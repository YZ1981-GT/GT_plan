# Design Document

## Overview

本设计将现有多套 AI 对话入口收敛为“一个受控 Chat Run 内核 + 多个宿主 adapter + 两种 engine”。设计不再假设现有 `doc_ai_chat` 链路已经具备正确授权与 Agent 运行语义，而是先修复资源绑定、会话状态、采纳门禁、浏览器敏感缓存和流协议，再扩展 mention/OCR/笔记/复核/地址索引，最后接入 DSH。

### 经代码核验后的基线

| 现有资产 | 复用方式 | 必须修复的事实 |
|---|---|---|
| `DshPanel.vue` / `ThreeColumnLayout.vue` | 保留布局、折叠、宽度和 badge 壳 | iframe、postMessage、窄屏和可访问性需替换 |
| `AIChatPanel.vue` / `DocAiChatPanel.vue` / `AiAssistantSidebar.vue` | 提取交互能力并迁移为 host adapter | 多套消息模型和渲染路径并存 |
| `useAiChat.ts` / `useDocAiChat.ts` / `utils/sse.ts` | 以 `utils/sse.ts` 为唯一 transport，迁移调用方 | `useDocAiChat` 按网络 chunk 拆行，会丢 SSE 事件 |
| `doc_ai_chat.py` | 重构为 run API 的路由入口 | 只有登录校验、ContextBuilder 异常 fail-open、POST 流不可恢复 |
| `doc_ai_context_builder.py` | 保留 token budget 与 citation 逻辑 | 资源查询未统一绑定项目/权限，note/report loader 错配 |
| `doc_chat_persistence.py` / `AIChatSession` / `AIChatMessage` | 复用会话与消息实体并补约束/字段 | locator 不含项目年度、无唯一约束、history 取最早 N 条 |
| `AIService` / vLLM | `NativeEngine` 复用 | 不新写模型 HTTP client |
| `KnowledgeIndexService` / `IndexSource` | 地址索引接入既有扩展点 | 不新建孤立向量库或独立 stale 体系 |
| `UnifiedOCRService` | 会话附件 OCR 复用 | 补文件安全、metadata、ownership 与清理状态 |
| `ReviewPromptService` | 复核模式后端调用 | 只返回结构化预览，正文不复制到前端 |
| `ExportMaskService` / 审计哈希链 | native 与 DSH 共用 | 显式补齐五角色映射和 tool/run 审计 |

### 关键设计原则

1. **授权先于读取**：任何资源 label、正文、索引片段和历史都在 `ResourceAccessResolver` 之后读取。
2. **服务端决定上下文**：客户端只提交稳定 ID；项目、年度、权限和权威消息由服务端解析。
3. **Run 是一等对象**：执行有 `run_id`、状态机、幂等、取消、重连、用量和唯一终态。
4. **事件是 typed contract**：engine 不返回裸字符串，统一产出 `ChatEvent`。
5. **前端只留一个内核**：不新增与 `AIChatPanel.vue` 大小写冲突的 `AiChatPanel.vue`，统一使用新名称 `PlatformAiChatPanel.vue`。
6. **DSH 不扩大权限**：Agent 自主决定“读什么”，但所有实际读取仍由平台 REST 权限门禁决定。
7. **全本地看 effective state**：以运行时实际模型路由、Cordis、工具目录、进程和网络为准，不以配置文本存在为准。
8. **失败可见且无成功尾声**：错误/取消后不再发 success `done`，不以空上下文、空 OCR 或 LLM 占位串伪装成功。

## Delivery Phases

```text
Phase A：安全与单一运行内核
  ResourceAccessResolver → HostContextResolver → Chat Run/state/SSE
  → session/message/run 持久化 → adopt fail-closed
  → PlatformAiChatPanel + sanitize + sensitive-cache cleanup

Phase B：上下文能力
  mention/context manifest → attachment/OCR → note capture
  → review mode → AddressCoordinateIndexSource

Phase C：DSH experimental engine
  MCP REST gates/scoped token → audit-data stdio server
  → custom Cordis smoke → DshEngine/backpressure
  → dual-user isolation/local-only/egress runtime acceptance
```

Phase C 依赖 A；Phase B 与 Phase C 不共享未授权旁路。DSH feature flag 只允许通过运行时验收的项目启用。

## Architecture

```text
┌──────────────────────────────────────────────────────────────────────┐
│ Host adapters                                                        │
│ DshPanel | Workpaper | Note | Report | Knowledge | New Window       │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ HostRef（稳定 ID，不含正文）
┌──────────────────────────────▼───────────────────────────────────────┐
│ PlatformAiChatPanel + usePlatformAiChat                              │
│ canonical message model + utils/sse.ts + AbortSignal + Last-Event-ID│
└──────────────┬───────────────────────────────────────────────────────┘
               │ POST /runs / GET /events / POST /cancel
┌──────────────▼───────────────────────────────────────────────────────┐
│ AI Chat API                                                          │
│ ResourceAccessResolver → HostContextResolver → ChatRunService        │
│                         ↓                                            │
│                   AuthorizedHostContext                              │
│                         ↓                                            │
│ ContextBuilder / Mention / Attachment / Review / Masking             │
│                         ↓                                            │
│ ChatRunCoordinator → NativeEngine | DshEngine                        │
│                         ↓ ChatEvent                                   │
│ Redis bounded replay + DB run/message/tool summary + SSE registry    │
└──────────────────────────────────────────────────────────────────────┘

DSH path only:
ChatRunCoordinator
  → run-scoped security context
  → custom Cordis + JSON-RPC server
  → dsh MCP client
  → per-run audit-data MCP stdio process
  → scoped REST token
  → /api/ai-chat/mcp/*
  → ResourceAccessResolver
```

