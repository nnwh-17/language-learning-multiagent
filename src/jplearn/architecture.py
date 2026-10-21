"""Description of the multi-agent architecture, rendered as HTML for the web UI's side panel.

The diagram is a tree: each node is an agent, a resource (tokenizer, dictionary, MCP server)
or the user, and each edge is the tool one node uses to call the next. Every node has a
status: "idle", "running", "done" (used earlier in this turn) or "waiting" (for the user's
approval), e.g. `render_html(status={"analyzer": "running"})`. See jplearn.activity.
"""

import html
from dataclasses import dataclass, field
from typing import Literal

Kind = Literal["user", "agent", "resource"]
Status = Literal["idle", "running", "done", "waiting"]


@dataclass
class Node:
    id: str
    label: str
    kind: Kind
    description: str = ""
    # (tool name used to reach the child, child node)
    calls: list[tuple[str, "Node"]] = field(default_factory=list)
    approval: set[str] = field(default_factory=set)  # tools that need the user's approval


tokenizer = Node("tokenizer", "Sudachi tokenizer", "resource", "readings, dictionary forms, POS")
jmdict = Node("jmdict", "JMdict", "resource", "local SQLite dictionary")
anki_read = Node("anki_read", "Anki MCP (read-only)", "resource", "checks existing cards")
anki_write = Node("anki_write", "Anki MCP", "resource", "adds notes via AnkiConnect")

analyzer = Node(
    "analyzer",
    "Analyzer",
    "agent",
    "word-by-word breakdown + grammar points",
    calls=[("tokenize_japanese", tokenizer), ("tokenize_japanese", jmdict)],
)
flashcards = Node(
    "flashcards",
    "Flashcard agent",
    "agent",
    "drafts vocab & grammar cards",
    calls=[("break_down", analyzer), ("findNotes", anki_read)],
)
orchestrator = Node(
    "orchestrator",
    "Orchestrator",
    "agent",
    "plans, delegates and replies",
    calls=[
        ("analyze_japanese", analyzer),
        ("lookup_word", jmdict),
        ("draft_flashcards", flashcards),
        ("add_flashcards", anki_write),
    ],
    approval={"add_flashcards"},
)
user = Node("user", "You", "user", "chat", calls=[("message", orchestrator)])

ROOT = user


def all_nodes(node: Node = ROOT) -> dict[str, Node]:
    nodes = {node.id: node}
    for _, child in node.calls:
        nodes |= all_nodes(child)
    return nodes


def approval_targets(tool_name: str) -> set[str]:
    """Ids of the nodes behind a tool that needs the user's approval."""
    return {
        child.id
        for node in all_nodes().values()
        for tool, child in node.calls
        if tool == tool_name and tool in node.approval
    }


def check_against_agents() -> list[str]:
    """Differences between this diagram and the tools the agents actually have."""
    from jplearn.agents.analyzer import analyzer as analyzer_agent
    from jplearn.agents.flashcards import flashcard_agent
    from jplearn.agents.orchestrator import orchestrator as orchestrator_agent
    from jplearn.anki import FLASHCARD_TOOLS

    problems = []
    for node, agent in [
        (orchestrator, orchestrator_agent),
        (analyzer, analyzer_agent),
        (flashcards, flashcard_agent),
    ]:
        # MCP toolsets only know their tools once connected, so compare function tools only
        actual = {name for ts in agent.toolsets for name in getattr(ts, "tools", {})}
        drawn = {tool for tool, _ in node.calls if tool not in FLASHCARD_TOOLS}
        if actual != drawn:
            problems.append(f"{node.label}: diagram {sorted(drawn)} vs code {sorted(actual)}")
    return problems


