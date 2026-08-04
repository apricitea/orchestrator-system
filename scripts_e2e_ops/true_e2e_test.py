#!/usr/bin/env python3
"""
TRUE End-to-End Test with Daemon

This test:
1. Clears Redis queue
2. Starts the daemon
3. Creates a test task
4. Monitors complete workflow
5. Verifies all stages work
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


def print_warning(text):
    print(f"{YELLOW}⚠️  {text}{RESET}")


# Test task
TEST_TASK_NAME = "[laptop-recommendation] [agent] P2: TRUE E2E Test - Add calculator utility"
TEST_TASK_DESC = """
Create a simple calculator utility for the laptop-recommendation project.

## Requirements:
1. Create a file called `utils/calculator.py` in the project directory
2. Add functions for basic operations:
   - add(a, b) -> float
   - subtract(a, b) -> float
   - multiply(a, b) -> float
   - divide(a, b) -> float (handle division by zero)
3. Include proper documentation and type hints
4. Add a simple example in the `if __name__ == "__main__"` block
5. Add basic error handling

## Working Directory:
/home/ubuntu/projects/laptop-recommendation

## Priority:
P2 (Medium priority - for TRUE end-to-end validation)
"""

# Track state
test_state = {
    "redis_cleared": False,
    "daemon_started": False,
    "card_id": None,
    "card_created": False,
    "in_progress": False,
    "pr_created": False,
    "pr_number": None,
    "in_review": False,
    "in_done": False,
    "review_commented": False,
    "issues_found": [],
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

        await redis.close()
        test_state["redis_cleared"] = True
        return True

    except Exception as e:
        print_error(f"Failed to clear Redis: {e}")
        logger.error("Failed to clear Redis", error=str(e))
        return False


async def create_test_task():
    """Create a test Trello task."""
    print_section("STEP 2: CREATE TEST TASK IN TRELLO")

    logger = get_logger("create_task")
    trello = get_trello_client()

    print_info(f"Creating task: {TEST_TASK_NAME}")

    try:
        card_id = await trello.create_card(
            name=TEST_TASK_NAME,
            desc=TEST_TASK_DESC,
            labels=["P2"],
        )

        if card_id:
            test_state["card_id"] = card_id
            test_state["card_created"] = True
            print_success(f"Created Trello card: {card_id}")
            print_info(f"Card URL: https://trello.com/c/{card_id}")
            logger.info(f"✓ Created Trello card: {card_id[:8]}")
            return card_id
        else:
            print_error("Failed to create Trello card")
            return None

    except Exception as e:
        print_error(f"Failed to create Trello card: {e}")
        logger.error("Failed to create Trello card", error=str(e))
        return None


async def monitor_and_run_daemon(card_id: str, timeout_seconds: int = 900):
    """Start daemon and monitor task progress."""
    print_section("STEP 3: START DAEMON AND MONITOR WORKFLOW")

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
            test_state["issues_found"].append(f"Daemon crash: {str(e)}")
            shutdown_event.set()

    daemon_task = asyncio.create_task(run_daemon())

    # Monitor task progress
    print_info(f"Monitoring workflow (timeout: {timeout_seconds}s)...\n")

    start_time = datetime.now()
    check_interval = 10
    last_status = "TODO"
    check_count = 0

    workflow_stages = {
        "TODO": "Task created",
        "IN PROGRESS": "Agent picked up task",
        "REVIEW": "PR created, in review",
        "DONE": "PR reviewed and approved ✅",
    }

    try:
        while not shutdown_event.is_set():
            check_count += 1
            elapsed = (datetime.now() - start_time).total_seconds()

            # Check timeout
            if elapsed > timeout_seconds:
                print_warning(f"Timeout reached ({timeout_seconds}s)")
                break

            try:
                # Get current card status
                trello = get_trello_client()
                lists = await trello.get_lists()
                current_status = None

                for list_name, list_id in lists.items():
                    import httpx
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.get(
                            f"{trello._base_url}/lists/{list_id}/cards",
                            params=trello._auth_params,
                        )
                        response.raise_for_status()
                        cards = response.json()

                        for card in cards:
                            if card["id"] == card_id:
                                current_status = list_name.upper()

                                # Track state
                                if current_status == "IN PROGRESS":
                                    test_state["in_progress"] = True
                                elif current_status == "REVIEW":
                                    test_state["in_review"] = True
                                    # Try to get PR URL
                                    try:
                                        actions_response = await client.get(
                                            f"{trello._base_url}/cards/{card_id}/actions",
                                            params={
                                                **trello._auth_params,
                                                "filter": "commentCard",
                                            },
                                        )
                                        actions_response.raise_for_status()
                                        actions = actions_response.json()

                                        for action in reversed(actions):
                                            comment_text = action.get("data", {}).get("text", "")
                                            if "PR #" in comment_text or "pr_url" in comment_text:
                                                import re
                                                pr_match = re.search(r'#(\d+)', comment_text)
                                                if pr_match:
                                                    test_state["pr_number"] = int(pr_match.group(1))
                                                    test_state["pr_created"] = True
                                    except Exception:
                                        pass
                                elif current_status == "DONE":
                                    test_state["in_done"] = True

                                break

                    if current_status:
                        break

                # Status change detected
                if current_status and current_status != last_status:
                    elapsed_str = str(elapsed).split(".")[0]
                    stage_desc = workflow_stages.get(current_status, current_status)
                    print_success(f"[{elapsed_str}] {last_status} → {current_status}")
                    print_info(f"Stage: {stage_desc}")
                    logger.info(f"Status: {last_status} → {current_status}")

                    last_status = current_status

                    # DONE - wait a bit for PR review then stop
                    if current_status == "DONE":
                        print_success(f"\n🎉 TASK COMPLETED!")
                        print_info("Waiting 30 seconds for PR review to finish...")
                        await asyncio.sleep(30)
                        shutdown_event.set()
                        break

                # Periodic update
                if check_count % 6 == 0:
                    elapsed_str = str(elapsed).split(".")[0]
                    current_stage = workflow_stages.get(last_status, last_status)
                    print_info(f"[{elapsed_str}] Status: {last_status} | {current_stage}")

            except Exception as e:
                logger.error("Error monitoring", error=str(e))
                test_state["issues_found"].append(f"Monitor error: {str(e)}")

            # Wait before next check
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


async def verify_pr_review(pr_number: int):
    """Verify PR review was completed."""
    print_section("STEP 4: VERIFY PR REVIEW")

    if not pr_number:
        print_error("No PR number found!")
        return False

    print_info(f"Checking PR #{pr_number} for review comments...")

    try:
        env = os.environ.copy()
        result = subprocess.run(
            ["gh", "pr", "view", str(pr_number), "--repo", "TheCurators/laptop-recommendation",
             "--json", "state,number,title"],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
            check=False
        )

        if result.returncode == 0:
            print_info(f"PR found: {result.stdout.strip()}")
            print_success(f"✅ PR #{pr_number} created")
            return True
        else:
            print_warning(f"Could not retrieve PR info")

    except Exception as e:
        print_warning(f"Error verifying PR: {e}")

    return test_state["pr_created"]


async def run_true_e2e_test():
    """Run true end-to-end test."""
    configure_logging()
    logger = get_logger("true_e2e_test")

    print_header("🚀 TRUE END-TO-END AUTONOMOUS TEST")
    print_info("This test validates the COMPLETE autonomous workflow:")
    print_info("  1. Clear Redis queue")
    print_info("  2. Start daemon")
    print_info("  3. Create test task")
    print_info("  4. Daemon picks up task automatically")
    print_info("  5. Task executes autonomously")
    print_info("  6. PR created automatically")
    print_info("  7. PR review runs automatically")
    print(f"{YELLOW}  8. Card moves to DONE when approved{RESET}\n")

    # Step 1: Clear Redis
    if not await clear_redis_queue():
        print_error("Failed to clear Redis queue")
        return 1

    # Step 2: Create task
    card_id = await create_test_task()
    if not card_id:
        print_error("Failed to create test task")
        return 1

    # Step 3: Run daemon and monitor
    success = await monitor_and_run_daemon(card_id, timeout_seconds=900)

    # Step 4: Verify PR
    if test_state.get("pr_number"):
        await verify_pr_review(test_state["pr_number"])

    # Final summary
    print_header("TRUE E2E TEST RESULTS")

    print(f"\n{BOLD}Workflow Stages:{RESET}\n")
    print(f"Redis cleared:       {GREEN}✓{RESET}" if test_state["redis_cleared"] else f"Redis cleared:       {RED}✗{RESET}")
    print(f"Daemon started:      {GREEN}✓{RESET}" if test_state["daemon_started"] else f"Daemon started:      {RED}✗{RESET}")
    print(f"Card created:        {GREEN}✓{RESET}" if test_state["card_created"] else f"Card created:        {RED}✗{RESET}")
    print(f"IN PROGRESS:         {GREEN}✓{RESET}" if test_state["in_progress"] else f"IN PROGRESS:         {RED}✗{RESET}")
    print(f"PR created:          {GREEN}✓{RESET}" if test_state["pr_created"] else f"PR created:          {RED}✗{RESET}")
    print(f"REVIEW:              {GREEN}✓{RESET}" if test_state["in_review"] else f"REVIEW:              {RED}✗{RESET}")
    print(f"DONE:                {GREEN}✓{RESET}" if test_state["in_done"] else f"DONE:                {RED}✗{RESET}")

    if test_state["pr_number"]:
        print(f"\n{BOLD}Artifacts:{RESET}\n")
        print(f"  • Trello card: https://trello.com/c/{card_id}")
        print(f"  • PR: https://github.com/TheCurators/laptop-recommendation/pull/{test_state['pr_number']}")

    if test_state["issues_found"]:
        print(f"\n{YELLOW}Issues found ({len(test_state['issues_found'])}):{RESET}")
        for issue in test_state["issues_found"]:
            print(f"  • {issue}")

    all_stages_passed = (
        test_state["redis_cleared"] and
        test_state["daemon_started"] and
        test_state["card_created"] and
        test_state["in_progress"] and
        test_state["pr_created"] and
        test_state["in_review"] and
        test_state["in_done"]
    )

    if all_stages_passed:
        print(f"\n{GREEN}{BOLD}🎉 COMPLETE SUCCESS!{RESET}")
        print(f"{GREEN}All workflow stages completed autonomously!{RESET}\n")
        print(f"{BOLD}{GREEN}✅ THE AUTONOMOUS WORKFLOW IS FULLY FUNCTIONAL!{RESET}\n")
        return 0
    else:
        print(f"\n{RED}{BOLD}⚠️ WORKFLOW INCOMPLETE{RESET}")
        print(f"{RED}Not all stages completed{RESET}\n")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_true_e2e_test())
    sys.exit(exit_code)
