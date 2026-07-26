"""
Database Models for Worker

PostgreSQL models for task storage (fallback when Trello/Telegram unavailable).
"""

import asyncio
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

import asyncpg
from pydantic import BaseModel, Field

from config.settings import get_settings
from utils.logger import get_logger


class TaskStatus(str, Enum):
    """Task status values."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    """Task priority levels."""
    P0 = "P0"  # Critical
    P1 = "P1"  # High
    P2 = "P2"  # Medium
    P3 = "P3"  # Low


class TaskSource(str, Enum):
    """Task source."""
    TRELLO = "trello"
    TELEGRAM = "telegram"
    DATABASE = "database"
    API = "api"


class Task(BaseModel):
    """Task model."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    description: str = ""
    project_name: str = ""
    priority: TaskPriority = TaskPriority.P3
    status: TaskStatus = TaskStatus.PENDING
    source: TaskSource = TaskSource.DATABASE
    source_id: str = ""  # ID from source (Trello card ID, Telegram message ID, etc.)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    error_message: str = ""
    metadata: dict = Field(default_factory=dict)

    class Config:
        use_enum_values = True


class TaskDB:
    """
    Task database operations using PostgreSQL.

    Provides async CRUD operations for task management.
    """

    def __init__(self):
        self.logger = get_logger("task_db")
        self.settings = get_settings()
        self._pool: Optional[asyncpg.Pool] = None

    async def initialize(self):
        """Initialize database connection and create tables."""
        try:
            self._pool = await asyncpg.create_pool(
                host=self.settings.postgres_host,
                port=self.settings.postgres_port,
                user=self.settings.postgres_user,
                password=self.settings.postgres_password,
                database=self.settings.postgres_db,
                min_size=2,
                max_size=10,
            )

            # Create tasks table
            await self._create_tables()
            self.logger.info("Task database initialized")

        except Exception as e:
            self.logger.error("Failed to initialize task database", error=str(e))
            self._pool = None

    async def _create_tables(self):
        """Create database tables."""
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id UUID PRIMARY KEY,
                    title VARCHAR(500) NOT NULL,
                    description TEXT,
                    project_name VARCHAR(100),
                    priority VARCHAR(10) NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    source VARCHAR(20) NOT NULL,
                    source_id VARCHAR(200),
                    created_at TIMESTAMP NOT NULL,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    retry_count INTEGER DEFAULT 0,
                    error_message TEXT,
                    metadata JSONB DEFAULT '{}'::jsonb
                )
            """)

            # Create indexes for common queries
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_status_priority
                ON tasks (status, priority DESC)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_created_at
                ON tasks (created_at DESC)
            """)

    async def create_task(self, task: Task) -> Task:
        """Create a new task."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO tasks (
                    id, title, description, project_name, priority, status,
                    source, source_id, created_at, started_at, completed_at,
                    retry_count, error_message, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                """,
                task.id,
                task.title,
                task.description,
                task.project_name,
                task.priority.value,
                task.status.value,
                task.source.value,
                task.source_id,
                task.created_at,
                task.started_at,
                task.completed_at,
                task.retry_count,
                task.error_message,
                task.metadata,
            )
        return task

    async def get_next_task(self, exclude_source: str | None = None) -> Optional[Task]:
        """
        Get the next pending task ordered by priority.

        Args:
            exclude_source: Optional source to exclude (e.g., "trello" if Trello is primary)

        Returns:
            Next task or None if no pending tasks
        """
        async with self._pool.acquire() as conn:
            query = """
                SELECT * FROM tasks
                WHERE status = $1
            """
            params = [TaskStatus.PENDING.value]

            if exclude_source:
                query += " AND source != $2"
                params.append(exclude_source)

            query += " ORDER BY priority ASC, created_at ASC LIMIT 1"

            row = await conn.fetchrow(query, *params)

            if row:
                # Handle metadata - convert from string if needed
                metadata = row.get("metadata", {})
                if isinstance(metadata, str):
                    import json
                    metadata = json.loads(metadata) if metadata else {}

                return Task(
                    id=str(row["id"]),
                    title=row["title"],
                    description=row["description"] or "",
                    project_name=row["project_name"] or "",
                    priority=TaskPriority(row["priority"]),
                    status=TaskStatus(row["status"]),
                    source=TaskSource(row["source"]),
                    source_id=row["source_id"] or "",
                    created_at=row["created_at"],
                    started_at=row["started_at"],
                    completed_at=row["completed_at"],
                    retry_count=row["retry_count"],
                    error_message=row["error_message"] or "",
                    metadata=metadata,
                )
            return None

    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        error_message: str = "",
    ) -> bool:
        """Update task status."""
        async with self._pool.acquire() as conn:
            query = "UPDATE tasks SET status = $1"
            params = [status.value]

            if status == TaskStatus.IN_PROGRESS:
                query += ", started_at = $2"
                params.append(datetime.utcnow())
            elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                query += ", completed_at = $2"
                params.append(datetime.utcnow())

            if error_message:
                query += ", error_message = $" + str(len(params) + 1)
                params.append(error_message)

            query += " WHERE id = $" + str(len(params) + 1)
            params.append(task_id)

            result = await conn.execute(query, *params)
            return "UPDATE 1" in result

    async def increment_retry(self, task_id: str) -> int:
        """Increment task retry count."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE tasks SET retry_count = retry_count + 1 WHERE id = $1",
                task_id,
            )
            row = await conn.fetchrow(
                "SELECT retry_count FROM tasks WHERE id = $1",
                task_id,
            )
            return row["retry_count"] if row else 0

    async def get_all_pending_tasks(self) -> list[Task]:
        """Get all pending tasks."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM tasks WHERE status = $1 ORDER BY priority ASC, created_at ASC",
                TaskStatus.PENDING.value,
            )

            return [
                Task(
                    id=str(row["id"]),
                    title=row["title"],
                    description=row["description"] or "",
                    project_name=row["project_name"] or "",
                    priority=TaskPriority(row["priority"]),
                    status=TaskStatus(row["status"]),
                    source=TaskSource(row["source"]),
                    source_id=row["source_id"] or "",
                    created_at=row["created_at"],
                    started_at=row["started_at"],
                    completed_at=row["completed_at"],
                    retry_count=row["retry_count"],
                    error_message=row["error_message"] or "",
                    metadata=row.get("metadata", {}),
                )
                for row in rows
            ]

    async def get_task_by_id(self, task_id: str) -> Optional[Task]:
        """Get a task by its ID."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM tasks WHERE id = $1",
                task_id,
            )

            if row:
                metadata = row.get("metadata", {})
                if isinstance(metadata, str):
                    import json
                    metadata = json.loads(metadata) if metadata else {}

                return Task(
                    id=str(row["id"]),
                    title=row["title"],
                    description=row["description"] or "",
                    project_name=row["project_name"] or "",
                    priority=TaskPriority(row["priority"]),
                    status=TaskStatus(row["status"]),
                    source=TaskSource(row["source"]),
                    source_id=row["source_id"] or "",
                    created_at=row["created_at"],
                    started_at=row["started_at"],
                    completed_at=row["completed_at"],
                    retry_count=row["retry_count"],
                    error_message=row["error_message"] or "",
                    metadata=metadata,
                )
            return None

    async def close(self):
        """Close database connection."""
        if self._pool:
            await self._pool.close()


# Global task DB instance
_task_db: TaskDB | None = None


def get_task_db() -> TaskDB:
    """Get the global task database instance."""
    global _task_db
    if _task_db is None:
        _task_db = TaskDB()
    return _task_db
