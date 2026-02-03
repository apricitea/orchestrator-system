"""
Feedback Loop Manager - Autonomous Retry and Fix Task Creation

Implements the full feedback loop:
1. Auto-retry on review failure
2. Auto-create fix tasks in Trello
3. Escalate to human after N attempts
4. Track metrics and success rates
"""

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Literal, Optional, Dict, Any

from agents.orchestrator.task_context import (
    TaskContext,
    TaskIteration,
    ReviewVerdict,
    TaskStatus,
    get_task_context_manager,
)
from agents.github.github_pr_reviewer import ReviewResult
from utils.logger import get_logger


class Action(str, Enum):
    """Action to take after review."""
    RETRY_NOW = "retry_now"
    CREATE_FIX_TASK = "create_fix_task"
    ESCALATE = "escalate"
    MARK_DONE = "mark_done"


@dataclass
class FeedbackDecision:
    """Decision made by feedback loop."""
    action: Action
    reason: str
    retry_count: int = 0
    max_retries: int = 3
    next_steps: List[str] = field(default_factory=list)
    should_create_fix_task: bool = False
    fix_task_title: Optional[str] = None
    fix_task_description: Optional[str] = None


class FeedbackLoopManager:
    """Manages the feedback loop for PR reviews."""

    def __init__(self):
        self.logger = get_logger("feedback_loop")
        self.max_iterations = 3
        self.max_total_attempts = 5

    def decide_next_action(
        self,
        context: TaskContext,
        review_result: ReviewResult,
    ) -> FeedbackDecision:
        """Decide what action to take after PR review."""
        current_iteration = context.current_iteration
        total_attempts = len([i for i in context.iterations if i.status in ["completed", "needs_revision", "failed"]])

        # Approved → Mark as done
        if review_result.verdict == "approved":
            return FeedbackDecision(
                action=Action.MARK_DONE,
                reason="PR approved by automated review",
            )

        # Too many attempts → Escalate
        if total_attempts >= self.max_total_attempts:
            return FeedbackDecision(
                action=Action.ESCALATE,
                reason=f"Maximum attempts ({self.max_total_attempts}) reached",
                retry_count=total_attempts,
                max_retries=self.max_total_attempts,
            )

        # Rejected → Create fix task
        if review_result.verdict == "rejected":
            return FeedbackDecision(
                action=Action.CREATE_FIX_TASK,
                reason=f"PR rejected with {len(review_result.security_issues) + len(review_result.quality_issues)} issues",
                should_create_fix_task=True,
                fix_task_title=self._generate_fix_task_title(context),
                fix_task_description=self._generate_fix_task_description(context, review_result),
            )

        # Needs changes → Check iteration count
        if review_result.verdict == "needs_changes":
            if current_iteration >= self.max_iterations:
                return FeedbackDecision(
                    action=Action.CREATE_FIX_TASK,
                    reason=f"Maximum iterations ({self.max_iterations}) on same PR",
                    should_create_fix_task=True,
                    fix_task_title=self._generate_fix_task_title(context, priority="P2"),
                    fix_task_description=self._generate_fix_task_description(context, review_result),
                )

        # Default: create fix task
        return FeedbackDecision(
            action=Action.CREATE_FIX_TASK,
            reason="PR needs changes",
            should_create_fix_task=True,
            fix_task_title=self._generate_fix_task_title(context),
            fix_task_description=self._generate_fix_task_description(context, review_result),
        )

    def _generate_fix_task_title(self, context: TaskContext, priority: str = "P1") -> str:
        """Generate title for fix task."""
        original_short = context.original_task[:50]
        return f"[{priority}] [FIX] {original_short}... (PR #{context.current_pr_number})"

    def _generate_fix_task_description(
        self,
        context: TaskContext,
        review_result: ReviewResult,
    ) -> str:
        """Generate description for fix task."""
        pr_url = context.iterations[-1].pr_url if context.iterations else ""
        
        issues = []
        for issue in review_result.security_issues + review_result.quality_issues[:10]:
            issues.append(f"- **{issue.title}** ({issue.severity})")
        
        return f"""## Fix Required for PR #{context.current_pr_number}

### Original Task
{context.original_task}

### PR Review Result
**Verdict:** {review_result.verdict.upper()}
**Summary:** {review_result.summary}

### Issues to Fix
{chr(10).join(issues)}

**PR:** #{context.current_pr_number} - {pr_url}

---
*Created by AI Orchestrator*
*Original: https://trello.com/c/{context.trello_card_id}*
"""


def get_feedback_manager() -> FeedbackLoopManager:
    """Get global feedback loop manager instance."""
    return FeedbackLoopManager()
