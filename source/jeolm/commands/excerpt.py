import io
import datetime
import time

from stat import S_ISREG as stat_is_regular_file

import tarfile
import zipfile

from jeolm.node import ( Node, FilelikeNode, ProductNode,
    FileNode, LazyWriteTextCommand, )
from jeolm.node.symlink import SymLinkedFileNode
from jeolm.node.latex import LaTeXNode
from jeolm.node_factory import DocumentNode

_MAX_MTIME = datetime.datetime.max.timestamp()

import logging
logger = logging.getLogger(__name__)


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

        if not isinstance(node, FilelikeNode):
            raise RuntimeError(node)

        if (isinstance(node, FileNode) and
                isinstance(node.command, LazyWriteTextCommand)):
            return self.add_member_str(
                path, node.command.textfunc(), time.time() )

        assert node.updated
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
    figure_node_factory, node_updater,
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
    latex_node = document_node
    while isinstance(latex_node, ProductNode):
        if isinstance(latex_node, LaTeXNode):
            break
        latex_node = latex_node.source
    else:
        raise RuntimeError(document_node)

    archive_node = Node(name='archive:{}'.format(document_node.name))
    for node in latex_node.needs:
        if not isinstance(node, FilelikeNode):
            continue
        if build_dir != node.path.parent:
            raise RuntimeError(node)
        archive_node.append_needs(node)
    for node in document_node.figure_nodes:
        archive_node.extend_needs(
            _get_other_figure_formats( node,
                figure_node_factory=figure_node_factory,
                build_dir_node=build_dir_node )
        )
    if include_pdf:
        archive_node.append_needs(document_node)

    node_updater.update(archive_node)
    with archive_manager:
        for member_node in archive_node.needs:
            archive_manager.add_member_node(
                path=str(member_node.path.relative_to(build_dir)),
                node=member_node )

def _get_other_figure_formats( node, *,
    figure_node_factory, build_dir_node,
    figure_formats=('<latex>', '<pdflatex>', '<xelatex>', '<lualatex>')
):
    if not isinstance(node, SymLinkedFileNode):
        raise RuntimeError(node)
    figure_node = node.source
    if not hasattr(figure_node, 'metapath'):
        raise RuntimeError(figure_node)
    metapath = figure_node.metapath
    figure_type = figure_node.figure_type
    if figure_type not in figure_node_factory.flexible_figure_types:
        # We most probably can't rebuild this figure in other format.
        return
    figure_nodes = {figure_node}
    for figure_format in figure_formats:
        other_figure_node = figure_node_factory( metapath,
            figure_format=figure_format, figure_type=figure_type )
        if other_figure_node in figure_nodes:
            continue
        figure_nodes.add(other_figure_node)
        yield SymLinkedFileNode(
            source=other_figure_node,
            path=node.path.with_suffix(other_figure_node.path.suffix),
            needs=(build_dir_node,) )

