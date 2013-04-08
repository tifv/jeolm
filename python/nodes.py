import os
import subprocess
import logging
import warnings

from itertools import chain

from pathlib import Path, PurePath

logger = logging.getLogger(__name__)
rule_logger = logging.getLogger(__name__ + '.rule')

class NodeCycleError(RuntimeError): pass

class Node:
    """
    Node represents target, or source, or anything.

    Attributes
    ----------

    name
        some short-but-identifying name

    updated
        bool, True if self.update() was ever triggered
    modified
        bool, True if self was modified, requiring any
        dependent nodes to be rebuilt
    needs
        list of dependencies
    rules
        list of functions, that are supposed to rebuild self
    _locked
        bool, dependency cycle protection
    """

    def __init__(self, *, name=None, needs=(), rules=()):
        if name is not None:
            self.name = str(name)
        else:
            self.name = 'id{}'.format(id(instance))
        self.needs = list(needs)
        self.rules = list(rules)

        self.updated = False
        self.modified = False

        self._locked = False

    def update(self):
        """
        Update the node, recursively updating prerequisites.
        """
        if self._locked:
            raise NodeCycleError(self.name)
        if self.updated:
            return
        self._update_needs()
        self._update_self()
        self.updated = True

    def _update_needs(self):
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

    def _update_self(self):
        if self.needs_build():
            self.run_rules()

    def needs_build(self):
        """
        Return True if the node needs building (is obsolete, etc.).
        """
        if any(
            node.modified
            for node in self.needs
        ):
            return True
        return False

    def extend_needs(self, needs):
        needs = list(needs)
        for need in needs:
            if not isinstance(need, Node): raise TypeError(need)
        self.needs.extend(needs)
        return self

    def append_needs(self, *needs):
        self.extend_needs(needs)
        return self

    def add_rule(self, rule):
        self.rules.append(rule)
        return rule

    def run_rules(self):
        for rule in self.rules:
            rule()

    def subprocess_rule(self, callargs, *, cwd, **kwargs):
        if not isinstance(cwd, Path) or not cwd.is_absolute():
            raise ValueError("cwd must be an absolute Path")
        rule_repr = '[{node.name}] <cwd={cwd!s}> {command}'.format(
            node=self, cwd=cwd, command=' '.join(callargs) )
        @self.add_rule
        def subprocess_rule():
            self.print_rule(rule_repr)
            try:
                subprocess.check_call(callargs, cwd=str(cwd), **kwargs)
            except subprocess.CalledProcessError as exception:
                rule_logger.critical(
                    "[{node.name}] {exc.cmd} returned code {exc.returncode}"
                    .format(node=self, exc=exception) )
                raise

    @staticmethod
    def print_rule(rule_repr):
        rule_logger.info(rule_repr)

