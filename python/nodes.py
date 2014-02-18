"""
Nodes, and dependency trees constructed of them.
"""

from itertools import chain

import os
from stat import S_ISDIR
import sys
import subprocess

from pathlib import Path, PurePath

import logging
from logging import DEBUG, INFO, WARNING, ERROR, CRITICAL
import warnings
logger = logging.getLogger(__name__)

__all__ = [
    'Node', 'NodeCycleError',
    'DatedNode', 'PathNode', 'ProductNode',
    'FileNode', 'TextNode', 'ProductFileNode',
    'LinkNode', 'DirectoryNode'
]

class NodeCycleError(RuntimeError):
    pass

class NodeMissingPathError(FileNotFoundError):
    pass

class Node:
    """
    Node represents target, or source, or whatever.

    Attributes
    ----------
    name
        str, some short-but-identifying name.
    needs
        list of Node instances, prerequisites of this node.
        Expectd to be populated with initialization,
        node.extend_needs() and node.append_needs() methods.
    rules
        list of functions, that are responsible for (re)building node
        and setting node.modified attribute as appropriate.
        Expected to be populated with @node.add_rule decorator.
    modified
        bool, True if node was modified, causing any
        dependent nodes to be rebuilt.  Only node.needs_build() method
        should be interested in quering this attribute.
    _updated
        bool, True if node.update() was ever triggered.
        Should be read and written only by node.update() method.
    _locked
        bool, dependency cycle protection.
        Should be read and written only by node.update() method.
    """

    def __init__(self, *, name=None, needs=(), rules=()):
        if name is not None:
            self.name = str(name)
        else:
            self.name = 'id{}'.format(id(instance))
        self.needs = list(needs)
        self.rules = list(rules)

        self._updated = False
        self.modified = False

        self._locked = False

    def update(self):
        """
        Update the node, recursively updating needs.
        """
        if self._locked:
            raise NodeCycleError(self.name)
        if self._updated:
            return
        self.update_needs()
        self.update_self()
        self._updated = True

    def update_needs(self):
        try:
            self._locked = True
            for node in self.needs:
                try:
                    node.update()
                except NodeCycleError as exception:
                    exception.args += (self.name,)
                    raise
        finally:
            self._locked = False

    def update_self(self):
        if self.needs_build():
            self.run_rules()

    def needs_build(self):
        """
        Return True if the node needs to be (re)built.

        Node needs build in the following case:
        1) any of needed nodes are modified.
        (Subclasses may introduce different conditions)
        """
        if any(node.modified for node in self.needs):
            return True
        return False

    def extend_needs(self, needs):
        needs = list(needs)
        for need in needs:
            if not isinstance(need, Node):
                raise TypeError(need)
        self.needs.extend(needs)
        return self

    def append_needs(self, *needs):
        self.extend_needs(needs)
        return self

    def force(self):
        self.needs_build = lambda: True

    def add_rule(self, rule):
        """Decorator."""
        self.rules.append(rule)
        return rule

    def run_rules(self):
        # Should be only called by self.update_self()
        for rule in self.rules:
            rule()

    def log(self, level, message):
        """
        Log a message specific for this node.

        Prepend a message with node.name and delegate to module logger.
        This function expects FancyFormatter to be used somewhere in
        logging facility.
        """
        if level <= INFO:
            colour = '<MAGENTA>'
            bold = ''
        elif level <= WARNING:
            colour = '<YELLOW>'
            bold = '<BOLD>'
        else:
            colour = '<RED>'
            bold = '<BOLD>'
        msg = '{bold}[{colour}{node.name}<NOCOLOUR>] {message}<RESET>'.format(
            colour=colour, bold=bold, node=self, message=message )
        logger.log(level, msg)

    def __repr__(self):
        return (
            "{node.__class__.__qualname__}(name='{node.name}')"
            .format(node=self) )

class DatedNode(Node):
    """
    DatedNode introduces a notion of modification time.

    Attributes
    ----------
    mtime
        integer, modification time in nanoseconds since epoch.
        Usually returned by some os.stat as st_mtime_ns attribute.
    """

    def __init__(self, *, mtime=None, **kwargs):
        super().__init__(**kwargs)
        self.mtime = mtime

    def update_self(self):
        self.load_mtime()
        super().update_self()

    def needs_build(self):
        """
        Return True if the node needs to be (re)built.

        Extension.
        DatedNode needs build in the following cases:
        1) node.mtime is None (this means that node was never built);
        2) any of prerequisites has mtime newer than node.mtime;
        3) for some other reason (see superclasses).
        """
        mtime = self.mtime
        if mtime is None:
            return True
        for node in self.needs:
            if hasattr(node, 'mtime') and self.mtime_less(mtime, node.mtime):
                return True
        return super().needs_build();

    def load_mtime(self):
        """
        Set node.mtime to appropriate value.

        No-op yet. Subclasses may introduce appropriate behavior.
        """
        pass

    @staticmethod
    def mtime_less(x, y):
        if y is None:
            return False;
        if x is None:
            return True;
        return x < y;

