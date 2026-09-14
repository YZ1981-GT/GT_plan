# Implementation Plan: F/G/H/I 循环逐 sheet 内容完整性深度打磨

## Overview

对照各循环源模板，按 design.md 的「打磨配方 + Sheet 5 类处置矩阵（A 明细/检查/测试表 · B 审定表 · C 附注披露 · D 调整分录 · E 导航/程序/静态文档豁免）」，逐 entry 打磨 F/G/H/I 共 512 个 sheet 组件（现 7 达标 / 505 待打磨）。

**每 entry 任务的验收（叶子任务通用 DoD）**：
- 该 entry 全部 A/B/C/D 类 sheet 满足六项标准（缺什么补什么，已有不重复）；E 类 sheet 仅补审计目标/编制提示（若源模板有）。
- 审计说明/结论走 `checklist_responses`，item_id `{code}-{sheet}-audit-note|-audit-conclusion`（多变体加后缀），onMounted 恢复 + saveImmediate 落库。
- 仅 F 循环接 🤖AI（已有 AiGenerate composable）；G/H/I 纯 textarea。
- 只用 str_replace 改 .vue；改动文件 get_diagnostics 零错误 + Vite transform 200。
- ref-unwrap 契约 / import 深度不回归。

**清单标注**（来自实测）：每 sheet 后 5 位 `OA·GD·AN·AC·TT` 表示现状（1=已有 0=缺）。施工只补 0 的项。

## Tasks

- [x] 0. 基础设施：验收扫描脚本 + 白名单
  - [x] 0.1 新增 `backend/scripts/check/check_fghi_sheet_completion.py`：按 Sheet 分类矩阵扫描 f/g/h/i 组件，校验 A/B/C/D 类 sheet 含 objective-alert + guidance-details + `-audit-note` + `-audit-conclusion`（A/B 另需 tab-toolbar+GtIndexChip）；E 类（Index/Directory/Procedure/Ref）白名单豁免；输出缺项报告，`--strict` 非零退出；Windows `sys.stdout.reconfigure(utf-8)` 防 GBK 崩。同时校验 P2（item_id 唯一）/P7（G/H/I 无新增 AI 按钮）。
    - _Requirements: 6.2, 9.1, 9.2, 9.3_
  - [x] 0.2 核对 `checklist_responses.py` item_id 前缀白名单覆盖 F/G/H/I 各 entry（`F1-`/`F2-`/`F3-`/`F4-`/`F5-`/`G1-`~`G14-`/`H1-`~`H10-`/`I1-`~`I6-`）；缺失前缀补 `elif ... pass` 分支（存 remark、conclusion=null）。
    - _Requirements: 4.2_

- [x] 1. F1 预付款项（GtF1Prepayment，f1/，11 sheet，3 已达标）
  - [x] 1.1 打磨 f1/ 待处理 sheet：Adjustment`01001` Analysis`11100` ComprehensiveCheck`11100` ConfirmationProcedure`00000`(E类) Detail`11101` DisclosureListed`01000` DisclosureSoe`01000` Procedure`00000`(E类)。已达标跳过：Adjudication/LongTerm/RelatedParty。对照 F 存货循环底稿模板库 F1 预付款项章节补主表字段/账龄/关联方列。
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 4.5, 5.1, 6.1_

