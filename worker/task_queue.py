"""
Task Queue Manager - Priority-based Task Queue (TRELLO ONLY)

Manages task queue from Trello only.
All metadata (PR URLs, status, etc.) stored in Trello card comments.
No database dependency.
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import uuid4

from redis.asyncio import Redis

from config.settings import get_settings
from utils.logger import get_logger
from worker.worker_config import get_worker_config
from worker.db_models import Task, TaskPriority, TaskSource
from worker.trello.client import get_trello_client
from worker.telegram.bot import get_telegram_bot


def _get_enum_value(enum_or_str):
    """Get value from enum or string."""
    if isinstance(enum_or_str, str):
        return enum_or_str
    return enum_or_str.value


def _dict_to_task(task_dict: dict) -> Task:
    """Convert dict to Task, handling enums and datetimes."""
    # Convert string enums back to enum objects
    if isinstance(task_dict.get('priority'), str):
        task_dict['priority'] = TaskPriority(task_dict['priority'])
    if isinstance(task_dict.get('status'), str):
        from worker.db_models import TaskStatus
        task_dict['status'] = TaskStatus(task_dict['status'])
    if isinstance(task_dict.get('source'), str):
        task_dict['source'] = TaskSource(task_dict['source'])

    # Convert ISO strings back to datetime
    for key in ['created_at', 'started_at', 'completed_at']:
        if task_dict.get(key):
            if isinstance(task_dict[key], str):
                # Parse ISO format
                task_dict[key] = datetime.fromisoformat(task_dict[key])

    return Task(**task_dict)


@dataclass(order=True)
class QueuedTask:
    """Task in queue with priority weight."""
    priority_weight: int
    created_at: datetime
    task: Task = field(compare=False)


class TaskQueueManager:
    """
    Manages the task queue from Trello only.

    Trello is the SINGLE source of truth.
    - Task status = card's list position (TODO, In Progress, Review, Done)
    - Metadata (PR URLs, errors) = stored in card comments
    - No database required
    """

    def __init__(self):
        self.logger = get_logger("task_queue")
        self.settings = get_settings()
        self.worker_config = get_worker_config()
        self._redis: Optional[Redis] = None
        self._trello_client = get_trello_client()
        self._telegram_bot = get_telegram_bot()

        # Redis keys (for in-memory queue only)
        self._queue_key = "worker:task_queue"
        self._processing_key = "worker:processing"
        self._completed_key = "worker:completed"

        # Comment prefix for metadata
        self._metadata_prefix = "🤖 AI_WORKER:"

    async def initialize(self):
        """Initialize Redis connection (no database)."""
        try:
            self._redis = Redis(
                host=self.settings.redis_host,
                port=self.settings.redis_port,
                db=0,
                decode_responses=True,
            )
            await self._redis.ping()
            self.logger.info("Task queue manager initialized (Trello-only mode)")
        except Exception as e:
            self.logger.error("Failed to connect to Redis", error=str(e))
            self._redis = None

    def _parse_metadata_from_comment(self, comment_text: str) -> dict:
        """
        Parse metadata from Trello card comment.

        Expected format: 🤖 AI_WORKER: {"pr_url": "...", "status": "..."}
        """
        try:
            if comment_text.startswith(self._metadata_prefix):
                json_str = comment_text[len(self._metadata_prefix):].strip()
                return json.loads(json_str)
        except Exception as e:
            self.logger.debug("Could not parse metadata from comment", error=str(e))
        return {}

    def _format_metadata_comment(self, metadata: dict) -> str:
        """Format metadata as Trello card comment."""
        return f"{self._metadata_prefix} {json.dumps(metadata)}"

    async def _get_task_metadata(self, card_id: str) -> dict:
        """
        Get metadata from Trello card comments.

        Args:
            card_id: Trello card ID

        Returns:
            Metadata dict with pr_url, status, etc.
        """
        try:
            # Import here to avoid circular import
            import httpx

            # Get card comments
            url = f"https://api.trello.com/1/cards/{card_id}/actions"
            params = {
                "key": self._trello_client.config.trello_api_key,
                "token": self._trello_client.config.trello_token,
                "filter": "commentCard",
            }

            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=10.0)
                if response.status_code == 200:
                    actions = response.json()
                    # Find our metadata comment (most recent first)
                    for action in reversed(actions):
                        comment_text = action.get("data", {}).get("text", "")
                        if comment_text.startswith(self._metadata_prefix):
                            return self._parse_metadata_from_comment(comment_text)
        except Exception as e:
            self.logger.debug("Could not get task metadata from Trello", error=str(e))

        return {}

    async def _update_task_metadata(self, card_id: str, metadata: dict):
        """
        Update metadata on Trello card (adds new comment).

        Args:
            card_id: Trello card ID
            metadata: Metadata dict to store
        """
        try:
            comment_text = self._format_metadata_comment(metadata)
            await self._trello_client.add_card_comment(card_id, comment_text)
            self.logger.debug("Updated task metadata on Trello", card_id=card_id[:8])
        except Exception as e:
            self.logger.warning("Could not update task metadata", error=str(e))

    async def refresh_tasks(self):
        """
        Refresh task queue from Trello.

        Workflow:
        1. Check "In Progress" list first
        2. If nothing in "In Progress", move highest-priority TODO to In Progress
        """
        try:
            # 1. First check In Progress list
            if self._trello_client.is_configured():
                in_progress_tasks = await self._trello_client.get_in_progress_cards()
                if in_progress_tasks:
                    for task in in_progress_tasks:
                        await self._add_to_queue(task)
                    self.logger.info(
                        "Found tasks in In Progress",
                        count=len(in_progress_tasks)
                    )
                else:
                    # 2. Nothing in In Progress, move highest priority TODO to In Progress
                    self.logger.info("No tasks in In Progress, moving TODO task to In Progress")
                    await self._move_highest_priority_todo_to_in_progress()

                # Also fetch remaining TODO cards
                todo_tasks = await self._trello_client.get_todo_cards()
                for task in todo_tasks:
                    await self._add_to_queue(task)

            # Log queue status
            queue_size = await self._get_queue_size()
            self.logger.info("Task queue refreshed", size=queue_size)

        except Exception as e:
            self.logger.error("Failed to refresh tasks", error=str(e))

    async def _move_highest_priority_todo_to_in_progress(self):
        """Move the highest priority TODO task to In Progress list."""
        try:
            # Get all TODO cards sorted by priority
            todo_tasks = await self._trello_client.get_todo_cards()
            if not todo_tasks:
                self.logger.debug("No TODO tasks to move")
                return

            # Sort by priority (P0 > P1 > P2 > P3)
            priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
            todo_tasks.sort(key=lambda t: priority_order.get(_get_enum_value(t.priority), 999))

            # Get highest priority task
            highest_priority_task = todo_tasks[0]

            # Move it to In Progress
            success = await self._trello_client.move_to_in_progress(highest_priority_task.source_id)

            if success:
                self.logger.info(
                    "Moved TODO task to In Progress",
                    task_id=highest_priority_task.id[:8],
                    title=highest_priority_task.title[:40],
                    priority=_get_enum_value(highest_priority_task.priority)
                )
            else:
                self.logger.warning(
                    "Failed to move task to In Progress",
                    task_id=highest_priority_task.id[:8]
                )

        except Exception as e:
            self.logger.error("Failed to move TODO task to In Progress", error=str(e))

    async def get_next_task(self) -> Optional[Task]:
        """
        Get the next task to process.

        Returns:
            Next task or None if queue is empty
        """
        try:
            # Check if Redis is available
            if not self._redis:
                self.logger.warning("Redis not available, cannot get next task")
                return None

            # Try to get from queue first
            task_data = await self._redis.zpopmin(self._queue_key)

            if task_data:
                task_json, score = task_data[0]
                task_dict = json.loads(task_json)
                # Convert ISO strings back to datetime
                task = _dict_to_task(task_dict)

                # Mark as processing with TTL (2 hours)
                # Use separate key per task to allow individual TTLs
                processing_key = f"{self._processing_key}:{task.id}"
                await self._redis.setex(
                    processing_key,
                    7200,  # 2 hours TTL
                    datetime.utcnow().isoformat(),
                )

                self.logger.info(
                    "Dequeued task",
                    task_id=task.id[:8],
                    title=task.title[:40],
                    priority=_get_enum_value(task.priority),
                )

                # Send telegram notification for task start
                try:
                    await self._telegram_bot.notify_task_started(task)
                except Exception as telegram_error:
                    self.logger.debug(
                        "Could not send telegram notification",
                        task_id=task.id[:8],
                        error=str(telegram_error),
                    )

                return task

            # If queue is empty, refresh and try again
            await self.refresh_tasks()

            task_data = await self._redis.zpopmin(self._queue_key)
            if task_data:
                task_json, score = task_data[0]
                task_dict = json.loads(task_json)
                # Convert ISO strings back to datetime
                task = _dict_to_task(task_dict)

                # Mark as processing with TTL
                processing_key = f"{self._processing_key}:{task.id}"
                await self._redis.setex(
                    processing_key,
                    7200,  # 2 hours TTL
                    datetime.utcnow().isoformat(),
                )

                return task

            return None

        except Exception as e:
            self.logger.error("Failed to get next task", error=str(e))
            return None

    async def mark_task_completed(
        self,
        task_id: str,
        success: bool = True,
        error: str = "",
        pr_url: str = "",
    ):
        """
        Mark task as completed and remove from processing.

        Moves successful Trello tasks to Review list (for human review).
        Stores PR URL in Trello card comment.

        Args:
            task_id: Task ID (internal UUID)
            success: Whether task succeeded
            error: Error message if failed
            pr_url: Pull request URL (if any)
        """
        try:
            # Extract source_id (Trello card ID) from task_id
            # Task objects have source_id field, but we only have task_id here
            # We need to find the task by checking the processing set

            trello_card_id = None
            if self._redis:
                # Get all processing tasks to find our task
                pattern = f"{self._processing_key}:*"
                async for key in self._redis.scan_iter(match=pattern):
                    # This gives us the timestamp, not the task data
                    pass

                # Actually, we need to store source_id when we queue the task
                # For now, we'll need to get task from the queue or find another way
                # Let's use the task's metadata that should have been stored

            # Since we don't have direct access to the task object here,
            # we need task_executor to call us with the source_id
            # For now, let's just remove from processing and rely on task_executor to handle Trello

            # Remove from processing (use individual key)
            if self._redis:
                processing_key = f"{self._processing_key}:{task_id}"
                await self._redis.delete(processing_key)

            # Note: Moving Trello card and adding comment is now handled by task_executor
            # which has access to the full task object including source_id

            # Add to completed set (for history) - only if Redis is available
            if self._redis:
                from worker.db_models import TaskStatus
                status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
                await self._redis.sadd(
                    self._completed_key,
                    f"{task_id}:{status.value}:{datetime.utcnow().isoformat()}",
                )

                # Clean up old completed tasks (keep last 1000)
                completed = await self._redis.smembers(self._completed_key)
                if len(completed) > 1000:
                    # Remove oldest
                    to_remove = sorted(completed)[:len(completed) - 1000]
                    await self._redis.srem(self._completed_key, *to_remove)

            self.logger.info(
                "Task completed",
                task_id=task_id[:8],
                success=success,
            )

        except Exception as e:
            self.logger.error(
                "Failed to mark task completed",
                task_id=task_id[:8],
                error=str(e),
            )

    async def mark_task_in_progress(self, task_id: str):
        """
        Mark a task as in progress (started execution).

        Status is tracked by Trello card position (In Progress list).
        This method is a no-op since Trello movement happens in task_executor.

        Args:
            task_id: Task ID to mark as in progress
        """
        # No-op: Trello card movement handles this
        self.logger.debug("Task in progress (status tracked by Trello)", task_id=task_id[:8])

    async def mark_trello_task_completed(
        self,
        task_id: str,
        source_id: str,
        success: bool = True,
        error: str = "",
        pr_url: str = "",
    ):
        """
        Mark a Trello task as completed.

        This is the NEW method that should be called by task_executor
        since it has access to the full task object.

        Args:
            task_id: Internal task ID
            source_id: Trello card ID
            success: Whether task succeeded
            error: Error message if failed
            pr_url: Pull request URL
        """
        try:
            # Remove from processing
            if self._redis:
                processing_key = f"{self._processing_key}:{task_id}"
                await self._redis.delete(processing_key)

            # If successful, move to Review and store PR URL
            if success:
                # Move to Review in Trello
                moved = await self._trello_client.move_to_review(source_id)
                if moved:
                    self.logger.info(
                        "Moved Trello task to Review",
                        task_id=task_id[:8],
                    )

                    # Store PR URL in Trello card comment
                    if pr_url:
                        await self._update_task_metadata(source_id, {"pr_url": pr_url})

                        # Send telegram notification
                        try:
                            # Create minimal task object for notification
                            from worker.db_models import TaskStatus
                            task = Task(
                                id=task_id,
                                source_id=source_id,
                                title="Task",
                                status=TaskStatus.COMPLETED,
                                metadata={"pr_url": pr_url}
                            )
                            await self._telegram_bot.notify_task_completed(task, pr_url)
                        except Exception as telegram_error:
                            self.logger.debug(
                                "Could not send telegram notification",
                                task_id=task_id[:8],
                                error=str(telegram_error),
                            )
                else:
                    self.logger.warning(
                        "Could not move Trello card to Review",
                        task_id=task_id[:8],
                        source_id=source_id[:8],
                    )
            else:
                # Failed: add error comment
                if error:
                    await self._update_task_metadata(source_id, {
                        "error": error[:500],  # Limit error length
                        "failed_at": datetime.utcnow().isoformat()
                    })

            # Add to completed set
            if self._redis:
                from worker.db_models import TaskStatus
                status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
                await self._redis.sadd(
                    self._completed_key,
                    f"{task_id}:{status.value}:{datetime.utcnow().isoformat()}",
                )

            self.logger.info(
                "Trello task completed",
                task_id=task_id[:8],
                success=success,
            )

        except Exception as e:
            self.logger.error(
                "Failed to mark Trello task completed",
                task_id=task_id[:8],
                error=str(e),
            )

    async def requeue_task(self, task_id: str):
        """
        Requeue a failed task for retry.

        Args:
            task_id: Task ID to requeue
        """
        try:
            # Just remove from processing
            if self._redis:
                processing_key = f"{self._processing_key}:{task_id}"
                await self._redis.delete(processing_key)

            self.logger.info("Task requeued", task_id=task_id[:8])

        except Exception as e:
            self.logger.error(
                "Failed to requeue task",
                task_id=task_id[:8],
                error=str(e),
            )

    async def _add_to_queue(self, task: Task):
        """
        Add task to priority queue.

        Args:
            task: Task to add
        """
        try:
            # Check if Redis is available
            if not self._redis:
                self.logger.warning("Redis not available, cannot add task to queue")
                return

            # Check if already in queue or processing
            if await self._redis.zscore(self._queue_key, task.id):
                return  # Already in queue
            processing_key = f"{self._processing_key}:{task.id}"
            if await self._redis.exists(processing_key):
                return  # Currently processing

            # Calculate priority weight
            # Higher weight = lower priority (Redis sorted set is ascending)
            source_priority = self.worker_config.task_source_priority.get(
                _get_enum_value(task.source),
                0,
            )
            priority_weight = self.worker_config.get_priority_weight(_get_enum_value(task.priority))

            # Combined score: (source_priority * 1000) + priority_weight
            # Lower score = higher priority
            score = (1000 - source_priority) + (1000 - priority_weight)

            # Serialize task with datetime handling
            task_dict = task.dict()
            # Convert datetime fields to ISO format strings
            for key, value in task_dict.items():
                if isinstance(value, datetime):
                    task_dict[key] = value.isoformat()
                elif value is None:
                    task_dict[key] = None

            task_json = json.dumps(task_dict)

            # Add to sorted set
            await self._redis.zadd(self._queue_key, {task_json: score})

        except Exception as e:
            self.logger.error(
                "Failed to add task to queue",
                task_id=task_id[:8] if 'task_id' in locals() else 'unknown',
                error=str(e),
            )

    async def _get_queue_size(self) -> int:
        """Get current queue size."""
        try:
            if not self._redis:
                return 0
            return await self._redis.zcard(self._queue_key)
        except:
            return 0

    async def get_queue_status(self) -> dict:
        """Get current queue status."""
        try:
            queue_size = await self._get_queue_size()
            # Count processing tasks using pattern match
            processing_count = 0
            if self._redis:
                # Use scan to find keys matching the processing pattern
                pattern = f"{self._processing_key}:*"
                async for key in self._redis.scan_iter(match=pattern):
                    processing_count += 1
            completed_count = await self._redis.scard(self._completed_key) if self._redis else 0

            return {
                "queued": queue_size,
                "processing": processing_count,
                "completed": completed_count,
            }

        except Exception as e:
            self.logger.error("Failed to get queue status", error=str(e))
            return {"queued": 0, "processing": 0, "completed": 0}

    async def close(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()


# Global task queue manager instance
_task_queue_manager: Optional[TaskQueueManager] = None


def get_task_queue_manager() -> TaskQueueManager:
    """Get the global task queue manager instance."""
    global _task_queue_manager
    if _task_queue_manager is None:
        _task_queue_manager = TaskQueueManager()
    return _task_queue_manager
