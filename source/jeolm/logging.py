import logging

import jeolm
jeolm_logger = logging.getLogger(jeolm.__name__)

from jeolm.fancify import fancify, unfancify

def setup_logging(level=logging.INFO, colour=True):
    node_formatter = NodeFormatter(
        "[{node_name}] {message}", colour=colour)
    formatter = MainFormatter(
        "{name}: {message}", colour=colour,
        node_formatter=node_formatter )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.setLevel(level)
    jeolm_logger.setLevel(level)
    jeolm_logger.addHandler(handler)

class FancifyingFormatter(logging.Formatter):

    def __init__(self, fmt, datefmt=None, *,
        colour=True
    ):
        fmt = '{term_bold}' + fmt + '{term_regular}'
        super().__init__(fmt=fmt, datefmt=datefmt, style='{')
        self.fancify = fancify if colour else unfancify

    def format(self, record):
        record.msg = self.fancify(record.msg)
        if record.levelno <= logging.INFO:
            bold, regular = '', ''
        else:
            bold, regular = self.fancify('<BOLD>'), self.fancify('<REGULAR>')
        record.term_bold = bold
        record.term_regular = regular
        return super().format(record)

class MainFormatter(FancifyingFormatter):

    def __init__(self, fmt, datefmt=None, *,
        colour=True, node_formatter
    ):
        super().__init__(fmt=fmt, datefmt=datefmt, colour=colour)
        self.node_formatter = node_formatter

    def format(self, record):
        if hasattr(record, 'node'):
            return self.node_formatter.format(record)
        return super().format(record)

class NodeFormatter(FancifyingFormatter):

    def format(self, record):
        record.node_name = self._fancify_node_name(
            record.node, record.levelno )
        super_message = super().format(record)
        if hasattr(record, 'prog_output'):
            assert not record.exc_info and not record.stack_info
            return ( "{super_message}\n{prog_output}"
                "{term_bold}"
                    "(output while building node {node_name})"
                "{term_regular}"
                .format(super_message=super_message, **record.__dict__)
            )
        else:
            return super_message

    def _fancify_node_name(self, node, level):
        if level <= logging.DEBUG:
            colour = '<CYAN>'
        elif level <= logging.INFO:
            colour = '<MAGENTA>'
        elif level <= logging.WARNING:
            colour = '<YELLOW>'
        else:
            colour = '<RED>'
        return self.fancify( '{colour}{node.name}<NOCOLOUR>'
            .format(node=node, colour=colour)
        )

