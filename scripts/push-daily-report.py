#!/usr/bin/env python3
"""
推送日报到飞书（使用 openclaw message send）
"""
import subprocess
from pathlib import Path
from datetime import datetime, timedelta

WORKSPACE = Path(__file__).parent.parent
REPORT_DIR = WORKSPACE / 'reports'

def get_yesterday_date():
    yesterday = datetime.now() - timedelta(days=1)
    return yesterday.strftime('%Y-%m-%d')

def main():
    yesterday = get_yesterday_date()
    report_file = REPORT_DIR / f'daily-{yesterday}.txt'
    flag_file = REPORT_DIR / f'ready-{yesterday}.flag'

    if not report_file.exists():
        print(f"⚠️  日报文件不存在: {report_file}")
        return

    if not flag_file.exists():
        print(f"⚠️  日报未就绪: {flag_file}")
        return

    report = report_file.read_text(encoding='utf-8').strip()

    try:
        result = subprocess.run(
            ['openclaw', 'message', 'send', '--channel', 'feishu',
             '--target', 'user:ou_d6540e9660ba1104c510007d85078d02',
             '--message', report],
            capture_output=True, text=True, timeout=30, cwd=WORKSPACE
        )
        if result.returncode == 0:
            print(f"✅ 日报已推送: {yesterday}")
            flag_file.unlink(missing_ok=True)
            log_file = REPORT_DIR / 'push-log.txt'
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"{datetime.now().isoformat()} - pushed: {yesterday}\n")
        else:
            print(f"❌ 推送失败: {result.stderr}")
    except Exception as e:
        print(f"❌ 推送异常: {e}")

if __name__ == '__main__':
    main()
