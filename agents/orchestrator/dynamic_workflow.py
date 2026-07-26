"""
Dynamic Workflow Generator

Generates context-aware workflows instead of rigid templates.
Analyzes task context and adapts the workflow accordingly.

Examples:
- README update → Skip security scan, skip tests
- Database migration → Add rollback plan, add manual testing
- API endpoint → Add integration tests, add API docs
- Security fix → Fast-track review, skip docs
"""

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Literal

from anthropic import AsyncAnthropic
from utils.logger import get_logger


class TaskType(str, Enum):
    """Types of tasks requiring different workflows."""
    FEATURE = "feature"
    BUGFIX = "bugfix"
    REFACTOR = "refactor"
    DOCUMENTATION = "documentation"
    CONFIGURATION = "configuration"
    TEST = "test"
    SECURITY = "security"
    PERFORMANCE = "performance"
    DEPLOYMENT = "deployment"
    HOTFIX = "hotfix"
    MISC = "misc"


class RiskLevel(str, Enum):
    """Risk level of a task."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class WorkflowStep:
    """A single step in the workflow."""
    agent: str
    task: str
    priority: str
    dependencies: List[int]
    context: Dict[str, Any]
    conditional: Optional[str] = None  # Condition for including this step
    optional: bool = False


@dataclass
class DynamicWorkflow:
    """Dynamically generated workflow."""
    task_type: TaskType
    risk_level: RiskLevel
    steps: List[WorkflowStep]
    requires_human_approval: bool
    estimated_duration_minutes: int
    rationale: str  # Why this workflow was chosen


class DynamicWorkflowGenerator:
    """
    Generates context-aware workflows using LLM reasoning.

    Instead of rigid 9-step workflows, analyzes the task and generates
    an appropriate workflow based on:
    - Task type (feature, bugfix, docs, etc.)
    - Risk level (database changes = high risk)
    - Context (hotfix = fast track)
    - Past patterns (what worked before)
    """

    def __init__(self, client: AsyncAnthropic, model: str = "claude-sonnet-4-5-20250929"):
        """Initialize workflow generator."""
        self.client = client
        self.model = model
        self.logger = get_logger("dynamic_workflow")

        self.system_prompt = """You are an expert at planning software development workflows.

Your job is to analyze a task and generate an appropriate workflow - NOT just use a rigid template.

## Key Principles:

1. **Right-size the workflow** - Don't over-engineer simple tasks
2. **Context matters** - A hotfix needs different process than a feature
3. **Risk-based** - High-risk changes need more scrutiny
4. **Efficient** - Skip unnecessary steps

## Task Types:

- **feature**: New functionality (full workflow with testing)
- **bugfix**: Fixing a bug (reproduce → fix → test → review)
- **refactor**: Improving code without changing behavior (tests essential)
- **documentation**: Docs only (minimal testing, no security scan)
- **configuration**: Config changes (validate → test → deploy)
- **test**: Adding tests only (run tests, verify coverage)
- **security**: Security fix (fast-track review, skip docs)
- **performance**: Performance optimization (benchmark first, then optimize)
- **deployment**: Deploy changes (rollback plan critical)
- **hotfix**: Urgent production fix (fast-track everything)

## Risk Levels:

- **LOW**: Config changes, docs, typos, minor CSS
- **MEDIUM**: Features without DB changes, bugfixes
- **HIGH**: Database migrations, API changes, auth changes
- **CRITICAL**: Payment processing, security fixes, data deletion

## Workflow Guidelines:

**ALWAYS INCLUDE:**
1. git_agent → Create branch (unless hotfix to existing branch)
2. git_agent → Commit changes
3. git_agent → Create PR
4. review_agent → Code review

**INCLUDE BASED ON CONTEXT:**
- coding_agent → If writing/modifying code
- testing_agent → If code changes (skip for pure docs)
- security_agent → If code changes (skip for config/docs)
- docs_agent → If user-facing changes (skip for hotfix/internal)
- deploy_agent → If deployment task
- performance testing → If performance task
- integration tests → If API/backend changes
- rollback plan → If deployment or database changes

**SKIP WHEN:**
- Security scan → Documentation-only changes
- Tests → Simple config changes, typo fixes
- Docs → Hotfixes, internal changes
- Full review → Hotfixes (use accelerated review)

## Output Format:

