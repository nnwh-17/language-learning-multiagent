"""Live record of which agents/resources are working, for the architecture side panel.

Agents and tools mark themselves with `with track("analyzer"): ...`. The web UI runs the
orchestrator through `Activity.watch()` and re-renders the panel on every change. Outside
of `watch()` (terminal chat, scripts) `track` does nothing.
"""

import asyncio
from collections import Counter
from collections.abc import AsyncIterator, Coroutine, Iterable
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from jplearn.architecture import Status

_current: ContextVar["Activity | None"] = ContextVar("activity", default=None)


@contextmanager
def track(*node_ids: str):
    """Mark architecture nodes (ids from jplearn.architecture) as running inside this block."""
    activity = _current.get()
    if activity is None:
        yield
        return
    activity._update(node_ids, +1)
    try:
        yield
    finally:
        activity._update(node_ids, -1)


class Activity:
    """Statuses of the architecture nodes during one orchestrator run."""

    def __init__(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._running: Counter[str] = Counter()  # a node can run several times at once
        self._done: set[str] = set()
        self._changed = asyncio.Event()
        self.result: Any = None

    def status(self) -> dict[str, Status]:
        status: dict[str, Status] = {node_id: "done" for node_id in self._done}
        status |= {node_id: "running" for node_id, n in self._running.items() if n}
        return status

    def _update(self, node_ids: Iterable[str], delta: int) -> None:
        # Sync tools run in a worker thread, so apply the change on the event loop's thread
        self._loop.call_soon_threadsafe(self._apply, tuple(node_ids), delta)

    def _apply(self, node_ids: tuple[str, ...], delta: int) -> None:
        for node_id in node_ids:
            self._running[node_id] += delta
            if not self._running[node_id]:
                self._done.add(node_id)
        self._changed.set()

    async def watch(self, coro: Coroutine) -> AsyncIterator[dict[str, Status]]:
        """Run `coro`, yielding the statuses each time they change. Its return value ends
        up in `self.result` (exceptions are re-raised)."""
        token = _current.set(self)
        try:
            task = asyncio.create_task(coro)  # the task copies the context, so it sees `self`
        finally:
            _current.reset(token)

        while not task.done():
            self._changed.clear()
            yield self.status()
            changed = asyncio.create_task(self._changed.wait())
            await asyncio.wait([task, changed], return_when=asyncio.FIRST_COMPLETED)
            changed.cancel()

        await asyncio.sleep(0)  # let updates scheduled by the last tool calls land
        self.result = task.result()
        yield self.status()
