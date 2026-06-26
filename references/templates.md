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

Use `references/diagram_type_maturity.md` as the checklist for deciding whether a template family is complete enough to call mature.

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
| `object_relationship_diagram` | `templates/object_relationship_diagram/minimal-contract.json` | `templates/object_relationship_diagram/reference-contract.json` | `templates/object_relationship_diagram/stress-contract.json` |
| `ontology_map` | `templates/ontology_map/minimal-contract.json` | `templates/ontology_map/reference-contract.json` | `templates/ontology_map/stress-contract.json` |
| `capability_domain_map` | `templates/capability_domain_map/minimal-contract.json` | `templates/capability_domain_map/reference-contract.json` | `templates/capability_domain_map/stress-contract.json` |
| `relationship_matrix` | `templates/relationship_matrix/minimal-contract.json` | `templates/relationship_matrix/reference-contract.json` | `templates/relationship_matrix/stress-contract.json` |

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

- The minimal template uses the default grouped/layered contract for simple ownership chains.
- The reference and stress templates use `variant: "domain_ownership_matrix"` for domain swimlanes, enterprise boundary, external partners, and bottom RACI/ownership tables.
- Matrix items use a dedicated compact card specification, separate from layered diagram cards; size them for two title lines plus one short subtitle.
- Place external partner panels below the enterprise boundary when cross-boundary relationships would otherwise cut across several domain lanes; route those links through domain-gap corridors.
- Use yellow/amber accents for governance or shared ownership in `accent-blueprint`.
- Use dashed connectors only for optional, indirect, shared-responsibility, or external-boundary links.

### Registry Table

Use for glossary, ontology, CTQ, risk, or parameter registries.

- Rows must include every declared column id.
- Use `rows[].kind` to drive semantic badges.
- Use `info_panels` for badge keys, ownership rules, metadata, or review notes that should remain visible beside the table.

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
- Use `info_panels` for relationship keys, use cases, operating rules, and review metadata instead of overcrowding the spoke labels.

### Object Relationship Diagram

Use for ER-style object models, entity relationship diagrams, MOC object links, or ontology-lite maps where attributes and cardinalities matter.

- Use `entities[]` rather than `nodes[]`; entity cards are table-like components, separate from layered cards.
- Use `entities[].attributes[].role` for `pk` and `fk` badges instead of relying on raw text only.
- Use relationship diamonds for named relationships and keep diamond labels short.
- Use `from_cardinality` and `to_cardinality` near endpoints when relationship multiplicity matters.
- Use entity `row`/`col` for card placement and relationship `row`/`col` for diamond placement. Half slots such as `col: 1.5` place diamonds between adjacent entity columns.
- Use self relationships for recursive fields such as `ParentCategoryID`; place the diamond explicitly and connect it to the entity from the nearest stable anchor.
- Place relationship diamonds before judging connector paths; cards should be arranged around those relationship slots so links stay short and structured.
- Use explicit `from_anchor` / `to_anchor` and `from_diamond_anchor` / `to_diamond_anchor` only when a dense local cluster makes automatic side selection ambiguous.
- Let non-axis links route as orthogonal polylines. Direct diagonal lines are a readability smell in dense ER diagrams.
- Keep enough horizontal and row corridor space for relationship diamonds; dense templates should widen the canvas and increase `entity_col_gap` / `entity_row_gap` rather than letting diamonds sit on entity cards.
- Do not use this type as a general graph renderer; when links become hard to read, split the model or move secondary relationships into an info panel.

### Ontology Map

Use for concept/class maps, glossary ontologies, semantic model sketches, and lightweight domain ontologies with examples.

- Use `concepts[]` rather than `entities[]`; concept cards show attributes and datatypes without PK/FK badges.
- Use `relationships[]` for ontology predicates. Keep predicate labels short enough to fit inside relationship diamonds.
- Use `instances[]` for example objects. Instances reference concepts and render as subordinate green cards, not relationship endpoints.
- Use `instances[].lane_offset` when several instance examples point to the same concept or would otherwise reuse the same long dashed corridor.
- Use `concept_anchor` and `instance_anchor` on an instance only when the automatic concept-to-instance link would cross a predicate diamond.
- Place relationship diamonds with `row`/`col` or polished `x`/`y` coordinates before judging connector paths; ontology maps reuse the object relationship geometry engine.
- Use side `info_panels` with `placement: "left"` or `placement: "right"` for legends, about/rules, and version cards when matching the blueprint reference style.
- Split the ontology if every concept needs many predicates; this type is for structured ontology maps, not arbitrary graph layout.

### Capability Domain Map

Use for enterprise capability maps, domain maps, operating-model decomposition, and capability gap discussions.

- Use `levels[]` for horizontal bands and `columns[]` for stable domain lanes.
- Use `items[]` with `level` and `column`; use `order` when multiple cards stack in one level/column cell.
- Use `levels[].kind/accent` and `columns[].kind/accent` for prominent header icons; do not put compact badges inside dense capability cards.
- Use `span` sparingly for strategic objectives or shared enablers that truly cover adjacent lanes.
- Keep connector overlays sparse. The map should remain readable from row/column alignment alone.
- Capability map cards use a dedicated dense-card spec: size them for two title lines plus one subtitle, and keep row/column gaps wide enough for side-corridor routing.
- When several connector overlays need the same vertical corridor, widen the canvas and use `relationships[].lane_offset` for the few routes that still need deliberate separation.
- Put usage rules, notes, and version blocks in `info_panels`; this type renders them as side panels to echo blueprint map conventions.
- Use the stress template to check whether the canvas should widen before shrinking text or card spacing.

### Relationship Matrix

Use for dense relationship coverage views where the primary diagram should become a small reference, not the main reading surface.

- Use `entities[]` as the single source for both row and column headers.
- Use `relationships[]` only for declared non-empty cells; empty cells are generated automatically.
- Use `type: "direct"`, `"indirect"`, or `"dependency"` and `strength: 1`, `2`, or `3`.
- Use `selected_cell` to drive the static detail panel. It may point to an empty cell if you want to explain a missing relationship, but both entities must exist.
- Keep auxiliary information in the built-in right-side detail, summary, and top-connected panels rather than adding explanatory dashboard blocks.
- Keep the primary preview panel reference-only. If users need to follow actual graph routes, use `object_relationship_diagram` or `ontology_map` as the primary diagram and link to a matrix companion view.
- Treat the first implementation as beta: run visual QA in `templates/template-gallery.html` before using it as a final production diagram.

## QA

Run:

```bash
py scripts/test_template_library.py
```

This checks every template contract, ensures expected SVGs are current, validates SVG geometry/style QA, and confirms the template gallery is up to date.
