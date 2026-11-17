from __future__ import annotations

import argparse
import json
import logging
import sys

from agency.config import get_settings
from agency.db import connect, get_lead, init_db, insert_lead


def _conn():
    s = get_settings()
    conn = connect(s.db_path)
    init_db(conn)
    return conn


def _auto_export_leads(conn, target: Path | str | None = None) -> None:
    """Automatically export all leads (any status) to CSV."""
    from agency.reporting import export_table_to_csv

    s = get_settings()
    out = Path(target) if target else s.leads_csv_path
    cnt = export_table_to_csv(conn, "leads", out)
    print(f"Auto-exported {cnt} total leads to {out}")


def cmd_init_db(a):
    _conn()
    print("database ready")


def cmd_find_leads(a):
    conn = _conn()
    if a.source == "places":
        from agency.leads import places

        found = places.search(f"{a.query} in {a.city}", limit=a.limit)
        print(f"{len(found)} places found, {places.save(conn, found, category=a.query)} new candidates saved")
    elif a.source == "geoapify":
        from agency.leads import geoapify

        found = geoapify.search(a.query, a.city, limit=a.limit)
        print(f"{len(found)} places found, {geoapify.save(conn, found, category=a.query)} new candidates saved")
    else:
        from agency.leads import osm

        found = osm.search(a.query, a.city)
        print(f"{len(found)} elements found, {osm.save(conn, found, a.query)} new candidates saved")
    _auto_export_leads(conn, getattr(a, "export_csv", None))


def cmd_verify(a):
    from agency.leads.verify import scrub_all, verify_all

    conn = _conn()
    print("verify:", verify_all(conn, a.limit))
    print("scrub:", scrub_all(conn))
    _auto_export_leads(conn)


def cmd_add_lead(a):
    """Insert a lead by hand (use your own phone number for tests)."""
    from agency.leads.verify import timezone_for
    from agency.phone import to_e164

    conn = _conn()
    phone = to_e164(a.phone)
    if not phone:
        sys.exit("invalid phone number")
    lid = insert_lead(
        conn, source="manual", source_id=phone, name=a.name, category=a.category, phone_e164=phone, city=a.city,
        state=a.state, lat=a.lat, lng=a.lng, timezone=timezone_for(a.lat, a.lng), status="ready",
        address=a.address, website_checked=0,
    )
    print(f"lead id {lid}" if lid else "lead already exists")
    _auto_export_leads(conn)


def cmd_preview(a):
    from agency.sitegen.ai_fill import fill_config
    from agency.sitegen.render import render_site

    s = get_settings()
    conn = _conn()
    lead = get_lead(conn, a.lead_id)
    if lead is None:
        sys.exit("lead not found")
    cfg = fill_config(lead, a.notes or "", credit=f"Website by {s.agency_name}", settings=s)
    print(render_site(cfg, s.output_dir))


def cmd_demo_site(a):
    from agency.sitegen.render import render_site
    from agency.sitegen.schema import HoursRow, Service, SiteConfig

    cfg = SiteConfig(
        slug=f"demo-{a.theme}", business_name="Lone Star Plumbing", theme=a.theme,
        tagline="Licensed local plumbers serving Austin", about="Family-run shop. Call any time with a leak, a clog, or a question.",
        phone="(512) 555-0100", phone_e164="+15125550100", address="1200 Example St, Austin, TX 78701",
        maps_query="1200 Example St Austin TX",
        hours=[HoursRow(day=d, text="8 AM - 6 PM") for d in ("Mon", "Tue", "Wed", "Thu", "Fri")] + [HoursRow(day="Sat", text="9 AM - 1 PM")],
        services=[Service(name="Leak repair", description="Fast diagnosis and fix"), Service(name="Water heaters", price="From $120")],
        credit="Website by Your Agency",
    )
    print(render_site(cfg, get_settings().output_dir))


def cmd_import_csv(a):
    from agency.leads.csv_import import import_csv

    conn = _conn()
    print(import_csv(conn, a.file, default_lat=a.lat, default_lng=a.lng, default_city=a.city,
                     default_state=a.state, source=a.source_label))
    _auto_export_leads(conn)


