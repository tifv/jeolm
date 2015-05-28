from string import Template
from functools import wraps
from itertools import chain
from contextlib import suppress

import hashlib

from pathlib import PurePosixPath

import jeolm
import jeolm.local
import jeolm.node
import jeolm.node.directory
import jeolm.node.symlink
import jeolm.node.latex
import jeolm.records
import jeolm.target

from jeolm.record_path import RecordPath

import logging
logger = logging.getLogger(__name__)


class TargetNode(jeolm.node.Node):
    pass

class TargetNodeFactory:

    def __init__(self, *, local, driver, text_node_shelf):
        self.local = local
        self.text_node_shelf = text_node_shelf
        self.driver = driver

        self.source_node_factory = SourceNodeFactory(local=self.local)
        self.figure_node_factory = FigureNodeFactory(
            local=self.local, driver=self.driver,
            build_dir_node=jeolm.node.directory.DirectoryNode(
                name='figure:dir',
                path=self.local.build_dir/'figures', parents=True ),
            source_node_factory=self.source_node_factory,
        )
        self.package_node_factory = PackageNodeFactory(
            local=self.local, driver=self.driver,
            build_dir_node=jeolm.node.directory.DirectoryNode(
                name='package:dir',
                path=self.local.build_dir/'packages', parents=True ),
            source_node_factory=self.source_node_factory,
            text_node_shelf=self.text_node_shelf,
        )
        self.document_node_factory = DocumentNodeFactory(
            local=self.local, driver=self.driver,
            build_dir_node=jeolm.node.directory.DirectoryNode(
                name='document:dir',
                path=self.local.build_dir/'documents', parents=True ),
            source_node_factory=self.source_node_factory,
            package_node_factory=self.package_node_factory,
            figure_node_factory=self.figure_node_factory,
            text_node_shelf=self.text_node_shelf,
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
                path=(self.local.root/outname).with_suffix(
                    document_node.path.suffix )
            )
            target_node.append_needs(exposed_node)
        return target_node


class DocumentNode(jeolm.node.FileNode):
    pass

