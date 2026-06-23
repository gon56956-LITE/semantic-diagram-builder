#!/usr/bin/env python3
"""Render a contract-driven semantic diagram to standalone SVG.

This renderer is intentionally conservative: it handles common knowledge maps,
layered topologies, hierarchies, hub-spoke maps, and boundary maps without
external dependencies. For complex layouts, use the SVG as a starting point and
adjust manually while preserving the skill QA rules.
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ACCENTS = {
    "hub": "#2F7DFF",
    "index": "#2F7DFF",
    "query": "#06B6D4",
    "glossary": "#7C3AED",
    "ontology": "#7C3AED",
    "process": "#2F7DFF",
    "quality": "#F97316",
    "risk": "#7C3AED",
    "package": "#22C55E",
    "source": "#334155",
    "registry": "#F97316",
    "capability": "#0EA5E9",
    "evidence": "#64748B",
    "decision": "#F59E0B",
    "object": "#64748B",
}

PALE = {
    "#2F7DFF": "#EFF6FF",
    "#06B6D4": "#ECFEFF",
    "#7C3AED": "#F5F3FF",
    "#F97316": "#FFF7ED",
    "#22C55E": "#ECFDF5",
    "#334155": "#F8FAFC",
    "#0EA5E9": "#F0F9FF",
    "#64748B": "#F8FAFC",
    "#F59E0B": "#FFFBEB",
}

VALID_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

# Stable layout metrics. Keep these named so generated diagrams do not drift
# into inconsistent card heights, row gaps, or layer padding.
LAYOUT = {
    "canvas_margin_x": 70,
    "top_y": 115,
    "card_h": 100,
    "card_min_w": 260,
    "card_max_w": 360,
    "card_col_gap": 56,
    "card_row_gap": 34,
    "layer_label_h": 42,
    "layer_top_pad": 64,
    "layer_bottom_pad": 32,
    "layer_min_h": 170,
    "layer_gap": 32,
    "layer_side_gutter": 110,
}


def e(text: object) -> str:
    return escape(str(text))


def wrap_text(text: str, max_chars: int = 22, max_lines: int = 2) -> list[str]:
    words = str(text).split()
    if not words:
        return [""]
    lines: list[str] = []
    line = words[0]
    for word in words[1:]:
        if len(line) + 1 + len(word) <= max_chars:
            line += " " + word
        else:
            lines.append(line)
            line = word
    lines.append(line)
    if len(lines) > max_lines:
        keep = lines[: max_lines]
        tail = " ".join(lines[max_lines - 1 :])
        keep[-1] = tail[: max_chars - 1].rstrip() + "..."
        return keep
    return lines


def style_block() -> str:
    return """