- [x] 2. F2 存货主表（GtF2InventoryMain/Valuation/StocktakeBundle，f2/，34 sheet，1 已达标）
  - [x] 2.1 打磨 f2/core：AdjudicationBlockTable`00000` Adjustment`01001` DetailSummary`11001` DisclosureListed`01001` DisclosureSoe`01001` Procedure`00000`(E类)。已达标跳过 Adjudication。
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 4.5, 5.1_
  - [x] 2.2 打磨 f2/analysis：CostComparison/OverallAnalysis/Policy/ProductionSales `11001`（补 AC+TT）。
    - _Requirements: 1.1, 2.1, 4.1, 5.1_
  - [x] 2.3 打磨 f2/detail + inspection：F2DetailSheet`11001` F2CutoffSheet`11001`（补 AC+TT；截止跨期标注保留）。
    - _Requirements: 1.1, 2.1, 3.3, 4.1, 5.1_
  - [x] 2.4 打磨 f2/stocktake：Plan`11000` Questionnaire`01000` Reconcile`11101` Rollforward`11101` SampleResult`01101` Summary`01000`（监盘要素/盘点差异保留，补缺项）。
    - _Requirements: 1.1, 2.1, 3.3, 4.1, 5.1_
  - [x] 2.5 打磨 f2/valuation：CostAllocation/DirectLaborAnalysis/ImpairmentReversal/ObsoleteInventory/OverheadDetail/ProductionCostDetail/RelatedPurchase `11101`、ImpairmentTest/SubcontractCheck `11001`、MaterialUsageCheck/PurchaseInboundCheck/StandardCostTest/ValuationAvg/ValuationFifo `00000`、F2ValuationTestSheet`01000`。跌价测试/可变现净值列对照源模板补全。
    - _Requirements: 1.1, 2.1, 3.1, 3.3, 4.1, 4.5, 5.1_

- [x] 3. F2 存货专项（GtF2InventorySpecial，f2-special/，18 sheet，1 已达标）
  - [x] 3.1 打磨 f2-special/contract：ContractCostCheck/ContractCostDetail/Impairment/LossContract `11101` ContractProcedure`11000`(E类)。
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 4.5, 5.1_
  - [x] 3.2 打磨 f2-special/ipo：CapacityEnergy/InterviewSummary/RelatedPartyInquiry/RelatedPartyMarket/SupplierChecklist `11001`、InterviewDetail/PurchasePrice `11101`、IpoProcedure`11000`(E类)、SupplierInfoCheck/SupplierStructure/UndisclosedParty/UnitPrice `11011`。已达标跳过 UnitConsumption。
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 4.5, 5.1_

- [x] 4. F3 应付票据（GtF3NotesPayable，f3-notes-payable/，10 sheet，1 已达标）
  - [x] 4.1 打磨 f3-notes-payable/：Adjustment`01001` Detail`11001` DisclosureListed`01000` DisclosureSOE`01000` InterestCalc`11011` OverdueCheck`11011` RelatedParty`11101` VoucherCheck`11010` F3VoucherCheckTable`00010`。已达标跳过 Adjudication。F3 有 useF3AiGenerate → 接 🤖AI。
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 4.5, 5.1_

- [x] 5. F4 应付账款（GtF4AccountsPayable，f4-accounts-payable/，11 sheet，0 达标）
  - [x] 5.1 打磨 f4-accounts-payable/：Adjudication`11110`(补TT) Adjustment`01000` Detail`11000` DisclosureListed`01000` DisclosureSOE`01000` LongOutstanding/RelatedParty/SubstantiveAnalysis/SupplierFinancing/UnrecordedCheck `11110`(补TT) VoucherCheck`11010`。补 AC 为主，Detail 补供应商/账龄列。
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.1_

- [x] 6. F5 主营业务成本（GtF5CostOfSales，f5-cost-of-sales/，8 sheet，1 已达标）
  - [x] 6.1 打磨 f5-cost-of-sales/：Adjustment`01001` Comparison/CostRollforward `11011` MajorAdjustment`00010` MonthlyDetail`11001` OtherCost/QuantityRecon `11101`。已达标跳过 Adjudication。
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 4.5, 5.1_

- [x] 7. F 循环 Playwright 实测
  - [x] 7.1 admin/admin123 登录 → 导航 F 存货底稿 → 抽验 F2 明细/跌价测试 + F1 明细 ≥2 sheet：审计目标/编制提示/审计说明/审计结论渲染 + console 0 error；`check_fghi_sheet_completion.py` F 循环段通过。
    - _Requirements: 8.1, 8.2, 8.3_

- [x] 8. G1 交易性金融资产（GtG1TradingFinancialAssets，g1/，16 sheet）
  - [x] 8.1 打磨 g1/：core Adjudication`11110`(补TT) Adjustment`11010` Detail`00000` DisclosureListed/SOE `11000`；classification 3×`11010`；inspection 6×`11010`；valuation 2×`11010`。补 AC+TT 为主，Detail 从零补公允价值/分类列。
    - _Requirements: 1.1, 2.1, 3.1, 3.3, 4.1, 5.1_

