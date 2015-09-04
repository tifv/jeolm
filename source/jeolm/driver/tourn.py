from functools import wraps
from string import Template

from jeolm.record_path import RecordPath
from jeolm.flags import FlagContainer
from jeolm.target import Target

from jeolm.driver.regular import RegularDriver, DriverError
from jeolm.driver.include import IncludingRecords

from . import processing_target, ensure_type_items

import logging
logger = logging.getLogger(__name__)

TOURN_PROBLEM_FLAGS = frozenset(('problems', 'solutions', 'complete',))

TOURN_ALL_FLAGS = frozenset((
    'problems', 'solutions', 'complete',
    'contest', 'jury', 'blank' ))

TOURN_CONTEST_KEYS = frozenset((
    '$contest', '$contest$league', '$contest$problem' ))
TOURN_REGATTA_KEYS = frozenset((
    '$regatta', '$regatta$league',
    '$regatta$subject', '$regatta$round',
    '$regatta$problem' ))
TOURN_SUBLEAGUE_KEYS = frozenset((
    '$contest$league', '$regatta$league',
    '$regatta$subject', '$regatta$round',
    '$contest$problem', '$regatta$problem', ))

def _get_tourn_flags(tourn_key):
    flags = set(TOURN_PROBLEM_FLAGS)
    if tourn_key in {'$contest$problem'}:
        pass
    elif tourn_key in {'$regatta$problem'}:
        flags.add('blank')
    else:
        flags.update({'contest', 'jury'})
    return flags

def ensure_tourn_flags(method):
    """Decorator."""
    @wraps(method)
    def wrapper(self, target, metarecord, **kwargs):
        tourn_key = metarecord.get('$tourn$key')
        if tourn_key is None:
            raise RuntimeError(target)
        tourn_flags = _get_tourn_flags(tourn_key)
        misused_flags = target.flags.intersection(
            TOURN_ALL_FLAGS - tourn_flags )
        if misused_flags:
            raise DriverError(
                "Misused tourn flags {flags} in {target}"
                .format(flags=misused_flags, target=target) )
        if not target.flags.intersection(tourn_flags):
            logger.error(
                "One of tourn flags is required: %(flags)s",
                dict(flags=', '.join(sorted(tourn_flags)))
            )
            raise DriverError(
                "No tourn flags in {target}"
                .format(target=target) )
        return method(self, target, metarecord, **kwargs)
    return wrapper

