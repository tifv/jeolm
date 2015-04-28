from string import Template
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
logger = logging.getLogger(__name__) # pylint: disable=invalid-name


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
        target_node.extend_needs(
            self.document_node_factory(target)
            for target in targets )
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
        with suppress(KeyError):
            return self.nodes[target]
        node = self.nodes[target] = self._prebuild_document(target)
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
        dvi_node = prebuild_dvi_method( target, recipe,
            build_dir=build_subdir, build_dir_node=build_subdir_node )
        pdf_node = self._prebuild_pdf( target, recipe, dvi_node,
            build_dir=build_subdir, build_dir_node=build_subdir_node )
        return self._prebuild_exposed(target, recipe, pdf_node)

    def _prebuild_dvi_regular(self, target, recipe,
        *, build_dir, build_dir_node
    ):
        main_tex_node = TextNode(
            name='document:{}:main.tex'.format(target),
            path=build_dir/'Main.tex',
            needs=(build_dir_node,),
            text_node_shelf=self.text_node_shelf,
            local=self.local )
        main_tex_node.set_command(jeolm.node.WriteTextCommand(
            main_tex_node, text=recipe['document'] ))

        package_nodes = [
            jeolm.node.symlink.SymLinkedFileNode(
                name='document:{}:sty:{}'.format(target, alias_name),
                source=self.package_node_factory(package_path),
                path=(build_dir/alias_name).with_suffix('.sty'),
                needs=(build_dir_node,) )
            for alias_name, package_path
            in recipe['package_paths'].items() ]
        figure_nodes = [
            jeolm.node.symlink.SymLinkedFileNode(
                name='document:{}:figure:{}'.format(target, alias_name),
                source=self.figure_node_factory(figure_path),
                path=(build_dir/alias_name).with_suffix('.eps'),
                needs=(build_dir_node,) )
            for alias_name, figure_path
            in recipe['figure_paths'].items() ]
        source_nodes = [
            jeolm.node.symlink.SymLinkedFileNode(
                name='document:{}:in.tex:{}'.format(target, alias),
                source=self.source_node_factory(inpath),
                path=build_dir/alias,
                needs=(build_dir_node,) )
            for alias, inpath in recipe['sources'].items() ]

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
            name='document:{}:main.tex'.format(target),
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
            name='document:{}:dtx'.format(target),
            source=source_node,
            path=build_dir/'{}.dtx'.format(package_name),
            needs=(build_dir_node,) )
        ins_node = TextNode(
            name='document:{}:ins'.format(target),
            path=build_dir/'driver.ins',
            needs=(build_dir_node,),
            text_node_shelf=self.text_node_shelf,
            local=self.local )
        ins_node.set_command(jeolm.node.WriteTextCommand( ins_node,
            self._substitute_driver_ins(package_name=package_name) ))
        drv_node = jeolm.node.ProductFileNode(
            name='document:{}:drv'.format(target),
            source=dtx_node,
            path=build_dir/'{}.drv'.format(package_name),
            needs=(ins_node,) )
        drv_node.set_subprocess_command(
            ( 'latex', '-interaction=nonstopmode', '-halt-on-error',
                ins_node.path.name ),
            cwd=build_dir )
        sty_node = jeolm.node.symlink.SymLinkedFileNode(
            name='document:{}:sty'.format(target),
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
            name='document:{}:main.pdf'.format(target),
            source=dvi_node, path=build_dir/'Main.pdf',
            needs=chain(dvi_node.figure_nodes, (build_dir_node,))
        )
        pdf_node.figure_nodes = dvi_node.figure_nodes
        pdf_node.build_dir_node = build_dir_node
        return pdf_node

    def _prebuild_exposed(self, target, recipe, document_node):
        outname = recipe['outname']
        assert '/' not in outname
        return jeolm.node.symlink.SymLinkedFileNode(
            name='document:{}:exposed'.format(target),
            source=document_node,
            path=(self.local.root/outname).with_suffix(
                document_node.path.suffix )
        )


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
            name='package:{}:dtx'.format(metapath),
            source=source_node,
            path=build_dir/'{}.dtx'.format(package_name),
            needs=(build_dir_node,) )
        ins_node = TextNode(
            name='package:{}:ins'.format(metapath),
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


class FigureNodeFactory:
    output_figure_formats = frozenset(('eps', 'pdf', '<pdflatex>'))

    def __init__(self, *, local, driver,
        build_dir_node,
        source_node_factory
    ):
        self.local = local
        self.driver = driver
        self.build_dir_node = build_dir_node
        self.source_node_factory = source_node_factory

        self.nodes = dict()

    def __call__(self, metapath, *, figure_format='eps'):
        assert isinstance(metapath, RecordPath), type(metapath)
        assert figure_format in self.output_figure_formats, figure_format
        try:
            node_dict = self.nodes[metapath]
        except KeyError:
            node_dict = None
        if node_dict is None:
            node_dict = self.nodes[metapath] = \
                self._prebuild_figure(metapath)
            assert node_dict.keys() >= self.output_figure_formats
        return node_dict[figure_format]

    def _prebuild_figure(self, metapath):
        """
        Return a dictionary of nodes.

        Return { figure_format : node
            for figure_format in self.output_figure_formats }.
        """
        figure_record = self.driver.produce_figure_record(metapath)
        buildname = figure_record['buildname']
        assert '/' not in buildname
        build_subdir = self.build_dir_node.path / buildname
        build_subdir_node = jeolm.node.directory.DirectoryNode(
            name='figure:{}:dir'.format(metapath),
            path=build_subdir, parents=False,
            needs=(self.build_dir_node,) )
        source_figure_format = figure_record['source_format']
        if source_figure_format == 'asy':
            prebuild_method = self._prebuild_asy_figure
        elif source_figure_format == 'svg':
            prebuild_method = self._prebuild_svg_figure
        elif source_figure_format == 'eps':
            prebuild_method = self._prebuild_eps_figure
        else:
            raise RuntimeError(metapath, source_figure_format)
        node_dict = prebuild_method( metapath, figure_record,
            build_dir_node=build_subdir_node )
        assert node_dict.keys() >= {'eps', 'pdf'}
        if '<pdflatex>' not in node_dict:
            node_dict['<pdflatex>'] = node_dict['pdf']
        for node in node_dict.values():
            if not hasattr(node, 'metapath'):
                node.metapath = metapath
        return node_dict

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
            source=main_asy_node, path=build_dir/'Main.eps',
            needs=chain((build_dir_node,), other_asy_nodes) )
        eps_node.set_subprocess_command(
            ( 'asy', '-outformat=eps', '-offscreen',
                main_asy_node.path.name ),
            cwd=build_dir )
        pdf_node = jeolm.node.ProductFileNode(
            name='figure:{}:pdf'.format(metapath),
            source=main_asy_node, path=build_dir/'Main.pdf',
            needs=chain((build_dir_node,), other_asy_nodes) )
        pdf_node.set_subprocess_command(
            ( 'asy', '-outformat=pdf', '-offscreen',
                main_asy_node.path.name ),
            cwd=build_dir )
        return {'eps' : eps_node, 'pdf' : pdf_node}

    def _prebuild_asy_figure_sources(self, metapath, figure_record,
        *, build_dir_node
    ):
        """Yield main asy source node and other source nodes."""
        build_dir = build_dir_node.path
        main_asy_node = jeolm.node.symlink.SymLinkedFileNode(
            name='figure:{}:main.asy'.format(metapath),
            source=self.source_node_factory(
                figure_record['source'] ),
            path=build_dir/'Main.asy',
            needs=(build_dir_node,) )
        other_asy_nodes = [
            jeolm.node.symlink.SymLinkedFileNode(
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
        source_svg_node = self.source_node_factory(figure_record['source'])
        svg_node = jeolm.node.symlink.SymLinkedFileNode(
            name='figure:{}:svg'.format(metapath),
            source=source_svg_node, path=build_dir/'Main.svg',
            needs=(build_dir_node,) )
        eps_node = jeolm.node.ProductFileNode(
            name='figure:{}:eps'.format(metapath),
            source=svg_node, path=build_dir/'Main.eps',
            needs=(build_dir_node,) )
        eps_node.set_subprocess_command(
            ('inkscape', '--without-gui',
                '--export-eps={}'.format(eps_node.path.name),
                svg_node.path.name ),
            cwd=build_dir )
        pdf_node = jeolm.node.ProductFileNode(
            name='figure:{}:pdf'.format(metapath),
            source=svg_node, path=build_dir/'Main.pdf',
            needs=(build_dir_node,) )
        pdf_node.set_subprocess_command(
            ('inkscape', '--without-gui',
                '--export-pdf={}'.format(pdf_node.path.name),
                svg_node.path.name ),
            cwd=build_dir )
        return {'eps' : eps_node, 'pdf' : pdf_node}

    def _prebuild_eps_figure(self, metapath, figure_record, *, build_dir_node):
        build_dir = build_dir_node.path
        source_eps_node = self.source_node_factory(figure_record['source'])
        eps_node = jeolm.node.symlink.ProxyNode(
            name='figure:{}:eps'.format(metapath),
            source=source_eps_node )
        linked_eps_node = jeolm.node.symlink.SymLinkedFileNode(
            name='figure:{}:eps:symlink'.format(metapath),
            source=eps_node, path=build_dir/'Main.eps',
            needs=(build_dir_node,) )
        pdf_node = jeolm.node.ProductFileNode(
            name='figure:{}:pdf'.format(metapath),
            source=linked_eps_node, path=build_dir/'Main.pdf',
            needs=(build_dir_node,) )
        pdf_node.set_subprocess_command(
            ('inkscape', '--without-gui',
                '--export-pdf={}'.format(pdf_node.path.name),
                linked_eps_node.path.name ),
            cwd=build_dir )
        return {'eps' : eps_node, 'pdf' : pdf_node }


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
                "Requested source node {} does not exist as file."
                .format(inpath) )
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
            self.log(logging.INFO, "Change in content detected")
            return True
        else:
            self.log(logging.DEBUG, "No change in content detected")
        return False

    def _run_command(self):
        super()._run_command()
        self._shelf[self._key] = self.text_hash
        self.log(logging.DEBUG, "Text database updated")

