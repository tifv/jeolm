import readline
import subprocess
import traceback

from pathlib import Path, PurePosixPath
import pyinotify

import jeolm
import jeolm.local
import jeolm.node
import jeolm.node_factory
import jeolm.metadata

from jeolm.commands import review
from jeolm.diffprint import log_metadata_diff

from jeolm.record_path import RecordPath
from jeolm.target import Target, TargetError

import logging
if __name__ == '__main__':
    from jeolm import logger
else:
    logger = logging.getLogger(__name__) # pylint: disable=invalid-name


def mainloop(local, text_node_factory):
    md = NotifiedMetadataManager(local=local)
    driver_class = local.driver_class
    md.review(PurePosixPath(), recursive=True)
    driver = driver_class()
    md.feed_metadata(driver)

    def review_metadata():
        with log_metadata_diff(md, logger=logger):
            review_list = md.generate_review_list()
            assert isinstance(review_list, (list, tuple)), type(review_list)
            for review_path in review_list:
                try:
                    review([review_path], local=local, md=md, recursive=True)
                except Exception: # pylint: disable=broad-except
                    traceback.print_exc()
                    logger.error(
                        "<BOLD>Error occured while reviewing "
                        "<RED>{}<NOCOLOUR>.<RESET>"
                        .format(review_path.relative_to(local.source_dir)) )
        if review_list:
            driver.clear()
            md.feed_metadata(driver)

    completer = Completer(driver=driver).readline_completer
    readline.set_completer(completer)
    readline.set_completer_delims('')
    readline.parse_and_bind('tab: complete')

    target = None
    while True:
        try:
            target_s = input('jeolm> ')
        except (KeyboardInterrupt, EOFError):
            print()
            md.dump_metadata_cache()
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
            build(target, local, text_node_factory, driver)
        except subprocess.CalledProcessError as exception:
            if getattr(exception, 'reported', False):
                continue
            traceback.print_exc()
        except Exception: # pylint: disable=broad-except
            traceback.print_exc()

def build(target, local, text_node_factory, driver):
    target_node_factory = jeolm.node_factory.TargetNodeFactory(
        local=local, driver=driver,
        text_node_factory=text_node_factory )
    target_node = target_node_factory([target], delegate=True)
    target_node.update()


class NotifiedMetadataManager(jeolm.metadata.MetadataManager):

    # pylint: disable=no-member
    creative_mask = (
        pyinotify.IN_CREATE | pyinotify.IN_CLOSE_WRITE |
        pyinotify.IN_MOVED_TO )
    destructive_mask = pyinotify.IN_MOVED_FROM | pyinotify.IN_DELETE
    self_destructive_mask = pyinotify.IN_MOVE_SELF | pyinotify.IN_DELETE_SELF
    mask = creative_mask | destructive_mask | self_destructive_mask
    # pylint: enable=no-member

    def __init__(self, *, local):
        self.review_set = set()
        self.wm = wm = pyinotify.WatchManager()
        self.eh = eh = self.EventHandler(md=self)
        self.notifier = pyinotify.Notifier(wm, eh, timeout=0)
        self.wdm = self.WatchDescriptorManager()
        super().__init__(local=local)
        self.wdm.add(self.wm.add_watch(
            str(self.local.source_dir), self.mask, rec=False ))
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
            if event.dir and path.suffix != '':
                continue
            if (not event.dir and
                cls.source_types.get(path.suffix) in {'directory', None}
            ):
                continue
            yield path

    def _create_record(self, path, parent_record, key):
        if path.suffix == '':
            source_path = str(self.local.source_dir/path.as_inpath())
            self.wdm.add(self.wm.add_watch(source_path, self.mask, rec=False))
        return super()._create_record(path, parent_record, key)

    def _delete_record(self, path, *args, **kwargs):
        if path.suffix == '':
            source_path = str(self.local.source_dir/path.as_inpath())
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
                    "(wd=<CYAN>{wd}<NOCOLOUR>)"
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


class Completer:

    def __init__(self, driver):
        super().__init__()

        self.driver = driver

        self._saved_text = None
        self._saved_completion = None

    def _is_target(self, path):
        return path in self.driver and self.driver.metapath_is_targetable(path)

    def _list_subtargets(self, path):
        return self.driver.list_targetable_children(path)

    def complete_target(self, uncompleted_arg):
        """Return an iterator over completions."""
        if ' ' in uncompleted_arg:
            return

        uncompleted_path = RecordPath(uncompleted_arg)

        if uncompleted_path.is_root():
            uncompleted_parent = uncompleted_path
            uncompleted_name = ''
        elif uncompleted_arg.endswith('/'):
            uncompleted_parent = uncompleted_path
            uncompleted_name = ''
            if self._is_target(uncompleted_parent):
                yield str(uncompleted_parent)
        else:
            uncompleted_parent = uncompleted_path.parent
            uncompleted_name = uncompleted_path.name

        for path in self._list_subtargets(uncompleted_parent):
            assert uncompleted_parent == path.parent, path
            name = path.name
            if not name.startswith(uncompleted_name):
                continue
            yield str(uncompleted_parent/name)

    def readline_completer(self, text, state):
        try:
            if self._saved_text != text:
                self._saved_completion = list(self.complete_target(text))
                self._saved_text = text
            if state < len(self._saved_completion):
                return self._saved_completion[state]
            else:
                return None
        except Exception: # pylint: disable=broad-except
            traceback.print_exc()


def main():
    jeolm.setup_logging(verbose=True)
    try:
        local = jeolm.local.LocalManager(root=Path.cwd())
    except jeolm.local.RootNotFoundError:
        jeolm.local.report_missing_root()
        raise SystemExit
    jeolm.node.PathNode.root = local.root
    text_node_factory = jeolm.node_factory.TextNodeFactory(local=local)
    try:
        mainloop(local, text_node_factory)
    finally:
        text_node_factory.close()


if __name__ == '__main__':
    main()

