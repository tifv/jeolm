import io
import datetime
import time
from pathlib import PurePosixPath, PosixPath

from stat import S_ISREG as stat_is_regular_file

import tarfile
import zipfile

from jeolm.node import Node, FilelikeNode, FileNode
from jeolm.node.text import TextNode, VarTextNode
from jeolm.node.cyclic import AutowrittenNeed

from . import Command

from typing import ( cast, ClassVar, Type, Any, Union, Optional,
    Callable, Iterable,
    Dict,
    BinaryIO )
# pylint: disable=invalid-name
ArchiveMTime = Union[int, float]
# pylint: enable=invalid-name


class _ArchiveCommand(Command):

    node: '_ArchiveNode'

    def __init__(self, node: '_ArchiveNode') -> None:
        assert isinstance(node, _ArchiveNode), type(node)
        super().__init__(node)

    async def run(self) -> None:
        self.logger.debug(
            "create archive <ITALIC>%(path)s<UPRIGHT>",
            dict(path=self.node.relative_path)
        )
        with self.node.path.open('wb') as archive_file:
            with self.Archiver(cast(BinaryIO, archive_file)) \
                    as archiver:
                for path, node in self.node.archive_content.items():
                    archiver.add_member_node(path, node)
        self.node.updated = True

    class Archiver:

        _file_mode = 0o000644

        def __init__(self, archive_stream: BinaryIO) -> None:
            pass

        def __enter__(self) -> '_ArchiveCommand.Archiver':
            return self

        def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
            return False # do not suppress exceptions

        def add_member_bytes( self, path: PurePosixPath,
            mtime: ArchiveMTime, content: bytes,
        ) -> None:
            raise NotImplementedError

        def add_member_str( self, path: PurePosixPath,
            mtime: ArchiveMTime, content: str,
        ) -> None:
            return self.add_member_bytes(path, mtime, content.encode('utf-8'))

        def add_member_stream( self,
            path: PurePosixPath, mtime: ArchiveMTime,
            content_stream: BinaryIO,
        ) -> None:
            content = content_stream.read()
            assert isinstance(content, bytes), type(content)
            return self.add_member_bytes(path, mtime, content)

        def add_member_node( self,
            path: PurePosixPath, node: FilelikeNode,
        ) -> None:

            if not isinstance(node, FilelikeNode):
                raise RuntimeError(node)

            if isinstance(node, TextNode):
                self.add_member_str(path, time.time(), node.text)
                return

            assert node.updated
            node_stat = node.stat(follow_symlinks=True)
            assert stat_is_regular_file(node_stat.st_mode)
            with node.path.open(mode='rb') as content_stream:
                self.add_member_stream(
                    path=path,
                    mtime=node_stat.st_mtime,
                    content_stream=cast(BinaryIO, content_stream),
                )


class _ZipArchiveCommand(_ArchiveCommand):

    class ZipArchiver(_ArchiveCommand.Archiver):

        _file_type = 0o100000

        _archive: zipfile.ZipFile

        def __init__(self, archive_stream: BinaryIO) -> None:
            super().__init__(archive_stream)
            self._archive = zipfile.ZipFile(archive_stream, mode='w')

        def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
            self._archive.close()
            return super().__exit__(exc_type, exc_val, exc_tb)

        def add_member_bytes( self,
            path: PurePosixPath, mtime: ArchiveMTime, content: bytes,
        ) -> None:
            if not isinstance(content, bytes):
                raise TypeError(type(content))
            info = zipfile.ZipInfo()
            info.filename = str(path)
            info.date_time = \
                datetime.datetime.fromtimestamp(mtime).timetuple()[:6]
            info.external_attr = (self._file_mode | self._file_type) << 16
            self._archive.writestr(info, content)


class _TgzArchiveCommand(_ArchiveCommand):

    class Archiver(_ArchiveCommand.Archiver):

        _archive: tarfile.TarFile

        def __init__(self, archive_stream: BinaryIO) -> None:
            super().__init__(archive_stream)
            self._archive = tarfile.open(fileobj=archive_stream, mode='w:gz')

        def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
            self._archive.close()
            return super().__exit__(exc_type, exc_val, exc_tb)

        def add_member_bytes( self,
            path: PurePosixPath, mtime: ArchiveMTime, content: bytes,
        ) -> None:
            info = tarfile.TarInfo(str(path))
            info.size = len(content)
            info.mtime = mtime # type: ignore
            info.mode = self._file_mode
            info.type = tarfile.REGTYPE
            self._archive.addfile(info, io.BytesIO(content))


class _ArchiveNode(FileNode):

    _Command: ClassVar[Type[_ArchiveCommand]] = _ArchiveCommand
    default_suffix: ClassVar[Optional[str]] = None

    command: _ArchiveCommand
    archive_content: Dict[PurePosixPath, FilelikeNode]

    def __init__( self, path: PosixPath,
        *, name: Optional[str] = None, needs: Iterable[Node] = (),
    ) -> None:
        super().__init__(path, name=name, needs=needs)
        self.archive_content = {}
        self.command = self._Command(self)

    def archive_add(self, path: PurePosixPath, node: FilelikeNode) -> None:
        if not isinstance(node, FilelikeNode):
            raise TypeError(type(node))
        if path in self.archive_content:
            raise ValueError(path)
        self.append_needs(node)
        self.archive_content[path] = node

    _skipped_nodes = (AutowrittenNeed, VarTextNode)

    def archive_add_tree( self, root_node: Node,
        *,
        node_filter: Callable[[FilelikeNode], bool],
        path_namer: Callable[[FilelikeNode], PurePosixPath],
    ) -> None:
        for node in root_node.iter_needs():
            if not isinstance(node, FilelikeNode):
                continue
            self._archive_add_tree_item(node, node_filter, path_namer)
            if isinstance(node, self._skipped_nodes):
                continue
            if not node_filter(node):
                continue
            path = path_namer(node)
            self.archive_add(path, node)

    def _archive_add_tree_item( self, node: FilelikeNode,
        node_filter: Callable[[FilelikeNode], bool],
        path_namer: Callable[[FilelikeNode], PurePosixPath],
    ) -> None:
        if isinstance(node, self._skipped_nodes):
            return
        if not node_filter(node):
            return
        path = path_namer(node)
        self.archive_add(path, node)

    def archive_add_dir( self, root_node: Node,
        base_dir: PosixPath, path_prefix: PurePosixPath
    ) -> None:
        def node_filter(node: FilelikeNode) -> bool:
            return base_dir in node.path.parents
        def path_namer(node: FilelikeNode) -> PurePosixPath:
            return path_prefix / node.path.relative_to(base_dir)
        self.archive_add_tree( root_node,
            node_filter=node_filter, path_namer=path_namer )

class ZipArchiveNode(_ArchiveNode):
    _Command = _ZipArchiveCommand
    default_suffix = '.zip'

class TgzArchiveNode(_ArchiveNode):
    _Command = _TgzArchiveCommand
    default_suffix = '.tgz'

