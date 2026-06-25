#!/usr/bin/env python3
"""Small regression checks for validate_semantic_svg.py."""
from __future__ import annotations

import importlib.util
from pathlib import Path


VALIDATOR = Path(__file__).with_name("validate_semantic_svg.py")
spec = importlib.util.spec_from_file_location("validate_semantic_svg", VALIDATOR)
validator = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(validator)


def check_svg(svg: str) -> list[str]:
    return validator.check_svg(svg)


def assert_pass(name: str, svg: str) -> None:
    issues = check_svg(svg)
    if issues:
        raise AssertionError(f"{name} should pass, got: {issues}")


def assert_issue(name: str, svg: str, expected: str) -> None:
    issues = check_svg(svg)
    if not any(expected in issue for issue in issues):
        raise AssertionError(f"{name} should fail with {expected!r}, got: {issues}")


def main() -> int:
    assert_pass(
        "node-id card compatibility",
        """
<svg width="400" height="260">
<g id="node-a"><rect x="20" y="20" width="160" height="96" fill="#FFFFFF" stroke="#334155"/><path d="M44,44 H58" class="icon-line" stroke="#334155"/><text class="card-title">A</text></g>
<path d="M 20 160 L 180 160" class="edge"/>
</svg>
""",
    )
    assert_pass(
        "classed card",
        """
<svg width="400" height="260">
<g id="node-b" class="card node-card"><rect x="20" y="20" width="160" height="96" fill="#FFFFFF" stroke="#334155"/><path class="icon-line" d="M44,44 H58" stroke="#334155"/><text class="card-title">B</text></g>
<path class="edge" d="M 20 160 L 180 160"/>
</svg>
""",
    )
    assert_issue(
        "hard connector turn",
        '<svg width="100" height="100"><path d="M 0 0 L 10 0 L 10 10" class="edge"/></svg>',
        "hard orthogonal turn",
    )
    assert_issue(
        "icon outside card",
        """
<svg width="400" height="260">
<g id="node-c" class="card node-card"><rect x="20" y="20" width="160" height="96" fill="#FFFFFF" stroke="#334155"/><path d="M260,220 L280,240" class="icon-line" stroke="#334155"/><text class="card-title">C</text></g>
</svg>
""",
        "outside card bounds",
    )
    assert_pass(
        "card css without card nodes",
        """
<svg width="400" height="260">
<style>.card-title{fill:#0F172A}</style>
<text x="20" y="40" class="table-header">Header</text>
</svg>
""",
    )
    assert_pass(
        "context stroke arrow marker",
        """
<svg width="100" height="100">
<defs><marker id="arrow"><path d="M0,0 L0,6 L9,3 z" fill="context-stroke"/></marker></defs>
<path d="M 0 0 L 10 0" class="edge" marker-end="url(#arrow)"/>
</svg>
""",
    )
    assert_issue(
        "fixed color arrow marker",
        """
<svg width="100" height="100">
<defs><marker id="arrow-fanout"><path d="M0,0 L0,6 L9,3 z" fill="#2563EB"/></marker></defs>
<path d="M 0 0 L 10 0" class="edge fanout" marker-end="url(#arrow-fanout)"/>
</svg>
""",
        "context-stroke",
    )
    assert_issue(
        "small generated label text",
        """
<svg width="600" height="260">
<style>.group-label{font:700 10px Arial}.note{font:500 10px Arial}</style>
<rect x="20" y="20" width="560" height="180" class="group-panel" fill="#EEF6FF"/>
<g class="group-label-wrap"><rect x="32" y="32" width="90" height="24" fill="#FFFFFF"/><text x="40" y="48" class="group-label">Layer</text></g>
</svg>
""",
        "group-label font size",
    )
    assert_issue(
        "group label without shield",
        """
<svg width="600" height="260">
<rect x="20" y="20" width="560" height="180" class="group-panel" fill="#EEF6FF"/>
<text x="40" y="48" class="group-label">Layer</text>
</svg>
""",
        "group labels should use background shields",
    )
    assert_issue(
        "hub spoke excessive whitespace",
        """
<svg width="800" height="900" data-diagram-type="hub_spoke">
<g id="node-hub" class="card"><rect x="300" y="180" width="200" height="200" fill="#FFFFFF" stroke="#334155"/></g>
</svg>
""",
        "excessive bottom whitespace",
    )
    assert_pass(
        "bottom bus explains larger layer padding",
        """
<svg width="600" height="520">
<rect x="20" y="20" width="560" height="196" fill="#EEF6FF"/>
<text x="48" y="43" class="group-label">A</text>
<rect x="20" y="248" width="560" height="224" fill="#EEF6FF"/>
<text x="48" y="271" class="group-label">B</text>
<g id="node-a" class="card node-card"><rect x="100" y="84" width="160" height="100" fill="#FFFFFF" stroke="#334155"/><text class="card-title">A</text></g>
<g id="node-b" class="card node-card"><rect x="100" y="322" width="160" height="100" fill="#FFFFFF" stroke="#334155"/><text class="card-title">B</text></g>
<path d="M 100 454 L 260 454" class="edge"/>
</svg>
""",
    )
    assert_issue(
        "object relationship diamond overlaps entity",
        """
<svg width="600" height="360" data-diagram-type="object_relationship_diagram">
<g id="entity-a" class="object-entity-card card"><rect x="100" y="100" width="180" height="120" fill="#FFFFFF" stroke="#334155"/><text class="card-title" style="font-size:18px">A</text></g>
<g id="relationship-r" class="relationship-diamond"><path d="M 210 123 L 258 146 L 210 169 L 162 146 Z" fill="#FFFFFF" stroke="#FF9F2E"/></g>
</svg>
""",
        "overlaps an entity card",
    )
    assert_issue(
        "object relationship direct diagonal",
        """
<svg width="600" height="360" data-diagram-type="object_relationship_diagram">
<g id="entity-a" class="object-entity-card card"><rect x="80" y="80" width="120" height="90" fill="#FFFFFF" stroke="#334155"/><text class="card-title" style="font-size:18px">A</text></g>
<g id="entity-b" class="object-entity-card card"><rect x="360" y="210" width="120" height="90" fill="#FFFFFF" stroke="#334155"/><text class="card-title" style="font-size:18px">B</text></g>
<g id="relationship-r" class="relationship-diamond"><path d="M 280 145 L 328 168 L 280 191 L 232 168 Z" fill="#FFFFFF" stroke="#FF9F2E"/></g>
<path d="M 200 125 L 232 168" class="edge object-relationship-link"/>
</svg>
""",
        "direct diagonal",
    )
    assert_issue(
        "object relationship cardinality label overlaps entity",
        """
<svg width="600" height="360" data-diagram-type="object_relationship_diagram">
<g id="entity-a" class="object-entity-card card"><rect x="80" y="80" width="160" height="100" fill="#FFFFFF" stroke="#334155"/><text class="card-title" style="font-size:18px">A</text></g>
<g id="relationship-r" class="relationship-diamond"><path d="M 330 110 L 378 133 L 330 156 L 282 133 Z" fill="#FFFFFF" stroke="#FF9F2E"/></g>
<g class="cardinality-label-wrap"><rect x="100" y="100" width="40" height="24" fill="#031E42"/><text x="110" y="116" class="note cardinality-label" style="font-size:15px">0..*</text></g>
</svg>
""",
        "cardinality label",
    )
    print("validate_semantic_svg selftest: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
