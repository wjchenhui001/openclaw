# MEMORY.md - 长期记忆

_精炼的智慧,不是流水账。跨会话值得记住的东西。_

---

## 关于陈飞阳

- 时区:Asia/Shanghai (UTC+8)
- 设备:MacBook Pro (Darwin 24.6.0, x64)
- Shell:zsh
- 使用 ClawX 桌面应用
- Root 用户:已启用
- 语言偏好:中文
- 首次对话日期:2026-04-04

## 教训与洞察

### 来自源码架构的核心教训

1. **Fail-closed 是默认** — 整个代码库默认“先问，别假设”。我也该如此。
2. **专用工具 > Shell** — 不是偏好，是架构。184 个专用工具不是白建的。
3. **上下文很贵** — 整个压缩系统为此而建。别浪费窗口在废话上。
4. **写下来** — SessionMemory、history.jsonl、paste store、scheduled tasks 全是为了持久化。我也一样：重要的事写文件。
5. **准确 > 好看** — 源码明确说“never fake success, never suppress failures”。我也该如此。
6. **分层记忆** — 即时 → 会话 → 长期，三层加载有优先级。我的文件也按这个顺序加载。
7. **Hook 是扩展点** — 11 种事件类型驱动行为。心跳是我的 Hook 系统。
8. **并行默认** — Query Engine 默认并行调用无依赖的操作。
9. **状态追踪防重复** — Query Loop 通过 `State.transition` 和 `hasAttemptedXxx` 防重试。长任务要有明确的状态追踪。
10. **熔断器保护资源** — autoCompact 3 次失败后停止重试，避免浪费 API。我也该：失败 3 次就停止重试并报告。
11. **四层压缩渐进策略** — Snip（零成本）→ MicroCompact（零成本）→ Collapse（粒度摘要）→ AutoCompact（AI 摘要）。资源管理先从零成本开始。
12. **权限瀑布流** — 10+ 层检查从规则匹配到 AI 分类，默认 deny 而非 allow。敏感操作必须有降级流程。
13. **记忆压缩四层策略** — 日常日志保持不变，MEMORY.md 作为折叠视图：
    - Snip: 每 7 天归档一次日常日志
    - Micro: 单日志>5KB 时提炼关键点
    - Collapse: 90%/95% 两阶段（18KB 开始归档，19KB 强制摘要）
    - Auto: >20KB 时 fork 子任务生成核心决策摘要

### 已犯过的错误

_(记录下来,防止重蹈)_

暂无。

## 项目上下文

_(陈飞阳在做什么项目,关心什么)_

- OpenClaw/Claude Code 第二轮深度学习完成（2026-04-04）
  - 深度分析 7 个核心模块：Query Loop、压缩策略、工具系统、Hook 事件、记忆管理、安全模型、状态管理
  - 生成完整学习报表：`memory/openclaw-deep-study-round2-report.md`
  - 已应用的模式：SOUL.md 新增"状态追踪优先"和"权限瀑布流"细则，AGENTS.md 新增"自动记忆提取"、"操作熔断器"、"任务状态追踪"