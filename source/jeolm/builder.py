from string import Template
from collections import OrderedDict
from functools import partial
from itertools import chain
from datetime import date

import os
import re
import hashlib
import json
import pickle
import subprocess
import threading

from pathlib import Path, PurePosixPath

import jeolm
import jeolm.node

from jeolm.node import (
    Node, DatedNode, FileNode, TextNode, ProductFileNode,
    LinkNode, DirectoryNode )

import logging
logger = logging.getLogger(__name__)

class Builder:
    build_formats = ('pdf', )
    known_formats = ('pdf', 'ps', 'dump')

    def __init__(self, targets, *, local, driver,
        force=None, delegate=True, executor=None
    ):
        self.local = local
        self.driver = driver

        self.targets = targets
        assert force in {'latex', 'generate', None}
        self.force = force
        self.delegate = delegate

        self.executor = executor

    def prebuild(self):
        outrecords_cache = self._load_outrecords_cache()

        targets = self.targets
        if self.delegate:
            targets = [
                delegated_target.flags_clean_copy(origin='target')
                for delegated_target
                in self.driver.list_delegated_targets(
                    *targets, recursively=True )
            ]
        outrecords = OrderedDict(
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
        figure_records = OrderedDict(
            (figure_path, self.driver.produce_figure_record(figure_path))
            for figure_path in figure_paths )
        package_records = OrderedDict(
            (package_path, self.driver.produce_package_record(package_path))
            for package_path in package_paths )
        self.outnodes = OrderedDict(
            (target, self.create_outnode(
                target, outrecord,
                outrecords_cache=outrecords_cache ))
            for target, outrecord in outrecords.items() )
        if any(node.modified for node in self.outnodes.values()):
            self._dump_outrecords_cache(outrecords_cache)

        self.source_nodes = OrderedDict()
        assert set(self.known_formats) >= set(self.build_formats)

        self.prebuild_packages( package_records,
            self.local.build_dir/'packages' )
        self.prebuild_figures( figure_records,
            build_dir=self.local.build_dir/'figures' )
        self.prebuild_documents( outrecords,
            build_dir=self.local.build_dir/'documents' )

        self.ultimate_node = Node(
            name='ultimate',
            needs=( node
                for build_format in self.build_formats
                for node in self.exposed_nodes[build_format].values() )
        )

    def build(self):
        if not hasattr(self, 'ultimate_node'):
            self.prebuild()
        self.ultimate_node.update(executor=self.executor)
        if self.executor is not None:
            self.ultimate_node.update()


    ##########
    # Outrecords cache management

    def _load_outrecords_cache(self):
        try:
            with self._outrecords_cache_path.open('rb') as cache_file:
                pickled_cache = cache_file.read()
        except FileNotFoundError:
            return {}
        else:
            return pickle.loads(pickled_cache)

    def _dump_outrecords_cache(self, outrecords_cache):
        pickled_cache = pickle.dumps(outrecords_cache)
        new_path = self.local.build_dir / '.outrecords.cache.pickle.new'
        with new_path.open('wb') as cache_file:
            cache_file.write(pickled_cache)
        new_path.rename(self._outrecords_cache_path)

    @property
    def _outrecords_cache_path(self):
        return self.local.build_dir / self._outrecords_cache_name

    _outrecords_cache_name = 'outrecords.cache.pickle'


    def create_outnode(self, target, outrecord, *, outrecords_cache):
        target_s = str(target)
        outnode = DatedNode(name='doc:{}:record'.format(target))
        outnode.record = outrecord
        outrecord_hash = self.outrecord_hash(outrecord)

        if target_s not in outrecords_cache:
            logger.debug("Metanode {} was not found in cache"
                .format(target_s) )
            modified = True
        elif outrecords_cache[target_s]['hash'] != outrecord_hash:
            logger.debug("Metanode {} was found obsolete in cache"
                .format(target_s) )
            modified = True
        else:
            logger.debug("Metanode {} was found in cache"
                .format(target_s) )
            modified = False

        if modified:
            outnode.set_mtime_to_now()
            outrecords_cache[target_s] = {
                'hash' : outrecord_hash, 'mtime' : outnode.mtime }
            outnode.modified = True
        else:
            outnode.mtime = outrecords_cache[target_s]['mtime']
        return outnode

    def prebuild_figures(self, figure_records, *, build_dir):
        self.figure_nodes = {
            figure_outtype : OrderedDict()
            for figure_outtype in ('eps', 'pdf') }
        for figure_path, figure_record in figure_records.items():
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

    def prebuild_packages(self, package_records, build_dir):
        self.package_nodes = OrderedDict()
        for package_path, package_record in package_records.items():
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

    def prebuild_documents(self, outrecords, *, build_dir):
        self.document_nodes = {
            build_format : OrderedDict()
            for build_format in self.known_formats }
        self.exposed_nodes = {
            build_format : OrderedDict()
            for build_format in self.known_formats }
        for target, outrecord in outrecords.items():
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

        package_nodes = [
            LinkNode(
                name='doc:{}:sty:{}'.format(target, alias_name),
                source=self.package_nodes[package_path],
                path=(build_dir/alias_name).with_suffix('.sty'),
                needs=(build_dir_node,) )
            for alias_name, package_path
            in outrecord['package_paths'].items() ]
        figure_nodes = [
            LinkNode(
                name='doc:{}:fig:{}'.format(target, alias_name),
                source=self.figure_nodes['eps'][figure_path],
                path=(build_dir/alias_name).with_suffix('.eps'),
                needs=(build_dir_node,) )
            for alias_name, figure_path
            in outrecord['figure_paths'].items() ]
        source_nodes = [
            LinkNode(
                name='doc:{}:source:{}'.format(target, alias),
                source=self.get_source_node(inpath),
                path=build_dir/alias,
                needs=(build_dir_node,) )
            for alias, inpath in outrecord['sources'].items() ]

        dvi_node = LaTeXNode(
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
            needs=(self.outnodes[target], build_dir_node,) )
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
            needs=(build_dir_node, dtx_node, ins_node,) )
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
                path=(self.local.root/outrecord['outname'])
                    .with_suffix(document_node.path.suffix)
            )

    def get_source_node(self, inpath):
        assert isinstance(inpath, PurePosixPath), repr(inpath)
        assert not inpath.is_absolute(), inpath
        if inpath in self.source_nodes:
            return self.source_nodes[inpath]
        node = self.source_nodes[inpath] = \
            FileNode(name='source:{}'.format(inpath),
                path=self.local.source_dir/inpath )
        if not node.path.exists():
            logger.warning( "Requested source node {} does not exist as file."
                .format(inpath) )
        return node

    @classmethod
    def outrecord_hash(cls, outrecord):
        return hashlib.sha256(cls._sorted_repr(outrecord).encode()).hexdigest()

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


