# Requirements Document

## Introduction

调整分录模块（`Adjustments.vue` + `import_templates.py::_import_adjustments` + `adjustment_service.py`）的每条明细行只持有一个科目字段 `standard_account_code`。导入模板（`export-template`）虽然让审计师从「项目科目库」下拉选择**二级明细科目**（如 `112201 应收账款-A客户`、909 行明细），但导入解析 `_import_adjustments` 通过 `_normalize_to_level1` 把二级明细码**归一到一级科目码**（`1122`）后才写入 `standard_account_code`，二级明细科目码在落库时丢失（仅 `account_name` 保留了二级名称）。

后果：调整分录**推送到底稿明细表**（`useAdjustmentDetailPropagation.matchByAccount` 按 `standard_account_code` 匹配）时只能拿到一级码 `1122`，会前缀上卷匹配到该一级下**全部**明细行（粗匹配），无法精确对应到审计师原本选定的那条明细/审定表分类。这就是用户反馈的「导出模板带了明细，但推不到底稿明细表和审定表」。

本特性在调整分录明细行**新增一个可选的「明细科目码」字段 `detail_account_code`**：一级码 `standard_account_code` 继续用于科目校验、试算表 recalc、报表取数（**功能完全不变**），新增的明细码仅用于**提高推送到底稿明细表的精度**。这是纯增量（additive）改动，历史数据与不带明细码的分录行为保持不变。

## Glossary

| 术语 | 含义 |
|------|------|
| 分录明细行 | `adjustment_entries` 表一行，一笔分录组含多行，借贷平衡 |
| 一级科目码 | `standard_account_code`，归一到标准科目（如 `1122`），用于校验/recalc/报表 |
| 明细科目码 | 新增 `detail_account_code`，审计师原始选定的二级/明细科目（如 `112201`），可空 |
| 归一化 | `_normalize_to_level1`，把二级明细码/客户码折叠到一级标准码 |
| recalc | `trial_balance_service.recalc_*`，按 `adjustments` **头表** `account_code`（一级）聚合调整数，**不读明细行表** |
| 明细表联动 | `useAdjustmentDetailPropagation`，底稿明细行按科目读时匹配集中调整明细行 |
| 前缀上卷 | `accountMatches` 现有逻辑：`a===b || a.startsWith(b) || b.startsWith(a)` |
| 零影响 | recalc/报表/审定/科目校验的输入与结果逐字节不变 |

## Requirements

### Requirement 1: 明细行新增可空 detail_account_code 字段
**User Story:** 作为审计师，我希望调整分录明细行能保留我原始选定的明细科目码，以便调整能精确对应到底稿明细表和审定表。

#### Acceptance Criteria
1. THE SYSTEM SHALL 在 `adjustment_entries` 表新增可空列 `detail_account_code`（VARCHAR，NULL 允许），通过运行时迁移（下一个可用版本号，执行前以 migration_status 复核）+ ORM 模型 `AdjustmentEntry` 同步声明。
2. THE SYSTEM SHALL 在 `AdjustmentLineItem` schema 新增可选字段 `detail_account_code: str | None = None`。
3. WHERE 明细行未提供 `detail_account_code` THE SYSTEM SHALL 将其存为 NULL，且该行的所有既有行为（校验、recalc、报表、审定、序列化）与新增字段前逐字节一致。
4. THE SYSTEM SHALL NOT 改变 `standard_account_code` 的语义、取值口径或非空约束（仍为一级标准码，用于校验/recalc/报表）。

### Requirement 2: 导入保留明细码而不改变一级归一
**User Story:** 作为审计师，我从模板下拉选了二级明细科目，希望导入后明细码被保留，同时一级归一逻辑不变。

#### Acceptance Criteria
1. WHEN `_import_adjustments` 解析每行 THE SYSTEM SHALL 继续按现有优先级把 `standard_account_code` 归一到一级标准码（一级编码 > 二级编码归一 > 二级名称归一），此逻辑逐字节不变。
2. WHEN 用户填写/下拉选择了二级明细科目（原始二级编码或经名称反查得到的 client 二级码）AND 该明细码 ≠ 归一后的一级码 THE SYSTEM SHALL 将原始明细码写入 `detail_account_code`。
3. WHEN 原始明细码为空 OR 明细码经解析后等于一级码 THE SYSTEM SHALL 将 `detail_account_code` 存为 NULL（不冗余存与一级相同的值）。
4. THE SYSTEM SHALL NOT 因新增 `detail_account_code` 而改变导入的成功/失败判定、借贷平衡校验、科目有效性校验（`_validate_account_codes` 仍只校验一级 `standard_account_code`）。

### Requirement 3: create/update 持久化 detail_account_code
**User Story:** 作为系统，我需要在写入分录明细行时持久化明细码。

