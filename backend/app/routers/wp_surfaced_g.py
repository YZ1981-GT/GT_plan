"""G 循环底稿公式 surfacing 目录（与各 useG{n}* composable 同源，不臆造）。

对齐 E1 标准（wp_formula.py::_E1_SHEET_FORMULAS）与 wp_surfaced_d.py / wp_surfaced_f.py：
把 G 循环各专属组件底稿（数据存 checklist_responses、无 wp_formula 网格记录）的
取数/计算/逻辑审核公式，以只读条目 surface 到公式管理中心，供审计师查阅每张 sheet
的公式逻辑（可追溯来源 composable / 函数名 / sheet）。

每条公式均可在对应前端 composable 中找到依据（calc 纯函数 / 跨 sheet 键 / TB 核对 /
合计聚合）；找不到依据的 sheet 不写（宁缺勿造）。

覆盖（科目方向 + 权威来源 composable，科目码取自各 g{n}Constants / g{n}AdjudicationItems）：
- G1 交易性金融资产（借方 1501）  ← useG1TraFinFormulaEngine / useG1Adjudication / useG1Detail
- G2 应收利息（借方 1132）        ← useG2IntRecFormulaEngine / useG2Adjudication / useG2ECLCalc
- G3 应收股利（借方 1131）        ← useG3DivRecFormulaEngine / useG3Adjudication
- G4 债权投资（借方 1501/减值 1502）← useG4MainFormulaEngine / useG4MainAdjudication /
                                       useG4MainInterestCalc / useG4EclImpairmentCalc
- G5 长期应收款（借方 1531）      ← useG5FormulaEngine / useG5LeaseAmortization / useG5InstallmentSales
- G6 其他债权投资（借方 1503，FVOCI）← useG6OthBonFormulaEngine / useG6EclImpairmentCalc
- G7 长期股权投资（借方 1511）    ← useG7FormulaEngine / useG7EquityMethodFormulaEngine /
                                     useG7SubFormulaEngine（权益法 / 成本法 / 长投减值三组）
- G8 其他权益工具投资（借方 1503，FVOCI）← useG8FormulaEngine / useG8Adjudication
- G9 其他非流动金融资产（借方 1519）← useG9FormulaEngine
- G10 交易性金融负债（贷方 2101）  ← useG10FormulaEngine / useG10Adjudication / useG10L3Reconciliation
- G11 投资收益（损益 6111 发生额）  ← useG11FormulaEngine / useG11ReturnRateAnalysis
- G12 套期（净敞口套期收益 6103 发生额）← useG12FormulaEngine / useG12NetExposure
- G13 公允价值变动损益（6101 发生额）← useG13FormulaEngine
- G14 信用减值损失（6702 发生额）    ← useG14FormulaEngine / useG14Adjudication

科目方向铁律：金融资产借方期末 = 期初审定 + 借 − 贷；金融负债贷方期末 = 期初审定 + 贷 − 借；
损益类取发生额（无期初期末，本期/上期对比）。

格式：base_code -> sheet_code -> [(项目名, 公式, 分类, 说明, 来源), ...]
分类只用三种：
  - 取数     跨 sheet / 四表库 / 从明细带入
  - 计算     表间计算（审定=未审+AJE+RJE、变动额/率、合计、净值、期末余额、实际利率法摊余等）
  - logic_check  逻辑审核（TB 核对、审定↔明细勾稽、借贷平衡、连续性、跨源勾稽、阶段判定等）
"""
from __future__ import annotations

SheetFormula = tuple[str, str, str, str, str]  # (项目名, 公式, 分类, 说明, 来源)

