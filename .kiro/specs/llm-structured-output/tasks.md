# Tasks: 本地 LLM 结构化输出（Instructor + vLLM guided decoding）

## Overview

按 design 分 4 组增量实施：① 依赖+配置+核心服务 → ② Pydantic 模型 + guided/降级双路径 → ③ 三场景接入（不回归）→ ④ 测试收尾。每组可独立验证。

**勘察结论（实施前必读，三场景现状差异大）**：
- `wp_document_recognizer._llm_recognize`（line ~280）：现用最脆弱的 `content[content.index("{"):content.rindex("}")+1]` + `json.loads`，无重试。返回字段 = `DOC_TYPE_FIELDS[doc_type]`（4 类：voucher/invoice/warehouse/bank_receipt，字段名已在文件顶部定义）。仅 `WP_AI_SERVICE_ENABLED=True` 时走 LLM，否则 `_get_stub_fields` 返回 None 模板。
- `wp_evidence_ocr_service._ocr_and_recognize`（line ~230）：**当前是 stub（TODO 待接入），根本没调 LLM**。字段 = `VOUCHER_FIELDS`（8 个，与 recognizer 的 voucher 一致）。本场景是"从 stub 首次接入"非"替换"。
- `tsj_structured_output_service`：**已有成熟 `parse_findings_json`（3 策略正则：直接/代码块/`{...}`）+ `process_review_response` fallback**。findings schema 字段已知：`issue_type/severity/sheet/cell_range/description/evidence_ref/remediation`。接入时 `extract_structured` 作为 `parse_findings_json` 的前置增强，解析失败仍走现有 fallback。
- 两套 LLM 客户端：本 spec 三场景都用 `llm_client.chat_completion`（非 AIService(db)）；新服务复用 `settings.LLM_BASE_URL`/`LLM_API_KEY`/`DEFAULT_CHAT_MODEL`。
- config 现状：`WP_AI_SERVICE_ENABLED=False`（默认）；新增开关与之独立。

## Tasks

### 组 ① 依赖 + 配置 + 核心服务骨架

- [x] 1. 依赖与配置
  - `backend/requirements.txt` 加 `instructor`（pin 版本，如 `instructor>=1.5,<2`）+ 确认 `openai`（instructor 依赖，未显式列则加）
  - `backend/app/core/config.py` 的 `Settings` 加三项：`LLM_STRUCTURED_OUTPUT_ENABLED: bool = True`（service 层总开关）/ `LLM_GUIDED_DECODING_ENABLED: bool = True`（guided 子开关）/ `LLM_STRUCTURED_MAX_RETRIES: int = 2`
  - `.env.example` 同步三项 + 注释说明分层语义
  - _Requirements: 5.1_

- [x] 2. 新建 `backend/app/services/structured_llm_service.py` 骨架
  - 模块级 `logger` + `T = TypeVar("T", bound=BaseModel)`
  - 定义 `class StructuredOutputError(Exception)`
  - 定义 `async def extract_structured(messages: list[dict], response_model: Type[T], *, model: str | None = None, max_retries: int | None = None, temperature: float = 0.1, max_tokens: int = 2000) -> T` 签名 + docstring（`max_retries=None` 时取 `settings.LLM_STRUCTURED_MAX_RETRIES`）
  - 延迟初始化单例客户端：`instructor.from_openai(AsyncOpenAI(base_url=settings.LLM_BASE_URL, api_key=settings.LLM_API_KEY, http_client=httpx.AsyncClient(trust_env=False)))`，模块级缓存 + `_get_client()` 懒构造
  - _Requirements: 1.1, 1.3_

- [x] 3. 检查点 — `python -c "from app.services.structured_llm_service import extract_structured, StructuredOutputError"` 无错 + getDiagnostics 干净

### 组 ② guided_json 透传 + Instructor 重试 + 降级

