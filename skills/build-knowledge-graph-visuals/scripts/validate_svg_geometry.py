#!/usr/bin/env python3
"""Validate SVG text containment with Chrome's actual font metrics."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse
from urllib.request import urlopen

from render_svg import find_chrome, stop_process


CHECK_EXPRESSION = r"""
(async () => {
  await document.fonts.ready;
  const svg = document.querySelector('svg');
  const rect = el => {
    const r = el.getBoundingClientRect();
    return {left:r.left, top:r.top, right:r.right, bottom:r.bottom,
            width:r.width, height:r.height};
  };
  const contains = (outer, inner, pad) =>
    inner.left >= outer.left + pad && inner.right <= outer.right - pad &&
    inner.top >= outer.top + pad && inner.bottom <= outer.bottom - pad;
  const describe = el => (el.textContent || '').trim().replace(/\s+/g, ' ');
  const canvas = rect(svg);
  const issues = [];
  let nodeTexts = 0;
  let edgeLabels = 0;

  for (const group of svg.querySelectorAll('[data-role="node"]')) {
    const shape = group.querySelector('rect, circle');
    if (!shape) {
      issues.push({kind:'node-shape-missing', id:group.dataset.nodeId || ''});
      continue;
    }
    const boundary = rect(shape);
    for (const text of group.querySelectorAll('text')) {
      nodeTexts += 1;
      const measured = rect(text);
      if (!contains(boundary, measured, 6)) {
        issues.push({kind:'node-text-overflow', id:group.dataset.nodeId || '',
                     text:describe(text), boundary, measured});
      }
    }
  }

  for (const group of svg.querySelectorAll('[data-role="edge-label"]')) {
    const background = group.querySelector('rect');
    const text = group.querySelector('text');
    edgeLabels += 1;
    if (!background || !text) {
      issues.push({kind:'edge-label-incomplete', index:group.dataset.edgeIndex || ''});
      continue;
    }
    const boundary = rect(background);
    const measured = rect(text);
    if (!contains(boundary, measured, 3)) {
      issues.push({kind:'edge-label-overflow', index:group.dataset.edgeIndex || '',
                   text:describe(text), boundary, measured});
    }
  }

  for (const text of svg.querySelectorAll('text')) {
    const measured = rect(text);
    if (!contains(canvas, measured, 0)) {
      issues.push({kind:'canvas-text-overflow', text:describe(text), measured});
    }
  }

  return {
    ok: issues.length === 0,
    node_count: svg.querySelectorAll('[data-role="node"]').length,
    node_text_count: nodeTexts,
    edge_label_count: edgeLabels,
    issues
  };
})()
"""


def recv_exact(connection: socket.socket, length: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < length:
        chunk = connection.recv(length - len(chunks))
        if not chunk:
            raise ConnectionError("WebSocket closed unexpectedly")
        chunks.extend(chunk)
    return bytes(chunks)


class WebSocket:
    def __init__(self, url: str, timeout: int) -> None:
        parsed = urlparse(url)
        self.connection = socket.create_connection((parsed.hostname, parsed.port), timeout=timeout)
        self.connection.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        request = (
            f"GET {path} HTTP/1.1\r\nHost: {parsed.hostname}:{parsed.port}\r\n"
            f"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\nOrigin: http://localhost\r\n\r\n"
        )
        self.connection.sendall(request.encode("ascii"))
        response = bytearray()
        while b"\r\n\r\n" not in response:
            response.extend(self.connection.recv(4096))
        if not response.startswith(b"HTTP/1.1 101"):
            raise ConnectionError(response.decode("utf-8", errors="replace"))
        expected = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
        ).decode("ascii")
        if expected.lower() not in response.decode("ascii", errors="ignore").lower():
            raise ConnectionError("invalid WebSocket accept response")

    def send_json(self, value: dict[str, object]) -> None:
        payload = json.dumps(value, separators=(",", ":")).encode("utf-8")
        mask = os.urandom(4)
        length = len(payload)
        if length < 126:
            header = bytes((0x81, 0x80 | length))
        elif length < 65536:
            header = bytes((0x81, 0x80 | 126)) + struct.pack(">H", length)
        else:
            header = bytes((0x81, 0x80 | 127)) + struct.pack(">Q", length)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.connection.sendall(header + mask + masked)

    def receive_json(self) -> dict[str, object]:
        while True:
            first, second = recv_exact(self.connection, 2)
            opcode = first & 0x0F
            length = second & 0x7F
            if length == 126:
                length = struct.unpack(">H", recv_exact(self.connection, 2))[0]
            elif length == 127:
                length = struct.unpack(">Q", recv_exact(self.connection, 8))[0]
            mask = recv_exact(self.connection, 4) if second & 0x80 else None
            payload = recv_exact(self.connection, length)
            if mask:
                payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
            if opcode == 0x8:
                raise ConnectionError("WebSocket closed before returning a result")
            if opcode == 0x9:
                self.connection.sendall(bytes((0x8A, len(payload))) + payload)
                continue
            if opcode == 0x1:
                return json.loads(payload.decode("utf-8"))

    def close(self) -> None:
        self.connection.close()


def wait_for_debugger(profile: Path, timeout: int) -> tuple[int, str]:
    deadline = time.monotonic() + timeout
    port_file = profile / "DevToolsActivePort"
    while time.monotonic() < deadline:
        if port_file.exists():
            lines = port_file.read_text(encoding="utf-8").splitlines()
            if lines:
                return int(lines[0]), lines[1] if len(lines) > 1 else ""
        time.sleep(0.1)
    raise TimeoutError("Chrome DevTools endpoint did not start")


def browser_check(svg_path: Path, timeout: int) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="kg-geometry-") as directory:
        profile = Path(directory) / "profile"
        command = [
            find_chrome(),
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-default-apps",
            "--disable-sync",
            "--metrics-recording-only",
            "--no-first-run",
            "--remote-allow-origins=*",
            "--remote-debugging-port=0",
            f"--user-data-dir={profile}",
            svg_path.as_uri(),
        ]
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        websocket = None
        try:
            port, _ = wait_for_debugger(profile, timeout)
            deadline = time.monotonic() + timeout
            pages = []
            while time.monotonic() < deadline:
                with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2) as response:
                    pages = json.load(response)
                pages = [page for page in pages if page.get("type") == "page"]
                if pages:
                    break
                time.sleep(0.1)
            if not pages:
                raise TimeoutError("Chrome did not create a page target")
            websocket = WebSocket(pages[0]["webSocketDebuggerUrl"], timeout)
            websocket.send_json({
                "id": 1,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": CHECK_EXPRESSION,
                    "awaitPromise": True,
                    "returnByValue": True,
                },
            })
            while True:
                message = websocket.receive_json()
                if message.get("id") != 1:
                    continue
                if "error" in message:
                    raise RuntimeError(json.dumps(message["error"], ensure_ascii=False))
                remote = message["result"]["result"]
                if remote.get("subtype") == "error":
                    raise RuntimeError(remote.get("description", "browser evaluation failed"))
                return remote["value"]
        finally:
            if websocket is not None:
                websocket.close()
            stop_process(process)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("svg", type=Path)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()
    svg = args.svg.resolve()
    if not svg.is_file():
        parser.error(f"SVG not found: {svg}")
    try:
        result = browser_check(svg, args.timeout)
    except (OSError, ValueError, RuntimeError, TimeoutError, ConnectionError,
            socket.timeout, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if not result.get("ok"):
        print("FAIL: browser geometry validation found overflow", file=sys.stderr)
        for issue in result.get("issues", []):
            print(f"  {json.dumps(issue, ensure_ascii=False)}", file=sys.stderr)
        return 1
    print(
        "PASS: browser geometry, "
        f"{result['node_count']} nodes, {result['node_text_count']} node texts, "
        f"{result['edge_label_count']} edge labels"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
