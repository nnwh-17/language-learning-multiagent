"""Web chat with the orchestrator. Run: python -m jplearn.web"""

import gradio as gr
from pydantic_ai.messages import ModelMessage

from jplearn.agents.orchestrator import orchestrator, tools_used


async def respond(message: str, chat: list[dict], history: list[ModelMessage]):
    message = message.strip()
    if not message:
        yield "", chat, history
        return

    # Show the user's message straight away while the agent works
    chat = chat + [{"role": "user", "content": message}]
    yield "", chat, history

    result = await orchestrator.run(message, message_history=history)
    out = result.output
    if out.plan:
        plan = "\n".join(f"{i}. {step}" for i, step in enumerate(out.plan, 1))
        chat.append({"role": "assistant", "content": plan, "metadata": {"title": "Plan"}})
    if tools := tools_used(result.new_messages()):
        chat.append(
            {"role": "assistant", "content": "\n".join(tools), "metadata": {"title": "Tools used"}}
        )
    chat.append({"role": "assistant", "content": out.reply})
    yield "", chat, result.all_messages()


with gr.Blocks(title="jplearn") as demo:
    gr.Markdown("# 日本語 tutor")
    chatbot = gr.Chatbot(height=600)
    history = gr.State([])  # PydanticAI message history, one per browser tab
    box = gr.Textbox(placeholder="Ask anything, or paste Japanese text...", show_label=False)
    clear = gr.Button("New chat")

    box.submit(respond, [box, chatbot, history], [box, chatbot, history])
    clear.click(lambda: ([], []), None, [chatbot, history])

if __name__ == "__main__":
    demo.launch()
