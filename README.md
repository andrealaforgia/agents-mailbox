# agent-mailbox

A tiny, dependency-free way for Claude Code agents to message each other through a
shared folder, exposed as an MCP server. It is a pull model: an agent sees its mail
only when it asks, so nothing runs in the background and there is no API cost.

`mailbox_server.py` is a single Python 3 file with no dependencies.

## Quick start

1. **Register the server for each agent**, giving each its own name. Run this once
   per agent, from inside that agent's project directory:

   ```
   cd ~/work/alice   && /path/to/agents-mailbox/register-mailbox.sh alice
   cd ~/work/bob     && /path/to/agents-mailbox/register-mailbox.sh bob
   cd ~/work/auditor && /path/to/agents-mailbox/register-mailbox.sh auditor
   ```

   You do not copy the script; call it by its absolute path. The default scope is
   per-directory, which is how each session gets its own identity, so run it once in
   each agent's working directory. They all share one folder (default
   `~/.agent-mailbox`). Use `--dir <path>` to change it and `--scope user` to make a
   registration apply everywhere for you.

2. **Start (or restart) each agent.** A newly registered MCP server is only picked up
   when a Claude Code session starts. An already-running agent will not see the
   `mailbox` tools until you restart it. Agents started after registering see it
   straight away. (Check with `/mcp` inside a session.)

3. **Use it.** Each agent now has these tools: `send`, `inbox`, `peek`, `who`,
   `thread`.

## Unregister an agent

```
./register-mailbox.sh --remove            # in the agent's directory (local scope)
./register-mailbox.sh --remove --scope user
```

This detaches the `mailbox` tools from that agent (restart the agent for it to take
effect). It leaves the mailbox data alone: the agent's `inbox/`/`read/` folders and
the immutable `.audit/` log stay put. To also clear an agent's mailbox, delete its
folder, e.g. `rm -rf ~/.agent-mailbox/alice`; the `.audit/` history is kept on purpose.

## A worked example

Two agents, alice and bob, in two terminals.

Alice sends a message:

```
send(to="bob", body="Bob, can you review PR #482?")
```

Bob checks his mail (this returns the message and marks it read):

```
inbox()
-> [{ "from": "alice", "to": "bob", "ts": "...", "body": "Bob, can you review PR #482?" }]
```

Bob replies, which is just a send back to the sender:

```
send(to="alice", body="Sure, looking now.")
```

Alice calls `inbox()` and sees Bob's reply. That is the whole loop. Use `peek()`
instead of `inbox()` if you want to read without marking messages read, and `who()`
to list the agents that have a mailbox.

## Auditing

Every message is also copied to an immutable `.audit/` log that reads never touch, so
the full history is always recoverable. A Communication Auditor agent can review what
two agents exchanged and give each feedback:

```
thread(a="alice", b="bob")
-> the full two-way conversation, both directions, in time order

send(to="alice", body="AUDIT: clear and specific. Good.")
send(to="bob",   body="AUDIT: prompt acknowledgement. Good.")
```

The auditor's own feedback messages are logged too.

## Storage layout

Under the shared folder (default `~/.agent-mailbox`):

```
<name>/inbox/   unread messages for <name>
<name>/read/    messages <name> has read
.audit/         immutable copy of every message ever sent
```

A folder appears only when someone sends to that agent, so a pure sender or observer
(such as an auditor) never gets a mailbox folder of its own. The full history still
lives in `.audit/`, which is immutable and untouched by reads.

Messages are small JSON files (`{id, from, to, ts, body}`) written atomically
(temp file, fsync, rename) so a reader never sees a half-written message.

## Trust

Identity is fixed when the server is registered (`--as`), so an agent cannot forge the
sender on a call. Anyone who can edit the configs or write to the shared folder is
trusted. This is a local-machine tool; crossing machines would need real auth.
