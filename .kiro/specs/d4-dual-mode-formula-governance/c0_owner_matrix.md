# C0 Owner矩阵 — D4-1..D4-36

> 依据：`backend/wp_templates/_index.json`（476条记录）+ 各模板文件 sheet 实际枚举（openpyxl read_only 实读）
> 分母：36 个逻辑 `wp_code`（D4-1 ~ D4-36），不把物理 sheet/变体/程序表纳入分母
> 模板源：`backend/wp_templates/`（运行时权威），不含 `~$` 锁文件及 `.bak`/`.preclean.bak` 副本

---

## 矩阵总表

| # | wp_code | owner_spec | 目标/边界 | 状态 | 模板文件 | 对应 sheet 名 | 模板存在 |
|---|---------|-----------|---------|------|---------|-------------|---------|
| 1 | D4-1 | d4-dual-mode-formula-governance | 营业收入审定表 | 专属 | D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx | 营业收入审定表D4-1 | Y |
| 2 | D4-2 | d4-revenue-matrix-bidirectional | 主营业务收入明细矩阵 | 已有owner | D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx | 主营业务收入明细表D4-2 | Y |
| 3 | D4-3 | d4-revenue-matrix-bidirectional | 其他业务收入明细 | 已有owner | D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx | 其他业务收入明细表D4-3 | Y |
| 4 | D4-4 | d4-adjustment-and-analysis-gap-closure | 调整分录汇总（复用A13/集中调整） | gap | D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx | 营业收入调整分录汇总D4-4 | Y |
| 5 | D4-5 | d-cycle-sheet-bidirectional-expansion | 会计政策检查 | 已有owner | D4-5 营业收入-会计政策（Leap-常规程序）.xlsx | 营业收入会计政策检查D4-5 | Y |
| 6 | D4-6 | d-cycle-sheet-bidirectional-expansion | 重要指标分析 | 已有owner | D4-6至D4-11营业收入 - 分析程序（Leap应对措施-分析程序）.xlsx | 重要指标分析D4-6 | Y |
| 7 | D4-7 | d-cycle-sheet-bidirectional-expansion | 毛利率分析 | 已有owner | D4-6至D4-11营业收入 - 分析程序（Leap应对措施-分析程序）.xlsx | 毛利率分析表D4-7 | Y |
| 8 | D4-8 | d4-adjustment-and-analysis-gap-closure | 重要产品毛利分析（复用现有计算） | gap | D4-6至D4-11营业收入 - 分析程序（Leap应对措施-分析程序）.xlsx | 重要产品毛利分析D4-8 | Y |
| 9 | D4-9 | d4-9-customer-structure-bidirectional-writeback | 重要客户结构分析 | 已有owner | D4-6至D4-11营业收入 - 分析程序（Leap应对措施-分析程序）.xlsx | 重要客户结构分析D4-9 | Y |
| 10 | D4-10 | d4-price-analysis-writeback-linkage | 重要客户销售价格分析 | 已有owner | D4-6至D4-11营业收入 - 分析程序（Leap应对措施-分析程序）.xlsx | 重要客户销售价格分析D4-10 | Y |
| 11 | D4-11 | d4-price-analysis-writeback-linkage | 产品销售价格分析 | 已有owner | D4-6至D4-11营业收入 - 分析程序（Leap应对措施-分析程序）.xlsx | 产品销售价格分析D4-11 | Y |
| 12 | D4-12 | d4-adjustment-and-analysis-gap-closure | 合同检查（复用卡片/OCR/AI） | gap | D4-12 营业收入-合同检查（Leap-常规程序）.xlsx | 合同检查表D4-12 | Y |
| 13 | D4-13 | d4-inspection-writeback-formula-io | ERP账面金额核对 | d-cycle扩展 | D4-13至D4-20主营业务收入-检查（Leap应对措施-检查）.xlsx | 营业收入账面金额与ERP系统核对记录D4-13 | Y |
| 14 | D4-14 | d4-inspection-writeback-formula-io | 发生检查 | d-cycle扩展 | D4-13至D4-20主营业务收入-检查（Leap应对措施-检查）.xlsx | 营业收入发生检查表D4-14 | Y |
| 15 | D4-15 | d4-inspection-writeback-formula-io | 完整性检查 | d-cycle扩展 | D4-13至D4-20主营业务收入-检查（Leap应对措施-检查）.xlsx | 营业收入完整性检查表D4-15 | Y |
| 16 | D4-16 | d4-inspection-writeback-formula-io | 出口收入电子口岸核对 | d-cycle扩展 | D4-13至D4-20主营业务收入-检查（Leap应对措施-检查）.xlsx | 出口收入电子口岸系统核对D4-16 | Y |
| 17 | D4-17 | d4-cutoff-return-writeback-formula-io | 截止测试（账到单据） | d-cycle扩展 | D4-13至D4-20主营业务收入-检查（Leap应对措施-检查）.xlsx | 营业收入截止测试（账到单据）D4-17 | Y |
| 18 | D4-18 | d4-cutoff-return-writeback-formula-io | 截止测试（单据到账） | d-cycle扩展 | D4-13至D4-20主营业务收入-检查（Leap应对措施-检查）.xlsx | 营业收入截止测试（单据到账）D4-18 | Y |
| 19 | D4-19 | d4-cutoff-return-writeback-formula-io | 销售折扣与折让检查 | d-cycle扩展 | D4-13至D4-20主营业务收入-检查（Leap应对措施-检查）.xlsx | 销售折扣与折让检查D4-19 | Y |
| 20 | D4-20 | d4-cutoff-return-writeback-formula-io | 销售退货检查 | d-cycle扩展 | D4-13至D4-20主营业务收入-检查（Leap应对措施-检查）.xlsx | 销售退货检查表 D4-20 | Y |
| 21 | D4-21 | d4-21-24-oo-bidirectional-and-cross-sheet-formula | 关联方销售情况及价格分析 | d-cycle扩展 | D4-21营业收入-关联方检查（Leap-常规程序）.xlsx | 关联方销售情况及价格分析D4-21 | Y |
| 22 | D4-22 | d4-21-24-oo-bidirectional-and-cross-sheet-formula | IPO重要指标分析表 | d-cycle扩展 | D4-22至D4-32营业收入-IPO 上市 新三板 重组 舞弊应对.xlsx | 重要指标分析表D4-22 | Y |
| 23 | D4-23 | d4-21-24-oo-bidirectional-and-cross-sheet-formula | 收入与开具发票金额比较分析 | d-cycle扩展 | D4-22至D4-32营业收入-IPO 上市 新三板 重组 舞弊应对.xlsx | 收入与开具发票金额比较分析D4-23 | Y |
| 24 | D4-24 | d4-21-24-oo-bidirectional-and-cross-sheet-formula | 第三方回款检查 | d-cycle扩展 | D4-22至D4-32营业收入-IPO 上市 新三板 重组 舞弊应对.xlsx | 第三方回款检查D4-24 | Y |
| 25 | D4-25 | d4-ipo-fraud-writeback-formula | IPO经销商检查 | d-cycle扩展 | D4-22至D4-32营业收入-IPO 上市 新三板 重组 舞弊应对.xlsx | 经销商检查D4-25 | Y |
| 26 | D4-26 | d4-ipo-fraud-writeback-formula | 境外销售收入检查 | d-cycle扩展 | D4-22至D4-32营业收入-IPO 上市 新三板 重组 舞弊应对.xlsx | 境外销售收入检查D4-26 | Y |
| 27 | D4-27 | d4-ipo-fraud-writeback-formula | 识别未披露关联方 | d-cycle扩展 | D4-22至D4-32营业收入-IPO 上市 新三板 重组 舞弊应对.xlsx | 识别未披露的关联方D4-27 | Y |
| 28 | D4-28 | d4-ipo-fraud-writeback-formula | 客户信息核查清单 | d-cycle扩展 | D4-22至D4-32营业收入-IPO 上市 新三板 重组 舞弊应对.xlsx | 客户信息核查清单D4-28 | Y |
| 29 | D4-29 | d4-ipo-fraud-writeback-formula | 客户信息检查表 | d-cycle扩展 | D4-22至D4-32营业收入-IPO 上市 新三板 重组 舞弊应对.xlsx | 客户信息检查表D4-29 | Y |
| 30 | D4-30 | d4-ipo-fraud-writeback-formula | 客户访谈记录汇总表 | d-cycle扩展 | D4-22至D4-32营业收入-IPO 上市 新三板 重组 舞弊应对.xlsx | 客户访谈记录汇总表D4-30 | Y |
| 31 | D4-31 | d4-ipo-fraud-writeback-formula | 客户访谈记录 | d-cycle扩展 | D4-22至D4-32营业收入-IPO 上市 新三板 重组 舞弊应对.xlsx | 客户访谈记录 D4-31 | Y |
| 32 | D4-32 | d4-ipo-fraud-writeback-formula | 客户供应商资金流水检查 | d-cycle扩展 | D4-22至D4-32营业收入-IPO 上市 新三板 重组 舞弊应对.xlsx | 客户、供应商等资金流水检查D4-32 | Y |
| 33 | D4-33 | d4-33-36-writeback-formula-and-io-closure | 其他业务毛利率分析 | d-cycle扩展 | D4-33至D4-36 其他业务收入.xlsx | 其他业务毛利率分析表D4-33 | Y |
| 34 | D4-34 | d4-33-36-writeback-formula-and-io-closure | 其他业务收入合同测算 | d-cycle扩展 | D4-33至D4-36 其他业务收入.xlsx | 其他业务收入合同测算表D4-34 | Y |
| 35 | D4-35 | d4-33-36-writeback-formula-and-io-closure | 其他业务收入检查 | d-cycle扩展 | D4-33至D4-36 其他业务收入.xlsx | 其他业务收入检查表D4-35 | Y |
| 36 | D4-36 | d4-33-36-writeback-formula-and-io-closure | 其他业务收入截止性测试 | d-cycle扩展 | D4-33至D4-36 其他业务收入.xlsx | 其他业务收入截止性测试D4-36 | Y |

