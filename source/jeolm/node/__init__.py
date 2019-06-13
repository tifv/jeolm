"""
Nodes, and dependency trees constructed of them.
"""

# Imports and logging {{{1

from contextlib import contextmanager
from types import coroutine
from shlex import quote

import os
import sys
import time
import traceback
import subprocess

import threading

from pathlib import PurePosixPath, PosixPath

import logging
logger = logging.getLogger(__name__)

import typing
from typing import ( ClassVar, Any, Union, Optional,
    Iterable, Sequence,
    Tuple, List, Set, Dict,
    Coroutine, Generator )
if typing.TYPE_CHECKING:
    import posix


class MissingTargetError(FileNotFoundError): # {{{1
    """Missing target file after execution of build commands."""
    pass


class NodeErrorReported(ValueError): # {{{1
    pass


def _mtime_less(mtime: Optional[int], other: Optional[int]) -> bool: # {{{1
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
            if the node was updated. If True, node will not be rebuilt.
        modified (bool):
            if the node was modified. If True, will cause most dependent
            nodes to be rebuilt. (Although some Node subclasses may
            ignore it.)
    """

    name: str
    needs: List['Node']
    updated: bool
    modified: bool

    def __init__( self,
        *, name: Optional[str] = None, needs: Iterable['Node'] = (),
    ) -> None:
        if name is not None:
            self.name = str(name)
        else:
            self.name = self._default_name()
        self.needs = list()
        for need in needs:
            self._append_needs(need)

        self.updated = False
        self.modified = False

    def _default_name(self) -> str:
        return str(id(self))

    def __hash__(self) -> Any:
        return hash((type(self).__name__, id(self)))

    async def update_self(self) -> None:
        self.updated = True

    def append_needs(self, node: 'Node') -> None:
        """
        Append a node to the needs list.
        """
        self._append_needs(node)

    def extend_needs(self, nodes: Iterable['Node']) -> None:
        """
        Extend needs list with nodes.
        """
        for node in nodes:
            self._append_needs(node)

    def _append_needs(self, node: 'Node') -> None:
        if not isinstance(node, Node):
            raise TypeError(node)
        self.needs.append(node)

    def iter_needs( self,
        *, _seen_nodes: Optional[Set['Node']] = None,
    ) -> Iterable['Node']:
        """
        Yield all needs of this node, recursively, depth-first.

        Yields:
            Node instances: all needs of this node, recursively, including
            this node (first). No repeats (they are skipped).
            Order is depth-first.
            node.needs is not inspected until after the node is yielded.
        """
        if _seen_nodes is None:
            _seen_nodes = set()
        if self in _seen_nodes:
            return
        else:
            _seen_nodes.add(self)
        yield self
        for need in self.needs:
            yield from need.iter_needs(_seen_nodes=_seen_nodes)

    @property
    def logger(self) -> 'Node.LoggerAdapter':
        return self.LoggerAdapter(logger, extra=dict(node=self))

    class LoggerAdapter(logging.LoggerAdapter): # {{{2

        extra: Any

        # override, internal
        def process(self, msg: Any, kwargs: Any) -> Any:
            extra = kwargs.setdefault('extra', {})
            extra.update(self.extra)
            return msg, kwargs

        def log_prog_output( self, level: int, prog: str, output: str,
        ) -> None:
            self.log( level,
                "Command %(prog)s output:",
                dict(prog=prog),
                extra=dict(prog_output=output) )

        def log_prog_error( self, prog: str, returncode: int, output: str,
        ) -> None:
            self.error(
                "Command %(prog)s returned code %(returncode)d, output:",
                dict(prog=prog, returncode=returncode),
                extra=dict(prog_output=output) )

    # }}}2

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r})"


class BuildableNode(Node): # {{{1
    """
    Represents a target that can be built by a command.
    """

    command: Optional['Command']
    _forced: bool = False

    def __init__( self,
        *, name: Optional[str] = None, needs: Iterable[Node] = (),
    ) -> None:
        super().__init__(name=name, needs=needs)
        self.command = None

    # Override
    async def update_self(self) -> None:
        if self._needs_build():
            await self._run_command()
        else:
            self.updated = True

    def _needs_build(self) -> bool:
        if self._forced:
            return True
        return any(need.modified for need in self.needs)

    def force(self) -> None:
        """Make the node unconditionally need to be rebuilt."""
        self._forced = True

    async def _run_command(self) -> None:
        if self.command is None:
            raise ValueError(
                "Node {node} cannot be rebuilt due to the lack of command"
                .format(node=self) )
        await self.command.run()


class Command: # {{{1
    """A base class for commands used with nodes."""

    node: BuildableNode

    def __init__(self, node: BuildableNode) -> None:
        if not isinstance(node, Node):
            raise RuntimeError(type(node))
        self.node = node

    async def run(self) -> None:
        self.node.updated = True

    @property
    def logger(self) -> Node.LoggerAdapter:
        return self.node.logger


class SubprocessCommand(Command): # {{{1
    """A command that will execute some external process."""

    callargs: List[str]
    cwd: PosixPath

    def __init__( self, node: BuildableNode, callargs: Sequence[str],
        *, cwd: PosixPath,
    ) -> None:
        super().__init__(node)
        self.callargs = list(callargs)
        if not isinstance(cwd, PosixPath):
            raise TypeError(
                f"cwd must be a pathlib.PosixPath instance, not {type(cwd)}" )
        if not cwd.is_absolute():
            raise ValueError(
                f"cwd must be an absolute path, got {cwd}" )
        self.cwd = cwd

    # Override
    async def run(self) -> None:
        await self._subprocess()
        self.node.updated = True

    async def _subprocess(self) -> None:
        """
        Run external process.

        Process output is catched and logged (with INFO level).

        Raises:
            subprocess.CalledProcessError:
                in case of error in the called process.
        """

        output = await self._subprocess_output()
        if not output: # child process didn't write anything
            return
        self._log_output(logging.INFO, output)

    @coroutine # type: ignore
    def _subprocess_output(self, log_error_output: bool = True
    ) -> Coroutine['SubprocessCommand', bytes, str]:
        """
        Run external process.

        Process output (the combined stdout and stderr of the spawned
        process, decoded with default encoding and errors='replace')
        is catched and returned (in case on no error).

        Args:
            log_error_output (bool, optional):
                If True (default), in case of process error its output will be
                logged (with ERROR level), and NodeErrorReported exception will
                be raised.
                If False, in case of process error output will not be logged,
                and CalledProcessError exception will be raised.

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
                command=' '.join(quote(arg) for arg in self.callargs), )
        )

        try:
            encoded_output: bytes = (yield self) # event loop doing its thing
        except subprocess.CalledProcessError as exception:
            if not log_error_output:
                raise
            self.logger.log_prog_error(
                exception.cmd[0], exception.returncode,
                exception.output.decode(encoding='utf-8', errors='replace') )
            raise NodeErrorReported from exception
        else:
            return encoded_output.decode(encoding='utf-8', errors='replace')

    def _log_output(self, level: int, output: str) -> None:
        self.logger.log_prog_output( level,
            self.callargs[0], output )


