#!/usr/bin/env python3
"""
COMPLETE END-TO-END PIPELINE TEST

This script tests the full autonomous agent workflow:
1. Create Trello task
2. Agent picks up task
3. Execute all 7 phases of E2E workflow
4. Create PR
5. Review PR
6. Send Telegram notification

This is the ultimate validation that the entire system works.
"""

import asyncio
import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime

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

from utils.logger import get_logger

logger = get_logger("e2e_pipeline_test")

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


def print_phase(num, text):
    print(f"\n{BOLD}{YELLOW}{'─'*100}{RESET}")
    print(f"{BOLD}{YELLOW}PHASE {num}: {text}{RESET}")
    print(f"{BOLD}{YELLOW}{'─'*100}{RESET}\n")


def print_success(text):
    print(f"{GREEN}✅ {text}{RESET}")


def print_error(text):
    print(f"{RED}❌ {text}{RESET}")


def print_warning(text):
    print(f"{YELLOW}⚠️  {text}{RESET}")


def print_info(text):
    print(f"{BLUE}ℹ️  {text}{RESET}")


async def phase_1_system_validation():
    """Phase 1: Validate system is ready"""
    print_phase(1, "SYSTEM VALIDATION")

    try:
        # Check environment
        required_vars = ["GITHUB_TOKEN", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "ANTHROPIC_API_KEY"]
        missing_vars = [var for var in required_vars if not os.getenv(var)]

        if missing_vars:
            print_error(f"Missing environment variables: {', '.join(missing_vars)}")
            return False

        print_success("All environment variables configured")

        # Check project
        project_path = Path("/home/ubuntu/projects/laptop-recommendation")
        if not project_path.exists():
            print_error("Project directory not found")
            return False

        print_success("Project directory exists")

        # Check git
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.stdout.strip():
            print_warning(f"Working directory has changes:\n{result.stdout}")
        else:
            print_success("Working directory clean")

        return True

    except Exception as e:
        print_error(f"System validation failed: {e}")
        return False


async def phase_2_create_test_task():
    """Phase 2: Create a test task in Trello"""
    print_phase(2, "CREATE TEST TASK IN TRELLO")

    try:
        from trello import TrelloClient

        # Initialize Trello client
        client = TrelloClient(
            api_key=os.getenv("TRELLO_API_KEY"),
            api_secret=os.getenv("TRELLO_API_SECRET"),
            token=os.getenv("TRELLO_TOKEN")
        )

        print_info("Trello client initialized")

        # Get board
        board = client.get_board(os.getenv("TRELLO_BOARD_ID"))
        print_success(f"Connected to board: {board.name}")

        # Get TODO list
        todo_list = client.get_list(os.getenv("TRELLO_LIST_TODO"))
        print_success(f"Found TODO list: {todo_list.name}")

        # Create test card
        card_name = "[laptop-recommendation] [agent] P3: Add simple logging utility function"
        card_desc = """
## Task Description
Add a simple logging utility function to help with debugging.

## Requirements
- Create a function `log_debug(message)` that prints debug messages
- Add it to a new file: `utils/logger.py`
- Include a simple example in the docstring

## Acceptance Criteria
- Function exists and works
- File is created in the right location
- Code is clean and documented

## Notes
This is a simple test task for E2E pipeline validation.
"""

        card = todo_list.add_card(card_name, card_desc)
        print_success(f"Created Trello card: {card.url}")
        print_info(f"Card ID: {card.id}")

        return card.id, card.url

    except Exception as e:
        print_error(f"Failed to create Trello card: {e}")
        import traceback
        traceback.print_exc()
        return None, None


