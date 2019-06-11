# Imports and logging {{{1
import re
import os
import os.path
from pathlib import PosixPath

from . import ( Node, DatedNode, BuildableNode, BuildableDatedNode,
    PathNode, FilelikeNode )
from .text import text_hash, TEXT_HASH_PATTERN

import logging
logger = logging.getLogger(__name__)

from typing import ClassVar, Optional, Iterable, List

class CyclicNeed(Node): # {{{1

    # Override
    async def update_self(self) -> None:
        self.refresh()
        self.updated = True

    def refresh(self) -> None:
        raise NotImplementedError

class CyclicDatedNeed(CyclicNeed, DatedNode): # {{{1

    # Override
    async def update_self(self) -> None:
        self._load_mtime()
        self.refresh()
        self.updated = True


class AutowrittenNeed(FilelikeNode, CyclicDatedNeed): # {{{1
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

    def refresh(self) -> None:
        self.modified = False
        if not os.path.lexists(self.path): # (1)
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
                raise OSError(
                    f"Expected regular file or symlink: {self.path}" )
        # path is a symlink
        target_name = os.readlink(str(self.path))
        match = self._var_name_regex.fullmatch(target_name)
        if match is None or match.group('name') != self.path.name: # (1a)
            self._refresh_clear()
            return
        target_path = self.path.with_name(target_name)
        if not os.path.lexists(target_path): # (1a)
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
    def _refresh_hash(path: PosixPath) -> str:
        with path.open(encoding='utf-8') as the_file:
            return text_hash(the_file.read())

    def _refresh_move( self, target_path: PosixPath,
        content_hash: str = None,
    ) -> None:
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

    def _refresh_clear(self) -> None:
        self.path.unlink()
        self.modified = True
        self._load_mtime()


class CyclicNode(BuildableNode): # {{{1

    cyclic_needs: List[CyclicNeed]
    cycle: int

    max_cycles: ClassVar[int] = 7

    def __init__( self,
        *, name: Optional[str] = None, needs: Iterable[Node] = (),
    ) -> None:
        self.cyclic_needs = list()
        super().__init__(name=name, needs=needs)
        self.cycle = 0

    def _append_needs(self, node: Node) -> None:
        super()._append_needs(node)
        if isinstance(node, CyclicNeed):
            self.cyclic_needs.append(node)

    # Override
    async def update_self(self) -> None:
        if self.cycle == 0:
            if self._needs_build():
                await self._update_cyclic()
            else:
                self.updated = True
        else:
            await self._update_cyclic()

    async def _update_cyclic(self) -> None:
        await self._run_command()
        assert self.updated
        self.cycle += 1
        for need in self.cyclic_needs:
            need.refresh()
        if self._needs_build_cyclic():
            if self.cycle < self.max_cycles:
                self._update_cyclic_continue()
            else:
                self._update_cyclic_halt()
        else:
            self._update_cyclic_finish()

    def _update_cyclic_continue(self) -> None:
        self.updated = False

    def _update_cyclic_halt(self) -> None:
        pass

    def _update_cyclic_finish(self) -> None:
        pass

    def _needs_build_cyclic(self) -> bool:
        return any(
            need.modified or not need.updated
            for need in self.cyclic_needs )

class CyclicDatedNode(CyclicNode, BuildableDatedNode): # {{{1

    # Override
    async def update_self(self) -> None:
        if self.cycle == 0:
            self._load_mtime()
            if self._needs_build():
                await self._update_cyclic()
            else:
                self.updated = True
        else:
            await self._update_cyclic()

class CyclicPathNode(PathNode, CyclicDatedNode): # {{{1
    pass

# }}}1
# vim: set foldmethod=marker :
