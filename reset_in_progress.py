#!/usr/bin/env python3
"""
Move old In Progress task back to TODO so system picks up the new E2E-TEST task.
"""

import asyncio
from worker.trello.client import get_trello_client

async def reset():
    client = get_trello_client()

    print("Moving In Progress task back to TODO...")
    in_progress = await client.get_in_progress_cards()
    if in_progress:
        for card in in_progress:
            await client.move_to_list(card.source_id, "To do")
            print(f"✓ Moved: {card.title[:50]}")
    else:
        print("No tasks in In Progress")

    print("\n✅ Ready - system will now pick up the new E2E-TEST task")

asyncio.run(reset())
