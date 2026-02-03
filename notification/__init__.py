"""
Notification Module

Telegram notifications for PR approvals and escalations.
"""

from agents.notification.telegram_notifier import (
    TelegramNotifier,
    get_telegram_notifier,
)

__all__ = [
    "TelegramNotifier",
    "get_telegram_notifier",
]