## Components and Interfaces

### 1. ResourceAccessResolver

新增公共 AI 授权适配层，建议路径：

```text
backend/app/services/ai_chat/
  access.py
  host_context.py
  contracts.py
```

核心接口：

```python
@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    principal_id: UUID
    project_id: UUID | None
    cycle_scope: frozenset[str]
    allowed_actions: frozenset[str]
    denial_code: str | None = None

class ResourceAccessResolver:
    async def authorize_host(self, user: User, host: HostRef) -> AccessDecision: ...
    async def authorize_resource(
        self,
        user: User,
        host: AuthorizedHostContext,
        resource_type: ResourceType,
        resource_id: str,
        action: str,
    ) -> AccessDecision: ...
```

实现只编排已有公开权限服务：项目成员关系、`gate_wp`/批量底稿可见性、知识库 access policy、角色分类与 `scope_cycles`。不得调用 `ContextBuilder._check_doc_access` 等私有辅助函数作为公共授权 API；知识库需提取公开 policy service，tree/list/read/create 共用。

授权调用顺序固定为：

```text
解析最小资源标识 → 授权决策 → 读取 label/正文/索引 → 脱敏 → 进入上下文
```

无权与不存在对外使用相同的非枚举响应；内部审计记录真实 denial code。

### 2. HostContextResolver

```python
class HostType(str, Enum):
    workpaper = "workpaper"
    note = "note"
    report = "report"
    knowledge_doc = "knowledge_doc"
    knowledge_folder = "knowledge_folder"
    global_knowledge = "global_knowledge"

@dataclass(frozen=True)
class HostRef:
    type: HostType
    id: str
    project_id_assertion: UUID | None = None
    year_assertion: int | None = None

@dataclass(frozen=True)
class AuthorizedHostContext:
    principal_id: UUID
    project_id: UUID | None
    year: int | None
    resource_type: HostType
    resource_id: str
    display_label: str
    permission_binding: str
    cycle_scope: frozenset[str]
    allowed_actions: frozenset[str]
```

每个宿主使用专属 resolver：

| 宿主 | 稳定输入 | 服务端权威来源 |
|---|---|---|
| workpaper | working paper instance ID | `WorkingPaper JOIN WpIndex`，同时绑定 project |
| note | note instance 或稳定 section key | disclosure note service + project/year |
| report | report instance/type | report service + project/year |
| knowledge_doc | document ID | knowledge public access policy |
| knowledge_folder | folder ID | folder policy + project scope |
| global_knowledge | 显式模式，无伪 project ID | 只允许公共/当前用户有权知识范围，禁用项目工具 |

客户端 assertion 与服务端结果不一致时返回 `host_context_mismatch`。ContextBuilder 改为只接受 `AuthorizedHostContext`，不再根据自由字符串把 note/report 回退到 WorkingPaper loader。

### 3. API Surface

新 run API：

```text
POST   /api/ai-chat/runs
GET    /api/ai-chat/runs/{run_id}/events
POST   /api/ai-chat/runs/{run_id}/cancel
GET    /api/ai-chat/sessions/{session_id}/messages
DELETE /api/ai-chat/sessions/{session_id}
GET    /api/ai-chat/capabilities
GET    /api/ai-chat/mentionable
POST   /api/ai-chat/attachments
DELETE /api/ai-chat/attachments/{attachment_id}
POST   /api/ai-chat/notes
POST   /api/ai-chat/adopt
GET    /api/ai-chat/review-prompt
```

`POST /runs` 只创建/返回幂等 run，不保持长连接：

```python
class ChatRunRequest(BaseModel):
    session_id: UUID | None
    host: HostRef
    query: constr(min_length=1, max_length=4000)
    mentions: list[MentionRef] = []
    attachment_ids: list[UUID] = []
    review_mode: bool = False
    sheet_name: str | None = None
    idempotency_key: UUID
```

响应：

```json
{
  "run_id": "...",
  "session_id": "...",
  "request_id": "...",
  "status": "queued",
  "events_url": "/api/ai-chat/runs/.../events"
}
```

`GET /events` 支持 `Last-Event-ID`；`POST /cancel` 幂等。迁移完成后删除旧 `POST /doc/{type}/{id}` 的内部调用方与旧双轨，不保留长期 compatibility fallback。

### 4. Typed Event Contract

```python
class ChatEventType(str, Enum):
    run_started = "run_started"
    context_ready = "context_ready"
    citation = "citation"
    delta = "delta"
    tool_started = "tool_started"
    tool_finished = "tool_finished"
    quota = "quota"
    error = "error"
    cancelled = "cancelled"
    done = "done"

class ChatEvent(BaseModel):
    event_id: str
    run_id: UUID
    session_id: UUID
    request_id: UUID
    type: ChatEventType
    timestamp: datetime
    message_id: UUID | None = None
    payload: dict[str, Any] = {}
```

状态机：

```text
queued → running → done
                 ↘ error
                 ↘ cancelled
queued ──────────↘ cancelled
running lease expired → interrupted → queued（仅尚未产生外部副作用且策略允许）
                                  ↘ error
```

