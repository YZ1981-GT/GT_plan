# D1/D2 Inventory 与口径对账表

> 本文档是 `workpaper-content-semantic-contract` spec Task 3 的交付物。
> 列明 D1/D2 生产 schema、generated 草稿、sheet inventory、映射和 cross-ref 口径。
> 可被 Task 6 (schema lint) 机器读取。

## 1. 生产 Schema vs Generated 草稿 对照表

| wp_code | 生产 schema（production） | generated 草稿（inventory only） | 角色说明 |
|---------|--------------------------|----------------------------------|----------|
| D1 | `C-D1-disclosure.yaml` | `generated/D1.yaml` | `load_schema("D1")` 命中 C-D1-disclosure（附注披露专属 schema）；generated/D1.yaml 仅作 sheet inventory |
| D2 | `C-D2-disclosure.yaml` | `generated/D2.yaml`, `generated/D2-1.yaml`, `generated/D2-5.yaml`, `generated/D2-6.yaml` | `load_schema("D2")` 命中 C-D2-disclosure；D2 主体 generated 仍是草稿 |
| D2A | `D2A.yaml` | generated/D2.yaml 内含 D2A sheet | 根目录 `D2A.yaml` 是较高质量程序控制台 schema |
| D2-8 | `D-D2-8.yaml` | `generated/D2-6.yaml` 内含 D2-8 sheet | 根目录 `D-D2-8.yaml` 是较高质量段落型坏账计算 schema |
| D2-13 | `D-D2-13.yaml` | `generated/D2-6.yaml` 内含 D2-13 sheet | 根目录 `D-D2-13.yaml` 是较高质量问答型 schema |

### 关键规则

- **`generated/*.yaml` 仅作 inventory 和迁移建议来源，不直接作为生产 schema 真源。**
- 只有根目录（非 `generated/` 子目录）的 `.yaml` 文件才是 production schema。
- 任何对 generated schema 的引用必须标注 `source_type=generated_draft`。

## 2. D1/D2 科目映射对账表

### 2.1 D1 应收票据

| 字段 | wp_account_mapping | wp_template_metadata_seed | cross_wp_references | 冲突 |
|------|-------------------|---------------------------|--------------------|----|
| wp_code | D1 | D1 | D1 (CW-27, CW-34) | ✅ 一致 |
| account_code | 1121 | 1121 | — | ✅ 一致 |
| account_name | 应收票据 | — | — | ✅ |
| report_row | **BS-004** | — | **BS-003** (CW-34) | ⚠️ 冲突：mapping=BS-004, cross_ref=BS-003 |
| note_section | **五、2** | **五、2** | **5.3** (CW-27) | ⚠️ 冲突：中文编号"五、2" vs 数字编号"5.3" |
| cross_ref_note_code | — | — | 5.3 | — |
| production_schema_path | `C-D1-disclosure.yaml` | — | — | — |
| generated_schema_path | `generated/D1.yaml` | — | — | — |
| mapping_status | **pending_inventory_reconciliation** | | | |

### 2.2 D2 应收账款

| 字段 | wp_account_mapping | wp_template_metadata_seed | cross_wp_references | 冲突 |
|------|-------------------|---------------------------|--------------------|----|
| wp_code | D2 | D2 | D2 (CW-07, CW-21~25, CW-32) | ✅ 一致 |
| account_code | 1122 | 1122 | — | ✅ 一致 |
| account_name | 应收账款 | — | — | ✅ |
| report_row | **BS-005** | — | **BS-005** (CW-32) | ✅ 一致 |
| note_section | **五、3** | **五、3** | **5.7** (CW-25) | ⚠️ 冲突：中文"五、3" vs 数字"5.7" |
| cross_ref_note_code | — | — | 5.7 | — |
| production_schema_path | `C-D2-disclosure.yaml` | — | — | — |
| generated_schema_path | `generated/D2.yaml`, `generated/D2-1.yaml` | — | — | — |
| mapping_status | **pending_inventory_reconciliation** | | | |

### 2.3 D2 细分底稿

| wp_code | account_code | report_row | note_section | production_schema | generated_schema | mapping_status |
|---------|-------------|-----------|-------------|-------------------|-----------------|----------------|
| D2-2 | 1122 | — | — | — | generated/D2.yaml 内含 | pending_inventory_reconciliation |
| D2-3 | 1122 | — | — | — | generated/D2.yaml 内含 | pending_inventory_reconciliation |
| D2-4 | 1122 | — | — | — | generated/D2.yaml 内含 | pending_inventory_reconciliation |
| D2A | 1122 | — | — | `D2A.yaml` (程序控制台) | generated/D2 内含 D2A sheet | confirmed_production |
| D2-8 | 1122 | — | — | `D-D2-8.yaml` (坏账计算) | generated/D2-6.yaml 内含 | confirmed_production |
| D2-13 | 1122 | — | — | `D-D2-13.yaml` (问答型) | generated/D2-6.yaml 内含 | confirmed_production |

