#!/home/ubuntu/venv/bin/python
"""
Standalone Telegram Bot Runner

Run the Telegram bot independently for task management via Telegram.
The bot handles commands like /addtrello, /trello, /status, /help, etc.
"""

import asyncio
import signal
import sys

sys.path.insert(0, '/home/ubuntu')

from worker.telegram.bot import get_telegram_bot
from utils.logger import get_logger

logger = get_logger("telegram_bot_runner")


class TelegramBotRunner:
    """Runner for standalone Telegram bot."""

    def __init__(self):
        self.bot = get_telegram_bot()
        self._running = False
        self._shutdown_event = asyncio.Event()

    async def start(self):
        """Start the Telegram bot."""
        if self._running:
            logger.warning("Bot already running")
            return

        if not self.bot.is_configured():
            logger.error("Telegram bot not configured")
            print("❌ Telegram bot not configured")
            print("   Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
            return 1

        self._running = True
        logger.info("Starting Telegram bot")
        print("🤖 Starting Telegram bot...")

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        try:
            # Start the bot
            await self.bot.start()

            print("✅ Telegram bot started")
            print(f"   Bot is listening for commands...")
            print(f"   Available commands: /help, /addtrello, /trello, /status, /list")
            print(f"   Press Ctrl+C to stop")

            # Send startup notification
            await self.bot.send_notification(
                "🤖 *Telegram Bot Started*\n\n"
                "I'm ready to help you manage tasks!\n\n"
                "Use /help to see available commands."
            )

            # Keep running until shutdown
            await self._shutdown_event.wait()

        except asyncio.CancelledError:
            logger.info("Bot cancelled")
        except Exception as e:
            logger.error("Bot error", error=str(e))
            print(f"❌ Bot error: {e}")
        finally:
            await self.stop()

    async def stop(self):
        """Stop the Telegram bot."""
        if not self._running:
            return

        self._running = False
        self._shutdown_event.set()

        logger.info("Stopping Telegram bot")
        print("\n🛑 Stopping Telegram bot...")

        await self.bot.stop()

        # Send shutdown notification
        await self.bot.send_notification("🛑 Telegram Bot Stopped")

        print("✅ Telegram bot stopped")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info("Received shutdown signal", signal=signum)
        self._shutdown_event.set()


async def main():
    """Main entry point."""
    runner = TelegramBotRunner()

    try:
        await runner.start()
        return 0
    except KeyboardInterrupt:
        print("\n⚠️  Keyboard interrupt")
        return 0
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
