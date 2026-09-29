# Universal WebUI Bridge

Talk to any web-based LLM (ChatGPT, Claude, Grok, Gemini, OpenWebUI, LM Studio,
Jan, Oobabooga, ...) from the terminal, a Streamlit GUI, or an HTTP API.

Logins persist via a **persistent browser profile** on disk: log in once per
service, stay logged in on every later run. No cookie copy-paste, no
"controlled by automation" warnings.

## Install

```
pip install -e .
python -m playwright install chromium
```

A real Google Chrome or Edge install will be used automatically when present,
which is friendlier to login flows than bundled Chromium.

## Three ways to use it

### 1. Terminal chat

```
webui-bridge                       # interactive menu, then chat
webui-bridge https://chatgpt.com   # skip the menu
```

A browser window opens. If the service needs you to log in, do that in the
window and press Enter in the terminal. After that it just chats:

```
You: write a haiku about debugging
Assistant: ...
```

### 2. Streamlit GUI

```
webui-bridge --gui
```

Pick a service, click *Open*, log in if asked, then chat in the page.

**Coding-agent mode.** Once you're in the chat screen, click *Open Agent CLI*.
The bridge starts an OpenAI-compatible HTTP server at
`http://localhost:8000/v1` and spawns a new terminal running a coding agent.
If **Pi** is installed and on your PATH it will be launched automatically.
Otherwise the built-in agent is used as a fallback.

The connected web LLM is the agent's brain. The bridge types messages into the
browser window and extracts responses — Pi or any other agent sees it as a
standard OpenAI-compatible API.

To use Pi directly:
```
pip install pi-agent           # or: npm install -g @pi-ai/pi
```
Then click *Open Agent CLI* in the GUI, or launch Pi yourself:
```
set OPENAI_BASE_URL=http://localhost:8000/v1
set OPENAI_API_KEY=webui-bridge
pi
```

### 3. HTTP API (for coding agents)

```
webui-bridge --serve https://chatgpt.com         # log in once, then it serves
```

```
curl -X POST localhost:8000/chat \
     -H "Content-Type: application/json" \
     -d '{"message":"hello"}'
# {"reply":"..."}
```

Endpoints:

| Method | Path     | Body / response                         |
|--------|----------|-----------------------------------------|
| POST   | `/chat`  | `{"message": "..."}` -> `{"reply":"..."}` |
| GET    | `/status`| current bridge state                    |
| GET    | `/health`| `{"ok": true}`                          |

## Python API

```python
import asyncio
from webui_bridge_v2 import LLMBridge, BridgeState

async def main():
    bridge = LLMBridge()                          # opens a real browser window
    status = await bridge.connect("https://chatgpt.com")
    if status.state is BridgeState.NEEDS_LOGIN:
        input("Log in in the window, then press Enter... ")
        await bridge.finish_login()
    print(await bridge.chat("Hello!"))
    await bridge.close()

asyncio.run(main())
```

## How login persistence works

The bridge launches Chrome with a dedicated profile directory at
`~/.universal_webui_bridge/profile/`. That directory holds your cookies,
localStorage, IndexedDB and service workers, exactly like a normal Chrome
profile. When you log into ChatGPT (or any other site) inside the bridge's
browser, that login is written to the profile. On the next run the same
profile is reused and you are still logged in.

The profile is on your machine and only used by the bridge. To "log out of
everything" just delete the directory.

## Supported services

Tested mechanically end-to-end against textarea and contenteditable mock UIs.
Live profiles ship for:

* ChatGPT, Claude, Gemini, Grok                (login required - once)
* OpenWebUI, LM Studio, Jan, Oobabooga         (local, no login)
* Anything else - paste the URL; heuristics will try to find the chat box

Selectors on big web apps drift. If a known site stops working, file an
issue with the URL and a one-line description.

## Troubleshooting

* **"Profile in use" / SingletonLock error** - a previous bridge window is
  still open. Close it and retry.
* **Chrome window opens but the GUI/CLI says "couldn't find the chat box"** -
  finish any login or splash screen in the window and click *I'm ready*.
* **Reply comes back as "(No reply detected...)"** - usually means the site
  uses a layout the heuristics did not match; report the URL.
* **`python -m playwright install chromium`** - run this if you see
  "Browser not installed" errors.

## Project layout

```
src/webui_bridge_v2/
    browser.py      persistent-profile Chrome session
    engine.py       detection + send + wait-for-reply
    core.py         LLMBridge public API
    profiles.py     known-UI selector hints
    cli.py          terminal client + entry point
    server.py       HTTP API for agents
    ui.py           Streamlit GUI
```

`src/webui_bridge/` is the older v1 implementation kept around for the unit
tests in `tests/`; everything new lives in `webui_bridge_v2`.

## Bonus: `auto-approve` Claude Code plugin

This repo also ships a small **Claude Code plugin** for anyone who runs Claude
Code (the CLI or the Desktop app) and wants it to run a prompt from start to
finish **without stopping to ask for permission on every step**.

```
/plugin marketplace add thesameoldthing88/universal-webui-bridge
/plugin install auto-approve@universal-webui-bridge
```

It installs a `PreToolUse` hook that auto-approves tool calls in any permission
mode, and comes with an off-switch (`CLAUDE_AUTOPILOT_DISABLE=1`) and a
per-tool "still ask me" list (`CLAUDE_AUTOPILOT_ASK`). See
[`plugins/auto-approve/README.md`](plugins/auto-approve/README.md) for the full
guide, the recommended `settings.json`, and the safety caveats (a few
destructive actions still prompt by design).

## License

MIT
