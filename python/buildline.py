import readline
import traceback

from pathlib import Path, PurePosixPath
import pyinotify

import jeolm.builder
import jeolm.filesystem
import jeolm.metadata

from jeolm.commands import review
from jeolm.diffprint import log_metadata_diff
import jeolm.completion

from jeolm.records import RecordPath
from jeolm.target import Target, TargetError

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
if __name__ == '__main__':
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    from jeolm.fancify import FancifyingFormatter as Formatter
    handler.setFormatter(Formatter("%(name)s: %(message)s"))
    logger.addHandler(handler)

def mainloop(fs):
    md = NotifiedMetadataManager(fs=fs)
    Driver = fs.find_driver_class()
    md.review(PurePosixPath(), recursive=True)
    driver = Driver()
    md.feed_metadata(driver)

    def review_metadata():
        with log_metadata_diff(md):
            review_list = md.generate_review_list()
            assert isinstance(review_list, (list, tuple)), type(review_list)
            for review_file in review_list:
                try:
                    review([review_file], fs=fs, md=md, recursive=True)
                except Exception as exc:
                    traceback.print_exc()
                    logger.error(
                        "<BOLD>Error occured while reviewing "
                        "<RED>{}<NOCOLOUR>.<RESET>"
                        .format(review_file.relative_to(fs.source_dir)) )
        if review_list:
            driver.clear()
            md.feed_metadata(driver)

    completer = jeolm.completion.Completer(driver=driver).readline_completer
    readline.set_completer(completer)
    readline.set_completer_delims('')
    readline.parse_and_bind('tab: complete')

    target = None
    while True:
        try:
            target_s = input('jeolm> ')
        except (KeyboardInterrupt, EOFError):
            print()
            md.dump_metadata()
            raise SystemExit
        review_metadata()
        if target_s == '':
            pass # use previous target
        else:
            try:
                target = Target.from_string(target_s)
            except TargetError:
                traceback.print_exc()
                continue
        if target is None:
            continue
        try:
            builder = jeolm.builder.Builder([target], fs=fs, driver=driver,
                force=None, delegate=True )
            builder.build()
        except Exception:
            traceback.print_exc()


class NotifiedMetadataManager(jeolm.metadata.MetadataManager):

    creative_mask = (
        pyinotify.IN_CREATE | pyinotify.IN_CLOSE_WRITE |
        pyinotify.IN_MOVED_TO )
    destructive_mask = pyinotify.IN_MOVED_FROM | pyinotify.IN_DELETE
    self_destructive_mask = pyinotify.IN_MOVE_SELF | pyinotify.IN_DELETE_SELF
    mask = creative_mask | destructive_mask | self_destructive_mask

    def __init__(self, *, fs):
        self.review_set = set()
        self.wm = wm = pyinotify.WatchManager()
        self.eh = eh = self.EventHandler(md=self)
        self.notifier = pyinotify.Notifier(wm, eh, timeout=0)
        self.wdm = self.WatchDescriptorManager()
        super().__init__(fs=fs)
        self.wdm.add(self.wm.add_watch(
            str(self.fs.source_dir), self.mask, rec=False ))
        self.source_dir_wd, = self.wdm.path_by_wd

    def generate_review_list(self):
        if not self.notifier.check_events():
            return ()
        self.eh.prepare_event_lists()
        self.notifier.read_events()
        self.notifier.process_events()
        creative_events, destructive_events = self.eh.get_event_lists()
        if self.source_dir_wd in self.eh.distrusted_wds:
            raise RuntimeError(
                "Source directory appears to be moved or deleted, "
                "unable to continue." )

        created_path_set = set(
            self.filter_reasonable_paths(creative_events) )
        destroyed_path_set = set(
            self.filter_reasonable_paths(destructive_events) )
        return list(destroyed_path_set) + \
            list(created_path_set - destroyed_path_set)

    @classmethod
    def filter_reasonable_paths(cls, events):
        for event in events:
            path = Path(event.pathname)
            if (event.dir and path.suffix != ''):
                continue
            if (not event.dir and path.suffix not in cls.source_types):
                continue
            yield path

    def _create_record(self, path, parent_record, key):
        if path.suffix == '':
            source_path = str(self.fs.source_dir/path.as_inpath())
            self.wdm.add(self.wm.add_watch(source_path, self.mask, rec=False))
        return super()._create_record(path, parent_record, key)

    def _delete_record(self, path, *args, **kwargs):
        if path.suffix == '':
            source_path = str(self.fs.source_dir/path.as_inpath())
            self.wm.rm_watch(self.wdm.pop(path=source_path))
        return super()._delete_record(path, *args, **kwargs)

    class WatchDescriptorManager:
        def __init__(self):
            self.wd_by_path = dict()
            self.path_by_wd = dict()
            super().__init__()

        def add(self, mapping):
            for path, wd in mapping.items():
                logger.debug("<GREEN>Start<NOCOLOUR> watching "
                    "path=<MAGENTA>{path}<NOCOLOUR> "
                    "(wd=<BLUE>{wd}<NOCOLOUR>)"
                    .format(path=path, wd=wd) )
                assert path not in self.wd_by_path
                assert wd not in self.path_by_wd
                self.wd_by_path[path] = wd
                self.path_by_wd[wd] = path

        def pop(self, *, path):
            wd = self.wd_by_path.pop(path)
            reverse_path = self.path_by_wd.pop(wd)
            logger.debug("<RED>Stop<NOCOLOUR> watching "
                "path=<MAGENTA>{path}<NOCOLOUR> "
                "(wd=<CYAN>{wd}<NOCOLOUR>)"
                .format(path=path, wd=wd) )
            assert reverse_path == path
            return wd

    class EventHandler(pyinotify.ProcessEvent):

        def prepare_event_lists(self):
            self.creative_events = []
            self.destructive_events = []
            self.distrusted_wds = set()

        def get_event_lists(self):
            """
            Return pair of lists (creative_events, destructive_events).

            Exclude any events from distrusted watches.
            """
            distrusted_wds = self.distrusted_wds
            return [
                event for event in self.creative_events
                if event.wd not in distrusted_wds
            ], [
                event for event in self.destructive_events
                if event.wd not in distrusted_wds
            ]

        def process_creative_event(self, event):
            self.creative_events.append(event)

        process_IN_CREATE = process_creative_event
        process_IN_CLOSE_WRITE = process_creative_event
        process_IN_MOVED_TO = process_creative_event

        def process_destructive_event(self, event):
            self.destructive_events.append(event)

        process_IN_DELETE = process_destructive_event
        process_IN_MOVED_FROM = process_destructive_event

        def process_self_destructive_event(self, event):
            self.distrusted_wds.add(event.wd)

        process_IN_DELETE_SELF = process_self_destructive_event
        process_IN_MOVE_SELF = process_self_destructive_event

if __name__ == '__main__':
    from jeolm import nodes
    from jeolm import setup_logging

    setup_logging(verbose=False)
    try:
        fs = jeolm.filesystem.FilesystemManager(root=Path.cwd())
    except jeolm.filesystem.RootNotFoundError:
        raise SystemExit
    nodes.PathNode.root = fs.root
    fs.report_broken_links()
    fs.load_local_module()

    mainloop(fs)

