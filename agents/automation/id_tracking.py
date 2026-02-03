"""
ID Tracking System for Orchestrator

Ensures traceability between:
- Trello cards
- Git commits
- Pull requests
- Fix tasks

All artifacts carry IDs for full audit trail.

NOTE: This module now imports from the comprehensive task_context system
to maintain compatibility while providing enhanced functionality.
"""

from dataclasses import dataclass, field
from typing import Optional, List, TYPE_CHECKING
from datetime import datetime

# Import the comprehensive TaskContext for extended functionality
# This maintains backward compatibility while adding iteration tracking
try:
    from agents.orchestrator.task_context import TaskContext as FullTaskContext
    _HAS_FULL_CONTEXT = True
except ImportError:
    _HAS_FULL_CONTEXT = False
    FullTaskContext = None

if _HAS_FULL_CONTEXT:
    # Use the comprehensive TaskContext with iteration tracking
    # Re-export it for backward compatibility
    TaskContext = FullTaskContext

    # Create a simple factory function for the old interface
    def create_simple_context(
        trello_card_id: str = "",
        trello_card_url: str = "",
        task_id: str = "",
        branch_name: str = "",
        commits: Optional[List[str]] = None,
        pr_number: Optional[int] = None,
        pr_url: str = "",
        is_fix_task: bool = False,
        fix_for_pr: Optional[int] = None,
        supersedes_pr: Optional[int] = None,
        review_cycle: int = 1,
        review_issues: Optional[List[str]] = None,
    ) -> 'TaskContext':
        """Create a TaskContext using the old simple interface."""
        context = TaskContext(
            task_id=task_id or "",
            trello_card_id=trello_card_id,
            trello_card_url=trello_card_url,  # NOW INCLUDED
            original_task="",  # Will be filled by caller
            project_name="",  # Will be filled by caller
            current_pr_number=pr_number,
            current_branch=branch_name,
            pr_url=pr_url,  # NOW INCLUDED
        )
        # Note: is_fix_task, fix_for_pr, review_cycle are now properties
        # They can be read but not set via constructor
        return context

else:
    # Fallback to original implementation if task_context not available
    @dataclass
    class TaskContext:
        """
        Context passed through entire orchestration lifecycle.

        This ensures all artifacts (commits, PRs) can be traced back to the original task.
        """

        # Original task identifiers
        trello_card_id: str = ""
        trello_card_url: str = ""
        task_id: str = ""

        # Git tracking
        branch_name: str = ""
        commits: List[str] = field(default_factory=list)
        pr_number: Optional[int] = None
        pr_url: str = ""

        # Fix tracking
        is_fix_task: bool = False
        fix_for_pr: Optional[int] = None
        supersedes_pr: Optional[int] = None

        # Review tracking
        review_cycle: int = 1
        review_issues: List[str] = field(default_factory=list)

        # Timestamps
        created_at: datetime = field(default_factory=datetime.utcnow)
        completed_at: Optional[datetime] = None

    def get_commit_message_prefix(self) -> str:
        """Generate commit message prefix with all IDs."""
        parts = []

        if self.trello_card_id:
            parts.append(f"[trello-{self.trello_card_id[:8]}]")

        if self.pr_number:
            parts.append(f"[pr-{self.pr_number}]")

        if self.is_fix_task and self.fix_for_pr:
            parts.append(f"[fix-for-pr-{self.fix_for_pr}]")

        if self.review_cycle > 1:
            parts.append(f"[cycle-{self.review_cycle}]")

        return " ".join(parts) + " " if parts else ""

    def get_trello_reference(self) -> str:
        """Get Trello card reference for PR descriptions."""
        if not self.trello_card_id:
            return ""

        return f"**Trello Task**: [{self.trello_card_id}]({self.trello_card_url})\n"

    def get_pr_description_metadata(self) -> str:
        """Get metadata section for PR descriptions."""
        lines = []

        if self.trello_card_id:
            lines.append(f"- **Trello Card**: {self.trello_card_id}")

        if self.commits:
            lines.append(f"- **Commits**: {', '.join(self.commits)}")

        if self.is_fix_task and self.fix_for_pr:
            lines.append(f"- **Fixes PR**: #{self.fix_for_pr}")

        if self.review_cycle > 1:
            lines.append(f"- **Review Cycle**: {self.review_cycle}")

        if not lines:
            return ""

        return "\n### Metadata\n" + "\n".join(lines) + "\n"

    def get_fix_task_description(self, original_pr_number: int, issues: List[str]) -> str:
        """Generate description for fix task in Trello."""
        return f"""## Fix Issues from PR Review

### Original PR: #{original_pr_number}
### Working Directory: {getattr(self, 'working_directory', '.')}

### Issues Found ({len(issues)}):
"""

    def create_fix_context(self, original_pr_number: int) -> 'TaskContext':
        """Create a new TaskContext for a fix task."""
        return TaskContext(
            trello_card_id=self.trello_card_id,
            task_id=self.task_id + "-fix",
            is_fix_task=True,
            fix_for_pr=original_pr_number,
            review_cycle=self.review_cycle + 1,
            created_at=datetime.utcnow()
        )


class IDTrackingMixin:
    """
    Mixin to add ID tracking to agents.

    Usage:
    ```python
    class MyAgent(IDTrackingMixin, BaseAgent):
        async def execute(self, task, **kwargs):
            context = self.get_or_create_context(**kwargs)
            # ... do work ...
            self.update_context(context)
            return AgentResult(metadata={"context": context})
        ```
    """

    @staticmethod
    def get_context_from_kwargs(**kwargs) -> TaskContext:
        """Extract TaskContext from kwargs."""
        context = kwargs.get("task_context")

        if not context:
            # Create from individual kwargs
            # Note: Using create_simple_context for compatibility
            context = TaskContext(
                task_id=kwargs.get("task_id", ""),
                trello_card_id=kwargs.get("trello_card_id", ""),
                trello_card_url=kwargs.get("trello_card_url", ""),
                original_task="",  # Will be filled by caller
                project_name="",  # Will be filled by caller
                current_pr_number=kwargs.get("pr_number") or kwargs.get("fix_for_pr"),
                current_branch=kwargs.get("branch_name", ""),
                pr_url=kwargs.get("pr_url", ""),
            )
            # Additional properties that aren't in constructor:
            # - is_fix_task: property (computed from iterations)
            # - fix_for_pr: property (alias for current_pr_number)
            # - review_cycle: property (alias for current_iteration)
            # - supersedes_pr: not used in comprehensive version

        return context

    @staticmethod
    def format_commit_message(message: str, context: TaskContext) -> str:
        """Format commit message with ID prefixes."""
        prefix = context.get_commit_message_prefix()
        return f"{prefix}{message}"

    @staticmethod
    def format_pr_description(title: str, body: str, context: TaskContext) -> str:
        """Format PR description with ID metadata."""
        metadata_section = context.get_pr_description_metadata()

        if not metadata_section:
            return body

        return f"{body}\n\n{metadata_section}"


# Global context storage (in production, use Redis or database)
_context_cache: dict[str, TaskContext] = {}


def store_context(task_id: str, context: TaskContext):
    """Store task context for later retrieval."""
    _context_cache[task_id] = context


def get_context(task_id: str) -> Optional[TaskContext]:
    """Retrieve stored task context."""
    return _context_cache.get(task_id)


def clear_context(task_id: str):
    """Clear task context after completion."""
    if task_id in _context_cache:
        del _context_cache[task_id]
