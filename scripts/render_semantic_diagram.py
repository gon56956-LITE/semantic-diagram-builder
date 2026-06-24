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

from semantic_diagram_styles import (
    StyleError,
    color as style_color,
    kind_accent,
    load_style_package,
    metric as style_metric,
    paint as style_paint,
    paint_attrs,
    pale_for,
    style_id,
    token as style_token,
    validate_style_package,
)
from semantic_diagram_types import DiagramTypeError, normalize_diagram_type, validate_contract_schema


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


def style_for_contract(contract: dict, contract_path: Path | None = None) -> dict:
    return load_style_package(contract.get("style"), contract_path)


def diagram_for_contract(contract: dict) -> tuple[str, str, list[str]]:
    return normalize_diagram_type(contract)


def layout_metrics(style: dict | None = None) -> dict:
    metrics = dict(LAYOUT)
    if style:
        for key, default in LAYOUT.items():
            metrics[key] = style_metric(style, key, default)
    return metrics


def _paint_attr(style: dict, attr: str, value: object, default: str, opacity: object = None) -> str:
    extra_opacity = opacity if isinstance(opacity, (int, float)) else None
    return paint_attrs(style, attr, value, default, extra_opacity)


def _style_component(style: dict, name: str) -> dict:
    component = style_token(style, f"components.{name}", {})
    return component if isinstance(component, dict) else {}


def _font_css(style: dict, path: str, default: str) -> str:
    value = style_token(style, path, default)
    return str(value or default)


def _px(value: object, default: float) -> float:
    match = re.match(r"^\s*([0-9.]+)", str(value or ""))
    if not match:
        return default
    try:
        return float(match.group(1))
    except ValueError:
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _fmt_px(value: float) -> str:
    return f"{round(value, 1):g}px"


def _card_text_metrics(style: dict, canvas_w: float) -> dict[str, float]:
    title_token = _px(style_token(style, "tokens.typography.card_title_size", "18px"), 18)
    sub_token = _px(style_token(style, "tokens.typography.card_sub_size", "13.5px"), 13.5)
    canvas_scale = _clamp(canvas_w / 1500.0, 0.92, 1.08)
    title_size = _clamp(21.5 * canvas_scale, max(20.5, title_token), 23.5)
    sub_size = _clamp(16.0 * canvas_scale, max(15.5, sub_token), 17.5)
    return {
        "title_size": title_size,
        "sub_size": sub_size,
        "title_line_h": max(title_size + 1.5, title_size * 1.08),
        "sub_line_h": max(sub_size + 1.5, sub_size * 1.1),
        "sub_gap": _clamp(title_size * 0.18, 3.0, 5.0),
    }


