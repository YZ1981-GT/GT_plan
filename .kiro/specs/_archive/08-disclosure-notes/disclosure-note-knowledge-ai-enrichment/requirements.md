# Requirements Document

## Introduction

附注模块复盘（2026-07-24）确认了内容层最大缺口：**用户要求的"文字部分参照知识库中指定文档（上年审计报告及附注、附注模板）以及 AI 的利用"当前完全缺失**。

现状（已核实）：

- `DisclosureEngine._generate_text_with_llm`（`disclosure_engine.py:521`）生成附注正文时，system prompt 是通用的，user prompt 只喂"科目名 + 试算表期末/期初数字"，**不检索任何知识库文档**。
- 上年附注仅从 `year-1` 的 `disclosure_notes.text_content`（`_prior_notes_cache`）读取，**仅连续审计且上年在本平台做过才有**；知识库上传的《上年审计报告及附注》《附注模板》PDF/docx **读不到**。
- 平台已有成熟 RAG 基础设施（`KnowledgeIndexService.semantic_search`，pgvector + BM25 + ilike 三级降级，`scope='knowledge_doc'` 可检索知识库文档，结果带 `document_name/folder_path/score`），但**附注生成链路完全没调用它**。

本 spec 目标：把知识库 RAG 检索接入附注 AI 正文生成与预填，让附注文字能"参照知识库中指定文档（上年审计报告及附注、附注模板、其他单位附注）"，并在前端提供"一键预填 / AI 填充 / 参照文档填充"的可溯源入口，同时严守 AI 治理（不自动写、经确认流）与 fail-open 零回归。

**范围边界**：本 spec 仅覆盖复盘"维度 2（内容/文字层）"的知识库+AI 增强。复盘的"公式管理校验公式（维度 4）""`resolve_formula` 表内公式取数""报表主要项目注释表格↔文字联动（维度 3）""`_sub_table_columns` 覆盖率"属独立技术域，各自后续单独立 spec，本 spec 不动。不改 `disclosure_notes` 表结构、不改现有模板生成骨架、不改底稿→附注同步机制。

## Glossary

| 术语 | 含义 |
|------|------|
| RAG | 检索增强生成（Retrieval-Augmented Generation）：先从知识库检索相关片段，作为上下文注入 LLM 再生成 |
| Knowledge_Retrieval | 经 `KnowledgeIndexService.semantic_search(scope='knowledge_doc', ...)` 检索知识库文档 chunk，返回带 `content/document_name/folder_path/score/source_type` 的结果列表 |
| Note_Context_Query | 为某附注章节构造的检索查询串（由 section_title + account_name + 科目关键词组成） |
| Grounded_Draft | 由 RAG 上下文驱动生成的附注正文草稿（含引用来源列表） |
| Citation | 生成草稿所依据的知识库来源标识（document_name + folder_path + chunk 片段），随草稿返回供审计师核对 |
| Prior_Year_Note_Source | 上年附注文字来源：①`year-1` DB 记录（现状）②知识库中检索到的上年审计报告/附注文档片段（新增回退） |
| Global_KB | 全局知识库（`GLOBAL_KB_PROJECT_ID`）：事务所级/共享文档（附注模板、其他单位范本）。`semantic_search` 的向量召回已同时检索 `[project_id, GLOBAL_KB_PROJECT_ID]`，故"参照其他单位模板"经全局知识库达成，**不跨具体客户项目边界** |
| Reference_Only_Mode | "参照文档填充"的纯检索模式：只返回检索到的原文片段（供审计师人工引用/复制），**不调用 LLM 生成**，与 AI grounded 生成模式并列 |
| Batch_Prefill | 一键批量 AI 预填充：对当前项目所有"空/草稿"章节批量执行 RAG 生成，逐章节独立、单章失败不影响其余、带进度 |
| Narrative_Only | AI 生成的附注文字仅为叙述草稿，**不产出/不编造披露数值**；金额等数值以表格 / resolver / 底稿审定数为准 |
| AI_Governance_Flow | AI 生成内容不直接写库，经 `wrap_ai_output_with_log` → pending → 审计师确认（`/api/ai-chat/adopt` 或采纳流）后才落 `text_content` |
| Fail_Open | 知识库/LLM 不可用时不阻断，降级到现有三级填充（上年 DB → 通用 LLM → 模板默认文字），行为与接入前一致 |
| DisclosureEditor | 附注模块前端主界面 `views/DisclosureEditor.vue` |
| DocAiChatPanel | 附注 AI 对话面板（`useDocAiChat` + `adoptContent` 采纳流） |

