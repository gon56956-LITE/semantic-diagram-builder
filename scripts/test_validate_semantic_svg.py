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
        "card title text overflow",
        """
<svg width="400" height="260">
<g id="node-long" class="card node-card"><rect x="20" y="20" width="120" height="96" fill="#FFFFFF" stroke="#334155"/><text x="40" y="62" class="card-title" style="font-size:18px">Very Long Unwrapped Semantic Label</text></g>
</svg>
""",
        "card-title text",
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
        "multi-source terminal anchors missing metadata",
        """
<svg width="500" height="300">
<defs><marker id="arrow-fanout"><path d="M0,0 L0,6 L9,3 z" fill="context-stroke"/></marker></defs>
<g id="node-target" class="card node-card"><rect x="180" y="160" width="120" height="70" fill="#FFFFFF" stroke="#334155"/><text class="card-title">T</text></g>
<path d="M 120 80 L 120 120 Q 120 134 134 134 L 234 134 Q 234 134 234 148 L 234 160" class="edge fanout terminal" marker-end="url(#arrow-fanout)" style="stroke:#16D9FF" data-target-id="target" data-source-id="source_a" data-route-color="#16D9FF"/>
<path d="M 340 80 L 340 120 Q 340 134 326 134 L 234 134 Q 234 134 234 148 L 234 160" class="edge edge-dashed fanout terminal" marker-end="url(#arrow-fanout)" style="stroke:#6EE66E" data-target-id="target" data-source-id="source_b" data-route-color="#6EE66E"/>
</svg>
""",
        "data-target-anchor",
    )
    assert_issue(
        "multi-source terminal anchors too close",
        """
<svg width="500" height="300">
<defs><marker id="arrow-fanout"><path d="M0,0 L0,6 L9,3 z" fill="context-stroke"/></marker></defs>
<g id="node-target" class="card node-card"><rect x="180" y="160" width="120" height="70" fill="#FFFFFF" stroke="#334155"/><text class="card-title">T</text></g>
<path d="M 120 80 L 120 120 Q 120 134 134 134 L 232 134 Q 232 134 232 148 L 232 160" class="edge fanout terminal" marker-end="url(#arrow-fanout)" style="stroke:#16D9FF" data-target-id="target" data-source-id="source_a" data-route-color="#16D9FF" data-target-anchor-lane="0" data-target-anchor-count="2" data-target-anchor-shift="-2.0"/>
<path d="M 340 80 L 340 120 Q 340 134 326 134 L 236 134 Q 236 134 236 148 L 236 160" class="edge edge-dashed fanout terminal" marker-end="url(#arrow-fanout)" style="stroke:#6EE66E" data-target-id="target" data-source-id="source_b" data-route-color="#6EE66E" data-target-anchor-lane="1" data-target-anchor-count="2" data-target-anchor-shift="2.0"/>
</svg>
""",
        "too close",
    )
    assert_pass(
        "multi-source terminal anchors separated",
        """
<svg width="500" height="300">
<defs><marker id="arrow-fanout"><path d="M0,0 L0,6 L9,3 z" fill="context-stroke"/></marker></defs>
<g id="node-target" class="card node-card"><rect x="180" y="160" width="120" height="70" fill="#FFFFFF" stroke="#334155"/><text class="card-title">T</text></g>
<path d="M 120 80 L 120 120 Q 120 134 134 134 L 225 134 Q 225 134 225 148 L 225 160" class="edge fanout terminal" marker-end="url(#arrow-fanout)" style="stroke:#16D9FF" data-target-id="target" data-source-id="source_a" data-route-color="#16D9FF" data-target-anchor-lane="0" data-target-anchor-count="2" data-target-anchor-shift="-9.0"/>
<path d="M 340 80 L 340 120 Q 340 134 326 134 L 243 134 Q 243 134 243 148 L 243 160" class="edge edge-dashed fanout terminal" marker-end="url(#arrow-fanout)" style="stroke:#6EE66E" data-target-id="target" data-source-id="source_b" data-route-color="#6EE66E" data-target-anchor-lane="1" data-target-anchor-count="2" data-target-anchor-shift="9.0"/>
</svg>
""",
    )
    assert_issue(
        "multi-source direct-link anchors missing metadata",
        """
<svg width="500" height="300">
<defs><marker id="arrow"><path d="M0,0 L0,6 L9,3 z" fill="context-stroke"/></marker></defs>
<g id="node-target" class="card node-card"><rect x="180" y="160" width="120" height="70" fill="#FFFFFF" stroke="#334155"/><text class="card-title">T</text></g>
<path d="M 120 80 L 120 120 Q 120 134 134 134 L 234 134 Q 234 134 234 148 L 234 160" class="edge direct-link" marker-end="url(#arrow)" style="stroke:#16D9FF" data-target-id="target" data-source-id="source_a" data-route-color="#16D9FF"/>
<path d="M 340 80 L 340 120 Q 340 134 326 134 L 234 134 Q 234 134 234 148 L 234 160" class="edge edge-dashed direct-link" marker-end="url(#arrow)" style="stroke:#6EE66E" data-target-id="target" data-source-id="source_b" data-route-color="#6EE66E"/>
</svg>
""",
        "data-target-anchor",
    )
    assert_pass(
        "multi-source direct-link anchors separated",
        """
<svg width="500" height="300">
<defs><marker id="arrow"><path d="M0,0 L0,6 L9,3 z" fill="context-stroke"/></marker></defs>
<g id="node-target" class="card node-card"><rect x="180" y="160" width="120" height="70" fill="#FFFFFF" stroke="#334155"/><text class="card-title">T</text></g>
<path d="M 120 80 L 120 120 Q 120 134 134 134 L 225 134 Q 225 134 225 148 L 225 160" class="edge direct-link" marker-end="url(#arrow)" style="stroke:#16D9FF" data-target-id="target" data-source-id="source_a" data-route-color="#16D9FF" data-target-anchor-lane="0" data-target-anchor-count="2" data-target-anchor-shift="-9.0"/>
<path d="M 340 80 L 340 120 Q 340 134 326 134 L 243 134 Q 243 134 243 148 L 243 160" class="edge edge-dashed direct-link" marker-end="url(#arrow)" style="stroke:#6EE66E" data-target-id="target" data-source-id="source_b" data-route-color="#6EE66E" data-target-anchor-lane="1" data-target-anchor-count="2" data-target-anchor-shift="9.0"/>
</svg>
""",
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
    assert_issue(
        "capability map direct diagonal",
        """
<svg width="700" height="360" data-diagram-type="capability_domain_map">
<g class="capability-level-icon capability-header-icon"></g>
<g class="capability-column-icon capability-header-icon"></g>
<text x="40" y="40" class="capability-level-label" style="font-size:15px">Level</text>
<text x="200" y="40" class="capability-column-label" style="font-size:15px">Column</text>
<g id="capability-item-a" class="capability-map-item card"><rect x="100" y="90" width="150" height="96" fill="#FFFFFF" stroke="#334155"/><text class="capability-title" style="font-size:16.5px">A</text></g>
<g id="capability-item-b" class="capability-map-item card"><rect x="420" y="220" width="150" height="96" fill="#FFFFFF" stroke="#334155"/><text class="capability-title" style="font-size:16.5px">B</text></g>
<path d="M 250 160 L 420 220" class="edge capability-map-link"/>
</svg>
""",
        "direct diagonal",
    )
    assert_issue(
        "capability map short card",
        """
<svg width="700" height="360" data-diagram-type="capability_domain_map">
<g class="capability-level-icon capability-header-icon"></g>
<g class="capability-column-icon capability-header-icon"></g>
<text x="40" y="40" class="capability-level-label" style="font-size:15px">Level</text>
<text x="200" y="40" class="capability-column-label" style="font-size:15px">Column</text>
<g id="capability-item-a" class="capability-map-item card"><rect x="100" y="90" width="150" height="66" fill="#FFFFFF" stroke="#334155"/><text class="capability-title" style="font-size:16.5px">A</text></g>
</svg>
""",
        "too short",
    )
    assert_issue(
        "capability map column header overflow",
        """
<svg width="700" height="360" data-diagram-type="capability_domain_map">
<rect x="120" y="30" width="120" height="38" fill="none" stroke="#334155"/>
<g class="capability-level-icon capability-header-icon"></g>
<g class="capability-column-icon capability-header-icon"></g>
<text x="40" y="120" class="capability-level-label" style="font-size:15px">Level</text>
<text x="170" y="55" class="capability-column-label" style="font-size:15px">Very Long Column Header</text>
<g id="capability-item-a" class="capability-map-item card"><rect x="120" y="120" width="150" height="96" fill="#FFFFFF" stroke="#334155"/><text class="capability-title" style="font-size:16.5px">A</text></g>
</svg>
""",
        "capability column label",
    )
    assert_issue(
        "capability map near-card corridor",
        """
<svg width="700" height="480" data-diagram-type="capability_domain_map">
<g class="capability-level-icon capability-header-icon"></g>
<g class="capability-column-icon capability-header-icon"></g>
<text x="40" y="40" class="capability-level-label" style="font-size:15px">Level</text>
<text x="200" y="40" class="capability-column-label" style="font-size:15px">Column</text>
<g id="capability-item-a" class="capability-map-item card"><rect x="180" y="80" width="100" height="96" fill="#FFFFFF" stroke="#334155"/><text class="capability-title" style="font-size:16.5px">A</text></g>
<g id="capability-item-b" class="capability-map-item card"><rect x="180" y="300" width="100" height="96" fill="#FFFFFF" stroke="#334155"/><text class="capability-title" style="font-size:16.5px">B</text></g>
<g id="capability-item-c" class="capability-map-item card"><rect x="120" y="190" width="100" height="96" fill="#FFFFFF" stroke="#334155"/><text class="capability-title" style="font-size:16.5px">C</text></g>
<path d="M 225 162 L 225 300" class="edge capability-map-link" data-from="a" data-to="b"/>
</svg>
""",
        "too close",
    )
    assert_issue(
        "capability map shared same-color corridor",
        """
<svg width="700" height="520" data-diagram-type="capability_domain_map">
<g class="capability-level-icon capability-header-icon"></g>
<g class="capability-column-icon capability-header-icon"></g>
<text x="40" y="40" class="capability-level-label" style="font-size:15px">Level</text>
<text x="200" y="40" class="capability-column-label" style="font-size:15px">Column</text>
<g id="capability-item-a" class="capability-map-item card"><rect x="20" y="80" width="80" height="96" fill="#FFFFFF" stroke="#334155"/><text class="capability-title" style="font-size:16.5px">A</text></g>
<g id="capability-item-b" class="capability-map-item card"><rect x="320" y="240" width="80" height="96" fill="#FFFFFF" stroke="#334155"/><text class="capability-title" style="font-size:16.5px">B</text></g>
<g id="capability-item-c" class="capability-map-item card"><rect x="20" y="180" width="80" height="96" fill="#FFFFFF" stroke="#334155"/><text class="capability-title" style="font-size:16.5px">C</text></g>
<g id="capability-item-d" class="capability-map-item card"><rect x="320" y="340" width="80" height="96" fill="#FFFFFF" stroke="#334155"/><text class="capability-title" style="font-size:16.5px">D</text></g>
<path d="M 100 121 L 200 121 L 200 281 L 320 281" class="edge capability-map-link" style="stroke:#F4F8FF" data-from="a" data-to="b"/>
<path d="M 100 221 L 200 221 L 200 381 L 320 381" class="edge capability-map-link" style="stroke:#F4F8FF" data-from="c" data-to="d"/>
</svg>
""",
        "same-color vertical corridor",
    )
    assert_issue(
        "relationship matrix top connected label overflow",
        """
<svg width="900" height="600" data-diagram-type="relationship_matrix">
<g class="relationship-matrix-grid info-panel"><rect x="20" y="20" width="240" height="120" fill="#FFFFFF" stroke="#334155"/><rect x="40" y="50" width="64" height="64" class="matrix-cell" fill="none"/><text x="72" y="90" class="matrix-cell-value" style="font-size:30px">1</text></g>
<g class="matrix-primary-preview info-panel"><rect x="280" y="20" width="120" height="120" fill="#FFFFFF" stroke="#334155"/></g>
<g class="matrix-summary-panel info-panel"><rect x="420" y="20" width="120" height="120" fill="#FFFFFF" stroke="#334155"/><rect x="440" y="70" width="80" height="14" class="matrix-distribution-bar" fill="#06B6D4"/></g>
<g class="matrix-focus-detail-panel info-panel"><rect x="560" y="20" width="120" height="120" fill="#FFFFFF" stroke="#334155"/></g>
<g class="matrix-top-connected-panel info-panel">
<rect x="20" y="180" width="420" height="160" fill="#FFFFFF" stroke="#334155"/>
<text x="38" y="212" class="info-panel-title" style="font-size:16px">Top Connected</text>
<text x="78" y="256" class="matrix-rank-label" style="font-size:18px">Very Long Semantic Entity Label</text>
<rect x="254" y="243" width="112" height="14" fill="#FFFFFF" stroke="#334155"/>
<rect x="254" y="243" width="80" height="14" fill="#06B6D4"/>
</g>
</svg>
""",
        "top-connected label",
    )
    assert_issue(
        "relationship matrix row label overflow",
        """
<svg width="900" height="680" data-diagram-type="relationship_matrix">
<g class="relationship-matrix-grid info-panel">
<rect x="20" y="20" width="280" height="220" fill="#FFFFFF" stroke="#334155"/>
<text x="40" y="124" class="matrix-row-label" style="font-size:18px">Very Long Matrix Row Label</text>
<text x="212" y="72" text-anchor="middle" class="matrix-col-label" style="font-size:18px">Col</text>
<rect x="180" y="90" width="64" height="64" class="matrix-cell" fill="none"/>
<text x="212" y="130" class="matrix-cell-value" style="font-size:24px">1</text>
</g>
<g class="matrix-primary-preview info-panel"><rect x="320" y="20" width="120" height="120" fill="#FFFFFF" stroke="#334155"/></g>
<g class="matrix-summary-panel info-panel"><rect x="460" y="20" width="120" height="120" fill="#FFFFFF" stroke="#334155"/><rect x="480" y="70" width="80" height="14" class="matrix-distribution-bar" fill="#06B6D4"/></g>
<g class="matrix-focus-detail-panel info-panel"><rect x="600" y="20" width="120" height="120" fill="#FFFFFF" stroke="#334155"/></g>
<g class="matrix-top-connected-panel info-panel"><rect x="20" y="300" width="420" height="160" fill="#FFFFFF" stroke="#334155"/></g>
</svg>
""",
        "row label",
    )
    assert_issue(
        "relationship matrix column label overflow",
        """
<svg width="900" height="680" data-diagram-type="relationship_matrix">
<g class="relationship-matrix-grid info-panel">
<rect x="20" y="20" width="280" height="220" fill="#FFFFFF" stroke="#334155"/>
<text x="40" y="124" class="matrix-row-label" style="font-size:18px">Row</text>
<text x="212" y="72" text-anchor="middle" class="matrix-col-label" style="font-size:18px">Very Long Matrix Column Label</text>
<rect x="180" y="90" width="64" height="64" class="matrix-cell" fill="none"/>
<text x="212" y="130" class="matrix-cell-value" style="font-size:24px">1</text>
</g>
<g class="matrix-primary-preview info-panel"><rect x="320" y="20" width="120" height="120" fill="#FFFFFF" stroke="#334155"/></g>
<g class="matrix-summary-panel info-panel"><rect x="460" y="20" width="120" height="120" fill="#FFFFFF" stroke="#334155"/><rect x="480" y="70" width="80" height="14" class="matrix-distribution-bar" fill="#06B6D4"/></g>
<g class="matrix-focus-detail-panel info-panel"><rect x="600" y="20" width="120" height="120" fill="#FFFFFF" stroke="#334155"/></g>
<g class="matrix-top-connected-panel info-panel"><rect x="20" y="300" width="420" height="160" fill="#FFFFFF" stroke="#334155"/></g>
</svg>
""",
        "column label",
    )
    print("validate_semantic_svg selftest: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
