#!/usr/bin/env python3
"""
Test Script for Orchestrator End-to-End

This script tests the orchestrator with a dummy task for wikipedia-analytics project.
"""

import asyncio
import sys
import traceback
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from agents.orchestrator.main_orchestrator import create_orchestrator
from agents import register_all_agents
from agents.base.agent_interface import get_agent_registry
from utils.logger import configure_logging, get_logger
from config.settings import get_settings


# Test task for wikipedia-analytics
TEST_TASK = """
[wikipedia-analytics] [agent] Create a simple test function

## Description:
Create a simple test function in the wikipedia-analytics project to verify the orchestrator is working.

## Requirements:
1. Create a file called `test_orchestrator.py` in the workspace directory (/home/ubuntu/workspace/test_orchestrator.py)
2. Add a simple function called `hello_orchestrator()` that returns a greeting
3. The function should include proper documentation
4. Run a quick test to verify it works

This is a simple test to verify the orchestrator can coordinate agents to complete a task.

## Working Directory:
/home/ubuntu/workspace
"""


async def test_orchestrator():
    """Test the orchestrator end-to-end."""
    # Configure logging
    configure_logging()
    logger = get_logger("test_orchestrator")
    logger.info("="*60)
    logger.info("ORCHESTRATOR END-TO-END TEST")
    logger.info("="*60)

    # Check configuration
    settings = get_settings()
    logger.info("Configuration check")
    logger.info(f"  Environment: {settings.environment}")
    logger.info(f"  Default Model: {settings.default_model}")
    logger.info(f"  Anthropic API Key: {'✓ Set' if settings.anthropic_api_key else '✗ Not set'}")
    logger.info(f"  OpenAI API Key: {'✓ Set' if settings.openai_api_key else '✗ Not set'}")
    logger.info(f"  Redis: {settings.redis_host}:{settings.redis_port}")
    logger.info(f"  Qdrant: {settings.qdrant_host}:{settings.qdrant_port}")

    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY not set - orchestrator may not work properly")
        logger.warning("Set it in .env file or via environment variable")

    # Step 1: Register all agents
    logger.info("\n" + "-"*60)
    logger.info("STEP 1: Registering all agents")
    logger.info("-"*60)
    try:
        register_all_agents()
        registry = get_agent_registry()
        registered_agents = registry.list_agents()
        logger.info(f"✓ Registered {len(registered_agents)} agents:")
        for agent_name in registered_agents:
            logger.info(f"  - {agent_name}")
    except Exception as e:
        logger.error(f"✗ Failed to register agents: {e}")
        traceback.print_exc()
        return False

    # Step 2: Create orchestrator
    logger.info("\n" + "-"*60)
    logger.info("STEP 2: Creating orchestrator")
    logger.info("-"*60)
    try:
        orchestrator = await create_orchestrator()
        logger.info("✓ Orchestrator created successfully")

        # Get orchestrator status
        status = await orchestrator.get_status()
        logger.info(f"  Claude enabled: {status.get('claude_enabled', False)}")
        logger.info(f"  Worker agents: {status.get('worker_agents', [])}")
    except Exception as e:
        logger.error(f"✗ Failed to create orchestrator: {e}")
        traceback.print_exc()
        return False

    # Step 3: Execute test task
    logger.info("\n" + "-"*60)
    logger.info("STEP 3: Executing test task")
    logger.info("-"*60)
    logger.info(f"Task: {TEST_TASK[:100]}...")

    try:
        result = await orchestrator.execute(TEST_TASK)

        logger.info(f"\n✓ Task execution completed")
        logger.info(f"  Status: {result.status}")
        logger.info(f"  Duration: {result.duration_ms}ms")

        if result.output:
            logger.info(f"\nOutput:\n{result.output}")

        if result.is_success():
            logger.info(f"\n✓✓✓ TASK SUCCEEDED ✓✓✓")
        elif result.is_partial():
            logger.warning(f"\n⚠⚠⚠ TASK PARTIALLY SUCCEEDED ⚠⚠⚠")
        else:
            logger.error(f"\n✗✗✗ TASK FAILED ✗✗✗")

        if result.errors:
            logger.error(f"\nErrors:")
            for error in result.errors:
                logger.error(f"  - {error}")

        if result.next_steps:
            logger.info(f"\nNext steps:")
            for step in result.next_steps:
                logger.info(f"  - {step}")

        if result.metadata:
            logger.info(f"\nMetadata:")
            for key, value in result.metadata.items():
                logger.info(f"  {key}: {value}")

        return result.is_success()

    except Exception as e:
        logger.error(f"✗ Task execution failed with exception: {e}")
        traceback.print_exc()
        return False


async def test_direct_agent_call():
    """Test direct agent call without orchestrator."""
    logger = get_logger("test_direct_agent")
    logger.info("\n" + "="*60)
    logger.info("DIRECT AGENT CALL TEST")
    logger.info("="*60)

    from agents.workers.coding_agent import create_coding_agent
    from agents.base.agent_interface import get_agent_registry

    try:
        # Create and register coding agent
        registry = get_agent_registry()
        if not registry.is_registered("coding_agent"):
            coding_agent = await create_coding_agent()
            registry.register("coding_agent", coding_agent)
            logger.info("✓ Coding agent registered")

        # Test direct call with proper workspace path
        simple_task = "Create a function called hello_world() in /home/ubuntu/workspace/hello_world.py that returns 'Hello, World!'"

        logger.info(f"Testing direct agent call: {simple_task}")
        result = await registry.call_agent("coding_agent", simple_task, file_path="/home/ubuntu/workspace/hello_world.py")

        logger.info(f"Result status: {result.status}")
        if result.output:
            logger.info(f"Output:\n{result.output[:500]}")

        if result.errors:
            logger.error(f"Errors: {result.errors}")

        return result.is_success()

    except Exception as e:
        logger.error(f"✗ Direct agent call failed: {e}")
        traceback.print_exc()
        return False


async def main():
    """Main test runner."""
    logger = get_logger("main")

    print("\n" + "="*70)
    print(" " * 15 + "ORCHESTRATOR E2E TEST SUITE")
    print("="*70 + "\n")

    # Run orchestrator test
    orchestrator_success = await test_orchestrator()

    # Run direct agent test as fallback
    if not orchestrator_success:
        logger.info("\n" + "="*60)
        logger.info("Running fallback direct agent test...")
        logger.info("="*60)
        direct_success = await test_direct_agent_call()
    else:
        direct_success = True

    # Summary
    print("\n" + "="*70)
    print(" " * 25 + "TEST SUMMARY")
    print("="*70)
    print(f"Orchestrator Test: {'✓ PASSED' if orchestrator_success else '✗ FAILED'}")
    print(f"Direct Agent Test: {'✓ PASSED' if direct_success else '✗ FAILED'}")
    print("="*70 + "\n")

    return 0 if (orchestrator_success or direct_success) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
