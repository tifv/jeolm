import argparse

from pathlib import Path

import jeolm
import jeolm.local
import jeolm.nodes
import jeolm.target
import jeolm.diffprint
import jeolm.commands

import logging
logger = logging.getLogger(__name__)

parser = argparse.ArgumentParser(prog='jeolm',
    description='Automated build system for course-like projects' )
parser.add_argument('-R', '--root',
    help='explicit root path of a jeolm project', )
parser.add_argument('-v', '--verbose',
    help='make debug messages to stdout',
    action='store_true', )
parser.add_argument('-C', '--no-colour',
    help='disable colour output',
    action='store_false', dest='colour', )

subparsers = parser.add_subparsers()

def main():
    args = parser.parse_args()
    if 'command' not in args:
        return parser.print_help()
    jeolm.setup_logging(verbose=args.verbose, colour=args.colour)
    if args.command == 'init':
        # special case: no local expected
        return main_init(args)
    try:
        local = jeolm.local.LocalManager(root=args.root)
    except jeolm.local.RootNotFoundError:
        jeolm.local.report_missing_root()
        raise SystemExit
    jeolm.nodes.PathNode.root = local.root
    main_function = globals()['main_' + args.command]
    return main_function(args, local=local)

build_parser = subparsers.add_parser('build',
    help='build specified targets', )
build_parser.add_argument('targets',
    nargs='*', metavar='TARGET', type=jeolm.target.Target.from_string)
force_build_group = build_parser.add_mutually_exclusive_group()
force_build_group.add_argument('-f', '--force-latex',
    help='force recompilation on LaTeX stage',
    action='store_const', dest='force', const='latex')
force_build_group.add_argument('-F', '--force-generate',
    help='force overwriting of generated LaTeX file',
    action='store_const', dest='force', const='generate')
build_parser.add_argument('-D', '--no-delegate',
    help='ignore the possibility of delegating targets',
    action='store_false', dest='delegate' )
build_parser.add_argument('-r', '--review',
    help='review included infiles prior to build',
    action='store_true', )
build_parser.add_argument('--dump',
    help='instead of building create standalone version of document',
    action='store_true', )
build_parser.add_argument('-j', '--jobs',
    help='number of parallel jobs',
    type=int, default=1, )
build_parser.set_defaults(command='build', force=None)

def main_build(args, *, local):
    from jeolm.builder import Builder
    if args.dump:
        from jeolm.builder import Dumper as Builder
    from jeolm.metadata import MetadataManager

    if not args.targets:
        logger.warn('No-op: no targets for building')
    md = MetadataManager(local=local)
    md.load_metadata_cache()
    driver = md.feed_metadata(local.driver_class())

    if args.review:
        sources = jeolm.commands.list_sources( args.targets,
            local=local, driver=driver, source_type='tex' )
        with jeolm.diffprint.log_metadata_diff(md):
            jeolm.commands.review( sources,
                viewpoint=Path.cwd(), local=local,
                md=md, recursive=False )
        md.dump_metadata_cache()
        driver.clear()
        md.feed_metadata(driver)

    if args.jobs < 1:
        raise argparse.ArgumentTypeError(
            "Positive integral number of jobs is required." )
    elif args.jobs > 1:
        from concurrent import futures
        executor = futures.ThreadPoolExecutor(max_workers=args.jobs)
    else:
        executor = None

    builder = Builder(args.targets, local=local, driver=driver,
        force=args.force, delegate=args.delegate,
        executor=executor )
    with jeolm.commands.refrain_called_process_error():
        builder.build()

review_parser = subparsers.add_parser('review',
    help='review given infiles' )
review_parser.add_argument('inpaths',
    nargs='*', metavar='INPATH', )
review_parser.add_argument('-r', '--recursive',
    action='store_true', )
review_parser.set_defaults(command='review')

def main_review(args, *, local):
    from jeolm.metadata import MetadataManager
    if not args.inpaths:
        logger.warn('No-op: no inpaths for review')
    md = MetadataManager(local=local)
    md.load_metadata_cache()
    with jeolm.diffprint.log_metadata_diff(md):
        jeolm.commands.review( args.inpaths,
            viewpoint=Path.cwd(), local=local,
            md=md, recursive=args.recursive )
    md.dump_metadata_cache()

init_parser = subparsers.add_parser('init',
    help='create jeolm directory/file structure' )
init_parser.add_argument('resources',
    nargs='*', metavar='RESOURCE', )
init_parser.set_defaults(command='init')

def main_init(args):
    jeolm.local.InitLocalManager(
        root=args.root, resources=args.resources )

list_parser = subparsers.add_parser('list',
    help='list all infiles for given targets' )
list_parser.add_argument('targets',
    nargs='*', metavar='TARGET', type=jeolm.target.Target.from_string, )
list_parser.add_argument('--type',
    help='searched-for infiles type',
    choices=['tex', 'asy'], default='tex',
    dest='source_type', metavar='SOURCE_TYPE', )
list_parser.set_defaults(command='list')

def main_list(args, *, local):
    if not args.targets:
        logger.warn('No-op: no targets for source list')
    jeolm.commands.print_source_list( args.targets,
        viewpoint=Path.cwd(), local=local,
        driver=jeolm.commands.simple_load_driver(local),
        source_type=args.source_type, )

spell_parser = subparsers.add_parser('spell',
    help='spell-check all infiles for given targets' )
spell_parser.add_argument('targets',
    nargs='*', metavar='TARGET', type=jeolm.target.Target.from_string, )
spell_parser.set_defaults(command='spell')

def main_spell(args, *, local):
    if not args.targets:
        logger.warn('No-op: no targets for spell check')
    jeolm.commands.check_spelling( args.targets,
        local=local, driver=jeolm.commands.simple_load_driver(local),
        colour=args.colour )

clean_parser = subparsers.add_parser('clean',
    help='clean toplevel links to build/**.pdf', )
clean_parser.set_defaults(command='clean')

def main_clean(args, *, local):
    jeolm.commands.clean(root=local.root)
    jeolm.commands.clean_broken_links(local.build_dir, recursive=True)


if __name__ == '__main__':
    main()

