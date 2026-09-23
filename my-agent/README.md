# my-agent

Copilot for the user's Bee hackathon project (beeplex), built on the
`00-getting-started` sample in
[awslabs/agentcore-samples](https://github.com/awslabs/agentcore-samples).
Python + Strands, running on **Amazon Nova Micro** (`ca.amazon.nova-micro-v1:0`)
in **ca-central-1** instead of the sample's default Claude Sonnet.

The agent's tools drive beeplex directly:

- `fetch_conversations(limit)` — recent Bee conversations (live via the Bee CLI,
  clearly-labelled mock data when the CLI isn't connected)
- `score_conversations(limit)` — engagement, forward-motion, and tone per conversation
- `generate_report(limit)` — Word/Excel/PowerPoint reports into beeplex's `family/`
  plus a refreshed coaching dashboard
- `bee_diary(limit)` — Bee's diary entry for today, in Bee's own first-person voice
  (persona mode: who Bee has become from your history)

(Clinical summaries are deliberately not wired up.)

## Layout

```
my-agent/
├── setup.sh            # one-script setup for a new user (run this first)
├── agentcore/
│   ├── agentcore.json      # project config (agents, memories)
│   ├── aws-targets.json    # deploy target: ca-central-1
│   └── .env.local          # local-only env (gitignored)
├── app/
│   └── my_agent/
│       ├── main.py         # agent entry point (tools + system prompt)
│       ├── model/load.py   # model config -> Nova Micro, ca-central-1
│       └── pyproject.toml  # Python dependencies
├── ui/
│   ├── app.py              # Streamlit dashboard (local web UI)
│   └── components/
│       └── conversation_cards/  # tier-2 custom component (clickable cards)
├── .streamlit/
│   └── config.toml         # Bee-themed look (honey-amber)
└── requirements.txt
```

## Run it (new user)

my-agent lives inside the beeplex repository, so there is only **one** thing
to download — clone beeplex and the agent comes with it:

```
git clone https://github.com/artbakerchat/beeplex.git
cd beeplex/my-agent
./setup.sh
```

`setup.sh` creates the virtualenv, installs requirements, checks for the Bee
CLI (guides `npm install -g @beeai/cli` + `bee login`), and checks for AWS
credentials. (If you ever separate the folders, set `BEEPLEX_DIR` to point at
your beeplex checkout.) Then:

```
.venv/bin/streamlit run ui/app.py   # dashboard — works with no credentials
```

The dashboard's buttons call the agent's tools directly: fetch conversations,
score them, generate the Word/Excel/PowerPoint reports. Without the Bee CLI
they run on clearly-labelled mock data; with `bee login` done, they're live.

For the full conversational agent (needs AWS credentials with Bedrock access,
Nova Micro enabled in ca-central-1):

```
export AWS_REGION=ca-central-1
agentcore dev        # terminal chat + local server on :8080 with hot reload
agentcore deploy     # deploy to AgentCore Runtime (needs real account ID in
                     # agentcore/aws-targets.json first)
```

### Try asking the agent

In `agentcore dev`, plain sentences route to the right tool:

**Fetch** (list recent conversations):
- "What conversations did I have recently?"
- "Show me my last 3 conversations and what they were about."

**Score** (engagement, forward motion, tone):
- "How engaging were my conversations today?"
- "Which of my recent conversations had the best forward motion?"
- "What was the tone of my last conversation?"

**Report** (build the .docx/.xlsx/.pptx):
- "Generate my report."
- "Build the weekly reports and refresh the dashboard."

**Diary** (Bee's persona, first-person):
- "What did Bee write about today?"
- "Read me Bee's diary entry."

Follow-ups work too ("tell me more about the second one"). Until `bee login`
is done, answers come from clearly-labelled mock data, and the agent says so.

## Notes

- The model is configured in `app/my_agent/model/load.py`. Override without
  editing: `MODEL_ID` and `AWS_REGION` env vars.
- `agentcore/aws-targets.json` still needs your real AWS account ID before
  `agentcore deploy`.
- This folder was hand-built to mirror what `agentcore create --name my-agent
  --framework Strands --model-provider Bedrock --memory none --defaults`
  scaffolds, with the Nova Micro swap applied. If the CLI's generated layout
  differs slightly, copy `app/my_agent/` into a fresh `agentcore create`
  project.
