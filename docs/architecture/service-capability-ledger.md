# Service 同族能力注册表

> 本文档记录后端 service 的同族分组、能力边界和复用/替代关系。
> 新增 service 的 PR 必须说明复用/替代关系。

## 更新规则

1. 新增 service → 必须在此文档标注所属族和职责
2. 修改 service 公开接口 → 更新能力描述
3. 废弃 service → 标注 `deprecated` 和替代方案
4. PR 必须说明与同族 service 的复用/替代关系

---

## 同族分类

### 🧮 公式引擎族（Formula）

> **治理状态**：已有 ADR-FORMULA-001 决策统一内核，迁移进行中。
> 详见 `docs/adr/ADR-FORMULA-001-single-kernel-three-layer-architecture.md`

| Service | 路径 | 职责 | 语法域 | 调用方 | 状态 |
|---|---|---|---|---|---|
| `formula_engine.py` | `services/formula_engine.py` | 报表 DSL 求值内核（TB/SUM_TB/ROW/PREV） | 报表 DSL | formula router, report_config, event_handlers, prefill | ✅ 统一内核 |
| `report_engine.py` | `services/report_engine.py` | 报表生成编排 + 报表公式求值（L2 层） | 报表 DSL | reports router, consol, chain_orchestrator | ✅ 活跃（L2 编排） |
| `formula_parse_utils.py` | `services/formula_parse_utils.py` | 递归下降解析器（tokenize + AST） | 报表 DSL | report_config router | ⚠️ 待收口到内核 |
| `cell_formula_evaluator.py` | `services/cell_formula_evaluator.py` | 底稿 Cell 公式执行（Excel 语法 =A1+B2） | Excel 语法 | excel_html, import_templates | ✅ 独立语法域 |
| `note_formula_engine.py` | `services/note_formula_engine.py` | 附注勾稽校验（8 类 Validator） | 校验规则 | note_templates router | ✅ 排除出收敛（非求值器） |
| `note_formula_generator.py` | `services/note_formula_generator.py` | 附注公式生成 | — | 附注模板 | ✅ 活跃 |
| `formula_reverse_index.py` | `services/formula_reverse_index.py` | 公式反向索引（依赖图） | — | 公式更新事件 | ✅ 活跃 |
| `wp_formula_service.py` | `services/wp_formula_service.py` | 自定义底稿公式 CRUD | 报表 DSL | wp_formula router | ✅ 活跃 |
| `wp_formula_eval_service.py` | `services/wp_formula_eval_service.py` | 底稿公式求值 | 报表 DSL | wp_formula router | ✅ 活跃 |
| `wp_formula_dependency.py` | `services/wp_formula_dependency.py` | 底稿公式依赖追踪 | — | wp_formula_service | ✅ 活跃 |
| `wp_formula_linkage_service.py` | `services/wp_formula_linkage_service.py` | 底稿公式联动 | — | wp_formula | ✅ 活跃 |
| `report_formula_service.py` | `services/report_formula_service.py` | 报表公式填充/seed | — | report 初始化 | ✅ 活跃（非求值器） |

### 📚 知识库族（Knowledge）

| Service | 路径 | 职责 | 调用方 | 状态 |
|---|---|---|---|---|
| `knowledge_index_service.py` | `services/knowledge_index_service.py` | 知识库索引构建 + 语义搜索 | reference_doc, doc_ai_chat | ✅ 主服务 |
| `knowledge_folder_service.py` | `services/knowledge_folder_service.py` | 知识库文件夹管理 | knowledge router | ✅ 活跃 |
| `reference_doc_service.py` | `services/reference_doc_service.py` | 参考文档管理 + RAG 上下文构建 | doc_ai_chat | ✅ 活跃 |
| `doc_ai_context_builder.py` | `services/doc_ai_context_builder.py` | 文档 AI 上下文构建 | doc_ai_chat | ✅ 活跃 |
| `doc_chat_persistence.py` | `services/doc_chat_persistence.py` | 文档对话持久化（DB） | doc_ai_chat | ✅ 活跃 |
| `vector_store.py` | `services/vector_store.py` | pgvector 向量存储 | knowledge_index_service | ✅ 活跃 |

