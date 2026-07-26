#!/usr/bin/env python3
"""
Direct Trello task processor - bypasses Redis, works directly with Trello.
"""

import asyncio
import sys
sys.path.insert(0, "/home/ubuntu")

from agents.orchestrator.main_orchestrator import create_orchestrator
from worker.trello.client import get_trello_client
from worker.db_models import Task, TaskSource, TaskPriority
from utils.logger import get_logger
import re

logger = get_logger("direct_trello")

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
    print("AI WORKER - DIRECT TRELLO PROCESSING")
    print("="*80)
    print()

    # Initialize
    trello = get_trello_client()
    orchestrator = await create_orchestrator()

    print("✅ Initialized orchestrator and Trello client")
    print()

    # Get TODO cards and move highest priority to In Progress
    print("📋 Checking Trello for tasks...")
    todo_cards = await trello.get_todo_cards()

    if not todo_cards:
        print("❌ No tasks in TODO")
        return 0

    # Get highest priority card (P0 first, then P1, etc.)
    # Sort by priority
    priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    todo_cards.sort(key=lambda card: priority_order.get(card.priority, 99))

    card = todo_cards[0]
    print(f"✅ Found task: {card.title[:60]}... (Priority: {card.priority})")

    # Move to In Progress
    await trello.move_to_in_progress(card.source_id)
    print("✅ Moved to In Progress")
    print(f"✅ Found task: {card.title[:60]}...")
    print()

    # Extract working directory
    working_dir = await get_working_directory(card.description or "")
    print(f"📂 Working Directory: {working_dir}")
    print()

    # Create Task object
    task = Task(
        id=card.source_id,
        source_id=card.source_id,
        title=card.title,
        description=card.description or "",
        source=TaskSource.TRELLO,
        priority=TaskPriority.P0,  # Will be read from card label
        metadata={"working_directory": working_dir}
    )

    try:
        # Execute task
        print("🚀 Executing task...")
        print("-"*80)
        result = await orchestrator.execute(
            task.description,
            source="trello",
            context={"working_directory": working_dir}
        )
        print("-"*80)
        print()

        # Check result
        if result.status in ["success", "partial"]:
            print(f"✅ Task completed successfully!")
            print(f"   Status: {result.status}")
            if result.metadata:
                pr_url = result.metadata.get("pr_url")
                if pr_url:
                    print(f"   PR: {pr_url}")

            # Move to Done/Review
            await trello.move_to_review(card.source_id)
            print()
            print("✅ Trello card moved to Review!")
            return 0
        else:
            print(f"❌ Task failed")
            print(f"   Errors: {result.errors}")
            # Move back to TODO
            await trello.move_to_list(card.source_id, "To do")
            return 1

    except Exception as e:
        logger.error("Task execution failed", error=str(e))
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    print()
    print("="*80)
    print("DONE")
    print("="*80)
    sys.exit(exit_code)
