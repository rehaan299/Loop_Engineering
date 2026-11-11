---
name: loop-engineering
description: Persistent, tiered project memory for coding agents. Use when the user says "install loop engineering", "start the session", "boot", "checkpoint", "close the session", "wrap up", or "migrate loop engineering", when a project contains docs/loop/, or when work must resume across sessions, models, or tools without re-reading the codebase.
license: MIT
metadata:
  version: "4.0.0"
  homepage: https://github.com/rehaan299/Loop_Engineering
---

# Loop Engineering

Loop Engineering keeps a project's working knowledge in `docs/loop/`: one small hot file (`BOOT.md`, at most 8,000 characters) loaded every session, and warm and cold files that hold the detail, cross-referenced by stable IDs (`D-###` decisions, `T-###` tasks, `TRAP-###` traps, `F-##` flows, `Q-###` questions). The agent reads the codebase properly once, then boots from `BOOT.md` and pulls everything else by ID only when a task needs it.

The full protocol is in `PROTOCOL.md` in this skill's directory. Read the section named below for the operation you are running; read the whole file the first time you install on a project.

## Pick the operation

| Situation | Operation | Protocol section |
|---|---|---|
| No `docs/loop/` in the project | **Install** | 2 (and 3, 4, 5) |
| `docs/loop/prompt.md` exists, no `BOOT.md` | **Migrate** from v3 | 13 |
| `docs/loop/BOOT.md` exists, new session | **Boot** | 9 |
| Mid-session save, or before compaction | **Checkpoint** | 7 |
| "close the session", "wrap up", "done for today" | **Close out** | 8 |

## The CLI (optional, recommended)

`scripts/loop.py` in this skill's directory is a dependency-free Python 3.9+ CLI. Run it from the project root:

```bash
python3 <this-skill-dir>/scripts/loop.py init        # scaffold docs/loop/ and the AGENTS.md block
python3 <this-skill-dir>/scripts/loop.py status      # dashboard: session, drift, budgets, health
python3 <this-skill-dir>/scripts/loop.py boot        # BOOT.md plus a git drift report
python3 <this-skill-dir>/scripts/loop.py next TRAP   # next free ID for a prefix
python3 <this-skill-dir>/scripts/loop.py check       # lint: budget, IDs, secrets, stale paths
python3 <this-skill-dir>/scripts/loop.py stamp --agent "<model name>"   # record the closeout
python3 <this-skill-dir>/scripts/loop.py migrate     # scaffold the v3 to v4 upgrade
```

If a global `loop` command or `.loop/loop.py` exists, it is the same tool.

## Non-negotiables

1. **Boot small.** At session start read only `BOOT.md`. Do not crawl the codebase or preload the other loop files.
2. **Pull by ID.** Search `docs/loop/` for an ID or heading and read only that section.
3. **Verify, then claim.** Record the test command and its observed result in `progress.md`.
4. **Record as you go.** Add `D-###` and `TRAP-###` entries the moment a decision or trap appears.
5. **Close out completely**, regenerate `BOOT.md` last and within budget, stamp `loop.json`, and make `loop check` pass.
6. **Never write secret values** into any loop file.
