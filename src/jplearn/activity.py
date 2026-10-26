"""Live record of what the agents are doing, for the web UI's architecture panel and log.

Two ways things get recorded:
- Every agent has the `Observe` capability, a PydanticAI hook that logs its run, each LLM
  call and each tool call, and marks the agent as running in the architecture panel.
- Tool and MCP nodes (tokenizer, dictionary, Anki MCP) mark themselves with `with track("jmdict"): ...`.

Entries nest: anything that happens inside an agent run or tool call is logged one level
deeper. The web UI runs the orchestrator through `Activity.watch()` and re-renders on every
change. Outside of `watch()` (terminal chat, scripts) nothing is recorded.
"""

import asyncio
import itertools
import time
from collections import Counter
from collections.abc import AsyncIterator, Coroutine, Iterable
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability

from jplearn.architecture import Status, all_nodes

_current: ContextVar["Activity | None"] = ContextVar("activity", default=None)
_parent: ContextVar["LogEntry | None"] = ContextVar("activity_parent", default=None)
_ids = itertools.count()

# Event kinds are shared with the web activity-log renderer.
EntryKind = Literal["user", "agent", "llm", "tool", "resource", "info", "error"]


@dataclass
class LogEntry:
    time: float  # time.time() when it started
    depth: int
    kind: EntryKind
    text: str
    detail: str = ""
    status: Literal["running", "done", "error", "info"] = "info"
    duration: float | None = None
    parent: int | None = None  # id of the enclosing entry; parallel work interleaves in time
    id: int = field(default_factory=lambda: next(_ids))


def tree_order(entries: list[LogEntry]) -> list[LogEntry]:
    """Entries with each one's children directly below it (in start order), so parallel
    tool calls don't interleave."""
    # Rebuild parent-child grouping so concurrent operations display as nested branches.
    known = {entry.id for entry in entries}
    children: dict[int | None, list[LogEntry]] = {}
    for entry in entries:
        children.setdefault(entry.parent if entry.parent in known else None, []).append(entry)

    ordered: list[LogEntry] = []

    def visit(parent: int | None) -> None:
        for entry in children.get(parent, []):
            ordered.append(entry)
            visit(entry.id)

    visit(None)
    return ordered


def is_output_tool(tool_name: str) -> bool:
    """Whether a tool call is PydanticAI returning structured output, not a real tool."""
    return tool_name.startswith("final_result")


def _short(value: Any, limit: int = 70) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


class Activity:
    """Statuses of the architecture nodes and the log for one orchestrator run."""

    def __init__(self, log: list[LogEntry] | None = None) -> None:
        self._loop = asyncio.get_running_loop()
        self._running: Counter[str] = Counter()  # a node can run several times at once
        self._done: set[str] = set()
        self._changed = asyncio.Event()
        self.log = log if log is not None else []
        self.result: Any = None

    def status(self) -> dict[str, Status]:
        # Running takes precedence if a node has both completed and active parallel work.
        status: dict[str, Status] = {node_id: "done" for node_id in self._done}
        status |= {node_id: "running" for node_id, n in self._running.items() if n}
        return status

    # Hooks and tools may run in worker threads (sync tools), so every change is applied
    # on the event loop's thread.
    def _post(self, fn, *args) -> None:
        self._loop.call_soon_threadsafe(self._apply, fn, args)

    def _apply(self, fn, args) -> None:
        fn(*args)
        self._changed.set()

    def _set_running(self, node_ids: Iterable[str], delta: int) -> None:
        for node_id in node_ids:
            self._running[node_id] += delta
            if not self._running[node_id]:
                self._done.add(node_id)

    def add(self, kind: EntryKind, text: str, detail: str = "") -> LogEntry:
        parent = _parent.get()
        depth = 0 if parent is None else parent.depth + 1
        entry = LogEntry(time.time(), depth, kind, text, detail, parent=parent and parent.id)
        self._post(self.log.append, entry)
        return entry

    async def watch(self, coro: Coroutine) -> AsyncIterator[dict[str, Status]]:
        """Run `coro`, yielding the statuses each time anything changes. Its return value
        ends up in `self.result` (exceptions are re-raised)."""
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


@contextmanager
def span(kind: EntryKind, text: str, node_ids: Iterable[str] = ()):
    """Log `text`, mark `node_ids` as running, and log everything inside one level deeper.
    Yields the log entry (or None when nothing is being recorded) so details can be added."""
    # Outside Activity.watch(), instrumentation is intentionally a no-op.
    activity = _current.get()
    if activity is None:
        yield None
        return
    node_ids = tuple(node_ids)
    entry = activity.add(kind, text)
    entry.status = "running"
    activity._post(activity._set_running, node_ids, +1)
    token = _parent.set(entry)
    try:
        yield entry
    except BaseException as e:
        entry.status = "error"
        entry.detail = _short(f"{type(e).__name__}: {e}", 160)
        raise
    else:
        entry.status = "done"
    finally:
        _parent.reset(token)
        entry.duration = time.time() - entry.time
        activity._post(activity._set_running, node_ids, -1)


@contextmanager
def track(node_id: str):
    """Mark a tool or MCP node from jplearn.architecture (e.g. "jmdict") as in use inside
    this block. It is logged as a "resource" entry, to tell it apart from an agent's tool call."""
    with span("resource", all_nodes()[node_id].label, [node_id]):
        yield


def log(kind: EntryKind, text: str, detail: str = "") -> None:
    """Add a one-off entry to the log (no-op when nothing is being recorded)."""
    if (activity := _current.get()) is not None:
        activity.add(kind, text, detail)


@dataclass
class Observe(AbstractCapability[Any]):
    """Logs an agent's run, LLM calls and tool calls, and marks its node in the panel.

    `node_id` is the agent's id in jplearn.architecture."""

    node_id: str

    @classmethod
    def get_serialization_name(cls) -> str | None:
        return None

    async def wrap_run(self, ctx: RunContext, *, handler):
        label = all_nodes()[self.node_id].label
        with span("agent", label, [self.node_id]) as entry:
            if entry and isinstance(ctx.prompt, str):
                entry.detail = _short(ctx.prompt)
            return await handler()

    async def wrap_model_request(self, ctx: RunContext, *, request_context, handler):
        # Record token use and tool requests alongside the model call in the activity tree.
        with span("llm", f"LLM call #{ctx.run_step}") as entry:
            response = await handler(request_context)
            if entry:
                usage = response.usage
                calls = [
                    "answer" if is_output_tool(p.tool_name) else p.tool_name
                    for p in response.parts
                    if p.part_kind == "tool-call"
                ]
                wants = f" → {', '.join(calls)}" if calls else ""
                entry.detail = f"{usage.input_tokens} in / {usage.output_tokens} out tokens{wants}"
            return response

    async def wrap_tool_execute(self, ctx: RunContext, *, call, tool_def, args, handler):
        if is_output_tool(call.tool_name):
            return await handler(args)
        with span("tool", call.tool_name) as entry:
            if entry:
                entry.detail = _short(call.args_as_dict())
            return await handler(args)
