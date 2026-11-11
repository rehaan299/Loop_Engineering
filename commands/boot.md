---
description: Start a Loop Engineering session (boot from BOOT.md, check drift, report)
---

Start a Loop Engineering session.

1. If `docs/loop/BOOT.md` is not already in your context from the session-start hook, run `python3 "${CLAUDE_PLUGIN_ROOT}/skills/loop-engineering/scripts/loop.py" boot` and read its output. If `docs/loop/` holds a v3 install (`prompt.md` and no `BOOT.md`), run `/loop-engineering:migrate` instead.
2. Follow Section 9 of `${CLAUDE_PLUGIN_ROOT}/skills/loop-engineering/PROTOCOL.md`: read nothing else from `docs/loop/` yet, inspect any drift the report shows, then output the boot report exactly as specified and wait for the operator.
