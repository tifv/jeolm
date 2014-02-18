from functools import partial

from ..target import Target
from .base import BaseDriver, DriverError

class DelegatingDriver(BaseDriver):

    ##########
    # High-level functions
    # (not dealing with metarecords and LaTeX strings directly)

    @checking_target_recursion
    @processing_target_aspect(aspect='delegation', wrap_generator=True)
    def trace_delegators(self, target, *, seen_targets):
        """Yield targets."""
        try:
            for item in self.generate_delegators(target):
                if isinstance(item, Target):
                    yield from self.trace_delegators(item,
                        seen_targets=seen_targets )
                else:
                    raise RuntimeError(item)
        except self.NoDelegators:
            yield target


    ##########
    # Record-level functions

    @fetching_metarecord
    @processing_target_aspect(aspect='delegation', wrap_generator=True)
    def generate_delegators(self, target, metarecord):
        """Yield targets."""
        delegate_key, pre_delegators = self.select_flagged_item(
            metarecord, '$delegate', target.flags )
        if delegate_key is None:
            raise self.NoDelegators
        with self.process_target_key(target, delegate_key):
            if not isinstance(pre_delegators, list):
                raise DriverError(type(pre_delegators))
            derive_target = partial( target.derive_from_string,
                origin=lambda: (
                    'delegate {target:target}, key {key}'
                    .format(target=target, key=delegate_key)
                ) )
            for item in pre_delegators:
                if isinstance(item, str):
                    yield derive_target(item)
                    continue
                if not isinstance(item, dict):
                    raise DriverError(type(item))
                item = item.copy()
                condition = item.pop('condition', [])
                if not target.flags.check_condition(condition):
                    continue
                if item.keys() == {'delegate'}:
                    yield derive_target(target, item['delegate'])
                else:
                    raise DriverError(item)

