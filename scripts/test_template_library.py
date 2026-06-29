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
import report_template_layout as layout_report  # noqa: E402
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


def _check_layout_report_scoring() -> None:
    dense_entry = layout_report.TemplateEntry(
        diagram_type="example",
        variant="stress",
        title="Dense Stress",
        svg=Path("dense.svg"),
        contract=Path("dense-contract.json"),
        max_height=1000,
    )
    dense_score, dense_notes = layout_report._risk_notes(  # noqa: SLF001
        dense_entry,
        width=1200,
        height=1100,
        content_w=1100,
        content_h=1040,
        right_ws=40,
        bottom_ws=20,
        ellipsis_ratio=0.0,
        text_density=80,
        qa_issue_count=0,
    )
    if dense_score != 0 or not any("dense but acceptable" in note for note in dense_notes):
        fail("height above max_height without redundancy should be a review note, not a compression priority")

    redundant_score, redundant_notes = layout_report._risk_notes(  # noqa: SLF001
        dense_entry,
        width=1200,
        height=1100,
        content_w=900,
        content_h=700,
        right_ws=40,
        bottom_ws=240,
        ellipsis_ratio=0.0,
        text_density=80,
        qa_issue_count=0,
    )
    if redundant_score <= 0 or not any("vertical redundancy" in note for note in redundant_notes):
        fail("height above max_height should rank only when vertical redundancy is present")


def main() -> int:
    _check_layout_report_scoring()

    manifest_path = ROOT / "templates" / "template-gallery-baseline.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    required_types = set(supported_diagram_types())

    for diagram_type in sorted(required_types):
        for variant in ("minimal", "reference", "stress"):
            contract_path = ROOT / "templates" / diagram_type / f"{variant}-contract.json"
            svg_path = ROOT / "templates" / diagram_type / f"{variant}.svg"
            if not contract_path.exists():
                fail(f"missing template contract: {contract_path.relative_to(ROOT)}")
            if not svg_path.exists():
                fail(f"missing template SVG: {svg_path.relative_to(ROOT)}")

            ok, messages = contract_validator.check(contract_path)
            if not ok:
                fail(f"{contract_path.relative_to(ROOT)} failed contract validation: {messages}")

            contract = json.loads(contract_path.read_text(encoding="utf-8-sig"))
            if contract.get("diagram_type") != diagram_type:
                fail(f"{contract_path.relative_to(ROOT)} has mismatched diagram_type")

            rendered_svg = renderer.render(contract, contract_path)
            expected_svg = svg_path.read_text(encoding="utf-8-sig")
            if rendered_svg.strip() != expected_svg.strip():
                fail(f"{svg_path.relative_to(ROOT)} is stale; regenerate it from {contract_path.relative_to(ROOT)}")

            issues = svg_validator.check_svg(expected_svg)
            if issues:
                fail(f"{svg_path.relative_to(ROOT)} failed SVG QA: {issues}")
            if f'data-diagram-type="{diagram_type}"' not in expected_svg:
                fail(f"{svg_path.relative_to(ROOT)} is missing expected diagram type")
            if f'data-style="{contract["style"]}"' not in expected_svg:
                fail(f"{svg_path.relative_to(ROOT)} is missing expected style")

    gallery_entries = manifest.get("gallery_templates", manifest["templates"])
    seen_types = {entry["diagram_type"] for entry in gallery_entries}
    if seen_types != required_types:
        fail(f"template gallery types do not match supported types: {sorted(seen_types)}")

    gallery_variants: dict[str, set[str]] = {}
    contract_paths: list[Path] = []
    for entry in gallery_entries:
        diagram_type = entry["diagram_type"]
        gallery_variants.setdefault(diagram_type, set()).add(entry["variant"])
        contract_path = ROOT / entry["contract"]
        svg_path = ROOT / entry["svg"]
        contract_paths.append(Path(entry["contract"]))
        contract = json.loads(contract_path.read_text(encoding="utf-8-sig"))
        if contract.get("style") != entry["style"]:
            fail(f"{entry['contract']} has mismatched style")
        if contract.get("title") != entry["title"]:
            fail(f"{entry['contract']} has mismatched title")
        if entry["variant"] == "minimal":
            fail("template gallery should use reference/stress entries, not minimal entries")
        if diagram_type == "hub_spoke" and _svg_height(svg_path.read_text(encoding="utf-8-sig")) > float(entry.get("max_height", 99999)):
            fail(f"{entry['svg']} canvas is too tall")

    for diagram_type, variants in gallery_variants.items():
        if variants != {"reference", "stress"}:
            fail(f"{diagram_type} gallery should include reference and stress templates")

    gallery_path = ROOT / manifest["gallery"]
    current_gallery = gallery_path.read_text(encoding="utf-8-sig") if gallery_path.exists() else ""
    expected_gallery = _render_gallery(contract_paths)
    if current_gallery.strip() != expected_gallery.strip():
        fail(f"{manifest['gallery']} is stale; regenerate it with scripts/build_style_gallery.py")
    if len(SVG_RE.findall(current_gallery)) != len(gallery_entries):
        fail("template gallery does not contain one SVG per template entry")

    report_path = ROOT / "templates" / "template-layout-report.md"
    current_report = report_path.read_text(encoding="utf-8-sig") if report_path.exists() else ""
    expected_report = layout_report.render_report(layout_report.scan_templates())
    if current_report.strip() != expected_report.strip():
        fail("template-layout-report.md is stale; regenerate it with scripts/report_template_layout.py")
    if "## Height Diagnostics" not in expected_report:
        fail("template layout report should include height source diagnostics")
    if "capability_domain_map/stress" not in expected_report or "height driven by content rows, not whitespace" not in expected_report:
        fail("template layout report should explain dense capability map height drivers")
    if "relationship_matrix/stress" not in expected_report or "height driven by matrix rows and companion panels" not in expected_report:
        fail("template layout report should explain dense relationship matrix height drivers")
    if "## Truncation Diagnostics" not in expected_report:
        fail("template layout report should include truncation diagnostics")
    if "relationship_matrix/stress" not in expected_report or "compact-fit:matrix-preview" not in expected_report:
        fail("template layout report should classify matrix truncation as compact-fit")
    if "semantic-review:card-title" in expected_report:
        fail("template layout report should not contain high-semantic card title truncation in bundled templates")
    if "taxonomy_tree/stress" not in expected_report or "context-review:card-sub" not in expected_report:
        fail("template layout report should keep context-level subtitle truncation visible for review")

    print("template library selftest: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
