#!/usr/bin/env python3
"""
批量注册所有 OpenClaw 工具到新标准化系统
"""
import sys
from pathlib import Path

# 确保 workspace 根目录在路径
workspace = Path(__file__).parent.parent
sys.path.insert(0, str(workspace))

from tools import registry

def run_registration():
    print("📦 开始批量工具注册...\n")

    before = len(registry._tools)

    # 1. 核心工具
    print("1️⃣ 迁移核心工具...")
    try:
        import tools.migration  # noqa
        core = ['file_write', 'feishu_message_send', 'web_search', 'git_commit']
        print(f"   ✅ 核心工具 ({len(core)}): {', '.join(core)}")
    except Exception as e:
        print(f"   ❌ 失败: {e}")

    # 2. 飞书工具
    print("\n2️⃣ 注册飞书工具...")
    try:
        import tools.feishu_wrapper  # noqa
        feishu = [t for t in registry._tools.keys() if t.startswith('feishu_')]
        print(f"   ✅ 飞书工具 ({len(feishu)}): {', '.join(feishu)}")
    except Exception as e:
        print(f"   ❌ 失败: {e}")

    # 3. 文档工具
    print("\n3️⃣ 注册文档工具...")
    try:
        import tools.document_tools  # noqa
        doc = [t for t in registry._tools.keys() if any(k in t for k in ['pdf_', 'docx_', 'xlsx_'])]
        print(f"   ✅ 文档工具 ({len(doc)}): {', '.join(doc)}")
    except Exception as e:
        print(f"   ❌ 失败: {e}")

    # 4. 附加工具（浏览器、Shell、Memory等）
    print("\n4️⃣ 注册附加工具...")
    try:
        import tools.additional_tools  # noqa
        additional = [
            'browser_open', 'browser_snapshot',
            'shell_exec',
            'memory_search', 'memory_write',
            'find_skills',
            'self_improve_log',
            'ocr_recognize'
        ]
        # 过滤已注册的
        new_added = [t for t in additional if t in registry._tools]
        print(f"   ✅ 附加工具 ({len(new_added)}): {', '.join(new_added)}")
    except Exception as e:
        print(f"   ❌ 失败: {e}")

    # 汇总
    total = len(registry._tools)
    added = total - before
    print(f"\n✅ 注册完成！总计 {total} 个工具（新增 {added} 个）")

    # 输出摘要
    print("\n" + "="*60)
    print("📋 工具分类统计:")
    categories = {}
    for tool in registry._tools.values():
        cat = tool.category
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(tool.name)

    for cat, names in sorted(categories.items()):
        print(f"  {cat:20s} ({len(names)}): {', '.join(sorted(names))}")

    print("\n🎉 系统就绪！可通过 `from tools import registry` 访问")
    print("   使用: registry.list_tools() 查看所有工具 Schema")

if __name__ == "__main__":
    run_registration()
