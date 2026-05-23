#!/usr/bin/env python3
"""
Agent Integration Adapters

This module provides adapters for popular coding agents to connect
to the Universal LLM Bridge.

Supported agents:
- Pi
- OpenCode
- Claude Desktop (via MCP)
- Codex
- Cursor
- VS Code extensions
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, AsyncGenerator
from dataclasses import dataclass
from datetime import datetime

from webui_bridge import UniversalWebUIBridge

logger = logging.getLogger(__name__)


@dataclass
class AgentMessage:
    """Standard message format for all agents."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None


class AgentAdapter(ABC):
    """Base class for all agent adapters."""
    
    def __init__(self, bridge: UniversalWebUIBridge):
        self.bridge = bridge
    
    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the adapter."""
        pass
    
    @abstractmethod
    async def send_message(self, content: str) -> str:
        """Send a message and get response."""
        pass
    
    @abstractmethod
    async def stream_message(self, content: str) -> AsyncGenerator[str, None]:
        """Send a message and stream the response."""
        pass
    
    @abstractmethod
    def get_config(self) -> Dict[str, Any]:
        """Get adapter configuration."""
        pass


class PiAdapter(AgentAdapter):
    """Adapter for Pi coding agent."""
    
    name = "Pi"
    description = "Pi coding agent integration"
    
    async def initialize(self) -> bool:
        """Setup Pi-specific settings."""
        logger.info("Initializing Pi adapter")
        return True
    
    async def send_message(self, content: str) -> str:
        """Send message via Pi interface."""
        await self.bridge.send(content)
        response = await self.bridge.wait_for_response()
        return response or ""
    
    async def stream_message(self, content: str) -> AsyncGenerator[str, None]:
        """Stream message via Pi."""
        await self.bridge.send(content)
        async for token in self.bridge.stream_response():
            yield token
    
    def get_config(self) -> Dict[str, Any]:
        return {
            "agent": "Pi",
            "adapter": "PiAdapter",
            "features": ["chat", "streaming", "code_extraction"],
            "setup_instructions": [
                "1. Ensure Pi is installed",
                "2. Configure Pi to use this bridge as provider",
                "3. Start coding with Pi"
            ]
        }


class OpenCodeAdapter(AgentAdapter):
    """Adapter for OpenCode CLI."""
    
    name = "OpenCode"
    description = "OpenCode CLI integration"
    
    async def initialize(self) -> bool:
        logger.info("Initializing OpenCode adapter")
        return True
    
    async def send_message(self, content: str) -> str:
        # Format for OpenCode
        formatted = self._format_for_opencode(content)
        await self.bridge.send(formatted)
        response = await self.bridge.wait_for_response()
        return self._format_from_opencode(response)
    
    async def stream_message(self, content: str) -> AsyncGenerator[str, None]:
        formatted = self._format_for_opencode(content)
        await self.bridge.send(formatted)
        async for token in self.bridge.stream_response():
            yield self._format_from_opencode(token)
    
    def _format_for_opencode(self, content: str) -> str:
        """Format message for OpenCode compatibility."""
        return content  # Default passthrough
    
    def _format_from_opencode(self, response: str) -> str:
        """Format response from OpenCode."""
        return response  # Default passthrough
    
    def get_config(self) -> Dict[str, Any]:
        return {
            "agent": "OpenCode",
            "adapter": "OpenCodeAdapter",
            "features": ["chat", "streaming"],
            "config_command": "opencode config set provider universal-bridge"
        }


class ClaudeDesktopAdapter(AgentAdapter):
    """Adapter for Claude Desktop app."""
    
    name = "Claude Desktop"
    description = "Anthropic Claude Desktop integration"
    
    async def initialize(self) -> bool:
        logger.info("Initializing Claude Desktop adapter")
        return True
    
    async def send_message(self, content: str) -> str:
        await self.bridge.send(content)
        response = await self.bridge.wait_for_response()
        return response
    
    async def stream_message(self, content: str) -> AsyncGenerator[str, None]:
        await self.bridge.send(content)
        async for token in self.bridge.stream_response():
            yield token
    
    def get_config(self) -> Dict[str, Any]:
        return {
            "agent": "Claude Desktop",
            "adapter": "ClaudeDesktopAdapter",
            "features": ["chat", "streaming", "artifacts"],
            "requires": "MCP server configuration"
        }


class CodexAdapter(AgentAdapter):
    """Adapter for OpenAI Codex CLI."""
    
    name = "Codex"
    description = "OpenAI Codex CLI integration"
    
    async def initialize(self) -> bool:
        logger.info("Initializing Codex adapter")
        return True
    
    async def send_message(self, content: str) -> str:
        await self.bridge.send(content)
        response = await self.bridge.wait_for_response()
        return response
    
    async def stream_message(self, content: str) -> AsyncGenerator[str, None]:
        await self.bridge.send(content)
        async for token in self.bridge.stream_response():
            yield token
    
    def get_config(self) -> Dict[str, Any]:
        return {
            "agent": "Codex",
            "adapter": "CodexAdapter",
            "features": ["chat", "streaming", "code_generation"],
            "config_command": "codex config set provider universal-bridge"
        }


class GenericAgentAdapter(AgentAdapter):
    """Generic adapter for any coding agent."""
    
    name = "Generic Agent"
    description = "Works with any coding agent"
    
    async def initialize(self) -> bool:
        logger.info("Initializing generic agent adapter")
        return True
    
    async def send_message(self, content: str) -> str:
        await self.bridge.send(content)
        response = await self.bridge.wait_for_response()
        return response
    
    async def stream_message(self, content: str) -> AsyncGenerator[str, None]:
        await self.bridge.send(content)
        async for token in self.bridge.stream_response():
            yield token
    
    def get_config(self) -> Dict[str, Any]:
        return {
            "agent": "Generic",
            "adapter": "GenericAgentAdapter",
            "features": ["chat", "streaming"],
            "instructions": "Use this bridge's HTTP API to communicate"
        }


# Agent registry
AGENT_ADAPTERS = {
    "pi": PiAdapter,
    "opencode": OpenCodeAdapter,
    "claude_desktop": ClaudeDesktopAdapter,
    "codex": CodexAdapter,
    "generic": GenericAgentAdapter,
}


def get_adapter(agent_name: str, bridge: UniversalWebUIBridge) -> AgentAdapter:
    """Get adapter for specific agent."""
    agent_key = agent_name.lower().replace(" ", "_")
    adapter_class = AGENT_ADAPTERS.get(agent_key, GenericAgentAdapter)
    return adapter_class(bridge)


def list_supported_agents():
    """List all supported agents."""
    return {
        key: {
            "name": adapter.name,
            "description": adapter.description
        }
        for key, adapter in AGENT_ADAPTERS.items()
    }


# HTTP Server for agent communication
from aiohttp import web


class AgentServer:
    """HTTP server that agents can connect to."""
    
    def __init__(self, bridge: UniversalWebUIBridge, port: int = 8000):
        self.bridge = bridge
        self.port = port
        self.app = web.Application()
        self.setup_routes()
    
    def setup_routes(self):
        """Setup HTTP routes."""
        self.app.router.add_post('/chat', self.handle_chat)
        self.app.router.add_post('/stream', self.handle_stream)
        self.app.router.add_get('/status', self.handle_status)
        self.app.router.add_get('/config', self.handle_config)
    
    async def handle_chat(self, request):
        """Handle chat request."""
        try:
            data = await request.json()
            message = data.get('message', '')
            
            await self.bridge.send(message)
            response = await self.bridge.wait_for_response()
            
            return web.json_response({
                'success': True,
                'response': response,
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    async def handle_stream(self, request):
        """Handle streaming request."""
        response = web.StreamResponse()
        response.content_type = 'text/event-stream'
        await response.prepare(request)
        
        try:
            data = await request.json()
            message = data.get('message', '')
            
            await self.bridge.send(message)
            
            async for token in self.bridge.stream_response():
                await response.write(f"data: {token}\n\n".encode())
            
            await response.write(b"data: [DONE]\n\n")
            
        except Exception as e:
            await response.write(f"data: ERROR: {str(e)}\n\n".encode())
        
        return response
    
    async def handle_status(self, request):
        """Get bridge status."""
        return web.json_response({
            'connected': True,
            'api_mode': False,  # TODO: track this
            'ui_type': None,  # TODO: track this
            'timestamp': datetime.now().isoformat()
        })
    
    async def handle_config(self, request):
        """Get configuration for agents."""
        return web.json_response({
            'name': 'Universal LLM Bridge',
            'version': '0.1.0',
            'endpoints': {
                'chat': '/chat',
                'stream': '/stream',
                'status': '/status'
            },
            'supported_agents': list_supported_agents()
        })
    
    async def start(self):
        """Start the server."""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, 'localhost', self.port)
        await site.start()
        logger.info(f"Agent server started on http://localhost:{self.port}")
    
    async def stop(self):
        """Stop the server."""
        await self.app.shutdown()
        await self.app.cleanup()
        logger.info("Agent server stopped")


# Main entry point for agent server
async def run_agent_server(bridge: UniversalWebUIBridge, port: int = 8000):
    """Run HTTP server for agent communication."""
    server = AgentServer(bridge, port)
    await server.start()
    
    try:
        # Keep running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await server.stop()


if __name__ == "__main__":
    # Example: Start server
    print("Supported agents:")
    for key, info in list_supported_agents().items():
        print(f"  - {info['name']}: {info['description']}")
