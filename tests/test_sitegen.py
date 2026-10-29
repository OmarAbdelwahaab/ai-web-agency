import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("pydantic")

from agency.config import Settings
from agency.sitegen.ai_fill import fill_config
from agency.sitegen.deploy import deploy_pages
from agency.sitegen.render import THEMES, render_site
from agency.sitegen.schema import (
    HoursRow,
    Service,
    SiteConfig,
    config_from_lead,
    slugify,
    theme_for_category,
)


def cfg(**over):
    base = dict(
        slug="test-shop-1",
        business_name="Test <Shop>",
        tagline="Serving Austin",
        phone="(512) 555-0100",
        phone_e164="+15125550100",
        address="1 Main St, Austin, TX",
        maps_query="Test Shop Austin",
    )
    base.update(over)
    return SiteConfig(**base)


def test_render_contains_phone_and_escapes(tmp_path):
    out = render_site(cfg(), tmp_path)
    html = (out / "index.html").read_text(encoding="utf-8")
    assert 'href="tel:+15125550100"' in html
    assert "Test &lt;Shop&gt;" in html and "<Shop>" not in html
    assert (out / "site.css").exists()
    assert (out / "robots.txt").exists()


def test_meta_tags_and_json_ld(tmp_path):
    c = cfg(
        business_name="Austin Bakehouse",
        tagline="Fresh sourdough and pastries",
        about="Neighborhood bakery crafting sourdough breads daily.",
        address="400 South Congress, Austin, TX",
    )
    html = (render_site(c, tmp_path) / "index.html").read_text(encoding="utf-8")
    assert '<meta name="description" content="Neighborhood bakery crafting sourdough breads daily.">' in html
    assert '<meta property="og:title" content="Austin Bakehouse | Fresh sourdough and pastries">' in html
    assert '<meta property="og:description" content="Neighborhood bakery crafting sourdough breads daily.">' in html
    assert '<meta property="og:type" content="website">' in html

    # JSON-LD structure verification
    assert '<script type="application/ld+json">' in html
    json_ld_raw = html.split('<script type="application/ld+json">')[1].split("</script>")[0]
    data = json.loads(json_ld_raw)
    assert data["@context"] == "https://schema.org"
    assert data["@type"] == "LocalBusiness"
    assert data["name"] == "Austin Bakehouse"
    assert data["telephone"] == "+15125550100"
    assert data["address"] == "400 South Congress, Austin, TX"


def test_optional_sections_hidden_when_empty(tmp_path):
    html = (render_site(cfg(), tmp_path) / "index.html").read_text(encoding="utf-8")
    assert "Opening hours" not in html and "What we do" not in html


def test_sections_shown_when_present(tmp_path):
    c = cfg(hours=[HoursRow(day="Mon", text="9-5")], services=[Service(name="Repairs", price="$50")])
    html = (render_site(c, tmp_path) / "index.html").read_text(encoding="utf-8")
    assert "Opening hours" in html and "Repairs" in html and "$50" in html


@pytest.mark.parametrize("theme", ["food", "health", "trades", "retail"])
def test_all_themes_render(tmp_path, theme):
    out = render_site(cfg(theme=theme), tmp_path)
    html = (out / "index.html").read_text(encoding="utf-8")
    assert THEMES[theme]["bg"] in html
    assert THEMES[theme]["accent"] in html


@pytest.mark.parametrize("slug,theme,name,tagline", [
    ("restaurant-site", "food", "Luigi Trattoria", "Authentic Italian wood-fired pizza"),
    ("pharmacy-site", "health", "Central Care Pharmacy", "Community pharmacy and wellness"),
    ("plumber-site", "trades", "Reliable Plumbing Pros", "Licensed emergency plumbing in Austin"),
    ("barber-site", "retail", "Crown & Blade Barbers", "Master barbers and hot towel shaves"),
    ("hardware-site", "retail", "Highland Hardware & Supply", "Tools, fasteners, and paints"),
])
def test_five_business_types_render(tmp_path, slug, theme, name, tagline):
    c = cfg(slug=slug, theme=theme, business_name=name, tagline=tagline)
    out = render_site(c, tmp_path)
    html = (out / "index.html").read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>")
    assert 'class="call-bar"' in html


def test_bad_slug_rejected():
    with pytest.raises(Exception):
        cfg(slug="Bad Slug!")


