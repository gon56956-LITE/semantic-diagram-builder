# Standard Diagram Types

Use `diagram_type` for new contracts. `layout` is a legacy compatibility field and should not be used in new templates.

Run `py scripts/validate_semantic_contract.py contract.json` before rendering. The validator fails early when a contract mixes structures from different diagram types, references missing ids, or omits required fields.

Use `references/diagram_type_maturity.md` to check whether a type has enough minimal, reference, stress, schema, renderer, validator, and gallery coverage to be treated as mature.

## layered_knowledge_topology

Use for abstraction layers, knowledge architecture, navigation/synthesis/source separation, and multi-row sibling layers.

Contract shape: `groups`, `nodes`, `edges`, `annotations`.

Renderer strategy: grouped/layered cards with optional row-level fan-out/fan-in routing.

Required fields: `groups[].id`, `groups[].label`, `nodes[].id`, `nodes[].label`, `nodes[].group`.

Rules: every node group must match a declared group; every edge endpoint must match a node id; `nodes[].row` and `nodes[].col` must be non-negative integers when provided.

## source_boundary_map

Use when the main message is derived knowledge versus authoritative controlled source material.

Contract shape: `groups`, `nodes`, `edges`, `annotations`.

Renderer strategy: grouped/layered cards. Put source-bound fan-in buses inside the source sibling layer and keep boundary labels out of connector corridors.

Schema rules are the same as `layered_knowledge_topology`.

## boundary_ownership_map

Use for domains, owners, stewards, applications, systems, data assets, and shared responsibility boundaries.

Default contract shape: `groups`, `nodes`, `edges`, `annotations`.

Default renderer strategy: grouped/layered cards. Use containment and dashed responsibility links before adding dense edge meshes.

Schema rules are the same as `layered_knowledge_topology`.

Variant: `domain_ownership_matrix`.

Use when the message is domain ownership, enterprise boundary, external partner boundary, and RACI/ownership assignments rather than layer-to-layer flow.

Contract shape: `boundary`, `domains`, `external_partners`, `relationships`, `ownership_key`, `ownership_assignments`, `annotations`.

Required fields:

- `variant: "domain_ownership_matrix"`
- `domains[].id`
- `domains[].label`
- `domains[].systems[].id` and `label` when systems are present
- `domains[].assets[].id` and `label` when assets are present

Optional fields:

- `boundary.label`
- `domains[].subtitle`, `kind`, `accent`, `owner`
- `external_partners[].id`, `label`, `subtitle`, `kind`, `accent`
- `relationships[].from`, `to`, `relation`, optional `style: "dashed"`, optional `accent`
- `ownership_key[].code`, `label`, `description`
- `ownership_assignments.columns[]` + `rows[]`, using the same column/row rules as `registry_table`

Rules: relationship endpoints must reference a domain, system, asset, or external partner id. Do not mix this variant with top-level `groups`, `nodes`, or `edges`.

## registry_table

Use for glossary, CTQ register, parameter register, risk register, status register, or compact index tables.

Contract shape: `columns`, `rows`, optional `info_panels`, `annotations`.

Required fields:

- `columns[].id`
- `columns[].label`
- `rows[]` keyed by column id

Optional fields: `columns[].width`, `columns[].align`, `rows[].id`, `rows[].kind`, `rows[].accent`, `info_panels[]`.

Unsupported structural fields: `groups`, `nodes`, `edges`, `hub_id`.

Rules: column ids must be unique; each row may only use column ids plus `id`, `kind`, and `accent`; each row must include every declared column id. Use `info_panels` for legend, owner, version, rule, or review metadata that would make the table itself too wide.

## taxonomy_tree

Use for classification trees, category hierarchies, rule trees, and parent-child knowledge taxonomies.

Contract shape: `nodes`, optional `edges`, `annotations`.

Preferred field: `nodes[].parent`.

Edges may express parent-child relationships when `nodes[].parent` is not used. If both are present and disagree, rendering fails.

Unsupported structural fields: `groups`, `columns`, `rows`, `hub_id`.

Rules: node ids must be unique; each parent must reference another node id; edge relations must be one of `parent`, `parent_of`, `contains`, `has_child`, or `classifies`; cycles are invalid.

## hub_spoke

Use for central hub/platform/module maps with surrounding comparable domains, capabilities, systems, or assets.

Contract shape: `hub_id`, `nodes`, optional `info_panels`, `annotations`.

Required field: `hub_id` matching one node id.

Optional fields: `nodes[].order` controls deterministic spoke placement; `info_panels[]` adds bottom legend/use-case/rule panels.

Unsupported structural fields: `groups`, `columns`, `rows`, `edges`.

Rules: at least one spoke is required in addition to the hub; `nodes[].parent` and `nodes[].group` are not used by this type. Use `info_panels` rather than adding many dashed spokes when the relationship semantics need explanation.

## object_relationship_diagram

Use for object relationship diagrams, data-model sketches, MOC object links, ontology-lite entity maps, and ER-style views that need objects, attributes, relationships, keys, and cardinalities.

Contract shape: `entities`, `relationships`, optional `info_panels`, `annotations`.

