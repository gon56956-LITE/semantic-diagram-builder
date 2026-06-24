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
