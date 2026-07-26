#!/usr/bin/env python3
"""
MINIMAL test - Straight to PR, no testing/security blocking.
"""

import asyncio
import sys
sys.path.insert(0, "/home/ubuntu")

from agents.orchestrator.main_orchestrator import create_orchestrator
from worker.trello.client import get_trello_client
import re

async def main():
    print("="*80)
    print("MINIMAL TEST - Branch → File → Commit → PR")
    print("="*80)
    print()

    trello = get_trello_client()
    orchestrator = await create_orchestrator()

    # Create MINIMAL task (no testing, no security scan)
    print("Creating minimal task...")
    lists = await trello.get_lists()
    todo_list_id = lists.get("To do") or lists.get("TODO")

    task_desc = """
## Task Description
Add a README section documenting the project.

## Requirements
1. Add section to README.md
2. Brief project description

## Working Directory
/home/ubuntu/projects/laptop-recommendation

Minimal test - no extensive testing or security scans needed.
    """

    card_id = await trello.create_card(
        name="[laptop-recommendation] [agent] P0: Add README documentation section",
        desc=task_desc,
        list_id=todo_list_id,
    )

    label_id = await trello.get_or_create_label("P0", "red")
    await trello.add_label_to_card(card_id, label_id)

    print(f"✅ Task created")
    print()

    # Get and move to In Progress
    todo_cards = await trello.get_todo_cards()
    priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    todo_cards.sort(key=lambda card: priority_order.get(card.priority, 99))

    card = todo_cards[0]
    await trello.move_to_in_progress(card.source_id)

    print(f"📋 Task: {card.title[:60]}...")
    print(f"📂 Working Directory: /home/ubuntu/projects/laptop-recommendation")
    print()

    # Execute
    print("🚀 Executing (will go to PR quickly)...")
    print("-"*80)
    result = await orchestrator.execute(
        card.description,
        source="trello",
        context={"working_directory": "/home/ubuntu/projects/laptop-recommendation"}
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
                print(f"\n🎉 PR CREATED: {pr_url}")
            if pr_number:
                print(f"   PR Number: #{pr_number}")

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
    sys.exit(exit_code)
