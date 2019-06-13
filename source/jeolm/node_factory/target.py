import jeolm.node
import jeolm.node.directory
import jeolm.node.symlink
from jeolm.utils.unique import unique

from .source import SourceNodeFactory
from .figure import FigureNodeFactory
from .package import PackageNodeFactory
from .document import DocumentNodeFactory

import logging
logger = logging.getLogger(__name__)

import typing
from typing import Type
if typing.TYPE_CHECKING:
    from .archive import BaseDocumentArchiveNode

class TargetNode(jeolm.node.Node):
    pass

class TargetNodeFactory:

    def __init__(self, *, project, driver):
        self.project = project
        self.driver = driver

        self.source_node_factory = SourceNodeFactory(project=self.project)
        self.figure_node_factory = FigureNodeFactory(
            project=self.project, driver=self.driver,
            build_dir_node=jeolm.node.directory.DirectoryNode(
                name='figure:dir',
                path=self.project.build_dir/'figures', parents=True ),
            source_node_factory=self.source_node_factory,
        )
        self.package_node_factory = PackageNodeFactory(
            project=self.project, driver=self.driver,
            build_dir_node=jeolm.node.directory.DirectoryNode(
                name='package:dir',
                path=self.project.build_dir/'packages', parents=True ),
            source_node_factory=self.source_node_factory,
        )
        self.document_node_factory = DocumentNodeFactory(
            project=self.project, driver=self.driver,
            build_dir_node=jeolm.node.directory.DirectoryNode(
                name='document:dir',
                path=self.project.build_dir/'documents', parents=True ),
            source_node_factory=self.source_node_factory,
            package_node_factory=self.package_node_factory,
            figure_node_factory=self.figure_node_factory,
        )

    def __call__( self, targets, *,
        delegate=True, archive=None, name='target'
    ):
        if delegate:
            targets = [
                delegated_target.flags_clean_copy(origin='target')
                for delegated_target
                in self.driver.list_delegated_targets(*targets)
            ]

        target_node = TargetNode(name=name)
        for target in unique(targets):
            document_node = self.document_node_factory(target)
            outname = document_node.outname
            assert '/' not in outname
            exposed_node = jeolm.node.symlink.SymLinkedFileNode(
                name='document:{}:exposed'.format(target),
                source=document_node,
                path=(self.project.root/outname).with_suffix(
                    document_node.path.suffix )
            )
            target_node.append_needs(exposed_node)
            if archive is not None:
                archive_node = self._get_archive_node( target,
                    document_node, archive_type=archive )
                target_node.append_needs(archive_node)
        return target_node

    def _get_archive_node( self, target, document_node, archive_type
    ) -> 'BaseDocumentArchiveNode':
        archive_node_class: Type['BaseDocumentArchiveNode']
        if archive_type == 'zip':
            from .archive import ZipDocumentArchiveNode
            archive_node_class = ZipDocumentArchiveNode
        elif archive_type == 'tgz':
            from .archive import TgzDocumentArchiveNode
            archive_node_class = TgzDocumentArchiveNode
        else:
            raise RuntimeError(archive_type)
        archive_node = archive_node_class(
            document_node=document_node, source_dir=self.project.source_dir,
            name="document:{}:archive".format(target),
            path=(self.project.root/document_node.outname).with_suffix(
                archive_node_class.default_suffix )
        )
        return archive_node

