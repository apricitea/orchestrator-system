"""
Reflective Thinking Pipeline

Implements meta-cognition for agents:
- Think → Act → Observe → Reflect cycle
- Self-critique before submitting work
- Learn from past mistakes
- Improve decision quality
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Literal

from anthropic import AsyncAnthropic
from utils.logger import get_logger


class ReflectionTrigger(str, Enum):
    """When to trigger reflection."""
    BEFORE_SUBMIT = "before_submit"  # Before submitting work
    AFTER_ERROR = "after_error"  # After encountering error
    ON_AMBIGUITY = "on_ambiguity"  # When uncertain
    PERIODIC = "periodic"  # At regular intervals


class ReflectionQuality(str, Enum):
    """Quality assessment of reflection."""
    EXCELLENT = "excellent"
    GOOD = "good"
    ADEQUATE = "adequate"
    NEEDS_IMPROVEMENT = "needs_improvement"
    POOR = "poor"


@dataclass
class ReflectionResult:
    """Result of reflective thinking process."""
    passed: bool
    quality: ReflectionQuality
    critiques: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    confidence: float = 0.0  # 0.0 to 1.0
    should_revise: bool = False
    revisions_needed: List[str] = field(default_factory=list)
    reflection_summary: str = ""


@dataclass
class Thought:
    """A single thought in the reflection process."""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    phase: Literal["plan", "act", "observe", "reflect"] = "reflect"
    content: str = ""
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class ReflectivePipeline:
    """
    Implements reflective thinking for autonomous agents.

    Based on cognitive science principles:
    1. Metacognition - thinking about thinking
    2. Self-monitoring - observing own thought processes
    3. Critical evaluation - judging quality of own work
    4. Adaptive adjustment - improving based on reflection
    """

    def __init__(self, client: AsyncAnthropic, model: str = "claude-haiku-4-5"):
        """Initialize reflective pipeline."""
        self.client = client
        self.model = model
        self.logger = get_logger("reflective_pipeline")
        self.reflection_history: List[Thought] = []
        self.max_history = 100

        self.system_prompt = """You are an expert at meta-cognitive analysis and self-reflection.

Your role is to critically evaluate work BEFORE it is submitted. Think like a senior engineer reviewing their own work with a critical eye.

## Reflection Dimensions:

1. **Correctness**: Does this accomplish the stated goal?
2. **Completeness**: Is anything missing or incomplete?
3. **Security**: Are there security vulnerabilities?
4. **Quality**: Is this production-ready code?
5. **Maintainability**: Will this be easy to understand and modify?
6. **Edge Cases**: What could go wrong? Have we handled failures?
7. **Best Practices**: Does this follow industry standards?

## Critical Thinking Questions:

- What assumptions am I making that might be wrong?
- What happens if this fails? How would I know?
- Could this be simpler? What's unnecessary complexity?
- What would I criticize if someone else wrote this?
- What's the worst thing that could happen with this change?
- Have I tested the failure modes?
- Is this over-engineered or under-engineered?

## Output Format:

Provide a JSON response with:
{
  "passed": true/false,
  "quality": "excellent/good/adequate/needs_improvement/poor",
  "confidence": 0.0-1.0,
  "critiques": ["specific issue 1", "specific issue 2"],
  "suggestions": ["improvement 1", "improvement 2"],
  "should_revise": true/false,
  "revisions_needed": ["specific revision 1", "specific revision 2"],
  "reflection_summary": "2-3 sentence summary of your reflection"
}

