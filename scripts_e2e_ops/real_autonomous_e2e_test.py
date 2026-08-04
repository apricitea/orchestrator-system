#!/usr/bin/env python3
"""
Real Autonomous E2E Test with Full Monitoring

This script:
1. Creates a test task in Trello
2. Starts the autonomous worker daemon
3. Monitors the complete execution
4. Captures all logs and issues
5. Stops when task completes or timeout

Run with: python3 real_autonomous_e2e_test.py
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
TEST_TASK_NAME = "[laptop-recommendation] [agent] P2: Add simple data validation utility"
TEST_TASK_DESC = """
Create a simple data validation utility for the laptop-recommendation project.

## Requirements:
1. Create a file called `utils/validator.py` in the project directory
2. Add a function called `validate_laptop_data(data)` that:
   - Validates laptop data structure
   - Checks required fields (brand, model, price, rating)
   - Validates data types (price should be float, rating should be 0-5)
   - Returns (is_valid: bool, errors: list[str])
3. Include proper documentation and type hints
4. Add a simple example in the `if __name__ == "__main__"` block

## Working Directory:
/home/ubuntu/projects/laptop-recommendation

## Priority:
P2 (Medium priority - for testing autonomous workflow)
"""

# Track state
test_state = {
    "card_id": None,
    "card_created": False,
    "daemon_started": False,
    "task_completed": False,
    "issues_found": [],
}


async def create_test_task():
    """Create a test Trello task."""
    print_section("STEP 1: CREATE TEST TASK IN TRELLO")

    logger = get_logger("create_task")
    trello = get_trello_client()

    if not trello.is_configured():
        print_error("Trello not configured!")
        return None

    print_info(f"Creating task: {TEST_TASK_NAME}")
    logger.info("Creating test Trello task...")

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


async def monitor_task_progress(card_id: str, timeout_seconds: int = 600):
    """Monitor task progress by polling Trello board."""
    print_section("STEP 2: MONITOR TASK PROGRESS")

    logger = get_logger("monitor")
    trello = get_trello_client()

    start_time = datetime.now()
    check_interval = 10  # Check every 10 seconds

    print_info(f"Monitoring task progress every {check_interval} seconds...")
    print_info(f"Timeout: {timeout_seconds} seconds")
    print(f"{YELLOW}Press Ctrl+C to stop monitoring early{RESET}\n")

    last_status = "TODO"
    check_count = 0

    while True:
        check_count += 1
        elapsed = (datetime.now() - start_time).total_seconds()

        # Check timeout
        if elapsed > timeout_seconds:
            print_warning(f"Timeout reached ({timeout_seconds}s)")
            logger.warning("Monitoring timeout reached")
            break

        try:
            # Get all cards in all lists
            lists = await trello.get_lists()
            current_status = None
            current_list_name = None

            for list_name, list_id in lists.items():
                # Get cards in this list
                import httpx
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(
                        f"{trello._base_url}/lists/{list_id}/cards",
                        params=trello._auth_params,
                    )
                    response.raise_for_status()
                    cards = response.json()

                    # Check if our test card is in this list
                    for card in cards:
                        if card["id"] == card_id:
                            current_status = list_name.upper()
                            current_list_name = list_name
                            break

                    if current_status:
                        break

            # Status change detected
            if current_status and current_status != last_status:
                elapsed_str = str(elapsed).split(".")[0]
                print_success(f"[{elapsed_str}] Status changed: {last_status} → {current_status}")
                logger.info(f"Status changed: {last_status} → {current_status}")

                last_status = current_status

                # Check if task completed
                if current_status in ["REVIEW", "DONE"]:
                    print_success(f"\n🎉 TASK COMPLETED! Status: {current_status}")
                    test_state["task_completed"] = True

                    # Get PR URL from card comments
                    try:
                        async with httpx.AsyncClient(timeout=30.0) as client:
                            response = await client.get(
                                f"{trello._base_url}/cards/{card_id}/actions",
                                params={
                                    **trello._auth_params,
                                    "filter": "commentCard",
                                },
                            )
                            response.raise_for_status()
                            actions = response.json()

                            # Find PR URL in comments
                            for action in reversed(actions):
                                comment_text = action.get("data", {}).get("text", "")
                                if "pr_url" in comment_text or "PR #" in comment_text:
                                    print_info(f"PR Info found in comments:")
                                    print(f"  {comment_text[:200]}...")

                    except Exception as e:
                        logger.warning("Could not get PR info from comments", error=str(e))

                    return True

            # Periodic status update
            if check_count % 6 == 0:  # Every minute
                elapsed_str = str(elapsed).split(".")[0]
                print_info(f"[{elapsed_str}] Status: {last_status} | Still monitoring...")

        except Exception as e:
            logger.error("Error monitoring task", error=str(e))
            test_state["issues_found"].append(f"Monitor error: {str(e)}")

        # Wait before next check
        await asyncio.sleep(check_interval)

    return False


async def run_daemon_with_monitoring(timeout_seconds: int = 600):
    """Run the daemon with monitoring."""
    print_section("STEP 3: START AUTONOMOUS DAEMON")

    logger = get_logger("daemon_runner")

    print_info("Initializing WorkerDaemon...")
    daemon = WorkerDaemon()
    shutdown_event = asyncio.Event()

    # Setup signal handlers
    def signal_handler(signum, frame):
        logger.info("Received signal, stopping daemon...")
        print_warning("\nReceived stop signal, shutting down...")
        shutdown_event.set()
        asyncio.create_task(daemon.stop())

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Start monitoring in background
    if test_state["card_id"]:
        monitor_task = asyncio.create_task(
            monitor_task_progress(test_state["card_id"], timeout_seconds)
        )
    else:
        print_error("No card ID to monitor!")
        return False

    # Start daemon in background
    print_info("Starting daemon in background...")
    test_state["daemon_started"] = True

    async def run_daemon():
        try:
            await daemon.start()
        except Exception as e:
            logger.error(f"Daemon crashed: {e}")
            test_state["issues_found"].append(f"Daemon crash: {str(e)}")
            shutdown_event.set()

    daemon_task = asyncio.create_task(run_daemon())

    # Wait for either monitor to complete or timeout
    try:
        await asyncio.wait_for(monitor_task, timeout=timeout_seconds)
        print_success("Monitor completed (task finished or timeout)")
    except asyncio.TimeoutError:
        print_warning(f"Monitoring timed out after {timeout_seconds}s")
    finally:
        # Stop daemon
        print_info("Stopping daemon...")
        shutdown_event.set()
        try:
            await asyncio.wait_for(daemon.stop(), timeout=30)
        except asyncio.TimeoutError:
            print_warning("Daemon stop timed out")
        except Exception as e:
            test_state["issues_found"].append(f"Daemon stop error: {str(e)}")

    # Cancel daemon task
        daemon_task.cancel()
        try:
            await daemon_task
        except asyncio.CancelledError:
            pass

    return test_state["task_completed"]


async def check_system_health():
    """Check system health before starting test."""
    print_section("SYSTEM HEALTH CHECK")

    logger = get_logger("health_check")

    checks = []

    # Check 1: Environment variables
    print_info("Checking environment variables...")
    required_vars = ["ANTHROPIC_API_KEY", "GITHUB_TOKEN", "TRELLO_API_KEY", "TRELLO_TOKEN"]
    all_present = True
    for var in required_vars:
        present = var in os.environ and os.environ[var]
        status = f"{GREEN}✓{RESET}" if present else f"{RED}✗{RESET}"
        print(f"  {status} {var}")
        if not present:
            all_present = False

    checks.append(("Environment variables", all_present))

    # Check 2: Redis connection
    print_info("\nChecking Redis connection...")
    try:
        from redis.asyncio import Redis
        redis = Redis(host="localhost", port=6379, db=0)
        await redis.ping()
        await redis.close()
        print_success("Redis connection: OK")
        checks.append(("Redis", True))
    except Exception as e:
        print_error(f"Redis connection: FAILED - {e}")
        checks.append(("Redis", False))

    # Check 3: Trello connection
    print_info("\nChecking Trello connection...")
    try:
        trello = get_trello_client()
        lists = await trello.get_lists()
        print_success(f"Trello connection: OK ({len(lists)} lists)")
        checks.append(("Trello", True))
    except Exception as e:
        print_error(f"Trello connection: FAILED - {e}")
        checks.append(("Trello", False))

    # Check 4: GitHub connection
    print_info("\nChecking GitHub connection...")
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if "Logged in" in result.stdout:
            print_success("GitHub connection: OK")
            checks.append(("GitHub", True))
        else:
            print_error(f"GitHub connection: FAILED - {result.stdout}")
            checks.append(("GitHub", False))
    except Exception as e:
        print_error(f"GitHub connection: FAILED - {e}")
        checks.append(("GitHub", False))

    # Summary
    print_info("\n" + "="*50)
    all_passed = all(passed for _, passed in checks)
    for check_name, passed in checks:
        status = f"{GREEN}✓{RESET}" if passed else f"{RED}✗{RESET}"
        print(f"{status} {check_name}")

    if all_passed:
        print_success("\n🎉 All health checks passed!")
        return True
    else:
        print_error("\n⚠️ Some health checks failed!")
        failed = [name for name, passed in checks if not passed]
        print_warning(f"Failed checks: {', '.join(failed)}")
        return False


async def main():
    """Main entry point."""
    configure_logging()
    logger = get_logger("main")

    print_header("🚀 REAL AUTONOMOUS E2E TEST")
    print_info("This test will:")
    print_info("  1. Check system health")
    print_info("  2. Create a test task in Trello")
    print_info("  3. Start the autonomous worker daemon")
    print_info("  4. Monitor task execution")
    print_info("  5. Capture all logs and issues")
    print(f"{YELLOW}  6. Stop when task completes or timeout{RESET}\n")

    # Step 1: Health check
    health_ok = await check_system_health()
    if not health_ok:
        print_error("\n⚠️ System health check failed!")
        print_warning("You can continue, but some features may not work.")
        response = input("Continue anyway? (y/N): ")
        if response.lower() != 'y':
            return 1

    # Step 2: Create test task
    card_id = await create_test_task()
    if not card_id:
        print_error("\n❌ Failed to create test task, aborting...")
        return 1

    # Step 3: Run daemon with monitoring
    print_header("STARTING AUTONOMOUS TEST")
    print_info("The daemon will now:")
    print_info("  • Pick up the task from Trello")
    print_info("  • Move card to IN PROGRESS")
    print_info("  • Execute the task (create validator.py)")
    print_info("  • Create a PR")
    print_info("  • Run PR review")
    print_info("  • Move card to REVIEW")
    print_info(f"{YELLOW}  • Send notifications{RESET}\n")

    timeout_seconds = 600  # 10 minutes
    print_info(f"Timeout: {timeout_seconds} seconds (10 minutes)")
    print_warning("This will take several minutes...\n")

    try:
        success = await run_daemon_with_monitoring(timeout_seconds)

        # Final summary
        print_header("TEST SUMMARY")

        print(f"\n{BOLD}Results:{RESET}\n")
        print(f"Card created: {GREEN}✓{RESET}" if test_state["card_created"] else f"Card created: {RED}✗{RESET}")
        print(f"Daemon started: {GREEN}✓{RESET}" if test_state["daemon_started"] else f"Daemon started: {RED}✗{RESET}")
        print(f"Task completed: {GREEN}✓{RESET}" if test_state["task_completed"] else f"Task completed: {RED}✗{RESET}")

        if test_state["issues_found"]:
            print(f"\n{YELLOW}Issues found ({len(test_state['issues_found'])}):{RESET}")
            for issue in test_state["issues_found"]:
                print(f"  • {issue}")

        if test_state["task_completed"]:
            print(f"\n{GREEN}{BOLD}🎉 TEST PASSED!{RESET}")
            print(f"{GREEN}Autonomous workflow is working!{RESET}\n")
            print_info("Artifacts:")
            print(f"  • Trello card: https://trello.com/c/{card_id}")
            return 0
        else:
            print(f"\n{RED}{BOLD}⚠️ TEST INCOMPLETE{RESET}")
            print(f"{RED}Task did not complete within timeout{RESET}\n")
            return 1

    except KeyboardInterrupt:
        print_warning("\n\nTest interrupted by user")
        return 1
    except Exception as e:
        print_error(f"\nTest failed with exception: {e}")
        logger.error("Test failed", error=str(e))
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