<defs>
  <filter id="shadow" x="-20%" y="-30%" width="140%" height="170%"><feDropShadow dx="0" dy="8" stdDeviation="8" flood-color="#0F172A" flood-opacity="0.10"/></filter>
  <marker id="arrow" markerWidth="10" markerHeight="10" refX="8.5" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L9,3 z" fill="#334155"/></marker>
  <style>
    .title{font:700 30px Inter,Segoe UI,Aptos,Arial,sans-serif;fill:#0F172A}
    .subtitle{font:400 14px Inter,Segoe UI,Aptos,Arial,sans-serif;fill:#64748B}
    .group-label{font:700 13px Inter,Segoe UI,Aptos,Arial,sans-serif;fill:#475569;letter-spacing:.06em;text-transform:uppercase}
    .card-title{font:700 17px Inter,Segoe UI,Aptos,Arial,sans-serif;fill:#0F172A}
    .card-sub{font:500 12.5px Inter,Segoe UI,Aptos,Arial,sans-serif;fill:#64748B}
    .edge{fill:none;stroke:#334155;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;opacity:.76}
    .edge-dashed{stroke-dasharray:8 8;opacity:.66}
    .note{font:500 12px Inter,Segoe UI,Aptos,Arial,sans-serif;fill:#64748B}
    .icon-line{fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
  </style>
</defs>""".strip()


def icon_svg(kind: str, x: float, y: float, color: str) -> str:
    pale = PALE.get(color, "#F8FAFC")
    k = kind or "object"
    if k in {"index", "moc", "document"}:
        return f'<rect x="{x}" y="{y}" width="18" height="20" rx="3" fill="{pale}" stroke="{color}" stroke-width="1.7"/><path d="M{x+4},{y+6} H{x+14} M{x+4},{y+11} H{x+14} M{x+4},{y+16} H{x+11}" class="icon-line" stroke="{color}"/>'
    if k == "query":
        return f'<circle cx="{x+8}" cy="{y+8}" r="7" fill="{pale}" stroke="{color}" stroke-width="1.7"/><path d="M{x+14},{y+14} L{x+20},{y+20}" class="icon-line" stroke="{color}"/>'
    if k in {"glossary", "ontology"}:
        return f'<path d="M{x},{y} H{x+16} Q{x+20},{y} {x+20},{y+4} V{y+19} H{x} Z" fill="{pale}" stroke="{color}" stroke-width="1.7"/><path d="M{x+5},{y+6} H{x+14} M{x+5},{y+12} H{x+14}" class="icon-line" stroke="{color}"/>'
    if k == "process":
        return f'<circle cx="{x+4}" cy="{y+11}" r="4" fill="{pale}" stroke="{color}" stroke-width="1.6"/><circle cx="{x+18}" cy="{y+4}" r="4" fill="{pale}" stroke="{color}" stroke-width="1.6"/><circle cx="{x+18}" cy="{y+18}" r="4" fill="{pale}" stroke="{color}" stroke-width="1.6"/><path d="M{x+8},{y+11} H{x+12} M{x+14},{y+7} L{x+12},{y+11} L{x+14},{y+15}" class="icon-line" stroke="{color}"/>'
    if k in {"quality", "registry"}:
        return f'<path d="M{x+10},{y} L{x+20},{y+18} H{x} Z" fill="{pale}" stroke="{color}" stroke-width="1.7"/><path d="M{x+10},{y+7} V{y+13} M{x+10},{y+17} V{y+17}" class="icon-line" stroke="{color}"/>'
    if k == "risk":
        return f'<path d="M{x+10},{y} L{x+19},{y+5} V{y+15} L{x+10},{y+20} L{x+1},{y+15} V{y+5} Z" fill="{pale}" stroke="{color}" stroke-width="1.7"/><path d="M{x+6},{y+10} L{x+9},{y+14} L{x+15},{y+6}" class="icon-line" stroke="{color}"/>'
    if k in {"package", "capability"}:
        return f'<rect x="{x}" y="{y+3}" width="20" height="16" rx="3" fill="{pale}" stroke="{color}" stroke-width="1.7"/><path d="M{x},{y+8} H{x+20} M{x+10},{y+3} V{y+19}" class="icon-line" stroke="{color}"/>'
    if k in {"source", "evidence"}:
        return f'<path d="M{x},{y} H{x+14} L{x+20},{y+6} V{y+20} H{x} Z" fill="{pale}" stroke="{color}" stroke-width="1.7"/><path d="M{x+14},{y} V{y+6} H{x+20}" class="icon-line" stroke="{color}"/>'
    if k == "decision":
        return f'<path d="M{x+10},{y} L{x+20},{y+10} L{x+10},{y+20} L{x},{y+10} Z" fill="{pale}" stroke="{color}" stroke-width="1.7"/><path d="M{x+6},{y+10} H{x+14}" class="icon-line" stroke="{color}"/>'
    return f'<circle cx="{x+10}" cy="{y+10}" r="8" fill="{pale}" stroke="{color}" stroke-width="1.7"/><path d="M{x+5},{y+10} H{x+15} M{x+10},{y+5} V{y+15}" class="icon-line" stroke="{color}"/>'


def make_card(node: dict, x: float, y: float, w: float, h: float) -> str:
    kind = node.get("kind", "object")
    color = node.get("accent") or ACCENTS.get(kind, ACCENTS["object"])
    if not VALID_HEX.match(color):
        color = ACCENTS["object"]
    title_lines = wrap_text(node.get("label", node.get("id", "Object")), max_chars=max(14, int(w / 14)), max_lines=2)
    sub = node.get("subtitle", "")
    parts = [f'<g id="node-{e(node.get("id", ""))}">']
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="20" fill="#FFFFFF" stroke="{color}" stroke-width="2.2" filter="url(#shadow)"/>')
    parts.append(icon_svg(kind, x + 24, y + 25, color))
    title_start = y + 31 if len(title_lines) == 1 else y + 26
    for i, line in enumerate(title_lines):
        parts.append(f'<text x="{x+w/2}" y="{title_start+i*20}" text-anchor="middle" class="card-title">{e(line)}</text>')
    if sub:
        sub_y = title_start + len(title_lines) * 20 + 11
        if sub_y > y + h - 16:
            sub_y = y + h - 16
        parts.append(f'<text x="{x+w/2}" y="{sub_y}" text-anchor="middle" class="card-sub">{e(sub)}</text>')
    parts.append('</g>')
    return "".join(parts)


def compute_layout(contract: dict) -> tuple[int, int, dict, dict]:
    nodes = contract.get("nodes", [])
    groups = contract.get("groups", [])
    if not groups:
        groups = [{"id": "default", "label": "Objects", "type": "layer"}]
        for n in nodes:
            n.setdefault("group", "default")
    group_ids = [g["id"] for g in groups]
    by_group = {gid: [] for gid in group_ids}
    no_group = []
    for n in nodes:
        gid = n.get("group")
        if gid in by_group:
            by_group[gid].append(n)
        else:
            no_group.append(n)
    if no_group:
        by_group.setdefault("ungrouped", []).extend(no_group)
        groups.append({"id": "ungrouped", "label": "Ungrouped", "type": "layer"})

    width = int(contract.get("width", 1500))
    margin_x = int(contract.get("canvas_margin_x", LAYOUT["canvas_margin_x"]))
    y = int(contract.get("top_y", LAYOUT["top_y"]))
    card_h = max(96, int(contract.get("card_height", LAYOUT["card_h"])))
    positions = {}
    group_boxes = {}

    for g in groups:
        gid = g["id"]
        gnodes = by_group.get(gid, [])
        n = max(1, len(gnodes))
        max_per_row = int(g.get("max_per_row", contract.get("max_nodes_per_row", 4)))
        rows = math.ceil(n / max_per_row)
        band_h = max(
            int(g.get("height", 0)),
            LAYOUT["layer_min_h"],
            LAYOUT["layer_top_pad"] + rows * card_h + (rows - 1) * LAYOUT["card_row_gap"] + LAYOUT["layer_bottom_pad"],
        )
        group_boxes[gid] = (margin_x, y, width - 2 * margin_x, band_h, g)
        for idx, node in enumerate(gnodes):
            row = idx // max_per_row
            col = idx % max_per_row
            in_row = min(max_per_row, n - row * max_per_row)
            gap = int(g.get("col_gap", contract.get("card_col_gap", LAYOUT["card_col_gap"])))
            usable = width - 2 * margin_x - int(g.get("side_gutter", LAYOUT["layer_side_gutter"]))
            card_w = min(LAYOUT["card_max_w"], max(LAYOUT["card_min_w"], (usable - gap * (in_row - 1)) / in_row))
            row_w = in_row * card_w + (in_row - 1) * gap
            x0 = (width - row_w) / 2
            x = x0 + col * (card_w + gap)
            cy = y + LAYOUT["layer_top_pad"] + row * (card_h + LAYOUT["card_row_gap"])
            positions[node["id"]] = (x, cy, card_w, card_h)
        y += band_h + int(g.get("gap_after", contract.get("layer_gap", LAYOUT["layer_gap"])))
    height = int(max(y + 40, contract.get("height", 800)))
    return width, height, positions, group_boxes


def center_bottom(pos):
    x, y, w, h = pos
    return x + w / 2, y + h


def center_top(pos):
    x, y, w, h = pos
    return x + w / 2, y


def right_mid(pos):
    x, y, w, h = pos
    return x + w, y + h / 2


def left_mid(pos):
    x, y, w, h = pos
    return x, y + h / 2


def edge_path(a, b) -> str:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    # Same visual row: route horizontally so the arrowhead points into the side anchor.
    if abs((ay + ah / 2) - (by + bh / 2)) < 40:
        sx, sy = right_mid(a) if ax < bx else left_mid(a)
        tx, ty = left_mid(b) if ax < bx else right_mid(b)
        return f'M {sx} {sy} L {tx} {ty}'

    # Cross-row edges use a rounded orthogonal elbow. Keep the control point on
    # the actual turn so corners do not curl in the opposite direction.
    sx, sy = center_bottom(a) if ay < by else center_top(a)
    tx, ty = center_top(b) if ay < by else center_bottom(b)
    mid_y = (sy + ty) / 2
    dx = 1 if tx >= sx else -1
    dy = 1 if ty >= sy else -1
    r = min(14, max(4, abs(tx - sx) / 4), max(4, abs(ty - sy) / 4))
    return (
        f'M {sx} {sy} '
        f'L {sx} {mid_y - dy * r} '
        f'Q {sx} {mid_y} {sx + dx * r} {mid_y} '
        f'L {tx - dx * r} {mid_y} '
        f'Q {tx} {mid_y} {tx} {mid_y + dy * r} '
        f'L {tx} {ty}'
    )


def render(contract: dict) -> str:
    width, height, positions, group_boxes = compute_layout(contract)
    nodes = {n["id"]: n for n in contract.get("nodes", [])}
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{e(contract.get("title", "Semantic Diagram"))}">']
    parts.append(style_block())
    parts.append(f'<rect x="0" y="0" width="{width}" height="{height}" rx="28" fill="#F8FBFF"/>')
    title = contract.get("title", "Semantic Diagram")
    subtitle = contract.get("subtitle", "")
    parts.append(f'<text x="{width/2}" y="54" text-anchor="middle" class="title">{e(title)}</text>')
    if subtitle:
        parts.append(f'<text x="{width/2}" y="80" text-anchor="middle" class="subtitle">{e(subtitle)}</text>')

    for gid, (x, y, w, h, g) in group_boxes.items():
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="26" fill="#EEF6FF" opacity="0.58"/>')
        parts.append(f'<text x="{x+28}" y="{y+23}" class="group-label">{e(g.get("label", gid))}</text>')

    # Draw edges behind cards but over group bands.
    for edge in contract.get("edges", []):
        fr, to = edge.get("from"), edge.get("to")
        if fr not in positions or to not in positions:
            continue
        cls = "edge edge-dashed" if edge.get("style") == "dashed" else "edge"
        parts.append(f'<path d="{edge_path(positions[fr], positions[to])}" class="{cls}" marker-end="url(#arrow)"/>')

    for node_id, pos in positions.items():
        parts.append(make_card(nodes[node_id], *pos))

    footer_y = height - 28
    footer_notes = [a for a in contract.get("annotations", []) if a.get("placement", "footer") == "footer"]
    for i, ann in enumerate(footer_notes[:3]):
        parts.append(f'<text x="{width/2}" y="{footer_y - (len(footer_notes[:3])-1-i)*17}" text-anchor="middle" class="note">{e(ann.get("text", ""))}</text>')

    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: render_semantic_diagram.py contract.json output.svg", file=sys.stderr)
        return 2
    contract_path = Path(argv[1])
    output_path = Path(argv[2])
    contract = json.loads(contract_path.read_text(encoding="utf-8-sig"))
    svg = render(contract)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(svg, encoding="utf-8", newline="\n")
    print(f"wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
