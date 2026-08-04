#!/usr/bin/env python3
"""
FINAL End-to-End Test - 2 Tasks

This test:
1. Clears Redis queue
2. Starts daemon
3. Creates 2 tasks in Trello
4. Monitors BOTH tasks through complete workflow
5. Verifies both reach DONE
"""

import asyncio
import os
import signal
import sys
import subprocess
from datetime import datetime
from pathlib import Path

# Load environment
env_file = Path("/home/ubuntu/.env")
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                value = value.strip().strip('"').strip("'")
                os.environ[key] = value

sys.path.insert(0, "/home/ubuntu")

from worker.trello.client import get_trello_client
from worker.daemon import WorkerDaemon
from utils.logger import configure_logging, get_logger

# ANSI colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_header(text):
    print(f"\n{BOLD}{BLUE}{'='*100}{RESET}")
    print(f"{BOLD}{BLUE}{text.center(100)}{RESET}")
    print(f"{BOLD}{BLUE}{'='*100}{RESET}\n")


def print_section(text):
    print(f"\n{BOLD}{YELLOW}{'─'*100}{RESET}")
    print(f"{BOLD}{YELLOW}{text}{RESET}")
    print(f"{BOLD}{YELLOW}{'─'*100}{RESET}\n")


def print_success(text):
    print(f"{GREEN}✅ {text}{RESET}")


def print_error(text):
    print(f"{RED}❌ {text}{RESET}")


def print_info(text):
    print(f"{BLUE}ℹ️  {text}{RESET}")


# Test tasks
TEST_TASKS = [
    {
        "name": "[laptop-recommendation] [agent] P2: Test Task 1 - Add counter utility",
        "desc": """
Create a simple counter utility for the laptop-recommendation project.

## Requirements:
1. Create a file called `utils/counter.py`
2. Add a class called `Counter` with methods:
   - increment() -> int
   - decrement() -> int
   - reset() -> None
   - get_count() -> int
3. Include proper documentation and type hints
4. Add example in `if __name__ == "__main__"` block

## Working Directory:
/home/ubuntu/projects/laptop-recommendation

## Priority:
P2 (Test task 1)
""",
        "label": "P2"
    },
    {
        "name": "[laptop-recommendation] [agent] P2: Test Task 2 - Add string utils",
        "desc": """
Create a string utility module for the laptop-recommendation project.

## Requirements:
1. Create a file called `utils/string_utils.py`
2. Add functions:
   - reverse_string(s: str) -> str
   - capitalize_words(s: str) -> str
   - is_palindrome(s: str) -> bool
3. Include proper documentation and type hints
4. Add examples in `if __name__ == "__main__"` block

## Working Directory:
/home/ubuntu/projects/laptop-recommendation

## Priority:
P2 (Test task 2)
""",
        "label": "P2"
    }
]

# Track state
test_state = {
    "redis_cleared": False,
    "daemon_started": False,
    "cards": [],
    "completed": [],
    "issues": [],
}


async def clear_redis_queue():
    """Clear stale tasks from Redis queue."""
    print_section("STEP 1: CLEAR REDIS QUEUE")

    logger = get_logger("clear_redis")

    try:
        from redis.asyncio import Redis

        redis = Redis(host="localhost", port=6379, db=0)
        queue_key = "task_queue"

        # Check current size
        size = await redis.llen(queue_key)
        print_info(f"Current queue size: {size} tasks")

        if size > 0:
            print_warning(f"Clearing {size} stale tasks...")
            await redis.delete(queue_key)
            print_success(f"Cleared {size} tasks")
        else:
            print_success("Queue is empty")

        await redis.aclose()  # Use aclose instead of close
        test_state["redis_cleared"] = True
        return True

    except Exception as e:
        print_error(f"Failed to clear Redis: {e}")
        logger.error("Failed to clear Redis", error=str(e))
        return False


