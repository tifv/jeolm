from collections import namedtuple

from jeolm.records import RecordPath

import jeolm.node
import jeolm.node.directory
import jeolm.node.symlink
import jeolm.node.cyclic
from jeolm.node.text import text_hash

from jeolm.driver import FigureRecipe

from . import _cache_node

import logging
logger = logging.getLogger(__name__)

import typing
from typing import Any, Dict
if typing.TYPE_CHECKING:
    from .source import SourceNodeFactory


class BuildableFigureNode(jeolm.node.FileNode):
    build_dir_node: jeolm.node.directory.DirectoryNode
    output_dir_node: jeolm.node.directory.DirectoryNode
    pass

class FigureNodeFactory: #{{{1

    figure_types = frozenset((
        '<latex>', '<pdflatex>', '<xelatex>', '<lualatex>',
        'pdf', 'eps', 'png', 'jpg', ))
    figure_source_types = frozenset((
        None,
        'asy', 'svg', 'pdf', 'eps', 'png', 'jpg', ))
    flexible_figure_source_types = frozenset(('asy', 'svg',))

    class _ProxyFigureNode(
        jeolm.node.symlink.ProxyFileNode[jeolm.node.FilelikeNode],
        BuildableFigureNode,
    ):
        pass

    source_node_factory: SourceNodeFactory
    build_dir_node: jeolm.node.directory.DirectoryNode

    _nodes: Dict[Any, jeolm.node.FilelikeNode]

    def __init__(self, *, project, driver,
        build_dir_node,
        source_node_factory
    ):
        self.project = project
        self.driver = driver
        self.source_node_factory = source_node_factory
        self.build_dir_node = build_dir_node

        self._nodes = dict()

    @property
    def build_dir(self):
        return self.build_dir_node.path

    def __call__(self, figure_path, *, figure_types):
        assert isinstance(figure_path, RecordPath)
        assert isinstance(figure_types, frozenset)
        return self._get_figure_node( figure_path,
            figure_types=figure_types )

    def _figure_node_key(self, figure_path, *, figure_types):
        return figure_path, figure_types

    @_cache_node(_figure_node_key)
    def _get_figure_node(self, figure_path, *, figure_types):
        figure_recipe: FigureRecipe = \
            self.driver.produce_figure_recipe(
                figure_path, figure_types=figure_types )
        source_type = figure_recipe.source_type
        figure_type = figure_recipe.figure_type

        if figure_type not in {'pdf', 'eps', 'png', 'jpg'}:
            raise RuntimeError

        if not self._check_figure_type(source_type, figure_type):
            raise ValueError( "Incompatible figure source type and type "
                f"for figure {figure_path}, "
                f"given source type {source_type} and type {figure_type}" )

        if   source_type == 'asy':
            get_figure_node_method = self._get_figure_path_asy_factory
        elif source_type == 'svg':
            get_figure_node_method = self._get_figure_node_svg
        elif source_type in {'pdf', 'eps', 'png', 'jpg'}:
            get_figure_node_method = self._get_figure_node_proxy
        else:
            raise RuntimeError

        node = get_figure_node_method( figure_path,
            figure_type=figure_type,
            figure_recipe=figure_recipe )
        if not hasattr(node, 'figure_path'):
            node.figure_path = figure_path
        return node

    @staticmethod
    def _check_figure_type(source_type, figure_type):
        if source_type in {'asy', 'svg'}:
            if figure_type in {'pdf', 'eps'}:
                return True
            else:
                return False
        elif source_type in {'pdf', 'eps', 'png', 'jpg'}:
            if figure_type == source_type:
                return True
            else:
                return False
        else:
            raise RuntimeError

    def _figure_node_proxy_key(self, figure_path, *, figure_type, **kwargs):
        return figure_path, figure_type

    @_cache_node(_figure_node_proxy_key)
    def _get_figure_node_proxy( self, figure_path,
        *, figure_type, figure_recipe: FigureRecipe,
    ):
        source_node = self.source_node_factory(figure_recipe.source)
        node = jeolm.node.symlink.ProxyFileNode( source_node,
            name='figure:{}:{}'.format(figure_path, figure_type) )
        return node

    def _figure_path_build_dir_key(self, figure_path):
        return figure_path, 'dir', 'dir'

    @_cache_node(_figure_path_build_dir_key)
    def _get_figure_path_build_dir(self, figure_path):
        parent_dir_node = self.build_dir_node
        dir_path = parent_dir_node.path / '-'.join(figure_path.parts)
        return jeolm.node.directory.DirectoryNode(
            name=f'figure:{figure_path}:dir',
            path=dir_path,
            needs=(parent_dir_node,) )

    # SVG {{{2

    def _build_dir_svg_key(self, figure_path):
        return figure_path, 'svg', 'dir'

    @_cache_node(_build_dir_svg_key)
    def _get_build_dir_svg(self, figure_path):
        parent_dir_node = self._get_figure_path_build_dir(figure_path)
        return jeolm.node.directory.BuildDirectoryNode(
            name=f'figure:{figure_path}:svg:dir',
            path=parent_dir_node.path/'svg',
            needs=(parent_dir_node,) )

    def _output_dir_svg_key(self, figure_path):
        return figure_path, 'svg', 'output-dir'

    @_cache_node(_output_dir_svg_key)
    def _get_output_dir_svg(self, figure_path):
        build_dir_node = self._get_build_dir_svg(figure_path)
        output_dir_node = jeolm.node.directory.DirectoryNode(
            name=f'figure:{figure_path}:svg:output-dir',
            path=build_dir_node.path/'output',
            needs=(build_dir_node,) )
        build_dir_node.register_node(output_dir_node)
        return output_dir_node

    def _get_figure_node_svg( self, figure_path,
        *, figure_type, figure_recipe
    ) -> BuildableFigureNode:
        build_dir_node = self._get_build_dir_svg(figure_path)
        output_dir_node = self._get_output_dir_svg(figure_path)
        svg_node = self._get_figure_node_svg_source( figure_path,
            figure_recipe=figure_recipe )
        assert svg_node.path.parent == build_dir_node.path
        figure_node = jeolm.node.ProductFileNode(
            name=f'figure:{figure_path}:svg:{figure_type}',
            source=svg_node,
            path=output_dir_node.path/f'Main.{figure_type}',
            needs=(build_dir_node.pre_cleanup_node, output_dir_node)
        )
        figure_node.command = jeolm.node.SubprocessCommand( figure_node,
            ( 'inkscape', '--without-gui',
                f'--export-{figure_type}=' +
                    str(figure_node.path.relative_to(build_dir_node.path)),
                svg_node.path.name
            ),
            cwd=build_dir_node.path )
        build_dir_node.post_check_node.append_needs(figure_node)
        proxy_figure_node = self._ProxyFigureNode( figure_node,
            name=f'{figure_node.name}:proxy',
            needs=(build_dir_node.post_check_node,) )
        proxy_figure_node.build_dir_node = build_dir_node
        proxy_figure_node.output_dir_node = output_dir_node
        return proxy_figure_node

    def _figure_node_svg_source_key(self, figure_path, **kwargs):
        return figure_path, 'svg', 'svg'

    @_cache_node(_figure_node_svg_source_key)
    def _get_figure_node_svg_source(self, figure_path, *, figure_recipe):
        build_dir_node = self._get_build_dir_svg(figure_path)
        source_svg_node = jeolm.node.symlink.SymLinkedFileNode(
            name=f'figure:{figure_path}:svg:source',
            source=self.source_node_factory(figure_recipe.source),
            path=build_dir_node.path/'Main.svg',
            needs=(build_dir_node,) )
        build_dir_node.register_node(source_svg_node)
        return source_svg_node

    # Asymptote {{{2

    def _figure_path_build_dir_asy_key(self, figure_path):
        return figure_path, 'asy', 'dir'

    @_cache_node(_figure_path_build_dir_asy_key)
    def _get_figure_path_build_dir_asy(self, figure_path):
        parent_dir_node = self._get_figure_path_build_dir(figure_path)
        return jeolm.node.directory.DirectoryNode(
            name=f'figure:{figure_path}:asy:dir',
            path=parent_dir_node.path/'asy',
            needs=(parent_dir_node,) )

    def _figure_path_asy_key(self, figure_path, *, figure_type, **kwargs):
        return figure_path, 'asy', figure_type

    @_cache_node(_figure_path_asy_key)
    def _get_figure_path_asy_factory( self, figure_path,
        *, figure_type, figure_recipe,
    ):
        build_dir_node = self._get_figure_path_build_dir_asy(figure_path)
        asy_source_nodes = self._get_figure_path_asy_sources( figure_path,
            figure_recipe=figure_recipe )
        return self.AsymptoteNode( self,
            name=f'figure:{figure_path}:asy:{figure_type}',
            figure_path=figure_path, figure_type=figure_type,
            build_dir_node=build_dir_node,
            asy_source_nodes=asy_source_nodes, )

    def _get_figure_path_asy_sources(self, figure_path, *, figure_recipe):
        asy_source_nodes = {}
        asy_source_nodes['Main.asy'] = \
            self.source_node_factory(figure_recipe.source)
        for accessed_name, inpath in figure_recipe.other_sources.items():
            if accessed_name in {'Main.asy', 'Run.asy'}:
                raise ValueError(accessed_name)
            asy_source_nodes[accessed_name] = self.source_node_factory(inpath)
        return asy_source_nodes

    AsymptoteContext = namedtuple( 'AsymptoteContext',
        ['latex_compiler', 'latex_preamble', 'width', 'height'] )

    class AsymptoteNode(jeolm.node.Node):

        def __init__( self, factory,
            *, figure_path, figure_type,
            build_dir_node, asy_source_nodes,
            needs=(),
            **kwargs
        ):
            super().__init__(
                needs=(*needs, build_dir_node, *asy_source_nodes.values()),
                **kwargs )
            self.factory = factory
            self.figure_path = figure_path
            self.figure_type = figure_type
            self.build_dir_node = build_dir_node
            self.asy_source_nodes = asy_source_nodes

        def __call__(self, asy_context) -> BuildableFigureNode:
            assert isinstance(asy_context, self.factory.AsymptoteContext)
            return self.factory._get_figure_node_asy( self.figure_path,
                figure_type=self.figure_type,
                asy_context=asy_context,
                parent_build_dir_node=self.build_dir_node,
                asy_source_nodes=self.asy_source_nodes,
            )

    def _build_dir_asy_key(self, figure_path, asy_context, **kwargs):
        return figure_path, 'asy', asy_context, 'dir'

    @_cache_node(_build_dir_asy_key)
    def _get_build_dir_asy( self, figure_path, asy_context,
        *, run_hash, parent_dir_node,
    ):
        return jeolm.node.directory.BuildDirectoryNode(
            name=f'figure:{figure_path}:asy:{run_hash[:10]}:dir',
            path=parent_dir_node.path/run_hash,
            needs=(parent_dir_node,) )

    def _output_dir_asy_key(self, figure_path, asy_context, **kwargs):
        return figure_path, 'asy', asy_context, 'output-dir'

    @_cache_node(_output_dir_asy_key)
    def _get_output_dir_asy( self, figure_path, asy_context,
        *, run_hash, build_dir_node,
    ):
        output_dir_node = jeolm.node.directory.DirectoryNode(
            name=f'figure:{figure_path}:asy:{run_hash[:10]}:output-dir',
            path=build_dir_node.path/'output',
            needs=(build_dir_node,) )
        build_dir_node.register_node(output_dir_node)
        return output_dir_node

    def _figure_node_asy_key(self, figure_path,
            *, figure_type, asy_context, **kwargs):
        return figure_path, 'asy', asy_context, figure_type

    @_cache_node(_figure_node_asy_key)
    def _get_figure_node_asy( self, figure_path,
        *, figure_type, asy_context,
        parent_build_dir_node, asy_source_nodes,
    ) -> BuildableFigureNode:
        run_asy_content = self._generate_run_asy(asy_context)
        run_hash = text_hash(run_asy_content)
        build_dir_node = self._get_build_dir_asy( figure_path, asy_context,
            run_hash=run_hash, parent_dir_node=parent_build_dir_node )
        output_dir_node = self._get_output_dir_asy( figure_path, asy_context,
            run_hash=run_hash, build_dir_node=build_dir_node )
        run_asy_node = jeolm.node.text.SimpleTextNode(
            name=f'figure:{figure_path}:asy:{run_hash[:10]}:source:run',
            path=build_dir_node.path/'Run.asy',
            text=run_asy_content,
            needs=(build_dir_node,))
        build_dir_node.register_node(run_asy_node)
        asy_nodes = self._get_figure_node_asy_sources(
            figure_path, asy_context,
            asy_source_nodes=asy_source_nodes,
            run_hash=run_hash, build_dir_node=build_dir_node )
        assert figure_type in {'eps', 'pdf'}
        figure_node = jeolm.node.ProductFileNode(
            name=f'figure:{figure_path}:asy:{run_hash[:10]}:{figure_type}',
            source=run_asy_node,
            path=output_dir_node.path/f'Main.{figure_type}',
            needs=( build_dir_node.pre_cleanup_node, output_dir_node,
                *asy_nodes ),
        )
        figure_node.command = jeolm.node.SubprocessCommand( figure_node,
            ( 'asy', f'-outformat={figure_type}', '-offscreen',
                run_asy_node.path.name,
                '-outname=' +
                    str(figure_node.path.relative_to(build_dir_node.path)),
            ),
            cwd=build_dir_node.path )
        build_dir_node.post_check_node.append_needs(figure_node)
        proxy_figure_node = self._ProxyFigureNode( figure_node,
            name=f'{figure_node.name}:proxy',
            needs=(build_dir_node.post_check_node,) )
        proxy_figure_node.build_dir_node = build_dir_node
        proxy_figure_node.output_dir_node = output_dir_node
        return proxy_figure_node

    @classmethod
    def _generate_run_asy(cls, asy_context):
        assert asy_context.latex_compiler in \
            {"latex", "pdflatex", "xelatex", "lualatex"}
        assert isinstance(asy_context.latex_preamble, str)
        if '"' in asy_context.latex_preamble:
            raise ValueError
        return (
            'access settings;\n'
            f'settings.tex = "{asy_context.latex_compiler}";\n'
            f'texpreamble("{asy_context.latex_preamble}");\n'
            "import Main;\n"
            +
            cls._generate_run_asy_size(asy_context.width, asy_context.height)
        )

    @classmethod
    def _generate_run_asy_size(cls, width, height):
        if width is None and height is None:
            return ''
        def format_dim(dim):
            if dim is None:
                return '0'
            return str(dim) + 'cm'
        return f"size({format_dim(width)}, {format_dim(height)});\n"

    def _figure_node_asy_sources_key(self, figure_path, asy_context, **kwargs):
        return figure_path, 'asy', asy_context, 'asy'

    @_cache_node(_figure_node_asy_sources_key)
    def _get_figure_node_asy_sources(self, figure_path, asy_context,
        *, asy_source_nodes, run_hash, build_dir_node ):
        asy_nodes = []
        for accessed_name, source_node in asy_source_nodes.items():
            assert accessed_name != 'Run.asy'
            asy_node = jeolm.node.symlink.SymLinkedFileNode(
                name=f'figure:{figure_path}:asy:{run_hash[:10]}:'
                    f'source:{accessed_name}',
                source=source_node,
                path=build_dir_node.path/accessed_name,
                needs=(build_dir_node,) )
            asy_nodes.append(asy_node)
            build_dir_node.register_node(asy_node)
        return asy_nodes

# }}}1
# vim: set foldmethod=marker :