### 🔗 Linkage/联动族

| Service | 路径 | 职责 | 调用方 | 状态 |
|---|---|---|---|---|
| `linkage_service.py` | `services/linkage_service.py` | 联动关系管理 | linkage router | ✅ 活跃 |
| `linkage_contract_builder.py` | `services/linkage_contract_builder.py` | LinkageContract 构建 | 穿透入口 | ✅ 活跃（平台原子） |
| `linkage_graph_builder.py` | `services/linkage_graph_builder.py` | 联动图构建（可视化） | panorama | ✅ 活跃 |
| `linkage_label_resolver.py` | `services/linkage_label_resolver.py` | 联动标签解析 | linkage UI | ✅ 活跃 |
| `linkage_panorama_aggregator.py` | `services/linkage_panorama_aggregator.py` | 全景联动聚合 | panorama router | ✅ 活跃 |
| `unified_lineage_service.py` | `services/unified_lineage_service.py` | 统一血缘追踪 | lineage panel | ✅ 活跃 |
| `cross_ref_service.py` | `services/cross_ref_service.py` | 交叉引用 | report/note | ✅ 活跃 |

### 📊 Stale/过期族

| Service | 路径 | 职责 | 调用方 | 状态 |
|---|---|---|---|---|
| `stale_propagation_engine.py` | `services/stale_propagation_engine.py` | stale 传播引擎 | event_handlers | ✅ 核心 |
| `stale_incremental_propagation.py` | `services/stale_incremental_propagation.py` | stale 增量传播 | stale_propagation | ✅ 活跃 |
| `stale_summary_aggregate.py` | `services/stale_summary_aggregate.py` | stale 汇总聚合 | dashboard | ✅ 活跃 |
| `stale_degraded_logger.py` | `services/stale_degraded_logger.py` | stale 降级日志 | stale_propagation | ✅ 活跃 |
| `note_stale_service.py` | `services/note_stale_service.py` | 附注 stale 特化 | note 编辑 | ✅ 活跃 |
| `report_stale_service.py` | `services/report_stale_service.py` | 报表 stale 特化 | report 编辑 | ✅ 活跃 |
| `consol_trial_stale_handler.py` | `services/consol_trial_stale_handler.py` | 合并试算 stale | consol | ✅ 活跃 |
| `consol_note_stale_handler.py` | `services/consol_note_stale_handler.py` | 合并附注 stale | consol | ✅ 活跃 |

### 📤 导出族（Export）

| Service | 路径 | 职责 | 调用方 | 状态 |
|---|---|---|---|---|
| `export_job_service.py` | `services/export_job_service.py` | 导出任务管理 | export router | ✅ 活跃 |
| `export_task_service.py` | `services/export_task_service.py` | 导出任务执行 | export_job | ✅ 活跃 |
| `export_package_service.py` | `services/export_package_service.py` | 打包导出 | archive | ✅ 活跃 |
| `export_progress_service.py` | `services/export_progress_service.py` | 导出进度跟踪 | export_job | ✅ 活跃 |
| `export_integrity_service.py` | `services/export_integrity_service.py` | 导出完整性校验 | export | ✅ 活跃 |
| `export_mask_service.py` | `services/export_mask_service.py` | 导出脱敏 | export | ✅ 活跃 |
| `report_export_engine.py` | `services/report_export_engine.py` | 报表导出引擎 | report router | ✅ 活跃 |
| `report_excel_exporter.py` | `services/report_excel_exporter.py` | 报表 Excel 导出 | report_export | ✅ 活跃 |
| `note_offline_export_service.py` | `services/note_offline_export_service.py` | 附注离线导出 | note export | ✅ 活跃 |
| `wp_offline_export_service.py` | `services/wp_offline_export_service.py` | 底稿离线导出 | wp export | ✅ 活跃 |
| `wp_xlsx_export_service.py` | `services/wp_xlsx_export_service.py` | 底稿 xlsx 导出 | wp download | ✅ 活跃 |
| `pdf_export_engine.py` | `services/pdf_export_engine.py` | PDF 导出引擎 | archive, report | ✅ 活跃 |

### 📥 导入族（Import）

