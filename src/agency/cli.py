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


def cmd_init_db(a):
    _conn()
    print("database ready")


def cmd_find_leads(a):
    conn = _conn()
    if a.source == "places":
        from agency.leads import places

        found = places.search(f"{a.query} in {a.city}", limit=a.limit)
        print(f"{len(found)} places found, {places.save(conn, found, category=a.query)} new candidates saved")
    else:
        from agency.leads import osm

        found = osm.search(a.query, a.city)
        print(f"{len(found)} elements found, {osm.save(conn, found, a.query)} new candidates saved")


def cmd_verify(a):
    from agency.leads.verify import scrub_all, verify_all

    conn = _conn()
    print("verify:", verify_all(conn, a.limit))
    print("scrub:", scrub_all(conn))


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

    print(import_csv(_conn(), a.file, default_lat=a.lat, default_lng=a.lng, default_city=a.city,
                     default_state=a.state, source=a.source_label))


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


def main(argv=None):
    from agency.logging_config import setup_logging

    setup_logging()
    p = argparse.ArgumentParser(prog="agency")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db").set_defaults(fn=cmd_init_db)

    f = sub.add_parser("find-leads")
    f.add_argument("--source", choices=["places", "osm"], default="places")
    f.add_argument("--query", required=True, help="places: free text like 'plumber'; osm: restaurant|pharmacy|plumber|electrician|hairdresser|hardware")
    f.add_argument("--city", required=True, help="places: 'Austin, TX'; osm: exact area name like 'Austin'")
    f.add_argument("--limit", type=int, default=40)
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

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