---

## 汇总统计

| 类别 | 个数 | wp_code |
|------|------|---------|
| 专属（d4-dual-mode-formula-governance） | 1 | D4-1 |
| 已有owner | 10 | D4-2, D4-3, D4-5, D4-6, D4-7, D4-9, D4-10, D4-11 |
| d-cycle扩展（已分配owner） | 22 | D4-13..D4-24, D4-25..D4-32, D4-33..D4-36 |
| gap（owner=d4-adjustment-and-analysis-gap-closure） | 3 | D4-4, D4-8, D4-12 |
| **合计（分母）** | **36** | — |

> **gap 三项的 owner spec `d4-adjustment-and-analysis-gap-closure` 已在 `.kiro/specs/` 存在**（design.md 1132B / requirements.md 1430B / tasks.md 1261B），非空壳，可据此推进缺口收口。

---

## D4-4 / D4-8 / D4-12 源模板实证摘要

### D4-4 — 营业收入调整分录汇总

- **所在 workbook**：`D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx`
- **sheet 名**：`营业收入调整分录汇总D4-4`
- **结构**：10列，表头行（第3行）：
  `调整事项说明 | 类别（报表调整/账项调整/其他） | 报表项目 | 科目名称 | 附注项目 | …… | 借方调整金额 | 贷方调整金额 | 索引 | 备注`
