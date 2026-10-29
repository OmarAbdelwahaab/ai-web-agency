import pytest

pytest.importorskip("pydantic")

from agency.sitegen.render import render_site
from agency.sitegen.schema import HoursRow, Service, SiteConfig, slugify, theme_for_category


def cfg(**over):
    base = dict(slug="test-shop-1", business_name="Test <Shop>", tagline="Serving Austin", phone="(512) 555-0100",
                phone_e164="+15125550100", address="1 Main St, Austin, TX", maps_query="Test Shop Austin")
    base.update(over)
    return SiteConfig(**base)


def test_render_contains_phone_and_escapes(tmp_path):
    out = render_site(cfg(), tmp_path)
    html = (out / "index.html").read_text()
    assert 'href="tel:+15125550100"' in html
    assert "Test &lt;Shop&gt;" in html and "<Shop>" not in html
    assert (out / "site.css").exists()


def test_optional_sections_hidden_when_empty(tmp_path):
    html = (render_site(cfg(), tmp_path) / "index.html").read_text()
    assert "Opening hours" not in html and "What we do" not in html


def test_sections_shown_when_present(tmp_path):
    c = cfg(hours=[HoursRow(day="Mon", text="9-5")], services=[Service(name="Repairs", price="$50")])
    html = (render_site(c, tmp_path) / "index.html").read_text()
    assert "Opening hours" in html and "Repairs" in html and "$50" in html


@pytest.mark.parametrize("theme", ["food", "health", "trades", "retail"])
def test_all_themes_render(tmp_path, theme):
    assert (render_site(cfg(theme=theme), tmp_path) / "index.html").exists()


def test_bad_slug_rejected():
    with pytest.raises(Exception):
        cfg(slug="Bad Slug!")


def test_helpers():
    assert slugify("Joe's Pizza & Pasta", 7) == "joe-s-pizza-pasta-7"
    assert theme_for_category("pharmacy") == "health"
    assert theme_for_category("plumber") == "trades"
    assert theme_for_category(None) == "retail"
