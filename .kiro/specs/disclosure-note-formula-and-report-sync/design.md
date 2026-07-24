# Design Document

## Overview

围绕"附注单元格的自动取数与勾稽"三处断裂，本设计以**最小侵入 + 复用既有内核 + 单一真源**为原则：

- **不新造求值器**：`resolve_formula` 委托既有公式内核（`formula_parse_utils.evaluate_formula` / `formula_management` 引擎），只补 source 数据装配。
- **linkage 单一真源**：报表 → 附注同步与表内 REPORT 公式求值共用同一 `ReportNoteLinkage`，避免两套映射漂移（正是本平台反复踩的坑）。
- **fail-open + 灰度**：所有新行为经 `DISCLOSURE_NOTE_FORMULA_ENABLED` 开关，默认关时逐字节等价当前。
- **Skip_On_Missing**：审计场景漏报优于误报，缺数据源一律 skip 不 false fail。

三处改动落在既有构件上（不新建大模块）：
- ①/② → `note_source_resolvers.py`（resolve_formula/resolve_prior_year_note）+ 新增薄编排 `NoteFormulaEvaluator` + `ReportNoteLinkage` + 重写 `ReportNoteSyncService.sync_report_to_notes`。
- ⑤ → `note_validation_engine.load_preset_rules` + `_parse_preset_md` + ValidationContext（已装配 report/tb/prior）。

## Architecture

```
                    ┌─────────────────────────────────────────────┐
                    │  DISCLOSURE_NOTE_FORMULA_ENABLED (灰度开关)   │
                    └─────────────────────────────────────────────┘
  报表变更 ──▶ sync_report_to_notes(重写) ──┐
                                            │  经 linkage 找目标 note cell
  generate_notes / refill ──▶ NoteFormulaEvaluator.evaluate_table ──┐
                                            │                        │
                                            ▼                        ▼
                          ┌──────────────────────────┐   ┌────────────────────────┐
                          │  ReportNoteLinkage(单一)  │   │  dispatch_resolver      │
                          │  ① Cell_Binding(REPORT)   │   │  → resolve_formula      │
                          │  ② report_note_linkage.json│  │    (sum/aging/report)   │
                          └──────────────────────────┘   │  → resolve_prior_year   │
                                            │             │    _note (value 模式)   │
                                            ▼             └────────────┬───────────┘
                          note_cell_merge(保留 manual/locked)          │ 复用
                                            │                          ▼
                                            ▼               formula_parse_utils
                          disclosure_notes.table_data       .evaluate_formula(既有内核)
                                            │
                                            ▼
                          note_validation_engine.validate_all
                          (load_preset_rules 修复 + _parse_preset_md 表格解析)
                                            │
                                            ▼
                          findings ──▶ DisclosureEditor 校验面板(既有)
```

### 决策 1：resolve_formula 委托既有内核，不新造求值器

`resolve_formula(binding, ctx)` 按 `binding.source` 装配数据后委托 `formula_parse_utils.evaluate_formula`（本平台求值单一内核，18 caller 已收口）：
- `source=='sum'`：从 ctx 的当前表 cells 取指定坐标区间 → 求和。
- `source=='report'`：从 `ctx["report_data"]`（row_code → amount，ValidationContext 已装配）取值。
- `source=='aging'`：复用既有账龄配置聚合（`useAgingConfig` 对应后端段）。
- `source=='prior_year_note'`：委托 `resolve_prior_year_note`（Req2）。

**理由**：避免第二套表达式引擎（memory 铁律"求值内核已收口"），只补 source→数据的装配。

### 决策 2：resolve_prior_year_note value 模式做单元格反查

`_prior_notes_cache` 当前只缓存 `text_content`（str）。value 模式需上年 `table_data` 单元格值 → 扩缓存为 `{note_section: {"text": str, "table": dict}}`，value 模式按 `binding.section + cell坐标(+table_index)` 反查。上年无表/坐标不存在 → None（Req2.2）。**text 模式行为不变**（Req2.3）。

### 决策 3：Report_Note_Linkage 单一真源（Cell_Binding 优先，config 回退）

经查证全平台无「报表行→附注单元格」映射。设计单一真源 `ReportNoteLinkage.resolve(report_row_code) → [{note_section, cell, table_index}]`：
1. **优先**：扫描 note.table_data 各单元格 Cell_Binding，`source=='report' && row_code==X` 的单元格即目标（就地绑定，天然单一真源，随模板演进）。
2. **回退**：`backend/data/disclosure/report_note_linkage.json`（data-driven，按 note_section 增量维护，仅覆盖模板未内嵌绑定的章节）。