class TournDriver(RegularDriver, IncludingRecords):

    @property
    def translations(self, _root=RecordPath()):
        translations = self.get(_root)['$translations']
        assert isinstance(translations, dict)
        assert all(isinstance(value, dict) for value in translations.values())
        return translations

    @staticmethod
    def target_flags_contest_to_blank(target):
        return target.flags_delta(
            difference={'contest'},
            union={'blank', 'without-problem-sources'} )

    @staticmethod
    def target_flags_jury_to_complete(target):
        return target.flags_delta(
            difference={'jury'},
            union={'complete', 'with-criteria'} )


    ##########
    # Record-level functions

    @ensure_type_items(RegularDriver.MetabodyItem)
    def _generate_header_def_metabody(self, target, metarecord, *, date):
        yield from super()._generate_header_def_metabody(
            target, metarecord, date=date )
        if '$tourn$key' not in metarecord:
            return
        tourn_key = metarecord['$tourn$key']

        if 'league-contained' in target.flags:
            if tourn_key not in TOURN_SUBLEAGUE_KEYS:
                raise RuntimeError(target)
            league = self._find_league(target.path, metarecord)
            yield self.VerbatimBodyItem(
                self.league_def_template.substitute(
                    league=self._find_name(league, metarecord['$language'])
                ) )
        else:
            if tourn_key in TOURN_SUBLEAGUE_KEYS:
                raise RuntimeError(target)

    # Extension
    @ensure_type_items((RegularDriver.MetabodyItem, Target))
    @processing_target
    def _generate_auto_metabody(self, target, metarecord):
        if '$tourn$key' not in metarecord:
            yield from super()._generate_auto_metabody(target, metarecord)
            return

        tourn_key = metarecord['$tourn$key']
        is_subleague = tourn_key in TOURN_SUBLEAGUE_KEYS
        is_regatta = tourn_key in TOURN_REGATTA_KEYS
        is_contest = tourn_key in TOURN_CONTEST_KEYS
        assert is_regatta or is_contest
        is_single_problem = (
            tourn_key in {'$contest$problem', '$regatta$problem'} )
        is_regatta_contest = ( is_regatta and
            not is_single_problem and 'contest' in target.flags )
        if 'no-header' not in target.flags and not is_regatta_contest:
            if is_subleague:
                yield target.flags_union({'header', 'league-contained'})
            else:
                yield target.flags_union({'header'})
        else:
            yield from self._generate_tourn_metabody(target, metarecord)

    @ensure_type_items((RegularDriver.MetabodyItem, Target))
    @processing_target
    def _generate_tourn_metabody(self, target, metarecord):
        tourn_key = metarecord['$tourn$key']
        tourn_flags = target.flags.intersection(_get_tourn_flags(tourn_key))
        if len(tourn_flags) > 1:
            raise ValueError(sorted(tourn_flags))

        args = [target, metarecord]
        kwargs = dict()
        if tourn_key in TOURN_CONTEST_KEYS:
            kwargs.update(contest=self._find_contest(target.path, metarecord))
        elif tourn_key in TOURN_REGATTA_KEYS:
            kwargs.update(regatta=self._find_regatta(target.path, metarecord))
        else:
            raise RuntimeError(tourn_key)
        if tourn_key in TOURN_SUBLEAGUE_KEYS:
            kwargs.update(league=self._find_league(target.path, metarecord))

        method = getattr(self,
            '_generate' + tourn_key.replace('$', '_') + '_matter' )

        yield from method(*args, **kwargs)

    @ensure_tourn_flags
    @ensure_type_items((RegularDriver.MetabodyItem, Target))
    @processing_target
    def _generate_contest_matter(self, target, metarecord,
        *, contest
    ):
        if 'contest' not in target.flags:
            yield self.VerbatimBodyItem(
                self.constitute_section(
                    self._find_name(contest, metarecord['$language']),
                    flags=target.flags )
            )
            target = target.flags_union({'contained'}, overadd=False)
            target = target.flags_union(
                self.increase_containment(target.flags) )

        for leaguekey in contest['leagues']:
            yield target.path_derive(leaguekey)

    @ensure_tourn_flags
    @ensure_type_items((RegularDriver.MetabodyItem, Target))
    @processing_target
    def _generate_regatta_matter(self, target, metarecord,
        *, regatta
    ):
        if 'contest' not in target.flags:
            yield self.VerbatimBodyItem(
                self.constitute_section(
                    self._find_name(regatta, metarecord['$language']),
                    flags=target.flags )
            )
            target = target.flags_union({'contained'}, overadd=False)
            target = target.flags_union(
                self.increase_containment(target.flags) )

        for leaguekey in regatta['leagues']:
            yield target.path_derive(leaguekey)

    @ensure_tourn_flags
    @ensure_type_items((RegularDriver.MetabodyItem, Target))
    @processing_target
    def _generate_contest_league_matter(self, target, metarecord,
        *, contest, league
    ):
        if 'contest' in target.flags:
            target = target.flags_delta(
                difference={'contest'},
                union={'problems', 'without-problem-sources'} )
            has_briefing = True
        else:
            has_briefing = False
        language = metarecord['$language']
        if 'league-contained' in target.flags:
            league_name = None
        else:
            league_name = self._find_name(league, language)
        yield self.VerbatimBodyItem(
            self.constitute_section(
                self._find_name(contest, language),
                league_name,
                flags=target.flags )
        )

        if 'jury' in target.flags:
            target = self.target_flags_jury_to_complete(target)
        yield self.VerbatimBodyItem(
            self.constitute_begin_tourn_problems(
                target.flags.intersection(TOURN_PROBLEM_FLAGS) )
        )
        target = target.flags_union({'itemized'})
        for problem in range(1, 1 + league['problems']):
            yield target.path_derive(str(problem))
        yield self.VerbatimBodyItem(
            self.end_tourn_problems_template.substitute() )
        if has_briefing:
            yield self.VerbatimBodyItem(
                self.briefing_template.substitute() )

    @ensure_tourn_flags
    @ensure_type_items((RegularDriver.MetabodyItem, Target))
    @processing_target
    def _generate_regatta_league_matter(self, target, metarecord,
        *, regatta, league
    ):
        if 'contest' not in target.flags:
            language = metarecord['$language']
            if 'league-contained' in target.flags:
                league_name = None
            else:
                league_name = self._find_name(league, language)
                target = target.flags_union(('league-contained',))
            yield self.VerbatimBodyItem(
                self.constitute_section(
                    self._find_name(regatta, language),
                    league_name,
                    flags=target.flags )
            )
            target = target.flags_union(('contained',), overadd=False)
            target = target.flags_union(
                self.increase_containment(target.flags) )
        by_round = ( 'by-round' in target.flags or
            'by-subject' not in target.flags )

        if by_round:
            for roundnum in range(1, 1 + league['rounds']):
                yield target.path_derive(str(roundnum))
        else:
            for subjectkey in league['subjects']:
                yield target.path_derive(subjectkey)

    @ensure_tourn_flags
    @ensure_type_items((RegularDriver.MetabodyItem, Target))
    @processing_target
    def _generate_regatta_subject_matter(self, target, metarecord,
        *, regatta, league
    ):
        subject = self._find_regatta_subject(target.path, metarecord)
        if 'contest' not in target.flags:
            language = metarecord['$language']
            if 'league-contained' in target.flags:
                league_name = None
            else:
                league_name = self._find_name(league, language)
            yield self.VerbatimBodyItem(
                self.constitute_section(
                    self._find_name(regatta, language),
                    league_name,
                    self._find_name(subject, language),
                    flags=target.flags )
            )
        else:
            target = self.target_flags_contest_to_blank(target)
        if 'jury' in target.flags:
            target = self.target_flags_jury_to_complete(target)

        if 'blank' not in target.flags:
            yield self.VerbatimBodyItem(
                self.constitute_begin_tourn_problems(
                    target.flags.intersection(TOURN_PROBLEM_FLAGS) )
            )
            target = target.flags_union(('itemized',))
        for roundnum in range(1, 1 + league['rounds']):
            yield target.path_derive(str(roundnum))
        if 'blank' not in target.flags:
            yield self.VerbatimBodyItem(
                self.end_tourn_problems_template.substitute() )

    @ensure_tourn_flags
    @ensure_type_items((RegularDriver.MetabodyItem, Target))
    @processing_target
    def _generate_regatta_round_matter(self, target, metarecord,
        *, regatta, league
    ):
        regatta_round = self._find_regatta_round(target.path, metarecord)
        if 'contest' not in target.flags:
            language = metarecord['$language']
            if 'league-contained' in target.flags:
                league_name = None
            else:
                league_name = self._find_name(league, language)
            yield self.VerbatimBodyItem(
                self.constitute_section(
                    self._find_name(regatta, language),
                    league_name,
                    self._find_name(regatta_round, language),
                    flags=target.flags )
            )
        else:
            target = self.target_flags_contest_to_blank(target)
        if 'jury' in target.flags:
            target = self.target_flags_jury_to_complete(target)

        if 'blank' not in target.flags:
            yield self.VerbatimBodyItem(
                self.constitute_begin_tourn_problems(
                    target.flags.intersection(TOURN_PROBLEM_FLAGS) )
            )
            target = target.flags_union(('itemized',))
        for subjectkey in league['subjects']:
            yield target.path_derive('..', subjectkey, target.path.name)
        if 'blank' not in target.flags:
            yield self.VerbatimBodyItem(
                self.end_tourn_problems_template.substitute() )

    @ensure_tourn_flags
    @ensure_type_items((RegularDriver.MetabodyItem, Target))
    @processing_target
    def _generate_contest_problem_matter(self, target, metarecord,
        *, contest, league
    ):
        yield from self._generate_tourn_problem_matter(
            target, metarecord,
            number=target.path.name )

    @ensure_tourn_flags
    @ensure_type_items((RegularDriver.MetabodyItem, Target))
    @processing_target
    def _generate_regatta_problem_matter(self, target, metarecord,
        *, regatta, league
    ):
        subject = self._find_regatta_subject(target.path, metarecord)
        regatta_round = self._find_regatta_round(target.path, metarecord)
        if 'blank' in target.flags:
            assert 'itemized' not in target.flags
            assert 'league-contained' in target.flags
            yield self.VerbatimBodyItem(
                self.regatta_blank_caption_template.substitute(
                    caption=self._find_name(regatta, metarecord['$language']),
                    mark=regatta_round['mark'] )
            )
        if 'blank' in target.flags:
            subtarget = target.flags_union({'problems'})
        else:
            subtarget = target
        assert subtarget.flags.intersection(TOURN_PROBLEM_FLAGS)
        yield from self._generate_tourn_problem_matter(
            subtarget, metarecord,
            number=self.regatta_number_template.substitute(
                subject_index=subject['index'],
                round_index=regatta_round['index'] )
        )
        if 'blank' in target.flags:
            yield self.VerbatimBodyItem(
                self.hrule_template.substitute() )
            yield self.ClearPageBodyItem()

    class ProblemBodyItem(RegularDriver.SourceBodyItem):
        __slots__ = ['number']

        def __init__(self, metapath, number):
            super().__init__(metapath=metapath)
            self.number = number

    @ensure_type_items((RegularDriver.MetabodyItem, Target))
    @processing_target
    def _generate_tourn_problem_matter(self, target, metarecord,
        *, number
    ):
        has_criteria = ( 'with-criteria' in target.flags and
            '$criteria' in metarecord )
        has_problem_source = (
            'without-problem-sources' not in target.flags and
            '$problem-source' in metarecord )
        has_problem_source_www = (
            'without-problem-sources' not in target.flags and
            '$problem-source$www' in metarecord )
        itemized = 'itemized' in target.flags
        if not itemized:
            yield self.VerbatimBodyItem(
                self.constitute_begin_tourn_problems(
                    target.flags.intersection(TOURN_PROBLEM_FLAGS) )
            )
        yield self.ProblemBodyItem(metapath=target.path, number=number)
        if has_criteria:
            yield self.VerbatimBodyItem(
                self.criteria_template.substitute(
                    criteria=metarecord['$criteria'] )
            )
        if has_problem_source:
            yield self.VerbatimBodyItem(
                self.problem_source_template.substitute(
                    source=metarecord['$problem-source'] )
            )
        if has_problem_source and has_problem_source_www:
            yield self.VerbatimBodyItem(r'\par')
        if has_problem_source_www:
            yield self.VerbatimBodyItem(
                self.problem_source_www_template.substitute(
                    source=metarecord['$problem-source$www'] )
            )
        if not itemized:
            yield self.VerbatimBodyItem(
                self.end_tourn_problems_template.substitute() )

    def _find_contest(self, metapath, metarecord=None):
        if metarecord is None:
            metarecord = self.get(metapath)
        contest_key = metarecord['$contest$key']
        if contest_key == '$contest':
            return metarecord[contest_key]
        elif contest_key in {'$contest$league', '$contest$problem'}:
            return self._find_contest(metapath.parent)
        else:
            raise RuntimeError

    def _find_regatta(self, metapath, metarecord=None):
        if metarecord is None:
            metarecord = self.get(metapath)
        regatta_key = metarecord['$regatta$key']
        if regatta_key == '$regatta':
            return metarecord[regatta_key]
        elif regatta_key in { '$regatta$league',
            '$regatta$subject', '$regatta$round', '$regatta$problem'
        }:
            return self._find_regatta(metapath.parent)
        else:
            raise RuntimeError

    def _find_league(self, metapath, metarecord=None):
        if metarecord is None:
            metarecord = self.get(metapath)
        tourn_key = metarecord['$tourn$key']
        if tourn_key in {'$contest$league', '$regatta$league'}:
            return metarecord[tourn_key]
        elif tourn_key in { '$contest$problem',
            '$regatta$subject', '$regatta$round', '$regatta$problem'
        }:
            return self._find_league(metapath.parent)
        else:
            raise RuntimeError

    def _find_regatta_subject(self, metapath, metarecord=None):
        if metarecord is None:
            metarecord = self.get(metapath)
        regatta_key = metarecord['$regatta$key']
        if regatta_key == '$regatta$subject':
            return metarecord['$regatta$subject']
        elif regatta_key == '$regatta$problem':
            return self._find_regatta_subject(metapath.parent)
        else:
            raise RuntimeError

    def _find_regatta_round(self, metapath, metarecord=None):
        if metarecord is None:
            metarecord = self.get(metapath)
        regatta_key = metarecord['$regatta$key']
        if regatta_key == '$regatta$round':
            return metarecord['$regatta$round']
        elif regatta_key == '$regatta$problem':
            return self._find_regatta_round(
                metapath.parent.parent/metapath.name)
        else:
            raise RuntimeError

    def _find_name(self, entity, language):
        name = entity['name']
        if isinstance(name, str):
            return name
        elif isinstance(name, dict):
            (key, value), = name.items()
            if key == 'translate':
                return self.translations[value][language]
            else:
                raise ValueError(name)
        else:
            raise TypeError(name)

    ##########
    # Record extension

    def _derive_record(self, parent_record, child_record, path):
        super()._derive_record(parent_record, child_record, path)
        child_record.setdefault('$language', parent_record.get('$language'))
        if '$contest$league' in parent_record:
            child_record['$contest$problem'] = {}
        if '$regatta$subject' in parent_record:
            child_record['$regatta$problem'] = {}

        contest_keys = TOURN_CONTEST_KEYS.intersection(child_record.keys())
        if contest_keys:
            contest_key, = contest_keys
            child_record['$contest$key'] = contest_key
        else:
            contest_key = None

        regatta_keys = TOURN_REGATTA_KEYS.intersection(child_record.keys())
        if regatta_keys:
            regatta_key, = regatta_keys
            child_record['$regatta$key'] = regatta_key
        else:
            regatta_key = None

        if contest_key and regatta_key:
            raise ValueError(child_record.keys())

        tourn_key = contest_key or regatta_key
        if not tourn_key:
            return
        if path.is_root():
            raise DriverError
        child_record['$tourn$key'] = tourn_key
        tourn_entity = child_record[tourn_key] = \
            child_record[tourn_key].copy()
        tourn_entity['metaname'] = path.name


    ##########
    # LaTeX-level functions

    # Extenstion
    @classmethod
    def _constitute_body_item(cls, item):
        if isinstance(item, cls.ProblemBodyItem):
            return cls._constitute_body_problem(
                alias=item.alias, number=item.number,
                figure_map=item.figure_map,
                metapath=item.metapath, inpath=item.inpath, )
        return super()._constitute_body_item(item)

    # Extension
    @classmethod
    def _constitute_body_problem( cls, *,
        alias, number, figure_map, metapath, inpath
    ):
        assert number is not None
        body = cls.tourn_problem_template.substitute(
            number=number, filename=alias,
            inpath=inpath, metapath=metapath )
        if figure_map:
            body = cls._constitute_figure_map(figure_map) + '\n' + body
        return body

    tourn_problem_template = Template(
        r'\tournproblem{$number}%' '\n'
        r'\input{$filename}% $metapath' )

    @classmethod
    def constitute_section(cls, *names, flags):
        try:
            select, = flags.intersection(
                ('problems', 'solutions', 'complete', 'jury',) )
        except ValueError as exc:
            assert isinstance(flags, FlagContainer), type(flags)
            exc.args += (flags.as_set(),)
            raise
        names = [name for name in names if name is not None]
        caption = names[-1]
        if 'subsubcontained' in flags:
            section_template = cls.subsubsection_template
        elif 'subcontained' in flags:
            section_template = cls.subsection_template
        else:
            section_template = cls.section_template
        if 'contained' not in flags:
            caption = '. '.join(names) + cls.caption_select_appendage[select]
        return section_template.substitute(caption=caption)

    section_template = Template(
        r'\section*{$caption}' )
    subsection_template = Template(
        r'\subsection*{$caption}' )
    subsubsection_template = Template(
        r'\subsubsection*{$caption}' )
    caption_select_appendage = {
        'problems' : '',
        'solutions' : ' (решения)',
        'complete' : ' (с решениями)',
        'jury' : ' (версия для жюри)',
    }

    @classmethod
    def constitute_begin_tourn_problems(cls, tourn_flags):
        select, = tourn_flags
        assert select in {'problems', 'solutions', 'complete'}
        return cls.begin_tourn_problems_template.substitute(select=select)

    league_def_template = Template(
        r'\def\jeolmleague{$league}' )

    begin_tourn_problems_template = Template(
        r'\begin{tourn-problems}{$select}' )
    end_tourn_problems_template = Template(
        r'\end{tourn-problems}' )
    briefing_template = Template(
        r'\briefing' )

    regatta_blank_caption_template = Template(
        r'\regattablankcaption{$caption}{$mark}' )
    hrule_template = Template(
        r'\medskip\hrule' )

    regatta_number_template = Template(
        r'$round_index$subject_index' )

    criteria_template = Template(
        r'\emph{Критерии: $criteria}\par' )
    problem_source_template = Template( r''
        r'\nopagebreak'
        r'\vspace{-1ex}\begingroup'
            r'\hfill\itshape\small($source' '%\n'
        r')\endgroup'
    )
    problem_source_www_template = Template( r''
        r'\nopagebreak'
        r'\vspace{-1ex}\begingroup'
            r'\hfill\itshape\small $source' '%\n'
        r'\endgroup'
    )

    ##########
    # Supplementary finctions

    @staticmethod
    def increase_containment(flags):
        if 'subcontained' not in flags:
            yield 'subcontained'
        elif 'subsubcontained' not in flags:
            yield 'subsubcontained'
        else:
            raise ValueError(flags)


