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

from .nodes import *
from .target import Target

import logging
logger = logging.getLogger(__name__)

class Builder:
    build_formats = ('pdf', )
    known_formats = ('pdf', 'ps', 'dump')

    def __init__(self, targets, *, fs, driver, force=None, delegate=True):
        self.fs = fs
        self.driver = driver

        self.targets = targets
        assert force in {'latex', 'generate', None}
        self.force = force
        self.delegate = delegate

    def prebuild(self):
        self.outrecords_cache = self.fs.load_outrecords_cache()
        self.metadata_mtime = self.fs.metadata_mtime

        targets = self.targets
        if self.delegate:
            targets = [
                delegated_target.flags_clean_copy(origin='target')
                for delegated_target
                in self.driver.list_delegators(*targets, recursively=True)
            ]
        self.outrecords = outrecords = OrderedDict(
            (target, self.driver.produce_outrecord(target))
            for target in targets )
        figpaths = [ figpath
            for outrecord in outrecords.values()
            for figpath in outrecord['figpaths'].values() ]
        self.figrecords = figrecords = OrderedDict(
            (figpath, self.driver.produce_figrecord(figpath))
            for figpath in figpaths )
        self.cache_updated = False
        self.outnodes = OrderedDict(
            (target, self.create_outnode(target, outrecord))
            for target, outrecord in outrecords.items() )
        if self.cache_updated:
            self.dump_outrecords_cache()

        self.source_nodes = OrderedDict()
        assert set(self.known_formats) >= set(self.build_formats)
        self.exposed_nodes = {fmt : OrderedDict() for fmt in self.build_formats}

        self.prebuild_figures(self.fs.build_dir/'figures')
        self.prebuild_documents(self.fs.build_dir/'documents')

        self.ultimate_node = Node(
            name='ultimate',
            needs=( node
                for fmt in self.build_formats
                for node in self.exposed_nodes[fmt].values()
            ) )

    def build(self):
        if not hasattr(self, 'ultimate_node'):
            self.prebuild()
        self.ultimate_node.update()

    def dump_outrecords_cache(self):
        self.fs.dump_outrecords_cache(self.outrecords_cache)

    def create_outnode(self, target, outrecord):
        target_s = target.__format__('target')
        outnode = DatedNode(name='doc:{:target}:record'.format(target))
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
            cache[target_s] = {
                'hash' : outrecord_hash, 'mtime' : self.metadata_mtime }
            outnode.mtime = self.metadata_mtime
            outnode.modified = True
            self.cache_updated = True
        else:
            outnode.mtime = cache[target_s]['mtime']
        return outnode

    def prebuild_figures(self, build_dir):
        self.eps_nodes = OrderedDict()
        for figpath, figrecord in self.figrecords.items():
            figtype = figrecord['type']
            if figtype == 'asy':
                prebuild_figure = self.prebuild_asy_figure
            elif figtype == 'eps':
                prebuild_figure = self.prebuild_eps_figure
            else:
                raise RuntimeError(figtype, figpath)
            prebuild_figure( figpath, figrecord,
                build_dir/figrecord['buildname'] )

    def prebuild_asy_figure(self, figpath, figrecord, build_dir):
        build_dir_node = DirectoryNode(
            name='fig:{}:dir'.format(figpath),
            path=build_dir, parents=True, )
        source_node = LinkNode(
            name='fig:{}:source:main'.format(figpath),
            source=self.get_source_node(figrecord['source']),
            path=build_dir/'main.asy',
            needs=(build_dir_node,) )
        eps_node = self.eps_nodes[figname] = FileNode(
            name='fig:{}:eps'.format(figpath),
            path=build_dir/'main.eps',
            needs=(source_node, build_dir_node) )
        eps_node.extend_needs(
            LinkNode(
                name='fig:{}:source:{}'.format(figpath, used_name),
                source=self.get_source_node(original_path),
                path=build_dir/used_name,
                needs=(build_dir_node,) )
            for used_name, original_path
            in figrecord['used'].items() )
        eps_node.add_subprocess_rule(
            ('asy', '-offscreen', 'main.asy'), cwd=build_dir )

    def prebuild_eps_figure(self, figname, figrecord, build_dir):
        self.eps_nodes[figname] = self.get_source_node(figrecord['source'])

    def prebuild_documents(self, build_dir):
        self.autosource_nodes = OrderedDict()
        self.dvi_nodes = OrderedDict()
        self.ps_nodes = OrderedDict()
        self.pdf_nodes = OrderedDict()
        self.dump_nodes = OrderedDict()
        for target, outrecord in self.outrecords.items():
            self.prebuild_document(
                target, outrecord, build_dir/outrecord['buildname'] )

    def prebuild_document(self, target, outrecord, build_dir):
        """
        Return nothing. Update self.*_nodes.

        Update self.autosource_nodes, self.pdf_nodes, self.ps_nodes.
        """
        build_dir_node = DirectoryNode(
            name='doc:{:target}:dir'.format(target),
            path=build_dir, parents=True, )
        outnode = self.outnodes[target]
        buildname = outrecord['buildname']
        outname = outrecord['outname']

        def local_name(node):
            return str(node.path.relative_to(build_dir))

        latex_log_name = buildname + '.log'

        autosource_node = self.autosource_nodes[target] = TextNode(
            name='doc:{:target}:autosource'.format(target),
            path=build_dir/'main.tex',
            text=outrecord['document'],
            needs=(outnode, build_dir_node) )
        if self.force == 'generate':
            autosource_node.force()

        linked_sources = [
            LinkNode(
                name='doc:{:target}:source:{}'.format(target, alias),
                source=self.get_source_node(inpath),
                path=build_dir/alias,
                needs=(build_dir_node,) )
            for alias, inpath in outrecord['inpaths'].items() ]
        linked_figures = [
            LinkNode(
                name='doc:{:target}:fig:{}'.format(target, figalias),
                source=self.eps_nodes[figpath],
                path=build_dir/figalias,
                needs=(build_dir_node,) )
            for figalias, figpath in outrecord['figpaths'] ]
        assert len(set(node.name for node in linked_figures)) == \
            len(linked_figures)

        dvi_node = self.dvi_nodes[target] = LaTeXNode(
            name='doc:{:target}:dvi'.format(target),
            source=autosource_node,
            path=(build_dir/buildname).with_suffix('.dvi'),
            cwd=build_dir, )
        dvi_node.extend_needs(linked_sources)
        dvi_node.extend_needs(linked_figures)
        if self.force == 'latex':
            dvi_node.force()

        if 'pdf' in self.build_formats:
            pdf_node = self.pdf_nodes[target] = FileNode(
                name='doc:{:target}:pdf'.format(target),
                path=(build_dir/buildname).with_suffix('.pdf'),
                needs=(dvi_node,) )
            pdf_node.extend_needs(linked_figures)
            pdf_node.add_subprocess_rule(
                ('dvipdf', local_name(dvi_node), local_name(pdf_node)),
                cwd=build_dir )
            self.exposed_nodes['pdf'][target] = LinkNode(
                name='doc:{:target}:exposed:pdf'.format(target),
                source=pdf_node,
                path=(self.fs.root/outname).with_suffix('.pdf') )

        if 'ps' in self.build_formats:
            ps_node = self.ps_nodes[target] = FileNode(
                name='doc:{:target}:ps'.format(target),
                path=(build_dir/buildname).with_suffix('.ps'),
                needs=(dvi_node,) )
            ps_node.extend_needs(linked_figures)
            ps_node.add_subprocess_rule(
                ('dvips', local_name(dvi_node), '-o', local_name(ps_node)),
                cwd=build_dir )
            self.exposed_nodes['ps'][target] = LinkNode(
                name='doc:{:target}:exposed:ps'.format(target),
                source=ps_node,
                path=(self.fs.root/outname).with_suffix('.ps') )

        if 'dump' in self.build_formats:
            dump_node = self.dump_nodes[target] = TextNode(
                name='doc:{:target}:source:dump'.format(target),
                path=build_dir/'dump.tex',
                textfunc=partial(
                    self.resolve_latex_inputs, outrecord['document'] ),
                needs=(outnode, build_dir_node) )
            dump_node.extend_needs(
                self.get_source_node(inpath)
                for inpath in outrecord['inpaths'].values() )
            self.exposed_nodes['dump'][target] = LinkNode(
                name='doc:{:target}:exposed:dump'.format(target),
                source=dump_node,
                path=(self.fs.root/outname).with_suffix('.tex') )

    def get_source_node(self, inpath):
        assert isinstance(inpath, PurePosixPath), repr(inpath)
        assert not inpath.is_absolute(), inpath
        if inpath in self.source_nodes:
            return self.source_nodes[inpath]
        node = self.source_nodes[inpath] = \
            FileNode(name='source:{}'.format(inpath),
                path=self.fs.source_dir/inpath )
        return node

    def resolve_latex_inputs(self, document):
        """
        Create a standalone document (dump).

        Substitute all local LaTeX file inputs (including sources and
        styles).
        """
        return self.latex_input_pattern.sub(self._latex_resolver, document)

    latex_input_pattern = re.compile(r'(?m)'
        r'\\(?:input|usepackage){[^{}]+}'
            r'% (?P<source>[-/\w]+\.(?:tex|sty))$' )

    def _latex_resolver(self, match):
        inpath = PurePosixPath(match.group('source'))
        source_node = self.get_source_node(inpath)
        with source_node.open('r') as f:
            replacement = f.read()
        if inpath.suffix == '.sty':
            if '@' in replacement:
                replacement = '\\makeatletter\n{}\\makeatother'.format(
                    replacement )
        elif inpath.suffix == '.tex':
            pass
        else:
            raise AssertionError(inpath)
        return replacement

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
        assert source.path.suffix == '.tex'
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

