from itertools import chain

import re
import hashlib

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

    def call(self):
        self.logger.info(
            "write to <ITALIC>%(path)s<UPRIGHT>",
            dict(path=self.node.relative_path)
        )
        with self.node.open('w') as text_file:
            text_file.write(self.text)
        super().call()

def text_hash(text):
    return hashlib.sha256(text.encode()).hexdigest()

class CleanupSymLinkCommand(SymLinkCommand):

    _var_name_regex = re.compile(r'(?P<name>.+)\.(?P<hash>[0-9a-f]{64})')

    # SymlinkNode class sets self.old_target attribute.
    def _clear_path(self):
        super()._clear_path()
        if self.node.old_target is None:
            return
        match = self._var_name_regex.fullmatch(self.node.old_target)
        if match is not None and match.group('name') == self.node.path.name:
            old_var_path = self.node.path.with_name(match.group(0))
            if old_var_path.exists():
                self.logger.debug(
                    "<GREEN>remove <ITALIC>%(path)s<UPRIGHT><NOCOLOUR>",
                    dict(path=self.node.root_relative(old_var_path))
                )
                old_var_path.unlink()


class TextNode(SymLinkedFileNode):

    _Command = CleanupSymLinkCommand

    def __init__(self, path, text,
        *, build_dir_node,
        name=None, needs=(), **kwargs
    ):
        if path.parent != build_dir_node.path:
            raise RuntimeError(path)
        var_name = '{name}.{hash}'.format(
            name=path.name, hash=text_hash(text) )
        var_text_node = FileNode(
            path=path.with_name(var_name),
            name='{}:var'.format(name),
            needs=(build_dir_node,) )
        var_text_node.set_command(WriteTextCommand(var_text_node, text))
        if isinstance(build_dir_node, BuildDirectoryNode):
            build_dir_node.register_node(var_text_node)
        super().__init__(
            source=var_text_node, path=path,
            name=name,
            needs=chain(needs, (build_dir_node,)),
            **kwargs )
        self.text = text