- [x] 9. G2 应收利息（GtG2InterestReceivable，g2/，9 sheet）
  - [x] 9.1 打磨 g2/：Adjudication/ECLCalc/InterestCalc/VoucherCheck `11011`(补AC)；BadDebtDetail/Detail/DisclosureListed/DisclosureSOE/OverdueCheck `11001`(补AC+TT)。
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.1_

- [x] 10. G3 应收股利（GtG3DividendReceivable，g3/，7 sheet）
  - [x] 10.1 打磨 g3/：Adjudication`00010` Adjustment`11000` CalcCheck`11010` Detail/DisclosureListed/DisclosureSOE `11000` OverdueCheck`11010`。补 OA/AN/AC/TT。
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.1_

- [x] 11. G4 债券投资（GtG4BondInvestmentMain/Ecl/Sppi，g4-bond-investment-*，19 sheet）
  - [x] 11.1 打磨 g4-bond-investment-main/：Adjudication`11110`(补TT) Adjustment/Detail `11000` Directory`00110`(E类) DisclosureListed/SOE `01000` Procedure`00000`(E类) InterestCalc`11010`。
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.1_
  - [x] 11.2 打磨 g4-bond-investment-ecl/：impairment 4×`11010`（补AC）；reference RefImpairmentGuidance/RefPdConversion `01000`(E类静态文档,仅补OA/GD)；VoucherCheck`11010`。
    - _Requirements: 1.1, 2.1, 4.1, 5.1, 9.2_
  - [x] 11.3 打磨 g4-bond-investment-sppi/：BusinessModel/SppiTest/InventoryReconciliation `11010` SecuritiesInventory`11110`（补AC+TT；SPPI 测试结构保留）。
    - _Requirements: 1.1, 2.1, 3.3, 4.1, 5.1_

- [x] 12. G5 长期应收款（GtG5LongTermReceivable，g5/，16 sheet，整循环 OA 缺）
  - [x] 12.1 打磨 g5/：core 6×`01000`(补OA/AN/AC/TT) Directory/Procedure `00000`(E类)；impairment ImpairmentCalc/StageClassification `01010` ReversalWriteoff`01000`；measurement EclPolicy/FactoringCheck `01000` InstallmentSales/LeaseAmortization `01010`；voucher `01010`。全 sheet 补审计目标。
    - _Requirements: 1.1, 1.2, 2.1, 3.1, 4.1, 5.1_

- [x] 13. G6 其他债权投资（GtG6OtherBondMain/Ecl/Sppi，g6-other-bond-investment-*，19 sheet）
  - [x] 13.1 打磨 g6-other-bond-investment-main/：Adjudication`01110`(补OA/TT) Adjustment`01000` BadDebtDetail`01010` Detail`01000` Directory`00110`(E类) DisclosureListed/SOE `01000` Procedure`00000`(E类)。
    - _Requirements: 1.1, 1.2, 2.1, 3.1, 4.1, 5.1_
  - [x] 13.2 打磨 g6-other-bond-investment-ecl/：4×`01010` VoucherCheck`01011`（补OA/AN/AC）。清理根目录重复 entry 文件 GtG6OtherBondEcl.vue vs GtG6OtherBondInvestmentEcl.vue（确认哪个在 registry，另一个若为死代码标注不删仅记录）。
    - _Requirements: 1.1, 1.2, 2.1, 4.1, 5.1_
  - [x] 13.3 打磨 g6-other-bond-investment-sppi/：BusinessModel/FairValueTest/InventoryRollForward/SecuritiesInventory/InterestCalculation `01010` SppiTest`01000`（补OA/AC）。
    - _Requirements: 1.1, 1.2, 2.1, 3.3, 4.1, 5.1_

