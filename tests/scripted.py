"""Scripted stand-ins for the LLM, so agent tests can say exactly what the model does.

A script is a list of steps; each model request runs the next step. For example:

    model = scripted(call("explain_concept", {"topic": "は"}), answer(["Explain"], "Done"))
    with orchestrator.override(model=model):
        result = await orchestrator.run("...")
"""

import json
from collections.abc import Callable

from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from jplearn.activity import is_output_tool

Step = Callable[[list[ModelMessage], AgentInfo], ModelResponse]


def scripted(*steps: Step) -> FunctionModel:
    """A model that answers each request with the next step (non-streamed runs)."""
    remaining = iter(steps)
    return FunctionModel(lambda messages, info: next(remaining)(messages, info))


def call(tool: str, args: dict) -> Step:
    """Step: the model calls `tool` with `args`."""
    return lambda messages, info: ModelResponse(parts=[ToolCallPart(tool, args)])


def answer(plan: list[str], reply: str) -> Step:
    """Step: the orchestrator gives its final OrchestratorReply."""
    return output({"plan": plan, "reply": reply})


def output(value: dict) -> Step:
    """Step: the agent returns `value` as its structured output."""
    return lambda messages, info: ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, value)])


def streamed(*steps) -> FunctionModel:
    """A model for streamed runs (the web UI). Each step is an async generator function
    `(messages, info) -> chunks`, e.g. `stream_call(...)` or a custom one."""
    remaining = iter(steps)

    async def stream(messages, info):
        async for chunk in next(remaining)(messages, info):
            yield chunk

    return FunctionModel(stream_function=stream)


def stream_call(tool: str, args: dict):
    async def step(messages, info):
        yield {0: DeltaToolCall(name=tool, json_args=json.dumps(args))}

    return step


def stream_output(*json_pieces: str):
    """Streams the structured output as JSON in pieces, like a real model."""

    async def step(messages, info):
        name = info.output_tools[0].name
        for i, piece in enumerate(json_pieces):
            yield {0: DeltaToolCall(name=name if i == 0 else None, json_args=piece)}

    return step


def tool_returns(messages: list[ModelMessage]) -> list[ToolReturnPart]:
    """Every real tool result the model has been sent so far (not the output acknowledgement)."""
    return [
        p for m in messages for p in m.parts if isinstance(p, ToolReturnPart) and not is_output_tool(p.tool_name)
    ]
