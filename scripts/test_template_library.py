#!/usr/bin/env python3
"""Regression checks for bundled semantic diagram templates."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_style_gallery as gallery  # noqa: E402
import render_semantic_diagram as renderer  # noqa: E402
from semantic_diagram_types import supported_diagram_types  # noqa: E402
import validate_semantic_contract as contract_validator  # noqa: E402
import validate_semantic_svg as svg_validator  # noqa: E402


SVG_RE = re.compile(r"<svg\b.*?</svg>", re.S)
SVG_SIZE_RE = re.compile(r'<svg[^>]*width="([0-9.]+)"[^>]*height="([0-9.]+)"')


def fail(message: str) -> None:
    raise AssertionError(message)


def _render_gallery(contract_paths: list[Path]) -> str:
    previous_cwd = Path.cwd()
    try:
        os.chdir(ROOT)
        return gallery.render_gallery_html(contract_paths)
    finally:
        os.chdir(previous_cwd)


def _svg_height(svg: str) -> float:
    match = SVG_SIZE_RE.search(svg)
    if not match:
        fail("template SVG is missing width/height")
    return float(match.group(2))


def main() -> int:
    manifest_path = ROOT / "templates" / "template-gallery-baseline.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    entries = manifest["templates"]
    required_types = set(supported_diagram_types())
    seen_types = {entry["diagram_type"] for entry in entries}
    if seen_types != required_types:
        fail(f"template manifest types do not match supported types: {sorted(seen_types)}")

    variants_by_type: dict[str, set[str]] = {}
    contract_paths: list[Path] = []
    for entry in entries:
        diagram_type = entry["diagram_type"]
        variants_by_type.setdefault(diagram_type, set()).add(entry["variant"])
        contract_path = ROOT / entry["contract"]
        svg_path = ROOT / entry["svg"]
        contract_paths.append(Path(entry["contract"]))

        ok, messages = contract_validator.check(contract_path)
        if not ok:
            fail(f"{entry['contract']} failed contract validation: {messages}")

        contract = json.loads(contract_path.read_text(encoding="utf-8-sig"))
        if contract.get("diagram_type") != diagram_type:
            fail(f"{entry['contract']} has mismatched diagram_type")
        if contract.get("style") != entry["style"]:
            fail(f"{entry['contract']} has mismatched style")
        if contract.get("title") != entry["title"]:
            fail(f"{entry['contract']} has mismatched title")

        rendered_svg = renderer.render(contract, contract_path)
        expected_svg = svg_path.read_text(encoding="utf-8-sig") if svg_path.exists() else ""
        if rendered_svg.strip() != expected_svg.strip():
            fail(f"{entry['svg']} is stale; regenerate it from {entry['contract']}")

        issues = svg_validator.check_svg(expected_svg)
        if issues:
            fail(f"{entry['svg']} failed SVG QA: {issues}")
        if f'data-diagram-type="{diagram_type}"' not in expected_svg:
            fail(f"{entry['svg']} is missing expected diagram type")
        if f'data-style="{entry["style"]}"' not in expected_svg:
            fail(f"{entry['svg']} is missing expected style")
        if diagram_type == "hub_spoke" and entry["variant"] == "reference":
            if _svg_height(expected_svg) > float(entry.get("max_height", 99999)):
                fail(f"{entry['svg']} canvas is too tall")

    for diagram_type, variants in variants_by_type.items():
        if variants != {"minimal", "reference"}:
            fail(f"{diagram_type} should have minimal and reference templates")

    gallery_path = ROOT / manifest["gallery"]
    current_gallery = gallery_path.read_text(encoding="utf-8-sig") if gallery_path.exists() else ""
    expected_gallery = _render_gallery(contract_paths)
    if current_gallery.strip() != expected_gallery.strip():
        fail(f"{manifest['gallery']} is stale; regenerate it with scripts/build_style_gallery.py")
    if len(SVG_RE.findall(current_gallery)) != len(entries):
        fail("template gallery does not contain one SVG per template entry")

    print("template library selftest: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
