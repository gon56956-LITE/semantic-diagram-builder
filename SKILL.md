---
name: semantic-diagram-builder
description: Build contract-driven semantic diagrams as clean SVGs for knowledge maps, hierarchy maps, layered topologies, source-boundary maps, MOC/object relationship maps, ontology maps, capability maps, and other non-sequential object-relation diagrams. Use when the user wants a designed diagram of concepts, knowledge objects, groups, boundaries, dependencies, or navigation structure rather than a time-ordered workflow.
metadata:
  short-description: Build semantic object-relation SVG diagrams
---

# Semantic Diagram Builder

Use this skill to turn a set of objects, groups, boundaries, annotations, and relationships into an Obsidian/PPT-ready SVG diagram.

This is not a workflow skill. If the diagram is mainly an execution sequence, process flow, SOP/WI step order, or agent/tool workflow, use `workflow-builder` instead. If it is a fishbone, fault tree, FMEA, prioritization matrix, or roadmap, use `brainstorm-diagrams`. If it is an optical physical/path diagram, use `opticflow-diagrams`.

## Core workflow

1. Build a semantic contract before rendering.
   - What are the nodes?
   - What are the groups/layers/boundaries?
   - What relation does each edge mean?
   - Which text is an annotation rather than a node?
   - Which node is the entry point or source of truth?
2. Choose a layout pattern.
   - `layered`: abstraction layers, knowledge architecture, source-boundary maps.
   - `hierarchy`: parent-child object trees.
   - `hub_spoke`: one center with surrounding domains/capabilities.
   - `topology`: object-relation maps with non-tree connections.
   - `boundary_map`: source-of-truth vs derived/synthesis objects.
   - `auto`: choose the closest pattern from the contract.
3. Apply stable layout metrics from `references/layout_metrics.md` before rendering or manual SVG edits.
4. Render an SVG with `scripts/render_semantic_diagram.py` when possible.
5. Run automated QA with `scripts/validate_semantic_svg.py` and then visual QA before presenting the diagram.

## Contract fields

Prefer JSON for deterministic script execution. YAML-like drafts are fine for discussion, but convert to JSON before running the bundled renderer unless PyYAML is available.

Minimum contract:

```json
{
  "title": "Diagram title",
  "subtitle": "Optional subtitle",
  "layout": "auto",
  "groups": [
    {"id": "g1", "label": "Group label", "type": "layer"}
  ],
  "nodes": [
    {"id": "n1", "label": "Node label", "subtitle": "Optional", "kind": "object", "group": "g1"}
  ],
  "edges": [
    {"from": "n1", "to": "n2", "relation": "related_to", "style": "primary"}
  ],
  "annotations": [
    {"text": "Optional note", "placement": "footer"}
  ]
}
```

Useful node fields:

- `id`: stable unique id.
- `label`: card title; the renderer wraps long labels.
- `subtitle`: small secondary label.
- `kind`: semantic category used for icon/accent. Common values: `hub`, `index`, `query`, `glossary`, `process`, `quality`, `risk`, `package`, `source`, `ontology`, `registry`, `capability`, `evidence`, `decision`, `object`.
- `group`: group/layer id.
- `importance`: `primary`, `normal`, or `secondary`.

Useful edge fields:

- `from`, `to`: node ids.
- `relation`: semantic relation; keep it source-faithful.
- `style`: `primary`, `secondary`, or `dashed`.
- `label`: use sparingly; prefer legends/annotations when labels would collide with paths.

Useful annotation placements:

- `footer`: below the main structure.
- `group:<group_id>`: inside a group band, away from connector corridors.
- `side`: side callout.
- `legend`: compact legend area.

## Layout and design rules

- Use the standard layout metrics unless there is a justified exception: content-card height, sibling spacing, row spacing, layer height, and layer gap should be systematic rather than hand-tuned per layer. See `references/layout_metrics.md`.
- Prefer rounded orthogonal elbow connectors over long diagonal curves.
- Do not place annotations on connector corridors, bus lines, or junctions.
- Keep group/layer labels separated from cards. In layered diagrams, labels may sit in the inter-layer gap or a safe label gutter, but never in an active bus corridor.
- Use bus/junction structure when multiple edges converge. Put horizontal bus channels inside the layer they organize: fan-out buses inside the target/sibling layer, fan-in buses inside the source/sibling layer before crossing the boundary. Avoid placing these buses in inter-layer gaps where they compete with layer titles.
- For fan-out into parallel sibling cards, place the horizontal bus inside the target layer above the cards, with clear vertical space before arrowheads enter the card tops.
- For fan-in from parallel sibling cards, place the horizontal merge bus inside the source layer below the cards, then use one trunk for the cross-layer transition.
- For parallel sibling cards with split or merge edges, complete the split/merge within the sibling layer and use one trunk for the cross-layer transition. If the bus needs room, increase the layer band height instead of pushing the bus into the gap.
- Use semantic icons and accent colors; do not use identical generic badges for every node unless the contract has no semantic kind. QA icon paths: a badge/icon must stay inside the card and must not look like a connector.
- Wrap long labels rather than letting text overflow. Give cards enough width and height for the icon, two title lines, and subtitle; do not let icons collide with title text.
- Prefer containment or legends over many unclear dashed edges. Dashed relations must have an obvious semantic meaning or be explained by a label/legend.
- Split dense diagrams instead of shrinking everything until unreadable.
- Default cards should be light-background with high-contrast text.
- Avoid external JS, external fonts, or browser-only features.

## Visual QA checklist

Before final delivery, verify:

- SVG opens or embeds in the target note.
- No invalid fill/stroke values such as `fill="moc"`.
- Text is readable at Obsidian preview scale.
- No annotation overlaps an edge or arrowhead.
- No group/layer title overlaps a card.
- No card title/subtitle collision.
- Connectors do not run through cards.
- Arrowheads are not hidden inside corners or text, and they point into the side/top/bottom anchor they visually enter.
- Rounded elbows bend in the direction of travel; no curled or backward-facing corners. Orthogonal connector turns should use rounded corners, not hard 90-degree corners, when the SVG is manually authored.
- QA both single-path turns and multi-path visual junctions. A vertical branch meeting a horizontal bus is still a hard T-junction unless the branch curves into the bus with a `Q` elbow.
- Icons are semantically distinct when node kinds differ, and icon strokes stay inside the badge/card.
- Card heights, sibling gaps, row gaps, layer heights, layer y-positions, layer bottom padding, and layer gaps follow the metric system in `references/layout_metrics.md` or have a visible reason to differ. Layer height is derived from actual card bounds plus padding; layer y-position is derived from previous layer height plus gap. Do not choose fixed container positions first and force content into them.
- Layer containers are tall enough for all contained cards; no card protrudes outside its layer band.
- Run `py scripts/validate_semantic_svg.py output.svg` when possible, then run `git diff --check` for generated SVGs when working in a git repo.

## Script usage

```bash
py scripts/render_semantic_diagram.py examples/ocs-r300-layered-contract.json output.svg
```

The script is a conservative generic renderer, not a full diagram engine. If a diagram needs a special layout, use the script output as a starting point and make surgical SVG adjustments while preserving the QA rules above. After manual edits, rerun `scripts/validate_semantic_svg.py` because hand-edited icons, connectors, and layer heights are common failure points.

## Example policy

Examples are regression/style references only. Do not hard-code their domain, layers, node names, or source-boundary assumptions into future diagrams.
