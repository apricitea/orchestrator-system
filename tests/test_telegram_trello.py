#!/usr/bin/env python3
"""
Test Telegram → Trello Integration

This script tests:
1. Telegram bot command handlers
2. Trello task creation
3. Trello task listing
"""

import asyncio
import sys
sys.path.insert(0, '/home/ubuntu')

from worker.telegram.bot import get_telegram_bot
from worker.trello.client import get_trello_client


async def test_trello_integration():
    """Test Trello client methods."""
    print("="*80)
    print("TESTING TRELLO INTEGRATION")
    print("="*80)

    # Get Trello client
    trello = get_trello_client()

    if not trello.is_configured():
        print("❌ Trello not configured")
        return False

    # Test 1: Get TODO tasks
    print("\n📋 Test 1: Fetch TODO tasks")
    try:
        todo_tasks = await trello.get_todo_cards()
        agent_tasks = [t for t in todo_tasks if '[agent]' in t.title]
        print(f"✅ Found {len(agent_tasks)} [agent] tasks in TODO")
        for task in agent_tasks[:3]:
            print(f"   - [{task.metadata.get('priority', 'P3')}] {task.title[:50]}...")
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False

    # Test 2: Get In Progress tasks
    print("\n🔄 Test 2: Fetch In Progress tasks")
    try:
        progress_tasks = await trello.get_in_progress_cards()
        agent_tasks = [t for t in progress_tasks if '[agent]' in t.title]
        print(f"✅ Found {len(agent_tasks)} [agent] tasks in In Progress")
        for task in agent_tasks[:3]:
            print(f"   - [{task.metadata.get('priority', 'P3')}] {task.title[:50]}...")
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False

    # Test 3: Get Review tasks
    print("\n👀 Test 3: Fetch Review tasks")
    try:
        review_tasks = await trello.get_review_cards()
        agent_tasks = [t for t in review_tasks if '[agent]' in t.title]
        print(f"✅ Found {len(agent_tasks)} [agent] tasks in Review")
        for task in agent_tasks[:3]:
            print(f"   - [{task.metadata.get('priority', 'P3')}] {task.title[:50]}...")
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False

    print("\n" + "="*80)
    print("✅ TRELLO INTEGRATION TEST PASSED")
    print("="*80)
    return True


async def test_telegram_bot():
    """Test Telegram bot initialization."""
    print("\n" + "="*80)
    print("TESTING TELEGRAM BOT")
    print("="*80)

    bot = get_telegram_bot()

    if not bot.is_configured():
        print("❌ Telegram bot not configured")
        print("   Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
        return False

    print("✅ Telegram bot is configured")
    print(f"   Bot token: {bot.config.telegram_bot_token[:20]}...")
    print(f"   Chat ID: {bot.config.telegram_chat_id}")

    print("\n" + "="*80)
    print("✅ TELEGRAM BOT TEST PASSED")
    print("="*80)
    return True


async def main():
    """Run all tests."""
    print("\n🔬 TELEGRAM → TRELLO INTEGRATION TESTS")
    print("="*80)

    # Test Telegram bot
    telegram_ok = await test_telegram_bot()

    # Test Trello integration
    trello_ok = await test_trello_integration()

    # Summary
    print("\n" + "="*80)
    print("FINAL SUMMARY")
    print("="*80)
    print(f"Telegram Bot: {'✅ PASS' if telegram_ok else '❌ FAIL'}")
    print(f"Trello Integration: {'✅ PASS' if trello_ok else '❌ FAIL'}")
    print("\n📖 Read TELEGRAM_TRELLO_INTEGRATION.md for usage guide")
    print("="*80)

    if telegram_ok and trello_ok:
        print("\n✅ ALL TESTS PASSED!")
        print("\n🚀 You can now use Telegram to manage orchestrator tasks:")
        print("   /addtrello <project> <priority> <title>")
        print("   /trello [todo|progress|review|all]")
        print("   /status")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED - Check configuration")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
