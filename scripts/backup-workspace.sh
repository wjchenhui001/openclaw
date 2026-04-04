#!/bin/bash
# 备份工作区并自动清理旧备份

set -e

echo "🔄 开始备份工作区..."
cd ~/.openclaw/workspace

# 执行备份
BACKUP_FILE="/tmp/workspace-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
tar -czf "$BACKUP_FILE" .
echo "✅ 备份完成: $BACKUP_FILE"

# 创建备份通知标志
touch "/tmp/openclaw-backup-notify/backup-$(date +%Y%m%d-%H%M%S)"
echo "✅ 备份通知标志已创建"

# 清理旧备份（保留最近5个）
echo "🧹 清理旧备份..."
python3 scripts/cleanup-old-backups.py

echo "🎉 备份流程完成"
