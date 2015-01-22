from itertools import chain

import re

from jeolm.node import ProductFileNode, SubprocessCommand

import logging
logger = logging.getLogger(__name__) # pylint: disable=invalid-name

__all__ = ['LaTeXNode']

class _LaTeXCommand(SubprocessCommand):

    latex_command = 'latex'
    target_suffix = '.dvi'

    _latex_additional_args = ('-interaction=nonstopmode', '-halt-on-error')

    # No more than 5 LaTeX runs in a row.
    _max_latex_reruns = 4

    def __init__(self, node, source_name, jobname, *, cwd):
        callargs = tuple(chain(
            (self.latex_command,),
            ('-jobname={}'.format(jobname),),
            self._latex_additional_args,
            (source_name,),
        ))
        super().__init__(node, callargs, cwd=cwd)

    # Override
    def _subprocess(self, *, reruns=0):
        latex_output = self._subprocess_output()

        if self._latex_output_requests_rerun(latex_output):
            if reruns < self._max_latex_reruns:
                self.log( logging.WARNING,
                    "LaTeX requests rerun" + '…' * (reruns+1) )
                return self._subprocess(reruns=reruns+1)
            else:
                self._log_output(latex_output, level=logging.WARNING)
                self.log( logging.WARNING,
                    "LaTeX requests rerun too many times in a row." )
        else:
            self._print_latex_log(
                latex_output,
                latex_log_path=self.node.path.with_suffix('.log') )

    @classmethod
    def _latex_output_requests_rerun(cls, latex_output):
        match = cls._latex_output_rerun_pattern.search(latex_output)
        return match is not None

    _latex_output_rerun_pattern = re.compile(
        r'[Rr]erun to (?#get something right)' )

    def _print_latex_log(self, latex_output, latex_log_path=None):
        """
        Print some of LaTeX output from its stdout and log.

        Print output if it is interesting.
        Otherwise, print overfulls from latex log
        (if latex_log_path is not None).
        """
        if self._latex_output_is_alarming(latex_output):
            self._log_output(latex_output, level=logging.WARNING)
        elif latex_log_path is not None:
            with latex_log_path.open(errors='replace') as latex_log_file:
                latex_log_text = latex_log_file.read()
            self._print_overfulls_from_latex_log(latex_log_text)

    @classmethod
    def _latex_output_is_alarming(cls, latex_output):
        match = cls._latex_output_alarming_pattern.search(latex_output)
        return match is not None

    _latex_output_alarming_pattern = re.compile(
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
            self._latex_log_overfull_pattern.finditer(latex_log_text) )
        if not matches:
            return
        header = "<BOLD>Overfulls and underfulls detected by LaTeX:<RESET>"
        self.node.log( logging.WARNING, '\n'.join(chain(
            (header,),
            ( self._format_overfull(match, page_numberer, file_namer)
                for match in matches )
        )))

    _latex_log_overfull_pattern = re.compile(
        r'(?m)^'
        r'(?P<overfull_type>Overfull|Underfull) '
        r'\\(?P<box_type>hbox|vbox) '
        r'(?P<badness>\((?:\d+(?:\.\d+)?pt too wide|badness \d+)\) |)'
        r'(?P<rest>.*)$'
    )
    _latex_overfull_log_template = (
        r'\g<overfull_type> '
        r'\\\g<box_type> '
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

    @classmethod
    def _find_page_numbers_in_latex_log(cls, latex_log_text):
        """
        Coroutine, yields page number for sent text position.

        As with any generator, initial next() call required.
        After that, sending position in latex_log_text will yield corresponding
        page number.
        """

        page_mark_positions = [0]
        last_page_number = 0
        matches = cls._latex_log_page_number_pattern.finditer(
            latex_log_text )
        for match in matches:
            page_number = int(match.group('page_number'))
            if page_number != last_page_number + 1:
                # Something got slightly wrong. Close your eyes
                continue
            page_mark_positions.append(match.end())
            assert len(page_mark_positions) == page_number + 1
            last_page_number = page_number
        page_mark_positions.append(len(latex_log_text))
        assert len(page_mark_positions) > 1

        last_page_number = 0
        last_position = page_mark_positions[last_page_number]
        assert last_position == 0
        next_position = page_mark_positions[last_page_number + 1]
        page_number = None # "answer" variable
        while True:
            position = (yield page_number)
            if position is None:
                page_number = None
                continue
            if __debug__ and position < last_position:
                raise RuntimeError("Sent position is not monotonic.")
            if __debug__ and position >= len(latex_log_text):
                raise RuntimeError("Sent position is out of range.")
            while position >= next_position:
                last_position = next_position
                last_page_number += 1
                next_position = page_mark_positions[last_page_number + 1]
            page_number = last_page_number + 1

    _latex_log_page_number_pattern = re.compile(
        r'\[(?P<page_number>\d+)\s*\]' )

    @classmethod
    def _find_file_names_in_latex_log(cls, latex_log_text):
        """
        Coroutine, yields input file name for sent text position.

        As with any generator, initial next() call required.
        After that, sending position in latex_log_text will yield corresponding
        input file name.

        Only local filenames are detected, e.g. starting with "./",
        and yielded without a prefixing "./".
        """

        file_name_positions = [0]
        file_names = [None]
        matches = cls._latex_log_file_name_pattern.finditer(
            latex_log_text )
        for match in matches:
            file_name_positions.append(match.end())
            file_names.append(match.group('file_name'))
        file_name_positions.append(len(latex_log_text))
        assert len(file_name_positions) == len(file_names) + 1

        last_index = 0
        last_position = file_name_positions[last_index]
        assert last_position == 0
        next_position = file_name_positions[last_index + 1]
        file_name = None # "answer" variable
        while True:
            position = (yield file_name)
            if position is None:
                file_name = None
                continue
            if __debug__ and position < last_position:
                raise RuntimeError("Sent position is not monotonic.")
            if __debug__ and position >= len(latex_log_text):
                raise RuntimeError("Sent position is out of range.")
            while position >= next_position:
                last_position = next_position
                last_index += 1
                next_position = file_name_positions[last_index + 1]
            file_name = file_names[last_index]

    _latex_log_file_name_pattern = re.compile(
        r'(?<=\(\./)' # "(./"
        r'(?P<file_name>.+?)' # "<file name>"
        r'(?=[\s)])' # ")" or "\n" or " "
    )

class LaTeXNode(ProductFileNode):
    """
    Represents a target of some latex command.

    Aims at reasonable handling of latex output to stdin/log.
    Completely suppresses latex output unless finds something
    interesting in it.
    """

    _Command = _LaTeXCommand

    def __init__(self, source, path, *, name=None, needs=(), **kwargs):
        super().__init__( source=source, path=path,
            name=name, needs=needs, **kwargs )
        assert path.is_absolute(), path

        cwd = path.parent
        if cwd != source.path.parent:
            raise RuntimeError
        jobname = path.stem

        command = self._Command(self, source.path.name, jobname, cwd=cwd)
        if path.suffix != command.target_suffix:
            raise RuntimeError

        self.set_command(command)

