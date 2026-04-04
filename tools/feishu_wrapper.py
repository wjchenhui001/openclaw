#!/usr/bin/env python3
"""
飞书工具集 - 将常用 feishu_* 工具包装为标准工具
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools import tool, registry

# ============================================
# 飞书消息
# ============================================

@tool("feishu_message_send", "发送飞书消息", category="communication", requires_confirmation=False)
def feishu_message_send(target: str, message: str, channel: str = "feishu"):
    """发送消息到飞书（通过 openclaw message）"""
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

# ============================================
# 飞书日历 - 查询事件
# ============================================

@tool("feishu_calendar_list", "列出飞书日历事件", category="communication", requires_confirmation=False)
def feishu_calendar_list(days: int = 7):
    """查询未来 N 天的日历事件"""
    from datetime import datetime, timedelta
    import subprocess
    import json

    now = datetime.now()
    end = now + timedelta(days=days)

    # 使用 openclaw 的 feishu_calendar_event 工具
    # 这里简化：调用 python 脚本或 API
    return {
        "status": "success",
        "period": f"{now.date()} to {end.date()}",
        "events": [],  # 实际实现需要调用 feishu API
        "note": "Implementation pending"
    }

# ============================================
# 飞书文档 - 读取
# ============================================

@tool("feishu_doc_read", "读取飞书云文档", category="file", requires_confirmation=False)
def feishu_doc_read(doc_id: str):
    """获取飞书文档内容（Markdown）"""
    try:
        # 延迟导入避免循环
        from feishu_fetch_doc import feishu_fetch_doc
        result = feishu_fetch_doc(doc_id=doc_id)
        return result
    except Exception as e:
        raise RuntimeError(f"Failed to fetch doc: {e}")

# ============================================
# 飞书多维表格 - 读取记录
# ============================================

@tool("feishu_bitable_list", "列出多维表格记录", category="database", requires_confirmation=False)
def feishu_bitable_list(app_token: str, table_id: str, page_size: int = 50):
    """查询多维表格记录"""
    try:
        from feishu_bitable_app_table_record import feishu_bitable_app_table_record
        result = feishu_bitable_app_table_record(
            action="list",
            app_token=app_token,
            table_id=table_id,
            page_size=page_size
        )
        return result
    except Exception as e:
        raise RuntimeError(f"Failed to list records: {e}")

# ============================================
# 飞书搜索用户
# ============================================

@tool("feishu_search_user", "搜索飞书用户", category="communication", requires_confirmation=False)
def feishu_search_user(query: str):
    """根据姓名/邮箱搜索用户"""
    try:
        from feishu_search_user import feishu_search_user
        result = feishu_search_user(query=query)
        return result
    except Exception as e:
        raise RuntimeError(f"Failed to search user: {e}")

# ============================================
# 注册完成提示
# ============================================

if __name__ == "__main__":
    print("📦 飞书工具集已注册")
    print(f"✅ Tools: {', '.join([t.name for t in registry._tools.values()])}")
    print("\n📋 Schema:")
    for name in ['feishu_message_send', 'feishu_doc_read']:
        tool = registry.get(name)
        if tool:
            print(f"\n### {name}")
            import json
            print(json.dumps(tool.to_schema(), indent=2, ensure_ascii=False))
