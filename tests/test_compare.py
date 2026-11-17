"""Unit tests for the site-design A/B comparison harness, scoring, and verdict rules."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from agency.config import Settings
from agency.db import connect, get_design_scores, init_db, insert_lead, record_design_score
from agency.sitegen.compare import (
    VALID_CRITERIA,
    compare_lead,
    compute_ab_report,
    export_report_to_csv,
    get_or_create_mapping,
    render_compare_html,
    resolve_site_label,
)


@pytest.fixture
def test_db(tmp_path: Path):
    db_file = tmp_path / "test_ab.db"
    conn = connect(db_file)
    init_db(conn)
    return conn


@pytest.fixture
def mock_lead_id(test_db):
    lid = insert_lead(
        test_db,
        source="manual",
        source_id="mock_phone_1",
        name="Austin Auto Repair",
        category="auto repair",
        phone_e164="+15125553344",
        city="Austin",
        state="TX",
        lat=30.25,
        lng=-97.75,
    )
    return lid


def test_random_mapping_and_resolution(tmp_path: Path):
    variants_dir = tmp_path / "variants"
    mapping1 = get_or_create_mapping(variants_dir)

    assert set(mapping1.keys()) >= {"site_1", "site_2"}
    assert {mapping1["site_1"], mapping1["site_2"]} == {"a", "b"}

    # Repeated call returns same mapping
    mapping2 = get_or_create_mapping(variants_dir)
    assert mapping1["site_1"] == mapping2["site_1"]
    assert mapping1["site_2"] == mapping2["site_2"]

    # Resolution
    assert resolve_site_label("Site 1", mapping1) == mapping1["site_1"]
    assert resolve_site_label("site_1", mapping1) == mapping1["site_1"]
    assert resolve_site_label("1", mapping1) == mapping1["site_1"]
    assert resolve_site_label("Site 2", mapping1) == mapping1["site_2"]
    assert resolve_site_label("2", mapping1) == mapping1["site_2"]
    assert resolve_site_label("a", mapping1) == "a"
    assert resolve_site_label("b", mapping1) == "b"

    with pytest.raises(ValueError):
        resolve_site_label("Site 3", mapping1)


def test_render_compare_html(tmp_path: Path):
    mapping = {"site_1": "b", "site_2": "a"}
    html = render_compare_html(
        slug="test-cafe-1",
        business_name="Test Cafe",
        mapping=mapping,
        qa_1={"status": "clean", "count": 0},
        qa_2={"status": "findings", "count": 2},
    )

    assert "Test Cafe" in html
    assert "Site 1" in html
    assert "Site 2" in html
    assert "site-1/index.html" in html
    assert "site-2/index.html" in html
    assert "variants/b" not in html
    assert "variants/a" not in html
    assert "first_impression" in html
    assert "Desktop View" in html
    assert "Mobile Phone (375px)" in html


def test_design_scores_crud(test_db, mock_lead_id):
    sid = record_design_score(test_db, mock_lead_id, "a", "first_impression", 4, reviewer="alice")
    assert sid is not None

    scores = get_design_scores(test_db, mock_lead_id)
    assert len(scores) == 1
    assert scores[0]["variant"] == "a"
    assert scores[0]["criterion"] == "first_impression"
    assert scores[0]["score"] == 4
    assert scores[0]["reviewer"] == "alice"

    # Out of range scores
    with pytest.raises(ValueError):
        record_design_score(test_db, mock_lead_id, "a", "first_impression", 0)

    with pytest.raises(ValueError):
        record_design_score(test_db, mock_lead_id, "a", "first_impression", 6)


def test_compare_lead_execution(test_db, mock_lead_id, tmp_path: Path):
    out_dir = tmp_path / "output"
    slug = f"austin-auto-repair-{mock_lead_id}"
    var_a = out_dir / slug / "variants" / "a"
    var_b = out_dir / slug / "variants" / "b"

    # Missing variants raise FileNotFoundError
    settings = Settings(output_dir=out_dir)
    with pytest.raises(FileNotFoundError):
        compare_lead(test_db, mock_lead_id, settings=settings, capture_screenshots=False)

    # Create dummy sites
    var_a.mkdir(parents=True)
    var_b.mkdir(parents=True)
    (var_a / "index.html").write_text("<html><body>Site A</body></html>", encoding="utf-8")
    (var_b / "index.html").write_text("<html><body>Site B</body></html>", encoding="utf-8")

    res = compare_lead(test_db, mock_lead_id, settings=settings, capture_screenshots=False)
    assert res["lead_id"] == mock_lead_id
    assert res["compare_html"].exists()
    assert res["mapping_path"].exists()
    assert (out_dir / slug / "site-1" / "index.html").exists()
    assert (out_dir / slug / "site-2" / "index.html").exists()


def test_verdict_rule_path_a_wins(test_db, tmp_path: Path):
    out_dir = tmp_path / "output"

    # Simulate 8 leads where Path A scores higher on 6 leads
    for i in range(1, 9):
        lid = insert_lead(
            test_db,
            source="manual",
            source_id=f"test_lead_{i}",
            name=f"Lead {i}",
            category="trades",
            phone_e164=f"+1512555000{i}",
            lat=30.0,
            lng=-97.0,
        )
        # Lead 1 to 6: A wins
        # Lead 7 to 8: B wins
        score_a = 5 if i <= 6 else 3
        score_b = 3 if i <= 6 else 5

        for crit in VALID_CRITERIA:
            record_design_score(test_db, lid, "a", crit, score_a)
            record_design_score(test_db, lid, "b", crit, score_b)

        # Mock build logs
        slug_var = out_dir / f"lead-{i}-{lid}" / "variants"
        (slug_var / "a").mkdir(parents=True, exist_ok=True)
        (slug_var / "b").mkdir(parents=True, exist_ok=True)
        (slug_var / "a" / "build-log.json").write_text(json.dumps({
            "duration_seconds": 120, "iterations": 1, "first_try_qa_pass": True
        }))
        (slug_var / "b" / "build-log.json").write_text(json.dumps({
            "duration_seconds": 140, "iterations": 1, "first_try_qa_pass": True
        }))

    report = compute_ab_report(test_db, output_dir=out_dir)
    assert report["a_wins"] == 6
    assert report["b_wins"] == 2
    assert report["verdict"] == "Path A (impeccable) wins"


def test_verdict_rule_worse_qa_results_in_hybrid(test_db, tmp_path: Path):
    out_dir = tmp_path / "output"

    # Simulate 8 leads where Path A has 6 wins, BUT worse QA pass rate
    for i in range(1, 9):
        lid = insert_lead(
            test_db,
            source="manual",
            source_id=f"test_lead_qa_{i}",
            name=f"Lead QA {i}",
            category="trades",
            phone_e164=f"+1512555110{i}",
            lat=30.0,
            lng=-97.0,
        )
        score_a = 5 if i <= 6 else 3
        score_b = 3 if i <= 6 else 5

        for crit in VALID_CRITERIA:
            record_design_score(test_db, lid, "a", crit, score_a)
            record_design_score(test_db, lid, "b", crit, score_b)

        slug_var = out_dir / f"lead-qa-{i}-{lid}" / "variants"
        (slug_var / "a").mkdir(parents=True, exist_ok=True)
        (slug_var / "b").mkdir(parents=True, exist_ok=True)
        # Path A failed first try QA on most runs
        (slug_var / "a" / "build-log.json").write_text(json.dumps({
            "duration_seconds": 120, "iterations": 2, "first_try_qa_pass": False
        }))
        # Path B passed first try QA
        (slug_var / "b" / "build-log.json").write_text(json.dumps({
            "duration_seconds": 140, "iterations": 1, "first_try_qa_pass": True
        }))

    report = compute_ab_report(test_db, output_dir=out_dir)
    assert report["a_wins"] == 6
    # QA pass rate of A (0.0) is worse than B (1.0) -> must fallback to hybrid verdict
    assert report["verdict"] == "no clear winner, consider hybrid"


def test_verdict_rule_tie_results_in_hybrid(test_db, tmp_path: Path):
    out_dir = tmp_path / "output"

    for i in range(1, 9):
        lid = insert_lead(
            test_db,
            source="manual",
            source_id=f"test_lead_tie_{i}",
            name=f"Lead Tie {i}",
            category="trades",
            phone_e164=f"+1512555220{i}",
            lat=30.0,
            lng=-97.0,
        )
        # 4 wins for A, 4 wins for B
        score_a = 5 if i <= 4 else 3
        score_b = 3 if i <= 4 else 5

        for crit in VALID_CRITERIA:
            record_design_score(test_db, lid, "a", crit, score_a)
            record_design_score(test_db, lid, "b", crit, score_b)

    report = compute_ab_report(test_db, output_dir=out_dir)
    assert report["a_wins"] == 4
    assert report["b_wins"] == 4
    assert report["verdict"] == "no clear winner, consider hybrid"


def test_export_report_to_csv(test_db, tmp_path: Path):
    lid = insert_lead(
        test_db,
        source="manual",
        source_id="test_lead_csv",
        name="CSV Test Cafe",
        category="cafe",
        phone_e164="+15125553300",
        lat=30.0,
        lng=-97.0,
    )
    for crit in VALID_CRITERIA:
        record_design_score(test_db, lid, "a", crit, 4)
        record_design_score(test_db, lid, "b", crit, 3)

    report = compute_ab_report(test_db, output_dir=tmp_path / "output")
    csv_file = tmp_path / "report.csv"
    count = export_report_to_csv(report, csv_file)

    assert count == 1
    assert csv_file.exists()
    content = csv_file.read_text(encoding="utf-8")
    assert "CSV Test Cafe" in content
    assert "first_impression_a" in content


def test_cli_ab_commands(test_db, mock_lead_id, tmp_path: Path, monkeypatch, capsys):
    from agency import cli

    out_dir = tmp_path / "output"
    slug = f"austin-auto-repair-{mock_lead_id}"
    var_a = out_dir / slug / "variants" / "a"
    var_b = out_dir / slug / "variants" / "b"
    var_a.mkdir(parents=True)
    var_b.mkdir(parents=True)
    (var_a / "index.html").write_text("<html><body>Site A</body></html>", encoding="utf-8")
    (var_b / "index.html").write_text("<html><body>Site B</body></html>", encoding="utf-8")

    settings = Settings(output_dir=out_dir)
    monkeypatch.setattr(cli, "_conn", lambda: test_db)
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    # 1. agency compare
    cli.main(["compare", str(mock_lead_id)])
    out_cmp = capsys.readouterr().out
    assert "A/B Comparison generated for 'Austin Auto Repair'" in out_cmp
    assert "compare.html" in out_cmp

    # 2. agency score
    cli.main(["score", str(mock_lead_id), "Site 1", "first_impression", "4"])
    out_sc = capsys.readouterr().out
    assert "Recorded score" in out_sc
    assert "Candidate: Site 1" in out_sc

    # 3. agency reveal
    cli.main(["reveal", str(mock_lead_id)])
    out_rev = capsys.readouterr().out
    assert "Blind Mapping Revealed" in out_rev
    assert "Site 1 -> Path" in out_rev

    # 4. agency compare-report
    csv_dest = str(tmp_path / "ab_report.csv")
    cli.main(["compare-report", "--output", csv_dest])
    out_rep = capsys.readouterr().out
    assert "A/B DESIGN PATH COMPARISON REPORT" in out_rep
    assert Path(csv_dest).exists()
