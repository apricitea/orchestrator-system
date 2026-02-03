"""
Git Utilities - Helper functions for git operations.

Includes branch cleanup, repository maintenance, and utility functions.
"""

import subprocess
from pathlib import Path
from typing import List, Optional

from utils.logger import get_logger

logger = get_logger("git_utils")


class GitUtils:
    """Utility functions for git operations."""

    @staticmethod
    def cleanup_merged_branches(
        repo_path: str,
        protect_branches: Optional[List[str]] = None,
        dry_run: bool = False,
    ) -> dict:
        """
        Clean up branches that have been merged to main/master.

        Args:
            repo_path: Path to the repository
            protect_branches: List of branch names to never delete
            dry_run: If True, only report what would be deleted

        Returns:
            Dict with cleanup results
        """
        protect_branches = protect_branches or ["main", "master", "develop", "staging"]
        repo = Path(repo_path)

        try:
            # Fetch latest from remote to sync branch status
            subprocess.run(
                ["git", "fetch", "--prune"],
                cwd=repo_path,
                capture_output=True,
                check=True,
            )

            # Get all merged branches
            result = subprocess.run(
                ["git", "branch", "--merged", "main"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )

            merged_branches = [
                b.strip().replace("*", "").strip()
                for b in result.stdout.split("\n")
                if b.strip() and not b.strip().startswith("*")
            ]

            # Filter out protected branches and current branch
            current_branch = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()

            branches_to_delete = [
                b
                for b in merged_branches
                if b not in protect_branches and b != current_branch
            ]

            results = {
                "dry_run": dry_run,
                "branches_found": len(branches_to_delete),
                "branches_deleted": 0,
                "branches_skipped": 0,
                "errors": [],
            }

            if branches_to_delete:
                logger.info(
                    "Found branches to clean up",
                    count=len(branches_to_delete),
                    branches=branches_to_delete[:10],
                )

                for branch in branches_to_delete:
                    try:
                        if dry_run:
                            logger.info("[DRY RUN] Would delete branch", branch=branch)
                            results["branches_deleted"] += 1
                        else:
                            subprocess.run(
                                ["git", "branch", "-d", branch],
                                cwd=repo_path,
                                capture_output=True,
                                text=True,
                                check=True,
                            )
                            logger.info("Deleted branch", branch=branch)
                            results["branches_deleted"] += 1
                    except subprocess.CalledProcessError as e:
                        # Branch might not be fully merged locally
                        logger.warning(
                            "Could not delete branch",
                            branch=branch,
                            error=e.stderr.strip(),
                        )
                        results["branches_skipped"] += 1

            return results

        except Exception as e:
            logger.error("Branch cleanup failed", error=str(e))
            return {
                "error": str(e),
                "branches_deleted": 0,
            }

    @staticmethod
    def cleanup_old_branches(
        repo_path: str,
        days_old: int = 30,
        protect_branches: Optional[List[str]] = None,
        dry_run: bool = False,
    ) -> dict:
        """
        Clean up branches older than specified days.

        Args:
            repo_path: Path to the repository
            days_old: Delete branches not modified in this many days
            protect_branches: List of branch names to never delete
            dry_run: If True, only report what would be deleted

        Returns:
            Dict with cleanup results
        """
        protect_branches = protect_branches or ["main", "master", "develop", "staging"]
        repo = Path(repo_path)

        try:
            # Get all branches with their last commit date
            result = subprocess.run(
                [
                    "git",
                    "for-each-ref",
                    "--sort=-committerdate",
                    "--format=%(refname:short)%00%(committerdate:unix)",
                    "refs/heads/",
                ],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )

            import time

            branches_to_delete = []
            cutoff_time = time.time() - (days_old * 24 * 60 * 60)

            for line in result.stdout.split("\n"):
                if not line:
                    continue

                try:
                    branch_name, commit_time = line.split("\x00")
                    commit_time = int(commit_time)

                    if (
                        branch_name not in protect_branches
                        and commit_time < cutoff_time
                    ):
                        branches_to_delete.append(branch_name)
                except (ValueError, IndexError):
                    continue

            results = {
                "dry_run": dry_run,
                "days_old": days_old,
                "branches_found": len(branches_to_delete),
                "branches_deleted": 0,
                "errors": [],
            }

            for branch in branches_to_delete:
                try:
                    if dry_run:
                        logger.info(
                            "[DRY RUN] Would delete old branch",
                            branch=branch,
                            days_old=days_old,
                        )
                        results["branches_deleted"] += 1
                    else:
                        subprocess.run(
                            ["git", "branch", "-D", branch],
                            cwd=repo_path,
                            capture_output=True,
                            text=True,
                            check=True,
                        )
                        logger.info("Deleted old branch", branch=branch)
                        results["branches_deleted"] += 1
                except subprocess.CalledProcessError as e:
                    results["errors"].append(f"{branch}: {e.stderr.strip()}")

            return results

        except Exception as e:
            logger.error("Old branch cleanup failed", error=str(e))
            return {
                "error": str(e),
                "branches_deleted": 0,
            }

    @staticmethod
    def get_repo_status(repo_path: str) -> dict:
        """Get repository status information."""
        try:
            # Get current branch
            current_branch = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()

            # Get total branches
            all_branches = subprocess.run(
                ["git", "branch", "-a"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            branch_count = len([b for b in all_branches.stdout.split("\n") if b.strip()])

            # Get uncommitted changes
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            has_changes = len(status.stdout.strip()) > 0

            return {
                "current_branch": current_branch,
                "branch_count": branch_count,
                "has_uncommitted_changes": has_changes,
                "repo_path": repo_path,
            }

        except Exception as e:
            logger.error("Failed to get repo status", error=str(e))
            return {"error": str(e)}
