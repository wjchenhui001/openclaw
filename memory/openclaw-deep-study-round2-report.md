# OpenClaw 第二轮深度学习报表

> 生成时间：2026-04-04  
> 源码路径：~/Downloads/src  
> 覆盖文件数：1884 个，约 30MB  
> 深度分析模块：7 个核心架构域

---

## 一、核心架构模式提取

### 1. Query Loop 决策树

**完整的消息处理流程（query.ts 1630行主循环）**

```
用户消息进入 → QueryEngine.submitMessage()
  │
  ├─ 1. Session 启动：读取 SOUL.md → USER.md → 今日/昨日 memory
  ├─ 2. 前置：relevant memory 预取 + skill 发现预取（并行，不阻塞）
  │
  └─ 3. Query Loop（while true 无限循环，7 种 continue 路径）
       │
       ├─ 3a. 消息预处理流水线
       │     SnipCompact（历史截断，feature-gated，零 AI 删除）
       │       ↓
       │     MicroCompact（工具结果缓存清理，零 AI 成本）
       │       ↓
       │     ContextCollapse（可选，90% 提交粒度上下文）
       │       ↓
       │     AutoCompact（阈值触发，forked agent 摘要）
       │       ↓
       │     预算检查（13K buffer，blocking limit 保护）
       │
       ├─ 3b. API 流式调用（callModel streaming）
       │     ├─ 成功 → assistantMessages 收集，tool_use 检测
       │     └─ 失败 → FallbackTriggeredError → 模型降级重试
       │
       ├─ 3c. 工具执行
       │     ├─ StreamingToolExecutor（并发，流式进度推送）
       │     └─ 旧路径：runTools（串行，全量等待）
       │
       ├─ 3d. Post-sampling hooks（extractSessionMemory 等）
       │
       └─ 3e. 7 种 Continue 路径决策
             │
             ├─ (1) collapse_drain_retry
             │   触发： withheld 413 + staged collapse 可 drain
             │   动作： drain 所有 staged collapses，继续
             │   保护： 检查 transition.reason 防重复
             │
             ├─ (2) reactive_compact_retry
             │   触发： withheld 413/media 错误 + reactiveCompact 可用
             │   动作： 调用 tryReactiveCompact，继续
             │   保护： hasAttemptedReactiveCompact 防重复
             │
             ├─ (3) max_output_tokens_escalate
             │   触发： max_output_tokens 错误 + 未用 override
             │   动作： 设置 maxOutputTokensOverride = 64K，继续
             │   保护： 仅一次 escalation
             │
             ├─ (4) max_output_tokens_recovery
             │   触发： escalation 后仍超限 + recovery count < 3
             │   动作： 注入 meta 消息，继续
             │   保护： MAX_OUTPUT_TOKENS_RECOVERY_LIMIT = 3
             │
             ├─ (5) stop_hook_blocking
             │   触发： Stop hooks 返回 blockingErrors
             │   动作： 注入 blocking error 消息，继续
             │   保护： stopHookActive 标记
             │
             ├─ (6) token_budget_continuation
             │   触发： token 预算未超 + diminishingReturns 未触发
             │   动作： 注入 nudge 消息，increment continuationCount
             │   保护： budgetTracker 状态
             │
             └─ (7) return Terminal（完成）
                   触发： 无 tool_use + 无 continue 条件
                   动作： 执行 handleStopHooks，返回

关键设计：状态携带通过 State 对象（14 个字段），continue 时完整替换

type State = {
  messages: Message[]                    // 当前消息数组
  toolUseContext: ToolUseContext         // 工具执行上下文
  autoCompactTracking: ... | undefined   // 压缩追踪状态
  maxOutputTokensRecoveryCount: number   // max_output 恢复计数
  hasAttemptedReactiveCompact: boolean   // 防重复响应式压缩
  maxOutputTokensOverride: number | undefined  // 覆盖的 max tokens
  pendingToolUseSummary: Promise<...>    // 延迟的工具摘要
  stopHookActive: boolean | undefined    // stop hook 活跃标记
  turnCount: number                      // 轮次计数
  transition: Continue | undefined       // 上一轮 continue 原因（测试断言用）
}
```

**我能如何应用：**
- 当前 AGENTS.md 中的"心跳主动出击"章节应该借鉴 continue 路径的状态驱动思维：不再基于时间猜测，而是基于明确的状态转换
- 记忆系统应该像 `autoCompactTracking` 一样有明确的追踪状态，而非"心里记着"

---

### 2. 上下文压缩策略

**四层压缩体系（zero-AI → zero-AI → optional-AI → AI）**

#### Layer 1: SnipCompact（snipCompact.ts，feature('HISTORY_SNIP')）
- **触发条件：** 历史消息数超过阈值
- **执行逻辑：** 删除最旧的非关键消息，保留最近 N 条 + 受保护的尾部
- **成本：** 零 AI，纯客户端计算
- **Tokens 释放：** 通过 `tokensFreed` 传给 autocompact，使其阈值检查反映实际节省
- **边界消息：** 生成 `createMicrocompactBoundaryMessage` 告知用户
- **适用场景：** 超长会话的粗粒度清理

