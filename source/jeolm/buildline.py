import readline
import traceback
from contextlib import contextmanager, suppress

from pathlib import Path, PurePosixPath
import pyinotify

import jeolm
import jeolm.commands
import jeolm.commands.review
import jeolm.commands.clean
import jeolm.project
import jeolm.node
import jeolm.node_factory.target
import jeolm.metadata

from jeolm.commands.diffprint import log_metadata_diff

from jeolm.target import Target, TargetError
from jeolm.records import RecordPath, RecordNotFoundError

from jeolm.node import NodeErrorReported

import logging
logger = logging.getLogger(__name__)


class BuildLine:

    def __init__(self, *,
        project, node_updater
    ):
        self.project = project
        self.node_updater = node_updater
        metadata_class = self.project.metadata_class
        if not issubclass(NotifiedMetadata, metadata_class):
            metadata_class = type( '_Metadata',
                (metadata_class, NotifiedMetadata), {} )
        else:
            metadata_class = NotifiedMetadata
        self.metadata = metadata_class(project=self.project)
        self.metadata.review(PurePosixPath())
        self.driver = (self.project.driver_class)()
        self.metadata.feed_metadata(self.driver)
        self.history_filename = str(self.project.build_dir/'buildline.history')

    @contextmanager
    def readline_setup(self):
        """
        Return a context manager.

        Should enclose the code where readline is actually working.

        On exit, writes readline history.
        """
        readline.set_completer(
            Completer(driver=self.driver).readline_completer )
        readline.set_completer_delims(';')
        readline.parse_and_bind('tab: complete')
        with suppress(FileNotFoundError):
            readline.read_history_file(self.history_filename)
        readline.set_history_length(1000)
        try:
            yield
        finally:
            readline.write_history_file(self.history_filename)

    def review_metadata(self):

        review_list = self.metadata.generate_review_list()
        assert isinstance(review_list, (tuple, list))
        if not review_list:
            return

        with log_metadata_diff(self.metadata, logger=logger):
            for review_path in review_list:
                inpath, = jeolm.commands.review.resolve_inpaths(
                    [review_path], source_dir=self.project.source_dir )
                try:
                    self.metadata.review(inpath)
                except Exception: # pylint: disable=broad-except
                    logger.exception(
                        "Error occured while reviewing "
                            "<RED>%(inpath)s<NOCOLOUR>",
                        dict(inpath=inpath) )
        self.driver.clear()
        self.metadata.feed_metadata(self.driver)

    def main(self):
        try:
            self.mainloop()
        finally:
            self.metadata.dump_metadata_cache()

    def mainloop(self):
        targets = []
        while True:
            try:
                targets_string = self.input()
            except (KeyboardInterrupt, EOFError):
                print() # clear the line before returning control
                return
            self.review_metadata()
            if not targets_string:
                pass # use previous target
            elif targets_string == 'clean':
                targets = []
                jeolm.commands.clean.clean_build_links(self.project.root)
            elif targets_string == 'dump':
                targets = []
                self.metadata.dump_metadata_cache()
            else:
                try:
                    targets = self.parse_targets(targets_string)
                except TargetError:
                    traceback.print_exc()
                    continue
            if not targets:
                continue
            try:
                self.build(targets)
            except Exception: # pylint: disable=broad-except
                traceback.print_exc()

    @classmethod
    def input(cls):
        return input('jeolm> ')

    @classmethod
    def parse_targets(cls, targets_string):
        targets = []
        for piece in targets_string.split(';'):
            target_string = piece.strip()
            if not target_string:
                continue
            targets.append(Target.from_string(target_string))
        return targets

    def build(self, targets):
        target_node_factory = jeolm.node_factory.target.TargetNodeFactory(
            project=self.project, driver=self.driver, )
        target_node = target_node_factory(targets, delegate=True)
        with suppress(NodeErrorReported):
            self.node_updater.update(target_node)

