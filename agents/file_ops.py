"""
File Operations Tools

Provides safe file system operations for agents to use.
All operations respect the sandbox security boundaries.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from sandbox.filesystem.jail import FilesystemJail, get_filesystem_jail
from utils.logger import get_logger


class FileOpsTool:
    """
    Tool for safe file operations.

    Provides methods for reading, writing, and manipulating files
    within the security boundaries of the sandbox.
    """

    def __init__(self, jail: Optional[FilesystemJail] = None):
        """Initialize file operations tool."""
        self.jail = jail or get_filesystem_jail()
        self.logger = get_logger("file_ops_tool")

    async def read_file(self, path: str) -> Dict[str, Any]:
        """
        Read a file safely.

        Args:
            path: File path to read

        Returns:
            Dict with success status and content
        """
        self.logger.info("Reading file", path=path)

        content = self.jail.safe_read(path)

        if content is None:
            return {
                "success": False,
                "error": f"Cannot read file: {path}",
                "path": path,
            }

        return {
            "success": True,
            "content": content,
            "path": path,
            "line_count": content.count('\n') + 1,
            "char_count": len(content),
        }

    async def write_file(
        self,
        path: str,
        content: str,
        create_dirs: bool = True,
    ) -> Dict[str, Any]:
        """
        Write content to a file safely.

        Args:
            path: File path to write
            content: Content to write
            create_dirs: Create parent directories if needed

        Returns:
            Dict with success status
        """
        self.logger.info("Writing file", path=path, size=len(content))

        if create_dirs:
            Path(path).parent.mkdir(parents=True, exist_ok=True)

        success = self.jail.safe_write(path, content)

        if not success:
            return {
                "success": False,
                "error": f"Cannot write file: {path}",
                "path": path,
            }

        return {
            "success": True,
            "path": path,
            "bytes_written": len(content),
        }

    async def delete_file(self, path: str) -> Dict[str, Any]:
        """
        Delete a file safely.

        Args:
            path: File path to delete

        Returns:
            Dict with success status
        """
        self.logger.info("Deleting file", path=path)

        success = self.jail.safe_delete(path)

        if not success:
            return {
                "success": False,
                "error": f"Cannot delete file: {path}",
                "path": path,
            }

        return {
            "success": True,
            "path": path,
        }

    async def list_files(
        self,
        directory: str,
        pattern: str = "*",
    ) -> Dict[str, Any]:
        """
        List files in a directory.

        Args:
            directory: Directory path
            pattern: Glob pattern for filtering

        Returns:
            Dict with success status and file list
        """
        self.logger.info("Listing files", directory=directory, pattern=pattern)

        if not self.jail.is_allowed(directory):
            return {
                "success": False,
                "error": f"Directory not allowed: {directory}",
                "files": [],
            }

        try:
            path = Path(directory)
            if not path.exists():
                return {
                    "success": False,
                    "error": f"Directory does not exist: {directory}",
                    "files": [],
                }

            files = []
            for item in sorted(path.glob(pattern)):
                if item.is_file():
                    files.append({
                        "name": item.name,
                        "path": str(item),
                        "size": item.stat().st_size,
                        "is_file": True,
                    })
                elif item.is_dir():
                    files.append({
                        "name": item.name,
                        "path": str(item),
                        "is_dir": True,
                    })

            return {
                "success": True,
                "directory": directory,
                "files": files,
                "count": len(files),
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "files": [],
            }

    async def file_exists(self, path: str) -> Dict[str, Any]:
        """
        Check if a file exists.

        Args:
            path: File path to check

        Returns:
            Dict with success status and existence
        """
        try:
            exists = Path(path).exists()

            return {
                "success": True,
                "exists": exists,
                "path": path,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "exists": False,
            }

    async def create_directory(
        self,
        path: str,
        parents: bool = True,
    ) -> Dict[str, Any]:
        """
        Create a directory.

        Args:
            path: Directory path to create
            parents: Create parent directories

        Returns:
            Dict with success status
        """
        self.logger.info("Creating directory", path=path)

        try:
            Path(path).mkdir(parents=parents, exist_ok=True)

            return {
                "success": True,
                "path": path,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "path": path,
            }

    async def append_file(
        self,
        path: str,
        content: str,
    ) -> Dict[str, Any]:
        """
        Append content to a file.

        Args:
            path: File path
            content: Content to append

        Returns:
            Dict with success status
        """
        self.logger.info("Appending to file", path=path)

        allowed, error = self.jail.validate_operation("write", path)
        if not allowed:
            return {
                "success": False,
                "error": error,
                "path": path,
            }

        try:
            with open(path, "a") as f:
                f.write(content)

            return {
                "success": True,
                "path": path,
                "bytes_appended": len(content),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "path": path,
            }

    async def move_file(
        self,
        source: str,
        destination: str,
    ) -> Dict[str, Any]:
        """
        Move a file.

        Args:
            source: Source path
            destination: Destination path

        Returns:
            Dict with success status
        """
        self.logger.info("Moving file", source=source, destination=destination)

        allowed_src, error_src = self.jail.validate_operation("read", source)
        allowed_dst, error_dst = self.jail.validate_operation("write", destination)

        if not allowed_src or not allowed_dst:
            return {
                "success": False,
                "error": error_src or error_dst,
            }

        try:
            Path(source).rename(destination)

            return {
                "success": True,
                "source": source,
                "destination": destination,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    async def search_files(
        self,
        directory: str,
        search_term: str,
        file_pattern: str = "*.py",
    ) -> Dict[str, Any]:
        """
        Search for files containing a term.

        Args:
            directory: Directory to search
            search_term: Term to search for
            file_pattern: File pattern to match

        Returns:
            Dict with search results
        """
        self.logger.info(
            "Searching files",
            directory=directory,
            term=search_term,
            pattern=file_pattern,
        )

        if not self.jail.is_allowed(directory):
            return {
                "success": False,
                "error": f"Directory not allowed: {directory}",
                "results": [],
            }

        try:
            results = []
            path = Path(directory)

            for file_path in path.rglob(file_pattern):
                if not self.jail.is_allowed(str(file_path)):
                    continue

                try:
                    content = file_path.read_text()
                    if search_term.lower() in content.lower():
                        results.append({
                            "path": str(file_path),
                            "relative_path": str(file_path.relative_to(path)),
                            "matches": content.lower().count(search_term.lower()),
                        })
                except Exception:
                    continue

            return {
                "success": True,
                "search_term": search_term,
                "directory": directory,
                "results": results,
                "count": len(results),
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "results": [],
            }
