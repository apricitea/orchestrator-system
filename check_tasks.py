#!/usr/bin/env python3
"""
Check task working directories.
"""

import asyncio
from worker.trello.client import get_trello_client
import httpx

async def check_tasks():
    client = get_trello_client()

    lists = await client.get_lists()
    todo_list_id = lists.get("To do") or lists.get("TODO")

    url = f"{client._base_url}/lists/{todo_list_id}/cards"
    params = {**client._auth_params, "fields": "name,desc"}

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        response = await http_client.get(url, params=params)
        response.raise_for_status()
        cards = response.json()

    print("=" * 80)
    print("CHECKING TASK WORKING DIRECTORIES")
    print("=" * 80)

    for card in cards:
        desc = card.get('desc', '')
        import re
        match = re.search(r'Working Directory\s*\n\s*(.+?)(?:\n|$)', desc, re.IGNORECASE)
        if match:
            path = match.group(1).strip()
            print(f"\n{card['name'][:50]}...")
            print(f"  Working Directory: {path}")
        else:
            print(f"\n{card['name'][:50]}...")
            print(f"  No Working Directory found!")

asyncio.run(check_tasks())
