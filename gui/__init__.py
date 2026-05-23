# GUI package initialization
from .agent_adapters import (
    AgentAdapter,
    PiAdapter,
    OpenCodeAdapter,
    ClaudeDesktopAdapter,
    CodexAdapter,
    GenericAgentAdapter,
    get_adapter,
    list_supported_agents,
    AgentServer,
)

__all__ = [
    'AgentAdapter',
    'PiAdapter',
    'OpenCodeAdapter',
    'ClaudeDesktopAdapter',
    'CodexAdapter',
    'GenericAgentAdapter',
    'get_adapter',
    'list_supported_agents',
    'AgentServer',
]
