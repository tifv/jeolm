"""
Nodes, and dependency trees constructed of them.
"""

import os
import sys
import re
import subprocess

from itertools import chain

from pathlib import Path, PurePath

from jeolm.utils import pure_relative

import logging
import warnings
logger = logging.getLogger(__name__)
rule_logger = logging.getLogger(__name__ + '.rule')

class NodeCycleError(RuntimeError): pass

class Node:
    """
    Node represents target, or source, or whatever.

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
            return;
        self.update_needs()
        self.update_self()
        self.updated = True

    def update_needs(self):
        try:
            self._locked = True
            for node in self.needs:
                try:
                    node.update()
                except NodeCycleError as exception:
                    exception.args += (self.name,)
                    raise;
        finally:
            self._locked = False

    def update_self(self):
        if self.needs_build():
            self.run_rules()

    def needs_build(self):
        """
        Return True if the node needs building (is obsolete, etc.).
        """
        if any(node.modified for node in self.needs):
            return True;
        return False;

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

    def add_rule(self, rule):
        self.rules.append(rule)
        return rule

    def run_rules(self):
        for rule in self.rules:
            rule()

    def add_subprocess_rule(self, callargs, *, cwd, **kwargs):
        if not isinstance(cwd, Path) or not cwd.is_absolute():
            raise ValueError("cwd must be an absolute Path")
        rule_repr = ('[<BOLD><MAGENTA>{node.name}<RESET>] '
            '<cwd=<BOLD><BLUE>{cwd!s}<RESET>> '
            '<BOLD>{command}<RESET>'
            .format(
                node=self, cwd=pure_relative(Path.cwd(), cwd),
                command=' '.join(callargs) ) )
        @self.add_rule
        def subprocess_rule():
            self.print_rule(rule_repr)
            try:
                subprocess.check_call(callargs, cwd=str(cwd), **kwargs)
            except subprocess.CalledProcessError as exception:
                rule_logger.critical(
                    '<BOLD>[<RED>{node.name}<BLACK>] '
                    '{exc.cmd} returned code {exc.returncode}<RESET>'
                    .format(node=self, exc=exception) )
                raise;

    @staticmethod
    def print_rule(rule_repr):
        rule_logger.info(rule_repr)

class DatedNode(Node):
    """
    DatedNode introduces a notion of modification time.

    Attributes
    ----------
    mtime
        integer, usually returned by some os.stat as st_mtime_ns
        (in nanoseconds)
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
        mtime = self.mtime
        if mtime is None:
            return True;
        for node in self.needs:
            if hasattr(node, 'mtime') and self.less(mtime, node.mtime):
                return True;
        return super().needs_build();

    @staticmethod
    def less(x, y):
        if y is None:
            return False;
        if x is None:
            return True;
        return x < y;

class PathNode(DatedNode):
    """
    PathNode represents filesystem path, existing or not.

    Attributes
    ----------
    path
        absolute pathlib.Path object
    """

    # This is used for detecting multiple nodes per path
    pathpool = set()

    def __init__(self, path, *args, **kwargs):
        if not isinstance(path, Path):
            path = Path(path)
        if not path.is_absolute():
            raise ValueError(path)
#        logger.debug("Creating {} for the path '{!s}'"
#            .format(self.__class__.__qualname__, path) )
        if path in self.pathpool:
            warnings.warn(
                "Duplicate PathNode('{!s}') object may be created"
                .format(path), stacklevel=2)
        if 'name' not in kwargs:
            kwargs['name'] = str(path)
        self.pathpool.add(path)
        super().__init__(*args, **kwargs)
        self.path = path

    def update_self(self):
        self.load_mtime()
        super().update_self()

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
            if self.less(mtime, self.mtime):
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