#### Layer 2: MicroCompact（microCompact.ts，530行）
- **双路径设计：**
  
  **路径 A: Cached MicroCompact（缓存编辑路径）**
  - 触发：`tengu_cache_plum_violet = true`（Ant 默认开启）+ 模型支持 cache-editing + main thread
  - 机制：跟踪 compactable tools（FileRead, Bash, Grep, Glob, WebSearch, WebFetch, FileEdit, FileWrite）
  - 删除策略：保持最近 `keepRecent` 个工具结果，删除更早的（通过 cache_edits API）
  - 关键特性：**不修改本地消息内容**，cache_reference 和 cache_edits 在 API 层添加
  - 边界消息：延迟到 API 响应后，使用真实的 `cache_deleted_input_tokens`
  
  **路径 B: Time-Based MicroCompact（时间触发路径）**
  - 触发：距离上次 assistant 消息的 gap > `gapThresholdMinutes`（可配置）
  - 执行：content-clear 所有但最近 N 个工具结果 → `TIME_BASED_MC_CLEARED_MESSAGE`
  - 副作用：**必须** `resetMicrocompactState()` + `notifyCacheDeletion()`
  - 原因：缓存已冷，内容已变，cached-MC 状态失效
  
- **零 AI 成本：** 纯规则驱动，基于工具 ID 和时间戳
- **可压缩工具白名单：** 仅 8 种工具（避免压缩思考/长输出）

#### Layer 3: Context Collapse（contextCollapse/，feature('CONTEXT_COLLAPSE')）
- **触发条件：** 上下文使用率超过 90%（commit-start）
- **执行逻辑：**
  - 将消息分组为"提交"（committed）和"暂存"（staged）
  - 提交的消息被替换为结构化摘要（forked agent 生成）
  - 仅当 95% 时阻塞性触发 compact
- **关键设计：** read-time projection，summary 存储在 collapse store 而非 REPL 数组
- **与 autocompact 互斥：** collapse 启用时 suppress autocompact

#### Layer 4: AutoCompact（autoCompact.ts，340行）
- **触发条件：** `tokenCount >= getAutoCompactThreshold(model)`
  - 阈值 = `effectiveContextWindow - 13K buffer`
  - effectiveContextWindow = `contextWindow - min(maxOutputTokens, 20K)`
- **执行流程（三路决策）：**
  
  ```
  shouldAutoCompact() 检查
    ├─ 递归保护：querySource === 'session_memory' | 'compact' | 'marble_origami' → false
    ├─ 用户配置：DISABLE_COMPACT / DISABLE_AUTO_COMPACT → false
    ├─ 功能互斥：REACTIVE_COMPACT 开启 → false
    └─ 功能互斥：CONTEXT_COLLAPSE 开启 → false
  
  通过后执行 autoCompactIfNeeded()
    ├─ Circuit Breaker：consecutiveFailures >= 3 → 短路
    ├─ 路径 1：trySessionMemoryCompaction()（见下文记忆章节）
    └─ 路径 2：compactConversation()（传统 forked agent 摘要）
  ```

- **熔断器设计：** 最多 3 次连续失败后停止重试（生产数据：1,279 个 session 有 50+ 次连续失败，浪费 ~250K API 调用/天）

**我能如何应用：**
- 当前的 `/context` 或压缩逻辑应该借鉴四层策略：先做零成本的 snip/micro，再做 AI 摘要
- 熔断器模式应应用到所有可能重复失败的操作（如网络请求、API 调用）

---

### 3. 工具系统设计原则

**核心架构（Tool.ts 793行 + tools/ 45 个工具）**

#### 3.1 Tool 接口设计（184 个工具的共性）

```typescript
type Tool = {
  // 1. 身份标识
  name: string                          // 工具名（如 'Bash', 'Read', 'Glob'）
  description: string                   // 模型可见的描述
  input_schema: ToolInputJSONSchema     // JSON Schema 验证
  
  // 2. 执行
  call(input: T, context: ToolUseContext): Promise<ToolResult>
  
  // 3. 权限
  checkPermissions?(input: T, context: ToolUseContext): Promise<'allow' | 'deny' | 'ask'>
  
  // 4. 验证
  validateInput?(input: T): ValidationResult
  
  // 5. 元信息
  requiresApproval?: boolean            // 是否总是需要用户批准
  maxResultSizeChars?: number           // 结果大小限制
  
  // 6. 观察性（可选）
  backfillObservableInput?(input: Record<string, unknown>): void
  onProgress?(progress: ProgressUpdate): void
}

// ToolResult 统一结构
type ToolResult = {
  data: ToolOutputType     // 结构化输出
  metadata?: {
    durationMs: number
    tokensUsed?: number
  }
}
```

