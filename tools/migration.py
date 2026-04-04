#!/usr/bin/env python3
"""
工具迁移脚本 - 注册标准化工具并生成报告
"""
import sys
import json
from pathlib import Path

# 添加 workspace/tools 到路径
workspace = Path(__file__).parent.parent
sys.path.insert(0, str(workspace))

# 导入工具系统（从 __init__.py）
import importlib.util
spec = importlib.util.spec_from_file_location("tools", workspace / "tools" / "__init__.py")
tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tools)

tool = tools.tool
registry = tools.registry

# ============================================
# 注册工具
# ============================================

@tool("file_write", "写入文件（覆盖）", category="file", requires_confirmation=True)
def file_write(file: str, content: str):
    p = Path(file)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding='utf-8')
    return {"status": "success", "file": str(p.absolute()), "size": p.stat().st_size}

@tool("feishu_message_send", "发送飞书消息", category="communication", requires_confirmation=False)
def feishu_message_send(target: str, message: str, channel: str = "feishu"):
    import subprocess
    result = subprocess.run(
        ['openclaw', 'message', 'send', '--channel', channel,
         '--target', target, '--message', message],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode == 0:
        return {"status": "success", "output": result.stdout.strip()}
    else:
        raise RuntimeError(f"Send failed: {result.stderr}")

@tool("web_search", "搜索网络（Brave Search）", category="research", requires_confirmation=False)
def web_search(query: str, count: int = 10):
    from web_search import web_search as search_func
    results = search_func(query=query, count=count)
    return {"status": "success", "query": query, "count": len(results), "results": results}

@tool("git_commit", "提交更改到 Git", category="development", requires_confirmation=True)
def git_commit(message: str, push: bool = False):
    import subprocess
    ws = workspace
    subprocess.run(['git', 'add', '-A'], cwd=ws, check=True, capture_output=True)
    result = subprocess.run(['git', 'commit', '-m', message], cwd=ws, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Commit failed: {result.stderr}")
    commit_hash = extract_commit_hash(result.stdout)
    pushed = False
    if push:
        push_result = subprocess.run(['git', 'push'], cwd=ws, capture_output=True, text=True)
        pushed = push_result.returncode == 0
        if not pushed:
            raise RuntimeError(f"Push failed: {push_result.stderr}")
    return {"status": "success", "commit": commit_hash, "message": message, "pushed": pushed}

def extract_commit_hash(output: str) -> str:
    import re
    match = re.search(r'\[[^\s]+ ([a-f0-9]+)\]', output)
    return match.group(1) if match else "unknown"

# ============================================
# 输出报告
# ============================================

if __name__ == "__main__":
    print("📦 工具标准化迁移完成")
    print(f"✅ 已注册工具: {', '.join(registry._tools.keys())}")
    print("\n📋 Schema 示例:")
    for name in ['file_write', 'web_search']:
        tool_obj = registry.get(name)
        if tool_obj:
            print(f"\n### {name}")
            print(json.dumps(tool_obj.to_schema(), indent=2, ensure_ascii=False))

    # 测试执行一个工具（web_search）
    print("\n🧪 测试执行:")
    test_result = registry.get("web_search")
    if test_result:
        print(f"  - {test_result.name}: 等待实际调用...")
