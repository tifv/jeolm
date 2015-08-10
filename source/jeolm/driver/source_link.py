"""
Keys recognized in metarecords:
  $source-root-link
"""

from string import Template

from jeolm.record_path import RecordPath
from jeolm.target import Target

from jeolm.driver.regular import RegularDriver

from . import processing_target, ensure_type_items

import logging
logger = logging.getLogger(__name__)


class SourceLinkDriver(RegularDriver):

    @property
    def _source_link_root(self, _root=RecordPath()):
        source_link_root = self.get(_root)['$source-link$root']
        assert isinstance(source_link_root, str)
        return source_link_root

    class SourceLinkBodyItem(RegularDriver.VerbatimBodyItem):
        _template = Template(
            r'\begin{flushright}\ttfamily\small' '\n'
            r'  \href{${root}${inpath}}' '\n'
            r'    {source:${inpath}}' '\n'
            r'\end{flushright}' )

        def __init__(self, inpath, *, root):
            super().__init__(
                value=self._template.substitute(root=root, inpath=inpath) )

    @ensure_type_items((RegularDriver.MetabodyItem, Target))
    @processing_target
    def _generate_source_metabody(self, target, metarecord):

        if 'source-link' not in target.flags:
            yield from super()._generate_source_metabody(target, metarecord)
            return

        yield target.flags_difference({'source-link'})
        yield self.RequirePackageBodyItem(package='hyperref')
        yield self.SourceLinkBodyItem(
            inpath=target.path.as_inpath(suffix='.tex'),
            root=self._source_link_root
        )

    source_link_template = (
        r'\begin{flushright}\ttfamily\small' '\n'
        r'\href{$target}{source:$text}' '\n'
        r'\end{flushright}' )

