# 外部 LLM 提供商运行时闭环 — Design

## 1. 现状实证与问题分级
- live PG（2026-10-19）`ai_model_config` 无 Key 列，`ai_provider_enum` 仅 `ollama/openai_compatible/paddleocr`；临时 V192 尚未执行，可安全重写。
- P0：Key 明文落库；create/delete/seed 无鉴权，update/test 仅登录；任意 endpoint 可携旧 Key 出站形成 SSRF/凭据外送。
- P0：新增 provider 不进入 `_validate_model`；`build_client_for_model` 未被 chat/stream/embedding/health 消费。
- P1：`llm_client.reconfigure()` 仅当前 worker 生效；重启和其他 worker回落 `.env`。
- P1：前端仍只有 3 个旧 provider，无 Key/test/clear；新增测试只直调 helper，未证明端点/DB/调用链。

## 2. 架构裁决
### ADR-LLM-001 配置优先级
`active ai_model_config row > .env fallback`。不使用进程内 reconfigure 作为权威状态。每次 LLM run 查询一次 active row；LLM 并发本身有硬上限，相对一次模型推理，该查询成本可忽略，换取多 worker/重启强一致。

### ADR-LLM-002 凭证 envelope
数据库列 `api_key_ciphertext TEXT`、`api_key_updated_at TIMESTAMPTZ`。`AIModelSecretService` 产出 `v1:<fernet-token>`，仅 runtime resolver 解密。缺少 `ENCRYPTION_KEY` 时外部 Key 写入/读取均 fail-closed；`.env` Key 保持部署级 secret，不复制进 DB。

### ADR-LLM-003 单一 provider registry
`llm_provider_registry.py` 保存 provider 元数据：默认 endpoint、Key header、是否需要 Key、支持类型、endpoint host policy、是否允许 Qwen 专属参数。router 和前端都读取 `/providers`，不再各写一份表。

### ADR-LLM-004 单一 runtime/transport
`llm_runtime.py` 定义 `ResolvedLLMConfig`、active row resolver、endpoint policy、payload builder、sync/stream/embedding/test transport。`AIService` 和 `llm_client` 只委派，不再各建 httpx 协议实现。NativeEngine 不读取 `_BASE_URL/_API_KEY` 私有变量。

### ADR-LLM-005 endpoint policy
官方 provider 固定 host。`openai_compatible/custom` 允许公网 HTTPS；本地 vLLM/Ollama 允许 loopback；其他私网 origin 只有精确命中 `LLM_ENDPOINT_ALLOWLIST` 才允许。保存做结构/host 校验，出站前再做 DNS/IP 校验；`follow_redirects=False`、`trust_env=False`。

### ADR-LLM-006 支持边界
| Provider | 协议 | Key header | 本轮状态 |
|---|---|---|---|
| local vLLM | OpenAI `/v1` | 可无 | 支持 |
| OpenAI-compatible/custom | OpenAI `/v1` | Bearer | 支持 |
| DeepSeek | OpenAI `/v1` | Bearer | 支持 |
| 通义千问 | compatible-mode `/v1` | Bearer | 支持 |
| 智谱 | `/api/paas/v4` | Bearer | 支持 |
| Ollama | OpenAI `/v1` | 无 | 支持 |
| Azure OpenAI | `/openai/v1` | `api-key` | 支持；旧 api-version 形态不支持 |
| PaddleOCR | 本地 Python | 无 | 保持现状，不走 LLM runtime |

## 3. 数据模型与迁移
- V192：新增 5 个 provider enum；新增 `api_key_ciphertext TEXT`、`api_key_updated_at`；将 name/type 唯一索引改为仅未删除行；新增每类型仅一个 active row 的 partial unique index。
- R192：删除两列及新增 partial indexes；enum label 按 PG 限制诚实保留。
- 迁移前检查 live active 重复数；若存在，禁止静默挑一个。

## 4. API 契约
- `GET /api/ai-models/providers`：registry 投影。
- `POST /api/ai-models`：不含 `is_active`；Key 为 write-only。
- `PUT /api/ai-models/{id}`：Key 空白保留、`clear_api_key` 显式清除。
- `POST /{id}/test`：生产同路径测试，不改变 active。
- `POST /{id}/activate`：验证后在事务内切换；返回 provider/model。
- `GET /health`：不返回 Key/内部上游正文。
- 所有端点（含 list/providers/health）统一 admin，避免暴露内部架构。

## 5. 前端
- `aiModelApi.ts` 扩充类型及 providers/test 方法；遵守 `http` 返回完整响应、取 `.data`。
- `AIModelConfig.vue` 动态 provider、password 输入、Key 状态/清除开关、测试按钮、active 状态和健康状态。
- `ModelTable.vue` 增加“已配置密钥”和“测试连接”；路由加 admin permission。

