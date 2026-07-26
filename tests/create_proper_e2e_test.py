#!/usr/bin/env python3
"""
Proper E2E Test - Following Orchestrator Guidelines

Creates test tasks in Trello using proper [agent] tag format.
Tests complete workflow: Trello → Decomposition → Implementation → Review → PR → Approval
"""

import asyncio
from worker.trello.client import get_trello_client

# Test tasks following proper [agent] tag format
TEST_TASKS = [
    {
        "title": "[E2E-TEST] [coding_agent] Create utility function with test coverage",
        "description": """
## Task Description
Create a Python utility function that validates email addresses with comprehensive tests.

## Requirements
1. Create utility function in src/utils/email_validator.py
2. Function should validate email format using regex
3. Handle edge cases (empty, invalid format, etc.)
4. Include proper error handling and logging
5. Write unit tests with 90%+ coverage
6. Follow security best practices (input validation, no hardcoded secrets)
7. Code review must pass
8. Create pull request with security checklist

## Working Directory
/home/ubuntu/projects/laptop-recommendation

## Expected Workflow (Standard):
1. [git_agent] Create feature branch
2. [coding_agent] Implement email validator
3. [testing_agent] Write unit tests
4. [testing_agent] Execute test suite
5. [security_agent] Security scan
6. [review_agent] Code review (verify Fix #1: uses git diff fallback)
7. [git_agent] Commit changes
8. [git_agent] Create PR (verify Fix #2: routes correctly)
9. [docs_agent] Update documentation

## Fixes Being Tested:
- Fix #1: Review agent git diff fallback (when no code provided)
- Fix #2: PR creation routing (should route to _create_pr not _create_branch)
- Fix #3: Git push authentication (automatic token injection)
        """,
        "priority": "P0",
        "labels": ["E2E-TEST", "P0"]
    },
    {
        "title": "[E2E-TEST] [git_agent] Simple file commit and PR workflow",
        "description": """
## Task Description
Create a simple configuration file and make a pull request to test basic workflow.

## Requirements
1. Create file config/test_config.json with sample config
2. Commit the change with conventional commit message
3. Create pull request

## Working Directory
/home/ubuntu/projects/laptop-recommendation

## This Tests:
- Basic git operations (branch, commit, PR)
- Fix #2: PR creation routing verification
- Fix #3: Git push authentication

## Expected Workflow:
1. [git_agent] Create branch
2. [coding_agent] Create config file
3. [git_agent] Commit
4. [git_agent] Create PR
        """,
        "priority": "P0",
        "labels": ["E2E-TEST", "P0", "simple"]
    }
]

async def setup_test():
    """Setup test environment and create tasks."""
    client = get_trello_client()

    print("=" * 80)
    print("PROPER E2E TEST SETUP")
    print("=" * 80)

    # Clear In Progress list
    print("\n🧹 Clearing In Progress list...")
    in_progress = await client.get_in_progress_cards()
    if in_progress:
        for card in in_progress:
            await client.move_to_list(card.source_id, "To do")
            print(f"  ✓ Moved card back to TODO: {card.title[:50]}...")
    else:
        print("  ✓ In Progress list already empty")

    # Get TODO list
    lists = await client.get_lists()
    todo_list_id = lists.get("To do") or lists.get("TODO")
    if not todo_list_id:
        raise ValueError("Could not find TODO list!")

    # Create test tasks
    print(f"\n📋 Creating {len(TEST_TASKS)} test tasks...")
    created_tasks = []

    for i, task in enumerate(TEST_TASKS, 1):
        print(f"\n[{i}/{len(TEST_TASKS)}] Creating: {task['title'][:60]}...")

        card_id = await client.create_card(
            name=task["title"],
            desc=task["description"],
            list_id=todo_list_id,
        )

        # Add priority label
        priority = task["priority"]
        label_colors = {
            "P0": "red",
            "P1": "orange",
            "P2": "yellow",
            "P3": "green"
        }
        label_id = await client.get_or_create_label(priority, label_colors.get(priority, "blue"))
        await client.add_label_to_card(card_id, label_id)

        # Add additional labels
        for label_name in task.get("labels", []):
            if label_name != priority:  # Skip priority if already added
                label_id = await client.get_or_create_label(label_name, "blue")
                await client.add_label_to_card(card_id, label_id)

        created_tasks.append(card_id)
        print(f"  ✓ Task created: {card_id}")

    print("\n" + "=" * 80)
    print("✅ E2E TEST SETUP COMPLETE")
    print("=" * 80)
    print(f"\nCreated {len(created_tasks)} test tasks")
    print("\n📝 Task Summary:")
    for i, task in enumerate(TEST_TASKS, 1):
        print(f"  {i}. {task['title']}")
        print(f"     Priority: {task['priority']}")
        print(f"     Labels: {', '.join(task['labels'])}")

    print("\n🚀 Ready to run orchestrator!")
    print("\nExpected to test:")
    print("  ✓ Fix #1: Review agent uses git diff when no code provided")
    print("  ✓ Fix #2: PR creation routes to _create_pr (not _create_branch)")
    print("  ✓ Fix #3: Git push with automatic authentication")
    print("\n" + "=" * 80)

    return created_tasks

if __name__ == "__main__":
    asyncio.run(setup_test())
