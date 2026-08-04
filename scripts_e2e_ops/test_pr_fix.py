#!/usr/bin/env python3
"""
Quick test to verify PR title fix.
"""

import asyncio
import os
import sys
import signal
from datetime import datetime
from pathlib import Path

# Load environment
env_file = Path("/home/ubuntu/.env")
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                value = value.strip().strip('"').strip("'")
                os.environ[key] = value

sys.path.insert(0, "/home/ubuntu")
from worker.trello.client import get_trello_client
from worker.daemon import WorkerDaemon
from utils.logger import configure_logging, get_logger

configure_logging()
logger = get_logger("pr_fix_test")

CARD_ID = "697effe6c7821c22978e5c96"
EXPECTED_IN_TITLE = ["email", "validator"]
WRONG_PATTERNS = ["Code Review Checklist", "Implement Code", "template", "checklist", "security checklist"]

async def monitor_task():
    """Monitor task and check PR title when created."""
    shutdown_event = asyncio.Event()

    # Start daemon
    print("🚀 Starting daemon...")
    daemon = WorkerDaemon()

    def signal_handler(signum, frame):
        print("\n🛑 Stopping...")
        shutdown_event.set()
        asyncio.create_task(daemon.stop())

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Start daemon in background
    async def run_daemon():
        try:
            await daemon.start()
        except Exception as e:
            print(f"❌ Daemon crashed: {e}")
            shutdown_event.set()

    daemon_task = asyncio.create_task(run_daemon())

    # Monitor
    print(f"📊 Monitoring task {CARD_ID[:8]}...\n")
    start_time = datetime.now()
    check_interval = 15
    pr_number = None

    try:
        while not shutdown_event.is_set():
            elapsed = (datetime.now() - start_time).total_seconds()

            if elapsed > 600:  # 10 min timeout
                print("⏰ Timeout reached")
                break

            try:
                trello = get_trello_client()

                # Check if card is in REVIEW (PR created)
                lists = await trello.get_lists()
                review_list_id = lists.get("REVIEW")

                if review_list_id:
                    import httpx
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.get(
                            f"{trello._base_url}/lists/{review_list_id}/cards",
                            params=trello._auth_params,
                        )
                        response.raise_for_status()
                        cards = response.json()

                        # Check if our card is in REVIEW
                        for card in cards:
                            if card["id"] == CARD_ID:
                                print(f"✅ Task reached REVIEW! Checking PR...")

                                # Get PR number from card comments
                                actions_response = await client.get(
                                    f"{trello._base_url}/cards/{CARD_ID}/actions",
                                    params={
                                        **trello._auth_params,
                                        "filter": "commentCard",
                                    },
                                )
                                actions_response.raise_for_status()
                                actions = actions_response.json()

                                for action in reversed(actions):
                                    comment_text = action.get("data", {}).get("text", "")
                                    if "PR #" in comment_text:
                                        import re
                                        pr_match = re.search(r'#(\d+)', comment_text)
                                        if pr_match:
                                            pr_number = int(pr_match.group(1))
                                            print(f"📌 Found PR #{pr_number}")
                                            break

                                if pr_number:
                                    # Check PR title
                                    result = await asyncio.create_subprocess_exec(
                                        "gh", "pr", "view", str(pr_number),
                                        "--repo", "TheCurators/laptop-recommendation",
                                        "--json", "title",
                                        stdout=asyncio.subprocess.PIPE,
                                        stderr=asyncio.subprocess.PIPE,
                                    )
                                    stdout, stderr = await result.communicate()

                                    if result.returncode == 0:
                                        import json
                                        pr_data = json.loads(stdout.decode())
                                        pr_title = pr_data.get("title", "")

                                        print(f"\n{'='*80}")
                                        print(f"PR #{pr_number} TITLE:")
                                        print(f"{'='*80}")
                                        print(f"{pr_title}")
                                        print(f"{'='*80}\n")

                                        # Check if title is correct
                                        pr_title_lower = pr_title.lower()

                                        # Check for wrong patterns
                                        has_wrong = any(w.lower() in pr_title_lower for w in WRONG_PATTERNS)
                                        # Check for expected patterns
                                        has_expected = any(e.lower() in pr_title_lower for e in EXPECTED_IN_TITLE)

                                        if has_wrong:
                                            print("❌ FAIL: Title contains template/wrong patterns!")
                                            print(f"   Found: {[w for w in WRONG_PATTERNS if w.lower() in pr_title_lower]}")
                                        elif has_expected:
                                            print("✅ SUCCESS: Title looks correct!")
                                            print(f"   Contains expected: {[e for e in EXPECTED_IN_TITLE if e.lower() in pr_title_lower]}")
                                        else:
                                            print("⚠️  UNCERTAIN: Title doesn't match expected patterns")

                                        # Check test coverage
                                        print("\n📊 Checking test coverage...")
                                        comments_result = await asyncio.create_subprocess_exec(
                                            "gh", "pr", "comments", str(pr_number),
                                            "--repo", "TheCurators/laptop-recommendation",
                                            stdout=asyncio.subprocess.PIPE,
                                            stderr=asyncio.subprocess.PIPE,
                                        )
                                        c_stdout, c_stderr = await comments_result.communicate()

                                        if comments_result.returncode == 0:
                                            comments = c_stdout.decode()
                                            if "Test Coverage:" in comments:
                                                import re
                                                cov_match = re.search(r'Test Coverage:\s*(\d+(?:\.\d+)?)%', comments)
                                                if cov_match:
                                                    coverage = cov_match.group(1)
                                                    print(f"   Test Coverage: {coverage}%")
                                                    if coverage == "0.0" or coverage == "0":
                                                        print("   ✅ Shows 0% instead of N/A - Fix working!")
                                                    elif coverage != "N/A":
                                                        print("   ✅ Shows actual percentage - Fix working!")
                                                    else:
                                                        print("   ❌ Still showing N/A - Fix not working")
                                                else:
                                                    # Check if N/A appears
                                                    if "N/A" in comments:
                                                        print("   ❌ Still showing N/A")
                                                    else:
                                                        print("   ⚠️  Coverage not found in comments")

                                        shutdown_event.set()
                                break

                # Periodic update
                if int(elapsed) % 60 == 0 and int(elapsed) > 0:
                    print(f"⏱️  [{int(elapsed)}s] Still waiting...")

            except Exception as e:
                logger.error("Monitor error", error=str(e))

            await asyncio.sleep(check_interval)

    finally:
        print("\n🛑 Stopping daemon...")
        shutdown_event.set()
        try:
            await asyncio.wait_for(daemon.stop(), timeout=30)
            print("✅ Daemon stopped")
        except asyncio.TimeoutError:
            print("⏰ Daemon stop timed out")

        daemon_task.cancel()
        try:
            await daemon_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(monitor_task())
