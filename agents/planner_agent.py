"""
Technical Planner Agent - Translates User Requests into Technical Plans

This agent takes user requests from Trello and converts them into clear,
well-structured technical plans that follow best practices and are ready
for autonomous execution by the orchestrator.
"""

from typing import Any, Dict, Optional

from agents.base.base_agent import AgentConfig, AgentResult, BaseAgent
from models.llm.llm_wrapper import get_llm_wrapper
from utils.logger import AgentLogger


class TechnicalPlannerAgent(BaseAgent):
    """
    Technical Planner Agent for refining user requests.

    Capabilities:
    - Convert user requests into clear technical specifications
    - Identify required components and dependencies
    - Suggest best practices and implementation strategies
    - Create structured technical plans for autonomous execution
    """

    def __init__(self, config: AgentConfig):
        """Initialize technical planner agent."""
        super().__init__(config)
        self.llm = get_llm_wrapper()
        self.logger.logger.info("Technical planner agent initialized")

    async def execute(self, task: str, **kwargs: Any) -> AgentResult:
        """
        Execute technical planning task.

        Args:
            task: User request to plan
            **kwargs: Additional context (project_name, current_state, etc.)

        Returns:
            Technical plan as AgentResult
        """
        project_name = kwargs.get("project_name", "")
        project_path = kwargs.get("project_path", "")

        # Analyze existing codebase if project path is provided
        codebase_analysis = ""
        if project_path:
            codebase_analysis = await self._analyze_codebase(project_path)

        # Build planning prompt
        planning_prompt = self._build_planning_prompt(
            task, project_name, codebase_analysis
        )

        # Generate technical plan
        response = await self.llm.generate(
            prompt=planning_prompt,
            system_prompt=self._get_system_prompt(),
            temperature=0.3,
            max_tokens=4096,
        )

        # Check if we got a valid response
        if not response or not response.content:
            return AgentResult(
                status="error",
                errors=["Failed to generate technical plan - no response from LLM"],
            )

        plan = response.content

        self.logger.logger.info(
            "Technical plan generated",
            task_length=len(task),
            plan_length=len(plan),
        )

        return AgentResult(
            status="success",
            output=plan,
            metadata={"original_request": task, "project": project_name},
        )

    async def validate(self, result: AgentResult) -> bool:
        """
        Validate the technical plan result.

        Args:
            result: Result to validate

        Returns:
            True if valid, False otherwise
        """
        # Check if we have a plan
        if not result.output or len(result.output) < 100:
            return False

        # Check for key sections in a technical plan
        required_keywords = [
            "implement",
            "step",
            "requirement",
        ]

        plan_lower = result.output.lower()
        return any(keyword in plan_lower for keyword in required_keywords)

    async def _analyze_codebase(self, project_path: str) -> str:
        """
        Analyze the existing codebase to understand the tech stack.

        Args:
            project_path: Path to the project

        Returns:
            Analysis summary
        """
        from pathlib import Path

        analysis = []
        path = Path(project_path)

        # Check for package.json (JavaScript/TypeScript project)
        if (path / "package.json").exists():
            analysis.append("JavaScript/TypeScript project detected")
            # Try to read dependencies
            try:
                with open(path / "package.json") as f:
                    import json
                    pkg = json.load(f)
                    deps = pkg.get("dependencies", {})
                    dev_deps = pkg.get("devDependencies", {})

                    if "react" in deps or "react" in dev_deps:
                        analysis.append("- Framework: React")
                    if "next" in deps or "next" in dev_deps:
                        analysis.append("- Framework: Next.js")
                    if "vue" in deps or "vue" in dev_deps:
                        analysis.append("- Framework: Vue.js")
                    if "@tailwindcss" in dev_deps:
                        analysis.append("- Styling: Tailwind CSS")
                    if "typescript" in dev_deps:
                        analysis.append("- Language: TypeScript")
            except:
                pass

        # Check for requirements.txt (Python project)
        elif (path / "requirements.txt").exists():
            analysis.append("Python project detected")
            try:
                with open(path / "requirements.txt") as f:
                    requirements = f.read()
                    if "flask" in requirements.lower():
                        analysis.append("- Framework: Flask")
                    if "django" in requirements.lower():
                        analysis.append("- Framework: Django")
                    if "fastapi" in requirements.lower():
                        analysis.append("- Framework: FastAPI")
            except:
                pass

        # Check for go.mod (Go project)
        elif (path / "go.mod").exists():
            analysis.append("Go project detected")

        # Check directory structure
        if (path / "static").exists() and (path / "templates").exists():
            analysis.append("- Structure: Flask/Jinja2 templates")

        if (path / "src").exists():
            analysis.append("- Structure: src/ directory")

        return "\n".join(analysis) if analysis else "Generic project structure"

    def _get_system_prompt(self) -> str:
        """Get system prompt for technical planning."""
        return """You are an expert Technical Planner and Software Architect.

Your role is to translate user requests into clear, actionable technical plans that autonomous AI agents can execute.

## Technical Planning Guidelines:

1. **Understand Requirements**: Parse user requests to identify the core functional requirements
2. **Apply Best Practices**: Recommend industry-standard approaches and patterns
3. **Be Specific**: Provide concrete implementation details, not vague suggestions
4. **Consider Constraints**: Think about performance, maintainability, and scalability
5. **Structure the Plan**: Organize into logical steps with dependencies

## Technical Plan Structure:

### Overview
- Clear description of what needs to be built
- Key technical decisions and rationale

### Requirements
- Functional requirements (what it should do)
- Non-functional requirements (performance, security, etc.)

### Implementation Plan
1. **Architecture/Design**
   - Component structure
   - Data models (if applicable)
   - Key interfaces

2. **Implementation Steps** (in order)
   - Step 1: [Clear action item with technical details]
   - Step 2: [Next action with dependencies]
   - ...

3. **Technical Specifications**
   - File names and locations
   - Function/class names
   - APIs to use
   - Dependencies to install

4. **Testing & Validation**
   - Test cases to implement
   - Validation criteria
   - Edge cases to handle

5. **Best Practices Applied**
   - Security considerations
   - Error handling
   - Code organization
   - Documentation

## Output Format:

Provide a clear, well-structured technical plan using markdown formatting.

Be specific about:
- File paths (e.g., `src/components/HeroSection.tsx`)
- Component/function names (e.g., `getTopWikipediaArticle()`)
- Libraries to use (e.g., "Use React Query for data fetching")
- Data structures (e.g., "interface Article { title: string, views: number }")

The plan should be detailed enough that an autonomous developer can execute it without clarification."""

    def _build_planning_prompt(
        self,
        task: str,
        project_name: str,
        codebase_analysis: str,
    ) -> str:
        """Build planning prompt from user request."""
        prompt = f"""## User Request:
{task}

"""

        if project_name:
            prompt += f"""
## Project:
{project_name}
"""

        if codebase_analysis:
            prompt += f"""
## Existing Codebase Analysis:
{codebase_analysis}

IMPORTANT: Your technical plan MUST match the existing tech stack and project structure detected above.
"""

        prompt += """

## Your Task:
Create a detailed technical plan for implementing this request that matches the existing codebase.

Your plan should:
1. Clarify what needs to be built (interpret requirements)
2. Match the existing tech stack (Python/Flask vs React/TypeScript, etc.)
3. Provide specific implementation steps using the RIGHT framework/language
4. Include file names, component names, and technical details
5. Consider best practices, testing, and edge cases

Be specific and actionable. The autonomous agents will execute your plan.
"""

        return prompt


def get_technical_planner() -> TechnicalPlannerAgent:
    """Get singleton technical planner agent instance."""
    return TechnicalPlannerAgent(
        AgentConfig(
            name="technical_planner",
            description="Translates user requests into technical plans",
            model="claude-sonnet-4-5-20250929",
            temperature=0.3,
            max_tokens=4096,
        )
    )
