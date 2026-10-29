---
description: Run the whole pipeline on one test lead without dialing anyone
---

1. Make sure `.env` has `LIVE_DIALING_ENABLED=false`.
2. Run `agency init-db`, then insert a fake lead with the owner's own phone number as the test number.
3. Run `agency preview --lead-id <id>` and open the generated site in `output/`.
4. Run `agency dial --lead-id <id>` (dry-run) and confirm the gate decision is logged.
5. Run `python -m agency.voice.agent console` and role-play as the lead. Check: AI disclosure in the first sentence, opt-out handling, no invented prices, voicemail hang-up.
6. Report any failure with the exact transcript line.
