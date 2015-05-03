import re
from collections import OrderedDict

import enchant

from jeolm.commands.list_sources import list_sources

import logging
logger = logging.getLogger(__name__)


def check_spelling(targets, *, local, driver, context=0, colour=True):
    if colour:
        from jeolm.fancify import fancifying_print as fprint
    else:
        logger.warn('Spelling is nearly useless in colourless mode.')
        from jeolm.fancify import unfancifying_print as fprint

    indicator_length = 0
    def indicator_clean():
        nonlocal indicator_length
        if indicator_length:
            print(' ' * indicator_length, end='\r')
        indicator_length = 0
    def indicator_show(name):
        nonlocal indicator_length
        print(name, end='\r')
        indicator_length = len(str(name))
    def piece_to_string(piece):
        if isinstance(piece, CorrectWord):
            return '<GREEN>{}<NOCOLOUR>'.format(piece.string)
        elif isinstance(piece, IncorrectWord):
            return '<RED>{}<NOCOLOUR>'.format(piece.string)
        else:
            return piece.string

    path_generator = list_sources(targets,
        local=local, driver=driver, source_type='tex' )
    for path in path_generator:
        indicator_clean()
        indicator_show(str(path))

        with path.open('r') as checked_file:
            text = checked_file.read()
        lines = ['']
        printed_line_numbers = set()
        try:
            for piece in LaTeXSpeller(text, lang='ru_RU'):
                if isinstance(piece, IncorrectWord):
                    lineno = len(lines) - 1
                    printed_line_numbers.update(
                        range(lineno-context, lineno+context+1) )
                piece_sl = piece_to_string(piece).split('\n')
                lines[-1] += piece_sl[0]
                for subpiece in piece_sl[1:]:
                    lines.append(subpiece)
        except ValueError as error:
            raise ValueError(
                "Error while spell-checking {}"
                .format(path.relative_to(local.source_dir))
            ) from error
        if not printed_line_numbers:
            continue
        indicator_clean()
        fprint(
            '<BOLD><YELLOW>{}<NOCOLOUR> possible misspellings<RESET>'
            .format(path.relative_to(local.source_dir)) )
        line_range = range(len(lines))
        lineno_offset = len(str(len(lines)))
        for lineno in sorted(printed_line_numbers):
            if lineno not in line_range:
                continue
            fprint(
                '<MAGENTA>{lineno: >{lineno_offset}}<NOCOLOUR>:{line}'
                .format( lineno=lineno+1, lineno_offset=lineno_offset,
                    line=lines[lineno] )
            )
    indicator_clean()


class TextPiece:
    __slots__ = ['string']

    def __init__(self, string):
        if isinstance(string, str):
            self.string = string
        else:
            raise RuntimeError(type(string))

class Word(TextPiece):
    __slots__ = []

class DottedAbbr(Word):
    __slots__ = []

class CorrectWord(Word):
    __slots__ = []

class IncorrectWord(Word):
    __slots__ = []


class LaTeXSpeller:
    def __init__(self, text, lang):
        self.lang = lang
        self.text = self.prepare_text(text, lang=lang)

    known_langs = frozenset(('en_US', 'ru_RU'))
    dotted_abbrs = {
        'en_US' : frozenset(('e.~g.', 'i.~e.')),
        'ru_RU' : frozenset(('т.~д.', 'т.~е.')),
    }

    def __iter__(self):
        dictionary = enchant.Dict(self.lang)

        for text_piece in LaTeXSlicer(self.text):
            assert isinstance(text_piece, TextPiece), type(text_piece)
            if not isinstance(text_piece, Word):
                yield text_piece
            elif isinstance(text_piece, DottedAbbr):
                if text_piece.string in self.dotted_abbrs[self.lang]:
                    yield CorrectWord(text_piece.string)
                else:
                    yield IncorrectWord(text_piece.string)
                continue
            else:
                if dictionary.check(text_piece.string):
                    yield CorrectWord(text_piece.string)
                else:
                    yield IncorrectWord(text_piece.string)

    spell_pattern = re.compile('(?m)'
        r'% spell (?P<words>.*)$')

    @classmethod
    def prepare_text(cls, text, *, lang):
        if lang == 'ru_RU':
            text = text.replace('ё', 'е')
        for match in cls.spell_pattern.finditer(text):
            for word in match.group('words').split(' '):
                text = text.replace(word, '')
        return text