## Requirements

### Requirement 1: RAG 检索接入 AI 正文生成

**User Story:** 作为审计助理，我希望附注 AI 生成正文时参照知识库中的上年审计报告/附注/模板，使草稿贴合本项目历史口径而非空泛套话。

#### Acceptance Criteria

1. WHEN `_generate_text_with_llm` 为某章节生成正文 THEN 系统 SHALL 先用 Note_Context_Query（section_title + account_name + 科目关键词）经 `KnowledgeIndexService.semantic_search(scope='knowledge_doc', top_k≤N)` 执行 Knowledge_Retrieval。
2. WHEN 检索命中 ≥1 条知识库片段 THEN 系统 SHALL 将命中片段（含 document_name 标注）拼入 LLM 的 user prompt 作为参照上下文，并在 system prompt 中要求"优先参照所提供资料的表述口径与结构"。
3. WHEN 检索命中 0 条 OR 检索抛异常 THEN 系统 SHALL 不阻断生成，退回无 RAG 上下文的现有生成路径（Fail_Open）。
4. WHERE 章节带 `account_name` 或可推断 `account_code`/`audit_area` THE 系统 SHALL 把这些作为 `semantic_search` 的上下文加权参数传入以提升相关性。
5. WHEN 生成 Grounded_Draft THEN 系统 SHALL 一并返回 Citation 列表（每条含 document_name + folder_path + 片段摘要 + `is_stale` 索引新鲜度标记），不得丢弃来源。
6. THE Knowledge_Retrieval SHALL 复用现有 `semantic_search` 不新建检索实现，不改其签名。
7. THE Grounded_Draft 的正文 SHALL 为中文，且当章节属 soe/listed 变体时优先参照同准则变体的资料表述。

### Requirement 2: 上年附注支持从知识库文档读取

**User Story:** 作为审计助理，我希望在上年审计不在本平台做的情况下，附注仍能从知识库上传的《上年审计报告及附注》抽取文字预填。

#### Acceptance Criteria

1. WHEN 某章节 `year-1` DB 附注文字缺失（`_prior_notes_cache` 无该 section 或长度不足）THEN 系统 SHALL 尝试从知识库检索该章节对应的上年附注文档片段作为 Prior_Year_Note_Source。
2. WHEN `year-1` DB 附注文字存在 THEN 系统 SHALL 优先使用 DB 记录（保持现有优先级 1 不变），知识库仅作缺失时的回退。
3. WHEN 知识库回退命中 THEN 系统 SHALL 将其纳入正文三级填充策略的"优先级 1（上年）"层，并保留 Citation 标注来源为知识库文档。
4. WHEN 知识库回退未命中 THEN 系统 SHALL 静默继续到优先级 2（LLM）/ 优先级 3（模板），不报错、不阻塞（Fail_Open）。

### Requirement 3: 前端一键预填 / AI 填充 / 参照文档填充入口与溯源

**User Story:** 作为审计助理，我希望在附注编辑器里对当前章节点"AI 填充"或"参照文档填充"，看到 AI 依据了哪些知识库文档，再决定是否采纳。

#### Acceptance Criteria