def _number(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _table_text_metrics(style: dict, canvas_w: float) -> dict[str, float]:
    table = _style_component(style, "table")
    header_token = _px(table.get("header_size", style_token(style, "tokens.typography.group_label_size", "13px")), 13)
    cell_token = _px(table.get("cell_size", style_token(style, "tokens.typography.card_sub_size", "13px")), 13)
    canvas_scale = _clamp(canvas_w / 1500.0, 0.92, 1.08)
    header_size = _clamp(16.0 * canvas_scale, max(14.5, header_token), 17.5)
    cell_size = _clamp(17.5 * canvas_scale, max(16.0, cell_token), 19.0)
    line_h = max(cell_size * 1.25, cell_size + 4)
    return {
        "header_size": header_size,
        "cell_size": cell_size,
        "line_h": line_h,
        "header_h": max(58.0, header_size * 3.8),
        "row_h": max(92.0, line_h * 3 + 28),
    }


def _css_attr(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def style_block(style: dict) -> str:
    typography = style_token(style, "tokens.typography", {})
    if not isinstance(typography, dict):
        typography = {}
    sans = typography.get("sans", "Inter,Segoe UI,Aptos,Arial,sans-serif")
    mono = typography.get("mono", "IBM Plex Mono,JetBrains Mono,Consolas,monospace")
    title_family = typography.get("title", sans)
    title_case = typography.get("title_transform", "none")

    connector = _style_component(style, "connector")
    arrow = style_color(style, connector.get("primary", "line_primary"), "#334155")
    fanout = style_color(style, connector.get("fanout", "accent_cyan"), "#2563EB")
    fanin = style_color(style, connector.get("fanin", "accent_green"), "#16A34A")
    edge_width = connector.get("stroke_width", 2)
    edge_opacity = connector.get("opacity", 0.76)
    fanout_opacity = connector.get("fanout_opacity", edge_opacity)
    fanin_opacity = connector.get("fanin_opacity", edge_opacity)
    table = _style_component(style, "table")
    table_header_size = table.get("header_size", style_token(style, "tokens.typography.group_label_size", "13px"))
    table_cell_size = table.get("cell_size", style_token(style, "tokens.typography.card_sub_size", "12.5px"))
    scope = f'[data-style="{_css_attr(style_id(style))}"]'

    card = _style_component(style, "card")
    shadow = card.get("shadow", {})
    shadow_enabled = bool(shadow.get("enabled", True)) if isinstance(shadow, dict) else bool(shadow)
    shadow_def = ""
    if shadow_enabled:
        shadow_color = style_color(style, shadow.get("color", "#0F172A") if isinstance(shadow, dict) else "#0F172A", "#0F172A")
        shadow_opacity = shadow.get("opacity", 0.10) if isinstance(shadow, dict) else 0.10
        shadow_dy = shadow.get("dy", 8) if isinstance(shadow, dict) else 8
        shadow_blur = shadow.get("blur", 8) if isinstance(shadow, dict) else 8
        shadow_def = f'\n  <filter id="shadow" x="-20%" y="-30%" width="140%" height="170%"><feDropShadow dx="0" dy="{shadow_dy}" stdDeviation="{shadow_blur}" flood-color="{shadow_color}" flood-opacity="{shadow_opacity}"/></filter>'

    grid = style_token(style, "tokens.grid", {})
    grid_defs = ""
    if isinstance(grid, dict) and grid.get("enabled"):
        small = grid.get("size", 16)
        large = grid.get("strong_every", 5) * small if isinstance(grid.get("strong_every", 5), (int, float)) else 80
        line_color, line_opacity = style_paint(style, grid.get("line", "grid_line"), "#FFFFFF")
        strong_color, strong_opacity = style_paint(style, grid.get("strong_line", "grid_line_strong"), "#FFFFFF")
        grid_defs = f"""
  <pattern id="blueprint-grid-small" width="{small}" height="{small}" patternUnits="userSpaceOnUse"><path d="M {small} 0 H 0 V {small}" fill="none" stroke="{line_color}" stroke-opacity="{line_opacity if line_opacity is not None else 0.08}" stroke-width="0.7"/></pattern>
  <pattern id="blueprint-grid" width="{large}" height="{large}" patternUnits="userSpaceOnUse"><rect width="{large}" height="{large}" fill="url(#blueprint-grid-small)"/><path d="M {large} 0 H 0 V {large}" fill="none" stroke="{strong_color}" stroke-opacity="{strong_opacity if strong_opacity is not None else 0.14}" stroke-width="1"/> </pattern>"""

    extra_defs = "\n".join(part.strip() for part in (shadow_def, grid_defs) if part.strip())
    extra_defs = f"\n  {extra_defs}" if extra_defs else ""

    return f"""
<defs>{extra_defs}
  <marker id="arrow" markerWidth="10" markerHeight="10" refX="8.5" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L9,3 z" fill="context-stroke"/></marker>
  <marker id="arrow-fanout" markerWidth="10" markerHeight="10" refX="8.5" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L9,3 z" fill="context-stroke"/></marker>
  <marker id="arrow-fanin" markerWidth="10" markerHeight="10" refX="8.5" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L9,3 z" fill="context-stroke"/></marker>
  <style>
    {scope} .title{{font:700 {_font_css(style, "tokens.typography.title_size", "30px")} {title_family};fill:{style_color(style, "text_primary", "#0F172A")};letter-spacing:{typography.get("title_letter_spacing", "0")};text-transform:{title_case}}}
    {scope} .subtitle{{font:400 {_font_css(style, "tokens.typography.subtitle_size", "14px")} {sans};fill:{style_color(style, "text_secondary", "#64748B")}}}
    {scope} .group-label{{font:700 {_font_css(style, "tokens.typography.group_label_size", "13px")} {mono};fill:{style_color(style, "text_secondary", "#475569")};letter-spacing:{typography.get("label_letter_spacing", ".06em")};text-transform:uppercase}}
    {scope} .card-title{{font:700 {_font_css(style, "tokens.typography.card_title_size", "17px")} {sans};fill:{style_color(style, "text_primary", "#0F172A")}}}
    {scope} .card-sub{{font:500 {_font_css(style, "tokens.typography.card_sub_size", "12.5px")} {sans};fill:{style_color(style, "text_secondary", "#64748B")}}}
    {scope} .edge{{fill:none;stroke:{arrow};stroke-width:{edge_width};stroke-linecap:round;stroke-linejoin:round;opacity:{edge_opacity}}}
    {scope} .fanout{{stroke:{fanout};opacity:{fanout_opacity}}}
    {scope} .fanin{{stroke:{fanin};opacity:{fanin_opacity}}}
    {scope} .route-shared{{marker-end:none}}
    {scope} .edge-dashed{{stroke-dasharray:{connector.get("dasharray", "8 8")};opacity:{connector.get("dashed_opacity", .66)}}}
    {scope} .note{{font:500 {_font_css(style, "tokens.typography.note_size", "12px")} {sans};fill:{style_color(style, "text_secondary", "#64748B")}}}
    {scope} .mono{{font-family:{mono}}}
    {scope} .table-header{{font:700 {table_header_size} {mono};fill:{style_color(style, "text_primary", "#0F172A")};letter-spacing:{typography.get("label_letter_spacing", ".06em")};text-transform:uppercase}}
    {scope} .table-cell{{font:500 {table_cell_size} {sans};fill:{style_color(style, "text_primary", "#0F172A")}}}
    {scope} .table-cell-secondary{{font:500 {table_cell_size} {sans};fill:{style_color(style, "text_secondary", "#64748B")}}}
    {scope} .tree-level-label{{font:700 {_font_css(style, "tokens.typography.group_label_size", "15px")} {mono};fill:{style_color(style, "text_secondary", "#64748B")};letter-spacing:{typography.get("label_letter_spacing", ".06em")};text-transform:uppercase}}
    {scope} .hub-label{{font:700 {_font_css(style, "tokens.typography.group_label_size", "13px")} {mono};fill:{style_color(style, "text_secondary", "#64748B")};letter-spacing:{typography.get("label_letter_spacing", ".06em")};text-transform:uppercase}}
    {scope} .icon-line{{fill:none;stroke-width:{_style_component(style, "icon").get("line_width", 1.8)};stroke-linecap:round;stroke-linejoin:round}}
  </style>
</defs>""".strip()


def icon_svg(kind: str, x: float, y: float, color: str, style: dict) -> str:
    icon = _style_component(style, "icon")
    fill_mode = icon.get("fill_mode", "pale")
    if fill_mode == "none":
        pale = "none"
    elif fill_mode == "component":
        pale = style_color(style, icon.get("fill", "panel_fill"), "#F8FAFC")
    else:
        pale = pale_for(style, color)
    stroke_width = icon.get("stroke_width", 1.7)
    k = kind or "object"
    if k in {"index", "moc", "document"}:
        return f'<rect x="{x}" y="{y}" width="18" height="20" rx="3" fill="{pale}" stroke="{color}" stroke-width="{stroke_width}"/><path d="M{x+4},{y+6} H{x+14} M{x+4},{y+11} H{x+14} M{x+4},{y+16} H{x+11}" class="icon-line" stroke="{color}"/>'
    if k == "query":
        return f'<circle cx="{x+8}" cy="{y+8}" r="7" fill="{pale}" stroke="{color}" stroke-width="{stroke_width}"/><path d="M{x+14},{y+14} L{x+20},{y+20}" class="icon-line" stroke="{color}"/>'
    if k in {"glossary", "ontology"}:
        return f'<path d="M{x},{y} H{x+16} Q{x+20},{y} {x+20},{y+4} V{y+19} H{x} Z" fill="{pale}" stroke="{color}" stroke-width="{stroke_width}"/><path d="M{x+5},{y+6} H{x+14} M{x+5},{y+12} H{x+14}" class="icon-line" stroke="{color}"/>'
    if k == "process":
        return f'<circle cx="{x+4}" cy="{y+11}" r="4" fill="{pale}" stroke="{color}" stroke-width="1.6"/><circle cx="{x+18}" cy="{y+4}" r="4" fill="{pale}" stroke="{color}" stroke-width="1.6"/><circle cx="{x+18}" cy="{y+18}" r="4" fill="{pale}" stroke="{color}" stroke-width="1.6"/><path d="M{x+8},{y+11} H{x+12} M{x+14},{y+7} L{x+12},{y+11} L{x+14},{y+15}" class="icon-line" stroke="{color}"/>'
    if k in {"quality", "registry"}:
        return f'<path d="M{x+10},{y} L{x+20},{y+18} H{x} Z" fill="{pale}" stroke="{color}" stroke-width="{stroke_width}"/><path d="M{x+10},{y+7} V{y+13} M{x+10},{y+17} V{y+17}" class="icon-line" stroke="{color}"/>'
    if k == "risk":
        return f'<path d="M{x+10},{y} L{x+19},{y+5} V{y+15} L{x+10},{y+20} L{x+1},{y+15} V{y+5} Z" fill="{pale}" stroke="{color}" stroke-width="{stroke_width}"/><path d="M{x+6},{y+10} L{x+9},{y+14} L{x+15},{y+6}" class="icon-line" stroke="{color}"/>'
    if k in {"package", "capability"}:
        return f'<rect x="{x}" y="{y+3}" width="20" height="16" rx="3" fill="{pale}" stroke="{color}" stroke-width="{stroke_width}"/><path d="M{x},{y+8} H{x+20} M{x+10},{y+3} V{y+19}" class="icon-line" stroke="{color}"/>'
    if k in {"source", "evidence"}:
        return f'<path d="M{x},{y} H{x+14} L{x+20},{y+6} V{y+20} H{x} Z" fill="{pale}" stroke="{color}" stroke-width="{stroke_width}"/><path d="M{x+14},{y} V{y+6} H{x+20}" class="icon-line" stroke="{color}"/>'
    if k == "decision":
        return f'<path d="M{x+10},{y} L{x+20},{y+10} L{x+10},{y+20} L{x},{y+10} Z" fill="{pale}" stroke="{color}" stroke-width="{stroke_width}"/><path d="M{x+6},{y+10} H{x+14}" class="icon-line" stroke="{color}"/>'
    return f'<circle cx="{x+10}" cy="{y+10}" r="8" fill="{pale}" stroke="{color}" stroke-width="{stroke_width}"/><path d="M{x+5},{y+10} H{x+15} M{x+10},{y+5} V{y+15}" class="icon-line" stroke="{color}"/>'


def make_card(node: dict, x: float, y: float, w: float, h: float, style: dict, canvas_width: float | None = None) -> str:
    kind = node.get("kind", "object")
    color = node.get("accent") or kind_accent(style, kind)
    if not VALID_HEX.match(color):
        color = kind_accent(style, "object")
    card = _style_component(style, "card")
    fill = card.get("fill", "card_fill")
    fill_default = style_color(style, "card_fill", "#FFFFFF")
    stroke = color if card.get("stroke_mode", "accent") == "accent" else style_color(style, card.get("stroke", "line_primary"), "#334155")
    stroke_width = card.get("stroke_width", 2.2)
    radius = card.get("radius", 20)
    shadow = card.get("shadow", {})
    shadow_enabled = bool(shadow.get("enabled", True)) if isinstance(shadow, dict) else bool(shadow)
    filter_attr = ' filter="url(#shadow)"' if shadow_enabled else ""
    pad_x = float(card.get("padding_x", 18))
    icon_gap = float(card.get("icon_gap", 16))
    text_x = x + pad_x + 22 + icon_gap
    text_w = max(80, w - (text_x - x) - pad_x)
    text_metrics = _card_text_metrics(style, canvas_width or w)
    title_size = text_metrics["title_size"]
    sub_size = text_metrics["sub_size"]
    title_line_h = text_metrics["title_line_h"]
    sub_line_h = text_metrics["sub_line_h"]
    sub_gap = text_metrics["sub_gap"]
    title_chars = max(8, int(text_w / max(8.0, title_size * 0.52)))
    title_lines = wrap_text(node.get("label", node.get("id", "Object")), max_chars=title_chars, max_lines=2)
    sub = node.get("subtitle", "")
    sub_lines: list[str] = []
    if sub:
        sub_chars = max(10, int(text_w / max(7.0, sub_size * 0.5)))
        sub_lines = wrap_text(sub, max_chars=sub_chars, max_lines=1 if len(title_lines) > 1 else 2)
    parts = [f'<g id="node-{e(node.get("id", ""))}" class="card node-card">']
    fill_attrs = _paint_attr(style, "fill", fill, fill_default, card.get("fill_opacity"))
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" {fill_attrs} stroke="{stroke}" stroke-width="{stroke_width}"{filter_attr}/>')
    parts.append(icon_svg(kind, x + pad_x, y + h / 2 - 10, color, style))
    block_h = len(title_lines) * title_line_h
    if sub_lines:
        block_h += sub_gap + len(sub_lines) * sub_line_h
    block_top = y + max(7.0, (h - block_h) / 2)
    title_start = block_top + title_size
    title_style = f' style="font-size:{_fmt_px(title_size)}"'
    sub_style = f' style="font-size:{_fmt_px(sub_size)}"'
    for i, line in enumerate(title_lines):
        parts.append(f'<text x="{text_x}" y="{title_start+i*title_line_h}" text-anchor="start" class="card-title"{title_style}>{e(line)}</text>')
    if sub_lines:
        sub_start = block_top + len(title_lines) * title_line_h + sub_gap + sub_size
        for i, line in enumerate(sub_lines):
            parts.append(f'<text x="{text_x}" y="{sub_start+i*sub_line_h}" text-anchor="start" class="card-sub"{sub_style}>{e(line)}</text>')
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


def build_layout_model(contract: dict, style: dict | None = None, contract_path: Path | None = None) -> dict:
    if style is None:
        style = style_for_contract(contract, contract_path)
    metrics = layout_metrics(style)
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
    margin_x = int(contract.get("canvas_margin_x", metrics["canvas_margin_x"]))
    y = int(contract.get("top_y", metrics["top_y"]))
    card_h = max(96, int(contract.get("card_height", metrics["card_h"])))
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
            int(g.get("row_gap", contract.get("card_row_gap", metrics["card_row_gap"]))),
            metrics["card_row_gap"],
        )
        if mode == "row_bus_side_trunk" and row_count > 1:
            if has_fanout and has_fanin:
                row_gap = max(row_gap, 2 * metrics["bus_to_card_clearance"] + metrics["bus_lane_gap"])
            else:
                row_gap = max(row_gap, metrics["bus_to_card_clearance"] + metrics["bus_bottom_clearance"])

        top_pad = int(g.get("top_pad", contract.get("layer_top_pad", metrics["layer_top_pad"])))
        bottom_pad = int(g.get("bottom_pad", contract.get("layer_bottom_pad", metrics["layer_bottom_pad"])))
        if mode == "row_bus_side_trunk" and has_fanout:
            top_pad = max(top_pad, metrics["layer_label_h"] + metrics["bus_to_card_clearance"])
        if mode == "row_bus_side_trunk" and has_fanin:
            bottom_pad = max(bottom_pad, metrics["bus_to_card_clearance"] + metrics["bus_bottom_clearance"])

        band_h = max(
            int(g.get("height", 0)),
            metrics["layer_min_h"],
            top_pad + row_count * card_h + (row_count - 1) * row_gap + bottom_pad,
        )
        group_boxes[gid] = (margin_x, y, width - 2 * margin_x, band_h, g)

        side_gutter = int(g.get("side_gutter", routing.get("side_gutter", metrics["layer_side_gutter"])))
        if mode == "row_bus_side_trunk":
            side_gutter = max(side_gutter, metrics["side_trunk_gutter"])
        gap = int(g.get("col_gap", contract.get("card_col_gap", metrics["card_col_gap"])))
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
            card_w = min(metrics["card_max_w"], max(metrics["card_min_w"], (usable - gap * (slots - 1)) / slots))
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
                "fanout_bus_y": row_top - metrics["bus_to_card_clearance"],
                "fanin_bus_y": row_top + card_h + metrics["bus_to_card_clearance"],
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
        y += band_h + int(g.get("gap_after", contract.get("layer_gap", metrics["layer_gap"])))
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
        terminal_paths = []
        upstream_x = sx if row == first_row else trunk_x
        if row == first_row:
            bus_points = list(source_bus_anchors)
            if has_lower_rows:
                bus_points.append(trunk_anchor_x)
        else:
            bus_points = [trunk_anchor_x]
        for target_id in targets:
            tx, ty = center_top(positions[target_id])
            if row == first_row and abs(tx - sx) < 1e-6:
                terminal_paths.append(_vertical_branch(tx, bus_y, ty))
                continue
            terminal_path, terminal_anchor = _curve_from_bus_from_side(tx, bus_y, ty, upstream_x)
            terminal_paths.append(terminal_path)
            bus_points.append(terminal_anchor)
        bus_gap = source_bus_gap if row == first_row else None
        for bus_d in _horizontal_bus_segments(bus_points, bus_y, bus_gap):
            paths.append(_path(bus_d, "edge fanout route-shared bus"))
        for terminal_path in terminal_paths:
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


def _canvas_parts(style: dict, width: float, height: float) -> list[str]:
    canvas = _style_component(style, "canvas")
    radius = canvas.get("radius", 28)
    bg = canvas.get("background", "background")
    parts = [f'<rect x="0" y="0" width="{width}" height="{height}" rx="{radius}" {_paint_attr(style, "fill", bg, "#F8FBFF")}/>']
    grid = style_token(style, "tokens.grid", {})
    if isinstance(grid, dict) and grid.get("enabled"):
        grid_opacity = grid.get("opacity", 1)
        parts.append(f'<rect x="0" y="0" width="{width}" height="{height}" rx="{radius}" fill="url(#blueprint-grid)" opacity="{grid_opacity}"/>')
    return parts


def _group_panel_svg(style: dict, x: float, y: float, w: float, h: float) -> str:
    group = _style_component(style, "group")
    radius = group.get("radius", 26)
    fill = group.get("fill", "group_fill")
    fill_default = style_color(style, "group_fill", "#EEF6FF")
    fill_attrs = _paint_attr(style, "fill", fill, fill_default, group.get("opacity"))
    stroke = group.get("stroke", "none")
    stroke_attrs = ""
    if stroke != "none":
        stroke_attrs = " " + _paint_attr(style, "stroke", stroke, "#F4F8FF", group.get("stroke_opacity"))
        stroke_attrs += f' stroke-width="{group.get("stroke_width", 1)}"'
        if group.get("dasharray") and group.get("dasharray") != "none":
            stroke_attrs += f' stroke-dasharray="{group.get("dasharray")}"'
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" class="group-panel" rx="{radius}" {fill_attrs}{stroke_attrs}/>'


def _group_label_svg(style: dict, x: float, y: float, w: float, label: str) -> str:
    label_w = min(w - 40, max(136.0, len(str(label)) * 8.4 + 24))
    bg = style_color(style, "background", "#F8FBFF")
    return (
        f'<g class="group-label-wrap">'
        f'<rect x="{x+18}" y="{y+6}" width="{label_w}" height="30" rx="7" fill="{bg}" fill-opacity="0.78"/>'
        f'<text x="{x+28}" y="{y+26}" class="group-label">{e(label)}</text>'
        f'</g>'
    )


def _svg_shell_start(contract: dict, style: dict, width: float, height: float, diagram_type: str) -> list[str]:
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{e(contract.get("title", "Semantic Diagram"))}" data-style="{e(style_id(style))}" data-diagram-type="{e(diagram_type)}">'
    ]
    parts.append(style_block(style))
    parts.extend(_canvas_parts(style, width, height))
    title = contract.get("title", "Semantic Diagram")
    subtitle = contract.get("subtitle", "")
    parts.append(f'<text x="{width/2}" y="54" text-anchor="middle" class="title">{e(title)}</text>')
    if subtitle:
        parts.append(f'<text x="{width/2}" y="80" text-anchor="middle" class="subtitle">{e(subtitle)}</text>')
    return parts


