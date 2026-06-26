# Diagram Type Production Readiness

Use this guide when choosing a `diagram_type` for real work. It answers a different question from `diagram_type_maturity.md`.

- Maturity asks: does the type have schema, renderer, templates, stress examples, and automated QA?
- Readiness asks: can this type be used for production diagrams today, and what authoring discipline does it require?

## Readiness Tiers

| Tier | Meaning | Production Rule |
| --- | --- | --- |
| `stable` | Safe for normal production use when the contract follows the documented shape. | Use directly from the reference template; run renderer and validator before delivery. |
| `beta` | Suitable for production after visual review, but dense layouts still need deliberate placement. | Start from the reference or stress template; expect to tune slots, lanes, or panels. |
| `experimental` | Useful for prototypes or design exploration, not yet reliable for repeated production use. | Do not use as a final diagram without manual review and likely SVG adjustment. |

## Current Readiness

| Diagram Type | Tier | Best For | Authoring Discipline | Main Risk | Next Hardening Step |
| --- | --- | --- | --- | --- | --- |
| `layered_knowledge_topology` | `stable` | Layered knowledge architecture, navigation-to-source maps, grouped dependency maps. | Use explicit `row`/`col` for multi-row sibling sets; keep fan-out/fan-in inside the layer. | Too many cross-layer edges can still become a bus diagram rather than a readable topology. | Add more real OCS-style stress contracts with 8-12 cards per layer. |
| `source_boundary_map` | `stable` | Derived knowledge versus controlled source authority. | Keep source-bound fan-in inside the source sibling layer; mark controlled-source boundary clearly. | Source boundary can become visually weak if it is only a final card rather than a band or panel. | Add a dense source-authority template with multiple source families. |
| `boundary_ownership_map` | `stable` for `domain_ownership_matrix`; `beta` for generic grouped ownership maps | Enterprise domains, systems, assets, external partners, owner/steward responsibility. | Prefer `variant: "domain_ownership_matrix"` when domains and ownership are the message. Put external partners below or outside the enterprise boundary when side placement causes crossings. | Generic grouped ownership maps can look like layered topology without enough ownership semantics. | Promote the matrix variant as the default production template; keep grouped maps as simple starter examples. |
| `registry_table` | `stable` | Glossaries, CTQ registers, parameter/risk/status registers. | Declare column widths; let canvas widen for dense tables; move rules/metadata into `info_panels`. | Long definitions and many columns can turn the table into a tiny dashboard. | Add cell-level wrapping tests for long CJK/English mixed labels. |
| `taxonomy_tree` | `stable` | Classification hierarchies, category trees, rule trees. | Use parent-child data; order siblings deliberately; allow dense leaf levels to wrap into multiple rows. | Dense same-level leaves can make parent-child origins ambiguous without color/lane separation. | Add a second stress template with multiple parents fanning into wrapped leaf rows. |
| `hub_spoke` | `stable` | Hub/platform/module maps with comparable spokes and a clear center. | Keep spokes comparable; use `info_panels` for use cases and relationship keys instead of many edge labels. | Overloading the hub with too many heterogeneous spokes makes the layout decorative rather than explanatory. | Add a variant for grouped spokes or ring sections before supporting very large hub maps. |
| `object_relationship_diagram` | `stable` | ER-style object maps, MOC objects, table-like entities with attributes, relationship diamonds, cardinality. | Plan entity rows/columns and relationship diamond slots before rendering. Use `lane_offset` or explicit anchors when two relationships share a corridor or sit close together. | Arbitrary graph placement is still out of scope; production diagrams should stay on the entity/relationship grid. | Add more domain-specific examples, such as MOC object maps and revision-controlled object models. |
| `ontology_map` | `stable` | Concept/class maps with predicates, datatype attributes, cardinality, instances, and bottom panels. | Use concepts for class semantics, instances only as examples, and bottom panels for legend/rules/version. Keep predicates short and use `lane_offset` when several instance links or predicates share a corridor. | It can drift into either ER-table style or a generic graph if concepts, instances, and predicates are not clearly separated. | Add domain-specific ontology templates such as MOC glossary ontology and WI-derived knowledge ontology. |
| `capability_domain_map` | `stable` | Strategic objectives, domains, sub-domains, capabilities, enablers, and sparse dependencies. | Let row/column alignment carry the meaning; keep relationship overlays sparse; use row/column header icons instead of per-card badges, and use `lane_offset` only for deliberate shared-corridor overlays. | Dense dependencies can quickly become a mesh even when cards are readable. | Add a dependency-focused companion view or relationship matrix for high-link cases. |
| `relationship_matrix` | `beta` | Companion view for high-connectivity same-entity relationships. | Use the same entity set for rows/columns; keep relationship types to `direct`, `indirect`, and `dependency`; use strengths sparingly; keep primary preview reference-only and support panels below the main matrix. | It can become a generic dark dashboard if support panels, numbers, and accents dominate the matrix. | Visual QA the reference/stress gallery, then decide whether the bottom-panel proportions and matrix density are stable enough to promote. |

