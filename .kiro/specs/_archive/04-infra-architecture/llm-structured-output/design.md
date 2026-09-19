# Design: 本地 LLM 结构化输出（Instructor + vLLM guided decoding）

## Overview

把"靠 prompt 让本地 Qwen3.5-27B 吐 JSON 然后 `json.loads`"这条不可靠链路，升级为**两层保障**：
1. **vLLM 端 guided decoding**（`guided_json` / `guided_grammar`，基于 xgrammar/outlines 后端）——在 GPU 解码时约束 token，**保证输出语法合法**（不会吐出半截 JSON / 多余 markdown 包裹）。
2. **客户端 Instructor + Pydantic**——把目标结构定义为 Pydantic 模型，自动做语义校验 + 失败重试 + 错误反馈纠错。

两层组合：vLLM 保证「语法对」，Instructor 保证「语义对」。目标把现有 OCR/证据/结构化复核场景的 JSON parse 失败率从实测 20-30% 降到 <2%。

**本地优先**：Instructor 是纯 Python 库（无外部服务）；guided decoding 是 vLLM 自带能力（已部署的 vLLM 8100 实例即支持，无需新实例）。

## 现状勘察

### 受影响的三个结构化输出场景

| 服务 | 现状取数方式 | 真实调用方（grep 实证）| 痛点 |
|------|------------|---------------------|------|
| `wp_document_recognizer.py` `_llm_recognize` | prompt → `chat_completion()` → `content[index("{"):rindex("}")+1]` + `json.loads`（最脆弱）| ✅ **活链路**：`routers/wp_document_recognize.py` 端点调 `recognize_batch` | markdown 包裹/截断/字段缺失致 parse 失败 |
| `wp_evidence_ocr_service.py` `_ocr_and_recognize` | **当前是 stub（TODO 待接入），根本没调 LLM** | ⚠️ **service 存在、grep 无 router 调用方**（半成品）| 尚未接 LLM，本场景是"首次接入"非"替换" |
| `tsj_structured_output_service.py` | 已有成熟 `parse_findings_json`（3 策略正则）+ `process_review_response` fallback | 🔴 **孤儿：`process_review_response`/`build_structured_prompt`/`write_findings_to_ai_content` 全仓零外部调用方** | 函数完备但无人调，改造无法验证"不回归"（无基线）|

> 🔴 **优先级裁定（勘察后）**：
> - **recognizer 是唯一有完整活链路的场景** → 本 spec 的核心交付，必做。
> - **evidence 有 service 无 router** → 可接入（从 stub 首次接 LLM），但端到端验证依赖未来 router 接线，标 `[ ]*`。
> - **tsj 是孤儿** → 改造一个零调用方的函数 = 无法验证、易伪绿。本 spec **不强行接入 tsj**；仅定义其 Pydantic 模型（`TsjReviewResult`，供 spec-5 DSPy 复用 + 未来接线用），实际接入降级为 `[ ]*` 或留待 tsj review 链路真正接线时一并做。

### 两套 LLM 客户端（design 必须兼容）

- **`llm_client.chat_completion(messages, model, temperature, max_tokens, stream, context_documents)`**：httpx 直调 vLLM `/chat/completions`，含熔断器。payload 已含 `chat_template_kwargs`，**可天然扩展 `extra_body`/顶层字段传 `guided_json`**。
- **`AIService(db).chat_completion(...)`**：需 DB 会话查 active model，OCR/knowledge/contract/wp_fill 用。

### vLLM guided decoding 接口（OpenAI 兼容扩展）

vLLM 在 OpenAI 兼容 `/chat/completions` 上支持 `extra_body`（或顶层）传：
- `guided_json`: JSON Schema（dict）——输出严格符合该 schema
- `guided_grammar`: GBNF 语法
- `guided_choice`: 枚举值列表
- `guided_regex`: 正则

> ⚠️ 现状勘察待实现期确认：当前部署的 vLLM 版本是否启用 guided decoding 后端（xgrammar 默认随 vLLM 0.6+ 内置）。design 提供**双路径**：vLLM 支持 → 走 guided_json；不支持 → 降级纯 Instructor retry（不阻断）。

## Architecture

### 分层

```
业务 service (wp_document_recognizer / wp_evidence_ocr / tsj_structured_output)
    │  传入 Pydantic response_model + messages
    ▼
structured_llm_service.py  （新建——统一结构化输出入口）
    │
    ├─ 模式 A：vLLM guided_json 可用
    │    └─ 把 PydanticModel.model_json_schema() 作为 guided_json 透传
    │       → vLLM 解码层保证语法合法
    │       → Instructor/Pydantic 再做语义校验（一次基本必过）
    │
    └─ 模式 B：guided 不可用（降级）
         └─ 纯 Instructor：prompt 注入 schema + max_retries 重试纠错
              → 失败 N 次后抛 StructuredOutputError，调用方走原 fallback
```

### 新建 `structured_llm_service.py`

