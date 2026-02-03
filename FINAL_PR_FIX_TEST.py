#!/usr/bin/env python3
"""
FINAL End-to-End Test - All Fixes Applied

This test validates ALL fixes:
1. PR Title Fix - Uses original_task instead of subtask
2. Test Coverage Fix - Shows 0% instead of N/A
3. Complete workflow - TODO → IN PROGRESS → REVIEW → DONE
"""

import asyncio
import os
import sys
import signal
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

configure_logging()
logger = get_logger("final_e2e_test")

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

def print_success(text):
    print(f"{GREEN}✅ {text}{RESET}")

def print_error(text):
    print(f"{RED}❌ {text}{RESET}")

def print_info(text):
    print(f"{BLUE}ℹ️  {text}{RESET}")

# Test task
TEST_TASK_NAME = "[laptop-recommendation] [agent] P2: Add password strength checker"
TEST_TASK_DESC = """
Create a password strength checker utility for the laptop-recommendation project.

## Requirements:
1. Create a file called `utils/password_checker.py`
2. Add a function:
   - check_password_strength(password: str) -> dict
   - Returns: {"strength": "weak|medium|strong", "score": 0-100}
3. Include proper documentation and type hints
4. Add example in `if __name__ == "__main__"` block

## Working Directory:
/home/ubuntu/projects/laptop-recommendation

## Priority:
P2 (Final test for all PR fixes)
"""

# Track state
test_state = {
    "card_id": None,
    "card_created": False,
    "in_progress": False,
    "pr_created": False,
    "pr_number": None,
    "pr_title": None,
    "in_review": False,
    "in_done": False,
    "pr_reviewed": False,
    "test_coverage": None,
    "fixes_working": {
        "pr_title": False,
        "test_coverage": False,
        "workflow": False,
    },
}

async def create_test_task():
    """Create test task in Trello."""
    print_header("STEP 1: CREATE TEST TASK")
    trello = get_trello_client()

    print_info(f"Creating task: {TEST_TASK_NAME}")

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
        return card_id
    else:
        print_error("Failed to create Trello card")
        return None

