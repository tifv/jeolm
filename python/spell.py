import re
from collections import OrderedDict

import enchant

import logging
logger = logging.getLogger(__name__)

class TextPiece:
    __slots__ = ['s']

    def __init__(self, s):
        if isinstance(s, str):
            self.s = s
        elif isinstance(s, TextPiece):
            self.s = s.s
        else:
            raise RuntimeError(type(s))

    def __str__(self):
        return self.s

class Word(TextPiece):

    def correct(self, is_correct=True):
        if is_correct:
            return CorrectWord(self)
        else:
            return self.incorrect()

    def incorrect(self):
        return IncorrectWord(self)

class DottedAbbr(Word):
    pass

class CorrectWord(Word):
    def __str__(self):
        return '<GREEN>' + super().__str__() + '<NOCOLOUR>'

class IncorrectWord(Word):
    def __str__(self):
        return '<RED>' + super().__str__() + '<NOCOLOUR>'

class Speller:
    def __init__(self, text, lang):
        self.lang = lang
        self.text = self.prepare_text(text, lang=lang)

    known_langs = frozenset(('en_US', 'ru_RU'))
    dotted_abbrs = {
        'en_US' : frozenset(('e.\,g.', 'i.\,e.')),
        'ru_RU' : frozenset(('т.\,д.', 'т.\,е.')),
    }

    def __iter__(self):
        dictionary = enchant.Dict(self.lang)

        for text_piece in LaTeXSlicer(self.text):
            assert isinstance(text_piece, TextPiece), type(text_piece)
            if not isinstance(text_piece, Word):
                yield text_piece
                continue
            if isinstance(text_piece, DottedAbbr):
                yield text_piece.correct(
                    text_piece.s in self.dotted_abbrs[self.lang] )
                continue
            yield text_piece.correct(dictionary.check(text_piece.s))

    prepare_text_pattern = re.compile('(?m)'
        r'^% spell (?P<delimiter>.)(?P<from>.*?)(?P=delimiter)'
        r' -> '
        r'(?P=delimiter)(?P<to>.*?)(?P=delimiter)$' )

    @classmethod
    def prepare_text(cls, text, *, lang):
        if lang == 'ru_RU':
            text = text.replace('ё', 'е')
        for match in cls.prepare_text_pattern.finditer(text):
            logger.debug(match.groupdict())
            text = text.replace(match.group('from'), match.group('to'))
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
        ('dotted_abbr',             r'(?!\d)\w\.(?:(?:\\,)?(?!\d)\w\.)+'),
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
            pos = clean_pos = match.end()
        stack.finish()

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
            message += ' <stack={}>'.format( list(self) )
            logger.error(message)
            if self.fatal:
                raise self.Error(message)

