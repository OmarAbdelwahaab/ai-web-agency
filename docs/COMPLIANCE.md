# Compliance checklist

Not legal advice. Book a short consult with a TCPA attorney before turning on live dialing.

## Why this matters
- The FCC ruled in 2024 that AI-generated human-sounding voices count as an artificial or prerecorded voice under the TCPA, which generally requires the recipient's prior express consent. Telemarketing needs prior express written consent.
- The law protects the person called, so it applies even if you operate from outside the US.
- The national Do Not Call registry covers personal numbers, not business-to-business calls, but that does not remove the AI-voice consent question, and many small owners answer on mobile phones.
- States have their own registries, hours, and recording-consent rules. Calling hours are 8 AM to 9 PM in the recipient's local time at most; some states are stricter.
- The FCC has proposed requiring AI disclosure at the start of calls. Do it anyway.

## Must-have before the first real call
- [ ] Attorney reviewed the call flow, lead sources, and consent approach.
- [ ] Decision recorded: which leads are eligible (opted in, inbound, or otherwise cleared by counsel).
- [ ] State-by-state calling windows and recording rules entered in `compliance/gates.py` (`STATE_WINDOWS`).
- [ ] Internal DNC table loaded and enforced; opt-out takes effect immediately.
- [ ] Owned US number registered with the SIP provider (business verification, caller-ID registration).
- [ ] AI disclosure + agency name + purpose in the first sentence (`voice/prompts.py`).
- [ ] Recording disclosure if recording is enabled.
- [ ] No payment details taken on calls; payment via link only.
- [ ] Refund/cancellation terms written in `pricing.yaml`.
- [ ] Audit log reviewed (gate decisions, outcomes, opt-outs).

## What the code enforces
`can_dial()` blocks: invalid number, DNC match, outside local window, attempts exceeded, wrong lead status, live dialing disabled, legal sign-off missing.
