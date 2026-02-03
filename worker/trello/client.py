"""
Trello Integration - Task Management via Trello

Fetches tasks from Trello board and updates card positions based on progress.
"""

import asyncio
import re
from dataclasses import dataclass
from typing import List, Optional

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from utils.logger import get_logger
from worker.worker_config import get_worker_config
from worker.db_models import Task, TaskPriority, TaskSource, TaskStatus


# Retry configuration for Trello API calls
RETRY_CONFIG = {
    "max_attempts": 3,
    "min_wait": 1,  # 1 second
    "max_wait": 10,  # 10 seconds
}


def is_retryable_error(exception: Exception) -> bool:
    """Check if an exception is retryable (transient network errors)."""
    if isinstance(exception, httpx.TimeoutException):
        return True
    if isinstance(exception, httpx.ConnectError):
        return True
    if isinstance(exception, httpx.NetworkError):
        return True
    # Check for HTTP status codes that are retryable
    if isinstance(exception, httpx.HTTPStatusError):
        return exception.response.status_code in [429, 500, 502, 503, 504]
    return False


@dataclass
class TrelloCard:
    """Trello card data."""
    id: str
    name: str
    desc: str
    idList: str
    labels: list[dict]
    url: str
    due: Optional[str] = None


@dataclass
class TrelloList:
    """Trello list data."""
    id: str
    name: str


