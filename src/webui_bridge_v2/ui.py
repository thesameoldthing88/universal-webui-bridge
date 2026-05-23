"""
Streamlit GUI.

Launched by:
    webui-bridge --gui
    # or:  python -m streamlit run src/webui_bridge_v2/ui.py

The Playwright bridge is async and the browser must outlive Streamlit's
rerun-on-every-interaction model, so all bridge work happens on a single
background event loop owned by a BridgeWorker that lives in st.session_state.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

import streamlit as st

from webui_bridge_v2 import BridgeState, LLMBridge
from webui_bridge_v2.profiles import QUICK_PICKS


class BridgeWorker:
    """One background event loop + one LLMBridge, lifetime = browser session."""

    def __init__(self, headless: bool = False):
        self.loop = asyncio.new_event_loop()
        self.bridge = LLMBridge(headless=headless)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._http_runner = None
        self._http_port: Optional[int] = None

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _call(self, coro, timeout: Optional[float] = None):
        fut = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return fut.result(timeout=timeout)

    def connect(self, url: str):
        return self._call(self.bridge.connect(url), timeout=120)

    def finish_login(self):
        return self._call(self.bridge.finish_login(timeout=180), timeout=200)

    def chat(self, message: str, timeout: float = 120.0) -> str:
        return self._call(self.bridge.chat(message, timeout=timeout), timeout=timeout + 15)

    def start_http_server(self, port: int = 8000) -> int:
        """Bring up the bridge HTTP API. Idempotent. Returns the bound port."""
        return self._call(self._start_http_coro(port), timeout=15)

    async def _start_http_coro(self, port: int) -> int:
        if self._http_runner is not None and self._http_port is not None:
            return self._http_port
        from aiohttp import web
        from webui_bridge_v2.server import build_app

        app = build_app(self.bridge)
        runner = web.AppRunner(app)
        await runner.setup()
        # Try the requested port; if it's busy, fall back to an OS-assigned one.
        for p in (port, 0):
            try:
                site = web.TCPSite(runner, "127.0.0.1", p)
                await site.start()
                break
            except OSError:
                continue
        else:
            await runner.cleanup()
            raise RuntimeError("Could not bind any port for the HTTP server")
        self._http_runner = runner
        self._http_port = site._server.sockets[0].getsockname()[1]
        return self._http_port

    def close(self) -> None:
        try:
            if self._http_runner is not None:
                try:
                    self._call(self._http_runner.cleanup(), timeout=5)
                except Exception:
                    pass
                self._http_runner = None
                self._http_port = None
            self._call(self.bridge.close(), timeout=20)
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)


# --- session-state helpers --------------------------------------------------

def _worker() -> BridgeWorker:
    if "worker" not in st.session_state:
        st.session_state.worker = BridgeWorker(headless=False)
    return st.session_state.worker


def _init_state() -> None:
    st.session_state.setdefault("phase", "pick")
    st.session_state.setdefault("url", "")
    st.session_state.setdefault("service", "")
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("login_message", "")
    st.session_state.setdefault("login_hint", "")
    st.session_state.setdefault("agent_url", "")
    st.session_state.setdefault("agent_type", "")
    st.session_state.setdefault("agent_workspace", "")


def _reset_session() -> None:
    if "worker" in st.session_state:
        try:
            st.session_state.worker.close()
        except Exception:
            pass
    for k in ("worker", "phase", "url", "service", "messages",
              "agent_url", "agent_type", "agent_workspace"):
        st.session_state.pop(k, None)


# --- pages ------------------------------------------------------------------

def _render_pick() -> None:
    st.subheader("1. Pick a service")
    options: list[tuple[str, str, str]] = []
    for group, services in QUICK_PICKS.items():
        for name, url in services.items():
            options.append((group, name, url))
    labels = [f"{name}   ({url})" for _, name, url in options]
    default_idx = next(
        (i for i, (g, _, _) in enumerate(options) if g.startswith("Web")), 0
    )
    pick = st.selectbox("Service", labels, index=default_idx, label_visibility="collapsed")
    url = options[labels.index(pick)][2]
    name = options[labels.index(pick)][1]

    custom = st.text_input("Or paste any URL", value="", placeholder="https://example.com/chat")
    if custom.strip():
        url = custom.strip()
        name = "Custom"

    st.caption(
        "A real browser window will open. You only log in the first time - "
        "your session is saved to disk and reused on every later run."
    )

    if st.button("Open", type="primary", use_container_width=True):
        with st.spinner(f"Opening {url} ..."):
            status = _worker().connect(url)
        st.session_state.url = url
        st.session_state.service = name
        if status.state is BridgeState.READY:
            st.session_state.phase = "chat"
        elif status.state is BridgeState.NEEDS_LOGIN:
            st.session_state.phase = "login"
            st.session_state.login_message = status.message
            st.session_state.login_hint = status.hint
        else:
            st.error(f"{status.message}\n\n{status.hint}")
            return
        st.rerun()


def _render_login() -> None:
    st.subheader(f"2. Log in to {st.session_state.service}")
    st.info(st.session_state.login_message or "Log in inside the browser window.")
    if st.session_state.login_hint:
        st.caption(st.session_state.login_hint)
    st.write(
        "A browser window is open. Sign in there if asked, get to the chat "
        "screen, then click the button below."
    )
    cols = st.columns([1, 1])
    if cols[0].button("I'm ready - continue", type="primary", use_container_width=True):
        with st.spinner("Looking for the chat input..."):
            status = _worker().finish_login()
        if status.state is BridgeState.READY:
            st.session_state.phase = "chat"
            st.rerun()
        else:
            st.error(f"{status.message}\n\n{status.hint}")
    if cols[1].button("Start over", use_container_width=True):
        _reset_session()
        st.rerun()


def _detect_pi_cmd() -> Optional[list]:
    """Find the Pi coding-agent CLI on PATH. Returns the argv list or None."""
    import shutil as _sh
    for name in ("pi", "pi-agent"):
        path = _sh.which(name)
        if path:
            return [path]
    return None


def _spawn_terminal(cmd: list, env: dict, cwd: Optional[str] = None) -> None:
    """Open a new terminal window, optionally starting in `cwd`."""
    if sys.platform == "win32":
        import subprocess as _sp

        bat_path = os.path.join(os.path.dirname(__file__), "..", "..", "_launch_agent.bat")
        lines = ["@echo off"]
        if cwd:
            # `cd /d` because cwd may be on a different drive than where the
            # bat file lives.
            lines.append(f'cd /d "{cwd}"')
        for k in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE"):
            if k in env:
                lines.append(f'set "{k}={env[k]}"')
        # Show the user where they are before handing off to the agent.
        lines.append("")
        lines.append("echo ===== Universal WebUI Bridge =====")
        lines.append("echo Workspace: %CD%")
        lines.append("echo Bridge:    %OPENAI_BASE_URL%")
        lines.append("echo.")
        lines.append(subprocess.list2cmdline(cmd))
        lines.append("")
        with open(bat_path, "w") as fh:
            fh.write("\n".join(lines))
        _sp.Popen(f'cmd.exe /c start "" "{bat_path}"', shell=True)
    elif sys.platform == "darwin":
        cmd_str = " ".join(f'"{c}"' for c in cmd)
        env_str = " ".join(f'{k}="{v}"' for k, v in env.items()
                           if k in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE"))
        cd_str = f'cd \\"{cwd}\\" && ' if cwd else ""
        script = f'tell app "Terminal" to do script "{cd_str}{env_str} {cmd_str}"'
        subprocess.Popen(["osascript", "-e", script])
    else:
        import shutil as _sh
        for term in ("x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal", "xterm"):
            if _sh.which(term):
                subprocess.Popen([term, "-e"] + cmd, env=env, cwd=cwd)
                break


def _register_bridge_in_pi_config(base_url: str, service_name: str) -> None:
    """Add the bridge as a provider in Pi's config. Also set it as the default."""
    pi_config_dir = Path.home() / ".pi" / "agent"
    pi_config_dir.mkdir(parents=True, exist_ok=True)
    model_id = service_name.lower().replace(" ", "-")

    # --- models.json: add the bridge provider ---
    models_path = pi_config_dir / "models.json"
    if models_path.exists():
        try:
            models = json.loads(models_path.read_text())
        except Exception:
            models = {}
    else:
        models = {}
    if "providers" not in models:
        models["providers"] = {}

    models["providers"]["webui-bridge"] = {
        "api": "openai-completions",
        "apiKey": "webui-bridge",
        "baseUrl": f"{base_url}/v1",
        "models": [
            {
                "_launch": True,
                "id": model_id,
                "name": f"Connected ({service_name})",
                "contextWindow": 128000,
                "input": ["text"],
            }
        ],
    }
    models_path.write_text(json.dumps(models, indent=2))

    # --- settings.json: make webui-bridge the default provider ---
    settings_path = pi_config_dir / "settings.json"
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except Exception:
            settings = {}
    else:
        settings = {}
    settings["defaultProvider"] = "webui-bridge"
    settings["defaultModel"] = model_id
    settings_path.write_text(json.dumps(settings, indent=2))


