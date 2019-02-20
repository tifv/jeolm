from jeolm.node import PathNode
import jeolm.node_factory.target

from . import simple_load_driver

import logging
logger = logging.getLogger(__name__)

def list_sources(targets, *, project, suffixes=None):
    driver = simple_load_driver(project)
    target_node_factory = jeolm.node_factory.target.TargetNodeFactory(
        project=project, driver=driver )
    target_node = target_node_factory(targets)

    source_dir = project.source_dir
    seen = set()
    for node in target_node.iter_needs():
        if not isinstance(node, PathNode):
            continue
        path = node.path
        if source_dir not in path.parents:
            continue
        if suffixes is not None and path.suffix not in suffixes:
            continue
        if path in seen:
            continue
        seen.add(path)
        yield path