def test_helpers():
    assert slugify("Joe's Pizza & Pasta", 7) == "joe-s-pizza-pasta-7"
    assert theme_for_category("pharmacy") == "health"
    assert theme_for_category("plumber") == "trades"
    assert theme_for_category("electrician") == "trades"
    assert theme_for_category("bakery") == "food"
    assert theme_for_category("barber") == "retail"
    assert theme_for_category(None) == "retail"


def test_config_from_lead():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE leads (id INTEGER PRIMARY KEY, name TEXT, category TEXT, phone_e164 TEXT, "
        "address TEXT, city TEXT, hours_json TEXT)"
    )
    conn.execute(
        "INSERT INTO leads VALUES (10, 'Star Auto', 'auto repair', '+15125550188', "
        "'500 1st St', 'Austin', '[\"Mon: 8-5\", \"Tue: 8-5\"]')"
    )
    lead = conn.execute("SELECT * FROM leads WHERE id = 10").fetchone()

    config = config_from_lead(lead, credit="Made by Agency")
    assert config.business_name == "Star Auto"
    assert config.theme == "trades"
    assert config.phone_e164 == "+15125550188"
    assert len(config.hours) == 2
    assert config.hours[0].day == "Mon"
    assert config.hours[0].text == "8-5"
    assert config.credit == "Made by Agency"


# --- AI Fill Tests ---

def make_dummy_lead():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE leads (id INTEGER, name TEXT, category TEXT, phone_e164 TEXT, address TEXT, "
        "city TEXT, hours_json TEXT, rating REAL, rating_count INTEGER)"
    )
    conn.execute(
        "INSERT INTO leads VALUES (1, 'Main Plumbers', 'plumbing', '+15125550100', '100 Main', 'Austin', '[]', 4.8, 42)"
    )
    return conn.execute("SELECT * FROM leads").fetchone()


def test_fill_config_no_api_key():
    lead = make_dummy_lead()
    settings = Settings(llm_api_key="")
    cfg = fill_config(lead, call_notes="owner likes fast work", settings=settings)
    assert cfg.business_name == "Main Plumbers"
    assert cfg.tagline == "Serving Austin"


def test_fill_config_valid_llm_response():
    lead = make_dummy_lead()
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.choices = [
        MagicMock(message=MagicMock(content=json.dumps({
            "tagline": "Reliable 24/7 plumbing repairs in Austin",
            "about": "Family-operated plumbing service trusted by Austin homeowners.",
            "services": [
                {"name": "Drain Snaking", "description": "Quick clearing of clogs", "price": "$120"},
            ],
        })))
    ]
    mock_client.chat.completions.create.return_value = mock_resp

    cfg = fill_config(lead, call_notes="drain snaking", client=mock_client)
    assert cfg.tagline == "Reliable 24/7 plumbing repairs in Austin"
    assert cfg.about == "Family-operated plumbing service trusted by Austin homeowners."
    assert len(cfg.services) == 1
    assert cfg.services[0].name == "Drain Snaking"
    assert cfg.services[0].price == "$120"


def test_fill_config_llm_retry_and_fallback():
    lead = make_dummy_lead()
    mock_client = MagicMock()
    # First response invalid JSON, second response invalid JSON
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content="not valid json"))]
    mock_client.chat.completions.create.return_value = mock_resp

    cfg = fill_config(lead, call_notes="notes", client=mock_client)
    assert cfg.tagline == "Serving Austin"  # deterministic fallback


def test_fill_config_llm_exception_fallback():
    lead = make_dummy_lead()
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("network down")

    cfg = fill_config(lead, call_notes="notes", client=mock_client)
    assert cfg.tagline == "Serving Austin"


# --- Deploy Pages Tests ---

def test_deploy_pages_disabled():
    with pytest.raises(RuntimeError, match="DEPLOY_ENABLED is false"):
        deploy_pages(Path("x"), "test-project", settings=Settings(deploy_enabled=False))


def test_deploy_pages_missing_tokens(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    with pytest.raises(RuntimeError, match="CLOUDFLARE_API_TOKEN is not set"):
        deploy_pages(Path("x"), "test-project", settings=Settings(deploy_enabled=True))


def test_deploy_pages_success(monkeypatch, tmp_path):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token123")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acc123")
    mock_run = MagicMock()
    monkeypatch.setattr("agency.sitegen.deploy.subprocess.run", mock_run)

    url = deploy_pages(tmp_path, "my-shop", settings=Settings(deploy_enabled=True))
    assert url == "https://my-shop.pages.dev"
    assert mock_run.call_count == 2
