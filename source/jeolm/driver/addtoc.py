"""
Keys recognized in metarecords:
  $caption
  $source$sections
"""

from string import Template

from jeolm.target import Target

from jeolm.driver.regular import RegularDriver

from . import DriverError, processing_target, ensure_type_items

import logging
logger = logging.getLogger(__name__)

class AddToCDriver(RegularDriver):

    @ensure_type_items((RegularDriver.MetabodyItem, Target))
    @processing_target
    def _generate_source_metabody(self, target, metarecord):

        if 'add-toc' not in target.flags:
            yield from super()._generate_source_metabody(target, metarecord)
            return

        yield from self._generate_source_tocline(target, metarecord)
        yield target.flags_difference({'add-toc'})

    @ensure_type_items((RegularDriver.MetabodyItem, Target))
    @processing_target
    def _generate_source_tocline(self, target, metarecord):
        caption = self._find_caption(metarecord)
        if caption is None:
            raise DriverError("Failed to retrieve caption for ToC")
        assert isinstance(caption, str), type(caption)
        if 'print' not in target.flags:
            # with hyperref, \phantomsection is required
            yield self.RequirePackageBodyItem(package='hyperref')
            yield self.VerbatimBodyItem(
                self.phantomsection_template.substitute() )
        else:
            # without hyperref, \phantomsection won't work
            yield self.ProhibitPackageBodyItem(package='hyperref')
        yield self.VerbatimBodyItem(
            self.addtoc_template.substitute(caption=caption) )

    @classmethod
    def _find_caption(cls, metarecord):
        if '$caption' in metarecord:
            return metarecord['$caption']
        elif '$source$sections' in metarecord:
            return '; '.join(metarecord['$source$sections'])
        else:
            return None

    ##########
    # LaTeX-level functions

    addtoc_template = Template(
        r'\addcontentsline{toc}{section}{$caption}' )
    phantomsection_template = Template(
        r'\phantomsection' )

