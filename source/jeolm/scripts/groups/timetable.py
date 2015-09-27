from collections import OrderedDict

from jeolm.record_path import RecordPath
from jeolm.flags import FlagContainer
from jeolm.fancify import fancify


class TimetableItem:
    pass

class ExtraTimetableItem(TimetableItem):

    def __init__(self, text):
        self.text = text
        self.excessive = False
        super().__init__()

    def is_missing(self):
        return 'MISSING' in self.text

    def fancy_repr(self):
        if self.is_missing():
            return ( fancify('<RED><BOLD>{}<REGULAR><NOCOLOUR>')
                .format(self.text) )
        elif self.excessive:
            return ( fancify('<YELLOW><BOLD>{}<REGULAR><NOCOLOUR>')
                .format(self.text) )
        else:
            return ( fancify('<YELLOW>{}<NOCOLOUR>')
                .format(self.text) )

class RecordTimetableItem(TimetableItem):

    def __init__(self, metapath, caption, authors):
        self.metapath = metapath
        self.caption = caption
        self.authors = authors
        super().__init__()

    def fancy_repr(self):
        return (
            fancify(
                "<GREEN>{item.caption}<RESET> "
                "by <CYAN>{item.authors}<RESET> "
                "({item.metapath})" )
            .format(item=self)
        )

def construct_timetable(*, driver):
    timetable = OrderedDict(
        (group, OrderedDict(
            (date, OrderedDict(
                (period, []) for period in periodlist
            ))
            for date, periodlist in groupvalue['timetable'].items()
        ))
        for group, groupvalue in driver.groups.items()
        if 'timetable' in groupvalue
    )
    _extend_timetable_extra(timetable, driver=driver)
    _extend_timetable_records(timetable, driver=driver)
    return timetable

def _extend_timetable_extra(timetable, *, driver):
    root_record = driver[RecordPath()]
    for group, group_timetable in timetable.items():
        _key, group_timetable_extra = driver.select_flagged_item(
            root_record, '$timetable$extra', FlagContainer({group}))
        if group_timetable_extra is None:
            continue
        for date, date_value in group_timetable_extra.items():
            date_timetable = group_timetable[date]
            if date_value is None:
                continue
            for period, extra in date_value.items():
                period_timetable = date_timetable[period]
                if extra is None:
                    continue
                assert isinstance(extra, str), type(extra)
                period_timetable.append(ExtraTimetableItem(extra))

def _extend_timetable_records(timetable, *, driver):
    for metapath, metarecord, group, date, period in driver.list_timetable():
        period_timetable = timetable[group][date][period]
        if period_timetable:
            for item in period_timetable:
                if isinstance(item, ExtraTimetableItem):
                    item.excessive = True
        period_timetable.append(
            RecordTimetableItem(
                caption=driver._find_caption(metarecord),
                authors=driver._constitute_authors(
                    metarecord['$authors'], thin_space=' ' ),
                metapath=metapath, )
        )

def print_timetable(listed_groups, *, driver,
    from_date=None, to_date=None,
    tab=(' ' * 4)
):
    timetable = construct_timetable(driver=driver)
    if listed_groups is None:
        listed_groups = list(timetable)
    for group in listed_groups:
        print(
            fancify("<MAGENTA>=== <BOLD>{}<REGULAR> ===<RESET>")
            .format(group) )
        for date, date_value in timetable[group].items():
            if from_date is not None and date < from_date:
                continue
            if to_date is not None and date > to_date:
                continue
            print( tab +
                fancify("<CYAN><BOLD>{}<RESET>").format(date) )
            for period, value in date_value.items():
                assert isinstance(value, list), type(value)
                if not value:
                    value = fancify("<RED><BOLD>MISSING<RESET>")
                else:
                    value = ', '.join(item.fancy_repr() for item in value)
                print( tab + tab +
                    fancify("<CYAN>{}: <RESET>{}").format(period, value) )


##########

import re
from datetime import date as date_type
import argparse

import jeolm.commands

def _date_arg( arg_s, *,
    date_regex=re.compile(
        '(?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})' )
):
    match = date_regex.fullmatch(arg_s)
    if match is None:
        raise RuntimeError(arg_s)
    return date_type(
        year=int(match.group('year')),
        month=int(match.group('month')),
        day=int(match.group('day')), )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('groups', nargs='*')
    parser.add_argument('--from-date', type=_date_arg)
    parser.add_argument('--to-date', type=_date_arg)
    args = parser.parse_args()
    if args.groups:
        groups = args.groups
    else:
        groups = None

    print_timetable( groups,
        from_date=args.from_date, to_date=args.to_date,
        driver=jeolm.commands.simple_load_driver() )

if __name__ == '__main__':
    main()