class DocumentNodeFactory:
    document_types = ('regular', 'standalone', 'latexdoc')

    class _DocumentNode(DocumentNode, jeolm.node.latex.DVI2PDFNode):
        pass

    def __init__(self, *, local, driver,
        build_dir_node,
        source_node_factory, package_node_factory, figure_node_factory,
        text_node_shelf
    ):
        self.local = local
        self.driver = driver
        self.build_dir_node = build_dir_node
        self.source_node_factory = source_node_factory
        self.package_node_factory = package_node_factory
        self.figure_node_factory = figure_node_factory
        self.text_node_shelf = text_node_shelf

        self.nodes = dict()

    @property
    def build_dir(self):
        return self.build_dir_node.path

    def __call__(self, target):
        assert isinstance(target, jeolm.target.Target), type(target)
        try:
            node = self.nodes[target]
        except KeyError:
            node = None
        if node is None:
            node = self.nodes[target] = self._prebuild_document(target)
        assert hasattr(node, 'outname'), node
        return node

    def _prebuild_document(self, target):
        recipe = self.driver.produce_outrecord(target)
        buildname = recipe['buildname']
        assert '/' not in buildname
        build_subdir = self.build_dir / buildname
        build_subdir_node = jeolm.node.directory.DirectoryNode(
            name='document:{}:dir'.format(target),
            path=build_subdir, parents=False,
            needs=(self.build_dir_node,) )
        document_type = recipe['type']
        if document_type not in self.document_types:
            raise RuntimeError(document_type, target)
        if document_type == 'regular':
            prebuild_dvi_method = self._prebuild_dvi_regular
        elif document_type == 'standalone':
            prebuild_dvi_method = self._prebuild_dvi_standalone
        elif document_type == 'latexdoc':
            prebuild_dvi_method = self._prebuild_dvi_latexdoc
        if recipe['compiler'] != 'latex':
            raise ValueError("No compilers except 'latex' are supported yet")
        dvi_node = prebuild_dvi_method( target, recipe,
            build_dir=build_subdir, build_dir_node=build_subdir_node )
        pdf_node = self._prebuild_pdf( target, recipe, dvi_node,
            build_dir=build_subdir, build_dir_node=build_subdir_node )
        return pdf_node

    def _prebuild_dvi_regular(self, target, recipe,
        *, build_dir, build_dir_node
    ):
        compiler = recipe['compiler']
        main_tex_node = TextNode(
            name='document:{}:source:main'.format(target),
            path=build_dir/'Main.tex',
            needs=(build_dir_node,),
            text_node_shelf=self.text_node_shelf,
            local=self.local )
        main_tex_node.set_command(jeolm.node.WriteTextCommand(
            main_tex_node, text=recipe['document'] ))

        package_nodes = [
            jeolm.node.symlink.SymLinkedFileNode(
                name='document:{}:package:{}'.format(target, alias_name),
                source=self.package_node_factory(package_path),
                path=(build_dir/alias_name).with_suffix('.sty'),
                needs=(build_dir_node,) )
            for alias_name, package_path
            in recipe['package_paths'].items() ]
        figure_nodes = [
            jeolm.node.symlink.SymLinkedFileNode(
                name='document:{}:figure:{}'.format(target, alias_name),
                source=self.figure_node_factory( figure_path,
                    figure_type=figure_type,
                    figure_format='<{}>'.format(compiler) ),
                path=(build_dir/alias_name).with_suffix('.eps'),
                needs=(build_dir_node,) )
            for alias_name, (figure_path, figure_type)
            in recipe['figures'].items() ]
        source_nodes = [
            jeolm.node.symlink.SymLinkedFileNode(
                name='document:{}:source:{}'.format(target, alias),
                source=self.source_node_factory(inpath),
                path=build_dir/alias,
                needs=(build_dir_node,) )
            for alias, inpath in recipe['sources'].items() ]

        if compiler != 'latex':
            raise RuntimeError
        dvi_node = jeolm.node.latex.LaTeXNode(
            name='document:{}:dvi'.format(target),
            source=main_tex_node,
            path=build_dir/'Main.dvi',
            needs=chain( package_nodes, source_nodes, figure_nodes,
                (build_dir_node,) )
        )
        dvi_node.figure_nodes = figure_nodes
        dvi_node.build_dir_node = build_dir_node
        return dvi_node

    def _prebuild_dvi_standalone(self, target, recipe,
        *, build_dir, build_dir_node
    ):
        source_node = self.source_node_factory(recipe['source'])
        tex_node = jeolm.node.symlink.SymLinkedFileNode(
            name='document:{}:source:main'.format(target),
            source=source_node, path=build_dir/'Main.tex',
            needs=(build_dir_node,) )
        dvi_node = jeolm.node.latex.LaTeXNode(
            name='document:{}:dvi'.format(target),
            source=tex_node, path=build_dir/'Main.dvi',
            needs=(build_dir_node,) )
        dvi_node.figure_nodes = []
        dvi_node.build_dir_node = build_dir_node
        return dvi_node

    def _prebuild_dvi_latexdoc(self, target, recipe,
        *, build_dir, build_dir_node
    ):
        package_name = recipe['name']

        source_node = self.source_node_factory(recipe['source'])
        dtx_node = jeolm.node.symlink.SymLinkedFileNode(
            name='document:{}:source:dtx'.format(target),
            source=source_node,
            path=build_dir/'{}.dtx'.format(package_name),
            needs=(build_dir_node,) )
        ins_node = TextNode(
            name='document:{}:source:ins'.format(target),
            path=build_dir/'driver.ins',
            needs=(build_dir_node,),
            text_node_shelf=self.text_node_shelf,
            local=self.local )
        ins_node.set_command(jeolm.node.WriteTextCommand( ins_node,
            self._substitute_driver_ins(package_name=package_name) ))
        drv_node = jeolm.node.ProductFileNode(
            name='document:{}:source:drv'.format(target),
            source=dtx_node,
            path=build_dir/'{}.drv'.format(package_name),
            needs=(ins_node,) )
        drv_node.set_subprocess_command(
            ( 'latex', '-interaction=nonstopmode', '-halt-on-error',
                ins_node.path.name ),
            cwd=build_dir )
        sty_node = jeolm.node.symlink.SymLinkedFileNode(
            name='document:{}:package'.format(target),
            source=self.package_node_factory(target.path),
            path=(build_dir/package_name).with_suffix('.sty'),
            needs=(build_dir_node,) )

        dvi_node = jeolm.node.latex.LaTeXNode(
            name='document:{}:dvi'.format(target),
            source=drv_node,
            path=build_dir/'Main.dvi',
            needs=(sty_node, dtx_node, build_dir_node,) )
        dvi_node.figure_nodes = []
        dvi_node.build_dir_node = build_dir_node
        return dvi_node

    _driver_ins_template = (
        r"\input docstrip.tex" '\n'
        r"\keepsilent" '\n'
        r"\askforoverwritefalse" '\n'
        r"\nopreamble" '\n'
        r"\nopostamble" '\n'
        r"\generate{"
            r"\file{$package_name.drv}"
                r"{\from{$package_name.dtx}{driver}}"
        r"}" '\n'
        r"\endbatchfile" '\n'
        r"\endinput"
    )
    _substitute_driver_ins = Template(_driver_ins_template).substitute

    def _prebuild_pdf(self, target, recipe, dvi_node, *,
        build_dir, build_dir_node
    ):
        pdf_node = self._DocumentNode(
            name='document:{}:pdf'.format(target),
            source=dvi_node, path=build_dir/'Main.pdf',
            needs=chain(dvi_node.figure_nodes, (build_dir_node,))
        )
        # pylint: disable=attribute-defined-outside-init
        pdf_node.figure_nodes = dvi_node.figure_nodes
        pdf_node.build_dir_node = build_dir_node
        pdf_node.outname = recipe['outname']
        # pylint: enable=attribute-defined-outside-init
        return pdf_node