class DatedNode(Node):
    """
    DatedNode has a notion of modification time.

    Attributes
    ----------

    mtime
        integer, usually returned by some os.stat as st_mtime_ns
        (in nanoseconds)

    See superclasses for other attributes.
    """

    def __init__(self, *args, mtime=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.mtime = mtime

    def needs_build(self):
        """
        DatedNode needs build, if
        1) self.mtime == None (this means that self is very old);
        2) some of the needed nodes has mtime newer than self;
        3) for some other reason (see superclasses).
        """
        if self.mtime is None:
            return True
        mtime = self.mtime
        for node in self.needs:
            if hasattr(node, 'mtime') and \
                    node.mtime is not None and \
                    mtime < node.mtime:
                return True
        return super().needs_build()


class PathNode(DatedNode):
    """
    PathNode represents filesystem path, existing or not.

    Attributes
    ----------

    path
        absolute pathlib.Path object

    See superclasses for other attributes
    """

    # This is used for detecting multiple nodes per path
    pathpool = set()

    def __init__(self, path, *args, **kwargs):
        if not isinstance(path, Path):
            path = Path(path)
        if not path.is_absolute(): raise ValueError(path)
        logger.debug("Creating {} for the path '{!s}'"
            .format(self.__class__.__qualname__, path) )
        if path in self.pathpool:
            warnings.warn(
                "Duplicate PathNode('{!s}') object may be created"
                .format(path), stacklevel=2)
        if 'name' not in kwargs:
            kwargs['name'] = str(path)
        self.pathpool.add(path)
        super().__init__(*args, **kwargs)
        self.path = path

    def _update_self(self):
        self.load_mtime()
        super()._update_self()

    def load_mtime(self):
        """
        Set self.mtime to appropriate value.

        Set self.mtime to None if file does not exist.
        """
        try:
            stat = self.stat()
        except FileNotFoundError:
            self.mtime = None
        else:
            self.mtime = stat.st_mtime_ns # nanoseconds

    def stat(self):
        return os.lstat(str(self.path))

    def __repr__(self):
        return "{}('{!s}')".format(
            type(self).__qualname__, self.path )

    def run_rules(self):
        mtime = self.mtime
        try:
            super().run_rules()
        except:
            self.load_mtime()
            if self.mtime is not None and (
                mtime is None or mtime < self.mtime
            ):
                self.path.unlink()
            raise
        self.load_mtime()
        if self.mtime is None:
            raise FileNotFoundError(
                "Path is missing after command execution: '{!s}'"
                .format(self.path) )
        if mtime != self.mtime:
            self.modified = True

class FileNode(PathNode):
    """
    FileNode represents a file, existing or not.
    """

    def stat(self):
        return os.stat(str(self.path))

    def open(self, *args, **kwargs):
        return open(str(self.path), *args, **kwargs)

    def edit_rule(self, editfunc):
        @self.add_rule
        def edit_rule():
            with self.open('r') as f:
                s = f.read()
            s = editfunc(s)
            with self.open('w') as f:
                f.write(s)

    def run_rules(self):
        if self.path.exists() and self.path.is_symlink():
            self.path.unlink()
        super().run_rules()

class LinkNode(PathNode):
    """
    LinkNode represents a symlink to the file.

    Attributes
    ----------

    source
        PathNode instance
    """

    def __init__(self, source, destpath, *, needs=(),
        relative=True, **kwargs
    ):
        if not isinstance(source, PathNode): raise TypeError
        self.source = source
        super().__init__(destpath, needs=chain((source,), needs), **kwargs)

        if not relative:
            self.source_path = source.path
        else:
            self.source_path = self.relative_path(
                self.path.parent(), source.path )

        @self.add_rule
        def link_rule():
            if os.path.lexists(str(self.path)):
                self.path.unlink()
            self.print_rule(
                '[{node.name}] <source={node.source.name}> '
                'ln --symbolic {node.source_path!s} {node.path!s}'
                .format(node=self) )
            os.symlink(str(self.source_path), str(self.path))
            self.modified = True

    def load_mtime(self):
        """
        Adopt self.mtime and self.modified: if link source is
        modified, then self is also modified; self.mtime should always
        be greater than or equal to source.mtime.
        """
        super().load_mtime()
        if self.mtime is None:
            return
        source = self.source
        source.load_mtime()
        source_mtime = source.mtime
        if source_mtime is not None and source_mtime > self.mtime:
            self.mtime = source_mtime
        if source.modified:
            self.modified = True

    def needs_build(self):
        """
        LinkNode needs build if
        1) path does not exist;
        2) path is not a link;
        3) path is a link, but wrong link.
        Superclasses IGNORED.
        """
        path = str(self.path)
        return not (
            os.path.lexists(path) and
            os.path.islink(path) and
            str(self.source_path) == os.readlink(path) )

    @classmethod
    def relative_path(cls, fromdir, absolute):
        """This asserts unexistance of directory symlinks."""
        if not absolute.is_absolute(): raise ValueError(absolute)
        if not fromdir.is_absolute(): raise ValueError(fromdir)
        upstairs = 0
        absolute_parents = set(absolute.parents())
        while fromdir not in absolute_parents:
            fromdir = fromdir.parts[:-1]
            upstairs += 1
        return PurePath(*
            ['..'] * upstairs + [absolute.relative_to(fromdir)] )

class DirectoryNode(PathNode):
    def __init__(self, path, *args, parents=False, **kwargs):
        super().__init__(path, *args, **kwargs)
        rule_repr = '[{node.name}] {command} {node.path}'.format(
            node=self, command='mkdir --parents' if parents else 'mkdir' )
        @self.add_rule
        def mkdir_rule():
            if os.path.lexists(str(path)):
                path.unlink()
            self.print_rule(rule_repr)
            # rwxr-xr-x
            path.mkdir(mode=0b111101101, parents=parents)
            self.modified = True

    def needs_build(self):
        path = str(self.path)
        return not (
            os.path.lexists(path) and
            os.path.isdir(path) )

    def load_mtime(self):
        """
        Set self.mtime to appropriate value.

        Set self.mtime to None if file does not exist.
        """
        try:
            stat = self.stat()
        except FileNotFoundError:
            self.mtime = None
        else:
            self.mtime = 0

