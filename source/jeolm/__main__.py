import argparse
from contextlib import suppress

from pathlib import Path

import jeolm
import jeolm.local
import jeolm.target
import jeolm.commands

from jeolm import logger


def _get_base_arg_parser( prog='jeolm',
    description='Automated build system for course-like projects'
):
    parser = argparse.ArgumentParser(prog=prog, description=description)
    parser.add_argument( '-R', '--root',
        help='explicit root path of a jeolm project' )
    parser.add_argument( '-v', '--verbose',
        help='make debug messages to stdout',
        action='store_true' )
    parser.add_argument( '-C', '--no-colour',
        help='disable colour output',
        action='store_false', dest='colour' )
    return parser

def main(args):
    assert 'command' in args, args
    concurrent = args.command in {'build', 'buildline'} and args.jobs > 1
    logging_manager = jeolm.LoggingManager(
        verbose=args.verbose, colour=args.colour, concurrent=concurrent)
    with logging_manager:
        if args.command == 'init':
            # special case: no local expected
            return main_init(args, logging_manager=logging_manager)
        try:
            local = jeolm.local.LocalManager(root=args.root)
        except jeolm.local.RootNotFoundError:
            jeolm.local.report_missing_root()
            raise SystemExit
        main_function = globals()['main_' + args.command]
        return main_function(
            args, local=local, logging_manager=logging_manager )


def _add_build_arg_subparser(subparsers):
    parser = subparsers.add_parser( 'build',
        help='build specified targets' )
    parser.add_argument( 'targets',
        nargs='*', metavar='TARGET', type=jeolm.target.Target.from_string)
    force_build_group = parser.add_mutually_exclusive_group()
    force_build_group.add_argument( '-f', '--force-latex',
        help='force recompilation on LaTeX stage',
        action='store_const', dest='force', const='latex' )
    force_build_group.add_argument( '-F', '--force-generate',
        help='force overwriting of generated LaTeX file',
        action='store_const', dest='force', const='generate' )
    parser.add_argument( '-D', '--no-delegate',
        help='ignore the possibility of delegating targets',
        action='store_false', dest='delegate' )
    parser.add_argument( '-j', '--jobs',
        help='number of parallel jobs',
        type=int, default=1 )
    parser.set_defaults(command='build', force=None)

def main_build(args, *, local, logging_manager):
    from jeolm.node import PathNode, NodeErrorReported
    from jeolm.node_factory import TargetNodeFactory

    if not args.targets:
        logger.warn('No-op: no targets for building')
    PathNode.root = local.root
    if args.jobs < 1:
        raise argparse.ArgumentTypeError(
            "Positive integral number of jobs is required." )
    semaphore = _get_build_semaphore(args.jobs)
    driver = jeolm.commands.simple_load_driver(local)

    with local.open_text_node_shelf() as text_node_shelf:
        target_node_factory = TargetNodeFactory(
            local=local, driver=driver, text_node_shelf=text_node_shelf)
        target_node = target_node_factory(args.targets, delegate=args.delegate)
        if args.force is None:
            pass
        elif args.force == 'latex':
            from jeolm.latex_node import LaTeXNode
            for node in target_node.iter_needs():
                if isinstance(node, LaTeXNode):
                    node.force()
        elif args.force == 'generate':
            from jeolm.latex_node import LaTeXNode
            from jeolm.node import FileNode
            for node in target_node.iter_needs():
                if (isinstance(node, LaTeXNode) and
                    isinstance(node.source, FileNode)
                ):
                    node.source.force()
        else:
            raise RuntimeError(args.force)
        with suppress(NodeErrorReported):
            target_node.update(semaphore=semaphore)

def _get_build_semaphore(jobs):
    assert isinstance(jobs, int), type(jobs)
    if jobs > 1:
        import threading
        return threading.BoundedSemaphore(value=jobs)
    else:
        return None


def _add_buildline_arg_subparser(subparsers):
    parser = subparsers.add_parser( 'buildline',
        help='start an interactive build shell' )
    parser.add_argument( '-j', '--jobs',
        help='number of parallel jobs',
        type=int, default=1 )
    parser.set_defaults(command='buildline', force=None)

