#!/usr/bin/env python3
"""
检查备份标记文件，发送通知。
"""
import os
import json
from pathlib import Path

NOTIFY_DIR = Path('/tmp/openclaw-backup-notify')
STATE_FILE = Path.home() / '.openclaw' / 'workspace' / 'memory' / 'last-backup-notified.json'

def load_notified():
    if STATE_FILE.exists():
        with open(STATE_FILE, 'r') as f:
            return set(json.load(f))
    return set()

def save_notified(notified):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(sorted(list(notified)), f, indent=2)

def main():
    notified = load_notified()
    new_files = []

    if NOTIFY_DIR.exists():
        for f in NOTIFY_DIR.iterdir():
            if f.is_file() and f.name.startswith('backup-') and f.name not in notified:
                new_files.append(f.name)
                notified.add(f.name)

    if new_files:
        # 这里只是标记，实际消息发送通过飞书 IM
        # 返回 JSON 供外部处理
        result = {
            'new_backups': new_files,
            'count': len(new_files)
        }
        print(json.dumps(result, ensure_ascii=False))
        save_notified(notified)
    else:
        print(json.dumps({'new_backups': [], 'count': 0}, ensure_ascii=False))

if __name__ == '__main__':
    main()