1. WHEN 用户在 DisclosureEditor 当前章节触发"AI 填充" THEN 系统 SHALL 调用带 RAG 的生成，并在采纳前展示 Grounded_Draft + Citation 列表。
2. WHEN 展示 Citation THEN 前端 SHALL 显示每条来源的 document_name 与 folder_path，供审计师点选核对。
3. WHEN 用户采纳草稿 THEN 系统 SHALL 走 AI_Governance_Flow（不直接覆盖 `text_content`）。
4. WHERE 检索无命中 THE 前端 SHALL 明确提示"未检索到可参照的知识库文档，已用通用生成"，不静默假装有依据。
5. WHEN 用户未采纳 THEN 现有 `text_content` SHALL 保持不变。
6. WHERE 当前章节被他人编辑锁定（`sectionLocks`）THE 前端 SHALL 禁用"采纳"（可预览草稿但不可写入），与现有编辑锁语义一致。

### Requirement 4: 参照其他单位/指定文档模板填充

**User Story:** 作为现场经理，我希望能指定知识库里某个文档（如某单位附注模板、全局共享范本）作为参照来源，或只调出相关原文片段供我人工引用。

#### Acceptance Criteria

1. WHEN 用户在填充时指定一个或多个知识库文档/文件夹作为参照范围 THEN 系统 SHALL 将 Knowledge_Retrieval 限定在该范围内（按 document/folder 过滤）。
2. WHEN 未指定参照范围 THEN 系统 SHALL 按默认 `scope='knowledge_doc'` 检索（含项目文档 + Global_KB 全局共享文档，Requirement 1 行为）。
3. WHERE 指定文档不可访问（权限/已删）THE 系统 SHALL 跳过该文档并如实提示（`skipped_docs`），不将其纳入上下文。
4. THE 参照范围过滤 SHALL 复用 `semantic_search` 的权限过滤（`user` 参数），不绕过知识库访问控制；"其他单位模板"来源限于 Global_KB 全局共享文档，**不跨读其他具体客户项目的私有文档**。
5. WHEN 用户选择 Reference_Only_Mode THEN 系统 SHALL 只返回检索到的原文片段（供人工引用），不调用 LLM 生成、不产 Grounded_Draft。
6. WHEN 用户选择 AI 生成模式 THEN 系统 SHALL 按 Requirement 1 生成 Grounded_Draft（参照范围内检索结果作上下文）。

### Requirement 5: AI 输出治理（不自动写 + 可溯源留痕）

**User Story:** 作为质量控制复核合伙人，我希望 AI 生成的附注文字经确认流才落库，且留有 AI 来源痕迹，避免未经复核的机器文字直接进正式附注。

#### Acceptance Criteria

1. WHEN AI 生成 Grounded_Draft THEN 系统 SHALL 经 `wrap_ai_output_with_log`/现有采纳流处理，pending 状态不直接写 `text_content`。
2. WHEN 审计师确认采纳 THEN 系统 SHALL 才把内容落入 `text_content`（**仅 substantive 正文，不写入 `guidance_text`**），并记录本次采纳的 Citation 溯源。
3. THE 本 spec SHALL 不改动现有 AI 治理链（`/api/ai-chat/adopt` / `wrap_ai_output_with_log`），仅在其上游补 RAG 上下文与 Citation。

### Requirement 6: Fail-Open 降级与零回归

**User Story:** 作为审计助理，我希望知识库或 AI 服务挂掉时附注生成照常工作，接入前能跑的现在也能跑。

#### Acceptance Criteria

1. WHEN 知识库索引为空 / `semantic_search` 抛异常 / LLM 不可用 THEN 系统 SHALL 退回接入前的三级填充策略，`generate_notes` 与 `refill_sections` 不因 RAG 失败而失败。
2. WHEN RAG 未启用（配置开关关闭）THEN 系统 SHALL 行为与接入前逐字一致（现有测试全绿）。
3. THE RAG 接入 SHALL 通过配置开关（默认可控）控制，可一键回退。
4. WHEN 批量生成（`generate_notes` 遍历多章节）中单章节 RAG 失败 THEN 系统 SHALL 仅该章节降级，不影响其余章节。

### Requirement 7: 检索相关性、范围与性能

