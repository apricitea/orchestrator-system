#!/usr/bin/env python3
"""
Simple script to run orchestrator on Trello tasks.
"""

import asyncio
import sys
sys.path.insert(0, "/home/ubuntu")

from worker.task_queue import TaskQueueManager
from utils.logger import get_logger

logger = get_logger("trello_orchestrator")

async def main():
    """Main entry point."""
    print("="*80)
    print("AI WORKER ORCHESTRATOR - TRELLO MODE")
    print("="*80)
    print()

    # Initialize task queue manager
    manager = TaskQueueManager()

    print("📋 Connected to Trello")
    print("🚀 Starting task processing...")
    print()
    print("Press Ctrl+C to stop")
    print("-"*80)
    print()

    try:
        # Run continuously
        await manager.run()
    except KeyboardInterrupt:
        print("\n🛑 Stopped by user")
    except Exception as e:
        logger.error("Orchestrator failed", error=str(e))
        print(f"\n❌ Error: {e}")
        return 1

    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
