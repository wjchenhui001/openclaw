#!/usr/bin/env python3
"""
OpenClaw 工具标准化系统
"""
from typing import Dict, Any, Callable, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
import json
import inspect

# 导出
__all__ = ['Tool', 'ToolParameter', 'ToolRegistry', 'tool', 'execute_tool_call', 'registry']

# 实现将在下面定义

# 全局注册表单例
_registry_instance = None

def _get_registry():
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = ToolRegistry()
    return _registry_instance

# 延迟定义类，避免循环导入
class ToolParameter:
    def __init__(self, name: str, type: str, description: str, required: bool = True, default: Any = None):
        self.name = name
        self.type = type
        self.description = description
        self.required = required
        self.default = default

class Tool:
    def __init__(self, name: str, description: str, function: Callable, parameters: list = None,
                 category: str = "general", requires_confirmation: bool = False):
        self.name = name
        self.description = description
        self.function = function
        self.parameters = parameters or []
        self.category = category
        self.requires_confirmation = requires_confirmation

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
    def __init__(self):
        self._tools = {}

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

# 全局注册表实例
registry = _get_registry()

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
                elif param.annotation == float:
                    param_type = "number"
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
