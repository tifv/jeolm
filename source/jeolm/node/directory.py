import os
import os.path
from stat import S_ISDIR

from . import BuildablePathNode, Command

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

    def __call__(self):
        super().__call__()
        node = self.node
        path = node.path
        parents = self.parents
        if os.path.lexists(str(path)):
            path.unlink()
        self.logger.info(
            "<GREEN>%(command)s %(path)s<NOCOLOUR>",
            dict(
                command='mkdir --parents' if parents else 'mkdir',
                path=self.node.relative_path, )
        )
        # rwxr-xr-x
        path.mkdir(mode=0b111101101, parents=parents)
        node.modified = True


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


