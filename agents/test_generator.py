"""
Automated Test Generation Agent

Based on SkillsMP unit-test-writer skill patterns:
- Generates comprehensive unit tests
- Covers edge cases and error conditions
- Uses proper mocking for external dependencies
- Enforces coverage thresholds
- Supports pytest and unittest frameworks
"""

import ast
import inspect
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from enum import Enum

from utils.logger import get_logger


class TestFramework(Enum):
    """Supported test frameworks."""
    PYTEST = "pytest"
    UNittest = "unittest"


class TestType(Enum):
    """Types of tests to generate."""
    UNIT = "unit"
    INTEGRATION = "integration"
    EDGE_CASE = "edge_case"
    ERROR_HANDLING = "error_handling"


@dataclass
class TestFunction:
    """Represents a test function to generate."""
    name: str
    description: str
    test_type: TestType
    setup_code: str
    test_code: str
    assertions: List[str]
    teardown_code: str = ""


@dataclass
class FunctionInfo:
    """Information extracted from a source function."""
    name: str
    parameters: List[Tuple[str, str]]  # (name, type_hint)
    return_type: Optional[str]
    docstring: Optional[str]
    source_code: str
    file_path: str
    line_number: int
    is_async: bool
    exceptions_raised: Set[str]
    external_calls: Set[str]


