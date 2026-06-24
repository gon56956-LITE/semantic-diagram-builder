# Semantic Diagram Templates

Templates are example contracts plus guidance. They are not hard-coded domain layouts.

## Layered Knowledge Topology

Use for navigation, synthesis, asset, and source layers. Start from `examples/ocs-r300-layered-contract.json` for a single-row sibling set or `examples/ocs-r300-multirrow-contract.json` for multi-row fan-out/fan-in.

Required choices:

- Declare `diagram_type: "layered_knowledge_topology"`.
- Declare `style`.
- Declare stable `groups`.
- Use `row` and `col` when sibling placement must remain reproducible.
- Use `routing.mode: "row_bus_side_trunk"` for multi-row fan-out/fan-in.

## Source-Boundary Map

Use when the key message is what derives from controlled source material and what remains authoritative.

Start from `examples/accent-blueprint-boundary-contract.json` when a technical blueprint visual is desired.

Rules:

- Declare `diagram_type: "source_boundary_map"`.
- Put fan-in buses inside the source sibling layer.
- Let vertically aligned source-to-target paths connect directly.
- Keep boundary labels and notes out of connector corridors.

## Boundary / Ownership Map

Use for domains, ownership, stewardship, and interface boundaries.

Rules:

- Declare `diagram_type: "boundary_ownership_map"`.
- Use group panels as boundaries.
- Use yellow/amber accents for governance or shared ownership in `accent-blueprint`.
- Use dashed connectors only for optional, indirect, or responsibility links.

## Registry / Index Map

Use for glossary, ontology, CTQ, risk, or parameter registries. Start from `examples/registry-table-contract.json`.

Rules:

- Declare `diagram_type: "registry_table"`.
- Prefer compact cards and tables.
- Keep registry notes in footer or side panels.
- Use accent colors only for semantic categories, not decoration.

## Taxonomy Tree

Use for classification trees, category hierarchies, and rule trees. Start from `examples/taxonomy-tree-contract.json`.

Rules:

- Declare `diagram_type: "taxonomy_tree"`.
- Prefer `nodes[].parent` for deterministic hierarchy placement.
- Use `nodes[].order` to control sibling order when needed.
- Split trees that have too many leaf nodes for a readable slide.

## Hub-Spoke Map

Use for central hubs with surrounding comparable domains, systems, capabilities, or asset modules. Start from `examples/hub-spoke-contract.json`.

Rules:

- Declare `diagram_type: "hub_spoke"`.
- Set `hub_id` to the center node.
- Use `nodes[].order` for deterministic spoke placement.
- Use dashed spokes only for optional or indirect relationships.
