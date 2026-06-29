#!/usr/bin/env python3
"""Build a compact layout health report for bundled template SVGs."""
from __future__ import annotations

import html
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import validate_semantic_svg as validator


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "templates" / "template-gallery-baseline.json"

SVG_SIZE_RE = re.compile(r'<svg[^>]*\bwidth="([0-9.]+)"[^>]*\bheight="([0-9.]+)"')
TAG_RE = re.compile(r'<(rect|circle|line|path)\b([^>]*)/?>', re.S)
TEXT_RE = re.compile(r'<text\b([^>]*)>(.*?)</text>', re.S)
ATTR_RE = re.compile(r'([A-Za-z_:][\w:.-]*)="([^"]*)"')
STYLE_FONT_RE = re.compile(r'\bfont-size\s*:\s*([0-9.]+)px')


@dataclass(frozen=True)
class TemplateEntry:
    diagram_type: str
    variant: str
    title: str
    svg: Path
    contract: Path
    max_height: float | None = None


@dataclass(frozen=True)
class LayoutStats:
    entry: TemplateEntry
    width: float
    height: float
    content_bounds: tuple[float, float, float, float]
    right_whitespace: float
    bottom_whitespace: float
    card_count: int
    connector_count: int
    panel_count: int
    text_count: int
    text_chars: int
    ellipsis_count: int
    qa_issue_count: int
    risk_score: float
    notes: tuple[str, ...]

    @property
    def template_id(self) -> str:
        return f"{self.entry.diagram_type}/{self.entry.variant}"

    @property
    def ellipsis_ratio(self) -> float:
        return self.ellipsis_count / self.text_count if self.text_count else 0.0

    @property
    def text_density(self) -> float:
        area_units = max(1.0, (self.width * self.height) / 100_000.0)
        return self.text_chars / area_units


def _attrs(raw: str) -> dict[str, str]:
    return {name: value for name, value in ATTR_RE.findall(raw)}


def _number(attrs: dict[str, str], name: str, default: float = 0.0) -> float:
    try:
        return float(attrs.get(name, default))
    except ValueError:
        return default


def _style_font_size(attrs: dict[str, str], default: float = 16.0) -> float:
    match = STYLE_FONT_RE.search(attrs.get("style", ""))
    if not match:
        return default
    return float(match.group(1))


def _text_bounds(attrs: dict[str, str], raw_text: str) -> tuple[float, float, float, float] | None:
    if "x" not in attrs or "y" not in attrs:
        return None
    text = html.unescape(re.sub(r'<[^>]+>', '', raw_text)).strip()
    if not text:
        return None
    x = _number(attrs, "x")
    y = _number(attrs, "y")
    size = _style_font_size(attrs)
    width = len(text) * size * 0.56
    anchor = attrs.get("text-anchor", "start")
    if anchor == "middle":
        left = x - width / 2
    elif anchor == "end":
        left = x - width
    else:
        left = x
    return left, y - size, width, size * 1.35


def _path_bounds(d: str) -> tuple[float, float, float, float] | None:
    try:
        geom = validator._parse_path_geometry(d)  # type: ignore[attr-defined]
    except Exception:
        return None
    points = geom.get("points", [])
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def _add_bound(bounds: list[tuple[float, float, float, float]], bound: tuple[float, float, float, float] | None) -> None:
    if not bound:
        return
    x, y, w, h = bound
    if w <= 0 and h <= 0:
        return
    bounds.append((x, y, w, h))


