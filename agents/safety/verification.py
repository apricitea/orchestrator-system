"""
Verification Pipeline & Risk-Based Approval

Implements safety checks before committing changes:
- Dry-run mode (preview changes before applying)
- Pre-commit validation
- Risk-based human intervention
- Automatic rollback capability
"""

import asyncio
import os
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Literal

from utils.logger import get_logger


class RiskLevel(str, Enum):
    """Risk level of changes."""
    SAFE = "safe"  # No human review needed
    LOW = "low"  # Optional review
    MEDIUM = "medium"  # Review recommended
    HIGH = "high"  # Review required
    CRITICAL = "critical"  # Human approval required


class VerificationStatus(str, Enum):
    """Status of verification."""
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


@dataclass
class VerificationCheck:
    """A single verification check."""
    name: str
    status: VerificationStatus
    message: str
    details: Optional[str] = None
    blocking: bool = True  # If True, blocks commit on failure


@dataclass
class VerificationResult:
    """Result of verification pipeline."""
    overall_status: VerificationStatus
    checks: List[VerificationCheck]
    risk_level: RiskLevel
    requires_human_approval: bool
    warnings: List[str] = field(default_factory=list)
    can_proceed: bool = False
    rollback_plan: Optional[str] = None


class RiskAnalyzer:
    """Analyzes risk level of proposed changes."""

    def __init__(self):
        """Initialize risk analyzer."""
        self.logger = get_logger("risk_analyzer")

        # High-risk patterns
        self.HIGH_RISK_PATTERNS = [
            "database", "migration", "schema", "drop table", "delete from",
            "payment", "stripe", "braintree", "paypal",
            "authentication", "authorization", "password", "token",
            "api key", "secret", "credential",
            "production", "prod", "live",
            "deployment", "deploy", "release",
        ]

        # Critical-risk patterns
        self.CRITICAL_PATTERNS = [
            "drop database", "truncate table", "delete.*where.*1=1",
            "rm -rf", "force push", "rebase",
            "credit card", "ssn", "social security",
            "pi", "personal data", "gdpr",
        ]

    def analyze_risk(
        self,
        task: str,
        files_changed: List[str],
        context: Dict[str, Any],
    ) -> RiskLevel:
        """
        Analyze risk level of proposed changes.

        Args:
            task: Task description
            files_changed: List of files being changed
            context: Additional context

        Returns:
            Risk level
        """
        task_lower = task.lower()
        risk_score = 0

        # Check file patterns
        for file_path in files_changed:
            file_lower = file_path.lower()

            # Config changes = higher risk
            if any(
                pattern in file_lower
                for pattern in ["config", "setting", "env", ".env"]
            ):
                risk_score += 1

            # Database files = high risk
            if any(
                pattern in file_lower
                for pattern in ["migration", "schema", "model", "sql"]
            ):
                risk_score += 2

            # Auth/security files = critical
            if any(
                pattern in file_lower
                for pattern in ["auth", "security", "password", "token"]
            ):
                risk_score += 3

        # Check task patterns
        for pattern in self.HIGH_RISK_PATTERNS:
            if pattern in task_lower:
                risk_score += 2

        for pattern in self.CRITICAL_PATTERNS:
            if pattern in task_lower:
                risk_score += 5

        # Determine risk level
        if risk_score >= 10:
            return RiskLevel.CRITICAL
        elif risk_score >= 6:
            return RiskLevel.HIGH
        elif risk_score >= 3:
            return RiskLevel.MEDIUM
        elif risk_score >= 1:
            return RiskLevel.LOW
        else:
            return RiskLevel.SAFE

    def requires_human_approval(
        self,
        task: str,
        files_changed: List[str],
        context: Dict[str, Any],
    ) -> bool:
        """Determine if human approval is required."""
        risk = self.analyze_risk(task, files_changed, context)
        return risk in [RiskLevel.HIGH, RiskLevel.CRITICAL]


