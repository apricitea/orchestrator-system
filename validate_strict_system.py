#!/usr/bin/env python3
"""
Validate Strict E2E System Setup

Run this to verify everything is configured correctly
before running the autonomous agent system.
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, "/home/ubuntu")

from agents.validation.strict_validator import get_strict_validator
from agents.notification.telegram_notifier import get_telegram_notifier
from utils.logger import get_logger


def load_env_file():
    """Load environment variables from .env file."""
    env_file = Path("/home/ubuntu/.env")
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    # Remove quotes if present
                    value = value.strip().strip('"').strip("'")
                    os.environ[key] = value


def check_environment():
    """Check environment variables."""
    print("\n" + "="*80)
    print("CHECKING ENVIRONMENT VARIABLES")
    print("="*80)

    required_vars = {
        "GITHUB_TOKEN": "GitHub personal access token",
        "TELEGRAM_BOT_TOKEN": "Telegram bot token from BotFather",
        "TELEGRAM_CHAT_ID": "Telegram chat ID for notifications",
        "ANTHROPIC_API_KEY": "Anthropic API key for Claude",
    }

    optional_vars = {
        "TRELLO_API_KEY": "Trello API key",
        "TRELLO_TOKEN": "Trello API token",
    }

    all_good = True

    print("\nRequired Variables:")
    for var, desc in required_vars.items():
        value = os.getenv(var)
        if value:
            masked = value[:4] + "*" * (len(value) - 8) + value[-4:] if len(value) > 8 else "****"
            print(f"  ✅ {var}: {masked}")
        else:
            print(f"  ❌ {var}: NOT SET ({desc})")
            all_good = False

    print("\nOptional Variables:")
    for var, desc in optional_vars.items():
        value = os.getenv(var)
        if value:
            masked = value[:4] + "*" * (len(value) - 8) + value[-4:] if len(value) > 8 else "****"
            print(f"  ✅ {var}: {masked}")
        else:
            print(f"  ⚠️  {var}: Not set (optional)")

    return all_good


def check_projects():
    """Check projects in /home/ubuntu/projects/."""
    print("\n" + "="*80)
    print("CHECKING PROJECTS")
    print("="*80)

    projects_path = Path("/home/ubuntu/projects")

    if not projects_path.exists():
        print(f"  ❌ Projects directory not found: {projects_path}")
        return []

    # Find all git repositories
    projects = []
    for item in projects_path.iterdir():
        if item.is_dir() and (item / ".git").exists():
            projects.append(item.name)

    if not projects:
        print("  ⚠️  No projects found")
        print("     Add projects with: git clone git@github.com:TheCurators/{project}.git")
        return []

    print(f"\n  Found {len(projects)} project(s):")
    for project in projects:
        print(f"    📁 {project}")

    return projects


async def validate_project_setup(project_name: str):
    """Validate a single project."""
    print("\n" + "-"*80)
    print(f"VALIDATING PROJECT: {project_name}")
    print("-"*80)

    validator = get_strict_validator()
    result = await asyncio.to_thread(
        validator.validate_project_setup,
        project_name
    )

    if result.passed:
        print(f"  ✅ Project '{project_name}' is VALID")
        print(f"  Checks passed:")
        for check, passed in result.details["checks"].items():
            status = "✅" if passed else "❌"
            print(f"    {status} {check}")
        return True
    else:
        print(f"  ❌ Project '{project_name}' validation FAILED")
        print(f"  Severity: {result.severity}")
        print(f"  Message: {result.message}")

        if result.details:
            failed = result.details.get("failed_zero_tolerance", [])
            if failed:
                print(f"  Failed checks: {', '.join(failed)}")

        if result.fix_suggestion:
            print(f"\n  💡 Fix Suggestion:")
            for line in result.fix_suggestion.split("\n"):
                print(f"     {line}")

        return False


async def test_telegram_notification():
    """Test Telegram notification."""
    print("\n" + "="*80)
    print("TESTING TELEGRAM NOTIFICATION")
    print("="*80)

    notifier = get_telegram_notifier()

    if not notifier.bot_token or not notifier.chat_id:
        print("  ⚠️  Telegram credentials not configured")
        print("     Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables")
        return False

    print("  Sending test notification...")

    success = await notifier.send_escalation_notification(
        reason="System validation test",
        project_name="validation-test",
        task_url="https://trello.com/test",
        context={"test": True},
    )

    if success:
        print("  ✅ Test notification sent successfully")
        print("  Check your Telegram for the message")
        return True
    else:
        print("  ❌ Failed to send test notification")
        print("  Check your bot token and chat ID")
        return False


async def main():
    """Main validation function."""
    # Load environment variables from .env file first
    load_env_file()

    logger = get_logger("validate_system")

    print("\n" + "="*80)
    print("🔍 STRICT E2E SYSTEM VALIDATION")
    print("="*80)
    print("\nThis script validates your system setup")
    print("Run this before starting the autonomous agent system")

    # Check environment
    env_ok = check_environment()

    # Check projects
    projects = check_projects()

    # Validate each project
    if projects:
        print("\n" + "="*80)
        print("VALIDATING ALL PROJECTS")
        print("="*80)

        project_results = {}
        for project in projects:
            project_results[project] = await validate_project_setup(project)

    # Test Telegram
    telegram_ok = await test_telegram_notification()

    # Final summary
    print("\n" + "="*80)
    print("VALIDATION SUMMARY")
    print("="*80)

    print(f"\nEnvironment Variables: {'✅ OK' if env_ok else '❌ FAILED'}")
    print(f"Projects Found: {len(projects)}")
    print(f"Projects Valid: {sum(1 for p in project_results.values() if p) if projects else 0}/{len(projects)}")
    print(f"Telegram: {'✅ OK' if telegram_ok else '❌ FAILED'}")

    all_good = env_ok and telegram_ok

    if projects:
        all_good = all_good and all(project_results.values())

        if not all(project_results.values()):
            print("\n❌ Some projects failed validation:")
            for project, valid in project_results.items():
                if not valid:
                    print(f"   • {project}")

    print("\n" + "="*80)
    if all_good:
        print("✅ SYSTEM VALIDATION PASSED")
        print("="*80)
        print("\nYour system is ready to run the strict E2E autonomous agent!")
        print("\nNext steps:")
        print("  1. Create Trello tasks with format: [{project}] [agent] P{level}: {description}")
        print("  2. Run the orchestrator to pick up and execute tasks")
        print("  3. Monitor Telegram for PR approval notifications")
        return 0
    else:
        print("❌ SYSTEM VALIDATION FAILED")
        print("="*80)
        print("\nPlease fix the issues above before running the system.")
        print("\nSee STRICT_SYSTEM_GUIDE.md for detailed setup instructions.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
