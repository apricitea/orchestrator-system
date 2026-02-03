#!/usr/bin/env python3
"""
AI Agent VPS - Main Entry Point

This is the main entry point for the autonomous CLI coding agent system.
"""

import asyncio
import sys

from agents.orchestrator.main_orchestrator import create_orchestrator
from agents.workers.coding_agent import create_coding_agent
from agents.workers.testing_agent import create_testing_agent
from agents.workers.git_agent import create_git_agent
from agents.workers.review_agent import create_review_agent
from agents.workers.debug_agent import create_debug_agent
from agents.workers.docs_agent import create_docs_agent
from agents.workers.deploy_agent import create_deploy_agent
from agents.base.agent_interface import get_agent_registry
from config.settings import get_settings
from utils.logger import configure_logging, get_logger


async def initialize_system():
    """Initialize the AI agent system."""
    settings = get_settings()

    # Configure logging
    configure_logging()
    logger = get_logger("main")
    logger.info("Initializing AI Agent VPS", environment=settings.environment)

    # Validate configuration
    if not settings.anthropic_api_key:
        logger.warning("No ANTHROPIC_API_KEY set - system will run in degraded mode")

    # Get agent registry
    registry = get_agent_registry()

    # Create and register worker agents
    logger.info("Creating worker agents")

    coding_agent = await create_coding_agent()
    registry.register("coding_agent", coding_agent)
    logger.info("Registered coding_agent (LLM-powered)")

    testing_agent = await create_testing_agent()
    registry.register("testing_agent", testing_agent)
    logger.info("Registered testing_agent (LLM-powered)")

    git_agent = await create_git_agent()
    registry.register("git_agent", git_agent)
    logger.info("Registered git_agent")

    review_agent = await create_review_agent()
    registry.register("review_agent", review_agent)
    logger.info("Registered review_agent (LLM-powered)")

    debug_agent = await create_debug_agent()
    registry.register("debug_agent", debug_agent)
    logger.info("Registered debug_agent (LLM-powered)")

    docs_agent = await create_docs_agent()
    registry.register("docs_agent", docs_agent)
    logger.info("Registered docs_agent (LLM-powered)")

    deploy_agent = await create_deploy_agent()
    registry.register("deploy_agent", deploy_agent)
    logger.info("Registered deploy_agent (LLM-powered)")

    # Create orchestrator
    logger.info("Creating orchestrator agent")
    orchestrator = await create_orchestrator()

    logger.info("System initialization complete")
    logger.info("Registered agents", agents=registry.list_agents())

    return orchestrator


async def interactive_mode(orchestrator):
    """Run in interactive mode."""
    logger = get_logger("interactive")

    print("\n" + "="*60)
    print("AI Agent VPS - Interactive Mode")
    print("="*60)
    print("Type your tasks below (or 'quit' to exit)")
    print("-"*60 + "\n")

    while True:
        try:
            task = input(">> ").strip()

            if not task:
                continue

            if task.lower() in ["quit", "exit", "q"]:
                print("\nGoodbye!")
                break

            print(f"\nExecuting: {task}")
            print("-"*40)

            result = await orchestrator.execute(task)

            if result.is_success():
                print("✓ Success")
                if result.output:
                    print(f"\n{result.output}")
                if result.metadata.get("tokens_used"):
                    print(f"\nTokens used: {result.metadata['tokens_used']}")
                if result.next_steps:
                    print("\nNext steps:")
                    for step in result.next_steps:
                        print(f"  - {step}")
            elif result.is_partial():
                print("⚠ Partial Success")
                if result.output:
                    print(f"\n{result.output}")
                if result.errors:
                    print("\nErrors:")
                    for error in result.errors:
                        print(f"  - {error}")
            else:
                print("✗ Failed")
                if result.errors:
                    print("\nErrors:")
                    for error in result.errors:
                        print(f"  - {error}")

            print(f"\nDuration: {result.duration_ms}ms")
            print("-"*40 + "\n")

        except KeyboardInterrupt:
            print("\n\nInterrupted. Use 'quit' to exit.")
        except Exception as e:
            logger.error("Unexpected error", error=str(e))
            print(f"\nError: {e}\n")


