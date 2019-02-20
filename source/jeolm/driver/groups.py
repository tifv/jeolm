from functools import partial
from string import Template
from collections import OrderedDict

from jeolm.utils.ordering import natural_keyfunc
from jeolm.records import RecordPath
from jeolm.target import FlagContainer, Target

from . import ( DriverError,
    process_target_aspect, process_target_key, processing_target,
    ensure_type_items )
from .regular import RegularDriver

import logging
logger = logging.getLogger(__name__)


class GroupsDriver(RegularDriver):

    # extension
    def __init__(self):
        super().__init__()
        self._cache.update(groups=list())

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
            match = self._attribute_key_regex.fullmatch(key)
            if match is None or match.group('stem') != '$groups':
                continue
            group_flags = FlagContainer.split_flags_string(
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

    # extension
    def _derive_record(self, parent_record, child_record, path):
        super()._derive_record(parent_record, child_record, path)
        child_record.setdefault( '$delegate$auto$groups',
            parent_record.get('$delegate$auto$groups', False) )
        child_record.setdefault( '$content$auto$groups',
            parent_record.get('$content$auto$groups', False) )

    @ensure_type_items(Target)
    @processing_target
    def _generate_targets_auto_source( self, target, record,
        *, _seen_targets,
    ):
        call_super = partial( super()._generate_targets_auto_source,
            target, record, _seen_targets=_seen_targets )
        if not record.get('$delegate$auto$groups', False):
            yield from call_super()
            return
        target_flags = target.flags.intersection(self.groups)
        if '$date$groups' not in record:
            logger.warning(
                "Record %(path)s does not define $date$groups",
                dict(path=target.path) )
            return
        record_groups = record['$date$groups']
        if target_flags:
            if target_flags.issubset(record_groups):
                yield from call_super()
            return
        if not set(record_groups).issubset(self.groups):
            wrong_groups = set(record_groups).difference(self.groups)
            raise DriverError( "Unknown groups: " +
                ', '.join(repr(group) for group in sorted(wrong_groups)) )
        for group in record_groups:
            yield from self._generate_targets(target.flags_union({group}))

    def _select_outname_auto(self, target, record, date=None):
        """Return outname."""
        outname_base = '-'.join(target.path.parts)
        target_groups = target.flags.intersection(self.groups)
        if len(target_groups) == 1:
            group, = target_groups
            outname_base = group + '-' + outname_base
            outname_flags = target.flags.__format__( 'optional',
                sorted_flags=sorted(target.flags.as_frozenset - target_groups)
            )
        else:
            outname_flags = '{:optional}'.format(target.flags)
        outname = outname_base + outname_flags
        return outname

    @ensure_type_items(RegularDriver.BodyItem)
    def _generate_body_header_def( self, target, record,
        *, header,
    ):
        yield from super()._generate_body_header_def( target, record,
            header=header )
        target_groups = target.flags.intersection(self.groups)
        if not target_groups:
            return
        group_name = ', '.join(
            self.groups[group_flag]['name']
            for group_flag in sorted(target_groups, key=natural_keyfunc)
        )
        if '%' in group_name:
            raise DriverError(group_name)
        yield self.VerbatimBodyItem(
            self.groupname_def_template.substitute(group_name=group_name)
        )

    @ensure_type_items(RegularDriver.BodyItem)
    @processing_target
    def _generate_body_auto_source( self, target, record,
        *, preamble, header_info,
        _seen_targets,
    ):
        call_super = partial( super()._generate_body_auto_source,
            target, record,
            preamble=preamble, header_info=header_info,
            _seen_targets=_seen_targets )
        if not record.get('$content$auto$groups', False):
            yield from call_super()
            return
        if '$date$groups' not in record:
            logger.warning(
                "Record %(path)s does not define $date$groups",
                dict(path=target.path) )
            return
        target_groups = target.flags.intersection(self.groups)
        if not target_groups:
            yield from call_super()
            return
        if not target_groups.issubset(record['$date$groups']):
            return
        yield from call_super()

    def _get_source_date(self, target, record):
        if '$date$groups' not in record:
            return super()._get_source_date(target, record)
        target_groups = target.flags.intersection(self.groups)
        if not target_groups:
            return super()._get_source_date(target, record)
        date_groups = record['$date$groups']
        if not target_groups.issubset(date_groups):
            raise DriverError
        return self._min_date(date_groups[group] for group in target_groups)

    groupname_def_template = Template(r'\def\jeolmgroupname{$group_name}%')


