#!/usr/bin/env python3
"""Regression checks for semantic diagram contract schema validation."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import render_semantic_diagram as renderer  # noqa: E402
import validate_semantic_contract as contract_cli  # noqa: E402


def load_contract(name: str) -> dict:
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8-sig"))


def assert_schema_pass(name: str, contract: dict) -> None:
    try:
        renderer.contract_warnings(contract, ROOT / "examples" / f"{name}.json")
    except renderer.DiagramTypeError as exc:
        raise AssertionError(f"{name} should pass schema validation, got: {exc}") from exc


def assert_schema_error(name: str, contract: dict, expected: str) -> None:
    try:
        renderer.contract_warnings(contract, ROOT / "examples" / f"{name}.json")
    except renderer.DiagramTypeError as exc:
        if expected not in str(exc):
            raise AssertionError(f"{name} should fail with {expected!r}, got: {exc}") from exc
    else:
        raise AssertionError(f"{name} should fail with {expected!r}")


def main() -> int:
    examples = [
        "ocs-r300-layered-contract.json",
        "ocs-r300-multirrow-contract.json",
        "accent-blueprint-boundary-contract.json",
        "registry-table-contract.json",
        "taxonomy-tree-contract.json",
        "hub-spoke-contract.json",
    ]
    for example in examples:
        assert_schema_pass(example, load_contract(example))

    ok, messages = contract_cli.check(ROOT / "examples" / "hub-spoke-contract.json")
    if not ok:
        raise AssertionError(f"contract-only validator should pass bundled examples, got: {messages}")

    layered = load_contract("ocs-r300-layered-contract.json")
    legacy = copy.deepcopy(layered)
    legacy.pop("diagram_type", None)
    legacy["layout"] = "layered"
    warnings = renderer.contract_warnings(legacy)
    if not any("deprecated" in warning for warning in warnings):
        raise AssertionError("legacy layout should pass schema validation with a deprecation warning")

    bad_group = copy.deepcopy(layered)
    bad_group["nodes"][0]["group"] = "missing"
    assert_schema_error("grouped node missing group", bad_group, "is not declared in groups")

    bad_edge = copy.deepcopy(layered)
    bad_edge["edges"][0]["to"] = "missing"
    assert_schema_error("grouped edge missing endpoint", bad_edge, "is not a node id")

    bad_coord = copy.deepcopy(layered)
    bad_coord["nodes"][0]["row"] = -1
    assert_schema_error("grouped negative row", bad_coord, "must be a non-negative integer")

    registry = load_contract("registry-table-contract.json")
    registry_with_nodes = copy.deepcopy(registry)
    registry_with_nodes["nodes"] = [{"id": "n", "label": "N"}]
    assert_schema_error("registry mixed nodes", registry_with_nodes, 'does not support top-level "nodes"')

    registry_missing_key = copy.deepcopy(registry)
    del registry_missing_key["rows"][0]["related"]
    assert_schema_error("registry missing column", registry_missing_key, "is missing column keys")

    registry_unknown_key = copy.deepcopy(registry)
    registry_unknown_key["rows"][0]["typo"] = "extra"
    assert_schema_error("registry unknown column", registry_unknown_key, "unknown column keys")

    taxonomy = load_contract("taxonomy-tree-contract.json")
    taxonomy_no_links = copy.deepcopy(taxonomy)
    for node in taxonomy_no_links["nodes"]:
        node.pop("parent", None)
    assert_schema_error("taxonomy no links", taxonomy_no_links, "requires parent links")

    taxonomy_bad_relation = {
        "title": "Bad taxonomy",
        "diagram_type": "taxonomy_tree",
        "style": "modern-tech",
        "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
        "edges": [{"from": "a", "to": "b", "relation": "related_to"}],
    }
    assert_schema_error("taxonomy bad relation", taxonomy_bad_relation, "is not a parent relation")

    taxonomy_cycle = {
        "title": "Cyclic taxonomy",
        "diagram_type": "taxonomy_tree",
        "style": "modern-tech",
        "nodes": [
            {"id": "a", "label": "A", "parent": "b"},
            {"id": "b", "label": "B", "parent": "a"},
        ],
    }
    assert_schema_error("taxonomy cycle", taxonomy_cycle, "cannot contain cycles")

    hub = load_contract("hub-spoke-contract.json")
    missing_hub = copy.deepcopy(hub)
    missing_hub["hub_id"] = "missing"
    assert_schema_error("hub missing hub_id", missing_hub, "hub_id to match a node id")

    hub_with_edges = copy.deepcopy(hub)
    hub_with_edges["edges"] = [{"from": "hub", "to": "portal", "relation": "connects"}]
    assert_schema_error("hub mixed edges", hub_with_edges, 'does not support top-level "edges"')

    hub_bool_order = copy.deepcopy(hub)
    hub_bool_order["nodes"][1]["order"] = True
    assert_schema_error("hub bool order", hub_bool_order, "order must be a number")

    hub_one_node = copy.deepcopy(hub)
    hub_one_node["nodes"] = [hub_one_node["nodes"][0]]
    assert_schema_error("hub one node", hub_one_node, "at least one spoke node")

    print("contract schema selftest: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
