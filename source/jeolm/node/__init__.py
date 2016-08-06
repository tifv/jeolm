"""
Nodes, and dependency trees constructed of them.
"""

from itertools import chain
from contextlib import contextmanager

import os
import sys
import time
import traceback
import subprocess

import threading

from pathlib import Path

import logging
logger = logging.getLogger(__name__)


class MissingTargetError(FileNotFoundError): # {{{1
    """Missing target file after execution of build commands."""
    pass

class NodeErrorReported(ValueError): # {{{1
    pass


class NodeUpdater: # {{{1

    def __init__(self):
        self.needs_map = dict()
        self.revneeds_map = dict()
        self.ready_nodes = set()
        super().__init__()

    def clear(self):
        """Must be called before reusing the updater."""
        self.needs_map.clear()
        self.revneeds_map.clear()
        self.ready_nodes.clear()

    def update(self, node):
        if node.updated:
            return
        self._add_node(node)
        self._update_added_nodes()

    def _add_node(self, node, *, _rev_need=None):
        assert not node.updated
        try:
            rev_needs = self.revneeds_map[node]
        except KeyError:
            already_added = False
            rev_needs = self.revneeds_map[node] = set()
        else:
            already_added = True
        if _rev_need is not None:
            rev_needs.add(_rev_need)
        if already_added:
            return
        else:
            self._readd_node(node)

    def _readd_node(self, node):
        assert node not in self.needs_map
        assert node not in self.ready_nodes
        needs = self.needs_map[node] = set()
        for need in node.needs:
            if need.updated:
                continue
            self._add_node(need, _rev_need=node)
            needs.add(need)
        if not needs:
            self.ready_nodes.add(node)

    def _update_added_nodes(self):
        while self.ready_nodes:
            node = self._pop_ready_node()
            self._update_node_self(node)
            self._update_node_finish(node)
        self._check_finished_update()

    def _pop_ready_node(self):
        node = self.ready_nodes.pop()
        if self.needs_map.pop(node):
            raise RuntimeError
        return node

    def _update_node_finish(self, node):
        if node.updated:
            self._revneeds_pop(node)
        else:
            self._readd_node(node)

    def _revneeds_pop(self, node):
        for revneed in self.revneeds_map.pop(node):
            revneed_needs = self.needs_map[revneed]
            assert node in revneed_needs
            revneed_needs.discard(node)
            if not revneed_needs:
                self.ready_nodes.add(revneed)

    @staticmethod
    def _update_node_self(node):
        try:
            assert not node.updated
            assert all(need.updated for need in node.needs)
            node.update_self()
        except NodeErrorReported:
            raise
        except Exception as exception:
            node.logger.exception("Exception occured:")
            raise NodeErrorReported from exception

    def _check_finished_update(self):
        if self.needs_map:
            raise RuntimeError( "Node dependencies formed a cycle:\n{}"
                .format('\n'.join(
                    repr(node) for node in self._find_needs_cycle()
                )) )
        if self.revneeds_map:
            raise RuntimeError

    def _find_needs_cycle(self):
        seen_nodes_map = dict()
        seen_nodes_list = list()
        assert self.needs_map
        node = next(iter(self.needs_map)) # arbitrary node
        while True:
            if node in seen_nodes_map:
                return seen_nodes_list[seen_nodes_map[node]:]
            seen_nodes_map[node] = len(seen_nodes_list)
            seen_nodes_list.append(node)
            assert self.needs_map[node]
            node = next(iter(self.needs_map[node]))


def _mtime_less(mtime, other): # {{{1
    if other is None:
        return False
    if mtime is None:
        return True
    return mtime < other


