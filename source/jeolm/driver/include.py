"""
Keys recognized in metarecords:
  $include
    list of subpaths for direct metadata inclusion.
"""

from jeolm.records import RecordPath, Records, RecordError

class IncludingRecords(Records):

    def _derive_record(self, parent_record, child_record, path):
        super()._derive_record(parent_record, child_record, path)
        for include_name in child_record.pop('$include', ()):
            include_path = RecordPath(path, include_name)
            include_record = self._get_include_record(include_path)
            self._merge_include_record(child_record, include_record)

    def _get_include_record(self, include_path, *,
        _seen_paths=None
    ):
        if _seen_paths is None:
            _seen_paths = set()
        if include_path in _seen_paths:
            raise RecordError( "Inclusion cycle detected from {}"
                .format(include_path) )
        _seen_paths.add(include_path)

        include_record = self.get(include_path, original=True).copy()
        self._fix_include_record( include_path, include_record,
            _seen_paths=_seen_paths )

        _seen_paths.discard(include_path)
        return include_record

    def _fix_include_record(self, include_path, include_record, *,
        _seen_paths
    ):
        for subinclude_name in include_record.pop('$include', ()):
            subinclude_path = RecordPath(include_path, subinclude_name)
            subinclude_record = self._get_include_record( subinclude_path,
                _seen_paths=_seen_paths )
            self._merge_include_record(include_record, subinclude_record)
        for key in include_record:
            if key.startswith('$'):
                continue
            include_record[key] = include_subrecord = \
                include_record[key].copy()
            self._fix_include_record( include_path/key, include_subrecord,
                _seen_paths=_seen_paths )

    @classmethod
    def _merge_include_record(cls, dest_dict, source_dict):
        for key, source_value in source_dict.items():
            assert key != '$include'
            dest_value = dest_dict.get(key)
            if dest_value is None:
                dest_dict[key] = source_value
            elif key.startswith('$'):
                # no override of attributes
                continue
            else:
                # recursive merge
                dest_dict[key] = dest_value = dest_value.copy()
                assert isinstance(dest_value, dict)
                assert isinstance(source_value, dict)
                cls._merge_include_record(dest_value, source_value)
