---
description: Build a custom static site variant using Path A (Impeccable skill)
globs: output/*/variants/a/*
---

# Workflow: Build Site Variant A (Impeccable)

> [!IMPORTANT]
> **CRITICAL AGENT EXECUTION RULES:**
> 1. **FRESH SESSION:** Execute this workflow in a clean, fresh session.
> 2. **BLIND ISOLATION:** Do NOT read, reference, or inspect `output/<slug>/variants/b/` or any other variant directory.
> 3. **TARGET OUTPUT:** Write exclusively to `output/<slug>/variants/a/index.html`. Do NOT overwrite `output/<slug>/index.html`.
> 4. **QA ITERATIONS:** Maximum of 3 QA iterations.
> 5. **BUILD LOG:** You MUST write build timing, iterations, and QA results to `output/<slug>/variants/a/build-log.json`.

---

## Prerequisites
1. Lead must be enriched (`agency enrich <lead_id>`).
2. Design brief must be generated (`agency brief <lead_id>`), producing `output/<slug>/brief.md` and `output/<slug>/brief.json`.

---

## Step-by-Step Procedure

### 1. Read Design Brief
Read `output/<slug>/brief.md` to understand:
- Business name, category, theme, address, phone number (`phone_e164`).
- Verified opening hours (never invent hours).
- Attributed customer reviews and owner notes (story, specialties).
- Local photo assets in `data/assets/<lead_id>/`.
- Category layout advice and tone guidance.

### 2. Start Build Logging
Create directory `output/<slug>/variants/a/` if it does not exist.
Record the build start timestamp:
```json
{
  "variant": "a",
  "start_time": "2026-11-09T10:00:00Z",
  "iterations": 1,
  "first_try_qa_pass": false
}
```

### 3. Craft the Website with Impeccable Skill
Use the **Impeccable** design philosophy:
- **Single Self-Contained File:** Write all markup and styles directly into `output/<slug>/variants/a/index.html`. No external CSS/JS frameworks.
- **Mobile-First Layout:** Perfect rendering on a 375px mobile screen without horizontal overflow.
- **Visual Hierarchy & Typography:** Purposeful type scale, intentional font pairings (e.g. clean system font stacks or high-quality web fonts), distinct headings, generous whitespace.
- **Color & Contrast:** Category-appropriate palette (avoid generic light gray boxes). Ensure high contrast on text and CTAs (WCAG AA).
- **Core Conversion Elements:**
  - High-visibility primary click-to-call button (`tel:<phone_e164>`).
  - Google Maps directions link with real address.
  - Verified opening hours table.
  - Authentic customer review snippets (with author attribution).
  - Owner photos if provided; if none, rely on strong typographic hierarchy and clean layout.
- **Honesty Rule:** Never invent awards, fake prices, unverified menu items, or fabricated claims.

### 4. QA Validation & Iteration (Max 3 Loops)
Run the design detector:
```bash
npx --yes impeccable detect --json output/<slug>/variants/a
```
1. If clean on iteration 1: mark `first_try_qa_pass = true`.
2. If findings are reported: fix them in `output/<slug>/variants/a/index.html` and re-run.
3. Repeat up to 3 iterations maximum.

### 5. Finalize Build Log
Write the final results to `output/<slug>/variants/a/build-log.json`:
```json
{
  "variant": "a",
  "design_path": "impeccable",
  "start_time": "<ISO_START>",
  "end_time": "<ISO_END>",
  "duration_seconds": 180,
  "iterations": 1,
  "first_try_qa_pass": true,
  "qa_status": "clean",
  "findings_count": 0
}
```
