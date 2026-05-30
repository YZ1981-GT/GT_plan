# 附注模块全栈改进 — 任务清单

> **版本**：v1.1（2026-05-26 修订：DSL 函数清单与代码事实对齐 + is_stale 字段已存在 + useNoteStale 标新建）
> **总任务数**：47（前置 3 + Sprint 0×4 + Sprint 1×8 + Sprint 1.5×6 + Sprint 2×9 + Sprint 3×8 + Sprint 4×6 + 收尾 3）
> **总工时**：18.5-19.5 人天（含前置 1d）
> **来源**：design.md 6 Sprint 拆解 + requirements.md 59 验收标准

---

## 前置（1 人天，外部依赖）

- [ ] **P-1** 老审计师列语义 review：50+ 变动表 binding 草稿（0.5d）
  - 依据 design.md D2 schema 写 `note_template_bindings.json` 草稿
  - 覆盖固定资产 / 无形资产 / 长期股权投资 / 递延所得税资产 / 在建工程 / 使用权资产 等
  - 产出：50+ 章节的列语义 ID + source + account_codes 标注

- [ ] **P-2** 致同 PDF 视觉基准库（0.5d）
  - 老审计师提供 5-10 张真实致同附注 PDF 截图
  - 标注：字体 / 字号 / 缩进 / 边框磅数 / 页边距
  - 存放：`tests/fixtures/note_visual_baseline/*.png` + `baseline.yaml`

- [ ] **P-3** `.md` 公式预解析（0.5d，并入 Sprint 1.5）
  - `scripts/parse_validation_preset_md.py` 解析 `附注模版/{soe,listed}版校验公式预设.md`
  - 输出：`backend/data/note_validation_rules.json`（按"科目-表格-编号"索引）+ `note_wide_table_preset.json`（列角色 + 符号）
  - 验证：上市版宽表 ~10 科目 + 国企版 ~12 科目命中率 100%

---

## Sprint 0：模板治理 + Word P0 修复 + 数据迁移（1 人天）

- [x] **0.1** `scripts/cleanup_note_templates.py` 一次性治理脚本
  - 删除 headers 中的空字符串占位（约 800+ 处）
  - 给每个 row 打 `row_type`（按 label vs headers[0] 启发式 + 人工 review）
  - 输出 diff 报告 `cleanup_report.txt`
  - 验收：CI 单测断言模板 JSON 中 row 字段含 row_type

- [x] **0.2** `scripts/migrate_disclosure_notes_to_v2.py` 数据迁移脚本（幂等）
  - 历史 DisclosureNote.table_data.row 升级为含 `row_type + _cell_meta`
  - 跳过已升级行（幂等）
  - 验收：3 个真实项目跑迁移后前端零回归

- [x] **0.3** Word 多表渲染 P0 bug 修复
  - `note_word_exporter.py` 优先取 `note.table_data._tables` 数组
  - 多表章节加 H3 表名标题
  - 空 header 列裁剪
  - CI 卡点：grep `_tables` 必须出现在 `note_word_exporter.py`

- [x] **0.4** Sprint 0 验收
  - 固定资产/应收票据等多表章节导出 5-12 张表全部出现
  - vue-tsc 0 错误，pytest 全绿
  - 提交 commit「Sprint 0: 模板治理 + Word P0 修复」

---

## Sprint 1：数据绑定层 + 列语义识别 + 引擎兼容层（5-6 人天）

- [x] **1.1** 新建 `backend/data/note_template_bindings.json`
  - 整合前置 P-1 草稿（50+ 变动表）
  - 自动生成 90 张 3 列标准表绑定（基于 wp_account_mapping.json 88 条）
  - 总覆盖 ≥ 140/173 章节（≥ 80%）
  - 单测：每条 binding 含 source / field / mode / account_codes 必填项

- [x] **1.2** `backend/app/services/note_column_semantics.py` 新建列语义识别引擎
  - 实现 `NoteColumnSemantics.identify(header_text)` 模糊匹配 20 个标准语义
  - 单测覆盖：`test_note_column_semantics.py` ≥ 20 用例

- [x] **1.3** 引擎改造 `disclosure_engine._build_table_data` 加 binding 分支
  - 优先读 binding，无绑定降级到 label 字符串匹配（兼容层）
  - 新增 `_build_with_binding` 方法
  - 单测：`test_disclosure_engine_v2.py` 至少 30 用例

