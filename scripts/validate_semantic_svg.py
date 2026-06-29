#!/usr/bin/env python3
"""Lightweight QA checks for semantic-diagram SVG output.

This is intentionally dependency-free. It catches common renderer/manual-edit
failures before delivery: malformed colors, icon paths escaping their card,
ambiguous dashed-line overuse, and obvious text-collision risk.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HEX_OR_NONE = re.compile(r'^(#[0-9A-Fa-f]{6}|none|context-stroke|url\(#[-A-Za-z0-9_]+\))$')
ATTR = re.compile(r'(fill|stroke)="([^"]+)"')
SVG_SIZE = re.compile(r'<svg[^>]*width="([0-9.]+)"[^>]*height="([0-9.]+)"')
DATA_DIAGRAM_RE = re.compile(r'data-diagram-type="([^"]+)"')
CARD_RE = re.compile(
    r'<g\b(?=[^>]*(?:\bclass="[^"]*\bcard\b[^"]*"|\bid="node-[^"]+"))[^>]*>(.*?)</g>',
    re.S,
)
CAPABILITY_ITEM_RE = re.compile(
    r'<g\b[^>]*\bid="capability-item-([^"]+)"[^>]*\bclass="[^"]*\bcapability-map-item\b[^"]*"[^>]*>(.*?)</g>',
    re.S,
)
INFO_PANEL_RE = re.compile(r'<g\b(?=[^>]*\bclass="[^"]*\binfo-panel\b[^"]*")[^>]*>(.*?)</g>', re.S)
RELATIONSHIP_DIAMOND_RE = re.compile(
    r'<g\b(?=[^>]*\bclass="[^"]*\brelationship-diamond\b[^"]*")[^>]*>.*?'
    r'<path\b[^>]*\bd="M ([0-9.]+) ([0-9.]+) L ([0-9.]+) ([0-9.]+) L ([0-9.]+) ([0-9.]+) L ([0-9.]+) ([0-9.]+) Z"',
    re.S,
)
RELATIONSHIP_DIAMOND_ID_RE = re.compile(
    r'<g\b(?=[^>]*\bclass="[^"]*\brelationship-diamond\b[^"]*")(?=[^>]*\bid="relationship-([^"]+)")[^>]*>.*?'
    r'<path\b[^>]*\bd="M ([0-9.]+) ([0-9.]+) L ([0-9.]+) ([0-9.]+) L ([0-9.]+) ([0-9.]+) L ([0-9.]+) ([0-9.]+) Z"',
    re.S,
)
CARDINALITY_LABEL_RE = re.compile(
    r'<g\b(?=[^>]*\bclass="[^"]*\bcardinality-label-wrap\b[^"]*")[^>]*>.*?'
    r'<rect x="([0-9.]+)" y="([0-9.]+)" width="([0-9.]+)" height="([0-9.]+)"',
    re.S,
)
MATRIX_CELL_RE = re.compile(
    r'<rect\b(?=[^>]*\bclass="[^"]*\bmatrix-cell\b[^"]*")[^>]*'
    r'\bx="([0-9.]+)" y="([0-9.]+)" width="([0-9.]+)" height="([0-9.]+)"',
    re.S,
)
MATRIX_PREVIEW_NODE_RE = re.compile(
    r'<g\b(?=[^>]*\bclass="[^"]*\bmatrix-preview-node\b[^"]*")[^>]*>.*?'
    r'<rect x="([-0-9.]+)" y="([-0-9.]+)" width="([-0-9.]+)" height="([-0-9.]+)"',
    re.S,
)
RECT_RE = re.compile(r'<rect x="([0-9.]+)" y="([0-9.]+)" width="([0-9.]+)" height="([0-9.]+)"')
TEXT_RE = re.compile(r'<text[^>]*class="card-(title|sub)"[^>]*>(.*?)</text>')
TEXT_ELEMENT_RE = re.compile(r'<text\b([^>]*)>(.*?)</text>', re.S)
TEXT_TAG_RE = re.compile(r'<text\b([^>]*)>', re.S)
LAYER_RE = re.compile(r'<rect x="([0-9.]+)" y="([0-9.]+)" width="([0-9.]+)" height="([0-9.]+)"[^>]*>?</rect>|<rect x="([0-9.]+)" y="([0-9.]+)" width="([0-9.]+)" height="([0-9.]+)"[^>]*/>')
GROUP_LABEL_RE = re.compile(r'<text[^>]*class="group-label"[^>]*>')
MATRIX_TOP_CONNECTED_PANEL_RE = re.compile(
    r'<g\b(?=[^>]*\bclass="[^"]*\bmatrix-top-connected-panel\b[^"]*")[^>]*>(.*?)</g>',
    re.S,
)
PATH_RE = re.compile(r'<path\b([^>]*)/?>')
CLASS_RE = re.compile(r'class="([^"]+)"')
D_RE = re.compile(r'\bd="([^"]+)"')
DATA_FROM_RE = re.compile(r'\bdata-from="([^"]*)"')
DATA_TO_RE = re.compile(r'\bdata-to="([^"]*)"')
DATA_RELATIONSHIP_RE = re.compile(r'\bdata-relationship="([^"]*)"')
STROKE_STYLE_RE = re.compile(r'stroke\s*:\s*(#[0-9A-Fa-f]{6})')
STROKE_ATTR_RE = re.compile(r'\bstroke="([^"]+)"')
DIRECT_LINE_RE = re.compile(r'^M ([-0-9.]+) ([-0-9.]+) L ([-0-9.]+) ([-0-9.]+)$')
MARKER_RE = re.compile(r'<marker\b([^>]*)>(.*?)</marker>', re.S)
FILL_RE = re.compile(r'\bfill="([^"]+)"')
STYLE_FONT_RE = re.compile(r'\bfont\s*:[^;}]*?([0-9.]+)px', re.S)
INLINE_FONT_RE = re.compile(r'\bfont-size\s*:\s*([0-9.]+)px')
X_ATTR_RE = re.compile(r'\bx="([-0-9.]+)"')
Y_ATTR_RE = re.compile(r'\by="([-0-9.]+)"')
CONNECTOR_CLASSES = {
    'edge',
    'edge-dashed',
    'line',
    'bus',
    'branch',
    'trunk',
    'terminal',
    'route-shared',
    'fanout',
    'fanoutbus',
    'fanin',
    'faninbus',
}
PATH_TOKEN_RE = re.compile(r'[MLQHVZmlqhvz]|[-+]?(?:\d*\.)?\d+(?:[eE][-+]?\d+)?')
EPS = 1e-6
BUS_CARD_CLEARANCE = 24.0
BUS_LANE_GAP = 48.0
LAYER_LABEL_HEIGHT = 42.0
TEXT_MIN_SIZES = {
    'group-label': 14.5,
    'tree-level-label': 14.5,
    'hub-label': 14.5,
    'note': 13.5,
    'table-header': 14.5,
    'table-cell': 16.0,
    'table-cell-secondary': 16.0,
    'info-panel-title': 14.5,
    'info-panel-item': 13.5,
    'capability-level-label': 14.5,
    'capability-column-label': 14.5,
}
INLINE_TEXT_MIN_SIZES = {
    'card-title': 18.0,
    'card-sub': 13.5,
    'capability-title': 16.0,
    'capability-sub': 13.0,
    'matrix-row-label': 14.0,
    'matrix-col-label': 14.0,
    'matrix-cell-value': 20.0,
    'ontology-attr': 13.0,
    'ontology-datatype': 13.0,
    'ontology-instance-title': 15.0,
    'ontology-instance-sub': 12.5,
}


def fail(msg: str, issues: list[str]) -> None:
    issues.append(msg)



def _rect_values(match: re.Match) -> tuple[float, float, float, float]:
    groups = match.groups()
    vals = groups[:4] if groups[0] is not None else groups[4:]
    return tuple(float(v) for v in vals)  # type: ignore[return-value]




def _path_tokens(d: str) -> list[str]:
    return PATH_TOKEN_RE.findall(d.replace(',', ' '))


def _path_attrs_with_classes(svg: str, wanted: set[str]) -> list[tuple[str, str, set[str]]]:
    matches = []
    for m in PATH_RE.finditer(svg):
        attrs = m.group(1)
        cm = CLASS_RE.search(attrs)
        dm = D_RE.search(attrs)
        if not cm or not dm:
            continue
        classes = set(cm.group(1).split())
        matched = classes & wanted
        if matched:
            matches.append((attrs, dm.group(1), classes))
    return matches


def _path_stroke(attrs: str) -> str:
    style_match = STROKE_STYLE_RE.search(attrs)
    if style_match:
        return style_match.group(1).lower()
    attr_match = STROKE_ATTR_RE.search(attrs)
    if attr_match:
        return attr_match.group(1).lower()
    return ''


def _axis_segment(a: tuple[float, float], b: tuple[float, float]) -> tuple[str | None, tuple[float, float], tuple[float, float]]:
    if abs(a[0] - b[0]) < EPS and abs(a[1] - b[1]) >= EPS:
        return 'v', a, b
    if abs(a[1] - b[1]) < EPS and abs(a[0] - b[0]) >= EPS:
        return 'h', a, b
    return None, a, b


def _parse_path_geometry(d: str) -> dict:
    """Parse simple SVG path geometry used by semantic diagrams.

    Returns endpoints, first/last tangent orientation, and straight axis-aligned
    L/H/V segments. Curves are intentionally not flattened: their presence means
    the route is already rounded at that local turn.
    """
    toks = _path_tokens(d)
    i = 0
    cmd = ''
    cur = (0.0, 0.0)
    start = None
    points: list[tuple[float, float]] = []
    straight_segments: list[tuple[str, tuple[float, float], tuple[float, float]]] = []
    first_dir: str | None = None
    last_dir: str | None = None

    def is_cmd(tok: str) -> bool:
        return bool(re.fullmatch(r'[MLQHVZmlqhvz]', tok))

    def add_line(to: tuple[float, float]) -> None:
        nonlocal cur, first_dir, last_dir
        orient, a, b = _axis_segment(cur, to)
        if orient:
            straight_segments.append((orient, a, b))
            first_dir = first_dir or orient
            last_dir = orient
        cur = to
        points.append(cur)

    while i < len(toks):
        if is_cmd(toks[i]):
            cmd = toks[i]
            i += 1
            if cmd in {'Z', 'z'}:
                break
        if cmd in {'M', 'm'}:
            if i + 1 >= len(toks):
                break
            x, y = float(toks[i]), float(toks[i + 1]); i += 2
            if cmd == 'm':
                x += cur[0]; y += cur[1]
            cur = (x, y)
            if start is None:
                start = cur
            points.append(cur)
            cmd = 'L' if cmd == 'M' else 'l'
        elif cmd in {'L', 'l'}:
            if i + 1 >= len(toks):
                break
            x, y = float(toks[i]), float(toks[i + 1]); i += 2
            if cmd == 'l':
                x += cur[0]; y += cur[1]
            add_line((x, y))
        elif cmd in {'H', 'h'}:
            if i >= len(toks):
                break
            x = float(toks[i]); i += 1
            if cmd == 'h':
                x += cur[0]
            add_line((x, cur[1]))
        elif cmd in {'V', 'v'}:
            if i >= len(toks):
                break
            y = float(toks[i]); i += 1
            if cmd == 'v':
                y += cur[1]
            add_line((cur[0], y))
        elif cmd in {'Q', 'q'}:
            if i + 3 >= len(toks):
                break
            x1, y1, x, y = float(toks[i]), float(toks[i + 1]), float(toks[i + 2]), float(toks[i + 3]); i += 4
            if cmd == 'q':
                x1 += cur[0]; y1 += cur[1]; x += cur[0]; y += cur[1]
            orient, _a, _b = _axis_segment((x1, y1), (x, y))
            last_dir = orient or last_dir
            if first_dir is None:
                orient_start, _a, _b = _axis_segment(cur, (x1, y1))
                first_dir = orient_start
            cur = (x, y)
            points.append((x1, y1))
            points.append(cur)
        else:
            break
    return {
        'start': start,
        'end': cur if points else None,
        'first_dir': first_dir,
        'last_dir': last_dir,
        'segments': straight_segments,
        'points': points,
        'has_curve': 'Q' in d or 'q' in d or 'C' in d or 'c' in d or 'A' in d or 'a' in d,
        'd': d,
    }


def _point_on_segment(pt: tuple[float, float], seg: tuple[str, tuple[float, float], tuple[float, float]]) -> bool:
    orient, a, b = seg
    x, y = pt
    if orient == 'h':
        return abs(y - a[1]) < EPS and min(a[0], b[0]) - EPS <= x <= max(a[0], b[0]) + EPS
    if orient == 'v':
        return abs(x - a[0]) < EPS and min(a[1], b[1]) - EPS <= y <= max(a[1], b[1]) + EPS
    return False


def _perpendicular(a: str | None, b: str | None) -> bool:
    return bool(a and b and a != b and {a, b} == {'h', 'v'})


def _path_class_set(path: dict) -> set[str]:
    return set(str(path.get('classes', '')).split())


def _is_intentional_bus_junction(a: dict, b: dict) -> bool:
    """Allow row-bus connector joins that are intentionally rendered as T joints."""
    ac = _path_class_set(a)
    bc = _path_class_set(b)

    if 'bus' in ac or 'bus' in bc:
        other = bc if 'bus' in ac else ac
        return bool(other & {'branch', 'trunk', 'terminal'})

    if 'trunk' in ac or 'trunk' in bc:
        other = bc if 'trunk' in ac else ac
        return bool(other & {'terminal', 'route-shared'})

    return False


def _connector_paths(svg: str) -> list[dict]:
    paths = []
    for idx, (_attrs, d, classes) in enumerate(_path_attrs_with_classes(svg, CONNECTOR_CLASSES), start=1):
        geom = _parse_path_geometry(d)
        geom['idx'] = idx
        geom['classes'] = ' '.join(sorted(classes))
        paths.append(geom)
    return paths


def _layer_rects(svg: str) -> list[tuple[float, float, float, float]]:
    layers: list[tuple[float, float, float, float]] = []
    for m in LAYER_RE.finditer(svg):
        x, y, w, h = _rect_values(m)
        after = svg[m.end(): m.end() + 140].lstrip()
        if (GROUP_LABEL_RE.match(after) or 'class="group-panel"' in m.group(0)) and w >= 500 and h >= 120:
            layers.append((x, y, w, h))
    layers.sort(key=lambda r: r[1])
    return layers


def _card_rects(svg: str) -> list[tuple[float, float, float, float]]:
    cards = []
    for card in CARD_RE.findall(svg):
        rect = RECT_RE.search(card)
        if not rect:
            continue
        cards.append(tuple(map(float, rect.groups())))
    return cards


def _capability_item_rects(svg: str) -> dict[str, tuple[float, float, float, float]]:
    items: dict[str, tuple[float, float, float, float]] = {}
    for item_id, body in CAPABILITY_ITEM_RE.findall(svg):
        rect = RECT_RE.search(body)
        if not rect:
            continue
        items[item_id] = tuple(map(float, rect.groups()))  # type: ignore[assignment]
    return items


def _info_panel_rects(svg: str) -> list[tuple[float, float, float, float]]:
    panels = []
    for panel in INFO_PANEL_RE.findall(svg):
        rect = RECT_RE.search(panel)
        if not rect:
            continue
        panels.append(tuple(map(float, rect.groups())))
    return panels


def _relationship_diamond_rects(svg: str) -> list[tuple[float, float, float, float]]:
    diamonds = []
    for match in RELATIONSHIP_DIAMOND_RE.finditer(svg):
        coords = list(map(float, match.groups()))
        xs = coords[0::2]
        ys = coords[1::2]
        diamonds.append((min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)))
    return diamonds


def _relationship_diamond_rects_by_id(svg: str) -> list[tuple[str, tuple[float, float, float, float]]]:
    diamonds = []
    for match in RELATIONSHIP_DIAMOND_ID_RE.finditer(svg):
        rel_id = match.group(1)
        coords = list(map(float, match.groups()[1:]))
        xs = coords[0::2]
        ys = coords[1::2]
        diamonds.append((rel_id, (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))))
    return diamonds


def _cardinality_label_rects(svg: str) -> list[tuple[float, float, float, float]]:
    return [tuple(map(float, match.groups())) for match in CARDINALITY_LABEL_RE.finditer(svg)]


def _diagram_type(svg: str) -> str:
    match = DATA_DIAGRAM_RE.search(svg)
    return match.group(1) if match else ''


def _css_font_sizes(svg: str, class_name: str) -> list[float]:
    sizes: list[float] = []
    rule_re = re.compile(rf'\.{re.escape(class_name)}\s*\{{([^}}]*)\}}', re.S)
    for match in rule_re.finditer(svg):
        font_match = STYLE_FONT_RE.search(match.group(1))
        if font_match:
            sizes.append(float(font_match.group(1)))
    return sizes


def _inline_font_sizes(svg: str, class_name: str) -> list[float]:
    sizes: list[float] = []
    for match in TEXT_TAG_RE.finditer(svg):
        attrs = match.group(1)
        class_match = CLASS_RE.search(attrs)
        if not class_match or class_name not in class_match.group(1).split():
            continue
        font_match = INLINE_FONT_RE.search(attrs)
        if font_match:
            sizes.append(float(font_match.group(1)))
    return sizes


def _text_width_estimate(text: str, size: float, factor: float = 0.56) -> float:
    return len(text) * size * factor


def _text_elements_with_class(svg: str, class_name: str) -> list[tuple[float, float, float, str]]:
    elements: list[tuple[float, float, float, str]] = []
    for attrs, raw_text in TEXT_ELEMENT_RE.findall(svg):
        class_match = CLASS_RE.search(attrs)
        if not class_match or class_name not in class_match.group(1).split():
            continue
        x_match = X_ATTR_RE.search(attrs)
        y_match = Y_ATTR_RE.search(attrs)
        font_match = INLINE_FONT_RE.search(attrs)
        if not x_match or not y_match or not font_match:
            continue
        text = re.sub(r'<[^>]+>', '', raw_text).strip()
        elements.append((float(x_match.group(1)), float(y_match.group(1)), float(font_match.group(1)), text))
    return elements


def _check_arrow_markers(svg: str, issues: list[str]) -> None:
    for attrs, body in MARKER_RE.findall(svg):
        id_match = re.search(r'\bid="([^"]+)"', attrs)
        if not id_match or 'arrow' not in id_match.group(1):
            continue
        fills = FILL_RE.findall(body)
        if 'context-stroke' not in fills:
            fail(
                f'arrow marker "{id_match.group(1)}" should use context-stroke so arrowheads match connector color',
                issues,
            )


def _check_text_scale(svg: str, issues: list[str]) -> None:
    for class_name, minimum in TEXT_MIN_SIZES.items():
        for size in _css_font_sizes(svg, class_name):
            if size + EPS < minimum:
                fail(f'{class_name} font size {size:g}px is below readable minimum {minimum:g}px', issues)
        for size in _inline_font_sizes(svg, class_name):
            if size + EPS < minimum:
                fail(f'{class_name} font size {size:g}px is below readable minimum {minimum:g}px', issues)

    for class_name, minimum in INLINE_TEXT_MIN_SIZES.items():
        for size in _inline_font_sizes(svg, class_name):
            if size + EPS < minimum:
                fail(f'{class_name} font size {size:g}px is below readable minimum {minimum:g}px', issues)


def _check_group_label_shields(svg: str, issues: list[str]) -> None:
    if 'class="group-panel"' not in svg:
        return
    label_count = len(GROUP_LABEL_RE.findall(svg))
    if not label_count:
        return
    shield_count = svg.count('class="group-label-wrap"')
    if shield_count < label_count:
        fail('group labels should use background shields when group panels are rendered', issues)
    first_edge = svg.find('class="edge')
    first_shield = svg.find('class="group-label-wrap"')
    if first_edge != -1 and first_shield != -1 and first_shield < first_edge:
        fail('group label shields should be drawn above connector paths', issues)


def _check_canvas_density(svg: str, issues: list[str]) -> None:
    if _diagram_type(svg) != 'hub_spoke':
        return
    size = SVG_SIZE.search(svg)
    if not size:
        return
    _width, height = map(float, size.groups())
    cards = _card_rects(svg)
    if not cards:
        return
    content_rects = cards + _info_panel_rects(svg)
    max_content_bottom = max(y + h for _x, y, _w, h in content_rects)
    bottom_whitespace = height - max_content_bottom
    if bottom_whitespace > 140:
        fail(f'hub_spoke canvas has excessive bottom whitespace: {bottom_whitespace:.0f}px', issues)


def _segment_inside_rect(seg: tuple[str, tuple[float, float], tuple[float, float]], rect: tuple[float, float, float, float]) -> bool:
    _orient, a, b = seg
    x, y, w, h = rect
    return (
        x - EPS <= a[0] <= x + w + EPS
        and x - EPS <= b[0] <= x + w + EPS
        and y - EPS <= a[1] <= y + h + EPS
        and y - EPS <= b[1] <= y + h + EPS
    )


def _segment_crosses_card(seg: tuple[str, tuple[float, float], tuple[float, float]], card: tuple[float, float, float, float]) -> bool:
    orient, a, b = seg
    x, y, w, h = card
    if orient == 'h':
        seg_y = a[1]
        if not (y + 2 < seg_y < y + h - 2):
            return False
        return max(min(a[0], b[0]), x + 2) < min(max(a[0], b[0]), x + w - 2)
    if orient == 'v':
        seg_x = a[0]
        if not (x + 2 < seg_x < x + w - 2):
            return False
        return max(min(a[1], b[1]), y + 2) < min(max(a[1], b[1]), y + h - 2)
    return False


def _segment_crosses_expanded_card(
    seg: tuple[str, tuple[float, float], tuple[float, float]],
    card: tuple[float, float, float, float],
    margin: float,
) -> bool:
    x, y, w, h = card
    expanded = (x - margin, y - margin, w + 2 * margin, h + 2 * margin)
    return _segment_crosses_card(seg, expanded)


def _rects_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float], pad: float = 0.0) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax - pad < bx + bw and ax + aw + pad > bx and ay - pad < by + bh and ay + ah + pad > by


def _axis_segment_overlap_length(
    a: tuple[str, tuple[float, float], tuple[float, float]],
    b: tuple[str, tuple[float, float], tuple[float, float]],
    tolerance: float = 1.5,
) -> float:
    orient_a, a1, a2 = a
    orient_b, b1, b2 = b
    if orient_a != orient_b:
        return 0.0
    if orient_a == 'h':
        if abs(a1[1] - b1[1]) > tolerance:
            return 0.0
        return max(0.0, min(max(a1[0], a2[0]), max(b1[0], b2[0])) - max(min(a1[0], a2[0]), min(b1[0], b2[0])))
    if orient_a == 'v':
        if abs(a1[0] - b1[0]) > tolerance:
            return 0.0
        return max(0.0, min(max(a1[1], a2[1]), max(b1[1], b2[1])) - max(min(a1[1], a2[1]), min(b1[1], b2[1])))
    return 0.0


def _check_ontology_geometry(
    svg: str,
    cards: list[tuple[float, float, float, float]],
    diamonds_by_id: list[tuple[str, tuple[float, float, float, float]]],
    issues: list[str],
) -> None:
    if 'class="ontology-concept-card card"' not in svg:
        fail('ontology_map should render ontology concept cards', issues)
    if 'class="ontology-instance-card card"' in svg and 'class="edge ontology-instance-link"' not in svg:
        fail('ontology_map should render instance-to-concept links', issues)
    if 'entity-key-badge' in svg:
        fail('ontology_map should not render ER-style PK/FK badges', issues)

    protected = cards + [diamond for _diamond_id, diamond in diamonds_by_id]
    for idx, panel in enumerate(_info_panel_rects(svg), start=1):
        if any(_rects_overlap(panel, rect, 8.0) for rect in protected):
            fail(f'ontology info panel {idx} overlaps concept, instance, or predicate geometry', issues)

    instance_segments: list[tuple[str, str, tuple[str, tuple[float, float], tuple[float, float]]]] = []
    for attrs, d, _classes in _path_attrs_with_classes(svg, {'ontology-instance-link'}):
        source_match = DATA_FROM_RE.search(attrs)
        target_match = DATA_TO_RE.search(attrs)
        source = source_match.group(1) if source_match else ''
        target = target_match.group(1) if target_match else ''
        geom = _parse_path_geometry(d)
        for seg in geom['segments']:
            instance_segments.append((source, target, seg))
            for diamond_id, diamond in diamonds_by_id:
                if _segment_crosses_expanded_card(seg, diamond, 1.0):
                    fail(f'ontology instance link {source or "unknown"}->{target or "unknown"} crosses predicate diamond {diamond_id}', issues)

    for idx, (source, target, seg) in enumerate(instance_segments):
        for other_source, other_target, other_seg in instance_segments[idx + 1:]:
            if (source, target) == (other_source, other_target):
                continue
            if _axis_segment_overlap_length(seg, other_seg) >= 36.0:
                fail(
                    f'ontology instance links {source or "unknown"}->{target or "unknown"} and '
                    f'{other_source or "unknown"}->{other_target or "unknown"} share the same corridor; offset one lane',
                    issues,
                )


def _check_object_relationship_geometry(svg: str, issues: list[str]) -> None:
    diagram_type = _diagram_type(svg)
    if diagram_type not in {'object_relationship_diagram', 'ontology_map'}:
        return
    cards = _card_rects(svg)
    diamonds_by_id = _relationship_diamond_rects_by_id(svg)
    diamonds = [rect for _rel_id, rect in diamonds_by_id]
    if diagram_type == 'ontology_map':
        _check_ontology_geometry(svg, cards, diamonds_by_id, issues)
    if not diamonds:
        fail(f'{diagram_type} should render relationship diamonds', issues)
        return
    for idx, diamond in enumerate(diamonds, start=1):
        if any(_rects_overlap(diamond, card, 8.0) for card in cards):
            fail(f'relationship diamond {idx} overlaps an entity card', issues)
    for idx, (_diamond_id, diamond) in enumerate(diamonds_by_id, start=1):
        for other_id, other in diamonds_by_id[idx:]:
            if _rects_overlap(diamond, other, 6.0):
                fail(f'relationship diamond {_diamond_id} is too close to relationship diamond {other_id}', issues)
    label_rects = _cardinality_label_rects(svg)
    label_text_count = 0
    for match in TEXT_TAG_RE.finditer(svg):
        class_match = CLASS_RE.search(match.group(1))
        if class_match and 'cardinality-label' in class_match.group(1).split():
            label_text_count += 1
    if label_text_count and len(label_rects) < label_text_count:
        fail('object relationship cardinality labels should use layout wrappers', issues)
    obstacles = cards + diamonds
    for idx, label in enumerate(label_rects, start=1):
        if any(_rects_overlap(label, obstacle, 1.0) for obstacle in obstacles):
            fail(f'cardinality label {idx} overlaps an entity card or relationship diamond', issues)
    relationship_segments: list[tuple[str, tuple[str, tuple[float, float], tuple[float, float]]]] = []
    dashed_relationship_seen = False
    for attrs, d, _classes in _path_attrs_with_classes(svg, {'object-relationship-link'}):
        rel_match = DATA_RELATIONSHIP_RE.search(attrs)
        rel_id = rel_match.group(1) if rel_match else ''
        if 'stroke-dasharray' in attrs:
            dashed_relationship_seen = True
        geom = _parse_path_geometry(d)
        for seg in geom['segments']:
            relationship_segments.append((rel_id, seg))
            for diamond_id, diamond in diamonds_by_id:
                if diamond_id == rel_id:
                    continue
                if _segment_crosses_expanded_card(seg, diamond, 1.0):
                    fail(f'object relationship link for {rel_id or "unknown"} crosses relationship diamond {diamond_id}', issues)
        match = DIRECT_LINE_RE.match(d)
        if not match:
            continue
        x1, y1, x2, y2 = map(float, match.groups())
        if abs(x1 - x2) >= EPS and abs(y1 - y2) >= EPS:
            fail('object relationship link uses a direct diagonal segment; route it orthogonally', issues)
    plain_text = re.sub(r'<[^>]+>', ' ', svg)
    if dashed_relationship_seen and not (re.search(r'dashed', plain_text, re.I) and re.search(r'optional|review|relation|relationship', plain_text, re.I)):
        fail('dashed object relationship links should be explained by a legend or info panel', issues)
    for idx, (rel_id, seg) in enumerate(relationship_segments):
        for other_rel_id, other_seg in relationship_segments[idx + 1:]:
            if rel_id == other_rel_id:
                continue
            if _axis_segment_overlap_length(seg, other_seg) >= 36.0:
                fail(f'object relationship links for {rel_id or "unknown"} and {other_rel_id or "unknown"} share the same corridor; offset one lane', issues)


def _check_capability_map_geometry(svg: str, issues: list[str]) -> None:
    if _diagram_type(svg) != 'capability_domain_map':
        return
    item_rects = _capability_item_rects(svg)
    if 'class="capability-map-item card"' not in svg:
        fail('capability_domain_map should render dedicated capability map items', issues)
    if 'class="capability-badge semantic-badge"' in svg:
        fail('capability_domain_map should not render item badges; use row and column header icons', issues)
    for item_id, (_x, _y, _w, h) in item_rects.items():
        if h < 94:
            fail(f'capability map item {item_id} is too short for dense title/subtitle content', issues)
    item_list = list(item_rects.items())
    for idx, (item_id, rect) in enumerate(item_list):
        x, y, w, h = rect
        for other_id, other in item_list[idx + 1:]:
            ox, oy, ow, oh = other
            if _rects_overlap(rect, other, 2.0):
                fail(f'capability map item {item_id} overlaps item {other_id}', issues)
            horizontal_overlap = min(x + w, ox + ow) - max(x, ox)
            if horizontal_overlap < min(w, ow) * 0.5:
                continue
            vertical_gap = max(y, oy) - min(y + h, oy + oh)
            if 0 <= vertical_gap < 24:
                fail(f'capability map item {item_id} is too close vertically to item {other_id}; increase item_gap or level_gap', issues)
    for idx, panel in enumerate(_info_panel_rects(svg), start=1):
        if any(_rects_overlap(panel, rect, 8.0) for rect in item_rects.values()):
            fail(f'capability info panel {idx} overlaps map items', issues)
    if 'capability-level-label' not in svg:
        fail('capability_domain_map should render level labels', issues)
    if 'capability-column-label' not in svg:
        fail('capability_domain_map should render column labels', issues)
    if 'capability-level-icon' not in svg:
        fail('capability_domain_map should render level header icons', issues)
    if 'capability-column-icon' not in svg:
        fail('capability_domain_map should render column header icons', issues)
    header_rects = [
        tuple(map(float, match.groups()))
        for match in RECT_RE.finditer(svg)
        if 80 <= float(match.group(3)) <= 360 and 28 <= float(match.group(4)) <= 70
    ]
    for idx, (text_x, text_y, size, text) in enumerate(_text_elements_with_class(svg, 'capability-column-label'), start=1):
        containing = [
            rect for rect in header_rects
            if rect[0] <= text_x <= rect[0] + rect[2] and rect[1] - 8 <= text_y <= rect[1] + rect[3] + 8
        ]
        if not containing:
            continue
        header = min(containing, key=lambda rect: rect[2] * rect[3])
        right_limit = header[0] + header[2] - 10.0
        if text_x + _text_width_estimate(text, size, 0.55) > right_limit + 2.0:
            fail(f'capability column label {idx} overflows its header slot; wrap or truncate the label', issues)
    vertical_lanes: list[tuple[float, float, float, str]] = []
    for attrs, d, _classes in _path_attrs_with_classes(svg, {'capability-map-link'}):
        match = DIRECT_LINE_RE.match(d)
        if not match:
            geom = _parse_path_geometry(d)
        else:
            x1, y1, x2, y2 = map(float, match.groups())
            if abs(x1 - x2) >= EPS and abs(y1 - y2) >= EPS:
                fail('capability map link uses a direct diagonal segment; route it orthogonally', issues)
            geom = _parse_path_geometry(d)
        source_match = DATA_FROM_RE.search(attrs)
        target_match = DATA_TO_RE.search(attrs)
        source = source_match.group(1) if source_match else ''
        target = target_match.group(1) if target_match else ''
        obstacles = {item_id: rect for item_id, rect in item_rects.items() if item_id not in {source, target}}
        for seg in geom['segments']:
            if any(_segment_crosses_expanded_card(seg, rect, 8.0) for rect in obstacles.values()):
                fail('capability map link runs too close to a non-endpoint card; use a wider corridor', issues)
                break
            orient, a, b = seg
            if orient == 'v' and abs(a[1] - b[1]) >= 36:
                vertical_lanes.append((a[0], min(a[1], b[1]), max(a[1], b[1]), _path_stroke(attrs)))
    for idx, lane in enumerate(vertical_lanes):
        x, y1, y2, stroke = lane
        if not stroke:
            continue
        for other_x, other_y1, other_y2, other_stroke in vertical_lanes[idx + 1:]:
            if stroke != other_stroke or abs(x - other_x) >= 3:
                continue
            overlap = min(y2, other_y2) - max(y1, other_y1)
            if overlap >= 36:
                fail('capability map links share the same same-color vertical corridor; offset the route lanes', issues)
                return


def _check_relationship_matrix_geometry(svg: str, issues: list[str]) -> None:
    if _diagram_type(svg) != 'relationship_matrix':
        return
    required_classes = (
        'relationship-matrix-grid',
        'matrix-primary-preview',
        'matrix-summary-panel',
        'matrix-focus-detail-panel',
        'matrix-top-connected-panel',
    )
    for class_name in required_classes:
        if class_name not in svg:
            fail(f'relationship_matrix should render {class_name}', issues)
    cells = [tuple(map(float, match.groups())) for match in MATRIX_CELL_RE.finditer(svg)]
    if not cells:
        fail('relationship_matrix should render matrix cells', issues)
    for idx, (_x, _y, w, h) in enumerate(cells, start=1):
        if w < 52 or h < 52:
            fail(f'relationship_matrix cell {idx} is below readable size: {w:.0f}x{h:.0f}', issues)
            break
    if 'matrix-selected-cell' in svg:
        fail('relationship_matrix is static and should not render an interactive-looking selected cell', issues)
    if 'class="matrix-distribution-bar"' not in svg:
        fail('relationship_matrix should render compact distribution bars', issues)
    if 'class="matrix-cell-value"' not in svg:
        fail('relationship_matrix should render readable cell values', issues)
    preview_rects = [tuple(map(float, match.groups())) for match in MATRIX_PREVIEW_NODE_RE.finditer(svg)]
    for idx, (x, y, w, h) in enumerate(preview_rects):
        for ox, oy, ow, oh in preview_rects[idx + 1:]:
            overlap_x = min(x + w, ox + ow) - max(x, ox)
            overlap_y = min(y + h, oy + oh) - max(y, oy)
            if overlap_x > 1 and overlap_y > 1:
                fail('relationship_matrix preview cards should not overlap', issues)
                return
    panels = _info_panel_rects(svg)
    for idx, panel in enumerate(panels):
        for other in panels[idx + 1:]:
            if _rects_overlap(panel, other, 4.0):
                fail('relationship_matrix dashboard panels should not overlap', issues)
                return
    for panel_body in MATRIX_TOP_CONNECTED_PANEL_RE.findall(svg):
        panel_rect = RECT_RE.search(panel_body)
        if not panel_rect:
            continue
        px, _py, pw, _ph = tuple(map(float, panel_rect.groups()))
        fallback_limit = px + pw - 206.0 - 12.0
        row_bars = [
            tuple(map(float, match.groups()))
            for match in RECT_RE.finditer(panel_body)
            if 90 <= float(match.group(3)) <= 130 and 10 <= float(match.group(4)) <= 18
        ]
        for idx, (text_x, text_y, size, text) in enumerate(_text_elements_with_class(panel_body, 'matrix-rank-label'), start=1):
            same_row_bars = [rect for rect in row_bars if abs(rect[1] - (text_y - 13.0)) <= 3 and rect[0] > text_x]
            bar_limit = min((rect[0] for rect in same_row_bars), default=fallback_limit) - 12.0
            if text_x + _text_width_estimate(text, size, 0.56) > bar_limit + 2.0:
                fail(f'relationship_matrix top-connected label {idx} overlaps the ranking bar area; fit or truncate the label', issues)
    if 'data-style="accent-blueprint"' in svg:
        if 'blueprint-grid' not in svg:
            fail('accent-blueprint relationship_matrix should render the blueprint grid', issues)
        if '#F4F8FF' not in svg and '#f4f8ff' not in svg.lower():
            fail('accent-blueprint relationship_matrix should use white/near-white primary linework', issues)


def _check_connector_clearance(svg: str, issues: list[str]) -> None:
    layers = _layer_rects(svg)
    cards = _card_rects(svg)
    paths = _connector_paths(svg)

    for p in paths:
        classes = set(str(p.get('classes', '')).split())
        for seg in p['segments']:
            if any(_segment_crosses_card(seg, card) for card in cards):
                fail(f'connector path {p["idx"]} runs through a card interior', issues)
                break
        if 'bus' not in classes:
            continue
        for seg in p['segments']:
            if seg[0] != 'h':
                continue
            containing = [layer for layer in layers if _segment_inside_rect(seg, layer)]
            if not containing:
                fail(f'bus connector path {p["idx"]} is outside layer bounds', issues)
                continue
            lx, ly, lw, lh = containing[0]
            bus_y = seg[1][1]
            if bus_y < ly + LAYER_LABEL_HEIGHT:
                fail(f'bus connector path {p["idx"]} is too close to the layer label area', issues)
            layer_cards = [card for card in cards if ly <= card[1] <= ly + lh]
            for cx, cy, cw, ch in layer_cards:
                overlap = max(min(seg[1][0], seg[2][0]), cx) < min(max(seg[1][0], seg[2][0]), cx + cw)
                if not overlap:
                    continue
                if bus_y <= cy and cy - bus_y < BUS_CARD_CLEARANCE:
                    fail(f'bus connector path {p["idx"]} is too close above a card', issues)
                if bus_y >= cy + ch and bus_y - (cy + ch) < BUS_CARD_CLEARANCE:
                    fail(f'bus connector path {p["idx"]} is too close below a card', issues)

    for layer in layers:
        lx, ly, lw, lh = layer
        bus_ys = []
        for p in paths:
            if 'bus' not in str(p.get('classes', '')).split():
                continue
            for seg in p['segments']:
                if seg[0] == 'h' and _segment_inside_rect(seg, layer):
                    bus_ys.append(round(seg[1][1], 1))
        bus_ys = sorted(set(bus_ys))
        for a, b in zip(bus_ys, bus_ys[1:]):
            if b - a < BUS_LANE_GAP and any(cy + ch < b and cy > a for _cx, cy, _cw, ch in cards):
                fail(f'bus lanes in layer at y={ly:.0f} are too close: {a}, {b}', issues)


def _check_connector_rounding(svg: str, issues: list[str]) -> None:
    paths = _connector_paths(svg)
    # Same-path orthogonal turns should use a curve command.
    for p in paths:
        d = p['d']
        if p['has_curve']:
            continue
        segments = p['segments']
        for first, second in zip(segments, segments[1:]):
            o1, _a, b = first
            o2, c, _d = second
            if abs(b[0] - c[0]) >= EPS or abs(b[1] - c[1]) >= EPS:
                continue
            if _perpendicular(o1, o2):
                fail(f'connector path {p["idx"]} has hard orthogonal turn without Q elbow: {d}', issues)
                break

    # Multi-path visual T-junctions: a straight endpoint that T-bones into another connector segment.
    for p in paths:
        endpoints = [(p['start'], p['first_dir'], 'start'), (p['end'], p['last_dir'], 'end')]
        for pt, tangent, which in endpoints:
            if pt is None or tangent is None:
                continue
            for q in paths:
                if p is q:
                    continue
                for seg in q['segments']:
                    seg_orient = seg[0]
                    if not _point_on_segment(pt, seg):
                        continue
                    if not _perpendicular(tangent, seg_orient):
                        continue
                    if _is_intentional_bus_junction(p, q):
                        continue
                    fail(
                        f'connector path {p["idx"]} {which} forms hard visual T-junction with path {q["idx"]}; encode the branch as a rounded Q route',
                        issues,
                    )
                    break
                else:
                    continue
                break

def _check_layer_metrics(svg: str, issues: list[str]) -> None:
    # Heuristic for generated semantic diagrams: a layer panel is a large rect
    # immediately followed by a group-label text. This keeps the check generic
    # and avoids relying on domain labels.
    layers = _layer_rects(svg)
    if len(layers) < 2:
        return

    card_bounds = [(y, y + h) for _x, y, _w, h in _card_rects(svg)]

    connector_paths = _connector_paths(svg)
    plain_bottom_pads: list[float] = []
    bus_bottom_pads: list[float] = []
    for i, (_x, y, _w, h) in enumerate(layers):
        next_y = layers[i + 1][1] if i + 1 < len(layers) else y + h + 1
        contained = [b for a, b in card_bounds if y <= a < min(y + h + 30, next_y)]
        if contained:
            max_card_bottom = max(contained)
            bottom_pad = round(y + h - max_card_bottom, 1)
            has_bottom_bus = False
            for path in connector_paths:
                for orient, a, b in path['segments']:
                    if orient != 'h':
                        continue
                    seg_y = a[1]
                    if max_card_bottom + 8 <= seg_y <= y + h - 2:
                        has_bottom_bus = True
                        break
                if has_bottom_bus:
                    break
            if has_bottom_bus:
                bus_bottom_pads.append(bottom_pad)
            else:
                plain_bottom_pads.append(bottom_pad)
    if len(plain_bottom_pads) >= 2 and max(plain_bottom_pads) - min(plain_bottom_pads) > 3:
        fail(f'inconsistent repeated-layer bottom padding: {plain_bottom_pads}', issues)
    if len(bus_bottom_pads) >= 2 and max(bus_bottom_pads) - min(bus_bottom_pads) > 3:
        fail(f'inconsistent repeated-layer bottom padding for bus layers: {bus_bottom_pads}', issues)

    gaps = [round(layers[i + 1][1] - (layers[i][1] + layers[i][3]), 1) for i in range(len(layers) - 1)]
    if len(gaps) >= 2 and max(gaps) - min(gaps) > 3:
        fail(f'inconsistent repeated-layer gaps: {gaps}', issues)


def check_svg(svg: str) -> list[str]:
    issues: list[str] = []
    size = SVG_SIZE.search(svg)
    if not size:
        fail('missing svg width/height', issues)
        width = height = 0.0
    else:
        width, height = map(float, size.groups())

    cards = CARD_RE.findall(svg)
    if re.search(r'<text[^>]*class="[^"]*\bcard-title\b', svg) and not cards:
        fail('card text exists but no card groups were recognized', issues)
    if 'class="edge' in svg and not _connector_paths(svg):
        fail('connector paths exist but no connector geometry was recognized', issues)

    for attr, value in ATTR.findall(svg):
        if value.startswith('#') or value in {'none', 'context-stroke'} or value.startswith('url(#'):
            if not HEX_OR_NONE.match(value):
                fail(f'invalid {attr} value: {value}', issues)
        elif value not in {'currentColor'}:
            # Named colors are avoided so semantic keys do not leak into SVG attrs.
            fail(f'non-portable {attr} value: {value}', issues)

    _check_arrow_markers(svg, issues)
    _check_text_scale(svg, issues)
    _check_group_label_shields(svg, issues)
    _check_canvas_density(svg, issues)
    _check_object_relationship_geometry(svg, issues)
    _check_capability_map_geometry(svg, issues)
    _check_relationship_matrix_geometry(svg, issues)

    dashed_count = 0
    for attrs, _d, classes in _path_attrs_with_classes(svg, {'edge', 'edge-dashed', 'line'}):
        if 'ontology-instance-link' in classes:
            continue
        if 'edge-dashed' in classes or 'stroke-dasharray' in attrs:
            dashed_count += 1
    if dashed_count > 8:
        fail(f'too many dashed relations ({dashed_count}); consider legend/containment instead', issues)

    for idx, card in enumerate(cards, start=1):
        rect = RECT_RE.search(card)
        if not rect:
            continue
        x, y, w, h = map(float, rect.groups())
        # Catch the failure mode where an icon path uses x as a y coordinate and
        # draws a line far outside the badge/card.
        for _attrs, d, _classes in _path_attrs_with_classes(card, {'icon-line'}):
            geom = _parse_path_geometry(d)
            points = geom['points']
            if not points:
                continue
            if width and height:
                for px, py in points:
                    if not (x - 20 <= px <= x + w + 20 and y - 20 <= py <= y + h + 20):
                        fail(f'card {idx} icon path point outside card bounds: {px:.1f},{py:.1f}', issues)
                        break
        title_lines = len(re.findall(r'class="card-title"', card))
        has_sub = 'class="card-sub"' in card
        if title_lines > 1 and h < 92:
            fail(f'card {idx} height {h:.0f} is risky for multi-line title/subtitle separation', issues)
        if has_sub and h < 72:
            fail(f'card {idx} height {h:.0f} is too short for a subtitle', issues)
        for klass, raw in TEXT_RE.findall(card):
            text = re.sub(r'<[^>]+>', '', raw)
            if klass == 'title' and len(text) > max(18, int(w / 8)):
                fail(f'card {idx} title may be too long for width {w:.0f}: {text}', issues)

    _check_connector_rounding(svg, issues)
    _check_connector_clearance(svg, issues)
    _check_layer_metrics(svg, issues)

    if 'Unsupported markdown' in svg:
        fail('contains Unsupported markdown placeholder', issues)
    return issues


def check(path: Path) -> list[str]:
    return check_svg(path.read_text(encoding='utf-8-sig'))


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print('Usage: validate_semantic_svg.py file.svg [file2.svg ...]', file=sys.stderr)
        return 2
    any_issues = False
    for name in argv[1:]:
        issues = check(Path(name))
        if issues:
            any_issues = True
            print(f'{name}: FAIL')
            for issue in issues:
                print(f'  - {issue}')
        else:
            print(f'{name}: PASS')
    return 1 if any_issues else 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
