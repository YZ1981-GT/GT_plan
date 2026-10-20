# 设计：DSH 子进程与知识库扫描件 OCR 接入本机优先路由

## 1. 现状与根因（2026-10-20 实证）

### 1.1 DSH：集成从未对真实 vendor 跑通

| # | 现状 | 证据 |
|---|------|------|
| D1 | Cordis 模型服务写 `baseUrl`，vendor 读 `baseURL`（大写）；读不到时依次回落 `$DEEPSEEK_BASE_URL` → 公网 `api.deepseek.com` | vendor `packages/llm/llm-deepseek/src/index.ts` 的 Config；`docs/config-catalog.md` |
| D2 | `initialize` 发 `provider: "local-vllm"`；vendor 只注册 `deepseek-official`，其余名字抛 `no adapter registered for provider` ⇒ 每次握手必败 | `packages/sdk/server/src/server.ts::initialize` |
| D3 | 运行请求发 `method: "run"`；真实协议只有 `initialize` / `session/prompt` / `shutdown` 三个请求 + `session.event` / `session.status` / `subagent.*` 通知 | `packages/sdk/protocol/src/types.ts` |
| D4 | 事件映射按臆造的 `tool.call` / `text` 等方法名；真实事件在 `session.event.params.event.type`：`assistant/chunk`、`assistant/message`、`tool/call`、`tool/result`、`turn/end` | `packages/core/session/src/known-event-types.ts` |
| D5 | `mcp-client` 服务没有配置（vendor 要求 `transport/serverName/command/args/env/cwd/toolCallTimeoutMs/failOnStartupError`）；平台另起的 MCP 进程 stdio 握在 Python 手里，DSH 连不上它 | config-catalog `dsh-mcp-client` |
| D6 | MCP 进程 env 写 `MCP_SCOPED_TOKEN`，`tools/audit-data-mcp/server.py` 读 `MCP_TOKEN` ⇒ 工具调用全部无凭据 | server.py 第 47 行 |
| D7 | 模型默认 `maxTokens` 256000，本机 vLLM `max_model_len=32768` ⇒ 首个请求 400 | 2026-10-20 真实运行：`max_tokens=256000 cannot be greater than max_model_len` |
| D8 | 未设 `DSH_HOME`，Node 端 `os.homedir()` 仍落到用户目录的 `.dsh`（含 `.credentials.yaml` / `settings.yaml`） | vendor `credentials-local` / `agent-instructions` 读 `$DSH_HOME` > `~/.dsh` |
| D9 | `validate_model_route` 只认 IP 字面量，企业域名一律拒绝 | `dsh_discovery.MODEL_ROUTE_ALLOWLIST_PATTERNS` |
| D10 | vendor 开发检出 `D:\DeepHorness` 已领先 pin 7 个提交（`c58810f43f` vs `9a226f1077`），且 node 运行时闭包不存在 ⇒ discovery 不可用 | `git log`；`runtime/` 下只有 `cordis.yml` |

真实运行验证（pin 版本闭包 + 本机 vLLM）：`initialize` → `session/prompt` → `assistant/chunk`(text-delta) → `assistant/message` → `turn/end{completed}` → `session.status{idle}` → `shutdown`，4.8 秒完成一轮。

另两条直接影响「服务器兜底」能否成立：

- Node 直连企业网关失败：`fetch('https://ai.gt-china.com.cn:10010/v1/models')` → `ECONNRESET`（域名被本机代理解析为 fake-IP `198.18.0.224`）。平台 Python 侧靠 `llm_endpoint_policy.resolve_endpoint` 的 fake-IP 兼容改投真实地址，Node 侧没有这层。
- 企业网关只接受 `reasoning_effort ∈ {low, medium, xhigh}`（传 `high` 返回 400，见 `ai_model_presets.GT_QWEN38`）；vendor 适配器只会发 `low/high/max`。

### 1.2 知识库扫描件

- `knowledge_upload_service.extract_text_with_ocr` 在上传请求内直接调 `MinerUService`（仅 PDF，`MINERU_ENABLED=False` 时跳过），不走统一 OCR 路由；扫描件入库后 `content_text` 为空，AI 检索不到。
- 没有 OCR 状态，界面固定提示「扫描件需开启 OCR」，用户无处可开。
- `unified_ocr_service.recognize` 对远程候选的任何失败都 `mark_unavailable`（含文件过大、4xx、读超时）⇒ 后台批量识别时一份坏 PDF 会让服务器 OCR 对所有人冷却 30 秒。

