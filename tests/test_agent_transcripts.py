import asyncio
import sqlite3
from unittest.mock import AsyncMock, MagicMock

import pytest

from agency.compliance import gates
from agency.config import Settings
from agency.db import connect, get_lead, init_db, insert_lead
from agency.voice import prompts
from agency.voice.agent import SalesAgent
from agency.voice.tools import CallTools


@pytest.fixture()
def env():
    conn = connect(":memory:")
    init_db(conn)
    lid = insert_lead(
        conn,
        source="places",
        source_id="p101",
        name="Apex Heating & Air",
        category="hvac",
        phone_e164="+15125550188",
        city="Austin",
        state="TX",
        timezone="America/Chicago",
        rating=4.8,
        rating_count=35,
        status="ready",
        attempts=0,
    )
    s = Settings(
        agency_name="Apex Web Studio",
        persona_name="Jordan",
        max_attempts=2,
    )
    tools = CallTools(conn, s, lid)
    tools.start_call()

    mock_ctx = MagicMock()
    mock_ctx.room = MagicMock()
    mock_ctx.room.name = "test-room"
    mock_ctx.api = MagicMock()
    mock_ctx.api.room.delete_room = AsyncMock()
    mock_ctx.shutdown = MagicMock()

    lead = get_lead(conn, lid)
    agent = SalesAgent(
        instructions=prompts.build_system_prompt(s, lead),
        call_tools=tools,
        ctx=mock_ctx,
    )
    tool_map = {t.info.name: t for t in agent.tools}
    return conn, s, lid, lead, tools, agent, tool_map, mock_ctx


# --- 1. Opening Disclosure & Compliance Tests ---

def test_opening_disclosure_rules(env):
    conn, s, lid, lead, _, _, _, _ = env
    line_normal = prompts.opening_line(s, lead)
    # Must disclose AI persona
    assert "Jordan" in line_normal
    assert "AI assistant" in line_normal
    # Must name agency
    assert "Apex Web Studio" in line_normal
    # Must state business calling
    assert "Apex Heating & Air" in line_normal
    # Must request permission to continue
    assert "Is this a good time for a quick minute?" in line_normal
    # Recording notice absent when RECORD_CALLS=false
    assert "recorded" not in line_normal

    # Recording notice present when RECORD_CALLS=true (Compliance Rule 7)
    s_rec = Settings(agency_name="Apex Web Studio", persona_name="Jordan", record_calls=True)
    line_rec = prompts.opening_line(s_rec, lead)
    assert "This call may be recorded." in line_rec


def test_system_prompt_guardrails(env):
    _, s, _, lead, _, agent, _, _ = env
    instructions = agent._instructions
    # Rule 3: Must never claim or imply human
    assert "Never claim or imply you are human" in instructions
    # Rule 6: Never invent prices
    assert "Never invent prices, discounts, guarantees" in instructions
    # Rule 7: Pre-built site claim forbidden unless preview was generated
    assert "Do NOT say a website has already been built" in instructions
    # Rule 4: No pressure after opt-out
    assert "Do not try to persuade after an opt-out" in instructions
    # Rule 6: No card numbers
    assert "Never ask for card numbers or bank details" in instructions


# --- 2. Transcript Scenario: Price Questions ---

def test_transcript_price_question(env):
    """Scenario: User asks 'How much does a website cost?'
    Agent must only quote approved packages and forbid discounts.
    """
    _, _, _, _, _, _, tool_map, _ = env
    price_info = asyncio.run(tool_map["get_price_list"]())
    assert "- Starter site (id: starter): $299" in price_info
    assert "- Standard site (id: standard): $499, then $25/month" in price_info
    assert "Discounts: not available, do not offer any" in price_info
    assert "Delivery:" in price_info
    assert "Refunds:" in price_info


# --- 3. Transcript Scenario: Opt-Out Flow ---

def test_transcript_opt_out_flow(env):
    """Scenario: User says 'Remove my number from your list and don't call again.'
    Agent must call mark_do_not_call, record DNC, add to dnc table, and hang up immediately.
    """
    conn, s, lid, _, _, _, tool_map, mock_ctx = env
    result = asyncio.run(tool_map["mark_do_not_call"](reason="said remove my number"))
    assert result == "recorded"

    # Verify DNC in database
    assert gates.is_dnc(conn, "+15125550188")
    lead_row = get_lead(conn, lid)
    assert lead_row["status"] == "dnc"

    # Verify call outcome logged
    call_row = conn.execute("SELECT * FROM calls WHERE lead_id = ?", (lid,)).fetchone()
    assert call_row["outcome"] == "dnc"
    assert "remove my number" in call_row["summary"]

    # Verify hangup invoked
    mock_ctx.api.room.delete_room.assert_awaited_once()

    # Verify compliance gate now strictly blocks any future dialing attempts
    assert not gates.can_dial(conn, lead_row, settings=s).allowed


# --- 4. Transcript Scenario: Voicemail / Answering Machine Flow ---

