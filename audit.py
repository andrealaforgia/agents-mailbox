#!/usr/bin/env python3
"""
audit.py: a read-only viewer over an agent-mailbox shared folder.

The mailbox server knows nothing about auditing. This is a SEPARATE tool that
reconstructs a conversation purely by reading the message files on disk. It is
not an MCP server and is never registered with an agent: run it directly. Every
message is a single file in its recipient's inbox/ or read/ folder, so reading
those files is all auditing needs.

Usage:
    python3 audit.py <a> <b> [--dir <shared-folder>] [--json]
    python3 audit.py --all   [--dir <shared-folder>] [--json]

Examples:
    python3 audit.py alice bob
    python3 audit.py --all
    python3 audit.py alice bob --dir ~/work/mailbox --json
"""

import argparse
import json
import os


def load_all(root):
    """Every message lives once, in its recipient's inbox/ or read/ folder."""
    seen, msgs = set(), []
    if not os.path.isdir(root):
        return msgs
    for name in os.listdir(root):
        agent_dir = os.path.join(root, name)
        if name.startswith(".") or not os.path.isdir(agent_dir):
            continue
        for sub in ("inbox", "read"):
            d = os.path.join(agent_dir, sub)
            if not os.path.isdir(d):
                continue
            for fname in os.listdir(d):
                if not fname.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(d, fname), encoding="utf-8") as fh:
                        m = json.load(fh)
                except (OSError, json.JSONDecodeError):
                    continue
                mid = m.get("id") or fname
                if mid in seen:
                    continue
                seen.add(mid)
                msgs.append(m)
    msgs.sort(key=lambda m: m.get("id") or "")
    return msgs


def main():
    ap = argparse.ArgumentParser(description="read-only audit viewer over an agent-mailbox folder")
    ap.add_argument("a", nargs="?", help="first agent")
    ap.add_argument("b", nargs="?", help="second agent")
    ap.add_argument("--all", action="store_true", help="show every message, not just one pair")
    ap.add_argument("--dir", default=os.path.expanduser("~/.agent-mailbox"), help="shared mailbox folder")
    ap.add_argument("--json", action="store_true", help="output JSON")
    opts = ap.parse_args()
    root = os.path.abspath(os.path.expanduser(opts.dir))

    msgs = load_all(root)
    if not opts.all:
        if not (opts.a and opts.b):
            ap.error("give two agent names, or use --all")
        pair = {opts.a, opts.b}
        msgs = [m for m in msgs if m.get("from") in pair and m.get("to") in pair]

    if opts.json:
        print(json.dumps(msgs, ensure_ascii=False, indent=2))
    elif not msgs:
        print("(no messages)")
    else:
        for m in msgs:
            ts = (m.get("ts") or "")[:19].replace("T", " ")
            print(f"{ts}  {m.get('from', '?')} -> {m.get('to', '?')}: {m.get('body', '')}")


if __name__ == "__main__":
    main()
