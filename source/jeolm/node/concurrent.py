from functools import partial

import threading
import queue

from . import NodeUpdater, NodeErrorReported, BuildableNode

class ConcurrentNodeUpdater(NodeUpdater):

    def __init__(self, *, jobs):
        super().__init__()
        if not isinstance(jobs, int):
            raise TypeError(type(jobs))
        if jobs < 1:
            raise ValueError(jobs)
        self.jobs = jobs

    def _update_added_nodes(self):
        updates_threads = dict()
        updates_finished = queue.Queue()
        error_occured = False
        while (not error_occured and self.ready_nodes) or updates_threads:

            have_to_wait = ( len(updates_threads) >= self.jobs or
                (error_occured or not self.ready_nodes) )
            if have_to_wait:
                node, exception = updates_finished.get()
                updates_threads.pop(node).join()
                if exception is not None:
                    try:
                        raise exception
                    except NodeErrorReported:
                        pass
                    error_occured = True
                else:
                    self._update_node_finish(node)
                continue

            node = self._pop_ready_node()
            if ( not isinstance(node, BuildableNode) or
                not node.wants_concurrency
            ):
                try:
                    self._update_node_self(node)
                except NodeErrorReported:
                    error_occured = True
                else:
                    self._update_node_finish(node)
                continue

            thread = updates_threads[node] = threading.Thread(target=partial(
                self._update_node_self_put, node, updates_finished
            ))
            thread.start()

        if error_occured:
            raise NodeErrorReported
        self._check_finished_update()

    def _update_node_self_put(self, node, updates_finished):
        try:
            self._update_node_self(node)
        except Exception as exception: # pylint: disable=broad-except
            updates_finished.put((node, exception))
        else:
            updates_finished.put((node, None))

