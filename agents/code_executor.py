"""
Code Executor Tool

Provides safe code execution capabilities for agents.
"""

from typing import Any, Dict, List, Optional

from sandbox.execution import CodeExecutor, ExecutionLanguage, get_code_executor
from utils.logger import get_logger


class CodeExecutorTool:
    """
    Tool for executing code in sandboxed containers.

    Provides safe execution environment for testing generated code.
    """

    def __init__(self):
        """Initialize code executor tool."""
        self.executor = get_code_executor()
        self.logger = get_logger("code_executor_tool")

    async def execute(
        self,
        code: str,
        language: str = "python",
        stdin: Optional[str] = None,
        timeout_ms: Optional[int] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Execute code in a sandboxed container.

        Args:
            code: Code to execute
            language: Programming language (python, node, bash)
            stdin: Optional stdin input
            timeout_ms: Execution timeout in milliseconds
            **kwargs: Additional parameters

        Returns:
            Result dictionary with success status and output
        """
        try:
            # Parse language
            try:
                exec_lang = ExecutionLanguage(language.lower())
            except ValueError:
                return {
                    "success": False,
                    "error": f"Unsupported language: {language}",
                    "result": None,
                }

            # Execute code
            result = await self.executor.execute(
                code=code,
                language=exec_lang,
                stdin=stdin,
                timeout_ms=timeout_ms,
            )

            return {
                "success": result.success,
                "result": result.to_dict(),
            }

        except Exception as e:
            self.logger.error("Code execution failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "result": None,
            }

    async def execute_file(
        self,
        file_path: str,
        language: str = "python",
        timeout_ms: Optional[int] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Execute a code file.

        Args:
            file_path: Path to code file
            language: Programming language
            timeout_ms: Execution timeout in milliseconds
            **kwargs: Additional parameters

        Returns:
            Result dictionary with success status and output
        """
        try:
            # Parse language
            try:
                exec_lang = ExecutionLanguage(language.lower())
            except ValueError:
                return {
                    "success": False,
                    "error": f"Unsupported language: {language}",
                    "result": None,
                }

            # Execute file
            result = await self.executor.execute_file(
                file_path=file_path,
                language=exec_lang,
                timeout_ms=timeout_ms,
            )

            return {
                "success": result.success,
                "result": result.to_dict(),
            }

        except Exception as e:
            self.logger.error("File execution failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "result": None,
            }

    async def test_code(
        self,
        code: str,
        test_input: str,
        expected_output: str,
        language: str = "python",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Test code with input and expected output.

        Args:
            code: Code to test
            test_input: Input to provide to code
            expected_output: Expected output
            language: Programming language
            **kwargs: Additional parameters

        Returns:
            Result with test pass/fail status
        """
        try:
            # Execute code with input
            result = await self.execute(
                code=code,
                language=language,
                stdin=test_input,
            )

            if not result["success"]:
                return {
                    "success": False,
                    "test_passed": False,
                    "error": result.get("error"),
                    "result": result.get("result"),
                }

            actual_output = result["result"]["output"]
            test_passed = actual_output.strip() == expected_output.strip()

            return {
                "success": True,
                "test_passed": test_passed,
                "expected": expected_output,
                "actual": actual_output,
                "result": result["result"],
            }

        except Exception as e:
            self.logger.error("Code test failed", error=str(e))
            return {
                "success": False,
                "test_passed": False,
                "error": str(e),
                "result": None,
            }
