from functools import partial
from pathlib import PurePosixPath, PosixPath

import jeolm.node
import jeolm.node.symlink
import jeolm.node.archive

from .document import DocumentNode, AsymptoteFigureNode
from .figure import BuildableFigureNode

import logging
logger = logging.getLogger(__name__)

import typing
from typing import ( Type, Optional,
    Iterable, Set )

class BaseDocumentArchiveNode(jeolm.node.archive.BaseArchiveNode):

    def __init__( self,
        path: PosixPath,
        *, document_node: DocumentNode, source_dir: PosixPath,
        name: Optional[str] = None, needs: Iterable[jeolm.node.Node] = (),
    ) -> None:
        super().__init__(path, name=name, needs=(*needs, document_node))
        self._document_node = document_node
        self._source_dir = source_dir
        self._document_output_dir = document_node.output_dir_node.path
        self._document_build_dir = document_node.build_dir_node.path
        self._archive_filled = False

    # Override
    async def update_self(self) -> None:
        if not self._archive_filled:
            assert self._document_node.updated
            seen_source_nodes: Set[jeolm.node.FilelikeNode] = set()
            self._archive_add_document_tree( self._document_node,
                seen_source_nodes=seen_source_nodes )
            self._archive_add_extra_sources( self._document_node,
                seen_source_nodes=seen_source_nodes )
            self._archive_filled = True
            assert not self.updated
            return
        await super().update_self()

    def _archive_add_document_item( self, node: jeolm.node.Node,
        *, seen_source_nodes: Set[jeolm.node.FilelikeNode],
    ) -> None:
        if not isinstance(node, jeolm.node.FilelikeNode):
            return
        if isinstance(node, self._skipped_nodes):
            return
        path: PosixPath = node.path
        if self._document_build_dir not in path.parents:
            return
        recurse = partial( self._archive_add_document_tree, node,
            seen_source_nodes=seen_source_nodes )
        if self._document_output_dir in path.parents:
            recurse()
            return
        if isinstance(node, AsymptoteFigureNode):
            assert node.link_node is not None
            self._archive_add_document_item( node.link_node,
                seen_source_nodes=seen_source_nodes )
            return
        archive_path: PurePosixPath = path.relative_to(self._document_build_dir)
        self.archive_add(archive_path, node)
        while isinstance(node, (jeolm.node.symlink.SymLinkNode, jeolm.node.symlink.ProxyNode)):
            logger.debug('%s -> %s', node.name, node.source.name)
            node = node.source
        seen_source_nodes.add(node)
        recurse()
        return

    def _archive_add_document_tree( self, node: jeolm.node.Node,
        *, seen_source_nodes: Set[jeolm.node.FilelikeNode],
    ) -> None:
        for need in node.needs:
            self._archive_add_document_item( need,
                seen_source_nodes=seen_source_nodes )

    def _archive_add_extra_sources( self, document_node: jeolm.node.FilelikeNode,
        *, seen_source_nodes: Set[jeolm.node.FilelikeNode],
    ) -> None:
        source_dir = self._source_dir
        def node_filter(node: jeolm.node.FilelikeNode) -> bool:
            if source_dir not in node.path.parents:
                return False
            if isinstance(node, jeolm.node.symlink.ProxyNode):
                return False
            if node in seen_source_nodes:
                return False
            return True
        def path_namer(node: jeolm.node.FilelikeNode) -> PurePosixPath:
            return PurePosixPath( 'extra',
                '-'.join(node.path.relative_to(source_dir).parts) )
        self.archive_add_tree( document_node,
            node_filter=node_filter, path_namer=path_namer )


class ZipDocumentArchiveNode(
        BaseDocumentArchiveNode, jeolm.node.archive.ZipArchiveNode ):
    pass

class TgzDocumentArchiveNode(
        BaseDocumentArchiveNode, jeolm.node.archive.TgzArchiveNode ):
    pass