**184 个工具的共性模式：**
1. **统一的错误处理：** 所有工具通过 `toError()` 包装异常，返回结构化错误
2. **一致的进度推送：** StreamingToolExecutor + `onProgress` 回调
3. **输入验证分离：** `validateInput` 在执行前运行，失败则返回 `ValidationResult`
4. **权限检查瀑布流：** `checkPermissions` → `hasPermissionsToUseTool` → AI 分类器

#### 3.2 权限检查瀑布流（10+ 层）

**permissions.ts 1488行，完整的决策链：**

```
hasPermissionsToUseTool(tool, input, context)
  │
  ├─ Step 0: Fast-path allows
  │   ├─ toolAlwaysAllowedRule() → 规则匹配 'Bash' 或 'Bash(prefix:*)'
  │   └─ MCP server-level rule: 'mcp__server1' 匹配所有该服务器的工具
  │
  ├─ Step 1: Working directory checks
  │   ├─ 路径是否在 additionalWorkingDirectories 中
  │   └─ 路径是否受保护（.git/, .env, 系统目录）
  │
  ├─ Step 1b: MCP elicitations
  │   └─ -32042 错误时触发 URL 确认流程
  │
  ├─ Step 1c: Sandbox override
  │   └─ shouldUseSandbox() 返回 true 时允许
  │
  ├─ Step 1d: Safety checks
  │   ├─ dangerousPatterns（rm -rf, chmod 777, curl | bash 等）
  │   ├─ pathValidation（symlink 双重检查，免疫路径）
  │   └─ filesystem.ts 中的 62KB 深度检查
  │
  ├─ Step 1e: AI Bash classifier（feature('BASH_CLASSIFIER')）
  │   ├─ 两阶段：yoloClassifier（本地）+ transcriptClassifier（API）
  │   └─ 返回 classifierApprovable 标记
  │
  ├─ Step 1f: Subagent permission delegation
  │   └─ AgentTool 的子 agent 继承父 agent 权限
  │
  ├─ Step 1g: Denial tracking
  │   ├─ consecutiveDenials 追踪
  │   └─ shouldFallbackToPrompting() 判断是否降级为用户提示
  │
  ├─ Step 2: Mode-based behavior
  │   ├─ 'default'  → ask（除非规则允许）
  │   ├─ 'auto'     → AI 分类器决策
  │   ├─ 'plan'     → 降级为 auto 或 prompt
  │   └─ 'dontAsk'  → deny 所有 ask
  │
  ├─ Step 3: PermissionRequest hooks（头代理无 UI 场景）
  │   └─ executePermissionRequestHooks() 允许 hook 拦截
  │
  └─ Step 4: Final ask/deny
        ├─ ask  → 显示用户权限对话框
        └─ deny → 返回拒绝消息

权限规则存储结构：
alwaysAllowRules: {
  global: ['Read', 'Glob'],
  pathSpecific: ['Write(~/project/**)'],
  mcp: ['mcp__feishu__Read']
}
alwaysDenyRules: {
  global: ['Bash(rm -rf /)'],
  pathSpecific: ['Write(/etc/**)']
}
```

**关键设计：**
- **Fail-closed 默认值：** 无规则匹配 → ask（除非 mode=dontAsk）
- **规则优先级：** cliArg > command > session > global
- **免疫路径 + symlink 检查：** filesystem.ts 的 `isPathProtected()` 解析 symlink 后再检查

#### 3.3 工具注册和发现机制

```typescript
// tools.ts 17KB 中的注册逻辑
const builtinTools: Tools = [
  new BashTool(),
  new FileReadTool(),
  new FileEditTool(),
  // ... 45 个内置工具
]

// 动态注册
mcpClients.forEach(client => {
  client.tools.forEach(tool => {
    tools.push({ ...tool, mcpInfo: { serverName: client.name } })
  })
})

// 工具发现
findToolByName(tools, name): Tool | undefined
getToolNameForPermissionCheck(tool): string  // MCP 工具返回 'mcp__server__tool'
```

#### 3.4 专用工具优先的设计意图

**为什么 184 个专用工具？**
- **Read 工具：** 自动处理编码、大文件截断、二进制检测
- **Glob 工具：** 跨平台路径匹配（vs `find` 命令的平台不一致）
- **Grep 工具：** 正则表达式跨平台统一（vs `grep -E` 的平台差异）
- **Edit 工具：** 文本替换验证、冲突检测、撤销支持
- **专用 > Bash 的理由：**
  1. 安全的权限粒度（允许 Read 但不允许 Bash）
  2. 更好的错误消息
  3. 跨平台一致性
  4. 可观察性（进度、缓存、指标）

**我能如何应用：**
- 当前 AGENTS.md 中"专用工具优先"章节已经体现，但需要补充：专用工具的权限粒度是安全模型的核心
- 在飞书插件中，可以为每个飞书 API 端点创建专用工具，而非暴露通用的 `feishu_api` Bash 命令
- 权限规则应该借鉴瀑布流结构：先规则匹配，再 AI 分类，最后用户确认

---

### 4. Hook 事件驱动架构

**11 种事件类型（hookEvents.ts + hooksConfigManager.ts）**

#### 4.1 事件类型及触发时机

