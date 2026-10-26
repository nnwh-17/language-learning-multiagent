"""Run the Gradio chat interface for the jplearn orchestrator.

This frontend manages per-tab conversation and approval state, streams activity updates,
and provides controls for viewing the agent graph and editing saved learner context.
"""

import re
import time

import gradio as gr
from pydantic_ai import DeferredToolRequests, ToolDenied
from pydantic_ai.messages import ModelMessage

from jplearn import user_context
from jplearn.activity import Activity, LogEntry
from jplearn.agents.orchestrator import describe_approval, orchestrator, stream_reply, tools_used
from jplearn.architecture import Status, all_nodes, approval_targets, render_html
from jplearn.log_view import render_log
from jplearn.theme import CSS, THEME
from jplearn.user_context import AGENTS, ALL, ContextItem

NEW_ITEM = "➕ New item"


# What each orchestrator tool is called in the chat, e.g. analyze_japanese -> Analyzer
STEP_LABELS = {tool: child.label for tool, child in all_nodes()["orchestrator"].calls}

COMPOSER_HINTS = {
    "idle": "Ask anything, or paste Japanese text...",
    "busy": "Working on it...",
    "approval": "Approve or reject above, or reply to change the request...",
}

# Kanji followed by a hiragana reading in brackets, e.g. 食(た)べる or 日本語（にほんご）
FURIGANA = re.compile(r"([一-鿿々]+)[(（]([ぁ-ゖー]+)[)）]")


def with_furigana(markdown: str) -> str:
    """Show readings written as 漢字(かんじ) above the kanji instead of in brackets."""
    return FURIGANA.sub(r"<ruby>\1<rp>(</rp><rt>\2</rt><rp>)</rp></ruby>", markdown)


def steps_message(plan: list[str], tools: list[str], seconds: float) -> dict | None:
    """One collapsed "How I answered" message with the plan and the specialists used."""
    parts = []
    if plan:
        parts.append("\n".join(f"{i}. {step}" for i, step in enumerate(plan, 1)))
    if tools:
        used = dict.fromkeys(STEP_LABELS.get(tool, tool) for tool in tools)  # dedupe, keep order
        parts.append("**Used:** " + " → ".join(used))
    if not parts:
        return None
    return {
        "role": "assistant",
        "content": "\n\n".join(parts),
        "metadata": {"title": "How I answered", "status": "done", "duration": round(seconds, 1)},
    }


def progress_message(status: dict[str, Status]) -> dict:
    """Temporary message with a spinner naming what is running right now."""
    nodes = all_nodes()
    running = [nodes[n].label for n, s in status.items() if s == "running" and n != "orchestrator"]
    return {
        "role": "assistant",
        "content": "Open **Agents** on the right for every step.",
        "metadata": {
            "title": "Working: " + " · ".join(running) if running else "Thinking...",
            "status": "pending",
        },
    }


class LiveReply:
    """The reply so far while the orchestrator streams it, shown below the progress message."""

    MIN_INTERVAL = 0.05  # seconds between UI refreshes, so fast streams don't flood the browser

    def __init__(self, activity: Activity) -> None:
        self.text = ""
        self._activity = activity
        self._last_refresh = 0.0

    def update(self, text: str) -> None:
        self.text = text
        if time.time() - self._last_refresh >= self.MIN_INTERVAL:
            self._last_refresh = time.time()
            self._activity.notify()

    def message(self) -> list[dict]:
        return [{"role": "assistant", "content": with_furigana(self.text)}] if self.text else []


async def run_orchestrator(chat: list[dict], live: LiveReply, **run_kwargs):
    """Run the orchestrator, streaming its reply into `live`, and append its output to the chat.

    Returns (chat, history, pending) where pending holds tool calls awaiting approval.
    """
    started = time.time()
    result = await orchestrator.run(**run_kwargs, event_stream_handler=stream_reply(live.update))
    out = result.output
    plan = [] if isinstance(out, DeferredToolRequests) else out.plan
    if steps := steps_message(plan, tools_used(result.new_messages()), time.time() - started):
        chat.append(steps)

    if isinstance(out, DeferredToolRequests):
        for call in out.approvals:
            chat.append({"role": "assistant", "content": "**Approval needed**\n\n" + describe_approval(call)})
        return chat, result.all_messages(), out

    chat.append({"role": "assistant", "content": with_furigana(out.reply)})
    return chat, result.all_messages(), None


