"""
Keys recognized in metarecords:
  $test
  $test$problem-scores
  $test$mark-limits
  $test$duration
"""

from string import Template

from jeolm.target import Target

from jeolm.driver.regular import RegularDriver

from . import DriverError, processing_target, ensure_type_items

import logging
logger = logging.getLogger(__name__)


class TestDriver(RegularDriver):

    @ensure_type_items((RegularDriver.MetabodyItem, Target))
    @processing_target
    def _generate_source_metabody(self, target, metarecord):
        no_postword = (
            not metarecord.get('$test', False) or
            'no-test-postword' in target.flags )
        if no_postword:
            yield from super()._generate_source_metabody(target, metarecord)
            return

        yield target.flags_union({'no-test-postword'})
        yield from self._generate_test_postword(target, metarecord)

    @ensure_type_items((RegularDriver.MetabodyItem))
    @processing_target
    def _generate_test_postword(self, target, metarecord):
        problem_scores = metarecord.get('$test$problem-scores')
        mark_limits = metarecord.get('$test$mark-limits')
        test_duration = metarecord.get('$test$duration')
        has_problem_scores = ( problem_scores is not None and
            'no-problem-scores' not in target.flags )
        has_mark_limits = ( has_problem_scores and
            mark_limits is not None and
            'no-mark-limits' not in target.flags )
        has_test_duration = ( test_duration is not None and
            'no-test-duration' not in target.flags )
        if not has_problem_scores and not has_test_duration:
            return # no-op
        yield self.VerbatimBodyItem(
            self.begin_postword_template.substitute() )
        postword_items = []
        if has_problem_scores:
            postword_items.append(
                self._constitute_problem_scores(problem_scores) )
        if has_mark_limits:
            postword_items.append(
                self._constitute_mark_limits(mark_limits) )
        if has_test_duration:
            postword_items.append(
                self._constitute_test_duration(test_duration) )
        need_newline = False
        for item in postword_items:
            if need_newline:
                yield self.VerbatimBodyItem('\\\\')
            yield self.VerbatimBodyItem(item)
            need_newline = True
        yield self.VerbatimBodyItem(
            self.end_postword_template.substitute() )

    begin_postword_template = Template(
        r'\begin{flushright}\scriptsize' )
    end_postword_template = Template(
        r'\end{flushright}' )

    @classmethod
    def _constitute_problem_scores(cls, problem_scores):
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
                subitems, subsum = cls._flatten_score_items(item, recursed=True)
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
    def _constitute_mark_limits(cls, mark_limits):
        return r'\({}\)%'.format(r',\ '.join(
            r'{score} \mapsto \mathbf{{{mark}}}'.format(mark=mark, score=score)
            for mark, score in sorted(mark_limits.items())
        ))

    @classmethod
    def _constitute_test_duration(cls, test_duration):
        if isinstance(test_duration, (int, float)):
            return '{}m'.format(test_duration)
        elif isinstance(test_duration, list):
            duration, unit = test_duration
            return '{} {}'.format(duration, unit)
        else:
            return str(test_duration)

