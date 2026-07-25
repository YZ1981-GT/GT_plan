# Requirements Document

## Introduction

F2 存货底稿跨底稿勾稽与智能取数加固。本文档定义需求。

## 背景

F2 是全平台最大的单科目模块（114 个 composable / 88 个子组件 / 4 个主入口）。二次复盘（2026-07-22）确认基础架构扎实，主要缺口集中在两类：

1. **跨底稿数据自动 Pull 缺失**：F2→D4 营业成本勾稽、NRV 测算参考售价、审定表 TB 子科目预填、期后出库自动取数、E1 现金流勾稽均需手工或不存在。
2. **内部勾稽自动化不足**：明细→审定跌价分配、抽盘→账面核对回写、库龄→呆滞候选、减值→K11 联动、截止三流匹配。

本 spec 遵循「触类旁通」范式：跨底稿 pull 复用 `h1CipH2Pull.ts`（`wp-id-by-code` + `checklist-responses` + 纯函数 extract + 容差 reconcile），后端 render 预填复用 H2 `_fetch_tb_data`/`_build_adjudication_prefill` + `related_parties`，减值联动复用 `crossWpEventBridge` 的 `impairment:calculated`，期后取数复用 D2 `importPostPaymentFromLedger`（序时账端点）。**不新造数据真源、不新造 xlsx 列格式、不改架构。**

## 范围边界

**纳入**：P0/P1 全部 + P2 高价值项（材料领用引导弹窗、成本↔损益勾稽）。
**排除**（P2 大结构改造，另立 spec）：多仓库分组视图、行业对标数据库。

## Glossary

- **跨底稿 pull**：一个底稿从另一底稿运行时取数（经 `wp-id-by-code` + `checklist-responses`）。
- **NRV**：可变现净值（估计售价 − 至完工成本 − 销售费用），CAS1 存货减值判定基础。
- **三流**：实物流（验货单）/单据流（入库单）/账务流（记账凭证），截止测试匹配对象。
- **产销存恒等式**：期初 + 本期生产入库 − 本期销售出库 = 期末。
- **优雅降级**：目标底稿缺失/为空/查询失败时返回明确状态提示而非崩溃。
- **TB 口径**：从 trial_balance/tb_balance 取审定/未审数（v2 正数 / v1 借正贷负）。

---

## Requirements

### Requirement 1: F2-1 审定表 TB 子科目预填

**User Story:** 作为审计助理，我希望 F2-1 审定表按存货子科目自动预填期初/期末未审数，这样我不必对着序时账逐行手录。

#### Acceptance Criteria

1. WHEN 渲染 F2-1 审定表且无持久化 `F2-adjudication-data` THEN 系统 SHALL 从 `tb_balance` 按科目前缀（1401~1412 原值 / 1471 跌价准备）分类归集期初/期末余额并预填到对应分类行。
2. WHERE 存在多级子科目 THE 系统 SHALL 优先取二级明细归集到 `F2_CATEGORIES` 的 rowKey，无二级时退一级总额。
3. WHEN 用户已编辑过审定表（存在持久化数据）THEN 系统 SHALL NOT 用预填覆盖用户数据。
4. WHEN 预填完成 THE 期末未审合计 SHALL 与 `trial_balance` 存货科目审定总额可勾稽（差异如实显示）。

### Requirement 2: 后端 render 上下文补 bs_date 与 related_parties

**User Story:** 作为审计助理，我希望 F2 底稿能拿到资产负债表日和关联方清单，这样期后取数窗口与关联采购识别才能自动化。

#### Acceptance Criteria

1. WHEN 渲染任一 F2 sheet THE `project_context` SHALL 包含 `bs_date`（=`{audit_year}-12-31`）。
2. WHEN 渲染任一 F2 sheet THE `project_context` SHALL 包含 `related_parties`（从 `related_party_registry` 取项目级未删除名单；无数据返回空数组不报错）。
3. IF `related_party_registry` 查询失败 THEN 系统 SHALL 优雅降级返回空数组并记 warning，不阻断渲染。

### Requirement 3: F2 出库结转 ↔ D4 营业成本勾稽

**User Story:** 作为现场经理，我希望看到存货本期减少（出库结转）与利润表营业成本的勾稽，这样能验证成本结转的完整性。

