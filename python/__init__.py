from pathlib import Path

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.NullHandler())
difflogger = logging.getLogger(__name__ + '.diff')
difflogger.setLevel(logging.INFO)
difflogger.addHandler(logging.NullHandler())

def get_parser(prog='jeolm'):
    from argparse import ArgumentParser
    parser = ArgumentParser(prog=prog,
        description='Automated build system for course-like projects' )
    parser.add_argument('-R', '--root',
        help='explicit root path of a jeolm project', )
    parser.add_argument('-v', '--verbose',
        help='make debug messages to stdout',
        action='store_true', )
    subparsers = parser.add_subparsers()

    build_parser = subparsers.add_parser('build',
        help='build specified targets', )
    build_parser.add_argument('targets',
        nargs='*', metavar='TARGET', )
    force_build_group = build_parser.add_mutually_exclusive_group()
    force_build_group.add_argument('-f', '--force-latex',
        help='force recompilation on LaTeX stage',
        action='store_true', )
    force_build_group.add_argument('-F', '--force-generate',
        help='force overwriting of generated LaTeX file',
        action='store_true', )
#    build_parser.add_argument('--dump',
#        help='instead of building create standalone version of document',
#        action='store_true', )
    build_parser.set_defaults(main_func=main_build)

    list_parser = subparsers.add_parser('list',
        help='list all infiles for given targets' )
    list_parser.add_argument('targets',
        nargs='*', metavar='TARGET', )
    list_parser.add_argument('--type',
        help='searched-for infiles type',
        choices=['tex', 'asy'], default='tex',
        dest='source_type', metavar='SOURCE_TYPE', )
    list_parser.set_defaults(main_func=main_list)

    expose_parser = subparsers.add_parser('expose',
        help='list generated main.tex files for given targets' )
    expose_parser.add_argument('targets',
        nargs='*', metavar='TARGET', )
    expose_parser.set_defaults(main_func=main_expose)

    spell_parser = subparsers.add_parser('spell',
        help='spell-check all infiles for given targets' )
    spell_parser.add_argument('targets',
        nargs='*', metavar='TARGET', )
    spell_parser.set_defaults(main_func=main_spell)

    review_parser = subparsers.add_parser('review', aliases=['r'],
        help='review given infiles' )
    review_parser.add_argument('inpaths',
        nargs='*', metavar='INPATH', )
    review_parser.add_argument('-r', '--recursive',
        action='store_true', )
    review_parser.set_defaults(main_func=main_review)

    clean_parser = subparsers.add_parser('clean',
        help='clean toplevel links to build/**.pdf', )
    clean_parser.set_defaults(main_func=main_clean)

    return parser

def main():
    from jeolm import filesystem, nodes

    parser = get_parser()
    args = parser.parse_args()

    setup_logging(args.verbose)
    try:
        fsmanager = filesystem.FSManager(
            root=Path(args.root) if args.root is not None else None )
    except filesystem.RootNotFoundError:
        raise SystemExit
    nodes.PathNode.root = fsmanager.root
    fsmanager.report_broken_links()

    fsmanager.load_local_module()

    if 'main_func' not in vars(args):
        return parser.print_help()
    return args.main_func(args, fsmanager=fsmanager)

def main_build(args, *, fsmanager):
    from jeolm.builder import Builder
#    if args.dump:
#        from jeolm.builder import Dumper as Builder
    if not args.targets:
        logger.warn('No-op: no targets for building')
    if args.force_latex:
        force = 'latex'
    elif args.force_generate:
        force = 'generate'
    else:
        force = None
    builder = Builder(args.targets, fsmanager=fsmanager, force=force)
    builder.update()

def main_review(args, *, fsmanager):
    from jeolm.commands import review
    if not args.inpaths:
        logger.warn('No-op: no inpaths for review')
    review(args.inpaths, viewpoint=Path.cwd(),
            fsmanager=fsmanager, recursive=args.recursive )

def main_list(args, *, fsmanager):
    from jeolm.commands import print_source_list
    if not args.targets:
        logger.warn('No-op: no targets for source list')
    print_source_list(args.targets,
        fsmanager=fsmanager, viewpoint=Path.cwd(),
        source_type=args.source_type, )

def main_expose(args, *, fsmanager):
    from jeolm.builder import Builder
    if not args.targets:
        logger.warn('No-op: no targets for exposing source')
    builder = Builder(args.targets, fsmanager=fsmanager, force=None)
    for node in builder.autosource_nodes.values():
        node.update()
        print(node.path)

def main_spell(args, *, fsmanager):
    from jeolm.commands import check_spelling
    if not args.targets:
        logger.warn('No-op: no targets for spell check')
    check_spelling(args.targets, fsmanager=fsmanager,)

def main_clean(args, *, fsmanager):
    from jeolm.commands import clean
    clean(root=fsmanager.root)
    fsmanager.clean_broken_links(fsmanager.build_dir, recursive=True)

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
    diffhandler = logging.StreamHandler()
    diffhandler.setLevel(logging.INFO)
    diffhandler.setFormatter(Formatter("%(message)s"))
    difflogger.propagate = False
    difflogger.addHandler(diffhandler)

