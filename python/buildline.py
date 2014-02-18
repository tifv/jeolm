import readline

from pathlib import Path, PurePosixPath
import pyinotify as pyin

from jeolm.builder import Builder
from jeolm.filesystem import FilesystemManager
from jeolm.metadata import MetadataManager

from jeolm.commands import review, print_metadata_diff
from jeolm.completion import Completer

from jeolm.records import RecordPath
from jeolm.target import Target, TargetError

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
if __name__ == '__main__':
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    logger.addHandler(handler)

def mainloop(fs):
    md = NotifiedMetadataManager(fs=fs)
    Driver = fs.find_driver_class()
    md.review(PurePosixPath(), recursive=True)
    driver = Driver()
    md.feed_metadata(driver)

    def review_metadata():
        with print_metadata_diff(md):
            review_list = md.generate_review_list()
            metadata_changed = bool(review_list)
            if metadata_changed:
                review(review_list, fs=fs, md=md, recursive=True)
        if metadata_changed:
            driver.clear()
            md.feed_metadata(driver)

    completer = Completer(driver=driver).readline_completer
    readline.set_completer(completer)
    readline.set_completer_delims('')
    readline.parse_and_bind('tab: complete')

    while True:
        try:
            target_s = input('jeolm> ')
        except (KeyboardInterrupt, EOFError):
            print()
            raise SystemExit
        review_metadata()
        if target_s == '':
            target = None
        else:
            try:
                target = Target.from_string(target_s)
            except TargetError:
                import sys, traceback
                traceback.print_exception(*sys.exc_info())
                continue
        if target is None:
            continue
        try:
            builder = Builder([target], fs=fs, driver=driver,
                force=None, delegate=True )
            builder.build()
        except Exception:
            import sys, traceback
            traceback.print_exception(*sys.exc_info())


class NotifiedMetadataManager(MetadataManager):

    creative_mask = pyin.IN_CREATE | pyin.IN_CLOSE_WRITE | pyin.IN_MOVED_TO
    destructive_mask = pyin.IN_MOVED_FROM | pyin.IN_DELETE
    self_destructive_mask = pyin.IN_MOVE_SELF | pyin.IN_DELETE_SELF
    mask = creative_mask | destructive_mask | self_destructive_mask

    def __init__(self, *, fs):
        self.review_set = set()
        self.wm = wm = pyin.WatchManager()
        self.eh = eh = self.EventHandler(md=self)
        self.notifier = pyin.Notifier(wm, eh, timeout=0)
        self.wdm = self.WatchDescriptorManager()
        super().__init__(fs=fs)

    def generate_review_list(self):
        notifier = self.notifier
        if not notifier.check_events():
            return ()
        notifier.read_events()
        notifier.process_events()
        overreviewed = set()
        for reviewed in self.review_set:
            assert reviewed.suffix in self.source_types, reviewed
            is_overreviewed = any(
                path in reviewed.parents
                for path in self.review_set
                if path is not reviewed )
            if is_overreviewed:
                overreviewed.add(review_candidate)
        review_list = sorted(self.review_set - overreviewed)
        self.review_set.clear()
        logger.debug(review_list)
        while self.wdm.untrusted_wds:
            wd = next(iter(self.wdm.untrusted_wds))
            self.unmerge(RecordPath(
                Path(self.wdm.path_by_wd[wd]).relative_to(self.fs.source_dir)
            ))
        return review_list

    def _create_record(self, path, record):
        if path.suffix == '':
            source_path = str(self.fs.source_dir/path.as_inpath())
            self.wdm.add(self.wm.add_watch(source_path, self.mask, rec=False))
        return super()._create_record(path, record)

    def _destroy_record(self, path, record):
        if path.suffix == '':
            source_path = str(self.fs.source_dir/path.as_inpath())
            self.wm.rm_watch(self.wdm.pop(path=source_path))
        return super()._destroy_record(path, record)

    class EventHandler(pyin.ProcessEvent):
        def my_init(self, md):
            self.md = md

        def process_needs_review(self, event):
            if not self.md.wdm.is_trusted(event.wd):
                return
            path = Path(event.pathname)
            if event.dir:
                if path.suffix != '':
                    return
            else:
                if path.suffix not in self.md.source_types or path.suffix == '':
                    return
            self.md.review_set.add(path)

        process_IN_CREATE = process_needs_review
        process_IN_CLOSE_WRITE = process_needs_review
        process_IN_MOVED_TO = process_needs_review

        process_IN_DELETE = process_needs_review
        process_IN_MOVED_FROM = process_needs_review

        def process_self_destructive(self, event):
            if not self.md.wdm.is_trusted(event.wd):
                return
            self.md.wdm.distrust(event.wd)

        process_IN_DELETE_SELF = process_self_destructive
        process_IN_MOVE_SELF = process_self_destructive

    class WatchDescriptorManager:
        def __init__(self):
            self.wd_by_path = dict()
            self.path_by_wd = dict()
            self.untrusted_wds = set()
            super().__init__()

        def add(self, mapping):
            for path, wd in mapping.items():
                logger.debug("Start watching path={path} (wd={wd})"
                    .format(path=path, wd=wd) )
                assert path not in self.wd_by_path
                assert wd not in self.path_by_wd
                self.wd_by_path[path] = wd
                self.path_by_wd[wd] = path

        def pop(self, *, path):
            wd = self.wd_by_path.pop(path)
            reverse_path = self.path_by_wd.pop(wd)
            logger.debug("Stop watching path={path} (wd={wd})"
                .format(path=path, wd=wd) )
            assert reverse_path == path
            self.untrusted_wds.discard(wd)
            return wd

        def distrust(self, wd):
            path = self.path_by_wd[wd]
            logger.debug("Distrusting path={path} (wd={wd})"
                .format(path=path, wd=wd) )
            for subpath, subwd in self.wd_by_path.items():
                if subpath.startswith(path + '/'):
                    self.untrusted_wds.add(subwd)
            self.untrusted_wds.add(wd)

        def is_trusted(self, wd):
            return wd not in self.untrusted_wds

if __name__ == '__main__':
    from jeolm import nodes
    from jeolm import setup_logging

    setup_logging(verbose=False)
    try:
        fs = FilesystemManager(root=Path.cwd())
    except filesystem.RootNotFoundError:
        raise SystemExit
    nodes.PathNode.root = fs.root
    fs.report_broken_links()
    fs.load_local_module()

    mainloop(fs)

