import re
import hashlib
from pathlib import PosixPath

import jeolm.node
import jeolm.node.directory
import jeolm.node.symlink
import jeolm.node.text
import jeolm.node.cyclic
import jeolm.node.latex

from jeolm.records import RecordPath
from jeolm.target import Target

from . import _cache_node
from .figure import FigureNodeFactory

import logging
logger = logging.getLogger(__name__)

from typing import Union, List


class DocumentNode(jeolm.node.FileNode):
    pass

class DocumentNodeFactory:

    document_types = ('regular', )

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
        recipe = self.driver.produce_document_recipe(target)
        build_dir_node = self._get_build_dir(target, recipe)
        output_dir_node = jeolm.node.directory.DirectoryNode(
            name='document:{}:output:dir'.format(target),
            path=build_dir_node.path/'output',
            needs=(build_dir_node,) )
        build_dir_node.register_node(output_dir_node)
        source_dir_node = jeolm.node.directory.BuildDirectoryNode(
            name='document:{}:source:dir'.format(target),
            path=build_dir_node.path/'sources',
            needs=(build_dir_node,) )
        build_dir_node.register_node(source_dir_node)
        figure_dir_node = jeolm.node.directory.BuildDirectoryNode(
            name='document:{}:figures:dir'.format(target),
            path=build_dir_node.path/'figures',
            needs=(build_dir_node,) )
        build_dir_node.register_node(figure_dir_node)
        document_type = recipe['type']
        if document_type == 'regular':
            prebuild_method = self._prebuild_regular
        else:
            raise RuntimeError
        main_source_node, source_nodes, package_nodes, figure_nodes = \
            prebuild_method( target, recipe,
                build_dir_node=build_dir_node,
                output_dir_node=output_dir_node,
                source_dir_node=source_dir_node,
                figure_dir_node=figure_dir_node )
        cyclic_figure_nodes = [ figure_node
            for figure_node in figure_nodes
            if isinstance(figure_node, jeolm.node.cyclic.CyclicNeed) ]
        document_node_class = self._document_node_classes[recipe['compiler']]
        document_node = document_node_class(
            name='document:{}:output'.format(target),
            source=main_source_node, jobname='Main',
            latex_predefs=r'\newif\ifjeolmfigurewritesize'
                r'\jeolmfigurewritesizetrue',
            build_dir_node=build_dir_node, output_dir_node=output_dir_node,
            figure_nodes=figure_nodes,
            needs=(*source_nodes, *package_nodes),
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
    def _target_path_build_dir_key(self, target_path):
        return target_path, 'target-path-dir'
    # pylint: enable=no-self-use

    @_cache_node(_target_path_build_dir_key)
    def _get_target_path_build_dir(self, target_path):
        assert isinstance(target_path, RecordPath)
        parent_dir_node = self.build_dir_node
        dir_path = parent_dir_node.path / '-'.join(target_path.parts)
        return jeolm.node.directory.DirectoryNode(
            name='document:{}:target-path-dir'.format(target_path),
            path=dir_path,
            needs=(parent_dir_node,) )

    # pylint: disable=no-self-use
    def _target_build_dir_key(self, target):
        return target, 'target-dir'
    # pylint: enable=no-self-use

    @_cache_node(_target_build_dir_key)
    def _get_target_build_dir(self, target):
        assert isinstance(target, Target)
        parent_dir_node = self._get_target_path_build_dir(target.path)
        buildname = ','.join(sorted(target.flags.as_frozenset))
        if not buildname:
            buildname = 'default'
        elif buildname == 'default':
            buildname = 'default,'
        assert not buildname.startswith('.')
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

    def _prebuild_regular( self, target, recipe,
        *, build_dir_node, output_dir_node,
        source_dir_node, figure_dir_node,
    ):
        """
        Prebuild all necessary for building a document.

        Return (
            main_source_node, source_nodes,
            package_nodes, figure_nodes ).
        """
        source_nodes = self._prebuild_regular_sources( target, recipe,
            source_dir_node=source_dir_node )
        package_nodes = self._prebuild_regular_packages( target, recipe,
            build_dir_node=build_dir_node )
        figure_nodes = self._prebuild_regular_figures( target, recipe,
            figure_dir_node=figure_dir_node, output_dir_node=output_dir_node )

        templatefill = dict()
        for source_path, source_node in source_nodes.items():
            templatefill['source', source_path] = \
                str(source_node.path.relative_to(build_dir_node.path))
        for (figure_path, figure_index), figure_node in figure_nodes.items():
            templatefill['figure', figure_path, figure_index] = \
                str( figure_node.path.relative_to(build_dir_node.path)
                        .with_suffix('') )
            if hasattr(figure_node, 'sizefile_node'):
                templatefill['figure-size', figure_path, figure_index] = \
                    str( figure_node.sizefile_node.path
                            .relative_to(output_dir_node.path) )
            else:
                templatefill['figure-size', figure_path, figure_index] = ''
        for package_path, package_node in package_nodes.items():
            templatefill['package', package_path] = \
                str(package_node.path.with_suffix('').name)
        main_source_node = jeolm.node.text.TextNode(
            name='document:{}:source:main'.format(target),
            path=build_dir_node.path/'Main.tex',
            text=recipe['document'].substitute(templatefill),
            build_dir_node=build_dir_node )
        build_dir_node.register_node(main_source_node)

        return (
            main_source_node, source_nodes.values(),
            package_nodes.values(), figure_nodes.values(),
        )

    @staticmethod
    def _name_hash(name):
        return hashlib.sha256(name.encode('utf-8')).hexdigest()

    def _prebuild_regular_sources( self, target, recipe,
        *, source_dir_node,
    ):
        "Return {source_path : source_node}."
        source_paths = list()
        for key in recipe['document'].keys():
            assert isinstance(key, tuple)
            key_type, *key_value = key
            if key_type == 'source':
                source_path, = key_value
                source_paths.append(source_path)
        source_path_aliases = {
            source_path : '-'.join(source_path.with_suffix('').parts)
            for source_path in source_paths }
        self._resolve_alias_conflicts( source_path_aliases,
            alias_key_func=lambda path, alias: (alias, path.suffix),
            key_hash_func=lambda path: self._name_hash(str(path)) )
        source_path_aliases = {
            source_path : alias + source_path.suffix
            for source_path, alias in source_path_aliases.items() }
        source_nodes = dict()
        for source_path, alias in source_path_aliases.items():
            source_node = source_nodes[source_path] = \
                jeolm.node.symlink.SymLinkedFileNode(
                    name='document:{}:source:{}'.format(target, alias),
                    source=self.source_node_factory(source_path),
                    path=source_dir_node.path/alias,
                    needs=(source_dir_node,)
                )
            source_dir_node.register_node(source_node)
        return source_nodes

    def _prebuild_regular_packages( self, target, recipe,
        *, build_dir_node,
    ):
        package_paths = list()
        for key in recipe['document'].keys():
            assert isinstance(key, tuple)
            key_type, *key_value = key
            if key_type == 'package':
                package_path, = key_value
                package_paths.append(package_path)
        package_nodes = dict()
        package_names = set()
        for package_path in package_paths:
            orig_package_node = self.package_node_factory(package_path)
            package_name = orig_package_node.package_name
            if package_name in package_names:
                raise ValueError(package_name)
            package_names.add(package_name)
            package_node = package_nodes[package_path] = \
                jeolm.node.symlink.SymLinkedFileNode(
                    name='document:{}:package:{}'.format(target, package_name),
                    source=orig_package_node,
                    path=(build_dir_node.path/package_name)
                        .with_suffix('.sty'),
                    needs=(build_dir_node,)
                )
            build_dir_node.register_node(package_node)
        return package_nodes

    def _prebuild_regular_figures( self, target, recipe,
        *, figure_dir_node, output_dir_node
    ):
        if recipe['compiler'] in {'latex'}:
            figure_formats = frozenset(('eps',))
        elif recipe['compiler'] in {'pdflatex', 'xelatex', 'lualatex'}:
            figure_formats = frozenset(('pdf', 'png', 'jpg'))
        else:
            raise RuntimeError
        figure_paths = list()
        for key in recipe['document'].keys():
            assert isinstance(key, tuple)
            key_type, *key_value = key
            if key_type == 'figure':
                figure_path, figure_index = key_value
                figure_paths.append((figure_path, figure_index))
        figure_path_aliases = {
            (figure_path, figure_index) : '-'.join(figure_path.parts)
            for (figure_path, figure_index) in figure_paths }
        self._resolve_alias_conflicts( figure_path_aliases,
            key_hash_func=lambda items:
                self._name_hash(':'.join(str(item) for item in items))
        )
        figure_nodes = dict()
        for (figure_path, figure_index), alias_stem \
                in figure_path_aliases.items():
            orig_figure_node = self.figure_node_factory( figure_path,
                figure_formats=figure_formats )
            if isinstance(orig_figure_node, FigureNodeFactory.AsymptoteNode):
                figure_node = figure_nodes[figure_path, figure_index] = \
                    self._prebuild_asy_figure( target, recipe,
                        orig_figure_node, figure_dir_node, alias_stem,
                        output_dir_node=output_dir_node )
            else:
                figure_suffix = orig_figure_node.path.suffix
                assert figure_suffix in {'.pdf', '.eps', '.png', '.jpg'}
                alias = alias_stem + figure_suffix
                figure_node = figure_nodes[figure_path, figure_index] = \
                    jeolm.node.symlink.SymLinkedFileNode(
                        name=f'document:{target}:figure:{alias}',
                        source=orig_figure_node,
                        path=(figure_dir_node.path/alias),
                        needs=(figure_dir_node,)
                    )
            figure_dir_node.register_node(figure_node)
        return figure_nodes

    def _prebuild_asy_figure( self, target, recipe,
        figure_node_subfactory, figure_dir_node, alias_stem,
        *, output_dir_node
    ):
        sizefile_path = output_dir_node.path/(alias_stem + '.figsize')
        alias = alias_stem + '.' + figure_node_subfactory.figure_format
        return AsymptoteFigureNode(
            name=f'document:{target}:figure:{alias}',
            figure_dir_node=figure_dir_node,
            alias=alias,
            node_subfactory=figure_node_subfactory,
            sizefile_path=sizefile_path,
            latex_compiler=recipe['asy_latex_compiler'],
            latex_preamble=recipe['asy_latex_preamble'],
        )

    @staticmethod
    def _resolve_alias_conflicts( aliases, *,
        alias_key_func=lambda key, alias: alias,
        key_hash_func, separator='-'
    ):
        reverse_aliases = dict()
        for key, alias in aliases.items():
            alias_key = alias_key_func(key, alias)
            reverse_aliases.setdefault(alias_key, set()).add(key)
        for alias_key, keys in reverse_aliases.items():
            if len(keys) <= 1:
                continue
            hashes = {key: key_hash_func(key) for key in keys}
            n = 4
            for n in range(4, max(len(h) for h in hashes.values()) + 1):
                if len(set(h[:n] for h in hashes.values())) < len(keys):
                    continue
                else:
                    break
            else:
                raise ValueError( "Full hash collision "
                    "(this should not be possible)" )
            for key in keys:
                aliases[key] = aliases[key] + separator + hashes[key][:n]


class AsymptoteFigureNode(
    jeolm.node.cyclic.CyclicDatedNeed,
    jeolm.node.FilelikeNode,
):

    figure_dir_node: jeolm.node.directory.DirectoryNode
    node_subfactory: FigureNodeFactory.AsymptoteNode
    sizefile_node: jeolm.node.cyclic.AutowrittenNeed
    latex_compiler: str
    latex_preamble: str
    _invariable_needs: List[jeolm.node.Node]
    link_node = Union[None, jeolm.node.Node]

    def __init__(self,
        *, figure_dir_node, alias,
        node_subfactory,
        sizefile_path,
        latex_compiler, latex_preamble,
        name=None, needs=(),
    ):
        self.figure_dir_node = figure_dir_node
        self.node_subfactory = node_subfactory
        self.sizefile_node = sizefile_node = \
            jeolm.node.cyclic.AutowrittenNeed(sizefile_path)
        self.latex_compiler = latex_compiler
        self.latex_preamble = latex_preamble
        self._invariable_needs = list()
        self.link_node = None
        super().__init__( path=figure_dir_node.path/alias,
            name=name,
            needs=(*needs, figure_dir_node, node_subfactory) )

    def _append_needs(self, node):
        super()._append_needs(node)
        self._invariable_needs.append(node)

    # update_self is called
    # - for the first time
    # - after relinking figure

    # Override
    async def update_self(self) -> None:
        if self.link_node is None:
            self.refresh()
            assert not self.updated
        else:
            assert self.link_node.updated
            self.modified = self.link_node.modified
            self.updated = True

    # refresh is called
    # - sometimes from update_self
    # - after document cycle

    def refresh(self):
        self.sizefile_node.refresh()
        if self.link_node is not None:
            if not self.sizefile_node.modified:
                self.modified = False
                return
            else:
                self.link_node = None
                self.updated = False

        assert self.link_node is None
        assert not self.updated
        width, height = self._read_sizes()
        orig_figure_node = self.node_subfactory(
            FigureNodeFactory.AsymptoteContext(
                self.latex_compiler, self.latex_preamble,
                width, height ),
        )
        assert isinstance(orig_figure_node, jeolm.node.PathNode)
        figure_node = jeolm.node.symlink.SymLinkedFileNode(
            name=f'{self.name}:link',
            source=orig_figure_node,
            path=self.path,
            needs=(orig_figure_node,),
        )
        self.link_node = figure_node
        self.needs = self._invariable_needs + [self.link_node]

    def _load_mtime(self):
        if self.link_node is not None:
            self.mtime = self.link_node.mtime
        else:
            self.mtime = None

    def _read_sizes(self):
        if self.sizefile_node.path.exists():
            with self.sizefile_node.path.open('r', encoding='utf-8') \
                    as sizefile:
                sizes_string = sizefile.read()
            width = self._read_size('width', sizes_string)
            height = self._read_size('height', sizes_string)
            return width, height
        else:
            return None, None

    _size_regex = re.compile(r'(?m)'
        r'^(?P<name>width|height)=(?P<value_pt>\d+(?:\.\d+)?)pt$')

    def _read_size(self, name, sizes_string):
        size = None
        for match in self._size_regex.finditer(sizes_string):
            if match.group('name') == name:
                if size is not None:
                    raise ValueError
                size = round(float(match.group('value_pt')) / 28.4527, 3)
        if size == 0.0:
            size = None
        return size

