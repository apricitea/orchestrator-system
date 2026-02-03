"""
Error Recovery Loop

Automatically detects errors and attempts fixes through iterative retry.
Parses error messages, generates fixes, and tracks error patterns.
"""

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from utils.logger import get_logger


class ErrorSeverity(str, Enum):
    """Severity of an error."""
    CRITICAL = "critical"  # Cannot proceed without fixing
    HIGH = "high"  # Blocks current task
    MEDIUM = "medium"  # Workaround possible
    LOW = "low"  # Non-critical


class ErrorCategory(str, Enum):
    """Category of error."""
    SYNTAX = "syntax"
    IMPORT = "import"
    RUNTIME = "runtime"
    TYPE = "type"
    LOGIC = "logic"
    DEPENDENCY = "dependency"
    NETWORK = "network"
    PERMISSION = "permission"
    UNKNOWN = "unknown"


@dataclass
class ErrorPattern:
    """Detected error pattern."""
    pattern: str
    category: ErrorCategory
    severity: ErrorSeverity
    frequency: int = 1
    suggested_fixes: List[str] = None

    def __post_init__(self):
        if self.suggested_fixes is None:
            self.suggested_fixes = []


@dataclass
class FixAttempt:
    """Attempted fix for an error."""
    attempt_number: int
    fix_description: str
    code_changes: Dict[str, str]  # file_path -> old_code
    success: bool
    error_message: str = ""
    new_error: Optional[str] = None


@dataclass
class ErrorContext:
    """Context information for an error."""
    error_message: str
    error_type: str
    file_path: Optional[str]
    line_number: Optional[int]
    code_snippet: Optional[str]
    stack_trace: str = ""
    category: ErrorCategory = ErrorCategory.UNKNOWN
    severity: ErrorSeverity = ErrorSeverity.MEDIUM


@dataclass
class RecoveryResult:
    """Result of error recovery attempt."""
    success: bool
    error_resolved: bool
    attempts_made: int
    fix_attempts: List[FixAttempt]
    final_state: str  # "resolved", "failed", "max_attempts_reached"
    learned_patterns: List[ErrorPattern] = None

    def __post_init__(self):
        if self.learned_patterns is None:
            self.learned_patterns = []


