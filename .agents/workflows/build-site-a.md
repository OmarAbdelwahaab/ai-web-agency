---
description: Build a custom static site variant using Path A (Impeccable skill) in sites-workspace
globs: sites-workspace/*
---

# Workflow: Build Site Variant A (Impeccable)

> [!IMPORTANT]
> **CRITICAL AGENT EXECUTION RULES:**
> 1. **FRESH SESSION:** Execute this workflow in a clean, fresh session.
> 2. **ISOLATED WORKSPACE:** Work ONLY within `sites-workspace/<slug>/`.
> 3. **NO TEMPLATE ANCHORING:** NEVER inspect, read, or copy from `src/agency/sitegen/templates/`, `render.py`, `SiteConfig`, or any Python source files.
> 4. **BLIND ISOLATION:** Do NOT read, reference, or inspect any other variant or previous output directory.
> 5. **CONCEPT FIRST:** Write 3 distinct design concepts to `sites-workspace/<slug>/concepts.md`, select one, then build.
> 6. **SCREENSHOT & CRITIQUE LOOP:** Screenshot at 375px and 1280px with `playwright-cli`, critique against the written rubric, fix. Stop when the rubric passes or after 5 rounds.
> 7. **TARGET OUTPUT:** Write `sites-workspace/<slug>/index.html`.
> 8. **IMPORT TO OUTPUT:** Import using `agency import-site <slug> --variant a`.
> 9. **BUILD LOG:** Record build timing, rounds/iterations, and QA results to `output/<slug>/variants/a/build-log.json`.

---

## Prerequisites
1. Lead must be enriched (`agency enrich <lead_id>`).
2. Design brief must be generated (`agency brief <lead_id>`), exporting `sites-workspace/<slug>/{facts.json,brief.md,assets/}`.

---

## Step-by-Step Procedure

### 1. Read Design Brief & Facts
Read `sites-workspace/<slug>/facts.json` and `sites-workspace/<slug>/brief.md` to understand:
- Business name, business type, phone number (`phone_e164`).
- Cleaned address and directions link.
- Verified opening hours (never guess or invent hours).
- Attributed customer reviews and owner notes (story, specialties).
- Local photo assets in `sites-workspace/<slug>/assets/`.
- Review modular building blocks in `sites-workspace/recipes/` if needed for inspiration.

### 2. Start Build Logging
Create directory `output/<slug>/variants/a/` if it does not exist.
Initialize `output/<slug>/variants/a/build-log.json`:
```json
{
  "variant": "a",
  "design_path": "impeccable",
  "start_time": "<ISO_START>",
  "rounds": 1,
  "first_try_rubric_pass": false
}
```

### 3. Concept First: Write 3 Design Concepts
Before writing HTML, create `sites-workspace/<slug>/concepts.md` with 3 short design concepts tailored to this specific local business:

Each concept must specify:
1. **Mood & Atmosphere:** (e.g. "Warm artisan morning bakery", "Crisp reliable emergency trades")
2. **Color Palette:** Hex values for Background, Surface, Primary Accent, Text, and CTA.
3. **Typography Pairing:** Heading font and body font stack with sizes.
4. **Layout Idea:** Above-the-fold composition, hero structure, and focal flow.

At the bottom of `concepts.md`, explicitly declare the selected concept and the rationale:
```markdown
## Selected Concept
Concept 2 is selected because...
```

### 4. Build Static Website (Impeccable Guidance)
Write the site into `sites-workspace/<slug>/index.html` following **Impeccable** design guidance:
- **Work Exclusively in Workspace:** Write all markup and styles directly into `sites-workspace/<slug>/index.html`.
- **Single Self-Contained File:** All HTML, inline CSS, and minimal vanilla JS in one file. No external CSS/JS frameworks.
- **Mobile-First Layout:** Perfect rendering on a 375px mobile screen without horizontal scrolling.
- **Visual Hierarchy & Typography:** Purposeful type scale, intentional font pairings (clean system font stacks or high-quality web fonts), distinct headings, generous whitespace.
- **Color & Contrast:** Purposeful palette matching the business type. Ensure high contrast on text and CTAs (WCAG AA compliant: 4.5:1 body, 3:1 headings).
- **Core Conversion Anchors:**
  - High-visibility primary click-to-call button (`tel:<phone_e164>`).
  - Google Maps directions link with real address.
  - Verified opening hours table (use recipe from `sites-workspace/recipes/hours.html` if desired).
  - Authentic customer review snippets (with author attribution).
  - Owner photos from `assets/` if provided; if none, rely on strong typographic hierarchy and clean layout.
- **Honesty Rule:** Never invent awards, fake prices, unverified menu items, or fabricated claims.

### 5. Screenshot, Critique & Fix Loop (Up to 5 Rounds)
For each round (up to 5 rounds max):

1. **Capture Screenshots at 375px and 1280px:**
   Serve the site and take screenshots using `playwright-cli`:
   - Mobile: 375px width (`--device="iPhone 15"` or viewport 375x667).
   - Desktop: 1280px width (viewport 1280x800).
2. **Critique against Written Rubric:**
   - **Rubric 1: Visual Hierarchy & Spacing:** Does the page breathe? Is the primary CTA unmissable?
   - **Rubric 2: Typography & Color:** Do font sizes scale cleanly? Is contrast WCAG AA compliant?
   - **Rubric 3: Fact Fidelity:** Are phone, address, verified hours, and reviews 100% faithful to `facts.json`?
   - **Rubric 4: Mobile Polish (375px):** Is there ZERO horizontal scroll? Are tap targets >= 44px?
   - **Rubric 5: Zero AI Slop / Filler:** Are there zero filler phrases ("lorem ipsum", "elevate", "beacon of excellence")?
3. **Run Design Detector:**
   ```bash
   npx --yes impeccable detect --json sites-workspace/<slug>
   ```
4. **Fix & Iterate:** If any rubric item or detector finding fails, fix `sites-workspace/<slug>/index.html` and repeat.
5. **Exit Condition:** Stop immediately when all 5 rubric points pass and detector is clean, or after 5 rounds.

### 6. Import to Production Output
Once validated, import the completed site to Variant A:
```bash
agency import-site <slug> --variant a
```

### 7. Finalize Build Log
Record final results in `output/<slug>/variants/a/build-log.json`:
```json
{
  "variant": "a",
  "design_path": "impeccable",
  "selected_concept": "Concept 2",
  "start_time": "<ISO_START>",
  "end_time": "<ISO_END>",
  "duration_seconds": 210,
  "rounds": 2,
  "first_try_rubric_pass": false,
  "qa_status": "clean",
  "findings_count": 0
}
```
