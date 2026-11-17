# Design Path A/B Testing Guide: Impeccable vs. Open Design

This guide outlines how to execute a controlled, blind A/B comparison between two site-design methodologies:
- **Path A ("impeccable"):** Code-first static design using the Impeccable skill.
- **Path B ("open-design"):** Open Design CLI (`od`) client-specific `DESIGN.md` generation, advisory anti-slop critique, and tokenized layout.

Both paths produce single-file, self-contained static HTML pages and are evaluated under identical QA gates and criteria.

---

## 1. Candidate Lead Selection (6–8 Leads)

Select 6 to 8 enriched leads spanning at least 3 distinct business categories:
- **Category 1 (Food / Beverage):** 2 leads (e.g. coffee shop, bakery, diner).
- **Category 2 (Home Trades):** 2 leads (e.g. plumbing, electrician, roofing).
- **Category 3 (Health / Care):** 2 leads (e.g. dental clinic, physical therapy, pharmacy).
- **Category 4 (Retail / Services):** 1–2 leads (e.g. boutique, hardware store, auto repair).

### Preparation Steps:
```bash
# 1. Enrich each lead with Google Places details, reviews, and local photos
agency enrich <lead_id>

# 2. Add owner call notes if available
agency note-lead <lead_id> "Key specialties and owner context"

# 3. Generate the design brief (produces output/<slug>/brief.json and brief.md)
agency brief <lead_id>
```

---

## 2. Generating Variant A and Variant B in Isolation

> [!IMPORTANT]
> **Strict Isolation Requirement:**
> - Variant A and Variant B must be generated in **separate, fresh sessions** to avoid cross-variant contamination.
> - An agent generating Variant A must never read `variants/b/`, and vice-versa.

### Generating Variant A (Impeccable):
1. In a fresh agent session, execute workflow:
   `.agents/workflows/build-site-a.md`
2. Target output: `output/<slug>/variants/a/index.html`.
3. Verify `output/<slug>/variants/a/build-log.json` recorded start/end time, iterations, and QA pass.

### Generating Variant B (Open Design):
1. Ensure Open Design (`od`) is installed on your machine outside this repository:
   ```bash
   od --version
   ```
   *(Note: If `od` is missing, Path B will fail with a clear error. Do not vendor Open Design into this repo).*
2. In a fresh agent session, execute workflow:
   `.agents/workflows/build-site-b.md`
3. Target output: `output/<slug>/variants/b/index.html`.
4. Verify `output/<slug>/variants/b/build-log.json` is recorded.

---

## 3. Running Blind Comparison

Generate the comparison harness and blind mapping:
```bash
agency compare <lead_id>
```

This command will:
1. Run QA checks on both variants.
2. Generate randomized `output/<slug>/variants/mapping.json` (assigns "Site 1" and "Site 2" randomly to 'a' or 'b').
3. Create `output/<slug>/compare.html`.
4. Capture phone screenshots (`mobile.png`) for both variants if `playwright-cli` is installed.

Open `output/<slug>/compare.html` in your browser. The page displays:
- Side-by-side iframes labeled purely as **Site 1** and **Site 2**.
- Desktop View (1200px) and Mobile View (375px) toggles.
- True variant mapping is completely hidden from the page.

---

## 4. Blind Scoring Workflow

Score both sites on a 1–5 scale across all 6 criteria:
1. `first_impression`: Visual impact, clarity of proposition, layout polish.
2. `layout_fit`: Whether the layout feels authentic and natural to the business category.
3. `copy_specificity`: Use of genuine facts, lack of generic filler copy.
4. `typography_color`: Font pairing, typographic scale, contrast, color palette.
5. `mobile`: Ergonomics on 375px phone screen, touch target sizes, CTA accessibility.
6. `photo_use`: Natural integration of owner photos or strong layout when photos are absent.

### Recording Scores:
```bash
agency score <lead_id> "Site 1" first_impression 4
agency score <lead_id> "Site 2" first_impression 5

agency score <lead_id> "Site 1" layout_fit 4
agency score <lead_id> "Site 2" layout_fit 4

agency score <lead_id> "Site 1" copy_specificity 5
agency score <lead_id> "Site 2" copy_specificity 4

agency score <lead_id> "Site 1" typography_color 4
agency score <lead_id> "Site 2" typography_color 5

agency score <lead_id> "Site 1" mobile 5
agency score <lead_id> "Site 2" mobile 4

agency score <lead_id> "Site 1" photo_use 4
agency score <lead_id> "Site 2" photo_use 4
```

### Revealing Mapping (After Scoring):
Once all scores for the lead are submitted, reveal the mapping:
```bash
agency reveal <lead_id>
```

---

## 5. Aggregating Results & Decision Rule

After completing evaluations across all 6–8 leads, run the report:
```bash
agency compare-report --output reports/ab_results.csv
```

### Decision / Verdict Rule:
- A path wins if:
  1. It scores higher on **at least 5 of 8 leads** (or $\ge 62.5\%$ of leads), **AND**
  2. Its QA first-try pass rate is **not worse** than the competitor.
- If neither path meets this bar:
  `"no clear winner, consider hybrid"`

---

## 6. Retiring the Comparison Harness

Once a winner is determined:
1. If **Path A (Impeccable)** wins:
   - Keep `.agents/workflows/build-site-a.md` as the primary `.agents/workflows/build-site.md`.
   - Remove `.agents/workflows/build-site-b.md`.
2. If **Path B (Open Design)** wins:
   - Promote `.agents/workflows/build-site-b.md` to `.agents/workflows/build-site.md`.
   - Remove `.agents/workflows/build-site-a.md`.
3. If **Hybrid**:
   - Merge `od` client-specific token generation with Impeccable review passes into a unified workflow.