def _append_annotations(parts: list[str], contract: dict, style: dict, width: float, height: float) -> None:
    legend_notes = [a for a in contract.get("annotations", []) if a.get("placement") == "legend"]
    if legend_notes:
        legend_x = width - 330
        legend_y = height - 88 - (len(legend_notes) - 1) * 24
        for i, ann in enumerate(legend_notes[:4]):
            color = style_color(style, ann.get("color", "text_secondary"), style_color(style, "text_secondary", "#64748B"))
            parts.append(f'<text x="{legend_x}" y="{legend_y + i*24}" class="note legend-note" fill="{color}">{e(ann.get("text", ""))}</text>')

    footer_y = height - 28
    footer_notes = [a for a in contract.get("annotations", []) if a.get("placement", "footer") == "footer"]
    for i, ann in enumerate(footer_notes[:3]):
        parts.append(f'<text x="{width/2}" y="{footer_y - (len(footer_notes[:3])-1-i)*17}" text-anchor="middle" class="note">{e(ann.get("text", ""))}</text>')


def _render_grouped_layered(contract: dict, style: dict, contract_path: Path | None, diagram_type: str) -> str:
    model = build_layout_model(contract, style, contract_path)
    width = model["width"]
    height = model["height"]
    positions = model["positions"]
    group_boxes = model["group_boxes"]
    nodes = {n["id"]: n for n in contract.get("nodes", [])}
    parts = _svg_shell_start(contract, style, width, height, diagram_type)

    for gid, (x, y, w, h, _g) in group_boxes.items():
        parts.append(_group_panel_svg(style, x, y, w, h))

    # Draw edges behind cards but over group bands.
    parts.extend(routed_edge_paths(model, contract.get("edges", [])))

    for gid, (x, y, w, _h, g) in group_boxes.items():
        parts.append(_group_label_svg(style, x, y, w, g.get("label", gid)))

    for node_id, pos in positions.items():
        parts.append(make_card(nodes[node_id], *pos, style, width))

    _append_annotations(parts, contract, style, width, height)
    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def _column_widths(columns: list[dict], available_w: float) -> list[float]:
    widths: list[float | None] = []
    fixed = 0.0
    auto_count = 0
    for col in columns:
        value = col.get("width")
        if isinstance(value, (int, float)) and value > 0:
            widths.append(float(value))
            fixed += float(value)
        else:
            widths.append(None)
            auto_count += 1
    auto_w = max(120.0, (available_w - fixed) / max(1, auto_count))
    out = [auto_w if w is None else w for w in widths]
    total = sum(out)
    if total > available_w:
        scale = available_w / total
        out = [w * scale for w in out]
    return out