class TestGenerator:
    """
    Generates comprehensive unit tests from source code.

    Based on SkillsMP best practices:
    - Test happy path
    - Test edge cases (empty, None, boundary values)
    - Test error conditions
    - Use fixtures for setup
    - Mock external dependencies
    """

    def __init__(self, framework: TestFramework = TestFramework.PYTEST):
        """
        Initialize test generator.

        Args:
            framework: Test framework to use (pytest or unittest)
        """
        self.framework = framework
        self.logger = get_logger("test_generator")

    def analyze_source_file(self, file_path: str) -> List[FunctionInfo]:
        """
        Analyze a Python source file and extract function information.

        Args:
            file_path: Path to the Python file to analyze

        Returns:
            List of function information objects
        """
        self.logger.logger.info("Analyzing source file", path=file_path)

        with open(file_path, 'r') as f:
            source = f.read()

        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            self.logger.logger.error("Failed to parse source file", error=str(e))
            return []

        functions = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Skip private functions and test functions
                if node.name.startswith('_') or node.name.startswith('test_'):
                    continue

                func_info = self._extract_function_info(node, source, file_path)
                functions.append(func_info)

        self.logger.logger.info("Extracted functions", count=len(functions))
        return functions

    def _extract_function_info(
        self,
        node: ast.FunctionDef,
        source: str,
        file_path: str
    ) -> FunctionInfo:
        """Extract information from a function AST node."""
        # Extract parameters
        parameters = []
        for arg in node.args.args:
            param_name = arg.arg
            param_type = None
            if arg.annotation:
                param_type = ast.unparse(arg.annotation)
            parameters.append((param_name, param_type))

        # Extract return type
        return_type = None
        if node.returns:
            return_type = ast.unparse(node.returns)

        # Extract docstring
        docstring = ast.get_docstring(node)

        # Extract source code
        source_code = ast.unparse(node)

        # Check if async
        is_async = isinstance(node, ast.AsyncFunctionDef)

        # Find exceptions raised
        exceptions_raised = self._find_exceptions_raised(node)

        # Find external calls
        external_calls = self._find_external_calls(node)

        return FunctionInfo(
            name=node.name,
            parameters=parameters,
            return_type=return_type,
            docstring=docstring,
            source_code=source_code,
            file_path=file_path,
            line_number=node.lineno,
            is_async=is_async,
            exceptions_raised=exceptions_raised,
            external_calls=external_calls
        )

    def _find_exceptions_raised(self, node: ast.FunctionDef) -> Set[str]:
        """Find exception types raised in the function."""
        exceptions = set()

        for child in ast.walk(node):
            if isinstance(child, ast.Raise):
                if child.exc:
                    if isinstance(child.exc, ast.Name):
                        exceptions.add(child.exc.id)
                    elif isinstance(child.exc, ast.Call) and isinstance(child.exc.func, ast.Name):
                        exceptions.add(child.exc.func.id)

        return exceptions

    def _find_external_calls(self, node: ast.FunctionDef) -> Set[str]:
        """Find potential external API/library calls."""
        external = set()

        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Attribute):
                    # method calls like requests.get()
                    external.add(child.func.attr)
                elif isinstance(child.func, ast.Name):
                    # direct calls like print()
                    external.add(child.func.id)

        return external

    def generate_tests(self, func_info: FunctionInfo) -> List[TestFunction]:
        """
        Generate comprehensive tests for a function.

        Args:
            func_info: Function information

        Returns:
            List of test functions
        """
        tests = []

        # 1. Happy path test
        tests.append(self._generate_happy_path_test(func_info))

        # 2. Edge case tests
        tests.extend(self._generate_edge_case_tests(func_info))

        # 3. Error handling tests
        if func_info.exceptions_raised:
            tests.extend(self._generate_error_handling_tests(func_info))

        # 4. Type validation tests
        if func_info.parameters:
            tests.append(self._generate_type_validation_test(func_info))

        return tests

    def _generate_happy_path_test(self, func_info: FunctionInfo) -> TestFunction:
        """Generate a test for the happy path."""
        param_names = [p[0] for p in func_info.parameters]

        # Create sample values based on types
        test_values = self._create_test_values(func_info.parameters)

        # Build test code
        setup_code = self._generate_setup_code(func_info)

        if func_info.is_async:
            test_code = f"""
async def test_{func_info.name}_success():
    '''Test {func_info.name} with valid inputs returns expected result'''
    {setup_code}

    result = await {func_info.name}({', '.join(f'{k}={v}' for k, v in test_values.items())})

    assert result is not None
    # Add specific assertions based on expected behavior
"""
        else:
            test_code = f"""
def test_{func_info.name}_success():
    '''Test {func_info.name} with valid inputs returns expected result'''
    {setup_code}

    result = {func_info.name}({', '.join(f'{k}={v}' for k, v in test_values.items())})

    assert result is not None
    # Add specific assertions based on expected behavior
"""

        return TestFunction(
            name=f"test_{func_info.name}_success",
            description=f"Test {func_info.name} with valid inputs",
            test_type=TestType.UNIT,
            setup_code=setup_code,
            test_code=test_code.strip(),
            assertions=["assert result is not None"]
        )

    def _generate_edge_case_tests(self, func_info: FunctionInfo) -> List[TestFunction]:
        """Generate edge case tests."""
        tests = []
        param_names = [p[0] for p in func_info.parameters]

        # Empty/None tests
        for param_name, param_type in func_info.parameters:
            if param_type in ['str', 'Optional[str]', 'Any', None]:
                test_code = f"""
def test_{func_info.name}_with_empty_{param_name}():
    '''Test {func_info.name} handles empty {param_name} gracefully'''
    result = {func_info.name}({param_name}='')
    # Assert behavior for empty input
"""
                tests.append(TestFunction(
                    name=f"test_{func_info.name}_empty_{param_name}",
                    description=f"Test empty {param_name}",
                    test_type=TestType.EDGE_CASE,
                    setup_code="",
                    test_code=test_code.strip(),
                    assertions=[]
                ))

            if param_type in ['Optional[str]', 'Optional[int]', 'Any', None]:
                test_code = f"""
def test_{func_info.name}_with_none_{param_name}():
    '''Test {func_info.name} handles None {param_name} gracefully'''
    result = {func_info.name}({param_name}=None)
    # Assert behavior for None input
"""
                tests.append(TestFunction(
                    name=f"test_{func_info.name}_none_{param_name}",
                    description=f"Test None {param_name}",
                    test_type=TestType.EDGE_CASE,
                    setup_code="",
                    test_code=test_code.strip(),
                    assertions=[]
                ))

        # Boundary value tests for numeric parameters
        for param_name, param_type in func_info.parameters:
            if param_type in ['int', 'float', 'Optional[int]', 'Optional[float]']:
                test_code = f"""
def test_{func_info.name}_boundary_values():
    '''Test {func_info.name} with boundary values for {param_name}'''
    # Test with 0
    result1 = {func_info.name}({param_name}=0)

    # Test with negative value
    result2 = {func_info.name}({param_name}=-1)

    # Test with large value
    result3 = {func_info.name}({param_name}=999999)

    # Assert behavior for boundary values
"""
                tests.append(TestFunction(
                    name=f"test_{func_info.name}_boundary_values",
                    description=f"Test boundary values",
                    test_type=TestType.EDGE_CASE,
                    setup_code="",
                    test_code=test_code.strip(),
                    assertions=[]
                ))

        return tests

    def _generate_error_handling_tests(self, func_info: FunctionInfo) -> List[TestFunction]:
        """Generate error handling tests."""
        tests = []

        for exception in func_info.exceptions_raised:
            test_code = f"""
def test_{func_info.name}_raises_{exception.lower()}():
    '''Test {func_info.name} raises {exception} on invalid input'''
    import pytest
    from {exception} import {exception}

    with pytest.raises({exception}):
        {func_info.name}(invalid_input='trigger_error')
"""
            tests.append(TestFunction(
                name=f"test_{func_info.name}_raises_{exception.lower()}",
                description=f"Test {exception} is raised",
                test_type=TestType.ERROR_HANDLING,
                setup_code="",
                test_code=test_code.strip(),
                assertions=[]
            ))

        return tests

    def _generate_type_validation_test(self, func_info: FunctionInfo) -> List[TestFunction]:
        """Generate type validation tests."""
        tests = []

        test_code = f"""
def test_{func_info.name}_type_validation():
    '''Test {func_info.name} validates input types'''
    import pytest

    # Test with wrong type for first parameter
    with pytest.raises((TypeError, ValueError)):
        {func_info.name}({func_info.parameters[0][0]}=None)
"""
        tests.append(TestFunction(
            name=f"test_{func_info.name}_type_validation",
            description=f"Test type validation",
            test_type=TestType.UNIT,
            setup_code="",
            test_code=test_code.strip(),
            assertions=[]
        ))

        return tests

    def _create_test_values(self, parameters: List[Tuple[str, str]]) -> Dict[str, str]:
        """Create test values based on parameter types."""
        values = {}

        for param_name, param_type in parameters:
            if param_type == 'str':
                values[param_name] = '"test_value"'
            elif param_type == 'int':
                values[param_name] = '42'
            elif param_type == 'float':
                values[param_name] = '3.14'
            elif param_type == 'bool':
                values[param_name] = 'True'
            elif param_type and 'List' in param_type:
                values[param_name] = '[]'
            elif param_type and 'Dict' in param_type:
                values[param_name] = '{}'
            elif param_type and 'Optional' in param_type:
                # Use the non-None type
                inner_type = param_type.replace('Optional[', '').replace(']', '')
                if inner_type == 'str':
                    values[param_name] = '"test_value"'
                else:
                    values[param_name] = 'None'
            else:
                values[param_name] = 'None'

        return values

    def _generate_setup_code(self, func_info: FunctionInfo) -> str:
        """Generate setup code for tests (fixtures, mocks, etc.)."""
        setup_lines = []

        # Add imports for external calls
        if 'requests' in func_info.external_calls:
            setup_lines.append("    from unittest.mock import patch, Mock")
            setup_lines.append("    mock_response = Mock()")
            setup_lines.append("    mock_response.status_code = 200")
            setup_lines.append("    mock_response.json.return_value = {}")

        if func_info.external_calls:
            if 'requests' not in func_info.external_calls:
                setup_lines.append("    from unittest.mock import patch, Mock")

        return '\n'.join(setup_lines)

    def generate_test_file(
        self,
        source_file: str,
        output_file: Optional[str] = None
    ) -> str:
        """
        Generate a complete test file from source code.

        Args:
            source_file: Path to source Python file
            output_file: Optional output file path

        Returns:
            Generated test file content
        """
        functions = self.analyze_source_file(source_file)

        if not functions:
            self.logger.logger.warning("No functions found to test")
            return ""

        # Generate module name
        module_name = Path(source_file).stem
        if output_file is None:
            output_file = f"test_{module_name}.py"

        # Build test file content
        lines = []

        # Header
        lines.append('"""')
        lines.append(f'Auto-generated tests for {module_name}')
        lines.append('"""')
        lines.append('')
        lines.append('import pytest')
        lines.append('from unittest.mock import patch, Mock, MagicMock')
        lines.append('')
        lines.append(f'from {module_name} import {", ".join(f.name for f in functions)}')
        lines.append('')

        # Generate tests for each function
        for func_info in functions:
            tests = self.generate_tests(func_info)

            for test in tests:
                lines.append('#' * 70)
                lines.append(f'# {test.description}')
                lines.append('#' * 70)
                lines.append(test.test_code)
                lines.append('')

        # Add pytest fixtures at the end
        lines.append('')
        lines.append('# Pytest Fixtures')
        lines.append('@pytest.fixture')
        lines.append('def sample_data():')
        lines.append('    """Provide sample test data"""')
        lines.append('    return {}')
        lines.append('')
        lines.append('@pytest.fixture')
        lines.append('def mock_client():')
        lines.append('    """Mock external API client"""')
        lines.append('    client = Mock()')
        lines.append('    return client')
        lines.append('')

        content = '\n'.join(lines)

        # Write to file if output specified
        if output_file:
            with open(output_file, 'w') as f:
                f.write(content)
            self.logger.logger.info("Generated test file", output=output_file)

        return content

    def generate_coverage_config(self, project_root: str) -> str:
        """
        Generate pytest coverage configuration.

        Args:
            project_root: Root directory of project

        Returns:
            Configuration file content
        """
        config = f"""# pytest.ini - Pytest configuration with coverage
[tool:pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*

# Coverage settings
addopts =
    --cov=.
    --cov-report=html
    --cov-report=term-missing
    --cov-fail-under=80

# Ignore patterns
ignore =
    */tests/*
    */test_*
    */__pycache__/*
    */migrations/*

# Minimum coverage
[coverage:report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise AssertionError
    raise NotImplementedError
    if __name__ == .__main__.:
    if TYPE_CHECKING:
"""
        return config


# Singleton instance
_test_generator: Optional[TestGenerator] = None


def get_test_generator(framework: TestFramework = TestFramework.PYTEST) -> TestGenerator:
    """Get the global test generator instance."""
    global _test_generator
    if _test_generator is None:
        _test_generator = TestGenerator(framework)
    return _test_generator
