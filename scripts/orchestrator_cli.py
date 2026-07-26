#!/usr/bin/env python3
"""
Orchestrator CLI - Command-line interface for managing the AI worker system.

Provides easy commands to:
- Start/stop the daemon
- Run tasks manually
- Check system status
- Clean up branches
- View logs
"""

import asyncio
import sys
import subprocess

sys.path.insert(0, "/home/ubuntu")

from worker.git_utils import GitUtils
from worker.monitoring import get_system_monitor
from worker.telegram.bot import get_telegram_bot
from worker.trello.client import get_trello_client


async def cmd_status():
    """Show system status."""
    print("╔═══════════════════════════════════════════════════════════════╗")
    print("║                    SYSTEM STATUS                              ║")
    print("╚═══════════════════════════════════════════════════════════════╝\n")

    # System status
    monitor = get_system_monitor()
    status = await monitor.get_system_status()

    if "error" in status:
        print(f"❌ Error: {status['error']}")
        return 1

    # System resources
    sys_status = status.get("system", {})
    print(f"🖥️  System Resources:")
    print(f"   CPU: {sys_status.get('cpu_percent', 'N/A')}%")
    mem = sys_status.get("memory", {})
    print(f"   Memory: {mem.get('used_percent', 'N/A')}% used ({mem.get('available_gb', 'N/A')} GB available)")
    disk = sys_status.get("disk", {})
    print(f"   Disk: {disk.get('used_percent', 'N/A')}% used ({disk.get('free_gb', 'N/A')} GB free)\n")

    # Running processes
    processes = status.get("processes", {})
    print(f"🔄 Running Processes: {processes.get('count', 0)}")
    for proc in processes.get("processes", [])[:5]:
        print(f"   - PID {proc['pid']}: {proc['name']} ({proc['memory_percent']:.1f}% RAM)")

    # Task queue
    queue_status = await monitor.get_task_queue_status()
    print(f"\n📋 Task Queue:")
    trello = queue_status.get("trello", {})
    if trello.get("configured"):
        print(f"   TODO: {trello.get('todo', 0)} tasks")
        print(f"   In Progress: {trello.get('in_progress', 0)} tasks")
        print(f"   Review: {trello.get('review', 0)} tasks")
    else:
        print(f"   ⚠️  Trello not configured")

    # Telegram bot
    print(f"\n🤖 Telegram Bot:")
    bot = get_telegram_bot()
    if bot.is_configured():
        # Check if running
        result = subprocess.run(
            ["pgrep", "-f", "start_telegram_bot.py"],
            capture_output=True,
        )
        if result.returncode == 0:
            print(f"   ✅ Running")
        else:
            print(f"   ❌ Not running (start with: start_telegram_bot)")
    else:
        print(f"   ⚠️  Not configured")

    return 0


async def cmd_cleanup(args):
    """Clean up old git branches."""
    repo = args.get("--repo", "/home/ubuntu/projects/laptop-recommendation")
    dry_run = "--dry-run" in args
    days = int(args.get("--days", "30"))

    print(f"🧹 Cleaning up old branches in {repo}")
    if dry_run:
        print("   [DRY RUN MODE - no changes will be made]\n")

    git_utils = GitUtils()
    result = git_utils.cleanup_old_branches(
        repo_path=repo,
        days_old=days,
        dry_run=dry_run,
    )

    print(f"\n   Branches found: {result.get('branches_found', 0)}")
    print(f"   Branches deleted: {result.get('branches_deleted', 0)}")
    if result.get("errors"):
        print(f"   Errors: {len(result['errors'])}")
        for error in result['errors'][:3]:
            print(f"      - {error}")

    return 0


