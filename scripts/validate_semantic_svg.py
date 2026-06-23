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

HEX_OR_NONE = re.compile(r'^(#[0-9A-Fa-f]{6}|none|url\(#[-A-Za-z0-9_]+\))$')
ATTR = re.compile(r'(fill|stroke)="([^"]+)"')
SVG_SIZE = re.compile(r'<svg[^>]*width="([0-9.]+)"[^>]*height="([0-9.]+)"')
CARD_RE = re.compile(r'<g[^>]*class="card"[^>]*>(.*?)</g>', re.S)
RECT_RE = re.compile(r'<rect x="([0-9.]+)" y="([0-9.]+)" width="([0-9.]+)" height="([0-9.]+)"')
ICON_PATH_RE = re.compile(r'<path[^>]*class="[^"]*icon[^"]*"[^>]*d="([^"]+)"')
NUM_RE = re.compile(r'[-+]?[0-9]*\.?[0-9]+')
TEXT_RE = re.compile(r'<text[^>]*class="card-(title|sub)"[^>]*>(.*?)</text>')
LAYER_RE = re.compile(r'<rect x="([0-9.]+)" y="([0-9.]+)" width="([0-9.]+)" height="([0-9.]+)"[^>]*>?</rect>|<rect x="([0-9.]+)" y="([0-9.]+)" width="([0-9.]+)" height="([0-9.]+)"[^>]*/>')
GROUP_LABEL_RE = re.compile(r'<text[^>]*class="group-label"[^>]*>')
CONNECTOR_PATH_RE = re.compile(r'<path\b([^>]*)\bd="([^"]+)"[^>]*/?>')
CLASS_RE = re.compile(r'class="([^"]+)"')
CONNECTOR_CLASSES = {
    'edge', 'edge-dashed', 'line', 'bus', 'fanout', 'fanoutbus', 'fanin', 'faninbus'
}
PATH_TOKEN_RE = re.compile(r'[MLQHVZmlqhvz]|[-+]?(?:\d*\.)?\d+(?:[eE][-+]?\d+)?')
EPS = 1e-6


def fail(msg: str, issues: list[str]) -> None:
    issues.append(msg)



def _rect_values(match: re.Match) -> tuple[float, float, float, float]:
    groups = match.groups()
    vals = groups[:4] if groups[0] is not None else groups[4:]
    return tuple(float(v) for v in vals)  # type: ignore[return-value]




def _path_tokens(d: str) -> list[str]:
    return PATH_TOKEN_RE.findall(d.replace(',', ' '))


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
            points.append(cur)
        else:
            break
    return {
        'start': start,
        'end': cur if points else None,
        'first_dir': first_dir,
        'last_dir': last_dir,
        'segments': straight_segments,
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


def _connector_paths(svg: str) -> list[dict]:
    paths = []
    for idx, m in enumerate(CONNECTOR_PATH_RE.finditer(svg), start=1):
        attrs, d = m.groups()
        cm = CLASS_RE.search(attrs)
        if not cm:
            continue
        classes = set(cm.group(1).split())
        if not (classes & CONNECTOR_CLASSES):
            continue
        geom = _parse_path_geometry(d)
        geom['idx'] = idx
        geom['classes'] = ' '.join(sorted(classes & CONNECTOR_CLASSES))
        paths.append(geom)
    return paths


def _check_connector_rounding(svg: str, issues: list[str]) -> None:
    paths = _connector_paths(svg)
    # Same-path orthogonal turns should use a curve command.
    for p in paths:
        d = p['d']
        if p['has_curve']:
            continue
        pts = []
        for m in re.finditer(r'([ML])\s*([-+]?(?:\d*\.)?\d+),([-+]?(?:\d*\.)?\d+)', d):
            pts.append((float(m.group(2)), float(m.group(3))))
        for a, b, c in zip(pts, pts[1:], pts[2:]):
            o1, _a, _b = _axis_segment(a, b)
            o2, _c, _d = _axis_segment(b, c)
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
    layers: list[tuple[float, float, float, float]] = []
    for m in LAYER_RE.finditer(svg):
        x, y, w, h = _rect_values(m)
        after = svg[m.end(): m.end() + 220]
        if GROUP_LABEL_RE.search(after) and w >= 500 and h >= 120:
            layers.append((x, y, w, h))
    if len(layers) < 2:
        return
    layers.sort(key=lambda r: r[1])

    card_bounds: list[tuple[float, float]] = []
    for card in CARD_RE.findall(svg):
        rect = RECT_RE.search(card)
        if not rect:
            continue
        _x, y, _w, h = map(float, rect.groups())
        # If a card group has a translate(0,dy), account for it.
        # The CARD_RE content excludes the opening <g>, so search a small prefix
        # is not available; generated diagrams should avoid transforms, but old
        # hand-edited diagrams are still checked approximately.
        card_bounds.append((y, y + h))

    bottom_pads: list[float] = []
    for i, (_x, y, _w, h) in enumerate(layers):
        next_y = layers[i + 1][1] if i + 1 < len(layers) else y + h + 1
        contained = [b for a, b in card_bounds if y <= a < min(y + h + 30, next_y)]
        if contained:
            bottom_pads.append(round(y + h - max(contained), 1))
    if len(bottom_pads) >= 2 and max(bottom_pads) - min(bottom_pads) > 3:
        fail(f'inconsistent repeated-layer bottom padding: {bottom_pads}', issues)

    gaps = [round(layers[i + 1][1] - (layers[i][1] + layers[i][3]), 1) for i in range(len(layers) - 1)]
    if len(gaps) >= 2 and max(gaps) - min(gaps) > 3:
        fail(f'inconsistent repeated-layer gaps: {gaps}', issues)


def check(path: Path) -> list[str]:
    svg = path.read_text(encoding='utf-8-sig')
    issues: list[str] = []
    size = SVG_SIZE.search(svg)
    if not size:
        fail('missing svg width/height', issues)
        width = height = 0.0
    else:
        width, height = map(float, size.groups())

    for attr, value in ATTR.findall(svg):
        if value.startswith('#') or value in {'none'} or value.startswith('url(#'):
            if not HEX_OR_NONE.match(value):
                fail(f'invalid {attr} value: {value}', issues)
        elif value not in {'currentColor'}:
            # Named colors are avoided so semantic keys do not leak into SVG attrs.
            fail(f'non-portable {attr} value: {value}', issues)

    dashed_count = svg.count('edge-dashed') + svg.count('stroke-dasharray')
    if dashed_count > 8:
        fail(f'too many dashed relations ({dashed_count}); consider legend/containment instead', issues)

    for idx, card in enumerate(CARD_RE.findall(svg), start=1):
        rect = RECT_RE.search(card)
        if not rect:
            continue
        x, y, w, h = map(float, rect.groups())
        # Catch the failure mode where an icon path uses x as a y coordinate and
        # draws a line far outside the badge/card.
        for d in ICON_PATH_RE.findall(card):
            vals = [float(v) for v in NUM_RE.findall(d)]
            if not vals:
                continue
            max_span = max(max(vals) - min(vals), 0)
            if max_span > max(w, h) + 80:
                fail(f'card {idx} icon path has suspicious coordinate span: {max_span:.1f}', issues)
            if width and height:
                for v in vals:
                    if v < -20 or v > max(width, height) + 20:
                        fail(f'card {idx} icon path coordinate outside canvas: {v}', issues)
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
    _check_layer_metrics(svg, issues)

    if 'Unsupported markdown' in svg:
        fail('contains Unsupported markdown placeholder', issues)
    return issues


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
