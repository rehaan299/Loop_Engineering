#!/usr/bin/env python3
"""
loop: the Loop Engineering CLI.

A single file, Python 3.9+, standard library only. It scaffolds, inspects,
lints, and stamps the docs/loop/ context layer described in PROTOCOL.md.

    loop init [--local] [--claude]   scaffold docs/loop/ and agent-file integration
    loop status                      dashboard
    loop boot                        print BOOT.md plus a drift report
    loop check [--strict]            lint the loop docs
    loop next PREFIX                 next free ID for D, T, TRAP, F, or Q
    loop stamp [--agent NAME]        record a closeout in loop.json
    loop migrate                     upgrade a v3 install to v4
    loop hook session-start          Claude Code SessionStart hook (JSON on stdout)
    loop version

Global option: --root PATH (default: the git root of the current directory).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

VERSION = "4.0.0"
LOOP_VERSION = "4.0"
DOCS_DIR = Path("docs") / "loop"
BOOT_BUDGET = 8000
HOOK_CONTEXT_CAP = 9500  # Claude Code caps additionalContext at 10,000 characters
UNFILLED = "<!-- loop:unfilled -->"

FILES = [
    ("BOOT.md", "hot"),
    ("progress.md", "warm"),
    ("codebase-map.md", "warm"),
    ("next-steps.md", "warm"),
    ("decisions.md", "cold"),
    ("traps.md", "cold"),
    ("system-design.md", "cold"),
    ("how-it-works.md", "cold"),
]

ID_HOME = {
    "D": "decisions.md",
    "T": "next-steps.md",
    "TRAP": "traps.md",
    "F": "codebase-map.md",
    "Q": "progress.md",
}
ID_WIDTH = {"D": 3, "T": 3, "TRAP": 3, "F": 2, "Q": 3}
DEF_RE = re.compile(r"^#{2,4}\s+(TRAP|D|T|F|Q)-(\d+)\b", re.MULTILINE)
REF_RE = re.compile(r"(?<![A-Za-z0-9_-])(TRAP|D|T|F|Q)-(\d{2,4})(?![A-Za-z0-9_])")

SECRET_PATTERNS = [
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private key block", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
    ("Anthropic key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("OpenAI-style key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{32,}")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("credentials in URL", re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s:/@]+:[^\s@/]{3,}@[^\s]+", re.IGNORECASE)),
    ("assigned secret", re.compile(
        r"(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token)\b\s*[:=]\s*['\"][^'\"\s]{8,}['\"]")),
]

AGENTS_BLOCK = """<!-- loop-engineering:start -->
## Loop Engineering
This project keeps persistent agent context in `docs/loop/`.
At session start, read `docs/loop/BOOT.md` (and nothing else from docs/loop/ until a task needs it).
Look up IDs (D-###, T-###, TRAP-###, F-##, Q-###) by searching docs/loop/.
At session end, when the operator says "close the session", follow the closeout in docs/loop/PROTOCOL.md or the loop-engineering skill.
<!-- loop-engineering:end -->"""
AGENTS_BLOCK_RE = re.compile(r"<!-- loop-engineering:start -->.*?<!-- loop-engineering:end -->", re.DOTALL)

# --------------------------------------------------------------------------- terminal UI

def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return sys.stdout.isatty()


COLOR = _supports_color()


def c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if COLOR else text


def bold(t: str) -> str: return c(t, "1")
def dim(t: str) -> str: return c(t, "2")
def green(t: str) -> str: return c(t, "32")
def yellow(t: str) -> str: return c(t, "33")
def red(t: str) -> str: return c(t, "31")
def cyan(t: str) -> str: return c(t, "36")
def magenta(t: str) -> str: return c(t, "35")


def bar(used: int, total: int, width: int = 24) -> str:
    frac = 0.0 if total <= 0 else min(used / total, 1.0)
    filled = int(round(frac * width))
    color = green if frac < 0.85 else (yellow if frac <= 1.0 else red)
    if used > total:
        color = red
    return color("█" * filled) + dim("░" * (width - filled))


def panel(title: str, rows: list[tuple[str, str]]) -> str:
    label_w = max((len(k) for k, _ in rows), default=0)
    lines = [f"  {cyan('◆')} {bold(title)}"]
    for k, v in rows:
        lines.append(f"    {dim(k.ljust(label_w))}  {v}")
    return "\n".join(lines)


BANNER = r"""
   ╭─────────────────────────────────────────────╮
   │   ⟳  L O O P   E N G I N E E R I N G   v4   │
   │      read once · boot small · pull by ID    │
   ╰─────────────────────────────────────────────╯"""

# --------------------------------------------------------------------------- helpers

def run_git(root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def find_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env).resolve()
    cwd = Path.cwd()
    top = run_git(cwd, "rev-parse", "--show-toplevel")
    return Path(top).resolve() if top else cwd.resolve()


def docs(root: Path) -> Path:
    return root / DOCS_DIR


def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def load_state(root: Path) -> dict:
    p = docs(root) / "loop.json"
    if not p.exists():
        return {}
    try:
        return json.loads(read(p))
    except json.JSONDecodeError:
        return {"_invalid": True}


def save_state(root: Path, state: dict) -> None:
    p = docs(root) / "loop.json"
    p.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def protocol_source() -> Path | None:
    here = Path(__file__).resolve().parent
    for cand in (here.parent / "PROTOCOL.md", here / "PROTOCOL.md",
                 here.parent / "LOOP_ENGINEERING.md", here / "LOOP_ENGINEERING.md"):
        if cand.exists():
            return cand
    return None


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def project_name(root: Path) -> str:
    return root.name


def drift(root: Path, anchor: str | None) -> dict:
    info = {"git": False, "anchor": anchor, "commits": [], "stat": "", "dirty": 0, "anchor_missing": False}
    if run_git(root, "rev-parse", "--git-dir") is None:
        return info
    info["git"] = True
    status = run_git(root, "status", "--porcelain")
    info["dirty"] = len([l for l in (status or "").splitlines() if l.strip() and DOCS_DIR.as_posix() not in l])
    if not anchor:
        return info
    if run_git(root, "cat-file", "-e", f"{anchor}^{{commit}}") is None:
        info["anchor_missing"] = True
        return info
    log = run_git(root, "log", "--oneline", f"{anchor}..HEAD")
    info["commits"] = [l for l in (log or "").splitlines() if l.strip()]
    info["stat"] = run_git(root, "diff", "--stat", f"{anchor}..HEAD", "--", ".", f":(exclude){DOCS_DIR.as_posix()}") or ""
    return info


def drift_text(d: dict, max_commits: int = 15) -> str:
    if not d["git"]:
        return "Drift: not a git repository, drift detection unavailable."
    if not d["anchor"]:
        return "Drift: no git_anchor in loop.json yet (run `loop stamp` at closeout)."
    if d["anchor_missing"]:
        return f"Drift: anchor {d['anchor']} is not in this clone (shallow clone or rewritten history). Treat the map as possibly stale."
    lines = []
    n = len(d["commits"])
    if n == 0:
        lines.append(f"Drift: none. HEAD matches anchor {d['anchor']}.")
    else:
        lines.append(f"Drift: {n} commit(s) since anchor {d['anchor']}. Check whether they touch mapped areas:")
        lines += [f"  {cmt}" for cmt in d["commits"][:max_commits]]
        if n > max_commits:
            lines.append(f"  ... and {n - max_commits} more")
        if d["stat"]:
            stat_lines = d["stat"].splitlines()
            lines.append("Changed files since anchor (summary):")
            lines += [f"  {s.strip()}" for s in stat_lines[-12:]]
    if d["dirty"]:
        lines.append(f"Working tree: {d['dirty']} uncommitted change(s) outside docs/loop/.")
    return "\n".join(lines)

# --------------------------------------------------------------------------- templates

def templates(name: str, session: int, today: str) -> dict[str, str]:
    u = UNFILLED + "\n"
    return {
        "BOOT.md": f"""{u}# BOOT: {name}

Session {session} | Updated {today} | Loop v{LOOP_VERSION} | Anchor (set at closeout)

## What this is
## Operator
## Stack and commands
## Status
## START HERE
## Traps (headlines)
## Key decisions (headlines)
## Where things are
- Schema, API surface, env vars, verified state: progress.md
- Tree, modules, flows, change-impact index: codebase-map.md
- Full task queue and blockers: next-steps.md
- Look up any ID by searching docs/loop/.

## Rules for this session
- Open source files only when about to change them, guided by codebase-map.md.
- Verify with tests before claiming anything works.
- Close with "close the session"; checkpoint with "checkpoint".
""",
        "progress.md": f"""{u}# progress.md

Project: {name} | Session: {session} | {today} | Agent:
Status:

## System summary
## Stack
## Runtime
## Schema
## Interface surface
## Integrations
## Environment variables
## Verified this session
## What's broken or incomplete
## Open questions
## Changed this session
""",
        "codebase-map.md": f"""{u}# codebase-map.md

Updated: session {session} | Anchor:

## Tree
## Entry points
## Modules
## Core flows
## Change-impact index
## Dead zones (do not read)
""",
        "next-steps.md": f"""{u}# next-steps.md

Updated: session {session}

## START HERE
## Queue
## Parked
## Done this session
""",
        "decisions.md": """# decisions.md

Append-only. Each decision is a `### D-NNN: Title` heading. Never delete; supersede.
""",
        "traps.md": """# traps.md

Append-only. Each trap is a `### TRAP-NNN: Title` heading with Symptom, Cause, Avoid, Where.
""",
        "system-design.md": f"""{u}# system-design.md

## Vision
## Success criteria
## Current position
## Architecture
## Phases
## Constraints
## Session history
| # | Date | Model | Focus | Outcome |
| - | ---- | ----- | ----- | ------- |
""",
        "how-it-works.md": """# how-it-works.md

Plain English, append-only. The one file written for the human.
""",
    }

# --------------------------------------------------------------------------- commands

def ensure_agents_block(root: Path, want_claude: bool) -> list[str]:
    actions = []
    agents = root / "AGENTS.md"
    text = read(agents)
    if AGENTS_BLOCK_RE.search(text):
        new = AGENTS_BLOCK_RE.sub(AGENTS_BLOCK, text)
        if new != text:
            agents.write_text(new, encoding="utf-8")
            actions.append("updated Loop Engineering block in AGENTS.md")
    else:
        sep = "" if not text else ("\n" if text.endswith("\n") else "\n\n")
        agents.write_text(text + sep + AGENTS_BLOCK + "\n", encoding="utf-8")
        actions.append("added Loop Engineering block to AGENTS.md" if text else "created AGENTS.md")

    claude = root / "CLAUDE.md"
    ctext = read(claude)
    if claude.exists():
        if "@AGENTS.md" not in ctext and "loop-engineering:start" not in ctext:
            claude.write_text("@AGENTS.md\n\n" + ctext, encoding="utf-8")
            actions.append("added @AGENTS.md import to CLAUDE.md")
    elif want_claude:
        claude.write_text("@AGENTS.md\n", encoding="utf-8")
        actions.append("created CLAUDE.md importing AGENTS.md")
    return actions


def ensure_gitignore(root: Path) -> str | None:
    gi = root / ".gitignore"
    text = read(gi)
    if any(line.strip().rstrip("/") == DOCS_DIR.as_posix() for line in text.splitlines()):
        return None
    sep = "" if not text or text.endswith("\n") else "\n"
    gi.write_text(text + sep + "\n# Loop Engineering context docs (local agent memory)\ndocs/loop/\n", encoding="utf-8")
    return "added docs/loop/ to .gitignore"


def copy_protocol(root: Path) -> str | None:
    src = protocol_source()
    if not src:
        return None
    dst = docs(root) / "PROTOCOL.md"
    if dst.exists() and read(dst) == read(src):
        return None
    shutil.copyfile(src, dst)
    return "installed docs/loop/PROTOCOL.md"


def cmd_init(root: Path, args) -> int:
    d = docs(root)
    d.mkdir(parents=True, exist_ok=True)
    state = load_state(root)
    session = int(state.get("session", 0) or 0) or 1
    today = datetime.now().date().isoformat()
    created = []
    for fname, content in templates(project_name(root), session, today).items():
        p = d / fname
        if not p.exists():
            p.write_text(content, encoding="utf-8")
            created.append(fname)
    if not (d / "loop.json").exists():
        save_state(root, {
            "loop_version": LOOP_VERSION,
            "project": project_name(root),
            "session": 0,
            "last_closeout": None,
            "agent": None,
            "git_anchor": None,
            "boot_char_budget": BOOT_BUDGET,
        })
        created.append("loop.json")
    actions = [f"created docs/loop/{f}" for f in created]
    pa = copy_protocol(root)
    if pa:
        actions.append(pa)
    actions += ensure_agents_block(root, args.claude)
    if args.local:
        g = ensure_gitignore(root)
        if g:
            actions.append(g)
    print(BANNER)
    print()
    if actions:
        for a in actions:
            print(f"  {green('✔')} {a}")
    else:
        print(f"  {green('✔')} already initialized, nothing to change")
    print()
    print(f"  {bold('Next:')} ask your agent to {cyan('install Loop Engineering on this project')}.")
    print(f"  It will read the codebase once and fill every file marked {dim('loop:unfilled')}.")
    return 0


def cmd_boot(root: Path, args) -> int:
    boot = docs(root) / "BOOT.md"
    if not boot.exists():
        print("No docs/loop/BOOT.md found. Run `loop init`, then install with your agent.", file=sys.stderr)
        return 1
    state = load_state(root)
    print(read(boot).rstrip())
    print()
    print("---")
    print(drift_text(drift(root, state.get("git_anchor"))))
    return 0


def collect_ids(d: Path) -> tuple[dict[str, list[str]], dict[str, set[str]]]:
    defs: dict[str, list[str]] = {}
    refs: dict[str, set[str]] = {}
    for p in sorted(d.glob("*.md")):
        if p.name == "PROTOCOL.md":
            continue
        text = read(p)
        for m in DEF_RE.finditer(text):
            key = f"{m.group(1)}-{m.group(2)}"
            defs.setdefault(key, []).append(p.name)
        for m in REF_RE.finditer(text):
            key = f"{m.group(1)}-{m.group(2)}"
            refs.setdefault(key, set()).add(p.name)
    return defs, refs


PATH_TOKEN = re.compile(r"`([A-Za-z0-9_.\-/]+/[A-Za-z0-9_.\-/]*|[A-Za-z0-9_\-/]+\.[A-Za-z][A-Za-z0-9]{0,5})(?::[\w.\-]+)?`")


def stale_map_paths(root: Path, d: Path) -> list[str]:
    text = read(d / "codebase-map.md")
    missing = []
    for m in PATH_TOKEN.finditer(text):
        token = m.group(1).rstrip("/")
        if not token or "*" in token or token.startswith(("http", "-")):
            continue
        if token.startswith("/") or ".." in token:
            continue
        if not (root / token).exists() and token not in missing:
            missing.append(token)
    return missing


def run_checks(root: Path) -> tuple[list[str], list[str], dict]:
    d = docs(root)
    errors: list[str] = []
    warnings: list[str] = []
    info: dict = {}
    if not d.exists():
        errors.append("docs/loop/ does not exist (run `loop init`)")
        return errors, warnings, info

    for fname, _tier in FILES:
        p = d / fname
        if not p.exists():
            errors.append(f"missing docs/loop/{fname}")
        elif UNFILLED in read(p):
            warnings.append(f"{fname} is still a scaffold (marked loop:unfilled)")
    if not (d / "PROTOCOL.md").exists():
        warnings.append("docs/loop/PROTOCOL.md missing (agents without the skill can't find the closeout rules)")

    state = load_state(root)
    if state.get("_invalid"):
        errors.append("loop.json is not valid JSON")
    elif not state:
        errors.append("missing docs/loop/loop.json")
    budget = int(state.get("boot_char_budget", BOOT_BUDGET) or BOOT_BUDGET)
    boot_len = len(read(d / "BOOT.md"))
    info["boot_len"], info["budget"] = boot_len, budget
    if boot_len > budget:
        errors.append(f"BOOT.md is {boot_len:,} chars, over the {budget:,} budget: distill it, link IDs instead of copying")
    elif boot_len > 0.85 * budget:
        warnings.append(f"BOOT.md is at {boot_len / budget:.0%} of budget")

    defs, refs = collect_ids(d)
    info["ids"] = len(defs)
    for key, files in sorted(defs.items()):
        if len(files) > 1:
            errors.append(f"{key} defined {len(files)} times ({', '.join(files)})")
        prefix = key.split("-")[0]
        home = ID_HOME[prefix]
        if files and files[0] != home:
            warnings.append(f"{key} is defined in {files[0]}, expected {home}")
    for key, files in sorted(refs.items()):
        if key not in defs:
            errors.append(f"{key} referenced in {', '.join(sorted(files))} but never defined")

    for p in sorted(d.glob("*")):
        if not p.is_file() or p.name == "PROTOCOL.md":
            continue
        for lineno, line in enumerate(read(p).splitlines(), 1):
            for label, pat in SECRET_PATTERNS:
                if pat.search(line):
                    errors.append(f"possible {label} in {p.name}:{lineno}")

    missing = stale_map_paths(root, d)
    if missing:
        shown = ", ".join(missing[:8]) + (" ..." if len(missing) > 8 else "")
        warnings.append(f"codebase-map.md mentions {len(missing)} path(s) that don't exist: {shown}")

    anchor = state.get("git_anchor")
    if anchor and run_git(root, "rev-parse", "--git-dir") is not None:
        if run_git(root, "cat-file", "-e", f"{anchor}^{{commit}}") is None:
            warnings.append(f"git_anchor {anchor} not found in this repository")
    return errors, warnings, info


def cmd_check(root: Path, args) -> int:
    errors, warnings, info = run_checks(root)
    print(f"\n  {cyan('◆')} {bold('loop check')}  {dim(str(docs(root)))}\n")
    for e in errors:
        print(f"    {red('✖')} {e}")
    for w in warnings:
        print(f"    {yellow('▲')} {w}")
    if not errors and not warnings:
        print(f"    {green('✔')} all checks passed")
    print()
    summary = f"{len(errors)} error(s), {len(warnings)} warning(s)"
    print(f"  {red(summary) if errors else (yellow(summary) if warnings else green(summary))}\n")
    if errors or (args.strict and warnings):
        return 1
    return 0


def next_id(root: Path, prefix: str) -> str:
    prefix = prefix.upper()
    if prefix not in ID_HOME:
        raise SystemExit(f"unknown prefix {prefix}; use one of {', '.join(ID_HOME)}")
    defs, refs = collect_ids(docs(root))
    nums = [int(k.split("-")[1]) for k in list(defs) + list(refs) if k.split("-")[0] == prefix]
    n = (max(nums) if nums else 0) + 1
    return f"{prefix}-{str(n).zfill(ID_WIDTH[prefix])}"


def cmd_next(root: Path, args) -> int:
    print(next_id(root, args.prefix))
    return 0


def cmd_stamp(root: Path, args) -> int:
    if not docs(root).exists():
        print("docs/loop/ not found; run `loop init` first", file=sys.stderr)
        return 1
    state = load_state(root)
    if state.get("_invalid"):
        print("loop.json is not valid JSON; fix it before stamping", file=sys.stderr)
        return 1
    state.setdefault("loop_version", LOOP_VERSION)
    state.setdefault("project", project_name(root))
    state.setdefault("boot_char_budget", BOOT_BUDGET)
    state["session"] = args.session if args.session is not None else int(state.get("session", 0) or 0) + 1
    state["last_closeout"] = now_iso()
    if args.agent:
        state["agent"] = args.agent
    sha = run_git(root, "rev-parse", "--short", "HEAD")
    if sha:
        state["git_anchor"] = sha
    save_state(root, state)
    print(f"  {green('✔')} stamped session {state['session']}"
          + (f", anchor {sha}" if sha else ", no git anchor (not a git repo)"))
    return 0


def start_here(root: Path) -> str:
    text = read(docs(root) / "next-steps.md")
    m = re.search(r"^## START HERE[ \t]*\n(.*?)(?=^## |\Z)", text, re.DOTALL | re.MULTILINE)
    if not m:
        return "(none)"
    body = " ".join(l.strip() for l in m.group(1).splitlines() if l.strip() and not l.lstrip().startswith("#"))
    return body[:110] + ("…" if len(body) > 110 else "") if body else "(empty)"


def cmd_status(root: Path, args) -> int:
    d = docs(root)
    print(BANNER)
    print()
    if not d.exists():
        if (root / "docs" / "loop" / "prompt.md").exists():
            print(f"  {yellow('▲')} v3 install detected. Run {cyan('loop migrate')}.")
        else:
            print(f"  {dim('Not installed here.')} Run {cyan('loop init')}, then ask your agent to install.")
        return 0
    if (d / "prompt.md").exists() and not (d / "BOOT.md").exists():
        print(f"  {yellow('▲')} v3 install detected (prompt.md, no BOOT.md). Run {cyan('loop migrate')}.\n")
    state = load_state(root)
    dr = drift(root, state.get("git_anchor"))
    errors, warnings, info = run_checks(root)

    if not dr["git"]:
        drift_val = dim("not a git repo")
    elif not dr["anchor"]:
        drift_val = yellow("no anchor yet")
    elif dr["anchor_missing"]:
        drift_val = yellow(f"anchor {dr['anchor']} not in clone")
    elif dr["commits"]:
        drift_val = yellow(f"{len(dr['commits'])} commit(s) since {dr['anchor']}")
    else:
        drift_val = green(f"in sync with {dr['anchor']}")
    if dr["git"] and dr["dirty"]:
        drift_val += dim(f"  ·  {dr['dirty']} uncommitted")

    print(panel(state.get("project", project_name(root)), [
        ("session", bold(str(state.get("session", 0)))),
        ("last close", str(state.get("last_closeout") or dim("never"))),
        ("agent", str(state.get("agent") or dim("unknown"))),
        ("drift", drift_val),
    ]))
    print()
    budget, boot_len = info.get("budget", BOOT_BUDGET), info.get("boot_len", 0)
    print(panel("context budget", [
        ("BOOT.md", f"{bar(boot_len, budget)}  {boot_len:,} / {budget:,} chars  {dim('≈ ' + str(boot_len // 4) + ' tokens')}"),
    ]))
    print()
    rows = []
    for fname, tier in FILES:
        p = d / fname
        tier_label = {"hot": red("HOT "), "warm": yellow("WARM"), "cold": cyan("COLD")}[tier]
        if not p.exists():
            rows.append((fname, f"{tier_label}  {red('missing')}"))
            continue
        text = read(p)
        flag = yellow("  scaffold") if UNFILLED in text else ""
        rows.append((fname, f"{tier_label}  {len(text):>7,} chars  {dim('≈ ' + str(len(text) // 4) + ' tok')}{flag}"))
    print(panel("tiers", rows))
    print()
    print(panel("next", [("START HERE", start_here(root)), ("IDs indexed", str(info.get("ids", 0)))]))
    print()
    health = (red(f"✖ {len(errors)} error(s)") if errors else green("✔ healthy")) + \
        (yellow(f"  ▲ {len(warnings)} warning(s)") if warnings else "")
    print(f"  {cyan('◆')} {bold('health')}  {health}  {dim('(loop check for details)')}\n")
    return 0


def cmd_migrate(root: Path, args) -> int:
    d = docs(root)
    if not (d / "prompt.md").exists():
        print("No v3 install found (docs/loop/prompt.md missing). Nothing to migrate.")
        return 0
    if (d / "BOOT.md").exists():
        print("BOOT.md already exists; this install looks migrated. Run `loop check`.")
        return 0
    state_existing = load_state(root)
    sess = 0
    m = re.findall(r"^\|\s*(\d+)\s*\|", read(d / "system-design.md"), re.MULTILINE)
    if m:
        sess = max(int(x) for x in m)
    created = []
    t = templates(project_name(root), sess or 1, datetime.now().date().isoformat())
    for fname in ("BOOT.md", "traps.md"):
        if not (d / fname).exists():
            (d / fname).write_text(t[fname], encoding="utf-8")
            created.append(fname)
    if not state_existing:
        save_state(root, {
            "loop_version": LOOP_VERSION,
            "project": project_name(root),
            "session": sess,
            "last_closeout": None,
            "agent": None,
            "git_anchor": run_git(root, "rev-parse", "--short", "HEAD"),
            "boot_char_budget": BOOT_BUDGET,
        })
        created.append("loop.json")
    pa = copy_protocol(root)
    actions = [f"created docs/loop/{f}" for f in created] + ([pa] if pa else []) + ensure_agents_block(root, False)
    print(BANNER)
    print()
    for a in actions:
        print(f"  {green('✔')} {a}")
    print(f"\n  {bold('Now ask your agent:')} {cyan('migrate Loop Engineering to v4')}")
    print("  It moves traps into traps.md, assigns T-/F- IDs, and distills BOOT.md (PROTOCOL.md Section 13).")
    return 0


def cmd_hook(root: Path, args) -> int:
    if args.event != "session-start":
        return 0
    payload = {}
    try:
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
            payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        payload = {}
    if not os.environ.get("CLAUDE_PROJECT_DIR") and payload.get("cwd"):
        root = find_root(payload["cwd"])
    d = docs(root)
    boot = d / "BOOT.md"
    if not boot.exists():
        if (d / "prompt.md").exists():
            ctx = ("This project has a Loop Engineering v3 install in docs/loop/. "
                   "Loop Engineering v4 is available: the operator can run /loop-engineering:boot or ask to migrate.")
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ctx}}))
        return 0
    state = load_state(root)
    source = payload.get("source", "startup")
    header = (f"Loop Engineering v{LOOP_VERSION} context for this project, loaded from docs/loop/BOOT.md "
              f"(session start: {source}). The other files in docs/loop/ hold detail by ID and are read only when a task needs them. "
              f"The closeout procedure is in docs/loop/PROTOCOL.md.\n\n")
    body = read(boot).replace(UNFILLED, "").strip()
    tail = "\n\n" + drift_text(drift(root, state.get("git_anchor")), max_commits=8)
    room = HOOK_CONTEXT_CAP - len(header) - len(tail)
    if len(body) > room:
        body = body[: max(room - 80, 0)] + "\n[BOOT.md truncated: over budget, distill it at closeout]"
    ctx = header + body + tail
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ctx}}))
    return 0

# --------------------------------------------------------------------------- entry

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="loop", description="Loop Engineering CLI")
    p.add_argument("--root", help="project root (default: git root of the current directory)")
    sub = p.add_subparsers(dest="cmd")
    i = sub.add_parser("init", help="scaffold docs/loop/ and agent-file integration")
    i.add_argument("--local", action="store_true", help="add docs/loop/ to .gitignore")
    i.add_argument("--claude", action="store_true", help="create CLAUDE.md importing AGENTS.md if missing")
    sub.add_parser("status", help="dashboard")
    sub.add_parser("boot", help="print BOOT.md plus a drift report")
    ch = sub.add_parser("check", help="lint the loop docs")
    ch.add_argument("--strict", action="store_true", help="treat warnings as errors")
    n = sub.add_parser("next", help="next free ID for a prefix")
    n.add_argument("prefix", help="D, T, TRAP, F, or Q")
    s = sub.add_parser("stamp", help="record a closeout in loop.json")
    s.add_argument("--agent", help="model or agent name to record")
    s.add_argument("--session", type=int, help="set the session number explicitly")
    sub.add_parser("migrate", help="upgrade a v3 install to v4")
    h = sub.add_parser("hook", help="harness hooks")
    h.add_argument("event", choices=["session-start"])
    sub.add_parser("version")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd in (None, "version"):
        if args.cmd is None:
            build_parser().print_help()
            return 0
        print(f"loop {VERSION} (protocol v{LOOP_VERSION})")
        return 0
    root = find_root(args.root)
    handlers = {
        "init": cmd_init, "status": cmd_status, "boot": cmd_boot, "check": cmd_check,
        "next": cmd_next, "stamp": cmd_stamp, "migrate": cmd_migrate, "hook": cmd_hook,
    }
    return handlers[args.cmd](root, args)


if __name__ == "__main__":
    sys.exit(main())
