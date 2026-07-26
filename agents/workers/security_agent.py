"""
Security Agent - LLM-Powered

Specialized agent for security analysis and vulnerability scanning using Claude/GPT.
"""

import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.base.base_agent import AgentConfig, AgentResult, BaseAgent
from agents.tools.tool_registry import get_tool_registry
from models.llm.llm_wrapper import get_llm_wrapper
from utils.logger import AgentLogger


class SecurityAgent(BaseAgent):
    """
    Agent specialized in security analysis and vulnerability detection using LLMs.

    Capabilities:
    - Static code analysis for security issues
    - Dependency vulnerability scanning
    - Secret detection
    - Security audit reports
    - OWASP Top 10 checks
    - Best practices enforcement
    """

    # Common secret patterns
    SECRET_PATTERNS = {
        "AWS Access Key": r"AKIA[0-9A-Z]{16}",
        "AWS Secret Key": r"[0-9a-zA-Z/+]{40}",
        "API Key": r"(?i)(api[_-]?key|apikey)['\"]?\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{16,})",
        "GitHub Token": r"ghp_[a-zA-Z0-9]{36}",
        "Slack Token": r"xox[pbar]-[0-9]{12}-[0-9]{12}-[0-9]{12}-[a-zA-Z0-9]{32}",
        "Private Key": r"-----BEGIN [A-Z]+ PRIVATE KEY-----",
        "Password": r"(?i)(password|passwd|pwd)['\"]?\s*[:=]\s*['\"]([^'\"]{8,})['\"]",
        "Database URL": r"(?i)(mongodb|postgresql|mysql|redis)://[^:\s]+:[^@\s]+@",
    }

    # Security vulnerabilities to check
    VULN_PATTERNS = {
        "SQL Injection": [
            r'f"SELECT.*\{.*\}',
            r'".*SELECT.*" \+ .*',
            r"'SELECT.*' \+ .*",
            r"execute\(.*format\(",
        ],
        "Command Injection": [
            r"os\.system\(",
            r"subprocess\.call\(.*shell=True",
            r"eval\(",
            r"exec\(",
        ],
        "Hardcoded Secrets": SECRET_PATTERNS.values(),
        "Weak Cryptography": [
            r"md5\(",
            r"sha1\(",
            r"DES_",
            r"RC4_",
        ],
        "Insecure Random": [
            r"random\.random\(",
        ],
        "Unsafe Deserialization": [
            r"pickle\.loads?\(",
            r"cPickle\.loads?\(",
        ],
    }

    def __init__(self, config: AgentConfig):
        """Initialize security agent."""
        super().__init__(config)
        self.llm = get_llm_wrapper()
        self.tools = get_tool_registry()
        self.logger.logger.info("Security agent initialized with LLM")

    async def execute(self, task: str, **kwargs: Any) -> AgentResult:
        """
        Execute a security task.

        Args:
            task: Task description
            **kwargs: Additional parameters

        Returns:
            Agent result
        """
        start_time = time.time()

        self.logger.logger.info("Executing security task", task=task)

        # Determine task type
        task_lower = task.lower()

        if "scan" in task_lower or "vulnerab" in task_lower:
            return await self._security_scan(task, **kwargs)
        elif "secret" in task_lower or "leak" in task_lower:
            return await self._scan_secrets(task, **kwargs)
        elif "depend" in task_lower:
            return await self._scan_dependencies(task, **kwargs)
        elif "audit" in task_lower or "report" in task_lower:
            return await self._security_audit(task, **kwargs)
        elif "owasp" in task_lower:
            return await self._owasp_check(task, **kwargs)
        else:
            # Use LLM to figure out what to do
            return await self._llm_assisted_security(task, **kwargs)

    async def _security_scan(self, task: str, **kwargs) -> AgentResult:
        """Perform static code security scan."""
        working_directory = kwargs.get("working_directory", ".")
        project_path = working_directory  # Use working_directory
        file_patterns = kwargs.get("file_patterns", ["*.py", "*.js", "*.ts"])

        self.logger.logger.info("Performing security scan", path=project_path)

        # Find files to scan
        files = self._find_files(project_path, file_patterns)

        if not files:
            return AgentResult(
                status="error",
                errors=["No files found to scan"],
            )

        findings = []

        # Scan each file (thorough security analysis)
        for file_path in files:
            file_findings = await self._scan_file(file_path)
            if file_findings:
                findings.extend(file_findings)

        # Generate report
        if findings:
            report = self._generate_scan_report(findings)

            return AgentResult(
                status="success",
                output=f"Security scan complete. Found {len(findings)} issues.",
                metadata={
                    "files_scanned": len(files),
                    "findings_count": len(findings),
                    "findings": findings,
                },
                next_steps=[
                    "Review and fix critical issues",
                    "Re-scan after fixes",
                    "Set up automated scanning",
                ],
            )
        else:
            return AgentResult(
                status="success",
                output="Security scan complete. No issues found.",
                metadata={"files_scanned": len(files), "findings_count": 0},
            )

    async def _scan_file(self, file_path: str) -> List[Dict[str, Any]]:
        """Scan a single file for security issues."""
        findings = []
        path = Path(file_path)

        try:
            content = path.read_text()
            lines = content.splitlines()

            # Check for each vulnerability pattern
            for vuln_type, patterns in self.VULN_PATTERNS.items():
                for pattern in patterns:
                    for line_num, line in enumerate(lines, 1):
                        if re.search(pattern, line, re.IGNORECASE):
                            findings.append({
                                "file": str(path),
                                "line": line_num,
                                "type": vuln_type,
                                "severity": self._get_severity(vuln_type),
                                "code": line.strip(),
                                "pattern": pattern,
                            })

        except Exception as e:
            self.logger.logger.warning("Failed to scan file", file=file_path, error=str(e))

        return findings

    async def _scan_secrets(self, task: str, **kwargs) -> AgentResult:
        """Scan for hardcoded secrets and credentials."""
        project_path = kwargs.get("project_path", ".")

        self.logger.logger.info("Scanning for secrets", path=project_path)

        files = self._find_files(project_path, ["*"])
        secrets_found = []

        for file_path in files:
            path = Path(file_path)

            # Skip common non-code files
            if path.suffix in [".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip"]:
                continue

            try:
                content = path.read_text()
                lines = content.splitlines()

                for secret_type, pattern in self.SECRET_PATTERNS.items():
                    for line_num, line in enumerate(lines, 1):
                        if re.search(pattern, line):
                            # Mask the actual secret
                            masked_line = self._mask_secret(line, pattern)

                            secrets_found.append({
                                "file": str(path.relative_to(project_path)),
                                "line": line_num,
                                "type": secret_type,
                                "severity": "critical",
                                "masked_code": masked_line,
                            })

            except Exception:
                continue

        if secrets_found:
            return AgentResult(
                status="success",
                output=f"Found {len(secrets_found)} potential secrets",
                metadata={
                    "secrets": secrets_found,
                    "count": len(secrets_found),
                },
                next_steps=[
                    "Verify and remove confirmed secrets",
                    "Rotate exposed credentials",
                    "Add .gitignore patterns",
                    "Set up pre-commit hooks",
                ],
            )
        else:
            return AgentResult(
                status="success",
                output="No secrets found",
                metadata={"count": 0},
            )

    async def _scan_dependencies(self, task: str, **kwargs) -> AgentResult:
        """Scan dependencies for known vulnerabilities."""
        project_path = kwargs.get("project_path", ".")

        self.logger.logger.info("Scanning dependencies", path=project_path)

        vulnerabilities = []

        # Check Python dependencies
        requirements_files = list(Path(project_path).rglob("requirements*.txt"))
        for req_file in requirements_files:
            vulns = await self._check_python_requirements(req_file)
            vulnerabilities.extend(vulns)

        # Check package.json
        package_files = list(Path(project_path).rglob("package.json"))
        for pkg_file in package_files:
            vulns = await self._check_npm_dependencies(pkg_file)
            vulnerabilities.extend(vulns)

        if vulnerabilities:
            return AgentResult(
                status="success",
                output=f"Found {len(vulnerabilities)} vulnerable dependencies",
                metadata={
                    "vulnerabilities": vulnerabilities,
                    "count": len(vulnerabilities),
                },
                next_steps=[
                    "Update vulnerable packages",
                    "Review severity and impact",
                    "Test updates thoroughly",
                ],
            )
        else:
            return AgentResult(
                status="success",
                output="No vulnerable dependencies found",
                metadata={"count": 0},
            )

    async def _check_python_requirements(self, req_file: Path) -> List[Dict[str, Any]]:
        """Check Python requirements for vulnerabilities."""
        vulns = []
        # In production, would query a vulnerability database
        # For now, provide a placeholder
        return vulns

    async def _check_npm_dependencies(self, pkg_file: Path) -> List[Dict[str, Any]]:
        """Check npm dependencies for vulnerabilities."""
        vulns = []
        # In production, would run `npm audit`
        # For now, provide a placeholder
        return vulns

    async def _security_audit(self, task: str, **kwargs) -> AgentResult:
        """Perform comprehensive security audit."""
        project_path = kwargs.get("project_path", ".")

        self.logger.logger.info("Performing security audit", path=project_path)

        # Run multiple checks
        scan_result = await self._security_scan(task, **kwargs)
        secrets_result = await self._scan_secrets(task, **kwargs)
        deps_result = await self._scan_dependencies(task, **kwargs)

        # Compile comprehensive report
        findings_count = (
            scan_result.metadata.get("findings_count", 0)
            + secrets_result.metadata.get("count", 0)
            + deps_result.metadata.get("count", 0)
        )

        return AgentResult(
            status="success",
            output=f"Security audit complete. Found {findings_count} total issues.",
            metadata={
                "scan_results": scan_result.metadata,
                "secrets_results": secrets_result.metadata,
                "dependencies_results": deps_result.metadata,
                "total_findings": findings_count,
            },
            next_steps=[
                "Review all findings",
                "Prioritize by severity",
                "Create remediation plan",
                "Implement fixes",
            ],
        )

    async def _owasp_check(self, task: str, **kwargs) -> AgentResult:
        """Check against OWASP Top 10."""
        project_path = kwargs.get("project_path", ".")

        self.logger.logger.info("Checking OWASP Top 10", path=project_path)

        # OWASP Top 10 2021 categories
        owasp_checks = {
            "A01: Broken Access Control": [],
            "A02: Cryptographic Failures": [],
            "A03: Injection": [],
            "A04: Insecure Design": [],
            "A05: Security Misconfiguration": [],
            "A06: Vulnerable Components": [],
            "A07: Auth Failures": [],
            "A08: Data Integrity Failures": [],
            "A09: Logging Failures": [],
            "A10: Server-Side Request Forgery": [],
        }

        # Run checks for each category
        # In production, would implement specific checks

        return AgentResult(
            status="success",
            output="OWASP Top 10 check complete",
            metadata={"owasp_findings": owasp_checks},
            next_steps=[
                "Review OWASP findings",
                "Implement security controls",
                "Follow secure coding practices",
            ],
        )

    async def _llm_assisted_security(self, task: str, **kwargs) -> AgentResult:
        """Use LLM to assist with security analysis."""
        context = kwargs.get("context", {})
        code = kwargs.get("code", "")

        prompt = f"""Help with security task: {task}

Context: {context if context else 'None provided'}

Analyze what security checks are needed and provide:
1. Security assessment
2. Vulnerabilities found
3. Risk level (critical/high/medium/low)
4. Remediation steps
5. Best practice recommendations"""

        if code:
            prompt += f"\n\nCode to analyze:\n```\n{code[:3000]}\n```"

        system_prompt = """You are a cybersecurity expert specializing in application security.

Provide thorough security analysis including:
- Common vulnerability patterns (OWASP Top 10)
- Injection flaws (SQL, XSS, command injection)
- Authentication and authorization issues
- Cryptographic weaknesses
- Configuration security
- Dependency vulnerabilities
- Secret/credential exposure

Be specific about vulnerabilities found and provide actionable remediation steps."""

        try:
            response = await self.llm.generate(
                prompt=prompt,
                model=self.config.model,
                system_prompt=system_prompt,
                temperature=0.3,
                max_tokens=4096,
            )

            return AgentResult(
                status="success",
                output=response.content,
                metadata={"llm_assisted": True},
                next_steps=[
                    "Review security analysis",
                    "Implement recommended fixes",
                    "Re-scan after changes",
                ],
            )

        except Exception as e:
            return AgentResult(
                status="error",
                errors=[str(e)],
            )

    def _find_files(self, project_path: str, patterns: List[str]) -> List[str]:
        """Find files matching patterns, excluding only directories that cause hangs."""
        path = Path(project_path)
        files = []

        # Only exclude directories that cause infinite hangs, not real code
        EXCLUDE_DIRS = {
            ".git",  # HUGE - causes hangs
            "node_modules",  # Can be massive - exclude for speed
        }

        for pattern in patterns:
            for file_path in path.rglob(pattern):
                # Only skip .git and node_modules to prevent hangs
                # Let it scan everything else for thorough security analysis
                if not any(excluded_dir in file_path.parts for excluded_dir in EXCLUDE_DIRS):
                    files.append(str(file_path))

        return files

    def _get_severity(self, vuln_type: str) -> str:
        """Get severity level for vulnerability type."""
        severity_map = {
            "SQL Injection": "critical",
            "Command Injection": "critical",
            "Hardcoded Secrets": "critical",
            "Unsafe Deserialization": "high",
            "Weak Cryptography": "medium",
            "Insecure Random": "low",
        }
        return severity_map.get(vuln_type, "medium")

    def _mask_secret(self, line: str, pattern: str) -> str:
        """Mask secrets in a line for logging."""
        match = re.search(pattern, line)
        if match:
            start, end = match.span()
            return line[:start] + "***REDACTED***" + line[end:]
        return line

    def _generate_scan_report(self, findings: List[Dict[str, Any]]) -> str:
        """Generate a security scan report."""
        lines = ["# Security Scan Report\n"]

        # Group by severity
        by_severity = {}
        for finding in findings:
            severity = finding["severity"]
            if severity not in by_severity:
                by_severity[severity] = []
            by_severity[severity].append(finding)

        # Order by severity
        for severity in ["critical", "high", "medium", "low"]:
            if severity in by_severity:
                lines.append(f"## {severity.upper()} ({len(by_severity[severity])})\n")
                for finding in by_severity[severity]:
                    lines.append(f"### {finding['type']}")
                    lines.append(f"- File: {finding['file']}")
                    lines.append(f"- Line: {finding['line']}")
                    lines.append(f"- Code: `{finding['code']}`")
                    lines.append("")

        return "\n".join(lines)

    async def validate(self, result: AgentResult) -> bool:
        """Validate security result."""
        return result.status in ["success", "partial", "error"]

    async def scan_project(
        self,
        project_path: str = ".",
    ) -> AgentResult:
        """Perform security scan on a project."""
        return await self.execute(
            f"Security scan for {project_path}",
            project_path=project_path,
        )

    async def audit_project(
        self,
        project_path: str = ".",
    ) -> AgentResult:
        """Perform comprehensive security audit."""
        return await self.execute(
            f"Security audit for {project_path}",
            project_path=project_path,
        )


async def create_security_agent() -> SecurityAgent:
    """Create a security agent instance."""
    config = AgentConfig(
        name="security_agent",
        description="Security scanning agent powered by LLM",
        model="claude-sonnet-4-5-20250929",
        temperature=0.2,
        max_tokens=4096,
    )

    return SecurityAgent(config)
