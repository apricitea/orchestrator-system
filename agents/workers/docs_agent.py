"""
Documentation Agent - LLM-Powered

Specialized agent for generating documentation using Claude/GPT.
"""

import os
import time
from pathlib import Path
from typing import Any, Dict

from agents.base.base_agent import AgentConfig, AgentResult, BaseAgent
from agents.tools.tool_registry import get_tool_registry
from models.llm.llm_wrapper import LLMResponse, get_llm_wrapper
from utils.logger import AgentLogger


class DocumentationAgent(BaseAgent):
    """
    Agent specialized in documentation generation using LLMs.

    Capabilities:
    - Generate API documentation
    - Create README files
    - Write code comments
    - Generate docstrings
    - Create user guides
    """

    def __init__(self, config: AgentConfig):
        """Initialize documentation agent."""
        super().__init__(config)
        self.llm = get_llm_wrapper()
        self.tools = get_tool_registry()
        self.logger.logger.info("Documentation agent initialized with LLM")

    async def execute(self, task: str, **kwargs: Any) -> AgentResult:
        """
        Execute a documentation task using LLM.

        Args:
            task: Task description
            **kwargs: Additional parameters

        Returns:
            Agent result with generated documentation
        """
        start_time = time.time()

        self.logger.logger.info("Executing documentation task", task=task)

        # Extract parameters
        code = kwargs.get("code", "")
        file_path = kwargs.get("file_path", "README.md")
        doc_type = kwargs.get("doc_type", "general")
        language = kwargs.get("language", "python")
        project_name = kwargs.get("project_name", "Project")
        working_directory = kwargs.get("working_directory", ".")

        # FIX: Convert relative file paths to absolute paths
        if file_path and not os.path.isabs(file_path):
            file_path = os.path.join(working_directory, file_path)
            self.logger.logger.info("Converted relative path to absolute", path=file_path)

        # Build prompt
        prompt = self._build_prompt(
            task=task,
            code=code,
            doc_type=doc_type,
            language=language,
            project_name=project_name,
        )

        # Get system prompt
        system_prompt = self._get_system_prompt(doc_type)

        try:
            llm_response: LLMResponse = await self.llm.generate(
                prompt=prompt,
                model=self.config.model,
                system_prompt=system_prompt,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )

            documentation = llm_response.content

            # Write to file if specified
            if file_path:
                write_result = await self.tools.execute_tool(
                    "file_ops",
                    "write_file",
                    path=file_path,
                    content=documentation,
                )

                if not write_result["success"]:
                    return AgentResult(
                        status="error",
                        errors=[f"Failed to write documentation: {write_result.get('error')}"],
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
                output=documentation,
                metadata={
                    "file_path": file_path,
                    "doc_type": doc_type,
                    "tokens_used": llm_response.total_tokens,
                },
                next_steps=[
                    "Review documentation for accuracy",
                    "Update as code changes",
                    "Add examples and tutorials",
                ],
                duration_ms=duration_ms,
            )

        except Exception as e:
            self.logger.logger.error("Documentation generation failed", error=str(e))
            return AgentResult(
                status="error",
                errors=[str(e)],
            )

    def _build_prompt(
        self,
        task: str,
        code: str,
        doc_type: str,
        language: str,
        project_name: str,
    ) -> str:
        """Build the prompt for documentation generation."""
        prompt_parts = [f"Task: {task}"]

        if project_name:
            prompt_parts.append(f"Project: {project_name}")

        prompt_parts.append(f"Documentation Type: {doc_type}")

        if language:
            prompt_parts.append(f"Language: {language}")

        if code:
            # Include a sample of the code
            lines = code.split('\n')
            sample = '\n'.join(lines[:50])  # First 50 lines
            if len(lines) > 50:
                sample += f"\n\n... ({len(lines) - 50} more lines)"
            prompt_parts.append(f"\nCode sample:\n```\n{sample}\n```")

        prompt_parts.append("\nGenerate clear, comprehensive documentation.")

        return "\n".join(prompt_parts)

    def _get_system_prompt(self, doc_type: str) -> str:
        """Get system prompt for documentation."""
        base = """You are an expert technical writer.

Generate documentation that is:
- Clear and concise
- Well-structured with headings and sections
- Easy to understand for the target audience
- Includes practical examples where relevant
- Uses proper formatting (markdown, etc.)
- Accurate and comprehensive
"""

        type_specific = {
            "api": """For API documentation, include:
- Endpoint descriptions
- Request/response formats
- Authentication requirements
- Error codes
- Usage examples
- Parameter descriptions""",

            "readme": """For README files, include:
- Project title and brief description
- Installation instructions
- Quick start guide
- Usage examples
- Configuration options
- Contributing guidelines
- License information""",

            "code": """For code documentation, include:
- Module/function descriptions
- Parameter explanations
- Return value descriptions
- Usage examples
- Notes on edge cases
- Requirements and dependencies""",

            "user_guide": """For user guides, include:
- Step-by-step instructions
- Screenshots or diagrams (described in text)
- Troubleshooting sections
- FAQ if applicable
- Best practices""",
        }

        return base + "\n\n" + type_specific.get(doc_type, "")

    async def validate(self, result: AgentResult) -> bool:
        """Validate documentation result."""
        return result.is_success() and result.output

    async def generate_readme(
        self,
        project_path: str = ".",
        project_name: str = "Project",
    ) -> AgentResult:
        """Generate README.md for a project."""
        task = "Generate comprehensive README.md"
        return await self.execute(
            task,
            file_path=f"{project_path}/README.md",
            doc_type="readme",
            project_name=project_name,
        )

    async def generate_api_docs(
        self,
        code: str,
        output_path: str = "docs/api.md",
    ) -> AgentResult:
        """Generate API documentation."""
        task = "Generate API documentation"
        return await self.execute(
            task,
            code=code,
            file_path=output_path,
            doc_type="api",
        )

    async def add_docstrings(
        self,
        code: str,
        language: str = "python",
    ) -> AgentResult:
        """Add docstrings to code."""
        task = "Add comprehensive docstrings to all functions and classes"
        result = await self.execute(
            task,
            code=code,
            doc_type="code",
            language=language,
        )

        # Update the file with docstrings
        if result.is_success():
            # The output is the documented code
            return AgentResult(
                status="success",
                output=result.output,
                metadata=result.metadata,
                next_steps=["Review docstrings for accuracy", "Update documentation generation if needed"],
            )

        return result


async def create_docs_agent() -> DocumentationAgent:
    """Create a documentation agent instance."""
    config = AgentConfig(
        name="docs_agent",
        description="Documentation generation agent powered by LLM",
        model="claude-haiku-4-5",
        temperature=0.5,
        max_tokens=4096,
    )

    return DocumentationAgent(config)
