# Imports and logging {{{1

import io
import os
import fcntl
import selectors
import subprocess

from . import NodeErrorReported

class _NodeMap: # {{{1

    def __init__(self):
        super().__init__()
        self.needs_map = dict()
        self.revneeds_map = dict()
        self.ready_nodes = set()

    def clear(self):
        """Must be called before reusing the map."""
        self.needs_map.clear()
        self.revneeds_map.clear()
        self.ready_nodes.clear()

    def add_node(self, node, *, _rev_need=None):
        assert not node.updated
        try:
            rev_needs = self.revneeds_map[node]
        except KeyError:
            already_added = False
            rev_needs = self.revneeds_map[node] = set()
        else:
            already_added = True
        if _rev_need is not None:
            rev_needs.add(_rev_need)
        if already_added:
            return
        else:
            self._readd_node(node)

    def _readd_node(self, node):
        assert node not in self.needs_map
        assert node not in self.ready_nodes
        needs = self.needs_map[node] = set()
        for need in node.needs:
            if need.updated:
                continue
            self.add_node(need, _rev_need=node)
            needs.add(need)
        if not needs:
            self.ready_nodes.add(node)

    def pop_ready_node(self):
        node = self.ready_nodes.pop()
        if self.needs_map.pop(node):
            raise RuntimeError
        return node

    def finish_node(self, node):
        if node.updated:
            # pop node from the need maps
            for revneed in self.revneeds_map.pop(node):
                revneed_needs = self.needs_map[revneed]
                assert node in revneed_needs
                revneed_needs.discard(node)
                if not revneed_needs:
                    self.ready_nodes.add(revneed)
        else:
            self._readd_node(node)

    def check_finished_update(self):
        if self.needs_map:
            raise RuntimeError( "Node dependencies formed a cycle:\n{}"
                .format('\n'.join(
                    repr(node) for node in self._find_needs_cycle()
                )) )
        if self.revneeds_map:
            raise RuntimeError

    def _find_needs_cycle(self):
        seen_nodes_map = dict()
        seen_nodes_list = list()
        assert self.needs_map
        node = next(iter(self.needs_map)) # arbitrary node
        while True:
            if node in seen_nodes_map:
                return seen_nodes_list[seen_nodes_map[node]:]
            seen_nodes_map[node] = len(seen_nodes_list)
            seen_nodes_list.append(node)
            assert self.needs_map[node]
            node = next(iter(self.needs_map[node]))

class NodeUpdater: # {{{1

    def __init__(self, *, jobs):
        super().__init__()
        if not isinstance(jobs, int):
            raise TypeError(type(jobs))
        if jobs < 1:
            raise ValueError(jobs)
        self.jobs = jobs
        self._node_map = None
        self._running_processes = None
        self._paused_coroutines = None
        self._error_occurred = None

    def update(self, node):
        if node.updated:
            return
        self._node_map = _NodeMap()
        self._node_map.add_node(node)
        # { node: (coroutine, process, pipe, output) }
        self._running_processes = {}
        # { node: (coroutine, value, exception) }
        self._paused_coroutines = {}
        self._error_occurred = False

        while True:
            if self._paused_coroutines:
                self._run_paused()
            elif ( len(self._running_processes) < self.jobs and
                    not self._error_occurred and self._node_map.ready_nodes ):
                node = self._node_map.pop_ready_node()
                # pylint: disable=assignment-from-no-return
                coroutine = self._ready_node_update(node)
                # pylint: enable=assignment-from-no-return
                self._paused_coroutines[node] = (coroutine, None, None)
            elif self._running_processes:
                self._wait_running()
            else:
                break
        if self._error_occurred:
            raise NodeErrorReported
        self._node_map.check_finished_update()

    def _run_paused(self):
        node, (coroutine, value, exception) = \
            self._paused_coroutines.popitem()
        try:
            if exception is None:
                command = coroutine.send(value)
            else:
                command = coroutine.throw(type(exception), exception)
        except StopIteration:
            self._node_map.finish_node(node)
        except NodeErrorReported:
            self._error_occurred = True
        else:
            process = subprocess.Popen(
                command.callargs, cwd=str(command.cwd),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                **command.kwargs )
            pipe = process.stdout
            pipe_fd = pipe.fileno()
            pipe_fl = fcntl.fcntl(pipe_fd, fcntl.F_GETFL)
            fcntl.fcntl( pipe_fd, fcntl.F_SETFL,
                pipe_fl | os.O_NONBLOCK )
            output = io.BytesIO()
            self._running_processes[node] = \
                (coroutine, process, pipe, output)

    def _wait_running(self):
        output_sel = selectors.DefaultSelector()
        for node, (coroutine, process, pipe, output) in \
                self._running_processes.items():
            output_sel.register(pipe, selectors.EVENT_READ, data=node)
        for key, events in output_sel.select():
            assert events == selectors.EVENT_READ
            node = key.data
            coroutine, process, pipe, output = self._running_processes[node]
            output_piece = pipe.read()
            if output_piece:
                output.write(output_piece)
            else:
                pipe.close()
                process.wait()
                del self._running_processes[node]
                output_bytes = output.getvalue()
                if process.returncode == 0:
                    self._paused_coroutines[node] = \
                        (coroutine, output_bytes, None)
                else:
                    exception = subprocess.CalledProcessError(
                        process.returncode, process.args,
                        output_bytes, None )
                    self._paused_coroutines[node] = \
                        (coroutine, None, exception)

    @staticmethod
    async def _ready_node_update(node):
        try:
            assert not node.updated
            assert all(need.updated for need in node.needs)
            await node.update_self()
        except NodeErrorReported:
            raise
        except Exception as exception:
            node.logger.exception("Exception occured:")
            raise NodeErrorReported from exception

# }}}1
# vim: set foldmethod=marker :
