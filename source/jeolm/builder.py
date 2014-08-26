from string import Template
from collections import OrderedDict
from itertools import chain
from functools import partial
from datetime import date

import hashlib
import pickle

from pathlib import PurePosixPath

import jeolm
import jeolm.node
import jeolm.latex_node
import jeolm.records
import jeolm.target

from jeolm.records import RecordPath

import logging
logger = logging.getLogger(__name__) # pylint: disable=invalid-name

class Builder:
    build_formats = ('pdf', )
    known_formats = ('pdf', 'ps', 'dump')

    def __init__(self, targets, *, local, driver,
        force=None, delegate=True
    ):
        self.local = local
        self.driver = driver

        self.targets = targets
        assert force in {'latex', 'generate', None}
        self.force = force
        self.delegate = delegate

    def prebuild(self, ultimate_node=None):
        self.recipe_node_factory = RecipeNodeFactory(
            local=self.local, driver=self.driver )

        targets = self.targets
        if self.delegate:
            targets = [
                delegated_target.flags_clean_copy(origin='target')
                for delegated_target
                in self.driver.list_delegated_targets(
                    *targets, recursively=True )
            ]
        self.source_node_factory = SourceNodeFactory(local=self.local)
        self.figure_node_factory = FigureNodeFactory(
            local=self.local, driver=self.driver,
            build_dir_node=jeolm.node.DirectoryNode(
                self.local.build_dir/'figures', parents=True ),
            source_node_factory=self.source_node_factory
        )
        self.package_node_factory = PackageNodeFactory(
            local=self.local, driver=self.driver,
            build_dir_node=jeolm.node.DirectoryNode(
                self.local.build_dir/'packages', parents=True ),
            source_node_factory=self.source_node_factory
        )
        assert set(self.known_formats) >= set(self.build_formats)

        self.prebuild_documents( targets,
            build_dir=self.local.build_dir/'documents' )

        if ultimate_node is None:
            ultimate_node = jeolm.node.TargetNode(name='ultimate')
        self.ultimate_node = ultimate_node
        ultimate_node.extend_needs( node
            for build_format in self.build_formats
            for node in self.exposed_nodes[build_format].values() )

        recipe_nodes = self.recipe_node_factory.nodes.values()
        if any(node.modified for node in recipe_nodes):
            self.recipe_node_factory.dump_recipe_cache()

    def build(self, semaphore=None):
        if not hasattr(self, 'ultimate_node'):
            self.prebuild()
        if semaphore is not None:
            self.ultimate_node.update_start(semaphore=semaphore)
        self.ultimate_node.update()



    def prebuild_documents(self, targets, *, build_dir):
        self.document_nodes = {
            build_format : OrderedDict()
            for build_format in self.known_formats }
        self.exposed_nodes = {
            build_format : OrderedDict()
            for build_format in self.known_formats }
        for target in targets:
            recipe_node = self.recipe_node_factory(target)
            recipe = recipe_node.recipe
            build_subdir = build_dir / recipe['buildname']
            build_dir_node = jeolm.node.DirectoryNode(
                name='doc:{}:dir'.format(target),
                path=build_subdir, parents=True, )
            document_type = recipe['type']
            if document_type == 'regular':
                prebuild_document = self.prebuild_regular_document
            elif document_type == 'standalone':
                prebuild_document = self.prebuild_standalone_document
            elif document_type == 'latexdoc':
                prebuild_document = self.prebuild_latexdoc_document
            else:
                raise RuntimeError(document_type, target)
            prebuild_document( target, recipe,
                build_dir=build_subdir, build_dir_node=build_dir_node,
                recipe_node=recipe_node )
            self.prebuild_document_exposed(target, recipe)

    def prebuild_regular_document(self, target, recipe,
        *, recipe_node, build_dir, build_dir_node
    ):
        """
        Return nothing.
        Update self.autosource_nodes, self.document_nodes.
        """
        buildname = recipe['buildname']

        main_tex_node = jeolm.node.FileNode(
            name='doc:{}:autosource'.format(target),
            path=build_dir/'main.tex',
            needs=(recipe_node, build_dir_node) )
        main_tex_node.add_command(jeolm.node.TextCommand.from_text(
            text=recipe['document'] ))
        if self.force == 'generate':
            main_tex_node.force()

        package_nodes = [
            jeolm.node.LinkNode(
                name='doc:{}:sty:{}'.format(target, alias_name),
                source=self.package_node_factory(package_path),
                path=(build_dir/alias_name).with_suffix('.sty'),
                needs=(build_dir_node,) )
            for alias_name, package_path
            in recipe['package_paths'].items() ]
        figure_nodes = [
            jeolm.node.LinkNode(
                name='doc:{}:fig:{}'.format(target, alias_name),
                source=self.figure_node_factory(figure_path),
                path=(build_dir/alias_name).with_suffix('.eps'),
                needs=(build_dir_node,) )
            for alias_name, figure_path
            in recipe['figure_paths'].items() ]
        source_nodes = [
            jeolm.node.LinkNode(
                name='doc:{}:source:{}'.format(target, alias),
                source=self.source_node_factory(inpath),
                path=build_dir/alias,
                needs=(build_dir_node,) )
            for alias, inpath in recipe['sources'].items() ]

        dvi_node = jeolm.latex_node.LaTeXNode(
            name='doc:{}:dvi'.format(target),
            source=main_tex_node,
            path=(build_dir/buildname).with_suffix('.dvi'),
            cwd=build_dir, )
        dvi_node.extend_needs(package_nodes)
        dvi_node.extend_needs(figure_nodes)
        dvi_node.extend_needs(source_nodes)
        if self.force == 'latex':
            dvi_node.force()
        self.prebuild_document_postdvi( target, dvi_node, figure_nodes,
            build_dir=build_dir )
        if 'dump' in self.build_formats:
            self.prebuild_document_dump( target, recipe,
                recipe_node=recipe_node,
                build_dir=build_dir, build_dir_node=build_dir_node )

    def prebuild_document_dump(self, target, recipe,
        *, recipe_node, build_dir, build_dir_node
    ):
        if recipe['figure_paths']:
            logger.warning("Cannot properly dump a document with figures.")
        dump_node = self.document_nodes['dump'][target] = jeolm.node.FileNode(
            name='doc:{}:dump'.format(target),
            path=build_dir/'dump.tex',
            needs=(recipe_node, build_dir_node,) )
        dump_node.add_command(jeolm.node.TextCommand(textfunc=partial(
            self.supply_filecontents, recipe
        )))
        dump_node.extend_needs(
            self.source_node_factory(inpath)
            for inpath in recipe['sources'].values() )
        dump_node.extend_needs(
            self.package_node_factory(package_path)
            for package_path in recipe['package_paths'].values() )

    def supply_filecontents(self, recipe):
        pieces = []
        for alias_name, package_path in recipe['package_paths'].items():
            package_node = \
                self.package_node_factory(package_path)
            with package_node.open() as package_file:
                contents = package_file.read().strip('\n')
            pieces.append(self.substitute_filecontents(
                filename=alias_name + '.sty', contents=contents ))
        for alias, inpath in recipe['sources'].items():
            source_node = self.source_node_factory(inpath)
            with source_node.open('r') as source_file:
                contents = source_file.read().strip('\n')
            pieces.append(self.substitute_filecontents(
                filename=alias, contents=contents ))
        pieces.append(recipe['document'])
        return '\n'.join(pieces)

    filecontents_template = (
        r"\begin{filecontents*}{$filename}" '\n'
        r"$contents" '\n'
        r"\end{filecontents*}" '\n' )
    substitute_filecontents = Template(filecontents_template).substitute

    def prebuild_standalone_document(self, target, recipe,
        *, recipe_node, build_dir, build_dir_node
    ):
        buildname = recipe['buildname']

        source_node = self.source_node_factory(recipe['source'])
        tex_node = jeolm.node.LinkNode(
            name='doc:{}:tex'.format(target),
            source=source_node,
            path=build_dir/'main.tex',
            needs=(build_dir_node,) )
        dvi_node = jeolm.latex_node.LaTeXNode(
            name='doc:{}:dvi'.format(target),
            source=tex_node,
            path=(build_dir/buildname).with_suffix('.dvi'),
            cwd=build_dir, )
        if self.force == 'latex':
            dvi_node.force()
        self.prebuild_document_postdvi( target, dvi_node, [],
            build_dir=build_dir )
        if 'dump' in self.build_formats:
            raise ValueError("Standalone document {} cannot be dumped."
                .format(target) )

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

    def prebuild_latexdoc_document(self, target, recipe,
        *, recipe_node, build_dir, build_dir_node
    ):
        buildname = recipe['buildname']
        package_name = recipe['name']

        source_node = self.source_node_factory(recipe['source'])
        dtx_node = jeolm.node.LinkNode(
            name='doc:{}:dtx'.format(target),
            source=source_node,
            path=build_dir/'{}.dtx'.format(package_name),
            needs=(build_dir_node,) )
        ins_node = jeolm.node.FileNode(
            name='doc:{}:ins'.format(target),
            path=build_dir/'driver.ins',
            needs=(recipe_node, build_dir_node,) )
        ins_node.add_command(jeolm.node.TextCommand(textfunc=partial(
            self._substitute_driver_ins, package_name=package_name
        )))
        if self.force == 'generate':
            ins_node.force()
        drv_node = jeolm.node.FileNode(
            name='doc:{}:drv'.format(target),
            path=build_dir/'{}.drv'.format(package_name),
            needs=(build_dir_node, dtx_node, ins_node,) )
        drv_node.add_subprocess_command(
            ('latex', '-interaction=nonstopmode',
                '-halt-on-error', '-file-line-error', 'driver.ins'),
            cwd=build_dir )
        sty_node = jeolm.node.LinkNode(
            name='doc:{}:sty'.format(target),
            source=self.package_node_factory(target.path),
            path=(build_dir/package_name).with_suffix('.sty'),
            needs=(build_dir_node,) )

        dvi_node = jeolm.latex_node.LaTeXNode(
            name='doc:{}:dvi'.format(target),
            source=drv_node,
            path=(build_dir/buildname).with_suffix('.dvi'),
            cwd=build_dir,
            needs=(sty_node,) )
        if self.force == 'latex':
            dvi_node.force()
        self.prebuild_document_postdvi( target, dvi_node, [],
            build_dir=build_dir )
        if 'dump' in self.build_formats:
            raise ValueError(
                "LaTeX package documentation {} cannot be dumped."
                .format(target) )

    def prebuild_document_postdvi(self, target, dvi_node, figure_nodes,
        *, build_dir
    ):
        pdf_node = self.document_nodes['pdf'][target] = jeolm.node.FileNode(
            name='doc:{}:pdf'.format(target),
            path=build_dir/'main.pdf',
            needs=(dvi_node,) )
        pdf_node.extend_needs(figure_nodes)
        pdf_node.add_subprocess_command(
            ('dvipdf', dvi_node.path.name, pdf_node.path.name),
            cwd=build_dir )
        ps_node = self.document_nodes['ps'][target] = jeolm.node.FileNode(
            name='doc:{}:ps'.format(target),
            path=build_dir/'main.ps',
            needs=(dvi_node,) )
        ps_node.extend_needs(figure_nodes)
        ps_node.add_subprocess_command(
            ('dvips', dvi_node.path.name, '-o', ps_node.path.name),
            cwd=build_dir )

    def prebuild_document_exposed(self, target, recipe):
        for build_format in self.build_formats:
            document_node = self.document_nodes[build_format][target]
            self.exposed_nodes[build_format][target] = jeolm.node.LinkNode(
                name='doc:{}:exposed:{}'.format(target, build_format),
                source=document_node,
                path=(self.local.root/recipe['outname'])
                    .with_suffix(document_node.path.suffix)
            )


