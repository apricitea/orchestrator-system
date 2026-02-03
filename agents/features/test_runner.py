"""
Test Runner Integration

Automated test execution with result parsing and failure analysis.
Supports pytest, unittest, and custom test frameworks.
"""

import asyncio
import json
import re
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional

from utils.logger import get_logger


class TestFramework(str, Enum):
    """Supported test frameworks."""
    PYTEST = "pytest"
    UNITTEST = "unittest"
    JEST = "jest"
    MOCHA = "mocha"


class TestStatus(str, Enum):
    """Test execution status."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class TestResult:
    """Result of a test execution."""
    framework: TestFramework
    test_file: str
    test_name: str
    status: TestStatus
    duration_ms: int
    error_message: str = ""
    error_output: str = ""
    line_number: int = 0


@dataclass
class TestRunResult:
    """Result of a test run."""
    framework: TestFramework
    total_tests: int
    passed: int
    failed: int
    skipped: int
    errors: int
    duration_ms: int
    results: List[TestResult]
    output: str = ""


class TestRunner:
    """
    Execute tests and parse results.

    Features:
    - Multi-framework support (pytest, unittest, jest, mocha)
    - Result parsing and extraction
    - Failure analysis
    - Coverage reporting
    - Automatic re-running of failed tests
    """

    def __init__(self):
        self.logger = get_logger("test_runner")

    async def run_tests(
        self,
        project_path: str,
        framework: TestFramework = TestFramework.PYTEST,
        target: Optional[str] = None,
        coverage: bool = False,
    ) -> TestRunResult:
        """
        Run tests for a project.

        Args:
            project_path: Path to the project
            framework: Test framework to use
            target: Specific test file/function to run
            coverage: Whether to run with coverage report

        Returns:
            Test run results
        """
        try:
            if framework == TestFramework.PYTEST:
                return await self._run_pytest(project_path, target, coverage)
            elif framework == TestFramework.UNITTEST:
                return await self._run_unittest(project_path, target, coverage)
            elif framework == TestFramework.JEST:
                return await self._run_jest(project_path, target, coverage)
            elif framework == TestFramework.MOCHA:
                return await self._run_mocha(project_path, target, coverage)
            else:
                return TestRunResult(
                    framework=framework,
                    total_tests=0,
                    passed=0,
                    failed=0,
                    skipped=0,
                    errors=0,
                    duration_ms=0,
                    results=[],
                    output="",
                )

        except Exception as e:
            self.logger.error("Test run failed", error=str(e))
            return TestRunResult(
                framework=framework,
                total_tests=0,
                passed=0,
                failed=0,
                skipped=0,
                errors=1,
                duration_ms=0,
                results=[],
                output=f"Error: {str(e)}",
            )

    async def _run_pytest(
        self,
        project_path: str,
        target: Optional[str],
        coverage: bool,
    ) -> TestRunResult:
        """Run pytest tests."""
        cmd = ["python3", "-m", "pytest"]

        if coverage:
            cmd.extend(["--cov=.", "--cov-report=json"])

        if target:
            cmd.append(target)
        else:
            cmd.append(project_path)

        cmd.extend(["-v", "--tb=short", "--json-report"])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=project_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate()
        output = stdout.decode()
        error_output = stderr.decode()

        # Parse results
        return self._parse_pytest_results(output, error_output, proc.returncode)

    def _parse_pytest_results(
        self,
        stdout: str,
        stderr: str,
        returncode: int,
    ) -> TestRunResult:
        """Parse pytest results."""
        results = []
        lines = stdout.split("\n")

        total = passed = failed = skipped = errors = 0
        duration_ms = 0

        for line in lines:
            # Parse test results
            # Format: test_file.py::test_function PASSED/FAILED
            match = re.match(r"(.+?)::(\w+)\s+(PASSED|FAILED|ERROR|SKIPPED)", line)
            if match:
                test_file, test_name, status_str = match.groups()
                status = TestStatus(status_str.lower())

                if status == TestStatus.PASSED:
                    passed += 1
                elif status == TestStatus.FAILED:
                    failed += 1
                elif status == TestStatus.ERROR:
                    errors += 1
                elif status == TestStatus.SKIPPED:
                    skipped += 1

                total += 1

                results.append(
                    TestResult(
                        framework=TestFramework.PYTEST,
                        test_file=test_file,
                        test_name=test_name,
                        status=status,
                        duration_ms=0,  # Parse from JSON if available
                    )
                )

        return TestRunResult(
            framework=TestFramework.PYTEST,
            total_tests=total,
            passed=passed,
            failed=failed,
            skipped=skipped,
            errors=errors,
            duration_ms=duration_ms,
            results=results,
            output=stdout + "\n" + stderr,
        )

    async def _run_unittest(
        self,
        project_path: str,
        target: Optional[str],
        coverage: bool,
    ) -> TestRunResult:
        """Run unittest tests."""
        cmd = ["python3", "-m", "unittest"]

        if coverage:
            cmd = ["python3", "-m", "coverage", "run", "-m", "unittest"]

        if target:
            cmd.append(target)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=project_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate()
        output = stdout.decode()

        # Parse unittest results
        return self._parse_unittest_results(output, proc.returncode)

    def _parse_unittest_results(self, output: str, returncode: int) -> TestRunResult:
        """Parse unittest results."""
        lines = output.split("\n")

        total = passed = failed = skipped = errors = 0

        # Parse summary line: "Ran X tests in Ys"
        for line in lines:
            match = re.match(r"Ran (\d+) tests?", line)
            if match:
                total = int(match.group(1))

            # Parse: "OK (skipped=X)"
            if "OK" in line:
                passed = total

            if "FAILED" in line:
                match = re.search(r"failures=(\d+)", line)
                if match:
                    failed = int(match.group(1))

                match = re.search(r"errors=(\d+)", line)
                if match:
                    errors = int(match.group(1))

        return TestRunResult(
            framework=TestFramework.UNITTEST,
            total_tests=total,
            passed=passed,
            failed=failed,
            skipped=skipped,
            errors=errors,
            duration_ms=0,
            results=[],
            output=output,
        )

    async def _run_jest(
        self,
        project_path: str,
        target: Optional[str],
        coverage: bool,
    ) -> TestRunResult:
        """Run Jest tests."""
        cmd = ["npx", "jest", "--json", "--verbose"]

        if target:
            cmd.append(target)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=project_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate()

        # Parse JSON output
        try:
            json_results = [json.loads(line) for line in stdout.split("\n") if line.strip()]
            return self._parse_jest_results(json_results)
        except:
            # Fallback to text parsing
            return TestRunResult(
                framework=TestFramework.JEST,
                total_tests=0,
                passed=0,
                failed=0,
                skipped=0,
                errors=0,
                duration_ms=0,
                results=[],
                output=stdout.decode() + "\n" + stderr.decode(),
            )

    def _parse_jest_results(self, json_results: list) -> TestRunResult:
        """Parse Jest JSON results."""
        total = passed = failed = skipped = 0
        results = []

        for result in json_results:
            if result.get("status") == "passed":
                passed += 1
            elif result.get("status") == "failed":
                failed += 1
            elif result.get("status") == "skipped":
                skipped += 1

            total += 1

        return TestRunResult(
            framework=TestFramework.JEST,
            total_tests=total,
            passed=passed,
            failed=failed,
            skipped=skipped,
            errors=0,
            duration_ms=0,
            results=results,
        )

    async def _run_mocha(
        self,
        project_path: str,
        target: Optional[str],
        coverage: bool,
    ) -> TestRunResult:
        """Run Mocha tests."""
        cmd = ["npx", "mocha", "--reporter", "json"]

        if target:
            cmd.append(target)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=project_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate()

        # Parse JSON output
        try:
            json_results = json.loads(stdout.decode())
            return self._parse_mocha_results(json_results)
        except:
            return TestRunResult(
                framework=TestFramework.MOCHA,
                total_tests=0,
                passed=0,
                failed=0,
                skipped=0,
                errors=0,
                duration_ms=0,
                results=[],
                output=stdout.decode() + "\n" + stderr.decode(),
            )

    def _parse_mocha_results(self, json_results: dict) -> TestRunResult:
        """Parse Mocha JSON results."""
        total = len(json_results.get("tests", []))
        passed = len(json_results.get("passes", []))
        failed = len(json_results.get("failures", []))
        pending = len(json_results.get("pending", []))
        skipped = pending

        return TestRunResult(
            framework=TestFramework.MOCHA,
            total_tests=total,
            passed=passed,
            failed=failed,
            skipped=skipped,
            errors=0,
            duration_ms=0,
            results=[],
            output="",
        )

    async def run_failed_tests(
        self,
        project_path: str,
        framework: TestFramework = TestFramework.PYTEST,
        last_results: Optional[TestRunResult] = None,
    ) -> TestRunResult:
        """
        Re-run only failed tests.

        Args:
            project_path: Path to the project
            framework: Test framework
            last_results: Previous test results to identify failures

        Returns:
            Test run results for failed tests
        """
        if not last_results or last_results.failed == 0:
            return TestRunResult(
                framework=framework,
                total_tests=0,
                passed=0,
                failed=0,
                skipped=0,
                errors=0,
                duration_ms=0,
                results=[],
                output="No failed tests to re-run",
            )

        # Build target with failed tests
        failed_tests = [
            f"{r.test_file}::{r.test_name}"
            for r in last_results.results
            if r.status == TestStatus.FAILED
        ]

        target = " ".join(failed_tests)
        return await self.run_tests(project_path, framework, target, coverage=False)

    def generate_fix_suggestions(
        self,
        results: TestRunResult,
    ) -> List[str]:
        """
        Generate fix suggestions for failed tests.

        Args:
            results: Test run results

        Returns:
            List of fix suggestions
        """
        suggestions = []

        for result in results.results:
            if result.status == TestStatus.FAILED:
                suggestion = f"Fix failing test: {result.test_name} in {result.test_file}"

                if result.error_message:
                    suggestion += f"\n  Error: {result.error_message[:200]}"

                suggestions.append(suggestion)

        return suggestions


# Global instance
_test_runner: Optional[TestRunner] = None


def get_test_runner() -> TestRunner:
    """Get the global test runner instance."""
    global _test_runner
    if _test_runner is None:
        _test_runner = TestRunner()
    return _test_runner
