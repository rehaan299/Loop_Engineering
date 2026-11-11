---
description: Save Loop Engineering progress mid-session (safe to /clear or compact afterwards)
---

Run a Loop Engineering checkpoint as defined in Section 7 of `${CLAUDE_PLUGIN_ROOT}/skills/loop-engineering/PROTOCOL.md`: overwrite `docs/loop/progress.md` and `docs/loop/next-steps.md`, append any new `D-###` and `TRAP-###` entries, regenerate `docs/loop/BOOT.md` within budget, then run `python3 "${CLAUDE_PLUGIN_ROOT}/skills/loop-engineering/scripts/loop.py" check` and fix any errors. Report in one line.
