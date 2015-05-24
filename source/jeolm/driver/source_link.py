"""
Keys recognized in metarecords:
  $source-root-link
"""

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
        yield self.substitute_source_link(
            target=( str(self.source_link_root) +
                str(target.path.as_inpath(suffix='.tex')) ),
            text=str(target.path)
        )

    def _constitute_source_link(self, metapath):
        return self.substitute_source_link(
            target=(
                str(self.source_root_link) +
                str(metapath.as_inpath(suffix='.tex')) ),
            text=str(metapath)
        )

    source_link_template = (
        r'\begin{flushright}\ttfamily\small' '\n'
        r'\href{$target}{source:$text}' '\n'
        r'\end{flushright}' )