## 6. 降级与错误
- active row 损坏/解密失败：fail-closed，返回 typed unavailable，不静默回落 `.env`（否则会把请求发送到错误提供商）。
- 仅“无 active row”允许 `.env` fallback。
- test/activate 对网络、401/403、404/模型不存在、timeout 映射稳定中文错误，不回显上游 body。

## 7. 验证
1. SQLite ORM + FastAPI 端点真实请求；逐权限角色验证。
2. 密文 SQL 直查、错 key fail-closed、四态更新契约。
3. endpoint policy 参数化覆盖 loopback/private/metadata/userinfo/redirect。
4. mock transport 逐值验证 AIService/llm_client/NativeEngine。
5. scratch/live PG 跑 V192 并核 `information_schema`/`pg_enum`/indexes。
6. 前端 Vitest + 单区域 tsc + Playwright 管理页；本地 mock OpenAI-compatible 服务验证真实 HTTP。

## 8. 2026-10-19 企业端点补充裁决
### ADR-LLM-007 reasoning effort
`ai_model_config.reasoning_effort` 保存 low/medium/high；runtime 只在非空时发送顶层 `reasoning_effort`。`context_window` 是模型元数据，平台输入预算仍由 `AI_CHAT_MAX_CONTEXT_TOKENS` 独立约束。

### ADR-LLM-008 PaddleX OCR adapter
V193 增加 `ocr_capability/ocr_protocol/api_path/auth_scheme/auth_header_name/request_timeout_seconds`。`ocr_protocol=local` 保持本机路径；`paddlex_json` 按官方 Basic Serving 发送 Base64 JSON并归一 `ocrResults/layoutParsingResults`。认证头是白名单枚举，避免猜内部网关协议。

### ADR-LLM-009 OCR active 维度
chat/embedding 仍按 model_type 单 active；OCR 改为按 capability 单 active，允许 `paddleocrv6:/ocr` 与 `paddleocrvl-1.6:/layout-parsing` 同时生效。UnifiedOCRService 默认使用 `ocr`，显式 `OCREngine.LAYOUT_PARSING` 使用版面解析；配置远程后失败不回退空文本。

### 外部资料实证
PaddleX 官方 API 证明 `/ocr` 与 `/layout-parsing` 均为 JSON POST、file 可传 Base64、响应为 `errorCode/result`；未发现目标内部网关认证 Header 证据，因此 UI 提供可选认证模式，真实上线前由服务方确认。

