from string import Template
from collections import OrderedDict
from datetime import date as date_type

from jeolm.driver.regular import Driver as RegularDriver, DriverError

from jeolm.record_path import RecordPath
from jeolm.flags import FlagContainer
from jeolm.records import RecordNotFoundError
from jeolm.target import Target

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
    # LaTeX-level functions

    @classmethod
    def _constitute_authors(cls, authors, thin_space=r'\,'):
        if len(authors) > 2:
            def abbreviate(author):
                *names, last = author.split(' ')
                return thin_space.join(
                    [name[0] + '.' for name in names] + [last] )
        else:
            def abbreviate(author):
                return author
        return ', '.join(abbreviate(author) for author in authors)

    def _derive_attributes(self, parent_record, child_record, name):
        child_record.setdefault('$delegate$groups',
            parent_record.get('$delegate$groups', True) )
        child_record.setdefault('$source$groups',
            parent_record.get('$source$groups', True) )
        super()._derive_attributes(parent_record, child_record, name)

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
                    yield target.path_derive(subname)
            elif not target.flags.intersection(self.groups):
                for group_flag in self.groups:
                    yield target.flags_union({group_flag})
            else:
                group_flags = target.flags.intersection(self.groups)
                if len(group_flags) != 1:
                    raise DriverError(target) from None
                group_flag, = group_flags
                if group_flag in metarecord['$timetable']:
                    raise # this is an atomic target, nowhere to delegate
                else:
                    pass # group does not match, delegate to nothing
        else:
            return

    @processing_target_aspect(aspect='auto metabody', wrap_generator=True)
    @classifying_items(aspect='metabody', default='verbatim')
    def generate_auto_metabody(self, target, metarecord):

        source_groups = metarecord['$source$groups']
        if not target.flags.check_condition(source_groups):
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
                yield target.derive(subname)
            return

        if not target.flags.intersection(self.groups):
            if len(metarecord['$timetable']) != 1:
                raise DriverError( "Unable to auto matter {target}"
                    .format(target=target) )
            group_name, = metarecord['$timetable']
            yield target.flags_union({group_name})
            return
        present_group_flag, = target.flags.intersection(self.groups)
        if present_group_flag not in target.flags:
            return

        yield from super().generate_auto_metabody(target, metarecord)

    @processing_target_aspect(aspect='header metabody', wrap_generator=True)
    @classifying_items(aspect='resolved_metabody', default='verbatim')
    def generate_header_metabody(self, target, metarecord, *, date):

        yield r'\begingroup'

        if '$authors' in metarecord:
            yield self.substitute_authorsdef(
                authors=self.constitute_authors(metarecord['$authors']) )

        group_flags = target.flags.intersection(self.groups)
        if group_flags:
            if len(group_flags) > 1:
                raise DriverError(
                    "Multiple group flags in {target}"
                    .format(target=target) )
            group_flag, = group_flags
            if '$timetable' not in metarecord or \
                    group_flag not in metarecord['$timetable']:
                raise DriverError(target)
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

    authorsdef_template = r'\def\jeolmauthors{$authors}'
    groupnamedef_template = r'\def\jeolmgroupname{$group_name}'
    period_template = r'$date, пара $period'

    @classmethod
    def constitute_authors(cls, authors, thin_space=r'\,'):
        if len(authors) > 2:
            def abbreviate(author):
                *names, last = author.split(' ')
                return thin_space.join([name[0] + '.' for name in names] + [last])
        else:
            def abbreviate(author):
                return author
        return ', '.join(abbreviate(author) for author in authors)

    @processing_target_aspect(aspect='source metabody', wrap_generator=True)
    @classifying_items(aspect='metabody', default='verbatim')
    def generate_source_metabody(self, target, metarecord):
        if target.flags.issuperset({'addtoc', 'no-header'}):
            if '$caption' in metarecord:
                caption = metarecord['$caption']
            else:
                caption = '; '.join(metarecord['$source$sections'])
            yield self.substitute_addtoc(line=caption)
            yield target.flags_difference({'addtoc'})
        else:
            yield from super().generate_source_metabody(target, metarecord)

    addtoc_template = r'\addcontentsline{toc}{section}{$line}'

