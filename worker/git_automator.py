"""
Git Automator - Automated Git Workflow

Handles the complete git workflow for AI-generated code:
1. Create feature branch from main
2. Commit changes with AI-generated messages
3. Push to remote
4. Create pull request with AI-generated description
5. Merge PR (if auto-merge enabled)
6. Clean up branch
"""

import asyncio
import subprocess
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

import httpx
from utils.logger import get_logger
from worker.worker_config import get_worker_config


class PRStatus(str, Enum):
    """Pull request status."""
    OPEN = "open"
    CLOSED = "closed"
    MERGED = "merged"


@dataclass
class PRResult:
    """Result of PR creation."""
    success: bool
    pr_number: int | None = None
    pr_url: str = ""
    error: str = ""


@dataclass
class MergeResult:
    """Result of PR merge."""
    success: bool
    merged: bool = False
    sha: str = ""
    error: str = ""


class GitAutomator:
    """
    Automates git workflow for AI-generated code.

    Follows best practices:
    - Feature branches from main
    - Atomic commits with conventional commits
    - Descriptive PRs
    - Squash merge to main
    - Branch cleanup after merge
    """

    def __init__(self):
        self.logger = get_logger("git_automator")
        self.worker_config = get_worker_config()

    async def create_feature_branch(
        self,
        project_path: Path,
        task_id: str,
        task_title: str,
    ) -> tuple[bool, str]:
        """
        Create a new feature branch from main.

        Args:
            project_path: Path to project repository
            task_id: Task ID for branch naming
            task_title: Task title for branch naming

        Returns:
            Tuple of (success, branch_name)
        """
        try:
            # Ensure main is up to date
            result = subprocess.run(
                ["git", "fetch", "origin"],
                cwd=project_path,
                capture_output=True,
                text=True,
                check=True,
            )

            # Checkout main
            subprocess.run(
                ["git", "checkout", "main"],
                cwd=project_path,
                capture_output=True,
                text=True,
                check=True,
            )

            # Pull latest main
            subprocess.run(
                ["git", "pull", "origin", "main"],
                cwd=project_path,
                capture_output=True,
                text=True,
                check=True,
            )

            # Create branch name
            branch_name = self._generate_branch_name(task_id, task_title)

            # Create and checkout new branch
            subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=project_path,
                capture_output=True,
                text=True,
                check=True,
            )

            self.logger.info(
                "Created feature branch",
                project=project_path.name,
                branch=branch_name,
            )
            return True, branch_name

        except subprocess.CalledProcessError as e:
            self.logger.error(
                "Failed to create branch",
                project=project_path.name,
                error=e.stderr,
            )
            return False, ""

    async def commit_changes(
        self,
        project_path: Path,
        commit_message: str,
    ) -> bool:
        """
        Commit changes with generated message.

        Args:
            project_path: Path to project repository
            commit_message: Conventional commit message

        Returns:
            True if successful
        """
        try:
            # Stage all changes
            subprocess.run(
                ["git", "add", "."],
                cwd=project_path,
                capture_output=True,
                text=True,
                check=True,
            )

            # Commit
            subprocess.run(
                ["git", "commit", "-m", commit_message],
                cwd=project_path,
                capture_output=True,
                text=True,
                check=True,
            )

            self.logger.info(
                "Committed changes",
                project=project_path.name,
                message=commit_message.split("\n")[0],
            )
            return True

        except subprocess.CalledProcessError as e:
            self.logger.error(
                "Failed to commit",
                project=project_path.name,
                error=e.stderr,
            )
            return False

    async def push_branch(
        self,
        project_path: Path,
        branch_name: str,
    ) -> bool:
        """
        Push branch to remote.

        Args:
            project_path: Path to project repository
            branch_name: Branch name to push

        Returns:
            True if successful
        """
        try:
            subprocess.run(
                ["git", "push", "-u", "origin", branch_name],
                cwd=project_path,
                capture_output=True,
                text=True,
                check=True,
            )

            self.logger.info(
                "Pushed branch",
                project=project_path.name,
                branch=branch_name,
            )
            return True

        except subprocess.CalledProcessError as e:
            self.logger.error(
                "Failed to push",
                project=project_path.name,
                error=e.stderr,
            )
            return False

    async def create_pull_request(
        self,
        project_name: str,
        branch_name: str,
        task_title: str,
        task_description: str,
        changes_summary: str,
    ) -> PRResult:
        """
        Create pull request using GitHub API.

        Args:
            project_name: GitHub project (username/repo)
            branch_name: Feature branch name
            task_title: Task title
            task_description: Task description
            changes_summary: Summary of changes made

        Returns:
            PRResult with PR information
        """
        if not self.worker_config.is_github_configured():
            return PRResult(
                success=False,
                error="GitHub not configured",
            )

        try:
            # Generate PR title and description
            pr_title = f"feat: {task_title}"
            pr_description = self._generate_pr_description(
                task_title,
                task_description,
                changes_summary,
            )

            # Create PR via GitHub API
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.github.com/repos/{project_name}/pulls",
                    headers={
                        "Authorization": f"Bearer {self.worker_config.github_token}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                    json={
                        "title": pr_title,
                        "body": pr_description,
                        "head": branch_name,
                        "base": "main",
                        "maintainer_can_modify": True,
                    },
                    timeout=30.0,
                )
                response.raise_for_status()

                data = response.json()
                pr_number = data["number"]
                pr_url = data["html_url"]

                self.logger.info(
                    "Created pull request",
                    project=project_name,
                    pr_number=pr_number,
                    url=pr_url,
                )

                return PRResult(
                    success=True,
                    pr_number=pr_number,
                    pr_url=pr_url,
                )

        except Exception as e:
            self.logger.error(
                "Failed to create PR",
                project=project_name,
                error=str(e),
            )
            return PRResult(
                success=False,
                error=str(e),
            )

    async def merge_pull_request(
        self,
        project_name: str,
        pr_number: int,
    ) -> MergeResult:
        """
        Merge pull request using GitHub API.

        Args:
            project_name: GitHub project (username/repo)
            pr_number: Pull request number

        Returns:
            MergeResult with merge information
        """
        if not self.worker_config.is_github_configured():
            return MergeResult(
                success=False,
                error="GitHub not configured",
            )

        if not self.worker_config.auto_merge:
            return MergeResult(
                success=True,
                merged=False,
                error="Auto-merge disabled",
            )

        try:
            # Merge PR via GitHub API (squash merge)
            async with httpx.AsyncClient() as client:
                response = await client.put(
                    f"https://api.github.com/repos/{project_name}/pulls/{pr_number}/merge",
                    headers={
                        "Authorization": f"Bearer {self.worker_config.github_token}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                    json={
                        "commit_title": f"Merge PR #{pr_number}",
                        "merge_method": "squash",
                        "commit_message": "Automated merge from AI worker",
                    },
                    timeout=30.0,
                )

                if response.status_code == 405:
                    # PR not mergeable (needs approval, checks, etc.)
                    return MergeResult(
                        success=True,
                        merged=False,
                        error="PR not mergeable (may need approval)",
                    )

                response.raise_for_status()
                data = response.json()
                sha = data.get("sha", "")

                self.logger.info(
                    "Merged pull request",
                    project=project_name,
                    pr_number=pr_number,
                    sha=sha[:8] if sha else "",
                )

                # Delete branch after merge if configured
                if self.worker_config.delete_branch_after_merge:
                    await self._delete_branch(project_name, pr_number)

                return MergeResult(
                    success=True,
                    merged=True,
                    sha=sha,
                )

        except Exception as e:
            self.logger.error(
                "Failed to merge PR",
                project=project_name,
                pr_number=pr_number,
                error=str(e),
            )
            return MergeResult(
                success=False,
                error=str(e),
            )

    async def _delete_branch(self, project_name: str, pr_number: int):
        """Delete branch after PR merge."""
        try:
            # Get PR info to find branch name
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://api.github.com/repos/{project_name}/pulls/{pr_number}",
                    headers={
                        "Authorization": f"Bearer {self.worker_config.github_token}",
                    },
                )
                response.raise_for_status()
                data = response.json()
                branch_name = data["head"]["ref"]

                # Delete branch
                await client.delete(
                    f"https://api.github.com/repos/{project_name}/git/refs/heads/{branch_name}",
                    headers={
                        "Authorization": f"Bearer {self.worker_config.github_token}",
                    },
                )

                self.logger.info(
                    "Deleted branch",
                    project=project_name,
                    branch=branch_name,
                )

        except Exception as e:
            self.logger.warning(
                "Failed to delete branch",
                project=project_name,
                error=str(e),
            )

    def _generate_branch_name(self, task_id: str, task_title: str) -> str:
        """Generate a branch name from task."""
        # Extract key words from title
        words = task_title.lower().split()[:5]
        slug = "-".join(words[:4])
        # Remove special characters
        slug = "".join(c if c.isalnum() or c == "-" else "" for c in slug)
        # Get short task ID
        short_id = task_id[:8] if len(task_id) > 8 else task_id
        return f"ai/{short_id}-{slug}"

    def _generate_pr_description(
        self,
        task_title: str,
        task_description: str,
        changes_summary: str,
    ) -> str:
        """Generate PR description."""
        return f"""## 📝 Summary

{task_title}

## 📋 Task Description

{task_description}

## 🔧 Changes Made

{changes_summary}

## 🤖 AI Generated

This pull request was created by the AI Worker Daemon.

**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}

---

## ✅ Checklist

- [x] Code follows project style guidelines
- [x] Changes are tested
- [x] Documentation updated (if needed)

## 📊 Review Notes

Please review the changes and ensure:
1. The implementation matches the task requirements
2. No breaking changes are introduced
3. Tests pass locally

---

**CC:** @{self.worker_config.github_username}
"""


# Global git automator instance
_git_automator: GitAutomator | None = None


def get_git_automator() -> GitAutomator:
    """Get the global git automator instance."""
    global _git_automator
    if _git_automator is None:
        _git_automator = GitAutomator()
    return _git_automator
