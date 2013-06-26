from collections import OrderedDict as ODict
from hashlib import md5

from pathlib import Path, PurePosixPath as PurePath

from .nodes import (
    Node, DatedNode, FileNode, DirectoryNode, LinkNode, LaTeXNode )
from . import filesystem, drivers, yaml

import logging
logger = logging.getLogger(__name__)

def build(targets, *, root):
    builder = Builder(targets, root=root)
    builder.prebuild()
    builder.update()

class Builder:
    shipout_format = 'pdf'

    def __init__(self, targets, *, root):
        self.root = root
        self.targets = targets

        self.metapaths = {
            'in' : root/'meta/in.yaml',
            'out' : root/'meta/out.yaml',
            'meta.cache' : root/'build/meta.cache.yaml',
        }
        self.source_nodes = ODict()
        self.autosource_nodes = ODict()
        self.eps_nodes = ODict()
        self.ps_nodes = ODict()
        self.pdf_nodes = ODict()
        self.shipout_ps_nodes = ODict()
        self.shipout_pdf_nodes = ODict()
        self.shipout_node = Node(name='shipout')

        self.driver = drivers.get_driver()

    def prebuild(self):
        self.load_meta_files()
        self.meta_mtime = max(
            self.metapaths['in'].st_mtime_ns,
            self.metapaths['out'].st_mtime_ns )
        self.metarecords, self.figrecords = \
            self.driver.produce_metarecords(
                self.targets, self.inrecords, self.outrecords )
        self.cache_updated = False
        self.metanodes = ODict(
            (metaname, self.create_metanode(metaname, metarecord))
            for metaname, metarecord, in self.metarecords.items() )
        if self.cache_updated:
            self.dump_meta_cache()

        self.prebuild_figures(DirectoryNode(
            self.root/'build/figures', name='build/figures/' ))
        self.prebuild_documents(DirectoryNode(
            self.root/'build/latex', name='build/latex/' ))
        self.prebuild_shipout()

    def update(self):
        self.shipout_node.update()

    def load_meta_files(self):
        with self.metapaths['in'].open() as f:
            self.inrecords = yaml.load(f) or ODict()
        with self.metapaths['out'].open() as g:
            self.outrecords = yaml.load(g) or {}
        if self.metapaths['meta.cache'].exists():
            with self.metapaths['meta.cache'].open() as h:
                self.metarecords_cache = yaml.load(h)
        else:
            self.metarecords_cache = {}

    def dump_meta_cache(self):
        s = yaml.dump(self.metarecords_cache, default_flow_style=False)
        meta_cache_new = Path('.meta.cache.yaml.new')
        with meta_cache_new.open('w') as f:
            f.write(s)
        meta_cache_new.rename(self.metapaths['meta.cache'])

    def create_metanode(self, metaname, metarecord):
        metanode = DatedNode(name='meta:{}'.format(metaname))
        metanode.record = metarecord
        cache = self.metarecords_cache
        metarecord_hash = self.metarecord_hash(metarecord)
        if metaname not in cache:
            logger.debug("Metanode {} was not found in cache"
                .format(metaname) )
            cache[metaname] = {'hash' : metarecord_hash, 'mtime' : self.meta_mtime}
            metanode.mtime = self.meta_mtime
            metanode.modified = True
            self.cache_updated = True
        elif cache[metaname]['hash'] != metarecord_hash:
            logger.debug("Metanode {} was found obsolete in cache"
                .format(metaname) )
            cache[metaname] = {'hash' : metarecord_hash, 'mtime' : self.meta_mtime}
            metanode.mtime = self.meta_mtime
            metanode.modified = True
            self.cache_updated = True
        else:
            logger.debug("Metanode {} was found in cache".format(metaname))
            metanode.mtime = cache[metaname]['mtime']
        return metanode

    def prebuild_figures(self, builddir_node):
        builddir = builddir_node.path
        eps_nodes = self.eps_nodes
        for figname, figrecord in self.figrecords.items():
            eps_nodes[figname] = self.prebuild_figure(
                figname, figrecord,
                DirectoryNode(builddir/figname, needs=(builddir_node,))
            )

    def prebuild_figure(self, figname, figrecord, builddir_node):
        figtype = figrecord['type']
        if figtype == 'asy':
            return self.prebuild_asy_figure(figname, figrecord, builddir_node);
        elif figtype == 'eps':
            return self.prebuild_eps_figure(figname, figrecord, builddir_node);
        else:
            raise AssertionError(figtype, figname)

    def prebuild_asy_figure(self, figname, figrecord, builddir_node):
        builddir = builddir_node.path
        source_node = LinkNode(
            self.get_source_node(figrecord['source']), builddir/'main.asy',
            needs=(builddir_node,) )
        eps_node = FileNode(
            builddir/'main.eps',
            name='build/figures:{}:eps'.format(figname),
            needs=(source_node, builddir_node) )
        eps_node.extend_needs(
            LinkNode(
                self.get_source_node(original_path), builddir/used_name,
                needs=(builddir_node,) )
            for used_name, original_path
            in figrecord['used'].items() )
        eps_node.add_subprocess_rule(
            ('asy', '-offscreen', 'main.asy'), cwd=builddir )
        return eps_node

    def prebuild_eps_figure(self, figname, figrecord, builddir_node):
        return self.get_source_node(figrecord['source'])

    def prebuild_documents(self, builddir_node):
        self.local_sty = FileNode(self.root/'meta/local.sty', name='local.sty')
        builddir = builddir_node.path
        for metaname, metarecord in self.metarecords.items():
            self.prebuild_document(
                metaname, metarecord,
                DirectoryNode(builddir/metaname, needs=(builddir_node,))
            )

    def prebuild_document(self, metaname, metarecord, builddir_node):
        """
        Return nothing. Update self.*_nodes.

        Update self.autosource_nodes, self.pdf_nodes, self.ps_nodes.
        """
        builddir = builddir_node.path
        metanode = self.metanodes[metaname]

        tex_name = metaname + '.tex'
        dvi_name = metaname + '.dvi'
        pdf_name = metaname + '.pdf'
        ps_name = metaname + '.ps'

        latex_log_name = metaname + '.log'

        tex_node = self.autosource_nodes[metaname] = FileNode(
            builddir/tex_name, needs=(metanode, builddir_node),
            name='build/latex:{}:tex'.format(metaname))
        @tex_node.add_rule
        def latex_generator_rule():
            tex_node.print_rule(
                '[{node.name}] jeolm:autosource {node.path!s}'
                .format(node=tex_node) )
            s = metarecord['document']
            with tex_node.open('w') as f:
                f.write(s)

        dvi_node = LaTeXNode(
            builddir/dvi_name, needs=(tex_node,),
            name='build/latex:{}:dvi'.format(metaname))
        dvi_node.extend_needs(
            LinkNode(
                self.get_source_node(inpath), builddir/alias_name,
                needs=(builddir_node,) )
            for alias_name, inpath in metarecord['sources'].items() )
        dvi_node.append_needs(
            LinkNode(self.local_sty, builddir/'local.sty',
                needs=(builddir_node,) ) )
        dvi_node.extend_needs(
            LinkNode(
                self.eps_nodes[figname], builddir/(figname+'.eps'),
                needs=(builddir_node,) )
            for figname in metarecord['fignames'] )
        dvi_node.add_latex_rule(tex_name, cwd=builddir,
            logpath=builddir/latex_log_name )

        if 'ps' in self.shipout_format:
            ps_node = self.ps_nodes[metaname] = FileNode(
                builddir/ps_name, needs=(dvi_node,),
                name='build/latex:{}:ps'.format(metaname))
            ps_node.add_subprocess_rule(
                ('dvips', dvi_name, '-o', ps_name), cwd=builddir )

        if 'pdf' in self.shipout_format:
            pdf_node = self.pdf_nodes[metaname] = FileNode(
                builddir/pdf_name, needs=(dvi_node,),
                name='build/latex:{}:pdf'.format(metaname) )
            pdf_node.add_subprocess_rule(
                ('dvipdf', dvi_name, pdf_name), cwd=builddir )

    def prebuild_shipout(self):
        if 'ps' in self.shipout_format:
            self.prebuild_shipout_ps()
        if 'pdf' in self.shipout_format:
            self.prebuild_shipout_pdf()

    def prebuild_shipout_ps(self):
        shipout_ps_nodes = self.shipout_ps_nodes
        for metaname in self.metarecords:
            shipout_ps_nodes[metaname] = LinkNode(
                self.ps_nodes[metaname], self.root/(metaname+'.ps'),
                name='shipout:{}:ps'.format(metaname))
        self.shipout_node.extend_needs(shipout_ps_nodes.values())

    def prebuild_shipout_pdf(self):
        shipout_pdf_nodes = self.shipout_pdf_nodes
        for metaname in self.metarecords:
            shipout_pdf_nodes[metaname] = LinkNode(
                self.pdf_nodes[metaname], self.root/(metaname+'.pdf'),
                name='shipout:{}:pdf'.format(metaname))
        self.shipout_node.extend_needs(shipout_pdf_nodes.values())

    def get_source_node(self, path):
        assert isinstance(path, PurePath), repr(path)
        assert not path.is_absolute(), path
        if path in self.source_nodes:
            return self.source_nodes[path];
        node = self.source_nodes[path] = \
            FileNode(self.root/'source'/path)
        return node;

    @staticmethod
    def metarecord_hash(metarecord):
        return md5(yaml.dump(metarecord).encode('utf-8')).hexdigest()