报表 → 附注同步与表内 REPORT 公式求值**共用此 linkage**（Req4.4），杜绝漂移。

### 决策 4：sync_report_to_notes 真同步（保留 manual/locked）

重写为：load report rows（current_period_amount）→ 对每行经 ReportNoteLinkage 找目标 note cell → 写入公式驱动单元格 → 经 `merge_table_data_preserving_cell_modes` 保留 manual/locked（Req3.2）→ 真实统计 `{synced_sections, skipped_sections, cells_updated, validation_run}`（Req3.3）→ 触发 `validate_all`（Req3.5/Req6）。无 linkage 目标 → skipped 计数（Req3.4）。

### 决策 5：preset 加载/解析修复（不改 executor）

`disclosure-note-validation-completion` 已交付 11 executor + ValidationContext 数据装配，唯 preset **规则加载**死：
- 修 `load_preset_rules` base_dir（补 `基础数据/` 前缀或改可靠 resolve）。
- 重写 `_parse_preset_md`：新增 markdown 表格解析（`| 编号 | 类型 | 公式 | … |` 表头识别 + 数据行提取），保留既有 bullet 解析，两者去重（Req5.4）。
- 确认 inline `_check_presets`/`_validation_rules` 被写入 `table_data`（`collect_inline_rules_for_note` 消费）。
- account↔section 映射（Req7）：复用 ACNR NOTE 域 / 披露模板 account_name 派生，供完整性 executor 落到科目粒度。

### 决策 6：灰度开关默认关 = 零回归

`DISCLOSURE_NOTE_FORMULA_ENABLED`（默认 False）。关闭时：`resolve_formula` 保持返 None、`sync_report_to_notes` 保持仅清 stale（当前可观察行为）。开启时启用新求值/同步。preset 修复（⑤）不受开关约束（纯 bug 修复，无新副作用；但若担忧可另置 `DISCLOSURE_NOTE_VALIDATION_STRICT` — 由 Design 阶段核实 executor 是否已在生产被调用后决定，避免突然涌现 findings）。

## Components and Interfaces

### NoteFormulaEvaluator（新增薄编排层，`note_formula_evaluator.py`）

```python
class NoteFormulaEvaluator:
    async def evaluate_table(self, table_data: dict, ctx: dict) -> dict:
        """遍历 table_data 各单元格 Cell_Binding，dispatch_resolver 求值回填。
        - 仅回填 Cell_Mode=='formula' 单元格（manual/locked 跳过）。
        - fail-open：单元格求值异常 → 该格保持原值 + 记 issue，不中断整表。
        - 幂等：相同 ctx 二次求值结果一致。
        返回带回填值的新 table_data（不就地改，便于 merge）。
        """
```

### resolve_formula / resolve_prior_year_note（`note_source_resolvers.py`，改造）

```python
async def resolve_formula(binding, ctx) -> Any:
    # source: sum | aging | report → 装配数据 + 委托 evaluate_formula；异常 → None
async def resolve_prior_year_note(binding, ctx) -> Any:
    # field=='text' → 原行为; field=='value' → 上年 table 单元格反查
```

### ReportNoteLinkage（新增，`report_note_linkage.py`）

```python
class ReportNoteLinkage:
    def targets_for_report_row(self, notes: list[DisclosureNote], row_code: str) -> list[LinkTarget]:
        # ① 扫 Cell_Binding(source=='report', row_code) ② 回退 config json
    def report_rows_for_note(self, note) -> set[str]:  # 反向，供 REPORT 公式求值
```

### ReportNoteSyncService.sync_report_to_notes（重写）

签名不变，返回值扩展为真实统计。内部走 ReportNoteLinkage + note_cell_merge + validate_all。

### note_validation_engine（改造）

`load_preset_rules`（路径修复）、`_parse_preset_md`（表格解析）、`build_account_section_map`（新增，Req7）。executor 不改。

## Data Models

### Cell_Binding（约定，存于 table_data 单元格）

```json
{ "source": "report|sum|aging|prior_year_note", "row_code": "BS-015",
  "cells": ["R2C2","R3C2"], "field": "value|text", "section": "五、18", "table_index": 0 }
```

### report_note_linkage.json（回退真源，data-driven）

```json
{ "BS-015": [{ "note_section": "五、22", "cell": "R9C2", "table_index": 0 }] }
```

### ValidationContext（已存在，本 spec 不改结构，仅确认装配）

`{ note_data, report_data(row_code→amount), tb_data, prior_note_data }`

### 迁移

