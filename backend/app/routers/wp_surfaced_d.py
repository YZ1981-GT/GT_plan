"""D 循环底稿公式 surfacing 目录（与各 useD{n}* composable 同源，不臆造）。

对齐 E1 标准（wp_formula._E1_SHEET_FORMULAS）：把「专属组件底稿」（数据存
checklist_responses、无 wp_formula 网格记录）的取数/计算/逻辑审核公式以只读条目
surface 到公式管理中心，让每张 sheet 都能体现其取数逻辑。

每条公式均可在对应前端 composable 中找到依据（calc 函数 / 跨 sheet 键 / TB 核对 /
合计聚合）；找不到依据的 sheet 不写（宁缺勿造）。

分类只用三种：
  - 取数     跨 sheet / 四表库 / 从明细带入
  - 计算     表间计算（审定=未审+AJE+RJE、变动额、变动率、合计、净值、期末余额等）
  - logic_check  逻辑审核（TB 核对、审定↔明细勾稽、ECL↔坏账差异、借贷平衡、跨期判定等）

科目方向：D1 应收票据(1121)/D2 应收账款(1122)/D5 应收款项融资(1124)/D6 合同资产(1141)
为资产借方；D3 预收账款(2203)/D7 合同负债(2205)为负债贷方；D4 营业收入(6001+6051)为
损益类取发生额。
"""
from __future__ import annotations

SheetFormula = tuple[str, str, str, str, str]  # (项目名, 公式, 分类, 说明, 来源)

