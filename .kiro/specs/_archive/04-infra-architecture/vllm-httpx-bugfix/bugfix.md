# Bugfix 需求文档：vLLM / httpx 链路 3 bug 修复

## 问题陈述

底稿模块 6+ 个 AI 对话框（存货跌价/所得税/减值/股份支付/薪酬/利息）+ TSJ 提示词驱动复核 + AI 辅助填写/分析性复核，全部因 LLM 链路 3 个 bug 而返回 stub 数据或报错。这 3 个 bug 是所有 AI 功能的共同前置阻塞——修复后一举解锁 TSJ 复核 + 6 个 stub 对话框两条线。

## Bug 条件分析

### Bug 1 — httpx 系统代理陷阱（Windows Clash 类代理导致 502）

**当前错误行为 C(X)**：Windows 上 Clash 类系统代理（127.0.0.1:7897）让 `httpx.AsyncClient()` 默认读取系统代理环境变量，把本应直连 localhost:8100（vLLM）的请求路由到代理，代理返回 502。

**触发条件**：Windows 环境 + 系统代理开启 + `httpx.AsyncClient()` 未显式禁用代理。

**期望正确行为**：所有 httpx client 创建时显式 `mounts={}, trust_env=False`，绕过系统代理直连 localhost。

**涉及文件**（4 处）：
- `backend/app/services/llm_client.py`（`_sync_completion` / `_stream_completion`）
- `backend/app/services/ai_service.py`（`_get_ollama_client` / `_get_llm_client` / `_get_chromadb_client`）
- `backend/app/services/availability_fallback_service.py`（`check_llm_available`）
- `backend/app/routers/system_settings.py`（`check_url`）

**修复成功标准**：
- WHEN 系统代理开启，THEN httpx 请求 localhost:8100 SHALL 直连成功（不经代理）
- WHEN grep `httpx.AsyncClient\(` 在上述 4 文件，THEN 每处 SHALL 含 `trust_env=False`

### Bug 2 — vLLM `chat_template_kwargs` 必须 payload 顶层

**当前错误行为**：`llm_client.py:107` 把 `chat_template_kwargs` 嵌套在 `extra_body` 内（`extra_body.chat_template_kwargs`），被 vLLM 静默忽略。`enable_thinking=False` 不生效，导致模型返回 thinking 内容（content=None + reasoning 有值）。

**触发条件**：任何 LLM 调用使用 `enable_thinking` 参数时。

**期望正确行为**：`chat_template_kwargs` 放在 payload 顶层（与 `messages`/`model`/`temperature` 同级），vLLM 正确读取。

**修复成功标准**：
- WHEN 调用 LLM 且 `settings.LLM_ENABLE_THINKING=False`，THEN vLLM 响应 SHALL 不含 reasoning 字段（content 非 None）
- WHEN 检查 `llm_client.py` payload 构建，THEN `chat_template_kwargs` SHALL 在顶层 dict 而非嵌套在 `extra_body` 内

### Bug 3 — LLM thinking content=None 未处理（finish_reason=length）

**当前错误行为**：当 vLLM 返回 `finish_reason=length`（token 超限）时，`content=None`（思考未完成），`_sync_completion` 直接返回 None 给调用方，调用方拿到 None 后行为不确定（有的静默失败，有的抛 AttributeError）。

**触发条件**：LLM 输入过长导致 token 超限 + `finish_reason=length`。

**期望正确行为**：`finish_reason=length` 且 `content=None` 时，返回友好提示"思考超 token 限制，请简化提问或增大 max_tokens"，**禁止**回退到 reasoning 字段（reasoning 是中间思考过程，非最终答案）。

**修复成功标准**：
- WHEN LLM 返回 `finish_reason=length` 且 `content=None`，THEN `_sync_completion` SHALL 返回包含中文提示的字符串（非 None）
- WHEN LLM 返回 `finish_reason=length`，THEN SHALL 不使用 `reasoning` 字段作为返回值

## Preservation 检查

- 修复后现有 pytest（含 test_ai_services / test_llm_client）0 回归
- 修复后 `WP_AI_SERVICE_ENABLED=True` 时 AI 端点（/ai/suggest / /ai/analytical-review / /ai/chat）能正常返回 LLM 响应（非 stub）
- 修复后 `WP_AI_SERVICE_ENABLED=False` 时仍返回 stub（门控不受影响）

## 范围边界

- 只修 LLM 链路的 3 个 bug，不改 AI 业务逻辑
- 不改 TSJ 提示词内容
- 不改前端 AI 对话框 UI
- 不做 LLM 性能优化 / prompt 工程
- 修复后 6 个 stub 对话框自动从 stub 切换到真实 LLM（由 `WP_AI_SERVICE_ENABLED` 门控，无需额外代码）
