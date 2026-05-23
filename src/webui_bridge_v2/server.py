"""
HTTP API for coding agents.

A long-running aiohttp server bound to a single LLMBridge. Chats are serialized
through an asyncio lock because the underlying browser holds one conversation
at a time.

Endpoints:

    POST /chat                    {"message": "..."}             -> {"reply": "..."}
    POST /v1/chat/completions     OpenAI-format request          -> OpenAI-format reply
                                                                    (or SSE if stream:true)
    GET  /v1/models                                              -> minimal model list
    GET  /status                                                 -> bridge state
    GET  /health                                                 -> {"ok": true}

The /v1/* path makes the bridge a drop-in OpenAI-compatible endpoint, so any
coding-agent CLI that accepts a custom OPENAI_BASE_URL can use the connected
web LLM as if it were OpenAI.

Important: every /v1/chat/completions call gets the FULL message history
(system + assistant turns + new user turn) formatted as a role-tagged string
and forwarded to the web LLM. The web LLM is treated as stateless from the
agent's perspective. To avoid the web LLM's OWN thread memory double-counting
previous turns, the very first /v1/chat/completions call after server startup
asks the bridge to reset the web LLM's conversation (clicks "new chat").
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Dict, List

from aiohttp import web

from .core import BridgeState, LLMBridge

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 300.0  # /v1 default; large code generations need room


def build_app(bridge: LLMBridge) -> web.Application:
    app = web.Application(client_max_size=4 * 1024 * 1024)
    app["bridge"] = bridge
    app["chat_lock"] = asyncio.Lock()
    # First /v1 call resets the web LLM chat so the agent's framing doesn't
    # collide with whatever's already in the browser tab.
    app["needs_reset"] = True

    app.router.add_post("/chat", _handle_chat)
    app.router.add_post("/v1/chat/completions", _handle_openai_chat)
    app.router.add_get("/v1/models", _handle_openai_models)
    app.router.add_get("/status", _handle_status)
    app.router.add_get("/health", _handle_health)
    return app


# --- legacy {"message": ...} endpoint -------------------------------------

async def _handle_chat(request: web.Request) -> web.Response:
    bridge: LLMBridge = request.app["bridge"]
    lock: asyncio.Lock = request.app["chat_lock"]

    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        return web.json_response({"error": "Body must be JSON"}, status=400)

    message = (body.get("message") or "").strip()
    if not message:
        return web.json_response({"error": "Missing 'message' field"}, status=400)
    timeout = float(body.get("timeout", DEFAULT_TIMEOUT))

    if bridge.state is not BridgeState.READY:
        return web.json_response(
            {"error": f"Bridge not ready (state: {bridge.state.value})"},
            status=503,
        )

    async with lock:
        try:
            reply = await bridge.chat(message, timeout=timeout)
        except Exception as exc:
            logger.exception("chat failed")
            return web.json_response({"error": str(exc)}, status=500)
    return web.json_response({"reply": reply})


# --- /status, /health -----------------------------------------------------

async def _handle_status(request: web.Request) -> web.Response:
    bridge: LLMBridge = request.app["bridge"]
    s = bridge.status
    return web.json_response(
        {
            "state": s.state.value,
            "url": s.url,
            "service": s.service,
            "message": s.message,
            "history_len": len(bridge.history),
        }
    )


async def _handle_health(_: web.Request) -> web.Response:
    return web.json_response({"ok": True})


# --- OpenAI-compatible shim ------------------------------------------------

def _err(message: str, *, status: int = 400, type_: str = "invalid_request_error") -> web.Response:
    return web.json_response({"error": {"message": message, "type": type_}}, status=status)


def _format_history(messages: List[Dict[str, Any]]) -> str:
    """Turn an OpenAI messages array into one role-tagged prompt.

    Web LLMs (ChatGPT/Claude/Gemini) read role-tagged transcripts very well even
    when they arrive as a single concatenated message. We finish with a bare
    `<<ASSISTANT>>` line to cue the model to continue from the assistant's
    point of view.
    """
    parts: List[str] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "user").upper()
        content = m.get("content", "")
        if isinstance(content, list):
            # multimodal content blocks: keep text only
            content = " ".join(
                str(c.get("text", "")) for c in content if isinstance(c, dict)
            )
        content = str(content).strip()
        if not content:
            continue
        parts.append(f"<<{role}>>\n{content}")
    if not parts:
        return ""
    parts.append("<<ASSISTANT>>")
    return "\n\n".join(parts)


async def _maybe_reset(bridge: LLMBridge, app: web.Application) -> None:
    """Once per server lifetime, ask the web LLM to start a new chat."""
    if not app.get("needs_reset"):
        return
    app["needs_reset"] = False
    try:
        await bridge.reset_conversation()
    except Exception as exc:
        logger.warning("reset_conversation failed (continuing anyway): %s", exc)


async def _handle_openai_chat(request: web.Request) -> web.Response:
    """Speak the OpenAI Chat Completions wire format.

    The whole `messages` array is converted to a role-tagged transcript and
    forwarded to the web LLM. The web LLM responds; we wrap the reply as the
    OpenAI single-completion shape (or as SSE if the caller asked for it).
    """
    bridge: LLMBridge = request.app["bridge"]
    lock: asyncio.Lock = request.app["chat_lock"]

    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        return _err("Body must be JSON")

    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        return _err("Missing or empty 'messages'")

    prompt = _format_history(messages)
    if not prompt.strip():
        return _err("No non-empty content found in messages")

    if bridge.state is not BridgeState.READY:
        return _err(
            f"Bridge not ready (state: {bridge.state.value}). Open and log in first.",
            status=503,
            type_="bridge_not_ready",
        )

    timeout = float(body.get("timeout", DEFAULT_TIMEOUT))
    want_stream = bool(body.get("stream"))
    model_name = body.get("model") or bridge.status.service or "webui-bridge"

    async with lock:
        await _maybe_reset(bridge, request.app)
        try:
            reply = await bridge.chat(prompt, timeout=timeout)
        except Exception as exc:
            logger.exception("openai chat failed")
            if want_stream:
                # Even on error, give SSE clients something parseable.
                return await _sse_error(request, str(exc), model_name)
            return _err(str(exc), status=500, type_="bridge_error")

    if want_stream:
        return await _sse_reply(request, reply, model_name)
    return _json_reply(reply, model_name)


def _json_reply(reply: str, model: str) -> web.Response:
    return web.json_response(
        {
            "id": "chatcmpl-" + uuid.uuid4().hex[:24],
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": reply},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }
    )


async def _sse_reply(request: web.Request, reply: str, model: str) -> web.StreamResponse:
    """Minimal SSE: one delta event with the full reply, then [DONE].

    Not real token streaming, but it satisfies the OpenAI SSE wire format so
    clients that default to `stream:true` don't sit waiting for chunks.
    """
    resp = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
    await resp.prepare(request)

    chunk_id = "chatcmpl-" + uuid.uuid4().hex[:24]
    created = int(time.time())

    first = {
        "id": chunk_id, "object": "chat.completion.chunk", "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {"role": "assistant", "content": reply},
                     "finish_reason": None}],
    }
    final = {
        "id": chunk_id, "object": "chat.completion.chunk", "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }

    await resp.write(f"data: {json.dumps(first)}\n\n".encode("utf-8"))
    await resp.write(f"data: {json.dumps(final)}\n\n".encode("utf-8"))
    await resp.write(b"data: [DONE]\n\n")
    await resp.write_eof()
    return resp


async def _sse_error(request: web.Request, message: str, model: str) -> web.StreamResponse:
    resp = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
        },
    )
    await resp.prepare(request)
    chunk_id = "chatcmpl-" + uuid.uuid4().hex[:24]
    payload = {
        "id": chunk_id, "object": "chat.completion.chunk", "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0,
                     "delta": {"role": "assistant", "content": f"[bridge error] {message}"},
                     "finish_reason": "stop"}],
    }
    await resp.write(f"data: {json.dumps(payload)}\n\n".encode("utf-8"))
    await resp.write(b"data: [DONE]\n\n")
    await resp.write_eof()
    return resp


async def _handle_openai_models(request: web.Request) -> web.Response:
    """Minimal /v1/models response so clients that probe it don't 404."""
    bridge: LLMBridge = request.app["bridge"]
    name = (bridge.status.service or "webui-bridge").lower().replace(" ", "-")
    return web.json_response(
        {
            "object": "list",
            "data": [
                {
                    "id": name,
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "webui-bridge",
                }
            ],
        }
    )


async def serve(bridge: LLMBridge, port: int = 8000, host: str = "localhost") -> None:
    """Start the server and block until cancelled."""
    app = build_app(bridge)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await runner.cleanup()
