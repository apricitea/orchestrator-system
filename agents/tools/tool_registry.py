"""
Tool Registry

Central registry for all agent tools.
Provides discovery and access to available tools.
"""

from typing import Any, Dict, List

from agents.tools.code_executor import CodeExecutorTool
from agents.tools.command_runner import CommandRunnerTool
from agents.tools.file_ops import FileOpsTool
from utils.logger import get_logger


class ToolRegistry:
    """
    Registry for all available tools.

    Agents can query this registry to find available tools
    and execute them safely.
    """

    def __init__(self):
        """Initialize tool registry."""
        self.logger = get_logger("tool_registry")
        self._tools: Dict[str, Any] = {}

        # Register core tools
        self._register_core_tools()

    def _register_core_tools(self):
        """Register core tools that are always available."""
        self.register("file_ops", FileOpsTool())
        self.register("command_runner", CommandRunnerTool())
        self.register("code_executor", CodeExecutorTool())

    def register(self, name: str, tool: Any) -> None:
        """
        Register a tool.

        Args:
            name: Tool name
            tool: Tool instance
        """
        self._tools[name] = tool
        self.logger.info("Tool registered", tool=name)

    def unregister(self, name: str) -> None:
        """
        Unregister a tool.

        Args:
            name: Tool name
        """
        if name in self._tools:
            del self._tools[name]
            self.logger.info("Tool unregistered", tool=name)

    def get(self, name: str) -> Any:
        """
        Get a tool by name.

        Args:
            name: Tool name

        Returns:
            Tool instance or None
        """
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        """
        List all available tools.

        Returns:
            List of tool names
        """
        return list(self._tools.keys())

    def get_tool_info(self, name: str) -> Dict[str, Any]:
        """
        Get information about a tool.

        Args:
            name: Tool name

        Returns:
            Tool information
        """
        tool = self.get(name)
        if tool is None:
            return {
                "name": name,
                "available": False,
            }

        # Get tool methods
        methods = []
        for attr_name in dir(tool):
            if not attr_name.startswith("_") and callable(getattr(tool, attr_name)):
                methods.append(attr_name)

        return {
            "name": name,
            "available": True,
            "type": type(tool).__name__,
            "methods": methods,
        }

    async def execute_tool(
        self,
        tool_name: str,
        method: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Execute a tool method.

        Args:
            tool_name: Name of the tool
            method: Method name to call
            **kwargs: Arguments to pass to method

        Returns:
            Result from tool method
        """
        tool = self.get(tool_name)
        if tool is None:
            return {
                "success": False,
                "error": f"Tool not found: {tool_name}",
            }

        if not hasattr(tool, method):
            return {
                "success": False,
                "error": f"Tool {tool_name} has no method: {method}",
            }

        tool_method = getattr(tool, method)

        try:
            # Check if method is async
            import asyncio
            if asyncio.iscoroutinefunction(tool_method):
                result = await tool_method(**kwargs)
            else:
                result = tool_method(**kwargs)

            return {
                "success": True,
                "tool": tool_name,
                "method": method,
                "result": result,
            }

        except Exception as e:
            self.logger.error(
                "Tool execution failed",
                tool=tool_name,
                method=method,
                error=str(e),
            )

            return {
                "success": False,
                "error": str(e),
                "tool": tool_name,
                "method": method,
            }

    def get_all_tools_info(self) -> Dict[str, Dict[str, Any]]:
        """
        Get information about all tools.

        Returns:
            Dictionary mapping tool names to info
        """
        info = {}
        for tool_name in self.list_tools():
            info[tool_name] = self.get_tool_info(tool_name)
        return info


# Global tool registry
_tool_registry: ToolRegistry = None


def get_tool_registry() -> ToolRegistry:
    """Get the global tool registry."""
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry()
    return _tool_registry
