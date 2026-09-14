# 设计文档：附注语义结构与前端呈现优化

## 概述

本设计在不破坏 `DisclosureNote.table_data` 唯一真源的前提下，引入附注语义结构层，用于支撑会计政策条款化审阅、报表科目披露四维导航、公式治理、底稿披露表绑定、披露平衡校验和离线模板工作包优化。

## 现有基础

### 模板源清单

本 spec 的语义 sidecar、模板变体矩阵、binding registry 和离线工作包均基于以下现有模板/配置派生，不直接替代它们：

| 文件 | 角色 |
|---|---|
| `backend/data/note_template_soe.json` | 国企版单体/通用附注主模板 |
| `backend/data/note_template_listed.json` | 上市版单体/通用附注主模板 |
| `backend/data/consol_note_sections_soe.json` | 国企版合并附注章节 |
| `backend/data/consol_note_sections_listed.json` | 上市版合并附注章节 |
| `backend/data/note_template_bindings.json` | 现有附注模板取数绑定 |
| `backend/data/note_wp_mapping_rules.json` | 附注与底稿映射规则 |
| `backend/data/note_check_preset_formulas.json` | 预置校验/公式 |
| `backend/data/note_soe_listed_diff.json` | 国企/上市差异 |
| `backend/data/multi_standard_note_templates.json` | 多准则模板配置 |

语义扩展初期以“派生 sidecar + diff 报告”的形式落地，不直接覆盖上述主模板。

### 后端

- `backend/app/services/disclosure_engine.py`
- `backend/app/services/note_formula_generator.py`
- `backend/app/services/note_source_resolvers.py`
- `backend/app/services/note_wp_data_resolver.py`
- `backend/app/services/note_cell_merge.py`
- `backend/app/services/note_column_semantics.py`
- `backend/app/services/note_format_config.py`
- `backend/app/services/note_word_dynamic_styles.py`
- `backend/app/services/note_validation_engine.py`
- `backend/app/services/note_auto_pull_service.py`
- `backend/app/services/note_offline_export_service.py`
- `backend/app/services/note_offline_import_service.py`

### 前端

- `audit-platform/frontend/src/views/DisclosureEditor.vue`
- `audit-platform/frontend/src/views/composables/useNoteTree.ts`
- `audit-platform/frontend/src/views/composables/useNoteDetail.ts`
- `audit-platform/frontend/src/views/composables/useNoteRefresh.ts`
- `audit-platform/frontend/src/views/composables/useNotePersist.ts`
- `audit-platform/frontend/src/views/composables/useNoteTemplate.ts`
- `audit-platform/frontend/src/components/formula/StructureEditor.vue`
- `audit-platform/frontend/src/components/formula/FormulaManagerDialog.vue`
- `audit-platform/frontend/src/components/notes/NoteOfflineExportDialog.vue`
- `audit-platform/frontend/src/components/notes/NoteOfflineImportDialog.vue`
- `audit-platform/frontend/src/components/notes/NotePriorYearPanel.vue`
- `audit-platform/frontend/src/components/notes/NoteTemplateSwitch.vue`

## 核心设计

### 1. `table_data` 兼容扩展

现有结构继续保留：

```json
{
  "headers": [],
  "rows": [],
  "_tables": [],
  "_formulas": {},
  "_check_presets": []
}
```

新增字段均采用 sidecar：

```json
{
  "_semantic": {
    "section_id": "accounts_receivable",
    "semantic_section_id": "accounts_receivable",
    "variant": "soe_consolidated",
    "scope": "consolidated"
  },
  "_tables": [
    {
      "table_id": "aging_analysis",
      "name": "账龄分析",
      "columns": [
        {
          "col_id": "closing_balance",
          "label": "期末余额",
          "source": "workpaper",
          "amount_role": "closing"
        }
      ],
      "rows": [
        {
          "row_id": "within_1_year",
          "row_type": "data",
          "label": "1年以内",
          "values": [100],
          "_cell_modes": {"0": "auto"},
          "_cell_meta": {"0": {"binding_id": "ar_aging_within_1y_closing"}}
        }
      ]
    }
  ]
}
```

### 2. 会计政策条款结构

新增 `_policy_clauses` sidecar：

