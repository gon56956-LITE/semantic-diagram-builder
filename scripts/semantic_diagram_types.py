#!/usr/bin/env python3
"""Diagram type registry and compatibility mapping."""
from __future__ import annotations

from typing import Any


class DiagramTypeError(ValueError):
    """Raised when a semantic diagram contract declares an unsupported type."""


DIAGRAM_TYPES: dict[str, dict[str, str]] = {
    "layered_knowledge_topology": {
        "strategy": "grouped_layered",
        "description": "Layered knowledge architecture with grouped cards and optional multi-row routing.",
    },
    "source_boundary_map": {
        "strategy": "grouped_layered",
        "description": "Source-of-truth boundary map using grouped/layered placement.",
    },
    "boundary_ownership_map": {
        "strategy": "grouped_layered",
        "description": "Domain, ownership, and stewardship boundary map.",
    },
    "registry_table": {
        "strategy": "table",
        "description": "Compact register or glossary table.",
    },
    "taxonomy_tree": {
        "strategy": "tree",
        "description": "Parent-child taxonomy or classification tree.",
    },
    "hub_spoke": {
        "strategy": "hub_spoke",
        "description": "Central hub with surrounding spokes.",
    },
}

LEGACY_LAYOUT_TYPES = {
    "layered": "layered_knowledge_topology",
    "boundary_map": "source_boundary_map",
    "hierarchy": "taxonomy_tree",
    "hub_spoke": "hub_spoke",
    "registry_table": "registry_table",
}

GROUPED_LAYERED_TYPES = {
    "layered_knowledge_topology",
    "source_boundary_map",
    "boundary_ownership_map",
}

TREE_PARENT_RELATIONS = {"parent", "parent_of", "contains", "has_child", "classifies"}
ROUTING_MODES = {"auto", "row_bus_side_trunk", "simple"}
ROUTING_SIDES = {"left", "right"}
COLUMN_ALIGNS = {"left", "center", "right"}
ROW_META_KEYS = {"id", "kind", "accent"}


def _infer_type(contract: dict[str, Any]) -> str:
    if isinstance(contract.get("columns"), list) and isinstance(contract.get("rows"), list):
        return "registry_table"
    if contract.get("hub_id"):
        return "hub_spoke"
    nodes = contract.get("nodes", [])
    if isinstance(nodes, list) and any(isinstance(node, dict) and node.get("parent") for node in nodes):
        return "taxonomy_tree"
    return "layered_knowledge_topology"


def normalize_diagram_type(contract: dict[str, Any]) -> tuple[str, str, list[str]]:
    """Return diagram_type, strategy, warnings."""
    warnings: list[str] = []
    raw_type = contract.get("diagram_type")
    raw_layout = contract.get("layout")

    if isinstance(raw_type, str) and raw_type.strip():
        diagram_type = raw_type.strip()
        if diagram_type not in DIAGRAM_TYPES:
            raise DiagramTypeError(f"unsupported diagram_type: {diagram_type}")
        if isinstance(raw_layout, str) and raw_layout.strip() and raw_layout != "auto":
            mapped = LEGACY_LAYOUT_TYPES.get(raw_layout.strip())
            if mapped and mapped != diagram_type:
                warnings.append(
                    f'layout "{raw_layout}" maps to "{mapped}" but diagram_type "{diagram_type}" takes precedence'
                )
            elif not mapped:
                warnings.append(f'layout "{raw_layout}" is ignored because diagram_type is declared')
        return diagram_type, DIAGRAM_TYPES[diagram_type]["strategy"], warnings

    if isinstance(raw_layout, str) and raw_layout.strip():
        layout = raw_layout.strip()
        if layout == "auto":
            diagram_type = _infer_type(contract)
            warnings.append(f'layout "auto" inferred diagram_type "{diagram_type}" for compatibility')
        elif layout in LEGACY_LAYOUT_TYPES:
            diagram_type = LEGACY_LAYOUT_TYPES[layout]
            warnings.append(f'layout "{layout}" is deprecated; use diagram_type "{diagram_type}"')
        else:
            raise DiagramTypeError(f'unsupported layout "{layout}"; declare diagram_type explicitly')
        return diagram_type, DIAGRAM_TYPES[diagram_type]["strategy"], warnings

    raise DiagramTypeError('contract must declare top-level "diagram_type"')


def supported_diagram_types() -> set[str]:
    return set(DIAGRAM_TYPES)


