"""
Task Executor - Execute Tasks via AI Agents

Executes tasks using the orchestrator and worker agents.
Handles git workflow automation.
"""

import asyncio
import os
import subprocess
from pathlib import Path

from agents.orchestrator.enhanced_orchestrator import get_enhanced_orchestrator
from utils.logger import get_logger
from worker.availability_checker import get_availability_checker, RateLimitInfo
from worker.worker_config import get_worker_config
from worker.db_models import Task, TaskStatus
from worker.git_automator import get_git_automator
from worker.task_queue import get_task_queue_manager
from worker.trello.client import get_trello_client
from worker.telegram.bot import get_telegram_bot


def _get_enum_value(enum_or_str):
    """Get value from enum or string."""
    if isinstance(enum_or_str, str):
        return enum_or_str
    return enum_or_str.value


class TaskExecutor:
    """
    Executes tasks using the AI agent system.

    Workflow:
    1. Clone/update project repository
    2. Create feature branch
    3. Call orchestrator to execute task
    4. Commit changes
    5. Push branch
    6. Create PR
    7. Merge PR (if auto-merge enabled)
    8. Update task status
    9. Send notifications
    """

    def __init__(self):
        self.logger = get_logger("task_executor")
        self.worker_config = get_worker_config()
        self._orchestrator = None
        self._git_automator = get_git_automator()
        self._availability_checker = get_availability_checker()
        self._task_queue = get_task_queue_manager()
        self._trello_client = get_trello_client()
        self._telegram_bot = get_telegram_bot()

    async def initialize(self):
        """Initialize the executor and orchestrator."""
        try:
            self._orchestrator = await get_enhanced_orchestrator()
            self.logger.info("Task executor initialized with enhanced orchestrator")
        except Exception as e:
            self.logger.error("Failed to initialize executor", error=str(e))

    def _is_valid_project(self, project_name: str) -> bool:
        """
        Check if a project is valid (exists in projects/ directory).

        Args:
            project_name: Project name (format: username/repo)

        Returns:
            True if project exists in projects/ directory
        """
        projects_dir = self.worker_config.projects_base_path
        project_path = projects_dir / project_name
        return project_path.exists() and project_path.is_dir()

    async def execute_task(self, task: Task) -> tuple[bool, str]:
        """
        Execute a task with automatic retry logic.

        Args:
            task: Task to execute

        Returns:
            Tuple of (success, message)
        """
        try:
            self.logger.info(
                "Executing task",
                task_id=task.id[:8],
                title=task.title,
                project=task.project_name,
            )

            # Move Trello card to In Progress (marks task as started)
            if _get_enum_value(task.source) == "trello":
                await self._trello_client.move_to_in_progress(task.source_id)

            # Validate project exists
            if not self._is_valid_project(task.project_name):
                error_msg = f"Project '{task.project_name}' does not exist in {self.worker_config.projects_base_path}. Skipping task."
                self.logger.warning("Project validation failed", project=task.project_name)
                await self._task_queue.mark_trello_task_completed(
                    task.id, task.source_id, False, error_msg
                )
                await self._telegram_bot.send_notification(
                    f"⚠️ *Task Skipped*\n\n"
                    f"📌 {task.title}\n"
                    f"📁 Project: {task.project_name}\n\n"
                    f"❌ Project not found in local projects directory.",
                )
                return False, error_msg

            # Add Telegram notification
            await self._telegram_bot.send_notification(
                f"▶️ *Starting Task*\n\n"
                f"📌 {task.title}\n"
                f"📁 {task.project_name}\n"
                f"⚡ Priority: {_get_enum_value(task.priority)}",
            )

            # Step 1: Ensure project repository exists
            project_path = await self._ensure_project_repo(task.project_name, task)
            if not project_path:
                raise Exception(f"Failed to setup project repository: {task.project_name}")

            # Step 1.5: Clean up any uncommitted changes from previous runs
            try:
                self.logger.info("Cleaning up uncommitted changes from previous runs")
                subprocess.run(
                    ["git", "reset", "--hard", "HEAD"],
                    cwd=project_path,
                    capture_output=True,
                    text=True,
                    check=False
                )
                subprocess.run(
                    ["git", "clean", "-fd"],
                    cwd=project_path,
                    capture_output=True,
                    text=True,
                    check=False
                )
                self.logger.info("Repository cleaned successfully")
            except Exception as cleanup_error:
                self.logger.warning(
                    "Could not clean repository, continuing anyway",
                    error=str(cleanup_error)
                )

            # Step 2: Execute task via orchestrator with retry logic
            max_retries = self.worker_config.task_max_retries
            retry_delay = self.worker_config.task_retry_delay

            for attempt in range(max_retries):
                try:
                    self.logger.info(
                        "Calling orchestrator",
                        task=task.title,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                    )

                    # Prepare task with context for orchestrator
                    enhanced_task = f"""## Task Request:
{task.title}

## Description:
{task.description}

## Current Working Directory:
{project_path}

## Project:
{task.project_name}

## Priority:
{_get_enum_value(task.priority)}
"""

                    # Pass working_directory in context for git operations
                    result = await self._orchestrator.execute(
                        enhanced_task,
                        context={"working_directory": str(project_path)},
                    )

                    # Check result status - partial is OK if PR was created
                    pr_url = result.metadata.get("pr_url", "") if result.metadata else ""
                    is_critical_failure = not result.is_success() and not result.is_partial()

                    if is_critical_failure:
                        error_msg = "; ".join(result.errors) if result.errors else "Unknown error"
                        # If this is not the last attempt, retry
                        if attempt < max_retries - 1:
                            self.logger.warning(
                                "Orchestrator failed, retrying",
                                attempt=attempt + 1,
                                error=error_msg,
                                retry_after=f"{retry_delay}s",
                            )
                            await asyncio.sleep(retry_delay)
                            continue
                        else:
                            raise Exception(f"Orchestrator failed after {max_retries} attempts: {error_msg}")

                    # If partial success without PR, still retry
                    if result.is_partial() and not pr_url:
                        error_msg = "; ".join(result.errors) if result.errors else "Partial completion without PR"
                        if attempt < max_retries - 1:
                            self.logger.warning(
                                "Partial completion without PR, retrying",
                                attempt=attempt + 1,
                                error=error_msg,
                                retry_after=f"{retry_delay}s",
                            )
                            await asyncio.sleep(retry_delay)
                            continue
                        else:
                            # Last attempt, will proceed with partial result
                            self.logger.warning(
                                "Proceeding with partial result after all retries exhausted",
                                error=error_msg
                            )

                    # Success (or acceptable partial)! Break out of retry loop
                    break

                except Exception as orchestrator_error:
                    error_msg = str(orchestrator_error)
                    # If this is not the last attempt, retry
                    if attempt < max_retries - 1:
                        self.logger.warning(
                            "Orchestrator exception, retrying",
                            attempt=attempt + 1,
                            error=error_msg,
                            retry_after=f"{retry_delay}s",
                        )
                        await asyncio.sleep(retry_delay)
                        continue
                    else:
                        raise

            # Extract PR URL if available from result
            pr_url = result.metadata.get("pr_url", "")

            # Mark task completed - moves to Review, stores PR URL in Trello comment, sends notification
            await self._task_queue.mark_trello_task_completed(
                task.id, task.source_id, True, "", pr_url
            )

            if pr_url:
                self.logger.info(
                    "Task completed successfully",
                    task_id=task.id[:8],
                    pr_url=pr_url,
                )
                return True, f"Completed: PR {pr_url}"
            else:
                self.logger.info(
                    "Task completed successfully",
                    task_id=task.id[:8],
                )
                return True, "Completed"

        except Exception as e:
            error_msg = str(e)
            self.logger.error(
                "Task execution failed",
                task_id=task.id[:8],
                error=error_msg,
            )

            # Mark as failed - moves card back, stores error in Trello comment, sends notification
            if _get_enum_value(task.source) == "trello":
                await self._task_queue.mark_trello_task_completed(
                    task.id, task.source_id, False, error_msg
                )
            else:
                await self._task_queue.mark_task_completed(
                    task.id, False, error_msg
                )

            return False, error_msg

    async def _ensure_project_repo(
        self,
        project_name: str,
        task: Task,
    ) -> Path | None:
        """
        Ensure project repository exists and is up to date.

        Args:
            project_name: Project name (format: username/repo)
            task: Task for context

        Returns:
            Path to project repository or None
        """
        try:
            projects_dir = self.worker_config.projects_base_path
            project_path = projects_dir / project_name

            # Clone if doesn't exist
            if not project_path.exists():
                self.logger.info("Cloning project", project=project_name)

                # Use git credential helper instead of embedding token in URL (security)
                github_url = f"https://github.com/{project_name}.git"
                env = os.environ.copy()
                env['GIT_ASKPASS'] = 'echo'
                env['GIT_USERNAME'] = 'oauth2'
                env['GIT_PASSWORD'] = self.worker_config.github_token

                subprocess.run(
                    ["git", "clone", github_url, str(project_path)],
                    check=True,
                    capture_output=True,
                    text=True,
                    env=env,
                )

                self.logger.info("Project cloned", path=str(project_path))
                return project_path

            # Update if exists
            self.logger.info("Updating project", project=project_name)

            subprocess.run(
                ["git", "fetch", "origin"],
                cwd=project_path,
                check=True,
                capture_output=True,
                text=True,
            )

            return project_path

        except subprocess.CalledProcessError as e:
            self.logger.error(
                "Failed to setup project repo",
                project=project_name,
                error=e.stderr,
            )
            return None

    def _generate_commit_message(self, task: Task) -> str:
        """Generate conventional commit message."""
        # Determine commit type based on task title
        title_lower = task.title.lower()
        if any(word in title_lower for word in ["fix", "bug", "error"]):
            commit_type = "fix"
        elif any(word in title_lower for word in ["add", "implement", "create"]):
            commit_type = "feat"
        elif any(word in title_lower for word in ["refactor", "clean"]):
            commit_type = "refactor"
        elif any(word in title_lower for word in ["test", "spec"]):
            commit_type = "test"
        elif any(word in title_lower for word in ["doc", "readme"]):
            commit_type = "docs"
        else:
            commit_type = "feat"

        # Generate commit message
        return f"""{commit_type}: {task.title}

{task.description}

---

Task ID: {task.id}
Source: {_get_enum_value(task.source)}
Priority: {_get_enum_value(task.priority)}

Generated by AI Worker Daemon
"""

    async def record_token_usage(self, tokens: int):
        """Record token usage for rate limit tracking."""
        await self._availability_checker.record_token_usage(tokens)


# Global task executor instance
_task_executor: TaskExecutor | None = None


def get_task_executor() -> TaskExecutor:
    """Get the global task executor instance."""
    global _task_executor
    if _task_executor is None:
        _task_executor = TaskExecutor()
    return _task_executor
