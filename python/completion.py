from collections import OrderedDict as ODict

from pathlib import Path, PurePosixPath as PurePath

import logging
logger = logging.getLogger(__name__)

long_options = (
    '--review', '--root', '--verbose',
    '--clean', '--archive',
    '--list-tex', '--list-asy',
    '--list-target-tex',
)
short_options = {
    '-r' : '--review', '-R' : '--root', '-v' : '--verbose',
    '-c' : '--clean', '-a' : '--archive'
}
pathlist_accepting_options = ('-r', '--review', '--list-tex', '--list-asy')

def main():
    import sys
    n = int(sys.argv[1]) - 1
    args = sys.argv[3:]
    current = args[n]
    previous = args[n-1] if n > 0 else None
    preceding = args[:n]

    if current.startswith('-'):
        if current in short_options:
            print(short_options[current])
            return;
        for option in long_options:
            if option.startswith(current):
                print(option)
        return;

    if previous is not None:
        if previous == '--root':
            # Request for directory completion
            sys.exit(101)
    if any(arg in preceding for arg in pathlist_accepting_options):
        # Request for filename completion
        sys.exit(100)

    from . import filesystem
    root = None
    while '--root' in args:
        if args.index('--root') < len(args) - 1:
            root = Path(args[args.index('--root')+1])
        args[args.index('--root')] = '--whatever'
    try:
        fsmanager = filesystem.FSManager(root=root)
    except filesystem.RootNotfoundError:
        raise SystemExit

    completer = Completer(fsmanager)

    completions = list(completer.complete(current))
    print('\n'.join(completions))

class Completer:
    def __init__(self, fsmanager):
        self.fsmanager = fsmanager
        self.load_target_list()

    def load_target_list(self):

        self.target_list = self.fsmanager.load_updated_completion_cache()
        if self.target_list is not None:
            return

        self.target_list = self.fsmanager.get_driver().list_targets()
        self.fsmanager.dump_completion_cache(self.target_list)

    def complete(self, uncompleted_arg):
        """Return an iterator over completions."""
        if '.' in uncompleted_arg or ' ' in uncompleted_arg:
            return;

        uncompleted_path = PurePath(uncompleted_arg)
        if uncompleted_path.is_absolute():
            return;

        if uncompleted_path == PurePath('.'):
            assert uncompleted_arg == ''
            uncompleted_parent = PurePath('.')
            uncompleted_name = ''
        elif uncompleted_arg.endswith('/'):
            uncompleted_parent = uncompleted_path
            uncompleted_name = ''
            if uncompleted_parent in self.target_list:
                yield str(uncompleted_parent) + '/'
        else:
            uncompleted_parent = uncompleted_path.parent()
            uncompleted_name = uncompleted_path.name

        for path in self.target_list:
            if uncompleted_parent != path.parent():
                continue;
            name = path.name
            assert path.suffix == ''
            if not name.startswith(uncompleted_name):
                continue;
            yield str(uncompleted_parent/name) + '/'

    def readline_completer(self, text, state):
        if not hasattr(self, 'saved_text') or self.saved_text != text:
            self.saved_completion = list(self.complete(text))
            self.saved_text = text
        if state < len(self.saved_completion):
            return self.saved_completion[state];
        else:
            return None;

if __name__ == '__main__':
    main()