class Dumper(Builder):
    build_formats = ('dump', )


class RecipeNodeFactory:

    def __init__(self, local, driver):
        self.local = local
        self.driver = driver

        self.nodes = dict()

        self._cache = self._load_recipe_cache()

    def _load_recipe_cache(self):
        try:
            with self._recipe_cache_path.open('rb') as cache_file:
                pickled_cache = cache_file.read()
        except FileNotFoundError:
            return {}
        else:
            return pickle.loads(pickled_cache)

    def dump_recipe_cache(self):
        pickled_cache = pickle.dumps(self._cache)
        new_path = self.local.build_dir / '.recipe.cache.pickle.new'
        with new_path.open('wb') as cache_file:
            cache_file.write(pickled_cache)
        new_path.rename(self._recipe_cache_path)

    @property
    def _recipe_cache_path(self):
        return self.local.build_dir / self._recipe_cache_name

    _recipe_cache_name = 'recipe.cache.pickle'


    def __call__(self, target):
        assert isinstance(target, jeolm.target.Target), type(target)
        try:
            return self.nodes[target]
        except KeyError:
            node = self.nodes[target] = self._prebuild_recipe(target)
            return node

    def _prebuild_recipe(self, target):
        recipe = self.driver.produce_outrecord(target)
        recipe_node = jeolm.node.DatedNode(
            name='document:{}:record'.format(target) )
        recipe_node.recipe = recipe
        recipe_hash = self.object_hash(recipe)

        # Although target can be used as dict key, it is not exactly a good
        # idea to pickle it.
        target_key = (target.path, target.flags.as_frozenset)
        if target_key not in self._cache:
            logger.debug("Metanode {} was not found in cache".format(target))
            modified = True
        elif self._cache[target_key]['hash'] != recipe_hash:
            logger.debug("Metanode {} was found obsolete in cache"
                .format(target) )
            modified = True
        else:
            logger.debug("Metanode {} was found in cache"
                .format(target) )
            modified = False

        if modified:
            recipe_node.touch()
            self._cache[target_key] = {
                'hash' : recipe_hash, 'mtime' : recipe_node.mtime }
            recipe_node.update()
            recipe_node.modified = True
        else:
            recipe_node.mtime = self._cache[target_key]['mtime']
        return recipe_node

    @classmethod
    def object_hash(cls, obj):
        return hashlib.sha256(cls._sorted_repr(obj).encode()).hexdigest()

    @classmethod
    def _sorted_repr(cls, obj):
        """
        Sorted representation of dicts and sets, graceful with OrderedDict.

        Allowed container types:
          OrderedDict, list, dict (items in representation are sorted by keys,
            only str keys are allowed).

        Allowed non-container types:
          str, int, float.
        """
        sorted_repr = cls._sorted_repr
        if obj is None or isinstance(obj, (str, int, float)):
            return repr(obj)
        if isinstance(obj, (PurePosixPath, date)):
            return repr(obj)
        if isinstance(obj, OrderedDict):
            return 'OrderedDict([{}])'.format(', '.join(
                '({}, {})'.format(sorted_repr(key), sorted_repr(value))
                for key, value in obj.items()
            ))
        if isinstance(obj, list):
            return '[{}]'.format(', '.join(
                sorted_repr(item) for item in obj
            ))
        if isinstance(obj, dict):
            assert all(isinstance(key, str) for key in obj.keys())
            return '{{{}}}'.format(', '.join(
                '{}: {}'.format(sorted_repr(key), sorted_repr(value))
                for key, value in sorted(obj.items())
            ))
        raise TypeError(obj)