#### Acceptance Criteria
1. WHEN `AdjustmentService.create_entry` 写入 `AdjustmentEntry` THE SYSTEM SHALL 将 `li.detail_account_code` 写入 `entry.detail_account_code`。
2. WHEN `AdjustmentService.update_entry` 重建明细行 THE SYSTEM SHALL 同样持久化 `detail_account_code`。
3. WHERE 前端手工新建/编辑分录未提供明细码 THE SYSTEM SHALL 存 NULL（手工录入的分录明细码可选，不强制）。

### Requirement 4: 响应与导出序列化 detail_account_code
**User Story:** 作为前端，我需要从分录响应里读到明细码才能做精确推送。

#### Acceptance Criteria
1. WHEN 分录组响应（`_build_group_response` / `AdjustmentEntryResponse` / `listAdjustments` 返回的 `line_items`）序列化明细行 THE SYSTEM SHALL 包含 `detail_account_code` 字段（NULL 时为 null）。
2. THE SYSTEM SHALL 在导出汇总（`_write_adj_sheet` / `export-summary`）保持既有列不变，可附加「明细科目」信息但不破坏既有列顺序与导入解析（additive）。
3. WHERE 明细码为 NULL THE SYSTEM SHALL 序列化为 null，不影响既有消费方。

### Requirement 5: 明细表联动优先用明细码精确匹配
**User Story:** 作为审计师，调整分录应精确推送到我选定的底稿明细行，而不是该一级科目下的全部明细行。

#### Acceptance Criteria
1. WHEN `useAdjustmentDetailPropagation` 加载调整明细行 THE SYSTEM SHALL 携带 `detail_account_code`。
2. WHEN 底稿明细行按科目匹配调整明细行 AND 调整行有 `detail_account_code` THE SYSTEM SHALL 优先用 `detail_account_code` 与底稿行科目做精确/上卷匹配。
3. WHEN 调整行 `detail_account_code` 为 NULL THE SYSTEM SHALL 回退到现有 `standard_account_code` 前缀上卷匹配（历史数据零回归）。
4. THE SYSTEM SHALL 保持 `accountMatches` 对空值的既有安全行为（任一为空返回 false）。

### Requirement 6: recalc / 报表 / 审定 / 校验零影响
**User Story:** 作为质量控制人，我要求新增明细码绝不改变试算表、报表、审定数、科目校验的任何结果。

#### Acceptance Criteria
1. THE SYSTEM SHALL 使 `trial_balance_service` 的调整聚合继续从 `adjustments` **头表** `account_code`（一级）`group_by` 聚合，**不读** `adjustment_entries.detail_account_code`。
2. THE SYSTEM SHALL 使 recalc 前后同一批分录的 `aje_adjustment` / `rje_adjustment` / `audited_amount` 结果逐字节一致（含 `origin != 'workpaper'` 过滤不变）。
3. THE SYSTEM SHALL 使报表取数（`report` 生成）与审定表带入（`useAdjudicationAdjustmentPull` / `useAdjustmentBringIn`，按 `standard_account_code` 聚合）结果不变。
4. THE SYSTEM SHALL 使 `_validate_account_codes` 仍只校验一级 `standard_account_code`，不因明细码非标准而使导入/创建失败。

### Requirement 7: 向后兼容与灰度安全
**User Story:** 作为运维，我要求上线后历史分录与旧客户端不受影响。

#### Acceptance Criteria
1. WHERE 历史 `adjustment_entries` 行 `detail_account_code` 为 NULL THE SYSTEM SHALL 表现与本特性上线前完全一致。
2. WHERE 旧前端不发送 `detail_account_code` THE SYSTEM SHALL 接受并存 NULL（schema 字段可选）。
3. THE SYSTEM SHALL 保证迁移幂等（列已存在则跳过），可安全重复应用。

### Requirement 8: 导入模板说明与手册对齐
**User Story:** 作为审计师，我希望模板/手册说明清楚明细科目会被保留用于推送到底稿。

#### Acceptance Criteria
1. THE SYSTEM SHALL 更新 `export-template` 的「关注事项」说明与调整分录模块使用手册，讲清「二级明细科目会被保留（detail_account_code），用于精确推送到底稿明细表/审定表；一级科目码用于校验与试算表/报表」。
2. THE SYSTEM SHALL NOT 因说明更新改变模板列结构或导入解析。

### Requirement 9: 正确性属性可测
**User Story:** 作为开发，我需要属性化测试锚定零回归与新行为。

#### Acceptance Criteria
1. THE SYSTEM SHALL 提供 characterization 基线测试锁定「未提供明细码时 recalc/校验/序列化逐字节不变」。
2. THE SYSTEM SHALL 提供属性化测试覆盖：明细码保留、NULL 回退、一级归一不变、recalc 不读明细码、前端匹配优先明细码。