#    def add_edit_rule(self, editfunc):
#        @self.add_rule
#        def edit_rule():
#            with self.open('r') as f:
#                s = f.read()
#            s = editfunc(s)
#            with self.open('w') as f:
#                f.write(s)

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
        PathNode instance. Represents the target of the link.
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
            self.source_path = pure_relative(
                self.path.parent(), source.path )

        rule_repr = (
            '[<BOLD><MAGENTA>{node.name}<RESET>] '
            '<source=<BOLD><BLUE>{node.source.name}<RESET>> '
            '<BOLD>ln --symbolic {node.source_path!s} {node.path!s}<RESET>'
            .format(node=self) )
        @self.add_rule
        def link_rule():
            if os.path.lexists(str(self.path)):
                self.path.unlink()
            self.print_rule(rule_repr)
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
        source.load_mtime()
        source_mtime = source.mtime
        if self.less(mtime, source_mtime):
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

class DirectoryNode(PathNode):
    def __init__(self, path, *args, parents=False, **kwargs):
        super().__init__(path, *args, **kwargs)
        rule_repr = ('[<BOLD><MAGENTA>{node.name}<RESET>] '
            '<BOLD>{command} {node.path}<RESET>'
            .format(node=self,
                command='mkdir --parents' if parents else 'mkdir' ) )
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
            self.mtime = 0

class LaTeXNode(FileNode):
    """
    Represents a target of some latex command.

    Aims at reasonable handling of latex output to stdin/log.
    Completely suppresses latex output unless finds something
    interesting in it.
    """

    interesting_latexlog_pattern = re.compile(
        '(?m)^! |[Ee]rror|[Ww]arning|No pages of output.'
    )
    latexlog_encoding = 'cp1251' # XXX WTF?

    overfull_latexlog_pattern = re.compile(
        r'(?m)^(Overfull|Underfull)\s+\\hbox\s+\([^()]*?\)\s+'
        r'in\s+paragraph\s+at\s+lines\s+\d+--\d+'
    )
    page_latexlog_pattern = re.compile(r'\[(?P<number>(?:\d|\s)+)\]')

    def add_latex_rule(self, sourcename, *,
        command='latex', cwd,
        logpath=None, **kwargs
    ):
        if not isinstance(cwd, Path) or not cwd.is_absolute():
            raise ValueError("cwd must be an absolute Path")
        kwargs.update(universal_newlines=False)
        rule_repr = ('[<BOLD><MAGENTA>{node.name}<RESET>] '
            '<cwd=<BOLD><BLUE>{cwd!s}<RESET>> '
            '<BOLD>{command} {sourcename}<RESET>'
            .format(
                node=self, cwd=pure_relative(Path.cwd(), cwd),
                command=command, sourcename=sourcename ) )
        callargs = ('latex',
            '-interaction=nonstopmode', '-halt-on-error', '-file-line-error',
            sourcename )
        @self.add_rule
        def latex_rule():
            self.print_rule(rule_repr)
            try:
                output = subprocess.check_output(callargs, cwd=str(cwd),
                    **kwargs )
            except subprocess.CalledProcessError as exception:
                self.print_latex_output(exception.output, force=True)
                rule_logger.critical(
                    '<BOLD>[<RED>{node.name}<BLACK>] '
                    '{exc.cmd} returned code {exc.returncode}<RESET>'
                    .format(node=self, exc=exception) )
                raise
            if not self.print_latex_output(output):
                if logpath is not None:
                    self.print_overfulls(logpath)

    def print_latex_output(self, output, force=False):
        """
        Print output if it is interesting.

        Return False if output was not interesting.
        """
        output = output.decode(self.latexlog_encoding)
        if force or self.interesting_latexlog_pattern.search(output):
            print(output)

    def print_overfulls(self, logpath):
        with logpath.open(encoding=self.latexlog_encoding) as f:
            s = f.read()

        page_marks = {1 : 0}
        last_page = 1; last_mark = 0
        while True:
            for match in self.page_latexlog_pattern.finditer(s):
                value = int(match.group('number').replace('\n', ''))
                if value == last_page + 1:
                    break
            else:
                break
            last_page += 1
            last_mark = match.end()
            page_marks[last_page] = last_mark
        def current_page(pos):
            page = max(
                (
                    (page, mark)
                    for (page, mark) in page_marks.items()
                    if mark <= pos
                ), key=lambda v:v[1])[0]
            if page == 1:
                return '1--2'
            else:
                return page + 1

        for match in self.overfull_latexlog_pattern.finditer(s):
            start = match.start()
            print(
                '[{}]'.format(current_page(match.start())),
                match.group(0) )

