"""
Code Diff Preview System

Generates human-readable diffs before applying changes.
Integrates with git workflow for review and confirmation.
"""

import difflib
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from utils.logger import get_logger


class DiffSeverity(str, Enum):
    """Severity level of changes."""
    LOW = "low"  # Comments, formatting
    MEDIUM = "medium"  # Logic changes, new functions
    HIGH = "high"  # Major refactors, API changes
    DESTRUCTIVE = "destructive"  # Deletions, breaking changes


class ChangeType(str, Enum):
    """Type of code change."""
    ADDITION = "addition"
    DELETION = "deletion"
    MODIFICATION = "modification"
    RENAME = "rename"
    MOVE = "move"


@dataclass
class FileChange:
    """Change information for a single file."""
    file_path: str
    change_type: ChangeType
    additions: int
    deletions: int
    old_content: str
    new_content: str
    severity: DiffSeverity


@dataclass
class DiffPreview:
    """Preview of code changes."""
    file_changes: List[FileChange]
    total_additions: int
    total_deletions: int
    total_files: int
    severity: DiffSeverity
    summary: str


@dataclass
class DiffHunk:
    """A contiguous section of changes."""
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    old_lines: List[str]
    new_lines: List[str]


class DiffPreviewGenerator:
    """
    Generate human-readable code diff previews.

    Features:
    - Unified diff format
    - Syntax highlighting detection
    - Severity assessment
    - Git integration
    - Change confirmation workflow
    """

    def __init__(self):
        self.logger = get_logger("diff_preview")

    def generate_diff(
        self,
        old_code: str,
        new_code: str,
        file_path: str = "",
    ) -> str:
        """
        Generate unified diff between two code versions.

        Args:
            old_code: Original code
            new_code: Modified code
            file_path: File path for display

        Returns:
            Unified diff string
        """
        old_lines = old_code.splitlines(keepends=True)
        new_lines = new_code.splitlines(keepends=True)

        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{file_path or 'file'}",
            tofile=f"b/{file_path or 'file'}",
            lineterm="",
        )

        return "".join(diff)

    def parse_diff(
        self,
        diff_content: str,
    ) -> Tuple[List[DiffHunk], Dict[str, int]]:
        """
        Parse a unified diff into structured hunks.

        Args:
            diff_content: Unified diff content

        Returns:
            Tuple of (hunks, stats) where stats has additions/deletions counts
        """
        hunks = []
        stats = {"additions": 0, "deletions": 0}

        lines = diff_content.split("\n")
        i = 0

        while i < len(lines):
            line = lines[i]

            # Parse hunk header: @@ -old_start,old_count +new_start,new_count @@
            if line.startswith("@@"):
                hunk_match = self._parse_hunk_header(line)
                if hunk_match:
                    old_start, old_count, new_start, new_count = hunk_match

                    old_lines = []
                    new_lines = []

                    # Collect hunk content
                    i += 1
                    while i < len(lines):
                        content_line = lines[i]

                        # End of hunk or start of new hunk
                        if content_line.startswith("@@") or (
                            content_line.startswith("+++") or
                            content_line.startswith("---") or
                            content_line.startswith("diff ")
                        ):
                            break

                        if content_line.startswith(" "):
                            # Context line
                            old_lines.append(content_line[1:])
                            new_lines.append(content_line[1:])

                        elif content_line.startswith("-"):
                            # Deletion
                            old_lines.append(content_line[1:])
                            stats["deletions"] += 1

                        elif content_line.startswith("+"):
                            # Addition
                            new_lines.append(content_line[1:])
                            stats["additions"] += 1

                        i += 1

                    hunks.append(
                        DiffHunk(
                            old_start=old_start,
                            old_count=old_count,
                            new_start=new_start,
                            new_count=new_count,
                            old_lines=old_lines,
                            new_lines=new_lines,
                        )
                    )

                    continue

            i += 1

        return hunks, stats

    def _parse_hunk_header(self, line: str) -> Optional[Tuple[int, int, int, int]]:
        """Parse hunk header line."""
        import re

        # Format: @@ -old_start,old_count +new_start,new_count @@
        match = re.match(r"^@@\s+-(\d+),?(\d+)?\s+\+(\d+),?(\d+)?\s+@@", line)
        if match:
            old_start = int(match.group(1))
            old_count = int(match.group(2)) if match.group(2) else 1
            new_start = int(match.group(3))
            new_count = int(match.group(4)) if match.group(4) else 1
            return (old_start, old_count, new_start, new_count)
        return None

    def assess_severity(
        self,
        file_change: FileChange,
    ) -> DiffSeverity:
        """
        Assess the severity of a file change.

        Args:
            file_change: File change information

        Returns:
            Severity level
        """
        # High ratio of deletions suggests destructive change
        if file_change.deletions > 0:
            ratio = file_change.additions / max(1, file_change.deletions)
            if ratio < 0.5:
                return DiffSeverity.DESTRUCTIVE

        # Large number of changes
        if file_change.additions + file_change.deletions > 100:
            return DiffSeverity.HIGH

        # Medium changes
        if file_change.additions + file_change.deletions > 20:
            return DiffSeverity.MEDIUM

        # Check for critical file types
        critical_files = [
            "__init__.py",
            "setup.py",
            "requirements.txt",
            "pyproject.toml",
            "package.json",
        ]
        if any(f in file_change.file_path for f in critical_files):
            return DiffSeverity.HIGH

        return DiffSeverity.MEDIUM

    def generate_preview(
        self,
        file_changes: Dict[str, Tuple[str, str]],  # file_path -> (old_content, new_content)
    ) -> DiffPreview:
        """
        Generate a comprehensive diff preview.

        Args:
            file_changes: Dictionary of file changes

        Returns:
            Diff preview with all changes
        """
        changes = []
        total_additions = 0
        total_deletions = 0
        max_severity = DiffSeverity.LOW

        for file_path, (old_content, new_content) in file_changes.items():
            # Generate diff
            diff = self.generate_diff(old_content, new_content, file_path)

            # Parse for stats
            hunks, stats = self.parse_diff(diff)

            # Determine change type
            if not old_content and new_content:
                change_type = ChangeType.ADDITION
            elif old_content and not new_content:
                change_type = ChangeType.DELETION
            else:
                change_type = ChangeType.MODIFICATION

            file_change = FileChange(
                file_path=file_path,
                change_type=change_type,
                additions=stats["additions"],
                deletions=stats["deletions"],
                old_content=old_content,
                new_content=new_content,
                severity=DiffSeverity.MEDIUM,  # Will be reassessed
            )

            # Assess severity
            file_change.severity = self.assess_severity(file_change)
            if self._severity_rank(file_change.severity) > self._severity_rank(max_severity):
                max_severity = file_change.severity

            changes.append(file_change)
            total_additions += stats["additions"]
            total_deletions += stats["deletions"]

        # Generate summary
        summary = self._generate_summary(changes, total_additions, total_deletions)

        return DiffPreview(
            file_changes=changes,
            total_additions=total_additions,
            total_deletions=total_deletions,
            total_files=len(changes),
            severity=max_severity,
            summary=summary,
        )

    def _severity_rank(self, severity: DiffSeverity) -> int:
        """Get numeric rank for severity comparison."""
        ranks = {
            DiffSeverity.LOW: 0,
            DiffSeverity.MEDIUM: 1,
            DiffSeverity.HIGH: 2,
            DiffSeverity.DESTRUCTIVE: 3,
        }
        return ranks.get(severity, 0)

    def _generate_summary(
        self,
        changes: List[FileChange],
        total_additions: int,
        total_deletions: int,
    ) -> str:
        """Generate a human-readable summary."""
        parts = []

        parts.append(f"Changes to {len(changes)} file(s):")
        parts.append(f"  +{total_additions} additions")
        parts.append(f"  -{total_deletions} deletions")

        # Categorize changes
        by_type = {}
        for change in changes:
            by_type.setdefault(change.change_type.value, 0)
            by_type[change.change_type.value] += 1

        parts.append("\nChange types:")
        for change_type, count in sorted(by_type.items()):
            parts.append(f"  {change_type}: {count}")

        return "\n".join(parts)

    def format_preview_text(self, preview: DiffPreview) -> str:
        """
        Format diff preview as human-readable text.

        Args:
            preview: Diff preview

        Returns:
            Formatted text
        """
        lines = []
        lines.append("=" * 80)
        lines.append("CODE DIFF PREVIEW")
        lines.append("=" * 80)
        lines.append("")
        lines.append(preview.summary)
        lines.append("")
        lines.append(f"Overall Severity: {preview.severity.upper()}")
        lines.append("")
        lines.append("-" * 80)

        for change in preview.file_changes:
            lines.append("")
            lines.append(f"File: {change.file_path}")
            lines.append(f"Type: {change.change_type.value}")
            lines.append(f"Severity: {change.severity.value}")
            lines.append(f"Changes: +{change.additions} -{change.deletions}")
            lines.append("")

            # Generate and display diff
            diff = self.generate_diff(change.old_content, change.new_content, change.file_path)
            if diff:
                lines.append(diff)
            else:
                lines.append("(no content change)")

            lines.append("-" * 80)

        lines.append("")
        lines.append("=" * 80)

        return "\n".join(lines)

    def get_git_diff(
        self,
        repo_path: str,
        staged: bool = False,
    ) -> str:
        """
        Get git diff from repository.

        Args:
            repo_path: Path to git repository
            staged: Get staged changes instead of working directory

        Returns:
            Git diff output
        """
        try:
            cmd = ["git", "diff", "--color=never"]
            if staged:
                cmd.insert(2, "--staged")

            result = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )

            return result.stdout

        except subprocess.CalledProcessError as e:
            self.logger.error("Failed to get git diff", error=str(e))
            return ""

    def apply_git_patch(
        self,
        repo_path: str,
        patch_content: str,
    ) -> bool:
        """
        Apply a git patch to the repository.

        Args:
            repo_path: Path to git repository
            patch_content: Patch content to apply

        Returns:
            True if successful
        """
        try:
            # Write patch to temp file
            patch_file = Path(repo_path) / ".claude_temp.patch"
            patch_file.write_text(patch_content)

            # Apply patch
            result = subprocess.run(
                ["git", "apply", str(patch_file)],
                cwd=repo_path,
                capture_output=True,
                text=True,
            )

            # Clean up
            patch_file.unlink()

            if result.returncode == 0:
                self.logger.info("Git patch applied successfully")
                return True
            else:
                self.logger.error(
                    "Failed to apply git patch",
                    error=result.stderr,
                )
                return False

        except Exception as e:
            self.logger.error("Failed to apply patch", error=str(e))
            return False

    def create_commit_from_preview(
        self,
        repo_path: str,
        preview: DiffPreview,
        commit_message: str,
    ) -> bool:
        """
        Create a git commit from a diff preview.

        Args:
            repo_path: Path to git repository
            preview: Diff preview
            commit_message: Commit message

        Returns:
            True if successful
        """
        try:
            # Stage all changed files
            for change in preview.file_changes:
                file_path = Path(repo_path) / change.file_path
                if file_path.exists():
                    subprocess.run(
                        ["git", "add", str(file_path)],
                        cwd=repo_path,
                        capture_output=True,
                        check=True,
                    )

            # Create commit
            result = subprocess.run(
                ["git", "commit", "-m", commit_message],
                cwd=repo_path,
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                self.logger.info(
                    "Git commit created",
                    message=commit_message,
                    files=len(preview.file_changes),
                )
                return True
            else:
                self.logger.error(
                    "Failed to create commit",
                    error=result.stderr,
                )
                return False

        except Exception as e:
            self.logger.error("Failed to create commit", error=str(e))
            return False


# Global instance
_diff_preview_generator: Optional[DiffPreviewGenerator] = None


def get_diff_preview_generator() -> DiffPreviewGenerator:
    """Get the global diff preview generator instance."""
    global _diff_preview_generator
    if _diff_preview_generator is None:
        _diff_preview_generator = DiffPreviewGenerator()
    return _diff_preview_generator
