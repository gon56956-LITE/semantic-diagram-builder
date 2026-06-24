#!/usr/bin/env python3
"""Layout strategy registry for semantic diagrams.

The first implementation intentionally maps supported grouped semantic layouts
to the existing layered strategy. Future strategies can be added here without
changing style packages.
"""
from __future__ import annotations


LAYOUT_STRATEGIES = {
    "auto": "layered",
    "layered": "layered",
    "boundary_map": "layered",
}


def resolve_layout_strategy(layout: object) -> str | None:
    if not isinstance(layout, str):
        return LAYOUT_STRATEGIES["auto"]
    return LAYOUT_STRATEGIES.get(layout)


def supported_layouts() -> set[str]:
    return set(LAYOUT_STRATEGIES)
