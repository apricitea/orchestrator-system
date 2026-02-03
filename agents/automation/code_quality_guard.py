"""
Code Quality Guard - Enforces security, quality, and best practices

This module implements patterns from SkillsMP agent skills:
- Security scanning (hardcoded secrets, XSS, SQL injection)
- Error handling validation
- Code quality checks
- Architecture validation
"""

import re
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

from utils.logger import get_logger


class Severity(Enum):
    """Issue severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class QualityIssue:
    """Represents a code quality issue."""
    severity: Severity
    category: str
    title: str
    description: str
    file_path: str
    line_number: Optional[int]
    fix_suggestion: str
    reference_url: Optional[str] = None


class CodeQualityGuard:
    """
    Enforces code quality standards based on SkillsMP best practices.

    Checks for:
    1. Security vulnerabilities (hardcoded secrets, XSS, SQL injection)
    2. Error handling issues
    3. Architecture violations
    4. Code quality issues
    """

    # Patterns for detecting hardcoded secrets
    SECRET_PATTERNS = [
        (r'password\s*=\s*["\'][^"\']+["\']', "Hardcoded password"),
        (r'api_key\s*=\s*["\'][^"\']+["\']', "Hardcoded API key"),
        (r'secret_key\s*=\s*["\'][^"\']+["\']', "Hardcoded secret key"),
        (r'token\s*=\s*["\'][^"\']+["\']', "Hardcoded token"),
        (r'SECRET_KEY\s*=\s*["\']', "Flask SECRET_KEY hardcoded"),
        (r'GITHUB_TOKEN\s*=\s*["\']', "GitHub token hardcoded"),
        (r'api[_-]?key\s*=\s*["\']', "API key in variable"),
        (r'secret[_-]?key\s*=\s*["\']', "Secret key in variable"),
        (r'aws[_-]?access[_-]?key\s*=\s*["\']', "AWS access key"),
        (r'aws[_-]?secret\s*=\s*["\']', "AWS secret key"),
    ]

    # Patterns for detecting security vulnerabilities
    XSS_PATTERNS = [
        (r'{{\s*\w+\s*}}', "Unescaped template variable (potential XSS)"),
        (r'innerHTML\s*=.*\+', "Direct innerHTML assignment (XSS risk)"),
        (r'document\.write\s*\(', "document.write usage (XSS risk)"),
        (r'eval\s*\(', "eval usage (code injection risk)"),
    ]

    SQL_INJECTION_PATTERNS = [
        (r'execute\s*\(\s*["\'].*\+\s*\w', "SQL query with string concatenation"),
        (r'query\s*\(\s*["\'].*\+\s*\w', "SQL query with string concatenation"),
        (r'f["\'].*SELECT.*{', "f-string in SQL query (potential injection)"),
    ]

    # Patterns for detecting poor error handling
    ERROR_HANDLING_PATTERNS = [
        (r'except\s*:', "Bare except clause"),
        (r'except\s+Exception\s*:', "Generic exception handler"),
        (r'pass\s*$', "Empty except block with pass"),
    ]

    # Patterns for detecting production issues
    PRODUCTION_ISSUES = [
        (r'app\.run\s*\(\s*debug\s*=\s*True', "Debug mode enabled"),
        (r'print\s*\(', "Using print instead of logger"),
        (r'pdb\.set_trace\s*\(\)', "Debugger left in code"),
        (r'breakpoint\s*\(\)', "Breakpoint left in code"),
    ]

    # Bad architecture patterns
    ARCHITECTURE_ANTI_PATTERNS = [
        (r'^import\s+\w+\s*$', "Wildcard import"),
        (r'from\s+\w+\s+import\s+\*', "Wildcard import"),
        (r'^\w+\s*=\s*\w+\(\)\s*$', "Global object instantiation"),
    ]

    # Dangerous operations - could destroy repo or system
    DANGEROUS_OPERATIONS = [
        (r'shutil\.rmtree\s*\(', "Recursive directory deletion"),
        (r'os\.remove\s*\(\s*["\']/', "File deletion in root path"),
        (r'os\.system\s*\(\s*["\']rm\s+-rf', "Shell command to delete files"),
        (r'subprocess\.call\s*\(\s*["\']rm\s+', "Shell command to delete files"),
        (r'subprocess\.run\s*\([^)]*shell\s*=\s*True', "Shell execution enabled (command injection risk)"),
        (r'os\.system\s*\(', "Direct shell command execution"),
        (r'eval\s*\(', "eval() usage (code execution)"),
        (r'exec\s*\(', "exec() usage (code execution)"),
        (r'__import__\s*\(\s*["\']os["\']', "Dynamic import of os module (suspicious)"),
        (r'repo\.delete\s*\(', "Repository deletion API"),
        (r'github\.get_repo\s*\([^)]+\)\.delete', "GitHub repository deletion"),
        (r'git\.delete_repository\s*\(', "Git repository deletion"),
        (r'\.delete\s*\(\s*\)', "Generic delete method call (verify intent)"),
    ]

    # Malicious code patterns
    MALICIOUS_PATTERNS = [
        (r'crypto\.createCipheriv', "Cryptographic function (potential malware)"),
        (r'child_process\.exec\s*\(', "Child process execution (potential backdoor)"),
        (r'net\.createServer\s*\([^)]*function', "Server creation (potential C2)"),
        (r'socket\.socket\s*\(', "Socket creation (potential network backdoor)"),
        (r'requests\.post\s*\([^)]*http://.*:[0-9]{4,5}', "Outbound connection to non-standard port (potential C2)"),
        (r'urllib\.request\.urlopen\s*\(', "HTTP request (potential data exfiltration)"),
        (r'base64\.b64decode\s*\([^)]*exec', "Decode and execute pattern (common in malware)"),
        (r'compile\s*\([^)]*exec', "Compile and execute pattern"),
        (r'while\s+True\s*:\s*os\.system', "Infinite command execution loop"),
        (r'time\.sleep\s*\([^)]*\)\s*;\s*eval', "Delayed execution (evasion technique)"),
        (r'getattr\s*\([^)]*__', "Access to private/dunder methods (potential exploit)"),
        (r'__import__\s*\([^)]+\)\s*\.\s*load', "Dynamic module loading (potential code injection)"),
    ]

    # Command injection patterns
    COMMAND_INJECTION_PATTERNS = [
        (r'os\.system\s*\(\s*\w+\s*\+', "Command with concatenation (injection risk)"),
        (r'os\.popen\s*\(', "os.popen usage (command injection risk)"),
        (r'subprocess\.call\s*\(\s*\w+\s*\+', "Subprocess with concatenation"),
        (r'subprocess\.Popen\s*\(\s*shell\s*=\s*True', "Popen with shell=True"),
        (r'commands\.getoutput\s*\(', "commands.getoutput (injection risk)"),
        (r'popen2\.popen', "popen2 usage (deprecated, unsafe)"),
    ]

    def __init__(self):
        self.logger = get_logger("code_quality_guard")
        self.issues: List[QualityIssue] = []

    def check_file(self, file_path: str, content: str) -> List[QualityIssue]:
        """
        Check a file for quality issues.

        Args:
            file_path: Path to the file
            content: File content

        Returns:
            List of quality issues found
        """
        self.issues = []
        lines = content.split('\n')

        # Check for secrets
        self._check_secrets(file_path, lines)

        # Check for XSS vulnerabilities
        self._check_xss(file_path, lines)

        # Check for SQL injection
        self._check_sql_injection(file_path, lines)

        # Check for command injection (NEW)
        self._check_command_injection(file_path, lines)

        # Check for dangerous operations (NEW)
        self._check_dangerous_operations(file_path, lines)

        # Check for malicious patterns (NEW)
        self._check_malicious_patterns(file_path, lines)

        # Check error handling
        self._check_error_handling(file_path, lines)

        # Check production issues
        self._check_production_issues(file_path, lines)

        # Check architecture patterns
        self._check_architecture(file_path, lines)

        return self.issues

    def _check_secrets(self, file_path: str, lines: List[str]):
        """Check for hardcoded secrets."""
        for line_num, line in enumerate(lines, 1):
            for pattern, description in self.SECRET_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    # Exclude comments
                    stripped = line.strip()
                    if stripped.startswith('#'):
                        continue

                    self.issues.append(QualityIssue(
                        severity=Severity.CRITICAL,
                        category="security",
                        title=description,
                        description=f"Hardcoded secret found in {file_path}:{line_num}",
                        file_path=file_path,
                        line_number=line_num,
                        fix_suggestion="Move secret to environment variable or secure config",
                        reference_url="https://skillsmp.com/de/skills/harperaa-secure-claude-skills-security-awareness-information-leakage-skill-md"
                    ))

    def _check_xss(self, file_path: str, lines: List[str]):
        """Check for XSS vulnerabilities."""
        # Only check HTML/template files
        if not (file_path.endswith('.html') or file_path.endswith('.htm')):
            return

        for line_num, line in enumerate(lines, 1):
            for pattern, description in self.XSS_PATTERNS:
                if re.search(pattern, line):
                    self.issues.append(QualityIssue(
                        severity=Severity.HIGH,
                        category="security",
                        title=description,
                        description=f"XSS vulnerability in {file_path}:{line_num}",
                        file_path=file_path,
                        line_number=line_num,
                        fix_suggestion="Use proper escaping: {{ var|e }} in Jinja2, DOMPurify for JavaScript",
                        reference_url="https://skillsmp.com/fr/skills/ssiumha-dots-prompts-skills-review-security-skill-md"
                    ))

    def _check_sql_injection(self, file_path: str, lines: List[str]):
        """Check for SQL injection vulnerabilities."""
        for line_num, line in enumerate(lines, 1):
            for pattern, description in self.SQL_INJECTION_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    self.issues.append(QualityIssue(
                        severity=Severity.CRITICAL,
                        category="security",
                        title=description,
                        description=f"SQL injection risk in {file_path}:{line_num}",
                        file_path=file_path,
                        line_number=line_num,
                        fix_suggestion="Use parameterized queries or prepared statements",
                        reference_url="https://skillsmp.com/fr/skills/ssiumha-dots-prompts-skills-review-security-skill-md"
                    ))

    def _check_error_handling(self, file_path: str, lines: List[str]):
        """Check for poor error handling."""
        for line_num, line in enumerate(lines, 1):
            for pattern, description in self.ERROR_HANDLING_PATTERNS:
                if re.search(pattern, line):
                    self.issues.append(QualityIssue(
                        severity=Severity.MEDIUM,
                        category="error_handling",
                        title=description,
                        description=f"Poor error handling in {file_path}:{line_num}",
                        file_path=file_path,
                        line_number=line_num,
                        fix_suggestion="Catch specific exceptions, handle errors appropriately",
                        reference_url="https://skillsmp.com/skills/wshobson-agents-plugins-developer-essentials-skills-error-handling-patterns-skill-md"
                    ))

    def _check_production_issues(self, file_path: str, lines: List[str]):
        """Check for production deployment issues."""
        for line_num, line in enumerate(lines, 1):
            for pattern, description in self.PRODUCTION_ISSUES:
                if re.search(pattern, line):
                    severity = Severity.HIGH if "debug" in description.lower() else Severity.LOW
                    self.issues.append(QualityIssue(
                        severity=severity,
                        category="production",
                        title=description,
                        description=f"Production issue in {file_path}:{line_num}",
                        file_path=file_path,
                        line_number=line_num,
                        fix_suggestion="Remove debug mode, use proper logging",
                        reference_url="https://skillsmp.com/skills/wshobson-agents-plugins-cicd-automation-skills-deployment-pipeline-design-skill-md"
                    ))

    def _check_architecture(self, file_path: str, lines: List[str]):
        """Check for architecture anti-patterns."""
        for line_num, line in enumerate(lines, 1):
            for pattern, description in self.ARCHITECTURE_ANTI_PATTERNS:
                if re.match(pattern, line.strip()):
                    self.issues.append(QualityIssue(
                        severity=Severity.LOW,
                        category="architecture",
                        title=description,
                        description=f"Architecture issue in {file_path}:{line_num}",
                        file_path=file_path,
                        line_number=line_num,
                        fix_suggestion="Use explicit imports, avoid global state",
                        reference_url="https://skillsmp.com/es/skills/vasilyu1983-ai-agents-public-frameworks-shared-skills-skills-software-architecture-design-skill-md"
                    ))

    def _check_dangerous_operations(self, file_path: str, lines: List[str]):
        """Check for dangerous operations that could destroy repo or system."""
        for line_num, line in enumerate(lines, 1):
            # Skip comments
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('//') or stripped.startswith('"""'):
                continue

            for pattern, description in self.DANGEROUS_OPERATIONS:
                if re.search(pattern, line):
                    self.issues.append(QualityIssue(
                        severity=Severity.CRITICAL,
                        category="dangerous_operations",
                        title=description,
                        description=f"Dangerous operation in {file_path}:{line_num}",
                        file_path=file_path,
                        line_number=line_num,
                        fix_suggestion="Review this operation carefully. Ensure it's necessary and properly controlled.",
                        reference_url="https://owasp.org/www-community/attacks/Command_Injection"
                    ))

    def _check_malicious_patterns(self, file_path: str, lines: List[str]):
        """Check for malicious code patterns."""
        for line_num, line in enumerate(lines, 1):
            # Skip comments
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('//') or stripped.startswith('"""'):
                continue

            for pattern, description in self.MALICIOUS_PATTERNS:
                if re.search(pattern, line):
                    self.issues.append(QualityIssue(
                        severity=Severity.CRITICAL,
                        category="malicious_code",
                        title=description,
                        description=f"Potentially malicious pattern in {file_path}:{line_num}",
                        file_path=file_path,
                        line_number=line_num,
                        fix_suggestion="This pattern is commonly found in malware. Review carefully and justify its use.",
                        reference_url="https://owasp.org/www-project-application-security-verification-standard/"
                    ))

    def _check_command_injection(self, file_path: str, lines: List[str]):
        """Check for command injection vulnerabilities."""
        for line_num, line in enumerate(lines, 1):
            # Skip comments
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('//') or stripped.startswith('"""'):
                continue

            for pattern, description in self.COMMAND_INJECTION_PATTERNS:
                if re.search(pattern, line):
                    self.issues.append(QualityIssue(
                        severity=Severity.CRITICAL,
                        category="security",
                        title=description,
                        description=f"Command injection risk in {file_path}:{line_num}",
                        file_path=file_path,
                        line_number=line_num,
                        fix_suggestion="Use subprocess without shell=True, or use proper parameter passing",
                        reference_url="https://owasp.org/www-community/attacks/Command_Injection"
                    ))

    def check_directory(self, directory: str, extensions: Optional[List[str]] = None) -> List[QualityIssue]:
        """
        Check all files in a directory for quality issues.

        Args:
            directory: Directory path to check
            extensions: File extensions to check (default: .py, .html, .htm, .js)

        Returns:
            List of quality issues found
        """
        if extensions is None:
            extensions = ['.py', '.html', '.htm', '.js']

        self.issues = []
        dir_path = Path(directory)

        if not dir_path.exists():
            self.logger.logger.error("Directory not found", path=directory)
            return self.issues

        # Find all relevant files
        for ext in extensions:
            for file_path in dir_path.rglob(f'*{ext}'):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        self.issues.extend(self.check_file(str(file_path), content))
                except Exception as e:
                    self.logger.logger.warning("Failed to check file", path=str(file_path), error=str(e))

        return self.issues

    def get_critical_issues(self) -> List[QualityIssue]:
        """Get only critical and high severity issues."""
        return [i for i in self.issues if i.severity in [Severity.CRITICAL, Severity.HIGH]]

    def get_security_issues(self) -> List[QualityIssue]:
        """Get only security-related issues."""
        return [i for i in self.issues if i.category == "security"]

    def generate_report(self) -> str:
        """Generate a human-readable quality report."""
        if not self.issues:
            return "✅ No quality issues found!"

        # Group by severity
        by_severity = {
            Severity.CRITICAL: [],
            Severity.HIGH: [],
            Severity.MEDIUM: [],
            Severity.LOW: [],
            Severity.INFO: [],
        }

        for issue in self.issues:
            by_severity[issue.severity].append(issue)

        report_lines = [
            "# Code Quality Report",
            f"Total issues found: {len(self.issues)}",
            ""
        ]

        for severity in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]:
            issues = by_severity[severity]
            if issues:
                emoji = {
                    Severity.CRITICAL: "🔴",
                    Severity.HIGH: "🟠",
                    Severity.MEDIUM: "🟡",
                    Severity.LOW: "🟢",
                    Severity.INFO: "ℹ️",
                }
                report_lines.append(f"{emoji[severity]} {severity.value.upper()} ({len(issues)} issues)")
                for issue in issues[:10]:  # Limit to 10 per category
                    report_lines.append(f"  - [{issue.category}] {issue.title}")
                    report_lines.append(f"    Location: {issue.file_path}:{issue.line_number}")
                    report_lines.append(f"    Fix: {issue.fix_suggestion}")
                    if len(issues) > 10:
                        report_lines.append(f"  ... and {len(issues) - 10} more")
                report_lines.append("")

        return "\n".join(report_lines)


# Singleton instance
_quality_guard: Optional[CodeQualityGuard] = None


def get_code_quality_guard() -> CodeQualityGuard:
    """Get the global code quality guard instance."""
    global _quality_guard
    if _quality_guard is None:
        _quality_guard = CodeQualityGuard()
    return _quality_guard
