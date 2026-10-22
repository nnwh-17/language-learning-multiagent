"""Model and render the agent/resource graph shown in the web UI.

The diagram is a tree: each node is an agent, a tool (tokenizer, dictionary, web), an MCP server
or the user, and each edge is the tool one node uses to call the next. Every node has a
status: "idle", "running", "done" (used earlier in this turn) or "waiting" (for the user's
approval), e.g. `render_html(status={"analyzer": "running"})`. See jplearn.activity.

Agent definitions mirror the tool wiring in ``agents/``; the health check compares the
diagram against those agents so the UI stays synchronized with the implementation.
"""

import html
from dataclasses import dataclass, field
from typing import Literal

Kind = Literal["user", "agent", "tool", "mcp"]
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
    checks: set[str] = field(default_factory=set)  # edges that aren't tools, e.g. output checks


tokenizer = Node("tokenizer", "Sudachi tokenizer", "tool", "readings, dictionary forms, POS")
jmdict = Node("jmdict", "JMdict", "tool", "local SQLite dictionary")
anki_read = Node("anki_read", "Anki MCP (read-only)", "mcp", "checks existing cards")
anki_write = Node("anki_write", "Anki MCP", "mcp", "adds notes via AnkiConnect")
web_search = Node("web_search", "DuckDuckGo", "tool", "web search")
web_fetch = Node("web_fetch", "Web pages", "tool", "fetches pages as markdown")

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
researcher = Node(
    "researcher",
    "Researcher",
    "agent",
    "finds Japanese reading material online",
    calls=[("search_web", web_search), ("fetch_page", web_fetch)],
)
examples = Node(
    "examples",
    "Example sentences",
    "agent",
    "writes example sentences for words",
    calls=[("lookup_word", jmdict), ("output check", tokenizer)],
    checks={"output check"},
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
        ("add_examples_to_card", anki_write),
        ("find_material", researcher),
        ("generate_examples", examples),
    ],
    approval={"add_flashcards", "add_examples_to_card"},
)
user = Node("user", "You", "user", "chat", calls=[("message", orchestrator)])

ROOT = user


def all_nodes(node: Node = ROOT) -> dict[str, Node]:
    # Flatten the graph for status updates, tool checks, and renderers.
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
    from jplearn.agents.examples import examples_agent
    from jplearn.agents.flashcards import flashcard_agent
    from jplearn.agents.orchestrator import orchestrator as orchestrator_agent
    from jplearn.agents.researcher import researcher as researcher_agent
    from jplearn.anki import FLASHCARD_TOOLS

    # Compare function tools only; MCP toolsets reveal their tool names after connecting.
    problems = []
    for node, agent in [
        (orchestrator, orchestrator_agent),
        (analyzer, analyzer_agent),
        (flashcards, flashcard_agent),
        (researcher, researcher_agent),
        (examples, examples_agent),
    ]:
        # MCP toolsets only know their tools once connected, so compare function tools only
        actual = {name for ts in agent.toolsets for name in getattr(ts, "tools", {})}
        drawn = {tool for tool, _ in node.calls if tool not in FLASHCARD_TOOLS | node.checks}
        if actual != drawn:
            problems.append(f"{node.label}: diagram {sorted(drawn)} vs code {sorted(actual)}")
    return problems


# Each kind has its own colour, used for the box, its type label and the arrows into it
KIND_LABELS = {"user": "you", "agent": "agent", "tool": "tool", "mcp": "MCP server"}
KIND_ICONS = {"user": "●", "agent": "◆", "tool": "⚙", "mcp": "⇄"}

