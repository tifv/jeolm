from string import Template

from . import _cache_node

import jeolm.node
import jeolm.node.directory
import jeolm.node.symlink
import jeolm.node.text

from jeolm.record_path import RecordPath

import logging
logger = logging.getLogger(__name__)


class PackageNodeFactory:
    package_types = frozenset(('dtx', 'sty',))

    def __init__(self, *, project, driver,
        build_dir_node,
        source_node_factory
    ):
        self.project = project
        self.driver = driver
        self.build_dir_node = build_dir_node
        self.source_node_factory = source_node_factory

        self._nodes = dict()

    @property
    def build_dir(self):
        return self.build_dir_node.path

    def __call__(self, metapath, *, package_type=None):
        assert isinstance(metapath, RecordPath)
        return self._get_package_node(metapath, package_type=package_type)

    # pylint: disable=no-self-use,unused-argument,unused-variable
    def _package_node_key(self, metapath,
        *, package_type,
        package_records=None
    ):
        return metapath, package_type, 'sty'
    # pylint: enable=no-self-use,unused-argument,unused-variable

    @_cache_node(_package_node_key)
    def _get_package_node(self, metapath,
        *, package_type,
        package_records=None
    ):
        if package_records is None:
            package_records = self.driver.produce_package_records(metapath)
        package_types = set(package_records)
        if package_type is not None:
            if package_type not in package_types:
                raise ValueError( "Package {0} of type {1} is not available"
                    .format(metapath, package_type) )
            package_types = {package_type}
        assert package_types, (package_records, package_type)

        if package_type is None:
            for package_type in ('dtx', 'sty',):
                if package_type in package_types:
                    break
            else:
                raise ValueError( "Unable to determine package type "
                    "for package {}, given types {}"
                    .format(metapath, sorted(package_types)) )
            return self._get_package_node( metapath,
                package_type=package_type,
                package_records=package_records )
        elif package_type == 'dtx':
            get_package_node_method = self._get_package_node_dtx
        elif package_type == 'sty':
            get_package_node_method = self._get_package_node_proxy
        else:
            raise RuntimeError

        node = get_package_node_method( metapath,
            package_record=package_records[package_type] )
        if not hasattr(node, 'metapath'):
            node.metapath = metapath
        return node

    # pylint: disable=no-self-use,unused-argument,unused-variable
    def _metapath_build_dir_key(self, metapath):
        return metapath, 'dir', 'dir'
    # pylint: enable=no-self-use,unused-argument,unused-variable

    @_cache_node(_metapath_build_dir_key)
    def _get_metapath_build_dir(self, metapath):
        parent_dir_node = self.build_dir_node
        buildname = '-'.join(metapath.parts)
        assert '.' not in buildname
        return jeolm.node.directory.DirectoryNode(
                name='package:{}:dir'.format(metapath),
                path=parent_dir_node.path/buildname,
                needs=(parent_dir_node,) )

    # pylint: disable=no-self-use,unused-argument,unused-variable
    def _build_dir_key(self, metapath, *, package_type):
        return metapath, package_type, 'dir'
    # pylint: enable=no-self-use,unused-argument,unused-variable

    @_cache_node(_build_dir_key)
    def _get_build_dir(self, metapath, *, package_type):
        if package_type == 'dtx':
            parent_dir_node = self._get_metapath_build_dir(metapath)
            return jeolm.node.directory.BuildDirectoryNode(
                name = 'package:{}:{}:dir'.format(metapath, package_type),
                path=parent_dir_node.path/package_type,
                needs=(parent_dir_node,) )
        else:
            raise RuntimeError

    # pylint: disable=no-self-use,unused-argument,unused-variable
    def _output_dir_key(self, metapath, *, package_type):
        return metapath, package_type, 'output-dir'
    # pylint: enable=no-self-use,unused-argument,unused-variable

    @_cache_node(_output_dir_key)
    def _get_output_dir(self, metapath, *, package_type):
        if package_type == 'dtx':
            build_dir_node = self._get_build_dir( metapath,
                package_type=package_type )
            output_dir_node = jeolm.node.directory.DirectoryNode(
                name = 'package:{}:{}:output-dir'
                    .format(metapath, package_type),
                path=build_dir_node.path/'output',
                needs=(build_dir_node,) )
            build_dir_node.register_node(output_dir_node)
            return output_dir_node
        else:
            raise RuntimeError

    def _get_package_node_dtx(self, metapath, *, package_record):
        build_dir_node = self._get_build_dir( metapath,
            package_type='dtx' )
        build_dir = build_dir_node.path
        output_dir_node = self._get_output_dir( metapath,
            package_type='dtx' )
        output_dir = output_dir_node.path
        source_dtx_node = self.source_node_factory(
            package_record['source'] )
        package_name = package_record['name']
        dtx_node = jeolm.node.symlink.SymLinkedFileNode(
            name='package:{}:source:dtx'.format(metapath),
            source=source_dtx_node,
            path=build_dir/'{}.dtx'.format(package_name),
            needs=(build_dir_node,) )
        build_dir_node.register_node(dtx_node)
        ins_node = jeolm.node.text.TextNode(
            name='package:{}:source:ins'.format(metapath),
            path=build_dir/'package.ins',
            text=self._substitute_ins(package_name=package_name),
            build_dir_node=build_dir_node )
        build_dir_node.register_node(ins_node)
        sty_node = jeolm.node.ProductFileNode(
            name='package:{}:sty'.format(metapath),
            source=dtx_node,
            path=output_dir/'{}.sty'.format(package_name),
            needs=(ins_node, build_dir_node.pre_cleanup_node) )
        sty_node.set_subprocess_command(
            ( 'latex', '-interaction=nonstopmode', '-halt-on-error',
                '-output-directory={}'.format(
                    output_dir.relative_to(build_dir) ),
                ins_node.path.name ),
            cwd=build_dir_node.path )
        build_dir_node.post_check_node.append_needs(sty_node)
        sty_node = jeolm.node.symlink.ProxyFileNode(
            source=sty_node, name='{}:proxy'.format(sty_node.name),
            needs=(build_dir_node.post_check_node,) )
        return sty_node

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
        r"\endinput" '\n'
    )
    _substitute_ins = Template(_ins_template).substitute

    def _get_package_node_proxy(self, metapath, *, package_record):
        source_node = self.source_node_factory(package_record['source'])
        node = jeolm.node.symlink.ProxyFileNode(
            name='package:{}:sty'.format(metapath),
            source=source_node )
        return node



