---
name: build-knowledge-graph-visuals
description: 从中文课程文章、技术专栏、访谈材料、文档或章节内容中抽取有证据的知识实体与有方向的关系，并通过确定性模板生成可编辑的竖版知识图谱、同构黑白 SVG 和高清 PNG/JPG。用于知识图谱、网状关系图、章节复习大图、手机传播长图和中心辐射式课程图谱；不用于只有先后顺序的流程、纯层级目录、统计图或自由风格 AI 生图。
---

# 内容驱动的知识图谱视觉化

把课程内容转换为“可验证的知识关系 + 稳定的视觉图谱”。内容可以变化，视觉系统不能每次重新发明。

## 不可破坏的约束

- 节点是知识对象，不是文章目录。
- 强关系有明确动词和原文证据；推断必须标明。
- 先判断是否真的需要网状图。流程、层级或比较更合适时，不硬做知识图谱。
- 默认使用 v2 严格模式：先写结构化 JSON，再由 `scripts/build_graph.py` 生成 SVG。
- 禁止把示例仅当“灵感”，然后徒手重新设计几何。示例代表必须复用的视觉系统。
- 黑底和白底由同一份 JSON、同一渲染器生成；不分别手改。
- SVG 是母版；PNG/JPG 只是交付格式。禁止让生图模型重绘文字密集图。

## 按需读取

- 开始建模时读 `references/modeling-method.md`。
- 写 v2 JSON 前读 `references/spec-v2.md`。
- 选择 `poster-radial` 或 `mobile-radial` 时读 `references/theme-system.md`。
- 交付前读 `references/adversarial-review.md` 和 `references/qa-checklist.md`。
- `assets/examples/knowledge-graph-method-spec.json` 是最小可执行示例。

## 工作流

### 1. 明确读者任务

写清：读者看完图要能回答什么、图用于课前导航还是课后复习、是否允许缩放。

模式选择：

- `poster-radial`：默认。视觉结构与仓库示例一致，适合课程页面和完整复习图，允许点开缩放。
- `mobile-radial`：用户明确要求手机无需缩放时使用。必须减少节点和交叉关系。

不得因为“手机传播”四个字就自动选择 mobile；传播图片也可能是允许点开的 poster。

### 2. 建立证据化图谱规格

完整读取原文，形成中心命题、节点表、关系表、删除项和推断声明。使用 `references/modeling-method.md`。

把每条边读成“起点 + 关系 + 终点”的完整句子。读不通就改词、降级或删除。

### 3. 通过结构闸门

结论只能是：

- `graph`：至少三条有学习价值的交叉关系，网状结构不可替代。
- `simpler-visual`：流程图、层级图、矩阵或表格更诚实。
- `split`：存在两个以上竞争主线，应拆成总图和子图。
- `insufficient-evidence`：原文不足，需要补材料或标注推断。

出现六步以上单向链路、两个以上闭环，或“主机制 + 岗位比较 + 地域约束”同时竞争时，优先 `split`，不要用超长绕边勉强塞进一张图。

### 4. 编写 v2 JSON

按 `references/spec-v2.md` 编写 `<topic>-graph-spec.json`：

- 中心节点只有一个。
- 每个语义组只有一个一级节点，外圈卫星解释该节点。
- 类型配色由组决定，不给单个节点随意配色。
- `relations` 只保留真正改变理解的跨组关系。
- 不在 JSON 里写坐标、字号、颜色值或 SVG。

先验证：

```bash
python <skill-dir>/scripts/build_graph.py <topic>-graph-spec.json --validate-only
```

验证失败时删减、缩短或拆图。禁止绕过脚本改为自由手写 SVG。

### 5. 确定性生成双主题 SVG

```bash
python <skill-dir>/scripts/build_graph.py <topic>-graph-spec.json \
  --out-dir <output-dir> --basename <topic>-knowledge-graph
```

脚本固定画布、视觉中心、环层、槽位、配色、字体层级和边线规则。只有在用户明确要求一种现有模板无法表达的新构图时，才允许扩展渲染器；扩展后必须新增回归样例。

### 6. 执行自动验证与渲染

```bash
python <skill-dir>/scripts/compare_svg_structure.py <dark.svg> <light.svg>
python <skill-dir>/scripts/self_test.py
python <skill-dir>/scripts/render_svg.py <dark.svg> --out <dark.png> --scale 2
python <skill-dir>/scripts/render_svg.py <light.svg> --out <light.png> --scale 2
```

脚本通过只证明结构和文件正确。仍须在目标显示宽度查看整图和局部，执行 `references/qa-checklist.md`。

### 7. 对抗式审查

执行 `references/adversarial-review.md`，记录“问题 → 判断 → 修正”。至少删除或降级一个候选节点或关系；若零修改，说明审查很可能流于形式。

## 自由布局例外

只有用户明确要求复刻某张新参考图、或严格模板无法表达必要关系时，才可自由布局。此时必须：

1. 先说明为何两个内置 profile 都不适用。
2. 从现有渲染器或 SVG 示例复制视觉变量，不从空白开始。
3. 新增可执行布局验证和一个回归 fixture。
4. 不得把一次自由布局直接称为“风格一致”。

## 默认交付

```text
<topic>-graph-spec.md
<topic>-graph-spec.json
<topic>-knowledge-graph-dark.svg
<topic>-knowledge-graph-dark.png
<topic>-knowledge-graph-light.svg
<topic>-knowledge-graph-light.png
```

交付说明只写：结构结论、profile、尺寸、主要审查修正和残余限制。

## 失败条件

- 未运行 `build_graph.py`，却声称使用了严格模式。
- 中心节点偏离视觉中心，或同心圆不承担分组结构。
- 类型颜色与图例不一致。
- 用贴边超长连线掩盖主线竞争。
- 黑白两版不是从同一 JSON 生成。
- mobile 在约 390 CSS px 宽度下无法直接读关键标签。
- 发现遮挡、越界、错字或结构不适配后仍放行。
