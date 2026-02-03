#!/usr/bin/env python3
"""
Create a REAL task for laptop-recommendation project to test all fixes.
"""

import asyncio
from worker.trello.client import get_trello_client

async def create_real_task():
    client = get_trello_client()

    # Clear test tasks first
    lists = await client.get_lists()
    todo_list_id = lists.get("To do") or lists.get("TODO")

    import httpx
    url = f"{client._base_url}/lists/{todo_list_id}/cards"
    params = {**client._auth_params, "fields": "name,id,labels"}

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        response = await http_client.get(url, params=params)
        response.raise_for_status()
        cards = response.json()

    print("🧹 Clearing test tasks...")
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        for card in cards:
            labels = [label.get("name", "") for label in card.get("labels", [])]
            if "E2E-TEST" in labels or "TEST FIXES" in labels:
                print(f"  Deleting: {card['name'][:40]}...")
                delete_url = f"{client._base_url}/cards/{card['id']}"
                await http_client.delete(delete_url, params=client._auth_params)

    # Create REAL task following production format
    # Format: [PROJECT] [agent] Description
    real_task = {
        "name": "[laptop-recommendation] [coding_agent] Add email notifications for price drops",
        "desc": """
## User Story
As a user, I want to receive email notifications when laptops I'm tracking drop in price, so I can make purchase decisions at the right time.

## Requirements
1. Create email notification service in apps/web/notifications/email_service.py
2. Implement price drop detection logic
3. Add email template for price alerts
4. Include proper error handling and logging
5. Follow existing code patterns in the project
6. Add configuration for SMTP settings

## Technical Details
- Use Flask mail or similar
- Check current price vs tracked price threshold
- Send emails to users watching specific laptops
- Log all notification attempts
- Handle SMTP failures gracefully

## Working Directory
/home/ubuntu/projects/laptop-recommendation

This will test:
- Code creation in real project structure
- Git operations (branch, commit, PR)
- Code review workflow
- PR creation and routing
        """,
    }

    print("\n📝 Creating REAL task...")
    card_id = await client.create_card(
        name=real_task["name"],
        desc=real_task["desc"],
        list_id=todo_list_id,
    )

    # Add P0 label
    label_id = await client.get_or_create_label("P0", "red")
    await client.add_label_to_card(card_id, label_id)

    print(f"\n✅ Created: {real_task['name']}")
    print(f"   Card ID: {card_id}")
    print("\nThis task will test all fixes in a REAL production scenario:")
    print("  ✓ Fix #1: Review agent git diff fallback")
    print("  ✓ Fix #2: PR creation routing to _create_pr")
    print("  ✓ Fix #3: Git push authentication (SSH)")
    print("\n🚀 Ready to run orchestrator!")

asyncio.run(create_real_task())