class TrelloClient:
    """
    Client for interacting with Trello API.

    Provides methods to:
    - Fetch cards from To Do list
    - Move cards between lists
    - Add comments to cards
    - Update card labels
    """

    def __init__(self):
        self.logger = get_logger("trello_client")
        self.config = get_worker_config()
        self._base_url = "https://api.trello.com/1"

        # Build auth params
        self._auth_params = {
            "key": self.config.trello_api_key,
            "token": self.config.trello_token,
        }

    def is_configured(self) -> bool:
        """Check if Trello is properly configured."""
        return self.config.is_trello_configured()

    async def get_in_progress_cards(self) -> list[Task]:
        """
        Fetch cards from In Progress list.

        Returns:
            List of tasks in In Progress
        """
        if not self.is_configured():
            return []

        try:
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self._base_url}/lists/{self.config.trello_list_in_progress}/cards",
                    params=self._auth_params,
                )
                response.raise_for_status()

                cards = response.json()

                tasks = []
                for card in cards:
                    task = self._card_to_task(card)
                    if task:
                        tasks.append(task)

                self.logger.info(
                    "Fetched tasks from Trello",
                    source="in_progress",
                    count=len(tasks),
                )

                return tasks

        except Exception as e:
            self.logger.error("Failed to fetch in-progress cards", error=str(e))
            return []

    async def get_todo_cards(self) -> list[Task]:
        """
        Fetch all cards from the To Do list.

        Returns:
            List of Task objects
        """
        if not self.is_configured():
            self.logger.warning("Trello not configured")
            return []

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Get cards from To Do list
                response = await client.get(
                    f"{self._base_url}/lists/{self.config.trello_list_todo}/cards",
                    params={
                        **self._auth_params,
                        "fields": "name,desc,url,due,labels",
                    },
                )
                response.raise_for_status()

                cards_data = response.json()
                tasks = []

                for card_data in cards_data:
                    task = self._card_to_task(card_data)
                    if task:
                        tasks.append(task)

                self.logger.info(
                    "Fetched tasks from Trello",
                    count=len(tasks),
                )
                return tasks

        except Exception as e:
            self.logger.error("Failed to fetch Trello cards", error=str(e))
            return []

    async def get_review_cards(self) -> list[Task]:
        """
        Fetch cards from Review list.

        Returns:
            List of Task objects from Review list
        """
        if not self.is_configured():
            return []

        try:
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self._base_url}/lists/{self.config.trello_list_review}/cards",
                    params=self._auth_params,
                )
                response.raise_for_status()

                cards_data = response.json()
                tasks = []

                for card_data in cards_data:
                    task = self._card_to_task(card_data)
                    if task:
                        tasks.append(task)

                self.logger.info(
                    "Fetched tasks from Trello",
                    count=len(tasks),
                    source="review",
                )
                return tasks

        except Exception as e:
            self.logger.error("Failed to fetch review cards", error=str(e))
            return []

    def _card_to_task(self, card_data: dict) -> Optional[Task]:
        """Convert Trello card to Task object."""
        try:
            # Parse priority from labels
            priority = TaskPriority.P3  # Default
            for label in card_data.get("labels", []):
                label_name = label.get("name", "").upper()
                if label_name in ("P0", "P1", "P2", "P3"):
                    priority = TaskPriority(label_name)
                    break

            # Parse project name and agent tag from title
            # Format: [project-name] [agent] Task description
            title = card_data["name"]
            project_name = ""
            is_agent_task = False

            # Extract all tags from title (format: [tag])
            tags = re.findall(r"\[([^\]]+)\]", title)
            remaining_title = title

            # Process tags
            for tag in tags:
                if tag.lower() == "agent":
                    is_agent_task = True
                elif not project_name and not tag.lower() in ["agent", "bug", "feature", "hotfix"]:
                    # First non-special tag is the project name
                    project_name = tag

            # Remove all tags from title to get the actual task description
            remaining_title = re.sub(r"\[[^\]]+\]\s*", "", title).strip()

            return Task(
                title=remaining_title,
                description=card_data.get("desc", ""),
                project_name=project_name,
                priority=priority,
                status=TaskStatus.PENDING,
                source=TaskSource.TRELLO,
                source_id=card_data["id"],
                metadata={
                    "trello_url": card_data.get("url", ""),
                    "trello_due": card_data.get("due", ""),
                    "is_agent_task": is_agent_task,
                },
            )

        except Exception as e:
            self.logger.error("Failed to convert card to task", error=str(e))
            return None

    @retry(
        stop=stop_after_attempt(RETRY_CONFIG["max_attempts"]),
        wait=wait_exponential(multiplier=1, min=RETRY_CONFIG["min_wait"], max=RETRY_CONFIG["max_wait"]),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def move_card(
        self,
        card_id: str,
        to_list: str,
        verify: bool = True,
    ) -> bool:
        """
        Move card to a different list.

        Args:
            card_id: Trello card ID
            to_list: Target list ID (progress, review, done)
            verify: Whether to verify the card actually moved (default: True)

        Returns:
            True if successful and verified
        """
        if not self.is_configured():
            return False

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.put(
                f"{self._base_url}/cards/{card_id}",
                params={
                    **self._auth_params,
                    "idList": to_list,
                },
            )
            response.raise_for_status()

            self.logger.info(
                "Moved Trello card",
                card_id=card_id[:8],
                to_list=to_list[:8],
            )

            # Verify the card actually moved if requested
            if verify:
                await asyncio.sleep(0.5)  # Small delay to ensure Trello updates
                verify_response = await client.get(
                    f"{self._base_url}/cards/{card_id}",
                    params=self._auth_params,
                )
                verify_response.raise_for_status()
                card_data = verify_response.json()

                actual_list = card_data.get("idList", "")
                if actual_list != to_list:
                    self.logger.error(
                        "Card move verification failed",
                        card_id=card_id[:8],
                        expected_list=to_list[:8],
                        actual_list=actual_list[:8],
                    )
                    return False

                self.logger.info(
                    "Card move verified",
                    card_id=card_id[:8],
                    in_list=to_list[:8],
                )

            return True

    async def add_card_comment(
        self,
        card_id: str,
        comment: str,
    ) -> bool:
        """
        Add a comment to a card.

        Args:
            card_id: Trello card ID
            comment: Comment text

        Returns:
            True if successful
        """
        if not self.is_configured():
            return False

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._base_url}/cards/{card_id}/actions/comments",
                    params=self._auth_params,
                    data={"text": comment},
                )
                response.raise_for_status()

                return True

        except Exception as e:
            self.logger.error(
                "Failed to add comment",
                card_id=card_id[:8],
                error=str(e),
            )
            return False

    async def update_card_label(
        self,
        card_id: str,
        label_color: str,
    ) -> bool:
        """
        Add a colored label to a card.

        Args:
            card_id: Trello card ID
            label_color: Color name (red, orange, yellow, green, etc.)

        Returns:
            True if successful
        """
        if not self.is_configured():
            return False

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._base_url}/cards/{card_id}/labels",
                    params=self._auth_params,
                    data={"color": label_color},
                )
                response.raise_for_status()

                return True

        except Exception as e:
            self.logger.error(
                "Failed to add label",
                card_id=card_id[:8],
                error=str(e),
            )
            return False

    async def update_card_title(
        self,
        card_id: str,
        new_title: str,
    ) -> bool:
        """
        Update a card's title.

        Args:
            card_id: Trello card ID
            new_title: New card title

        Returns:
            True if successful
        """
        if not self.is_configured():
            return False

        try:
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.put(
                    f"{self._base_url}/cards/{card_id}",
                    params={
                        **self._auth_params,
                        "name": new_title,
                    },
                )
                response.raise_for_status()

                self.logger.info(
                    "Updated card title",
                    card_id=card_id[:8],
                    new_title=new_title,
                )
                return True

        except Exception as e:
            self.logger.error(
                "Failed to update card title",
                card_id=card_id[:8],
                error=str(e),
            )
            return False

    async def get_lists(self) -> dict[str, str]:
        """
        Get all lists on the board.

        Returns:
            Dict mapping list names to IDs
        """
        if not self.is_configured():
            return {}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self._base_url}/boards/{self.config.trello_board_id}/lists",
                    params={
                        **self._auth_params,
                        "fields": "name,id",
                    },
                )
                response.raise_for_status()

                lists_data = response.json()
                return {lst["name"]: lst["id"] for lst in lists_data}

        except Exception as e:
            self.logger.error("Failed to get lists", error=str(e))
            return {}

    async def get_labels(self) -> list[dict]:
        """
        Get all labels on the board.

        Returns:
            List of label dicts with id, name, color
        """
        if not self.is_configured():
            return []

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self._base_url}/boards/{self.config.trello_board_id}/labels",
                    params={
                        **self._auth_params,
                        "fields": "id,name,color",
                    },
                )
                response.raise_for_status()

                return response.json()

        except Exception as e:
            self.logger.error("Failed to get labels", error=str(e))
            return []

    async def create_label(self, name: str, color: str = "sky") -> Optional[dict]:
        """
        Create a new label on the board.

        Args:
            name: Label name
            color: Label color (red, orange, yellow, green, sky, blue, purple, pink, lime, black)

        Returns:
            Label dict if successful, None otherwise
        """
        if not self.is_configured():
            return None

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._base_url}/boards/{self.config.trello_board_id}/labels",
                    params=self._auth_params,
                    data={"name": name, "color": color},
                )
                response.raise_for_status()

                label = response.json()
                self.logger.info("Created label", name=name, label_id=label["id"])
                return label

        except Exception as e:
            self.logger.error("Failed to create label", name=name, error=str(e))
            return None

    async def get_or_create_label(self, name: str, color: str = "sky") -> Optional[str]:
        """
        Get existing label by name or create a new one.

        Args:
            name: Label name
            color: Label color for creation

        Returns:
            Label ID if successful, None otherwise
        """
        labels = await self.get_labels()
        for label in labels:
            if label.get("name") == name:
                return label["id"]

        # Label doesn't exist, create it
        label = await self.create_label(name, color)
        return label["id"] if label else None

    async def add_label_to_card(self, card_id: str, label_id: str) -> bool:
        """
        Add a label to a card by label ID.

        Args:
            card_id: Trello card ID
            label_id: Label ID to add

        Returns:
            True if successful
        """
        if not self.is_configured():
            return False

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._base_url}/cards/{card_id}/idLabels",
                    params=self._auth_params,
                    data={"value": label_id},
                )
                response.raise_for_status()

                self.logger.info("Added label to card", card_id=card_id[:8], label_id=label_id[:8])
                return True

        except Exception as e:
            self.logger.error("Failed to add label to card", card_id=card_id[:8], error=str(e))
            return False

    async def create_card(
        self,
        name: str,
        desc: str = "",
        list_id: Optional[str] = None,
        labels: Optional[List[str]] = None,
    ) -> Optional[str]:
        """
        Create a new Trello card.

        Args:
            name: Card name/title
            desc: Card description
            list_id: Target list ID (defaults to TODO list)
            labels: List of label names to add

        Returns:
            Card ID if successful, None otherwise
        """
        if not self.is_configured():
            return None

        try:
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Use TODO list by default
                target_list = list_id or self.config.trello_list_todo

                response = await client.post(
                    f"{self._base_url}/cards",
                    params=self._auth_params,
                    data={
                        "name": name,
                        "desc": desc,
                        "idList": target_list,
                    },
                )
                response.raise_for_status()

                card = response.json()
                card_id = card["id"]
                self.logger.info("Created Trello card", card_id=card_id[:8], name=name)

                # Add labels if specified
                if labels:
                    for label_name in labels:
                        label_id = await self.get_or_create_label(label_name, "orange")
                        if label_id:
                            await self.add_label_to_card(card_id, label_id)

                return card_id

        except Exception as e:
            self.logger.error("Failed to create card", name=name, error=str(e))
            return None

    # Helper methods for common operations
    async def move_to_in_progress(self, card_id: str) -> bool:
        """Move card to In Progress list."""
        return await self.move_card(card_id, self.config.trello_list_in_progress)

    async def move_to_review(self, card_id: str) -> bool:
        """Move card to Review list."""
        return await self.move_card(card_id, self.config.trello_list_review)

    async def move_to_done(self, card_id: str) -> bool:
        """Move card to Done list."""
        return await self.move_card(card_id, self.config.trello_list_done)

    # === FIX ISSUE #3: Add missing wrapper methods ===

    async def get_list_id_by_name(self, list_name: str) -> Optional[str]:
        """
        Get list ID by name.

        Args:
            list_name: Name of the list (e.g., "TODO", "In Progress", "Review")

        Returns:
            List ID if found, None otherwise
        """
        try:
            lists = await self.get_lists()
            return lists.get(list_name)
        except Exception as e:
            self.logger.logger.error("Failed to get list ID by name", name=list_name, error=str(e))
            return None

    async def add_card_label(self, card_id: str, label_name: str, color: str = "sky") -> bool:
        """
        Add a label to a card by name (creates label if needed).

        Args:
            card_id: Trello card ID
            label_name: Name of the label (e.g., "bug", "enhancement", "urgent")
            color: Label color (default: "sky")

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get or create the label
            label_id = await self.get_or_create_label(label_name, color)
            if not label_id:
                self.logger.logger.error("Failed to get or create label", name=label_name)
                return False

            # Add label to card
            return await self.add_label_to_card(card_id, label_id)
        except Exception as e:
            self.logger.logger.error("Failed to add label to card", card_id=card_id, label=label_name, error=str(e))
            return False

    async def move_to_list(self, card_id: str, list_name: str) -> bool:
        """
        Move card to a list by name.

        Args:
            card_id: Trello card ID
            list_name: Name of the target list (e.g., "TODO", "Blocked", "Done")

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get list ID by name
            list_id = await self.get_list_id_by_name(list_name)
            if not list_id:
                self.logger.logger.error("List not found", name=list_name)
                return False

            # Move card to list
            return await self.move_card(card_id, list_id)
        except Exception as e:
            self.logger.logger.error("Failed to move card to list", card_id=card_id, list=list_name, error=str(e))
            return False


# Global Trello client instance
_trello_client: Optional[TrelloClient] = None


def get_trello_client() -> TrelloClient:
    """Get the global Trello client instance."""
    global _trello_client
    if _trello_client is None:
        _trello_client = TrelloClient()
    return _trello_client
