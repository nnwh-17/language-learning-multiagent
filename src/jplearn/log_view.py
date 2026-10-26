"""Render the nested activity events produced by ``activity.py`` as chat HTML.

The web frontend refreshes this view as agent, model, tool, and resource spans change.
"""

import html
import time

from jplearn.activity import LogEntry, tree_order

MAX_ROWS = 400

BADGES = {
    "user": "YOU",
    "agent": "AGENT",
    "llm": "LLM",
    "tool": "TOOL",
    "resource": "RES",
    "info": "INFO",
    "error": "ERROR",
}

CSS = """
.alog { max-height: 340px; overflow-y: auto; display: flex; flex-direction: column-reverse;
  font-family: var(--font-mono); font-size: 12px; line-height: 1.4;
  border: 1px solid var(--border-color-primary); border-radius: 6px; padding: 6px 8px;
  background: var(--block-background-fill); color: var(--body-text-color); }
.alog .empty { color: var(--body-text-color-subdued); }
.alog .row { padding: 1px 0 1px 6px; }
.alog .row.k-user { margin-top: 8px; padding-top: 6px; border-top: 1px solid var(--border-color-primary); }
.alog .row.k-user:first-child { margin-top: 0; border-top: none; }
.alog .nest { display: inline-block; width: 14px; height: 1.4em; vertical-align: top;
  border-left: 1px solid var(--border-color-primary); }
.alog .t { color: var(--body-text-color-subdued); margin-right: 8px; }
.alog .badge { display: inline-block; min-width: 46px; text-align: center; font-size: 10px;
  border-radius: 4px; padding: 0 4px; margin-right: 6px; border: 1px solid var(--border-color-primary);
  color: var(--body-text-color-subdued); }
.alog .k-agent .badge { border-color: var(--color-accent); color: var(--color-accent); font-weight: 600; }
.alog .k-agent .txt { font-weight: 600; }
.alog .k-llm .badge { background: var(--color-accent-soft); color: var(--body-text-color); border-color: transparent; }
.alog .k-user .badge { background: var(--color-accent); color: white; border-color: transparent; }
.alog .k-error .badge, .alog .s-error .badge { border-color: var(--error-border-color, #ef4444); color: var(--error-text-color, #ef4444); }
.alog .dur { color: var(--body-text-color-subdued); margin-left: 8px; }
.alog .s-running .dur { color: var(--color-accent); animation: alog-pulse 1.2s ease-in-out infinite; }
.alog .s-error .dur, .alog .s-error .detail, .alog .k-error .detail { color: var(--error-text-color, #ef4444); }
.alog .detail { color: var(--body-text-color-subdued); margin-left: 6px; }
@keyframes alog-pulse { 50% { opacity: 0.4; } }
"""


def _row(entry: LogEntry) -> str:
    e = html.escape
    clock = time.strftime("%H:%M:%S", time.localtime(entry.time))
    # Show elapsed duration or failure state beside each event.
    if entry.status == "running":
        dur = "running…"
    elif entry.status == "error":
        dur = f"failed after {entry.duration:.1f}s" if entry.duration is not None else "failed"
    elif entry.duration is not None:
        dur = f"{entry.duration:.1f}s"
    else:
        dur = ""
    # Each nesting level is a left border, so the levels line up like a tree
    indent = "".join("<span class='nest'></span>" for _ in range(entry.depth))
    detail = f"<span class='detail'>{e(entry.detail)}</span>" if entry.detail else ""
    return (
        f"<div class='row k-{entry.kind} s-{entry.status}'>"
        f"<span class='t'>{clock}</span>{indent}"
        f"<span class='badge'>{BADGES[entry.kind]}</span><span class='txt'>{e(entry.text)}</span>"
        f"<span class='dur'>{dur}</span>{detail}</div>"
    )


def render_log(entries: list[LogEntry]) -> str:
    # Bound the view size, and reorder parallel events into their parent-child tree.
    rows = "".join(_row(entry) for entry in tree_order(entries[-MAX_ROWS:]))
    body = rows or "<div class='empty'>Nothing yet. Send a message to see the agents at work.</div>"
    # column-reverse keeps the box scrolled to the newest entry; the inner div keeps the order
    return f"<style>{CSS}</style><div class='alog'><div>{body}</div></div>"
