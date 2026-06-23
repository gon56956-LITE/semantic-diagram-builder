# Visual QA

Run this checklist before delivering a semantic diagram.

## Geometry

- Card heights, horizontal gaps, row gaps, layer heights, layer y-positions, and inter-layer gaps are consistent with `layout_metrics.md` unless the exception is intentional and visible.
- Layer y-positions are derived sequentially from previous layer height plus layer gap; repeated layers should not have independently hand-tuned gaps.
- Repeated layer bottom padding is visually consistent. If one layer's bottom padding looks wider/narrower, recalculate from the actual card bounds.
- No card overlaps another card.
- No group label overlaps a card.
- No annotation overlaps a connector, arrowhead, or junction.
- No connector runs through a card.
- Arrowheads land on the target side with enough visual clearance and point in the direction of entry. If an arrow enters a pill/card from the left, the arrowhead points right, not down.
- Rounded elbow corners bend in the direction of travel; there are no curled, backward, hook-like, or hard 90-degree elbows in manually authored SVG connectors.
- Multi-edge convergence uses a bus or simple elbow structure, not tangled diagonals. Branches should enter target anchors directly without extra local bends or zigzags.
- In layered diagrams, horizontal fan-out/fan-in buses sit inside the layer they organize, not in inter-layer label gaps.
- Fan-out bus sits inside the target layer with visible clearance above the target card row; arrowheads do not touch or crowd the bus.
- Fan-in bus sits inside the source layer with visible clearance below the source card row; only a single trunk crosses into the next layer after merge.
- Parallel sibling nodes split and merge within their own layer; only a single trunk crosses into the next layer after merge.
- Layer titles, boundary captions, and explanatory notes do not share space with connector buses.

## Text

- Long labels wrap; they do not overflow the card.
- Card icons/badges do not collide with card titles; widen the card or move the icon if needed.
- Card title and subtitle do not collide; increase card height before reducing font size.
- Layer containers fully contain their cards and captions; calculate height from actual card bounds plus target bottom padding, not from a guessed fixed container height.
- Compare bottom padding across repeated layers; visible mismatch means the layer height or card row height needs recalculation.
- Repeated layer structures use the same offset between class/backbone pills and first-row content cards.
- Footer/caption text is outside active connector corridors.
- The diagram title is visible at the chosen canvas width.

## Semantics

- Node `kind` values are semantic, not cosmetic.
- Distinct semantic kinds use distinct icons or accents.
- Dashed edges mean a weaker/secondary/navigational relation, not a missing process step. If dashed lines are not self-evident, replace them with containment, a legend, or an explicit annotation.
- Boundary/source notes do not imply replacement of controlled source documents.

## SVG integrity

- No invalid color attributes such as `fill="moc"` or `stroke="query"`.
- Icon paths stay within the card/icon area; no badge line extends into the diagram as if it were a connector.
- No external JS, external CSS, or remote assets.
- SVG embeds cleanly in Obsidian using `![[...svg]]`.
- Run `py scripts/validate_semantic_svg.py output.svg` where possible.
- Run `git diff --check` if the target workspace is a git repository.

## Connector path audit

When a visual issue remains after moving cards, inspect the actual SVG path data rather than guessing from the screenshot.

Checks:
- Root-to-backbone or hub-to-backbone connectors should be one clean orthogonal route. Watch for small coordinate mismatches such as a hidden `L360,133 L360,130` step that creates a notch.
- Backbone endings should align with the last branch anchor. If a vertical backbone extends below the final branch, shorten the backbone rather than masking the tail.
- A shared bus should not carry a terminal arrowhead unless the bus itself is the semantic target. Put arrowheads on the short terminal branch into the card or pill.
- For multi-row sibling sets, verify fan-out and fan-in paths separately: each row should have its own bus channel, and no route should pass through or touch a sibling card.
- Do not fake a rounded elbow by composing two separate straight paths that visually meet at a hard 90-degree corner. If a user-perceived route changes direction, encode that route segment with a `Q` rounded elbow in the actual path data.
- Audit multi-path T-junctions and merge-junctions visually, not only individual path data. A vertical stem meeting a horizontal bus is still a hard visual corner unless the branch route curves into the bus with a `Q` elbow.
- Colored connector legends must sit in empty layer space or a side/footer area, never on top of a bus or arrow corridor.
