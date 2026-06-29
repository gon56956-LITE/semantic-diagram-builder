#!/usr/bin/env python3
"""Regression checks for render_semantic_diagram.py."""
from __future__ import annotations

import copy
import importlib.util
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


renderer = load_module("render_semantic_diagram", ROOT / "scripts" / "render_semantic_diagram.py")
validator = load_module("validate_semantic_svg", ROOT / "scripts" / "validate_semantic_svg.py")


def load_contract(name: str) -> dict:
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8-sig"))


def load_json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))


def assert_valid(name: str, contract: dict) -> str:
    svg = renderer.render(contract)
    issues = validator.check_svg(svg)
    if issues:
        raise AssertionError(f"{name} should validate, got: {issues}")
    return svg


def path_ds(svg: str, required_classes: set[str]) -> list[str]:
    matches = []
    for attrs in re.findall(r'<path\b([^>]*)/?>', svg):
        class_match = re.search(r'class="([^"]+)"', attrs)
        d_match = re.search(r'\bd="([^"]+)"', attrs)
        if not class_match or not d_match:
            continue
        classes = set(class_match.group(1).split())
        if required_classes <= classes:
            matches.append(d_match.group(1))
    return matches


def path_attrs(svg: str, required_classes: set[str]) -> list[str]:
    matches = []
    for attrs in re.findall(r'<path\b([^>]*)/?>', svg):
        class_match = re.search(r'class="([^"]+)"', attrs)
        if not class_match:
            continue
        classes = set(class_match.group(1).split())
        if required_classes <= classes:
            matches.append(attrs)
    return matches


def assert_rounded_paths(svg: str, required_classes: set[str], label: str) -> None:
    paths = path_ds(svg, required_classes)
    if not paths:
        raise AssertionError(f"{label} path was not rendered")
    for d in paths:
        if ' Q ' not in d:
            raise AssertionError(f"{label} should use a rounded Q elbow, got: {d}")


def text_font_sizes(svg: str, class_name: str) -> list[float]:
    sizes = []
    for attrs in re.findall(r'<text\b([^>]*)>', svg):
        class_match = re.search(r'class="([^"]+)"', attrs)
        style_match = re.search(r'font-size:([0-9.]+)px', attrs)
        if not class_match or not style_match:
            continue
        if class_name in class_match.group(1).split():
            sizes.append(float(style_match.group(1)))
    return sizes


def css_font_size(svg: str, class_name: str) -> float:
    match = re.search(rf'\.{re.escape(class_name)}\{{font:[^}}]*?([0-9.]+)px', svg)
    if not match:
        raise AssertionError(f"missing CSS font size for {class_name}")
    return float(match.group(1))


def node_rects(svg: str) -> dict[str, tuple[float, float, float, float]]:
    rects = {}
    pattern = re.compile(
        r'<g id="node-([^"]+)"[^>]*><rect x="([0-9.]+)" y="([0-9.]+)" width="([0-9.]+)" height="([0-9.]+)"'
    )
    for node_id, x, y, w, h in pattern.findall(svg):
        rects[node_id] = (float(x), float(y), float(w), float(h))
    return rects


def info_panel_rects(svg: str) -> dict[str, tuple[float, float, float, float]]:
    rects = {}
    pattern = re.compile(
        r'<g class="[^"]*\binfo-panel\b[^"]*" data-panel-id="([^"]+)"[^>]*>\s*'
        r'<rect x="([-0-9.]+)" y="([-0-9.]+)" width="([-0-9.]+)" height="([-0-9.]+)"',
        re.S,
    )
    for panel_id, x, y, w, h in pattern.findall(svg):
        rects[panel_id] = (float(x), float(y), float(w), float(h))
    return rects


def group_rect(svg: str, group_id: str) -> tuple[float, float, float, float]:
    match = re.search(
        rf'<g id="{re.escape(group_id)}"[^>]*>\s*'
        r'<rect x="([-0-9.]+)" y="([-0-9.]+)" width="([-0-9.]+)" height="([-0-9.]+)"',
        svg,
        re.S,
    )
    if not match:
        raise AssertionError(f"expected measurable group rect for {group_id}")
    return tuple(float(value) for value in match.groups())


def relationship_diamond_center(svg: str, relationship_id: str) -> tuple[float, float]:
    match = re.search(
        rf'<g id="relationship-{re.escape(relationship_id)}"[^>]*>\s*'
        r'<path d="M ([-0-9.]+) [-0-9.]+ L [-0-9.]+ ([-0-9.]+)',
        svg,
        re.S,
    )
    if not match:
        raise AssertionError(f"expected measurable relationship diamond for {relationship_id}")
    return float(match.group(1)), float(match.group(2))


def ontology_instance_link_end(svg: str, instance_id: str) -> tuple[float, float]:
    match = re.search(rf'<path d="([^"]+)"[^>]*\bdata-to="{re.escape(instance_id)}"', svg)
    if not match:
        raise AssertionError(f"expected ontology instance link to {instance_id}")
    values = [float(value) for value in re.findall(r'[-0-9.]+', match.group(1))]
    return values[-2], values[-1]


def assert_bottom_panels_pack_like_masonry(svg: str, lower_panel_id: str) -> None:
    rects = info_panel_rects(svg)
    if lower_panel_id not in rects:
        raise AssertionError(f"expected packed bottom panel {lower_panel_id}")
    top_y = min(y for _x, y, _w, _h in rects.values())
    top_row = [rect for rect in rects.values() if abs(rect[1] - top_y) < 1]
    tallest_top_bottom = max(y + h for _x, y, _w, h in top_row)
    lower_y = rects[lower_panel_id][1]
    if lower_y >= tallest_top_bottom:
        raise AssertionError("bottom info panels should pack into the shortest column instead of opening a full new row")


def assert_three_bottom_panels_use_side_stack(svg: str) -> None:
    rects = info_panel_rects(svg)
    for panel_id in ("legend", "qa", "metadata"):
        if panel_id not in rects:
            raise AssertionError(f"expected compact bottom panel {panel_id}")
    legend_x, legend_y, legend_w, legend_h = rects["legend"]
    qa_x, qa_y, qa_w, qa_h = rects["qa"]
    metadata_x, metadata_y, metadata_w, metadata_h = rects["metadata"]
    if not legend_x < qa_x:
        raise AssertionError("three bottom panels should place the first panel on the left")
    if abs(qa_x - metadata_x) > 1 or abs(qa_w - metadata_w) > 1:
        raise AssertionError("three bottom panels should stack the second and third panels in the right column")
    if not metadata_y > qa_y + qa_h:
        raise AssertionError("three bottom panels should put the third panel below the second")
    right_stack_h = metadata_y + metadata_h - qa_y
    if abs(legend_y - qa_y) > 1 or legend_h + 1 < right_stack_h:
        raise AssertionError("left bottom panel should span the right-side stack height")


