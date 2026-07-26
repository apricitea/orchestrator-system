#!/usr/bin/env python3
"""
Clear old E2E test tasks and recreate with correct paths.
"""

import asyncio
from worker.trello.client import get_trello_client

async def clear_and_recreate():
    client = get_trello_client()

    print("=" * 80)
    print("CLEARING OLD E2E TASKS AND RECREATING")
    print("=" * 80)

    # Get TODO list
    lists = await client.get_lists()
    todo_list_id = lists.get("To do") or lists.get("TODO")

    # Get all cards from TODO
    import httpx
    url = f"{client._base_url}/lists/{todo_list_id}/cards"
    params = {**client._auth_params, "fields": "name,id,labels"}

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        response = await http_client.get(url, params=params)
        response.raise_for_status()
        cards = response.json()

    print(f"\n📋 Found {len(cards)} cards in TODO")

    # Delete old E2E-TEST cards
    deleted = 0
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        for card in cards:
            labels = [label.get("name", "") for label in card.get("labels", [])]
            if "E2E-TEST" in labels:
                print(f"  🗑️  Deleting: {card['name'][:50]}...")
                delete_url = f"{client._base_url}/cards/{card['id']}"
                await http_client.delete(delete_url, params=client._auth_params)
                deleted += 1

    print(f"\n✅ Deleted {deleted} old E2E-TEST tasks")

    # Now recreate with correct path
    print("\n📝 Creating new E2E test tasks...")

    TEST_TASKS = [
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
- Fix #3: Git push authentication (SSH)

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

    for task in TEST_TASKS:
        card_id = await client.create_card(
            name=task["title"],
            desc=task["description"],
            list_id=todo_list_id,
        )

        # Add labels
        for label_name in task["labels"]:
            label_colors = {"P0": "red", "P1": "orange", "P2": "yellow", "P3": "green"}
            color = label_colors.get(label_name, "blue") if label_name.startswith("P") else "blue"
            label_id = await client.get_or_create_label(label_name, color)
            await client.add_label_to_card(card_id, label_id)

        print(f"  ✓ Created: {task['title'][:50]}...")

    print("\n" + "=" * 80)
    print("✅ READY FOR E2E TEST")
    print("=" * 80)

asyncio.run(clear_and_recreate())
