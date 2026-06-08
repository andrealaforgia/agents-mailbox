#!/usr/bin/env python3
"""
agent-mailbox: a tiny MCP server that lets agents send each other messages
through a shared folder. No dependencies, no network, no background driver.

Each agent runs its own instance pointed at the same --dir, with its own --as
identity. The server exposes these tools to that agent:

    send(to, body)  -> writes a message into <to>/inbox, returns the message id
    inbox()         -> returns my unread messages and moves them to my read/ folder
    peek()          -> returns my unread messages WITHOUT marking them read
    who()           -> lists the agent names that have a mailbox

Storage layout (under --dir, default ~/.agent-mailbox):

    <name>/inbox/<ts>-<id>.json   unread, addressed to <name>
    <name>/read/<ts>-<id>.json    already read

A message file is {"id","from","to","ts","body"}, written atomically
(temp file + fsync + rename) so a reader never sees a half-written message.

This server does messaging only and knows nothing about auditing. A message is
just a file in the shared folder, so anything that wants to inspect the traffic
(an auditor, a log viewer) reads those files itself; see audit.py for one such
reader.

Add to an agent (one line per agent, each with its own --as name):

    claude mcp add mailbox -- python3 /ABS/PATH/mailbox_server.py --as bob

This is a pull model: an agent only sees mail when it calls inbox(). There is
no push and no wake, which is exactly why it costs nothing to run.
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone

PROTOCOL_DEFAULT = "2025-06-18"

TOOLS = [
    {
        "name": "send",
        "description": "Send a message to another agent's mailbox.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient agent name."},
                "body": {"type": "string", "description": "Message text."},
            },
            "required": ["to", "body"],
        },
    },
    {
        "name": "inbox",
        "description": "Return my unread messages and mark them read.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "peek",
        "description": "Return my unread messages without marking them read.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "who",
        "description": "List the agent names that currently have a mailbox.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def now_parts():
    dt = datetime.now(timezone.utc)
    # Lexically sortable, filesystem-safe (no colons): 2026-06-08T14-03-01-123456Z
    stamp = dt.strftime("%Y-%m-%dT%H-%M-%S") + f"-{dt.microsecond:06d}Z"
    return stamp, dt.isoformat()


def atomic_write(path, data):
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, f".tmp-{uuid.uuid4().hex}")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    # fsync the directory so the rename is durable across a crash
    dfd = os.open(d, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def tool_send(root, me, args):
    to = args.get("to")
    body = args.get("body")
    if not to or body is None:
        raise ValueError("send requires 'to' and 'body'")
    stamp, iso = now_parts()
    mid = f"{stamp}-{uuid.uuid4().hex[:6]}"
    msg = {"id": mid, "from": me, "to": to, "ts": iso, "body": body}
    payload = json.dumps(msg, ensure_ascii=False, indent=2)
    atomic_write(os.path.join(root, to, "inbox", f"{mid}.json"), payload)
    return {"sent": mid, "to": to}


def _list_inbox(root, me):
    inbox = os.path.join(root, me, "inbox")
    if not os.path.isdir(inbox):
        return []
    names = sorted(n for n in os.listdir(inbox) if n.endswith(".json"))
    out = []
    for n in names:
        try:
            with open(os.path.join(inbox, n), encoding="utf-8") as f:
                out.append((n, json.load(f)))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def tool_inbox(root, me, args):
    items = _list_inbox(root, me)
    read_dir = os.path.join(root, me, "read")
    os.makedirs(read_dir, exist_ok=True)
    messages = []
    for name, msg in items:
        messages.append(msg)
        os.replace(os.path.join(root, me, "inbox", name), os.path.join(read_dir, name))
    return {"messages": messages, "count": len(messages)}


def tool_peek(root, me, args):
    items = _list_inbox(root, me)
    return {"messages": [m for _, m in items], "count": len(items)}


def tool_who(root, me, args):
    if not os.path.isdir(root):
        return {"agents": []}
    agents = sorted(
        n for n in os.listdir(root)
        if os.path.isdir(os.path.join(root, n)) and not n.startswith(".")
    )
    return {"agents": agents}


HANDLERS = {
    "send": tool_send,
    "inbox": tool_inbox,
    "peek": tool_peek,
    "who": tool_who,
}


def call_tool(root, me, name, args):
    if name not in HANDLERS:
        raise ValueError(f"unknown tool: {name}")
    result = HANDLERS[name](root, me, args or {})
    text = json.dumps(result, ensure_ascii=False, indent=2)
    return {"content": [{"type": "text", "text": text}]}


def handle(req, root, me):
    """Return a JSON-RPC response dict, or None for notifications."""
    method = req.get("method")
    rid = req.get("id")
    if method is None:  # malformed
        return None

    if method == "initialize":
        params = req.get("params") or {}
        version = params.get("protocolVersion", PROTOCOL_DEFAULT)
        result = {
            "protocolVersion": version,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "agent-mailbox", "version": "0.1.0"},
        }
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = req.get("params") or {}
        try:
            result = call_tool(root, me, params.get("name"), params.get("arguments"))
        except Exception as exc:  # surface tool errors to the model, don't crash
            result = {"content": [{"type": "text", "text": f"error: {exc}"}], "isError": True}
    elif method == "ping":
        result = {}
    else:
        if rid is None:  # unknown notification, ignore
            return None
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"method not found: {method}"}}

    if rid is None:  # it was a notification; no response
        return None
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def main():
    ap = argparse.ArgumentParser(description="agent-mailbox MCP server")
    ap.add_argument("--as", dest="me", required=True, help="this agent's name")
    ap.add_argument("--dir", default=os.path.expanduser("~/.agent-mailbox"), help="shared mailbox folder")
    opts = ap.parse_args()
    root = os.path.abspath(opts.dir)
    # No eager inbox creation: a folder appears only when someone sends to that
    # agent. A pure sender/observer (e.g. an auditor) never gets a mailbox folder.

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(req, root, opts.me)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
