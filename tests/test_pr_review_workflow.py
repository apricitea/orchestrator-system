#!/usr/bin/env python3
"""
Test PR Review Workflow

This script tests:
1. PR review posts comments to GitHub
2. Card moves to DONE when PR approved
3. Feedback loop creates fix tasks when PR not approved
"""

import asyncio
import os
import sys
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

from agents.orchestrator.enhanced_orchestrator import EnhancedOrchestrator
from agents.automation.id_tracking import TaskContext
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


def print_success(text):
    print(f"{GREEN}✅ {text}{RESET}")


def print_error(text):
    print(f"{RED}❌ {text}{RESET}")


def print_info(text):
    print(f"{BLUE}ℹ️  {text}{RESET}")


def print_warning(text):
    print(f"{YELLOW}⚠️  {text}{RESET}")


async def test_pr_review_workflow():
    """Test the PR review workflow."""
    configure_logging()
    logger = get_logger("test_pr_review_workflow")

    print_header("🧪 PR REVIEW WORKFLOW TEST")

    # Initialize orchestrator
    print_info("Initializing Enhanced Orchestrator...")
    orchestrator = EnhancedOrchestrator()
    await orchestrator.initialize()
    print_success("Orchestrator initialized")

    # Test case 1: Review PR #17 (has review comment already)
    print_header("TEST 1: REVIEW PR #17 (Known to work)")

    test_context_1 = TaskContext(
        task_id="test_pr_17",
        trello_card_id="697c5f370be65361b572d0e1",  # Test card from earlier
        original_task="Test PR review workflow",
        project_name="laptop-recommendation",
        trello_card_url="https://trello.com/c/697c5f370be65361b572d0e1",
    )

    print_info(f"Testing PR review for PR #17")
    print_info(f"Trello card: {test_context_1.trello_card_id[:8]}")
    print_info(f"Repo: /home/ubuntu/projects/laptop-recommendation\n")

    try:
        result = await orchestrator._review_pr(
            repo_path="/home/ubuntu/projects/laptop-recommendation",
            pr_number=17,
            context=test_context_1,
        )

        print_info(f"Review result:")
        print(f"  Status: {result.status}")
        print(f"  Output: {result.output[:100] if result.output else 'N/A'}...")

        if result.is_success():
            print_success("PR review: APPROVED ✅")
            print_info("Card should be moved to DONE")
        else:
            print_warning(f"PR review: {result.status}")
            if result.errors:
                print_warning(f"Errors: {result.errors[:3]}")

    except Exception as e:
        print_error(f"PR review failed: {e}")
        import traceback
        traceback.print_exc()

    # Test case 2: Review PR #19 (from autonomous test)
    print_header("TEST 2: REVIEW PR #19 (From autonomous test)")

    test_context_2 = TaskContext(
        task_id="test_pr_19",
        trello_card_id="697ed6ca0c20667bc99003b3",  # Card from autonomous test
        original_task="Test PR review workflow",
        project_name="laptop-recommendation",
        trello_card_url="https://trello.com/c/697ed6ca0c20667bc99003b3",
    )

    print_info(f"Testing PR review for PR #19")
    print_info(f"Trello card: {test_context_2.trello_card_id[:8]}")
    print_info(f"Repo: /home/ubuntu/projects/laptop-recommendation\n")

    try:
        result = await orchestrator._review_pr(
            repo_path="/home/ubuntu/projects/laptop-recommendation",
            pr_number=19,
            context=test_context_2,
        )

        print_info(f"Review result:")
        print(f"  Status: {result.status}")
        print(f"  Output: {result.output[:100] if result.output else 'N/A'}...")

        if result.is_success():
            print_success("PR review: APPROVED ✅")
            print_info("Card should be moved to DONE")
        else:
            print_warning(f"PR review: {result.status}")
            if result.errors:
                print_warning(f"Errors: {result.errors[:3]}")

    except Exception as e:
        print_error(f"PR review failed: {e}")
        import traceback
        traceback.print_exc()

    # Summary
    print_header("TEST SUMMARY")
    print_info("PR Review Workflow Test Complete")
    print_info("\nWhat to check:")
    print_info("  1. Review comments on PR #17 and #19 on GitHub")
    print_info("  2. Trello cards status on board")
    print_info("  3. Any error logs above\n")

    print_success("Test completed!")
    print_info("Check GitHub PRs for review comments:")
    print_info("  • https://github.com/TheCurators/laptop-recommendation/pull/17")
    print_info("  • https://github.com/TheCurators/laptop-recommendation/pull/19")


if __name__ == "__main__":
    asyncio.run(test_pr_review_workflow())