Return JSON with:
{
  "task_type": "feature|bugfix|refactor|...",
  "risk_level": "low|medium|high|critical",
  "steps": [
    {
      "agent": "git_agent",
      "task": "Create feature branch",
      "priority": "high",
      "dependencies": [],
      "context": {},
      "optional": false
    },
    ...
  ],
  "requires_human_approval": true/false,
  "estimated_duration_minutes": 30,
  "rationale": "Why this workflow makes sense for this task"
}

Be smart about it. A README update doesn't need a security scan. A typo fix doesn't need unit tests.
"""

    async def generate_workflow(
        self,
        task: str,
        context: Dict[str, Any],
    ) -> DynamicWorkflow:
        """
        Generate a dynamic workflow based on task analysis.

        Args:
            task: Task description
            context: Task context (working directory, file paths, etc.)

        Returns:
            Dynamically generated workflow
        """
        self.logger.info(
            "Generating dynamic workflow",
            task=task[:50],
            context_keys=list(context.keys()),
        )

        prompt = self._build_prompt(task, context)

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                temperature=0.3,
                system=self.system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            )

            content = response.content[0].text

            # Extract JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            workflow_data = json.loads(content)

            # Convert to WorkflowStep objects
            steps = []
            for step_data in workflow_data.get("steps", []):
                steps.append(WorkflowStep(**step_data))

            workflow = DynamicWorkflow(
                task_type=TaskType(workflow_data.get("task_type", "feature")),
                risk_level=RiskLevel(workflow_data.get("risk_level", "medium")),
                steps=steps,
                requires_human_approval=workflow_data.get("requires_human_approval", False),
                estimated_duration_minutes=workflow_data.get("estimated_duration_minutes", 30),
                rationale=workflow_data.get("rationale", ""),
            )

            self.logger.info(
                "Workflow generated",
                task_type=workflow.task_type,
                risk_level=workflow.risk_level,
                num_steps=len(workflow.steps),
                requires_human=workflow.requires_human_approval,
            )

            return workflow

        except Exception as e:
            self.logger.error("Workflow generation failed", error=str(e))
            # Fallback to standard workflow
            return self._fallback_workflow(task, context)

    def _build_prompt(self, task: str, context: Dict[str, Any]) -> str:
        """Build prompt for workflow generation."""
        prompt_parts = [
            "## Task:\n" + task,
        ]

        # Add context
        if "working_directory" in context:
            prompt_parts.append(f"\n## Working Directory:\n{context['working_directory']}")

        if "files_changed" in context:
            prompt_parts.append(f"\n## Files Changed:\n{context['files_changed']}")

        if "security_requirements" in context:
            prompt_parts.append(f"\n## Security Requirements:\n{context['security_requirements']}")

        # Detect hints from task
        task_lower = task.lower()
        hints = []

        if any(word in task_lower for word in ["hotfix", "urgent", "production issue"]):
            hints.append("This is a HOTFIX - needs fast-track workflow")

        if any(word in task_lower for word in ["database", "migration", "schema"]):
            hints.append("This involves DATABASE CHANGES - high risk, needs rollback plan")

        if any(word in task_lower for word in ["readme", "documentation", "docs"]):
            hints.append("This is DOCUMENTATION only - can skip security scan and tests")

        if any(word in task_lower for word in ["config", "configuration", "setting"]):
            hints.append("This is a CONFIGURATION change - needs validation but minimal testing")

        if any(word in task_lower for word in ["security", "vulnerability", "cve"]):
            hints.append("This is a SECURITY fix - needs fast-track review, skip docs")

        if any(word in task_lower for word in ["api", "endpoint", "route"]):
            hints.append("This is an API change - needs integration testing")

        if hints:
            prompt_parts.append("\n## Detected Context:\n" + "\n".join(f"- {h}" for h in hints))

        prompt_parts.append(
            "\n\nGenerate an appropriate workflow for this task."
            "\nBe smart about what steps to include and what to skip."
        )

        return "\n".join(prompt_parts)

    def _fallback_workflow(
        self,
        task: str,
        context: Dict[str, Any],
    ) -> DynamicWorkflow:
        """Generate fallback workflow if LLM fails."""
        self.logger.warning("Using fallback workflow")

        # Simple heuristic-based workflow
        task_lower = task.lower()

        # Detect task type
        if any(word in task_lower for word in ["hotfix", "urgent"]):
            task_type = TaskType.HOTFIX
        elif any(word in task_lower for word in ["bug", "fix", "issue"]):
            task_type = TaskType.BUGFIX
        elif any(word in task_lower for word in ["doc", "readme", "comment"]):
            task_type = TaskType.DOCUMENTATION
        elif any(word in task_lower for word in ["security", "vulnerab"]):
            task_type = TaskType.SECURITY
        elif any(word in task_lower for word in ["perform", "speed", "optim"]):
            task_type = TaskType.PERFORMANCE
        else:
            task_type = TaskType.FEATURE

        # Detect risk
        if any(word in task_lower for word in ["database", "migration", "schema", "payment"]):
            risk_level = RiskLevel.HIGH
        elif any(word in task_lower for word in ["api", "auth", "security"]):
            risk_level = RiskLevel.MEDIUM
        else:
            risk_level = RiskLevel.LOW

        # Build workflow based on type
        if task_type == TaskType.DOCUMENTATION:
            steps = [
                WorkflowStep(
                    agent="git_agent",
                    task="Create branch",
                    priority="high",
                    dependencies=[],
                    context={},
                ),
                WorkflowStep(
                    agent="coding_agent",
                    task=task,
                    priority="high",
                    dependencies=[0],
                    context={},
                ),
                WorkflowStep(
                    agent="review_agent",
                    task="Quick review of documentation",
                    priority="high",
                    dependencies=[1],
                    context={},
                ),
                WorkflowStep(
                    agent="git_agent",
                    task="Commit and create PR",
                    priority="high",
                    dependencies=[2],
                    context={},
                ),
            ]
            requires_human = False
            duration = 15

        elif task_type == TaskType.HOTFIX:
            steps = [
                WorkflowStep(
                    agent="coding_agent",
                    task=task,
                    priority="high",
                    dependencies=[],
                    context={},
                ),
                WorkflowStep(
                    agent="testing_agent",
                    task="Quick smoke test",
                    priority="high",
                    dependencies=[0],
                    context={},
                ),
                WorkflowStep(
                    agent="security_agent",
                    task="Fast security scan",
                    priority="high",
                    dependencies=[0],
                    context={},
                ),
                WorkflowStep(
                    agent="review_agent",
                    task="Accelerated review for hotfix",
                    priority="high",
                    dependencies=[1, 2],
                    context={},
                ),
                WorkflowStep(
                    agent="git_agent",
                    task="Commit and create PR with hotfix label",
                    priority="high",
                    dependencies=[3],
                    context={"labels": ["hotfix", "fast-track"]},
                ),
            ]
            requires_human = True
            duration = 20

        else:
            # Standard feature workflow
            steps = [
                WorkflowStep(
                    agent="git_agent",
                    task="Create branch",
                    priority="high",
                    dependencies=[],
                    context={},
                ),
                WorkflowStep(
                    agent="coding_agent",
                    task=task,
                    priority="high",
                    dependencies=[0],
                    context=context,
                ),
                WorkflowStep(
                    agent="testing_agent",
                    task="Write and run tests",
                    priority="high",
                    dependencies=[1],
                    context={},
                ),
                WorkflowStep(
                    agent="security_agent",
                    task="Security scan",
                    priority="high",
                    dependencies=[1],
                    context={},
                ),
                WorkflowStep(
                    agent="review_agent",
                    task="Full code review",
                    priority="high",
                    dependencies=[2, 3],
                    context={},
                ),
                WorkflowStep(
                    agent="git_agent",
                    task="Commit and create PR",
                    priority="high",
                    dependencies=[4],
                    context={},
                ),
                WorkflowStep(
                    agent="docs_agent",
                    task="Update documentation",
                    priority="medium",
                    dependencies=[5],
                    context={},
                ),
            ]
            requires_human = risk_level != RiskLevel.LOW
            duration = 45

        return DynamicWorkflow(
            task_type=task_type,
            risk_level=risk_level,
            steps=steps,
            requires_human_approval=requires_human,
            estimated_duration_minutes=duration,
            rationale=f"Fallback workflow for {task_type} with {risk_level} risk",
        )


def get_dynamic_workflow_generator(
    client: AsyncAnthropic,
    model: str = "claude-sonnet-4-5-20250929",
) -> DynamicWorkflowGenerator:
    """Get workflow generator instance."""
    return DynamicWorkflowGenerator(client=client, model=model)