def _content_bounds(svg: str, width: float, height: float) -> tuple[float, float, float, float]:
    stripped = re.sub(r'<defs\b.*?</defs>', '', svg, flags=re.S)
    stripped = re.sub(r'<style\b.*?</style>', '', stripped, flags=re.S)
    bounds: list[tuple[float, float, float, float]] = []

    for tag, raw_attrs in TAG_RE.findall(stripped):
        attrs = _attrs(raw_attrs)
        classes = set(attrs.get("class", "").split())
        if tag == "rect":
            x = _number(attrs, "x")
            y = _number(attrs, "y")
            w = _number(attrs, "width")
            h = _number(attrs, "height")
            if x <= 1 and y <= 1 and w >= width * 0.96 and h >= height * 0.96:
                continue
            if "grid" in classes or "background" in classes:
                continue
            _add_bound(bounds, (x, y, w, h))
        elif tag == "circle":
            cx = _number(attrs, "cx")
            cy = _number(attrs, "cy")
            r = _number(attrs, "r")
            _add_bound(bounds, (cx - r, cy - r, 2 * r, 2 * r))
        elif tag == "line":
            x1, y1 = _number(attrs, "x1"), _number(attrs, "y1")
            x2, y2 = _number(attrs, "x2"), _number(attrs, "y2")
            _add_bound(bounds, (min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1)))
        elif tag == "path":
            _add_bound(bounds, _path_bounds(attrs.get("d", "")))

    for raw_attrs, raw_text in TEXT_RE.findall(stripped):
        _add_bound(bounds, _text_bounds(_attrs(raw_attrs), raw_text))

    if not bounds:
        return 0.0, 0.0, width, height
    left = min(x for x, _y, _w, _h in bounds)
    top = min(y for _x, y, _w, _h in bounds)
    right = max(x + w for x, _y, w, _h in bounds)
    bottom = max(y + h for _x, y, _w, h in bounds)
    return left, top, max(0.0, right - left), max(0.0, bottom - top)


def _text_values(svg: str) -> list[str]:
    values = []
    for _attrs, raw_text in TEXT_RE.findall(svg):
        text = html.unescape(re.sub(r'<[^>]+>', '', raw_text)).strip()
        if text:
            values.append(text)
    return values


def _count_class(svg: str, class_name: str) -> int:
    return sum(1 for raw_classes in re.findall(r'\bclass="([^"]+)"', svg) if class_name in raw_classes.split())


def _risk_notes(
    entry: TemplateEntry,
    width: float,
    height: float,
    right_ws: float,
    bottom_ws: float,
    ellipsis_ratio: float,
    text_density: float,
    qa_issue_count: int,
) -> tuple[float, tuple[str, ...]]:
    score = 0.0
    notes: list[str] = []

    if qa_issue_count:
        score += qa_issue_count * 100.0
        notes.append(f"{qa_issue_count} SVG QA issue(s)")
    if entry.max_height is not None and height > entry.max_height:
        score += 80.0 + (height - entry.max_height) / 10.0
        notes.append(f"height above max_height {entry.max_height:g}px")
    if width > 2600:
        score += (width - 2600) / 20.0
        notes.append("very wide canvas")
    if height > 1800:
        score += (height - 1800) / 20.0
        notes.append("very tall canvas")

    right_limit = max(180.0, width * 0.16)
    bottom_limit = max(160.0, height * 0.14)
    if right_ws > right_limit:
        score += (right_ws - right_limit) / 12.0
        notes.append(f"right whitespace {right_ws:.0f}px")
    if bottom_ws > bottom_limit:
        score += (bottom_ws - bottom_limit) / 12.0
        notes.append(f"bottom whitespace {bottom_ws:.0f}px")

    if ellipsis_ratio >= 0.20:
        score += ellipsis_ratio * 80.0
        notes.append(f"ellipsis ratio {ellipsis_ratio:.0%}")
    if text_density > 260:
        score += (text_density - 260) / 4.0
        notes.append(f"text density {text_density:.0f}")
    if not notes:
        notes.append("ok")
    return score, tuple(notes)


def _read_entries(manifest_path: Path = MANIFEST) -> list[TemplateEntry]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    entries: list[TemplateEntry] = []
    seen: set[str] = set()
    for section_name in ("templates", "gallery_templates"):
        for raw in manifest.get(section_name, []):
            svg = raw["svg"]
            if svg in seen:
                continue
            seen.add(svg)
            entries.append(
                TemplateEntry(
                    diagram_type=str(raw["diagram_type"]),
                    variant=str(raw["variant"]),
                    title=str(raw["title"]),
                    svg=ROOT / svg,
                    contract=ROOT / raw["contract"],
                    max_height=float(raw["max_height"]) if "max_height" in raw else None,
                )
            )
    return entries