class Node: # {{{1
    """
    Represents a target, or a source, or something.

    Attributes:
        name (str):
            some identifying name.
            Should show up only in log messages.
        needs (list of Node):
            prerequisites of this node.
            Should not be populated directly.
        updated (bool):
            if the node was updated. If True, node will never be rebuilt.
            When True, must never revert to False.
        modified (bool):
            if the node was modified. If True, will cause most dependent
            nodes to be rebuilt. (Although some Node subclasses may
            ignore it.)
    """

    def __init__(self, *, name=None, needs=()):
        """
        Initialize Node instance.

        Args:
            name (str, optional):
                assigned to the node.name attribute.
            needs (iterable of Node, optional):
                iterated over, forming node.needs attribute.
        """
        if name is not None:
            self.name = str(name)
        else:
            self.name = self._default_name()
        self.needs = list(needs)

        self.updated = False
        self.modified = False

    def _default_name(self):
        return str(id(self))

    def __hash__(self):
        return hash((type(self).__name__, id(self)))

    # Should be only called by NodeUpdater
    def update_self(self):
        self.updated = True

    def append_needs(self, node):
        """
        Append a node to the needs list.

        Args:
            node (Node): a node to be appended to needs.

        Returns None.
        """
        self._append_needs(node)

    def extend_needs(self, nodes):
        """
        Extend needs list with nodes.

        Args:
            nodes (iterable of Node): a nodes to be appended to needs.

        Returns None.
        """
        for node in nodes:
            self._append_needs(node)

    def _append_needs(self, node):
        if not isinstance(node, Node):
            raise TypeError(node)
        self.needs.append(node)

    def iter_needs(self, _seen_nodes=None, _reversed=False):
        """
        Yield all needs of this node, recursively.

        Yields:
            Node instances: all needs of this node, recursively, including
            this node (first). No repeats (they are skipped).
            Every node is guaranteed to come before all of its prerequisites,
            given that nodes do not form a cycle.
        """
        if not _reversed:
            if _seen_nodes is not None:
                raise RuntimeError
            yield from reversed(list(self.iter_needs(_reversed=True)))
            return
        if _seen_nodes is None:
            _seen_nodes = {self}
        elif self in _seen_nodes:
            return
        else:
            _seen_nodes.add(self)
        for need in reversed(self.needs):
            yield from need.iter_needs(
                _seen_nodes=_seen_nodes, _reversed=True )
        yield self

    @property
    def logger(self):
        return self._LoggerAdapter(logger, node=self)

    class _LoggerAdapter(logging.LoggerAdapter): # {{{2

        # pylint: disable=redefined-outer-name

        def __init__(self, logger, node):
            super().__init__(logger, extra=dict(node=node))

        # pylint: enable=redefined-outer-name

        def process(self, msg, kwargs):
            extra = kwargs.setdefault('extra', {})
            extra.update(self.extra)
            return msg, kwargs

        def log_prog_output(self, level, prog, output):
            self.log( level,
                "Command %(prog)s output:",
                dict(prog=prog),
                extra=dict(prog_output=output)
            )
    # }}}2

    def __repr__(self):
        return (
            "{node.__class__.__name__}(name='{node.name}')"
            .format(node=self) )


class BuildableNode(Node): # {{{1
    """
    Represents a target that can be built by a command.

    Attributes (additional to superclasses):
        command (callable):
            command that is responsible for (re)building the node and
            setting node.modified attribute as appropriate.
            Should not be set directly.
    """

    def __init__(self, *, name=None, needs=(), **kwargs):
        """
        Initialize BuildableNode instance.

        Args:
            name, needs (optional)
                passed to the superclass.
        """
        super().__init__(name=name, needs=needs, **kwargs)
        self.command = None

    # Partial override
    def update_self(self):
        if self._needs_build():
            self._run_command()
        else:
            super().update_self()
            self.command.clear()

    @property
    def wants_concurrency(self):
        try:
            return self.command.wants_concurrency
        except AttributeError:
            return False

    def _needs_build(self):
        """
        If the node needs to be (re)built.

        Node needs to be rebuilt in the following case:
          - any of needed nodes are modified.
        Subclasses may introduce different conditions.

        Returns:
            bool: True if the node needs to be rebuilt, False otherwise.
        """
        if any(node.modified for node in self.needs):
            return True
        return False

    def force(self):
        """Make the node unconditionally need to be rebuilt."""
        force_node = Node(name='{}:force'.format(self.name))
        self.needs.insert(0, force_node)
        force_node.updated = True
        force_node.modified = True

    def set_command(self, command):
        """
        Set the argement as node.command attribute.

        Args:
            command (Command):
                a command to be assigned to the node.command attribute.
        """
        if not isinstance(command, Command):
            raise RuntimeError
        self.command = command

    def set_subprocess_command(self, callargs, *, cwd, **kwargs):
        return self.set_command(SubprocessCommand( self,
            callargs, cwd=cwd, **kwargs ))

    def _run_command(self):
        # Should be only called by self.update_self()
        if self.command is None:
            raise ValueError(
                "Node {node} cannot be rebuilt due to the lack of command"
                .format(node=self) )
        self.command.call()


class Command: # {{{1
    """A base class for commands used with nodes."""

    def __init__(self, node):
        if not isinstance(node, Node):
            raise RuntimeError(type(node))
        self.node = node

    wants_concurrency = False

    def call(self):
        self.node.updated = True
        self.clear()

    def clear(self):
        del self.node # break reference cycle

    @property
    def logger(self):
        return self.node.logger


