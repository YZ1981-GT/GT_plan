# 需求：DSH 子进程与知识库扫描件 OCR 接入本机优先路由

承接 `llm-ocr-local-first-routing`（commit `eba3332a2`）：平台对话 / 向量 / OCR 已统一为「本机优先，本机不可用时用已配置的服务器模型」。该 spec 明确把两处留在范围外，本 spec 收口：

- DSH 多步 Agent 子进程（`dsh_engine.py`）仍按写死的 `localhost:8100` 生成配置。
- 知识库扫描件 OCR 仍在上传请求内直接调 MinerU（仅 PDF、默认关闭），不走统一 OCR 路由。

调研中确认 DSH 集成从未对真实 vendor 运行时跑通过（协议、provider 名、配置键名都不对，见 design §1）。「接入路由」必须先让它能跑，所以本 spec 一并修协议与进程管理。

## 术语

- 路由 / 候选：`llm_runtime.resolve_route` 产出的有序候选（本机在前），`llm_route` 的冷却记录。
- vendor：DSH 仓库（`DSH_VENDOR_ROOT`）。运行时载体 = vendor 构建产出的 node 闭包 `python/sdk-runtime/src/deepseek_harness_runtime/runtime/node/`。
- 受信端点：环回 / 内网 IP 字面量，或平台受信端点清单（`ai_model_presets.BUILTIN_TRUSTED_ENDPOINTS` + `LLM_ENDPOINT_ALLOWLIST`，native 引擎同一份）。

## Requirement 1：DSH 按平台对话路由选模型

1.1 每次 DSH run 在启动子进程前，按平台对话路由顺序探测候选，取第一个可用的；本 run 全程只用这一个候选，执行中途不切换（一次 Agent 推理不混用两个模型）。

1.2 探测结果与平台共用同一份冷却记录与探测缓存。没有可用候选时，run 以 `engine_unavailable` 结束，日志列出每个候选的原因（含因冷却跳过的）。

1.3 写给 vendor 的模型服务配置使用 vendor 真实键名：`baseURL`、`apiKeyEnv`、`models[].id`、`thinking`、`reasoningEffort`；`initialize` 用 vendor 唯一注册的 provider 路由名 `deepseek-official` 和所选候选的模型名。

1.4 DSH 子进程环境不继承父进程：只注入本 run 的转发令牌（平台私有变量名，按 design ADR-DKR-001 经平台环回转发，上游 Key 不进子进程），不注入 `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL`；`DSH_HOME` 指向本 run 的会话目录，不读写用户目录下的 `.dsh`。（初稿写「Key 经私有变量名注入」，采纳环回转发后改为只给令牌。）

1.5 运行中模型调用失败（`turn/end` 为 error）时，该候选记入冷却，run 以 `engine_unavailable` 结束，不在本 run 内换候选重跑。

1.6 run 的 usage 与终态事件记录实际服务的模型名与部署位置（本机 / 服务器）。

1.7 Key 不进日志、不进写盘的配置文件、不进任何事件 payload。

1.8 转发令牌与 MCP scoped token 的签名密钥派生自平台密钥（`JWT_SECRET_KEY`，各加域分离前缀），不得落回源码常量；平台密钥缺失时拒绝签发，run 以 typed error 结束（`engine_unavailable`；未知角色 fail-closed 为 `access_denied`），不拉起子进程、不留会话目录。（实施中发现，见 design §1.3 D11 / D12。）

## Requirement 2：DSH 端点策略（修订 dsh-agent-panel-integration Req 12.1~12.3）

2.1 所选候选的端点必须是受信端点；否则 run 以 `local_only_violation` 结束，不启动子进程。DeepSeek 官方 API 等公网端点仍被拒绝。

2.2 修订原因与范围：原 12.1 / 12.2 要求「仅内网或环回」，写于平台尚无服务器兜底之时。上一 spec 已让 native 引擎在本机不可用时用企业服务器 qwen3.8（事务所自建自管、已在受信清单内）；DSH 改为同一口径。依据：用户 2026-10-19 指令「dsh 子进程要接入」（本机优先，本机不可用时用服务器模型）。12.3「不发起公网请求」收窄为「不向受信端点以外发请求」。

2.3 `deepseek-official` 只是 vendor 适配器的路由名，不代表请求目的地；端点判定以写入配置的 `baseURL` 为准。

## Requirement 3：DSH 协议与进程对齐 vendor 真实实现

3.1 JSON-RPC 流程：`initialize` → `session/prompt`（`{sessionId, contentBlocks}`）→ 消费 `session.event` / `session.status` 通知，直到本 session 回到 idle → `shutdown`。

3.2 事件映射：`assistant/chunk` 的 text-delta → `delta`；`tool/call` → `tool_started`；`tool/result` → `tool_finished`；`turn/end` 的 completed / max-tokens → 完成；error / aborted → 失败；没有收到 chunk 时用 `assistant/message` 的定稿文本兜底。

3.3 audit-data MCP 由 DSH 的 mcp-client 按 Cordis 配置以 stdio 拉起，scoped token 只放进该服务的 env。平台不再单独拉起一个没人连接的 MCP 进程。

3.4 取消、超时或结束时：先发 `shutdown`，再终止 DSH 根进程及其全部后代（Windows 按进程树，POSIX 按进程组），最后删除会话目录。

3.5 运行时载体缺失时 run 以 `engine_unavailable` 结束，消息指明缺哪个文件、如何构建。

## Requirement 4：拆分超门禁文件

4.1 `dsh_engine.py`（1069 行）与 `dsh_discovery.py`（891 行）先按职责拆到 ≤800 行，拆分本身不改行为；既有测试的 patch 目标路径保持可解析。

## Requirement 5：知识库扫描件后台 OCR

5.1 上传时若正文为空且文件类型可 OCR（PDF / 图片），文档照常入库并标记「待识别」；上传请求内不做 OCR（不阻塞、不受 2 分钟上传超时影响）。

5.2 后台 worker 认领待识别文档（多进程不重复处理），经平台统一 OCR 路由识别，写回正文并刷新检索索引。

5.3 状态如实可见：待识别 / 识别中 / 已完成 / 未识别出文字 / 失败（带中文原因）。服务暂不可用时退避重试，超过次数上限才判失败；文件自身问题（过大、损坏、服务返回 4xx）直接失败，不重试。

5.4 单个文件的请求类失败不得让服务器 OCR 进入全局冷却（修 `unified_ocr_service`：只有服务不可用 / 配置类失败才冷却；读超时不冷却）。

5.5 进程重启或崩溃后，「识别中」且租约过期的文档会被重新认领；写回时校验租约，过期 worker 的结果不覆盖新结果。

5.6 文档列表接口返回 OCR 状态与原因；对该文档有管理权限的用户（与删除同一判定）可对失败 / 未识别出文字 / 存量扫描件发起「重新识别」；已有正文或正在识别的拒绝（409）。

5.7 前端：上传汇总与文档列表按状态提示，删除「扫描件需开启 OCR」旧文案；列表里有待识别 / 识别中的文档时自动刷新，完成后提示消失。

5.8 迁移 V198 / R198（`IF NOT EXISTS`），ORM 同步；不回填存量文档，存量扫描件按需「重新识别」。
