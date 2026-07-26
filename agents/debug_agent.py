"""
Debug Agent - LLM-Powered

Specialized agent for debugging and issue resolution using Claude/GPT.
"""

import time
from typing import Any, Dict

from agents.base.base_agent import AgentConfig, AgentResult, BaseAgent
from models.llm.llm_wrapper import LLMResponse, get_llm_wrapper
from utils.logger import AgentLogger


class DebugAgent(BaseAgent):
    """
    Agent specialized in debugging using LLMs.

    Capabilities:
    - Analyze error messages with LLM
    - Identify root causes
    - Propose fixes
    - Verify solutions
    - Debug tests
    """

    def __init__(self, config: AgentConfig):
        """Initialize debug agent."""
        super().__init__(config)
        self.llm = get_llm_wrapper()
        self.logger.logger.info("Debug agent initialized with LLM")

    async def execute(self, task: str, **kwargs: Any) -> AgentResult:
        """
        Execute a debugging task using LLM.

        Args:
            task: Task description
            **kwargs: Additional parameters

        Returns:
            Agent result
        """
        start_time = time.time()

        self.logger.logger.info("Executing debug task", task=task)

        error_message = kwargs.get("error_message", "")
        code = kwargs.get("code", "")
        stack_trace = kwargs.get("stack_trace", "")
        language = kwargs.get("language", "python")
        context = kwargs.get("context", {})

        # Build prompt for LLM
        prompt = self._build_prompt(task, error_message, code, stack_trace, language, context)

        # Get system prompt
        system_prompt = self._get_system_prompt()

        try:
            llm_response: LLMResponse = await self.llm.generate(
                prompt=prompt,
                model=self.config.model,
                system_prompt=system_prompt,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )

            analysis = llm_response.content
            duration_ms = int((time.time() - start_time) * 1000)

            self.logger.log_token_usage(
                model=self.config.model,
                prompt_tokens=llm_response.prompt_tokens,
                completion_tokens=llm_response.completion_tokens,
                total_tokens=llm_response.total_tokens,
            )

            return AgentResult(
                status="success",
                output=analysis,
                metadata={
                    "error": error_message,
                    "language": language,
                    "tokens_used": llm_response.total_tokens,
                },
                next_steps=[
                    "Apply suggested fix",
                    "Run tests to verify",
                    "Update tests if needed",
                ],
                duration_ms=duration_ms,
            )

        except Exception as e:
            self.logger.logger.error("Debug analysis failed", error=str(e))
            return AgentResult(
                status="error",
                errors=[str(e)],
            )

    def _build_prompt(
        self,
        task: str,
        error_message: str,
        code: str,
        stack_trace: str,
        language: str,
        context: Dict[str, Any],
    ) -> str:
        """Build prompt for debugging."""
        prompt_parts = [
            f"Task: {task}",
            f"Language: {language}",
        ]

        if error_message:
            prompt_parts.append(f"\nError:\n{error_message}")

        if code:
            prompt_parts.append(f"\nCode:\n```\n{code}\n```")

        if stack_trace:
            prompt_parts.append(f"\nStack Trace:\n```\n{stack_trace}\n```")

        if context:
            prompt_parts.append(f"\nAdditional Context:")
            for key, value in context.items():
                prompt_parts.append(f"  - {key}: {value}")

        prompt_parts.append("\nAnalyze this issue and provide:")
        prompt_parts.append("1. Root cause analysis")
        prompt_parts.append("2. Detailed explanation of what's wrong")
        prompt_parts.append("3. Specific fix with code")
        prompt_parts.append("4. Verification steps")
        prompt_parts.append("5. Prevention strategies")

        return "\n".join(prompt_parts)

    def _get_system_prompt(self) -> str:
        """Get system prompt for debugging."""
        return """You are an expert debugging specialist with deep knowledge of software systems, error patterns, and troubleshooting techniques.

Provide thorough debugging analysis including:
- Root cause identification
- Step-by-step explanation of the issue
- Specific, actionable fixes with code
- Verification steps to confirm the fix works
- Strategies to prevent similar issues

Format your response as:
# Debug Analysis

## Issue Summary
[Brief description of the problem]

## Root Cause
[Detailed explanation of what's causing the issue]

## The Fix
```python
[Specific code fix]
```

## Explanation
[Why the fix works]

## Verification Steps
1. [Step to verify]
2. [Another step]
3. [Final verification]

## Prevention
[How to avoid this issue in the future]

Be thorough and practical. Focus on helping the user understand and resolve the issue."""

    async def validate(self, result: AgentResult) -> bool:
        """Validate debug result."""
        return result.is_success() and result.output

    async def investigate(
        self,
        issue: str,
        context: Dict[str, Any] = None,
    ) -> AgentResult:
        """
        Investigate an issue.

        Args:
            issue: Issue description
            context: Additional context

        Returns:
            Agent result with investigation findings
        """
        task = f"Investigate: {issue}"
        return await self.execute(task, **(context or {}))

    async def fix_bug(
        self,
        code: str,
        error: str,
        language: str = "python",
    ) -> AgentResult:
        """
        Fix a bug in code.

        Args:
            code: Code with bug
            error: Error message
            language: Programming language

        Returns:
            Agent result with fixed code
        """
        task = f"Fix bug: {error}"
        return await self.execute(
            task,
            code=code,
            error_message=error,
            language=language,
        )


async def create_debug_agent() -> DebugAgent:
    """Create a debug agent instance."""
    config = AgentConfig(
        name="debug_agent",
        description="Debugging and issue resolution agent powered by LLM",
        model="claude-sonnet-4-5-20250929",
        temperature=0.5,
        max_tokens=4096,
    )

    return DebugAgent(config)