class LaTeXNode(ProductFileNode):
    """
    Represents a target of some latex command.

    Aims at reasonable handling of latex output to stdin/log.
    Completely suppresses latex output unless finds something
    interesting in it.
    """

    latex_command = 'latex'
    target_suffix = '.dvi'

    _latex_additional_args = (
        '-interaction=nonstopmode', '-halt-on-error', '-file-line-error', )

    _latex_output_decode_kwargs = {
        'encoding' : 'ascii', 'errors' : 'replace' }

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

        self.add_rule(partial(
            self._latex_rule, jobname, cwd=cwd
        ))

    def _latex_rule(self, jobname, *, cwd):
        callargs = (self.latex_command,
            '-jobname={}'.format(jobname),
            ) + self._latex_additional_args + (
            self.source.path.name, )

        latex_output = self._subprocess_output(
            callargs, cwd=cwd )

        if self._latex_output_requests_rerun(latex_output):
            print(latex_output)
            try:
                self._turn_older_than_source()
            except FileNotFoundError as exception:
                raise jeolm.node.MissingTargetError(*exception.args) \
                    from exception
            else:
                self.modified = True
                self._log( logging.WARNING,
                    "Next run will rebuild the target." )
        else:
            self.print_latex_log(
                latex_output,
                latex_log_path=self.path.with_suffix('.log') )

    @classmethod
    def _latex_output_requests_rerun(cls, latex_output):
        match = cls.latex_output_rerun_pattern.search(latex_output)
        return match is not None
    latex_output_rerun_pattern = re.compile(
        r'[Rr]erun to (?#get something right)' )

    def print_latex_log(self, latex_output, latex_log_path=None):
        """
        Print some of LaTeX output from its stdout and log.

        Print output if it is interesting.
        Otherwise, print overfulls from latex log
        (if latex_log_path is not None).
        """
        if self._latex_output_is_alarming(latex_output):
            print(latex_output)
            self._log(logging.WARNING, 'Alarming LaTeX output detected.')
        elif latex_log_path is not None:
            with latex_log_path.open(
                **self._latex_output_decode_kwargs
            ) as latex_log_file:
                latex_log_text = latex_log_file.read()
            self._print_overfulls_from_latex_log(latex_log_text)

    @classmethod
    def _latex_output_is_alarming(cls, latex_output):
        match = cls.latex_output_alarming_pattern.search(latex_output)
        return match is not None
    latex_output_alarming_pattern = re.compile(
        r'[Ee]rror|[Ww]arning|No pages of output' )

    def _print_overfulls_from_latex_log(self, latex_log_text):
        page_numberer = self._find_page_numbers_in_latex_log(latex_log_text)
        next(page_numberer) # initialize coroutine
        file_namer = self._find_file_names_in_latex_log(latex_log_text)
        next(file_namer) # initialize coroutine

        matches = list(
            self._latex_log_overfull_pattern.finditer(latex_log_text) )
        if not matches:
            return
        header = "<BOLD>Overfulls and underfulls detected by LaTeX:<RESET>"
        self._log( logging.INFO, '\n'.join(chain(
            (header,),
            (
                self._format_overfull(match, page_numberer, file_namer)
                for match in matches )
        )))

    _latex_log_overfull_pattern = re.compile(
        r'(?m)^'
        r'(?P<overfull_type>Overfull|Underfull) '
        r'\\(?P<box_type>hbox|vbox) '
        r'(?P<badness>\((?:\d+(?:\.\d+)?pt too wide|badness \d+)\) |)'
        r'(?P<rest>.*)$'
    )
    _latex_overfull_log_template = (
        r'\g<overfull_type> '
        r'\\\g<box_type> '
        r'<YELLOW>\g<badness><NOCOLOUR>'
        r'\g<rest>' )

    @classmethod
    def _format_overfull(cls, match, page_numberer, file_namer):
        position = match.start()
        page_number = page_numberer.send(position)
        file_name = file_namer.send(position)
        message = match.expand(cls._latex_overfull_log_template)
        return (
            "<CYAN>[{page_number}]<NOCOLOUR>"
            ' '
            "<MAGENTA>({file_name})<NOCOLOUR>"
            '\n'
            "{message}"
        ).format(
            page_number=page_number, file_name=file_name,
            message=message
        )

    @classmethod
    def _find_page_numbers_in_latex_log(cls, latex_log_text):
        """
        Coroutine, yields page number for sent text position.

        As with any generator, initial next() call required.
        After that, sending position in latex_log_text will yield corresponding
        page number.
        """

        page_mark_positions = [0]
        last_page_number = 0
        matches = cls._latex_log_page_number_pattern.finditer(
            latex_log_text )
        for match in matches:
            page_number = int(match.group('page_number'))
            if page_number != last_page_number + 1:
                # Something got slightly wrong. Close your eyes
                continue
            page_mark_positions.append(match.end())
            assert len(page_mark_positions) == page_number + 1
            last_page_number = page_number
        page_mark_positions.append(len(latex_log_text))
        assert len(page_mark_positions) > 1

        last_page_number = 0
        last_position = page_mark_positions[last_page_number]
        assert last_position == 0
        next_position = page_mark_positions[last_page_number + 1]
        page_number = None # "answer" variable
        while True:
            position = (yield page_number)
            if position is None:
                page_number = None
                continue
            if __debug__ and position < last_position:
                raise RuntimeError("Sent position is not monotonic.")
            if __debug__ and position >= len(latex_log_text):
                raise RuntimeError("Sent position is out of range.")
            while position >= next_position:
                last_position = next_position
                last_page_number += 1
                next_position = page_mark_positions[last_page_number + 1]
            page_number = last_page_number + 1

    _latex_log_page_number_pattern = re.compile(
        r'\[(?P<page_number>\d+)\s*\]' )

    @classmethod
    def _find_file_names_in_latex_log(cls, latex_log_text):
        """
        Coroutine, yields input file name for sent text position.

        As with any generator, initial next() call required.
        After that, sending position in latex_log_text will yield corresponding
        input file name.

        Only local filenames are detected, e.g. starting with "./",
        and return without a prefixing "./".
        """

        file_name_positions = [0]
        file_names = [None]
        matches = cls._latex_log_file_name_pattern.finditer(
            latex_log_text )
        for match in matches:
            file_name_positions.append(match.end())
            file_names.append(match.group('file_name'))
        file_name_positions.append(len(latex_log_text))
        assert len(file_name_positions) == len(file_names) + 1

        last_index = 0
        last_position = file_name_positions[last_index]
        assert last_position == 0
        next_position = file_name_positions[last_index + 1]
        file_name = None # "answer" variable
        while True:
            position = (yield file_name)
            if position is None:
                file_name = None
                continue
            if __debug__ and position < last_position:
                raise RuntimeError("Sent position is not monotonic.")
            if __debug__ and position >= len(latex_log_text):
                raise RuntimeError("Sent position is out of range.")
            while position >= next_position:
                last_position = next_position
                last_index += 1
                next_position = file_name_positions[last_index + 1]
            file_name = file_names[last_index]

    _latex_log_file_name_pattern = re.compile(
        r'(?<=\(\./)' # "(./"
        r'(?P<file_name>.+?)' # "<file name>"
        r'(?=[\s)])' # ")" or "\n" or " "
    )

class Dumper(Builder):
    build_formats = ('dump', )

