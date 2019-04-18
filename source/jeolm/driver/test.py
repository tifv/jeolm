r"""
Record keys recognized by the driver:
* $test
* $test$problem-scores
* $test$mark-limits
* $test$duration
"""

from string import Template

from jeolm.target import Target

from jeolm.driver.regular import RegularDriver

from . import DriverError, processing_target, ensure_type_items

import logging
logger = logging.getLogger(__name__)


class TestDriver(RegularDriver):

    @ensure_type_items(RegularDriver.BodyItem)
    @processing_target
    def _generate_body_auto( self, target, record,
        *, preamble, header_info,
        _seen_targets,
    ):
        if not record.get('$test', False) or \
                'contained' not in target.flags or \
                'no-test-guard' in target.flags:
            yield from super()._generate_body_auto( target, record,
                preamble=preamble, header_info=header_info,
                _seen_targets=_seen_targets )
            return
        target = target.flags_union({'no-test-guard'})
        yield from self._generate_body( target, record,
            preamble=preamble, header_info=header_info,
            _seen_targets=_seen_targets )
        yield from self._generate_test_briefing(target, record)

    @ensure_type_items((RegularDriver.BodyItem))
    @processing_target
    def _generate_test_briefing(self, target, metarecord):
        problem_scores = metarecord.get('$test$problem-scores')
        mark_limits = metarecord.get('$test$mark-limits')
        duration = metarecord.get('$test$duration')
        if problem_scores is None and mark_limits is None and duration is None:
            return # no-op
        yield self.VerbatimBodyItem(
            self.begin_briefing_template.substitute() )
        briefing_items = []
        if problem_scores is not None:
            briefing_items.append(
                self._constitute_test_problem_scores(problem_scores) )
        if mark_limits is not None:
            briefing_items.append(
                self._constitute_test_mark_limits(mark_limits) )
        if duration is not None:
            briefing_items.append(
                self._constitute_test_duration(duration) )
        need_newline = False
        for item in briefing_items:
            if need_newline:
                yield self.VerbatimBodyItem('\\\\')
            yield self.VerbatimBodyItem(item)
            need_newline = True
        yield self.VerbatimBodyItem(
            self.end_briefing_template.substitute() )

    begin_briefing_template = Template(
        r'\begin{flushright}\scriptsize' )
    end_briefing_template = Template(
        r'\end{flushright}' )

    @classmethod
    def _constitute_test_problem_scores(cls, problem_scores):
        score_items, score_sum = cls._flatten_score_items(problem_scores)
        return r'\({} = {}\)%'.format(''.join(score_items), score_sum)

    @classmethod
    def _flatten_score_items(cls, problem_scores, recursed=False):
        if isinstance(problem_scores, int):
            return [str(problem_scores)], problem_scores
        elif isinstance(problem_scores, dict):
            (key, value), = problem_scores.items()
            return str(key), int(value)
        elif isinstance(problem_scores, list):
            first = True
            score_items = []
            score_sum = 0
            if recursed:
                score_items.append('(')
            for item in problem_scores:
                if not first:
                    score_items.append('+')
                first = False
                subitems, subsum = \
                    cls._flatten_score_items(item, recursed=True)
                score_items.extend(subitems)
                score_sum += subsum
            if recursed:
                score_items.append(')')
            return score_items, score_sum
        else:
            raise DriverError(
                "Problem scores must be an int or a list of problem scores, "
                "found {}".format(type(problem_scores)) )

    @classmethod
    def _constitute_test_mark_limits(cls, mark_limits):
        return r'\({' + r',\ '.join(
            fr'{score} \mapsto \mathbf{{{mark}}}'
            for mark, score in sorted(mark_limits.items())
        ) + '}\)%'

    @classmethod
    def _constitute_test_duration(cls, duration):
        if isinstance(duration, (int, float)):
            return '{}m'.format(duration)
        elif isinstance(duration, list):
            duration, unit = duration
            return '{} {}'.format(duration, unit)
        else:
            return str(duration)

