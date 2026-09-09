# Version 2 graph specification

Use this schema with `scripts/build_graph.py`. The JSON is the source of truth for content; the renderer owns geometry and visual styling.

```json
{
  "version": 2,
  "profile": "poster-radial",
  "title": "知识图谱标题",
  "subtitle": "内容范围或章节说明",
  "reading_guide": "中心是核心判断，第一圈是关键模块，外圈是问题、机制和指标。",
  "footer": "一句可以独立传播的核心判断。",
  "source_note": "来源：用户提供的材料；推断关系已在图谱规格中标明。",
  "evidence": [{
    "id": "lesson-01-p12",
    "source": "课程第 01 讲",
    "locator": "第 12 段",
    "excerpt": "支持该节点或关系的简短原文"
  }],
  "center": {
    "id": "core",
    "title": "核心对象",
    "subtitle": "它解决什么问题，以及为什么重要",
    "evidence_id": "lesson-01-p12"
  },
  "groups": [
    {
      "id": "inputs",
      "label": "输入理解",
      "color": "blue",
      "relation": "依赖",
      "evidence_id": "lesson-01-p12",
      "primary": {
        "id": "input-normalization",
        "title": "输入规范化",
        "subtitle": "把自然输入变成结构化输入",
        "evidence_id": "lesson-01-p12"
      },
      "satellites": [
        {
          "id": "context",
          "title": "上下文召回",
          "subtitle": "历史对话与关键事实",
          "evidence_id": "lesson-01-p12"
        }
      ]
    }
  ],
  "relations": [
    {
      "source": "input-normalization",
      "target": "another-primary-node",
      "label": "提供输入",
      "strength": "strong",
      "bend": 60,
      "evidence_id": "lesson-01-p12",
      "status": "explicit"
    }
  ]
}
```

## Profiles

### `poster-radial`

- Canvas: `1800 × 2600`.
- Groups: 3–5.
- Satellites per group: 0–3.
- Total nodes including center: at most 21.
- Cross-relations: at most 5.
- Use for course pages and deep-review posters where readers may zoom.

### `mobile-radial`

- Canvas: `1080 × 2600`.
- Groups: 3–4.
- Satellites per group: 0–2.
- Total nodes including center: at most 13.
- Cross-relations: at most 3.
- Use only when key labels must remain readable at approximately 390 CSS pixels wide.

## Invariants

- Every group has exactly one primary node. Satellites explain or qualify that primary node.
- A group has one semantic color. Do not assign colors node by node.
- `relation` is the labeled strong edge between the center and the group primary.
- `evidence` is required. Every center, primary, satellite, group relation, and cross-relation must reference a valid `evidence_id`.
- `status` may be `explicit`, `inferred`, or `disputed`; omitted values default to `explicit`.
- A group may use `bend` from `-160` to `160` when its center relation needs room for a collision-free label.
- `relations` contains only cross-group relations that materially change understanding.
- `bend` may be `-160` to `160`; use it only to separate a cross-edge from another edge.
- Do not add coordinates, colors, font sizes, gradients, or SVG fragments to the JSON.
- If the limits reject the content, delete low-value nodes or split the deliverable. Do not bypass the validator.

## Commands

```bash
python <skill-dir>/scripts/build_graph.py graph-spec.json --validate-only
python <skill-dir>/scripts/build_graph.py graph-spec.json --out-dir outputs --basename topic-knowledge-graph
python <skill-dir>/scripts/compare_svg_structure.py outputs/topic-knowledge-graph-dark.svg outputs/topic-knowledge-graph-light.svg
```

The renderer returning an error is a design signal, not an invitation to hand-write an unconstrained SVG.
