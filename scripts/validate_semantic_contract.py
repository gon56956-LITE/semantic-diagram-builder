#!/usr/bin/env python3
"""Validate semantic diagram contracts without rendering SVG."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from render_semantic_diagram import DiagramTypeError, StyleError, contract_warnings


def check(path: Path) -> tuple[bool, list[str]]:
    try:
        contract = json.loads(path.read_text(encoding="utf-8-sig"))
        warnings = contract_warnings(contract, path)
    except (OSError, json.JSONDecodeError, StyleError, DiagramTypeError) as exc:
        return False, [str(exc)]
    return True, warnings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: validate_semantic_contract.py contract.json [contract2.json ...]", file=sys.stderr)
        return 2
    any_fail = False
    for name in argv[1:]:
        path = Path(name)
        ok, messages = check(path)
        if ok:
            print(f"{path}: PASS")
            for message in messages:
                print(f"  warning: {message}")
        else:
            any_fail = True
            print(f"{path}: FAIL")
            for message in messages:
                print(f"  - {message}")
    return 1 if any_fail else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