#### Acceptance Criteria

1. WHEN 用户在 F2 分析/审定区触发成本勾稽 THE 系统 SHALL 从 `trial_balance` 取主营业务成本（6401）审定发生额。
2. WHEN 明细表本期减少（出库）合计已录入 THE 系统 SHALL 计算 `出库结转合计 vs 营业成本` 差异并显示。
3. IF |差异| 超过容差（默认存货余额的 5% 或绝对值可配）THEN 系统 SHALL 以警示色 surface 差异并提示查明原因（其他业务成本/存货报废/在产品变动）。
4. IF 6401 审定数缺失 THEN 系统 SHALL 优雅提示"营业成本数据未取到"而非崩溃。

### Requirement 4: 明细表期后出库自动取数

**User Story:** 作为审计助理，我希望一键从次年序时账取存货期后出库数据，这样能验证库龄长的存货期后是否正常周转。

#### Acceptance Criteria

1. WHEN 用户在明细表点击"取期后出库" THE 系统 SHALL 从次年（bs_year+1）序时账查询存货科目贷方发生额（默认窗口次年前 6 个月）。
2. WHEN 取数完成 THE 系统 SHALL 按存货名称规范化归集并弹预览（匹配 N 项合计 X / 未匹配 M 笔 Y）供确认。
3. WHEN 用户确认 THE 系统 SHALL 将期后出库数量/金额填入明细表对应行的 `postPeriodQty`/`postPeriodAmt` 列（不覆盖已有非零值时提示）。
4. WHERE 明细表处于只读状态 THE 取数按钮 SHALL 禁用。

### Requirement 5: 明细 → 审定跌价准备分配 surface

**User Story:** 作为审计助理，我希望明细表能显示对应的跌价准备分配，这样审定表净额与报表列报口径一致。

#### Acceptance Criteria

1. WHEN F2-9 减值测试有结果 THE 系统 SHALL 将各存货类别的跌价准备金额可带入明细表/审定表。
2. WHEN 审定表渲染 THE 系统 SHALL 显示"存货净额 = 存货余额 − 跌价准备(1471)"行。
3. WHEN 跌价准备变动 THE 净额行 SHALL 自动重算。

### Requirement 6: 减值测试 → K11 资产减值损失联动

**User Story:** 作为现场经理，我希望存货跌价准备的计提/转回自动推送 K11，这样跨底稿减值数据一致。

#### Acceptance Criteria

1. WHEN F2 减值测试/转回计算出计提或转回金额 THE 系统 SHALL 通过 `eventBus.emit('impairment:calculated')` 发布（含 wpCode/amount/accountCode 1471）。
2. WHERE 事件已在 `crossWpEventBridge.BRIDGED_EVENTS` THE 发布 SHALL 同时到达 window 与 eventBus 消费者（K11）。
3. WHEN 金额为 0 或未计算 THE 系统 SHALL NOT 发布无效事件。

### Requirement 7: 呆滞存货从库龄自动提候选

**User Story:** 作为审计助理，我希望呆滞存货识别能从明细库龄自动提候选，这样减少遗漏与手工录入。

#### Acceptance Criteria

1. WHEN 明细表存在库龄 > 1 年的存货行 THE 呆滞存货表 SHALL 提供"从明细带入候选"按钮。
2. WHEN 用户点击带入 THE 系统 SHALL 按存货名称/规格汇总库龄超期行作为呆滞候选（标注"候选"需审计师确认）。
3. WHEN 候选带入 THE 系统 SHALL NOT 覆盖用户已录入的呆滞判断。

### Requirement 8: 抽盘汇总 → 账面核对回写

**User Story:** 作为审计助理，我希望 F2-25 抽盘结果自动回写 F2-24 账面核对表实盘数，这样不必两处重复录入。

#### Acceptance Criteria

1. WHEN F2-25 抽盘汇总录入盘点数量 THE F2-24 账面核对表 SHALL 提供"从抽盘带入实盘数"能力。
2. WHEN 带入完成 THE 账面核对表 SHALL 按存货名称匹配填入实盘数并自动计算账实差异。
3. IF 抽盘与账面无法匹配 THE 系统 SHALL 提示未匹配项，不静默丢弃。

