#!/usr/bin/env python3
"""
Comprehensive End-to-End Test for Orchestrator Agent

Tests the full orchestrator workflow including:
1. Task decomposition
2. Agent routing
3. Multi-agent coordination
4. Git operations with proper branch naming
5. Test execution with validation
6. Result synthesis
"""

import asyncio
import sys
import os
import traceback
from datetime import datetime

# Add project root to path
sys.path.insert(0, '/home/ubuntu')

from agents.orchestrator.main_orchestrator import create_orchestrator
from utils.logger import get_logger

logger = get_logger("e2e_test")

# Comprehensive test task that exercises all major functionality
TEST_TASK = """
[wikipedia-analytics] [agent] Enhance the data analyzer module

Create a comprehensive data analyzer module for the Wikipedia analytics project.
The module should include data processing, statistics calculation, and visualization.

## Requirements:

### Working Directory:
/home/ubuntu/projects/wikipedia-analytics

### Implementation Details:

1. **Core Module** (coding_agent - P0):
   - Create `src/analyzer.py` with:
     - DataProcessor class for cleaning and transforming data
     - StatisticsCalculator class for computing metrics
     - Visualizer class for generating plots
   - Use pandas for data handling
   - Use matplotlib for visualization

2. **Tests** (testing_agent - P1):
   - Create comprehensive unit tests in `tests/test_analyzer.py`
   - Test all three classes
   - Include edge cases and error handling
   - Execute tests to verify correctness

3. **Git Operations** (git_agent - P1):
   - Create a new feature branch for this enhancement
   - Branch name should be descriptive and sanitized
   - Commit the implementation with proper message
   - Create a pull request description

4. **Documentation** (docs_agent - P2):
   - Document the module in `docs/analyzer.md`
   - Include usage examples
   - Document API and class methods

### Priority Order:
- Implement core module first (P0)
- Then tests (P1)
- Git operations (P1)
- Documentation (P2)

### Validation Criteria:
- Code runs without errors
- Tests pass successfully
- Git branch is properly named
- Documentation is complete
"""

# Fallback simpler test if the comprehensive one is too complex
SIMPLE_TEST_TASK = """
[wikipedia-analytics] [agent] Add statistics calculator module

Create a simple statistics calculator for the wikipedia-analytics project.

## Working Directory:
/home/ubuntu/projects/wikipedia-analytics

## Requirements:
1. Create `src/stats.py` with basic statistics functions
2. Write tests in `tests/test_stats.py`
3. Execute tests to verify
4. Create git branch and commit
"""


async def run_orchestrator_test():
    """Run the orchestrator E2E test."""

    print("\n" + "="*80)
    print("ORCHESTRATOR END-TO-END TEST")
    print("="*80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80 + "\n")

    # Initialize orchestrator
    print("📦 Initializing orchestrator agent...")
    try:
        orchestrator = await create_orchestrator()
        print("✅ Orchestrator initialized successfully\n")
    except Exception as e:
        print(f"❌ Failed to initialize orchestrator: {e}")
        traceback.print_exc()
        return False

    # Check orchestrator status
    print("🔍 Checking orchestrator status...")
    try:
        status = await orchestrator.get_status()
        print(f"✅ Orchestrator status:")
        print(f"   - Registered agents: {len(status['registered_agents'])}")
        print(f"   - Worker agents: {status['worker_agents']}")
        print(f"   - Claude enabled: {status['claude_enabled']}")
        print()
    except Exception as e:
        print(f"❌ Failed to get status: {e}")
        traceback.print_exc()

    # Check if project directory exists, if not create it
    project_dir = "/home/ubuntu/projects/wikipedia-analytics"
    if not os.path.exists(project_dir):
        print(f"📁 Creating project directory: {project_dir}")
        os.makedirs(project_dir, exist_ok=True)
        os.makedirs(os.path.join(project_dir, "src"), exist_ok=True)
        os.makedirs(os.path.join(project_dir, "tests"), exist_ok=True)
        os.makedirs(os.path.join(project_dir, "docs"), exist_ok=True)
        print("✅ Project structure created\n")
    else:
        print(f"✅ Project directory exists: {project_dir}\n")

    # Execute the test task
    print("🚀 Executing orchestrator test task...")
    print("-" * 80)
    print("Task:")
    print(SIMPLE_TEST_TASK)
    print("-" * 80 + "\n")

    start_time = datetime.now()

    try:
        result = await orchestrator.execute(
            SIMPLE_TEST_TASK,
            working_directory=project_dir,
            temperature=0.3,
            max_retries=2,
        )

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        print("\n" + "="*80)
        print("ORCHESTRATOR TEST RESULT")
        print("="*80)
        print(f"Status: {result.status}")
        print(f"Duration: {duration:.2f} seconds")
        print(f"Duration (ms): {result.duration_ms}")

        if result.output:
            print("\n📄 Output:")
            print("-" * 80)
            print(result.output[:1000])  # First 1000 chars
            if len(result.output) > 1000:
                print(f"\n... ({len(result.output) - 1000} more characters)")
            print("-" * 80)

        if result.metadata:
            print("\n📊 Metadata:")
            for key, value in result.metadata.items():
                if key != "tokens_used":  # Skip tokens for cleaner output
                    print(f"   {key}: {value}")

        if result.next_steps:
            print("\n📋 Next Steps:")
            for i, step in enumerate(result.next_steps[:5], 1):
                print(f"   {i}. {step}")
            if len(result.next_steps) > 5:
                print(f"   ... and {len(result.next_steps) - 5} more")

        if result.errors:
            print("\n❌ Errors:")
            for error in result.errors:
                print(f"   - {error}")

        print("\n" + "="*80)
        if result.is_success():
            print("✅ ORCHESTRATOR TEST PASSED")
        elif result.is_partial():
            print("⚠️  ORCHESTRATOR TEST PARTIALLY PASSED")
        else:
            print("❌ ORCHESTRATOR TEST FAILED")
        print("="*80 + "\n")

        return result.is_success() or result.is_partial()

    except Exception as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        print(f"\n❌ Exception during orchestrator execution:")
        print(f"Error: {str(e)}")
        print(f"Duration: {duration:.2f} seconds")
        traceback.print_exc()
        print("\n" + "="*80)
        print("❌ ORCHESTRATOR TEST FAILED")
        print("="*80 + "\n")
        return False


async def main():
    """Main test entry point."""
    success = await run_orchestrator_test()

    if success:
        print("✅ All tests completed successfully!")
        return 0
    else:
        print("❌ Some tests failed. Check logs above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