- [x] **1.4** 实现 7 种 source 数据源解析器
  - `_resolve_from_trial_balance(binding, project_id, year)`
  - `_resolve_from_ledger_sum(binding, project_id, year)` + period_filter 三模式
  - `_resolve_from_aux_balance(binding, project_id, year)`
  - `_resolve_aux_ledger_aging(binding, project_id, year)`（D4 新建）
  - `_resolve_formula(binding, table_data)` 表内引用
  - `_resolve_prior_year_note(binding, project_id, year)` 复用 prior_notes_cache
  - `_resolve_manual(binding)` 直接读 manual_value
  - 单测：每个 source 至少 3 用例

- [x] **1.5** sidecar 字段持久化（D1）
  - `DisclosureNote.table_data.row` 新增 `row_type` + `_cell_meta`
  - 引擎重生成规则三态：auto 覆盖 / manual 保留 + manual_value 备份 / locked 跳过
  - 单测：PBT `test_note_persistence_property.py` 4 用例（auto/manual/locked round-trip）

- [x] **1.6** 数据迁移脚本验证
  - 跑 0.2 迁移脚本到本地 PG
  - 抽查 20 个章节确认 round-trip 不丢字段
  - 前端 DisclosureEditor.vue 老代码零修改测试

- [ ] **1.7** R1 验收 UAT（3 个真实项目）
  - 陕西华氏 SOE / 安徽骨科 SOE / 1 个 Listed 上市样本
  - 53 个变动表"本期增加/减少"列自动取数命中率 ≥ 95%
  - 整体表格数字准确率 ≥ 95%
  - 老审计师 review 20 章节通过
  

- [x] **1.8** Sprint 1 验收
  - CI 卡点：模板 JSON 中 `account_codes` 引用 = 0；`row._cell_modes` 三态断言通过
  - vue-tsc / pytest 全绿
  - 提交 commit「Sprint 1: 数据绑定层 + 列语义识别 + 引擎兼容层」

---

## Sprint 1.5：公式 DSL 沉淀 + 三式联动整合（2 人天）

- [x] **1.5.1** `docs/NOTE_FORMULA_DSL.md` 完整 DSL 语法参考
  - 已有 5 函数文档化：`TB / WP / REPORT / cell / SUM`（不改实现）
  - 🆕 本 spec 新建 2 函数：`PRIOR / AGING`
  - 每函数含正常 / 缺数据 / 边界 case
  - `note_formula_generator.py`（入口 `generate_formulas_for_table`）头部 `__doc__` 引用

- [x] **1.5.2** `=AGING(account, bucket)` + `=PRIOR(account, period)` 函数实现（D4 新建）
  - **=AGING**：从 TbAuxLedger 反推账龄分桶（5 桶：1 年以内 / 1-2 / 2-3 / 3-5 / 5 年以上）；客户未提供辅助序时账时返回 None（章节标 not_applicable）
  - **=PRIOR**：上年附注期末值取数，复用 `disclosure_engine._preload_data_for_notes.prior_notes_cache`
  - 单测：`test_note_formula_dsl.py` 至少 6 用例（=AGING × 3 + =PRIOR × 3）

- [x] **1.5.3** ConsolNoteTab 重复公式 dialog 收敛
  - 删除 `ConsolNoteTab.vue:424-493` 内置 dialog
  - `FormulaManagerDialog` 加 `scope: 'note' | 'consol_note' | 'report'` prop
  - CI 卡点：grep `noteFormulaRules.value` 在 ConsolNoteTab.vue 应消失

- [x] **1.5.4** 单元格级公式 `_formulas` 数组（D4）
  - `note.table_data._formulas = [{row, col, expr, binding_id, evaluated_at}]`
  - 不污染 row 结构，独立顶层数组

- [x] **1.5.5** ADR-007 撰写 `docs/adr/ADR-007-note-triple-format-source-of-truth.md`
  - DisclosureNote.table_data 唯一真源
  - structure.json / xlsx / HTML 三式职责
  - `triple_format_adapter.update_note_from_structure` 单入口规约