```json
{
  "_policy_clauses": [
    {
      "clause_id": "policy_revenue",
      "title": "收入确认",
      "level": 2,
      "current_text": "...",
      "template_text": "...",
      "prior_year_text": "...",
      "variables": ["company_name", "year"],
      "diff_status": "changed",
      "confirm_status": "pending"
    }
  ]
}
```

前端新增 `NotePolicyReviewPanel.vue`：

- 条款目录
- 模板 / 上年 / 本年三栏对照
- 差异摘要
- 变量高亮
- 批量确认未变条款

#### clause_id 生成规则

条款 ID 必须稳定，不能依赖纯标题模糊匹配：

1. 若模板源显式提供 `clause_id`，直接使用。
2. 若无显式 ID，则使用 `semantic_section_id + heading_path_hash`。
3. 若同一 heading path 重复，追加稳定序号。
4. 上年/模板/本年对比必须使用 `clause_id` 对齐，不允许仅按标题文本匹配。
5. 标题改名但 heading path 位置不变时，应保留原 clause_id 并标记 title_changed。

### 3. 数据披露四维上下文

新增 `NoteDisclosureContextBar.vue`：

```text
单位 | 年度 | 科目/明细 | 金额口径
```

数据来源：

- 单位：项目 / 合并范围 / 子公司
- 年度：ProjectContext
- 科目：note semantic section + report mapping
- 金额口径：columns[].amount_role

单位维度来源：

| 场景 | 来源 |
|---|---|
| 单体 | 当前项目 |
| 合并 | 合并范围服务 / `consol_scope` |
| 子公司 | 合并范围内 component entity |
| 分部 | 后续分部配置 |
| 关联方 | 关联方主体，不等同于合并单位 |

### 4. row_type 与结构保护

行类型枚举：

```typescript
type NoteRowType =
  | 'table_title'
  | 'group_header'
  | 'data'
  | 'subtotal'
  | 'total'
  | 'note_tip'
  | 'footnote'
  | 'blank'
  | 'custom'
```

编辑规则：

- 普通内容编辑仅允许 `data/custom/note_tip/footnote`。
- `table_title/group_header/subtotal/total` 默认结构锁定。
- 结构编辑必须通过 `StructureEditor` 且要求更高权限。

### 5. 公式治理

公式锚点升级为：

```text
section_id + table_id + row_id + col_id
```

`_formulas` 扩展：

```json
{
  "accounts_receivable.aging_analysis.within_1_year.closing_balance": {
    "formula_id": "f_ar_001",
    "expr": "WP('D2','附注披露表','within_1_year_closing')",
    "source": "template",
    "dependencies": [
      {"type": "workpaper", "wp_code": "D2", "field": "within_1_year_closing"}
    ],
    "last_result": "100.00",
    "last_error": null,
    "last_evaluated_at": "2026-06-06T00:00:00Z"
  }
}
```

前端新增或扩展 `NoteCellSourceDrawer.vue`：

- 当前值
- 公式
- 来源
- 依赖
- 执行结果
- 手工覆盖
- 恢复自动

### 6. note_binding_registry

初期可采用 JSON 配置，后续再评估 DB 化：

```json
{
  "binding_id": "ar_aging_within_1y_closing",
  "section_id": "accounts_receivable",
  "table_id": "aging_analysis",
  "row_id": "within_1_year",
  "col_id": "closing_balance",
  "source": "workpaper",
  "wp_code": "D2",
  "sheet": "附注披露表",
  "field": "within_1_year_closing",
  "aggregation": "sum"
}
```

后端新增 `note_binding_registry_service.py`：

- load registry
- resolve binding
- validate binding
- impact by source change

### 7. 披露平衡规则

新增 `note_disclosure_balance_rules.json`：

```json
{
  "rule_id": "ar_closing_balance_tieout",
  "section_id": "accounts_receivable",
  "left": "sum(note.accounts_receivable.aging_analysis.*.closing_balance)",
  "right": "report.BS.accounts_receivable.closing_balance",
  "tolerance": "0.01",
  "severity": "blocking"
}
```

后端新增 `note_disclosure_balance_service.py`，结果进入附注质量清单。

### 7.1 关联方披露专项

关联方章节单独建模，不简单套用普通科目披露：

数据来源：

- `backend/app/models/related_party_models.py`
- EQCR 关联方模块
- 附件/函证证据
- 手工交易明细
- 报表余额

