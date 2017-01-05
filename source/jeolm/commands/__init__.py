import jeolm.project

import logging
logger = logging.getLogger(__name__)


def simple_load_driver(project=None):
    if project is None:
        project = jeolm.project.Project()
    metadata = (project.metadata_class)(project=project)
    metadata.load_metadata_cache()
    return metadata.feed_metadata((project.driver_class)())