```typescript
type HookEvent =
  | 'PreToolUse'       // 工具执行前，input 为工具调用参数 JSON
  | 'PostToolUse'      // 工具执行后，input 为 { inputs, response }
  | 'PostToolUseFailure' // 工具失败后，input 为 { tool_name, error, error_type, is_interrupt, is_timeout }
  | 'PermissionDenied' // Auto 模式分类器拒绝后，input 为 { tool_name, reason }
  | 'Notification'     // 通知发送时，notification_type: permission_prompt | idle_prompt | auth_success | elicitation_dialog | elicitation_complete | elicitation_response
  | 'UserPromptSubmit' // 用户提交 prompt 时，input 为原始 prompt 文本
  | 'SessionStart'     // 新会话开始时，source: startup | resume | clear | compact
  | 'Stop'             // Claude 结论响应前
  | 'StopFailure'      // 模型返回错误时（非用户中断）
  | 'PreCompact'       // 压缩操作开始前
  | 'PostCompact'      // 压缩操作结束后

Always Emitted: ['SessionStart', 'Setup']  // 低噪声生命周期事件
```

#### 4.2 AsyncHookRegistry 执行机制

**AsyncHookRegistry.ts 258行**

```typescript
// 状态管理
const pendingHooks = new Map<string, PendingAsyncHook>()

type PendingAsyncHook = {
  processId: string
  hookId: string
  hookName: string
  hookEvent: HookEvent | 'StatusLine' | 'FileSuggestion'
  timeout: number                // 默认 15s
  shellCommand: ShellCommand     // 实际执行的子进程
  responseAttachmentSent: boolean
  stopProgressInterval: () => void
}

// 注册流程
registerPendingAsyncHook({ processId, hookId, asyncResponse, ... })
  ├─ 启动进度推送：startHookProgressInterval()（每秒轮询 stdout/stderr）
  ├─ 设置超时：15s（可配置）
  └─ 存入 pendingHooks Map

// 轮询响应
checkForAsyncHookResponses()
  ├─ 遍历所有 pending hooks
  ├─ 检查 shellCommand.status === 'completed'
  ├─ 解析 stdout 中的 JSON（忽略 async: true 的行）
  ├─ finalizeHook() 清理资源、emitHookResponse()
  ├─ 从 pendingHooks 删除
  └─ 如果 hookEvent === 'SessionStart'，invalidateSessionEnvCache()

// 优雅关闭
finalizePendingAsyncHooks()
  ├─ 已完成的：emit 响应
  ├─ 未完成的：kill() + emit cancelled
  └─ pendingHooks.clear()
```

**事件执行顺序：**
```
用户操作（如运行 Bash）
  ↓
PreToolUse hooks（同步 + 异步，可 block）
  ↓
[如果 async hook 返回 exit 2 → block 工具执行]
  ↓
工具执行
  ↓
PostToolUse hooks（异步，non-blocking 推送进度）
  ↓
[如果失败] → PostToolUseFailure hooks
  ↓
Stop hooks（如果是最后一条消息）
```

#### 4.3 Hook 的注册、合并、执行流程

**hooksConfigManager.ts 520行**

```typescript
// 1. 配置来源（优先级从高到低）
//    - CLI args: --hook-matcher ...
//    - Command matcher: 命令内置的 matcher
//    - Session: 会话级临时注册
//    - Global: .claude/settings.local.json 中的 hooks 配置

// 2. 注册结构
type RegisteredHookMatcher = HookCallbackMatcher | PluginHookMatcher
  where HookCallbackMatcher = {
    matcher: Partial<{
      tool_name?: string
      notification_type?: string
      source?: string
      hookName?: string
    }>
    callback: (input: string, signal: AbortSignal) => Promise<HookJSONOutput>
    priority: number  // 低优先级数字 = 高优先级执行
  }

// 3. 匹配算法
getMatchingHooks(event: HookEvent, context: any): HookCallbackMatcher[]
  ├─ 从 registeredHooks[event] 获取所有注册的 matcher
  ├─ 按 priority 排序（数字小先执行）
  ├─ 应用 matcher 过滤：
  │   ├─ 如果 tool_name 指定了，仅匹配该工具
  │   ├─ 如果 notification_type 指定了，仅匹配该通知类型
  │   └─ 否则通配所有
  └─ 返回排序后的 hook 列表

// 4. 执行顺序
executePreToolUseHooks(toolName: string, input: any)
  ├─ for each hook in getMatchingHooks('PreToolUse', { tool_name: toolName })
  │   ├─ 如果是同步：await callback(JSON.stringify(input), signal)
  │   └─ 如果是异步：registerPendingAsyncHook()，稍后 checkForAsyncHookResponses()
  └─ 如果任何 hook 返回非空 stderr → 决定是否 block
```

#### 4.4 如何通过 Hook 扩展行为

**典型用例（sessionHooks.ts 中的实现）：**