async def create_test_tasks():
    """Create 2 test tasks in Trello."""
    print_section("STEP 2: CREATE 2 TEST TASKS IN TRELLO")

    logger = get_logger("create_tasks")
    trello = get_trello_client()

    for i, task in enumerate(TEST_TASKS, 1):
        print_info(f"Creating Task {i}: {task['name'][:50]}...")

        try:
            card_id = await trello.create_card(
                name=task["name"],
                desc=task["desc"],
                labels=[task["label"]],
            )

            if card_id:
                test_state["cards"].append({
                    "id": card_id,
                    "name": task["name"],
                    "task_num": i,
                })
                print_success(f"Task {i} created: {card_id}")
                logger.info(f"✓ Created task {i}: {card_id[:8]}")
            else:
                print_error(f"Failed to create task {i}")
                return None

        except Exception as e:
            print_error(f"Failed to create task {i}: {e}")
            logger.error(f"Failed to create task {i}", error=str(e))
            return None

    print_success(f"\nBoth tasks created successfully!")
    print_info(f"Task 1: {test_state['cards'][0]['id']}")
    print_info(f"Task 2: {test_state['cards'][1]['id']}")
    return True


async def monitor_and_run_daemon(timeout_seconds: int = 1200):
    """Start daemon and monitor both tasks."""
    print_section("STEP 3: START DAEMON AND MONITOR BOTH TASKS")

    logger = get_logger("daemon_monitor")
    shutdown_event = asyncio.Event()

    # Start daemon
    print_info("Starting WorkerDaemon...")
    daemon = WorkerDaemon()
    test_state["daemon_started"] = True

    # Setup signal handlers
    def signal_handler(signum, frame):
        logger.info("Received signal, stopping daemon...")
        print_warning("\nReceived stop signal, shutting down...")
        shutdown_event.set()
        asyncio.create_task(daemon.stop())

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Start daemon in background
    async def run_daemon():
        try:
            await daemon.start()
        except Exception as e:
            logger.error(f"Daemon crashed: {e}")
            test_state["issues"].append(f"Daemon crash: {str(e)}")
            shutdown_event.set()

    daemon_task = asyncio.create_task(run_daemon())

    # Monitor both tasks
    print_info(f"Monitoring BOTH tasks (timeout: {timeout_seconds}s)...\n")
    print_info("Waiting for both tasks to reach DONE...\n")

    start_time = datetime.now()
    check_interval = 10

    # Track card statuses
    card_statuses = {card['id']: "TODO" for card in test_state["cards"]}

    workflow_stages = {
        "TODO": "Task created",
        "IN PROGRESS": "Agent picked up task",
        "REVIEW": "PR created, in review",
        "DONE": "PR reviewed and approved ✅",
    }

    try:
        while not shutdown_event.is_set():
            elapsed = (datetime.now() - start_time).total_seconds()

            # Check timeout
            if elapsed > timeout_seconds:
                print_warning(f"Timeout reached ({timeout_seconds}s)")
                break

            try:
                trello = get_trello.client()
                lists = await trello.get_lists()

                # Check each card
                for card in test_state["cards"]:
                    card_id = card['id']
                    old_status = card_statuses[card_id]
                    new_status = None

                    # Find which list the card is in
                    for list_name, list_id in lists.items():
                        import httpx
                        async with httpx.AsyncClient(timeout=30.0) as client:
                            response = await client.get(
                                f"{trello._base_url}/lists/{list_id}/cards",
                                params=trello._auth_params,
                            )
                            response.raise_for_status()
                            cards = response.json()

                            for c in cards:
                                if c["id"] == card_id:
                                    new_status = list_name.upper()
                                    break

                            if new_status:
                                break

                    # Status change detected
                    if new_status and new_status != old_status:
                        elapsed_str = str(elapsed).split(".")[0]
                        stage_desc = workflow_stages.get(new_status, new_status)
                        print_success(f"[{elapsed_str}] Task {card['task_num']}: {old_status} → {new_status}")
                        print_info(f"  Stage: {stage_desc}")
                        logger.info(f"Task {card['task_num']}: {old_status} → {new_status}")

                        card_statuses[card_id] = new_status

                        # Task reached DONE
                        if new_status == "DONE":
                            test_state["completed"].append(card_id)
                            print_success(f"🎉 Task {card['task_num']} COMPLETED!")

                # Check if both tasks completed
                if len(test_state["completed"]) == len(test_state["cards"]):
                    print_success(f"\n🎉 BOTH TASKS COMPLETED!")
                    await asyncio.sleep(10)  # Brief pause
                    shutdown_event.set()
                    break

                # Periodic update
                if int(elapsed) % 60 == 0 and int(elapsed) > 0:
                    elapsed_str = str(elapsed).split(".")[0]
                    completed_count = len(test_state["completed"])
                    print_info(f"[{elapsed_str}] {completed_count}/{len(test_state['cards'])} tasks completed")

            except Exception as e:
                logger.error("Error monitoring", error=str(e))
                test_state["issues"].append(f"Monitor error: {str(e)}")

            await asyncio.sleep(check_interval)

    finally:
        # Stop daemon
        print_info("\nStopping daemon...")
        shutdown_event.set()
        try:
            await asyncio.wait_for(daemon.stop(), timeout=30)
            print_success("Daemon stopped")
        except asyncio.TimeoutError:
            print_warning("Daemon stop timed out")

        daemon_task.cancel()
        try:
            await daemon_task
        except asyncio.CancelledError:
            pass


