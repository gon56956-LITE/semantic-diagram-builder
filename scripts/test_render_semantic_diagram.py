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
    assert_valid("single-row layered example", layered)

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

    print("render_semantic_diagram selftest: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