```typescript
// SessionStart Hook：初始化环境变量
registerHookMatcher({
  hookEvent: 'SessionStart',
  matcher: { source: 'startup' },
  callback: async (input: string) => {
    const config = JSON.parse(input)
    if (config.source === 'startup') {
      // 从 .env 加载环境变量
      await loadEnvFile()
      return { sessionEnvVars: { ... } }
    }
    return {}
  }
})

// Stop Hook：提取会话记忆
registerPostSamplingHook(extractSessionMemory)
  // 这其实是 PostSampling 的特殊注册方式
  // 在每次模型响应完成后自动运行
```

**我能如何应用：**
- 当前的"心跳主动出击"可以通过 SessionStart hook 实现：会话启动时注册定期检查
- 可以通过 PreToolUse hook 拦截敏感工具调用（如 feishu_im_user_message），添加额外的确认步骤
- PostToolUse hook 可用于工具调用的审计日志

---

### 5. 记忆管理最佳实践

**三层记忆架构（SessionMemory 280行 + memdir/ 8 个文件）**

#### 5.1 三层记忆的定义

| 层级 | 位置 | 示例 | 加载时机 | 生命周期 |
|------|------|------|---------|---------|
| 1. 核心身份 | `SOUL.md` | 行为准则、红线 | 每次会话启动 | 永久（用户编辑） |
| 2. 用户上下文 | `USER.md` | 称呼、时区、偏好 | 每次会话启动 | 永久（用户编辑） |
| 3. 每日上下文 | `memory/YYYY-MM-DD.md` | 今天的事件日志 | 读今天 + 昨天 | 每天新建 |
| 4. 长期记忆 | `MEMORY.md` | 精炼智慧、决策记录 | 仅主会话 | 永久（自动提炼） |

#### 5.2 SessionMemory 的自动提取和更新

**sessionMemory.ts 480行的核心流程：**

```typescript
// 1. 初始化：注册 post-sampling hook（仅在 autoCompactEnabled 时）
initSessionMemory()
  ├─ 检查：isAutoCompactEnabled()，false 则跳过
  └─ 注册：registerPostSamplingHook(extractSessionMemory)

// 2. 触发条件检查
shouldExtractMemory(messages): boolean
  ├─ 初始化检查：tokenCount >= minimumMessageTokensToInit（默认 50K）
  ├─ Token 增长检查：增量 >= minimumTokensBetweenUpdate（默认 30K）
  ├─ 工具调用检查：工具调用数 >= toolCallsBetweenUpdates（默认 5）
  └─ 安全条件：最后一条 assistant 消息无 tool_use（避免 orphaned tool_results）

// 3. 提取执行
extractSessionMemory(context: REPLHookContext)
  ├─ Guard：仅 main REPL thread（querySource === 'repl_main_thread'）
  ├─ Gate：isSessionMemoryGateEnabled()（GrowthBook 动态门控）
  ├─ 检查：shouldExtractMemory(messages)，不满足则返回
  ├─ Setup：
  │   ├─ 创建 isolated context（createSubagentContext）
  │   ├─ 确保文件存在：getSessionMemoryPath()
  │   └─ 读取当前内容：FileReadTool(memoryPath)
  ├─ 提取：
  │   ├─ 构建 prompt：buildSessionMemoryUpdatePrompt(currentMemory)
  │   └─ 运行 forked agent：runForkedAgent(querySource='session_memory')
  │       └─ 隔离的工具权限：createMemoryFileCanUseTool(memoryPath)
  │           └─ 只允许 FILE_EDIT_TOOL 且 file_path === memoryPath
  └─ 后置：
      ├─ 更新 lastSummarizedMessageId
      ├─ 记录提取事件：logEvent('tengu_session_memory_extraction')
      └─ 标记完成：markExtractionCompleted()

// 4. 提取提示词设计（prompts.ts 340行）
buildSessionMemoryUpdatePrompt(currentMemory: string, memoryPath: string)
  ├─ 指令：只编辑 <session-memory> 块，保留其他内容
  ├─ 目标：用户偏好、项目背景、关键技术栈、待办事项、决策记录
  └─ 约束：不要杜撰、保持简洁、聚焦有用信息
```

**关键设计：记忆保护**
- **Forked Agent 隔离：** `createSubagentContext()` 创建独立的 readFileState，污染不会影响主会话
- **工具权限限制：** `createMemoryFileCanUseTool()` 只允许编辑 SESSION_MEMORY.md，其他操作一律拒绝
- **查询来源保护：** `querySource !== 'session_memory'` skip autocompact，防止递归死锁
- **最后消息 ID 保护：** `setLastSummarizedMessageId()` 确保不 orphaned tool_results

#### 5.3 记忆文件加载优先级

**memdir/memdir.ts 570行的加载逻辑：**

```typescript
// findRelevantMemories.ts 的检索策略
findRelevantMemories(query: string, maxResults: number)
  ├─ 1. 扫描 memory/*.md 文件
  ├─ 2. 对每个文件：
  │   ├─ 读取内容
  │   ├─ 计算与 query 的语义相似度（向量 or 关键词匹配）
  │   └─ 按分数排序
  └─ 3. 返回 top-N 相关片段

// 手动加载（/command 或用户请求）
loadMemoryPrompt(memoryDir: string)
  ├─ 检查 memory/ 目录存在
  ├─ 列出所有 .md 文件
  ├─ 按日期排序（最新优先）
  └─ 加载最近 N 个文件
```

