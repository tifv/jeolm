# Imports and logging {{{1

from itertools import chain
from pathlib import PosixPath

import re

from . import ( Node, FilelikeNode, ProductFileNode,
    SubprocessCommand )
from .cyclic import AutowrittenNeed, CyclicPathNode
from .directory import DirectoryNode, BuildDirectoryNode

import logging
logger = logging.getLogger(__name__)

from typing import ( TypeVar, ClassVar, Type, Optional,
    Iterable, Iterator,
    Tuple, Generator, )
T = TypeVar('T')

class LaTeXCommand(SubprocessCommand): # {{{1

    latex_command = 'latex'
    target_suffix = '.dvi'

    latex_mode_args = ('-interaction=nonstopmode', '-halt-on-error')

    node: 'LaTeXNode'
    output_dir: PosixPath
    jobname: str
    source_name: str
    latex_log_path: PosixPath
    latex_log: Optional['LaTeXLog']

    def __init__( self, node: 'LaTeXNode',
        *, source_name: str,
        latex_predefs: Optional[str] = None,
        output_dir: PosixPath, jobname: str, cwd: PosixPath,
    ) -> None:
        assert isinstance(node, LaTeXNode), type(node)
        self.output_dir = output_dir
        self.jobname = jobname
        self.source_name = source_name
        callargs = ( self.latex_command,
            f'-output-directory={output_dir.relative_to(cwd)}',
            f'-jobname={jobname}',
            *self.latex_mode_args,
            self._init_latex_main_arg( source_name,
                latex_predefs=latex_predefs ),
        )
        super().__init__(node, callargs, cwd=cwd)
        self.latex_log_path = (output_dir/jobname).with_suffix('.log')
        self.latex_log = None

    @classmethod
    def _init_latex_main_arg( cls, source_name: str,
        *, latex_predefs: Optional[str] = None
    ) -> str:
        if latex_predefs is None:
            return source_name
        if not isinstance(latex_predefs, str):
            raise TypeError(type(latex_predefs))
        if not latex_predefs.startswith('\\'):
            raise ValueError(latex_predefs)
        return latex_predefs + r'\input{' + source_name + r'}'

    # Override
    async def _subprocess(self) -> None:
        latex_output = await self._subprocess_output()
        self.latex_log = LaTeXLog(
            latex_output, self.latex_log_path, node=self.node )

class PdfLaTeXCommand(LaTeXCommand):
    latex_command = 'pdflatex'
    target_suffix = '.pdf'

class XeLaTeXCommand(LaTeXCommand):
    latex_command = 'xelatex'
    target_suffix = '.pdf'

class LuaLaTeXCommand(LaTeXCommand):
    latex_command = 'lualatex'
    target_suffix = '.pdf'


class LaTeXNode(ProductFileNode, CyclicPathNode): # {{{1
    """
    Represents a target of some latex command.

    Aims at reasonable handling of latex output to stdin/log.
    Completely suppresses latex output unless finds something
    interesting in it.
    """

    _Command: ClassVar[Type[LaTeXCommand]] = LaTeXCommand
    max_cycles: ClassVar[int] = 7

    command: LaTeXCommand

    def __init__( self, source: FilelikeNode,
        *, latex_predefs: Optional[str] = None, jobname: str,
        build_dir_node: DirectoryNode, output_dir_node: DirectoryNode,
        figure_nodes: Iterable[Node] = (),
        name: Optional[str] = None, needs: Iterable[Node] = (),
    ) -> None:
        build_dir = build_dir_node.path
        if source.path.parent != build_dir:
            raise ValueError
        output_dir = output_dir_node.path
        if not (build_dir == output_dir or build_dir in output_dir.parents):
            raise ValueError
        if '.' in jobname:
            raise ValueError
        path = (output_dir / jobname).with_suffix(
            self._Command.target_suffix )
        if name is None:
            name = self._default_name()

        self.aux_node = AutowrittenNeed(
            path=(output_dir/jobname).with_suffix('.aux'),
            name='{}:aux'.format(name),
            needs=(output_dir_node,) )
        self.toc_node = AutowrittenNeed(
            path=(output_dir/jobname).with_suffix('.toc'),
            name='{}:toc'.format(name),
            needs=(output_dir_node,) )

        super().__init__( source=source, path=path,
            name=name,
            needs=( *needs, *figure_nodes,
                output_dir_node, self.aux_node, self.toc_node ),
        )
        if isinstance(build_dir_node, BuildDirectoryNode):
            self.append_needs(build_dir_node.pre_cleanup_node)

        self.command = self._Command( self,
            source_name=source.path.name,
            latex_predefs=latex_predefs,
            output_dir=output_dir, jobname=jobname,
            cwd=build_dir )
        assert self.path.suffix == self.command.target_suffix

    def _update_cyclic_continue(self) -> None:
        super()._update_cyclic_continue()
        self.logger.info(
            "LaTeX requires rerunning" + '…' * self.cycle )

    def _update_cyclic_halt(self) -> None:
        if self.command.latex_log is None:
            raise RuntimeError
        self.command.latex_log.print_latex_log(everything=True)
        self.logger.warning(
            "LaTeX requires rerunning too many times in a row." )

    def _update_cyclic_finish(self) -> None:
        if self.command.latex_log is None:
            raise RuntimeError
        self.command.latex_log.print_latex_log()