一个 run 只有一个 terminal event。`ChatRunService.finish()` 使用数据库 compare-and-set 更新，终态后拒绝追加业务事件。error/cancelled 只允许追加审计清理事件，不允许 assistant success message。

稳定 error code 包括：

```text
access_denied
host_context_mismatch
context_build_failed
semantic_unavailable
ocr_unavailable
engine_unavailable
local_only_violation
rate_limited
tool_budget_exceeded
attachment_invalid
run_cancelled
run_interrupted
adopt_log_failed
```

用户看到中文消息；内部 exception 仅写受控日志。

### 5. Run Coordinator、SSE Replay 与取消

新增 `ChatRunCoordinator`：

1. `POST /runs` 在事务中解析 HostContext、upsert session、按 `(user_id, session_id, idempotency_key)` upsert run，并只保存一条 user message。
2. commit 后将 run 放入有界执行队列；executor 使用 Redis lease 或等价原子租约保证同一 run 只有一个执行者。
3. engine 事件写入有界 Redis Stream `ai-chat:run:{run_id}`，设置 TTL；`delta` 不逐 token 写数据库。
4. assistant partial text按节流窗口更新 message 草稿；terminal 时一次完成最终正文、usage、citations 和 hash。
5. SSE endpoint 从 Redis Stream 按 `Last-Event-ID` 回放并订阅新事件，接入 `sse_registry` drain。
6. cancel 设置持久化状态与 Redis cancel signal；NativeEngine 检查 AbortEvent，DshEngine 终止 root/children/MCP。
7. 启动恢复任务扫描 lease 过期的 running run：无外部副作用且未到 retry limit 时重排，否则标记 interrupted/error。

前端只通过增强后的 `utils/sse.ts` 消费 SSE。parser 保留跨 chunk buffer，兼容 CRLF/LF、event/id/data 多行、心跳和 AbortSignal。

### 6. Persistence Model

实施时先通过 migration status 获取下一个可用 V 号，不在 spec 预占 V147。迁移幂等并只增加必要字段/表。

#### 复用并扩展 `ai_chat_sessions`

新增或校正：

```text
session_key             服务端规范化 hash
host_type / host_id
project_id / audit_year
engine_preference       服务端记录，不由客户端覆盖
review_mode
last_message_at
```

唯一约束：`(user_id, session_key)`。`session_key` 输入至少包含 user/project/year/host type/host ID；全局知识模式使用显式 sentinel，不使用空字符串。

#### 复用并扩展 `ai_chat_messages`

复用已有 `referenced_sources`、model/token/latency 字段（存在即不重复新增），补齐缺失的：

```text
run_id
status: draft/completed/failed/cancelled
content_hash
citations/context_manifest
```

history 使用子查询倒序取最近 N 条，再在外层正序返回。

#### 新增 `ai_chat_runs`

```text
id, session_id, request_id, idempotency_key
actor_id, project_id, host_type, host_id
engine, status, capability_snapshot
queued_at, started_at, finished_at, cancel_requested_at
error_code, usage, latency_ms, retry_count, lease_owner, lease_expires_at
```

唯一约束：`(actor_id, session_id, idempotency_key)`；状态更新使用 compare-and-set。

#### 新增 `ai_chat_tool_calls`

```text
id, run_id, parent_call_id, tool_call_id, tool_name
arg_hash, result_bytes, status, error_code, started_at, finished_at
```

不保存 scoped token 或完整工具入参。

#### 新增 `ai_chat_attachments`

```text
id, owner_id, project_id, session_id, run_id
sha256, original_name, storage_name, mime_type, size_bytes
ocr_status, ocr_text_encrypted_or_protected, error_code
created_at, expires_at, legal_hold, deleted_at
```

业务证据附件表不受影响。OCR 文本的存储方式沿用平台敏感文本保护能力；若平台无字段级加密，至少限制 DB/文件权限并设置最短必要保留期。

#### 新增 `ai_chat_action_receipts`

为 note save/adopt 提供通用幂等收据：

```text
action_type, actor_id, session_id, idempotency_key
source_message_hash, result_resource_id, status, error_code
```

唯一约束：`(action_type, actor_id, session_id, idempotency_key)`。

### 7. ContextBuilder、Mention 与 Context Manifest

ContextBuilder 新入口：

```python
async def build(
    self,
    *,
    host: AuthorizedHostContext,
    query: str,
    mentions: Sequence[MentionRef],
    attachments: Sequence[AuthorizedAttachment],
    review: ReviewContext | None,
) -> ChatContext: ...
```

ContextBuilder 不再负责首次授权，只消费已授权对象；每个 mention/attachment 在 resolver 层再次校验与当前 host 的关系。

服务端 schema 单一真源：

```python
class MentionType(str, Enum):
    workpaper = "workpaper"
    note = "note"
    report = "report"
    knowledge_doc = "knowledge_doc"
    knowledge_folder = "knowledge_folder"
    address = "address"
    attachment = "attachment"
```

前端类型从 OpenAPI schema 生成；若当前生成链暂不可用，则运行时契约测试直接加载后端 schema 对账，不手写第二份常量。

上下文预算由单一 `ContextBudgetPolicy` 声明，例如：

```text
system/policy         固定保留
host excerpt          上限 30%
explicit mentions     上限 30%，用户显式优先
attachments/OCR       上限 15%
review prompt         上限 10%
automatic RAG         使用剩余预算，最先裁剪
```

