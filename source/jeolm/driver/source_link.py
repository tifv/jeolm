"""
Keys recognized in metarecords:
  $source-link$root
"""

from string import Template

from jeolm.utils.unique import unique

from jeolm.records import RecordPath
from jeolm.target import Target

from jeolm.driver.regular import RegularDriver

from . import DriverError, processing_target, ensure_type_items

import logging
logger = logging.getLogger(__name__)

from typing import Optional


class SourceLinkDriver(RegularDriver):

    _source_link_root: Optional[str]

    def __init__(self):
        super().__init__()
        self._source_link_root = None

    def _clear_cache(self) -> None:
        self._source_link_root = None
        super()._clear_cache()

    @property
    def _source_link_root(self) -> str:
        if self._source_link_root is not None:
            return self._source_link_root
        else:
            source_link_root = self.get(RecordPath())['$source-link$root']
            if not isinstance(source_link_root, str):
                raise DriverError
            if not source_link_root.endswith('/'):
                raise DriverError
            self._source_link_root = source_link_root
            self._cache_is_clear = False
            return source_link_root

    class SourceLinkBodyItem(RegularDriver.VerbatimBodyItem):
        _template = Template(
            r'\begin{flushright}\ttfamily\small' '\n'
            r'  \href{${root}${source_path}}' '\n'
            r'    {source:${source_path}}' '\n'
            r'\end{flushright}' )

        def __init__(self, source_path, *, root):
            super().__init__(
                value=self._template.substitute(
                    root=root, source_path=source_path )
            )

    class FigureDirLinkBodyItem(SourceLinkBodyItem):
        _template = Template(
            r'\begin{flushright}\ttfamily\small' '\n'
            r'  \href{${root}${source_path}}' '\n'
            r'    {figures:${source_path}}' '\n'
            r'\end{flushright}' )

    @ensure_type_items(RegularDriver.BodyItem)
    @processing_target
    def _generate_body_source( self, target, record=None,
        *, preamble, header_info,
        _seen_targets,
    ):
        if 'source-link' not in target.flags:
            yield from super()._generate_body_source( target, record,
                preamble=preamble, header_info=header_info,
                _seen_targets=_seen_targets )
            return
        figure_parents = []
        for item in super()._generate_body_source( target, record,
            preamble=preamble, header_info=header_info,
            _seen_targets=_seen_targets
        ):
            yield item
            if isinstance(item, self.SourceBodyItem):
                yield self.SourceLinkBodyItem(
                    source_path=item.source_path,
                    root=self._source_link_root )
            elif isinstance(item, self.FigureDefBodyItem):
                figure_parents.append(item.figure_path.parent)
        for figure_parent in unique(figure_parents):
            yield self.FigureDirLinkBodyItem(
                source_path=figure_parent.as_source_path(),
                root=self._source_link_root )