def cmd_qa_site(a):
    from agency.sitegen import qa

    s = get_settings()
    site_dir = s.output_dir / a.slug
    if not site_dir.exists():
        sys.exit(f"{site_dir} does not exist; run `agency preview` or `agency demo-site` first")
    print(qa.summarize_for_owner(qa.run_detector(site_dir)))
    shot = s.output_dir / "_qa" / a.slug / "mobile.png"
    print(f"mobile screenshot: {shot}" if qa.mobile_screenshot(site_dir, shot) else "mobile screenshot skipped (playwright-cli not installed or failed)")


def cmd_dial(a):
    from agency.voice.dispatch import dispatch_call

    print(json.dumps(dispatch_call(_conn(), a.lead_id, live=a.live), indent=2))


def cmd_dnc_add(a):
    from agency.compliance.gates import add_dnc
    from agency.phone import to_e164

    phone = to_e164(a.phone)
    if not phone:
        sys.exit("invalid phone number")
    add_dnc(_conn(), phone, a.reason)
    print(f"{phone} added to DNC")


def cmd_bot(a):
    from agency.notify.telegram import run_bot

    run_bot(_conn())


def cmd_dashboard(a):
    from agency.reporting import render_dashboard

    print(render_dashboard(_conn()))


def cmd_export_csv(a):
    from agency.reporting import export_all_to_csv, export_table_to_csv

    conn = _conn()
    if a.table == "all":
        results = export_all_to_csv(conn, a.output)
        print("Exported tables to " + str(a.output) + ":")
        for tbl, cnt in sorted(results.items()):
            print(f"  {tbl}.csv: {cnt} rows")
    else:
        cnt = export_table_to_csv(conn, a.table, a.output)
        print(f"Exported {cnt} rows from '{a.table}' to {a.output}")


def cmd_record_legal_review(a):
    from agency.db import record_legal_review

    rid = record_legal_review(_conn(), a.attorney, law_firm=a.firm or "", notes=a.notes or "")
    print(f"Legal review #{rid} recorded for {a.attorney}")


def cmd_enrich(a):
    from agency.enrichment import enrich_lead, is_rich_lead
    from agency.enrichment.images import LocalAssetSource

    s = get_settings()
    conn = _conn()
    enrichment = enrich_lead(conn, a.lead_id, settings=s)
    lead = get_lead(conn, a.lead_id)
    local_imgs = LocalAssetSource(s.assets_dir).get_images(a.lead_id)
    qualifies = is_rich_lead(enrichment.data_richness, s.richness_threshold)

    print(f"Enriched Lead #{a.lead_id}: {lead['name'] if lead else 'Unknown'}")
    print(f"  Rating: {enrichment.rating or 'N/A'} ({enrichment.review_count or 0} reviews)")
    print(f"  Top review snippets: {len(enrichment.top_reviews)}")
    print(f"  Categories: {', '.join(enrichment.categories) if enrichment.categories else 'None'}")
    print(f"  Photo references: {len(enrichment.photo_refs)}")
    print(f"  Local owner images: {len(local_imgs)}")
    print(f"  Website absent: {'Yes' if enrichment.website_confirmed_none else 'No'}")
    if enrichment.owner_notes:
        print(f"  Owner notes: {enrichment.owner_notes.strip()}")
    print(f"  Data richness score: {enrichment.data_richness:.2f} (Threshold: {s.richness_threshold:.2f})")
    print(f"  Status: {'QUALIFIED for agent-built site' if qualifies else 'Template fallback'}")


def cmd_note_lead(a):
    from agency.enrichment import is_rich_lead, record_owner_note

    note_text = (a.note or a.flag_note or "").strip()
    if not note_text:
        sys.exit("error: note text is required")

    s = get_settings()
    conn = _conn()
    enrichment = record_owner_note(conn, a.lead_id, note_text, settings=s)
    qualifies = is_rich_lead(enrichment.data_richness, s.richness_threshold)

    print(f"Recorded owner note for Lead #{a.lead_id}:")
    print(f"  Note: {note_text}")
    print(f"  Updated data richness score: {enrichment.data_richness:.2f} (Threshold: {s.richness_threshold:.2f})")
    print(f"  Status: {'QUALIFIED for agent-built site' if qualifies else 'Template fallback'}")


