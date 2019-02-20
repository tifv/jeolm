from shlex import quote

from pathlib import Path

from jeolm.node import ( Node, PathNode, BuildablePathNode,
    FileNode, SubprocessCommand, )
from jeolm.node.directory import DirectoryNode, MakeDirCommand
from jeolm.node.symlink import SymLinkNode, SymLinkCommand, ProxyNode
from jeolm.node.text import WriteTextCommand
from jeolm.node.cyclic import AutowrittenNeed
from jeolm.node.latex import LaTeXCommand

from jeolm.node_factory.target import TargetNode
from jeolm.node_factory.document import AsymptoteFigureNode

import logging
logger = logging.getLogger(__name__)


class UnrepresentableNode(Exception):
    pass

class UnbuildableNode(Exception):
    pass


class RuleRepresenter:

    @classmethod
    def represent(cls, node, *, viewpoint):
        raise NotImplementedError

    @classmethod
    def _represent_node(cls, node, *, viewpoint):
        if isinstance(node, PathNode):
            return cls._represent_node_PathNode(
                node, viewpoint=viewpoint )
        elif isinstance(node, TargetNode):
            return cls._represent_node_TargetNode(node)
        else:
            raise RuntimeError(type(node))

    # pylint: disable=invalid-name

    @classmethod
    def _represent_node_TargetNode(cls, node):
        node_repr = node.name
        cls._check_node_representation(node_repr)
        return node_repr

    @classmethod
    def _represent_node_PathNode(cls, node, *, viewpoint):
        node_repr = str(node.path.relative_to(viewpoint))
        cls._check_node_representation(node_repr)
        return node_repr

    # pylint: enable=invalid-name

    @staticmethod
    def _check_node_representation(node_repr):
        if any(x in node_repr for x in '\t\n #\\:'):
            raise RuntimeError(
                "Prohibited symbols found in node representation: {}"
                .format(quote(node_repr)) )

    @classmethod
    def _represent_dependencies(cls, node, *, viewpoint):
        normal_needs, order_only_needs = cls._split_needs(node)
        parts = []
        def add_newline():
            parts.append(' \\\n  ')
        def add_space():
            parts.append(' ')
        def add_node(node):
            parts.append(cls._represent_node(node, viewpoint=viewpoint))
        add_node(node)
        parts.append(':')

        if normal_needs:
            for need in normal_needs:
                add_newline()
                add_node(need)
        if order_only_needs:
            if normal_needs:
                add_newline()
            else:
                add_space()
            parts.append('|')
            for need in order_only_needs:
                add_newline()
                add_node(need)
        return ''.join(parts)

    @classmethod
    def _split_needs(cls, node):
        """Return pair of lists (normal_needs, order_only_needs)."""
        normal_needs = []
        order_only_needs = []
        for need in node.needs:
            if not isinstance(need, (PathNode, TargetNode)):
                continue
            if isinstance(need, AutowrittenNeed):
                continue
            while True:
                if isinstance(need, SymLinkNode):
                    order_only_needs.append(need)
                    need = need.source
                elif isinstance(need, ProxyNode):
                    need = need.source
                elif isinstance(need, AsymptoteFigureNode):
                    if need.link_node is None:
                        need.refresh()
                    if need.link_node is None:
                        raise RuntimeError
                    need = need.link_node
                else:
                    break
            if cls._is_order_only_need(node, need):
                order_only_needs.append(need)
            else:
                normal_needs.append(need)
        return normal_needs, order_only_needs

    # pylint: disable=unused-argument

    @classmethod
    def _is_order_only_need(cls, node, need):
        return isinstance(need, DirectoryNode)

    # pylint: enable=unused-argument


class TargetRuleRepresenter(RuleRepresenter):

    _template = (
        '# {node.name}' '\n'
        '{dependencies}' '\n'
        '.PHONY: {target}' )

    @classmethod
    def represent(cls, node, *, viewpoint):
        return cls._template.format(
            node=node,
            target=cls._represent_node_TargetNode(node),
            dependencies=cls._represent_dependencies(
                node, viewpoint=viewpoint )
        )

    @classmethod
    def _is_order_only_need(cls, node, need):
        return True


class LinkRuleRepresenter(RuleRepresenter):

    _template = (
        '# {node.name}' '\n'
        '{dependencies}' '\n'
        '\t' 'ln --symbolic --force {link_target} "$@"' )

    @classmethod
    def represent(cls, node, *, viewpoint):
        command = node.command
        if not isinstance(command, SymLinkCommand):
            raise RuntimeError(type(command))
        return cls._template.format(
            node=node,
            dependencies=cls._represent_dependencies(
                node, viewpoint=viewpoint ),
            link_target=quote(command.target) )

    @classmethod
    def _is_order_only_need(cls, node, need):
        if need is node.source:
            return True
        return super()._is_order_only_need(node, need)


class DirectoryRuleRepresenter(RuleRepresenter):

    _template = (
        '# {node.name}' '\n'
        '{dependencies}' '\n'
        '\t' 'mkdir "$@"' )

    _template_parents = (
        '# {node.name}' '\n'
        '{dependencies}' '\n'
        '\t' 'mkdir --parents "$@"' )

    @classmethod
    def represent(cls, node, *, viewpoint):
        command = node.command
        if not isinstance(command, MakeDirCommand):
            raise RuntimeError(type(command))
        template = ( cls._template_parents
            if command.parents else cls._template )
        return template.format(
            node=node,
            dependencies=cls._represent_dependencies(
                node, viewpoint=viewpoint ), )


