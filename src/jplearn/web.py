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


# Warm neutrals and a terracotta accent, in the style of Claude's interface
THEME = gr.themes.Base(
    primary_hue="orange",
    neutral_hue="stone",
    radius_size="lg",
    font=["ui-sans-serif", "-apple-system", "Segoe UI", "Hiragino Sans", "Yu Gothic UI", "Meiryo", "sans-serif"],
    font_mono=["ui-monospace", "Cascadia Code", "Consolas", "monospace"],
).set(
    body_background_fill="#faf9f5",
    body_background_fill_dark="#262624",
    background_fill_primary="#faf9f5",
    background_fill_primary_dark="#262624",
    background_fill_secondary="#f5f4ed",
    background_fill_secondary_dark="#1f1e1d",
    block_background_fill="#ffffff",
    block_background_fill_dark="#30302e",
    block_border_color="#e8e6dc",
    block_border_color_dark="#3e3e38",
    border_color_primary="#e8e6dc",
    border_color_primary_dark="#3e3e38",
    block_shadow="none",
    block_shadow_dark="none",
    body_text_color="#141413",
    body_text_color_dark="#f5f4ef",
    body_text_color_subdued="#73726c",
    body_text_color_subdued_dark="#a6a39a",
    color_accent="#c96442",
    color_accent_soft="#f5e6de",
    color_accent_soft_dark="#4a3128",
    input_background_fill="#ffffff",
    input_background_fill_dark="#30302e",
    button_primary_background_fill="#c96442",
    button_primary_background_fill_dark="#c96442",
    button_primary_background_fill_hover="#b5583a",
    button_primary_background_fill_hover_dark="#d97757",
    button_primary_text_color="#ffffff",
    button_primary_text_color_dark="#ffffff",
    button_secondary_background_fill="transparent",
    button_secondary_background_fill_dark="transparent",
    button_secondary_background_fill_hover="#f0eee6",
    button_secondary_background_fill_hover_dark="#3a3a37",
)

SERIF = 'ui-serif, Georgia, "Hiragino Mincho ProN", "Yu Mincho", serif'
CSS = f"""
footer {{ display: none !important; }}
.gradio-container {{ max-width: 100% !important; }}

/* Centred conversation column, like claude.ai */
#main {{ max-width: 800px; width: 100%; margin: 0 auto; }}
#chat, #chat .bubble-wrap {{ border: none !important; background: transparent !important; }}
#chat .message {{ font-size: 16px; line-height: 1.65; }}
#chat .bot-row .message, #chat .message.bot {{
  background: transparent !important; border: none !important; box-shadow: none !important;
  font-family: {SERIF}; }}
#chat .user-row .message, #chat .message.user {{
  background: #f0eee6 !important; border: none !important; border-radius: 16px !important;
  padding: 10px 16px !important; }}
.dark #chat .user-row .message, .dark #chat .message.user {{ background: #141413 !important; }}
#chat .bubble.bot-row {{ max-width: 100%; }}
#chat .placeholder-content h2 {{ font-family: {SERIF}; font-weight: 400; font-size: 32px; }}

/* Rounded composer with the send button inside it */
#composer {{ border: 1px solid var(--border-color-primary) !important; border-radius: 20px !important;
  background: var(--input-background-fill) !important; padding: 10px 12px !important;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.04); }}
#composer textarea {{ font-size: 16px; background: transparent !important; border: none !important;
  box-shadow: none !important; }}
#composer button {{ background: #c96442 !important; color: white !important; border-radius: 10px !important; }}
#composer button:hover {{ background: #b5583a !important; }}
#chat .examples {{ grid-template-columns: repeat(2, 1fr) !important; max-width: 640px; margin: 0 auto; }}
.hint, .hint * {{ text-align: center; font-size: 12px !important; color: var(--body-text-color-subdued) !important; }}

#approval {{ gap: 8px; justify-content: center; }}
#approval button {{ max-width: 160px; border-radius: 10px; }}
#approval button.secondary {{ border: 1px solid var(--border-color-primary); }}

/* Sidebars */
.sidebar {{ background: var(--background-fill-secondary) !important; }}
.brand h2 {{ font-family: {SERIF}; font-weight: 500; margin: 4px 0 12px; }}
#new-chat {{ justify-content: flex-start; font-weight: 500; border: none; box-shadow: none; }}
.side-section {{ border: none !important; background: transparent !important; }}
"""

PLACEHOLDER = """## How can I help you study today?

Ask about grammar or vocabulary, paste Japanese text to break down, or make Anki cards."""

EXAMPLES = [
    {"text": "Break down: 昨日、友達と一緒に新しいレストランに行きました。"},
    {"text": "What's the difference between は and が?"},
    {"text": "Give me example sentences using 〜てしまう"},
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
                label="Applies to", choices=[(label, key) for key, label in AGENTS.items()], value="all"
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
            placeholder="Ask anything, or paste Japanese text...",
            show_label=False,
            container=False,
            lines=1,
            max_lines=8,
            submit_btn=True,
            autofocus=True,
        )
        gr.Markdown("Open **Agents** on the right to watch each step.", elem_classes="hint")

    state = [chatbot, history, pending, status, log]
    out = [*state, architecture, log_view, approve_btn, reject_btn]
    box.submit(respond, [box, *state, graph_view], [box, *out])
    chatbot.example_select(pick_example, None, box).then(respond, [box, *state, graph_view], [box, *out])
    approve_btn.click(approve, [*state, graph_view], out)
    reject_btn.click(reject, [*state, graph_view], out)
    clear.click(lambda graph: outputs([], [], None, {}, [], graph), graph_view, out)
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