def cmd_brief(a):
    from agency.sitegen.brief import generate_brief

    s = get_settings()
    conn = _conn()
    brief_data, json_p, md_p = generate_brief(conn, a.lead_id, settings=s)
    print(f"Generated design brief for '{brief_data['business_name']}' (#{a.lead_id}):")
    print(f"  Slug: {brief_data['slug']}")
    print(f"  Theme: {brief_data['theme']} ({brief_data['category']})")
    print(f"  Data richness: {brief_data['data_richness']:.2f}")
    print(f"  JSON: {json_p}")
    print(f"  Markdown: {md_p}")


def cmd_import_site(a):
    from agency.sitegen.import_site import import_site

    s = get_settings()
    try:
        res = import_site(a.slug, variant=a.variant, settings=s)
    except (FileNotFoundError, ValueError) as e:
        sys.exit(f"error: {e}")

    print(f"Imported site for '{a.slug}' successfully:")
    print(f"  Source: {res['source_dir']}")
    print(f"  Target: {res['target_dir']}")
    if res.get("variant"):
        print(f"  Variant: {res['variant']}")
    print(f"  QA Status: {res['qa_summary']}")



def cmd_compare(a):
    from agency.sitegen.compare import compare_lead

    s = get_settings()
    conn = _conn()
    res = compare_lead(conn, a.lead_id, settings=s)
    print(f"A/B Comparison generated for '{res['business_name']}' (#{a.lead_id}):")
    print(f"  Comparison view: {res['compare_html']}")
    print(f"  Blind mapping: {res['mapping_path']} (hidden from comparison page)")
    print(f"  Variant A QA: {res['variant_a_qa']['summary']}")
    print(f"  Variant B QA: {res['variant_b_qa']['summary']}")
    if res.get("screenshot_a"):
        print(f"  Screenshot A: {res['screenshot_a']}")
    if res.get("screenshot_b"):
        print(f"  Screenshot B: {res['screenshot_b']}")


def cmd_score(a):
    from agency.db import get_lead, record_design_score
    from agency.sitegen.compare import VALID_CRITERIA, get_or_create_mapping, resolve_site_label
    from agency.sitegen.schema import slugify

    crit = a.criterion.lower()
    if crit not in VALID_CRITERIA:
        sys.exit(f"error: invalid criterion '{a.criterion}'. Choose from: {', '.join(VALID_CRITERIA)}")
    if a.score < 1 or a.score > 5:
        sys.exit("error: score must be between 1 and 5")

    s = get_settings()
    conn = _conn()
    lead = get_lead(conn, a.lead_id)
    if not lead:
        sys.exit(f"error: lead #{a.lead_id} not found")

    slug = slugify(lead["name"], lead["id"])
    variants_dir = s.output_dir / slug / "variants"
    mapping = get_or_create_mapping(variants_dir)

    variant = resolve_site_label(a.site_label, mapping)
    sid = record_design_score(conn, a.lead_id, variant, crit, a.score, reviewer=a.reviewer)

    print(f"Recorded score #{sid} for Lead #{a.lead_id}:")
    print(f"  Candidate: {a.site_label}")
    print(f"  Criterion: {crit}")
    print(f"  Score: {a.score}/5")
    print(f"  Reviewer: {a.reviewer}")


def cmd_reveal(a):
    from agency.db import get_design_scores, get_lead
    from agency.sitegen.compare import get_or_create_mapping
    from agency.sitegen.schema import slugify

    s = get_settings()
    conn = _conn()
    lead = get_lead(conn, a.lead_id)
    if not lead:
        sys.exit(f"error: lead #{a.lead_id} not found")

    slug = slugify(lead["name"], lead["id"])
    variants_dir = s.output_dir / slug / "variants"
    mapping_file = variants_dir / "mapping.json"
    if not mapping_file.exists():
        sys.exit(f"error: no mapping found at {mapping_file}. Run `agency compare {a.lead_id}` first.")

    mapping = get_or_create_mapping(variants_dir)
    scores = get_design_scores(conn, a.lead_id)

    path_names = {"a": "Path A (impeccable)", "b": "Path B (open-design)"}
    print(f"Blind Mapping Revealed for Lead #{a.lead_id} ({lead['name']}):")
    print(f"  Site 1 -> {path_names.get(mapping['site_1'], mapping['site_1'])}")
    print(f"  Site 2 -> {path_names.get(mapping['site_2'], mapping['site_2'])}")

    if scores:
        print("\nRecorded Scores:")
        for sc in scores:
            path = path_names.get(sc["variant"], sc["variant"])
            print(f"  - [{path}] {sc['criterion']}: {sc['score']}/5 (by {sc['reviewer']})")


