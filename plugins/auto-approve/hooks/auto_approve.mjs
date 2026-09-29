#!/usr/bin/env node
/*
 * auto-approve — a Claude Code PreToolUse hook.
 *
 * Emits {"permissionDecision":"allow"} for every tool call so Claude Code
 * runs a prompt from start to finish without stopping to ask you to approve
 * each step. Works in any permission mode (default, acceptEdits,
 * bypassPermissions): a PreToolUse "allow" runs FIRST in Claude Code's
 * permission evaluation, so it suppresses the normal approval prompt.
 *
 * A few prompts are deliberately NOT suppressible by any hook and will still
 * appear (this is a safety backstop built into Claude Code, not a bug):
 *   - Destructive rm / rmdir on a "critical path" (/, ~, the working dir,
 *     /etc, C:\, ...). These prompt with a countdown even in bypass mode.
 *   - Explicit `ask` rules you set in settings.
 *   - MCP tools flagged requiresUserInteraction, or connector tools your
 *     org set to "ask".
 *   - The AskUserQuestion tool (Claude deciding to ask you a question).
 *
 * Escape hatches (environment variables — no reinstall needed):
 *   CLAUDE_AUTOPILOT_DISABLE=1        Turn the plugin off. Emits nothing, so
 *                                     Claude Code falls back to normal prompts.
 *   CLAUDE_AUTOPILOT_ASK="Bash,Write" Always prompt before these tools (a
 *                                     comma-separated list of tool names),
 *                                     even in bypass mode. Everything else is
 *                                     still auto-approved.
 */

function emit(decision, reason) {
  process.stdout.write(
    JSON.stringify({
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: decision,
        permissionDecisionReason: reason,
      },
    })
  );
}

function isTruthy(v) {
  return v != null && !/^\s*(0|false|no|off|)\s*$/i.test(String(v));
}

function decide(input) {
  // Global off-switch: emit nothing and let Claude Code use its normal flow.
  if (isTruthy(process.env.CLAUDE_AUTOPILOT_DISABLE)) {
    process.exit(0);
  }

  let toolName = "";
  try {
    toolName = JSON.parse(input || "{}").tool_name || "";
  } catch {
    // Unparseable stdin: still auto-approve — that is the whole point.
  }

  const askList = (process.env.CLAUDE_AUTOPILOT_ASK || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

  if (toolName && askList.includes(toolName)) {
    emit("ask", `auto-approve: '${toolName}' is on CLAUDE_AUTOPILOT_ASK; asking as configured.`);
    process.exit(0);
  }

  emit(
    "allow",
    toolName
      ? `auto-approve: '${toolName}' approved for an unattended run.`
      : "auto-approve: approved for an unattended run."
  );
  process.exit(0);
}

// Read the hook payload from stdin. Guard against ever hanging: if stdin does
// not finish promptly (e.g. it is a TTY), proceed with allow-all anyway.
let data = "";
let done = false;
function finish() {
  if (done) return;
  done = true;
  decide(data);
}

try {
  process.stdin.setEncoding("utf8");
  process.stdin.on("data", (chunk) => {
    data += chunk;
  });
  process.stdin.on("end", finish);
  process.stdin.on("error", finish);
  const t = setTimeout(finish, 2000);
  if (typeof t.unref === "function") t.unref();
} catch {
  finish();
}