def _open_agent_cli() -> None:
    """Start the HTTP server and spawn a new terminal running a coding agent."""
    import datetime as _dt

    worker = _worker()
    port = worker.start_http_server(port=8000)
    base_url = f"http://localhost:{port}"
    st.session_state.agent_url = base_url

    # Fresh, per-launch workspace so Pi (or the built-in agent) writes its
    # project files into a clean dir instead of polluting the bridge's source.
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    workspace = Path.home() / ".universal_webui_bridge" / "pi_workspace" / stamp
    workspace.mkdir(parents=True, exist_ok=True)
    st.session_state.agent_workspace = str(workspace)

    env = {
        **os.environ,
        "OPENAI_API_KEY": "webui-bridge",
        "OPENAI_BASE_URL": f"{base_url}/v1",
        "OPENAI_API_BASE": f"{base_url}/v1",
    }

    pi = _detect_pi_cmd()
    if pi:
        _register_bridge_in_pi_config(base_url, st.session_state.service)
        _spawn_terminal(pi, env, cwd=str(workspace))
        st.session_state.agent_type = "pi"
    else:
        cmd = [sys.executable, "-m", "webui_bridge_v2", "--agent-cli", base_url]
        _spawn_terminal(cmd, env, cwd=str(workspace))
        st.session_state.agent_type = "builtin"


