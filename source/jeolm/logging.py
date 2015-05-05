from logging import Formatter, StreamHandler, DEBUG, INFO, WARNING

from jeolm import logger as jeolm_logger
from jeolm.fancify import fancify, unfancify

def setup_logging(verbose=False, colour=True):
    node_formatter = NodeFormatter(
        "[{node_name}] {message}", colour=colour)
    formatter = MainFormatter(
        "{name}: {message}", colour=colour,
        node_formatter=node_formatter )
    handler = StreamHandler()
    handler.setFormatter(formatter)
    handler.setLevel(INFO if not verbose else DEBUG)
    jeolm_logger.addHandler(handler)

class FancifyingFormatter(Formatter):

    def __init__(self, fmt=None, datefmt=None, *,
        colour=True
    ):
        fmt = '{term_bold}' + fmt + '{term_reset}'
        super().__init__(fmt=fmt, datefmt=datefmt, style='{')
        self.fancify = fancify if colour else unfancify

    def format(self, record):
        record.msg = self.fancify(record.msg)
        if record.levelno <= INFO:
            bold, reset = '', ''
        else:
            bold, reset = self.fancify('<BOLD>'), self.fancify('<RESET>')
        record.term_bold = bold
        record.term_reset = reset
        return super().format(record)

class MainFormatter(FancifyingFormatter):

    def __init__(self, fmt=None, datefmt=None, *,
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
                "{term_reset}"
                .format(super_message=super_message, **record.__dict__)
            )
        else:
            return super_message

    def _fancify_node_name(self, node, level):
        if level <= DEBUG:
            colour = '<CYAN>'
        elif level <= INFO:
            colour = '<MAGENTA>'
        elif level <= WARNING:
            colour = '<YELLOW>'
        else:
            colour = '<RED>'
        return self.fancify( '{colour}{node.name}<NOCOLOUR>'
            .format(node=node, colour=colour)
        )

