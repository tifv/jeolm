from argparse import ArgumentParser

from pathlib import Path, PurePosixPath

import jeolm
from jeolm.target import Target
from jeolm.diffprint import log_metadata_diff
from jeolm.commands import (
    review, print_source_list, check_spelling, clean,
    list_sources, simple_load_driver, refrain_called_process_error, )

import logging
logger = logging.getLogger(__name__)


parser = ArgumentParser(prog='jeolm',
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
    from jeolm import filesystem, nodes
    from jeolm import setup_logging

    args = parser.parse_args()
    if 'command' not in args:
        return parser.print_help()
    setup_logging(verbose=args.verbose, colour=args.colour)
    if args.command == 'init':
        # special case: no fs expected
        return main_init(args)
    try:
        fs = filesystem.FilesystemManager(root=args.root)
    except filesystem.RootNotFoundError:
        raise SystemExit
    nodes.PathNode.root = fs.root
    fs.report_broken_links()
    fs.load_local_module()
    main_function = globals()['main_' + args.command]
    return main_function(args, fs=fs)

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
build_parser.add_argument('-j', '--jobs',
    help='number of parallel jobs',
    type=int, default=1, )
build_parser.set_defaults(command='build', force=None)

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

    if args.jobs < 1:
        raise argparse.ArgumentTypeError(
            "Positive integral number of jobs is required." )
    elif args.jobs > 1:
        from concurrent import futures
        executor = futures.ThreadPoolExecutor(max_workers=args.jobs)
    else:
        executor = None

    builder = Builder(args.targets, fs=fs, driver=driver,
        force=args.force, delegate=args.delegate,
        executor=executor )
    with refrain_called_process_error():
        builder.build()

review_parser = subparsers.add_parser('review',
    help='review given infiles' )
review_parser.add_argument('inpaths',
    nargs='*', metavar='INPATH', )
review_parser.add_argument('-r', '--recursive',
    action='store_true', )
review_parser.set_defaults(command='review')

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

init_parser = subparsers.add_parser('init',
    help='create jeolm directory/file structure' )
init_parser.add_argument('resources',
    nargs='*', metavar='RESOURCE', )
init_parser.set_defaults(command='init')

def main_init(args):
    from shutil import copyfile
    from jeolm import filesystem
    fs = filesystem.InitFilesystemManager(root=args.root)
    fs.fix_root()
    for resource_name in args.resources:
        resource_dir = fs.locate_resource(resource_name)
        assert isinstance(resource_dir, Path), type(resource_dir)
        assert resource_dir.is_dir(), resource_dir
        for p in sorted(resource_dir.glob('**/*')):
            assert not p.is_symlink(), p
            r = p.relative_to(resource_dir)
            q = fs.root/r
            if p.is_dir():
                if q.exists():
                    if not q.is_dir():
                        raise NotADirectoryError(q)
                    else:
                        continue
                else:
                    q.mkdir()
            else:
                logger.info("Updating {}".format(r))
                copyfile(str(p), str(q))

list_parser = subparsers.add_parser('list',
    help='list all infiles for given targets' )
list_parser.add_argument('targets',
    nargs='*', metavar='TARGET', type=Target.from_string, )
list_parser.add_argument('--type',
    help='searched-for infiles type',
    choices=['tex', 'asy'], default='tex',
    dest='source_type', metavar='SOURCE_TYPE', )
list_parser.set_defaults(command='list')

def main_list(args, *, fs):
    if not args.targets:
        logger.warn('No-op: no targets for source list')
    print_source_list( args.targets,
        fs=fs, driver=simple_load_driver(fs),
        viewpoint=Path.cwd(), source_type=args.source_type, )

spell_parser = subparsers.add_parser('spell',
    help='spell-check all infiles for given targets' )
spell_parser.add_argument('targets',
    nargs='*', metavar='TARGET', type=Target.from_string, )
spell_parser.set_defaults(command='spell')

def main_spell(args, *, fs):
    if not args.targets:
        logger.warn('No-op: no targets for spell check')
    if not args.colour:
        logger.warn('Spelling is nearly useless in colourless mode.')
    check_spelling( args.targets,
        fs=fs, driver=simple_load_driver(fs),
        colour=args.colour )

clean_parser = subparsers.add_parser('clean',
    help='clean toplevel links to build/**.pdf', )
clean_parser.set_defaults(command='clean')

def main_clean(args, *, fs):
    clean(root=fs.root)
    fs.clean_broken_links(fs.build_dir, recursive=True)


if __name__ == '__main__':
    main()