def assert_ontology_stress_layout(svg: str) -> None:
    first_row = group_rect(svg, "instance-customer_acme")
    beta = group_rect(svg, "instance-customer_beta")
    sku_b44 = group_rect(svg, "instance-sku_b44")
    if beta[1] - (first_row[1] + first_row[3]) < 56:
        raise AssertionError("ontology_map stress second instance row should leave readable routing space")
    for instance_id, rect in (("customer_beta", beta), ("sku_b44", sku_b44)):
        end_x, end_y = ontology_instance_link_end(svg, instance_id)
        center_top = (rect[0] + rect[2] / 2, rect[1])
        if abs(end_x - center_top[0]) > 1 or abs(end_y - center_top[1]) > 1:
            raise AssertionError("ontology_map stress instance links should land on centered top anchors")
    governed = relationship_diamond_center(svg, "governed_by")
    reviewed = relationship_diamond_center(svg, "reviewed_by")
    if governed[0] > reviewed[0] - 80 or governed[1] < reviewed[1] + 120:
        raise AssertionError("ontology_map governed_by diamond should sit lower and left of the reviewed_by diamond")
    supplied = relationship_diamond_center(svg, "supplied_by")
    constrained = relationship_diamond_center(svg, "constrained_by")
    proved = relationship_diamond_center(svg, "proved_by")
    if not (supplied[0] < constrained[0] < proved[0]) or max(y for _x, y in (supplied, constrained, proved)) - min(y for _x, y in (supplied, constrained, proved)) > 12:
        raise AssertionError("ontology_map stress middle-row diamonds should align with their source/target lanes")
    governed_paths = re.findall(r'<path\b[^>]*\bdata-relationship="governed_by"[^>]*/>', svg)
    if len(governed_paths) < 2 or any(path.count(" Q ") > 1 for path in governed_paths[:2]):
        raise AssertionError("ontology_map governed_by links should use simple elbows instead of extra detours")


def first_q_lanes_from(svg: str, source_bottoms: set[float]) -> set[float]:
    lanes = set()
    start_pattern = re.compile(r'^M ([-0-9.]+) ([-0-9.]+)\b')
    q_pattern = re.compile(r'\bQ [-0-9.]+ ([-0-9.]+) [-0-9.]+ [-0-9.]+')
    for d in path_ds(svg, {"taxonomy-link"}):
        start = start_pattern.search(d)
        q = q_pattern.search(d)
        if not start or not q:
            continue
        if round(float(start.group(2)), 1) in source_bottoms:
            lanes.add(round(float(q.group(1)), 1))
    return lanes


def assert_card_type_scale(label: str, svg: str) -> None:
    title_sizes = text_font_sizes(svg, "card-title")
    sub_sizes = text_font_sizes(svg, "card-sub")
    if not title_sizes or min(title_sizes) < 20.5:
        raise AssertionError(f"{label} card titles should use canvas-aware readable font sizes")
    if max(title_sizes) - min(title_sizes) > 0.2:
        raise AssertionError(f"{label} card titles should use one diagram-level font scale")
    if max(title_sizes) > 23.5:
        raise AssertionError(f"{label} card titles should not grow with individual card width")
    if not sub_sizes or min(sub_sizes) < 15.5:
        raise AssertionError(f"{label} card subtitles should use canvas-aware readable font sizes")
    if max(sub_sizes) - min(sub_sizes) > 0.2:
        raise AssertionError(f"{label} card subtitles should use one diagram-level font scale")
    if max(sub_sizes) > 17.5:
        raise AssertionError(f"{label} card subtitles should not grow with individual card width")


def assert_table_scale(svg: str) -> None:
    header_sizes = text_font_sizes(svg, "table-header")
    cell_sizes = text_font_sizes(svg, "table-cell") + text_font_sizes(svg, "table-cell-secondary")
    if not header_sizes or min(header_sizes) < 15:
        raise AssertionError("registry_table headers should be readable at gallery scale")
    if not cell_sizes or min(cell_sizes) < 16:
        raise AssertionError("registry_table cells should be readable at gallery scale")
    for kind in ("capability", "source", "risk", "package"):
        if f'data-kind="{kind}"' not in svg:
            raise AssertionError(f"registry_table should render semantic badges for {kind}")


def assert_hub_spoke_design(svg: str) -> None:
    if 'class="hub-core card"' not in svg:
        raise AssertionError("hub_spoke should render a designed central hub core")
    if svg.count('class="hub-spoke-node spoke-block card"') < 4:
        raise AssertionError("hub_spoke should render designed spoke blocks instead of generic cards")
    if 'class="edge hub-spoke-link"' not in svg and 'hub-spoke-link' not in svg:
        raise AssertionError("hub_spoke should render explicit hub-spoke connector links")
    title_sizes = text_font_sizes(svg, "card-title")
    sub_sizes = text_font_sizes(svg, "card-sub")
    if not title_sizes or min(title_sizes) < 18:
        raise AssertionError("hub_spoke labels should remain readable")
    if not sub_sizes or min(sub_sizes) < 13.5:
        raise AssertionError("hub_spoke subtitles should remain readable")


def assert_boundary_matrix_design(svg: str) -> None:
    if 'class="boundary-matrix-item"' not in svg:
        raise AssertionError("boundary_ownership_map domain_ownership_matrix should render compact matrix items")
    if 'class="edge boundary-matrix-link"' not in svg:
        raise AssertionError("boundary_ownership_map domain_ownership_matrix should render relationship links")
    if "OWNERSHIP KEY (RACI)" not in svg or "OWNERSHIP ASSIGNMENTS" not in svg:
        raise AssertionError("boundary_ownership_map domain_ownership_matrix should render RACI key and assignment table")
    if 'class="card node-card"' in svg:
        raise AssertionError("boundary_ownership_map domain_ownership_matrix should not fall back to generic node cards")
    item_heights = [
        float(value)
        for value in re.findall(
            r'<g id="matrix-item-[^"]+" class="boundary-matrix-item"[^>]*>\s*<rect [^>]*height="([0-9.]+)"',
            svg,
        )
    ]
    if not item_heights or min(item_heights) < 76:
        raise AssertionError("boundary matrix item cards should be tall enough for dense title/subtitle content")
    external_link_attrs = [
        attrs
        for attrs in path_attrs(svg, {"boundary-matrix-link"})
        if re.search(r'data-to="(payment_gateway|logistics_provider|cloud_provider|regulatory_authority|regulator|identity_provider)"', attrs)
    ]
    if not external_link_attrs or any('data-corridor-x=' not in attrs for attrs in external_link_attrs):
        raise AssertionError("boundary matrix external links should route through domain-gap corridors")
    title_sizes = text_font_sizes(svg, "matrix-title")
    sub_sizes = text_font_sizes(svg, "matrix-sub")
    if not title_sizes or min(title_sizes) < 18:
        raise AssertionError("boundary matrix item titles should remain readable")
    if not sub_sizes or min(sub_sizes) < 13.5:
        raise AssertionError("boundary matrix item subtitles should remain readable")