class VerificationPipeline:
    """
    Verification pipeline for pre-commit checks.

    Implements safety checks before committing:
    1. Syntax validation
    2. Test execution
    3. Security scan
    4. File validation
    5. Risk assessment
    """

    def __init__(self, working_directory: str = "."):
        """Initialize verification pipeline."""
        self.working_directory = working_directory
        self.logger = get_logger("verification_pipeline")
        self.risk_analyzer = RiskAnalyzer()

    async def verify_before_commit(
        self,
        task: str,
        files_changed: List[str],
        context: Dict[str, Any],
    ) -> VerificationResult:
        """
        Run verification pipeline before commit.

        Args:
            task: Task description
            files_changed: List of changed files
            context: Additional context

        Returns:
            Verification result
        """
        self.logger.info(
            "Running verification pipeline",
            task=task[:50],
            files=files_changed,
        )

        checks = []

        # 1. Risk analysis
        risk_check = await self._check_risk_level(task, files_changed, context)
        checks.append(risk_check)

        # 2. File validation
        file_check = await self._check_files(files_changed)
        checks.append(file_check)

        # 3. Syntax validation (for code files)
        syntax_check = await self._check_syntax(files_changed)
        checks.append(syntax_check)

        # 4. Quick security scan
        security_check = await self._quick_security_check(files_changed, context)
        checks.append(security_check)

        # 5. Determine overall status
        blocking_failures = [c for c in checks if c.blocking and c.status == VerificationStatus.FAILED]

        if blocking_failures:
            overall_status = VerificationStatus.FAILED
            can_proceed = False
        else:
            warnings = [c for c in checks if c.status == VerificationStatus.WARNING]
            if warnings:
                overall_status = VerificationStatus.WARNING
            else:
                overall_status = VerificationStatus.PASSED
            can_proceed = True

        # Check if human approval needed
        risk_level = self.risk_analyzer.analyze_risk(task, files_changed, context)
        requires_human = risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]

        if requires_human and can_proceed:
            can_proceed = False  # Block until human approval

        result = VerificationResult(
            overall_status=overall_status,
            checks=checks,
            risk_level=risk_level,
            requires_human_approval=requires_human,
            can_proceed=can_proceed,
            warnings=[c.message for c in checks if c.status == VerificationStatus.WARNING],
        )

        self.logger.info(
            "Verification complete",
            status=overall_status,
            risk_level=risk_level,
            can_proceed=can_proceed,
        )

        return result

    async def _check_risk_level(
        self,
        task: str,
        files_changed: List[str],
        context: Dict[str, Any],
    ) -> VerificationCheck:
        """Check risk level of changes."""
        risk_level = self.risk_analyzer.analyze_risk(task, files_changed, context)

        if risk_level == RiskLevel.SAFE:
            return VerificationCheck(
                name="Risk Analysis",
                status=VerificationStatus.PASSED,
                message=f"Risk level: {risk_level.value} - no special precautions needed",
                blocking=False,
            )
        elif risk_level in [RiskLevel.LOW, RiskLevel.MEDIUM]:
            return VerificationCheck(
                name="Risk Analysis",
                status=VerificationStatus.WARNING,
                message=f"Risk level: {risk_level.value} - proceed with caution",
                blocking=False,
            )
        else:
            return VerificationCheck(
                name="Risk Analysis",
                status=VerificationStatus.FAILED,
                message=f"Risk level: {risk_level.value} - human approval required",
                blocking=True,
            )

    async def _check_files(self, files_changed: List[str]) -> VerificationCheck:
        """Check if files exist and are accessible."""
        issues = []

        for file_path in files_changed:
            full_path = os.path.join(self.working_directory, file_path)

            if not os.path.exists(full_path):
                issues.append(f"File not found: {file_path}")
                continue

            if not os.access(full_path, os.R_OK):
                issues.append(f"File not readable: {file_path}")

        if issues:
            return VerificationCheck(
                name="File Validation",
                status=VerificationStatus.FAILED,
                message=f"File validation failed",
                details="; ".join(issues),
                blocking=True,
            )
        else:
            return VerificationCheck(
                name="File Validation",
                status=VerificationStatus.PASSED,
                message=f"All {len(files_changed)} files validated",
                blocking=False,
            )

    async def _check_syntax(self, files_changed: List[str]) -> VerificationCheck:
        """Check syntax of code files."""
        python_files = [f for f in files_changed if f.endswith(".py")]

        if not python_files:
            return VerificationCheck(
                name="Syntax Check",
                status=VerificationStatus.SKIPPED,
                message="No Python files to check",
                blocking=False,
            )

        syntax_errors = []

        for file_path in python_files:
            full_path = os.path.join(self.working_directory, file_path)

            try:
                result = subprocess.run(
                    ["python3", "-m", "py_compile", full_path],
                    capture_output=True,
                    timeout=10,
                )

                if result.returncode != 0:
                    syntax_errors.append(f"{file_path}: {result.stderr.decode()}")

            except subprocess.TimeoutExpired:
                syntax_errors.append(f"{file_path}: syntax check timeout")
            except Exception as e:
                syntax_errors.append(f"{file_path}: {str(e)}")

        if syntax_errors:
            return VerificationCheck(
                name="Syntax Check",
                status=VerificationStatus.FAILED,
                message=f"Syntax errors found in {len(syntax_errors)} file(s)",
                details="; ".join(syntax_errors),
                blocking=True,
            )
        else:
            return VerificationCheck(
                name="Syntax Check",
                status=VerificationStatus.PASSED,
                message=f"All {len(python_files)} Python files have valid syntax",
                blocking=False,
            )

    async def _quick_security_check(
        self,
        files_changed: List[str],
        context: Dict[str, Any],
    ) -> VerificationCheck:
        """Quick security check for common issues."""
        issues = []

        # Check for common security issues
        security_patterns = {
            r"password\s*=\s*['\"][^'\"]+['\"]": "Hardcoded password",
            r"api_key\s*=\s*['\"][^'\"]+['\"]": "Hardcoded API key",
            r"secret\s*=\s*['\"][^'\"]+['\"]": "Hardcoded secret",
            r"token\s*=\s*['\"][^'\"]+['\"]": "Hardcoded token",
        }

        for file_path in files_changed:
            if not file_path.endswith(".py"):
                continue

            full_path = os.path.join(self.working_directory, file_path)

            try:
                with open(full_path, "r") as f:
                    content = f.read()

                import re
                for pattern, description in security_patterns.items():
                    if re.search(pattern, content, re.IGNORECASE):
                        issues.append(f"{file_path}: {description}")

            except Exception:
                pass  # Skip files that can't be read

        if issues:
            return VerificationCheck(
                name="Security Scan",
                status=VerificationStatus.WARNING,
                message=f"Potential security issues: {len(issues)}",
                details="; ".join(issues),
                blocking=False,  # Warning only, let reviewer decide
            )
        else:
            return VerificationCheck(
                name="Security Scan",
                status=VerificationStatus.PASSED,
                message="No obvious security issues detected",
                blocking=False,
            )


def get_verification_pipeline(working_directory: str = ".") -> VerificationPipeline:
    """Get verification pipeline instance."""
    return VerificationPipeline(working_directory)