Renderer strategy: ER-style entity table cards plus relationship diamonds. Explicit entity `row`/`col` controls table placement. Relationship `row`/`col` controls diamond placement on the same ER grid; half slots such as `col: 1.5` place diamonds between adjacent entity columns. Explicit relationship `x`/`y` is still accepted for rare manual overrides but should not be the normal template style.

Required fields:

- `entities[].id`
- `entities[].label`
- `relationships[].from`
- `relationships[].to`
- `relationships[].label`

Optional fields:

- `entities[].row`, `col`, `x`, `y`, `width`, `height`
- `entities[].kind`, `accent`, `weak`
- `entities[].attributes[].name`, optional `role: "pk" | "fk" | "attribute" | "derived"`, optional `type`
- `relationships[].id`, `style`, `accent`, `from_cardinality`, `to_cardinality`, `row`, `col`, `x`, `y`, `diamond_width`, `diamond_height`
- `relationships[].from_anchor`, `to_anchor`, `from_diamond_anchor`, `to_diamond_anchor` as `left`, `right`, `top`, or `bottom` for dense layouts where automatic anchor choice is ambiguous
- `info_panels[]` for legend, cardinality key, scope notes, or version metadata

Unsupported structural fields: `groups`, `nodes`, `edges`, `columns`, `rows`, `hub_id`, `domains`, `external_partners`.

Rules: every relationship endpoint must reference an entity id; self relationships are supported for hierarchy or recursive ownership relations when the relationship has explicit `row`/`col` or `x`/`y` placement. Relationship labels render inside diamonds, so keep them short. Use `weak: true` for dashed weak-entity cards. Use PK/FK roles instead of embedding key semantics only in the attribute name. Plan relationship diamonds as fixed slots before evaluating connector paths; non-axis relationship links should route as orthogonal polylines rather than direct diagonals. Use explicit card or diamond anchors when a relationship sits near another diamond and the automatic side would make the connector appear to start or end on the wrong corner.

## capability_domain_map

Use for strategic objectives, business domains, sub-domains, capabilities, enabling capabilities, and sparse support/dependency overlays.

Contract shape: `levels`, `columns`, `items`, optional `relationships`, optional `info_panels`, optional `annotations`.

Renderer strategy: banded capability map with dedicated left-side level labels, stable column lanes, dense but legible capability cards, sparse orthogonal connector overlays, and right-side `info_panels`.

Required fields:

- `levels[].id`
- `levels[].label`
- `columns[].id`
- `columns[].label`
- `items[].id`
- `items[].label`
- `items[].level`
- `items[].column`

Optional fields:

- `levels[].kind`, `accent`
- `columns[].width`, `kind`, `accent`
- `items[].subtitle`, `kind`, `accent`, `order`, `span`
- `relationships[].from`, `to`, `relation`, optional `style`, optional `accent`
- `info_panels[]` for usage, notes, version, legend, or scope panels

Unsupported structural fields: `groups`, `nodes`, `edges`, `rows`, `hub_id`, `domains`, `external_partners`, `entities`.

Rules: every item must reference a declared level and column. `items[].span` is a positive integer and should be used sparingly for objectives or shared enablers. Relationship endpoints must reference item ids and should remain sparse; the primary reading path is the grid alignment, not the connector mesh. Use this type when row/column alignment is the message; use `boundary_ownership_map` when ownership and external boundaries are the message.

Spacing rules: capability cards are not the same component as layered topology cards. They reserve enough height for two title lines plus one short subtitle, and the renderer enforces wider row/column corridors so same-column stacked cards can route around each other without touching neighboring cards. Repeated same-corridor routes are offset into lanes; if many same-color overlays still compete for attention, widen the canvas or split the dependencies into a separate view.

Header icon rules: dense capability cards do not render per-card badges. Use `levels[].kind/accent` and `columns[].kind/accent` to render prominent semantic icons in the row and column headers; the cards themselves stay focused on title and subtitle text.

## Planned Candidate Types

The following types have design intent but are not mature renderer strategies yet. Do not declare them as `diagram_type` until they are promoted into the registry.

### ontology_map

Use for formal concept/class maps that need class boxes, relationship diamonds or labeled predicates, datatype attributes, and instance examples.

Likely contract shape: `concepts`, `relationships`, optional `instances`, `datatypes`, `legend`, and `info_panels`.

First strategy goal: constrained ontology layout with class lanes or clusters, explicit relationship labels, and separate instance/datatype styling so it does not collapse into a generic graph.

First stress focus: class/instance differentiation, relationship-label readability, one-to-many cardinality labels, and avoiding graph spaghetti.

## Shared info_panels

`registry_table`, `hub_spoke`, `object_relationship_diagram`, and `capability_domain_map` support information panels for dense legends, rules, use cases, metadata, cardinality keys, relationship keys, or usage notes.

Fields:

- `info_panels[].title`
- `info_panels[].items[]` as strings or objects
- Optional `info_panels[].id`, `kind`, `accent`
- Optional item object fields: `label`, `value`, `text`, `kind`, `accent`
