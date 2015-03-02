"""
This application aims managing course-like projects, that consist of
many small pieces distributed to course listeners over time.

Application includes build system implemented in Python, and
complementary LaTeX package.
"""

from contextlib import contextmanager

from pathlib import Path

import logging

logger = logging.getLogger(__name__) # pylint: disable=invalid-name
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.NullHandler())

@contextmanager
def setup_logging(verbose=False, colour=True, concurrent=True):
    """
    Context manager.

    Enter:
        Setup handlers and formatters for package-top-level logger.

    Exit:
        If concurrent is True (default), then print out any remaining
        messages and shut down logging system.
    """
    if colour:
        from jeolm.fancify import FancifyingFormatter as Formatter
    else:
        from jeolm.fancify import UnfancifyingFormatter as Formatter
    formatter = Formatter("%(name)s: %(message)s")
    if concurrent:
        from logging.handlers import QueueHandler, QueueListener
        import queue
        import atexit
        log_queue = queue.Queue()
        handler = QueueHandler(log_queue)
        finishing_handler = logging.StreamHandler()
        listener = QueueListener(log_queue, finishing_handler)
        listener.start()
    else:
        handler = finishing_handler = logging.StreamHandler()
    handler.setLevel(logging.INFO if not verbose else logging.DEBUG)
    finishing_handler.setFormatter(formatter)
    logger.addHandler(handler)

    try:
        yield
    finally:
        if concurrent:
            listener.stop()
        else:
            pass