def _text_anchor_for(align: object) -> tuple[str, float]:
    if align == "right":
        return "end", 1.0
    if align == "center":
        return "middle", 0.5
    return "start", 0.0


def _render_wrapped_text(
    parts: list[str],
    lines: list[str],
    x: float,
    y: float,
    klass: str,
    anchor: str = "start",
    line_h: float = 16,
    inline_style: str = "",
) -> None:
    start_y = y - (len(lines) - 1) * line_h / 2
    for i, line in enumerate(lines):
        style_attr = f' style="{inline_style}"' if inline_style else ""
        parts.append(f'<text x="{x}" y="{start_y + i*line_h}" text-anchor="{anchor}" class="{klass}"{style_attr}>{e(line)}</text>')


def _table_badge_svg(style: dict, kind: object, x: float, y: float, size: float, color: str) -> str:
    fill = pale_for(style, color)
    icon_offset = (size - 20) / 2
    return (
        f'<g class="table-badge semantic-badge" data-kind="{e(kind or "object")}">'
        f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="5" fill="{fill}" stroke="{color}" stroke-width="1.2"/>'
        f'{icon_svg(str(kind or "object"), x + icon_offset, y + icon_offset, color, style)}'
        f'</g>'
    )


def _render_table(contract: dict, style: dict, diagram_type: str) -> str:
    metrics = layout_metrics(style)
    columns = [c for c in contract.get("columns", []) if isinstance(c, dict) and c.get("id")]
    rows = [r for r in contract.get("rows", []) if isinstance(r, dict)]
    if not columns:
        raise DiagramTypeError("registry_table requires non-empty columns")
    margin_x = int(contract.get("canvas_margin_x", metrics["canvas_margin_x"]))
    width = int(contract.get("width", 1500))
    table_x = margin_x
    table_y = int(contract.get("top_y", metrics["top_y"]))
    table_w = width - 2 * margin_x
    text_metrics = _table_text_metrics(style, width)
    header_h = int(max(_number(contract.get("header_height"), text_metrics["header_h"]), text_metrics["header_h"]))
    row_h = int(max(_number(contract.get("row_height"), text_metrics["row_h"]), text_metrics["row_h"]))
    header_style = f'font-size:{_fmt_px(text_metrics["header_size"])}'
    cell_style = f'font-size:{_fmt_px(text_metrics["cell_size"])}'
    term_style = f'{cell_style};font-weight:700'
    line_h = text_metrics["line_h"]
    height = int(max(contract.get("height", 0), table_y + header_h + max(1, len(rows)) * row_h + 110))
    col_widths = _column_widths(columns, table_w)
    table = _style_component(style, "table")
    radius = table.get("radius", _style_component(style, "card").get("radius", 8))
    fill = table.get("fill", "panel_fill")
    header_fill = table.get("header_fill", "panel_fill_strong")
    stroke = table.get("stroke", "line_primary")
    stroke_color, stroke_opacity = style_paint(style, stroke, "#334155")
    stroke_opacity = table.get("grid_opacity", stroke_opacity if stroke_opacity is not None else 0.55)

    parts = _svg_shell_start(contract, style, width, height, diagram_type)
    parts.append(
        f'<rect x="{table_x}" y="{table_y}" width="{table_w}" height="{header_h + max(1, len(rows)) * row_h}" rx="{radius}" {_paint_attr(style, "fill", fill, "#FFFFFF", table.get("fill_opacity"))} stroke="{stroke_color}" stroke-opacity="{stroke_opacity}" stroke-width="{table.get("stroke_width", 1)}"/>'
    )
    parts.append(
        f'<rect x="{table_x}" y="{table_y}" width="{table_w}" height="{header_h}" rx="{radius}" {_paint_attr(style, "fill", header_fill, "#EEF6FF", table.get("header_opacity"))}/>'
    )
    cur_x = table_x
    for idx, col in enumerate(columns):
        col_w = col_widths[idx]
        if idx > 0:
            parts.append(f'<line x1="{cur_x}" y1="{table_y}" x2="{cur_x}" y2="{table_y + header_h + max(1, len(rows)) * row_h}" stroke="{stroke_color}" stroke-opacity="{stroke_opacity}" stroke-width="1"/>')
        anchor, offset = _text_anchor_for(col.get("align"))
        text_x = cur_x + 16 + (col_w - 32) * offset
        parts.append(f'<text x="{text_x}" y="{table_y + header_h / 2 + text_metrics["header_size"] / 3}" text-anchor="{anchor}" class="table-header" style="{header_style}">{e(col.get("label", col.get("id")))}</text>')
        cur_x += col_w
    parts.append(f'<line x1="{table_x}" y1="{table_y + header_h}" x2="{table_x + table_w}" y2="{table_y + header_h}" stroke="{stroke_color}" stroke-opacity="{stroke_opacity}" stroke-width="1"/>')

    if not rows:
        parts.append(f'<text x="{table_x + table_w/2}" y="{table_y + header_h + row_h/2 + 4}" text-anchor="middle" class="table-cell-secondary">No rows</text>')
    for row_idx, row in enumerate(rows):
        y = table_y + header_h + row_idx * row_h
        if row_idx > 0:
            parts.append(f'<line x1="{table_x}" y1="{y}" x2="{table_x + table_w}" y2="{y}" stroke="{stroke_color}" stroke-opacity="{stroke_opacity}" stroke-width="1"/>')
        cur_x = table_x
        row_kind = row.get("kind", "object")
        row_accent = row.get("accent") or kind_accent(style, row_kind)
        row_accent = style_color(style, row_accent, kind_accent(style, "object"))
        for col_idx, col in enumerate(columns):
            col_w = col_widths[col_idx]
            value = row.get(col["id"], "")
            anchor, offset = _text_anchor_for(col.get("align"))
            badge_size = 30
            pad_left = 62 if col_idx == 0 else 16
            text_x = cur_x + pad_left + (col_w - pad_left - 16) * offset
            max_chars = max(8, int((col_w - pad_left - 16) / max(8.0, text_metrics["cell_size"] * 0.55)))
            lines = wrap_text(str(value), max_chars=max_chars, max_lines=3)
            klass = "table-cell" if col_idx == 0 else "table-cell-secondary"
            _render_wrapped_text(
                parts,
                lines,
                text_x,
                y + row_h / 2 + text_metrics["cell_size"] / 3,
                klass,
                anchor,
                line_h,
                term_style if col_idx == 0 else cell_style,
            )
            if col_idx == 0:
                parts.append(_table_badge_svg(style, row_kind, cur_x + 16, y + row_h / 2 - badge_size / 2, badge_size, row_accent))
            cur_x += col_w

    _append_annotations(parts, contract, style, width, height)
    parts.append('</svg>')
    return "\n".join(parts) + "\n"


