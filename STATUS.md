# Universal WebUI Bridge — Build Status

> Handoff / status report for the repo at `C:\Users\chadk\universal-webui-bridge`.
> `README.md` is the *usage* doc; this file is the *project* doc — what works,
> what's iffy, what's next. Last updated 2026-05-22.

## TL;DR

The bridge works end-to-end. You can connect a web LLM (the user has live-tested
Gemini), chat with it from a CLI / GUI / HTTP API, and one-click a button that
opens a terminal running a tool-using coding agent backed by that same LLM.

Build state: **working beta**. Mechanism verified by automated mock tests and
one live web-LLM session. Real-world breadth (every supported service, every
edge case) hasn't been exercised — see *known issues* below.

---

## What works (and how I verified it)

| Capability | How it was verified |
|---|---|
| Persistent login (cookies + localStorage survive across separate browser processes) | Empirical: two-process test wrote a marker, second process read it back |
| URL navigation (skips `networkidle` so SPA pages don't hang) | Engine + smoke tests |
| Chat input detection on `<textarea>` and `contenteditable` | Mock-tested both layouts |
| Send via button click, fallback to Enter | Mock; works on Gemini live |
| Reply detection via known selectors + 15 generic patterns + body-text diff with longest-common-prefix/suffix | Mock-tested with class-based mock and a no-matching-selector mock; live on Gemini |
| Wait-for-stable streaming (don't return mid-stream) | Mock streams word-by-word; engine waits for 2.5s of stability |
| Strip user-message echo from body diff | JS-side suffix trim before returning |
| CLI chat (`webui-bridge https://...`) with live spinner | Confirmed by hand + smoke test |
| Streamlit GUI on a background event loop | Imports + worker round-trip tested |
| HTTP API: `/chat`, `/status`, `/health` | curl roundtrip test |
| OpenAI-compatible HTTP API: `/v1/chat/completions`, `/v1/models` | Full E2E: external subprocess agent called it and got real replies back |
| GUI button "Open Agent CLI" starts the HTTP server and spawns a new console window with the agent | E2E test with `CREATE_NEW_CONSOLE` |
| Coding-agent loop (tools: `write_file` / `read_file` / `list_dir` / `run_python`) | E2E with mock LLM emitting `tool` / `done` JSON blocks; real file written to disk |
| Sandbox: workspace path traversal refused | Unit test (`AgentTools._resolve`) |
| 48 legacy unit tests (`tests/test_bridge.py`) still pass | `pytest tests/` clean after every change |

---

## Project layout

```
src/
  webui_bridge_v2/         <- current package; everything here is wired
    browser.py             persistent Chrome/Edge/Chromium profile session
    engine.py              detect / send / wait_for_reply (multi-selector + body diff)
    core.py                LLMBridge public API
    profiles.py            best-effort selectors per known site
    server.py              aiohttp API (custom + OpenAI shim)
    cli.py                 terminal client + --agent-cli + --gui + --serve
    ui.py                  Streamlit GUI (BridgeWorker pattern)
    agent.py               tool-using coding agent loop
    __main__.py            entry point for python -m webui_bridge_v2
  webui_bridge/            <- v1, legacy; kept only because tests/test_bridge.py runs
                              against it. NOT used by anything in v2.
gui/                       <- v1-era files (orphan; targets webui_bridge).
                              Kept untouched but unreachable from the new flow.
tests/test_bridge.py       <- v1 unit tests (48, all mocked)
README.md                  usage doc
STATUS.md                  THIS file
ROADMAP.md                 historical record of the original audit
pyproject.toml             v2.1.0, entry point: webui-bridge -> webui_bridge_v2.cli:main
```

---

## Things that might need to be fixed

Ordered by risk × likelihood.

1. **Real-site selectors drift.** Profiles ship with current-as-of-2026-05-22
   selectors for ChatGPT, Claude, Gemini, Grok, OpenWebUI, LM Studio, Jan,
   Oobabooga. Sites redesign their DOM regularly. The body-diff fallback
   catches most drift, but the reply may include UI chrome text ("Copy",
   "Like") tacked on. Symptoms: replies have weird trailing words.
   *Fix path:* tune `assistant_selector` per site as drift happens.

2. **Body-diff can return UI chrome.** The longest-common-suffix trim helps,
   but mid-page UI changes (typing indicators, toolbar tooltips) can pollute
   the delta. *Fix path:* scope the diff to a heuristically-detected
   conversation container instead of `document.body`.

3. **No streaming yet.** `chat()` waits for the full reply, then returns it.
   The CLI shows a spinner so it doesn't *look* dead, but tokens don't appear
   live. *Fix path:* SSE on `/v1/chat/completions`; engine already polls
   incrementally — expose those poll results as a generator.

4. **No "new chat" automation.** When you flip from chat → agent, the LLM's
   own conversation history can confuse it. The system prompt says "forget
   prior conversation" but compliance varies. *Fix path:* per-profile selector
   for the "New chat" button; click it before the first agent prompt.

5. **`run_python` isn't truly sandboxed.** It runs `python -I` in a
   subprocess `cwd=workspace` with a 30s timeout. The code can still do
   anything Python can do on your machine (network, env, your home dir).
   Filesystem tools are constrained to the workspace; Python isn't.
   *Fix path:* none simple. Document the trust boundary clearly; require
   user confirmation for `run_python`; or move to a container.

6. **Windows-only verification for terminal-spawning.** The GUI's
   `_open_agent_cli` has code for macOS (`osascript`) and Linux
   (`gnome-terminal`/`konsole`/...), but only Windows
   `CREATE_NEW_CONSOLE` has been exercised. The other branches are
   written but untested.

7. **HTTP API has no auth.** Anything on localhost can `POST /chat`. Fine
   for a single-user dev tool, not OK if you forward the port. *Fix path:*
   accept a token via env var, check `Authorization: Bearer` header.

8. **Single bridge, single conversation.** One `LLMBridge` instance =
   one browser tab = one chat. The HTTP server serializes calls through a
   lock. No way to talk to two LLMs at once. *Fix path:* multi-bridge
   server (separate profile dirs, routing by model id).

9. **Bridge cleanup on hard exit.** Ctrl+C in the CLI usually closes
   Playwright cleanly. A SIGKILL or unexpected crash can leave a Chromium
   subprocess behind. The persistent profile dir generally still survives
   (it's just files). If the next run says "profile in use", close the
   stray Chromium window.

10. **Tests are ad-hoc + the 48 v1 unit tests test the legacy package.**
    The new modules don't have a pytest suite — verification has been
    "write a smoke script, run it, delete it." *Fix path:* port the smoke
    scripts to `tests/test_v2/`. Mark live-LLM tests as slow/optional.

11. **Streamlit UI write-from-thread.** The BridgeWorker thread updates
    a queue, but Streamlit's session_state writes happen on the main
    thread that reads the queue (so we don't actually do cross-thread
    writes). Still, Streamlit's threading rules are loose; on heavy
    pages this might glitch. Not observed.

12. **Edge-channel persistent-context launches always emit a benign
    "Settings version is not 7" warning** on this machine. It's a
    crashpad version mismatch; Playwright recovers and launches anyway.
    Cosmetic noise.

---

## Where I'd go with more time

In priority order:

1. **Streaming end-to-end.** Server-sent events on
   `/v1/chat/completions`, partial-text yields from `engine.wait_for_reply`,
   live token rendering in the CLI and GUI. This is the highest-impact UX
   improvement.

2. **Per-site selector hardening.** Live-test against each profile, fix
   what breaks, refine `assistant_selector` and `streaming_selector`.
   ChatGPT and Claude in particular need this since they're the
   most-likely-to-be-used.

3. **Reply text cleanup.** Strip "Copy" / "Edit" / "Share" / model-name
   chrome from extracted text. Probably a per-profile post-processor.

4. **"New chat" automation.** A `new_chat_selector` field in profiles plus
   an `engine.new_conversation()` call invoked before each agent run.

5. **macOS + Linux verification.** Boot a VM, test the terminal-launching
   code paths, tweak as needed.

6. **HTTP auth + multi-conversation.** Token-gated endpoint; multiple
   `LLMBridge` instances keyed by an opaque "session id" or by which
   profile-dir to use.

7. **Proper test suite.** Move the smoke scripts into `tests/test_v2/`,
   gate live-LLM tests behind a `--live` marker, run unit tests in CI.

8. **More tools.** `run_shell` (with confirmation), `apply_patch` for
   edit operations, an optional `web_search` that goes through the
   connected LLM. Keep the tool list short by default.

9. **Cost/timing telemetry.** Show "agent used N LLM calls, took Ts" in
   the GUI. Useful for debugging long-running runs.

10. **Bring back the in-app agent panel as an alternative to the
    terminal.** Some users will prefer to stay in the browser. The code
    that did this was deleted in the latest pivot but is in git history.

11. **Package + ship.** PyPI release, GitHub Actions running the unit
    tests, a small homepage. Right now it's "clone + pip install -e .".

---

## How to pick this up cold (for another agent or future me)

1. Read this file, then `README.md`.
2. `cd C:\Users\chadk\universal-webui-bridge`
3. `python -m pip install -e .` (already done on this machine)
4. `pytest tests/test_bridge.py` → expect 48 passing.
5. Smoke: `python -m py_compile src/webui_bridge_v2/*.py`.
6. Live try: `webui-bridge --gui`, pick Gemini, log in (or use the saved
   profile), click *Open Agent CLI*, ask the agent to do something small.
7. The agent's sandbox: `~/.universal_webui_bridge/agent_workspace/<ts>/`.
8. The Chrome login profile: `~/.universal_webui_bridge/profile/`.

If something is broken: check `engine.py` for detection issues; check
`server.py` for HTTP issues; check `agent.py` for tool-loop issues. The
modules are kept small on purpose.

---

## Acceptance checklist (definition of "done enough")

- [x] Connect to a real web LLM and exchange a message
- [x] Stay logged in across runs without re-typing credentials
- [x] HTTP API speaks OpenAI Chat Completions
- [x] Click a button → external terminal opens → coding agent runs against the connected LLM
- [x] Agent writes real files in a sandbox and reports back
- [x] 48 legacy unit tests still pass
- [ ] Pytest suite for the new modules
- [ ] Streaming tokens end-to-end
- [ ] Verified live against ChatGPT and Claude (only Gemini live-tested so far)
- [ ] macOS + Linux verified
