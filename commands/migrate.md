---
description: Upgrade a Loop Engineering v3 install (prompt.md) to v4 (BOOT.md, traps.md, IDs)
---

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/skills/loop-engineering/scripts/loop.py" migrate` from the project root.
2. Follow Section 13 of `${CLAUDE_PLUGIN_ROOT}/skills/loop-engineering/PROTOCOL.md` to do the content work: move traps into `traps.md`, normalize decision headings, assign `T-###` and `F-##` IDs, and distill `BOOT.md`.
3. Run `loop.py check`, fix everything it reports, and give the one-line migration report.