- [x] **1.5.6** Sprint 1.5 验收
  - 5 函数 + DSL 文档完整
  - vue-tsc / pytest 全绿
  - 提交 commit「Sprint 1.5: 公式 DSL 沉淀 + 三式联动 ADR」

---

## Sprint 2：Word 真致同样式 + CellTrace + 联动事件（3.5 人天）

- [x] **2.1** `scripts/build_note_export_template.py` 一次性生成 docx 模板
  - D7 完整结构：6 段落样式 + 1 字符样式 + 1 表格样式 + 默认行高 + 页面 + 页眉页脚
  - 输出 `backend/data/note_export_template.docx`
  - 单测断言每个样式的字体名/字号/缩进/边框值

- [x] **2.2** `NoteWordExporter` 重写（D7 关键 OOXML）
  - 加载 `note_export_template.docx` 而非 `Document()`
  - `apply_gt_dual_font(run)` 双字体 rPr 注入
  - `apply_gt_three_line(table)` 三线表
  - `fill_multi_header(table, header_rows, total_cols)` rowspan/colspan grid 二阶段填充
  - `apply_gt_row_height(row, cm=0.7)` 固定行高 + 关闭标题行重复
  - `fmt_amount_gt(val)` 空值/零值留白
  - `add_landscape_section(doc)` 章节级横向

- [x] **2.3** CellTrace 后端端点（R3）
  - `GET /api/disclosure-notes/{note_id}/cells/{row_idx}/{col_idx}/trace`
  - `disclosure_engine.trace_cell` 实现：binding 反查 + 公式展开 + 证据数据采样（≤ 100 行）
  - 单测：`test_note_cell_trace.py` ≥ 5 用例

- [x] **2.4** CellTraceDialog.vue 前端组件（R3）
  - 三栏布局：左 binding 元数据，中 公式展开，右 命中数据行
  - 点击数据行 emit `penetrate-to-tb` → 跳 TrialBalance 页面
  - DisclosureEditor.vue 右键菜单"溯源"打开

- [x] **2.5** EventBus 订阅 3 类**新增**事件（R2.1）
  - 现状：`event_handlers._mark_downstream_stale_on_rollback` 已订阅 `LEDGER_DATASET_ROLLED_BACK`，本 spec **不动**
  - 本 spec 新增 3 个 handler：
    - `disclosure_engine.on_event_ledger_activated`
    - `disclosure_engine.on_event_workpaper_reviewed`
    - `disclosure_engine.on_event_adjustment_approved`
  - 集成测试：`test_note_stale_event_chain.py` ≥ 8 用例（3 新事件 × 2 路径 + ROLLED_BACK 兼容性 × 2）

- [x] **2.6** 视觉回归测试 `tests/test_note_export_visual.py`
  - 11 项断言：字体 / 字号 / 章节缩进 / 段落间距 / 三线表磅数 / 行高 / 留白 / 标题行不重复 / 页眉 / 页边距
  - 每个断言用 OOXML 解析（不依赖人眼）

- [x] **2.7** 多表 + 多层表头集成测试
  - 应收票据 12 张表全部出现
  - 固定资产变动表"本期增加→购置/在建转入"二级表头正确合并

- [x] **2.8** 文档 ADR-008 + ADR-009
  - ADR-008: Note cell mode persistence (auto/manual/locked)
  - ADR-009: GT Word template style namespace (GTNote*)

- [x] **2.9** Sprint 2 验收
  - 11 项视觉断言全绿
  - CellTraceDialog 端到端 Playwright 测试通过
  - CI 卡点：docx 样式名 grep `GTNote*` 前缀
  - vue-tsc / pytest 全绿
  - 提交 commit「Sprint 2: Word 真致同样式 + CellTrace + 联动事件」

---

## Sprint 3：自定义编辑 + 联动 UI + 智能裁剪（3.5 人天）

- [x] **3.1** StructureEditor 新增能力（R4.1）
  - DisclosureEditor 工具栏"➕ 新增章节"按钮 + 对话框
  - StructureEditor 内"➕ 加表"/"➕ 加列" + 列语义下拉
  - 新增列绑定草稿自动生成（R1.1 列语义识别引擎）
  - 单测：`StructureEditor.add-section.spec.ts` ≥ 5 用例