TREE_PARENT_RELATIONS = {"parent", "parent_of", "contains", "has_child", "classifies"}


def _tree_maps(contract: dict) -> tuple[dict[str, dict], dict[str, str], dict[str, list[str]], list[str]]:
    nodes = [n for n in contract.get("nodes", []) if isinstance(n, dict) and n.get("id")]
    node_by_id = {str(n["id"]): n for n in nodes}
    parent_map: dict[str, str] = {}
    for node in nodes:
        if node.get("parent"):
            parent = str(node["parent"])
            child = str(node["id"])
            if parent not in node_by_id:
                raise DiagramTypeError(f'taxonomy_tree parent "{parent}" for "{child}" is not a node id')
            parent_map[child] = parent

    edge_parent_map: dict[str, str] = {}
    for edge in contract.get("edges", []):
        fr, to = edge.get("from"), edge.get("to")
        if fr not in node_by_id or to not in node_by_id:
            continue
        relation = edge.get("relation")
        if parent_map and relation not in TREE_PARENT_RELATIONS:
            continue
        if to in edge_parent_map and edge_parent_map[to] != fr:
            raise DiagramTypeError(f'taxonomy_tree node "{to}" has multiple edge parents')
        edge_parent_map[str(to)] = str(fr)

    if parent_map:
        for child, edge_parent in edge_parent_map.items():
            if child in parent_map and parent_map[child] != edge_parent:
                raise DiagramTypeError(f'taxonomy_tree parent conflict for "{child}"')
    else:
        parent_map = edge_parent_map

    children = {node_id: [] for node_id in node_by_id}
    for child, parent in parent_map.items():
        children[parent].append(child)
    order = {str(n["id"]): i for i, n in enumerate(nodes)}
    for child_list in children.values():
        child_list.sort(key=lambda node_id: (node_by_id[node_id].get("order", order[node_id]), order[node_id]))
    roots = [node_id for node_id in node_by_id if node_id not in parent_map]
    if not roots and node_by_id:
        raise DiagramTypeError("taxonomy_tree must have at least one root")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            raise DiagramTypeError("taxonomy_tree cannot contain cycles")
        if node_id in visited:
            return
        visiting.add(node_id)
        for child in children[node_id]:
            visit(child)
        visiting.remove(node_id)
        visited.add(node_id)

    for root in roots:
        visit(root)
    return node_by_id, parent_map, children, roots