## 3. 口径冲突明细

### 3.1 report_row 冲突

| wp_code | 来源 A | report_row (A) | 来源 B | report_row (B) | 分析 |
|---------|--------|---------------|--------|---------------|------|
| D1 | wp_account_mapping.json | BS-004 | cross_wp_references CW-34 | BS-003 | CW-34 将 D1 应收票据映射到 BS-003（交易性金融资产行），疑似 cross_ref 侧编码有误 |

### 3.2 note_section 编号体系不一致

| wp_code | wp_account_mapping / metadata_seed | cross_wp_references | 说明 |
|---------|-----------------------------------|--------------------|----|
| D1 | 五、2 | 5.3 | 两套编号体系：中文"五、X"（审计底稿传统标法）vs 数字"5.X"（附注章节路由 code）；数字编号间存在偏移（"五、2"≠"5.2"——因附注章节含货币资金=5.1、应收票据=5.2 或 5.3 取决于报表排列） |
| D2 | 五、3 | 5.7 | 数字编号"5.7"与中文"五、3"差距明显，说明 cross_ref 使用的附注章节号可能是按报表行完整排列后的序号 |

### 3.3 D2 在不同文件中的 report_row 表达变体

| 出现位置 | 表达形式 | 说明 |
|---------|---------|------|
| wp_account_mapping.json | BS-005 | 资产负债表行编码 |
| cross_wp_references CW-32 | BS-005 | 一致 |
| cross_wp_references CW-07 | (source_wp=D2, 无 report_row) | 仅作为减值来源 |
| generated/D2-6.yaml（含 D2-8） | 坏账准备计算表 | 内部 sheet，无 report_row 概念 |
| C-D2-disclosure.yaml | 附注披露 schema | 不含 report_row，面向附注子表 |

### 3.4 前端静态引用已知问题

- 前端静态引用中存在 D1 被误写为"营业收入"或"收入循环总控台"的情况
- 该问题由 `workpaper-account-package-d1-d2-pilot` spec 承接修复，本 inventory 仅记录

## 4. Sheet Inventory（generated schema 内含 sheet 清单）

### 4.1 generated/D1.yaml sheet inventory

| sheet_name | 推断 sheet_type | 说明 |
|-----------|----------------|------|
| D1A 应收票据审计程序表 | procedure | 程序控制台 |
| 审定表D1-1 | audit_sheet | 审定表 |
| 应收票据明细表D1-2 | detail_table | 明细 |
| 坏账准备明细表D1-4 | detail_table | 坏账明细 |
| 应收票据账龄分析表D1-5 | analysis | 账龄分析 |
| 应收票据质押检查表D1-12 | procedure | 检查程序 |
| 应收票据贴现背书明细表D1-8 | detail_table | 贴现背书 |
| 附注披露信息（上市公司） | disclosure | 对应 C-D1-disclosure.yaml |
| 附注披露信息（国企） | disclosure | 对应 C-D1-disclosure.yaml |
| D1-16 科目结论表 | conclusion | 结论 |

### 4.2 generated/D2.yaml + D2-1 + D2-5 + D2-6 sheet inventory

| sheet_name | 推断 sheet_type | 所在 generated 文件 |
|-----------|----------------|-------------------|
| D2A 应收账款实质性程序表 | control_panel / procedure | D2.yaml |
| 审定表D2-1 | audit_sheet | D2-1.yaml |
| 应收账款明细表D2-2 | detail_table | D2.yaml |
| 坏账准备明细表D2-3 | detail_table | D2.yaml |
| 调整分录汇总表D2-4 | adjustment | D2.yaml |
| 函证汇总D2-5 | confirmation_summary | D2-5.yaml |
| 应收账款ECL测算D2-6 | analysis | D2-6.yaml |
| 坏账准备计算表D2-8 | analysis | D2-6.yaml（也有独立 D-D2-8.yaml） |
| 应收账款账龄分析表D2-9 | analysis | D2-6.yaml |
| 应收账款检查D2-13 | procedure | D2-6.yaml（也有独立 D-D2-13.yaml） |
| 附注披露信息（上市公司）D2-1 | disclosure | 对应 C-D2-disclosure.yaml |
| 附注披露信息（国企） | disclosure | 对应 C-D2-disclosure.yaml |