class LaTeXSlicer:
    def __init__(self, text):
        self.text = text

    latex_optarg = r'(?:\[[^%{}\[\]\n]+\])?'
    latex_reqarg = r'(?:\{[^%{}\[\]\n]+\})'
    latex_possible_args = (
        r'(?:'
            r'\*'
        r'|'
            r'\{[^%{}\[\]\n]+\}'
        r'|'
            r'\[[^%{}\[\]\n]+\]'
        r')*' )
    LATEX_PATTERNS = OrderedDict((
        ('nospell', r'(?ms)^% nospell begin$.*?^% nospell end$\n'),
        ('comment',                 r'%.*\n'),
        ('tex_begin',               r'\{'),
        ('tex_end',                 r'\}'),
        ('latex_begin',
            r'\\begin\{(?P<environment>[^%{}\n]+)\}' + latex_possible_args),
        ('latex_end',
            r'\\end\{(?P<environment>[^%{}\n]+)\}'),
        ('tex_display_math',        r'\$\$'),
        ('tex_inline_math',         r'\$'),
        ('latex_display_math_begin',    r'\\\['),
        ('latex_display_math_end',      r'\\\]'),
        ('latex_inline_math_begin',     r'\\\('),
        ('latex_inline_math_end',       r'\\\)'),
        ('text_macro_begin',        r'\\(?:inter)?text\{'),
        ('label_macro',             r'\\(?:label|ref)' + latex_reqarg),
        ('space_macro',             r'\\(?:vspace|hspace)' + latex_reqarg),
        ('latex_style_macro_begin',     r'\\(?:emph|textbf){' ),
        ('linebreak_macro',         r'\\\\\*?' + latex_optarg),
        ('newline',                 r'\n'),
        ('macro',                   r'\\[a-zA-Z]+' + latex_possible_args),
        ('escape_macro',            r'\\(?:[${}%])'),
        ('char_macro',              r'\\(?:[^a-zA-Z${}%\n])'),
        ('tex_size_argument',
            r'(?:\d+\.?\d*|\.\d+)(?:em|ex|in|pt|cm)' ),
        ('dotted_abbr',             r'(?!\d)\w\.(?:(?:~)?(?!\d)\w\.)+'),
        ('word',
            r'(?<![\-\w])(?!-)'
                r'(?:(?!\d)[\w\-])+'
            r'(?<!-)' ),
    ))

    math_environments = frozenset((
        'math', 'displaymath', 'equation', 'equation*',
        'align', 'align*',
        'eqnarray', 'eqnarray*',
        'multline', 'multline*',
        'gather', 'gather*',
        'flalign', 'flalign*',
        'alignat', 'alignat*',
    ))

    def __iter__(self):

        text = self.text
        length = len(text)
        patterns = [
            (name, re.compile(pattern))
            for name, pattern in self.LATEX_PATTERNS.items()
        ]

        pos = clean_pos = 0
        stack = self.LaTeXStack()
        while pos < length:
            for name, pattern in patterns:
                match = pattern.match(text, pos)
                if match is not None:
                    break
            else:
                pos = pos + 1
                continue
            if pos > clean_pos:
                yield TextPiece(text[clean_pos:pos])
                clean_pos = pos
            matched_piece = match.group(0)
            # pylint: disable=undefined-loop-variable
            if not stack.math_mode and name in {'dotted_abbr', 'word'}:
                if name == 'word':
                    yield Word(matched_piece)
                elif name == 'dotted_abbr':
                    yield DottedAbbr(matched_piece)
            else:
                method = getattr(self, name, None)
                if method is not None:
                    try:
                        method(match, stack)
                    except self.LaTeXStack.Error as error:
                        error.args += ("<char={}>".format(match.group(0)),)
                yield TextPiece(matched_piece)
            # pylint: enable=undefined-loop-variable
            pos = clean_pos = match.end()
        stack.finish()

    # pylint: disable=unused-argument

    @staticmethod
    def tex_begin(match, stack):
        stack.push('{')

    @staticmethod
    def tex_end(match, stack):
        closed = stack.pop(('{', r'\text{'), '}')
        if closed == '{':
            pass
        elif closed == r'\text{':
            stack.enter_math()
        else:
            raise RuntimeError

    @staticmethod
    def latex_begin(match, stack, math_environments=math_environments):
        environment = match.group('environment')
        stack.push_environment(environment)
        if environment in math_environments:
            stack.enter_math()

    @staticmethod
    def latex_end(match, stack, math_environments=math_environments):
        environment = match.group('environment')
        stack.pop_environment(environment)
        if environment in math_environments:
            stack.exit_math()

    @staticmethod
    def tex_display_math(match, stack):
        if stack.topmost != '$$':
            stack.push('$$')
            stack.enter_math()
        else:
            stack.pop('$$', '$$')
            logger.warning("'$$' usage in LaTeX document detected")
            stack.exit_math()

    @staticmethod
    def tex_inline_math(match, stack):
        if stack.topmost != '$':
            stack.push('$')
            stack.enter_math()
        else:
            stack.pop('$', '$')
            stack.exit_math()

    @staticmethod
    def latex_display_math_begin(match, stack):
        stack.push(r'\[')
        stack.enter_math()

    @staticmethod
    def latex_display_math_end(match, stack):
        stack.pop(r'\[', r'\]')
        stack.exit_math()

    @staticmethod
    def latex_inline_math_begin(match, stack):
        stack.push(r'\(')
        stack.enter_math()

    @staticmethod
    def latex_inline_math_end(match, stack):
        stack.pop(r'\(', r'\)')
        stack.exit_math()

    @staticmethod
    def latex_style_macro_begin(match, stack):
        stack.push('{')

    @staticmethod
    def text_macro_begin(match, stack):
        if stack.math_mode:
            stack.push(r'\text{')
            stack.exit_math()
        else:
            stack.push('{')

    # pylint: enable=unused-argument

    class LaTeXStack:
        __slots__ = ['_stack', 'math_mode']
        fatal = True

        class Error(ValueError):
            pass

        def __init__(self):
            super().__init__()
            self._stack = ['document']
            self.math_mode = False

        @property
        def topmost(self):
            return self._stack[-1]

        def push(self, value):
            return self._stack.append(value)

        def push_environment(self, environment):
            return self.push(r'\begin{{{}}}'.format(environment))

        def pop(self, expected, right):
            if isinstance(expected, str):
                expected = (expected,)
            assert isinstance(expected, tuple), type(expected)
            left = self.topmost
            if left not in expected:
                self.error("{} is closed by {}".format(left, right))
            self._stack.pop()
            return left

        def pop_environment(self, environment):
            return self.pop(
                r'\begin{{{}}}'.format(environment),
                r'\end{{{}}}'.format(environment) )

        def enter_math(self):
            if self.math_mode:
                self.error('Double-entered math mode.')
            self.math_mode = True

        def exit_math(self):
            if not self.math_mode:
                self.error("Double-exited math mode.")
            self.math_mode = False

        def finish(self):
            if self.topmost != 'document':
                self.error("Unclosed groups by the end of the document.")

        def error(self, message):
            message += ' <stack={}>'.format(self._stack)
            logger.error(message)
            if self.fatal:
                raise self.Error(message)

