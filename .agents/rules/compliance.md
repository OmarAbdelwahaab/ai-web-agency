# Compliance rules (always on)

These are engineering requirements, not legal advice. The owner must get a TCPA attorney's review before `LIVE_DIALING_ENABLED=true`.

1. `LIVE_DIALING_ENABLED` and `LEGAL_REVIEW_DONE` must BOTH be true for any real outbound call. Default false. Never change these defaults and never add a way around them.
2. Every call must pass `agency.compliance.gates.can_dial()` first: valid US number, not in the internal `dnc` table, inside the lead's LOCAL calling window (default 08:00-21:00, stricter per-state overrides allowed), attempt limit not exceeded.
3. The agent's first words must disclose it is an AI assistant, name the agency, and state the purpose. It must never claim or imply it is human.
4. If the person says stop, remove me, don't call, not interested in being called again: call `mark_do_not_call` immediately, apologize briefly, end the call. No persuasion after an opt-out.
5. Voicemail or answering machine: hang up. Do not leave AI-generated messages.
6. Never collect card numbers or bank details on the call. Payment happens through a link sent after a verbal yes.
7. If `RECORD_CALLS=true`, the opening must also say the call may be recorded.
8. Do not spoof caller ID. Use only a number the agency owns and that accepts return calls.
9. Never help bypass carrier or provider rules (account rotation, number rotation to dodge blocking, etc.).
10. Keep an audit trail: gate decisions, call outcomes, opt-outs, consent evidence.
