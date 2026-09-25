# BeePlex

Chat with your Bee memories from an MCP-compatible chat app. Ask what happened
today, find a past conversation, review commitments, or generate a report.
Your chat app supplies the language model; BeePlex supplies the tools and context.

## Install

Requires Python 3.11+. From the repository folder:

```sh
python -m pip install -e ".[reports]"
```

- macOS / Linux: `python3 -m pip install -e ".[reports]"`
- Windows: `py -m pip install --user -e ".[reports]"`

After installing, `beeplex` is a command on your PATH. On Windows, if PowerShell
does not recognize it yet, close and reopen the terminal — the installer places
the command in `%APPDATA%\Python\Python3XX\Scripts`, which PATH picks up on a
fresh shell.

No install needed for a quick look: from the same folder,
`python -m beeplex --demo doctor` (or `py -m beeplex --demo doctor` on Windows)
runs straight from the checkout, as long as the dependencies are installed.

## Example runs

Demo mode (`--demo`) serves the nine simulator scenarios as clearly labelled
`[MOCK]` sample conversations through the exact same code path as the live Bee
CLI — no Bee account or login needed. Every command below works in live mode by
omitting `--demo`.

**Check your setup:**

```sh
$ beeplex --demo doctor
Mode: demo (sample memories)
Bee CLI installed: no
Logged in: not checked in demo mode
Reports extras installed: yes
Data directory: /home/hatch/.beeplex/demo
Data directory writable: yes
Sample memories only. These are not the user's real conversations.
```

**Browse conversations:**

```sh
$ beeplex --demo conversations --limit 3
Mode: demo (sample memories)
Data:
  Id: sim_template_visit
  Title: [MOCK] TEMPLATE - doctor visit (edit me)
  Summary: [MOCK] Minimal test template - six turns
  Id: sim_doctor_visit
  Title: [MOCK] Patient visit - knee pain
  Summary: [MOCK] Doctor sees a patient about three weeks of right knee pain
  Id: sim_followup_visit
  Title: [MOCK] BP med review
  Summary: [MOCK] Blood pressure follow-up; dizziness since lisinopril dose increase
Next cursor: 3
```

**Read a transcript:**

```sh
$ beeplex --demo read sim_template_visit --limit 3
Mode: demo (sample memories)
Data:
  Id: sim_template_visit
  Title: [MOCK] TEMPLATE - doctor visit (edit me)
  Summary: [MOCK] Minimal test template - six turns
  Utterances:
    Speaker: Speaker 1
    Text: [MOCK] what's changed
    Speaker: Speaker 2
    Text: [MOCK] nothing
    Speaker: Speaker 1
    Text: [MOCK] what's new
Next offset: 3
Total utterances: 6
```

**Score recent conversations:**

```sh
$ beeplex --demo score --limit 2
Mode: demo (sample memories)
Data:
  Title: [MOCK] TEMPLATE - doctor visit (edit me)
  Date: 2026-09-24
  Engagement: Low (1.0)
  Forward motion: —
  Tone: —
  Title: [MOCK] Patient visit - knee pain
  Date: 2026-09-24
  Engagement: Moderate (5.0)
  Forward motion: High (9.9)
  Tone: —
Detail: 2 conversations via Bee CLI (sample data)
Interpretation: Heuristic observations about conversation structure, not objective judgments about people.
```

**Generate the voice editor pages:**

```sh
$ beeplex --demo voice sim_argument
Browser transcript editor: /home/hatch/.beeplex/demo/voice/sim_argument.html
All-recordings editor: /home/hatch/.beeplex/demo/voice/slack.html (9 recordings)
Open this HTML file in your browser. Audio uses browser text-to-speech.
```

Every `voice` run writes two pages: the single-conversation editor and a
refreshed multi-scenario `slack.html` covering every recording in the current
mode (live Bee CLI or demo), with a scenario picker. Both are self-contained
HTML with editable speaker timing lanes and spoken transcript playback (browser
text-to-speech, because Bee's transcript response does not include its original
audio). Bee timestamps are used when available; otherwise the editor estimates
segment lengths from the text. Timing and transcript edits are saved in that
browser's local storage, shared between the two pages.

