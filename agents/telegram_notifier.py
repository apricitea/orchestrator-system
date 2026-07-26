"""
Telegram Notification System

Sends notifications to Telegram when PRs are approved and ready for merge.
"""

import os
from typing import Dict, Optional

import httpx
from utils.logger import get_logger


class TelegramNotifier:
    """Send Telegram notifications for PR approvals."""

    def __init__(self):
        """Initialize Telegram notifier."""
        self.logger = get_logger("telegram_notifier")
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")

        if not self.bot_token or not self.chat_id:
            self.logger.warning(
                "Telegram credentials not configured",
                has_token=bool(self.bot_token),
                has_chat_id=bool(self.chat_id),
            )

    async def send_pr_approval_notification(
        self,
        project_name: str,
        pr_number: int,
        pr_title: str,
        pr_url: str,
        branch_name: str,
        base_branch: str = "main",
        check_results: Optional[Dict] = None,
    ) -> bool:
        """
        Send notification when PR is approved and ready to merge.

        Args:
            project_name: Name of the project
            pr_number: PR number
            pr_title: PR title
            pr_url: Full URL to the PR
            branch_name: Feature branch name
            base_branch: Base branch (default: main)
            check_results: Optional dict of check results

        Returns:
            True if notification sent successfully
        """
        if not self.bot_token or not self.chat_id:
            self.logger.error("Cannot send notification: credentials not configured")
            return False

        # Build message
        message = self._build_approval_message(
            project_name=project_name,
            pr_number=pr_number,
            pr_title=pr_title,
            pr_url=pr_url,
            branch_name=branch_name,
            base_branch=base_branch,
            check_results=check_results or {},
        )

        # Send to Telegram
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    json={
                        "chat_id": self.chat_id,
                        "text": message,
                        "parse_mode": "Markdown",
                        "disable_web_page_preview": False,
                    },
                )

                if response.status_code == 200:
                    self.logger.info(
                        "Telegram notification sent",
                        project=project_name,
                        pr_number=pr_number,
                    )
                    return True
                else:
                    self.logger.error(
                        "Telegram API error",
                        status_code=response.status_code,
                        response=response.text,
                    )
                    return False

        except Exception as e:
            self.logger.error("Failed to send Telegram notification", error=str(e))
            return False

    async def send_escalation_notification(
        self,
        reason: str,
        project_name: str,
        task_url: str,
        context: Dict,
    ) -> bool:
        """
        Send escalation notification when agent cannot proceed.

        Args:
            reason: Why escalation is needed
            project_name: Project name
            task_url: URL to Trello card
            context: Additional context

        Returns:
            True if notification sent successfully
        """
        if not self.bot_token or not self.chat_id:
            self.logger.error("Cannot send escalation: credentials not configured")
            return False

        message = f"""
🚨 *AUTONOMOUS AGENT ESCALATION*

*Reason:* {reason}

*Context:*
• Project: `{project_name}`
• Task URL: {task_url}

Please review and take appropriate action.
        """.strip()

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    json={
                        "chat_id": self.chat_id,
                        "text": message,
                        "parse_mode": "Markdown",
                    },
                )

                return response.status_code == 200

        except Exception as e:
            self.logger.error("Failed to send escalation notification", error=str(e))
            return False

    def _build_approval_message(
        self,
        project_name: str,
        pr_number: int,
        pr_title: str,
        pr_url: str,
        branch_name: str,
        base_branch: str,
        check_results: Dict,
    ) -> str:
        """Build approval notification message."""
        # Build check status emojis
        checks = check_results.get("checks", {})

        def get_status_emoji(check_name: str) -> str:
            status = checks.get(check_name, "unknown")
            if status == "passed":
                return "✅"
            elif status == "warning":
                return "⚠️"
            elif status == "failed":
                return "❌"
            return "❓"

        message = f"""
🎉 *PR APPROVED AND READY TO MERGE*

*Project:* `{project_name}`
*PR:* #{pr_number}
*Title:* {pr_title}
*URL:* {pr_url}

*Branch:* `{branch_name}` → `{base_branch}`
*Author:* Autonomous Agent

*Check Results:*
{get_status_emoji('tests')} Tests Passing
{get_status_emoji('security')} Security Scan
{get_status_emoji('review')} Code Review
{get_status_emoji('pr_review')} PR Review

✅ All checks passed
✅ Code review approved
✅ PR review approved

👉 [Please review and merge]({pr_url})
        """.strip()

        return message


# Global instance
_telegram_notifier = None


def get_telegram_notifier() -> TelegramNotifier:
    """Get global Telegram notifier instance."""
    global _telegram_notifier
    if _telegram_notifier is None:
        _telegram_notifier = TelegramNotifier()
    return _telegram_notifier