async def cmd_review_pr(args):
    """Manually review a PR."""
    import os
    os.chdir("/home/ubuntu")

    repo = args.get("--repo", "/home/ubuntu/projects/laptop-recommendation")
    pr_number = args.get("--pr")

    if not pr_number:
        print("❌ --pr number is required")
        return 1

    try:
        from agents.pr_review_agent.pr_review_agent import get_pr_review_agent

        reviewer = get_pr_review_agent()

        print(f"🔍 Reviewing PR #{pr_number}...")

        # Get PR info first
        result = subprocess.run(
            ["gh", "pr", "view", pr_number, "--json", "headRefName,baseRefName"],
            cwd=repo,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print(f"❌ Failed to get PR info: {result.stderr}")
            return 1

        import json
        pr_info = json.loads(result.stdout)
        branch_name = pr_info["headRefName"]
        base_branch = pr_info["baseRefName"]

        # Run review
        review = await reviewer.review_pr(
            repo_path=repo,
            pr_number=int(pr_number),
            branch_name=branch_name,
            base_branch=base_branch,
        )

        # Post review
        await reviewer.post_review_comment(repo, int(pr_number), review)

        print(f"✅ Review posted for PR #{pr_number}")
        print(f"   Status: {review.get('approval_status', 'unknown').upper()}")
        print(f"   Score: {review.get('overall_score', 'N/A')}/10")

        return 0

    except Exception as e:
        print(f"❌ Review failed: {e}")
        return 1


async def cmd_monitor(args):
    """Start the monitoring API server."""
    from worker.monitoring import StatusAPI

    host = args.get("--host", "0.0.0.0")
    port = int(args.get("--port", "8765"))

    api = StatusAPI(host=host, port=port)

    print(f"🚀 Starting monitoring API on http://{host}:{port}")
    print(f"   Endpoints:")
    print(f"      http://{host}:{port}/status - Full status")
    print(f"      http://{host}:{port}/system - System metrics")
    print(f"      http://{host}:{port}/queue - Task queue status")
    print(f"      http://{host}:{port}/health - Health check")

    await api.start()


async def cmd_run_task(args):
    """Run orchestrator on a Trello task."""
    print("🚀 Running orchestrator on Trello tasks...")

    result = subprocess.run(
        ["/home/ubuntu/venv/bin/python", "/home/ubuntu/run_orchestrator_on_trello.py"],
    )

    return result.returncode


async def cmd_start_daemon(args):
    """Start the worker daemon."""
    print("🚀 Starting worker daemon...")

    result = subprocess.run(
        ["/home/ubuntu/venv/bin/python", "-m", "worker.daemon"],
    )

    return result.returncode


def print_usage():
    """Print usage help."""
    print("""
╔═══════════════════════════════════════════════════════════════╗
║              AI WORKER ORCHESTRATOR CLI                         ║
╚═══════════════════════════════════════════════════════════════╝

Usage: python orchestrator_cli.py <command> [options]

Commands:
  status              Show system status
  cleanup             Clean up old git branches
  review-pr           Review a specific pull request
  monitor             Start monitoring API server
  run-task            Run orchestrator on Trello tasks
  start-daemon        Start the worker daemon
  help                Show this help message

Options:
  --repo <path>       Repository path (default: /home/ubuntu/projects/laptop-recommendation)
  --pr <number>       PR number for review-pr command
  --days <number>     Days threshold for cleanup (default: 30)
  --dry-run           Show what would be done without making changes
  --host <address>    API server host (default: 0.0.0.0)
  --port <number>     API server port (default: 8765)

Examples:
  python orchestrator_cli.py status
  python orchestrator_cli.py cleanup --dry-run --days 7
  python orchestrator_cli.py review-pr --pr 123
  python orchestrator_cli.py monitor --port 9000
  python orchestrator_cli.py run-task
""")


async def main():
    """Main CLI entry point."""
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    command = sys.argv[1].lower()
    args = sys.argv[2:]

    # Parse args into dict
    args_dict = {}
    i = 0
    while i < len(args):
        if args[i].startswith("--"):
            key = args[i][2:]
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                args_dict[key] = args[i + 1]
                i += 2
            else:
                args_dict[key] = True
                i += 1
        else:
            i += 1

    # Execute command
    if command == "status":
        sys.exit(await cmd_status())
    elif command == "cleanup":
        sys.exit(await cmd_cleanup(args_dict))
    elif command == "review-pr":
        sys.exit(await cmd_review_pr(args_dict))
    elif command == "monitor":
        sys.exit(await cmd_monitor(args_dict))
    elif command == "run-task":
        sys.exit(await cmd_run_task(args_dict))
    elif command == "start-daemon":
        sys.exit(await cmd_start_daemon(args_dict))
    elif command in ["help", "-h", "--help"]:
        print_usage()
        sys.exit(0)
    else:
        print(f"❌ Unknown command: {command}")
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
