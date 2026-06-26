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
    "object_relationship_diagram": {
        "strategy": "object_relationship",
        "description": "ER-style object relationship diagram with entity tables, relationships, attributes, and cardinality labels.",
    },
    "ontology_map": {
        "strategy": "object_relationship",
        "description": "Ontology concept map with concept cards, relationship diamonds, instances, datatypes, and side panels.",
    },
    "capability_domain_map": {
        "strategy": "capability_map",
        "description": "Banded capability/domain map with level labels, aligned columns, and capability dependency overlays.",
    },
}

BOUNDARY_OWNERSHIP_VARIANTS = {
    "grouped_layered": "grouped_layered",
    "domain_ownership_matrix": "boundary_matrix",
}

LEGACY_LAYOUT_TYPES = {
    "layered": "layered_knowledge_topology",
    "boundary_map": "source_boundary_map",
    "hierarchy": "taxonomy_tree",
    "hub_spoke": "hub_spoke",
    "registry_table": "registry_table",
    "object_relationship": "object_relationship_diagram",
    "ontology": "ontology_map",
    "capability_map": "capability_domain_map",
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
INFO_PANEL_ITEM_KEYS = {"label", "value", "text", "kind", "accent"}
ENTITY_ATTRIBUTE_ROLES = {"pk", "fk", "attribute", "derived"}
RELATIONSHIP_STYLES = {"solid", "dashed", "primary", "secondary"}
ANCHOR_SIDES = {"left", "right", "top", "bottom"}


def _infer_type(contract: dict[str, Any]) -> str:
    if isinstance(contract.get("domains"), list):
        return "boundary_ownership_map"
    if isinstance(contract.get("columns"), list) and isinstance(contract.get("rows"), list):
        return "registry_table"
    if contract.get("hub_id"):
        return "hub_spoke"
    if isinstance(contract.get("entities"), list):
        return "object_relationship_diagram"
    if isinstance(contract.get("concepts"), list):
        return "ontology_map"
    if isinstance(contract.get("levels"), list) and isinstance(contract.get("items"), list):
        return "capability_domain_map"
    nodes = contract.get("nodes", [])
    if isinstance(nodes, list) and any(isinstance(node, dict) and node.get("parent") for node in nodes):
        return "taxonomy_tree"
    return "layered_knowledge_topology"


def _strategy_for_contract(diagram_type: str, contract: dict[str, Any]) -> str:
    if diagram_type != "boundary_ownership_map":
        return DIAGRAM_TYPES[diagram_type]["strategy"]
    variant = contract.get("variant")
    if variant in (None, "", "reference", "minimal", "stress"):
        return "grouped_layered"
    if not isinstance(variant, str):
        raise DiagramTypeError("boundary_ownership_map variant must be a string")
    strategy = BOUNDARY_OWNERSHIP_VARIANTS.get(variant)
    if not strategy:
        supported = ", ".join(sorted(BOUNDARY_OWNERSHIP_VARIANTS))
        raise DiagramTypeError(f'unsupported boundary_ownership_map variant "{variant}"; supported variants: {supported}')
    return strategy


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
        return diagram_type, _strategy_for_contract(diagram_type, contract), warnings

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
        return diagram_type, _strategy_for_contract(diagram_type, contract), warnings

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


def _validate_info_panels(contract: dict[str, Any], diagram_type: str) -> None:
    panels = _list_field(contract, "info_panels", diagram_type, required=False, allow_empty=True)
    for panel_idx, panel in enumerate(panels):
        if not isinstance(panel, dict):
            raise DiagramTypeError(f"{diagram_type} info_panels[{panel_idx}] must be an object")
        _required_str(panel, "title", f"{diagram_type} info_panels[{panel_idx}]")
        if "id" in panel and panel["id"] not in (None, "") and not isinstance(panel["id"], str):
            raise DiagramTypeError(f"{diagram_type} info_panels[{panel_idx}].id must be a string")
        if "kind" in panel and panel["kind"] not in (None, "") and not isinstance(panel["kind"], str):
            raise DiagramTypeError(f"{diagram_type} info_panels[{panel_idx}].kind must be a string")
        if "accent" in panel and panel["accent"] not in (None, "") and not isinstance(panel["accent"], str):
            raise DiagramTypeError(f"{diagram_type} info_panels[{panel_idx}].accent must be a string")
        items = panel.get("items", [])
        if items in (None, ""):
            continue
        if not isinstance(items, list):
            raise DiagramTypeError(f"{diagram_type} info_panels[{panel_idx}].items must be a list")
        for item_idx, item in enumerate(items):
            if isinstance(item, str):
                if not item.strip():
                    raise DiagramTypeError(f"{diagram_type} info_panels[{panel_idx}].items[{item_idx}] must not be empty")
                continue
            if not isinstance(item, dict):
                raise DiagramTypeError(f"{diagram_type} info_panels[{panel_idx}].items[{item_idx}] must be a string or object")
            unknown = sorted(set(item) - INFO_PANEL_ITEM_KEYS)
            if unknown:
                joined = ", ".join(unknown)
                raise DiagramTypeError(f"{diagram_type} info_panels[{panel_idx}].items[{item_idx}] has unknown keys: {joined}")
            if not any(str(item.get(key, "")).strip() for key in ("label", "value", "text")):
                raise DiagramTypeError(f"{diagram_type} info_panels[{panel_idx}].items[{item_idx}] requires label, value, or text")


def _validate_number(value: Any, context: str, *, minimum: float | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DiagramTypeError(f"{context} must be a number")
    if minimum is not None and float(value) < minimum:
        raise DiagramTypeError(f"{context} must be >= {minimum:g}")


def _validate_grouped_layered(contract: dict[str, Any], diagram_type: str) -> None:
    _forbid_fields(contract, diagram_type, {"columns", "rows", "hub_id", "domains", "external_partners", "relationships", "ownership_assignments", "ownership_key", "info_panels"})
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


def _validate_columns_rows(owner: dict[str, Any], diagram_type: str, context: str) -> None:
    columns = _object_items(_list_field(owner, "columns", diagram_type, required=True), f"{context}.columns", diagram_type)
    rows = _object_items(_list_field(owner, "rows", diagram_type, required=True, allow_empty=True), f"{context}.rows", diagram_type)
    column_ids = _unique_required_ids(columns, "column", diagram_type)
    for idx, column in enumerate(columns):
        _required_str(column, "label", f"{diagram_type} {context}.columns[{idx}]")
        if "width" in column:
            _validate_number(column["width"], f"{diagram_type} {context}.columns[{idx}].width", minimum=1)
        align = column.get("align")
        if align is not None and align not in COLUMN_ALIGNS:
            raise DiagramTypeError(f'{diagram_type} {context}.columns[{idx}].align must be "left", "center", or "right"')
    _optional_ids(rows, "row", diagram_type)
    allowed_keys = set(column_ids) | ROW_META_KEYS
    for row_idx, row in enumerate(rows):
        unknown = sorted(set(row) - allowed_keys)
        if unknown:
            joined = ", ".join(unknown)
            raise DiagramTypeError(f"{diagram_type} {context}.rows[{row_idx}] has unknown column keys: {joined}")
        missing = [column_id for column_id in column_ids if column_id not in row]
        if missing:
            joined = ", ".join(missing)
            raise DiagramTypeError(f"{diagram_type} {context}.rows[{row_idx}] is missing column keys: {joined}")


def _collect_boundary_matrix_item_ids(items: list[dict[str, Any]], diagram_type: str, context: str) -> set[str]:
    ids = set(_unique_required_ids(items, context, diagram_type))
    for idx, item in enumerate(items):
        _required_str(item, "label", f"{diagram_type} {context}[{idx}]")
        for nested_key in ("systems", "assets"):
            nested = item.get(nested_key, [])
            if nested in (None, ""):
                continue
            if not isinstance(nested, list):
                raise DiagramTypeError(f'{diagram_type} {context}[{idx}].{nested_key} must be a list')
            nested_objects = _object_items(nested, f"{context}[{idx}].{nested_key}", diagram_type)
            nested_ids = _unique_required_ids(nested_objects, nested_key[:-1], diagram_type)
            for nested_idx, nested_item in enumerate(nested_objects):
                _required_str(nested_item, "label", f"{diagram_type} {context}[{idx}].{nested_key}[{nested_idx}]")
            overlap = ids & set(nested_ids)
            if overlap:
                joined = ", ".join(sorted(overlap))
                raise DiagramTypeError(f"{diagram_type} duplicate boundary matrix item ids: {joined}")
            ids.update(nested_ids)
    return ids


def _validate_boundary_ownership_map(contract: dict[str, Any], diagram_type: str) -> None:
    strategy = _strategy_for_contract(diagram_type, contract)
    if strategy == "grouped_layered":
        _validate_grouped_layered(contract, diagram_type)
        return

    _forbid_fields(contract, diagram_type, {"groups", "nodes", "edges", "columns", "rows", "hub_id", "info_panels"})
    domains = _object_items(_list_field(contract, "domains", diagram_type, required=True), "domains", diagram_type)
    domain_ids = _collect_boundary_matrix_item_ids(domains, diagram_type, "domains")
    external_items = _object_items(
        _list_field(contract, "external_partners", diagram_type, required=False, allow_empty=True),
        "external_partners",
        diagram_type,
    )
    external_ids = set(_unique_required_ids(external_items, "external_partner", diagram_type)) if external_items else set()
    for idx, item in enumerate(external_items):
        _required_str(item, "label", f"{diagram_type} external_partners[{idx}]")
    overlap = domain_ids & external_ids
    if overlap:
        joined = ", ".join(sorted(overlap))
        raise DiagramTypeError(f"{diagram_type} duplicate boundary matrix item ids: {joined}")
    known_ids = domain_ids | external_ids

    boundary = contract.get("boundary", {})
    if boundary not in ({}, None) and not isinstance(boundary, dict):
        raise DiagramTypeError(f"{diagram_type} boundary must be an object")

    relationships = _object_items(
        _list_field(contract, "relationships", diagram_type, required=False, allow_empty=True),
        "relationships",
        diagram_type,
    )
    for idx, relationship in enumerate(relationships):
        source = _required_str(relationship, "from", f"{diagram_type} relationships[{idx}]")
        target = _required_str(relationship, "to", f"{diagram_type} relationships[{idx}]")
        _required_str(relationship, "relation", f"{diagram_type} relationships[{idx}]")
        if source not in known_ids:
            raise DiagramTypeError(f'{diagram_type} relationships[{idx}].from "{source}" is not a boundary matrix item id')
        if target not in known_ids:
            raise DiagramTypeError(f'{diagram_type} relationships[{idx}].to "{target}" is not a boundary matrix item id')

    ownership_key = _object_items(
        _list_field(contract, "ownership_key", diagram_type, required=False, allow_empty=True),
        "ownership_key",
        diagram_type,
    )
    for idx, item in enumerate(ownership_key):
        _required_str(item, "code", f"{diagram_type} ownership_key[{idx}]")
        _required_str(item, "label", f"{diagram_type} ownership_key[{idx}]")

    assignments = contract.get("ownership_assignments")
    if assignments is not None:
        if not isinstance(assignments, dict):
            raise DiagramTypeError(f"{diagram_type} ownership_assignments must be an object")
        _validate_columns_rows(assignments, diagram_type, "ownership_assignments")


def _validate_registry_table(contract: dict[str, Any], diagram_type: str) -> None:
    _forbid_fields(contract, diagram_type, {"groups", "nodes", "edges", "hub_id"})
    _validate_columns_rows(contract, diagram_type, "")


def _validate_taxonomy_tree(contract: dict[str, Any], diagram_type: str) -> None:
    _forbid_fields(contract, diagram_type, {"groups", "columns", "rows", "hub_id", "info_panels"})
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


def _validate_object_relationship_diagram(contract: dict[str, Any], diagram_type: str) -> None:
    _forbid_fields(contract, diagram_type, {"groups", "nodes", "edges", "columns", "rows", "hub_id", "domains", "external_partners"})
    entities = _object_items(_list_field(contract, "entities", diagram_type, required=True), "entities", diagram_type)
    relationships = _object_items(_list_field(contract, "relationships", diagram_type, required=False, allow_empty=True), "relationships", diagram_type)
    entity_ids = set(_unique_required_ids(entities, "entity", diagram_type))
    for entity_idx, entity in enumerate(entities):
        _required_str(entity, "label", f"{diagram_type} entities[{entity_idx}]")
        for coord in ("row", "col"):
            if coord in entity:
                value = entity[coord]
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise DiagramTypeError(f"{diagram_type} entities[{entity_idx}].{coord} must be a non-negative integer")
        for coord in ("x", "y", "width", "height"):
            if coord in entity:
                _validate_number(entity[coord], f"{diagram_type} entities[{entity_idx}].{coord}", minimum=0)
        attributes = entity.get("attributes", [])
        if attributes in (None, ""):
            continue
        if not isinstance(attributes, list):
            raise DiagramTypeError(f"{diagram_type} entities[{entity_idx}].attributes must be a list")
        for attr_idx, attr in enumerate(attributes):
            if not isinstance(attr, dict):
                raise DiagramTypeError(f"{diagram_type} entities[{entity_idx}].attributes[{attr_idx}] must be an object")
            _required_str(attr, "name", f"{diagram_type} entities[{entity_idx}].attributes[{attr_idx}]")
            role = attr.get("role", "attribute")
            if role not in ENTITY_ATTRIBUTE_ROLES:
                raise DiagramTypeError(f'{diagram_type} entities[{entity_idx}].attributes[{attr_idx}].role "{role}" is not supported')

    relationship_ids = _optional_ids(relationships, "relationship", diagram_type)
    for rel_idx, relationship in enumerate(relationships):
        source = _required_str(relationship, "from", f"{diagram_type} relationships[{rel_idx}]")
        target = _required_str(relationship, "to", f"{diagram_type} relationships[{rel_idx}]")
        _required_str(relationship, "label", f"{diagram_type} relationships[{rel_idx}]")
        if source not in entity_ids:
            raise DiagramTypeError(f'{diagram_type} relationships[{rel_idx}].from "{source}" is not an entity id')
        if target not in entity_ids:
            raise DiagramTypeError(f'{diagram_type} relationships[{rel_idx}].to "{target}" is not an entity id')
        if source == target and not (
            isinstance(relationship.get("row"), (int, float))
            or isinstance(relationship.get("col"), (int, float))
            or (isinstance(relationship.get("x"), (int, float)) and isinstance(relationship.get("y"), (int, float)))
        ):
            raise DiagramTypeError(f'{diagram_type} relationship "{source}->{target}" self relationships need row/col or x/y placement')
        style = relationship.get("style")
        if style is not None and style not in RELATIONSHIP_STYLES:
            raise DiagramTypeError(f'{diagram_type} relationships[{rel_idx}].style "{style}" is not supported')
        for coord in ("row", "col", "x", "y", "diamond_width", "diamond_height"):
            if coord in relationship:
                _validate_number(relationship[coord], f"{diagram_type} relationships[{rel_idx}].{coord}", minimum=0)
        for key in ("from_cardinality", "to_cardinality"):
            value = relationship.get(key)
            if value is not None and not isinstance(value, str):
                raise DiagramTypeError(f"{diagram_type} relationships[{rel_idx}].{key} must be a string")
        for key in ("from_anchor", "to_anchor", "from_diamond_anchor", "to_diamond_anchor"):
            value = relationship.get(key)
            if value is not None and value not in ANCHOR_SIDES:
                supported = ", ".join(sorted(ANCHOR_SIDES))
                raise DiagramTypeError(f'{diagram_type} relationships[{rel_idx}].{key} must be one of: {supported}')
    if len(relationship_ids) != len(set(relationship_ids)):
        raise DiagramTypeError(f"{diagram_type} duplicate relationship ids")


def _validate_ontology_attributes(owner: dict[str, Any], context: str, diagram_type: str) -> None:
    attributes = owner.get("attributes", [])
    if attributes in (None, ""):
        return
    if not isinstance(attributes, list):
        raise DiagramTypeError(f"{context}.attributes must be a list")
    for attr_idx, attr in enumerate(attributes):
        if not isinstance(attr, dict):
            raise DiagramTypeError(f"{context}.attributes[{attr_idx}] must be an object")
        _required_str(attr, "name", f"{context}.attributes[{attr_idx}]")
        for key in ("type", "kind", "accent"):
            if key in attr and attr[key] not in (None, "") and not isinstance(attr[key], str):
                raise DiagramTypeError(f"{context}.attributes[{attr_idx}].{key} must be a string")


def _validate_ontology_map(contract: dict[str, Any], diagram_type: str) -> None:
    _forbid_fields(contract, diagram_type, {"groups", "nodes", "edges", "columns", "rows", "hub_id", "domains", "external_partners", "entities"})
    concepts = _object_items(_list_field(contract, "concepts", diagram_type, required=True), "concepts", diagram_type)
    relationships = _object_items(_list_field(contract, "relationships", diagram_type, required=False, allow_empty=True), "relationships", diagram_type)
    instances = _object_items(_list_field(contract, "instances", diagram_type, required=False, allow_empty=True), "instances", diagram_type)

    concept_ids = set(_unique_required_ids(concepts, "concept", diagram_type))
    instance_ids = set(_unique_required_ids(instances, "instance", diagram_type)) if instances else set()
    overlap = concept_ids & instance_ids
    if overlap:
        joined = ", ".join(sorted(overlap))
        raise DiagramTypeError(f"{diagram_type} duplicate concept/instance ids: {joined}")

    for concept_idx, concept in enumerate(concepts):
        _required_str(concept, "label", f"{diagram_type} concepts[{concept_idx}]")
        for coord in ("row", "col"):
            if coord in concept:
                value = concept[coord]
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise DiagramTypeError(f"{diagram_type} concepts[{concept_idx}].{coord} must be a non-negative integer")
        for coord in ("x", "y", "width", "height"):
            if coord in concept:
                _validate_number(concept[coord], f"{diagram_type} concepts[{concept_idx}].{coord}", minimum=0)
        for key in ("kind", "accent", "subtitle"):
            if key in concept and concept[key] not in (None, "") and not isinstance(concept[key], str):
                raise DiagramTypeError(f"{diagram_type} concepts[{concept_idx}].{key} must be a string")
        _validate_ontology_attributes(concept, f"{diagram_type} concepts[{concept_idx}]", diagram_type)

    for instance_idx, instance in enumerate(instances):
        _required_str(instance, "label", f"{diagram_type} instances[{instance_idx}]")
        concept = _required_str(instance, "concept", f"{diagram_type} instances[{instance_idx}]")
        if concept not in concept_ids:
            raise DiagramTypeError(f'{diagram_type} instances[{instance_idx}].concept "{concept}" is not a concept id')
        for coord in ("row", "col"):
            if coord in instance:
                value = instance[coord]
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise DiagramTypeError(f"{diagram_type} instances[{instance_idx}].{coord} must be a non-negative integer")
        for coord in ("x", "y", "width", "height"):
            if coord in instance:
                _validate_number(instance[coord], f"{diagram_type} instances[{instance_idx}].{coord}", minimum=0)
        for key in ("kind", "accent", "subtitle"):
            if key in instance and instance[key] not in (None, "") and not isinstance(instance[key], str):
                raise DiagramTypeError(f"{diagram_type} instances[{instance_idx}].{key} must be a string")

    relationship_ids = _optional_ids(relationships, "relationship", diagram_type)
    for rel_idx, relationship in enumerate(relationships):
        source = _required_str(relationship, "from", f"{diagram_type} relationships[{rel_idx}]")
        target = _required_str(relationship, "to", f"{diagram_type} relationships[{rel_idx}]")
        _required_str(relationship, "label", f"{diagram_type} relationships[{rel_idx}]")
        if source not in concept_ids:
            raise DiagramTypeError(f'{diagram_type} relationships[{rel_idx}].from "{source}" is not a concept id')
        if target not in concept_ids:
            raise DiagramTypeError(f'{diagram_type} relationships[{rel_idx}].to "{target}" is not a concept id')
        if source == target and not (
            isinstance(relationship.get("row"), (int, float))
            or isinstance(relationship.get("col"), (int, float))
            or (isinstance(relationship.get("x"), (int, float)) and isinstance(relationship.get("y"), (int, float)))
        ):
            raise DiagramTypeError(f'{diagram_type} relationship "{source}->{target}" self relationships need row/col or x/y placement')
        style = relationship.get("style")
        if style is not None and style not in RELATIONSHIP_STYLES:
            raise DiagramTypeError(f'{diagram_type} relationships[{rel_idx}].style "{style}" is not supported')
        for coord in ("row", "col", "x", "y", "diamond_width", "diamond_height"):
            if coord in relationship:
                _validate_number(relationship[coord], f"{diagram_type} relationships[{rel_idx}].{coord}", minimum=0)
        for key in ("from_cardinality", "to_cardinality"):
            value = relationship.get(key)
            if value is not None and not isinstance(value, str):
                raise DiagramTypeError(f"{diagram_type} relationships[{rel_idx}].{key} must be a string")
        for key in ("from_anchor", "to_anchor", "from_diamond_anchor", "to_diamond_anchor"):
            value = relationship.get(key)
            if value is not None and value not in ANCHOR_SIDES:
                supported = ", ".join(sorted(ANCHOR_SIDES))
                raise DiagramTypeError(f'{diagram_type} relationships[{rel_idx}].{key} must be one of: {supported}')
    if len(relationship_ids) != len(set(relationship_ids)):
        raise DiagramTypeError(f"{diagram_type} duplicate relationship ids")


def _validate_capability_domain_map(contract: dict[str, Any], diagram_type: str) -> None:
    _forbid_fields(contract, diagram_type, {"groups", "nodes", "edges", "rows", "hub_id", "domains", "external_partners", "entities"})
    levels = _object_items(_list_field(contract, "levels", diagram_type, required=True), "levels", diagram_type)
    columns = _object_items(_list_field(contract, "columns", diagram_type, required=True), "columns", diagram_type)
    items = _object_items(_list_field(contract, "items", diagram_type, required=True), "items", diagram_type)
    relationships = _object_items(_list_field(contract, "relationships", diagram_type, required=False, allow_empty=True), "relationships", diagram_type)

    level_ids = set(_unique_required_ids(levels, "level", diagram_type))
    column_ids = set(_unique_required_ids(columns, "column", diagram_type))
    for idx, level in enumerate(levels):
        _required_str(level, "label", f"{diagram_type} levels[{idx}]")
        for key in ("kind", "accent"):
            if key in level and level[key] not in (None, "") and not isinstance(level[key], str):
                raise DiagramTypeError(f"{diagram_type} levels[{idx}].{key} must be a string")
    for idx, column in enumerate(columns):
        _required_str(column, "label", f"{diagram_type} columns[{idx}]")
        if "width" in column:
            _validate_number(column["width"], f"{diagram_type} columns[{idx}].width", minimum=80)
        for key in ("kind", "accent"):
            if key in column and column[key] not in (None, "") and not isinstance(column[key], str):
                raise DiagramTypeError(f"{diagram_type} columns[{idx}].{key} must be a string")

    item_ids = set(_unique_required_ids(items, "item", diagram_type))
    for idx, item in enumerate(items):
        _required_str(item, "label", f"{diagram_type} items[{idx}]")
        level = _required_str(item, "level", f"{diagram_type} items[{idx}]")
        column = _required_str(item, "column", f"{diagram_type} items[{idx}]")
        if level not in level_ids:
            raise DiagramTypeError(f'{diagram_type} items[{idx}].level "{level}" is not a level id')
        if column not in column_ids:
            raise DiagramTypeError(f'{diagram_type} items[{idx}].column "{column}" is not a column id')
        for key in ("kind", "accent", "subtitle"):
            if key in item and item[key] not in (None, "") and not isinstance(item[key], str):
                raise DiagramTypeError(f"{diagram_type} items[{idx}].{key} must be a string")
        if "badge" in item:
            raise DiagramTypeError(f"{diagram_type} items[{idx}].badge is not supported; use levels[].kind or columns[].kind for header icons")
        if "span" in item:
            value = item["span"]
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise DiagramTypeError(f"{diagram_type} items[{idx}].span must be a positive integer")
        if "order" in item:
            _validate_number(item["order"], f"{diagram_type} items[{idx}].order")

    for idx, relationship in enumerate(relationships):
        source = _required_str(relationship, "from", f"{diagram_type} relationships[{idx}]")
        target = _required_str(relationship, "to", f"{diagram_type} relationships[{idx}]")
        _required_str(relationship, "relation", f"{diagram_type} relationships[{idx}]")
        if source not in item_ids:
            raise DiagramTypeError(f'{diagram_type} relationships[{idx}].from "{source}" is not an item id')
        if target not in item_ids:
            raise DiagramTypeError(f'{diagram_type} relationships[{idx}].to "{target}" is not an item id')
        if source == target:
            raise DiagramTypeError(f'{diagram_type} relationship "{source}->{target}" cannot point to itself')
        style = relationship.get("style")
        if style is not None and style not in RELATIONSHIP_STYLES:
            raise DiagramTypeError(f'{diagram_type} relationships[{idx}].style "{style}" is not supported')
        if "accent" in relationship and relationship["accent"] not in (None, "") and not isinstance(relationship["accent"], str):
            raise DiagramTypeError(f"{diagram_type} relationships[{idx}].accent must be a string")


def validate_contract_schema(contract: dict[str, Any], diagram_type: str | None = None) -> list[str]:
    """Validate structural fields for a standard semantic diagram contract."""
    contract = _require_contract_dict(contract)
    _require_title(contract)
    _validate_annotations(contract, diagram_type or str(contract.get("diagram_type") or contract.get("layout") or "contract"))
    _validate_info_panels(contract, diagram_type or str(contract.get("diagram_type") or contract.get("layout") or "contract"))

    if diagram_type is None:
        diagram_type, _strategy, warnings = normalize_diagram_type(contract)
    else:
        warnings = []
        if diagram_type not in DIAGRAM_TYPES:
            raise DiagramTypeError(f"unsupported diagram_type: {diagram_type}")

    if diagram_type == "boundary_ownership_map":
        _validate_boundary_ownership_map(contract, diagram_type)
    elif diagram_type in GROUPED_LAYERED_TYPES:
        _validate_grouped_layered(contract, diagram_type)
    elif diagram_type == "registry_table":
        _validate_registry_table(contract, diagram_type)
    elif diagram_type == "taxonomy_tree":
        _validate_taxonomy_tree(contract, diagram_type)
    elif diagram_type == "hub_spoke":
        _validate_hub_spoke(contract, diagram_type)
    elif diagram_type == "object_relationship_diagram":
        _validate_object_relationship_diagram(contract, diagram_type)
    elif diagram_type == "ontology_map":
        _validate_ontology_map(contract, diagram_type)
    elif diagram_type == "capability_domain_map":
        _validate_capability_domain_map(contract, diagram_type)
    else:
        raise DiagramTypeError(f"unsupported diagram_type: {diagram_type}")
    return warnings
