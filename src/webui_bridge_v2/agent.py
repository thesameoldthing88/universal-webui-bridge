"""
A small coding agent that uses any connected web LLM as its brain.

The agent's loop:
    1. Send the system prompt + the user's task to the LLM (via LLMBridge.chat).
    2. Parse the LLM's reply for a ```tool block (a JSON call) or a ```done block.
    3. Execute the tool inside a per-session sandbox workspace.
    4. Send the tool result back to the LLM as the next prompt.
    5. Repeat until the LLM emits ```done or max_steps is reached.

The agent streams events through an `on_event(kind, data)` callback so the
GUI can show a live log of every step.

Tools (all confined to the workspace directory):
    write_file(path, content)
    read_file(path)
    list_dir(path)
    run_python(code)
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional, Protocol

logger = logging.getLogger(__name__)

EventCallback = Callable[[str, Any], None]


# --- Tool layer ------------------------------------------------------------

@dataclass
class ToolResult:
    ok: bool
    output: str

    def __str__(self) -> str:
        prefix = "" if self.ok else "[ERROR] "
        return prefix + self.output


class AgentTools:
    """Filesystem + Python execution, all confined to one workspace dir."""

    MAX_READ_CHARS = 8_000
    MAX_OUTPUT_CHARS = 8_000
    PYTHON_TIMEOUT_S = 30

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)

    def _resolve(self, path: str) -> Path:
        """Resolve a user-provided path, refusing anything outside workspace."""
        if not isinstance(path, str):
            raise ValueError("path must be a string")
        candidate = (self.workspace / path).resolve()
        # Allow workspace itself or descendants only.
        try:
            candidate.relative_to(self.workspace)
        except ValueError:
            raise ValueError(f"Path escapes workspace: {path}")
        return candidate

    def write_file(self, path: str, content: str) -> ToolResult:
        p = self._resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if not isinstance(content, str):
            content = str(content)
        p.write_text(content, encoding="utf-8")
        return ToolResult(True, f"Wrote {len(content)} characters to {path}")

    def read_file(self, path: str) -> ToolResult:
        p = self._resolve(path)
        if not p.exists():
            return ToolResult(False, f"File not found: {path}")
        if p.is_dir():
            return ToolResult(False, f"That path is a directory: {path}")
        text = p.read_text(encoding="utf-8", errors="replace")
        if len(text) > self.MAX_READ_CHARS:
            text = text[: self.MAX_READ_CHARS] + "\n... (truncated)"
        return ToolResult(True, text)

    def list_dir(self, path: str = ".") -> ToolResult:
        p = self._resolve(path)
        if not p.exists():
            return ToolResult(False, f"Not found: {path}")
        if not p.is_dir():
            return ToolResult(False, f"Not a directory: {path}")
        items = []
        for entry in sorted(p.iterdir()):
            kind = "dir " if entry.is_dir() else "file"
            try:
                size = entry.stat().st_size if entry.is_file() else 0
            except OSError:
                size = 0
            items.append(f"{kind}  {entry.name}  ({size} bytes)")
        return ToolResult(True, "\n".join(items) if items else "(empty)")

    def run_python(self, code: str) -> ToolResult:
        if not isinstance(code, str):
            return ToolResult(False, "code must be a string")
        try:
            result = subprocess.run(
                [sys.executable, "-I", "-c", code],
                capture_output=True,
                text=True,
                timeout=self.PYTHON_TIMEOUT_S,
                cwd=str(self.workspace),
            )
        except subprocess.TimeoutExpired:
            return ToolResult(False, f"Timed out after {self.PYTHON_TIMEOUT_S}s")
        except Exception as exc:
            return ToolResult(False, f"Could not run Python: {exc}")
        out = result.stdout or ""
        if result.stderr:
            out += ("\n--- stderr ---\n" if out else "") + result.stderr
        if len(out) > self.MAX_OUTPUT_CHARS:
            out = out[: self.MAX_OUTPUT_CHARS] + "\n... (truncated)"
        ok = result.returncode == 0
        if not ok and not out:
            out = f"exit code {result.returncode}"
        return ToolResult(ok, out or "(no output)")


# --- Parsing ---------------------------------------------------------------

# Tolerant of whitespace variations: real LLM UIs preserve newlines inside
# <pre>/<code>, but some chat layouts (and `innerText` on non-pre elements)
# collapse them into single spaces.
_TOOL_BLOCK = re.compile(r"```\s*tool\b\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
_DONE_BLOCK = re.compile(r"```\s*done\b\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


@dataclass
class ParsedReply:
    tool: Optional[Dict[str, Any]] = None   # {"name": ..., "args": {...}}
    done_text: Optional[str] = None         # final answer if the LLM said done
    error: str = ""                         # parsing problem, sent back to LLM


def parse_reply(text: str) -> ParsedReply:
    """Pull a single ```tool or ```done block out of the LLM's response."""
    done = _DONE_BLOCK.search(text)
    if done:
        return ParsedReply(done_text=done.group(1).strip())

    tool = _TOOL_BLOCK.search(text)
    if tool:
        raw = tool.group(1).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            return ParsedReply(error=f"JSON in your ```tool block was invalid: {exc}")
        if not isinstance(data, dict) or "name" not in data:
            return ParsedReply(error="```tool JSON needs a 'name' field.")
        args = data.get("args", {})
        if not isinstance(args, dict):
            return ParsedReply(error="```tool 'args' must be a JSON object.")
        return ParsedReply(tool={"name": data["name"], "args": args})

    return ParsedReply(
        error="No ```tool or ```done block found. Wrap your call like:\n"
              "```tool\n{\"name\": \"list_dir\", \"args\": {\"path\": \".\"}}\n```"
    )