CATALOG: dict[str, dict[str, list[SheetFormula]]] = {
    # ═══════════════════════════════════════════════════════════════════════
    # D1 应收票据（资产借方 1121；含 ECL 坏账 / 业务模式 / 背书贴现）
    # ═══════════════════════════════════════════════════════════════════════
    "D1": {
        # D1-1 审定表（三区块：原值/坏账/净值）
        "D1-1": [
            ("审定数", "未审数 + 账项调整(AJE) + 重分类调整(RJE)", "计算",
             "各行审定金额（calcAuditedAmount）", "useD1Adjudication"),
            ("应收票据净值", "应收票据原值 − 坏账准备", "计算",
             "第三区块逐行净值=原值行−坏账行（calcNetValue）", "useD1Adjudication"),
            ("区块小计", "Σ 区块内明细行", "计算",
             "原值/坏账/净值各区块小计（calcSubtotal）", "useD1Adjudication"),
            ("变动额", "期末审定数 − 期初审定数", "计算",
             "本期净值较期初变动额", "useD1Adjudication"),
            ("变动率", "变动额 ÷ 期初审定数", "计算",
             "期初=0 特殊处理（calcChangeRate）；|变动率|>30% 红色高亮（isChangeRateExceeding）",
             "useD1FormulaEngine"),
            ("从 D1-2 按类别带入", "按承兑类型（银行/商业）从 D1-2 明细带入原值各列", "取数",
             "原值区块行数据取自 D1-cat-rows（categoryRows 匹配银行承兑/商业承兑）", "useD1Adjudication"),
            ("试算平衡表数核对", "净值审定合计 − 试算平衡表数(1121)", "logic_check",
             "审定净值与 TB 应收票据(1121)核对，差异须查明（D1-adj-tb-amount 优先，回退 render 预填）",
             "useD1Adjudication"),
        ],
        # D1-2 按类别明细
        "D1-2": [
            ("期末未审数", "期初审定 + 本期增加 − 本期减少", "计算",
             "按承兑类别原值明细期末未审（calcCurrentUnadjusted）", "useD1FormulaEngine"),
            ("审定数", "未审数 + AJE + RJE", "计算",
             "各类别审定金额（calcAuditedAmount）", "useD1FormulaEngine"),
            ("比例", "IFERROR(本行余额 ÷ 合计行余额, 0)", "计算",
             "各类别占比（safeDivide 语义）", "useD1FormulaEngine"),
        ],
        # D1-3 按客户明细
        "D1-3": [
            ("期末未审数", "期初审定 + 本期增加 − 本期减少", "计算",
             "按客户原值明细期末未审（calcCurrentUnadjusted）", "useD1FormulaEngine"),
            ("审定数", "未审数 + AJE + RJE", "计算",
             "各客户审定金额（calcAuditedAmount）", "useD1FormulaEngine"),
        ],
        # D1-4 坏账准备
        "D1-4": [
            ("期末未审数", "期初审定 + 本期计提 − 本期收回 − 本期转回 − 本期核销 + 本期其他", "计算",
             "坏账准备明细期末未审（calcBadDebtEndBalance）", "useD1FormulaEngine"),
            ("预期信用损失率", "各阶段迁徙率连乘", "计算",
             "按组合计提损失率（calcExpectedLossRate）", "useD1FormulaEngine"),
            ("应计提", "余额 × 损失率", "计算",
             "单项/组合计提（calcProvision）", "useD1FormulaEngine"),
            ("差异", "实际账面余额 − 应计提", "计算",
             "正值多提/负值少提（calcDifference）", "useD1FormulaEngine"),
        ],
        # D1-5 调整分录
        "D1-5": [
            ("借贷平衡校验", "Σ 借方金额 = Σ 贷方金额", "logic_check",
             "调整分录借贷平衡", "D1-5 调整分录"),
            ("AJE/RJE 回写审定表", "按科目将 AJE/RJE 累加到 D1-1 审定表对应行", "取数",
             "监听 adjustment:created 按科目映射行（resolveRowKeyFromAccount）", "useD1Adjudication"),
        ],
        # D1-6 业务模式（QA矩阵 IF 判定）
        "D1-6": [
            ("业务模式判定", "IF(Q1=是∧Q2=否→收取合同现金流量为目标; Q1=是∧Q2=是∧Q4=是→收取+出售; 否则→其他业务模式)",
             "logic_check", "四问答矩阵推导业务模式（determineBusinessMode）", "useD1FormulaEngine"),
            ("列报项目判定", "收取+出售→应收款项融资; 收取为目标→应收票据; 其他业务模式→以公允价值计量金融资产",
             "logic_check", "业务模式→列报科目映射（determineReportItem）", "useD1FormulaEngine"),
        ],
        # D1-7 备查簿
        "D1-7": [
            ("年末余额", "年初 + 本期收到 − 本期背书 − 本期到期承兑 − 本期贴现", "计算",
             "备查簿年末余额（calcMemoEndingBalance）", "useD1FormulaEngine"),
            ("高信用银行判定", "承兑人名称 ∈ 6大行+9家上市股份制银行关键词", "logic_check",
             "承兑人信用识别（isHighCreditBank）", "useD1FormulaEngine"),
            ("终止确认建议", "已贴现/已背书 ∧ 银行承兑 ∧ 高信用银行 → 是；商业承兑 → 否", "logic_check",
             "终止确认倾向建议（suggestDerecognized）", "useD1FormulaEngine"),
            ("信用评级建议", "高信用银行承兑→AA；商业承兑→其他", "logic_check",
             "信用评级默认档（suggestCreditRating）", "useD1FormulaEngine"),
        ],
        # D1-8 背书贴现明细
        "D1-8": [
            ("已贴现未终止确认合计", "Σ（已贴现尚未到期且未终止确认）汇票金额", "计算",
             "仍列示应收票据/表外披露（discountNotDerecognizedTotal），与 D5 应收款项融资勾稽",
             "useD1CrossSheet"),
            ("已背书转让合计", "Σ（已背书转让尚未到期）汇票金额", "计算",
             "表外披露口径（endorsedTransferTotal）", "useD1CrossSheet"),
            ("期末未到期背书贴现金额", "已贴现/已背书 ∧ 到期日>基准日 → 取票面金额", "计算",
             "审计基准日尚未到期部分（calcUnexpiredEndorsedDiscounted）", "useD1FormulaEngine"),
        ],
        # D1-9 贴息检查
        "D1-9": [
            ("贴息天数", "到期日 − 贴现日", "计算",
             "自然天数差，贴现日晚于到期日按 0（calcDiscountDays）", "useD1FormulaEngine"),
            ("应计贴现利息", "票面金额 × 贴现率 × 贴息天数 ÷ 360", "计算",
             "P×R×D/360（calcDiscountInterest）", "useD1FormulaEngine"),
            ("贴息差异", "应计贴现利息 − 账面贴现利息", "logic_check",
             "与账面核对，差异≠0 高亮（calcInterestDifference）", "useD1FormulaEngine"),
        ],
        # D1-15 ECL 模型测算
        "D1-15": [
            ("ECL 应计提减值合计", "各阶段 Σ 应计提减值", "计算",
             "ECL 模型应计提（D1-ecl-total-should-provision）", "useD1CrossSheet"),
            ("ECL 应计提 ↔ D1-4 坏账准备勾稽", "ECL 模型应计提 − D1-4 坏账准备明细审定合计", "logic_check",
             "二者理论应一致，差异>阈值提示复核（eclVsBadDebtDiff）", "useD1CrossSheet"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # D2 应收账款（资产借方 1122；含 ECL 单项/组合迁徙率 / 质押保理 / 截止）
    # ═══════════════════════════════════════════════════════════════════════
    "D2": {
        # D2-1 审定表（单项计提/账龄组合/客户类型组合）
        "D2-1": [
            ("审定数", "未审数 + 账项调整(AJE) + 重分类调整(RJE)", "计算",
             "各分类行审定金额（getAuditedAmount）", "useD2Adjudication"),
            ("合计", "Σ（单项计提 + 账龄组合 + 客户类型组合）", "计算",
             "三分类合计（buildTotalRow）", "useD2Adjudication"),
            ("变动率", "(期末审定 − 期初审定) ÷ 期初审定", "计算",
             "期初=0 特殊处理（getChangeRate）；|变动率|>30% 高亮（isChangeRateWarning）",
             "useD2Adjudication"),
            ("按信用风险组合从 D2-2 聚合", "SUMIF(D2-2 明细, 信用风险组合方式=分类, 期末未审/AJE/RJE)", "取数",
             "按单项计提/账龄组合/客户类型组合聚合明细各值列（sumif / sumifAggregation）",
             "useD2Adjudication / useD2CrossSheet"),
            ("试算平衡表数核对", "审定合计 − 试算平衡表数(1122)", "logic_check",
             "审定合计与 TB 应收账款(1122)核对（trialBalanceDiff，容差 0.005）", "useD2Adjudication"),
            ("D2-1 原值合计 ↔ D2-2 明细合计", "D2-1 三分类审定合计 − D2-2 明细审定合计", "logic_check",
             "审定表↔明细表勾稽（detailCrossValidation，容差 0.01）", "useD2Adjudication"),
            ("D2-3 坏账准备 ↔ D2-9 ECL 应计提", "D2-3 坏账准备合计 − D2-9 应计提合计", "logic_check",
             "坏账准备与 ECL 测算勾稽（eclCrossValidation）", "useD2Adjudication"),
        ],
        # D2-2 明细表（动态账龄）
        "D2-2": [
            ("期初审定", "期初未审 + 期初 AJE + 期初 RJE", "计算",
             "明细行期初审定（getAuditedAmount / recalcRow）", "useD2Detail"),
            ("期末余额", "期初审定 + 借方发生 − 贷方发生", "计算",
             "借方科目期末余额（recalcRow）", "useD2Detail"),
            ("期末未审", "期末余额 + 被审计单位重分类", "计算",
             "明细行期末未审（recalcRow）", "useD2Detail"),
            ("期末审定", "期末未审 + 账项调整(Z) + 重分类调整(AA)", "计算",
             "明细行期末审定（getAuditedAmount / recalcRow）", "useD2Detail"),
            ("关联方自动匹配", "客户名称 ⊇ 关联方清单关键词 → 其他关联方，否则非关联方", "logic_check",
             "编辑客户名称触发关联方匹配（matchRelatedParty）", "useD2Detail"),
            ("从辅助余额表导入", "取 1122 客户维度辅助余额（期初/借方/贷方/期末），按客户名去重合并", "取数",
             "importFromAuxBalance（不覆盖 AJE/RJE/账龄）", "useD2Detail"),
            ("期后回款取数", "取基准日后 1122 贷方发生额，按客户名归集填入期后回款列", "取数",
             "序时账 1122 贷方=收款（importPostPaymentFromLedger）", "useD2Detail"),
        ],
        # D2-3 坏账准备（三分类）
        "D2-3": [
            ("期初审定", "期初未审 + 期初 AJE + 期初 RJE", "计算",
             "坏账准备行期初审定（recalcRow）", "useD2BadDebt"),
            ("期末未审数", "期初审定 + 计提 + 其他增加 − 转回 − 核销 − 其他减少", "计算",
             "坏账准备变动（recalcRow）", "useD2BadDebt"),
            ("期末审定", "期末未审 + 期末 AJE + 期末 RJE", "计算",
             "坏账准备行期末审定（getAuditedAmount）", "useD2BadDebt"),
            ("分类小计", "Σ 该分类子行", "计算",
             "单项/账龄组合/客户类型组合固定小计行（recalcFixedRow）", "useD2BadDebt"),
            ("ECL 差异", "坏账准备合计审定数 − D2-9 ECL 测算总额", "logic_check",
             "差异≠0 黄色警告（eclDifference / eclWarning）", "useD2BadDebt"),
        ],
        # D2-5 分析程序
        "D2-5": [
            ("应收账款周转率", "营业收入 ÷ 平均应收账款", "计算",
             "周转率（calculateTurnoverRate）", "useD2Analysis"),
            ("应收账款周转天数", "365 ÷ 周转率", "计算",
             "周转天数（calculateTurnoverDays）", "useD2Analysis"),
            ("坏账准备计提比率", "坏账准备余额 ÷ 应收账款合计", "计算",
             "坏账率（取 D2-3 坏账合计 / D2-1 审定合计）", "useD2Analysis"),
            ("前五大客户集中度", "前五大客户审定金额合计 ÷ 客户审定总额", "计算",
             "从 D2-2 明细 Top5 聚合（buildTop5FromDetail）", "useD2Analysis"),
            ("周转天数变动警告", "|(本期周转天数 − 上期) ÷ 上期| > 30%", "logic_check",
             "变动超阈值须关注（turnoverDaysWarning）", "useD2Analysis"),
        ],
        # D2-7 凭证抽查
        "D2-7": [
            ("跨期判定", "收入确认日期 > 资产负债表日 → 跨期", "logic_check",
             "凭证抽查跨期自动标记（determineCutoff / autoMarkCutoff）", "useD2VoucherCheck"),
            ("异常率", "异常笔数 ÷ 样本笔数", "计算",
             "抽查异常率（abnormalRate）", "useD2VoucherCheck"),
            ("抽样进度", "已抽样本数 ÷ 目标样本量", "计算",
             "抽样覆盖进度（progress）", "useD2VoucherCheck"),
        ],
        # D2-9 单项 ECL
        "D2-9": [
            ("应计提", "审定余额 × 预期信用损失率", "计算",
             "单项 ECL 应计提（calculateProvision）", "useD2Ecl"),
            ("差异", "实际账面余额 − 应计提", "计算",
             "单项 ECL 差异（calculateDifference）", "useD2Ecl"),
            ("从 D2-3 取实际账面余额", "取 D2-3 坏账准备各分类固定行审定数合计", "取数",
             "actualBalance 自动填入（d3BadDebtTotal）", "useD2Ecl"),
            ("从 D2-2 筛单项计提导入", "筛选 D2-2 明细信用风险组合方式=单项计提的客户", "取数",
             "导入债务人名称与审定余额（importFromDetail）", "useD2Ecl"),
        ],
        # D2-10 组合迁徙率
        "D2-10": [
            ("平均迁徙率", "AVG(第1年, 第2年, 第3年 迁徙率)", "计算",
             "各账龄段三年平均迁徙率（recalcAllMigration）", "useD2Ecl"),
            ("预期信用损失率", "本段平均迁徙率 × 后续各段平均迁徙率连乘", "计算",
             "迁徙率矩阵连乘（calculateExpectedLossRate）", "useD2FormulaEngine"),
            ("折现法预期损失率", "1 − Σ(情景现值 × 概率) ÷ 余额", "计算",
             "概率加权折现法（recalcDiscountRow）", "useD2Ecl"),
            ("迁徙率变动警告", "|(本年迁徙率 − 上年) ÷ 上年| > 50%", "logic_check",
             "迁徙率大幅变动提示（migrationChangeWarning）", "useD2Ecl"),
        ],
        # D2-12 质押保理
        "D2-12": [
            ("质押比例", "质押总额 ÷ 应收账款审定总额", "计算",
             "质押占比（calculatePledgeRatio），跨 sheet 取 D2-1 审定合计", "useD2PledgeCheck"),
            ("质押比例警告", "质押比例 > 50%", "logic_check",
             "关注应收账款可用性（pledgeRatioWarning）", "useD2PledgeCheck"),
            ("CAS23 终止确认判定", "风险已转移→终止；风险未转移∧未保留控制→终止；否则→不终止", "logic_check",
             "保理终止确认自动判定（determineDerecognition）", "useD2PledgeCheck"),
        ],
        # 附注披露（上市/国企）
        "附注上市": [
            ("附注披露金额", "取自 D2-1 审定表各分类（单项/账龄/客户类型）审定数", "取数",
             "附注按分类取审定数（adjudicationForDisclosure）", "useD2CrossSheet"),
            ("账龄段分布", "按审定账龄段从 D2-2 明细聚合", "取数",
             "附注账龄披露取自明细（agingFromDetail）", "useD2CrossSheet"),
        ],
        "附注国企": [
            ("附注披露金额", "取自 D2-1 审定表各分类审定数", "取数",
             "附注按分类取审定数（adjudicationForDisclosure）", "useD2CrossSheet"),
            ("账龄段分布", "按审定账龄段从 D2-2 明细聚合", "取数",
             "附注账龄披露取自明细（agingFromDetail）", "useD2CrossSheet"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # D3 预收账款（负债贷方 2203；含款项性质 / 动态账龄 / CAS14 收入准则）
    # ═══════════════════════════════════════════════════════════════════════
    "D3": {
        # D3-1 审定表（按性质 + 按账龄）
        "D3-1": [
            ("审定数", "未审 + 账项调整(AJE) + 重分类调整(RJE)", "计算",
             "各行审定金额（calcAuditedAmount）", "useD3FormulaEngine"),
            ("合计", "Σ 各行", "计算",
             "审定表合计（calcSubtotal）", "useD3FormulaEngine"),
            ("变动额", "期末审定 − 期初审定", "计算",
             "本期变动额（calcChangeAmount）", "useD3FormulaEngine"),
            ("变动率", "(期末审定 − 期初审定) ÷ 期初审定", "计算",
             "期初=0 特殊处理（calcChangeRate）；|变动率|>30% 高亮（isChangeRateExceeding）",
             "useD3FormulaEngine"),
            ("按款项性质从 D3-2 聚合", "按 nature 分组 SUM(D3-2 明细 期末审定/期初审定)", "取数",
             "按性质分类区块取数（aggregateByNature / natureAggregation）", "useD3CrossSheet"),
            ("按审定账龄从 D3-2 聚合", "按项目账龄段 SUM(D3-2 明细审定账龄)", "取数",
             "按账龄分类区块取数（aggregateAgingByKeys，segment-driven）", "useD3CrossSheet"),
            ("CAS14 合同负债提示", "其他类款项性质金额>0 → 提示区分合同负债", "logic_check",
             "款项性质分类勾稽提示", "useD3Adjudication"),
        ],
        # D3-2 明细表
        "D3-2": [
            ("期初审定余额(H)", "期初未审(E) + 期初账项调整(F) + 期初重分类调整(G)", "计算",
             "D3-2 明细 H 列（calcPriorAudited）", "useD3FormulaEngine"),
            ("期末余额(O)", "期初审定(H) + 贷方发生(N) − 借方发生(M)", "计算",
             "贷方科目期末余额（calcEndBalance）", "useD3FormulaEngine"),
            ("期末未审余额(Q)", "期末余额(O) + 被审计单位重分类(P)", "计算",
             "D3-2 明细 Q 列（calcEndUnadjusted）", "useD3FormulaEngine"),
            ("期末审定数(T)", "期末未审(Q) + 期末账项调整(R) + 期末重分类调整(S)", "计算",
             "D3-2 明细 T 列（calcEndAudited）", "useD3FormulaEngine"),
        ],
        # D3-3 调整分录
        "D3-3": [
            ("借贷平衡校验", "Σ 借方调整金额 = Σ 贷方调整金额", "logic_check",
             "调整分录借贷平衡", "D3-3 调整分录"),
            ("AJE/RJE 汇总回写审定表", "账项调整→AJE / 重分类调整→RJE 借方金额汇总", "取数",
             "回写 D3-1 审定表（adjustmentTotals）", "useD3CrossSheet"),
        ],
        # D3-5 长期账龄检查
        "D3-5": [
            ("从 D3-2 导入长期行", "筛选 D3-2 审定账龄>1年段(dayFrom≥366)合计>0 的行", "取数",
             "长期检查导入（longTermRows，segment-driven）", "useD3CrossSheet"),
        ],
        # D3-6 关联方检查
        "D3-6": [
            ("从 D3-2 导入关联方行", "筛选 D3-2 relationType≠非关联方 的行", "取数",
             "关联方检查导入（relatedPartyRows）", "useD3CrossSheet"),
            ("关联方期末余额", "期初 + 贷方发生 − 借方发生", "计算",
             "贷方科目关联方期末余额（calcRelatedPartyEndBalance）", "useD3FormulaEngine"),
        ],
        # D3-7 检查表 / 期后结转
        "D3-7": [
            ("异常率", "异常笔数 ÷ 已检查笔数 × 100%", "计算",
             "凭证检查异常率（calcAnomalyRate）", "useD3FormulaEngine"),
            ("期后结转按客户聚合", "按客户 SUM(D3-7 期后结转贷方金额)", "取数",
             "供 D3-2 期后结转交叉验证（postPeriodSettlementSync）", "useD3CrossSheet"),
        ],
        # 附注披露
        "附注上市": [
            ("附注披露金额", "取自 D3-1 审定表（按性质聚合 + 按账龄聚合 + 长期行）", "取数",
             "附注取审定数（adjudicationForDisclosure）", "useD3CrossSheet"),
        ],
        "附注国企": [
            ("附注披露金额", "取自 D3-1 审定表（按性质聚合 + 按账龄聚合 + 长期行）", "取数",
             "附注取审定数（adjudicationForDisclosure）", "useD3CrossSheet"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # D4 营业收入（损益类取发生额 6001 主营 + 6051 其他；无余额概念）
    # ═══════════════════════════════════════════════════════════════════════
    "D4": {
        # D4-1 审定表（主营 + 其他 双区块）
        "D4-1": [
            ("审定数", "未审 + 账项调整(AJE) + 重分类调整(RJE)", "计算",
             "损益类各行审定金额（calcAuditedAmount）", "useD4FormulaEngine"),
            ("营业收入合计", "主营业务收入小计 + 其他业务收入小计", "计算",
             "grandTotalRow（calcSubtotal）", "useD4Adjudication"),
            ("主营按产品从 D4-2 聚合", "按产品 SUM(月度合计 + 审计调整)", "取数",
             "主营区块取数（mainRevenueByProduct）", "useD4Adjudication / useD4CrossSheet"),
            ("其他按项目从 D4-3 聚合", "按项目 SUM(未审 + 审计调整)", "取数",
             "其他区块取数（otherRevenueByItem）", "useD4Adjudication / useD4CrossSheet"),
            ("试算平衡表数核对", "营业收入审定合计 − 试算平衡表数(6001 + 6051)", "logic_check",
             "审定合计与 TB 核对（differenceRow）", "useD4Adjudication"),
            ("主营小计 ↔ D4-2 合计", "D4-1 主营小计 − D4-2 明细合计", "logic_check",
             "审定表↔明细表勾稽（mainCrossValidation，容差 0.005）", "useD4Adjudication"),
            ("其他小计 ↔ D4-3 合计", "D4-1 其他小计 − D4-3 合计", "logic_check",
             "审定表↔明细表勾稽（otherCrossValidation）", "useD4Adjudication"),
        ],
        # D4-2 主营明细（22 列宽表，1-12 月）
        "D4-2": [
            ("本期未审合计", "Σ(1月 ~ 12月)", "计算",
             "月度合计（calcMonthlyTotal）", "useD4FormulaEngine"),
            ("本期审定", "本期未审合计 + 本期审计调整", "计算",
             "含调整审定（calcAuditedWithAdj）", "useD4FormulaEngine"),
            ("变动率", "(本期 − 上期) ÷ 上期", "计算",
             "本期=0∧上期=0→空；上期=0→N/A（calcChangeRate）", "useD4FormulaEngine"),
            ("从序时账取数", "按产品(account_name)×月聚合 6001 贷方净额(贷−借)", "取数",
             "序时账月度取数（d4_ledger_monthly_by_product）", "useD4CrossSheet"),
        ],
        # D4-3 其他业务收入
        "D4-3": [
            ("本期审定", "本期未审 + 本期审计调整", "计算",
             "其他收入审定（calcAuditedWithAdj）", "useD4FormulaEngine"),
            ("占比", "本项 ÷ 合计 × 100%", "计算",
             "各项目占比（calcProportion）", "useD4FormulaEngine"),
        ],
        # D4-4 调整分录
        "D4-4": [
            ("借贷平衡校验", "Σ 借方金额 = Σ 贷方金额", "logic_check",
             "调整分录借贷平衡", "D4-4 调整分录"),
            ("AJE/RJE 分拆回写审定表", "6001→主营 / 6051→其他；金额 = 借方 − 贷方(损益贷方借增贷减)", "取数",
             "按科目分拆 AJE/RJE 回写 D4-1（adjustmentTotals）", "useD4CrossSheet"),
        ],
        # D4-7 月度毛利
        "D4-7": [
            ("毛利率", "(收入 − 成本) ÷ 收入", "计算",
             "月度毛利率（calcGrossMarginRate）", "useD4FormulaEngine"),
        ],
        # D4-8 产品毛利
        "D4-8": [
            ("毛利率", "(收入 − 成本) ÷ 收入", "计算",
             "产品毛利率（calcGrossMarginRate），产品收入取自 D4-2", "useD4FormulaEngine"),
        ],
        # D4-9 客户结构
        "D4-9": [
            ("客户占比", "本客户审定金额 ÷ 客户审定总额 × 100%", "计算",
             "按审定金额降序 Top 排名占比（calcProportion / customerStructureData）",
             "useD4CrossSheet"),
        ],
        # D4-12 合同检查
        "D4-12": [
            ("覆盖率", "已检查金额 ÷ 收入合计 × 100%", "计算",
             "合同检查覆盖率（calcCoverageRate）", "useD4FormulaEngine"),
        ],
        # D4-14 收入发生检查
        "D4-14": [
            ("异常率", "异常笔数 ÷ 已检查笔数 × 100%", "计算",
             "发生检查异常率（calcAnomalyRate）", "useD4FormulaEngine"),
        ],
        # D4-15 收入发生检查
        "D4-15": [
            ("异常率", "异常笔数 ÷ 已检查笔数 × 100%", "计算",
             "发生检查异常率（calcAnomalyRate）", "useD4FormulaEngine"),
        ],
        # D4-17 截止测试
        "D4-17": [
            ("跨期判定", "凭证日期与参考日期分居资产负债表日两侧 → 跨期", "logic_check",
             "收入截止测试跨期判定（isCrossPeriod）", "useD4FormulaEngine"),
            ("跨期天数", "|凭证日期 − 参考日期|", "计算",
             "截止测试跨期天数（calcCrossPeriodDays）", "useD4FormulaEngine"),
        ],
        # D4-18 截止测试
        "D4-18": [
            ("跨期判定", "凭证日期与参考日期分居资产负债表日两侧 → 跨期", "logic_check",
             "收入截止测试跨期判定（isCrossPeriod）", "useD4FormulaEngine"),
            ("跨期天数", "|凭证日期 − 参考日期|", "计算",
             "截止测试跨期天数（calcCrossPeriodDays）", "useD4FormulaEngine"),
        ],
        # D4-21 关联方价格分析
        "D4-21": [
            ("价格差异率", "(关联方单价 − 非关联方单价) ÷ 非关联方单价 × 100%", "计算",
             "关联方交易价格公允性（calcPriceDiffRate）", "useD4FormulaEngine"),
        ],
        # D4-32 资金流水检查
        "D4-32": [
            ("资金回流可疑判定", "同一对手入/出金额差异<10% ∧ 间隔<30天 → 可疑", "logic_check",
             "资金回流识别（isSuspiciousFundFlow）", "useD4FormulaEngine"),
        ],
        # D4-33 其他业务毛利
        "D4-33": [
            ("毛利率", "(收入 − 成本) ÷ 收入", "计算",
             "其他业务毛利率（calcGrossMarginRate）", "useD4FormulaEngine"),
        ],
        # 附注披露
        "附注上市": [
            ("附注营业收入披露", "取自 D4-1 审定表（主营审定 + 其他审定 = 合计）", "取数",
             "附注取审定数（adjudicationForDisclosure）", "useD4CrossSheet"),
            ("附注营业成本取数", "从 TB 科目 6401/6402 取本期/上期成本", "取数",
             "成本跨循环取数（costFromTb）", "useD4CrossSheet"),
        ],
        "附注国企": [
            ("附注营业收入披露", "取自 D4-1 审定表（主营审定 + 其他审定 = 合计）", "取数",
             "附注取审定数（adjudicationForDisclosure）", "useD4CrossSheet"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # D5 应收款项融资（FVOCI 资产借方 1124；公允价值贴现测算）
    # ═══════════════════════════════════════════════════════════════════════
    "D5": {
        # D5-1 审定表
        "D5-1": [
            ("审定数", "未审 + 账项调整(AJE) + 重分类调整(RJE)", "计算",
             "各行审定金额（calcAuditedAmount）", "useD5FormulaEngine"),
            ("按类别从 D5-2 聚合", "按类别(应收票据/应收账款) SUM(D5-2 期末审定/期初审定)", "取数",
             "审定表分类取数（categoryAggregation）", "useD5CrossSheet"),
            ("OCI 公允价值变动", "小计(票面) − D5-4 公允价值合计", "取数",
             "从 D5-4 公允价值测算取数（ociChange）", "useD5CrossSheet"),
            ("公允价值合计", "小计 − 减:OCI 公允价值变动", "计算",
             "D5 特殊审定表结构（calcFvTotal）", "useD5FormulaEngine"),
            ("变动额", "期末审定 − 期初审定", "计算",
             "本期变动额（calcChangeAmount）", "useD5FormulaEngine"),
            ("变动率", "(期末审定 − 期初审定) ÷ 期初审定", "计算",
             "期初=0 特殊处理（calcChangeRate）；|变动率|>30% 高亮（isChangeRateExceeding）",
             "useD5FormulaEngine"),
        ],
        # D5-2 明细表
        "D5-2": [
            ("期初审定", "期初未审 + 期初 AJE + 期初 RJE", "计算",
             "明细期初审定（calcAuditedAmount）", "useD5FormulaEngine"),
            ("期末余额(J)", "期初审定(F) + 本期增加(H) − 本期减少(I)", "计算",
             "借方科目期末余额（calcEndBalance）", "useD5FormulaEngine"),
            ("期末未审余额(L)", "期末余额(J) + 被审计单位重分类(K)", "计算",
             "D5-2 明细 L 列（calcEndUnadjusted）", "useD5FormulaEngine"),
            ("期末审定余额(O)", "期末未审(L) + 账项调整(M) + 重分类调整(N)", "计算",
             "D5-2 明细 O 列（calcEndAudited）", "useD5FormulaEngine"),
            ("ECL 阶段建议", "违约或逾期>90天→阶段三；逾期>30天→阶段二；否则阶段一", "logic_check",
             "信用风险显著增加判定（suggestEclStage）", "useD5FormulaEngine"),
        ],
        # D5-3 调整分录
        "D5-3": [
            ("借贷平衡校验", "Σ 借方金额 = Σ 贷方金额", "logic_check",
             "调整分录借贷平衡", "D5-3 调整分录"),
            ("AJE/RJE 汇总回写审定表", "账项调整→AJE / 报表(重分类)调整→RJE；净额 = 借方 − 贷方(借方科目)", "取数",
             "回写 D5-1 审定表（adjustmentTotals）", "useD5CrossSheet"),
        ],
        # D5-4 公允价值测算
        "D5-4": [
            ("剩余天数(G)", "到期日 − 计量日", "计算",
             "距到期天数（calcRemainingDays）", "useD5FormulaEngine"),
            ("贴现利息(I)", "票面金额 × 市场贴现利率 × 剩余天数 ÷ 360", "计算",
             "FVOCI 贴现法（calcDiscountInterest）", "useD5FormulaEngine"),
            ("公允价值(K)", "票面金额 − 贴现利息", "计算",
             "期末公允价值（calcFairValue）", "useD5FormulaEngine"),
            ("公允价值合计", "Σ 各行公允价值", "计算",
             "供 D5-1 OCI 变动计算（fairValueTotal）", "useD5CrossSheet"),
        ],
        # 附注披露
        "附注上市": [
            ("附注披露金额", "取自 D5-1（应收票据/应收账款/小计/OCI变动/公允价值合计）", "取数",
             "附注取审定数（adjudicationForDisclosure）", "useD5CrossSheet"),
            ("减值准备期末", "上年末 + 本期计提 − 收回转回 − 核销", "计算",
             "减值准备变动表（calcImpairmentEnd）", "useD5FormulaEngine"),
        ],
        "附注国企": [
            ("附注披露金额", "取自 D5-1（应收票据/应收账款/小计/OCI变动/公允价值合计）", "取数",
             "附注取审定数（adjudicationForDisclosure）", "useD5CrossSheet"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # D6 合同资产（资产借方 1141；三区块净值 + ECL 双组合测算）
    # 合同资产科目为 1141；report_config 报表行 BS-011 四准则一致。原 `1402` 是在途物资
    # （存货类），属误用。
    # ═══════════════════════════════════════════════════════════════════════
    "D6": {
        # D6-1 审定表（三区块：原值/坏账准备/净值）
        "D6-1": [
            ("期末未审(借方科目)", "期初审定 + 借方发生 − 贷方发生", "计算",
             "借方科目期末未审（calcEndUnadjustedDebit）", "useD6FormulaEngine"),
            ("审定数", "未审 + 账项调整(AJE) + 重分类调整(RJE)", "计算",
             "各审定列（calcAuditedAmount / calcEndAudited）", "useD6FormulaEngine"),
            ("净值", "合同资产原值 − 坏账准备", "计算",
             "三区块逐行净值联动（calcNetValue / netValueRows）", "useD6FormulaEngine / useD6CrossSheet"),
            ("区块合计", "小计 − 减:列示于其他非流动资产的合同资产", "计算",
             "各区块合计行（calcBlockTotal）", "useD6FormulaEngine"),
            ("原值从 D6-2 聚合", "按合同类型 SUM(D6-2 期末审定/期初审定)", "取数",
             "原值区块取数（originalValueAggregation）", "useD6CrossSheet"),
            ("坏账准备从 D6-3 聚合", "按分类 SUM(D6-3 期末审定/期初审定)", "取数",
             "坏账区块取数（impairmentAggregation）", "useD6CrossSheet"),
            ("D6-4 调整分录回写", "AJE = Σ 借方 / RJE = Σ 贷方", "取数",
             "从 D6-4 汇总 AJE/RJE（adjustmentTotals）", "useD6CrossSheet"),
            ("净值交叉验证", "净值合计 − (原值合计 − 坏账合计)", "logic_check",
             "三区块勾稽（netValueValidation，容差 0.01）", "useD6CrossSheet"),
        ],
        # D6-2 明细表
        "D6-2": [
            ("期末未审", "期初审定 + 借方发生 − 贷方发生", "计算",
             "借方科目明细期末未审（calcEndUnadjustedDebit）", "useD6FormulaEngine"),
            ("期末审定", "期末未审 + 账项调整 + 重分类调整", "计算",
             "明细期末审定（calcEndAudited）", "useD6FormulaEngine"),
            ("1年以上收款权合计", "Σ D6-2 各行 1年以上收款权", "取数",
             "供 D6-1 非流动扣减参考（nonCurrentTotal）", "useD6CrossSheet"),
        ],
        # D6-3 减值准备明细
        "D6-3": [
            ("减值准备期末未审", "期初审定 + 计提 + 其他增加 − 转回 − 核销 − 其他减少", "计算",
             "减值准备变动（calcImpairmentEndUnadjusted）", "useD6FormulaEngine"),
            ("期末审定", "期末未审 + 账项调整 + 重分类调整", "计算",
             "减值准备期末审定（calcEndAudited）", "useD6FormulaEngine"),
        ],
        # D6-4 调整分录
        "D6-4": [
            ("借贷平衡校验", "Σ 借方金额 = Σ 贷方金额", "logic_check",
             "调整分录借贷平衡", "D6-4 调整分录"),
        ],
        # D6-5 关联方检查
        "D6-5": [
            ("关联方期末余额", "期初余额 + 借方发生 − 贷方发生", "计算",
             "借方科目关联方期末余额（calcRelatedPartyEndBalance）", "useD6FormulaEngine"),
            ("账面价值", "期末余额 − 坏账准备", "计算",
             "关联方账面价值（calcBookValue）", "useD6FormulaEngine"),
        ],
        # D6-8 减值测算（ECL 双组合）
        "D6-8": [
            ("ECL 应计提", "审定余额 × 预期信用损失率", "计算",
             "减值测算③列（calcExpectedProvision）", "useD6FormulaEngine"),
            ("ECL 差异", "应计提 − 账面余额", "计算",
             "减值测算⑤列，正=计提不足/负=计提过多（calcEclDifference）", "useD6FormulaEngine"),
            ("ECL 应计提合计", "单项合计 + 各组合小计", "计算",
             "ECL 应计提汇总（eclReferenceValues）", "useD6CrossSheet"),
            ("D6-8 应计提 ↔ D6-3 账面减值差异", "D6-8 ECL 应计提合计 − D6-3 账面减值合计", "logic_check",
             "差异>1元视为重大（eclVsImpairmentDiff）", "useD6CrossSheet"),
        ],
        # 附注披露
        "附注上市": [
            ("附注披露金额", "取自 D6-1 三区块（原值/坏账/净值）审定数", "取数",
             "附注取审定数（adjudicationForDisclosure）", "useD6CrossSheet"),
            ("比例%", "该类别金额 ÷ 合计金额 × 100", "计算",
             "附注比例列（calcPercentage）", "useD6FormulaEngine"),
            ("ECL 减值披露", "取自 D6-8 单项/组合应计提", "取数",
             "附注 ECL 取数（eclForDisclosure）", "useD6CrossSheet"),
            ("减值变动披露", "取自 D6-3 计提/转回/核销", "取数",
             "附注减值变动取数（impairmentChangesForDisclosure）", "useD6CrossSheet"),
        ],
        "附注国企": [
            ("附注披露金额", "取自 D6-1 三区块（原值/坏账/净值）审定数", "取数",
             "附注取审定数（adjudicationForDisclosure）", "useD6CrossSheet"),
            ("减值变动披露", "取自 D6-3 计提/转回/核销", "取数",
             "附注减值变动取数（impairmentChangesForDisclosure）", "useD6CrossSheet"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # D7 合同负债（负债贷方 2205；双区块 按性质 + 按账龄 + 截止）
    # ═══════════════════════════════════════════════════════════════════════
    "D7": {
        # D7-1 审定表（按性质 + 按账龄 双区块）
        "D7-1": [
            ("审定数", "未审 + 账项调整(AJE) + 重分类调整(RJE)", "计算",
             "各行审定金额（calcAuditedAmount）", "useD7FormulaEngine"),
            ("小计", "Σ 明细行", "计算",
             "各区块小计（calcSubtotal）", "useD7FormulaEngine"),
            ("合同负债合计", "小计 − 计入其他非流动负债的合同负债", "计算",
             "按性质区块合计（calcContractLiabilityTotal）", "useD7FormulaEngine"),
            ("变动额", "期末审定 − 期初审定", "计算",
             "本期变动额（calcChangeAmount）", "useD7FormulaEngine"),
            ("变动率", "(期末审定 − 期初审定) ÷ 期初审定", "计算",
             "期初=0 特殊处理（calcChangeRate）；|变动率|>30% 高亮（isChangeRateExceeding）",
             "useD7FormulaEngine"),
            ("按性质从 D7-2 聚合", "按款项性质 SUM(D7-2 期末审定/期初审定)", "取数",
             "按性质分类区块取数（aggregateByNature / natureAggregation）", "useD7CrossSheet"),
            ("按账龄从 D7-2 聚合", "按项目账龄段 SUM(D7-2 审定账龄)", "取数",
             "按账龄分类区块取数（aggregateAgingByKeys，segment-driven）", "useD7CrossSheet"),
            ("调整按性质/账龄双分组", "D7-3 调整分录按性质与账龄段双分组累加 AJE/RJE", "取数",
             "调整数派生（adjustmentTotals.byNature / byAging）", "useD7CrossSheet"),
            ("试算平衡表数核对", "按账龄合计 − 试算平衡表数(2205)", "logic_check",
             "审定合计与 TB 合同负债(2205)核对（trialBalanceDiff）", "useD7Adjudication"),
            ("性质合计 ↔ 账龄合计交叉验证", "按性质合计 − 按账龄合计", "logic_check",
             "同一总额两视图应相等（crossValidation，容差 0.01）", "useD7CrossSheet"),
        ],
        # D7-2 明细表
        "D7-2": [
            ("期末余额", "期初 + 贷方发生 − 借方发生", "计算",
             "贷方科目期末余额（calcCreditEndBalance）", "useD7FormulaEngine"),
            ("审定数", "未审 + AJE + RJE", "计算",
             "明细审定金额（calcAuditedAmount）", "useD7FormulaEngine"),
        ],
        # D7-3 调整分录
        "D7-3": [
            ("借贷平衡校验", "Σ 借方金额 = Σ 贷方金额", "logic_check",
             "调整分录借贷平衡", "D7-3 调整分录"),
            ("按性质/账龄双分组回写", "借方>0→AJE / 否则贷方→RJE，按性质与账龄段双分组", "取数",
             "回写 D7-1 审定表（adjustmentTotals）", "useD7CrossSheet"),
        ],
        # D7-4 分析
        "D7-4": [
            ("Top10 债务人排序", "按期末审定金额降序取前 10", "计算",
             "Top N 排序（topNByField）", "useD7FormulaEngine"),
        ],
        # D7-6 关联方检查
        "D7-6": [
            ("关联方期末余额", "期初 + 贷方发生 − 借方发生", "计算",
             "贷方科目关联方期末余额（calcCreditEndBalance）", "useD7FormulaEngine"),
        ],
        # D7-7 凭证检查 / 期后结转
        "D7-7": [
            ("期后结转贷方合计", "Σ D7-7 期后结转贷方金额", "取数",
             "供 D7-2 期后结转勾稽（voucherPostTransferTotal）", "useD7CrossSheet"),
        ],
        # 附注披露
        "附注上市": [
            ("附注披露金额", "取自 D7-1 审定表（按性质各行 + 合同负债合计）", "取数",
             "附注取审定数（adjudicationForDisclosure）", "useD7CrossSheet"),
        ],
        "附注国企": [
            ("附注披露金额", "取自 D7-1 审定表（按性质各行 + 合同负债合计）", "取数",
             "附注取审定数（adjudicationForDisclosure）", "useD7CrossSheet"),
        ],
    },
}
