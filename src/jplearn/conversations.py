"""Save web chats to disk so they survive a page reload or an app restart.

Each chat is one JSON file in ``data/chats/``: what the chat window shows, the PydanticAI
message history the orchestrator continues from, and any Anki write still waiting for
approval. The web UI saves after every turn and lists saved chats in the left sidebar.
"""

import re
import time
import uuid

from pydantic import BaseModel
from pydantic_ai import DeferredToolRequests
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart

from jplearn.config import DATA_DIR

CHATS_DIR = DATA_DIR / "chats"
TITLE_LENGTH = 48
_VALID_ID = re.compile(r"^[\w-]+$")  # ids become file names, so nothing like ../


class SavedChat(BaseModel):
    id: str
    title: str
    updated: float  # time.time() of the last save
    messages: list[dict]  # the chat window's messages, as Gradio gives them
    history: list[ModelMessage]  # what the orchestrator remembers
    pending: list[str] = []  # tool_call_ids waiting for the user's approval


def _path(chat_id: str):
    if not _VALID_ID.match(chat_id):
        raise ValueError(f"invalid chat id: {chat_id!r}")
    return CHATS_DIR / f"{chat_id}.json"


def _title(messages: list[dict]) -> str:
    """The first thing the user said, on one line and shortened."""
    first = next((m for m in messages if m["role"] == "user"), None)
    if first is None:
        return "New chat"
    content = first["content"]
    if isinstance(content, list):  # Gradio's [{"type": "text", "text": ...}] form
        content = " ".join(part.get("text", "") for part in content if isinstance(part, dict))
    text = " ".join(str(content).split())
    return text if len(text) <= TITLE_LENGTH else text[: TITLE_LENGTH - 1] + "…"


def save(
    chat_id: str | None,
    messages: list[dict],
    history: list[ModelMessage],
    pending: DeferredToolRequests | None = None,
) -> str:
    """Save a chat (a new one when `chat_id` is None) and return its id."""
    chat_id = chat_id or f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    chat = SavedChat(
        id=chat_id,
        title=_title(messages),
        updated=time.time(),
        messages=messages,
        history=history,
        pending=[call.tool_call_id for call in pending.approvals] if pending else [],
    )
    CHATS_DIR.mkdir(parents=True, exist_ok=True)
    # Write a temporary file and swap it in, so a crash mid-write can't corrupt the chat.
    tmp = _path(chat_id).with_suffix(".tmp")
    tmp.write_text(chat.model_dump_json(), encoding="utf-8")
    tmp.replace(_path(chat_id))
    return chat_id


def load(chat_id: str) -> SavedChat | None:
    path = _path(chat_id)
    if not path.exists():
        return None
    return SavedChat.model_validate_json(path.read_text(encoding="utf-8"))


def pending_approvals(chat: SavedChat) -> DeferredToolRequests | None:
    """Rebuild the approval request a chat was waiting on, from its saved history."""
    if not chat.pending:
        return None
    calls = [
        part
        for message in chat.history
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ToolCallPart) and part.tool_call_id in chat.pending
    ]
    return DeferredToolRequests(approvals=calls) if calls else None


def list_chats() -> list[SavedChat]:
    """Saved chats, most recently updated first. Unreadable files are skipped."""
    chats = []
    for path in CHATS_DIR.glob("*.json"):
        try:
            chats.append(SavedChat.model_validate_json(path.read_text(encoding="utf-8")))
        except ValueError:
            continue
    return sorted(chats, key=lambda chat: chat.updated, reverse=True)


def delete(chat_id: str) -> None:
    _path(chat_id).unlink(missing_ok=True)
