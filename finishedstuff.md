# Finished Stuff — Session Summary

Date: 2026-05-22

---

## Overview

This session integrated **Pi** (the coding agent CLI) into the Universal WebUI Bridge. Previously, the GUI had an "Open Agent CLI" button that launched a built-in agent. Now, it detects Pi on PATH and launches it instead, wiring it to the bridge's OpenAI-compatible HTTP API so Pi uses whatever web LLM is connected (ChatGPT, Claude, Gemini, Grok, etc.) as its brain.

## Files Changed

### 1. `src/webui_bridge_v2/agent.py` — Crash Bug Fix

**Problem:** `json.loads()` called on line 160 but `json` was never imported. Would crash immediately if the built-in CodingAgent was used.

**Fix:** Added `import json` at line 23.

```python
import json  # <-- added
```

---

### 2. `src/webui_bridge_v2/browser.py` — Stale Browser Profile Cleanup

**Problem:** If the previous bridge session crashed or was force-killed, Chrome/Edge leaves lock files (`SingletonLock`, `SingletonCookie`, etc.) and lingering processes in `~/.universal_webui_bridge/profile/`. The next launch fails with "Opening in existing browser session" / "SingletonLock" errors.

**Fix:** Added two new functions called in `BrowserSession.start()` before launching the browser:

- **`_clean_profile_locks(profile_dir)`** — Deletes stale lock files:
  - `SingletonLock`, `SingletonSocket`, `SingletonCookie`, `Lockfile`, `.lock` from the profile directory
  - Also checks parent directory for `SingletonLock`

- **`_kill_lingering_chrome(profile_dir)`** — Kills browser processes holding the profile open:
  - **Windows:** Uses `wmic process where` to find and delete processes with `chrome`, `msedge`, or `chromium` in the name and the profile path in their command line
  - **Linux/macOS:** Uses `pkill -f` with SIGTERM then SIGKILL

Added imports: `import subprocess as _sp`, `import sys as _sys`

---

### 3. `src/webui_bridge_v2/ui.py` — Major Pi Integration (Core Changes)

This was the main file changed. Here's every modification:

#### 3a. New imports
Added `import json` and `from pathlib import Path` to module-level imports.

#### 3b. `_detect_pi_cmd()` — New function
Finds Pi on the system PATH. Checks for `pi` and `pi-agent` (both npm and pip install names). Returns the bare command name (not full path) so cmd.exe can resolve it via PATHEXT.

```python
def _detect_pi_cmd() -> Optional[list]:
    import shutil as _sh
    for name in ("pi", "pi-agent"):
        if _sh.which(name):
            return [name]
    return None
```

#### 3c. `_spawn_terminal()` — Rewritten for Windows
Replaced the old `CREATE_NEW_CONSOLE` subprocess approach with a batch-file launcher pattern. This is necessary because:
- `CreateProcess` cannot execute `.cmd`/`.bat`/`.ps1` files directly
- `CREATE_NEW_CONSOLE` loses environment variable propagation through PowerShell
- Pi is installed via npm as `pi.CMD` and the old code tried to pass it to `CreateProcess` directly — `FileNotFoundError`

**New approach:**
1. Writes a temporary `.bat` file to the project root (`_launch_agent.bat`)
2. Sets `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `OPENAI_API_BASE` env vars in the batch file
3. Runs the CLI command via `subprocess.list2cmdline()` for proper Windows quoting
4. Uses `cmd.exe /c start "" "path\to\batch.bat"` to open a new console window

```python
def _spawn_terminal(cmd: list, env: dict) -> None:
    if sys.platform == "win32":
        import subprocess as _sp
        bat_path = os.path.join(os.path.dirname(__file__), "..", "..", "_launch_agent.bat")
        lines = ["@echo off"]
        for k in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE"):
            if k in env:
                lines.append(f'set "{k}={env[k]}"')
        lines.append("")
        lines.append(subprocess.list2cmdline(cmd))
        lines.append("")
        with open(bat_path, "w") as fh:
            fh.write("\n".join(lines))
        _sp.Popen(f'cmd.exe /c start "" "{bat_path}"', shell=True)
