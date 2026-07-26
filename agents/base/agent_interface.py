"""
Agent Interface and Communication Protocol

This module defines the interfaces and protocols for agent communication,
including the agent registry and inter-agent messaging.
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel

from agents.base.base_agent import AgentConfig, AgentResult


class AgentMessage(BaseModel):
    """Message sent between agents."""

    sender: str
    receiver: str
    action: str
    data: Dict[str, Any]
    message_id: Optional[str] = None
    correlation_id: Optional[str] = None
    timestamp: Optional[float] = None


class MessageHandler(ABC):
    """Abstract base class for message handlers."""

    @abstractmethod
    async def handle(self, message: AgentMessage) -> AgentResult:
        """Handle an incoming message."""
        pass


class AgentRegistry:
    """
    Registry for managing available agents.

    This registry keeps track of all available agents and provides
    methods for agent discovery and communication.
    """

    def __init__(self):
        """Initialize the agent registry."""
        self._agents: Dict[str, Any] = {}
        self._message_handlers: Dict[str, List[Callable]] = {}

    def register(self, name: str, agent: Any) -> None:
        """
        Register an agent.

        Args:
            name: Agent name
            agent: Agent instance
        """
        self._agents[name] = agent

    def unregister(self, name: str) -> None:
        """
        Unregister an agent.

        Args:
            name: Agent name
        """
        if name in self._agents:
            del self._agents[name]

    def get(self, name: str) -> Optional[Any]:
        """
        Get an agent by name.

        Args:
            name: Agent name

        Returns:
            Agent instance or None if not found
        """
        return self._agents.get(name)

    def list_agents(self) -> List[str]:
        """List all registered agent names."""
        return list(self._agents.keys())

    def is_registered(self, name: str) -> bool:
        """Check if an agent is registered."""
        return name in self._agents

    async def call_agent(
        self,
        agent_name: str,
        task: str,
        **kwargs: Any,
    ) -> AgentResult:
        """
        Call an agent by name.

        Args:
            agent_name: Name of the agent to call
            task: Task description
            **kwargs: Additional task parameters

        Returns:
            AgentResult from the agent

        Raises:
            ValueError: If agent not found
        """
        agent = self.get(agent_name)
        if agent is None:
            return AgentResult(
                status="error",
                errors=[f"Agent '{agent_name}' not found"],
            )

        return await agent.call(task, **kwargs)

    async def broadcast(
        self,
        task: str,
        agents: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Dict[str, AgentResult]:
        """
        Broadcast a task to multiple agents.

        Args:
            task: Task description
            agents: List of agent names (None = all agents)
            **kwargs: Additional task parameters

        Returns:
            Dictionary mapping agent names to results
        """
        if agents is None:
            agents = self.list_agents()

        results = {}
        for agent_name in agents:
            results[agent_name] = await self.call_agent(agent_name, task, **kwargs)

        return results


# Global agent registry
agent_registry = AgentRegistry()


def get_agent_registry() -> AgentRegistry:
    """Get the global agent registry."""
    return agent_registry
