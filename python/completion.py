import abc

from pathlib import Path, PurePosixPath

import logging
logger = logging.getLogger(__name__)

def main():
    options = ('--root', '--verbose')
    short_options = {'-R' : '--root', '-v' : '--verbose'}

    subcommands = ('build', 'review', 'list', 'spell', 'clean', )
    subcommand_options = {
        'build' : ('--force-latex', '--force-generate', '--review', '--dump'),
        'list' : ('--type',),
        'review' : ('--recursive',),
    }
    subcommand_short_options = {
        'build' : {
            '-f' : '--force-latex', '-F' : '--force-generate',
            '-r' : '--review' },
        'review' : {'-r' : '--recursive'}
    }
    subcommands_accepting_paths = ('r', 'review', )
    subcommands_accepting_targets = ('build', 'list', 'spell', 'expose', )

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
    import jeolm.local
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
        local = jeolm.local.LocalManager(root=root)
    except local.RootNotFoundError:
        jeolm.local.report_missing_root()
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
        completer = CachingCompleter(local)
        completions = list(completer.complete_target(current))
        print('\n'.join(completions))

class BaseCompleter(metaclass=abc.ABCMeta):

    @abc.abstractproperty
    def target_list(self):
        raise NotImplementedError

    def complete_target(self, uncompleted_arg):
        """Return an iterator over completions."""
        if ' ' in uncompleted_arg:
            return;

        uncompleted_path = PurePosixPath(uncompleted_arg)
        if not uncompleted_path.is_absolute():
            uncompleted_path = PurePosixPath('/', uncompleted_path)

        if uncompleted_path.name == '':
            uncompleted_parent = PurePosixPath('/')
            uncompleted_name = ''
        elif uncompleted_arg.endswith('/'):
            uncompleted_parent = uncompleted_path
            uncompleted_name = ''
            if uncompleted_parent in self.target_list:
                yield str(uncompleted_parent) + '/'
        else:
            uncompleted_parent = uncompleted_path.parent
            uncompleted_name = uncompleted_path.name

        for path in self.target_list:
            if uncompleted_parent != path.parent:
                continue;
            name = path.name
            assert path.suffix == ''
            if not name.startswith(uncompleted_name):
                continue;
            yield str(uncompleted_parent/name) + '/'

    def readline_completer(self, text, state):
        try:
            if getattr(self, '_saved_text', None) != text:
                self._saved_completion = list(self.complete_target(text))
                self._saved_text = text
            if state < len(self._saved_completion):
                return self._saved_completion[state]
            else:
                return None
        except:
            import sys, traceback
            traceback.print_exception(*sys.exc_info())

class Completer(BaseCompleter):

    def __init__(self, driver):
        self.driver = driver
        super().__init__()

    @property
    def target_list(self):
        return ( PurePosixPath(metapath)
            for metapath in self.driver.list_metapaths() )

class CachingCompleter(BaseCompleter):

    def __init__(self, local):
        self.local = local
        super().__init__()

    @property
    def target_list(self):
        try:
            return getattr(self, '_target_list')
        except AttributeError:
            pass

        target_list = self._load_target_list_cache()
        if target_list is None:
            from jeolm.metadata import MetadataManager
            driver_class = self.local.driver_class
            md = MetadataManager(local=self.local)
            md.load_metadata_cache()
            driver = md.feed_metadata(driver_class())
            target_list = [ PurePosixPath(metapath)
                for metapath in driver.list_metapaths() ]
            if not target_list:
                logger.warning("Target list is empty.")
            self._dump_target_list_cache(target_list)
        self._target_list = target_list
        return target_list

    def _load_target_list_cache(self):
        try:
            with self._target_list_cache_path.open('r') as cache_file:
                cache = cache_file.read()
        except FileNotFoundError:
            return None
        else:
            return [
                PurePosixPath(line)
                for line in cache.split('\n')
                if line != '' ]

    def _dump_target_list_cache(self, target_list):
        cache = '\n'.join(str(target) for target in target_list)
        if not cache or not target_list:
            logger.warning("Completion cache seems empty")
        new_path = self.local.build_dir / '.targets.cache.list.new'
        with new_path.open('w') as cache_file:
            cache_file.write(cache)
        new_path.rename(self._target_list_cache_path)

    def invalidate_target_list_cache(self):
        if self._target_list_cache_path.exists():
            self._target_list_cache_path.unlink()

    @property
    def _target_list_cache_path(self):
        return self.local.build_dir / self._target_list_cache_name

    _target_list_cache_name = 'targets.cache.list'

if __name__ == '__main__':
    main()

