#!/usr/bin/env python3
"""Render a contract-driven semantic diagram to standalone SVG.

This renderer is intentionally conservative: it handles common grouped/layered
semantic diagrams without external dependencies. For complex layouts, use the
SVG as a starting point and adjust manually while preserving the skill QA rules.
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
SCRIPT_SUPPORTED_LAYOUTS = {"auto", "layered"}

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
    "bus_to_card_clearance": 32,
    "bus_bottom_clearance": 18,
    "bus_lane_gap": 48,
    "side_trunk_gutter": 130,
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
  <marker id="arrow-fanout" markerWidth="10" markerHeight="10" refX="8.5" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L9,3 z" fill="#2563EB"/></marker>
  <marker id="arrow-fanin" markerWidth="10" markerHeight="10" refX="8.5" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L9,3 z" fill="#16A34A"/></marker>
  <style>
    .title{font:700 30px Inter,Segoe UI,Aptos,Arial,sans-serif;fill:#0F172A}
    .subtitle{font:400 14px Inter,Segoe UI,Aptos,Arial,sans-serif;fill:#64748B}
    .group-label{font:700 13px Inter,Segoe UI,Aptos,Arial,sans-serif;fill:#475569;letter-spacing:.06em;text-transform:uppercase}
    .card-title{font:700 17px Inter,Segoe UI,Aptos,Arial,sans-serif;fill:#0F172A}
    .card-sub{font:500 12.5px Inter,Segoe UI,Aptos,Arial,sans-serif;fill:#64748B}
    .edge{fill:none;stroke:#334155;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;opacity:.76}
    .fanout{stroke:#2563EB;opacity:.74}
    .fanin{stroke:#16A34A;opacity:.74}
    .route-shared{marker-end:none}
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
    parts = [f'<g id="node-{e(node.get("id", ""))}" class="card node-card">']
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


def _num(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _rounded_path(points: list[tuple[float, float]], radius: float = 14) -> str:
    clean: list[tuple[float, float]] = []
    for x, y in points:
        pt = (round(float(x), 2), round(float(y), 2))
        if not clean or abs(clean[-1][0] - pt[0]) > 1e-6 or abs(clean[-1][1] - pt[1]) > 1e-6:
            clean.append(pt)
    if not clean:
        return ""
    if len(clean) == 1:
        return f"M {clean[0][0]} {clean[0][1]}"

    parts = [f"M {clean[0][0]} {clean[0][1]}"]
    for idx in range(1, len(clean) - 1):
        prev_x, prev_y = clean[idx - 1]
        x, y = clean[idx]
        next_x, next_y = clean[idx + 1]
        in_axis = "v" if abs(prev_x - x) < 1e-6 else "h" if abs(prev_y - y) < 1e-6 else None
        out_axis = "v" if abs(next_x - x) < 1e-6 else "h" if abs(next_y - y) < 1e-6 else None
        if not in_axis or not out_axis or in_axis == out_axis:
            parts.append(f"L {x} {y}")
            continue
        r = min(radius, abs(prev_x - x) / 2 + abs(prev_y - y) / 2, abs(next_x - x) / 2 + abs(next_y - y) / 2)
        if r < 1:
            parts.append(f"L {x} {y}")
            continue
        in_x = x - math.copysign(r, x - prev_x) if abs(x - prev_x) > 1e-6 else x
        in_y = y - math.copysign(r, y - prev_y) if abs(y - prev_y) > 1e-6 else y
        out_x = x + math.copysign(r, next_x - x) if abs(next_x - x) > 1e-6 else x
        out_y = y + math.copysign(r, next_y - y) if abs(next_y - y) > 1e-6 else y
        parts.append(f"L {round(in_x, 2)} {round(in_y, 2)}")
        parts.append(f"Q {x} {y} {round(out_x, 2)} {round(out_y, 2)}")
    end_x, end_y = clean[-1]
    parts.append(f"L {end_x} {end_y}")
    return " ".join(parts)


def _node_group_map(nodes: list[dict], group_ids: set[str]) -> dict[str, str]:
    mapping = {}
    for node in nodes:
        node_id = node.get("id")
        if not node_id:
            continue
        gid = node.get("group")
        mapping[node_id] = gid if gid in group_ids else "ungrouped"
    return mapping


def _connector_stats(nodes: list[dict], groups: list[dict], edges: list[dict]) -> dict:
    group_ids = {g["id"] for g in groups}
    node_groups = _node_group_map(nodes, group_ids)
    group_order = {g["id"]: idx for idx, g in enumerate(groups)}
    fanout_targets: dict[tuple[str, str], list[str]] = {}
    fanin_sources: dict[tuple[str, str], list[str]] = {}

    for edge in edges:
        fr, to = edge.get("from"), edge.get("to")
        if fr not in node_groups or to not in node_groups:
            continue
        sg, tg = node_groups[fr], node_groups[to]
        if sg == tg:
            continue
        if group_order.get(sg, 0) >= group_order.get(tg, 0):
            continue
        fanout_targets.setdefault((fr, tg), []).append(to)
        fanin_sources.setdefault((sg, to), []).append(fr)

    fanout_families = {key: vals for key, vals in fanout_targets.items() if len(set(vals)) > 1}
    fanin_families = {key: vals for key, vals in fanin_sources.items() if len(set(vals)) > 1}

    return {
        "node_groups": node_groups,
        "group_order": group_order,
        "fanout_families": fanout_families,
        "fanin_families": fanin_families,
        "fanout_groups": {tg for (_fr, tg) in fanout_families},
        "fanin_groups": {sg for (sg, _to) in fanin_families},
    }


def _assign_rows(gnodes: list[dict], max_per_row: int) -> dict:
    assignments: dict[str, tuple[int, int]] = {}
    explicit_nodes: set[str] = set()
    used: set[tuple[int, int]] = set()
    auto_nodes = []

    for node in gnodes:
        node_id = node.get("id")
        if not node_id:
            continue
        if node.get("row") is None and node.get("col") is None:
            auto_nodes.append(node)
            continue
        row = max(0, _num(node.get("row"), 0))
        col = max(0, _num(node.get("col"), 0))
        while (row, col) in used:
            col += 1
        assignments[node_id] = (row, col)
        explicit_nodes.add(node_id)
        used.add((row, col))

    cursor = 0
    for node in auto_nodes:
        node_id = node.get("id")
        if not node_id:
            continue
        while True:
            row = cursor // max_per_row
            col = cursor % max_per_row
            cursor += 1
            if (row, col) not in used:
                break
        assignments[node_id] = (row, col)
        used.add((row, col))

    rows: dict[int, list[dict]] = {}
    row_explicit: dict[int, bool] = {}
    for node in gnodes:
        node_id = node.get("id")
        if node_id not in assignments:
            continue
        row, _col = assignments[node_id]
        rows.setdefault(row, []).append(node)
        row_explicit[row] = row_explicit.get(row, False) or node_id in explicit_nodes
    for row_nodes in rows.values():
        row_nodes.sort(key=lambda n: assignments[n["id"]][1])
    return {"assignments": assignments, "rows": rows, "row_explicit": row_explicit}


def build_layout_model(contract: dict) -> dict:
    nodes = list(contract.get("nodes", []))
    groups = [dict(g) for g in contract.get("groups", [])]
    if not groups:
        groups = [{"id": "default", "label": "Objects", "type": "layer"}]
        nodes = [dict(n, group=n.get("group", "default")) for n in nodes]
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

    stats = _connector_stats(nodes, groups, contract.get("edges", []))

    width = int(contract.get("width", 1500))
    margin_x = int(contract.get("canvas_margin_x", LAYOUT["canvas_margin_x"]))
    y = int(contract.get("top_y", LAYOUT["top_y"]))
    card_h = max(96, int(contract.get("card_height", LAYOUT["card_h"])))
    positions = {}
    group_boxes = {}
    group_layouts = {}

    for g in groups:
        gid = g["id"]
        gnodes = by_group.get(gid, [])
        max_per_row = max(1, int(g.get("max_per_row", contract.get("max_nodes_per_row", 4))))
        row_model = _assign_rows(gnodes, max_per_row)
        rows = row_model["rows"]
        row_ids = sorted(rows) or [0]
        row_count = max(1, len(row_ids))

        routing = g.get("routing") if isinstance(g.get("routing"), dict) else {}
        requested_mode = routing.get("mode", "auto")
        has_fanout = gid in stats["fanout_groups"]
        has_fanin = gid in stats["fanin_groups"]
        use_row_bus = requested_mode == "row_bus_side_trunk" or (
            requested_mode == "auto" and row_count > 1 and (has_fanout or has_fanin)
        )
        mode = "row_bus_side_trunk" if use_row_bus else "simple"

        row_gap = max(
            int(g.get("row_gap", contract.get("card_row_gap", LAYOUT["card_row_gap"]))),
            LAYOUT["card_row_gap"],
        )
        if mode == "row_bus_side_trunk" and row_count > 1:
            if has_fanout and has_fanin:
                row_gap = max(row_gap, 2 * LAYOUT["bus_to_card_clearance"] + LAYOUT["bus_lane_gap"])
            else:
                row_gap = max(row_gap, LAYOUT["bus_to_card_clearance"] + LAYOUT["bus_bottom_clearance"])

        top_pad = int(g.get("top_pad", contract.get("layer_top_pad", LAYOUT["layer_top_pad"])))
        bottom_pad = int(g.get("bottom_pad", contract.get("layer_bottom_pad", LAYOUT["layer_bottom_pad"])))
        if mode == "row_bus_side_trunk" and has_fanout:
            top_pad = max(top_pad, LAYOUT["layer_label_h"] + LAYOUT["bus_to_card_clearance"])
        if mode == "row_bus_side_trunk" and has_fanin:
            bottom_pad = max(bottom_pad, LAYOUT["bus_to_card_clearance"] + LAYOUT["bus_bottom_clearance"])

        band_h = max(
            int(g.get("height", 0)),
            LAYOUT["layer_min_h"],
            top_pad + row_count * card_h + (row_count - 1) * row_gap + bottom_pad,
        )
        group_boxes[gid] = (margin_x, y, width - 2 * margin_x, band_h, g)

        side_gutter = int(g.get("side_gutter", routing.get("side_gutter", LAYOUT["layer_side_gutter"])))
        if mode == "row_bus_side_trunk":
            side_gutter = max(side_gutter, LAYOUT["side_trunk_gutter"])
        gap = int(g.get("col_gap", contract.get("card_col_gap", LAYOUT["card_col_gap"])))
        layer_w = width - 2 * margin_x
        usable = layer_w - (2 * side_gutter if mode == "row_bus_side_trunk" else side_gutter)

        row_infos = {}
        for row_ordinal, row_id in enumerate(row_ids):
            row_nodes = rows.get(row_id, [])
            explicit_row = row_model["row_explicit"].get(row_id, False)
            if explicit_row:
                slots = max(row_model["assignments"][n["id"]][1] for n in row_nodes) + 1
            else:
                slots = len(row_nodes)
            slots = max(1, slots)
            card_w = min(LAYOUT["card_max_w"], max(LAYOUT["card_min_w"], (usable - gap * (slots - 1)) / slots))
            row_w = slots * card_w + (slots - 1) * gap
            x0 = (width - row_w) / 2
            row_top = y + top_pad + row_ordinal * (card_h + row_gap)
            for compact_col, node in enumerate(row_nodes):
                assigned_col = row_model["assignments"][node["id"]][1]
                col = assigned_col if explicit_row else compact_col
                x = x0 + col * (card_w + gap)
                positions[node["id"]] = (x, row_top, card_w, card_h)
            row_infos[row_id] = {
                "top": row_top,
                "bottom": row_top + card_h,
                "fanout_bus_y": row_top - LAYOUT["bus_to_card_clearance"],
                "fanin_bus_y": row_top + card_h + LAYOUT["bus_to_card_clearance"],
                "nodes": [n.get("id") for n in row_nodes],
            }
        group_layouts[gid] = {
            "box": group_boxes[gid],
            "mode": mode,
            "routing": routing,
            "rows": row_infos,
            "assignments": row_model["assignments"],
            "side_gutter": side_gutter,
            "fanout_side": routing.get("fanout_side", "right"),
            "fanin_side": routing.get("fanin_side", "left"),
        }
        y += band_h + int(g.get("gap_after", contract.get("layer_gap", LAYOUT["layer_gap"])))
    height = int(max(y + 40, contract.get("height", 800)))
    return {
        "width": width,
        "height": height,
        "positions": positions,
        "group_boxes": group_boxes,
        "group_layouts": group_layouts,
        "groups": groups,
        "stats": stats,
    }


def compute_layout(contract: dict) -> tuple[int, int, dict, dict]:
    model = build_layout_model(contract)
    return model["width"], model["height"], model["positions"], model["group_boxes"]


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


def edge_path(a, b, bus_y: float | None = None) -> str:
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
    if abs(tx - sx) < 1e-6:
        return f'M {sx} {sy} L {tx} {ty}'
    mid_y = bus_y if bus_y is not None else (sy + ty) / 2
    dx = 1 if tx >= sx else -1
    dy_start = 1 if mid_y >= sy else -1
    dy_end = 1 if ty >= mid_y else -1
    r = max(4, min(14, abs(tx - sx) / 4, abs(mid_y - sy) / 2, abs(ty - mid_y) / 2))
    return (
        f'M {sx} {sy} '
        f'L {sx} {mid_y - dy_start * r} '
        f'Q {sx} {mid_y} {sx + dx * r} {mid_y} '
        f'L {tx - dx * r} {mid_y} '
        f'Q {tx} {mid_y} {tx} {mid_y + dy_end * r} '
        f'L {tx} {ty}'
    )


def _unique(ids: list[str]) -> list[str]:
    seen = set()
    out = []
    for value in ids:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _row_for(layout: dict, node_id: str) -> int | None:
    assigned = layout["assignments"].get(node_id)
    return assigned[0] if assigned else None


def _side_x(layout: dict, side: str) -> float:
    x, _y, w, _h, _g = layout["box"]
    if side == "left":
        return x + layout["side_gutter"] / 2
    return x + w - layout["side_gutter"] / 2


def _path(d: str, classes: str, marker: str | None = None) -> str:
    marker_attr = f' marker-end="url(#{marker})"' if marker else ""
    return f'<path d="{d}" class="{classes}"{marker_attr}/>'


def _vertical_branch(x: float, start_y: float, end_y: float) -> str:
    return _rounded_path([(x, start_y), (x, end_y)])


def _horizontal_bus(points: list[float], y: float) -> str:
    return _rounded_path([(min(points), y), (max(points), y)])


def _horizontal_bus_segments(points: list[float], y: float, gap: tuple[float, float] | None = None) -> list[str]:
    clean = sorted({round(float(x), 2) for x in points})
    if len(clean) < 2:
        return []
    if gap is None:
        return [_horizontal_bus(clean, y)]

    gap_left, gap_right = sorted(gap)
    segments = []
    left = [x for x in clean if x <= gap_left + 1e-6]
    right = [x for x in clean if x >= gap_right - 1e-6]
    if len(left) >= 2 and max(left) - min(left) > 1e-6:
        segments.append(_horizontal_bus(left, y))
    if len(right) >= 2 and max(right) - min(right) > 1e-6:
        segments.append(_horizontal_bus(right, y))
    return segments


def _branch_radius(a: float, b: float) -> float:
    return min(14, max(4, abs(a - b) / 2))


def _direction_toward(x: float, target_x: float) -> int:
    return 1 if target_x >= x else -1


def _curve_to_bus_toward(x: float, start_y: float, bus_y: float, toward_x: float) -> tuple[str, float]:
    direction = _direction_toward(x, toward_x)
    r = _branch_radius(start_y, bus_y)
    anchor_x = x + direction * r
    return _rounded_path([(x, start_y), (x, bus_y), (anchor_x, bus_y)]), anchor_x


def _split_curve_to_bus(x: float, start_y: float, bus_y: float) -> tuple[list[str], tuple[float, float]]:
    r = _branch_radius(start_y, bus_y)
    left_anchor = x - r
    right_anchor = x + r
    return (
        [
            _rounded_path([(x, start_y), (x, bus_y), (left_anchor, bus_y)]),
            _rounded_path([(x, start_y), (x, bus_y), (right_anchor, bus_y)]),
        ],
        (left_anchor, right_anchor),
    )


def _curve_from_bus_from_side(x: float, bus_y: float, target_y: float, from_x: float) -> tuple[str, float]:
    direction = _direction_toward(from_x, x)
    r = _branch_radius(bus_y, target_y)
    anchor_x = x - direction * r
    return _rounded_path([(anchor_x, bus_y), (x, bus_y), (x, target_y)]), anchor_x


def _split_curve_from_bus(x: float, bus_y: float, target_y: float) -> tuple[list[str], tuple[float, float], float]:
    r = _branch_radius(bus_y, target_y)
    left_anchor = x - r
    right_anchor = x + r
    stem_y = bus_y + math.copysign(r, target_y - bus_y)
    return (
        [
            _rounded_path([(left_anchor, bus_y), (x, bus_y), (x, stem_y)]),
            _rounded_path([(right_anchor, bus_y), (x, bus_y), (x, stem_y)]),
        ],
        (left_anchor, right_anchor),
        stem_y,
    )


def _fanout_family_paths(source_id: str, target_group: str, target_ids: list[str], model: dict) -> tuple[list[str], set[tuple[str, str]]]:
    positions = model["positions"]
    layout = model["group_layouts"].get(target_group)
    if not layout or layout["mode"] != "row_bus_side_trunk" or source_id not in positions:
        return [], set()

    row_targets: dict[int, list[str]] = {}
    for target_id in _unique(target_ids):
        if target_id not in positions:
            continue
        row = _row_for(layout, target_id)
        if row is None:
            continue
        row_targets.setdefault(row, []).append(target_id)
    if not row_targets:
        return [], set()

    paths = []
    routed = {(source_id, target_id) for targets in row_targets.values() for target_id in targets}
    sx, sy = center_bottom(positions[source_id])
    side = layout.get("fanout_side", "right")
    trunk_x = _side_x(layout, side)
    first_row = min(row_targets)
    first_bus_y = layout["rows"][first_row]["fanout_bus_y"]
    has_lower_rows = any(row != first_row for row in row_targets)
    trunk_inward = -1 if side == "right" else 1
    trunk_anchor_x = trunk_x + trunk_inward * 14

    first_targets = row_targets[first_row]
    first_target_centers = [center_top(positions[target_id])[0] for target_id in first_targets]
    source_bus_gap: tuple[float, float] | None = None
    if min(first_target_centers) < sx < max(first_target_centers):
        source_paths, source_bus_gap = _split_curve_to_bus(sx, sy, first_bus_y)
        source_bus_anchors = list(source_bus_gap)
        for source_path in source_paths:
            paths.append(_path(source_path, "edge fanout route-shared branch"))
    else:
        source_path, source_bus_anchor = _curve_to_bus_toward(
            sx,
            sy,
            first_bus_y,
            (min(first_target_centers) + max(first_target_centers)) / 2,
        )
        source_bus_anchors = [source_bus_anchor]
        paths.append(_path(source_path, "edge fanout route-shared branch"))

    for row in sorted(row_targets):
        if row == first_row:
            continue
        bus_y = layout["rows"][row]["fanout_bus_y"]
        paths.append(
            _path(
                _rounded_path([(trunk_anchor_x, first_bus_y), (trunk_x, first_bus_y), (trunk_x, bus_y), (trunk_anchor_x, bus_y)]),
                "edge fanout route-shared trunk",
            )
        )

    for row in sorted(row_targets):
        targets = row_targets[row]
        bus_y = layout["rows"][row]["fanout_bus_y"]
        terminal_anchors = []
        upstream_x = sx if row == first_row else trunk_x
        if row == first_row:
            bus_points = list(source_bus_anchors)
            if has_lower_rows:
                bus_points.append(trunk_anchor_x)
        else:
            bus_points = [trunk_anchor_x]
        for target_id in targets:
            tx, ty = center_top(positions[target_id])
            terminal_path, terminal_anchor = _curve_from_bus_from_side(tx, bus_y, ty, upstream_x)
            terminal_anchors.append((terminal_path, terminal_anchor))
            bus_points.append(terminal_anchor)
        bus_gap = source_bus_gap if row == first_row else None
        for bus_d in _horizontal_bus_segments(bus_points, bus_y, bus_gap):
            paths.append(_path(bus_d, "edge fanout route-shared bus"))
        for terminal_path, _terminal_anchor in terminal_anchors:
            paths.append(_path(terminal_path, "edge fanout terminal", "arrow-fanout"))
    return paths, routed


def _fanin_family_paths(source_group: str, target_id: str, source_ids: list[str], model: dict) -> tuple[list[str], set[tuple[str, str]]]:
    positions = model["positions"]
    layout = model["group_layouts"].get(source_group)
    if not layout or layout["mode"] != "row_bus_side_trunk" or target_id not in positions:
        return [], set()

    row_sources: dict[int, list[str]] = {}
    for source_id in _unique(source_ids):
        if source_id not in positions:
            continue
        row = _row_for(layout, source_id)
        if row is None:
            continue
        row_sources.setdefault(row, []).append(source_id)
    if not row_sources:
        return [], set()

    paths = []
    routed = {(source_id, target_id) for sources in row_sources.values() for source_id in sources}
    side = layout.get("fanin_side", "left")
    trunk_x = _side_x(layout, side)
    trunk_inward = 1 if side == "left" else -1
    trunk_anchor_x = trunk_x + trunk_inward * 14
    row_bus_ys = [layout["rows"][row]["fanin_bus_y"] for row in row_sources]
    first_bus_y = min(row_bus_ys)
    join_y = max(row_bus_ys)
    tx, ty = center_top(positions[target_id])
    aligned_sources = []
    for source_id in _unique(source_ids):
        if source_id not in positions:
            continue
        sx, sy = center_bottom(positions[source_id])
        if abs(sx - tx) < 1e-6 and sy <= ty:
            aligned_sources.append((sy, source_id))
    direct_source_id = max(aligned_sources)[1] if aligned_sources else None

    if abs(first_bus_y - join_y) > 1e-6:
        paths.append(
            _path(
                _rounded_path([(trunk_anchor_x, first_bus_y), (trunk_x, first_bus_y), (trunk_x, join_y), (trunk_anchor_x, join_y)]),
                "edge fanin route-shared trunk",
            )
        )

    terminal_merge_paths: list[str] = []
    terminal_anchors: list[float] = []
    terminal_gap: tuple[float, float] | None = None
    terminal_marker_path = ""
    if direct_source_id:
        _dsx, direct_start_y = center_bottom(positions[direct_source_id])
        terminal_marker_path = _vertical_branch(tx, direct_start_y, ty)

    for row in sorted(row_sources):
        sources = row_sources[row]
        bus_y = layout["rows"][row]["fanin_bus_y"]
        source_centers = []
        for source_id in sources:
            if source_id == direct_source_id:
                continue
            sx, sy = center_bottom(positions[source_id])
            source_path, source_anchor = _curve_to_bus_toward(sx, sy, bus_y, trunk_x)
            source_centers.append(source_anchor)
            paths.append(_path(source_path, "edge fanin route-shared branch"))
        if abs(bus_y - join_y) <= 1e-6:
            source_span = source_centers + [trunk_anchor_x]
            if direct_source_id and min(source_span) < tx < max(source_span):
                terminal_merge_paths, terminal_gap, terminal_start_y = _split_curve_from_bus(tx, join_y, ty)
                terminal_anchors = list(terminal_gap)
            elif min(source_span) < tx < max(source_span):
                terminal_merge_paths, terminal_gap, terminal_start_y = _split_curve_from_bus(tx, join_y, ty)
                terminal_anchors = list(terminal_gap)
                terminal_marker_path = _vertical_branch(tx, terminal_start_y, ty)
            else:
                terminal_path, terminal_anchor = _curve_from_bus_from_side(tx, join_y, ty, trunk_x)
                if direct_source_id:
                    terminal_merge_paths = [terminal_path]
                    terminal_anchors = [terminal_anchor]
                else:
                    terminal_anchors = [terminal_anchor]
                    terminal_marker_path = terminal_path
            bus_points = source_span + terminal_anchors
            bus_gap = terminal_gap
        else:
            bus_points = source_centers + [trunk_anchor_x]
            bus_gap = None
        for bus_d in _horizontal_bus_segments(bus_points, bus_y, bus_gap):
            paths.append(_path(bus_d, "edge fanin route-shared bus"))

    for terminal_path in terminal_merge_paths:
        paths.append(_path(terminal_path, "edge fanin route-shared merge"))
    paths.append(_path(terminal_marker_path, "edge fanin terminal", "arrow-fanin"))
    return paths, routed


def routed_edge_paths(model: dict, edges: list[dict]) -> list[str]:
    paths = []
    routed_edges: set[tuple[str, str]] = set()
    stats = model["stats"]
    for (source_id, target_group), target_ids in stats["fanout_families"].items():
        family_paths, family_edges = _fanout_family_paths(source_id, target_group, target_ids, model)
        paths.extend(family_paths)
        routed_edges.update(family_edges)
    for (source_group, target_id), source_ids in stats["fanin_families"].items():
        family_paths, family_edges = _fanin_family_paths(source_group, target_id, source_ids, model)
        paths.extend(family_paths)
        routed_edges.update(family_edges)

    positions = model["positions"]
    for edge in edges:
        fr, to = edge.get("from"), edge.get("to")
        if fr not in positions or to not in positions or (fr, to) in routed_edges:
            continue
        cls = "edge edge-dashed" if edge.get("style") == "dashed" else "edge"
        paths.append(_path(edge_path(positions[fr], positions[to]), cls, "arrow"))
    return paths


def render(contract: dict) -> str:
    model = build_layout_model(contract)
    width = model["width"]
    height = model["height"]
    positions = model["positions"]
    group_boxes = model["group_boxes"]
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
    parts.extend(routed_edge_paths(model, contract.get("edges", [])))

    for node_id, pos in positions.items():
        parts.append(make_card(nodes[node_id], *pos))

    legend_notes = [a for a in contract.get("annotations", []) if a.get("placement") == "legend"]
    if legend_notes:
        legend_x = width - 330
        legend_y = height - 84 - (len(legend_notes) - 1) * 20
        for i, ann in enumerate(legend_notes[:4]):
            color = ann.get("color", "#64748B")
            if not VALID_HEX.match(color):
                color = "#64748B"
            parts.append(f'<text x="{legend_x}" y="{legend_y + i*20}" class="note" fill="{color}">{e(ann.get("text", ""))}</text>')

    footer_y = height - 28
    footer_notes = [a for a in contract.get("annotations", []) if a.get("placement", "footer") == "footer"]
    for i, ann in enumerate(footer_notes[:3]):
        parts.append(f'<text x="{width/2}" y="{footer_y - (len(footer_notes[:3])-1-i)*17}" text-anchor="middle" class="note">{e(ann.get("text", ""))}</text>')

    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def contract_warnings(contract: dict) -> list[str]:
    warnings: list[str] = []
    layout = contract.get("layout", "auto")
    if layout not in SCRIPT_SUPPORTED_LAYOUTS:
        warnings.append(
            f'layout "{layout}" is not rendered specially; falling back to grouped/layered placement'
        )

    node_ids = [n.get("id") for n in contract.get("nodes", []) if n.get("id")]
    node_id_set = set(node_ids)
    if len(node_ids) != len(node_id_set):
        warnings.append("duplicate node ids may collapse cards or edges")

    skipped_edges = []
    for edge in contract.get("edges", []):
        fr, to = edge.get("from"), edge.get("to")
        if fr not in node_id_set or to not in node_id_set:
            skipped_edges.append(f"{fr}->{to}")
    if skipped_edges:
        examples = ", ".join(skipped_edges[:5])
        suffix = "..." if len(skipped_edges) > 5 else ""
        warnings.append(f"edges with missing endpoints will be skipped: {examples}{suffix}")

    unsupported_annotations = [
        a.get("placement", "footer")
        for a in contract.get("annotations", [])
        if a.get("placement", "footer") not in {"footer", "legend"}
    ]
    if unsupported_annotations:
        placements = ", ".join(sorted(set(str(p) for p in unsupported_annotations)))
        warnings.append(f"non-footer annotations are contract guidance only and were not rendered: {placements}")

    labeled_edges = [edge for edge in contract.get("edges", []) if edge.get("label")]
    if labeled_edges:
        warnings.append("edge labels are contract guidance only and were not rendered")
    return warnings


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: render_semantic_diagram.py contract.json output.svg", file=sys.stderr)
        return 2
    contract_path = Path(argv[1])
    output_path = Path(argv[2])
    contract = json.loads(contract_path.read_text(encoding="utf-8-sig"))
    for warning in contract_warnings(contract):
        print(f"warning: {warning}", file=sys.stderr)
    svg = render(contract)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(svg, encoding="utf-8", newline="\n")
    print(f"wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