class PackageNodeFactory:

    def __init__(self, *, local, driver,
        build_dir_node,
        source_node_factory, text_node_shelf
    ):
        self.local = local
        self.driver = driver
        self.build_dir_node = build_dir_node
        self.source_node_factory = source_node_factory
        self.text_node_shelf = text_node_shelf

        self.nodes = dict()

    def __call__(self, metapath):
        assert isinstance(metapath, RecordPath), type(metapath)
        try:
            node = self.nodes[metapath]
        except KeyError:
            node = None
        if node is None:
            node = self.nodes[metapath] = self._prebuild_package(metapath)
        return node

    def _prebuild_package(self, metapath):
        package_record = self.driver.produce_package_record(metapath)
        buildname = package_record['buildname']
        assert '/' not in buildname
        build_subdir = self.build_dir_node.path / buildname
        build_subdir_node = jeolm.node.directory.DirectoryNode(
            name='package:{}:dir'.format(metapath),
            path=build_subdir, parents=False,
            needs=(self.build_dir_node,) )
        source_package_format = package_record['source_format']
        if source_package_format == 'dtx':
            prebuild_sty_method = self._prebuild_dtx_package
        elif source_package_format == 'sty':
            prebuild_sty_method = self._prebuild_sty_package
        else:
            raise RuntimeError(source_package_format, metapath)
        return prebuild_sty_method( metapath, package_record,
            build_dir_node=build_subdir_node )

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
        r"\endinput" )
    _substitute_ins = Template(_ins_template).substitute

    def _prebuild_dtx_package(self, metapath, package_record,
        *, build_dir_node
    ):
        build_dir = build_dir_node.path
        assert build_dir.is_absolute()
        source_node = self.source_node_factory(
            package_record['source'] )
        package_name = package_record['name']
        dtx_node = jeolm.node.symlink.SymLinkedFileNode(
            name='package:{}:source:dtx'.format(metapath),
            source=source_node,
            path=build_dir/'{}.dtx'.format(package_name),
            needs=(build_dir_node,) )
        ins_node = TextNode(
            name='package:{}:source:ins'.format(metapath),
            path=build_dir/'package.ins',
            needs=(build_dir_node,),
            text_node_shelf=self.text_node_shelf,
            local=self.local )
        ins_node.set_command(jeolm.node.WriteTextCommand( ins_node,
            self._substitute_ins(package_name=package_name) ))
        sty_node = jeolm.node.ProductFileNode(
            name='package:{}:sty'.format(metapath),
            source=dtx_node,
            path=build_dir/'{}.sty'.format(package_name),
            needs=(ins_node,) )
        sty_node.set_subprocess_command(
            ( 'latex', '-interaction=nonstopmode', '-halt-on-error',
                ins_node.path.name ),
            cwd=build_dir )
        return sty_node

    # pylint: disable=unused-argument,unused-variable

    def _prebuild_sty_package(self, metapath, package_record,
        *, build_dir_node
    ):
        return self.source_node_factory(package_record['source'])

    # pylint: enable=unused-argument,unused-variable

# pylint: disable=protected-access

