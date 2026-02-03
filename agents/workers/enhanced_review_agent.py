"""
Enhanced Review Agent with Trello Feedback Loop

This agent:
1. Reviews code/PRs
2. Creates Trello tasks for issues found
3. Tracks fixes via commit IDs
4. Closes old PRs when new fixes are ready
"""

import re
import os
import subprocess
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from agents.base.base_agent import AgentConfig, AgentResult, BaseAgent
from models.llm.llm_wrapper import get_llm_wrapper
from utils.logger import AgentLogger
from worker.trello.client import get_trello_client


@dataclass
class ReviewIssue:
    """Represents an issue found during review."""
    severity: str  # "critical", "high", "medium", "low"
    category: str  # "bug", "security", "performance", "style", "documentation"
    description: str
    file_path: str
    line_number: Optional[int]
    suggested_fix: str


class EnhancedReviewAgent(BaseAgent):
    """
    Enhanced review agent that creates feedback loops.

    Workflow:
    1. Review code/PR
    2. Identify issues
    3. Create Trello tasks for each issue
    4. Track original PR number in task metadata
    5. When fixes committed, close old PR
    """

    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self.llm = get_llm_wrapper()
        self.trello = get_trello_client()
        self.logger.logger.info("Enhanced review agent initialized with Trello integration")

    async def execute(self, task: str, **kwargs: Any) -> AgentResult:
        """Execute review with potential Trello task creation."""
        start_time = os.times()[4]

        # Get context
        pr_number = kwargs.get("pr_number")
        commit_hash = kwargs.get("commit_hash")
        working_directory = kwargs.get("working_directory", ".")
        project_name = kwargs.get("project_name", "")

        # Perform the review
        review_result = await self._perform_review(task, **kwargs)

        # If issues found and we have PR context, create Trello tasks
        if pr_number and not review_result.is_success():
            await self._create_fix_tasks(
                pr_number=pr_number,
                commit_hash=commit_hash,
                working_directory=working_directory,
                project_name=project_name,
                errors=review_result.errors or []
            )

        # Check if we should approve or request changes
        if pr_number:
            await self._manage_pr_lifecycle(
                pr_number=pr_number,
                review_result=review_result,
                project_name=project_name
            )

        duration = os.times()[4] - start_time
        review_result.metadata["duration_ms"] = int(duration * 1000)

        return review_result

    async def _perform_review(self, task: str, **kwargs: Any) -> AgentResult:
        """Perform the actual code review with security and quality scanning."""
        import time
        from agents.workers.review_agent import ReviewAgent
        from agents.automation.code_quality_guard import get_code_quality_guard

        all_errors = []
        all_output = []

        # Step 1: Run code quality guard for security and static analysis
        working_directory = kwargs.get("working_directory", ".")
        quality_guard = get_code_quality_guard()

        self.logger.logger.info("Running code quality and security scan")
        quality_issues = quality_guard.check_directory(working_directory)

        if quality_issues:
            critical_issues = quality_guard.get_critical_issues()
            security_issues = quality_guard.get_security_issues()

            self.logger.logger.warning(
                "Quality issues found",
                total=len(quality_issues),
                critical=len(critical_issues),
                security=len(security_issues)
            )

            # Convert quality issues to error messages
            for issue in critical_issues + security_issues:
                error_msg = f"[{issue.severity.value.upper()}] {issue.category}: {issue.title} in {issue.file_path}:{issue.line_number} - {issue.fix_suggestion}"
                all_errors.append(error_msg)
                all_output.append(f"❌ {error_msg}")

            # Generate quality report
            quality_report = quality_guard.generate_report()
            all_output.append(f"\n## Security & Quality Report\n{quality_report}")

        # Step 2: Run original review agent for code logic and architecture
        original_agent = ReviewAgent(self.config)
        review_result = await original_agent.execute(task, **kwargs)

        # Merge results
        if review_result.errors:
            all_errors.extend(review_result.errors)
        if review_result.output:
            all_output.append(review_result.output)

        # If critical issues found, mark as failure
        if quality_guard.get_critical_issues():
            result = AgentResult(
                status="error",
                errors=all_errors,
                output="\n".join(all_output),
                metadata={
                    "security_issues_count": len(quality_guard.get_security_issues()),
                    "critical_issues_count": len(quality_guard.get_critical_issues()),
                    "quality_check_passed": False
                }
            )
        else:
            result = AgentResult(
                status=review_result.status,
                errors=all_errors if all_errors else None,
                output="\n".join(all_output) if all_output else review_result.output,
                metadata={
                    "security_issues_count": len(quality_guard.get_security_issues()),
                    "quality_check_passed": True
                }
            )

        return result

    async def _create_fix_tasks(
        self,
        pr_number: int,
        commit_hash: Optional[str],
        working_directory: str,
        project_name: str,
        errors: List[str]
    ):
        """Create Trello tasks for each issue found."""

        if not self.trello.is_configured():
            self.logger.logger.warning("Trello not configured, cannot create fix tasks")
            return

        # Parse errors into structured issues
        issues = self._parse_errors_into_issues(errors, working_directory)

        if not issues:
            return

        self.logger.logger.info(
            "Creating fix tasks",
            pr_number=pr_number,
            issue_count=len(issues)
        )

        # Group issues by category to reduce task count
        grouped_issues = self._group_issues_by_category(issues)

        # Create Trello card for each group
        for category, category_issues in grouped_issues.items():
            await self._create_trello_fix_task(
                pr_number=pr_number,
                commit_hash=commit_hash,
                project_name=project_name,
                category=category,
                issues=category_issues,
                working_directory=working_directory
            )

    def _parse_errors_into_issues(self, errors: List[str], working_dir: str) -> List[ReviewIssue]:
        """Parse error messages into structured ReviewIssue objects."""
        issues = []

        for error in errors:
            # Determine severity
            severity = "medium"
            if any(word in error.lower() for word in ["critical", "security", "vulnerability", "fatal"]):
                severity = "critical"
            elif any(word in error.lower() for word in ["error", "fail", "bug", "broken"]):
                severity = "high"
            elif any(word in error.lower() for word in ["warning", "consider", "improve"]):
                severity = "low"

            # Determine category
            category = "bug"
            if "security" in error.lower():
                category = "security"
            elif "performance" in error.lower() or "slow" in error.lower():
                category = "performance"
            elif "style" in error.lower() or "format" in error.lower():
                category = "style"
            elif "doc" in error.lower() or "comment" in error.lower():
                category = "documentation"

            # Extract file path if present
            file_path = ""
            path_match = re.search(r'([a-zA-Z0-9_/]+\.[a-z]+)', error)
            if path_match:
                file_path = path_match.group(1)

            issues.append(ReviewIssue(
                severity=severity,
                category=category,
                description=error,
                file_path=file_path,
                line_number=None,
                suggested_fix=""
            ))

        return issues

    def _group_issues_by_category(self, issues: List[ReviewIssue]) -> Dict[str, List[ReviewIssue]]:
        """Group issues by category to reduce task count."""
        grouped = {}

        # Critical issues get their own tasks
        for issue in issues:
            if issue.severity == "critical":
                key = f"CRITICAL: {issue.description[:50]}..."
            else:
                key = issue.category.capitalize()

            if key not in grouped:
                grouped[key] = []
            grouped[key].append(issue)

        return grouped

    async def _create_trello_fix_task(
        self,
        pr_number: int,
        commit_hash: Optional[str],
        project_name: str,
        category: str,
        issues: List[ReviewIssue],
        working_directory: str
    ):
        """Create a Trello task for fixing issues."""

        # Build task title with PR reference for traceability
        title = f"[{project_name}] [agent] P1: Fix {category} (PR #{pr_number})"

        # Build task description with all details
        description = f"""## Fix Issues from PR Review

### Original PR: #{pr_number}
### Commit: {commit_hash or 'N/A'}
### Working Directory: {working_directory}

### Issues Found ({len(issues)}):
"""

        for i, issue in enumerate(issues, 1):
            description += f"\n#### Issue #{i}: [{issue.severity.upper()}] {issue.category}\n"
            description += f"**Description**: {issue.description}\n"
            if issue.file_path:
                description += f"**File**: `{issue.file_path}`\n"
            description += "\n"

        description += f"""
### Requirements:
1. Fix all {len(issues)} issues listed above
2. Add/update tests to prevent regression
3. Ensure all tests pass
4. Update documentation if needed

### Priority: P1 - High (fixes required for PR approval)

### Deliverables:
- Fixed code
- Updated tests
- Git commit with fixes
- New pull request (old PR will be closed)

### Tracking:
- Original PR: #{pr_number}
- Original Commit: {commit_hash}
- Status: Fix in progress
"""

        # Create the Trello card
        try:
            import httpx

            # Get TODO list ID
            todo_list_id = os.getenv('TRELLO_LIST_TODO')
            trello_key = os.getenv('TRELLO_API_KEY')
            trello_token = os.getenv('TRELLO_TOKEN')

            async with httpx.AsyncClient() as client:
                # Create card
                response = await client.post(
                    f"https://api.trello.com/1/cards",
                    params={
                        "key": trello_key,
                        "token": trello_token,
                        "idList": todo_list_id,
                        "name": title,
                        "desc": description
                    }
                )
                card = response.json()
                card_id = card['id']

                # Add P1 label (high priority)
                await client.post(
                    f"https://api.trello.com/1/cards/{card_id}/labels",
                    params={
                        "key": trello_key,
                        "token": trello_token,
                        "color": "orange",
                        "name": "P1"
                    }
                )

                # Add metadata to card for tracking
                metadata = {
                    "pr_number": str(pr_number),
                    "commit_hash": commit_hash or "",
                    "fix_type": "review_feedback",
                    "category": category
                }

                await client.put(
                    f"https://api.trello.com/1/cards/{card_id}",
                    params={
                        "key": trello_key,
                        "token": trello_token,
                    },
                    json={"name": title}  # Trello doesn't have custom metadata field
                )

                self.logger.logger.info(
                    "Created fix task",
                    card_id=card_id[:12],
                    category=category,
                    issue_count=len(issues)
                )

        except Exception as e:
            self.logger.logger.error("Failed to create fix task", error=str(e))

    async def _manage_pr_lifecycle(
        self,
        pr_number: int,
        review_result: AgentResult,
        project_name: str
    ):
        """Manage PR lifecycle based on review results."""

        try:
            # Get PR details
            import httpx
            from dotenv import load_dotenv
            load_dotenv('/home/ubuntu/.env')

            github_token = os.getenv('GITHUB_TOKEN')

            async with httpx.AsyncClient() as client:
                # Get PR state
                response = await client.get(
                    f"https://api.github.com/repos/TheCurators/{project_name}/pulls/{pr_number}",
                    headers={"Authorization": f"token {github_token}"}
                )
                pr_data = response.json()
                pr_state = pr_data.get('state', 'open')

                if pr_state != 'open':
                    self.logger.logger.info("PR not open", pr_number=pr_number, state=pr_state)
                    return

                if review_result.is_success():
                    # Approve the PR
                    await self._approve_pr(pr_number, project_name)
                    self.logger.logger.info("PR approved", pr_number=pr_number)
                else:
                    # Request changes
                    await self._request_changes(pr_number, project_name, review_result.errors)
                    self.logger.logger.info("Changes requested", pr_number=pr_number)

        except Exception as e:
            self.logger.logger.error("Failed to manage PR lifecycle", error=str(e))

    async def _approve_pr(self, pr_number: int, project_name: str):
        """Approve a PR via GitHub API."""
        import subprocess

        try:
            # Use gh CLI to approve PR
            subprocess.run(
                ["gh", "pr", "review", str(pr_number), "--approve", "-b", "LGTM", "-R", f"TheCurators/{project_name}"],
                capture_output=True,
                check=True,
                timeout=30
            )
            self.logger.logger.info("Approved PR", pr_number=pr_number)
        except subprocess.CalledProcessError as e:
            self.logger.logger.error("Failed to approve PR", error=e.stderr)

    async def _request_changes(self, pr_number: int, project_name: str, errors: List[str]):
        """Request changes on a PR with specific feedback."""
        import subprocess

        # Build review comment
        comment = "## Review Feedback\n\nChanges requested. Please address the following issues:\n\n"

        for i, error in enumerate(errors, 1):
            comment += f"{i}. {error}\n"

        comment += "\nFix tasks have been created in Trello. Once fixes are committed, a new PR will be created and this PR will be closed."

        try:
            # Use gh CLI to request changes
            subprocess.run(
                ["gh", "pr", "review", str(pr_number), "--request-changes", "-b", comment, "-R", f"TheCurators/{project_name}"],
                capture_output=True,
                check=True,
                timeout=30
            )
            self.logger.logger.info("Requested changes", pr_number=pr_number)
        except subprocess.CalledProcessError as e:
            self.logger.logger.error("Failed to request changes", error=e.stderr)


def get_enhanced_review_agent() -> EnhancedReviewAgent:
    """Get singleton instance of enhanced review agent."""
    from agents.base.base_agent import AgentConfig

    config = AgentConfig(
        name="enhanced_review_agent",
        description="Enhanced review agent with Trello feedback loop",
        model="claude-sonnet-4-5-20250929"
    )

    return EnhancedReviewAgent(config)
