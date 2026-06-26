# Diagram Type Maturity Matrix

Use this matrix to decide whether a standard `diagram_type` is mature enough to use as a reusable template family. A mature type has a clear contract shape, a predictable layout strategy, representative templates, stress coverage, and automated QA for its known failure modes.

## Maturity Levels

| Level | Meaning | Required Evidence |
| --- | --- | --- |
| `minimal` | The smallest valid contract renders correctly and teaches the required fields. | `minimal-contract.json`, `minimal.svg`, contract validation, SVG validation. |
| `reference` | A normal real-world example shows the intended visual pattern and semantic affordances. | `reference-contract.json`, `reference.svg`, readable labels, meaningful accents, representative annotations or panels. |
| `stress` | Dense content exposes routing, typography, wrapping, canvas, and style limits before users hit them in production. | `stress-contract.json`, `stress.svg`, template gallery entry, regression assertions for the known failure modes. |
| `mature` | The renderer, schema, docs, and QA all encode the lessons from minimal/reference/stress. | Type docs, template docs, schema checks, renderer tests, validator checks, gallery QA. |

## Type Matrix

| Diagram Type | Current Maturity | Minimal Coverage | Reference Coverage | Stress Coverage | Must-Pass QA |
| --- | --- | --- | --- | --- | --- |
| `layered_knowledge_topology` | Mature for grouped layered maps | Single grouped/layered contract with nodes and edges. | Multiple layers with navigation, synthesis, derived knowledge, and source boundary. | Multi-row sibling layer with fan-out/fan-in and explicit row/col placement. | Row-level bus stays inside layer; title does not collide with routes; direct vertical fan-in stays direct; card type scale is diagram-level consistent. |
| `source_boundary_map` | Mature for source-bound grouped maps | Simple derived/source boundary chain. | Accent Blueprint boundary map with controlled-source semantics. | Dense source/derived layer routing with fan-in/fan-out clearance. | Fan-in bus stays in source sibling layer; source-to-target direct path is preferred when aligned; boundary labels stay out of connector corridors. |
| `boundary_ownership_map` | Mature for grouped ownership and `domain_ownership_matrix` variant | Simple grouped/layered ownership chain. | Domain ownership matrix with enterprise boundary, external partners, RACI key, and assignment table. | Dense domain lanes, multiple systems/assets, external partners, RACI rows, and external relationship corridors. | Matrix cards fit two title lines plus subtitle; external partner panel sits below enterprise boundary when side placement would cause crossings; external links use domain-gap corridors with slight lane offsets. |
| `registry_table` | Mature for dense semantic registers | Basic columns, rows, semantic badges. | Compact register with definitions, owner, type, and related items. | Wide multi-column register with long definitions, status, risk, evidence, related items, and `info_panels`. | Column widths do not compress below readability; canvas expands for dense columns; header labels remain legible; badges are semantic; info panels render as visible bottom panels. |
| `taxonomy_tree` | Mature for deterministic trees with dense leaves | Root and children with parent links. | Multi-level taxonomy with level labels and parent-child connectors. | Dense leaf level wraps into multiple rows and uses separate local fan-out corridors. | Dense levels wrap instead of forcing huge canvas; parent groups use distinct connector colors; wrapped fan-out corridors and row lanes are staggered; connectors do not become visually ambiguous. |
| `hub_spoke` | Mature for designed hub-spoke maps | Center hub plus comparable spokes. | Designed hub core and spoke blocks with dashed optional relation. | Many spokes with mixed semantics, dashed spokes, and bottom `info_panels`. | Hub/spoke blocks are designed components, not generic cards; canvas height is content-driven; info panels count as content; dashed spokes are explained by relationship keys or notes. |
| `object_relationship_diagram` | Reference implementation for ER-style object maps | Two entities with attributes, a relationship diamond, and cardinality labels. | Multi-entity object relationship map with PK/FK badges, weak entity, relationship diamonds, and cardinality key. | Dense object model with many entities, mixed relationship styles, fixed relationship slots, orthogonal routes, and info panels. | Entity cards use table-like sizing; relationship endpoints reference entities; diamonds use row/col slots; non-axis links route orthogonally; cardinality labels stay readable. |
| `ontology_map` | Reference implementation for ontology-style concept maps | Two concepts, a predicate diamond, cardinality labels, and an instance example. | Blueprint ontology map with concepts, attributes, relationship diamonds, instances, side legend/about/rules/version panels. | Dense concept map with multiple concept rows, many predicate diamonds, instance row, side panels, and bottom metadata panel. | Concept cards are not ER table cards; instances remain subordinate; relationship diamonds reuse fixed-slot routing; side panels do not overlap concept geometry. |
| `capability_domain_map` | Reference implementation for banded capability maps | Two levels, two columns, domain/capability items, and side usage panel. | Blueprint capability/domain map with objectives, domains, sub-domains, capabilities, enablers, and side panels. | Wide dense map with many columns, stacked sub-domains/capabilities, shared enablers, and sparse dependency overlays. | Level labels and column labels remain readable; stacked cards do not overlap; sparse connectors stay in row gaps; side panels render as readable blueprint blocks. |

