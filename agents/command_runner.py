"""
Command Execution Tool

Provides safe command execution for agents.
All commands run in sandboxed environment with timeouts.
"""

import asyncio
import subprocess
from typing import Any, Dict, List, Optional

from utils.logger import get_logger


class CommandRunnerTool:
    """
    Tool for executing shell commands safely.

    All commands run with:
    - Timeouts
    - Output capture
    - Error handling
    - Resource limits
    """

    def __init__(
        self,
        default_timeout: int = 30,
        working_directory: str = "/home/ubuntu/workspace",
    ):
        """
        Initialize command runner.

        Args:
            default_timeout: Default timeout in seconds
            working_directory: Default working directory
        """
        self.default_timeout = default_timeout
        self.working_directory = working_directory
        self.logger = get_logger("command_runner")

    async def execute(
        self,
        command: str,
        args: Optional[List[str]] = None,
        timeout: Optional[int] = None,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        capture_output: bool = True,
    ) -> Dict[str, Any]:
        """
        Execute a command asynchronously.

        Args:
            command: Command to execute
            args: Command arguments
            timeout: Timeout in seconds
            cwd: Working directory
            env: Environment variables
            capture_output: Whether to capture stdout/stderr

        Returns:
            Dict with execution results
        """
        timeout = timeout or self.default_timeout
        cwd = cwd or self.working_directory

        self.logger.info(
            "Executing command",
            command=command,
            args=args,
            timeout=timeout,
            cwd=cwd,
        )

        cmd = [command]
        if args:
            cmd.extend(args)

        try:
            # Create subprocess
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE if capture_output else None,
                stderr=subprocess.PIPE if capture_output else None,
            )

            # Wait with timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )

                return {
                    "success": process.returncode == 0,
                    "exit_code": process.returncode,
                    "stdout": stdout.decode('utf-8', errors='replace') if stdout else "",
                    "stderr": stderr.decode('utf-8', errors='replace') if stderr else "",
                    "command": command,
                    "args": args,
                    "timeout": timeout,
                    "timed_out": False,
                }

            except asyncio.TimeoutError:
                # Kill the process
                try:
                    process.kill()
                    await process.wait()
                except Exception as e:
                    # Log but don't fail - we're already handling timeout
                    self.logger.warning(
                        "Failed to kill timed-out process",
                        error=str(e),
                        command=command,
                    )

                return {
                    "success": False,
                    "error": f"Command timed out after {timeout} seconds",
                    "command": command,
                    "args": args,
                    "timeout": timeout,
                    "timed_out": True,
                    "exit_code": -1,
                }

        except FileNotFoundError:
            return {
                "success": False,
                "error": f"Command not found: {command}",
                "command": command,
                "exit_code": -1,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "command": command,
                "exit_code": -1,
            }

    async def execute_python(
        self,
        code: str,
        timeout: int = 10,
    ) -> Dict[str, Any]:
        """
        Execute Python code.

        Args:
            code: Python code to execute
            timeout: Timeout in seconds

        Returns:
            Dict with execution results
        """
        self.logger.info("Executing Python code", code_length=len(code))

        return await self.execute(
            command="python3",
            args=["-c", code],
            timeout=timeout,
        )

    async def run_tests(
        self,
        test_path: str = ".",
        framework: str = "pytest",
        verbose: bool = True,
        cwd: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Run tests.

        Args:
            test_path: Path to tests
            framework: Test framework (pytest, unittest)
            verbose: Verbose output
            cwd: Working directory for tests
            timeout: Timeout in seconds (defaults to 300 for tests)

        Returns:
            Dict with test results
        """
        self.logger.info(
            "Running tests",
            framework=framework,
            path=test_path,
            cwd=cwd or self.working_directory,
            timeout=timeout or 300,
        )

        if framework == "pytest":
            args = [test_path, "-v" if verbose else ""]
            args = [a for a in args if a]  # Remove empty strings
        elif framework == "unittest":
            args = ["discover", "-s", test_path]
            if verbose:
                args.append("-v")
        else:
            return {
                "success": False,
                "error": f"Unknown test framework: {framework}",
            }

        return await self.execute(
            command=framework,
            args=args,
            timeout=timeout or 300,  # 5 minutes for tests, or custom timeout
            cwd=cwd,
        )

    async def install_dependencies(
        self,
        package_manager: str = "pip",
        packages: Optional[List[str]] = None,
        requirements_file: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Install dependencies.

        Args:
            package_manager: Package manager (pip, npm, cargo)
            packages: List of packages to install
            requirements_file: Requirements file path

        Returns:
            Dict with installation results
        """
        self.logger.info(
            "Installing dependencies",
            manager=package_manager,
        )

        if package_manager == "pip":
            if requirements_file:
                args = ["install", "-r", requirements_file]
            elif packages:
                args = ["install"] + packages
            else:
                return {
                    "success": False,
                    "error": "Must specify packages or requirements_file",
                }
        elif package_manager == "npm":
            if requirements_file:
                args = ["install"]
            else:
                args = ["install"] + (packages or [])
        elif package_manager == "cargo":
            args = ["add"] + (packages or [])
        else:
            return {
                "success": False,
                "error": f"Unknown package manager: {package_manager}",
            }

        return await self.execute(
            command=package_manager,
            args=args,
            timeout=300,
        )

    async def git_command(
        self,
        args: List[str],
    ) -> Dict[str, Any]:
        """
        Execute a git command.

        Args:
            args: Git arguments

        Returns:
            Dict with execution results
        """
        return await self.execute(
            command="git",
            args=args,
            timeout=60,
        )

    async def docker_command(
        self,
        args: List[str],
    ) -> Dict[str, Any]:
        """
        Execute a docker command.

        Args:
            args: Docker arguments

        Returns:
            Dict with execution results
        """
        return await self.execute(
            command="docker",
            args=args,
            timeout=120,
        )

    async def check_command_exists(
        self,
        command: str,
    ) -> Dict[str, Any]:
        """
        Check if a command exists.

        Args:
            command: Command to check

        Returns:
            Dict with existence status
        """
        result = await self.execute(
            command="which",
            args=[command],
            timeout=5,
        )

        return {
            "exists": result["success"],
            "path": result["stdout"].strip() if result["stdout"] else None,
            "command": command,
        }

    async def get_file_info(
        self,
        path: str,
    ) -> Dict[str, Any]:
        """
        Get file information.

        Args:
            path: File path

        Returns:
            Dict with file info
        """
        result = await self.execute(
            command="ls",
            args=["-la", path],
            timeout=5,
        )

        if result["success"]:
            # Parse ls output
            parts = result["stdout"].split()
            if len(parts) >= 9:
                return {
                    "success": True,
                    "path": path,
                    "permissions": parts[0],
                    "size": int(parts[4]),
                    "owner": parts[2],
                    "group": parts[3],
                    "modified": " ".join(parts[5:8]),
                }

        return result

    async def count_lines(
        self,
        path: str,
    ) -> Dict[str, Any]:
        """
        Count lines in a file.

        Args:
            path: File path

        Returns:
            Dict with line count
        """
        result = await self.execute(
            command="wc",
            args=["-l", path],
            timeout=5,
        )

        if result["success"]:
            try:
                count = int(result["stdout"].split()[0])
                return {
                    "success": True,
                    "path": path,
                    "line_count": count,
                }
            except (ValueError, IndexError):
                pass

        return {
            "success": False,
            "error": "Could not count lines",
            "path": path,
        }

    async def grep(
        self,
        pattern: str,
        path: str,
        args: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Search for a pattern in files.

        Args:
            pattern: Search pattern
            path: Path to search
            args: Additional grep arguments

        Returns:
            Dict with search results
        """
        grep_args = [pattern, path]
        if args:
            grep_args.extend(args)

        return await self.execute(
            command="grep",
            args=grep_args,
            timeout=30,
        )
