---
name: build-knowledge-graph-visuals
description: 从中文课程文章、技术专栏、访谈材料、文档或章节内容中抽取有证据的知识实体与有方向的关系，并通过确定性径向或叙事闭环模板生成可编辑竖版知识图谱、同构黑白 SVG 和高清 PNG/JPG。用于知识图谱、网状关系图、章节复习大图和手机传播长图；不用于纯线性流程、目录层级、统计图或自由风格 AI 生图。
---

# 内容驱动的知识图谱视觉化

把课程内容转换为“可验证的知识关系 + 有明确视觉论点的稳定图谱”。稳定不等于所有内容套同一种形状；布局必须表达内容本身的结构。

## 核心标准

- 节点是知识对象，不是目录标题；强关系有明确动词和证据，推断必须标明。
- 图必须提出并证明一个判断，不能只是把摘要装进同样大小的卡片。
- 综合教学图同时提供三层信息：一眼看懂的主线、可识别的阶段/角色、能学到具体内容的副文与检验。
- 先写结构化 JSON，再由确定性脚本生成 SVG；黑白主题不得分别手改。
- 示例既约束视觉语言，也约束对应 profile 的空间语法。
- SVG 是母版；禁止让生图模型重绘文字密集图。

## 按需读取

- 建模前读 `references/modeling-method.md`。
- 径向图读 `references/spec-v2.md`。
- 高密度双列叙事图读 `references/spec-v3-story-loop.md`。
- 选择版型和配色时读 `references/theme-system.md`。
- 交付前读 `references/adversarial-review.md` 与 `references/qa-checklist.md`。
- 径向样例：`assets/examples/knowledge-graph-method-spec.json`。
- 叙事闭环样例：`assets/examples/fde-story-loop-spec.json`。

## 工作流

### 1. 定义读者任务与深度

写清读者看完后要回答什么、用于导航还是复习、是否允许缩放。

- `compact`：概念导航，保留 8–15 个节点。
- `comprehensive`：完整课程论证，必须包含具体机制、反例、检验和约束，而不是泛化标题。

### 2. 选择能表达内容的 profile

- `story-loop`：存在“为何现在 → 怎么做 → 交付什么 → 如何验证 → 哪些条件成立”的主线，同时有反馈、反例或回路。中文课程长图优先考虑。
- `poster-radial`：没有单一阅读顺序，重点是中心概念与多个对等模块的关系。
- `mobile-radial`：用户明确要求手机无需缩放；必须主动减少节点和交叉关系。

不要因为参考图“有中心节点”就误判为径向图。先看读者视线是在绕中心比较，还是沿上中下推进。

### 3. 建立证据化图谱

完整读取原文，形成中心命题、节点表、关系表、删除项和推断声明。把每条边读成“起点 + 关系 + 终点”；读不通就改词、降级或删除。

结构结论只能是：

- `graph`：交叉关系或反馈回路对理解不可替代。
- `simpler-visual`：流程、层级、矩阵或表格更诚实。
- `split`：内容超过模板容量或存在两个无法统一的主线。
- `insufficient-evidence`：材料不足，需要补充或标注推断。

### 4. 生成并验证

径向模式：

```bash
python <skill-dir>/scripts/build_graph.py <topic>-graph-spec.json --validate-only
python <skill-dir>/scripts/build_graph.py <topic>-graph-spec.json \
  --out-dir <output-dir> --basename <topic>-knowledge-graph
```

叙事闭环：

```bash
python <skill-dir>/scripts/build_story_graph.py <topic>-story-spec.json --validate-only
python <skill-dir>/scripts/build_story_graph.py <topic>-story-spec.json \
  --out-dir <output-dir> --basename <topic>-knowledge-graph
```

验证失败时缩短文案、改关系路由、删减或拆图。禁止绕过脚本手写一个无法回归的 SVG。

### 5. 强制执行渲染—查看—修正

```bash
python <skill-dir>/scripts/compare_svg_structure.py <dark.svg> <light.svg>
python <skill-dir>/scripts/self_test.py
python <skill-dir>/scripts/render_svg.py <dark.svg> --out <dark.png> --scale 2
python <skill-dir>/scripts/render_svg.py <light.svg> --out <light.png> --scale 2
```

脚本通过不等于视觉通过。必须查看整图和文字密集局部，修正溢出、遮挡、失衡、无意义留白和单调配色，然后重新渲染。综合图按自然段或阶段逐区复核，不要一次生成后直接交付。

### 6. 对抗式审查

执行 `references/adversarial-review.md`，记录“问题 → 判断 → 修正”。至少删除或降级一个候选节点或关系；零修改通常意味着审查流于形式。

## 扩展模板

只有现有三种 profile 都无法表达必要结构时才扩展。新增模板必须：

1. 说明现有 profile 为什么失配。
2. 从共享主题变量出发，不从空白设计。
3. 新增结构化规格、确定性渲染、失败校验和回归 fixture。
4. 实际渲染黑白版本并查看，而不是只验证代码。

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

- 未运行所选 profile 的生成器和回归测试。
- 综合图只有抽象标题，没有机制、反例、检验和约束。
- 叙事内容被压成对等径向分组，或径向关系被硬拉成单一路径。
- 标题、副文、图例或关系标签溢出、遮挡、截断。
- 类型颜色与图例不一致，或所有节点同色导致语义层级消失。
- 径向图用贴边长线掩盖主线竞争；`story-loop` 的 rail 没有承担真实反馈或成立条件。
- 黑白两版不是从同一 JSON 生成。
- 发现结构不适配后仍以“形式差不多”为理由放行。