async def run_turn(chat: list[dict], history: list[ModelMessage], log: list[LogEntry], **run_kwargs):
    """Run the orchestrator, yielding (chat, history, pending, status, log, busy) each time
    something starts or finishes, so the progress message, the architecture panel and the
    log stay live."""
    activity = Activity(log)
    live = LiveReply(activity)
    try:
        async for status in activity.watch(run_orchestrator(chat, live, **run_kwargs)):
            yield chat + [progress_message(status)] + live.message(), history, None, status, log, True
    except Exception as e:
        # Show the failure instead of crashing the page; the failed steps are marked in the log
        error = f"{type(e).__name__}: {e}"
        log.append(LogEntry(time.time(), 0, "error", "Turn failed", error))
        chat.append({"role": "assistant", "content": "⚠️ Sorry, something went wrong and I couldn't finish that. Please try again."})
        chat.append({"role": "assistant", "content": f"`{error}`", "metadata": {"title": "Error details"}})
        yield chat, history, None, activity.status(), log, False
        return

    chat, history, pending = activity.result
    status = activity.status()
    if pending is not None:
        for call in pending.approvals:
            status |= {node_id: "waiting" for node_id in approval_targets(call.tool_name)}
            log.append(LogEntry(time.time(), 0, "info", f"Waiting for your approval: {call.tool_name}"))
    yield chat, history, pending, status, log, False


def architecture_html(status: dict[str, Status], graph: bool) -> str:
    return render_html(status, view="graph" if graph else "tree")


def user_entry(text: str, detail: str = "") -> LogEntry:
    return LogEntry(time.time(), 0, "user", text, detail)


def outputs(chat, history, pending, status, log, busy, graph, clear_box=False):
    """Values for [box, chatbot, history, pending, status, log, architecture, log_view,
    approve_btn, reject_btn]. The composer is locked while a turn is running."""
    waiting = pending is not None
    hint = "busy" if busy else "approval" if waiting else "idle"
    box = gr.Textbox(
        interactive=not busy, placeholder=COMPOSER_HINTS[hint], **({"value": ""} if clear_box else {})
    )
    return (
        box, chat, history, pending, status, log, architecture_html(status, graph), render_log(log),
        gr.Button(visible=waiting), gr.Button(visible=waiting),
    )


async def respond(message: str, chat, history, pending, status, log, graph: bool):
    message = message.strip()
    if not message:
        yield outputs(chat, history, pending, status, log, False, graph)
        return

    # Show the user's message straight away while the agent works
    chat = chat + [{"role": "user", "content": message}]
    log.append(user_entry("Message", message))
    if pending is None:
        turn = run_turn(chat, history, log, user_prompt=message, message_history=history)
    else:
        # Replying instead of approving rejects the pending action, with the reply as the reason
        results = pending.build_results(
            approvals={c.tool_call_id: ToolDenied(f"User replied instead: {message}") for c in pending.approvals}
        )
        turn = run_turn(chat, history, log, message_history=history, deferred_tool_results=results)
    async for update in turn:
        yield outputs(*update, graph, clear_box=True)


async def decide(approved: bool, chat, history, pending, log, graph: bool):
    chat = chat + [{"role": "user", "content": "✅ Approved" if approved else "❌ Rejected"}]
    log.append(user_entry("Approved" if approved else "Rejected"))
    results = pending.build_results(approvals={c.tool_call_id: approved for c in pending.approvals})
    async for update in run_turn(chat, history, log, message_history=history, deferred_tool_results=results):
        yield outputs(*update, graph)


async def approve(chat, history, pending, status, log, graph):
    async for update in decide(True, chat, history, pending, log, graph):
        yield update


async def reject(chat, history, pending, status, log, graph):
    async for update in decide(False, chat, history, pending, log, graph):
        yield update


def context_lists(items: list[ContextItem], selected: str = NEW_ITEM):
    """Updates for [active checkboxes, edit dropdown] after the saved items changed."""
    names = [i.name for i in items]
    return (
        gr.CheckboxGroup(choices=names, value=[i.name for i in items if i.enabled]),
        gr.Dropdown(choices=[NEW_ITEM, *names], value=selected if selected in names else NEW_ITEM),
    )


def pick_context(name: str):
    """Fill the editor with the chosen item (or blank it for a new one)."""
    item = next((i for i in user_context.load() if i.name == name), None)
    if item is None:
        return "", ALL, ""
    return item.name, item.applies_to, item.text


def save_context(name: str, applies_to: str, text: str):
    name, text = name.strip(), text.strip()
    if not name or not text:
        return *context_lists(user_context.load()), "⚠️ Give the item a name and some text."
    # Persist validated learner preferences for subsequent agent runs.
    items = user_context.upsert(ContextItem(name=name, text=text, applies_to=applies_to))
    return *context_lists(items, name), f"Saved **{name}**. It applies from your next message."


def delete_context(name: str):
    if name == NEW_ITEM:
        return *context_lists(user_context.load()), "", ALL, "", "Pick an item to delete."
    items = user_context.delete(name)
    return *context_lists(items), "", ALL, "", f"Deleted **{name}**."


def toggle_context(names: list[str]):
    user_context.set_enabled(set(names))


PLACEHOLDER = """## How can I help you study today?

Ask why something works the way it does, paste Japanese text to break down, find
something to read, or make Anki cards."""