## Selection Rules

Choose the type whose primary structure matches the message:

| Primary Message | Use | Avoid |
| --- | --- | --- |
| Knowledge layers, abstraction levels, source authority flow | `layered_knowledge_topology` or `source_boundary_map` | `capability_domain_map` unless columns are the message. |
| Domain ownership, boundaries, external parties, RACI-like assignment | `boundary_ownership_map` with `variant: "domain_ownership_matrix"` | Generic `layered_knowledge_topology` when ownership is the main message. |
| Rows and columns are the content | `registry_table` | Any node-link diagram. |
| Parent-child classification | `taxonomy_tree` | `object_relationship_diagram` unless relationships are non-hierarchical. |
| One central platform/module with comparable surrounding modules | `hub_spoke` | `layered_knowledge_topology` when there is no true center. |
| Entity/object attributes, keys, relationships, and cardinality | `object_relationship_diagram` | `ontology_map` unless class/instance semantics are important. |
| Concepts/classes, predicates, datatype properties, example instances | `ontology_map` | `object_relationship_diagram` when PK/FK table structure is the real message. |
| Capabilities organized by bands and domains | `capability_domain_map` | `taxonomy_tree` when there is no stable column/domain axis. |
| Relationship coverage, strength, and type comparison across the same entity set | `relationship_matrix` | Primary node-link diagrams when the relationship mesh is already too dense to read. |

## Production Checklist

Before using a diagram type in a real deliverable:

1. Start from `templates/<diagram_type>/reference-contract.json` or `stress-contract.json`, not from a blank file.
2. Check the tier. For `beta` types, plan slots and lanes explicitly before judging the output.
3. Keep the contract shape pure. Do not mix `groups/nodes`, `columns/rows`, `entities`, `concepts`, or `levels/items` in the same contract.
4. Run `py scripts/validate_semantic_contract.py <contract.json>` when the contract is external or hand-authored.
5. Render with `py scripts/render_semantic_diagram.py <contract.json> <output.svg>`.
6. Run `py scripts/validate_semantic_svg.py <output.svg>`.
7. Inspect in the gallery or target note at the actual presentation size.
8. If the diagram needs many special manual coordinates, stop and reassess whether a different type or variant is a better fit.

## When To Split A Diagram

Split the diagram instead of forcing one canvas when:

- A `layered_knowledge_topology` needs more than two dense cross-layer relationship families.
- A `taxonomy_tree` has many parents and many wrapped leaf rows with overlapping fan-out corridors.
- An `object_relationship_diagram` or `ontology_map` needs more than 10 relationship diamonds with overlapping lanes.
- A `capability_domain_map` needs dependency overlays between most columns.
- A `registry_table` needs both many columns and long paragraph definitions.
- A `relationship_matrix` needs more than about 12-14 entities or requires different row and column entity sets.

The renderer should preserve clarity, not prove that every relation can fit into one SVG.