def _render_tree(contract: dict, style: dict, diagram_type: str) -> str:
    node_by_id, parent_map, children, roots = _tree_maps(contract)
    if not node_by_id:
        raise DiagramTypeError("taxonomy_tree requires nodes")
    metrics = layout_metrics(style)
    margin_x = int(contract.get("canvas_margin_x", metrics["canvas_margin_x"]))
    card_w = float(contract.get("card_width", 230))
    card_h = float(contract.get("card_height", metrics["card_h"]))
    level_gap = float(contract.get("level_gap", 84))
    leaf_slots: dict[str, int] = {}
    centers: dict[str, float] = {}
    depths: dict[str, int] = {}
    leaf_index = 0

    def assign(node_id: str, depth: int) -> float:
        nonlocal leaf_index
        depths[node_id] = depth
        if not children[node_id]:
            leaf_slots[node_id] = leaf_index
            leaf_index += 1
            centers[node_id] = float(leaf_slots[node_id])
            return centers[node_id]
        child_centers = [assign(child, depth + 1) for child in children[node_id]]
        centers[node_id] = sum(child_centers) / len(child_centers)
        return centers[node_id]

    for root in roots:
        assign(root, 0)
    leaf_count = max(1, leaf_index)
    min_width = int(2 * margin_x + leaf_count * card_w + max(0, leaf_count - 1) * 44)
    width = int(max(contract.get("width", 1500), min_width))
    top_y = int(contract.get("top_y", metrics["top_y"]))
    max_depth = max(depths.values())
    height = int(max(contract.get("height", 0), top_y + (max_depth + 1) * card_h + max_depth * level_gap + 110))
    span = max(1.0, width - 2 * margin_x - card_w)
    step = span / max(1, leaf_count - 1)
    positions: dict[str, tuple[float, float, float, float]] = {}
    for node_id, slot_center in centers.items():
        cx = margin_x + card_w / 2 + slot_center * step
        y = top_y + depths[node_id] * (card_h + level_gap)
        positions[node_id] = (cx - card_w / 2, y, card_w, card_h)

    parts = _svg_shell_start(contract, style, width, height, diagram_type)
    for child, parent in parent_map.items():
        parts.append(_path(edge_path(positions[parent], positions[child]), "edge taxonomy-link", "arrow"))
    for node_id in sorted(positions, key=lambda nid: (depths[nid], positions[nid][0])):
        parts.append(make_card(node_by_id[node_id], *positions[node_id], style, width))
    for depth in range(max_depth + 1):
        parts.append(f'<text x="{margin_x}" y="{top_y + depth * (card_h + level_gap) - 14}" class="tree-level-label">Level {depth}</text>')
    _append_annotations(parts, contract, style, width, height)
    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def _circle_anchor(cx: float, cy: float, radius: float, tx: float, ty: float) -> tuple[float, float]:
    dx = tx - cx
    dy = ty - cy
    dist = math.hypot(dx, dy) or 1.0
    return cx + dx / dist * radius, cy + dy / dist * radius


