"""Web chat with the orchestrator. Run: python -m jplearn.web"""

import gradio as gr
from pydantic_ai import DeferredToolRequests, ToolDenied
from pydantic_ai.messages import ModelMessage

from jplearn.agents.orchestrator import describe_approval, orchestrator, tools_used


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


def buttons(pending):
    return gr.Button(visible=pending is not None), gr.Button(visible=pending is not None)


async def respond(message: str, chat: list[dict], history: list[ModelMessage], pending):
    message = message.strip()
    if not message:
        yield "", chat, history, pending, *buttons(pending)
        return

    # Show the user's message straight away while the agent works
    chat = chat + [{"role": "user", "content": message}]
    yield "", chat, history, pending, *buttons(None)

    if pending is None:
        chat, history, pending = await run_orchestrator(chat, user_prompt=message, message_history=history)
    else:
        # Replying instead of approving rejects the pending action, with the reply as the reason
        results = pending.build_results(
            approvals={c.tool_call_id: ToolDenied(f"User replied instead: {message}") for c in pending.approvals}
        )
        chat, history, pending = await run_orchestrator(
            chat, message_history=history, deferred_tool_results=results
        )
    yield "", chat, history, pending, *buttons(pending)


async def decide(approved: bool, chat: list[dict], history: list[ModelMessage], pending):
    chat = chat + [{"role": "user", "content": "✅ Approved" if approved else "❌ Rejected"}]
    yield chat, history, None, *buttons(None)
    results = pending.build_results(approvals={c.tool_call_id: approved for c in pending.approvals})
    chat, history, pending = await run_orchestrator(
        chat, message_history=history, deferred_tool_results=results
    )
    yield chat, history, pending, *buttons(pending)


async def approve(chat, history, pending):
    async for update in decide(True, chat, history, pending):
        yield update


async def reject(chat, history, pending):
    async for update in decide(False, chat, history, pending):
        yield update


with gr.Blocks(title="jplearn") as demo:
    gr.Markdown("# 日本語 tutor")
    chatbot = gr.Chatbot(height=600)
    history = gr.State([])  # PydanticAI message history, one per browser tab
    pending = gr.State(None)  # DeferredToolRequests waiting for approval
    with gr.Row():
        approve_btn = gr.Button("Approve", variant="primary", visible=False)
        reject_btn = gr.Button("Reject", variant="stop", visible=False)
    box = gr.Textbox(placeholder="Ask anything, or paste Japanese text...", show_label=False)
    clear = gr.Button("New chat")

    state = [chatbot, history, pending]
    box.submit(respond, [box, *state], [box, *state, approve_btn, reject_btn])
    approve_btn.click(approve, state, [*state, approve_btn, reject_btn])
    reject_btn.click(reject, state, [*state, approve_btn, reject_btn])
    clear.click(lambda: ([], [], None, *buttons(None)), None, [*state, approve_btn, reject_btn])

if __name__ == "__main__":
    demo.launch()
