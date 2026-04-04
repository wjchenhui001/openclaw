#!/usr/bin/env python3
"""
OpenClaw 工具标准化系统
"""
from typing import Dict, Any, Callable, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
import json
import inspect

@dataclass
class ToolParameter:
    """工具参数定义"""
    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None

@dataclass
class Tool:
    """工具定义"""
    name: str
    description: str
    function: Callable
    parameters: list = field(default_factory=list)
    category: str = "general"
    requires_confirmation: bool = False

    def to_schema(self) -> Dict[str, Any]:
        properties = {}
        required = []
        for param in self.parameters:
            properties[param.name] = {
                "type": param.type,
                "description": param.description
            }
            if param.default is not None:
                properties[param.name]["default"] = param.default
            if param.required:
                required.append(param.name)
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": properties,
                "required": required
            },
            "category": self.category,
            "requiresConfirmation": self.requires_confirmation
        }

class ToolRegistry:
    """工具注册表 - 单例"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}
        return cls._instance

    def register(self, tool: Tool):
        self._tools[tool.name] = tool
        return self

    def get(self, name: str):
        return self._tools.get(name)

    def list_tools(self):
        return [tool.to_schema() for tool in self._tools.values()]

    def validate_input(self, tool_name: str, input_data: Dict[str, Any]) -> List[str]:
        tool = self.get(tool_name)
        if not tool:
            return [f"Tool '{tool_name}' not found"]
        errors = []
        for param in tool.parameters:
            if param.required and param.name not in input_data:
                errors.append(f"Missing required parameter: {param.name}")
        return errors

registry = ToolRegistry()

def tool(name: str, description: str, category: str = "general", requires_confirmation: bool = False):
    def decorator(func: Callable):
        sig = inspect.signature(func)
        parameters = []
        for param_name, param in sig.parameters.items():
            if param_name in ['self', 'cls']:
                continue
            param_type = "string"
            if param.annotation != inspect.Parameter.empty:
                if param.annotation == str:
                    param_type = "string"
                elif param.annotation == int:
                    param_type = "integer"
                elif param.annotation == bool:
                    param_type = "boolean"
            parameters.append(ToolParameter(
                name=param_name,
                type=param_type,
                description=f"Parameter {param_name}",
                default=param.default if param.default != inspect.Parameter.empty else None,
                required=param.default == inspect.Parameter.empty
            ))
        tool_def = Tool(
            name=name,
            description=description,
            function=func,
            parameters=parameters,
            category=category,
            requires_confirmation=requires_confirmation
        )
        registry.register(tool_def)
        return func
    return decorator

def execute_tool_call(tool_name: str, arguments: Dict[str, Any], auto_confirm: bool = False):
    tool = registry.get(tool_name)
    if not tool:
        return {"status": "error", "error": f"Tool not found: {tool_name}"}
    validation_errors = registry.validate_input(tool_name, arguments)
    if validation_errors:
        return {"status": "error", "error": "; ".join(validation_errors)}
    if tool.requires_confirmation and not auto_confirm:
        return {"status": "error", "error": "Requires confirmation"}
    try:
        result = tool.function(**arguments)
        return {
            "status": "success",
            "result": result,
            "tool": tool_name,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "tool": tool_name,
            "timestamp": datetime.now().isoformat()
        }

__all__ = ['Tool', 'ToolParameter', 'ToolRegistry', 'tool', 'execute_tool_call', 'registry']