async def run_final_test():
    """Run final end-to-end test with 2 tasks."""
    configure_logging()
    logger = get_logger("final_e2e_test")

    print_header("🚀 FINAL END-TO-END TEST - 2 TASKS")
    print_info("This test validates the COMPLETE autonomous workflow with 2 tasks:")
    print_info("  1. Clear Redis queue")
    print_info("  2. Start daemon")
    print_info("  3. Create 2 tasks in Trello")
    print_info("  4. Monitor BOTH tasks through complete workflow")
    print(f"{YELLOW}  5. Verify BOTH reach DONE{RESET}\n")

    # Step 1: Clear Redis
    if not await clear_redis_queue():
        print_error("Failed to clear Redis queue")
        return 1

    # Step 2: Create tasks
    if not await create_test_tasks():
        print_error("Failed to create test tasks")
        return 1

    # Step 3: Run daemon and monitor
    await monitor_and_run_daemon(timeout_seconds=1200)

    # Final summary
    print_header("FINAL TEST RESULTS")

    print(f"\n{BOLD}Workflow Stages:{RESET}\n")
    print(f"Redis cleared:       {GREEN}✓{RESET}" if test_state["redis_cleared"] else f"Redis cleared:       {RED}✗{RESET}")
    print(f"Daemon started:      {GREEN}✓{RESET}" if test_state["daemon_started"] else f"Daemon started:      {RED}✗{RESET}")

    print(f"\n{BOLD}Task Completion:{RESET}\n")
    for i, card in enumerate(test_state["cards"], 1):
        completed = card['id'] in test_state["completed"]
        status = f"{GREEN}✓ DONE{RESET}" if completed else f"{RED}✗ NOT DONE{RESET}"
        print(f"Task {i}: {status}")

    if test_state["issues"]:
        print(f"\n{YELLOW}Issues found ({len(test_state['issues'])}):{RESET}")
        for issue in test_state["issues"]:
            print(f"  • {issue}")

    all_completed = len(test_state["completed"]) == len(test_state["cards"])

    if all_completed:
        print(f"\n{GREEN}{BOLD}🎉 COMPLETE SUCCESS!{RESET}")
        print(f"{GREEN}Both tasks completed the full autonomous workflow!{RESET}\n")
        print(f"{BOLD}{GREEN}✅ THE AUTONOMOUS SYSTEM IS FULLY VALIDATED!{RESET}\n")

        print(f"{BOLD}Artifacts:{RESET}\n")
        for i, card in enumerate(test_state["cards"], 1):
            print(f"  Task {i}: https://trello.com/c/{card['id']}")

        return 0
    else:
        print(f"\n{RED}{BOLD}⚠️ INCOMPLETE{RESET}")
        print(f"{RED}Only {len(test_state['completed'])}/{len(test_state['cards'])} tasks completed{RESET}\n")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_final_test())
    sys.exit(exit_code)