CSS = """
.arch { --k-agent: #c96442; --k-tool: #8a8780; --k-mcp: #4f7cac; --k-user: var(--body-text-color);
  font-size: 13px; line-height: 1.35; }
.arch ul { list-style: none; margin: 0; padding-left: 14px; border-left: 1px solid var(--border-color-primary); }
.arch > ul { border-left: none; padding-left: 0; }
.arch li { margin: 6px 0; position: relative; }
.arch .edge { font-family: var(--font-mono); font-size: 11px; color: var(--body-text-color-subdued); }
.arch .node { display: block; margin-top: 2px; padding: 5px 8px; border-radius: 3px;
  border: 1px solid var(--border-color-primary); background: var(--block-background-fill); }
.arch .node b { font-weight: 600; }
.arch .node small { display: block; color: var(--body-text-color-subdued); }
.arch .kind { float: right; font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; }
.arch .kind-agent { border-left: 4px solid var(--k-agent); border-radius: 8px;
  background: color-mix(in srgb, var(--k-agent) 10%, var(--block-background-fill)); }
.arch .kind-tool { border-left: 4px solid var(--k-tool); }
.arch .kind-mcp { border-left: 4px solid var(--k-mcp);
  background: color-mix(in srgb, var(--k-mcp) 10%, var(--block-background-fill)); }
.arch .kind-user { border-left: 4px solid var(--k-user); border-radius: 14px; }
.arch .kind-agent .kind { color: var(--k-agent); }
.arch .kind-tool .kind { color: var(--k-tool); }
.arch .kind-mcp .kind { color: var(--k-mcp); }
.arch .kind-user .kind { color: var(--body-text-color-subdued); }
.arch .lock { font-size: 10px; padding: 0 4px; border-radius: 4px; margin-left: 4px;
  background: var(--color-accent-soft); color: var(--body-text-color); }
.arch .status-running { box-shadow: 0 0 0 2px var(--color-accent); animation: arch-pulse 1.2s ease-in-out infinite; }
.arch .status-done b::after { content: " ✓"; color: var(--color-accent); }
.arch .status-waiting { border-style: dashed; border-color: var(--color-accent); }
.arch .status-waiting b::after { content: " · awaiting approval"; font-weight: 400; font-size: 11px; color: var(--color-accent); }
@keyframes arch-pulse { 50% { opacity: 0.55; } }
.arch .legend { margin-top: 12px; font-size: 11px; color: var(--body-text-color-subdued); }
.arch .keys { display: flex; flex-wrap: wrap; gap: 6px 12px; margin-bottom: 6px; }
.arch .key { display: inline-flex; align-items: center; gap: 5px; color: var(--body-text-color); }
.arch .swatch { width: 14px; height: 10px; border: 1.5px solid; }
.arch .swatch.kind-agent { border-color: var(--k-agent); border-radius: 4px;
  background: color-mix(in srgb, var(--k-agent) 15%, transparent); }
.arch .swatch.kind-tool { border-color: var(--k-tool); border-radius: 1px; }
.arch .swatch.kind-mcp { border-color: var(--k-mcp); border-radius: 1px;
  background: color-mix(in srgb, var(--k-mcp) 15%, transparent); }
.arch .swatch.kind-user { border-color: var(--k-user); border-radius: 999px; }
"""


def _render(node: Node, status: dict[str, Status], edge: str | None, locked: bool) -> str:
    e = html.escape
    label = f"<span class='edge'>{e(edge)}{'<span class=lock>🔒 approval</span>' if locked else ''}</span>" if edge else ""
    box = (
        f"<span class='node kind-{node.kind} status-{status.get(node.id, 'idle')}' data-id='{node.id}'>"
        f"<span class='kind'>{KIND_ICONS[node.kind]} {KIND_LABELS[node.kind]}</span>"
        f"<b>{e(node.label)}</b><small>{e(node.description)}</small></span>"
    )
    children = "".join(
        _render(child, status, tool, tool in node.approval) for tool, child in node.calls
    )
    return f"<li>{label}{box}{f'<ul>{children}</ul>' if children else ''}</li>"