### 1.3 实施中发现（2026-10-20，变异测试阶段）

| # | 现状 | 处置 |
|---|------|------|
| D11 | 转发令牌（本 spec 初版）与既有 MCP scoped token（`mcp_token._signing_key`）的签名密钥读 `settings.SECRET_KEY`；Settings 没有这个字段 ⇒ 恒落回源码常量 ⇒ 读过源码的人可签出任意 user / project 的 MCP token 调 `/api/ai-chat/mcp/*`（该路由只认 `X-MCP-Token`） | 两处都改为派生自 `JWT_SECRET_KEY`（域分离前缀不同），缺失即拒签；先例 `note_text_batch_flow._signing_key` |
| D12 | `_create_run_context` 先建临时会话目录再签 scoped token；签发失败（未知角色 / 密钥缺失）抛非 typed 异常、目录泄漏（本机 `%TEMP%` 实测 10 个空 `dsh_run_*`） | 先校验并签发、最后建目录；失败映射为 typed error（未知角色 `access_denied`，其余 `engine_unavailable`） |

附注（不改代码）：模型里约 100 处 `sa.Enum(..., create_type=False)` 的 `create_type` 被通用 `sa.Enum` 静默丢弃（只对 `postgresql.ENUM` 生效），`table.create()` 仍会发 `CREATE TYPE`。生产 DDL 走迁移、`create_all` 默认 `checkfirst=True`，不受影响；真库测试逐表建表须 `checkfirst=True`。

## 2. 架构决策

### ADR-DKR-001 DSH 的模型请求经平台环回转发

DSH 子进程的 `baseURL` 指向平台自身 `http://127.0.0.1:{PORT}/api/ai-chat/dsh-llm/v1`，Key 位置放每个 run 的签名令牌；平台按令牌绑定的候选把请求转发给上游。

- 复用平台出站的全部保护：端点策略、DNS 复核、fake-IP 兼容（`build_runtime_client`）。
- 平台按候选重写思考参数（`reasoning_effort` / `chat_template_kwargs`，与 `build_chat_payload` 同一份规则），解决适配器与网关参数不兼容。
- 上游 Key 不进子进程环境、不写盘。
- 子进程本身只连环回，原 Req 12.1 的「DSH effective endpoint 为环回」在字面上仍成立。

令牌 = HMAC 签名的 JSON：`run_id`、候选 `identity`、`exp`；密钥派生自 `JWT_SECRET_KEY`（前缀 `dsh-llm-forward:`，与 MCP scoped token 的 `mcp-scoped:` 分离，见 D11）。无状态，多 worker 下任一进程都能校验。转发端每次重新解析路由并按 `identity` 找候选，找不到（运行中配置被改）即 409。

否决：

- 直连上游：上面两条实测失败。
- 转发端做逐请求故障转移：一次多步推理会混用两个模型，与 ADR-DKR-002 冲突。

### ADR-DKR-002 run 级选候选：预检探测、全程固定

启动子进程前按路由顺序探测（共用 `model_route_status` 的探测缓存与 `llm_route` 冷却记录），取第一个可用候选，写进令牌。运行中失败只记冷却并结束本 run，下一个 run 自然选到下一个候选。

### ADR-DKR-003 端点策略修订（dsh-agent-panel-integration Req 12.1~12.3）

判定对象从「DSH 配置里的 URL」改为「转发端实际出站的上游端点」：`validate_dsh_upstream` 只放行平台受信清单（企业预设 + `LLM_ENDPOINT_ALLOWLIST`）或环回 / 内网 IP 字面量，否则该候选不给 DSH 用；路由里一个可用端点都没有 ⇒ `local_only_violation`。比 native 更严：官方公网 API 即使配置为服务器候选也不给 DSH。

DSH 子进程侧由 Cordis 校验器把关：模型服务 `baseURL` 必须是环回转发地址、`apiKeyEnv` 不得是 `DEEPSEEK_API_KEY`。`validate_model_route` 不改（仍服务 `.env` 健康检查）。

### ADR-DKR-004 vendor 根目录：独立 pin 检出

