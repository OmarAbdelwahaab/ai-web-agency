"""Gate check + LiveKit agent dispatch. Dry-run by default."""
from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from datetime import datetime

from agency.compliance.gates import can_dial
from agency.config import Settings, get_settings
from agency.db import get_lead


async def _create_dispatch(s: Settings, room: str, metadata: str) -> str:
    from livekit import api  # imported lazily so the rest of the package works without livekit installed

    lkapi = api.LiveKitAPI()  # reads LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET from env
    try:
        d = await lkapi.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(agent_name=s.livekit_agent_name, room=room, metadata=metadata)
        )
        return str(d)
    finally:
        await lkapi.aclose()


def dispatch_call(
    conn: sqlite3.Connection,
    lead_id: int,
    *,
    live: bool = False,
    settings: Settings | None = None,
    now_utc: datetime | None = None,
) -> dict:
    s = settings or get_settings()
    lead = get_lead(conn, lead_id)
    if lead is None:
        return {"dispatched": False, "reason": "lead not found"}
    gate = can_dial(conn, lead, live=live, settings=s, now_utc=now_utc)
    if not gate.allowed:
        return {"dispatched": False, "reason": gate.reason}
    room = f"call-{lead_id}-{int(time.time())}"
    metadata = json.dumps({"lead_id": lead_id, "phone_number": lead["phone_e164"], "live": True})
    if not live:
        return {"dispatched": False, "dry_run": True, "would_dispatch": {"room": room, "metadata": json.loads(metadata)}}
    if not s.sip_trunk_id:
        return {"dispatched": False, "reason": "SIP_OUTBOUND_TRUNK_ID is not set"}
    result = asyncio.run(_create_dispatch(s, room, metadata))
    return {"dispatched": True, "room": room, "result": result}
