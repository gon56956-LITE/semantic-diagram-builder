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
CARDINALITY_LABEL_RE = re.compile(
    r'<g\b(?=[^>]*\bclass="[^"]*\bcardinality-label-wrap\b[^"]*")[^>]*>.*?'
    r'<rect x="([0-9.]+)" y="([0-9.]+)" width="([0-9.]+)" height="([0-9.]+)"',
    re.S,
)
RECT_RE = re.compile(r'<rect x="([0-9.]+)" y="([0-9.]+)" width="([0-9.]+)" height="([0-9.]+)"')
TEXT_RE = re.compile(r'<text[^>]*class="card-(title|sub)"[^>]*>(.*?)</text>')
TEXT_TAG_RE = re.compile(r'<text\b([^>]*)>', re.S)
LAYER_RE = re.compile(r'<rect x="([0-9.]+)" y="([0-9.]+)" width="([0-9.]+)" height="([0-9.]+)"[^>]*>?</rect>|<rect x="([0-9.]+)" y="([0-9.]+)" width="([0-9.]+)" height="([0-9.]+)"[^>]*/>')
GROUP_LABEL_RE = re.compile(r'<text[^>]*class="group-label"[^>]*>')
PATH_RE = re.compile(r'<path\b([^>]*)/?>')
CLASS_RE = re.compile(r'class="([^"]+)"')
D_RE = re.compile(r'\bd="([^"]+)"')
DATA_FROM_RE = re.compile(r'\bdata-from="([^"]*)"')
DATA_TO_RE = re.compile(r'\bdata-to="([^"]*)"')
STROKE_STYLE_RE = re.compile(r'stroke\s*:\s*(#[0-9A-Fa-f]{6})')
STROKE_ATTR_RE = re.compile(r'\bstroke="([^"]+)"')
DIRECT_LINE_RE = re.compile(r'^M ([-0-9.]+) ([-0-9.]+) L ([-0-9.]+) ([-0-9.]+)$')
MARKER_RE = re.compile(r'<marker\b([^>]*)>(.*?)</marker>', re.S)
FILL_RE = re.compile(r'\bfill="([^"]+)"')
STYLE_FONT_RE = re.compile(r'\bfont\s*:[^;}]*?([0-9.]+)px', re.S)
INLINE_FONT_RE = re.compile(r'\bfont-size\s*:\s*([0-9.]+)px')
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


def _check_object_relationship_geometry(svg: str, issues: list[str]) -> None:
    if _diagram_type(svg) != 'object_relationship_diagram':
        return
    cards = _card_rects(svg)
    diamonds = _relationship_diamond_rects(svg)
    if not diamonds:
        fail('object_relationship_diagram should render relationship diamonds', issues)
        return
    for idx, diamond in enumerate(diamonds, start=1):
        if any(_rects_overlap(diamond, card, 8.0) for card in cards):
            fail(f'relationship diamond {idx} overlaps an entity card', issues)
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
    for _attrs, d, _classes in _path_attrs_with_classes(svg, {'object-relationship-link'}):
        match = DIRECT_LINE_RE.match(d)
        if not match:
            continue
        x1, y1, x2, y2 = map(float, match.groups())
        if abs(x1 - x2) >= EPS and abs(y1 - y2) >= EPS:
            fail('object relationship link uses a direct diagonal segment; route it orthogonally', issues)


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
    if 'capability-level-label' not in svg:
        fail('capability_domain_map should render level labels', issues)
    if 'capability-column-label' not in svg:
        fail('capability_domain_map should render column labels', issues)
    if 'capability-level-icon' not in svg:
        fail('capability_domain_map should render level header icons', issues)
    if 'capability-column-icon' not in svg:
        fail('capability_domain_map should render column header icons', issues)
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

    dashed_count = svg.count('edge-dashed') + svg.count('stroke-dasharray')
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
