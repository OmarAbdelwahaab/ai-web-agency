# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
- **End visitor (local consumer):** A local resident browsing on a mobile phone (often on cellular data, in a hurry) who needs contact information, opening hours, address/directions, or a quick summary of services.
- **Client (local business owner):** An owner or manager of a local US small business (e.g., trade contractor, restaurant, pharmacy, retail shop) lacking an official website or relying solely on a social profile. Needs local searchers to find and call them without managing complex tech or paying high agency retainers.
- **Agency owner (operator):** The agency operator who oversees lead qualification, monitors AI voice outreach, reviews generated site previews via Telegram, approves deployments, and manages customer relationships.

## Product Purpose
An AI-assisted agency platform that identifies US local businesses lacking websites, conducts compliant AI voice outreach, and upon customer agreement generates a deterministic, single-page, mobile-optimized website populated strictly with verified business facts. The system requires human owner review before deployment to Cloudflare Pages, delivering high-utility web presence within minutes.

## Positioning
Zero-hallucination, high-speed utility websites for local businesses. Unlike generic AI website builders that invent filler copy, stock imagery, fake testimonials, and bloated multi-page frameworks, this system generates clean, deterministic single-page sites filled solely with verified facts from the lead record and call notes, featuring instant tap-to-call, clear hours/location, and zero JavaScript dependencies.

## Operating Context
- **Lead Discovery & Verification:** Google Places API and OpenStreetMap leads scrubbed against TCPA/DNC gates, time-of-day calling windows, and social-only website classifications.
- **Voice Outreach:** LiveKit Agents worker communicating with small business owners via SIP trunk, strictly referencing facts, script guidelines, and `pricing.yaml`.
- **Review & Approval:** Previews generated as static artifacts; agency owner receives mobile-width screenshots and automated Impeccable design-detector reports in Telegram to approve (`/approve <client_id>`) or reject prior to public deployment.
- **Deployment & Hosting:** Static files pushed to Cloudflare Pages; client receives live URL via messaging/email.

## Capabilities and Constraints
- **Strictly Factual Content:** Generated sites must only contain verified data from the lead record or call notes. Never invent hours, prices, years in business, awards, or customer reviews.
- **Single-Page Static Architecture:** Rendered using Jinja2 templates without JavaScript frameworks, client-side trackers, or external web fonts beyond Google Fonts with fallback stacks.
- **Themed Archetypes:** Four distinct industry themes defined in `DESIGN.md`: food, health, trades, and retail.
- **Mobile-First Layout:** Prominent tap-to-call primary CTA, sticky call bar on mobile screens (<700px), visible hours panel, and embedded directions/map link.
- **Out of Scope:** Multi-page architectures, e-commerce, custom customer portals, blogging, appointment booking engines, and intrusive visual animations.

## Brand Commitments
- **Voice & Tone:** Plain, friendly, concise, and respectful. No marketing hyperbole or unverified superlatives ("#1", "best").
- **Identity Model:** Configurable white-label agency branding defined via `.env` / configuration (representing the agency owner's local service).
- **Transparency:** The AI voice agent explicitly discloses that it is an AI assistant calling on behalf of the agency.

## Evidence on Hand
- Jinja2 template and stylesheet located at `src/agency/sitegen/templates/site.html.j2` and `site.css`.
- Pydantic models in `src/agency/sitegen/schema.py` governing `SiteConfig` validation.
- Pricing structure pinned in `pricing.yaml`.
- Database schema and compliance gates in `src/agency/db.py` and `src/agency/compliance/gates.py`.

## Product Principles
1. **Facts Only, Never Hallucinate:** Every claim, service, hour, and contact point on a generated site must derive from verified lead data or recorded call notes.
2. **Phone Call First:** The primary objective of every generated page is facilitating immediate local customer contact (tap-to-call) and physical discovery.
3. **Speed and Semantic Restraint:** Instant loading on weak mobile connections through minimal semantic HTML/CSS, zero client-side JavaScript, and strict accessibility.
4. **Human in the Loop:** No site is published or delivered without the agency owner reviewing and approving the rendered preview in Telegram.

## Accessibility & Inclusion
- WCAG AA text contrast ratio (minimum 4.5:1 for body text, 3:1 for large display elements).
- Minimum touch target sizing of 44x44px for buttons and interactive links.
- Single semantic `<h1>`, strictly ordered heading hierarchy (`<h2>`, `<h3>`), and logical reading order.
- Respect for `prefers-reduced-motion` across all CSS transitions.
