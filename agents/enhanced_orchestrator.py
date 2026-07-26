"""
Enhanced Orchestrator - Integrates all features into the workflow.

This wrapper adds:
1. PR Review after PR creation (with feedback loop)
2. Branch cleanup after successful completion (rate limited)
3. Task recovery/checkpointing
4. Progress tracking
5. ID tracking for full traceability
"""

import asyncio
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from agents.orchestrator.main_orchestrator import create_orchestrator
from agents.base.base_agent import AgentResult
from agents.automation.id_tracking import TaskContext, IDTrackingMixin, store_context
from utils.logger import get_logger

logger = get_logger("enhanced_orchestrator")


class EnhancedOrchestrator:
    """
    Enhanced orchestrator with all features auto-integrated.

    Workflow:
    1. Checkpoint at start
    2. Run standard orchestrator
    3. Post-process results:
       - PR review if PR was created
       - Branch cleanup if successful (rate limited)
    4. Update checkpoint
    """

    def __init__(self):
        self.orchestrator = None
        self.logger = get_logger("enhanced_orchestrator")
        self._last_branch_cleanup: Optional[datetime] = None

    async def initialize(self):
        """Initialize the orchestrator."""
        self.orchestrator = await create_orchestrator()

    async def execute(
        self,
        task: str,
        task_id: Optional[str] = None,
        **kwargs: Any
    ) -> AgentResult:
        """
        Execute task with full feature integration.

        Args:
            task: Task description
            task_id: Optional task ID for recovery
            **kwargs: Additional parameters (including trello_card_id, trello_card_url, etc.)

        Returns:
            Agent result with all post-processing applied
        """
        from worker.task_recovery import get_task_recovery

        recovery = get_task_recovery()
        task_id = task_id or f"task_{uuid4().hex[:8]}"

        # === CONTEXT TRACKING: Create or extract TaskContext ===
        context = IDTrackingMixin.get_context_from_kwargs(**kwargs)

        # If no task_id in context, use the one we generated
        if not context.task_id:
            context.task_id = task_id

        # === CRITICAL: Set original_task if not already set ===
        # This is needed for PR title generation to use the actual task instead of subtasks
        if not context.original_task:
            # Extract the original task from the task parameter
            # The task parameter has format like "## Task Request:\n[laptop-recommendation] [agent] P2: Add feature\n..."
            import re
            # Extract just the task title from the enhanced task format
            task_match = re.search(r'## Task Request:\s*\n(.+?)(?:\n|$)', task)
            if task_match:
                context.original_task = task_match.group(1).strip()
            else:
                # Fallback: use the first 200 chars of task
                context.original_task = task[:200]

            # Extract project name from original_task
            # Format: "[project-name] [agent] P2: Task description"
            project_match = re.search(r'\[([^\]]+)\]', context.original_task)
            if project_match:
                context.project_name = project_match.group(1)

            self.logger.info(
                "Set original_task in context",
                original_task=context.original_task[:60],
                project_name=context.project_name,
            )

        # Store context for later retrieval
        store_context(context.task_id, context)

        self.logger.info(
            "Created task context",
            task_id=task_id[:8],
            trello_id=context.trello_card_id[:8] if context.trello_card_id else None,
            is_fix=context.is_fix_task,
        )

        # Add context to kwargs for all agents
        kwargs_with_context = {
            **kwargs,
            "task_context": context,
            "trello_card_id": context.trello_card_id,
            "trello_card_url": context.trello_card_url,
            "is_fix_task": context.is_fix_task,
            "fix_for_pr": context.fix_for_pr,
            "supersedes_pr": context.supersedes_pr,
            "review_cycle": context.review_cycle,
        }

        # Step 1: Check for existing checkpoint
        checkpoint = recovery.load_checkpoint(task_id)
        if checkpoint:
            self.logger.info(
                "Resuming from checkpoint",
                task_id=task_id[:8],
                progress=checkpoint.get("metadata", {}).get("progress"),
            )

        # Step 2: Save initial checkpoint
        recovery.save_checkpoint(
            task_id,
            {"task": task, "status": "started"},
            {"progress": 0, "working_directory": kwargs.get("context", {}).get("working_directory")},
        )

        try:
            # Step 3: Execute standard orchestrator with context
            result = await self.orchestrator.execute(task, **kwargs_with_context)

            # Update context with PR info if available
            if result.metadata:
                pr_url = result.metadata.get("pr_url") or result.metadata.get("url")
                if pr_url:
                    context.pr_url = pr_url
                    # Extract PR number
                    import re
                    pr_match = re.search(r'/pull/(\d+)', pr_url)
                    if pr_match:
                        context.pr_number = int(pr_match.group(1))
                        self.logger.info("Updated context with PR info", pr_number=context.pr_number)
                        # Store updated context
                        store_context(context.task_id, context)

            # Step 4: Post-processing based on results
            if result.is_success() or result.is_partial():
                await self._post_process_success(result, task_id, recovery, context)
            else:
                await self._post_process_failure(result, task_id, recovery)

            return result

        except Exception as e:
            self.logger.error("Orchestrator execution failed", error=str(e))

            # Save failure checkpoint
            recovery.save_checkpoint(
                task_id,
                {"task": task, "status": "failed", "error": str(e)},
                {"progress": 0, "failed": True},
            )

            return AgentResult(
                status="error",
                errors=[str(e)],
            )

    async def _post_process_success(
        self,
        result: AgentResult,
        task_id: str,
        recovery,
        context: TaskContext,
    ):
        """Post-process successful task execution."""
        self.logger.info("Post-processing successful task")

        # Extract working directory and PR info
        working_dir = result.metadata.get("working_directory")
        pr_url = result.metadata.get("pr_url") or result.metadata.get("url")
        pr_number = result.metadata.get("pr_number") or context.pr_number

        # 1. PR Review - if PR was created AND we have working directory
        if pr_url and pr_number:
            if not working_dir:
                self.logger.warning(
                    "Cannot run PR review - no working directory in result metadata",
                    pr_number=pr_number,
                )
            else:
                self.logger.info("Running PR review with feedback loop", pr_number=pr_number)
                try:
                    review_result = await self._review_pr(
                        repo_path=working_dir,
                        pr_number=pr_number,
                        context=context,
                    )
                    recovery.save_checkpoint(
                        task_id,
                        {"status": "pr_reviewed"},
                        {"progress": 95, "pr_reviewed": True},
                    )

                    # === NEW: Handle feedback loop if PR not approved ===
                    if not review_result.is_success():
                        self.logger.warning(
                            "PR review not approved",
                            pr_number=pr_number,
                            errors=review_result.errors,
                        )

                        # Create fix task in Trello for the issues
                        await self._create_fix_tasks_for_review(
                            pr_number=pr_number,
                            review_result=review_result,
                            context=context,
                        )

                except Exception as e:
                    self.logger.warning("PR review failed", error=str(e))

        # 2. Branch cleanup - cleanup old branches after successful completion
        # Check if branch cleanup is enabled and enough time has passed since last cleanup
        from worker.worker_config import get_worker_config
        worker_config = get_worker_config()

        if working_dir and worker_config.enable_branch_cleanup:
            # Check if enough time has passed since last cleanup
            should_cleanup = False
            if self._last_branch_cleanup is None:
                # First time, run cleanup
                should_cleanup = True
                self.logger.info("First branch cleanup")
            else:
                # Check if interval has passed
                time_since_cleanup = datetime.utcnow() - self._last_branch_cleanup
                interval_hours = worker_config.branch_cleanup_interval_hours
                if time_since_cleanup >= timedelta(hours=interval_hours):
                    should_cleanup = True
                    self.logger.info(
                        "Branch cleanup interval passed",
                        hours_since_last=time_since_cleanup.total_seconds() / 3600,
                        interval_hours=interval_hours,
                    )
                else:
                    self.logger.debug(
                        "Skipping branch cleanup - interval not yet passed",
                        hours_until_next=(timedelta(hours=interval_hours) - time_since_cleanup).total_seconds() / 3600,
                    )

            if should_cleanup:
                try:
                    await self._cleanup_branches(working_dir)
                    self._last_branch_cleanup = datetime.utcnow()
                except Exception as e:
                    self.logger.warning("Branch cleanup failed", error=str(e))
        elif working_dir and not worker_config.enable_branch_cleanup:
            self.logger.info("Branch cleanup disabled in configuration")

        # 3. Mark as completed - delete checkpoint
        recovery.delete_checkpoint(task_id)

    async def _post_process_failure(
        self,
        result: AgentResult,
        task_id: str,
        recovery,
    ):
        """Post-process failed task execution."""
        self.logger.warning("Task execution failed")

        # Save checkpoint for potential recovery
        recovery.save_checkpoint(
            task_id,
            {"status": "failed", "errors": result.errors},
            {"progress": 0, "failed": True, "errors": result.errors},
        )

    async def _review_pr(self, repo_path: str, pr_number: int, context=None):
        """Review a pull request with enhanced feedback loop.

        Returns:
            AgentResult with verdict (approved/needs_changes/rejected)
        """
        from agents.github.github_pr_reviewer import get_github_pr_reviewer
        from worker.trello.client import get_trello_client

        # Get Trello client for card movement
        trello_client = get_trello_client()

        self.logger.info("Starting PR review", pr_number=pr_number)

        try:
            # Use GitHub PR reviewer (which we know works and posts comments)
            reviewer = await get_github_pr_reviewer()

            result = await reviewer.review_and_post(
                pr_number=pr_number,
                workspace=repo_path,
            )

            self.logger.info(
                "PR review completed",
                verdict=result.verdict,
                summary=result.summary[:100] if result.summary else "",
            )

            # === NEW: Move card to DONE if PR approved ===
            if result.verdict == "approved":
                trello_card_id = getattr(context, "trello_card_id", "") if context else ""
                if trello_card_id:
                    self.logger.info("PR approved, moving card to DONE", card_id=trello_card_id[:8])
                    try:
                        moved = await trello_client.move_to_done(trello_card_id)
                        if moved:
                            self.logger.info("Card moved to DONE", card_id=trello_card_id[:8])
                        else:
                            self.logger.warning("Failed to move card to DONE", card_id=trello_card_id[:8])
                    except Exception as e:
                        self.logger.error("Error moving card to DONE", error=str(e))

            # === Convert ReviewResult to AgentResult ===
            # Map verdict to AgentResult status
            if result.verdict == "approved":
                agent_result = AgentResult(
                    status="success",
                    output=result.summary,
                )
            elif result.verdict == "needs_changes":
                # Convert security_issues and quality_issues to errors
                errors = []
                for issue in result.security_issues:
                    errors.append(f"{issue.severity} {issue.category}: {issue.title}")
                for issue in result.quality_issues:
                    errors.append(f"{issue.severity} {issue.category}: {issue.title}")

                agent_result = AgentResult(
                    status="error",  # Will trigger feedback loop
                    errors=errors,
                    output=result.summary,
                )
            else:  # rejected
                errors = ["PR rejected"] + [
                    f"{issue.severity} {issue.category}: {issue.title}"
                    for issue in result.security_issues + result.quality_issues
                ]
                agent_result = AgentResult(
                    status="error",
                    errors=errors,
                    output=result.summary,
                )

            return agent_result

        except Exception as e:
            self.logger.error("PR review failed", error=str(e))
            # Return error so feedback loop is triggered
            return AgentResult(
                status="error",
                errors=[f"PR review failed: {str(e)}"],
            )

    async def _create_fix_tasks_for_review(
        self,
        pr_number: int,
        review_result: AgentResult,
        context: TaskContext,
    ):
        """Create fix tasks in Trello when PR review fails.

        Args:
            pr_number: Pull request number
            review_result: Result from PR review
            context: Task context with project info
        """
        from worker.trello.client import get_trello_client

        trello = get_trello_client()

        # Get project name from context or PR URL
        project_name = getattr(context, "project_name", "unknown")
        if not project_name or project_name == "unknown":
            # Try to extract from PR URL
            pr_url = f"https://github.com/TheCurators/*/pull/{pr_number}"
            # We'll use a default project
            project_name = "laptop-recommendation"

        # Increment review cycle
        current_cycle = getattr(context, "review_cycle", 1)
        next_cycle = current_cycle + 1

        # === ESCAPE HATCH: Prevent infinite fix loops ===
        # After 3 fix attempts, move card to Blocked instead of creating another fix card
        MAX_FIX_CYCLES = 3

        if current_cycle >= MAX_FIX_CYCLES:
            self.logger.warning(
                "Maximum fix cycles reached, moving card to Blocked",
                pr_number=pr_number,
                cycle=current_cycle,
                max_cycles=MAX_FIX_CYCLES,
            )

            # Get the original card ID
            original_card_id = getattr(context, "trello_card_id", None)
            if original_card_id:
                try:
                    # Move to Blocked list
                    moved = await trello.move_to_list(original_card_id, "Blocked")
                    if moved:
                        self.logger.info(
                            "Moved card to Blocked",
                            card_id=original_card_id[:8],
                            reason=f"Failed {current_cycle} fix attempts",
                        )

                        # Add comment explaining why
                        await trello.add_card_comment(
                            original_card_id,
                            f"⚠️ **Automated blocking after {current_cycle} fix attempts**\n\n"
                            f"This task has been automatically blocked after {MAX_FIX_CYCLES} fix cycles. "
                            f"Each fix attempt did not resolve the PR review issues. "
                            f"Manual intervention is required to:\n"
                            f"1. Review the PR feedback\n"
                            f"2. Understand why fixes aren't working\n"
                            f"3. Either fix manually or unblock the task\n\n"
                            f"PR: #{pr_number}\n"
                            f"Last errors:\n{errors_text[:500]}"
                        )
                        return None
                except Exception as e:
                    self.logger.error("Failed to move card to Blocked", error=str(e))

            # If we can't move to Blocked, at least stop creating fix cards
            self.logger.error("Cannot create another fix card", cycle=current_cycle)
            return None

        # Create task description
        errors_text = "\n".join([f"- {err}" for err in (review_result.errors or [])])

        task_name = f"[{project_name}] [agent] [FIX-{pr_number}] P1: Fix PR #{pr_number} review issues (cycle {next_cycle})"

        task_desc = f"""Fix issues found during PR review for PR #{pr_number}.

## PR Review Feedback:
{errors_text}

## Context:
- Original PR: #{pr_number}
- Review cycle: {next_cycle}
- This is a fix task to address the review feedback

## Instructions:
1. Review the feedback above
2. Fix all the issues listed
3. Create a new PR with the fixes
4. Reference PR #{pr_number} in the commit message

## Priority: P1 (High - blocking previous PR)
"""

        try:
            card_id = await trello.create_card(
                name=task_name,
                desc=task_desc,
            )

            if card_id:
                self.logger.info(
                    "Created fix task for PR review",
                    pr_number=pr_number,
                    cycle=next_cycle,
                    card_id=card_id[:8],
                )

                # Add label
                await trello.add_card_label(card_id, "P1")

                return card_id
            else:
                self.logger.error("Failed to create fix task")

        except Exception as e:
            self.logger.error("Failed to create fix task", error=str(e))

        return None

    async def _cleanup_branches(self, repo_path: str):
        """Clean up old git branches using configuration settings."""
        from worker.git_utils import GitUtils
        from worker.worker_config import get_worker_config

        git = GitUtils()
        worker_config = get_worker_config()

        # Clean up branches using configured settings
        result = git.cleanup_old_branches(
            repo_path=repo_path,
            days_old=worker_config.branch_cleanup_days_old,
            protect_branches=worker_config.branch_cleanup_protected_branches,
            dry_run=False,
        )

        self.logger.info(
            "Branch cleanup completed",
            deleted=result.get("branches_deleted", 0),
            found=result.get("branches_found", 0),
            days_old=worker_config.branch_cleanup_days_old,
        )


# Global instance
_enhanced_orchestrator: Optional[EnhancedOrchestrator] = None


async def get_enhanced_orchestrator() -> EnhancedOrchestrator:
    """Get the global enhanced orchestrator instance."""
    global _enhanced_orchestrator
    if _enhanced_orchestrator is None:
        _enhanced_orchestrator = EnhancedOrchestrator()
        await _enhanced_orchestrator.initialize()
    return _enhanced_orchestrator
