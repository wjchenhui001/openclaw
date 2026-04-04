# OpenClaw 深度学习报表

基于对 `~/Downloads/src` OpenClaw 源码的全面学习（QueryEngine.ts、query.ts、Tool.ts 三大核心文件 + 权限系统、记忆系统、Hook 系统、压缩策略模块），生成以下详细报表。

---

## 一、核心架构模式提取

### 1. Query Loop 决策树

**消息处理的完整流程（query.ts: queryLoop 函数，约 1700 行）**

```
第 1 步: 启动循环 (while true)
  ├─ 启动技能发现预取 (startSkillDiscoveryPrefetch)
  ├─ 启动记忆预取 (startRelevantMemoryPrefetch)
  └─ 发出 Stream Request Start 事件

第 2 步: 工具结果预算检查 (applyToolResultBudget)
  ├─ 限制聚合工具结果大小
  ├─ 在主循环前应用
  ├─ 与 microcompact 组合
  └─ 持久化替换状态到 sidechain 文件

第 3 步: Snip 压缩 (snipCompactIfNeeded) [feature('HISTORY_SNIP')]
  ├─ 从头部截取老旧对话
  ├─ 保留尾部助理消息（保护缓存）
  ├─ 返回 freed tokens 数量
  └─ 可选：yield boundary message

第 4 步: Micro Compact [cached_microcompact]
  ├─ 编辑缓存而非真实 API 调用
  ├─ 延迟 boundary message 直到 API 响应后
  ├─ 使用 cache_deleted_input_tokens
  └─ 不修改 messagesForQuery

第 5 步: Context Collapse [CONTEXT_COLLAPSE]
  ├─ 应用 staged collapses
  ├─ 读取时投影，不写入 REPL 数组
  ├─ 在 autocompact 前运行
  └─ 90% commit / 95% blocking-spawn 流程

第 6 步: Auto Compact (autoCompactIfNeeded)
  ├─ 阈值检查：effectiveWindow - 13K buffer
  ├─ 检查：禁用 auto_compact？→ 跳过
  ├─ 检查：reactive-only mode？→ 跳过
  ├─ 检查：context-collapse on？→ 跳过
  ├─ 检查：querySource='compact'？→ 跳过（防递归）
  ├─ 连续失败≥3 → 熔断，不再重试
  ├─ task_budget remaining 跟踪
  └─ 追踪状态更新：turnId, turnCounter, consecutiveFailures

第 7 步: 阻塞限制检查
  ├─ 如果 tokens ≥ blockingLimit（effectiveWindow - 3K）
  ├─ 且 autocompact/collapse 未激活
  └─ 则 yield API error: "prompt_too_long"

第 8 步: 模型选择 (getRuntimeMainLoopModel)
  ├─ 基于 permission 模式
  ├─ plan 模式 + 超过 200K tokens → 切换模型
  └─ 支持 fastMode 门控

第 9 步: API 流式调用 (callModel / queryModelWithStreaming)
  ├─ 前置钩子：执行 postSamplingHooks
  ├─ 流式处理：
  │   ├─ onStreaming 回调更新 spinner
  │   ├─ handleMessageFromStream 处理内容
  │   ├─ 工具使用块检测 (tool_use blocks)
  │   └─ 思考块保护规则（thinking blocks 不能是最后一条）
  ├─ 错误处理：
  │   ├─ max_output_tokens → 恢复重试（最多 3 次）
  │   ├─ prompt_too_long → reactive compact
  │   ├─ 其他错误 → fallback 模型
  │   └─ fallback 失败 → 抛出错误
  └─ 后置钩子：executeStopFailureHooks

第 10 步: 工具执行
  ├─ 旧路径：逐工具调用 (legacy tool execution)
  └─ 新路径：StreamingToolExecutor（并行执行）
      ├─ 注册工具执行进度回调
      ├─ 并行执行多个工具
      ├─ 权限检查 (hasPermissionsToUseTool)
      ├─ yield 工具结果消息
      └─ 更新 queryTracking

第 11 步: 停止钩子检查 (Stop Hook)
  ├─ 如果助手消息没有工具使用
  ├─ 执行 stop hooks
  ├─ hook 返回 "blocking" → 继续循环
  └─ hook 返回 "success" → 结束

第 12 步: 决策点
  ├─ 有工具使用块 → 继续循环（处理工具结果）
  ├─ 无工具使用 + 停止钩子通过 → 返回 {reason: "done"}
  ├─ 达到 maxTurns → 返回 {reason: "max_turns"}
  ├─ 预算超支 → 返回 {reason: "budget_exceeded"}
  └─ 错误 → 抛出异常
```

