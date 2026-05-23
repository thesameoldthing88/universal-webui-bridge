"""
Interactive terminal client.

Usage:
    python -m webui_bridge_v2                          # menu + chat loop
    python -m webui_bridge_v2 <url>                    # skip menu
    python -m webui_bridge_v2 --serve [--url <url>]    # HTTP server for agents
    python -m webui_bridge_v2 --headless <url>         # no visible browser
                                                       # (only useful when
                                                       #  already logged in)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from typing import List, Optional, Tuple

from .core import BridgeState, LLMBridge, normalize_url
from .profiles import QUICK_PICKS, detect_profile


def _flatten_menu() -> List[Tuple[str, str, str]]:
    """[(group, name, url), ...] in the order shown to the user."""
    items: List[Tuple[str, str, str]] = []
    for group, services in QUICK_PICKS.items():
        for name, url in services.items():
            items.append((group, name, url))
    return items


def _print_menu() -> None:
    print()
    print("=" * 56)
    print("  Universal WebUI Bridge")
    print("=" * 56)
    last_group = ""
    items = _flatten_menu()
    for i, (group, name, url) in enumerate(items, start=1):
        if group != last_group:
            print(f"\n  {group}:")
            last_group = group
        print(f"    {i:>2}) {name:<14} {url}")
    print(f"\n    {len(items)+1:>2}) Custom URL")
    print(f"     q) Quit\n")


def _pick_url() -> Optional[str]:
    items = _flatten_menu()
    while True:
        _print_menu()
        choice = input(f"Pick [1-{len(items)+1}] or q: ").strip().lower()
        if choice in ("q", "quit", "exit"):
            return None
        if choice == str(len(items) + 1) or choice == "c":
            url = input("Enter URL: ").strip()
            if url:
                return url
            continue
        try:
            idx = int(choice)
            if 1 <= idx <= len(items):
                return items[idx - 1][2]
        except ValueError:
            pass
        print("Please enter a number from the list.\n")


async def _aio_input(prompt: str) -> str:
    return await asyncio.to_thread(input, prompt)


async def _connect_with_login_pause(bridge: LLMBridge, url: str) -> bool:
    """Connect, then walk the user through any login that's needed."""
    print(f"\nOpening {url} ...")
    status = await bridge.connect(url)

    while status.state is BridgeState.NEEDS_LOGIN:
        print(f"\n  {status.message}")
        if status.hint:
            print(f"  ({status.hint})")
        print("\n  Log in inside the browser window if needed, then come back here.")
        await _aio_input("  Press Enter when you're on the chat screen... ")
        status = await bridge.finish_login()

    if status.state is BridgeState.READY:
        print(f"\n  {status.message}")
        return True
    print(f"\n  Error: {status.message}")
    if status.hint:
        print(f"  Hint: {status.hint}")
    return False


# --- Interactive chat ------------------------------------------------------

async def run_chat(url: Optional[str], headless: bool) -> int:
    if not url:
        url = _pick_url()
        if not url:
            return 0

    bridge = LLMBridge(headless=headless)
    try:
        if not await _connect_with_login_pause(bridge, url):
            return 1

        print("\nType a message. Commands: /quit  /clear  /help\n")
        while True:
            try:
                msg = await _aio_input("You: ")
            except (EOFError, KeyboardInterrupt):
                print()
                break

            cmd = msg.strip().lower()
            if cmd in ("/quit", "/exit", ":q"):
                break
            if cmd in ("/help", "?"):
                print("  /quit  - leave chat (browser closes; login is saved)")
                print("  /clear - clear local history (does not affect the web UI)")
                continue
            if cmd == "/clear":
                bridge.history.clear()
                print("  (local history cleared)")
                continue
            if not msg.strip():
                continue

            reply = await _await_reply_with_spinner(bridge.chat(msg))
            print(reply, "\n")
        return 0
    finally:
        await bridge.close()


async def _await_reply_with_spinner(coro) -> str:
    """Run `coro` while showing a live waiting indicator in the terminal."""
    task = asyncio.create_task(coro)
    spinner = "|/-\\"
    start = time.monotonic()
    i = 0
    print("  (waiting...)  ", end="", flush=True)
    try:
        while True:
            try:
                reply = await asyncio.wait_for(asyncio.shield(task), timeout=0.25)
                break
            except asyncio.TimeoutError:
                i += 1
                elapsed = int(time.monotonic() - start)
                print(
                    f"\r  ({spinner[i % 4]} waiting for reply... {elapsed}s)  ",
                    end="",
                    flush=True,
                )
    except (KeyboardInterrupt, asyncio.CancelledError):
        task.cancel()
        try:
            await task
        except Exception:
            pass
        print("\r  (interrupted)" + " " * 40)
        raise
    except Exception as exc:
        task.cancel()
        try:
            await task
        except Exception:
            pass
        print(f"\r  [error] {exc}" + " " * 40)
        return ""
    print("\r" + " " * 60 + "\rAssistant: ", end="", flush=True)
    return reply


# --- HTTP server -----------------------------------------------------------

async def run_server(url: str, port: int, headless: bool) -> int:
    from .server import serve

    bridge = LLMBridge(headless=headless)
    try:
        if not await _connect_with_login_pause(bridge, url):
            return 1
        print(f"\nHTTP API listening on http://localhost:{port}")
        print("  POST /chat   {\"message\":\"...\"}  ->  {\"reply\":\"...\"}")
        print("  GET  /status                       ->  bridge state")
        print("  GET  /health                       ->  ok")
        print("Press Ctrl+C to stop.\n")
        await serve(bridge, port=port)
        return 0
    finally:
        await bridge.close()


