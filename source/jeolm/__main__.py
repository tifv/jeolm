import argparse
from contextlib import suppress

from pathlib import Path

import jeolm
import jeolm.local
import jeolm.target
import jeolm.commands

import logging
from jeolm import logger # use 'jeolm' logger instead of '__main__' one.


def _get_base_arg_parser( prog='jeolm',
    description='Automated build system for course-like projects'
):
    parser = argparse.ArgumentParser(prog=prog, description=description)
    parser.add_argument( '-R', '--root',
        help='explicit root path of a jeolm project' )
    parser.add_argument( '-v', '--verbose',
        help='include debug messages in log output',
        action='store_true' )
    parser.add_argument( '-C', '--no-colour',
        help='disable colour output',
        action='store_false', dest='colour' )
    return parser

def main(args):
    concurrent = args.command in {'build', 'buildline'} and args.jobs > 1
    logging_manager = jeolm.LoggingManager(
        verbose=args.verbose, colour=args.colour, concurrent=concurrent)
    with logging_manager:
        if args.command is None:
            logger.fatal("No command selected.")
            raise SystemExit(1)
        if args.command == 'init':
            # special case: no local expected
            return main_init(args, logging_manager=logging_manager)
        try:
            local = jeolm.local.LocalManager(root=args.root)
        except jeolm.local.RootNotFoundError:
            jeolm.local.report_missing_root()
            raise SystemExit(1)
        return args.command_func(
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
    parser.set_defaults(command_func=main_build, force=None)

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
            from jeolm.node.latex import LaTeXNode
            for node in target_node.iter_needs():
                if isinstance(node, LaTeXNode):
                    node.force()
        elif args.force == 'generate':
            from jeolm.node.latex import LaTeXNode
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
    parser.set_defaults(command_func=main_buildline, force=None)

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
    parser.set_defaults(command_func=main_review)

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
    # command_func default is intentionally not set

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
    parser.set_defaults(command_func=main_list)

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
    parser.set_defaults(command_func=main_spell)

def main_spell(args, *, local, logging_manager):
    if not args.targets:
        logger.warn('No-op: no targets for spell check')
    jeolm.commands.check_spelling( args.targets,
        local=local,
        driver=jeolm.commands.simple_load_driver(local),
        colour=args.colour )


def _add_makefile_arg_subparser(subparsers):
    parser = subparsers.add_parser( 'makefile',
        help='generate makefile for given targets' )
    parser.add_argument( 'targets',
        nargs='*', metavar='TARGET', type=jeolm.target.Target.from_string)
    parser.add_argument( '-o', '--output-makefile',
        help='where to write makefile; default is Makefile; '
            'generated makefile must be executed from the root directory '
            'of the jeolm project',
        default='Makefile' )
    parser.add_argument( '-O', '--output-unbuildable',
        help=( 'where to write list of files which Makefile cannot rebuild '
            '(and depends on); default is stdout' ) )
    parser.set_defaults(command_func=main_makefile)

def main_makefile(args, *, local, logging_manager):
    from jeolm.makefile import MakefileGenerator
    from jeolm.node import PathNode, NodeErrorReported
    from jeolm.node_factory import TargetNodeFactory

    if not args.targets:
        logger.warn('No-op: no targets for makefile generation')
    PathNode.root = local.root
    driver = jeolm.commands.simple_load_driver(local)

    with local.open_text_node_shelf() as text_node_shelf:
        target_node_factory = TargetNodeFactory(
            local=local, driver=driver, text_node_shelf=text_node_shelf)
        makefile_string, unbuildable_nodes, unrepresentable_nodes = \
            MakefileGenerator.generate(
                target_node_factory(args.targets, name='first'),
                viewpoint=local.root )
        with suppress(NodeErrorReported):
            for node in unbuildable_nodes:
                node.update()
    for node in unrepresentable_nodes:
        node.log( logging.WARNING,
            "Node has no possible representation in Makefile" )
    with open(args.output_makefile, 'w') as makefile:
        makefile.write(makefile_string)
    if args.output_unbuildable is None:
        _print_unbuildable_list(unbuildable_nodes, local=local)
    else:
        with open(args.output_unbuildable, 'w') as unbuildable_list_file:
            _print_unbuildable_list( unbuildable_nodes, local=local,
                file=unbuildable_list_file )

def _print_unbuildable_list(unbuildable_nodes, *, local, **kwargs):
    for node in unbuildable_nodes:
        print(str(node.path.relative_to(local.root)), **kwargs)


def _add_clean_arg_subparser(subparsers):
    parser = subparsers.add_parser( 'clean',
        help='clean toplevel links to build/**.pdf' )
    parser.set_defaults(command_func=main_clean)

def main_clean(args, *, local, logging_manager):
    jeolm.commands.clean(root=local.root)
    jeolm.commands.clean_broken_links(local.build_dir, recursive=True)


def _get_arg_parser():
    parser = _get_base_arg_parser()
    subparsers = parser.add_subparsers(title='commands', dest='command')
    _add_build_arg_subparser(subparsers)
    _add_buildline_arg_subparser(subparsers)
    _add_review_arg_subparser(subparsers)
    _add_init_arg_subparser(subparsers)
    _add_list_arg_subparser(subparsers)
    _add_spell_arg_subparser(subparsers)
    _add_makefile_arg_subparser(subparsers)
    _add_clean_arg_subparser(subparsers)
    return parser

def _get_args():
    parser = _get_arg_parser()
    args = parser.parse_args()
    return args

if __name__ == '__main__':
    main(args=_get_args())

