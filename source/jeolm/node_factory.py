from string import Template

import hashlib
import dbm.gnu
import shelve

from pathlib import PurePosixPath, Path

import jeolm
import jeolm.local
import jeolm.node
import jeolm.latex_node
import jeolm.records
import jeolm.target

from jeolm.record_path import RecordPath

import logging
logger = logging.getLogger(__name__) # pylint: disable=invalid-name


class TargetNodeFactory:

    def __init__(self, *, local, driver, text_node_factory):
        self.local = local
        self.text_node_factory = text_node_factory
        self.driver = driver

        self.source_node_factory = SourceNodeFactory(local=self.local)
        self.figure_node_factory = FigureNodeFactory(
            local=self.local, driver=self.driver,
            build_dir_node=jeolm.node.DirectoryNode(
                name='figure:dir',
                path=self.local.build_dir/'figures', parents=True ),
            source_node_factory=self.source_node_factory,
        )
        self.package_node_factory = PackageNodeFactory(
            local=self.local, driver=self.driver,
            build_dir_node=jeolm.node.DirectoryNode(
                name='package:dir',
                path=self.local.build_dir/'packages', parents=True ),
            source_node_factory=self.source_node_factory,
            text_node_factory=self.text_node_factory,
        )
        self.document_node_factory = DocumentNodeFactory(
            local=self.local, driver=self.driver,
            build_dir_node=jeolm.node.DirectoryNode(
                name='document:dir',
                path=self.local.build_dir/'documents', parents=True ),
            source_node_factory=self.source_node_factory,
            package_node_factory=self.package_node_factory,
            figure_node_factory=self.figure_node_factory,
            text_node_factory=self.text_node_factory,
        )

    def __call__(self, targets, *, delegate=True, name='target'):
        if delegate:
            targets = [
                delegated_target.flags_clean_copy(origin='target')
                for delegated_target
                in self.driver.list_delegated_targets(
                    *targets, recursively=True )
            ]

        target_node = jeolm.node.TargetNode(name=name)
        target_node.extend_needs(
            self.document_node_factory(target)
            for target in targets )
        return target_node


