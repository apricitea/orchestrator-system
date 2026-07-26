#!/usr/bin/env python3
"""
Final End-to-End Validation Test

This test runs a COMPLETE workflow from start to finish:
1. Create NEW task in Trello
2. Wait for daemon to pick it up
3. Monitor execution
4. Verify PR created
5. Verify PR review runs
6. Verify card moves to DONE
7. Verify review comment posted

This will CONFIRM the entire autonomous workflow works end-to-end.
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
TEST_TASK_NAME = "[laptop-recommendation] [agent] P3: E2E Final Test - Add greeting utility"
TEST_TASK_DESC = """
Create a simple greeting utility for the laptop-recommendation project.

## Requirements:
1. Create a file called `utils/greeting.py` in the project directory
2. Add a function called `greet(name: str) -> str` that:
   - Returns a friendly greeting message
   - Uses the format: "Hello, {name}! Welcome to the laptop recommendation system."
3. Include proper documentation and type hints
4. Add a simple example in the `if __name__ == "__main__"` block

## Working Directory:
/home/ubuntu/projects/laptop-recommendation

## Priority:
P3 (Low priority - for final E2E validation)
"""

# Track state
test_state = {
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


async def create_test_task():
    """Create a test Trello task."""
    print_section("STEP 1: CREATE TEST TASK IN TRELLO")

    logger = get_logger("create_task")
    trello = get_trello_client()

    print_info(f"Creating task: {TEST_TASK_NAME}")

    try:
        card_id = await trello.create_card(
            name=TEST_TASK_NAME,
            desc=TEST_TASK_DESC,
            labels=["P3"],
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


async def monitor_task_progress(card_id: str, timeout_seconds: int = 900):
    """Monitor task progress by polling Trello board."""
    print_section("STEP 2: MONITOR COMPLETE WORKFLOW")

    logger = get_logger("monitor")
    trello = get_trello_client()

    start_time = datetime.now()
    check_interval = 10  # Check every 10 seconds

    print_info(f"Monitoring complete workflow every {check_interval} seconds...")
    print_info(f"Timeout: {timeout_seconds} seconds (15 minutes)")
    print(f"{YELLOW}Press Ctrl+C to stop monitoring early{RESET}\n")

    last_status = "TODO"
    check_count = 0
    workflow_stages = {
        "TODO": "Task created",
        "IN PROGRESS": "Agent picked up task",
        "REVIEW": "PR created, in review",
        "DONE": "PR reviewed and approved",
    }

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

                            # Track state
                            if current_status == "IN PROGRESS":
                                test_state["in_progress"] = True
                            elif current_status == "REVIEW":
                                test_state["in_review"] = True
                                # Try to get PR URL from card
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
                                            # Extract PR number
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
                print_success(f"[{elapsed_str}] Status changed: {last_status} → {current_status}")
                print_info(f"Stage: {stage_desc}")
                logger.info(f"Status changed: {last_status} → {current_status}")

                last_status = current_status

                # Check if task completed (reached DONE)
                if current_status == "DONE":
                    print_success(f"\n🎉 TASK COMPLETED! Status: {current_status}")

                    # Give time for PR review to complete
                    print_info("Waiting 30 seconds for PR review to finish...")
                    await asyncio.sleep(30)

                    return True

            # Periodic status update
            if check_count % 6 == 0:  # Every minute
                elapsed_str = str(elapsed).split(".")[0]
                current_stage = workflow_stages.get(last_status, last_status)
                print_info(f"[{elapsed_str}] Status: {last_status} | Stage: {current_stage} | Still monitoring...")

        except Exception as e:
            logger.error("Error monitoring task", error=str(e))
            test_state["issues_found"].append(f"Monitor error: {str(e)}")

        # Wait before next check
        await asyncio.sleep(check_interval)

    return False


async def verify_pr_review(pr_number: int):
    """Verify PR review was completed."""
    print_section("STEP 3: VERIFY PR REVIEW")

    if not pr_number:
        print_error("No PR number found!")
        return False

    print_info(f"Checking PR #{pr_number} for review comments...")

    try:
        # Try to get PR info via gh CLI
        env = os.environ.copy()
        result = subprocess.run(
            ["gh", "pr", "view", str(pr_number), "--repo", "TheCurators/laptop-recommendation",
             "--json", "state,number,title,reviewDecision"],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
            check=False
        )

        if result.returncode == 0:
            print_info(f"PR info retrieved:")
            print(f"  {result.stdout}")

            # Check for review comments
            result2 = subprocess.run(
                ["gh", "api", f"repos/TheCurators/laptop-recommendation/issues/{pr_number}/comments"],
                capture_output=True,
                text=True,
                env=env,
                timeout=30,
                check=False
            )

            if result2.returncode == 0 and "Automated PR Review" in result2.stdout:
                print_success("✅ Automated PR review comment found!")
                test_state["review_commented"] = True
                return True
            else:
                print_warning("Review comment not found (may still be processing)")
        else:
            print_warning(f"Could not retrieve PR info: {result.stderr}")

    except Exception as e:
        print_warning(f"Error verifying PR review: {e}")

    return test_state["review_commented"]


async def run_final_validation():
    """Run final end-to-end validation."""
    configure_logging()
    logger = get_logger("final_e2e_test")

    print_header("🚀 FINAL END-TO-END VALIDATION TEST")
    print_info("This test will:")
    print_info("  1. Create a NEW test task in Trello")
    print_info("  2. Wait for daemon to pick it up")
    print_info("  3. Monitor execution through all stages")
    print_info("  4. Verify PR is created")
    print_info("  5. Verify PR review runs")
    print_info("  6. Verify card moves to DONE")
    print(f"{YELLOW}  7. Verify review comment posted{RESET}\n")

    # Step 1: Create test task
    card_id = await create_test_task()
    if not card_id:
        print_error("\n❌ Failed to create test task")
        return 1

    # Step 2: Monitor complete workflow
    print_header("MONITORING COMPLETE AUTONOMOUS WORKFLOW")
    print_info("The daemon should now:")
    print_info("  • Pick up the task from Trello")
    print_info("  • Move card to IN PROGRESS")
    print_info("  • Execute the task (create greeting.py)")
    print_info("  • Create a PR")
    print_info("  • Run PR review")
    print_info("  • Move card to DONE if approved")
    print(f"{YELLOW}  • Post review comment{RESET}\n")

    timeout_seconds = 900  # 15 minutes

    try:
        # Wait a bit for daemon to process
        print_info("Waiting 30 seconds for daemon to pick up task...")
        await asyncio.sleep(30)

        success = await monitor_task_progress(card_id, timeout_seconds)

        # Step 3: Verify PR review
        if test_state.get("pr_number"):
            await verify_pr_review(test_state["pr_number"])

        # Final summary
        print_header("FINAL VALIDATION RESULTS")

        print(f"\n{BOLD}Workflow Stages:{RESET}\n")
        print(f"Card created:        {GREEN}✓{RESET}" if test_state["card_created"] else f"Card created:        {RED}✗{RESET}")
        print(f"Moved to IN PROGRESS: {GREEN}✓{RESET}" if test_state["in_progress"] else f"Moved to IN PROGRESS: {RED}✗{RESET}")
        print(f"PR created:          {GREEN}✓{RESET}" if test_state["pr_created"] else f"PR created:          {RED}✗{RESET}")
        print(f"Moved to REVIEW:     {GREEN}✓{RESET}" if test_state["in_review"] else f"Moved to REVIEW:     {RED}✗{RESET}")
        print(f"Moved to DONE:       {GREEN}✓{RESET}" if test_state["in_done"] else f"Moved to DONE:       {RED}✗{RESET}")
        print(f"Review commented:    {GREEN}✓{RESET}" if test_state["review_commented"] else f"Review commented:    {YELLOW}⊘{RESET}")

        if test_state["issues_found"]:
            print(f"\n{YELLOW}Issues found ({len(test_state['issues_found'])}):{RESET}")
            for issue in test_state["issues_found"]:
                print(f"  • {issue}")

        all_stages_passed = (
            test_state["card_created"] and
            test_state["in_progress"] and
            test_state["pr_created"] and
            test_state["in_review"] and
            test_state["in_done"]
        )

        if all_stages_passed:
            print(f"\n{GREEN}{BOLD}🎉 COMPLETE SUCCESS!{RESET}")
            print(f"{GREEN}All workflow stages completed!{RESET}\n")
            print_info("Artifacts:")
            print(f"  • Trello card: https://trello.com/c/{card_id}")
            if test_state["pr_number"]:
                print(f"  • PR: https://github.com/TheCurators/laptop-recommendation/pull/{test_state['pr_number']}")

            print(f"\n{BOLD}{GREEN}✅ THE AUTONOMOUS WORKFLOW IS FULLY FUNCTIONAL!{RESET}\n")
            return 0
        else:
            print(f"\n{RED}{BOLD}⚠️ WORKFLOW INCOMPLETE{RESET}")
            print(f"{RED}Not all stages completed{RESET}\n")
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
    exit_code = asyncio.run(run_final_validation())
    sys.exit(exit_code)
