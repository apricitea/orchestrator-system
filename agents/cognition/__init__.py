"""
Agent Cognition Module

Implements advanced cognitive capabilities:
- Reflective thinking (meta-cognition)
- Self-critique and improvement
- Learning from experience
"""

from agents.cognition.reflective_pipeline import (
    ReflectiveAgentMixin,
    ReflectivePipeline,
    ReflectionQuality,
    ReflectionResult,
    ReflectionTrigger,
    Thought,
    get_reflective_pipeline,
)

__all__ = [
    "ReflectiveAgentMixin",
    "ReflectivePipeline",
    "ReflectionQuality",
    "ReflectionResult",
    "ReflectionTrigger",
    "Thought",
    "get_reflective_pipeline",
]
