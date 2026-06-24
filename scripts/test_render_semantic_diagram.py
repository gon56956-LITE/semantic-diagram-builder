#!/usr/bin/env python3
"""Regression checks for render_semantic_diagram.py."""
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
validator = load_module("validate_semantic_svg", ROOT / "scripts" / "validate_semantic_svg.py")


def load_contract(name: str) -> dict:
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8-sig"))


def assert_valid(name: str, contract: dict) -> str:
    svg = renderer.render(contract)
    issues = validator.check_svg(svg)
    if issues:
        raise AssertionError(f"{name} should validate, got: {issues}")
    return svg


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


def assert_rounded_paths(svg: str, required_classes: set[str], label: str) -> None:
    paths = path_ds(svg, required_classes)
    if not paths:
        raise AssertionError(f"{label} path was not rendered")
    for d in paths:
        if ' Q ' not in d:
            raise AssertionError(f"{label} should use a rounded Q elbow, got: {d}")


def text_font_sizes(svg: str, class_name: str) -> list[float]:
    sizes = []
    for attrs in re.findall(r'<text\b([^>]*)>', svg):
        class_match = re.search(r'class="([^"]+)"', attrs)
        style_match = re.search(r'font-size:([0-9.]+)px', attrs)
        if not class_match or not style_match:
            continue
        if class_name in class_match.group(1).split():
            sizes.append(float(style_match.group(1)))
    return sizes


def css_font_size(svg: str, class_name: str) -> float:
    match = re.search(rf'\.{re.escape(class_name)}\{{font:[^}}]*?([0-9.]+)px', svg)
    if not match:
        raise AssertionError(f"missing CSS font size for {class_name}")
    return float(match.group(1))


def assert_card_type_scale(label: str, svg: str) -> None:
    title_sizes = text_font_sizes(svg, "card-title")
    sub_sizes = text_font_sizes(svg, "card-sub")
    if not title_sizes or min(title_sizes) < 20.5:
        raise AssertionError(f"{label} card titles should use canvas-aware readable font sizes")
    if max(title_sizes) - min(title_sizes) > 0.2:
        raise AssertionError(f"{label} card titles should use one diagram-level font scale")
    if max(title_sizes) > 23.5:
        raise AssertionError(f"{label} card titles should not grow with individual card width")
    if not sub_sizes or min(sub_sizes) < 15.5:
        raise AssertionError(f"{label} card subtitles should use canvas-aware readable font sizes")
    if max(sub_sizes) - min(sub_sizes) > 0.2:
        raise AssertionError(f"{label} card subtitles should use one diagram-level font scale")
    if max(sub_sizes) > 17.5:
        raise AssertionError(f"{label} card subtitles should not grow with individual card width")


def assert_table_scale(svg: str) -> None:
    header_sizes = text_font_sizes(svg, "table-header")
    cell_sizes = text_font_sizes(svg, "table-cell") + text_font_sizes(svg, "table-cell-secondary")
    if not header_sizes or min(header_sizes) < 15:
        raise AssertionError("registry_table headers should be readable at gallery scale")
    if not cell_sizes or min(cell_sizes) < 16:
        raise AssertionError("registry_table cells should be readable at gallery scale")
    for kind in ("capability", "source", "risk", "package"):
        if f'data-kind="{kind}"' not in svg:
            raise AssertionError(f"registry_table should render semantic badges for {kind}")


def assert_hub_spoke_design(svg: str) -> None:
    if 'class="hub-core card"' not in svg:
        raise AssertionError("hub_spoke should render a designed central hub core")
    if svg.count('class="hub-spoke-node spoke-block card"') < 4:
        raise AssertionError("hub_spoke should render designed spoke blocks instead of generic cards")
    if 'class="edge hub-spoke-link"' not in svg and 'hub-spoke-link' not in svg:
        raise AssertionError("hub_spoke should render explicit hub-spoke connector links")
    title_sizes = text_font_sizes(svg, "card-title")
    sub_sizes = text_font_sizes(svg, "card-sub")
    if not title_sizes or min(title_sizes) < 18:
        raise AssertionError("hub_spoke labels should remain readable")
    if not sub_sizes or min(sub_sizes) < 13.5:
        raise AssertionError("hub_spoke subtitles should remain readable")