#### 5.4 压缩时对记忆的保护策略

**autoCompact.ts 和 compact.ts 中的保护：**

```typescript
// 1. SessionMemory 路径优先
autoCompactIfNeeded()
  ├─ trySessionMemoryCompaction() 先尝试
  │   └─ 如果成功，运行 postCompactCleanup() 并返回
  └─ 否则 fallback 到 compactConversation()

// 2. 记忆文件排除
compactConversation()
  ├─ 收集所有用户消息
  ├─ 排除 SYSTEM 消息（SOUL.md, USER.md, CLAUDE.md 等）
  ├─ 对剩余的 assistant/user 消息生成摘要
  └─ 恢复被排除的系统消息到压缩后数组

// 3. 压缩后清理
runPostCompactCleanup(querySource)
  ├─ 重置 lastSummarizedMessageId（因为消息 UUID 变了）
  ├─ 通知缓存中断：notifyCompaction()
  └─ 标记：markPostCompaction()
```

**我能如何应用：**
- 当前 AGENTS.md 已正确定义三层记忆，但 SESSION_MEMORY.md 的自动提取机制可以更明确
- 飞书集成中，应该为每个会话创建独立的 session memory，而非全局 MEMORY.md
- 压缩时的保护策略应借鉴：隔离上下文、限制工具权限、避免递归

---

### 6. 安全模型深度解析

**权限系统的 10+ 层检查（permissions.ts 1488行 + filesystem.ts 62KB）**

#### 6.1 Fail-closed 默认值设计

**核心原则：默认拒绝，显式允许**

```typescript
// PermissionMode（PermissionMode.ts）
type PermissionMode =
  | 'default'   // 安全默认：规则不匹配→ask
  | 'auto'      // AI 分类器决策
  | 'plan'      // 计划模式（降级为 auto/prompt）
  | 'dontAsk'   // 自动拒绝所有 ask

// 权限决策瀑布（PermissionResult.ts）
type PermissionDecision =
  | { behavior: 'allow'; updatedInput?: any; decisionReason?: ... }
  | { behavior: 'deny'; message: string; decisionReason?: ... }
  | { behavior: 'ask'; decisionReason?: ... }

// 默认行为：无规则匹配 → ask（除非 mode=dontAsk）
```

**Fail-closed 的体现：**
1. 没有 alwaysAllow 规则 → ask
2. Bash 分类器失败 → deny（默认拒绝不安全命令）
3. Path validation 无法解析 → deny
4. Hook 超时 → deny（15s 超时后自动拒绝）

#### 6.2 AI 分类器的两阶段决策

**yoloClassifier.ts 52KB + classifierDecision.ts 110行**

```typescript
// 第一阶段：Yolo Classifier（本地，轻量级）
classifyYoloAction(command: string): 'safe' | 'check' | 'dangerous'
  ├─ 使用小型本地模型/规则快速判断
  ├─ 'safe' → 自动允许（如 ls, cat, grep）
  ├─ 'dangerous' → 自动拒绝（如 rm -rf /, chmod 777 /etc）
  └─ 'check' → 进入第二阶段

// 第二阶段：Transcript Classifier（API，重量级）
transcriptClassifier(command: string, context: any): 'approve' | 'deny'
  ├─ 调用 API 模型进行深度分析
  ├─ 考虑上下文：用户意图、文件路径、历史行为
  ├─ 返回 classifierApprovable 标记
  └─ 如果 'approve' → 自动允许；否则 ask/deny

// 分类器结果缓存
classifierApprovals.ts
  ├─ 缓存：command → decision（过期时间 30 分钟）
  └─ 刷新：CLASSIFIER_FAIL_CLOSED_REFRESH_MS = 30 * 60 * 1000
```

**关键设计：**
- **两阶段权衡：** Yolo 快速过滤 80% 的明显安全/危险命令，Transcript 处理边界情况
- **缓存策略：** 30 分钟过期，避免重复 API 调用
- **Fail-closed：** 分类器失败时，默认 ask 而非允许

#### 6.3 免疫路径和 Symlink 双重检查

**filesystem.ts 中的深度保护**

```typescript
// 1. 免疫路径列表
const PROTECTED_PATHS = [
  '/etc', '/usr', '/var', '/root', '/bin', '/sbin',
  '/Users/*/Library', '/Users/*/.ssh', '/Users/*/.gitconfig',
  process.env.HOME + '/.claude/credentials.json',
  // ... 50+ 系统路径
]

// 2. 路径验证流程（双重检查）
validatePath(filePath: string, mode: 'read' | 'write'): ValidationResult
  ├─ 步骤 1：标准化路径（resolveSymlinks）
  │   ├─ 真实路径：fs.realpathSync(filePath)
  │   └─ 工作目录前缀：确保在 cwd 或 allowed dirs 内
  └─ 步骤 2：免疫检查（isPathProtected）
      ├─ 直接匹配：filePath 是否在 PROTECTED_PATHS 中
      ├─ 前缀匹配：filePath.startsWith(protectedPath + '/')
      └─ Symlink 二次检查：即使原始路径安全，解析后的 symlinks 也要检查

// 3. 工作目录管理
additionalWorkingDirectories: Map<string, AdditionalWorkingDirectory>
  ├─ 允许用户显式添加信任的目录
  ├─ 每个目录有 scope（session | permanent）
  └─ 权限规则中可指定路径：Write(~/project/**)
```