def _hub_text_lines(text: object, max_chars: int, max_lines: int) -> list[str]:
    return wrap_text(str(text or ""), max_chars=max_chars, max_lines=max_lines)


def _render_spoke_block(node: dict, x: float, y: float, w: float, h: float, style: dict, canvas_w: float) -> str:
    kind = node.get("kind", "object")
    color = node.get("accent") or kind_accent(style, kind)
    if not VALID_HEX.match(color):
        color = kind_accent(style, "object")
    card = _style_component(style, "card")
    fill = card.get("fill", "card_fill")
    radius = min(float(card.get("radius", 10)), 10)
    title_size = _clamp(19.0 * _clamp(canvas_w / 1500.0, 0.92, 1.08), 18.0, 20.5)
    sub_size = _clamp(14.5 * _clamp(canvas_w / 1500.0, 0.92, 1.08), 13.5, 15.5)
    text_x = x + 66
    text_w = max(80, w - 82)
    title_lines = _hub_text_lines(node.get("label", node.get("id", "Spoke")), max(8, int(text_w / (title_size * 0.55))), 2)
    sub_lines = _hub_text_lines(node.get("subtitle", ""), max(10, int(text_w / (sub_size * 0.52))), 1)
    block_h = len(title_lines) * (title_size + 2) + (sub_size + 5 if sub_lines else 0)
    top = y + (h - block_h) / 2
    parts = [f'<g id="node-{e(node.get("id", ""))}" class="hub-spoke-node spoke-block card">']
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" {_paint_attr(style, "fill", fill, "#FFFFFF", card.get("fill_opacity"))} stroke="{color}" stroke-width="{max(1.4, float(card.get("stroke_width", 1.4)))}"/>')
    parts.append(icon_svg(kind, x + 24, y + h / 2 - 10, color, style))
    for i, line in enumerate(title_lines):
        parts.append(f'<text x="{text_x}" y="{top + title_size + i * (title_size + 2)}" text-anchor="start" class="card-title" style="font-size:{_fmt_px(title_size)}">{e(line)}</text>')
    if sub_lines:
        sub_y = top + len(title_lines) * (title_size + 2) + sub_size + 5
        parts.append(f'<text x="{text_x}" y="{sub_y}" text-anchor="start" class="card-sub" style="font-size:{_fmt_px(sub_size)}">{e(sub_lines[0])}</text>')
    parts.append('</g>')
    return "".join(parts)


def _render_hub_core(node: dict, cx: float, cy: float, radius: float, style: dict, canvas_w: float) -> str:
    kind = node.get("kind", "hub")
    color = node.get("accent") or kind_accent(style, kind)
    if not VALID_HEX.match(color):
        color = kind_accent(style, "hub")
    card = _style_component(style, "card")
    fill = card.get("fill", "card_fill")
    title_size = _clamp(22.0 * _clamp(canvas_w / 1500.0, 0.92, 1.08), 21.0, 24.0)
    sub_size = _clamp(15.0 * _clamp(canvas_w / 1500.0, 0.92, 1.08), 14.0, 16.0)
    title_lines = _hub_text_lines(node.get("label", "Hub"), 15, 2)
    sub_lines = _hub_text_lines(node.get("subtitle", ""), 20, 2)
    block_h = len(title_lines) * (title_size + 2) + (len(sub_lines) * (sub_size + 2) + 6 if sub_lines else 0)
    top = cy - block_h / 2
    parts = [f'<g id="node-{e(node.get("id", ""))}" class="hub-core card">']
    parts.append(f'<rect x="{cx-radius}" y="{cy-radius}" width="{radius*2}" height="{radius*2}" fill="none" stroke="none"/>')
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="{radius}" {_paint_attr(style, "fill", fill, "#FFFFFF", card.get("fill_opacity"))} stroke="{color}" stroke-width="3.2"/>')
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="{radius-12}" fill="none" stroke="{color}" stroke-opacity="0.32" stroke-width="1.3"/>')
    for i, line in enumerate(title_lines):
        parts.append(f'<text x="{cx}" y="{top + title_size + i * (title_size + 2)}" text-anchor="middle" class="card-title" style="font-size:{_fmt_px(title_size)}">{e(line)}</text>')
    for i, line in enumerate(sub_lines):
        parts.append(f'<text x="{cx}" y="{top + len(title_lines) * (title_size + 2) + 8 + sub_size + i * (sub_size + 2)}" text-anchor="middle" class="card-sub" style="font-size:{_fmt_px(sub_size)}">{e(line)}</text>')
    parts.append('</g>')
    return "".join(parts)


