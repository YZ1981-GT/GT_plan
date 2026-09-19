# Requirements Document

## Introduction

H2 在建工程（科目 1604/1605）模块 P0 修复后的 P1 增强：披露表→附注结构化推送（当前缺 buildH2SyncPayload）、审定表从集中登记带入调整（双科目特殊适配）、H2-2 明细四表取数自动种子、H4 工程物资跨底稿勾稽。科目方向：1604/1605 均为资产借方。

## Requirements

### Requirement 1: 披露表→附注结构化推送（buildH2SyncPayload）

**User Story:** 作为审计师，我在 H2 上市/国企披露表编制完成后点击「同步到附注」按钮，希望附注模块（五、23/八、23）的表格与文本框内容自动与披露表一致，无需在两处重复录入。

#### Acceptance Criteria

- 上市版 sub_table_data 覆盖模板五、23 的全部 6 张子表（在建工程汇总/在建工程明细/重要在建工程项目变动情况/变动情况续/在建工程减值准备情况/工程物资「项  目」），列头逐字对齐模板 `tables[].headers`
- 国企版 sub_table_data 覆盖模板八、23 的 4 张子表（在建工程/（1）在建工程情况/（2）重要在建工程项目本期变动情况/（3）本期计提在建工程减值准备情况）
- 数据源：汇总表→H2-1 审定数；明细/变动→H2-2 明细行；减值→H2-1 减值段；利息→H2-10/11 资本化利息；工程物资→H2-1 工程物资段；受限→H2-2 `isMortgaged='Y'` 行
- columns 键集合与 sub_table_data 键相同（投影器按名匹配）
- `_note_texts` 包含披露表文本区内容（空则不传）
- year 从 `useAuditContext().year` 取
- 覆盖率守卫 `check_disclosure_columns_coverage.py` 登记 `buildH2SyncPayload`

### Requirement 2: 正反向跳转联动核实

**User Story:** 作为审计师，我在附注编辑器查看在建工程章节（五、23/八、23）时可以跳到披露表，在披露表也能跳回附注，双向可追溯。

#### Acceptance Criteria

- `noteDisclosureJump` H2 分支返回正确 sheet 常量
- `noteDisclosureReverseJump` 已登记 `H2:{listed:'五、23',soe:'八、23'}`
- H2 披露表工具栏显示「↩ 跳转回附注」split-button（主按钮按当前变体、下拉可切换）

### Requirement 3: 审定表「从集中登记带入调整」（H2 双科目适配）

**User Story:** 作为审计师，我在 H2-1 审定表点击「从集中登记带入调整」时，希望集中式调整分录中涉及 1604/1605 科目的分录能分别带入原值段/工程物资段的期末账项调整列，对齐 F2/K6 双科目范式。

#### Acceptance Criteria

- 两独立 `useAdjudicationBringIn` 实例：1604 原值段 direction='debit' + 1605 工程物资段 direction='debit'
- 净发生额=借−贷（资产借方）
- apply 按目标行累加 endAdjustment（非替换）+ emit `substantive:adjudicated`
- 弹窗逐笔 guessTargetRowKey 按名称匹配
- 减值段不纳入 bring-in

### Requirement 4: H2-2 明细表四表取数自动种子

**User Story:** 作为审计师，我希望首次打开 H2-2 明细表时系统自动从余额表子科目预填工程项目行（科目名称/期初/期末），避免逐行手打起步。

#### Acceptance Criteria

- 后端 render 策略加 `_build_h2_detail_prefill`：查 tb_balance 1604% 叶子，按子科目名映射工程行（cipBegin=opening_balance / cipEnd=closing_balance）
- 仅叶子科目（防双算），过滤全零行
- 输出 `html_data.detail_prefill`，前端仅 `H2-2-rows` 为空时种子（Persist_First，内存态不落库）
- 灰度开关 `H2_DETAIL_PREFILL_ENABLED` 默认 True

### Requirement 5: H4 工程物资跨底稿勾稽

**User Story:** 作为审计师，我希望在 H2-1 审定表工程物资段看到与 H4 审定合计的勾稽比对结果（一致/差异金额），无需手动对照。

#### Acceptance Criteria

- 新建 `h2H4MaterialPull.ts`（复用 wp-id-by-code + checklist-responses pull 范式）从 H4 读 `H4-1-audited-total`
- H2-1 审定表渲染勾稽卡（H2 工程物资审定 / H4 审定 / 差异 / 告警）
- 「勾稽 H4」按钮触发拉取（非自动 onMounted）
- H4 缺失时显示 info 不崩

### Requirement 6: 零回归 + 向后兼容

**User Story:** 作为平台维护者，我希望以上功能落地后全部现有 H2 能力不回归。

#### Acceptance Criteria

- H2 全部 21 sheet HTML 渲染 0 error（Vite transform 200）
- 现有导入导出/跨表勾稽/利息资本化/转固检查行为不变
- 附注既有 `_tables` 不被空 sync 载荷清空（平台层 no-op 保护）
- H2-2 已有明细行不被 prefill 覆盖

### Requirement 7: 正确性属性可测

**User Story:** 作为开发者，我需要每条需求可通过自动化测试验证。

#### Acceptance Criteria

- 每条 Requirement 至少映射一个 Property
- 后端改动 AST 编译通过
- 前端改动 get_diagnostics + Vite transform 200

## Glossary

| Term | Meaning |
|------|---------|
| sync payload | `POST /wp-disclosure-sync/sync-from-workpaper` 请求体 |
| Persist_First | 仅 allResponses 无该键时才写种子值 |
| 叶子科目 | tb_balance 中某 code 不是任何其它 code 前缀的行 |
| 净额 bring-in | endAdjustment 单列 = AJE+RJE 合并 |
| H4 工程物资 | 科目 1605，独立底稿 |