def assert_object_relationship_design(svg: str) -> None:
    if 'data-diagram-type="object_relationship_diagram"' not in svg:
        raise AssertionError("object_relationship_diagram should declare its diagram type")
    if svg.count('class="object-entity-card card"') < 6:
        raise AssertionError("object_relationship_diagram should render entity table cards")
    if svg.count('class="relationship-diamond"') < 5:
        raise AssertionError("object_relationship_diagram should render relationship diamonds")
    if 'class="edge object-relationship-link"' not in svg:
        raise AssertionError("object_relationship_diagram should render relationship links")
    if "PK" not in svg or "FK" not in svg:
        raise AssertionError("object_relationship_diagram should render PK/FK badges")
    if 'class="note cardinality-label"' not in svg or "1..*" not in svg:
        raise AssertionError("object_relationship_diagram should render cardinality labels")
    if 'class="cardinality-label-wrap"' not in svg:
        raise AssertionError("object_relationship_diagram cardinality labels should use layout wrappers")
    if 'stroke-dasharray="7 5"' not in svg:
        raise AssertionError("object_relationship_diagram should support weak entity dashed cards")
    if 'data-slot-row=' not in svg or 'data-slot-col=' not in svg:
        raise AssertionError("object_relationship_diagram should expose relationship grid slots")
    title_sizes = text_font_sizes(svg, "card-title")
    table_sizes = text_font_sizes(svg, "entity-attr")
    if not title_sizes or min(title_sizes) < 18:
        raise AssertionError("object_relationship_diagram entity titles should remain readable")
    if not table_sizes or min(table_sizes) < 13:
        raise AssertionError("object_relationship_diagram attribute rows should remain readable")


def assert_ontology_map_design(svg: str) -> None:
    if 'data-diagram-type="ontology_map"' not in svg:
        raise AssertionError("ontology_map should declare its diagram type")
    if svg.count('class="ontology-concept-card card"') < 4:
        raise AssertionError("ontology_map should render ontology concept cards")
    if svg.count('class="relationship-diamond"') < 4:
        raise AssertionError("ontology_map should render relationship diamonds")
    if 'class="edge object-relationship-link ontology-relationship-link"' not in svg:
        raise AssertionError("ontology_map should reuse relationship-map connector geometry")
    if 'class="ontology-instance-card card"' not in svg:
        raise AssertionError("ontology_map should render instance cards")
    if 'class="edge ontology-instance-link"' not in svg:
        raise AssertionError("ontology_map should render instance-to-concept links")
    instance_paths = path_ds(svg, {"ontology-instance-link"})
    if any(path.startswith(("M 537.5 302.0", "M 962.5 302.0")) for path in instance_paths):
        raise AssertionError("ontology_map instance links should use offset anchors, not relationship center anchors")
    if 'ontology-side-panel' in svg:
        raise AssertionError("ontology_map should render info panels below the concept canvas, not as side panels")
    if svg.count('class="info-panel"') < 3:
        raise AssertionError("ontology_map should render legend/about/rules panels below the map")
    assert_bottom_panels_pack_like_masonry(svg, "version")
    if "PK" not in svg or "1..*" not in svg:
        raise AssertionError("ontology_map should render datatype rows and cardinality labels")
    if 'entity-key-badge' in svg:
        raise AssertionError("ontology_map should not render ER-style PK/FK badges")
    concept_titles = text_font_sizes(svg, "ontology-concept-title")
    attrs = text_font_sizes(svg, "ontology-attr")
    if not concept_titles or min(concept_titles) < 18:
        raise AssertionError("ontology_map concept titles should remain readable")
    if not attrs or min(attrs) < 13:
        raise AssertionError("ontology_map attribute rows should remain readable")
    for relationship in ("works_for", "assigned_to"):
        links = re.findall(rf'<path\b[^>]*\bdata-relationship="{relationship}"[^>]*/>', svg)
        if len(links) < 2:
            raise AssertionError(f"ontology_map should render both endpoints for {relationship}")
        if any('data-route="axis"' not in link for link in links[:2]):
            raise AssertionError(f"ontology_map horizontal relationship {relationship} should stay on a direct axis")


def assert_capability_map_design(svg: str) -> None:
    if 'data-diagram-type="capability_domain_map"' not in svg:
        raise AssertionError("capability_domain_map should declare its diagram type")
    if 'class="capability-map-item card"' not in svg:
        raise AssertionError("capability_domain_map should render dedicated capability map items")
    if 'capability-level-label' not in svg or 'capability-column-label' not in svg:
        raise AssertionError("capability_domain_map should render level and column labels")
    if svg.count('capability-level-icon') < 5 or svg.count('capability-column-icon') < 4:
        raise AssertionError("capability_domain_map should render prominent row and column header icons")
    if 'class="edge capability-map-link"' not in svg:
        raise AssertionError("capability_domain_map should render capability relationship links")
    if 'class="card node-card"' in svg:
        raise AssertionError("capability_domain_map should not fall back to generic node cards")
    if 'class="capability-badge semantic-badge"' in svg:
        raise AssertionError("capability_domain_map should keep semantic badges out of dense item cards")
    title_sizes = text_font_sizes(svg, "capability-title")
    sub_sizes = text_font_sizes(svg, "capability-sub")
    if not title_sizes or min(title_sizes) < 16:
        raise AssertionError("capability_domain_map item titles should remain readable")
    if sub_sizes and min(sub_sizes) < 13:
        raise AssertionError("capability_domain_map item subtitles should remain readable")
    item_heights = [float(value) for value in re.findall(r'class="capability-map-item card"[^>]*>.*?<rect [^>]*height="([0-9.]+)"', svg, re.S)]
    if not item_heights or min(item_heights) < 94:
        raise AssertionError("capability_domain_map item cards should be tall enough for dense title/subtitle content")
    level_label_rect = re.search(r'<rect x="[^"]+" y="[^"]+" width="([0-9.]+)" height="[^"]+" rx="5"[^>]*stroke="#16D9FF"', svg)
    if not level_label_rect or float(level_label_rect.group(1)) < 175:
        raise AssertionError("capability_domain_map level label lane should be content-driven wide enough for long row labels")