CATALOG: dict[str, dict[str, list[SheetFormula]]] = {
    # ═══════════════════════════════════════════════════════════════════════
    # G1 交易性金融资产（借方 1501；公允价值计量，FVTPL）
    # ═══════════════════════════════════════════════════════════════════════
    "G1": {
        # G1-1 审定表（期初/期末 × 未审/调整/审定，投资成本/累计FV/账面余额×分类×品种）
        "G1-1": [
            ("审定数", "未审数 + 账项调整(AJE)", "计算",
             "各叶子行审定金额（calcAuditedAmount，期初/期末各自）", "useG1Adjudication / useG1TraFinFormulaEngine"),
            ("账面余额（公允价值）", "投资成本审定 + 累计公允价值变动审定（同分类同品种）", "计算",
             "carrying 层 = cost 层 + fv 层逐行合并", "useG1Adjudication"),
            ("小计 / 分类合计", "Σ 各品种叶子（成本/FV/账面各分类小计与总小计）", "计算",
             "leafKeysForClass / leafKeysForSection 汇总（calcSubtotal）", "useG1Adjudication"),
            ("账面余额合计", "carrying 小计 − 减:超过一年到期的部分", "计算",
             "footer-book-total（列报口径扣减 footer-over-one-year）", "useG1Adjudication"),
            ("变动额", "期末审定 − 期初审定", "计算",
             "本期较期初变动额（calcChangeAmount）", "useG1TraFinFormulaEngine"),
            ("变动率", "(期末审定 − 期初审定) ÷ 期初审定", "计算",
             "期初=0→''/N/A（calcChangeRate）；|变动率|>阈值高亮+原因必填（isChangeRateExceeding）",
             "useG1TraFinFormulaEngine"),
            ("从 G1-2 明细汇总带入", "按 分类×品种 SUM(G1-2 成本/累计FV 期初·期末)", "取数",
             "syncFromDetail（保留已有账项调整与原因分析）", "useG1Adjudication / g1CrossHelpers"),
            ("G1-3 调整分录回写", "监听 g1:adjustment-confirmed 按科目净额写入期末账项调整", "取数",
             "applyAdjustmentWriteback / allocateWriteback 分摊到投资成本行", "useG1Adjudication / g1AdjudicationItems"),
            ("试算平衡表数核对", "账面余额合计（审定） − 试算平衡表数(1501)", "logic_check",
             "审定合计与 TB 交易性金融资产核对（trialBalanceDiff；G1_ACCOUNT_CODE=1501，本地空时从 html_data.tb_values seed）",
             "useG1Adjudication"),
        ],
        # G1-2 明细表（借方科目）
        "G1-2": [
            ("期末余额", "期初审定 + 借方发生 − 贷方发生", "计算",
             "借方科目期末余额（calcDebitBalance / calcEndBalance）", "useG1Detail / useG1TraFinFormulaEngine"),
            ("审定数", "未审数 + AJE + RJE", "计算",
             "明细行审定金额（calcAuditedAmount）", "useG1TraFinFormulaEngine"),
        ],
        # G1-3 调整分录
        "G1-3": [
            ("借贷平衡校验", "Σ 借方金额 = Σ 贷方金额", "logic_check",
             "调整分录借贷平衡（isDebitCreditBalanced，容差 0.01）", "useG1Adjustment / useG1TraFinFormulaEngine"),
            ("按科目回写审定表", "确认后按 G1_ACCOUNT_CODE 匹配净额写入 G1-1 期末账项调整", "取数",
             "dispatch g1:adjustment-confirmed → applyAdjustmentWriteback", "useG1Adjustment"),
        ],
        # G1-5 投资收益测算
        "G1-5": [
            ("处置净收益", "(处置对价 − 成本) − 交易费用", "计算",
             "已实现收益 calcRealizedGain 后扣费 calcNetGain", "useG1IncomeCalc / useG1TraFinFormulaEngine"),
            ("计息天数", "截止日 − 起始日（日历日差）", "计算",
             "持有期利息计息天数（calcAccruedDays）", "useG1TraFinFormulaEngine"),
            ("应计利息", "本金 × 年化利率% ÷ 100 × 天数 ÷ 基数(365/360)", "计算",
             "债券类利息收入（calcInterestByBasis，Actual/365 默认）", "useG1TraFinFormulaEngine"),
        ],
        # G1-6 公允价值测试
        "G1-6": [
            ("公允价值", "数量 × 单位公允价值（数量<0 记 0）", "计算",
             "持仓公允价值（calcFairValue）", "useG1FairValueTest / useG1TraFinFormulaEngine"),
            ("面值合计", "单位面值 × 数量（保留 2 位）", "计算",
             "债券面值总计（calcFaceTotal）", "useG1TraFinFormulaEngine"),
            ("Level1 差异", "数量 × 活跃市场报价 − 账面价值", "logic_check",
             "第一层次公允价值与账面核对（calcLevel1Diff）", "useG1FairValueTest / useG1TraFinFormulaEngine"),
        ],
        # G1-12 有价证券盘点倒轧
        "G1-12": [
            ("盘点差异", "盘点实存 − 账面数量", "logic_check",
             "监盘数量核对（calcCountDiff）", "useG1CountReconciliation / useG1TraFinFormulaEngine"),
            ("资产负债表日实存", "盘点日实存 − 增加 + 减少", "计算",
             "盘点日→报表日倒轧（calcReconciliation）", "useG1CountReconciliation / useG1TraFinFormulaEngine"),
            ("期末数量", "期初 + 买入 − 卖出（不为负）", "计算",
             "持仓数量结存（calcClosingQuantity）", "useG1TraFinFormulaEngine"),
        ],
        # G1-13 凭证检查
        "G1-13": [
            ("借贷平衡校验", "Σ 借方金额 = Σ 贷方金额", "logic_check",
             "凭证检查借贷平衡（isDebitCreditBalanced）", "useG1VoucherCheck / useG1TraFinFormulaEngine"),
        ],
        # 附注披露
        "附注上市": [
            ("附注披露金额", "取自 G1-1 审定表（投资成本/累计公允价值变动/账面余额审定数）", "取数",
             "附注按分类取审定数（adjudicationForDisclosure）", "useG1DisclosureListed"),
            ("公允价值变动合计", "Σ G1-1 fv 层各叶子审定", "取数",
             "供 G13 公允价值变动损益跨底稿勾稽（calcG1FvChangeAuditedTotal，发布 g-cycle:source-fv）",
             "useG1Adjudication / gCycleExternalCross"),
        ],
        "附注国企": [
            ("附注披露金额", "取自 G1-1 审定表（投资成本/累计公允价值变动/账面余额审定数）", "取数",
             "附注按分类取审定数（adjudicationForDisclosure）", "useG1DisclosureSoe"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # G2 应收利息（借方 1132；原值/坏账/净值三层 + 债券利息测算 + ECL 三阶段）
    # ═══════════════════════════════════════════════════════════════════════
    "G2": {
        # G2-1 审定表（原值/坏账/净值 × 期初/期末未审·调整·审定）
        "G2-1": [
            ("审定数", "未审数 + 账项调整", "计算",
             "各叶子行审定（calcAuditedAmount，期初/期末各自）", "useG2Adjudication / useG2IntRecFormulaEngine"),
            ("原值/坏账小计", "Σ 该 section 叶子（单项/组合）", "计算",
             "leafKeysForSection 汇总（calcSubtotal）", "useG2Adjudication"),
            ("应收利息净值", "原值小计 − 坏账准备小计", "计算",
             "净值行 = gross__subtotal − provision__subtotal", "useG2Adjudication"),
            ("合计", "= 净值（列报口径）", "计算",
             "footer-total 取净值行", "useG2Adjudication"),
            ("变动额 / 变动率", "期末审定 − 期初审定；变动额 ÷ 期初审定", "计算",
             "期初=0→''/N/A；|变动率|>阈值差异分析必填（calcChangeAmount/calcChangeRate）", "useG2IntRecFormulaEngine"),
            ("从 G2-2 / G2-3 汇总带入", "原值取 G2-2 期末应收(Stage3→单项/其余→组合)；坏账取 G2-3 单项·组合期末审定", "取数",
             "syncFromSupporting（aggregateGrossFromDetail / aggregateProvisionFromBadDebt）", "useG2Adjudication / g2CrossHelpers"),
            ("试算平衡表数核对", "净值审定合计 − 试算平衡表数(1132)", "logic_check",
             "审定合计与 TB 应收利息核对（variance/hasVarianceHighlight，容差 0.005；fetchTrialBalance 取 1132）",
             "useG2Adjudication"),
        ],
        # G2-2 明细表（借方科目 + 利息测算）
        "G2-2": [
            ("借方余额", "期初 + 借方 − 贷方", "计算",
             "资产类期末余额（calcDebitBalance / calcEndBalance）", "useG2Detail / useG2IntRecFormulaEngine"),
            ("应收利息", "面值 × 利率% ÷ 100 × 天数 ÷ 365", "计算",
             "债券惯例 365 天基准（calcInterest365，区别于 F3 票据 360 天）", "useG2IntRecFormulaEngine"),
            ("计息天数", "截止日 − 起始日", "计算",
             "计息天数（calcAccruedDays）", "useG2IntRecFormulaEngine"),
            ("期末应收", "应计利息 − 已收利息", "计算",
             "净应收（calcNetReceivable）", "useG2IntRecFormulaEngine"),
        ],
        # G2-3 坏账准备
        "G2-3": [
            ("应计提", "审定余额 × 损失率", "计算",
             "账龄组合口径应计提（calcExpectedProvision）", "useG2BadDebtDetail / useG2IntRecFormulaEngine"),
            ("差异", "应计提 − 账面坏账准备", "logic_check",
             "与账面核对（calcEclDifference）", "useG2IntRecFormulaEngine"),
        ],
        # G2-4 调整分录
        "G2-4": [
            ("借贷平衡校验", "Σ 借方金额 = Σ 贷方金额", "logic_check",
             "调整分录借贷平衡（isDebitCreditBalanced）", "useG2Adjustment / useG2IntRecFormulaEngine"),
            ("回写审定表", "确认后按净额写入 G2-1 期末账项调整", "取数",
             "g2:adjustment-confirmed → applyAdjustmentWriteback", "useG2Adjudication"),
        ],
        # G2-5 利息测算
        "G2-5": [
            ("应收利息测算", "面值 × 利率% ÷ 100 × 天数 ÷ 365", "计算",
             "独立利息测算表（calcInterest365 + calcAccruedDays）", "useG2InterestCalc / useG2IntRecFormulaEngine"),
        ],
        # G2 ECL 三阶段
        "G2-ECL": [
            ("预期信用损失(ECL)", "EAD × PD × LGD", "计算",
             "三阶段 ECL（calcECL）", "useG2ECLCalc / useG2IntRecFormulaEngine"),
            ("逾期天数", "MAX(0, 当前日 − 约定到期日)", "计算",
             "逾期天数（calcOverdueDays）", "useG2IntRecFormulaEngine"),
            ("阶段判定", "已减值→阶段3；信用风险显著增加→阶段2；否则→阶段1", "logic_check",
             "阶段判定（determineStage）", "useG2IntRecFormulaEngine"),
            ("ECL 差异", "测算 ECL − 企业计提", "logic_check",
             "ECL 与企业计提核对（calcECLVariance）", "useG2IntRecFormulaEngine"),
        ],
        "附注上市": [
            ("附注披露金额", "取自 G2-1 审定表（原值/坏账/净值审定数）", "取数",
             "附注取审定数", "useG2DisclosureListed"),
        ],
        "附注国企": [
            ("附注披露金额", "取自 G2-1 审定表（原值/坏账/净值审定数）", "取数",
             "附注取审定数", "useG2DisclosureSoe"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # G3 应收股利（借方 1131；按被投资方逐行 + 账龄一年内/一年以上）
    # ═══════════════════════════════════════════════════════════════════════
    "G3": {
        # G3-1 审定表
        "G3-1": [
            ("期初审定", "期初未审 + 期初 AJE + 期初 RJE", "计算",
             "期初审定（calcAdjustedAmount）", "useG3Adjudication / useG3DivRecFormulaEngine"),
            ("期末未审", "期初审定 + 本期宣告(借方) − 本期收回(贷方)", "计算",
             "借方科目期末未审（calcDebitBalance）", "useG3DivRecFormulaEngine"),
            ("期末审定", "期末未审 + 期末 AJE + 期末 RJE", "计算",
             "期末审定（calcAdjustedAmount）", "useG3DivRecFormulaEngine"),
            ("合计", "Σ 各被投资方行", "计算",
             "审定表合计（calcSubtotal）", "useG3Adjudication"),
            ("变动额 / 变动率", "期末审定 − 期初审定；÷ 期初审定", "计算",
             "期初=0→''/N/A；|变动率|>30% 原因分析必填（calcChangeAmount/calcChangeRate）", "useG3DivRecFormulaEngine"),
            ("账龄汇总", "参照 G3-5 逾期≥365 天拆分一年内 / 一年以上", "计算",
             "computeG3AgingSummary（读 G3-5 逾期数据）", "useG3Adjudication / g3AdjudicationItems"),
            ("从 G3-2 明细带入", "按被投资方 SUM(G3-2 本期宣告/收回)", "取数",
             "syncFromDetail（保留期初未审与 AJE/RJE）", "useG3Adjudication / g3AdjudicationItems"),
            ("试算平衡表数核对", "期末审定合计 − 试算平衡表数(1131)", "logic_check",
             "审定合计与 TB 应收股利核对（variance/hasVarianceHighlight，容差 0.005；fetchTrialBalance 取 1131）",
             "useG3Adjudication"),
        ],
        # G3-2 明细
        "G3-2": [
            ("期末余额", "期初 + 本期宣告(借方) − 本期收回(贷方)", "计算",
             "借方科目明细期末余额（calcDebitBalance）", "useG3Detail / useG3DivRecFormulaEngine"),
        ],
        # G3-3 调整分录
        "G3-3": [
            ("借贷平衡校验", "Σ 借方金额 = Σ 贷方金额", "logic_check",
             "调整分录借贷平衡", "useG3Adjustment"),
            ("回写审定表", "确认后按 AJE/RJE 净额写入 G3-1", "取数",
             "g3:adjustment-confirmed → applyG3AdjustmentWriteback", "useG3Adjudication / g3AdjudicationItems"),
        ],
        # G3-5 逾期检查
        "G3-5": [
            ("逾期天数 / 账龄拆分", "逾期≥365 天 → 一年以上，否则一年内", "logic_check",
             "供 G3-1 账龄汇总（G3_OVERDUE_STORAGE_KEY）", "useG3OverdueCheck / g3AdjudicationItems"),
        ],
        "附注上市": [
            ("附注披露金额", "取自 G3-1 审定表（各被投资方期末审定）", "取数",
             "附注取审定数", "useG3Adjudication"),
        ],
        "附注国企": [
            ("附注披露金额", "取自 G3-1 审定表（各被投资方期末审定）", "取数",
             "附注取审定数", "useG3Adjudication"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # G4 债权投资（借方 1501 原值 / 1502 减值；摊余成本三层 + 实际利率法 + ECL）
    # ═══════════════════════════════════════════════════════════════════════
    "G4": {
        # G4-1 审定表（原值/减值/净值三层）
        "G4-1": [
            ("审定数", "未审数 + 账项调整", "计算",
             "各叶子行审定（audited = unadj + adjustment）", "useG4MainAdjudication"),
            ("净值叶子", "对应原值审定 − 减值审定", "计算",
             "net 层 = 摊余成本（calcAmortizedCost，逐单项/组合）", "useG4MainAdjudication / useG4MainFormulaEngine"),
            ("section 小计", "Σ section 内单项+组合叶子", "计算",
             "原值/减值/净值各小计（sumLeaves）", "useG4MainAdjudication"),
            ("section 净额", "小计 − 减:一年内到期部分", "计算",
             "one_year_deduct 扣减后 section_net", "useG4MainAdjudication"),
            ("变动率", "(期末审定 − 期初审定) ÷ 期初审定", "计算",
             "prior=0→null；|变动率|>30% 高亮+原因必填（calcChangeRate）", "useG4MainFormulaEngine"),
            ("G4-3 调整分录回写(分离口径)", "原值净额→1501 行 / 减值净额→1502 行（贷−借取反）", "取数",
             "g4:adjustment-writeback → applySplitWriteback（按 1501/1502 分拆）", "useG4MainAdjudication / g4AdjudicationItems"),
            ("试算平衡表数核对", "净值(摊余成本)审定合计 − 试算平衡表数(1501)", "logic_check",
             "footer-variance = net__net − TB(1501)（fetchTrialBalance 取 1501）", "useG4MainAdjudication"),
        ],
        # G4-2 明细
        "G4-2": [
            ("期末余额", "期初 + 借方发生 − 贷方发生", "计算",
             "借方科目明细期末余额（calcEndBalance）", "useG4MainDetail / useG4BonInvFormulaEngine"),
            ("审定数", "未审 + AJE + RJE", "计算",
             "明细审定（calcAuditedAmount）", "useG4BonInvFormulaEngine"),
        ],
        # G4-3 调整分录
        "G4-3": [
            ("借贷平衡校验", "Σ 借方金额 = Σ 贷方金额（容差 0.005）", "logic_check",
             "调整分录借贷平衡（BALANCE_TOLERANCE）", "useG4MainAdjustment"),
        ],
        # G4-4 利息测算（实际利率法）
        "G4-4": [
            ("初始入账价值", "购买对价 + 交易费用", "计算",
             "(一)初始计量（calcInitialCarryingAmount）", "useG4MainInterestCalc / useG4MainFormulaEngine"),
            ("期初摊余成本", "期初账面总额 − 期初减值准备余额", "计算",
             "(二)摊余成本基数（calcAmortizedCost；Stage3 减值更大→基数更低）", "useG4MainInterestCalc"),
            ("实际利息收入", "期初摊余成本 × 实际利率 × 天数 ÷ 365", "计算",
             "实际利率法确认利息（calcEffectiveInterest）", "useG4MainFormulaEngine"),
            ("现金流入(票息)", "面值 × 票面利率 × 天数 ÷ 365", "计算",
             "名义票息（calcCashInflow）", "useG4MainFormulaEngine"),
            ("期末账面总额", "期初账面 + 实际利息 − 现金流入 − 已收回本金", "计算",
             "期末倒轧（calcEndingBalance；首期开口=初始入账价值，其后=上期期末）", "useG4MainInterestCalc / useG4MainFormulaEngine"),
            ("利率合理性校验", "|实际利率 − 票面利率| > 200bp(2%) → 异常", "logic_check",
             "利率来源合理性（rateWarnings，RATE_DIFF_THRESHOLD=0.02）", "useG4MainInterestCalc"),
            ("利息合计 ↔ G4-1 审定利息", "各项目实际利息合计 − G4-1 审定利息收入", "logic_check",
             "差异 |Δ|>0.01 红色高亮（summary.variance / VARIANCE_THRESHOLD）", "useG4MainInterestCalc"),
        ],
        # G4-9 三阶段判定
        "G4-9": [
            ("阶段判定 → G4-10", "各投资项目 auditStage(Stage1/2/3) 同步至减值测算", "取数",
             "applyStageUpdates（按项目名归一匹配，缺失新建行）", "useG4EclStageClassification / useG4EclImpairmentCalc"),
        ],
        # G4-10 减值准备测算（ECL 公式链）
        "G4-10": [
            ("减值准备③(Stage1/2)", "账面余额① × 信用损失率②", "计算",
             "损失率法（calcImpairmentProvision）", "useG4EclImpairmentCalc / useG4EclFormulaEngine"),
            ("减值准备③(Stage3)", "MAX(0, 账面余额① − 预计未来现金流量现值PV)", "计算",
             "现值法（calcImpairmentFromPv）", "useG4EclFormulaEngine"),
            ("账面价值④", "账面余额① − 减值准备③", "计算",
             "calcBookValue", "useG4EclFormulaEngine"),
            ("减值调整⑥", "目标审定减值⑧' − 减值准备③", "计算",
             "调整恒等式（calcImpairmentAdjustmentIdentity；目标⑧'=(①+⑤)×②A 或 现值法）", "useG4EclImpairmentCalc"),
            ("调整后⑦⑧⑨", "⑦=①+⑤；⑧=③+⑥；⑨=⑦−⑧", "计算",
             "调整后账面余额/减值/账面价值（calcAdjustedBalance/Impairment/BookValue）", "useG4EclImpairmentCalc"),
            ("本期计提 / 转回", "diff=⑧−期初减值；计提=MAX(0,diff)/转回=MAX(0,−diff)", "计算",
             "currentProvision / currentReversal", "useG4EclImpairmentCalc"),
        ],
        # G4-11 ECL 损失率测算
        "G4-11": [
            ("ECL 损失率 → G4-10", "两套测算(PD×LGD / 损失率法)收集损失率回写②", "取数",
             "collectEclRateUpdates / applyEclRateUpdates（默认跳过 Stage3 现值法）", "useG4EclImpairmentCalc"),
        ],
        "附注上市": [
            ("附注披露金额", "取自 G4-1 审定表（原值/减值/净值审定数）", "取数",
             "附注取审定数", "useG4EclImpairmentCalc / 附注组件"),
        ],
        "附注国企": [
            ("附注披露金额", "取自 G4-1 审定表（原值/减值/净值审定数）", "取数",
             "附注取审定数", "附注组件"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # G5 长期应收款（借方 1531；融资租赁内含利率法 + 分期销售实际利率法）
    # ═══════════════════════════════════════════════════════════════════════
    "G5": {
        # G5-1 审定表
        "G5-1": [
            ("审定数", "未审数 + AJE + RJE", "计算",
             "各行审定（calcAuditedAmount）", "useG5Adjudication / useG5LonTerFormulaEngine"),
            ("变动额 / 变动率", "期末审定 − 期初审定；÷ 期初审定", "计算",
             "期初=0→''/N/A（calcChangeAmount/calcChangeRate）", "useG5LonTerFormulaEngine"),
            ("试算平衡表数核对", "期末审定合计 − 试算平衡表数(1531)", "logic_check",
             "审定合计与 TB 长期应收款核对", "useG5Adjudication"),
        ],
        # G5-2 余额明细
        "G5-2": [
            ("期末余额", "期初 + 借方发生 − 贷方发生", "计算",
             "借方科目明细期末余额（calcEndBalance）", "useG5BalanceDetail / useG5LonTerFormulaEngine"),
        ],
        # G5-3 调整分录
        "G5-3": [
            ("借贷平衡校验", "Σ 借方金额 = Σ 贷方金额", "logic_check",
             "调整分录借贷平衡", "useG5Adjustment"),
        ],
        # G5-5 融资租赁未实现收益测算（内含利率法）
        "G5-5": [
            ("净投资额", "应收融资租赁款 − 未实现融资收益", "计算",
             "calcNetInvestment", "useG5LeaseAmortization / useG5FormulaEngine"),
            ("本期融资收益", "期初净投资额 × 内含利率", "计算",
             "calcLeaseFinancingIncome", "useG5FormulaEngine"),
            ("期末应收 / 期末未实现", "期初应收 − 本期收款；期初未实现 − 本期收益", "计算",
             "calcEndingReceivable / calcEndingUnrealizedIncome（第N期期初=第N-1期期末）", "useG5FormulaEngine"),
            ("最低租赁收款额", "各期租金 + 承租人担保余值 + 第三方担保余值", "计算",
             "syncMinimumLeasePayment", "useG5LeaseAmortization"),
            ("毛投资额", "最低租赁收款额 + 未担保余值期末 + 初始直接费用", "计算",
             "buildReconcileRow.grossInvestment", "useG5LeaseAmortization"),
            ("账面净值", "净投资期末 − 减值准备 − 已核销", "计算",
             "carryingAmount", "useG5LeaseAmortization"),
            ("期间连续性校验", "第N期期初应收/未实现 = 第N-1期期末（容差 0.01）", "logic_check",
             "validateContinuity / getContinuityErrors", "useG5LeaseAmortization"),
            ("未实现/净投资差异", "审计期末 − 账面期末", "logic_check",
             "unrealizedVariance / netVariance", "useG5LeaseAmortization"),
        ],
        # G5-6 分期销售未实现融资收益测算（实际利率法）
        "G5-6": [
            ("未实现融资收益初始", "应收总额 − 公允价值", "计算",
             "calcInstallment 初始（recalcInitial）", "useG5InstallmentSales / useG5FormulaEngine"),
            ("期初摊余成本(未收本金)", "期初应收 − 期初未实现", "计算",
             "calcNetInvestment", "useG5FormulaEngine"),
            ("本期融资收益", "期初摊余成本 × 实际利率", "计算",
             "calcInstallmentFinancingIncome", "useG5FormulaEngine"),
            ("已收本金", "本期收款 − 本期融资收益", "计算",
             "模板列(2)=(5)−(3)", "useG5InstallmentSales"),
            ("期末应收 / 期末摊余", "期初应收 − 本期收款；期初摊余 + 本期收益 − 本期收款", "计算",
             "calcEndingReceivable / calcSalesAmortizedCost", "useG5FormulaEngine"),
            ("期间连续性校验", "应收 + 未实现均需连贯（容差 0.01）", "logic_check",
             "validateContinuity", "useG5InstallmentSales"),
        ],
        "附注上市": [
            ("附注披露金额", "取自 G5-1 审定表 + G5-5/G5-6 净投资/摊余期末", "取数",
             "附注取审定数", "useG5DisclosureListed"),
        ],
        "附注国企": [
            ("附注披露金额", "取自 G5-1 审定表 + G5-5/G5-6 净投资/摊余期末", "取数",
             "附注取审定数", "useG5DisclosureSoe"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # G6 其他债权投资（借方 1503，FVOCI；ECL 三阶段测算）
    # ═══════════════════════════════════════════════════════════════════════
    "G6": {
        # G6-1 审定表
        "G6-1": [
            ("审定数", "未审数 + AJE + RJE", "计算",
             "各行审定（calcAuditedAmount）", "useG6MainAdjudication / useG6OthBonFormulaEngine"),
            ("变动额 / 变动率", "期末审定 − 期初审定；÷ 期初审定", "计算",
             "calcChangeAmount / calcChangeRate", "useG6OthBonFormulaEngine"),
            ("试算平衡表数核对", "期末审定合计 − 试算平衡表数(1503)", "logic_check",
             "审定合计与 TB 其他债权投资核对（G6_ACCOUNT_CODE=1503）", "useG6MainAdjudication"),
        ],
        # G6-2 明细
        "G6-2": [
            ("期末余额", "期初 + 借方发生 − 贷方发生", "计算",
             "借方科目明细期末余额（calcEndBalance）", "useG6MainDetail / useG6OthBonFormulaEngine"),
        ],
        # G6-4 调整分录
        "G6-4": [
            ("借贷平衡校验", "Σ 借方金额 = Σ 贷方金额（容差 0.005）", "logic_check",
             "调整分录借贷平衡（BALANCE_TOLERANCE）", "useG6MainAdjustment"),
        ],
        # G6-12 减值准备测算（ECL）
        "G6-12": [
            ("减值准备③(Stage1/2)", "账面余额① × 信用损失率②", "计算",
             "损失率法（calcImpairmentProvision）", "useG6EclImpairmentCalc / useG6EclFormulaEngine"),
            ("减值准备③(Stage3)", "MAX(0, 账面余额① − 预计未来现金流量现值PV)", "计算",
             "现值法（calcImpairmentFromPv；PV=0 表示零回收）", "useG6EclFormulaEngine"),
            ("减值调整⑥", "Stage1/2: ⑤×②A + ①×(②A−②)；Stage3: 目标⑧−③", "计算",
             "calcImpairmentAdjustment / calcImpairmentAdjustmentIdentity", "useG6EclImpairmentCalc"),
            ("调整后⑦⑧⑨", "⑦=①+⑤；⑧=③+⑥；⑨=⑦−⑧", "计算",
             "calcAdjustedBalance / calcAdjustedImpairment / calcAdjustedBookValue", "useG6EclImpairmentCalc"),
            ("回收率参考", "Σ现值 ÷ Σ账面余额", "logic_check",
             "totalRecoveryRate（合计行 D 列参考）", "useG6EclImpairmentCalc"),
            ("本期计提 / 转回", "diff=⑧−期初减值；计提=MAX(0,diff)/转回=MAX(0,−diff)", "计算",
             "currentProvision / currentReversal", "useG6EclImpairmentCalc"),
        ],
        "附注上市": [
            ("附注披露金额", "取自 G6-1 审定表（其他债权投资审定数）", "取数",
             "附注取审定数", "附注组件"),
        ],
        "附注国企": [
            ("附注披露金额", "取自 G6-1 审定表（其他债权投资审定数）", "取数",
             "附注取审定数", "附注组件"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # G7 长期股权投资（借方 1511；权益法 / 成本法(子公司) / 长投减值三组）
    # ═══════════════════════════════════════════════════════════════════════
    "G7": {
        # G7-1 审定表
        "G7-1": [
            ("期末未审", "期初审定 + 借方发生 − 贷方发生", "计算",
             "借方/资产类科目期末未审（calcDebitBalance）", "useG7FormulaEngine"),
            ("审定数", "未审数 + AJE + RJE", "计算",
             "期初/期末审定（calcAdjustedAmount，AJE/RJE 两列独立调整）", "useG7FormulaEngine"),
            ("变动率", "(current − prior) ÷ prior", "计算",
             "prior=0→null；|变动率|>20% 橙色高亮（calcChangeRate）", "useG7FormulaEngine"),
            ("试算平衡表数核对", "期末审定合计 − 试算平衡表数(1511)", "logic_check",
             "审定合计与 TB 长期股权投资核对（G7_ACCOUNT_CODE=1511）", "useG7FormData"),
        ],
        # G7-2 明细
        "G7-2": [
            ("期末投资成本", "期初投资成本 + 新增投资 − 处置减少", "计算",
             "calcEndingCost（子公司/合营/联营通用）", "useG7FormulaEngine"),
            ("期末权益法调整", "期初权益法调整 + 权益法增加 − 权益法减少", "计算",
             "calcEndingEquityAdj（合营/联营）", "useG7FormulaEngine"),
            ("期末账面价值", "期末小计(成本+权益法调整) − 期末减值准备", "计算",
             "calcBookValue", "useG7FormulaEngine"),
        ],
        # G7-3 调整分录
        "G7-3": [
            ("借贷平衡校验", "|Σ借方 − Σ贷方| < 0.01", "logic_check",
             "调整分录借贷平衡（isDebitCreditBalanced）", "useG7FormulaEngine"),
        ],
        # G7-8 同控初始计量测试
        "G7-8": [
            ("同控初始投资成本", "被合并方账面净资产 × 持股比例", "计算",
             "CAS20 同一控制下企业合并（calcSameControlCost）", "useG7SubFormulaEngine"),
            ("一次合并差额⑤", "初始投资成本③ − 支付对价合计④", "计算",
             "正贷记资本公积/负冲减（calcSameControlMergerDifference）", "useG7SubFormulaEngine"),
            ("分步同控合并日成本⑤", "合并日净资产账面价值④ × 累计持股比例①", "计算",
             "calcSameControlStepCost", "useG7SubFormulaEngine"),
        ],
        # G7-9 非同控初始计量测试
        "G7-9": [
            ("非同控合并成本", "合并对价公允价值合计（中介费用费用化不计入）", "计算",
             "CAS20 非同一控制下（calcNotSameControlCost）", "useG7SubFormulaEngine"),
            ("商誉/廉价购买利得", "初始投资成本 − 享有可辨认净资产公允价值份额", "计算",
             "正=商誉/负=营业外收入（calcGoodwill）", "useG7SubFormulaEngine"),
        ],
        # G7-10 后续计量测试（成本法）
        "G7-10": [
            ("成本法投资收益", "被投资方宣告现金股利 × 持股比例", "计算",
             "calcCostMethodIncome", "useG7SubFormulaEngine"),
            ("成本法期末账面", "期初账面 + 追加投资 − 减值计提", "计算",
             "calcSubsequentBalance", "useG7SubFormulaEngine"),
            ("股利差异", "应享有股利 − 实际入账股利", "logic_check",
             "calcDividendVariance", "useG7SubFormulaEngine"),
            ("购买少数股权权益调整⑤", "购买成本② − 按新增比例享有净资产份额④", "计算",
             "CAS33 权益性交易（calcNciEquityAdjustment；④=持续计算净资产FV×新增比例）", "useG7SubFormulaEngine"),
            ("不丧失控制权处置个别收益⑤", "处置对价④ − 处置日账面① × 减少比例③ ÷ 原比例②", "计算",
             "calcPartialDisposalIndividualGain", "useG7SubFormulaEngine"),
        ],
        # G7-11 处置测试（非一揽子）
        "G7-11": [
            ("处置损益", "处置对价 − 处置日账面 − 应收股利 + 可转损益OCI", "计算",
             "CAS2/CAS33 丧失控制权处置（calcDisposalGain）", "useG7SubFormulaEngine"),
        ],
        # G7-13 投资成本测试（权益法初始）
        "G7-13": [
            ("初始投资成本", "支付对价 + 直接相关费用", "计算",
             "calcInvestmentCost", "useG7EquityMethodFormulaEngine"),
            ("享有净资产份额", "净资产公允价值 × 持股比例", "计算",
             "calcShareOfNetAssets", "useG7EquityMethodFormulaEngine"),
            ("商誉/营业外收入差额", "初始投资成本 − 享有份额", "计算",
             "正=商誉/负=营业外收入（calcGoodwill）", "useG7EquityMethodFormulaEngine"),
        ],
        # G7-14 权益法核算表
        "G7-14": [
            ("调整后净利润", "报告净利润 − 内部交易 − 公允价值折旧 + 政策调整 + 其他", "计算",
             "CAS2 权益法核算前调整（calcAdjustedNetProfit）", "useG7EquityMethodFormulaEngine"),
            ("持股比例份额", "值 × 持股比例", "计算",
             "投资收益/OCI/其他权益份额通用乘法（calcEquityShare）", "useG7EquityMethodFormulaEngine"),
            ("期末权益法余额", "期初 + 投资收益 + OCI + 其他权益 − 股利", "计算",
             "calcEquityMethodBalance", "useG7EquityMethodFormulaEngine"),
            ("长投账面余额", "投资成本期末 + 损益调整期末 + OCI期末 + 其他权益变动期末", "计算",
             "calcLteiBookBalance（R=O+L+I+F）", "useG7EquityMethodFormulaEngine"),
            ("与应享净资产差额", "长投账面余额 − 经审计净资产 × 持股比例", "logic_check",
             "calcNetAssetShareVariance（S=R−Q）", "useG7EquityMethodFormulaEngine"),
            ("期末勾稽差异 ↔ G7-2", "长投账面余额 − G7-2 审定期末总额", "logic_check",
             "calcClosingReconVariance", "useG7EquityMethodFormulaEngine"),
        ],
        # G7-15 内部交易抵销
        "G7-15": [
            ("未实现利润", "交易金额 × 毛利率", "计算",
             "calcUnrealizedProfit", "useG7EquityMethodFormulaEngine"),
            ("应抵销金额", "顺流:未实现利润全额 / 逆流:未实现利润 × 持股比例", "计算",
             "calcEliminationAmount", "useG7EquityMethodFormulaEngine"),
        ],
        # G7-17 减值测试（CAS8）
        "G7-17": [
            ("可收回金额", "MAX(公允价值减处置费用后净额, 使用价值)", "计算",
             "CAS8 资产减值（calcRecoverableAmount）", "useG7EquityMethodFormulaEngine"),
            ("减值金额", "MAX(0, 账面价值 − 可收回金额)", "计算",
             "减值非负（calcImpairmentAmount）", "useG7EquityMethodFormulaEngine"),
        ],
        # G7-18 凭证检查
        "G7-18": [
            ("借贷平衡校验", "|Σ借方 − Σ贷方| < 0.01", "logic_check",
             "凭证检查借贷平衡（isDebitCreditBalanced）", "useG7SubFormulaEngine"),
        ],
        "附注上市": [
            ("附注披露金额", "取自 G7-1/G7-2 审定表（投资成本/权益法调整/账面价值）", "取数",
             "附注取审定数（含同控/非同控/少数股东联动）", "附注组件"),
        ],
        "附注国企": [
            ("附注披露金额", "取自 G7-1/G7-2 审定表（投资成本/权益法调整/账面价值）", "取数",
             "附注取审定数", "附注组件"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # G8 其他权益工具投资（借方 1503，FVOCI 且不可回收至损益；无 AJE/RJE 分列）
    # ═══════════════════════════════════════════════════════════════════════
    "G8": {
        # G8-1 审定表（单分组公允价值）
        "G8-1": [
            ("审定数", "未审数 + 账项调整", "计算",
             "各行审定（calcAdjustedAmount，G8 无 AJE/RJE 分列）", "useG8Adjudication / useG8FormulaEngine"),
            ("合计", "Σ 各公允价值行", "计算",
             "分组小计（calcSubtotal）", "useG8Adjudication"),
            ("变动额 / 变动率", "期末审定 − 期初审定；÷ |期初审定|", "计算",
             "prior=0→null；|变动率|>阈值原因必填（calcChangeAmount/calcChangeRate）", "useG8FormulaEngine"),
            ("从 G8-2 明细带入", "取 G8-2 账面余额合计 → fv_1 期初/期末未审", "取数",
             "syncUnadjustedFromDetail（保留 G8-3 回写的账项调整）", "useG8Adjudication / g8CrossHelpers"),
            ("G8-3 调整分录回写", "监听 g8:adjustment-writeback 写入期末账项调整", "取数",
             "applyG8AdjustmentWriteback（默认行 fv_1）", "useG8Adjudication / g8AdjStorage"),
            ("试算平衡表数核对", "期末审定合计 − 试算平衡表数(1503)", "logic_check",
             "审定合计与 TB 其他权益工具投资核对（variance，容差 0.01；loadTrialBalanceFromApi 取 1503 借−贷）",
             "useG8Adjudication"),
            ("审定 ↔ G8-2 明细勾稽", "期末审定合计 − G8-2 明细期末合计", "logic_check",
             "detailCrossVariance（容差 0.01）", "useG8Adjudication"),
            ("审定 ↔ G8-4 公允测试勾稽", "期末审定合计 − G8-4 审定公允价值合计", "logic_check",
             "fvCrossVariance（容差 0.01）", "useG8Adjudication"),
        ],
        # G8-2 明细
        "G8-2": [
            ("期末余额", "期初审定 + 增加 − 减少 + 公允价值变动", "计算",
             "calcEndingBalance", "useG8Detail / useG8FormulaEngine"),
            ("OCI 期末累计", "期初累计 + 本期 OCI − 转入留存收益", "计算",
             "CAS22 处置时 OCI 可转留存（calcOciCumulativeEnding）", "useG8FormulaEngine"),
        ],
        # G8-3 调整分录
        "G8-3": [
            ("借贷平衡校验", "|Σ借方 − Σ贷方| < 0.01", "logic_check",
             "调整分录借贷平衡（isDebitCreditBalanced）", "useG8Adjustment / useG8FormulaEngine"),
        ],
        # G8-4 公允价值测试
        "G8-4": [
            ("公允价值", "数量 × 单价（保留 2 位）", "计算",
             "calcFairValueAmount", "useG8FairValueTest / useG8FormulaEngine"),
            ("公允价值差异", "审定公允价值 − 未审公允价值", "logic_check",
             "calcFairValueDiff", "useG8FormulaEngine"),
            ("数量变动影响", "(审定数量 − 未审数量) × 未审单价", "计算",
             "差异归因·数量（calcFairValueQtyImpact）", "useG8FormulaEngine"),
            ("价格变动影响", "审定数量 × (审定单价 − 未审单价)", "计算",
             "差异归因·价格（calcFairValuePriceImpact）", "useG8FormulaEngine"),
        ],
        "附注上市": [
            ("附注披露金额", "取自 G8-1 审定表（其他权益工具投资审定数）", "取数",
             "附注取审定数（发布 g-cycle:source-fv 供 G13 勾稽）", "useG8Disclosure / useG8Adjudication"),
        ],
        "附注国企": [
            ("附注披露金额", "取自 G8-1 审定表（其他权益工具投资审定数）", "取数",
             "附注取审定数", "useG8Disclosure"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # G9 其他非流动金融资产（借方 1519；FVTPL / FVOCI + L3 调节 10 因子）
    # ═══════════════════════════════════════════════════════════════════════
    "G9": {
        # G9-1 审定表
        "G9-1": [
            ("审定数", "未审数 + AJE + RJE", "计算",
             "各行审定（calcAdjustedAmount）", "useG9Adjudication / useG9FormulaEngine"),
            ("变动额 / 变动率", "期末审定 − 期初审定；÷ |期初审定|", "计算",
             "calcChangeAmount / calcChangeRate", "useG9FormulaEngine"),
            ("试算平衡表数核对", "期末审定合计 − 试算平衡表数(1519)", "logic_check",
             "审定合计与 TB 其他非流动金融资产核对（G9_ACCOUNT_CODE=1519，历史 1510/1504 回退）", "useG9Adjudication"),
        ],
        # G9-2 明细
        "G9-2": [
            ("期末余额", "期初审定 + 增加 − 减少 + 公允价值变动 + 利息 − 减值 + OCI变动", "计算",
             "calcEndingBalance", "useG9Detail / useG9FormulaEngine"),
        ],
        # G9-4 公允价值测试
        "G9-4": [
            ("公允价值", "数量 × 单价（保留 2 位）", "计算",
             "calcFairValueAmount", "useG9FairValueTest / useG9FormulaEngine"),
            ("公允价值差异", "审定 − 未审", "logic_check",
             "calcFairValueDiff", "useG9FormulaEngine"),
            ("数量/价格变动影响", "数量影响=(审定量−未审量)×未审价；价格影响=审定量×(审定价−未审价)", "计算",
             "calcFairValueQtyImpact / calcFairValuePriceImpact", "useG9FormulaEngine"),
        ],
        # G9-5 第三层次公允价值调节表（10 因子）
        "G9-5": [
            ("L3 期末余额", "期初 + 购买 − 处置 + 转入 − 转出 + FV变动(损益) + FV变动(OCI) + 利息 − 减值 + 其他", "计算",
             "10 因子调节（calcL3Reconciliation）", "useG9L3Reconciliation / useG9FormulaEngine"),
            ("L3 差异", "公式期末 − 报表期末", "logic_check",
             "calcL3Variance", "useG9FormulaEngine"),
        ],
        # G9 凭证/调整
        "G9-调整": [
            ("借贷平衡校验", "|Σ借方 − Σ贷方| < 0.01", "logic_check",
             "调整分录借贷平衡（isDebitCreditBalanced）", "useG9Adjustment / useG9FormulaEngine"),
        ],
        "附注上市": [
            ("附注披露金额", "取自 G9-1 审定表（其他非流动金融资产审定数）", "取数",
             "附注取审定数", "useG9Disclosure"),
        ],
        "附注国企": [
            ("附注披露金额", "取自 G9-1 审定表（其他非流动金融资产审定数）", "取数",
             "附注取审定数", "useG9Disclosure"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # G10 交易性金融负债（贷方 2101；三部分:初始/累计FV变动/账面 + L3 调节）
    # ═══════════════════════════════════════════════════════════════════════
    "G10": {
        # G10-1 审定表（三部分结构）
        "G10-1": [
            ("审定数", "未审数 + AJE + RJE", "计算",
             "各行审定（calcAdjustedAmount）", "useG10Adjudication / useG10FormulaEngine"),
            ("期末未审(缺失时倒推)", "期初审定 + 本期贷方 − 本期借方", "计算",
             "贷方负债余额（calcCreditBalance，resolveClosingUnadjusted 回退）", "useG10Adjudication / useG10FormulaEngine"),
            ("(三)账面余额", "(一)初始金额 + (二)累计公允价值变动", "计算",
             "calcBookFromParts", "useG10FormulaEngine"),
            ("分组小计 / 合计", "Σ 各分组行；合计取 (三)账面余额分组", "计算",
             "subtotalForGroup / totalRow（以账面余额口径核对）", "useG10Adjudication"),
            ("变动额 / 变动率", "期末审定 − 期初审定；÷ |期初审定|", "计算",
             "calcChangeAmount / calcChangeRate", "useG10FormulaEngine"),
            ("(一)+(二)=(三) 分项勾稽", "各负债 初始 + 累计FV变动 = 账面（期初/期末）", "logic_check",
             "threePartMismatches（容差 0.01）", "useG10Adjudication"),
            ("试算平衡表数核对", "(三)账面余额审定合计 − 试算平衡表数(2101)", "logic_check",
             "审定合计与 TB 交易性金融负债核对（variance/hasVarianceHighlight；resolveG10TbRow 取 2101）", "useG10Adjudication"),
            ("审定 ↔ G10-2 明细勾稽", "(三)账面审定合计 − G10-2 明细期末合计", "logic_check",
             "detailCrossVariance（容差 0.01）", "useG10Adjudication"),
        ],
        # G10-2 明细
        "G10-2": [
            ("期末余额", "期初审定 + 本期初始确认 + 公允价值变动 + 利息 − 本期减少", "计算",
             "贷方负债明细期末（calcG10DetailClosingBalance → calcCreditBalance）", "useG10Detail / useG10FormulaEngine"),
        ],
        # G10-3 调整分录
        "G10-3": [
            ("借贷平衡校验", "|Σ借方 − Σ贷方| < 0.01", "logic_check",
             "调整分录借贷平衡（isDebitCreditBalanced）", "useG10Adjustment / useG10FormulaEngine"),
            ("回写审定表", "g10:adjustment-writeback 按行写入 AJE/RJE", "取数",
             "applyG10AdjustmentWritebacks", "useG10Adjudication / g10AdjStorage"),
        ],
        # G10-6 第三层次公允价值调节表（负债方向）
        "G10-6": [
            ("L3 期末余额", "期初 + 本期新增 − 本期终止 + 转入 − 转出 + FV变动 + 利息 + 其他", "计算",
             "负债方向调节（calcL3Reconciliation）", "useG10L3Reconciliation / useG10FormulaEngine"),
            ("L3 差异", "企业期末(reportedClosing) − 公式期末", "logic_check",
             "variance（超阈值可推送 G10-3）", "useG10L3Reconciliation"),
            ("从 G10-2 / G10-5 Level3 带入", "按负债名匹配 Level3 明细/公允测试", "取数",
             "pullFromDetail / pullFromFairValueTest（mergeByLiabilityName）", "useG10L3Reconciliation"),
            ("L3 ↔ G10-5 公允测试勾稽", "L3 企业期末合计 − G10-5 Level3 审定公允价值合计", "logic_check",
             "fvCrossVariance", "useG10L3Reconciliation"),
        ],
        "附注上市": [
            ("附注披露金额", "取自 G10-1 审定表（初始/累计FV变动/账面审定数）", "取数",
             "附注取审定数", "useG10Disclosure"),
        ],
        "附注国企": [
            ("附注披露金额", "取自 G10-1 审定表（初始/累计FV变动/账面审定数）", "取数",
             "附注取审定数", "useG10Disclosure"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # G11 投资收益（损益 6111 取发生额；本期/上期对比 + 收益率分析）
    # ═══════════════════════════════════════════════════════════════════════
    "G11": {
        # G11-1 审定表
        "G11-1": [
            ("审定数", "未审数 + 账项调整", "计算",
             "损益类各行审定（calcAdjustedAmount）", "useG11Adjudication / useG11FormulaEngine"),
            ("变动额 / 变动率", "本期审定 − 上期审定；÷ |上期审定|", "计算",
             "prior=0→null；|变动率|>20% 高亮（calcChangeAmount/calcChangeRate）", "useG11FormulaEngine"),
            ("试算平衡表数核对", "本期审定合计 − 试算平衡表数(6111 发生额)", "logic_check",
             "审定合计与 TB 投资收益核对（G11_ACCOUNT_CODE=6111）", "useG11Adjudication"),
        ],
        # G11-2 明细
        "G11-2": [
            ("本期审定", "本期未审 + 本期账项调整", "计算",
             "各分项审定（calcAdjustedAmount）", "useG11DetailAnalysis / useG11FormulaEngine"),
        ],
        # G11-3 调整分录
        "G11-3": [
            ("借贷平衡校验", "|Σ借方 − Σ贷方| < 0.01", "logic_check",
             "调整分录借贷平衡（isDebitCreditBalanced）", "useG11Adjustment / useG11FormulaEngine"),
        ],
        # G11-4 收益率分析
        "G11-4": [
            ("平均投资余额", "(期初 + 期末) ÷ 2", "计算",
             "calcAverageBalance", "useG11ReturnRateAnalysis / useG11FormulaEngine"),
            ("收益率", "本期发生额 ÷ 平均投资余额", "计算",
             "平均余额=0→null（calcReturnRate）", "useG11FormulaEngine"),
            ("收益率变动", "本期收益率 − 上期收益率", "logic_check",
             "|Δ|>5 个百分点 标异常（calcReturnRateChange / isReturnRateChangeExceeding）", "useG11FormulaEngine"),
            ("与市场收益率差异", "本期收益率 − 市场平均收益率", "logic_check",
             "重大投资外部对标（vsMarketDiff）", "useG11ReturnRateAnalysis"),
            ("从 G11-1 带入", "读 G11-1 本期/上期审定数 → 发生额① / 审定数④", "取数",
             "pullFromAdjudication", "useG11ReturnRateAnalysis"),
            ("从试算表带入余额", "取 15 类投资科目期初/期末余额作平均投资基数", "取数",
             "pullBalancesFromTb（buildBalancePatchFromTb）", "useG11ReturnRateAnalysis"),
            ("发生额合计 ↔ G11-1 审定合计", "G11-4 本期发生额合计 − G11-1 审定合计", "logic_check",
             "adjCrossCheck（容差 0.01）", "useG11ReturnRateAnalysis"),
        ],
        "附注上市": [
            ("附注披露金额", "取自 G11-1 审定表（投资收益各分项审定数）", "取数",
             "附注取审定数", "useG11Disclosure"),
        ],
        "附注国企": [
            ("附注披露金额", "取自 G11-1 审定表（投资收益各分项审定数）", "取数",
             "附注取审定数", "useG11Disclosure"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # G12 套期（净敞口套期收益 6103 取发生额；套期有效性 + 风险净敞口）
    # ═══════════════════════════════════════════════════════════════════════
    "G12": {
        # G12-1 审定表
        "G12-1": [
            ("审定数", "未审数 + 账项调整", "计算",
             "损益类各行审定（calcAdjustedAmount）", "useG12Adjudication / useG12FormulaEngine"),
            ("变动额 / 变动率", "本期审定 − 上期审定；÷ |上期审定|", "计算",
             "prior=0→null；|变动率|>20% 高亮（calcChangeAmount/calcChangeRate）", "useG12FormulaEngine"),
            ("试算平衡表数核对", "本期审定合计 − 试算平衡表数(6103 发生额)", "logic_check",
             "审定合计与 TB 套期收益核对（G12_ACCOUNT_CODE=6103）", "useG12Adjudication"),
        ],
        # G12-2 套期明细
        "G12-2": [
            ("公允价值变动", "期末公允价值 − 期初公允价值", "计算",
             "calcFVChange", "useG12HedgeDetail / useG12FormulaEngine"),
            ("套期无效部分", "|套期工具变动 − 被套期项目变动|", "计算",
             "套期有效性评估（calcHedgeIneffectiveness）", "useG12FormulaEngine"),
        ],
        # G12-3 调整分录
        "G12-3": [
            ("借贷平衡校验", "|Σ借方 − Σ贷方| < 0.01", "logic_check",
             "调整分录借贷平衡（isDebitCreditBalanced）", "useG12Adjustment / useG12FormulaEngine"),
        ],
        # G12-5 风险净敞口检查
        "G12-5": [
            ("净头寸", "头寸1金额 − 头寸2金额（同币种）", "计算",
             "净敞口建议（suggestNetPosition，可手工覆盖）", "useG12NetExposure / g12NetExposureCalc"),
            ("从 G12-2 带入", "按套期关系带入项目/净头寸/套期工具", "取数",
             "importFromHedgeDetail / syncNetPositionFromG12_2", "useG12NetExposure"),
        ],
        # G12 凭证检查
        "G12-凭证": [
            ("凭证异常判定", "任一核对项 = 否 → 异常", "logic_check",
             "isVoucherAbnormal", "useG12VoucherCheck / useG12FormulaEngine"),
        ],
        "附注上市": [
            ("附注披露金额", "取自 G12-1 审定表（套期损益审定数）", "取数",
             "附注取审定数", "useG12Disclosure"),
        ],
        "附注国企": [
            ("附注披露金额", "取自 G12-1 审定表（套期损益审定数）", "取数",
             "附注取审定数", "useG12Disclosure"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # G13 公允价值变动损益（6101 取发生额；成本+累计FV变动恒等 + 跨源勾稽）
    # ═══════════════════════════════════════════════════════════════════════
    "G13": {
        # G13-1 审定表
        "G13-1": [
            ("审定数", "未审数 + 账项调整", "计算",
             "损益类各行审定（calcAdjustedAmount）", "useG13Adjudication / useG13FormulaEngine"),
            ("变动额 / 变动率", "本期审定 − 上期审定；÷ |上期审定|", "计算",
             "prior=0→null；|变动率|>30% 须说明原因（calcChangeAmount/calcChangeRate）", "useG13FormulaEngine"),
            ("试算平衡表数核对", "本期审定合计 − 试算平衡表数(6101 发生额)", "logic_check",
             "审定合计与 TB 公允价值变动损益核对（G13_ACCOUNT_CODE=6101）", "useG13Adjudication"),
        ],
        # G13-2 明细
        "G13-2": [
            ("公允价值变动", "期末公允价值 − 期初公允价值", "计算",
             "calcFVChange", "useG13Detail / useG13FormulaEngine"),
            ("公允价值(恒等)", "成本 + 累计公允价值变动", "计算",
             "calcFairValueFromParts", "useG13FormulaEngine"),
            ("BS 公允价值核对", "成本 + 累计公允价值变动 = 公允价值（容差 0.01）", "logic_check",
             "isBsFvReconciled", "useG13FormulaEngine"),
            ("计入损益 ↔ 损益审定核对", "计入损益金额 = 损益科目审定数（容差 0.01）", "logic_check",
             "isPlReconciled", "useG13FormulaEngine"),
            ("FV变动 ↔ 审定核对", "|公允价值变动 − 审定数| ≤ 容差", "logic_check",
             "calcVariance / isFvReconciled", "useG13FormulaEngine"),
        ],
        # G13-3 调整分录
        "G13-3": [
            ("借贷平衡校验", "|Σ借方 − Σ贷方| < 0.01", "logic_check",
             "调整分录借贷平衡（isDebitCreditBalanced）", "useG13Adjustment / useG13FormulaEngine"),
        ],
        # G13 跨源勾稽（G13-2 各源 FV 变动 vs G1/G8/G9/G10 各源）
        "G13-跨源": [
            ("跨底稿 FV 变动勾稽", "G13-2 各源公允价值变动 ↔ G1/G8/G9/G10 发布的 g-cycle:source-fv", "logic_check",
             "各源底稿 publishGCycleSourceFv 汇总核对（useG13ExternalCross）", "useG13ExternalCross / gCycleSourceFv"),
        ],
        "附注上市": [
            ("附注披露金额", "取自 G13-1 审定表（公允价值变动损益审定数）", "取数",
             "附注取审定数", "useG13Disclosure"),
        ],
        "附注国企": [
            ("附注披露金额", "取自 G13-1 审定表（公允价值变动损益审定数）", "取数",
             "附注取审定数", "useG13Disclosure"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # G14 信用减值损失（6702 取发生额；本期自 G14-2 同步，上期独立录入）
    # ═══════════════════════════════════════════════════════════════════════
    "G14": {
        # G14-1 审定表
        "G14-1": [
            ("本期审定数", "本期未审 + 本期账项调整（自 G14-2 明细同步）", "计算",
             "本期取 G14-2 明细 currentAudited（buildRow）", "useG14Adjudication"),
            ("上期审定数", "上期未审 + 上期账项调整（独立录入）", "计算",
             "calcAdjustedAmount（priorStore 独立录入）", "useG14Adjudication / useG14FormulaEngine"),
            ("变动额 / 变动率", "本期审定 − 上期审定；÷ |上期审定|", "计算",
             "|变动率|>30% 或变动额超阈值或上期0本期非0 → 原因必填（calcChangeAmount/calcChangeRate）",
             "useG14FormulaEngine"),
            ("合计", "Σ 各减值来源行", "计算",
             "calcSubtotal", "useG14Adjudication"),
            ("试算平衡表数核对", "本期审定合计 − 试算平衡表数(6702 借−贷发生额)", "logic_check",
             "审定合计与 TB 信用减值损失核对（loadTrialBalanceFromApi 取 6702，损益类借−贷）", "useG14Adjudication"),
            ("审定 ↔ G14-2 明细勾稽", "G14-1 本期审定合计 − G14-2 明细合计", "logic_check",
             "detailMismatch / detailCrossValidation（容差 0.01）", "useG14Adjudication"),
        ],
        # G14-2 明细（对齐致同 xlsx 明细表 G14-2）
        "G14-2": [
            ("计入损益(K列)", "本期计提 − 本期转回（转回按正数录入）", "计算",
             "calcNetImpairmentLoss（= currentAudited）", "useG14Detail / useG14FormulaEngine"),
            ("减值准备期末(J列)", "期初 + 计提 − 转回 − 转销 + 其他变动", "计算",
             "calcProvisionRollForward", "useG14FormulaEngine"),
            ("准备滚动核对", "期初+计提−转回−转销+其他 = 期末实际（容差 0.01）", "logic_check",
             "isRollForwardBalanced", "useG14FormulaEngine"),
            ("审定 ↔ 计入损益核对", "审定数 D = 计入损益 K（容差 0.01）", "logic_check",
             "isReconciled", "useG14FormulaEngine"),
        ],
        # G14-3 调整分录
        "G14-3": [
            ("借贷平衡校验", "|Σ借方 − Σ贷方| < 0.01", "logic_check",
             "调整分录借贷平衡（isDebitCreditBalanced）", "useG14Adjustment / useG14FormulaEngine"),
        ],
        "附注上市": [
            ("附注披露金额", "取自 G14-1 审定表（信用减值损失各来源审定数）", "取数",
             "附注取审定数（各减值来源 ECL：G2/G4/G5/G6 等经 G14_ECL_CROSS_REF 引用）", "useG14Disclosure / g14Constants"),
        ],
        "附注国企": [
            ("附注披露金额", "取自 G14-1 审定表（信用减值损失各来源审定数）", "取数",
             "附注取审定数", "useG14Disclosure"),
        ],
    },
}

