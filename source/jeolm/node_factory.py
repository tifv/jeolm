from string import Template
from functools import wraps
from itertools import chain
from contextlib import suppress

from pathlib import PurePosixPath

import jeolm
import jeolm.project
import jeolm.node
import jeolm.node.directory
import jeolm.node.symlink
import jeolm.node.latex
import jeolm.node.text
import jeolm.records
import jeolm.target

from jeolm.record_path import RecordPath
from jeolm.target import Target

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

    def __call__(self, targets, *, delegate=True, name='target'):
        if delegate:
            targets = [
                delegated_target.flags_clean_copy(origin='target')
                for delegated_target
                in self.driver.list_delegated_targets(
                    *targets, recursively=True )
            ]

        target_node = TargetNode(name=name)
        for target in targets:
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
        return target_node

# pylint: disable=protected-access

def _cache_node(key_function):
    """Decorator factory for NodeFactory classes methods."""
    def decorator(method):
        @wraps(method)
        def wrapper(self, *args, **kwargs):
            key = key_function(self, *args, **kwargs)
            try:
                return self._nodes[key]
            except KeyError:
                pass
            node = self._nodes[key] = method(self, *args, **kwargs)
            return node
        return wrapper
    return decorator

# pylint: enable=protected-access

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


class PackageNodeFactory:
    package_types = frozenset(('dtx', 'sty',))

    def __init__(self, *, project, driver,
        build_dir_node,
        source_node_factory
    ):
        self.project = project
        self.driver = driver
        self.build_dir_node = build_dir_node
        self.source_node_factory = source_node_factory

        self._nodes = dict()

    @property
    def build_dir(self):
        return self.build_dir_node.path

    def __call__(self, metapath, *, package_type=None):
        assert isinstance(metapath, RecordPath)
        return self._get_package_node(metapath, package_type=package_type)

    # pylint: disable=no-self-use,unused-argument,unused-variable
    def _package_node_key(self, metapath,
        *, package_type,
        package_records=None
    ):
        return metapath, package_type, 'sty'
    # pylint: enable=no-self-use,unused-argument,unused-variable

    @_cache_node(_package_node_key)
    def _get_package_node(self, metapath,
        *, package_type,
        package_records=None
    ):
        if package_records is None:
            package_records = self.driver.produce_package_records(metapath)
        package_types = set(package_records)
        if package_type is not None:
            if package_type not in package_types:
                raise ValueError( "Package {0} of type {1} is not available"
                    .format(metapath, package_type) )
            package_types = {package_type}
        assert package_types, (package_records, package_type)

        if package_type is None:
            for package_type in ('dtx', 'sty',):
                if package_type in package_types:
                    break
            else:
                raise ValueError( "Unable to determine package type "
                    "for package {}, given types {}"
                    .format(metapath, sorted(package_types)) )
            return self._get_package_node( metapath,
                package_type=package_type,
                package_records=package_records )
        elif package_type == 'dtx':
            get_package_node_method = self._get_package_node_dtx
        elif package_type == 'sty':
            get_package_node_method = self._get_package_node_proxy
        else:
            raise RuntimeError

        node = get_package_node_method( metapath,
            package_record=package_records[package_type] )
        if not hasattr(node, 'metapath'):
            node.metapath = metapath
        return node

    # pylint: disable=no-self-use,unused-argument,unused-variable
    def _metapath_build_dir_key(self, metapath):
        return metapath, 'dir', 'dir'
    # pylint: enable=no-self-use,unused-argument,unused-variable

    @_cache_node(_metapath_build_dir_key)
    def _get_metapath_build_dir(self, metapath):
        parent_dir_node = self.build_dir_node
        buildname = '-'.join(metapath.parts)
        assert '.' not in buildname
        return jeolm.node.directory.DirectoryNode(
                name='package:{}:dir'.format(metapath),
                path=parent_dir_node.path/buildname,
                needs=(parent_dir_node,) )

    # pylint: disable=no-self-use,unused-argument,unused-variable
    def _build_dir_key(self, metapath, *, package_type):
        return metapath, package_type, 'dir'
    # pylint: enable=no-self-use,unused-argument,unused-variable

    @_cache_node(_build_dir_key)
    def _get_build_dir(self, metapath, *, package_type):
        if package_type == 'dtx':
            parent_dir_node = self._get_metapath_build_dir(metapath)
            return jeolm.node.directory.BuildDirectoryNode(
                name = 'package:{}:{}:dir'.format(metapath, package_type),
                path=parent_dir_node.path/package_type,
                needs=(parent_dir_node,) )
        else:
            raise RuntimeError

    # pylint: disable=no-self-use,unused-argument,unused-variable
    def _output_dir_key(self, metapath, *, package_type):
        return metapath, package_type, 'output-dir'
    # pylint: enable=no-self-use,unused-argument,unused-variable

    @_cache_node(_output_dir_key)
    def _get_output_dir(self, metapath, *, package_type):
        if package_type == 'dtx':
            build_dir_node = self._get_build_dir( metapath,
                package_type=package_type )
            output_dir_node = jeolm.node.directory.DirectoryNode(
                name = 'package:{}:{}:output-dir'
                    .format(metapath, package_type),
                path=build_dir_node.path/'output',
                needs=(build_dir_node,) )
            build_dir_node.register_node(output_dir_node)
            return output_dir_node
        else:
            raise RuntimeError

    def _get_package_node_dtx(self, metapath, *, package_record):
        build_dir_node = self._get_build_dir( metapath,
            package_type='dtx' )
        build_dir = build_dir_node.path
        output_dir_node = self._get_output_dir( metapath,
            package_type='dtx' )
        output_dir = output_dir_node.path
        source_dtx_node = self.source_node_factory(
            package_record['source'] )
        package_name = package_record['name']
        dtx_node = jeolm.node.symlink.SymLinkedFileNode(
            name='package:{}:source:dtx'.format(metapath),
            source=source_dtx_node,
            path=build_dir/'{}.dtx'.format(package_name),
            needs=(build_dir_node,) )
        build_dir_node.register_node(dtx_node)
        ins_node = jeolm.node.text.TextNode(
            name='package:{}:source:ins'.format(metapath),
            path=build_dir/'package.ins',
            text=self._substitute_ins(package_name=package_name),
            build_dir_node=build_dir_node )
        build_dir_node.register_node(ins_node)
        sty_node = jeolm.node.ProductFileNode(
            name='package:{}:sty'.format(metapath),
            source=dtx_node,
            path=output_dir/'{}.sty'.format(package_name),
            needs=(ins_node, build_dir_node.pre_cleanup_node) )
        sty_node.set_subprocess_command(
            ( 'latex', '-interaction=nonstopmode', '-halt-on-error',
                '-output-directory={}'.format(
                    output_dir.relative_to(build_dir) ),
                ins_node.path.name ),
            cwd=build_dir_node.path )
        build_dir_node.post_check_node.append_needs(sty_node)
        sty_node = jeolm.node.symlink.ProxyFileNode(
            source=sty_node, name='{}:proxy'.format(sty_node.name),
            needs=(build_dir_node.post_check_node,) )
        return sty_node

    _ins_template = (
        r"\input docstrip.tex" '\n'
        r"\keepsilent" '\n'
        r"\askforoverwritefalse" '\n'
        r"\nopreamble" '\n'
        r"\nopostamble" '\n'
        r"\generate{"
            r"\file{$package_name.sty}"
                r"{\from{$package_name.dtx}{package}}"
        r"}" '\n'
        r"\endbatchfile" '\n'
        r"\endinput" '\n'
    )
    _substitute_ins = Template(_ins_template).substitute

    def _get_package_node_proxy(self, metapath, *, package_record):
        source_node = self.source_node_factory(package_record['source'])
        node = jeolm.node.symlink.ProxyFileNode(
            name='package:{}:sty'.format(metapath),
            source=source_node )
        return node


