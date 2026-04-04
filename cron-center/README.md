# Cron 任务中心

统一管理所有定时任务（macOS launchd）。

## 📋 当前任务列表

| 任务名称 | 触发时间 | 描述 | 状态 |
|---------|---------|------|------|
| `ai.openclaw.daily-report` | 每天 09:00 | 日报生成与推送 |
| `ai.openclaw.workspace-backup` | 每天 04:00 | 工作区自动备份（保留最近5个） |
| `ai.openclaw.eat-now` | 每天 12:00, 18:00 | 吃饭提醒 |
| `ai.openclaw.sleep-reminder` | 每天 23:00 | 睡眠提醒 |
| `ai.openclaw.reminder-*` | 自定义时间 | 通过 remind-me 技能动态创建的单次提醒 |
| `ai.openclaw.eat-once` | 一次性 | 临时单次提醒 |

> **注**: 状态 `-` 表示任务已加载但未到执行时间；`1` 表示正在运行或待触发。

## 🛠️ 管理命令

### 查看所有任务状态

```bash
launchctl list | grep ai.openclaw
```

### 查看单个任务

```bash
# 查看任务配置
cat ~/Library/LaunchAgents/ai.openclaw.daily-report.plist

# 查看任务日志
tail -f /tmp/openclaw-daily-report.log

# 查看错误日志
tail -f /tmp/openclaw-daily-report.err
```

### 启用/禁用任务

```bash
# 禁用（卸载）
launchctl unload ~/Library/LaunchAgents/ai.openclaw.daily-report.plist

# 启用（加载）
launchctl load ~/Library/LaunchAgents/ai.openclaw.daily-report.plist

# 立即触发
launchctl kickstart -k user/$(id -u)/ai.openclaw.daily-report
```

### 添加新定时任务

```bash
# 1. 在 cron-center/tasks/ 创建 .plist 文件
# 2. 加载任务
launchctl load ~/Library/LaunchAgents/your-task.plist
# 3. 记录到 README.md 的任务列表
```

## 📝 任务模板

### 一次性任务（指定时间执行一次）

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>ai.openclaw.mytask</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>cd ~/.openclaw/workspace && ./scripts/myscript.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>10</integer>
        <key>Minute</key><integer>30</integer>
    </array>
    <key>RunAtLoad</key>
    <false/>
    <key>StandardOutPath</key>
    <string>/tmp/openclaw-mytask.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/openclaw-mytask.err</string>
</dict>
</plist>
```

### 重复任务（Cron 风格）

```xml
<key>StartCalendarInterval</key>
<array>
    <dict>
        <key>Hour</key><integer>9</integer>
        <key>Minute</key><integer>0</integer>
    </dict>
    <dict>
        <key>Hour</key><integer>12</integer>
        <key>Minute</key><integer>0</integer>
    </dict>
</array>
```

## 🔗 相关文档

- [macOS launchd 指南](https://www.launchd.info/)
- [cron 表达式转换](https://crontab.guru/)
- 任务脚本参考：`scripts/` 目录

## 🧹 清理过期任务

定期检查并清理不再需要的任务：
```bash
# 列出所有 openclaw 任务
ls ~/Library/LaunchAgents/ai.openclaw.*.plist

# 卸载并删除旧任务
launchctl unload ~/Library/LaunchAgents/old-task.plist
rm ~/Library/LaunchAgents/old-task.plist
```

---

**维护者**: 陈飞阳
**最后更新**: 2026-04-05
