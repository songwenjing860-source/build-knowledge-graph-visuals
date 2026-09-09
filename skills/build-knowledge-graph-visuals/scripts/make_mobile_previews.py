#!/usr/bin/env python3
"""Create a true-width mobile preview and top/middle/bottom review crops from SVG."""

from __future__ import annotations

import argparse
import html
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from render_svg import find_chrome, png_size, stop_process, svg_size


def screenshot(document: Path, output: Path, width: int, height: int,
               profile: Path, timeout: int) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    command = [
        find_chrome(),
        "--headless=new",
        "--disable-gpu",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-default-apps",
        "--disable-sync",
        "--hide-scrollbars",
        "--metrics-recording-only",
        "--no-first-run",
        "--force-device-scale-factor=1",
        f"--window-size={width},{height}",
        f"--screenshot={output}",
        f"--user-data-dir={profile}",
        document.as_uri(),
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    deadline = time.monotonic() + timeout
    last_size = -1
    stable_since = None
    try:
        while time.monotonic() < deadline:
            if output.exists() and output.stat().st_size > 100:
                current_size = output.stat().st_size
                if current_size == last_size:
                    stable_since = stable_since or time.monotonic()
                    if time.monotonic() - stable_since >= 0.6:
                        break
                else:
                    last_size = current_size
                    stable_since = None
            if process.poll() is not None and not output.exists():
                raise RuntimeError(f"Chrome exited with code {process.returncode}")
            time.sleep(0.2)
        else:
            raise TimeoutError(f"preview did not finish within {timeout} seconds")
    finally:
        stop_process(process)
    actual = png_size(output)
    if actual != (width, height):
        raise ValueError(f"unexpected preview size {actual}; expected {(width, height)}")


def html_document(svg: Path, width: int, height: int, offset: int = 0) -> str:
    source = html.escape(svg.resolve().as_uri(), quote=True)
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
html,body{{margin:0;width:{width}px;height:{height}px;overflow:hidden;background:#fff}}
.stage{{position:relative;width:{width}px;height:{height}px;overflow:hidden}}
img{{position:absolute;left:0;top:-{offset}px;width:{width}px;height:auto;display:block}}
</style></head><body><div class="stage"><img src="{source}"></div></body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("svg", type=Path)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--basename")
    parser.add_argument("--target-width", type=int, default=390)
    parser.add_argument("--region-height", type=int, default=420)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    svg = args.svg.resolve()
    if not svg.is_file():
        parser.error(f"SVG not found: {svg}")
    if args.target_width < 240 or args.region_height < 160:
        parser.error("target width must be >= 240 and region height must be >= 160")

    try:
        source_width, source_height = svg_size(svg)
        full_height = round(source_height * args.target_width / source_width)
        region_height = min(args.region_height, full_height)
        offsets = {
            "top": 0,
            "middle": max(0, (full_height - region_height) // 2),
            "bottom": max(0, full_height - region_height),
        }
        out_dir = (args.out_dir or svg.parent).resolve()
        basename = args.basename or svg.stem
        out_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="kg-mobile-preview-") as directory:
            root = Path(directory)
            full_html = root / "full.html"
            full_html.write_text(html_document(svg, args.target_width, full_height), encoding="utf-8")
            full_output = out_dir / f"{basename}-mobile-full.png"
            screenshot(full_html, full_output, args.target_width, full_height,
                       root / "profile-full", args.timeout)
            print(f"PREVIEW: {full_output} ({args.target_width}x{full_height})")

            for name, offset in offsets.items():
                region_html = root / f"{name}.html"
                region_html.write_text(
                    html_document(svg, args.target_width, region_height, offset),
                    encoding="utf-8",
                )
                output = out_dir / f"{basename}-mobile-{name}.png"
                screenshot(region_html, output, args.target_width, region_height,
                           root / f"profile-{name}", args.timeout)
                print(f"CROP: {output} ({args.target_width}x{region_height}, y={offset})")
    except (OSError, RuntimeError, TimeoutError, ValueError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
