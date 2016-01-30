import os
import os.path
from stat import S_ISDIR

from . import (
    Node, BuildableNode, PathNode, BuildablePathNode,
    Command,
    NodeErrorReported )

import logging
logger = logging.getLogger(__name__)


class MakeDirCommand(Command):
    """
    Create a directory.

    Attributes (additional to superclasses):
        parents (bool):
            True if the parents of directory will be created if needed.
    """

    def __init__(self, node, *, parents):
        assert isinstance(node, DirectoryNode), type(node)
        super().__init__(node)
        self.parents = parents

    def call(self):
        path = self.node.path
        if os.path.lexists(str(path)):
            path.unlink()
        self.logger.debug(
            "create directory <ITALIC>%(path)s<UPRIGHT>%(parents)s",
            dict(
                path=self.node.relative_path,
                parents=' with parents' if self.parents else '')
        )
        # rwxr-xr-x
        path.mkdir(mode=0b111101101, parents=self.parents)
        self.node.modified = True
        super().call()


class DirectoryNode(BuildablePathNode):
    """
    Represents a directory.
    """

    _Command = MakeDirCommand

    def __init__(self, path,
        *, parents=False,
        name=None, needs=(), **kwargs
    ):
        """
        Initialize DirectoryNode instance.

        Args:
            path (pathlib.Path):
                passed to the superclass.
            parents (bool):
                if True then the parents of directory will be created if
                needed.
            name, needs (optional)
                passed to the superclass.
        """
        super().__init__(path=path, name=name, needs=needs, **kwargs)
        self.set_command(self._Command(self, parents=parents))

    wants_concurrency = False

    def _load_mtime(self):
        """
        Set node.mtime attribute to appropriate value.

        Set node.mtime to None if node.path does not exist.
        Otherwise, set self.mtime to 0.

        This method overrides normal behavior. It reflects the fact that
        directories cannot be modified: they either exist (mtime=0) or
        not (mtime=None). Directory real mtime changes with every new file
        in it, so using it would cause unnecessary updates.
        """
        try:
            stat = self.stat()
        except FileNotFoundError:
            self.mtime = None
            return
        if S_ISDIR(stat.st_mode):
            self.mtime = 0
        else:
            raise NotADirectoryError(
                "Found something where a directory should be: {}"
                .format(self.relative_path) )

    def _needs_build(self):
        """
        Return True if the node needs to be (re)built.

        Override.
        DirectoryNode needs to be rebuilt in the following cases:
          - path does not exist;
          - path is not a directory.
        Superclasses ignored.
        """
        if self.mtime is None:
            return True
        return False


class _CheckDirectoryNode(Node):

    def __init__(self, path, approved_names, *, name, needs=()):
        super().__init__(name=name, needs=needs)
        self.path = path
        self.approved_names = approved_names

    def _find_rogue_names(self):
        return set(os.listdir(str(self.path))) - self.approved_names

class _CleanupCommand(Command):

    def __init__(self, node):
        assert isinstance(node, _PreCleanupNode), type(node)
        super().__init__(node)

    def call(self):
        for rogue_name in self.node.rogue_names:
            rogue_path = self.node.path / rogue_name
            if rogue_path.is_dir():
                self.logger.error(
                    "Detected rogue directory <RED>%(path)s<NOCOLOUR>",
                    dict(path=rogue_path) )
                raise NodeErrorReported from IsADirectoryError()
            self.logger.warning(
                "Detected rogue file <YELLOW>%(path)s<NOCOLOUR>, removing",
                dict(path=rogue_path) )
            rogue_path.unlink()
        self.node.modified = True
        super().call()

class _PreCleanupNode(_CheckDirectoryNode, BuildableNode):

    def __init__(self, path, approved_names, *, name, needs=()):
        super().__init__(path, approved_names, name=name, needs=needs)
        self.set_command(_CleanupCommand(self))
        self.rogue_names = None

    wants_concurrency = False

    def _needs_build(self):
        rogue_names = self.rogue_names = self._find_rogue_names()
        return bool(rogue_names)

class _PostCheckNode(_CheckDirectoryNode):

    def update_self(self):
        for rogue_name in self._find_rogue_names():
            self.logger.warning(
                "Detected rogue path <YELLOW>%(path)s<NOCOLOUR>",
                dict(path=self.path / rogue_name) )
        self.updated = True

class BuildDirectoryNode(DirectoryNode):
    """
    Represents a build directory.

    Adds some control over the contents of the directory, so that rogue
    files will not interfere with the build process.
    """

    def __init__(self, path,
        *, parents=False,
        name=None, needs=(), **kwargs
    ):
        super().__init__(path=path, parents=parents, name=name, needs=needs)
        approved_names = self.approved_names = set()
        self.pre_cleanup_node = _PreCleanupNode(
            path, approved_names,
            name='{}:pre-cleanup'.format(name), needs=(self,) )
        self.post_check_node = _PostCheckNode(
            path, approved_names,
            name='{}:post-check'.format(name),
            needs=(self, self.pre_cleanup_node),
        )

    def register_node(self, node):
        if not isinstance(node, PathNode):
            raise TypeError(type(node))
        path = node.path
        if path.parent != self.path:
            raise ValueError(path)
        self.approved_names.add(path.name)
        self.pre_cleanup_node.append_needs(node)