class SubprocessRuleRepresenter(RuleRepresenter):

    _template = (
        '# {node.name}' '\n'
        '{dependencies}' '\n'
        '\t' '{command}' )

    @classmethod
    def represent(cls, node, *, viewpoint):
        command = node.command
        return cls._template.format(
            node=node,
            dependencies=cls._represent_dependencies(
                node, viewpoint=viewpoint ),
            command=cls._represent_command(
                command, viewpoint=viewpoint ) )

    _command_template = 'cd {cwd} && {callargs}'

    @classmethod
    def _represent_command(cls, command, *, viewpoint):
        return cls._command_template.format(
            cwd=quote(str(command.cwd.relative_to(viewpoint))),
            callargs=' '.join(quote(arg) for arg in command.callargs) )


class LaTeXRuleRepresenter(RuleRepresenter):

    _template = (
        '# {node.name}' '\n'
        '{dependencies}' '\n'
        '\t' '{command}' )

    @classmethod
    def represent(cls, node, *, viewpoint):
        command = node.command
        return cls._template.format(
            node=node,
            dependencies=cls._represent_dependencies(
                node, viewpoint=viewpoint ),
            command=cls._represent_command(
                command, viewpoint=viewpoint ) )

    _command_template = 'cd {cwd} && latexmk {latexmk_args}'

    _compiler_opts = {
        'latex' : None,
        'pdflatex' : '-pdf',
        'lualatex' : '-lualatex',
        'xelatex' : '-xelatex',
    }

    @classmethod
    def _represent_command(cls, command, *, viewpoint):
        assert isinstance(command, LaTeXCommand)
        cwd = command.cwd
        latexmk_args = ( cls._compiler_opts[command.latex_command],
            f'-output-directory={command.output_dir.relative_to(cwd)}',
            f'-jobname={command.jobname}',
            *command.latex_mode_args,
            command.source_name,
        )
        return cls._command_template.format(
            cwd=quote(str(cwd.relative_to(viewpoint))),
            latexmk_args=' '.join( quote(arg)
                for arg in latexmk_args if arg is not None )
        )


class MakefileGenerator:

    _TargetRuleRepresenter = TargetRuleRepresenter
    _LinkRuleRepresenter = LinkRuleRepresenter
    _DirectoryRuleRepresenter = DirectoryRuleRepresenter
    _SubprocessRuleRepresenter = SubprocessRuleRepresenter
    _LaTeXRuleRepresenter = LaTeXRuleRepresenter

    @classmethod
    def generate(cls, node, *, viewpoint):
        """
        Return triple containing makefile as a string and additional info.

        Return triple:
            makefile (string):
                contents of a makefile, which should be executed from viewpoint
                directory;
            unbuildable_nodes (list):
                nodes that correspond to files but cannot be rebuilt by
                makefile. These nodes have to be updated by jeolm.
            unrepresentable_nodes (list):
                nodes that has no possible representation in makefile.
        """

        assert isinstance(viewpoint, Path), type(viewpoint)
        makefile_parts = [
            "# Generated by jeolm.makefile for {node}".format(node=node) ]
        unbuildable_nodes = []
        unrepresentable_nodes = []

        for need in node.iter_needs():
            # pylint: disable=unpacking-non-sequence
            try:
                rule_repr = cls._represent_rule(need, viewpoint=viewpoint)
            except UnbuildableNode as exception:
                node, = exception.args
                unbuildable_nodes.append(node)
            except UnrepresentableNode as exception:
                node, = exception.args
                unrepresentable_nodes.append(node)
            else:
                makefile_parts.append(rule_repr)
            # pylint: enable=unpacking-non-sequence
        return (
            '\n\n'.join(makefile_parts),
            unbuildable_nodes,
            unrepresentable_nodes )

    @classmethod
    def _represent_rule(cls, node, *, viewpoint):
        """Return Makefile rule as string."""
        if not isinstance(node, Node):
            raise TypeError(type(node))
        if isinstance(node, TargetNode):
            return cls._TargetRuleRepresenter.represent(
                node, viewpoint=viewpoint )
        if not isinstance(node, PathNode):
            raise UnrepresentableNode(node)

        return cls._represent_path_rule(node, viewpoint=viewpoint)

    @classmethod
    def _represent_path_rule(cls, node, *, viewpoint):
        if isinstance(node, ProxyNode):
            raise UnrepresentableNode(node)
        if isinstance(node, AsymptoteFigureNode):
            if node.link_node is None:
                node.refresh()
            raise UnrepresentableNode(node)
        if isinstance(node, AutowrittenNeed):
            raise UnrepresentableNode(node)
        if not isinstance(node, BuildablePathNode):
            raise UnbuildableNode(node)
        if isinstance(node, SymLinkNode):
            return cls._represent_link_rule(
                node, viewpoint=viewpoint )
        elif isinstance(node, DirectoryNode):
            return cls._DirectoryRuleRepresenter.represent(
                node, viewpoint=viewpoint )
        elif isinstance(node, FileNode):
            return cls._represent_file_rule(node, viewpoint=viewpoint)
        else:
            raise TypeError(
                "Unknown subclass of PathNode: {}".format(type(node)) )

    @classmethod
    def _represent_file_rule(cls, node, *, viewpoint):
        command = node.command
        if command is None:
            raise ValueError("FileNode is expected to have a command")
        if isinstance(command, SubprocessCommand):
            if isinstance(command, LaTeXCommand):
                return cls._LaTeXRuleRepresenter.represent(
                    node, viewpoint=viewpoint )
            return cls._SubprocessRuleRepresenter.represent(
                node, viewpoint=viewpoint )
        if isinstance(command, WriteTextCommand):
            raise UnbuildableNode(node)
        else:
            raise TypeError(
                "Unknown class of command: {}".format(type(command)) )

    @classmethod
    def _represent_link_rule(cls, node, *, viewpoint):
        return cls._LinkRuleRepresenter.represent(
            node, viewpoint=viewpoint )