# --- Agent CLI -------------------------------------------------------------

class _HTTPChatBackend:
    """Adapter so CodingAgent can call a remote bridge over HTTP as its brain."""

    def __init__(self, base_url: str):
        self.url = base_url.rstrip("/") + "/v1/chat/completions"

    async def chat(self, message: str, timeout: float = 180.0) -> str:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            payload = {"messages": [{"role": "user", "content": message}]}
            try:
                async with session.post(
                    self.url, json=payload,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as resp:
                    data = await resp.json()
            except aiohttp.ClientError as exc:
                raise RuntimeError(f"Could not reach bridge ({exc}). Is it running?")
        if "error" in data:
            err = data["error"]
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            raise RuntimeError(msg)
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"Empty response from bridge: {data}")
        return choices[0].get("message", {}).get("content", "")


def _cli_event(kind: str, data) -> None:
    """Pretty-print one agent event to the terminal."""
    if kind == "workspace":
        print(f"  workspace: {data}")
    elif kind == "task":
        print(f"  task: {data}")
    elif kind == "step":
        print(f"\n  --- step {data} ---")
    elif kind == "llm":
        first = str(data).strip().split("\n", 1)[0]
        if len(first) > 100:
            first = first[:100] + "..."
        print(f"  LLM> {first}")
    elif kind == "tool_call":
        name = data.get("name", "?") if isinstance(data, dict) else str(data)
        args = data.get("args", {}) if isinstance(data, dict) else {}
        preview = ", ".join(f"{k}={repr(v)[:40]}" for k, v in args.items())
        print(f"  TOOL> {name}({preview})")
    elif kind == "tool_result":
        ok = getattr(data, "ok", True)
        out = getattr(data, "output", str(data))
        first = out.replace("\n", " | ")[:140]
        print(f"  {'RES' if ok else 'ERR'} > {first}")
    elif kind == "warning":
        print(f"  [warn] {data}")
    elif kind == "error":
        print(f"  [error] {data}")
    elif kind == "done":
        print(f"\n  DONE: {data}")


async def run_agent_cli(base_url: str) -> int:
    """Interactive coding-agent REPL that uses a running bridge as its LLM."""
    import datetime as _dt
    from pathlib import Path as _Path

    from .agent import CodingAgent

    print("=" * 60)
    print("  Universal WebUI Bridge - Coding Agent")
    print("=" * 60)
    print(f"  brain: {base_url}/v1   (OpenAI-compatible)")
    print("  Type a coding task and press Enter. Ctrl+C or 'quit' to exit.")
    print()
    print("  TIP: If you have Pi installed, run `pi` in a separate terminal")
    print("       with OPENAI_BASE_URL and OPENAI_API_KEY set to the values above.")
    print("       Pi will use this bridge's web LLM as its brain directly.")
    print()

    backend = _HTTPChatBackend(base_url)
    ws_root = _Path.home() / ".universal_webui_bridge" / "agent_workspace"

    while True:
        try:
            task = await _aio_input("Task> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        task = task.strip()
        if not task:
            continue
        if task.lower() in ("quit", "exit", ":q"):
            break

        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        workspace = ws_root / stamp
        agent = CodingAgent(backend, workspace)
        try:
            await agent.run(task, on_event=_cli_event)
        except Exception as exc:
            print(f"  [agent error] {exc}")
        print()
    print("Goodbye.")
    return 0


# --- GUI launcher ----------------------------------------------------------

def _launch_gui() -> int:
    """Exec `streamlit run ui.py`. Streamlit owns the process after this."""
    from pathlib import Path

    try:
        import streamlit.web.cli as stcli
    except ImportError:
        print("Streamlit is not installed. Install it:  pip install streamlit")
        return 1
    ui_path = Path(__file__).resolve().parent / "ui.py"
    sys.argv = ["streamlit", "run", str(ui_path)]
    return stcli.main() or 0


# --- Entry point -----------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="webui-bridge", add_help=True,
                                     description="Universal WebUI Bridge")
    parser.add_argument("url", nargs="?", help="LLM URL (or pick from a menu if omitted)")
    parser.add_argument("--serve", action="store_true",
                        help="Start the HTTP API for coding agents")
    parser.add_argument("--port", type=int, default=8000, help="HTTP port (default 8000)")
    parser.add_argument("--headless", action="store_true",
                        help="Don't show the browser window (only for already-logged-in sites)")
    parser.add_argument("--gui", action="store_true",
                        help="Launch the Streamlit GUI instead of the terminal client")
    parser.add_argument("--agent-cli", metavar="URL",
                        help="Run a coding agent (built-in, or use Pi directly) using the "
                             "bridge as its LLM. Pi is preferred: `pi` will auto-detect "
                             "OPENAI_BASE_URL.  e.g. --agent-cli http://localhost:8000")
    parser.add_argument("--debug", action="store_true", help="Verbose logging")
    args = parser.parse_args(argv)

    if args.gui:
        return _launch_gui()

    if args.agent_cli:
        try:
            return asyncio.run(run_agent_cli(args.agent_cli))
        except KeyboardInterrupt:
            return 0

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    url = normalize_url(args.url) if args.url else None

    try:
        if args.serve:
            if not url:
                print("--serve needs a URL. Example:  --serve https://chatgpt.com")
                return 2
            return asyncio.run(run_server(url, args.port, args.headless))
        return asyncio.run(run_chat(url, args.headless))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