建议新增 `related_party_disclosure_adapter.py`：

- 关联方主体清单
- 关系类型
- 交易类型
- 本期发生额
- 期末余额
- 是否已函证/是否有附件
- 与报表项目的 tie-out

### 8. 离线工作包结构

导出 xlsx 包含：

- `00_填报说明`
- `01_章节清单`
- `政策条款`
- `科目披露`
- `关联方`
- `99_校验结果`

每个 sheet 保留隐藏列：

- `section_id`
- `table_id`
- `row_id`
- `col_id`
- `binding_id`
- `cell_mode`

导入兼容策略：

- 旧版离线包继续按现有导入路径处理。
- 新版 semantic workbook 在隐藏 `_meta` sheet 中记录 `workbook_version`、`template_type`、`semantic_version`。
- 用户修改隐藏语义列时，导入结果标记 `structure_conflict`。
- 用户修改锁定单元格时，导入结果标记 `locked_cell_conflict`。
- 公式列被修改时，导入结果标记 `formula_override_attempt`。

### 9. 模板变体矩阵

新增 `note_template_variant_matrix.json`：

```json
{
  "semantic_section_id": "accounts_receivable",
  "variants": {
    "soe_standalone": {"section_id": "soe_ar_s", "number": "五、3"},
    "soe_consolidated": {"section_id": "soe_ar_c", "number": "八、3"},
    "listed_standalone": {"section_id": "listed_ar_s", "number": "五、4"},
    "listed_consolidated": {"section_id": "listed_ar_c", "number": "七、4"}
  }
}
```

### 10. 质量清单结果 schema

```json
{
  "level": "blocking",
  "category": "tieout",
  "section_id": "accounts_receivable",
  "table_id": "aging_analysis",
  "row_id": "total",
  "col_id": "closing_balance",
  "message": "附注明细合计与报表应收账款期末数不一致",
  "route": "/projects/{pid}/disclosure-notes?section=accounts_receivable",
  "evidence": {
    "left": "123.00",
    "right": "120.00",
    "diff": "3.00"
  }
}
```

### 11. 绑定注册表 CI 校验

新增 `check_note_binding_registry.py`：

- 校验 `section_id/table_id/row_id/col_id` 存在于模板或 sidecar。
- 校验 `wp_code` 存在于底稿模板库或项目底稿索引。
- 校验 `source` 枚举合法。
- 校验同一 cell 不存在重复 active binding。
- 校验 source_missing 时存在 fallback 或显式说明。

## API 草案

- `GET /api/disclosure-notes/{pid}/{year}/{section}/policy-clauses`
- `POST /api/disclosure-notes/{pid}/{year}/{section}/policy-clauses/confirm`
- `GET /api/disclosure-notes/{pid}/{year}/{section}/semantic-table`
- `GET /api/disclosure-notes/{pid}/{year}/{section}/cell-source`
- `GET /api/disclosure-notes/{pid}/{year}/quality-checklist`
- `GET /api/disclosure-notes/template-variants/{semantic_section_id}`
- `GET /api/disclosure-notes/{pid}/{year}/{section}/related-party-disclosure`
- `POST /api/disclosure-notes/{pid}/{year}/semantic-sidecar/preview`

## 迁移策略

1. 不修改现有 `values` 数组语义。
2. 新增 `row_type/table_id/row_id/col_id` 都作为 sidecar。
3. 缺失 sidecar 时按旧结构推断。
4. P0 不做 DB 迁移，先基于 JSONB 兼容扩展。
5. binding registry 初期用 JSON 配置，待试点稳定后再 DB 化。
6. P0-MVP 不新增数据库表，不改 `disclosure_notes` 表结构；所有新增字段仅存在于 `table_data` sidecar 或前端 DTO。
7. 旧 `_formulas` 下标锚点继续有效；新语义锚点优先。若两者同时命中同一 cell 且结果不一致，记录 warning 并保留旧结果，不静默覆盖。

## 风险与回滚

- 风险：sidecar 推断不准。  
  回滚：只在标注完整的章节启用 semantic mode。
- 风险：离线模板变复杂。  
  回滚：保留旧离线导出格式，新增 `semantic_workbook=true` 参数。
- 风险：公式锚点迁移影响旧公式。  
  回滚：保留旧下标公式，新增语义锚点公式优先级更高。
