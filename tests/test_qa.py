import json
import subprocess
from pathlib import Path

from agency.sitegen import qa


class FakeProc:
    def __init__(self, code, out="", err=""):
        self.returncode, self.stdout, self.stderr = code, out, err


def test_detector_clean(monkeypatch):
    monkeypatch.setattr(qa.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(qa.subprocess, "run", lambda *a, **k: FakeProc(0))
    r = qa.run_detector(Path("x"))
    assert r.status == "clean" and "clean" in qa.summarize_for_owner(r)


def test_detector_findings(monkeypatch):
    monkeypatch.setattr(qa.shutil, "which", lambda name: "/usr/bin/" + name)
    out = json.dumps([{"rule": "small-touch-target"}, {"rule": "overused-font"}])
    monkeypatch.setattr(qa.subprocess, "run", lambda *a, **k: FakeProc(2, out))
    r = qa.run_detector(Path("x"))
    assert r.status == "findings" and r.count == 2 and "overused-font" in r.detail


def test_detector_error_and_skipped(monkeypatch):
    monkeypatch.setattr(qa.shutil, "which", lambda name: None)
    assert qa.run_detector(Path("x")).status == "skipped"
    monkeypatch.setattr(qa.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(qa.subprocess, "run", lambda *a, **k: FakeProc(1, "", "boom"))
    assert qa.run_detector(Path("x")).status == "error"


def test_detector_timeout(monkeypatch):
    monkeypatch.setattr(qa.shutil, "which", lambda name: "/usr/bin/" + name)

    def boom(*a, **k):
        raise subprocess.TimeoutExpired("npx", 1)

    monkeypatch.setattr(qa.subprocess, "run", boom)
    assert qa.run_detector(Path("x")).status == "error"


def test_screenshot_skipped_without_playwright(monkeypatch, tmp_path):
    monkeypatch.setattr(qa.shutil, "which", lambda name: None)
    assert qa.mobile_screenshot(tmp_path, tmp_path / "a.png") is False