class PackageNodeFactory:
    package_types = ('dtx', 'sty')

    def __init__(self, *, local, driver,
        build_dir_node, source_node_factory
    ):
        self.local = local
        self.driver = driver
        self.build_dir_node = build_dir_node
        self.source_node_factory = source_node_factory

        self.nodes = dict()

    def __call__(self, metapath):
        assert isinstance(metapath, RecordPath), type(metapath)
        try:
            return self.nodes[metapath]
        except KeyError:
            node = self.nodes[metapath] = self._prebuild_package(metapath)
            return node

    def _prebuild_package(self, metapath):
        package_record = self.driver.produce_package_record(metapath)
        build_subdir = self.build_dir_node.path / package_record['buildname']
        build_subdir_node = jeolm.node.DirectoryNode(
            name='package:{}:dir'.format(metapath),
            path=build_subdir, parents=False,
            needs=(self.build_dir_node,) )
        package_type = package_record['type']
        if package_type not in self.package_types:
            raise RuntimeError(package_type)
        prebuild_method = getattr( self,
            '_prebuild_{}_package'.format(package_type) )
        return prebuild_method( metapath, package_record,
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
        dtx_node = jeolm.node.LinkNode(
            name='package:{}:dtx'.format(metapath),
            source=source_node,
            path=build_dir/'{}.dtx'.format(package_name),
            needs=(build_dir_node,) )
        ins_node = jeolm.node.FileNode(
            name='package:{}:ins'.format(metapath),
            path=build_dir/'package.ins',
            needs=(build_dir_node,) )
        ins_node.add_command(jeolm.node.TextCommand(textfunc=partial(
            self._substitute_ins, package_name=package_name
        )))
        sty_node = jeolm.node.FileNode(
            name='package:{}:sty'.format(metapath),
            path=build_dir/'{}.sty'.format(package_name),
            needs=(build_dir_node, dtx_node, ins_node) )
        sty_node.add_subprocess_command(
            ( 'latex', '-interaction=nonstopmode', '-halt-on-error',
                ins_node.path.name ),
            cwd=build_dir )
        return sty_node

    def _prebuild_sty_package(self, metapath, package_record,
        *, build_dir_node
    ):
        return self.source_node_factory(package_record['source'])


class FigureNodeFactory:
    figure_types = ('asy', 'svg', 'eps')

    def __init__(self, *, local, driver,
        build_dir_node, source_node_factory
    ):
        self.local = local
        self.driver = driver
        self.build_dir_node = build_dir_node
        self.source_node_factory = source_node_factory

        self.nodes = dict()

    def __call__(self, metapath):
        assert isinstance(metapath, RecordPath), type(metapath)
        try:
            return self.nodes[metapath]
        except KeyError:
            node = self.nodes[metapath] = self._prebuild_figure(metapath)
            return node

    def _prebuild_figure(self, metapath):
        figure_record = self.driver.produce_figure_record(metapath)
        build_subdir = self.build_dir_node.path / figure_record['buildname']
        build_subdir_node = jeolm.node.DirectoryNode(
            name='figure:{}:dir'.format(metapath),
            path=build_subdir, parents=False,
            needs=(self.build_dir_node,) )
        figure_type = figure_record['type']
        if figure_type not in self.figure_types:
            raise RuntimeError(figure_type)
        prebuild_method = getattr( self,
            '_prebuild_{}_figure'.format(figure_type) )
        return prebuild_method( metapath, figure_record,
            build_dir_node=build_subdir_node )

    def _prebuild_asy_figure(self, metapath, figure_record,
        *, build_dir_node
    ):
        build_dir = build_dir_node.path
        main_asy_node, *_other_asy_nodes = asy_nodes = \
            list(self._prebuild_asy_figure_sources( metapath, figure_record,
                build_dir_node=build_dir_node ))
        assert main_asy_node.path.parent == build_dir
        eps_node = jeolm.node.FileNode(
            name='figure:{}:eps'.format(metapath),
            path=build_dir/'main.eps',
            needs=chain(asy_nodes, (build_dir_node,)) )
        assert main_asy_node is eps_node.needs[0], asy_nodes
        eps_node.add_subprocess_command(
            ( 'asy', '-outformat=eps', '-offscreen',
                main_asy_node.path.name ),
            cwd=build_dir )
        return eps_node

    def _prebuild_asy_figure_sources(self, metapath, figure_record,
        *, build_dir_node
    ):
        """Yield main asy source node and other source nodes."""
        build_dir = build_dir_node.path
        main_asy_node = jeolm.node.LinkNode(
            name='figure:{}:asy:main'.format(metapath),
            source=self.source_node_factory(
                figure_record['source'] ),
            path=build_dir/'main.asy',
            needs=(build_dir_node,) )
        other_asy_nodes = [
            jeolm.node.LinkNode(
                name='figure:{}:asy:{}'.format(metapath, accessed_name),
                source=self.source_node_factory(inpath),
                path=build_dir/accessed_name,
                needs=(build_dir_node,) )
            for accessed_name, inpath
            in figure_record['accessed_sources'].items() ]
        yield main_asy_node
        yield from other_asy_nodes

    def _prebuild_svg_figure(self, metapath, figure_record,
        *, build_dir_node
    ):
        build_dir = build_dir_node.path
        svg_node = jeolm.node.LinkNode(
            name='figure:{}:svg'.format(metapath),
            source=self.source_node_factory(
                figure_record['source'] ),
            path=build_dir/'main.svg',
            needs=(build_dir_node,) )
        eps_node = jeolm.node.FileNode(
            name='fig:{}:eps'.format(metapath),
            path=build_dir/'main.eps',
            needs=(svg_node, build_dir_node) )
        eps_node.add_subprocess_command(
            ('inkscape', '--export-eps=main.eps', '-without-gui', 'main.svg'),
            cwd=build_dir )
        return eps_node

    def _prebuild_eps_figure(self, metapath, figure_record, *, build_dir_node):
        return self.source_node_factory(figure_record['source'])


class SourceNodeFactory:

    def __init__(self, *, local):
        self.local = local
        self.nodes = dict()

    def __call__(self, inpath):
        assert isinstance(inpath, PurePosixPath), type(inpath)
        assert not inpath.is_absolute(), inpath
        try:
            return self.nodes[inpath]
        except KeyError:
            node = self.nodes[inpath] = self._prebuild_source(inpath)
            return node

    def _prebuild_source(self, inpath):
        source_node = jeolm.node.SourceFileNode(
            name='source:{}'.format(inpath),
            path=self.local.source_dir/inpath )
        if not source_node.path.exists():
            logger.warning(
                "Requested source node {} does not exist as file."
                .format(inpath) )
        return source_node

