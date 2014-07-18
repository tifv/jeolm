from string import Template
from collections import OrderedDict
from itertools import chain
from functools import partial
from datetime import date

import os
import re
import hashlib
import json
import subprocess

from pathlib import Path, PurePosixPath

from .nodes import (
    Node, DatedNode, FileNode, TextNode, ProductFileNode,
    LinkNode, DirectoryNode )
from .target import Target

import logging
logger = logging.getLogger(__name__)

class Builder:
    build_formats = ('pdf', )
    known_formats = ('pdf', 'ps', 'dump')

    def __init__(self, targets, *, fs, driver,
        force=None, delegate=True, executor=None
    ):
        self.fs = fs
        self.driver = driver

        self.targets = targets
        assert force in {'latex', 'generate', None}
        self.force = force
        self.delegate = delegate

        self.executor = executor

    def prebuild(self):
        self.outrecords_cache = self.fs.load_outrecords_cache()

        targets = self.targets
        if self.delegate:
            targets = [
                delegated_target.flags_clean_copy(origin='target')
                for delegated_target
                in self.driver.list_delegated_targets(
                    *targets, recursively=True )
            ]
        self.outrecords = outrecords = OrderedDict(
            (target, self.driver.produce_outrecord(target))
            for target in targets )
        figure_paths = [ figure_path
            for outrecord in outrecords.values()
            if outrecord['type'] in {'regular'}
            for figure_path in outrecord['figure_paths'].values() ]
        package_paths = [ package_path
            for outrecord in outrecords.values()
            if outrecord['type'] in {'regular', 'latexdoc'}
            for package_path in outrecord['package_paths'].values() ]
        self.figure_records = figure_records = OrderedDict(
            (figure_path, self.driver.produce_figure_record(figure_path))
            for figure_path in figure_paths )
        self.package_records = package_records = OrderedDict(
            (package_path, self.driver.produce_package_record(package_path))
            for package_path in package_paths )
        self.cache_updated = False
        self.outnodes = OrderedDict(
            (target, self.create_outnode(target, outrecord))
            for target, outrecord in outrecords.items() )
        if self.cache_updated:
            self.dump_outrecords_cache()

        self.source_nodes = OrderedDict()
        assert set(self.known_formats) >= set(self.build_formats)

        self.prebuild_figures(self.fs.build_dir/'figures')
        self.prebuild_packages(self.fs.build_dir/'packages')
        self.prebuild_documents(self.fs.build_dir/'documents')

        self.ultimate_node = Node(
            name='ultimate',
            needs=( node
                for build_format in self.build_formats
                for node in self.exposed_nodes[build_format].values()
            ) )

    def build(self):
        if not hasattr(self, 'ultimate_node'):
            self.prebuild()
        self.ultimate_node.update(executor=self.executor)
        if self.executor is not None:
            self.ultimate_node.update()

    def dump_outrecords_cache(self):
        self.fs.dump_outrecords_cache(self.outrecords_cache)

    def create_outnode(self, target, outrecord):
        target_s = str(target)
        outnode = DatedNode(name='doc:{}:record'.format(target))
        outnode.record = outrecord
        cache = self.outrecords_cache
        outrecord_hash = self.outrecord_hash(outrecord)

        if target_s not in cache:
            logger.debug("Metanode {} was not found in cache"
                .format(target_s) )
            modified = True
        elif cache[target_s]['hash'] != outrecord_hash:
            logger.debug("Metanode {} was found obsolete in cache"
                .format(target_s) )
            modified = True
        else:
            logger.debug("Metanode {} was found in cache"
                .format(target_s) )
            modified = False

        if modified:
            outnode.set_mtime_to_now()
            cache[target_s] = {
                'hash' : outrecord_hash, 'mtime' : outnode.mtime }
            outnode.modified = True
            self.cache_updated = True
        else:
            outnode.mtime = cache[target_s]['mtime']
        return outnode

    def prebuild_figures(self, build_dir):
        self.figure_nodes = {
            figure_outtype : OrderedDict()
            for figure_outtype in ('eps', 'pdf') }
        for figure_path, figure_record in self.figure_records.items():
            build_subdir = build_dir / figure_record['buildname']
            build_dir_node = DirectoryNode(
                name='fig:{}:dir'.format(figure_path),
                path=build_subdir, parents=True, )
            figure_type = figure_record['type']
            if figure_type == 'asy':
                prebuild_figure = self.prebuild_asy_figure
            elif figure_type == 'eps':
                prebuild_figure = self.prebuild_eps_figure
            elif figure_type == 'svg':
                prebuild_figure = self.prebuild_svg_figure
            else:
                raise RuntimeError(figure_type, figure_path)
            prebuild_figure( figure_path, figure_record,
                build_dir=build_subdir,
                build_dir_node=build_dir_node )

    def prebuild_asy_figure(self, figure_path, figure_record,
        *, build_dir, build_dir_node
    ):
        main_asy_node = LinkNode(
            name='fig:{}:asy:main'.format(figure_path),
            source=self.get_source_node(figure_record['source']),
            path=build_dir/'main.asy',
            needs=(build_dir_node,) )
        other_asy_nodes = [
            LinkNode(
                name='fig:{}:asy:{}'.format(figure_path, accessed_name),
                source=self.get_source_node(inpath),
                path=build_dir/accessed_name,
                needs=(build_dir_node,) )
            for accessed_name, inpath
            in figure_record['accessed_sources'].items() ]
        eps_node = self.figure_nodes['eps'][figure_path] = FileNode(
            name='fig:{}:eps'.format(figure_path),
            path=build_dir/'main.eps',
            needs=(main_asy_node, build_dir_node) )
        eps_node.extend_needs(other_asy_nodes)
        eps_node.add_subprocess_rule(
            ('asy', '-outformat=eps', '-offscreen', 'main.asy'),
            cwd=build_dir )
        pdf_node = self.figure_nodes['pdf'][figure_path] = FileNode(
            name='fig:{}:pdf'.format(figure_path),
            path=build_dir/'main.pdf',
            needs=(main_asy_node, build_dir_node) )
        pdf_node.extend_needs(other_asy_nodes)
        pdf_node.add_subprocess_rule(
            ('asy', '-outformat=pdf', '-offscreen', 'main.asy'),
            cwd=build_dir )

    def prebuild_svg_figure(self, figure_path, figure_record,
        *, build_dir, build_dir_node
    ):
        svg_node = LinkNode(
            name='fig:{}:svg'.format(figure_path),
            source=self.get_source_node(figure_record['source']),
            path=build_dir/'main.svg',
            needs=(build_dir_node,) )
        eps_node = self.figure_nodes['eps'][figure_path] = FileNode(
            name='fig:{}:eps'.format(figure_path),
            path=build_dir/'main.eps',
            needs=(svg_node, build_dir_node) )
        eps_node.add_subprocess_rule(
            ('inkscape', '--export-eps=main.eps', '-without-gui', 'main.svg'),
            cwd=build_dir )
        pdf_node = self.figure_nodes['pdf'][figure_path] = FileNode(
            name='fig:{}:pdf'.format(figure_path),
            path=build_dir/'main.pdf',
            needs=(svg_node, build_dir_node) )
        pdf_node.add_subprocess_rule(
            ('inkscape', '--export-pdf=main.pdf', '-without-gui', 'main.svg'),
            cwd=build_dir )

    def prebuild_eps_figure(self, figure_path, figure_record,
        *, build_dir, build_dir_node
    ):
        source_node = self.get_source_node(figure_record['source'])
        eps_node = LinkNode(
            name='fig:{}:eps'.format(figure_path),
            source=source_node,
            path=build_dir/'main.eps',
            needs=(build_dir_node,) )
        self.figure_nodes['eps'][figure_path] = source_node
        pdf_node = self.figure_nodes['pdf'][figure_path] = FileNode(
            name='fig:{}:pdf'.format(figure_path),
            path=build_dir/'main.pdf',
            needs=(eps_node, build_dir_node) )
        pdf_node.add_subprocess_rule(
            ('inkscape', '--export-pdf=main.pdf', '-without-gui', 'main.eps'),
            cwd=build_dir )

    def prebuild_packages(self, build_dir):
        self.package_nodes = OrderedDict()
        for package_path, package_record in self.package_records.items():
            build_subdir = build_dir / package_record['buildname']
            build_dir_node = DirectoryNode(
                name='sty:{}:dir'.format(package_path),
                path=build_subdir, parents=True, )
            package_type = package_record['type']
            if package_type == 'dtx':
                prebuild_package = self.prebuild_dtx_package
            elif package_type == 'sty':
                prebuild_package = self.prebuild_sty_package
            else:
                raise RuntimeError(package_type, package_path)
            prebuild_package( package_path, package_record,
                build_dir=build_subdir,
                build_dir_node=build_dir_node )

    package_ins_template = (
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
        r"\endinput"
    )
    substitute_package_ins = Template(package_ins_template).substitute

    def prebuild_dtx_package(self, package_path, package_record,
        *, build_dir, build_dir_node
    ):
        source_node = self.get_source_node(package_record['source'])
        package_name = package_record['name']
        dtx_node = LinkNode(
            name='sty:{}:dtx'.format(package_path),
            source=source_node,
            path=build_dir/'{}.dtx'.format(package_name),
            needs=(build_dir_node,) )
        ins_node = TextNode(
            name='sty:{}:ins'.format(package_path),
            path=build_dir/'package.ins',
            text=self.substitute_package_ins(package_name=package_name),
            needs=(build_dir_node,) )
        sty_node = self.package_nodes[package_path] = FileNode(
            name='sty:{}:sty'.format(package_path),
            path=build_dir/'{}.sty'.format(package_name),
            needs=(build_dir_node, dtx_node, ins_node) )
        sty_node.add_subprocess_rule(
            ('latex', '-interaction=nonstopmode',
                '-halt-on-error', '-file-line-error', 'package.ins'),
            cwd=build_dir )

    def prebuild_sty_package(self, package_path, package_record,
        *, build_dir, build_dir_node
    ):
        sty_node = self.package_nodes[package_path] = \
            self.get_source_node(package_record['source'])

    def prebuild_documents(self, build_dir):
        self.document_nodes = {
            build_format : OrderedDict()
            for build_format in self.known_formats }
        self.exposed_nodes = {
            build_format : OrderedDict()
            for build_format in self.known_formats }
        for target, outrecord in self.outrecords.items():
            build_subdir = build_dir / outrecord['buildname']
            build_dir_node = DirectoryNode(
                name='doc:{}:dir'.format(target),
                path=build_subdir, parents=True, )
            document_type = outrecord['type']
            if document_type == 'regular':
                prebuild_document = self.prebuild_regular_document
            elif document_type == 'standalone':
                prebuild_document = self.prebuild_standalone_document
            elif document_type == 'latexdoc':
                prebuild_document = self.prebuild_latexdoc_document
            else:
                raise RuntimeError(document_type, target)
            prebuild_document( target, outrecord,
                build_dir=build_subdir,
                build_dir_node=build_dir_node )
            self.prebuild_document_exposed(target, outrecord)

    def prebuild_regular_document(self, target, outrecord,
        *, build_dir, build_dir_node
    ):
        """
        Return nothing.
        Update self.autosource_nodes, self.document_nodes.
        """
        buildname = outrecord['buildname']

        main_tex_node = TextNode(
            name='doc:{}:autosource'.format(target),
            path=build_dir/'main.tex',
            text=outrecord['document'],
            needs=(self.outnodes[target], build_dir_node) )
        if self.force == 'generate':
            main_tex_node.force()

        source_nodes = [
            LinkNode(
                name='doc:{}:source:{}'.format(target, alias),
                source=self.get_source_node(inpath),
                path=build_dir/alias,
                needs=(build_dir_node,) )
            for alias, inpath in outrecord['sources'].items() ]
        figure_nodes = [
            LinkNode(
                name='doc:{}:fig:{}'.format(target, alias_name),
                source=self.figure_nodes['eps'][figure_path],
                path=(build_dir/alias_name).with_suffix('.eps'),
                needs=(build_dir_node,) )
            for alias_name, figure_path
            in outrecord['figure_paths'].items() ]
        package_nodes = [
            LinkNode(
                name='doc:{}:sty:{}'.format(target, alias_name),
                source=self.package_nodes[package_path],
                path=(build_dir/alias_name).with_suffix('.sty'),
                needs=(build_dir_node,) )
            for alias_name, package_path
            in outrecord['package_paths'].items() ]

        dvi_node = LaTeXNode(
            name='doc:{}:dvi'.format(target),
            source=main_tex_node,
            path=(build_dir/buildname).with_suffix('.dvi'),
            cwd=build_dir, )
        dvi_node.extend_needs(source_nodes)
        dvi_node.extend_needs(figure_nodes)
        dvi_node.extend_needs(package_nodes)
        if self.force == 'latex':
            dvi_node.force()
        self.prebuild_document_postdvi( target, dvi_node, figure_nodes,
            build_dir=build_dir )
        if 'dump' in self.build_formats:
            self.prebuild_document_dump( target, outrecord,
                build_dir=build_dir,
                build_dir_node=build_dir_node )

    def prebuild_document_dump(self, target, outrecord,
        *, build_dir, build_dir_node
    ):
        if outrecord['figure_paths']:
            logger.warning("Cannot properly dump a document with figures.")
        dump_node = self.document_nodes['dump'][target] = TextNode(
            name='doc:{}:dump'.format(target),
            path=build_dir/'dump.tex',
            textfunc=partial(self.supply_filecontents, outrecord),
            needs=(self.outnodes[target], build_dir_node) )
        dump_node.extend_needs(
            self.get_source_node(inpath)
            for inpath in outrecord['sources'].values() )
        dump_node.extend_needs(
            self.package_nodes[package_path]
            for package_path in outrecord['package_paths'].values() )

    def supply_filecontents(self, outrecord):
        pieces = []
        for alias_name, package_path in outrecord['package_paths'].items():
            package_node = self.package_nodes[package_path]
            with package_node.open() as f:
                contents = f.read().strip('\n')
            pieces.append(self.substitute_filecontents(
                filename=alias_name + '.sty', contents=contents ))
        for alias, inpath in outrecord['sources'].items():
            source_node = self.get_source_node(inpath)
            with source_node.open('r') as f:
                contents = f.read().strip('\n')
            pieces.append(self.substitute_filecontents(
                filename=alias, contents=contents ))
        pieces.append(outrecord['document'])
        return '\n'.join(pieces)

    filecontents_template = (
        r"\begin{filecontents*}{$filename}" '\n'
        r"$contents" '\n'
        r"\end{filecontents*}" '\n' )
    substitute_filecontents = Template(filecontents_template).substitute

    def prebuild_standalone_document(self, target, outrecord,
        *, build_dir, build_dir_node
    ):
        buildname = outrecord['buildname']

        source_node = self.get_source_node(outrecord['source'])
        tex_node = LinkNode(
            name='doc:{}:tex'.format(target),
            source=source_node,
            path=build_dir/'main.tex',
            needs=(build_dir_node,) )
        dvi_node = LaTeXNode(
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

    driver_ins_template = (
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
    substitute_driver_ins = Template(driver_ins_template).substitute

    def prebuild_latexdoc_document(self, target, outrecord,
        *, build_dir, build_dir_node
    ):
        buildname = outrecord['buildname']
        package_name = outrecord['name']

        source_node = self.get_source_node(outrecord['source'])
        dtx_node = LinkNode(
            name='doc:{}:dtx'.format(target),
            source=source_node,
            path=build_dir/'{}.dtx'.format(package_name),
            needs=(build_dir_node,) )
        ins_node = TextNode(
            name='doc:{}:ins'.format(target),
            path=build_dir/'driver.ins',
            text=self.substitute_driver_ins(package_name=package_name),
            needs=(self.outnodes[target], build_dir_node,) )
        if self.force == 'generate':
            ins_node.force()
        drv_node = FileNode(
            name='doc:{}:drv'.format(target),
            path=build_dir/'{}.drv'.format(package_name),
            needs=(build_dir_node, dtx_node, ins_node) )
        drv_node.add_subprocess_rule(
            ('latex', '-interaction=nonstopmode',
                '-halt-on-error', '-file-line-error', 'driver.ins'),
            cwd=build_dir )
        sty_node = LinkNode(
            name='doc:{}:sty'.format(target),
            source=self.package_nodes[target.path],
            path=(build_dir/package_name).with_suffix('.sty'),
            needs=(build_dir_node,) )

        dvi_node = LaTeXNode(
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
            raise ValueError("LaTeX package documentation {} cannot be dumped."
                .format(target) )

    def prebuild_document_postdvi(self, target, dvi_node, figure_nodes,
        *, build_dir
    ):
        pdf_node = self.document_nodes['pdf'][target] = FileNode(
            name='doc:{}:pdf'.format(target),
            path=dvi_node.path.with_suffix('.pdf'),
            needs=(dvi_node,) )
        pdf_node.extend_needs(figure_nodes)
        pdf_node.add_subprocess_rule(
            ('dvipdf', dvi_node.path.name, pdf_node.path.name),
            cwd=build_dir )
        ps_node = self.document_nodes['ps'][target] = FileNode(
            name='doc:{}:ps'.format(target),
            path=dvi_node.path.with_suffix('.ps'),
            needs=(dvi_node,) )
        ps_node.extend_needs(figure_nodes)
        ps_node.add_subprocess_rule(
            ('dvips', dvi_node.path.name, '-o', ps_node.path.name),
            cwd=build_dir )

    def prebuild_document_exposed(self, target, outrecord):
        for build_format in self.build_formats:
            document_node = self.document_nodes[build_format][target]
            self.exposed_nodes[build_format][target] = LinkNode(
                name='doc:{}:exposed:{}'.format(target, build_format),
                source=document_node,
                path=(self.fs.root/outrecord['outname'])
                    .with_suffix(document_node.path.suffix)
            )

    def get_source_node(self, inpath):
        assert isinstance(inpath, PurePosixPath), repr(inpath)
        assert not inpath.is_absolute(), inpath
        if inpath in self.source_nodes:
            return self.source_nodes[inpath]
        node = self.source_nodes[inpath] = \
            FileNode(name='source:{}'.format(inpath),
                path=self.fs.source_dir/inpath )
        if not node.path.exists():
            logger.warning( "Requested source node {} does not exist as file."
                .format(inpath) )
        return node

    @classmethod
    def outrecord_hash(cls, outrecord):
        return hashlib.md5(json.dumps(cls.sterilize(outrecord),
            ensure_ascii=True, sort_keys=True,
        ).encode('ascii')).hexdigest()

    @classmethod
    def sterilize(cls, obj):
        """Sterilize object for JSON dumping."""
        sterilize = cls.sterilize
        if isinstance(obj, OrderedDict):
            return OrderedDict(
                (sterilize(k), sterilize(v)) for k, v in obj.items() )
        elif isinstance(obj, dict):
            return {sterilize(k) : sterilize(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [sterilize(i) for i in obj]
#        elif isinstance(obj, set):
#            return {sterilize(i) : None for i in obj}
        elif obj is None or isinstance(obj, (str, int, float)):
            return obj
        elif isinstance(obj, (PurePosixPath, date)):
            return str(obj)
        else:
            raise TypeError(type(obj))

class LaTeXNode(ProductFileNode):
    """
    Represents a target of some latex command.

    Aims at reasonable handling of latex output to stdin/log.
    Completely suppresses latex output unless finds something
    interesting in it.
    """

    latex_command = 'latex'
    target_suffix = '.dvi'

    def __init__(self, source, path, *, cwd, **kwargs):
        super().__init__(source, path, **kwargs)

        if not isinstance(cwd, Path):
            raise TypeError(type(cwd))
        if not cwd.is_absolute():
            raise ValueError(cwd)

        # Ensure that both latex source and target are in the same directory
        # and this directory is cwd.
        assert path.parent == cwd == source.path.parent
        assert path.suffix == self.target_suffix
        jobname = path.stem

        rule_repr = (
            '<cwd=<BLUE>{cwd}<NOCOLOUR>> '
            '<GREEN>{node.latex_command} -jobname={jobname} '
                '{node.source.path.name}<NOCOLOUR>'
            .format(
                cwd=self.root_relative(cwd), jobname=jobname,
                node=self )
        )
        callargs = (self.latex_command,
            '-jobname={}'.format(jobname),
            '-interaction=nonstopmode', '-halt-on-error', '-file-line-error',
            self.source.path.name )
        @self.add_rule
        def latex_rule():
            source_path = self.source.path
            self.log(logging.INFO, rule_repr)
            try:
                output = subprocess.check_output(callargs, cwd=str(cwd),
                    universal_newlines=False )
            except subprocess.CalledProcessError as exception:
                self.check_latex_log(
                    exception.output, logpath=None, critical=True )
                self.log(logging.CRITICAL,
                    '{exc.cmd} returned code {exc.returncode}<RESET>'
                    .format(node=self, exc=exception) )
                exception.reported = True
                raise
            self.check_latex_log(
                output, logpath=self.path.with_suffix('.log') )

    latex_decoding_kwargs = {'encoding' : 'cp1251', 'errors' : 'replace'}

    def check_latex_log(self, output, logpath, critical=False):
        """
        Print some of LaTeX output from its stdout and log.

        Print output if it is interesting or critical is True.
        Otherwise, print overfulls from log (if logpath is not None).
        """
        output = output.decode(**self.latex_decoding_kwargs)
        if critical:
            print(output)
        elif self.latex_output_need_rerun(output):
            print(output)
            try:
                sourcestat = self.source.stat()
                os.utime(
                    str(self.path),
                    ns=(sourcestat.st_atime_ns-1, sourcestat.st_mtime_ns-1) )
                self.modified = True
                self.log(logging.WARNING, 'Next run will rebuild the target.')
            except FileNotFoundError:
                pass
        elif self.latex_output_is_alarming(output):
            print(output)
            self.log(logging.WARNING, 'Alarming LaTeX output detected.')
        elif logpath is not None:
            self.print_overfulls(logpath)

    latex_output_alarming_pattern = re.compile(
        r'(?m)^! |[Ee]rror|[Ww]arning|No pages of output.' )
    @classmethod
    def latex_output_is_alarming(cls, output):
        return cls.latex_output_alarming_pattern.search(output) is not None

    latex_output_rerun_pattern = re.compile(r'[Rr]erun to')
    @classmethod
    def latex_output_need_rerun(cls, output):
        return cls.latex_output_rerun_pattern.search(output) is not None

    latex_log_overfull_pattern = re.compile(
        r'(?m)^(Overfull|Underfull)\s+\\hbox\s+\([^()]*?\)\s+'
        r'in\s+paragraph\s+at\s+lines\s+\d+--\d+' )
    latex_log_page_pattern = re.compile(r'\[(?P<number>(?:\d|\s)+)\]')

    def print_overfulls(self, logpath):
        enc_args = {}
        with logpath.open(**self.latex_decoding_kwargs) as f:
            s = f.read()

        page_marks = {1 : 0}
        last_page = 1; last_mark = 0
        while True:
            for match in self.latex_log_page_pattern.finditer(s):
                value = match.group('number').replace('\n', '')
                if not value:
                    continue
                try:
                    value = int(value)
                except ValueError:
                    logger.warning(
                        "Error while parsing log file: '{}'".format(
                            match.group(0)
                                .encode('unicode_escape').decode('utf-8')
                        ) )
                    continue
                else:
                    if value == last_page + 1:
                        break
            else:
                break
            last_page += 1
            last_mark = match.end()
            page_marks[last_page] = last_mark
        def current_page(pos):
            page = max(
                (
                    (page, mark)
                    for (page, mark) in page_marks.items()
                    if mark <= pos
                ), key=lambda v:v[1])[0]
            if page == 1:
                return '1--2'
            else:
                return page + 1

        for match in self.latex_log_overfull_pattern.finditer(s):
            start = match.start()
            print(
                '[{}]'.format(current_page(match.start())),
                match.group(0) )

class Dumper(Builder):
    build_formats = ('dump', )