**我能如何应用：**
- 当前的安全检查应该借鉴双重检查：路径标准化 + 免疫列表，而非单纯的字符串匹配
- 飞书集成中，敏感文件（如 credentials）应该有独立的保护路径列表

#### 6.4 权限规则的配置和优先级

**permissionRuleParser.ts 和 permissionsLoader.ts**

```typescript
// 规则语法
'Bash'                          // 允许/拒绝所有 Bash 调用
'Bash(prefix:~/project/*)'     // 允许/拒绝特定前缀的 Bash
'Write(~/project/src/**)'      // 通配符路径
'Read'                          // 允许所有文件读取
'mcp__feishu__Read'             // 允许飞书的 Read 工具
'Agent(Explorer)'               // 拒绝特定类型的 AgentTool

// 规则来源及优先级（从高到低）
1. CLI arg（命令行参数）
2. Command（命令内置）
3. Session（会话级，.claude/session_permissions.json）
4. User（.claude/settings.local.json）
5. Managed（管理策略，企业环境）
6. Global（默认全局规则）

// 规则冲突处理
// - 更高优先级的规则覆盖低优先级
// - 同一优先级中，更具体的规则（有路径/前缀）覆盖通配规则
// - 'deny' 优先级高于 'allow'（安全优先）
```

**我能如何应用：**
- 飞书工具的权限规则应该借鉴路径语法：`feishu_im_user_message(chat_id:oc_xxx)` 限制可发消息的群组
- 会话级规则可用于临时授权（如开发任务期间允许特定目录的 Bash）

---

## 二、自我进化应用

### 1. 行为准则升级

**从 Query Loop 学习的状态驱动思维 → 更新 SOUL.md**

当前 SOUL.md 已有"容错与降级"和"先调研再动手"，但缺少**明确的状态追踪**。应用如下：

**新增行为准则：**
```markdown
### 11. 状态追踪优先
源码的 Query Loop 通过 State 对象（14 个字段）携带 7 种 continue 路径的决策状态，
而非依赖隐式变量或"心里记着"。应用：
- 长任务必须有明确的追踪状态（如 `hasAttemptedReactiveCompact` 防重复）
- 使用 `transition` 字段记录上一轮操作的原因，便于调试和测试
- "心里记着"只在当前轮有效；跨轮/跨会话的状态必须持久化到文件
```

### 2. 工作流优化

**从四层压缩和熔断器 → 更新 AGENTS.md**

**新增工作流：**
```markdown
## 操作熔断器

当某操作连续失败 N 次时，停止重试并告知用户：
- 网络请求失败 3 次 → 报告错误，不再尝试
- API 调用连续 413/429 → 切换到降级策略（如压缩、等待）
- 文件读取连续失败 → 检查路径错误，而非重复读取

这与 OpenClaw 的 autoCompact circuit breaker 设计一致：3 次失败后停止重试。
```

**优化任务管理：**
```markdown
### 任务状态追踪

复杂任务（3+ 步骤）应使用明确的追踪状态：
- 任务 ID（用于 continue 时定位）
- 已完成的步骤列表
- 失败重试计数
- 最后执行时间

这借鉴了 `autoCompactTracking` 的设计：
{ compacted: boolean, turnCounter: number, turnId: string, consecutiveFailures: number }
```

### 3. 记忆策略改进

**从 SessionMemory 机制 → 优化 MEMORY.md 和 daily notes 管理**

**当前状态：** AGENTS.md 已有三层记忆定义，但缺少自动提取机制。

**改进：**
```markdown
## 自动记忆提取（借鉴 SessionMemory）

### 触发条件
当以下条件同时满足时，自动从对话日志提炼长期记忆：
1. 累计 token 增长 >= 30K（自上次提取）
2. 工具调用次数 >= 5（表明有实质性交互）
3. 最后一条 assistant 消息无工具调用（对话自然中断）

### 提取执行
- 使用 forked agent 隔离提取，污染主会话
- 只允许编辑 MEMORY.md，其他操作拒绝
- 提取内容：用户偏好、技术决策、待办事项、项目背景
- 保留原始日志：memory/YYYY-MM-DD.md 不被修改

### 压缩保护
当执行 /compact 或自动压缩时：
1. 系统文件（SOUL.md, USER.md, MEMORY.md）始终保留，不被摘要
2. 压缩后重置追踪状态（lastSummarizedMessageId）
3. 通知缓存层，避免误报
```

