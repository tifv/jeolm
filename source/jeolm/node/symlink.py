import os
import os.path

from pathlib import PurePosixPath

from . import ProductNode, FilelikeNode, _mtime_less

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


class SymLinkNode(ProductNode):
    """
    Represents a symbolic link to some other path.

    Attributes (additional to superclasses):
        source (PathNode):
            derived from ProductNode, this attribute is assigned specific
            semantics: it is the target of symbolic link.
    """

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
            self.link_target = str(source.path)
        else:
            self.link_target = str(_naive_relative_to(
                source.path, self.path.parent ))

        def link_command():
            if not isinstance(self.link_target, str):
                raise TypeError(type(self.link_target))
            if os.path.lexists(str(self.path)):
                self.path.unlink()
            self.log(logging.INFO, (
                '<source=<CYAN>{node.source.name}<NOCOLOUR>> '
                '<GREEN>ln --symbolic {node.link_target} '
                    '{node.relative_path}<NOCOLOUR>'
                .format(node=self) ))
            os.symlink(self.link_target, str(self.path))
            self.modified = True
        self.set_command(link_command)

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
        assert source_mtime is not None, self
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
        path = str(self.path)
        return not (
            self.mtime is not None and
            os.path.islink(path) and
            self.link_target == os.readlink(path) )


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
    original node.

    Attributes (additional to superclasses):
        source (PathNode):
            derived from ProductNode, this attribute is assigned specific
            semantics: it is the node to be proxy for.
    """

    def __init__(self, source, *, name=None, needs=(), **kwargs):
        """
        Initialize SymLinkNode instance.

        Args:
            source (PathNode):
                passed to the superclass; source.path becomes self.path.
            name (optional)
                passed to the superclass.
            needs (optional)
                must be an empty iterable.
        """
        if list(needs):
            raise ValueError("ProxyNode does not accept any excess needs.")
        super().__init__( source=source, path=source.path,
            name=name, **kwargs )

    # Override
    def _update_self(self):
        self._load_mtime()
        self.modified = self.source.modified

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

