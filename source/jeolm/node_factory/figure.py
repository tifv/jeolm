from itertools import chain

import jeolm.node
import jeolm.node.directory
import jeolm.node.symlink

from jeolm.record_path import RecordPath

from . import _cache_node

import logging
logger = logging.getLogger(__name__)


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



