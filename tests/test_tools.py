import pytest

from agency.compliance.gates import is_dnc
from agency.config import Settings
from agency.db import connect, get_lead, init_db, insert_lead
from agency.voice.prompts import build_system_prompt, format_price_list, load_pricing, opening_line
from agency.voice.tools import CallTools


@pytest.fixture()
def setup():
    conn = connect(":memory:")
    init_db(conn)
    lid = insert_lead(conn, source="t", source_id="1", name="Test Shop", phone_e164="+15125550100", status="ready",
                      timezone="America/Chicago", city="Austin", attempts=0)
    s = Settings()
    tools = CallTools(conn, s, lid)
    tools.start_call()
    return conn, s, lid, tools


def test_opening_discloses_ai_and_agency(setup):
    conn, s, lid, _ = setup
    line = opening_line(s, get_lead(conn, lid))
    assert "AI assistant" in line and s.agency_name in line and "Test Shop" in line


def test_do_not_call_blocks_future_calls(setup):
    conn, _, lid, tools = setup
    tools.mark_do_not_call("said stop")
    assert is_dnc(conn, "+15125550100")
    assert get_lead(conn, lid)["status"] == "dnc"


def test_voicemail_retries_until_limit(setup):
    conn, s, lid, tools = setup
    tools.record_outcome("voicemail", "machine")
    assert get_lead(conn, lid)["status"] == "ready"  # 1 attempt < limit


def test_invalid_outcome_rejected(setup):
    assert "invalid" in setup[3].record_outcome("maybe")


def test_price_list_comes_from_yaml(setup):
    _, s, _, tools = setup
    text = tools.get_price_list()
    assert "Starter site" in text and "do not offer any" in text


def test_prompt_forbids_claiming_prebuilt_site(setup):
    conn, s, lid, _ = setup
    prompt = build_system_prompt(s, get_lead(conn, lid), preview_ready=False)
    assert "Do NOT say a website has already been built" in prompt
    assert "Never claim or imply you are human" in prompt