具体比例可通过配置调整，但所有分支必须经过同一 policy。Context Manifest：

```python
@dataclass
class ContextManifestItem:
    source_type: str
    source_id: str
    label: str
    decision: Literal["included", "trimmed", "denied", "unavailable"]
    reason_code: str | None
    token_estimate: int
    version: str | None
    is_stale: bool
    jump_route: str | None
```

`context_ready` 消费该 manifest；模型消息构建消费真正 included excerpts，防止 additive dead code。

`extra_scopes` 在所有宿主迁移后删除。知识树 route 必须先把 current user/project scope 传入公开 policy service，不能只修 URL。

### 8. Address Coordinate Index

新增 `AddressCoordinateIndexSource`，注册到现有 `IndexSource` registry：

```python
class AddressCoordinateIndexSource(IndexSource):
    source_type = KnowledgeSourceType.address_coordinate

    async def enumerate(self, project_id: UUID, year: int): ...
    async def fingerprint(self, item) -> str: ...
    async def render_text(self, item) -> str: ...
```

文本只由 `AddressEntry.label`、ACNR `semantic_label`、domain、URI/formula reference 等已有字段组合。不得在模块中出现科目/章节/表名字面量副本。

失效监听 canonical ACNR events；legacy `address_registry.invalidate()` 只通过统一桥接发布 canonical event，不在各调用点散挂索引更新。搜索必须提供严格 `source_types={address_coordinate}`，embedding health gate 失败返回 `semantic_unavailable`，不走默认 BM25/ILIKE fallback 冒充语义结果。

迁移执行要求：

1. 实施时查询最新迁移号；
2. 使用数据库实际 enum 名 `knowledge_source_type_enum`；
3. `ADD VALUE IF NOT EXISTS`；
4. 新 enum DML 在后续独立事务/运行时执行；
5. 三向守卫校验源坐标、IndexSource 输出和运行时搜索结果。

### 9. Attachment and OCR Service

附件上传服务流程：

```text
stream upload
 → 数量/Content-Length 初筛
 → 随机临时名
 → SHA-256 + extension/MIME magic 双校验
 → 图片像素/PDF 页数/解压上限
 → malware scanner（平台存在则复用；不可用按部署策略 fail-closed）
 → 写 metadata(status=uploaded)
 → UnifiedOCRService
 → status=succeeded/empty/failed/cancelled
```

客户端获得 attachment ID 与状态，不获得服务器路径。下一轮 run 只提交 IDs；服务端按 owner/project/session/host 授权后读取 OCR 文本。相同 owner/session/hash 的重复上传可幂等复用。

清理器先锁 metadata、删除磁盘、确认结果，再标记 deleted；失败保留 metadata 和 error 供重试。clear session 触发异步清理，但 legal hold 跳过。所有 OCR 文本以不可信数据定界并进入 Context Manifest。

### 10. Note Capture and Adopt

#### 项目笔记

`POST /notes` 请求只包含 message IDs、用户确认名称和 idempotency key。服务端：

1. 重新授权 HostContext 与 `knowledge.create` action；
2. 查询 server-issued completed assistant messages；
3. 锁定/创建 `ai_chat_action_receipts`；
4. 通过数据库唯一定位或 upsert 获取当前项目/年度 notes folder；
5. 组装 Markdown：原问题、回复、citations、run/message IDs、content hash；
6. 调用既有 KnowledgeDocument service，带 `project_ids` 与 tags；
7. 触发既有索引；
8. 保存 receipt 和哈希链审计；
9. 返回授权后的 jump route。

失败不清空前端选择，receipt 可安全重试。

#### 采纳

`POST /adopt` 不再接受客户端正文作为权威值：

```python
class AdoptRequest(BaseModel):
    message_id: UUID
    host: HostRef
    target_cell: str | None
    target_field: str | None
    idempotency_key: UUID
```

服务端校验 message→run→session→actor→HostContext，读取数据库正文和 hash，再调用 `wrap_ai_output_with_log`。`ai_content_log_id` 为空、日志创建异常或 commit 失败均回滚 receipt 并返回 `adopt_log_failed`。只有有效 log ID 才返回“已进入确认流”。

### 11. Review Mode

复核预览 route 只返回：

```text
source_level / tips / checklist / risk_areas / version
```

Chat run 内部依据 AuthorizedHostContext 的 wp_code/sheet 调用 `ReviewPromptService.load_prompt()` 获取正文。`SystemMessageAssembler` 将平台政策、复核 prompt、数据定界说明合并为单个 system message。

非 workpaper host、无权 sheet、prompt 加载失败均拒绝 review run；不静默降级普通问答。review mode 保存在服务端 session。

### 12. Engine Contract

```python
@dataclass(frozen=True)
class EngineCapabilities:
    streaming: bool
    tools: bool
    subagents: bool
    max_context: int
    structured_output: bool
    local_only: bool
    review_mode: bool
    attachments: bool

class ChatEngine(Protocol):
    async def capabilities(self) -> EngineCapabilities: ...
    async def run(
        self,
        request: AuthorizedChatRunRequest,
        cancel: CancelSignal,
    ) -> AsyncIterator[ChatEvent]: ...
```

`resolve_engine()` 只读服务端配置和 feature flag。capability snapshot 写入 run，前端从 `/capabilities` 获取，不复制假设。

#### NativeEngine