def _cache_figure_node(figure_type=None, figure_format=None):
    """Decorator factory for methods of FigureNodeFactory."""
    if figure_type is None and figure_format is None:
        def decorator(method):
            @wraps(method)
            def wrapper(self, metapath,
                *, figure_type, figure_format, **kwargs
            ):
                try:
                    return self._nodes[metapath, figure_type, figure_format]
                except KeyError:
                    pass
                node = method( self, metapath,
                    figure_type=figure_type, figure_format=figure_format,
                    **kwargs )
                self._nodes[metapath, figure_type, figure_format] = node
                return node
            return wrapper
    elif figure_format is None:
        def decorator(method, figure_type=figure_type):
            @wraps(method)
            def wrapper(self, metapath,
                *, figure_format, **kwargs
            ):
                try:
                    return self._nodes[metapath, figure_type, figure_format]
                except KeyError:
                    pass
                node = method( self, metapath,
                    figure_format=figure_format, **kwargs )
                self._nodes[metapath, figure_type, figure_format] = node
                return node
            return wrapper
    elif figure_type is None:
        def decorator(method, figure_format=figure_format):
            @wraps(method)
            def wrapper(self, metapath,
                *, figure_type, **kwargs
            ):
                try:
                    return self._nodes[metapath, figure_type, figure_format]
                except KeyError:
                    pass
                node = method( self, metapath,
                    figure_type=figure_type, **kwargs )
                self._nodes[metapath, figure_type, figure_format] = node
                return node
            return wrapper
    else:
        def decorator(method,
            figure_type=figure_type, figure_format=figure_format
        ):
            @wraps(method)
            def wrapper(self, metapath, **kwargs):
                try:
                    return self._nodes[metapath, figure_type, figure_format]
                except KeyError:
                    pass
                node = method(self, metapath, **kwargs)
                self._nodes[metapath, figure_type, figure_format] = node
                return node
            return wrapper
    return decorator

# pylint: enable=protected-access

