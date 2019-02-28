from string import Template
from pathlib import PosixPath

from . import _cache_node

import jeolm.node
import jeolm.node.directory
import jeolm.node.symlink
import jeolm.node.text

from jeolm.records import RecordPath

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

    def __call__(self, package_path):
        assert isinstance(package_path, RecordPath)
        return self._get_package_node(package_path)

    # pylint: disable=no-self-use,unused-argument,unused-variable
    def _package_node_key(self, package_path):
        return package_path, 'sty'
    # pylint: enable=no-self-use,unused-argument,unused-variable

    @_cache_node(_package_node_key)
    def _get_package_node(self, package_path):
        package_recipe = self.driver.produce_package_recipe(package_path)
        package_type = package_recipe.source_type

        if package_type == 'dtx':
            get_package_node_method = self._get_package_node_dtx
        elif package_type == 'sty':
            get_package_node_method = self._get_package_node_proxy
        else:
            raise RuntimeError

        node = get_package_node_method( package_path,
            package_recipe=package_recipe )
        if not hasattr(node, 'package_path'):
            node.package_path = package_path
        if not hasattr(node, 'package_name'):
            node.package_name = package_recipe.name
        return node

    def _get_package_node_proxy(self, package_path, *, package_recipe):
        source_node = self.source_node_factory(package_recipe.source)
        node = jeolm.node.symlink.ProxyFileNode(
            name='package:{}:sty'.format(package_path),
            source=source_node )
        return node

    # pylint: disable=no-self-use,unused-argument,unused-variable
    def _package_path_build_dir_key(self, package_path):
        return package_path, 'dir', 'dir'
    # pylint: enable=no-self-use,unused-argument,unused-variable

    @_cache_node(_package_path_build_dir_key)
    def _get_package_path_build_dir(self, package_path):
        parent_dir_node = self.build_dir_node
        dir_path = parent_dir_node.path / '-'.join(package_path.parts)
        return jeolm.node.directory.DirectoryNode(
                name='package:{}:dir'.format(package_path),
                path=dir_path,
                needs=(parent_dir_node,) )

    # pylint: disable=no-self-use,unused-argument,unused-variable
    def _build_dir_key(self, package_path, *, package_type):
        return package_path, package_type, 'dir'
    # pylint: enable=no-self-use,unused-argument,unused-variable

    @_cache_node(_build_dir_key)
    def _get_build_dir(self, package_path, *, package_type):
        if package_type == 'dtx':
            parent_dir_node = self._get_package_path_build_dir(package_path)
            return jeolm.node.directory.BuildDirectoryNode(
                name = 'package:{}:{}:dir'.format(package_path, package_type),
                path=parent_dir_node.path/package_type,
                needs=(parent_dir_node,) )
        else:
            raise RuntimeError

    # pylint: disable=no-self-use,unused-argument,unused-variable
    def _output_dir_key(self, package_path, *, package_type):
        return package_path, package_type, 'output-dir'
    # pylint: enable=no-self-use,unused-argument,unused-variable

    @_cache_node(_output_dir_key)
    def _get_output_dir(self, package_path, *, package_type):
        if package_type == 'dtx':
            build_dir_node = self._get_build_dir( package_path,
                package_type=package_type )
            output_dir_node = jeolm.node.directory.DirectoryNode(
                name = 'package:{}:{}:output-dir'
                    .format(package_path, package_type),
                path=build_dir_node.path/'output',
                needs=(build_dir_node,) )
            build_dir_node.register_node(output_dir_node)
            return output_dir_node
        else:
            raise RuntimeError

    def _get_package_node_dtx(self, package_path, *, package_recipe):
        build_dir_node = self._get_build_dir( package_path,
            package_type='dtx' )
        build_dir = build_dir_node.path
        output_dir_node = self._get_output_dir( package_path,
            package_type='dtx' )
        output_dir = output_dir_node.path
        source_dtx_node = self.source_node_factory(
            package_recipe.source )
        package_name = package_recipe.name
        dtx_node = jeolm.node.symlink.SymLinkedFileNode(
            name='package:{}:source:dtx'.format(package_path),
            source=source_dtx_node,
            path=build_dir/'{}.dtx'.format(package_name),
            needs=(build_dir_node,) )
        build_dir_node.register_node(dtx_node)
        ins_node = jeolm.node.text.TextNode(
            name='package:{}:source:ins'.format(package_path),
            path=build_dir/'package.ins',
            text=self._ins_template.substitute(package_name=package_name),
            build_dir_node=build_dir_node )
        build_dir_node.register_node(ins_node)
        sty_node = jeolm.node.ProductFileNode(
            name='package:{}:sty'.format(package_path),
            source=dtx_node,
            path=output_dir/'{}.sty'.format(package_name),
            needs=(ins_node, build_dir_node.pre_cleanup_node) )
        sty_node.command = jeolm.node.SubprocessCommand( sty_node,
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

    _ins_template = Template(
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

