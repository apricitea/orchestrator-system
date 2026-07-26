"""
Incremental Code Editor

Enables precise, targeted code edits instead of full file rewrites.
Uses AST-based parsing to modify specific code sections while preserving context.
"""

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Union

from utils.logger import get_logger


@dataclass
class CodeEdit:
    """Represents a targeted code edit."""
    file_path: str
    search_pattern: str  # Pattern to find the section to edit
    replacement: str  # New code to insert
    context_lines: int = 3  # Lines of context for matching


@dataclass
class EditResult:
    """Result of a code edit operation."""
    success: bool
    file_path: str
    edits_made: int
    original_code: str
    modified_code: str
    error: str = ""


class IncrementalEditor:
    """
    Performs incremental edits to code files.

    Features:
    - AST-based parsing for precise edits
    - Context-aware replacements
    - Multi-section edits
    - Preserves formatting and structure
    """

    def __init__(self):
        self.logger = get_logger("incremental_editor")

    def edit_code(self, edits: List[CodeEdit]) -> List[EditResult]:
        """
        Apply incremental edits to code files.

        Args:
            edits: List of code edits to apply

        Returns:
            List of edit results
        """
        results = []

        for edit in edits:
            try:
                result = self._apply_edit(edit)
                results.append(result)

                if result.success:
                    self.logger.info(
                        "Code edit successful",
                        file=edit.file_path,
                        edits=result.edits_made,
                    )
                else:
                    self.logger.error(
                        "Code edit failed",
                        file=edit.file_path,
                        error=result.error,
                    )

            except Exception as e:
                self.logger.error(
                    "Code edit error",
                    file=edit.file_path,
                    error=str(e),
                )
                results.append(
                    EditResult(
                        success=False,
                        file_path=edit.file_path,
                        edits_made=0,
                        original_code="",
                        modified_code="",
                        error=str(e),
                    )
                )

        return results

    def _apply_edit(self, edit: CodeEdit) -> EditResult:
        """Apply a single edit to a file."""
        file_path = Path(edit.file_path)

        if not file_path.exists():
            return EditResult(
                success=False,
                file_path=edit.file_path,
                edits_made=0,
                original_code="",
                modified_code="",
                error="File not found",
            )

        original_code = file_path.read_text()

        # Try different edit strategies
        modified_code = self._try_pattern_replace(original_code, edit)

        if modified_code == original_code:
            return EditResult(
                success=False,
                file_path=edit.file_path,
                edits_made=0,
                original_code=original_code,
                modified_code=original_code,
                error="Pattern not found or no changes made",
            )

        # Write the modified code
        file_path.write_text(modified_code)

        return EditResult(
            success=True,
            file_path=edit.file_path,
            edits_made=1,
            original_code=original_code,
            modified_code=modified_code,
        )

    def _try_pattern_replace(self, code: str, edit: CodeEdit) -> str:
        """Replace using search pattern with context."""
        lines = code.split("\n")
        search_lines = edit.search_pattern.split("\n")

        # Find the pattern with context
        for i in range(len(lines) - len(search_lines) + 1):
            match = True
            for j, search_line in enumerate(search_lines):
                # Simple pattern matching (can be enhanced)
                if search_line.strip() and search_line.strip() not in lines[i + j]:
                    match = False
                    break

            if match:
                # Found the pattern, replace it
                replacement_lines = edit.replacement.split("\n")
                new_lines = (
                    lines[:i]  # Lines before match
                    + replacement_lines  # New code
                    + lines[i + len(search_lines):]  # Lines after match
                )
                return "\n".join(new_lines)

        return code

    def insert_method(
        self,
        file_path: str,
        class_name: str,
        method_code: str,
        after_method: Optional[str] = None,
    ) -> EditResult:
        """
        Insert a method into a class.

        Args:
            file_path: Path to the file
            class_name: Name of the class
            method_code: Method code to insert
            after_method: Insert after this method (optional)

        Returns:
            Edit result
        """
        try:
            code = Path(file_path).read_text()
            tree = ast.parse(code)

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == class_name:
                    # Find the position to insert
                    insert_pos = node.end_lineno

                    lines = code.split("\n")
                    indent = "    "  # 4 spaces

                    # Add method with proper indentation
                    method_lines = [
                        indent + line if line.strip() else line
                        for line in method_code.split("\n")
                    ]

                    new_lines = (
                        lines[:insert_pos]
                        + method_lines
                        + lines[insert_pos:]
                    )

                    new_code = "\n".join(new_lines)
                    Path(file_path).write_text(new_code)

                    return EditResult(
                        success=True,
                        file_path=file_path,
                        edits_made=1,
                        original_code=code,
                        modified_code=new_code,
                    )

            return EditResult(
                success=False,
                file_path=file_path,
                edits_made=0,
                original_code=code,
                modified_code=code,
                error=f"Class {class_name} not found",
            )

        except Exception as e:
            return EditResult(
                success=False,
                file_path=file_path,
                edits_made=0,
                original_code="",
                modified_code="",
                error=str(e),
            )

    def edit_function(
        self,
        file_path: str,
        function_name: str,
        new_code: str,
    ) -> EditResult:
        """
        Edit a specific function in a file.

        Args:
            file_path: Path to the file
            function_name: Name of the function to edit
            new_code: New function code

        Returns:
            Edit result
        """
        try:
            code = Path(file_path).read_text()
            tree = ast.parse(code)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == function_name:
                    # Get function start and end
                    start_line = node.lineno - 1
                    end_line = node.end_lineno

                    lines = code.split("\n")

                    # Calculate indentation from first line
                    first_line = lines[start_line]
                    indent = len(first_line) - len(first_line.lstrip())

                    # Build new function with proper indentation
                    new_func_lines = []
                    for line in new_code.split("\n"):
                        new_func_lines.append(" " * indent + line if line.strip() else line)

                    # Replace the function
                    new_lines = (
                        lines[:start_line]
                        + new_func_lines
                        + lines[end_line:]
                    )

                    new_code = "\n".join(new_lines)
                    Path(file_path).write_text(new_code)

                    return EditResult(
                        success=True,
                        file_path=file_path,
                        edits_made=1,
                        original_code=code,
                        modified_code=new_code,
                    )

            return EditResult(
                success=False,
                file_path=file_path,
                edits_made=0,
                original_code=code,
                modified_code=code,
                error=f"Function {function_name} not found",
            )

        except Exception as e:
            return EditResult(
                success=False,
                file_path=file_path,
                edits_made=0,
                original_code="",
                modified_code="",
                error=str(e),
            )

    def add_import(
        self,
        file_path: str,
        import_statement: str,
    ) -> EditResult:
        """Add an import statement to a file."""
        try:
            code = Path(file_path).read_text()

            # Check if import already exists
            if import_statement in code:
                return EditResult(
                    success=True,
                    file_path=file_path,
                    edits_made=0,
                    original_code=code,
                    modified_code=code,
                )

            # Find the last import line
            lines = code.split("\n")
            import_index = -1

            for i, line in enumerate(lines):
                if line.strip().startswith(("import ", "from ")):
                    import_index = i

            if import_index >= 0:
                # Insert after last import
                lines.insert(import_index + 1, import_statement)
            else:
                # Insert at the beginning (after shebang/comments)
                lines.insert(0, import_statement)

            new_code = "\n".join(lines)
            Path(file_path).write_text(new_code)

            return EditResult(
                success=True,
                file_path=file_path,
                edits_made=1,
                original_code=code,
                modified_code=new_code,
            )

        except Exception as e:
            return EditResult(
                success=False,
                file_path=file_path,
                edits_made=0,
                original_code="",
                modified_code="",
                error=str(e),
            )


# Global instance
_incremental_editor: Optional[IncrementalEditor] = None


def get_incremental_editor() -> IncrementalEditor:
    """Get the global incremental editor instance."""
    global _incremental_editor
    if _incremental_editor is None:
        _incremental_editor = IncrementalEditor()
    return _incremental_editor