**我能如何应用：**

1. **在我的会话中实现类似的决策循环：** 在 AGENTS.md 中明确 7 种 continue 路径（工具使用、恢复、紧凑、停止钩子、错误重试、预算检查、maxTurns），每次循环前检查状态对象的 `transition` 字段
2. **采用"先诊断再修复"模式：** 与盲目重试相同操作不同，OpenClaw 在每次 continue 时检查 `hasAttemptedReactiveCompact` 等布尔标志，避免重复无效操作
3. **实现操作熔断器：** 连续失败 3 次就停止重试并报告用户，不要浪费资源
4. **在长会话中使用后台预取：** 技能发现和记忆检索在流式 API 调用期间后台运行，完成后才 await，隐藏延迟
5. **使用 State 对象携带决策状态：** 不要"心里记着"，跨循环轮次的信息必须通过显式状态对象传递

### 2. 上下文压缩策略

**四层压缩的触发条件和执行逻辑**

#### 2.1 第一层：Snip Compact (HISTORY_SNIP)

**触发条件：**
- 功能门控开启
- 会话消息超过头部截取阈值

**执行逻辑：**
- 从对话头部删除老旧的 user/assistant 消息对
- 保留尾部的 assistant 消息（保护 API 缓存）
- 返回 `tokensFreed` 数量

**我能如何应用：**
- 在我的会话管理中，可以定期归档超过一定天数的旧对话，但保持最近的对话活跃
- 在 MEMORY.md 中，可以将过于详细的历史记录提炼为简洁摘要，替换原文

#### 2.2 第二层：Micro Compact (Cached)

**触发条件：**
- 功能门控开启
- 当前对话有累积的缓存可编辑

**执行逻辑：**
- **不触发真实 API 调用**，仅编辑缓存状态
- 通过修改缓存的 `cache_deleted_input_tokens` 字段
- 延迟 yield boundary message 直到实际 API 响应后

**我能如何应用：**
- 在我的本地任务管理中，可以维护一个"待总结"队列，批量处理而非逐个处理
- 避免频繁的微小更新，积累到一定量再批量提交

#### 2.3 第三层：Context Collapse

**触发条件：**
- 功能门控开启
- `isContextCollapseEnabled()` 返回 true

**执行逻辑：**
- **读取时投影：** 不修改 REPL 消息数组，而是创建一个折叠后的视图
- 总结消息存储在 collapse store 中
- 支持 staged collapses：90% 阈值开始 commit，95% blocking

**关键设计：**
- Collapse 与 autocompact 互斥：如果 collapse 开启，autocompact 被抑制

**我能如何应用：**
- 在记忆管理中采用类似的分层策略：日常日志（`memory/YYYY-MM-DD.md`）保持不变，MEMORY.md 作为折叠视图
- 实施"90% 开始归档，95% 强制摘要"的两阶段策略

#### 2.4 第四层：Auto Compact

**触发条件：**
- 未被环境变量禁用
- 用户配置 `autoCompactEnabled` 为 true
- 令牌计数 `tokenCountWithEstimation(messages) - snipTokensFreed ≥ autoCompactThreshold`
  - 阈值 = `effectiveContextWindow - 13K buffer`

**执行逻辑：**
1. **Fork 子智能体：** 运行独立的 compact agent
2. **执行 Pre-Compact Hooks：** 允许钩子提供自定义压缩指令
3. **调用 API 生成摘要：** 最大输出 20K tokens
4. **处理失败：**
   - 如果 API 返回 `prompt_too_long`：从头部删除消息重试（最多 3 次）
   - 连续失败 ≥ 3：熔断，不再重试
