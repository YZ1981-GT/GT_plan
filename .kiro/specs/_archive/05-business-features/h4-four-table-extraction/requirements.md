# Requirements Document

## Introduction

H4 工程物资（科目1605）明细表 H4-2 当前全手工录入，审计师需逐行填写物资分类、期初金额、本期增减等24列。平台四表库（tb_balance/tb_ledger）已有1605多级子科目数据，应自动提取种子到 H4-2 明细（Persist-First 手工优先）+ H4-1 审定表 TB 核对行走规则映射 + H4-6 盘点覆盖率分母自动带入 + H4-5 减少检查与 H2 在建工程跨底稿勾稽。

本 spec 聚焦四表库→H4 底稿自动取数/联动，不改审定表三区块结构/不改公式引擎/不改附注联动（附注经 H2 在建工程合并披露已通，H4 无独立附注节）。

## Requirements

### Requirement 1: H4-2 明细表从 tb_balance 叶子自动种子

**User Story:** 作为审计助理，我打开 H4-2 明细表时希望系统自动从余额表提取 1605 子科目数据作为初始行，减少手工录入。

#### Acceptance Criteria

- Only leaf accounts are seeded (no parent-child double-counting)
- Zero-balance leaves (all four fields < 0.005) are excluded
- Persist-First: if `H4-2-rows` already has content, seeding is skipped entirely
- Seeded rows carry `source: 'tb_balance'` marker for provenance
- Category derivation uses last segment of account_name (e.g., "工程物资-钢材" → "钢材")
- Uses `get_active_filter` for dataset isolation

### Requirement 2: H4-1 审定表 TB 核对走规则映射

**User Story:** 作为现场经理，我希望审定表试算平衡表核对行的科目口径与报表映射一致，且项目可自定义映射不硬编码。

#### Acceptance Criteria

- report_account_mapping consulted for project-level overrides
- Fallback to `['1605']` if no mapping configured (zero-regression)
- TB amount displayed = SUM of mapped trial_balance codes' audited_amount
- `project_context.tb_source_codes` output for provenance tracing

### Requirement 3: H4-6 盘点覆盖率分母从 H4-2 自动带入

**User Story:** 作为审计助理，我执行盘点检查时希望覆盖率分母自动取 H4-2 期末合计，不用手工抄数。

#### Acceptance Criteria

- Population = H4-2 期末合计（`useH4CrossSheet.detailTotal`）
- Manual override: if user explicitly fills population field, manual takes precedence
- Zero population guard: coverage rate shows "—" not Infinity
- "从 H4-2 带入" button available for explicit pull

### Requirement 4: H4-5 减少检查↔H2 在建工程跨底稿勾稽

**User Story:** 作为现场经理，我希望 H4-5 领用出库的物资金额与 H2 在建工程记录的物资消耗金额可自动核对，差异时告警。

#### Acceptance Criteria

- Cross-workpaper pull from H2-2 detail rows via wp-id-by-code + checklist-responses
- H2-2 物资消耗字段: `transferAmount` (减少中来源=工程物资)
- Diff = H4-5 领用合计 − H2-2 物资消耗合计
- |diff| > 1 → warning alert; else → success "勾稽一致"
- "勾稽 H2" button triggers pull; cached result shown until refresh

### Requirement 5: 灰度开关与零回归

**User Story:** 作为运维人员，我希望新功能有灰度开关，默认关闭时行为与现有完全一致。

#### Acceptance Criteria

- Default = False in config.py
- render output identical when flag off
- Flag read at render-time (not startup-only)
- Frontend checks flag from `project_context.h4_extraction_enabled`

### Requirement 6: 正确性属性可测

**User Story:** 作为开发者，我希望核心取数逻辑有属性测试覆盖，防止回归。

#### Acceptance Criteria

- P1: Leaf-only seeding (parent codes excluded)
- P2: Zero-balance exclusion
- P3: Persist-First (existing rows never overwritten)
- P4: Rule-mapping TB fallback to hardcoded prefix
- P5: Coverage denominator = detailTotal
- P6: H2 pull diff calculation accuracy
- P7: Flag-off byte-equivalence
- P8: Provenance marker present on seeded rows

## Glossary

| Term | Definition |
|------|-----------|
| tb_balance | 余额表原始数据（多级子科目，借正贷负口径） |
| leaf account | 不是任何其它科目前缀的科目码（最细粒度） |
| Persist-First | 已有手工/导入数据时不覆盖（宁缺勿造） |
| report_account_mapping | 项目级报表行→科目码映射（可覆盖标准映射） |
| H2-2 物资消耗 | H2 在建工程明细表中"领用工程物资"减少项 |
| detailTotal | useH4CrossSheet computed 的 H4-2 明细期末余额合计 |