def assert_relationship_matrix_design(svg: str, expected_total: int) -> None:
    if 'data-diagram-type="relationship_matrix"' not in svg:
        raise AssertionError("relationship_matrix should declare its diagram type")
    for class_name in (
        "relationship-matrix-grid",
        "matrix-primary-preview",
        "matrix-summary-panel",
        "matrix-focus-detail-panel",
        "matrix-top-connected-panel",
    ):
        if class_name not in svg:
            raise AssertionError(f"relationship_matrix should render {class_name}")
    for removed_text in ("When To Use", "How To Read", "Metadata", "Companion Views Guide"):
        if removed_text in svg:
            raise AssertionError(f"relationship_matrix should not render explanatory dashboard panel: {removed_text}")
    full_preview_note = "Too many edges here. Read the matrix for type, strength, and coverage."
    if f">{full_preview_note}</text>" in svg:
        raise AssertionError("relationship_matrix preview footer should wrap instead of overflowing its container")
    if 'class="matrix-cell"' not in svg or 'class="matrix-cell-value"' not in svg:
        raise AssertionError("relationship_matrix should render matrix cells and values")
    if 'class="matrix-row-label"' not in svg or 'class="matrix-col-label"' not in svg:
        raise AssertionError("relationship_matrix should render row and column labels")
    cell_count = svg.count('class="matrix-cell"')
    entity_count = int(cell_count ** 0.5)
    if entity_count * entity_count != cell_count:
        raise AssertionError("relationship_matrix should render a square entity matrix")
    if svg.count('class="matrix-row-label"') != entity_count:
        raise AssertionError("relationship_matrix row labels should stay on one line")
    if svg.count('class="matrix-col-label"') != entity_count:
        raise AssertionError("relationship_matrix column labels should stay on one line")
    if 'matrix-selected-cell' in svg:
        raise AssertionError("relationship_matrix is static and should not render an interactive-looking selected cell")
    if svg.count('class="matrix-distribution-bar"') < 3:
        raise AssertionError("relationship_matrix should render compact distribution bars")
    if not re.search(rf'class="matrix-summary-value"[^>]*>{expected_total}</text>', svg):
        raise AssertionError("relationship_matrix summary should match the contract relationship count")
    row_label_sizes = text_font_sizes(svg, "matrix-row-label")
    col_label_sizes = text_font_sizes(svg, "matrix-col-label")
    cell_sizes = text_font_sizes(svg, "matrix-cell-value")
    panel_item_sizes = text_font_sizes(svg, "info-panel-item")
    preview_title_sizes = text_font_sizes(svg, "matrix-preview-title")
    preview_sub_sizes = text_font_sizes(svg, "matrix-preview-sub")
    rank_label_sizes = text_font_sizes(svg, "matrix-rank-label")
    preview_rects = [
        tuple(map(float, values))
        for values in re.findall(
            r'<g class="matrix-preview-node"[^>]*>\s*<rect x="([-0-9.]+)" y="([-0-9.]+)" width="([-0-9.]+)" height="([-0-9.]+)"',
            svg,
        )
    ]
    if len(preview_rects) != entity_count:
        raise AssertionError("relationship_matrix preview should render one non-overlapping card per entity")
    if entity_count >= 8 and min((w for _x, _y, w, _h in preview_rects), default=0) < 170:
        raise AssertionError("relationship_matrix preview cards should be wide enough for title and subtitle text")
    for idx, (x, y, w, h) in enumerate(preview_rects):
        for ox, oy, ow, oh in preview_rects[idx + 1:]:
            overlap_x = min(x + w, ox + ow) - max(x, ox)
            overlap_y = min(y + h, oy + oh) - max(y, oy)
            if overlap_x > 1 and overlap_y > 1:
                raise AssertionError("relationship_matrix preview cards should not overlap")
    footer_lines = [
        (float(y), float(size), text)
        for y, size, text in re.findall(r'<text x="[^"]+" y="([-0-9.]+)" class="note" style="font-size:([0-9.]+)px[^"]*">(Too many edges here[^<]*|[^<]*coverage\\.)</text>', svg)
    ]
    if footer_lines:
        preview_bottom = max(y + h for _x, y, _w, h in preview_rects)
        footer_top = min(y - size * 1.15 for y, size, _text in footer_lines)
        if footer_top - preview_bottom < 28:
            raise AssertionError("relationship_matrix preview footer should keep clear space below the last card row")
    if not row_label_sizes or min(row_label_sizes) < 18:
        raise AssertionError("relationship_matrix row labels should remain readable")
    if not col_label_sizes or min(col_label_sizes) < 18:
        raise AssertionError("relationship_matrix column labels should remain readable")
    if not cell_sizes or min(cell_sizes) < 28:
        raise AssertionError("relationship_matrix cell values should remain readable")
    if not panel_item_sizes or min(panel_item_sizes) < 16:
        raise AssertionError("relationship_matrix panel body text should remain readable")
    if not preview_title_sizes or min(preview_title_sizes) < 16:
        raise AssertionError("relationship_matrix preview titles should remain readable")
    if not preview_sub_sizes or min(preview_sub_sizes) < 15:
        raise AssertionError("relationship_matrix preview subtitles should remain readable")
    if not rank_label_sizes or min(rank_label_sizes) < 16:
        raise AssertionError("relationship_matrix ranking labels should remain readable")
    grid = re.search(r'<g class="relationship-matrix-grid">(.*?)</g>', svg, re.S)
    if not grid:
        raise AssertionError("relationship_matrix grid group should be present")
    panel = re.search(r'<rect x="([0-9.]+)" y="[^"]+" width="([0-9.]+)" height="[^"]+"', grid.group(1))
    matrix = re.search(
        r'<rect x="([0-9.]+)" y="[^"]+" width="([0-9.]+)" height="[^"]+" rx="6" fill="none" stroke="[^"]+" stroke-opacity="0.58"',
        grid.group(1),
    )
    if not panel or not matrix:
        raise AssertionError("relationship_matrix should render a measurable center panel and matrix")
    panel_x, panel_w = float(panel.group(1)), float(panel.group(2))
    matrix_x, matrix_w = float(matrix.group(1)), float(matrix.group(2))
    if matrix_w < panel_w * 0.95 or matrix_x - panel_x > 24:
        raise AssertionError("relationship_matrix table should fill the central container width")
    panel_rect = re.search(r'<rect x="([0-9.]+)" y="([0-9.]+)" width="([0-9.]+)" height="([0-9.]+)"', grid.group(1))
    detail_rect = re.search(
        r'class="info-panel relationship-matrix-panel matrix-focus-detail-panel"[^>]*>.*?'
        r'<rect x="([0-9.]+)" y="([0-9.]+)" width="([0-9.]+)" height="([0-9.]+)"',
        svg,
        re.S,
    )
    if not panel_rect or not detail_rect:
        raise AssertionError("relationship_matrix should expose measurable main and detail panels")
    main_y, main_h = float(panel_rect.group(2)), float(panel_rect.group(4))
    detail_y = float(detail_rect.group(2))
    if detail_y < main_y + main_h:
        raise AssertionError("relationship_matrix support panels should sit below the main diagram and matrix")