```

#### 3d. `_register_bridge_in_pi_config()` — New function
Programmatically adds the bridge as a provider in Pi's own configuration files so it appears in Pi's model selection UI and auto-connects.

**What it does:**
1. **Writes to `~/.pi/agent/models.json`:**
   - Adds a `webui-bridge` provider entry
   - Sets `api: "openai-completions"` (Pi knows how to talk this protocol)
   - Sets `baseUrl` to `http://localhost:8000/v1`
   - Sets `apiKey: "webui-bridge"` (required; bridge doesn't validate it)
   - Creates a model entry with `_launch: true` for auto-selection
   - Model ID is derived from the connected service name (e.g., "gemini" for Gemini)

2. **Writes to `~/.pi/agent/settings.json`:**
   - Sets `defaultProvider: "webui-bridge"` so Pi uses it automatically
   - Sets `defaultModel` to the service-specific model ID

```python
def _register_bridge_in_pi_config(base_url: str, service_name: str) -> None:
    pi_config_dir = Path.home() / ".pi" / "agent"
    pi_config_dir.mkdir(parents=True, exist_ok=True)
    model_id = service_name.lower().replace(" ", "-")
    # ... writes models.json and settings.json
```

#### 3e. `_open_agent_cli()` — Rewritten
Changed from launching the built-in CodingAgent to:
1. Starting the HTTP server (unchanged)
2. Detecting Pi on PATH
3. If Pi found: registers bridge in Pi config, launches Pi with env vars, sets `agent_type = "pi"`
4. If Pi not found: launches built-in CodingAgent as fallback, sets `agent_type = "builtin"`

#### 3f. Chat page messaging
Updated to show different messages depending on which agent was launched:
- **Pi launched:** Success message explaining the bridge API URL
- **Fallback:** Info message with Pi install instructions

#### 3g. Session state
Added `agent_type` to session state tracking and reset logic.

---

### 4. `src/webui_bridge_v2/cli.py` — CLI Updates

- Updated `--agent-cli` help text to mention Pi
- Updated `run_agent_cli()` banner to include Pi usage hint
- Removed stale "click New chat" tip (replaced with Pi instructions)

---

### 5. `src/webui_bridge_v2/server.py` — Relative Import Fix

**Problem:** `from .server import build_app` failed with "ImportError: attempted relative import with no known parent package" when called from `BridgeWorker._start_http_coro` which runs in a background thread's event loop.

**Fix:** Changed to absolute import: `from webui_bridge_v2.server import build_app`

---

### 6. `README.md` — Documentation Updated

- Replaced built-in agent documentation with Pi-focused instructions
- Added Pi install commands (`pip install pi-agent` / `npm install -g @pi-ai/pi`)
- Added manual Pi launch instructions with env vars

---

## Architecture: How Pi Connects to the Web LLM

```
┌─────────────────────────────────────────────────────────────────────┐
│  Browser Window (ChatGPT / Claude / Gemini / Grok / etc.)           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  User's chat session (logged in via persistent profile)      │   │
│  │  Bridge types messages → browser reads responses            │   │
│  └─────────────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ Playwright automation
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  LLMBridge (core.py) + ChatEngine (engine.py)                        │
│  • detect()  — find chat input on page                              │
│  • send()    — type message, click button/Enter                     │
│  • wait_for_reply() — poll selectors + body-text diff               │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ bridge.chat()
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  HTTP Server (server.py) — localhost:8000                            │
│  POST /v1/chat/completions   ← OpenAI Chat Completions wire format  │
│  GET  /v1/models              ← model list                          │
│  GET  /status                 ← bridge state                        │
│  GET  /health                 ← {"ok": true}                        │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ HTTP request
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Pi (pi.ps1 / pi.cmd) launched in new terminal                       │
│  • Reads ~/.pi/agent/settings.json → defaultProvider: "webui-bridge"│
│  • Reads ~/.pi/agent/models.json → baseUrl: localhost:8000/v1       │
│  • env: OPENAI_BASE_URL, OPENAI_API_KEY set by batch launcher       │
│  • Pi treats the web LLM like a standard OpenAI API endpoint        │
│  • All user prompts → bridge → browser → web LLM → response → Pi   │
└─────────────────────────────────────────────────────────────────────┘
```

## Bugs Fixed This Session

| # | Bug | File | Root Cause | Fix |
|---|-----|------|-----------|-----|
| 1 | `ImportError: attempted relative import` | `ui.py` | `from .server import build_app` in background thread loses `__package__` context | Changed to `from webui_bridge_v2.server import build_app` |
| 2 | `NameError: name 'json' is not defined` | `agent.py` | `import json` was missing; `json.loads()` called on line 160 | Added `import json` |
| 3 | "Opening in existing browser session" crash | `browser.py` | Stale Chrome lock files (`SingletonLock`) from previous crash | Added `_clean_profile_locks()` and `_kill_lingering_chrome()` |
| 4 | `FileNotFoundError` when spawning Pi | `ui.py` | `.CMD`/`.ps1` passed directly to `CreateProcess` which can't execute scripts | Rewrote `_spawn_terminal()` to use batch-file launcher pattern |
| 5 | "Windows cannot find '\\'" crash from `start` command | `ui.py` | `start` misinterpreted backslashes in temp path; also path was unquoted | Switched to project-root batch file `_launch_agent.bat`, proper quoting with `cmd.exe /c start "" "path"`, `shell=True` |

## Tests

All 48 legacy v1 unit tests pass:
```
48 passed in 0.34s
```

All v2 modules compile clean (`py_compile`).

## Verification

The bridge HTTP API was tested live:
```
POST /v1/chat/completions {"messages":[{"role":"user","content":"say hello world"}],"model":"webui-bridge"}
→ {"choices":[{"message":{"content":"Hello world!"}}]}
```

The full round-trip works: browser → engine → bridge → HTTP API → Pi can receive real LLM responses.

## How to Use

1. `webui-bridge --gui` (or `Start_Bridge.bat`)
2. Pick a service (e.g., Gemini, ChatGPT, Claude)
3. Log in if needed (one-time per service)
4. In chat screen, click **Open Agent CLI**
5. Pi opens in a new terminal, already configured to use the bridge
6. Type any coding task in Pi — the web LLM responds

## Remaining Work (Not Done This Session)

- `run_python` tool in built-in agent is not truly sandboxed
- No SSE streaming yet (chat() waits for full reply)
- HTTP API has no authentication
- Only Windows terminal spawning verified (macOS/Linux untested)
- Pi may need model selection confirmation on first launch