复用 AIService、熔断器、并发限制、single-system merge 和本地 vLLM。把 chunk 转为 `delta`，收集 usage/model/latency，识别 fail-soft placeholder 并转 typed error；error 后不保存 completed assistant message。

#### DshEngine

只在 Phase C feature flag 与项目 allowlist 同时满足时可选。不可用时返回 `engine_unavailable`，绝不隐式调用 NativeEngine。

### 13. DSH Custom Cordis and MCP

实施前先完成 SDK discovery：验证实际安装 artifact、版本/commit/hash、Python import、配置 schema 和 JSON-RPC handshake，再将兼容版本精确 pin 到平台依赖；`0.0.0.dev0` 或 `latest` 不可作为生产 pin。

custom Cordis 的最小组成：

```yaml
services:
  - '@deepseek-ai/dsh-sdk-jsonrpc-server'   # SDK bridge，必需
  - agent-spine
  - local-vllm-provider
  - '@deepseek-ai/dsh-mcp-client'
  - internal-stdio-transport                # 运输服务，不暴露为 Agent 工具
```

禁止注册为 Agent 工具：filesystem write、bash、shell、任意 subprocess command、web fetch、外部搜索。启动自检读取**实际激活后的** model route 与 tool catalog：

```text
model endpoint ∈ loopback/internal allowlist
tool catalog == MCP_READONLY_TOOLS
no bundled default
no cloud provider
no shell/fs-write/web-fetch tool
JSON-RPC handshake success
MCP handshake success
```

#### audit-data MCP server

位置建议 `tools/audit-data-mcp/server.py`，stdio only、零 DB。工具清单由平台后端导出的 `MCP_READONLY_TOOLS` schema 生成/校验，避免 server 再抄一份：

```text
wp_list / wp_read / tb_query / addr_lookup
kb_search / note_read / review_prompt
```

每个工具只调用 `/api/ai-chat/mcp/*`，平台端重新执行 ResourceAccessResolver、masking、配额和审计。

#### 身份与进程隔离

Phase C 首个可交付实现采用 per-run MCP stdio process：token 只注入该 run 的 MCP process，DSH root 不持有长期登录 token。DSH worker 使用有界并发：

```text
AI_DSH_MAX_ACTIVE_RUNS
AI_DSH_QUEUE_LIMIT
AI_DSH_RUN_TIMEOUT_SECONDS
AI_DSH_PROCESS_TTL_SECONDS
```

若 DSH root 无法证明完整 reset，则 root 也不得跨 principal 复用；结束后销毁。未来若引入 token broker 或安全 warm pool，必须先有双用户污染测试，不在实现中自行放宽。

child Agent 继承相同 run security context；所有工具 call 的 platform endpoint 仍逐次验 token/project/run/scope/expiry。

### 14. Frontend Convergence

目标结构：

```text
components/ai/
  PlatformAiChatPanel.vue       唯一核心面板，名称避开 Windows 大小写冲突
  ChatMessageList.vue
  ChatComposer.vue
  ChatMentionPicker.vue
  ChatAttachmentPicker.vue
  ChatContextInspector.vue
  ChatReviewModeBar.vue
  DshPanel.vue                  布局 adapter

composables/
  usePlatformAiChat.ts          唯一 run/message state
  useAiMention.ts
  useAiNoteCapture.ts

utils/sse.ts                    唯一 SSE parser/transport
```

迁移策略：

1. 抽取 canonical TS contracts（优先 OpenAPI generated type）。
2. 增强 `utils/sse.ts`，先让现有入口使用同一 transport。
3. 建立 `PlatformAiChatPanel.vue`，从现有组件迁移附件、citation、确认卡等能力。
4. `DshPanel`、Workpaper、Report、Disclosure、Knowledge、独立窗口改为 HostRef adapter。
5. 浏览器验证 session/history/事件一致。
6. 删除无消费方的旧核心组件/composable/手写 parser；保留有独立宿主职责的 adapter。

消息正文不进入 localStorage。panel width 可保留；logout、user switch 和首次升级调用 legacy cache scrubber 清除 `doc_ai_chat_*`。review mode 与 history 由服务端 session 恢复。

渲染统一：

```text
Markdown/untrusted excerpt
 → marked.parse
 → useSanitize / DOMPurify
 → v-html
```

测试检查最终 DOM 中 script、iframe、事件属性、危险 URL 和注入 SVG 均不存在。

### 15. Responsive and Accessibility

- `>1400px`：独立列；`769–1400px`：fixed drawer；`≤768px`：全屏 + safe-area。
- 触发条和 icon action 使用 button 语义；resizer 支持鼠标、触摸和左右键微调。
- 打开时焦点进入标题/输入区，关闭时回原触发器；全屏使用 focus trap。
- `aria-live="polite"` 只播报节流后的文本或完成状态，避免逐 token 噪声。
- mention 列表使用 combobox/listbox 语义；错误、quota 和 engine capability 有文本，不只靠颜色。
- 尊重 `prefers-reduced-motion`。

### 16. Rate Limits, Backpressure and Quotas

新增独立服务端配置，但 route matcher 必须真实消费：

```text
AI_CHAT_RATE_LIMIT_PER_MINUTE
AI_CHAT_MAX_ACTIVE_RUNS_PER_USER
AI_CHAT_MAX_ATTACHMENTS_PER_RUN
AI_CHAT_MAX_CONTEXT_TOKENS
AI_MCP_MAX_CALLS_PER_RUN
AI_MCP_MAX_BYTES_PER_CALL
AI_DSH_MAX_ACTIVE_RUNS
AI_DSH_QUEUE_LIMIT
```

