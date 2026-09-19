# Requirements: 本地 LLM 结构化输出（Instructor + vLLM guided decoding）

## Introduction

本地 Qwen3.5-27B 通过 prompt 要求吐 JSON 再 `json.loads` 的方式实测失败率 20-30%（markdown 包裹 / 截断 / 字段缺失 / 类型错）。引入 **Instructor（Pydantic 验证 + 重试纠错）** + **vLLM guided decoding（`guided_json`，解码层约束语法）** 双层保障，把结构化输出失败率降到 <2%，覆盖三个现有场景：底稿文档识别、证据 OCR 结构化、TSJ 审计复核结构化输出。

本方案纯本地：Instructor 是 Python 库，guided decoding 是已部署 vLLM 8100 自带能力，不引入外部服务、不新增 GPU 实例。

## Glossary

- **Instructor**: Python 库，包装 OpenAI 兼容客户端，传 `response_model=PydanticClass` 自动做验证 + 重试 + 错误反馈纠错
- **guided decoding**: vLLM 在解码阶段按 schema/grammar 约束 token 采样，保证输出语法合法（后端 xgrammar / outlines）
- **guided_json**: vLLM `/chat/completions` 扩展参数，传 JSON Schema 强约束输出结构
- **response_model**: Pydantic BaseModel 子类，定义期望的结构化输出
- **structured_llm_service**: 新建统一结构化输出入口服务
- **StructuredOutputError**: 所有重试后仍失败抛出的异常，触发调用方 legacy fallback
- **legacy fallback**: 各 service 原有的 `json.loads` 解析路径，保留作降级兜底

## Requirements

### Requirement 1: 统一结构化输出入口

**User Story:** As a 后端开发者, I want 一个统一的 `extract_structured(messages, response_model)` 入口, so that 所有需要 LLM 吐结构化数据的场景共用一套验证+重试+降级逻辑，不再各自手写 json.loads。

#### Acceptance Criteria
1. THE 系统 SHALL 提供 `structured_llm_service.extract_structured(messages, response_model, *, model, max_retries, temperature, max_tokens)` 异步函数，返回 `response_model` 强类型实例。
2. WHEN 调用方传入 Pydantic `response_model`, THE 系统 SHALL 用 `response_model.model_json_schema()` 作为输出约束。
3. THE 入口 SHALL 复用 `settings.LLM_BASE_URL` / `LLM_API_KEY` / `DEFAULT_CHAT_MODEL`，httpx 客户端保持 `trust_env=False`。
4. WHEN 所有重试失败, THE 系统 SHALL 抛出 `StructuredOutputError`（不返回半成品）。

### Requirement 2: vLLM guided decoding 优先 + 自动降级

**User Story:** As a 后端开发者, I want guided_json 在 vLLM 支持时自动启用、不支持时自动降级, so that 不同 vLLM 版本下都能跑，且支持时拿到语法保证。

#### Acceptance Criteria
1. WHILE `LLM_GUIDED_DECODING_ENABLED` 为真, THE 系统 SHALL 把 schema 作为 `guided_json` 透传给 vLLM。
2. IF vLLM 不支持 guided_json（旧版本/后端未启用/返回参数错误）, THEN 系统 SHALL 自动降级为纯 Instructor retry 模式并记一次 warning。
3. WHEN guided_json 生效, THE 系统 SHALL 仍执行 Pydantic 语义校验（双保险）。
4. WHERE `LLM_GUIDED_DECODING_ENABLED` 为假, THE 系统 SHALL 直接走纯 Instructor retry 模式。

### Requirement 3: Instructor 重试与纠错

**User Story:** As a 后端开发者, I want Pydantic 校验失败时自动把错误反馈给模型重试, so that 偶发的字段缺失/类型错能自愈而非直接失败。

#### Acceptance Criteria
1. THE 系统 SHALL 支持 `max_retries`（默认取 `LLM_STRUCTURED_MAX_RETRIES`=2）。
2. WHEN Pydantic 校验失败, THE 系统 SHALL 将校验错误信息反馈给模型并重试，直到成功或耗尽重试。
3. THE 重试 SHALL 复用熔断器行为，vLLM 连续失败时快速降级不拖垮后端。

### Requirement 4: 场景接入且不回归（按真实活跃度分档）

**User Story:** As an 审计助理, I want 文档识别/证据 OCR 的结构化提取更稳定, so that AI 提取的字段不再因 parse 失败而丢失。

> 勘察实证：recognizer 有活 router 链路；evidence 有 service 无 router；tsj 三函数全仓零调用方（孤儿）。接入按此分档。

#### Acceptance Criteria
1. THE `wp_document_recognizer`（活链路，**核心交付**）SHALL 定义其输出 Pydantic 模型并改用 `extract_structured`，且保留原 json.loads 作 legacy fallback。
2. THE `wp_evidence_ocr_service`（service 存在、无 router）SHALL 从 stub 接入 `extract_structured`（受 `WP_AI_SERVICE_ENABLED` + `LLM_STRUCTURED_OUTPUT_ENABLED` 双开关控制）；端到端验证依赖未来 router 接线，标 `[ ]*`。
3. THE `tsj_structured_output_service`（孤儿，零调用方）SHALL 仅定义 Pydantic 模型 `TsjReviewResult`（供复用/未来接线）；实际把 `extract_structured` 接入其链路标 `[ ]*`（依赖 tsj review 上游真正接线，否则无法验证不回归）。
4. WHEN `extract_structured` 抛 `StructuredOutputError`, THE 已接入的 service SHALL 捕获并走原有 legacy fallback（不回归、不抛 500）。
5. THE 三场景的 Pydantic 模型 SHALL 集中定义在 `backend/app/schemas/llm_structured.py`（recognizer/evidence 模型必做，TsjReviewResult 一并定义）。

### Requirement 5: 配置开关与可回退

**User Story:** As a 运维, I want 能用配置开关一键回退到旧解析路径, so that 新链路出问题时不影响生产。

#### Acceptance Criteria
1. THE 系统 SHALL 提供三个配置项：`LLM_STRUCTURED_OUTPUT_ENABLED`（service 层总开关，默认 True）/ `LLM_GUIDED_DECODING_ENABLED`（guided_json 子开关，默认 True）/ `LLM_STRUCTURED_MAX_RETRIES`（默认 2）。
2. WHERE `LLM_STRUCTURED_OUTPUT_ENABLED` 为假, THE 各接入 service SHALL 完全跳过 `extract_structured`、直接走原 `json.loads` 路径（不导入/不依赖新服务，等价于改动前行为）。
3. THE 三个开关 SHALL 分层独立：总开关关 → 完全 legacy；总开关开 + guided 关 → 纯 Instructor retry；两者全开 → guided + Instructor 双层。
4. THE `LLM_STRUCTURED_OUTPUT_ENABLED` SHALL 支持全局生效；如需按 service 细分回退，SHALL 以同名约定（如逐 service 读同一开关）保证语义一致。

### Requirement 6: 验证

**User Story:** As a 开发者, I want 单测+PBT 覆盖核心逻辑、集成测试验证真实收益, so that 改动可证明有效且不回归。

#### Acceptance Criteria
1. THE 系统 SHALL 有单元测试（mock vLLM）覆盖：guided_json 透传 / Instructor 重试 / StructuredOutputError 抛出 / 降级路径。
2. THE 系统 SHALL 有 PBT（hypothesis `max_examples=5`）验证 Pydantic 模型 schema round-trip。
3. THE 系统 SHOULD 有集成测试（标 `[ ]*` 外部依赖 vLLM 在线）对比 guided on/off 的 50 样本 parse 成功率。
