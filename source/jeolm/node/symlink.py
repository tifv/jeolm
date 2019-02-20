import os
import os.path

from pathlib import PurePosixPath, PosixPath

from . import ( Node, PathNode, ProductNode, FilelikeNode,
    Command, MissingTargetError, _mtime_less )

import logging
logger = logging.getLogger(__name__)

from typing import ClassVar, Type, Optional, Iterable


def _naive_relative_to(path: PosixPath, root: PosixPath) -> PurePosixPath:
    """
    Compute relative PurePosixPath, result may include '..' parts.

    Both arguments must be absolute PurePosixPath's and lack '..' parts.

    Possibility of symlinks is ignored, i. e. arguments are interpreted
    as resolved paths.
    """
    if not path.is_absolute():
        raise ValueError(path)
    if not root.is_absolute():
        raise ValueError(root)
    if '..' in path.parts:
        raise ValueError(path)
    if '..' in root.parts:
        raise ValueError(root)
    upstairs = 0
    while root not in path.parents:
        parent = root.parent
        assert parent != root
        root = parent
        upstairs += 1
    return PurePosixPath(
        * (('..',) * upstairs),
        path.relative_to(root) )

class SymLinkCommand(Command):

    node: 'SymLinkNode'

    def __init__(self, node: 'SymLinkNode', target: str) -> None:
        assert isinstance(node, SymLinkNode), type(node)
        super().__init__(node)
        assert isinstance(target, str), type(target)
        self.target = target

    async def run(self) -> None:
        if os.path.lexists(str(self.node.path)):
            self._clear_path()
        self.logger.debug(
            "<source=<CYAN>%(source_name)s<NOCOLOUR>> "
            "symlink \"<ITALIC>%(link_target)s<UPRIGHT>\" "
            "to <ITALIC>%(path)s<UPRIGHT>",
            dict(
                source_name=self.node.source.name,
                link_target=self.target,
                path=self.node.relative_path, )
        )
        self.node.path.symlink_to(self.target)
        self.node.modified = True
        self.node.updated = True

    def _clear_path(self) -> None:
        self.node.path.unlink()

class SymLinkNode(ProductNode):
    """
    Represents a symbolic link to some other path.

    Attributes (additional to superclasses):
        source (PathNode):
            derived from ProductNode, this attribute is assigned specific
            semantics: it is the target of symbolic link.
    """

    _Command: ClassVar[Type[SymLinkCommand]] = SymLinkCommand

    command: SymLinkCommand
    current_target: Optional[str]

    def __init__( self, source: PathNode, path: PosixPath,
        *, relative: bool = True,
        name: Optional[str] = None, needs: Iterable[Node] = (),
    ) -> None:
        """
        Initialize SymLinkNode instance.

        Args:
            source (PathNode):
                passed to the superclass
            path (pathlib.Path):
                passed to the superclass.
            relative (bool):
                if the resulting symbolic link should be relative or absolute.
            name, needs (optional)
                passed to the superclass.
        """
        super().__init__( source, path,
            name=name, needs=needs )
        if not relative:
            target = str(source.path)
        else:
            target = str(_naive_relative_to(source.path, self.path.parent))
        self.command = self._Command(self, target)
        self.current_target = None

    def _load_mtime(self) -> None:
        """
        Set node.mtime attribute to appropriate value.

        Partial override.
        node.mtime is set to None in the following cases:
          - node.path does not exist as filesystem path;
          - node.path is not a link;
          - node.path is a link, but wrong link.

        Adopt node.mtime and node.modified: if link source is modified, then
        node is also modified; node.mtime should always be greater than or
        equal to source.mtime, unless the link does not exist.

        Also, set self.current_target to link target.
        """
        super()._load_mtime()
        if self.mtime is None:
            return
        if not self.path.is_symlink():
            self.mtime = None
            return
        self.current_target = os.readlink(str(self.path))
        if self.current_target != self.command.target:
            self.mtime = None
            return
        # link is pointing at the right file
        source = self.source
        if source.mtime is None:
            raise MissingTargetError(source)
        if _mtime_less(self.mtime, source.mtime):
            self.mtime = source.mtime
        if source.modified:
            self.modified = True

    def _needs_build(self) -> bool:
        if self._forced:
            return True
        return self.mtime is None


class SymLinkedFileNode(SymLinkNode, FilelikeNode):

    def __init__( self, source: FilelikeNode, path: PosixPath,
        *, relative: bool = True,
        name: Optional[str] = None, needs: Iterable[Node] = (),
    ) -> None:
        if not isinstance(source, FilelikeNode):
            raise TypeError(type(source))
        super().__init__( source, path, relative=relative,
            name=name, needs=needs )

class ProxyNode(PathNode):
    """
    Represents the same path as its source.

    This allows assigning some attributes which should not belong to the
    original node, or adding some post-dependencies.

    Attributes (additional to superclasses):
        source (PathNode):
            derived from ProductNode, this attribute is assigned specific
            semantics: it is the node to be proxy for.
    """

    def __init__( self, source: PathNode,
        *, name: Optional[str] = None, needs: Iterable[Node] = (),
    ) -> None:
        """
        Initialize ProxyNode instance.

        Args:
            source (PathNode):
                passed to the superclass; source.path becomes self.path.
            name (optional)
                passed to the superclass.
            needs (optional)
                passed to the superclass.
        """
        if not isinstance(source, PathNode):
            raise TypeError(type(source))
        self.source = source
        super().__init__( path=source.path,
            name=name, needs=(source, *needs) )

    # Override
    async def update_self(self) -> None:
        self._load_mtime()
        self.modified = self.source.modified
        self.updated = True

    def _load_mtime(self) -> None:
        self.mtime = self.source.mtime

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(name={self.name!r}, "
            f"source={self.source!r})" )

class ProxyFileNode(ProxyNode, FilelikeNode):

    def __init__( self, source: FilelikeNode,
        *, name: Optional[str] = None, needs: Iterable[Node] = (),
    ) -> None:
        if not isinstance(source, FilelikeNode):
            raise TypeError(type(source))
        super().__init__(source, name=name, needs=needs)