class FigureNodeFactory:
    figure_formats = frozenset((
        '<latex>', '<pdflatex>', '<xelatex>', '<lualatex>',
        'pdf', 'eps', 'png', 'jpg', ))
    figure_types = frozenset((
        None,
        'asy', 'svg', 'pdf', 'eps', 'png', 'jpg', ))

    def __init__(self, *, local, driver,
        build_dir_node,
        source_node_factory
    ):
        self.local = local
        self.driver = driver
        self.build_dir_node = build_dir_node
        self.source_node_factory = source_node_factory

        self._nodes = dict()

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

    @_cache_figure_node()
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
            figure_format = self._determine_figure_format(
                figure_types, figure_format )
            if figure_format is None:
                raise ValueError( "Unable to determine figure format "
                    "for figure {}, given types {} and format {}"
                    .format(metapath, sorted(figure_types), figure_format) )
            return self._get_figure_node( metapath,
                figure_type=figure_type, figure_format=figure_format,
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
            get_figure_node_method = self._get_figure_node_symlink

        node = get_figure_node_method( metapath,
            figure_format=figure_format,
            figure_record=figure_records[figure_type] )
        if not hasattr(node, 'metapath'):
            node.metapath = metapath
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

    @_cache_figure_node(figure_format='dir')
    def _get_figure_node_dir(self, metapath, *, figure_type):
        if figure_type == 'dir':
            parent_dir_node = self.build_dir_node
            buildname = '-'.join(metapath.parts)
            assert '.' not in buildname
            return jeolm.node.directory.DirectoryNode(
                    name='figure:{}:dir'.format(metapath),
                    path=parent_dir_node.path/buildname,
                    needs=(parent_dir_node,) )
        elif figure_type in {'asy', 'svg'}:
            parent_dir_node = self._get_figure_node_dir( metapath,
                figure_type='dir' )
            return jeolm.node.directory.DirectoryNode(
                    name = 'figure:{}:{}:dir'.format(metapath, figure_type),
                    path=parent_dir_node.path/figure_type,
                    needs=(parent_dir_node,) )
        else:
            raise RuntimeError

    _main_file_names = {'pdf' : 'Main.pdf', 'eps' : 'Main.eps'}

    def _get_figure_node_asy( self, metapath,
        *, figure_format, figure_record
    ):
        build_dir_node = self._get_figure_node_dir( metapath,
            figure_type='asy' )
        main_asy_node = self._get_figure_node_asy_source( metapath,
            figure_record=figure_record )
        other_asy_nodes = main_asy_node.other_asy_nodes
        assert main_asy_node.path.parent == build_dir_node.path
        node = jeolm.node.ProductFileNode(
            name='figure:{}:asy:{}'.format(metapath, figure_format),
            source=main_asy_node,
            path=build_dir_node.path/self._main_file_names[figure_format],
            needs=chain((build_dir_node,), other_asy_nodes) )
        node.set_subprocess_command(
            ( 'asy', '-outformat={}'.format(figure_format), '-offscreen',
                main_asy_node.path.name ),
            cwd=build_dir_node.path )
        return node

    @_cache_figure_node(figure_type='asy', figure_format='asy')
    def _get_figure_node_asy_source(self, metapath, *, figure_record):
        build_dir_node = self._get_figure_node_dir( metapath,
            figure_type='asy' )
        main_asy_node = jeolm.node.symlink.SymLinkedFileNode(
            name='figure:{}:asy:source:main'.format(metapath),
            source=self.source_node_factory(figure_record['source']),
            path=build_dir_node.path/'Main.asy',
            needs=(build_dir_node,) )
        other_asy_nodes = main_asy_node.other_asy_nodes = list()
        for accessed_name, inpath in figure_record['accessed_sources'].items():
            if accessed_name == 'Main.asy':
                raise ValueError(
                    "Cannot symlink non-main asy file as Main.asy: "
                    "{} wants to access {}"
                    .format(metapath, inpath) )
            node = jeolm.node.symlink.SymLinkedFileNode(
                name='figure:{}:asy:source:{}'.format(metapath, accessed_name),
                source=self.source_node_factory(inpath),
                path=build_dir_node.path/accessed_name,
                needs=(build_dir_node,) )
            other_asy_nodes.append(node)
        return main_asy_node

    def _get_figure_node_svg( self, metapath,
        *, figure_format, figure_record
    ):
        build_dir_node = self._get_figure_node_dir( metapath,
            figure_type='svg' )
        svg_node = self._get_figure_node_svg_source( metapath,
            figure_record=figure_record )
        assert svg_node.path.parent == build_dir_node.path
        node = jeolm.node.ProductFileNode(
            name='figure:{}:svg:{}'.format(metapath, figure_format),
            source=svg_node,
            path=build_dir_node.path/self._main_file_names[figure_format],
            needs=(build_dir_node,) )
        node.set_subprocess_command(
            ( 'inkscape', '--without-gui',
                '--export-{}={}'.format(figure_format, node.path.name),
                svg_node.path.name ),
            cwd=build_dir_node.path )
        return node

    @_cache_figure_node(figure_type='svg', figure_format='svg')
    def _get_figure_node_svg_source(self, metapath, *, figure_record):
        build_dir_node = self._get_figure_node_dir( metapath,
            figure_type='svg' )
        return jeolm.node.symlink.SymLinkedFileNode(
            name='figure:{}:svg:source'.format(metapath),
            source=self.source_node_factory(figure_record['source']),
            path=build_dir_node.path/'Main.svg',
            needs=(build_dir_node,) )

    def _get_figure_node_symlink( self, metapath,
        *, figure_format, figure_record
    ):
        source_node = self.source_node_factory(figure_record['source'])
        node = jeolm.node.symlink.ProxyFileNode(
            name='figure:{}:{}'.format(metapath, figure_format),
            source=source_node )
        return node


class SourceNodeFactory:

    def __init__(self, *, local):
        self.local = local
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
            path=self.local.source_dir/inpath )
        if not source_node.path.exists():
            logger.warning(
                "Requested source node <YELLOW>%(inpath)s<NOCOLOUR> "
                    "does not exist as file",
                dict(inpath=inpath) )
        return source_node


class TextNode(jeolm.node.FileNode):

    def __init__(self, path, *, name=None, needs=(),
        text_node_shelf, local
    ):
        super().__init__(path, name=name, needs=needs)
        self._shelf = text_node_shelf
        self._key = str(self.path.relative_to(local.build_dir))
        self._text_hash = None

    @property
    def text_hash(self):
        if self._text_hash is not None:
            return self._text_hash
        assert self.command is not None, self
        assert isinstance(self.command, jeolm.node.WriteTextCommand), self
        self._text_hash = hashlib.sha256(self.command.text.encode()).digest()
        return self._text_hash

    def _needs_build(self):
        if super()._needs_build():
            return True
        old_text_hash = self._shelf.get(self._key)
        if self.text_hash != old_text_hash:
            self.logger.info("Change in content detected")
            return True
        else:
            self.logger.debug("No change in content detected")
        return False

    def _run_command(self):
        super()._run_command()
        self._shelf[self._key] = self.text_hash
        self.logger.debug("Text database updated")

