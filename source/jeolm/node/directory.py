import os
import os.path
from stat import S_ISDIR
from pathlib import PurePosixPath, PosixPath

from . import (
    Node, BuildableNode, PathNode, BuildablePathNode,
    Command,
    NodeErrorReported )

import logging
logger = logging.getLogger(__name__)

from typing import ClassVar, Type, Optional, Iterable, Sequence, Set

class MakeDirCommand(Command):
    """
    Create a directory.

    Attributes (additional to superclasses):
        parents (bool):
            True if the parents of directory will be created if needed.
    """

    node: 'DirectoryNode'

    def __init__(self, node: 'DirectoryNode', *, parents: bool) -> None:
        assert isinstance(node, DirectoryNode), type(node)
        super().__init__(node)
        self.parents = parents

    async def run(self) -> None:
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
        self.node.updated = True

class DirectoryNode(BuildablePathNode):
    """
    Represents a directory.
    """

    _Command: ClassVar[Type[MakeDirCommand]] = MakeDirCommand

    command: MakeDirCommand

    def __init__( self, path: PosixPath,
        *, parents: bool = False,
        name: Optional[str] = None, needs: Iterable[Node] = (),
    ) -> None:
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
        super().__init__(path, name=name, needs=needs)
        self.command = self._Command(self, parents=parents)

    def _load_mtime(self) -> None:
        """
        Set node.mtime attribute to appropriate value.

        Set node.mtime to None if node.path does not exist.
        Otherwise, set self.mtime to 0.
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

    def _needs_build(self) -> bool:
        if self._forced:
            return True
        return self.mtime is None


class _CheckDirectoryNode(Node):

    dir_node: 'BuildDirectoryNode'

    _rogue_names: Optional[Sequence[str]]

    def __init__( self, dir_node: 'BuildDirectoryNode',
        *, name: Optional[str] = None, needs: Iterable[Node] = (),
    ) -> None:
        super().__init__(name=name, needs=needs)
        self.dir_node = dir_node
        self.path = dir_node.path
        self._rogue_names = None

    def _find_rogue_names(self) -> Sequence[str]:
        if os.path.lexists(self.path):
            return sorted(
                set(os.listdir(self.path)) - self.dir_node.approved_names
            )
        else:
            return []

    @property
    def rogue_names(self) -> Sequence[str]:
        if self._rogue_names is not None:
            return self._rogue_names
        rogue_names = self._rogue_names = tuple(self._find_rogue_names())
        return rogue_names

    def root_relative(self, path: PosixPath) -> PurePosixPath:
        return self.dir_node.root_relative(path)

class _CleanupCommand(Command):

    node: '_PreCleanupNode'

    async def run(self) -> None:
        for rogue_name in self.node.rogue_names:
            rogue_path = self.node.path / rogue_name
            if rogue_path.is_dir():
                self.logger.error(
                    "Detected rogue directory <RED>%(path)s<NOCOLOUR>",
                    dict(path=self.node.root_relative(rogue_path)) )
                raise NodeErrorReported from IsADirectoryError()
            self.logger.warning(
                "Detected rogue file <YELLOW>%(path)s<NOCOLOUR>, removing",
                dict(path=self.node.root_relative(rogue_path)) )
            rogue_path.unlink()
        self.node.modified = True
        self.node.updated = True

class _PreCleanupNode(_CheckDirectoryNode, BuildableNode):

    command: '_CleanupCommand'

    def __init__( self, dir_node: 'BuildDirectoryNode',
        *, name: Optional[str] = None, needs: Iterable[Node] = (),
    ) -> None:
        super().__init__(dir_node, name=name, needs=needs)
        self.command = _CleanupCommand(self)

    def _needs_build(self) -> bool:
        if self._forced:
            return True
        return len(self.rogue_names) > 0

class _PostCheckNode(_CheckDirectoryNode):

    # Override
    async def update_self(self) -> None:
        for rogue_name in self.rogue_names:
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

    approved_names: Set[str]
    pre_cleanup_node: _PreCleanupNode
    post_check_node: _PostCheckNode

    def __init__( self, path: PosixPath,
        *, parents: bool = False,
        name: Optional[str] = None, needs: Iterable[Node] = (),
    ) -> None:
        super().__init__( path, parents=parents,
            name=name, needs=needs )
        self.approved_names = set()
        self.pre_cleanup_node = _PreCleanupNode( self,
            name='{}:pre-cleanup'.format(name), needs=(self,) )
        self.post_check_node = _PostCheckNode( self,
            name='{}:post-check'.format(name),
            needs=(self, self.pre_cleanup_node),
        )

    def register_node(self, node: PathNode) -> None:
        if not isinstance(node, PathNode):
            raise TypeError(type(node))
        path = node.path
        if path.parent != self.path:
            raise ValueError(path)
        self.approved_names.add(path.name)
        self.pre_cleanup_node.append_needs(node)
        if isinstance(node, BuildDirectoryNode):
            self.pre_cleanup_node.append_needs(node.pre_cleanup_node)
            self.post_check_node.append_needs(node.post_check_node)

