#!/usr/bin/env python3
"""
End-to-End Daemon Test

This script:
1. Creates a Trello task for wikipedia-analytics
2. Starts the worker daemon
3. Monitors the complete execution
"""

import asyncio
import sys
import signal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils.logger import configure_logging, get_logger
from worker.trello.client import get_trello_client
from worker.daemon import WorkerDaemon


# Test task for wikipedia-analytics
TEST_TASK_NAME = "[wikipedia-analytics] [agent] [P1] Create a simple data analysis function"

TEST_TASK_DESC = """
Create a simple data analysis function for the wikipedia-analytics project.

## Requirements:
1. Create a file called `data_analyzer.py` in the project directory
2. Add a function called `analyze_pageviews(data)` that:
   - Takes a list of pageview data as input
   - Returns the total views, average views, and peak day
3. Include proper documentation and type hints
4. Add a simple example in the `if __name__ == "__main__"` block

## Working Directory:
/home/ubuntu/projects/wikipedia-analytics
"""


async def create_test_task():
    """Create a test Trello task."""
    logger = get_logger("create_task")
    logger.info("Creating test Trello task...")

    trello = get_trello_client()

    if not trello.is_configured():
        logger.error("Trello not configured!")
        return None

    card_id = await trello.create_card(
        name=TEST_TASK_NAME,
        desc=TEST_TASK_DESC,
        labels=["P1"],
    )

    if card_id:
        logger.info(f"✓ Created Trello card: {card_id[:8]}")
        return card_id
    else:
        logger.error("Failed to create Trello card")
        return None


async def run_daemon_with_timeout(timeout_seconds=300):
    """Run the daemon with a timeout."""
    logger = get_logger("daemon_runner")
    daemon = WorkerDaemon()
    shutdown_event = asyncio.Event()

    async def timeout_handler():
        """Handle timeout."""
        await asyncio.sleep(timeout_seconds)
        logger.info(f"Timeout reached ({timeout_seconds}s), stopping daemon...")
        shutdown_event.set()
        await daemon.stop()

    # Setup signal handlers
    def signal_handler(signum, frame):
        logger.info("Received signal, stopping daemon...")
        shutdown_event.set()
        asyncio.create_task(daemon.stop())

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Start timeout handler
    asyncio.create_task(timeout_handler())

    # Start daemon
    try:
        logger.info("="*60)
        logger.info("STARTING WORKER DAEMON FOR E2E TEST")
        logger.info("="*60)
        await daemon.start()
    except Exception as e:
        logger.error(f"Daemon crashed: {e}")
        return False

    return True


async def monitor_task_progress():
    """Monitor task progress by checking Trello board."""
    logger = get_logger("monitor")
    trello = get_trello_client()

    for i in range(60):  # Check for 5 minutes (60 * 5 seconds)
        await asyncio.sleep(5)

        # Get current cards
        lists = await trello.get_lists()
        logger.info(f"Check #{i+1}: Trello board status")

        for list_name, list_id in lists.items():
            # Get cards in this list
            try:
                import httpx
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(
                        f"{trello._base_url}/lists/{list_id}/cards",
                        params=trello._auth_params,
                    )
                    response.raise_for_status()
                    cards = response.json()

                    if cards:
                        logger.info(f"  {list_name}: {len(cards)} card(s)")
                        for card in cards:
                            if TEST_TASK_NAME.split("]")[0] in card["name"]:
                                logger.info(f"    - {card['name'][:50]}... ({card['name'].split(']')[-1].strip()})")

                                # Check if moved to DONE
                                if list_name == "Done":
                                    logger.info("✓✓✓ TASK COMPLETED IN TRELLO! ✓✓✓")
                                    return True

            except Exception as e:
                logger.warning(f"Could not check list {list_name}: {e}")

    return False


async def main():
    """Main entry point."""
    configure_logging()
    logger = get_logger("main")

    print("\n" + "="*70)
    print(" " * 15 + "END-TO-END DAEMON TEST")
    print("="*70 + "\n")

    # Step 1: Create test task
    logger.info("STEP 1: Creating test Trello task")
    card_id = await create_test_task()

    if not card_id:
        logger.error("Failed to create test task, aborting...")
        return 1

    logger.info(f"Test task created: {card_id[:8]}")

    # Step 2: Start monitoring in background
    logger.info("STEP 2: Starting task monitor")
    monitor_task = asyncio.create_task(monitor_task_progress())

    # Step 3: Start daemon
    logger.info("STEP 3: Starting worker daemon")
    success = await run_daemon_with_timeout(timeout_seconds=300)

    # Wait for monitor
    completed = await monitor_task

    # Summary
    print("\n" + "="*70)
    print(" " * 25 + "TEST SUMMARY")
    print("="*70)
    print(f"Daemon ran successfully: {'✓ YES' if success else '✗ NO'}")
    print(f"Task completed in Trello: {'✓ YES' if completed else '✗ NO'}")
    print("="*70 + "\n")

    return 0 if (success and completed) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