def cmd_compare_report(a):
    from agency.sitegen.compare import compute_ab_report, export_report_to_csv

    s = get_settings()
    conn = _conn()
    report = compute_ab_report(conn, s.output_dir)

    print("=" * 65)
    print("A/B DESIGN PATH COMPARISON REPORT")
    print("=" * 65)

    print("\n--- Summary ---")
    print(f"Total Leads Evaluated: {len(report['lead_results'])}")
    print(f"Path A Wins: {report['a_wins']}")
    print(f"Path B Wins: {report['b_wins']}")
    print(f"Ties: {report['ties']}")

    print("\n--- Criteria Averages (1-5) ---")
    print(f"{'Criterion':<20} | {'Path A (impeccable)':<20} | {'Path B (open-design)':<20}")
    print("-" * 65)
    for crit, avgs in report["criterion_averages"].items():
        print(f"{crit:<20} | {avgs['a']:<20.2f} | {avgs['b']:<20.2f}")

    print("\n--- Build & Quality Metrics ---")
    stats = report["build_stats"]
    print(f"QA First-Try Pass Rate:  Path A: {stats['a']['qa_first_try_pass_rate'] * 100:.1f}%  |  Path B: {stats['b']['qa_first_try_pass_rate'] * 100:.1f}%")
    print(f"Avg Duration (sec):       Path A: {stats['a']['avg_duration_seconds']:.1f}s   |  Path B: {stats['b']['avg_duration_seconds']:.1f}s")
    print(f"Avg Iterations:           Path A: {stats['a']['avg_iterations']:.1f}     |  Path B: {stats['b']['avg_iterations']:.1f}")

    print("\n--- Final Verdict ---")
    print(f">> {report['verdict']} <<\n")

    if a.output:
        cnt = export_report_to_csv(report, a.output)
        print(f"Exported {cnt} lead comparison rows to {a.output}")





