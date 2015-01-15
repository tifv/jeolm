"""
Nodes, and dependency trees constructed of them.
"""

from itertools import chain

import os
from stat import S_ISDIR
import subprocess
import time
from contextlib import contextmanager

import threading

from pathlib import Path, PurePosixPath

import logging
logger = logging.getLogger(__name__) # pylint: disable=invalid-name


class CycleError(RuntimeError):
    pass

class MissingTargetError(FileNotFoundError):
    """Missing target file after execution of build commands."""
    pass


class CatchingThread(threading.Thread):
    def __init__(self, *, target=None):
        super().__init__(target=target)
        assert not hasattr(self, 'exception')
        self.exception = None

    def run(self):
        """
        Extension.

        Catch and save any exception occured (normal exception, i. e.
        Exception instance).
        """
        try:
            return super().run()
        except Exception as exception: # pylint: disable=broad-except
            self.exception = exception

    def join(self, timeout=None):
        """
        Extension.

        Raise any exception catched by run().
        """
        super().join(timeout=timeout)
        if self.exception is not None:
            raise self.exception # pylint: disable=raising-bad-type


def mtime_less(mtime, other):
    if other is None:
        return False
    if mtime is None:
        return True
    return mtime < other


def pure_relative(path, root):
    """
    Compute relative PurePosixPath, with '..' parts.

    Both arguments must be absolute PurePosixPath's and lack '..' parts.
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



class Node:
    """
    Represents target, or source, or whatever.

    Attributes:
        name (str):
            some identifying name.
            Should show up only in log messages.
        needs (list of Node):
            prerequisites of this node.
            Should not be populated directly.
        modified (bool):
            if the node was modified. If equal to True, will cause any
            dependent nodes to be rebuilt.
        thread (CatchingThread or None):
            if not None, thread responsible for updating the node.
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
            self.name = str(id(self))
        self.needs = list(needs)

        self.modified = False

        # _updated (bool): if the node was updated, i.e. if node.update or
        # node.update_start method has ever completed.
        self._updated = False
        # _locked (bool): dependency cycle protection.
        self._locked = False

        self.thread = None

    def __hash__(self):
        return hash(id(self))

    def update(self, *, semaphore=None):
        """
        Update the node, first recursively updating needs.

        Args:
            semaphore (threading.BoundedSemaphore or None, optional):
                if not None, the node.update_start method will be called
                prior to normal update process, allowing concurrent execution.
                Default is None.

        Returns None.
        """

        if semaphore is not None:
            self.update_start(semaphore=semaphore)
        with self._check_for_cycle():
            if self._updated:
                if self.thread is not None:
                    assert isinstance(self.thread, CatchingThread)
                    self.thread.join()
                return
            for need in self.needs:
                need.update()
            self._update_self()
            self._updated = True
            return

    def update_start(self, *, semaphore):
        """
        Create a thread that will update the node.

        Creates a thread that will update the node after waiting for
        prerequisites (all the required thread are also created).
        Stores thread object in self.thread.

        The number of concurrently running build commands is limited by
        provided semaphore.

        Args:
            semaphore (threading.BoundedSemaphore):
                semaphore that limits concurrent execution of build commands.

        Returns None.

        Finalization of update process should be ensured by subsequent call
        to node.update method.
        """

        if not isinstance(semaphore, threading.BoundedSemaphore):
            raise TypeError(type(semaphore))

        with self._check_for_cycle():
            if self._updated:
                return
            for need in self.needs:
                need.update_start(semaphore=semaphore)
            def wait_and_update():
                for need in self.needs:
                    subthread = need.thread
                    if subthread is None:
                        continue
                    assert isinstance(subthread, CatchingThread)
                    subthread.join()
                with semaphore:
                    self._update_self()
            thread = self.thread = CatchingThread(target=wait_and_update)
            thread.start()
            self._updated = True

    @contextmanager
    def _check_for_cycle(self):
        if self._locked:
            raise CycleError(self.name)
        self._locked = True
        try:
            yield
        except CycleError as exception:
            exception.args += (self.name,)
            raise
        finally:
            self._locked = False

    # Should be only called by node.update method or by thread created by
    # node.update_start method.
    def _update_self(self):
        pass

    # This will only get used by BuildableNode and subclasses.
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
        if self._updated:
            raise RuntimeError
        if not isinstance(node, Node):
            raise TypeError(node)
        self.needs.append(node)

    def iter_needs(self, _seen_nodes=None, _reversed=False):
        """
        Yield all needs of this node, recursively.

        Yields:
            Node instances: all needs of this node, recursively, including
            this node (first). No repeats (they are skipped).
            Every node is guaranteed to come before all of its prerequisites.
        """
        if not _reversed:
            yield from reversed(list(self.iter_needs(
                _seen_nodes=_seen_nodes, _reversed=True )))
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

    def log(self, level, message):
        """
        Log a message specific for this node.

        Prepend a message with node.name and delegate to module logger.
        This function expects FancifyingFormatter to be used somewhere
        in logging facility.
        """
        if level <= logging.INFO:
            bold, reset = '', ''
        else:
            bold, reset = '<BOLD>', '<RESET>'
        msg = '{bold}[{name}] {message}{reset}'.format(
            bold=bold, reset=reset,
            name=self.fancified_repr(level), message=message )
        logger.log(level, msg)

    def __repr__(self):
        return (
            "{node.__class__.__name__}(name='{node.name}')"
            .format(node=self) )

    def fancified_repr(self, level):
        if level <= logging.DEBUG:
            colour = '<CYAN>'
        elif level <= logging.INFO:
            colour = '<MAGENTA>'
        elif level <= logging.WARNING:
            colour = '<YELLOW>'
        else:
            colour = '<RED>'
        return '{colour}{name}<NOCOLOUR>'.format(colour=colour, name=self.name)