## 9. 2026-10-19 企业预设补充
### ADR-LLM-010 预置公开参数、用户只录 Key
V194 增加 `preset_key` 并插入三条固定 UUID 的 inactive 记录，所有公开参数预填，`api_key_ciphertext=NULL`。后端只允许 preset 更新 `api_key/clear_api_key`，禁止删除；前端显示“企业预设/录入 Key”并禁用其他字段。固定 base URL 进入代码内建精确可信集合，以兼容企业 VPN 的 198.18/15 fake-IP；metadata/link-local 仍无条件拒绝。回滚仅删除无 Key且 inactive 的原始预设，已使用记录先脱离 preset 标识再保留。
## 10. 2026-10-19 激活失败复盘补充
### 现场结论
真实 Key 录入后激活报「模型验证失败」。`/test` 实得 `provider_unreachable`；Python OpenSSL、curl Schannel、经代理端口三条路径均在 TLS 握手阶段被关。本机 Mesl（mihomo TUN + fake-IP + `dns-hijack any:53` + strict-route）日志为 `dial DIRECT ... ai.gt-china.com.cn:10010 error: dns resolve failed: couldn't find ip`；AliDNS/DNSPod/Cloudflare DoH 对该域名均 NXDOMAIN（SOA `dns1.cscdns.net`），只能由公司内网 DNS 解析。属本机网络环境问题，平台无法也不应绕过；内网 DNS 下的真实连通性在本机未能验证。
### ADR-LLM-011 连接测试按协议可用判定
`test_runtime_config` 改用 `_probe_chat_completion`：与生产同一 transport、鉴权与 payload（含 `reasoning_effort`），`max_tokens=16`，只要求 2xx + 合法 `choices`。推理模型小预算下返回 `content=null, finish_reason=length`（本机 vLLM Qwen3.5 实测 max_tokens=1/16 均如此），旧判据会使推理模型永远无法激活。生产 `chat_sync` 仍要求正文。
### ADR-LLM-012 失败原因必须可诊断
传输失败统一经 `describe_network_failure` 归类（证书 / TLS 握手中断 / 拒连 / 对端重置 / 对端提前关闭 / DNS / 超时），域名落在 198.18/15 时追加代理分流提示（证书错误除外）；400/422 且设置了思考强度时提示改「未指定」。`AIService.last_validation_error` 保留 code + 安全文案，`activate` 与激活中模型的 `PUT` 返回 400 `{error_code, message}`，OCR `/test` 返回真实 code。文案不含上游正文、请求头或 Key。
### ADR-LLM-013 思考强度由用户选择
V195 把 `gt_qwen38` 由 V194 播种的 `low` 置为 NULL（仅当仍为 `low`）；预设可编辑白名单 `PRESET_USER_EDITABLE_FIELDS = {api_key, clear_api_key, reasoning_effort}`，`reasoning_effort` 仅对 chat 预设放行，端点/模型名/供应商/上下文等目的地字段仍 422 且整单不落库。前端提供显式「未指定」选项（`empty-values` 使 `''` 可选），仅在思考强度变化时提交。R195 在仍为 NULL 时恢复 `low`。
### 现场补充实证（同日第二轮）
WSL 内直接查询公司 DNS（绕开 strict-route 的 DNS 拦截）得到 `ai.gt-china.com.cn` 的内网地址，位于 Mesl `route-exclude-address` 覆盖的私网段；进程内把域名钉到该地址后：证书为 DigiCert/GeoTrust 签发的 `*.gt-china.com.cn`、校验通过；`GET /v1/models` 用用户 Key 返回 200 且仅含 `qwen3.8`；连接测试与生产对话均成功。即 Key、模型名、端点均正确，唯一阻断是本机代理对该域名的 DNS 处理。本机系统 hosts 文件自 2026-06-28 起为 381 字节全 NUL（非本 spec 引入），未改动。
### ADR-LLM-014 思考强度取值按服务端实测登记
企业网关对 `high` 返回 400 `Unexpected reasoning effort high. Supported types are xhigh (default), medium, and low.`。V196 把 CHECK 约束扩为 low/medium/high/xhigh，`ReasoningEffort` 增加 `xhigh`；预设新增非 DB 元数据 `reasoning_effort_options=("low","medium","xhigh")` 与 `reasoning_effort_server_default="xhigh"`，API 行投影返回这两项，后端对预设拒绝集合外取值（422），前端只渲染集合内选项并把「未指定」标为服务端默认值。非预设模型不限制。R196 先把 xhigh 置 NULL 再恢复旧约束。
## 11. 2026-10-19 本机代理（fake-IP）兼容
### 实证
Mesl TUN 开启时：后端进程直连公司 DNS 被 strict-route 拦截（UDP 超时、TCP WinError 10013）；经本机代理混合端口 HTTP CONNECT 到公司 DNS:53 走 DNS-over-TCP 可得真实地址（私网段，Mesl 默认不接管该段路由）。`gt-china.com.cn` 公网 IP 不提供 10010/10080，企业 AI 不对公网开放，外网无 VPN 时不可能连通。
### ADR-LLM-015 fake-IP 兼容解析
- 触发条件：endpoint 命中 allowlist（内建企业端点或 `LLM_ENDPOINT_ALLOWLIST`），且系统解析结果**全部**落在 198.18/15 或解析失败；总开关 `LLM_FAKE_IP_COMPAT`（默认开）。其他情况走系统 DNS，行为不变。
- 地址来源：①`LLM_ENDPOINT_HOST_OVERRIDES`（`host=ip`，显式钉选）②上游 DNS 自动发现：服务器取 `LLM_UPSTREAM_DNS_SERVERS` 或本机网卡配置（Windows 注册表 Tcpip 接口 NameServer/DhcpNameServer，其他系统 `/etc/resolv.conf`），剔除 fake-IP/环回/链路本地；每台依次 TCP 直连 → 经本机 HTTP 代理 CONNECT 的 TCP → UDP（代理取 `LLM_UPSTREAM_DNS_PROXY` 或环境变量 / WinINet 设置，只认环回地址；strict-route 下 TCP 直连立即被拒、UDP 要等超时，故 UDP 放最后），单次 1.5s、总预算 6s。
- 校验：只取 A 记录；结果不得是 fake-IP，并按 allowlist 端点的既有策略复核（允许私网，拒绝环回、链路本地、多播、未指定）。
- 连接：`PinnedAddressTransport` 只把 TCP 连接改投到已校验地址，URL、Host、TLS SNI 与证书校验仍按原域名 —— 被投毒的地址拿不到该域名的有效证书。
- 缓存：按域名缓存，TTL 取记录 TTL 并夹在 30~300s；失败结果缓存 30s；最近一次结果供错误诊断（上游也 NXDOMAIN ⇒ 提示可能不在公司网络；上游 DNS 都连不上 ⇒ 提示改用显式钉选）。
### ADR-LLM-016 远程 OCR 连接测试图
内置 1x1 PNG 被 PaddleX 拒为 HTTP 422 `Invalid input file`。改为 240x64 黑白文字图（459 字节，内容 `GT OCR 2026`，以常量内嵌、不新增运行时依赖）；两条企业 OCR 均返回 200 且原样识别。HTTP 422 文案补充"文件格式或尺寸不被接受"。
