# DSPy 可行性评估

> 评估日期：2026-06-04
> 结论：**仅文档（不落代码）**
> Requirements: 5.1, 5.4

## 1. DSPy 简介

[DSPy](https://dspy-docs.vercel.app/) 是 Stanford NLP 团队开发的框架，核心理念是将 LLM prompt 视为可编译、可优化的"程序"而非硬编码字符串：

- **Signature**：声明式输入→输出契约（如 `question -> answer`）
- **Module**：组合 Signature 的可复用程序块（ChainOfThought / ReAct / Predict 等）
- **Teleprompter/Optimizer**：自动优化 prompt（BootstrapFewShot / MIPROv2 / COPRO 等）
- **Adapter**：支持 OpenAI 兼容 endpoint（vLLM 天然适配）

关键价值主张：系统化 prompt 版本管理 + 自动优化 + 可组合性。

## 2. 当前架构现状

### 2.1 三套 LLM 调用路径

| 路径 | 位置 | 职责 | 调用方 |
|------|------|------|--------|
| `llm_client.chat_completion()` | `llm_client.py` | httpx + 熔断器，RAG 注入 | wp_llm_prompts / role_ai / pm / doc_ai_chat |
| `AIService(db).chat_completion()` | `ai_service.py` | 需 DB session 查 active model | OCR / knowledge / contract / wp_fill |
| `LLMService().generate()` | `llm_service.py` | 轻量封装，返 LLMResponse | 审计 stub 引擎 |

### 2.2 结构化输出（spec `llm-structured-output`）

`structured_llm_service.py` 已实现 Instructor + vLLM `guided_json` 双层：
- 主路径：`instructor.from_openai(AsyncOpenAI)` + `response_model: type[T]` (Pydantic BaseModel)
- vLLM 加速：`extra_body={"guided_json": schema}` 约束生成
- 降级：guided_json 被拒 → 纯 Instructor retry
- 统一入口：`extract_structured(messages, response_model)` → `T`

### 2.3 prompt 散落现状

审计 LLM prompt 以字符串模板散落在各 service 内（wp_llm_prompts / role_ai / pm / 各循环复核）。无统一版本管理，修改需直接改代码。

## 3. DSPy 整合成本评估

### 3.1 与 vLLM 的兼容性 ✅

DSPy 2.x 原生支持 OpenAI 兼容 endpoint：
```python
import dspy
lm = dspy.LM("openai/Qwen3.5-27B-NVFP4", api_base="http://localhost:8100", api_key="not-needed")
dspy.configure(lm=lm)
```
技术上无障碍，vLLM + Qwen3.5 可直接对接。

### 3.2 与 Instructor/Pydantic 的重叠 ⚠️

| 能力 | Instructor (已有) | DSPy |
|------|-------------------|------|
| 结构化输出 | `response_model` Pydantic | `TypedPredictor` / `dspy.OutputField(type=...)` |
| JSON Schema 约束 | vLLM guided_json | 需自行对接 guided_json（DSPy 不原生支持） |
| 重试/验证 | Instructor 内置 max_retries + Pydantic validation | 需自定义 Assertion + retry 逻辑 |
| 学习曲线 | 低（Pydantic 生态成熟） | 中-高（DSPy 独有概念体系） |

**结论**：结构化输出场景 Instructor 已完整覆盖，DSPy 在此无增量价值。

### 3.3 DSPy 独有价值：Prompt 优化 ⚠️

DSPy 的核心差异化在于 **自动 prompt 优化**（Teleprompter）：
- 需要：标注数据集（input-output pairs）作为训练/评估集
- 需要：可量化的评估指标（accuracy / F1 / 自定义 metric）
- 需要：足够的调用次数（BootstrapFewShot 需 ~100 次 LLM 调用编译一个 Module）

**审计场景障碍**：
1. **标注数据稀缺**：审计复核结果无系统化标注数据集，现有场景（控制了解/销售收入复核等）输出质量靠人工判断
2. **评估指标模糊**：审计结论的"正确性"难以自动量化（非 classification/extraction 类明确任务）
3. **调用成本**：每次优化需 100+ 次 LLM 调用，vLLM 本地部署无 API 费用但 GPU 时间有限

### 3.4 架构碎片化风险 🔴

当前已存在 3 套 LLM 调用路径 + 1 套 Instructor 结构化输出。引入 DSPy = 第 5 种 LLM 交互方式：

```
现状：llm_client → AIService → LLMService → Instructor
引入后：llm_client → AIService → LLMService → Instructor → DSPy
```

对 1-2 人团队而言，维护 5 套并行方案的认知负担过重。

### 3.5 孤儿代码风险

`tsj_structured_output_service`（TsjReviewResult 等模型）全仓 0 调用方 = 孤儿代码。这是最适合做 DSPy PoC 的候选，但其孤儿状态意味着即使改造成功也无实际业务流量验证。

## 4. 学习曲线与团队 ROI

| 维度 | 评估 |
|------|------|
| API 稳定性 | DSPy 2.x 已发布但仍在快速迭代（月级 breaking change） |
| 文档质量 | 中等（核心概念文档齐全，高级用法文档薄弱） |
| 调试难度 | 高（Signature→Module→Optimizer 多层抽象，错误定位困难） |
| 团队规模 | 1-2 人（学习成本无法在团队内分摊/传播） |
| 投产时间 | 估 2-3 周（含学习+PoC+对比验证） |
| 预期收益 | 低-中（prompt 优化需标注数据，当前不具备） |

## 5. 决策

### 结论：仅文档，不落代码

**理由**：

1. **Instructor 已覆盖核心痛点**：结构化输出（失败率从 20-30% 降至 <2%）是当前最紧迫需求，Instructor + guided_json 已完整解决
2. **DSPy 独有价值（自动优化）的前置条件不满足**：缺乏标注数据 + 评估指标，无法发挥 Teleprompter 核心优势
3. **架构碎片化**：3 套 LLM 客户端 + Instructor = 4 种方式已够，第 5 种加剧维护负担
4. **团队 ROI 不达标**：1-2 人团队，2-3 周学习投入换取不确定收益
5. **最佳 PoC 候选是孤儿代码**：tsj_structured_output_service 0 调用方，即使改造成功也无业务验证价值
6. **优先级最低**：gitleaks/SQLFluff/uv/Docling 均已完成或评估完毕，DSPy 在此轮生命周期内无迫切性

### 未来重新评估触发条件

以下任一条件满足时建议重新评估 DSPy：

1. **prompt 优化成为瓶颈**：审计复核 LLM 输出质量不达标，且 Instructor 重试/guided_json 无法解决
2. **积累标注数据**：建立了审计复核 input-output 对标注集（≥50 对）
3. **团队扩大**：有专人负责 ML/NLP 工程，可承担学习曲线
4. **DSPy 生态成熟**：API 稳定 + 与 Instructor/Pydantic 有官方集成方案
5. **合并 LLM 客户端**：将 3 套客户端统一后，再考虑上层框架引入

## 6. 替代方案（当前推荐路径）

| 需求 | 推荐方案 | 状态 |
|------|---------|------|
| 结构化输出 | Instructor + vLLM guided_json | ✅ spec `llm-structured-output` 已实施 |
| Prompt 版本管理 | Git 管理 prompt 模板文件（`backend/prompts/` 目录） | 💡 待规划 |
| Prompt 质量评估 | 手动 A/B 对比 + 审计专家评审 | 现状 |
| Prompt 系统化组织 | 统一 prompt 注册表 + 模板变量化 | 💡 中期目标 |

---

*本评估基于 DSPy 2.x（2026-06 时点）、项目当前架构（3 套 LLM 客户端 + Instructor 结构化输出）、及 1-2 人团队规模作出。条件变化时应重新评估。*
