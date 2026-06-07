#!/usr/bin/env bash
#
# Register the agent-mailbox MCP server for ONE agent identity.
# Run it once in each agent's context (e.g. from inside that agent's project dir),
# giving that agent its own --as name. They all share the same mailbox folder.
#
# Usage:
#   ./register-mailbox.sh <agent-name> [--dir <shared-folder>] [--scope local|user|project]
#
# Examples:
#   ./register-mailbox.sh alice
#   ./register-mailbox.sh bob --dir ~/work/agent-mailbox
#   ./register-mailbox.sh auditor --scope user
#
set -euo pipefail

# --- args -------------------------------------------------------------------
if [[ $# -lt 1 || "$1" == -* ]]; then
  echo "usage: $0 <agent-name> [--dir <shared-folder>] [--scope local|user|project]" >&2
  exit 2
fi
AGENT="$1"; shift
DIR="$HOME/.agent-mailbox"
SCOPE="local"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir)   DIR="$2"; shift 2 ;;
    --scope) SCOPE="$2"; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

# --- resolve paths ----------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER="$SCRIPT_DIR/mailbox_server.py"
[[ -f "$SERVER" ]] || { echo "error: mailbox_server.py not found next to this script ($SERVER)" >&2; exit 1; }
DIR="${DIR/#\~/$HOME}"   # expand a leading ~

# find the claude CLI (PATH first, then the versioned install)
CLAUDE="$(command -v claude || true)"
if [[ -z "$CLAUDE" ]]; then
  CLAUDE="$(ls -1d "$HOME"/.local/share/claude/versions/* 2>/dev/null | sort -V | tail -1 || true)"
fi
[[ -n "$CLAUDE" && -x "$CLAUDE" ]] || { echo "error: could not find the 'claude' CLI" >&2; exit 1; }

PYTHON="$(command -v python3 || true)"
[[ -n "$PYTHON" ]] || { echo "error: python3 not found" >&2; exit 1; }

# No mailbox folder is created here: an agent's inbox appears only when someone
# sends to it, so a pure sender/observer (e.g. an auditor) leaves no folder.

# --- (re)register -----------------------------------------------------------
# Remove any existing "mailbox" entry in this scope so re-running is idempotent.
"$CLAUDE" mcp remove mailbox -s "$SCOPE" >/dev/null 2>&1 || true

"$CLAUDE" mcp add mailbox -s "$SCOPE" -- "$PYTHON" "$SERVER" --as "$AGENT" --dir "$DIR"

echo "registered 'mailbox' for agent '$AGENT' (scope: $SCOPE, folder: $DIR)"
echo "tools available to this agent: send, inbox, peek, who, thread"