class SubprocessCommand(Command): # {{{1
    """A command that will execute some external process."""

    def __init__(self, node, callargs, *, cwd, **kwargs):
        super().__init__(node)
        self.callargs = callargs
        if not isinstance(cwd, Path):
            raise ValueError(
                "cwd must be a pathlib.Path instance, not {cwd_type}"
                .format(cwd_type=type(cwd)) )
        if not cwd.is_absolute():
            raise ValueError("cwd must be an absolute path")
        self.cwd = cwd
        kwargs.setdefault('stderr', subprocess.STDOUT)
        self.kwargs = kwargs

    wants_concurrency = True

    def call(self):
        self._subprocess()
        super().call()

    def _subprocess(self):
        """
        Run external process.

        Process output (see _subprocess_output() method documentation)
        is catched and logged (with INFO level).

        Returns None.

        Raises:
            subprocess.CalledProcessError:
                in case of error in the called process.
        """

        output = self._subprocess_output()
        if not output: # child process didn't write anything
            return
        self._log_output(logging.INFO, output)

    def _subprocess_output(self, log_error_output=True):
        """
        Run external process.

        Process output (the combined stdout and stderr of the spawned
        process, decoded with default encoding and errors='replace')
        is catched and done something with, depending on args.

        Args:
            log_error_output (bool, optional):
                If True (default), in case of process error its output will be
                logged (with ERROR level). If False, it will not be logged.
                Defaults to True. In any case, any received
                subprocess.CalledProcessError exception is reraised.

        Returns:
            Process output (str).

        Raises:
            subprocess.CalledProcessError:
                in case of error in the called process.
        """

        if isinstance(self.node, PathNode):
            root_relative = self.node.root_relative
        else:
            root_relative = PathNode.root_relative

        self.logger.info(
            "<cwd=<CYAN><ITALIC>%(cwd)s<UPRIGHT><NOCOLOUR>> "
            "<GREEN><ITALIC>%(command)s<UPRIGHT><NOCOLOUR>",
            dict(
                cwd=root_relative(self.cwd),
                command=' '.join(self.callargs), )
        )

        try:
            encoded_output = subprocess.check_output(
                self.callargs, cwd=str(self.cwd), **self.kwargs )
        except subprocess.CalledProcessError as exception:
            if not log_error_output:
                raise
            self.logger.error(
                "Command %(prog)s returned code %(returncode)d, output:",
                dict(
                    prog=exception.cmd[0],
                    returncode=exception.returncode, ),
                extra=dict(
                    prog_output=exception.output.decode(errors='replace'), )
            )
            raise NodeErrorReported from exception
        else:
            return encoded_output.decode(encoding='utf-8', errors='replace')

    def _log_output(self, level, output):
        self.logger.log_prog_output( level,
            self.callargs[0], output )


class DatedNode(Node): # {{{1
    """
    Represents something that has a modification time.

    Attributes (additional to superclasses):
        mtime (int): modification time *in nanoseconds* since epoch.
            Usually returned by some os.stat as st_mtime_ns attribute.
    """

    def __init__(self, name=None, needs=(), **kwargs):
        """
        Initialize DatedNode instance.

        Args:
            name, needs (optional)
                passed to the superclass.
        """
        super().__init__(name=name, needs=needs, **kwargs)
        self.mtime = None

    def update_self(self):
        self._load_mtime()
        super().update_self()

    def _load_mtime(self):
        """
        Set node.mtime attribute to appropriate value.

        No-op here. Subclasses may introduce appropriate behavior.
        """
        pass

    def touch(self):
        """Set node.mtime to the current time."""
        self.mtime = int(time.time() * (10**9))


# BuildableNode overrides update_self(), while DatedNode extends it.
# So, the order of superclasses is important.
class BuildableDatedNode(DatedNode, BuildableNode): # {{{1
    """Represents a target that has a modification time."""

    def _needs_build(self):
        """
        If the node needs to be (re)built.

        Extension.
        DatedNode needs to be rebuilt in the following cases:
          - node.mtime is None (this means that node was never built);
          - any of prerequisites has mtime newer than node.mtime;
        or for some other reason (see superclasses).

        Returns:
            bool: True if the node needs to be rebuilt, False otherwise.
        """
        if super()._needs_build():
            return True
        mtime = self.mtime
        if mtime is None:
            return True
        for need in self.needs:
            if not isinstance(need, DatedNode):
                continue
            if need.mtime is None:
                raise RuntimeError
            if _mtime_less(mtime, need.mtime):
                return True
        return False


