"""
Specifications Agent - Generates detailed task specifications from user requests.

This agent takes a brief user request and expands it into a detailed
task specification suitable for the orchestrator agent to execute.
"""

import asyncio
import os
from pathlib import Path
from typing import Optional

from anthropic import AsyncAnthropic
from config.settings import get_settings
from utils.logger import get_logger

logger = get_logger("specs_agent")


class AgentResult:
    """Simple result class for specifications agent."""

    def __init__(
        self,
        status: str,
        output: Optional[str] = None,
        errors: Optional[list] = None,
        metadata: Optional[dict] = None,
    ):
        self.status = status
        self.output = output
        self.errors = errors or []
        self.metadata = metadata or {}

    def is_success(self) -> bool:
        return self.status == "success"


class SpecificationsAgent:
    """
    Agent that generates detailed task specifications from brief user requests.

    This agent:
    1. Analyzes the project structure
    2. Understands the existing codebase
    3. Generates detailed requirements and implementation approach
    4. Creates comprehensive task specifications for the orchestrator
    """

    def __init__(self):
        self.settings = get_settings()
        self.projects_dir = Path("/home/ubuntu/projects")
        self.client = AsyncAnthropic(api_key=self.settings.anthropic_api_key)

    async def generate_specification(
        self,
        project_name: str,
        task_title: str,
        user_description: str = "",
        priority: str = "P1",
    ) -> AgentResult:
        """
        Generate a detailed task specification from a user request.

        Args:
            project_name: Name of the project (e.g., "laptop-recommendation")
            task_title: Brief title of the task
            user_description: Additional user context (optional)
            priority: Task priority (P0-P3)

        Returns:
            AgentResult with detailed task specification
        """
        project_path = self.projects_dir / project_name

        if not project_path.exists():
            return AgentResult(
                status="error",
                errors=[f"Project not found: {project_name}"],
            )

        try:
            # Analyze project structure
            project_info = await self._analyze_project(project_path, project_name)

            # Generate the specification
            spec = await self._generate_spec(
                project_name=project_name,
                project_path=project_path,
                task_title=task_title,
                user_description=user_description,
                priority=priority,
                project_info=project_info,
            )

            return AgentResult(
                status="success",
                output=spec,
                metadata={"project_name": project_name, "task_title": task_title},
            )

        except Exception as e:
            logger.error("Failed to generate specification", error=str(e))
            return AgentResult(
                status="error",
                errors=[f"Failed to generate specification: {str(e)}"],
            )

    async def _analyze_project(self, project_path: Path, project_name: str) -> dict:
        """Analyze the project structure and gather context."""

        info = {
            "name": project_name,
            "path": str(project_path),
            "structure": [],
            "tech_stack": [],
            "key_files": [],
        }

        try:
            # Get project structure
            for item in sorted(project_path.iterdir())[:50]:  # Limit to 50 items
                if item.is_dir() and not item.name.startswith("."):
                    # Count files in subdirectory
                    try:
                        files = list(item.rglob("*.*"))
                        if len(files) <= 100:  # Only show smaller directories
                            info["structure"].append(f"📁 {item.name}/")
                    except Exception:
                        pass
                elif item.is_file() and not item.name.startswith("."):
                    info["key_files"].append(f"📄 {item.name}")

            # Detect tech stack from files
            if (project_path / "package.json").exists():
                info["tech_stack"].append("Node.js/npm")
            if (project_path / "requirements.txt").exists():
                info["tech_stack"].append("Python")
            if (project_path / "pyproject.toml").exists():
                info["tech_stack"].append("Python/pyproject")
            if (project_path / "Cargo.toml").exists():
                info["tech_stack"].append("Rust")
            if (project_path / "go.mod").exists():
                info["tech_stack"].append("Go")
            if list(project_path.rglob("*.tsx")) or list(project_path.rglob("*.jsx")):
                info["tech_stack"].append("React/Next.js")
            if list(project_path.rglob("*.vue")):
                info["tech_stack"].append("Vue.js")

        except Exception as e:
            logger.warning("Could not fully analyze project", error=str(e))

        return info

    async def _generate_spec(
        self,
        project_name: str,
        project_path: Path,
        task_title: str,
        user_description: str,
        priority: str,
        project_info: dict,
    ) -> str:
        """Generate the detailed task specification using LLM."""

        # Prepare context for LLM
        context = f"""Project: {project_name}
Working Directory: {project_path}
Task Title: {task_title}
Priority: {priority}

Project Tech Stack: {', '.join(project_info.get('tech_stack', ['Unknown']))}

Project Structure:
{chr(10).join(project_info.get('structure', [])[:20])}

Key Files:
{chr(10).join(project_info.get('key_files', [])[:30])}

User Request: {user_description or task_title}

---

You are a technical project manager. Generate a DETAILED task specification for the orchestrator agent to implement.

The specification should include:
1. **Working Directory**: Full path to the project
2. **Requirements**: Detailed breakdown of what needs to be implemented (3-7 specific requirements)
3. **Implementation Approach**: Step-by-step technical approach (3-5 steps)
4. **Files to Modify/Create**: Specific files that need work
5. **Testing Requirements**: What tests should be added/modified
6. **Deliverables**: Complete list of expected outputs

Be SPECIFIC and actionable. Include file paths, function names, and technical details.
Keep it concise but comprehensive. 300-600 words total.

Generate the specification now:"""

        try:
            response = await self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2000,
                temperature=0.5,
                system="You are a technical project manager who creates detailed task specifications for software development.",
                messages=[
                    {"role": "user", "content": context},
                ],
            )

            llm_output = response.content[0].text.strip()

        except Exception as e:
            logger.warning("LLM call failed, using fallback", error=str(e))
            llm_output = None

        if not llm_output:
            # Fallback to basic template if LLM fails
            return self._generate_basic_template(
                project_name, project_path, task_title, user_description, priority
            )

        # Format the specification
        spec = f"""## {task_title}

### Task added via Telegram by user

### Working Directory:
{project_path}

### Priority:
{priority}

### Requirements and Implementation Plan:

{llm_output}

### Deliverables:
- Complete implementation
- Tests added/updated
- Git branch, commit, and pull request
- Code follows project patterns
- No breaking changes to existing functionality

---
💡 This task will be picked up by the orchestrator agent and executed automatically."""

        return spec

    def _generate_basic_template(
        self,
        project_name: str,
        project_path: Path,
        task_title: str,
        user_description: str,
        priority: str,
    ) -> str:
        """Generate a basic template if LLM fails."""

        return f"""## {task_title}

### Task added via Telegram

### Working Directory:
{project_path}

### Requirements:
{user_description or task_title}

### Priority:
{priority}

### Implementation Notes:
- Analyze existing code patterns in the project
- Follow the project's coding style and conventions
- Ensure all changes are tested

### Deliverables:
- Implementation
- Tests
- Git branch, commit, and pull request
- Documentation

---
💡 This task will be picked up by the orchestrator agent."""


# Global instance
_specs_agent: Optional[SpecificationsAgent] = None


def get_specs_agent() -> SpecificationsAgent:
    """Get the global specifications agent instance."""
    global _specs_agent
    if _specs_agent is None:
        _specs_agent = SpecificationsAgent()
    return _specs_agent