限流 response/event 包含 remaining/reset/retry_after。Redis 不可用时采用平台既有 fail policy，但不能无限放开 DSH/MCP；高风险 Agent 路径应 fail-closed 或进入有界本地降级队列并明确标识。

### 17. Audit and Observability

run 和 tool call 事件进入平台哈希链：

```text
AI_CHAT_RUN_STARTED
AI_CHAT_RUN_DONE / ERROR / CANCELLED
AI_CHAT_TOOL_STARTED
AI_CHAT_TOOL_FINISHED / FAILED
AI_CHAT_ACCESS_DENIED
AI_CHAT_NOTE_SAVED
AI_CHAT_ADOPT_REQUESTED
AI_CHAT_ATTACHMENT_DELETED / CLEANUP_FAILED
AI_CHAT_LOCAL_ONLY_VIOLATION
```

审计只存 ID、hash、计数、字节数、时长和 error code。结构化指标包括 active/queued runs、queue wait、latency、tokens、tool calls/run、cancel latency、MCP bytes、denials、pool occupancy、attachment bytes、cleanup failures、local-only violations。

## Data Models

持久化模型的完整字段、唯一约束与迁移策略见“Components and Interfaces → Persistence Model”。模型边界固定为：复用并扩展 `ai_chat_sessions` / `ai_chat_messages`，新增 `ai_chat_runs`、`ai_chat_tool_calls`、`ai_chat_attachments` 与 `ai_chat_action_receipts`；Redis 仅保存带 TTL 的短时事件回放，不作为会话、消息或审计的权威存储。

## Error Handling

| 场景 | terminal / HTTP 行为 | 禁止行为 |
|---|---|---|
| 授权失败 | 资源不可枚举响应 + access audit | 先读 label/正文再拒绝 |
| Host mismatch | `host_context_mismatch` | 猜测项目或回退 WorkingPaper |
| Context build 失败 | `error(context_build_failed)` | 空上下文继续模型 |
| LLM placeholder/熔断 | typed error，不保存 completed assistant | 当正常正文落库 |
| mention endpoint 失败 | 独立 error state | 显示“无结果” |
| embedding down | `semantic_unavailable` | BM25 冒充语义结果 |
| OCR down | `ocr_unavailable` | 200 + 空文本 |
| DSH/MCP down | `engine_unavailable` | 静默 NativeEngine fallback |
| cancel | `cancelled` 且停止 descendants | cancel 后继续 tool call |
| note/adopt 下游失败 | transaction rollback + receipt failed | success toast/清空选择 |
| terminal race | compare-and-set 只接受首个终态 | error 后追加 done |

## Security Considerations

1. 客户端输入、知识正文、OCR 和模型输出均不可信；展示 sanitize，模型输入做数据定界。
2. Agent 工具能力与数据权限双重收口：tool catalog 限制“能做什么”，REST gate 限制“能读什么”。
3. scoped token 不进入日志、DB、前端或共享 runtime；环境变量使用 allowlist 构造，不从父进程全量继承。
4. MCP stdio 进程不监听端口，不持有 DB/Redis 凭据；运行目录与临时文件按 run 隔离。
5. local-only 通过 effective model/tool/network runtime probe 验证。
6. 浏览器不持久化敏感对话；遗留 localStorage 主动清理。
7. 附件路径不可由用户控制，下载/预览同样执行 owner/HostContext 授权。

## Migration and Rollout

1. 实施时查询 migration status，分配下一个 V 号；不使用本设计中的固定编号。
2. 先增加新表/字段与 backfill session key，再加唯一约束；重复 session 合并规则在迁移脚本中显式记录。
3. Phase A 使用 native engine shadow/allowlist；所有宿主迁移后删除旧 POST stream 与 legacy cache。
4. Phase B 能力按 endpoint capability 开启，embedding down 时 address 明确 unavailable。
5. Phase C 只对测试项目 feature flag；通过双用户、取消、进程、端口、egress、clean checkout 后再扩大 allowlist。
6. 任一阶段回滚只关闭新入口/feature flag，不恢复不安全的 iframe、客户端正文采纳或跨用户 localStorage 缓存。

## Testing Strategy

- **后端契约/行为**：pytest，直接执行授权、HostContext、run state、幂等、取消、history、note/adopt、MCP gate。
- **并发测试**：两个标签页首轮会话、相同 idempotency key、terminal race、cancel/tool race、双用户 DSH/MCP。
- **协议属性测试**：随机 SSE 字节分片、事件顺序、Last-Event-ID replay、Context Manifest 数量与预算。
- **前端行为**：Vitest mount，验证 DOM、焦点、quota、错误态、capability gate、legacy cache scrubber。
- **浏览器**：Playwright 390/768/1400px、五角色、mention/OCR/note/review/cancel/reconnect/XSS。
- **运行时安全**：真实 SDK/Cordis handshake、实际 tool catalog、端口扫描、进程树、egress deny、effective local model route。
- **变异检验**：只认可预期守卫打红；区分 RED/GREEN/ANCHOR-MISS/WRONG-TEST。
- **清洁检出**：clean checkout 执行 CI，确认新增迁移、schema、guard、mutation script 均已跟踪。

## Correctness Properties

### Property 1: 授权拒绝前零读取

