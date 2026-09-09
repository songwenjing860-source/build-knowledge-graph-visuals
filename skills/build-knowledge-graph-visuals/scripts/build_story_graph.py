#!/usr/bin/env python3
"""Render a dense two-column story-loop knowledge map from a v3 JSON spec."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import html
import json
import math
from pathlib import Path
import sys
from typing import Any, Callable


WIDTH, HEIGHT = 1080, 3000
MARGIN = 28
FONT = {"title": 58, "subtitle": 30, "guide": 24, "node": 35,
        "body": 27, "core": 43, "core_body": 30, "edge": 22}

SLOTS = {
    "premise-left": (45, 390, 420, 170), "premise-right": (615, 390, 420, 170),
    "trigger-left": (45, 700, 420, 180), "trigger-right": (615, 700, 420, 180),
    "role-left": (45, 1290, 420, 160), "role-right": (615, 1290, 420, 160),
    "outcome-left": (45, 1555, 420, 160), "outcome-right": (615, 1555, 420, 160),
    "synthesis-center": (270, 1835, 540, 165),
    "test-left": (45, 2105, 420, 170), "test-right": (615, 2105, 420, 170),
    "context-left": (45, 2390, 420, 170), "context-right": (615, 2390, 420, 170),
    "condition-center": (270, 2670, 540, 165),
}
CORE_SLOT = (300, 1000, 480, 220)

TYPE_STYLE = {
    "mechanism": ("机制", "#a5f3fc", "#22d3ee"),
    "problem": ("问题", "#fecdd3", "#fb7185"),
    "constraint": ("约束", "#fde68a", "#f59e0b"),
    "validation": ("验证", "#d9f99d", "#84cc16"),
    "action": ("行动", "#bbf7d0", "#34d399"),
    "boundary": ("边界", "#ddd6fe", "#a78bfa"),
}

VALID_STATUSES = {"explicit", "inferred", "disputed"}


@dataclass(frozen=True)
class Box:
    node_id: str
    x: float
    y: float
    width: float
    height: float
    node_type: str
    title: str
    subtitle: str
    slot: str
    evidence_id: str = ""
    status: str = "explicit"

    @property
    def cx(self) -> float:
        return self.x + self.width / 2

    @property
    def cy(self) -> float:
        return self.y + self.height / 2


def fail(message: str) -> None:
    raise ValueError(message)


def visual_units(text: str) -> float:
    return sum(1 if ord(char) > 127 else 0.55 for char in text)


def require_text(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        fail(f"{field} must be a non-empty string")
    value = value.strip()
    if len(value) > maximum:
        fail(f"{field} is too long ({len(value)} > {maximum})")
    return value


def validate_evidence(spec: dict[str, Any]) -> set[str]:
    evidence = spec.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        fail("evidence must contain at least one source record")
    evidence_ids: set[str] = set()
    for index, item in enumerate(evidence):
        field = f"evidence[{index}]"
        if not isinstance(item, dict):
            fail(f"{field} must be an object")
        evidence_id = require_text(item.get("id"), f"{field}.id", 32)
        if evidence_id in evidence_ids:
            fail(f"duplicate evidence id: {evidence_id}")
        evidence_ids.add(evidence_id)
        require_text(item.get("source"), f"{field}.source", 80)
        require_text(item.get("locator"), f"{field}.locator", 120)
        excerpt = item.get("excerpt")
        if excerpt is not None:
            require_text(excerpt, f"{field}.excerpt", 220)
    return evidence_ids


def validate_evidence_ref(item: dict[str, Any], field: str,
                          evidence_ids: set[str]) -> tuple[str, str]:
    evidence_id = require_text(item.get("evidence_id"), f"{field}.evidence_id", 32)
    if evidence_id not in evidence_ids:
        fail(f"{field}.evidence_id references unknown evidence: {evidence_id}")
    status = item.get("status", "explicit")
    if status not in VALID_STATUSES:
        fail(f"{field}.status must be one of: {', '.join(sorted(VALID_STATUSES))}")
    return evidence_id, status


def split_two_lines(text: str, capacity: float) -> list[str]:
    for separator in ("｜", "|"):
        if separator in text:
            parts = [part.strip() for part in text.split(separator) if part.strip()]
            if len(parts) < 2:
                fail("forced line break needs at least two text parts")
            candidates = []
            for index in range(1, len(parts)):
                lines = ("｜".join(parts[:index]), "｜".join(parts[index:]))
                candidates.append((max(visual_units(line) for line in lines), lines))
            widest, lines = min(candidates, key=lambda item: item[0])
            if widest > capacity:
                fail("forced line break does not fit its two-line slot")
            return list(lines)
    if visual_units(text) <= capacity:
        return [text]
    candidates: list[tuple[float, int]] = []
    for index in range(1, len(text)):
        left = text[:index].rstrip(" ，、｜|：；")
        right = text[index:].lstrip(" ，、｜|：；")
        if not left or not right:
            continue
        widest = max(visual_units(left), visual_units(right))
        punctuation_bonus = -1.5 if text[index - 1] in " ，、｜|：；" else 0
        candidates.append((widest + punctuation_bonus, index))
    if not candidates:
        fail("text cannot be wrapped")
    _, split_at = min(candidates)
    lines = [text[:split_at].rstrip(" ，、｜|：；"), text[split_at:].lstrip(" ，、｜|：；")]
    if max(visual_units(line) for line in lines) > capacity:
        fail("text does not fit its two-line slot")
    return lines


def validate_copy(title: str, subtitle: str, width: float, field: str,
                  title_font: int = FONT["node"], body_font: int = FONT["body"]) -> None:
    if visual_units(title) * title_font > width - 50:
        fail(f"{field}.title overflows its card; shorten it")
    try:
        split_two_lines(subtitle, (width - 54) / body_font)
    except ValueError as exc:
        fail(f"{field}.subtitle {exc}")


def validate_spec(spec: dict[str, Any]) -> dict[str, Box]:
    if spec.get("version") != 3 or spec.get("profile") != "story-loop":
        fail("story-loop requires version 3 and profile story-loop")
    evidence_ids = validate_evidence(spec)
    title = require_text(spec.get("title"), "title", 28)
    subtitle = require_text(spec.get("subtitle"), "subtitle", 48)
    guide = require_text(spec.get("reading_guide"), "reading_guide", 70)
    footer = require_text(spec.get("footer"), "footer", 58)
    source_note = require_text(spec.get("source_note"), "source_note", 72)
    for text, field, font in ((title, "title", FONT["title"]),
                              (subtitle, "subtitle", FONT["subtitle"]),
                              (guide, "reading_guide", FONT["guide"]),
                              (footer, "footer", 24), (source_note, "source_note", 20)):
        if visual_units(text) * font > WIDTH - 2 * MARGIN - 24:
            fail(f"{field} overflows the canvas; shorten it")

    center = spec.get("center")
    if not isinstance(center, dict):
        fail("center must be an object")
    center_id = require_text(center.get("id"), "center.id", 24)
    center_title = require_text(center.get("title"), "center.title", 18)
    center_subtitle = require_text(center.get("subtitle"), "center.subtitle", 40)
    center_evidence, center_status = validate_evidence_ref(center, "center", evidence_ids)
    validate_copy(center_title, center_subtitle, CORE_SLOT[2], "center",
                  FONT["core"], FONT["core_body"])
    boxes = {center_id: Box(center_id, *CORE_SLOT, "center", center_title,
                            center_subtitle, "center", center_evidence, center_status)}

    nodes = spec.get("nodes")
    if not isinstance(nodes, list) or not 10 <= len(nodes) <= len(SLOTS):
        fail(f"nodes must contain 10-{len(SLOTS)} items")
    used_slots: set[str] = set()
    for index, node in enumerate(nodes):
        field = f"nodes[{index}]"
        if not isinstance(node, dict):
            fail(f"{field} must be an object")
        node_id = require_text(node.get("id"), f"{field}.id", 28)
        if node_id in boxes:
            fail(f"duplicate node id: {node_id}")
        slot = node.get("slot")
        if slot not in SLOTS:
            fail(f"{field}.slot must be a named story-loop slot")
        if slot in used_slots:
            fail(f"duplicate slot: {slot}")
        used_slots.add(slot)
        node_type = node.get("type")
        if node_type not in TYPE_STYLE:
            fail(f"{field}.type must be one of: {', '.join(TYPE_STYLE)}")
        title = require_text(node.get("title"), f"{field}.title", 16)
        subtitle = require_text(node.get("subtitle"), f"{field}.subtitle", 40)
        evidence_id, status = validate_evidence_ref(node, field, evidence_ids)
        x, y, width, height = SLOTS[slot]
        validate_copy(title, subtitle, width, field)
        boxes[node_id] = Box(node_id, x, y, width, height, node_type, title, subtitle, slot,
                             evidence_id, status)

    ids = set(boxes)
    relations = spec.get("relations")
    if not isinstance(relations, list) or not 12 <= len(relations) <= 24:
        fail("relations must contain 12-24 meaningful edges")
    allowed_routes = {"direct", "left-rail", "right-rail", "top-lane", "bottom-lane"}
    for index, relation in enumerate(relations):
        field = f"relations[{index}]"
        if relation.get("source") not in ids or relation.get("target") not in ids:
            fail(f"{field} references an unknown node")
        require_text(relation.get("label"), f"{field}.label", 10)
        validate_evidence_ref(relation, field, evidence_ids)
        if relation.get("kind", "strong") not in {"strong", "constraint", "weak"}:
            fail(f"{field}.kind must be strong, constraint, or weak")
        if relation.get("route", "direct") not in allowed_routes:
            fail(f"{field}.route must be one of: {', '.join(allowed_routes)}")
        label_at = relation.get("label_at", 0.5)
        if not isinstance(label_at, (int, float)) or not 0.15 <= label_at <= 0.85:
            fail(f"{field}.label_at must be between 0.15 and 0.85")
        bend = relation.get("bend", 0)
        if not isinstance(bend, (int, float)) or not -180 <= bend <= 180:
            fail(f"{field}.bend must be between -180 and 180")
    return boxes


def clip_to_box(source: Box, target_x: float, target_y: float) -> tuple[float, float]:
    dx, dy = target_x - source.cx, target_y - source.cy
    if not dx and not dy:
        return source.cx, source.cy
    scale_x = source.width / 2 / abs(dx) if dx else float("inf")
    scale_y = source.height / 2 / abs(dy) if dy else float("inf")
    scale = min(scale_x, scale_y)
    return source.cx + dx * scale, source.cy + dy * scale


def route_geometry(source: Box, target: Box, route: str, bend: float) -> tuple[str, Callable[[float], tuple[float, float]], list[tuple[float, float]]]:
    start = clip_to_box(source, target.cx, target.cy)
    end = clip_to_box(target, source.cx, source.cy)
    if route == "direct":
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy) or 1
        control = ((start[0] + end[0]) / 2 - dy / length * bend,
                   (start[1] + end[1]) / 2 + dx / length * bend)
        def point(t: float) -> tuple[float, float]:
            u = 1 - t
            return (u*u*start[0] + 2*u*t*control[0] + t*t*end[0],
                    u*u*start[1] + 2*u*t*control[1] + t*t*end[1])
        samples = [point(i / 30) for i in range(31)]
        return f"M {start[0]:.1f} {start[1]:.1f} Q {control[0]:.1f} {control[1]:.1f} {end[0]:.1f} {end[1]:.1f}", point, samples

    if route == "left-rail":
        points = [start, (20, start[1]), (20, end[1]), end]
    elif route == "right-rail":
        points = [start, (1060, start[1]), (1060, end[1]), end]
    elif route == "top-lane":
        points = [start, (start[0], 620), (end[0], 620), end]
    else:
        points = [start, (start[0], 2870), (end[0], 2870), end]
    lengths = [math.dist(a, b) for a, b in zip(points, points[1:])]
    total = sum(lengths) or 1
    def point(t: float) -> tuple[float, float]:
        remaining = t * total
        for (a, b), length in zip(zip(points, points[1:]), lengths):
            if remaining <= length:
                ratio = remaining / length if length else 0
                return a[0] + (b[0] - a[0]) * ratio, a[1] + (b[1] - a[1]) * ratio
            remaining -= length
        return points[-1]
    samples = [point(i / 40) for i in range(41)]
    return "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in points), point, samples


def point_inside(point: tuple[float, float], box: Box, padding: float = 10) -> bool:
    return box.x - padding <= point[0] <= box.x + box.width + padding and box.y - padding <= point[1] <= box.y + box.height + padding


def validate_routes(spec: dict[str, Any], boxes: dict[str, Box]) -> None:
    label_boxes: list[tuple[float, float, float, float]] = []
    for index, relation in enumerate(spec["relations"]):
        source, target = boxes[relation["source"]], boxes[relation["target"]]
        _, point, samples = route_geometry(source, target, relation.get("route", "direct"), relation.get("bend", 0))
        unrelated = [box for box in boxes.values() if box.node_id not in {source.node_id, target.node_id}]
        hit = next((box for sample in samples[2:-2] for box in unrelated if point_inside(sample, box)), None)
        if hit:
            fail(f"relations[{index}] crosses node {hit.node_id}; change route or bend")
        lx, ly = point(relation.get("label_at", 0.5))
        label_width = max(82, visual_units(relation["label"]) * FONT["edge"] + 28)
        rect = (lx - label_width / 2, ly - 20, label_width, 40)
        if rect[0] < 4 or rect[0] + rect[2] > WIDTH - 4:
            fail(f"relations[{index}] label leaves the canvas; change label_at")
        if any(not (rect[0] + rect[2] + 6 <= old[0] or old[0] + old[2] + 6 <= rect[0]
                       or rect[1] + rect[3] + 6 <= old[1] or old[1] + old[3] + 6 <= rect[1])
               for old in label_boxes):
            fail(f"relations[{index}] label collides with another relation label")
        label_hits = [box for box in boxes.values()
                      if not (rect[0] + rect[2] + 4 <= box.x or box.x + box.width + 4 <= rect[0]
                              or rect[1] + rect[3] + 4 <= box.y or box.y + box.height + 4 <= rect[1])]
        if label_hits:
            fail(f"relations[{index}] label overlaps node {label_hits[0].node_id}; change label_at")
        label_boxes.append(rect)


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def node_svg(box: Box) -> str:
    if box.node_type == "center":
        title_font, body_font = FONT["core"], FONT["core_body"]
        subtitle_lines = split_two_lines(box.subtitle, (box.width - 60) / body_font)
        shape = (f'<rect class="core-outer" x="{box.x}" y="{box.y}" width="{box.width}" height="{box.height}" rx="92"/>'
                 f'<rect class="core-inner" x="{box.x + 17}" y="{box.y + 17}" width="{box.width - 34}" height="{box.height - 34}" rx="76"/>')
    else:
        title_font, body_font = FONT["node"], FONT["body"]
        subtitle_lines = split_two_lines(box.subtitle, (box.width - 54) / body_font)
        shape = f'<rect class="node-shape type-{box.node_type}" x="{box.x}" y="{box.y}" width="{box.width}" height="{box.height}" rx="30"/>'
    title_y = box.cy - (36 if len(subtitle_lines) == 2 else 20)
    text = f'<text class="node-title {"core-text" if box.node_type == "center" else ""}" x="{box.cx}" y="{title_y}" text-anchor="middle" style="font-size:{title_font}px">{esc(box.title)}</text>'
    first_y = title_y + 48
    for line_index, line in enumerate(subtitle_lines):
        text += f'<text class="node-sub {"core-text" if box.node_type == "center" else ""}" x="{box.cx}" y="{first_y + line_index * (body_font + 8)}" text-anchor="middle" style="font-size:{body_font}px">{esc(line)}</text>'
    return (f'<g data-role="node" data-node-id="{esc(box.node_id)}" data-slot="{box.slot}" '
            f'data-type="{box.node_type}" data-evidence-id="{esc(box.evidence_id)}" '
            f'data-status="{esc(box.status)}">{shape}{text}</g>')


def render(spec: dict[str, Any], boxes: dict[str, Box], theme: str) -> str:
    dark = theme == "dark"
    bg = "#0b1323" if dark else "#f8fafc"
    bg2 = "#070b13" if dark else "#ffffff"
    title_color = "#f8fafc" if dark else "#0f172a"
    body_color = "#cbd5e1" if dark else "#334155"
    muted = "#94a3b8" if dark else "#64748b"
    panel = "#101827" if dark else "#ffffff"
    border = "#334155" if dark else "#cbd5e1"
    edge_colors = {"strong": "#49d6e9" if dark else "#0891b2",
                   "constraint": "#fbbf24" if dark else "#d97706",
                   "weak": "#64748b" if dark else "#94a3b8"}
    defs = [
        f'<linearGradient id="page" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{bg}"/><stop offset="1" stop-color="{bg2}"/></linearGradient>',
        '<linearGradient id="core-fill" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#31596b"/><stop offset="1" stop-color="#164e63"/></linearGradient>',
        '<filter id="shadow" x="-25%" y="-25%" width="150%" height="160%"><feDropShadow dx="0" dy="10" stdDeviation="14" flood-opacity=".16"/></filter>',
    ]
    for key, (_, start, end) in TYPE_STYLE.items():
        defs.append(f'<linearGradient id="{key}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{start}"/><stop offset="1" stop-color="{end}"/></linearGradient>')
    for kind, color in edge_colors.items():
        defs.append(f'<marker id="arrow-{kind}" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M0,0 L9,5 L0,10 Z" fill="{color}"/></marker>')
    css = f"""
    text{{font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Noto Sans CJK SC','Microsoft YaHei',sans-serif}}
    .title{{fill:{title_color};font-size:{FONT['title']}px;font-weight:900}} .subtitle{{fill:{body_color};font-size:{FONT['subtitle']}px;font-weight:700}}
    .guide{{fill:{muted};font-size:{FONT['guide']}px}} .legend{{fill:{body_color};font-size:23px;font-weight:750}}
    .ring{{fill:none;stroke:{border};stroke-width:2;opacity:.62}} .edge{{fill:none;stroke-linecap:round;stroke-linejoin:round}}
    .edge.strong{{stroke:{edge_colors['strong']};stroke-width:3.6}} .edge.constraint{{stroke:{edge_colors['constraint']};stroke-width:3.6}}
    .edge.weak{{stroke:{edge_colors['weak']};stroke-width:2.4;stroke-dasharray:9 12;opacity:.7}}
    .edge-label-bg{{fill:{panel};stroke:{border};stroke-width:1.5}} .edge-label{{fill:{title_color};font-size:{FONT['edge']}px;font-weight:800}}
    .node-shape{{stroke:#fff;stroke-width:2.2;filter:url(#shadow)}}
    .type-mechanism{{fill:url(#mechanism)}} .type-problem{{fill:url(#problem)}} .type-constraint{{fill:url(#constraint)}}
    .type-validation{{fill:url(#validation)}} .type-action{{fill:url(#action)}} .type-boundary{{fill:url(#boundary)}}
    .node-title{{fill:#0f172a;font-weight:900}} .node-sub{{fill:#334155;font-weight:600}}
    .core-outer{{fill:#6ee7f9;stroke:#e0f2fe;stroke-width:3;filter:url(#shadow)}} .core-inner{{fill:url(#core-fill);stroke:#22d3ee;stroke-width:3}}
    .core-text{{fill:#fff}} .footer{{fill:{body_color};font-size:24px;font-weight:800}} .source{{fill:{muted};font-size:20px}}
    """
    edges = []
    labels = []
    for index, relation in enumerate(spec["relations"]):
        kind = relation.get("kind", "strong")
        path, point, _ = route_geometry(boxes[relation["source"]], boxes[relation["target"]], relation.get("route", "direct"), relation.get("bend", 0))
        marker = "" if kind == "weak" else f' marker-end="url(#arrow-{kind})"'
        edges.append(
            f'<path class="edge {kind}" data-source="{esc(relation["source"])}" '
            f'data-target="{esc(relation["target"])}" '
            f'data-evidence-id="{esc(relation["evidence_id"])}" '
            f'data-status="{esc(relation.get("status", "explicit"))}" d="{path}"{marker}/>'
        )
        if kind != "weak" or relation.get("show_label", True):
            lx, ly = point(relation.get("label_at", 0.5))
            label_width = max(82, visual_units(relation["label"]) * FONT["edge"] + 28)
            labels.append(f'<g data-role="edge-label" data-edge-index="{index}"><rect class="edge-label-bg" x="{lx-label_width/2:.1f}" y="{ly-20:.1f}" width="{label_width:.1f}" height="40" rx="13"/><text class="edge-label" x="{lx:.1f}" y="{ly+7:.1f}" text-anchor="middle">{esc(relation["label"])}</text></g>')

    used_types = []
    for node in spec["nodes"]:
        if node["type"] not in used_types:
            used_types.append(node["type"])
    legend = []
    x, y = 48, 275
    for node_type in used_types:
        label, _, end = TYPE_STYLE[node_type]
        legend.append(f'<circle cx="{x}" cy="{y}" r="11" fill="{end}"/><text class="legend" x="{x+21}" y="{y+8}">{label}</text>')
        x += 92 + visual_units(label) * 23
        if x > 920:
            x, y = 48, 320
    if y < 320:
        x, y = 48, 320
    for kind, label in (("strong", "强关系"), ("constraint", "约束关系"), ("weak", "弱关联")):
        color = edge_colors[kind]
        dash = ' stroke-dasharray="8 10"' if kind == "weak" else ""
        marker = "" if kind == "weak" else f' marker-end="url(#arrow-{kind})"'
        legend.append(f'<path d="M{x} {y}h42" stroke="{color}" stroke-width="3"{dash}{marker}/><text class="legend" x="{x+57}" y="{y+8}">{label}</text>')
        x += 175

    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" data-layout-version="3" data-profile="story-loop" data-theme="{theme}">',
        '<defs>', *defs, '</defs>', f'<style>{css}</style>', '<rect width="100%" height="100%" fill="url(#page)"/>',
        f'<text class="title" x="{MARGIN}" y="82">{esc(spec["title"])}</text>',
        f'<text class="subtitle" x="{MARGIN}" y="132">{esc(spec["subtitle"])}</text>',
        f'<text class="guide" x="{MARGIN}" y="178">{esc(spec["reading_guide"])}</text>',
        f'<rect x="{MARGIN}" y="220" width="{WIDTH-2*MARGIN}" height="125" rx="28" fill="{panel}" stroke="{border}"/>',
        *legend,
        '<ellipse class="ring" cx="540" cy="1490" rx="510" ry="930"/><ellipse class="ring" cx="540" cy="1490" rx="385" ry="760"/><ellipse class="ring" cx="540" cy="1490" rx="255" ry="575"/>',
        '<g id="edges">', *edges, '</g>', '<g id="nodes">',
        *(node_svg(box) for box in boxes.values()), '</g>', '<g id="edge-labels">', *labels, '</g>',
        f'<text class="footer" x="{MARGIN+16}" y="2915">{esc(spec["footer"])}</text>',
        f'<text class="source" x="{MARGIN+16}" y="2960">{esc(spec["source_note"])}</text>', '</svg>'
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("--out-dir", type=Path, default=Path.cwd())
    parser.add_argument("--basename")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
        boxes = validate_spec(spec)
        validate_routes(spec, boxes)
        print(f"PASS: story-loop, {len(boxes)} nodes, {len(spec['relations'])} relations")
        if args.validate_only:
            return 0
        args.out_dir.mkdir(parents=True, exist_ok=True)
        basename = args.basename or args.spec.stem.removesuffix("-spec")
        for theme in ("dark", "light"):
            output = args.out_dir / f"{basename}-{theme}.svg"
            output.write_text(render(spec, boxes, theme), encoding="utf-8")
            print(f"SVG: {output}")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
