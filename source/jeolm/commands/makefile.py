from shlex import quote

from pathlib import Path

from jeolm.node import ( Node, PathNode, BuildablePathNode,
    FileNode, SubprocessCommand, LazyWriteTextCommand, )
from jeolm.node.directory import DirectoryNode, MakeDirCommand
from jeolm.node.symlink import SymLinkNode, ProxyNode

from jeolm.node_factory import TargetNode

import logging
logger = logging.getLogger(__name__) # pylint: disable=invalid-name


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
            while True:
                if isinstance(need, SymLinkNode):
                    order_only_needs.append(need)
                    need = need.source
                elif isinstance(need, ProxyNode):
                    need = need.source
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
        '{dependencies}' '\n'
        '.PHONY: {target}' )

    @classmethod
    def represent(cls, node, *, viewpoint):
        return cls._template.format(
            target=cls._represent_node_TargetNode(node),
            dependencies=cls._represent_dependencies(
                node, viewpoint=viewpoint )
        )

    @classmethod
    def _is_order_only_need(cls, node, need):
        return True


class LinkRuleRepresenter(RuleRepresenter):

    _template = (
        '{dependencies}' '\n'
        '\t' 'ln --symbolic --force {link_target} "$@"' )

    @classmethod
    def represent(cls, node, *, viewpoint):
        return cls._template.format(
            dependencies=cls._represent_dependencies(
                node, viewpoint=viewpoint ),
            link_target=quote(node.link_target) )

    @classmethod
    def _is_order_only_need(cls, node, need):
        if need is node.source:
            return True
        return super()._is_order_only_need(node, need)


class DirectoryRuleRepresenter(RuleRepresenter):

    _template = (
        '{dependencies}' '\n'
        '\t' '{command} "$@"' )

    @classmethod
    def represent(cls, node, *, viewpoint):
        command = node.command
        if not isinstance(command, MakeDirCommand):
            raise RuntimeError(type(command))
        bash_command = 'mkdir --parents' if command.parents else 'mkdir'
        return cls._template.format(
            dependencies=cls._represent_dependencies(
                node, viewpoint=viewpoint ),
            command=bash_command )


class SubprocessRuleRepresenter(RuleRepresenter):

    _template = (
        '{dependencies}' '\n'
        '\t' '{command}' )

    @classmethod
    def represent(cls, node, *, viewpoint):
        command = node.command
        return cls._template.format(
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


class MakefileGenerator:

    _TargetRuleRepresenter = TargetRuleRepresenter
    _LinkRuleRepresenter = LinkRuleRepresenter
    _DirectoryRuleRepresenter = DirectoryRuleRepresenter
    _SubprocessRuleRepresenter = SubprocessRuleRepresenter

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
        if isinstance(node, ProxyNode):
            raise UnrepresentableNode(node)

        # PathNode cases
        if not isinstance(node, BuildablePathNode):
            raise UnbuildableNode(node)
        if isinstance(node, SymLinkNode):
            return cls._represent_link_rule(
                node, viewpoint=viewpoint )
        elif isinstance(node, DirectoryNode):
            return cls._DirectoryRuleRepresenter.represent(
                node, viewpoint=viewpoint )
        elif isinstance(node, FileNode):
            command = node.command
            if command is None:
                raise RuntimeError("FileNode is expected to have a command")
            if isinstance(command, SubprocessCommand):
                return cls._SubprocessRuleRepresenter.represent(
                    node, viewpoint=viewpoint )
            if isinstance(command, LazyWriteTextCommand):
                raise UnbuildableNode(node)
            else:
                raise TypeError(
                    "Unknown class of command: {}".format(type(command)) )
        else:
            raise TypeError(
                "Unknown subclass of PathNode: {}".format(type(node)) )

    @classmethod
    def _represent_link_rule(cls, node, *, viewpoint):
        return cls._LinkRuleRepresenter.represent(
            node, viewpoint=viewpoint )