对任意无权用户与任意 HostRef，授权拒绝发生后，资源 loader、正文 SQL、索引搜索和 label serializer 的调用次数均为 0。

**Validates: Requirements 2.1, 2.5, 2.8**

### Property 2: HostContext 断言一致性

对任意伪造的 client project/year/doc assertion，只要与服务端反查结果不一致，请求即返回 `host_context_mismatch`，且不创建 session/run。

**Validates: Requirements 2.3, 3.3**

### Property 3: 五角色权限交集

五角色 × 跨项目 × `scope_cycles` × private/project_group 的生成矩阵，其实际允许集合恒等于已有权限服务决策的交集，AI 模块不产生额外允许项。

**Validates: Requirements 2.2, 2.6, 2.7**

### Property 4: 全端点授权一致性

mention、history、clear、adopt、attachment、note、review 和 MCP 对同一资源/动作返回一致授权结果；直接 ID 不得绕过搜索可见性。

**Validates: Requirements 2.4**

### Property 5: 宿主加载器唯一映射

每种 HostType 均调用唯一对应的业务 loader；note/report/knowledge_folder 输入不会调用 WorkingPaper loader，空 project ID 不会被构造成有效项目 HostContext。

**Validates: Requirements 3.1, 3.2, 3.4, 3.7**

### Property 6: 会话与 Run 并发幂等

100 个并发相同 session key 的首次请求最终只产生一个 session；100 个相同 idempotency key 请求只产生一个 run、一条 user message 和一次 engine invocation。

**Validates: Requirements 4.6, 4.11**

### Property 7: Run 唯一终态

任意 run 的事件序列满足状态机，terminal event 恰好一个；注入 engine error 或 cancel 后，序列中不存在后续 `done` 或 completed assistant message。

**Validates: Requirements 4.3, 4.5**

### Property 8: 取消传播到全部后代

对运行中 native/DSH/tool/child-agent 的任意取消时点，cancel 最终传播到全部 descendants，取消确认后工具调用计数不再增加。

**Validates: Requirements 4.7**

### Property 9: SSE 任意分片与续传等价

将同一 SSE 字节流按任意位置分片并混用 CRLF/LF，客户端解析事件序列与未分片基线完全一致；按 Last-Event-ID 重连不丢失也不重复业务事件。

**Validates: Requirements 4.1, 4.4, 4.8, 4.12**

### Property 10: 最近历史顺序与元数据完整

history 对超过 N 条消息的会话返回最近 N 条并按时间正序，且每条包含真实 ID、run status、engine、citations 与已有 usage metadata。

**Validates: Requirements 4.10**

### Property 11: Mention Schema 与候选授权一致

Mention type 的前端 runtime schema 与后端 OpenAPI schema 集合相等；候选均已授权且不存在 null instance ID。

**Validates: Requirements 5.2, 5.3**

### Property 12: 预算与 Context Manifest 一致

对任意 mention/attachment/RAG 数量，最终 token estimate 不超过 budget；Context Manifest 中 included/trimmed/denied/unavailable 与实际传入模型的片段一一对应。

**Validates: Requirements 5.5, 5.6, 5.7**

### Property 13: 搜索错误态与空态可区分

mention endpoint 的 HTTP/timeout/capability failure 渲染错误态，成功空数组渲染空态；两种 DOM 与可访问文案不同。

**Validates: Requirements 5.4**

### Property 14: extra_scopes 双轨彻底收敛

所有旧宿主迁移后，请求 payload、后端 schema 和源码调用图中均不存在 `extra_scopes` 消费路径，且 mention folder 行为仍通过集成测试。

**Validates: Requirements 5.8**

### Property 15: 地址索引真源与失效联动

AddressCoordinateIndexSource 的输出文本只由源 AddressEntry/ACNR 字段生成；源变更触发 canonical invalidation 后，索引 fingerprint 变化并更新或标 stale。

**Validates: Requirements 6.2, 6.3, 6.6**

### Property 16: 语义不可用不伪降级

embedding down 时 address semantic API 返回 `semantic_unavailable`，不会返回 BM25/ILIKE 候选；恢复后结果严格限定 `address_coordinate` source type。

**Validates: Requirements 6.5**

### Property 17: 地址权限与脱敏一致

未授权用户不能通过 address 搜索或直接 ID 获得 label/current value；授权结果中的当前值经过与 native chat 相同的角色脱敏。

**Validates: Requirements 6.1, 6.7**

### Property 18: 附件安全校验先于 OCR

扩展名伪装、MIME 不匹配、超页数/像素/大小、路径穿越和跨用户 attachment ID 均在 OCR/正文读取前被拒绝。

**Validates: Requirements 7.2, 7.4**

### Property 19: OCR 五态互斥且可见

OCR HTTP unavailable、in-process 全链失败、timeout、empty 与 success 五种状态各自产生唯一状态/error code；只有 success/empty 可进入已授权 Context Manifest。

**Validates: Requirements 7.5, 7.6, 7.7**

### Property 20: 附件清理幂等可重试

附件 cleanup 在删除失败后保留 metadata 并可重试；重复执行最终收敛到同一 deleted 状态，legal hold 附件不删除。

**Validates: Requirements 7.8, 7.9**

### Property 21: 项目笔记并发幂等

同一 note idempotency key 的并发请求只创建一个 folder/document/receipt；保存内容来自服务端 messages，并包含 run/message/citation/hash 溯源。