class NotifiedMetadata(jeolm.metadata.Metadata):

    # pylint: disable=no-member
    creative_mask = (
        pyinotify.IN_CREATE | pyinotify.IN_CLOSE_WRITE |
        pyinotify.IN_MOVED_TO )
    destructive_mask = pyinotify.IN_MOVED_FROM | pyinotify.IN_DELETE
    self_destructive_mask = pyinotify.IN_MOVE_SELF | pyinotify.IN_DELETE_SELF
    mask = creative_mask | destructive_mask | self_destructive_mask
    # pylint: enable=no-member

    def __init__(self, *, project):
        self.review_set = set()
        self.watch = pyinotify.WatchManager()
        self.events = self.EventHandler()
        self.notifier = pyinotify.Notifier(self.watch, self.events, timeout=0)
        self.descriptors = self.WatchDescriptorManager()
        super().__init__(project=project)
        self.descriptors.add(self.watch.add_watch(
            str(self.project.source_dir), self.mask, rec=False ))
        self.source_dir_wd, = self.descriptors.path_by_wd

    def generate_review_list(self):
        if not self.notifier.check_events():
            return ()
        self.events.prepare_event_lists()
        self.notifier.read_events()
        self.notifier.process_events()
        creative_events, destructive_events = self.events.get_event_lists()
        if self.source_dir_wd in self.events.distrusted_wds:
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
        """Yield paths."""
        for event in events:
            path = Path(event.pathname)
            if event.dir and path.suffix != '':
                continue
            if not event.dir and ( path.suffix == '' or
                path.suffix not in cls.source_types
            ):
                continue
            yield path

    def _create_record(self, path, parent_record):
        if path.suffix == '':
            source_path = str(self.project.source_dir/path.as_source_path())
            self.descriptors.add(self.watch.add_watch(
                source_path, self.mask, rec=False ))
        return super()._create_record(path, parent_record)

    def _delete_record(self, path, *args, **kwargs):
        if path.suffix == '':
            source_path = str(self.project.source_dir/path.as_source_path())
            self.watch.rm_watch(self.descriptors.pop(path=source_path))
        return super()._delete_record(path, *args, **kwargs)

    class WatchDescriptorManager:
        def __init__(self):
            self.wd_by_path = dict()
            self.path_by_wd = dict()
            super().__init__()

        def add(self, mapping):
            for path, descriptor in mapping.items():
                logger.debug(
                    "Start watching path %(path)s (wd=%(descriptor)d)",
                    dict(path=path, descriptor=descriptor) )
                assert path not in self.wd_by_path
                assert descriptor not in self.path_by_wd
                self.wd_by_path[path] = descriptor
                self.path_by_wd[descriptor] = path

        def pop(self, *, path):
            descriptor = self.wd_by_path.pop(path)
            reverse_path = self.path_by_wd.pop(descriptor)
            logger.debug(
                "Stop watching path %(path)s (wd=%(descriptor)d)",
                dict(path=path, descriptor=descriptor) )
            assert reverse_path == path
            return descriptor

    class EventHandler(pyinotify.ProcessEvent):

        def prepare_event_lists(self):
            # pylint: disable=attribute-defined-outside-init
            self.creative_events = []
            self.destructive_events = []
            self.distrusted_wds = set()
            # pylint: enable=attribute-defined-outside-init

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
        return path in self.driver and self.driver.path_is_targetable(path)

    def _list_subtargets(self, path):
        with suppress(RecordNotFoundError):
            yield from self.driver.list_targetable_children(path)

    def complete_target(self, uncompleted_arg):
        """Return an iterator over completions."""
        if '[' in uncompleted_arg or ']' in uncompleted_arg:
            return
        if uncompleted_arg.startswith(' '):
            prefix = ' '
            uncompleted_arg = uncompleted_arg.lstrip()
        else:
            prefix = ''
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
                yield prefix + str(uncompleted_parent)
        else:
            uncompleted_parent = uncompleted_path.parent
            uncompleted_name = uncompleted_path.name

        for path in self._list_subtargets(uncompleted_parent):
            assert uncompleted_parent == path.parent, path
            name = path.name
            if not name.startswith(uncompleted_name):
                continue
            yield prefix + str(uncompleted_parent/name)

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

