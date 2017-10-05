# Imports and logging {{{1
import abc
from itertools import chain

import re
import os
import os.path

from . import ( Node, DatedNode, BuildableNode, FilelikeNode,
    Command, SubprocessCommand )
from .text import text_hash, TEXT_HASH_PATTERN

class CyclicNeed(Node, metaclass=abc.ABCMeta): # {{{1

    async def update_self(self):
        await super().update_self()
        self.refresh()

    @abc.abstractmethod
    def refresh(self):
        raise NotImplementedError

class AutowrittenNeed(FilelikeNode, CyclicNeed, DatedNode): # {{{1
    """
    This node can be in one of the following states:
    (1) path is non-existing.
        (1a) path is a broken symlink.
    (2) path is a symlink to regular file.
        (2a) path is a regular file.

    refresh() method reduces (1a) to (1) and (2a) to (2).
    Also, if symlink hash in case (2) does not match the contents of
    a file, file is moved and symlink updated.
    """

    # Symlink that does not conform to _var_name_regex is qualified
    # as broken (1a).
    _var_name_regex = re.compile(
        r'(?P<name>.+)\.(?P<hash>' + TEXT_HASH_PATTERN + ')' )
    _empty_hash = text_hash('')

    def refresh(self):
        self.modified = False
        if not os.path.lexists(str(self.path)): # (1)
            return
        if not self.path.is_symlink():
            if self.path.is_file(): # (2a)
                content_hash = self._refresh_hash(self.path)
                self.logger.debug( "Hash updated to %(b)s…",
                    dict(b=content_hash) )
                self._refresh_move(self.path, )
                return
            elif self.path.is_dir():
                raise IsADirectoryError(str(self.path))
            else:
                raise OSError( "Expected regular file or symlink: {}"
                    .format(str(self.path)) )
        # path is a symlink
        target_name = os.readlink(str(self.path))
        match = self._var_name_regex.fullmatch(target_name)
        if match is None or match.group('name') != self.path.name: # (1a)
            self._refresh_clear()
            return
        target_path = self.path.with_name(target_name)
        if not os.path.lexists(str(target_path)): # (1a)
            self._refresh_clear()
            return
        if target_path.is_symlink() or not target_path.is_file():
            raise OSError( "Expected regular file: {}"
                .format(str(target_path)) )
        # (2) path is a conforming symlink and targets a file
        content_hash = self._refresh_hash(target_path)
        if content_hash == match.group('hash'):
            return
        self.logger.debug( "Hash updated from %(a)s to %(b)s…",
            dict(a=match.group('hash'), b=content_hash) )
        self._refresh_move(target_path, content_hash)

    @staticmethod
    def _refresh_hash(path):
        with path.open(encoding='utf-8') as the_file:
            return text_hash(the_file.read())

    def _refresh_move(self, target_path, content_hash=None):
        if content_hash is None:
            content_hash = self._refresh_hash(target_path)
        new_name = '{name}.{hash}'.format(
            name=self.path.name, hash=content_hash )
        new_path = self.path.with_name(new_name)
        if os.path.lexists(str(new_path)):
            new_path.unlink()
        target_path.rename(new_path)
        if os.path.lexists(str(self.path)):
            self.path.unlink()
        self.path.symlink_to(new_name)
        self.modified = True
        self._load_mtime()

    def _refresh_clear(self):
        self.path.unlink()
        self.modified = True
        self._load_mtime()


class CyclicCommand(Command): # {{{1

    # Override
    async def call(self):
        pass

class CyclicSubprocessCommand(SubprocessCommand, CyclicCommand): # {{{1
    pass

class CyclicNode(BuildableNode): # {{{1

    max_cycles = 7

    def __init__(self, *, needs=(), cyclic_needs=(), **kwargs):
        self.cyclic_needs = list(cyclic_needs)
        super().__init__(needs=chain(needs, self.cyclic_needs), **kwargs)
        self.cycle = 0

    def _needs_build(self):
        if self.cycle <= 0:
            return super()._needs_build()
        elif self._needs_build_cyclic():
            return self.cycle < self.max_cycles
        else:
            return False

    def _needs_build_cyclic(self):
        return any( node.modified
            for node in self.cyclic_needs )

    async def _run_command(self):
        await super()._run_command()
        for need in self.cyclic_needs:
            need.refresh()
        self.cycle += 1

# }}}1
# vim: set foldmethod=marker :