- [x] **3.2** 自定义模板存储（D8）
  - `backend/storage/projects/{pid}/templates/custom_note_template.json` schema
  - `POST /api/projects/{pid}/note-template/save` 端点
  - 历史版本 snapshot 存于 `v{N}.json`（不可变）
  - 单测：版本 round-trip + 回滚

- [x] **3.3** 模板 union 算法（D3）
  - `disclosure_engine._load_templates` 调 `merge_templates(baseline, custom)`
  - 冲突解决：custom > baseline，按 sort_order 排序
  - 单测：`test_disclosure_engine_v2.py` 加 5 用例（覆盖 / 新增 / 排序）

- [x] **3.4** 自定义模板版本回滚 UI
  - `POST /api/projects/{pid}/note-template/restore?version=N`
  - StructureEditor 工具栏"📜 历史版本"按钮 + 列表 dialog
  - 二次确认 + 回滚后产生新版本（不覆盖历史）

- [x] **3.5** 删除自定义条目 + 回收站（R4.1）
  - 右键"删除此章节/表格/列"二次确认
  - 进 30 天保留期回收站
  - 复用现有 `RecycleBin.vue` 组件

- [x] **3.6** 联动 UI 实装（R2.1 前端）
  - 章节列表红点 + tooltip "上游已变更，建议重算"
  - 右键菜单"重算此章节" → 调 `update_note_values`
  - `POST /disclosure-notes/{id}/dismiss-stale` 一键忽略
  - 🆕 新建 composable `audit-platform/frontend/src/composables/useNoteStale.ts`（grep 全仓 0 命中，本 spec 新建）订阅 EventBus

- [x] **3.7** NoteTrimService.auto_trim 简化版（v2 §5.3）
  - 现有方法 5 个：`get_sections/save_trim/get_trim_scheme/resolve_template_type/_init_from_template`
  - 🆕 本 spec 新增 `auto_trim(project_id, year, template_type)` 方法
  - 检查 binding.skip_if_all_zero 列出科目，TrialBalance 全为 0 → 调现有 `save_trim` 标 not_applicable
  - 单测：`test_note_trim_service_auto.py` 覆盖率 ≥ 80%

- [x] **3.8** Sprint 3 验收
  - 5 个真实流程 Playwright 端到端测试（新增章节 / 改公式 / 红点重算 / 历史回滚 / auto_trim）
  - vue-tsc / pytest 全绿
  - CI 卡点：`auto_trim` 单测覆盖率 ≥ 80%
  - 提交 commit「Sprint 3: 自定义编辑 + 联动 UI + 智能裁剪」

---

## Sprint 4：check_presets 接入 + linkage 增强 + NoteFormatConfig（2.5 人天）

- [x] **4.1** check_presets 接入 NoteValidationEngine（v2 §5.4）
  - `PRESET_TO_RULE` 字典覆盖 11 个枚举：余额 / 宽表 / 纵向 / 交叉 / 跨科目 / 其中项 / 二级明细 / 完整性 / 账龄衔接 / LLM审核 / 描述
  - 引擎从 `note.table_data._validation_rules` 触发
  - 单测：每个规则至少 2 用例

- [x] **4.2** linkage_graph_builder 增强（R2.2）
  - 从 `note.referenced_accounts` 自动生成 NOTE→TB→WP 双向边
  - 单测断言相对增量（mock 20 章节 → ≥40 节点新增），避免硬编码 ≥200（13 单测）

- [x] **4.3** 报表 ReportView "附注引用我"侧栏
  - rowCode → 反查所有引用此报表项的 note_section
  - 双向溯源跳转

- [x] **4.4** `note_format_config.py` 抽出（v2 §5.4）
  - `@dataclass(frozen=True) NoteFormatConfig` 21 项排版参数
  - `GET /api/disclosure-notes/format-config` 端点
  - 前端 CSS 变量应用

- [x] **4.5** ADR-010 撰写 `docs/adr/ADR-010-note-custom-template-versioning.md`

- [x] **4.6** Sprint 4 验收
  - CI 卡点：`PRESET_TO_RULE` 必须覆盖 `check_presets` 全部 11 个枚举
  - linkage NOTE 节点数 ≥ 200
  - vue-tsc / pytest 全绿
  - 提交 commit「Sprint 4: check_presets + linkage 增强 + NoteFormatConfig」

