from itertools import chain

import jeolm.node
import jeolm.node.directory
import jeolm.node.symlink
import jeolm.node.text
import jeolm.node.latex

from jeolm.record_path import RecordPath
from jeolm.target import Target

from . import _cache_node

import logging
logger = logging.getLogger(__name__)


class DocumentNode(jeolm.node.FileNode):
    pass

class DocumentNodeFactory:

    document_types = ('regular', 'standalone', 'latexdoc')

    class _LaTeXDocumentNode(jeolm.node.latex.LaTeXPDFNode, DocumentNode):
        pass

    class _PdfLaTeXDocumentNode(jeolm.node.latex.PdfLaTeXNode, DocumentNode):
        pass

    class _XeLaTeXDocumentNode(jeolm.node.latex.XeLaTeXNode, DocumentNode):
        pass

    class _LuaLaTeXDocumentNode(jeolm.node.latex.LuaLaTeXNode, DocumentNode):
        pass

    _document_node_classes = {
        'latex' : _LaTeXDocumentNode,
        'pdflatex' : _PdfLaTeXDocumentNode,
        'xelatex' : _XeLaTeXDocumentNode,
        'lualatex' : _LuaLaTeXDocumentNode,
    }

    class _ProxyDocumentNode(jeolm.node.symlink.ProxyFileNode, DocumentNode):
        pass

    def __init__(self, *, project, driver,
        build_dir_node,
        source_node_factory, package_node_factory, figure_node_factory
    ):
        self.project = project
        self.driver = driver
        self.build_dir_node = build_dir_node
        self.source_node_factory = source_node_factory
        self.package_node_factory = package_node_factory
        self.figure_node_factory = figure_node_factory

        self._nodes = dict()

    @property
    def build_dir(self):
        return self.build_dir_node.path

    def __call__(self, target):
        assert isinstance(target, Target), type(target)
        return self._get_document_node(target)

    # pylint: disable=no-self-use
    def _document_node_key(self, target):
        return target, 'pdf'
    # pylint: enable=no-self-use

    @_cache_node(_document_node_key)
    def _get_document_node(self, target):
        recipe = self.driver.produce_outrecord(target)
        build_dir_node = self._get_build_dir(target, recipe)
        output_dir_node = jeolm.node.directory.DirectoryNode(
            name='document:{}:output:dir'.format(target),
            path=build_dir_node.path/'output',
            needs=(build_dir_node,) )
        build_dir_node.register_node(output_dir_node)
        document_type = recipe['type']
        if document_type == 'regular':
            prebuild_method = self._prebuild_regular
        else:
            raise RuntimeError
        main_source_node, source_nodes, package_nodes, figure_nodes = \
            prebuild_method( target, recipe,
                build_dir_node=build_dir_node )
        document_node_class = self._document_node_classes[recipe['compiler']]
        document_node = document_node_class(
            name='document:{}:output'.format(target),
            source=main_source_node, jobname='Main',
            build_dir_node=build_dir_node, output_dir_node=output_dir_node,
            figure_nodes=figure_nodes,
            needs=chain(source_nodes, package_nodes),
        )
        build_dir_node.post_check_node.append_needs(document_node)
        document_node = self._ProxyDocumentNode(
            source=document_node, name='{}:proxy'.format(document_node.name),
            needs=(build_dir_node.post_check_node,), )
        # pylint: disable=attribute-defined-outside-init
        document_node.figure_nodes = figure_nodes
        document_node.build_dir_node = build_dir_node
        document_node.outname = recipe['outname']
        # pylint: enable=attribute-defined-outside-init
        return document_node

    # pylint: disable=no-self-use
    def _metapath_build_dir_key(self, metapath):
        return metapath, 'metapath-dir'
    # pylint: enable=no-self-use

    @_cache_node(_metapath_build_dir_key)
    def _get_metapath_build_dir(self, metapath):
        assert isinstance(metapath, RecordPath)
        parent_dir_node = self.build_dir_node
        buildname = '-'.join(metapath.parts)
        assert '.' not in buildname
        return jeolm.node.directory.DirectoryNode(
            name='document:{}:metapath-dir'.format(metapath),
            path=parent_dir_node.path/buildname,
            needs=(parent_dir_node,) )

    # pylint: disable=no-self-use
    def _target_build_dir_key(self, target):
        return target, 'target-dir'
    # pylint: enable=no-self-use

    @_cache_node(_target_build_dir_key)
    def _get_target_build_dir(self, target):
        assert isinstance(target, Target)
        parent_dir_node = self._get_metapath_build_dir(target.path)
        buildname = ','.join(sorted(target.flags.as_frozenset))
        assert buildname != '0,'
        if buildname == '0':
            buildname = '0,'
        elif not buildname:
            buildname = '0'
        assert '.' not in buildname
        return jeolm.node.directory.DirectoryNode(
            name='document:{}:target-dir'.format(target),
            path=parent_dir_node.path/buildname,
            needs=(parent_dir_node,) )

    # pylint: disable=no-self-use,unused-argument,unused-variable
    def _build_dir_key(self, target, recipe):
        return target, 'dir'
    # pylint: enable=no-self-use,unused-argument,unused-variable

    @_cache_node(_build_dir_key)
    def _get_build_dir(self, target, recipe):
        assert isinstance(target, Target)
        parent_dir_node = self._get_target_build_dir(target)
        buildname = recipe['compiler']
        assert '.' not in buildname
        return jeolm.node.directory.BuildDirectoryNode(
            name='document:{}:dir'.format(target),
            path=parent_dir_node.path/buildname,
            needs=(parent_dir_node,) )

    def _prebuild_regular(self, target, recipe, *, build_dir_node):
        """
        Prebuild all necessary for building a document.

        Return (
            main_source_node, source_nodes,
            package_nodes, figure_nodes ).
        """
        build_dir = build_dir_node.path
        main_source_node = jeolm.node.text.TextNode(
            name='document:{}:source:main'.format(target),
            path=build_dir/'Main.tex',
            text=recipe['document'],
            build_dir_node=build_dir_node )
        build_dir_node.register_node(main_source_node)

        source_nodes = list()
        for alias, inpath in recipe['sources'].items():
            source_node = jeolm.node.symlink.SymLinkedFileNode(
                name='document:{}:source:{}'.format(target, alias),
                source=self.source_node_factory(inpath),
                path=build_dir/alias,
                needs=(build_dir_node,)
            )
            source_nodes.append(source_node)
            build_dir_node.register_node(source_node)

        return (
            main_source_node, source_nodes,
            self._prebuild_regular_packages( target, recipe,
                build_dir_node=build_dir_node ),
            self._prebuild_regular_figures( target, recipe,
                build_dir_node=build_dir_node ),
        )

    def _prebuild_regular_packages( self, target, recipe,
        *, build_dir_node
    ):
        build_dir = build_dir_node.path
        package_nodes = list()
        for package_name, package_path in recipe['package_paths'].items():
            package_node = jeolm.node.symlink.SymLinkedFileNode(
                name='document:{}:package:{}'.format(target, package_name),
                source=self.package_node_factory(package_path),
                path=(build_dir/package_name).with_suffix('.sty'),
                needs=(build_dir_node,)
            )
            package_nodes.append(package_node)
            build_dir_node.register_node(package_node)
        return package_nodes

    def _prebuild_regular_figures( self, target, recipe,
        *, build_dir_node
    ):
        build_dir = build_dir_node.path
        figure_nodes = list()
        compiler = recipe['compiler']
        for alias_stem, (figure_path, figure_type) in (
                recipe['figures'].items() ):
            figure_node = self.figure_node_factory( figure_path,
                figure_type=figure_type,
                figure_format='<{}>'.format(compiler) )
            figure_suffix = figure_node.path.suffix
            assert figure_suffix in {'.pdf', '.eps', '.png', '.jpg'}
            figure_node = jeolm.node.symlink.SymLinkedFileNode(
                name='document:{}:figure:{}'.format(target, alias_stem),
                source=figure_node,
                path=(build_dir/alias_stem).with_suffix(figure_suffix),
                needs=(build_dir_node,)
            )
            figure_nodes.append(figure_node)
            build_dir_node.register_node(figure_node)
        return figure_nodes



