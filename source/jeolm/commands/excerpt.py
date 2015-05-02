import io
import datetime
import time

from stat import S_ISREG as stat_is_regular_file

import tarfile
import zipfile

from jeolm.node import (
    FilelikeNode, FollowingPathNode,
    FileNode, LazyWriteTextCommand, )
from jeolm.node.symlink import SymLinkedFileNode
from jeolm.node.directory import DirectoryNode
from jeolm.node.latex import LaTeXNode
from jeolm.node_factory import DocumentNode

_MAX_MTIME = datetime.datetime.max.timestamp()

import logging
logger = logging.getLogger(__name__) # pylint: disable=invalid-name


class _ArchiveManager:

    _file_mode = 0o000644
    _file_type = 0o100000

    def __init__(self, stream):
        self.stream = stream
        self.archive = None

    def add_member_stream(self, path, content_stream, content_size, mtime):
        raise NotImplementedError

    def add_member_bytes(self, path, content, mtime):
        raise NotImplementedError

    def add_member_str(self, path, content, mtime):
        return self.add_member_bytes(path, content.encode(), mtime)

    def add_member_node(self, path, node):

        while isinstance(node, SymLinkedFileNode):
            node = node.source
        if not isinstance(node, FilelikeNode):
            raise RuntimeError(node)
        if not isinstance(node, (FollowingPathNode, FileNode)):
            raise RuntimeError(node)

        if (isinstance(node, FileNode) and
                isinstance(node.command, LazyWriteTextCommand)):
            return self.add_member_str(
                path, node.command.textfunc(), time.time() )

        node.update()
        node_stat = node.stat(follow_symlinks=True)
        assert stat_is_regular_file(node_stat.st_mode)
        with node.open(mode='rb') as content_stream:
            self.add_member_stream(
                path=path,
                content_stream=content_stream,
                content_size=node_stat.st_size,
                mtime=node_stat.st_mtime,
            )

    def start(self):
        raise NotImplementedError

    def finish(self):
        raise NotImplementedError

    def __enter__(self):
        self.start()

    def __exit__(self, exc_type, exc_value, traceback):
        self.finish()

class _TarGzArchiveManager(_ArchiveManager):

    def add_member_stream(self, path, content_stream, content_size, mtime):
        if not content_stream.read(0) == b'':
            raise TypeError(type(content_stream))
        info = tarfile.TarInfo(path)
        info.size = content_size
        info.mtime = mtime
        info.mode = self._file_mode
        info.type = tarfile.REGTYPE
        self.archive.addfile(info, content_stream)

    def add_member_bytes(self, path, content, mtime):
        return self.add_member_stream(
            path, io.BytesIO(content), len(content), mtime )

    def start(self):
        self.archive = tarfile.open(fileobj=self.stream, mode='w:gz')

    def finish(self):
        self.archive.close()

class _ZipArchiveManager(_ArchiveManager):

    def add_member_stream(self, path, content_stream, content_size, mtime):
        content = content_stream.read(content_size)
        return self.add_member_bytes(path, content, mtime)

    def add_member_bytes(self, path, content, mtime):
        if not isinstance(content, bytes):
            raise TypeError(type(content))
        info = zipfile.ZipInfo( path,
            datetime.datetime.fromtimestamp(mtime).timetuple()[:6] )
        info.external_attr = (self._file_mode | self._file_type) << 16
        self.archive.writestr(info, content)

    def start(self):
        self.archive = zipfile.ZipFile(self.stream, mode='w')

    def finish(self):
        self.archive.close()


def excerpt_document( document_node, *, stream, include_pdf=False,
    figure_node_factory,
    archive_format='tar.gz'
):
    """Return None."""
    if archive_format == 'tar.gz':
        archive_manager = _TarGzArchiveManager(stream)
    elif archive_format == 'zip':
        archive_manager = _ZipArchiveManager(stream)
    else:
        raise RuntimeError(archive_format)

    assert isinstance(document_node, DocumentNode)
    build_dir_node = document_node.build_dir_node
    build_dir = build_dir_node.path
    latex_node, = [ node
        for node in document_node.iter_needs()
        if isinstance(node, LaTeXNode)
        if node.path.parent == build_dir]

    archived_nodes = list()
    for node in latex_node.needs:
        if isinstance(node, DirectoryNode):
            continue
        if not isinstance(node, FilelikeNode):
            raise RuntimeError(node)
        if build_dir != node.path.parent:
            raise RuntimeError(node)
        archived_nodes.append(node)
    for node in document_node.figure_nodes:
        archived_nodes.extend(
            _get_other_figure_formats( node,
                figure_node_factory=figure_node_factory,
                build_dir_node=build_dir_node )
        )
    if include_pdf:
        archived_nodes.append(document_node)

    with archive_manager:
        for member_node in archived_nodes:
            archive_manager.add_member_node(
                path=str(member_node.path.relative_to(build_dir)),
                node=member_node )

def _get_other_figure_formats( node, *,
    figure_node_factory, build_dir_node
):
    if not isinstance(node, SymLinkedFileNode):
        raise RuntimeError(node)
    figure_eps_node = node.source
    if not hasattr(figure_eps_node, 'metapath'):
        raise RuntimeError(figure_eps_node)
    metapath = figure_eps_node.metapath
    figure_nodes = {figure_eps_node}
    for figure_format in ('<latex>', '<pdflatex>'):
        figure_node = figure_node_factory( metapath,
            figure_format=figure_format )
        if figure_node in figure_nodes:
            continue
        figure_nodes.add(figure_node)
        yield SymLinkedFileNode(
            source=figure_node,
            path=node.path.with_suffix(figure_node.path.suffix),
            needs=(build_dir_node,) )