class ErrorRecoveryLoop:
    """
    Automatic error detection and recovery system.

    Features:
    - Parse and categorize errors
    - Generate fix suggestions
    - Apply fixes iteratively
    - Track error patterns
    - Learn from past fixes
    """

    # Common error patterns for detection
    ERROR_PATTERNS = {
        ErrorCategory.SYNTAX: [
            r"SyntaxError:.*",
            r"IndentationError:.*",
            r"TabError:.*",
        ],
        ErrorCategory.IMPORT: [
            r"ModuleNotFoundError:.*",
            r"ImportError:.*",
            r"No module named .*",
        ],
        ErrorCategory.TYPE: [
            r"TypeError:.*",
            r"AttributeError:.*",
            r"ValueError:.*",
        ],
        ErrorCategory.DEPENDENCY: [
            r"MissingDependencyException:.*",
            r"PackageNotFoundError:.*",
        ],
        ErrorCategory.PERMISSION: [
            r"PermissionError:.*",
            r"AccessDenied:.*",
        ],
        ErrorCategory.NETWORK: [
            r"ConnectionError:.*",
            r"TimeoutError:.*",
            r"HTTPError:.*",
        ],
    }

    def __init__(self, max_attempts: int = 3):
        """
        Initialize the error recovery loop.

        Args:
            max_attempts: Maximum number of fix attempts before giving up
        """
        self.max_attempts = max_attempts
        self.logger = get_logger("error_recovery")
        self.error_patterns: Dict[str, ErrorPattern] = {}
        self.fix_history: List[FixAttempt] = []

    def parse_error(
        self,
        error_output: str,
        file_context: Optional[Dict[str, str]] = None,
    ) -> ErrorContext:
        """
        Parse error output to extract structured information.

        Args:
            error_output: Raw error output
            file_context: Optional context about files involved

        Returns:
            Parsed error context
        """
        # Extract error type
        error_type = "UnknownError"
        type_match = re.search(r"^(\w+Error):", error_output, re.MULTILINE)
        if type_match:
            error_type = type_match.group(1)

        # Extract file path and line number
        file_path = None
        line_number = None
        location_match = re.search(r'File "(.+)", line (\d+)', error_output)
        if location_match:
            file_path = location_match.group(1)
            line_number = int(location_match.group(2))

        # Extract code snippet if available
        code_snippet = None
        if file_path and line_number and file_context:
            file_path_key = Path(file_path).name
            if file_path_key in file_context:
                lines = file_context[file_path_key].split("\n")
                start = max(0, line_number - 3)
                end = min(len(lines), line_number + 2)
                code_snippet = "\n".join(lines[start:end])

        # Categorize error
        category = self._categorize_error(error_output)

        # Determine severity
        severity = self._determine_severity(category, error_type)

        # Extract stack trace
        stack_trace = self._extract_stack_trace(error_output)

        return ErrorContext(
            error_message=self._extract_error_message(error_output),
            error_type=error_type,
            file_path=file_path,
            line_number=line_number,
            code_snippet=code_snippet,
            stack_trace=stack_trace,
            category=category,
            severity=severity,
        )

    def _categorize_error(self, error_output: str) -> ErrorCategory:
        """Categorize error based on patterns."""
        for category, patterns in self.ERROR_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, error_output, re.IGNORECASE):
                    return category
        return ErrorCategory.UNKNOWN

    def _determine_severity(
        self,
        category: ErrorCategory,
        error_type: str,
    ) -> ErrorSeverity:
        """Determine error severity."""
        if category in [ErrorCategory.SYNTAX, ErrorCategory.IMPORT]:
            return ErrorSeverity.CRITICAL
        elif category == ErrorCategory.PERMISSION:
            return ErrorSeverity.HIGH
        elif category == ErrorCategory.DEPENDENCY:
            return ErrorSeverity.MEDIUM
        else:
            return ErrorSeverity.MEDIUM

    def _extract_error_message(self, error_output: str) -> str:
        """Extract the main error message."""
        # Usually the last line is the error message
        lines = error_output.strip().split("\n")
        for line in reversed(lines):
            if line.strip() and not line.startswith("  ") and ":" in line:
                return line.strip()
        return lines[-1] if lines else ""

    def _extract_stack_trace(self, error_output: str) -> str:
        """Extract the full stack trace."""
        # Stack trace is everything before the final error message
        lines = error_output.split("\n")
        trace_lines = []
        for line in lines:
            if line.strip().startswith("File ") or "Traceback" in line:
                trace_lines.append(line)
            elif trace_lines and line.startswith("  "):
                trace_lines.append(line)
        return "\n".join(trace_lines)

    def generate_fix_suggestion(
        self,
        error_context: ErrorContext,
    ) -> List[str]:
        """
        Generate fix suggestions for an error.

        Args:
            error_context: Parsed error context

        Returns:
            List of fix suggestions
        """
        suggestions = []

        if error_context.category == ErrorCategory.IMPORT:
            suggestions.append(
                f"Install missing module: "
                f"`pip install {self._extract_package_name(error_context.error_message)}`"
            )
            suggestions.append("Check if the module name is spelled correctly")

        elif error_context.category == ErrorCategory.SYNTAX:
            suggestions.append(
                f"Fix syntax error at line {error_context.line_number}"
            )
            if "IndentationError" in error_context.error_type:
                suggestions.append("Check for consistent indentation (use 4 spaces)")
            suggestions.append("Review code around the error for missing brackets/quotes")

        elif error_context.category == ErrorCategory.TYPE:
            suggestions.append("Check variable types before operation")
            suggestions.append("Add type checking/conversion if needed")
            if "AttributeError" in error_context.error_type:
                suggestions.append(
                    f"Verify that the object has the attribute: "
                    f"{self._extract_attribute_name(error_context.error_message)}"
                )

        elif error_context.category == ErrorCategory.DEPENDENCY:
            suggestions.append("Install missing dependencies")
            suggestions.append("Check requirements.txt is up to date")

        elif error_context.category == ErrorCategory.PERMISSION:
            suggestions.append("Check file permissions")
            suggestions.append("Ensure user has read/write access")

        else:
            suggestions.append(f"Review {error_context.error_type}: {error_context.error_message}")
            suggestions.append("Check the stack trace for the root cause")

        return suggestions

    def _extract_package_name(self, error_message: str) -> str:
        """Extract package name from import error."""
        match = re.search(r"No module named ['\"](.+?)['\"]", error_message)
        if match:
            return match.group(1)
        return "<package_name>"

    def _extract_attribute_name(self, error_message: str) -> str:
        """Extract attribute name from AttributeError."""
        match = re.search(r"has no attribute ['\"](.+?)['\"]", error_message)
        if match:
            return match.group(1)
        return "<attribute_name>"

    async def recover_from_error(
        self,
        error_context: ErrorContext,
        apply_fix_callback,
        max_attempts: Optional[int] = None,
    ) -> RecoveryResult:
        """
        Attempt to recover from an error through iterative fixes.

        Args:
            error_context: The error to recover from
            apply_fix_callback: Async function that takes (suggestion, attempt_num) and applies the fix
            max_attempts: Override default max attempts

        Returns:
            Recovery result with all attempts and outcome
        """
        if max_attempts is None:
            max_attempts = self.max_attempts

        attempts = []
        learned_patterns = []

        self.logger.info(
            "Starting error recovery",
            error_type=error_context.error_type,
            category=error_context.category,
            max_attempts=max_attempts,
        )

        for attempt_num in range(1, max_attempts + 1):
            # Generate fix suggestions
            suggestions = self.generate_fix_suggestion(error_context)

            self.logger.info(
                "Recovery attempt",
                attempt=attempt_num,
                suggestions=len(suggestions),
            )

            # Try each suggestion
            for suggestion in suggestions:
                try:
                    # Apply the fix via callback
                    result = await apply_fix_callback(suggestion, attempt_num)

                    fix_attempt = FixAttempt(
                        attempt_number=attempt_num,
                        fix_description=suggestion,
                        code_changes=result.get("changes", {}),
                        success=result.get("success", False),
                    )

                    if result.get("success", False):
                        # Error resolved!
                        self.logger.info(
                            "Error resolved successfully",
                            attempt=attempt_num,
                            suggestion=suggestion,
                        )

                        # Record successful pattern
                        self._record_successful_pattern(error_context, suggestion)

                        return RecoveryResult(
                            success=True,
                            error_resolved=True,
                            attempts_made=attempt_num,
                            fix_attempts=attempts + [fix_attempt],
                            final_state="resolved",
                        )
                    else:
                        # Fix failed, check for new error
                        new_error = result.get("error", "")
                        if new_error and new_error != error_context.error_message:
                            fix_attempt.new_error = new_error
                            error_context = self.parse_error(new_error)

                        fix_attempt.error_message = result.get("message", "Unknown error")
                        attempts.append(fix_attempt)

                except Exception as e:
                    self.logger.warning(
                        "Fix attempt failed",
                        attempt=attempt_num,
                        error=str(e),
                    )
                    attempts.append(
                        FixAttempt(
                            attempt_number=attempt_num,
                            fix_description=suggestion,
                            code_changes={},
                            success=False,
                            error_message=str(e),
                        )
                    )

        # Max attempts reached
        self.logger.warning(
            "Max recovery attempts reached",
            attempts=len(attempts),
            error=error_context.error_message,
        )

        return RecoveryResult(
            success=False,
            error_resolved=False,
            attempts_made=len(attempts),
            fix_attempts=attempts,
            final_state="max_attempts_reached",
        )

    def _record_successful_pattern(
        self,
        error_context: ErrorContext,
        fix: str,
    ):
        """Record a successful error-fix pattern."""
        pattern_key = f"{error_context.category}:{error_context.error_type}"

        if pattern_key not in self.error_patterns:
            self.error_patterns[pattern_key] = ErrorPattern(
                pattern=pattern_key,
                category=error_context.category,
                severity=error_context.severity,
                suggested_fixes=[fix],
            )
        else:
            pattern = self.error_patterns[pattern_key]
            pattern.frequency += 1
            if fix not in pattern.suggested_fixes:
                pattern.suggested_fixes.append(fix)

        self.logger.info(
            "Recorded successful pattern",
            pattern=pattern_key,
            frequency=self.error_patterns[pattern_key].frequency,
        )

    def get_learned_patterns(
        self,
        category: Optional[ErrorCategory] = None,
    ) -> List[ErrorPattern]:
        """
        Get learned error-fix patterns.

        Args:
            category: Filter by category (optional)

        Returns:
            List of learned patterns sorted by frequency
        """
        patterns = list(self.error_patterns.values())

        if category:
            patterns = [p for p in patterns if p.category == category]

        return sorted(patterns, key=lambda p: p.frequency, reverse=True)

    def get_fix_history(
        self,
        file_path: Optional[str] = None,
    ) -> List[FixAttempt]:
        """
        Get history of fix attempts.

        Args:
            file_path: Filter by file path (optional)

        Returns:
            List of fix attempts
        """
        if file_path:
            return [
                a for a in self.fix_history
                if file_path in a.code_changes.keys()
            ]
        return self.fix_history.copy()


# Global instance
_error_recovery_loop: Optional[ErrorRecoveryLoop] = None


def get_error_recovery_loop(max_attempts: int = 3) -> ErrorRecoveryLoop:
    """Get the global error recovery loop instance."""
    global _error_recovery_loop
    if _error_recovery_loop is None:
        _error_recovery_loop = ErrorRecoveryLoop(max_attempts=max_attempts)
    return _error_recovery_loop