---

## 收尾（最终验收）

- [x] **F-1** 全量 UAT（2 真实项目通过 ✅，2026-05-27）
  - **首汽租车_2025（df5b8403）**: tb_balance 1654 → trial_balance 166 → 173 章节 → 138.8KB docx（service 直调）
  - **重庆和平药房_2025（2aa00f57）**: tb_balance 774 → 40 章节（auto_trim 起作用）→ 38.2KB docx（前端 UI 全自动化 Playwright）
  - 验收报告 `docs/uat/disclosure-note-uat-report-2026-05-27.md` + 2 docx + UI 截图

- [ ] **F-2** memory.md 状态刷新 + dev-history 沉淀
  - "真正待办"中"附注模块改进 v2.0 实施"项移到"全部已完成 spec ✅"
  - dev-history.md 追加详细技术决策（D1-D8）+ 性能数据 + UAT 结论
  - architecture.md 追加附注三层架构图（模板/绑定/引擎）

- [ ] **F-3** 文档收口
  - `docs/DISCLOSURE_NOTE_IMPROVEMENT_PROPOSAL.md` 顶部加 "已实施 ✅ commit hash" 标记
  - `.kiro/specs/INDEX.md` 追加 disclosure-note-full-revamp 条目（47/47 tasks ✅）
  - 最终 commit「F: 附注模块全栈改进 v2.0 实施完成（47/47 tasks）」

---

## 任务依赖图

```
P-1 (审计师) ──┐
P-2 (基准) ───┼─→ Sprint 0 ─→ Sprint 1 ─→ Sprint 1.5 ─→ Sprint 2 ─→ Sprint 3 ─→ Sprint 4 ─→ F
P-3 (.md预解析) ┘
                                    ↑
                              ADR-007/008/009 落地
```

**关键路径**：P-1/P-2/P-3 → 0 → 1 → 1.5 → 2 → 3 → 4 → F

**并行可能**：
- Sprint 1.5 与 Sprint 2 部分可并行（DSL 文档 vs Word 模板生成不冲突）
- Sprint 3 与 Sprint 4 部分可并行（前端自定义编辑 vs 后端 linkage 增强）

---

## 进度追踪

| Sprint | 任务数 | 工时 | 完成态 | 关键 commit |
|--------|-------:|-----:|-------|-------------|
| 前置 | 3 | 1d | ⏳ 待启动 | — |
| Sprint 0 | 4 | 1d | ⏳ 待启动 | — |
| Sprint 1 | 8 | 5-6d | ⏳ 待启动 | — |
| Sprint 1.5 | 6 | 2d | ⏳ 待启动 | — |
| Sprint 2 | 9 | 3.5d | ⏳ 待启动 | — |
| Sprint 3 | 8 | 3.5d | ⏳ 待启动 | — |
| Sprint 4 | 6 | 2.5d | ⏳ 待启动 | — |
| 收尾 | 3 | 0.5d | ⏳ 待启动 | — |
| **合计** | **47** | **18.5-19.5d** | **0/47** | — |

完成态图示：⏳ 待启动 / 🚧 进行中 / ✅ 完成

---

## 风险预警卡点

每个 Sprint 结束前必须确认：

| 卡点 | 检查方式 |
|------|---------|
| 前置卡点 | 50+ 变动表 binding 草稿质量审计师签字 |
| Sprint 0 卡点 | grep `_tables` in `note_word_exporter.py` |
| Sprint 1 卡点 | 模板 JSON `account_codes` 引用 = 0 |
| Sprint 1.5 卡点 | grep `noteFormulaRules.value` in `ConsolNoteTab.vue` 应为 0 |
| Sprint 2 卡点 | 11 项视觉断言全绿 + docx 样式 grep `GTNote*` |
| Sprint 3 卡点 | `auto_trim` 单测覆盖率 ≥ 80% |
| Sprint 4 卡点 | `PRESET_TO_RULE` 覆盖 11 个枚举 + NOTE 节点 ≥ 200 |
| 收尾卡点 | 3 真实项目 UAT 数字 95% + 视觉 11 项全绿 |

任一卡点失败 → 不进入下一 Sprint，必须复盘修复。