def main_buildline(args, *, local, logging_manager):
    from jeolm.node import PathNode
    from jeolm.buildline import BuildLine

    PathNode.root = local.root
    if args.jobs < 1:
        raise argparse.ArgumentTypeError(
            "Positive integral number of jobs is required." )
    semaphore = _get_build_semaphore(args.jobs)

    with local.open_text_node_shelf() as text_node_shelf:
        buildline = BuildLine(
            local=local, text_node_shelf=text_node_shelf,
            semaphore=semaphore, logging_manager=logging_manager )
        with buildline.readline_setup():
            return buildline.main()


def _add_review_arg_subparser(subparsers):
    parser = subparsers.add_parser( 'review',
        help='review given infiles' )
    parser.add_argument( 'inpaths',
        nargs='*', metavar='INPATH' )
    parser.set_defaults(command='review')

def main_review(args, *, local, logging_manager):
    from jeolm.diffprint import log_metadata_diff
    if not args.inpaths:
        logger.warn('No-op: no inpaths for review')
    metadata = (local.metadata_class)(local=local)
    metadata.load_metadata_cache()
    with log_metadata_diff(metadata, logger=logger):
        jeolm.commands.review( args.inpaths,
            viewpoint=Path.cwd(), local=local, metadata=metadata )
    metadata.dump_metadata_cache()


def _add_init_arg_subparser(subparsers):
    parser = subparsers.add_parser( 'init',
        help='create jeolm directory/file structure' )
    parser.add_argument( 'resources',
        nargs='*', metavar='RESOURCE' )
    parser.set_defaults(command='init')

def main_init(args, logging_manager):
    jeolm.local.InitLocalManager(
        root=args.root, resources=args.resources )


def _add_list_arg_subparser(subparsers):
    parser = subparsers.add_parser( 'list',
        help='list all infiles for given targets' )
    parser.add_argument( 'targets',
        nargs='*', metavar='TARGET', type=jeolm.target.Target.from_string )
    parser.add_argument( '--type',
        help='searched-for infiles type',
        choices=['tex', 'asy'], default='tex',
        dest='source_type', metavar='SOURCE_TYPE' )
    parser.set_defaults(command='list')

def main_list(args, *, local, logging_manager):
    if not args.targets:
        logger.warn('No-op: no targets for source list')
    jeolm.commands.print_source_list( args.targets,
        viewpoint=Path.cwd(), local=local,
        driver=jeolm.commands.simple_load_driver(local),
        source_type=args.source_type )


def _add_spell_arg_subparser(subparsers):
    parser = subparsers.add_parser( 'spell',
        help='spell-check all infiles for given targets' )
    parser.add_argument( 'targets',
        nargs='*', metavar='TARGET', type=jeolm.target.Target.from_string )
    parser.set_defaults(command='spell')

def main_spell(args, *, local, logging_manager):
    if not args.targets:
        logger.warn('No-op: no targets for spell check')
    jeolm.commands.check_spelling( args.targets,
        local=local,
        driver=jeolm.commands.simple_load_driver(local),
        colour=args.colour )


def _add_clean_arg_subparser(subparsers):
    parser = subparsers.add_parser( 'clean',
        help='clean toplevel links to build/**.pdf' )
    parser.set_defaults(command='clean')

def main_clean(args, *, local, logging_manager):
    jeolm.commands.clean(root=local.root)
    jeolm.commands.clean_broken_links(local.build_dir, recursive=True)


def _get_arg_parser():
    parser = _get_base_arg_parser()
    subparsers = parser.add_subparsers()
    _add_build_arg_subparser(subparsers)
    _add_buildline_arg_subparser(subparsers)
    _add_review_arg_subparser(subparsers)
    _add_init_arg_subparser(subparsers)
    _add_list_arg_subparser(subparsers)
    _add_spell_arg_subparser(subparsers)
    _add_clean_arg_subparser(subparsers)
    return parser

def _get_args():
    parser = _get_arg_parser()
    args = parser.parse_args()
    if 'command' not in args:
        return parser.print_help()
    return args

if __name__ == '__main__':
    main(args=_get_args())