`DSH_VENDOR_ROOT` 改由 `settings` 读取（`.env` 可配，默认值不变）。本机配置为 `D:\dsh_vendor_pinned`：从 `D:\DeepHorness` 本地克隆、检出 pin 提交、构建 node 闭包。

- pin 常量不改：平台只跑验证过的 vendor 版本。
- 用户的 DSH 开发检出不动，继续开发不再打红平台门禁。
- 否决「改 pin 到开发分支 HEAD」：用户下一次提交又会漂移。

vendor 构建脚本在 Windows + Node 24 上 spawn `pnpm.cmd` 抛 `EINVAL`，node 闭包按其源码步骤复现（`pnpm deploy --legacy --prod` hoisted → 补回 legacy hoist → 实化软链），步骤写进 `docs/reference/llm-provider-configuration.md`。

### ADR-DKR-005 知识库 OCR：持久状态 + 后台 worker + 行认领

`knowledge_documents` 新增 `ocr_status`、`ocr_attempts`、`ocr_error`、`ocr_due_at`。

- 上传只标「待识别」。
- worker 用 `FOR UPDATE SKIP LOCKED` 认领（SQLite 用条件更新）。
- `ocr_due_at` 一列两用：待识别时是下次可尝试时间（退避），识别中时是租约到期时间。
- 写回带 `ocr_attempts` 围栏：只有持有当前租约的那一次能落库。

否决：

- 请求内 OCR：多页扫描件会超过 2 分钟上传超时。
- 放进 `run_indexing_pipeline`：私有文档在抽取前就被跳过。
- 复用 `index_status`：两种状态机会互相覆盖。

### ADR-DKR-006 OCR 冷却口径

远程候选只在 `kind ∈ {unavailable, config}` 时冷却。连接阶段超时仍归 unavailable；读超时（服务在、这份文件慢）改归 `timeout`，不冷却。

## 3. 组件

### 3.1 DSH 拆分（行为不变，Task 1）

| 新模块 | 自 | 内容 |
|--------|----|------|
| `dsh_cordis_policy.py` | discovery | 工具清单、禁用模式、`CordisServiceSpec`、`build_platform_cordis_config`、`validate_cordis_services` / `validate_tool_catalog` / `validate_model_route` |
| `dsh_smoke.py` | discovery | 三个 `smoke_*` |
| `dsh_process.py` | engine | `DshRunContext`、`DshProcessManager`、超时 / TTL 配置、env 与配置写盘 |
| `dsh_protocol.py` | engine | 握手、prompt、事件映射 |

`dsh_discovery` / `dsh_engine` 保留原名再导出，测试的 patch 字符串（`dsh_discovery.discover_dsh_sdk`、`dsh_engine._dsh_max_active`、`dsh_engine.DshEngine._create_run_context`、`dsh_engine.DshProcessManager.spawn_*`、`D.asyncio.create_subprocess_exec`）保持可解析。

### 3.2 DSH 接入（Task 2~5）

- `dsh_model_bridge.py`：`select_run_candidate()`（预检）、令牌签发 / 校验、`rewrite_request(body, config)`（强制 model、丢弃 `thinking` / `reasoning_effort` / `chat_template_kwargs` / `extra_body` 后按候选重写思考参数，其余字段原样）。
- `routers/dsh_model_forward.py`：`POST /api/ai-chat/dsh-llm/v1/chat/completions`（`router_registry/system.py` §130.2）。只接受环回来源且不带代理头（`X-Forwarded-For` / `X-Forwarded-Host` / `X-Real-IP` / `Forwarded`）；令牌错误 401；流式按解压后的字节回传上游 SSE。连接失败 502 并冷却；读超时 504 不冷却；上游 5xx / 401 / 403 / 404 原样回传并冷却；400 / 422 / 429 原样回传不冷却；成功转发清除该候选冷却。
- Cordis 配置：`llm-deepseek{baseURL, apiKeyEnv, thinking, models[{id, contextWindow, maxTokens}], retryPolicy{mode: normal, maxRetries: 1}}` + `mcp-client{stdio: sys.executable server.py, env{AUDIT_API_BASE, MCP_TOKEN, MCP_RUN_ID, PYTHONIOENCODING}, failOnStartupError: true}` + agent-spine（`dshHome` = 会话目录，`workspaceContext: false`，skills / bash / jobs 关闭）+ sdk-jsonrpc-server + sessions-jsonl。
- 子进程 env：`PATH`、`SYSTEMROOT`、`APPDATA`、`DSH_HOME`、`DSH_CORDIS_CONFIG`、`DSH_SESSION_ROOT`、`DSH_CWD`、`NODE_ENV`、令牌变量 `GT_DSH_LLM_TOKEN`。
- 进程树终止：Windows `taskkill /PID <pid> /T /F`，POSIX `start_new_session` + `killpg`。

