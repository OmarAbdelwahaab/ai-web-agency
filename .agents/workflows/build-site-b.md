---
description: Build a custom static site variant using Path B (Open Design CLI/MCP)
globs: output/*/variants/b/*
---

# Workflow: Build Site Variant B (Open Design)

> [!IMPORTANT]
> **CRITICAL AGENT EXECUTION RULES:**
> 1. **FRESH SESSION:** Execute this workflow in a clean, fresh session.
> 2. **BLIND ISOLATION:** Do NOT read, reference, or inspect `output/<slug>/variants/a/` or any other variant directory.
> 3. **TARGET OUTPUT:** Write exclusively to `output/<slug>/variants/b/index.html`. Do NOT overwrite `output/<slug>/index.html`.
> 4. **OPEN DESIGN REQUIREMENT:** Open Design CLI (`od`) must be installed on your environment outside this repository. If `od` is missing, FAIL IMMEDIATELY with an error; do NOT silently fall back.
> 5. **NEVER USE REAL-BRAND DESIGN SYSTEMS:** Tailor design tokens to the specific local client. Never adopt Apple, Stripe, or generic commercial brand systems.
> 6. **QA ITERATIONS:** Maximum of 3 QA iterations against the repo design detector. Open Design lint is advisory only.
> 7. **BUILD LOG:** You MUST write build timing, iterations, and QA results to `output/<slug>/variants/b/build-log.json`.

---

## Step 0: Verify Open Design CLI Availability
Check that `od` is installed:
```bash
od --version
```
If `od` is NOT found in `PATH` or MCP tools, abort execution immediately with:
`Error: 'od' (Open Design CLI) is not installed or available in PATH. Path B requires Open Design installed outside this repo.`

---

## Step-by-Step Procedure

### 1. Read Design Brief & Generate Client DESIGN.md
1. Read `output/<slug>/brief.json` and `output/<slug>/brief.md`.
2. Create directory `output/<slug>/variants/b/` if it does not exist.
3. Use `od` to generate a tailored design specification `output/<slug>/variants/b/DESIGN.md` based on `brief.json`:
   - Design tokens: typography scale, semantic color palette (primary, secondary, neutral, surface, CTA), spacing units.
   - Layout rationale specific to the business type (e.g. food, trades, health).
   - Zero borrowed commercial brand systems (create an authentic, bespoke local palette).

### 2. Start Build Logging
Initialize `output/<slug>/variants/b/build-log.json`:
```json
{
  "variant": "b",
  "start_time": "2026-11-09T10:00:00Z",
  "iterations": 1,
  "first_try_qa_pass": false
}
```

### 3. Build Static Page from Client DESIGN.md
Write `output/<slug>/variants/b/index.html`:
- **Single Self-Contained File:** All HTML, inline CSS, and minimal vanilla JS in one file.
- **Tokens Implementation:** Accurately implement the design system specified in `output/<slug>/variants/b/DESIGN.md`.
- **Mobile Ergonomics:** Responsive down to 375px mobile screen width.
- **Conversion Anchors:**
  - Click-to-call button prominently linked to `tel:<phone_e164>`.
  - Google Maps directions link with real address.
  - Formatted opening hours table.
  - Attributed reviews and owner notes.
- **Honesty Constraint:** Zero invented claims, awards, prices, or fabricated testimonials.

### 4. Run Open Design Critique & Anti-Slop (Advisory)
Run `od critique` or anti-slop check on the built variant:
```bash
od critique output/<slug>/variants/b/index.html
```
Review feedback. *Note: Open Design lint/critique is advisory only; apply helpful refinements.*

### 5. Standard QA Validation & Iteration (Max 3 Loops)
Run the repo's design detector (identical gate to Path A):
```bash
npx --yes impeccable detect --json output/<slug>/variants/b
```
1. If clean on iteration 1: mark `first_try_qa_pass = true`.
2. If findings are reported: fix them in `output/<slug>/variants/b/index.html` and re-run.
3. Repeat up to 3 iterations maximum.

### 6. Finalize Build Log
Record final results in `output/<slug>/variants/b/build-log.json`:
```json
{
  "variant": "b",
  "design_path": "open-design",
  "start_time": "<ISO_START>",
  "end_time": "<ISO_END>",
  "duration_seconds": 195,
  "iterations": 1,
  "first_try_qa_pass": true,
  "qa_status": "clean",
  "findings_count": 0
}
```
