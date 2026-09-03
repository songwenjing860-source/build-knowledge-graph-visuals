#!/usr/bin/env python3
"""Verify that dark and light SVGs share text, geometry, and element order."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


IGNORED_ATTRIBUTES = {
    "fill",
    "fill-opacity",
    "opacity",
    "stroke",
    "stroke-opacity",
    "style",
    "filter",
    "flood-color",
    "flood-opacity",
    "stop-color",
    "stop-opacity",
    "data-theme",
}


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def text_content(element: ET.Element) -> str:
    return "".join(element.itertext()).strip()


def visible_elements(element: ET.Element):
    if local_name(element.tag) == "defs":
        return
    yield element
    for child in element:
        yield from visible_elements(child)


def signature(path: Path) -> list[tuple[str, tuple[tuple[str, str], ...], str]]:
    root = ET.parse(path).getroot()
    result = []
    for element in visible_elements(root):
        tag = local_name(element.tag)
        if tag == "style":
            continue
        attributes = tuple(
            sorted((key, value) for key, value in element.attrib.items() if key not in IGNORED_ATTRIBUTES)
        )
        content = text_content(element) if tag == "text" else ""
        result.append((tag, attributes, content))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dark", type=Path)
    parser.add_argument("light", type=Path)
    args = parser.parse_args()

    try:
        dark = signature(args.dark)
        light = signature(args.light)
    except (OSError, ET.ParseError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if len(dark) != len(light):
        print(f"FAIL: element count differs: dark={len(dark)}, light={len(light)}", file=sys.stderr)
        return 1

    mismatches = []
    for index, (dark_item, light_item) in enumerate(zip(dark, light, strict=True)):
        if dark_item != light_item:
            mismatches.append((index, dark_item, light_item))
            if len(mismatches) == 5:
                break

    if mismatches:
        print("FAIL: theme files differ in text or geometry", file=sys.stderr)
        for index, dark_item, light_item in mismatches:
            print(f"  element {index}\n    dark:  {dark_item}\n    light: {light_item}", file=sys.stderr)
        return 1

    text_count = sum(1 for tag, _, _ in dark if tag == "text")
    print(f"PASS: {len(dark)} elements and {text_count} text nodes share the same structure")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