def _render_chat() -> None:
    cols = st.columns([3, 1, 1])
    cols[0].subheader(st.session_state.service)
    cols[0].caption(st.session_state.url)
    if cols[1].button("Open Agent CLI", type="primary", use_container_width=True,
                      help="Opens a new terminal running a coding agent that uses "
                           "this connection as its LLM."):
        _open_agent_cli()
    if cols[2].button("Disconnect", use_container_width=True):
        _reset_session()
        st.rerun()

    if st.session_state.agent_url:
        ws = st.session_state.agent_workspace
        if st.session_state.agent_type == "pi":
            st.success(
                f"Pi terminal launched. Pi is using the web LLM as its brain via "
                f"**{st.session_state.agent_url}/v1**.\n\n"
                f"Files Pi creates will land in:  \n`{ws}`"
            )
        else:
            st.info(
                f"Built-in agent launched (Pi not found on PATH). Bridge is serving "
                f"at **{st.session_state.agent_url}/v1**. Install Pi "
                f"(`npm install -g @pi-ai/pi` or `pip install pi-agent`) and re-launch "
                f"to use it instead.\n\nWorkspace:  \n`{ws}`"
            )

    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.write(m["content"])

    prompt = st.chat_input("Type your message...")
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Waiting for reply..."):
                try:
                    reply = _worker().chat(prompt)
                except Exception as exc:
                    reply = f"Error: {exc}"
            st.write(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})


# --- main -------------------------------------------------------------------

def main() -> None:
    st.set_page_config(page_title="Universal WebUI Bridge", page_icon="🌉", layout="centered")
    st.title("Universal WebUI Bridge")
    _init_state()
    phase = st.session_state.phase
    if phase == "pick":
        _render_pick()
    elif phase == "login":
        _render_login()
    else:
        _render_chat()


if __name__ == "__main__":
    main()
