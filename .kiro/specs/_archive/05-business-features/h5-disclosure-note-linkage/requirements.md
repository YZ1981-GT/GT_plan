# Requirements Document

## Introduction

H5 油气资产（科目1631/1632，行业限定 oil_gas/mining）披露表↔附注模块联动完全缺失。本 spec 补齐 SOE 披露表→附注结构化同步 + 审定表「从集中登记带入调整」双科目接入。权威附注章节：soe = 八、25（listed = null，上市无独立章节）。

## Requirements

### Requirement 1: SOE 披露表→附注结构化同步

**User Story:** 作为审计师，我在 H5 国企版披露表编制完成后，希望一键把表格和说明同步到附注模块的 八、25 章节，避免手工重录。

#### Acceptance Criteria

- 1.1 同步载荷 sub_table_data 子表键与附注模板 note_template_soe.json 八、25 tables[].name 一致
- 1.2 columns 列头为中文（来自 el-table-column 真实 label）
- 1.3 _note_texts 携带说明区段纯文本
- 1.4 payload.year 从 useAuditContext 取（不依赖后端 fallback 当前年）
- 1.5 current_standard 恒传 soe_standalone
- 1.6 成功后 emit disclosure:note-text-updated (accountCode=1631, sectionIds=[八、25])
- 1.7 上市版披露表不加同步按钮

### Requirement 2: SOE 披露表反向跳转按钮

**User Story:** 作为审计师，我在 H5 国企版披露表想快速确认附注模块中 八、25 的呈现，点击按钮即可跳转。

#### Acceptance Criteria

- 2.1 复用 buildNoteJumpRoute(projectId, H5, soe) 导航
- 2.2 上市版披露表不显示该按钮

### Requirement 3: 审定表双科目「从集中登记带入调整」

**User Story:** 作为审计师，我希望 H5-1 审定表能从集中调整登记拉取 1631/1632 相关分录，自动累加到对应区块的 AJE/RJE 列。

#### Acceptance Criteria

- 3.1 复用共享 useAdjudicationBringIn helper
- 3.2 1631 使用 direction=debit（资产借方净发生额=借-贷）
- 3.3 1632 使用 direction=credit（备抵贷方净发生额=贷-借）
- 3.4 两科目各自独立弹窗逐笔分配目标分类行
- 3.5 带入后 updateCell 累加 aje/rje + publishAdjudicated 触发 TB 回写
- 3.6 无匹配时 ElMessage.info 提示

### Requirement 4: 覆盖率守卫登记

**User Story:** 作为开发者，我需要确保新增的 buildH5SyncPayload 在覆盖率守卫中注册，CI 可追踪。

#### Acceptance Criteria

- 4.1 check_disclosure_columns_coverage.py COLUMN_BUILDERS 登记 buildH5SyncPayload
- 4.2 --strict exit 0

### Requirement 5: 零回归

**User Story:** 作为用户，我需要确保上述功能部署后不改变任何既有行为。

#### Acceptance Criteria

- 5.1 上市版无同步/跳转/bring-in 按钮
- 5.2 全改动文件 get_diagnostics 全清 + Vite transform 200
- 5.3 后端零改动
- 5.4 已有 H5 vitest 全绿

### Requirement 6: 正确性属性可测

**User Story:** 作为开发者，我需要 8 条 vitest 验证功能正确性。

#### Acceptance Criteria

- 6.1 P1-P8 vitest 全绿
- 6.2 live round-trip 通过（可选）

## Glossary

| 术语 | 含义 |
|------|------|
| sync-from-workpaper | POST 端点，推送底稿披露数据到附注 |
| buildH5SyncPayload | 待新建纯函数，构造 H5 SOE 同步载荷 |
| useAdjudicationBringIn | 共享 helper，从集中登记按科目拉调整到审定表 |
| 双科目 | H5 审定表同时管理 1631(debit) + 1632(credit) |