def main(argv=None):
    from agency.logging_config import setup_logging

    setup_logging()
    p = argparse.ArgumentParser(prog="agency")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db").set_defaults(fn=cmd_init_db)

    f = sub.add_parser("find-leads")
    f.add_argument("--source", choices=["places", "osm", "geoapify"], default="places")
    f.add_argument("--query", required=True, help="places: free text like 'plumber'; osm: restaurant|pharmacy|plumber|electrician|hairdresser|hardware")
    f.add_argument("--city", required=True, help="places: 'Austin, TX'; osm: exact area name like 'Austin'")
    f.add_argument("--limit", type=int, default=40)
    f.add_argument("--export-csv", default=None, help="custom CSV export destination (defaults to LEADS_CSV_PATH or leads.csv)")
    f.set_defaults(fn=cmd_find_leads)

    v = sub.add_parser("verify", help="normalize, qualify, and scrub new leads")
    v.add_argument("--limit", type=int, default=500)
    v.set_defaults(fn=cmd_verify)

    al = sub.add_parser("add-lead")
    al.add_argument("--name", required=True)
    al.add_argument("--phone", required=True)
    al.add_argument("--lat", type=float, required=True)
    al.add_argument("--lng", type=float, required=True)
    al.add_argument("--category", default="local business")
    al.add_argument("--city", default=None)
    al.add_argument("--state", default=None)
    al.add_argument("--address", default=None)
    al.set_defaults(fn=cmd_add_lead)

    pv = sub.add_parser("preview")
    pv.add_argument("--lead-id", type=int, required=True)
    pv.add_argument("--notes", default="")
    pv.set_defaults(fn=cmd_preview)

    d = sub.add_parser("demo-site")
    d.add_argument("--theme", choices=["food", "health", "trades", "retail"], default="trades")
    d.set_defaults(fn=cmd_demo_site)

    ic = sub.add_parser("import-csv", help="import leads from any CSV (flexible column names)")
    ic.add_argument("--file", required=True)
    ic.add_argument("--lat", type=float, default=None, help="default latitude for rows without coordinates (city center is fine)")
    ic.add_argument("--lng", type=float, default=None)
    ic.add_argument("--city", default=None)
    ic.add_argument("--state", default=None, help="two-letter state code")
    ic.add_argument("--source-label", default="csv")
    ic.set_defaults(fn=cmd_import_csv)

    qs = sub.add_parser("qa-site", help="design detector + mobile screenshot for output/<slug>")
    qs.add_argument("--slug", required=True)
    qs.set_defaults(fn=cmd_qa_site)

    dl = sub.add_parser("dial", help="dry-run by default; --live needs LIVE_DIALING_ENABLED and LEGAL_REVIEW_DONE")
    dl.add_argument("--lead-id", type=int, required=True)
    dl.add_argument("--live", action="store_true")
    dl.set_defaults(fn=cmd_dial)

    dn = sub.add_parser("dnc-add")
    dn.add_argument("--phone", required=True)
    dn.add_argument("--reason", default="manual")
    dn.set_defaults(fn=cmd_dnc_add)

    sub.add_parser("telegram-bot").set_defaults(fn=cmd_bot)

    sub.add_parser("dashboard", help="display business metrics, leads, call cap, and gate logs").set_defaults(fn=cmd_dashboard)

    exp = sub.add_parser("export-csv", help="export leads, calls, clients, or gate logs to CSV")
    exp.add_argument("--table", default="all", help="table name (leads, calls, clients, gate_log, dnc, legal_reviews, or all)")
    exp.add_argument("--output", required=True, help="output directory (if table=all) or file path (if single table)")
    exp.set_defaults(fn=cmd_export_csv)

    lr = sub.add_parser("record-legal-review", help="record TCPA compliance attorney review in audit log")
    lr.add_argument("--attorney", required=True, help="attorney name")
    lr.add_argument("--firm", default="", help="law firm name")
    lr.add_argument("--notes", default="", help="notes or scope of review")
    lr.set_defaults(fn=cmd_record_legal_review)

    en = sub.add_parser("enrich", help="enrich a lead with Google Places details, reviews, and local photos")
    en.add_argument("lead_id", type=int, help="lead id to enrich")
    en.set_defaults(fn=cmd_enrich)

    nl = sub.add_parser("note-lead", help="record call notes for a lead to increase data richness")
    nl.add_argument("lead_id", type=int, help="lead id to annotate")
    nl.add_argument("note", nargs="?", default=None, help="note text")
    nl.add_argument("--notes", dest="flag_note", default=None, help="note text (alternative to positional argument)")
    nl.set_defaults(fn=cmd_note_lead)

    bf = sub.add_parser("brief", help="generate output/<slug>/brief.json and brief.md for custom site design")
    bf.add_argument("lead_id", type=int, help="lead id to generate design brief for")
    bf.set_defaults(fn=cmd_brief)

    imp_p = sub.add_parser("import-site", help="import built site from sites-workspace/<slug>/ to output/<slug>/")
    imp_p.add_argument("slug", help="slug identifier of the site (e.g. apex-heating-air-1)")
    imp_p.add_argument("--variant", choices=["a", "b"], default=None, help="target variant folder (a or b)")
    imp_p.set_defaults(fn=cmd_import_site)

    cmp_p = sub.add_parser("compare", help="run QA and generate side-by-side A/B comparison page for a lead")
    cmp_p.add_argument("lead_id", type=int, help="lead id to compare")
    cmp_p.set_defaults(fn=cmd_compare)

    sc_p = sub.add_parser("score", help="record a 1-5 score for Site 1 or Site 2 on a specific criterion")
    sc_p.add_argument("lead_id", type=int, help="lead id")
    sc_p.add_argument("site_label", help="candidate label ('Site 1' or 'Site 2')")
    sc_p.add_argument("criterion", help="evaluation criterion (e.g. first_impression, layout_fit, etc.)")
    sc_p.add_argument("score", type=int, help="score from 1 to 5")
    sc_p.add_argument("--reviewer", default="owner", help="name or initials of reviewer")
    sc_p.set_defaults(fn=cmd_score)

    rev_p = sub.add_parser("reveal", help="reveal blind mapping between Site 1/Site 2 and Path A/Path B")
    rev_p.add_argument("lead_id", type=int, help="lead id to reveal")
    rev_p.set_defaults(fn=cmd_reveal)

    rep_p = sub.add_parser("compare-report", help="aggregate A/B comparison scores, QA pass rates, and compute verdict")
    rep_p.add_argument("--output", default=None, help="optional CSV export destination")
    rep_p.set_defaults(fn=cmd_compare_report)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