| Service | 路径 | 职责 | 调用方 | 状态 |
|---|---|---|---|---|
| `import_service.py` | `services/import_service.py` | 通用导入入口 | import router | ✅ 活跃 |
| `import_job_service.py` | `services/import_job_service.py` | 导入任务管理 | import | ✅ 活跃 |
| `import_job_runner.py` | `services/import_job_runner.py` | 导入任务执行 | import_job | ✅ 活跃 |
| `import_validation_service.py` | `services/import_validation_service.py` | 导入数据校验 | import_job | ✅ 活跃 |
| `import_template_service.py` | `services/import_template_service.py` | 导入模板管理 | import_templates router | ✅ 活跃 |
| `import_intelligence.py` | `services/import_intelligence.py` | 智能导入（列映射推断） | import | ✅ 活跃 |
| `smart_import_engine.py` | `services/smart_import_engine.py` | 智能导入引擎 | import | ✅ 活跃 |
| `import_queue_service.py` | `services/import_queue_service.py` | 导入队列 | import | ✅ 活跃 |
| `import_event_outbox_service.py` | `services/import_event_outbox_service.py` | 导入事件发件箱 | import | ✅ 活跃 |
| `note_offline_import_service.py` | `services/note_offline_import_service.py` | 附注离线导入 | note import | ✅ 活跃 |
| `wp_offline_import_service.py` | `services/wp_offline_import_service.py` | 底稿离线导入 | wp import | ✅ 活跃 |

### 🏢 合并族（Consolidation）

| Service | 路径 | 职责 | 调用方 | 状态 |
|---|---|---|---|---|
| `consol_aggregation_service.py` | `services/consol_aggregation_service.py` | 合并汇总 | consol router | ✅ 活跃 |
| `consol_scope_service.py` | `services/consol_scope_service.py` | 合并范围管理 | consol router | ✅ 活跃 |
| `consol_tree_service.py` | `services/consol_tree_service.py` | 合并架构树 | consol router | ✅ 活跃 |
| `consol_trial_service.py` | `services/consol_trial_service.py` | 合并试算 | consol router | ✅ 活跃 |
| `consol_report_service.py` | `services/consol_report_service.py` | 合并报表 | consol router | ✅ 活跃 |
| `consol_disclosure_service.py` | `services/consol_disclosure_service.py` | 合并附注（**1736 行，待拆分**） | consol router | ⚠️ 待治理 |
| `consol_enhanced_service.py` | `services/consol_enhanced_service.py` | 合并增强服务 | consol | ✅ 活跃 |
| `consol_elimination_rules.py` | `services/consol_elimination_rules.py` | 抵销规则 | consol | ✅ 活跃 |
| `consol_auto_elimination_service.py` | `services/consol_auto_elimination_service.py` | 自动抵销 | consol | ✅ 活跃 |
| `consol_snapshot_service.py` | `services/consol_snapshot_service.py` | 合并快照 | consol | ✅ 活跃 |
| `consol_reconciliation_service.py` | `services/consol_reconciliation_service.py` | 合并核对 | consol | ✅ 活跃 |
| `consol_pivot_service.py` | `services/consol_pivot_service.py` | 合并透视 | consol | ✅ 活跃 |
| `consol_drilldown_service.py` | `services/consol_drilldown_service.py` | 合并穿透 | consol | ✅ 活跃 |
| `consol_cascade_refresh_service.py` | `services/consol_cascade_refresh_service.py` | 合并级联刷新 | consol | ✅ 活跃 |
| `consol_worksheet_engine.py` | `services/consol_worksheet_engine.py` | 合并工作底稿引擎 | consol | ✅ 活跃 |

### 🤖 AI/LLM 族