GRAPH_CSS = """
.arch svg { width: 100%; height: auto; font-family: var(--font); }
.arch .g-node rect { fill: var(--block-background-fill); stroke-width: 1.5; }
.arch .g-node.kind-agent rect { stroke: var(--k-agent); fill: color-mix(in srgb, var(--k-agent) 12%, var(--block-background-fill)); }
.arch .g-node.kind-tool rect { stroke: var(--k-tool); }
.arch .g-node.kind-mcp rect { stroke: var(--k-mcp); fill: color-mix(in srgb, var(--k-mcp) 12%, var(--block-background-fill)); }
.arch .g-node.kind-user rect { stroke: var(--k-user); }
.arch .g-node.status-running rect { stroke-width: 3.5; animation: arch-pulse 1.2s ease-in-out infinite; }
.arch .g-node.status-waiting rect { stroke: var(--color-accent); stroke-width: 2; stroke-dasharray: 4 3; }
.arch .g-node .title { font-size: 12px; font-weight: 600; fill: var(--body-text-color); }
.arch .g-node .sub { font-size: 9px; font-weight: 600; letter-spacing: .05em; text-transform: uppercase; }
.arch .g-node.kind-agent .sub { fill: var(--k-agent); }
.arch .g-node.kind-tool .sub { fill: var(--k-tool); }
.arch .g-node.kind-mcp .sub { fill: var(--k-mcp); }
.arch .g-node.kind-user .sub { fill: var(--body-text-color-subdued); }
.arch .g-done circle { fill: var(--color-accent); }
.arch .g-done text { font-size: 10px; font-weight: 700; fill: white; }
.arch .g-edge { fill: none; stroke-width: 1.3; }
.arch .g-edge.approval { stroke-dasharray: 4 3; }
.arch .to-agent { stroke: var(--k-agent); fill: var(--k-agent); }
.arch .to-tool { stroke: var(--k-tool); fill: var(--k-tool); }
.arch .to-mcp { stroke: var(--k-mcp); fill: var(--k-mcp); }
.arch .to-user { stroke: var(--k-user); fill: var(--k-user); }
.arch .g-edge[class*=to-] { fill: none; }
.arch .g-label { font-size: 9px; font-family: var(--font-mono); stroke: none;
  paint-order: stroke; }
.arch .g-label.halo { stroke: var(--background-fill-primary); stroke-width: 3px; }
"""

BOX_W, BOX_H, LAYER_GAP, MIN_WIDTH, BOX_GAP = 128, 42, 52, 340, 10
MARGIN = 26  # room at the sides for the lanes of arrows that skip a layer
LANE = 10
RADIUS = {"user": BOX_H / 2, "agent": 10, "tool": 2, "mcp": 2}


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


def _label(cls: str, x: float, y: float, text: str, extra: str = "") -> str:
    # Drawn twice: a background-coloured halo underneath keeps the label readable over arrows
    return "".join(
        f"<text class='g-label {cls}{halo}' x='{x}' y='{y}' {extra}>{text}</text>" for halo in (" halo", "")
    )


