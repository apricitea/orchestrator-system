#!/usr/bin/env python3
"""
Simple script to process ONE Trello task and demonstrate the workflow.
"""

import asyncio
import sys
sys.path.insert(0, "/home/ubuntu")

from agents.orchestrator.main_orchestrator import create_orchestrator
from worker.task_queue import TaskQueueManager
from utils.logger import get_logger

logger = get_logger("trello_demo")

async def main():
    """Main entry point."""
    print("="*80)
    print("AI WORKER - PROCESS ONE TRELLO TASK")
    print("="*80)
    print()

    # Initialize
    queue_manager = TaskQueueManager()
    orchestrator = await create_orchestrator()

    print("✅ Initialized orchestrator and task queue")
    print()

    # Get next task from Trello
    print("📋 Fetching next task from Trello...")
    task = await queue_manager.get_next_task()

    if not task:
        print("❌ No tasks available in Trello")
        return 1

    print(f"✅ Found task: {task.title[:60]}...")
    print(f"   Priority: {task.priority}")
    print(f"   Working Directory: {task.metadata.get('working_directory', 'Not specified')}")
    print()

    # Mark as processing
    await queue_manager.mark_processing(task.id, task.source_id)

    try:
        # Execute task
        print("🚀 Executing task...")
        print("-"*80)
        result = await orchestrator.execute(
            task.description,
            source=task.source,
            context={"working_directory": task.metadata.get("working_directory")}
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

            # Mark as completed
            await queue_manager.mark_task_completed(
                task.id,
                task.source_id,
                success=True,
                pr_url=result.metadata.get("pr_url") if result.metadata else None
            )
            print()
            print("✅ Trello card updated!")
            return 0
        else:
            print(f"❌ Task failed")
            print(f"   Errors: {result.errors}")

            # Mark as failed
            await queue_manager.mark_task_completed(
                task.id,
                task.source_id,
                success=False,
                error=result.errors[0] if result.errors else "Unknown error"
            )
            return 1

    except Exception as e:
        logger.error("Task execution failed", error=str(e))
        print(f"\n❌ Error: {e}")

        # Mark as failed
        await queue_manager.mark_task_completed(
            task.id,
            task.source_id,
            success=False,
            error=str(e)
        )
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    print()
    print("="*80)
    print("DONE")
    print("="*80)
    sys.exit(exit_code)