```python
from pydantic import BaseModel
from typing import TypeVar, Type

T = TypeVar("T", bound=BaseModel)

class StructuredOutputError(Exception):
    """结构化输出在所有重试后仍失败"""

async def extract_structured(
    messages: list[dict],
    response_model: Type[T],
    *,
    model: str | None = None,
    max_retries: int = 2,
    temperature: float = 0.1,
    max_tokens: int = 2000,
) -> T:
    """统一结构化输出入口。

    1. 尝试 vLLM guided_json（response_model.model_json_schema()）
    2. Instructor 客户端做 Pydantic 验证 + 重试
    3. 全部失败抛 StructuredOutputError（调用方决定降级）
    """
```

实现要点：
- 用 `instructor.from_openai(AsyncOpenAI(base_url=settings.LLM_BASE_URL, ...))` 包客户端
- guided_json 通过 Instructor 的 `extra_body={"guided_json": schema}` 或直接走 vLLM mode 传入
- 复用 `settings.LLM_BASE_URL` / `LLM_API_KEY` / `DEFAULT_CHAT_MODEL`
- `httpx` 客户端保持 `trust_env=False`（与全仓铁律一致）
- 熔断：复用 `llm_client._breaker` 或自建轻量熔断（保持与现有一致行为）

### 现有 service 改造（最小侵入）

每个受影响 service：定义其输出的 Pydantic 模型 → 调 `extract_structured(...)` → 拿到强类型对象 → 失败时 `except StructuredOutputError` 走原有 fallback（保证不回归）。

```python
# wp_document_recognizer.py 示意
class DocRecognitionResult(BaseModel):
    doc_type: str
    fields: dict[str, str]
    confidence: float

try:
    result = await extract_structured(messages, DocRecognitionResult, max_tokens=...)
    return result.model_dump()
except StructuredOutputError:
    logger.warning("structured extract failed, fallback to legacy parse")
    return _legacy_json_parse(...)  # 原有逻辑保留
```

### Pydantic 模型定义位置

新建 `backend/app/schemas/llm_structured.py` 集中放三个场景的 response_model（doc recognition / evidence OCR / tsj review），避免散落 service 内。

## 配置开关

```python
# config.py
LLM_STRUCTURED_OUTPUT_ENABLED: bool = True  # service 层总开关：关 → 完全走 legacy json.loads
LLM_GUIDED_DECODING_ENABLED: bool = True    # vLLM guided_json 子开关
LLM_STRUCTURED_MAX_RETRIES: int = 2          # Instructor 重试次数
```

三层分级（design 实现必须严格对应 Req 5.3）：

| LLM_STRUCTURED_OUTPUT_ENABLED | LLM_GUIDED_DECODING_ENABLED | 行为 |
|---|---|---|
| False | （忽略） | service 完全跳过 `extract_structured`，直接 legacy `json.loads`（等价改动前） |
| True | False | 调 `extract_structured`，纯 Instructor retry（不传 guided_json） |
| True | True | guided_json + Instructor 双层 |

- service 层判断模式：每个接入 service 在调 `extract_structured` 前先 `if not settings.LLM_STRUCTURED_OUTPUT_ENABLED: return _legacy_json_parse(...)`，保证总开关关时新服务**不被 import 触发副作用**
- guided 子开关由 `structured_llm_service` 内部读取，service 层无感

## Error Handling

| 场景 | 降级 |
|------|------|
| vLLM 不支持 guided_json（旧版本/未启用后端） | 自动降级纯 Instructor retry，记 warning 一次 |
| Instructor 重试 N 次仍失败 | 抛 StructuredOutputError，调用方走 legacy fallback |
| vLLM 服务不可用（连接失败/超时） | 复用熔断器，返回降级，不拖垮后端 |
| Pydantic 校验失败（字段类型/缺失） | Instructor 自动把校验错误反馈给模型重试 |
| 模型吐出超长被截断（finish_reason=length） | 复用 llm_client 现有处理，归类为重试 |

## 测试策略

- **单测**（mock vLLM 响应）：guided_json 透传正确性 / Instructor 重试触发 / StructuredOutputError 抛出 / 降级路径
- **PBT**（hypothesis，max_examples=5 遵守铁律）：任意合法 Pydantic 模型 round-trip（schema 生成 → mock 合法 JSON → 解析回模型）
- **集成**（需 vLLM 在线，标 `[ ]*` 外部依赖）：真实 Qwen3.5-27B 对 50 个 OCR 样本，对比 guided on/off 的 parse 成功率

## 与现有能力的关系

| 能力 | 复用 | 新增 |
|------|------|------|
| vLLM 调用 | `settings.LLM_BASE_URL` / httpx trust_env=False | guided_json 透传 |
| 熔断 | `llm_client._breaker` 行为 | 结构化场景熔断 |
| 降级 | 各 service 原 json.loads fallback | StructuredOutputError 触发点 |
| system 消息合并 | `_merge_system_messages`（vLLM 单 system 约束） | Instructor 模式同样遵守 |
