"""
Keys recognized in metarecords:
  $groups[+]
    Only works in toplevel. Declares a group.

  $timetable
  $groups$delegate
  $groups$delegate$into
  $groups$matter
  $groups$matter$into

"""

from collections import OrderedDict
from datetime import date as date_type

from jeolm.driver.regular import RegularDriver, DriverError

from jeolm.record_path import RecordPath
from jeolm.flags import FlagContainer
from jeolm.target import Target
from jeolm.utils import natural_keyfunc

import logging
logger = logging.getLogger(__name__)


class GroupsDriver(RegularDriver):

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
        for key, value in self.getitem(RecordPath()).items():
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

    def list_timetable(self, path=RecordPath()):
        for metapath, metarecord in self.items(path=path):
            with self.process_target_aspect(
                Target(metapath, ()), aspect="timetable"
            ):
                yield from self._list_metarecord_timetable(
                    metapath, metarecord )

    def _list_metarecord_timetable(self, metapath, metarecord):
        timetable = metarecord.get('$timetable')
        if timetable is None:
            return
        for group_flag, group_timetable in timetable.items():
            if not isinstance(group_flag, str):
                raise DriverError(type(group_flag))
            if group_flag not in self.groups:
                raise DriverError(group_flag)
            if not isinstance(group_timetable, dict):
                raise DriverError(type(group_timetable))
            for date, date_timetable in group_timetable.items():
                if not isinstance(date, date_type):
                    raise DriverError(type(date))
                if not isinstance(date_timetable, dict):
                    raise DriverError(type(date_timetable))
                for period, period_value in date_timetable.items():
                    if not isinstance(period, int):
                        raise DriverError(type(period))
                    if period_value is not None:
                        raise DriverError(period_value)
                    yield metapath, metarecord, group_flag, date, period

    def _extract_first_period(self, target, metarecord, group_flag):
        try:
            group_timetable = metarecord['$timetable'][group_flag]
        except KeyError as error:
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

    ##########
    # Record extension

    def _derive_attributes(self, parent_record, child_record, name):
        child_record.setdefault('$groups$delegate',
            parent_record.get('$groups$delegate', True) )
        child_record.setdefault('$groups$matter',
            parent_record.get('$groups$matter', True) )
        super()._derive_attributes(parent_record, child_record, name)

    ##########
    # Record-level functions (delegate)

    @fetching_metarecord
    @processing_target_aspect(aspect='delegators', wrap_generator=True)
    def generate_delegators(self, target, metarecord):
        try:
            yield from super().generate_delegators(target, metarecord)
        except self.NoDelegators:
            delegate_groups = metarecord['$groups$delegate']
            if not target.flags.check_condition(delegate_groups):
                raise
            if '$timetable' not in metarecord:
                for subname in metarecord:
                    if subname.startswith('$'):
                        continue
                    subrecord = self[target.path/subname]
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

    @processing_target_aspect( aspect='auto metabody [training]',
        wrap_generator=True )
    @classifying_items(aspect='metabody', default='verbatim')
    def generate_auto_metabody(self, target, metarecord):

        matter_groups = metarecord['$groups$matter']
        if not target.flags.check_condition(matter_groups):
            yield from super().generate_auto_metabody(target, metarecord)
            return

        if '$timetable' not in metarecord or not metarecord['$timetable']:
            if metarecord.get('$source$able', False):
                raise DriverError(
                    "Sourceable target {target} does not have timetable"
                    .format(target=target) )
            for subname in metarecord:
                if subname.startswith('$'):
                    continue
                subrecord = self[target.path/subname]
                matter_groups_able = subrecord.get('$groups$matter$into', True)
                if not target.flags.check_condition(matter_groups_able):
                    continue
                yield self.ClearPageBodyItem()
                yield target.path_derive(subname)
                yield self.ClearPageBodyItem()
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

        yield from super().generate_auto_metabody(target, metarecord)

    def _generate_header_def_metabody(self, target, metarecord, *, date):

        group_flags = target.flags.intersection(self.groups)
        if group_flags:
            yield self.substitute_groupname_def(
                group_name=', '.join(
                    self.groups[group_flag]['name']
                    for group_flag in sorted(group_flags, key=natural_keyfunc)
                ) )

        yield from super()._generate_header_def_metabody(
            target, metarecord, date=date )

    def _find_date(self, target, metarecord, group_flag=None):
        if group_flag is None:
            group_flags = target.flags.intersection(self.groups)
            if not group_flags or '$timetable' not in metarecord:
                return super()._find_date(target, metarecord)
            if len(group_flags) > 1:
                date = self.min_date(list(
                    self._find_date(target, metarecord, group_flag=group_flag)
                    for group_flag in group_flags ))
                if date is None:
                    return super()._find_date(target, metarecord)
                else:
                    return date
            group_flag, = group_flags
        first_date, first_period = self._extract_first_period(
            target, metarecord, group_flag )
        if first_date is not None:
            if first_period is not None:
                return self.substitute_period(
                    date=self.constitute_date(first_date),
                    period=first_period )
            else:
                return first_date
        return super()._find_date(target, metarecord)

    groupname_def_template = r'\def\jeolmgroupname{$group_name}'
    period_template = r'$date, пара $period'

