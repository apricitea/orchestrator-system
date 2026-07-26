"""
PR Review Agent - Technical Code Expert for Pull Request Reviews

This agent automatically reviews pull requests for:
- Code quality and best practices
- Security vulnerabilities
- Performance issues
- Test coverage
- Documentation completeness
"""

import re
import subprocess
from pathlib import Path
from typing import List, Optional

from anthropic import AsyncAnthropic
from config.settings import get_settings
from utils.logger import get_logger

logger = get_logger("pr_review_agent")


class PRReviewAgent:
    """
    Technical code expert agent that reviews pull requests.

    Analyzes code changes and provides comprehensive feedback on:
    - Code quality and style
    - Security issues
    - Performance concerns
    - Testing coverage
    - Documentation
    """

    def __init__(self):
        self.settings = get_settings()
        self.client = AsyncAnthropic(api_key=self.settings.anthropic_api_key)

    async def review_pr(
        self,
        repo_path: str,
        pr_number: int,
        branch_name: str,
        base_branch: str = "main",
    ) -> dict:
        """
        Review a pull request comprehensively.

        Args:
            repo_path: Path to the repository
            pr_number: Pull request number
            branch_name: Feature branch name
            base_branch: Base branch (default: main)

        Returns:
            Review results with approval status and feedback
        """
        try:
            # Get PR diff
            diff = await self._get_pr_diff(repo_path, base_branch, branch_name)

            if not diff:
                return {
                    "status": "error",
                    "message": "Could not get PR diff",
                }

            # Get changed files
            changed_files = await self._get_changed_files(repo_path, base_branch, branch_name)

            # Analyze with Claude
            review = await self._analyze_with_claude(diff, changed_files, repo_path)

            # Run automated checks
            automated_checks = await self._run_automated_checks(repo_path, changed_files)

            # Combine results
            final_review = self._combine_reviews(review, automated_checks)

            return final_review

        except Exception as e:
            logger.error("PR review failed", error=str(e))
            return {
                "status": "error",
                "message": f"Review failed: {str(e)}",
            }

    async def _get_pr_diff(
        self, repo_path: str, base_branch: str, branch_name: str
    ) -> str:
        """Get the diff for the PR."""
        try:
            result = subprocess.run(
                ["git", "diff", f"{base_branch}...{branch_name}"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout
        except Exception as e:
            logger.error("Failed to get diff", error=str(e))
            return ""

    async def _get_changed_files(
        self, repo_path: str, base_branch: str, branch_name: str
    ) -> List[str]:
        """Get list of changed files."""
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", f"{base_branch}...{branch_name}"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip().split("\n")
        except Exception as e:
            logger.error("Failed to get changed files", error=str(e))
            return []

    async def _analyze_with_claude(
        self, diff: str, changed_files: List[str], repo_path: str
    ) -> dict:
        """Analyze the PR using Claude AI."""
        # Limit diff size to avoid token limits
        diff_preview = diff[:10000] if len(diff) > 10000 else diff

        prompt = f"""You are a senior code reviewer conducting a technical PR review.

Repository path: {repo_path}

Changed files ({len(changed_files)}):
{chr(10).join(changed_files[:20])}

Diff (first 10k chars):
{diff_preview}

{'Diff truncated due to size...' if len(diff) > 10000 else ''}

Please review this pull request and provide feedback in the following JSON format:

{{
    "overall_score": <1-10>,
    "approval_status": <"approved"|"request_changes"|"comment">,
    "summary": "<brief summary of changes>",
    "strengths": ["<strength 1>", "<strength 2>"],
    "issues": [
        {{
            "severity": <"critical"|"high"|"medium"|"low">,
            "category": <"security"|"performance"|"code_quality"|"testing"|"documentation"|"best_practice">,
            "file": "<file path>",
            "line": "<line number or description>",
            "description": "<issue description>",
            "suggestion": "<how to fix>"
        }}
    ],
    "security_concerns": ["<any security issues found>"],
    "performance_notes": ["<any performance concerns>"],
    "testing_feedback": "<feedback on test coverage>",
    "documentation_feedback": "<feedback on documentation>"
}}

Focus on:
1. **Security**: SQL injection, XSS, auth issues, sensitive data exposure
2. **Code Quality**: Clean code principles, maintainability, naming
3. **Performance**: N+1 queries, inefficient algorithms, memory leaks
4. **Testing**: Test coverage, edge cases, mocking
5. **Documentation**: Code comments, API docs, README updates

Be thorough but constructive. If code is excellent, approve with praise."""

        try:
            response = await self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4000,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = response.content[0].text

            # Extract JSON from response
            json_match = re.search(r"\{[\s\S]*\}", response_text)
            if json_match:
                import json
                try:
                    review_data = json.loads(json_match.group())
                    return review_data
                except json.JSONDecodeError:
                    logger.warning("Failed to parse Claude response as JSON")

            # Fallback if JSON parsing fails
            return {
                "status": "completed",
                "raw_response": response_text,
                "approval_status": "comment",
            }

        except Exception as e:
            logger.error("Claude analysis failed", error=str(e))
            return {
                "status": "error",
                "message": f"Claude analysis failed: {str(e)}",
            }

    async def _run_automated_checks(
        self, repo_path: str, changed_files: List[str]
    ) -> dict:
        """Run automated checks on the code."""
        checks = {
            "has_tests": False,
            "test_files": [],
            "has_migration": False,
            "has_env_changes": False,
            "large_files": [],
            "security_keywords": [],
        }

        for file_path in changed_files:
            full_path = Path(repo_path) / file_path

            # Check for test files
            if "test" in file_path.lower() or "spec" in file_path.lower():
                checks["test_files"].append(file_path)
                checks["has_tests"] = True

            # Check for database migrations
            if "migration" in file_path.lower():
                checks["has_migration"] = True

            # Check for env file changes
            if ".env" in file_path or "config" in file_path.lower():
                checks["has_env_changes"] = True

            # Check file sizes
            if full_path.exists():
                size_kb = full_path.stat().st_size / 1024
                if size_kb > 500:  # Larger than 500KB
                    checks["large_files"].append(f"{file_path} ({size_kb:.0f}KB)")

                # Check for security keywords in code
                if full_path.suffix in [".py", ".js", ".ts", ".tsx", ".jsx"]:
                    try:
                        content = full_path.read_text()[:5000]  # Check first 5KB
                        security_keywords = [
                            "password",
                            "secret",
                            "api_key",
                            "token",
                            "private_key",
                            "credentials",
                        ]
                        for keyword in security_keywords:
                            if keyword in content.lower():
                                checks["security_keywords"].append(
                                    f"{keyword} found in {file_path}"
                                )
                                break  # Only note each file once
                    except Exception:
                        pass

        return checks

    def _combine_reviews(self, claude_review: dict, automated_checks: dict) -> dict:
        """Combine Claude review with automated checks."""
        if "raw_response" in claude_review:
            # Fallback format
            return {
                "status": "completed",
                "approval_status": "comment",
                "claude_review": claude_review["raw_response"],
                "automated_checks": automated_checks,
            }

        # Determine final approval status
        approval = claude_review.get("approval_status", "comment")

        # Downgrade approval if critical automated issues found
        if automated_checks["security_keywords"] and approval == "approved":
            approval = "request_changes"

        return {
            "status": "completed",
            "approval_status": approval,
            "overall_score": claude_review.get("overall_score", 0),
            "summary": claude_review.get("summary", ""),
            "strengths": claude_review.get("strengths", []),
            "issues": claude_review.get("issues", []),
            "security_concerns": claude_review.get("security_concerns", [])
            + automated_checks["security_keywords"],
            "performance_notes": claude_review.get("performance_notes", []),
            "testing_feedback": claude_review.get("testing_feedback", ""),
            "documentation_feedback": claude_review.get("documentation_feedback", ""),
            "automated_checks": automated_checks,
        }

    async def post_review_comment(
        self,
        repo_path: str,
        pr_number: int,
        review: dict,
    ) -> bool:
        """Post the review as a comment on the PR."""
        try:
            # Format review comment
            comment = self._format_review_comment(pr_number, review)

            # Post using gh CLI
            result = subprocess.run(
                ["gh", "pr", "comment", str(pr_number), "--body", comment],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                logger.info("Posted review comment", pr_number=pr_number)
                return True
            else:
                logger.error(
                    "Failed to post review",
                    error=result.stderr,
                )
                return False

        except Exception as e:
            logger.error("Failed to post review comment", error=str(e))
            return False

    def _format_review_comment(self, pr_number: int, review: dict) -> str:
        """Format the review as a markdown comment."""
        status_emoji = {
            "approved": "✅",
            "request_changes": "🔄",
            "comment": "💬",
        }

        approval = review.get("approval_status", "comment")
        emoji = status_emoji.get(approval, "💬")

        comment = f"""# PR Review #{pr_number} {emoji}

**Overall Score:** {review.get('overall_score', 'N/A')}/10
**Status:** {approval.upper()}

## Summary
{review.get('summary', 'No summary provided.')}

## Strengths
{chr(10).join(f'- {s}' for s in review.get('strengths', []))}

## Issues Found
"""

        issues = review.get("issues", [])
        if issues:
            for issue in issues:
                severity_emoji = {
                    "critical": "🔴",
                    "high": "🟠",
                    "medium": "🟡",
                    "low": "🟢",
                }
                emoji = severity_emoji.get(issue.get("severity", "low"), "🟢")
                comment += f"\n{emoji} **{issue.get('category', 'Other')}** - {issue.get('severity', 'low').upper()}\n"
                comment += f"   - **File:** `{issue.get('file', 'unknown')}`\n"
                comment += f"   - **Issue:** {issue.get('description', 'No description')}\n"
                if issue.get('suggestion'):
                    comment += f"   - **Suggestion:** {issue.get('suggestion')}\n"
        else:
            comment += "\n✨ No issues found!"

        comment += f"""

## Security
{chr(10).join(f'- {s}' for s in review.get('security_concerns', [])) or '✅ No security concerns'}

## Performance
{chr(10).join(f'- {p}' for p in review.get('performance_notes', [])) or '✅ No performance issues'}

## Testing
{review.get('testing_feedback', 'No testing feedback provided.')}

## Documentation
{review.get('documentation_feedback', 'No documentation feedback provided.')}

## Automated Checks
- **Test Files:** {len(review.get('automated_checks', {}).get('test_files', []))} found
- **Migrations:** {'Yes' if review.get('automated_checks', {}).get('has_migration') else 'None'}
- **Config Changes:** {'Yes ⚠️' if review.get('automated_checks', {}).get('has_env_changes') else 'None'}
- **Large Files:** {len(review.get('automated_checks', {}).get('large_files', []))} files >500KB

---
🤖 *This review was generated by the AI PR Review Agent*
"""

        return comment


# Global instance
_pr_review_agent: Optional[PRReviewAgent] = None


def get_pr_review_agent() -> PRReviewAgent:
    """Get the global PR review agent instance."""
    global _pr_review_agent
    if _pr_review_agent is None:
        _pr_review_agent = PRReviewAgent()
    return _pr_review_agent
