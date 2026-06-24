# Standard Diagram Types

Use `diagram_type` for new contracts. `layout` is a legacy compatibility field and should not be used in new templates.

Run `py scripts/validate_semantic_contract.py contract.json` before rendering. The validator fails early when a contract mixes structures from different diagram types, references missing ids, or omits required fields.

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

Contract shape: `groups`, `nodes`, `edges`, `annotations`.

Renderer strategy: grouped/layered cards. Use containment and dashed responsibility links before adding dense edge meshes.

Schema rules are the same as `layered_knowledge_topology`.

## registry_table

Use for glossary, CTQ register, parameter register, risk register, status register, or compact index tables.

Contract shape: `columns`, `rows`, `annotations`.

Required fields:

- `columns[].id`
- `columns[].label`
- `rows[]` keyed by column id

Optional fields: `columns[].width`, `columns[].align`, `rows[].id`, `rows[].kind`, `rows[].accent`.

Unsupported structural fields: `groups`, `nodes`, `edges`, `hub_id`.

Rules: column ids must be unique; each row may only use column ids plus `id`, `kind`, and `accent`; each row must include every declared column id.

## taxonomy_tree

Use for classification trees, category hierarchies, rule trees, and parent-child knowledge taxonomies.

Contract shape: `nodes`, optional `edges`, `annotations`.

Preferred field: `nodes[].parent`.

Edges may express parent-child relationships when `nodes[].parent` is not used. If both are present and disagree, rendering fails.

Unsupported structural fields: `groups`, `columns`, `rows`, `hub_id`.

Rules: node ids must be unique; each parent must reference another node id; edge relations must be one of `parent`, `parent_of`, `contains`, `has_child`, or `classifies`; cycles are invalid.

## hub_spoke

Use for central hub/platform/module maps with surrounding comparable domains, capabilities, systems, or assets.

Contract shape: `hub_id`, `nodes`, `annotations`.

Required field: `hub_id` matching one node id.

Optional field: `nodes[].order` controls deterministic spoke placement.

Unsupported structural fields: `groups`, `columns`, `rows`, `edges`.

Rules: at least one spoke is required in addition to the hub; `nodes[].parent` and `nodes[].group` are not used by this type.