CSS = """
.arch { font-size: 13px; line-height: 1.35; }
.arch ul { list-style: none; margin: 0; padding-left: 14px; border-left: 1px solid var(--border-color-primary); }
.arch > ul { border-left: none; padding-left: 0; }
.arch li { margin: 6px 0; position: relative; }
.arch .edge { font-family: var(--font-mono); font-size: 11px; color: var(--body-text-color-subdued); }
.arch .node { display: block; margin-top: 2px; padding: 5px 8px; border-radius: 6px;
  border: 1px solid var(--border-color-primary); background: var(--block-background-fill); }
.arch .node b { font-weight: 600; }
.arch .node small { display: block; color: var(--body-text-color-subdued); }
.arch .kind-agent { border-left: 4px solid var(--color-accent); }
.arch .kind-resource { border-left: 4px solid var(--neutral-400); }
.arch .kind-user { border-left: 4px solid var(--secondary-500, var(--neutral-500)); }
.arch .lock { font-size: 10px; padding: 0 4px; border-radius: 4px; margin-left: 4px;
  background: var(--color-accent-soft); color: var(--body-text-color); }
.arch .status-running { box-shadow: 0 0 0 2px var(--color-accent); }
.arch .status-running::after { content: "running"; float: right; font-size: 10px; color: var(--color-accent); }
.arch .status-done { opacity: 1; }
.arch .status-done::after { content: "✓"; float: right; color: var(--color-accent); }
.arch .status-waiting { border-style: dashed; border-color: var(--color-accent); }
.arch .status-waiting::after { content: "awaiting approval"; float: right; font-size: 10px; color: var(--color-accent); }
.arch .status-running { animation: arch-pulse 1.2s ease-in-out infinite; }
@keyframes arch-pulse { 50% { opacity: 0.55; } }
.arch .legend { margin-top: 12px; font-size: 11px; color: var(--body-text-color-subdued); }
"""


def _render(node: Node, status: dict[str, Status], edge: str | None, locked: bool) -> str:
    e = html.escape
    label = f"<span class='edge'>{e(edge)}{'<span class=lock>🔒 approval</span>' if locked else ''}</span>" if edge else ""
    box = (
        f"<span class='node kind-{node.kind} status-{status.get(node.id, 'idle')}' data-id='{node.id}'>"
        f"<b>{e(node.label)}</b><small>{e(node.description)}</small></span>"
    )
    children = "".join(
        _render(child, status, tool, tool in node.approval) for tool, child in node.calls
    )
    return f"<li>{label}{box}{f'<ul>{children}</ul>' if children else ''}</li>"


GRAPH_CSS = """
.arch svg { width: 100%; height: auto; font-family: var(--font); }
.arch .g-node rect { fill: var(--block-background-fill); stroke: var(--border-color-primary); }
.arch .g-node.kind-agent rect { stroke: var(--color-accent); }
.arch .g-node.status-running rect { stroke: var(--color-accent); stroke-width: 3; }
.arch .g-node.status-done rect { fill: var(--color-accent-soft); }
.arch .g-node.status-waiting rect { stroke: var(--color-accent); stroke-width: 2; stroke-dasharray: 4 3; }
.arch .g-node .title { font-size: 12px; font-weight: 600; fill: var(--body-text-color); }
.arch .g-node .sub { font-size: 9.5px; fill: var(--body-text-color-subdued); }
.arch .g-edge { fill: none; stroke: var(--body-text-color-subdued); stroke-width: 1.2; }
.arch .g-edge.approval { stroke-dasharray: 4 3; }
.arch .g-label { font-size: 9px; font-family: var(--font-mono); fill: var(--body-text-color-subdued);
  paint-order: stroke; stroke: var(--background-fill-primary); stroke-width: 3px; }
.arch .g-arrow { fill: var(--body-text-color-subdued); }
"""

BOX_W, BOX_H, LAYER_GAP, WIDTH = 136, 40, 52, 340
MARGIN = 26  # room at the sides for the lanes of arrows that skip a layer
LANE = 10


def _layers() -> dict[str, int]:
    """Layer of each node = length of the longest call path from the root, so every
    arrow points downwards."""
    depth: dict[str, int] = {}

    def visit(node: Node, d: int) -> None:
        if depth.get(node.id, -1) < d:
            depth[node.id] = d
            for _, child in node.calls:
                visit(child, d + 1)

    visit(ROOT, 0)
    return depth