class BuildableNode(Node):
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

    def _update_self(self):
        super()._update_self()
        if self._needs_build():
            self._run_command()

    def force(self):
        """
        Make the node unconditionally need to be rebuilt.
        """
        force_node = Node(name='{}:force'.format(self.name))
        self.needs.insert(0, force_node)
        force_node.update()
        force_node.modified = True

    def set_command(self, command):
        """
        Set the argement as node.command attribute.

        May be used as decorator.

        Args:
            command (callable):
                a command to be assigned to the node.command attribute.

        Returns:
            command (the same object).
        """
        self.command = command
        return command

    def set_subprocess_command(self, callargs, *, cwd, **kwargs):
        return self.set_command(SubprocessCommand( self,
            callargs, cwd=cwd, **kwargs ))

    def _run_command(self):
        # Should be only called by self._update_self()
        if self.command is None:
            raise ValueError(
                "Node {node} cannot be rebuilt due to the lack of command"
                .format(node=self) )
        self.command()


class Command:
    """Convenience class for commands used with nodes."""

    def __init__(self, node):
        assert isinstance(node, Node), type(node)
        self.node = node

    def __call__(self):
        pass

    def log(self, level, message):
        return self.node.log(level, message)


class SubprocessCommand(Command):

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

    def __call__(self):
        super().__call__()
        self._subprocess()

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
        if not output:
            return
        self._log_output(output)

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

        self.log(logging.INFO, (
            '<cwd=<CYAN>{cwd}<NOCOLOUR>> <GREEN>{command}<NOCOLOUR>'
            .format(
                cwd=root_relative(self.cwd),
                command=' '.join(self.callargs), )
        ))

        try:
            encoded_output = subprocess.check_output(
                self.callargs, cwd=str(self.cwd), **self.kwargs )
        except subprocess.CalledProcessError as exception:
            if not log_error_output:
                raise
            output = exception.output.decode(errors='replace')
            self.log(logging.ERROR,
                "<BOLD>Command {exc.cmd[0]} returned code {exc.returncode}, "
                    "output:<RESET>\n{output}"
                "<BOLD>(error output while building "
                    "<RED>{node.name}<NOCOLOUR>)<RESET>"
                .format(node=self.node, exc=exception, output=output)
            )
            # Stop jeolm.commands.refrain_called_process_error
            # (which most probably surrounds us) from reporting the error.
            exception.reported = True
            raise
        else:
            return encoded_output.decode(errors='replace')

    def _log_output(self, output, level=logging.INFO):
        self.log( level,
            "Command {prog} output:<RESET>\n{output}"
            "{bold}(output while building {node_name})"
            .format(
                node_name=self.node.fancified_repr(level),
                prog=self.callargs[0], output=output,
                bold='<BOLD>' if level >= logging.WARNING else '')
        )