class DocumentNodeFactory:
    document_types = ('regular', 'standalone', 'latexdoc')

    def __init__(self, *, local, driver,
        build_dir_node,
        source_node_factory, package_node_factory, figure_node_factory,
        text_node_factory
    ):
        self.local = local
        self.driver = driver
        self.build_dir_node = build_dir_node
        self.source_node_factory = source_node_factory
        self.package_node_factory = package_node_factory
        self.figure_node_factory = figure_node_factory
        self.text_node_factory = text_node_factory

        self.nodes = dict()

    def __call__(self, target):
        assert isinstance(target, jeolm.target.Target), type(target)
        try:
            return self.nodes[target]
        except KeyError:
            node = self.nodes[target] = self._prebuild_document(target)
            return node

    def _prebuild_document(self, target):
        recipe = self.driver.produce_outrecord(target)
        buildname = recipe['buildname']
        assert '/' not in buildname
        build_subdir = self.build_dir_node.path / buildname
        build_subdir_node = jeolm.node.DirectoryNode(
            name='document:{}:dir'.format(target),
            path=build_subdir, parents=False,
            needs=(self.build_dir_node,) )
        document_type = recipe['type']
        if document_type not in self.document_types:
            raise RuntimeError(document_type, target)
        if document_type == 'regular':
            prebuild_method = self._prebuild_regular_document
        elif document_type == 'standalone':
            prebuild_method = self._prebuild_standalone_document
        elif document_type == 'latexdoc':
            prebuild_method = self._prebuild_latexdoc_document
        pdf_node = prebuild_method( target, recipe,
            build_dir=build_subdir, build_dir_node=build_subdir_node )
        return self._prebuild_exposed_document(target, recipe, pdf_node)

    def _prebuild_regular_document(self, target, recipe,
        *, build_dir, build_dir_node
    ):
        buildname = recipe['buildname']

        main_tex_node = jeolm.node.FileNode(
            name='document:{}:tex'.format(target),
            path=build_dir/'main.tex',
            needs=(build_dir_node,) )
        main_tex_node.append_needs(self.text_node_factory(
            main_tex_node.path, recipe['document'] ))
        main_tex_node.add_command(jeolm.node.WriteTextCommand.from_text(
            text=recipe['document'] ))

        package_nodes = [
            jeolm.node.LinkedFileNode(
                name='document:{}:sty:{}'.format(target, alias_name),
                source=self.package_node_factory(package_path),
                path=(build_dir/alias_name).with_suffix('.sty'),
                needs=(build_dir_node,) )
            for alias_name, package_path
            in recipe['package_paths'].items() ]
        figure_nodes = [
            jeolm.node.LinkedFileNode(
                name='document:{}:fig:{}'.format(target, alias_name),
                source=self.figure_node_factory(figure_path),
                path=(build_dir/alias_name).with_suffix('.eps'),
                needs=(build_dir_node,) )
            for alias_name, figure_path
            in recipe['figure_paths'].items() ]
        source_nodes = [
            jeolm.node.LinkedFileNode(
                name='document:{}:in.tex:{}'.format(target, alias),
                source=self.source_node_factory(inpath),
                path=build_dir/alias,
                needs=(build_dir_node,) )
            for alias, inpath in recipe['sources'].items() ]

        dvi_node = jeolm.latex_node.LaTeXNode(
            name='document:{}:dvi'.format(target),
            source=main_tex_node,
            path=(build_dir/buildname).with_suffix('.dvi') )
        dvi_node.extend_needs(package_nodes)
        dvi_node.extend_needs(figure_nodes)
        dvi_node.extend_needs(source_nodes)
        return self._prebuild_pdf_document( target,
            dvi_node, figure_nodes, build_dir=build_dir )

    def _prebuild_standalone_document(self, target, recipe,
        *, build_dir, build_dir_node
    ):
        buildname = recipe['buildname']

        source_node = self.source_node_factory(recipe['source'])
        tex_node = jeolm.node.LinkedFileNode(
            name='document:{}:tex'.format(target),
            source=source_node,
            path=build_dir/'main.tex',
            needs=(build_dir_node,) )
        dvi_node = jeolm.latex_node.LaTeXNode(
            name='document:{}:dvi'.format(target),
            source=tex_node,
            path=(build_dir/buildname).with_suffix('.dvi') )
        return self._prebuild_pdf_document( target,
            dvi_node, [], build_dir=build_dir )

    def _prebuild_latexdoc_document(self, target, recipe,
        *, build_dir, build_dir_node
    ):
        buildname = recipe['buildname']
        package_name = recipe['name']

        source_node = self.source_node_factory(recipe['source'])
        dtx_node = jeolm.node.LinkedFileNode(
            name='document:{}:dtx'.format(target),
            source=source_node,
            path=build_dir/'{}.dtx'.format(package_name),
            needs=(build_dir_node,) )
        ins_node = jeolm.node.FileNode(
            name='document:{}:ins'.format(target),
            path=build_dir/'driver.ins',
            needs=(build_dir_node,) )
        ins_text = self._substitute_driver_ins(package_name=package_name)
        ins_node.add_command(jeolm.node.WriteTextCommand.from_text(ins_text))
        ins_node.append_needs(self.text_node_factory(ins_node.path, ins_text))
        drv_node = jeolm.node.ProductFileNode(
            name='document:{}:drv'.format(target),
            source=dtx_node,
            path=build_dir/'{}.drv'.format(package_name),
            needs=(ins_node,) )
        drv_node.add_subprocess_command(
            ( 'latex', '-interaction=nonstopmode', '-halt-on-error',
                ins_node.path.name ),
            cwd=build_dir )
        sty_node = jeolm.node.LinkedFileNode(
            name='document:{}:sty'.format(target),
            source=self.package_node_factory(target.path),
            path=(build_dir/package_name).with_suffix('.sty'),
            needs=(build_dir_node,) )

        dvi_node = jeolm.latex_node.LaTeXNode(
            name='document:{}:dvi'.format(target),
            source=drv_node,
            path=(build_dir/buildname).with_suffix('.dvi'),
            needs=(sty_node, dtx_node) )
        return self._prebuild_pdf_document( target,
            dvi_node, [], build_dir=build_dir )

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

    def _prebuild_pdf_document(self, target,
        dvi_node, figure_nodes, *, build_dir
    ):
        pdf_node = jeolm.node.ProductFileNode(
            name='document:{}:pdf'.format(target),
            source=dvi_node,
            path=build_dir/'main.pdf', )
        pdf_node.extend_needs(figure_nodes)
        pdf_node.add_subprocess_command(
            ('dvipdf', dvi_node.path.name, pdf_node.path.name),
            cwd=build_dir )
        #ps_node = jeolm.node.FileNode(
        #    name='document:{}:ps'.format(target),
        #    path=build_dir/'main.ps',
        #    needs=(dvi_node,) )
        #ps_node.extend_needs(figure_nodes)
        #ps_node.add_subprocess_command(
        #    ('dvips', dvi_node.path.name, '-o', ps_node.path.name),
        #    cwd=build_dir )
        return pdf_node

    def _prebuild_exposed_document(self, target, recipe, document_node):
        outname = recipe['outname']
        assert '/' not in outname
        return jeolm.node.LinkedFileNode(
            name='document:{}:exposed'.format(target),
            source=document_node,
            path=(self.local.root/outname).with_suffix(
                document_node.path.suffix )
        )


