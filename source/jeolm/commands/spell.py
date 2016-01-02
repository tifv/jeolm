import re
from collections import OrderedDict

import enchant

from jeolm.commands.list_sources import list_sources

import logging
logger = logging.getLogger(__name__)


def check_spelling(targets, *, local, driver, colour=True):
    if colour:
        from jeolm.fancify import fancifying_print as fprint
    else:
        logger.warning('Spelling is nearly useless in colourless mode.')
        from jeolm.fancify import unfancifying_print as fprint
    indicator = Indicator()
    formatter = Formatter(fprint=fprint)

    path_generator = list_sources(targets,
        local=local, driver=driver, source_type='tex' )
    for path in path_generator:
        indicator.show(str(path.relative_to(local.source_dir)))
        formatter.reset()
        with path.open('r') as checked_file:
            text = checked_file.read()
        try:
            for piece in Speller(text, lang='ru_RU'):
                formatter.add_piece(piece)
        except ValueError as error:
            raise ValueError(
                "Error while spell-checking {}"
                .format(path.relative_to(local.source_dir))
            ) from error
        if not formatter.selected_lines:
            continue
        indicator.clean()
        fprint(
            '<BOLD><YELLOW>{}<NOCOLOUR> possible misspellings<REGULAR>'
            .format(path.relative_to(local.source_dir)) )
        formatter.print_selected_lines()
    indicator.clean()


class Indicator:

    def __init__(self):
        self.length = 0

    def clean(self):
        if self.length:
            print(' ' * self.length, end='\r')
            self.length = 0

    def show(self, name):
        if not isinstance(name, str):
            raise TypeError(type(name))
        print(name + ' ' * (self.length - len(name)), end='\r')
        self.length = len(name)

class Formatter:

    def __init__(self, fprint, context=0):
        self._fprint = fprint
        self.context = context

        self.lines = None
        self.selected_lines = None
        self.reset()

    def reset(self):
        self.lines = ['']
        self.selected_lines = set()

    def add_piece(self, piece):
        if isinstance(piece, IncorrectWord):
            lineno = len(self.lines) - 1
            self.selected_lines.update(
                range(lineno-self.context, lineno+self.context+1) )
        if isinstance(piece, NewlinePiece):
            assert piece.string == '\n'
            self.lines.append('')
            return
        elif '\n' in piece.string:
            for subpiece in self.split_piece(piece):
                self.add_piece(subpiece)
            return
        self.lines[-1] += self.format_piece(piece)

    def print_selected_lines(self):
        lines = self.lines
        line_range = range(len(lines))
        lineno_offset = len(str(len(lines)))
        for lineno in sorted(self.selected_lines):
            if lineno not in line_range:
                continue
            self._fprint(
                '<MAGENTA>{lineno: >{lineno_offset}}<NOCOLOUR>:{line}'
                .format( lineno=lineno+1, lineno_offset=lineno_offset,
                    line=lines[lineno] )
            )

    @staticmethod
    def split_piece(piece):
        piece_cls = type(piece)
        first = True
        for substring in piece.string.split('\n'):
            if not first:
                yield NewlinePiece('\n')
            yield piece_cls(substring)
            first = False

    @staticmethod
    def format_piece(piece):
        assert isinstance(piece, TextPiece), type(piece)
        if isinstance(piece, ExcludedPiece):
            return '<BLUE>{}<NOCOLOUR>'.format(piece.string)
        elif isinstance(piece, CorrectWord):
            return '<GREEN>{}<NOCOLOUR>'.format(piece.string)
        elif isinstance(piece, IncorrectWord):
            return '<RED>{}<NOCOLOUR>'.format(piece.string)
        else:
            return piece.string


class TextPiece:
    __slots__ = ['string']

    def __init__(self, string):
        if isinstance(string, str):
            self.string = string
        else:
            raise RuntimeError(type(string))

class NewlinePiece(TextPiece):
    __slots__ = []

class ExcludedPiece(TextPiece):
    __slots__ = []

class Word(TextPiece):
    __slots__ = []

