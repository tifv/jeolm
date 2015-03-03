"""
This application aims managing course-like projects, that consist of
many small pieces distributed to course listeners over time.

Application includes build system implemented in Python, and
complementary LaTeX package.
"""

from contextlib import contextmanager
import queue

from pathlib import Path

import logging
import logging.handlers

logger = logging.getLogger(__name__) # pylint: disable=invalid-name
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.NullHandler())

class LoggingManager:

    def __init__(self, verbose=False, colour=True, concurrent=True):
        if colour:
            from jeolm.fancify import FancifyingFormatter as formatter_class
        else:
            from jeolm.fancify import UnfancifyingFormatter as formatter_class
        self.formatter = formatter_class("%(name)s: %(message)s")
        self.finishing_handler = logging.StreamHandler()
        self.finishing_handler.setFormatter(self.formatter)

        self.concurrent = concurrent
        if self.concurrent:
            self.queue = queue.Queue()
            self.handler = logging.handlers.QueueHandler(self.queue)
            self.listener = None
        else:
            self.handler = self.finishing_handler
        self.handler.setLevel(logging.INFO if not verbose else logging.DEBUG)
        logger.addHandler(self.handler)

    def _get_listener(self):
        listener = logging.handlers.QueueListener(
            self.queue, self.finishing_handler )
        return listener

    def sync(self):
        if self.concurrent:
            if self.listener is not None:
                self.listener.stop()
            self.listener = self._get_listener()
            self.listener.start()

    def __enter__(self):
        if self.concurrent:
            if self.listener is not None:
                raise RuntimeError(
                    "LoggingManager is not a reentrant context manager.")
            self.listener = self._get_listener()
            self.listener.start()

    def __exit__(self, exc_type, exc_value, traceback):
        if self.concurrent:
            self.listener.stop()
            self.listener = None
        return False # reraise exception, if any

