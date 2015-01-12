from pathlib import Path

from jeolm.node import ( Node, TargetNode, PathNode, LinkNode, DirectoryNode,
    SourceFileNode, FileNode,
    SubprocessCommand, WriteTextCommand, )

import logging
if __name__ == '__main__':
    from jeolm import logger
else:
    logger = logging.getLogger(__name__) # pylint: disable=invalid-name

class Rule:
    def __new__(cls, node):
        if cls is not Rule: # guard
            return super(Rule, cls).__new__(cls)
        if not isinstance(node, Node):
            raise TypeError(type(node))
        if not isinstance(node, (PathNode, TargetNode)):
            raise UnrepresentableNode(node)

        if isinstance(node, TargetNode):
            return super(Rule, cls).__new__(TargetRule)
        if isinstance(node, LinkNode):
            return super(Rule, cls).__new__(LinkRule)
        if isinstance(node, DirectoryNode):
            return super(Rule, cls).__new__(DirectoryRule)

        if isinstance(node, SourceFileNode):
            raise UnbuildableNode(node)
        if not isinstance(node, FileNode):
            raise TypeError(type(node))

        command = node.command
        if command is None:
            raise RuntimeError("FileNode is expected to have a command.")
        if isinstance(command, SubprocessCommand):
            return super(Rule, cls).__new__(SubprocessRule)
        if isinstance(command, WriteTextCommand):
            raise UnbuildableNode(node)
        raise RuntimeError("Unknown type of command.")

    def __init__(self, node):
        self.node = node

    def represent(self, *, viewpoint):
        raise NotImplementedError

    @classmethod
    def _represent_needs( cls, needs,
        *, viewpoint,
        order_only_filter=lambda node: isinstance(node, DirectoryNode)
    ):
        normal_needs = []
        order_only_needs = []
        for need in needs:
            if not isinstance(need, (PathNode, TargetNode)):
                continue
            while isinstance(need, LinkNode):
                order_only_needs.append(need)
                need = need.source
            if order_only_filter(need):
                order_only_needs.append(need)
            else:
                normal_needs.append(need)
        needs_repr_parts = []
        if normal_needs:
            needs_repr_parts.extend(
                cls.represent_node(need, viewpoint=viewpoint)
                for need in normal_needs )
        if order_only_needs:
            needs_repr_parts.append('|')
            needs_repr_parts.extend(
                cls.represent_node(need, viewpoint=viewpoint)
                for need in order_only_needs )
        return cls._format_needs(needs_repr_parts)

    @classmethod
    def _format_needs(cls, needs_repr_parts):
        split_next_line = False
        parts = []
        for part in needs_repr_parts:
            if part != '|':
                split_next_line = True
            if split_next_line:
                parts.append(' \\\n  ')
            else:
                parts.append(' ')
            parts.append(part)
            split_next_line = True
        return ''.join(parts)

    @classmethod
    def represent_node(cls, node, *, viewpoint):
        if isinstance(node, PathNode):
            node_s = str(node.path.relative_to(viewpoint))
        elif isinstance(node, TargetNode):
            node_s = node.name
        if ' ' in node_s or '\\' in node_s:
            raise RuntimeError(node_s)
        return node_s

class TargetRule(Rule):
    _template = (
        '{target}:{needs}' '\n'
        '.PHONY: {target}'
    )

    def represent(self, *, viewpoint):
        return self._template.format(
            target=self.represent_node(self.node, viewpoint=viewpoint),
            needs=self._represent_needs(self.node.needs, viewpoint=viewpoint) )

    @classmethod
    def _represent_needs(cls, needs, *, viewpoint):
        return super()._represent_needs( needs,
            viewpoint=viewpoint,
            order_only_filter=lambda need: True )

class LinkRule(Rule):
    _template = (
        '{target}:{needs}' '\n'
        '\t' 'ln --symbolic --force "{link_target}" "$@"'
    )

    def represent(self, *, viewpoint):
        return self._template.format(
            target=self.represent_node(self.node, viewpoint=viewpoint),
            needs=self._represent_needs(
                self.node.needs,
                viewpoint=viewpoint,
                source=self.node.source ),
            link_target=self.node.link_target )

    @classmethod
    def _represent_needs(cls, needs, *, viewpoint, source):
        def order_only_filter(need):
            return need is source or isinstance(need, DirectoryNode)
        return super()._represent_needs( needs,
            viewpoint=viewpoint,
            order_only_filter=order_only_filter )

class DirectoryRule(Rule):
    _template = (
        '{target}:{needs}' '\n'
        '\t' 'mkdir "$@"'
    )

    def represent(self, *, viewpoint):
        # XXX parents
        return self._template.format(
            target=self.represent_node(self.node, viewpoint=viewpoint),
            needs=self._represent_needs(self.node.needs, viewpoint=viewpoint) )

class SubprocessRule(Rule):
    _template = (
        '{target}:{needs}' '\n'
        '\t' '{command}'
    )

    def represent(self, *, viewpoint):
        command = self.node.command
        return self._template.format(
            target=self.represent_node(self.node, viewpoint=viewpoint),
            needs=self._represent_needs(self.node.needs, viewpoint=viewpoint),
            command=self._represent_command(command, viewpoint=viewpoint))

    _command_template = 'cd "{cwd}" && {callargs}'

    def _represent_command(self, command, *, viewpoint):
        return self._command_template.format(
            cwd=command.cwd.relative_to(viewpoint),
            callargs=' '.join('"{}"'.format(arg) for arg in command.callargs) )

class UnrepresentableNode(Exception):
    pass

class UnbuildableNode(Exception):
    pass

def generate_makefile(node, *, viewpoint):
    """
    Return Makefile as a string.

    Update all nodes that cannot be built by Makefile.
    """
    assert isinstance(viewpoint, Path), type(viewpoint)
    makefile_parts = [
        "# Generated by jeolm.makefile for {node}".format(node=node) ]
    for need in node.iter_needs():
        try:
            rule = Rule(need)
        except UnrepresentableNode:
            continue
        except UnbuildableNode as exception:
            node, = exception.args
            if isinstance(node, SourceFileNode):
                level, bold, reset = logging.DEBUG, '', ''
            else:
                level, bold, reset = logging.INFO, '', ''
            logger.log( level,
                "{bold}Node {node} cannot be built by Makefile.{reset}"
                .format(bold=bold, node=node, reset=reset) )
            node.update()
            continue
        makefile_parts.append(rule.represent(viewpoint=viewpoint))
    return '\n\n'.join(makefile_parts)

def main(name='main'):
    import sys
    import jeolm
    import jeolm.local
    import jeolm.target
    import jeolm.commands
    import jeolm.node_factory
    jeolm.setup_logging(verbose=False)
    local = jeolm.local.LocalManager()
    driver = jeolm.commands.simple_load_driver(local=local)
    text_node_factory = jeolm.node_factory.TextNodeFactory(local=local)
    targets = map(jeolm.target.Target.from_string, sys.argv[1:])
    target_node_factory = jeolm.node_factory.TargetNodeFactory(
        local=local, driver=driver, text_node_factory=text_node_factory )
    target_node = target_node_factory(targets, delegate=True, name=name)
    target_node.name = 'first'
    print(generate_makefile(target_node, viewpoint=local.root))

if __name__ == '__main__':
    main()