class PathNode(DatedNode): # {{{1
    """
    Represents a filesystem object.

    Attributes (additional to superclasses):
        path (pathlib.Path):
            absolute path, represented by the node.

    Class attributes:
        root (pathlib.Path or None):
            absolute path, relative to which various paths will appear in
            log messages.
    """

    root = None

    def __init__(self, path, *, name=None, needs=(), **kwargs):
        """
        Initialize PathNode instance.

        Args:
            path (pathlib.Path):
                absolute path, assigned to the node.path attribute.
            name, needs (optional):
                passed to the superclass.
                The default for name is str(path).
        """
        if not isinstance(path, Path):
            raise TypeError(type(path))
        if not path.is_absolute():
            raise ValueError(
                "{cls.__name__} cannot be initialized "
                "with relative path: '{path}'"
                .format(cls=self.__class__, path=path) )
        if name is None:
            name = str(path)
        super().__init__(name=name, needs=needs, **kwargs)
        self.path = path

    def _load_mtime(self):
        """
        Set node.mtime attribute to appropriate value.

        Set node.mtime to None if node.path does not exist as filesystem path.
        Otherwise, use st_mtime_ns attribute from the structure returned by
        node.stat().
        """
        try:
            stat = self.stat()
        except FileNotFoundError:
            self.mtime = None
        else:
            self.mtime = stat.st_mtime_ns # nanoseconds

    def touch(self):
        """
        Set node.mtime and actual node.path mtime to the current time.
        """
        # Override, making use of os.utime default behavior.
        os.utime(str(self.path))
        self._load_mtime()

    def stat(self, follow_symlinks=False):
        """
        Return appropriate stat structure.

        By default, do not follow symlinks.
        """
        return os.stat(str(self.path), follow_symlinks=follow_symlinks)

    def __repr__(self):
        return ( "{node.__class__.__name__}(name='{node.name}', "
            "path='{node.relative_path}')"
            .format(node=self) )

    @property
    def relative_path(self):
        return self.root_relative(self.path)

    @classmethod
    def root_relative(cls, path):
        if cls.root is None:
            return path
        return path.relative_to(cls.root)


class BuildablePathNode(PathNode, BuildableDatedNode): # {{{1
    """Represents a filesystem object that can be (re)built."""

    def _run_command(self):
        prerun_mtime = self.mtime
        super()._run_command()
        self._load_mtime()
        if self.mtime is None:
            # Succeeded command did not result in a file
            raise MissingTargetError(self)
        if _mtime_less(prerun_mtime, self.mtime):
            self.modified = True


class ProductNode(BuildablePathNode): # {{{1
    """
    Represents a filesystem target that has a source.

    ProductNode is a subclass of PathNode that introduces a notion of
    source, which is also a PathNode.

    Attributes (additional to superclasses):
        source (PathNode):
            prominent prerequisite, whatever it means.
            Exact semantics is defined by subclasses.
    """

    def __init__(self, source, path, *, name=None, needs=(), **kwargs):
        """
        Initialize ProductNode instance.

        Args:
            source (PathNode):
                assigned to the node.source attribute.
                Prepended to needs.
            path (pathlib.Path):
                passed to the superclass.
            name, needs (optional)
                passed to the superclass.
        """
        if not isinstance(source, PathNode):
            raise TypeError(type(source))
        self.source = source
        needs = chain((source,), needs)
        super().__init__(path=path, name=name, needs=needs, **kwargs)

    def __repr__(self):
        return ( "{node.__class__.__name__}(name='{node.name}', "
            "path='{node.relative_path}', source={node.source!r})"
            .format(node=self) )


class FollowingPathNode(PathNode): # {{{1
    """Represents a path that can be or not be a symbolic link."""

    # Override
    def stat(self, follow_symlinks=True):
        """
        Return appropriate stat structure.

        By default, do follow symlinks.
        """
        return super().stat(follow_symlinks=follow_symlinks)


class FilelikeNode(PathNode): # {{{1
    """Represents path which can be opened as file."""

    def open(self, mode='r', *, encoding='utf-8', **kwargs):
        """Open a file-like node.path (try, at least)."""
        return open( str(self.path),
            mode=mode, encoding=encoding, **kwargs )


class SourceFileNode(FollowingPathNode, FilelikeNode): # {{{1
    """Represents a source file."""

    def update_self(self):
        super().update_self()
        if self.mtime is None:
            self.logger.error( "Source file %(path)s is missing",
                dict(path=self.relative_path) )
            raise NodeErrorReported from MissingTargetError(self.path)


class FileNode(BuildablePathNode, FilelikeNode): # {{{1
    """Represents a file target."""

    def _run_command(self):
        # Avoid writing to remnant symlink.
        if self.path.is_symlink():
            self.path.unlink()
            self._load_mtime()
        prerun_mtime = self.mtime
        try:
            super()._run_command()
        except MissingTargetError:
            raise
        except:
            self._load_mtime()
            if _mtime_less(prerun_mtime, self.mtime):
                # Failed command resulted in a file written.
                # We have to clear it.
                self.logger.error( "Deleting %(path)s",
                    dict(path=self.relative_path) )
                self.path.unlink()
            raise


class ProductFileNode(ProductNode, FileNode): # {{{1
    """Represents a file target that has a source."""
    pass

# }}}1
# vim: set foldmethod=marker :
