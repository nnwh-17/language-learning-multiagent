"""Saved preferences, live activity tracking, and the agents diagram."""

import anyio
import pytest

from jplearn import user_context
from jplearn.activity import Activity, log, span, track, tree_order
from jplearn.architecture import all_nodes, approval_targets, check_against_agents, render_html
from jplearn.user_context import ContextItem

# --- saved preferences ---


def test_preferences_start_empty_and_round_trip():
    assert user_context.load() == []
    user_context.upsert(ContextItem(name="Level", text="JLPT N4"))
    assert user_context.load() == [ContextItem(name="Level", text="JLPT N4")]


def test_upsert_replaces_item_with_same_name():
    user_context.upsert(ContextItem(name="Level", text="N5"))
    items = user_context.upsert(ContextItem(name="Level", text="N4"))
    assert [i.text for i in items] == ["N4"]


def test_delete_and_toggle():
    user_context.upsert(ContextItem(name="A", text="a"))
    user_context.upsert(ContextItem(name="B", text="b"))
    assert [i.enabled for i in user_context.set_enabled({"B"})] == [False, True]
    assert [i.name for i in user_context.delete("A")] == ["B"]


def test_instructions_include_only_enabled_items_for_that_agent():
    user_context.upsert(ContextItem(name="Everyone", text="I speak Mandarin"))
    user_context.upsert(ContextItem(name="Explainer only", text="Use cooking analogies", applies_to="explainer"))
    user_context.upsert(ContextItem(name="Off", text="hidden", enabled=False))

    explainer = user_context.instructions_for("explainer")
    analyzer = user_context.instructions_for("analyzer")
    assert "I speak Mandarin" in explainer and "cooking" in explainer and "hidden" not in explainer
    assert "I speak Mandarin" in analyzer and "cooking" not in analyzer


def test_no_instructions_when_nothing_saved():
    assert user_context.instructions_for("orchestrator") is None


def test_preference_scopes_list_every_agent():
    agent_ids = {node.id for node in all_nodes().values() if node.kind == "agent"}
    assert set(user_context.AGENTS) == agent_ids | {user_context.ALL}


# --- live activity ---


def test_recording_is_a_no_op_outside_watch():
    with span("agent", "Analyzer", ["analyzer"]) as entry:
        assert entry is None
    log("info", "nothing listens")  # must not raise


@pytest.mark.anyio
async def test_watch_tracks_nested_work_and_returns_result():
    release = anyio.Event()

    async def work():
        with span("agent", "Analyzer", ["analyzer"]):
            with track("jmdict"):
                await release.wait()  # hold here until the test has seen the running state
        return 42

    activity = Activity()
    statuses = []
    async for status in activity.watch(work()):
        statuses.append(status)
        if status.get("jmdict") == "running":
            release.set()

    assert activity.result == 42
    assert {"analyzer": "running", "jmdict": "running"} in statuses
    assert statuses[-1] == {"analyzer": "done", "jmdict": "done"}
    agent, resource = activity.log
    assert (agent.kind, agent.depth, agent.status) == ("agent", 0, "done")
    assert (resource.kind, resource.depth, resource.parent, resource.text) == ("resource", 1, agent.id, "JMdict")


@pytest.mark.anyio
async def test_watch_marks_failed_span_and_reraises():
    async def work():
        with span("tool", "lookup_word"):
            raise ValueError("boom")

    activity = Activity()
    with pytest.raises(ValueError):
        async for _ in activity.watch(work()):
            pass
    (entry,) = activity.log
    assert entry.status == "error" and "boom" in entry.detail


def test_tree_order_groups_children_under_parents():
    from jplearn.activity import LogEntry

    parent_a = LogEntry(0, 0, "agent", "A")
    parent_b = LogEntry(1, 0, "agent", "B")
    child_a = LogEntry(2, 1, "tool", "a1", parent=parent_a.id)  # started after B
    assert [e.text for e in tree_order([parent_a, parent_b, child_a])] == ["A", "a1", "B"]


# --- agents diagram ---


def test_diagram_matches_agent_tools():
    assert check_against_agents() == []


def test_approval_targets_are_anki_writes():
    assert approval_targets("add_flashcards") == {"anki_write"}
    assert approval_targets("analyze_japanese") == set()


@pytest.mark.parametrize("view", ["tree", "graph"])
def test_render_shows_every_node_and_status(view):
    html = render_html({"explainer": "running"}, view=view)
    assert all(node.label in html for node in all_nodes().values())
    assert "status-running" in html
