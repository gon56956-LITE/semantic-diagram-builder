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
    print("validate_semantic_svg selftest: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
