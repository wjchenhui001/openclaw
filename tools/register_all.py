#!/usr/bin/env python3
"""
批量注册所有 OpenClaw 工具到新标准化系统
"""
import sys
from pathlib import Path

# 将 workspace 根目录加入路径（而非 tools/）
workspace = Path(__file__).parent.parent
sys.path.insert(0, str(workspace))

# 现在可以导入 tools 包
from tools import registry

print("📦 开始批量工具注册...")

before = len(registry._tools)

# 1. 迁移核心工具（这会注册 4 个工具）
print("\n1️⃣ 迁移核心工具...")
try:
    import tools.migration  # noqa
    print(f"   ✅ 核心工具: {', '.join([t for t in registry._tools.keys() if t in ['file_write', 'feishu_message_send', 'web_search', 'git_commit']])}")
except Exception as e:
    print(f"   ❌ 核心工具迁移失败: {e}")

# 2. 飞书工具
print("\n2️⃣ 注册飞书工具...")
try:
    import tools.feishu_wrapper  # noqa
    feishu_tools = [t for t in registry._tools.keys() if t.startswith('feishu_')]
    print(f"   ✅ 飞书工具 ({len(feishu_tools)}): {', '.join(feishu_tools)}")
except Exception as e:
    print(f"   ❌ 飞书工具注册失败: {e}")

# 3. 文档工具
print("\n3️⃣ 注册文档工具...")
try:
    import tools.document_tools  # noqa
    doc_tools = [t for t in registry._tools.keys() if any(k in t for k in ['pdf_', 'docx_', 'xlsx_'])]
    print(f"   ✅ 文档工具 ({len(doc_tools)}): {', '.join(doc_tools)}")
except Exception as e:
    print(f"   ❌ 文档工具注册失败: {e}")

# 汇总
total = len(registry._tools)
print(f"\n✅ 注册完成！总计 {total} 个工具（新增 {total - before} 个）")

# 列出所有工具
print("\n📋 所有工具清单:")
for i, name in enumerate(sorted(registry._tools.keys()), 1):
    tool = registry.get(name)
    print(f"  {i:2d}. {name:25s} [{tool.category}] {'(需确认)' if tool.requires_confirmation else ''}")

# 输出部分 Schema 示例
print("\n📝 Schema 示例（3 个工具）:")
import json
for name in ['file_write', 'web_search', 'pdf_extract_text']:
    tool = registry.get(name)
    if tool:
        print(f"\n### {name}")
        print(json.dumps(tool.to_schema(), indent=2, ensure_ascii=False))

print("\n🎉 系统就绪！可通过 tools.registry 访问")
