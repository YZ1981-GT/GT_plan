"""J 循环底稿公式 surfacing 目录（与各 useJ{n}* composable 同源，不臆造）。

对齐 E1 标准（wp_formula._E1_SHEET_FORMULAS）+ D 循环 surfacing（wp_surfaced_d）：
把「专属组件底稿」（数据存 checklist_responses、无 wp_formula 网格记录）的取数/计算/
逻辑审核公式以只读条目 surface 到公式管理中心，让每张 sheet 都能体现其取数逻辑。

每条公式均可在对应前端 composable 中找到依据（calc 函数 / 跨 sheet 键 / TB 核对 /
合计聚合 / 精算-期权定价引擎）；找不到依据的 sheet 不写（宁缺勿造）。

分类只用三种：
  - 取数     跨 sheet / 从明细带入 / 抽凭样本回填
  - 计算     表间计算（审定=未审+AJE+RJE、负债期末=期初+增-减、变动额/率、合计、
             人均/测算/摊销、DBO 六要素、BS 期权定价等）
  - logic_check  逻辑审核（TB 核对、审定↔明细勾稽、分配闭合、差异率阈值、
             精算假设范围、CAS9 条件、借贷平衡等）

科目方向（负债贷方：期末 = 期初 + 贷方发生(增加) − 借方发生(减少)）：
  - J1 应付职工薪酬     2211（负债贷方，useJ1FormulaEngine / useJ1Integration 回写 2211）
  - J2 长期应付职工薪酬 2221（负债贷方，useJ2FormulaEngine / useJ2Integration 回写 2221）
  - J3 股份支付         无单一 TB 回写；跨科目（资本公积 3002 / 应付职工薪酬 2211 /
             管理费用 6602），费用确认走 EventBus 分流 M4/J1/K8-K9（useJ3FormData /
             useJ3CrossSheet / useJ3Integration）
"""
from __future__ import annotations

SheetFormula = tuple[str, str, str, str, str]  # (项目名, 公式, 分类, 说明, 来源)