async def task_mode(orchestrator, task: str):
    """Execute a single task and exit."""
    logger = get_logger("task_mode")

    logger.info("Executing task", task=task)

    result = await orchestrator.execute(task)

    if result.is_success():
        print(f"✓ Success: {task}")
        if result.output:
            print(f"\n{result.output}")
        if result.metadata.get("tokens_used"):
            print(f"\nTokens used: {result.metadata['tokens_used']}")
        if result.next_steps:
            print("\nNext steps:")
            for step in result.next_steps:
                print(f"  - {step}")
        return 0
    elif result.is_partial():
        print(f"⚠ Partial Success: {task}")
        if result.output:
            print(f"\n{result.output}")
        if result.errors:
            print("\nErrors:")
            for error in result.errors:
                print(f"  - {error}")
        return 1
    else:
        print(f"✗ Failed: {task}")
        if result.errors:
            print("\nErrors:")
            for error in result.errors:
                print(f"  - {error}")
        return 2


async def status_mode():
    """Show system status."""
    from config.settings import get_settings
    settings = get_settings()

    print("\n" + "="*60)
    print("AI Agent VPS - System Status")
    print("="*60)

    print(f"\nEnvironment: {settings.environment}")
    print(f"Debug Mode: {settings.debug}")
    print(f"\nLLM Configuration:")
    print(f"  Default Model: {settings.default_model}")
    print(f"  Fallback Model: {settings.fallback_model}")
    print(f"  Small Model: {settings.small_model}")

    api_keys = []
    if settings.anthropic_api_key:
        api_keys.append("✓ Anthropic API")
    if settings.openai_api_key:
        api_keys.append("✓ OpenAI API")

    if api_keys:
        print(f"\nAPI Keys:")
        for key in api_keys:
            print(f"  {key}")
    else:
        print(f"\n⚠ No API keys configured!")

    print(f"\nMemory Systems:")
    print(f"  Redis: {settings.redis_host}:{settings.redis_port}")
    print(f"  Qdrant: {settings.qdrant_host}:{settings.qdrant_port}")

    print(f"\nSecurity:")
    print(f"  Sandbox: {'Enabled' if settings.sandbox_enabled else 'Disabled'}")
    print(f"  Workspace: {settings.sandbox_workspace}")

    print("\n" + "="*60 + "\n")
    return 0


async def main():
    """Main entry point."""
    # Check for status command
    if len(sys.argv) > 1 and sys.argv[1] in ["--status", "-s"]:
        return await status_mode()

    # Check for help command
    if len(sys.argv) > 1 and sys.argv[1] in ["--help", "-h"]:
        print("""
AI Agent VPS - Autonomous CLI Coding Agent System

Usage:
  python main.py              Interactive mode
  python main.py --task TASK  Execute single task
  python main.py --status     Show system status
  python main.py --help       Show this help

Examples:
  python main.py --task "Implement user authentication"
  python main.py --task "Fix the login bug"
  python main.py --task "Add tests for payment module"
  python main.py              # Interactive mode

Environment Variables:
  ANTHROPIC_API_KEY         Anthropic API key (required)
  OPENAI_API_KEY             OpenAI API key (optional fallback)
  REDIS_HOST                 Redis host (default: localhost)
  QDRANT_HOST                Qdrant host (default: localhost)

For more information, see README.md
""")
        return 0

    # Check for task mode
    if len(sys.argv) > 1 and sys.argv[1] == "--task":
        if len(sys.argv) > 2:
            orchestrator = await initialize_system()
            task = " ".join(sys.argv[2:])
            return await task_mode(orchestrator, task)
        else:
            print("Error: --task requires a task description")
            return 1

    # Default: interactive mode
    orchestrator = await initialize_system()
    await interactive_mode(orchestrator)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
