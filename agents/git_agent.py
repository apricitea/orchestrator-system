"""
Git Agent - LLM-Powered with Full Automation

Specialized agent for Git operations and workflow automation using the GitWorkflow class.
Implements feature branch workflow with conventional commits.
"""

import re
import subprocess
import time
from typing import Any, Dict, List, Optional

from agents.base.base_agent import AgentConfig, AgentResult, BaseAgent
from agents.tools.tool_registry import get_tool_registry
from automation.git import GitBranchType
from models.llm.llm_wrapper import get_llm_wrapper
from utils.logger import AgentLogger


class GitAgent(BaseAgent):
    """
    Agent specialized in Git operations with full automation.

    Capabilities:
    - Feature branch workflow
    - Conventional commits
    - Pull request creation
    - Automated merging
    - Branch management
    - Conflict detection

    Note: Uses direct subprocess calls to git commands to avoid module caching issues
    in long-running daemon processes.
    """

    def __init__(self, config: AgentConfig):
        """Initialize git agent."""
        super().__init__(config)
        self.llm = get_llm_wrapper()
        self.tools = get_tool_registry()
        self._working_dir = "."
        self.logger.logger.info("Git agent initialized with subprocess-based automation")

    def _sanitize_branch_name(self, name: str) -> str:
        """
        Sanitize branch name by removing invalid characters and common stop words.

        Git branch names must:
        - Not contain spaces (use hyphens instead)
        - Not contain special characters (only alphanumeric, hyphens, underscores allowed)
        - Not start or end with hyphen
        - Not contain consecutive hyphens
        - Not be empty

        Preserves branch type prefixes if present (feature/, bugfix/, hotfix/, etc.)

        Args:
            name: Raw branch name

        Returns:
            Sanitized branch name
        """
        import re

        # Common stop words to remove from branch names
        stop_words = {
            "a", "an", "the", "for", "to", "in", "on", "at", "by", "with",
            "from", "of", "and", "or", "but", "is", "are", "was", "were"
        }

        # Branch type prefixes to preserve
        branch_types = {"feature", "bugfix", "hotfix", "refactor", "docs", "test", "perf"}

        # Convert to lowercase
        name = name.lower().strip()

        # Check if name starts with a known branch type prefix
        prefix = None
        for bt in branch_types:
            if name.startswith(f"{bt}/"):
                prefix = f"{bt}/"
                # Remove prefix for sanitization, will add back later
                name = name[len(f"{bt}/"):]
                break

        # Replace spaces and underscores with hyphens
        name = re.sub(r'[\s_]+', '-', name)

        # Remove all characters except alphanumeric and hyphens
        name = re.sub(r'[^a-z0-9-]', '', name)

        # Split into words and filter out stop words
        words = [w for w in name.split('-') if w and w not in stop_words]

        # Rejoin with hyphens
        name = '-'.join(words)

        # Remove consecutive hyphens
        name = re.sub(r'-+', '-', name)

        # Remove leading/trailing hyphens
        name = name.strip('-')

        # Limit length (git has a practical limit around 255 chars)
        if len(name) > 200:
            # Keep first 100 chars and last 100 chars
            name = name[:100] + '-' + name[-100:] if len(name) > 200 else name

        # Ensure we have at least something
        if not name:
            name = "branch"

        # Add back the prefix if it was present
        if prefix:
            name = f"{prefix}{name}"

        return name

    def _extract_working_directory(self, task: str) -> Optional[str]:
        """
        Extract working directory from task description.

        Args:
            task: Task description that may contain working directory

        Returns:
            Working directory path or None
        """
        # Look for patterns like:
        # "Working Directory: /path/to/dir"
        # "## Working Directory\n/home/ubuntu/path"
        # "Working Directory:\n/home/ubuntu/path"
        patterns = [
            r'(?:Current )?Working Directory:\s*(.+?)(?:\n|$)',  # "Working Directory: /path"
            r'##\s*Working Directory\s*\n\s*(.+?)(?:\n|$)',      # "## Working Directory\n/path"
        ]

        for pattern in patterns:
            match = re.search(pattern, task, re.IGNORECASE)
            if match:
                path = match.group(1).strip()
                # Clean up common markdown formatting
                path = re.sub(r'^[`\'"]*|[`\'"]*$', '', path)  # Remove quotes/backticks
                self.logger.logger.info("Extracted working directory from task", path=path)
                return path

        return None

    def _get_default_branch(self, working_dir: str, feature_branch: Optional[str] = None) -> str:
        """
        Detect the default branch for PR target.

        Args:
            working_dir: Working directory of the git repository
            feature_branch: Feature branch name (optional, for better detection)

        Returns:
            Default branch name (main, master, develop, etc.)
        """
        try:
            # If feature branch is provided, try to determine what it was based on
            if feature_branch:
                # Method 1: Check the merge-base to find common ancestor
                try:
                    for candidate in ["main", "master", "develop"]:
                        # Check if this branch exists on remote
                        result = subprocess.run(
                            ["git", "branch", "-r"],
                            capture_output=True,
                            text=True,
                            cwd=working_dir,
                            check=False
                        )
                        if f"origin/{candidate}" in result.stdout:
                            # Check if feature branch has commits from this candidate
                            merge_base_result = subprocess.run(
                                ["git", "merge-base", f"origin/{candidate}", feature_branch],
                                capture_output=True,
                                text=True,
                                cwd=working_dir,
                                check=False
                            )
                            if merge_base_result.returncode == 0:
                                self.logger.logger.info(
                                    "Detected base branch from merge-base",
                                    feature=feature_branch,
                                    base=candidate
                                )
                                return candidate
                except Exception as e:
                    self.logger.logger.debug("Could not detect via merge-base", error=str(e))

            # Method 2: Check remote branches and prioritize develop if it exists
            result = subprocess.run(
                ["git", "branch", "-r"],
                capture_output=True,
                text=True,
                cwd=working_dir,
                check=False
            )
            if "origin/develop" in result.stdout or "remotes/origin/develop" in result.stdout:
                self.logger.logger.info("Detected base branch via remote check", branch="develop")
                return "develop"
            elif "origin/main" in result.stdout or "remotes/origin/main" in result.stdout:
                self.logger.logger.info("Detected base branch via remote check", branch="main")
                return "main"
            elif "origin/master" in result.stdout or "remotes/origin/master" in result.stdout:
                self.logger.logger.info("Detected base branch via remote check", branch="master")
                return "master"

            # Method 3: Use git symbolic-ref to get HEAD
            result = subprocess.run(
                ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
                capture_output=True,
                text=True,
                cwd=working_dir,
                check=False
            )
            if result.returncode == 0:
                default_ref = result.stdout.strip()
                default_branch = default_ref.split("/")[-1]
                self.logger.logger.info("Detected default branch via symbolic-ref", branch=default_branch)
                return default_branch

            # Fallback
            self.logger.logger.info("Could not detect default branch, using 'main'")
            return "main"

        except Exception as e:
            self.logger.logger.warning("Error detecting default branch, using 'main'", error=str(e))
            return "main"

    async def execute(self, task: str, **kwargs: Any) -> AgentResult:
        """
        Execute a git task.

        Args:
            task: Task description
            **kwargs: Additional parameters

        Returns:
            Agent result
        """
        start_time = time.time()

        self.logger.logger.info("Executing git task", task=task)

        # Extract working directory from task and store for git operations
        self._working_dir = kwargs.get("working_directory") or self._extract_working_directory(task) or "."
        self.logger.logger.info("Working directory for git operations", path=self._working_dir)

        # Parse task and route to appropriate method
        task_lower = task.lower()

        try:
            self.logger.logger.info("Git execute: starting task routing", task_lower=task_lower[:50])

            if "status" in task_lower:
                self.logger.logger.info("Git execute: routing to _get_status")
                return await self._get_status()

            # Check for PR creation FIRST (before "create branch") to avoid misrouting
            elif ("pr" in task_lower or "pull request" in task_lower) and "create" in task_lower:
                title = kwargs.get("title")
                description = kwargs.get("description", "")
                self.logger.logger.info("Git execute: routing to _create_pr")
                # Remove title and description from kwargs to avoid "multiple values" error
                pr_kwargs = {k: v for k, v in kwargs.items() if k not in ['title', 'description']}
                return await self._create_pr(title, description, task, **pr_kwargs)

            elif ("create" in task_lower or "new" in task_lower) and "branch" in task_lower:
                branch_name = kwargs.get("branch_name")
                branch_type = kwargs.get("branch_type", GitBranchType.FEATURE)
                base_branch = kwargs.get("base_branch")
                self.logger.logger.info("Git execute: routing to _create_branch", branch_name=branch_name, branch_type=branch_type.value)
                result = await self._create_branch(branch_name, branch_type, base_branch, task)
                self.logger.logger.info("Git execute: _create_branch returned", status=result.status, has_errors=len(result.errors) if result.errors else 0)
                return result

            elif "commit" in task_lower:
                message = kwargs.get("message")
                return await self._make_commit(message, task, **kwargs)

            elif "push" in task_lower:
                branch = kwargs.get("branch")
                return await self._push(branch)

            elif ("pr" in task_lower or "pull request" in task_lower):
                # PR-related operations (view, list, etc.)
                title = kwargs.get("title")
                description = kwargs.get("description", "")
                return await self._create_pr(title, description, task, **kwargs)

            elif "merge" in task_lower:
                source = kwargs.get("source_branch")
                target = kwargs.get("target_branch", "develop")
                strategy = kwargs.get("strategy", "merge")
                return await self._merge(source, target, strategy)

            elif "branches" in task_lower:
                return await self._list_branches()

            elif "log" in task_lower or "commits" in task_lower:
                limit = kwargs.get("limit", 10)
                return await self._get_commits(limit)

            else:
                # Use LLM to determine git action
                return await self._llm_assisted_git(task, **kwargs)

        except Exception as e:
            self.logger.logger.error("Git task execution failed", error=str(e), exc_info=True)
            return AgentResult(
                status="error",
                errors=[f"Git task execution failed: {str(e)}"],
            )

    async def _get_status(self) -> AgentResult:
        """Get repository status using direct git commands."""
        import subprocess

        working_dir = getattr(self, '_working_dir', '.')

        try:
            # Get current branch
            branch_result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                cwd=working_dir,
                check=True
            )
            current_branch = branch_result.stdout.strip()

            # Get status
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                cwd=working_dir,
                check=True
            )
            status_lines = status_result.stdout.strip().split('\n') if status_result.stdout.strip() else []

            # Parse status
            modified = []
            added = []
            deleted = []
            untracked = []

            for line in status_lines:
                if not line:
                    continue
                status_code = line[:2]
                filepath = line[3:]
                if 'M' in status_code:
                    modified.append(filepath)
                if 'A' in status_code:
                    added.append(filepath)
                if 'D' in status_code:
                    deleted.append(filepath)
                if '??' in status_code:
                    untracked.append(filepath)

            has_changes = bool(modified or added or deleted or untracked)

            result = {
                "success": True,
                "current_branch": current_branch,
                "modified": modified,
                "added": added,
                "deleted": deleted,
                "untracked": untracked,
                "has_changes": has_changes,
            }

            output = f"""Current branch: {current_branch}

Modified files: {len(modified)}
Added files: {len(added)}
Deleted files: {len(deleted)}
Untracked files: {len(untracked)}

Has changes: {has_changes}"""

            if modified:
                output += f"\n\nModified:\n" + "\n".join(f"  - {f}" for f in modified[:10])

            return AgentResult(
                status="success",
                output=output,
                metadata=result,
            )

        except subprocess.CalledProcessError as e:
            return AgentResult(
                status="error",
                errors=[f"Failed to get git status: {e.stderr}"],
            )
        except Exception as e:
            return AgentResult(
                status="error",
                errors=[f"Unexpected error: {str(e)}"],
            )

    async def _create_branch(
        self,
        branch_name: Optional[str],
        branch_type: GitBranchType,
        base_branch: Optional[str],
        task: str,
    ) -> AgentResult:
        """Create a new branch using direct git commands (bypasses module caching)."""
        # Log IMMEDIATELY to confirm method is being called
        self.logger.logger.info("=== _create_branch CALLED ===", branch_name=branch_name, task=task[:50])

        import subprocess
        import os
        import re

        # Get working directory
        working_dir = self._extract_working_directory(task) or getattr(self, '_working_dir', '.')
        self.logger.logger.info("Creating branch in directory", path=working_dir, branch_type=branch_type.value, requested_name=branch_name)

        # Extract branch name from task if not provided
        # Task format: "Create feature branch 'branch-name' from main"
        if not branch_name:
            match = re.search(r"branch\s+['\"]?([^'\"]+)['\"]?", task, re.IGNORECASE)
            if match:
                branch_name = self._sanitize_branch_name(match.group(1))
                self.logger.logger.info("Extracted and sanitized branch name from task", branch_name=branch_name)

        # Use LLM to generate branch name if still not provided
        if not branch_name:
            generated_name = await self._generate_branch_name(task, branch_type)
            branch_name = self._sanitize_branch_name(generated_name)
            self.logger.logger.info("Generated and sanitized branch name", branch_name=branch_name)
        else:
            # Sanitize the provided branch name as well
            branch_name = self._sanitize_branch_name(branch_name)
            self.logger.logger.info("Sanitized provided branch name", branch_name=branch_name)

        # === FIX 1: Double-prefix prevention ===
        prefix = f"{branch_type.value}/"
        if branch_name.startswith(prefix):
            # Name already includes prefix, use as-is
            final_branch_name = branch_name
            self.logger.logger.info("Branch name already has prefix", branch_name=final_branch_name)
        else:
            # Add the prefix
            final_branch_name = f"{prefix}{branch_name}"
            self.logger.logger.info("Adding prefix to branch name", prefix=prefix, branch_name=final_branch_name)

        # === FIX 2: Intelligent base branch detection ===
        if base_branch is None:
            if branch_type == GitBranchType.HOTFIX:
                base_branch = "main"
            else:
                # Detect available base branch
                try:
                    result = subprocess.run(
                        ["git", "branch", "-r"],
                        capture_output=True,
                        text=True,
                        cwd=working_dir,
                        check=False
                    )
                    if "origin/develop" in result.stdout or "remotes/origin/develop" in result.stdout:
                        base_branch = "develop"
                    else:
                        base_branch = "main"
                    self.logger.logger.info("Detected base branch", branch=base_branch)
                except:
                    base_branch = "main"
                    self.logger.logger.info("Defaulting to main branch")

        self.logger.logger.info("Using base branch", base_branch=base_branch)

        # === Execute git operations ===
        try:
            # Checkout base branch
            self.logger.logger.info("Checking out base branch", branch=base_branch)
            subprocess.run(
                ["git", "checkout", base_branch],
                capture_output=True,
                text=True,
                cwd=working_dir,
                check=True
            )

            # Pull latest changes
            self.logger.logger.info("Pulling latest changes", branch=base_branch)
            subprocess.run(
                ["git", "pull", "origin", base_branch],
                capture_output=True,
                text=True,
                cwd=working_dir,
                check=False  # Non-fatal if pull fails
            )

            # FIX: Check if branch already exists
            existing_branch_result = subprocess.run(
                ["git", "branch", "--list", final_branch_name],
                capture_output=True,
                text=True,
                cwd=working_dir,
                check=False
            )

            if final_branch_name in existing_branch_result.stdout:
                # Branch exists, delete it to start fresh
                self.logger.logger.info("Branch already exists, deleting for fresh start", branch=final_branch_name)
                subprocess.run(
                    ["git", "branch", "-D", final_branch_name],
                    capture_output=True,
                    text=True,
                    cwd=working_dir,
                    check=False
                )

            # Create and checkout new branch
            self.logger.logger.info("Creating new branch", branch_name=final_branch_name)
            subprocess.run(
                ["git", "checkout", "-b", final_branch_name],
                capture_output=True,
                text=True,
                cwd=working_dir,
                check=True
            )

            self.logger.logger.info("Branch created successfully", branch=final_branch_name, base=base_branch)

            return AgentResult(
                status="success",
                output=f"Created branch '{final_branch_name}' from '{base_branch}'",
                metadata={
                    "branch": final_branch_name,
                    "base_branch": base_branch,
                    "branch_type": branch_type.value,
                },
                next_steps=[
                    "Make your changes",
                    "Commit changes",
                    "Push and create PR",
                ],
            )

        except subprocess.CalledProcessError as e:
            self.logger.logger.error("Failed to create branch", error=str(e), stderr=e.stderr)
            return AgentResult(
                status="error",
                errors=[f"Failed to create branch '{final_branch_name}': {e.stderr}"],
            )
        except Exception as e:
            self.logger.logger.error("Unexpected error creating branch", error=str(e))
            return AgentResult(
                status="error",
                errors=[f"Unexpected error: {str(e)}"],
            )

    async def _make_commit(
        self,
        message: Optional[str],
        task: str,
        **kwargs: Any,
    ) -> AgentResult:
        """Create a commit using direct git commands."""
        import subprocess

        working_dir = getattr(self, '_working_dir', '.')

        # Use LLM to generate commit message if not provided
        if not message:
            message = await self._generate_commit_message(task, **kwargs)

        # === CONTEXT TRACKING: Add ID prefixes to commit message ===
        from agents.automation.id_tracking import IDTrackingMixin, TaskContext, store_context

        context = IDTrackingMixin.get_context_from_kwargs(**kwargs)

        if context and any([context.trello_card_id, context.pr_number, context.is_fix_task]):
            # Format message with ID prefixes
            message = IDTrackingMixin.format_commit_message(message, context)
            self.logger.logger.info("Formatted commit with context",
                                    trello_id=context.trello_card_id[:8] if context.trello_card_id else None,
                                    pr_number=context.pr_number,
                                    is_fix=context.is_fix_task)

        add_all = kwargs.get("add_all", True)

        try:
            # Stage all changes if requested
            if add_all:
                self.logger.logger.info("Staging all changes")
                subprocess.run(
                    ["git", "add", "."],
                    capture_output=True,
                    text=True,
                    cwd=working_dir,
                    check=True
                )

            # Create commit
            self.logger.logger.info("Creating commit", message=message)
            commit_result = subprocess.run(
                ["git", "commit", "-m", message],
                capture_output=True,
                text=True,
                cwd=working_dir,
                check=True
            )

            # Get commit hash
            hash_result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                cwd=working_dir,
                check=True
            )
            short_hash = hash_result.stdout.strip()

            self.logger.logger.info("Commit created successfully", hash=short_hash, message=message)

            # === CONTEXT TRACKING: Store commit SHA in context ===
            if context:
                context.commits.append(short_hash)
                # Store updated context
                if context.task_id:
                    store_context(context.task_id, context)
                self.logger.logger.info("Stored commit in context",
                                        hash=short_hash,
                                        total_commits=len(context.commits))

            result = {
                "success": True,
                "short_hash": short_hash,
                "message": message,
            }

            return AgentResult(
                status="success",
                output=f"Committed: {short_hash} - {message}",
                metadata=result,
                next_steps=[
                    "Push to remote",
                    "Create pull request",
                ],
            )

        except subprocess.CalledProcessError as e:
            # Check if nothing to commit
            if "nothing to commit" in e.stderr.lower():
                return AgentResult(
                    status="success",
                    output="No changes to commit",
                    metadata={"success": True, "short_hash": None, "message": message},
                )
            return AgentResult(
                status="error",
                errors=[f"Failed to create commit: {e.stderr}"],
            )
        except Exception as e:
            return AgentResult(
                status="error",
                errors=[f"Unexpected error: {str(e)}"],
            )

    async def _push(self, branch: Optional[str]) -> AgentResult:
        """Push branch to remote using direct git commands."""
        import subprocess
        import os

        working_dir = getattr(self, '_working_dir', '.')

        try:
            # Get current branch if not specified
            if not branch:
                branch_result = subprocess.run(
                    ["git", "branch", "--show-current"],
                    capture_output=True,
                    text=True,
                    cwd=working_dir,
                    check=True
                )
                branch = branch_result.stdout.strip()

            self.logger.logger.info("Pushing branch", branch=branch)

            # Ensure GitHub token is available for authentication
            github_token = os.environ.get('GITHUB_TOKEN')
            env = os.environ.copy()
            if github_token:
                # Set GH_TOKEN for gh CLI commands
                env['GH_TOKEN'] = github_token
                self.logger.logger.debug("Using GitHub token for authentication")

            # Check if remote URL needs authentication
            remote_result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                cwd=working_dir,
                check=True
            )
            remote_url = remote_result.stdout.strip()

            # If remote URL is HTTPS and doesn't have token, update it
            if remote_url.startswith('https://github.com/') and '@' not in remote_url:
                if github_token:
                    # Inject token into URL
                    parts = remote_url.split('://')
                    auth_url = f"{parts[0]}//{github_token}@{parts[1]}"
                    subprocess.run(
                        ["git", "remote", "set-url", "origin", auth_url],
                        capture_output=True,
                        cwd=working_dir,
                        check=True
                    )
                    self.logger.logger.info("Updated remote URL with authentication")
                    remote_url = auth_url

            # Push to remote
            push_result = subprocess.run(
                ["git", "push", "-u", "origin", branch],
                capture_output=True,
                text=True,
                cwd=working_dir,
                env=env,
                check=True
            )

            self.logger.logger.info("Branch pushed successfully", branch=branch)

            return AgentResult(
                status="success",
                output=f"Pushed branch '{branch}' to remote",
                metadata={"branch": branch, "success": True},
                next_steps=["Create pull request"],
            )

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            self.logger.logger.error("Git push failed", error=error_msg)
            return AgentResult(
                status="error",
                errors=[f"Failed to push branch: {error_msg}"],
            )
        except Exception as e:
            return AgentResult(
                status="error",
                errors=[f"Unexpected error: {str(e)}"],
            )

    async def _create_pr(
        self,
        title: Optional[str],
        description: str,
        task: str,
        **kwargs: Any,
    ) -> AgentResult:
        """Create a pull request using gh CLI or PRManager if TaskContext provided."""
        import subprocess
        import os

        working_dir = getattr(self, '_working_dir', '.')

        # === FIX ISSUE #2: Use PRManager when TaskContext is provided ===
        task_context = kwargs.get("task_context")
        if task_context:
            try:
                from agents.github.pr_manager import get_pr_manager
                from dataclasses import dataclass

                @dataclass
                class ImplementationResult:
                    title: str = ""
                    summary: str = ""
                    test_coverage: float = 0.0

                # Get current branch
                branch_result = subprocess.run(
                    ["git", "branch", "--show-current"],
                    capture_output=True,
                    text=True,
                    cwd=working_dir,
                    check=True
                )
                source_branch = branch_result.stdout.strip()

                # Detect target branch
                target_branch = kwargs.get("target_branch")
                if not target_branch:
                    target_branch = self._get_default_branch(working_dir, source_branch)
                    self.logger.logger.info("Auto-detected target branch", branch=target_branch)

                # Prepare implementation result
                impl_result = ImplementationResult(
                    title=title or f"Feat: {task[:60]}",
                    summary=description or "Implementation complete",
                    test_coverage=0.0,
                )

                # Use PRManager for smart create/update decision
                pr_manager = get_pr_manager()
                pr_result = await pr_manager.create_or_update_pr(
                    context=task_context,
                    implementation_result=impl_result,
                    branch_name=source_branch,
                    base_branch=target_branch,
                )

                self.logger.logger.info("PRManager result",
                    number=pr_result.pr_number,
                    action=pr_result.action,
                    url=pr_result.pr_url)

                # Run PR review if enabled
                pr_review_result = None
                if kwargs.get("run_pr_review", False):
                    self.logger.logger.info("Running PR review", pr_number=pr_result.pr_number)
                    try:
                        from agents.pr_review_agent.pr_review_agent import get_pr_review_agent

                        reviewer = get_pr_review_agent()
                        review = await reviewer.review_pr(
                            repo_path=working_dir,
                            pr_number=pr_result.pr_number,
                            branch_name=source_branch,
                            base_branch=target_branch,
                        )

                        # Post review as comment
                        await reviewer.post_review_comment(
                            repo_path=working_dir,
                            pr_number=pr_result.pr_number,
                            review=review,
                        )

                        pr_review_result = review
                        self.logger.logger.info(
                            "PR review completed",
                            approval=review.get("approval_status", "unknown"),
                        )

                    except Exception as review_error:
                        self.logger.logger.warning(
                            "PR review failed, continuing",
                            error=str(review_error),
                        )

                return AgentResult(
                    status="success",
                    output=f"PR #{pr_result.pr_number} {pr_result.action}: {pr_result.pr_url}",
                    metadata={
                        "url": pr_result.pr_url,
                        "pr_url": pr_result.pr_url,
                        "pr_number": pr_result.pr_number,
                        "action": pr_result.action,
                        "source_branch": source_branch,
                        "target_branch": target_branch,
                        "success": True,
                        "pr_review": pr_review_result,
                    },
                    next_steps=[
                        "Wait for review",
                        "Address feedback",
                        "Merge when approved",
                    ],
                )

            except Exception as e:
                self.logger.logger.warning("PRManager failed, falling back to direct gh CLI", error=str(e))
                # Fall through to direct gh CLI method below

        # Load GitHub token from .env if GH_TOKEN not set
        if not os.environ.get('GH_TOKEN'):
            try:
                from pathlib import Path
                env_file = Path.home() / '.env'
                if env_file.exists():
                    with open(env_file) as f:
                        for line in f:
                            if line.startswith('GITHUB_TOKEN=') and not line.strip().startswith('#'):
                                token = line.split('=', 1)[1].strip()
                                os.environ['GH_TOKEN'] = token
                                self.logger.logger.info("Loaded GitHub token from .env")
                                break
            except Exception as e:
                self.logger.logger.debug("Could not load .env file", error=str(e))

        # Generate PR details with LLM if not provided
        if not title:
            # Use original task from context, not the subtask
            task_context = kwargs.get("task_context")
            original_task = task_context.original_task if task_context else task

            # DEBUG: Log what we're using for PR title
            self.logger.logger.info(
                "PR title generation",
                has_context=bool(task_context),
                original_task=original_task[:100] if original_task else "None",
            )

            # Extract just the core task (remove priority, labels, etc.)
            # Format: "[project] [agent] P2: Actual task description"
            if ":" in original_task:
                # Get everything after the last colon
                core_task = original_task.split(":")[-1].strip()
            else:
                core_task = original_task

            self.logger.logger.info(
                "PR title generation - using core_task",
                core_task=core_task[:100] if core_task else "None",
            )

            title, description = await self._generate_pr_details(core_task)

        source_branch = kwargs.get("source_branch")

        try:
            # Get current branch if not specified
            if not source_branch:
                branch_result = subprocess.run(
                    ["git", "branch", "--show-current"],
                    capture_output=True,
                    text=True,
                    cwd=working_dir,
                    check=True
                )
                source_branch = branch_result.stdout.strip()

            # Auto-detect target branch if not specified
            target_branch = kwargs.get("target_branch")
            if not target_branch:
                target_branch = self._get_default_branch(working_dir, source_branch)
                self.logger.logger.info("Auto-detected target branch", branch=target_branch)

            self.logger.logger.info("Creating pull request", source=source_branch, target=target_branch, title=title)

            # Ensure branch is pushed to remote first
            self.logger.logger.info("Ensuring branch is pushed to remote")

            # Prepare environment with authentication
            env = os.environ.copy()
            github_token = os.environ.get('GITHUB_TOKEN')
            if github_token:
                env['GH_TOKEN'] = github_token

            # Update remote URL with token if needed
            remote_result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                cwd=working_dir,
                check=True
            )
            remote_url = remote_result.stdout.strip()
            if remote_url.startswith('https://github.com/') and '@' not in remote_url and github_token:
                parts = remote_url.split('://')
                auth_url = f"{parts[0]}//{github_token}@{parts[1]}"
                subprocess.run(
                    ["git", "remote", "set-url", "origin", auth_url],
                    capture_output=True,
                    cwd=working_dir,
                    check=True
                )
                self.logger.logger.info("Updated remote URL with authentication for PR creation")

            push_result = subprocess.run(
                ["git", "push", "-u", "origin", source_branch],
                capture_output=True,
                text=True,
                cwd=working_dir,
                env=env,
                check=False  # Don't fail if already pushed
            )
            if push_result.returncode != 0 and "already up to date" not in push_result.stdout.lower():
                # Check if it's a non-fast-forward error (remote branch exists and is different)
                if "non-fast-forward" in push_result.stderr.lower() or "rejected" in push_result.stderr.lower():
                    self.logger.logger.info("Remote branch exists with different commits, force pushing")
                    push_result = subprocess.run(
                        ["git", "push", "-u", "origin", source_branch, "--force"],
                        capture_output=True,
                        text=True,
                        cwd=working_dir,
                        env=env,
                        check=False
                    )
                if push_result.returncode != 0:
                    self.logger.logger.warning("Branch push had issues", error=push_result.stderr)

            # Try using gh CLI
            try:
                # Prepare environment with GH_TOKEN
                env = os.environ.copy()
                pr_result = subprocess.run(
                    ["gh", "pr", "create", "--title", title, "--body", description,
                     "--base", target_branch, "--head", source_branch],
                    capture_output=True,
                    text=True,
                    cwd=working_dir,
                    env=env,
                    check=True
                )

                # Get PR URL from output
                url = pr_result.stdout.strip()

                # Verify PR actually exists by querying it
                self.logger.logger.info("Verifying PR creation", url=url)
                verify_result = subprocess.run(
                    ["gh", "pr", "view", "--json", "url,state,number"],
                    capture_output=True,
                    text=True,
                    cwd=working_dir,
                    env=env,
                    check=True
                )

                if verify_result.returncode == 0:
                    import json
                    pr_data = json.loads(verify_result.stdout)
                    verified_url = pr_data.get("url", url)
                    pr_state = pr_data.get("state", "unknown")
                    pr_number = pr_data.get("number", "unknown")

                    self.logger.logger.info("PR verified successfully",
                        url=verified_url, state=pr_state, number=pr_number)

                    # Run PR review if enabled
                    pr_review_result = None
                    if kwargs.get("run_pr_review", False):
                        self.logger.logger.info("Running PR review", pr_number=pr_number)
                        try:
                            from agents.pr_review_agent.pr_review_agent import get_pr_review_agent

                            reviewer = get_pr_review_agent()
                            review = await reviewer.review_pr(
                                repo_path=working_dir,
                                pr_number=pr_number,
                                branch_name=source_branch,
                                base_branch=target_branch,
                            )

                            # Post review as comment
                            await reviewer.post_review_comment(
                                repo_path=working_dir,
                                pr_number=pr_number,
                                review=review,
                            )

                            pr_review_result = review
                            self.logger.logger.info(
                                "PR review completed",
                                approval=review.get("approval_status", "unknown"),
                            )

                        except Exception as review_error:
                            self.logger.logger.warning(
                                "PR review failed, continuing",
                                error=str(review_error),
                            )

                    return AgentResult(
                        status="success",
                        output=f"PR #{pr_number} created: {verified_url}",
                        metadata={
                            "url": verified_url,
                            "pr_url": verified_url,  # Add both keys for compatibility
                            "pr_number": pr_number,
                            "state": pr_state,
                            "source_branch": source_branch,
                            "target_branch": target_branch,
                            "success": True,
                            "pr_review": pr_review_result,
                        },
                        next_steps=[
                            "Wait for review",
                            "Address feedback",
                            "Merge when approved",
                        ],
                    )
                else:
                    self.logger.logger.error("PR verification failed", stderr=verify_result.stderr)
                    return AgentResult(
                        status="error",
                        errors=["PR creation appeared to succeed but verification failed"],
                        metadata={"url": url, "verification_failed": True}
                    )

            except subprocess.CalledProcessError as e:
                # gh CLI might not be configured or available
                if "gh" not in e.stderr.lower() and "authenticated" not in e.stderr.lower():
                    raise

                # Return manual creation instructions
                self.logger.logger.info("gh CLI not available, returning manual instructions")

                return AgentResult(
                    status="partial",
                    output=f"""PR requires manual creation via web interface

Title: {title}
Source: {source_branch}
Target: {target_branch}

Description:
{description}

To create manually:
1. Visit: https://github.com/<your-org>/<your-repo>/compare/{target_branch}...{source_branch}
2. Click "Create pull request"
3. Use title and description above""",
                    metadata={"requires_manual": True, "source_branch": source_branch, "target_branch": target_branch, "success": True},
                    next_steps=[
                        "Follow instructions above",
                        "Wait for review",
                        "Address feedback",
                    ],
                )

        except subprocess.CalledProcessError as e:
            # Check if PR already exists
            import re
            stderr_lower = e.stderr.lower() if e.stderr else ""
            stdout_lower = e.stdout.lower() if e.stdout else ""

            if "already exists" in stderr_lower and "pull request" in stderr_lower:
                # Extract PR URL from error message
                # Example: "a pull request for branch X into branch Y already exists:\nhttps://github.com/..."
                pr_url_match = re.search(r'https://github\.com/[^/]+/[^/]+/pull/\d+', e.stderr)
                if pr_url_match:
                    existing_pr_url = pr_url_match.group(0)
                    existing_pr_number = existing_pr_url.split('/')[-1]

                    self.logger.logger.info("PR already exists, returning existing PR",
                        url=existing_pr_url, number=existing_pr_number)

                    return AgentResult(
                        status="success",
                        output=f"PR already exists: #{existing_pr_number}",
                        metadata={
                            "pr_url": existing_pr_url,
                            "url": existing_pr_url,
                            "pr_number": int(existing_pr_number),
                            "action": "reused_existing",
                            "source_branch": source_branch,
                            "target_branch": target_branch,
                        },
                        next_steps=[
                            "Review existing PR",
                            "Add new commits if needed",
                            "Request review",
                        ],
                    )

            # Other errors
            return AgentResult(
                status="error",
                errors=[f"Failed to create PR: {e.stderr}"],
            )
        except Exception as e:
            return AgentResult(
                status="error",
                errors=[f"Unexpected error: {str(e)}"],
            )

    async def _merge(
        self,
        source: Optional[str],
        target: str,
        strategy: str,
    ) -> AgentResult:
        """Merge a branch using direct git commands."""
        import subprocess

        working_dir = getattr(self, '_working_dir', '.')

        if not source:
            return AgentResult(
                status="error",
                errors=["source_branch is required for merge"],
            )

        try:
            self.logger.logger.info("Merging branch", source=source, target=target, strategy=strategy)

            # Checkout target branch
            subprocess.run(
                ["git", "checkout", target],
                capture_output=True,
                text=True,
                cwd=working_dir,
                check=True
            )

            # Pull latest changes
            subprocess.run(
                ["git", "pull", "origin", target],
                capture_output=True,
                text=True,
                cwd=working_dir,
                check=False
            )

            # Merge based on strategy
            if strategy == "squash":
                # Squash merge
                subprocess.run(
                    ["git", "merge", "--squash", source],
                    capture_output=True,
                    text=True,
                    cwd=working_dir,
                    check=True
                )
                subprocess.run(
                    ["git", "commit", "-m", f"Merged {source} into {target} (squash)"],
                    capture_output=True,
                    text=True,
                    cwd=working_dir,
                    check=True
                )
            elif strategy == "rebase":
                # Rebase merge
                subprocess.run(
                    ["git", "merge", "--rebase", source],
                    capture_output=True,
                    text=True,
                    cwd=working_dir,
                    check=True
                )
            else:
                # Default merge
                subprocess.run(
                    ["git", "merge", "--no-ff", source],
                    capture_output=True,
                    text=True,
                    cwd=working_dir,
                    check=True
                )

            # Push merged changes
            subprocess.run(
                ["git", "push", "origin", target],
                capture_output=True,
                text=True,
                cwd=working_dir,
                check=True
            )

            # Delete source branch if requested
            subprocess.run(
                ["git", "branch", "-d", source],
                capture_output=True,
                text=True,
                cwd=working_dir,
                check=False
            )

            self.logger.logger.info("Branch merged successfully", source=source, target=target)

            return AgentResult(
                status="success",
                output=f"Merged '{source}' into '{target}' using {strategy} strategy",
                metadata={"source": source, "target": target, "strategy": strategy, "success": True},
            )

        except subprocess.CalledProcessError as e:
            return AgentResult(
                status="error",
                errors=[f"Failed to merge branch: {e.stderr}"],
            )
        except Exception as e:
            return AgentResult(
                status="error",
                errors=[f"Unexpected error: {str(e)}"],
            )

    async def _list_branches(self) -> AgentResult:
        """List all branches using direct git commands."""
        import subprocess

        working_dir = getattr(self, '_working_dir', '.')

        try:
            # Get current branch
            current_result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                cwd=working_dir,
                check=True
            )
            current_branch = current_result.stdout.strip()

            # Get all branches
            branches_result = subprocess.run(
                ["git", "branch", "-a"],
                capture_output=True,
                text=True,
                cwd=working_dir,
                check=True
            )

            branches = []
            for line in branches_result.stdout.strip().split('\n'):
                if not line:
                    continue

                # Clean up the branch name
                branch_name = line.strip().replace('* ', '').strip()

                # Determine if remote
                is_remote = branch_name.startswith('remotes/')
                if is_remote:
                    branch_name = branch_name.replace('remotes/', '').replace('origin/', '')

                # Skip HEAD reference
                if 'HEAD' in branch_name:
                    continue

                branches.append({
                    "name": branch_name,
                    "is_current": branch_name == current_branch,
                    "is_remote": is_remote,
                    "branch_type": "feature" if '/' in branch_name else "main"
                })

            output = "Branches:\n\n"
            for branch in branches:
                current = " (current)" if branch["is_current"] else ""
                remote = " [remote]" if branch["is_remote"] else ""
                output += f"  {branch['name']}{current}{remote} - {branch['branch_type']}\n"

            return AgentResult(
                status="success",
                output=output,
                metadata={"branches": branches, "success": True},
            )

        except subprocess.CalledProcessError as e:
            return AgentResult(
                status="error",
                errors=[f"Failed to list branches: {e.stderr}"],
            )
        except Exception as e:
            return AgentResult(
                status="error",
                errors=[f"Unexpected error: {str(e)}"],
            )

    async def _get_commits(self, limit: int) -> AgentResult:
        """Get commit history using direct git commands."""
        import subprocess
        from datetime import datetime

        working_dir = getattr(self, '_working_dir', '.')

        try:
            # Get commit log
            result = subprocess.run(
                ["git", "log", "-n", str(limit), "--pretty=format:%H|%an|%ad|%s", "--date=short"],
                capture_output=True,
                text=True,
                cwd=working_dir,
                check=True
            )

            commits = []
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue

                parts = line.split('|')
                if len(parts) != 4:
                    continue

                full_hash, author, date_str, message = parts
                short_hash = full_hash[:7]

                commits.append({
                    "full_hash": full_hash,
                    "short_hash": short_hash,
                    "author": author,
                    "date": date_str,
                    "message": message
                })

            output = f"Recent {len(commits)} commits:\n\n"
            for commit in commits:
                output += f"  {commit['short_hash']} - {commit['author']} - {commit['date']}\n"
                output += f"    {commit['message']}\n\n"

            return AgentResult(
                status="success",
                output=output,
                metadata={"commits": commits, "success": True},
            )

        except subprocess.CalledProcessError as e:
            return AgentResult(
                status="error",
                errors=[f"Failed to get commits: {e.stderr}"],
            )
        except Exception as e:
            return AgentResult(
                status="error",
                errors=[f"Unexpected error: {str(e)}"],
            )

    async def _generate_branch_name(
        self,
        task: str,
        branch_type: GitBranchType,
    ) -> str:
        """Use LLM to generate a branch name."""
        prompt = f"""Generate a descriptive branch name for this task: {task}

Branch type: {branch_type.value}

Requirements:
- Use kebab-case (hyphens, not spaces)
- Be concise but descriptive
- Examples: feature/user-auth, bugfix/login-error, hotfix-security-patch

Return ONLY the branch name (without the {branch_type.value}/ prefix)."""

        response = await self.llm.generate(
            prompt=prompt,
            model=self.config.model,
            temperature=0.3,
            max_tokens=64,
        )

        # Clean up response
        branch_name = response.content.strip().strip("`").strip()
        # Remove prefix if LLM included it
        if branch_name.startswith(f"{branch_type.value}/"):
            branch_name = branch_name.split("/", 1)[1]

        return branch_name

    async def _generate_commit_message(self, task: str, **kwargs) -> str:
        """Use LLM to generate a commit message."""
        # First, try to extract a commit message that's already in the task (in quotes)
        import re
        quote_pattern = r"['\"]([^'\"]+)['\"]"
        matches = re.findall(quote_pattern, task)

        # If we found a quoted message that looks like a conventional commit, use it
        for match in matches:
            if re.match(r"^(feat|fix|docs|style|refactor|perf|test|chore|ci|build|revert):", match):
                self.logger.logger.info("Found pre-formatted commit message in task", message=match)
                return match

        # Use original task from context for better commit messages
        # This handles the case where the task is a subtask but we want the overall feature description
        task_context = kwargs.get("task_context")
        original_task = task_context.original_task if task_context else task

        self.logger.logger.info(
            "Commit message generation",
            has_context=bool(task_context),
            using_original=bool(task_context),
            original_task=original_task[:100] if original_task else "None",
        )

        # Extract the core task for commit message generation
        # Remove metadata like "Working Directory", "Requirements", etc.
        core_task = original_task

        # If the task contains newlines, extract just the first meaningful line or summary
        if "\n" in core_task:
            lines = core_task.split("\n")
            # Find the first line that looks like a task description
            for line in lines:
                line = line.strip()
                if line and not line.startswith("Working") and not line.startswith("Requirements"):
                    core_task = line
                    break

        # Fall back to LLM generation with the actual feature context
        prompt = f"""Generate a conventional commit message for this feature: {core_task}

Use the format: <type>: <description>

Types: feat, fix, docs, style, refactor, perf, test, chore, ci

Return ONLY the commit message (without 'git commit -m' or quotes)."""

        response = await self.llm.generate(
            prompt=prompt,
            model=self.config.model,
            temperature=0.3,
            max_tokens=128,
        )

        return response.content.strip().strip("`").strip('"').strip("'")

    async def _generate_pr_details(self, task: str) -> tuple[str, str]:
        """Use LLM to generate PR title and description."""
        prompt = f"""Generate a pull request title and description for this task: {task}

IMPORTANT: Output MUST follow this exact format (start with TITLE: immediately):

TITLE: <PR title>
DESCRIPTION: <detailed description>

The description should include:
- Summary of changes
- Motivation/context
- Testing performed
- Checklist (screenshots, docs, etc.)

Do NOT include any text before "TITLE:". Start your response with "TITLE:" directly."""

        response = await self.llm.generate(
            prompt=prompt,
            model=self.config.model,
            temperature=0.4,
            max_tokens=1024,
        )

        content = response.content

        # Parse title and description
        title = task  # Default to task as title
        description = content

        if "TITLE:" in content:
            parts = content.split("DESCRIPTION:", 1)
            if len(parts) == 2:
                # Extract title: get everything AFTER "TITLE:" in parts[0]
                # This handles meta-messages before "TITLE:"
                title_part = parts[0]
                if "TITLE:" in title_part:
                    # Get only the text after "TITLE:"
                    extracted_title = title_part.split("TITLE:", 1)[1].strip()
                    # Safety check: use extracted title only if it looks valid
                    # (not too long, doesn't contain meta-message indicators)
                    if extracted_title and len(extracted_title) < 200:
                        title = extracted_title
                    # If extracted title looks bad, keep default (task)
                else:
                    title = title_part.strip()
                description = parts[1].strip()

        return title, description

    async def _llm_assisted_git(self, task: str, **kwargs: Any) -> AgentResult:
        """Use LLM to determine and execute git action."""
        prompt = f"""Analyze this git task and determine what action to take: {task}

Available actions:
- status: Show repository status
- create_branch: Create a new branch
- commit: Commit changes
- push: Push to remote
- create_pr: Create pull request
- merge: Merge branches
- list_branches: List all branches
- get_commits: Show commit history

Determine the most appropriate action and any required parameters.
Respond in JSON format:
{{
    "action": "action_name",
    "parameters": {{
        "param1": "value1",
        "param2": "value2"
    }},
    "reasoning": "Why this action is appropriate"
}}"""

        response = await self.llm.generate(
            prompt=prompt,
            model=self.config.model,
            temperature=0.3,
            max_tokens=512,
        )

        # Parse LLM response and execute
        # For now, provide guidance
        return AgentResult(
            status="partial",
            output=f"Git task analyzed: {task}\n\nLLM Response:\n{response.content}",
            next_steps=[
                "Review suggested action",
                "Execute with appropriate parameters",
            ],
        )

    async def validate(self, result: AgentResult) -> bool:
        """Validate git result."""
        return result.is_success()


async def create_git_agent() -> GitAgent:
    """Create a git agent instance."""
    config = AgentConfig(
        name="git_agent",
        description="Git operations agent with full workflow automation",
        model="claude-haiku-4-5",
        temperature=0.3,
        max_tokens=2048,
    )

    return GitAgent(config)
