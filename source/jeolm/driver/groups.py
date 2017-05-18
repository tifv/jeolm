"""
Keys recognized in metarecords:
  $groups[+]
    Only works in toplevel. Declares a group.

  $timetable
  $groups$delegate
  $groups$delegate$into
  $groups$matter
  $groups$matter$into
  $groups$matter$order

"""

from itertools import chain
from collections import OrderedDict
from string import Template
from datetime import date as date_type

from jeolm.record_path import RecordPath
from jeolm.flags import FlagContainer
from jeolm.target import Target
from jeolm.utils import natural_keyfunc

from jeolm.driver.regular import RegularDriver

from . import ( DriverError,
    process_target_aspect, processing_target,
    ensure_type_items, )

import logging
logger = logging.getLogger(__name__)


class GroupsDriver(RegularDriver):

    # extension
    def __init__(self):
        super().__init__()
        self._cache.update(groups=list())

    ##########
    # Generic group-related methods and properties

    @property
    def groups(self):
        if self._cache['groups']:
            groups, = self._cache['groups']
        else:
            groups = self._get_groups()
            self._cache['groups'].append(groups)
        return groups

    def _get_groups(self):
        groups = OrderedDict()
        for key, value in self.get(RecordPath()).items():
            match = self.attribute_key_regex.fullmatch(key)
            if match is None or match.group('stem') != '$groups':
                continue
            group_flags = FlagContainer.split_flags_group(
                match.group('flags') )
            if len(group_flags) > 1:
                raise RuntimeError(
                    "Incorrect group definition: {}".format(key) )
            group_flag, = group_flags
            if (
                not isinstance(value, dict) or
                not (value.keys() >= {'name'})
            ):
                raise RuntimeError(
                    "Group definition must be a dict with (at least) "
                    "'name' key: {}".format(key) )
            groups[group_flag] = value
        return groups


    ##########
    # Record extension

    # extension
    def _derive_record(self, parent_record, child_record, path):
        super()._derive_record(parent_record, child_record, path)
        child_record.setdefault('$groups$delegate',
            parent_record.get('$groups$delegate', True) )
        child_record.setdefault('$groups$matter',
            parent_record.get('$groups$matter', True) )
        child_record.setdefault('$groups$matter$order',
            parent_record.get('$groups$matter$order', 'default') )

    ##########
    # Record-level functions (delegate)

    # extension
    @processing_target
    def _generate_delegators(self, target, metarecord=None):
        if metarecord is None:
            metarecord = self.get(target.path)

        try:
            yield from super()._generate_delegators(target, metarecord)
        except self.NoDelegators:
            delegate_groups = metarecord['$groups$delegate']
            if not target.flags.check_condition(delegate_groups):
                raise
            if '$timetable' not in metarecord:
                for subname in metarecord:
                    if subname.startswith('$'):
                        continue
                    subrecord = self.get(target.path/subname)
                    if not subrecord.get('$target$able', True):
                        continue
                    delegate_groups_able = subrecord.get(
                        '$groups$delegate$into', True )
                    if not target.flags.check_condition(delegate_groups_able):
                        continue
                    yield target.path_derive(subname)
            elif not target.flags.intersection(self.groups):
                for group_flag in self.groups:
                    yield target.flags_union({group_flag})
            else:
                group_flags = target.flags.intersection(self.groups)
                if len(group_flags) != 1:
                    raise DriverError(
                        "Multiple flags in target {}".format(target)
                    ) from None
                group_flag, = group_flags
                if group_flag in metarecord['$timetable']:
                    raise # this is an atomic target, nowhere to delegate
                else:
                    pass # group does not match, delegate to nothing
        else:
            return

    ##########
    # Record-level functions (outrecord)

    # extension
    @ensure_type_items((RegularDriver.MetabodyItem, Target))
    @processing_target
    def _generate_auto_metabody(self, target, metarecord):

        matter_groups = metarecord['$groups$matter']
        if not target.flags.check_condition(matter_groups):
            yield from super()._generate_auto_metabody(target, metarecord)
            return

        if '$timetable' not in metarecord or not metarecord['$timetable']:
            if metarecord.get('$source$able', False):
                raise DriverError(
                    "Sourceable target {target} does not have timetable"
                    .format(target=target) )
            order = metarecord['$groups$matter$order']
            if order == 'default':
                by_order = self._generate_auto_metabody_by_order
            elif order == 'date':
                by_order = self._generate_auto_metabody_by_date
            else:
                raise ValueError(
                    "Unrecognized $group$matter$order '{order}' "
                    "in target {target}"
                    .format(target=target, order=order) )
            yield from by_order(target, metarecord)
            return

        timetable = metarecord['$timetable']
        if len(timetable) < 1:
            raise RuntimeError(timetable)
        present_group_flags = target.flags.intersection(self.groups)
        if not present_group_flags:
            group_names = set(timetable)
            yield target.flags_union(group_names)
            return
        if not present_group_flags.issubset(timetable.keys()):
            return

        yield from super()._generate_auto_metabody(target, metarecord)

    @ensure_type_items((RegularDriver.MetabodyItem, Target))
    @processing_target
    def _generate_auto_metabody_by_order(self, target, metarecord):
        for subname in metarecord:
            if subname.startswith('$'):
                continue
            subrecord = self.get(target.path/subname)
            matter_groups_able = subrecord.get('$groups$matter$into', True)
            if not target.flags.check_condition(matter_groups_able):
                continue
            yield self.ClearPageBodyItem()
            yield target.path_derive(subname)
            yield self.ClearPageBodyItem()

    @ensure_type_items((RegularDriver.MetabodyItem, Target))
    @processing_target
    def _generate_auto_metabody_by_date(self, target, metarecord):
        group_flags = target.flags.intersection(self.groups)
        if len(group_flags) != 1:
            raise DriverError(
                "Multiple flags in target {}".format(target)
            ) from None
        group_flag, = group_flags
        subtargetperiods = []
        subtargets_extra = []
        for subname in metarecord:
            if subname.startswith('$'):
                continue
            subtarget = target.path_derive(subname)
            subrecord = self.get(target.path/subname)
            matter_groups_able = subrecord.get('$groups$matter$into', True)
            if not target.flags.check_condition(matter_groups_able):
                continue
            subperiod = self._find_period_recursive(
                subtarget, subrecord, group_flag )
            if subperiod != (None, None):
                subtargetperiods.append([subtarget, subperiod])
            else:
                subtargets_extra.append(subtarget)
        def key(subtargetperiod):
            subtarget, (date, period) = subtargetperiod
            assert date is not None
            if period is None:
                period = float('+inf')
            return (date, period)
        sorted_subtargetperiods = sorted(subtargetperiods, key=key)
        subtargets = chain(
            ( subtargetperiod[0]
                for subtargetperiod in sorted_subtargetperiods ),
            subtargets_extra )
        for subtarget in subtargets:
            yield self.ClearPageBodyItem()
            yield subtarget
            yield self.ClearPageBodyItem()

    # extension
    @ensure_type_items((RegularDriver.MetabodyItem))
    def _generate_header_def_metabody(self, target, metarecord, *, date):

        group_flags = target.flags.intersection(self.groups)
        if group_flags:
            group_name = ', '.join(
                self.groups[group_flag]['name']
                for group_flag in sorted(group_flags, key=natural_keyfunc)
            )
            if '%' in group_name:
                raise DriverError(
                    "'%' symbol is found in the group name {}"
                    .format(group_name) )
            yield self.VerbatimBodyItem(
                self.groupname_def_template.substitute(group_name=group_name)
            )

        yield from super()._generate_header_def_metabody(
            target, metarecord, date=date )

    # extension
    def _find_date(self, target, metarecord, *, group_flag=None):
        if group_flag is None:
            group_flags = target.flags.intersection(self.groups)
            if not group_flags or '$timetable' not in metarecord:
                return super()._find_date(target, metarecord)
            if len(group_flags) > 1:
                date = self._min_date(list(
                    self._find_date(target, metarecord, group_flag=group_flag)
                    for group_flag in group_flags ))
                if date is None:
                    return super()._find_date(target, metarecord)
                else:
                    return date
            group_flag, = group_flags
        first_date, first_period = self._find_period(
            target, metarecord, group_flag )
        if first_date is not None:
            if first_period is not None:
                return self.period_template.substitute(
                    date=self._constitute_date(first_date),
                    period=first_period )
            else:
                return first_date
        return super()._find_date(target, metarecord)

    def _find_period(self, target, metarecord, group_flag):
        try:
            group_timetable = metarecord['$timetable'][group_flag]
        except KeyError:
            return None, None
        if group_timetable:
            first_date = min(group_timetable)
        else:
            return None, None
        if group_timetable[first_date]:
            first_period = min(group_timetable[first_date])
        else:
            return first_date, None
        return first_date, first_period

    def _find_period_recursive(self, target, metarecord, group_flag):
        if '$timetable' in metarecord:
            return self._find_period(target, metarecord, group_flag)
        subperiods = []
        for subname in metarecord:
            if subname.startswith('$'):
                continue
            subtarget = target.path_derive(subname)
            subrecord = self.get(subtarget.path)
            matter_groups_able = subrecord.get('$groups$matter$into', True)
            if not target.flags.check_condition(matter_groups_able):
                continue
            subperiod = self._find_period_recursive(
                subtarget, subrecord, group_flag )
            if subperiod == (None, None):
                continue
            subperiods.append(subperiod)
        if not subperiods:
            return (None, None)
        def key(dateperiod):
            date, period = dateperiod
            if period is None:
                period = float('+inf')
            return (date, period)
        return min(subperiods, key=key)

    groupname_def_template = Template(r'\def\jeolmgroupname{$group_name}%')
    period_template = Template(r'$date, пара $period')