CATALOG: dict[str, dict[str, list[SheetFormula]]] = {
    # ═══════════════════════════════════════════════════════════════════════
    # J1 应付职工薪酬（负债贷方 2211；短期薪酬/离职后福利/辞退福利/其他长期）
    # ═══════════════════════════════════════════════════════════════════════
    "J1": {
        # J1-1 审定表（四分类 × 期初/期末 × 未审/调整/审定 + 变动分析）
        "J1-1": [
            ("审定数", "未审数 + 账项调整(AJE) + 重分类调整(RJE)", "计算",
             "各行期初/期末审定金额（calcAuditedAmount）", "useJ1Adjudication / useJ1FormulaEngine"),
            ("分类小计", "Σ 该分类明细行", "计算",
             "短期薪酬/离职后福利/辞退福利/其他长期 各分类小计（calcSubtotal）", "useJ1Adjudication"),
            ("合计", "Σ 四分类小计（期初/期末 审定数）", "计算",
             "审定表合计行（grandTotal）", "useJ1Adjudication"),
            ("变动额", "期末审定 − 期初审定", "计算",
             "本期较期初变动额（calcChangeDiff）", "useJ1FormulaEngine"),
            ("变动率", "IF(期初=0∧期末=0→0; 期初=0∧期末>0→100%; 其他→变动额÷期初审定)", "计算",
             "期初=0 特殊处理（calcChangeRate）", "useJ1FormulaEngine"),
            ("审定表 ↔ 明细表核对", "J1-1 审定合计 − J1-2 明细期末合计", "logic_check",
             "审定表与明细表勾稽（adjudicationVsDetail：J1-1-audited-total vs J1-2-end-total，容差 0.01）",
             "useJ1CrossSheet"),
            ("试算平衡表数核对", "审定合计 − 试算平衡表数(2211)", "logic_check",
             "审定合计与 TB 应付职工薪酬(2211)核对，差异须查明", "useJ1Integration"),
        ],
        # J1-2 明细表（3 分区：短期/离职后·其他长期/辞退，14 列宽表）
        "J1-2": [
            ("未审-期末数", "未审期初 + 本期增加 − 本期减少", "计算",
             "负债贷方口径期末（calcLiabilityEndBalance，2211 期末=期初+增-减）", "useJ1FormulaEngine"),
            ("审定-期初数", "未审期初 + 期初调整", "计算",
             "明细审定期初（recalcRow）", "useJ1Detail"),
            ("审定-本期增加", "未审增加 + 账项调整增加", "计算",
             "明细审定增加（recalcRow）", "useJ1Detail"),
            ("审定-本期减少", "未审减少 + 账项调整减少", "计算",
             "明细审定减少（recalcRow）", "useJ1Detail"),
            ("审定-期末数", "审定期初 + 审定增加 − 审定减少", "计算",
             "明细审定期末（calcLiabilityEndBalance）", "useJ1Detail / useJ1FormulaEngine"),
            ("分区合计", "Σ 分区内非「其中」子项（indent=0）", "计算",
             "只对大类行求和避免子项重复（calcSectionTotal）", "useJ1Detail"),
            ("全表合计", "Σ 三分区合计", "计算",
             "应付职工薪酬合计（grandTotal）", "useJ1Detail"),
        ],
        # J1-3 调整分录汇总表
        "J1-3": [
            ("借贷平衡校验", "Σ 借方调整金额 = Σ 贷方调整金额", "logic_check",
             "调整分录借贷平衡", "J1-3 调整分录汇总表"),
            ("AJE/RJE 回写审定表", "按科目将账项调整(AJE)/重分类调整(RJE)累加到 J1-1 审定表对应行", "取数",
             "监听 adjustment:created 回写 J1-1", "useJ1Adjudication / J1TabAdjustment"),
        ],
        # J1-4 月度分析表（8 指标区块 × 部门 × 12 月）
        "J1-4": [
            ("本期人均工资", "本期计提工资合计 ÷ 本期员工数量", "计算",
             "各月人均（currentAvgWage，除零返 0）", "useJ1MonthlyAnalysis"),
            ("上期人均工资", "上期计提工资合计 ÷ 上期员工数量", "计算",
             "上期各月人均（priorAvgWage）", "useJ1MonthlyAnalysis"),
            ("人均工资变动率", "(本期人均 − 上期人均) ÷ 上期人均", "计算",
             "人均变动率（avgWageChangeRate → calcChangeRate）", "useJ1MonthlyAnalysis"),
            ("各月计提占比", "当月计提合计 ÷ 全年计提合计 × 100%", "计算",
             "月度占比（monthlyProportion）", "useJ1MonthlyAnalysis"),
            ("月度合计", "Σ(1月 ~ 12月)", "计算",
             "月度分析各行年合计（calcMonthlyTotal）", "useJ1FormulaEngine"),
            ("月度异常检测", "|(当月计提 − 部门月均) ÷ 部门月均| > 30%", "logic_check",
             "月度偏离均值超阈值高亮（fluctuations）", "useJ1MonthlyAnalysis"),
            ("月度分析 ↔ 审定表核对", "J1-4 年度合计 − J1-1 审定合计", "logic_check",
             "月度分析合计与审定表核对（monthlyVsAdjudication：J1-4-annual-total vs J1-1-audited-total）",
             "useJ1CrossSheet"),
        ],
        # J1-5 与同行业对比分析表（4 区块）
        "J1-5": [
            ("本期人均", "本期薪酬总额 ÷ 本期人数", "计算",
             "公司薪酬总览人均（recalcDeptRow / calcPerCapitaSalary）", "useJ1IndustryCompare / useJ1SalaryCalc"),
            ("薪酬占收入比", "本期薪酬总额 ÷ 营业收入 × 100%", "计算",
             "薪酬强度指标（revenueRatio / calcSalaryRevenueRatio）", "useJ1IndustryCompare / useJ1SalaryCalc"),
            ("人均工资变动率", "(本期人均 − 上期人均) ÷ 上期人均", "计算",
             "人均变动率（avgChangeRate）", "useJ1IndustryCompare"),
            ("与行业差异率", "(公司人均 − 行业均值) ÷ 行业均值 × 100%", "计算",
             "行业差异率（industryDiff / calcIndustryDiffRate）", "useJ1IndustryCompare / useJ1SalaryCalc"),
            ("同行业人均(生产人员)", "行业人工成本 ÷ 行业人数", "计算",
             "对比表人均工资（recalcProdRow.avgWage）", "useJ1IndustryCompare"),
            ("人均产出", "营业收入 ÷ 人数", "计算",
             "同行业人均产出（perCapitaOutput）", "useJ1IndustryCompare"),
            ("人工成本占比", "人工成本 ÷ 总成本 × 100%", "计算",
             "同行业成本占比（costRatio）", "useJ1IndustryCompare"),
            ("社保人数核对", "(公司发放工资人数 − 免缴人数) − 各类社保上交人数合计", "logic_check",
             "工资人数 vs 社保人数差异（socialLeftTotal − socialRightTotal = socialDiff）", "useJ1IndustryCompare"),
        ],
        # J1-6 计提情况检查表（人数×均薪测算 vs 实际计提）
        "J1-6": [
            ("工资应提", "人数 × 月均薪酬 × 月数", "计算",
             "工资测算（calcSalaryEstimate）", "useJ1SalaryCalc"),
            ("社保应提", "缴费基数 × 缴纳比例 × 月数", "计算",
             "社保测算（calcInsuranceEstimate）", "useJ1SalaryCalc"),
            ("住房公积金应提", "缴费基数 × 缴纳比例 × 月数", "计算",
             "公积金测算（calcHousingFundEstimate）", "useJ1SalaryCalc"),
            ("计提差异率", "(实际计提 − 应计提) ÷ 应计提 × 100%", "计算",
             "计提差异率（calcAccrualDiffRate，应提=0 返回 null）", "useJ1SalaryCalc"),
            ("计提差异异常", "|计提差异率| > 5%", "logic_check",
             "差异率超阈值须调查原因（isAbnormal / hasAbnormal）", "useJ1AccrualCheck"),
        ],
        # J1-7 分配情况检查表（薪酬费用分配到各科目闭合校验 → K8/K9）
        "J1-7": [
            ("行合计", "管理费用 + 销售费用 + 生产成本 + 制造费用 + 研发费用 + 在建工程 + 其他", "计算",
             "分配行合计（rowTotal = calcSubtotal）", "useJ1AllocationCheck"),
            ("行差额", "行合计 − 明细表贷方增加", "计算",
             "分配 vs 明细贷方增加差额（difference）", "useJ1AllocationCheck"),
            ("分配闭合校验", "|Σ 各费用科目分配 − 薪酬贷方增加合计| < 0.01", "logic_check",
             "分配闭合（validateAllocationClosure / overallClosure，容差 0.01 元）",
             "useJ1AllocationCheck / useJ1FormulaEngine"),
            ("列合计 → K8/K9 联动", "销售费用列合计 → K8；管理费用列合计 → K9", "取数",
             "分配列合计供 K8 销售费用/K9 管理费用联动（totalSelling/totalAdmin）",
             "useJ1AllocationCheck / useJ1CrossSheet"),
            ("分配闭合 ↔ K8/K9 交叉验证", "J1-7 销售/管理费用 − K8/K9 薪酬组成部分", "logic_check",
             "跨底稿交叉验证（crossValidateAllocation，容差 0.01）", "useJ1Integration"),
        ],
        # J1-8 凭证级检查表（复用 useK1VoucherCheck，科目 2211 贷方/负债；三区：贷方计提+借方发放+期后支付）
        "J1-8": [
            ("抽样总体", "测试总体(借方+贷方发生) − 特定样本(大额/关联方/异常)", "计算",
             "抽样总体笔数/金额（computeK1SamplingPopulation）", "useK1VoucherCheck"),
            ("检查比例", "已检查金额 ÷ 账面本期发生额（借方/贷方/期末余额）", "计算",
             "检查比例表（checkRatios，账面=0 返回 null）", "useK1VoucherCheck"),
            ("检查比例偏低", "检查比例 < 30% ∧ 账面金额 > 0", "logic_check",
             "比例偏低需扩样或说明（lowRatioWarnings）", "useK1VoucherCheck"),
            ("五项核对完整", "原始凭证完整 ∧ 账记相符 ∧ 会计处理正确 ∧ 会计期间正确 ∧ 其他核对一致", "logic_check",
             "逐笔五项核对全勾选（isK1VoucherRowChecksComplete）", "useK1VoucherCheck"),
            ("样本量偏差", "实际检查笔数 < 计划抽样样本量 → 需扩样", "logic_check",
             "计划 vs 实际样本量（sampleSizeDeviation）", "useK1VoucherCheck"),
            ("抽凭样本回填", "抽凭引擎样本 → 凭证检查行（按凭证号去重）", "取数",
             "科学抽样回填（fillFromSamples）", "useK1VoucherCheck"),
            ("异常凭证 → 调整备忘", "标记异常的凭证 → J1 调整分录草稿", "取数",
             "异常凭证推送调整备忘（buildAbnormalAdjDrafts）", "useK1VoucherCheck"),
        ],
        # J1-9 非货币性福利检查表
        "J1-9": [
            ("非货币性福利合计", "Σ 各项福利金额", "计算",
             "非货币福利合计（totalAmount = calcSubtotal）", "useJ1NonMonetaryCheck"),
            ("合规性判定", "计量方式(公允/成本/评估)恰当 ∧ 凭证支持 → 合规", "logic_check",
             "非货币福利合规检查（isCompliant / hasNonCompliant）", "useJ1NonMonetaryCheck"),
        ],
        # J1-10 辞退福利检查表（CAS9 确认条件）
        "J1-10": [
            ("预计辞退福利合计", "Σ 各部门预计金额", "计算",
             "预计辞退福利合计（totalEstimated）", "useJ1SeveranceCheck"),
            ("实际计提合计", "Σ 各部门实际计提", "计算",
             "实际计提合计（totalActual）", "useJ1SeveranceCheck"),
            ("CAS9 确认条件全满足", "正式辞退计划 ∧ 已沟通 ∧ 可操作 ∧ 不能撤回 四条件全部满足", "logic_check",
             "CAS9 辞退福利确认（allConditionsMet：四条件全 isMet）", "useJ1SeveranceCheck"),
        ],
        # 附注披露（上市/国企）
        "附注上市": [
            ("期末余额", "期初余额(上年年末) + 本期增加 − 本期减少", "计算",
             "披露变动表期末（calcLiabilityEndBalance，负债贷方）", "useJ1Disclosure / useJ1FormulaEngine"),
            ("附注合计", "Σ 各小计行期末余额", "计算",
             "附注披露合计（totalEnd）", "useJ1Disclosure"),
            ("附注金额取审定数", "取自 J1-1 审定表各分类审定数", "取数",
             "附注披露取审定数（subscribe substantive:adjudicated 刷新）", "useJ1Integration"),
        ],
        "附注国企": [
            ("期末余额", "期初余额 + 本期增加 − 本期减少", "计算",
             "披露变动表期末（calcLiabilityEndBalance，负债贷方）", "useJ1Disclosure / useJ1FormulaEngine"),
            ("附注合计", "Σ 各小计行期末余额", "计算",
             "附注披露合计（totalEnd）", "useJ1Disclosure"),
            ("附注金额取审定数", "取自 J1-1 审定表各分类审定数", "取数",
             "附注披露取审定数", "useJ1Integration"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # J2 长期应付职工薪酬（负债贷方 2221；设定受益计划 / 其他长期福利 / 辞退福利）
    # ═══════════════════════════════════════════════════════════════════════
    "J2": {
        # J2-1 审定表（三区块：设定受益计划/其他长期福利/辞退福利 + 减一年内到期）
        "J2-1": [
            ("审定数", "未审数 + 账项调整(AJE)", "计算",
             "各区块期初/期末审定金额（calcAuditedAmount）", "useJ2Adjudication / useJ2FormulaEngine"),
            ("合计", "设定受益计划 + 其他长期职工福利 + 辞退福利（期初/期末 审定）", "计算",
             "三区块合计行（totalRow）", "useJ2Adjudication"),
            ("列报金额", "合计期末审定 − 减:一年内支付的长期应付职工薪酬", "计算",
             "长期应付职工薪酬净额（reportingAmount）", "useJ2Adjudication"),
            ("变动额", "本期审定 − 上期审定", "计算",
             "本期审定较上期变动额（calcChangeAmount）", "useJ2FormulaEngine"),
            ("变动率", "IF(上期=0∧本期=0→0; 上期=0→100%; 其他→变动额÷上期审定)", "计算",
             "变动率（calcChangeRate，基数=0 特殊处理）", "useJ2FormulaEngine"),
            ("审定表 ↔ 明细表核对", "J2-1 审定期初/期末 − J2-2 明细期初/期末余额", "logic_check",
             "明细 vs 审定一致性（checkConsistency，容差 0.01）", "useJ2CrossSheet"),
            ("试算平衡表数核对", "审定合计 − 试算平衡表数(2221)", "logic_check",
             "审定合计与 TB 长期应付职工薪酬(2221)核对", "useJ2Integration"),
        ],
        # J2-2 明细表（DBO + 计划资产 + 净负债三区段，CAS9 六要素）
        "J2-2": [
            ("DBO 期末余额", "期初 + (当期服务成本 + 利息费用 + 精算损失 + 其他增加) − (已支付福利 + 精算利得 + 其他减少)",
             "计算", "设定受益义务现值期末（calcLiabilityEndBalance / calcEndDBO 六要素分解）",
             "useJ2Detail / useJ2ActuarialEngine"),
            ("净负债", "DBO 期末现值 − 计划资产公允价值", "计算",
             "设定受益计划净负债（calcNetLiability；正=净负债/负=净资产）", "useJ2ActuarialEngine"),
            ("利息费用", "期初 DBO × 折现率", "计算",
             "DBO 利息成本（calcInterestCost）", "useJ2ActuarialEngine"),
            ("期初/期末/净负债合计", "Σ 各区段", "计算",
             "明细合计（totalBeginBalance/totalEndBalance/totalNetLiability）", "useJ2Detail"),
        ],
        # J2-3 调整分录汇总表
        "J2-3": [
            ("借贷平衡校验", "Σ 借方调整金额 = Σ 贷方调整金额", "logic_check",
             "调整分录借贷平衡", "J2-3 调整分录汇总表"),
            ("AJE/RJE 回写审定表", "账项调整(AJE)/重分类调整(RJE) 回写 J2-1 审定表对应区块", "取数",
             "监听 adjustment:created 回写 J2-1", "J2TabAdjustment"),
        ],
        # J2-4 计提检查（精算假设 + ISA620 专家利用 + 敏感性）
        "J2-4": [
            ("精算损益", "实际 DBO（新假设）− 预期 DBO（旧假设）", "计算",
             "精算假设变动损益，计入 OCI（calcActuarialGainLoss；正=损失/负=利得）", "useJ2ActuarialEngine"),
            ("假设对比变动率", "(本期假设 − 上期假设) ÷ 上期假设 × 100%", "计算",
             "折现率/薪酬增长率/死亡率/离职率 逐项对比（comparisons.deviation）", "useJ2AccrualCheck"),
            ("敏感性分析", "ΔDBO ≈ ∓ DBO × 平均久期 × 50bp（折现率±50bp）", "计算",
             "折现率敏感性（calcSensitivity，Modified Duration 近似）", "useJ2ActuarialEngine"),
            ("精算假设范围校验", "折现率∈[2%,8%] ∧ 薪酬增长率∈[3%,15%] ∧ 死亡率≤5% ∧ 离职率≤30%", "logic_check",
             "ISA620 假设合理性范围（validateAssumptions，超限告警）", "useJ2ActuarialEngine"),
            ("ISA620 专家利用完成度", "已完成评估项 ÷ 8 项（资质/独立性/工作范围/方法论/总体结论）", "计算",
             "精算师工作利用评价完成度（isa620Completeness）", "useJ2AccrualCheck"),
            ("精算假设变动 → B51 联动", "精算假设变动 → 发布 actuarial:assumption-changed 事件", "取数",
             "假设变动联动 B51 会计估计（publishAssumptionChanged）", "useJ2CrossSheet / useJ2Integration"),
        ],
        # 附注披露（上市/国企）
        "附注上市": [
            ("DBO 变动六要素", "期初 + 当期服务成本 + 利息费用 + 精算损失 − 已支付福利 = 期末", "计算",
             "设定受益义务现值变动表（取自 J2-2 明细）", "useJ2Disclosure"),
            ("附注金额取审定/明细数", "取自 J2-1 审定表与 J2-2 明细表", "取数",
             "附注自动取数（fetchAdjudicationData）", "useJ2CrossSheet / useJ2Disclosure"),
            ("敏感性披露", "折现率±50bp 对 DBO 的影响", "取数",
             "取自 J2-4 敏感性分析（calcSensitivity）", "useJ2Disclosure"),
        ],
        "附注国企": [
            ("长期应付职工薪酬变动", "期初余额 + 本期增加 − 本期减少 = 期末余额", "计算",
             "国企版四列变动（负债贷方 E=B+C-D）", "useJ2Disclosure / useJ2FormulaEngine"),
            ("附注金额取审定/明细数", "取自 J2-1 审定表与 J2-2 明细表", "取数",
             "附注自动取数（fetchAdjudicationData）", "useJ2CrossSheet / useJ2Disclosure"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # J3 股份支付（无单一 TB 回写；跨科目 3002/2211/6602，费用走 EventBus 分流）
    # ═══════════════════════════════════════════════════════════════════════
    "J3": {
        # J3-1 股份支付情况表（费用分摊 CAS11）
        "J3-1": [
            ("总公允价值", "单位公允价值 × 权益工具数量", "计算",
             "授予日总公允价值（calcTotalFairValue）", "useJ3Detail / useJ3FormulaEngine"),
            ("累计确认费用", "总公允价值 × MIN(已服务年数 ÷ 等待期, 1)", "计算",
             "CAS11 等待期累计费用（calcCumulativeExpense）", "useJ3FormulaEngine"),
            ("本期确认费用", "累计应确认 − 以前年度累计已确认", "计算",
             "本期费用（calcVestingExpense，估计变更可正确调整）", "useJ3FormulaEngine"),
            ("剩余待确认费用", "总公允价值 − 已确认累计费用", "计算",
             "剩余待确认（calcRemainingExpense）", "useJ3FormulaEngine"),
            ("合计", "Σ 各方案（股数/本期/累计/剩余/总公允价值）", "计算",
             "情况表合计（subtotals = calcSubtotal）", "useJ3Detail"),
            ("权益/现金结算分类", "按结算方式分组统计本期费用", "计算",
             "权益结算(贷记资本公积)/现金结算(贷记应付职工薪酬)分类（equitySummary/cashSummary）",
             "useJ3Detail"),
        ],
        # J3-2 股份支付检查表（Black-Scholes 期权定价 + CAS11 合规）
        "J3-2": [
            ("BS 看涨期权价格", "C = S·N(d₁) − K·e^(−rT)·N(d₂)", "计算",
             "Black-Scholes 期权定价（calcBlackScholes）", "useJ3OptionPricingEngine"),
            ("d₁", "[ln(S/K) + (r + σ²/2)·T] ÷ (σ·√T)", "计算",
             "BS 参数 d1（calcD1）", "useJ3OptionPricingEngine"),
            ("d₂", "d₁ − σ·√T", "计算",
             "BS 参数 d2（calcD2）", "useJ3OptionPricingEngine"),
            ("BS 参数合理性校验", "S>0 ∧ K>0 ∧ T>0 ∧ σ∈[10%,100%] ∧ r∈[1%,10%]", "logic_check",
             "期权定价参数范围（validateBSParams，超限审计关注）", "useJ3OptionPricingEngine / useJ3Check"),
            ("整体检查结论", "任一检查项「不符合」→ 存在不符合事项；全部已选 → 全部符合", "logic_check",
             "CAS11 合规整体结论（overallConclusion）", "useJ3Check"),
        ],
        # J3-1 / J3-2 跨科目联动（无单一 TB 回写）
        "跨科目联动": [
            ("权益结算 → M4 资本公积", "Σ 权益结算方案本期费用 → 贷记资本公积(3002)", "取数",
             "权益结算联动 M4（m4LinkageStatus / publishEquitySettled）",
             "useJ3CrossSheet / useJ3Integration"),
            ("现金结算 → J1 应付职工薪酬", "Σ 现金结算方案本期费用 → 贷记应付职工薪酬(2211)", "取数",
             "现金结算联动 J1（j1LinkageStatus / publishCashSettled）",
             "useJ3CrossSheet / useJ3Integration"),
            ("费用 → K8/K9 管理费用", "Σ 全部方案本期费用 → 借记管理费用(6602)", "取数",
             "费用借方联动 K8/K9（expenseLinkageStatus）", "useJ3CrossSheet"),
            ("股份支付费用确认事件", "发布 share-payment:expense-recognized（权益/现金/合计金额）", "取数",
             "费用确认 EventBus 分流（publishCrossAccountEvent / publishSharePaymentExpense）",
             "useJ3CrossSheet / useJ3Integration"),
        ],
    },
}
