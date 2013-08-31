from pathlib import Path

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.NullHandler())

def get_parser(prog='jeolm'):
    from argparse import ArgumentParser
    parser = ArgumentParser(prog=prog,
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
        help='clean toplevel links to build/**.pdf; clean **.dvi in build/',
        action='count', )
    command.add_argument('-a', '--archive',
        help='create project archive, including some intermediate files',
        action='store_true', )
    command.add_argument('targets',
        help='build specified targets',
        nargs='*', default=[], )
    return parser

def main():
    from jeolm import filesystem, builder, inrecords, commands

    args = get_parser().parse_args()

    setup_logging(args.verbose)
    try:
        fsmanager = filesystem.FSManager(
            root=Path(args.root) if args.root is not None else None )
    except filesystem.RootNotFoundError:
        raise SystemExit
    fsmanager.report_broken_links()

    fsmanager.load_local_module()

    if args.review is not None:
        return inrecords.review(args.review, viewpoint=Path.cwd(),
            fsmanager=fsmanager )
    if args.list_tex is not None:
        return inrecords.print_inpaths(args.list_tex, suffix='.tex',
            viewpoint=Path.cwd(), fsmanager=fsmanager );
    if args.list_asy is not None:
        return inrecords.print_inpaths(args.list_asy, suffix='.asy',
            viewpoint=Path.cwd(), fsmanager=fsmanager );
    if args.clean is not None:
        assert args.clean >= 1
        if args.clean == 1:
            return commands.cleanview(root=fsmanager.root);
        if args.clean > 1:
            return commands.unbuild(root=fsmanager.root);
    if args.archive:
        return commands.archive(fsmanager=fsmanager);

    builder = builder.Builder(args.targets, fsmanager=fsmanager)
    builder.update()

def setup_logging(verbose):
    import sys
    if sys.stderr.isatty():
        from jeolm.fancify import FancyFormatter as Formatter
    else:
        from jeolm.fancify import NotSoFancyFormatter as Formatter
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO if not verbose else logging.DEBUG)
    handler.setFormatter(Formatter("%(name)s: %(message)s"))
    logger.addHandler(handler)

