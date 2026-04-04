#!/usr/bin/env python3
"""
OpenClaw 工具标准化系统
"""
from typing import Dict, Any, Callable, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
import json
import inspect
import sys
from pathlib import Path

# 确保 tools/ 所在目录在 Python 路径中
TOOLS_DIR = Path(__file__).parent.resolve()
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

# ============================================
# 数据类
# ============================================

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
    parameters: List[ToolParameter] = field(default_factory=list)
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
    """工具注册表 - 单例模式"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}
        return cls._instance

    def register(self, tool: Tool):
        self._tools[tool.name] = tool
        return self

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
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

# 全局注册表
registry = ToolRegistry()

def tool(name: str, description: str, category: str = "general", requires_confirmation: bool = False):
    """装饰器：注册函数为标准化工具"""
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

def execute_tool_call(tool_name: str, arguments: Dict[str, Any], auto_confirm: bool = False) -> Dict[str, Any]:
    """执行工具调用（简单版本，无重试）"""
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

# 导出
__all__ = [
    'Tool', 'ToolParameter', 'ToolRegistry',
    'tool', 'execute_tool_call', 'registry'
]

# 自动加载所有工具模块（延迟导入）
def _load_all_tools():
    """导入所有工具子模块，触发 @tool 装饰器注册"""
    import importlib
    import pkgutil

    # 获取当前包的所有子模块（排除 __init__）
    package_name = __name__
    for _, mod_name, is_pkg in pkgutil.iter_modules(__path__):
        if mod_name.startswith('__'):
            continue
        try:
            importlib.import_module(f"{package_name}.{mod_name}")
        except Exception as e:
            print(f"[tools] Warning: failed to load module {mod_name}: {e}", file=sys.stderr)

# 立即加载
_load_all_tools()
