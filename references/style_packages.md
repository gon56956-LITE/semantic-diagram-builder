# Style Packages

Semantic diagram styles are declarative JSON packages. They control visual language without executing code and without changing routing semantics.

## Loading

- Built-in style id: `style: "modern-tech"`, `style: "accent-blueprint"`, or `style: "brief-grid"`.
- Local style path: `style: "./my-style/style.json"` relative to the contract file.
- Missing or invalid styles are hard errors.

## Package Shape

Required fields:

- `id`: stable style id.
- `version`: style package version.
- `metrics`: numeric layout metric overrides. Keep these equal across styles when geometry must remain identical.
- `tokens.colors`: color tokens as `#RRGGBB`, `rgba(r,g,b,a)`, or `none`.
- `components`: declarative renderer component settings for canvas, group, card, icon, connector, table, tree_node, hub, spoke, and metadata_panel.
- `qa`: optional reference image and reference contracts.

Style packages may define:

- canvas background and grid.
- typography stacks and type sizes.
- group panel fill/stroke.
- card fill, radius, border mode, and shadow behavior.
- icon fill mode and stroke widths.
- connector primary/fanout/fanin colors, stroke width, dash style, and marker colors.
- connector palettes for repeated fan-in/fan-out families, dashed relation overlays, and relation-specific colors.
- table fill, header fill, grid opacity, and table typography.
- tree, hub, spoke, and metadata panel visual defaults.
- semantic accent mapping by node `kind`.

Style packages may not:

- execute Python or JavaScript.
- fetch remote assets.
- replace fan-out/fan-in routing logic.
- change the selected `diagram_type` or layout strategy.
- hide invalid SVG colors behind raw snippets.

## Accent Blueprint

`accent-blueprint` is the first user-defined style package. It follows the supplied reference image and uses:

- deep navy/cobalt background.
- subtle CAD-like grid.
- white or near-white typography and linework.
- sparse semantic accents: cyan, yellow, green, purple, orange.
- thin rectangular panels, compact technical typography, and clean arrowheads.

Accent colors are semantic emphasis, not the whole theme. The diagram should remain blue-and-white first.

Connector color policy:

- Primary structural links stay white or near-white.
- Repeated fan-in/fan-out families may use the connector family palette so shared corridors remain distinguishable.
- Sparse dashed overlays use relation-specific colors first, then source-object accent or the relation palette when the relation repeats.
- Explicit edge or relationship `accent` values still win when a contract needs a known semantic color.

## Brief Grid

`brief-grid` is a warm grid-paper briefing style. It follows the supplied executive/intelligence brief references and uses:

- off-white paper background with engineering grid lines.
- black/navy monospace report typography.
- square cards, tables, and panels with thin technical borders and no shadows.
- red/orange alert accents plus muted navy, blue, green, purple, and ochre semantic colors.
- context-stroke arrow markers so connector arrows inherit lane color.

## QA

Use geometry validation for routing and style gallery review for visual quality:

```bash
py scripts/validate_semantic_svg.py output.svg
py scripts/build_style_gallery.py examples/style-gallery.html examples/accent-blueprint-boundary-contract.json
py scripts/test_style_gallery_quality.py
```

For screenshot review, compare the generated gallery/SVG against the style reference image listed in the style package `qa.reference_image`.

`examples/style-gallery-baseline.json` is the shared QA manifest for the bundled examples. It keeps the checked contract list, expected diagram types/styles, and style-specific quality gates in one place so gallery regressions are caught before visual review.
