"""Optional QA for generated sites: deterministic design detector + mobile screenshot.

Tools used (both optional, both need Node):
- Impeccable CLI:   npx impeccable detect <dir>        (62 deterministic design/AI-slop rules, no LLM, no API key)
- Playwright CLI:   npm i -g @playwright/cli           (screenshots in a real browser)

Everything here degrades gracefully: if a tool is missing the check is reported as 'skipped'.
"""
from __future__ import annotations

import json
import logging
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DetectResult:
    status: str  # 'clean' | 'findings' | 'error' | 'skipped'
    count: int = 0
    detail: str = ""


def run_detector(site_dir: Path, *, timeout: int = 120) -> DetectResult:
    """Run `impeccable detect --json`. Exit 0 = clean, 2 = findings, 1 = could not scan."""
    npx = shutil.which("npx")
    if not npx:
        return DetectResult("skipped", detail="npx not installed")
    try:
        proc = subprocess.run(
            [npx, "--yes", "impeccable", "detect", "--json", str(site_dir)],
            capture_output=True, text=True, timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        return DetectResult("error", detail=str(e))
    if proc.returncode == 0:
        return DetectResult("clean")
    if proc.returncode == 2:
        count, detail = _summarize(proc.stdout)
        return DetectResult("findings", count=count, detail=detail)
    return DetectResult("error", detail=(proc.stderr or proc.stdout)[:300])


def _summarize(stdout: str) -> tuple[int, str]:
    """Best-effort: the JSON shape belongs to Impeccable, so only count obvious list structures."""
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return 0, stdout[:300]
    items = data if isinstance(data, list) else data.get("findings") or data.get("results") or []
    if isinstance(items, list):
        names = [str(i.get("rule") or i.get("id") or i.get("name") or "") for i in items if isinstance(i, dict)]
        return len(items), ", ".join(sorted({n for n in names if n}))[:300]
    return 0, ""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def mobile_screenshot(site_dir: Path, out_png: Path, *, device: str = "iPhone 15") -> bool:
    """Serve the site locally and screenshot it with playwright-cli. Returns True on success."""
    exe = shutil.which("playwright-cli")
    if not exe:
        return False
    port = _free_port()
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", str(site_dir)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    session = f"-s=qa{port}"
    try:
        time.sleep(0.8)
        out_png.parent.mkdir(parents=True, exist_ok=True)
        steps = [
            [exe, session, "open", f"http://127.0.0.1:{port}/", f"--device={device}"],
            [exe, session, "screenshot", f"--filename={out_png}"],
        ]
        for cmd in steps:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=90)
        return out_png.exists()
    except (subprocess.SubprocessError, OSError) as e:
        log.warning("screenshot failed: %s", e)
        return False
    finally:
        subprocess.run([exe, session, "close"], capture_output=True, text=True)
        server.terminate()


def summarize_for_owner(result: DetectResult) -> str:
    if result.status == "clean":
        return "Design check: clean"
    if result.status == "findings":
        extra = f" ({result.detail})" if result.detail else ""
        return f"Design check: {result.count} finding(s){extra}"
    if result.status == "skipped":
        return f"Design check: skipped ({result.detail})"
    return f"Design check: could not run ({result.detail})"
