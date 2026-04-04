#!/usr/bin/env python3
"""
设置一次性提醒（5分钟后、10分钟后等）
用法: python3 scripts/set-reminder.py --minutes 5 --message "提醒内容"
"""
import os
import sys
import json
import time
import subprocess
from pathlib import Path

def create_launch_agent(minutes_from_now, message):
    """创建 launchd 一次性任务"""
    now = time.localtime()
    target_minute = now.tm_min + minutes_from_now
    target_hour = now.tm_hour
    target_day = now.tm_mday

    if target_minute >= 60:
        target_minute -= 60
        target_hour += 1
        if target_hour >= 24:
            target_hour -= 24
            target_day += 1

    # 生成唯一标签
    import uuid
    label = f"ai.openclaw.reminder-{uuid.uuid4().hex[:8]}"

    # 创建 plist
    plist_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>cd ~/.openclaw/workspace && python3 -c "from feishu_im_user_message import send; send(action='send', receive_id_type='open_id', receive_id='ou_d6540e9660ba1104c510007d85078d02', msg_type='text', content=json.dumps({{'text': '{message}'}}))" 2>/dev/null || echo "Failed to send reminder"</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>{target_hour}</integer>
        <key>Minute</key><integer>{target_minute}</integer>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/openclaw-reminder-{label}.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/openclaw-reminder-{label}.err</string>
</dict>
</plist>'''

    plist_path = Path.home() / 'Library' / 'LaunchAgents' / f'{label}.plist'
    plist_path.write_text(plist_content)

    # 加载并立即启动
    subprocess.run(['launchctl', 'unload', str(plist_path)], stderr=subprocess.DEVNULL)
    subprocess.run(['launchctl', 'load', str(plist_path)], check=True)
    subprocess.run(['launchctl', 'start', label], check=True)

    print(json.dumps({
        'label': label,
        'time': f'{target_hour:02d}:{target_minute:02d}',
        'message': message,
        'plist': str(plist_path)
    }, ensure_ascii=False))

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--minutes', type=int, required=True)
    parser.add_argument('--message', required=True)
    args = parser.parse_args()

    create_launch_agent(args.minutes, args.message)
