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


def load_json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))


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

    boundary_matrix = load_json("templates/boundary_ownership_map/reference-contract.json")
    assert_schema_pass("boundary ownership matrix", boundary_matrix)

    bad_boundary_variant = copy.deepcopy(boundary_matrix)
    bad_boundary_variant["variant"] = "unknown_matrix"
    assert_schema_error("boundary unknown variant", bad_boundary_variant, "unsupported boundary_ownership_map variant")

    bad_boundary_missing_domains = copy.deepcopy(boundary_matrix)
    del bad_boundary_missing_domains["domains"]
    assert_schema_error("boundary matrix missing domains", bad_boundary_missing_domains, 'requires "domains"')

    bad_boundary_relationship = copy.deepcopy(boundary_matrix)
    bad_boundary_relationship["relationships"][0]["to"] = "missing"
    assert_schema_error("boundary matrix missing relationship target", bad_boundary_relationship, "is not a boundary matrix item id")

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

    registry_stress = load_json("templates/registry_table/stress-contract.json")
    assert_schema_pass("registry stress with info panels", registry_stress)

    registry_bad_panel = copy.deepcopy(registry_stress)
    registry_bad_panel["info_panels"][0]["items"][0]["unknown"] = "nope"
    assert_schema_error("registry bad info panel item", registry_bad_panel, "unknown keys")

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
    hub_stress = load_json("templates/hub_spoke/stress-contract.json")
    assert_schema_pass("hub stress with info panels", hub_stress)

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

    object_relationship = load_json("templates/object_relationship_diagram/reference-contract.json")
    assert_schema_pass("object relationship reference", object_relationship)

    object_relationship_with_nodes = copy.deepcopy(object_relationship)
    object_relationship_with_nodes["nodes"] = [{"id": "n", "label": "N"}]
    assert_schema_error("object relationship mixed nodes", object_relationship_with_nodes, 'does not support top-level "nodes"')

    object_relationship_bad_endpoint = copy.deepcopy(object_relationship)
    object_relationship_bad_endpoint["relationships"][0]["to"] = "missing"
    assert_schema_error("object relationship missing endpoint", object_relationship_bad_endpoint, "is not an entity id")

    object_relationship_bad_role = copy.deepcopy(object_relationship)
    object_relationship_bad_role["entities"][0]["attributes"][0]["role"] = "primary"
    assert_schema_error("object relationship bad attribute role", object_relationship_bad_role, "is not supported")

    object_relationship_bad_slot = copy.deepcopy(object_relationship)
    object_relationship_bad_slot["relationships"][0]["col"] = True
    assert_schema_error("object relationship bad relationship slot", object_relationship_bad_slot, "relationships[0].col must be a number")

    object_relationship_bad_anchor = copy.deepcopy(object_relationship)
    object_relationship_bad_anchor["relationships"][0]["from_diamond_anchor"] = "upper-left"
    assert_schema_error("object relationship bad anchor", object_relationship_bad_anchor, "must be one of")

    object_relationship_bad_lane_offset = copy.deepcopy(object_relationship)
    object_relationship_bad_lane_offset["relationships"][0]["lane_offset"] = True
    assert_schema_error("object relationship bad lane offset", object_relationship_bad_lane_offset, "lane_offset must be a number")

    object_relationship_self_missing_slot = copy.deepcopy(object_relationship)
    object_relationship_self_missing_slot["relationships"][0]["to"] = object_relationship_self_missing_slot["relationships"][0]["from"]
    object_relationship_self_missing_slot["relationships"][0].pop("row", None)
    object_relationship_self_missing_slot["relationships"][0].pop("col", None)
    assert_schema_error("object relationship self missing placement", object_relationship_self_missing_slot, "self relationships need row/col or x/y placement")

    ontology = load_json("templates/ontology_map/reference-contract.json")
    assert_schema_pass("ontology map reference", ontology)

    ontology_with_entities = copy.deepcopy(ontology)
    ontology_with_entities["entities"] = [{"id": "n", "label": "N"}]
    assert_schema_error("ontology mixed entities", ontology_with_entities, 'does not support top-level "entities"')

    ontology_bad_relationship = copy.deepcopy(ontology)
    ontology_bad_relationship["relationships"][0]["to"] = "missing"
    assert_schema_error("ontology missing relationship endpoint", ontology_bad_relationship, "is not a concept id")

    ontology_bad_instance = copy.deepcopy(ontology)
    ontology_bad_instance["instances"][0]["concept"] = "missing"
    assert_schema_error("ontology missing instance concept", ontology_bad_instance, "is not a concept id")

    ontology_bad_attr = copy.deepcopy(ontology)
    ontology_bad_attr["concepts"][0]["attributes"][0].pop("name", None)
    assert_schema_error("ontology bad attribute", ontology_bad_attr, 'requires non-empty "name"')

    ontology_bad_lane_offset = copy.deepcopy(ontology)
    ontology_bad_lane_offset["relationships"][0]["lane_offset"] = "wide"
    assert_schema_error("ontology bad lane offset", ontology_bad_lane_offset, "lane_offset must be a number")

    capability_map = load_json("templates/capability_domain_map/reference-contract.json")
    assert_schema_pass("capability domain map reference", capability_map)

    capability_bad_level = copy.deepcopy(capability_map)
    capability_bad_level["items"][0]["level"] = "missing"
    assert_schema_error("capability missing level", capability_bad_level, "is not a level id")

    capability_bad_column = copy.deepcopy(capability_map)
    capability_bad_column["items"][0]["column"] = "missing"
    assert_schema_error("capability missing column", capability_bad_column, "is not a column id")

    capability_bad_relationship = copy.deepcopy(capability_map)
    capability_bad_relationship["relationships"][0]["to"] = "missing"
    assert_schema_error("capability missing relationship target", capability_bad_relationship, "is not an item id")

    capability_bad_badge = copy.deepcopy(capability_map)
    capability_bad_badge["items"][0]["badge"] = "CAP"
    assert_schema_error("capability item badge", capability_bad_badge, "items[0].badge is not supported")

    print("contract schema selftest: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
