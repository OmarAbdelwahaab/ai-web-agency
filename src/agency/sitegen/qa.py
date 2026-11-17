"""QA for generated sites: fact fidelity, filler phrases, horizontal overflow, missing photos, and design detector.

Tools used (all optional, degrade gracefully):
- Impeccable CLI:   npx impeccable detect <dir>        (deterministic design/AI-slop rules)
- Playwright CLI:   playwright-cli screenshot           (screenshots in real browser)
"""
from __future__ import annotations

import html as html_lib
import json
import logging
import re
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DetectResult:
    status: str  # 'clean' | 'findings' | 'error' | 'skipped'
    count: int = 0
    detail: str = ""


@dataclass(frozen=True)
class QAGateFinding:
    category: str  # 'fact_fidelity' | 'filler' | 'overflow' | 'missing_photos' | 'design' | 'system'
    severity: str  # 'error' | 'warning'
    message: str


@dataclass(frozen=True)
class QAGateResult:
    passed: bool
    status: str  # 'clean' | 'findings' | 'error' | 'skipped'
    count: int = 0
    findings: list[QAGateFinding] = field(default_factory=list)
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


def _get_page_text(html: str) -> str:
    """Extract visible text from HTML content with scripts, styles, and tags stripped."""
    no_scripts = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    no_tags = re.sub(r"<[^>]+>", " ", no_scripts)
    text = html_lib.unescape(no_tags)
    return " ".join(text.split())