- [x] 14. G7 长期股权投资（GtG7LongTermEquityMain/Method/Subsidiary，g7-long-term-equity-*，22 sheet）
  - [x] 14.1 打磨 g7-long-term-equity-main/：Adjudication`11110`(补TT) Adjustment/Detail `11000` Directory`00100`(E类) Procedure`00000`(E类) DisclosureListed/SOE `11000`。
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.1_
  - [x] 14.2 打磨 g7-long-term-equity-method/：calculation 3×`01010` impairment 2×`01010` info AccountingPolicy`01010` BasicInfo`11000` FinancialInfo`01000`（补OA/AN/AC；权益法计算结构保留）。
    - _Requirements: 1.1, 1.2, 2.1, 3.3, 4.1, 5.1_
  - [x] 14.3 打磨 g7-long-term-equity-subsidiary/：disposal DisposalPackage/Single `11010` initial 3×`01010` subsequent `01010` voucher `11010`（补OA/AC）。
    - _Requirements: 1.1, 1.2, 2.1, 3.1, 4.1, 5.1_

- [x] 15. G8 其他权益工具投资（GtG8OtherEquityInstruments，g8/，11 sheet，整循环 OA 缺）
  - [x] 15.1 打磨 g8/：core Adjudication`01100`(补OA/AC/TT) Directory`01000`(E类) rest `00000`；valuation DesignationCheck/FairValueTest `01010`；voucher `00000`。多 sheet 从零补。
    - _Requirements: 1.1, 1.2, 2.1, 3.1, 4.1, 5.1_

- [x] 16. G9 其他非流动金融资产（GtG9OtherNoncurrentFinancial，g9/，11 sheet）
  - [x] 16.1 打磨 g9/：core Adjudication`11100`(补AC/TT) Adjustment/Detail/DisclosureBase `11000` Directory`01000`(E类) DisclosureListed/SOE/Procedure `00000`；valuation FairValueTest/L3Reconciliation `01010`；voucher `11000`。
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.1_

- [x] 17. G10 交易性金融负债（GtG10TradingFinancialLiabilities，g10/，13 sheet，整循环 OA 缺）
  - [x] 17.1 打磨 g10/：classification ClassificationCheck/FairValueTest `01010` L3Reconciliation`01000`；core Adjudication`01100`(补OA/AC/TT) Adjustment/Detail/Directory/DisclosureBase `01000` DisclosureListed/SOE/Procedure `00000`；voucher DerivativeCheck`01010` VoucherCheck`01000`。全补 OA。
    - _Requirements: 1.1, 1.2, 2.1, 3.1, 4.1, 5.1_

- [x] 18. G11 投资收益（GtG11InvestmentIncome，g11/，10 sheet，最弱）
  - [x] 18.1 打磨 g11/：ReturnRateAnalysis`00010` Adjudication`01110`(补OA) Directory`01000`(E类) 其余 `00000` 从零补。损益类发生额取数保留。
    - _Requirements: 1.1, 1.2, 2.1, 3.1, 4.1, 5.1_

- [x] 19. G12 净敞口套期收益（GtG12NetHedgeGains，g12/，10 sheet）
  - [x] 19.1 打磨 g12/：Adjudication`11110`(补TT) Adjustment/DisclosureListed/SOE/HedgeDetail/VoucherCheck `11000` Directory`01000`(E类) Procedure`00000`(E类)；FairValueTest/NetExposureCheck `01010`。
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.1_

- [x] 20. G13 公允价值变动损益（GtG13FairValueChanges，g13/，7 sheet）
  - [x] 20.1 打磨 g13/：Adjudication`01110`(补OA) Adjustment/Detail `11000` Directory/DisclosureListed/DisclosureSOE `01000` Procedure`00000`(E类)。
    - _Requirements: 1.1, 1.2, 2.1, 3.1, 4.1, 5.1_

- [x] 21. G14 信用减值损失（GtG14CreditImpairmentLoss，g14/，7 sheet）
  - [x] 21.1 打磨 g14/：Adjudication`11110`(补TT) Adjustment/Detail `11000` Directory`01000`(E类) DisclosureListed/SOE `11000` Procedure`00000`(E类)。
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.1_

- [x] 22. G 循环 Playwright 实测
  - [x] 22.1 admin/admin123 → 导航 G 投资底稿 → 抽验 G4 债券明细/SPPI + G1 交易性金融资产 ≥2 sheet：六项渲染 + console 0 error；`check_fghi_sheet_completion.py` G 循环段通过。
    - _Requirements: 8.1, 8.2, 8.3_

