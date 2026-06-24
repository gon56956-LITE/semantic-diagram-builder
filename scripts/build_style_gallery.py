#!/usr/bin/env python3
"""Build a self-contained HTML gallery for style visual QA."""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

import render_semantic_diagram as renderer


ROOT = Path(__file__).resolve().parents[1]


def render_gallery_html(contract_paths: list[Path]) -> str:
    sections = []
    for contract_path in contract_paths:
        contract = json.loads(contract_path.read_text(encoding="utf-8-sig"))
        svg = renderer.render(contract, contract_path)
        style_name = contract.get("style", "")
        diagram_type = contract.get("diagram_type", contract.get("layout", ""))
        title = contract.get("title", contract_path.stem)
        sections.append(
            f"""
<section class="frame">
  <header>
    <strong>{html.escape(str(title))}</strong>
    <span>{html.escape(str(style_name))}</span>
    <span>{html.escape(str(diagram_type))}</span>
    <code>{html.escape(str(contract_path))}</code>
  </header>
  <div class="svg-wrap">{svg}</div>
</section>""".strip()
        )

    body = "\n".join(sections)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Semantic Diagram Style Gallery</title>
  <style>
    body{{margin:0;background:#0b1220;color:#e5e7eb;font-family:Inter,Segoe UI,Arial,sans-serif}}
    main{{padding:24px;display:grid;gap:24px}}
    .frame{{border:1px solid #334155;background:#111827;padding:14px}}
    header{{display:flex;gap:16px;align-items:baseline;margin:0 0 12px 0;color:#cbd5e1}}
    header strong{{color:#f8fafc}}
    header code{{margin-left:auto;color:#94a3b8}}
    .svg-wrap{{overflow:auto;background:#020617}}
    svg{{display:block;max-width:100%;height:auto}}
  </style>
</head>
<body>
<main>
{body}
</main>
</body>
</html>
"""


def build_gallery(output_path: Path, contract_paths: list[Path]) -> None:
    output = render_gallery_html(contract_paths)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output, encoding="utf-8", newline="\n")


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("Usage: build_style_gallery.py output.html contract.json [contract2.json ...]", file=sys.stderr)
        return 2
    output_path = Path(argv[1])
    contracts = [Path(arg) for arg in argv[2:]]
    build_gallery(output_path, contracts)
    print(f"wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
