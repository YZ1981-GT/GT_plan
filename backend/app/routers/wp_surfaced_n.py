"""N 循环（税项）底稿公式 surfacing 目录（与各 useN{n}* composable 同源，不臆造）。

对齐 E1 标准（wp_formula._E1_SHEET_FORMULAS）与 D 循环（wp_surfaced_d）：把「专属组件
底稿」（数据存 checklist_responses、无 wp_formula 网格记录）的取数/计算/逻辑审核公式以
只读条目 surface 到公式管理中心，让每张 sheet 都能体现其取数逻辑。

每条公式均可在对应前端 composable 中找到依据（calc 函数 / 跨 sheet 键 / TB 核对 /
合计聚合）；找不到依据的 sheet 不写（宁缺勿造）。

分类只用三种：
  - 取数     跨 sheet / 跨底稿(N1↔N3↔N5 / A利润表 / I6/I2) / 从明细带入 / 回写TB / 回填
  - 计算     表间计算（审定=未审+AJE+RJE、期末余额、递延税=差异×税率、应纳税所得额、
             有效税率、加权平均税率、合计、变动额、变动率等）
  - logic_check  逻辑审核（审定↔明细勾稽、审定↔测算表核对、行级期末=审定校验、
             N1/N3 递延核对差异、账面↔申报表差异、弥补期限届满、亏损判定等）

科目方向（以各 composable ACCOUNT_CODE / 引擎 docstring 核实）：
  N1 递延所得税资产 1811：资产借方 → 期末余额 = 期初 + 借方 − 贷方
  N2 应交税费       2221：负债贷方 → 期末余额 = 期初 + 贷方(计提) − 借方(缴纳)
  N3 递延所得税负债 2901：负债贷方 → 期末余额 = 期初 + 贷方(确认) − 借方(转回)
  N4 税金及附加     6403：损益借方 → 取发生额 = 借方发生 − 贷方发生
  N5 所得税费用     6801：损益借方 → 取发生额（当期 + 递延）

审定数公式在资产/负债/损益类中相同（审定 = 未审 + AJE + RJE），差异在取数口径
（资产/负债取余额，损益取发生额）。
"""
from __future__ import annotations

SheetFormula = tuple[str, str, str, str, str]  # (项目名, 公式, 分类, 说明, 来源)

