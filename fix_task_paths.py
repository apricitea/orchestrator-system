#!/usr/bin/env python3
"""
Update ALL Trello tasks with CORRECT working directory.
"""

import asyncio
from worker.trello.client import get_trello_client
import httpx

async def fix_all_tasks():
    client = get_trello_client()

    # Get TODO list
    lists = await client.get_lists()
    todo_list_id = lists.get("To do") or lists.get("TODO")

    # Get all cards
    url = f"{client._base_url}/lists/{todo_list_id}/cards"
    params = {**client._auth_params, "fields": "name,id,desc"}

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        response = await http_client.get(url, params=params)
        response.raise_for_status()
        cards = response.json()

    print(f"Found {len(cards)} tasks in TODO")
    print("\nUpdating working directory to CORRECT path...")

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        for card in cards:
            old_desc = card.get('desc', '')
            if '/home/ubuntu/laptop-recommendation' in old_desc:
                # Fix the path
                new_desc = old_desc.replace('/home/ubuntu/laptop-recommendation', '/home/ubuntu/projects/laptop-recommendation')

                # Update card
                update_url = f"{client._base_url}/cards/{card['id']}"
                await http_client.put(
                    update_url,
                    params={
                        **client._auth_params,
                        'desc': new_desc
                    }
                )

                print(f"✅ Updated: {card['name'][:50]}...")
            else:
                print(f"  Skipped: {card['name'][:50]}...")

    print("\n✅ All tasks updated with CORRECT working directory!")
    print("   CORRECT PATH: /home/ubuntu/projects/laptop-recommendation")
    print("   CORRECT REPO: git@github.com:TheCurators/laptop-recommendation.git")

asyncio.run(fix_all_tasks())