- [x] 4. 实现 guided_json 优先路径
  - `WHILE settings.LLM_GUIDED_DECODING_ENABLED` → 把 `response_model.model_json_schema()` 通过 instructor 调用的 `extra_body={"guided_json": <schema>}` 传入（vLLM OpenAI 兼容扩展参数）
  - 成功路径：vLLM 解码层约束 + instructor 的 Pydantic 二次校验（`response_model=response_model`）
  - 返回强类型 `response_model` 实例
  - _Requirements: 2.1, 2.3, 1.2_

- [x] 5. 实现自动降级 + Instructor retry
  - guided_json 不被 vLLM 接受（捕获 `openai.BadRequestError`/参数错/旧版本特征）→ 降级：去掉 `extra_body` 重试纯 instructor retry，`logger.warning` 记一次（模块级标志位避免刷屏）
  - `max_retries` 默认取 `settings.LLM_STRUCTURED_MAX_RETRIES`；instructor 的 `max_retries=` 参数传入，Pydantic 校验失败自动反馈模型重试
  - 耗尽重试（instructor 抛 `InstructorRetryException` 等）→ 包装抛 `StructuredOutputError`
  - `settings.LLM_GUIDED_DECODING_ENABLED=False` → 直接走 instructor retry（不传 guided_json）
  - _Requirements: 2.2, 2.4, 3.1, 3.2, 1.4_

- [x] 6. 熔断行为对齐
  - vLLM 连续失败（ConnectError/Timeout）→ 复用 `llm_client._breaker`（import 并在失败时 `record_failure`/成功 `record_success`），熔断打开时快速抛 `StructuredOutputError` 不实际请求
  - _Requirements: 3.3_

- [x] 7. 检查点 — 核心服务单测先行（mock `AsyncOpenAI`/instructor，覆盖：guided 成功 / guided 降级 instructor / 重试耗尽抛 StructuredOutputError / 熔断打开快速失败 四条路径）

### 组 ③ Pydantic 模型 + 场景接入（按活跃度分档，不回归）

- [x] 8. 新建 `backend/app/schemas/llm_structured.py`
  - `DocRecognitionResult`：`doc_type: str` + `fields: dict[str, str | None]`（字段动态，与现有 `fields` dict 返回结构一致；可选按 `DOC_TYPE_FIELDS` 校验键集）
  - `EvidenceOcrResult`：8 个 VOUCHER_FIELDS（voucher_no/voucher_date/debit_amount/credit_amount/summary/account_name/preparer/reviewer，全 `str | None`）
  - `TsjFinding`（单条）：`issue_type/severity/sheet/cell_range/description/evidence_ref/remediation`；`TsjReviewResult`：`findings: list[TsjFinding]`（与 STRUCTURED_OUTPUT_INSTRUCTION JSON 对齐；**即使 tsj 接入降级，模型也定义好供 spec-5 DSPy 复用**）
  - _Requirements: 4.5_

- [x] 9. `wp_document_recognizer.py` 接入（**核心交付，活链路**，改 `_llm_recognize` line ~280）
  - 函数开头：`if not settings.LLM_STRUCTURED_OUTPUT_ENABLED:` → 保留现有 `content[index..rindex] + json.loads` 旧逻辑（legacy 不动）
  - 总开关开：`result = await extract_structured(messages, DocRecognitionResult, max_tokens=1000, temperature=0.1)` → 返回 `result.fields`（或 `model_dump()` 适配现有 `fields` dict 消费）
  - `except StructuredOutputError:` → `logger.warning` + 回退现有 json.loads 解析（不回归）
  - **验证基线**：经 `routers/wp_document_recognize.py` 端点（recognize_batch）端到端可测
  - _Requirements: 4.1, 4.4, 5.2, 5.3_

