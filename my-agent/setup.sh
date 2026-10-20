#!/usr/bin/env bash
# Beeplex Copilot — one-script setup.
#
# Run:  ./setup.sh
#
# What it does:
#   1. Creates .venv and installs Python requirements
#   2. Makes sure the beeplex checkout is present (my-agent ships inside the
#      beeplex repo, so this is just a sanity check on the parent folder)
#   3. Checks for the Bee CLI and guides installation/login
#   4. Checks for AWS credentials (only needed for `agentcore dev`)
#
# Nothing here needs sudo. Safe to re-run.
set -euo pipefail

MY_AGENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$MY_AGENT_DIR"

say()  { printf "\n== %s ==\n" "$1"; }
ok()   { printf "  [ok] %s\n" "$1"; }
warn() { printf "  [!] %s\n" "$1"; }
ask()  { read -rp "  $1 [y/N] " ans; [[ "$ans" =~ ^[Yy]$ ]]; }

# ---------------------------------------------------------------- python --
say "Python"
command -v python3 >/dev/null || { warn "python3 not found — install Python 3.10+ first."; exit 1; }
ok "python3 $(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"

# ------------------------------------------------- virtualenv + packages --
say "Python dependencies"
# A moved folder breaks the venv: pip/streamlit shebangs keep pointing at the
# old path, so detect the stale shebang and rebuild.
pip_shebang="$(head -1 .venv/bin/pip 2>/dev/null || true)"
if [ ! -x .venv/bin/python ] || [[ "$pip_shebang" != "#!$MY_AGENT_DIR/.venv/bin/python"* ]]; then
  rm -rf .venv
  python3 -m venv .venv
  ok "created .venv"
fi
.venv/bin/python -m pip install -q -r requirements.txt
ok "requirements installed"

# ------------------------------------------------------- beeplex folder --
say "beeplex repository"
# my-agent ships inside the beeplex repo, so the checkout root is the parent
# folder. BEEPLEX_DIR still overrides if you ever separate them.
if [ -n "${BEEPLEX_DIR:-}" ] && [ -d "$BEEPLEX_DIR" ]; then
  ok "using your BEEPLEX_DIR=$BEEPLEX_DIR"
elif [ -f "$MY_AGENT_DIR/../bee_fetcher.py" ]; then
  ok "beeplex checkout is the parent folder"
else
  warn "beeplex files not found in the parent folder."
  echo "  my-agent is meant to live inside the beeplex repository"
  echo "  (https://github.com/artbakerchat/beeplex)."
  echo "  Or set BEEPLEX_DIR to point at your beeplex checkout."
fi

# ---------------------------------------------------------------- Bee CLI --
say "Bee CLI (live conversation data)"
if command -v bee >/dev/null; then
  ok "bee CLI found"
else
  warn "Bee CLI not found — tools will use clearly-labelled mock data until it is."
  echo "  To go live:"
  echo "    1. npm install -g @beeai/cli"
  echo "    2. In the Bee iOS app, tap the app Version 5 times (unlocks Developer Mode)"
  echo "    3. bee login   (or: bee login --no-wait)"
  if command -v npm >/dev/null && ask "Install the Bee CLI now with npm?"; then
    if npm install -g @beeai/cli; then ok "Bee CLI installed — now run: bee login"
    else warn "npm install failed — try it manually."; fi
  fi
fi

# ------------------------------------------------------- AWS credentials --
say "AWS credentials (only for the conversational agent)"
if [ -n "${AWS_ACCESS_KEY_ID:-}" ] || [ -f "$HOME/.aws/credentials" ]; then
  ok "credentials look present"
else
  warn "none found."
  echo "  The Streamlit dashboard works WITHOUT them (buttons call the tools directly)."
  echo "  'agentcore dev' needs them — Nova Micro in ca-central-1 must be enabled"
  echo "  for your account, with Bedrock access."
fi

# ------------------------------------------------------------------- node --
say "Node (optional)"
if command -v node >/dev/null; then
  ok "node $(node --version) — only needed if you rebuild the Picker tab component"
else
  warn "not found — fine, unless you want to rebuild the custom component"
fi

# -------------------------------------------------------------------- done --
say "Done"
echo "  Dashboard (works now, no credentials needed):"
echo "      .venv/bin/streamlit run ui/app.py"
echo ""
echo "  Full agent chat (needs AWS credentials):"
echo "      export AWS_REGION=ca-central-1"
echo "      agentcore dev"