### 4. 安全边界强化

**从 10+ 层权限检查 → 强化权限意识**

**新增安全规则：**
```markdown
## 权限检查瀑布流（应用自 OpenClaw）

任何敏感操作前，按顺序检查：
1. **用户显式设置** - 是否有 alwaysAllow/alwaysDeny 规则？
2. **路径免疫** - 目标路径是否在保护列表中？
3. **危险模式检测** - 是否有 `rm -rf`、`chmod 777` 等危险模式？
4. **AI 分类** - （未来）使用小型模型预判安全性
5. **最后确认** - ask 用户确认

**Fail-closed 原则：** 任何一级不确定 → 问用户，而非假设允许。
```

**飞书集成特殊规则：**
```markdown
## 飞书消息发送安全

发送飞书消息前必须：
1. 确认接收对象（chat_id 或 open_id）是否与用户意图一致
2. 确认消息内容无敏感信息（密码、密钥、个人数据）
3. 群发消息时必须有用户明确同意
4. 记录发送审计日志（用于事后追溯）
```

---

## 三、具体改进清单

| 改进项 | 当前状态 | 目标状态 | 执行计划 |
|--------|---------|---------|---------|
| **Query Loop 状态追踪** | SOUL.md 未提及状态驱动 | 新增"状态追踪优先"准则 | 更新 SOUL.md，添加第 11 条行为准则 |
| **自动记忆提取** | AGENTS.md 只有三层定义，无自动提取机制 | 引入 SessionMemory 的触发条件 + forked agent 隔离 | 更新 AGENTS.md 的"记忆系统"章节，补充提取流程和压缩保护 |
| **操作熔断器** | 无明确的失败重试限制 | 引入 3 次失败后停止重试的规则 | 更新 AGENTS.md 的"容错与降级"章节，新增熔断器说明 |
| **任务状态追踪** | Todo/Task 跟踪但未定义结构 | 借鉴 `autoCompactTracking` 设计结构化任务状态 | 更新 AGENTS.md 的任务管理章节，定义追踪字段 |
| **权限检查瀑布流** | "安全优先"但未细化 | 引入 5 层检查流程 + Fail-closed | 更新 SOUL.md 的"安全优先"章节，细化每层检查 |
| **专用工具边界** | 已定义但未强化理由 | 补充专用工具的 4 大优势（安全、错误、跨平台、可观测） | 更新 AGENTS.md 的工具使用原则，强化专用 > Shell |
| **Hook 扩展机制** | 未提及 | 引入 11 种事件类型及扩展能力 | 新增 AGENTS.md 的 Hook 扩展章节（可选） |
| **飞书消息安全** | FEISHU_TOOLS.md 有工具定义，无安全规则 | 引入消息发送的 4 步安全检查 | 创建/更新 FLYSPECK.md 或飞书专用规则文件 |

---

## 四、学习总结

### 从 OpenClaw 源码中提取的 5 条最关键设计原则

**1. 状态驱动的 Continue 机制**
Query Loop 的 7 种 continue 路径不是靠"if-else"判断，而是通过 `State.transition` 字段显式追踪上一轮的操作原因，配合 `hasAttemptedReactiveCompact` 等布尔值防重试。这使复杂的决策逻辑变得可测试、可调试、可预测。**应用：任何多轮任务都要有明确的状态追踪，而非依赖隐式上下文。**

**2. 四层压缩的渐进策略**
Snip（零成本删除）→ MicroCompact（零成本缓存清理）→ Collapse（可选的粒度摘要）→ AutoCompact（AI 摘要）。每一层都是前一层的 fallback，且成本递增。**应用：资源管理应该先从零成本操作开始，只有必要才升级到 AI 摘要。**

**3. 专用工具而非通用 Shell**
184 个专用工具的设计不是装饰，而是安全模型的核心：专用的 Read/Edit/Glob/Grep 提供比 Bash 更细的权限粒度、更好的错误消息、跨平台一致性。**应用：为每个飞书 API 端点创建专用工具，而非暴露通用 API 调用。**

**4. Fail-closed 的权限瀑布流**
10+ 层检查从规则匹配到 AI 分类，每一层失败都走向更保守的决策（allow → ask → deny）。默认 ask 而非默认 allow。**应用：敏感操作必须有降级流程，任何一级的不确定都导向用户确认。**

**5. Forked Agent 的隔离机制**
SessionMemory 提取、AutoCompact 摘要、Context Collapse 都运行在 forked agent 中，独立的 readFileState、工具权限、abortController。这防止了"污染主会话"的问题。**应用：后台任务必须隔离上下文，避免影响用户的主线程体验。**

---

**本次学习生成的文件：**
- `memory/openclaw-deep-study-round2-report.md`（本文件）

**建议的后续动作：**
1. 更新 `SOUL.md`，添加"状态追踪优先"行为准则
2. 更新 `AGENTS.md`，补充自动记忆提取、熔断器、权限瀑布流
3. 创建飞书专用安全规则（如 `memory/feishu-message-rules.md`）