class PathNode(DatedNode):
    """
    PathNode represents filesystem path, existing or not.

    It introduces path attribute and add_subprocess_rule() method.

    Attributes
    ----------
    path
        absolute pathlib.Path object
    """

    root = None

    def __init__(self, path, **kwargs):
        if not isinstance(path, Path):
            path = Path(path)
        if not path.is_absolute():
            raise ValueError(
                "{cls.__qualname__} cannot be initialized "
                "with relative path: '{path}'"
                .format(cls=self.__class__, path=path) )
        if 'name' not in kwargs:
            kwargs['name'] = str(path)
        super().__init__(**kwargs)
        self.path = path

    def load_mtime(self):
        """
        Set node.mtime to appropriate value.

        Set node.mtime to None if path does not exist.
        Otherwise, use st_mtime_ns attribute for the structure
        returned by node.stat().
        """
        try:
            stat = self.stat()
        except FileNotFoundError:
            self.mtime = None
        else:
            self.mtime = stat.st_mtime_ns # nanoseconds

    def stat(self):
        """
        Return appropriate stat structure. Do not follow symlinks.
        """
        return os.stat(str(self.path), follow_symlinks=False)

    def __repr__(self):
        return (
            "{node.__class__.__qualname__}("
            "name='{node.name}', path='{node.relative_path}')"
            .format(node=self) )

    def run_rules(self):
        prerun_mtime = self.mtime
        try:
            super().run_rules()
        except:
            self.load_mtime()
            if self.mtime_less(prerun_mtime, self.mtime):
                # Failed rule resulted in a file written.
                # We have to clear it.
                self.log(ERROR, 'deleting {}'.format(self.relative_path))
                self.path.unlink()
            raise
        self.load_mtime()
        if self.mtime is None:
            # Succeeded rule did not result in a file
            raise NodeMissingPathError(repr(self))
        if prerun_mtime != self.mtime:
            self.modified = True

    def add_subprocess_rule(self, callargs, *, cwd, **kwargs):
        if not isinstance(cwd, Path) or not cwd.is_absolute():
            raise ValueError("cwd must be an absolute Path")
        rule_repr = (
            '<cwd=<BLUE>{cwd}<NOCOLOUR>> <GREEN>{command}<NOCOLOUR>'.format(
                cwd=self.root_relative(cwd),
                command=' '.join(callargs)
            ) )
        @self.add_rule
        def subprocess_rule():
            self.log(INFO, rule_repr)
            try:
                subprocess.check_call(callargs, cwd=str(cwd), **kwargs)
            except subprocess.CalledProcessError as exception:
                self.log(CRITICAL,
                    'Command {exc.cmd} returned code {exc.returncode}'
                    .format(exc=exception) )
                exception.reported = True
                raise

    @property
    def relative_path(self):
        return self.root_relative(self.path)

    @classmethod
    def root_relative(self, path):
        if self.root is None:
            return path
        return self.pure_relative(path, self.root)

    @staticmethod
    def pure_relative(path, root):
        """
        Compute relative PurePath, with '..' parts.

        Both arguments must be absolute PurePath's and lack '..' parts.
        As a special case, if root is None, than path is returned.
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
        return PurePath(*
            ['..'] * upstairs + [path.relative_to(root)] )

class ProductNode(PathNode):
    """
    ProductionNode has a source.

    ProductionNode is a subclass of PathNode that introduces a notion
    of source, which is also a PathNode.

    Attributes
    ----------
    source
        PathNode instance. Exact semantics is defined by subclasses.
    """

    def __init__(self, source, path, *, needs=(), **kwargs):
        if not isinstance(source, PathNode):
            raise TypeError(type(source))
        self.source = source
        needs = chain((source,), needs)
        super().__init__(path, needs=needs, **kwargs)

    def __repr__(self):
        return (
            "{node.__class__.__qualname__}(name='{node.name}', "
                "source={node.source!r}, path='{node.relative_path}')"
            .format(node=self) )

class FileNode(PathNode):
    """
    FileNode represents a file, existing or not (yet).
    """

    def stat(self):
        """
        Return appropriate stat structure. Follow symlinks.
        """
        return os.stat(str(self.path), follow_symlinks=True)

    def open(self, *args, **kwargs):
        return open(str(self.path), *args, **kwargs)

    def run_rules(self):
        # Written in blood
        if self.path.exists() and self.path.is_symlink():
            self.path.unlink()
        super().run_rules()

class TextNode(FileNode):
    """
    Write some generated text to a file.
    """
    def __init__(self, path, text=None, textfunc=None, **kwargs):
        super().__init__(path, **kwargs)
        if text is not None:
            if textfunc is not None:
                raise ValueError(
                    "Exactly one of the 'text' and 'textfunc' arguments "
                    "must be supplied" )
            if not isinstance(text, str):
                raise TypeError(type(text))
            textfunc = lambda: text
        if textfunc is None:
            raise ValueError(
                "Exactly one of the 'text' and 'textfunc' arguments "
                "must be supplied" )

        rule_repr = (
            '<GREEN>Write generated text to {node.relative_path}<NOCOLOUR>'
            .format(node=self) )
        @self.add_rule
        def write_text_rule(textfunc=textfunc):
            self.log(INFO, rule_repr)
            text = textfunc()
            assert isinstance(text, str), text
            with self.open('w') as f:
                f.write(text)

class ProductFileNode(ProductNode, FileNode):
    # Order is everything.
    pass

class LinkNode(ProductNode):
    """
    LinkNode represents a symlink to the file.

    Attributes
    ----------
    source (derived)
        PathNode instance. Represents the target of the link.
    """

    def __init__(self, source, path, *, relative=True, **kwargs):
        super().__init__(source, path, **kwargs)

        if not relative:
            self.source_path = source.path
        else:
            self.source_path = self.pure_relative(
                source.path, self.path.parent )

        rule_repr = (
            '<source=<BLUE>{node.source.name}<NOCOLOUR>> '
            '<GREEN>ln --symbolic {node.source_path} '
                '{node.relative_path}<NOCOLOUR>'
            .format(node=self) )
        @self.add_rule
        def link_rule():
            if os.path.lexists(str(self.path)):
                self.path.unlink()
            self.log(INFO, rule_repr)
            os.symlink(str(self.source_path), str(self.path))
            self.modified = True

    def load_mtime(self):
        """
        Adopt self.mtime and self.modified: if link source is
        modified, then self is also modified; self.mtime should always
        be greater than or equal to source.mtime.
        """
        super().load_mtime()
        mtime = self.mtime
        if mtime is None:
            return
        source = self.source
        source_mtime = source.mtime
        if self.mtime_less(mtime, source_mtime):
            self.mtime = source_mtime
        if source.modified:
            self.modified = True

    def needs_build(self):
        """
        Return True if the node needs to be (re)built.

        Override.
        LinkNode needs build in the following cases:
        1) path does not exist;
        2) path is not a link;
        3) path is a link, but wrong link.
        Superclasses ignored.
        """
        path = str(self.path)
        return not (
            os.path.lexists(path) and
            os.path.islink(path) and
            str(self.source_path) == os.readlink(path) )

class DirectoryNode(PathNode):
    def __init__(self, path, *, parents=False, **kwargs):
        super().__init__(path, **kwargs)
        rule_repr = (
            '<GREEN>{command} {node.relative_path}<NOCOLOUR>'
            .format(node=self,
                command='mkdir --parents' if parents else 'mkdir' ) )
        @self.add_rule
        def mkdir_rule():
            if os.path.lexists(str(path)):
                path.unlink()
            self.log(INFO, rule_repr)
            # rwxr-xr-x
            path.mkdir(mode=0b111101101, parents=parents)
            self.modified = True

    def needs_build(self):
        """
        Return True if the node needs to be (re)built.

        Override.
        DirectoryNode needs build in the following cases:
        1) path does not exist;
        2) path is not a directory.
        Superclasses ignored.
        """
        if self.mtime is None:
            return True
        return False

    def load_mtime(self):
        """
        Set self.mtime to appropriate value.

        Set self.mtime to None if self.path does not exist.
        Otherwise, set self.mtime to 0.

        This method overrides normal behavior. It reflects the fact
        that directories cannot be modified --- they either exist
        (mtime=0) or not (mtime=None). Directory real mtime changes with
        every new file in it --- using it would cause unnecessary
        updates.
        """
        try:
            stat = self.stat()
        except FileNotFoundError:
            self.mtime = None
        else:
            if S_ISDIR(stat.st_mode):
                self.mtime = 0
            else:
                raise NotADirectoryError(
                    "Found something where a directory should be: {}"
                    .format(self.relative_path) )

