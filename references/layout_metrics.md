# Layout Metrics

These metrics keep semantic diagrams visually consistent. Use them as defaults unless a specific diagram needs a justified exception.

## Card metrics

- Standard content card height: `100 px`.
- Minimum content card height: `96 px`; only use smaller cards when there is no subtitle and no multi-line title.
- Minimum content card width: `260 px`; use wider cards for labels longer than about 18 characters or when icons collide with titles.
- Maximum default card width: `360 px` before considering a split diagram.
- Icon/badge gutter inside a card: reserve roughly `44 px` from the left edge; title text must not enter this area.
- Title/subtitle rhythm: one-line title near the upper middle; two-line title uses `20 px` line spacing; subtitle should sit at least `16 px` below the last title line and at least `18 px` above the card bottom.

## Card spacing

- Horizontal gap between sibling cards: `56 px` default; never below `40 px` unless cards have no connectors and short labels.
- Vertical gap between card rows in the same layer: `34 px` default; never below `24 px`.
- If a layer has a class/backbone pill, reserve a left gutter so the first content card starts after the pill plus at least `48 px`.
- If a vertical backbone feeds class/backbone pills, keep the backbone at least `40 px` left of the pill anchor. Keep branches straight and orthogonal into the target anchor; do not add extra bends, hooks, or zigzags at the target.
- In a repeated layered diagram, use the same vertical offset between the layer pill and the first content row in every layer.

## Bus and connector clearance

- Fan-out bus placement: put the horizontal bus inside the target layer, above the target sibling cards.
- Fan-in bus placement: put the horizontal merge bus inside the source layer, below the source sibling cards.
- Minimum bus-to-card clearance: keep at least `24 px` between a horizontal bus and the nearest card edge before an arrowhead enters or leaves a card. Prefer `32 px` when space allows.
- Row-bus default clearance in generated diagrams: `32 px` from card top/bottom to the row bus.
- Minimum gap between a fan-in lane from one row and a fan-out lane for the next row: `48 px`.
- Cross-layer transition rule: after fan-in, use one trunk to cross the layer gap; before fan-out, enter the target layer first, then split.
- Orthogonal connector turns should use rounded `Q` corners. Avoid hard 90-degree turns in hand-authored SVGs unless the diagram is intentionally grid-like.
- Do not add parallel bus lanes as a default style. Use a single clear bus unless the user explicitly requests multiple lanes and the diagram remains readable.
- Side-trunk gutter default for generated multi-row routing: reserve at least `130 px` inside the layer side gutter. The default fan-out side is right; the default fan-in side is left.

## Layer container metrics

Layer height is derived from the actual rendered content bounds, not guessed and not forced by a fixed card height. The preferred calculation is:

```text
layer_height = max_card_bottom - layer_top + layer_bottom_pad
```

When all cards in a layer use the same standard height, this is equivalent to:

```text
layer_height = layer_top_pad + rows * card_height + (rows - 1) * row_gap + layer_bottom_pad
```

If cards in the same row need different internal title layouts, first decide whether they should share a row height. If they intentionally differ, still calculate the layer from the tallest actual card bottom.

Defaults:

- `layer_top_pad`: `64 px` from layer top to first content-card top.
- `layer_bottom_pad`: `32 px` below the last content row.
- Minimum layer height: `170 px`.
- Layer label and short description occupy the top label area; content cards should not overlap this area.
- If cards are manually moved, recalculate the layer height so no card or caption protrudes outside the layer band.

## Inter-layer spacing and layer positions

Layer `y` positions are derived sequentially, not hand-placed independently:

```text
first_layer_y = chosen_start_y
next_layer_y = previous_layer_y + previous_layer_height + layer_gap
```

- Default gap between layer containers: `32 px`.
- Repeated layer gaps should be equal unless the diagram has an explicit section break.
- Do not use inter-layer gaps as bus corridors when the bus semantically belongs to a layer.
- Layer labels may sit in a safe label gutter, but buses, captions, and arrows must not share that same lane.

## Manual edit rule

When manually editing an SVG, move a whole card group rather than only some child elements. If you move only selected paths/text, badges, titles, and subtitles will drift out of alignment.

## Multi-row sibling set metrics

When a sibling set is split into multiple rows, calculate the layer from the actual row geometry and connector channels.

Defaults:
- Prefer increasing canvas width before reducing card width below the readable minimum.
- Keep at least `40 px` between a fan-out bus and the target row's card top when arrowheads enter downward.
- Keep at least `40 px` between a source row's card bottom and its fan-in merge bus.
- Keep at least `48 px` between separate fan-out and fan-in bus channels when both appear between two card rows.
- Add side-gutter width when a lower-row fan-out route must bypass upper-row cards; do not route through card columns.
- Layer height must include all card rows, row gaps, bus channels, connector clearances, and bottom padding.
- If both fan-out and fan-in lanes are present between two rows, calculate row gap as at least `bus_to_card_clearance + bus_lane_gap + bus_to_card_clearance`.
- Use explicit `row` and `col` contract fields for multi-row examples that must remain stable across future edits.
