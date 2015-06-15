"""
Keys recognized in metarecords:
  $caption
  $source$sections
"""

from jeolm.driver.regular import RegularDriver, DriverError

import logging
logger = logging.getLogger(__name__)


class AddToCDriver(RegularDriver):

    @processing_target_aspect( aspect='source metabody [addtoc]',
        wrap_generator=True )
    @classifying_items(aspect='metabody', default='verbatim')
    def generate_source_metabody(self, target, metarecord):

        super_metabody = super().generate_source_metabody(target, metarecord)
        if 'no-header' not in target.flags:
            yield from super_metabody
            return
        if 'add-toc' not in target.flags:
            yield from super_metabody
            return

        caption = self._find_caption(metarecord)
        if caption is None:
            raise DriverError("Failed to retrieve caption for ToC")
        assert isinstance(caption, str), type(caption)
        # without hyperref, \phantomsection won't work
        # (and with hyperref, \phantomsection is required)
        yield self.RequirePackageBodyItem(package='hyperref')
        yield self.substitute_addtoc(line=caption)
        yield target.flags_difference({'add-toc'})

    @classmethod
    def _find_caption(cls, metarecord):
        if '$caption' in metarecord:
            return metarecord['$caption']
        elif '$source$sections' in metarecord:
            return '; '.join(metarecord['$source$sections'])
        else:
            return None

    addtoc_template = r'\phantomsection\addcontentsline{toc}{section}{$line}'

    ##########
    # LaTeX-level functions