- [x] 23. H1 固定资产（GtH1FixedAssets，h1/，25 sheet）
  - [x] 23.1 打磨 h1/：core Adjudication`01110`(补OA) 其余 `01000`~`01100`；depreciation DepreciationAlloc`11010` Straight`01110` Impair/Multi `01100`；impairment Impairment`01110` Recoverable`01000`；inspection FinanceLease/OperatingLease/RelatedParty/TitleBuilding/TitleVehicle `11010`、AdditionCheck/DisposalCheck/IdleCheck `01010`、PolicyCheck`01110`；stocktake `01000`/Summary`01010`。补 OA/AC/TT + 折旧原值累计折旧减值列。
    - _Requirements: 1.1, 1.2, 2.1, 3.1, 3.3, 4.1, 5.1_

- [x] 24. H2 在建工程（GtH2ConstructionInProgress，h2/，20 sheet）
  - [x] 24.1 打磨 h2/：Adjudication`01110`(补OA)；Analysis/CostComparison/TransferCheck `01100`；Impairment`01010` StocktakeCheck`01010`；rest `01000`。补 OA/AN/AC/TT + 转固检查列。
    - _Requirements: 1.1, 1.2, 2.1, 3.1, 4.1, 5.1_

- [x] 25. H3 投资性房地产（GtH3InvestmentProperty，h3/，21 sheet，整循环 OA 缺）
  - [x] 25.1 打磨 h3/：AdjudicationCost/Fair/DetailCost/Fair/depreciation/fairvalue/impairment/rental `00100`；inspection AdditionCost/AdditionFair/RelatedParty `00110`；DisclosureListed/Soe/Index `01000`；Adjustment/PolicyCheck `00000`。全补 OA + 成本/公允双模式说明。
    - _Requirements: 1.1, 1.2, 2.1, 3.1, 3.3, 4.1, 5.1_

- [x] 26. H4 工程物资（GtH4EngineeringMaterials，h4/，12 sheet）
  - [x] 26.1 打磨 h4/：Adjudication`01110`(补OA)；Adjustment/Detail/AdditionCheck/DisposalCheck/RelatedParty/StocktakeCheck `01100`；disclosures/impairment/index `01000`。补 OA/AN/AC/TT。
    - _Requirements: 1.1, 1.2, 2.1, 3.1, 4.1, 5.1_

- [x] 27. H5 油气资产（GtH5OilGasAssets，h5/，23 sheet，整循环 OA 缺）
  - [x] 27.1 打磨 h5/：Adjudication/Adjustment/Detail/Impairment/lease/most inspection `01100`；Analysis/Recoverable/PolicyCheck `01010`；disclosures/index/depletion/stocktake `01000`。全补 OA + 折耗单位产量法列（行业守卫保留）。
    - _Requirements: 1.1, 1.2, 2.1, 3.1, 3.3, 4.1, 5.1_

- [x] 28. H6 固定资产清理（GtH6AssetDisposalClearing，h6/，7 sheet）
  - [x] 28.1 打磨 h6/：Adjudication`01110`(补OA) Adjustment`01100` Detail`11100` Check`11100` disclosures/index `01000`。补 OA/AC/TT。
    - _Requirements: 1.1, 1.2, 2.1, 3.1, 4.1, 5.1_

- [x] 29. H7 生物资产（GtH7BiologicalAssets，h7/，26 sheet，H 循环最佳）
  - [x] 29.1 打磨 h7/：core AdjudicationCost/Fair/Adjustment/DetailCost/Fair/depreciation/fairvalue `11101`(补AC) Analysis`11011`(补AC) DisclosureListed/Soe `11001` Index`00000`(E类)；impairment Impairment`11100` Recoverable`11010`；inspection AdditionCost/Fair/DisposalCost/Fair/RelatedParty `11100`、PolicyCheck`11010`、TransferReview`11000`；production/stocktake `11000`、StocktakeSummary`11010`。补 AC 为主（成本/公允双计量加变体后缀）。
    - _Requirements: 1.1, 2.1, 3.3, 4.1, 4.4, 5.1_

