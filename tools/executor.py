#!/usr/bin/env python3
"""
Tool Executor - 受 Claude Code CLI 启发的工具执行系统
支持: 并行执行、智能确认、错误分类、结果合并
"""
import asyncio
import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass, field

# 添加 workspace 到路径，以便导入 tools
sys.path.insert(0, str(Path(__file__).parent.parent))

# 导入工具注册表
from tools import ToolRegistry, registry as global_registry

@dataclass
class ToolUse:
    """工具调用请求"""
    name: str
    arguments: Dict[str, Any]
    id: Optional[str] = None
    index: int = 0

@dataclass
class ToolResult:
    """工具执行结果"""
    tool_use_id: str
    tool_name: str
    status: str  # success, error, cancelled
    content: Any
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

class ToolExecutor:
    """工具执行器 - 核心类"""

    def __init__(self, auto_confirm: bool = False, max_retries: int = 2):
        self.auto_confirm = auto_confirm
        self.max_retries = max_retries
        self.confirmation_policy = {
            "file_write": "always",
            "file_delete": "always",
            "shell_exec": "always",
            "git_commit": "always",
            "feishu_message_send": "never",
            "web_search": "never",
        }
        self.registry = global_registry

    def _classify_error(self, error: Exception) -> str:
        """错误分类 - 决定是否重试"""
        error_str = str(error).lower()
        if any(kw in error_str for kw in ['timeout', 'connection', 'network', 'econnreset']):
            return "NETWORK"
        if any(kw in error_str for kw in ['429', 'too many requests', 'rate limit', 'quota', 'overloaded']):
            return "RATE_LIMIT"
        if any(kw in error_str for kw in ['unavailable', 'maintenance', 'service down']):
            return "SERVICE"
        return "FATAL"

    def needs_confirmation(self, tool_name: str, arguments: Dict[str, Any]) -> bool:
        policy = self.confirmation_policy.get(tool_name, "never")
        if policy == "never":
            return False
        if self.auto_confirm:
            return False
        if policy == "always":
            return True
        if policy == "dangerous":
            return self._is_dangerous(arguments)
        return False

    def _is_dangerous(self, arguments: Dict[str, Any]) -> bool:
        if 'file' in arguments:
            file_path = arguments['file']
            sensitive = ['/etc/', '/var/', '/usr/local/', '~/.ssh/', '/root/']
            if any(file_path.startswith(p) for p in sensitive):
                return True
        if 'command' in arguments:
            cmd = arguments['command']
            dangerous_keywords = ['rm -rf', 'sudo', 'chmod 777', 'dd if=', ':(){ :|:& };']
            if any(kw in cmd for kw in dangerous_keywords):
                return True
        return False

    async def execute(self, tool_use: ToolUse) -> ToolResult:
        tool = self.registry.get(tool_use.name)
        if not tool:
            return ToolResult(
                tool_use_id=tool_use.id or "",
                tool_name=tool_use.name,
                status="error",
                content=None,
                error=f"Tool not found: {tool_use.name}"
            )

        if self.needs_confirmation(tool_use.name, tool_use.arguments):
            return ToolResult(
                tool_use_id=tue.id or "",
                tool_name=tool_use.name,
                status="cancelled",
                content=None,
                error="Requires user confirmation (dangerous operation)"
            )

        last_exception = None
        for attempt in range(self.max_retries + 1):
            try:
                result = tool.function(**tool_use.arguments)
                return ToolResult(
                    tool_use_id=tool_use.id or "",
                    tool_name=tool_use.name,
                    status="success",
                    content=result,
                    metadata={"attempt": attempt + 1}
                )
            except Exception as e:
                last_exception = e
                category = self._classify_error(e)

                if attempt < self.max_retries and category in ["NETWORK", "RATE_LIMIT", "SERVICE"]:
                    backoff = 2 ** attempt
                    await asyncio.sleep(backoff)
                else:
                    break

        return ToolResult(
            tool_use_id=tool_use.id or "",
            tool_name=tool_use.name,
            status="error",
            content=None,
            error=str(last_exception),
            metadata={"attempts": self.max_retries + 1, "category": self._classify_error(last_exception)}
        )

    async def execute_batch(self, tool_uses: List[ToolUse]) -> List[ToolResult]:
        tasks = [self.execute(tue) for tue in tool_uses]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed = []
        for tue, result in zip(tool_uses, results):
            if isinstance(result, Exception):
                processed.append(ToolResult(
                    tool_use_id=tue.id or "",
                    tool_name=tue.name,
                    status="error",
                    content=None,
                    error=str(result)
                ))
            else:
                processed.append(result)
        return processed

    def format_result_for_llm(self, result: ToolResult) -> Dict[str, Any]:
        if result.status == "success":
            return {
                "type": "tool_result",
                "tool_use_id": result.tool_use_id,
                "content": {
                    "text": json.dumps(result.content, ensure_ascii=False, indent=2)
                }
            }
        else:
            return {
                "type": "tool_result",
                "tool_use_id": result.tool_use_id,
                "content": {
                    "text": f"Error: {result.error}"
                },
                "is_error": True
            }

# 如果 tools/__init__.py 没有导出 ToolUse/ToolResult，需要在这里定义
if 'ToolUse' not in globals():
    from dataclasses import dataclass
    @dataclass
    class ToolUse:
        name: str
        arguments: Dict[str, Any]
        id: str = None
        index: int = 0

    @dataclass
    class ToolResult:
        tool_use_id: str
        tool_name: str
        status: str
        content: Any
        error: Optional[str] = None
        metadata: Dict[str, Any] = None

        def __post_init__(self):
            if self.metadata is None:
                self.metadata = {}

# 快速测试
if __name__ == "__main__":
    async def test():
        executor = ToolExecutor(auto_confirm=True)
        results = await executor.execute_batch([
            ToolUse(name="web_search", arguments={"query": "OpenClaw AI", "count": 5}, id="call-1")
        ])
        print("=== 测试执行结果 ===")
        for res in results:
            print(f"Tool: {res.tool_name}, Status: {res.status}")
            if res.status == "success" and isinstance(res.content, dict):
                print(f"Result keys: {list(res.content.keys())}")
            if res.error:
                print(f"Error: {res.error}")
            print()