EXAMPLES = [
    {"text": "Break down: 昨日、友達と一緒に新しいレストランに行きました。"},
    {"text": "What's the difference between は and が?"},
    {"text": "Find me an easy news article to read"},
    {"text": "Make Anki flashcards for 勉強, 練習 and 復習"},
]


def pick_example(evt: gr.SelectData) -> str:
    return evt.value["text"]


# Left: new chat and saved preferences. Centre: the conversation. Right: what the agents are doing.
with gr.Blocks(title="jplearn", fill_height=True) as demo:
    with gr.Sidebar(label="Menu", open=True, position="left", width=300) as menu:
        gr.Markdown("## 日本語 tutor", elem_classes="brand")
        clear = gr.Button("＋  New chat", elem_id="new-chat", variant="secondary")
        with gr.Accordion("Preferences", open=False, elem_classes="side-section"):
            gr.Markdown(
                "Notes the agents read on every message: your background, goals, how you like "
                "answers formatted. Untick an item to switch it off without deleting it."
            )
            ctx_active = gr.CheckboxGroup(label="Active items", choices=[])
            ctx_pick = gr.Dropdown(label="Edit item", choices=[NEW_ITEM], value=NEW_ITEM)
            ctx_name = gr.Textbox(label="Name", placeholder="e.g. My background")
            ctx_scope = gr.Dropdown(
                label="Applies to", choices=[(label, key) for key, label in AGENTS.items()], value=ALL
            )
            ctx_text = gr.Textbox(
                label="Context",
                lines=4,
                placeholder=(
                    "e.g. I'm an English speaker around JLPT N4. I can read hiragana/katakana and "
                    "~300 kanji. Always add romaji after example sentences. Keep answers short and "
                    "use tables for vocabulary."
                ),
            )
            with gr.Row():
                ctx_save = gr.Button("Save", variant="primary", size="sm")
                ctx_delete = gr.Button("Delete", variant="secondary", size="sm")
            ctx_status = gr.Markdown()

    with gr.Sidebar(label="Agents", open=False, position="right", width=460) as agents_panel:
        gr.Markdown("### Agents")
        graph_view = gr.Checkbox(label="Graph view", value=False)
        architecture = gr.HTML(render_html())
        gr.Markdown("### Activity")
        log_view = gr.HTML(render_log([]))

    with gr.Column(elem_id="main", scale=1):
        chatbot = gr.Chatbot(
            elem_id="chat",
            show_label=False,
            scale=1,
            placeholder=PLACEHOLDER,
            examples=EXAMPLES,
            buttons=["copy"],
        )
        history = gr.State([])  # PydanticAI message history, one per browser tab
        pending = gr.State(None)  # DeferredToolRequests waiting for approval
        status = gr.State({})  # architecture node id -> status, for the side panel
        log = gr.State([])  # LogEntry list for the activity log
        with gr.Row(elem_id="approval"):
            approve_btn = gr.Button("Approve", variant="primary", visible=False)
            reject_btn = gr.Button("Reject", variant="secondary", visible=False)
        box = gr.Textbox(
            elem_id="composer",
            placeholder=COMPOSER_HINTS["idle"],
            show_label=False,
            container=False,
            lines=1,
            max_lines=8,
            submit_btn=True,
            autofocus=True,
        )
        gr.Markdown("Open **Agents** on the right to watch each step.", elem_classes="hint")

    state = [chatbot, history, pending, status, log]
    out = [box, *state, architecture, log_view, approve_btn, reject_btn]
    box.submit(respond, [box, *state, graph_view], out)
    chatbot.example_select(pick_example, None, box).then(respond, [box, *state, graph_view], out)
    approve_btn.click(approve, [*state, graph_view], out)
    reject_btn.click(reject, [*state, graph_view], out)
    clear.click(lambda graph: outputs([], [], None, {}, [], False, graph, clear_box=True), graph_view, out)
    graph_view.change(architecture_html, [status, graph_view], architecture)

    # Only one sidebar open at a time: opening either one closes the other
    def close_sidebar():
        return gr.Sidebar(open=False)

    menu.expand(close_sidebar, None, agents_panel, queue=False, show_progress="hidden")
    agents_panel.expand(close_sidebar, None, menu, queue=False, show_progress="hidden")

    # The file can change outside this tab, so reload the items whenever the page opens
    demo.load(lambda: context_lists(user_context.load()), None, [ctx_active, ctx_pick])
    ctx_pick.change(pick_context, ctx_pick, [ctx_name, ctx_scope, ctx_text])
    ctx_save.click(save_context, [ctx_name, ctx_scope, ctx_text], [ctx_active, ctx_pick, ctx_status])
    ctx_delete.click(
        delete_context, ctx_pick, [ctx_active, ctx_pick, ctx_name, ctx_scope, ctx_text, ctx_status]
    )
    ctx_active.input(toggle_context, ctx_active, None)

if __name__ == "__main__":
    demo.launch(theme=THEME, css=CSS)