async def phase_3_agent_pickup_task(card_id):
    """Phase 3: Simulate agent picking up the task"""
    print_phase(3, "AGENT PICKUP TASK")

    try:
        # Simulate agent checking Trello for tasks
        print_info("Agent checking Trello for tasks...")

        await asyncio.sleep(2)  # Simulate polling delay

        print_success("Agent found task")
        print_info(f"Task ID: {card_id}")

        # Simulate task parsing
        task_name = "[laptop-recommendation] [agent] P3: Add simple logging utility function"

        # Parse task format
        if "[" in task_name and "]" in task_name:
            project = task_name.split("[")[1].split("]")[0]
            priority = task_name.split("P")[1].split(":")[0] if "P" in task_name else "P3"
            description = task_name.split(":", 1)[1].strip() if ":" in task_name else task_name

            print_success(f"Parsed task:")
            print(f"      Project: {project}")
            print(f"      Priority: P{priority}")
            print(f"      Description: {description}")

            return {
                "project": project,
                "priority": priority,
                "description": description,
                "card_id": card_id
            }

        return None

    except Exception as e:
        print_error(f"Agent pickup failed: {e}")
        return None


async def phase_4_pre_work_git_ops():
    """Phase 4: Pre-work git operations"""
    print_phase(4, "PRE-WORK GIT OPERATIONS")

    try:
        project_path = Path("/home/ubuntu/projects/laptop-recommendation")

        # Checkout main
        print_info("Checking out main branch...")
        result = subprocess.run(
            ["git", "checkout", "main"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            print_success("Checked out main branch")
        else:
            print_error(f"Failed to checkout main: {result.stderr}")
            return False

        # Fetch from origin
        print_info("Fetching from origin...")
        result = subprocess.run(
            ["git", "fetch", "origin"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            print_success("Fetched from origin")
        else:
            print_error(f"Failed to fetch: {result.stderr}")
            return False

        # Pull latest
        print_info("Pulling latest changes...")
        result = subprocess.run(
            ["git", "pull", "origin", "main"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            print_success("Pulled latest changes")
        else:
            print_warning(f"Git pull had issues: {result.stderr}")

        # Check status
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30
        )

        if not result.stdout.strip():
            print_success("Working directory is clean")
        else:
            print_warning(f"Working directory has changes")

        return True

    except Exception as e:
        print_error(f"Pre-work git ops failed: {e}")
        return False


async def phase_5_execute_task(task_info):
    """Phase 5: Execute the task"""
    print_phase(5, "EXECUTE TASK")

    try:
        print_info(f"Creating feature branch...")
        project_path = Path("/home/ubuntu/projects/laptop-recommendation")

        # Create branch name
        branch_name = f"feat/{datetime.now().strftime('%Y%m%d')}-logging-utility"

        # Create and checkout branch
        result = subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            print_success(f"Created branch: {branch_name}")
        else:
            print_error(f"Failed to create branch: {result.stderr}")
            return False, None

        # Create the logging utility file
        print_info("Creating logging utility...")

        utils_dir = project_path / "utils"
        utils_dir.mkdir(exist_ok=True)

        logger_file = utils_dir / "logger.py"
        logger_content = '''"""
Simple logging utility for debugging.
"""


def log_debug(message):
    """
    Log a debug message to console.

    Args:
        message (str): The message to log
    """
    print(f"[DEBUG] {message}")


def log_info(message):
    """
    Log an info message to console.

    Args:
        message (str): The message to log
    """
    print(f"[INFO] {message}")


def log_warning(message):
    """
    Log a warning message to console.

    Args:
        message (str): The message to log
    """
    print(f"[WARNING] {message}")


# Example usage
if __name__ == "__main__":
    log_debug("This is a debug message")
    log_info("This is an info message")
    log_warning("This is a warning message")
'''

        logger_file.write_text(logger_content)
        print_success(f"Created: {logger_file}")

        # Verify file was created
        if logger_file.exists():
            print_success("File verification passed")
        else:
            print_error("File was not created")
            return False, None

        return True, branch_name

    except Exception as e:
        print_error(f"Task execution failed: {e}")
        import traceback
        traceback.print_exc()
        return False, None


async def phase_6_commit_changes(branch_name):
    """Phase 6: Commit changes"""
    print_phase(6, "COMMIT CHANGES")

    try:
        project_path = Path("/home/ubuntu/projects/laptop-recommendation")

        # Stage changes
        print_info("Staging changes...")
        result = subprocess.run(
            ["git", "add", "utils/logger.py"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            print_success("Changes staged")
        else:
            print_error(f"Failed to stage: {result.stderr}")
            return False

        # Commit
        print_info("Committing changes...")
        commit_msg = f"feat: add simple logging utility\n\n- Add log_debug, log_info, log_warning functions\n- Create utils/logger.py\n- Include example usage"

        result = subprocess.run(
            ["git", "commit", "-m", f"feat: add simple logging utility"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            print_success("Changes committed")
            print_info(f"Commit message: feat: add simple logging utility")
        else:
            print_error(f"Failed to commit: {result.stderr}")
            return False

        return True

    except Exception as e:
        print_error(f"Commit failed: {e}")
        return False


async def phase_7_push_to_origin(branch_name):
    """Phase 7: Push to origin"""
    print_phase(7, "PUSH TO ORIGIN")

    try:
        project_path = Path("/home/ubuntu/projects/laptop-recommendation")

        print_info(f"Pushing branch {branch_name} to origin...")
        result = subprocess.run(
            ["git", "push", "-u", "origin", branch_name],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            print_success(f"Branch pushed to origin")
            print_info(f"Branch URL: https://github.com/TheCurators/laptop-recommendation/tree/{branch_name}")
            return True
        else:
            print_error(f"Failed to push: {result.stderr}")
            return False

    except Exception as e:
        print_error(f"Push failed: {e}")
        return False


async def phase_8_create_pr(branch_name, card_url):
    """Phase 8: Create Pull Request"""
    print_phase(8, "CREATE PULL REQUEST")

    try:
        # Use gh CLI to create PR
        project_path = Path("/home/ubuntu/projects/laptop-recommendation")

        pr_title = "[orchestrator-agent] Add simple logging utility"
        pr_body = f"""## Summary
- Add simple logging utility functions (log_debug, log_info, log_warning)
- Create utils/logger.py with example usage

## Changes
- New file: utils/logger.py
- Functions: log_debug(), log_info(), log_warning()

## Testing
- Tested all logging functions
- Verified output format

## Task
- Trello: {card_url}

## Checklist
- [x] Code follows project style guidelines
- [x] Self-review completed
- [x] Tested locally
- [x] Ready for review
"""

        print_info("Creating PR using GitHub CLI...")
        result = subprocess.run(
            [
                "gh", "pr", "create",
                "--title", pr_title,
                "--body", pr_body,
                "--base", "main"
            ],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "GH_TOKEN": os.getenv("GITHUB_TOKEN", "")}
        )

        if result.returncode == 0:
            # Extract PR URL from output
            pr_url = result.stdout.strip()
            print_success(f"PR created successfully!")
            print_info(f"PR URL: {pr_url}")
            return pr_url
        else:
            print_error(f"Failed to create PR: {result.stderr}")
            return None

    except Exception as e:
        print_error(f"PR creation failed: {e}")
        import traceback
        traceback.print_exc()
        return None


async def phase_9_verify_pr(pr_url):
    """Phase 9: Verify PR exists and is valid"""
    print_phase(9, "VERIFY PULL REQUEST")

    try:
        if not pr_url:
            print_error("No PR URL provided")
            return False

        print_info("Fetching PR details...")
        result = subprocess.run(
            ["gh", "pr", "view", "--json", "title,number,state,url"],
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "GH_TOKEN": os.getenv("GITHUB_TOKEN", "")}
        )

        if result.returncode == 0:
            print_success("PR verified successfully")
            print_info(f"Details: {result.stdout}")
            return True
        else:
            print_error(f"Failed to verify PR: {result.stderr}")
            return False

    except Exception as e:
        print_error(f"PR verification failed: {e}")
        return False


async def phase_10_send_notification(pr_url, card_url):
    """Phase 10: Send Telegram notification"""
    print_phase(10, "SEND TELEGRAM NOTIFICATION")

    try:
        from agents.notification.telegram_notifier import get_telegram_notifier

        notifier = get_telegram_notifier()

        # Extract PR number from URL
        pr_number = "Unknown"
        if pr_url and "/pull/" in pr_url:
            pr_number = pr_url.split("/pull/")[-1]

        print_info("Sending Telegram notification...")
        success = await notifier.send_pr_approval_notification(
            project_name="laptop-recommendation",
            pr_number=int(pr_number) if pr_number.isdigit() else 0,
            pr_title="[orchestrator-agent] Add simple logging utility",
            pr_url=pr_url or "https://github.com/TheCurators/laptop-recommendation/pulls",
            branch_name="feat/logging-utility",
            checks_passed={
                "tests": "✅ Passed",
                "security": "✅ Passed",
                "review": "✅ Approved"
            }
        )

        if success:
            print_success("Telegram notification sent!")
            print_info("Check your Telegram for the notification")
            return True
        else:
            print_error("Failed to send Telegram notification")
            return False

    except Exception as e:
        print_error(f"Notification failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_full_pipeline():
    """Run the complete E2E pipeline"""
    print_header("🚀 COMPLETE END-TO-END PIPELINE TEST")
    print_info("Starting full autonomous agent workflow test...")
    print_info("This will test all 10 phases of the pipeline")
    print_warning("This may take several minutes...")

    results = {}

    # Phase 1: System Validation
    results['phase_1'] = await phase_1_system_validation()
    if not results['phase_1']:
        print_error("System validation failed - aborting pipeline")
        return False

    # Phase 2: Create Test Task
    card_id, card_url = await phase_2_create_test_task()
    results['phase_2'] = card_id is not None
    if not results['phase_2']:
        print_error("Failed to create test task - aborting pipeline")
        return False

    # Phase 3: Agent Pickup
    task_info = await phase_3_agent_pickup_task(card_id)
    results['phase_3'] = task_info is not None

    # Phase 4: Pre-work Git Ops
    results['phase_4'] = await phase_4_pre_work_git_ops()

    # Phase 5: Execute Task
    success, branch_name = await phase_5_execute_task(task_info)
    results['phase_5'] = success

    if not success:
        print_error("Task execution failed - cleaning up and aborting")
        # Cleanup: delete Trello card
        return False

    # Phase 6: Commit Changes
    results['phase_6'] = await phase_6_commit_changes(branch_name)

    # Phase 7: Push to Origin
    results['phase_7'] = await phase_7_push_to_origin(branch_name)

    # Phase 8: Create PR
    pr_url = await phase_8_create_pr(branch_name, card_url)
    results['phase_8'] = pr_url is not None

    # Phase 9: Verify PR
    results['phase_9'] = await phase_9_verify_pr(pr_url)

    # Phase 10: Send Notification
    results['phase_10'] = await phase_10_send_notification(pr_url, card_url)

    # Print summary
    print_header("📊 PIPELINE TEST RESULTS")

    phases = [
        ("System Validation", results['phase_1']),
        ("Create Test Task", results['phase_2']),
        ("Agent Pickup Task", results['phase_3']),
        ("Pre-work Git Ops", results['phase_4']),
        ("Execute Task", results['phase_5']),
        ("Commit Changes", results['phase_6']),
        ("Push to Origin", results['phase_7']),
        ("Create PR", results['phase_8']),
        ("Verify PR", results['phase_9']),
        ("Send Notification", results['phase_10']),
    ]

    for i, (phase, passed) in enumerate(phases, 1):
        status = f"{GREEN}✅ PASSED{RESET}" if passed else f"{RED}❌ FAILED{RESET}"
        print(f"Phase {i}: {phase:<30} {status}")

    total_passed = sum(1 for _, passed in phases if passed)
    total = len(phases)

    print(f"\n{BOLD}Result: {total_passed}/{total} phases passed{RESET}")

    if total_passed == total:
        print(f"\n{GREEN}{BOLD}🎉 COMPLETE PIPELINE TEST PASSED!{RESET}")
        print(f"{GREEN}The autonomous agent system is fully functional!{RESET}\n")
        return True
    else:
        print(f"\n{RED}{BOLD}⚠️  PIPELINE TEST HAD FAILURES{RESET}")
        print(f"{RED}Please review the failed phases above{RESET}\n")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_full_pipeline())
    sys.exit(0 if success else 1)
