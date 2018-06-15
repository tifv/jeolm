from itertools import chain

import re
import hashlib
import base64

from . import FileNode, Command
from .directory import BuildDirectoryNode
from .symlink import SymLinkedFileNode, SymLinkCommand

class WriteTextCommand(Command):
    """
    Write some text to a file.
    """

    def __init__(self, node, text):
        if not isinstance(node, FileNode):
            raise RuntimeError(type(node))
        super().__init__(node)
        if not isinstance(text, str):
            raise TypeError(type(text))
        self.text = text

    async def call(self):
        self.logger.info(
            "write to <ITALIC>%(path)s<UPRIGHT>",
            dict(path=self.node.relative_path)
        )
        with self.node.open('w') as text_file:
            text_file.write(self.text)
        await super().call()

def text_hash(text):
    return base64.b64encode( hashlib.sha256(text.encode('utf-8')).digest(),
        b'+-' ).decode()[:-1]
TEXT_HASH_PATTERN = r"[0-9a-zA-Z\+\-]{43}"

class _CleanupSymLinkCommand(SymLinkCommand):

    _var_name_regex = re.compile(
        r'(?P<name>.+)\.(?P<hash>' + TEXT_HASH_PATTERN + ')' )

    # SymlinkNode class sets self.current_target attribute.
    def _clear_path(self):
        super()._clear_path()
        if self.node.current_target is None:
            return
        match = self._var_name_regex.fullmatch(self.node.current_target)
        if match is not None and match.group('name') == self.node.path.name:
            old_var_path = self.node.path.with_name(match.group(0))
            if old_var_path.exists():
                self.logger.debug(
                    "<GREEN>remove <ITALIC>%(path)s<UPRIGHT><NOCOLOUR>",
                    dict(path=self.node.root_relative(old_var_path))
                )
                old_var_path.unlink()


class VarTextNode(FileNode):

    def __init__(self, path, text, *,
        name=None, needs=(), **kwargs
    ):
        super().__init__(path, name=name, needs=needs, **kwargs)
        self.set_command(WriteTextCommand(self, text))

class TextNode(SymLinkedFileNode):

    _Command = _CleanupSymLinkCommand

    def __init__(self, path, text,
        *, build_dir_node,
        name=None, needs=(), **kwargs
    ):
        if path.parent != build_dir_node.path:
            raise RuntimeError(path)
        var_name = '{name}.{hash}'.format(
            name=path.name, hash=text_hash(text) )
        var_text_node = VarTextNode(
            path=path.with_name(var_name), text=text,
            name='{}:var'.format(name),
            needs=(build_dir_node,) )
        if isinstance(build_dir_node, BuildDirectoryNode):
            build_dir_node.register_node(var_text_node)
        super().__init__(
            source=var_text_node, path=path,
            name=name,
            needs=chain(needs, (build_dir_node,)),
            **kwargs )
        self.text = text

