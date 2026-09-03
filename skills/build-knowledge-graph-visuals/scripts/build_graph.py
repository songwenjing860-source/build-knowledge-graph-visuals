#!/usr/bin/env python3
"""Build matching dark/light knowledge-graph SVGs from a constrained JSON spec.

The renderer intentionally owns geometry, typography, palette, and edge routing.
The calling agent owns only the evidence-backed graph model and a small number of
declared layout choices. This separation makes repeated runs visually stable.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import html
import json
import math
from pathlib import Path
import sys
from typing import Any


PALETTES = {
    "blue": ("#bfdbfe", "#60a5fa", "#2563eb"),
    "green": ("#bbf7d0", "#34d399", "#059669"),
    "amber": ("#fde68a", "#f59e0b", "#d97706"),
    "violet": ("#ddd6fe", "#a78bfa", "#7c3aed"),
    "rose": ("#fbcfe8", "#f472b6", "#db2777"),
}

PROFILES = {
    "poster-radial": {
        "width": 1800,
        "height": 2600,
        "center": (900, 1370),
        "primary_radius": (570, 570),
        "satellite_radius": (710, 815),
        "primary_size": (380, 142),
        "satellite_size": (270, 104),
        "core_radius": 205,
        "max_groups": 5,
        "max_satellites": 3,
        "max_nodes": 21,
        "header_bottom": 340,
        "footer_top": 2260,
        "margin": 42,
        "font": {"title": 72, "subtitle": 32, "guide": 25, "core": 47,
                 "primary": 31, "satellite": 24, "body": 20, "edge": 19},
    },
    "mobile-radial": {
        "width": 1080,
        "height": 2600,
        "center": (540, 1370),
        "primary_radius": (335, 620),
        "satellite_radius": (365, 900),
        "primary_size": (360, 164),
        "satellite_size": (300, 126),
        "core_radius": 178,
        "max_groups": 4,
        "max_satellites": 2,
        "max_nodes": 13,
        "header_bottom": 380,
        "footer_top": 2320,
        "margin": 24,
        "font": {"title": 57, "subtitle": 30, "guide": 24, "core": 39,
                 "primary": 36, "satellite": 34, "body": 26, "edge": 24},
    },
}


@dataclass(frozen=True)
class Box:
    node_id: str
    role: str
    group_id: str
    color: str
    title: str
    subtitle: str
    x: float
    y: float
    width: float
    height: float

    @property
    def cx(self) -> float:
        return self.x + self.width / 2

    @property
    def cy(self) -> float:
        return self.y + self.height / 2


def fail(message: str) -> None:
    raise ValueError(message)


def require_text(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        fail(f"{field} must be a non-empty string")
    text = value.strip()
    if len(text) > maximum:
        fail(f"{field} is too long ({len(text)} > {maximum}); shorten the wording")
    return text


def require_copy_fit(text: str, field: str, width: float, font_size: int,
                     lines: int = 1, padding: float = 40) -> None:
    capacity = max(1, (width - padding) / font_size) * lines
    if visual_units(text) > capacity:
        fail(f"{field} does not fit its {lines}-line slot; shorten the wording")


def validate_spec(spec: dict[str, Any]) -> dict[str, Any]:
    if spec.get("version") != 2:
        fail("version must be 2")
    profile_name = spec.get("profile", "poster-radial")
    if profile_name not in PROFILES:
        fail(f"profile must be one of: {', '.join(PROFILES)}")
    profile = PROFILES[profile_name]
    require_text(spec.get("title"), "title", 32)
    require_text(spec.get("subtitle"), "subtitle", 54)
    require_text(spec.get("reading_guide"), "reading_guide", 78)

    center = spec.get("center")
    if not isinstance(center, dict):
        fail("center must be an object")
    require_text(center.get("id"), "center.id", 32)
    center_title = require_text(center.get("title"), "center.title", 18)
    center_subtitle = require_text(center.get("subtitle"), "center.subtitle", 42)
    core_width = profile["core_radius"] * 2
    require_copy_fit(center_title, "center.title", core_width, profile["font"]["core"], padding=20)
    require_copy_fit(center_subtitle, "center.subtitle", core_width, profile["font"]["body"], lines=2)

    groups = spec.get("groups")
    if not isinstance(groups, list) or not 3 <= len(groups) <= profile["max_groups"]:
        fail(f"groups must contain 3-{profile['max_groups']} groups for {profile_name}")

    ids = {center["id"]}
    legend_labels: list[str] = []
    node_count = 1
    for group_index, group in enumerate(groups):
        field = f"groups[{group_index}]"
        if not isinstance(group, dict):
            fail(f"{field} must be an object")
        group_id = require_text(group.get("id"), f"{field}.id", 24)
        if group_id in ids:
            fail(f"duplicate id: {group_id}")
        color = group.get("color")
        if color not in PALETTES:
            fail(f"{field}.color must be one of: {', '.join(PALETTES)}")
        group_label = require_text(group.get("label"), f"{field}.label", 12)
        legend_labels.append(group_label)
        require_text(group.get("relation"), f"{field}.relation", 10)
        primary = group.get("primary")
        if not isinstance(primary, dict):
            fail(f"{field}.primary must be an object")
        primary_id = require_text(primary.get("id"), f"{field}.primary.id", 32)
        if primary_id in ids:
            fail(f"duplicate id: {primary_id}")
        ids.add(primary_id)
        primary_title = require_text(primary.get("title"), f"{field}.primary.title", 18)
        primary_subtitle = require_text(primary.get("subtitle"), f"{field}.primary.subtitle", 42)
        require_copy_fit(primary_title, f"{field}.primary.title", profile["primary_size"][0], profile["font"]["primary"])
        require_copy_fit(primary_subtitle, f"{field}.primary.subtitle", profile["primary_size"][0], profile["font"]["body"], lines=2)
        node_count += 1

        satellites = group.get("satellites", [])
        if not isinstance(satellites, list) or len(satellites) > profile["max_satellites"]:
            fail(f"{field}.satellites may contain at most {profile['max_satellites']} nodes")
        for satellite_index, node in enumerate(satellites):
            node_field = f"{field}.satellites[{satellite_index}]"
            if not isinstance(node, dict):
                fail(f"{node_field} must be an object")
            node_id = require_text(node.get("id"), f"{node_field}.id", 32)
            if node_id in ids:
                fail(f"duplicate id: {node_id}")
            ids.add(node_id)
            node_title = require_text(node.get("title"), f"{node_field}.title", 16)
            node_subtitle = require_text(node.get("subtitle"), f"{node_field}.subtitle", 32)
            require_copy_fit(node_title, f"{node_field}.title", profile["satellite_size"][0], profile["font"]["satellite"], padding=32)
            require_copy_fit(node_subtitle, f"{node_field}.subtitle", profile["satellite_size"][0], profile["font"]["body"], lines=2, padding=32)
            node_count += 1

    group_legend_width = sum(72 + visual_units(label) * profile["font"]["body"] for label in legend_labels)
    relation_legend_width = 310 if profile_name == "poster-radial" else 0
    if group_legend_width + relation_legend_width > profile["width"] - 2 * profile["margin"]:
        fail("group labels do not fit the legend; shorten the labels")

    if node_count > profile["max_nodes"]:
        fail(f"node count {node_count} exceeds {profile_name} limit {profile['max_nodes']}")

    relations = spec.get("relations", [])
    if not isinstance(relations, list):
        fail("relations must be an array")
    if len(relations) > (5 if profile_name == "poster-radial" else 3):
        fail("too many cross-relations; split the graph instead of creating edge spaghetti")
    for index, relation in enumerate(relations):
        field = f"relations[{index}]"
        if not isinstance(relation, dict):
            fail(f"{field} must be an object")
        if relation.get("source") not in ids or relation.get("target") not in ids:
            fail(f"{field} references an unknown node")
        require_text(relation.get("label"), f"{field}.label", 10)
        if relation.get("strength", "strong") not in {"strong", "weak"}:
            fail(f"{field}.strength must be strong or weak")
        bend = relation.get("bend", 0)
        if not isinstance(bend, (int, float)) or not -160 <= bend <= 160:
            fail(f"{field}.bend must be between -160 and 160")

    return profile


def polar(cx: float, cy: float, rx: float, ry: float, degrees: float) -> tuple[float, float]:
    radians = math.radians(degrees)
    return cx + rx * math.cos(radians), cy + ry * math.sin(radians)


def layout(spec: dict[str, Any], profile: dict[str, Any]) -> dict[str, Box]:
    cx, cy = profile["center"]
    boxes: dict[str, Box] = {}
    center = spec["center"]
    radius = profile["core_radius"]
    boxes[center["id"]] = Box(center["id"], "center", "center", "violet", center["title"],
                                     center["subtitle"], cx - radius, cy - radius,
                                     radius * 2, radius * 2)

    groups = spec["groups"]
    start_angle = -90
    step = 360 / len(groups)
    for index, group in enumerate(groups):
        angle = start_angle + index * step
        px, py = polar(cx, cy, *profile["primary_radius"], angle)
        pw, ph = profile["primary_size"]
        primary = group["primary"]
        boxes[primary["id"]] = Box(primary["id"], "primary", group["id"], group["color"],
                                            primary["title"], primary["subtitle"],
                                            px - pw / 2, py - ph / 2, pw, ph)

        satellites = group.get("satellites", [])
        count = len(satellites)
        if count:
            # Never place a satellite on the same radial ray as its primary:
            # the portrait canvas cannot create enough radial separation at
            # the left/right cardinal slots. Tangential offsets are stable and
            # keep the primary visually dominant.
            if count == 1:
                offsets = [30]
            elif count == 2:
                offsets = [-27, 27]
            else:
                offsets = [-42, -21, 21]
            sw, sh = profile["satellite_size"]
            for node, offset in zip(satellites, offsets, strict=True):
                sx, sy = polar(cx, cy, *profile["satellite_radius"], angle + offset)
                boxes[node["id"]] = Box(node["id"], "satellite", group["id"], group["color"],
                                                 node["title"], node["subtitle"],
                                                 sx - sw / 2, sy - sh / 2, sw, sh)
    return boxes


def overlap(a: Box, b: Box, padding: float = 12) -> bool:
    return not (a.x + a.width + padding <= b.x or b.x + b.width + padding <= a.x
                or a.y + a.height + padding <= b.y or b.y + b.height + padding <= a.y)


def validate_layout(boxes: dict[str, Box], profile: dict[str, Any]) -> None:
    width, height = profile["width"], profile["height"]
    margin = profile["margin"]
    for box in boxes.values():
        if box.x < margin or box.x + box.width > width - margin:
            fail(f"node {box.node_id} violates the horizontal safe area")
        if box.y < profile["header_bottom"] or box.y + box.height > profile["footer_top"]:
            fail(f"node {box.node_id} violates the graph-area safe zone")
    all_boxes = list(boxes.values())
    collisions = []
    for index, first in enumerate(all_boxes):
        for second in all_boxes[index + 1:]:
            if overlap(first, second):
                collisions.append(f"{first.node_id}/{second.node_id}")
    if collisions:
        fail("node collisions: " + ", ".join(collisions))


def curve_geometry(source: Box, target: Box, bend: float) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
    start = clip_to_box(source, target)
    end = clip_to_box(target, source)
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy) or 1
    nx, ny = -dy / length, dx / length
    control = ((start[0] + end[0]) / 2 + nx * bend, (start[1] + end[1]) / 2 + ny * bend)
    return start, control, end


def curve_point(start: tuple[float, float], control: tuple[float, float],
                end: tuple[float, float], t: float) -> tuple[float, float]:
    one_minus = 1 - t
    return (
        one_minus * one_minus * start[0] + 2 * one_minus * t * control[0] + t * t * end[0],
        one_minus * one_minus * start[1] + 2 * one_minus * t * control[1] + t * t * end[1],
    )


def point_in_box(point: tuple[float, float], box: Box, padding: float = 16) -> bool:
    return (box.x - padding <= point[0] <= box.x + box.width + padding
            and box.y - padding <= point[1] <= box.y + box.height + padding)


def validate_relation_routes(spec: dict[str, Any], boxes: dict[str, Box]) -> None:
    for index, relation in enumerate(spec.get("relations", [])):
        source = boxes[relation["source"]]
        target = boxes[relation["target"]]
        geometry = curve_geometry(source, target, relation.get("bend", 0))
        unrelated = [box for box in boxes.values() if box.node_id not in {source.node_id, target.node_id}]
        for step in range(1, 20):
            point = curve_point(*geometry, step / 20)
            hit = next((box for box in unrelated if point_in_box(point, box)), None)
            if hit:
                fail(f"relations[{index}] crosses node {hit.node_id}; change bend or split the graph")


def clip_to_box(source: Box, target: Box) -> tuple[float, float]:
    dx, dy = target.cx - source.cx, target.cy - source.cy
    if dx == 0 and dy == 0:
        return source.cx, source.cy
    scale_x = (source.width / 2) / abs(dx) if dx else float("inf")
    scale_y = (source.height / 2) / abs(dy) if dy else float("inf")
    scale = min(scale_x, scale_y)
    return source.cx + dx * scale, source.cy + dy * scale


def svg_text(text: str) -> str:
    return html.escape(text, quote=True)


def wrap_text(text: str, max_units: int) -> list[str]:
    """Wrap mixed Chinese/Latin text using a stable approximate visual width."""
    words = text.replace("｜", " | ").split()
    if len(words) > 1:
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if visual_units(candidate) <= max_units:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines[:2]
    if visual_units(text) <= max_units:
        return [text]
    midpoint = len(text) // 2
    split_at = min(range(1, len(text)), key=lambda i: abs(i - midpoint) + (0 if text[i - 1] in "，、：；·" else 3))
    return [text[:split_at].rstrip("，、：；·"), text[split_at:].lstrip("，、：；·")]


def visual_units(text: str) -> float:
    return sum(1 if ord(char) > 127 else 0.55 for char in text)


def edge_svg(source: Box, target: Box, label: str, strength: str, bend: float,
             edge_index: int, font_size: int, avoid_boxes: list[Box] | None = None) -> str:
    start, control, end = curve_geometry(source, target, bend)
    path_class = "edge weak" if strength == "weak" else "edge strong"
    marker = "" if strength == "weak" else ' marker-end="url(#arrow)"'
    path = (f'<path data-role="edge" data-source="{svg_text(source.node_id)}" '
            f'data-target="{svg_text(target.node_id)}" class="{path_class}" '
            f'd="M {start[0]:.1f} {start[1]:.1f} Q {control[0]:.1f} {control[1]:.1f} '
            f'{end[0]:.1f} {end[1]:.1f}"{marker}/>' )
    if strength == "weak":
        return path
    label_width = max(76, visual_units(label) * font_size + 30)
    label_height = 38
    candidates = (0.52, 0.35, 0.65, 0.22, 0.78)
    lx, ly = curve_point(start, control, end, candidates[0])
    for candidate in candidates:
        trial_x, trial_y = curve_point(start, control, end, candidate)
        label_box = Box("edge-label", "label", "edge", "", "", "",
                        trial_x - label_width / 2, trial_y - label_height / 2,
                        label_width, label_height)
        if not any(overlap(label_box, box, padding=8) for box in (avoid_boxes or [])):
            lx, ly = trial_x, trial_y
            break
    label_svg = (f'<g data-role="edge-label" data-edge-index="{edge_index}">'
                 f'<rect class="edge-label-bg" x="{lx - label_width / 2:.1f}" y="{ly - 19:.1f}" '
                 f'width="{label_width:.1f}" height="38" rx="13"/>'
                 f'<text class="edge-label" x="{lx:.1f}" y="{ly + 7:.1f}" text-anchor="middle">'
                 f'{svg_text(label)}</text></g>')
    return path + label_svg


def node_svg(box: Box, font: dict[str, int]) -> str:
    role_class = box.role
    title_size = font["core"] if box.role == "center" else font["primary"] if box.role == "primary" else font["satellite"]
    body_size = font["body"]
    if box.role == "center":
        shape = (f'<circle class="node-shape center-shape" cx="{box.cx:.1f}" cy="{box.cy:.1f}" '
                 f'r="{box.width / 2:.1f}"/>')
    else:
        shape = (f'<rect class="node-shape {role_class}-shape color-{box.color}" x="{box.x:.1f}" y="{box.y:.1f}" '
                 f'width="{box.width:.1f}" height="{box.height:.1f}" rx="{34 if box.role == "primary" else 27}"/>')
    max_units = 18 if box.role == "center" else 19 if box.role == "primary" else 16
    subtitle_lines = wrap_text(box.subtitle, max_units)
    title_y = box.cy - (18 if subtitle_lines else 0)
    text = (f'<text class="node-title {role_class}-title" x="{box.cx:.1f}" y="{title_y:.1f}" '
            f'text-anchor="middle" style="font-size:{title_size}px">{svg_text(box.title)}</text>')
    for line_index, line in enumerate(subtitle_lines):
        y = title_y + 43 + line_index * (body_size + 8)
        text += (f'<text class="node-sub {role_class}-sub" x="{box.cx:.1f}" y="{y:.1f}" '
                 f'text-anchor="middle" style="font-size:{body_size}px">{svg_text(line)}</text>')
    return (f'<g id="node-{svg_text(box.node_id)}" data-role="node" data-node-role="{box.role}" '
            f'data-node-id="{svg_text(box.node_id)}" data-group="{svg_text(box.group_id)}" '
            f'data-color="{box.color}" data-x="{box.x:.1f}" data-y="{box.y:.1f}" '
            f'data-width="{box.width:.1f}" data-height="{box.height:.1f}">{shape}{text}</g>')


def render_svg(spec: dict[str, Any], profile: dict[str, Any], boxes: dict[str, Box], theme: str) -> str:
    width, height = profile["width"], profile["height"]
    font = profile["font"]
    dark = theme == "dark"
    background = "#0b1220" if dark else "#ffffff"
    title = "#f8fafc" if dark else "#0f172a"
    body = "#cbd5e1" if dark else "#475569"
    muted = "#94a3b8" if dark else "#64748b"
    panel = "#111827" if dark else "#ffffff"
    panel_stroke = "#334155" if dark else "#dbe3ee"
    edge = "#39c6dc" if dark else "#0891b2"
    weak = "#64748b" if dark else "#94a3b8"
    label_bg = "#101827" if dark else "#ffffff"
    label_text = "#f8fafc" if dark else "#0f172a"
    cx, cy = profile["center"]

    defs = [
        '<linearGradient id="background" x1="0" y1="0" x2="0" y2="1">',
        f'<stop offset="0" stop-color="{background}"/><stop offset="1" stop-color="{("#070b13" if dark else "#f8fafc")}"/>',
        '</linearGradient>',
        '<linearGradient id="core" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f472b6"/><stop offset=".52" stop-color="#8b5cf6"/><stop offset="1" stop-color="#22d3ee"/></linearGradient>',
        '<filter id="shadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="12" stdDeviation="16" flood-opacity=".15"/></filter>',
        f'<marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M0,0 L9,5 L0,10 Z" fill="{edge}"/></marker>',
    ]
    for name, colors in PALETTES.items():
        start, finish, _ = colors
        if not dark:
            start = start
        defs.append(f'<linearGradient id="{name}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{start}"/><stop offset="1" stop-color="{finish}"/></linearGradient>')

    css = f"""
      text {{ font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Noto Sans CJK SC','Microsoft YaHei',sans-serif; }}
      .title {{ fill:{title}; font-weight:900; font-size:{font['title']}px; }}
      .subtitle {{ fill:{body}; font-weight:600; font-size:{font['subtitle']}px; }}
      .guide {{ fill:{muted}; font-size:{font['guide']}px; }}
      .legend {{ fill:{body}; font-size:{font['body']}px; font-weight:700; }}
      .ring {{ fill:none; stroke:{panel_stroke}; stroke-width:2; opacity:.72; }}
      .edge {{ fill:none; stroke-linecap:round; }}
      .edge.strong {{ stroke:{edge}; stroke-width:3.2; opacity:.76; }}
      .edge.weak {{ stroke:{weak}; stroke-width:2.2; stroke-dasharray:9 12; opacity:.52; }}
      .edge-label-bg {{ fill:{label_bg}; stroke:{panel_stroke}; stroke-width:1.5; }}
      .edge-label {{ fill:{label_text}; font-size:{font['edge']}px; font-weight:800; }}
      .node-shape {{ stroke:{("#ffffff" if dark else "#ffffff")}; stroke-width:2; filter:url(#shadow); }}
      .primary-shape {{ stroke-width:2.5; }}
      .satellite-shape {{ opacity:.96; }}
      .color-blue {{ fill:url(#blue); }} .color-green {{ fill:url(#green); }}
      .color-amber {{ fill:url(#amber); }} .color-violet {{ fill:url(#violet); }}
      .color-rose {{ fill:url(#rose); }}
      .center-shape {{ fill:url(#core); stroke:{("#e0f2fe" if dark else "#ffffff")}; stroke-width:5; filter:url(#shadow); }}
      .node-title {{ fill:#0f172a; font-weight:900; }}
      .node-sub {{ fill:#334155; font-weight:550; }}
      .center-title,.center-sub {{ fill:#ffffff; }}
      .center-sub {{ font-weight:650; }}
      .footer-panel {{ fill:{panel}; stroke:{panel_stroke}; stroke-width:1.5; }}
      .footer {{ fill:{body}; font-size:{font['body']}px; }}
      .source {{ fill:{muted}; font-size:{max(17, font['body'] - 3)}px; }}
    """

    group_lookup = {group["id"]: group for group in spec["groups"]}
    edges: list[str] = []
    edge_index = 0
    center_box = boxes[spec["center"]["id"]]
    for group in spec["groups"]:
        primary = boxes[group["primary"]["id"]]
        edges.append(edge_svg(center_box, primary, group["relation"], "strong", 0, edge_index, font["edge"]))
        edge_index += 1
        for satellite in group.get("satellites", []):
            edges.append(edge_svg(primary, boxes[satellite["id"]], "", "weak", 0, edge_index, font["edge"]))
            edge_index += 1
    for relation in spec.get("relations", []):
        avoid = [box for box in boxes.values()
                 if box.node_id not in {relation["source"], relation["target"]}]
        edges.append(edge_svg(boxes[relation["source"]], boxes[relation["target"]], relation["label"],
                              relation.get("strength", "strong"), relation.get("bend", 0),
                              edge_index, font["edge"], avoid))
        edge_index += 1

    legend_items = []
    legend_x = profile["margin"] + 18
    legend_y = 295 if width == 1800 else 275
    for group in spec["groups"]:
        color = group["color"]
        fill = PALETTES[color][1]
        legend_items.append(f'<circle cx="{legend_x}" cy="{legend_y}" r="11" fill="{fill}"/><text class="legend" x="{legend_x + 21}" y="{legend_y + 7}">{svg_text(group["label"])}</text>')
        legend_x += 72 + visual_units(group["label"]) * font["body"]
    if width != 1800:
        legend_x = profile["margin"] + 18
        legend_y = 335
    legend_items.append(f'<path d="M {legend_x} {legend_y} h 46" stroke="{edge}" stroke-width="3" marker-end="url(#arrow)"/><text class="legend" x="{legend_x + 61}" y="{legend_y + 7}">强关系</text>')
    legend_x += 155
    legend_items.append(f'<path d="M {legend_x} {legend_y} h 46" stroke="{weak}" stroke-width="2" stroke-dasharray="8 10"/><text class="legend" x="{legend_x + 61}" y="{legend_y + 7}">弱关联</text>')

    footer = spec.get("footer", "")
    source_note = spec.get("source_note", "")
    footer_lines = wrap_text(footer, 68 if width == 1800 else 39) if footer else []
    footer_y = profile["footer_top"] + 28
    footer_svg = f'<rect class="footer-panel" x="{profile["margin"]}" y="{profile["footer_top"]}" width="{width - 2 * profile["margin"]}" height="{height - profile["footer_top"] - profile["margin"]}" rx="34"/>'
    for index, line in enumerate(footer_lines):
        footer_svg += f'<text class="footer" x="{profile["margin"] + 42}" y="{footer_y + 38 + index * 36}">{svg_text(line)}</text>'
    if source_note:
        footer_svg += f'<text class="source" x="{profile["margin"] + 42}" y="{height - profile["margin"] - 28}">{svg_text(source_note)}</text>'

    group_nodes = []
    for group in spec["groups"]:
        group_nodes.append(node_svg(boxes[group["primary"]["id"]], font))
        group_nodes.extend(node_svg(boxes[node["id"]], font) for node in group.get("satellites", []))
    group_nodes.append(node_svg(center_box, font))

    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" data-layout-version="2" data-profile="{spec["profile"]}" data-theme="{theme}">',
        '<defs>', *defs, '</defs>', f'<style>{css}</style>',
        '<rect width="100%" height="100%" fill="url(#background)"/>',
        f'<text class="title" x="{profile["margin"]}" y="94">{svg_text(spec["title"])}</text>',
        f'<text class="subtitle" x="{profile["margin"]}" y="146">{svg_text(spec["subtitle"])}</text>',
        f'<text class="guide" x="{profile["margin"]}" y="190">{svg_text(spec["reading_guide"])}</text>',
        f'<rect x="{profile["margin"]}" y="245" width="{width - 2 * profile["margin"]}" height="{88 if width == 1800 else 120}" rx="28" fill="{panel}" stroke="{panel_stroke}"/>',
        *legend_items,
        f'<ellipse class="ring" cx="{cx}" cy="{cy}" rx="{profile["primary_radius"][0]}" ry="{profile["primary_radius"][1]}"/>',
        f'<ellipse class="ring" cx="{cx}" cy="{cy}" rx="{profile["satellite_radius"][0]}" ry="{profile["satellite_radius"][1]}"/>',
        '<g id="edges">', *edges, '</g>',
        '<g id="nodes">', *group_nodes, '</g>',
        footer_svg,
        '</svg>',
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path, help="Version-2 JSON graph specification")
    parser.add_argument("--out-dir", type=Path, default=Path.cwd())
    parser.add_argument("--basename", help="Output stem; defaults to the spec filename")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
        profile = validate_spec(spec)
        boxes = layout(spec, profile)
        validate_layout(boxes, profile)
        validate_relation_routes(spec, boxes)
        print(f"PASS: {spec['profile']}, {len(boxes)} nodes, {len(spec.get('relations', []))} cross-relations")
        if args.validate_only:
            return 0
        args.out_dir.mkdir(parents=True, exist_ok=True)
        basename = args.basename or args.spec.stem.removesuffix("-spec")
        for theme in ("dark", "light"):
            output = args.out_dir / f"{basename}-{theme}.svg"
            output.write_text(render_svg(spec, profile, boxes, theme), encoding="utf-8")
            print(f"SVG: {output}")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
