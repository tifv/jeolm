"""
Nodes, and dependency trees constructed of them.
"""

from itertools import chain
from functools import partial

import os
from stat import S_ISDIR
import subprocess
import time
from contextlib import contextmanager

from concurrent import futures

from pathlib import Path, PurePosixPath

import logging
from logging import DEBUG, INFO, WARNING, ERROR, CRITICAL
logger = logging.getLogger(__name__)

class CycleError(RuntimeError):
    pass

class MissingTargetError(FileNotFoundError):
    """Missing target file after execution of build commands."""
    pass

class Node:
    """
    Node represents target, or source, or whatever.

    Attributes:
      name (str): some short-but-identifying name.
        Shows up in log messages.
      needs (list of Node instances): prerequisites of this node.
        Should not be populated directly, but rather with initialization
        and node.extend_needs() method.
      commands (list of callables): commands that are responsible for
        (re)building node and setting `modified` attribute as appropriate.
        Expected to be populated with node.add_command() method
        (which may serve as decorator).
      modified (bool): if the node was modified.
        If equal to True, this attribute will cause any dependent nodes
        to be rebuilt. False by default, should be conditionally set to
        True by build commands (see above) or node._run_commands() method.
        Only node.needs_build() method of depending node should be
        interested in reading this attribute.
      _forced (bool): if the node was forced to rebuild.
        Setting it to True will cause node.needs_build() to always return
        True. Should be changed only by node.force() method.
      _updated (bool): if the node was ever updated.
        True if node.update() has ever completed in either concurrent or
        non-concurrent fashion. (The former means that the future returned
        by node.update() has completed.) Should be read and set only by
        node.update() method.
      _locked (bool): dependency cycle protection.
        Should be read and set only by node.update() method.
      _future (concurrent.futures.Future or None)
        Should be read and set only by node.update() method.
    """

    def __init__(self, *, name=None, needs=()):
        """
        Initialize Node instance.

        After initialization, node is un-updated, un-forced, un-modified.

        Args:
          name (str, optional): see `name` attribute in class documentation.
          needs (iterable of Node instances, optional): see `needs` attribute
            in class documentation.
        """
        if name is not None:
            self.name = str(name)
        else:
            self.name = 'id{}'.format(id(self))
        self.needs = list(needs)
        self.commands = list()

        self.modified = False
        self._forced = False

        self._updated = False
        self._locked = False
        self._future = None

    def __hash__(self):
        return hash(id(self))

    def update(self, *, executor=None):
        if executor is None:
            return self._update_nonconcurrent()
        else:
            return self._update_concurrent(executor=executor)

    def _update_nonconcurrent(self):
        """
        Update the node, first recursively updating needs.

        Return None.
        """

        with self._check_for_cycle():
            if self._updated:
                if self._future is not None:
                    self._future.result()
                return
            for node in self.needs:
                node.update()
            self._update_self()
            self._updated = True
            return

    def _update_concurrent(self, *, executor):
        """
        Issue a future that will update the node.

        Collect the corresponding futures from needs (prerequisite nodes) and
        create a future that will wait for them, and then update the node.

        Return a future (concurrent.futures.Future instance).
        """

        if not isinstance(executor, futures.Executor):
            raise RuntimeError(type(executor))

        with self._check_for_cycle():
            if self._updated:
                if self._future is None:
                    self._future = self._one_shot_future(lambda: None)
                return self._future
            needed_futures = [
                node.update(executor=executor)
                for node in self.needs ]
            if not needed_futures: # no dependencies, easy case
                self._future = executor.submit(self._update_self)
            else:
                def wait_for_needs_and_update_self():
                    for future in needed_futures:
                        future.result()
                    return executor.submit(self._update_self).result()
                self._future = self._one_shot_future(
                    wait_for_needs_and_update_self )
            self._updated = True
            return self._future

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

    @staticmethod
    def _one_shot_future(func, *args, **kwargs):
        one_shot_executor = futures.ThreadPoolExecutor(max_workers=1)
        future = one_shot_executor.submit(func, *args, **kwargs)
        one_shot_executor.shutdown(wait=False)
        return future

    def _update_self(self):
        if self.needs_build():
            self._run_commands()

    def needs_build(self):
        """
        Return True if the node needs to be (re)built.

        Node needs build in the following case:
        1) any of needed nodes are modified.
        (Subclasses may introduce different conditions)
        """
        if self._forced or any(node.modified for node in self.needs):
            return True
        return False

    def extend_needs(self, nodes):
        for node in nodes:
            self._append_needs(node)
        return self

    def _append_needs(self, node):
        if not isinstance(node, Node):
            raise TypeError(node)
        self.needs.append(node)

    def force(self):
        self._forced = True

    def add_command(self, command):
        """Decorator."""
        self.commands.append(command)
        return command

    def _run_commands(self):
        # Should be only called by self._update_self()
        for command in self.commands:
            command()

    def iter_needs(self, _seen_needs=None):
        """Yield this node and all needs, recursively."""
        if _seen_needs is None:
            _seen_needs = {self}
        elif self in _seen_needs:
            return
        else:
            _seen_needs.add(self)
        yield self
        for need in self.needs:
            yield from need.iter_needs(_seen_needs=_seen_needs)

    def _log(self, level, message):
        """
        Log a message specific for this node.

        Prepend a message with node.name and delegate to module logger.
        This function expects FancifyingFormatter to be used somewhere
        in logging facility.
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

class TargetNode(Node):
    """Represent an abstract target."""
    pass

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

    def _update_self(self):
        self.load_mtime()
        super()._update_self()

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
        return super().needs_build()

    def load_mtime(self):
        """
        Set node.mtime to appropriate value.

        No-op here. Subclasses may introduce appropriate behavior.
        """
        pass

    def set_mtime_to_now(self):
        self.mtime = int(time.time() * (10**9))

    @staticmethod
    def mtime_less(x, y):
        if y is None:
            return False
        if x is None:
            return True
        return x < y

class PathNode(DatedNode):
    """
    PathNode represents filesystem path, existing or not.

    It introduces `path` attribute.

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

    def _run_commands(self):
        prerun_mtime = self.mtime
        try:
            super()._run_commands()
        except:
            self.load_mtime()
            if self.mtime_less(prerun_mtime, self.mtime):
                # Failed command resulted in a file written.
                # We have to clear it.
                self._log(ERROR, 'deleting {}'.format(self.relative_path))
                self.path.unlink()
            raise
        self.load_mtime()
        if self.mtime is None:
            # Succeeded commands did not result in a file
            raise MissingTargetError(repr(self))
        if prerun_mtime != self.mtime:
            self.modified = True

    @property
    def relative_path(self):
        return self.root_relative(self.path)

    @classmethod
    def root_relative(cls, path):
        if cls.root is None:
            return path
        return cls.pure_relative(path, cls.root)

    @staticmethod
    def pure_relative(path, root):
        """
        Compute relative PurePosixPath, with '..' parts.

        Both arguments must be absolute PurePosixPath's and lack '..' parts.
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
        return PurePosixPath(*
            ['..'] * upstairs + [path.relative_to(root)] )

class SubprocessCommand:

    def __init__(self, node, callargs, *, cwd, **kwargs):
        self.node = node
        self.callargs = callargs
        if not isinstance(cwd, Path):
            raise ValueError(
                "cwd must be a pathlib.Path object, not {cwd_type.__name__}"
                .format(cwd_type=type(cwd)) )
        if not cwd.is_absolute():
            raise ValueError("cwd must be an absolute Path")
        self.cwd = cwd
        kwargs.setdefault('stderr', subprocess.STDOUT)
        self.kwargs = kwargs

    def __call__(self):
        """
        Run external process.

        Process output (see _subprocess_output() method documentation)
        is catched and logged (with INFO level).

        Returns None.

        Raises:
          subprocess.CalledProcessError: in case of error in the called
            process.
        """

        output = self._subprocess_output()
        if not output:
            return
        self.node._log(INFO,
            "Command {prog} output:<RESET>\n{output}"
            "(output while building <MAGENTA>{node.name}<NOCOLOUR>)"
            .format(node=self.node, prog=self.callargs[0], output=output)
        )

    def _subprocess_output(self, log_error_output=True):
        """
        Run external process.

        Process output (the combined stdout and stderr of the spawned
        process, decoded with default encoding and errors='replace')
        is catched and done something with, depending on args.

        Args:
          log_error_output (bool, optional): If True (default), in case of
            process error its output will be logged (with ERROR level).
            If False, it will not be logged. Defaults to True. In any case,
            any received subprocess.CalledProcessError exception is reraised.

        Returns:
          Process output (str).

        Raises:
          subprocess.CalledProcessError: in case of error in the called
            process.
        """

        self.node._log(INFO, (
            '<cwd=<CYAN>{cwd}<NOCOLOUR>> <GREEN>{command}<NOCOLOUR>'
            .format(
                cwd=self.node.root_relative(self.cwd),
                command=' '.join(self.callargs), )
        ))

        try:
            encoded_output = subprocess.check_output(
                self.callargs, cwd=str(self.cwd), **self.kwargs )
        except subprocess.CalledProcessError as exception:
            if not log_error_output:
                raise
            output = exception.output.decode(errors='replace')
            self.node._log(ERROR,
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

class ProductNode(PathNode):
    """
    ProductNode has a source.

    ProductNode is a subclass of PathNode that introduces a notion of
    source, which is also a PathNode. The source is automatically
    prepended to node.needs list.

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

    def _turn_older_than_source(self):
        """Alter mtime to be just below source mtime."""
        sourcestat = self.source.stat()
        os.utime(
            str(self.path),
            ns=(sourcestat.st_atime_ns-1, sourcestat.st_mtime_ns-1)
        )
        self.load_mtime()

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

    def _run_commands(self):
        # Written in blood
        if self.path.exists() and self.path.is_symlink():
            self.path.unlink()
        super()._run_commands()

