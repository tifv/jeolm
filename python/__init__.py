from pathlib import Path

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.NullHandler())
cleanlogger = logging.getLogger(__name__ + '.clean')
cleanlogger.setLevel(logging.INFO)
cleanlogger.addHandler(logging.NullHandler())

def main():
    from jeolm.argparser import parser
    from jeolm import filesystem, nodes

    args = parser.parse_args()

    setup_logging(args.verbose)
    try:
        fs = filesystem.FilesystemManager(
            root=Path(args.root) if args.root is not None else None )
    except filesystem.RootNotFoundError:
        raise SystemExit
    nodes.PathNode.root = fs.root
    fs.report_broken_links()

    if 'command' not in args:
        return parser.print_help()

    fs.load_local_module()

    main_function = globals()['main_' + args.command]
    return main_function(args, fs=fs)

def main_build(args, *, fs):

    from jeolm.builder import Builder
    if args.dump:
        from jeolm.builder import Dumper as Builder
    if not args.targets:
        logger.warn('No-op: no targets for building')

    if args.review:
        from jeolm.commands import list_sources, review
        review(
            list_sources( args.targets,
                fsmanager=fs, source_type='tex' ),
            viewpoint=Path.cwd(),
            fsmanager=fs, recursive=False )

    builder = Builder(args.targets, fsmanager=fs,
        force=args.force, delegate=args.delegate )
    builder.update()

def main_review(args, *, fs):
    from jeolm.commands import review
    if not args.inpaths:
        logger.warn('No-op: no inpaths for review')
    review(args.inpaths, viewpoint=Path.cwd(),
            fsmanager=fs, recursive=args.recursive )

def main_list(args, *, fs):
    from jeolm.commands import print_source_list
    if not args.targets:
        logger.warn('No-op: no targets for source list')
    print_source_list(args.targets,
        fsmanager=fs, viewpoint=Path.cwd(),
        source_type=args.source_type, )

def main_expose(args, *, fs):
    from jeolm.builder import Builder
    if not args.targets:
        logger.warn('No-op: no targets for exposing source')
    builder = Builder(args.targets, fsmanager=fs, force=None)
    for node in builder.autosource_nodes.values():
        node.update()
        print(node.path)

def main_spell(args, *, fs):
    from jeolm.commands import check_spelling
    if not args.targets:
        logger.warn('No-op: no targets for spell check')
    check_spelling(args.targets, fsmanager=fs,)

def main_clean(args, *, fs):
    from jeolm.commands import clean
    clean(root=fs.root)
    fs.clean_broken_links(fs.build_dir, recursive=True)

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
    cleanhandler = logging.StreamHandler()
    cleanhandler.setLevel(logging.INFO)
    cleanhandler.setFormatter(Formatter("%(message)s"))
    cleanlogger.propagate = False
    cleanlogger.addHandler(cleanhandler)