**Write Bee's diary:**

```sh
$ beeplex --demo diary --limit 2
Mode: demo (sample memories)
Data: # Bee — September 24, 2026 Everything is still firsts for me. 0 days in,
and I'm starting to recognize your rhythms. Not much said in “[MOCK] TEMPLATE -
doctor visit (edit me)”. That's alright — I was there for the quiet too. ...
File: /home/hatch/.beeplex/demo/Bee_2026-09-24.md
```

Generated files live in the data directory — `~/.beeplex` in live mode,
`~/.beeplex/demo` in demo mode (`%USERPROFILE%\.beeplex` on Windows).
A demo run produces, for example:

```text
~/.beeplex/demo/
├── voice/
│   ├── sim_argument.html   ← single-conversation editor page
│   └── slack.html          ← all-recordings editor page
├── dashboard.html             ← coaching dashboard
├── Bee_Transcript_Action_Log_2026-09-24.docx
├── Bee_Transcript_Metrics_2026-09-24.xlsx
├── Bee_Insights_Presentation_2026-09-24.pptx
├── Bee_2026-09-24.md          ← Bee's diary
├── user.md                    ← incremental profile
└── profile_state.json
```

The data directory is created lazily: `voice/` appears the first time you run
`beeplex voice`, `demo/` the first time you use `--demo`. Read commands
(`conversations`, `read`, `search`, `score`, `status`) write nothing to disk.
Only `report`, `diary`, `profile --refresh`, and `voice` create files.

## Use it with a chat app

Generate the MCP configuration for your chat app:

```sh
beeplex --demo --config
```

Paste the output into your app's MCP settings. It includes the correct absolute
Python path automatically and looks like this:

```json
{
  "mcpServers": {
    "beeplex": {
      "command": "/absolute/path/to/python",
      "args": ["-m", "beeplex", "--demo"]
    }
  }
}
```

Restart or reconnect your chat app after adding the server. It launches BeePlex
automatically. Running `beeplex` in a terminal starts the MCP transport and waits
for a client; it is not an interactive chat terminal.

Try asking:

- "What have I been talking about today?"
- "What did we decide about the launch?"
- "Read that conversation and tell me what I promised."
- "What do I need to follow up on?"
- "How engaging were my recent conversations?"
- "Make a report and write Bee's diary."

Demo responses are always labelled as sample data.

## Connect your Bee

Install and authenticate the Bee CLI:

