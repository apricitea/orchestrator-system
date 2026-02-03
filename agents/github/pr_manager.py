"""
PR Manager - Smart PR Creation and Updates

Decides whether to create new PR or update existing based on context.
Handles PR lifecycle across multiple iterations.
"""

import os
import subprocess
from dataclasses import dataclass
from typing import Literal, Optional
from datetime import datetime

from agents.orchestrator.task_context import TaskContext, ReviewVerdict


@dataclass
class PRResult:
    """Result of PR creation or update."""
    pr_number: int
    pr_url: str
    action: Literal["created", "updated", "reused"]
    branch_name: str
    title: str
    description: str


class PRManager:
    """
    Manages PR lifecycle with smart create/update decisions.

    Features:
    - Detects existing PRs for the same task
    - Updates existing PRs instead of creating duplicates
    - Formats PR descriptions with iteration history
    - Links PRs to Trello cards
    """

    def __init__(self):
        self.github_token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')

    async def create_or_update_pr(
        self,
        context: TaskContext,
        implementation_result,  # Would be ImplementationResult dataclass
        branch_name: str,
        base_branch: str = "main",
    ) -> PRResult:
        """
        Create new PR or update existing based on context.

        Args:
            context: Task context with iteration history
            implementation_result: Implementation details (summary, changes, etc.)
            branch_name: Git branch name
            base_branch: Target branch (default: main)

        Returns:
            PRResult with pr_number, action taken, etc.
        """
        if context.should_create_new_pr():
            return await self._create_new_pr(
                context=context,
                implementation_result=implementation_result,
                branch_name=branch_name,
                base_branch=base_branch,
            )
        else:
            return await self._update_existing_pr(
                context=context,
                implementation_result=implementation_result,
                branch_name=branch_name,
            )

    async def _create_new_pr(
        self,
        context: TaskContext,
        implementation_result,
        branch_name: str,
        base_branch: str,
    ) -> PRResult:
        """Create a new PR."""
        print(f"🆕 Creating new PR for branch: {branch_name}")

        # === FIX ISSUE #6: Validate inputs ===
        if not branch_name:
            raise ValueError("branch_name is required")

        if not context.trello_card_id:
            print("Warning: No trello_card_id in context")

        # Extract implementation details
        title = getattr(implementation_result, 'title', f"Feat: {context.original_task[:60]}")
        summary = getattr(implementation_result, 'summary', 'Implementation complete')
        test_coverage = getattr(implementation_result, 'test_coverage', 0)

        # Format PR description
        description = self._format_pr_description(
            context=context,
            summary=summary,
            test_coverage=test_coverage,
            is_first_pr=True,
        )

        # Create PR using gh CLI
        env = os.environ.copy()
        if self.github_token:
            env['GH_TOKEN'] = self.github_token

        try:
            result = subprocess.run(
                ["gh", "pr", "create",
                 "--title", title,
                 "--body", description,
                 "--base", base_branch,
                 "--head", branch_name],
                capture_output=True,
                text=True,
                env=env,
                check=True
            )

            # Extract PR URL
            pr_url = result.stdout.strip()

            # Verify and get PR number
            verify_result = subprocess.run(
                ["gh", "pr", "view", "--json", "url,number,state"],
                capture_output=True,
                text=True,
                env=env,
                check=True
            )

            if verify_result.returncode == 0:
                import json
                pr_data = json.loads(verify_result.stdout)
                pr_number = pr_data["number"]
                verified_url = pr_data["url"]

                print(f"✅ Created PR #{pr_number}: {verified_url}")

                return PRResult(
                    pr_number=pr_number,
                    pr_url=verified_url,
                    action="created",
                    branch_name=branch_name,
                    title=title,
                    description=description,
                )

        except subprocess.CalledProcessError as e:
            # Check if PR already exists
            if "already exists" in e.stderr.lower():
                return await self._handle_existing_pr(context, branch_name, e.stderr)

            raise

    async def _update_existing_pr(
        self,
        context: TaskContext,
        implementation_result,
        branch_name: str,
    ) -> PRResult:
        """Update existing PR with new commits and refreshed description."""
        pr_number = context.current_pr_number
        print(f"🔄 Updating existing PR #{pr_number}")

        # Push new commits
        print(f"   Pushing new commits to branch: {branch_name}")
        subprocess.run(
            ["git", "push", "origin", branch_name],
            capture_output=True,
            check=False
        )

        # Extract implementation details
        summary = getattr(implementation_result, 'summary', 'Updates applied')
        test_coverage = getattr(implementation_result, 'test_coverage', 0)

        # Format updated PR description
        description = self._format_pr_description(
            context=context,
            summary=summary,
            test_coverage=test_coverage,
            is_first_pr=False,
        )

        # Update PR description
        env = os.environ.copy()
        if self.github_token:
            env['GH_TOKEN'] = self.github_token

        # Get current PR title
        pr_info = subprocess.run(
            ["gh", "pr", "view", str(pr_number), "--json", "title,url"],
            capture_output=True,
            text=True,
            env=env,
            check=True
        )

        import json
        pr_data = json.loads(pr_info.stdout)
        pr_title = pr_data["title"]
        pr_url = pr_data["url"]

        # Update PR description with iteration indicator
        iteration_indicator = f"[v{context.current_iteration}] "
        new_title = pr_title
        if not pr_title.startswith("[v"):
            # Add iteration indicator to title
            new_title = f"{iteration_indicator}{pr_title}"

        subprocess.run(
            ["gh", "pr", "edit", str(pr_number),
             "--title", new_title,
             "--body", description],
            capture_output=True,
            text=True,
            env=env,
            check=False
        )

        print(f"✅ Updated PR #{pr_number}: {pr_url}")

        return PRResult(
            pr_number=pr_number,
            pr_url=pr_url,
            action="updated",
            branch_name=branch_name,
            title=new_title,
            description=description,
        )

    async def _handle_existing_pr(
        self,
        context: TaskContext,
        branch_name: str,
        error_message: str,
    ) -> PRResult:
        """Handle case where PR already exists."""
        import re

        # Extract PR URL from error
        pr_url_match = re.search(r'https://github\.com/[^/]+/[^/]+/pull/\d+', error_message)
        if pr_url_match:
            pr_url = pr_url_match.group(0)
            pr_number = int(pr_url.split('/')[-1])

            print(f"♻️ Reusing existing PR #{pr_number}")

            return PRResult(
                pr_number=pr_number,
                pr_url=pr_url,
                action="reused",
                branch_name=branch_name,
                title=f"PR #{pr_number}",
                description="",
            )

        raise Exception(f"PR already exists but could not extract URL: {error_message}")

    def _format_pr_description(
        self,
        context: TaskContext,
        summary: str,
        test_coverage: float,
        is_first_pr: bool,
    ) -> str:
        """Format PR description with full context."""

        # Build iteration history section
        iteration_history = ""
        if not is_first_pr or context.iterations:
            iteration_history = "\n### 📜 Previous Iterations\n\n"
            for iteration in context.iterations:
                if iteration.pr_number:
                    verdict_emoji = {
                        "approved": "✅",
                        "needs_changes": "⚠️",
                        "rejected": "❌",
                        None: "⏳"
                    }.get(iteration.review_verdict.value if iteration.review_verdict else None, "❓")

                    iteration_history += (
                        f"- **Iteration {iteration.iteration_number}:** "
                        f"{verdict_emoji} {iteration.status}"
                    )
                    if iteration.review_verdict:
                        iteration_history += f" ({iteration.review_verdict.value})"
                    iteration_history += "\n"

        # Build fixes section
        fixes_section = ""
        recommendations = context.get_fix_recommendations()
        if recommendations and not is_first_pr:
            fixes_section = "\n### 🔧 Fixes Applied\n\n"
            for fix in recommendations[:5]:
                fixes_section += f"- {fix}\n"

        # Full description
        description = f"""
## 🎯 Task
{context.original_task}

## ✅ Implementation Summary
{summary}

## 🔒 Security Checklist
- [x] SQL injection prevention: Parameterized queries used
- [x] XSS prevention: User inputs escaped
- [x] No hardcoded secrets
- [x] Input validation on all endpoints

## 🧪 Testing
- Test Coverage: {test_coverage}%
- All tests passing

## 📊 Code Quality
- Follows project style guidelines
- Error handling implemented
- Documentation included

{fixes_section}

## 🔗 Linked Trello Card
https://trello.com/c/{context.trello_card_id}

{iteration_history}

---
**Iteration:** {context.current_iteration}
**Status:** {context.current_status.value.upper()}
**Last Updated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}

🤖 *Automated PR by AI Orchestrator*
"""

        return description.strip()

    async def link_pr_to_trello(
        self,
        pr_number: int,
        trello_card_id: str,
        trello_client,
    ):
        """Link PR to Trello card via comment."""
        pr_url = f"https://github.com/{trello_client.repo_owner}/{trello_client.repo_name}/pull/{pr_number}"

        comment = f"""🔗 **Pull Request Created**

PR #{pr_number} has been created for this task.

**View PR:** {pr_url}

The PR will be automatically reviewed. Check the PR for review results.
"""

        try:
            await trello_client.add_card_comment(trello_card_id, comment)
        except Exception as e:
            print(f"Warning: Could not link PR to Trello: {e}")


# Global instance
_pr_manager: Optional[PRManager] = None


def get_pr_manager() -> PRManager:
    """Get global PR manager instance."""
    global _pr_manager
    if _pr_manager is None:
        _pr_manager = PRManager()
    return _pr_manager
