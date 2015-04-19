import jeolm.local

import logging
logger = logging.getLogger(__name__) # pylint: disable=invalid-name

def simple_load_driver(local=None):
    if local is None:
        local = jeolm.local.LocalManager()
    metadata = (local.metadata_class)(local=local)
    metadata.load_metadata_cache()
    return metadata.feed_metadata((local.driver_class)())

