from pathlib import Path

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.NullHandler())

cleanlogger = logging.getLogger(__name__ + '.clean')
cleanlogger.propagate = False
cleanlogger.setLevel(logging.INFO)
cleanlogger.addHandler(logging.NullHandler())

def setup_logging(verbose=False):
    import sys
    if sys.stderr.isatty():
        from jeolm.fancify import FancyFormatter as Formatter
    else:
        from jeolm.fancify import NotSoFancyFormatter as Formatter
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO if not verbose else logging.DEBUG)
    handler.setFormatter(Formatter("%(name)s: %(message)s"))
    logger.addHandler(handler)
    cleanhandler = logging.StreamHandler()
    cleanhandler.setLevel(logging.INFO)
    cleanhandler.setFormatter(Formatter("%(message)s"))
    cleanlogger.addHandler(cleanhandler)

