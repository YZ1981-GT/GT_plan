# Implementation Plan

## Overview

按 M0-M3 分 6 波实现附注"报表↔附注金额/公式联动"三处断裂修复。原则：复用既有公式内核（不新造求值器）、linkage 单一真源、fail-open + 灰度开关（默认关零回归）、Skip_On_Missing。禁止自己写业务代码交由子代理；子代理遇错自定位根因修主代码重跑，不放宽断言/跳用例。

依赖上游：`disclosure-note-validation-completion`（已交付 11 executor + ValidationContext 装配 report/tb/prior）。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1", "1.2", "1.3"], "depends_on": [] },
    { "wave": 1, "tasks": ["2.1", "2.2", "2.3", "2.4"], "depends_on": ["1.1", "1.2", "1.3"] },
    { "wave": 2, "tasks": ["3.1", "3.2", "3.3"], "depends_on": ["2.1", "2.2", "2.3", "2.4"] },
    { "wave": 3, "tasks": ["4.1", "4.2", "4.3", "4.4"], "depends_on": ["3.1", "3.2", "3.3"] },
    { "wave": 4, "tasks": ["5.1", "5.2", "5.3", "5.4", "5.5"], "depends_on": ["1.1", "1.2", "1.3"] },
    { "wave": 5, "tasks": ["6.1", "6.2", "6.3", "6.4"], "depends_on": ["3.1", "3.2", "3.3", "4.1", "4.2", "4.3", "4.4", "5.1", "5.2", "5.3", "5.4", "5.5"] }
  ]
}
```

## Tasks

- [x] 1. Wave 0：安全网 + 脚手架
  - [x] 1.1 新增 `DISCLOSURE_NOTE_FORMULA_ENABLED` 配置（默认 False）到 settings，读取封装到 disclosure 相关服务；不改任何行为。
    - _Requirements: 8.3, 8.4_
  - [x] 1.2 characterization 测试锁定当前 stub 可观察行为：`resolve_formula` 返 None、`resolve_prior_year_note` value 返 None/text 返文本、`sync_report_to_notes` 仅清 is_stale 且 validation_run 硬编码。作为零回归基线。
    - _Requirements: 8.1, 8.4_
  - [x] 1.3 核实并测试 `ValidationContext` 已装配 `report_data(row_code→amount)/tb_data/prior_note_data`（依赖 `disclosure-note-validation-completion`）；缺项则补装配。
    - _Requirements: 6.1, 6.3_

- [x] 2. Wave 1：表内公式求值内核（resolve_formula + prior value）
  - [x] 2.1 实现 `resolve_formula` 的 sum/report/aging source：装配 ctx 数据后委托 `formula_parse_utils.evaluate_formula`（不新造求值器）；异常/缺数据 → None 记 issue。
    - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - [x] 2.2 实现 `resolve_prior_year_note` 的 value 模式：按 section + 坐标(+table_index) 从上年 table 反查金额；无表/坐标不存在 → None；text 模式不回归。
    - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - [x] 2.3 扩 `_prior_notes_cache` 结构为 `{section: {text, table}}`（`disclosure_engine._preload_data_for_notes` 写入），供 value 模式反查；text 模式读取路径兼容不变。
    - _Requirements: 2.1, 2.4_
  - [x] 2.4 PBT + 单测：Property 1（幂等）、2（fail-open）、3（REPORT 一致）、4（SUM 复用内核）、5（上年 value/text）。
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 9.1_

- [x] 3. Wave 2：NoteFormulaEvaluator 编排层
  - [x] 3.1 新增 `note_formula_evaluator.py::NoteFormulaEvaluator.evaluate_table`：遍历 table_data 单元格 Cell_Binding → dispatch_resolver 求值回填；仅回填 formula 单元格（manual/locked 跳过）；单元格级 fail-open；幂等；返回新 table_data 不就地改。
    - _Requirements: 1.1, 1.4, 1.5, 3.2, 8.2_
  - [x] 3.2 集成到 `generate_notes` / refill 链路（灰度内 `DISCLOSURE_NOTE_FORMULA_ENABLED`）：构表后对 Formula_Cell 求值回填，经 note_cell_merge 保留 manual/locked；开关关时旁路。
    - _Requirements: 1.1, 3.2, 8.1, 8.3_
  - [x] 3.3 PBT + 单测：Property 6（manual/locked 保留）；开关关闭旁路 characterization。
    - _Requirements: 3.2, 8.3, 8.4, 9.1_

- [x] 4. Wave 3：ReportNoteLinkage 单一真源 + 报表→附注真同步
  - [x] 4.1 新增 `report_note_linkage.py::ReportNoteLinkage`：`targets_for_report_row`（Cell_Binding source=='report' 优先 → config 回退）+ `report_rows_for_note`（反向，供 REPORT 求值共用同一 linkage）。
    - _Requirements: 4.1, 4.2, 4.3, 4.4_
  - [x] 4.2 新增 `backend/data/disclosure/report_note_linkage.json` 骨架（回退真源，按 note_section 增量维护，先覆盖高频章节；坐标非法/缺失跳过）。
    - _Requirements: 4.1, 4.3_
  - [x] 4.3 重写 `ReportNoteSyncService.sync_report_to_notes`（灰度内）：经 ReportNoteLinkage 找目标 → 写公式单元格 → note_cell_merge 保留 manual/locked → 真实统计 `{synced_sections, skipped_sections, cells_updated, validation_run}` → 触发 validate_all；无 linkage 目标计 skipped；开关关时保持仅清 stale。
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 8.3, 8.4_
  - [x] 4.4 PBT + 单测：Property 7（linkage 单一真源优先级 + 同步/求值共用目标集）、8（同步真实统计）。
    - _Requirements: 3.1, 3.3, 3.4, 4.1, 4.2, 4.4, 9.1_

- [x] 5. Wave 4：附注校验 preset 加载/解析修复
  - [x] 5.1 修 `note_validation_engine.load_preset_rules` base_dir（补 `基础数据/` 前缀或改可靠 resolve）；文件缺失 fail-open 返空规则集 + warning。
    - 交付：`_PRESET_FILES` 值补 `基础数据/附注模版/` 前缀；实测 soe 760 / listed 187 规则可加载（此前恒 0）。缺失/损坏 fail-open 返 []。
    - _Requirements: 5.1, 5.3_
  - [x] 5.2 重写 `_parse_preset_md` 支持 markdown 表格格式（`| 编号 | 类型 | 公式 | … |` 表头识别 + 数据行提取），保留 bullet 解析，两者去重。
    - 交付：markdown 表格解析（跳表头/分隔行、无表头裸行、公式内嵌|拼回、rule_id 存 metadata）+ 保留 bullet + 去重键(section,type,归一表达式)。
    - _Requirements: 5.2, 5.4_
  - [x] 5.3 确认 inline `_check_presets`/`_validation_rules` 被写入 note.table_data 并被 `collect_inline_rules_for_note` 消费；缺失则补装配（不改 executor）。
    - 交付：发现断链（生成链从不写校验 preset 进 table_data）→ disclosure_engine 新增 `_resolve_check_roles`+`_inject_validation_rules`（附加式幂等，generate_notes 构表后注入 `_validation_rules` sidecar，零渲染回归）。
    - _Requirements: 6.1, 6.2_
  - [x] 5.4 新增 `build_account_section_map`（复用 ACNR NOTE 域 / 披露模板 account_name）供完整性 executor 科目粒度校验；无映射回退 section-scope。
    - 交付：复用 `note_templates_seed.json` account_mapping_template（account_codes→note_section）；ValidationContext 加可选 account_section_map；`_execute_completeness` 加附加式科目粒度分支（gated，默认空→逐字节不变回退 section-scope）。
    - _Requirements: 7.1, 7.2, 7.3_
  - [x] 5.5 PBT + 单测：Property 9（表格解析等价 bullet 去重）、10（加载 fail-open）、11（Skip_On_Missing 优于误报）。
    - 交付：`backend/tests/test_note_preset_wave4.py`（30 passed）。
    - _Requirements: 5.2, 5.3, 5.4, 6.3, 7.3, 9.1_

- [x] 6. Wave 5：findings 集成 + 契约守卫 + 全量门
  - [x] 6.1 集成校验产 findings：generate_notes/sync 后 validate_all 产出合计=分项、附注↔报表行、变动表期初+增-减=期末、分类小计=合计；确认 DisclosureEditor 校验面板消费展示（既有面板不重建）。
    - 交付：`backend/tests/test_disclosure_note_findings_integration.py`（15 passed）。两路径：validate_all 端到端（mock DB，产 findings dict 覆盖 纵向/余额/宽表 + 平衡不产 finding）+ execute_rule 直调（纵向/其中项/交叉[report_row]/宽表 balanced pass / unbalanced fail + Skip_On_Missing）。前端字段核对（read only）：`NoteValidationFinding`(auditPlatformApi.ts)+DisclosureEditor.vue 校验面板消费 `note_section/table_name/check_type/severity/message/expected_value/actual_value` 与 validate_all findings dict 逐字段一致（测试 test_findings_dict_matches_frontend_contract 断言 ⊇）。
    - _Requirements: 6.1, 6.2, 6.4_
  - [x] 6.2 契约守卫：新增守卫脚本断言 report→note 映射只有 ReportNoteLinkage 单一真源（禁止第二处硬编码）；Property 12（开关关闭零回归）characterization。
    - 交付：`backend/scripts/check/check_report_note_linkage_single_source.py --strict` 退出 0（扫 616 services *.py；detector①硬编码 note_section+RxCx 映射字面量、detector②绕过写入=读报表+写附注单元格+未经 linkage/逐格binding 机制；豁免 report_note_linkage.py 所有者 + report_note_sync_service.py 消费者 + triple_format_adapter.py 多模块格式适配器）。Property 12 复用既有覆盖：characterization(TestResolveFormulaStub/TestSyncReportToNotesStub)+wave1(test_resolve_formula_none_when_disabled)+wave2(test_default_flag_is_off)+wave3(TestSyncStubZeroRegression)。
    - _Requirements: 4.4, 8.1, 8.3, 8.4, 9.1_
  - [x] 6.3 全量测试门：新增/既有 disclosure 相关测试全绿 + `disclosure-note-validation-completion` 无回归 + get_diagnostics 全清 + Vite transform 改动前端文件 200。
    - 交付：287 passed（wave1=21 / wave2+3=36 / characterization+preset_wave4+findings=59 / note_source_resolvers+preset_to_rule=82 / validation-completion set[completeness_aging/completion_baseline/completion_integration/context_loading/cross/secondary_llm]=89）。get_diagnostics 两新文件全清。前端未改 → 无需 Vite 检查。零新增回归差集=∅：本波仅新增 2 文件（测试+守卫），未改任何生产代码（M 生产文件均属 Wave0-4 上游）。
    - _Requirements: 9.2_
  - [x] 6.4 Playwright（需实例化项目 + 已生成报表/附注）：报表变更 → 同步 → 附注单元格更新（manual/locked 保留）；DisclosureEditor 校验面板展示 findings + 跳转披露表 round-trip。仅在存在满足前置的实例化项目时执行，否则记录前置不满足。
    - **前置不满足，未执行 Playwright（不伪造）**。已满足：dev server 9980/3030 均 200；实例化项目含报表+附注（0ec33ac9：181 附注/155 报表、2aa00f57：40/152，year=2025）。**不满足（阻断真同步 round-trip）**：report→note linkage 目标为空——`data/disclosure/report_note_linkage.json` 仅含元数据键无业务映射（0 目标），且全库 2025 附注**无一条**含 in-cell REPORT Cell_Binding（`_cell_meta.source=='report'`，SQL 实测 0）→ 即便临时开启 `DISCLOSURE_NOTE_FORMULA_ENABLED` 真同步也 `cells_updated=0`，无单元格可更新，无法演示「报表变更→同步→附注单元格更新」。findings 面板侧：全库 2025 附注**无一条**含 inline `_validation_rules`/`_check_presets`（SQL 实测 0），inline 驱动路径无数据。灰度开关默认 False，开启需改 env + 重启**共享** dev 后端（并发会话在用，有中断风险），且开启后仍受上述空 linkage 阻断。**需要**：① 至少一节附注模板内嵌 REPORT Cell_Binding 或在 report_note_linkage.json 增维护对应节的 report_row→note_cell 映射（按源模板/审计口径，不臆造）；② 生成附注时写入 inline `_validation_rules`（Wave4 Task5.3 _inject_validation_rules 已就绪，需重新生成附注使其落到 table_data）；③ 独立（非并发共享）环境临时开启灰度开关。功能正确性已由 6.1 集成测试（validate_all 端到端产 findings）+ wave3 单测（真同步写单元格/保留 manual/locked，mock DB）覆盖。
    - _Requirements: 3.1, 6.4_

## Notes

- **边界**：不改知识库 RAG 叙述（`disclosure-note-knowledge-ai-enrichment`）；不改 `_sub_table_columns` 列头投影（`disclosure-table-sync-convergence`）；不改底稿→附注同步（`wp_disclosure_sync_service`）；不改 report 内部恒等式勾稽（`logic_check`）；不改附注模板骨架/生成顺序。
- **复用不新造**：求值走 `formula_parse_utils.evaluate_formula` 单一内核；保留 manual/locked 走 `merge_table_data_preserving_cell_modes`；校验 executor 保持 `disclosure-note-validation-completion` 交付不动，仅修 preset 规则加载/解析。
- **无 DB 迁移**：Cell_Binding/linkage 存于既有 `table_data` JSON 与 data 文件。
- **灰度**：`DISCLOSURE_NOTE_FORMULA_ENABLED` 默认 False；关闭时逐字节等价当前（stub 返 None / 仅清 stale）。preset 修复（Wave4）是纯 bug 修复；若担心突现 findings 冲击，可在 5.x 评估后加 `DISCLOSURE_NOTE_VALIDATION_STRICT` 二级开关。
- **审计铁律**：Skip_On_Missing 漏报优于误报；linkage 缺失跳过可审计不写错单元格；禁止臆造报表行→附注单元格映射（config 按源模板/审计口径逐节维护）。
