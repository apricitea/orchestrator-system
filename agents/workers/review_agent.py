"""
Review Agent - LLM-Powered

Specialized agent for code review and quality assurance using Claude/GPT.
"""

import time
from typing import Any, Dict

from agents.base.base_agent import AgentConfig, AgentResult, BaseAgent
from models.llm.llm_wrapper import LLMResponse, get_llm_wrapper
from utils.logger import AgentLogger


class ReviewAgent(BaseAgent):
    """
    Agent specialized in code review using LLMs.

    Capabilities:
    - Review code quality with LLM analysis
    - Check for bugs and potential issues
    - Verify style guide compliance
    - Security review
    - Performance analysis
    """

    def __init__(self, config: AgentConfig):
        """Initialize review agent."""
        super().__init__(config)
        self.llm = get_llm_wrapper()
        self.logger.logger.info("Review agent initialized with LLM")

    async def execute(self, task: str, **kwargs: Any) -> AgentResult:
        """
        Execute a review task using LLM.

        Args:
            task: Task description
            **kwargs: Additional parameters

        Returns:
            Agent result
        """
        start_time = time.time()

        self.logger.logger.info("Executing review task", task=task)

        code = kwargs.get("code", "")
        file_path = kwargs.get("file_path", "")
        review_type = kwargs.get("review_type", "general")
        language = kwargs.get("language", "python")
        working_directory = kwargs.get("working_directory", ".")

        # If no code provided, try to read from file_path or working directory
        if not code:
            import os

            # If file_path is specified, read that file
            if file_path and os.path.exists(file_path):
                self.logger.logger.info("Reading code from file", file_path=file_path)
                try:
                    with open(file_path, 'r') as f:
                        code = f.read()
                except Exception as e:
                    self.logger.logger.error("Failed to read file", file_path=file_path, error=str(e))
            elif working_directory and working_directory != ".":
                # Search for code files in working directory
                self.logger.logger.info("Searching for code files in working directory", path=working_directory)
                src_dir = os.path.join(working_directory, "src")
                if os.path.exists(src_dir):
                    # Find code files based on language
                    extensions = ['.py', '.ts', '.tsx', '.js', '.jsx']
                    for root, dirs, files in os.walk(src_dir):
                        for file in files:
                            if any(file.endswith(ext) for ext in extensions):
                                full_path = os.path.join(root, file)
                                try:
                                    with open(full_path, 'r') as f:
                                        file_code = f.read()
                                        if code:
                                            code += f"\n\n# File: {full_path}\n{file_code}"
                                        else:
                                            code = f"# File: {full_path}\n{file_code}"
                                        file_path = full_path  # Update file_path to the first found file
                                except Exception:
                                    continue
                                    break

            # If still no code, check git diff for changes
            if not code:
                import subprocess
                try:
                    # Try to get git diff to see what changed
                    result = subprocess.run(
                        ["git", "diff", "--cached"],
                        capture_output=True,
                        text=True,
                        cwd=working_directory,
                        timeout=10
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        code = result.stdout
                        file_path = "git diff --cached"
                        self.logger.logger.info("Using git diff for review", diff_size=len(code))
                    else:
                        # Try unstaged changes
                        result = subprocess.run(
                            ["git", "diff"],
                            capture_output=True,
                            text=True,
                            cwd=working_directory,
                            timeout=10
                        )
                        if result.returncode == 0 and result.stdout.strip():
                            code = result.stdout
                            file_path = "git diff"
                            self.logger.logger.info("Using git diff (unstaged) for review", diff_size=len(code))
                except Exception as e:
                    self.logger.logger.warning("Could not get git diff", error=str(e))

            # If still no code after trying git diff, do a simple task review instead
            if not code:
                self.logger.logger.info("No code to review, performing task validation review")
                # Build a simple prompt based on the task description
                code = f"# Task: {task}\n# No code changes to review - validating task approach only"
                file_path = ""

        # Build prompt for LLM
        prompt = self._build_prompt(task, code, file_path, review_type, language)

        # Get system prompt based on review type
        system_prompt = self._get_system_prompt(review_type)

        try:
            llm_response: LLMResponse = await self.llm.generate(
                prompt=prompt,
                model=self.config.model,
                system_prompt=system_prompt,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )

            review = llm_response.content
            duration_ms = int((time.time() - start_time) * 1000)

            self.logger.log_token_usage(
                model=self.config.model,
                prompt_tokens=llm_response.prompt_tokens,
                completion_tokens=llm_response.completion_tokens,
                total_tokens=llm_response.total_tokens,
            )

            return AgentResult(
                status="success",
                output=review,
                metadata={
                    "file_path": file_path,
                    "review_type": review_type,
                    "language": language,
                    "tokens_used": llm_response.total_tokens,
                },
                next_steps=[
                    "Address critical issues",
                    "Consider suggestions",
                    "Re-review after changes",
                ],
                duration_ms=duration_ms,
            )

        except Exception as e:
            self.logger.logger.error("Review failed", error=str(e))
            return AgentResult(
                status="error",
                errors=[str(e)],
            )

    def _build_prompt(
        self,
        task: str,
        code: str,
        file_path: str,
        review_type: str,
        language: str,
    ) -> str:
        """Build prompt for code review."""
        prompt_parts = [
            f"Task: {task}",
            f"File: {file_path}",
            f"Language: {language}",
            f"Review Type: {review_type}",
            "\nCode to review:",
            f"```\n{code}\n```",
        ]

        return "\n".join(prompt_parts)

    def _get_system_prompt(self, review_type: str) -> str:
        """Get system prompt for review."""
        base = """You are an expert code reviewer with deep knowledge of software engineering best practices.

Provide thorough, constructive code reviews covering:
- Correctness and logic errors
- Security vulnerabilities
- Performance issues
- Code style and readability
- Error handling
- Edge cases and boundary conditions
- Design patterns and architecture

Format your review as:
# Code Review

## Summary
[Brief overall assessment]

## Issues Found
### Critical
- [Issue descriptions]

### Important
- [Issue descriptions]

### Minor
- [Issue descriptions]

## Suggestions
[Improvement suggestions]

## Positive Aspects
[What's done well]

## Overall Assessment
[Approved / Needs Changes / Rejected]

## Next Steps
[Actionable next steps]

Be specific, constructive, and helpful."""

        type_specific = {
            "security": """Focus on:
- Injection vulnerabilities (SQL, XSS, command injection)
- Authentication and authorization issues
- Cryptographic weaknesses
- Secret/credential exposure
- Input validation
- Output encoding
- Dependency vulnerabilities""",

            "performance": """Focus on:
- Algorithmic complexity
- Inefficient operations
- Memory leaks
- Unnecessary computations
- Database query optimization
- Caching opportunities
- Resource management""",

            "style": """Focus on:
- Code formatting and consistency
- Naming conventions
- Code organization
- Comment quality
- Documentation
- Language idioms
- Design patterns""",
        }

        if review_type in type_specific:
            return base + "\n\n" + type_specific[review_type]

        return base

    async def validate(self, result: AgentResult) -> bool:
        """Validate review result."""
        return result.is_success() and result.output

    async def review_code(
        self,
        code: str,
        file_path: str = "unknown",
    ) -> AgentResult:
        """
        Review code for quality and issues.

        Args:
            code: Code to review
            file_path: File path

        Returns:
            Agent result with review
        """
        task = f"Review code in {file_path}"
        return await self.execute(task, code=code, file_path=file_path)

    async def security_review(
        self,
        code: str,
    ) -> AgentResult:
        """
        Perform security review of code.

        Args:
            code: Code to review

        Returns:
            Agent result with security findings
        """
        task = "Security review of code"
        return await self.execute(task, code=code, review_type="security")


async def create_review_agent() -> ReviewAgent:
    """Create a review agent instance."""
    config = AgentConfig(
        name="review_agent",
        description="Code review and quality assurance agent powered by LLM",
        model="claude-sonnet-4-5-20250929",
        temperature=0.3,
        max_tokens=4096,
    )

    return ReviewAgent(config)
