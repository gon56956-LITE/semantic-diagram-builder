# Layout Patterns

Use these patterns as selection guidance. They are not templates with fixed domain content.

## layered_knowledge_topology / source_boundary_map / boundary_ownership_map

Use for knowledge architecture, abstraction layers, source-boundary maps, and navigation/synthesis/source separation.

Rules:
- Start from `references/layout_metrics.md` for card height, sibling spacing, row spacing, layer height, and layer gap.
- Put layer bands in the background.
- Keep layer labels away from cards and away from bus corridors. A layer label may occupy the inter-layer gap, but connector buses should not.
- Route cross-layer edges with rounded orthogonal elbows.
- Put fan-out horizontal buses inside the target/sibling layer, not in the gap above it.
- Put fan-in horizontal buses inside the source/sibling layer, then cross into the next layer with a single trunk.
- For parallel cards, split and merge edges within the same layer as the cards they organize; avoid merging inside the downstream layer title area.
- If routing space is tight, enlarge the layer band or move cards vertically; do not let buses collide with labels, annotations, or boundary captions.
- If a layer uses a class/backbone pill, reserve a gutter between that pill and the content cards so they do not collide.
- Put explanatory text in footer, side callouts, or layer whitespace, not on connector corridors.

## taxonomy_tree

Use for parent-child trees, object taxonomies, and nested concept maps.

Rules:
- Prefer top-down tree if depth matters.
- Prefer left-right tree if labels are long.
- Collapse dense children into summary nodes when there are too many leaves.

## hub_spoke

Use when one central object organizes multiple domains, capabilities, routes, or entry points.

Rules:
- Center is the hub; spokes should be semantically comparable.
- Avoid crossing spokes with secondary edges; move secondary relations to a legend or separate detail diagram.

## topology guidance

Use for non-tree object relationship maps.

Rules:
- Use clusters/groups to reduce spaghetti.
- Keep primary edges visually stronger than secondary edges.
- If edges cross often, split into multiple diagrams.

## source_boundary_map

Use when the key message is a boundary between source-of-truth objects and derived/synthesis/navigation objects.

Rules:
- Make the boundary visually explicit.
- Do not imply derived notes replace controlled source documents.
- Place authority/disclaimer notes in footer or boundary band, not on arrows.

## boundary_ownership_map: domain_ownership_matrix

Use when a boundary/ownership map needs to show who owns domains, systems, assets, external partners, and RACI assignments in one technical blueprint.

Rules:
- Use `diagram_type: "boundary_ownership_map"` with `variant: "domain_ownership_matrix"`.
- Put the enterprise boundary in the main canvas and render each domain as a vertical swimlane column.
- Put systems/applications and data/assets inside their owning domain column; keep external partners outside the enterprise boundary.
- Put shared responsibility and optional external links in sparse dashed connectors. Do not use dashed styling as decoration.
- Put ownership key and assignment rows in the bottom band so the main boundary map remains readable.
- Prefer this variant when the main question is "who owns what?" Use the default grouped/layered variant when the main question is "how does ownership flow across layers?"

## Multi-row sibling routing

Use this when one sibling set no longer fits in a single readable row.

Rules:
- Increase canvas width before shrinking cards. If the set is still too wide, split the sibling set into rows while preserving readable card width and label rhythm.
- Give each row its own fan-out bus and fan-in bus. Do not reuse one crowded bus channel for both split and merge routes.
- Route fan-out to a lower row through a clear center gap or side gutter; the route must not pass through row-1 cards or crowd their arrowheads.
- Route fan-in from each row below that row's cards, then merge with one cross-layer trunk after the row-level buses have converged.
- Shared buses and trunks normally have no arrow marker; only terminal branches entering cards, pills, or source nodes should carry arrowheads.
- Branches into or out of a bus must be route-level rounded elbows. Do not draw a straight vertical branch that visually T-bones into a horizontal bus.
- If fan-out and fan-in coexist in the same layer, use distinct styles or colors and keep the legend outside all bus corridors.

Bundled renderer behavior:
- Use `nodes[].row` and `nodes[].col` to lock multi-row sibling placement when the diagram must be reproducible.
- Set `groups[].routing.mode` to `row_bus_side_trunk` to force row-level routing. In `auto`, this mode is selected when a group has more than one row and participates in fan-out or fan-in.
- `routing.fanout_side` defaults to `right`; `routing.fanin_side` defaults to `left`.
- Set `routing.mode` to `simple` only when you intentionally want the older per-edge elbow routing and will visually inspect the result.
