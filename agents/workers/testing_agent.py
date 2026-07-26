"""
Testing Agent - LLM-Powered

Specialized agent for test generation and execution using Claude/GPT.
"""

import os
import time
from typing import Any, Dict

from agents.base.base_agent import AgentConfig, AgentResult, BaseAgent
from agents.tools.tool_registry import get_tool_registry
from models.llm.llm_wrapper import LLMResponse, get_llm_wrapper
from utils.logger import AgentLogger


class TestingAgent(BaseAgent):
    """
    Agent specialized in testing using LLMs.

    Capabilities:
    - Generate unit tests with Claude/GPT
    - Generate integration tests
    - Run test suites
    - Analyze coverage
    - Debug test failures
    """

    def __init__(self, config: AgentConfig):
        """Initialize testing agent."""
        super().__init__(config)
        self.llm = get_llm_wrapper()
        self.tools = get_tool_registry()
        self.logger.logger.info("Testing agent initialized with LLM")

    async def execute(self, task: str, **kwargs: Any) -> AgentResult:
        """
        Execute a testing task using LLM.

        Args:
            task: Task description
            **kwargs: Additional parameters

        Returns:
            Agent result
        """
        start_time = time.time()

        self.logger.logger.info("Executing testing task", task=task)

        # Extract parameters
        code = kwargs.get("code", "")
        file_path = kwargs.get("file_path", "test_generated.py")
        language = kwargs.get("language", "python")
        test_type = kwargs.get("test_type", "unit")
        framework = kwargs.get("framework", None)  # Don't default yet!
        working_directory = kwargs.get("working_directory", ".")

        # === CRITICAL FIX: Auto-detect test framework ===
        # Prevents infinite loop of wrong tests (e.g., pytest for React)
        framework = self._detect_framework(framework, file_path, language, working_directory)
        self.logger.logger.info("Detected test framework", framework=framework, file_path=file_path)

        # FIX: Convert relative file paths to absolute paths
        if file_path and not os.path.isabs(file_path):
            file_path = os.path.join(working_directory, file_path)
            self.logger.logger.info("Converted relative path to absolute", path=file_path)

        # Determine if we're generating or running tests
        task_lower = task.lower()
        if "run" in task_lower or "execute" in task_lower or "verify" in task_lower:
            return await self._run_tests(task, **kwargs)

        # Generate tests
        prompt = self._build_prompt(
            task=task,
            code=code,
            language=language,
            test_type=test_type,
            framework=framework,
        )

        system_prompt = self._get_system_prompt(framework)

        try:
            llm_response: LLMResponse = await self.llm.generate(
                prompt=prompt,
                model=self.config.model,
                system_prompt=system_prompt,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )

            tests = llm_response.content

            # Extract tests from response
            tests = self._extract_code(tests)

            # Write to file if specified
            if file_path:
                write_result = await self.tools.execute_tool(
                    "file_ops",
                    "write_file",
                    path=file_path,
                    content=tests,
                )

                if not write_result["success"]:
                    return AgentResult(
                        status="error",
                        errors=[f"Failed to write tests: {write_result.get('error')}"],
                    )

            duration_ms = int((time.time() - start_time) * 1000)

            self.logger.log_token_usage(
                model=self.config.model,
                prompt_tokens=llm_response.prompt_tokens,
                completion_tokens=llm_response.completion_tokens,
                total_tokens=llm_response.total_tokens,
            )

            return AgentResult(
                status="success",
                output=tests,
                metadata={
                    "file_path": file_path,
                    "test_type": test_type,
                    "framework": framework,
                    "tokens_used": llm_response.total_tokens,
                },
                next_steps=[
                    "Run tests to verify they pass",
                    "Check test coverage",
                    "Review test quality",
                ],
                duration_ms=duration_ms,
            )

        except Exception as e:
            self.logger.logger.error("Test generation failed", error=str(e))
            return AgentResult(
                status="error",
                errors=[str(e)],
            )

    async def _run_tests(self, task: str, **kwargs) -> AgentResult:
        """Run existing tests or verify application."""
        import httpx
        import subprocess
        import os
        import time

        working_directory = kwargs.get("working_directory", ".")
        task_lower = task.lower()

        # Check if this is a Flask/HTTP app verification task
        # More specific detection - only trigger if explicit Flask/HTTP keywords are present
        http_keywords = ["flask", "http route", "api endpoint", "web app", "localhost:5000", "0.0.0.0:5000"]
        is_http_task = any(keyword in task_lower for keyword in http_keywords)
        # Also check if task contains a route pattern like /about, /api/users, etc.
        has_route_pattern = bool(__import__("re").search(r'/[a-zA-Z0-9_]+', task))

        if is_http_task or (has_route_pattern and any(word in task_lower for word in ["app", "flask", "server"])):
            self.logger.logger.info("Detected HTTP/Flask verification task", task=task)

            # Try to find and extract the route to test
            route = "/about"  # default
            if "/about" in task:
                route = "/about"
            elif "/" in task:
                # Try to extract route like "/api/users"
                import re
                route_match = re.search(r'/[a-zA-Z0-9_/]+', task)
                if route_match:
                    route = route_match.group(0)

            self.logger.logger.info("Testing HTTP route", route=route)

            # Start Flask app in background
            app_file = os.path.join(working_directory, "app.py")
            if os.path.exists(app_file):
                try:
                    # Start Flask app in background
                    # Use sys.executable to get the current python interpreter
                    import sys
                    python_exe = sys.executable if hasattr(sys, 'executable') else 'python3'
                    process = subprocess.Popen(
                        [python_exe, "app.py"],
                        cwd=working_directory,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )

                    # Wait for app to start
                    time.sleep(3)

                    # Test the route
                    try:
                        response = httpx.get(f"http://localhost:5000{route}", timeout=5.0)

                        # Clean up: kill the Flask process
                        process.terminate()
                        process.wait(timeout=2)

                        if response.status_code == 200:
                            content_preview = response.text[:200] if response.text else "empty"
                            self.logger.logger.info(
                                "HTTP route verification successful",
                                route=route,
                                status_code=response.status_code,
                                content_length=len(response.text),
                            )
                            return AgentResult(
                                status="success",
                                output=f"Route {route} returned HTTP {response.status_code}\nContent preview: {content_preview}",
                                metadata={
                                    "route": route,
                                    "status_code": response.status_code,
                                    "content_length": len(response.text),
                                },
                            )
                        else:
                            return AgentResult(
                                status="error",
                                errors=[f"Route {route} returned HTTP {response.status_code}, expected 200"],
                            )
                    except httpx.RequestError as e:
                        # Clean up: kill the Flask process
                        process.terminate()
                        process.wait(timeout=2)
                        return AgentResult(
                            status="error",
                            errors=[f"Failed to connect to Flask app: {str(e)}"],
                        )
                    except Exception as e:
                        # Clean up: kill the Flask process
                        process.terminate()
                        process.wait(timeout=2)
                        return AgentResult(
                            status="error",
                            errors=[f"Error testing route: {str(e)}"],
                        )

                except Exception as e:
                    self.logger.logger.error("Failed to start Flask app", error=str(e))
                    return AgentResult(
                        status="error",
                        errors=[f"Failed to start Flask app: {str(e)}"],
                    )
            else:
                return AgentResult(
                    status="error",
                    errors=[f"Flask app file not found: {app_file}"],
                )

        # Check if this is a simple module verification task
        # (e.g., "verify the function executes correctly" - just run the module)
        file_path = kwargs.get("file_path", "")
        is_verify_task = any(word in task_lower for word in ["verify", "executes correctly", "works correctly", "test the"])
        is_simple_module_test = is_verify_task and file_path and not any(word in task_lower for word in ["pytest", "unit test", "integration test", "test suite"])

        if is_simple_module_test:
            self.logger.logger.info("Detected simple module verification task", task=task, file_path=file_path)
            import sys
            python_exe = sys.executable if hasattr(sys, 'executable') else 'python3'

            # Run the module directly
            result = await self.tools.execute_tool(
                "command_runner",
                "execute",
                command=python_exe,
                args=[file_path],
                cwd=working_directory,
                timeout=30,
            )

            if result["success"]:
                tool_result = result["result"]
                stdout = tool_result.get("stdout", "")
                stderr = tool_result.get("stderr", "")
                exit_code = tool_result.get("exit_code", 0)

                if exit_code == 0:
                    self.logger.logger.info("Module verification successful", file_path=file_path)
                    return AgentResult(
                        status="success",
                        output=f"Module executed successfully.\n\nOutput:\n{stdout}",
                        metadata={"exit_code": exit_code, "file_path": file_path},
                    )
                else:
                    return AgentResult(
                        status="error",
                        errors=[f"Module execution failed with exit code {exit_code}", stderr or stdout],
                    )
            else:
                return AgentResult(
                    status="error",
                    errors=[f"Failed to run module: {result.get('error')}"],
                )

        # Default: Run test suite
        test_path = kwargs.get("test_path", ".")
        framework = kwargs.get("framework", "pytest")

        self.logger.logger.info("Running tests", path=test_path, framework=framework)

        # Use command runner to execute tests (allow thorough testing, no artificial timeout)
        result = await self.tools.execute_tool(
            "command_runner",
            "run_tests",
            test_path=test_path,
            framework=framework,
            verbose=True,
            cwd=working_directory,
        )

        if result["success"]:
            tool_result = result["result"]
            stdout = tool_result.get("stdout", "")
            # Ensure output is non-empty for validation
            output = stdout if stdout else f"Tests executed successfully with {framework}"
            return AgentResult(
                status="success",
                output=output,
                metadata={
                    "exit_code": tool_result.get("exit_code"),
                    "framework": framework,
                },
            )
        else:
            # Check for no tests collected (pytest exit code 5)
            tool_result = result.get("result", {})
            exit_code = tool_result.get("exit_code", -1)
            stderr = tool_result.get("stderr", "")

            if exit_code == 5 or "no tests collected" in stderr.lower():
                # No tests found - this is an ERROR for best practices
                self.logger.logger.warning("No tests collected", test_path=test_path)
                return AgentResult(
                    status="error",
                    errors=[f"No tests found in {test_path}. Tests must exist and pass before creating PR."],
                    metadata={
                        "exit_code": exit_code,
                        "framework": framework,
                        "no_tests_found": True,
                    },
                    next_steps=[
                        "Create tests for this module",
                        "Ensure tests can be imported and run",
                        "Verify tests pass before creating PR",
                    ],
                )
            else:
                # Actual test failure or execution error
                return AgentResult(
                    status="error",
                    errors=[result.get("error", "Test execution failed")],
                )

    def _detect_framework(
        self,
        framework: str | None,
        file_path: str,
        language: str,
        working_directory: str,
    ) -> str:
        """
        Auto-detect the correct test framework.

        Prevents catastrophic bug where pytest is used for React projects.

        Args:
            framework: Explicitly passed framework (if any)
            file_path: Path to test file
            language: Programming language
            working_directory: Project root directory

        Returns:
            Detected framework name (pytest, jest, vitest, etc.)
        """
        # If framework explicitly provided, use it
        if framework:
            self.logger.logger.info("Using explicit framework", framework=framework)
            return framework

        # DETECTION RULE 1: File extension mapping
        if file_path:
            file_ext = os.path.splitext(file_path)[1].lower()
            file_name = os.path.basename(file_path).lower()

            # React/TypeScript/JavaScript → Jest or Vitest
            if file_ext in ['.tsx', '.jsx', '.ts', '.js']:
                # Check if test file
                if 'test' in file_name or 'spec' in file_name:
                    # Detect between Jest and Vitest
                    return self._detect_jest_vs_vitest(working_directory)

            # Python → pytest
            if file_ext == '.py':
                return 'pytest'

            # Go → go test
            if file_ext == '.go':
                return 'gotest'

            # Rust → cargo test
            if file_ext == '.rs':
                return 'cargo'

            # Java → JUnit
            if file_ext == '.java':
                return 'junit'

        # DETECTION RULE 2: Language-based mapping
        language_lower = language.lower() if language else ''

        if language_lower in ['javascript', 'typescript', 'js', 'ts']:
            return self._detect_jest_vs_vitest(working_directory)

        if language_lower in ['python', 'py']:
            return 'pytest'

        if language_lower in ['golang', 'go']:
            return 'gotest'

        # DETECTION RULE 3: Project structure
        framework = self._detect_from_project_structure(working_directory)
        if framework:
            return framework

        # DEFAULT: If all else fails, use pytest (but log warning)
        self.logger.logger.warning(
            "Could not detect framework, using default pytest",
            file_path=file_path,
            language=language,
        )
        return 'pytest'

    def _detect_jest_vs_vitest(self, working_directory: str) -> str:
        """
        Detect whether to use Jest or Vitest for JavaScript/TypeScript projects.

        Args:
            working_directory: Project root directory

        Returns:
            'jest' or 'vitest'
        """
        # Check for Vitest config files
        vitest_configs = [
            'vitest.config.ts',
            'vitest.config.js',
            'vitest.config.json',
            'vite.config.ts',  # Vitest can be configured here too
            'vite.config.js',
        ]

        for config_file in vitest_configs:
            config_path = os.path.join(working_directory, config_file)
            if os.path.exists(config_path):
                self.logger.logger.info("Detected Vitest config", config=config_file)
                return 'vitest'

        # Check for package.json
        package_json_path = os.path.join(working_directory, 'package.json')
        if os.path.exists(package_json_path):
            try:
                import json
                with open(package_json_path, 'r') as f:
                    package_json = json.load(f)

                # Check for vitest in dependencies
                deps = package_json.get('dependencies', {})
                dev_deps = package_json.get('devDependencies', {})

                if 'vitest' in dev_deps or 'vitest' in deps:
                    self.logger.logger.info("Found vitest in package.json")
                    return 'vitest'

                if 'jest' in dev_deps or 'jest' in deps:
                    self.logger.logger.info("Found jest in package.json")
                    return 'jest'

                # Check for test scripts
                scripts = package_json.get('scripts', {})
                test_script = scripts.get('test', '')

                if 'vitest' in test_script:
                    self.logger.logger.info("Test script uses vitest")
                    return 'vitest'

                if 'jest' in test_script:
                    self.logger.logger.info("Test script uses jest")
                    return 'jest'

            except Exception as e:
                self.logger.logger.warning("Failed to parse package.json", error=str(e))

        # DEFAULT to Jest for React projects (more common)
        self.logger.logger.info("Defaulting to Jest for JavaScript/TypeScript")
        return 'jest'

    def _detect_from_project_structure(self, working_directory: str) -> str | None:
        """
        Detect test framework from project structure.

        Args:
            working_directory: Project root directory

        Returns:
            Framework name or None if undetectable
        """
        # Check for pytest-specific files
        pytest_indicators = [
            'pytest.ini',
            'pyproject.toml',  # Can contain pytest config
            'setup.cfg',  # Can contain pytest config
            'conftest.py',  # Pytest fixture file
            '.pytest_cache',  # Pytest cache directory
        ]

        for indicator in pytest_indicators:
            if os.path.exists(os.path.join(working_directory, indicator)):
                self.logger.logger.info("Detected pytest project", indicator=indicator)
                return 'pytest'

        # Check for Jest/Vitest config (already covered, but for completeness)
        jest_indicators = [
            'jest.config.js',
            'jest.config.ts',
            'vitest.config.ts',
            'vitest.config.js',
        ]

        for indicator in jest_indicators:
            if os.path.exists(os.path.join(working_directory, indicator)):
                if 'jest' in indicator:
                    return 'jest'
                if 'vitest' in indicator:
                    return 'vitest'

        # Check for Go module
        if os.path.exists(os.path.join(working_directory, 'go.mod')):
            self.logger.logger.info("Detected Go module")
            return 'gotest'

        # Check for Cargo.toml (Rust)
        if os.path.exists(os.path.join(working_directory, 'Cargo.toml')):
            self.logger.logger.info("Detected Rust project")
            return 'cargo'

        # Check for pom.xml (Maven/Java)
        if os.path.exists(os.path.join(working_directory, 'pom.xml')):
            self.logger.logger.info("Detected Maven project")
            return 'junit'

        return None

    def _build_prompt(
        self,
        task: str,
        code: str,
        language: str,
        test_type: str,
        framework: str,
    ) -> str:
        """Build the prompt for test generation."""
        prompt_parts = [f"Task: {task}"]

        if code:
            prompt_parts.append(f"\nCode to test:\n```\n{code}\n```")

        prompt_parts.extend([
            f"Language: {language}",
            f"Test Type: {test_type}",
            f"Framework: {framework}",
        ])

        prompt_parts.append("\nGenerate comprehensive tests.")

        return "\n".join(prompt_parts)

    def _get_system_prompt(self, framework: str = "pytest") -> str:
        """Get system prompt for testing based on framework."""
        framework_lower = framework.lower()

        # Jest/Vitest prompt for JavaScript/TypeScript
        if framework_lower in ['jest', 'vitest']:
            return """You are an expert test engineer specializing in React testing with Jest/Vitest.

Generate comprehensive tests that:
- Test normal behavior (happy path)
- Test edge cases and boundary conditions
- Test error cases and exception handling
- Follow React testing best practices
- Use @testing-library/react for component testing
- Are clear and maintainable
- Use descriptive test names
- Include necessary imports and mocks

IMPORTANT RULES:
- ALWAYS use real Jest/Vitest syntax - NOT Python pytest!
- Import from @testing-library/react for components
- Use render(), screen, fireEvent, or userEvent
- Write actual tests that can run - NO MOCKS of the component itself!
- Test the REAL component behavior

Test structure:
```javascript
import { render, screen } from '@testing-library/react';
import { ComponentName } from './ComponentName';

describe('ComponentName', () => {
  it('should render correctly', () => {
    render(<ComponentName />);
    expect(screen.getByText('expected text')).toBeInTheDocument();
  });

  it('should handle user interactions', () => {
    render(<ComponentName />);
    // Test interaction
  });
});
```

Return only the test code, preferably in a markdown code block with javascript or typescript label."""

        # Pytest prompt for Python
        elif framework_lower == 'pytest':
            return """You are an expert test engineer specializing in Python testing with pytest.

Generate comprehensive tests that:
- Test normal behavior (happy path)
- Test edge cases and boundary conditions
- Test error cases and exception handling
- Follow pytest best practices
- Are clear and maintainable
- Use descriptive test names
- Include necessary imports and fixtures

Structure tests using:
- Arrange-Act-Assert pattern
- Clear test names that describe what is being tested
- Helpful comments for complex test logic
- Proper setup and teardown with fixtures

Return only the test code, preferably in a markdown code block with python label."""

        # Go testing prompt
        elif framework_lower == 'gotest':
            return """You are an expert test engineer specializing in Go testing.

Generate comprehensive tests that:
- Test normal behavior (happy path)
- Test edge cases and boundary conditions
- Test error cases and exception handling
- Follow Go testing best practices
- Use table-driven tests where appropriate
- Are clear and maintainable

Structure tests using:
- Test functions starting with Test
- Clear test names that describe what is being tested
- t.Run() for subtests
- Proper setup and teardown

Return only the test code, preferably in a markdown code block with go label."""

        # JUnit prompt for Java
        elif framework_lower == 'junit':
            return """You are an expert test engineer specializing in Java testing with JUnit.

Generate comprehensive tests that:
- Test normal behavior (happy path)
- Test edge cases and boundary conditions
- Test error cases and exception handling
- Follow JUnit 5 best practices
- Use @Test, @BeforeEach, @AfterEach annotations
- Are clear and maintainable

Return only the test code, preferably in a markdown code block with java label."""

        # Default prompt (fallback)
        return f"""You are an expert test engineer specializing in {framework}.

Generate comprehensive tests that:
- Test normal behavior (happy path)
- Test edge cases and boundary conditions
- Test error cases and exception handling
- Follow {framework} best practices
- Are clear and maintainable
- Use descriptive test names

Return only the test code, preferably in a markdown code block."""

    def _extract_code(self, response: str) -> str:
        """Extract code from LLM response."""
        response = response.strip()

        if response.startswith("```"):
            lines = response.split('\n')
            if len(lines) > 1:
                first_line = lines[0]
                if first_line.startswith("```") and not first_line == "```":
                    response = '\n'.join(lines[1:-1])
                else:
                    response = response[3:]
                    if response.endswith("```"):
                        response = response[:-3]

        return response.strip()

    async def validate(self, result: AgentResult) -> bool:
        """Validate testing result."""
        return result.is_success() and result.output

    async def write_tests(
        self,
        code: str,
        test_type: str = "unit",
    ) -> AgentResult:
        """Write tests for code."""
        task = f"Write {test_type} tests for code"
        return await self.execute(task, code=code, test_type=test_type)

    async def run_tests(
        self,
        test_path: str = ".",
        framework: str = "pytest",
    ) -> AgentResult:
        """Run test suite."""
        task = f"Run {framework} tests"
        return await self.execute(task, test_path=test_path, framework=framework)

    async def analyze_coverage(
        self,
        code_path: str,
    ) -> AgentResult:
        """Analyze test coverage."""
        task = f"Analyze test coverage for {code_path}"

        # Run coverage command
        result = await self.tools.execute_tool(
            "command_runner",
            "execute",
            command="pytest",
            args=[f"--cov={code_path}", "--cov-report=term-missing"],
            timeout=60,
        )

        return AgentResult(
            status="success" if result["success"] else "error",
            output=result.get("result", {}).get("stdout", ""),
            errors=[result.get("error")] if not result["success"] else [],
        )


async def create_testing_agent() -> TestingAgent:
    """Create a testing agent instance."""
    config = AgentConfig(
        name="testing_agent",
        description="Test generation agent powered by LLM",
        model="claude-haiku-4-5",
        temperature=0.2,
        max_tokens=4096,
    )

    return TestingAgent(config)
