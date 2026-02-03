#!/usr/bin/env python3
"""
Create PROPER format Trello tasks following:
[project-name] [agent] P#: Description
"""

import asyncio
from worker.trello.client import get_trello_client

async def create_proper_tasks():
    client = get_trello_client()

    # Clear all existing test cards
    lists = await client.get_lists()
    todo_list_id = lists.get("To do") or lists.get("TODO")

    import httpx
    url = f"{client._base_url}/lists/{todo_list_id}/cards"
    params = {**client._auth_params, "fields": "name,id,labels"}

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        response = await http_client.get(url, params=params)
        response.raise_for_status()
        cards = response.json()

    print("🧹 Clearing all cards from TODO...")
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        for card in cards:
            print(f"  Deleting: {card['name'][:50]}...")
            delete_url = f"{client._base_url}/cards/{card['id']}"
            await http_client.delete(delete_url, params=client._auth_params)

    # Create PROPER format tasks
    proper_tasks = [
        {
            "name": "[laptop-recommendation] [agent] P0: Add price drop email notifications",
            "desc": """
## Task Description
Implement email notification system for price drops on tracked laptops.

## Requirements
1. Create notification service in apps/web/notifications/
2. Implement price comparison logic
3. Add email template for alerts
4. Configure SMTP settings
5. Add error handling and logging

## Working Directory
/home/ubuntu/projects/laptop-recommendation

## Expected Workflow:
1. [git_agent] Create feature branch
2. [coding_agent] Implement notification service
3. [testing_agent] Write tests
4. [review_agent] Code review
5. [git_agent] Commit changes
6. [git_agent] Create pull request
            """,
            "priority": "P0",
            "color": "red"
        },
        {
            "name": "[laptop-recommendation] [agent] P1: Fix scraper rate limiting issue",
            "desc": """
## Task Description
Fix rate limiting problem in Amazon scraper that's causing request failures.

## Requirements
1. Investigate current rate limiting implementation
2. Add proper retry logic with exponential backoff
3. Implement request queuing
4. Add monitoring and alerts

## Working Directory
/home/ubuntu/projects/laptop-recommendation

## Expected Workflow:
1. [git_agent] Create bugfix branch
2. [coding_agent] Implement fix
3. [testing_agent] Test fix
4. [review_agent] Review
5. [git_agent] Commit and PR
            """,
            "priority": "P1",
            "color": "orange"
        },
        {
            "name": "[laptop-recommendation] [agent] P2: Add keyboard navigation support",
            "desc": """
## Task Description
Add keyboard shortcuts and navigation support to the web application.

## Requirements
1. Implement arrow key navigation for laptop lists
2. Add keyboard shortcuts for common actions
3. Ensure accessibility compliance
4. Add user preference settings

## Working Directory
/home/ubuntu/projects/laptop-recommendation
            """,
            "priority": "P2",
            "color": "yellow"
        },
        {
            "name": "[laptop-recommendation] [agent] P3: Update README with new features",
            "desc": """
## Task Description
Update project README to document recently added features and improvements.

## Requirements
1. Document new scraper features
2. Add setup instructions
3. Update API documentation links
4. Add contributing guidelines

## Working Directory
/home/ubuntu/projects/laptop-recommendation
            """,
            "priority": "P3",
            "color": "green"
        }
    ]

    print("\n📝 Creating PROPER format tasks...\n")
    for task in proper_tasks:
        card_id = await client.create_card(
            name=task["name"],
            desc=task["desc"],
            list_id=todo_list_id,
        )

        # Add priority label
        label_id = await client.get_or_create_label(task["priority"], task["color"])
        await client.add_label_to_card(card_id, label_id)

        print(f"✅ Created: {task['name']}")
        print(f"   Priority: {task['priority']}")
        print()

    print("=" * 80)
    print("✅ PROPER FORMAT TASKS CREATED")
    print("=" * 80)
    print("\nFormat: [project-name] [agent] P#: Description")
    print("All tasks follow the proper guidelines and best practices!")
    print("\nPriorities:")
    print("  P0: Critical (price notifications)")
    print("  P1: High (scraper bug fix)")
    print("  P2: Medium (keyboard navigation)")
    print("  P3: Low (README update)")

asyncio.run(create_proper_tasks())