class DottedAbbr(Word):
    __slots__ = []

class CorrectWord(Word):
    __slots__ = []

class IncorrectWord(Word):
    __slots__ = []

class CorrectAbbr(DottedAbbr, CorrectWord):
    __slots__ = []

class IncorrectAbbr(DottedAbbr, IncorrectWord):
    __slots__ = []


class Speller:

    known_langs = frozenset(('en_US', 'ru_RU'))
    dotted_abbrs = {
        'en_US' : frozenset(('e.~g.', 'i.~e.')),
        'ru_RU' : frozenset(('т.~д.', 'т.~е.')),
    }
    spell_regex = re.compile( r'(?m)'
    r'^% spell (?:'
        r'(?P<exclude_type>words|string|regex) (?P<exclude>.*)'
    r'|'
        r'.*' # mismatch (detected by lack of 'exclude_type' group)
    r')$' )

    def __init__(self, text, lang):
        self.lang = lang
        assert self.lang in self.known_langs, self.lang
        self.dictionary = enchant.Dict(self.lang)
        self.text = self.prepare_text(text, lang=self.lang)
        self.exclusions = list(self.find_exclusions(text))

    @classmethod
    def prepare_text(cls, text, *, lang):
        if lang == 'ru_RU':
            text = text.replace('ё', 'е')
        return text

    @classmethod
    def find_exclusions(cls, text):
        for match in cls.spell_regex.finditer(text):
            if match.group('exclude_type') == 'words':
                for word in match.group('exclude').split(' '):
                    if not word[0].isalnum() or not word[-1].isalnum():
                        raise ValueError(word)
                    yield r'\b' + re.escape(word) + r'\b'
            elif match.group('exclude_type') == 'string':
                yield re.escape(match.group('exclude'))
            elif match.group('exclude_type') == 'regex':
                yield match.group('exclude')
            else:
                raise ValueError(match.group(0))

    def __iter__(self):
        for text_piece in Slicer(self.text, self.exclusions):
            assert isinstance(text_piece, TextPiece), type(text_piece)
            if not isinstance(text_piece, Word):
                yield text_piece
            elif isinstance(text_piece, DottedAbbr):
                if self.check_abbr(text_piece.string):
                    yield CorrectAbbr(text_piece.string)
                else:
                    yield IncorrectAbbr(text_piece.string)
            else:
                if self.check_word(text_piece.string):
                    yield CorrectWord(text_piece.string)
                else:
                    yield IncorrectWord(text_piece.string)

    def check_word(self, word):
        try:
            return self.dictionary.check(word)
        except enchant.errors.Error as exception:
            raise ValueError(
                "Unable to check word '{}'".format(word)
            ) from exception

    def check_abbr(self, abbr):
        return abbr in self.dotted_abbrs[self.lang]