5. **构建压缩后消息：** 摘要 + 附件 + 钩子结果
6. **Post-Compact 清理：**
   - 恢复 5 个关键文件（每个最多 5K tokens）
   - 恢复技能指令（总预算 25K，每技能 5K 截断）
7. **更新追踪状态**

**我能如何应用：**
1. **在 MEMORY.md 管理中实现类似策略：**
   - 定期（每周）检查大小
   - 如果超过阈值，提炼核心决策和偏好，移动旧条目到归档文件夹
2. **在长会话中使用子智能体做摘要：** 当对话超过一定长度，fork 一个子任务来提炼关键点
3. **实施熔断器：** 如果连续 3 次摘要尝试失败，停止重试并通知用户

### 3. 工具系统设计原则

**184 个工具的共性设计模式（Tool.ts: 792 行）**

#### 3.1 工具接口定义

```typescript
export type Tool = {
  name: string
  description: string
  inputSchema: ZodType
  call: (input: any, context: ToolUseContext) => Promise<ToolResult>
  
  // 可选能力
  checkPermissions?: (input: any, context: ToolUseContext) => Promise<PermissionCheckResult>
  requiresUserInteraction?: () => boolean
  maxResultSizeChars?: number
}
```

**关键设计：**
- **统一接口：** 所有工具都遵循相同的输入/输出模式
- **输入验证：** 使用 Zod schema 验证工具输入
- **权限检查：** `checkPermissions` 钩子允许工具自定义权限逻辑
- **结果大小限制：** `maxResultSizeChars` 防止单一工具结果占满上下文

**我能如何应用：**
- 在我的本地脚本中，采用统一的命令接口模式：每个命令都有 `validate(input)`、`execute(input, context)`、`checkPermissions(input)` 三件套
- 为高风险操作添加 `requiresUserInteraction()` 检查

#### 3.2 工具权限检查流水线（10+ 层权限瀑布）

```
第 1 层: 功能门控检查 → 禁用则 deny
第 2 层: 工具级始终允许规则 → 匹配则 allow
第 3 层: 工具级始终拒绝规则 → 匹配则 deny
第 4 层: 工具级始终询问规则 → 匹配则 ask
第 5 层: 内容级规则匹配（工具+内容）→ 按优先级排序匹配
第 6 层: 工作目录检查 → 不在工作目录内则 safetyCheck
第 7 层: 危险模式检测 → 检测到危险命令则 deny
第 8 层: Permission Prompt Tool → 触发交互式权限请求
第 9 层: DontAsk 模式 → 转换为 deny（Fail-Closed）
第 10a 层: Auto 模式 → Transcript Classifier 两阶段分类
第 10b 层: Plan 模式 → 阻止工具执行
第 11 层: 钩子检查 → PreToolUse hooks 可以 blocking
第 12 层: Bypass Permissions → 在 bypass 列表中且已接受则 allow
第 13 层: 最终决定 → 返回 'ask'，等待用户交互
```

**关键设计原则：**

1. **Fail-Closed（默认拒绝）：** 任何一层不确定 → 询问用户
2. **早期退出（Early Exit）：** 允许规则匹配后立即返回
3. **规则优先级：** session > command > cliArg > 用户设置
4. **多层防护：** 规则匹配 → 路径免疫 → 危险模式 → AI 分类器 → 用户确认
5. **Denial Tracking：** 连续拒绝达到阈值后回退到询问
6. **Auto Mode 快速路径：** acceptEdits 检查和允许列表绕过分类器
7. **分类器两级架构：** Stage 1 快速筛查，Stage 2 详细分析

**我能如何应用：**

1. **在我的本地安全策略中实现类似的多层检查：**
   - 第 1 层：白名单（已知安全的命令）
   - 第 2 层：黑名单（明确禁止的危险命令）
   - 第 3 层：路径检查（禁止写入 `.git/`、`~/.ssh/` 等）
   - 第 4 层：工作目录限制
   - 第 5 层：用户确认（未知操作必须确认）

2. **实现拒绝追踪和回退：**
   - 记录连续失败的操作
   - 如果某类操作连续失败 3 次，停止自动尝试并请求人工干预

