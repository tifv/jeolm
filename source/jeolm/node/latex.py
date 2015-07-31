from itertools import chain

import re

from . import ProductFileNode, SubprocessCommand
from .directory import BuildDirectoryNode

import logging
logger = logging.getLogger(__name__)


class LaTeXCommand(SubprocessCommand):

    latex_command = 'latex'
    target_suffix = '.dvi'

    _latex_mode_args = ('-interaction=nonstopmode', '-halt-on-error')

    # No more than 5 LaTeX runs in a row.
    _max_latex_reruns = 4

    def __init__(self, node, *, source_name, output_dir, jobname, cwd):
        assert isinstance(node, LaTeXNode), type(node)
        output_dir_arg = output_dir.relative_to(cwd)
        callargs = tuple(chain(
            ( self.latex_command,
                '-output-directory={}'.format(output_dir_arg),
                '-jobname={}'.format(jobname), ),
            self._latex_mode_args,
            (source_name,),
        ))
        super().__init__(node, callargs, cwd=cwd)
        self._latex_log_path = (output_dir/jobname).with_suffix('.log')

    # Override
    def _subprocess(self, *, reruns=0):
        latex_output = self._subprocess_output()

        if self._latex_output_requests_rerun(latex_output):
            if reruns < self._max_latex_reruns:
                self.logger.info(
                    "LaTeX requests rerun" + '…' * (reruns+1) )
                return self._subprocess(reruns=reruns+1)
            else:
                self._log_output(logging.WARNING, latex_output)
                self.logger.warning(
                    "LaTeX requests rerun too many times in a row." )
        else:
            self._print_latex_log( latex_output,
                latex_log_path=self._latex_log_path )

    @classmethod
    def _latex_output_requests_rerun(cls, latex_output):
        match = cls._latex_output_rerun_regex.search(latex_output)
        return match is not None

    _latex_output_rerun_regex = re.compile(
        r'[Rr]erun to (?#get something right)' )

    def _print_latex_log(self, latex_output, latex_log_path=None):
        """
        Print some of LaTeX output from its stdout and log.

        Print output if it is interesting.
        Otherwise, print overfulls from latex log
        (if latex_log_path is not None).
        """
        if self._latex_output_is_alarming(latex_output):
            self._log_output(logging.WARNING, latex_output)
        elif latex_log_path is not None:
            with latex_log_path.open(errors='replace') as latex_log_file:
                latex_log_text = latex_log_file.read()
            self._print_overfulls_from_latex_log(latex_log_text)

    @classmethod
    def _latex_output_is_alarming(cls, latex_output):
        match = cls._latex_output_alarming_regex.search(latex_output)
        return match is not None

    _latex_output_alarming_regex = re.compile(
        r'[Ee]rror|'
            # loading warning.sty package should not trigger alarm
            r'(?!warning/warning.sty)(?!(?<=warning/)warning.sty)'
        r'[Ww]arning|'
        r'No pages of output' )

    def _print_overfulls_from_latex_log(self, latex_log_text):
        page_numberer = self._find_page_numbers_in_latex_log(latex_log_text)
        next(page_numberer) # initialize coroutine
        file_namer = self._find_file_names_in_latex_log(latex_log_text)
        next(file_namer) # initialize coroutine

        matches = list(
            self._latex_log_overfull_regex.finditer(latex_log_text) )
        if not matches:
            return
        header = "Overfulls and underfulls detected by LaTeX:<RESET>"
        self.logger.info('\n'.join(chain(
            (header,),
            ( self._format_overfull(match, page_numberer, file_namer)
                for match in matches )
        )))

    _latex_log_overfull_regex = re.compile(
        r'(?m)^'
        r'(?P<overfull_type>Overfull|Underfull) '
        r'(?P<box_type>\\hbox|\\vbox) '
        r'(?P<badness>\((?:\d+(?:\.\d+)?pt too wide|badness \d+)\) |)'
        r'(?P<rest>.*)$'
    )
    _latex_overfull_log_template = (
        r'\g<overfull_type> '
        r'\g<box_type> '
        r'<YELLOW>\g<badness><NOCOLOUR>'
        r'\g<rest>' )

    @classmethod
    def _format_overfull(cls, match, page_numberer, file_namer):
        position = match.start()
        page_number = page_numberer.send(position)
        file_name = file_namer.send(position)
        message = match.expand(cls._latex_overfull_log_template)
        return (
            "<CYAN>[{page_number}]<NOCOLOUR>"
            ' '
            "<MAGENTA>({file_name})<NOCOLOUR>"
            '\n'
            "{message}"
        ).format(
            page_number=page_number, file_name=file_name,
            message=message
        )

    @staticmethod
    def _inverse_monotonic(monotonic, min_position, max_position):
        """
        Coroutine.

        Initial next() call is required.

        Args:
            monotonic (iterable of pairs):
                iterable producing a finite sequence of pairs (p_i, v_i), where
                p_i is nondecreasing.

        Send:
            integer p, min_position <= p <= max_position.
        Return:
            v_i, such that p_i = max(p_i, p_i <= p).
        """

        monotonic = chain( monotonic, ((max_position+1, None),) )

        prev_position, prev_value = min_position, None
        next_position, next_value = next(monotonic)
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
                next_position, next_value = next(monotonic)

    @classmethod
    def _find_page_numbers_in_latex_log(cls, latex_log_text):
        finder = (
            (match.end(), int(match.group('page_number')) + 1)
            for match
            in cls._latex_log_page_number_regex.finditer(latex_log_text)
        )
        return cls._inverse_monotonic(
            chain( ((0,1),), finder), 0, len(latex_log_text) )

    _latex_log_page_number_regex = re.compile(
        r'\[(?P<page_number>\d+)\s*\]' )

    @classmethod
    def _find_file_names_in_latex_log(cls, latex_log_text):
        finder = (
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

class PdfLaTeXCommand(LaTeXCommand):
    latex_command = 'pdflatex'
    target_suffix = '.pdf'

class XeLaTeXCommand(LaTeXCommand):
    latex_command = 'xelatex'
    target_suffix = '.pdf'

class LuaLaTeXCommand(LaTeXCommand):
    latex_command = 'lualatex'
    target_suffix = '.pdf'


class LaTeXNode(ProductFileNode):
    """
    Represents a target of some latex command.

    Aims at reasonable handling of latex output to stdin/log.
    Completely suppresses latex output unless finds something
    interesting in it.
    """

    _Command = LaTeXCommand

    def __init__( self, source, jobname,
        build_dir_node, output_dir_node,
        *, name=None, figure_nodes=(), needs=(), **kwargs
    ):
        build_dir = build_dir_node.path
        if source.path.parent != build_dir:
            raise RuntimeError
        output_dir = output_dir_node.path
        if not (build_dir == output_dir or build_dir in output_dir.parents):
            raise RuntimeError
        if '.' in jobname:
            raise RuntimeError
        path = (output_dir / jobname).with_suffix(
            self._Command.target_suffix )

        super().__init__( source=source, path=path,
            name=name, needs=chain(needs, figure_nodes, (output_dir_node,)),
            **kwargs )
        if isinstance(build_dir_node, BuildDirectoryNode):
            self.append_needs(build_dir_node.pre_cleanup_node)

        command = self._Command( self,
            source_name=source.path.name,
            output_dir=output_dir, jobname=jobname,
            cwd=build_dir )
        if self.path.suffix != command.target_suffix:
            raise RuntimeError
        self.set_command(command)

class PdfLaTeXNode(LaTeXNode):
    _Command = PdfLaTeXCommand

class XeLaTeXNode(LaTeXNode):
    _Command = XeLaTeXCommand

class LuaLaTeXNode(LaTeXNode):
    _Command = LuaLaTeXCommand


class LaTeXPDFNode(ProductFileNode):

    _LaTeXNode = LaTeXNode

    def __init__( self, source, jobname,
        build_dir_node, output_dir_node,
        *, name=None, figure_nodes=(), needs=(), **kwargs
    ):
        build_dir = build_dir_node.path
        if source.path.parent != build_dir:
            raise RuntimeError
        dvi_node = self._LaTeXNode( source, jobname,
            build_dir_node, output_dir_node,
            name='{}:dvi'.format(name),
            figure_nodes=figure_nodes, needs=needs, **kwargs )
        del source # is not self.source
        if output_dir_node.path != dvi_node.path.parent:
            raise RuntimeError
        if dvi_node.path.suffix != '.dvi':
            raise RuntimeError
        super().__init__( source=dvi_node,
            path=dvi_node.path.with_suffix('.pdf'),
            name=name,
            needs=chain(figure_nodes, (output_dir_node,)),
            **kwargs )
        self.set_subprocess_command(
            ( 'dvipdf',
                str(self.source.path.relative_to(build_dir)),
                str(self.path.relative_to(build_dir)) ),
            cwd=build_dir )

