"""
Telegram Bot Integration - Task Management via Telegram

Provides a Telegram bot interface for:
- Adding tasks
- Listing tasks
- Checking status
- Receiving notifications
"""

import asyncio
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from utils.logger import get_logger
from worker.worker_config import get_worker_config
from worker.db_models import Task, TaskPriority, TaskSource, TaskStatus


class TelegramCommand(str, Enum):
    """Telegram bot commands."""
    START = "start"
    ADD = "add"
    ADDTRELLO = "addtrello"
    LIST = "list"
    TRELLO = "trello"
    STATUS = "status"
    PRIORITY = "priority"
    CANCEL = "cancel"
    HELP = "help"


@dataclass
class TelegramTask:
    """Task from Telegram."""
    chat_id: int
    message_id: int
    title: str
    description: str
    project_name: str
    priority: TaskPriority


class TelegramBot:
    """
    Telegram bot for task management.

    Commands:
    /start - Initialize bot
    /add <project> <priority> <task> - Add a new task
    /list - List all pending tasks
    /status - Check worker status
    /priority <task_id> <P0-P3> - Change task priority
    /cancel <task_id> - Cancel a task
    /help - Show help
    """

    def __init__(self):
        self.logger = get_logger("telegram_bot")
        self.config = get_worker_config()
        self._application: Optional[Application] = None
        self._running = False

    def is_configured(self) -> bool:
        """Check if Telegram is properly configured."""
        return self.config.is_telegram_configured()

    async def start(self):
        """Start the Telegram bot."""
        if not self.is_configured():
            self.logger.warning("Telegram not configured")
            return

        try:
            self._application = Application.builder().token(self.config.telegram_bot_token).build()

            # Register handlers
            self._application.add_handler(CommandHandler("start", self._cmd_start))
            self._application.add_handler(CommandHandler("addtrello", self._cmd_add_trello))
            self._application.add_handler(CommandHandler("trello", self._cmd_trello))
            self._application.add_handler(CommandHandler("status", self._cmd_status))
            self._application.add_handler(CommandHandler("help", self._cmd_help))

            # Start bot
            self._running = True
            await self._application.initialize()
            await self._application.start()
            await self._application.updater.start_polling(drop_pending_updates=True)

            self.logger.info("Telegram bot started")

        except Exception as e:
            self.logger.error("Failed to start Telegram bot", error=str(e))

    async def stop(self):
        """Stop the Telegram bot."""
        if self._application and self._running:
            self._running = False
            await self._application.updater.stop()
            await self._application.stop()
            await self._application.shutdown()
            self.logger.info("Telegram bot stopped")

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        await update.message.reply_text(
            "🤖 *AI Worker Bot*\n\n"
            "I help you manage tasks for the AI worker daemon.\n\n"
            "Use /help to see available commands.",
            parse_mode="Markdown",
        )

    async def _cmd_add_trello(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /addtrello command - Add task directly to Trello with full specifications.

        Usage: /addtrello <project> <priority> <title>

        Example:
        /addtrello laptop-recommendation P1 Add dark mode

        The specifications agent will analyze the project and generate a detailed
        task specification automatically.
        """
        if not context.args or len(context.args) < 3:
            await update.message.reply_text(
                "❌ Usage: /addtrello <project> <priority> <title>\n\n"
                "Example:\n"
                "/addtrello laptop-recommendation P1 Add dark mode\n\n"
                "The specifications agent will analyze the project and generate\n"
                "a detailed task specification automatically.",
            )
            return

        try:
            from worker.trello.client import get_trello_client
            from agents.specifications_agent.specs_agent import get_specs_agent

            project_name = context.args[0]
            priority_str = context.args[1].upper()
            title = " ".join(context.args[2:])

            # Validate priority
            if priority_str not in ("P0", "P1", "P2", "P3"):
                await update.message.reply_text(
                    "❌ Invalid priority. Use P0, P1, P2, or P3",
                )
                return

            # Get Trello client
            trello = get_trello_client()

            if not trello.is_configured():
                await update.message.reply_text(
                    "❌ Trello is not configured. Please check your environment variables."
                )
                return

            # Send "working on it" message
            status_msg = await update.message.reply_text(
                f"🔍 *Analyzing project and generating specification...*\n\n"
                f"📁 Project: {project_name}\n"
                f"📌 Task: {title}\n"
                f"⚡ Priority: {priority_str}\n\n"
                f"This may take 30-60 seconds...",
                parse_mode="Markdown",
            )

            # Use specifications agent to generate detailed task description
            specs_agent = get_specs_agent()
            spec_result = await specs_agent.generate_specification(
                project_name=project_name,
                task_title=title,
                user_description="",
                priority=priority_str,
            )

            if spec_result.is_success():
                task_spec = spec_result.output
            else:
                # Fallback to basic template if specs agent fails
                task_spec = f"""## {title}

### Task added via Telegram by: {update.effective_user.full_name or update.effective_user.username}

### Working Directory:
/home/ubuntu/projects/{project_name}

### Requirements:
{title}

### Priority: {priority_str}

### Deliverables:
- Implementation
- Tests
- Git branch, commit, and pull request
- Documentation

---
⚠️ Specifications agent failed to generate detailed requirements.
Basic template used instead.
"""

            # Create Trello card with [agent] tag
            full_title = f"[{project_name}] [agent] {priority_str}: {title}"
            card_id = await trello.create_card(full_title, task_spec)

            if card_id:
                # Add priority label
                import httpx
                import os
                from dotenv import load_dotenv
                load_dotenv('/home/ubuntu/.env')

                trello_key = os.getenv('TRELLO_API_KEY')
                trello_token = os.getenv('TRELLO_TOKEN')

                # Map priority to label color
                priority_colors = {
                    'P0': 'red',
                    'P1': 'orange',
                    'P2': 'yellow',
                    'P3': 'green'
                }

                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"https://api.trello.com/1/cards/{card_id}/labels",
                        params={
                            'key': trello_key,
                            'token': trello_token,
                            'color': priority_colors.get(priority_str, 'green'),
                            'name': priority_str
                        }
                    )

                await update.message.reply_text(
                    f"✅ *Trello Task Created with AI-Generated Specification*\n\n"
                    f"📌 {title}\n"
                    f"📁 Project: {project_name}\n"
                    f"⚡ Priority: {priority_str}\n"
                    f"🆔 Card ID: {card_id[:12]}...\n\n"
                    f"🤖 Specifications agent analyzed the project and generated\n"
                    f"   detailed requirements for the orchestrator.\n\n"
                    f"💡 View the card in Trello to see the full specification.",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("❌ Failed to create Trello card")

        except Exception as e:
            self.logger.error("Failed to add Trello task", error=str(e))
            await update.message.reply_text(f"❌ Failed to add Trello task: {str(e)}")

    async def _cmd_trello(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /trello command - Show tasks from Trello lists.

        Usage: /trello [list]

        Lists:
        - todo (default)
        - progress
        - review
        - all
        """
        from worker.trello.client import get_trello_client

        trello = get_trello_client()

        if not trello.is_configured():
            await update.message.reply_text(
                "❌ Trello is not configured"
            )
            return

        try:
            # Parse list argument
            list_filter = "all"
            if context.args:
                list_filter = context.args[0].lower()

            message = "📋 *Trello Tasks*\n\n"

            if list_filter in ["todo", "all"]:
                # Fetch TODO tasks - show all tasks
                todo_tasks = await trello.get_todo_cards()

                if todo_tasks:
                    message += f"*📝 TODO List ({len(todo_tasks)})*\n"
                    for task in todo_tasks[:5]:
                        # Extract priority from title or metadata
                        priority = task.metadata.get('priority', 'P3')
                        # Show is_agent_task indicator
                        agent_indicator = "🤖" if task.metadata.get('is_agent_task') else ""
                        message += f"\n⚡ [{priority}] {agent_indicator} {task.title[:60]}\n"
                        if task.project_name:
                            message += f"   📁 {task.project_name}\n"

                    if len(todo_tasks) > 5:
                        message += f"\n... and {len(todo_tasks) - 5} more TODO tasks\n"
                else:
                    message += "*📝 TODO List*\nNo tasks\n"

            if list_filter in ["progress", "all"]:
                message += "\n"
                # Fetch In Progress tasks - show all tasks
                progress_tasks = await trello.get_in_progress_cards()

                if progress_tasks:
                    message += f"*🔄 In Progress ({len(progress_tasks)})*\n"
                    for task in progress_tasks[:3]:
                        priority = task.metadata.get('priority', 'P3')
                        agent_indicator = "🤖" if task.metadata.get('is_agent_task') else ""
                        message += f"\n⚡ [{priority}] {agent_indicator} {task.title[:60]}\n"
                else:
                    message += "*🔄 In Progress*\nNo active tasks\n"

            if list_filter in ["review", "all"]:
                message += "\n"
                # Fetch Review tasks - show all tasks
                review_tasks = await trello.get_review_cards()

                if review_tasks:
                    message += f"*👀 Review ({len(review_tasks)})*\n"
                    for task in review_tasks[:5]:
                        priority = task.metadata.get('priority', 'P3')
                        agent_indicator = "🤖" if task.metadata.get('is_agent_task') else ""
                        message += f"\n⚡ [{priority}] {agent_indicator} {task.title[:60]}\n"

                    if len(review_tasks) > 5:
                        message += f"\n... and {len(review_tasks) - 5} more in review\n"
                else:
                    message += "*👀 Review*\nNo tasks\n"

            # Add footer
            message += "\n💡 /trello [todo|progress|review|all]"

            await update.message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            self.logger.error("Failed to fetch Trello tasks", error=str(e))
            await update.message.reply_text(f"❌ Failed to fetch Trello tasks: {str(e)}")

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        try:
            from worker.availability_checker import get_availability_checker

            checker = get_availability_checker()
            status = await checker.get_status()

            if status["available"]:
                message = (
                    f"✅ *Worker Status*\n\n"
                    f"🟢 API Available\n"
                    f"📊 Daily tokens: {status['daily_tokens_used']}/{status['daily_tokens_limit']}\n"
                    f"📈 {status['daily_tokens_percentage']}% used"
                )
            else:
                message = (
                    f"⚠️ *Worker Status*\n\n"
                    f"🔴 API Unavailable\n"
                    f"ℹ️ {status['reason']}"
                )

            await update.message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            self.logger.error("Failed to get status", error=str(e))
            await update.message.reply_text(f"❌ Failed to get status: {str(e)}")

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        help_text = """🤖 *AI Worker Bot - Help*

*Task Commands:*
/addtrello <project> <priority> <title> - Add task to Trello (for orchestrator)
/trello [list] - Show Trello tasks (todo/progress/review/all)
/status - Check worker/daemon status

*Priority Levels:*
P0 - Critical (immediate)
P1 - High (within 1 hour)
P2 - Medium (within 4 hours)
P3 - Low (within 24 hours)

*Trello Integration:*
💡 Use /addtrello to create tasks that the orchestrator agent will work on
💡 Tasks created via /addtrello are tagged with [agent] and moved through:
   TODO → In Progress → Review → Done
💡 Use /trello to see all orchestrator tasks

*Examples:*
/addtrello laptop-recommendation P1 Add dark mode
/trello review
/trello all
"""

        await update.message.reply_text(help_text, parse_mode="Markdown")

    async def send_notification(
        self,
        message: str,
        chat_id: Optional[int] = None,
    ) -> bool:
        """
        Send a notification message.

        Args:
            message: Message text
            chat_id: Optional chat ID (defaults to configured chat)

        Returns:
            True if successful
        """
        if not self.is_configured():
            return False

        try:
            chat_id = chat_id or self.config.telegram_chat_id

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"https://api.telegram.org/bot{self.config.telegram_bot_token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": message,
                        "parse_mode": "Markdown",
                        "disable_web_page_preview": True,
                    },
                )
                response.raise_for_status()
                return True

        except Exception as e:
            # Try without Markdown if that's the issue
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        f"https://api.telegram.org/bot{self.config.telegram_bot_token}/sendMessage",
                        json={
                            "chat_id": chat_id,
                            "text": message,
                            "disable_web_page_preview": True,
                        },
                    )
                    response.raise_for_status()
                    return True
            except Exception as e2:
                self.logger.error("Failed to send notification", error=str(e2))
                return False

    async def notify_task_started(
        self,
        task: Task,
    ):
        """Send notification when task is started."""
        # Handle both enum and string priority
        priority_value = task.priority.value if hasattr(task.priority, 'value') else task.priority

        message = (
            f"🚀 *Task Started*\n\n"
            f"📌 {task.title}\n"
            f"📁 {task.project_name or 'N/A'}\n"
            f"⚡ Priority: {priority_value}\n"
        )

        await self.send_notification(message)

    async def notify_task_completed(
        self,
        task: Task,
        pr_url: str = "",
    ):
        """Send notification when task is completed."""
        message = (
            f"✅ *Task Completed*\n\n"
            f"📌 {task.title}\n"
            f"📁 {task.project_name}\n"
        )

        if pr_url:
            message += f"🔗 PR: {pr_url}\n"

        await self.send_notification(message)

    async def notify_task_failed(self, task: Task, error: str):
        """Send notification when task fails."""
        message = (
            f"❌ *Task Failed*\n\n"
            f"📌 {task.title}\n"
            f"📁 {task.project_name}\n"
            f"ℹ️ {error[:200]}"
        )

        await self.send_notification(message)


# Global Telegram bot instance
_telegram_bot: Optional[TelegramBot] = None


def get_telegram_bot() -> TelegramBot:
    """Get the global Telegram bot instance."""
    global _telegram_bot
    if _telegram_bot is None:
        _telegram_bot = TelegramBot()
    return _telegram_bot