def render_graph(status: dict[str, Status]) -> str:
    """SVG graph: each node drawn once, arrows labelled with the tool name."""
    e = html.escape
    nodes = all_nodes()
    depth = _layers()
    by_layer: dict[int, list[str]] = {}
    for node_id in nodes:  # insertion order = order of discovery, keeps siblings together
        by_layer.setdefault(depth[node_id], []).append(node_id)

    # Wide enough for the fullest layer; the SVG scales down to fit the panel
    widest = max(len(ids) for ids in by_layer.values())
    width = max(MIN_WIDTH, widest * (BOX_W + BOX_GAP) + 2 * MARGIN)
    pos: dict[str, tuple[float, float]] = {}  # top-left corner of each box
    for layer, ids in by_layer.items():
        slot = (width - 2 * MARGIN) / len(ids)
        for i, node_id in enumerate(ids):
            x = MARGIN + slot * (i + 0.5) - BOX_W / 2
            pos[node_id] = (x, MARGIN + layer * (BOX_H + LAYER_GAP))
    height = MARGIN * 2 + len(by_layer) * BOX_H + (len(by_layer) - 1) * LAYER_GAP

    # Build labeled arrows separately from node boxes so shared destinations stay readable.
    edges, labels = [], []
    for parent in nodes.values():
        px, py = pos[parent.id]
        # Several tools can lead to the same child: draw one arrow with a label per tool
        by_child: dict[str, list[str]] = {}
        for tool, child in parent.calls:
            by_child.setdefault(child.id, []).append(tool)
        labelled = set()  # one tool can reach several resources; label it once
        for child_id, tools in by_child.items():
            cx, cy = pos[child_id]
            to = f"to-{nodes[child_id].kind}"  # arrows take the colour of what they point at
            approval = any(t in parent.approval for t in tools)
            texts = [f"{e(t)}{' 🔒' if t in parent.approval else ''}" for t in tools]
            if depth[child_id] - depth[parent.id] == 1:
                # Neighbouring layers: from the bottom of the parent into the top of the child
                x1, y1 = px + BOX_W / 2, py + BOX_H
                x2, y2 = cx + BOX_W / 2, cy
                path = f"M{x1},{y1} C{x1},{y1 + 25} {x2},{y2 - 25} {x2},{y2}"
                # Label near the child so labels of sibling arrows don't collide; stack upwards
                label = "".join(
                    _label(to, x1 + (x2 - x1) * 0.75, y2 - 10 - 11 * (len(texts) - 1 - i), text,
                           "text-anchor='middle'")
                    for i, text in enumerate(texts)
                )
            else:
                # Skips a layer: leave the parent's side, run down a lane at the edge, enter the child's side
                left = cx + BOX_W / 2 < width / 2
                lane = LANE if left else width - LANE
                x1, y1 = (px if left else px + BOX_W), py + BOX_H / 2
                x2, y2 = (cx if left else cx + BOX_W), cy + BOX_H / 2
                path = f"M{x1},{y1} C{lane},{y1} {lane},{y1} {lane},{y1 + 20} L{lane},{y2 - 20} C{lane},{y2} {lane},{y2} {x2},{y2}"
                mid = (y1 + y2) / 2
                label = _label(
                    to, lane, mid, " / ".join(texts),
                    f"text-anchor='middle' dominant-baseline='central' transform='rotate(-90 {lane} {mid})'",
                )
            edges.append(
                f"<path class='g-edge {to}{' approval' if approval else ''}' d='{path}' marker-end='url(#arrow-{to})'/>"
            )
            if tuple(tools) not in labelled:
                labelled.add(tuple(tools))
                labels.append(label)

    boxes = []
    for node in nodes.values():
        x, y = pos[node.id]
        state = status.get(node.id, "idle")
        # A small ✓ badge on the corner of anything used this turn
        done = (
            f"<g class='g-done'><circle cx='{x + BOX_W - 2}' cy='{y + 2}' r='7'/>"
            f"<text x='{x + BOX_W - 2}' y='{y + 5.5}' text-anchor='middle'>✓</text></g>"
            if state == "done" else ""
        )
        boxes.append(
            f"<g class='g-node kind-{node.kind} status-{state}' data-id='{node.id}'>"
            f"<title>{KIND_LABELS[node.kind]}: {e(node.description)}</title>"
            f"<rect x='{x}' y='{y}' width='{BOX_W}' height='{BOX_H}' rx='{RADIUS[node.kind]}'/>"
            f"<text class='sub' x='{x + BOX_W / 2}' y='{y + 15}' text-anchor='middle'>"
            f"{KIND_ICONS[node.kind]} {KIND_LABELS[node.kind]}</text>"
            f"<text class='title' x='{x + BOX_W / 2}' y='{y + 31}' text-anchor='middle'>{e(node.label)}</text>"
            f"{done}</g>"
        )

    markers = "".join(
        f"<marker id='arrow-to-{kind}' viewBox='0 0 10 10' refX='9' refY='5' markerWidth='7' markerHeight='7' "
        f"orient='auto-start-reverse'><path class='to-{kind}' d='M0,0 L10,5 L0,10 z'/></marker>"
        for kind in KIND_LABELS
    )
    return (
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='Agent architecture graph'>"
        f"<defs>{markers}</defs>" + "".join(edges) + "".join(boxes) + "".join(labels) + "</svg>"
    )


def _legend(notes: str) -> str:
    keys = "".join(
        f"<span class='key'><span class='swatch kind-{kind}'></span>{label}</span>"
        for kind, label in KIND_LABELS.items() if kind != "user"
    )
    return f"<div class='legend'><div class='keys'>{keys}</div>{notes}</div>"


def render_html(status: dict[str, Status] | None = None, view: Literal["tree", "graph"] = "tree") -> str:
    """HTML of the architecture as a tree or a graph. `status` maps node id -> Status."""
    status = status or {}
    if view == "graph":
        return (
            f"<style>{CSS}{GRAPH_CSS}</style><div class='arch'>{render_graph(status)}"
            + _legend(
                "Arrows take the colour of what they call and are labelled with the tool used · "
                "dashed 🔒 = needs your approval · hover a box for details<br>"
                "Thick pulsing border = running · ✓ = used this turn · dashed box = awaiting your approval"
            )
            + "</div>"
        )
    return (
        f"<style>{CSS}</style><div class='arch'><ul>{_render(ROOT, status, None, False)}</ul>"
        + _legend(
            "Small text above a box = the tool used to call it<br>"
            "Pulsing ring = running · ✓ = used this turn · dashed = awaiting your approval"
        )
        + "</div>"
    )
