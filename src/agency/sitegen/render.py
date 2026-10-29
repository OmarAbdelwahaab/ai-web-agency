from __future__ import annotations

import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from agency.sitegen.schema import SiteConfig

TEMPLATES = Path(__file__).parent / "templates"

# Design tokens per theme. Fonts load from Google Fonts with system fallbacks.
THEMES = {
    "food": dict(
        bg="#F6F1FA", ink="#2A1636", muted="#6B5A78", accent="#E8A317", on_accent="#2A1636",
        panel="#2A1636", on_panel="#F6F1FA", rule="#D9CDE3",
        display="'Young Serif', Georgia, serif", body="'Instrument Sans', system-ui, sans-serif",
        fonts="family=Young+Serif&family=Instrument+Sans:wght@400;500;600",
    ),
    "health": dict(
        bg="#F2F8F7", ink="#0C3B3F", muted="#4F7377", accent="#12806F", on_accent="#FFFFFF",
        panel="#0C3B3F", on_panel="#EAF6F4", rule="#CFE3E0",
        display="'Newsreader', Georgia, serif", body="'Figtree', system-ui, sans-serif",
        fonts="family=Newsreader:opsz,wght@6..72,500;6..72,600&family=Figtree:wght@400;500;600",
    ),
    "trades": dict(
        bg="#FFFFFF", ink="#0F1B2D", muted="#5A6678", accent="#F25C05", on_accent="#0F1B2D",
        panel="#0F1B2D", on_panel="#FFFFFF", rule="#E3E7ED",
        display="'Archivo', system-ui, sans-serif", body="'Archivo', system-ui, sans-serif",
        fonts="family=Archivo:wght@400;500;800",
    ),
    "retail": dict(
        bg="#F1F4FA", ink="#18223A", muted="#5B6680", accent="#3556D8", on_accent="#FFFFFF",
        panel="#18223A", on_panel="#F1F4FA", rule="#D8DEEC",
        display="'Bricolage Grotesque', system-ui, sans-serif", body="'Hanken Grotesk', system-ui, sans-serif",
        fonts="family=Bricolage+Grotesque:wght@600;700&family=Hanken+Grotesk:wght@400;500;600",
    ),
}


def _env() -> Environment:
    return Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))


def render_site(cfg: SiteConfig, out_root: Path) -> Path:
    """Render cfg into out_root/<slug>/ and return that directory."""
    out = Path(out_root) / cfg.slug
    out.mkdir(parents=True, exist_ok=True)
    html = _env().get_template("index.html.j2").render(cfg=cfg, t=THEMES[cfg.theme])
    (out / "index.html").write_text(html, encoding="utf-8")
    shutil.copyfile(TEMPLATES / "site.css", out / "site.css")
    (out / "robots.txt").write_text("User-agent: *\nAllow: /\n", encoding="utf-8")
    return out
