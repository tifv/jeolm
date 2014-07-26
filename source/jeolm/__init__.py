"""
This application aims managing course-like projects, that consist of
many small pieces distributed to course listeners over time.

Application includes build system implemented in Python, and
complementary LaTeX package.
"""

from pathlib import Path

import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.NullHandler())

# This logger is intended to print messages as-is, without name
# prefix.
cleanlogger = logging.getLogger(__name__ + '.clean')
cleanlogger.propagate = False
cleanlogger.setLevel(logging.INFO)
cleanlogger.addHandler(logging.NullHandler())

def setup_logging(verbose=False, colour=True):
    """
    Setup handlers and formatters for package-top-level loggers.

    These include jeolm and jeolm.clean loggers.
    """
    if colour:
        from jeolm.fancify import FancifyingFormatter as Formatter
    else:
        from jeolm.fancify import UnfancifyingFormatter as Formatter
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO if not verbose else logging.DEBUG)
    handler.setFormatter(Formatter("%(name)s: %(message)s"))
    logger.addHandler(handler)
    cleanhandler = logging.StreamHandler()
    cleanhandler.setLevel(logging.INFO)
    cleanhandler.setFormatter(Formatter("%(message)s"))
    cleanlogger.addHandler(cleanhandler)