**User Story:** 作为审计助理，我希望 AI 参照的是与当前科目/领域真正相关的资料，且批量生成不因检索拖垮。

#### Acceptance Criteria

1. THE Note_Context_Query SHALL 由 section_title + account_name + 科目关键词组成，不使用整段模板文字作查询（避免噪声）。
2. WHERE 可推断 account_code / audit_area THE 系统 SHALL 传入 `semantic_search` 的 `account_code`/`audit_area` 上下文加权参数。
3. THE `top_k` SHALL 有上限（如 ≤5），拼入 prompt 的上下文 SHALL 有字符预算上限（截断超长片段），避免 token 溢出。
4. WHEN `generate_notes` 批量遍历章节 THEN RAG 检索 SHALL 按章节独立执行且不引入 N+1 之外的额外全量扫描（复用现有预加载缓存不受破坏）。

### Requirement 8: 正确性属性与可测性

**User Story:** 作为质量控制复核合伙人，我希望关键行为（Fail-Open、优先级、不自动写、Citation 不丢）有可测断言守卫。

#### Acceptance Criteria

1. THE 上年优先级（DB 优先于知识库回退，知识库优先于 LLM，LLM 优先于模板）SHALL 有测试守卫。
2. THE Fail-Open（检索/LLM 异常 → 降级不抛）SHALL 有测试守卫。
3. THE Citation 随 Grounded_Draft 一并返回且与命中片段一致 SHALL 有测试守卫。
4. THE AI 输出不直接写 `text_content`（经确认流）SHALL 有测试守卫。
5. THE RAG 关闭时行为与接入前一致（零回归）SHALL 有测试守卫。
6. THE Reference_Only_Mode 不调用 LLM（无生成）SHALL 有测试守卫。
7. THE 批量预填充单章失败隔离 SHALL 有测试守卫。

### Requirement 9: 反幻觉与数值安全（审计域约束）

**User Story:** 作为质量控制复核合伙人，我要求 AI 生成的附注文字只起草叙述、绝不编造披露数字或事实，避免未经证据支持的机器数字进入正式附注。

#### Acceptance Criteria

1. THE Grounded_Draft SHALL 为 Narrative_Only——AI 仅起草文字叙述，披露数值以附注表格 / resolver 取数 / 底稿审定数为准，不由 AI 产出权威数值。
2. WHERE system prompt 构造 THE 系统 SHALL 明确约束"只依据所提供的资料与数据表述，不得虚构未提供的金额、比例、日期、主体名称"。
3. WHEN 生成文字中出现具体金额/比例 THEN 该数值 SHALL 仅可来自注入上下文（检索片段或传入的 TB/表格数据），前端 SHALL 提示审计师"AI 文字中的数字须与附注表格核对"。
4. THE 本 spec SHALL 不新增 AI 自动写入附注表格数值单元格的路径（数值联动属报表主要项目注释/公式 spec，不在本 spec）。

### Requirement 10: 一键批量 AI 预填充

**User Story:** 作为审计助理，我希望对整套附注一键 AI 预填充空白/草稿章节的文字，而不用逐章节手动触发。

#### Acceptance Criteria

1. WHEN 用户触发一键批量预填充 THEN 系统 SHALL 对当前项目所有"文字为空或 draft"的章节执行 Batch_Prefill（带 RAG），逐章节生成 Grounded_Draft。
2. WHEN 批量生成中某章节检索/LLM 失败 THEN 系统 SHALL 仅该章节降级（Fail_Open），不影响其余章节，并在结果汇总中标注该章节降级。
3. WHEN 批量生成完成 THEN 系统 SHALL 返回逐章节结果（生成/降级/跳过）与各自 Citation，供审计师逐章确认采纳（仍经 AI_Governance_Flow，不批量自动写库）。
4. THE 批量预填充 SHALL 跳过已有实质正文/已锁定/manual_override 的章节，不覆盖既有内容。
5. WHERE 章节数量较多 THE 系统 SHALL 提供进度反馈，不因单次批量阻塞界面。
