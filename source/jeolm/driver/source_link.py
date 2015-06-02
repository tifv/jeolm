"""
Keys recognized in metarecords:
  $source-root-link
"""

from string import Template

from jeolm.driver.regular import RegularDriver

from jeolm.record_path import RecordPath

import logging
logger = logging.getLogger(__name__)


class SourceLinkDriver(RegularDriver):

    @property
    def source_link_root(self, _root=RecordPath()):
        source_link_root = self.getitem(_root)['$source-link$root']
        assert isinstance(source_link_root, str)
        return source_link_root

    @property
    def source_link_default(self, _root=RecordPath()):
        source_link_default = self.getitem(_root).get(
            '$source-link$default', False )
        assert isinstance(source_link_default, bool)
        return source_link_default

    class SourceLinkBodyItem(RegularDriver.VerbatimBodyItem):
        _template = (
            r'\begin{flushright}\ttfamily\small' '\n'
            r'  \href{${root}${inpath}}' '\n'
            r'    {source:${inpath}}' '\n'
            r'\end{flushright}' )
        _substitute = Template(_template).substitute

        def __init__(self, inpath, *, root):
            super().__init__(value=self._substitute(root=root, inpath=inpath))

    @processing_target_aspect( aspect='source metabody [source_link]',
        wrap_generator=True )
    @classifying_items(aspect='metabody', default='verbatim')
    def generate_source_metabody(self, target, metarecord):
        source_link_default = self.source_link_default

        super_metabody = super().generate_source_metabody(target, metarecord)
        if 'no-header' not in target.flags:
            yield from super_metabody
            return
        if 'source-link' not in target.flags:
            if (source_link_default and 'no-source-link' not in target.flags):
                yield target.flags_union({'source-link'})
                return
            else:
                yield from super_metabody
                return

        yield target.flags_delta(
            difference={'source-link'},
            union=( {'no-source-link'} if source_link_default else {} ))
        yield self.RequirePackageBodyItem(package='hyperref')
        yield self.SourceLinkBodyItem(
            inpath=target.path.as_inpath(suffix='.tex'),
            root=self.source_link_root
        )

    source_link_template = (
        r'\begin{flushright}\ttfamily\small' '\n'
        r'\href{$target}{source:$text}' '\n'
        r'\end{flushright}' )

