from pathlib import Path

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.NullHandler())

def get_parser():
    from argparse import ArgumentParser
    parser = ArgumentParser(
        description='Automated build system for course-like projects' )
    parser.add_argument('-R', '--root',
        help='explicit root path of a jeolm project', )
    parser.add_argument('-v', '--verbose',
        help='make debug messages to stdout',
        action='store_true', )
    command = parser.add_mutually_exclusive_group()
    command.add_argument('-r', '--review',
        help='review given inrecords (defaults to all inrecords)',
        nargs='*', metavar='INROOT', )
    command.add_argument('--list-tex',
        help='list all TeX infiles in given inrecords '
            '(defaults to all infiles); file paths are relative to cwd',
        nargs='*', metavar='INROOT', )
    command.add_argument('--list-asy',
        help='list all Asymptote infiles in given inrecords '
            '(defaults to all infiles); file paths are relative to cwd',
        nargs='*', metavar='INROOT', )
    command.add_argument('-c', '--clean',
        help='clean toplevel links to build/**.pdf; clean **.tex in build/',
        action='count', )
    command.add_argument('-a', '--archive',
        help='create project archive, including some intermediate files',
        action='store_true', )
    command.add_argument('targets',
        help='build specified targets',
        nargs='*', default=[], )
    return parser

def main():
    args = get_parser().parse_args()

    from jeolm import filesystem, builder, inrecords, commands

    setup_logging(args.verbose)
    root = filesystem.find_root(
        proposal=None if args.root is None else Path(args.root) )
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
        return inrecords.review(args.review, viewpoint=Path.cwd(), root=root);
    if args.list_tex is not None:
        return inrecords.print_inpaths(args.list_tex, '.tex',
            viewpoint=Path.cwd(), root=root );
    if args.list_asy is not None:
        return inrecords.print_inpaths(args.list_asy, '.asy',
            viewpoint=Path.cwd(), root=root );
    if args.clean is not None:
        assert args.clean >= 1
        if args.clean == 1:
            return commands.cleanview(root=root);
        if args.clean > 1:
            return commands.unbuild(root=root);
    if args.archive:
        return commands.archive(root=root);

    return builder.build(args.targets, root=root);

def setup_logging(verbose):
    import sys
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO if not verbose else logging.DEBUG)
    handler.setFormatter(FancyFormatter("%(name)s: %(message)s",
        fancy=sys.stderr.isatty() ))
    logger.addHandler(handler)

def setup_file_logging(root):
    handler = logging.FileHandler(str(root/'jeolm.log'))
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(FancyFormatter("%(name)s: %(message)s", fancy=False))
    logger.addHandler(handler)

class FancyFormatter(logging.Formatter):
    fancy_replacements = {
        '<RESET>' : '\033[0m', '<BOLD>' : '\033[1m',
        '<NOCOLOUR>' : '\033[39m',

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

