# 外部 LLM 提供商运行时闭环 — Requirements

## 背景
平台默认调用本地 vLLM，但事务所还需要以 API Key 调用外部 OpenAI-compatible 服务。现有初版只增加字段和下拉枚举，未让 active model 真正进入全部调用链，且存在明文密钥、越权配置和 SSRF/凭据外送风险。

## Requirement 1：单一配置权威源
1. `ai_model_config` MUST 是运行时模型配置的持久权威源。
2. 每个 `model_type` MUST 最多一个未删除的 active model。
3. `.env` MUST 只在该类型没有 active row 时作为 bootstrap fallback。
4. 进程重启、热重载及多 worker MUST 从同一数据库 active row 得到相同配置，不得依赖某 worker 的模块全局变量。

## Requirement 2：凭证安全
1. per-model API Key MUST 以 Fernet 密文落库，数据库、API 响应和日志均不得出现明文。
2. 加密 MUST 复用 `EncryptionService(settings.ENCRYPTION_KEY)`；未配置密钥时，保存外部 Key MUST fail-closed。
3. API 响应 MUST 只返回 `has_api_key` 与更新时间，不得返回掩码 Key 到可回写字段。
4. 更新时：省略或空白 `api_key` MUST 保留旧值；非空 MUST 替换；`clear_api_key=true` MUST 显式清除；替换与清除互斥。

## Requirement 3：出站端点安全
1. 保存及每次出站前 MUST 校验 endpoint：仅 http/https、无 userinfo/query/fragment、无非法端口。
2. DeepSeek/通义千问/智谱/Azure MUST 限定官方 host；custom/OpenAI-compatible 的私网端点 MUST 在服务端 allowlist 中。
3. DNS 解析到 link-local、metadata、多播、未指定或未经放行的私网/环回地址 MUST 拒绝。
4. HTTP 客户端 MUST 禁止自动重定向并保持 `trust_env=False`。

## Requirement 4：提供商支持矩阵
1. MUST 支持本地 vLLM、OpenAI-compatible、DeepSeek、通义千问、智谱、custom OpenAI-compatible。
2. Ollama MUST 通过其 `/v1` OpenAI-compatible 接口接入，不再维护第二套 chat 协议。
3. Azure OpenAI MUST 仅支持 `/openai/v1` 端点并使用 `api-key` header；旧 deployment + `api-version` 形态不在本轮范围。
4. 只有本地 Qwen/vLLM MAY 收到 `chat_template_kwargs`；外部服务不得收到该专有字段。

## Requirement 5：真实调用链统一
1. `AIService` 的 validate/chat/stream/embedding/health MUST 使用同一 runtime resolver 和 transport。
2. `llm_client.chat_completion` 及 AI Chat NativeEngine MUST 在每次 run 解析 active row，不得使用启动时缓存的 URL/Key/model。
3. 显式 `model` 参数 MAY 覆盖模型名，但不得绕过 active row 的 endpoint/凭证策略。
4. Embedding MUST 使用 active embedding row；无 active row 时回落 `LLM_EMBEDDING_BASE_URL`。

## Requirement 6：管理 API 与权限
1. 模型 list/create/update/delete/test/activate/health/seed MUST 仅 admin 可用。
2. Create/Update DTO MUST 不暴露 `is_active`；只有 activate 流程可改变 active 状态。
3. activate MUST 先验证连接，再以原子事务切换 active row。
4. test MUST 使用与生产调用完全相同的 resolver/transport，稳定返回中文错误码，不回显上游响应或密钥。

## Requirement 7：前端管理闭环
1. AI 模型配置页面 MUST 动态加载 provider 元数据，不硬编码枚举。
2. 页面 MUST 支持 Key 配置状态、留空保留、显式清除、连接测试和激活。
3. 页面及路由 MUST 仅 admin 可见/可访问；后端权限仍是最终边界。
4. 所有用户可见文本 MUST 为中文，错误提示不得泄漏凭证或内部响应体。

## Requirement 8：迁移、兼容与可观测性
1. V192/R192 MUST 配对、幂等，并与 PG 16 `ai_provider_enum` 现状兼容。
2. 密文字段 MUST 使用 `TEXT`；旧明文列不得创建。
3. 健康接口 MUST 返回 active provider/model/endpoint（不含 Key）及 chat/embedding 独立状态。
4. 文档 MUST 准确描述支持矩阵、ENCRYPTION_KEY、allowlist、切换语义和已知限制。

## 验收标准
- 真实端点级鉴权测试证明未登录 401、非 admin 403、admin 可操作。
- 写入已知 Key 后，直接 SQL 不包含明文；替换/保留/清除三态闭合。
- active row 经 `AIService`、`llm_client`、NativeEngine 三路发出的 endpoint/header/model 逐值一致。
- 本地兼容 mock 服务完成新增→测试→激活→真实 chat；前端 Playwright 完成相同管理流程。

## Requirement 9：企业 OpenAI-compatible 运行参数
1. 模型配置 MUST 支持 `context_window=262144` 和可选 `reasoning_effort=low|medium|high`。
2. 外部模型 MUST 将 `reasoning_effort` 作为 OpenAI-compatible 顶层字段发送；未配置时不得发送。
3. 企业自定义 HTTPS 端点和非标准 TLS 端口 MUST 可表达，同时仍执行 DNS/IP 出站策略。
4. 模型上下文容量 MUST 与平台 `AI_CHAT_MAX_CONTEXT_TOKENS` 输入预算分开表达，不能混为同一限制。

## Requirement 10：远程 PaddleX OCR 双能力
1. OCR 配置 MUST 显式区分 `ocr` 与 `layout_parsing` capability，两者 MAY 同时 active。
2. 远程协议 MUST 支持 PaddleX Basic Serving JSON：Base64 `file`、`fileType`、`POST /ocr|/layout-parsing`、`errorCode/result` 响应。
3. 认证 MUST 支持 none/bearer/X-API-Key/api-key/custom-header 白名单模式，Key 继续使用同一密文服务。
4. OCR 测试连接 MUST 发送内置合成图片，不得发送项目或客户文件。
5. 正常附件 OCR MUST 消费 active `ocr` 配置；显式版面解析 MUST 消费 active `layout_parsing` 配置。
6. 远程失败 MUST 进入 failed/unavailable，不得吞异常后以空文本标 completed。

## Requirement 11：致同企业内建预设
1. 平台 MUST 幂等预置 `qwen3.8`、`paddleocrv6`、`paddleocrvl-1.6` 三条 inactive 配置，且 MUST 不包含 API Key。
2. 预设参数 MUST 锁定，用户只能录入、替换或清除 Key；预设记录不得删除。
3. 三个预设的两个精确 endpoint MUST 作为内建可信地址支持 VPN/TUN 198.18/15 映射，不得扩大到同域其他端口/路径。
4. R194 MUST 不删除已经录入 Key 或已激活的预设模型。
5. UI MUST 标识“企业预设”，未配 Key 时提供“录入 Key”入口并锁定其他输入。