# --- The LLM contract ------------------------------------------------------

class _ChatBackend(Protocol):
    async def chat(self, message: str, timeout: float = ...) -> str: ...


_SYSTEM_PROMPT = """You are now a coding assistant. Forget any earlier conversation in this thread; only the instructions below apply from this point.

You work inside a sandbox directory. To do anything, respond with EXACTLY ONE tool call per turn, in this exact format:

```tool
{"name": "TOOL_NAME", "args": {ARGS}}
```

The available tools are:

- write_file(path, content): create or overwrite a file.
    Example args: {"path": "hello.py", "content": "print('hello')"}
- read_file(path): read a file from the workspace.
    Example args: {"path": "hello.py"}
- list_dir(path): list a directory. Use "." for the workspace root.
    Example args: {"path": "."}
- run_python(code): run Python code in the workspace and return stdout/stderr.
    Example args: {"code": "print(2+2)"}

Rules:
- Output one ```tool block per response and nothing else. No prose around it.
- After each tool call I will reply with the result. Then you decide the next step.
- When the task is finished, respond with a final summary in this exact format:

```done
Your one or two sentence summary of what you did.
```

Workspace path on disk: __WORKSPACE__

The user's task:
__TASK__
"""

_RETRY_HINT = (
    "Your last response could not be parsed. Reply with exactly one ```tool "
    "block (or a ```done block when finished) and no other text."
)


# --- Agent -----------------------------------------------------------------

class CodingAgent:
    """Drive a tool-using loop against any chat backend (the LLMBridge)."""

    def __init__(self, bridge: _ChatBackend, workspace: Path):
        self.bridge = bridge
        self.tools = AgentTools(workspace)
        self.workspace = self.tools.workspace

    async def run(
        self,
        task: str,
        on_event: EventCallback,
        max_steps: int = 15,
        per_call_timeout: float = 180.0,
    ) -> None:
        on_event("workspace", str(self.workspace))
        on_event("task", task)

        prompt = (
            _SYSTEM_PROMPT
            .replace("__WORKSPACE__", str(self.workspace))
            .replace("__TASK__", task)
        )
        for step in range(1, max_steps + 1):
            on_event("step", step)
            try:
                reply = await self.bridge.chat(prompt, timeout=per_call_timeout)
            except Exception as exc:
                on_event("error", f"LLM call failed: {exc}")
                return
            on_event("llm", reply)

            parsed = parse_reply(reply)
            if parsed.done_text is not None:
                on_event("done", parsed.done_text)
                return
            if parsed.error or parsed.tool is None:
                on_event("warning", parsed.error or "Could not parse a tool call.")
                prompt = _RETRY_HINT
                continue

            on_event("tool_call", parsed.tool)
            result = self._execute(parsed.tool)
            on_event("tool_result", result)
            prompt = (
                f"Result of `{parsed.tool['name']}`:\n```\n{result.output}\n```\n"
                "What's the next step?"
            )

        on_event("done", f"Reached max_steps ({max_steps}) without finishing.")

    def _execute(self, tool: Dict[str, Any]) -> ToolResult:
        name = tool.get("name", "")
        args = tool.get("args", {}) or {}
        fn = getattr(self.tools, name, None)
        if not callable(fn) or name.startswith("_"):
            return ToolResult(False, f"Unknown tool: {name!r}")
        try:
            return fn(**args)
        except TypeError as exc:
            return ToolResult(False, f"Wrong arguments for {name}: {exc}")
        except Exception as exc:
            return ToolResult(False, f"Tool {name} crashed: {exc}")
