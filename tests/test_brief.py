"""Unit tests for site design brief generation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agency.config import Settings
from agency.db import connect, init_db, insert_lead, save_enrichment
from agency.sitegen.brief import build_brief_dict, generate_brief, render_brief_markdown


@pytest.fixture
def test_db(tmp_path: Path):
    db_file = tmp_path / "test_brief.db"
    conn = connect(db_file)
    init_db(conn)
    return conn


@pytest.fixture
def sample_lead(test_db):
    lid = insert_lead(
        test_db,
        source="places",
        source_id="places/ChIJbrief123",
        name="Oak Hill Bakery",
        category="bakery",
        phone_e164="+15125557788",
        address="5600 Highway 290 W, Austin, TX 78735, United States of America",
        city="Austin",
        state="TX",
        lat=30.2312,
        lng=-97.8541,
        hours_json=json.dumps(["Mo-Fr 06:30-14:00; Sa 07:00-13:00"]),
        rating=4.9,
        rating_count=65,
    )
    save_enrichment(
        test_db,
        lead_id=lid,
        rating=4.9,
        review_count=65,
        top_reviews_json=json.dumps([
            {"author_name": "Clara S.", "text": "Best sourdough in southwest Austin!", "rating": 5.0}
        ]),
        categories_json=json.dumps(["bakery", "cafe"]),
        owner_notes="Family-run for 8 years. Sourdough starter is 25 years old.",
        data_richness=0.85,
    )
    return lid


def test_build_brief_dict(test_db, sample_lead, tmp_path: Path):
    settings = Settings(assets_dir=tmp_path / "assets", output_dir=tmp_path / "output")
    brief = build_brief_dict(test_db, sample_lead, settings=settings)

    assert brief["business_name"] == "Oak Hill Bakery"
    assert brief["slug"] == f"oak-hill-bakery-{sample_lead}"
    assert brief["theme"] == "food"
    assert "United States of America" not in brief["address"]
    assert len(brief["hours"]) == 2
    assert brief["hours"][0]["day"] == "Mon–Fri"
    assert brief["hours"][0]["text"] == "6:30 AM – 2:00 PM"
    assert len(brief["top_reviews"]) == 1
    assert "sourdough" in brief["top_reviews"][0]["text"]
    assert "25 years old" in brief["owner_notes"]
    assert len(brief["design_constraints"]) > 0


def test_render_brief_markdown(test_db, sample_lead, tmp_path: Path):
    settings = Settings(assets_dir=tmp_path / "assets", output_dir=tmp_path / "output")
    brief = build_brief_dict(test_db, sample_lead, settings=settings)
    md = render_brief_markdown(brief)

    assert "# Design Brief: Oak Hill Bakery" in md
    assert "tel:+15125557788" in md
    assert "Mon–Fri" in md
    assert "6:30 AM – 2:00 PM" in md
    assert "Clara S." in md
    assert "25 years old" in md
    assert "Hard Constraints (Non-Negotiable)" in md
    # Ensure layout prescriptions and template section lists were removed
    assert "Recommended Structure" not in md
    assert "Palette Advice" not in md


def test_generate_brief_file_writing(test_db, sample_lead, tmp_path: Path):
    out_dir = tmp_path / "output"
    settings = Settings(assets_dir=tmp_path / "assets", output_dir=out_dir)

    brief_data, json_p, md_p = generate_brief(test_db, sample_lead, output_dir=out_dir, settings=settings)

    assert json_p.exists()
    assert md_p.exists()
    assert json_p.name == "brief.json"
    assert md_p.name == "brief.md"

    facts_p = out_dir / brief_data["slug"] / "facts.json"
    assert facts_p.exists()
    saved_facts = json.loads(facts_p.read_text(encoding="utf-8"))
    assert saved_facts["business_name"] == "Oak Hill Bakery"
    assert saved_facts["business_type"] == "bakery"
    assert saved_facts["phone_e164"] == "+15125557788"
    assert "photos" in saved_facts
    assert "top_reviews" in saved_facts
    assert saved_facts["owner_notes"] == "Family-run for 8 years. Sourdough starter is 25 years old."


def test_cli_brief(test_db, sample_lead, monkeypatch, capsys, tmp_path: Path):
    from agency import cli

    monkeypatch.setattr(cli, "_conn", lambda: test_db)
    settings = Settings(output_dir=tmp_path / "output", assets_dir=tmp_path / "assets")
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    cli.main(["brief", str(sample_lead)])
    out = capsys.readouterr().out

    assert "Generated design brief for 'Oak Hill Bakery'" in out
    assert "brief.json" in out
    assert "brief.md" in out