def scan_entry(entry: TemplateEntry) -> LayoutStats:
    svg = entry.svg.read_text(encoding="utf-8-sig")
    size_match = SVG_SIZE_RE.search(svg)
    if not size_match:
        raise ValueError(f"{entry.svg.relative_to(ROOT)} is missing width/height")
    width, height = map(float, size_match.groups())
    left, top, content_w, content_h = _content_bounds(svg, width, height)
    right_ws = max(0.0, width - (left + content_w))
    bottom_ws = max(0.0, height - (top + content_h))
    text_values = _text_values(svg)
    ellipsis_count = sum(text.count("...") for text in text_values)
    qa_issue_count = len(validator.check_svg(svg))
    risk_score, notes = _risk_notes(
        entry,
        width,
        height,
        right_ws,
        bottom_ws,
        ellipsis_count / len(text_values) if text_values else 0.0,
        sum(len(text) for text in text_values) / max(1.0, (width * height) / 100_000.0),
        qa_issue_count,
    )
    return LayoutStats(
        entry=entry,
        width=width,
        height=height,
        content_bounds=(left, top, content_w, content_h),
        right_whitespace=right_ws,
        bottom_whitespace=bottom_ws,
        card_count=_count_class(svg, "card"),
        connector_count=_count_class(svg, "edge") + _count_class(svg, "capability-map-link"),
        panel_count=_count_class(svg, "info-panel"),
        text_count=len(text_values),
        text_chars=sum(len(text) for text in text_values),
        ellipsis_count=ellipsis_count,
        qa_issue_count=qa_issue_count,
        risk_score=risk_score,
        notes=notes,
    )


def scan_templates(entries: list[TemplateEntry] | None = None) -> list[LayoutStats]:
    return [scan_entry(entry) for entry in (entries or _read_entries())]


def _fmt_num(value: float) -> str:
    return f"{value:.0f}"


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def render_report(stats: list[LayoutStats]) -> str:
    ranked = sorted(stats, key=lambda item: (-item.risk_score, item.template_id))
    top_rows = [
        [
            str(idx),
            item.template_id,
            _fmt_num(item.risk_score),
            "; ".join(item.notes),
        ]
        for idx, item in enumerate(ranked[:8], start=1)
    ]
    summary_rows = [
        [
            item.template_id,
            f"{_fmt_num(item.width)}x{_fmt_num(item.height)}",
            f"{_fmt_num(item.content_bounds[2])}x{_fmt_num(item.content_bounds[3])}",
            f"{_fmt_num(item.right_whitespace)}/{_fmt_num(item.bottom_whitespace)}",
            str(item.card_count),
            str(item.connector_count),
            str(item.panel_count),
            f"{item.text_count}/{item.text_chars}",
            f"{item.ellipsis_count} ({item.ellipsis_ratio:.0%})",
            str(item.qa_issue_count),
            "; ".join(item.notes),
        ]
        for item in sorted(stats, key=lambda item: item.template_id)
    ]

    return "\n".join(
        [
            "# Template Layout Report",
            "",
            "Generated by `py scripts/report_template_layout.py templates/template-layout-report.md`.",
            "",
            "## Top Layout Risks",
            "",
            _markdown_table(["Rank", "Template", "Risk", "Notes"], top_rows),
            "",
            "## Template Metrics",
            "",
            _markdown_table(
                [
                    "Template",
                    "Canvas",
                    "Content",
                    "Whitespace R/B",
                    "Cards",
                    "Lines",
                    "Panels",
                    "Text Cnt/Chars",
                    "Ellipsis",
                    "QA",
                    "Notes",
                ],
                summary_rows,
            ),
            "",
        ]
    )


def build_report(output_path: Path) -> None:
    output = render_report(scan_templates())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output, encoding="utf-8", newline="\n")


def main(argv: list[str]) -> int:
    if len(argv) > 2:
        print("Usage: report_template_layout.py [output.md]", file=sys.stderr)
        return 2
    output = render_report(scan_templates())
    if len(argv) == 2:
        output_path = Path(argv[1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8", newline="\n")
        print(f"wrote {output_path}")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
