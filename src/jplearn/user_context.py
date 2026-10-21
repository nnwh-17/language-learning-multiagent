"""Store user context ("skills") shared with selected learning agents.

Items in ``data/context.json`` describe the learner's background, goals, and preferences.
Each agent reloads applicable enabled items when a run starts so updates take effect
without restarting the app.
"""

import json
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import Agent

CONTEXT_FILE = Path(__file__).resolve().parents[2] / "data" / "context.json"
ALL = "all"

# Agents context can be scoped to: node id -> label (ids match jplearn.architecture)
AGENTS = {
    ALL: "All agents",
    "orchestrator": "Orchestrator (replies to you)",
    "analyzer": "Analyzer",
    "flashcards": "Flashcard agent",
    "researcher": "Researcher",
    "examples": "Example sentences",
}


class ContextItem(BaseModel):
    name: str
    text: str
    applies_to: str = Field(default=ALL, description="An AGENTS key")
    enabled: bool = True


def load() -> list[ContextItem]:
    if not CONTEXT_FILE.exists():
        return []
    return [ContextItem.model_validate(item) for item in json.loads(CONTEXT_FILE.read_text(encoding="utf-8"))]


def save(items: list[ContextItem]) -> None:
    CONTEXT_FILE.parent.mkdir(exist_ok=True)
    data = [item.model_dump() for item in items]
    CONTEXT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def upsert(item: ContextItem) -> list[ContextItem]:
    """Add the item, or replace the one with the same name."""
    items = [i for i in load() if i.name != item.name]
    items.append(item)
    save(items)
    return items


def delete(name: str) -> list[ContextItem]:
    items = [i for i in load() if i.name != name]
    save(items)
    return items


def set_enabled(names: set[str]) -> list[ContextItem]:
    items = load()
    for item in items:
        item.enabled = item.name in names
    save(items)
    return items


def instructions_for(agent_id: str) -> str | None:
    """The enabled context for one agent, formatted as extra instructions."""
    items = [i for i in load() if i.enabled and i.applies_to in (ALL, agent_id)]
    if not items:
        return None
    sections = "\n\n".join(f"### {item.name}\n{item.text.strip()}" for item in items)
    return (
        "## Context from the user\n"
        "The user saved the following about themselves and their preferences. Follow it "
        "unless it conflicts with your task or output format.\n\n" + sections
    )


def use_user_context(agent: Agent, agent_id: str) -> None:
    """Add the user's saved context to `agent`'s instructions (re-read on every run)."""
    agent.instructions(lambda: instructions_for(agent_id))