| Service | 路径 | 职责 | 调用方 | 状态 |
|---|---|---|---|---|
| `ai_service.py` | `services/ai_service.py` | AI 服务主入口（OCR/knowledge/contract/wp_fill） | 多处 | ✅ 活跃 |
| `llm_client.py` | `services/llm_client.py` | LLM 客户端（httpx + 熔断器） | wp_llm_prompts, role_ai, pm | ✅ 活跃 |
| `structured_llm_service.py` | `services/structured_llm_service.py` | 结构化 LLM 输出（instructor） | AI 相关 | ✅ 活跃 |
| `unified_ai_service.py` | `services/unified_ai_service.py` | 统一 AI 服务 facade | 顶层调用 | ✅ 活跃 |
| `ai_content_gate.py` | `services/ai_content_gate.py` | AI 内容确认门禁 | AI 输出写入前 | ✅ 活跃（平台原子） |
| `ai_content_log_service.py` | `services/ai_content_log_service.py` | AI 内容日志 | ai_content_gate | ✅ 活跃 |
| `ai_contribution_watermark.py` | `services/ai_contribution_watermark.py` | AI 贡献水印 | AI 输出 | ✅ 活跃 |
| `ai_plugin_service.py` | `services/ai_plugin_service.py` | AI 插件管理 | ai router | ✅ 活跃 |
| `note_ai_assistant_service.py` | `services/note_ai_assistant_service.py` | 附注 AI 助手 | note_ai router | ✅ 活跃 |
| `wp_ai_service.py` | `services/wp_ai_service.py` | 底稿 AI 服务 | wp AI 相关 | ✅ 活跃 |
| `wp_chat_service.py` | `services/wp_chat_service.py` | 底稿对话 | wp_chat router | ✅ 活跃 |
| `ocr_service_v2.py` | `services/ocr_service_v2.py` | OCR 服务 v2 | 文档识别 | ✅ 活跃 |
| `unified_ocr_service.py` | `services/unified_ocr_service.py` | 统一 OCR 入口 | wp_ocr | ✅ 活跃 |

### 📝 附注族（Note/Disclosure）

| Service | 路径 | 职责 | 调用方 | 状态 |
|---|---|---|---|---|
| `disclosure_engine.py` | `services/disclosure_engine.py` | 附注引擎（1601 行） | disclosure router | ✅ 活跃 |
| `note_template_service.py` | `services/note_template_service.py` | 附注模板管理 | note_templates router | ✅ 活跃 |
| `note_fill_engine.py` | `services/note_fill_engine.py` | 附注填充引擎 | disclosure | ✅ 活跃 |
| `note_validation_engine.py` | `services/note_validation_engine.py` | 附注校验引擎（740 行） | disclosure | ✅ 活跃 |
| `note_stale_service.py` | `services/note_stale_service.py` | 附注 stale | stale 族 | ✅ 活跃 |
| `note_auto_pull_service.py` | `services/note_auto_pull_service.py` | 附注自动拉取 | disclosure | ✅ 活跃 |
| `note_cross_reference_service.py` | `services/note_cross_reference_service.py` | 附注交叉引用 | disclosure | ✅ 活跃 |
| `note_word_exporter.py` | `services/note_word_exporter.py` | 附注 Word 导出 | note export | ✅ 活跃 |

### 📋 底稿族（Workpaper）

> 底稿族服务数量最多（50+），以 `wp_` 前缀标识。核心子族：

| 子族 | 代表 Service | 职责 |
|---|---|---|
| 渲染 | `wp_render_schema_service`, `wp_program_extract` | 底稿渲染配置 |
| 数据 | `wp_parsed_data_service`, `wp_data_rules` | 底稿数据解析 |
| AI | `wp_ai_service`, `wp_chat_service`, `wp_auto_fill_service` | 底稿 AI 辅助 |
| 审阅 | `wp_review_service`, `wp_review_checklist_service` | 底稿复核 |
| 导入导出 | `wp_offline_export_service`, `wp_offline_import_service` | 底稿离线操作 |
| 模板 | `wp_template_init_service`, `wp_template_registry` | 底稿模板管理 |

---

## PR 规范

新增 service 的 PR **必须**说明：

1. **所属族**：属于哪个同族分组
2. **复用关系**：是否复用了同族已有 service 的能力
3. **替代关系**：是否替代（deprecate）某个已有 service
4. **新增原因**：如果同族已有类似 service，为何不扩展而是新建

**PR checklist 检查项**（已集成到 `.github/pull_request_template.md`）：
- [ ] 新增 service 是否已在 `docs/architecture/service-capability-ledger.md` 注册？
- [ ] 是否说明了与同族 service 的复用/替代关系？
- [ ] 如果是新族，是否有足够理由不归入现有族？
