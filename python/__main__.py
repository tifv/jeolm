from argparse import ArgumentParser

from pathlib import Path

import jeolm
from jeolm.target import Target
from jeolm.diffprint import log_metadata_diff
from jeolm.commands import (
    review, print_source_list, check_spelling, clean,
    list_sources, simple_load_driver, refrain_called_process_error, )

import logging
logger = logging.getLogger(__name__)



def main():
    from jeolm import filesystem, nodes
    from jeolm import setup_logging

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
    from jeolm.metadata import MetadataManager

    if not args.targets:
        logger.warn('No-op: no targets for building')
    md = MetadataManager(fs=fs)
    md.load_metadata()
    Driver = fs.find_driver_class()
    driver = md.feed_metadata(Driver())

    if args.review:
        sources = list_sources( args.targets,
            fs=fs, driver=driver, source_type='tex' )
        with log_metadata_diff(md):
            review( sources, viewpoint=Path.cwd(),
                fs=fs, md=md, recursive=False )
        md.dump_metadata()
        driver = md.feed_metadata(Driver())

    builder = Builder(args.targets, fs=fs, driver=driver,
        force=args.force, delegate=args.delegate )
    with refrain_called_process_error():
        builder.build()

def main_review(args, *, fs):
    from jeolm.metadata import MetadataManager
    if not args.inpaths:
        logger.warn('No-op: no inpaths for review')
    md = MetadataManager(fs=fs)
    md.load_metadata()
    with log_metadata_diff(md):
        review(args.inpaths, viewpoint=Path.cwd(),
                fs=fs, md=md, recursive=args.recursive )
    md.dump_metadata()

def main_list(args, *, fs):
    if not args.targets:
        logger.warn('No-op: no targets for source list')
    print_source_list(args.targets,
        fs=fs, driver=simple_load_driver(fs),
        viewpoint=Path.cwd(), source_type=args.source_type, )

#def main_expose(args, *, fs):
#    from jeolm.builder import Builder
#    if not args.targets:
#        logger.warn('No-op: no targets for exposing source')
#    builder = Builder(args.targets, fs=fs, force=None)
#    for node in builder.autosource_nodes.values():
#        node.update()
#        print(node.path)

def main_spell(args, *, fs):
    if not args.targets:
        logger.warn('No-op: no targets for spell check')
    check_spelling(args.targets, fs=fs, driver=simple_load_driver(fs))

def main_clean(args, *, fs):
    clean(root=fs.root)
    fs.clean_broken_links(fs.build_dir, recursive=True)



parser = ArgumentParser(prog='jeolm',
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
    nargs='*', metavar='TARGET', type=Target.from_string)
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
build_parser.set_defaults(command='build', force=None)

list_parser = subparsers.add_parser('list',
    help='list all infiles for given targets' )
list_parser.add_argument('targets',
    nargs='*', metavar='TARGET', type=Target.from_string, )
list_parser.add_argument('--type',
    help='searched-for infiles type',
    choices=['tex', 'asy'], default='tex',
    dest='source_type', metavar='SOURCE_TYPE', )
list_parser.set_defaults(command='list')

#expose_parser = subparsers.add_parser('expose',
#    help='list generated main.tex files for given targets' )
#expose_parser.add_argument('targets',
#    nargs='*', metavar='TARGET', type=Target.from_string, )
#expose_parser.set_defaults(command='expose')

spell_parser = subparsers.add_parser('spell',
    help='spell-check all infiles for given targets' )
spell_parser.add_argument('targets',
    nargs='*', metavar='TARGET', type=Target.from_string, )
spell_parser.set_defaults(command='spell')

review_parser = subparsers.add_parser('review',
    help='review given infiles' )
review_parser.add_argument('inpaths',
    nargs='*', metavar='INPATH', )
review_parser.add_argument('-r', '--recursive',
    action='store_true', )
review_parser.set_defaults(command='review')

clean_parser = subparsers.add_parser('clean',
    help='clean toplevel links to build/**.pdf', )
clean_parser.set_defaults(command='clean')



if __name__ == '__main__':
    main()