- [ ]* 10. `wp_evidence_ocr_service.py` 接入（service 存在无 router，从 stub 首次接入）
  - `_ocr_and_recognize` 现状 stub（返回 `{field: None}`）；接入：`if not (settings.LLM_STRUCTURED_OUTPUT_ENABLED and settings.WP_AI_SERVICE_ENABLED):` → 保留 stub（不破坏 WP_AI 开关语义）
  - 两开关都开：构造 voucher prompt（参照 recognizer VOUCHER 模板）→ `extract_structured(messages, EvidenceOcrResult, ...)` → `result.model_dump()`
  - `except StructuredOutputError:` → 回退 stub
  - **标 `[ ]*`**：端到端验证依赖未来 router 接线，当前仅单测覆盖 service 层逻辑
  - _Requirements: 4.2, 4.4, 5.2, 5.3_

- [ ]* 11. `tsj_structured_output_service.py` 接入（孤儿，零调用方——降级可选）
  - 🔴 **勘察实证：`process_review_response`/`build_structured_prompt`/`write_findings_to_ai_content` 全仓零外部调用方**。接入一个无人调的函数无法验证不回归（无基线）。
  - **本任务降级 `[ ]*`**：仅当 tsj review 上游链路真正接线时才做；届时上游产生 messages 处改调 `extract_structured(messages, TsjReviewResult, ...)`，`process_review_response` 的 `parse_findings_json` + fallback 保留作 legacy 兜底
  - 当前 spec 范围内：TsjReviewResult 模型已在 task 8 定义即可（满足复用需求）
  - _Requirements: 4.3, 4.4, 5.2, 5.3_

- [x] 12. 检查点 — recognizer（活链路）getDiagnostics 干净 + 原 fallback 保留可走 + `LLM_STRUCTURED_OUTPUT_ENABLED=False` 时 recognizer 完全走 legacy（不触发 extract_structured）；evidence/tsj 按 `[ ]*` 状态如实标记
  - _Requirements: 5.2, 5.4_

### 组 ④ 测试与收尾

- [x] 13. 单元测试 `backend/tests/test_structured_llm_service.py`
  - mock instructor 客户端（monkeypatch `_get_client` 返回 mock）
  - 断言：guided_json 透传时 `extra_body` 含 schema / instructor 重试触发 / 耗尽抛 `StructuredOutputError` / guided BadRequest 降级 instructor / `LLM_GUIDED_DECODING_ENABLED=False` 不传 guided_json / 熔断打开快速失败
  - service 层：`LLM_STRUCTURED_OUTPUT_ENABLED=False` 时 mock 确认 `wp_document_recognizer._llm_recognize` 不调 `extract_structured`（走 legacy）
  - _Requirements: 6.1, 5.2, 5.3_

- [x] 14. PBT `backend/tests/test_structured_llm_pbt.py`
  - hypothesis `max_examples=5`：用 hypothesis 生成简单 Pydantic 模型实例 → `model_dump_json()` 作 mock LLM 返回 → `extract_structured` round-trip 解析回等值实例
  - _Requirements: 6.2_

- [ ] 15.* 集成测试 `backend/tests/test_structured_llm_integration.py`（外部依赖 vLLM 在线）
  - 50 个真实/构造 OCR 样本，对比 `LLM_GUIDED_DECODING_ENABLED` on/off 的 parse 成功率，断言 guided 成功率 ≥98%
  - `@pytest.mark.skipif(not vllm_online)`，需 vLLM 8100 在线
  - _Requirements: 6.3_

- [x] 16. 最终检查点
  - `python -m pytest backend/tests/test_structured_llm_service.py backend/tests/test_structured_llm_pbt.py -v` 全绿
  - recognizer（活链路）getDiagnostics 无错 + legacy fallback 代码块未删除（grep 确认 `json.loads` 路径仍在）
  - evidence/tsj 的 `[ ]*` 状态如实标记（evidence 单测覆盖 service 层 / tsj 仅模型定义）
  - 三开关分层语义验证：总关→legacy / 总开+guided 关→纯 instructor / 全开→双层
