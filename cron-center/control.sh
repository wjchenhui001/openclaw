#!/bin/bash
# Cron 任务中心控制脚本

AGENTS_DIR="$HOME/Library/LaunchAgents"
TASKS_DIR="$(cd "$(dirname "$0")" && pwd)/tasks"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

function list_tasks() {
    echo "📋 任务列表 (launchctl list | grep ai.openclaw):"
    echo ""
    launchctl list | grep ai.openclaw | while read line; do
        status=$(echo $line | awk '{print $1}')
        pid=$(echo $line | awk '{print $2}')
        label=$(echo $line | awk '{print $3}')
        echo "  $label"
        echo "    状态: $status, PID: ${pid:-无}"
        # 查找对应的 plist
        plist="$AGENTS_DIR/$label.plist"
        if [ -f "$plist" ]; then
            echo "    配置文件: $plist"
        else
            echo -e "    ${RED}配置文件缺失${NC}"
        fi
        echo ""
    done
}

function start_task() {
    local label="ai.openclaw.$1"
    local plist="$AGENTS_DIR/$label.plist"

    if [ ! -f "$plist" ]; then
        echo -e "${RED}❌ 任务配置文件不存在: $plist${NC}"
        exit 1
    fi

    echo "🚀 启动任务: $label"
    launchctl load "$plist"
    sleep 1
    if launchctl list | grep -q "$label"; then
        echo -e "${GREEN}✅ 任务已启动${NC}"
    else
        echo -e "${RED}❌ 启动失败${NC}"
    fi
}

function stop_task() {
    local label="ai.openclaw.$1"
    local plist="$AGENTS_DIR/$label.plist"

    if [ ! -f "$plist" ]; then
        echo -e "${RED}❌ 任务配置文件不存在: $plist${NC}"
        exit 1
    fi

    echo "🛑 停止任务: $label"
    launchctl unload "$plist"
    sleep 1
    if launchctl list | grep -q "$label"; then
        echo -e "${RED}❌ 任务仍在运行${NC}"
    else
        echo -e "${GREEN}✅ 任务已停止${NC}"
    fi
}

function tail_log() {
    local task=$1
    local log="/tmp/openclaw-${task}.log"
    local err="/tmp/openclaw-${task}.err"

    echo "📊 查看日志: $task"
    if [ -f "$log" ]; then
        echo "--- 标准输出 (tail -f $log) ---"
        tail -n 20 "$log"
    else
        echo -e "${YELLOW}⚠️  日志文件不存在: $log${NC}"
    fi
    echo ""
    if [ -f "$err" ]; then
        echo "--- 错误输出 (tail -f $err) ---"
        tail -n 20 "$err"
    else
        echo -e "${YELLOW}⚠️  错误日志不存在: $err${NC}"
    fi
}

function show_help() {
    echo "Cron 任务中心 - 管理所有定时任务"
    echo ""
    echo "用法: $0 <command> [task_name]"
    echo ""
    echo "命令:"
    echo "  list                       列出所有任务"
    echo "  start <task>               启动指定任务 (不含 ai.openclaw. 前缀)"
    echo "  stop <task>                停止指定任务"
    echo "  logs <task>                查看任务日志"
    echo "  reload <task>              重新加载任务配置"
    echo "  help                      显示此帮助"
    echo ""
    echo "示例:"
    echo "  $0 list"
    echo "  $0 start daily-report"
    echo "  $0 logs workspace-backup"
    echo ""
    echo "当前任务:"
    ls "$TASKS_DIR"/*.plist 2>/dev/null | xargs -I{} basename {} .plist | sed 's/^/  - /'
}

case "$1" in
    list)
        list_tasks
        ;;
    start)
        if [ -z "$2" ]; then
            echo "用法: $0 start <task_name>"
            exit 1
        fi
        start_task "$2"
        ;;
    stop)
        if [ -z "$2" ]; then
            echo "用法: $0 stop <task_name>"
            exit 1
        fi
        stop_task "$2"
        ;;
    logs)
        if [ -z "$2" ]; then
            echo "用法: $0 logs <task_name>"
            exit 1
        fi
        tail_log "$2"
        ;;
    reload)
        if [ -z "$2" ]; then
            echo "Usage: $0 reload <task_name>"
            exit 1
        fi
        label="ai.openclaw.$2"
        plist="$AGENTS_DIR/$label.plist"
        if [ -f "$plist" ]; then
            launchctl unload "$plist" 2>/dev/null
            launchctl load "$plist"
            echo "✅ 任务已重新加载: $label"
        else
            echo "❌ 配置文件不存在: $plist"
        fi
        ;;
    help|*)
        show_help
        ;;
esac
