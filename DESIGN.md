# DESIGN.md

Design contract for the site template in `src/agency/sitegen/templates/`. Keep this file in sync with `src/agency/sitegen/render.py` (THEMES) and `site.css`. Do not copy any brand's design system.

## Themes
| Theme | Used for | Background | Ink | Accent | Panel | Display font | Body font |
|---|---|---|---|---|---|---|---|
| food | restaurants, cafes, bakeries | #F6F1FA | #2A1636 | #E8A317 | #2A1636 | Young Serif | Instrument Sans |
| health | pharmacies, clinics, dental | #F2F8F7 | #0C3B3F | #12806F | #0C3B3F | Newsreader | Figtree |
| trades | plumbing, electric, HVAC, repair | #FFFFFF | #0F1B2D | #F25C05 | #0F1B2D | Archivo 800 | Archivo |
| retail | shops and everything else | #F1F4FA | #18223A | #3556D8 | #18223A | Bricolage Grotesque | Hanken Grotesk |

Theme selection: `theme_for_category()` in `sitegen/schema.py`.

## Layout
- Header: business name left, phone right.
- Hero: business name as the large display line, one-line tagline, one call button, address. Opening hours sit in a solid panel beside it on desktop and below it on mobile.
- Sections in order, each hidden when empty: services, about, find us (map and directions link).
- Services are ruled rows (name, description, price on the right), not cards.
- Mobile: a full-width fixed call bar at the bottom. Hidden from 700px up.
- Max content width 1180px. Body text lines no longer than 62ch.

## Rules
- Two typefaces at most per theme (one display, one body), loaded with `display=swap` and real fallbacks.
- Neutrals are tinted toward the theme. No pure black or gray text on colored backgrounds.
- One accent color, used for the primary action and focus rings only.
- No nested cards, no icon tiles above headings, no gradients, no glows, no bounce easing.
- Motion: hover and focus transitions only; respect `prefers-reduced-motion`.
- Text contrast at least 4.5:1, touch targets at least 44px, visible focus styles, one h1, headings in order.

## QA before shipping a template change
1. `agency demo-site --theme <each theme>`, then `agency qa-site --slug demo-<theme>`.
2. Look at the mobile screenshot in `output/_qa/`.
3. Fix every design-detector finding or justify it in a comment.
4. `pytest -q`.
