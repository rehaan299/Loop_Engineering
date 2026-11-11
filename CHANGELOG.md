# Changelog

## 4.0.0 (2026-11-11)

### Added
- Tiered context: `BOOT.md` is the only file loaded every session (8,000 character cap); warm and cold files are read by section or ID.
- Stable IDs across all docs: `D-###` decisions, `T-###` tasks, `TRAP-###` traps, `F-##` flows, `Q-###` open questions.
- `traps.md`, split out of `progress.md`, with headlines surfaced in `BOOT.md`.
- `loop.json` with session number, last closeout, agent, and git anchor.
- Drift detection: boot reports commits and uncommitted changes since the last closeout.
- Checkpoint operation for mid-session saves before `/clear` or compaction.
- Verification-first closeout: tests run and evidence recorded before the docs are rewritten.
- Managed `AGENTS.md` block and `CLAUDE.md` import so every agent on the team finds the loop.
- `loop` CLI (Python 3.9+, standard library only): `init`, `status`, `boot`, `check`, `next`, `stamp`, `migrate`, `hook`.
- Claude Code plugin and marketplace with six commands and a SessionStart hook that loads `BOOT.md` on startup, after `/clear`, and after compaction.
- Agent Skill (`skills/loop-engineering/`) for any tool supporting the Agent Skills standard.
- One-line installer (`install.sh`), test suite, and CI.
- Secret scanning and stale-path detection in `loop check`.

### Changed
- `prompt.md` is replaced by `BOOT.md`. `loop migrate` scaffolds the upgrade; existing files are kept.
- Decision headings use `### D-NNN: Title`. Existing numbers are preserved.
- Protocol file renamed from `LOOP_ENGINEERING.MD` to `LOOP_ENGINEERING.md`.

## 3.0

- Seven-file `docs/loop/` layout, install, boot, and closeout protocol.
