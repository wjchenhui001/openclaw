#!/bin/bash
# 日报推送脚本（9:00 自动执行）

export PATH="$HOME/.local/bin:$PATH"

WORKSPACE="$HOME/.openclaw/workspace"
REPORT_DIR="$WORKSPACE/reports"
YESTERDAY=$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d "yesterday" +%Y-%m-%d)

REPORT_FILE="$REPORT_DIR/daily-$YESTERDAY.txt"
FLAG_FILE="$REPORT_DIR/ready-$YESTERDAY.flag"

if [ ! -f "$REPORT_FILE" ]; then
    echo "⚠️  日报文件不存在: $REPORT_FILE"
    exit 1
fi

if [ ! -f "$FLAG_FILE" ]; then
    echo "⚠️  日报未就绪: $FLAG_FILE"
    exit 1
fi

REPORT=$(cat "$REPORT_FILE")

cd "$WORKSPACE"
openclaw message send --channel feishu --target user:ou_d6540e9660ba1104c510007d85078d02 --message "$REPORT"

if [ $? -eq 0 ]; then
    echo "✅ 日报已推送: $YESTERDAY"
    rm -f "$FLAG_FILE"
    echo "$(date -Iseconds) - pushed: $YESTERDAY" >> "$REPORT_DIR/push-log.txt"
else
    echo "❌ 推送失败"
    exit 1
fi