def _require_contract_dict(contract: Any) -> dict[str, Any]:
    if not isinstance(contract, dict):
        raise DiagramTypeError("contract must be a JSON object")
    return contract


def _require_title(contract: dict[str, Any]) -> None:
    title = contract.get("title")
    if not isinstance(title, str) or not title.strip():
        raise DiagramTypeError('contract must declare non-empty "title"')


def _list_field(contract: dict[str, Any], field: str, diagram_type: str, *, required: bool, allow_empty: bool = False) -> list[Any]:
    if field not in contract:
        if required:
            raise DiagramTypeError(f'{diagram_type} requires "{field}"')
        return []
    value = contract.get(field)
    if not isinstance(value, list):
        raise DiagramTypeError(f'{diagram_type} field "{field}" must be a list')
    if required and not allow_empty and not value:
        raise DiagramTypeError(f'{diagram_type} requires non-empty "{field}"')
    return value


def _object_items(items: list[Any], field: str, diagram_type: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise DiagramTypeError(f'{diagram_type} {field}[{idx}] must be an object')
        objects.append(item)
    return objects


def _required_str(item: dict[str, Any], key: str, context: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DiagramTypeError(f'{context} requires non-empty "{key}"')
    return value.strip()


def _unique_required_ids(items: list[dict[str, Any]], field: str, diagram_type: str) -> list[str]:
    ids: list[str] = []
    for idx, item in enumerate(items):
        value = _required_str(item, "id", f"{diagram_type} {field}[{idx}]")
        ids.append(value)
    duplicates = sorted({value for value in ids if ids.count(value) > 1})
    if duplicates:
        joined = ", ".join(duplicates)
        raise DiagramTypeError(f'{diagram_type} duplicate {field} ids: {joined}')
    return ids


def _optional_ids(items: list[dict[str, Any]], field: str, diagram_type: str) -> list[str]:
    ids: list[str] = []
    for idx, item in enumerate(items):
        value = item.get("id")
        if value is None or value == "":
            continue
        if not isinstance(value, str):
            raise DiagramTypeError(f'{diagram_type} {field}[{idx}].id must be a string')
        ids.append(value)
    duplicates = sorted({value for value in ids if ids.count(value) > 1})
    if duplicates:
        joined = ", ".join(duplicates)
        raise DiagramTypeError(f'{diagram_type} duplicate {field} ids: {joined}')
    return ids


def _forbid_fields(contract: dict[str, Any], diagram_type: str, fields: set[str]) -> None:
    for field in sorted(fields):
        if field not in contract:
            continue
        value = contract.get(field)
        if value in (None, "", [], {}):
            continue
        raise DiagramTypeError(f'{diagram_type} does not support top-level "{field}"')


def _validate_annotations(contract: dict[str, Any], diagram_type: str) -> None:
    annotations = _list_field(contract, "annotations", diagram_type, required=False, allow_empty=True)
    for idx, annotation in enumerate(annotations):
        if not isinstance(annotation, dict):
            raise DiagramTypeError(f'{diagram_type} annotations[{idx}] must be an object')
        if "text" not in annotation or not str(annotation.get("text", "")).strip():
            raise DiagramTypeError(f'{diagram_type} annotations[{idx}] requires non-empty "text"')


def _validate_number(value: Any, context: str, *, minimum: float | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DiagramTypeError(f"{context} must be a number")
    if minimum is not None and float(value) < minimum:
        raise DiagramTypeError(f"{context} must be >= {minimum:g}")


def _validate_grouped_layered(contract: dict[str, Any], diagram_type: str) -> None:
    _forbid_fields(contract, diagram_type, {"columns", "rows", "hub_id"})
    groups = _object_items(_list_field(contract, "groups", diagram_type, required=True), "groups", diagram_type)
    nodes = _object_items(_list_field(contract, "nodes", diagram_type, required=True), "nodes", diagram_type)
    edges = _object_items(_list_field(contract, "edges", diagram_type, required=False, allow_empty=True), "edges", diagram_type)

    group_ids = set(_unique_required_ids(groups, "group", diagram_type))
    for idx, group in enumerate(groups):
        _required_str(group, "label", f"{diagram_type} groups[{idx}]")
        for numeric in ("max_per_row", "row_gap", "side_gutter", "height"):
            if numeric in group:
                _validate_number(group[numeric], f"{diagram_type} groups[{idx}].{numeric}", minimum=0)
        routing = group.get("routing")
        if routing is not None:
            if not isinstance(routing, dict):
                raise DiagramTypeError(f"{diagram_type} groups[{idx}].routing must be an object")
            mode = routing.get("mode")
            if mode is not None and mode not in ROUTING_MODES:
                raise DiagramTypeError(f'{diagram_type} groups[{idx}].routing.mode "{mode}" is not supported')
            for key in ("fanout_side", "fanin_side"):
                side = routing.get(key)
                if side is not None and side not in ROUTING_SIDES:
                    raise DiagramTypeError(f'{diagram_type} groups[{idx}].routing.{key} must be "left" or "right"')

    node_ids = set(_unique_required_ids(nodes, "node", diagram_type))
    for idx, node in enumerate(nodes):
        _required_str(node, "label", f"{diagram_type} nodes[{idx}]")
        group_id = _required_str(node, "group", f"{diagram_type} nodes[{idx}]")
        if group_id not in group_ids:
            raise DiagramTypeError(f'{diagram_type} nodes[{idx}].group "{group_id}" is not declared in groups')
        for coord in ("row", "col"):
            if coord in node:
                value = node[coord]
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise DiagramTypeError(f"{diagram_type} nodes[{idx}].{coord} must be a non-negative integer")

    for idx, edge in enumerate(edges):
        source = _required_str(edge, "from", f"{diagram_type} edges[{idx}]")
        target = _required_str(edge, "to", f"{diagram_type} edges[{idx}]")
        _required_str(edge, "relation", f"{diagram_type} edges[{idx}]")
        if source not in node_ids:
            raise DiagramTypeError(f'{diagram_type} edges[{idx}].from "{source}" is not a node id')
        if target not in node_ids:
            raise DiagramTypeError(f'{diagram_type} edges[{idx}].to "{target}" is not a node id')


def _validate_registry_table(contract: dict[str, Any], diagram_type: str) -> None:
    _forbid_fields(contract, diagram_type, {"groups", "nodes", "edges", "hub_id"})
    columns = _object_items(_list_field(contract, "columns", diagram_type, required=True), "columns", diagram_type)
    rows = _object_items(_list_field(contract, "rows", diagram_type, required=True, allow_empty=True), "rows", diagram_type)

    column_ids = _unique_required_ids(columns, "column", diagram_type)
    for idx, column in enumerate(columns):
        _required_str(column, "label", f"{diagram_type} columns[{idx}]")
        if "width" in column:
            _validate_number(column["width"], f"{diagram_type} columns[{idx}].width", minimum=1)
        align = column.get("align")
        if align is not None and align not in COLUMN_ALIGNS:
            raise DiagramTypeError(f'{diagram_type} columns[{idx}].align must be "left", "center", or "right"')

    _optional_ids(rows, "row", diagram_type)
    allowed_keys = set(column_ids) | ROW_META_KEYS
    for row_idx, row in enumerate(rows):
        unknown = sorted(set(row) - allowed_keys)
        if unknown:
            joined = ", ".join(unknown)
            raise DiagramTypeError(f"{diagram_type} rows[{row_idx}] has unknown column keys: {joined}")
        missing = [column_id for column_id in column_ids if column_id not in row]
        if missing:
            joined = ", ".join(missing)
            raise DiagramTypeError(f"{diagram_type} rows[{row_idx}] is missing column keys: {joined}")


def _validate_taxonomy_tree(contract: dict[str, Any], diagram_type: str) -> None:
    _forbid_fields(contract, diagram_type, {"groups", "columns", "rows", "hub_id"})
    nodes = _object_items(_list_field(contract, "nodes", diagram_type, required=True), "nodes", diagram_type)
    edges = _object_items(_list_field(contract, "edges", diagram_type, required=False, allow_empty=True), "edges", diagram_type)

    node_ids = set(_unique_required_ids(nodes, "node", diagram_type))
    parent_map: dict[str, str] = {}
    for idx, node in enumerate(nodes):
        node_id = str(node["id"])
        _required_str(node, "label", f"{diagram_type} nodes[{idx}]")
        if node.get("group"):
            raise DiagramTypeError(f"{diagram_type} nodes[{idx}] should not declare group")
        parent = node.get("parent")
        if parent is None or parent == "":
            continue
        if not isinstance(parent, str):
            raise DiagramTypeError(f"{diagram_type} nodes[{idx}].parent must be a node id string")
        if parent == node_id:
            raise DiagramTypeError(f'{diagram_type} node "{node_id}" cannot be its own parent')
        if parent not in node_ids:
            raise DiagramTypeError(f'{diagram_type} parent "{parent}" for "{node_id}" is not a node id')
        parent_map[node_id] = parent

    edge_parent_map: dict[str, str] = {}
    for idx, edge in enumerate(edges):
        source = _required_str(edge, "from", f"{diagram_type} edges[{idx}]")
        target = _required_str(edge, "to", f"{diagram_type} edges[{idx}]")
        relation = edge.get("relation", "parent")
        if relation not in TREE_PARENT_RELATIONS:
            raise DiagramTypeError(f'{diagram_type} edges[{idx}].relation "{relation}" is not a parent relation')
        if source not in node_ids:
            raise DiagramTypeError(f'{diagram_type} edges[{idx}].from "{source}" is not a node id')
        if target not in node_ids:
            raise DiagramTypeError(f'{diagram_type} edges[{idx}].to "{target}" is not a node id')
        if source == target:
            raise DiagramTypeError(f'{diagram_type} edge "{source}->{target}" cannot point to itself')
        if target in edge_parent_map and edge_parent_map[target] != source:
            raise DiagramTypeError(f'taxonomy_tree node "{target}" has multiple edge parents')
        edge_parent_map[target] = source

    combined = dict(parent_map)
    for child, edge_parent in edge_parent_map.items():
        if child in combined and combined[child] != edge_parent:
            raise DiagramTypeError(f'taxonomy_tree parent conflict for "{child}"')
        combined[child] = edge_parent
    if len(nodes) > 1 and not combined:
        raise DiagramTypeError("taxonomy_tree requires parent links via nodes[].parent or edges")

    children = {node_id: [] for node_id in node_ids}
    for child, parent in combined.items():
        children[parent].append(child)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            raise DiagramTypeError("taxonomy_tree cannot contain cycles")
        if node_id in visited:
            return
        visiting.add(node_id)
        for child in children[node_id]:
            visit(child)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in node_ids:
        visit(node_id)


def _validate_hub_spoke(contract: dict[str, Any], diagram_type: str) -> None:
    _forbid_fields(contract, diagram_type, {"groups", "columns", "rows", "edges"})
    nodes = _object_items(_list_field(contract, "nodes", diagram_type, required=True), "nodes", diagram_type)
    node_ids = set(_unique_required_ids(nodes, "node", diagram_type))
    if len(nodes) < 2:
        raise DiagramTypeError("hub_spoke requires one hub node and at least one spoke node")
    hub_id = contract.get("hub_id")
    if not isinstance(hub_id, str) or not hub_id.strip():
        raise DiagramTypeError('hub_spoke requires non-empty "hub_id"')
    if hub_id not in node_ids:
        raise DiagramTypeError("hub_spoke requires hub_id to match a node id")
    for idx, node in enumerate(nodes):
        _required_str(node, "label", f"{diagram_type} nodes[{idx}]")
        if node.get("group"):
            raise DiagramTypeError(f"{diagram_type} nodes[{idx}] should not declare group")
        if "parent" in node:
            raise DiagramTypeError(f"{diagram_type} nodes[{idx}] should not declare parent")
        if "order" in node:
            _validate_number(node["order"], f"{diagram_type} nodes[{idx}].order")


def validate_contract_schema(contract: dict[str, Any], diagram_type: str | None = None) -> list[str]:
    """Validate structural fields for a standard semantic diagram contract."""
    contract = _require_contract_dict(contract)
    _require_title(contract)
    _validate_annotations(contract, diagram_type or str(contract.get("diagram_type") or contract.get("layout") or "contract"))

    if diagram_type is None:
        diagram_type, _strategy, warnings = normalize_diagram_type(contract)
    else:
        warnings = []
        if diagram_type not in DIAGRAM_TYPES:
            raise DiagramTypeError(f"unsupported diagram_type: {diagram_type}")

    if diagram_type in GROUPED_LAYERED_TYPES:
        _validate_grouped_layered(contract, diagram_type)
    elif diagram_type == "registry_table":
        _validate_registry_table(contract, diagram_type)
    elif diagram_type == "taxonomy_tree":
        _validate_taxonomy_tree(contract, diagram_type)
    elif diagram_type == "hub_spoke":
        _validate_hub_spoke(contract, diagram_type)
    else:
        raise DiagramTypeError(f"unsupported diagram_type: {diagram_type}")
    return warnings
