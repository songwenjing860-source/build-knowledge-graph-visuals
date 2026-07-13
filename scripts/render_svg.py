#!/usr/bin/env python3
"""Render an SVG to a deterministic high-resolution PNG and optional JPG."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET


def parse_dimension(value: str | None) -> int | None:
    if not value:
        return None
    cleaned = value.strip().lower()
    for suffix in ("px", "pt"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
    try:
        return round(float(cleaned))
    except ValueError:
        return None


def svg_size(path: Path) -> tuple[int, int]:
    root = ET.parse(path).getroot()
    width = parse_dimension(root.get("width"))
    height = parse_dimension(root.get("height"))
    if width and height:
        return width, height

    view_box = root.get("viewBox")
    if view_box:
        values = view_box.replace(",", " ").split()
        if len(values) == 4:
            return round(float(values[2])), round(float(values[3]))
    raise ValueError("SVG must define numeric width/height or a four-value viewBox")


def find_chrome() -> str:
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
    ]
    for candidate in candidates:
        if candidate.startswith("/") and Path(candidate).exists():
            return candidate
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise FileNotFoundError("Chrome/Chromium was not found; install one to render SVG files")


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Output is not a valid PNG: {path}")
    return struct.unpack(">II", header[16:24])


def stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=3)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def render(svg: Path, png: Path, scale: int, timeout: int) -> tuple[int, int]:
    width, height = svg_size(svg)
    expected = (width * scale, height * scale)
    chrome = find_chrome()
    png.parent.mkdir(parents=True, exist_ok=True)
    if png.exists():
        png.unlink()

    with tempfile.TemporaryDirectory(prefix="kg-svg-render-") as profile:
        command = [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-default-apps",
            "--disable-sync",
            "--hide-scrollbars",
            "--metrics-recording-only",
            "--no-first-run",
            f"--force-device-scale-factor={scale}",
            f"--window-size={width},{height}",
            f"--screenshot={png}",
            f"--user-data-dir={profile}",
            svg.resolve().as_uri(),
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
                if png.exists() and png.stat().st_size > 100:
                    current_size = png.stat().st_size
                    if current_size == last_size:
                        stable_since = stable_since or time.monotonic()
                        if time.monotonic() - stable_since >= 0.6:
                            break
                    else:
                        last_size = current_size
                        stable_since = None
                if process.poll() is not None and not png.exists():
                    raise RuntimeError(f"Chrome exited with code {process.returncode} before rendering")
                time.sleep(0.2)
            else:
                raise TimeoutError(f"Rendering did not finish within {timeout} seconds")
        finally:
            stop_process(process)

    actual = png_size(png)
    if actual != expected:
        raise ValueError(f"Unexpected PNG size {actual}; expected {expected}")
    return actual


def make_jpg(png: Path, quality: int) -> Path:
    jpg = png.with_suffix(".jpg")
    sips = shutil.which("sips")
    if sips:
        subprocess.run(
            [sips, "-s", "format", "jpeg", "-s", "formatOptions", str(quality), str(png), "--out", str(jpg)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        return jpg

    magick = shutil.which("magick")
    if magick:
        subprocess.run([magick, str(png), "-quality", str(quality), str(jpg)], check=True)
        return jpg

    raise FileNotFoundError("JPG export needs macOS sips or ImageMagick; PNG was created successfully")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("svg", type=Path, help="Input SVG file")
    parser.add_argument("--out", type=Path, help="Output PNG path")
    parser.add_argument("--scale", type=int, default=2, choices=range(1, 5))
    parser.add_argument("--jpg", action="store_true", help="Also export a same-name JPG")
    parser.add_argument("--quality", type=int, default=96, choices=range(80, 101))
    parser.add_argument("--timeout", type=int, default=45)
    args = parser.parse_args()

    svg = args.svg.resolve()
    if not svg.is_file():
        parser.error(f"SVG not found: {svg}")
    png = (args.out or svg.with_suffix(".png")).resolve()

    try:
        width, height = render(svg, png, args.scale, args.timeout)
        print(f"PNG: {png} ({width}x{height})")
        if args.jpg:
            print(f"JPG: {make_jpg(png, args.quality)}")
    except Exception as exc:  # noqa: BLE001 - CLI should return a concise failure.
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
