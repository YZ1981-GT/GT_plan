# Implementation Plan

## Overview

把知识库 RAG 检索接入附注 AI 正文生成，加法式、可开关、fail-open。执行顺序：配置开关+零回归安全网 → NoteKnowledgeEnricher 核心 → DisclosureEngine 注入 → ai-fill 端点 → 前端填充入口 → 测试门。每波先补测试守卫再改主代码；RAG 失败一律 fail-open 退回现有三级填充，现有测试零回归。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1", "2"], "desc": "配置开关 + 零回归安全网" },
    { "wave": 1, "tasks": ["3", "4"], "desc": "NoteKnowledgeEnricher 核心 + 单测/PBT" },
    { "wave": 2, "tasks": ["5", "6"], "desc": "DisclosureEngine 注入 + 集成测试" },
    { "wave": 3, "tasks": ["7"], "desc": "ai-fill 端点 + 采纳流对接" },
    { "wave": 4, "tasks": ["8", "9"], "desc": "前端 NoteAiFillDialog + DisclosureEditor 入口" },
    { "wave": 5, "tasks": ["10", "11"], "desc": "全量测试门 + Playwright(可选)" }
  ]
}
```

## Tasks

- [x] 1. 配置开关与检索接口核实
  - `app/core/config.py` 增 `DISCLOSURE_NOTE_RAG_ENABLED`(默认可控) / `DISCLOSURE_NOTE_RAG_TOP_K=5` / `DISCLOSURE_NOTE_RAG_CHAR_BUDGET=3000`
  - readCode 确认 `KnowledgeIndexService.semantic_search` 返回结果的 content 字段真实名（content / content_text），供 enricher 读取；文档/文件夹过滤所需字段确认
  - _需求：6.3, 7.3_

- [x] 2. 零回归安全网（characterization）
  - 为 `_generate_text_with_llm` + `generate_notes` 现有三级填充路径补 characterization 测试（mock llm_client），锁定"接入前"行为
  - 断言：开关关闭时行为与现状逐字一致（后续 P6 的基线）
  - _需求：6.1, 6.2_ _属性：Property 6_

- [x] 3. NoteKnowledgeEnricher 核心实现
  - 新建 `app/services/note_knowledge_enricher.py`：`GroundedDraft`(text/citations/degraded)/`Citation`(含 is_stale) DTO + `_GROUNDED_SYSTEM_PROMPT_ZH`(Narrative_Only 反幻觉约束+中文) + `build_query` + `retrieve`(复用 `semantic_search(scope='knowledge_doc')`, 含 project+Global_KB, fail-open, content 读 'content' 字段, 透传 is_stale) + `build_grounded_user_prompt`(截断 char_budget) + `generate_note_text`(reference_only 分支不生成) + `retrieve_prior_year_note` + `batch_prefill`(单章隔离+跳过既有/锁定/manual_override)
  - doc_filter 按 document/folder 过滤；user 权限透传（不越权跨客户项目，仅项目+Global_KB）
  - _需求：1.1, 1.4, 1.5, 1.6, 1.7, 2.1, 4.1, 4.4, 4.5, 7.1, 7.2, 7.3, 9.1, 9.2, 10.1, 10.4_

- [x] 4. NoteKnowledgeEnricher 单测 + PBT
  - `backend/tests/` 新建：build_query 不含整段模板(P7)、retrieve fail-open 异常/空→[](P2)、权限过滤(P10)、build_grounded_user_prompt 截断(P8)、doc_filter 范围(P9)、citations 与命中一致(P5)、命中即注入(P1)、reference_only 不调 LLM(P13)、反幻觉 system prompt 含约束+中文(P14/P16)、batch 跳过既有(P15)、batch 单章降级隔离(P12)
  - `hypothesis` 覆盖 P1/P8/P9（fast profile，max_examples=5）
  - _需求：1.1, 1.3, 1.7, 4.1, 4.4, 4.5, 7.1, 7.3, 8.3, 8.6, 8.7, 9.1, 9.2, 10.2, 10.4_ _属性：Property 1, 2, 5, 7, 8, 9, 10, 12, 13, 14, 15, 16_

- [x] 5. DisclosureEngine 注入
  - `_generate_text_with_llm`：开关开启时先调 `enricher.generate_note_text`，text 非空则用之并暂存 `_last_citations`，否则退回现有通用 LLM 路径；返回签名不变(`str | None`)
  - 修复历史 dead-import：`from ... import llm_client`（符号不存在，恒返 None）→ 模块级 `chat_completion`（返回 str）+ 本地 `_is_llm_error`（占位串 `[LLM.../⚠️...` 判降级），即便开关关闭也让通用 LLM 层恢复工作
  - `generate_notes` 优先级 1b：`_prior_notes_cache` 缺该 section 且开关开启 → 调 `retrieve_prior_year_note`，命中作为上年来源 + 记 Citation（保持 DB 优先，Property 3）
  - 批量单章 RAG 失败仅该章降级(try/except 隔离，Property 12)；开关关闭时不实例化/不调用 enricher（惰性 `_get_enricher`，Property 6）
  - _需求：1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 2.4, 6.4_

- [x] 6. DisclosureEngine 集成测试
  - `backend/tests/test_disclosure_note_rag_integration.py`：patch `NoteKnowledgeEnricher` 构造点 + `chat_completion`：上年优先级链 DB→知识库→LLM→模板(P3/P4)、关闭开关 `NoteKnowledgeEnricher` 未被构造零回归(P6)、批量单章降级隔离(P12)
  - _需求：2.1, 2.2, 2.3, 6.2, 6.4_ _属性：Property 3, 4, 6, 12_

- [x] 7. ai-fill / batch-ai-fill 端点 + 采纳流对接
  - `routers/disclosure_notes.py` 增 `POST /{project_id}/{year}/{note_section}/ai-fill`(body doc_filter/reference_only → resp text+citations(含 is_stale)+degraded+skipped_docs，不落库) + `POST /{project_id}/{year}/batch-ai-fill`(一键批量→逐章结果，不落库，Req10)
  - 无命中返回 `degraded:true`；权限跳过文档返回 `skipped_docs`
  - 采纳落库仅写 text_content 不碰 guidance_text（Req5.2）
  - 端点测试：不写库(P11)、degraded 提示、权限跳过、reference_only 不生成(P13)、batch 逐章结果
  - _需求：3.1, 3.4, 4.3, 4.5, 5.1, 5.2, 5.3, 10.1, 10.3_ _属性：Property 11, 13_

- [x] 8. 前端 NoteAiFillDialog
  - 新建 `components/disclosure/NoteAiFillDialog.vue`：模式切换(AI 生成/参照文档 Reference_Only)+参照范围多选(知识库文档/文件夹，可空)+触发 ai-fill+预览 Grounded_Draft+Citation 列表(document_name/folder_path 可点选，is_stale 标过期)+含金额提示"数字须与附注表格核对"+采纳走 `useDocAiChat.adoptContent`
  - 章节被 sectionLocks 锁定时"采纳"禁用(可预览不可写)
  - 无命中明确提示"未检索到可参照的知识库文档，已用通用生成"
  - _需求：3.1, 3.2, 3.4, 3.6, 4.1, 4.5, 5.1, 9.3_

- [x] 9. DisclosureEditor 入口 + vitest
  - `views/DisclosureEditor.vue` 当前章节工具栏加"AI 填充""参照文档填充"按钮 → 打开 NoteAiFillDialog；顶部工具栏加"一键 AI 预填充"→ batch-ai-fill 进度+逐章确认
  - vitest：Dialog 展示 Citation、无命中提示、reference_only 模式无生成、锁定禁用采纳、采纳调 adoptContent、未采纳 text_content 不变、批量进度渲染
  - _需求：3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.5, 10.5_ _属性：Property 11, 13_

- [x] 10. 全量测试门 + 契约守卫
  - 后端 disclosure + note_source + enricher 全套；前端 disclosure vitest；get_diagnostics 全清；Vite transform 改动文件全 200
  - 断言 Requirement 8 全部属性(P1-P16)有覆盖
  - _需求：8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_ _属性：Property 1-16_

- [ ] 11. Playwright 端到端实测（可选收尾）\* — 前置条件未满足：knowledge_index 表当前无任何已索引知识库文档（COUNT=0），RAG 检索恒空→无 Citation 可端到端预览，故该可选实测在当前环境无法有效执行；待有已索引文档的实例化项目时补做
  - 需知识库已索引文档的实例化项目：DisclosureEditor AI 填充 → 预览 Citation → 采纳 → 确认流 → 附注文字更新 → round-trip 落库
  - _需求：3.1, 3.2, 3.3, 5.1, 5.2_

## Notes

- **边界**：仅覆盖复盘维度 2（内容/文字层知识库+AI）。公式校验（维度 4）、`resolve_formula` 表内公式、报表主要项目注释表格↔文字联动（维度 3）、`_sub_table_columns` 覆盖率各自独立后续 spec，本 spec 不动。
- **不改**：`disclosure_notes` 表结构、模板生成骨架、底稿→附注同步、现有 AI 治理确认流。
- **复用**：`KnowledgeIndexService.semantic_search`（不新建检索）、`llm_client.chat_completion`、`wrap_ai_output_with_log`/`useDocAiChat.adoptContent`（不改治理链）。
- **铁律**：RAG 失败一律 fail-open；PBT 用 fast profile(max_examples=5)；context 传 LLM 前值转字符串；前端调 `/ai/generate-text` 类端点 context 为 dict[str,str] 避 422。
- **Playwright 环境坑**：DisclosureEditor 可能受并发会话 SSE 跳转影响，须 addInitScript 中和 EventSource + 单次 run 内完成操作链。