class PackageNodeFactory:
    package_types = ('dtx', 'sty')

    def __init__(self, *, local, driver,
        build_dir_node,
        source_node_factory, text_node_factory
    ):
        self.local = local
        self.driver = driver
        self.build_dir_node = build_dir_node
        self.source_node_factory = source_node_factory
        self.text_node_factory = text_node_factory

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
        buildname = package_record['buildname']
        assert '/' not in buildname
        build_subdir = self.build_dir_node.path / buildname
        build_subdir_node = jeolm.node.DirectoryNode(
            name='package:{}:dir'.format(metapath),
            path=build_subdir, parents=False,
            needs=(self.build_dir_node,) )
        package_type = package_record['type']
        if package_type not in self.package_types:
            raise RuntimeError(package_type, metapath)
        if package_type == 'dtx':
            prebuild_method = self._prebuild_dtx_package
        elif package_type == 'sty':
            prebuild_method = self._prebuild_sty_package
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
        dtx_node = jeolm.node.LinkedFileNode(
            name='package:{}:dtx'.format(metapath),
            source=source_node,
            path=build_dir/'{}.dtx'.format(package_name),
            needs=(build_dir_node,) )
        ins_node = jeolm.node.FileNode(
            name='package:{}:ins'.format(metapath),
            path=build_dir/'package.ins',
            needs=(build_dir_node,) )
        ins_text = self._substitute_ins(package_name=package_name)
        ins_node.add_command(jeolm.node.WriteTextCommand.from_text(ins_text))
        ins_node.append_needs(self.text_node_factory(ins_node.path, ins_text))
        sty_node = jeolm.node.ProductFileNode(
            name='package:{}:sty'.format(metapath),
            source=dtx_node,
            path=build_dir/'{}.sty'.format(package_name),
            needs=(ins_node,) )
        sty_node.add_subprocess_command(
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


class FigureNodeFactory:
    figure_types = ('asy', 'svg', 'eps')

    def __init__(self, *, local, driver,
        build_dir_node,
        source_node_factory
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
        buildname = figure_record['buildname']
        assert '/' not in buildname
        build_subdir = self.build_dir_node.path / buildname
        build_subdir_node = jeolm.node.DirectoryNode(
            name='figure:{}:dir'.format(metapath),
            path=build_subdir, parents=False,
            needs=(self.build_dir_node,) )
        figure_type = figure_record['type']
        if figure_type not in self.figure_types:
            raise RuntimeError(figure_type, metapath)
        if figure_type == 'asy':
            prebuild_method = self._prebuild_asy_figure
        elif figure_type == 'svg':
            prebuild_method = self._prebuild_svg_figure
        elif figure_type == 'eps':
            prebuild_method = self._prebuild_eps_figure
        return prebuild_method( metapath, figure_record,
            build_dir_node=build_subdir_node )

    def _prebuild_asy_figure(self, metapath, figure_record,
        *, build_dir_node
    ):
        build_dir = build_dir_node.path
        main_asy_node, *other_asy_nodes = \
            list(self._prebuild_asy_figure_sources( metapath, figure_record,
                build_dir_node=build_dir_node ))
        assert main_asy_node.path.parent == build_dir
        eps_node = jeolm.node.ProductFileNode(
            name='figure:{}:eps'.format(metapath),
            source=main_asy_node,
            path=build_dir/'main.eps',
            needs=other_asy_nodes )
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
        main_asy_node = jeolm.node.LinkedFileNode(
            name='figure:{}:asy:main'.format(metapath),
            source=self.source_node_factory(
                figure_record['source'] ),
            path=build_dir/'main.asy',
            needs=(build_dir_node,) )
        other_asy_nodes = [
            jeolm.node.LinkedFileNode(
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
        svg_node = jeolm.node.LinkedFileNode(
            name='figure:{}:svg'.format(metapath),
            source=self.source_node_factory(
                figure_record['source'] ),
            path=build_dir/'main.svg',
            needs=(build_dir_node,) )
        eps_node = jeolm.node.ProductFileNode(
            name='fig:{}:eps'.format(metapath),
            source=svg_node,
            path=build_dir/'main.eps' )
        eps_node.add_subprocess_command(
            ('inkscape', '--without-gui',
                '--export-eps={}'.format(eps_node.path.name),
                svg_node.path.name ),
            cwd=build_dir )
        return eps_node

    # pylint: disable=unused-argument,unused-variable

    def _prebuild_eps_figure(self, metapath, figure_record, *, build_dir_node):
        return self.source_node_factory(figure_record['source'])

    # pylint: enable=unused-argument,unused-variable


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


class TextNodeFactory:

    def __init__(self, *, local):
        self.local = local
        self.nodes = dict()
        self.shelf_db = dbm.gnu.open(str(self._db_path), 'cf')
        self.shelf = shelve.Shelf(self.shelf_db)

    @property
    def _db_path(self):
        return self.local.build_dir / self._db_name

    _db_name = 'textnodes.db'

    def __call__(self, path, text):
        assert isinstance(path, Path), type(path)
        if path.is_absolute():
            path = path.relative_to(self.local.root)
        assert not path.is_absolute(), path
        try:
            node = self.nodes[path]
        except KeyError:
            node = self.nodes[path] = self._load_node(path)
        text_hash = hashlib.sha256(text.encode()).digest()
        if node.text_hash == text_hash:
            node.log(logging.DEBUG, "Text not changed")
            return node
        node.log(logging.INFO, "Text has UPDATED")
        node.text_hash = text_hash
        node.touch()
        self._dump_node(path, node)
        return node

    def _load_node(self, path):
        node = jeolm.node.DatedNode(name='text:{}'.format(path))
        record = self.shelf.get(str(path))
        if record is not None:
            assert isinstance(record, dict), type(record)
            assert len(record) == 2, record.keys()
            node.text_hash = record['text_hash']
            node.mtime = record['mtime']
        else:
            node.text_hash = node.mtime = None
        node.update()
        return node

    def _dump_node(self, path, node):
        record = {'text_hash' : node.text_hash, 'mtime' : node.mtime}
        self.shelf[str(path)] = record
        if record is not None:
            node.text_hash = record['text_hash']
            node.mtime = record['mtime']
        else:
            node.text_hash = node.mtime = None
        node.update()
        return node

    def sync(self):
        self.shelf.sync()
        self.shelf_db.sync() # probably redundant

    def close(self):
        self.shelf.close()
        self.shelf_db.close() # probably redundant

