# Semantic Diagram Templates

Templates are reusable starting contracts plus rendered reference SVGs. They are not hard-coded domain layouts.

Each standard diagram type has:

- `templates/<diagram_type>/minimal-contract.json`: the smallest useful contract shape.
- `templates/<diagram_type>/reference-contract.json`: a richer reference pattern.
- `templates/<diagram_type>/stress-contract.json`: a dense QA pattern intended to expose routing, typography, spacing, and canvas issues.
- `templates/<diagram_type>/minimal.svg`: renderer output for the minimal contract.
- `templates/<diagram_type>/reference.svg`: renderer output for the reference contract.
- `templates/<diagram_type>/stress.svg`: renderer output for the stress contract.

`templates/template-gallery.html` renders the reference and stress templates for visual review. Minimal templates remain available as starting points, but they are intentionally not used as the main visual QA gallery because they are too small to expose many layout problems. `templates/template-gallery-baseline.json` is the manifest used by `py scripts/test_template_library.py`.

## Usage

1. Pick the closest `diagram_type`.
2. Copy the matching minimal or reference contract structure.
3. Replace node/group/table content while preserving required structural fields.
4. Run `py scripts/validate_semantic_contract.py your-contract.json`.
5. Render and run SVG QA.

## Template Index

| Diagram type | Minimal template | Reference template | Stress template |
| --- | --- | --- | --- |
| `layered_knowledge_topology` | `templates/layered_knowledge_topology/minimal-contract.json` | `templates/layered_knowledge_topology/reference-contract.json` | `templates/layered_knowledge_topology/stress-contract.json` |
| `source_boundary_map` | `templates/source_boundary_map/minimal-contract.json` | `templates/source_boundary_map/reference-contract.json` | `templates/source_boundary_map/stress-contract.json` |
| `boundary_ownership_map` | `templates/boundary_ownership_map/minimal-contract.json` | `templates/boundary_ownership_map/reference-contract.json` | `templates/boundary_ownership_map/stress-contract.json` |
| `registry_table` | `templates/registry_table/minimal-contract.json` | `templates/registry_table/reference-contract.json` | `templates/registry_table/stress-contract.json` |
| `taxonomy_tree` | `templates/taxonomy_tree/minimal-contract.json` | `templates/taxonomy_tree/reference-contract.json` | `templates/taxonomy_tree/stress-contract.json` |
| `hub_spoke` | `templates/hub_spoke/minimal-contract.json` | `templates/hub_spoke/reference-contract.json` | `templates/hub_spoke/stress-contract.json` |

## Type Notes

### Layered Knowledge Topology

Use for navigation, synthesis, asset, and source layers.

- Use `row` and `col` when sibling placement must remain reproducible.
- Use `routing.mode: "row_bus_side_trunk"` for multi-row fan-out/fan-in.

### Source-Boundary Map

Use when the key message is what derives from controlled source material and what remains authoritative.

- Put fan-in buses inside the source sibling layer.
- Let vertically aligned source-to-target paths connect directly.
- Keep boundary labels and notes out of connector corridors.

### Boundary Ownership Map

Use for domains, ownership, stewardship, and interface boundaries.

- Use group panels as boundaries.
- Use yellow/amber accents for governance or shared ownership in `accent-blueprint`.
- Use dashed connectors only for optional, indirect, or responsibility links.

### Registry Table

Use for glossary, ontology, CTQ, risk, or parameter registries.

- Rows must include every declared column id.
- Use `rows[].kind` to drive semantic badges.
- Keep registry notes in footer annotations unless a custom layout is needed.

### Taxonomy Tree

Use for classification trees, category hierarchies, and rule trees.

- Prefer `nodes[].parent` for deterministic hierarchy placement.
- Use `nodes[].order` to control sibling order when needed.
- Split trees that have too many leaf nodes for a readable slide.

### Hub-Spoke

Use for central hubs with surrounding comparable domains, systems, capabilities, or asset modules.

- Set `hub_id` to the center node.
- Use `nodes[].order` for deterministic spoke placement.
- Use dashed spokes only for optional or indirect relationships.

## QA

Run:

```bash
py scripts/test_template_library.py
```

This checks every template contract, ensures expected SVGs are current, validates SVG geometry/style QA, and confirms the template gallery is up to date.