class FigureNodeFactory:
    figure_formats = frozenset((
        '<latex>', '<pdflatex>', '<xelatex>', '<lualatex>',
        'pdf', 'eps', 'png', 'jpg', ))
    figure_types = frozenset((
        None,
        'asy', 'svg', 'pdf', 'eps', 'png', 'jpg', ))
    flexible_figure_types = frozenset(('asy', 'svg',))

    def __init__(self, *, project, driver,
        build_dir_node,
        source_node_factory
    ):
        self.project = project
        self.driver = driver
        self.build_dir_node = build_dir_node
        self.source_node_factory = source_node_factory

        self._nodes = dict()

    @property
    def build_dir(self):
        return self.build_dir_node.path

    def __call__(self, metapath, *, figure_type, figure_format):
        assert isinstance(metapath, RecordPath)
        if figure_type not in self.figure_types:
            raise RuntimeError( "Unknown figure type {}"
                .format(figure_type) )
        if figure_format not in self.figure_formats:
            raise RuntimeError( "Unknown figure format {}"
                .format(figure_format) )
        return self._get_figure_node( metapath,
            figure_type=figure_type, figure_format=figure_format )

    # pylint: disable=no-self-use,unused-argument,unused-variable
    def _figure_node_key(self, metapath,
        *, figure_type, figure_format,
        figure_records=None
    ):
        return metapath, figure_type, figure_format
    # pylint: enable=no-self-use,unused-argument,unused-variable

    @_cache_node(_figure_node_key)
    def _get_figure_node(self, metapath,
        *, figure_type, figure_format,
        figure_records=None
    ):
        if figure_records is None:
            figure_records = self.driver.produce_figure_records(metapath)
        figure_types = set(figure_records)
        if figure_type is not None:
            if figure_type not in figure_types:
                raise ValueError( "Figure {0} of type {1} is not available"
                    .format(metapath, figure_type) )
            figure_types = {figure_type}
        assert figure_types, (figure_records, figure_type, figure_format)

        if figure_format in {
                '<latex>', '<pdflatex>', '<xelatex>', '<lualatex>' }:
            refined_figure_format = self._determine_figure_format(
                figure_types, figure_format )
            if refined_figure_format is None:
                raise ValueError( "Unable to determine figure format "
                    "for figure {}, given types {} and format {}"
                    .format(metapath, sorted(figure_types), figure_format) )
            return self._get_figure_node( metapath,
                figure_type=figure_type, figure_format=refined_figure_format,
                figure_records=figure_records )
        elif figure_format in {'pdf', 'eps', 'png', 'jpg'}:
            pass
        else:
            raise RuntimeError

        if figure_type is None:
            figure_type = self._determine_figure_type(
                figure_types, figure_format )
            if figure_type is None:
                raise ValueError( "Unable to determine figure type "
                    "for figure {}, given types {} and format {}"
                    .format(metapath, sorted(figure_types), figure_format) )
            return self._get_figure_node( metapath,
                figure_type=figure_type, figure_format=figure_format,
                figure_records=figure_records )
        else:
            if not self._check_figure_type(figure_type, figure_format):
                raise ValueError( "Incompatible figure type and format "
                    "for figure {}, given type {} and format {}"
                    .format(metapath, figure_type, figure_format) )

        if   figure_type == 'asy':
            get_figure_node_method = self._get_figure_node_asy
        elif figure_type == 'svg':
            get_figure_node_method = self._get_figure_node_svg
        elif figure_type in {'pdf', 'eps', 'png', 'jpg'}:
            get_figure_node_method = self._get_figure_node_proxy
        else:
            raise RuntimeError

        node = get_figure_node_method( metapath,
            figure_format=figure_format,
            figure_record=figure_records[figure_type] )
        if not hasattr(node, 'metapath'):
            node.metapath = metapath
        if not hasattr(node, 'figure_type'):
            node.figure_type = figure_type
        if not hasattr(node, 'figure_format'):
            node.figure_figure_format = figure_format
        return node

    @staticmethod
    def _determine_figure_format(figure_types, figure_format):
        if figure_format == '<latex>':
            return 'eps'
        elif figure_format in {'<pdflatex>', '<xelatex>', '<lualatex>'}:
            suggested_formats = set()
            if figure_types.intersection(('asy', 'svg', 'pdf',)):
                suggested_formats.add('pdf')
            if figure_types.intersection(('png',)):
                suggested_formats.add('png')
            if figure_types.intersection(('jpg',)):
                suggested_formats.add('jpg')
            if len(suggested_formats) != 1:
                return None
            figure_format, = suggested_formats
            return figure_format
        else:
            raise RuntimeError

    @staticmethod
    def _determine_figure_type(figure_types, figure_format):
        if figure_format in {'pdf', 'eps'}:
            for figure_type in ('asy', 'svg', figure_format):
                if figure_type in figure_types:
                    return figure_type
            return None
        elif figure_format in {'png', 'jpg'}:
            figure_type = figure_format
            if figure_type not in figure_types:
                return None
            return figure_type
        else:
            raise RuntimeError

    @staticmethod
    def _check_figure_type(figure_type, figure_format):
        if figure_type in {'asy', 'svg'}:
            if figure_format in {'pdf', 'eps'}:
                return True
            else:
                return False
        elif figure_type in {'pdf', 'eps', 'png', 'jpg'}:
            if figure_format == figure_type:
                return True
            else:
                return False
        else:
            raise RuntimeError

    # pylint: disable=no-self-use,unused-argument,unused-variable
    def _metapath_build_dir_key(self, metapath):
        return metapath, 'dir', 'dir'
    # pylint: enable=no-self-use,unused-argument,unused-variable

    @_cache_node(_metapath_build_dir_key)
    def _get_metapath_build_dir(self, metapath):
        parent_dir_node = self.build_dir_node
        buildname = '-'.join(metapath.parts)
        assert '.' not in buildname
        return jeolm.node.directory.DirectoryNode(
            name='figure:{}:dir'.format(metapath),
            path=parent_dir_node.path/buildname,
            needs=(parent_dir_node,) )

    # pylint: disable=no-self-use,unused-argument,unused-variable
    def _build_dir_key(self, metapath, *, figure_type):
        return metapath, figure_type, 'dir'
    # pylint: enable=no-self-use,unused-argument,unused-variable

    @_cache_node(_build_dir_key)
    def _get_build_dir(self, metapath, *, figure_type):
        if figure_type in {'asy', 'svg'}:
            parent_dir_node = self._get_metapath_build_dir(metapath)
            return jeolm.node.directory.BuildDirectoryNode(
                name = 'figure:{}:{}:dir'.format(metapath, figure_type),
                path=parent_dir_node.path/figure_type,
                needs=(parent_dir_node,) )
        else:
            raise RuntimeError

    # pylint: disable=no-self-use,unused-argument,unused-variable
    def _output_dir_key(self, metapath, *, figure_type):
        return metapath, figure_type, 'output-dir'
    # pylint: enable=no-self-use,unused-argument,unused-variable

    @_cache_node(_output_dir_key)
    def _get_output_dir(self, metapath, *, figure_type):
        if figure_type in {'asy', 'svg'}:
            build_dir_node = self._get_build_dir( metapath,
                figure_type=figure_type )
            output_dir_node = jeolm.node.directory.DirectoryNode(
                name = 'figure:{}:{}:output-dir'
                    .format(metapath, figure_type),
                path=build_dir_node.path/'output',
                needs=(build_dir_node,) )
            build_dir_node.register_node(output_dir_node)
            return output_dir_node
        else:
            raise RuntimeError

    _main_file_names = {'pdf' : 'Main.pdf', 'eps' : 'Main.eps'}

    def _get_figure_node_asy( self, metapath,
        *, figure_format, figure_record
    ):
        build_dir_node = self._get_build_dir( metapath,
            figure_type='asy' )
        build_dir = build_dir_node.path
        output_dir_node = self._get_output_dir( metapath,
            figure_type='asy' )
        output_dir = output_dir_node.path
        main_asy_node = self._get_figure_node_asy_source( metapath,
            figure_record=figure_record )
        other_asy_nodes = main_asy_node.other_asy_nodes
        assert main_asy_node.path.parent == build_dir
        figure_node = jeolm.node.ProductFileNode(
            name='figure:{}:asy:{}'.format(metapath, figure_format),
            source=main_asy_node,
            path=output_dir/self._main_file_names[figure_format],
            needs=chain(
                (build_dir_node.pre_cleanup_node, output_dir_node),
                other_asy_nodes )
        )
        figure_node.set_subprocess_command(
            ( 'asy', '-outformat={}'.format(figure_format), '-offscreen',
                main_asy_node.path.name,
                '-outname={}'.format(
                    figure_node.path.relative_to(build_dir) ),
            ),
            cwd=build_dir_node.path )
        build_dir_node.post_check_node.append_needs(figure_node)
        figure_node = jeolm.node.symlink.ProxyFileNode(
            source=figure_node, name='{}:proxy'.format(figure_node.name),
            needs=(build_dir_node.post_check_node,) )
        return figure_node

    # pylint: disable=no-self-use,unused-argument,unused-variable
    def _figure_node_asy_source_key(self, metapath, *, figure_record):
        return metapath, 'asy', 'asy'
    # pylint: enable=no-self-use,unused-argument,unused-variable

    @_cache_node(_figure_node_asy_source_key)
    def _get_figure_node_asy_source(self, metapath, *, figure_record):
        build_dir_node = self._get_build_dir( metapath,
            figure_type='asy' )
        main_asy_node = jeolm.node.symlink.SymLinkedFileNode(
            name='figure:{}:asy:source:main'.format(metapath),
            source=self.source_node_factory(figure_record['source']),
            path=build_dir_node.path/'Main.asy',
            needs=(build_dir_node,) )
        build_dir_node.register_node(main_asy_node)
        other_asy_nodes = main_asy_node.other_asy_nodes = list()
        for accessed_name, inpath in figure_record['other_sources'].items():
            if accessed_name == 'Main.asy':
                raise ValueError(
                    "Cannot symlink non-main asy file as Main.asy: "
                    "{} wants to access {}"
                    .format(metapath, inpath) )
            asy_node = jeolm.node.symlink.SymLinkedFileNode(
                name='figure:{}:asy:source:{}'.format(metapath, accessed_name),
                source=self.source_node_factory(inpath),
                path=build_dir_node.path/accessed_name,
                needs=(build_dir_node,) )
            other_asy_nodes.append(asy_node)
            build_dir_node.register_node(asy_node)
        return main_asy_node

    def _get_figure_node_svg( self, metapath,
        *, figure_format, figure_record
    ):
        build_dir_node = self._get_build_dir( metapath,
            figure_type='svg' )
        build_dir = build_dir_node.path
        output_dir_node = self._get_output_dir( metapath,
            figure_type='svg' )
        output_dir = output_dir_node.path
        svg_node = self._get_figure_node_svg_source( metapath,
            figure_record=figure_record )
        assert svg_node.path.parent == build_dir
        figure_node = jeolm.node.ProductFileNode(
            name='figure:{}:svg:{}'.format(metapath, figure_format),
            source=svg_node,
            path=output_dir/self._main_file_names[figure_format],
            needs=(build_dir_node.pre_cleanup_node, output_dir_node)
        )
        figure_node.set_subprocess_command(
            ( 'inkscape', '--without-gui',
                '--export-{}={}'.format(
                    figure_format,
                    figure_node.path.relative_to(build_dir) ),
                svg_node.path.name
            ),
            cwd=build_dir_node.path )
        build_dir_node.post_check_node.append_needs(figure_node)
        figure_node = jeolm.node.symlink.ProxyFileNode(
            source=figure_node, name='{}:proxy'.format(figure_node.name),
            needs=(build_dir_node.post_check_node,) )
        return figure_node

    # pylint: disable=no-self-use,unused-argument,unused-variable
    def _figure_node_svg_source_key(self, metapath, *, figure_record):
        return metapath, 'svg', 'svg'
    # pylint: enable=no-self-use,unused-argument,unused-variable

    @_cache_node(_figure_node_svg_source_key)
    def _get_figure_node_svg_source(self, metapath, *, figure_record):
        build_dir_node = self._get_build_dir( metapath,
            figure_type='svg' )
        source_svg_node = jeolm.node.symlink.SymLinkedFileNode(
            name='figure:{}:svg:source'.format(metapath),
            source=self.source_node_factory(figure_record['source']),
            path=build_dir_node.path/'Main.svg',
            needs=(build_dir_node,) )
        build_dir_node.register_node(source_svg_node)
        return source_svg_node

    def _get_figure_node_proxy( self, metapath,
        *, figure_format, figure_record
    ):
        source_node = self.source_node_factory(figure_record['source'])
        node = jeolm.node.symlink.ProxyFileNode(
            name='figure:{}:{}'.format(metapath, figure_format),
            source=source_node )
        return node


class SourceNodeFactory:

    def __init__(self, *, project):
        self.project = project
        self.nodes = dict()

    def __call__(self, inpath):
        assert isinstance(inpath, PurePosixPath), type(inpath)
        assert not inpath.is_absolute(), inpath
        with suppress(KeyError):
            return self.nodes[inpath]
        node = self.nodes[inpath] = self._prebuild_source(inpath)
        return node

    def _prebuild_source(self, inpath):
        source_node = jeolm.node.SourceFileNode(
            name='source:{}'.format(inpath),
            path=self.project.source_dir/inpath )
        if not source_node.path.exists():
            logger.warning(
                "Requested source node <YELLOW>%(inpath)s<NOCOLOUR> "
                    "does not exist as file",
                dict(inpath=inpath) )
        return source_node

