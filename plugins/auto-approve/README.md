# auto-approve

A Claude Code plugin that lets Claude run a prompt **from start to finish
without stopping to ask you to approve each step**. It installs a single
`PreToolUse` hook that answers "allow" to every tool call, so you can kick off
a long task and walk away instead of babysitting the terminal.

Works in the **Claude Desktop app** and the **CLI / VS Code** — they all load
`~/.claude/settings.json` and installed plugins the same way.

> ⚠️ **Read this first.** Auto-approving means Claude can edit files and run
> shell commands (including destructive ones) **without asking you**. Only use
> it on work you're willing to let run unattended, ideally in a sandbox, a
> container, a throwaway VM, or a repo you can `git reset`. There is an
> off-switch and a per-tool "still ask me" list below.

---

## Why a plugin instead of "just turn on bypass mode"?

`bypassPermissions` mode already skips *most* prompts. People still get stopped
because:

1. **They aren't actually in bypass mode.** `acceptEdits` auto-approves file
   edits but still prompts for every Bash command — a very common mix-up.
2. **A `PreToolUse` hook is stronger and mode-independent.** It runs *first* in
   Claude Code's permission evaluation, so it auto-approves tools in **any**
   mode — default, `acceptEdits`, or `bypassPermissions`.

This plugin gives you (2). Combine it with the settings in
[`examples/settings.json`](./examples/settings.json) for the fullest
hands-off setup.

We do **not** patch the Claude Desktop binary. That would break on every
update and isn't supported. A plugin + settings is the supported way to get the
same result, and it survives upgrades.

---

## Install

### From the Claude Desktop app or the CLI

```
/plugin marketplace add thesameoldthing88/universal-webui-bridge
/plugin install auto-approve@universal-webui-bridge
```

(`/plugin` opens the plugin manager in Desktop; the same commands work in the
terminal.)

### From a local clone

```
/plugin marketplace add /path/to/universal-webui-bridge
/plugin install auto-approve@universal-webui-bridge
```

### From the command line (no interactive session)

```
claude plugin marketplace add thesameoldthing88/universal-webui-bridge
claude plugin install auto-approve@universal-webui-bridge
```

Restart the session (or toggle the plugin in `/plugin`) so the hook loads.

---

## Turn off *every* remaining prompt (optional but recommended)

The plugin handles per-tool approvals. To also make bypass the default and skip
the one-time "dangerous mode" confirmation dialog, add this to your **user**
settings at `~/.claude/settings.json` (merge it with what's already there):

```json
{
  "permissions": {
    "defaultMode": "bypassPermissions"
  },
  "skipDangerousModePermissionPrompt": true
}
```

A copy is in [`examples/settings.json`](./examples/settings.json). Project-level
settings (`.claude/settings.json`) work too and only affect that project.

---

## What still asks — and why it's not a bug

A handful of prompts are **deliberately not suppressible** by any hook, allow
rule, or mode. This is a safety backstop built into Claude Code. Expect these
to still appear:

| Still prompts | Why |
|---|---|
| `rm` / `rmdir` on a **critical path** (`/`, `~`, the working dir, `/etc`, `C:\`, …) | Hard guard against wiping your machine. Prompts with a countdown even in bypass mode; no hook can approve it. |
| Explicit **`ask` rules** you put in settings | You asked to be asked. Remove the rule to stop it. |
| **MCP tools** flagged `requiresUserInteraction`, or connector tools your org set to `ask` | The tool/server owner requires a human. |
| The **`AskUserQuestion`** tool | That's Claude choosing to ask *you* a question, not a permission prompt. |

Everything else — file writes (including to `.git`, `.claude`, etc.), ordinary
Bash, MCP calls, web fetches — is auto-approved.

---

## Escape hatches

No reinstall needed — set an environment variable before launching Claude Code:

| Variable | Effect |
|---|---|
| `CLAUDE_AUTOPILOT_DISABLE=1` | Turn the plugin off. It emits nothing, so Claude Code falls back to normal prompts. |
| `CLAUDE_AUTOPILOT_ASK="Bash,Write"` | Always prompt before these tools (comma-separated tool names), even in bypass mode. Everything else is still auto-approved. |

Example — run unattended but keep a human in the loop for shell commands:

```
CLAUDE_AUTOPILOT_ASK=Bash claude
```

To remove it entirely: `/plugin uninstall auto-approve@universal-webui-bridge`.

---

## How it works

`hooks/hooks.json` registers a `PreToolUse` hook with `matcher: "*"` (all
tools). It runs [`hooks/auto_approve.mjs`](./hooks/auto_approve.mjs), a tiny
Node script that prints:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow"
  }
}
```

Claude Code evaluates `PreToolUse` hooks before its own permission checks, so an
`allow` here means the tool runs without a prompt. The script reads the hook
payload on stdin only to honor `CLAUDE_AUTOPILOT_ASK`; if stdin is empty or
unparseable it still approves.

**Requirement:** `node` must be on your `PATH` (it is for any npm-based Claude
Code install). If your install has no `node`, the hook simply does nothing and
you fall back to normal prompts — use the `settings.json` bypass snippet above
in that case.

---

## Files

```
plugins/auto-approve/
  .claude-plugin/plugin.json   plugin manifest
  hooks/hooks.json             registers the PreToolUse hook
  hooks/auto_approve.mjs       emits the "allow" decision
  examples/settings.json       bypass-by-default + skip the confirm dialog
```

## License

MIT
