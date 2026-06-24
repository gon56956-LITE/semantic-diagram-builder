# Standard Diagram Types

Use `diagram_type` for new contracts. `layout` is a legacy compatibility field and should not be used in new templates.

## layered_knowledge_topology

Use for abstraction layers, knowledge architecture, navigation/synthesis/source separation, and multi-row sibling layers.

Contract shape: `groups`, `nodes`, `edges`, `annotations`.

Renderer strategy: grouped/layered cards with optional row-level fan-out/fan-in routing.

## source_boundary_map

Use when the main message is derived knowledge versus authoritative controlled source material.

Contract shape: `groups`, `nodes`, `edges`, `annotations`.

Renderer strategy: grouped/layered cards. Put source-bound fan-in buses inside the source sibling layer and keep boundary labels out of connector corridors.

## boundary_ownership_map

Use for domains, owners, stewards, applications, systems, data assets, and shared responsibility boundaries.

Contract shape: `groups`, `nodes`, `edges`, `annotations`.

Renderer strategy: grouped/layered cards. Use containment and dashed responsibility links before adding dense edge meshes.

## registry_table

Use for glossary, CTQ register, parameter register, risk register, status register, or compact index tables.

Contract shape: `columns`, `rows`, `annotations`.

Required fields:

- `columns[].id`
- `columns[].label`
- `rows[]` keyed by column id

Optional fields: `columns[].width`, `columns[].align`, `rows[].id`, `rows[].kind`, `rows[].accent`.

## taxonomy_tree

Use for classification trees, category hierarchies, rule trees, and parent-child knowledge taxonomies.

Contract shape: `nodes`, optional `edges`, `annotations`.

Preferred field: `nodes[].parent`.

Edges may express parent-child relationships when `nodes[].parent` is not used. If both are present and disagree, rendering fails.

## hub_spoke

Use for central hub/platform/module maps with surrounding comparable domains, capabilities, systems, or assets.

Contract shape: `hub_id`, `nodes`, `annotations`.

Required field: `hub_id` matching one node id.

Optional field: `nodes[].order` controls deterministic spoke placement.