class TextCommand:
    """
    Write some generated text to a file.
    """
    def __init__(self, node, textfunc):
        self.node = node
        self.textfunc = textfunc

    @classmethod
    def from_text(cls, node, text):
        return cls(node, textfunc=lambda: text)

    def __call__(self):
        text = self.textfunc()
        if not isinstance(text, str):
            raise TypeError(type(text))
        self.node._log(INFO, (
            '<GREEN>Write generated text to {node.relative_path}<NOCOLOUR>'
            .format(node=self.node)
        ))
        with self.node.open('w') as f:
            f.write(text)

class ProductFileNode(ProductNode, FileNode):
    pass

class LinkNode(ProductNode):
    """
    LinkNode represents a symlink to the file.

    Attributes
    ----------
    source (derived from ProductNode)
        PathNode instance. Represents the target of the link.
    """

    def __init__(self, source, path, *, relative=True, **kwargs):
        super().__init__(source, path, **kwargs)

        if not relative:
            self.link_target = str(source.path)
        else:
            self.link_target = str(self.pure_relative(
                source.path, self.path.parent ))

        @self.add_command
        def link_command():
            if not isinstance(self.link_target, str):
                raise TypeError(type(self.link_target))
            if os.path.lexists(str(self.path)):
                self.path.unlink()
            self._log(INFO, (
                '<source=<CYAN>{node.source.name}<NOCOLOUR>> '
                '<GREEN>ln --symbolic {node.link_target} '
                    '{node.relative_path}<NOCOLOUR>'
                .format(node=self) ))
            os.symlink(self.link_target, str(self.path))
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
            self.link_target == os.readlink(path) )

class DirectoryNode(PathNode):
    def __init__(self, path, *, parents=False, **kwargs):
        super().__init__(path, **kwargs)
        @self.add_command
        def mkdir_command():
            if os.path.lexists(str(path)):
                path.unlink()
            self._log(INFO, (
                '<GREEN>{command} {node.relative_path}<NOCOLOUR>'
                .format(
                    node=self,
                    command='mkdir --parents' if parents else 'mkdir' )
            ))
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
            return
        if S_ISDIR(stat.st_mode):
            self.mtime = 0
        else:
            raise NotADirectoryError(
                "Found something where a directory should be: {}"
                .format(self.relative_path) )