def _load_facts(site_dir: Path, facts_input: dict[str, Any] | Path | str | None) -> dict[str, Any] | None:
    """Retrieve facts dictionary from parameter or adjacent facts.json file."""
    if isinstance(facts_input, dict):
        return facts_input
    if isinstance(facts_input, (str, Path)):
        p = Path(facts_input)
        if p.exists() and p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    candidates = [
        site_dir / "facts.json",
        site_dir.parent / "facts.json",
        site_dir.parent.parent / "facts.json",
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            try:
                return json.loads(c.read_text(encoding="utf-8"))
            except Exception:
                pass
    return None


def check_fact_fidelity(html: str, facts: dict[str, Any]) -> list[QAGateFinding]:
    """Validate that verified phone, tel: CTA, address, and hours from facts.json appear correctly on the page."""
    findings: list[QAGateFinding] = []
    page_text = _get_page_text(html)

    # 1. Phone number display
    phone_clean = facts.get("phone", "")
    phone_e164 = facts.get("phone_e164", "")
    digits = re.sub(r"\D", "", phone_e164 or phone_clean or "")[-10:]

    if digits:
        text_digits = re.sub(r"\D", "", page_text)
        has_phone = (
            (phone_clean and phone_clean in page_text)
            or (phone_e164 and phone_e164 in page_text)
            or (digits in text_digits)
        )
        if not has_phone:
            findings.append(QAGateFinding(
                category="fact_fidelity",
                severity="error",
                message=f"Phone number '{phone_clean or phone_e164}' missing from page content",
            ))

    # 2. tel: click-to-call link
    tel_matches = re.findall(r'href\s*=\s*["\']tel:([^"\']+)["\']', html, re.IGNORECASE)
    if not tel_matches:
        findings.append(QAGateFinding(
            category="fact_fidelity",
            severity="error",
            message="Click-to-call 'tel:' link is missing from page",
        ))
    elif digits:
        match_digits = [re.sub(r"\D", "", m)[-10:] for m in tel_matches]
        if not any(digits == md for md in match_digits if md):
            findings.append(QAGateFinding(
                category="fact_fidelity",
                severity="error",
                message=f"'tel:' link points to '{tel_matches[0]}', expected '{phone_e164 or phone_clean}'",
            ))

    # 3. Cleaned address
    address = facts.get("address")
    if address and address.strip():
        # Check normalized address or street portion
        addr_clean = address.strip()
        street_part = addr_clean.split(",")[0].strip()
        addr_norm = " ".join(re.sub(r"[,\.]", " ", addr_clean).split()).lower()
        page_norm = " ".join(re.sub(r"[,\.]", " ", page_text).split()).lower()

        if addr_norm not in page_norm and street_part.lower() not in page_norm:
            findings.append(QAGateFinding(
                category="fact_fidelity",
                severity="error",
                message=f"Address '{addr_clean}' missing from page content",
            ))

    # 4. Opening hours strings
    hours = facts.get("hours") or []
    if hours:
        for h in hours:
            day = h.get("day", "").strip()
            time_str = h.get("text", "").strip()
            if not day or not time_str:
                continue

            day_norm = day.replace("–", "-").replace("—", "-").lower()
            time_norm = time_str.replace("–", "-").replace("—", "-").lower()
            page_h_norm = page_text.replace("–", "-").replace("—", "-").lower()

            # Check if day and time appear on the page
            day_present = (day_norm in page_h_norm) or (day_norm[:3] in page_h_norm)
            time_present = (time_norm in page_h_norm) or (time_str in page_text)
            if not (day_present and time_present):
                findings.append(QAGateFinding(
                    category="fact_fidelity",
                    severity="error",
                    message=f"Opening hours '{day}: {time_str}' missing from page",
                ))

    return findings


FILLER_RULES = [
    (r"\blorem\s+ipsum\b", "Lorem Ipsum placeholder detected"),
    (r"\[insert\b", "Unfilled bracket template '[insert...]' detected"),
    (r"\binsert\s+(?:your|name|phone|address|here|photo|image|description|text)\b", "'insert your...' template placeholder detected"),
    (r"\[business\s*name\]", "[business name] placeholder detected"),
    (r"\[phone\b", "[phone...] placeholder detected"),
    (r"\{phone\}", "{phone} template variable detected"),
    (r"\{address\}", "{address} template variable detected"),
    (r"\byour\s+business\s+here\b", "'your business here' placeholder detected"),
    (r"\bplaceholder\b", "'placeholder' text detected"),
    (r"\btodo\b", "'TODO' placeholder detected"),
    (r"\btbd\b", "'TBD' placeholder detected"),
    (r"\bdelve\s+into\b", "AI-slop phrase 'delve into' detected"),
    (r"\ba\s+testament\s+to\b", "AI-slop phrase 'a testament to' detected"),
    (r"\btapestry\s+of\b", "AI-slop phrase 'tapestry of' detected"),
    (r"\belevate\s+your\s+experience\b", "AI-slop phrase 'elevate your experience' detected"),
    (r"\bbeacon\s+of\s+excellence\b", "AI-slop phrase 'beacon of excellence' detected"),
    (r"\bpremier\s+destination\b", "AI-slop phrase 'premier destination' detected"),
    (r"\bnestled\s+in\s+the\s+heart\s+of\b", "AI-slop phrase 'nestled in the heart of' detected"),
]


def check_filler_phrases(html: str) -> list[QAGateFinding]:
    """Detect forbidden filler phrases, template placeholders, and generic AI slop."""
    findings: list[QAGateFinding] = []
    page_text = _get_page_text(html)

    for pattern, desc in FILLER_RULES:
        if re.search(pattern, page_text, re.IGNORECASE) or re.search(pattern, html, re.IGNORECASE):
            findings.append(QAGateFinding(
                category="filler",
                severity="error",
                message=desc,
            ))

    return findings


def check_horizontal_overflow(html: str, site_dir: Path | None = None) -> list[QAGateFinding]:
    """Check for mobile 375px horizontal overflow via viewport meta tags and fixed pixel widths."""
    findings: list[QAGateFinding] = []

    # 1. Viewport meta tag
    has_viewport = bool(
        re.search(r'<meta[^>]+name=["\']viewport["\'][^>]+content=["\'][^"\']*width=device-width', html, re.IGNORECASE)
        or re.search(r'<meta[^>]+content=["\'][^"\']*width=device-width[^"\']+[name=["\']viewport["\']', html, re.IGNORECASE)
    )
    if not has_viewport:
        findings.append(QAGateFinding(
            category="overflow",
            severity="error",
            message="Missing mobile viewport meta tag (<meta name='viewport' content='width=device-width, initial-scale=1.0'>)",
        ))

    # 2. Fixed pixel widths > 375px not guarded by responsive desktop media queries
    # Remove desktop media queries @media (min-width: ...px >= 376px)
    css_stripped = re.sub(
        r"@media\s*\(\s*min-width\s*:\s*(?:[4-9]\d\d|\d{4,})px\s*\)\s*\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}",
        " ",
        html,
        flags=re.IGNORECASE,
    )

    for match in re.finditer(r"(?<![-a-z0-9])(?:min-width|width)\s*:\s*(\d+)px", css_stripped, re.IGNORECASE):
        px = int(match.group(1))
        if px > 375:
            findings.append(QAGateFinding(
                category="overflow",
                severity="error",
                message=f"Fixed width {px}px exceeds 375px mobile viewport",
            ))
            break

    return findings


def check_photo_usage(html: str, facts: dict[str, Any]) -> list[QAGateFinding]:
    """Ensure rich leads with verified local photo assets feature images on the page."""
    findings: list[QAGateFinding] = []
    richness = float(facts.get("data_richness") or 0.0)
    photos = facts.get("photos") or []

    if richness >= 0.6 and len(photos) > 0:
        img_tags = re.findall(r'<img\b[^>]*>', html, re.IGNORECASE)
        if not img_tags:
            findings.append(QAGateFinding(
                category="missing_photos",
                severity="error",
                message="Rich lead has verified photo assets, but no <img> tags were included on the page",
            ))
            return findings

        img_srcs = re.findall(r'<img\b[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
        referenced = False
        for p in photos:
            p_path = p.get("path", "")
            filename = Path(p_path).name.lower()
            for src in img_srcs:
                if filename in src.lower() or p_path.lower() in src.lower():
                    referenced = True
                    break
            if referenced:
                break

        if not referenced:
            findings.append(QAGateFinding(
                category="missing_photos",
                severity="error",
                message="Rich lead photos from facts.json were not referenced by any <img> tag on the page",
            ))

    return findings


def run_qa_gate(
    site_dir: Path | str,
    facts: dict[str, Any] | Path | str | None = None,
    *,
    run_detector_check: bool = True,
) -> QAGateResult:
    """Run full Phase 4 QA gate: fact fidelity, filler phrases, horizontal overflow, missing photos, and detector."""
    site_path = Path(site_dir)
    index_html = site_path / "index.html" if site_path.is_dir() else site_path
    if not index_html.exists():
        return QAGateResult(
            passed=False,
            status="error",
            count=1,
            findings=[QAGateFinding("system", "error", f"File not found: {index_html}")],
            detail=f"File not found: {index_html}",
        )

    html = index_html.read_text(encoding="utf-8")
    loaded_facts = _load_facts(site_path if site_path.is_dir() else site_path.parent, facts)

    findings: list[QAGateFinding] = []

    # 1. Fact fidelity
    if loaded_facts:
        findings.extend(check_fact_fidelity(html, loaded_facts))

    # 2. Filler phrases
    findings.extend(check_filler_phrases(html))

    # 3. Horizontal overflow
    findings.extend(check_horizontal_overflow(html, site_path if site_path.is_dir() else site_path.parent))

    # 4. Missing photos for rich leads
    if loaded_facts:
        findings.extend(check_photo_usage(html, loaded_facts))

    # 5. Impeccable design detector
    if run_detector_check and (site_path.is_dir() or site_path.parent.is_dir()):
        det_dir = site_path if site_path.is_dir() else site_path.parent
        det_res = run_detector(det_dir)
        if det_res.status == "findings":
            findings.append(QAGateFinding(
                category="design",
                severity="error" if det_res.count > 0 else "warning",
                message=f"Design detector reported {det_res.count} finding(s): {det_res.detail}",
            ))

    err_count = sum(1 for f in findings if f.severity == "error")
    passed = (err_count == 0)
    status = "clean" if passed else "findings"
    detail = "; ".join(f.message for f in findings) if findings else "All QA checks passed cleanly"

    return QAGateResult(
        passed=passed,
        status=status,
        count=len(findings),
        findings=findings,
        detail=detail,
    )


def summarize_gate_result(result: QAGateResult) -> str:
    """Format QA gate result for human owner notification or CLI output."""
    if result.passed:
        return "QA Gate: PASSED (Clean)"
    errs = [f.message for f in result.findings if f.severity == "error"]
    sample = "; ".join(errs[:3])
    if len(errs) > 3:
        sample += f" (+{len(errs) - 3} more)"
    return f"QA Gate: FAILED ({len(errs)} error(s): {sample})"


def summarize_for_owner(result: DetectResult | QAGateResult) -> str:
    """Summarize detector or gate result for display."""
    if isinstance(result, QAGateResult):
        return summarize_gate_result(result)
    if result.status == "clean":
        return "Design check: clean"
    if result.status == "findings":
        extra = f" ({result.detail})" if result.detail else ""
        return f"Design check: {result.count} finding(s){extra}"
    if result.status == "skipped":
        return f"Design check: skipped ({result.detail})"
    return f"Design check: could not run ({result.detail})"
