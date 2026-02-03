#!/usr/bin/env python3
"""
List existing Trello cards to understand the real structure.
"""

import asyncio
from worker.trello.client import get_trello_client

async def list_cards():
    client = get_trello_client()

    lists = await client.get_lists()
    todo_list_id = lists.get("To do") or lists.get("TODO")

    # Get all cards from TODO
    import httpx
    url = f"{client._base_url}/lists/{todo_list_id}/cards"
    params = {**client._auth_params, "fields": "name,desc,labels"}

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        response = await http_client.get(url, params=params)
        response.raise_for_status()
        cards = response.json()

    print("=" * 80)
    print("EXISTING TRELLO CARDS")
    print("=" * 80)
    print(f"\nFound {len(cards)} cards in TODO:\n")

    for i, card in enumerate(cards[:10], 1):  # Show first 10
        print(f"{i}. {card['name']}")
        labels = [label.get('name', '') for label in card.get('labels', [])]
        if labels:
            print(f"   Labels: {', '.join(labels)}")
        desc = card.get('desc', '')
        if desc and len(desc) < 200:
            print(f"   Desc: {desc[:100]}...")
        print()

asyncio.run(list_cards())
