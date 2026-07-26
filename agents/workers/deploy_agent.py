"""
Deploy Agent - LLM-Powered

Specialized agent for deployment operations using Claude/GPT.
"""

import time
from typing import Any, Dict, List

from agents.base.base_agent import AgentConfig, AgentResult, BaseAgent
from agents.tools.tool_registry import get_tool_registry
from models.llm.llm_wrapper import get_llm_wrapper
from utils.logger import AgentLogger


class DeploymentAgent(BaseAgent):
    """
    Agent specialized in deployment operations using LLMs.

    Capabilities:
    - Build applications
    - Create deployment configurations
    - Execute deployments
    - Manage environment configs
    - Rollback deployments
    """

    def __init__(self, config: AgentConfig):
        """Initialize deployment agent."""
        super().__init__(config)
        self.llm = get_llm_wrapper()
        self.tools = get_tool_registry()
        self.logger.logger.info("Deployment agent initialized with LLM")

    async def execute(self, task: str, **kwargs: Any) -> AgentResult:
        """
        Execute a deployment task.

        Args:
            task: Task description
            **kwargs: Additional parameters

        Returns:
            Agent result
        """
        start_time = time.time()

        self.logger.logger.info("Executing deployment task", task=task)

        # Determine task type
        if "build" in task.lower():
            return await self._build(task, **kwargs)
        elif "deploy" in task.lower():
            return await self._deploy(task, **kwargs)
        elif "rollback" in task.lower():
            return await self._rollback(task, **kwargs)
        elif "config" in task.lower() or "environment" in task.lower():
            return await self._generate_config(task, **kwargs)
        else:
            # Use LLM to figure out what to do
            return await self._llm_assisted_deploy(task, **kwargs)

    async def _build(self, task: str, **kwargs) -> AgentResult:
        """Build application."""
        build_type = kwargs.get("build_type", "docker")
        project_path = kwargs.get("project_path", ".")

        self.logger.logger.info("Building application", type=build_type)

        if build_type == "docker":
            # Build Docker image
            result = await self.tools.execute_tool(
                "command_runner",
                "execute",
                command="docker",
                args=["build", "-t", "app:latest", project_path],
                timeout=300,
            )

            return AgentResult(
                status="success" if result["success"] else "error",
                output=result.get("result", {}).get("stdout", ""),
                errors=[result.get("error")] if not result["success"] else [],
                metadata={"build_type": build_type},
            )

        elif build_type == "npm":
            result = await self.tools.execute_tool(
                "command_runner",
                "execute",
                command="npm",
                args=["run", "build"],
                cwd=project_path,
                timeout=180,
            )

            return AgentResult(
                status="success" if result["success"] else "error",
                output=result.get("result", {}).get("stdout", ""),
                errors=[result.get("error")] if not result["success"] else [],
            )

        else:
            return AgentResult(
                status="error",
                errors=[f"Unknown build type: {build_type}"],
            )

    async def _deploy(self, task: str, **kwargs) -> AgentResult:
        """Deploy application."""
        environment = kwargs.get("environment", "staging")
        deploy_type = kwargs.get("deploy_type", "docker")

        self.logger.logger.info("Deploying application", env=environment, type=deploy_type)

        if environment == "production":
            # Require confirmation for production
            return AgentResult(
                status="partial",
                output="Production deployment requires confirmation",
                errors=["Use --confirm flag or manual approval for production deployment"],
                next_steps=["Get approval", "Re-run with confirmation"],
            )

        if deploy_type == "docker":
            result = await self.tools.execute_tool(
                "command_runner",
                "execute",
                command="docker",
                args=["run", "-d", "--name", "app", "-p", "80:80", "app:latest"],
                timeout=60,
            )

            if result["success"]:
                return AgentResult(
                    status="success",
                    output="Application deployed successfully",
                    metadata={"environment": environment, "container_id": "app"},
                    next_steps=["Verify deployment", "Check application logs", "Run health checks"],
                )
            else:
                return AgentResult(
                    status="error",
                    errors=[result.get("error")],
                )

        return AgentResult(
            status="error",
            errors=[f"Unknown deploy type: {deploy_type}"],
        )

    async def _rollback(self, task: str, **kwargs) -> AgentResult:
        """Rollback deployment."""
        self.logger.logger.info("Rolling back deployment")

        result = await self.tools.execute_tool(
            "command_runner",
            "execute",
            command="docker",
            args=["stop", "app"],
            timeout=30,
        )

        result2 = await self.tools.execute_tool(
            "command_runner",
            "execute",
            command="docker",
            args=["rm", "app"],
            timeout=10,
        )

        if result["success"] and result2["success"]:
            return AgentResult(
                status="success",
                output="Deployment rolled back successfully",
                next_steps=["Verify rollback", "Deploy previous version"],
            )
        else:
            return AgentResult(
                status="error",
                errors=["Rollback failed"],
            )

    async def _generate_config(self, task: str, **kwargs) -> AgentResult:
        """Generate deployment configuration using LLM."""
        app_type = kwargs.get("app_type", "python")
        target = kwargs.get("target", "docker")

        prompt = f"""Generate deployment configuration for:
Application Type: {app_type}
Target: {target}
Task: {task}

Include:
- Configuration files
- Environment variables
- Deployment scripts
- Health checks
- Scaling recommendations"""

        system_prompt = """You are a DevOps expert specializing in deployment automation.

Generate production-ready deployment configurations that:
- Follow best practices for the target platform
- Include security considerations
- Handle scaling and load balancing
- Include monitoring and logging
- Provide rollback strategies
- Are well-documented with comments

Return configuration files in markdown code blocks with file paths as headers."""

        try:
            llm_response = await self.llm.generate(
                prompt=prompt,
                model=self.config.model,
                system_prompt=system_prompt,
                temperature=0.3,
                max_tokens=4096,
            )

            config = llm_response.content

            return AgentResult(
                status="success",
                output=config,
                metadata={"app_type": app_type, "target": target},
                next_steps=[
                    "Review generated configuration",
                    "Customize for specific needs",
                    "Test in staging environment",
                ],
            )

        except Exception as e:
            return AgentResult(
                status="error",
                errors=[str(e)],
            )

    async def _llm_assisted_deploy(self, task: str, **kwargs) -> AgentResult:
        """Use LLM to assist with deployment."""
        context = kwargs.get("context", {})

        prompt = f"""Help with deployment task: {task}

Context: {context if context else 'None provided'}

Analyze what needs to be done and provide:
1. Step-by-step deployment plan
2. Required commands
3. Configuration changes needed
4. Risks and mitigations
5. Verification steps"""

        system_prompt = """You are a DevOps expert helping with deployments.

Provide clear, actionable deployment guidance including:
- Exact commands to run
- Configuration file changes
- Pre-deployment checks
- Post-deployment verification
- Rollback procedures

Be specific and practical. Assume the user has technical knowledge but needs guidance on this specific deployment."""

        try:
            response = await self.llm.generate(
                prompt=prompt,
                model=self.config.model,
                system_prompt=system_prompt,
                temperature=0.5,
                max_tokens=3072,
            )

            return AgentResult(
                status="success",
                output=response.content,
                metadata={"llm_assisted": True},
                next_steps=["Review deployment plan", "Execute steps", "Verify deployment"],
            )

        except Exception as e:
            return AgentResult(
                status="error",
                errors=[str(e)],
            )

    async def validate(self, result: AgentResult) -> bool:
        """Validate deployment result."""
        return result.status in ["success", "partial", "error"]

    async def create_deployment_plan(
        self,
        application: str,
        environment: str = "production",
    ) -> AgentResult:
        """Create a deployment plan."""
        task = f"Create deployment plan for {application} to {environment}"
        return await self.execute(
            task,
            context={"application": application, "environment": environment},
        )

    async def verify_deployment(self, url: str = "http://localhost:80") -> AgentResult:
        """Verify deployment is working."""
        result = await self.tools.execute_tool(
            "command_runner",
            "execute",
            command="curl",
            args=["-f", url],
            timeout=10,
        )

        return AgentResult(
            status="success" if result["success"] else "error",
            output=f"Health check: {'PASS' if result['success'] else 'FAIL'}",
            metadata={"url": url},
        )


async def create_deploy_agent() -> DeploymentAgent:
    """Create a deployment agent instance."""
    config = AgentConfig(
        name="deploy_agent",
        description="Deployment operations agent powered by LLM",
        model="claude-sonnet-4-5-20250929",
        temperature=0.3,
        max_tokens=4096,
    )

    return DeploymentAgent(config)
