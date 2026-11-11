---
description: Close the Loop Engineering session (verify, rewrite docs, distill BOOT.md, stamp)
---

Close this Loop Engineering session.

Follow Section 8 of `${CLAUDE_PLUGIN_ROOT}/skills/loop-engineering/PROTOCOL.md` completely and in order: run the tests and record evidence, update every loop file, regenerate `docs/loop/BOOT.md` last within its 8,000 character budget, then run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/loop-engineering/scripts/loop.py" stamp --agent "<your model name>"
python3 "${CLAUDE_PLUGIN_ROOT}/skills/loop-engineering/scripts/loop.py" check
```

Fix every error `check` reports, answer the self-check questions, and finish with the one-paragraph plain-English summary.