Enable Developer Mode in the Bee app by tapping the app version five times
in Settings. The [Bee CLI guide](https://docs.bee.computer/docs/cli) covers setup.

```sh
npm install -g @beeai/cli
bee login
beeplex --check
```

Run `beeplex --config` for a live configuration, or remove `"--demo"` from your
existing configuration, then reconnect. If Bee isn't available,
tools return an actionable error. Live mode never silently substitutes sample data.

## Concept

BeePlex is deliberately **not an agent** — it is the agent's senses, not
its brain. Any MCP-compatible host (Codex, Claude Code, Claude Desktop,
Cursor, or Muse as a remote host) supplies the judgment; BeePlex supplies
the memory. See [docs/host-agents.md](docs/host-agents.md) for the full
concept, including the layered host pattern and demo/live side-by-side
configs.

## Tools

| Tool | What to ask |
| --- | --- |
| `connection_status` | "Is my Bee connected?" |
| `get_context` | "Catch me up" or "What happened on September 20?" |
| `search_memories` | "Find the discussion about the launch" |
| `fetch_conversations` | "Show my recent conversations" |
| `read_conversation` | "What exactly did we say in that conversation?" |
| `get_todos` | "What are my commitments?" |
| `score_conversations` | "How did my conversations go?" |
| `disagreement_view` | "Where do Bee and beeplex disagree?" |
| `generate_report` | "Export my recent conversations" |
| `bee_diary` | "Write Bee's diary" |
| `user_profile` | "What do you know about me?" / "Refresh my profile" |

Search and conversation browsing return IDs for follow-up questions. Transcript
reading is paginated. Prompts `catch_up` and `reflect` are available in clients
that support MCP prompts. The `beeplex://guide` resource explains tool selection.

## Direct CLI

Run any tool directly from the shell, without an MCP client. For sample data:

```sh
beeplex --demo status
beeplex --demo context --period recent --limit 5
beeplex --demo search "launch" --semantic --limit 5
beeplex --demo conversations --limit 5
beeplex --demo read sim_template_visit --offset 0 --limit 10
beeplex --demo todos --limit 10
beeplex --demo score --limit 3
beeplex --demo report --limit 3
beeplex --demo diary --limit 3
beeplex --demo profile --refresh --limit 3
beeplex --demo voice sim_argument
beeplex --demo doctor
```

Omit `--demo` for your Bee account, or set `BEEPLEX_DEMO=1` for samples.
Every command accepts `--json` for the full tool payload and `--help` for options.
Use `context --period date --date-str YYYY-MM-DD` for a dated summary;
search accepts `--since`/`--until`, and conversations/todos accept `--cursor`.
Profile reads by default; `--refresh --full` rebuilds it. Report requires the
`reports` extra. `--data-dir PATH` selects the output folder. With no subcommand,
BeePlex still starts the MCP stdio server; `--check` and `--config` work as before.

## Configuration

| Setting | Default / purpose |
| --- | --- |
| `BEE_CLI` | `bee`; executable path if it is not on your chat app's PATH |
| `BEEPLEX_DATA_DIR` | `~/.beeplex`; reports, dashboard, diary and profile |
| `BEEPLEX_DEMO=1` | Same as `--demo`: routes the CLI calls to the bundled demo CLI (`beeplex/demo_cli.py`), so the exact same code path serves clearly-labelled sample data — there is no separate mock branch |
| `BEEPLEX_LLM=1` | Opt in to extra provider calls for scoring and writing |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Optional Gemini enrichment settings |
| `BEDROCK_REGION`, `BEDROCK_MODEL` | Optional Bedrock enrichment settings |

`--data-dir /absolute/path` overrides the output folder. Demo files always go in
its `demo/` subfolder, separate from your live history. Existing `family/` data is
left in place; set `BEEPLEX_DATA_DIR` to that folder to keep using it.

The default installation needs no AWS account or additional model key. Basic
tools work with `pip install -e .`; the `reports` extra enables Office exports.
Install `.[bedrock]` only if using Bedrock. Provider enrichment is off unless
`BEEPLEX_LLM=1`, even if credentials already exist. Enabling it sends transcript
text to the configured provider. Demo mode disables enrichment.

Bee is accessed read-only. Scoring alone does not save history; generating reports
updates the local dashboard and history. Diary writing and profile refresh save
local files. Conversation data returned by MCP is visible to your chat app and
its model. No HTTP listener or cloud deployment is needed.

## Repository

```text
beeplex/       MCP server, Bee access, scoring and report modules
tests/         Offline tests and MCP transport checks
simulator/     Scripted Bee CLI and scoring benchmark
archive/       Original agent/UI, patches, workbook and historical documentation
pyproject.toml Package, dependencies and beeplex command
```

The old AWS/Streamlit app is retained as historical source in `archive/`; it is
not part of the installed package. The former root scripts are now package
modules (`python -m beeplex.reports`, `python -m beeplex.profile`,
`python -m beeplex.bee_fetcher --clinical`). Clinical extraction requires the
`reports` extra and remains a separate command, outside the MCP tools.

## Develop

```sh
python -m pip install -e ".[reports,dev]"
python -m pytest
python -m ruff check beeplex tests
python simulator/bench.py
```

With uv installed, `uv sync --extra reports --extra dev --locked` uses the checked-in
lockfile; `uv run beeplex --demo --check` checks the demo connection.

For a cross-platform simulation of the live CLI path, set `BEE_CLI` to the
absolute path of `simulator/bee` and set `BEEPLEX_DATA_DIR` to a scratch folder.
`SIM_BEE_EMPTY=1` and `SIM_BEE_FAIL_AUTH=1` exercise empty and disconnected states.
The simulator is synthetic data but runs through the live code path.

The MCP integration follows the [official Python SDK](https://py.sdk.modelcontextprotocol.io/).