def q_turns(svg: str, required_classes: set[str]) -> list[tuple[float, float, float]]:
    turns = []
    pattern = re.compile(
        r'M ([-0-9.]+) ([-0-9.]+) L ([-0-9.]+) ([-0-9.]+) '
        r'Q ([-0-9.]+) ([-0-9.]+) ([-0-9.]+) ([-0-9.]+)'
    )
    for d in path_ds(svg, required_classes):
        m = pattern.search(d)
        if not m:
            raise AssertionError(f"rounded path shape was not recognized: {d}")
        turns.append((float(m.group(1)), float(m.group(5)), float(m.group(7))))
    return turns


def main() -> int:
    layered = load_contract("ocs-r300-layered-contract.json")
    layered_svg = assert_valid("single-row layered example", layered)
    if 'data-diagram-type="layered_knowledge_topology"' not in layered_svg:
        raise AssertionError("layered example should declare the standard diagram type")
    assert_card_type_scale("layered", layered_svg)
    if css_font_size(layered_svg, "group-label") < 15:
        raise AssertionError("layer labels should be readable at gallery scale")
    if css_font_size(layered_svg, "note") < 14:
        raise AssertionError("legend/footer notes should be readable at gallery scale")

    legacy = copy.deepcopy(layered)
    legacy.pop("diagram_type", None)
    legacy["layout"] = "layered"
    legacy_warnings = renderer.contract_warnings(legacy)
    if not any("deprecated" in warning and "layered_knowledge_topology" in warning for warning in legacy_warnings):
        raise AssertionError("legacy layout should be accepted with a deprecation warning")

    conflict = copy.deepcopy(layered)
    conflict["diagram_type"] = "source_boundary_map"
    conflict["layout"] = "layered"
    conflict_warnings = renderer.contract_warnings(conflict)
    if not any("takes precedence" in warning for warning in conflict_warnings):
        raise AssertionError("diagram_type should take precedence over conflicting layout")

    unknown = copy.deepcopy(layered)
    unknown["diagram_type"] = "unknown_type"
    try:
        renderer.render(unknown)
    except renderer.DiagramTypeError:
        pass
    else:
        raise AssertionError("unknown diagram_type should fail explicitly")

    multi = load_contract("ocs-r300-multirrow-contract.json")
    svg = assert_valid("multi-row routed example", multi)
    if 'class="edge fanout route-shared bus"' not in svg:
        raise AssertionError("multi-row fan-out bus was not rendered")
    if 'class="edge fanin route-shared bus"' not in svg:
        raise AssertionError("multi-row fan-in bus was not rendered")
    if 'marker-end="url(#arrow-fanout)"' not in svg or 'marker-end="url(#arrow-fanin)"' not in svg:
        raise AssertionError("terminal fan-out/fan-in arrows were not rendered")
    assert_rounded_paths(svg, {"fanout", "terminal"}, "fan-out terminal")
    assert_rounded_paths(svg, {"fanout", "branch"}, "fan-out source branch")
    assert_rounded_paths(svg, {"fanin", "merge"}, "fan-in terminal merge")
    assert_rounded_paths(svg, {"fanin", "branch"}, "fan-in row bus branch")
    assert_rounded_paths(svg, {"route-shared", "trunk"}, "side trunk")

    fanout_source_turns = q_turns(svg, {"fanout", "branch"})
    if not any(end_x < turn_x for _start_x, turn_x, end_x in fanout_source_turns):
        raise AssertionError("center fan-out source should round into the left bus segment")
    if not any(end_x > turn_x for _start_x, turn_x, end_x in fanout_source_turns):
        raise AssertionError("center fan-out source should round into the right bus segment")

    fanout_turns = q_turns(svg, {"fanout", "terminal"})
    if not any(start_x > turn_x for start_x, turn_x, _end_x in fanout_turns):
        raise AssertionError("left-of-source fan-out terminals should round in from the right")
    if not any(start_x < turn_x for start_x, turn_x, _end_x in fanout_turns):
        raise AssertionError("right-of-source fan-out terminals should round in from the left")

    fanin_branch_turns = q_turns(svg, {"fanin", "branch"})
    if not all(end_x < turn_x for _start_x, turn_x, end_x in fanin_branch_turns):
        raise AssertionError("left-side fan-in branches should round toward the left trunk")
    fanin_merge_turns = q_turns(svg, {"fanin", "merge"})
    if not any(start_x < turn_x for start_x, turn_x, _end_x in fanin_merge_turns):
        raise AssertionError("center fan-in target should merge from the left bus segment")
    if not any(start_x > turn_x for start_x, turn_x, _end_x in fanin_merge_turns):
        raise AssertionError("center fan-in target should merge from the right bus segment")

    model = renderer.build_layout_model(multi)
    positions = model["positions"]
    if positions["faceplate"][1] <= positions["mems"][1]:
        raise AssertionError("explicit row field did not place faceplate on a lower row")
    if positions["mech"][0] <= positions["faceplate"][0]:
        raise AssertionError("explicit col field did not order lower-row nodes")
    if model["group_layouts"]["subkb"]["mode"] != "row_bus_side_trunk":
        raise AssertionError("multi-row routed group did not select row_bus_side_trunk")

    face_x, face_bottom = renderer.center_bottom(positions["faceplate"])
    target_x, target_top = renderer.center_top(positions["controlled_sources"])
    direct_path = renderer._vertical_branch(face_x, face_bottom, target_top)
    if direct_path not in path_ds(svg, {"fanin", "terminal"}):
        raise AssertionError("vertically aligned fan-in source should connect directly to the target")
    direct_source_prefix = f"M {face_x} {face_bottom} "
    if any(d.startswith(direct_source_prefix) for d in path_ds(svg, {"fanin", "branch"})):
        raise AssertionError("vertically aligned fan-in source should not bend into the side bus")

    simple = copy.deepcopy(multi)
    for group in simple["groups"]:
        if group["id"] == "subkb":
            group["routing"]["mode"] = "simple"
    simple_svg = renderer.render(simple)
    if 'class="edge fanout route-shared bus"' in simple_svg or 'class="edge fanin route-shared bus"' in simple_svg:
        raise AssertionError("routing.mode=simple should not emit row-level buses")

    registry = load_contract("registry-table-contract.json")
    registry_svg = assert_valid("registry table example", registry)
    if 'data-diagram-type="registry_table"' not in registry_svg or 'class="table-header"' not in registry_svg:
        raise AssertionError("registry_table should render table headers and declare its diagram type")
    if 'class="card node-card"' in registry_svg:
        raise AssertionError("registry_table should render as a table, not as grouped cards")
    assert_table_scale(registry_svg)

    tree = load_contract("taxonomy-tree-contract.json")
    tree_svg = assert_valid("taxonomy tree example", tree)
    if 'data-diagram-type="taxonomy_tree"' not in tree_svg or 'class="edge taxonomy-link"' not in tree_svg:
        raise AssertionError("taxonomy_tree should render parent-child connectors")
    assert_card_type_scale("taxonomy_tree", tree_svg)
    if css_font_size(tree_svg, "tree-level-label") < 15:
        raise AssertionError("taxonomy level labels should be readable at gallery scale")
    conflict_tree = copy.deepcopy(tree)
    conflict_tree["edges"] = [{"from": "maps", "to": "glossary", "relation": "parent"}]
    try:
        renderer.contract_warnings(conflict_tree)
    except renderer.DiagramTypeError:
        pass
    else:
        raise AssertionError("taxonomy_tree parent conflicts should fail")

    hub = load_contract("hub-spoke-contract.json")
    hub_svg = assert_valid("hub-spoke example", hub)
    if 'data-diagram-type="hub_spoke"' not in hub_svg or 'id="node-hub"' not in hub_svg:
        raise AssertionError("hub_spoke should render the declared hub")
    if 'edge-dashed' not in hub_svg:
        raise AssertionError("hub_spoke should preserve dashed spoke style")
    assert_hub_spoke_design(hub_svg)
    size_match = re.search(r'<svg[^>]*height="([0-9.]+)"', hub_svg)
    if not size_match or float(size_match.group(1)) > 720:
        raise AssertionError("hub_spoke should use a compact content-driven canvas height")

    print("render_semantic_diagram selftest: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