class PdfLaTeXNode(LaTeXNode):
    _Command = PdfLaTeXCommand

class XeLaTeXNode(LaTeXNode):
    _Command = XeLaTeXCommand

class LuaLaTeXNode(LaTeXNode):
    _Command = LuaLaTeXCommand


class LaTeXPDFNode(ProductFileNode): # {{{1

    _LaTeXNode = LaTeXNode

    def __init__( self, source: FilelikeNode,
        *, latex_predefs: Optional[str] = None, jobname: str,
        build_dir_node: DirectoryNode, output_dir_node: DirectoryNode,
        figure_nodes: Iterable[Node] = (),
        name: Optional[str] = None, needs: Iterable[Node] = (),
    ) -> None:
        build_dir = build_dir_node.path
        if source.path.parent != build_dir:
            raise RuntimeError
        if name is None:
            name = self._default_name()
        dvi_node = self._LaTeXNode( source,
            latex_predefs=latex_predefs, jobname=jobname,
            build_dir_node=build_dir_node, output_dir_node=output_dir_node,
            name='{}:dvi'.format(name),
            figure_nodes=figure_nodes, needs=needs )
        del source # is not self.source
        if output_dir_node.path != dvi_node.path.parent:
            raise RuntimeError
        if dvi_node.path.suffix != '.dvi':
            raise RuntimeError
        super().__init__( source=dvi_node,
            path=dvi_node.path.with_suffix('.pdf'),
            name=name,
            needs=(*figure_nodes, output_dir_node) )
        self.command = SubprocessCommand( self,
            ( 'dvipdf',
                str(self.source.path.relative_to(build_dir)),
                str(self.path.relative_to(build_dir)) ),
            cwd=build_dir )