无 DB schema 变更（Cell_Binding/linkage 存于既有 `table_data` JSON 与 data 文件）。无新迁移号。

## Correctness Properties

### Property 1: 公式求值幂等
对同一 table_data + ctx，`evaluate_table` 二次求值结果逐值相等。
**Validates: Requirements 1.5**

### Property 2: 求值 fail-open
任意 binding/ctx（含缺字段、非法坐标、缺数据源）下 `resolve_formula` 返 None 或数值，绝不抛出到调用方。
**Validates: Requirements 1.4, 8.2**

### Property 3: REPORT source 取值一致
`source=='report'` 求得的值等于 ctx.report_data[row_code]；row_code 不存在 → None。
**Validates: Requirements 1.3**

### Property 4: SUM 复用内核
`source=='sum'` 结果等于既有 `evaluate_formula` 对同坐标区间的求和（不另算）。
**Validates: Requirements 1.2**

### Property 5: 上年 value 反查
value 模式返回上年 table 对应坐标值；上年无表/坐标不存在 → None；text 模式行为不变。
**Validates: Requirements 2.1, 2.2, 2.3, 2.4**

### Property 6: manual/locked 保留
report → note 同步 / 公式回填后，Cell_Mode ∈ {manual, locked} 的单元格值不变。
**Validates: Requirements 3.2**

### Property 7: linkage 单一真源优先级
同一 row_code 在 Cell_Binding 与 config 都有目标时，以 Cell_Binding 为准；同步与 REPORT 求值取相同目标集合。
**Validates: Requirements 4.1, 4.2, 4.4**

### Property 8: 同步真实统计
`sync_report_to_notes` 返回的 cells_updated 等于实际写入的公式单元格数；无 linkage 的行计入 skipped_sections；validation_run 反映实际。
**Validates: Requirements 3.1, 3.3, 3.4**

### Property 9: preset 表格解析等价 bullet
同一规则以 bullet 与 markdown 表格两种格式书写时，解析出的可执行规则集等价且去重。
**Validates: Requirements 5.2, 5.4**

### Property 10: preset 加载 fail-open
preset 文件缺失/损坏时 `load_preset_rules` 返回空规则集不抛错。
**Validates: Requirements 5.3**

### Property 11: Skip_On_Missing 优于误报
校验依赖数据源缺失时 finding.passed=true + details.skipped，绝不 false fail。
**Validates: Requirements 6.3, 7.3**

### Property 12: 开关关闭零回归
`DISCLOSURE_NOTE_FORMULA_ENABLED=False` 时，resolve_formula 返 None、sync_report_to_notes 仅清 stale，与当前可观察行为逐字节等价。
**Validates: Requirements 8.1, 8.3, 8.4**

## Error Handling

- resolve_formula / evaluate_table：单元格级 try/except，异常记 issue + 该格保持原值，整表继续（Req1.4）。
- sync_report_to_notes：单节 try/except 隔离，一节失败不影响其余，计入 skipped + errors（Req3.4）。
- load_preset_rules：文件缺失/解析异常 → 空规则集 + warning（Req5.3）。
- 校验依赖缺失：executor 已具 Skip_On_Missing（`disclosure-note-validation-completion` 交付），本 spec 保持不引入 false fail（Req6.3）。

## Testing Strategy

- **PBT（hypothesis，max_examples=5）**：P1-P12 逐条属性测试（求值幂等/fail-open/linkage 优先/skip/开关零回归）。
- **单测**：resolve_formula 各 source、resolve_prior_year_note value/text、ReportNoteLinkage 优先级、sync_report_to_notes 真统计、_parse_preset_md 表格解析。
- **集成（真实 PG16）**：generate_notes → 公式回填 → validate_all 产 findings；report 变更 → sync → note cell 更新（manual/locked 保留）。
- **契约守卫**：linkage 单一真源守卫（禁止新增第二处 report→note 硬编码映射）；开关关闭零回归 characterization。
- **Playwright（可选，需实例化项目）**：DisclosureEditor 校验面板展示 findings + 跳转披露表 round-trip。

## Migration / Rollout（M0-M3）

- **M0**：开关默认关；characterization 锁定当前 stub 行为；确认 ValidationContext 已装配 report/tb/prior（依赖 `disclosure-note-validation-completion`）。
- **M1**：resolve_formula + prior value + NoteFormulaEvaluator（灰度内）。
- **M2**：ReportNoteLinkage + sync_report_to_notes 真同步。
- **M3**：preset 加载/解析修复 + account↔section 映射 + findings 集成 + 全量门。