class Slicer:

    def __init__(self, text, exclusions):
        self.text = text
        if not exclusions:
            self.regex = self._default_regex
        else:
            self.regex = self._get_regex(exclusions)
        self.stack = self.Stack()

    @classmethod
    def _get_regex(cls, exclusions):
        assert exclusions
        pattern = (
            r'(?P<exclude>' +
                r'|'.join(exclusions) +
            r')' +
            r'|' +
            cls._latex_base_pattern
        )
        regex = re.compile(pattern, re.MULTILINE)
        return regex

    # All regexes imply re.MULTILINE

    _tex_normal_macro = r'\\[a-zA-Z]{2,}'
    _tex_char_macro = r'\\[^\n]'
    _tex_macro = _tex_normal_macro + r'|' + _tex_char_macro
    _latex_arg = (
        r'(?:' +
            _tex_macro +
        r'|' +
            r'[^\\%{}\[\]\n]' +
        r')*' )
    _latex_reqarg = r'\{(?:' + _latex_arg + r')\}'
    _latex_optarg = r'\[(?:' + _latex_arg + r')\]'
    _latex_possible_args = (
        r'(?:\s*(?:' +
            r'\*' +
        r'|' +
            _latex_reqarg +
        r'|' +
            _latex_optarg +
        r'))*' )

    _latex_patterns = OrderedDict((
        ('nospell', r'^% nospell begin$(?:.|\n)*?^% nospell end$\n'),
        ('comment',                 r'%.*\n'),
        ('text_end',                r'\Z'),
        ('tex_begin',               r'\{'),
        ('tex_end',                 r'\}'),
        ('tex_begingroup',          r'\begingroup'),
        ('tex_endgroup',            r'\endgroup'),
        ('latex_begin',
            r'\\begin\{(?P<begin_environment>[^\\%{}\[\]\n]+)\}' +
                r'(?:' + _latex_possible_args + r')' ),
        ('latex_end',
            r'\\end\{(?P<end_environment>[^%{}\n]+)\}' ),
        ('tex_display_math',        r'\$\$'),
        ('tex_inline_math',         r'\$'),
        ('latex_display_math_begin',    r'\\\['),
        ('latex_display_math_end',      r'\\\]'),
        ('latex_inline_math_begin',     r'\\\('),
        ('latex_inline_math_end',       r'\\\)'),
        ('latex_text_macro_begin',
            r'\\(?:text|emph|textbf|textsf|textit)\{' ),
        ('intertext_macro_begin',        r'\\intertext\{'),
        ('label_macro',             r'\\(?:label|ref)' + _latex_reqarg),
        ('space_macro',             r'\\(?:vspace|hspace)' + _latex_reqarg),
        ('accent_macro',
            r"\\[`'\^" + r'"H~ckl=b\.druvto]\{[^%{}\n]?\}' ),
        ('linebreak_macro',         r'\\\\\*?(?:' + _latex_optarg + ')?'),
        ('newline',                   r'\n'),
        ('space',                   r'[\s~]+'),
        ('normal_macro',
            _tex_normal_macro + _latex_possible_args ),
        ('char_macro',              _tex_char_macro),
        ('tex_size_argument',
            r'(?:\d+\.?\d*|\.\d+)(?:em|ex|in|pt|cm)' ),
        ('dotted_abbr',             r'(?!\d)\w\.(?:~?(?!\d)\w\.)+'),
        ('word',
            r'(?<![\-\w])(?!-)'
                r'(?:(?!\d)[\w\-])+'
            r'(?<!-)' ),
    ))
    _latex_base_pattern = r'|'.join(
        r'(?P<' + name + r'>' + pattern + r')'
        for name, pattern in _latex_patterns.items()
    )
    _default_regex = re.compile(_latex_base_pattern, re.MULTILINE)


    def __iter__(self):
        text = self.text
        last_end = 0
        with self.stack:
            for match in self.regex.finditer(text):
                start, end = match.span()
                if start > last_end:
                    yield TextPiece(text[last_end:start])
                last_end = end
                yield from self._extract_text_pieces(match)
            assert last_end == len(text)

    def _extract_text_pieces(self, match):
        name = match.lastgroup
        assert name in self._latex_patterns or name == 'exclude', name
        string = match.group(name)
        piece_method = getattr(self, name, None)
        if piece_method is None:
            yield TextPiece(string)
        else:
            try:
                yield from piece_method(match, string)
            except self.Stack.Error as error:
                error.args += (match,)
                raise


    math_environments = frozenset((
        'math', 'displaymath', 'equation', 'equation*',
        'align', 'align*',
        'eqnarray', 'eqnarray*',
        'multline', 'multline*',
        'gather', 'gather*',
        'flalign', 'flalign*',
        'alignat', 'alignat*',
    ))

    # pylint: disable=no-self-use,unused-argument

    def text_end(self, match, string):
        return ()

    def newline(self, match, string):
        yield NewlinePiece(string)

    def exclude(self, match, string):
        yield ExcludedPiece(string)

    def word(self, match, string):
        if not self.stack.math_mode:
            yield Word(string)
        else:
            yield TextPiece(string)

    def dotted_abbr(self, match, string):
        if not self.stack.math_mode:
            yield DottedAbbr(string)
        else:
            yield TextPiece(string)

    def tex_begin(self, match, string):
        self.stack.push('{')
        yield TextPiece(string)

    def tex_end(self, match, string):
        self.stack.pop('{', '}')
        yield TextPiece(string)

    def tex_begingroup(self, match, string):
        self.stack.push(r'\begingroup')
        yield TextPiece(string)

    def tex_endgroup(self, match, string):
        self.stack.pop(r'\begingroup', r'\endgroup')
        yield TextPiece(string)

    def latex_begin(self, match, string):
        environment = match.group('begin_environment')
        if environment in self.math_environments:
            math_mode = True
        else:
            math_mode = None
        self.stack.begin_environment(environment, math_mode=math_mode)
        yield TextPiece(string)

    def latex_end(self, match, string):
        environment = match.group('end_environment')
        self.stack.end_environment(environment)
        yield TextPiece(string)

    def tex_display_math(self, match, string):
        if not self.stack.math_mode:
            self.stack.push('$$', math_mode=True)
        else:
            self.stack.pop('$$', '$$')
            logger.warning("'$$' usage in LaTeX document detected")
        yield TextPiece(string)

    def tex_inline_math(self, match, string):
        if not self.stack.math_mode:
            self.stack.push('$', math_mode=True)
        else:
            self.stack.pop('$', '$')
        yield TextPiece(string)

    def latex_display_math_begin(self, match, string):
        self.stack.push(r'\[', math_mode=True)
        yield TextPiece(string)

    def latex_display_math_end(self, match, string):
        self.stack.pop(r'\[', r'\]')
        yield TextPiece(string)

    def latex_inline_math_begin(self, match, string):
        self.stack.push(r'\(', math_mode=True)
        yield TextPiece(string)

    def latex_inline_math_end(self, match, string):
        self.stack.pop(r'\(', r'\)')
        yield TextPiece(string)

    def latex_text_macro_begin(self, match, string):
        self.stack.push('{', math_mode=False)
        yield TextPiece(string)

    def intertext_macro_begin(self, match, string):
        if not self.stack.math_mode:
            self.stack.error(
                r"'\intertext' usage outside of math environment detected" )
        self.stack.push('{', math_mode=False)
        yield TextPiece(string)

    # pylint: enable=no-self-use,unused-argument


    class Stack:
        fatal = True

        class Error(ValueError):
            pass

        def __init__(self):
            super().__init__()
            self._stack = None
            # self._stack is a triple (left, math_mode, tail) or None

        # pylint: disable=unused-variable,unpacking-non-sequence

        @property
        def left(self):
            left, math_mode, tail = self._stack
            return left

        @property
        def math_mode(self):
            left, math_mode, tail = self._stack
            return math_mode

        def push(self, left, *, math_mode=None):
            if math_mode is None:
                math_mode = self.math_mode
            elif math_mode:
                if self.math_mode:
                    self.error('Double-entered math mode.')
                math_mode = True
            else:
                math_mode = False
            assert isinstance(left, str)
            assert isinstance(math_mode, bool)
            self._stack = (left, math_mode, self._stack)

        def pop(self, expected_left, right):
            assert isinstance(expected_left, str) or expected_left is None
            (left, math_mode, self._stack) = self._stack
            if expected_left is not None and left != expected_left:
                self.error("'{}' is closed by '{}'".format(left, right))
            return left

        # pylint: enable=unused-variable,unpacking-non-sequence

        def begin_environment(self, environment, *, math_mode=None):
            return self.push(
                r'\begin{{{}}}'.format(environment),
                math_mode=math_mode )

        def end_environment(self, environment):
            return self.pop(
                r'\begin{{{}}}'.format(environment),
                r'\end{{{}}}'.format(environment) )

        def __enter__(self):
            self.begin_environment('document', math_mode=False)

        def __exit__(self, exc_type, exc_value, traceback):
            if exc_type is not None:
                return False # let the exception propagate
            self.end_environment('document')
            assert self._stack is None

        def error(self, message):
            message += ' <stack={}>'.format(self._stack)
            logger.error(message)
            if self.fatal:
                raise self.Error(message)

