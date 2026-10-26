"""Run the Gradio chat interface for the jplearn orchestrator.

This frontend manages per-tab conversation and approval state, streams activity updates,
and provides controls for viewing the agent graph and editing saved learner context.
"""

import time

import gradio as gr
from pydantic_ai import DeferredToolRequests, ToolDenied
from pydantic_ai.messages import ModelMessage

from jplearn import conversations, user_context
from jplearn.activity import Activity, LogEntry
from jplearn.agents.orchestrator import describe_approval, orchestrator, stream_reply, tools_used
from jplearn.architecture import Status, all_nodes, approval_targets, render_html
from jplearn.kana import with_furigana
from jplearn import quiz_view
from jplearn.log_view import render_log
from jplearn.quiz_view import QuizSession
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


# --- quiz panel (see quiz_view.py). Its values: [quiz_state, *quiz_ui] ---


def sync_quiz(history, session: QuizSession | None):
    """Show the chat's unfinished quiz, keep the one in progress, or hide the panel."""
    found = quiz_view.active_quiz(history)
    if found is None:
        return None, *quiz_view.render(None)
    if session is not None and session.id == found.id:
        return (gr.skip(),) * (1 + QUIZ_UI_SIZE)  # already showing; keep the learner's progress
    return found, *quiz_view.render(found)


def check_answer(session: QuizSession | None, choice: str | None, typed: str):
    if session is None or session.checked:
        return (gr.skip(),) * (1 + QUIZ_UI_SIZE)
    response = (choice if session.question.kind == "choice" else typed) or ""
    if not response.strip():
        return session, *quiz_view.render(session, notice="Choose or type an answer first.")
    session = quiz_view.answer(session, response.strip())
    return session, *quiz_view.render(session)


async def finish_quiz(session: QuizSession | None, chat, history, pending, status, log, graph):
    """Close the panel and send the results to the orchestrator for feedback.
    Values for [*out, quiz_state, *quiz_ui]."""
    if session is None:
        yield (gr.skip(),) * (OUT_SIZE + 1 + QUIZ_UI_SIZE)
        return
    chat = chat + [{"role": "user", "content": quiz_view.results_markdown(session)}]
    log.append(user_entry("Quiz finished", f"{session.score}/{len(session.quiz.questions)}"))
    run_kwargs = {"user_prompt": quiz_view.results_prompt(session), "message_history": history}
    if pending is not None:  # an approval left waiting is rejected, as when replying instead
        run_kwargs["deferred_tool_results"] = pending.build_results(
            approvals={c.tool_call_id: ToolDenied("User finished a quiz instead") for c in pending.approvals}
        )
    async for update in run_turn(chat, history, log, **run_kwargs):
        yield *outputs(*update, graph), None, *quiz_view.render(None)


async def advance_quiz(session: QuizSession | None, chat, history, pending, status, log, graph):
    """Next question, or the results after the last one."""
    if session is not None and session.checked and not session.is_last:
        session = quiz_view.next_question(session)
        yield *(gr.skip(),) * OUT_SIZE, session, *quiz_view.render(session)
        return
    async for update in finish_quiz(session, chat, history, pending, status, log, graph):
        yield update


QUIZ_UI_SIZE = len(quiz_view.render(None))
OUT_SIZE = len(outputs([], [], None, {}, [], False, False))  # values in `out`


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


def chat_list(selected: str | None = None) -> gr.Radio:
    """The sidebar's list of saved chats, newest first."""
    return gr.Radio(choices=[(c.title, c.id) for c in conversations.list_chats()], value=selected)


def save_chat(chat_id: str | None, chat, history, pending):
    """Save the conversation after each turn. Returns [chat_id, chat list]."""
    if not chat:
        return chat_id, chat_list(chat_id)
    chat_id = conversations.save(chat_id, chat, history, pending)
    return chat_id, chat_list(chat_id)


def open_chat(chat_id: str | None, graph: bool):
    """Values for [*out, chat_id] showing a saved chat, or an empty one."""
    saved = conversations.load(chat_id) if chat_id else None
    if saved is None:
        return *outputs([], [], None, {}, [], False, graph, clear_box=True), None
    pending = conversations.pending_approvals(saved)
    return *outputs(saved.messages, saved.history, pending, {}, [], False, graph, clear_box=True), saved.id


def new_chat(graph: bool):
    """Values for [*out, chat_id, chat list]: an empty chat, nothing selected."""
    return *open_chat(None, graph), chat_list()