class DatedNode(Node): # {{{1
    """
    Represents something that has a modification time.

    Attributes (additional to superclasses):
        mtime (int): modification time *in nanoseconds* since epoch.
            Usually returned by some os.stat as st_mtime_ns attribute.
    """

    mtime: Optional[int]

    def __init__( self,
        *, name: Optional[str] = None, needs: Iterable[Node] = (),
    ) -> None:
        super().__init__(name=name, needs=needs)
        self.mtime = None

    # Override
    async def update_self(self) -> None:
        self._load_mtime()
        self.updated = True

    def _load_mtime(self) -> None:
        """
        Set self.mtime attribute to appropriate value.
        """
        pass

    def touch(self) -> None:
        """
        Set self.mtime to the current time.
        """
        self.mtime = int(time.time() * (10**9))


class BuildableDatedNode(DatedNode, BuildableNode): # {{{1
    """Represents a target that has a modification time."""

    # Override
    async def update_self(self) -> None:
        self._load_mtime()
        if self._needs_build():
            await self._run_command()
        else:
            self.updated = True

    async def _run_command(self) -> None:
        await super()._run_command()
        self._load_mtime()

    def _needs_build(self) -> bool:
        if self._forced:
            return True
        if any(need.modified for need in self.needs):
            return True
        if self.mtime is None:
            return True
        for need in self.needs:
            if not isinstance(need, DatedNode):
                continue
            if _mtime_less(self.mtime, need.mtime):
                return True
        return False


