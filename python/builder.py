from collections import OrderedDict as ODict
from itertools import chain
from functools import partial
from datetime import date

import os
import re
import hashlib
import json
import subprocess

from pathlib import Path, PurePosixPath as PurePath

from .nodes import *

from . import filesystem, driver

import logging
logger = logging.getLogger(__name__)

class Builder:
    build_formats = ('pdf', )
    known_formats = ('pdf', 'ps', 'dump')

    def __init__(self, targets, *, fsmanager, force_recompile):
        self.fsmanager = fsmanager
        self.root = self.fsmanager.root
        self.force_recompile = force_recompile

        self.driver = self.fsmanager.get_driver()
        self.metarecords_cache = self.fsmanager.load_metarecords_cache()
        self.records_mtime = self.fsmanager.records_mtime

        self.metarecords, self.figrecords = \
            self.driver.produce_metarecords(targets)
        self.cache_updated = False
        self.metanodes = ODict(
            (metaname, self.create_metanode(metaname, metarecord))
            for metaname, metarecord, in self.metarecords.items() )
        if self.cache_updated:
            self.dump_meta_cache()

        self.source_nodes = ODict()
        assert set(self.known_formats) >= set(self.build_formats)
        self.exposed_nodes = {fmt : ODict() for fmt in self.build_formats}

        self.prebuild_figures(self.fsmanager.build_dir/'figures')
        self.prebuild_documents(self.fsmanager.build_dir/'documents')

        self.ultimate_node = Node(
            name='ultimate',
            needs=( node
                for fmt in self.build_formats
                for node in self.exposed_nodes[fmt].values()
            ) )

    def update(self):
        self.ultimate_node.update()

    def dump_meta_cache(self):
        self.fsmanager.dump_metarecords_cache(self.metarecords_cache)

    def create_metanode(self, metaname, metarecord):
        metanode = DatedNode(name='doc:{}:meta'.format(metaname))
        metanode.record = metarecord
        cache = self.metarecords_cache
        metarecord_hash = self.metarecord_hash(metarecord)

        if metaname not in cache:
            logger.debug("Metanode {} was not found in cache"
                .format(metaname) )
            modified = True
        elif cache[metaname]['hash'] != metarecord_hash:
            logger.debug("Metanode {} was found obsolete in cache"
                .format(metaname) )
            modified = True
        else:
            logger.debug("Metanode {} was found in cache"
                .format(metaname) )
            modified = False

        if modified:
            cache[metaname] = {
                'hash' : metarecord_hash, 'mtime' : self.records_mtime }
            metanode.mtime = self.records_mtime
            metanode.modified = True
            self.cache_updated = True
        else:
            metanode.mtime = cache[metaname]['mtime']
        return metanode

    def prebuild_figures(self, build_dir):
        self.eps_nodes = ODict()
        for figname, figrecord in self.figrecords.items():
            self.prebuild_figure(figname, figrecord, build_dir/figname)

    def prebuild_figure(self, figname, figrecord, build_dir):
        figtype = figrecord['type']
        if figtype == 'asy':
            self.prebuild_asy_figure(
                figname, figrecord, build_dir=build_dir )
        elif figtype == 'eps':
            self.prebuild_eps_figure(
                figname, figrecord, build_dir=build_dir )
        else:
            raise AssertionError(figtype, figname)

    def prebuild_asy_figure(self, figname, figrecord, build_dir):
        build_dir_node = DirectoryNode(
            name='fig:{}:dir'.format(figname),
            path=build_dir, parents=True, )
        source_node = LinkNode(
            name='fig:{}:source:main'.format(figname),
            source=self.get_source_node(figrecord['source']),
            path=build_dir/'main.asy',
            needs=(build_dir_node,) )
        eps_node = self.eps_nodes[figname] = FileNode(
            name='fig:{}:eps'.format(figname),
            path=build_dir/'main.eps',
            needs=(source_node, build_dir_node) )
        eps_node.extend_needs(
            LinkNode(
                name='fig:{}:source:{}'.format(figname, used_name),
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
        self.autosource_nodes = ODict()
        self.dvi_nodes = ODict()
        self.ps_nodes = ODict()
        self.pdf_nodes = ODict()
        self.dump_nodes = ODict()
        for metaname, metarecord in self.metarecords.items():
            self.prebuild_document(
                metaname, metarecord, build_dir/metaname )

    def prebuild_document(self, metaname, metarecord, build_dir):
        """
        Return nothing. Update self.*_nodes.

        Update self.autosource_nodes, self.pdf_nodes, self.ps_nodes.
        """
        build_dir_node = DirectoryNode(
            name='doc:{}:dir'.format(metaname),
            path=build_dir, parents=True, )
        metanode = self.metanodes[metaname]

        def local_name(node):
            return str(node.path.relative(build_dir))

        latex_log_name = metaname + '.log'

        autosource_node = self.autosource_nodes[metaname] = TextNode(
            name='doc:{}:source:main'.format(metaname),
            path=build_dir/'main.tex',
            text=metarecord['document'],
            needs=(metanode, build_dir_node) )

        linked_sources = [
            LinkNode(
                name='doc:{}:source:{}'.format(metaname, alias_name),
                source=self.get_source_node(inpath),
                path=build_dir/alias_name,
                needs=(build_dir_node,) )
            for alias_name, inpath in metarecord['sources'].items() ]
        linked_figures = [
            LinkNode(
                name='doc:{}:fig:{}'.format(metaname, figname),
                source=self.eps_nodes[figname],
                path=(build_dir/figname).with_suffix('.eps'),
                needs=(build_dir_node,) )
            for figname in metarecord['fignames'] ]

        dvi_node = self.dvi_nodes[metaname] = LaTeXNode(
            name='doc:{}:dvi'.format(metaname),
            source=autosource_node,
            path=(build_dir/metaname).with_suffix('.dvi'),
            cwd=build_dir, )
        dvi_node.extend_needs(linked_sources)
        dvi_node.extend_needs(linked_figures)
        if self.force_recompile:
            dvi_node.needs_build = lambda: True

        if 'pdf' in self.build_formats:
            pdf_node = self.pdf_nodes[metaname] = FileNode(
                name='doc:{}:pdf'.format(metaname),
                path=(build_dir/metaname).with_suffix('.pdf'),
                needs=(dvi_node,) )
            pdf_node.extend_needs(linked_figures)
            pdf_node.add_subprocess_rule(
                ('dvipdf', local_name(dvi_node), local_name(pdf_node)),
                cwd=build_dir )
            self.exposed_nodes['pdf'][metaname] = LinkNode(
                name='doc:{}:exposed:pdf'.format(metaname),
                source=pdf_node,
                path=(self.root/metaname).with_suffix('.pdf') )

        if 'ps' in self.build_formats:
            ps_node = self.ps_nodes[metaname] = FileNode(
                name='doc:{}:ps'.format(metaname),
                path=(build_dir/metaname).with_suffix('.ps'),
                needs=(dvi_node,) )
            ps_node.extend_needs(linked_figures)
            ps_node.add_subprocess_rule(
                ('dvips', local_name(dvi_node), '-o', local_name(ps_node)),
                cwd=build_dir )
            self.exposed_nodes['ps'][metaname] = LinkNode(
                name='doc:{}:exposed:ps'.format(metaname),
                source=ps_node,
                path=(self.root/metaname).with_suffix('.ps') )

        if 'dump' in self.build_formats:
            dump_node = self.dump_nodes[metaname] = TextNode(
                name='doc:{}:source:dump'.format(metaname),
                path=build_dir/'dump.tex',
                textfunc=partial(
                    self.resolve_latex_inputs, metarecord['document'] ),
                needs=(metanode, build_dir_node) )
            dump_node.extend_needs(
                self.get_source_node(inpath)
                for inpath in metarecord['inpaths'] )
            if self.force_recompile:
                dump_node.needs_build = lambda: True
            self.exposed_nodes['dump'][metaname] = LinkNode(
                name='doc:{}:exposed:dump'.format(metaname),
                source=dump_node,
                path=(self.root/metaname).with_suffix('.dump.tex') )

    def get_source_node(self, inpath):
        assert isinstance(inpath, PurePath), repr(inpath)
        assert not inpath.is_absolute(), inpath
        if inpath in self.source_nodes:
            return self.source_nodes[inpath]
        node = self.source_nodes[inpath] = \
            FileNode(name='source:{}'.format(inpath),
                path=self.fsmanager.source_dir/inpath )
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
        inpath = PurePath(match.group('source'))
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
    def metarecord_hash(cls, metarecord):
        return hashlib.md5(json.dumps(cls.sterilize(metarecord),
            ensure_ascii=True, sort_keys=True,
        ).encode('ascii')).hexdigest()

    @classmethod
    def sterilize(cls, obj):
        """Sterilize object for JSON dumping."""
        sterilize = cls.sterilize
        if isinstance(obj, ODict):
            return ODict((sterilize(k), sterilize(v)) for k, v in obj.items())
        elif isinstance(obj, dict):
            return {sterilize(k) : sterilize(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [sterilize(i) for i in obj]
#        elif isinstance(obj, set):
#            return {sterilize(i) : None for i in obj}
        elif obj is None or isinstance(obj, (str, int, float)):
            return obj
        elif isinstance(obj, (PurePath, date)):
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
        assert path.parent() == cwd == source.path.parent()
        assert path.suffix == '.dvi'
        assert source.path.suffix == '.tex'

        rule_repr = (
            '<cwd=<BLUE>{cwd}<NOCOLOUR>> '
            '<GREEN>{node.latex_command} -jobname={node.path.basename} '
                '{node.source.path.name}<NOCOLOUR>'
            .format(
                cwd=self.pure_relative(cwd, self.root),
                node=self )
        )
        callargs = (self.latex_command,
            '-jobname={}'.format(self.path.basename),
            '-interaction=nonstopmode', '-halt-on-error', '-file-line-error',
            self.source.path.name )
        @self.add_rule
        def latex_rule():
            source_path = self.source.path
            old_ns = source_path.st_atime_ns-1, source_path.st_mtime_ns-1
            self.log(logging.INFO, rule_repr)
            try:
                output = subprocess.check_output(callargs, cwd=str(cwd),
                    universal_newlines=False )
            except subprocess.CalledProcessError as exception:
                self.print_some_latex_log(exception.output,
                    logpath=None, critical=True )
                self.log(logging.CRITICAL,
                    '{exc.cmd} returned code {exc.returncode}<RESET>'
                    .format(node=self, exc=exception) )
                exception.reported = True
                raise
            log_is_interesting = self.print_some_latex_log(
                output, logpath=self.path.with_suffix('.log') )
            if log_is_interesting:
                try:
                    os.utime(str(self.path), ns=old_ns)
                    self.modified = True
                    logger.warning(
                        '<BOLD>[<YELLOW>{node.name}<NOCOLOUR>] '
                        'Next run will rebuild the target.<RESET>'
                        .format(node=self) )
                except FileNotFoundError:
                    pass

    interesting_latexlog_pattern = re.compile(
        '(?m)^! |[Ee]rror|[Ww]arning|No pages of output.' )
    overfull_latexlog_pattern = re.compile(
        r'(?m)^(Overfull|Underfull)\s+\\hbox\s+\([^()]*?\)\s+'
        r'in\s+paragraph\s+at\s+lines\s+\d+--\d+' )
    page_latexlog_pattern = re.compile(r'\[(?P<number>(?:\d|\s)+)\]')

    latex_decoding_kwargs = {'encoding' : 'cp1251', 'errors' : 'replace'}

    @classmethod
    def print_some_latex_log(cls, output, logpath, critical=False):
        """
        Print some of LaTeX output from its stdout and log.

        Print output if it is interesting or critical is True.
        Otherwise, print overfulls from log (if logpath is not None).
        Return (bool) if output is interesting.
        """
        output = output.decode(**cls.latex_decoding_kwargs)
        is_interesting = (
            cls.interesting_latexlog_pattern.search(output) is not None )
        if critical or is_interesting:
            print(output)
        elif logpath is not None:
            cls.print_overfulls(logpath)
        return is_interesting

    @classmethod
    def print_overfulls(cls, logpath):
        enc_args = {}
        with logpath.open(**cls.latex_decoding_kwargs) as f:
            s = f.read()

        page_marks = {1 : 0}
        last_page = 1; last_mark = 0
        while True:
            for match in cls.page_latexlog_pattern.finditer(s):
                value = int(match.group('number').replace('\n', ''))
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

        for match in cls.overfull_latexlog_pattern.finditer(s):
            start = match.start()
            print(
                '[{}]'.format(current_page(match.start())),
                match.group(0) )

class Dumper(Builder):
    build_formats = ('dump', )