## 5. 对账状态汇总（机器可读）

```json
{
  "inventory_version": "2025-R5-reconciliation-v1",
  "generated_at": "2026-06-07",
  "spec": "workpaper-content-semantic-contract",
  "task": "3",
  "items": [
    {
      "wp_code": "D1",
      "account_code": "1121",
      "account_name": "应收票据",
      "report_row": "BS-004",
      "note_section": "五、2",
      "cross_ref_note_code": "5.3",
      "production_schema_path": "backend/data/wp_render_schema/C-D1-disclosure.yaml",
      "generated_schema_path": "backend/data/wp_render_schema/generated/D1.yaml",
      "sheet_inventory": ["D1A", "D1-1", "D1-2", "D1-4", "D1-5", "D1-8", "D1-12", "D1-16", "附注披露(上市)", "附注披露(国企)"],
      "known_conflicts": [
        "report_row: mapping=BS-004 vs cross_ref=BS-003",
        "note_section: mapping=五、2 vs cross_ref=5.3 (编号体系不统一)"
      ],
      "mapping_status": "pending_inventory_reconciliation"
    },
    {
      "wp_code": "D2",
      "account_code": "1122",
      "account_name": "应收账款",
      "report_row": "BS-005",
      "note_section": "五、3",
      "cross_ref_note_code": "5.7",
      "production_schema_path": "backend/data/wp_render_schema/C-D2-disclosure.yaml",
      "generated_schema_path": "backend/data/wp_render_schema/generated/D2.yaml",
      "sheet_inventory": ["D2A", "D2-1", "D2-2", "D2-3", "D2-4", "D2-5", "D2-6", "D2-8", "D2-9", "D2-13", "附注披露(上市)", "附注披露(国企)"],
      "known_conflicts": [
        "note_section: mapping=五、3 vs cross_ref=5.7 (编号体系不统一)",
        "D2 在不同文件中出现 BS-005、BS-008、五、3、五-1-1、5.7 等不同表达"
      ],
      "mapping_status": "pending_inventory_reconciliation"
    },
    {
      "wp_code": "D2A",
      "account_code": "1122",
      "account_name": "应收账款(程序控制台)",
      "report_row": null,
      "note_section": null,
      "cross_ref_note_code": null,
      "production_schema_path": "backend/data/wp_render_schema/D2A.yaml",
      "generated_schema_path": "backend/data/wp_render_schema/generated/D2.yaml",
      "sheet_inventory": ["D2A"],
      "known_conflicts": [],
      "mapping_status": "confirmed_production"
    },
    {
      "wp_code": "D2-8",
      "account_code": "1122",
      "account_name": "应收账款(坏账准备计算)",
      "report_row": null,
      "note_section": null,
      "cross_ref_note_code": null,
      "production_schema_path": "backend/data/wp_render_schema/D-D2-8.yaml",
      "generated_schema_path": "backend/data/wp_render_schema/generated/D2-6.yaml",
      "sheet_inventory": ["D2-8"],
      "known_conflicts": [],
      "mapping_status": "confirmed_production"
    },
    {
      "wp_code": "D2-13",
      "account_code": "1122",
      "account_name": "应收账款(检查程序)",
      "report_row": null,
      "note_section": null,
      "cross_ref_note_code": null,
      "production_schema_path": "backend/data/wp_render_schema/D-D2-13.yaml",
      "generated_schema_path": "backend/data/wp_render_schema/generated/D2-6.yaml",
      "sheet_inventory": ["D2-13"],
      "known_conflicts": [],
      "mapping_status": "confirmed_production"
    }
  ],
  "reconciliation_rules": {
    "generated_is_not_production": true,
    "production_schema_dir": "backend/data/wp_render_schema/",
    "generated_schema_dir": "backend/data/wp_render_schema/generated/",
    "valid_mapping_statuses": [
      "confirmed_production",
      "pending_inventory_reconciliation",
      "conflict_requires_review"
    ]
  }
}
```

## 6. 下一步

1. 对账项（`mapping_status=pending_inventory_reconciliation`）需人工确认 report_row 和 note_section 正确编码后转为 `confirmed`。
2. D1 的 CW-34 `report_row_code=BS-003` 需修正为 BS-004（或确认哪个是正确值）。
3. 建立统一的 note_section 编号映射表（中文"五、X" ↔ 数字"5.X"）。
4. generated schema 可用于推断 sheet_type，但不可直接引用为 `schema_ref`。
