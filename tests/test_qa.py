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


# ---------------------------------------------------------------------------
# Phase 4 Rescoped QA Gate Tests
# ---------------------------------------------------------------------------

def test_qa_gate_fact_fidelity_missing_phone(tmp_path: Path):
    facts = {
        "name": "Acme Plumbing",
        "phone": "(512) 555-0100",
        "phone_e164": "+15125550100",
        "address": "100 Main St, Austin, TX",
        "hours": [{"day": "Mon–Fri", "text": "8 AM – 5 PM"}],
    }
    # Page has address and hours and tel link, but missing phone text
    html = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
    <body><h1>Acme Plumbing</h1><p>100 Main St, Austin, TX</p><p>Mon–Fri: 8 AM – 5 PM</p>
    <a href="tel:+15125550100">Call Us</a></body></html>"""
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "index.html").write_text(html, encoding="utf-8")

    res = qa.run_qa_gate(site_dir, facts, run_detector_check=False)
    # The tel text "Call Us" doesn't have phone string, but digits 5125550100 are in href,
    # however phone string is missing from visible text.
    # If phone string is not in visible text:
    phone_errs = [f for f in res.findings if f.category == "fact_fidelity" and "Phone number" in f.message]
    # Now let's test when phone digits are completely absent
    bad_html = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
    <body><h1>Acme Plumbing</h1><p>100 Main St, Austin, TX</p><p>Mon–Fri: 8 AM – 5 PM</p>
    <a href="tel:+18009999999">Call Us</a></body></html>"""
    (site_dir / "index.html").write_text(bad_html, encoding="utf-8")
    res = qa.run_qa_gate(site_dir, facts, run_detector_check=False)
    assert not res.passed
    assert any("Phone number" in f.message for f in res.findings)


def test_qa_gate_fact_fidelity_missing_tel_link(tmp_path: Path):
    facts = {
        "name": "Acme Plumbing",
        "phone": "(512) 555-0100",
        "phone_e164": "+15125550100",
    }
    html = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
    <body><h1>Acme Plumbing</h1><p>Call (512) 555-0100</p></body></html>"""
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "index.html").write_text(html, encoding="utf-8")

    res = qa.run_qa_gate(site_dir, facts, run_detector_check=False)
    assert not res.passed
    assert any("Click-to-call 'tel:' link is missing" in f.message for f in res.findings)


def test_qa_gate_fact_fidelity_missing_address(tmp_path: Path):
    facts = {
        "name": "Acme Plumbing",
        "phone": "(512) 555-0100",
        "phone_e164": "+15125550100",
        "address": "742 Evergreen Terrace, Austin, TX 78704",
    }
    html = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
    <body><h1>Acme Plumbing</h1><p>Call (512) 555-0100</p><a href="tel:+15125550100">Call</a></body></html>"""
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "index.html").write_text(html, encoding="utf-8")

    res = qa.run_qa_gate(site_dir, facts, run_detector_check=False)
    assert not res.passed
    assert any("Address" in f.message for f in res.findings)


def test_qa_gate_fact_fidelity_missing_hours(tmp_path: Path):
    facts = {
        "name": "Acme Bakery",
        "phone": "(512) 555-0100",
        "phone_e164": "+15125550100",
        "hours": [{"day": "Mon–Fri", "text": "6:30 AM – 2:00 PM"}],
    }
    html = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
    <body><h1>Acme Bakery</h1><p>Call (512) 555-0100</p><a href="tel:+15125550100">Call</a></body></html>"""
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "index.html").write_text(html, encoding="utf-8")

    res = qa.run_qa_gate(site_dir, facts, run_detector_check=False)
    assert not res.passed
    assert any("Opening hours" in f.message for f in res.findings)


def test_qa_gate_filler_phrases_detected(tmp_path: Path):
    html = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
    <body>
      <h1>Acme Store</h1>
      <p>Lorem ipsum dolor sit amet. [insert description here]</p>
      <p>A beacon of excellence in the local area.</p>
    </body></html>"""
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "index.html").write_text(html, encoding="utf-8")

    res = qa.run_qa_gate(site_dir, run_detector_check=False)
    assert not res.passed
    filler_messages = [f.message for f in res.findings if f.category == "filler"]
    assert len(filler_messages) >= 3
    assert any("Lorem Ipsum" in m for m in filler_messages)
    assert any("beacon of excellence" in m for m in filler_messages)


