import re

import enchant

import logging
logger = logging.getLogger(__name__)

prepare_pattern = re.compile('(?m)'
    r'^% (?P<delimiter>.)(?P<from>.*?)(?P=delimiter)'
    r' -> '
    r'(?P=delimiter)(?P<to>.*?)(?P=delimiter)$' )

def prepare_original(s, *, lang):
    assert lang == 'ru_RU'
    s = s.replace('ё', 'е')
    for match in prepare_pattern.finditer(s):
        logger.debug(match.groupdict())
        s = s.replace(match.group('from'), match.group('to'))
    return s

def correct(s, *, lang):
    return ''.join(_correct_iter(s, lang=lang))

def _correct_iter(s, *, lang):
    clean_position = 0
    for match, suggestions in misspellings(s, lang=lang):
        yield s[clean_position:match.start()]
        yield '['
        yield ','.join(
            suggestions[:3] or
            '?' * max(1, match.end() - match.start() - 2) )
        yield ']'
        clean_position = match.end()
    yield s[clean_position:]

def misspellings(s, *, lang):
    dictionary = enchant.Dict(lang)
    for match in words(s, lang=lang):
        if match.group('dotted_abbr') is not None:
            continue
        if dictionary.check(match.group()):
            continue
        yield match, dictionary.suggest(match.group())

ru_word_pattern = re.compile(
    r'(?P<dotted_abbr>[а-яА-Я]\.(?:\\\,[а-яА-Я]\.)+)'
        '|'
    r'(?P<word>(?<![а-яА-Я\-])(?![-])[а-яА-Я\-]+)' )

en_word_pattern = re.compile(
    r'(?P<dotted_abbr>[a-zA-Z]\.(?:\\,[a-zA-Z]\.)+)'
        '|'
    r'(?P<word>(?!-)[a-zA-Z\-]+)' )

def words(s, *, lang):
    """Generate matches"""
    if lang.startswith('ru'):
        word_pattern = ru_word_pattern
    elif lang.startswith('en'):
        word_pattern = en_word_pattern
    word_iter = word_pattern.finditer
    for text_slice in detex(s):
        for match in word_iter(s, text_slice.start, text_slice.stop):
            yield match

latex_pattern = re.compile(
    r'(?P<comment>%.*\n)'
        '|'
    r'(?P<brace_open>\{)'
        '|'
    r'(?P<brace_close>\})'
        '|'
    r'\\begin{(?P<latex_begin>.+?)}'
        '|'
    r'\\end{(?P<latex_end>.+?)}'
        '|'
    r'(?P<tex_display_math>\$\$)'
        '|'
    r'(?P<tex_inline_math>\$)'
        '|'
    r'(?P<latex_display_math_begin>\\\[)'
        '|'
    r'(?P<latex_display_math_end>\\\])'
        '|'
    r'(?P<latex_inline_math_begin>\\\()'
        '|'
    r'(?P<latex_inline_math_end>\\\))'
        '|'
    r'(?P<text_open>\\(?:inter)?text{)'
        '|'
    r'(?P<label_macro>\\(?:label|ref){[^{}]+?})'
        '|'
    r'(?P<space_macro>\\(?:vspace|hspace){[^{}]+?})'
        '|'
    r'(?P<newline>\\\\(?:\[[^{}[\]]+?\])?)'
        '|'
    r'(?P<macro>\\[a-zA-Z]+(?![a-zA-Z]))'
        '|'
    r'(?P<escape>\\(?:[${}%]))'
#        '|'
#    r'(?P<char_macro>\\(?:[^a-zA-Z]))'
)
_latex_pattern_index = {v : k for k, v in latex_pattern.groupindex.items()}

latex_rubbish = frozenset((
    'label_macro', 'space_macro',
    'newline',
    'macro', 'escape',
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

def detex(s, fatal=False):
    """
    Find text pieces in LaTeX string s.

    Generate slices so that s[slice] is a text piece.
    """

    stack = ['document']
    math_mode = False
    clean_position = 0

    def enter_math():
        nonlocal math_mode
        if math_mode:
            error()
        math_mode = True
    def exit_math():
        nonlocal math_mode
        if not math_mode:
            error()
        math_mode = False
    def error():
        args = (match.start(), stack, match.group())
        logger.error(args)
        if fatal:
            raise ValueError(*args)

    def comment(group):
        pass
    def brace_open(group):
        stack.append('{')
    def brace_close(group):
        closed = stack[-1]
        if closed == '{':
            pass
        elif closed == r'\text{':
            enter_math()
        else: error()
        stack.pop()
    def latex_begin(environment, math_environments=math_environments):
        if environment in math_environments:
            enter_math()
        stack.append(environment)
    def latex_end(environment, math_environments=math_environments):
        if stack[-1] != environment: error()
        if environment in math_environments:
            exit_math()
        stack.pop()
    def tex_display_math(group):
        if stack[-1] != '$$':
            enter_math(); stack.append('$$')
        else:
            exit_math(); stack.pop()
    def tex_inline_math(group):
        if stack[-1] != '$':
            enter_math(); stack.append('$')
        else:
            exit_math(); stack.pop()
    def latex_display_math_begin(group):
        enter_math(); stack.append(r'\[')
    def latex_display_math_end(group):
        if stack[-1] == r'\[':
            pass
        else: error()
        exit_math(); stack.pop()
    def latex_inline_math_begin(group):
        enter_math(); stack.append(r'\(')
    def latex_inline_math_end(group):
        if stack[-1] == r'\(':
            pass
        else: error()
        exit_math(); stack.pop()
    def text_open(group):
        if math_mode:
            exit_math(); stack.append(r'\text{')
        else:
            stack.append(r'{')
    def rubbish(group):
        pass

    namespace = locals()
    function_index = [
        namespace.get(_latex_pattern_index.get(i, 'nothing'), rubbish)
        for i in range(len(_latex_pattern_index)+1)
    ]

    for match in latex_pattern.finditer(s):
        if not math_mode:
            yield slice(clean_position, match.start())
        clean_position = match.end()

        group, = (v for v in match.groups() if v is not None)
        function_index[match.lastindex](group)
    yield slice(clean_position, len(s))