async def monitor_and_test():
    """Monitor task and validate all fixes."""
    print_header("STEP 2: START DAEMON AND MONITOR WORKFLOW")

    shutdown_event = asyncio.Event()

    # Start daemon
    print_info("Starting WorkerDaemon...")
    daemon = WorkerDaemon()

    def signal_handler(signum, frame):
        print_info("\nStopping...")
        shutdown_event.set()
        asyncio.create_task(daemon.stop())

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    async def run_daemon():
        try:
            await daemon.start()
        except Exception as e:
            print_error(f"Daemon crashed: {e}")
            shutdown_event.set()

    daemon_task = asyncio.create_task(run_daemon())

    # Monitor
    card_id = test_state["card_id"]
    print_info(f"Monitoring task {card_id[:8]}...\n")
    start_time = datetime.now()
    check_interval = 15

    workflow_stages = {
        "TODO": "Task created",
        "IN PROGRESS": "Agent picked up task",
        "REVIEW": "PR created, in review",
        "DONE": "PR reviewed and approved ✅",
    }

    try:
        while not shutdown_event.is_set():
            elapsed = (datetime.now() - start_time).total_seconds()

            if elapsed > 900:  # 15 min timeout
                print_warning("Timeout reached")
                break

            try:
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

                                if current_status == "IN PROGRESS":
                                    test_state["in_progress"] = True
                                elif current_status == "REVIEW":
                                    test_state["in_review"] = True

                                    # Get PR number
                                    if not test_state["pr_number"]:
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
                                            if "PR #" in comment_text:
                                                import re
                                                pr_match = re.search(r'#(\d+)', comment_text)
                                                if pr_match:
                                                    test_state["pr_number"] = int(pr_match.group(1))
                                                    print_success(f"PR #{test_state['pr_number']} created")

                                                    # === FIX 1: Check PR Title ===
                                                    import subprocess
                                                    result = subprocess.run([
                                                        'gh', 'pr', 'view', str(test_state['pr_number']),
                                                        '--repo', 'TheCurators/laptop-recommendation',
                                                        '--json', 'title'
                                                    ], env=os.environ, capture_output=True, text=True)

                                                    if result.returncode == 0:
                                                        import json
                                                        pr_data = json.loads(result.stdout)
                                                        test_state["pr_title"] = pr_data.get("title", "")

                                                        print(f"\n{BOLD}PR Title:{RESET}")
                                                        print(f"  {test_state['pr_title']}")

                                                        # Check if title contains expected keywords
                                                        title_lower = test_state["pr_title"].lower()
                                                        expected_keywords = ["password", "strength", "checker"]
                                                        wrong_patterns = ["checklist", "template", "security checklist"]

                                                        has_expected = any(kw in title_lower for kw in expected_keywords)
                                                        has_wrong = any(wrong in title_lower for wrong in wrong_patterns)

                                                        if has_expected and not has_wrong:
                                                            print_success("FIX 1: PR Title is CORRECT! ✅")
                                                            test_state["fixes_working"]["pr_title"] = True
                                                        else:
                                                            print_error("FIX 1: PR Title is WRONG ❌")
                                                            print_error(f"  Expected keywords: {expected_keywords}")

                                elif current_status == "DONE":
                                    test_state["in_done"] = True
                                    test_state["fixes_working"]["workflow"] = True
                                    print_success("\nFIX 3: Workflow completed - Card moved to DONE! ✅")

                                break

                    if current_status:
                        break

                # Status change
                if current_status:
                    elapsed_str = str(int(elapsed))
                    stage_desc = workflow_stages.get(current_status, current_status)
                    print_info(f"[{elapsed_str}s] {current_status}")

                    # DONE - check PR review
                    if current_status == "DONE" and not test_state["pr_reviewed"]:
                        print_success("Task completed, checking PR review...")

                        if test_state["pr_number"]:
                            # Get PR review comments
                            comments_result = await asyncio.create_subprocess_exec(
                                "gh", "pr", "comments", str(test_state["pr_number"]),
                                "--repo", "TheCurators/laptop-recommendation",
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE,
                            )
                            c_stdout, c_stderr = await comments_result.communicate()

                            if comments_result.returncode == 0:
                                comments = c_stdout.decode()

                                # === FIX 2: Check Test Coverage ===
                                print(f"\n{BOLD}Checking Test Coverage...{RESET}")

                                if "Test Coverage:" in comments:
                                    import re
                                    cov_match = re.search(r'Test Coverage:\s*(\d+(?:\.\d+)?)%', comments)
                                    if cov_match:
                                        coverage = cov_match.group(1)
                                        test_state["test_coverage"] = coverage
                                        print(f"  Test Coverage: {coverage}%")

                                        if coverage != "N/A":
                                            print_success("FIX 2: Test Coverage shows percentage (not N/A)! ✅")
                                            test_state["fixes_working"]["test_coverage"] = True
                                        else:
                                            print_error("FIX 2: Test Coverage still shows N/A ❌")
                                    else:
                                        print_error("Could not parse coverage value")
                                else:
                                    print_warning("Test Coverage not found in comments")

                                test_state["pr_reviewed"] = True

                        await asyncio.sleep(10)
                        shutdown_event.set()
                        break

                await asyncio.sleep(check_interval)

            except Exception as e:
                logger.error("Monitor error", error=str(e))

    finally:
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
    """Run final comprehensive test."""
    print_header("🚀 FINAL END-TO-END TEST - ALL FIXES")
    print_info("This test validates:")
    print_info("  FIX 1: PR Title uses original_task (not subtask)")
    print_info("  FIX 2: Test Coverage shows % (not N/A)")
    print(f"  FIX 3: Complete workflow TODO → IN PROGRESS → REVIEW → DONE{RESET}\n")

    # Step 1: Create task
    card_id = await create_test_task()
    if not card_id:
        return 1

    # Step 2: Monitor and test
    await monitor_and_test()

    # Final summary
    print_header("FINAL TEST RESULTS")

    print(f"\n{BOLD}Workflow Stages:{RESET}\n")
    print(f"Card created:     {GREEN}✓{RESET}" if test_state["card_created"] else f"Card created:     {RED}✗{RESET}")
    print(f"IN PROGRESS:      {GREEN}✓{RESET}" if test_state["in_progress"] else f"IN PROGRESS:      {RED}✗{RESET}")
    print(f"PR created:       {GREEN}✓{RESET}" if test_state["pr_created"] else f"PR created:       {RED}✗{RESET}")
    print(f"REVIEW:           {GREEN}✓{RESET}" if test_state["in_review"] else f"REVIEW:           {RED}✗{RESET}")
    print(f"DONE:             {GREEN}✓{RESET}" if test_state["in_done"] else f"DONE:             {RED}✗{RESET}")

    print(f"\n{BOLD}Fixes Validated:{RESET}\n")
    print(f"FIX 1 - PR Title:           {GREEN}✓ WORKING{RESET}" if test_state["fixes_working"]["pr_title"] else f"FIX 1 - PR Title:           {RED}✗ FAILED{RESET}")
    print(f"FIX 2 - Test Coverage:      {GREEN}✓ WORKING{RESET}" if test_state["fixes_working"]["test_coverage"] else f"FIX 2 - Test Coverage:      {RED}✗ FAILED{RESET}")
    print(f"FIX 3 - Workflow:           {GREEN}✓ WORKING{RESET}" if test_state["fixes_working"]["workflow"] else f"FIX 3 - Workflow:           {RED}✗ FAILED{RESET}")

    if test_state["pr_title"]:
        print(f"\n{BOLD}PR Details:{RESET}\n")
        print(f"  PR Number: #{test_state['pr_number']}")
        print(f"  PR Title: {test_state['pr_title']}")

    all_fixes_working = all(test_state["fixes_working"].values())

    if all_fixes_working:
        print(f"\n{GREEN}{BOLD}🎉 ALL FIXES VALIDATED!{RESET}")
        print(f"{GREEN}All PR process fixes are working correctly!{RESET}\n")
        return 0
    else:
        print(f"\n{RED}{BOLD}⚠️ SOME FIXES FAILED{RESET}\n")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(run_final_test())
    sys.exit(exit_code)
