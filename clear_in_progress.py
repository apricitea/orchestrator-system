#!/usr/bin/env python3
"""
Clear In Progress and restart with CORRECT repository.
"""

import asyncio
from worker.trello.client import get_trello_client
import httpx

async def clear_and_restart():
    client = get_trello_client()

    # Get In Progress list ID
    in_progress_id = client.config.trello_list_in_progress

    # Get cards in In Progress
    url = f"{client._base_url}/lists/{in_progress_id}/cards"
    params = {**client._auth_params, "fields": "name,id,desc"}

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        response = await http_client.get(url, params=params)
        response.raise_for_status()
        cards = response.json()

    if cards:
        print(f"🧹 Clearing {len(cards)} tasks from In Progress...")
        for card in cards:
            desc = card.get('desc', '')
            import re
            match = re.search(r'Working Directory\s*\n\s*(.+?)(?:\n|$)', desc, re.IGNORECASE)
            if match:
                path = match.group(1).strip()
                print(f"\n  Moving: {card['name'][:50]}...")
                print(f"    Old Path: {path}")

            # Move back to TODO
            await client.move_to_list(card['id'], "To do")
            print(f"    ✓ Moved to TODO")

        print("\n✅ In Progress cleared!")
        print("\nNow the orchestrator will pick up tasks with CORRECT path:")
        print("  ✅ Path: /home/ubuntu/projects/laptop-recommendation")
        print("  ✅ Repo: git@github.com:TheCurators/laptop-recommendation.git")
    else:
        print("✓ In Progress is already empty")

asyncio.run(clear_and_restart())
