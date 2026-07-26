"""
Worker Configuration

Configuration settings specific to the worker daemon.
"""

from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from config.settings import get_settings


class WorkerConfig(BaseSettings):
    """Worker daemon configuration."""

    model_config = SettingsConfigDict(
        env_file="/home/ubuntu/.env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Worker behavior
    check_interval: int = Field(default=60, description="Check interval in seconds")
    max_concurrent_tasks: int = Field(default=1, description="Max concurrent tasks")
    auto_merge: bool = Field(default=True, description="Auto-merge PRs after approval")
    delete_branch_after_merge: bool = Field(
        default=True, description="Delete branch after merge"
    )

    # Branch cleanup configuration
    enable_branch_cleanup: bool = Field(
        default=True, description="Enable automatic branch cleanup"
    )
    branch_cleanup_days_old: int = Field(
        default=7, description="Clean up branches older than this many days"
    )
    branch_cleanup_protected_branches: list = Field(
        default=["main", "master", "develop", "staging"],
        description="Branches to never delete"
    )
    branch_cleanup_interval_hours: int = Field(
        default=24, description="Run branch cleanup at most this often (in hours)"
    )

    # Project management
    projects_base_path: Path = Field(
        default=Path("/home/ubuntu/projects"), description="Base path for project repositories"
    )

    # Task source priorities (higher = more preferred)
    task_source_priority: dict = Field(
        default={"trello": 100, "telegram": 50, "database": 10},
        description="Priority for task sources",
    )

    # Rate limiting
    rate_limit_check_enabled: bool = Field(default=True, description="Enable rate limit checking")
    rate_limit_retry_after: int = Field(
        default=60, description="Default retry after seconds when rate limited"
    )
    rate_limit_max_retries: int = Field(default=10, description="Max retries when rate limited")
    rate_limit_backoff_multiplier: float = Field(
        default=2.0, description="Exponential backoff multiplier"
    )

    # Task processing
    task_timeout: int = Field(default=3600, description="Task timeout in seconds")
    task_max_retries: int = Field(default=3, description="Max retries per task")
    task_retry_delay: int = Field(default=300, description="Retry delay in seconds")

    # Priority levels
    priority_levels: List[str] = Field(
        default=["P0", "P1", "P2", "P3"], description="Priority levels"
    )
    priority_weights: dict = Field(
        default={"P0": 1000, "P1": 100, "P2": 10, "P3": 1},
        description="Priority weights for sorting",
    )

    # Trello configuration
    trello_api_key: str = Field(default="", description="Trello API key")
    trello_api_secret: str = Field(default="", description="Trello API secret")
    trello_token: str = Field(default="", description="Trello token")
    trello_board_id: str = Field(default="", description="Trello board ID")
    trello_list_todo: str = Field(default="", description="Trello To Do list ID")
    trello_list_in_progress: str = Field(default="", description="Trello In Progress list ID")
    trello_list_review: str = Field(default="", description="Trello Review list ID")
    trello_list_done: str = Field(default="", description="Trello Done list ID")

    # Telegram configuration
    telegram_bot_token: str = Field(default="", description="Telegram bot token")
    telegram_chat_id: str = Field(default="", description="Telegram chat ID")
    telegram_group_id: str = Field(default="", description="Telegram group ID (optional)")

    # GitHub configuration
    github_token: str = Field(default="", description="GitHub personal access token")
    github_username: str = Field(default="", description="GitHub username")

    # Logging
    log_path: Path = Field(
        default=Path("/home/ubuntu/data/logs"), description="Log path"
    )

    @field_validator("projects_base_path")
    @classmethod
    def ensure_projects_path_exists(cls, v: Path) -> Path:
        """Ensure projects directory exists."""
        v.mkdir(parents=True, exist_ok=True)
        return v

    @field_validator("log_path")
    @classmethod
    def ensure_log_path_exists(cls, v: Path) -> Path:
        """Ensure log directory exists."""
        v.mkdir(parents=True, exist_ok=True)
        return v

    def get_priority_weight(self, priority: str) -> int:
        """Get weight for priority level."""
        return self.priority_weights.get(priority.upper(), 1)

    def is_trello_configured(self) -> bool:
        """Check if Trello is properly configured."""
        return all(
            [
                self.trello_api_key,
                self.trello_token,
                self.trello_board_id,
                self.trello_list_todo,
                self.trello_list_in_progress,
                self.trello_list_review,
                self.trello_list_done,
            ]
        )

    def is_telegram_configured(self) -> bool:
        """Check if Telegram is properly configured."""
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    def is_github_configured(self) -> bool:
        """Check if GitHub is properly configured."""
        return bool(self.github_token and self.github_username)


# Global worker config instance
_worker_config: WorkerConfig | None = None


def get_worker_config() -> WorkerConfig:
    """Get the global worker configuration instance."""
    global _worker_config
    if _worker_config is None:
        _worker_config = WorkerConfig()
    return _worker_config
