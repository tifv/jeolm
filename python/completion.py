from collections import OrderedDict as ODict

from pathlib import Path, PurePosixPath as PurePath

import logging
logger = logging.getLogger(__name__)

def main():
    options = ('--root', '--verbose')
    short_options = {'-R' : '--root', '-v' : '--verbose'}

    subcommands = ('build', 'review', 'list', 'spell', 'clean', )
    subcommand_options = {
        'build' : ('--force-recompile', '--dump', ),
        'list' : ('--type',) }
    subcommand_short_options = {'build' : {'-f' : '--force-recompile'}}
    subcommands_accepting_paths = ('r', 'review', )
    subcommands_accepting_targets = ('build', 'list', 'spell', )

    import sys
    n = int(sys.argv[1]) - 1
#    prog = sys.argv[2]
    args = sys.argv[3:]
    if n == len(args):
        # workaround
        args.append('')
    current = args[n]
    previous = args[n-1] if n > 0 else None
    preceding = args[:n]

    if previous is not None:
        if previous == '--root':
            # Request for directory completion
            sys.exit(101)
    from . import filesystem
    root = None
    while '--root' in args:
        root_key_index = args.index('--root')
        root_value_index = root_key_index + 1
        if root_value_index < len(args):
            root = Path(args[root_value_index])
        del args[root_key_index:root_value_index+1]
        if n > root_value_index:
            n -= 2
        elif n < root_key_index:
            pass
        elif n == root_key_index:
            print('--root')
            return
        else:
            return
    try:
        fsmanager = filesystem.FSManager(root=root)
    except filesystem.RootNotFoundError:
        raise SystemExit

    while '--verbose' in args:
        verbose_key_index = args.index('--verbose')
        del args[verbose_key_index]
        if n > verbose_key_index:
            n -= 1
        elif n < verbose_key_index:
            pass
        else:
            print('--verbose')
            return

    if n == 0:
        for subcommand in subcommands:
            if subcommand.startswith(current):
                print(subcommand)
        return
    subcommand = args[0]
    if current.startswith('-'):
        if current in subcommand_short_options.get(subcommand, ()):
            print(subcommand_short_options[subcommand][current])
            return
        if current in short_options:
            print(short_options[current])
            return
        for option in subcommand_options[subcommand] + options:
            if option.startswith(current):
                print(option)
        return

    if subcommand in subcommands_accepting_paths:
        # Request for filename completion
        sys.exit(100)
    elif subcommand in subcommands_accepting_targets:
        completer = Completer(fsmanager)
        completions = list(completer.complete_target(current))
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

    def complete_target(self, uncompleted_arg):
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
            self.saved_completion = list(self.complete_target(text))
            self.saved_text = text
        if state < len(self.saved_completion):
            return self.saved_completion[state];
        else:
            return None;

if __name__ == '__main__':
    main()

