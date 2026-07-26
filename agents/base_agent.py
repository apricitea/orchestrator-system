"""
Base Agent Class

This module provides the abstract base class for all agents in the system.
It defines the common interface and functionality that all agents must implement.
"""

import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from config.settings import get_settings
from utils.logger import AgentLogger, get_logger


class AgentConfig(BaseModel):
    """Configuration for an agent."""

    name: str
    description: str
    model: str
    temperature: float = Field(default=0.7, ge=0.0, le=1.0)
    max_tokens: int = Field(default=4096, ge=1)
    timeout: int = Field(default=300, ge=1)
    max_retries: int = Field(default=3, ge=0)
    enabled: bool = Field(default=True)


class AgentResult(BaseModel):
    """Result from an agent operation."""

    status: str  # "success", "error", "partial"
    output: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)
    next_steps: List[str] = Field(default_factory=list)
    duration_ms: int = Field(default=0)

    def is_success(self) -> bool:
        """Check if the result is successful."""
        return self.status == "success"

    def is_error(self) -> bool:
        """Check if the result is an error."""
        return self.status == "error"

    def is_partial(self) -> bool:
        """Check if the result is partial success."""
        return self.status == "partial"


class BaseAgent(ABC):
    """
    Abstract base class for all agents.

    All agents must inherit from this class and implement the required methods.
    """

    def __init__(self, config: AgentConfig):
        """
        Initialize the base agent.

        Args:
            config: Agent configuration
        """
        self.config = config
        self.settings = get_settings()
        self.logger = AgentLogger(
            agent_name=config.name,
            agent_id=f"{config.name}_{int(time.time())}",
        )
        self._call_count = 0
        self._total_tokens = 0

    @abstractmethod
    async def execute(self, task: str, **kwargs: Any) -> AgentResult:
        """
        Execute a task.

        Args:
            task: Task description
            **kwargs: Additional task parameters

        Returns:
            AgentResult with execution outcome
        """
        pass

    @abstractmethod
    async def validate(self, result: AgentResult) -> bool:
        """
        Validate the result of an agent execution.

        Args:
            result: Result to validate

        Returns:
            True if valid, False otherwise
        """
        pass

    async def call(
        self,
        task: str,
        **kwargs: Any,
    ) -> AgentResult:
        """
        Call the agent with retry logic and logging.

        Args:
            task: Task description
            **kwargs: Additional task parameters

        Returns:
            AgentResult with execution outcome
        """
        task_id = f"{self.config.name}_{int(time.time() * 1000)}"
        start_time = time.time()

        self.logger.log_task_start(task=task, task_id=task_id, **kwargs)

        last_error = None
        for attempt in range(self.config.max_retries):
            try:
                result = await self.execute(task, **kwargs)

                # Validate result
                if await self.validate(result):
                    duration_ms = int((time.time() - start_time) * 1000)
                    result.duration_ms = duration_ms

                    self.logger.log_task_complete(
                        task_id=task_id,
                        duration_ms=duration_ms,
                        status=result.status,
                    )

                    self._call_count += 1
                    if "tokens_used" in result.metadata:
                        self._total_tokens += result.metadata["tokens_used"]

                    return result
                else:
                    # Validation failed, treat as error
                    return AgentResult(
                        status="error",
                        errors=["Validation failed"],
                    )

            except Exception as e:
                last_error = e
                self.logger.logger.warning(
                    "Agent execution failed",
                    agent=self.config.name,
                    attempt=attempt + 1,
                    error=str(e),
                )

                if attempt < self.config.max_retries - 1:
                    await self._retry_delay(attempt + 1)

        # All retries failed
        duration_ms = int((time.time() - start_time) * 1000)
        self.logger.log_task_error(
            task_id=task_id,
            error=str(last_error),
            duration_ms=duration_ms,
        )

        return AgentResult(
            status="error",
            errors=[str(last_error) or "Unknown error"],
        )

    async def _retry_delay(self, attempt: int) -> None:
        """Wait before retrying."""
        import asyncio

        delay = self.settings.retry_delay * (2 ** (attempt - 1))
        await asyncio.sleep(delay)

    def get_stats(self) -> Dict[str, Any]:
        """Get agent statistics."""
        return {
            "name": self.config.name,
            "call_count": self._call_count,
            "total_tokens": self._total_tokens,
            "enabled": self.config.enabled,
        }

    def reset_stats(self) -> None:
        """Reset agent statistics."""
        self._call_count = 0
        self._total_tokens = 0

    @classmethod
    def get_config_from_settings(cls, agent_name: str) -> AgentConfig:
        """Get agent configuration from settings."""
        settings = get_settings()
        model_config = settings.model_config_for_agent(agent_name)

        return AgentConfig(
            name=agent_name,
            description=f"{agent_name} for autonomous coding",
            **model_config,
        )


class ToolInterface(ABC):
    """Abstract base class for agent tools."""

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        """Execute the tool."""
        pass

    @abstractmethod
    def validate_input(self, **kwargs: Any) -> bool:
        """Validate tool input."""
        pass