**Validates: Requirements 8.1, 8.2, 8.3, 8.4**

### Property 22: 采纳权威正文与失败回滚

篡改 message ID、project ID、HostRef 或客户端正文的 adopt 请求均被拒；模拟 `ai_content_log` 写入失败时 transaction 回滚且响应不含 success。

**Validates: Requirements 8.6, 8.7**

### Property 23: 复核模式宿主与单 System 约束

复核模式只在已授权 workpaper HostContext 可用；模型输入中 system message 恰好一条，prompt 加载失败不会产生普通问答回复。

**Validates: Requirements 9.1, 9.2, 9.3, 9.6**

### Property 24: 引擎能力与 UI 一致

请求体中任意 engine 字段都不影响服务端选择；capability snapshot 与实际 engine 行为一致，不支持入口在 DOM 中禁用并显示中文原因。

**Validates: Requirements 10.1, 10.3, 10.4**

### Property 25: DSH 失败不降级

DSH 启动/handshake/MCP/local-model 任一步失败时 terminal code 为 `engine_unavailable` 或 `local_only_violation`，NativeEngine invocation count 恒为 0。

**Validates: Requirements 10.5, 12.2**

### Property 26: Effective Cordis 与工具目录受控

加载 effective custom Cordis 后，JSON-RPC/MCP handshake 成功，实际 model route 位于 allowlist，实际 Agent tool catalog 与 `MCP_READONLY_TOOLS` 完全相等且不含危险工具。

**Validates: Requirements 11.1, 11.2, 11.3, 12.1**

### Property 27: MCP 零数据库与零监听端口

MCP server 运行期间无监听 TCP 端口、无数据库连接/import/凭据；全部数据请求均命中 `AUDIT_API_BASE` 下受权 endpoint。

**Validates: Requirements 11.4**

### Property 28: DSH 跨用户隔离

两个用户并发执行 DSH run 时，交换 token/run/project 或复用前一 run 的 MCP process 均被拒；回收后扫描 root/session/JSONL/日志不含前一 principal 数据。

**Validates: Requirements 11.5, 11.6, 11.11**

### Property 29: 子 Agent 权限只收窄

子 Agent 的 effective project/cycle/scope/expiry 是父 run 的相等或更窄集合，永不扩大；MCP calls/bytes 超预算后明确失败且无后续工具调用。

**Validates: Requirements 11.7, 11.8**

### Property 30: 五角色脱敏一致

native 与 DSH 对五角色构造敏感文本返回相同脱敏结果；未知角色触发拒绝而非使用宽松默认映射。

**Validates: Requirements 11.9**

### Property 31: 提示注入不能扩大权限

含提示注入文本的数据始终被定界，服务器工具授权仍依据 run policy；deterministic fake agent 尝试越权工具/参数时 endpoint 拒绝，不以真实模型轨迹相同作为判据。

**Validates: Requirements 11.10**

### Property 32: 哈希链事件成对完整

每个 run 恰有 started 与一个 terminal 哈希链事件，每个 tool call 恰有 started 与 finished/failed；审计字段完整且不含 token、完整正文或附件内容。

**Validates: Requirements 12.6, 12.7**

### Property 33: 下游故障不产生假成功

ContextBuilder、LLM placeholder、tool、note/adopt 任一下游故障都只产生 typed error，不产生 success terminal、成功 toast 或 completed assistant message。

**Validates: Requirements 12.4, 12.5, 12.9**

### Property 34: 不可信 HTML 统一净化

AI、mention、OCR、citation 和 manifest 的恶意 HTML 经真实组件渲染后，DOM 不含 script/iframe/event attribute/dangerous URL/SVG payload，五种来源走同一 sanitizer。

**Validates: Requirements 13.1, 13.2**

### Property 35: 浏览器敏感缓存清理

logout、user switch 和首次升级会删除所有遗留 `doc_ai_chat_*` key；运行期间 localStorage 只允许面板尺寸等非敏感偏好，不含消息/OCR/mention/附件正文。

**Validates: Requirements 1.3, 13.3, 13.4**

### Property 36: AI Chat 真实限流接线

AI chat route 实际命中独立限流 matcher；触发后事件包含 remaining/reset/retry_after，前端保留草稿并显示中文倒计时。

**Validates: Requirements 13.5, 13.6, 13.7**

### Property 37: 三视口与可访问交互

在 390px、768px、1400px 视口下，面板分别满足全屏/浮层/独立列规则，关键操作可纯键盘完成，焦点打开关闭可逆且 live region 不逐 token 轰炸。

**Validates: Requirements 1.2, 1.6, 1.7, 14.6**

### Property 38: DSH Backpressure 有界

达到 DSH active/queue 上限时不会创建额外子进程，后续请求得到有界排队或明确 quota error；取消/超时后占用最终归零。

**Validates: Requirements 11.12, 12.8**

### Property 39: 前端只有一个聊天内核

完成迁移后，全仓只有一个核心聊天组件、一个 canonical message model 和一个 SSE transport；旧核心实现无引用且已删除，所有宿主行为使用同一 run/session。

**Validates: Requirements 1.8, 1.9**

### Property 40: Clean Checkout 收口完整

在 clean checkout 中三阶段守卫、变异脚本和 Playwright 均能运行，spec 正式产物不存在未跟踪依赖，requirements/design/tasks 机器诊断为零错误。

**Validates: Requirements 14.4, 14.5, 14.8**
