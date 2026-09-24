# BeePlex Is Not an Agent

This is a deliberate design choice, not a missing feature. This document
explains the concept so it stays explicit as the project evolves.

## The concept in one line

**BeePlex is the agent's senses, not the agent's brain.**

An agent judges, decides, and acts. BeePlex remembers, measures, and
retrieves. The agent is the chef; BeePlex is the fridge — it doesn't cook,
but without fresh ingredients the chef can't make anything, and a fridge
fits in any kitchen.

## What BeePlex does not do

- No agentic loop: it never decides what to do next on its own.
- No proactive behavior: no nudges, no scheduled check-ins, no goal
  tracking — that loop belongs to the host.
- No judgment calls about your life: it hands over labelled evidence
  (Bee's own summaries vs. BeePlex's independent measurements) and lets
  the host — and you — reconcile them.

Keeping judgment out is what makes BeePlex trustworthy *as infrastructure*:
any host can rely on it precisely because it doesn't have opinions about
what the host should do.

## What a host does

The host is any MCP-compatible client: **Codex, Claude Code,
Claude Desktop, Cursor** — or **Muse** (the assistant) acting as a remote
host. The host:

1. Talks to you and figures out what you want.
2. Picks the right BeePlex tools (`fetch_conversations`,
   `score_conversations`, `generate_report`, `bee_diary`, `user_profile`,
   …) and chains them.
3. Interprets the results, answers, and follows up.

BeePlex never competes with hosts. It makes every host smarter, and it is
host-agnostic by construction — swap the host, keep the memory.

## The data flow

```
Bee device → Bee cloud → Bee CLI (authenticated) → BeePlex → host → you
```

BeePlex never talks to the device directly. The **Bee CLI is the only
bridge** to your data (`bee conversations list --json`, etc.), called as a
subprocess. Demo mode (`--demo`) swaps in a fake CLI
(`beeplex/demo_cli.py`) on the exact same code path — there is no separate
mock branch, so switching to live data changes nothing but the source.

## Hosts can stack: the layered pattern

Because BeePlex is host-agnostic, hosts themselves can be layered:

```
you → Muse → Codex → BeePlex → Codex → Muse → you
```

Muse (remote, conversational) drives Codex (local, agentic) via
`codex exec`, and Codex drives BeePlex over MCP/stdio. Each layer adds
something: Muse brings the conversation, Codex brings the agentic loop on
your machine where the real data lives, BeePlex brings the memory.

Trade-offs of stacking, stated honestly:

- **Two models run** (Muse's reasoning + Codex's API calls) — it costs more.
- **One extra hop** — it is slower than talking to Codex directly.
- **Only non-interactive mode** (`codex exec`) works through a remote host;
  the interactive TUI needs a real terminal.

The point of the pattern is not efficiency — it is proof. A host driving
another host driving BeePlex demonstrates the core claim live: *any agent
can plug this in*.

## Demo and live side by side

MCP servers are just named entries in the host's config, so demo and live
can coexist without touching any code:

```toml
[mcp_servers.beeplex]        # demo — clearly labelled sample data
command = "/path/to/python"
args = ["-m", "beeplex", "--demo"]

[mcp_servers.beeplex_live]   # live — your real Bee data
command = "/path/to/python"
args = ["-m", "beeplex", "--data-dir", "/home/you/.beeplex"]
```

The host sees two tool sets and picks per request: "show me the demo"
vs. "pull today's real report". `--data-dir` keeps the outputs fully
separate. See `README.md` for setup steps.

## Why this matters for the hackathon

Everyone is building agents. Agents are only as good as what they can see.
BeePlex is the perception layer for personal AI — structured, honest,
labelled memory that any agent can plug into. The scarce piece in the agent
era is not another brain; it is trustworthy senses.
