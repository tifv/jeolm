from pathlib import Path

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.NullHandler())

def get_parser():
    from argparse import ArgumentParser
    parser = ArgumentParser(description='Automated build system')
    parser.add_argument(
        '-R', '--root', help='explicit root path of a jeolm project')
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='explicit root path of a jeolm project')
    command = parser.add_mutually_exclusive_group()
    command.add_argument(
        '-r', '--review',
        nargs='*',
        help='review infiles' )
    command.add_argument(
        '-c', '--clean',
        action='count',
        help=
            'clean toplevel links to build/**.pdf; '
            'clean *.yaml and *.tex in build/; '
            'clean all in build/' )
    command.add_argument(
        '-a', '--archive',
        action='store_true',
        help='create project archive, including some intermediate files' )
    command.add_argument(
        '-i', '--interactive',
        action='store_true',
        help='get targets in the interactive prompt and build them' )
    command.add_argument(
        'targets',
        nargs='*', default=[],
        help='build specified targets' )
    return parser

def main():
    from jeolm import filesystem, builder, inrecords, commands

    args = get_parser().parse_args()
    setup_logging(args.verbose)
    if args.root is None:
        root = filesystem.find_root()
    else:
        root = Path(args.root).resolve()
        if not filesystem.check_root(root):
            root = None
    if root is None:
        logger.critical(
            '<BOLD><RED>Missing directory and file layout '
            'required for jeolm.<RESET>' )
        logger.warning('<BOLD>Required layout: {}<RESET>'
            .format(filesystem.repr_required()) )
        raise SystemExit
#    setup_file_logging(root)
#    logger.debug('Log file enabled')

    filesystem.load_localmodule(root)

    if args.review is not None:
        inrecords.review(args.review, viewpoint=Path.cwd(), root=root)
        return
    if args.clean:
        if args.clean == 1:
            commands.cleanview(root=root)
        elif args.clean >= 2:
            commands.unbuild(root=root)
        return
    if args.archive:
        commands.archive(root=root)
        return
    if args.interactive or not args.targets:
        commands.shell(root=root)
        return

    builder.build(args.targets, root=root)

def setup_logging(verbose):
    import sys
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO if not verbose else logging.DEBUG)
    handler.setFormatter(FancyFormatter("%(name)s: %(message)s",
        fancy=sys.stdout.isatty() ))
    logger.addHandler(handler)

def setup_file_logging(root):
    handler = logging.FileHandler(str(root['jeolm.log']))
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(FancyFormatter("%(name)s: %(message)s", fancy=False))
    logger.addHandler(handler)

class FancyFormatter(logging.Formatter):
    fancy_replacements = {
        '<RESET>' : '\033[0m', '<BOLD>' : '\033[1m',

        '<BLACK>' : '\033[30m', '<RED>'     : '\033[31m',
        '<GREEN>' : '\033[32m', '<YELLOW>'  : '\033[33m',
        '<BLUE>'  : '\033[34m', '<MAGENTA>' : '\033[35m',
        '<CYAN>'  : '\033[36m', '<WHITE>'   : '\033[37m',
    }

    def __init__(self, *args, fancy=False, **kwargs):
        self.fancy = fancy
        return super().__init__(*args, **kwargs)

    def format(self, record):
        return self.fancify(super().format(record))

    def fancify(self, s):
        for k, v in self.fancy_replacements.items():
            s = s.replace(k, v if self.fancy else '')
        return s