### 3.3 知识库 OCR（Task 6~9）

- 迁移 V198 / R198：四列 + 部分索引 `(ocr_due_at) WHERE ocr_status IN ('pending','running')`。
- `knowledge_ocr_service.py`：`is_ocr_eligible`、`mark_pending`、`claim_next`、`process`、`request_retry`。
- `workers/knowledge_ocr_worker.py`：`run(stop_event)` + `wake()` + `drain()`；空闲轮询 30 秒，上传提交后 `wake()`；`KNOWLEDGE_OCR_WORKER_ENABLED=False` 不启动。注册在 `main._start_workers` 与 `startup_registry`（两处并存，见 Task 4 / Part C 对 `_start_workers` 的核查）。
- 上传：去掉请求内 MinerU；正文为空且可 OCR ⇒ `ocr_status='pending'`，回执带 `ocr_queued`。
- 路由：列表加 `ocr_status` / `ocr_error`；`POST /api/knowledge-library/documents/{id}/ocr-retry`（与删除同一管理权限判定，403 / 404 / 409）。
- 前端：`knowledgeUpload.ts` 文案与回执解析；`KnowledgeBase.vue` 状态标记、重新识别按钮、有待识别时 5 秒轮询。

## 4. 错误映射

| 情形 | DSH run 结果 | 冷却 |
|------|-------------|------|
| 无可用候选（全部探测失败） | `engine_unavailable`，日志逐个列原因 | 探测时已记 |
| 候选端点不受信 | `local_only_violation`，不启动子进程 | 否 |
| 运行时载体 / node / MCP 文件缺失 | `engine_unavailable` | 否 |
| 上游连接失败 | 转发返回 502 → `turn/end{error}` → `engine_unavailable` | 是（转发端记） |
| 上游 5xx / 401 / 403 / 404 | 原样回传 → `turn/end{error}` → `engine_unavailable` | 是（转发端记） |
| 上游读超时 | 转发返回 504 → `engine_unavailable` | 否 |
| 上游 400 / 422 / 429 | `turn/end{error}` → `engine_unavailable` | 否 |
| 转发令牌 / scoped token 签不出（平台密钥缺失；未知角色） | `engine_unavailable`（未知角色 `access_denied`），不启动子进程、不留会话目录 | 否 |
| 取消 / 超时 | `cancelled` / `engine_unavailable`，进程树终止 | 否 |

| 知识库 OCR 情形 | 状态 |
|----------------|------|
| 识别出文字 | `done`（正文写回、索引刷新） |
| 识别成功但无文字 | `empty` |
| 服务不可用 / 配置问题（unavailable、config：连不上、5xx、401 / 403 / 404）、读超时、未配置 OCR 模型 | 回 `pending`，退避 1 / 5 分钟，第 3 次仍失败 ⇒ `failed` |
| 所有候选都是请求类失败（文件过大、422 / 400 / 413 等 4xx）、文件不存在、没有存储文件 | `failed`，不重试 |
| 租约过期且次数用尽（进程反复中断） | `failed`（原 worker 迟到的结果按围栏丢弃） |

## 5. 测试与验收

- 单测：拆分前后同一组 DSH 测试全绿；协议模块对假运行时（按 vendor 协议回放的脚本进程）；令牌签名 / 过期 / 篡改；转发参数重写；OCR 状态机（SQLite）；冷却口径。
- 真实 PG：认领 `SKIP LOCKED` 两会话不重复、租约过期重认领、围栏拒绝过期写回。
- 真实运行：DSH 经 pin 闭包 → 转发 → 本机 vLLM；本机不可用 → 服务器 qwen3.8；Playwright 知识库上传扫描 PDF → 识别中 → 完成。
- 变异：每条新守卫磁盘注入后必须打红、逐字节恢复。

## 6. 不在范围

- DSH 默认仍关闭（`AI_DSH_ENABLED=False`）。
- 知识库上传入口仍不接受图片（后端可识别图片，前端 accept 不改）。
- 存量扫描件不批量回填。
