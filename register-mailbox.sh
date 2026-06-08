#!/usr/bin/env bash
#
# Register (or unregister) the agent-mailbox MCP server for ONE agent identity.
# Run it once in each agent's context (e.g. from inside that agent's project dir),
# giving that agent its own name. They all share the same mailbox folder.
#
# Usage:
#   ./register-mailbox.sh <agent-name> [--dir <shared-folder>] [--scope local|user|project]
#   ./register-mailbox.sh --remove [--scope local|user|project]
#
# Examples:
#   ./register-mailbox.sh alice
#   ./register-mailbox.sh bob --dir ~/work/agent-mailbox
#   ./register-mailbox.sh auditor --scope user
#   ./register-mailbox.sh --remove                # unregister in this dir (local scope)
#   ./register-mailbox.sh --remove --scope user   # unregister the user-scope one
#
set -euo pipefail

usage() {
  echo "usage: $0 <agent-name> [--dir <shared-folder>] [--scope local|user|project]" >&2
  echo "       $0 --remove [--scope local|user|project]" >&2
}

# --- args -------------------------------------------------------------------
AGENT=""
DIR="$HOME/.agent-mailbox"
SCOPE="local"
REMOVE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --remove)    REMOVE=1; shift ;;
    --dir)       DIR="$2"; shift 2 ;;
    --scope)     SCOPE="$2"; shift 2 ;;
    -h|--help)   usage; exit 0 ;;
    -*)          echo "unknown option: $1" >&2; usage; exit 2 ;;
    *)           if [[ -z "$AGENT" ]]; then AGENT="$1"; shift; else echo "unexpected argument: $1" >&2; usage; exit 2; fi ;;
  esac
done

# find the claude CLI (PATH first, then the versioned install)
CLAUDE="$(command -v claude || true)"
if [[ -z "$CLAUDE" ]]; then
  CLAUDE="$(ls -1d "$HOME"/.local/share/claude/versions/* 2>/dev/null | sort -V | tail -1 || true)"
fi
[[ -n "$CLAUDE" && -x "$CLAUDE" ]] || { echo "error: could not find the 'claude' CLI" >&2; exit 1; }

# --- unregister -------------------------------------------------------------
if [[ "$REMOVE" -eq 1 ]]; then
  if "$CLAUDE" mcp remove mailbox -s "$SCOPE" 2>/dev/null; then
    echo "unregistered 'mailbox' (scope: $SCOPE). Restart the agent for it to drop the tools."
  else
    echo "no 'mailbox' registration found in scope '$SCOPE' (nothing to remove)."
  fi
  echo "note: any mailbox data under the shared folder is left intact (the .audit log is kept on purpose)."
  exit 0
fi

# --- register ---------------------------------------------------------------
[[ -n "$AGENT" ]] || { echo "error: agent name required to register" >&2; usage; exit 2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER="$SCRIPT_DIR/mailbox_server.py"
[[ -f "$SERVER" ]] || { echo "error: mailbox_server.py not found next to this script ($SERVER)" >&2; exit 1; }
DIR="${DIR/#\~/$HOME}"   # expand a leading ~

PYTHON="$(command -v python3 || true)"
[[ -n "$PYTHON" ]] || { echo "error: python3 not found" >&2; exit 1; }

# No mailbox folder is created here: an agent's inbox appears only when someone
# sends to it, so a pure sender/observer (e.g. an auditor) leaves no folder.

# Remove any existing "mailbox" entry in this scope so re-running is idempotent.
"$CLAUDE" mcp remove mailbox -s "$SCOPE" >/dev/null 2>&1 || true

"$CLAUDE" mcp add mailbox -s "$SCOPE" -- "$PYTHON" "$SERVER" --as "$AGENT" --dir "$DIR"

echo "registered 'mailbox' for agent '$AGENT' (scope: $SCOPE, folder: $DIR)"
echo "tools available to this agent: send, inbox, peek, who"