def _render_hub_spoke(contract: dict, style: dict, diagram_type: str) -> str:
    nodes = [n for n in contract.get("nodes", []) if isinstance(n, dict) and n.get("id")]
    node_by_id = {str(n["id"]): n for n in nodes}
    hub_id = str(contract.get("hub_id", ""))
    if hub_id not in node_by_id:
        raise DiagramTypeError("hub_spoke requires hub_id to match a node id")
    spokes = [n for n in nodes if str(n["id"]) != hub_id]
    order = {str(n["id"]): i for i, n in enumerate(nodes)}
    spokes.sort(key=lambda n: (n.get("order", order[str(n["id"])]), order[str(n["id"])]))
    metrics = layout_metrics(style)
    width = int(contract.get("width", 1500))
    margin_x = int(contract.get("canvas_margin_x", metrics["canvas_margin_x"]))
    hub_radius = float(contract.get("hub_radius", 118))
    spoke_w = float(contract.get("spoke_width", 280))
    spoke_h = float(contract.get("spoke_height", 86))
    center_x = width / 2
    positions: dict[str, tuple[float, float, float, float]] = {}
    left = spokes[: math.ceil(len(spokes) / 2)]
    right = spokes[math.ceil(len(spokes) / 2):]
    left_x = margin_x + 95
    right_x = width - margin_x - 95 - spoke_w
    column_gap = 34
    left_total = len(left) * spoke_h + max(0, len(left) - 1) * column_gap
    right_total = len(right) * spoke_h + max(0, len(right) - 1) * column_gap
    content_half_h = max(hub_radius + 20, left_total / 2, right_total / 2)
    center_y = int(max(float(contract.get("center_y", 390)), metrics["top_y"] + content_half_h + 28))
    for i, node in enumerate(left):
        positions[str(node["id"])] = (left_x, center_y - left_total / 2 + i * (spoke_h + column_gap), spoke_w, spoke_h)
    for i, node in enumerate(right):
        positions[str(node["id"])] = (right_x, center_y - right_total / 2 + i * (spoke_h + column_gap), spoke_w, spoke_h)
    content_bottom = max([center_y + hub_radius + 20] + [y + h for _x, y, _w, h in positions.values()])
    min_height = int(content_bottom + 92)
    height = int(max(contract.get("height", min_height), min_height))

    parts = _svg_shell_start(contract, style, width, height, diagram_type)
    parts.append(f'<circle cx="{center_x}" cy="{center_y}" r="{hub_radius + 20}" fill="none" stroke="{kind_accent(style, "hub")}" stroke-opacity="0.16" stroke-width="1.4"/>')
    for node in spokes:
        node_id = str(node["id"])
        edge_cls = "edge edge-dashed" if node.get("style") == "dashed" else "edge"
        x, y, w, h = positions[node_id]
        target_x = x + w if x < center_x else x
        target_y = y + h / 2
        sx, sy = _circle_anchor(center_x, center_y, hub_radius, target_x, target_y)
        parts.append(_path(f"M {round(sx, 2)} {round(sy, 2)} L {round(target_x, 2)} {round(target_y, 2)}", f"{edge_cls} hub-spoke-link", "arrow"))
    parts.append(_render_hub_core(node_by_id[hub_id], center_x, center_y, hub_radius, style, width))
    for node in spokes:
        parts.append(_render_spoke_block(node, *positions[str(node["id"])], style, width))
    _append_annotations(parts, contract, style, width, height)
    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def render(contract: dict, contract_path: Path | None = None, style: dict | None = None) -> str:
    if style is None:
        style = style_for_contract(contract, contract_path)
    diagram_type, strategy, _warnings = diagram_for_contract(contract)
    validate_contract_schema(contract, diagram_type)
    if strategy == "table":
        return _render_table(contract, style, diagram_type)
    if strategy == "tree":
        return _render_tree(contract, style, diagram_type)
    if strategy == "hub_spoke":
        return _render_hub_spoke(contract, style, diagram_type)
    if strategy == "grouped_layered":
        return _render_grouped_layered(contract, style, contract_path, diagram_type)
    raise DiagramTypeError(f"unsupported render strategy: {strategy}")

    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def contract_warnings(contract: dict, contract_path: Path | None = None) -> list[str]:
    warnings: list[str] = []
    # Validate style early so CLI failures are explicit and do not fall back.
    style_for_contract(contract, contract_path)
    diagram_type, strategy, type_warnings = diagram_for_contract(contract)
    warnings.extend(type_warnings)
    warnings.extend(validate_contract_schema(contract, diagram_type))

    node_ids = [n.get("id") for n in contract.get("nodes", []) if n.get("id")]
    node_id_set = set(node_ids)
    if diagram_type == "taxonomy_tree":
        _tree_maps(contract)

    skipped_edges = []
    for edge in contract.get("edges", []):
        fr, to = edge.get("from"), edge.get("to")
        if fr not in node_id_set or to not in node_id_set:
            skipped_edges.append(f"{fr}->{to}")
    if skipped_edges:
        examples = ", ".join(skipped_edges[:5])
        suffix = "..." if len(skipped_edges) > 5 else ""
        warnings.append(f"edges with missing endpoints will be skipped: {examples}{suffix}")

    unsupported_annotations = [a.get("placement", "footer") for a in contract.get("annotations", []) if a.get("placement", "footer") not in {"footer", "legend"}]
    if unsupported_annotations:
        placements = ", ".join(sorted(set(str(p) for p in unsupported_annotations)))
        warnings.append(f"non-footer annotations are contract guidance only and were not rendered: {placements}")

    labeled_edges = [edge for edge in contract.get("edges", []) if edge.get("label")]
    if labeled_edges:
        warnings.append("edge labels are contract guidance only and were not rendered")
    if strategy != "grouped_layered" and contract.get("groups"):
        warnings.append(f'groups are ignored by diagram_type "{diagram_type}"')
    return warnings


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: render_semantic_diagram.py contract.json output.svg", file=sys.stderr)
        return 2
    contract_path = Path(argv[1])
    output_path = Path(argv[2])
    contract = json.loads(contract_path.read_text(encoding="utf-8-sig"))
    try:
        for warning in contract_warnings(contract, contract_path):
            print(f"warning: {warning}", file=sys.stderr)
        svg = render(contract, contract_path)
    except (StyleError, DiagramTypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(svg, encoding="utf-8", newline="\n")
    print(f"wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