- [x] 30. H8 使用权资产（GtH8RightOfUseAssets，h8/，19 sheet，整循环 OA 缺，TT 全有）
  - [x] 30.1 打磨 h8/：Adjudication`01111`(补OA) Detail`11001` 其余 core/depreciation/impairment/inspection/measurement `01001` LeaseIdentification`01101` Index`01000`(E类)。全补 OA + 部分补 AC/AN。
    - _Requirements: 1.1, 1.2, 2.1, 3.1, 4.1, 5.1_

- [x] 31. H9 租赁负债（GtH9LeaseLiabilities，h9/，9 sheet）
  - [x] 31.1 打磨 h9/：Adjudication`01110`(补OA) Adjustment`01100` Detail`10110` FinanceCost`00110` RelatedParty`01110` Amortization/disclosures `01000` Index`00000`(E类)。补 OA/GD/AN/AC/TT。
    - _Requirements: 1.1, 1.2, 2.1, 3.1, 4.1, 5.1_

- [x] 32. H10 资产处置收益（GtH10AssetDisposalIncome，h10/，9 sheet）
  - [x] 32.1 打磨 h10/：Adjudication`01110`(补OA) Detail`00010` Check`00010` Directory`01000`(E类) Adjustment/DisclosureBase/Listed/SOE/Procedure `00000`。多 sheet 从零补（Procedure/Disclosure 按类处置）。
    - _Requirements: 1.1, 1.2, 2.1, 3.1, 4.1, 5.1_

- [x] 33. H 循环 Playwright 实测
  - [x] 33.1 admin/admin123 → 导航 H 固定资产底稿 → 抽验 H1 明细/折旧 + H7 生物资产 ≥2 sheet：六项渲染 + console 0 error；`check_fghi_sheet_completion.py` H 循环段通过。
    - _Requirements: 8.1, 8.2, 8.3_

- [x] 34. I1 无形资产（GtI1IntangibleAssets，i1/，16 sheet）
  - [x] 34.1 打磨 i1/：amortization NoImpair/WithImpair `01110` Alloc`01000`；core Adjudication`00110` Adjustment`01100` Detail`00000` disclosures/index `01000`；impairment ImpairmentTest/RecoverableTest `01100`；inspection 5×`01010`。补 OA/AN/AC/TT + 摊销原值列。
    - _Requirements: 1.1, 1.2, 2.1, 3.1, 4.1, 5.1_

- [x] 35. I2 开发支出（GtI2DevelopmentExpenditure，i2/，19 sheet，17/19 空壳）
  - [x] 35.1 打磨 i2/（重点·从零补）：17 个 `00000` sheet 比照 i1 同构 sheet 从零补六项内容；Adjudication`00100` Index`01000`(E类)。研发资本化/费用化归集结构对照 I 无形资产循环底稿模板库研发章节 + B23-8/C9 研发控制模板。
    - _Requirements: 1.1, 1.2, 2.1, 3.1, 3.3, 4.1, 5.1, 7.1_

- [x] 36. I3 商誉（GtI3Goodwill，i3/，11 sheet）
  - [x] 36.1 打磨 i3/：Adjudication`11111` Adjustment`11111` InitialValue`11111` ImpairmentTest/RecoverableTest `11111` disclosures/index `11111` Detail/TargetedCheck/ReviewProcess `11111`。全部 OA/GD/AN/AC/TT + 商誉减值测试 CGU 列已完备（i3-goodwill spec 已实现全部内容）。get_diagnostics 12文件零错误。
    - _Requirements: 1.1, 1.2, 2.1, 3.1, 3.3, 4.1, 5.1_

- [x] 37. I4 长期待摊费用（GtI4LongTermPrepaid，i4/，10 sheet）
  - [x] 37.1 打磨 i4/：Adjudication`01110`(补OA) PolicyCheck/TargetedCheck `01010` amortization/adjustment/detail/disclosures/index `01000`。补 OA/AN/AC/TT + 摊销列。
    - _Requirements: 1.1, 1.2, 2.1, 3.1, 4.1, 5.1_

- [x] 38. I5 其他非流动资产（GtI5OtherNoncurrentAssets，i5/，7 sheet）
  - [x] 38.1 打磨 i5/：Adjudication`01110`(补OA) TargetedCheck`01010` rest `01000`。补 OA/AN/AC/TT。
    - _Requirements: 1.1, 1.2, 2.1, 3.1, 4.1, 5.1_

