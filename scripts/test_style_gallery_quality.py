#!/usr/bin/env python3
"""Regression checks for the semantic diagram style gallery."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_style_gallery as gallery  # noqa: E402
import validate_semantic_svg as validator  # noqa: E402


SVG_RE = re.compile(r"<svg\b.*?</svg>", re.S)
SVG_SIZE_RE = re.compile(r'<svg[^>]*width="([0-9.]+)"[^>]*height="([0-9.]+)"')


def fail(message: str) -> None:
    raise AssertionError(message)


def _render_expected(contract_paths: list[Path]) -> str:
    previous_cwd = Path.cwd()
    try:
        os.chdir(ROOT)
        return gallery.render_gallery_html(contract_paths)
    finally:
        os.chdir(previous_cwd)


def _svg_size(svg: str) -> tuple[float, float]:
    match = SVG_SIZE_RE.search(svg)
    if not match:
        fail("gallery svg is missing width/height")
    return float(match.group(1)), float(match.group(2))


def main() -> int:
    baseline_path = ROOT / "examples" / "style-gallery-baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8-sig"))
    contracts = baseline["contracts"]
    contract_paths = [Path(entry["path"]) for entry in contracts]

    gallery_path = ROOT / baseline["gallery"]
    current = gallery_path.read_text(encoding="utf-8-sig")
    rendered = _render_expected(contract_paths)
    if current.strip() != rendered.strip():
        fail("style gallery is stale; regenerate it with scripts/build_style_gallery.py")

    if re.search(r"<script\b", current, re.I):
        fail("style gallery should not contain scripts")
    if re.search(r'\b(?:href|src)="https?://', current, re.I):
        fail("style gallery should not depend on remote assets")

    svgs = SVG_RE.findall(current)
    if len(svgs) != len(contracts):
        fail(f"expected {len(contracts)} gallery SVGs, found {len(svgs)}")

    for entry, svg in zip(contracts, svgs):
        expected_style = entry["style"]
        expected_type = entry["diagram_type"]
        expected_title = entry["title"]

        if f'data-style="{expected_style}"' not in svg:
            fail(f"{entry['path']} is missing data-style={expected_style}")
        if f'data-diagram-type="{expected_type}"' not in svg:
            fail(f"{entry['path']} is missing data-diagram-type={expected_type}")
        if f'aria-label="{expected_title}"' not in svg:
            fail(f"{entry['path']} is missing expected aria-label")
        if 'fill="context-stroke"' in svg or 'markerUnits="userSpaceOnUse"' not in svg:
            fail(f"{entry['path']} should use explicit, user-space arrow markers")

        issues = validator.check_svg(svg)
        if issues:
            fail(f"{entry['path']} failed SVG QA: {issues}")

        if expected_style == "accent-blueprint":
            if 'id="blueprint-grid"' not in svg or 'fill="#062B5F"' not in svg:
                fail(f"{entry['path']} is missing the Accent Blueprint grid/background")
        if expected_type == "registry_table":
            if 'class="table-badge semantic-badge"' not in svg or "data-kind=" not in svg:
                fail("registry_table gallery example should include semantic badges")
        if expected_type == "hub_spoke":
            if 'class="hub-core card"' not in svg or 'class="hub-spoke-node spoke-block card"' not in svg:
                fail("hub_spoke gallery example should use designed hub/spoke components")
            _width, height = _svg_size(svg)
            if height > float(entry.get("max_height", 99999)):
                fail(f"hub_spoke gallery canvas is too tall: {height:g}px")

    print("style gallery quality: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
