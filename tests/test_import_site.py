"""Unit tests for agency import-site command and import_site module."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agency.config import Settings
from agency.sitegen.import_site import import_site


def test_import_site_missing_source_raises(tmp_path: Path):
    settings = Settings(
        output_dir=tmp_path / "output",
        sites_workspace_dir=tmp_path / "sites-workspace",
    )
    with pytest.raises(FileNotFoundError) as exc_info:
        import_site("nonexistent-slug", settings=settings)
    assert "Please build the site in sites-workspace/nonexistent-slug/ first" in str(exc_info.value)


def test_import_site_invalid_variant_raises(tmp_path: Path):
    settings = Settings(
        output_dir=tmp_path / "output",
        sites_workspace_dir=tmp_path / "sites-workspace",
    )
    ws_slug = settings.sites_workspace_dir / "my-slug"
    ws_slug.mkdir(parents=True)
    (ws_slug / "index.html").write_text("<html><body>Test</body></html>", encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        import_site("my-slug", variant="c", settings=settings)
    assert "Invalid variant 'c'. Must be 'a' or 'b'" in str(exc_info.value)


def test_import_site_to_main_output(tmp_path: Path):
    settings = Settings(
        output_dir=tmp_path / "output",
        sites_workspace_dir=tmp_path / "sites-workspace",
    )
    slug = "austin-bakery-1"
    ws_slug = settings.sites_workspace_dir / slug
    ws_slug.mkdir(parents=True)

    (ws_slug / "index.html").write_text("""<!DOCTYPE html><html><head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Austin Bakery</title></head><body><h1>Austin Bakery</h1>
    <p>123 Main St, Austin, TX</p><p>(512) 555-0100</p>
    <a href="tel:+15125550100">Call</a></body></html>""", encoding="utf-8")
    (ws_slug / "facts.json").write_text(json.dumps({"name": "Austin Bakery", "phone": "(512) 555-0100", "phone_e164": "+15125550100", "address": "123 Main St, Austin, TX"}), encoding="utf-8")
    (ws_slug / "brief.md").write_text("# Design Brief: Austin Bakery", encoding="utf-8")

    assets_dir = ws_slug / "assets"
    assets_dir.mkdir()
    (assets_dir / "bread.jpg").write_text("fake image data", encoding="utf-8")

    res = import_site(slug, settings=settings)
    assert res["slug"] == slug
    assert res["variant"] is None

    target = settings.output_dir / slug
    assert (target / "index.html").exists()
    assert (target / "facts.json").exists()
    assert (target / "brief.md").exists()
    assert (target / "assets" / "bread.jpg").exists()
    assert (target / "assets" / "bread.jpg").read_text(encoding="utf-8") == "fake image data"
    assert "QA" in res["qa_summary"]


def test_import_site_to_variant(tmp_path: Path):
    settings = Settings(
        output_dir=tmp_path / "output",
        sites_workspace_dir=tmp_path / "sites-workspace",
    )
    slug = "austin-bakery-1"
    ws_slug = settings.sites_workspace_dir / slug
    ws_slug.mkdir(parents=True)

    (ws_slug / "index.html").write_text("""<!DOCTYPE html><html><head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Austin Bakery</title></head><body><h1>Austin Bakery</h1>
    <p>123 Main St, Austin, TX</p><p>(512) 555-0100</p>
    <a href="tel:+15125550100">Call</a></body></html>""", encoding="utf-8")

    res = import_site(slug, variant="b", settings=settings)
    assert res["variant"] == "b"

    target = settings.output_dir / slug / "variants" / "b"
    assert (target / "index.html").exists()


def test_cli_import_site(tmp_path: Path, monkeypatch, capsys):
    from agency import cli

    settings = Settings(
        output_dir=tmp_path / "output",
        sites_workspace_dir=tmp_path / "sites-workspace",
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    slug = "austin-bakery-1"
    ws_slug = settings.sites_workspace_dir / slug
    ws_slug.mkdir(parents=True)
    (ws_slug / "index.html").write_text("""<!DOCTYPE html><html><head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Austin Bakery</title></head><body><h1>Austin Bakery</h1></body></html>""", encoding="utf-8")

    cli.main(["import-site", slug, "--variant", "a"])
    out = capsys.readouterr().out
    assert "Imported site for 'austin-bakery-1' successfully:" in out
    assert "Variant: a" in out
    assert (settings.output_dir / slug / "variants" / "a" / "index.html").exists()
