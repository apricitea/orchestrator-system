"""
Coding Agent - LLM-Powered

Specialized agent for code generation and modification using Claude/GPT.
"""

import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional

from agents.base.base_agent import AgentConfig, AgentResult, BaseAgent
from agents.tools.tool_registry import get_tool_registry
from models.llm.llm_wrapper import LLMResponse, get_llm_wrapper
from utils.logger import AgentLogger


class CodingAgent(BaseAgent):
    """
    Agent specialized in code generation using LLMs.

    Capabilities:
    - Generate new code with Claude/GPT
    - Refactor existing code
    - Fix bugs
    - Add features
    - Write code in multiple languages
    """

    def __init__(self, config: AgentConfig):
        """Initialize coding agent."""
        super().__init__(config)
        self.llm = get_llm_wrapper()
        self.tools = get_tool_registry()
        self.logger.logger.info("Coding agent initialized with LLM")

    async def execute(self, task: str, **kwargs: Any) -> AgentResult:
        """
        Execute a coding task using LLM.

        Args:
            task: Task description
            **kwargs: Additional parameters (file_path, language, working_directory, etc.)

        Returns:
            Agent result with generated code
        """
        start_time = time.time()

        self.logger.logger.info("Executing coding task", task=task)

        # Extract parameters
        file_path = kwargs.get("file_path")
        language = kwargs.get("language", "python")
        framework = kwargs.get("framework", "")
        existing_code = kwargs.get("code", "")
        requirements = kwargs.get("requirements", [])
        working_directory = kwargs.get("working_directory", ".")

        # FIX: Extract file path from task if not provided, or convert relative paths to absolute
        if not file_path or file_path == "generated.py":
            inferred_path = self._extract_file_path_from_task(task, language, working_directory)
            if inferred_path:
                file_path = inferred_path
                self.logger.logger.info("Inferred file path from task", path=file_path)
        elif file_path and not os.path.isabs(file_path):
            # Convert relative path to absolute path
            file_path = os.path.join(working_directory, file_path)
            self.logger.logger.info("Converted relative path to absolute", path=file_path)

        # Build the prompt
        prompt = self._build_prompt(
            task=task,
            language=language,
            framework=framework,
            existing_code=existing_code,
            requirements=requirements,
        )

        # Get system prompt
        system_prompt = self._get_system_prompt(language)

        # Generate code using LLM
        try:
            llm_response: LLMResponse = await self.llm.generate(
                prompt=prompt,
                model=self.config.model,
                system_prompt=system_prompt,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )

            code = llm_response.content

            # Extract code from response (remove markdown if present)
            code = self._extract_code(code)

            # FIX: Always write to file if we have a valid file path
            if file_path:
                # FIX: Check if file_path is a directory (ends with / or is existing directory)
                is_directory_path = file_path.endswith('/') or (os.path.exists(file_path) and os.path.isdir(file_path))

                if is_directory_path:
                    # This is a directory creation task, not a file write task
                    # Ensure the directory exists
                    if not os.path.exists(file_path):
                        self.logger.logger.info("Creating directory", path=file_path)
                        os.makedirs(file_path, exist_ok=True)
                        self.logger.logger.info("Directory created successfully", path=file_path)
                    else:
                        self.logger.logger.info("Directory already exists", path=file_path)

                    # Don't try to write file content to a directory
                    # The task was just to create the directory structure
                else:
                    # This is a file write task
                    # Ensure parent directory exists
                    parent_dir = os.path.dirname(file_path)
                    if parent_dir and not os.path.exists(parent_dir):
                        self.logger.logger.info("Creating directory", path=parent_dir)
                        os.makedirs(parent_dir, exist_ok=True)

                    # Write the file
                    write_result = await self.tools.execute_tool(
                        "file_ops",
                        "write_file",
                        path=file_path,
                        content=code,
                    )

                    if not write_result["success"]:
                        return AgentResult(
                            status="error",
                            errors=[f"Failed to write file: {write_result.get('error')}"],
                        )

                    # FIX: Verify file was actually created
                    verified = await self._verify_file_exists(file_path)
                    if not verified:
                        return AgentResult(
                            status="error",
                            errors=[f"File verification failed: {file_path} was not created or is empty"],
                        )

            duration_ms = int((time.time() - start_time) * 1000)

            # Log token usage
            self.logger.log_token_usage(
                model=self.config.model,
                prompt_tokens=llm_response.prompt_tokens,
                completion_tokens=llm_response.completion_tokens,
                total_tokens=llm_response.total_tokens,
            )

            return AgentResult(
                status="success",
                output=code,
                metadata={
                    "file_path": file_path,
                    "language": language,
                    "lines_written": code.count('\n') + 1,
                    "tokens_used": llm_response.total_tokens,
                },
                next_steps=[
                    "Write tests for the generated code",
                    "Review code quality",
                    "Run tests to verify functionality",
                ],
                duration_ms=duration_ms,
            )

        except Exception as e:
            self.logger.logger.error("Code generation failed", error=str(e))
            return AgentResult(
                status="error",
                errors=[str(e)],
            )

    def _build_prompt(
        self,
        task: str,
        language: str,
        framework: str,
        existing_code: str,
        requirements: list,
    ) -> str:
        """Build the prompt for code generation."""
        prompt_parts = [f"Task: {task}"]

        if language:
            prompt_parts.append(f"Language: {language}")

        if framework:
            prompt_parts.append(f"Framework: {framework}")

        if existing_code:
            prompt_parts.append(f"\nExisting code:\n```\n{existing_code}\n```")

        if requirements:
            prompt_parts.append(f"\nRequirements:")
            for req in requirements:
                prompt_parts.append(f"  - {req}")

        prompt_parts.append("\nPlease generate the code.")

        return "\n".join(prompt_parts)

    def _get_system_prompt(self, language: str = "python") -> str:
        """Get system prompt for coding."""
        return f"""You are an expert {language} developer.

Generate clean, production-ready code that:
- Is well-structured and follows best practices
- Handles errors appropriately
- Is well-documented with docstrings/comments
- Follows {language} conventions
- Is secure and efficient

Return only the code, preferably in a markdown code block.
Focus on being correct and practical over being clever."""

    def _extract_code(self, response: str) -> str:
        """Extract code from LLM response."""
        response = response.strip()

        # Remove markdown code blocks
        if response.startswith("```"):
            lines = response.split('\n')
            if len(lines) > 1:
                # Find the language identifier line
                first_line = lines[0]
                if first_line.startswith("```") and not first_line == "```":
                    # Skip first line (```python) and last line (```)
                    response = '\n'.join(lines[1:-1])
                else:
                    # Just remove ``` markers
                    response = response[3:]
                    if response.endswith("```"):
                        response = response[:-3]

        return response.strip()

    def _extract_file_path_from_task(
        self,
        task: str,
        language: str,
        working_directory: str = ".",
    ) -> Optional[str]:
        """
        Extract or infer file path from task description.

        Looks for:
        - Explicit file paths in quotes/backticks
        - File path mentions (e.g., "create utils.py", "in app/routes.py")
        - Infers from language and task type

        Returns:
            Absolute file path or None
        """
        # Try explicit patterns first
        # Pattern 1: "create/update/modify X.py" or "X.ts" etc
        for ext in [".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java"]:
            pattern = rf'[\s\'"`]([a-zA-Z_0-9/\\\-]+{ext})[\s\'"`]'
            matches = re.findall(pattern, task)
            if matches:
                file_path = matches[0]
                # Convert to absolute path
                if not os.path.isabs(file_path):
                    return os.path.join(working_directory, file_path)
                return file_path

        # Pattern 2: "in file X" or "file X"
        pattern = r'(?:in|file|path)[\s:]+[`\'"]?([a-zA-Z_0-9/\\\-]+\.[a-zA-Z]+)[`\'"]?'
        matches = re.findall(pattern, task, re.IGNORECASE)
        if matches:
            file_path = matches[0]
            if not os.path.isabs(file_path):
                return os.path.join(working_directory, file_path)
            return file_path

        # Pattern 3: Infer from common locations based on language
        task_lower = task.lower()

        if language == "python":
            # Common Python patterns
            if any(word in task_lower for word in ["model", "schema", "entity"]):
                return os.path.join(working_directory, "models", "generated_model.py")
            elif any(word in task_lower for word in ["route", "endpoint", "api", "handler"]):
                return os.path.join(working_directory, "routes", "generated_routes.py")
            elif any(word in task_lower for word in ["service", "business logic"]):
                return os.path.join(working_directory, "services", "generated_service.py")
            elif any(word in task_lower for word in ["util", "helper", "common"]):
                return os.path.join(working_directory, "utils", "generated_utils.py")
            elif "test" in task_lower:
                return os.path.join(working_directory, "tests", "test_generated.py")
            # Default Python location
            return os.path.join(working_directory, "generated_code.py")

        elif language in ["typescript", "javascript"]:
            # Common TypeScript/JavaScript patterns
            if any(word in task_lower for word in ["component", "ui"]):
                return os.path.join(working_directory, "src", "components", "GeneratedComponent.tsx")
            elif any(word in task_lower for word in ["hook", "use"]):
                return os.path.join(working_directory, "src", "hooks", "useGenerated.ts")
            elif any(word in task_lower for word in ["service", "api"]):
                return os.path.join(working_directory, "src", "services", "generatedService.ts")
            elif "test" in task_lower:
                return os.path.join(working_directory, "src", "__tests__", "generated.test.ts")
            # Default TS location
            return os.path.join(working_directory, "src", "generated.ts")

        # Fallback: generated.py in working directory
        return os.path.join(working_directory, "generated.py")

    async def _verify_file_exists(self, file_path: str) -> bool:
        """
        Verify that a file was actually created.

        Args:
            file_path: Path to verify

        Returns:
            True if file exists and has content
        """
        if not file_path:
            return False

        try:
            path = Path(file_path)
            if path.exists() and path.is_file():
                size = path.stat().st_size
                if size > 0:
                    self.logger.logger.info(
                        "Verified file creation",
                        path=file_path,
                        size_bytes=size,
                    )
                    return True
                else:
                    self.logger.logger.warning("File exists but is empty", path=file_path)
                    return False
            else:
                self.logger.logger.error("File was not created", path=file_path)
                return False
        except Exception as e:
            self.logger.logger.error("Failed to verify file", error=str(e))
            return False

    async def validate(self, result: AgentResult) -> bool:
        """Validate coding result."""
        return result.is_success() and result.output and len(result.output) > 0

    async def generate_function(
        self,
        spec: str,
        language: str = "python",
    ) -> AgentResult:
        """Generate a function based on specification."""
        task = f"Create a {language} function: {spec}"
        return await self.execute(task, language=language)

    async def refactor_code(
        self,
        code: str,
        goals: list,
    ) -> AgentResult:
        """Refactor existing code."""
        task = f"Refactor code with goals: {', '.join(goals)}"
        return await self.execute(task, code=code)

    async def fix_bug(
        self,
        code: str,
        error_message: str,
    ) -> AgentResult:
        """Fix a bug in code."""
        task = f"Fix bug: {error_message}"
        return await self.execute(task, code=code, error=error_message)


async def create_coding_agent() -> CodingAgent:
    """Create a coding agent instance."""
    config = AgentConfig(
        name="coding_agent",
        description="Code generation agent powered by LLM",
        model="claude-sonnet-4-5-20250929",
        temperature=0.3,
        max_tokens=8192,
    )

    return CodingAgent(config)
