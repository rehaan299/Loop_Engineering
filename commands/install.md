---
description: Install Loop Engineering on this project (one deep read, then tiered context docs)
argument-hint: "[--local to keep docs/loop/ out of git]"
---

Install Loop Engineering v4 on this project.

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/skills/loop-engineering/scripts/loop.py" init --claude $ARGUMENTS` from the project root to scaffold `docs/loop/`, `loop.json`, `PROTOCOL.md`, and the AGENTS.md / CLAUDE.md integration.
2. Read `${CLAUDE_PLUGIN_ROOT}/skills/loop-engineering/PROTOCOL.md` in full.
3. Follow Section 2 of the protocol exactly, starting with the four questions in Section 2.1. Use the Explore subagent for the broad codebase reading in Section 2.2 so your own context stays clean for synthesis.
4. Fill every file marked `loop:unfilled`, write `BOOT.md` last, run `loop.py stamp --agent "<your model name>"`, then `loop.py check`, and fix everything it reports before giving the installed report.