## Shared Maturity Rules

- Every standard type needs `minimal`, `reference`, and `stress` contracts plus rendered SVGs.
- `templates/template-gallery.html` should include reference and stress entries, not minimal entries.
- Stress examples should be deliberately complex enough to reveal issues; tiny examples are not a valid stress baseline.
- The renderer should fail or warn when the contract shape is mixed across diagram types.
- Style packages may change visual tokens, but they must not change routing or layout semantics.
- Generated examples must be validated with both contract/schema checks and SVG geometry/style checks.

## Known Failure Modes To Preserve In QA

| Failure Mode | Applies To | QA Rule |
| --- | --- | --- |
| Fan-out/fan-in bus collides with layer title. | `layered_knowledge_topology`, `source_boundary_map` | Layer height must include bus/trunk channels and clearance. |
| Rounded connector elbow bends backward. | All routed types | Rounded `Q` elbows must turn in the direction of travel; vertical direct links must not add unnecessary side bends. |
| Dense sibling row creates unreadable edge mesh. | `taxonomy_tree`, layered maps | Use per-parent corridors, lane staggering, and connector colors for dense fan-out groups. |
| External partner links cross several domain lanes. | `boundary_ownership_map` | Put external partner panel below enterprise boundary and route through domain-gap corridors. |
| Matrix cards reuse generic card sizing and clip content. | `boundary_ownership_map` | Matrix item cards use a dedicated compact spec sized for two title lines plus one subtitle. |
| Wide table squeezes column headers and cells. | `registry_table` | Canvas expands when declared column widths exceed available width. |
| Notes, legends, or metadata become tiny unreadable text. | `registry_table`, `hub_spoke` | Use `info_panels` with readable title/item type sizes and include them in canvas density checks. |
| Hub-spoke becomes generic cards around a circle. | `hub_spoke` | Use designed hub core, designed spoke blocks, and relationship/use-case panels. |
| Object relationship map becomes a generic graph. | `object_relationship_diagram` | Use entity table cards, relationship diamonds, PK/FK badges, and endpoint cardinality labels. |
| Relationship diamonds collide with entity cards. | `object_relationship_diagram` | Reserve horizontal and row corridors for diamonds; prefer relationship `row`/`col` slots over raw `x`/`y`. |
| Dense ER links become ambiguous diagonal lines. | `object_relationship_diagram` | Relationship diamonds use fixed row/column slots, and non-axis card-to-diamond links route as orthogonal polylines. |
| Relationship cardinality labels collide with entity cards or diamonds. | `object_relationship_diagram` | Place labels near anchors with enough clearance; use explicit diamond placement in reference templates. |
| Ontology map degenerates into an ER table. | `ontology_map` | Use concept cards without PK/FK badges, instance cards, datatype rows, and side panels. |
| Ontology side panels collide with the concept core. | `ontology_map` | Reserve side-panel gutters or use explicit concept `x`/`y` placement in reference-style maps. |
| Capability maps become unreadable spiderwebs. | `capability_domain_map` | Keep relationships sparse; alignment and banding must carry the primary structure. |
| Capability cards stack or span into adjacent lanes. | `capability_domain_map` | Use row/column slots, stack ordering, and canvas widening before shrinking text. |
| Accent Blueprint becomes generic dark dashboard. | All Accent Blueprint outputs | Keep deep blue grid/white linework as the base; use accents sparingly for semantic differentiation. |

## Promotion Checklist

Before marking a new diagram type or variant as mature:

1. Contract schema validates the type-specific shape and rejects mixed structures.
2. Renderer strategy is separate enough that new geometry is not hidden inside unrelated type branches.
3. Minimal/reference/stress templates exist and render to current SVGs.
4. Template gallery includes reference and stress examples.
5. `scripts/test_render_semantic_diagram.py` checks the unique geometry or component behavior.
6. `scripts/test_contract_schema.py` checks at least one valid and one invalid contract shape.
7. `scripts/validate_semantic_svg.py` recognizes the type's rendered content for density and connector checks.
8. `references/diagram_types.md` documents contract fields and unsupported fields.
9. `references/templates.md` documents when to choose the type and how to avoid known design failures.
10. Visual QA confirms readable text, no connector/card collisions, and style-specific fidelity.

## Candidate New Types

These are good next candidates because they are common semantic diagrams but need distinct strategies rather than being forced into layered layouts.

| Candidate Type | Why Add It | Likely Strategy | First Stress Focus |
| --- | --- | --- | --- |
| `relationship_matrix` | Dense many-to-many semantic relationships where a graph would be unreadable. | Matrix/table hybrid. | Row/column label readability, sparse cell semantics, and legend clarity. |
