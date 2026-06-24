#!/usr/bin/env python3
"""Legacy layout compatibility helpers.

Standard contracts should use diagram_type. This module remains for callers
that still ask which legacy layout names are recognized.
"""
from __future__ import annotations

from semantic_diagram_types import LEGACY_LAYOUT_TYPES, supported_diagram_types


LAYOUT_STRATEGIES = dict(LEGACY_LAYOUT_TYPES)
LAYOUT_STRATEGIES["auto"] = "layered_knowledge_topology"

def resolve_layout_strategy(layout: object) -> str | None:
    if not isinstance(layout, str):
        return LAYOUT_STRATEGIES["auto"]
    return LAYOUT_STRATEGIES.get(layout)


def supported_layouts() -> set[str]:
    return set(LAYOUT_STRATEGIES)


def supported_types() -> set[str]:
    return supported_diagram_types()
