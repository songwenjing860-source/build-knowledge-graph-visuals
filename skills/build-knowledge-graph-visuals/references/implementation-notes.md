# Implementation notes

Read this file only when maintaining the renderers, debugging validation, or extending a profile. It is not required for ordinary graph generation.

## Responsibility boundary

- The agent owns reader intent, the center claim, evidence-backed nodes, relation semantics, status, and deletion decisions.
- JSON is the source of truth for graph content.
- The renderer owns geometry, typography, palette, edge routing, labels, and SVG structure.
- Chrome owns final font shaping and rasterization.
- Automated checks catch structural and geometric defects; they do not prove domain truth.

## Evidence contract

Both schemas require a non-empty top-level `evidence` registry. Each record has a unique `id`, `source`, and `locator`; `excerpt` is optional. Every center, node, group relation, and explicit relation references an existing `evidence_id`.

`status` is one of:

- `explicit`: directly supported by the cited source.
- `inferred`: an editorial synthesis supported but not directly stated.
- `disputed`: retained because the material itself contains a disagreement.

The renderer copies evidence IDs and status values into SVG `data-*` attributes. This preserves traceability without putting citations into the visible poster.

## Radial label planning

`build_graph.py` creates one ordered edge list for center spokes, satellite links, and cross-relations. It validates every path, then plans all visible labels together.

For each strong label it tries curve positions `0.52`, `0.35`, `0.65`, `0.22`, and `0.78`. A candidate is rejected when it leaves the canvas, overlaps any node, or overlaps an earlier label. A group-level `bend` can create space for center-spoke labels; its range is `-160..160`.

Do not weaken this check merely to keep a crowded graph. Shorten the label, change the bend, reduce content, select another profile, or split the graph.

## Browser geometry validation

`validate_svg_geometry.py` embeds the SVG in a temporary local HTML document and opens it in headless Chrome. After `document.fonts.ready`, it uses `getBoundingClientRect()` to check:

- every node text element is inside its node shape;
- every edge-label text element is inside its label background;
- every text element stays inside the SVG canvas.

This check complements the fast Python visual-unit estimate with the actual browser font metrics used for delivery.

## Mobile review artifacts

`make_mobile_previews.py` renders the SVG at a real target display width, defaulting to 390 px. It creates:

- `<name>-mobile-full.png`;
- `<name>-mobile-top.png`;
- `<name>-mobile-middle.png`;
- `<name>-mobile-bottom.png`.

The three crops are review surfaces, not additional deliverables. Inspect them before claiming mobile readability.

## Rendering details

`render_svg.py` uses headless Chrome with a temporary profile, a fixed logical window, and a forced device scale factor. It waits for a stable PNG, stops the process group, reads the PNG header, and rejects unexpected dimensions. JPG export uses macOS `sips` first and ImageMagick second.

## Known limits

- Source semantics still require human or model judgment.
- Browser geometry checks text containment, not aesthetic balance.
- Fixed profiles intentionally reject content that exceeds their capacity.
- No pixel-baseline comparison is enforced because browser and font versions can change antialiasing; structural and geometric checks are the stable baseline.