- [x] 39. I6 研发费用（GtI6ResearchDevelopmentExpense，i6/，9 sheet）
  - [x] 39.1 打磨 i6/：Adjudication`01110`(补OA) TargetedCheck`01010` adjustment/detail/disclosures/index/cutoff `01000`。补 OA/AN/AC/TT + 研发费用归集/加计扣除列（结合研发特点）。
    - _Requirements: 1.1, 1.2, 2.1, 3.1, 3.3, 4.1, 5.1_

- [x] 40. I 循环 Playwright 实测
  - [x] 40.1 admin/admin123 → 导航 I 无形资产底稿 → 抽验 I1 明细/摊销 + I6 研发费用（或 I2 补全后）≥2 sheet：六项渲染 + console 0 error；`check_fghi_sheet_completion.py` I 循环段通过。
    - _Requirements: 8.1, 8.2, 8.3_

- [x] 41. 全局最终验证
  - [x] 41.1 `check_fghi_sheet_completion.py --strict` 全 F/G/H/I 通过（P1/P2/P6/P7）；`check_wp_ref_contract.py --strict` exit 0（P3）；`fix_wp_composables_import_depth.py --check` 通过（P4）；全改动 .vue 无 U+FFFD（P8）。
    - _Requirements: 6.2, 6.3, 6.5, 9.1_
  - [x] 41.2 前端 vitest + fast-check 持久化往返幂等（P5，F/G/H/I 各 1 代表 sheet，numRuns=20）；全改动文件 get_diagnostics 零错误汇总。
    - _Requirements: 4.2, 4.3, 6.5_

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["0.1", "0.2"] },
    { "id": 1, "tasks": ["1.1", "2.1", "2.2"] },
    { "id": 2, "tasks": ["2.3", "2.4", "2.5"] },
    { "id": 3, "tasks": ["3.1", "3.2", "4.1"] },
    { "id": 4, "tasks": ["5.1", "6.1"] },
    { "id": 5, "tasks": ["7.1"] },
    { "id": 6, "tasks": ["8.1", "9.1", "10.1"] },
    { "id": 7, "tasks": ["11.1", "11.2", "11.3"] },
    { "id": 8, "tasks": ["12.1", "13.1", "13.2"] },
    { "id": 9, "tasks": ["13.3", "14.1", "14.2"] },
    { "id": 10, "tasks": ["14.3", "15.1", "16.1"] },
    { "id": 11, "tasks": ["17.1", "18.1", "19.1"] },
    { "id": 12, "tasks": ["20.1", "21.1"] },
    { "id": 13, "tasks": ["22.1"] },
    { "id": 14, "tasks": ["23.1", "24.1", "25.1"] },
    { "id": 15, "tasks": ["26.1", "27.1", "28.1"] },
    { "id": 16, "tasks": ["29.1", "30.1", "31.1"] },
    { "id": 17, "tasks": ["32.1"] },
    { "id": 18, "tasks": ["33.1"] },
    { "id": 19, "tasks": ["34.1", "35.1", "36.1"] },
    { "id": 20, "tasks": ["37.1", "38.1", "39.1"] },
    { "id": 21, "tasks": ["40.1"] },
    { "id": 22, "tasks": ["41.1", "41.2"] }
  ]
}
```

## Notes

- 源模板：`基础数据/致同通用审计程序及底稿模板（2025年修订）/BCD类底稿md/{F存货|G投资|H固定资产|I无形资产}循环/*循环底稿模板库.md`（研发另见 I 循环 B23-8/C9 模板）
- 蓝本组件：`e1/E1TabCashDetail.vue`（配方）、`e1/E1TabIpoSpecial.vue`（多变体 SHEET_META）
- 并发 ≤3、stagger 5s；每 entry 完成即 get_diagnostics + Vite transform 200
- E 类（Index/Directory/Procedure/ConfirmationProcedure/Ref*）豁免主表补列 + 审计说明/结论，仅在源模板有时补 OA/GD
- 仅 F 循环接 🤖AI（useF2/F2Valuation/F2Stocktake/F2Special/F3AiGenerate）；G/H/I 纯 textarea
- 只用 str_replace，禁 PowerShell（防 UTF-8 损坏）
