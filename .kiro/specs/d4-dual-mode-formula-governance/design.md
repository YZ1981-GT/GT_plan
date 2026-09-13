# Design — D4双模式公式治理总纲

## 统一范围与分母
本总纲治理36个逻辑 `wp_code`，不把物理 Excel sheet、sheet 变体或程序表纳入分母。`D4-22A`、`D4-31T`、D422A 等仅作为实现证据。公式定义 key 必须使用 `wp_id`；`preset_version`只表示定义版本，不属于业务 target identity。

## R1 逐表 owner 矩阵（唯一真源）
| wp_code | owner | 目标/边界 | 状态 |
|---|---|---|---|
| D4-1 | d4-dual-mode-formula-governance | 审定表 | 专属 |
| D4-2 | d4-revenue-matrix-bidirectional | 主营明细矩阵 | 专属 |
| D4-3 | d4-revenue-matrix-bidirectional | 其他收入明细 | 专属 |
| D4-4 | d4-adjustment-and-analysis-gap-closure | 调整分录；复用A13/集中调整 | gap |
| D4-5 | d-cycle-sheet-bidirectional-expansion | 政策检查；既有d-cycle扩展 | 已有owner |
| D4-6 | d-cycle-sheet-bidirectional-expansion | 指标分析；既有d-cycle扩展 | 已有owner |
| D4-7 | d-cycle-sheet-bidirectional-expansion | 月度毛利；既有d-cycle扩展 | 已有owner |
| D4-8 | d4-adjustment-and-analysis-gap-closure | 产品毛利；复用现有计算 | gap |
| D4-9 | d4-9-customer-structure-bidirectional-writeback | 客户结构双区 | 专属 |
| D4-10 | d4-price-analysis-writeback-linkage | 客户价格联动 | 专属 |
| D4-11 | d4-price-analysis-writeback-linkage | 产品价格联动 | 专属 |
| D4-12 | d4-adjustment-and-analysis-gap-closure | 合同检查；复用卡片/OCR/AI | gap |
| D4-13 | d4-inspection-writeback-formula-io | ERP检查 | d-cycle扩展 |
| D4-14 | d4-inspection-writeback-formula-io | 发生检查 | d-cycle扩展 |
| D4-15 | d4-inspection-writeback-formula-io | 完整性检查 | d-cycle扩展 |
| D4-16 | d4-inspection-writeback-formula-io | 出口检查 | d-cycle扩展 |
| D4-17 | d4-cutoff-return-writeback-formula-io | 截止前向 | d-cycle扩展 |
| D4-18 | d4-cutoff-return-writeback-formula-io | 截止后向 | d-cycle扩展 |
| D4-19 | d4-cutoff-return-writeback-formula-io | 折扣检查 | d-cycle扩展 |
| D4-20 | d4-cutoff-return-writeback-formula-io | 退货检查 | d-cycle扩展 |
| D4-21 | d4-21-24-oo-bidirectional-and-cross-sheet-formula | 关联方价格 | d-cycle扩展 |
| D4-22 | d4-21-24-oo-bidirectional-and-cross-sheet-formula | IPO指标 | d-cycle扩展 |
| D4-23 | d4-21-24-oo-bidirectional-and-cross-sheet-formula | 发票比较 | d-cycle扩展 |
| D4-24 | d4-21-24-oo-bidirectional-and-cross-sheet-formula | 第三方检查 | d-cycle扩展 |
| D4-25 | d4-ipo-fraud-writeback-formula | IPO经销商 | d-cycle扩展 |
| D4-26 | d4-ipo-fraud-writeback-formula | 境外收入 | d-cycle扩展 |
| D4-27 | d4-ipo-fraud-writeback-formula | 未披露关联方 | d-cycle扩展 |
| D4-28 | d4-ipo-fraud-writeback-formula | 客户核查 | d-cycle扩展 |
| D4-29 | d4-ipo-fraud-writeback-formula | 客户明细 | d-cycle扩展 |
| D4-30 | d4-ipo-fraud-writeback-formula | 访谈汇总 | d-cycle扩展 |
| D4-31 | d4-ipo-fraud-writeback-formula | 访谈明细 | d-cycle扩展 |
| D4-32 | d4-ipo-fraud-writeback-formula | 资金流 | d-cycle扩展 |
| D4-33 | d4-33-36-writeback-formula-and-io-closure | 其他收入毛利 | d-cycle扩展 |
| D4-34 | d4-33-36-writeback-formula-and-io-closure | 其他收入合同 | d-cycle扩展 |
| D4-35 | d4-33-36-writeback-formula-and-io-closure | 其他收入检查 | d-cycle扩展 |
| D4-36 | d4-33-36-writeback-formula-and-io-closure | 其他收入截止 | d-cycle扩展 |

D4-5/6/7按实际 `D4TabPolicyCheck`、`D4TabIndicator`、`D4TabMarginMonthly` 及 d-cycle bridge 核定；D4-4/8/12只收口双向身份、公式和验收，不重做已有A13/调整、产品月度计算、合同卡片/OCR/AI。

## R2-R8
### R2 共享同步协议
HTML、Excel、导入导出统一经过 `ContentMutationService` 与 `useWorkpaperSyncBridge`。不同字段自动合并；同字段冲突保留 base/current/incoming、决策和轨迹。durable ack仅表示决策已持久化，不等于applied；canonical rematerialize及目标content version确认后才算applied。禁止Excel优先、最后写胜出和文件直读回调。

### R3 公式定义
key=`wp_id + stable_sheet_key + row_key + field_key + custom`；`preset_version`只参与定义版本比较，不进入业务target identity。升级保留custom，删除custom恢复preset；缺失、损坏、blocked、stale分态。F-SHELL v2和编辑schema白名单，禁止eval、外链和remark/field_overrides冒充公式库。

### R4 DAG与联动
表内、表间公式均可二次编辑，同scope单writer，按真实引用建DAG。循环、冲突、stale显式失败。公式同步不是TB/A13；TB/A13只能由独立显式确认发布。

### R5-R8 验收
风险发现不等于错报；四表取数复用 `app/services/four_table/`。导入保留sheet/table/region/stable row key/formula mask。按角色、scope、wp_id、content version做CAS。C0模板/identity、C1sync、C2formula、C3linkage、C4逐表验收只门控相关平台产物，不等待全平台77项；UNVERIFIABLE不计GREEN。

## Correctness Properties
### Property 1: 分母恒36且owner唯一
36个且仅36个 `wp_code` 各有一条owner记录；物理sheet/变体/程序表不扩张分母。
**Validates: Requirements 1.1, 1.2, 8.1**
### Property 2: 三方合并与durable-ack≠applied
不同字段自动合并，同字段冲突保留三方轨迹；durable ack在applied前不会伪装为applied。
**Validates: Requirements 2.1, 2.2**
### Property 3: 公式key用wp_id且分态
公式key使用 `wp_id`，preset/custom/stale/损坏/缺失可区分，禁止eval和外链。
**Validates: Requirements 3.1, 3.2, 3.3**
### Property 4: 真实DAG与发布边界
表内表间真实DAG支持二次编辑，循环和单writer冲突失败；同步不触发TB/A13。
**Validates: Requirements 4.1, 4.2, 5.1**
### Property 5: 只门控相关产物不假绿
各owner的C0-C4只门控相关产物，UNVERIFIABLE不假绿。
**Validates: Requirements 8.1**
