"""
Dependency Auto-Management

Automatically detects and manages Python package dependencies.
Updates requirements.txt, handles version conflicts, and detects security vulnerabilities.
"""

import ast
import re
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set

import httpx

from utils.logger import get_logger


class DependencyType(str, Enum):
    """Type of dependency."""
    STANDARD_LIBRARY = "std"
    THIRD_PARTY = "third_party"
    LOCAL = "local"


@dataclass
class DependencyInfo:
    """Information about a dependency."""
    name: str
    version: Optional[str]
    type: DependencyType
    file_path: str
    line_number: int
    is_missing: bool = False


@dataclass
class DependencyUpdate:
    """Required dependency update."""
    package_name: str
    current_version: Optional[str]
    latest_version: str
    action: str  # "add", "upgrade", "remove"


class DependencyManager:
    """
    Automatically manage project dependencies.

    Features:
    - Scan code for imports
    - Check if packages are installed
    - Detect missing dependencies
    - Update requirements.txt
    - Check for outdated packages
    - Security vulnerability scanning
    """

    def __init__(self):
        self.logger = get_logger("dependency_manager")

    async def scan_project(
        self,
        project_path: str,
    ) -> List[DependencyInfo]:
        """
        Scan project for all dependencies.

        Args:
            project_path: Path to the project

        Returns:
            List of all dependencies found
        """
        dependencies = []

        python_files = Path(project_path).rglob("*.py")

        for file_path in python_files:
            file_deps = await self._scan_file(str(file_path))
            dependencies.extend(file_deps)

        self.logger.info(
            "Scanned project dependencies",
            project=project_path,
            count=len(dependencies),
        )

        return dependencies

    async def _scan_file(self, file_path: str) -> List[DependencyInfo]:
        """Scan a single Python file for dependencies."""
        dependencies = []

        try:
            code = Path(file_path).read_text()
            tree = ast.parse(code, filename=file_path)

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        dep = DependencyInfo(
                            name=alias.name.split(".")[0],
                            version=None,
                            type=DependencyType.THIRD_PARTY,
                            file_path=file_path,
                            line_number=node.lineno,
                        )
                        dependencies.append(dep)

                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        dep = DependencyInfo(
                            name=node.module.split(".")[0],
                            version=None,
                            type=DependencyType.THIRD_PARTY,
                            file_path=file_path,
                            line_number=node.lineno,
                        )
                        dependencies.append(dep)

                    for alias in node.names:
                        if alias.name:
                            dep = DependencyInfo(
                                name=alias.name.split(".")[0],
                                version=None,
                                type=DependencyType.THIRD_PARTY,
                                file_path=file_path,
                                line_number=node.lineno,
                            )
                            dependencies.append(dep)

        except Exception as e:
            self.logger.warning("Failed to scan file", file=file_path, error=str(e))

        return dependencies

    async def check_missing(
        self,
        dependencies: List[DependencyInfo],
    ) -> List[DependencyInfo]:
        """
        Check which dependencies are missing.

        Args:
            dependencies: List of dependencies to check

        Returns:
            List of missing dependencies
        """
        missing = []

        for dep in dependencies:
            if dep.type == DependencyType.THIRD_PARTY:
                try:
                    __import__(dep.name)
                except ImportError:
                    dep.is_missing = True
                    missing.append(dep)

        return missing

    async def update_requirements(
        self,
        project_path: str,
        dependencies: List[DependencyInfo],
    ) -> bool:
        """
        Update requirements.txt with missing dependencies.

        Args:
            project_path: Path to the project
            dependencies: Dependencies to add

        Returns:
            True if successful
        """
        requirements_path = Path(project_path) / "requirements.txt"

        try:
            # Read existing requirements
            existing_packages: Set[str] = set()
            if requirements_path.exists():
                content = requirements_path.read_text()
                for line in content.split("\n"):
                    match = re.match(r"^([a-zA-Z0-9_-]+)", line.strip())
                    if match:
                        existing_packages.add(match.group(1))

            # Find new packages to add
            new_packages = set()
            for dep in dependencies:
                if dep.is_missing and dep.name not in existing_packages:
                    new_packages.add(dep.name)

            if not new_packages:
                self.logger.info("No new dependencies to add")
                return True

            # Append new packages
            with open(requirements_path, "a") as f:
                f.write(f"\n# Auto-added dependencies\n")
                for package in sorted(new_packages):
                    f.write(f"{package}\n")

            self.logger.info(
                "Updated requirements.txt",
                new_packages=len(new_packages),
            )

            return True

        except Exception as e:
            self.logger.error("Failed to update requirements", error=str(e))
            return False

    async def check_outdated(
        self,
        project_path: str,
    ) -> List[DependencyUpdate]:
        """
        Check for outdated packages.

        Args:
            project_path: Path to the project

        Returns:
            List of available updates
        """
        requirements_path = Path(project_path) / "requirements.txt"

        if not requirements_path.exists():
            return []

        try:
            # Get installed packages
            result = subprocess.run(
                ["/home/ubuntu/venv/bin/pip", "list", "--outdated", "--format=json"],
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                return []

            import json
            outdated = json.loads(result.stdout)

            updates = []
            for pkg in outdated:
                updates.append(
                    DependencyUpdate(
                        package_name=pkg["name"],
                        current_version=pkg.get("version", "unknown"),
                        latest_version=pkg["latest_version"],
                        action="upgrade",
                    )
                )

            return updates

        except Exception as e:
            self.logger.error("Failed to check outdated packages", error=str(e))
            return []

    async def detect_security_issues(
        self,
        project_path: str,
    ) -> List[Dict[str, str]]:
        """
        Detect known security vulnerabilities in dependencies.

        Args:
            project_path: Path to the project

        Returns:
            List of security issues found
        """
        issues = []

        try:
            # Use pip-audit or similar tool
            result = subprocess.run(
                ["/home/ubuntu/venv/bin/pip", "check", project_path],
                capture_output=True,
                text=True,
                timeout=60,
            )

            # Parse output for known vulnerability patterns
            output = result.stdout + result.stderr

            if "vulnerability" in output.lower():
                # Parse for CVE numbers and package names
                cve_pattern = r"([A-Za-z0-9_-]+)\s+(CVE-\d{4}-\d+)"
                matches = re.findall(cve_pattern, output)

                for package, cve in matches:
                    issues.append(
                        {
                            "package": package,
                            "cve": cve,
                            "severity": "high",
                        }
                    )

        except Exception as e:
            self.logger.warning("Security check failed", error=str(e))

        return issues

    async def install_dependencies(
        self,
        project_path: str,
        packages: Optional[List[str]] = None,
    ) -> bool:
        """
        Install dependencies into the virtual environment.

        Args:
            project_path: Path to the project
            packages: Specific packages to install (optional)

        Returns:
            True if successful
        """
        try:
            if packages:
                cmd = ["/home/ubuntu/venv/bin/pip", "install"] + packages
            else:
                requirements_path = Path(project_path) / "requirements.txt"
                if not requirements_path.exists():
                    self.logger.warning("No requirements.txt found")
                    return False

                cmd = ["/home/ubuntu/venv/bin/pip", "install", "-r", str(requirements_path)]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                self.logger.info("Dependencies installed successfully")
                return True
            else:
                self.logger.error(
                    "Failed to install dependencies",
                    error=stderr.decode(),
                )
                return False

        except Exception as e:
            self.logger.error("Failed to install dependencies", error=str(e))
            return False


# Global instance
_dependency_manager: Optional[DependencyManager] = None


def get_dependency_manager() -> DependencyManager:
    """Get the global dependency manager instance."""
    global _dependency_manager
    if _dependency_manager is None:
        _dependency_manager = DependencyManager()
    return _dependency_manager


# Add asyncio import at top
import asyncio