- **行集**：预留空行（约20行），无硬编码行；底部提示"仅列示与本报表项目相关的审计调整，项目组可根据项目实际情况选择是否使用该底稿"
- **边界**：复用 A13 集中调整分录平台能力，只收口身份键/公式 mask/双向同步，不重新实现调整分录逻辑

### D4-8 — 重要产品毛利分析

- **所在 workbook**：`D4-6至D4-11营业收入 - 分析程序（Leap应对措施-分析程序）.xlsx`
- **sheet 名**：`重要产品毛利分析D4-8`
- **结构**：24列，两级表头，行标签列（A列），含：
  - 本期数（10列）：`销量 | 平均单价 | 金额 | 销量 | 平均单位成本 | 金额 | 毛利 | 毛利率`（分营业收入/营业成本两组）
  - 上期数（10列）：同构
  - 本期比上期增减变动分析（4列）：`平均单价 | 单位成本 | 主营业务收入 | 主营业务成本 | 毛利 | 毛利率`
  - 备注（1列）
- **行集**：按产品维度动态扩展（`产品A：` 标签行引导，无固定行数）
- **边界**：复用现有月度毛利/毛利率计算逻辑，只收口产品维度身份键、公式 preset/custom、双向同步

### D4-12 — 合同检查表

- **所在 workbook**：`D4-12 营业收入-合同检查（Leap-常规程序）.xlsx`
- **sheet 名**：`合同检查表D4-12`
- **结构**：11列（A=行标签，B..K=合同1..10），行标签列：
  `索引号 | 合同编号 | 交易对方名称 | 合同签订日期 | 服务内容/提供产品名称 | 合同金额 | 交货时间/服务期间 | 交货方式/提供服务方式 | 结算方式 | 结算时间 | 质量保证条款 | 销售退回条款 | 违约条款 | 特殊约定 | 订立双方是否签字 | 订立双方是否盖章 | 时段法/时点法 | 验收条款 | 收入确认时间 | 表明控制权转移的单据名称 | 是否涉及特定交易（附质量保证/附销售退回/主要责任人和代理人/售后回购/分期收款/寄售商品/以旧换新/授予知识产权等） | 结论`
- **行集**：23行标签（固定骨架），合同列动态扩展（B..K 为合同1..10，可按需增加）
- **边界**：复用合同卡片/OCR/AI 平台能力，只收口合同身份键、双向同步、公式 mask

---

## 备注

1. **`_index.json` 中所有 D4 条目的 `wp_code` 均为 `"D4"`（父级）**，未细化到 D4-x。实际 wp_code 由 sheet 名后缀（如 `D4-1`、`D4-12`）确定，运行时 `wp_template_finder` 按 sheet 名解析。
2. `D4-5` 模板文件独立存在（`D4-5 营业收入-会计政策（Leap-常规程序）.xlsx`），与 D4-6~D4-11 分属不同 workbook，但均在 `D/` 目录下。
3. `D4-21` 有独立 workbook（`D4-21营业收入-关联方检查（Leap-常规程序）.xlsx`），D4-22~D4-32 共享一个多 sheet workbook。
4. `D4-22A`（IPO 程序表）出现在 D4-22~D4-32 workbook 的 `程序表D4-22A` sheet，属于程序表（不计入分母）。
