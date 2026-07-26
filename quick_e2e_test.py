#!/usr/bin/env python3
"""
Simple test that will complete quickly - create a config file and PR.
"""

import asyncio
import sys
sys.path.insert(0, "/home/ubuntu")

from agents.orchestrator.main_orchestrator import create_orchestrator
from worker.trello.client import get_trello_client
from worker.db_models import Task, TaskSource, TaskPriority
import re

async def get_working_directory(task_description: str) -> str:
    """Extract working directory from task description."""
    patterns = [
        r'Working Directory:\s*(.+?)(?:\n|$)',
        r'## Working Directory\s*\n\s*(.+?)(?:\n|$)',
    ]
    for pattern in patterns:
        match = re.search(pattern, task_description, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return "."

async def main():
    """Main entry point."""
    print("="*80)
    print("QUICK E2E TEST - Simple Task → PR")
    print("="*80)
    print()

    # Initialize
    trello = get_trello_client()
    orchestrator = await create_orchestrator()

    # Create a simple P0 task
    print("Creating simple P0 test task...")
    lists = await trello.get_lists()
    todo_list_id = lists.get("To do") or lists.get("TODO")

    task_desc = """
## Task Description
Create a configuration file for scraper settings.

## Requirements
1. Create config/scraper_config.json
2. Add rate limiting settings
3. Add timeout configuration

## Working Directory
/home/ubuntu/projects/laptop-recommendation

This is a quick test to verify the full workflow including PR creation.
    """

    card_id = await trello.create_card(
        name="[laptop-recommendation] [agent] P0: Create scraper config file",
        desc=task_desc,
        list_id=todo_list_id,
    )

    label_id = await trello.get_or_create_label("P0", "red")
    await trello.add_label_to_card(card_id, label_id)

    print(f"✅ Task created: {card_id}")
    print()

    # Get and move to In Progress
    todo_cards = await trello.get_todo_cards()
    priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    todo_cards.sort(key=lambda card: priority_order.get(card.priority, 99))

    card = todo_cards[0]
    await trello.move_to_in_progress(card.source_id)

    working_dir = await get_working_directory(card.description or "")
    print(f"📋 Task: {card.title[:60]}...")
    print(f"📂 Working Directory: {working_dir}")
    print()

    # Execute
    print("🚀 Executing...")
    print("-"*80)
    result = await orchestrator.execute(
        card.description,
        source="trello",
        context={"working_directory": working_dir}
    )
    print("-"*80)
    print()

    if result.status in ["success", "partial"]:
        print(f"✅ SUCCESS!")
        print(f"   Status: {result.status}")
        if result.metadata:
            pr_url = result.metadata.get("pr_url")
            pr_number = result.metadata.get("pr_number")
            if pr_url:
                print(f"   PR URL: {pr_url}")
            if pr_number:
                print(f"   PR Number: {pr_number}")

        await trello.move_to_review(card.source_id)
        print()
        print("✅ Trello card moved to Review!")
        return 0
    else:
        print(f"❌ Failed")
        print(f"   Errors: {result.errors}")
        await trello.move_to_list(card.source_id, "To do")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    print()
    print("="*80)
    print("DONE")
    print("="*80)
    sys.exit(exit_code)
