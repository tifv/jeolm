"""
Keys recognized in metarecords:
  $training$matter$combine[*]
"""

from jeolm.target import Target

from jeolm.driver.regular import RegularDriver
from jeolm.driver.groups import GroupsDriver
from jeolm.driver.authors import AuthorsDriver
from jeolm.driver.addtoc import AddTocDriver
from jeolm.driver.source_link import SourceLinkDriver

from . import ( DriverError,
    processing_target, ensure_type_items, )

import logging
logger = logging.getLogger(__name__)


class TrainingDriver(
    GroupsDriver, AuthorsDriver, AddTocDriver, SourceLinkDriver
):

    def _select_outname(self, target, metarecord, date=None):
        return super()._select_outname(target, metarecord, date=None)

    # extension
    @ensure_type_items((RegularDriver.MetabodyItem, Target))
    @processing_target
    def _generate_auto_metabody(self, target, metarecord):

        matter_key, matter_combine = self.select_flagged_item(
            metarecord, '$training$matter$combine', target.flags )
        if matter_key is None:
            yield from super()._generate_auto_metabody(target, metarecord)
            return

        group_flags = target.flags.intersection(self.groups)
        if len(group_flags) != 1:
            raise DriverError(
                "Multiple flags in target {}".format(target)
            ) from None
        group_flag, = group_flags

        if 'no-header' in target.flags:
            raise DriverError

        if matter_combine is True:
            matter_combine = []
            for name in metarecord:
                if name.startswith('$'):
                    continue
                subtarget = target.path_derive(name)
                subrecord = self.get(subtarget.path)
                if '$timetable' not in subrecord:
                    continue
                if group_flag not in subrecord['$timetable']:
                    continue
                matter_combine.append(name)

        if not isinstance(matter_combine, list):
            raise DriverError

        first, *other = matter_combine
        yield self.ClearPageBodyItem()
        first_subtarget = target.path_derive(first).flags_union({'header'})
        yield first_subtarget
        for name in other:
            subtarget = target.path_derive(name)
            subtarget = subtarget.flags_union( {'no-header', 'contained'},
                origin="training matter {target}, key {key}"
                    .format(target=target, key=matter_key) )
            if 'add-toc' in target.flags:
                subtarget = subtarget.flags_difference( {'add-toc'},
                    origin="training matter {target}, key {key}"
                        .format(target=target, key=matter_key) )
            yield subtarget
        yield self.ClearPageBodyItem()

