import pytest

from agency.db import connect, init_db
from agency.leads.csv_import import import_csv


@pytest.fixture()
def conn():
    c = connect(":memory:")
    init_db(c)
    return c


def write(tmp_path, text):
    p = tmp_path / "leads.csv"
    p.write_text(text, encoding="utf-8")
    return p


def test_imports_with_flexible_columns_and_defaults(tmp_path, conn):
    p = write(tmp_path, "title,phone,website,review_rating,review_count,category\n"
                        "Joe's Plumbing,(512) 555-0101,,4.8,120,Plumber\n"
                        "Sample Cafe,512-555-0102,facebook.com/samplecafe,4.2,35,Cafe\n")
    out = import_csv(conn, p, default_lat=30.27, default_lng=-97.74, default_city="Austin", default_state="TX")
    assert out["inserted"] == 2 and out["no_coordinates"] == 0
    row = conn.execute("SELECT * FROM leads WHERE name = ?", ("Joe's Plumbing",)).fetchone()
    assert row["rating"] == 4.8 and row["rating_count"] == 120 and row["city"] == "Austin" and row["state"] == "TX"


def test_duplicates_and_missing_fields(tmp_path, conn):
    p = write(tmp_path, "name,phone\nA Shop,512-555-0100\nA Shop again,(512) 555-0100\n,512-555-0111\nNo Phone,\n")
    out = import_csv(conn, p, default_lat=30.0, default_lng=-97.0)
    assert out == {"inserted": 1, "duplicates": 1, "skipped_no_name_or_phone": 2, "no_coordinates": 0}


def test_rows_without_coordinates_are_flagged(tmp_path, conn):
    p = write(tmp_path, "name,phone\nShop,512-555-0100\n")
    assert import_csv(conn, p)["no_coordinates"] == 1
