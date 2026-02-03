"""
Validation Module

Strict validation to ensure ZERO MISTAKES.
"""

from agents.validation.strict_validator import (
    StrictValidator,
    ValidationResult,
    ValidationSeverity,
    get_strict_validator,
)

__all__ = [
    "StrictValidator",
    "ValidationResult",
    "ValidationSeverity",
    "get_strict_validator",
]
