#!/usr/bin/env python3
"""
附加工具集 - 迁移剩余 OpenClaw 技能到标准化工具
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools import tool, registry

# ============================================
# Browser 工具
# ============================================

@tool("browser_open", "打开网页", category="browser", requires_confirmation=False)
def browser_open(url: str):
    """打开 URL 在浏览器中（仅打开，不交互）"""
    import subprocess
    import os

    # 根据平台打开浏览器
    try:
        if sys.platform == "darwin":  # macOS
            subprocess.run(["open", url], check=True)
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", url], check=True)
        elif sys.platform == "win32":
            os.startfile(url)  # Windows only
        else:
            raise RuntimeError(f"Unsupported platform: {sys.platform}")
        return {"status": "success", "url": url}
    except Exception as e:
        raise RuntimeError(f"Failed to open browser: {e}")

@tool("browser_snapshot", "获取网页截图", category="browser", requires_confirmation=False)
def browser_snapshot(url: str = None, target: str = "host"):
    """获取浏览器当前页面的截图（需浏览器已启动）"""
    try:
        # 调用 openclaw browser 工具
        from browser import browser
        result = browser(action="snapshot", target=target, url=url)
        return {"status": "success", "result": result}
    except Exception as e:
        raise RuntimeError(f"Browser snapshot failed: {e}")

# ============================================
# Shell/Exec 工具
# ============================================

@tool("shell_exec", "执行 Shell 命令", category="development", requires_confirmation=True)
def shell_exec(command: str, timeout: int = 60, workdir: str = None):
    """执行系统命令（危险操作，需要确认）"""
    import subprocess
    from pathlib import Path as _Path

    cwd = _Path(workdir) if workdir else None

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd
        )
        return {
            "status": "success",
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr
        }
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Command timeout after {timeout}s")
    except Exception as e:
        raise RuntimeError(f"Command failed: {e}")

# ============================================
# Memory 工具
# ============================================

@tool("memory_search", "搜索记忆", category="memory", requires_confirmation=False)
def memory_search(query: str, max_results: int = 10):
    """在 MEMORY.md 和 memory/ 文件中搜索"""
    try:
        from memory_search import memory_search
        results = memory_search(query=query, maxResults=max_results)
        return {"status": "success", "query": query, "count": len(results), "results": results}
    except Exception as e:
        raise RuntimeError(f"Memory search failed: {e}")

@tool("memory_write", "写入记忆", category="memory", requires_confirmation=True)
def memory_write(content: str, file: str = "memory/SESSION_MEMORY.md"):
    """写入内容到记忆文件（需要确认）"""
    from pathlib import Path as _Path
    import time

    memory_file = _Path(file)
    if not memory_file.parent.exists():
        memory_file.parent.mkdir(parents=True, exist_ok=True)

    # 追加内容，带时间戳
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = f"\n## {timestamp}\n{content}\n"
    if memory_file.exists():
        memory_file.write_text(memory_file.read_text(encoding='utf-8') + entry, encoding='utf-8')
    else:
        memory_file.write_text(f"# Session Memory\n{entry}", encoding='utf-8')

    return {"status": "success", "file": str(memory_file), "size": memory_file.stat().st_size}

# ============================================
# Find Skills 工具
# ============================================

@tool("find_skills", "发现可用技能", category="system", requires_confirmation=False)
def find_skills(query: str = None, category: str = None):
    """搜索已安装的技能或查找新技能"""
    try:
        from find_skills import find_skills
        results = find_skills(query=query, category=category)
        return {"status": "success", "count": len(results), "results": results}
    except Exception as e:
        raise RuntimeError(f"Find skills failed: {e}")

# ============================================
# 自改进技能
# ============================================

@tool("self_improve_log", "记录自我改进", category="system", requires_confirmation=False)
def self_improve_log(issue: str, fix: str, category: str = "general"):
    """记录学到的教训或改进"""
    # 直接使用 memory_write 的逻辑，但指定到改进日志
    from pathlib import Path as _Path
    import time

    log_dir = _Path("memory/improvements")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{time.strftime('%Y-%m')}.md"

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = f"""
## {timestamp} - {category}
**问题**: {issue}
**改进**: {fix}
"""
    if log_file.exists():
        log_file.write_text(log_file.read_text(encoding='utf-8') + entry, encoding='utf-8')
    else:
        log_file.write_text(f"# 自我改进日志\n{entry}", encoding='utf-8')

    return {"status": "success", "file": str(log_file), "category": category}

# ============================================
# OCR 工具（包装已有技能）
# ============================================

@tool("ocr_recognize", "识别图片文字", category="document", requires_confirmation=False)
def ocr_recognize(image_path: str, lang: str = "chi_sim+eng"):
    """从图片中提取文字"""
    try:
        from ocr import recognize_text
        text = recognize_text(image_path, lang=lang)
        return {"status": "success", "text": text, "lang": lang, "image": image_path}
    except ImportError:
        raise RuntimeError("ocr skill not installed. Please install Tesseract first.")
    except Exception as e:
        raise RuntimeError(f"OCR failed: {e}")

# ============================================
# 注册完成
# ============================================

if __name__ == "__main__":
    print("📦 附加工具已注册")
    added = [t.name for t in registry._tools.values() if t.name not in ['file_write', 'feishu_message_send', 'web_search', 'git_commit', 'feishu_calendar_list', 'feishu_doc_read', 'feishu_bitable_list', 'feishu_search_user', 'pdf_extract_text', 'pdf_get_info', 'docx_read', 'xlsx_read']]
    print(f"   New tools: {', '.join(added)}")
    print(f"\n✅ Total tools in registry: {len(registry._tools)}")
