from .generic import Driver, DriverError

import logging
logger = logging.getLogger(__name__)

class TestPaperDriver(Driver):
    @processing_target(aspect='tex matter', wrap_generator=True)
    @classify_items(aspect='matter', default='verbatim')
    def generate_tex_matter(self, target, metarecord):
        super_matter = super().generate_tex_matter(target, metarecord)
        if 'no-header' not in target.flags:
            yield from super_matter
            return
        if metarecord.get('$test', False):
            if 'exclude-test' in target.flags:
                return
            yield self.substitute_begingroup()
            yield self.substitute_interrobang_section()
            yield from super_matter
            yield from self.generate_test_postword(target, metarecord)
            yield self.substitute_endgroup()
        else:
            yield from super_matter

    begingroup_template = r'\begingroup'
    endgroup_template = r'\endgroup'
    interrobang_section_template = (
        r'\let\oldsection\section'
        r'\def\section#1#2{\oldsection#1{\textinterrobang\ #2}}' )

    @processing_target(aspect='test postword', wrap_generator=True)
    @classify_items(aspect='matter', default='verbatim')
    def generate_test_postword(self, target, metarecord):
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
        yield {'verbatim' : self.substitute_begin_postword()}
        postword_items = []
        if has_problem_scores:
            postword_items.append(
                self.constitute_problem_scores(problem_scores) )
        if has_mark_limits:
            postword_items.append(
                self.constitute_mark_limits(mark_limits) )
        if has_test_duration:
            postword_items.append(
                self.constitute_test_duration(test_duration) )
        need_newline = False
        for item in postword_items:
            if need_newline:
                yield {'verbatim' : '\\\\'}
            yield {'verbatim' : item}
            need_newline = True
        yield {'verbatim' : self.substitute_end_postword()}

    begin_postword_template = r'\begin{flushright}\scriptsize'
    end_postword_template = r'\end{flushright}'

    @classmethod
    def constitute_problem_scores(cls, problem_scores):
        score_items, score_sum = cls.flatten_score_items(problem_scores)
        return r'\({} = {}\)%'.format(''.join(score_items), score_sum)

    @classmethod
    def flatten_score_items(cls, problem_scores, recursed=False):
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
                subitems, subsum = cls.flatten_score_items(item, recursed=True)
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
    def constitute_mark_limits(cls, mark_limits):
        return r'\({}\)%'.format(',\ '.join(
            r'{score} \mapsto \mathbf{{{mark}}}'.format(mark=mark, score=score)
            for mark, score in sorted(mark_limits.items())
        ))

    @classmethod
    def constitute_test_duration(cls, test_duration):
        if isinstance(test_duration, (int, float)):
            return '{}m'.format(test_duration)
        elif isinstance(test_duration, list):
            duration, unit = test_duration
            return '{} {}'.format(duration, unit)
        else:
            return str(test_duration)