def render_graph(status: dict[str, Status]) -> str:
    """SVG graph: each node drawn once, arrows labelled with the tool name."""
    e = html.escape
    nodes = all_nodes()
    depth = _layers()
    by_layer: dict[int, list[str]] = {}
    for node_id in nodes:  # insertion order = order of discovery, keeps siblings together
        by_layer.setdefault(depth[node_id], []).append(node_id)

    pos: dict[str, tuple[float, float]] = {}  # top-left corner of each box
    for layer, ids in by_layer.items():
        slot = (WIDTH - 2 * MARGIN) / len(ids)
        for i, node_id in enumerate(ids):
            x = MARGIN + slot * (i + 0.5) - BOX_W / 2
            pos[node_id] = (x, MARGIN + layer * (BOX_H + LAYER_GAP))
    height = MARGIN * 2 + len(by_layer) * BOX_H + (len(by_layer) - 1) * LAYER_GAP

    edges, labels = [], []
    for parent in nodes.values():
        px, py = pos[parent.id]
        labelled = set()  # one tool can reach several resources; label it once
        for tool, child in parent.calls:
            cx, cy = pos[child.id]
            approval = tool in parent.approval
            text = f"{e(tool)}{' 🔒' if approval else ''}"
            if depth[child.id] - depth[parent.id] == 1:
                # Neighbouring layers: from the bottom of the parent into the top of the child
                x1, y1 = px + BOX_W / 2, py + BOX_H
                x2, y2 = cx + BOX_W / 2, cy
                path = f"M{x1},{y1} C{x1},{y1 + 25} {x2},{y2 - 25} {x2},{y2}"
                # Label near the child so labels of sibling arrows don't collide
                label = f"<text class='g-label' x='{x1 + (x2 - x1) * 0.75}' y='{y2 - 10}' text-anchor='middle'>{text}</text>"
            else:
                # Skips a layer: leave the parent's side, run down a lane at the edge, enter the child's side
                left = cx + BOX_W / 2 < WIDTH / 2
                lane = LANE if left else WIDTH - LANE
                x1, y1 = (px if left else px + BOX_W), py + BOX_H / 2
                x2, y2 = (cx if left else cx + BOX_W), cy + BOX_H / 2
                path = f"M{x1},{y1} C{lane},{y1} {lane},{y1} {lane},{y1 + 20} L{lane},{y2 - 20} C{lane},{y2} {lane},{y2} {x2},{y2}"
                mid = (y1 + y2) / 2
                label = (
                    f"<text class='g-label' x='{lane}' y='{mid}' text-anchor='middle' dominant-baseline='central' "
                    f"transform='rotate(-90 {lane} {mid})'>{text}</text>"
                )
            edges.append(
                f"<path class='g-edge{' approval' if approval else ''}' d='{path}' marker-end='url(#arrow)'/>"
            )
            if tool not in labelled:
                labelled.add(tool)
                labels.append(label)

    boxes = []
    for node in nodes.values():
        x, y = pos[node.id]
        sub = {"agent": "agent", "resource": "tool / resource", "user": "chat"}[node.kind]
        boxes.append(
            f"<g class='g-node kind-{node.kind} status-{status.get(node.id, 'idle')}' data-id='{node.id}'>"
            f"<title>{e(node.description)}</title>"
            f"<rect x='{x}' y='{y}' width='{BOX_W}' height='{BOX_H}' rx='6'/>"
            f"<text class='title' x='{x + BOX_W / 2}' y='{y + 17}' text-anchor='middle'>{e(node.label)}</text>"
            f"<text class='sub' x='{x + BOX_W / 2}' y='{y + 31}' text-anchor='middle'>{sub}</text></g>"
        )

    return (
        f"<svg viewBox='0 0 {WIDTH} {height}' role='img' aria-label='Agent architecture graph'>"
        "<defs><marker id='arrow' viewBox='0 0 10 10' refX='9' refY='5' markerWidth='7' markerHeight='7' "
        "orient='auto-start-reverse'><path class='g-arrow' d='M0,0 L10,5 L0,10 z'/></marker></defs>"
        + "".join(edges) + "".join(boxes) + "".join(labels) + "</svg>"
    )


def render_html(status: dict[str, Status] | None = None, view: Literal["tree", "graph"] = "tree") -> str:
    """HTML of the architecture as a tree or a graph. `status` maps node id -> Status."""
    status = status or {}
    if view == "graph":
        return (
            f"<style>{CSS}{GRAPH_CSS}</style><div class='arch'>{render_graph(status)}"
            "<div class='legend'>Orange border = agent · arrow label = tool used · "
            "dashed 🔒 = needs your approval · hover a box for details<br>"
            "Thick pulsing border = running · filled = used this turn · "
            "dashed box = awaiting your approval</div></div>"
        )
    return (
        f"<style>{CSS}</style><div class='arch'><ul>{_render(ROOT, status, None, False)}</ul>"
        "<div class='legend'>Accent bar = agent · grey bar = tool/resource · "
        "small text above a box = the tool used to call it<br>"
        "Pulsing ring = running · ✓ = used this turn · dashed = awaiting your approval</div></div>"
    )
