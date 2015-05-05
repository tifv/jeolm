"""
This application aims managing course-like projects, that consist of
many small pieces distributed to course listeners over time.

Application includes build system implemented in Python, and
complementary LaTeX package.
"""

from contextlib import contextmanager

from pathlib import Path

import logging as the_logging

logger = the_logging.getLogger(__name__)
logger.setLevel(the_logging.DEBUG)
logger.addHandler(the_logging.NullHandler())

