"""
Cost-Aware Model Router

Routes tasks to appropriate models based on complexity:
- Simple tasks → Haiku (fast, cheap)
- Medium tasks → Sonnet (balanced)
- Complex tasks → Opus (best quality)

Optimizes for cost while maintaining quality.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Literal

from utils.logger import get_logger


class ModelTier(str, Enum):
    """Model complexity tiers."""
    ECONOMY = "economy"  # Haiku - fast, cheap
    STANDARD = "standard"  # Sonnet - balanced
    PREMIUM = "premium"  # Opus - best quality


@dataclass
class ModelRecommendation:
    """Recommended model for a task."""
    model: str
    tier: ModelTier
    confidence: float  # 0.0 to 1.0
    reasoning: str
    estimated_cost_usd: float
    estimated_time_seconds: float


class ComplexityIndicators:
    """Indicators of task complexity."""

    # Low complexity indicators
    LOW_PATTERNS = [
        r"add.*comment",
        r"update.*readme",
        r"fix.*typo",
        r"change.*color",
        r"rename.*variable",
        r"update.*config",
        r"simple.*test",
        r"documentation",
        r"formatting",
    ]

    # High complexity indicators
    HIGH_PATTERNS = [
        r"redesign.*architecture",
        r"optimize.*performance",
        r"security.*audit",
        r"database.*migration",
        r"implement.*from scratch",
        r"complex.*algorithm",
        r"distributed.*system",
        r"async.*programming",
        r"concurrency",
    ]

    # Security-critical patterns
    SECURITY_PATTERNS = [
        r"security",
        r"vulnerab",
        r"auth",
        r"authentication",
        r"authorization",
        r"encryption",
        r"sql.*inject",
        r"xss",
        r"csrf",
    ]

    # Features requiring more reasoning
    COMPLEX_FEATURES = [
        "api",
        "endpoint",
        "database",
        "cache",
        "queue",
        "websocket",
        "authentication",
        "authorization",
        "payment",
        "file.*upload",
    ]


class ModelRouter:
    """
    Routes tasks to appropriate models based on complexity analysis.

    Cost optimization strategy:
    - Haiku (~$0.25/M tokens): Simple, repetitive tasks
    - Sonnet (~$3/M tokens): Standard development tasks
    - Opus (~$15/M tokens): Complex architecture, security, reasoning-heavy

    Quality assurance:
    - Conservative routing (better to over-estimate complexity)
    - Confidence scores for recommendations
    - Fallback to higher tier if uncertain
    """

    # Pricing (USD per million tokens as of 2024)
    PRICING = {
        ModelTier.ECONOMY: {"input": 0.25, "output": 1.25},
        ModelTier.STANDARD: {"input": 3.00, "output": 15.00},
        ModelTier.PREMIUM: {"input": 15.00, "output": 75.00},
    }

    # Expected speed (tokens per second)
    SPEED = {
        ModelTier.ECONOMY: 150,  # Fast
        ModelTier.STANDARD: 80,   # Medium
        ModelTier.PREMIUM: 40,    # Slow but thorough
    }

    MODEL_NAMES = {
        ModelTier.ECONOMY: "claude-haiku-4-5",
        ModelTier.STANDARD: "claude-sonnet-4-5-20250929",
        ModelTier.PREMIUM: "claude-opus-4-5-20251101",
    }

    def __init__(self):
        """Initialize model router."""
        self.logger = get_logger("model_router")

    def recommend_model(
        self,
        task: str,
        agent_name: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ModelRecommendation:
        """
        Recommend appropriate model for a task.

        Args:
            task: Task description
            agent_name: Agent that will execute the task
            context: Additional context

        Returns:
            Model recommendation with reasoning
        """
        complexity_score = self._calculate_complexity(task, agent_name, context or {})
        tier = self._score_to_tier(complexity_score, task)
        model = self.MODEL_NAMES[tier]

        # Calculate estimated cost (assuming 5K tokens)
        estimated_input_tokens = self._estimate_tokens(task, context or {})
        estimated_output_tokens = 2000  # Conservative estimate
        estimated_cost = (
            (estimated_input_tokens / 1_000_000) * self.PRICING[tier]["input"]
            + (estimated_output_tokens / 1_000_000) * self.PRICING[tier]["output"]
        )

        # Estimate time
        total_tokens = estimated_input_tokens + estimated_output_tokens
        estimated_time = total_tokens / self.SPEED[tier]

        recommendation = ModelRecommendation(
            model=model,
            tier=tier,
            confidence=self._calculate_confidence(complexity_score),
            reasoning=self._generate_reasoning(complexity_score, tier, task),
            estimated_cost_usd=estimated_cost,
            estimated_time_seconds=estimated_time,
        )

        self.logger.info(
            "Model recommendation",
            task=task[:50],
            agent=agent_name,
            model=model,
            tier=tier,
            cost_usd=estimated_cost,
            confidence=recommendation.confidence,
        )

        return recommendation

    def _calculate_complexity(
        self,
        task: str,
        agent_name: str,
        context: Dict[str, Any],
    ) -> float:
        """
        Calculate complexity score (0.0 = simple, 1.0 = complex).

        Factors:
        - Task description patterns
        - Agent type (security agent = higher complexity)
        - Code length
        - Dependencies
        - Security relevance
        """
        score = 0.3  # Base complexity (medium-low)

        task_lower = task.lower()

        # Check for low complexity patterns
        for pattern in ComplexityIndicators.LOW_PATTERNS:
            if re.search(pattern, task_lower):
                score -= 0.2
                break

        # Check for high complexity patterns
        for pattern in ComplexityIndicators.HIGH_PATTERNS:
            if re.search(pattern, task_lower):
                score += 0.3
                break

        # Check for complex features
        for feature in ComplexityIndicators.COMPLEX_FEATURES:
            if feature in task_lower:
                score += 0.15

        # Security patterns always increase complexity
        for pattern in ComplexityIndicators.SECURITY_PATTERNS:
            if re.search(pattern, task_lower):
                score += 0.2
                break

        # Agent-specific adjustments
        if agent_name == "security_agent":
            score += 0.2  # Security analysis needs high quality
        elif agent_name == "review_agent":
            score += 0.15  # Reviews need good reasoning
        elif agent_name == "planner_agent":
            score += 0.25  # Planning is critical
        elif agent_name in ["docs_agent", "git_agent"]:
            score -= 0.1  # These can use faster models

        # Context adjustments
        if "code" in context and len(str(context.get("code", ""))) > 5000:
            score += 0.1  # Lots of code to analyze

        if "dependencies" in context:
            deps = context["dependencies"]
            if isinstance(deps, list) and len(deps) > 5:
                score += 0.1  # Complex dependency graph

        # Task length indicator
        if len(task) > 500:
            score += 0.1  # Long task description = complex

        # Clamp to [0, 1]
        return max(0.0, min(1.0, score))

    def _score_to_tier(self, score: float, task: str) -> ModelTier:
        """Convert complexity score to model tier."""
        task_lower = task.lower()

        # Security always uses at least standard
        if any(
            pattern in task_lower
            for pattern in ComplexityIndicators.SECURITY_PATTERNS
        ):
            if score < 0.4:
                return ModelTier.STANDARD
            elif score < 0.7:
                return ModelTier.STANDARD
            else:
                return ModelTier.PREMIUM

        # Normal routing
        if score < 0.3:
            return ModelTier.ECONOMY
        elif score < 0.6:
            return ModelTier.STANDARD
        else:
            return ModelTier.PREMIUM

    def _calculate_confidence(self, complexity_score: float) -> float:
        """Calculate confidence in recommendation."""
        # Higher confidence when complexity is clearly low or high
        if complexity_score < 0.2 or complexity_score > 0.8:
            return 0.9
        elif complexity_score < 0.4 or complexity_score > 0.6:
            return 0.7
        else:
            return 0.5  # Medium complexity = less certain

    def _generate_reasoning(self, complexity_score: float, tier: ModelTier, task: str) -> str:
        """Generate human-readable reasoning."""
        parts = []

        if complexity_score < 0.3:
            parts.append("Task appears straightforward with clear requirements")
        elif complexity_score < 0.6:
            parts.append("Task involves standard development work")
        else:
            parts.append("Task requires complex reasoning and careful analysis")

        if tier == ModelTier.ECONOMY:
            parts.append("→ Using Haiku for fast, cost-effective execution")
        elif tier == ModelTier.STANDARD:
            parts.append("→ Using Sonnet for balanced quality and cost")
        else:
            parts.append("→ Using Opus for highest quality reasoning")

        return " ".join(parts)

    def _estimate_tokens(self, task: str, context: Dict[str, Any]) -> int:
        """Estimate input token count."""
        # Rough estimate: 1 token ≈ 4 characters
        tokens = len(task) / 4

        # Add context tokens
        if "code" in context:
            tokens += len(str(context["code"])) / 4
        if "files_changed" in context:
            tokens += len(str(context["files_changed"])) / 4

        return int(tokens)

    def get_model_for_agent(
        self,
        agent_name: str,
        default_model: str,
    ) -> str:
        """
        Get appropriate model for an agent (fallback method).

        Used when task context isn't available for detailed routing.
        """
        # Agent-specific defaults
        agent_defaults = {
            "planner_agent": self.MODEL_NAMES[ModelTier.PREMIUM],  # Planning needs best reasoning
            "security_agent": self.MODEL_NAMES[ModelTier.STANDARD],  # Security needs quality
            "review_agent": self.MODEL_NAMES[ModelTier.STANDARD],  # Reviews need good reasoning
            "coding_agent": self.MODEL_NAMES[ModelTier.STANDARD],  # Coding needs balance
            "testing_agent": self.MODEL_NAMES[ModelTier.ECONOMY],  # Test generation can be fast
            "debug_agent": self.MODEL_NAMES[ModelTier.STANDARD],  # Debugging needs reasoning
            "docs_agent": self.MODEL_NAMES[ModelTier.ECONOMY],  # Docs can be fast
            "git_agent": self.MODEL_NAMES[ModelTier.ECONOMY],  # Git is straightforward
            "deploy_agent": self.MODEL_NAMES[ModelTier.STANDARD],  # Deploy needs care
        }

        return agent_defaults.get(agent_name, default_model)


# Global instance
_model_router = None


def get_model_router() -> ModelRouter:
    """Get global model router instance."""
    global _model_router
    if _model_router is None:
        _model_router = ModelRouter()
    return _model_router
