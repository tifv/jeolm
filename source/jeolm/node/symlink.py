import os
import os.path

from pathlib import PurePosixPath

from . import ProductNode, FilelikeNode, Command, _mtime_less

import logging
logger = logging.getLogger(__name__)


def _naive_relative_to(path, root):
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
    if any('..' in p.parts for p in (path, root)):
        raise ValueError(path, root)
    upstairs = 0
    while root not in path.parents:
        parent = root.parent
        assert parent != root
        root = parent
        upstairs += 1
    return PurePosixPath(*
        ['..'] * upstairs + [path.relative_to(root)] )

class SymLinkCommand(Command):

    def __init__(self, node, target):
        assert isinstance(node, SymLinkNode), type(node)
        super().__init__(node)
        assert isinstance(target, str), type(target)
        self.target = target

    def __call__(self):
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
        os.symlink(self.target, str(self.node.path))
        self.node.modified = True
        super().__call__()

    def _clear_path(self):
        self.node.path.unlink()

class SymLinkNode(ProductNode):
    """
    Represents a symbolic link to some other path.

    Attributes (additional to superclasses):
        source (PathNode):
            derived from ProductNode, this attribute is assigned specific
            semantics: it is the target of symbolic link.
    """

    _Command = SymLinkCommand

    def __init__(self, source, path, *, relative=True,
        name=None, needs=(), **kwargs
    ):
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
        super().__init__( source=source, path=path,
            name=name, needs=needs, **kwargs )

        if not relative:
            target = str(source.path)
        else:
            target = str(_naive_relative_to(
                source.path, self.path.parent ))

        self.set_command(self._Command(self, target))

        self.old_target = None

    wants_concurrency = False

    def _load_mtime(self):
        """
        Set node.mtime attribute to appropriate value.

        Adopt node.mtime and node.modified: if link source is modified, then
        node is also modified; node.mtime should always be greater than or
        equal to source.mtime, unless the link does not exist.
        """
        super()._load_mtime()
        mtime = self.mtime
        if mtime is None:
            return
        source = self.source
        source_mtime = source.mtime
        if source_mtime is None:
            raise RuntimeError
        if _mtime_less(mtime, source_mtime):
            self.mtime = source_mtime
        if source.modified:
            self.modified = True

    def _needs_build(self):
        """
        If the node needs to be (re)built.

        Override.
        SymLinkNode needs to be rebuilt in the following cases:
          - node.path does not exist as filesystem path;
          - node.path is not a link;
          - node.path is a link, but wrong link.
        Superclasses ignored.
        """
        if self.mtime is not None and os.path.islink(str(self.path)):
            self.old_target = os.readlink(str(self.path))
            if self.command.target == self.old_target:
                return False
        return True


class SymLinkedFileNode(SymLinkNode, FilelikeNode):

    def __init__(self, source, path, *, relative=True,
        name=None, needs=(), **kwargs
    ):
        if not isinstance(source, FilelikeNode):
            raise TypeError(type(source))
        super().__init__( source, path, relative=relative,
            name=name, needs=needs, **kwargs )

class ProxyNode(ProductNode):
    """
    Represents the same path as its source.

    This allows assigning some attributes which sould not belong to the
    original node, or adding some post-dependencies.

    Attributes (additional to superclasses):
        source (PathNode):
            derived from ProductNode, this attribute is assigned specific
            semantics: it is the node to be proxy for.
    """

    def __init__(self, source, *, name=None, needs=(), **kwargs):
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
        super().__init__( source=source, path=source.path,
            name=name, needs=needs, **kwargs )

    wants_concurrency = False

    # Override
    def update_self(self):
        self._load_mtime()
        self.modified = self.source.modified
        self.updated = True

    def _load_mtime(self):
        self.mtime = self.source.mtime

    def _needs_build(self):
        raise RuntimeError("You should not be here.")

    def _append_needs(self, node):
        if node is not self.source:
            raise RuntimeError(node)

class ProxyFileNode(ProxyNode, FilelikeNode):

    def __init__(self, source, *, name=None, needs=(), **kwargs):
        if not isinstance(source, FilelikeNode):
            raise TypeError(type(source))
        super().__init__(source, name=name, needs=needs, **kwargs)

