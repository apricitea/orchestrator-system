"""
Worker Daemon - Always-On Task Processing

Main daemon loop that:
1. Checks API availability
2. Fetches next task from queue
3. Executes task
4. Handles rate limiting and errors
5. Reports status
"""

import asyncio
import signal
from datetime import datetime

from utils.logger import get_logger
from worker.availability_checker import get_availability_checker
from worker.worker_config import get_worker_config
from worker.db_models import get_task_db
from worker.task_executor import get_task_executor
from worker.task_queue import get_task_queue_manager
from worker.telegram.bot import get_telegram_bot


class WorkerDaemon:
    """
    Always-on worker daemon.

    Runs continuously, processing tasks from the queue when API is available.
    Handles graceful shutdown and error recovery.
    """

    def __init__(self):
        self.logger = get_logger("worker_daemon")
        self.config = get_worker_config()
        self._running = False
        self._shutdown_event = asyncio.Event()

        # Components
        self._availability_checker = get_availability_checker()
        self._task_queue = get_task_queue_manager()
        self._task_executor = get_task_executor()
        self._task_db = get_task_db()
        self._telegram_bot = get_telegram_bot()

        # Statistics
        self._tasks_processed = 0
        self._tasks_succeeded = 0
        self._tasks_failed = 0
        self._start_time: datetime | None = None

    async def start(self):
        """Start the worker daemon."""
        if self._running:
            self.logger.warning("Daemon already running")
            return

        self._running = True
        self._start_time = datetime.utcnow()
        self.logger.info("Starting worker daemon")

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        # Initialize components
        await self._initialize_components()

        # Start Telegram bot only if not disabled
        # Skip if standalone bot is running (controlled by ENABLE_TELEGRAM_IN_DAEMON env var)
        import os
        telegram_enabled = os.environ.get('ENABLE_TELEGRAM_IN_DAEMON', 'true').lower() == 'true'
        if self._telegram_bot.is_configured() and telegram_enabled:
            asyncio.create_task(self._telegram_bot.start())

        # Start Monitoring API server (runs in background)
        try:
            from worker.monitoring import StatusAPI

            monitoring_api = StatusAPI(host="127.0.0.1", port=8765)
            asyncio.create_task(monitoring_api.start())
            self.logger.info("Monitoring API started on http://127.0.0.1:8765")
        except Exception as e:
            self.logger.warning("Could not start monitoring API", error=str(e))

        # Send startup notification
        await self._telegram_bot.send_notification(
            f"🚀 *AI Worker Daemon Started*\n\n"
            f"⏰ {self._start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            f"🔄 Check interval: {self.config.check_interval}s\n"
            f"📊 Max concurrent tasks: {self.config.max_concurrent_tasks}\n"
            f"📈 Monitoring: http://127.0.0.1:8765/status",
        )

        # Main loop
        await self._main_loop()

    async def stop(self):
        """Stop the worker daemon."""
        if not self._running:
            return

        self.logger.info("Stopping worker daemon")
        self._running = False
        self._shutdown_event.set()

        # Send shutdown notification
        uptime = str(datetime.utcnow() - self._start_time).split(".")[0]
        await self._telegram_bot.send_notification(
            f"🛑 *AI Worker Daemon Stopped*\n\n"
            f"⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            f"⏱️ Uptime: {uptime}\n"
            f"📊 Tasks processed: {self._tasks_processed}\n"
            f"✅ Succeeded: {self._tasks_succeeded}\n"
            f"❌ Failed: {self._tasks_failed}",
        )

        # Stop Telegram bot
        await self._telegram_bot.stop()

        # Close connections
        await self._availability_checker.close()
        await self._task_queue.close()
        await self._task_db.close()

        self.logger.info("Worker daemon stopped")

    async def _initialize_components(self):
        """Initialize all components."""
        self.logger.info("Initializing components")

        await self._availability_checker.initialize()
        await self._task_queue.initialize()
        await self._task_db.initialize()
        await self._task_executor.initialize()

        # Initial task refresh
        await self._task_queue.refresh_tasks()

        self.logger.info("Components initialized")

    async def _main_loop(self):
        """Main daemon loop."""
        while self._running:
            try:
                # Check if we should shutdown
                if self._shutdown_event.is_set():
                    break

                # Check availability
                available, reason = await self._availability_checker.is_available()

                if not available:
                    self.logger.info("API unavailable, waiting", reason=reason)
                    await self._telegram_bot.send_notification(
                        f"⚠️ API Unavailable\n\nℹ️ {reason}\n"
                        f"⏳ Waiting {self.config.check_interval}s before retry..."
                    )
                    await asyncio.sleep(self.config.check_interval)
                    continue

                # Get next task
                task = await self._task_queue.get_next_task()

                if task:
                    # Handle both enum and string for priority
                    priority_value = task.priority.value if hasattr(task.priority, 'value') else task.priority
                    self.logger.info(
                        "Processing task",
                        task_id=task.id[:8],
                        title=task.title,
                        priority=priority_value,
                    )

                    # Execute task
                    success, message = await self._task_executor.execute_task(task)

                    self._tasks_processed += 1
                    if success:
                        self._tasks_succeeded += 1
                    else:
                        self._tasks_failed += 1

                    # Log statistics
                    await self._log_statistics()

                    # Small delay between tasks
                    await asyncio.sleep(5)

                else:
                    # No tasks, wait and refresh
                    self.logger.debug("No tasks in queue")
                    await asyncio.sleep(self.config.check_interval)
                    await self._task_queue.refresh_tasks()

            except asyncio.CancelledError:
                self.logger.info("Main loop cancelled")
                break
            except Exception as e:
                self.logger.error("Error in main loop", error=str(e))
                await asyncio.sleep(self.config.check_interval)

    async def _log_statistics(self):
        """Log current statistics."""
        queue_status = await self._task_queue.get_queue_status()
        availability_status = await self._availability_checker.get_status()

        self.logger.info(
            "Statistics",
            processed=self._tasks_processed,
            succeeded=self._tasks_succeeded,
            failed=self._tasks_failed,
            queue_size=queue_status["queued"],
            processing=queue_status["processing"],
            api_available=availability_status["available"],
        )

    async def get_status(self) -> dict:
        """Get daemon status."""
        queue_status = await self._task_queue.get_queue_status()
        availability_status = await self._availability_checker.get_status()

        uptime = str(datetime.utcnow() - self._start_time).split(".")[0] if self._start_time else "0:00:00"

        return {
            "running": self._running,
            "uptime": uptime,
            "tasks_processed": self._tasks_processed,
            "tasks_succeeded": self._tasks_succeeded,
            "tasks_failed": self._tasks_failed,
            "queue": queue_status,
            "availability": availability_status,
        }

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        self.logger.info("Received shutdown signal", signal=signum)
        self._shutdown_event.set()


async def run_worker():
    """Run the worker daemon."""
    daemon = WorkerDaemon()

    try:
        await daemon.start()
    except Exception as e:
        daemon.logger.error("Worker crashed", error=str(e))
    finally:
        await daemon.stop()


if __name__ == "__main__":
    asyncio.run(run_worker())
