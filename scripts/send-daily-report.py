#!/usr/bin/env python3
"""
生成日报文本（保存到 reports/ 目录）
"""
from pathlib import Path
from datetime import datetime, timedelta

WORKSPACE = Path(__file__).parent.parent
MEMORY_DIR = WORKSPACE / 'memory'
REPORT_DIR = WORKSPACE / 'reports'
REPORT_DIR.mkdir(exist_ok=True)

def get_yesterday_date():
    yesterday = datetime.now() - timedelta(days=1)
    return yesterday.strftime('%Y-%m-%d')

def load_daily_log(date_str):
    log_file = MEMORY_DIR / f'{date_str}.md'
    if log_file.exists():
        return log_file.read_text(encoding='utf-8')
    return None

def extract_report_section(content):
    lines = content.split('\n')
    report_lines = []
    in_report = False
    for line in lines:
        if '📝 今日总结' in line or '今日总结' in line:
            in_report = True
        if in_report:
            report_lines.append(line)
            if line.startswith('## ') and '今日总结' not in line:
                break
    return '\n'.join(report_lines) if report_lines else content

def main():
    yesterday = get_yesterday_date()
    content = load_daily_log(yesterday)
    if not content:
        report = f"📅 日报：未找到 {yesterday} 的日志文件"
    else:
        report_section = extract_report_section(content)
        report = f"📅 **{yesterday} 日报**\n\n{report_section}"
    report_file = REPORT_DIR / f'daily-{yesterday}.txt'
    report_file.write_text(report, encoding='utf-8')
    flag_file = REPORT_DIR / f'ready-{yesterday}.flag'
    flag_file.touch()
    print(f"✅ 日报已生成: {report_file}")

if __name__ == '__main__':
    main()
