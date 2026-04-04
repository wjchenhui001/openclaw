#!/usr/bin/env python3
"""
清理旧的 workspace 备份文件，只保留最近 5 个
"""
import os
import glob
from pathlib import Path

BACKUP_PATTERN = "/tmp/workspace-backup-*.tar.gz"
MAX_KEEP = 5

def cleanup_old_backups():
    # 按修改时间排序（最新的在前）
    backups = sorted(glob.glob(BACKUP_PATTERN), key=os.path.getmtime, reverse=True)

    if len(backups) <= MAX_KEEP:
        print(f"✅ 备份数量 ({len(backups)}) 未超过 {MAX_KEEP}，无需清理")
        return

    to_delete = backups[MAX_KEEP:]
    for f in to_delete:
        try:
            os.remove(f)
            print(f"🗑️  删除旧备份: {f}")
        except Exception as e:
            print(f"⚠️  删除失败 {f}: {e}")

    print(f"✅ 保留 {MAX_KEEP} 个最新备份，清理了 {len(to_delete)} 个旧备份")

if __name__ == '__main__':
    cleanup_old_backups()