### Requirement 9: 截止测试三流日期匹配 + 跨期勾稽面板

**User Story:** 作为现场经理，我希望截止测试能对比验货/入库/记账三个日期并与 D4/D6 截止勾稽，这样跨期错报识别更严谨。

#### Acceptance Criteria

1. WHEN 编制采购/销售截止测试 THE 系统 SHALL 提供验货单日期/入库单日期列（与记账凭证日期并列）。
2. WHEN 三日期差异超过阈值（默认 N 天）THE 系统 SHALL 自动标红。
3. WHEN F2-29~32 存在跨期凭证 THE 系统 SHALL 提供顶部面板显示跨期笔数/金额并提示与 D4 收入截止、D6 应付截止形成三角勾稽（跨底稿 pull，优雅降级）。

### Requirement 10: NRV 测算从 D4 pull 近期售价参考

**User Story:** 作为审计助理，我希望减值 NRV 测算能参考近期同品售价，这样估计售价有依据。

#### Acceptance Criteria

1. WHEN 编制 NRV 测算 THE 系统 SHALL 提供从收入侧（D4/序时账）pull 近期销售单价作为"估计售价"参考。
2. WHEN 参考售价带入 THE 系统 SHALL 保留其作为参考值，不强制覆盖审计师手录售价。
3. IF 售价数据不可得 THEN 系统 SHALL 优雅提示，NRV 测算仍可手工完成。

### Requirement 11: 产销存勾稽 + 成本 ↔ 损益表勾稽

**User Story:** 作为现场经理，我希望产销存恒等式与成本结转到损益表的勾稽自动 surface，这样存货完整性有闭环验证。

#### Acceptance Criteria

1. WHEN 编制产销存分析 THE 系统 SHALL 显示"期初 + 本期生产入库 − 本期销售出库 = 期末"恒等式及差异。
2. WHEN 差异非零 THE 系统 SHALL 提示归因方向（报废/盘亏/调整）。
3. WHEN 编制成本分析 THE 系统 SHALL 显示"期初在产品 + 本期完工入库成本 − 期末在产品 ≈ 营业成本"勾稽（从 TB 取数）。

### Requirement 12: F2-34 材料领用引导式弹窗

**User Story:** 作为审计助理，我希望材料领用检查像 F2-33 一样用引导式弹窗，这样多单据核对不必对着宽表横滚。

#### Acceptance Criteria

1. WHEN 编制 F2-34 材料领用检查 THE 系统 SHALL 提供引导式弹窗（分组卡片：领料单/生产工单/记账凭证 + 核对项）。
2. WHEN 用户在弹窗录入 THE 系统 SHALL 实时显示核对项勾稽状态（领料单↔工单品名数量一致/定额用量 vs 实际）。
3. WHERE 存在附件 THE 弹窗 SHALL 支持 📎 上传 + OCR 回填（复用现有 OCR 端点）。
4. WHEN 弹窗保存 THE 数据 SHALL 回写主表行并持久化（与完整表格并存）。

### Requirement 13: F2 异常 → B50 风险信号

**User Story:** 作为现场经理，我希望存货异常（呆滞/减值异常/毛利率异常）自动产生 B50 风险信号，这样风险导向审计链路可追溯。

#### Acceptance Criteria

1. WHEN F2 识别到呆滞存货/减值异常/毛利率异常 THE 系统 SHALL 通过 eventBus 发布风险信号（含来源 wpCode/风险描述）。
2. WHERE 事件通道存在 THE 信号 SHALL 可被 B50 风险识别底稿消费。
3. WHEN 无异常 THE 系统 SHALL NOT 发布空信号。

---

## 非功能约束

- **不假绿**：任务标记完成前须 vitest/pytest 真实通过 + 关键路径 Playwright 实测。
- **优雅降级**：所有跨底稿 pull 在目标底稿缺失/为空/查询失败时返回明确状态提示（wp_missing/empty/error），不崩溃。
- **UTF-8**：仅用 fs_write/str_replace 改文件，禁止 PowerShell Set-Content 破坏中文编码。
- **ref 契约**：新组件遵守 props 解包 + toRef 重包范式，避免 ref-unwrap 崩溃。
- **不臆造披露**：涉及附注/披露内容须对照源模板，不按常识造表。
