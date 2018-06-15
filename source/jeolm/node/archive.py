import io
import datetime
import time

from contextlib import contextmanager
from stat import S_ISREG as stat_is_regular_file

import tarfile
import zipfile

from jeolm.node import FilelikeNode, FileNode
from jeolm.node.text import TextNode, VarTextNode
from jeolm.node.cyclic import AutowrittenNeed

from . import Command

class _ArchiveCommand(Command):

    _file_mode = 0o000644

    def __init__(self, node):
        assert isinstance(node, _ArchiveNode), type(node)
        super().__init__(node)
        self._archive = None

    async def call(self):
        self.logger.debug(
            "create archive <ITALIC>%(path)s<UPRIGHT>",
            dict(path=self.node.relative_path)
        )
        with self.node.open('wb') as archive_file:
            with self.open_archive(archive_file) as self._archive:
                for path, node in self.node.archive_content.items():
                    self.add_member_node(path, node)
        await super().call()

    @classmethod
    @contextmanager
    def open_archive(self, fileobj):
        raise NotImplementedError
        yield None

    def add_member_bytes(self, path, mtime, content: bytes):
        raise NotImplementedError

    def add_member_str(self, path, mtime, content):
        return self.add_member_bytes(path, mtime, content.encode('utf-8'))

    def add_member_stream(self, path, mtime, content_stream):
        content = content_stream.read()
        assert isinstance(content, bytes), type(content)
        return self.add_member_bytes(path, mtime, content)

    def add_member_node(self, path, node):

        if not isinstance(node, FilelikeNode):
            raise RuntimeError(node)

        if isinstance(node, TextNode):
            return self.add_member_str(path, time.time(), node.text)

        assert node.updated
        node_stat = node.stat(follow_symlinks=True)
        assert stat_is_regular_file(node_stat.st_mode)
        with node.open(mode='rb') as content_stream:
            self.add_member_stream(
                path=path,
                mtime=node_stat.st_mtime,
                content_stream=content_stream,
            )

class _ZipArchiveCommand(_ArchiveCommand):

    _file_type = 0o100000

    def add_member_bytes(self, path, mtime, content):
        if not isinstance(content, bytes):
            raise TypeError(type(content))
        info = zipfile.ZipInfo( str(path),
            datetime.datetime.fromtimestamp(mtime).timetuple()[:6] )
        info.external_attr = (self._file_mode | self._file_type) << 16
        self._archive.writestr(info, content)

    @classmethod
    @contextmanager
    def open_archive(cls, fileobj):
        archive = zipfile.ZipFile(fileobj, mode='w')
        try:
            yield archive
        finally:
            archive.close()

class _TgzArchiveCommand(_ArchiveCommand):

    def add_member_bytes(self, path, mtime, content):
        if not isinstance(content, bytes):
            raise TypeError(type(content))
        info = tarfile.TarInfo(str(path))
        info.size = len(content)
        info.mtime = mtime
        info.mode = self._file_mode
        info.type = tarfile.REGTYPE
        self._archive.addfile(info, io.BytesIO(content))

    @classmethod
    @contextmanager
    def open_archive(cls, fileobj):
        archive = tarfile.open(fileobj=fileobj, mode='w:gz')
        try:
            yield archive
        finally:
            archive.close()

class _ArchiveNode(FileNode):

    _Command = _ArchiveCommand
    default_suffix = None

    def __init__(self, path, name=None, **kwargs):
        super().__init__(path, name=name, **kwargs)
        self.archive_content = {}
        self.set_command(self._Command(self))

    def archive_add(self, path, node):
        if not isinstance(node, FilelikeNode):
            raise TypeError(type(node))
        if path in self.archive_content:
            raise ValueError(path)
        self.append_needs(node)
        self.archive_content[path] = node

    def archive_add_dir( self, path_prefix, root_node, node_dir, *,
        node_filter=None, path_namer=None
    ):
        for node in root_node.iter_needs():
            if not isinstance(node, FilelikeNode):
                continue
            if isinstance(node, (AutowrittenNeed, VarTextNode)):
                continue
            if not node_dir in node.path.parents:
                continue
            if node_filter is not None and not node_filter(node):
                continue
            if path_namer is None:
                path = path_prefix / node.path.relative_to(node_dir)
            else:
                path = path_namer(node)
            self.archive_add(path, node)

class ZipArchiveNode(_ArchiveNode):
    _Command = _ZipArchiveCommand
    default_suffix = '.zip'

class TgzArchiveNode(_ArchiveNode):
    _Command = _TgzArchiveCommand
    default_suffix = '.tgz'

