#!/usr/bin/env python3
"""
Check all Trello lists and find examples of real card structure.
"""

import asyncio
from worker.trello.client import get_trello_client

async def check_structure():
    client = get_trello_client()

    # Get all lists
    import httpx
    url = f"{client._base_url}/boards/{client.config.trello_board_id}/lists"
    params = {**client._auth_params, "fields": "name,id"}

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        response = await http_client.get(url, params=params)
        response.raise_for_status()
        lists = response.json()

    print("=" * 80)
    print("TRELLO BOARD STRUCTURE")
    print("=" * 80)
    print(f"\nFound {len(lists)} lists:\n")

    for lst in lists:
        list_name = lst['name']
        list_id = lst['id']

        # Get cards in this list
        cards_url = f"{client._base_url}/lists/{list_id}/cards"
        cards_params = {**client._auth_params, "fields": "name,labels"}

        async with httpx.AsyncClient(timeout=30.0) as http_client:
            cards_response = await http_client.get(cards_url, params=cards_params)
            cards_response.raise_for_status()
            cards = cards_response.json()

        print(f"📋 {list_name}: {len(cards)} cards")

        if cards:
            # Show examples from this list
            for card in cards[:3]:  # First 3 cards
                print(f"   - {card['name']}")
                labels = [label.get('name', '') for label in card.get('labels', [])]
                if labels:
                    print(f"     Labels: {', '.join(labels)}")
        print()

asyncio.run(check_structure())
