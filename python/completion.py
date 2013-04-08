from collections import OrderedDict as ODict
import logging

from pathlib import Path, PurePath
from . import filesystem, yaml

logger = logging.getLogger(__name__)

class Completer:
    def __init__(self, root):
        with root['meta/in.yaml'].open() as f:
            inrecords = yaml.load(f) or ODict()
        with root['meta/out.yaml'].open() as g:
            outrecords = yaml.load(g) or {}
        self.accessor = Accessor(inrecords, outrecords)

    def complete(self, uncompleted_arg):
        if '.' in uncompleted_arg or ' ' in uncompleted_arg:
            return
        whatever, plus, uncompleted_arg = uncompleted_arg.rpartition('+')

        uncompleted_path = PurePath(uncompleted_arg)
        if uncompleted_path.is_absolute():
            return

        if uncompleted_path == PurePath('.'):
            assert uncompleted_arg == ''
            uncompleted_parent = PurePath('.')
            uncompleted_name = ''
        elif uncompleted_arg.endswith('/'):
            uncompleted_parent = uncompleted_path
            uncompleted_name = ''
        else:
            uncompleted_parent = uncompleted_path.parent()
            uncompleted_name = uncompleted_path.name

        parent_record = self.accessor[uncompleted_parent]
        if parent_record is None:
            return
        assert isinstance(parent_record, dict), parent_record
        for name in sorted(parent_record.keys()):
            if '$' in name:
                continue
            if not name.startswith(uncompleted_name):
                continue
            if name == uncompleted_name:
                yield (whatever + plus +
                    str(uncompleted_parent[uncompleted_name]) + '/' )
            elif name.endswith('.asy'):
                continue
            elif name.endswith('.tex'):
                yield (whatever + plus +
                    str(uncompleted_parent[name[:-4]]) + '/' )
            else:
                yield whatever + plus + str(uncompleted_parent[name]) + '/'

    def readline_completer(self, text, state):
        if not hasattr(self, 'saved_text') or self.saved_text != text:
            self.saved_completion = list(self.complete(text))
            self.saved_text = text
        if state < len(self.saved_completion):
            return self.saved_completion[state]
        else:
            return None

class RecordAccessor:
    def __init__(self, records):
        self.records = records

    def __getitem__(self, path):
        assert isinstance(path, PurePath) and not path.is_absolute(), path

        record = self.records
        missing = False
        for part in path.parts:
            assert '+' not in part and ' ' not in part, path
            if missing or (part not in record):
                missing = True; record = None
            else:
                record = record[part]
        if missing:
            return self.default_factory()
        return record

    def __contains__(self, path):
        assert isinstance(path, PurePath) and not path.is_absolute(), path

        record = self.records
        missing = False
        for part in path.parts:
            assert '+' not in part and ' ' not in part, path
            if missing or (part not in record):
                missing = True; record = None
            else:
                record = record[part]
        return not missing

    @staticmethod
    def default_factory():
        return None

class Accessor:
    def __init__(self, inrecords, outrecords):
        self.inrecords = RecordAccessor(inrecords)
        self.outrecords = RecordAccessor(outrecords)

    def __getitem__(self, path):
        inrecord = self.inrecords[path]
        outrecord = self.outrecords[path]
        if inrecord is not None and not isinstance(inrecord, ODict):
            inrecord = {}
        if outrecord is not None and not isinstance(outrecord, dict):
            outrecord = {}
        if inrecord is None:
            return outrecord
        if outrecord is None:
            return dict(inrecord)
        ans = dict()
        ans.update(inrecord)
        ans.update(outrecord)
        return ans

def main():
    import sys
    root = filesystem.find_root()

    completer = Completer(root)

    print('\n'.join(Completer.complete(sys.argv[2])))

if __name__ == '__main__':
    main()

