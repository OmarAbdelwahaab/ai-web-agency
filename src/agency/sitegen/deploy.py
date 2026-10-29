"""Deploy a rendered site to Cloudflare Pages using wrangler. Disabled unless DEPLOY_ENABLED=true."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from agency.config import Settings, get_settings


def deploy_pages(site_dir: Path, project: str, *, settings: Settings | None = None) -> str:
    s = settings or get_settings()
    if not s.deploy_enabled:
        raise RuntimeError("DEPLOY_ENABLED is false")
    for var in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"):
        if not os.environ.get(var):
            raise RuntimeError(f"{var} is not set")
    npx = shutil.which("npx") or "npx"
    # TODO(verify): confirm current wrangler flags at https://developers.cloudflare.com/pages/
    subprocess.run(
        [npx, "--yes", "wrangler", "pages", "project", "create", project, "--production-branch", "main"],
        capture_output=True, text=True,
    )  # ignore failure: project may already exist
    subprocess.run(
        [npx, "--yes", "wrangler", "pages", "deploy", str(site_dir), "--project-name", project, "--branch", "main"],
        check=True, capture_output=True, text=True,
    )
    return f"https://{project}.pages.dev"
