"""LiveKit voice agent worker.

IMPORTANT: LiveKit Agents changes quickly. Before editing, read the current docs
(https://docs.livekit.io/llms.txt, telephony/making-calls/outbound-calls) and pin versions in pyproject.toml.
Signatures below follow the docs as of late 2026 and must be verified against the installed version.

Run:  python -m agency.voice.agent console   (talk to it in the terminal, no phone)
      python -m agency.voice.agent dev       (worker waits for dispatches from `agency dial --live`)
"""
from __future__ import annotations

import json
import logging

from livekit import api
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, RunContext, cli, function_tool

from agency.compliance.gates import can_dial
from agency.config import get_settings
from agency.db import connect, get_lead, init_db, insert_lead
from agency.voice.prompts import build_system_prompt, opening_line
from agency.voice.tools import CallTools

log = logging.getLogger("agency.voice")
server = AgentServer()


def _build_session(s) -> AgentSession:
    """Providers are chosen via env so you can swap free tiers. TODO(verify): plugin class names/args."""
    from livekit.plugins import silero

    if s.stt_provider == "deepgram":
        from livekit.plugins import deepgram
        stt = deepgram.STT(model="nova-3", language="en-US")
    else:
        raise ValueError(f"unsupported STT_PROVIDER {s.stt_provider}")

    if s.voice_llm_provider == "groq":
        from livekit.plugins import groq
        llm = groq.LLM(model=s.llm_model)
    else:
        raise ValueError(f"unsupported VOICE_LLM_PROVIDER {s.voice_llm_provider}")

    if s.tts_provider == "cartesia":
        from livekit.plugins import cartesia
        tts = cartesia.TTS()
    else:
        raise ValueError(f"unsupported TTS_PROVIDER {s.tts_provider}")

    return AgentSession(stt=stt, llm=llm, tts=tts, vad=silero.VAD.load())


class SalesAgent(Agent):
    def __init__(self, *, instructions: str, tools: CallTools, ctx: JobContext):
        super().__init__(instructions=instructions)
        self._tools, self._ctx = tools, ctx

    async def _hangup(self) -> None:
        try:
            await self._ctx.api.room.delete_room(api.DeleteRoomRequest(room=self._ctx.room.name))
        except Exception:  # room may already be gone
            log.exception("hangup failed")

    @function_tool()
    async def get_price_list(self, context: RunContext) -> str:
        """Return the only approved packages, prices, delivery promise, and refund/discount rules."""
        return self._tools.get_price_list()

    @function_tool()
    async def save_notes(self, context: RunContext, notes: str) -> str:
        """Save facts the person told you (services, hours, email, preferences) for building their site."""
        return self._tools.save_notes(notes)

    @function_tool()
    async def schedule_callback(self, context: RunContext, when_text: str) -> str:
        """The person asked to be called later. Pass their wording, e.g. 'tomorrow afternoon'. Then end the call politely."""
        out = self._tools.schedule_callback(when_text)
        return out

    @function_tool()
    async def record_outcome(self, context: RunContext, outcome: str, summary: str) -> str:
        """Record the call result. outcome is one of: yes, no, callback, voicemail, wrong_number."""
        return self._tools.record_outcome(outcome, summary)

    @function_tool()
    async def mark_do_not_call(self, context: RunContext, reason: str) -> str:
        """The person asked not to be called again. Call this immediately, apologize briefly, then end the call."""
        out = self._tools.mark_do_not_call(reason)
        await self._hangup()
        return out

    @function_tool()
    async def detected_answering_machine(self, context: RunContext) -> str:
        """Call this if you reached voicemail or an automated greeting. Do not leave a message."""
        out = self._tools.record_outcome("voicemail", "answering machine")
        await self._hangup()
        return out

    @function_tool()
    async def create_deal(self, context: RunContext, package_id: str, contact_email: str) -> str:
        """The person agreed to a package. Pass the package id from get_price_list and their email address."""
        return self._tools.create_deal(package_id, contact_email)

    @function_tool()
    async def end_call(self, context: RunContext) -> str:
        """End the call after a polite goodbye."""
        await self._hangup()
        return "call ended"


def _test_lead(conn):
    """Console mode: insert a throwaway lead so the agent has context without a real number."""
    lid = insert_lead(conn, source="console", source_id="test", name="Sample Plumbing Co", category="plumber",
                      phone_e164="+15125550100", city="Austin", state="TX", timezone="America/Chicago",
                      rating=4.7, rating_count=82, status="ready")
    return get_lead(conn, lid)


@server.rtc_session(agent_name=get_settings().livekit_agent_name)
async def entrypoint(ctx: JobContext):
    s = get_settings()
    if s.record_calls:
        raise NotImplementedError("Recording is not implemented yet. Keep RECORD_CALLS=false until it is built and disclosed.")

    await ctx.connect()
    meta = json.loads(ctx.job.metadata) if ctx.job.metadata else None
    conn = connect(s.db_path if meta else ":memory:")
    init_db(conn)

    if meta:
        lead = get_lead(conn, meta["lead_id"])
        gate = can_dial(conn, lead, live=True)  # defense in depth: re-check at dial time
        if not gate.allowed:
            log.warning("blocked at dial time: %s", gate.reason)
            return
    else:
        lead = _test_lead(conn)
        gate = None

    tools = CallTools(conn, s, lead["id"])
    tools.start_call(gate.reason if gate else "console-test")

    if meta:
        identity = f"lead-{lead['id']}"
        try:
            await ctx.api.sip.create_sip_participant(
                api.CreateSIPParticipantRequest(
                    room_name=ctx.room.name,
                    sip_trunk_id=s.sip_trunk_id,
                    sip_call_to=meta["phone_number"],
                    participant_identity=identity,
                    wait_until_answered=True,
                )
            )
        except api.TwirpError as e:
            log.error("SIP error %s %s", e.metadata.get("sip_status_code"), e.metadata.get("sip_status"))
            tools.record_outcome("no", f"call failed: {e.metadata.get('sip_status')}")
            ctx.shutdown()
            return

    session = _build_session(s)
    agent = SalesAgent(instructions=build_system_prompt(s, lead), tools=tools, ctx=ctx)
    await session.start(agent=agent, room=ctx.room)
    await session.say(opening_line(s, lead), allow_interruptions=False)  # disclosure is always said verbatim


if __name__ == "__main__":
    cli.run_app(server)
