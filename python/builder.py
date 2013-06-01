from collections import OrderedDict as ODict
import logging

from pathlib import Path, PurePath

from .nodes import Node, DatedNode, FileNode, DirectoryNode, LinkNode
from . import filesystem, drivers, yaml

logger = logging.getLogger(__name__)

def build(targets, *, root):
    Builder(root).build(targets)

class Builder:
    def __new__(cls, root):
        instance = super().__new__(cls)

        instance.root = root
        instance.inpath = root['meta/in.yaml']
        instance.outpath = root['meta/out.yaml']
        instance.cachepath = root['build/cache.yaml']
        instance.cachepath_new = root['build/cache.yaml.new']

        instance.source_nodes = dict()

        instance.driver = drivers.get_driver()

        return instance

    def build(self, targets):
        self.targets = targets

        self.load_meta_files()
        self.meta_mtime = max(
            self.inpath.st_mtime_ns, self.outpath.st_mtime_ns)
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
            self.root['build/figures'], name='build/figures/' ))
        self.prebuild_documents(DirectoryNode(
            self.root['build/latex'], name='build/latex/' ))
        self.shipout()

    def load_meta_files(self):
        with self.inpath.open() as f:
            self.inrecords = yaml.load(f) or ODict()
        with self.outpath.open() as g:
            self.outrecords = yaml.load(g) or {}
        if self.cachepath.exists():
            with self.cachepath.open() as h:
                self.metarecords_cache = yaml.load(h)
        else:
            self.metarecords_cache = {'cache mtimes' : {}}

    def dump_meta_cache(self):
        s = yaml.dump(self.metarecords_cache, default_flow_style=False)
        with open(str(self.cachepath_new), 'w') as f:
            f.write(s)
        self.cachepath_new.rename(self.cachepath)

    def create_metanode(self, metaname, metarecord):
        metanode = DatedNode(name='meta:{}'.format(metaname))
        metanode.record = metarecord
        cache = self.metarecords_cache
        if metaname not in cache:
            logger.debug("Metanode '{}' was not found in cache"
                .format(metaname) )
            cache['cache mtimes'][metaname] = metanode.mtime = self.meta_mtime
            cache[metaname] = metarecord
            self.cache_updated = True
        elif cache[metaname] != metarecord:
            logger.debug("Metanode {} was found obsolete in cache"
                .format(metaname) )
            cache['cache mtimes'][metaname] = metanode.mtime = self.meta_mtime
            cache[metaname] = metarecord
            metanode.modified = True
            self.cache_updated = True
        else:
            logger.debug("Metanode {} was found in cache".format(metaname))
            metanode.mtime = cache['cache mtimes'][metaname]
        return metanode

    def prebuild_figures(self, builddir_node):
        builddir = builddir_node.path
        eps_nodes = self.eps_nodes = ODict()
        for figname, figrecord in self.figrecords.items():
            eps_nodes[figname] = self.prebuild_figure(
                figname, figrecord,
                DirectoryNode(builddir[figname], needs=(builddir_node,))
            )

    def prebuild_figure(self, figname, figrecord, builddir_node):
        figtype = figrecord['type']
        assert figtype in {'asy', 'eps'}, figname
        if figtype == 'asy':
            return self.prebuild_asy_figure(figname, figrecord, builddir_node)
        elif figtype == 'eps':
            return self.prebuild_eps_figure(figname, figrecord, builddir_node)

    def prebuild_asy_figure(self, figname, figrecord, builddir_node):
        builddir = builddir_node.path
        source_node = LinkNode(
            self.get_source_node(figrecord['source']), builddir['main.asy'],
            needs=(builddir_node,) )
        eps_node = FileNode(
            builddir['main.eps'],
            name='build/figures:{}:eps'.format(figname),
            needs=(source_node, builddir_node) )
        eps_node.extend_needs(
            LinkNode(
                self.get_source_node(original_path), builddir[used_name],
                needs=(builddir_node,) )
            for used_name, original_path
            in figrecord['used'].items() )
        eps_node.subprocess_rule(('asy', '-offscreen', 'main.asy'), cwd=builddir)
        return eps_node

    def prebuild_eps_figure(self, figname, figrecord, builddir_node):
        return self.get_source_node(figrecord['source'])

    def prebuild_documents(self, builddir_node):
        self.local_sty = FileNode(self.root['meta/local.sty'], name='local.sty')
        builddir = builddir_node.path
        self.autosource_nodes = ODict()
        self.ps_nodes = ODict()
        self.pdf_nodes = ODict()
        for metaname, metarecord in self.metarecords.items():
            self.prebuild_document(
                metaname, metarecord,
                DirectoryNode(builddir[metaname], needs=(builddir_node,))
            )

    def prebuild_document(self, metaname, metarecord, builddir_node):
        """
        Return nothing. Update self.pdf_nodes, self.ps_a4_nodes, self
        """
        builddir = builddir_node.path
        metanode = self.metanodes[metaname]

        tex_name = metaname + '.tex'
        dvi_name = metaname + '.dvi'
        pdf_name = metaname + '.pdf'
        ps_name = metaname + '.ps'

    # self.autosource_nodes
        tex_node = self.autosource_nodes[metaname] = FileNode(
            builddir[tex_name], needs=(metanode, builddir_node),
            name='build/latex:{}:tex'.format(metaname))
        @tex_node.add_rule
        def latex_generator_rule():
            tex_node.print_rule(
                '[{node.name}] jeolm:autosource {node.path!s}'
                .format(node=tex_node) )
            s = metarecord['document']
            with tex_node.open('w') as f:
                f.write(s)

        dvi_node = FileNode(
            builddir[dvi_name], needs=(tex_node,),
            name='build/latex:{}:dvi'.format(metaname))
        dvi_node.extend_needs(
            LinkNode(
                self.get_source_node(inpath), builddir[alias_name],
                needs=(builddir_node,) )
            for alias_name, inpath in metarecord['sources'].items() )
        dvi_node.append_needs(
            LinkNode(self.local_sty, builddir['local.sty'],
                needs=(builddir_node,) ) )
        dvi_node.extend_needs(
            LinkNode(
                self.eps_nodes[figname], builddir[figname + '.eps'],
                needs=(builddir_node,) )
            for figname in metarecord['fignames'] )
        dvi_node.subprocess_rule(
            ('latex', '-halt-on-error', tex_name), cwd=builddir)

    # self.ps_nodes
        ps_node = self.ps_nodes[metaname] = FileNode(
            builddir[ps_name], needs=(dvi_node,),
            name='build/latex:{}:ps'.format(metaname))
        ps_node.subprocess_rule(
            ('dvips', dvi_name, '-o', ps_name), cwd=builddir )

    # self.pdf_nodes
        pdf_node = self.pdf_nodes[metaname] = FileNode(
            builddir[pdf_name], needs=(dvi_node,),
            name='build/latex:{}:pdf'.format(metaname) )
        pdf_node.subprocess_rule(
            ('dvipdf', dvi_name, pdf_name), cwd=builddir )

    def shipout(self):
        shipout_ps_nodes = self.shipout_ps_nodes = ODict()
        shipout_pdf_nodes = self.shipout_pdf_nodes = ODict()
        for metaname in self.metarecords:
            shipout_ps_nodes[metaname] = LinkNode(
                self.ps_nodes[metaname], self.root[metaname + '.ps'],
                name='shipout:{}:ps'.format(metaname))
            shipout_pdf_nodes[metaname] = LinkNode(
                self.pdf_nodes[metaname], self.root[metaname + '.pdf'],
                name='shipout:{}:pdf'.format(metaname))
        supernode = self.supernode = Node(name='supernode')
#        supernode.extend_needs(shipout_ps_nodes.values())
        supernode.extend_needs(shipout_pdf_nodes.values())
        supernode.update()

    def get_source_node(self, name):
        assert isinstance(name, PurePath), repr(name)
        assert not name.is_absolute(), name
        if name in self.source_nodes:
            return self.source_nodes[name]
        node = self.source_nodes[name] = \
            FileNode(self.root['source'][name])
        return node

