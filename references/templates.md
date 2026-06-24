# Semantic Diagram Templates

Templates are example contracts plus guidance. They are not hard-coded domain layouts.

## Layered Knowledge Topology

Use for navigation, synthesis, asset, and source layers. Start from `examples/ocs-r300-layered-contract.json` for a single-row sibling set or `examples/ocs-r300-multirrow-contract.json` for multi-row fan-out/fan-in.

Required choices:

- Declare `style`.
- Declare stable `groups`.
- Use `row` and `col` when sibling placement must remain reproducible.
- Use `routing.mode: "row_bus_side_trunk"` for multi-row fan-out/fan-in.

## Source-Boundary Map

Use when the key message is what derives from controlled source material and what remains authoritative.

Start from `examples/accent-blueprint-boundary-contract.json` when a technical blueprint visual is desired.

Rules:

- Put fan-in buses inside the source sibling layer.
- Let vertically aligned source-to-target paths connect directly.
- Keep boundary labels and notes out of connector corridors.

## Boundary / Ownership Map

Use for domains, ownership, stewardship, and interface boundaries.

Rules:

- Use group panels as boundaries.
- Use yellow/amber accents for governance or shared ownership in `accent-blueprint`.
- Use dashed connectors only for optional, indirect, or responsibility links.

## Registry / Index Map

Use for glossary, ontology, CTQ, risk, or parameter registries.

Rules:

- Prefer compact cards and tables.
- Keep registry notes in footer or side panels.
- Use accent colors only for semantic categories, not decoration.
