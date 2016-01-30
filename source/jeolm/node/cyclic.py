from itertools import chain

import re
import os
import os.path

from . import BuildableNode, FilelikeNode
from .text import text_hash

class CyclicNeed(FilelikeNode):

    _var_name_regex = re.compile(r'(?P<name>.+)\.(?P<hash>[0-9a-f]{64})')
    _empty_hash = text_hash('')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._current_hash = None
        self._current_path = None

    def update_self(self):
        super().update_self()
        self._current_path, self._current_hash = \
            self._find_current_path_and_hash()
        self.refresh()

    def _find_current_path_and_hash(self):
        if not self.path.exists():
            return None, None
        if not self.path.is_symlink():
            if self.path.is_dir():
                raise IsADirectoryError(str(self.path))
            return self.path, None
        else:
            link_target = os.readlink(str(self.path))
            match = self._var_name_regex.fullmatch(link_target)
            if match is None or match.group('name') != self.path.name:
                return None, None
            current_path = self.path.with_name(match.group(0))
            if os.path.lexists(str(current_path)):
                if not current_path.is_file() or current_path.is_symlink():
                    return None, None
            else:
                if match.group('hash') != self._empty_hash:
                    return None, None
            return current_path, match.group('hash')

    def refresh(self):
        if self._current_path is not None:
            if ( self._current_hash == self._empty_hash and
                not self._current_path.exists()
            ):
                self.modified = False
                return
            with self.open() as aux_file:
                new_hash = text_hash(aux_file.read())
            if new_hash == self._current_hash:
                self.modified = False
                return
            self.logger.debug(
                "Hash changed from %(a)s… to %(b)s…",
                dict(a=str(self._current_hash)[:12], b=new_hash[:12])
            )
        else:
            new_hash = self._empty_hash
        new_name = '{name}.{hash}'.format(
            name=self.path.name, hash=new_hash)
        new_path = self.path.with_name(new_name)
        if os.path.lexists(str(new_path)):
            new_path.unlink()
        if self._current_path is not None:
            self._current_path.rename(new_path)
            if self._current_path == self.path:
                self.mtime = None
        if self.mtime is not None:
            self.path.unlink()
        self.path.symlink_to(new_name)
        self._current_hash = new_hash
        self._current_path = new_path
        self.modified = True
        self._load_mtime()


class CyclicNode(BuildableNode):

    max_cycles = 7

    def __init__(self, *, needs=(), cyclic_needs=(), **kwargs):
        self.cyclic_needs = list(cyclic_needs)
        super().__init__(needs=chain(needs, cyclic_needs), **kwargs)
        self.cycle = 0

    def _needs_build(self):
        if self.cycle <= 0 and super()._needs_build():
            return True
        elif any(node.modified for node in self.cyclic_needs):
            if self.cycle < self.max_cycles:
                return True
            else:
                return False
        else:
            return False

    def _run_command(self):
        super()._run_command()
        for need in self.cyclic_needs:
            need.refresh()

