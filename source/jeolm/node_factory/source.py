from contextlib import suppress
from pathlib import PurePosixPath

import jeolm.node

import logging
logger = logging.getLogger(__name__)

import typing
from typing import Any, Dict
if typing.TYPE_CHECKING:
    import jeolm.project


class SourceNodeFactory:

    project: 'jeolm.project.Project'
    nodes: Dict[Any, jeolm.node.FilelikeNode]

    def __init__(self, *, project: 'jeolm.project.Project') -> None:
        self.project = project
        self.nodes = dict()

    def __call__(self, inpath: PurePosixPath) -> jeolm.node.SourceFileNode:
        assert isinstance(inpath, PurePosixPath), type(inpath)
        assert not inpath.is_absolute(), inpath
        try:
            return self.nodes[inpath]
        except KeyError:
            pass
        node = self.nodes[inpath] = self._prebuild_source(inpath)
        return node

    def _prebuild_source(self, inpath: PurePosixPath) -> jeolm.node.SourceFileNode:
        source_node = jeolm.node.SourceFileNode(
            name='source:{}'.format(inpath),
            path=self.project.source_dir/inpath )
        if not source_node.path.exists():
            logger.warning(
                "Requested source node <YELLOW>%(inpath)s<NOCOLOUR> "
                    "does not exist as file",
                dict(inpath=inpath) )
        return source_node


