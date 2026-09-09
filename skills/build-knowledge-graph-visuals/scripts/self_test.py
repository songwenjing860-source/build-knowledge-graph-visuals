#!/usr/bin/env python3
"""Run deterministic regression checks for both strict layout profiles."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile

import build_graph
import build_story_graph


def exercise(spec_path: Path) -> None:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    profile = build_graph.validate_spec(spec)
    boxes = build_graph.layout(spec, profile)
    build_graph.validate_layout(boxes, profile)
    label_boxes = build_graph.validate_relation_routes(spec, boxes, profile)
    labels = list(label_boxes.values())
    for index, first in enumerate(labels):
        for second in labels[index + 1:]:
            assert not build_graph.overlap(first, second, padding=6)
    dark = build_graph.render_svg(spec, profile, boxes, "dark")
    light = build_graph.render_svg(spec, profile, boxes, "light")
    expected_nodes = 1 + sum(1 + len(group.get("satellites", [])) for group in spec["groups"])
    for rendered in (dark, light):
        assert rendered.count('data-role="node"') == expected_nodes
        assert rendered.count('data-evidence-id="') >= expected_nodes
        assert f'data-profile="{spec["profile"]}"' in rendered
        assert 'data-layout-version="2"' in rendered
    with tempfile.TemporaryDirectory(prefix="kg-v2-test-") as directory:
        output = Path(directory)
        (output / "dark.svg").write_text(dark, encoding="utf-8")
        (output / "light.svg").write_text(light, encoding="utf-8")


def exercise_rejections(spec_path: Path) -> None:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    too_wide = deepcopy(spec)
    too_wide["groups"][0]["primary"]["title"] = "超" * 18
    try:
        build_graph.validate_spec(too_wide)
    except ValueError as exc:
        assert "does not fit" in str(exc)
    else:
        raise AssertionError("overlong node copy was not rejected")

    unknown_edge = deepcopy(spec)
    unknown_edge["relations"] = [{
        "source": spec["center"]["id"], "target": "missing-node",
        "label": "错误关系", "strength": "strong", "bend": 0,
    }]
    try:
        build_graph.validate_spec(unknown_edge)
    except ValueError as exc:
        assert "unknown node" in str(exc)
    else:
        raise AssertionError("relation to an unknown node was not rejected")

    unknown_evidence = deepcopy(spec)
    unknown_evidence["center"]["evidence_id"] = "missing-evidence"
    try:
        build_graph.validate_spec(unknown_evidence)
    except ValueError as exc:
        assert "unknown evidence" in str(exc)
    else:
        raise AssertionError("unknown evidence reference was not rejected")

    missing_evidence = deepcopy(spec)
    missing_evidence.pop("evidence")
    try:
        build_graph.validate_spec(missing_evidence)
    except ValueError as exc:
        assert "evidence must contain" in str(exc)
    else:
        raise AssertionError("missing evidence registry was not rejected")


def exercise_story(spec_path: Path) -> None:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    boxes = build_story_graph.validate_spec(spec)
    build_story_graph.validate_routes(spec, boxes)
    dark = build_story_graph.render(spec, boxes, "dark")
    light = build_story_graph.render(spec, boxes, "light")
    for rendered in (dark, light):
        assert rendered.count('data-role="node"') == len(boxes)
        assert rendered.count('data-evidence-id="') == len(boxes) + len(spec["relations"])
        assert 'data-profile="story-loop"' in rendered
        assert 'data-layout-version="3"' in rendered

    overflow = deepcopy(spec)
    overflow["nodes"][0]["title"] = "超" * 16
    try:
        build_story_graph.validate_spec(overflow)
    except ValueError as exc:
        assert "overflows" in str(exc)
    else:
        raise AssertionError("story-loop accepted overflowing copy")

    missing_evidence = deepcopy(spec)
    missing_evidence["relations"][0].pop("evidence_id")
    try:
        build_story_graph.validate_spec(missing_evidence)
    except ValueError as exc:
        assert "evidence_id" in str(exc)
    else:
        raise AssertionError("story-loop accepted a relation without evidence")


def main() -> int:
    skill = Path(__file__).resolve().parent.parent
    examples = skill / "assets" / "examples"
    fixtures = [examples / "knowledge-graph-method-spec.json", examples / "mobile-method-spec.json"]
    for fixture in fixtures:
        exercise(fixture)
        print(f"PASS: {fixture.name}")
    exercise_rejections(fixtures[1])
    print("PASS: invalid specs are rejected")
    story_fixture = examples / "fde-story-loop-spec.json"
    exercise_story(story_fixture)
    print(f"PASS: {story_fixture.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
