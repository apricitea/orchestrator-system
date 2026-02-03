"""
Main Orchestrator Agent - Powered by Claude

The central coordinator for all autonomous coding tasks.
Uses Anthropic's Claude API for intelligent task decomposition and agent coordination.
"""

import asyncio
import json
import re
import time
from typing import Any, Dict, List, Optional

from anthropic import AsyncAnthropic
from agents import register_all_agents  # Import to trigger agent registration
from agents.base.agent_interface import AgentRegistry, get_agent_registry
from agents.base.base_agent import AgentConfig, AgentResult, BaseAgent
from config.settings import get_settings
from memory.memory_manager import get_memory_manager
from utils.logger import AgentLogger, get_logger

# Ensure all agents are registered
register_all_agents()


class TaskDecomposer:
    """
    Decomposes complex tasks into manageable sub-tasks using Claude.

    Uses intelligent reasoning to break down tasks and determine dependencies.
    """

    def __init__(self, client: AsyncAnthropic, model: str):
        """Initialize task decomposer with Claude client."""
        self.client = client
        self.model = model
        self.logger = get_logger("task_decomposer")

        self.system_prompt = """You are an expert task decomposition specialist for autonomous software development with state-of-the-art security and quality practices.

Your role is to analyze user requests and break them down into specific, actionable sub-tasks that can be delegated to specialized worker agents.

## Available Worker Agents:

1. **coding_agent** - Write, generate, and modify code
2. **testing_agent** - Write tests and run test suites
3. **review_agent** - Review code for quality and issues
4. **debug_agent** - Debug issues and fix bugs
5. **docs_agent** - Generate and update documentation
6. **git_agent** - Handle git operations (branches, commits, PRs)
7. **deploy_agent** - Handle deployment operations
8. **security_agent** - Security scanning and vulnerability checks

## CRITICAL - Security & Quality Best Practices (from SkillsMP):

### Security Requirements (MANDATORY):
1. **NEVER hardcode secrets** - Always use environment variables
2. **XSS Prevention** - Escape all user input in templates
3. **SQL Injection** - Use parameterized queries only
4. **Error Handling** - Specific exceptions, proper error messages
5. **Input Validation** - Validate at EVERY layer (defense in depth)

### Code Quality Standards:
1. **No bare except clauses** - Catch specific exceptions
2. **No print statements** - Use proper logging
3. **Debug mode OFF** - Never deploy with debug=True
4. **Descriptive variable names** - No single letters except loop iterators
5. **Modular design** - Single responsibility, no monolithic functions

### Architecture Patterns:
1. **Separation of concerns** - Logic, data, presentation separated
2. **Dependency injection** - Pass dependencies, don't use globals
3. **Error recovery** - Graceful degradation, fail safely
4. **Logging & monitoring** - Structured logging, error tracking

## Task Decomposition Guidelines:

1. **Be Specific**: Each sub-task should have a clear, specific description
2. **Prioritize**: Mark tasks as "high", "medium", or "low" priority
3. **Sequence**: Order tasks logically (dependencies first)
4. **Be Realistic**: Only create tasks that agents can actually complete
5. **Think Step-by-Step**: Consider the full workflow from start to finish
6. **Security First**: Always include security scanning for code changes

## ENHANCED STANDARD WORKFLOW - Include these steps for feature implementation:

For any feature implementation task, ALWAYS include these sub-tasks in this order:

1. **git_agent** - Create feature branch (high priority, no dependencies)
2. **coding_agent** - Implement the feature with security best practices (high priority, depends on branch)
3. **testing_agent** - Write comprehensive unit tests (high priority, depends on code)
4. **testing_agent** - Execute test suite and verify coverage (high priority, depends on tests)
5. **security_agent** - Security scan for vulnerabilities (high priority, depends on code)
6. **review_agent** - Review code quality, security, and architecture (high priority, depends on security scan)
7. **git_agent** - Commit changes with conventional commit message (high priority, depends on review)
8. **git_agent** - Create pull request with security checklist (high priority, depends on commit) ⭐ IMPORTANT
9. **docs_agent** - Update documentation (medium priority, depends on commit)

## AUTO-FIX CAPABILITIES - Self-Healing Workflow:

**IMPORTANT:** The orchestrator has a built-in self-healing mechanism for test failures!

If tests fail (step 4), the system will AUTOMATICALLY:
1. Detect test failures
2. Generate fix tasks using debug_agent
3. Re-run tests to verify fixes
4. Repeat up to 3 times until tests pass

This means:
- Tests that fail will trigger automatic fix attempts
- No need for manual intervention for simple test failures
- PRs are only created if tests pass (after auto-fix retries)
- If tests still fail after 3 attempts, workflow stops with detailed error

**You do NOT need to add explicit "fix failing tests" tasks** - the orchestrator handles this automatically!

## IMPORTANT - File Path Context for coding_agent:

When creating tasks for the coding_agent, ALWAYS include a "file_path" in the context if the task involves creating or modifying a file. Be specific about where files should be created.

Examples:
- For models: {"language": "python", "file_path": "models/user.py"}
- For routes: {"language": "python", "file_path": "routes/auth.py"}
- For components: {"language": "typescript", "file_path": "src/components/Header.tsx"}
- For services: {"language": "python", "file_path": "services/auth_service.py"}
- For tests: {"language": "python", "file_path": "tests/test_auth.py"}

## Output Format:

Return a JSON array of sub-tasks with this structure:
[
  {
    "agent": "agent_name",
    "task": "Specific task description",
    "priority": "high|medium|low",
    "dependencies": ["task_index_1", "task_index_2"],
    "context": {}
  }
]

## Examples:

User: "Implement user authentication with JWT"
Response:
[
  {"agent": "git_agent", "task": "Create feature branch feature/jwt-authentication", "priority": "high", "dependencies": [], "context": {}},
  {"agent": "coding_agent", "task": "Create user model with username, email, password_hash fields. Use environment variables for secret config in models/user.py", "priority": "high", "dependencies": [0], "context": {"language": "python", "file_path": "models/user.py", "security_requirements": ["no_hardcoded_secrets", "input_validation"]}},
  {"agent": "coding_agent", "task": "Implement JWT token generation and validation with proper error handling in utils/jwt.py", "priority": "high", "dependencies": [0], "context": {"language": "python", "file_path": "utils/jwt.py", "security_requirements": ["error_handling", "secure_defaults"]}},
  {"agent": "coding_agent", "task": "Create authentication endpoints with input validation and XSS prevention in routes/auth.py", "priority": "high", "dependencies": [1, 2], "context": {"language": "python", "framework": "fastapi", "file_path": "routes/auth.py", "security_requirements": ["input_validation", "xss_prevention"]}},
  {"agent": "testing_agent", "task": "Write comprehensive unit tests for JWT utilities covering edge cases in tests/test_jwt.py", "priority": "high", "dependencies": [2], "context": {"language": "python", "file_path": "tests/test_jwt.py", "coverage_target": "90%"}},
  {"agent": "testing_agent", "task": "Execute test suite and verify minimum 80% coverage", "priority": "high", "dependencies": [3, 4], "context": {}},
  {"agent": "security_agent", "task": "Security scan for hardcoded secrets, XSS vulnerabilities, and SQL injection", "priority": "high", "dependencies": [3], "context": {}},
  {"agent": "review_agent", "task": "Review code quality, security, error handling, and architecture patterns", "priority": "high", "dependencies": [5, 6], "context": {"checklist": ["error_handling", "architecture", "security"]}},
  {"agent": "git_agent", "task": "Commit changes with conventional commit message including scope and description", "priority": "high", "dependencies": [7], "context": {}},
  {"agent": "git_agent", "task": "Create pull request with security checklist in description", "priority": "high", "dependencies": [8], "context": {"security_checklist": ["no_secrets", "xss_checked", "tests_pass"]}},
  {"agent": "docs_agent", "task": "Generate API documentation for auth endpoints using OpenAPI/Swagger", "priority": "medium", "dependencies": [8], "context": {}}
]

Remember: Always return valid JSON. Never include explanatory text outside the JSON.
"""

    async def decompose(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Decompose a task into sub-tasks using Claude.

        Args:
            task: Task description
            context: Additional context about the task

        Returns:
            List of sub-tasks
        """
        self.logger.info("Decomposing task", task=task)

        try:
            # Build the user message
            user_message = f"Decompose this task into sub-tasks: {task}"

            if context:
                user_message += f"\n\nContext: {json.dumps(context, indent=2)}"

            # Call Claude
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                temperature=0.3,
                system=self.system_prompt,
                messages=[
                    {"role": "user", "content": user_message}
                ]
            )

            # Extract and parse the response
            content = response.content[0].text

            # Try to extract JSON from the response
            # Claude might wrap it in markdown code blocks
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            subtasks = json.loads(content)

            self.logger.info(
                "Task decomposed",
                subtask_count=len(subtasks),
                subtasks=json.dumps(subtasks, indent=2)
            )

            return subtasks

        except json.JSONDecodeError as e:
            self.logger.error("Failed to parse Claude response", error=str(e))
            # Fallback to simple decomposition
            return self._fallback_decomposition(task)

        except Exception as e:
            self.logger.error("Decomposition failed", error=str(e))
            return self._fallback_decomposition(task)

    def _fallback_decomposition(self, task: str) -> List[Dict[str, Any]]:
        """Fallback decomposition when Claude fails."""
        return [
            {
                "agent": "coding_agent",
                "task": task,
                "priority": "high",
                "dependencies": [],
                "context": {}
            }
        ]


class AgentRouter:
    """Routes tasks to appropriate agents with intelligent retry logic."""

    def __init__(self, registry: AgentRegistry):
        """Initialize router."""
        self.registry = registry
        self.logger = get_logger("agent_router")

    async def route(
        self,
        agent_name: str,
        task: str,
        **kwargs: Any,
    ) -> AgentResult:
        """
        Route a task to an agent.

        Args:
            agent_name: Name of target agent
            task: Task description
            **kwargs: Additional parameters

        Returns:
            Agent result
        """
        if not self.registry.is_registered(agent_name):
            self.logger.warning("Agent not registered", agent=agent_name)
            return AgentResult(
                status="error",
                errors=[f"Agent '{agent_name}' not registered"],
            )

        self.logger.info("Routing to agent", agent=agent_name, task=task)

        return await self.registry.call_agent(agent_name, task, **kwargs)


class ResultSynthesizer:
    """
    Synthesizes results from multiple agents.

    Combines outputs, handles conflicts, and generates final response.
    """

    def __init__(self, client: AsyncAnthropic, model: str):
        """Initialize result synthesizer."""
        self.client = client
        self.model = model
        self.logger = get_logger("result_synthesizer")

        self.system_prompt = """You are an expert at synthesizing results from multiple AI agents.

Your role is to:
1. Combine outputs from different agents into a coherent response
2. Identify and resolve any conflicts between agent outputs
3. Extract key insights and next steps
4. Provide a clear summary for the user

## Output Format:

Provide a clear, well-structured response with:
- Summary of what was accomplished
- Key results from each agent
- Any issues encountered
- Next steps for the user

Be concise but thorough. Focus on actionable information.
"""

    async def combine(
        self,
        results: List[AgentResult],
        original_task: str = "",
        executed_subtasks: dict = None,
    ) -> AgentResult:
        """
        Combine multiple agent results.

        Args:
            results: List of agent results
            original_task: The original task for context
            executed_subtasks: Dictionary mapping task index to subtask info

        Returns:
            Synthesized result
        """
        # Store executed subtasks for use in critical failure checking
        self._executed_subtasks = executed_subtasks or {}

        # Check for CRITICAL failures that should stop the workflow
        # These tasks failing means we cannot proceed safely
        critical_agents = ["testing_agent", "security_agent"]
        critical_failures = []

        for i, r in enumerate(results):
            # Check if this was a critical task that failed
            task_agent = self._executed_subtasks.get(i, {}).get("agent", "")
            if r.is_error() or (not r.is_success() and not r.is_partial()):
                # This task failed - check if it's critical
                for critical in critical_agents:
                    if critical in task_agent or "test" in task_agent.lower() or "security" in task_agent.lower():
                        critical_failures.append((i, task_agent, r.errors or ["Task failed"]))

        # If critical tasks failed, return error (fail fast)
        if critical_failures:
            self.logger.logger.error(
                "Critical task(s) failed - cannot proceed",
                failures=[f"{agent}: {errors}" for i, agent, errors in critical_failures]
            )
            return self._synthesize_failure_with_critical(results, critical_failures)

        # Check if all succeeded
        if all(r.is_success() for r in results):
            return await self._synthesize_success(results, original_task)

        # Check if any succeeded (but no critical failures)
        successful = [r for r in results if r.is_success()]
        if successful:
            return await self._synthesize_partial(successful, results, original_task)

        # All failed
        return self._synthesize_failure(results)

    async def _synthesize_success(
        self,
        results: List[AgentResult],
        original_task: str,
    ) -> AgentResult:
        """Synthesize successful results."""
        all_next_steps = []
        all_outputs = []

        for r in results:
            if r.output:
                all_outputs.append(r.output)
            all_next_steps.extend(r.next_steps)

        combined_output = "\n\n".join(all_outputs)

        # Use Claude to create a nice summary
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                temperature=0.3,
                system=self.system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": f"Original task: {original_task}\n\nResults:\n{combined_output}\n\nPlease synthesize these results into a clear summary."
                    }
                ]
            )

            summary = response.content[0].text

            return AgentResult(
                status="success",
                output=summary,
                next_steps=list(set(all_next_steps)),  # Deduplicate
                metadata={
                    "agent_count": len(results),
                    "total_duration_ms": sum(r.duration_ms for r in results),
                },
            )

        except Exception as e:
            self.logger.warning("Failed to synthesize with Claude", error=str(e))
            # Fallback to simple combination
            return AgentResult(
                status="success",
                output=combined_output,
                next_steps=all_next_steps,
                metadata={
                    "agent_count": len(results),
                    "total_duration_ms": sum(r.duration_ms for r in results),
                },
            )

    async def _synthesize_partial(
        self,
        successful: List[AgentResult],
        all_results: List[AgentResult],
        original_task: str,
    ) -> AgentResult:
        """Synthesize partial success results."""
        combined_output = "\n\n".join([r.output or "" for r in successful if r.output])

        all_errors = []
        for r in all_results:
            all_errors.extend(r.errors)

        all_next_steps = []
        for r in all_results:
            all_next_steps.extend(r.next_steps)

        return AgentResult(
            status="partial",
            output=f"Partially completed:\n\n{combined_output}",
            errors=all_errors,
            next_steps=list(set(all_next_steps)),
            metadata={
                "successful_count": len(successful),
                "total_count": len(all_results),
            },
        )

    def _synthesize_failure(self, results: List[AgentResult]) -> AgentResult:
        """Synthesize failed results."""
        all_errors = []
        for r in results:
            all_errors.extend(r.errors)

        return AgentResult(
            status="error",
            errors=all_errors,
        )

    def _synthesize_failure_with_critical(
        self,
        results: List[AgentResult],
        critical_failures: list
    ) -> AgentResult:
        """
        Synthesize results when critical tasks failed.

        Args:
            results: All agent results
            critical_failures: List of (index, agent, errors) tuples

        Returns:
            Error result with detailed information about critical failures
        """
        all_errors = []

        # Add all errors from all results
        for r in results:
            all_errors.extend(r.errors)

        # Add specific critical failure messages
        critical_error_msgs = []
        for idx, agent, errors in critical_failures:
            error_str = f"❌ CRITICAL: {agent} failed"
            critical_error_msgs.append(error_str)
            for e in errors:
                critical_error_msgs.append(f"   - {e}")

        # Build detailed error message
        error_message = (
            "Critical task(s) failed - workflow stopped:\n\n" +
            "\n".join(critical_error_msgs) +
            "\n\nThese failures must be fixed before proceeding."
        )

        return AgentResult(
            status="error",
            errors=[error_message] + all_errors,
            metadata={
                "critical_failures": [(agent, errors) for idx, agent, errors in critical_failures],
                "failed_at": [agent for idx, agent, errors in critical_failures],
            },
            next_steps=[
                "Fix failing tests",
                "Ensure all tests pass before creating PR",
                "Re-run the workflow after fixing",
            ],
        )


class OrchestratorAgent(BaseAgent):
    """
    Main orchestrator agent powered by Claude.

    Coordinates all other agents to complete complex tasks using:
    - Claude for intelligent reasoning and planning
    - Worker agents for specialized tasks
    - Memory systems for context and knowledge
    """

    def __init__(self, config: AgentConfig):
        """Initialize orchestrator."""
        super().__init__(config)

        settings = get_settings()

        # Initialize Claude client
        api_key = settings.anthropic_api_key
        if not api_key:
            self.logger.logger.warning("No Anthropic API key found - using placeholder")
            self.client = None
        else:
            self.client = AsyncAnthropic(api_key=api_key)

        # Initialize components
        if self.client:
            self.decomposer = TaskDecomposer(self.client, config.model)
            self.synthesizer = ResultSynthesizer(self.client, config.model)
        else:
            self.decomposer = None
            self.synthesizer = None

        # Track executed subtasks for fail-fast logic
        self._executed_subtasks: dict[int, dict] = {}

        # Self-healing retry configuration
        self.max_retries = 3  # Maximum attempts to fix failing tests
        self._retry_count = 0  # Track current retry attempt

        self.registry = get_agent_registry()
        self.router = AgentRouter(self.registry)

        self._worker_agents: List[str] = [
            "coding_agent",
            "testing_agent",
            "review_agent",
            "debug_agent",
            "docs_agent",
            "git_agent",
            "deploy_agent",
            "security_agent",
        ]

    def _generate_fix_tasks(
        self,
        test_failure_output: str,
        working_directory: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate fix tasks when tests fail.

        Args:
            test_failure_output: Output from failed test run
            working_directory: Optional working directory context

        Returns:
            List of fix subtasks to attempt to resolve test failures
        """
        self.logger.logger.info(
            "Generating auto-fix tasks for test failures",
            retry_count=self._retry_count,
        )

        fix_tasks = [
            {
                "agent": "debug_agent",
                "task": f"Fix failing tests. Test output:\n\n{test_failure_output}\n\nAnalyze the failures and fix the code or tests to make them pass.",
                "priority": "high",
                "dependencies": [],
                "context": {
                    "working_directory": working_directory,
                    "is_retry_task": True,
                    "retry_attempt": self._retry_count + 1,
                }
            },
            {
                "agent": "testing_agent",
                "task": "Re-run test suite to verify fixes",
                "priority": "high",
                "dependencies": [0],  # Run after debug_agent
                "context": {
                    "working_directory": working_directory,
                    "is_verification": True,
                }
            }
        ]

        return fix_tasks

    async def execute(self, task: str, **kwargs: Any) -> AgentResult:
        """
        Execute a task by coordinating worker agents using Claude.

        Args:
            task: Task description
            **kwargs: Additional parameters

        Returns:
            Agent result
        """
        start_time = time.time()

        # Reset retry count for new task
        self._retry_count = 0

        self.logger.logger.info("Executing task", task=task)

        # Extract working directory from task or context (for git operations)
        working_directory = None

        # First check context parameter
        if kwargs.get("context") and isinstance(kwargs["context"], dict):
            working_directory = kwargs["context"].get("working_directory")

        # If not in context, try to extract from task text
        if not working_directory:
            # Support multiple formats:
            # "Working Directory: /path"
            # "## Working Directory\n/path"
            patterns = [
                r'(?:Current )?Working Directory:\s*(.+?)(?:\n|$)',  # "Working Directory: /path"
                r'##\s*Working Directory\s*\n\s*(.+?)(?:\n|$)',      # "## Working Directory\n/path"
            ]
            for pattern in patterns:
                wd_match = re.search(pattern, task, re.IGNORECASE)
                if wd_match:
                    working_directory = wd_match.group(1).strip()
                    # Clean up markdown formatting
                    working_directory = re.sub(r'^[`\'"]*|[`\'"]*$', '', working_directory)
                    break

        if working_directory:
            self.logger.logger.info("Using working directory", path=working_directory)

        # Step 1: Decompose task using Claude
        if self.decomposer:
            subtasks = await self.decomposer.decompose(task, kwargs.get("context"))
        else:
            # Fallback without Claude
            subtasks = [{
                "agent": "coding_agent",
                "task": task,
                "priority": "high",
                "dependencies": [],
                "context": {}
            }]

        if not subtasks:
            return AgentResult(
                status="error",
                errors=["Could not decompose task"],
            )

        self.logger.logger.info(
            "Decomposed into sub-tasks",
            count=len(subtasks),
        )

        # Step 2: Execute sub-tasks with concurrent execution for independent tasks
        results = []
        completed = set()
        task_map = {i: subtask for i, subtask in enumerate(subtasks)}

        # Execute tasks in waves - each wave contains tasks whose dependencies are satisfied
        while len(completed) < len(subtasks):
            # Find tasks that are ready to execute (dependencies met and not completed)
            ready_tasks = []
            for i, subtask in enumerate(subtasks):
                if i in completed:
                    continue

                dependencies = subtask.get("dependencies", [])
                if all(dep in completed for dep in dependencies):
                    ready_tasks.append(i)

            if not ready_tasks:
                # No tasks ready but not all completed - circular dependency or issue
                self.logger.logger.warning(
                    "No ready tasks found - possible circular dependency",
                    completed=len(completed),
                    total=len(subtasks),
                )
                break

            self.logger.logger.info(
                "Executing wave of tasks",
                wave_size=len(ready_tasks),
                completed=len(completed),
            )

            # Execute all ready tasks concurrently
            async def execute_task(task_index: int) -> tuple[int, AgentResult]:
                subtask = task_map[task_index]
                agent_name = subtask["agent"]
                subtask_desc = subtask["task"]
                subtask_context = subtask.get("context", {})

                # Track this subtask for fail-fast logic
                self._executed_subtasks[task_index] = subtask

                # Add working directory to context if available (for git operations)
                if working_directory:
                    subtask_context["working_directory"] = working_directory

                # === CRITICAL: Pass original task for git_agent PR title generation ===
                # Create a task_context object with original_task so PR titles reflect the actual feature
                # Merge: subtask context takes precedence, then global kwargs
                merged_context = {**kwargs, **subtask_context}

                # For git_agent operations, ensure it has access to the original overall task
                # This is needed for both PR creation (for title) and commit (for message)
                if agent_name == "git_agent" and ("Create pull request" in subtask_desc or "Commit" in subtask_desc):
                    # Create a simple task context object with the original task
                    merged_context["task_context"] = type('TaskContext', (), {'original_task': task})()

                self.logger.logger.info(
                    "Executing sub-task",
                    task_index=task_index,
                    agent=agent_name,
                    task=subtask_desc,
                )

                # Add timeout to prevent infinite hangs (5 minutes max per subtask)
                try:
                    result = await asyncio.wait_for(
                        self.router.route(
                            agent_name,
                            subtask_desc,
                            **merged_context,
                        ),
                        timeout=300.0  # 5 minutes
                    )
                except asyncio.TimeoutError:
                    self.logger.logger.error(
                        "Sub-task timeout",
                        task_index=task_index,
                        agent=agent_name,
                        timeout_seconds=300,
                    )
                    result = AgentResult(
                        status="error",
                        errors=[f"Sub-task timeout after 5 minutes: {subtask_desc[:50]}..."],
                    )

                return task_index, result

            # Run all tasks in this wave concurrently
            wave_results = await asyncio.gather(
                *[execute_task(i) for i in ready_tasks],
                return_exceptions=True,
            )

            # Process results
            for result in wave_results:
                if isinstance(result, Exception):
                    self.logger.logger.error("Task execution raised exception", error=str(result))
                    continue

                task_index, task_result = result
                subtask = task_map[task_index]

                results.append(task_result)
                completed.add(task_index)

                # If high-priority non-testing task failed, stop
                # But testing_agent failures trigger retry logic instead
                if subtask.get("priority") == "high" and task_result.is_error():
                    # Check if this is a testing_agent failure - if so, we'll retry
                    is_testing_task = "testing_agent" in subtask.get("agent", "") or "test" in subtask.get("agent", "").lower()

                    if not is_testing_task:
                        # Non-testing critical task failed - stop immediately
                        return AgentResult(
                            status="error",
                            errors=[
                                f"Critical sub-task failed: {subtask['task']}",
                                *task_result.errors
                            ],
                            metadata={"failed_at": subtask["agent"], "task_index": task_index},
                        )

        # === SELF-HEALING RETRY LOOP FOR TEST FAILURES ===
        # Check if any testing_agent tasks failed and attempt auto-fix
        test_failures = []
        test_failure_output = ""

        for i, r in enumerate(results):
            task_agent = self._executed_subtasks.get(i, {}).get("agent", "")
            if "testing_agent" in task_agent or "test" in task_agent.lower():
                if r.is_error() or (not r.is_success() and not r.is_partial()):
                    test_failures.append((i, task_agent, r.errors))
                    if r.output:
                        test_failure_output += f"\n{r.output}\n"
                    if r.errors:
                        test_failure_output += "\n".join(r.errors)

        # Retry loop: attempt to fix failing tests
        while test_failures and self._retry_count < self.max_retries:
            self._retry_count += 1
            self.logger.logger.warning(
                "Tests failed - attempting auto-fix",
                retry_attempt=self._retry_count,
                max_retries=self.max_retries,
                failures_count=len(test_failures),
            )

            # Generate fix tasks
            fix_tasks = self._generate_fix_tasks(test_failure_output, working_directory)

            # Execute fix tasks
            fix_results = []
            fix_completed = set()
            fix_task_map = {i: task for i, task in enumerate(fix_tasks)}

            while len(fix_completed) < len(fix_tasks):
                # Find ready fix tasks
                ready_fixes = []
                for i, fix_task in enumerate(fix_tasks):
                    if i in fix_completed:
                        continue
                    dependencies = fix_task.get("dependencies", [])
                    if all(dep in fix_completed for dep in dependencies):
                        ready_fixes.append(i)

                if not ready_fixes:
                    break

                # Execute fix tasks
                async def execute_fix_task(fix_index: int) -> tuple[int, AgentResult]:
                    fix_subtask = fix_task_map[fix_index]
                    fix_agent = fix_subtask["agent"]
                    fix_desc = fix_subtask["task"]
                    fix_context = fix_subtask.get("context", {})

                    if working_directory:
                        fix_context["working_directory"] = working_directory

                    self.logger.logger.info(
                        "Executing fix task",
                        retry_attempt=self._retry_count,
                        fix_index=fix_index,
                        agent=fix_agent,
                    )

                    try:
                        fix_result = await asyncio.wait_for(
                            self.router.route(fix_agent, fix_desc, **fix_context),
                            timeout=300.0
                        )
                    except asyncio.TimeoutError:
                        self.logger.logger.error("Fix task timeout", fix_index=fix_index)
                        fix_result = AgentResult(
                            status="error",
                            errors=[f"Fix task timeout after 5 minutes"],
                        )

                    return fix_index, fix_result

                # Run fix tasks concurrently
                fix_wave_results = await asyncio.gather(
                    *[execute_fix_task(i) for i in ready_fixes],
                    return_exceptions=True,
                )

                # Process fix results
                for fix_result in fix_wave_results:
                    if isinstance(fix_result, Exception):
                        continue

                    fix_idx, fix_res = fix_result
                    fix_results.append(fix_res)
                    fix_completed.add(fix_idx)

            # Check if tests now pass after fix attempt
            # Look for the testing_agent verification task result
            tests_passed = False
            for res in fix_results:
                task_agent = fix_task_map.get(len(fix_results) - 1, {}).get("agent", "")
                if "testing_agent" in task_agent or "test" in task_agent.lower():
                    if res.is_success():
                        tests_passed = True
                        self.logger.logger.info(
                            "Tests now pass after auto-fix",
                            retry_attempt=self._retry_count,
                        )
                        # Add fix results to main results
                        results.extend(fix_results)
                        break
                    else:
                        # Tests still failing - update failure info for next retry
                        test_failure_output = ""
                        if res.output:
                            test_failure_output += f"\n{res.output}\n"
                        if res.errors:
                            test_failure_output += "\n".join(res.errors)
                        test_failures = [(0, "testing_agent", res.errors)]
                        break

            if tests_passed:
                # Success! Tests pass after fix
                test_failures = []
                break

        # If we exhausted retries and tests still fail, return error
        if test_failures and self._retry_count >= self.max_retries:
            self.logger.logger.error(
                "Tests still failing after max retries",
                retry_attempts=self._retry_count,
                max_retries=self.max_retries,
            )
            return AgentResult(
                status="error",
                errors=[
                    f"Tests failed after {self._retry_count} auto-fix attempts. Manual intervention required.",
                    *(test_failures[0][2] if test_failures else [])
                ],
                metadata={
                    "failed_at": "testing_agent",
                    "retry_attempts": self._retry_count,
                    "max_retries": self.max_retries,
                },
                next_steps=[
                    "Review test failures manually",
                    "Fix code or tests to resolve failures",
                    "Re-run the workflow after manual fixes",
                ],
            )

        # Step 3: Synthesize results
        if self.synthesizer and len(results) > 1:
            final_result = await self.synthesizer.combine(results, original_task=task, executed_subtasks=self._executed_subtasks)
        else:
            # Simple synthesis
            if results and results[0].is_success():
                final_result = results[0]
            else:
                final_result = AgentResult(
                    status="error",
                    errors=["Task execution failed"],
                )

        duration_ms = int((time.time() - start_time) * 1000)
        final_result.duration_ms = duration_ms

        # Include retry information in metadata if auto-fix was attempted
        if self._retry_count > 0:
            if not final_result.metadata:
                final_result.metadata = {}
            final_result.metadata["auto_fix_attempts"] = self._retry_count
            self.logger.logger.info(
                "Task completed with auto-fix",
                retry_attempts=self._retry_count,
                duration_ms=duration_ms,
            )

        # Include working directory in metadata for downstream processes
        if working_directory:
            if not final_result.metadata:
                final_result.metadata = {}
            final_result.metadata["working_directory"] = working_directory

        # Preserve important metadata from subtask results (PR info, etc.)
        for result in results:
            if result.metadata:
                if not final_result.metadata:
                    final_result.metadata = {}
                # Preserve PR-related metadata
                if "pr_url" in result.metadata:
                    final_result.metadata["pr_url"] = result.metadata["pr_url"]
                if "pr_number" in result.metadata:
                    final_result.metadata["pr_number"] = result.metadata["pr_number"]
                if "url" in result.metadata and "pr_url" not in final_result.metadata:
                    final_result.metadata["pr_url"] = result.metadata["url"]

        # === CLEANUP: Return to main branch and clean working directory ===
        # This prevents the daemon from failing when trying to start a new task
        if working_directory and final_result.status == "success":
            try:
                import subprocess
                self.logger.logger.info("Cleanup: Returning to main branch", working_dir=working_directory)

                # Checkout main
                subprocess.run(
                    ["git", "checkout", "main"],
                    cwd=working_directory,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=30
                )

                # Clean uncommitted changes (restore modified files)
                subprocess.run(
                    ["git", "restore", "."],
                    cwd=working_directory,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=30
                )

                self.logger.logger.info("Cleanup completed", returned_to_main=True, clean_working_tree=True)
            except Exception as e:
                self.logger.logger.warning("Cleanup failed (non-critical)", error=str(e))
                # Don't fail the task if cleanup fails

        # === TRELLO INTEGRATION: Create/update card ===
        # Only create cards if we're not already working with an existing Trello task
        # (i.e., trello_card_id is not already in context)
        if final_result.status == "success":
            try:
                from worker.trello.client import get_trello_client

                trello_client = get_trello_client()

                # Check if we already have a Trello card (from daemon workflow)
                existing_card_id = None
                for subtask_result in self._executed_subtasks:
                    if hasattr(subtask_result, 'metadata') and subtask_result.metadata:
                        if 'trello_card_id' in subtask_result.metadata:
                            existing_card_id = subtask_result.metadata['trello_card_id']
                            break

                if not existing_card_id and trello_client.is_configured():
                    # No existing card - create a new one
                    self.logger.logger.info("Creating Trello card for completed task")

                    # Extract project name from working directory
                    project_name = working_directory.split('/')[-1] if working_directory else "unknown"

                    # Create card title
                    card_title = f"[{project_name}] {task[:80]}"

                    # Create card description with PR link if available
                    card_desc = f"Task: {task}\n\n"
                    if "pr_url" in final_result.metadata:
                        card_desc += f"**PR:** {final_result.metadata['pr_url']}\n\n"
                    if "pr_number" in final_result.metadata:
                        card_desc += f"**PR Number:** {final_result.metadata['pr_number']}\n\n"
                    card_desc += f"**Status:** {final_result.status}\n"
                    card_desc += f"**Duration:** {duration_ms / 1000:.1f}s\n"

                    # Create card in TODO list
                    card_id = await trello_client.create_card(
                        name=card_title,
                        desc=card_desc,
                    )

                    if card_id:
                        self.logger.logger.info("Trello card created successfully", card_id=card_id[:8])

                        # Move card to Done since task completed successfully
                        moved = await trello_client.move_to_done(card_id)
                        if moved:
                            self.logger.logger.info("Trello card moved to Done", card_id=card_id[:8])
                        else:
                            self.logger.logger.warning("Failed to move card to Done", card_id=card_id[:8])

                    else:
                        self.logger.logger.warning("Failed to create Trello card")
                elif existing_card_id:
                    # We already have a card from the daemon workflow
                    # The enhanced_orchestrator will handle moving it
                    self.logger.logger.info("Task has existing Trello card", card_id=existing_card_id[:8])

            except ImportError:
                # Trello client not available (running outside daemon environment)
                self.logger.logger.debug("Trello client not available, skipping card creation")
            except Exception as e:
                # Don't fail the task if Trello integration fails
                self.logger.logger.warning("Trello integration failed (non-critical)", error=str(e))

        self.logger.logger.info(
            "Task completed",
            status=final_result.status,
            duration_ms=duration_ms,
        )

        return final_result

    async def validate(self, result: AgentResult) -> bool:
        """
        Validate orchestrator result.

        Args:
            result: Result to validate

        Returns:
            True if valid
        """
        return result.status in ["success", "partial", "error"]

    async def get_status(self) -> Dict[str, Any]:
        """
        Get orchestrator and system status.

        Returns:
            Status information
        """
        registered_agents = self.registry.list_agents()

        agent_stats = {}
        for agent_name in registered_agents:
            agent = self.registry.get(agent_name)
            if agent and hasattr(agent, "get_stats"):
                agent_stats[agent_name] = agent.get_stats()

        return {
            "orchestrator": self.get_stats(),
            "registered_agents": registered_agents,
            "worker_agents": self._worker_agents,
            "agent_stats": agent_stats,
            "claude_enabled": self.client is not None,
        }

    async def chat(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Chat directly with Claude for planning and reasoning.

        Args:
            message: User message
            context: Additional context

        Returns:
            Claude's response
        """
        if not self.client:
            return "Claude client not configured. Please set ANTHROPIC_API_KEY."

        system_prompt = """You are an expert software development coordinator.

You help users plan and execute software development tasks by:
1. Understanding their requirements
2. Suggesting approaches
3. Breaking down work into manageable steps
4. Identifying potential issues

Be practical, specific, and actionable. Focus on helping the user accomplish their goals."""

        try:
            response = await self.client.messages.create(
                model=self.config.model,
                max_tokens=4096,
                temperature=0.7,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": message}
                ]
            )

            return response.content[0].text

        except Exception as e:
            self.logger.logger.error("Chat failed", error=str(e))
            return f"Error: {str(e)}"


async def create_orchestrator() -> OrchestratorAgent:
    """Create and initialize the orchestrator agent."""
    config = AgentConfig(
        name="orchestrator",
        description="Main coordinator powered by Claude",
        model="claude-sonnet-4-5-20250929",
        temperature=0.7,
        max_tokens=4096,
    )

    orchestrator = OrchestratorAgent(config)

    # Initialize memory manager
    await get_memory_manager()

    return orchestrator
