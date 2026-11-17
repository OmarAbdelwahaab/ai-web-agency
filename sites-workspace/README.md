# Sites Workspace

This directory is an isolated, clean workspace for AI coding agents designing custom static websites.

## Workspace Architecture

```
sites-workspace/
├── README.md               # This guide
├── recipes/                # Reusable HTML/CSS building blocks (heroes, grids, reviews, etc.)
├── references/             # Visual reference examples per category
└── <slug>/                 # Active project sandbox for a single lead
    ├── facts.json          # Strict, validated business data
    ├── brief.md            # Design intent and non-negotiable constraints
    ├── assets/             # Authentic owner photos (if available)
    └── index.html          # Finished, self-contained single-page static site
```

## Rules for Agents

1. **Work Exclusively Here:** Work only within `sites-workspace/<slug>/`.
2. **No Template Anchoring:** Never read or copy `src/agency/sitegen/templates/template.html`, `render.py`, `SiteConfig`, or any Python source code.
3. **Strict Facts:** Use only facts from `facts.json` (phone, real hours, verified reviews, address). Never invent claims.
4. **Self-Contained Output:** Write single-file static HTML into `sites-workspace/<slug>/index.html` with inline CSS and minimal JS.
5. **Import When Done:** After testing and validating with `impeccable detect`, import the finished site back to the production output path via:
   ```bash
   agency import-site <slug> [--variant a|b]
   ```
