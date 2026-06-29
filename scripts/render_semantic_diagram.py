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
EPS = 1e-6
ANCHOR_SIDES = {"left", "right", "top", "bottom"}

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


def _truncate_text_line(text: str, max_chars: int) -> str:
    max_chars = max(4, max_chars)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _wrap_text_to_width(
    text: str,
    pixel_width: float,
    font_size: float,
    max_lines: int = 2,
    min_chars: int = 8,
    char_factor: float = 0.56,
) -> list[str]:
    max_chars = max(min_chars, int(max(1.0, pixel_width) / max(1.0, font_size * char_factor)))
    return [_truncate_text_line(line, max_chars) for line in wrap_text(text, max_chars=max_chars, max_lines=max_lines)]


def _fit_text_to_width(
    text: str,
    pixel_width: float,
    font_size: float,
    min_chars: int = 8,
    char_factor: float = 0.56,
) -> str:
    return _wrap_text_to_width(text, pixel_width, font_size, max_lines=1, min_chars=min_chars, char_factor=char_factor)[0]


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


def _fmt_num(value: float) -> str:
    return f"{round(value, 2):g}"


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


def style_block(style: dict, canvas_w: float | None = None) -> str:
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
        small_base = max(1.0, _number(grid.get("size", 16), 16))
        strong_every = max(1.0, _number(grid.get("strong_every", 5), 5))
        reference_w = max(1.0, _number(grid.get("reference_width", 1500), 1500))
        scale = 1.0
        if grid.get("scale_with_canvas", True) and canvas_w:
            scale = max(0.1, float(canvas_w) / reference_w)
        small_value = small_base * scale
        large_value = small_base * strong_every * scale
        small = _fmt_num(small_value)
        large = _fmt_num(large_value)
        small_stroke = _fmt_num(_number(grid.get("stroke_width", 0.7), 0.7) * scale)
        strong_stroke = _fmt_num(_number(grid.get("strong_stroke_width", 1), 1) * scale)
        line_color, line_opacity = style_paint(style, grid.get("line", "grid_line"), "#FFFFFF")
        strong_color, strong_opacity = style_paint(style, grid.get("strong_line", "grid_line_strong"), "#FFFFFF")
        grid_defs = f"""
  <pattern id="blueprint-grid-small" width="{small}" height="{small}" patternUnits="userSpaceOnUse"><path d="M {small} 0 H 0 V {small}" fill="none" stroke="{line_color}" stroke-opacity="{line_opacity if line_opacity is not None else 0.08}" stroke-width="{small_stroke}"/></pattern>
  <pattern id="blueprint-grid" width="{large}" height="{large}" patternUnits="userSpaceOnUse"><rect width="{large}" height="{large}" fill="url(#blueprint-grid-small)"/><path d="M {large} 0 H 0 V {large}" fill="none" stroke="{strong_color}" stroke-opacity="{strong_opacity if strong_opacity is not None else 0.14}" stroke-width="{strong_stroke}"/> </pattern>"""

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
    {scope} .info-panel-title{{font:700 {_font_css(style, "tokens.typography.group_label_size", "15px")} {mono};fill:{style_color(style, "text_primary", "#0F172A")};letter-spacing:{typography.get("label_letter_spacing", ".06em")};text-transform:uppercase}}
    {scope} .info-panel-item{{font:500 {_font_css(style, "tokens.typography.note_size", "14px")} {sans};fill:{style_color(style, "text_secondary", "#64748B")}}}
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
    compact_card = w < 250
    pad_x = float(card.get("padding_x", 18))
    icon_gap = float(card.get("icon_gap", 16))
    if compact_card:
        pad_x = min(pad_x, 16.0)
        icon_gap = min(icon_gap, 6.0)
    text_x = x + pad_x + 22 + icon_gap
    text_w = max(80, w - (text_x - x) - pad_x)
    text_metrics = _card_text_metrics(style, canvas_width or w)
    title_size = text_metrics["title_size"]
    sub_size = text_metrics["sub_size"]
    if compact_card:
        title_size = min(title_size, 21.0)
        sub_size = min(sub_size, 16.0)
    title_line_h = max(title_size + 1.5, title_size * 1.08)
    sub_line_h = max(sub_size + 1.5, sub_size * 1.1)
    sub_gap = _clamp(title_size * 0.18, 3.0, 5.0)
    title_lines = _wrap_text_to_width(
        str(node.get("label", node.get("id", "Object"))),
        text_w,
        title_size,
        max_lines=2,
        min_chars=8,
        char_factor=0.58,
    )
    sub = node.get("subtitle", "")
    sub_lines: list[str] = []
    if sub:
        sub_lines = _wrap_text_to_width(
            str(sub),
            text_w,
            sub_size,
            max_lines=1 if len(title_lines) > 1 else 2,
            min_chars=10,
            char_factor=0.54,
        )
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
        "style": style,
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


def _path(d: str, classes: str, marker: str | None = None, extra_attrs: str = "") -> str:
    marker_attr = f' marker-end="url(#{marker})"' if marker else ""
    extra = f" {extra_attrs.strip()}" if extra_attrs.strip() else ""
    return f'<path d="{d}" class="{classes}"{marker_attr}{extra}/>'


def _connector_palette_color(style: dict, palette_name: str, index: int, fallback: str = "") -> str:
    connector = _style_component(style, "connector")
    palette = connector.get(palette_name)
    if not isinstance(palette, list) or not palette:
        return fallback
    raw = palette[index % len(palette)]
    color = style_color(style, raw, "")
    return color if VALID_HEX.match(color) else fallback


def _connector_family_attrs(style: dict, role: str, index: int) -> str:
    color = _connector_palette_color(style, f"{role}_palette", index)
    if not color:
        return ""
    return f'style="stroke:{color}" data-route-family="{index}" data-route-color="{color}"'


def _connector_family_lane_shift(style: dict, role: str, index: int) -> float:
    connector = _style_component(style, "connector")
    gap = float(connector.get(f"{role}_lane_gap", connector.get("family_lane_gap", 16.0)))
    offsets = [0.0, 1.0, -1.0, 2.0, -2.0, 3.0, -3.0]
    return offsets[index % len(offsets)] * gap


def _preferred_side_for_points(layout: dict, x_values: list[float], fallback: str) -> str:
    if not x_values:
        return fallback
    left_x = _side_x(layout, "left")
    right_x = _side_x(layout, "right")
    avg_x = sum(x_values) / len(x_values)
    return "left" if abs(avg_x - left_x) <= abs(avg_x - right_x) else "right"


def _vertical_branch(x: float, start_y: float, end_y: float) -> str:
    return _rounded_path([(x, start_y), (x, end_y)])


def _horizontal_bus(points: list[float], y: float, overlap: float = 2.0) -> str:
    return _rounded_path([(min(points) - overlap, y), (max(points) + overlap, y)])


def _horizontal_bus_segments(points: list[float], y: float, gap: tuple[float, float] | None = None) -> list[str]:
    clean = sorted({round(float(x), 2) for x in points})
    if len(clean) < 2:
        return []
    if gap is None:
        return [_horizontal_bus(clean, y)]

    gap_left, gap_right = sorted(gap)
    gap_mid = (gap_left + gap_right) / 2
    segments = []
    left = []
    right = []
    for x in clean:
        if x <= gap_left + 1e-6:
            left.append(x)
        elif x >= gap_right - 1e-6:
            right.append(x)
        elif x < gap_mid:
            left.append(x)
        elif x > gap_mid:
            right.append(x)
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


