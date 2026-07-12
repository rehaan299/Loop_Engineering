# Loop Engineering

A persistent context layer for AI coding agents: full context between sessions and across models. 

## The problem

If you've used an AI agent inside a real production codebase, you've hit this wall: every new session starts with zero context. The agent doesn't know what got built last session, doesn't know why small architectural decisions were made along the way, and doesn't know about implicit setup steps or ordering that aren't written down anywhere in the code itself.

To get any of that back, it either has to read through the entire codebase, which costs real time and tokens, or it skips that step and works off assumptions. That second path is the dangerous one: it'll fix the first thing it sees without understanding the system underneath it, and break something else in the process.

Either way you pay. Re-crawling a large repo is ten to thirty minutes of wall time and a serious chunk of token budget, every single session, to get the agent back to the same context it had yesterday. I ran into this firsthand enough times that I built this to fix it for good.

## How it works

**First session, the agent reads your codebase properly.** Not a skim. It explores the repo, runs commands itself, reads the manifests, traces the entry points, reconstructs the schema, maps the core data flows, and hunts down the traps. This is expensive and it's supposed to be. You pay it once.

**Then it compiles what it learned into docs.** Seven dense markdown files in `docs/loop/`, written by the agent for the next agent. Not a README, not for humans, optimized to be read cold and understood immediately.

**Every session after that, it boots from the docs in seconds.** It only opens actual source files when it's about to modify them, and by then it knows exactly which two files to open instead of forty.

**At closeout, it rewrites the docs.** Automatically, before the conversation ends. You never maintain them; they maintain themselves as a side effect of the work.

A 500k line repo compresses to a few thousand lines of context docs. That ratio is the whole point.

## What you get

- **Session persistence across models and tools.** Plain markdown. Claude wrote them, Gemini reads them. Cursor yesterday, ChatGPT today, no difference.
- **A codebase map that kills repeat file reads.** Directory tree with per-directory purpose, module inventory with import/export surfaces, traced data flows, and a change-impact index that answers "if I add an endpoint, which files do I touch."
- **An append-only decision log.** Every architectural call recorded with context, alternatives, and consequences. No agent re-litigates a settled choice six weeks later.
- **Full technical state, always current.** Schema written out in full, interface surface, environment, what works, what's broken, and every known trap.
- **Automatic housekeeping.** Closeout rewrites everything. The loop can't go stale unless you skip it.
- **A hard rule against placeholders.** No `// TODO`, no `// ... rest of the code`, no partials. Every file the agent writes runs as written.

## Setup

Zero install, zero dependencies. One markdown file.

### First time, per project

Copy the contents of `LOOP_ENGINEERING.md`, open a chat with your agent inside your codebase, and paste it in.

It asks four short questions first, only things it can't get from the code:

```
1. What should I call you, and any notes on how you like to work?
2. Any hard constraints I won't find in the code?
   (compliance, deadlines, systems outside this repo)
3. Who else touches this project?
4. Anything expensive for me to discover on my own?
   (landmines, deprecated code still in prod, undocumented business rules)
```

Skip any of them with "you decide" and it moves on. Then it reads the codebase, writes `docs/loop/`, adds it to `.gitignore` if you want it kept local, and starts working.

Once per project. Never again.

### Every session after

Open a new chat, paste `docs/loop/prompt.md`, and send:

```
read prompt.md and start the session
```

It reads the docs, gives you a boot report (where the project stands, what's next, any blockers), and waits for your go.

### Closing out

```
close the session
```

It rewrites `progress.md`, updates `codebase-map.md`, appends any new decisions, refreshes the task queue with a single unambiguous START HERE, moves the roadmap position, and logs a plain-English summary for you. Then it runs a self-check: secrets scrubbed, docs sufficient for a cold agent on a different model to resume, every bug and trap recorded.

Next chat, you paste `prompt.md` and you're back exactly where you left off. Same model, different model, tomorrow, three weeks from now.

## Who this is for

Anyone using an AI agent inside a codebase too big to re-explain every time. Especially if:

- You're burning real token budget re-establishing context every session
- You switch between models or tools and want context to travel with you
- You're on a long-running project and keep losing the thread between sessions
- You want an audit trail of technical decisions instead of letting a fresh agent guess
- You've noticed output quality degrading late in long sessions and want a clean way to check out and resume

## Feedback

Built this to fix my own problem. Putting it out free because other people are probably hitting the same wall. If something breaks, a section feels missing, or you've got a better way to structure one of the files, open an issue or a PR. Feedback is the reason it's public.

## License

MIT.