Be thorough but constructive. If work is excellent, say so and pass it. If there are issues, be specific about what needs fixing.
"""

    async def reflect_before_submit(
        self,
        agent_name: str,
        task: str,
        work: Dict[str, Any],
        context: Dict[str, Any],
    ) -> ReflectionResult:
        """
        Reflect on work before submission.

        Args:
            agent_name: Agent submitting the work
            task: Original task description
            work: Work being submitted (code, config, etc.)
            context: Additional context

        Returns:
            Reflection result with pass/fail and feedback
        """
        self.logger.info(
            "Reflecting before submit",
            agent=agent_name,
            task=task[:50],
        )

        # Record thought
        self._record_thought(
            phase="reflect",
            content=f"Pre-submit reflection for {agent_name} on task: {task[:50]}",
        )

        # Build reflection prompt
        prompt = self._build_reflection_prompt(
            agent_name=agent_name,
            task=task,
            work=work,
            context=context,
        )

        try:
            # Call LLM for reflection
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                temperature=0.3,  # Lower temp for consistent critical thinking
                system=self.system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            )

            # Parse response
            import json
            content = response.content[0].text

            # Try to extract JSON from markdown code block
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            reflection_data = json.loads(content)
            result = ReflectionResult(**reflection_data)

            self.logger.info(
                "Reflection complete",
                agent=agent_name,
                passed=result.passed,
                quality=result.quality,
                confidence=result.confidence,
                should_revise=result.should_revise,
            )

            # Record reflection result
            self._record_thought(
                phase="reflect",
                content=f"Reflection result: passed={result.passed}, quality={result.quality}",
                metadata={
                    "agent": agent_name,
                    "passed": result.passed,
                    "quality": result.quality,
                    "confidence": result.confidence,
                },
            )

            return result

        except Exception as e:
            self.logger.error("Reflection failed", error=str(e))
            # Fail open - don't block submission if reflection fails
            return ReflectionResult(
                passed=True,
                quality=ReflectionQuality.ADEQUATE,
                confidence=0.5,
                reflection_summary=f"Reflection failed: {str(e)}. Allowing submission.",
            )

    def _build_reflection_prompt(
        self,
        agent_name: str,
        task: str,
        work: Dict[str, Any],
        context: Dict[str, Any],
    ) -> str:
        """Build prompt for reflection."""
        prompt_parts = [
            f"## Agent: {agent_name}",
            f"\n## Task:\n{task}",
        ]

        # Add work details
        if "code" in work:
            prompt_parts.append(f"\n## Code:\n```\n{work['code'][:5000]}\n```")
        if "file_path" in work:
            prompt_parts.append(f"\n## File: {work['file_path']}")
        if "changes" in work:
            prompt_parts.append(f"\n## Changes:\n{work['changes']}")
        if "output" in work:
            output_preview = work["output"][:2000]
            prompt_parts.append(f"\n## Output:\n```\n{output_preview}\n```")

        # Add context
        if "working_directory" in context:
            prompt_parts.append(f"\n## Working Directory: {context['working_directory']}")
        if "dependencies" in context:
            prompt_parts.append(f"\n## Dependencies: {context['dependencies']}")

        prompt_parts.append(
            "\n\n## CRITICALLY EVALUATE THIS WORK:"
            "\nThink like a senior engineer conducting a self-review. Be thorough."
            "\nWhat could go wrong? What's missing? Is this production-ready?"
        )

        return "\n".join(prompt_parts)

    def _record_thought(
        self,
        phase: Literal["plan", "act", "observe", "reflect"],
        content: str,
        confidence: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a thought in the reflection history."""
        thought = Thought(
            phase=phase,
            content=content,
            confidence=confidence,
            metadata=metadata or {},
        )
        self.reflection_history.append(thought)

        # Trim history if needed
        if len(self.reflection_history) > self.max_history:
            self.reflection_history = self.reflection_history[-self.max_history :]

    def get_reflection_summary(self) -> Dict[str, Any]:
        """Get summary of reflection history."""
        if not self.reflection_history:
            return {"total_thoughts": 0, "phases": {}}

        phases = {}
        for thought in self.reflection_history:
            phase = thought.phase
            if phase not in phases:
                phases[phase] = {"count": 0, "avg_confidence": 0.0}
            phases[phase]["count"] += 1
            phases[phase]["avg_confidence"] += thought.confidence

        # Calculate averages
        for phase_data in phases.values():
            if phase_data["count"] > 0:
                phase_data["avg_confidence"] /= phase_data["count"]

        return {
            "total_thoughts": len(self.reflection_history),
            "phases": phases,
            "recent_thoughts": [
                {
                    "phase": t.phase,
                    "content": t.content[:100],
                    "confidence": t.confidence,
                }
                for t in self.reflection_history[-5:]
            ],
        }


class ReflectiveAgentMixin:
    """
    Mixin to add reflective capabilities to any agent.

    Usage:
        class MyAgent(ReflectiveAgentMixin, BaseAgent):
            async def execute(self, task, **kwargs):
                # Do work
                result = await self._do_work(task, **kwargs)

                # Reflect before submitting
                reflection = await self.reflect_before_submit(
                    task=task,
                    work={"output": result.output},
                    context=kwargs,
                )

                if not reflection.passed:
                    # Revise work based on reflection
                    result = await self._revise_work(result, reflection)

                return result
    """

    def __init__(self, *args, **kwargs):
        """Initialize reflective agent."""
        super().__init__(*args, **kwargs)
        # Will be set by orchestrator
        self._reflective_pipeline: Optional[ReflectivePipeline] = None

    def set_reflective_pipeline(self, pipeline: ReflectivePipeline) -> None:
        """Set the reflective pipeline for this agent."""
        self._reflective_pipeline = pipeline

    async def reflect_before_submit(
        self,
        task: str,
        work: Dict[str, Any],
        context: Dict[str, Any],
    ) -> ReflectionResult:
        """Reflect on work before submission."""
        if not self._reflective_pipeline:
            self.logger.logger.warning("No reflective pipeline set, skipping reflection")
            return ReflectionResult(
                passed=True,
                quality=ReflectionQuality.ADEQUATE,
                confidence=0.5,
                reflection_summary="No reflective pipeline configured.",
            )

        return await self._reflective_pipeline.reflect_before_submit(
            agent_name=self.config.name,
            task=task,
            work=work,
            context=context,
        )

    async def _revise_work(
        self,
        original_result: Any,
        reflection: ReflectionResult,
    ) -> Any:
        """Revise work based on reflection feedback.

        Override in subclass to implement revision logic.
        """
        self.logger.logger.info(
            "Revise work called but not implemented",
            suggestions=reflection.suggestions,
        )
        return original_result


def get_reflective_pipeline(
    client: AsyncAnthropic,
    model: str = "claude-haiku-4-5",
) -> ReflectivePipeline:
    """Get a reflective pipeline instance."""
    return ReflectivePipeline(client=client, model=model)