def _fanout_family_paths(source_id: str, target_group: str, target_ids: list[str], model: dict, family_index: int = 0) -> tuple[list[str], set[tuple[str, str]]]:
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
    family_attrs = _connector_family_attrs(model.get("style", {}), "fanout", family_index)
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
            paths.append(_path(source_path, "edge fanout route-shared branch", extra_attrs=family_attrs))
    else:
        source_path, source_bus_anchor = _curve_to_bus_toward(
            sx,
            sy,
            first_bus_y,
            (min(first_target_centers) + max(first_target_centers)) / 2,
        )
        source_bus_anchors = [source_bus_anchor]
        paths.append(_path(source_path, "edge fanout route-shared branch", extra_attrs=family_attrs))

    for row in sorted(row_targets):
        if row == first_row:
            continue
        bus_y = layout["rows"][row]["fanout_bus_y"]
        paths.append(
            _path(
                _rounded_path([(trunk_anchor_x, first_bus_y), (trunk_x, first_bus_y), (trunk_x, bus_y), (trunk_anchor_x, bus_y)]),
                "edge fanout route-shared trunk",
                extra_attrs=family_attrs,
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
        for bus_d in _horizontal_bus_segments(bus_points, bus_y):
            paths.append(_path(bus_d, "edge fanout route-shared bus", extra_attrs=family_attrs))
        for terminal_path in terminal_paths:
            paths.append(_path(terminal_path, "edge fanout terminal", "arrow-fanout", family_attrs))
    return paths, routed


def _fanin_family_paths(source_group: str, target_id: str, source_ids: list[str], model: dict, family_index: int = 0) -> tuple[list[str], set[tuple[str, str]]]:
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
    style = model.get("style", {})
    family_attrs = _connector_family_attrs(style, "fanin", family_index)
    lane_shift = _connector_family_lane_shift(style, "fanin", family_index)
    routed = {(source_id, target_id) for sources in row_sources.values() for source_id in sources}
    source_center_xs = [center_bottom(positions[source_id])[0] for source_id in _unique(source_ids) if source_id in positions]
    target_center_x = center_top(positions[target_id])[0]
    side = _preferred_side_for_points(layout, source_center_xs + [target_center_x], layout.get("fanin_side", "left"))
    trunk_x = _side_x(layout, side)
    trunk_inward = 1 if side == "left" else -1
    trunk_anchor_x = trunk_x + trunk_inward * 14
    row_bus_ys = [layout["rows"][row]["fanin_bus_y"] + lane_shift for row in row_sources]
    first_bus_y = min(row_bus_ys)
    join_y = max(row_bus_ys)
    has_cross_row_trunk = abs(first_bus_y - join_y) > 1e-6
    tx, ty = center_top(positions[target_id])
    aligned_sources = []
    for source_id in _unique(source_ids):
        if source_id not in positions:
            continue
        sx, sy = center_bottom(positions[source_id])
        if abs(sx - tx) < 1e-6 and sy <= ty:
            aligned_sources.append((sy, source_id))
    direct_source_id = max(aligned_sources)[1] if aligned_sources else None

    if has_cross_row_trunk:
        paths.append(
            _path(
                _rounded_path([(trunk_anchor_x, first_bus_y), (trunk_x, first_bus_y), (trunk_x, join_y), (trunk_anchor_x, join_y)]),
                "edge fanin route-shared trunk",
                extra_attrs=family_attrs,
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
        bus_y = layout["rows"][row]["fanin_bus_y"] + lane_shift
        source_centers = []
        for source_id in sources:
            if source_id == direct_source_id:
                continue
            sx, sy = center_bottom(positions[source_id])
            target_direction_x = tx if abs(bus_y - join_y) <= 1e-6 else trunk_x
            source_path, source_anchor = _curve_to_bus_toward(sx, sy, bus_y, target_direction_x)
            source_centers.append(source_anchor)
            paths.append(_path(source_path, "edge fanin route-shared branch", extra_attrs=family_attrs))
        if abs(bus_y - join_y) <= 1e-6:
            source_span = list(source_centers)
            if has_cross_row_trunk:
                source_span.append(trunk_anchor_x)
            if not source_span and direct_source_id:
                source_span = [tx]
            if not source_span:
                source_span = [trunk_anchor_x]
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
            paths.append(_path(bus_d, "edge fanin route-shared bus", extra_attrs=family_attrs))

    for terminal_path in terminal_merge_paths:
        paths.append(_path(terminal_path, "edge fanin route-shared merge", extra_attrs=family_attrs))
    paths.append(_path(terminal_marker_path, "edge fanin terminal", "arrow-fanin", family_attrs))
    return paths, routed


def routed_edge_paths(model: dict, edges: list[dict]) -> list[str]:
    paths = []
    routed_edges: set[tuple[str, str]] = set()
    stats = model["stats"]
    for family_index, ((source_id, target_group), target_ids) in enumerate(stats["fanout_families"].items()):
        family_paths, family_edges = _fanout_family_paths(source_id, target_group, target_ids, model, family_index)
        paths.extend(family_paths)
        routed_edges.update(family_edges)
    for family_index, ((source_group, target_id), source_ids) in enumerate(stats["fanin_families"].items()):
        family_paths, family_edges = _fanin_family_paths(source_group, target_id, source_ids, model, family_index)
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
    variant = contract.get("variant")
    variant_attr = f' data-variant="{e(variant)}"' if isinstance(variant, str) and variant.strip() else ""
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{e(contract.get("title", "Semantic Diagram"))}" data-style="{e(style_id(style))}" data-diagram-type="{e(diagram_type)}"{variant_attr}>'
    ]
    parts.append(style_block(style, width))
    parts.extend(_canvas_parts(style, width, height))
    title = contract.get("title", "Semantic Diagram")
    subtitle = contract.get("subtitle", "")
    parts.append(f'<text x="{width/2}" y="54" text-anchor="middle" class="title">{e(title)}</text>')
    if subtitle:
        subtitle_size = _px(_font_css(style, "tokens.typography.subtitle_size", "14px"), 14)
        subtitle_chars = max(28, int((width - 120) / max(7.0, subtitle_size * 0.56)))
        subtitle_lines = wrap_text(str(subtitle), max_chars=subtitle_chars, max_lines=2)
        _render_wrapped_text(parts, subtitle_lines, width / 2, 80, "subtitle", anchor="middle", line_h=subtitle_size + 4)
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
    fixed_w = sum(float(col.get("width")) for col in columns if isinstance(col.get("width"), (int, float)) and col.get("width") > 0)
    auto_count = sum(1 for col in columns if not (isinstance(col.get("width"), (int, float)) and col.get("width") > 0))
    min_auto_col_w = float(contract.get("min_auto_column_width", 180))
    required_table_w = fixed_w + auto_count * min_auto_col_w
    if required_table_w > width - 2 * margin_x:
        width = int(math.ceil(required_table_w + 2 * margin_x))
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
    table_h = header_h + max(1, len(rows)) * row_h
    panels = _info_panels(contract)
    panel_y = table_y + table_h + 24
    _panel_layouts, panels_h = _info_panel_layouts(panels, table_x, panel_y, table_w, width)
    height = int(max(contract.get("height", 0), panel_y + panels_h + 72 if panels else table_y + table_h + 110))
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
        f'<rect x="{table_x}" y="{table_y}" width="{table_w}" height="{table_h}" rx="{radius}" {_paint_attr(style, "fill", fill, "#FFFFFF", table.get("fill_opacity"))} stroke="{stroke_color}" stroke-opacity="{stroke_opacity}" stroke-width="{table.get("stroke_width", 1)}"/>'
    )
    parts.append(
        f'<rect x="{table_x}" y="{table_y}" width="{table_w}" height="{header_h}" rx="{radius}" {_paint_attr(style, "fill", header_fill, "#EEF6FF", table.get("header_opacity"))}/>'
    )
    cur_x = table_x
    for idx, col in enumerate(columns):
        col_w = col_widths[idx]
        if idx > 0:
            parts.append(f'<line x1="{cur_x}" y1="{table_y}" x2="{cur_x}" y2="{table_y + table_h}" stroke="{stroke_color}" stroke-opacity="{stroke_opacity}" stroke-width="1"/>')
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

    _render_info_panels(parts, panels, style, table_x, panel_y, table_w, width)
    _append_annotations(parts, contract, style, width, height)
    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def _accent_color(style: dict, item: dict, fallback_kind: str = "object") -> str:
    raw = item.get("accent")
    if raw:
        color = style_color(style, raw, "")
        if VALID_HEX.match(color):
            return color
    color = kind_accent(style, item.get("kind", fallback_kind))
    return color if VALID_HEX.match(color) else style_color(style, "line_primary", "#F4F8FF")


def _relation_color_candidates(rel: dict) -> list[str]:
    candidates = []
    for key in ("relation", "id", "label", "style"):
        raw = rel.get(key)
        if raw is None:
            continue
        value = str(raw).strip()
        if not value:
            continue
        candidates.append(value)
        normalized = re.sub(r"\s+", "_", value.lower())
        if normalized != value:
            candidates.append(normalized)
    return candidates


def _connector_relation_color(
    style: dict,
    rel: dict,
    *,
    default_token: str = "line_primary",
    source_item: dict | None = None,
    prefer_source: bool = False,
    palette_index: int | None = None,
    use_palette: bool = False,
) -> str:
    raw = rel.get("accent")
    if raw:
        color = style_color(style, raw, "")
        if VALID_HEX.match(color):
            return color
    if prefer_source and source_item:
        color = _accent_color(style, source_item, "object")
        if VALID_HEX.match(color):
            return color
    connector = _style_component(style, "connector")
    relation_colors = connector.get("relation_colors", {})
    if isinstance(relation_colors, dict):
        for key in _relation_color_candidates(rel):
            if key in relation_colors:
                color = style_color(style, relation_colors[key], "")
                if VALID_HEX.match(color):
                    return color
    if use_palette and palette_index is not None:
        color = _connector_palette_color(style, "relation_palette", palette_index)
        if color:
            return color
    return style_color(style, default_token, "#F4F8FF")


def _panel_rect_svg(
    style: dict,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    stroke: str | None = None,
    dasharray: str | None = None,
    radius: float | None = None,
    fill: str = "panel_fill",
    fill_opacity: float | None = None,
    stroke_opacity: float = 0.62,
) -> str:
    group = _style_component(style, "group")
    stroke_color = stroke or style_color(style, group.get("stroke", "line_primary"), "#334155")
    rx = radius if radius is not None else group.get("radius", 8)
    dash_attr = f' stroke-dasharray="{dasharray}"' if dasharray and dasharray != "none" else ""
    fill_attrs = _paint_attr(style, "fill", fill, "#FFFFFF", fill_opacity if fill_opacity is not None else group.get("opacity"))
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" {fill_attrs} '
        f'stroke="{stroke_color}" stroke-opacity="{stroke_opacity}" stroke-width="{group.get("stroke_width", 1)}"{dash_attr}/>'
    )


def _info_panels(contract: dict) -> list[dict]:
    panels = contract.get("info_panels", [])
    if not isinstance(panels, list):
        return []
    return [panel for panel in panels if isinstance(panel, dict)]


def _info_panel_item_text(item: object) -> tuple[str, str, str]:
    if isinstance(item, dict):
        label = str(item.get("label", "")).strip()
        value = str(item.get("value", item.get("text", ""))).strip()
        kind = str(item.get("kind", "")).strip()
        if label and value:
            return f"{label}: {value}", kind, str(item.get("accent", "")).strip()
        return label or value, kind, str(item.get("accent", "")).strip()
    return str(item), "", ""


def _info_panel_height(panel: dict, panel_w: float, canvas_w: float) -> float:
    body_size = _clamp(14.0 * _clamp(canvas_w / 1500.0, 0.95, 1.08), 14.0, 15.2)
    line_h = body_size + 4
    content_w = max(120, panel_w - 42)
    max_chars = max(16, int(content_w / (body_size * 0.60)))
    items = panel.get("items", [])
    if not isinstance(items, list):
        items = []
    total = 46.0
    for item in items:
        text, _kind, _accent = _info_panel_item_text(item)
        if not text:
            continue
        total += max(1, len(wrap_text(text, max_chars=max_chars, max_lines=3))) * line_h + 6
    return max(92.0, total + 14)


def _info_panel_layouts(panels: list[dict], x: float, y: float, w: float, canvas_w: float) -> tuple[list[tuple[dict, float, float, float, float]], float]:
    if not panels:
        return [], 0.0
    gap = 18.0
    if len(panels) == 3 and w < 1650:
        left_w = (w - gap) * 0.46
        right_w = w - gap - left_w
        right_h1 = _info_panel_height(panels[1], right_w, canvas_w)
        right_h2 = _info_panel_height(panels[2], right_w, canvas_w)
        right_total_h = right_h1 + gap + right_h2
        left_h = max(_info_panel_height(panels[0], left_w, canvas_w), right_total_h)
        layouts = [
            (panels[0], x, y, left_w, left_h),
            (panels[1], x + left_w + gap, y, right_w, right_h1),
            (panels[2], x + left_w + gap, y + right_h1 + gap, right_w, right_h2),
        ]
        return layouts, left_h
    cols = min(3, len(panels))
    panel_w = (w - (cols - 1) * gap) / cols
    layouts: list[tuple[dict, float, float, float, float]] = []
    col_bottoms = [y for _ in range(cols)]
    for panel in panels:
        col_idx = min(range(cols), key=lambda idx: (col_bottoms[idx], idx))
        panel_x = x + col_idx * (panel_w + gap)
        panel_y = col_bottoms[col_idx]
        panel_h = _info_panel_height(panel, panel_w, canvas_w)
        layouts.append((panel, panel_x, panel_y, panel_w, panel_h))
        col_bottoms[col_idx] = panel_y + panel_h + gap
    return layouts, max(col_bottoms) - y - gap


def _render_info_panels(parts: list[str], panels: list[dict], style: dict, x: float, y: float, w: float, canvas_w: float) -> float:
    layouts, total_h = _info_panel_layouts(panels, x, y, w, canvas_w)
    body_size = _clamp(14.0 * _clamp(canvas_w / 1500.0, 0.95, 1.08), 14.0, 15.2)
    line_h = body_size + 4
    for panel, px, py, pw, ph in layouts:
        color = _accent_color(style, panel, "object")
        panel_id = str(panel.get("id", panel.get("title", "panel"))).lower().replace(" ", "-")
        parts.append(f'<g class="info-panel" data-panel-id="{e(panel_id)}">')
        parts.append(_panel_rect_svg(style, px, py, pw, ph, fill="panel_fill", stroke=color, stroke_opacity=0.62, radius=6))
        parts.append(f'<text x="{px + 18}" y="{py + 28}" class="info-panel-title">{e(panel.get("title", "Info"))}</text>')
        items = panel.get("items", [])
        if not isinstance(items, list):
            items = []
        text_y = py + 56
        max_chars = max(16, int(max(120, pw - 48) / (body_size * 0.60)))
        for item in items:
            text, kind, accent = _info_panel_item_text(item)
            if not text:
                continue
            item_color = style_color(style, accent, "") if accent else kind_accent(style, kind or panel.get("kind", "object"))
            if not VALID_HEX.match(item_color):
                item_color = color
            lines = wrap_text(text, max_chars=max_chars, max_lines=3)
            parts.append(f'<rect x="{px + 18}" y="{text_y - 10}" width="9" height="9" rx="2" fill="{item_color}" opacity="0.95"/>')
            for idx, line in enumerate(lines):
                parts.append(
                    f'<text x="{px + 36}" y="{text_y + idx * line_h}" class="info-panel-item" '
                    f'style="font-size:{_fmt_px(body_size)}">{e(line)}</text>'
                )
            text_y += max(1, len(lines)) * line_h + 6
        parts.append('</g>')
    return total_h


MATRIX_TYPE_LABELS = {
    "direct": "Direct",
    "indirect": "Indirect",
    "dependency": "Dependency",
}


def _matrix_entities(contract: dict) -> list[tuple[int, dict]]:
    entities = [entity for entity in contract.get("entities", []) if isinstance(entity, dict) and entity.get("id")]
    return sorted(enumerate(entities), key=lambda pair: (pair[1].get("order", pair[0]), pair[0]))


def _matrix_relationships(contract: dict) -> list[dict]:
    return [rel for rel in contract.get("relationships", []) if isinstance(rel, dict)]


def _matrix_type_color(style: dict, rel_type: str, strength: int = 1, accent: object = None) -> str:
    if accent:
        color = style_color(style, accent, "")
        if VALID_HEX.match(color):
            return color
    if strength >= 3:
        return style_color(style, "accent_yellow", "#FFD84D")
    if rel_type == "indirect":
        return style_color(style, "accent_cyan", "#16D9FF")
    if rel_type == "dependency":
        return style_color(style, "accent_purple", "#B56CFF")
    return style_color(style, "line_primary", "#F4F8FF")


def _matrix_rel_index(relationships: list[dict]) -> dict[tuple[str, str], dict]:
    rels: dict[tuple[str, str], dict] = {}
    for rel in relationships:
        key = (str(rel.get("from", "")), str(rel.get("to", "")))
        current = rels.get(key)
        if current is None or int(rel.get("strength", 1)) > int(current.get("strength", 1)):
            rels[key] = rel
    return rels


def _matrix_focus_cell(contract: dict, relationships: list[dict]) -> tuple[str, str]:
    focus = contract.get("focus_cell", contract.get("selected_cell"))
    if isinstance(focus, dict) and focus.get("from") and focus.get("to"):
        return str(focus["from"]), str(focus["to"])
    if not relationships:
        return "", ""
    best = max(enumerate(relationships), key=lambda pair: (int(pair[1].get("strength", 1)), -pair[0]))[1]
    return str(best.get("from", "")), str(best.get("to", ""))


def _matrix_stats(entity_ids: list[str], relationships: list[dict]) -> dict:
    counts = {rel_type: 0 for rel_type in MATRIX_TYPE_LABELS}
    connected = {entity_id: {"count": 0, "strong": 0} for entity_id in entity_ids}
    for rel in relationships:
        rel_type = str(rel.get("type", "direct"))
        if rel_type in counts:
            counts[rel_type] += 1
        strength = int(rel.get("strength", 1))
        for endpoint in (str(rel.get("from", "")), str(rel.get("to", ""))):
            if endpoint not in connected:
                continue
            connected[endpoint]["count"] += 1
            if strength >= 3:
                connected[endpoint]["strong"] += 1
    return {
        "counts": counts,
        "total": len(relationships),
        "strong": sum(1 for rel in relationships if int(rel.get("strength", 1)) >= 3),
        "possible": max(0, len(entity_ids) * (len(entity_ids) - 1)),
        "connected": connected,
    }


def _render_matrix_panel(
    parts: list[str],
    panel: dict,
    style: dict,
    x: float,
    y: float,
    w: float,
    h: float,
    canvas_w: float,
    *,
    class_name: str = "",
) -> None:
    panel_id = str(panel.get("id", panel.get("title", "panel"))).lower().replace(" ", "-")
    color = _accent_color(style, panel, "object")
    scale = _clamp(canvas_w / 2200.0, 0.98, 1.1)
    title_size = _clamp(17.5 * scale, 17.5, 19.2)
    body_size = _clamp(17.2 * scale, 17.0, 18.4)
    line_h = body_size + 5
    parts.append(f'<g class="info-panel relationship-matrix-panel {class_name}" data-panel-id="{e(panel_id)}">')
    parts.append(_panel_rect_svg(style, x, y, w, h, fill="panel_fill", stroke=color, stroke_opacity=0.62, radius=6))
    parts.append(f'<text x="{x + 18}" y="{y + 32}" class="info-panel-title" style="font-size:{_fmt_px(title_size)}">{e(panel.get("title", "Info"))}</text>')
    items = panel.get("items", [])
    if not isinstance(items, list):
        items = []
    max_chars = max(18, int((w - 48) / (body_size * 0.52)))
    cur_y = y + 64
    for item in items:
        text, kind, accent = _info_panel_item_text(item)
        if not text:
            continue
        item_color = style_color(style, accent, "") if accent else kind_accent(style, kind or panel.get("kind", "object"))
        if not VALID_HEX.match(item_color):
            item_color = color
        lines = wrap_text(text, max_chars=max_chars, max_lines=3)
        parts.append(f'<rect x="{x + 18}" y="{cur_y - 10}" width="8" height="8" rx="2" fill="{item_color}"/>')
        for idx, line in enumerate(lines):
            parts.append(f'<text x="{x + 34}" y="{cur_y + idx * line_h}" class="info-panel-item" style="font-size:{_fmt_px(body_size)}">{e(line)}</text>')
        cur_y += len(lines) * line_h + 8
    parts.append('</g>')


def _render_matrix_primary_preview(
    parts: list[str],
    entities: list[dict],
    relationships: list[dict],
    style: dict,
    x: float,
    y: float,
    w: float,
    h: float,
    canvas_w: float,
) -> None:
    line = style_color(style, "line_primary", "#F4F8FF")
    secondary = style_color(style, "text_secondary", "#C9DAF5")
    parts.append('<g class="matrix-primary-preview">')
    parts.append(_panel_rect_svg(style, x, y, w, h, fill="panel_fill", stroke=line, stroke_opacity=0.54, radius=6))
    title_size = _clamp(17.5 * _clamp(canvas_w / 2200.0, 0.98, 1.1), 17.5, 19.2)
    note_size = _clamp(16.0 * _clamp(canvas_w / 2200.0, 0.98, 1.1), 16.0, 17.4)
    parts.append(f'<text x="{x + 18}" y="{y + 32}" class="info-panel-title" style="font-size:{_fmt_px(title_size)}">PRIMARY DIAGRAM (REFERENCE ONLY)</text>')
    parts.append(f'<text x="{x + 18}" y="{y + 62}" class="note" style="font-size:{_fmt_px(note_size)}">Dense reference view: too many lines to read directly.</text>')
    cx = x + w / 2
    cy = y + h / 2 + 10
    rx = max(120, w * 0.33)
    ry = max(92, h * 0.27)
    card_w = min(174, max(140, w / 3.9))
    card_h = 66
    positions: dict[str, tuple[float, float, float, float]] = {}
    count = max(1, len(entities))
    if count >= 8:
        dense_card_w = min(210, max(176, w * 0.32))
        card_h = 76
        top = y + 118
        bottom = y + h - 150
        lane_counts = [math.ceil(count / 2), count // 2]
        lane_x = [x + 34, x + w - dense_card_w - 34]
        lane_step = [
            (bottom - top) / max(1, lane_counts[0] - 1),
            (bottom - top) / max(1, lane_counts[1] - 1),
        ]
        lane_seen = [0, 0]
        for idx, entity in enumerate(entities):
            lane = idx % 2
            lane_idx = lane_seen[lane]
            lane_seen[lane] += 1
            center_y = top + lane_idx * lane_step[lane]
            positions[str(entity["id"])] = (lane_x[lane], center_y - card_h / 2, dense_card_w, card_h)
    else:
        for idx, entity in enumerate(entities):
            angle = -math.pi / 2 + 2 * math.pi * idx / count
            ex = cx + rx * math.cos(angle) - card_w / 2
            ey = cy + ry * math.sin(angle) - card_h / 2
            positions[str(entity["id"])] = (ex, ey, card_w, card_h)
    for rel in relationships[: min(26, len(relationships))]:
        source = str(rel.get("from", ""))
        target = str(rel.get("to", ""))
        if source not in positions or target not in positions:
            continue
        sx, sy, sw, sh = positions[source]
        tx, ty, tw, th = positions[target]
        color = _matrix_type_color(style, str(rel.get("type", "direct")), int(rel.get("strength", 1)), rel.get("accent"))
        dash = ' stroke-dasharray="5 5"' if rel.get("type") != "direct" else ""
        parts.append(
            f'<line x1="{sx + sw/2}" y1="{sy + sh/2}" x2="{tx + tw/2}" y2="{ty + th/2}" '
            f'class="matrix-preview-link" stroke="{color}" stroke-opacity="0.42" stroke-width="{1.0 + int(rel.get("strength", 1)) * 0.35}"{dash}/>'
        )
    for entity in entities:
        ex, ey, ew, eh = positions[str(entity["id"])]
        color = _accent_color(style, entity, "object")
        parts.append(f'<g class="matrix-preview-node" data-entity="{e(entity["id"])}">')
        parts.append(_panel_rect_svg(style, ex, ey, ew, eh, fill="panel_fill", stroke=color, stroke_opacity=0.9, radius=6))
        parts.append(icon_svg(str(entity.get("kind", "object")), ex + 12, ey + eh / 2 - 10, color, style))
        preview_chars = max(9, int((ew - 54) / max(8.8, note_size * 0.64)))
        label = wrap_text(str(entity.get("label", entity["id"])), max_chars=preview_chars, max_lines=1)[0]
        sub = wrap_text(str(entity.get("subtitle", "Entity")), max_chars=preview_chars, max_lines=1)[0]
        parts.append(f'<text x="{ex + 44}" y="{ey + 28}" class="matrix-preview-title" style="font-size:{_fmt_px(note_size)};font-weight:700;fill:{line}">{e(label)}</text>')
        parts.append(f'<text x="{ex + 44}" y="{ey + 52}" class="matrix-preview-sub" style="font-size:{_fmt_px(note_size - 0.8)};fill:{secondary}">{e(sub)}</text>')
        parts.append('</g>')
    footer = "Too many edges here. Read the matrix for type, strength, and coverage."
    footer_chars = max(18, int((w - 68) / (note_size * 0.54)))
    footer_lines = wrap_text(footer, max_chars=footer_chars, max_lines=2)
    footer_line_h = note_size + 5
    footer_y = y + h - 28 - (len(footer_lines) - 1) * footer_line_h
    for idx, line_text in enumerate(footer_lines):
        parts.append(
            f'<text x="{x + 34}" y="{footer_y + idx * footer_line_h}" class="note" '
            f'style="font-size:{_fmt_px(note_size)};fill:{secondary}">{e(line_text)}</text>'
        )
    parts.append('</g>')


def _render_relationship_matrix(contract: dict, style: dict, diagram_type: str) -> str:
    entity_pairs = _matrix_entities(contract)
    entities = [entity for _idx, entity in entity_pairs]
    entity_ids = [str(entity["id"]) for entity in entities]
    relationships = _matrix_relationships(contract)
    rel_index = _matrix_rel_index(relationships)
    focus_from, focus_to = _matrix_focus_cell(contract, relationships)
    focus_rel = rel_index.get((focus_from, focus_to))
    stats = _matrix_stats(entity_ids, relationships)
    entity_by_id = {str(entity["id"]): entity for entity in entities}

    n = len(entities)
    labels = [str(entity.get("label", entity["id"])) for entity in entities]
    margin = float(contract.get("canvas_margin_x", 48))
    top_y = float(contract.get("top_y", 118))
    gap = 20.0
    main_y = top_y
    left_w = 580.0
    matrix_pad_x = 20.0
    bottom_panel_h = 330.0

    def matrix_label_size_for(canvas_w: float) -> float:
        scale = _clamp(canvas_w / 2200.0, 0.98, 1.1)
        return _clamp(18.5 * scale, 18.2, 20.2)

    def matrix_label_width_for(canvas_w: float) -> float:
        label_char_cap = max(8.0, float(contract.get("matrix_label_char_cap", 10)))
        return label_char_cap * matrix_label_size_for(canvas_w) * 0.54

    base_width = int(max(float(contract.get("width", 0) or 0), 1960, 1180 + n * 88))
    label_size = matrix_label_size_for(base_width)
    longest_label_w = min(max((len(label) * label_size * 0.54 for label in labels), default=0.0), matrix_label_width_for(base_width))
    row_label_w = max(220.0, longest_label_w + 78.0)
    min_cell_w = max(92.0, longest_label_w + 22.0)
    min_center_w = row_label_w + n * min_cell_w + 2 * matrix_pad_x
    min_width = 2 * margin + left_w + gap + min_center_w
    width = int(max(base_width, math.ceil(min_width)))

    label_size = matrix_label_size_for(width)
    longest_label_w = min(max((len(label) * label_size * 0.54 for label in labels), default=0.0), matrix_label_width_for(width))
    row_label_w = max(220.0, longest_label_w + 78.0)
    min_cell_w = max(92.0, longest_label_w + 22.0)
    min_center_w = row_label_w + n * min_cell_w + 2 * matrix_pad_x
    min_width = 2 * margin + left_w + gap + min_center_w
    width = int(max(width, math.ceil(min_width)))

    center_w = width - 2 * margin - left_w - gap
    cell_w = max(min_cell_w, (center_w - 2 * matrix_pad_x - row_label_w) / max(1, n))
    cell_h = _clamp(cell_w * 0.82, 82.0, 96.0)
    matrix_w = row_label_w + n * cell_w
    header_h = 94.0
    matrix_h = header_h + n * cell_h
    main_h = max(650.0, matrix_h + 112.0)
    bottom_y = main_y + main_h + gap
    height = int(max(float(contract.get("height", 0) or 0), bottom_y + bottom_panel_h + 72))

    left_x = margin
    center_x = left_x + left_w + gap
    line = style_color(style, "line_primary", "#F4F8FF")
    secondary = style_color(style, "text_secondary", "#C9DAF5")
    grid_color = style_color(style, "line_primary", "#F4F8FF")
    panel_fill = "panel_fill"

    parts = _svg_shell_start(contract, style, width, height, diagram_type)

    _render_matrix_primary_preview(parts, entities, relationships, style, left_x, main_y, left_w, main_h, width)

    parts.append('<g class="relationship-matrix-grid">')
    parts.append(_panel_rect_svg(style, center_x, main_y, center_w, main_h, fill=panel_fill, stroke=line, stroke_opacity=0.56, radius=6))
    matrix_scale = _clamp(width / 2200.0, 0.98, 1.1)
    panel_title_size = _clamp(17.5 * matrix_scale, 17.5, 19.2)
    note_size = _clamp(16.0 * matrix_scale, 16.0, 17.4)
    index_size = _clamp(14.5 * matrix_scale, 14.5, 15.8)
    label_size = matrix_label_size_for(width)
    cell_size = _clamp(30.0 * matrix_scale, 28.5, 33.0)
    parts.append(f'<text x="{center_x + 20}" y="{main_y + 34}" class="info-panel-title" style="font-size:{_fmt_px(panel_title_size)}">RELATIONSHIP MATRIX</text>')
    parts.append(f'<text x="{center_x + 20}" y="{main_y + 64}" class="note" style="font-size:{_fmt_px(note_size)}">Entities x Entities</text>')
    filter_x = center_x + center_w - 500
    filter_y = main_y + 18
    for idx, rel_type in enumerate(("direct", "indirect", "dependency")):
        color = _matrix_type_color(style, rel_type, 1)
        fx = filter_x + idx * 158
        parts.append(f'<rect x="{fx}" y="{filter_y}" width="16" height="16" rx="3" fill="{color}" opacity="0.9"/>')
        parts.append(f'<text x="{fx + 24}" y="{filter_y + 14}" class="note" style="font-size:{_fmt_px(note_size)};fill:{line}">{MATRIX_TYPE_LABELS[rel_type]}</text>')
    matrix_x = center_x + matrix_pad_x
    matrix_y = main_y + 96
    parts.append(f'<rect x="{matrix_x}" y="{matrix_y}" width="{matrix_w}" height="{matrix_h}" rx="6" fill="none" stroke="{grid_color}" stroke-opacity="0.58" stroke-width="1"/>')
    for idx in range(n + 1):
        x = matrix_x + row_label_w + idx * cell_w
        parts.append(f'<line x1="{x}" y1="{matrix_y}" x2="{x}" y2="{matrix_y + matrix_h}" stroke="{grid_color}" stroke-opacity="0.48" stroke-width="1"/>')
        y = matrix_y + header_h + idx * cell_h
        parts.append(f'<line x1="{matrix_x}" y1="{y}" x2="{matrix_x + matrix_w}" y2="{y}" stroke="{grid_color}" stroke-opacity="0.48" stroke-width="1"/>')
    parts.append(f'<line x1="{matrix_x}" y1="{matrix_y + header_h}" x2="{matrix_x + matrix_w}" y2="{matrix_y + header_h}" stroke="{grid_color}" stroke-opacity="0.68" stroke-width="1.2"/>')
    for idx, entity in enumerate(entities):
        label = labels[idx]
        col_label = _fit_text_to_width(label, cell_w - 12.0, label_size, min_chars=6, char_factor=0.54)
        row_label = _fit_text_to_width(label, row_label_w - 82.0, label_size, min_chars=6, char_factor=0.54)
        col_x = matrix_x + row_label_w + idx * cell_w + cell_w / 2
        row_y = matrix_y + header_h + idx * cell_h + cell_h / 2
        parts.append(f'<text x="{col_x}" y="{matrix_y + 34}" text-anchor="middle" class="matrix-col-index" style="font-size:{_fmt_px(index_size)};fill:{secondary}">{idx + 1:02d}</text>')
        parts.append(f'<text x="{col_x}" y="{matrix_y + 64}" text-anchor="middle" class="matrix-col-label" style="font-size:{_fmt_px(label_size)};font-weight:700;fill:{line}">{e(col_label)}</text>')
        parts.append(f'<text x="{matrix_x + 20}" y="{row_y + index_size * 0.35}" class="matrix-row-index" style="font-size:{_fmt_px(index_size)};fill:{secondary}">{idx + 1:02d}</text>')
        parts.append(f'<text x="{matrix_x + 62}" y="{row_y + label_size * 0.35}" class="matrix-row-label" style="font-size:{_fmt_px(label_size)};font-weight:700;fill:{line}">{e(row_label)}</text>')

    for row_idx, source in enumerate(entities):
        for col_idx, target in enumerate(entities):
            source_id = str(source["id"])
            target_id = str(target["id"])
            x = matrix_x + row_label_w + col_idx * cell_w
            y = matrix_y + header_h + row_idx * cell_h
            rel = rel_index.get((source_id, target_id))
            state = "empty" if rel is None else str(rel.get("type", "direct"))
            parts.append(f'<rect x="{x}" y="{y}" width="{cell_w}" height="{cell_h}" class="matrix-cell" data-from="{e(source_id)}" data-to="{e(target_id)}" data-state="{e(state)}" fill="none"/>')
            cell_text_y = y + cell_h / 2 + cell_size * 0.32
            if source_id == target_id:
                parts.append(f'<text x="{x + cell_w/2}" y="{cell_text_y}" text-anchor="middle" class="matrix-cell-value" style="font-size:{_fmt_px(cell_size)};fill:{secondary}">-</text>')
                continue
            if rel is None:
                parts.append(f'<text x="{x + cell_w/2}" y="{cell_text_y}" text-anchor="middle" class="matrix-cell-value" style="font-size:{_fmt_px(cell_size)};fill:{secondary};opacity:0.72">-</text>')
                continue
            strength = int(rel.get("strength", 1))
            color = _matrix_type_color(style, str(rel.get("type", "direct")), strength, rel.get("accent"))
            marker_r = max(14.0, min(24.0, 9.0 + strength * 4.0, min(cell_w, cell_h) * 0.28))
            parts.append(f'<circle cx="{x + cell_w/2}" cy="{y + cell_h/2}" r="{marker_r}" fill="{color}" fill-opacity="0.13" stroke="{color}" stroke-opacity="0.55" stroke-width="1"/>')
            parts.append(f'<text x="{x + cell_w/2}" y="{cell_text_y}" text-anchor="middle" class="matrix-cell-value" style="font-size:{_fmt_px(cell_size)};font-weight:700;fill:{color}">{strength}</text>')
    parts.append('</g>')

    bottom_x = margin
    bottom_w = width - 2 * margin
    detail_w = max(520.0, bottom_w * 0.34)
    summary_w = max(480.0, bottom_w * 0.28)
    top_conn_w = bottom_w - detail_w - summary_w - 2 * gap
    if top_conn_w < 520.0:
        equal_w = (bottom_w - 2 * gap) / 3
        detail_w = summary_w = top_conn_w = equal_w
    detail_x = bottom_x
    summary_x = detail_x + detail_w + gap
    top_conn_x = summary_x + summary_w + gap
    focus_label_from = entity_by_id.get(focus_from, {}).get("label", focus_from)
    focus_label_to = entity_by_id.get(focus_to, {}).get("label", focus_to)
    detail_items = [
        {"label": "From", "value": focus_label_from},
        {"label": "To", "value": focus_label_to},
    ]
    if focus_rel:
        detail_items.extend([
            {"label": "Type", "value": MATRIX_TYPE_LABELS.get(str(focus_rel.get("type")), str(focus_rel.get("type"))), "kind": str(focus_rel.get("type"))},
            {"label": "Strength", "value": f'{focus_rel.get("strength", 1)}'},
            {"label": "Path", "value": focus_rel.get("path", f"{focus_label_from} -> {focus_label_to}")},
            focus_rel.get("note", focus_rel.get("label", "Relationship is declared in the matrix.")),
        ])
    else:
        detail_items.append("No relationship is declared for this focus pair.")
    detail_y = bottom_y
    _render_matrix_panel(parts, {"id": "focus_cell", "title": "Focus Relationship", "kind": "query", "items": detail_items}, style, detail_x, detail_y, detail_w, bottom_panel_h, width, class_name="matrix-focus-detail-panel")

    summary_y = bottom_y
    total = max(1, stats["total"])
    parts.append('<g class="matrix-summary-panel info-panel">')
    parts.append(_panel_rect_svg(style, summary_x, summary_y, summary_w, bottom_panel_h, fill="panel_fill", stroke=line, stroke_opacity=0.62, radius=6))
    parts.append(f'<text x="{summary_x + 18}" y="{summary_y + 32}" class="info-panel-title" style="font-size:{_fmt_px(panel_title_size)}">SUMMARY</text>')
    metric_w = (summary_w - 56) / 3
    metric_y = summary_y + 80
    for idx, (value, label) in enumerate(((n, "Entities"), (stats["total"], "Relationships"), (stats["strong"], "Strong"))):
        mx = summary_x + 18 + idx * metric_w
        parts.append(f'<text x="{mx}" y="{metric_y}" class="matrix-summary-value" style="font-size:30px;font-weight:700;fill:{line}">{value}</text>')
        parts.append(f'<text x="{mx}" y="{metric_y + 24}" class="note" style="font-size:{_fmt_px(note_size - 1)}">{label}</text>')
    dist_y = summary_y + 132
    bar_x = summary_x + 154
    bar_w = summary_w - 230
    for idx, rel_type in enumerate(("direct", "indirect", "dependency")):
        color = _matrix_type_color(style, rel_type, 1)
        count = stats["counts"][rel_type]
        pct = round(count / total * 100)
        y = dist_y + idx * 34
        fill_w = bar_w * count / total
        parts.append(f'<text x="{summary_x + 24}" y="{y}" class="matrix-summary-label" style="font-size:{_fmt_px(note_size)};font-weight:700;fill:{line}">{MATRIX_TYPE_LABELS[rel_type]}</text>')
        parts.append(f'<rect x="{bar_x}" y="{y - 13}" width="{bar_w}" height="14" rx="2" fill="{style_color(style, "background_dark", "#031E42")}" stroke="{line}" stroke-opacity="0.18"/>')
        parts.append(f'<rect x="{bar_x}" y="{y - 13}" width="{fill_w}" height="14" rx="2" fill="{color}" opacity="0.86" class="matrix-distribution-bar"/>')
        parts.append(f'<text x="{summary_x + summary_w - 24}" y="{y}" text-anchor="end" class="note" style="font-size:{_fmt_px(note_size)}">{count} ({pct}%)</text>')
    parts.append('</g>')

    connected_rows = sorted(
        ((entity_id, values["count"], values["strong"]) for entity_id, values in stats["connected"].items()),
        key=lambda row: (-row[1], -row[2], entity_by_id[row[0]].get("label", row[0])),
    )
    top_conn_y = bottom_y
    top_conn_h = bottom_panel_h
    max_rows = max(3, int((top_conn_h - 72) // 32))
    connected_rows = connected_rows[:max_rows]
    parts.append('<g class="matrix-top-connected-panel info-panel">')
    parts.append(_panel_rect_svg(style, top_conn_x, top_conn_y, top_conn_w, top_conn_h, fill="panel_fill", stroke=line, stroke_opacity=0.62, radius=6))
    parts.append(f'<text x="{top_conn_x + 18}" y="{top_conn_y + 32}" class="info-panel-title" style="font-size:{_fmt_px(panel_title_size)}">TOP CONNECTED ENTITIES</text>')
    max_count = max((row[1] for row in connected_rows), default=1)
    for idx, (entity_id, count_value, strong_value) in enumerate(connected_rows):
        y = top_conn_y + 76 + idx * 32
        rank_bar_x = top_conn_x + top_conn_w - 206
        label_x = top_conn_x + 58
        label_w = max(90.0, rank_bar_x - label_x - 18.0)
        label = _fit_text_to_width(
            str(entity_by_id[entity_id].get("label", entity_id)),
            label_w,
            note_size + 0.6,
            min_chars=8,
            char_factor=0.56,
        )
        rank_bar_w = 112 * count_value / max_count
        parts.append(f'<text x="{top_conn_x + 28}" y="{y}" class="matrix-rank" style="font-size:{_fmt_px(note_size)};fill:{secondary}">{idx + 1}</text>')
        parts.append(f'<text x="{label_x}" y="{y}" class="matrix-rank-label" style="font-size:{_fmt_px(note_size + 0.6)};font-weight:700;fill:{line}">{e(label)}</text>')
        parts.append(f'<rect x="{rank_bar_x}" y="{y - 13}" width="112" height="14" rx="2" fill="{style_color(style, "background_dark", "#031E42")}" stroke="{line}" stroke-opacity="0.18"/>')
        parts.append(f'<rect x="{rank_bar_x}" y="{y - 13}" width="{rank_bar_w}" height="14" rx="2" fill="{style_color(style, "accent_cyan", "#16D9FF")}" opacity="0.82"/>')
        parts.append(f'<text x="{top_conn_x + top_conn_w - 78}" y="{y}" class="matrix-rank-value" style="font-size:{_fmt_px(note_size)};fill:{line}">{count_value}</text>')
        parts.append(f'<text x="{top_conn_x + top_conn_w - 34}" y="{y}" class="matrix-rank-strong" style="font-size:{_fmt_px(note_size)};fill:{style_color(style, "accent_yellow", "#FFD84D")}">{strong_value}</text>')
    parts.append('</g>')

    _append_annotations(parts, contract, style, width, height)
    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def _ontology_panel_groups(panels: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    # Dense ontology maps stay more readable when the concept canvas keeps the
    # horizontal space; legacy left/right placement is treated as bottom-panel
    # ordering guidance instead of reserving side gutters.
    return [], [], panels


def _matrix_text_lines(text: object, max_chars: int, max_lines: int) -> list[str]:
    return wrap_text(str(text or ""), max_chars=max_chars, max_lines=max_lines)


def _matrix_item_svg(item: dict, x: float, y: float, w: float, h: float, style: dict, canvas_w: float) -> str:
    kind = str(item.get("kind", "object"))
    color = _accent_color(style, item, kind)
    text_primary = style_color(style, "text_primary", "#0F172A")
    text_secondary = style_color(style, "text_secondary", "#64748B")
    title_size = _clamp(18.0 * _clamp(canvas_w / 1500.0, 0.92, 1.08), 18.0, 19.5)
    sub_size = _clamp(14.0 * _clamp(canvas_w / 1500.0, 0.92, 1.08), 13.5, 15.0)
    text_x = x + 42
    text_w = max(70, w - 54)
    title_lines = _matrix_text_lines(item.get("label", item.get("id", "Item")), max(7, int(text_w / (title_size * 0.55))), 2)
    sub_lines = _matrix_text_lines(item.get("subtitle", ""), max(9, int(text_w / (sub_size * 0.5))), 1)
    title_line_h = title_size + 2
    sub_line_h = sub_size + 2
    sub_gap = 4
    block_h = len(title_lines) * title_line_h + (sub_gap + sub_line_h if sub_lines else 0)
    top = y + (h - block_h) / 2
    parts = [f'<g id="matrix-item-{e(item.get("id", ""))}" class="boundary-matrix-item" data-kind="{e(kind)}">']
    parts.append(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" '
        f'{_paint_attr(style, "fill", "card_fill", "#FFFFFF", 1)} stroke="{color}" stroke-width="1.2"/>'
    )
    parts.append(icon_svg(kind, x + 14, y + h / 2 - 10, color, style))
    for idx, line in enumerate(title_lines):
        parts.append(
            f'<text x="{text_x}" y="{top + title_size + idx * title_line_h}" '
            f'text-anchor="start" class="matrix-title" style="font-size:{_fmt_px(title_size)};font-weight:700;fill:{text_primary}">{e(line)}</text>'
        )
    if sub_lines:
        sub_y = top + len(title_lines) * title_line_h + sub_gap + sub_size
        parts.append(
            f'<text x="{text_x}" y="{sub_y}" text-anchor="start" class="matrix-sub" '
            f'style="font-size:{_fmt_px(sub_size)};font-weight:500;fill:{text_secondary}">{e(sub_lines[0])}</text>'
        )
    parts.append('</g>')
    return "".join(parts)


def _matrix_connector_path(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> str:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    if ax + aw / 2 <= bx + bw / 2:
        sx, sy = ax + aw, ay + ah / 2
        tx, ty = bx, by + bh / 2
    else:
        sx, sy = ax, ay + ah / 2
        tx, ty = bx + bw, by + bh / 2
    if abs(sy - ty) < 2:
        return _rounded_path([(sx, sy), (tx, ty)])
    mid_x = (sx + tx) / 2
    return _rounded_path([(sx, sy), (mid_x, sy), (mid_x, ty), (tx, ty)])


def _matrix_external_connector_path(
    source: tuple[float, float, float, float],
    target: tuple[float, float, float, float],
    corridor_x: float,
    exit_y: float,
) -> str:
    sx = source[0] + source[2] if corridor_x >= source[0] + source[2] / 2 else source[0]
    sy = source[1] + source[3] / 2
    tx = target[0] + target[2] / 2
    ty = target[1]
    return _rounded_path([(sx, sy), (corridor_x, sy), (corridor_x, exit_y), (tx, exit_y), (tx, ty)])


def _render_compact_table(
    parts: list[str],
    style: dict,
    title: str,
    columns: list[dict],
    rows: list[dict],
    x: float,
    y: float,
    w: float,
    canvas_w: float,
) -> float:
    if not columns:
        return 0
    metrics = _table_text_metrics(style, canvas_w)
    header_size = _clamp(metrics["header_size"] - 1.0, 13.5, 16.0)
    cell_size = _clamp(metrics["cell_size"] - 2.2, 13.5, 16.0)
    title_h = 28
    header_h = 34
    row_h = 34
    h = title_h + header_h + max(1, len(rows)) * row_h
    table = _style_component(style, "table")
    stroke_color, stroke_opacity = style_paint(style, table.get("stroke", "line_primary"), "#334155")
    stroke_opacity = table.get("grid_opacity", stroke_opacity if stroke_opacity is not None else 0.55)
    parts.append(_panel_rect_svg(style, x, y, w, h, fill="panel_fill", stroke=stroke_color, stroke_opacity=stroke_opacity, radius=6))
    parts.append(f'<text x="{x + w/2}" y="{y + 20}" text-anchor="middle" class="table-header" style="font-size:{_fmt_px(header_size)}">{e(title)}</text>')
    col_widths = _column_widths(columns, w - 24)
    table_x = x + 12
    table_y = y + title_h
    parts.append(f'<line x1="{table_x}" y1="{table_y}" x2="{table_x + w - 24}" y2="{table_y}" stroke="{stroke_color}" stroke-opacity="{stroke_opacity}" stroke-width="1"/>')
    cur_x = table_x
    for idx, col in enumerate(columns):
        col_w = col_widths[idx]
        if idx > 0:
            parts.append(f'<line x1="{cur_x}" y1="{table_y}" x2="{cur_x}" y2="{table_y + header_h + max(1, len(rows))*row_h}" stroke="{stroke_color}" stroke-opacity="{stroke_opacity}" stroke-width="1"/>')
        anchor, offset = _text_anchor_for(col.get("align"))
        text_x = cur_x + 10 + (col_w - 20) * offset
        parts.append(f'<text x="{text_x}" y="{table_y + 22}" text-anchor="{anchor}" class="table-header" style="font-size:{_fmt_px(header_size)}">{e(col.get("label", col.get("id")))}</text>')
        cur_x += col_w
    parts.append(f'<line x1="{table_x}" y1="{table_y + header_h}" x2="{table_x + w - 24}" y2="{table_y + header_h}" stroke="{stroke_color}" stroke-opacity="{stroke_opacity}" stroke-width="1"/>')
    if not rows:
        parts.append(f'<text x="{x + w/2}" y="{table_y + header_h + 22}" text-anchor="middle" class="table-cell-secondary" style="font-size:{_fmt_px(cell_size)}">No rows</text>')
    for row_idx, row in enumerate(rows):
        row_y = table_y + header_h + row_idx * row_h
        if row_idx > 0:
            parts.append(f'<line x1="{table_x}" y1="{row_y}" x2="{table_x + w - 24}" y2="{row_y}" stroke="{stroke_color}" stroke-opacity="{stroke_opacity}" stroke-width="1"/>')
        cur_x = table_x
        for idx, col in enumerate(columns):
            col_w = col_widths[idx]
            anchor, offset = _text_anchor_for(col.get("align"))
            text_x = cur_x + 10 + (col_w - 20) * offset
            max_chars = max(5, int((col_w - 20) / max(7.0, cell_size * 0.52)))
            lines = wrap_text(str(row.get(col["id"], "")), max_chars=max_chars, max_lines=1)
            klass = "table-cell" if idx == 0 else "table-cell-secondary"
            parts.append(f'<text x="{text_x}" y="{row_y + 22}" text-anchor="{anchor}" class="{klass}" style="font-size:{_fmt_px(cell_size)}">{e(lines[0])}</text>')
            cur_x += col_w
    return h


def _render_boundary_ownership_matrix(contract: dict, style: dict, diagram_type: str) -> str:
    metrics = layout_metrics(style)
    width = int(contract.get("width", 1700))
    margin_x = int(contract.get("canvas_margin_x", metrics["canvas_margin_x"]))
    top_y = int(contract.get("top_y", metrics["top_y"]))
    domains = [d for d in contract.get("domains", []) if isinstance(d, dict)]
    externals = [p for p in contract.get("external_partners", []) if isinstance(p, dict)]
    assignments = contract.get("ownership_assignments") if isinstance(contract.get("ownership_assignments"), dict) else {}
    assignment_columns = [c for c in assignments.get("columns", []) if isinstance(c, dict)]
    assignment_rows = [r for r in assignments.get("rows", []) if isinstance(r, dict)]
    ownership_key = [k for k in contract.get("ownership_key", []) if isinstance(k, dict)]

    legend_h = 56
    map_y = top_y + legend_h + 18
    item_h = 78
    item_gap = 10
    domain_header_h = 42
    lane_pad = 18
    max_domain_items = max((len(d.get("systems", []) or []) + len(d.get("assets", []) or []) + (1 if d.get("owner") else 0) for d in domains), default=1)
    boundary_h = max(320, 78 + domain_header_h + max_domain_items * (item_h + item_gap) + 34)
    external_gap_y = 24 if externals else 0
    external_cols = 0
    external_rows = 0
    external_h = 0
    if externals:
        external_available_w = width - 2 * margin_x - 48
        external_cols = max(1, min(len(externals), min(5, int((external_available_w + 18) / (210 + 18)))))
        external_rows = math.ceil(len(externals) / external_cols)
        external_h = 62 + external_rows * item_h + max(0, external_rows - 1) * item_gap + 24
    table_y = map_y + boundary_h + external_gap_y + external_h + 26
    bottom_h = max(130, 28 + 34 + max(1, len(assignment_rows)) * 34)
    height = int(max(contract.get("height", 0), table_y + bottom_h + 72))

    parts = _svg_shell_start(contract, style, width, height, diagram_type)
    line = style_color(style, "line_primary", "#F4F8FF")
    secondary = style_color(style, "text_secondary", "#C9DAF5")
    cyan = style_color(style, "accent_cyan", "#16D9FF")
    yellow = style_color(style, "accent_yellow", "#FFD84D")
    green = style_color(style, "accent_green", "#6EE66E")
    purple = style_color(style, "accent_purple", "#B56CFF")
    orange = style_color(style, "accent_orange", "#FF9F2E")
    panel_fill = "panel_fill"

    legend_x = margin_x
    legend_y = top_y - 8
    legend_w = width - 2 * margin_x
    parts.append(_panel_rect_svg(style, legend_x, legend_y, legend_w, legend_h, fill=panel_fill, stroke=line, stroke_opacity=0.58, radius=6))
    legend_items = [
        ("Domain", cyan, "rect"),
        ("System / Application", green, "rect"),
        ("Data / Asset", yellow, "rect"),
        ("External", purple, "rect"),
        ("Ownership Boundary", line, "line"),
        ("Shared Responsibility", purple, "dash"),
        ("Data Flow", orange, "arrow"),
    ]
    lx = legend_x + 18
    ly = legend_y + 22
    for label, color, shape in legend_items:
        if shape == "line":
            parts.append(f'<line x1="{lx}" y1="{ly}" x2="{lx+30}" y2="{ly}" stroke="{color}" stroke-width="1.4"/>')
        elif shape == "dash":
            parts.append(f'<line x1="{lx}" y1="{ly}" x2="{lx+30}" y2="{ly}" stroke="{color}" stroke-width="1.4" stroke-dasharray="6 5"/>')
        elif shape == "arrow":
            parts.append(f'<path d="M {lx} {ly} L {lx+30} {ly}" class="edge" marker-end="url(#arrow)" style="stroke:{color};opacity:0.95"/>')
        else:
            parts.append(f'<rect x="{lx}" y="{ly-7}" width="28" height="14" rx="3" fill="none" stroke="{color}" stroke-width="1.3"/>')
        parts.append(f'<text x="{lx+40}" y="{ly+4}" class="note" style="font-size:14px">{e(label)}</text>')
        lx += max(128, len(label) * 8 + 70)

    boundary_x = margin_x
    boundary_w = width - 2 * margin_x
    boundary = contract.get("boundary") if isinstance(contract.get("boundary"), dict) else {}
    boundary_label = boundary.get("label", "Enterprise Boundary")
    parts.append(_panel_rect_svg(style, boundary_x, map_y, boundary_w, boundary_h, fill="panel_fill", stroke=line, stroke_opacity=0.7, radius=8, dasharray="10 7"))
    parts.append(f'<text x="{boundary_x + boundary_w/2}" y="{map_y + 28}" text-anchor="middle" class="group-label">{e(boundary_label)}</text>')

    domain_gap = 18
    domain_count = max(1, len(domains))
    domain_area_x = boundary_x + 28
    domain_area_y = map_y + 58
    domain_area_w = boundary_w - 56
    domain_col_w = (domain_area_w - (domain_count - 1) * domain_gap) / domain_count
    item_positions: dict[str, tuple[float, float, float, float]] = {}
    domain_positions: dict[str, tuple[float, float, float, float]] = {}
    item_domains: dict[str, str] = {}
    domain_palette = [cyan, cyan, orange, yellow, green]
    for idx, domain in enumerate(domains):
        dx = domain_area_x + idx * (domain_col_w + domain_gap)
        dy = domain_area_y
        domain_id = str(domain["id"])
        color = _accent_color(style, domain, "capability") if domain.get("accent") else domain_palette[idx % len(domain_palette)]
        parts.append(_panel_rect_svg(style, dx, dy, domain_col_w, boundary_h - 86, fill="panel_fill", stroke=color, stroke_opacity=0.7, radius=6))
        parts.append(f'<text x="{dx + domain_col_w/2}" y="{dy + 24}" text-anchor="middle" class="group-label" style="fill:{line}">{e(domain.get("label", domain.get("id")))}</text>')
        if domain.get("subtitle"):
            parts.append(f'<text x="{dx + domain_col_w/2}" y="{dy + 43}" text-anchor="middle" class="note" style="font-size:14px">{e(domain.get("subtitle"))}</text>')
        item_x = dx + lane_pad
        item_w = domain_col_w - 2 * lane_pad
        item_y = dy + domain_header_h + 16
        domain_rect = (dx, dy, domain_col_w, boundary_h - 86)
        item_positions[domain_id] = domain_rect
        domain_positions[domain_id] = domain_rect
        item_domains[domain_id] = domain_id
        for item in list(domain.get("systems", []) or []) + list(domain.get("assets", []) or []):
            item_id = str(item["id"])
            item_positions[item_id] = (item_x, item_y, item_w, item_h)
            item_domains[item_id] = domain_id
            parts.append(_matrix_item_svg(item, item_x, item_y, item_w, item_h, style, width))
            item_y += item_h + item_gap
        if domain.get("owner"):
            owner_id = f'{domain.get("id")}_owner'
            owner_item = {
                "id": owner_id,
                "label": str(domain.get("owner")),
                "subtitle": "owner / steward",
                "kind": "quality",
                "accent": "accent_yellow",
            }
            item_positions[owner_id] = (item_x, item_y, item_w, item_h)
            item_domains[owner_id] = domain_id
            parts.append(_matrix_item_svg(owner_item, item_x, item_y, item_w, item_h, style, width))

    external_ids: set[str] = set()
    if externals:
        ex_x = boundary_x
        ex_y = map_y + boundary_h + external_gap_y
        ex_w = boundary_w
        parts.append(_panel_rect_svg(style, ex_x, ex_y, ex_w, external_h, fill="panel_fill", stroke=purple, stroke_opacity=0.78, radius=8))
        parts.append(f'<text x="{ex_x + ex_w/2}" y="{ex_y + 30}" text-anchor="middle" class="group-label" style="fill:{line}">EXTERNAL PARTNERS</text>')
        external_card_gap = 18
        raw_item_w = (ex_w - 48 - (external_cols - 1) * external_card_gap) / external_cols
        item_w = min(260, raw_item_w)
        row_w = external_cols * item_w + (external_cols - 1) * external_card_gap
        row_x0 = ex_x + (ex_w - row_w) / 2
        item_y0 = ex_y + 62
        for idx, item in enumerate(externals):
            item.setdefault("kind", "object")
            item.setdefault("accent", "accent_purple")
            row = idx // external_cols
            col = idx % external_cols
            item_x = row_x0 + col * (item_w + external_card_gap)
            item_y = item_y0 + row * (item_h + item_gap)
            item_id = str(item["id"])
            external_ids.add(item_id)
            item_positions[item_id] = (item_x, item_y, item_w, item_h)
            parts.append(_matrix_item_svg(item, item_x, item_y, item_w, item_h, style, width))

    domain_order = [str(domain["id"]) for domain in domains if domain.get("id")]

    def source_corridor_x(source_id: str, target_rect: tuple[float, float, float, float]) -> float:
        domain_id = item_domains.get(source_id)
        if not domain_id or domain_id not in domain_positions:
            source_rect = item_positions[source_id]
            return source_rect[0] + source_rect[2] / 2
        dx, _dy, dw, _dh = domain_positions[domain_id]
        domain_idx = domain_order.index(domain_id) if domain_id in domain_order else 0
        candidates: list[float] = []
        if domain_idx < len(domain_order) - 1:
            candidates.append(dx + dw + domain_gap / 2)
        if domain_idx > 0:
            candidates.append(dx - domain_gap / 2)
        if not candidates:
            candidates.append(dx + dw + domain_gap / 2)
        target_center = target_rect[0] + target_rect[2] / 2
        return min(candidates, key=lambda value: abs(value - target_center))

    corridor_use_count: dict[float, int] = {}
    corridor_offsets = [0, -10, 10, -18, 18, -26, 26]
    for rel_idx, rel in enumerate(contract.get("relationships", []) or []):
        if not isinstance(rel, dict):
            continue
        source = str(rel.get("from", ""))
        target = str(rel.get("to", ""))
        if source not in item_positions or target not in item_positions:
            continue
        color = _connector_relation_color(
            style,
            rel,
            default_token="line_primary",
            palette_index=rel_idx,
            use_palette=rel.get("style") == "dashed",
        )
        dash = ' stroke-dasharray="6 5"' if rel.get("style") == "dashed" or rel.get("relation") in {"shared_responsibility", "external"} else ""
        extra_attrs = ""
        if target in external_ids and source in item_domains:
            base_corridor_x = source_corridor_x(source, item_positions[target])
            corridor_key = round(base_corridor_x, 1)
            corridor_idx = corridor_use_count.get(corridor_key, 0)
            corridor_use_count[corridor_key] = corridor_idx + 1
            corridor_x = base_corridor_x + corridor_offsets[corridor_idx % len(corridor_offsets)]
            exit_y = map_y + boundary_h + external_gap_y / 2
            path = _matrix_external_connector_path(item_positions[source], item_positions[target], corridor_x, exit_y)
            extra_attrs = f' data-corridor-x="{round(corridor_x, 2)}"'
        else:
            path = _matrix_connector_path(item_positions[source], item_positions[target])
        parts.append(f'<path d="{path}" class="edge boundary-matrix-link" marker-end="url(#arrow)" style="stroke:{color};opacity:0.86"{dash} data-from="{e(source)}" data-to="{e(target)}"{extra_attrs}/>')

    key_w = min(430, (width - 2 * margin_x) * 0.34)
    table_gap = 22
    table_x = margin_x + key_w + table_gap
    table_w = width - 2 * margin_x - key_w - table_gap
    parts.append(_panel_rect_svg(style, margin_x, table_y, key_w, bottom_h, fill="panel_fill", stroke=line, stroke_opacity=0.58, radius=6))
    parts.append(f'<text x="{margin_x + 18}" y="{table_y + 26}" class="table-header">OWNERSHIP KEY (RACI)</text>')
    key_y = table_y + 56
    for idx, item in enumerate(ownership_key[:5]):
        y = key_y + idx * 25
        code = str(item.get("code", ""))
        label = str(item.get("label", ""))
        desc = str(item.get("description", ""))
        parts.append(f'<text x="{margin_x + 22}" y="{y}" class="table-cell" style="font-size:16px;font-weight:700">{e(code)}</text>')
        parts.append(f'<text x="{margin_x + 55}" y="{y}" class="table-cell-secondary" style="font-size:16px">{e(label)}{e(" - " + desc if desc else "")}</text>')

    _render_compact_table(
        parts,
        style,
        "OWNERSHIP ASSIGNMENTS",
        assignment_columns,
        assignment_rows,
        table_x,
        table_y,
        table_w,
        width,
    )
    _append_annotations(parts, contract, style, width, height)
    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def _capability_header_icon_svg(kind: str, x: float, y: float, color: str, style: dict, class_name: str) -> str:
    icon_kind = kind or "index"
    return (
        f'<g class="{class_name} capability-header-icon" data-kind="{e(icon_kind)}">'
        f'<rect x="{x}" y="{y}" width="30" height="30" rx="6" fill="{pale_for(style, color)}" '
        f'stroke="{color}" stroke-width="1.2" stroke-opacity="0.95"/>'
        f'{icon_svg(icon_kind, x + 5, y + 5, color, style)}'
        f'</g>'
    )


def _capability_item_svg(item: dict, x: float, y: float, w: float, h: float, style: dict, canvas_w: float) -> str:
    kind = str(item.get("kind", "capability"))
    color = _accent_color(style, item, "capability")
    card = _style_component(style, "card")
    fill = card.get("fill", "card_fill")
    radius = min(float(card.get("radius", 8)), 6)
    title_size = _clamp(16.5 * _clamp(canvas_w / 1500.0, 0.95, 1.08), 16.5, 18.2)
    sub_size = _clamp(13.2 * _clamp(canvas_w / 1500.0, 0.95, 1.08), 13.0, 14.5)
    text_primary = style_color(style, "text_primary", "#F4F8FF")
    text_secondary = style_color(style, "text_secondary", "#C9DAF5")
    text_x = x + 16
    text_w = max(80, w - 30)
    title_lines = wrap_text(str(item.get("label", item.get("id", "Capability"))), max_chars=max(8, int(text_w / (title_size * 0.55))), max_lines=2)
    sub_lines = wrap_text(str(item.get("subtitle", "")), max_chars=max(10, int(text_w / (sub_size * 0.52))), max_lines=1) if item.get("subtitle") else []
    title_line_h = title_size + 2
    sub_gap = 4
    block_h = len(title_lines) * title_line_h + (sub_gap + sub_size if sub_lines else 0)
    text_y = y + (h - block_h) / 2 + title_size
    parts = [f'<g id="capability-item-{e(item.get("id", ""))}" class="capability-map-item card" data-kind="{e(kind)}">']
    parts.append(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" '
        f'{_paint_attr(style, "fill", fill, "#FFFFFF", card.get("fill_opacity"))} '
        f'stroke="{color}" stroke-width="1.2"/>'
    )
    for idx, line in enumerate(title_lines):
        parts.append(
            f'<text x="{text_x}" y="{text_y + idx * title_line_h}" class="capability-title" '
            f'style="font-size:{_fmt_px(title_size)};font-weight:700;fill:{text_primary}">{e(line)}</text>'
        )
    if sub_lines:
        parts.append(
            f'<text x="{text_x}" y="{text_y + len(title_lines) * title_line_h + sub_gap}" class="capability-sub" '
            f'style="font-size:{_fmt_px(sub_size)};font-weight:500;fill:{text_secondary}">{e(sub_lines[0])}</text>'
        )
    parts.append('</g>')
    return "".join(parts)


def _vertical_segment_blocked(
    x: float,
    y1: float,
    y2: float,
    obstacles: list[tuple[float, float, float, float]],
) -> bool:
    low = min(y1, y2)
    high = max(y1, y2)
    for ox, oy, ow, oh in obstacles:
        if ox + 2 < x < ox + ow - 2 and max(low, oy + 2) < min(high, oy + oh - 2):
            return True
    return False


def _capability_corridor_base_x(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
    obstacles: list[tuple[float, float, float, float]],
    sy: float,
    ty: float,
    corridor_offset: float,
) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    left_x = min(ax, bx) - corridor_offset
    right_x = max(ax + aw, bx + bw) + corridor_offset

    def corridor_score(x: float) -> int:
        low = min(sy, ty)
        high = max(sy, ty)
        score = 0
        for ox, oy, ow, oh in obstacles:
            if ox - 8 < x < ox + ow + 8 and max(low, oy - 8) < min(high, oy + oh + 8):
                score += 1
        return score

    return left_x if corridor_score(left_x) <= corridor_score(right_x) else right_x


def _capability_detour_corridor_key(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
    obstacles: list[tuple[float, float, float, float]],
    corridor_offset: float,
) -> float | None:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    acx = ax + aw / 2
    bcx = bx + bw / 2
    if ay + ah <= by:
        sx, sy = acx, ay + ah
        tx, ty = bcx, by
    elif by + bh <= ay:
        sx, sy = acx, ay
        tx, ty = bcx, by + bh
    else:
        return None
    if abs(sx - tx) < EPS:
        needs_detour = _vertical_segment_blocked(sx, sy, ty, obstacles)
    else:
        lane_y = (sy + ty) / 2
        needs_detour = _vertical_segment_blocked(sx, sy, lane_y, obstacles) or _vertical_segment_blocked(tx, lane_y, ty, obstacles)
    if not needs_detour:
        return None
    return round(_capability_corridor_base_x(a, b, obstacles, sy, ty, corridor_offset), 2)


def _capability_lane_shift(index: int, corridor_offset: float, lane_gap: float = 12.0) -> float:
    offsets = [0.0, -1.0, 1.0, -2.0, 2.0, -3.0, 3.0]
    raw = offsets[index % len(offsets)] * lane_gap
    limit = max(lane_gap, corridor_offset - 6.0)
    return max(-limit, min(limit, raw))


def _capability_route_band_key(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float | None:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    if ay + ah <= by:
        return round((ay + ah + by) / 2, 1)
    if by + bh <= ay:
        return round((by + bh + ay) / 2, 1)
    return None


def _shifted_lane(base: float, low: float, high: float, shift: float) -> float:
    if low > high:
        return base
    return _clamp(base + shift, low, high)


def _detour_clearance(stub: float, lane_shift: float, gap: float, max_extra: float) -> float:
    endpoint_extra = min(abs(lane_shift), max_extra)
    return min(stub + endpoint_extra, max(stub, gap / 2 - 2.0))


def _direct_lane_y(sy: float, ty: float, lane_shift: float) -> float:
    low = min(sy, ty) + 8.0
    high = max(sy, ty) - 8.0
    base = (sy + ty) / 2
    return _shifted_lane(base, low, high, lane_shift)


def _capability_level_label_width(contract: dict, levels: list[dict]) -> float:
    if contract.get("level_label_width") is not None:
        return float(contract["level_label_width"])
    labels = [str(level.get("label", level.get("id", ""))) for level in levels]
    tokens = [token for label in labels for token in re.split(r"\s+", label.strip()) if token]
    longest_token = max((len(token) for token in tokens), default=9)
    text_w = longest_token * 15.5 * 0.56
    min_w = float(contract.get("level_label_min_width", 148))
    max_w = float(contract.get("level_label_max_width", 240))
    return _clamp(text_w + 84, min_w, max_w)


def _capability_link_path(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
    obstacles: list[tuple[float, float, float, float]] | None = None,
    corridor_offset: float = 20.0,
    lane_shift: float = 0.0,
) -> str:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    obstacles = obstacles or []
    acx, acy = ax + aw / 2, ay + ah / 2
    bcx, bcy = bx + bw / 2, by + bh / 2

    def detour_path(sx: float, sy: float, tx: float, ty: float) -> str:
        direction = 1 if ty >= sy else -1
        stub = 8.0
        gap = abs(ty - sy)
        source_clearance = _detour_clearance(stub, lane_shift, gap, 34.0)
        target_clearance = _detour_clearance(stub, lane_shift, gap, 14.0)
        low = min(sy, ty) + stub
        high = max(sy, ty) - stub
        corridor_x = _capability_corridor_base_x(a, b, obstacles, sy, ty, corridor_offset) + lane_shift
        source_lane_y = _clamp(sy + direction * source_clearance, low, high)
        target_lane_y = _clamp(ty - direction * target_clearance, low, high)
        return _rounded_path(
            [
                (sx, sy),
                (sx, source_lane_y),
                (corridor_x, source_lane_y),
                (corridor_x, target_lane_y),
                (tx, target_lane_y),
                (tx, ty),
            ],
            radius=10,
        )

    if ay + ah <= by:
        sx, sy = acx, ay + ah
        tx, ty = bcx, by
        if abs(sx - tx) < EPS:
            if _vertical_segment_blocked(sx, sy, ty, obstacles):
                return detour_path(sx, sy, tx, ty)
            return _rounded_path([(sx, sy), (tx, ty)])
        lane_y = _direct_lane_y(sy, ty, lane_shift)
        if _vertical_segment_blocked(sx, sy, lane_y, obstacles) or _vertical_segment_blocked(tx, lane_y, ty, obstacles):
            return detour_path(sx, sy, tx, ty)
        return _rounded_path([(sx, sy), (sx, lane_y), (tx, lane_y), (tx, ty)])
    if by + bh <= ay:
        sx, sy = acx, ay
        tx, ty = bcx, by + bh
        if abs(sx - tx) < EPS:
            if _vertical_segment_blocked(sx, sy, ty, obstacles):
                return detour_path(sx, sy, tx, ty)
            return _rounded_path([(sx, sy), (tx, ty)])
        lane_y = _direct_lane_y(sy, ty, lane_shift)
        if _vertical_segment_blocked(sx, sy, lane_y, obstacles) or _vertical_segment_blocked(tx, lane_y, ty, obstacles):
            return detour_path(sx, sy, tx, ty)
        return _rounded_path([(sx, sy), (sx, lane_y), (tx, lane_y), (tx, ty)])
    if acx <= bcx:
        return _rounded_path([(ax + aw, acy), (bx, bcy)])
    return _rounded_path([(ax, acy), (bx + bw, bcy)])


def _render_capability_domain_map(contract: dict, style: dict, diagram_type: str) -> str:
    metrics = layout_metrics(style)
    levels = [level for level in contract.get("levels", []) if isinstance(level, dict)]
    columns = [column for column in contract.get("columns", []) if isinstance(column, dict)]
    items = [item for item in contract.get("items", []) if isinstance(item, dict)]
    panels = _info_panels(contract)
    margin_x = int(contract.get("canvas_margin_x", metrics["canvas_margin_x"]))
    top_y = int(contract.get("top_y", metrics["top_y"]))
    level_label_w = _capability_level_label_width(contract, levels)
    col_gap = max(float(contract.get("column_gap", 44)), 44.0)
    row_gap = max(float(contract.get("level_gap", 36)), 36.0)
    item_h = max(float(contract.get("item_height", 96)), 96.0)
    item_gap = max(float(contract.get("item_gap", 28)), 28.0)
    default_col_w = max(float(contract.get("column_width", 205)), 200.0)
    header_h = 56.0
    label_gap = max(float(contract.get("label_gap", 44)), 44.0)
    col_widths = [float(column.get("width", default_col_w)) for column in columns]
    grid_w = sum(col_widths) + max(0, len(columns) - 1) * col_gap
    map_w = level_label_w + label_gap + grid_w
    natural_w = 2 * margin_x + map_w
    width = int(max(float(contract.get("width", 0)), natural_w))
    content_x = (width - map_w) / 2
    map_x = content_x
    grid_x = map_x + level_label_w + label_gap

    column_x: dict[str, float] = {}
    cur_x = grid_x
    for idx, column in enumerate(columns):
        column_x[str(column["id"])] = cur_x
        cur_x += col_widths[idx] + col_gap
    column_index = {str(column["id"]): idx for idx, column in enumerate(columns)}

    grouped: dict[tuple[str, str], list[dict]] = {}
    for item in items:
        grouped.setdefault((str(item.get("level")), str(item.get("column"))), []).append(item)
    order_index = {id(item): idx for idx, item in enumerate(items)}
    for stack in grouped.values():
        stack.sort(key=lambda item: (item.get("order", order_index[id(item)]), order_index[id(item)]))

    level_heights: dict[str, float] = {}
    for level in levels:
        level_id = str(level["id"])
        max_stack = max((len(stack) for (stack_level, _col), stack in grouped.items() if stack_level == level_id), default=1)
        level_heights[level_id] = max(float(level.get("height", 0) or 0), max(86.0, max_stack * item_h + max(0, max_stack - 1) * item_gap + 24))

    map_y = top_y + header_h + 18
    map_h = sum(level_heights[str(level["id"])] for level in levels) + max(0, len(levels) - 1) * row_gap
    panel_y = map_y + map_h + 36
    _panel_layouts, panels_h = _info_panel_layouts(panels, margin_x, panel_y, width - 2 * margin_x, width)
    height = int(max(float(contract.get("height", 0)), panel_y + panels_h + 64 if panels else map_y + map_h + 76))

    parts = _svg_shell_start(contract, style, width, height, diagram_type)
    line = style_color(style, "line_primary", "#F4F8FF")
    secondary = style_color(style, "text_secondary", "#C9DAF5")
    level_label_size = _clamp(14.5 * _clamp(width / 1500.0, 0.95, 1.08), 14.5, 16.0)
    col_label_size = _clamp(14.5 * _clamp(width / 1500.0, 0.95, 1.08), 14.5, 16.0)

    parts.append(_panel_rect_svg(style, map_x, top_y, map_w, header_h, fill="panel_fill", stroke=line, stroke_opacity=0.52, radius=6))
    for idx, column in enumerate(columns):
        cx = column_x[str(column["id"])]
        cw = col_widths[idx]
        color = _accent_color(style, column, "capability")
        icon_kind = str(column.get("kind", "index"))
        parts.append(f'<rect x="{cx}" y="{top_y + 9}" width="{cw}" height="{header_h - 18}" rx="5" fill="none" stroke="{color}" stroke-opacity="0.7" stroke-width="1"/>')
        parts.append(_capability_header_icon_svg(icon_kind, cx + 12, top_y + 13, color, style, "capability-column-icon"))
        label_lines = _wrap_text_to_width(
            str(column.get("label", column.get("id"))),
            max(70.0, cw - 64.0),
            col_label_size,
            max_lines=2,
            min_chars=7,
            char_factor=0.55,
        )
        label_line_h = col_label_size + 2
        label_y = top_y + 35
        if len(label_lines) > 1:
            label_y -= (len(label_lines) - 1) * label_line_h / 2
        for line_idx, line_text in enumerate(label_lines):
            text_y = label_y if line_idx == 0 else label_y + line_idx * label_line_h
            parts.append(
                f'<text x="{cx + 52}" y="{text_y}" text-anchor="start" class="capability-column-label" '
                f'style="font-size:{_fmt_px(col_label_size)};font-weight:700;fill:{line}">{e(line_text)}</text>'
            )

    positions: dict[str, tuple[float, float, float, float]] = {}
    level_y: dict[str, float] = {}
    items_by_id = {str(item["id"]): item for item in items if item.get("id")}
    y = map_y
    for level in levels:
        level_id = str(level["id"])
        row_h = level_heights[level_id]
        level_y[level_id] = y
        color = _accent_color(style, level, "capability")
        icon_kind = str(level.get("kind", "capability"))
        parts.append(_panel_rect_svg(style, map_x, y, map_w, row_h, fill="panel_fill", stroke=line, stroke_opacity=0.22, radius=6))
        parts.append(f'<rect x="{map_x}" y="{y}" width="{level_label_w}" height="{row_h}" rx="5" fill="none" stroke="{color}" stroke-width="1.2" stroke-opacity="0.95"/>')
        parts.append(_capability_header_icon_svg(icon_kind, map_x + 16, y + row_h / 2 - 15, color, style, "capability-level-icon"))
        label_x = map_x + 58
        label_w = max(70, level_label_w - 72)
        label_lines = wrap_text(str(level.get("label", level_id)), max_chars=max(8, int(label_w / (level_label_size * 0.55))), max_lines=2)
        start_y = y + row_h / 2 - (len(label_lines) - 1) * (level_label_size + 2) / 2 + level_label_size / 3
        for idx, line_text in enumerate(label_lines):
            parts.append(
                f'<text x="{label_x}" y="{start_y + idx * (level_label_size + 2)}" '
                f'text-anchor="start" class="capability-level-label" style="font-size:{_fmt_px(level_label_size)};font-weight:700;fill:{color}">{e(line_text)}</text>'
            )
        for (stack_level, col_id), stack in grouped.items():
            if stack_level != level_id:
                continue
            if col_id not in column_x:
                continue
            col_idx = column_index[col_id]
            span = 1
            for stack_idx, item in enumerate(stack):
                span = max(1, int(item.get("span", 1)))
                item_x = column_x[col_id]
                item_w = sum(col_widths[col_idx:min(len(col_widths), col_idx + span)]) + max(0, min(span, len(col_widths) - col_idx) - 1) * col_gap
                stack_h = len(stack) * item_h + max(0, len(stack) - 1) * item_gap
                item_y = y + (row_h - stack_h) / 2 + stack_idx * (item_h + item_gap)
                positions[str(item["id"])] = (item_x, item_y, item_w, item_h)
        y += row_h + row_gap

    corridor_offset = col_gap / 2
    relationship_lane_gap = float(contract.get("relationship_lane_gap", 14.0))
    route_counts: dict[tuple[str, float], int] = {}
    for rel_idx, rel in enumerate(contract.get("relationships", []) or []):
        if not isinstance(rel, dict):
            continue
        source = str(rel.get("from", ""))
        target = str(rel.get("to", ""))
        if source not in positions or target not in positions:
            continue
        color = _connector_relation_color(
            style,
            rel,
            default_token="line_primary",
            source_item=items_by_id.get(source),
            prefer_source=rel.get("relation") in {"supports", "enables", "dependency"},
            palette_index=rel_idx,
            use_palette=rel.get("style") in {"dashed", "secondary"} or rel.get("relation") in {"supports", "shared"},
        )
        dash = ' stroke-dasharray="6 5"' if rel.get("style") in {"dashed", "secondary"} or rel.get("relation") in {"supports", "shared"} else ""
        obstacles = [rect for item_id, rect in positions.items() if item_id not in {source, target}]
        corridor_key = _capability_detour_corridor_key(positions[source], positions[target], obstacles, corridor_offset)
        band_key = _capability_route_band_key(positions[source], positions[target])
        route_key = ("corridor", corridor_key) if corridor_key is not None else ("band", band_key or 0.0)
        route_index = route_counts.get(route_key, 0)
        route_counts[route_key] = route_index + 1
        lane_shift = _capability_lane_shift(route_index, corridor_offset, relationship_lane_gap) if band_key is not None else 0.0
        lane_shift += float(rel.get("lane_offset", 0.0))
        path = _capability_link_path(positions[source], positions[target], obstacles, corridor_offset, lane_shift)
        corridor_attr = f' data-corridor-x="{round(corridor_key, 1):g}"' if corridor_key is not None else ""
        parts.append(f'<path d="{path}" class="edge capability-map-link" marker-end="url(#arrow)" style="stroke:{color};opacity:0.86"{dash} data-from="{e(source)}" data-to="{e(target)}" data-relation="{e(rel.get("relation", ""))}" data-lane-shift="{round(lane_shift, 1):g}"{corridor_attr}/>')

    for item_id in sorted(positions, key=lambda iid: (positions[iid][1], positions[iid][0])):
        item = next(item for item in items if str(item.get("id")) == item_id)
        parts.append(_capability_item_svg(item, *positions[item_id], style, width))

    if panels:
        _render_info_panels(parts, panels, style, margin_x, panel_y, width - 2 * margin_x, width)
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


def _render_tree_family_backbone(
    contract: dict,
    style: dict,
    diagram_type: str,
    node_by_id: dict[str, dict],
    parent_map: dict[str, str],
    children: dict[str, list[str]],
    roots: list[str],
) -> str:
    metrics = layout_metrics(style)
    margin_x = int(contract.get("canvas_margin_x", metrics["canvas_margin_x"]))
    top_y = int(contract.get("top_y", metrics["top_y"]))
    card_w = float(contract.get("card_width", 230))
    card_h = float(contract.get("card_height", metrics["card_h"]))
    family_gap = max(float(contract.get("family_gap", contract.get("tree_col_gap", metrics["card_col_gap"]))), 72.0)
    root_gap = max(float(contract.get("root_gap", 118)), 96.0)
    backbone_start_gap = max(float(contract.get("backbone_start_gap", 70)), 54.0)
    backbone_node_gap = max(float(contract.get("backbone_node_gap", contract.get("tree_row_gap", 34))), 28.0)
    backbone_nested_gap = max(float(contract.get("backbone_nested_gap", 22)), 18.0)
    backbone_block_gap = max(float(contract.get("backbone_block_gap", backbone_node_gap)), 28.0)
    depth_indent = max(float(contract.get("backbone_depth_indent", 56)), 36.0)
    backbone_offset = max(float(contract.get("backbone_offset", 30)), 22.0)

    order = {
        str(n["id"]): i
        for i, n in enumerate(contract.get("nodes", []))
        if isinstance(n, dict) and n.get("id")
    }
    sorted_roots = sorted(roots, key=lambda node_id: (node_by_id[node_id].get("order", order.get(node_id, 0)), order.get(node_id, 0)))
    depths: dict[str, int] = {}

    def assign_depth(node_id: str, depth: int) -> None:
        depths[node_id] = depth
        for child_id in children[node_id]:
            assign_depth(child_id, depth + 1)

    for root in sorted_roots:
        assign_depth(root, 0)

    family_roots: list[str] = []
    for root in sorted_roots:
        if children[root]:
            family_roots.extend(children[root])
        else:
            family_roots.append(root)
    if not family_roots:
        family_roots = sorted_roots

    def descendants(node_id: str) -> list[str]:
        items: list[str] = []
        for child_id in children[node_id]:
            items.append(child_id)
            items.extend(descendants(child_id))
        return items

    family_descendants = {family_id: descendants(family_id) for family_id in family_roots}
    family_max_depth = {
        family_id: max((depths[node_id] for node_id in [family_id] + family_descendants[family_id]), default=1)
        for family_id in family_roots
    }
    family_lane_width = {
        family_id: card_w + max(0, family_max_depth[family_id] - 2) * depth_indent
        for family_id in family_roots
    }
    family_count = max(1, len(family_roots))
    family_band_w = sum(family_lane_width.values()) + max(0, family_count - 1) * family_gap
    min_width = int(2 * margin_x + family_band_w)
    width = int(max(contract.get("width", 1500), min_width))
    family_x0 = (width - family_band_w) / 2
    root_y = float(top_y)
    level1_y = root_y + card_h + root_gap
    desc_y0 = level1_y + card_h + backbone_start_gap

    positions: dict[str, tuple[float, float, float, float]] = {}
    if sorted_roots:
        root_count = len(sorted_roots)
        root_gap_x = max(family_gap, 72.0)
        root_band_w = root_count * card_w + max(0, root_count - 1) * root_gap_x
        root_x0 = (width - root_band_w) / 2
        for idx, root in enumerate(sorted_roots):
            positions[root] = (root_x0 + idx * (card_w + root_gap_x), root_y, card_w, card_h)

    family_base_x: dict[str, float] = {}
    cursor_x = family_x0
    for family_id in family_roots:
        family_base_x[family_id] = cursor_x
        cursor_x += family_lane_width[family_id] + family_gap

    def place_subtree(family_id: str, node_id: str, y: float) -> float:
        x = family_base_x[family_id] + max(0, depths[node_id] - 2) * depth_indent
        positions[node_id] = (x, y, card_w, card_h)
        subtree_bottom = y + card_h
        child_y = y + card_h + backbone_nested_gap
        for child_id in children[node_id]:
            child_bottom = place_subtree(family_id, child_id, child_y)
            subtree_bottom = max(subtree_bottom, child_bottom)
            child_y = child_bottom + backbone_nested_gap
        return subtree_bottom

    for family_id in family_roots:
        x = family_base_x[family_id] + max(0.0, family_lane_width[family_id] - card_w) / 2
        if family_id not in positions or parent_map.get(family_id):
            positions[family_id] = (x, level1_y, card_w, card_h)
        subtree_y = desc_y0
        for child_id in children[family_id]:
            subtree_bottom = place_subtree(family_id, child_id, subtree_y)
            subtree_y = subtree_bottom + backbone_block_gap

    content_bottom = max((y + h for _x, y, _w, h in positions.values()), default=top_y + card_h)
    height = int(max(contract.get("height", 0), content_bottom + 110))

    family_by_node: dict[str, str] = {}
    for family_id, node_ids in family_descendants.items():
        family_by_node[family_id] = family_id
        for node_id in node_ids:
            family_by_node[node_id] = family_id

    family_palette = [
        style_color(style, "accent_cyan", "#16D9FF"),
        style_color(style, "accent_yellow", "#FFD84D"),
        style_color(style, "accent_green", "#6EE66E"),
        style_color(style, "accent_purple", "#B56CFF"),
        style_color(style, "accent_orange", "#FF9F2E"),
    ]
    family_rank = {family_id: idx for idx, family_id in enumerate(family_roots)}
    family_backbone_x = {
        family_id: family_base_x[family_id] - backbone_offset
        for family_id in family_roots
        if family_id in positions
    }

    def color_for_family(family_id: str) -> str:
        explicit = node_by_id[family_id].get("accent") if family_id in node_by_id else None
        if isinstance(explicit, str) and VALID_HEX.match(explicit):
            return explicit
        return family_palette[family_rank.get(family_id, 0) % len(family_palette)]

    def route_for(parent_id: str, child_id: str) -> tuple[str, dict[str, float]]:
        parent_rect = positions[parent_id]
        child_rect = positions[child_id]
        child_family = family_by_node.get(child_id, child_id)
        parent_depth = depths.get(parent_id, 0)
        child_depth = depths.get(child_id, 0)
        sx, sy = center_bottom(parent_rect)
        tx, ty = center_top(child_rect)
        if parent_id in sorted_roots and child_id in family_roots:
            lane_y = (sy + ty) / 2
            if abs(sx - tx) < 1e-6:
                return _rounded_path([(sx, sy), (tx, ty)]), {"lane_y": lane_y, "link_tier": 0}
            return _rounded_path([(sx, sy), (sx, lane_y), (tx, lane_y), (tx, ty)]), {"lane_y": lane_y, "link_tier": 0}

        backbone_x = family_backbone_x.get(child_family, child_rect[0] - backbone_offset)
        child_x, child_y, _child_w, child_h = child_rect
        child_cy = child_y + child_h / 2
        parent_x, parent_y, parent_w, parent_h = parent_rect
        if parent_id == child_family or (parent_depth <= 1 and child_depth == 2):
            branch_y = parent_y + parent_h + min(24.0, backbone_start_gap / 2)
            route = _rounded_path([
                (parent_x + parent_w / 2, parent_y + parent_h),
                (parent_x + parent_w / 2, branch_y),
                (backbone_x, branch_y),
                (backbone_x, child_cy),
                (child_x, child_cy),
            ])
            return route, {"backbone_x": backbone_x, "branch_y": branch_y, "link_tier": 1}

        parent_cx, parent_bottom = center_bottom(parent_rect)
        nested_x = child_x - max(14.0, backbone_offset / 2)
        branch_y = (parent_bottom + child_y) / 2
        route = _rounded_path([
            (parent_cx, parent_bottom),
            (parent_cx, branch_y),
            (nested_x, branch_y),
            (nested_x, child_cy),
            (child_x, child_cy),
        ])
        return route, {"nested_x": nested_x, "branch_y": branch_y, "link_tier": 2}

    parts = _svg_shell_start(contract, style, width, height, diagram_type)
    for child_id, parent_id in parent_map.items():
        if parent_id not in positions or child_id not in positions:
            continue
        family_id = family_by_node.get(child_id, child_id)
        color = color_for_family(family_id)
        route, route_meta = route_for(parent_id, child_id)
        link_tier = int(route_meta.pop("link_tier", 1))
        link_tier_name = "root_family" if link_tier == 0 else "family_backbone" if link_tier == 1 else "nested_branch"
        meta_attrs = " ".join(
            f'data-{key.replace("_", "-")}="{round(value, 2)}"'
            for key, value in route_meta.items()
        )
        link_classes = "edge taxonomy-link taxonomy-backbone-link"
        if link_tier == 2:
            link_classes += " taxonomy-nested-link"
        parts.append(_path(
            route,
            link_classes,
            "arrow",
            f'data-layout="family_backbone" data-link-tier="{link_tier_name}" data-family="{e(family_id)}" data-parent="{e(parent_id)}" data-child="{e(child_id)}" data-depth="{depths.get(child_id, 0)}" {meta_attrs} style="stroke:{color};opacity:0.92"',
        ))

    for node_id in sorted(positions, key=lambda nid: (positions[nid][1], positions[nid][0], order.get(nid, 0))):
        parts.append(make_card(node_by_id[node_id], *positions[node_id], style, width))
    if sorted_roots:
        label_x = max(24.0, min(float(margin_x), min(family_backbone_x.values(), default=float(margin_x)) - 112.0))
        parts.append(f'<text x="{label_x}" y="{root_y - 14}" class="tree-level-label">Level 0</text>')
    if family_roots and any(parent_map.get(family_id) for family_id in family_roots):
        parts.append(f'<text x="{label_x}" y="{level1_y - 14}" class="tree-level-label">Level 1</text>')
    if any(family_descendants.values()):
        parts.append(f'<text x="{label_x}" y="{desc_y0 - 14}" class="tree-level-label">Level 2+</text>')
    _append_annotations(parts, contract, style, width, height)
    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def _render_tree(contract: dict, style: dict, diagram_type: str) -> str:
    node_by_id, parent_map, children, roots = _tree_maps(contract)
    if not node_by_id:
        raise DiagramTypeError("taxonomy_tree requires nodes")
    tree_layout = contract.get("tree_layout", "level_rows") or "level_rows"
    if tree_layout == "family_backbone":
        return _render_tree_family_backbone(contract, style, diagram_type, node_by_id, parent_map, children, roots)
    metrics = layout_metrics(style)
    margin_x = int(contract.get("canvas_margin_x", metrics["canvas_margin_x"]))
    card_w = float(contract.get("card_width", 230))
    card_h = float(contract.get("card_height", metrics["card_h"]))
    col_gap = float(contract.get("tree_col_gap", contract.get("card_col_gap", metrics["card_col_gap"])))
    row_gap = max(float(contract.get("tree_row_gap", 88)), 72.0)
    level_gap = max(float(contract.get("level_gap", 132)), 108.0)
    max_per_row = max(1, int(contract.get("tree_max_per_row", contract.get("max_nodes_per_row", 6))))
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
    ordered_by_depth: dict[int, list[str]] = {}
    for node_id in node_by_id:
        ordered_by_depth.setdefault(depths[node_id], []).append(node_id)
    for depth_nodes in ordered_by_depth.values():
        depth_nodes.sort(key=lambda node_id: (centers[node_id], node_by_id[node_id].get("order", 0), node_id))

    max_cols = max(1, max(min(max_per_row, len(nodes)) for nodes in ordered_by_depth.values()))
    min_width = int(2 * margin_x + max_cols * card_w + max(0, max_cols - 1) * col_gap)
    width = int(max(contract.get("width", 1500), min_width))
    top_y = int(contract.get("top_y", metrics["top_y"]))
    max_depth = max(depths.values())
    depth_starts: dict[int, float] = {}
    y = float(top_y)
    for depth in range(max_depth + 1):
        depth_starts[depth] = y
        row_count = max(1, math.ceil(len(ordered_by_depth.get(depth, [])) / max_per_row))
        y += row_count * card_h + max(0, row_count - 1) * row_gap
        if depth < max_depth:
            y += level_gap
    height = int(max(contract.get("height", 0), y + 110))

    positions: dict[str, tuple[float, float, float, float]] = {}
    visual_rows: dict[str, tuple[int, int, float]] = {}
    row_rects: dict[tuple[int, int], list[tuple[float, float, float, float]]] = {}
    for depth, depth_nodes in ordered_by_depth.items():
        depth_max_cols = max(1, min(max_per_row, len(depth_nodes)))
        grid_w = depth_max_cols * card_w + max(0, depth_max_cols - 1) * col_gap
        grid_x0 = (width - grid_w) / 2
        for idx, node_id in enumerate(depth_nodes):
            row = idx // max_per_row
            col = idx % max_per_row
            row_nodes = depth_nodes[row * max_per_row:(row + 1) * max_per_row]
            offset_cols = (depth_max_cols - len(row_nodes)) / 2
            x = grid_x0 + (col + offset_cols) * (card_w + col_gap)
            node_y = depth_starts[depth] + row * (card_h + row_gap)
            rect = (x, node_y, card_w, card_h)
            positions[node_id] = rect
            visual_rows[node_id] = (depth, row, x + card_w / 2)
            row_rects.setdefault((depth, row), []).append(rect)

    target_parents_by_row: dict[tuple[int, int], dict[str, list[str]]] = {}
    for child_id, parent_id in parent_map.items():
        depth, row, _cx = visual_rows[child_id]
        if row > 0:
            target_parents_by_row.setdefault((depth, row), {}).setdefault(parent_id, []).append(child_id)

    def corridor_slots_for(depth: int, row: int) -> list[float]:
        blockers: list[tuple[float, float, float, float]] = []
        for earlier_row in range(row):
            blockers.extend(row_rects.get((depth, earlier_row), []))
        if not blockers:
            return [width / 2]
        slots = [margin_x / 2, width - margin_x / 2]
        for earlier_row in range(row):
            ordered = sorted(row_rects.get((depth, earlier_row), []))
            for left, right in zip(ordered, ordered[1:]):
                gap_left = left[0] + left[2]
                gap_right = right[0]
                gap_w = gap_right - gap_left
                if gap_w < 20:
                    continue
                center = (gap_left + gap_right) / 2
                offsets = [0.0]
                if gap_w >= 58:
                    offsets = [-12.0, 12.0, 0.0]
                if gap_w >= 86:
                    offsets = [-24.0, 0.0, 24.0]
                for offset in offsets:
                    candidate = center + offset
                    if gap_left + 10 <= candidate <= gap_right - 10:
                        slots.append(candidate)
        valid = sorted({
            round(candidate, 2) for candidate in slots
            if not any(rx + 2 < candidate < rx + rw - 2 for rx, _ry, rw, _rh in blockers)
        })
        return valid or [margin_x / 2, width - margin_x / 2]

    parent_corridors: dict[tuple[int, int, str], float] = {}
    for row_key, parent_children in target_parents_by_row.items():
        depth, row = row_key
        slots = corridor_slots_for(depth, row)
        used: list[float] = []

        def desired_x(parent_id: str) -> float:
            child_centers = [center_top(positions[child_id])[0] for child_id in parent_children[parent_id]]
            parent_x, _parent_y = center_bottom(positions[parent_id])
            return (sum(child_centers) / len(child_centers) + parent_x) / 2

        for parent_id in sorted(parent_children, key=lambda pid: (desired_x(pid), positions[pid][0], pid)):
            available = [slot for slot in slots if all(abs(slot - existing) >= 16 for existing in used)]
            chosen = min(available or slots, key=lambda slot: abs(slot - desired_x(parent_id)))
            used.append(chosen)
            parent_corridors[(depth, row, parent_id)] = chosen

    def corridor_x_for(parent_id: str, child_id: str, target_x: float) -> float:
        depth, row, _cx = visual_rows[child_id]
        assigned = parent_corridors.get((depth, row, parent_id))
        if assigned is not None:
            return assigned
        slots = corridor_slots_for(depth, row)
        return min(slots, key=lambda candidate: abs(candidate - target_x))

    lane_parents_by_child_depth: dict[int, list[str]] = {}
    for child_id, parent_id in parent_map.items():
        child_depth = visual_rows[child_id][0]
        parents = lane_parents_by_child_depth.setdefault(child_depth, [])
        if parent_id not in parents:
            parents.append(parent_id)
    for parents in lane_parents_by_child_depth.values():
        parents.sort(key=lambda node_id: (positions[node_id][1], positions[node_id][0], node_id))

    family_palette = [
        style_color(style, "accent_cyan", "#16D9FF"),
        style_color(style, "accent_yellow", "#FFD84D"),
        style_color(style, "accent_green", "#6EE66E"),
        style_color(style, "accent_purple", "#B56CFF"),
        style_color(style, "accent_orange", "#FF9F2E"),
    ]

    def parent_rank(parent_id: str, child_depth: int) -> int:
        parents = lane_parents_by_child_depth.get(child_depth, [parent_id])
        return parents.index(parent_id) if parent_id in parents else 0

    def tree_edge_color(parent_id: str, child_depth: int) -> str:
        explicit = node_by_id[parent_id].get("accent")
        if isinstance(explicit, str) and VALID_HEX.match(explicit):
            return explicit
        parents = lane_parents_by_child_depth.get(child_depth, [parent_id])
        if len(parents) > 1:
            return family_palette[parent_rank(parent_id, child_depth) % len(family_palette)]
        color = kind_accent(style, node_by_id[parent_id].get("kind", "object"))
        return color if VALID_HEX.match(color) else style_color(style, "line_primary", "#F4F8FF")

    def parent_lane_y(parent_id: str, child_depth: int, fallback_y: float) -> float:
        parents = lane_parents_by_child_depth.get(child_depth, [parent_id])
        parent_bottom = positions[parent_id][1] + positions[parent_id][3]
        first_row_top = depth_starts[child_depth]
        lane_top = parent_bottom + 22
        lane_bottom = first_row_top - 22
        if lane_bottom <= lane_top:
            return fallback_y
        rank = parent_rank(parent_id, child_depth)
        return lane_top + (rank + 1) * (lane_bottom - lane_top) / (len(parents) + 1)

    def target_row_lane_y(parent_id: str, child_depth: int, child_row: int, fallback_y: float) -> float:
        if child_row <= 0:
            return fallback_y
        parents = sorted(
            target_parents_by_row.get((child_depth, child_row), {}),
            key=lambda node_id: (positions[node_id][0], node_id),
        )
        if not parents:
            return fallback_y
        prev_row_bottom = depth_starts[child_depth] + (child_row - 1) * (card_h + row_gap) + card_h
        row_top = depth_starts[child_depth] + child_row * (card_h + row_gap)
        lane_top = prev_row_bottom + 20
        lane_bottom = row_top - 20
        if lane_bottom <= lane_top:
            return fallback_y
        rank = parents.index(parent_id) if parent_id in parents else 0
        return lane_top + (rank + 1) * (lane_bottom - lane_top) / (len(parents) + 1)

    def tree_edge_route(parent_id: str, child_id: str) -> tuple[str, dict[str, float]]:
        sx, sy = center_bottom(positions[parent_id])
        tx, ty = center_top(positions[child_id])
        child_depth, child_row, _cx = visual_rows[child_id]
        top_lane_y = parent_lane_y(parent_id, child_depth, (sy + ty) / 2)
        if child_row == 0:
            if abs(tx - sx) < 1e-6:
                return _rounded_path([(sx, sy), (tx, ty)]), {"lane_y": top_lane_y}
            return _rounded_path([(sx, sy), (sx, top_lane_y), (tx, top_lane_y), (tx, ty)]), {"lane_y": top_lane_y}
        corridor_x = corridor_x_for(parent_id, child_id, tx)
        prev_row_bottom = depth_starts[child_depth] + (child_row - 1) * (card_h + row_gap) + card_h
        target_corridor_y = target_row_lane_y(parent_id, child_depth, child_row, (prev_row_bottom + ty) / 2)
        return _rounded_path([
            (sx, sy),
            (sx, top_lane_y),
            (corridor_x, top_lane_y),
            (corridor_x, target_corridor_y),
            (tx, target_corridor_y),
            (tx, ty),
        ]), {"lane_y": top_lane_y, "corridor_x": corridor_x, "row_lane_y": target_corridor_y}

    parts = _svg_shell_start(contract, style, width, height, diagram_type)
    for child, parent in parent_map.items():
        child_depth = visual_rows[child][0]
        route, route_meta = tree_edge_route(parent, child)
        color = tree_edge_color(parent, child_depth)
        meta_attrs = " ".join(
            f'data-{key.replace("_", "-")}="{round(value, 2)}"'
            for key, value in route_meta.items()
        )
        parts.append(_path(
            route,
            "edge taxonomy-link",
            "arrow",
            f'data-parent="{e(parent)}" data-child="{e(child)}" {meta_attrs} style="stroke:{color};opacity:0.92"',
        ))
    for node_id in sorted(positions, key=lambda nid: (depths[nid], positions[nid][1], positions[nid][0])):
        parts.append(make_card(node_by_id[node_id], *positions[node_id], style, width))
    for depth in range(max_depth + 1):
        parts.append(f'<text x="{margin_x}" y="{depth_starts[depth] - 14}" class="tree-level-label">Level {depth}</text>')
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
    text_w = max(80, x + w - 8 - text_x)
    title_lines = _wrap_text_to_width(
        str(node.get("label", node.get("id", "Spoke"))),
        text_w,
        title_size,
        max_lines=2,
        min_chars=8,
        char_factor=0.58,
    )
    sub_lines = _wrap_text_to_width(
        str(node.get("subtitle", "")),
        text_w,
        sub_size,
        max_lines=1,
        min_chars=10,
        char_factor=0.54,
    )
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
    sub_lines = _wrap_text_to_width(
        str(node.get("subtitle", "")),
        radius * 1.65,
        sub_size,
        max_lines=2,
        min_chars=16,
        char_factor=0.54,
    )
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
    panels = _info_panels(contract)
    panel_y = content_bottom + 28
    panel_x = margin_x
    panel_w = width - 2 * margin_x
    _panel_layouts, panels_h = _info_panel_layouts(panels, panel_x, panel_y, panel_w, width)
    min_height = int(panel_y + panels_h + 64 if panels else content_bottom + 92)
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
    _render_info_panels(parts, panels, style, panel_x, panel_y, panel_w, width)
    _append_annotations(parts, contract, style, width, height)
    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def _entity_attributes(entity: dict) -> list[dict]:
    attrs = entity.get("attributes", [])
    if not isinstance(attrs, list):
        return []
    return [attr for attr in attrs if isinstance(attr, dict)]


def _entity_size(entity: dict, default_w: float, header_h: float, row_h: float) -> tuple[float, float]:
    attrs = _entity_attributes(entity)
    width = float(entity.get("width", default_w))
    height = float(entity.get("height", header_h + max(2, len(attrs)) * row_h + 12))
    return width, height


def _relationship_primary_items(contract: dict, diagram_type: str) -> list[dict]:
    key = "concepts" if diagram_type == "ontology_map" else "entities"
    return [item for item in contract.get(key, []) if isinstance(item, dict) and item.get("id")]


def _ontology_instances(contract: dict) -> list[dict]:
    return [item for item in contract.get("instances", []) if isinstance(item, dict) and item.get("id")]


def _relationship_layout_items(contract: dict, diagram_type: str) -> list[dict]:
    if diagram_type == "ontology_map":
        return _relationship_primary_items(contract, diagram_type) + _ontology_instances(contract)
    return _relationship_primary_items(contract, diagram_type)


def _relationship_instance_ids(contract: dict, diagram_type: str) -> set[str]:
    if diagram_type != "ontology_map":
        return set()
    return {str(item["id"]) for item in _ontology_instances(contract)}


def _relationship_default_metrics(contract: dict, diagram_type: str) -> dict[str, float]:
    if diagram_type == "ontology_map":
        return {
            "width": float(contract.get("concept_width", 220)),
            "header_h": float(contract.get("concept_header_height", 40)),
            "row_h": float(contract.get("concept_attribute_row_height", 25)),
            "col_gap": float(contract.get("concept_col_gap", 112)),
            "row_gap": float(contract.get("concept_row_gap", 132)),
            "instance_w": float(contract.get("instance_width", 180)),
            "instance_h": float(contract.get("instance_height", 62)),
        }
    return {
        "width": float(contract.get("entity_width", 220)),
        "header_h": float(contract.get("entity_header_height", 42)),
        "row_h": float(contract.get("attribute_row_height", 26)),
        "col_gap": float(contract.get("entity_col_gap", 110)),
        "row_gap": float(contract.get("entity_row_gap", 120)),
        "instance_w": 0.0,
        "instance_h": 0.0,
    }


def _relationship_item_size(
    item: dict,
    defaults: dict[str, float],
    instance_ids: set[str],
) -> tuple[float, float]:
    if str(item.get("id", "")) in instance_ids:
        width = float(item.get("width", defaults["instance_w"]))
        height = float(item.get("height", defaults["instance_h"]))
        return width, height
    return _entity_size(item, defaults["width"], defaults["header_h"], defaults["row_h"])


def _rect_center(rect: tuple[float, float, float, float]) -> tuple[float, float]:
    x, y, w, h = rect
    return x + w / 2, y + h / 2


def _rect_anchor(rect: tuple[float, float, float, float], target: tuple[float, float]) -> tuple[float, float]:
    return _rect_anchor_with_side(rect, target)[0]


def _rect_anchor_on_side(rect: tuple[float, float, float, float], side: str) -> tuple[float, float]:
    x, y, w, h = rect
    cx, cy = _rect_center(rect)
    if side == "left":
        return x, cy
    if side == "right":
        return x + w, cy
    if side == "top":
        return cx, y
    if side == "bottom":
        return cx, y + h
    return cx, cy


def _rect_edge_anchor_toward(
    rect: tuple[float, float, float, float],
    target: tuple[float, float],
    side: str,
    inset: float = 22.0,
) -> tuple[float, float]:
    x, y, w, h = rect
    tx, ty = target
    if side == "top":
        return _clamp(tx, x + inset, x + w - inset), y
    if side == "bottom":
        return _clamp(tx, x + inset, x + w - inset), y + h
    if side == "left":
        return x, _clamp(ty, y + inset, y + h - inset)
    if side == "right":
        return x + w, _clamp(ty, y + inset, y + h - inset)
    return _rect_center(rect)


def _rect_anchor_with_side(
    rect: tuple[float, float, float, float],
    target: tuple[float, float],
    preferred_side: str | None = None,
) -> tuple[tuple[float, float], str]:
    x, y, w, h = rect
    cx, cy = _rect_center(rect)
    if preferred_side in ANCHOR_SIDES:
        return _rect_anchor_on_side(rect, preferred_side), preferred_side
    dx = target[0] - cx
    dy = target[1] - cy
    if abs(dx) >= abs(dy):
        return ((x + w, cy), "right") if dx >= 0 else ((x, cy), "left")
    return ((cx, y + h), "bottom") if dy >= 0 else ((cx, y), "top")


def _diamond_anchor(cx: float, cy: float, w: float, h: float, target: tuple[float, float]) -> tuple[float, float]:
    return _diamond_anchor_with_side(cx, cy, w, h, target)[0]


def _diamond_anchor_on_side(cx: float, cy: float, w: float, h: float, side: str) -> tuple[float, float]:
    if side == "left":
        return cx - w / 2, cy
    if side == "right":
        return cx + w / 2, cy
    if side == "top":
        return cx, cy - h / 2
    if side == "bottom":
        return cx, cy + h / 2
    return cx, cy


def _diamond_anchor_with_side(
    cx: float,
    cy: float,
    w: float,
    h: float,
    target: tuple[float, float],
    preferred_side: str | None = None,
) -> tuple[tuple[float, float], str]:
    if preferred_side in ANCHOR_SIDES:
        return _diamond_anchor_on_side(cx, cy, w, h, preferred_side), preferred_side
    dx = target[0] - cx
    dy = target[1] - cy
    if abs(dx) < EPS and abs(dy) < EPS:
        return (cx, cy), "center"
    scale_x = (w / 2) / abs(dx) if abs(dx) > EPS else float("inf")
    scale_y = (h / 2) / abs(dy) if abs(dy) > EPS else float("inf")
    scale = min(scale_x, scale_y)
    side = "right" if abs(dx) >= abs(dy) and dx >= 0 else "left" if abs(dx) >= abs(dy) else "bottom" if dy >= 0 else "top"
    return (cx + dx * scale, cy + dy * scale), side


def _rect_overlaps(a: tuple[float, float, float, float], b: tuple[float, float, float, float], pad: float = 0.0) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax - pad < bx + bw and ax + aw + pad > bx and ay - pad < by + bh and ay + ah + pad > by


def _relationship_box(cx: float, cy: float, w: float, h: float) -> tuple[float, float, float, float]:
    return cx - w / 2, cy - h / 2, w, h


def _relationship_overlaps_entity(cx: float, cy: float, w: float, h: float, rects: list[tuple[float, float, float, float]]) -> bool:
    box = _relationship_box(cx, cy, w, h)
    return any(_rect_overlaps(box, rect, 10.0) for rect in rects)


def _slot_axis_value(centers: dict[int, float], coord: float) -> float:
    if not centers:
        return 0.0
    keys = sorted(centers)
    if abs(coord - round(coord)) < EPS and int(round(coord)) in centers:
        return centers[int(round(coord))]
    diffs = [centers[b] - centers[a] for a, b in zip(keys, keys[1:])]
    step = sum(diffs) / len(diffs) if diffs else 260.0
    lower = max((key for key in keys if key <= coord), default=None)
    upper = min((key for key in keys if key >= coord), default=None)
    if lower is not None and upper is not None and lower != upper:
        span = upper - lower
        ratio = (coord - lower) / span
        return centers[lower] + (centers[upper] - centers[lower]) * ratio
    if lower is not None:
        return centers[lower] + (coord - lower) * step
    if upper is not None:
        return centers[upper] - (upper - coord) * step
    return centers[keys[0]]


def _object_relationship_grid(contract: dict, positions: dict[str, tuple[float, float, float, float]], diagram_type: str) -> dict:
    row_values: dict[int, list[float]] = {}
    col_values: dict[int, list[float]] = {}
    for entity in _relationship_primary_items(contract, diagram_type):
        if not isinstance(entity, dict):
            continue
        entity_id = str(entity.get("id", ""))
        if entity_id not in positions:
            continue
        cx, cy = _rect_center(positions[entity_id])
        if isinstance(entity.get("row"), int):
            row_values.setdefault(int(entity["row"]), []).append(cy)
        if isinstance(entity.get("col"), int):
            col_values.setdefault(int(entity["col"]), []).append(cx)
    rows = {row: sum(values) / len(values) for row, values in row_values.items()}
    cols = {col: sum(values) / len(values) for col, values in col_values.items()}
    return {"rows": rows, "cols": cols}


def _orthogonal_link_points(
    start: tuple[float, float],
    end: tuple[float, float],
    start_side: str,
    end_side: str,
) -> list[tuple[float, float]]:
    if abs(start[0] - end[0]) < EPS or abs(start[1] - end[1]) < EPS:
        return [start, end]
    start_horizontal = start_side in {"left", "right"}
    end_horizontal = end_side in {"left", "right"}
    if start_horizontal != end_horizontal and start_side in ANCHOR_SIDES and end_side in ANCHOR_SIDES:
        sx_vec, sy_vec = _side_vector(start_side)
        ex_vec, ey_vec = _side_vector(end_side)
        stub = min(34.0, max(18.0, (abs(start[0] - end[0]) + abs(start[1] - end[1])) / 8))
        start_stub = (start[0] + sx_vec * stub, start[1] + sy_vec * stub)
        end_stub = (end[0] + ex_vec * stub, end[1] + ey_vec * stub)
        corner = (start_stub[0], end_stub[1]) if start_horizontal else (end_stub[0], start_stub[1])
        points = [start, start_stub, corner, end_stub, end]
        cleaned = [points[0]]
        for point in points[1:]:
            if abs(point[0] - cleaned[-1][0]) >= EPS or abs(point[1] - cleaned[-1][1]) >= EPS:
                cleaned.append(point)
        return cleaned
    if start_horizontal and end_horizontal:
        mid_x = (start[0] + end[0]) / 2
        points = [start, (mid_x, start[1]), (mid_x, end[1]), end]
    elif not start_horizontal and not end_horizontal:
        mid_y = (start[1] + end[1]) / 2
        points = [start, (start[0], mid_y), (end[0], mid_y), end]
    elif start_horizontal and not end_horizontal:
        points = [start, (end[0], start[1]), end]
    else:
        points = [start, (start[0], end[1]), end]
    cleaned = [points[0]]
    for point in points[1:]:
        if abs(point[0] - cleaned[-1][0]) >= EPS or abs(point[1] - cleaned[-1][1]) >= EPS:
            cleaned.append(point)
    return cleaned


def _simple_orthogonal_link_points(
    start: tuple[float, float],
    end: tuple[float, float],
    start_side: str,
    end_side: str,
) -> list[tuple[float, float]]:
    if abs(start[0] - end[0]) < EPS or abs(start[1] - end[1]) < EPS:
        return [start, end]
    start_horizontal = start_side in {"left", "right"}
    end_horizontal = end_side in {"left", "right"}
    corner = (start[0], end[1]) if not start_horizontal and end_horizontal else (end[0], start[1])
    return [start, corner, end]


def _side_vector(side: str) -> tuple[float, float]:
    if side == "left":
        return -1.0, 0.0
    if side == "right":
        return 1.0, 0.0
    if side == "top":
        return 0.0, -1.0
    if side == "bottom":
        return 0.0, 1.0
    return 0.0, 0.0


def _label_text_box(x: float, y: float, text: str, size: float, anchor: str) -> tuple[float, float, float, float]:
    width = max(22.0, len(text) * size * 0.62 + 10.0)
    height = size + 8.0
    if anchor == "end":
        bx = x - width
    elif anchor == "middle":
        bx = x - width / 2
    else:
        bx = x
    return bx, y - height / 2, width, height


def _label_overlaps_any(box: tuple[float, float, float, float], boxes: list[tuple[float, float, float, float]], pad: float = 0.0) -> bool:
    return any(_rect_overlaps(box, other, pad) for other in boxes)


def _cardinality_candidates(
    text: str,
    anchor: tuple[float, float],
    side: str,
    rect: tuple[float, float, float, float],
    size: float,
) -> list[tuple[float, float, str, tuple[float, float, float, float]]]:
    x, y, w, h = rect
    ax, ay = anchor
    candidates: list[tuple[float, float, str]] = []
    if side == "right":
        for dy in (-16, 18, -38, 40, -62, 64, -86, 88):
            candidates.append((x + w + 12, ay + dy, "start"))
    elif side == "left":
        for dy in (-16, 18, -38, 40, -62, 64, -86, 88):
            candidates.append((x - 12, ay + dy, "end"))
    elif side == "top":
        for dx, text_anchor in ((14, "start"), (-14, "end"), (38, "start"), (-38, "end"), (64, "start"), (-64, "end"), (0, "middle")):
            candidates.append((ax + dx, y - 20, text_anchor))
    elif side == "bottom":
        for dx, text_anchor in ((14, "start"), (-14, "end"), (38, "start"), (-38, "end"), (64, "start"), (-64, "end"), (0, "middle")):
            candidates.append((ax + dx, y + h + 18, text_anchor))
    else:
        candidates.append((ax + 12, ay - 14, "start"))
    return [(cx, cy, text_anchor, _label_text_box(cx, cy, text, size, text_anchor)) for cx, cy, text_anchor in candidates]


def _render_cardinality_label(
    text: str,
    anchor: tuple[float, float],
    side: str,
    rect: tuple[float, float, float, float],
    size: float,
    style: dict,
    relationship_id: str,
    endpoint: str,
    obstacle_boxes: list[tuple[float, float, float, float]],
    used_boxes: list[tuple[float, float, float, float]],
) -> str:
    candidates = _cardinality_candidates(text, anchor, side, rect, size)
    chosen = candidates[0]
    for candidate in candidates:
        _cx, _cy, _anchor, box = candidate
        if not _label_overlaps_any(box, obstacle_boxes, 3.0) and not _label_overlaps_any(box, used_boxes, 2.0):
            chosen = candidate
            break
    cx, cy, text_anchor, box = chosen
    used_boxes.append(box)
    bx, by, bw, bh = box
    fill = style_color(style, "background_dark", "#031E42")
    stroke = style_color(style, "line_primary", "#F4F8FF")
    text_color = style_color(style, "text_primary", "#F4F8FF")
    return (
        f'<g class="cardinality-label-wrap" data-relationship="{relationship_id}" data-endpoint="{endpoint}">'
        f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="3" fill="{fill}" fill-opacity="0.72" '
        f'stroke="{stroke}" stroke-opacity="0.28" stroke-width="0.7"/>'
        f'<text x="{cx}" y="{cy}" dominant-baseline="middle" text-anchor="{text_anchor}" '
        f'class="note cardinality-label" style="font-size:{_fmt_px(size)};fill:{text_color}">{e(text)}</text>'
        f'</g>'
    )


def _render_object_entity(entity: dict, rect: tuple[float, float, float, float], style: dict, canvas_w: float) -> str:
    x, y, w, h = rect
    kind = str(entity.get("kind", "object"))
    color = _accent_color(style, entity, "object")
    card = _style_component(style, "card")
    fill = card.get("fill", "card_fill")
    header_fill = "panel_fill_strong"
    radius = min(float(card.get("radius", 8)), 7)
    header_h = float(entity.get("header_height", 42))
    row_h = float(entity.get("attribute_row_height", 26))
    title_size = _clamp(18.0 * _clamp(canvas_w / 1500.0, 0.98, 1.08), 18.0, 19.5)
    attr_size = _clamp(13.5 * _clamp(canvas_w / 1500.0, 0.95, 1.08), 13.2, 14.8)
    dash = ' stroke-dasharray="7 5"' if entity.get("weak") else ""
    parts = [f'<g id="entity-{e(entity.get("id", ""))}" class="object-entity-card card" data-kind="{e(kind)}">']
    parts.append(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" '
        f'{_paint_attr(style, "fill", fill, "#FFFFFF", card.get("fill_opacity"))} '
        f'stroke="{color}" stroke-width="1.3"{dash}/>'
    )
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{header_h}" rx="{radius}" {_paint_attr(style, "fill", header_fill, "#FFFFFF", 0.06)}/>')
    title_lines = wrap_text(str(entity.get("label", entity.get("id", "Entity"))), max_chars=max(8, int((w - 28) / (title_size * 0.58))), max_lines=1)
    parts.append(
        f'<text x="{x + w/2}" y="{y + header_h/2 + title_size/3}" text-anchor="middle" class="card-title" '
        f'style="font-size:{_fmt_px(title_size)}">{e(title_lines[0])}</text>'
    )
    parts.append(f'<line x1="{x}" y1="{y + header_h}" x2="{x + w}" y2="{y + header_h}" stroke="{color}" stroke-opacity="0.62" stroke-width="1"/>')
    text_primary = style_color(style, "text_primary", "#0F172A")
    text_secondary = style_color(style, "text_secondary", "#64748B")
    badge_fill = style_color(style, "background_dark", "#031E42")
    attrs = _entity_attributes(entity)
    for idx, attr in enumerate(attrs):
        ay = y + header_h + idx * row_h
        if idx > 0:
            parts.append(f'<line x1="{x}" y1="{ay}" x2="{x + w}" y2="{ay}" stroke="{color}" stroke-opacity="0.25" stroke-width="1"/>')
        role = str(attr.get("role", "attribute")).lower()
        label = "PK" if role == "pk" else "FK" if role == "fk" else ""
        attr_name = str(attr.get("name", "attribute"))
        attr_type = str(attr.get("type", ""))
        tx = x + 16
        if label:
            badge_color = style_color(style, "accent_cyan" if role == "pk" else "accent_purple", color)
            parts.append(f'<rect x="{x + 12}" y="{ay + row_h/2 - 9}" width="30" height="18" rx="4" fill="{badge_fill}" stroke="{badge_color}" stroke-width="1"/>')
            parts.append(f'<text x="{x + 27}" y="{ay + row_h/2 + 5}" text-anchor="middle" class="entity-key-badge" style="font-size:12px;fill:{badge_color};font-weight:700">{label}</text>')
            tx = x + 50
        name_lines = wrap_text(attr_name, max_chars=max(7, int((w - (tx - x) - 16) / (attr_size * 0.52))), max_lines=1)
        parts.append(f'<text x="{tx}" y="{ay + row_h/2 + attr_size/3}" class="entity-attr" style="font-size:{_fmt_px(attr_size)};fill:{text_primary}">{e(name_lines[0])}</text>')
        if attr_type:
            parts.append(f'<text x="{x + w - 14}" y="{ay + row_h/2 + attr_size/3}" text-anchor="end" class="entity-attr-secondary" style="font-size:{_fmt_px(attr_size)};fill:{text_secondary}">{e(attr_type)}</text>')
    parts.append('</g>')
    return "".join(parts)


def _render_ontology_concept(concept: dict, rect: tuple[float, float, float, float], style: dict, canvas_w: float) -> str:
    x, y, w, h = rect
    kind = str(concept.get("kind", "ontology"))
    color = _accent_color(style, concept, "ontology")
    card = _style_component(style, "card")
    fill = card.get("fill", "card_fill")
    header_fill = "panel_fill_strong"
    radius = min(float(card.get("radius", 8)), 7)
    header_h = float(concept.get("header_height", concept.get("concept_header_height", 40)))
    row_h = float(concept.get("attribute_row_height", concept.get("concept_attribute_row_height", 25)))
    title_size = _clamp(18.0 * _clamp(canvas_w / 1500.0, 0.98, 1.08), 18.0, 19.5)
    attr_size = _clamp(13.5 * _clamp(canvas_w / 1500.0, 0.95, 1.08), 13.2, 14.8)
    parts = [f'<g id="concept-{e(concept.get("id", ""))}" class="ontology-concept-card card" data-kind="{e(kind)}">']
    parts.append(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" '
        f'{_paint_attr(style, "fill", fill, "#FFFFFF", card.get("fill_opacity"))} '
        f'stroke="{color}" stroke-width="1.3"/>'
    )
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{header_h}" rx="{radius}" {_paint_attr(style, "fill", header_fill, "#FFFFFF", 0.06)}/>')
    title_lines = wrap_text(str(concept.get("label", concept.get("id", "Concept"))), max_chars=max(8, int((w - 28) / (title_size * 0.58))), max_lines=1)
    parts.append(
        f'<text x="{x + w/2}" y="{y + header_h/2 + title_size/3}" text-anchor="middle" class="card-title ontology-concept-title" '
        f'style="font-size:{_fmt_px(title_size)}">{e(title_lines[0])}</text>'
    )
    parts.append(f'<line x1="{x}" y1="{y + header_h}" x2="{x + w}" y2="{y + header_h}" stroke="{color}" stroke-opacity="0.62" stroke-width="1"/>')
    text_primary = style_color(style, "text_primary", "#0F172A")
    text_secondary = style_color(style, "text_secondary", "#64748B")
    for idx, attr in enumerate(_entity_attributes(concept)):
        ay = y + header_h + idx * row_h
        if idx > 0:
            parts.append(f'<line x1="{x}" y1="{ay}" x2="{x + w}" y2="{ay}" stroke="{color}" stroke-opacity="0.25" stroke-width="1"/>')
        attr_name = str(attr.get("name", "attribute"))
        attr_type = str(attr.get("type", ""))
        name_lines = wrap_text(attr_name, max_chars=max(7, int((w - 30) / (attr_size * 0.52))), max_lines=1)
        parts.append(f'<text x="{x + 16}" y="{ay + row_h/2 + attr_size/3}" class="ontology-attr" style="font-size:{_fmt_px(attr_size)};fill:{text_primary}">{e(name_lines[0])}</text>')
        if attr_type:
            parts.append(f'<text x="{x + w - 14}" y="{ay + row_h/2 + attr_size/3}" text-anchor="end" class="ontology-datatype" style="font-size:{_fmt_px(attr_size)};fill:{text_secondary}">{e(attr_type)}</text>')
    parts.append('</g>')
    return "".join(parts)


def _render_ontology_instance(instance: dict, rect: tuple[float, float, float, float], style: dict, canvas_w: float) -> str:
    x, y, w, h = rect
    color = _accent_color(style, instance, "package")
    card = _style_component(style, "card")
    fill = card.get("fill", "card_fill")
    radius = min(float(card.get("radius", 8)), 7)
    title_size = _clamp(15.5 * _clamp(canvas_w / 1500.0, 0.98, 1.08), 15.5, 16.8)
    sub_size = _clamp(12.8 * _clamp(canvas_w / 1500.0, 0.95, 1.08), 12.5, 13.8)
    text_primary = style_color(style, "text_primary", "#0F172A")
    text_secondary = style_color(style, "text_secondary", "#64748B")
    label = str(instance.get("label", instance.get("id", "Instance")))
    subtitle = str(instance.get("subtitle", instance.get("concept", "")))
    title_lines = wrap_text(label, max_chars=max(8, int((w - 28) / (title_size * 0.55))), max_lines=1)
    sub_lines = wrap_text(subtitle, max_chars=max(8, int((w - 28) / (sub_size * 0.52))), max_lines=1) if subtitle else []
    block_h = title_size + (5 + sub_size if sub_lines else 0)
    block_y = y + (h - block_h) / 2
    parts = [f'<g id="instance-{e(instance.get("id", ""))}" class="ontology-instance-card card" data-concept="{e(instance.get("concept", ""))}">']
    parts.append(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" '
        f'{_paint_attr(style, "fill", fill, "#FFFFFF", card.get("fill_opacity"))} '
        f'stroke="{color}" stroke-width="1.3"/>'
    )
    parts.append(f'<text x="{x + w/2}" y="{block_y + title_size}" text-anchor="middle" class="ontology-instance-title" style="font-size:{_fmt_px(title_size)};font-weight:700;fill:{text_primary}">{e(title_lines[0])}</text>')
    if sub_lines:
        parts.append(f'<text x="{x + w/2}" y="{block_y + title_size + 5 + sub_size}" text-anchor="middle" class="ontology-instance-sub" style="font-size:{_fmt_px(sub_size)};font-weight:500;fill:{text_secondary}">{e(sub_lines[0])}</text>')
    parts.append('</g>')
    return "".join(parts)


def _axis_segment_crosses_rect(a: tuple[float, float], b: tuple[float, float], rect: tuple[float, float, float, float], pad: float = 0.0) -> bool:
    x, y, w, h = rect
    x -= pad
    y -= pad
    w += 2 * pad
    h += 2 * pad
    if abs(a[0] - b[0]) < EPS:
        seg_x = a[0]
        if not (x < seg_x < x + w):
            return False
        return max(min(a[1], b[1]), y) < min(max(a[1], b[1]), y + h)
    if abs(a[1] - b[1]) < EPS:
        seg_y = a[1]
        if not (y < seg_y < y + h):
            return False
        return max(min(a[0], b[0]), x) < min(max(a[0], b[0]), x + w)
    return False


def _points_cross_any_rect(points: list[tuple[float, float]], rects: list[tuple[float, float, float, float]], pad: float = 0.0) -> bool:
    for a, b in zip(points, points[1:]):
        if any(_axis_segment_crosses_rect(a, b, rect, pad) for rect in rects):
            return True
    return False


def _axis_segment_orientation(a: tuple[float, float], b: tuple[float, float]) -> str | None:
    if abs(a[0] - b[0]) < EPS and abs(a[1] - b[1]) >= EPS:
        return "v"
    if abs(a[1] - b[1]) < EPS and abs(a[0] - b[0]) >= EPS:
        return "h"
    return None


def _relationship_natural_anchor_sides(
    source_rect: tuple[float, float, float, float],
    target_rect: tuple[float, float, float, float],
    rel: dict,
) -> tuple[str | None, str | None, str | None, str | None]:
    sx, sy, sw, sh = source_rect
    tx, ty, tw, th = target_rect
    scx, scy = _rect_center(source_rect)
    tcx, tcy = _rect_center(target_rect)
    source_side = rel.get("from_anchor")
    target_side = rel.get("to_anchor")
    source_diamond_side = rel.get("from_diamond_anchor")
    target_diamond_side = rel.get("to_diamond_anchor")
    if source_side or target_side or source_diamond_side or target_diamond_side:
        return source_side, target_side, source_diamond_side, target_diamond_side
    if sx + sw <= tx and abs(scy - tcy) <= max(sh, th) * 0.38:
        return "right", "left", "left", "right"
    if tx + tw <= sx and abs(scy - tcy) <= max(sh, th) * 0.38:
        return "left", "right", "right", "left"
    if sy + sh <= ty and abs(scx - tcx) <= max(sw, tw) * 0.38:
        return "bottom", "top", "top", "bottom"
    if ty + th <= sy and abs(scx - tcx) <= max(sw, tw) * 0.38:
        return "top", "bottom", "bottom", "top"
    return None, None, None, None


def _relationship_link_pair(
    rel: dict,
    source_rect: tuple[float, float, float, float],
    target_rect: tuple[float, float, float, float],
    cx: float,
    cy: float,
    diamond_w: float,
    diamond_h: float,
    avoid_rects: list[tuple[float, float, float, float]],
) -> tuple[list[tuple[float, float]], list[tuple[float, float]], str, str, str, str]:
    source_side_hint, target_side_hint, from_diamond_hint, to_diamond_hint = _relationship_natural_anchor_sides(source_rect, target_rect, rel)
    variants: list[tuple[str | None, str | None, str | None, str | None]] = [
        (source_side_hint, target_side_hint, from_diamond_hint, to_diamond_hint),
    ]
    for source_side, target_side, from_diamond_side, to_diamond_side in (
        ("right", "left", "left", "right"),
        ("left", "right", "right", "left"),
        ("bottom", "top", "top", "bottom"),
        ("top", "bottom", "bottom", "top"),
        (None, None, None, None),
    ):
        variant = (source_side, target_side, from_diamond_side, to_diamond_side)
        if variant not in variants:
            variants.append(variant)

    best: tuple[list[tuple[float, float]], list[tuple[float, float]], str, str, str, str] | None = None
    best_score: tuple[int, int] | None = None
    for source_side, target_side, from_diamond_side, to_diamond_side in variants:
        s_anchor, s_side = _rect_anchor_with_side(source_rect, (cx, cy), source_side)
        t_anchor, t_side = _rect_anchor_with_side(target_rect, (cx, cy), target_side)
        d_from, d_from_side = _diamond_anchor_with_side(cx, cy, diamond_w, diamond_h, s_anchor, from_diamond_side)
        d_to, d_to_side = _diamond_anchor_with_side(cx, cy, diamond_w, diamond_h, t_anchor, to_diamond_side)
        lane_offset = float(rel.get("lane_offset", 0.0))
        link_points = _simple_orthogonal_link_points if rel.get("simple_elbow") is True else _orthogonal_link_points
        source_points = _offset_relationship_lane(link_points(s_anchor, d_from, s_side, d_from_side), lane_offset)
        target_points = _offset_relationship_lane(link_points(d_to, t_anchor, d_to_side, t_side), lane_offset)
        crosses = int(_points_cross_any_rect(source_points, avoid_rects, 8.0)) + int(_points_cross_any_rect(target_points, avoid_rects, 8.0))
        bends = max(0, len(source_points) - 2) + max(0, len(target_points) - 2)
        score = (crosses, bends)
        if best_score is None or score < best_score:
            best_score = score
            best = (source_points, target_points, s_side, t_side, d_from_side, d_to_side)
        if crosses == 0:
            break
    assert best is not None
    return best


def _offset_relationship_lane(points: list[tuple[float, float]], offset: float) -> list[tuple[float, float]]:
    if abs(offset) < EPS or len(points) < 4:
        return points
    best_idx: int | None = None
    best_orient: str | None = None
    best_length = 0.0
    for idx, (a, b) in enumerate(zip(points, points[1:])):
        if idx == 0 or idx + 1 >= len(points) - 1:
            continue
        orient = _axis_segment_orientation(a, b)
        if not orient:
            continue
        length = abs(b[0] - a[0]) if orient == "h" else abs(b[1] - a[1])
        if length > best_length:
            best_idx = idx
            best_orient = orient
            best_length = length
    if best_idx is None or best_orient is None:
        return points
    shifted = list(points)
    a = shifted[best_idx]
    b = shifted[best_idx + 1]
    if best_orient == "h":
        shifted[best_idx] = (a[0], a[1] + offset)
        shifted[best_idx + 1] = (b[0], b[1] + offset)
    else:
        shifted[best_idx] = (a[0] + offset, a[1])
        shifted[best_idx + 1] = (b[0] + offset, b[1])
    return shifted


def _ontology_instance_link_points(
    concept_rect: tuple[float, float, float, float],
    instance_rect: tuple[float, float, float, float],
    obstacles: list[tuple[float, float, float, float]],
    lane_offset: float = 0.0,
    concept_anchor_override: object = None,
    instance_anchor_override: object = None,
) -> list[tuple[float, float]]:
    instance_center = _rect_center(instance_rect)
    if concept_anchor_override:
        concept_anchor, concept_side = _rect_anchor_with_side(concept_rect, instance_center, concept_anchor_override)
    else:
        concept_anchor, concept_side = _rect_edge_anchor_toward(concept_rect, instance_center, "bottom"), "bottom"
    if instance_anchor_override:
        instance_anchor, instance_side = _rect_anchor_with_side(instance_rect, concept_anchor, instance_anchor_override)
    else:
        instance_anchor, instance_side = _rect_edge_anchor_toward(instance_rect, concept_anchor, "top"), "top"
    direct_points = _orthogonal_link_points(concept_anchor, instance_anchor, concept_side, instance_side)
    if not _points_cross_any_rect(direct_points, obstacles, 12.0):
        return direct_points
    cx, _cy = _rect_center(concept_rect)
    ix, _iy = _rect_center(instance_rect)
    xs = [concept_rect[0], instance_rect[0]] + [rect[0] for rect in obstacles]
    rights = [concept_rect[0] + concept_rect[2], instance_rect[0] + instance_rect[2]] + [rect[0] + rect[2] for rect in obstacles]
    corridor_x = min(xs) - 48.0 if ix <= cx else max(rights) + 48.0
    corridor_x += lane_offset
    top_lane_y = concept_anchor[1] + 34.0 + lane_offset
    bottom_lane_y = instance_anchor[1] - 34.0 + lane_offset
    points = [
        concept_anchor,
        (concept_anchor[0], top_lane_y),
        (corridor_x, top_lane_y),
        (corridor_x, bottom_lane_y),
        (instance_anchor[0], bottom_lane_y),
        instance_anchor,
    ]
    return points


def _render_ontology_instance_links(contract: dict, positions: dict[str, tuple[float, float, float, float]], style: dict) -> list[str]:
    paths: list[str] = []
    instances = _ontology_instances(contract)
    lane_step = float(contract.get("ontology_instance_lane_gap", 18.0))
    concept_ids = _unique(str(instance.get("concept", "")) for instance in instances if instance.get("concept"))
    concept_palette_index = {concept_id: idx for idx, concept_id in enumerate(concept_ids)}
    for idx, instance in enumerate(instances):
        instance_id = str(instance.get("id", ""))
        concept_id = str(instance.get("concept", ""))
        if instance_id not in positions or concept_id not in positions:
            continue
        concept_rect = positions[concept_id]
        instance_rect = positions[instance_id]
        obstacles = [rect for item_id, rect in positions.items() if item_id not in {concept_id, instance_id}]
        lane_offset = float(instance.get("lane_offset", (idx - (len(instances) - 1) / 2) * lane_step))
        points = _ontology_instance_link_points(
            concept_rect,
            instance_rect,
            obstacles,
            lane_offset,
            instance.get("concept_anchor"),
            instance.get("instance_anchor"),
        )
        color = _connector_palette_color(style, "ontology_instance_palette", concept_palette_index.get(concept_id, idx))
        if not color:
            color = _accent_color(style, instance, "package")
        paths.append(
            f'<path d="{_rounded_path(points)}" class="edge ontology-instance-link" '
            f'style="stroke:{color};opacity:0.78" stroke-dasharray="6 5" data-route-family="{e(concept_id)}" data-route-color="{color}" data-from="{e(concept_id)}" data-to="{e(instance_id)}"/>'
        )
    return paths


def _object_relationship_layout(contract: dict, style: dict, diagram_type: str) -> tuple[int, int, dict[str, tuple[float, float, float, float]], float, dict]:
    metrics = layout_metrics(style)
    entities = _relationship_layout_items(contract, diagram_type)
    primary_items = _relationship_primary_items(contract, diagram_type)
    instance_ids = _relationship_instance_ids(contract, diagram_type)
    margin_x = int(contract.get("canvas_margin_x", metrics["canvas_margin_x"]))
    top_y = int(contract.get("top_y", metrics["top_y"]))
    defaults = _relationship_default_metrics(contract, diagram_type)
    default_w = defaults["width"]
    col_gap = defaults["col_gap"]
    row_gap = defaults["row_gap"]
    max_diamond_w = max(
        [float(rel.get("diamond_width", 96)) for rel in contract.get("relationships", []) if isinstance(rel, dict)]
        or [96.0]
    )
    col_gap = max(col_gap, float(contract.get("relationship_col_gap_min", max_diamond_w + 48)))
    row_gap = max(row_gap, float(contract.get("relationship_row_gap_min", 132)))
    sizes = {str(entity["id"]): _relationship_item_size(entity, defaults, instance_ids) for entity in entities}
    order_index = {id(entity): idx for idx, entity in enumerate(entities)}
    concept_max_row = max(
        (int(entity.get("row", 0)) for entity in primary_items if str(entity.get("id", "")) not in instance_ids),
        default=0,
    )
    rows: dict[int, list[dict]] = {}
    for idx, entity in enumerate(entities):
        default_row = concept_max_row + 1 if str(entity.get("id", "")) in instance_ids else 0
        row = int(entity.get("row", default_row))
        rows.setdefault(row, []).append(entity)
    for row_entities in rows.values():
        row_entities.sort(key=lambda entity: (entity.get("col", order_index[id(entity)]), order_index[id(entity)]))
    max_row_w = 0.0
    for row_entities in rows.values():
        if any("col" in entity for entity in row_entities):
            max_col = max(int(entity.get("col", 0)) for entity in row_entities)
            row_w = (max_col + 1) * default_w + max_col * col_gap
        else:
            row_w = sum(sizes[str(entity["id"])][0] for entity in row_entities) + max(0, len(row_entities) - 1) * col_gap
        max_row_w = max(max_row_w, row_w)
    width = int(max(contract.get("width", 1500), max_row_w + 2 * margin_x))
    positions: dict[str, tuple[float, float, float, float]] = {}
    y = top_y
    for row in sorted(rows):
        row_entities = rows[row]
        explicit_cols = any("col" in entity for entity in row_entities)
        if explicit_cols:
            max_col = max(int(entity.get("col", 0)) for entity in row_entities)
            row_w = (max_col + 1) * default_w + max_col * col_gap
        else:
            row_w = sum(sizes[str(entity["id"])][0] for entity in row_entities) + max(0, len(row_entities) - 1) * col_gap
        row_h_actual = max(sizes[str(entity["id"])][1] for entity in row_entities)
        row_x = (width - row_w) / 2
        x = row_x
        for entity in row_entities:
            entity_id = str(entity["id"])
            ew, eh = sizes[entity_id]
            if explicit_cols:
                ex = row_x + int(entity.get("col", 0)) * (default_w + col_gap)
            else:
                ex = x
            ex = float(entity.get("x", ex))
            ey = float(entity.get("y", y + (row_h_actual - eh) / 2))
            positions[entity_id] = (ex, ey, ew, eh)
            x += ew + col_gap
        y += row_h_actual + row_gap
    grid = _object_relationship_grid(contract, positions, diagram_type)
    entity_rects = list(positions.values())
    relationship_bottoms = []
    for rel in contract.get("relationships", []) or []:
        if not isinstance(rel, dict):
            continue
        source = str(rel.get("from", ""))
        target = str(rel.get("to", ""))
        if source not in positions or target not in positions:
            continue
        cx, cy = _relationship_center(rel, positions[source], positions[target], entity_rects, grid)
        relationship_bottoms.append(cy + float(rel.get("diamond_height", 46)) / 2)
    content_bottom = max(
        [ey + eh for ex, ey, ew, eh in positions.values()] + relationship_bottoms,
        default=top_y,
    )
    panels = _info_panels(contract)
    left_panels: list[dict] = []
    right_panels: list[dict] = []
    bottom_panels = panels
    if diagram_type == "ontology_map":
        left_panels, right_panels, bottom_panels = _ontology_panel_groups(panels)
    panel_y = content_bottom + 36
    _layouts, panels_h = _info_panel_layouts(bottom_panels, margin_x, panel_y, width - 2 * margin_x, width)
    bottom_h = panel_y + panels_h + 64 if bottom_panels else content_bottom + 82
    height = int(max(contract.get("height", 0), bottom_h))
    return width, height, positions, panel_y, grid


def _auto_relationship_center(source_rect: tuple[float, float, float, float], target_rect: tuple[float, float, float, float]) -> tuple[float, float]:
    sx, sy, sw, sh = source_rect
    tx, ty, tw, th = target_rect
    scx, scy = _rect_center(source_rect)
    tcx, tcy = _rect_center(target_rect)

    if sx + sw <= tx:
        return (sx + sw + tx) / 2, (scy + tcy) / 2
    if tx + tw <= sx:
        return (tx + tw + sx) / 2, (scy + tcy) / 2
    if sy + sh <= ty:
        return (scx + tcx) / 2, (sy + sh + ty) / 2
    if ty + th <= sy:
        return (scx + tcx) / 2, (ty + th + sy) / 2
    return (scx + tcx) / 2, (scy + tcy) / 2


def _snap_relationship_center_to_card_axis(
    cx: float,
    cy: float,
    source_rect: tuple[float, float, float, float],
    target_rect: tuple[float, float, float, float],
    diamond_w: float,
    diamond_h: float,
    rel: dict,
) -> tuple[float, float]:
    if rel.get("snap_to_axis") is False:
        return cx, cy
    sx, sy, sw, sh = source_rect
    tx, ty, tw, th = target_rect
    scx, scy = _rect_center(source_rect)
    tcx, tcy = _rect_center(target_rect)
    y_axis = (scy + tcy) / 2
    x_axis = (scx + tcx) / 2
    snap_y_tolerance = max(18.0, diamond_h * 0.55)
    snap_x_tolerance = max(18.0, diamond_w * 0.28)
    if (sx + sw <= tx or tx + tw <= sx) and abs(cy - y_axis) <= snap_y_tolerance:
        return cx, y_axis
    if (sy + sh <= ty or ty + th <= sy) and abs(cx - x_axis) <= snap_x_tolerance:
        return x_axis, cy
    return cx, cy


def _relationship_center(
    rel: dict,
    source_rect: tuple[float, float, float, float],
    target_rect: tuple[float, float, float, float],
    entity_rects: list[tuple[float, float, float, float]],
    grid: dict,
) -> tuple[float, float]:
    diamond_w = float(rel.get("diamond_width", 96))
    diamond_h = float(rel.get("diamond_height", 46))
    if isinstance(rel.get("row"), (int, float)) or isinstance(rel.get("col"), (int, float)):
        auto_x, auto_y = _auto_relationship_center(source_rect, target_rect)
        cx = _slot_axis_value(grid.get("cols", {}), float(rel["col"])) if isinstance(rel.get("col"), (int, float)) else auto_x
        cy = _slot_axis_value(grid.get("rows", {}), float(rel["row"])) if isinstance(rel.get("row"), (int, float)) else auto_y
        return _snap_relationship_center_to_card_axis(cx, cy, source_rect, target_rect, diamond_w, diamond_h, rel)
    if isinstance(rel.get("x"), (int, float)) and isinstance(rel.get("y"), (int, float)):
        cx, cy = float(rel["x"]), float(rel["y"])
        if not _relationship_overlaps_entity(cx, cy, diamond_w, diamond_h, entity_rects):
            return _snap_relationship_center_to_card_axis(cx, cy, source_rect, target_rect, diamond_w, diamond_h, rel)
        return _auto_relationship_center(source_rect, target_rect)
    sx, sy = _rect_center(source_rect)
    tx, ty = _rect_center(target_rect)
    cx, cy = _auto_relationship_center(source_rect, target_rect)
    if _relationship_overlaps_entity(cx, cy, diamond_w, diamond_h, entity_rects):
        return (sx + tx) / 2, (sy + ty) / 2
    return _snap_relationship_center_to_card_axis(cx, cy, source_rect, target_rect, diamond_w, diamond_h, rel)


def _render_relationship_diamond(rel: dict, cx: float, cy: float, style: dict, canvas_w: float) -> str:
    color = style_color(style, rel.get("accent"), "")
    if not VALID_HEX.match(color):
        color = style_color(style, "accent_orange", "#FF9F2E")
    w = float(rel.get("diamond_width", 96))
    h = float(rel.get("diamond_height", 46))
    label = str(rel.get("label", rel.get("id", "rel")))
    label_size = _clamp(13.5 * _clamp(canvas_w / 1500.0, 0.95, 1.08), 13.5, 14.5)
    lines = wrap_text(label, max_chars=max(6, int((w - 18) / (label_size * 0.55))), max_lines=2)
    path = f"M {cx} {cy - h/2} L {cx + w/2} {cy} L {cx} {cy + h/2} L {cx - w/2} {cy} Z"
    slot_attrs = ""
    if isinstance(rel.get("row"), (int, float)):
        slot_attrs += f' data-slot-row="{e(rel["row"])}"'
    if isinstance(rel.get("col"), (int, float)):
        slot_attrs += f' data-slot-col="{e(rel["col"])}"'
    parts = [f'<g id="relationship-{e(rel.get("id", label))}" class="relationship-diamond" data-relation="{e(label)}"{slot_attrs}>']
    parts.append(f'<path d="{path}" fill="{pale_for(style, color)}" stroke="{color}" stroke-width="1.4"/>')
    start_y = cy + label_size / 3 - (len(lines) - 1) * (label_size + 1) / 2
    for idx, line in enumerate(lines):
        parts.append(f'<text x="{cx}" y="{start_y + idx * (label_size + 1)}" text-anchor="middle" class="note" style="font-size:{_fmt_px(label_size)};fill:{style_color(style, "text_primary", "#F4F8FF")}">{e(line)}</text>')
    parts.append('</g>')
    return "".join(parts)


def _render_object_relationship(contract: dict, style: dict, diagram_type: str) -> str:
    width, height, positions, panel_y, grid = _object_relationship_layout(contract, style, diagram_type)
    margin_x = int(contract.get("canvas_margin_x", layout_metrics(style)["canvas_margin_x"]))
    parts = _svg_shell_start(contract, style, width, height, diagram_type)
    diamond_specs: list[tuple[dict, float, float]] = []
    link_parts: list[str] = []
    label_parts: list[str] = []
    entity_rects = list(positions.values())
    item_by_id = {str(item["id"]): item for item in _relationship_layout_items(contract, diagram_type)}
    instance_ids = _relationship_instance_ids(contract, diagram_type)
    relationship_link_class = "edge object-relationship-link"
    if diagram_type == "ontology_map":
        relationship_link_class += " ontology-relationship-link"
    used_label_boxes: list[tuple[float, float, float, float]] = []
    line_color = style_color(style, "line_primary", "#F4F8FF")
    card_label_size = _clamp(14.0 * _clamp(width / 1500.0, 0.95, 1.08), 13.5, 15.0)
    relationship_layouts: list[tuple[dict, str, str, float, float, float, float]] = []
    all_diamond_boxes: list[tuple[float, float, float, float]] = []
    for rel in contract.get("relationships", []) or []:
        if not isinstance(rel, dict):
            continue
        source = str(rel.get("from", ""))
        target = str(rel.get("to", ""))
        if source not in positions or target not in positions:
            continue
        source_rect = positions[source]
        target_rect = positions[target]
        cx, cy = _relationship_center(rel, source_rect, target_rect, entity_rects, grid)
        diamond_w = float(rel.get("diamond_width", 96))
        diamond_h = float(rel.get("diamond_height", 46))
        relationship_layouts.append((rel, source, target, cx, cy, diamond_w, diamond_h))
        all_diamond_boxes.append(_relationship_box(cx, cy, diamond_w, diamond_h))

    for rel_idx, (rel, source, target, cx, cy, diamond_w, diamond_h) in enumerate(relationship_layouts):
        source_rect = positions[source]
        target_rect = positions[target]
        color = _connector_relation_color(
            style,
            rel,
            default_token="line_primary",
            palette_index=rel_idx,
            use_palette=rel.get("style") in {"dashed", "secondary"},
        )
        dash = ' stroke-dasharray="6 5"' if rel.get("style") in {"dashed", "secondary"} else ""
        rel_id = e(rel.get("id", f"{source}-{target}"))
        label_obstacles = entity_rects + all_diamond_boxes
        if source == target:
            card_anchor, card_side = _rect_anchor_with_side(source_rect, (cx, cy), rel.get("from_anchor") or rel.get("to_anchor"))
            d_anchor, d_side = _diamond_anchor_with_side(
                cx,
                cy,
                diamond_w,
                diamond_h,
                card_anchor,
                rel.get("from_diamond_anchor") or rel.get("to_diamond_anchor"),
            )
            self_points = _orthogonal_link_points(d_anchor, card_anchor, d_side, card_side)
            self_route = "axis" if len(self_points) == 2 else "orthogonal"
            link_parts.append(f'<path d="{_rounded_path(self_points)}" class="{relationship_link_class}" style="stroke:{color};opacity:0.9"{dash} data-route="{self_route}" data-link-end="self" data-card-anchor="{card_side}" data-diamond-anchor="{d_side}" data-relationship="{rel_id}" data-from="{e(source)}" data-to="{e(target)}"/>')
            for key, endpoint in (("from_cardinality", "from"), ("to_cardinality", "to")):
                card = rel.get(key)
                if card:
                    label_parts.append(
                        _render_cardinality_label(
                            str(card),
                            card_anchor,
                            card_side,
                            source_rect,
                            card_label_size,
                            style,
                            rel_id,
                            endpoint,
                            label_obstacles,
                            used_label_boxes,
                        )
                    )
            diamond_specs.append((rel, cx, cy))
            continue
        avoid_diamond_boxes = [box for idx, box in enumerate(all_diamond_boxes) if idx != rel_idx]
        source_points, target_points, s_side, t_side, d_from_side, d_to_side = _relationship_link_pair(
            rel,
            source_rect,
            target_rect,
            cx,
            cy,
            diamond_w,
            diamond_h,
            avoid_diamond_boxes,
        )
        s_anchor = source_points[0]
        t_anchor = target_points[-1]
        source_route = "axis" if len(source_points) == 2 else "orthogonal"
        target_route = "axis" if len(target_points) == 2 else "orthogonal"
        link_parts.append(f'<path d="{_rounded_path(source_points)}" class="{relationship_link_class}" style="stroke:{color};opacity:0.9"{dash} data-route="{source_route}" data-link-end="from" data-card-anchor="{s_side}" data-diamond-anchor="{d_from_side}" data-relationship="{rel_id}" data-from="{e(source)}" data-to="{e(target)}"/>')
        link_parts.append(f'<path d="{_rounded_path(target_points)}" class="{relationship_link_class}" style="stroke:{color};opacity:0.9"{dash} data-route="{target_route}" data-link-end="to" data-card-anchor="{t_side}" data-diamond-anchor="{d_to_side}" data-relationship="{rel_id}" data-from="{e(source)}" data-to="{e(target)}"/>')
        for key, anchor, side, rect, endpoint in (
            ("from_cardinality", s_anchor, s_side, source_rect, "from"),
            ("to_cardinality", t_anchor, t_side, target_rect, "to"),
        ):
            card = rel.get(key)
            if card:
                label_parts.append(
                    _render_cardinality_label(
                        str(card),
                        anchor,
                        side,
                        rect,
                        card_label_size,
                        style,
                        rel_id,
                        endpoint,
                        label_obstacles,
                        used_label_boxes,
                    )
                )
        diamond_specs.append((rel, cx, cy))

    parts.extend(link_parts)
    if diagram_type == "ontology_map":
        parts.extend(_render_ontology_instance_links(contract, positions, style))
    for entity_id in sorted(positions, key=lambda eid: (positions[eid][1], positions[eid][0])):
        entity = item_by_id[entity_id]
        if diagram_type == "ontology_map":
            if entity_id in instance_ids:
                parts.append(_render_ontology_instance(entity, positions[entity_id], style, width))
            else:
                parts.append(_render_ontology_concept(entity, positions[entity_id], style, width))
        else:
            parts.append(_render_object_entity(entity, positions[entity_id], style, width))
    for rel, cx, cy in diamond_specs:
        parts.append(_render_relationship_diamond(rel, cx, cy, style, width))
    parts.extend(label_parts)
    panels = _info_panels(contract)
    if diagram_type == "ontology_map":
        _left_panels, _right_panels, bottom_panels = _ontology_panel_groups(panels)
        _render_info_panels(parts, bottom_panels, style, margin_x, panel_y, width - 2 * margin_x, width)
    else:
        _render_info_panels(parts, panels, style, margin_x, panel_y, width - 2 * margin_x, width)
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
    if strategy == "object_relationship":
        return _render_object_relationship(contract, style, diagram_type)
    if strategy == "capability_map":
        return _render_capability_domain_map(contract, style, diagram_type)
    if strategy == "boundary_matrix":
        return _render_boundary_ownership_matrix(contract, style, diagram_type)
    if strategy == "relationship_matrix":
        return _render_relationship_matrix(contract, style, diagram_type)
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
