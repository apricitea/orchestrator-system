#!/usr/bin/env python3
"""
Create test tasks in Trello for end-to-end orchestrator testing.
"""

import asyncio
from worker.trello.client import get_trello_client

TEST_TASKS = [
    {
        "title": "[E2E TEST] Simple Feature - Add Hello World Function",
        "description": """
## Task Description
Add a simple hello_world() function to the repository.

## Requirements
- Create src/hello.py
- Implement hello_world() function that returns "Hello, World!"
- Add basic tests

## Working Directory
/home/ubuntu/test-orchestrator-repo
        """,
        "priority": "P3",
        "label": "green",
        "expected_outcome": "PR created and approved"
    },
    {
        "title": "[E2E TEST] Bug Fix - Fix Typo in README",
        "description": """
## Task Description
Fix a typo in the README.md file.

## Requirements
- Change "Test Repository" to "Test Repository (E2E)"
- Commit the change

## Working Directory
/home/ubuntu/test-orchestrator-repo
        """,
        "priority": "P1",
        "label": "orange",
        "expected_outcome": "PR created and approved"
    },
    {
        "title": "[E2E TEST] Feature - Add Calculator Module",
        "description": """
## Task Description
Create a calculator module with basic operations.

## Requirements
- Create src/calculator.py
- Implement add(), subtract(), multiply(), divide()
- Add comprehensive tests
- Add docstrings

## Working Directory
/home/ubuntu/test-orchestrator-repo
        """,
        "priority": "P2",
        "label": "yellow",
        "expected_outcome": "PR created, needs revisions (missing error handling)"
    },
    {
        "title": "[E2E TEST] CRITICAL - Security Fix - Input Validation",
        "description": """
## Task Description
Add input validation to calculator module.

## Requirements
- Validate numeric inputs
- Handle division by zero
- Add type checking

## Working Directory
/home/ubuntu/test-orchestrator-repo

## Context
This is a follow-up to calculator module. Wait for calculator PR first.
        """,
        "priority": "P0",
        "label": "red",
        "expected_outcome": "Should wait for calculator PR first"
    },
]

async def create_test_tasks():
    client = get_trello_client()

    # Get or create labels
    label_ids = {}
    for task in TEST_TASKS:
        priority = task["priority"]
        color = task["label"]
        label_id = await client.get_or_create_label(priority, color)
        label_ids[priority] = label_id

    # Get TODO list (note: it's "To do" with space and lowercase 'd')
    lists = await client.get_lists()
    todo_list_id = lists.get("To do") or lists.get("TODO")

    if not todo_list_id:
        print("❌ TODO list not found!")
        print(f"Available lists: {list(lists.keys())}")
        return

    # Create cards
    for i, task in enumerate(TEST_TASKS, 1):
        print(f"\n[{i}/{len(TEST_TASKS)}] Creating: {task['title']}")

        # Create card
        card_id = await client.create_card(
            name=task["title"],
            desc=task["description"],
            list_id=todo_list_id,
        )

        # Add priority label
        priority_label_id = label_ids.get(task["priority"])
        if priority_label_id:
            await client.add_label_to_card(card_id, priority_label_id)

        print(f"  ✅ Created")
        print(f"     Priority: {task['priority']}")
        print(f"     Card ID: {card_id}")
        print(f"     Expected: {task.get('expected_outcome', 'Success')}")

    print(f"\n{'='*70}")
    print(f"✅ Created {len(TEST_TASKS)} test tasks in TODO list")
    print(f"{'='*70}")
    print("\n📋 Priority Order:")
    print(f"  1. P0 (Critical - will be processed first)")
    print(f"  2. P1 (High)")
    print(f"  3. P2 (Medium)")
    print(f"  4. P3 (Low)")
    print(f"\nNext: Run orchestrator to process tasks")
    print(f"  python3 /home/ubuntu/run_orchestrator_on_trello.py")

if __name__ == "__main__":
    asyncio.run(create_test_tasks())