def test_transcript_voicemail_flow_within_attempts(env):
    """Scenario: Agent reaches voicemail greeting.
    Agent must NOT leave a message, call detected_answering_machine, hang up,
    and leave lead 'ready' if attempts < max_attempts.
    """
    conn, _, lid, _, _, _, tool_map, mock_ctx = env
    result = asyncio.run(tool_map["detected_answering_machine"]())
    assert result == "recorded"

    lead_row = get_lead(conn, lid)
    # Attempt 1 of 2 -> remains ready for next window retry
    assert lead_row["status"] == "ready"

    # Hangup invoked
    mock_ctx.api.room.delete_room.assert_awaited_once()


def test_transcript_voicemail_flow_exceeding_attempts(env):
    """Scenario: Voicemail reached when lead has already reached max_attempts.
    Status transitions to 'voicemail' instead of 'ready'.
    """
    conn, s, lid, _, _, _, tool_map, mock_ctx = env
    # Simulate second attempt
    conn.execute("UPDATE leads SET attempts = 2 WHERE id = ?", (lid,))
    conn.commit()

    asyncio.run(tool_map["detected_answering_machine"]())
    lead_row = get_lead(conn, lid)
    assert lead_row["status"] == "voicemail"


# --- 5. Transcript Scenario: Callback Flow ---

def test_transcript_callback_flow(env):
    """Scenario: User says 'I'm with a client right now. Call me back Friday at 10 AM.'
    Agent invokes schedule_callback with wording, records callback outcome.
    """
    conn, _, lid, _, _, _, tool_map, _ = env
    result = asyncio.run(tool_map["schedule_callback"](when_text="Friday at 10 AM"))
    assert result == "recorded"

    lead_row = get_lead(conn, lid)
    assert lead_row["status"] == "callback"
    assert lead_row["callback_at"] == "Friday at 10 AM"

    call_row = conn.execute("SELECT * FROM calls WHERE lead_id = ?", (lid,)).fetchone()
    assert call_row["outcome"] == "callback"
    assert "Friday at 10 AM" in call_row["summary"]


# --- 6. Transcript Scenario: Notes Saving ---

def test_transcript_save_facts(env):
    """Scenario: User shares facts: 'We specialize in heat pump replacements and AC tuneups.'
    Agent saves facts to the lead record.
    """
    conn, _, lid, _, _, _, tool_map, _ = env
    res = asyncio.run(tool_map["save_notes"](notes="Specializes in heat pumps and AC tuneups. Open 24/7."))
    assert res == "saved"

    lead_row = get_lead(conn, lid)
    assert "heat pumps" in lead_row["notes"]


# --- 7. Transcript Scenario: Verbal Yes / Deal Flow ---

def test_transcript_create_deal(env):
    """Scenario: User agrees to starter package: 'Yes let's do the starter site, my email is admin@apexheat.com'
    Agent calls create_deal, which handles deal pipeline, creates client row, and generates payment link.
    """
    conn, _, lid, _, _, _, tool_map, _ = env
    # Save a note first
    asyncio.run(tool_map["save_notes"](notes="Emergency heating repair"))

    deal_msg = asyncio.run(tool_map["create_deal"](package_id="starter", contact_email="admin@apexheat.com"))
    assert "deal created" in deal_msg

    # Verify client table
    client_row = conn.execute("SELECT * FROM clients WHERE lead_id = ?", (lid,)).fetchone()
    assert client_row is not None
    assert client_row["package_id"] == "starter"
    assert client_row["contact_email"] == "admin@apexheat.com"
    assert client_row["status"] == "awaiting_review"
    assert client_row["site_slug"] is not None

    # Verify lead status updated to 'yes'
    lead_row = get_lead(conn, lid)
    assert lead_row["status"] == "yes"


# --- 8. Session Builder and Provider Configuration Tests ---

def test_build_session_none_providers():
    from agency.voice.agent import _build_session

    s = Settings(
        stt_provider="none",
        tts_provider="none",
        voice_llm_provider="groq",
        llm_api_key="mock_groq_key",
    )
    async def _create():
        return _build_session(s)

    session = asyncio.run(_create())
    assert session is not None


def test_build_session_openai_providers():
    from agency.voice.agent import _build_session

    s = Settings(
        stt_provider="none",
        tts_provider="none",
        voice_llm_provider="openai",
        llm_api_key="mock_openai_key",
        llm_model="gpt-4o-mini",
    )
    async def _create():
        return _build_session(s)

    session = asyncio.run(_create())
    assert session is not None


def test_build_session_unsupported_providers():
    from agency.voice.agent import _build_session

    with pytest.raises(ValueError, match="unsupported STT_PROVIDER invalid_stt"):
        _build_session(Settings(stt_provider="invalid_stt"))

    with pytest.raises(ValueError, match="unsupported VOICE_LLM_PROVIDER invalid_llm"):
        _build_session(Settings(stt_provider="none", voice_llm_provider="invalid_llm"))

    with pytest.raises(ValueError, match="unsupported TTS_PROVIDER invalid_tts"):
        _build_session(Settings(stt_provider="none", voice_llm_provider="groq", llm_api_key="k", tts_provider="invalid_tts"))