CATALOG: dict[str, dict[str, list[SheetFormula]]] = {
    # ═══════════════════════════════════════════════════════════════════════
    # N1 递延所得税资产（资产借方 1811；暂时性差异×税率=递延税；含可弥补亏损）
    # ═══════════════════════════════════════════════════════════════════════
    "N1": {
        # N1-1 审定表（7 类资产侧暂时性差异；期初/期末各 未审/AJE/RJE/审定 双期）
        "N1-1": [
            ("期初审定数", "期初未审 + 期初AJE + 期初RJE", "计算",
             "期初审定（calcAuditedAmount）", "useN1Adjudication / useN1FormulaEngine"),
            ("期末审定数", "期末未审 + 期末AJE + 期末RJE", "计算",
             "期末审定（calcAuditedAmount）", "useN1Adjudication / useN1FormulaEngine"),
            ("变动额(审定)", "期末审定数 − 期初审定数", "计算",
             "本期审定较期初变动额（changeAudited）", "useN1Adjudication"),
            ("变动率", "IF(期初=0∧变动=0,0; 期初=0∧变动>0,1; 变动÷期初)", "计算",
             "变动占比（calcChangeProportion，xlsx K 列公式模式）", "useN1FormulaEngine"),
            ("合计", "Σ 各暂时性差异项目", "计算",
             "审定表合计行（calcSubtotal）", "useN1Adjudication / useN1FormulaEngine"),
            ("审定表 ↔ N1-2 明细表勾稽", "N1-1 审定期末合计 − N1-2 明细期末递延税资产合计", "logic_check",
             "审定↔明细勾稽（adjudicationVsDetail，|diff|<0.01 匹配）", "useN1CrossSheet"),
            ("审定确认额 ↔ N1-4 测算表核对", "N1-1 审定确认额 − N1-4 测算递延税资产合计(资产部分)", "logic_check",
             "审定↔测算勾稽（adjudicationVsCalcTable）", "useN1CrossSheet"),
            ("审定合计回写 TB(1811)", "期末审定合计 → trial_balance 1811 期末余额", "取数",
             "审定数变化触发 TB 回写（watch endAudited → writebackTB）", "useN1Adjudication / useN1FormData"),
            ("本期变动额 → N5-8", "期末审定 − 期初审定 → N5-8 递延所得税费用核对", "取数",
             "递延税资产本期变动供 N5 核对（deferredTaxChange）", "useN1CrossSheet"),
        ],
        # N1-2 明细表（暂时性差异×税率=递延税资产，含加权平均税率）
        "N1-2": [
            ("可抵扣暂时性差异", "MAX(0, 计税基础 − 账面价值)", "计算",
             "资产项：账面 < 计税基础时产生（deductibleDiff）", "useN1Detail"),
            ("递延税资产期初余额", "ROUND(暂时性差异(期初) × 适用税率(期初), 2)", "计算",
             "期初递延税资产（calcDeferredTax）", "useN1DeferredTaxEngine"),
            ("递延税资产期末余额", "ROUND(可抵扣暂时性差异 × 适用税率(期末), 2)", "计算",
             "期末递延税资产（calcDeferredTax）", "useN1DeferredTaxEngine"),
            ("期初/期末审定", "递延税资产 + AJE + RJE", "计算",
             "明细行审定（calcAuditedAmount）", "useN1Detail / useN1FormulaEngine"),
            ("分类小计", "Σ 同类别行", "计算",
             "按暂时性差异类别小计（calcSubtotal）", "useN1Detail"),
            ("加权平均税率", "Σ 各项递延税额 ÷ Σ 各项可抵扣差异", "计算",
             "底部统计（calcWeightedAvgRate，差异合计=0 返 0）", "useN1DeferredTaxEngine"),
        ],
        # N1-4 测算表（可抵扣/应纳税暂时性差异分列 → 资产 N1 / 负债 N3）
        "N1-4": [
            ("暂时性差异", "账面价值 − 计税基础", "计算",
             "第一步差异（calcTemporaryDifference）", "useN1DeferredTaxEngine"),
            ("可抵扣暂时性差异", "IF(账面−计税<0, 计税−账面, 0)", "计算",
             "可抵扣差异（calcDeductibleDiff）→ 递延税资产", "useN1DeferredTaxEngine"),
            ("应纳税暂时性差异", "IF(账面−计税>0, 账面−计税, 0)", "计算",
             "应纳税差异（calcTaxableDiff）→ 递延税负债", "useN1DeferredTaxEngine"),
            ("递延所得税资产", "IF(可抵扣差异=0, 0, 可抵扣差异 × 适用税率)", "计算",
             "资产部分（calcDeferredTaxAsset，零值保护）", "useN1DeferredTaxEngine"),
            ("递延所得税负债", "IF(应纳税差异=0, 0, 应纳税差异 × 适用税率)", "计算",
             "负债部分（calcDeferredTaxLiability），联动 N3", "useN1DeferredTaxEngine"),
            ("应确认与账面差异", "应确认金额 − 实际账面金额", "计算",
             "应调整列，正=追加确认/负=转回（calcDeferredTaxDiff）", "useN1DeferredTaxEngine"),
            ("资产/负债分列", "可抵扣差异→N1(资产)；应纳税差异→N3(负债)", "取数",
             "同源暂时性差异分列，同主体可抵销/异主体分列（n1ToN3Correspondence）", "useN1CrossSheet"),
            ("可弥补亏损行取自 N1-5", "N1-5 可确认递延税资产合计 → N1-4 可弥补亏损行", "取数",
             "亏损可确认额回填测算表（lossCheckToCalcTable）", "useN1CrossSheet"),
        ],
        # N1-5 可弥补亏损检查表（谨慎性原则 + 弥补期限）
        "N1-5": [
            ("未弥补亏损", "MAX(0, 亏损金额 − 已弥补金额)", "计算",
             "未弥补亏损（calcUnrecoveredLoss）", "useN1LossCompensationEngine"),
            ("已弥补金额合计", "期初已弥补 + 本期弥补", "计算",
             "累计已弥补（totalRecovered）", "useN1LossCheck"),
            ("可确认递延税资产", "MIN(未弥补亏损, 预计未来应纳税所得额) × 适用税率", "计算",
             "谨慎性上限（calcRecognizableAsset，CAS18 第15条）", "useN1LossCompensationEngine"),
            ("弥补截止年度", "亏损年度 + 最长弥补年限", "计算",
             "一般 5 年 / 高新·科技型中小企业 10 年（expiryYear）", "useN1LossCheck"),
            ("剩余弥补年限", "MAX(0, 亏损年度 + 最长弥补年限 − 当前年度)", "计算",
             "剩余可弥补时间（calcRemainingYears）", "useN1LossCompensationEngine"),
            ("弥补期限届满判定", "当前年度 > 亏损年度 + 最长弥补年限 → 届满(标红,不可确认)", "logic_check",
             "届满不再确认递延税资产（isCompensationExpired）", "useN1LossCompensationEngine"),
            ("预计不足预警", "未届满 ∧ 预计未来应纳税所得额 < 未弥补亏损 ∧ 未弥补>0", "logic_check",
             "标黄警告（isInsufficient）", "useN1LossCheck"),
            ("可确认合计 → N1-4", "Σ 各年度可确认递延税资产 → N1-4 可弥补亏损行", "取数",
             "回填测算表（N1-5-total-recognizable）", "useN1LossCheck"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # N2 应交税费（负债贷方 2221；多税种测算 + N4 计提联动）
    # ═══════════════════════════════════════════════════════════════════════
    "N2": {
        # N2-1 审定表（13 类税种 + 其他）
        "N2-1": [
            ("期末余额", "期初 + 本期贷方(计提) − 本期借方(缴纳)", "计算",
             "负债类期末余额（calcLiabilityEndBalance）", "useN2Adjudication / useN2FormulaEngine"),
            ("审定数", "未审 + AJE + RJE", "计算",
             "各税种行审定（calcAuditedAmount）", "useN2Adjudication / useN2FormulaEngine"),
            ("合计", "Σ 各税种行", "计算",
             "审定表合计（calcSubtotal）", "useN2Adjudication"),
            ("行级校验(期末=审定)", "期末余额 − 审定数", "logic_check",
             "审定表合一逻辑：每行期末余额应=审定数（rowValidations，|diff|≤0.01）", "useN2Adjudication"),
            ("审定表 ↔ N2-2 明细表勾稽", "N2-1 审定期末合计 − N2-2 明细期末合计", "logic_check",
             "两侧均按负债类 期末=期初+计提−缴纳 现算（adjudicationVsDetail）", "useN2CrossSheet"),
            ("各税种 ↔ 测算表核对", "N2-1 各税种审定 − 对应测算表(N2-6/N2-8/N2-9/N2-10)结果", "logic_check",
             "逐税种交叉验证（adjudicationVsCalcTables）", "useN2CrossSheet"),
            ("审定合计回写 TB(2221)", "审定合计 → trial_balance 2221 期末余额", "取数",
             "TB 回写（triggerWriteback → writebackTB）", "useN2Adjudication / useN2FormData"),
            ("各税种计提额 → N4", "Σ 计入税金及附加税种的本期贷方(计提)发生额 → N4", "取数",
             "计提额联动税金及附加（accrualToN4，排除增值税/所得税；EventBus tax-accrual:updated）",
             "useN2CrossSheet"),
        ],
        # N2-2 明细表
        "N2-2": [
            ("期末余额", "期初 + 计提(贷) − 缴纳(借)", "计算",
             "负债类明细期末余额（现算，存储字段 beginning/accrual/payment）", "useN2CrossSheet"),
            ("账面 ↔ 申报表差异", "账面金额 − 申报表金额", "logic_check",
             "差异≠0 红色高亮须填原因（calcDiff）", "useN2FormulaEngine"),
        ],
        # N2-8 城建税及附加测算
        "N2-8": [
            ("城建税/教育费附加/地方教育附加", "(增值税 + 消费税) × 适用税率", "计算",
             "城建税 7%/5%/1%、教育费附加 3%、地方教育附加 2%（calcSurtax）", "useN2MultiTaxEngine"),
            ("计税依据取自 N2-6", "N2-6 应交增值税 → N2-8 城建税及附加计税依据", "取数",
             "增值税测算结果 feeds 附加税（vatToSurtax）", "useN2CrossSheet"),
        ],
        # N2-9 房产税测算
        "N2-9": [
            ("房产税(从价)", "房产原值 × (1 − 扣除比例) × 1.2%", "计算",
             "从价计征（calcPropertyTaxByValue，扣除比例各省 0.10~0.30）", "useN2MultiTaxEngine"),
            ("房产税(从租)", "租金收入 × 12%", "计算",
             "从租计征（calcPropertyTaxByRent）", "useN2MultiTaxEngine"),
        ],
        # N2-10 土地增值税测算
        "N2-10": [
            ("增值率", "增值额 ÷ 扣除项目金额", "计算",
             "匹配四级超率累进档次（calcAppreciationRate，扣除项=0 返 0）", "useN2MultiTaxEngine"),
            ("应交土地增值税", "增值额 × 适用税率 − 扣除项目金额 × 速算扣除系数", "计算",
             "四级累进 30%/40%/50%/60%（calcLandVat）", "useN2MultiTaxEngine"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # N3 递延所得税负债（负债贷方 2901；应纳税暂时性差异×税率=递延税负债）
    # ═══════════════════════════════════════════════════════════════════════
    "N3": {
        # N3-1 审定表（5 类应纳税暂时性差异）
        "N3-1": [
            ("期末余额", "期初 + 本期贷方(确认) − 本期借方(转回)", "计算",
             "负债类期末余额（calcLiabilityEndBalance）", "useN3Adjudication / useN3FormulaEngine"),
            ("审定数", "未审 + AJE + RJE", "计算",
             "各项目行审定（calcAuditedAmount）", "useN3Adjudication / useN3FormulaEngine"),
            ("变动额", "期末 − 期初", "计算",
             "本期变动额（calcChange）", "useN3FormulaEngine"),
            ("变动率", "IF(期初=0∧变动=0,0; 期初=0∧变动>0,1; 变动÷期初)", "计算",
             "xlsx 公式模式（calcChangeRate）", "useN3FormulaEngine"),
            ("合计", "Σ 各应纳税暂时性差异项目", "计算",
             "审定表合计（calcSubtotal）", "useN3Adjudication"),
            ("行级校验(期末=审定)", "期末余额 − 审定数", "logic_check",
             "审定表合一逻辑（rowValidations，|diff|≤0.01）", "useN3Adjudication"),
            ("审定表 ↔ N3-2 明细表勾稽", "N3-1 审定合计 − N3-2 明细期末递延税负债合计", "logic_check",
             "SUMIF 等价交叉验证（crossValidation / adjudicationVsDetail）", "useN3Adjudication / useN3CrossSheet"),
            ("与 N1 对应关系", "同一纳税主体可抵销后净额列示；不同主体 N1/N3 分列", "logic_check",
             "递延税资产/负债抵销判定（n3ToN1Correspondence）", "useN3CrossSheet"),
            ("审定合计回写 TB(2901)", "审定合计 → trial_balance 2901 期末余额", "取数",
             "TB 回写（triggerWriteback → writebackTB）", "useN3Adjudication / useN3FormData"),
            ("本期变动额 → N5-8", "期末审定 − 期初 → N5-8 递延所得税费用核对", "取数",
             "递延税负债本期变动供 N5 核对（deferredTaxChange；EventBus deferred-tax:liability-updated）",
             "useN3CrossSheet"),
        ],
        # N3-2 明细表
        "N3-2": [
            ("应纳税暂时性差异", "账面价值 − 计税基础", "计算",
             "应纳税差异（calcTaxableTemporaryDifference）", "useN3DeferredTaxEngine"),
            ("期末递延所得税负债", "ROUND(应纳税暂时性差异 × 适用税率, 2)", "计算",
             "递延税负债（calcDeferredTaxLiabilityRounded）", "useN3DeferredTaxEngine"),
            ("加权平均税率", "Σ 各项递延税负债 ÷ Σ 各项应纳税差异", "计算",
             "统计摘要（calcWeightedAvgRate）", "useN3DeferredTaxEngine"),
            ("特殊项不确认判定", "商誉/长期股权投资拟长期持有 → 期末递延税负债=0", "logic_check",
             "特殊项不确认递延税负债（isSpecialNonRecognitionItem）", "useN3DeferredTaxEngine"),
            ("转回项判定", "期末递延税负债=0 ∧ 期初>0 ∧ 非特殊项 → 已转回(灰色)", "logic_check",
             "转回行标识（isReversed）", "useN3Detail"),
            ("按分类汇总(SUMIF) → N3-1", "按分类 Σ 期末递延税负债 → N3-1 审定表各分类行", "取数",
             "分类汇总供审定表（categoryTotals，跳过特殊项）", "useN3Detail"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # N4 税金及附加（损益借方发生额 6403；N2 计提对应 + A 利润表勾稽）
    # ═══════════════════════════════════════════════════════════════════════
    "N4": {
        # N4-1 审定表（10 税种行）
        "N4-1": [
            ("本期审定数", "本期未审(发生额) + AJE + RJE", "计算",
             "损益类各税种审定（calcAuditedAmount）", "useN4Adjudication / useN4FormulaEngine"),
            ("合计", "Σ 各税种行", "计算",
             "审定表合计（calcSubtotal）", "useN4Adjudication / useN4FormulaEngine"),
            ("同比变动率", "(本期审定 − 上期审定) ÷ 上期审定", "计算",
             "上期=0 返 null 显示「—」（calcYoyChange）", "useN4FormulaEngine"),
            ("审定表 ↔ N4-2 明细表勾稽", "N4-1 审定合计 − N4-2 明细本期合计", "logic_check",
             "同源两视图应一致（detailCrossValidation，|diff|<0.01）", "useN4Adjudication / useN4CrossSheet"),
            ("N4 费用确认 ↔ N2 计提额核对", "N4 各税种费用确认 − N2 各税种本期计提额", "logic_check",
             "费用确认=计提（n4VsN2Accrual，差异≠0 红色高亮；税种名归一化匹配）", "useN4CrossSheet"),
            ("审定合计回写 TB(6403)", "审定合计(发生额) → trial_balance 6403", "取数",
             "损益类发生额回写（writeback → writebackTB）", "useN4Adjudication / useN4FormData"),
            ("审定合计 → A 利润表", "税金及附加审定合计 → A 利润表「税金及附加」行", "取数",
             "供利润表勾稽（toIncomeStatement；EventBus expense:taxes-surcharges-updated）", "useN4CrossSheet"),
        ],
        # N4-2 明细表
        "N4-2": [
            ("本期税额", "计税依据 × 适用税率", "计算",
             "各税种本期税额（periodAmount；分税种专用公式见 useN4MultiTaxEngine）", "useN4Detail"),
            ("同比变动率", "(本期税额 − 上期税额) ÷ 上期税额", "计算",
             "上期=0 返 null（calcYoyChange）", "useN4FormulaEngine"),
            ("N2 计提差异", "本期税额 − N2 计提额", "logic_check",
             "差异≠0 标红（diff，N2 计提额来自 EventBus tax-accrual:updated）", "useN4Detail"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # N5 所得税费用（损益借方发生额 6801；当期 + 递延 + 有效税率调节）
    # ═══════════════════════════════════════════════════════════════════════
    "N5": {
        # N5-1 审定表（当期 + 递延 = 所得税费用；有效税率）
        "N5-1": [
            ("所得税费用合计", "当期所得税费用 + 递延所得税费用", "计算",
             "所得税费用合计（calcIncomeTaxExpense / adjudicationVsCalc.total）", "useN5IncomeTaxEngine / useN5CrossSheet"),
            ("当期所得税费用取自 N5-4", "N5-4 当期应纳所得税额 → N5-1 当期所得税费用行", "取数",
             "N5-4 回填（读 N5-1-current-tax，syncCurrentTaxToAdjudication）", "useN5CrossSheet / useN5CurrentTaxCalc"),
            ("递延所得税费用取自 N5-8", "N5-8 递延所得税费用 → N5-1 递延所得税费用行", "取数",
             "N5-8 回填（读 N5-1-deferred-tax，syncDeferredExpenseToAdjudication）",
             "useN5CrossSheet / useN5DeferredReconcile"),
            ("有效税率", "所得税费用合计 ÷ 会计利润总额", "计算",
             "合理性分析，会计利润=0 返 null（calcEffectiveTaxRate）", "useN5CrossSheet / useN5FormulaEngine"),
            ("所得税费用 → A 利润表", "所得税费用合计 → A 利润表「所得税费用」行", "取数",
             "供利润表勾稽（publishIncomeTaxUpdated；EventBus income-tax:updated）", "useN5CrossSheet"),
        ],
        # N5-4 当期所得税费用计算表（会计利润 → 应纳税所得额 → 当期所得税）
        "N5-4": [
            ("应纳税所得额", "会计利润总额 + 纳税调增合计 − 纳税调减合计", "计算",
             "计算链核心（calcTaxableIncome）", "useN5IncomeTaxEngine / useN5CurrentTaxCalc"),
            ("应纳所得税额", "应纳税所得额 × 适用税率", "计算",
             "亏损(应纳税所得额≤0)时为 0（calcCurrentTax）", "useN5IncomeTaxEngine / useN5CurrentTaxCalc"),
            ("当期应纳所得税额", "MAX(0, 应纳所得税额 − 减免税额 − 抵免税额)", "计算",
             "当期所得税不为负（currentTax）", "useN5CurrentTaxCalc"),
            ("亏损判定", "应纳税所得额 < 0 → 亏损(当期所得税=0)", "logic_check",
             "亏损标记（isLoss）", "useN5CurrentTaxCalc"),
            ("会计利润总额取自 A 利润表", "A 利润表利润总额 → N5-4 会计利润总额", "取数",
             "跨底稿取数（accountingProfit；profitFromIncomeStatement）", "useN5CurrentTaxCalc / useN5CrossSheet"),
            ("纳税调增/调减合计取自 N5-5", "N5-5 调增合计/调减合计 → N5-4", "取数",
             "纳税调整回填（addBackTotal / deductTotal）", "useN5CurrentTaxCalc"),
            ("减免税额取自 N5-6", "N5-6 减免税额合计 → N5-4 减免所得税额行", "取数",
             "税收优惠回填（taxRelief）", "useN5CurrentTaxCalc"),
            ("加计扣除额取自 N5-6-1", "N5-6-1 加计扣除额 → 纳税调减", "取数",
             "研发加计扣除回填（superDeduction）", "useN5CurrentTaxCalc"),
            ("当期所得税 → 回填 N5-1", "N5-4 当期应纳所得税额 → N5-1 审定表", "取数",
             "回填审定表（syncCurrentTaxToAdjudication）", "useN5CurrentTaxCalc"),
        ],
        # N5-5 纳税调整明细表（5 大类：收入/扣除/资产/特殊事项/其他）
        "N5-5": [
            ("调增合计", "Σ 各行调增金额", "计算",
             "纳税调增合计（calcSubtotal）", "useN5TaxAdjustment / useN5FormulaEngine"),
            ("调减合计", "Σ 各行调减金额", "计算",
             "纳税调减合计（calcSubtotal）", "useN5TaxAdjustment / useN5FormulaEngine"),
            ("调整净额", "调增合计 − 调减合计", "计算",
             "净调整额（calcNetAdjustment）", "useN5TaxAdjustment / useN5TaxAdjustmentEngine"),
            ("各类小计", "Σ 同类(收入类/扣除类/资产类/特殊事项/其他)行调增/调减", "计算",
             "分类小计（categorySubtotals）", "useN5TaxAdjustment"),
            ("调增/调减合计 → 回填 N5-4", "N5-5 调增合计/调减合计 → N5-4 计算表", "取数",
             "回填当期计算表（syncTotalsToCurrentTaxCalc）", "useN5TaxAdjustment"),
            ("研发费用加计扣除行 → N5-6-1", "研发费用加计扣除行联动 N5-6-1", "取数",
             "加计扣除联动（linkedSource='N5-6-1'）", "useN5TaxAdjustment"),
        ],
        # N5-6 税收优惠（减免税额）
        "N5-6": [
            ("减免税额合计 → N5-4", "N5-6 减免税额合计 → N5-4 减免所得税额行", "取数",
             "税收优惠减免额（N5-6-tax-relief-total）", "useN5CurrentTaxCalc"),
        ],
        # N5-6-1 加计扣除研发费用情况明细表（6 大费用类别）
        "N5-6-1": [
            ("研发费用合计", "人员人工 + 直接投入 + 折旧费用 + 无形资产摊销 + 其他费用", "计算",
             "各项目研发费用合计（totalExpense = calcSubtotal）", "useN5RdSuperDeduction / useN5FormulaEngine"),
            ("费用化加计扣除额", "费用化研发费用 × 加计比例", "计算",
             "费用化加计（calcRdSuperDeduction，一般企业 100%）", "useN5RdSuperDeduction / useN5IncomeTaxEngine"),
            ("资本化加计扣除额", "资本化研发费用 × 加计比例", "计算",
             "资本化加计（calcRdSuperDeduction）", "useN5RdSuperDeduction / useN5IncomeTaxEngine"),
            ("加计扣除额合计", "费用化加计 + 资本化加计", "计算",
             "加计扣除额合计（totalDeduction）", "useN5RdSuperDeduction"),
            ("研发费用取自 I6/I2", "I6 费用化研发费用 + I2 资本化开发支出 → N5-6-1", "取数",
             "跨底稿研发费用取数（setFromI6I2；rdFromI6I2）", "useN5RdSuperDeduction / useN5CrossSheet"),
            ("加计扣除额 → 回填 N5-5", "N5-6-1 加计扣除额合计 → N5-5 纳税调减项", "取数",
             "回填纳税调整（syncDeductionToTaxAdjustment）", "useN5RdSuperDeduction"),
        ],
        # N5-8 递延所得税费用核对表（N1/N3 递延变动核对）
        "N5-8": [
            ("递延税资产本期变动", "递延税资产期末 − 递延税资产期初", "计算",
             "资产本期变动（assetChange）", "useN5DeferredReconcile"),
            ("递延税负债本期变动", "递延税负债期末 − 递延税负债期初", "计算",
             "负债本期变动（liabilityChange）", "useN5DeferredReconcile"),
            ("递延所得税费用", "递延税负债本期增加 − 递延税资产本期增加", "计算",
             "递延所得税费用（calcDeferredTaxExpense）", "useN5DeferredReconcile / useN5IncomeTaxEngine"),
            ("与 N1 核对差异", "本表资产变动合计 − N1 传入递延税资产本期变动", "logic_check",
             "N1 核对（n1Diff，|diff|≤0.01）", "useN5DeferredReconcile"),
            ("与 N3 核对差异", "本表负债变动合计 − N3 传入递延税负债本期变动", "logic_check",
             "N3 核对（n3Diff，|diff|≤0.01）", "useN5DeferredReconcile"),
            ("核对通过判定", "|N1 差异| ≤ 0.01 ∧ |N3 差异| ≤ 0.01", "logic_check",
             "整体核对（isReconciled）", "useN5DeferredReconcile"),
            ("从 N1 接收递延税资产变动", "N1-1 期末审定 − 期初审定 → N5-8", "取数",
             "订阅 deferred-tax:asset-updated（n1AssetChange）", "useN5DeferredReconcile / useN5CrossSheet"),
            ("从 N3 接收递延税负债变动", "N3-1 期末审定 − 期初审定 → N5-8", "取数",
             "订阅 deferred-tax:liability-updated（n3LiabilityChange）", "useN5DeferredReconcile / useN5CrossSheet"),
            ("递延所得税费用 → 回填 N5-1", "N5-8 递延所得税费用 → N5-1 审定表", "取数",
             "回填审定表（syncDeferredExpenseToAdjudication）", "useN5DeferredReconcile"),
        ],
    },
}
