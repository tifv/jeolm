from pathlib import Path, PurePosixPath

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
                raise RuntimeError("XXX") # XXX
#                archive_node = self._get_archive_node( target,
#                    document_node, archive_type=archive )
#                target_node.append_needs(archive_node)
        return target_node

#    def _get_archive_node(self, target, document_node, archive_type):
#        if archive_type == 'zip':
#            from jeolm.node.archive import ZipArchiveNode as ArchiveNode
#        elif archive_type == 'tgz':
#            from jeolm.node.archive import TgzArchiveNode as ArchiveNode
#        else:
#            raise RuntimeError(archive_type)
#        # XXX maybe we should just pack source/ and figures/ directories
#        # from builddir
#        archive_node = ArchiveNode(
#            name="document:{}:archive".format(target),
#            path=(self.project.root/document_node.outname).with_suffix(
#                ArchiveNode.default_suffix )
#        )
#        source_dir = self.project.source_dir
#        style_dir = source_dir / '_style'
#        archive_node.archive_add_dir( PurePosixPath('.'),
#            document_node, source_dir,
#            node_filter=lambda node: style_dir not in node.path.parents,
#            path_namer=lambda node: '-'.join(node.path.relative_to(source_dir).parts),
#        )
#        return archive_node

