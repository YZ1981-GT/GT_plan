# 设计文档：vLLM / httpx 链路 3 bug 修复

## 概述

3 个精确定位的 bug，修复方案明确，无架构变更。纯代码修正 + 测试验证，约 1 天。

## Bug 1 修复：httpx 系统代理绕过

### 修改点（4 文件）

每处 `httpx.AsyncClient()` 或 `httpx.Client()` 创建时加 `mounts={}, trust_env=False`：

```python
# 修复前
client = httpx.AsyncClient(base_url=url, timeout=timeout)

# 修复后
client = httpx.AsyncClient(base_url=url, timeout=timeout, mounts={}, trust_env=False)
```

**文件清单**：
1. `backend/app/services/llm_client.py` — `_sync_completion` / `_stream_completion` 中的 client
2. `backend/app/services/ai_service.py` — `_get_ollama_client` / `_get_llm_client` / `_get_chromadb_client`
3. `backend/app/services/availability_fallback_service.py` — `check_llm_available`
4. `backend/app/routers/system_settings.py` — `check_url`

### 触类旁通 grep

修复后 grep 全仓 `httpx.AsyncClient\(|httpx.Client\(` 确认无遗漏（排除测试文件中已有 `trust_env=False` 的）。

## Bug 2 修复：chat_template_kwargs 提升到顶层

### 修改点

`backend/app/services/llm_client.py` 的 payload 构建：

```python
# 修复前
payload = {
    "model": model,
    "messages": messages,
    "temperature": temperature,
    "max_tokens": max_tokens,
    "extra_body": {
        "chat_template_kwargs": {"enable_thinking": settings.LLM_ENABLE_THINKING}
    }
}

# 修复后
payload = {
    "model": model,
    "messages": messages,
    "temperature": temperature,
    "max_tokens": max_tokens,
    "chat_template_kwargs": {"enable_thinking": settings.LLM_ENABLE_THINKING},
}
```

## Bug 3 修复：finish_reason=length 处理

### 修改点

`backend/app/services/llm_client.py` 的 `_sync_completion` 返回值处理：

```python
# 修复前
content = choice.message.content
return content  # content=None 时直接返回 None

# 修复后
content = choice.message.content
if content is None and choice.finish_reason == "length":
    return "⚠️ 思考超出 token 限制，请简化提问或增大 max_tokens 设置。"
if content is None:
    return "⚠️ LLM 未返回有效内容，请重试。"
return content
```

**关键约束**：禁止 fallback 到 `choice.message.reasoning`（中间思考过程，非最终答案）。

## 正确性属性

**Property 1: 代理绕过**
对任意 httpx client 创建调用，`trust_env` 参数 SHALL 为 False。

**Property 2: chat_template_kwargs 顶层**
对任意 LLM payload，`chat_template_kwargs` SHALL 为顶层 key（非嵌套在 extra_body 内）。

**Property 3: 无 None 返回**
对任意 LLM 响应，`_sync_completion` 返回值 SHALL 为非 None 字符串。

## 测试策略

- Bug 1：mock httpx.AsyncClient 构造函数，断言 `trust_env=False, mounts={}` 被传入
- Bug 2：mock httpx.post，捕获 payload，断言 `chat_template_kwargs` 在顶层
- Bug 3：构造 `finish_reason=length` + `content=None` 的 mock 响应，断言返回中文提示字符串（非 None）；构造正常响应断言返回 content 原值
- 集成验证：启动 vLLM 后调 `/ai/suggest` 端点，断言返回非 stub 内容（需 vLLM 服务可用）
