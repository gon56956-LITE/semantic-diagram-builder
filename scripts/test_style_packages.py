#!/usr/bin/env python3
"""Regression checks for semantic diagram style packages."""
from __future__ import annotations

import copy
import importlib.util
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


renderer = load_module("render_semantic_diagram", ROOT / "scripts" / "render_semantic_diagram.py")
gallery = load_module("build_style_gallery", ROOT / "scripts" / "build_style_gallery.py")


def load_contract(name: str) -> dict:
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8-sig"))


def path_ds(svg: str, required_classes: set[str]) -> list[str]:
    matches = []
    for attrs in re.findall(r'<path\b([^>]*)/?>', svg):
        class_match = re.search(r'class="([^"]+)"', attrs)
        d_match = re.search(r'\bd="([^"]+)"', attrs)
        if not class_match or not d_match:
            continue
        classes = set(class_match.group(1).split())
        if required_classes <= classes:
            matches.append(d_match.group(1))
    return matches


def main() -> int:
    modern = renderer.load_style_package("modern-tech")
    accent = renderer.load_style_package("accent-blueprint")
    if modern["id"] != "modern-tech" or accent["id"] != "accent-blueprint":
        raise AssertionError("built-in style ids did not load correctly")

    multi = load_contract("ocs-r300-multirrow-contract.json")
    modern_model = renderer.build_layout_model(copy.deepcopy(multi))
    accent_contract = copy.deepcopy(multi)
    accent_contract["style"] = "accent-blueprint"
    accent_model = renderer.build_layout_model(accent_contract)
    if modern_model["positions"] != accent_model["positions"]:
        raise AssertionError("style packages should not change layout geometry with equal metrics")
    if modern_model["group_boxes"] != accent_model["group_boxes"]:
        raise AssertionError("style packages should not change group geometry with equal metrics")

    accent_svg = renderer.render(accent_contract)
    for required in (
        'data-style="accent-blueprint"',
        'id="blueprint-grid"',
        '#062B5F',
        '#F4F8FF',
        '#FF9F2E',
        '#6EE66E',
        'fill="context-stroke"',
        '[data-style="accent-blueprint"] .card-title',
    ):
        if required not in accent_svg:
            raise AssertionError(f"accent-blueprint SVG missing {required}")

    boundary = load_contract("accent-blueprint-boundary-contract.json")
    boundary_model = renderer.build_layout_model(boundary)
    boundary_svg = renderer.render(boundary)
    module_x, module_top = renderer.center_top(boundary_model["positions"]["module_b"])
    row = boundary_model["group_layouts"]["assets"]["assignments"]["module_b"][0]
    bus_y = boundary_model["group_layouts"]["assets"]["rows"][row]["fanout_bus_y"]
    direct_module_path = renderer._vertical_branch(module_x, bus_y, module_top)
    fanout_terminals = path_ds(boundary_svg, {"fanout", "terminal"})
    if direct_module_path not in fanout_terminals:
        raise AssertionError("center-aligned fan-out target should use a straight vertical terminal")
    module_suffix = f"L {module_x} {module_top}"
    if any(" Q " in d and d.endswith(module_suffix) for d in fanout_terminals):
        raise AssertionError("center-aligned fan-out target should not receive a rounded bus elbow")

    missing = copy.deepcopy(multi)
    missing.pop("style", None)
    try:
        renderer.render(missing)
    except renderer.StyleError:
        pass
    else:
        raise AssertionError("missing style should raise StyleError")

    relative_contract = copy.deepcopy(multi)
    relative_contract["style"] = "../styles/modern-tech/style.json"
    relative_svg = renderer.render(relative_contract, ROOT / "examples" / "relative-contract.json")
    if 'data-style="modern-tech"' not in relative_svg:
        raise AssertionError("relative style path did not load")

    invalid = copy.deepcopy(modern)
    invalid.pop("_path", None)
    invalid["tokens"]["colors"]["background"] = "blue"
    try:
        renderer.validate_style_package(invalid)
    except renderer.StyleError:
        pass
    else:
        raise AssertionError("invalid color token should raise StyleError")

    gallery_html = gallery.render_gallery_html([
        ROOT / "examples" / "accent-blueprint-boundary-contract.json",
        ROOT / "examples" / "registry-table-contract.json",
        ROOT / "examples" / "taxonomy-tree-contract.json",
        ROOT / "examples" / "hub-spoke-contract.json",
    ])
    if "accent-blueprint" not in gallery_html or "<svg" not in gallery_html:
        raise AssertionError("style gallery did not embed rendered SVG")
    for diagram_type in ("source_boundary_map", "registry_table", "taxonomy_tree", "hub_spoke"):
        if f'data-diagram-type="{diagram_type}"' not in gallery_html:
            raise AssertionError(f"style gallery missing {diagram_type}")

    print("style package selftest: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
