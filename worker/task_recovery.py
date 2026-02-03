"""
Task Recovery and Checkpoint System

Allows tasks to be resumed if they crash or are interrupted.
Provides checkpoint/save-state functionality for long-running tasks.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from utils.logger import get_logger

logger = get_logger("task_recovery")


class TaskRecovery:
    """
    Task recovery system with checkpointing.

    Allows tasks to:
    - Save state at checkpoints
    - Resume from last checkpoint on failure
    - Track progress across restarts
    """

    def __init__(self, checkpoint_dir: str = "/tmp/task_checkpoints"):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.logger = get_logger("task_recovery")

    def get_checkpoint_path(self, task_id: str) -> Path:
        """Get the checkpoint file path for a task."""
        return self.checkpoint_dir / f"{task_id}.json"

    def save_checkpoint(
        self,
        task_id: str,
        state: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Save a checkpoint for a task.

        Args:
            task_id: Unique task identifier
            state: Current state to save
            metadata: Optional metadata (progress, step info, etc.)

        Returns:
            True if checkpoint saved successfully
        """
        try:
            checkpoint_path = self.get_checkpoint_path(task_id)

            checkpoint_data = {
                "task_id": task_id,
                "timestamp": datetime.utcnow().isoformat(),
                "state": state,
                "metadata": metadata or {},
            }

            with open(checkpoint_path, "w") as f:
                json.dump(checkpoint_data, f, indent=2)

            self.logger.info(
                "Checkpoint saved",
                task_id=task_id[:8],
                checkpoint=str(checkpoint_path),
            )

            return True

        except Exception as e:
            self.logger.error("Failed to save checkpoint", task_id=task_id, error=str(e))
            return False

    def load_checkpoint(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Load a checkpoint for a task.

        Args:
            task_id: Unique task identifier

        Returns:
            Checkpoint data or None if not found/invalid
        """
        try:
            checkpoint_path = self.get_checkpoint_path(task_id)

            if not checkpoint_path.exists():
                self.logger.debug("No checkpoint found", task_id=task_id[:8])
                return None

            with open(checkpoint_path, "r") as f:
                checkpoint_data = json.load(f)

            # Validate checkpoint data is complete
            if not self._validate_checkpoint_data(checkpoint_data):
                self.logger.warning(
                    "Invalid checkpoint data - will be ignored",
                    task_id=task_id[:8],
                )
                # Delete the invalid checkpoint
                checkpoint_path.unlink()
                return None

            self.logger.info(
                "Checkpoint loaded",
                task_id=task_id[:8],
                timestamp=checkpoint_data.get("timestamp"),
            )

            return checkpoint_data

        except json.JSONDecodeError as e:
            self.logger.error("Checkpoint file corrupted - will be deleted", task_id=task_id, error=str(e))
            # Delete corrupted checkpoint
            try:
                checkpoint_path.unlink()
            except Exception:
                pass
            return None
        except Exception as e:
            self.logger.error("Failed to load checkpoint", task_id=task_id, error=str(e))
            return None

    def _validate_checkpoint_data(self, data: Dict[str, Any]) -> bool:
        """
        Validate checkpoint data is complete and valid.

        Args:
            data: Checkpoint data to validate

        Returns:
            True if valid, False otherwise
        """
        # Check required fields exist
        required_fields = ["task_id", "timestamp", "state"]
        for field in required_fields:
            if field not in data:
                return False

        # Validate timestamp is a valid ISO format string
        try:
            datetime.fromisoformat(data["timestamp"])
        except (ValueError, TypeError):
            return False

        # Validate state is a dict
        if not isinstance(data.get("state"), dict):
            return False

        # Validate metadata is a dict (if present)
        metadata = data.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            return False

        return True

    def delete_checkpoint(self, task_id: str) -> bool:
        """
        Delete a checkpoint for a task.

        Args:
            task_id: Unique task identifier

        Returns:
            True if deleted successfully
        """
        try:
            checkpoint_path = self.get_checkpoint_path(task_id)

            if checkpoint_path.exists():
                checkpoint_path.unlink()
                self.logger.info("Checkpoint deleted", task_id=task_id[:8])

            return True

        except Exception as e:
            self.logger.error("Failed to delete checkpoint", task_id=task_id, error=str(e))
            return False

    def has_checkpoint(self, task_id: str) -> bool:
        """Check if a checkpoint exists for a task."""
        return self.get_checkpoint_path(task_id).exists()

    def list_checkpoints(self) -> list:
        """List all checkpoints."""
        try:
            checkpoints = []
            for checkpoint_file in self.checkpoint_dir.glob("*.json"):
                try:
                    with open(checkpoint_file, "r") as f:
                        data = json.load(f)
                        checkpoints.append({
                            "task_id": data.get("task_id"),
                            "timestamp": data.get("timestamp"),
                            "metadata": data.get("metadata", {}),
                            "file": str(checkpoint_file),
                        })
                except Exception:
                    pass

            return sorted(checkpoints, key=lambda x: x.get("timestamp", ""), reverse=True)

        except Exception as e:
            self.logger.error("Failed to list checkpoints", error=str(e))
            return []

    def cleanup_old_checkpoints(self, hours_old: int = 24) -> int:
        """
        Clean up checkpoints older than specified hours.

        Args:
            hours_old: Delete checkpoints older than this

        Returns:
            Number of checkpoints cleaned up
        """
        try:
            cutoff_time = time.time() - (hours_old * 3600)
            cleaned = 0

            for checkpoint_file in self.checkpoint_dir.glob("*.json"):
                if checkpoint_file.stat().st_mtime < cutoff_time:
                    checkpoint_file.unlink()
                    cleaned += 1

            if cleaned > 0:
                self.logger.info("Cleaned up old checkpoints", count=cleaned)

            return cleaned

        except Exception as e:
            self.logger.error("Failed to cleanup checkpoints", error=str(e))
            return 0


class CheckpointContext:
    """
    Context manager for automatic checkpointing.

    Usage:
        async with CheckpointContext(task_id, recovery) as ctx:
            # Do work
            ctx.update_state({"progress": 50})
            # More work
            ctx.update_state({"progress": 100})
    """

    def __init__(
        self,
        task_id: str,
        recovery: TaskRecovery,
        initial_state: Optional[Dict[str, Any]] = None,
    ):
        self.task_id = task_id
        self.recovery = recovery
        self.state = initial_state or {}
        self.metadata = {}
        self.auto_save = True

    async def __aenter__(self):
        # Load existing checkpoint if available
        existing = self.recovery.load_checkpoint(self.task_id)
        if existing:
            self.state = existing.get("state", {})
            self.metadata = existing.get("metadata", {})
            logger.info("Resumed from checkpoint", task_id=self.task_id[:8])

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            # Task completed successfully, delete checkpoint
            self.recovery.delete_checkpoint(self.task_id)
        else:
            # Task failed, save final state
            if self.auto_save:
                self.recovery.save_checkpoint(
                    self.task_id,
                    self.state,
                    {**self.metadata, "failed": True, "error": str(exc_val)},
                )
        return False

    def update_state(self, state_update: Dict[str, Any]):
        """Update the current state."""
        self.state.update(state_update)
        if self.auto_save:
            self.recovery.save_checkpoint(self.task_id, self.state, self.metadata)

    def set_metadata(self, key: str, value: Any):
        """Set metadata for the checkpoint."""
        self.metadata[key] = value
        if self.auto_save:
            self.recovery.save_checkpoint(self.task_id, self.state, self.metadata)


# Global instance
_task_recovery: Optional[TaskRecovery] = None


def get_task_recovery() -> TaskRecovery:
    """Get the global task recovery instance."""
    global _task_recovery
    if _task_recovery is None:
        _task_recovery = TaskRecovery()
    return _task_recovery
