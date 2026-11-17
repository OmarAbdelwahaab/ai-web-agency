"""A/B comparison harness for site-design paths (Path A: Impeccable vs Path B: Open Design)."""
from __future__ import annotations

import csv
import datetime
import json
import random
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from agency.config import Settings, get_settings
from agency.db import get_design_scores, get_lead
from agency.sitegen import qa
from agency.sitegen.schema import slugify

VALID_CRITERIA = (
    "first_impression",
    "layout_fit",
    "copy_specificity",
    "typography_color",
    "mobile",
    "photo_use",
)


def get_or_create_mapping(variants_dir: Path) -> dict[str, str]:
    """Retrieve or generate blind randomized mapping between Site 1/Site 2 and variants a/b."""
    mapping_file = variants_dir / "mapping.json"
    if mapping_file.exists():
        try:
            data = json.loads(mapping_file.read_text(encoding="utf-8"))
            if "site_1" in data and "site_2" in data:
                return data
        except Exception:
            pass

    # Randomly assign Site 1 and Site 2 to 'a' and 'b'
    order = ["a", "b"]
    random.shuffle(order)
    mapping = {
        "site_1": order[0],
        "site_2": order[1],
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    variants_dir.mkdir(parents=True, exist_ok=True)
    mapping_file.write_text(json.dumps(mapping, indent=2), encoding="utf-8")
    return mapping


def resolve_site_label(label: str, mapping: dict[str, str]) -> str:
    """Resolve user-facing site label (e.g. 'Site 1', '1', 'site_1') to true variant ('a' or 'b')."""
    clean = label.strip().lower().replace("-", "_").replace(" ", "_")
    if clean in ("site_1", "1", "s1"):
        return mapping["site_1"]
    if clean in ("site_2", "2", "s2"):
        return mapping["site_2"]
    if clean in ("a", "variant_a"):
        return "a"
    if clean in ("b", "variant_b"):
        return "b"
    raise ValueError(f"Unknown site label '{label}'. Please use 'Site 1' or 'Site 2'.")


def run_variant_qa(variant_dir: Path) -> dict[str, Any]:
    """Run QA gate on a specific variant directory."""
    index_html = variant_dir / "index.html"
    if not index_html.exists():
        return {
            "status": "missing",
            "count": 0,
            "detail": f"{index_html.name} not found",
            "summary": "Site file missing",
        }

    res = qa.run_qa_gate(variant_dir)
    return {
        "status": res.status,
        "count": res.count,
        "detail": res.detail,
        "summary": qa.summarize_gate_result(res),
    }


def _copy_variant_to_neutral(src_dir: Path, dst_dir: Path) -> None:
    """Copy variant files to neutral site-1/ or site-2/ directory for blind review."""
    dst_dir.mkdir(parents=True, exist_ok=True)
    if not src_dir.exists():
        return
    for item in src_dir.iterdir():
        if item.is_file():
            shutil.copyfile(item, dst_dir / item.name)
        elif item.is_dir() and item.name in ("assets", "images"):
            shutil.copytree(item, dst_dir / item.name, dirs_exist_ok=True)


def render_compare_html(
    slug: str,
    business_name: str,
    mapping: dict[str, str],
    qa_1: dict[str, Any],
    qa_2: dict[str, Any],
) -> str:
    """Generate self-contained side-by-side comparison page with blind Site 1 and Site 2 labels."""
    site_1_file = "site-1/index.html"
    site_2_file = "site-2/index.html"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>A/B Comparison: {business_name}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #0f172a;
      color: #f8fafc;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }}
    header {{
      background: #1e293b;
      padding: 1rem 1.5rem;
      border-bottom: 1px solid #334155;
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 1rem;
    }}
    .title-group h1 {{
      font-size: 1.25rem;
      font-weight: 700;
      color: #fff;
    }}
    .title-group p {{
      font-size: 0.85rem;
      color: #94a3b8;
    }}
    .controls {{
      display: flex;
      gap: 0.75rem;
      align-items: center;
    }}
    .btn {{
      padding: 0.45rem 0.9rem;
      border-radius: 6px;
      font-size: 0.85rem;
      font-weight: 600;
      cursor: pointer;
      border: 1px solid #475569;
      background: #334155;
      color: #f8fafc;
      transition: all 0.2s;
    }}
    .btn.active, .btn:hover {{
      background: #3b82f6;
      border-color: #3b82f6;
    }}
    .rubric {{
      background: #1e293b;
      padding: 0.6rem 1.5rem;
      font-size: 0.8rem;
      color: #cbd5e1;
      border-bottom: 1px solid #334155;
      display: flex;
      gap: 1.5rem;
      flex-wrap: wrap;
    }}
    .rubric strong {{ color: #38bdf8; }}
    .split-container {{
      display: flex;
      flex: 1;
      width: 100%;
      height: calc(100vh - 120px);
      gap: 8px;
      padding: 8px;
      background: #0b1120;
    }}
    .site-pane {{
      flex: 1;
      display: flex;
      flex-direction: column;
      background: #1e293b;
      border-radius: 8px;
      overflow: hidden;
      border: 1px solid #334155;
      transition: width 0.3s ease;
    }}
    .pane-header {{
      background: #1e293b;
      padding: 0.6rem 1rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid #334155;
    }}
    .pane-header h2 {{
      font-size: 1rem;
      font-weight: 600;
      color: #e2e8f0;
    }}
    .badge {{
      font-size: 0.75rem;
      padding: 0.2rem 0.5rem;
      border-radius: 9999px;
      font-weight: 600;
      background: #334155;
      color: #94a3b8;
    }}
    .badge.clean {{ background: #065f46; color: #6ee7b7; }}
    .badge.findings {{ background: #991b1b; color: #fca5a5; }}
    .iframe-wrapper {{
      flex: 1;
      width: 100%;
      height: 100%;
      display: flex;
      justify-content: center;
      background: #000;
      overflow: hidden;
    }}
    iframe {{
      width: 100%;
      height: 100%;
      border: none;
      background: #fff;
      transition: width 0.3s ease;
    }}
    /* Mobile emulation container */
    .mobile-mode .split-container {{
      justify-content: center;
      gap: 24px;
      overflow-x: auto;
    }}
    .mobile-mode .site-pane {{
      flex: 0 0 375px;
      max-width: 375px;
      height: 750px;
      margin: auto;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7);
      border: 3px solid #475569;
    }}
    .mobile-mode iframe {{
      width: 375px;
      height: 100%;
    }}
  </style>
</head>
<body>
  <header>
    <div class="title-group">
      <h1>Blind Comparison: {business_name}</h1>
      <p>Slug: <code>{slug}</code> | Rate both variants on a 1-5 scale per criterion.</p>
    </div>
    <div class="controls">
      <button class="btn active" id="btnDesktop" onclick="setMode('desktop')">Desktop View</button>
      <button class="btn" id="btnMobile" onclick="setMode('mobile')">Mobile Phone (375px)</button>
    </div>
  </header>

  <div class="rubric">
    <div><strong>Scoring Criteria (1-5):</strong></div>
    <div>1. first_impression</div>
    <div>2. layout_fit</div>
    <div>3. copy_specificity</div>
    <div>4. typography_color</div>
    <div>5. mobile</div>
    <div>6. photo_use</div>
  </div>

  <div class="split-container" id="splitContainer">
    <!-- Site 1 -->
    <div class="site-pane">
      <div class="pane-header">
        <h2>Site 1</h2>
        <span class="badge {qa_1.get('status')}">QA: {qa_1.get('status', 'skipped')} ({qa_1.get('count', 0)} findings)</span>
      </div>
      <div class="iframe-wrapper">
        <iframe src="{site_1_file}" title="Site 1"></iframe>
      </div>
    </div>

    <!-- Site 2 -->
    <div class="site-pane">
      <div class="pane-header">
        <h2>Site 2</h2>
        <span class="badge {qa_2.get('status')}">QA: {qa_2.get('status', 'skipped')} ({qa_2.get('count', 0)} findings)</span>
      </div>
      <div class="iframe-wrapper">
        <iframe src="{site_2_file}" title="Site 2"></iframe>
      </div>
    </div>
  </div>

  <script>
    function setMode(mode) {{
      const body = document.body;
      const btnDesktop = document.getElementById('btnDesktop');
      const btnMobile = document.getElementById('btnMobile');
      if (mode === 'mobile') {{
        body.classList.add('mobile-mode');
        btnMobile.classList.add('active');
        btnDesktop.classList.remove('active');
      }} else {{
        body.classList.remove('mobile-mode');
        btnDesktop.classList.add('active');
        btnMobile.classList.remove('active');
      }}
    }}
  </script>
</body>
</html>
"""


def compare_lead(
    conn: sqlite3.Connection,
    lead_id: int,
    settings: Settings | None = None,
    capture_screenshots: bool = True,
) -> dict[str, Any]:
    """Perform comparison of variant a and variant b for a given lead."""
    s = settings or get_settings()
    lead = get_lead(conn, lead_id)
    if lead is None:
        raise ValueError(f"Lead #{lead_id} not found in database")

    slug = slugify(lead["name"], lead["id"])
    slug_dir = s.output_dir / slug
    variants_dir = slug_dir / "variants"
    var_a_dir = variants_dir / "a"
    var_b_dir = variants_dir / "b"

    if not var_a_dir.exists() or not (var_a_dir / "index.html").exists():
        raise FileNotFoundError(
            f"Variant A not found at {var_a_dir / 'index.html'}. Run workflow build-site-a first."
        )
    if not var_b_dir.exists() or not (var_b_dir / "index.html").exists():
        raise FileNotFoundError(
            f"Variant B not found at {var_b_dir / 'index.html'}. Run workflow build-site-b first."
        )

    # 1. Run QA checks
    qa_a = run_variant_qa(var_a_dir)
    qa_b = run_variant_qa(var_b_dir)

    # 2. Get or create blind random mapping
    mapping = get_or_create_mapping(variants_dir)
    qa_1 = qa_a if mapping["site_1"] == "a" else qa_b
    qa_2 = qa_b if mapping["site_2"] == "b" else qa_a

    # 3. Setup neutral directories site-1/ and site-2/ under slug_dir
    site_1_dir = slug_dir / "site-1"
    site_2_dir = slug_dir / "site-2"
    _copy_variant_to_neutral(variants_dir / mapping["site_1"], site_1_dir)
    _copy_variant_to_neutral(variants_dir / mapping["site_2"], site_2_dir)

    # 4. Create output/<slug>/compare.html
    html_content = render_compare_html(
        slug=slug,
        business_name=lead["name"],
        mapping=mapping,
        qa_1=qa_1,
        qa_2=qa_2,
    )
    compare_html_path = slug_dir / "compare.html"
    compare_html_path.write_text(html_content, encoding="utf-8")

    # 5. Export phone screenshots if requested
    shot_a_path = var_a_dir / "mobile.png"
    shot_b_path = var_b_dir / "mobile.png"
    shot_a_ok = False
    shot_b_ok = False
    if capture_screenshots:
        shot_a_ok = qa.mobile_screenshot(var_a_dir, shot_a_path)
        shot_b_ok = qa.mobile_screenshot(var_b_dir, shot_b_path)

    return {
        "lead_id": lead_id,
        "slug": slug,
        "business_name": lead["name"],
        "compare_html": compare_html_path,
        "mapping_path": variants_dir / "mapping.json",
        "variant_a_qa": qa_a,
        "variant_b_qa": qa_b,
        "screenshot_a": shot_a_path if shot_a_ok else None,
        "screenshot_b": shot_b_path if shot_b_ok else None,
    }


def read_build_log(variants_dir: Path, variant: str) -> dict[str, Any] | None:
    """Read build-log.json for a variant if present."""
    log_file = variants_dir / variant / "build-log.json"
    if not log_file.exists():
        return None
    try:
        return json.loads(log_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def compute_ab_report(
    conn: sqlite3.Connection,
    output_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Compute per-variant averages, win counts, build metrics, and final verdict."""
    s = get_settings()
    out_base = Path(output_dir) if output_dir else s.output_dir

    all_scores = get_design_scores(conn)

    # Group scores by (lead_id, variant) -> {criterion: score}
    scores_by_lead_var: dict[int, dict[str, dict[str, int]]] = {}
    for row in all_scores:
        lid = row["lead_id"]
        var = row["variant"].lower()
        crit = row["criterion"].lower()
        scores_by_lead_var.setdefault(lid, {}).setdefault(var, {})[crit] = row["score"]

    lead_results: list[dict[str, Any]] = []
    a_wins = 0
    b_wins = 0
    ties = 0

    criterion_totals: dict[str, dict[str, list[int]]] = {
        c: {"a": [], "b": []} for c in VALID_CRITERIA
    }

    for lid, vars_dict in sorted(scores_by_lead_var.items()):
        lead = get_lead(conn, lid)
        lead_name = lead["name"] if lead else f"Lead #{lid}"
        slug = slugify(lead_name, lid) if lead else f"lead-{lid}"

        scores_a = vars_dict.get("a", {})
        scores_b = vars_dict.get("b", {})

        for c in VALID_CRITERIA:
            if c in scores_a:
                criterion_totals[c]["a"].append(scores_a[c])
            if c in scores_b:
                criterion_totals[c]["b"].append(scores_b[c])

        mean_a = (sum(scores_a.values()) / len(scores_a)) if scores_a else 0.0
        mean_b = (sum(scores_b.values()) / len(scores_b)) if scores_b else 0.0

        if scores_a and scores_b:
            if mean_a > mean_b:
                winner = "a"
                a_wins += 1
            elif mean_b > mean_a:
                winner = "b"
                b_wins += 1
            else:
                winner = "tie"
                ties += 1
        else:
            winner = "incomplete"

        lead_results.append({
            "lead_id": lid,
            "lead_name": lead_name,
            "slug": slug,
            "mean_a": round(mean_a, 2),
            "mean_b": round(mean_b, 2),
            "winner": winner,
            "scores_a": scores_a,
            "scores_b": scores_b,
        })

    # Criterion averages
    criterion_averages: dict[str, dict[str, float]] = {}
    for c in VALID_CRITERIA:
        vals_a = criterion_totals[c]["a"]
        vals_b = criterion_totals[c]["b"]
        criterion_averages[c] = {
            "a": round(sum(vals_a) / len(vals_a), 2) if vals_a else 0.0,
            "b": round(sum(vals_b) / len(vals_b), 2) if vals_b else 0.0,
        }

    # Gather build logs
    build_metrics: dict[str, dict[str, Any]] = {
        "a": {"durations": [], "iterations": [], "first_try_passes": []},
        "b": {"durations": [], "iterations": [], "first_try_passes": []},
    }

    if out_base.exists():
        for slug_folder in out_base.iterdir():
            if slug_folder.is_dir() and (slug_folder / "variants").exists():
                for v in ("a", "b"):
                    blog = read_build_log(slug_folder / "variants", v)
                    if blog:
                        if "duration_seconds" in blog:
                            build_metrics[v]["durations"].append(blog["duration_seconds"])
                        if "iterations" in blog:
                            build_metrics[v]["iterations"].append(blog["iterations"])
                        if "first_try_qa_pass" in blog:
                            build_metrics[v]["first_try_passes"].append(bool(blog["first_try_qa_pass"]))

    def _safe_mean(vals: list[float | int]) -> float:
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    qa_pass_rate_a = (
        round(sum(build_metrics["a"]["first_try_passes"]) / len(build_metrics["a"]["first_try_passes"]), 2)
        if build_metrics["a"]["first_try_passes"]
        else 0.0
    )
    qa_pass_rate_b = (
        round(sum(build_metrics["b"]["first_try_passes"]) / len(build_metrics["b"]["first_try_passes"]), 2)
        if build_metrics["b"]["first_try_passes"]
        else 0.0
    )

    # Verdict Rule:
    # A path wins if it scores higher on at least 5 of 8 leads without a worse QA pass rate;
    # otherwise "no clear winner, consider hybrid".
    verdict: str
    if a_wins >= 5 and qa_pass_rate_a >= qa_pass_rate_b:
        verdict = "Path A (impeccable) wins"
    elif b_wins >= 5 and qa_pass_rate_b >= qa_pass_rate_a:
        verdict = "Path B (open-design) wins"
    else:
        verdict = "no clear winner, consider hybrid"

    return {
        "lead_results": lead_results,
        "a_wins": a_wins,
        "b_wins": b_wins,
        "ties": ties,
        "criterion_averages": criterion_averages,
        "build_stats": {
            "a": {
                "avg_duration_seconds": _safe_mean(build_metrics["a"]["durations"]),
                "avg_iterations": _safe_mean(build_metrics["a"]["iterations"]),
                "qa_first_try_pass_rate": qa_pass_rate_a,
                "total_logged_builds": len(build_metrics["a"]["durations"]),
            },
            "b": {
                "avg_duration_seconds": _safe_mean(build_metrics["b"]["durations"]),
                "avg_iterations": _safe_mean(build_metrics["b"]["iterations"]),
                "qa_first_try_pass_rate": qa_pass_rate_b,
                "total_logged_builds": len(build_metrics["b"]["durations"]),
            },
        },
        "verdict": verdict,
    }


def export_report_to_csv(report: dict[str, Any], output_path: Path | str) -> int:
    """Export detailed lead comparison and criteria breakdown to CSV."""
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for lr in report["lead_results"]:
        row = {
            "lead_id": lr["lead_id"],
            "business_name": lr["lead_name"],
            "slug": lr["slug"],
            "mean_score_a": lr["mean_a"],
            "mean_score_b": lr["mean_b"],
            "winner": lr["winner"],
        }
        for c in VALID_CRITERIA:
            row[f"{c}_a"] = lr["scores_a"].get(c, "")
            row[f"{c}_b"] = lr["scores_b"].get(c, "")
        rows.append(row)

    if not rows:
        return 0

    fieldnames = list(rows[0].keys())
    with out_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)