3. **采用快速路径优化：**
   - 对于已知安全的操作（如 `ls`、`grep`、`cat`），直接允许
   - 对于高风险操作（如 `rm`、`mv`、写入系统目录），立即要求确认

---

## 二、自我进化应用

### 1. 行为准则升级（应用到 SOUL.md）

基于学到的 Query Loop 决策树和压缩策略，SOUL.md 需要新增：

- **连续性决策原则：** 每次循环前检查状态，明确 7 种 continue 路径，不盲目重试
- **熔断器强化：** 任何操作连续失败 3 次 → 停止并报告用户
- **后台预取模式：** 技能发现和记忆检索在后台运行，隐藏延迟
- **状态显式传递：** 跨轮次信息通过文件传递，不"心里记着"

### 2. 工作流优化（应用到 AGENTS.md）

基于学到的工具系统设计：

- **统一命令接口：** 所有本地脚本采用 `validate/execute/checkPermissions` 三件套
- **快速路径优化：** 已知安全操作直接执行，高风险操作立即确认
- **拒绝追踪机制：** 记录失败，连续 3 次失败后停止并报告

### 3. 记忆策略改进（应用到 MEMORY.md 管理）

基于学到的四层压缩策略：

- **归档策略：** 日常日志保持不变，MEMORY.md 作为折叠视图
- **两阶段摘要：** 90% 阈值开始归档，95% 强制摘要
- **子智能体摘要：** 长会话时 fork 子任务提炼关键点
- **关键文件恢复：** Post-Compact 恢复最多 5 个关键文件

### 4. 安全边界强化

基于学到的 10+ 层权限瀑布：

- **多层检查：** 白名单 → 黑名单 → 路径检查 → 工作目录 → 用户确认
- **快速路径：** 安全操作直接允许，危险操作立即确认
- **分类器思维：** 即使不用 AI，也模仿两阶段检查（快速筛查 + 详细分析）

---

## 三、具体改进清单

| 改进项 | 当前状态 | 目标状态 | 执行计划 |
|--------|---------|---------|---------|
| Query Loop 决策树 | 隐式，无明确状态 | 显式 7 种 continue 路径 | 在 AGENTS.md 中定义 continue 决策点 |
| 操作熔断器 | 已定义但未强化 | 连续 3 次失败即停止 | 在 SOUL.md 中强化，在每次操作中执行 |
| 后台预取 | 无 | 技能/记忆后台运行 | 在心跳检查中并行执行发现任务 |
| 四层压缩策略 | 无 | 分层归档 + 摘要 | 在 MEMORY.md 中实施 90%/95% 两阶段 |
| 统一命令接口 | 无 | validate/execute/checkPermissions | 为本地脚本创建模板 |
| 快速路径优化 | 无 | 安全操作直接执行 | 在 AGENTS.md 中定义白名单/黑名单 |
| 拒绝追踪 | 无 | 连续失败 3 次报告 | 在 AGENTS.md 中定义追踪机制 |
| 多层安全检查 | 部分 | 5 层权限瀑布 | 在 SOUL.md 中补充路径/工作目录检查 |

---

## 四、学习总结

从 OpenClaw 源码中学到的最关键设计原则：

1. **Fail-Closed 是核心：** 任何不确定 → 询问用户，不猜测
2. **状态显式传递：** 跨轮次信息通过文件或状态对象，不"心里记着"
3. **熔断器模式：** 连续失败 3 次 → 停止，不要浪费资源
4. **分层压缩：** 四层策略（Snip → Micro → Collapse → Auto），每层有不同触发条件
5. **快速路径优化：** 已知安全操作直接执行，减少 API 调用
6. **多层防护：** 10+ 层权限检查，早期退出，规则优先级
7. **后台预取：** 技能发现和记忆检索在后台运行，隐藏延迟
8. **统一接口：** 所有工具遵循相同输入/输出模式，便于扩展

这些原则不仅适用于 OpenClaw 系统，也适用于我作为 agent 的日常行为。我将把这些原则融入 SOUL.md、AGENTS.md 和 MEMORY.md，实现真正的自我进化。

---

_报表生成时间：2026-04-04 20:56_
_基于对 1884 个源码文件的第二轮深度学习_
