"""Web chat with the orchestrator. Run: python -m jplearn.web"""

import gradio as gr
from pydantic_ai import DeferredToolRequests, ToolDenied
from pydantic_ai.messages import ModelMessage

from jplearn.activity import Activity, track
from jplearn.agents.orchestrator import describe_approval, orchestrator, tools_used
from jplearn.architecture import Status, approval_targets, render_html


async def run_orchestrator(chat: list[dict], **run_kwargs):
    """Run the orchestrator and append its output to the chat.

    Returns (chat, history, pending) where pending holds tool calls awaiting approval.
    """
    with track("orchestrator"):
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


async def run_turn(chat: list[dict], history: list[ModelMessage], **run_kwargs):
    """Run the orchestrator, yielding (chat, history, pending, status) each time an agent
    starts or finishes, so the architecture panel shows what is running."""
    activity = Activity()
    async for status in activity.watch(run_orchestrator(chat, **run_kwargs)):
        yield chat, history, None, status
    chat, history, pending = activity.result
    status = activity.status()
    if pending is not None:
        for call in pending.approvals:
            status |= {node_id: "waiting" for node_id in approval_targets(call.tool_name)}
    yield chat, history, pending, status


def architecture_html(status: dict[str, Status], graph: bool) -> str:
    return render_html(status, view="graph" if graph else "tree")


def outputs(chat, history, pending, status, graph):
    """Values for [chatbot, history, pending, status, architecture, approve_btn, reject_btn]."""
    show = pending is not None
    return (
        chat, history, pending, status, architecture_html(status, graph),
        gr.Button(visible=show), gr.Button(visible=show),
    )


async def respond(message: str, chat, history, pending, status, graph: bool):
    message = message.strip()
    if not message:
        yield "", *outputs(chat, history, pending, status, graph)
        return

    # Show the user's message straight away while the agent works
    chat = chat + [{"role": "user", "content": message}]
    if pending is None:
        turn = run_turn(chat, history, user_prompt=message, message_history=history)
    else:
        # Replying instead of approving rejects the pending action, with the reply as the reason
        results = pending.build_results(
            approvals={c.tool_call_id: ToolDenied(f"User replied instead: {message}") for c in pending.approvals}
        )
        turn = run_turn(chat, history, message_history=history, deferred_tool_results=results)
    async for update in turn:
        yield "", *outputs(*update, graph)


async def decide(approved: bool, chat, history, pending, graph: bool):
    chat = chat + [{"role": "user", "content": "✅ Approved" if approved else "❌ Rejected"}]
    results = pending.build_results(approvals={c.tool_call_id: approved for c in pending.approvals})
    async for update in run_turn(chat, history, message_history=history, deferred_tool_results=results):
        yield outputs(*update, graph)


async def approve(chat, history, pending, status, graph):
    async for update in decide(True, chat, history, pending, graph):
        yield update


async def reject(chat, history, pending, status, graph):
    async for update in decide(False, chat, history, pending, graph):
        yield update


with gr.Blocks(title="jplearn") as demo:
    with gr.Sidebar(label="Architecture", open=False, position="right", width=360):
        gr.Markdown("### Multi-agent architecture")
        graph_view = gr.Checkbox(label="Graph view", value=False)
        architecture = gr.HTML(render_html())

    gr.Markdown("# 日本語 tutor")
    chatbot = gr.Chatbot(height=600)
    history = gr.State([])  # PydanticAI message history, one per browser tab
    pending = gr.State(None)  # DeferredToolRequests waiting for approval
    status = gr.State({})  # architecture node id -> status, for the side panel
    with gr.Row():
        approve_btn = gr.Button("Approve", variant="primary", visible=False)
        reject_btn = gr.Button("Reject", variant="stop", visible=False)
    box = gr.Textbox(placeholder="Ask anything, or paste Japanese text...", show_label=False)
    clear = gr.Button("New chat")

    state = [chatbot, history, pending, status]
    out = [*state, architecture, approve_btn, reject_btn]
    box.submit(respond, [box, *state, graph_view], [box, *out])
    approve_btn.click(approve, [*state, graph_view], out)
    reject_btn.click(reject, [*state, graph_view], out)
    clear.click(lambda graph: outputs([], [], None, {}, graph), graph_view, out)
    graph_view.change(architecture_html, [status, graph_view], architecture)

if __name__ == "__main__":
    demo.launch()