class DatedNode(Node):
    """
    Introduces a notion of modification time.

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

    def _update_self(self):
        self._load_mtime()
        super()._update_self()

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
        mtime = self.mtime
        if mtime is None:
            return True
        if super()._needs_build():
            return True
        for node in self.needs:
            if not isinstance(node, DatedNode):
                continue
            if mtime_less(mtime, node.mtime):
                return True

    def _load_mtime(self):
        """
        Set node.mtime attribute to appropriate value.

        No-op here. Subclasses may introduce appropriate behavior.
        """
        pass

    def touch(self):
        """Set node.mtime to the current time."""
        self.mtime = int(time.time() * (10**9))


class PathNode(DatedNode):
    """
    Represents filesystem path.

    Attributes (additional to superclasses):
        path (pathlib.Path):
            absolute path, represented by the node.

    Class attributes:
        root (pathlib.Path or None):
            absolute path, relative to which various paths will appear in
            log messages.
            (For that, PathNode.root_relative class method should be used.)
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

    def stat(self):
        """
        Return appropriate stat structure. Do not follow symlinks.
        """
        return os.stat(str(self.path), follow_symlinks=False)

    def __repr__(self):
        return (
            "{node.__class__.__name__}("
            "name='{node.name}', path='{node.relative_path}')"
            .format(node=self) )

    @property
    def relative_path(self):
        return self.root_relative(self.path)

    @classmethod
    def root_relative(cls, path):
        if cls.root is None:
            return path
        return path.relative_to(cls.root)


class BuildablePathNode(PathNode, BuildableNode):

    def _run_command(self):
        prerun_mtime = self.mtime
        super()._run_command()
        self._load_mtime()
        if self.mtime is None:
            # Succeeded command did not result in a file
            raise MissingTargetError(repr(self))
        if mtime_less(prerun_mtime, self.mtime):
            self.modified = True


class ProductNode(BuildablePathNode):
    """
    Represents a node with a source.

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
        return (
            "{node.__class__.__name__}(name='{node.name}', "
                "source={node.source!r}, path='{node.relative_path}')"
            .format(node=self) )


class FollowingPathNode(PathNode):
    """Represent a path that can be or not be a symbolic link."""

    # Override
    def stat(self):
        """
        Return appropriate stat structure. Follow symlinks.
        """
        return os.stat(str(self.path), follow_symlinks=True)


class FilelikeNode(PathNode):
    """Represents path which can be opened as file."""

    def open(self, mode='r', *args, **kwargs):
        """Open a file-like node.path (try, at least)."""
        return open(str(self.path), *args, mode=mode, **kwargs)


class SourceFileNode(FollowingPathNode, FilelikeNode):
    """Represents a source file."""

    pass

class FileNode(BuildablePathNode, FilelikeNode):
    """
    Represents a file that can be recreated by a build command.
    """

    def _run_command(self):
        # Avoid writing to remnant symlink.
        if self.path.exists() and self.path.is_symlink():
            self.path.unlink()
            self._load_mtime()
        prerun_mtime = self.mtime
        try:
            super()._run_command()
        except MissingTargetError:
            raise
        except:
            self._load_mtime()
            if mtime_less(prerun_mtime, self.mtime):
                # Failed command resulted in a file written.
                # We have to clear it.
                self.log( logging.ERROR,
                    'deleting {}'.format(self.relative_path) )
                self.path.unlink()
            raise


class WriteTextCommand(Command):
    """
    Write some generated text to a file.
    """

    def __init__(self, node, textfunc):
        assert isinstance(node, FileNode), type(node)
        super().__init__(node)
        self.textfunc = textfunc

    @classmethod
    def from_text(cls, node, text):
        return cls(node, textfunc=lambda: text)

    def __call__(self):
        super().__call__()
        text = self.textfunc()
        if not isinstance(text, str):
            raise TypeError(type(text))
        self.log(logging.INFO, (
            '<GREEN>Write generated text to {node.relative_path}<NOCOLOUR>'
            .format(node=self.node)
        ))
        with self.node.open('w') as text_file:
            text_file.write(text)


class ProductFileNode(ProductNode, FileNode):
    pass


class LinkNode(ProductNode):
    """
    Represents a symbolic link to some other path.

    Attributes (additional to superclasses):
        source (PathNode):
            derived from ProductNode, this attribute is assigned specific
            semantics: it is the target of symbolic link.
    """

    def __init__(self, source, path,
        *, relative=True,
        name=None, needs=(), **kwargs
    ):
        """
        Initialize LinkNode instance.

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
            self.link_target = str(pure_relative(
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
        if mtime_less(mtime, source_mtime):
            self.mtime = source_mtime
        if source.modified:
            self.modified = True

    def _needs_build(self):
        """
        If the node needs to be (re)built.

        Override.
        LinkNode needs to be rebuilt in the following cases:
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


class LinkedFileNode(LinkNode, FilelikeNode):
    pass


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
        self.log(logging.INFO, (
            '<GREEN>{command} {node.relative_path}<NOCOLOUR>'
            .format(
                node=node,
                command='mkdir --parents' if parents else 'mkdir' )
        ))
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