def assert_no_direct_diagonal_object_links(svg: str) -> None:
    direct_line = re.compile(r'^M ([-0-9.]+) ([-0-9.]+) L ([-0-9.]+) ([-0-9.]+)$')
    for d in path_ds(svg, {"object-relationship-link"}):
        match = direct_line.match(d)
        if not match:
            continue
        x1, y1, x2, y2 = map(float, match.groups())
        if abs(x1 - x2) >= 0.1 and abs(y1 - y2) >= 0.1:
            raise AssertionError(f"object_relationship_diagram should not use direct diagonal links, got: {d}")


def q_turns(svg: str, required_classes: set[str]) -> list[tuple[float, float, float]]:
    turns = []
    pattern = re.compile(
        r'M ([-0-9.]+) ([-0-9.]+) L ([-0-9.]+) ([-0-9.]+) '
        r'Q ([-0-9.]+) ([-0-9.]+) ([-0-9.]+) ([-0-9.]+)'
    )
    for d in path_ds(svg, required_classes):
        m = pattern.search(d)
        if not m:
            raise AssertionError(f"rounded path shape was not recognized: {d}")
        turns.append((float(m.group(1)), float(m.group(5)), float(m.group(7))))
    return turns


def main() -> int:
    layered = load_contract("ocs-r300-layered-contract.json")
    layered_svg = assert_valid("single-row layered example", layered)
    if 'data-diagram-type="layered_knowledge_topology"' not in layered_svg:
        raise AssertionError("layered example should declare the standard diagram type")
    assert_card_type_scale("layered", layered_svg)
    if css_font_size(layered_svg, "group-label") < 15:
        raise AssertionError("layer labels should be readable at gallery scale")
    if css_font_size(layered_svg, "note") < 14:
        raise AssertionError("legend/footer notes should be readable at gallery scale")

    legacy = copy.deepcopy(layered)
    legacy.pop("diagram_type", None)
    legacy["layout"] = "layered"
    legacy_warnings = renderer.contract_warnings(legacy)
    if not any("deprecated" in warning and "layered_knowledge_topology" in warning for warning in legacy_warnings):
        raise AssertionError("legacy layout should be accepted with a deprecation warning")

    conflict = copy.deepcopy(layered)
    conflict["diagram_type"] = "source_boundary_map"
    conflict["layout"] = "layered"
    conflict_warnings = renderer.contract_warnings(conflict)
    if not any("takes precedence" in warning for warning in conflict_warnings):
        raise AssertionError("diagram_type should take precedence over conflicting layout")

    unknown = copy.deepcopy(layered)
    unknown["diagram_type"] = "unknown_type"
    try:
        renderer.render(unknown)
    except renderer.DiagramTypeError:
        pass
    else:
        raise AssertionError("unknown diagram_type should fail explicitly")

    multi = load_contract("ocs-r300-multirrow-contract.json")
    svg = assert_valid("multi-row routed example", multi)
    if 'class="edge fanout route-shared bus"' not in svg:
        raise AssertionError("multi-row fan-out bus was not rendered")
    if 'class="edge fanin route-shared bus"' not in svg:
        raise AssertionError("multi-row fan-in bus was not rendered")
    if 'marker-end="url(#arrow-fanout)"' not in svg or 'marker-end="url(#arrow-fanin)"' not in svg:
        raise AssertionError("terminal fan-out/fan-in arrows were not rendered")
    assert_rounded_paths(svg, {"fanout", "terminal"}, "fan-out terminal")
    assert_rounded_paths(svg, {"fanout", "branch"}, "fan-out source branch")
    assert_rounded_paths(svg, {"fanin", "merge"}, "fan-in terminal merge")
    assert_rounded_paths(svg, {"fanin", "branch"}, "fan-in row bus branch")
    assert_rounded_paths(svg, {"route-shared", "trunk"}, "side trunk")

    fanout_source_turns = q_turns(svg, {"fanout", "branch"})
    if not any(end_x < turn_x for _start_x, turn_x, end_x in fanout_source_turns):
        raise AssertionError("center fan-out source should round into the left bus segment")
    if not any(end_x > turn_x for _start_x, turn_x, end_x in fanout_source_turns):
        raise AssertionError("center fan-out source should round into the right bus segment")

    fanout_turns = q_turns(svg, {"fanout", "terminal"})
    if not any(start_x > turn_x for start_x, turn_x, _end_x in fanout_turns):
        raise AssertionError("left-of-source fan-out terminals should round in from the right")
    if not any(start_x < turn_x for start_x, turn_x, _end_x in fanout_turns):
        raise AssertionError("right-of-source fan-out terminals should round in from the left")

    fanin_branch_turns = q_turns(svg, {"fanin", "branch"})
    if not all(end_x < turn_x for _start_x, turn_x, end_x in fanin_branch_turns):
        raise AssertionError("left-side fan-in branches should round toward the left trunk")
    fanin_merge_turns = q_turns(svg, {"fanin", "merge"})
    if not any(start_x < turn_x for start_x, turn_x, _end_x in fanin_merge_turns):
        raise AssertionError("center fan-in target should merge from the left bus segment")
    if not any(start_x > turn_x for start_x, turn_x, _end_x in fanin_merge_turns):
        raise AssertionError("center fan-in target should merge from the right bus segment")

    model = renderer.build_layout_model(multi)
    positions = model["positions"]
    if positions["faceplate"][1] <= positions["mems"][1]:
        raise AssertionError("explicit row field did not place faceplate on a lower row")
    if positions["mech"][0] <= positions["faceplate"][0]:
        raise AssertionError("explicit col field did not order lower-row nodes")
    if model["group_layouts"]["subkb"]["mode"] != "row_bus_side_trunk":
        raise AssertionError("multi-row routed group did not select row_bus_side_trunk")

    face_x, face_bottom = renderer.center_bottom(positions["faceplate"])
    target_x, target_top = renderer.center_top(positions["controlled_sources"])
    direct_path = renderer._vertical_branch(face_x, face_bottom, target_top)
    if direct_path not in path_ds(svg, {"fanin", "terminal"}):
        raise AssertionError("vertically aligned fan-in source should connect directly to the target")
    direct_source_prefix = f"M {face_x} {face_bottom} "
    if any(d.startswith(direct_source_prefix) for d in path_ds(svg, {"fanin", "branch"})):
        raise AssertionError("vertically aligned fan-in source should not bend into the side bus")

    simple = copy.deepcopy(multi)
    for group in simple["groups"]:
        if group["id"] == "subkb":
            group["routing"]["mode"] = "simple"
    simple_svg = renderer.render(simple)
    if 'class="edge fanout route-shared bus"' in simple_svg or 'class="edge fanin route-shared bus"' in simple_svg:
        raise AssertionError("routing.mode=simple should not emit row-level buses")

    registry = load_contract("registry-table-contract.json")
    registry_svg = assert_valid("registry table example", registry)
    if 'data-diagram-type="registry_table"' not in registry_svg or 'class="table-header"' not in registry_svg:
        raise AssertionError("registry_table should render table headers and declare its diagram type")
    if 'class="card node-card"' in registry_svg:
        raise AssertionError("registry_table should render as a table, not as grouped cards")
    assert_table_scale(registry_svg)
    registry_stress = load_json("templates/registry_table/stress-contract.json")
    registry_stress_svg = assert_valid("registry table stress template", registry_stress)
    registry_width_match = re.search(r'<svg[^>]*width="([0-9.]+)"', registry_stress_svg)
    if not registry_width_match or float(registry_width_match.group(1)) < 2300:
        raise AssertionError("registry_table stress template should allow a wide canvas for dense columns")
    if registry_stress_svg.count('class="info-panel"') < 3:
        raise AssertionError("registry_table stress template should render bottom info panels")
    if registry_stress_svg.count('class="table-badge semantic-badge"') < 8:
        raise AssertionError("registry_table stress template should exercise many semantic badges")

    boundary_minimal = load_json("templates/boundary_ownership_map/minimal-contract.json")
    _dtype, minimal_strategy, _warnings = renderer.diagram_for_contract(boundary_minimal)
    if minimal_strategy != "grouped_layered":
        raise AssertionError("boundary_ownership_map without variant should keep grouped_layered strategy")
    boundary_minimal_svg = assert_valid("boundary ownership minimal template", boundary_minimal)
    if 'class="card node-card"' not in boundary_minimal_svg:
        raise AssertionError("boundary_ownership_map minimal template should still render grouped node cards")

    boundary_matrix = load_json("templates/boundary_ownership_map/reference-contract.json")
    _dtype, matrix_strategy, _warnings = renderer.diagram_for_contract(boundary_matrix)
    if matrix_strategy != "boundary_matrix":
        raise AssertionError("boundary_ownership_map domain_ownership_matrix should select boundary_matrix strategy")
    boundary_matrix_svg = assert_valid("boundary ownership matrix template", boundary_matrix)
    if 'data-variant="domain_ownership_matrix"' not in boundary_matrix_svg:
        raise AssertionError("boundary_ownership_map matrix SVG should expose data-variant")
    assert_boundary_matrix_design(boundary_matrix_svg)

    tree = load_contract("taxonomy-tree-contract.json")
    tree_svg = assert_valid("taxonomy tree example", tree)
    if 'data-diagram-type="taxonomy_tree"' not in tree_svg or 'class="edge taxonomy-link"' not in tree_svg:
        raise AssertionError("taxonomy_tree should render parent-child connectors")
    assert_card_type_scale("taxonomy_tree", tree_svg)
    if css_font_size(tree_svg, "tree-level-label") < 15:
        raise AssertionError("taxonomy level labels should be readable at gallery scale")
    stress_tree = load_json("templates/taxonomy_tree/stress-contract.json")
    stress_tree_svg = assert_valid("taxonomy tree stress template", stress_tree)
    width_match = re.search(r'<svg[^>]*width="([0-9.]+)"', stress_tree_svg)
    if not width_match or float(width_match.group(1)) > 1800:
        raise AssertionError("taxonomy_tree should wrap dense levels instead of forcing an overly wide canvas")
    stress_rects = node_rects(stress_tree_svg)
    leaf_ids = {
        "domain_map",
        "ownership_map",
        "flow_overview",
        "glossary",
        "parameter_register",
        "risk_register",
        "work_module",
        "training_module",
        "playbook",
        "source_doc",
        "quality_record",
        "test_result",
    }
    leaf_rows = {round(stress_rects[node_id][1], 1) for node_id in leaf_ids}
    if len(leaf_rows) < 2:
        raise AssertionError("taxonomy_tree dense leaf level should wrap into multiple visual rows")
    level1_parent_ids = {"maps", "registries", "modules", "evidence"}
    level1_bottoms = {
        round(stress_rects[node_id][1] + stress_rects[node_id][3], 1)
        for node_id in level1_parent_ids
    }
    level1_lanes = first_q_lanes_from(stress_tree_svg, level1_bottoms)
    if len(level1_lanes) < 3:
        raise AssertionError("taxonomy_tree Level 1 parents should use separate local fan-out lanes")
    taxonomy_attrs = path_attrs(stress_tree_svg, {"taxonomy-link"})
    level1_edge_attrs = [
        attrs for attrs in taxonomy_attrs
        if re.search(r'data-parent="(maps|registries|modules|evidence)"', attrs)
    ]
    level1_colors = {
        color.upper()
        for attrs in level1_edge_attrs
        for color in re.findall(r'style="[^"]*stroke:(#[0-9A-Fa-f]{6})', attrs)
    }
    if len(level1_colors) < 4:
        raise AssertionError("taxonomy_tree Level 1 fan-out groups should use distinct connector colors")
    wrapped_corridors = {
        re.search(r'data-parent="([^"]+)"', attrs).group(1): float(re.search(r'data-corridor-x="([-0-9.]+)"', attrs).group(1))
        for attrs in level1_edge_attrs
        if 'data-corridor-x=' in attrs and re.search(r'data-parent="([^"]+)"', attrs)
    }
    if len(wrapped_corridors) < 2:
        raise AssertionError("taxonomy_tree stress case should exercise wrapped parent corridors")
    if len(set(round(value, 1) for value in wrapped_corridors.values())) != len(wrapped_corridors):
        raise AssertionError("taxonomy_tree wrapped fan-out groups should not share the same vertical corridor")
    wrapped_row_lanes = {
        re.search(r'data-parent="([^"]+)"', attrs).group(1): float(re.search(r'data-row-lane-y="([-0-9.]+)"', attrs).group(1))
        for attrs in level1_edge_attrs
        if 'data-row-lane-y=' in attrs and re.search(r'data-parent="([^"]+)"', attrs)
    }
    if len(wrapped_row_lanes) < 2:
        raise AssertionError("taxonomy_tree stress case should exercise wrapped row lanes")
    if len(set(round(value, 1) for value in wrapped_row_lanes.values())) != len(wrapped_row_lanes):
        raise AssertionError("taxonomy_tree wrapped fan-out groups should use staggered row lanes")
    conflict_tree = copy.deepcopy(tree)
    conflict_tree["edges"] = [{"from": "maps", "to": "glossary", "relation": "parent"}]
    try:
        renderer.contract_warnings(conflict_tree)
    except renderer.DiagramTypeError:
        pass
    else:
        raise AssertionError("taxonomy_tree parent conflicts should fail")

    hub = load_contract("hub-spoke-contract.json")
    hub_svg = assert_valid("hub-spoke example", hub)
    if 'data-diagram-type="hub_spoke"' not in hub_svg or 'id="node-hub"' not in hub_svg:
        raise AssertionError("hub_spoke should render the declared hub")
    if 'edge-dashed' not in hub_svg:
        raise AssertionError("hub_spoke should preserve dashed spoke style")
    assert_hub_spoke_design(hub_svg)
    size_match = re.search(r'<svg[^>]*height="([0-9.]+)"', hub_svg)
    if not size_match or float(size_match.group(1)) > 720:
        raise AssertionError("hub_spoke should use a compact content-driven canvas height")
    hub_stress = load_json("templates/hub_spoke/stress-contract.json")
    hub_stress_svg = assert_valid("hub-spoke stress template", hub_stress)
    if hub_stress_svg.count('class="info-panel"') < 3:
        raise AssertionError("hub_spoke stress template should render operating info panels")
    if hub_stress_svg.count('class="hub-spoke-node spoke-block card"') < 10:
        raise AssertionError("hub_spoke stress template should exercise many designed spoke blocks")

    object_relationship = load_json("templates/object_relationship_diagram/reference-contract.json")
    object_relationship_svg = assert_valid("object relationship reference template", object_relationship)
    assert_object_relationship_design(object_relationship_svg)
    _dtype, object_strategy, _warnings = renderer.diagram_for_contract(object_relationship)
    if object_strategy != "object_relationship":
        raise AssertionError("object_relationship_diagram should select object_relationship strategy")
    object_stress = load_json("templates/object_relationship_diagram/stress-contract.json")
    object_stress_svg = assert_valid("object relationship stress template", object_stress)
    if object_stress_svg.count('class="object-entity-card card"') < 9:
        raise AssertionError("object_relationship_diagram stress template should exercise many entity cards")
    if object_stress_svg.count('class="relationship-diamond"') < 9:
        raise AssertionError("object_relationship_diagram stress template should exercise many relationships")
    if object_stress_svg.count('data-route="orthogonal"') < 2:
        raise AssertionError("object_relationship_diagram stress template should exercise orthogonal relationship routing")
    if "Dashed optional relation" not in object_stress_svg:
        raise AssertionError("object_relationship_diagram stress template should explain dashed optional relationships")
    if len(re.findall(r'<path\b[^>]*class="edge object-relationship-link"[^>]*data-relationship="category_parent"', object_stress_svg)) != 1:
        raise AssertionError("object_relationship_diagram self relationships should render as one connector")
    if not re.search(r'data-link-end="self"[^>]*data-card-anchor="top"[^>]*data-diamond-anchor="bottom"[^>]*data-relationship="category_parent"', object_stress_svg):
        raise AssertionError("object_relationship_diagram should honor explicit self-relationship anchors")
    assert_three_bottom_panels_use_side_stack(object_stress_svg)
    assert_no_direct_diagonal_object_links(object_stress_svg)

    ontology_map = load_json("templates/ontology_map/reference-contract.json")
    ontology_svg = assert_valid("ontology map reference template", ontology_map)
    assert_ontology_map_design(ontology_svg)
    _dtype, ontology_strategy, _warnings = renderer.diagram_for_contract(ontology_map)
    if ontology_strategy != "object_relationship":
        raise AssertionError("ontology_map should reuse the object_relationship strategy")
    ontology_stress = load_json("templates/ontology_map/stress-contract.json")
    ontology_stress_svg = assert_valid("ontology map stress template", ontology_stress)
    if ontology_stress_svg.count('class="ontology-concept-card card"') < 8:
        raise AssertionError("ontology_map stress template should exercise many concept cards")
    if ontology_stress_svg.count('class="relationship-diamond"') < 8:
        raise AssertionError("ontology_map stress template should exercise many predicate diamonds")
    if ontology_stress_svg.count('class="ontology-instance-card card"') < 6:
        raise AssertionError("ontology_map stress template should exercise multiple instances per concept")
    if ontology_stress_svg.count('class="edge ontology-instance-link"') < 6:
        raise AssertionError("ontology_map stress template should exercise instance-to-concept link lanes")
    if 'ontology-side-panel' in ontology_stress_svg:
        raise AssertionError("ontology_map stress template should keep explanatory panels below the map")
    if ontology_stress_svg.count('class="info-panel"') < 3:
        raise AssertionError("ontology_map stress template should exercise bottom info panels")
    assert_bottom_panels_pack_like_masonry(ontology_stress_svg, "metadata")
    assert_ontology_stress_layout(ontology_stress_svg)
    assert_no_direct_diagonal_object_links(ontology_stress_svg)
    reviewed_links = re.findall(r'<path\b[^>]*\bdata-relationship="reviewed_by"[^>]*/>', ontology_stress_svg)
    if len(reviewed_links) < 2 or any('data-route="axis"' not in link for link in reviewed_links[:2]):
        raise AssertionError("ontology_map reviewed_by relation should stay on the direct Evidence-Policy axis")

    capability_map = load_json("templates/capability_domain_map/reference-contract.json")
    capability_svg = assert_valid("capability domain map reference template", capability_map)
    assert_capability_map_design(capability_svg)
    _dtype, capability_strategy, _warnings = renderer.diagram_for_contract(capability_map)
    if capability_strategy != "capability_map":
        raise AssertionError("capability_domain_map should select capability_map strategy")
    if 'capability-side-panel' in capability_svg:
        raise AssertionError("capability_domain_map should render info panels below the map, not as side panels")
    if capability_svg.count('class="info-panel"') < 3:
        raise AssertionError("capability_domain_map should render bottom info panels")
    capability_stress = load_json("templates/capability_domain_map/stress-contract.json")
    capability_stress_svg = assert_valid("capability domain map stress template", capability_stress)
    if capability_stress_svg.count('class="capability-map-item card"') < 40:
        raise AssertionError("capability_domain_map stress template should exercise dense capability cards")
    if capability_stress_svg.count('class="edge capability-map-link"') < 20:
        raise AssertionError("capability_domain_map stress template should exercise sparse but meaningful overlays")
    if capability_stress_svg.count('data-relation="supports"') < 8:
        raise AssertionError("capability_domain_map stress template should exercise shared enabler support overlays")
    support_lane_shifts = [
        float(value)
        for value in re.findall(r'data-relation="supports"[^>]*data-lane-shift="([-0-9.]+)"', capability_stress_svg)
    ]
    if len({round(value, 1) for value in support_lane_shifts if abs(value) > 0.1}) < 4:
        raise AssertionError("capability_domain_map support overlays should use staggered lane shifts")
    repeated_corridors = re.findall(r'data-relation="supports"[^>]*data-corridor-x="([-0-9.]+)"', capability_stress_svg)
    if len(repeated_corridors) < 3:
        raise AssertionError("capability_domain_map stress template should exercise detour corridors")
    if 'capability-side-panel' in capability_stress_svg:
        raise AssertionError("capability_domain_map stress template should keep info panels below the map")
    if capability_stress_svg.count('class="info-panel"') < 3:
        raise AssertionError("capability_domain_map stress template should render bottom info panels")
    if capability_stress_svg.count('capability-column-icon') < 8:
        raise AssertionError("capability_domain_map stress template should exercise column header icons")
    if not all(label_part in capability_stress_svg for label_part in ("Customer", "Experience Ops", "Technology", "Platform")):
        raise AssertionError("capability_domain_map stress template should exercise wrapped long column headers")
    short_lane = renderer._capability_level_label_width({}, [{"id": "a", "label": "A"}, {"id": "b", "label": "Ops"}])
    long_lane = renderer._capability_level_label_width({}, [{"id": "sub", "label": "Sub-Domains"}])
    if not short_lane < long_lane:
        raise AssertionError("capability level label lane should grow from label content instead of using one fixed width")
    long_header_capability = {
        "title": "Capability Long Header Regression",
        "diagram_type": "capability_domain_map",
        "style": "accent-blueprint",
        "width": 900,
        "levels": [{"id": "capability", "label": "Capabilities", "kind": "capability"}],
        "columns": [
            {"id": "customer", "label": "Customer Experience Operations", "kind": "object"},
            {"id": "data", "label": "Semantic Governance Intelligence", "kind": "source"},
        ],
        "items": [
            {"id": "experience", "label": "Experience Ops", "level": "capability", "column": "customer"},
            {"id": "governance", "label": "Governance", "level": "capability", "column": "data"},
        ],
    }
    long_header_svg = assert_valid("capability domain map long header regression", long_header_capability)
    if long_header_svg.count('class="capability-column-label"') < 4:
        raise AssertionError("capability_domain_map long column headers should wrap into multiple label lines")
    for long_label in ("Customer Experience Operations", "Semantic Governance Intelligence"):
        if f">{long_label}</text>" in long_header_svg:
            raise AssertionError("capability_domain_map column headers should fit long labels inside the header slot")

    relationship_matrix = load_json("templates/relationship_matrix/reference-contract.json")
    relationship_svg = assert_valid("relationship matrix reference template", relationship_matrix)
    assert_relationship_matrix_design(relationship_svg, len(relationship_matrix["relationships"]))
    _dtype, relationship_strategy, _warnings = renderer.diagram_for_contract(relationship_matrix)
    if relationship_strategy != "relationship_matrix":
        raise AssertionError("relationship_matrix should select relationship_matrix strategy")
    relationship_minimal = load_json("templates/relationship_matrix/minimal-contract.json")
    relationship_minimal_svg = assert_valid("relationship matrix minimal template", relationship_minimal)
    assert_relationship_matrix_design(relationship_minimal_svg, len(relationship_minimal["relationships"]))
    relationship_stress = load_json("templates/relationship_matrix/stress-contract.json")
    relationship_stress_svg = assert_valid("relationship matrix stress template", relationship_stress)
    assert_relationship_matrix_design(relationship_stress_svg, len(relationship_stress["relationships"]))
    expected_cells = len(relationship_stress["entities"]) ** 2
    if relationship_stress_svg.count('class="matrix-cell"') < expected_cells:
        raise AssertionError("relationship_matrix stress template should render one cell per entity pair")
    stress_width = float(re.search(r'<svg[^>]*width="([0-9.]+)"', relationship_stress_svg).group(1))
    if stress_width > float(relationship_stress["width"]):
        raise AssertionError("relationship_matrix stress template should not widen solely to reserve an auxiliary panel rail")
    if "Payment approval gates shipment release" not in relationship_stress_svg:
        raise AssertionError("relationship_matrix stress template should render static focus relationship details")
    if not re.search(r'class="matrix-rank-label"[^>]*>[^<]*\.\.\.</text>', relationship_stress_svg):
        raise AssertionError("relationship_matrix stress template should exercise fitted top-connected labels")
    if not re.search(r'class="matrix-row-label"[^>]*>[^<]*\.\.\.</text>', relationship_stress_svg):
        raise AssertionError("relationship_matrix stress template should exercise fitted long entity labels")
    if "Commercial Order Orchestration Control Tower Across Regional Fulfillment Channels</text>" in relationship_stress_svg:
        raise AssertionError("relationship_matrix stress template should not render long entity labels unbounded")
    fitted_rank_label = renderer._fit_text_to_width(
        "Very Long Semantic Relationship Node Label For Dense Ranking Panels",
        150,
        18,
        min_chars=8,
    )
    if not fitted_rank_label.endswith("...") or len(fitted_rank_label) > 18:
        raise AssertionError("relationship_matrix ranking labels should have a reusable width-fitting guard")

    print("render_semantic_diagram selftest: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
