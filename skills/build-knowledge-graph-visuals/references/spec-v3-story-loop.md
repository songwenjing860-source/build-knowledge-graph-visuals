# Version 3 story-loop specification

Generation requires `--explicit-story-request` in addition to the spec path. Pass this only for an explicit user request; `--validate-only` remains available for regression checks without enabling generation.

Use `story-loop` ONLY when the user explicitly requests this profile or a two-column narrative diagram. Narrative, feedback, tests, constraints, reading order, or return paths in the source material do not authorize this choice. Otherwise use `poster-radial`. This legacy template is excluded from default visual references.

## Shape

- Canvas: `1080 × 3000`; default export: `2160 × 6000`.
- One center claim plus 10–14 named slots.
- 12–24 meaningful relations.
- Six semantic node types: `mechanism`, `problem`, `constraint`, `validation`, `action`, `boundary`.
- Five route choices: `direct`, `left-rail`, `right-rail`, `top-lane`, `bottom-lane`.
- `｜` inside a subtitle requests a balanced two-line split. The renderer rejects a split that cannot fit.

## Slots

```text
premise-left       premise-right
trigger-left       trigger-right
                 [center]
role-left          role-right
outcome-left       outcome-right
             synthesis-center
test-left          test-right
context-left       context-right
              condition-center
```

The slot names are semantic reading positions, not arbitrary coordinates. Leave a slot empty only when the source material genuinely lacks that role.

## Minimal schema

```json
{
  "version": 3,
  "profile": "story-loop",
  "title": "主题",
  "subtitle": "范围",
  "reading_guide": "如何读图",
  "footer": "可独立传播的判断",
  "source_note": "来源与推断声明",
  "evidence": [{
    "id": "lesson-01-p12", "source": "课程第 01 讲", "locator": "第 12 段"
  }],
  "center": {
    "id": "core", "title": "中心判断", "subtitle": "结果｜复利",
    "evidence_id": "lesson-01-p12"
  },
  "nodes": [{
    "id": "problem", "slot": "premise-left", "type": "problem",
    "title": "真实问题", "subtitle": "具体表现｜造成的后果",
    "evidence_id": "lesson-01-p12"
  }],
  "relations": [{
    "source": "problem", "target": "core", "label": "暴露",
    "kind": "strong", "route": "left-rail", "label_at": 0.72, "bend": 0,
    "evidence_id": "lesson-01-p12", "status": "explicit"
  }]
}
```

`evidence` is required. Every center, node, and relation references a valid `evidence_id`. `status` may be `explicit`, `inferred`, or `disputed`; omitted values default to `explicit`.

## Commands

```bash
python <skill-dir>/scripts/build_story_graph.py story-spec.json --validate-only
python <skill-dir>/scripts/build_story_graph.py story-spec.json --out-dir outputs --basename topic-knowledge-graph
python <skill-dir>/scripts/compare_svg_structure.py outputs/topic-knowledge-graph-dark.svg outputs/topic-knowledge-graph-light.svg
```

Validation covers text capacity, unique slots, node crossings, relation-label collisions, canvas bounds, relation count, and reference integrity. A failed route is a request to change `route`, `bend`, or `label_at`; do not hide the edge behind a card.