class PathNode(DatedNode): # {{{1
    """
    Represents a filesystem object.

    Attributes (additional to superclasses):
        path (pathlib.PosixPath):
            absolute path, represented by the node.

    Class attributes:
        root (pathlib.PosixPath or None):
            absolute path, relative to which various paths will appear in
            log messages.
    """

    root: ClassVar[Optional[PosixPath]] = None
    path: PosixPath

    def __init__( self, path: PosixPath,
        *, name: Optional[str] = None, needs: Iterable[Node] = ()
    ) -> None:
        if not isinstance(path, PosixPath):
            raise TypeError(type(path))
        if not path.is_absolute():
            raise ValueError(
                f"{self.__class__.__name__} cannot be initialized "
                f"with relative path: {path!r}" )
        if name is None:
            name = str(path)
        super().__init__(name=name, needs=needs)
        self.path = path

    def _load_mtime(self) -> None:
        """
        Set self.mtime attribute to the self.path's mtime.
        """
        try:
            stat = self.stat()
        except FileNotFoundError:
            self.mtime = None
        else:
            self.mtime = stat.st_mtime_ns # nanoseconds

    def touch(self) -> None:
        """
        Set self.mtime and actual self.path mtime to the current time.
        """
        # Override, making use of os.utime default behavior.
        os.utime(str(self.path))
        self._load_mtime()

    def stat(self, follow_symlinks: bool = False) -> 'posix.stat_result':
        """
        Return stat structure of self.path.
        """
        return os.stat(str(self.path), follow_symlinks=follow_symlinks)

    def __repr__(self) -> str:
        return ( f"{self.__class__.__name__}(name={self.name!r}, "
            f"path={self.relative_path!r})" )

    @property
    def relative_path(self) -> PurePosixPath:
        return self.root_relative(self.path)

    @classmethod
    def root_relative(cls, path: PosixPath) -> PurePosixPath:
        if cls.root is None:
            return path
        return path.relative_to(cls.root)


class BuildablePathNode(PathNode, BuildableDatedNode): # {{{1
    """Represents a filesystem object that can be (re)built."""

    async def _run_command(self) -> None:
        prerun_mtime = self.mtime
        await super()._run_command()
        if _mtime_less(prerun_mtime, self.mtime):
            self.modified = True
        else:
            self.logger.error( "Path %(path)s was not updated",
                dict(path=self.relative_path) )
            raise MissingTargetError(self)


class ProductNode(BuildablePathNode): # {{{1
    """
    Represents a filesystem target that has a source.

    ProductNode is a subclass of PathNode that introduces a notion of
    source, which is also a PathNode.

    Attributes (additional to superclasses):
        source (PathNode):
            prominent prerequisite, whatever it means.
            Exact semantics may be defined by subclasses.
    """

    source: PathNode

    def __init__( self, source: PathNode, path: PosixPath,
        *, name: Optional[str] = None, needs: Iterable[Node] = ()
    ) -> None:
        if not isinstance(source, PathNode):
            raise TypeError(type(source))
        self.source = source
        super().__init__( path=path, name=name,
            needs=(source, *needs) )

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(name={self.name!r}, "
            f"path={self.relative_path!r}, source={self.source!r})" )


class FollowingPathNode(PathNode): # {{{1
    """Represents a path that can be or not be a symbolic link."""

    # Override
    def stat(self, follow_symlinks: bool = True) -> 'posix.stat_result':
        """
        Return appropriate stat structure.

        By default, do follow symlinks.
        """
        return super().stat(follow_symlinks=follow_symlinks)


class FilelikeNode(PathNode): # {{{1
    """Represents path which can be opened as file."""
    pass


class SourceFileNode(FollowingPathNode, FilelikeNode): # {{{1
    """Represents a source file."""

    # Override
    async def update_self(self) -> None:
        self._load_mtime()
        if self.mtime is None:
            self.logger.error( "Source file %(path)s is missing",
                dict(path=self.relative_path) )
            raise NodeErrorReported from MissingTargetError(self.path)
        self.updated = True


class FileNode(BuildablePathNode, FilelikeNode): # {{{1
    """Represents a file target."""

    async def _run_command(self) -> None:
        # Avoid writing to remnant symlink.
        if self.path.is_symlink():
            self.path.unlink()
            self._load_mtime()
        prerun_mtime = self.mtime
        try:
            await super()._run_command()
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
