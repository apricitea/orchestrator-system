#!/usr/bin/env python3
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
logger = get_logger("e2e_test")

GREEN = "\033[92m"
RED = "\033[91m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"

CARD_ID = "697f1165560a0f67e4f30ec1"
EXPECTED_KEYWORDS = ["url", "validator"]

async def monitor():
    shutdown_event = asyncio.Event()

    # Start daemon
    print(f"{BOLD}{BLUE}Starting daemon...{RESET}")
    daemon = WorkerDaemon()

    def signal_handler(signum, frame):
        print(f"\n{BLUE}Stopping...{RESET}")
        shutdown_event.set()
        asyncio.create_task(daemon.stop())

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    async def run_daemon():
        try:
            await daemon.start()
        except Exception as e:
            print(f"{RED}Daemon crashed: {e}{RESET}")
            shutdown_event.set()

    daemon_task = asyncio.create_task(run_daemon())

    # Monitor
    print(f"{BLUE}Monitoring task {CARD_ID[:8]}...{RESET}\n")
    start_time = datetime.now()
    check_interval = 15
    last_status = "TODO"
    pr_number = None

    try:
        while not shutdown_event.is_set():
            elapsed = (datetime.now() - start_time).total_seconds()

            if elapsed > 900:
                print(f"{BLUE}Timeout reached{RESET}")
                break

            try:
                trello = get_trello_client()
                lists = await trello.get_lists()
                current_status = None

                for list_name, list_id in lists.items():
                    import httpx
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.get(
                            f"{trello._base_url}/lists/{list_id}/cards",
                            params=trello._auth_params,
                        )
                        response.raise_for_status()
                        cards = response.json()

                        for card in cards:
                            if card["id"] == CARD_ID:
                                current_status = list_name.upper()

                                if current_status == "REVIEW" and not pr_number:
                                    # Get PR number
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
                                                print(f"\n{GREEN}✅ PR #{pr_number} created{RESET}")

                                                # Check PR title
                                                import subprocess
                                                result = subprocess.run([
                                                    'gh', 'pr', 'view', str(pr_number),
                                                    '--repo', 'TheCurators/laptop-recommendation',
                                                    '--json', 'title'
                                                ], env=os.environ, capture_output=True, text=True)

                                                if result.returncode == 0:
                                                    import json
                                                    pr_data = json.loads(result.stdout)
                                                    pr_title = pr_data.get("title", "")

                                                    print(f"\n{BOLD}PR Title:{RESET} {pr_title}")

                                                    # Check if title is correct
                                                    title_lower = pr_title.lower()
                                                    has_expected = any(kw in title_lower for kw in EXPECTED_KEYWORDS)

                                                    if has_expected:
                                                        print(f"{GREEN}✅ FIX 1: PR Title is CORRECT!{RESET}")
                                                    else:
                                                        print(f"{RED}❌ FIX 1: PR Title is WRONG{RESET}")

                                elif current_status == "DONE":
                                    print(f"\n{GREEN}✅ Task reached DONE!{RESET}")
                                    shutdown_event.set()
                                    break

                    if current_status:
                        break

                if current_status and current_status != last_status:
                    elapsed_str = str(int(elapsed))
                    print(f"{BLUE}[{elapsed_str}s] {last_status} → {current_status}{RESET}")
                    last_status = current_status

                await asyncio.sleep(check_interval)

            except Exception as e:
                logger.error("Error checking status", error=str(e))

    except Exception as e:
        logger.error("Monitor error", error=str(e))

    finally:
        print(f"\n{BLUE}Stopping daemon...{RESET}")
        shutdown_event.set()
        try:
            await asyncio.wait_for(daemon.stop(), timeout=30)
            print(f"{GREEN}✅ Daemon stopped{RESET}")
        except asyncio.TimeoutError:
            print(f"{BLUE}Daemon stop timed out{RESET}")

        daemon_task.cancel()
        try:
            await daemon_task
        except asyncio.CancelledError:
            pass

if __name__ == "__main__":
    asyncio.run(monitor())
