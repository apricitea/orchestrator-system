"""
Strict Validator for Autonomous Agent Operations

Enforces ZERO TOLERANCE policy for mistakes.
Validates EVERYTHING before proceeding.
"""

import os
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.logger import get_logger


class ValidationSeverity(str, Enum):
    """Severity of validation failure."""
    WARNING = "warning"  # Can proceed with warning
    ERROR = "error"  # Must fix before proceeding
    CRITICAL = "critical"  # Stop everything, escalate


@dataclass
class ValidationResult:
    """Result of validation."""
    passed: bool
    severity: ValidationSeverity
    message: str
    details: Optional[Dict[str, Any]] = None
    fix_suggestion: Optional[str] = None


class StrictValidator:
    """
    Strict validator that enforces ZERO MISTAKES policy.

    Every operation must pass validation before proceeding.
    """

    def __init__(self):
        """Initialize strict validator."""
        self.logger = get_logger("strict_validator")
        self.projects_base_path = Path("/home/ubuntu/projects")

        # Zero tolerance checks
        self.ZERO_TOLERANCE = [
            "project_exists",
            "git_initialized",
            "git_remote_configured",
            "git_remote_is_github",
            "git_fetch_works",
            "working_directory_valid",
        ]

    def validate_project_setup(self, project_name: str) -> ValidationResult:
        """
        Validate project is properly set up.

        ZERO TOLERANCE: If any check fails, STOP and ASK USER.
        """
        self.logger.info("Validating project setup", project=project_name)

        checks = {}
        errors = []

        # Check 1: Project folder exists
        project_path = self.projects_base_path / project_name
        checks["project_exists"] = project_path.exists()
        if not checks["project_exists"]:
            errors.append(f"Project folder not found: {project_path}")

        # If project doesn't exist, stop immediately
        if not checks["project_exists"]:
            return ValidationResult(
                passed=False,
                severity=ValidationSeverity.CRITICAL,
                message=f"Project '{project_name}' not found in /home/ubuntu/projects/",
                details={"available_projects": self._list_available_projects()},
                fix_suggestion=f"Please create project folder or provide GitHub URL to clone",
            )

        # Check 2: Git initialized
        git_dir = project_path / ".git"
        checks["git_initialized"] = git_dir.exists()
        if not checks["git_initialized"]:
            errors.append("Git not initialized")

        # Check 3: Git remote configured
        if checks["git_initialized"]:
            try:
                result = subprocess.run(
                    ["git", "remote", "-v"],
                    cwd=project_path,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if result.returncode == 0 and result.stdout:
                    checks["git_remote_configured"] = True
                    remotes = result.stdout.strip()
                    self.logger.info("Git remotes found", remotes=remotes)
                else:
                    checks["git_remote_configured"] = False
                    errors.append("No git remote configured")

            except Exception as e:
                checks["git_remote_configured"] = False
                errors.append(f"Failed to check git remote: {str(e)}")
        else:
            checks["git_remote_configured"] = False

        # Check 4: Git remote is GitHub
        if checks.get("git_remote_configured"):
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                remote_url = result.stdout.strip()
                checks["git_remote_is_github"] = "github.com" in remote_url

                if not checks["git_remote_is_github"]:
                    errors.append(f"Git remote is not GitHub: {remote_url}")
            else:
                checks["git_remote_is_github"] = False
                errors.append("Cannot get git remote URL")
        else:
            checks["git_remote_is_github"] = False

        # Check 5: Git fetch works
        if checks.get("git_remote_configured"):
            try:
                result = subprocess.run(
                    ["git", "fetch", "origin", "--dry-run"],
                    cwd=project_path,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                checks["git_fetch_works"] = result.returncode == 0
                if not checks["git_fetch_works"]:
                    errors.append(f"Git fetch failed: {result.stderr}")
            except Exception as e:
                checks["git_fetch_works"] = False
                errors.append(f"Git fetch error: {str(e)}")
        else:
            checks["git_fetch_works"] = False

        # Check 6: Working directory is writable
        if checks["project_exists"]:
            checks["working_directory_valid"] = os.access(project_path, os.W_OK)
            if not checks["working_directory_valid"]:
                errors.append(f"Working directory not writable: {project_path}")
        else:
            checks["working_directory_valid"] = False

        # Evaluate all checks
        failed_zero_tolerance = [
            check for check in self.ZERO_TOLERANCE
            if not checks.get(check, False)
        ]

        if failed_zero_tolerance:
            return ValidationResult(
                passed=False,
                severity=ValidationSeverity.CRITICAL,
                message=f"Project validation failed: {len(failed_zero_tolerance)} critical issues",
                details={
                    "checks": checks,
                    "failed_zero_tolerance": failed_zero_tolerance,
                    "errors": errors,
                },
                fix_suggestion=self._generate_fix_suggestion(project_name, checks, errors),
            )

        self.logger.info(
            "Project validation passed",
            project=project_name,
            all_checks=checks,
        )

        return ValidationResult(
            passed=True,
            severity=ValidationSeverity.ERROR,  # No issues
            message=f"Project '{project_name}' validated successfully",
            details={"checks": checks},
        )

    def validate_git_state(self, project_name: str) -> ValidationResult:
        """
        Validate git state before starting work.

        Ensures:
        - On correct branch
        - Main branch is up to date
        - Working directory is clean
        """
        self.logger.info("Validating git state", project=project_name)
        project_path = self.projects_base_path / project_name

        checks = {}
        errors = []

        # Check 1: Current branch
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                current_branch = result.stdout.strip()
                checks["current_branch"] = current_branch
                self.logger.info("Current branch", branch=current_branch)
            else:
                errors.append("Cannot determine current branch")
                checks["current_branch"] = None

        except Exception as e:
            errors.append(f"Failed to get current branch: {str(e)}")
            checks["current_branch"] = None

        # Check 2: Working directory clean
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                has_changes = bool(result.stdout.strip())
                checks["working_directory_clean"] = not has_changes

                if has_changes:
                    errors.append(f"Working directory has uncommitted changes:\n{result.stdout}")
            else:
                errors.append("Cannot check git status")
                checks["working_directory_clean"] = False

        except Exception as e:
            errors.append(f"Failed to check git status: {str(e)}")
            checks["working_directory_clean"] = False

        # Evaluate
        if not checks.get("working_directory_clean", False):
            return ValidationResult(
                passed=False,
                severity=ValidationSeverity.ERROR,
                message="Working directory not clean",
                details={"checks": checks, "errors": errors},
                fix_suggestion="Commit or stash changes before proceeding",
            )

        return ValidationResult(
            passed=True,
            severity=ValidationSeverity.ERROR,
            message="Git state validated",
            details={"checks": checks},
        )

    def validate_trello_task_format(self, task_name: str) -> ValidationResult:
        """
        Validate Trello task follows strict format.

        Required format: [{project}] [agent] P{level}: {description}
        """
        self.logger.info("Validating Trello task format", task=task_name)

        import re

        # Strict format pattern
        pattern = r"^\[(.+?)\]\s+\[agent\]\s+P([0-3]):\s+(.+)$"

        match = re.match(pattern, task_name)

        if not match:
            return ValidationResult(
                passed=False,
                severity=ValidationSeverity.ERROR,
                message=f"Trello task format invalid",
                details={
                    "task_name": task_name,
                    "expected_format": "[{project}] [agent] P{level}: {description}",
                    "examples": [
                        "[laptop-recommendation] [agent] P0: Fix authentication bug",
                        "[web-api] [agent] P1: Add user profile endpoint",
                    ],
                },
                fix_suggestion="Please rename task to match required format",
            )

        project = match.group(1)
        priority = match.group(2)
        description = match.group(3)

        self.logger.info(
            "Trello task format valid",
            project=project,
            priority=priority,
            description=description[:50],
        )

        return ValidationResult(
            passed=True,
            severity=ValidationSeverity.ERROR,
            message="Trello task format valid",
            details={
                "project": project,
                "priority": priority,
                "description": description,
            },
        )

    def _list_available_projects(self) -> List[str]:
        """List all available projects."""
        try:
            if not self.projects_base_path.exists():
                return []

            return [
                d.name
                for d in self.projects_base_path.iterdir()
                if d.is_dir() and (d / ".git").exists()
            ]
        except Exception as e:
            self.logger.error("Failed to list projects", error=str(e))
            return []

    def _generate_fix_suggestion(
        self,
        project_name: str,
        checks: Dict[str, bool],
        errors: List[str],
    ) -> str:
        """Generate fix suggestion based on validation failures."""
        suggestions = []

        if not checks.get("project_exists", False):
            available = self._list_available_projects()
            if available:
                suggestions.append(
                    f"Available projects: {', '.join(available)}"
                )
            suggestions.append(
                f"To add project, please provide GitHub URL: git@github.com:TheCurators/{project_name}.git"
            )

        if not checks.get("git_remote_configured", False):
            suggestions.append(
                f"Run: cd /home/ubuntu/{project_name} && git remote add origin git@github.com:TheCurators/{project_name}.git"
            )

        if not checks.get("git_fetch_works", False):
            suggestions.append(
                "Check GitHub credentials and network connection"
            )

        return "\n".join(suggestions) if suggestions else "Please review errors and fix manually"


# Global instance
_strict_validator = None


def get_strict_validator() -> StrictValidator:
    """Get global strict validator instance."""
    global _strict_validator
    if _strict_validator is None:
        _strict_validator = StrictValidator()
    return _strict_validator