def delete_chat(chat_id: str | None, graph: bool):
    if chat_id:
        conversations.delete(chat_id)
    return new_chat(graph)


def reopen_latest_chat(graph: bool):
    """On page load, carry on with the most recent chat."""
    chats = conversations.list_chats()
    latest = chats[0].id if chats else None
    return *open_chat(latest, graph), chat_list(latest)


PLACEHOLDER = """## How can I help you study today?

Ask why something works the way it does, paste Japanese text to break down, find
something to read, or make Anki cards."""

EXAMPLES = [
    {"text": "Break down: 昨日、友達と一緒に新しいレストランに行きました。"},
    {"text": "What's the difference between は and が?"},
    {"text": "Quiz me on basic N5 verbs"},
    {"text": "Make Anki flashcards for 勉強, 練習 and 復習"},
]


def pick_example(evt: gr.SelectData) -> str:
    return evt.value["text"]


# Left: new chat and saved preferences. Centre: the conversation. Right: what the agents are doing.
with gr.Blocks(title="jplearn", fill_height=True) as demo:
    with gr.Sidebar(label="Menu", open=True, position="left", width=300) as menu:
        gr.Markdown("## 日本語 tutor", elem_classes="brand")
        clear = gr.Button("＋  New chat", elem_id="new-chat", variant="secondary")
        chats = gr.Radio(label="Chats", choices=[], elem_id="chats")
        delete_chat_btn = gr.Button("Delete this chat", elem_id="delete-chat", variant="secondary", size="sm")
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
        chat_id = gr.State(None)  # id of the saved chat shown in this tab (None until the first save)
        quiz_state = gr.State(None)  # QuizSession for the quiz panel, or None
        with gr.Column(elem_id="quiz", visible=False) as quiz_panel:
            quiz_progress = gr.HTML()
            quiz_question = gr.Markdown(elem_id="quiz-question")
            quiz_choices = gr.Radio(choices=[], show_label=False, elem_id="quiz-choices", container=False)
            quiz_typed = gr.Textbox(show_label=False, container=False, elem_id="quiz-typed")
            quiz_feedback = gr.Markdown(elem_id="quiz-feedback")
            with gr.Row(elem_id="quiz-actions"):
                quiz_check = gr.Button("Check", variant="primary", size="sm")
                quiz_next = gr.Button("Next question →", variant="primary", size="sm", visible=False)
                quiz_end = gr.Button("End quiz", variant="secondary", size="sm")
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
    quiz_ui = [quiz_panel, quiz_progress, quiz_question, quiz_choices, quiz_typed, quiz_feedback, quiz_check, quiz_next]
    # Every turn is followed by a save, so chats survive a reload or restart, and by a quiz
    # sync, which opens a quiz the turn started (or the open chat's unfinished one)
    save = (save_chat, [chat_id, chatbot, history, pending], [chat_id, chats])
    sync = (sync_quiz, [history, quiz_state], [quiz_state, *quiz_ui])
    box.submit(respond, [box, *state, graph_view], out).then(*save).then(*sync)
    chatbot.example_select(pick_example, None, box).then(respond, [box, *state, graph_view], out).then(*save).then(*sync)
    approve_btn.click(approve, [*state, graph_view], out).then(*save).then(*sync)
    reject_btn.click(reject, [*state, graph_view], out).then(*save).then(*sync)
    clear.click(new_chat, graph_view, [*out, chat_id, chats]).then(*sync)
    chats.input(open_chat, [chats, graph_view], [*out, chat_id]).then(*sync)
    delete_chat_btn.click(delete_chat, [chat_id, graph_view], [*out, chat_id, chats]).then(*sync)
    demo.load(reopen_latest_chat, graph_view, [*out, chat_id, chats]).then(*sync)

    # Choices are marked as soon as one is clicked; typed answers on Enter or Check
    check = (check_answer, [quiz_state, quiz_choices, quiz_typed], [quiz_state, *quiz_ui])
    quiz_choices.input(*check)
    quiz_typed.submit(*check)
    quiz_check.click(*check)
    quiz_next.click(advance_quiz, [quiz_state, *state, graph_view], [*out, quiz_state, *quiz_ui]).then(*save)
    quiz_end.click(finish_quiz, [quiz_state, *state, graph_view], [*out, quiz_state, *quiz_ui]).then(*save)
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
