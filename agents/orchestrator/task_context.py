"""
Task Context and Historical Tracking System

Tracks task iterations, PR history, and review results across multiple attempts.
Provides checkpointing for recovery and full audit trail.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Literal, Optional, Dict, Any


class ReviewVerdict(str, Enum):
    """PR review verdict."""
    APPROVED = "approved"
    NEEDS_CHANGES = "needs_changes"
    REJECTED = "rejected"


class TaskStatus(str, Enum):
    """Task status across iterations."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    NEEDS_REVISION = "needs_revision"
    IN_REVIEW = "in_review"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class SecurityIssue:
    """Security issue found during review."""
    severity: str  # critical, warning, info
    category: str  # SQL_INJECTION, XSS, HARDCODED_SECRET, etc.
    title: str
    description: str
    file_path: str
    line_number: int
    code_snippet: str = ""


@dataclass
class QualityIssue:
    """Quality issue found during review."""
    category: str  # ERROR_HANDLING, TESTING, DOCUMENTATION, etc.
    severity: str  # critical, warning, info
    title: str
    description: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None


@dataclass
class TaskIteration:
    """
    Represents a single attempt at completing a task.

    Tracks:
    - What was attempted
    - What was produced (commits, files, PR)
    - What was found in review (security, quality issues)
    - What needs to be fixed
    """
    iteration_number: int
    timestamp: datetime
    status: Literal["in_progress", "failed", "completed", "needs_revision"]

    # PR information
    pr_number: Optional[int] = None
    pr_url: Optional[str] = None
    pr_action: Optional[Literal["created", "updated", "reused"]] = None

    # Review results
    review_verdict: Optional[ReviewVerdict] = None
    security_issues: List[SecurityIssue] = field(default_factory=list)
    quality_issues: List[QualityIssue] = field(default_factory=list)
    test_coverage: float = 0.0

    # What was done
    commits_created: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    branch_name: Optional[str] = None

    # What needs to be fixed
    fix_recommendations: List[str] = field(default_factory=list)

    # Additional metadata
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None
    agent_results: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        # Handle datetime
        data['timestamp'] = self.timestamp.isoformat()
        # Handle ReviewVerdict enum
        if self.review_verdict:
            data['review_verdict'] = self.review_verdict.value
        # Handle SecurityIssue and QualityIssue lists
        data['security_issues'] = [asdict(i) for i in self.security_issues]
        data['quality_issues'] = [asdict(i) for i in self.quality_issues]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TaskIteration':
        """Create from dictionary."""
        # Parse timestamp
        if isinstance(data.get('timestamp'), str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])

        # Parse ReviewVerdict
        if data.get('review_verdict'):
            data['review_verdict'] = ReviewVerdict(data['review_verdict'])

        # Parse security issues
        security_issues = data.pop('security_issues', [])
        data['security_issues'] = [SecurityIssue(**i) if isinstance(i, dict) else i for i in security_issues]

        # Parse quality issues
        quality_issues = data.pop('quality_issues', [])
        data['quality_issues'] = [QualityIssue(**i) if isinstance(i, dict) else i for i in quality_issues]

        return cls(**data)

    def get_summary(self) -> str:
        """Get human-readable summary of this iteration."""
        lines = [
            f"### Iteration {self.iteration_number}: {self.status.upper()}",
            f"**Time:** {self.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        ]

        if self.pr_number:
            action_emoji = {"created": "🆕", "updated": "🔄", "reused": "♻️"}.get(self.pr_action, "📌")
            lines.append(f"**PR:** {action_emoji} #{self.pr_number} ({self.pr_action})")

        if self.review_verdict:
            verdict_emoji = {
                "approved": "✅",
                "needs_changes": "⚠️",
                "rejected": "❌"
            }.get(self.review_verdict.value, "❓")
            lines.append(f"**Review:** {verdict_emoji} {self.review_verdict.value.upper()}")

            if self.security_issues:
                critical = len([i for i in self.security_issues if i.severity == "critical"])
                lines.append(f"- Security: {len(self.security_issues)} issues ({critical} critical)")

            if self.quality_issues:
                lines.append(f"- Quality: {len(self.quality_issues)} issues")

            if self.test_coverage > 0:
                lines.append(f"- Coverage: {self.test_coverage}%")

        if self.fix_recommendations:
            lines.append(f"**Fixes Needed:** {len(self.fix_recommendations)}")
            for fix in self.fix_recommendations[:3]:
                lines.append(f"  - {fix}")

        if self.error_message:
            lines.append(f"**Error:** {self.error_message[:100]}")

        return "\n".join(lines)


@dataclass
class TaskContext:
    """
    Full context for a task across multiple iterations.

    Provides:
    - Historical tracking of all attempts
    - PR management (create vs update decisions)
    - Recovery from failures
    - Full audit trail
    """

    # Task identification
    task_id: str
    trello_card_id: str
    original_task: str
    project_name: str

    # Current state
    current_iteration: int = 0
    current_pr_number: Optional[int] = None
    current_branch: Optional[str] = None  # Also accessible as 'branch_name' for compatibility
    current_status: TaskStatus = TaskStatus.PENDING

    # Iteration history
    iterations: List[TaskIteration] = field(default_factory=list)

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None  # When task was completed

    # Repository info
    repo_owner: Optional[str] = None
    repo_name: Optional[str] = None

    # === ADDITIONAL COMPATIBILITY FIELDS (from id_tracking.TaskContext) ===
    # These fields are used by enhanced_orchestrator and must be present
    # for full backward compatibility
    trello_card_url: str = ""  # Can be constructed from trello_card_id
    pr_url: str = ""  # Can be constructed from pr_number and repo info
    supersedes_pr: Optional[int] = None  # PR this task supersedes (for fix tasks)
    review_issues: List[str] = field(default_factory=list)  # Issues from review
    commits: List[str] = field(default_factory=list)  # Commit hashes (also tracked in iterations)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        # Handle datetimes
        data['created_at'] = self.created_at.isoformat()
        data['updated_at'] = self.updated_at.isoformat()
        if self.completed_at:
            data['completed_at'] = self.completed_at.isoformat()
        # Handle TaskStatus enum
        data['current_status'] = self.current_status.value
        # Handle iterations
        data['iterations'] = [i.to_dict() for i in self.iterations]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TaskContext':
        """Create from dictionary."""
        # Parse datetimes
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if isinstance(data.get('updated_at'), str):
            data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        if isinstance(data.get('completed_at'), str):
            data['completed_at'] = datetime.fromisoformat(data['completed_at'])

        # Parse TaskStatus
        if isinstance(data.get('current_status'), str):
            data['current_status'] = TaskStatus(data['current_status'])

        # Parse iterations
        iterations = data.pop('iterations', [])
        data['iterations'] = [TaskIteration.from_dict(i) for i in iterations]

        return cls(**data)

    def start_new_iteration(self) -> TaskIteration:
        """Start a new iteration."""
        self.current_iteration += 1
        self.current_status = TaskStatus.IN_PROGRESS
        self.updated_at = datetime.utcnow()

        iteration = TaskIteration(
            iteration_number=self.current_iteration,
            timestamp=datetime.utcnow(),
            status="in_progress",
        )

        self.iterations.append(iteration)
        return iteration

    def complete_iteration(
        self,
        iteration: TaskIteration,
        status: Literal["completed", "failed", "needs_revision"],
        pr_number: Optional[int] = None,
        pr_url: Optional[str] = None,
        pr_action: Optional[str] = None,
        review_verdict: Optional[ReviewVerdict] = None,
    ):
        """Mark an iteration as complete."""
        iteration.status = status
        iteration.pr_number = pr_number or iteration.pr_number
        iteration.pr_url = pr_url or iteration.pr_url
        iteration.pr_action = pr_action or iteration.pr_action
        iteration.review_verdict = review_verdict or iteration.review_verdict

        # Update current state
        self.current_pr_number = iteration.pr_number
        self.updated_at = datetime.utcnow()

        if status == "completed":
            self.current_status = TaskStatus.IN_REVIEW if iteration.pr_number else TaskStatus.COMPLETED
        elif status == "needs_revision":
            self.current_status = TaskStatus.NEEDS_REVISION
        else:
            self.current_status = TaskStatus.FAILED

    def should_create_new_pr(self) -> bool:
        """
        Decide whether to create new PR or update existing.

        Returns:
            True if should create new PR, False if should update existing
        """
        # No PR exists → create new
        if self.current_pr_number is None:
            return True

        # Too many iterations on same PR → fresh start
        if self.current_iteration >= 3:
            return True

        # PR exists and iterations < 3 → update existing (default behavior)
        # Previous iteration was rejected → also update same PR
        return False  # Update existing PR

    def get_current_pr(self) -> Optional[int]:
        """Get the current PR number for this task."""
        return self.current_pr_number

    def get_last_iteration(self) -> Optional[TaskIteration]:
        """Get the most recent iteration."""
        return self.iterations[-1] if self.iterations else None

    def get_history_summary(self) -> str:
        """Get formatted history of all iterations."""
        if not self.iterations:
            return "No iterations yet."

        lines = [
            f"## Task History: {self.original_task[:60]}...",
            f"",
            f"**Current Status:** {self.current_status.value.upper()}",
            f"**Total Iterations:** {self.current_iteration}",
            f"**Current PR:** #{self.current_pr_number}" if self.current_pr_number else "**Current PR:** None",
            f"",
            f"### Iterations:",
        ]

        for iteration in self.iterations:
            lines.append("")
            lines.append(iteration.get_summary())

        return "\n".join(lines)

    def get_fix_recommendations(self) -> List[str]:
        """Get all fix recommendations from previous iterations."""
        recommendations = []
        for iteration in self.iterations:
            recommendations.extend(iteration.fix_recommendations)
        return recommendations

    # ========== ID TRACKING COMPATIBILITY METHODS ==========
    # These methods provide compatibility with agents.automation.id_tracking.TaskContext

    def get_commit_message_prefix(self) -> str:
        """Generate commit message prefix with all IDs."""
        parts = []

        if self.trello_card_id:
            parts.append(f"[trello-{self.trello_card_id[:8]}]")

        if self.current_pr_number:
            parts.append(f"[pr-{self.current_pr_number}]")

        if self.supersedes_pr:
            parts.append(f"[supersedes-pr-{self.supersedes_pr}]")

        if len(self.iterations) > 1:
            parts.append(f"[cycle-{self.current_iteration}]")

        return " ".join(parts) + " " if parts else ""

    def get_trello_reference(self) -> str:
        """Get Trello card reference for PR descriptions."""
        if not self.trello_card_id:
            return ""

        trello_url = f"https://trello.com/c/{self.trello_card_id}"
        return f"**Trello Task**: [{self.trello_card_id}]({trello_url})\n"

    def get_pr_description_metadata(self) -> str:
        """Get metadata section for PR descriptions."""
        lines = []

        if self.trello_card_id:
            lines.append(f"- **Trello Card**: {self.trello_card_id}")

        if self.current_pr_number:
            lines.append(f"- **PR**: #{self.current_pr_number}")

        if self.supersedes_pr:
            lines.append(f"- **Supersedes PR**: #{self.supersedes_pr}")

        if self.current_iteration > 1:
            lines.append(f"- **Iteration**: {self.current_iteration}")

        if not lines:
            return ""

        return "\n### Metadata\n" + "\n".join(lines) + "\n"

    @property
    def is_fix_task(self) -> bool:
        """Check if this is a fix task (for compatibility with id_tracking)."""
        # Check if any iteration was a fix/retry
        return len([i for i in self.iterations if i.status in ["needs_revision", "failed"]]) > 0

    @property
    def fix_for_pr(self) -> Optional[int]:
        """Get the PR this task is fixing (for compatibility)."""
        return self.current_pr_number if self.is_fix_task else None

    @property
    def review_cycle(self) -> int:
        """Get the review cycle number (for compatibility)."""
        return self.current_iteration

    @property
    def branch_name(self) -> Optional[str]:
        """Alias for current_branch (for compatibility with id_tracking)."""
        return self.current_branch

    @branch_name.setter
    def branch_name(self, value: Optional[str]):
        """Set current_branch via branch_name property (for compatibility)."""
        self.current_branch = value

    @property
    def pr_number(self) -> Optional[int]:
        """Alias for current_pr_number (for compatibility with id_tracking)."""
        return self.current_pr_number

    @pr_number.setter
    def pr_number(self, value: Optional[int]):
        """Set current_pr_number via pr_number property (for compatibility)."""
        self.current_pr_number = value


class TaskContextManager:
    """
    Manages task context persistence and retrieval.

    Saves checkpoints to:
    - Local filesystem (/tmp/task_checkpoints/)
    - Trello card comments (for sync across machines)

    === FIX ISSUE #4: File locking for concurrent access ===
    """

    def __init__(self, checkpoint_dir: str = "/tmp/task_checkpoints"):
        # === FIX ISSUE #6: Validate checkpoint directory ===
        self.checkpoint_dir = Path(checkpoint_dir)

        # Validate directory can be created
        try:
            self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
            # Test write permissions
            test_file = self.checkpoint_dir / ".write_test"
            test_file.touch()
            test_file.unlink()
        except Exception as e:
            raise ValueError(f"Cannot access checkpoint directory {checkpoint_dir}: {e}")

        self._lock_file = None

    def _get_lock_file_path(self, trello_card_id: str) -> Path:
        """Get the lock file path for a given card ID."""
        return self.checkpoint_dir / f"{trello_card_id}.lock"

    def _acquire_lock(self, trello_card_id: str, timeout: float = 30.0) -> bool:
        """
        Acquire file lock for checkpoint access.

        Args:
            trello_card_id: Trello card ID
            timeout: Maximum time to wait for lock (seconds)

        Returns:
            True if lock acquired, False otherwise
        """
        import fcntl
        import time

        lock_path = self._get_lock_file_path(trello_card_id)

        try:
            # Create/open lock file
            self._lock_file = open(lock_path, 'w')

            # Try to acquire exclusive lock (non-blocking first)
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    # Lock acquired successfully
                    self._lock_file.write(f"{os.getpid()}\n")
                    self._lock_file.flush()
                    return True
                except IOError:
                    # Lock is held by another process
                    time.sleep(0.1)

            # Timeout waiting for lock
            self._lock_file.close()
            self._lock_file = None
            return False

        except Exception as e:
            print(f"Warning: Failed to acquire lock: {e}")
            if self._lock_file:
                self._lock_file.close()
                self._lock_file = None
            return False

    def _release_lock(self, trello_card_id: str):
        """Release file lock."""
        if self._lock_file:
            try:
                import fcntl
                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
                self._lock_file.close()
                self._lock_file = None

                # Clean up lock file
                lock_path = self._get_lock_file_path(trello_card_id)
                if lock_path.exists():
                    lock_path.unlink()
            except Exception as e:
                print(f"Warning: Failed to release lock: {e}")

    def save_checkpoint(self, context: TaskContext) -> str:
        """
        Save task context to checkpoint file with file locking and atomic write.

        Args:
            context: Task context to save

        Returns:
            Path to saved checkpoint file
        """
        # Acquire lock
        if not self._acquire_lock(context.trello_card_id):
            raise Exception(f"Failed to acquire lock for checkpoint: {context.trello_card_id}")

        try:
            checkpoint_file = self.checkpoint_dir / f"{context.trello_card_id}.json"

            # Atomic write: write to temp file, then rename
            temp_file = self.checkpoint_dir / f"{context.trello_card_id}.json.tmp"

            with open(temp_file, 'w') as f:
                json.dump(context.to_dict(), f, indent=2, default=str)
                f.flush()
                os.fsync(f.fileno())

            # Atomic rename
            temp_file.replace(checkpoint_file)

            return str(checkpoint_file)

        finally:
            # Always release lock
            self._release_lock(context.trello_card_id)

    def load_checkpoint(self, trello_card_id: str) -> Optional[TaskContext]:
        """
        Load task context from checkpoint file with file locking.

        Args:
            trello_card_id: Trello card ID

        Returns:
            TaskContext if found, None otherwise
        """
        checkpoint_file = self.checkpoint_dir / f"{trello_card_id}.json"

        if not checkpoint_file.exists():
            return None

        # Acquire lock
        if not self._acquire_lock(trello_card_id):
            print(f"Warning: Could not acquire lock to load checkpoint: {trello_card_id}")
            # Try to load anyway (may be partially read)

        try:
            with open(checkpoint_file, 'r') as f:
                data = json.load(f)

            return TaskContext.from_dict(data)
        except Exception as e:
            print(f"Warning: Failed to load checkpoint: {e}")
            return None
        finally:
            # Always release lock
            self._release_lock(trello_card_id)

    def delete_checkpoint(self, trello_card_id: str):
        """Delete checkpoint file with locking."""
        # Acquire lock
        if not self._acquire_lock(trello_card_id):
            print(f"Warning: Could not acquire lock to delete checkpoint: {trello_card_id}")
            # Try anyway

        try:
            checkpoint_file = self.checkpoint_dir / f"{trello_card_id}.json"
            if checkpoint_file.exists():
                checkpoint_file.unlink()
        finally:
            # Always release lock
            self._release_lock(trello_card_id)

    def list_all_checkpoints(self) -> List[str]:
        """List all checkpoint IDs."""
        return [
            f.stem for f in self.checkpoint_dir.glob("*.json")
            if f.is_file()
        ]

    async def sync_to_trello(
        self,
        context: TaskContext,
        trello_client,  # Would import actual TrelloClient
    ):
        """
        Sync task history to Trello card as comment.

        Args:
            context: Task context to sync
            trello_client: Trello client for posting comments
        """
        history_summary = context.get_history_summary()

        comment = f"""🤖 **TASK CHECKPOINT**

{history_summary}

---
*Last updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}*
"""

        try:
            await trello_client.add_card_comment(
                card_id=context.trello_card_id,
                comment=comment
            )
        except Exception as e:
            print(f"Warning: Failed to sync to Trello: {e}")


# Global instance
_context_manager: Optional[TaskContextManager] = None


def get_task_context_manager() -> TaskContextManager:
    """Get global task context manager instance."""
    global _context_manager
    if _context_manager is None:
        _context_manager = TaskContextManager()
    return _context_manager


async def load_or_create_task_context(
    trello_card_id: str,
    original_task: str,
    project_name: str,
    repo_owner: Optional[str] = None,
    repo_name: Optional[str] = None,
) -> TaskContext:
    """
    Load existing context or create new one.

    Args:
        trello_card_id: Trello card ID
        original_task: Task description
        project_name: Project/workspace path
        repo_owner: GitHub repo owner
        repo_name: GitHub repo name

    Returns:
        TaskContext (loaded or new)
    """
    manager = get_task_context_manager()

    # Try to load existing
    context = manager.load_checkpoint(trello_card_id)

    if context:
        print(f"✅ Resumed from checkpoint: {trello_card_id[:8]}")
        print(f"   Previous iterations: {context.current_iteration}")
        return context

    # Create new context
    context = TaskContext(
        task_id=f"task_{trello_card_id[:8]}",
        trello_card_id=trello_card_id,
        original_task=original_task,
        project_name=project_name,
        repo_owner=repo_owner,
        repo_name=repo_name,
    )

    print(f"✨ Created new task context: {trello_card_id[:8]}")
    return context