class LaTeXLog: # {{{1

    latex_output: str
    latex_log_path: Optional[PosixPath]
    node: LaTeXNode

    def __init__( self, latex_output: str, latex_log_path: PosixPath = None,
        *, node: LaTeXNode,
    ) -> None:
        self.latex_output = latex_output
        self.latex_log_path = latex_log_path
        self.node = node

    @property
    def logger(self) -> Node.LoggerAdapter:
        return self.node.logger

    def print_latex_log(self, *, everything: bool = False) -> None:
        """
        Print some of LaTeX output from its stdout and log.

        Print output if it is interesting.
        Otherwise, print overfulls from latex log
        (if latex_log_path is not None).
        """
        if everything or self._latex_output_is_alarming():
            self.logger.log_prog_output( logging.WARNING,
                self.node.command.latex_command, self.latex_output )
        elif self.latex_log_path is not None:
            with self.latex_log_path.open(errors='replace', encoding='utf-8') \
                    as latex_log_file:
                latex_log_text = latex_log_file.read()
            self._print_warnings_from_latex_log(latex_log_text)

    def _latex_output_is_alarming(self) -> bool:
        match = self._latex_output_alarming_regex.search(self.latex_output)
        return match is not None

    _latex_output_alarming_regex = re.compile(
        r'[Ee]rror|'
            # loading warning.sty package should not trigger alarm
            r'(?!warning/warning.sty)(?!(?<=warning/)warning.sty)'
        r'[Ww]arning|'
        r'[Rr]erun to|'
        r'No pages of output' )

    def _print_warnings_from_latex_log(self, latex_log_text: str) -> None:
        page_numberer = self._find_page_numbers_in_latex_log(latex_log_text)
        next(page_numberer) # initialize coroutine
        file_namer = self._find_file_names_in_latex_log(latex_log_text)
        next(file_namer) # initialize coroutine

        matches = list(
            self._latex_log_warning_regex.finditer(latex_log_text) )
        if not matches:
            return
        report = ["Problems encountered by LaTeX:<RESET>"]
        for match in matches:
            position = match.start()
            page_number = page_numberer.send(position)
            file_name = file_namer.send(position)
            report.append(
                "<CYAN>[{page_number}]<NOCOLOUR>"
                ' '
                "<MAGENTA>({file_name})<NOCOLOUR>"
                .format(page_number=page_number, file_name=file_name) )
            if match.group('overfull') is not None:
                # 10pt is delibirate
                is_large = float(match.group('overfull_points') or 0) > 10
                message = match.expand(self._latex_log_overfull_template)
                if is_large:
                    message = "<BOLD>" + message + "<REGULAR>"
            elif match.group('misschar') is not None:
                message = match.expand(self._latex_log_misschar_template)
                message = "<BOLD>" + message + "<REGULAR>"
            else:
                raise RuntimeError
            report.append(message)
        self.logger.info('\n'.join(report))

    _latex_log_overfull_pattern = ( # r'(?m)'
        r'^(?P<overfull_type>Overfull|Underfull) '
        r'(?P<overfull_box_type>\\hbox|\\vbox) '
        r'(?P<overfull_badness>'
            r'\((?:(?P<overfull_points>\d+(?:\.\d+)?)pt too wide|badness \d+)\)'
        r'|)'
        r'(?P<overfull_rest>.*)$'
    )
    _latex_log_overfull_template = (
        r'\g<overfull_type> '
        r'\g<overfull_box_type> '
        r'<YELLOW>\g<overfull_badness><NOCOLOUR>'
        r'\g<overfull_rest>' )

    _latex_log_misschar_pattern = ( # r'(?m)'
        r'^Missing character: (?P<misschar_msg>.*)$'
    )
    _latex_log_misschar_template = (
        r'Missing character: \g<misschar_msg>'
    )

    _latex_log_warning_regex = re.compile( r'(?m)'
        r'(?P<overfull>' + _latex_log_overfull_pattern + ')|'
        r'(?P<misschar>' + _latex_log_misschar_pattern + ')'
    )

    # Locate page numbers and file names {{{2

    @staticmethod
    def _inverse_monotonic(
        monotonic: Iterator[Tuple[int, Optional[T]]],
        min_position: int, max_position: int,
    ) -> Generator[Optional[T], int, None]:
        """
        Coroutine.

        Initial next() call is required.

        Args:
            monotonic (iterable of pairs):
                iterable producing a finite sequence of pairs (p_i, v_i), where
                p_i is nondecreasing.

        Send:
            integer p, min_position <= p <= max_position.
        Yield:
            v_i, such that p_i = max(p_i, p_i <= p).
        """

        def get_next_position() -> Tuple[int, Optional[T]]:
            try:
                return next(monotonic)
            except StopIteration:
                return (max_position + 1, None)

        prev_position, prev_value = min_position, None
        next_position, next_value = get_next_position()
        while True:
            position = (yield prev_value)
            if position is None or not isinstance(position, int):
                raise RuntimeError("Expected to receive position.")
            if position < min_position or position > max_position:
                raise RuntimeError("Sent position is out of range.")
            if position < prev_position:
                raise RuntimeError("Sent position is not monotonic.")
            while position >= next_position:
                prev_position, prev_value = next_position, next_value
                next_position, next_value = get_next_position()

    @classmethod
    def _find_page_numbers_in_latex_log( cls, latex_log_text: str
    ) -> Generator[Optional[int], int, None]:
        finder: Iterator[Tuple[int, int]] = (
            (match.end(), int(match.group('page_number')) + 1)
            for match
            in cls._latex_log_page_number_regex.finditer(latex_log_text)
        )
        return cls._inverse_monotonic(
            chain( ((0,1),), finder), 0, len(latex_log_text) )

    _latex_log_page_number_regex = re.compile(
        r'\[(?P<page_number>\d+)\s*\]' )

    @classmethod
    def _find_file_names_in_latex_log( cls, latex_log_text: str
    ) -> Generator[Optional[str], int, None]:
        finder: Iterator[Tuple[int, str]] = (
            (match.end(), match.group('file_name'))
            for match
            in cls._latex_log_file_name_regex.finditer(latex_log_text)
        )
        return cls._inverse_monotonic(finder, 0, len(latex_log_text))

    _latex_log_file_name_regex = re.compile(
        r'(?<=\(\./)' # "(./"
        r'(?P<file_name>.+?)' # "<file name>"
        r'(?=[\s)])' # ")" or "\n" or " "
    )

    # }}}2

# }}}1
# vim: set foldmethod=marker :
