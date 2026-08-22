# Implementation Plan

## Overview

本计划按 Phase A（安全与单一 Chat Run 内核）→ Phase B（上下文能力）→ Phase C（DSH Experimental Agent）严格推进。每个阶段先完成实现，再由独立守卫和浏览器验收封口；阶段未全绿时，后续阶段不得启动。所有任务均为必做项，没有 optional 跳过口径。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": [1], "note": "先建立公共资源权限策略；任何上下文、搜索、历史和 MCP 均不得先于它实现" },
    { "wave": 2, "tasks": [2, 3], "note": "可信 HostContext 与持久化模型可并行，均依赖 Wave 1 的安全边界" },
    { "wave": 3, "tasks": [4, 7], "note": "Run 创建协议与采纳 fail-closed；分别依赖 HostContext/持久化与权限/收据模型" },
    { "wave": 4, "tasks": [5, 6], "note": "Run coordinator/SSE 与 NativeEngine 均依赖 typed run contract" },
    { "wave": 5, "tasks": [8, 12], "note": "前端 canonical transport 与服务端配额/审计可并行，依赖可执行 native run" },
    { "wave": 6, "tasks": [9], "note": "建立唯一 PlatformAiChatPanel 并迁移全部宿主" },
    { "wave": 7, "tasks": [10], "note": "在统一核心上一次性收口 sanitize 与敏感缓存" },
    { "wave": 8, "tasks": [11], "note": "在稳定 DOM 上完成响应式与可访问性" },
    { "wave": 9, "tasks": [13], "note": "Phase A 独立守卫、并发与浏览器基线；未通过不得进入后续阶段" },
    { "wave": 10, "tasks": [14, 16, 18, 20, 22], "note": "Phase B 五条后端能力在 Phase A 绿后并行，目标资源彼此独立" },
    { "wave": 11, "tasks": [15, 17, 19, 21, 23], "note": "各能力的前端或最终接线，分别依赖对应 Wave 10 任务" },
    { "wave": 12, "tasks": [24], "note": "Phase B 独立行为守卫与浏览器验收" },
    { "wave": 13, "tasks": [25, 27], "note": "MCP REST 安全边界与 DSH SDK/Cordis discovery 可并行" },
    { "wave": 14, "tasks": [26], "note": "audit-data MCP server 依赖 scoped REST endpoints" },
    { "wave": 15, "tasks": [28], "note": "DshEngine 依赖 MCP server 与真实 Cordis handshake" },
    { "wave": 16, "tasks": [29, 30], "note": "脱敏/注入/工具审计与 capability/local-only 接线可在 DshEngine 稳定后并行" },
    { "wave": 17, "tasks": [31], "note": "Phase C 双用户、取消、进程、端口和 egress 真实运行时验收" },
    { "wave": 18, "tasks": [32], "note": "跨阶段守卫归并与 CI job 接线" },
    { "wave": 19, "tasks": [33], "note": "守卫稳定后执行变异，避免同波自证" },
    { "wave": 20, "tasks": [34], "note": "变异全 RED 后执行完整 Playwright 五角色/三视口验收" },
    { "wave": 21, "tasks": [35], "note": "clean checkout、三件套机器校验、产物跟踪和临时文件清理" }
  ]
}
```

---

## Tasks

## Phase A — 安全基线与单一 Chat Run 内核

- [x] 1. 建立公共资源权限策略与 `ResourceAccessResolver`
  - 从 `ContextBuilder` 私有权限辅助和知识库 route/service 中提取公共 `KnowledgeAccessPolicy`，让 tree/list/read/create 都显式接收 current user 与 project scope
  - 新建 `backend/app/services/ai_chat/access.py`，编排项目成员关系、`gate_wp`/批量底稿可见性、知识库 access policy、角色分类和 `scope_cycles`
  - 定义 action capability：read/search/history/clear/upload/note-create/adopt/review/agent-run；角色只作上界，不复制第二套资源权限算法
  - 所有拒绝在 label/摘要/正文/索引查询前发生；外部使用不可枚举响应，内部写 denial audit
  - 建立五角色 × 跨项目 × 跨循环 × private/project_group 的共享测试夹具
  - **Validates: Requirements 2.1, 2.2, 2.4, 2.5, 2.6, 2.7, 2.8**
  - **Properties: 1, 3, 4**

- [x] 2. 实现可信 `HostContextResolver` 并纠正全部宿主契约
  - **Depends on:** Task 1
  - 新建 `HostType`、`HostRef`、`AuthorizedHostContext` 与 `HostContextResolver`
  - 为 workpaper/note/report/knowledge_doc/knowledge_folder/global_knowledge 建专属 resolver，禁止 note/report 回退到 WorkingPaper loader
  - 项目、年度、resource ID 由服务端反查；客户端 assertion 不一致返回 `host_context_mismatch`
  - 修正 `WorkpaperEditor`、`ReportView`、`DisclosureEditor`、`KnowledgeBase`、全局 DshPanel 与独立窗口的输入契约；无项目页面使用显式 global mode 或禁用项目工具
  - 为每种 host 写真实 route/service 集成契约，断言正确业务 loader 被调用
  - **Validates: Requirements 2.3, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7**
  - **Properties: 2, 5**

- [x] 3. 增强 AI chat 持久化模型与并发约束
  - **Depends on:** Task 1
  - 实施时先查询 migration status 获取下一个可用 V 号，不在代码或 spec 预占固定编号
  - 扩展 `ai_chat_sessions`：server-generated session key、host type/id、audit year、review mode、last message time；回填并合并重复 locator 后建立 `(user_id, session_key)` 唯一约束
  - 扩展 `ai_chat_messages`：run/status/content hash/context manifest；复用已存在的 citations/model/token/latency 字段，不重复造列
  - 新增 `ai_chat_runs`、`ai_chat_tool_calls`、`ai_chat_attachments`、`ai_chat_action_receipts`，全部使用幂等约束和必要索引
  - 所有迁移使用幂等 DDL；禁止在同一 enum migration 事务中立即写新 enum 值
  - history 改为倒序取最近 N 条、外层正序返回，并携带真实 message/run metadata
  - **Validates: Requirements 4.10, 4.11, 7.3, 8.2, 8.3**
  - **Properties: 6, 10, 21**

- [x] 4. 定义 typed contract 并实现幂等 Run 创建 API
  - **Depends on:** Tasks 2, 3
  - 在服务端单一模块定义 `ChatRunRequest`、`ChatEventType`、`ChatEvent`、`EngineCapabilities`、稳定 error codes；通过 OpenAPI 暴露前端类型
  - 新增 `POST /api/ai-chat/runs`：先 resolve/authorize HostContext，再 upsert session/run/user message
  - 唯一键为 `(actor_id, session_id, idempotency_key)`；重复请求返回原 run，不重复调用 engine
  - 新增 run status compare-and-set，保证 terminal event 恰好一个
  - 请求体拒绝 engine、scope、资源正文、客户端 message content 等越权字段
  - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 10.2**
  - **Properties: 6, 7**

- [x] 5. 实现 `ChatRunCoordinator`、SSE replay、取消与 drain
  - **Depends on:** Task 4
  - 新增有界执行队列与 Redis lease，确保一个 run 只有一个 executor；队列满返回 typed quota error
  - engine events 写入带 TTL 的 Redis Stream；数据库只保存 run/message/tool 摘要，不逐 token 写行
  - 新增 `GET /runs/{id}/events`，支持 `Last-Event-ID`、心跳和 replay；接入现有 `sse_registry` drain
  - 新增幂等 `POST /runs/{id}/cancel`，CancelSignal 传播到 engine/tool/child；terminal 后拒绝业务事件
  - 启动恢复扫描 lease-expired run，按“无副作用 + retry limit”重排或标记 interrupted
  - 注入 terminal race、断流、重连、服务 drain 和 cancel/tool race 做行为测试
  - **Validates: Requirements 4.1, 4.5, 4.7, 4.8, 4.9, 4.12**
  - **Properties: 7, 8, 9**

- [x] 6. 实现统一 `ChatEngine` 与 `NativeEngine`
  - **Depends on:** Task 4
  - 新建 typed `ChatEngine.run(request, cancel) -> AsyncIterator[ChatEvent]` 与 capabilities contract
  - `NativeEngine` 复用现有 AIService、熔断器、并发限制、single-system merge 和本地 vLLM，不新写模型 HTTP client
  - 将模型 chunk 转为 delta；保存 model/usage/latency；识别 fail-soft placeholder 并转 typed error
  - ContextBuilder 异常、LLM placeholder、熔断、timeout 均不保存 completed assistant，不产生 success `done`
  - engine 只由服务端 config/feature flag 选择，请求字段不能覆盖
  - **Validates: Requirements 10.1, 10.2, 10.3, 10.5, 10.7, 12.4, 12.5, 12.9**
  - **Properties: 7, 24, 33**

- [x] 7. 把 AI 内容采纳改为 server-authoritative、幂等且 fail-closed
  - **Depends on:** Tasks 1, 3
  - `AdoptRequest` 改为 message ID + HostRef + target + idempotency key，不信任客户端 content/project assertion
  - 校验 message→run→session→actor→HostContext，读取服务端 completed assistant 正文与 content hash
  - 使用 `ai_chat_action_receipts` 防重；`wrap_ai_output_with_log`/commit 任一步失败则回滚并返回 `adopt_log_failed`
  - 仅非空且真实存在的 `ai_content_log_id` 可返回“已进入确认流”
  - 写平台哈希链审计，保存 ID/hash 而非重复正文
  - 注入日志创建异常、commit 异常、篡改 message/project/host/content 做反向测试
  - **Validates: Requirements 8.1, 8.6, 8.7, 8.8, 8.9**
  - **Properties: 22, 32, 33**

- [x] 8. 收敛前端 canonical SSE transport 与 run state
  - **Depends on:** Tasks 4, 5
  - 增强既有 `frontend/src/utils/sse.ts`：跨 chunk buffer、CRLF/LF、多行 data、event/id、心跳、AbortSignal、Last-Event-ID
  - 新建 `usePlatformAiChat.ts`，作为唯一 run/session/message/cancel/reconnect 状态；消费 OpenAPI/generated contracts
  - 保留用户草稿、quota 和 context manifest；断流只重订阅原 run，不重复 POST
  - 对随机字节分片做 property test，基线事件序列必须一致
  - 禁止在 composable 内再实现一套 ReadableStream 行解析
  - **Validates: Requirements 1.8, 4.1, 4.4, 4.8**
  - **Properties: 9, 39**

- [x] 9. 建立 `PlatformAiChatPanel` 并迁移所有宿主
  - **Depends on:** Task 8
  - 新建唯一核心 `PlatformAiChatPanel.vue`、`ChatMessageList.vue`、`ChatComposer.vue`、`ChatContextInspector.vue`
  - 禁止创建 `AiChatPanel.vue`（与既有 `AIChatPanel.vue` 在 Windows 路径冲突）或第二个 `useAiChat.ts`
  - `DshPanel` 保留布局壳并移除 iframe/postMessage；Workpaper/Report/Disclosure/Knowledge/独立窗口改为 HostRef adapter
  - badge 来源改为 canonical message/run event；新窗口打开平台聊天 route
  - 迁移完成后删除无消费方的旧核心组件/composable/parser；有独立布局职责者只保留 adapter
  - 断言所有宿主看到同一 session/history/terminal status
  - **Validates: Requirements 1.1, 1.4, 1.5, 1.8, 1.9, 1.10, 3.5**
  - **Properties: 5, 39**

- [x] 10. 统一不可信内容渲染并清理浏览器敏感缓存
  - **Depends on:** Task 9
  - 所有 AI/mention/OCR/citation/manifest HTML 统一走 `marked.parse()` → 既有 `useSanitize()` → `v-html`
  - 删除手写 Markdown 正则和旁路 sanitizer；真实 mount 后检查 DOM，不用“符号出现次数”判据
  - 消息/OCR/mention/attachment/prompt 不写 localStorage；服务端 history 为权威来源
  - logout、user switch、首次升级清理遗留 `doc_ai_chat_*`；面板宽度等非敏感偏好可保留
  - 构造 script/iframe/event handler/dangerous URL/SVG payload 覆盖五类来源
  - **Validates: Requirements 1.3, 13.1, 13.2, 13.3, 13.4**
  - **Properties: 34, 35**

- [x] 11. 完成三档响应式与可访问性
  - **Depends on:** Task 10
  - `>1400px` 独立列、`769–1400px` fixed drawer、`≤768px` 全屏 + safe-area
  - 触发器/icon/resizer 改语义 button；支持触摸、键盘微调、Escape、focus trap、焦点恢复和滚动隔离
  - mention/消息/错误/quota 使用正确 combobox/listbox/live-region 语义，文案全中文且不只靠颜色
  - `aria-live` 对流式文本节流，尊重 reduced-motion
  - 在 390/768/1400px 和纯键盘流程下做组件测试
  - **Validates: Requirements 1.2, 1.6, 1.7, 14.6**
  - **Properties: 37**

- [x] 12. 接通真实限流、哈希链审计与运行指标
  - **Depends on:** Tasks 5, 6
  - 新增 AI chat/run/MCP/DSH queue 配额配置，并确保 route matcher 真实命中，不保留未消费 prefix 常量
  - quota/error event 返回 remaining/reset/retry_after；前端保留草稿并显示中文倒计时
  - run started/terminal、access denied、note/adopt、attachment cleanup 进入哈希链审计
  - 结构化指标覆盖 active/queued、queue wait、latency、tokens、cancel latency、denials、attachment bytes/cleanup failures
  - 审计与指标不记录 token、完整正文、附件内容或未脱敏上下文
  - **Validates: Requirements 12.6, 12.7, 12.8, 13.5, 13.6, 13.7**
  - **Properties: 32, 36**

- [x] 13. Phase A 行为守卫、并发测试与浏览器基线
  - **Depends on:** Tasks 1–12
  - 后端覆盖 Properties 1–10、22、24、32–33；前端覆盖 Properties 34–39 中 Phase A 项
  - 真跑 100 并发 session/run idempotency、terminal race、cancel/tool race、Last-Event-ID replay
  - 五角色验证 host/search/history/clear/adopt 的允许与拒绝
  - Playwright smoke：全部宿主打开统一面板、发送 native 对话、取消、重连、切账号无缓存泄漏
  - 故意移除 gate、改坏 terminal CAS、拆断 SSE JSON、恢复 localStorage 正文，守卫必须分别打红
  - Phase A 未全绿 SHALL 停止执行 Task 14 及以后任务
  - **🔴 已发现 6 项必修缺陷（Task 13 守卫暴露）→ ✅ 已全部修复：**
    1. ~~`chatRunState` 缺少前端终态 guard：error 后仍接受 dispatch `done`~~ → ✅ 已加终态 guard（`isTerminal` 时 early return）
    2. ~~`chatRunState` 缺少前端终态 guard：cancelled 后仍接受 dispatch `delta`~~ → ✅ 同上
    3. ~~旧 `AiChatPanel.vue` 未删除（Windows 路径冲突风险）~~ → ✅ 已删除（零消费方死代码）
    4. 旧 `useDocAiChat.ts` 存在但仅作 adoptContent adapter（NoteAiFillDialog 消费方）→ ✅ 不含独立 SSE，不阻塞
    5. 宿主页面注释中仍提及 `DocAiChatPanel`（纯文本注释，非模板引用）→ ✅ 实际 import/template 已全迁移
    6. ~~`marked` 对 `javascript:` 链接语法路径~~ → ✅ marked 不解析为 `<a>` 标签（输出纯文本），sanitizer 兜底 DOM href
  - **Validates: Requirements 14.1, 14.4**
  - **Properties: 1–10, 22, 24, 32–39**

---

## Phase B — 上下文能力

- [x] 14. 实现 mention 聚合搜索、授权加载与 Context Manifest
  - **Depends on:** Task 13
  - 服务端单一 `MentionType` schema 覆盖 7 类；前端类型由 OpenAPI 生成或运行时 schema 对账
  - `GET /api/ai-chat/mentionable` 在 ResourceAccessResolver 后统一返回 `{type,id,label,sublabel,jump_route}`，过滤 null instance
  - ContextBuilder 改为消费 `AuthorizedHostContext`、authorized mentions、attachments、review context
  - 建立 `ContextBudgetPolicy`；宿主/mention/OCR/review/RAG 共用预算，生成 included/trimmed/denied/unavailable manifest
  - 修复知识树 current user/project scope 传递；全宿主迁移后删除 `extra_scopes` 字段、旧 URL 和旧消费方
  - jump route 点击仍由目标页面重新授权
  - **Validates: Requirements 5.2, 5.3, 5.5, 5.6, 5.7, 5.8, 5.9**
  - **Properties: 11, 12, 14**

- [x] 15. 实现前端 mention 与 Context Inspector
  - **Depends on:** Task 14
  - 新建 `ChatMentionPicker.vue` / `useAiMention.ts`，支持 `@`、防抖、键盘导航、多选、tag 移除与类型过滤
  - 搜索失败/超时/能力不可用与成功空结果使用不同状态、DOM 和中文文案
  - `ChatContextInspector` 展示实际纳入、裁剪、拒绝、unavailable、version、stale 与原因，不把客户端 label 当权威
  - 被裁剪 mention 可见；context manifest 与 citation jump 可操作且重新鉴权
  - **Validates: Requirements 5.1, 5.4, 5.7, 5.9**
  - **Properties: 12, 13**

- [x] 16. 实现会话附件 metadata、安全上传与 OCR 状态机
  - **Depends on:** Task 13
  - 使用 Task 3 的 `ai_chat_attachments`；上传只返回 attachment ID/状态，不返回服务器路径
  - 同时校验扩展名、MIME magic、数量、大小、图片像素、PDF 页数/解压上限；随机 storage name，拒绝路径穿越
  - metadata 绑定 owner/project/session/run/hash/status/expiry/legal hold；重复 owner/session/hash 幂等
  - 复用 `UnifiedOCRService`，区分 HTTP unavailable、in-process failure、timeout、empty、success/cancelled
  - 下一轮 run 逐个校验 attachment owner/host/session；OCR 文本经定界、脱敏后进入 manifest
  - cleanup 先删文件再标 deleted；失败保留 metadata 可重试，legal hold 跳过并记录审计
  - **Validates: Requirements 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9**
  - **Properties: 18, 19, 20**

- [x] 17. 实现附件、粘贴、OCR 展开与清理交互
  - **Depends on:** Task 16
  - 新建 `ChatAttachmentPicker.vue`，支持按钮、拖拽、clipboard image、上传进度、取消与重试
  - 分别显示 uploaded/OCR running/succeeded/empty/failed/cancelled；空文本允许用户补充说明
  - OCR 原文展开走统一 sanitizer；只向 run 提交 attachment IDs
  - clear session/删除附件时显示异步清理状态，失败可重试且不假报成功
  - **Validates: Requirements 7.1, 7.6, 7.7, 7.9**
  - **Properties: 19, 20, 34**

- [x] 18. 实现幂等项目笔记转存服务
  - **Depends on:** Tasks 3, 13
  - `POST /api/ai-chat/notes` 只接收 completed assistant message IDs、用户确认名称、HostRef 和 idempotency key
  - ResourceAccessResolver 校验 `knowledge.create`；从数据库读取问题/回复/citations/hash
  - notes folder 定位规则单一真源，使用数据库唯一约束/upsert，禁止仅“先查后建”
  - 使用 `ai_chat_action_receipts` 防重；文档写入 project/year/tags/run/message/citation/hash，并触发现有索引
  - 哈希链记录 note saved；失败回滚 receipt，可安全重试
  - **Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.8, 8.9**
  - **Properties: 21, 32**

- [x] 19. 实现消息选择、复制和项目笔记 UI
  - **Depends on:** Task 18
  - `ChatMessageList` 支持单选/多选 completed assistant message；复制按服务端顺序拼接
  - 转存前用 `ElMessageBox.prompt` 要求用户确认名称，不静默生成时间戳
  - 失败保留选择与名称并显示可重试原因；成功返回并打开授权 jump route
  - 重复点击复用同一 idempotency key，避免双文档
  - **Validates: Requirements 8.2, 8.5**
  - **Properties: 21**

- [x] 20. 实现服务端复核模式与 single-system assembly
  - **Depends on:** Task 13
  - 仅 AuthorizedHostContext=workpaper 且有权 sheet 时加载 `ReviewPromptService.load_prompt(wp_code,sheet_name)`
  - `GET /review-prompt` 只返回 source_level/tips/checklist/risk_areas/version，不返回正文
  - `SystemMessageAssembler` 将政策、review prompt、数据定界合成一条 system
  - prompt 加载失败以 typed error 终止，不静默普通问答；review mode 保存到 server session
  - **Validates: Requirements 9.1, 9.2, 9.3, 9.5, 9.6**
  - **Properties: 23**

- [x] 21. 实现前端复核模式条
  - **Depends on:** Task 20
  - 新建 `ChatReviewModeBar.vue`，按 host capability 显示/禁用并提供中文原因
  - 展示 source_level/tips/checklist/risk_areas/version；base 时明确“当前使用通用复核模板”
  - 模式从 server session 恢复，不写无作用域 localStorage
  - **Validates: Requirements 9.1, 9.4, 9.5**
  - **Properties: 23, 24**

- [x] 22. 接入 `AddressCoordinateIndexSource` 与迁移
  - **Depends on:** Task 13
  - 🔴 前置检查本地 embedding health；不可用则任务保持阻塞并登记，不以空索引完成
  - 实施时查询最新迁移号；向真实 `knowledge_source_type_enum` 添加 `address_coordinate`，使用 `IF NOT EXISTS`，迁移内不写使用新 enum 的 DML
  - 实现并注册 `AddressCoordinateIndexSource`，复用现有增量更新/fingerprint/stale；文本只来自 AddressEntry/ACNR 字段
  - ACNR canonical invalidation event 驱动更新；legacy invalidate 通过统一桥接，不散挂调用点
  - 搜索严格限定 source type；embedding down 返回 `semantic_unavailable`，禁止 BM25/ILIKE 冒充
  - **Validates: Requirements 6.2, 6.3, 6.4, 6.5, 6.6**
  - **Properties: 15, 16**

- [x] 23. 接通地址 mention、权限、脱敏与跳转
  - **Depends on:** Tasks 14, 22
  - address 候选返回稳定 addr ID、label/domain/URI/formula ref/jump route；当前值只在授权后解析
  - 复用 ResourceAccessResolver 与 ExportMaskService；未授权不能搜索 label 或直接 ID 读取
  - manifest 展示 version/stale/unavailable；目标跳转再次鉴权
  - 做源坐标 → IndexSource → runtime search → mention → context 的四边契约，不只检查索引表存在
  - **Validates: Requirements 6.1, 6.6, 6.7**
  - **Properties: 15, 17**

- [x] 24. Phase B 行为守卫与浏览器验收
  - **Depends on:** Tasks 14–23
  - 后端覆盖 Properties 11–23；前端覆盖 mention/OCR/note/review 的真实 DOM 与失败态
  - 注入知识 tree 越权、mention 直接 ID、token budget、embedding down、OCR 五态、跨用户 attachment、cleanup failure、并发 note save、prompt failure
  - Playwright 完成：`@` 多选与裁剪 manifest、粘贴截图 OCR、空文本补充、选中转存、复核模式、地址 unavailable/stale
  - 故意删 manifest 消费方、放宽 attachment owner、改错 note unique key、开启语义 fallback，守卫须分别打红
  - Phase B 未全绿 SHALL 停止执行 Task 25 及以后任务
  - **Validates: Requirements 14.2, 14.4**
  - **Properties: 11–23, 34**

---

## Phase C — DSH Experimental Agent

- [x] 25. 实现 MCP scoped REST endpoints 与 token 生命周期
  - **Depends on:** Tasks 13, 24
  - 新增 `/api/ai-chat/mcp/*`，全部调用 ResourceAccessResolver、scope/project/run/expiry 校验、ExportMaskService、行数/字节/调用预算和哈希链审计
  - scoped token 绑定 user/project/run/read-only scope/exp，不透传长期登录 token
  - 明确 auditor/manager/partner/qc/eqcr 的脱敏映射；未知角色 fail-closed
  - token 撤权、过期、cancel 和 child inheritance 使用同一 security context
  - 双用户交换 token/run/project/cycle 均返回拒绝且无旁路
  - **Validates: Requirements 11.5, 11.7, 11.8, 11.9, 12.6, 12.7**
  - **Properties: 28, 29, 30, 32**

- [x] 26. 实现 `audit-data` MCP stdio server
  - **Depends on:** Task 25
  - 新建 `tools/audit-data-mcp/server.py`，只通过 `AUDIT_API_BASE` 调 MCP REST endpoints，不 import DB driver/ORM，不读取 DB/Redis/平台密钥
  - 工具 schema 从服务端 `MCP_READONLY_TOOLS` 生成/校验，运行时集合不多不少
  - 工具覆盖 wp_list/wp_read/tb_query/addr_lookup/kb_search/note_read/review_prompt，全部 `readonly=true`
  - stdio only，不监听 TCP；内部 transport command 固定，不接受 Agent 自定义 shell command
  - 构造调用频率、返回字节、run budget 超限，必须明确失败且停止后续调用
  - **Validates: Requirements 11.2, 11.3, 11.4, 11.8**
  - **Properties: 26, 27, 29**

- [x] 27. 完成 DSH SDK discovery、精确 pin 与 custom Cordis smoke
  - **Depends on:** Task 24
  - 验证实际 SDK artifact/version/commit/hash、Python import、配置 schema；不得以 `0.0.0.dev0` 或 `latest` 作为生产 pin
  - custom Cordis 必含 `dsh-sdk-jsonrpc-server`、agent spine、本地 vLLM provider、dsh MCP client 和内部 stdio transport
  - 区分运输子进程与 Agent 工具；实际 Agent catalog 不得含 fs-write/bash/shell/subprocess command/web-fetch
  - 真跑 SDK import、Cordis load、JSON-RPC handshake、MCP handshake 与 fake local model smoke
  - 输出并断言 effective model route/tool catalog，不读取“候选配置里出现 localhost”代替
  - `D:\DeepHorness` 保持 vendor 只读；不修改上游源码
  - **Validates: Requirements 10.6, 11.1, 11.2, 11.3, 12.1, 14.7**
  - **Properties: 25, 26**

- [x] 28. 实现 `DshEngine`、有界 worker 与取消传播
  - **Depends on:** Tasks 26, 27
  - DshEngine 消费统一 `AuthorizedChatRunRequest` 并产 typed ChatEvent；MCP/tool/subagent event 映射到统一协议
  - 每 run 使用独立 MCP stdio process；若 DSH root 无法证明 reset，则 root 也不跨 principal 复用
  - 实现 active/queue/run-timeout/process-TTL 配置与 backpressure；不得按请求无界拉起进程
  - cancel/timeout/terminal 传播并清理 root、children、MCP process、session files/JSONL；清理失败记录审计和指标
  - DSH/MCP/handshake 失败返回 `engine_unavailable`，NativeEngine invocation count 必为 0
  - **Validates: Requirements 4.7, 10.2, 10.5, 11.6, 11.7, 11.11, 11.12**
  - **Properties: 8, 25, 28, 29, 38**

- [x] 29. 接通 DSH 脱敏、提示注入边界与工具审计
  - **Depends on:** Task 28
  - native/DSH/MCP 返回统一走显式五角色 ExportMaskService mapping
  - 不可信底稿/知识/OCR 使用数据定界；服务器 REST gate 独立于模型提示执行权限
  - 用 deterministic fake agent 尝试被注入内容诱导的越权工具/参数，断言 endpoint 拒绝；不要求真实模型轨迹每次相同
  - 每个 tool call 产生 started + finished/failed 哈希链记录，字段含 run/actor/project/tool/arg hash/result bytes/duration/error
  - 审计中扫描并拒绝 scoped token、完整敏感正文和附件内容
  - **Validates: Requirements 11.9, 11.10, 12.6, 12.7**
  - **Properties: 30, 31, 32**

- [x] 30. 接通 capability、feature flag、启动与 local-only 自检
  - **Depends on:** Task 28
  - `/capabilities` 返回实际 engine capability；前端禁用 tools/subagents 等不支持入口并显示中文原因
  - DSH 由服务端 experimental flag + project allowlist 启用，客户端不可覆盖；未验收项目保持 native
  - 启动脚本不再为 iframe 启动 DSH Web UI；只检查/启动 SDK runtime 所需组件
  - effective route 若为 cloud/bundled default/未知 provider，拒绝启动并记录 `local_only_violation`
  - embedding/OCR/model/MCP 各自健康与错误码分离；部署配置列出全部本地依赖
  - **Validates: Requirements 10.1, 10.3, 10.4, 10.5, 10.6, 12.1, 12.2, 12.4**
  - **Properties: 24, 25, 26**

- [x] 31. Phase C 双用户、取消、进程、端口与 egress 真实验收
  - **Depends on:** Tasks 25–30
  - 两用户同时运行跨两底稿多步 Agent，交换 token/run/project 均拒绝，返回数据与 session 文件不串用
  - 在 root/tool/child 三个阶段取消，确认 descendants 停止、后续 tool count 不增长、占用归零
  - 达到 active/queue limit，确认不增加进程、请求有界排队或明确失败
  - 观察真实进程树、监听端口、effective tool catalog、model endpoint；MCP 无 TCP 监听
  - 在受控测试环境阻断/监视公网，证明模型、embedding、OCR、MCP、plugin 无 egress
  - 销毁后扫描 root/session/JSONL/log/temp 不含前一 principal 数据
  - Phase C 未全绿 SHALL 不扩大 project allowlist
  - **Validates: Requirements 11.4, 11.5, 11.6, 11.11, 11.12, 12.2, 12.3, 14.3, 14.7**
  - **Properties: 25–32, 38**

---

## Governance, Mutation and Final Acceptance

- [x] 32. 建立跨阶段后端/前端守卫与独立 CI jobs
  - **Depends on:** Tasks 13, 24, 31
  - 后端按 access/host/run/context/attachment/note/review/MCP/DSH 分组覆盖 Properties 1–33、38
  - 前端按 transport/core/sanitize/a11y/mention/OCR/note/review/capability 覆盖 Properties 9、13、19–24、34–39
  - 守卫使用真实函数执行、状态机、DB 约束、mount DOM、运行进程/网络证据；静态扫描只作补充
  - CI job 在 clean checkout 安装/加载必要测试资产；DSH runtime job可按明确 runner capability 分层，但不得把未执行写成通过
  - 产物清单逐个执行 `git status --porcelain -- <path>`，正式测试/脚本出现 `??` 即登记未完成
  - **Validates: Requirements 14.4, 14.5**
  - **Properties: 1–40**

- [x] 33. 执行完整变异检验并修复假绿守卫
  - **Depends on:** Task 32
  - 新建 mutation manifest/runner，复用 `_mutation_kit`，`guard_files` 纳入覆盖分母
  - 变异至少包含：移除前置 gate、调换 host loader、去掉 unique、error 后发 done、取消不传 child、SSE 拆包、放宽 attachment owner、采纳信任客户端、启用 semantic fallback、Cordis 加 bash、切 cloud model、复用跨用户 token、移除 sanitize、恢复 localStorage 正文
  - 每个变异必须命中唯一锚点并由预期测试打红；记录 RED/GREEN/ANCHOR-MISS/WRONG-TEST
  - `--check-anchors` 在 clean source 上运行；CRLF 锚点不得用跨行裸字符串
  - 所有 GREEN/ANCHOR-MISS/WRONG-TEST 修复前不得进入 Task 34
  - **Validates: Requirements 14.4**
  - **Properties: 1–40**

- [x] 34. 完整 Playwright 五角色、三视口与用户可见行为验收
  - **Depends on:** Task 33
  - 视口 390/768/1400px：打开/关闭/拖拽/全屏/focus/keyboard/badge/new-window
  - 五角色：当前 host、跨循环 mention、private/project_group 知识、note/adopt/review/agent capability 的允许与拒绝均有中文反馈
  - native 链路：发送、stream、断流重连、取消、history、quota、Context Manifest、XSS
  - Phase B：mention 多选裁剪、粘贴 OCR 五态、note 幂等与失败保留、review base 提示、address unavailable/stale
  - Phase C：capability、engine unavailable 不 fallback、多步工具可见、取消、queue limit
  - 浏览器网络面板核对 run 只创建一次、Last-Event-ID replay、不出现旧 `/doc` 双轨和 DSH Web UI iframe 请求
  - **Validates: Requirements 1.1–1.10, 5.1, 5.4, 7.1, 8.5, 9.4, 10.4, 13.1, 13.6, 14.6**
  - **Properties: 9, 13, 19, 21, 23–25, 34–39**

- [x] 35. clean checkout、三件套一致性与收口复盘
  - **Depends on:** Task 34
  - ✅ 三件套 diagnostics：零错误
  - ✅ AC 覆盖：120/120，Property 覆盖：40/40，无 phantom 引用
  - ✅ 依赖图：35 tasks / 21 waves / 无同波强依赖
  - ✅ 迁移号：V149（本 spec 新增 V147 + V149），幂等 IF NOT EXISTS
  - ✅ 变异 --check-anchors：15/15 通过
  - ✅ 临时文件清理：已删 tmp_task6_anchors.py / tmp_task6_radiation.py
  - 🔴 产物跟踪：**全部正式产物 `??` 未跟踪**（spec 目录、后端 28 files、迁移 2 files、MCP server、前端 6 files、测试 35 files、Playwright 4 files、mutation runner）→ 需 git add + commit + CI 通过后方可标 `[x]`
  - 🔴 clean checkout CI：未跟踪 → 无法在 clean checkout 验证 → 阻塞
  - 结论：逻辑层面全绿，阻塞项仅 = git 入库 + CI
  - 从 clean checkout 运行目标 backend pytest、frontend vitest、typecheck/lint、mutation `--check-anchors`、Playwright 与 CI jobs
  - 对 requirements/design/tasks 运行 diagnostics，要求零错误；扫描 Requirement AC 是否均被 task 引用、Property 编号/Validates 是否有效、Task graph 是否含同波强依赖
  - 核对实施时最新 migration 号、幂等性和重启应用结果；不得沿用 spec 中旧号猜测
  - 逐个检查正式产物是否 tracked；spec 目录当前若仍为 `??` SHALL 视为未完成
  - 删除本 spec 自己产生的 `tmp_*` / `_wip_*`，不删除其他并发会话文件
  - 记录剩余容量边界、DSH allowlist、告警阈值、运行时实证与明确未验证项；任务标记不得假绿
  - **Validates: Requirements 14.5, 14.8**
  - **Properties: 40**

---

## Notes

1. `DshPanel.vue` 只是布局 adapter；核心组件固定命名为 `PlatformAiChatPanel.vue`，避免 Windows 大小写路径冲突。
2. `D:\DeepHorness` 为 vendor 只读；不修改上游源码，不再把 DSH Web UI 当成平台面板依赖。
3. 本 spec 不预占迁移 V 号；Task 3/22 开始时各自通过 migration status 获取当时最新值并协调为同一或连续迁移。
4. Phase A、B、C 的阶段守卫是后续阶段的真实前置条件；阻塞原因必须写入本文件对应 task，不得把未执行标成完成。
5. 地址 embedding、DSH SDK/Cordis 或运行时安全条件不满足时，相关任务保持阻塞并给出证据；不使用“功能隐藏了所以算完成”的口径。
6. 生产目标是 6000 用户，不等于允许 6000 个 Agent 子进程。容量由 active/queue/backpressure 配置与实测决定，超限必须可见。
7. 最终只保留一个消息模型、一个 SSE transport、一个核心聊天组件和一个服务端事件 schema；迁移完成即删除死代码。
