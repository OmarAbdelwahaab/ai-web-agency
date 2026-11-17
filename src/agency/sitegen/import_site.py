"""Import completed site from isolated sites-workspace/<slug>/ into production output/<slug>/."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from agency.config import Settings, get_settings
from agency.sitegen import qa


def import_site(
    slug: str,
    variant: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Copy finished site from sites-workspace/<slug>/ to output/<slug>/ (or variants/<variant>/)."""
    s = settings or get_settings()
    workspace_dir = s.sites_workspace_dir / slug
    source_html = workspace_dir / "index.html"

    if not source_html.exists():
        raise FileNotFoundError(
            f"Site not found at {source_html}. Please build the site in sites-workspace/{slug}/ first."
        )

    if variant:
        var_clean = variant.strip().lower()
        if var_clean not in ("a", "b"):
            raise ValueError(f"Invalid variant '{variant}'. Must be 'a' or 'b'.")
        target_dir = s.output_dir / slug / "variants" / var_clean
    else:
        target_dir = s.output_dir / slug

    target_dir.mkdir(parents=True, exist_ok=True)

    # 1. Copy index.html
    shutil.copyfile(source_html, target_dir / "index.html")

    # 2. Copy assets/ if present
    workspace_assets = workspace_dir / "assets"
    if workspace_assets.exists() and workspace_assets.is_dir():
        target_assets = target_dir / "assets"
        target_assets.mkdir(parents=True, exist_ok=True)
        for f in workspace_assets.iterdir():
            if f.is_file():
                shutil.copyfile(f, target_assets / f.name)

    # 3. Copy facts.json & brief.md if present
    for meta_file in ("facts.json", "brief.md"):
        src_meta = workspace_dir / meta_file
        if src_meta.exists():
            shutil.copyfile(src_meta, target_dir / meta_file)

    # 4. Run QA gate
    qa_res = qa.run_qa_gate(target_dir)
    qa_summary = qa.summarize_for_owner(qa_res)

    return {
        "slug": slug,
        "variant": variant,
        "source_dir": workspace_dir,
        "target_dir": target_dir,
        "qa_result": qa_res,
        "qa_summary": qa_summary,
    }