def test_qa_gate_horizontal_overflow_375px(tmp_path: Path):
    # 1. Missing viewport meta
    html_no_viewport = """<!DOCTYPE html><html><head><title>No Viewport</title></head><body><h1>Hi</h1></body></html>"""
    site_dir = tmp_path / "site1"
    site_dir.mkdir()
    (site_dir / "index.html").write_text(html_no_viewport, encoding="utf-8")
    res1 = qa.run_qa_gate(site_dir, run_detector_check=False)
    assert not res1.passed
    assert any("Missing mobile viewport meta tag" in f.message for f in res1.findings)

    # 2. Fixed width > 375px
    html_fixed_width = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>.container { width: 500px; }</style></head><body><div class="container">Content</div></body></html>"""
    site_dir2 = tmp_path / "site2"
    site_dir2.mkdir()
    (site_dir2 / "index.html").write_text(html_fixed_width, encoding="utf-8")
    res2 = qa.run_qa_gate(site_dir2, run_detector_check=False)
    assert not res2.passed
    assert any("Fixed width 500px exceeds 375px" in f.message for f in res2.findings)


def test_qa_gate_missing_photos_for_rich_lead(tmp_path: Path):
    facts = {
        "name": "Premier Salon",
        "data_richness": 0.85,
        "photos": [{"path": "assets/interior.jpg", "caption": "Salon styling chairs"}],
    }
    # No img tags
    html_no_img = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
    <body><h1>Premier Salon</h1></body></html>"""
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "index.html").write_text(html_no_img, encoding="utf-8")

    res = qa.run_qa_gate(site_dir, facts, run_detector_check=False)
    assert not res.passed
    assert any("verified photo assets, but no <img>" in f.message for f in res.findings)


def test_qa_gate_old_thistle_cafe_bad_output_fails(tmp_path: Path):
    """Old Thistle Cafe uncleaned output: uncleaned address mismatch, missing tel link,
    placeholder copy, missing hours, missing photos, and horizontal overflow.
    Must reliably fail the QA gate across multiple categories.
    """
    thistle_facts = {
        "name": "Thistle Cafe",
        "business_name": "Thistle Cafe",
        "phone": "(512) 555-0199",
        "phone_e164": "+15125550199",
        "address": "221 West 6th Street, Austin, TX 78701",
        "hours": [{"day": "Mon–Fri", "text": "7:00 AM – 3:00 PM"}],
        "data_richness": 0.85,
        "photos": [{"path": "assets/dining.jpg", "caption": "Main dining room"}],
    }

    # Deliberately bad legacy HTML with multiple flaws:
    bad_html = """<!DOCTYPE html>
    <html>
    <head>
      <title>Thistle Cafe</title>
      <style>
        .page-wrap { width: 600px; margin: 0 auto; }
      </style>
    </head>
    <body>
      <div class="page-wrap">
        <h1>Thistle Cafe</h1>
        <p>Welcome! [insert business description here]. We are a beacon of excellence in the culinary world.</p>
        <p>Location: Thistle Cafe, 221 West 6th Street, Austin, TX 78701, United States of America</p>
        <button onclick="alert('call')">Call Us</button>
      </div>
    </body>
    </html>"""

    site_dir = tmp_path / "thistle_bad"
    site_dir.mkdir()
    (site_dir / "index.html").write_text(bad_html, encoding="utf-8")

    res = qa.run_qa_gate(site_dir, thistle_facts, run_detector_check=False)
    assert not res.passed
    assert res.status == "findings"
    assert res.count >= 4

    categories = {f.category for f in res.findings}
    assert "fact_fidelity" in categories  # missing tel: link, missing hours
    assert "filler" in categories         # [insert...], beacon of excellence
    assert "overflow" in categories       # missing viewport, width 600px
    assert "missing_photos" in categories # rich lead with no <img>


def test_qa_gate_clean_page_passes(tmp_path: Path):
    """Valid site strictly implementing all facts passes the QA gate cleanly."""
    facts = {
        "name": "Thistle Cafe",
        "business_name": "Thistle Cafe",
        "phone": "(512) 555-0199",
        "phone_e164": "+15125550199",
        "address": "221 West 6th Street, Austin, TX 78701",
        "hours": [{"day": "Mon–Fri", "text": "7:00 AM – 3:00 PM"}],
        "data_richness": 0.85,
        "photos": [{"path": "assets/dining.jpg", "caption": "Main dining room"}],
    }

    clean_html = """<!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Thistle Cafe</title>
      <style>
        body { margin: 0; font-family: sans-serif; }
        .hero { padding: 2rem 1rem; }
        .cta-btn { display: inline-block; padding: 12px 24px; min-height: 48px; background: #0f172a; color: #fff; }
      </style>
    </head>
    <body>
      <main class="hero">
        <h1>Thistle Cafe</h1>
        <p>Fresh daily lunch and artisan espresso.</p>
        <p>Visit us at 221 West 6th Street, Austin, TX 78701</p>
        <p>Hours: Mon–Fri: 7:00 AM – 3:00 PM</p>
        <p>Phone: (512) 555-0199</p>
        <a href="tel:+15125550199" class="cta-btn">Call (512) 555-0199</a>
        <figure>
          <img src="assets/dining.jpg" alt="Main dining room">
          <figcaption>Main dining room</figcaption>
        </figure>
      </main>
    </body>
    </html>"""

    site_dir = tmp_path / "thistle_clean"
    site_dir.mkdir()
    (site_dir / "index.html").write_text(clean_html, encoding="utf-8")

    res = qa.run_qa_gate(site_dir, facts, run_detector_check=False)
    assert res.passed
    assert res.status == "clean"
    assert res.count == 0
    assert "PASSED" in qa.summarize_gate_result(res)
