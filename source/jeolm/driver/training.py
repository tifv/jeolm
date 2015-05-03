from string import Template
from collections import OrderedDict
from functools import partial
from datetime import date as date_type

from jeolm.driver.regular import Driver as RegularDriver, DriverError

from jeolm.record_path import RecordPath
from jeolm.flags import FlagContainer
from jeolm.records import RecordNotFoundError
from jeolm.target import Target

import logging
logger = logging.getLogger(__name__)


class Driver(RegularDriver):

    def __init__(self):
        super().__init__()
        self._cache.update(groups={})

    ##########
    # Generic group-related methods and properties

    @property
    def groups(self):
        if self._cache['groups']:
            return self._cache['groups'].copy()
        groups = OrderedDict()
        for key, value in self.getitem(RecordPath()).items():
            match = self.flagged_pattern.match(key)
            if match is None or match.group('key') != '$group':
                continue
            group_flag, = FlagContainer.split_flags_group(
                match.group('flags') )
            groups[group_flag] = value
            assert isinstance(value, dict)
            assert value.keys() >= {'name', 'timetable'}
        assert groups
        assert isinstance(groups, OrderedDict), type(groups)
        self._cache['groups'] = groups
        return groups

    def list_timetable(self):
        for metapath, metarecord in self.items():
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

    def extract_first_period(self, target, metarecord, group_flag):
        group_timetable = metarecord['$timetable'][group_flag]
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
        child_record.setdefault('$delegate$groups',
            parent_record.get('$delegate$groups', True) )
        child_record.setdefault('$matter$groups',
            parent_record.get('$matter$groups', True) )
        super()._derive_attributes(parent_record, child_record, name)

    ##########
    # Record-level functions (delegate)

    @fetching_metarecord
    @processing_target_aspect(aspect='delegators', wrap_generator=True)
    def generate_delegators(self, target, metarecord):
        try:
            yield from super().generate_delegators(target, metarecord)
        except self.NoDelegators:
            delegate_groups = metarecord['$delegate$groups']
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
                        '$delegate$groups$into', True )
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

#    def select_outname(self, target, metarecord, date=None):
#        no_group = ( not target.flags.intersection(self.groups) or
#            '$timetable' not in metarecord or date is None)
#        if no_group:
#            return super().select_outname(target, metarecord, date=date)
#
#        group_flag, = target.flags.intersection(self.groups)
#        first_date, first_period = self.extract_first_period(
#            target, metarecord, group_flag )
#        date_prefix = (
#            '{0.year:04}-'
#            '{0.month:02}-'
#            '{0.day:02}-'
#            'p{1}'
#        ).format(first_date, first_period)
#        outname = date_prefix + '-' + '{target:outname}'.format(target=target)
#
#        return outname
#
#    def select_outname(self, target, metarecord, date=None):
#        return super().select_outname(target, metarecord, date=None)

    @processing_target_aspect(aspect='auto metabody', wrap_generator=True)
    @classifying_items(aspect='metabody', default='verbatim')
    def generate_auto_metabody(self, target, metarecord):

        matter_groups = metarecord['$matter$groups']
        if not target.flags.check_condition(matter_groups):
            yield from super().generate_auto_metabody(target, metarecord)
            return

        if '$timetable' not in metarecord:
            if metarecord.get('$source$able', False):
                raise DriverError(
                    "Sourceable target {target} does not have timetable"
                    .format(target=target) )
            for subname in metarecord:
                if subname.startswith('$'):
                    continue
                subrecord = self[target.path/subname]
                matter_groups_able = subrecord.get('$matter$groups$into', True)
                if not target.flags.check_condition(matter_groups_able):
                    continue
                yield target.path_derive(subname)
                yield self.substitute_clearpage()
            return
        timetable = metarecord['$timetable']

        present_group_flags = target.flags.intersection(self.groups)
        if not present_group_flags:
            if len(timetable) != 1:
                raise DriverError( "Unable to auto matter {target}"
                    .format(target=target) )
            group_name, = timetable
            yield target.flags_union({group_name})
            return
        if len(present_group_flags) > 1:
            raise DriverError(
                "Multiple group flags present in target {}".format(target) )
        present_group_flag,  = present_group_flags
        if present_group_flag not in timetable:
            return

        yield from super().generate_auto_metabody(target, metarecord)

    @processing_target_aspect(aspect='header metabody', wrap_generator=True)
    @classifying_items(aspect='resolved_metabody', default='verbatim')
    def generate_header_metabody(self, target, metarecord, *, date):

        yield r'\begingroup'

        authors=self._constitute_authors(metarecord)
        if authors is not None:
            assert isinstance(authors, str), type(authors)
            yield self.substitute_authorsdef(authors=authors)

        group_flags = target.flags.intersection(self.groups)
        if group_flags:
            if len(group_flags) > 1:
                raise DriverError(
                    "Multiple group flags in {target}"
                    .format(target=target) )
            group_flag, = group_flags
            if '$timetable' not in metarecord:
                raise DriverError(
                    "Group flag present in target {}, "
                    "but there is no timetable to generate header."
                    .format(target) )
            if group_flag not in metarecord['$timetable']:
                raise DriverError(
                    "Group flag present in target {}, "
                    "but the timetable does not contain it"
                    .format(target) )
            yield self.substitute_groupnamedef(
                group_name=self.groups[group_flag]['name'] )
            first_date, first_period = self.extract_first_period(
                target, metarecord, group_flag )
            if first_date is not None:
                if first_period is not None:
                    date = self.substitute_period(
                        date=self.constitute_date(first_date),
                        period=first_period )
                else:
                    date = first_date

        yield from super().generate_header_metabody(
            target, metarecord, date=date )

        yield r'\endgroup'

    @processing_target_aspect(aspect='source metabody', wrap_generator=True)
    @classifying_items(aspect='metabody', default='verbatim')
    def generate_source_metabody(self, target, metarecord):
        if target.flags.issuperset({'addtoc', 'no-header'}):
            caption = self._constitute_caption(metarecord)
            if caption is None:
                raise DriverError("Failed to retrieve caption for toc")
            assert isinstance(caption, str), type(caption)
            yield self.substitute_addtoc(line=caption)
            yield target.flags_difference({'addtoc'})
        else:
            yield from super().generate_source_metabody(target, metarecord)

    ##########
    # LaTeX-level functions

    @classmethod
    def _constitute_authors(cls, metarecord, thin_space=r'\,'):
        try:
            authors = metarecord['$authors']
        except KeyError as exception:
            return None
        if len(authors) > 2:
            abbreviate = partial(cls._abbreviate_author, thin_space=thin_space)
        else:
            abbreviate = lambda author: author
        return ', '.join(abbreviate(author) for author in authors)

    @staticmethod
    def _abbreviate_author(author, thin_space=r'\,'):
        *names, last = author.split(' ')
        return thin_space.join([name[0] + '.' for name in names] + [last])

    @classmethod
    def _constitute_caption(cls, metarecord):
        if '$caption' in metarecord:
            return metarecord['$caption']
        elif '$source$sections' in metarecord:
            return '; '.join(metarecord['$source$sections'])
        else:
            return None

    authorsdef_template = r'\def\jeolmauthors{$authors}'
    groupnamedef_template = r'\def\jeolmgroupname{$group_name}'
    period_template = r'$date, пара $period'
    addtoc_template = r'\addcontentsline{toc}{section}{$line}'

