"""Run the Gradio chat interface for the jplearn orchestrator.

This frontend manages per-tab conversation and approval state, streams activity updates,
and provides controls for viewing the agent graph and editing saved learner context.
"""

import time

import gradio as gr
from pydantic_ai import DeferredToolRequests, ToolDenied
from pydantic_ai.messages import ModelMessage

from jplearn import user_context
from jplearn.activity import Activity, LogEntry
from jplearn.agents.orchestrator import describe_approval, orchestrator, tools_used
from jplearn.architecture import Status, approval_targets, render_html
from jplearn.log_view import render_log
from jplearn.user_context import AGENTS, ContextItem

NEW_ITEM = "➕ New item"

async def run_orchestrator(chat: list[dict], **run_kwargs):
    """Run the orchestrator and append its output to the chat.

    Returns (chat, history, pending) where pending holds tool calls awaiting approval.
    """
    result = await orchestrator.run(**run_kwargs)
    if tools := tools_used(result.new_messages()):
        chat.append(
            {"role": "assistant", "content": "\n".join(tools), "metadata": {"title": "Tools used"}}
        )

    out = result.output
    if isinstance(out, DeferredToolRequests):
        for call in out.approvals:
            chat.append({"role": "assistant", "content": "**Approval needed**\n\n" + describe_approval(call)})
        return chat, result.all_messages(), out

    if out.plan:
        plan = "\n".join(f"{i}. {step}" for i, step in enumerate(out.plan, 1))
        chat.append({"role": "assistant", "content": plan, "metadata": {"title": "Plan"}})
    chat.append({"role": "assistant", "content": out.reply})
    return chat, result.all_messages(), None


async def run_turn(chat: list[dict], history: list[ModelMessage], log: list[LogEntry], **run_kwargs):
    """Run the orchestrator, yielding (chat, history, pending, status, log) each time
    something starts or finishes, so the architecture panel and the log stay live."""
    # Activity.watch streams intermediate status snapshots to keep the UI responsive.
    activity = Activity(log)
    try:
        async for status in activity.watch(run_orchestrator(chat, **run_kwargs)):
            yield chat, history, None, status, log
    except Exception as e:
        # Show the failure instead of crashing the page; the failed steps are marked in the log
        error = f"{type(e).__name__}: {e}"
        log.append(LogEntry(time.time(), 0, "error", "Turn failed", error))
        chat.append({"role": "assistant", "content": f"⚠️ Something went wrong:\n\n`{error}`"})
        yield chat, history, None, activity.status(), log
        return

    chat, history, pending = activity.result
    status = activity.status()
    if pending is not None:
        for call in pending.approvals:
            status |= {node_id: "waiting" for node_id in approval_targets(call.tool_name)}
            log.append(LogEntry(time.time(), 0, "info", f"Waiting for your approval: {call.tool_name}"))
    yield chat, history, pending, status, log


def architecture_html(status: dict[str, Status], graph: bool) -> str:
    return render_html(status, view="graph" if graph else "tree")


def user_entry(text: str, detail: str = "") -> LogEntry:
    return LogEntry(time.time(), 0, "user", text, detail)


def outputs(chat, history, pending, status, log, graph):
    """Values for [chatbot, history, pending, status, log, architecture, log_view,
    approve_btn, reject_btn]."""
    show = pending is not None
    return (
        chat, history, pending, status, log, architecture_html(status, graph), render_log(log),
        gr.Button(visible=show), gr.Button(visible=show),
    )


async def respond(message: str, chat, history, pending, status, log, graph: bool):
    message = message.strip()
    if not message:
        yield "", *outputs(chat, history, pending, status, log, graph)
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
        yield "", *outputs(*update, graph)


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
        return "", "all", ""
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
        return *context_lists(user_context.load()), "", "all", "", "Pick an item to delete."
    items = user_context.delete(name)
    return *context_lists(items), "", "all", "", f"Deleted **{name}**."


def toggle_context(names: list[str]):
    user_context.set_enabled(set(names))


# Assemble chat, live architecture/log panels, and saved-context controls.
with gr.Blocks(title="jplearn") as demo:
    with gr.Sidebar(label="Architecture", open=False, position="right", width=420):
        gr.Markdown("### Multi-agent architecture")
        graph_view = gr.Checkbox(label="Graph view", value=False)
        architecture = gr.HTML(render_html())

    gr.Markdown("# 日本語 tutor")
    with gr.Accordion("Your context & preferences", open=False):
        gr.Markdown(
            "Saved notes the agents read on every message: your background, goals, how you "
            "like answers formatted, ... Untick an item to switch it off without deleting it."
        )
        ctx_active = gr.CheckboxGroup(label="Active items", choices=[])
        ctx_pick = gr.Dropdown(label="Edit item", choices=[NEW_ITEM], value=NEW_ITEM)
        with gr.Row():
            ctx_name = gr.Textbox(label="Name", placeholder="e.g. My background", scale=2)
            ctx_scope = gr.Dropdown(
                label="Applies to", choices=[(label, key) for key, label in AGENTS.items()], value="all", scale=1
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
            ctx_save = gr.Button("Save", variant="primary")
            ctx_delete = gr.Button("Delete", variant="stop")
        ctx_status = gr.Markdown()

    chatbot = gr.Chatbot(height=600)
    history = gr.State([])  # PydanticAI message history, one per browser tab
    pending = gr.State(None)  # DeferredToolRequests waiting for approval
    status = gr.State({})  # architecture node id -> status, for the side panel
    log = gr.State([])  # LogEntry list for the activity log
    with gr.Row():
        approve_btn = gr.Button("Approve", variant="primary", visible=False)
        reject_btn = gr.Button("Reject", variant="stop", visible=False)
    box = gr.Textbox(placeholder="Ask anything, or paste Japanese text...", show_label=False)
    clear = gr.Button("New chat")
    with gr.Accordion("Activity log", open=True):
        log_view = gr.HTML(render_log([]))

    state = [chatbot, history, pending, status, log]
    out = [*state, architecture, log_view, approve_btn, reject_btn]
    box.submit(respond, [box, *state, graph_view], [box, *out])
    approve_btn.click(approve, [*state, graph_view], out)
    reject_btn.click(reject, [*state, graph_view], out)
    clear.click(lambda graph: outputs([], [], None, {}, [], graph), graph_view, out)
    graph_view.change(architecture_html, [status, graph_view], architecture)

    # The file can change outside this tab, so reload the items whenever the page opens
    demo.load(lambda: context_lists(user_context.load()), None, [ctx_active, ctx_pick])
    ctx_pick.change(pick_context, ctx_pick, [ctx_name, ctx_scope, ctx_text])
    ctx_save.click(save_context, [ctx_name, ctx_scope, ctx_text], [ctx_active, ctx_pick, ctx_status])
    ctx_delete.click(
        delete_context, ctx_pick, [ctx_active, ctx_pick, ctx_name, ctx_scope, ctx_text, ctx_status]
    )
    ctx_active.input(toggle_context, ctx_active, None)

if __name__ == "__main__":
    demo.launch()
