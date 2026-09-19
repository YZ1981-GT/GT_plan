"""L 循环底稿公式 surfacing 目录（与各 useL{n}* composable 同源，不臆造）。

对齐 D 循环 surfacing（wp_surfaced_d._CATALOG）与 E1 标准（wp_formula._E1_SHEET_FORMULAS）：
把「专属组件底稿」（数据存 checklist_responses、无 wp_formula 网格记录）的取数/计算/
逻辑审核公式以只读条目 surface 到公式管理中心，让每张 sheet 都能体现其取数逻辑。

每条公式均可在对应前端 composable 中找到依据（calc 函数 / 跨 sheet 键 / SUMIF 带入 /
TB 核对 / 借贷平衡 / 实际利率法 / 截止跨期判定）；找不到依据的 sheet 不写（宁缺勿造）。
L4~L8 无独立披露 composable（附注仅经 EventBus 刷新，非公式源）→ 不写附注 sheet。

分类只用三种：
  - 取数     跨 sheet / 四表库 / 从明细带入（SUMIF）/ L 循环利息汇聚
  - 计算     表间计算（审定=未审+AJE+RJE、期末余额、变动额/率、合计、净值、
             利息=本金×率×天数、实际利率法摊销、初始计量、权益负债划分等）
  - logic_check  逻辑审核（TB 核对、审定↔明细勾稽、征信↔明细勾稽、借贷平衡、
             差异高亮、逾期分级、担保比例、跨期判定、末期验证等）

科目方向（负债类：期末=期初+贷方−借方；审定=未审+账项调整(AJE)+重分类调整(RJE)）：
  L1 短期借款(2001)/L2 应付利息(2231)/L3 长期借款(2501)/L4 应付债券(2502)/
  L5 长期应付款(2701 原值 + 未确认融资费用备抵借方)/L6 专项应付款(2601)/
  L7 其他非流动负债(2801) 均为负债贷方；
  L8 财务费用(6603) 为损益类借方，取本期发生额（借方发生−贷方发生），无余额概念。
"""
from __future__ import annotations

SheetFormula = tuple[str, str, str, str, str]  # (项目名, 公式, 分类, 说明, 来源)

CATALOG: dict[str, dict[str, list[SheetFormula]]] = {
    # ═══════════════════════════════════════════════════════════════════════
    # L1 短期借款（负债贷方 2001；双期审定 / 利息测算 / 征信核对 / 逾期 / 抵质押）
    # ═══════════════════════════════════════════════════════════════════════
    "L1": {
        # L1-1 审定表（双期结构，4 类：信用/抵押/保证/质押）
        "L1-1": [
            ("审定数", "未审数 + 账项调整(AJE) + 重分类调整(RJE)", "计算",
             "期初/期末各行审定金额（beginAudited/endAudited）", "useL1Adjudication"),
            ("期末审定合计", "Σ 各分类期末审定数", "计算",
             "合计行期末审定（total.endAudited），供 TB 回写 / 逾期表 L1-7 消费（totalAuditedAmount）",
             "useL1Adjudication / useL1FormulaEngine.calcSubtotal"),
            ("变动额", "期末未审 − 期初未审 / 期末审定 − 期初审定", "计算",
             "本期未审/审定较期初变动额（unadjChange/auditedChange）", "useL1Adjudication"),
            ("变动率", "变动额 ÷ 期初基数", "计算",
             "base=0 时特殊处理（无变动→0/正向→1/负向→−1，calcRate）", "useL1Adjudication"),
            ("从 L1-2 明细带入", "按借款种类 SUMIF(明细 期初/期末未审)；期末未审=期初+贷方借入−借方归还", "取数",
             "按信用/抵押/保证/质押聚合明细带入审定表（importFromDetail，_loanTypeToCategoryName）",
             "useL1Adjudication"),
            ("TB 回写(2001)", "期末审定合计 → 回写 trial_balance 科目 2001", "取数",
             "saveAndWriteback + EventBus 'substantive:adjudicated'（accountCode=2001）", "useL1Adjudication"),
            ("审定表 ↔ 明细表勾稽", "审定表期末未审合计 − 明细表期末余额合计", "logic_check",
             "|差额| ≤ 0.01 视为匹配（adjudicationVsDetail）", "useL1CrossSheet"),
        ],
        # L1-2 明细表（30 列宽表，负债类 roll-forward）
        "L1-2": [
            ("期末余额", "期初 + 贷方发生(借入) − 借方发生(归还)", "计算",
             "负债类期末余额（calcLiabilityEndBalance）", "useL1FormulaEngine"),
            ("合计期末余额", "Σ 各行期末余额", "计算",
             "供与审定表 L1-1 交叉验证（totalEndBalance）", "useL1Detail / useL1FormulaEngine.calcSubtotal"),
        ],
        # L1-3 调整分录（AJE/RJE）
        "L1-3": [
            ("借贷平衡校验", "Σ 借方金额 = Σ 贷方金额", "logic_check",
             "AJE/RJE 借贷平衡（|差额| ≤ 0.01，currentBalance.isBalanced）", "useL1Adjustment"),
            ("2001 净影响", "科目 2001 贷方 − 借方", "计算",
             "AJE/RJE 净调增短期借款（ajeNetAmount/rjeNetAmount）", "useL1Adjustment"),
            ("发布调整事件", "借贷平衡 → EventBus 'adjustment:created'", "取数",
             "通知 A13 汇总 + L1-1 审定表累加（saveAndPublish）", "useL1Adjustment"),
        ],
        # L1-4 征信核对
        "L1-4": [
            ("报表日倒轧余额", "征信查询日余额 + 增加金额 − 减少金额", "计算",
             "征信倒轧（calcCreditRollForward，xlsx P11=J11+N11−O11）", "useL1FormulaEngine"),
            ("征信差异", "征信倒轧余额 − 账面借款余额", "logic_check",
             "差异≠0 红色高亮 + 强制填差异说明（calcCreditDiff，完整性核心控制）", "useL1CreditCheck"),
            ("征信 ↔ 明细勾稽", "Σ 征信倒轧余额 − Σ 明细期末余额", "logic_check",
             "|差额| ≤ 0.01 视为一致（creditVsDetail）", "useL1CrossSheet"),
        ],
        # L1-5 利息测算表（实际天数 365 制）
        "L1-5": [
            ("起算时点", "max(报告期起始日, 借款起始日)", "计算",
             "xlsx G11=IF(D11<=$D$9,$D$9,D11)（calcStartDate）", "useL1InterestEngine"),
            ("截止时点", "min(借款到期日, 报告期截止日)", "计算",
             "xlsx H11=IF(E11<=$E$9,E11,$E$9)（calcEndDate）", "useL1InterestEngine"),
            ("计息天数", "(截止−起算)=365→365；否则 (截止−起算)+1", "计算",
             "整年取 365 天，非整年算头算尾+1（calcInterestDays）", "useL1InterestEngine"),
            ("测算利息", "本金 × 年利率 × 计息天数 ÷ 365", "计算",
             "xlsx M11=J11*I11/365*L11（calcInterest，365 天制）", "useL1InterestEngine"),
            ("利息差异", "测算利息 − 账载利息", "logic_check",
             "|差异|>0.01 红色高亮（calcInterestDiff / hasDiffWarning）", "useL1InterestCalc"),
            ("利息 → L2/L8 联动", "Σ 测算利息（短期借款利息全部费用化）", "取数",
             "EventBus 'l1:interest-calculated' 供 L2 计提核对 / L8 利息支出（publishInterestCalculated）",
             "useL1CrossSheet"),
        ],
        # L1-7 逾期检查
        "L1-7": [
            ("逾期天数", "报告期截止日 − 借款到期日", "计算",
             "无到期日→0；正值逾期/负值未到期（calcOverdueDays，xlsx L1-7 J11）", "useL1OverdueCheck / useL1InterestEngine"),
            ("逾期风险分级", "<30天=低(黄)/30~90天=中(橙)/>90天=高(红)", "logic_check",
             "逾期天数分级高亮（overdueLevel）", "useL1OverdueCheck"),
            ("逾期金额合计", "Σ 逾期行 逾期金额", "计算",
             "逾期笔数与金额统计（totalOverdueAmount/overdueCount）", "useL1OverdueCheck"),
        ],
        # L1-8 抵质押检查
        "L1-8": [
            ("担保比例", "抵质押贷款额 ÷ 资产账面净值 × 100", "计算",
             "资产净值=0 时返 0（除零保护，calcPledgeRatio）", "useL1PledgeCheck / useL1FormulaEngine"),
            ("担保比例警告", "担保比例 > 100%", "logic_check",
             "贷款超过担保资产价值（hasRatioWarning）", "useL1PledgeCheck"),
        ],
        # 附注披露（上市/国企）—— category-level 从审定表 L1-1 派生
        "附注上市": [
            ("分类披露金额", "取自审定表 L1-1 各分类审定数（期末=审定期末/上年年末=审定期初）", "取数",
             "披露 → 审定 → 明细链一致（categoryRows 从 L1-adj-* 派生）", "useL1DisclosureData"),
            ("逾期借款表", "从 L1-7 逾期检查带入（逾期金额>0 的行）", "取数",
             "借款单位/期末余额/借款利率(+逾期时间/逾期利率)（importFromOverdueCheck）", "useL1DisclosureData"),
        ],
        "附注国企": [
            ("分类披露金额", "取自审定表 L1-1 各分类审定数（期末=审定期末/期初=审定期初）", "取数",
             "披露 → 审定 → 明细链一致（categoryRows 从 L1-adj-* 派生）", "useL1DisclosureData"),
            ("逾期借款表", "从 L1-7 逾期检查带入（逾期金额>0 的行）", "取数",
             "借款单位/期末余额/借款利率（importFromOverdueCheck）", "useL1DisclosureData"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # L2 应付利息（负债贷方 2231；双期审定含优先股/永续债 + 凭证检查 + 计提核对）
    # ═══════════════════════════════════════════════════════════════════════
    "L2": {
        # L2-1 审定表（双期，5 类 + 优先股/永续债[工具1/工具2汇总] + 其他）
        "L2-1": [
            ("审定数", "未审数 + 账项调整(AJE) + 重分类调整(RJE)", "计算",
             "期初/期末各行审定（beginAudited/endAudited，deriveRow）", "useL2Adjudication"),
            ("优先股/永续债汇总", "工具1 + 工具2", "计算",
             "汇总行不可编辑，自动聚合子行（PREFERRED_SUB_KEYS，aggregateRows）", "useL2Adjudication"),
            ("合计", "Σ(4 主类 + 优先股汇总 + 其他)（不含工具1/工具2子行）", "计算",
             "源模板 =SUM(B7:B10,B13)（totalRow）", "useL2Adjudication"),
            ("变动额/变动率", "期末−期初；变动额÷期初基数", "计算",
             "base=0 特殊处理（unadjChange/auditedChange/calcRate）", "useL2Adjudication"),
            ("从 L2-2 明细带入", "按类别 SUMIF：期初未审=Σ beginBalance；期末未审=Σ endUnadjusted", "取数",
             "长期借款利息/债券利息/短期借款利息/其他聚合带入（importFromDetail，detailSourceToRowKey）",
             "useL2Adjudication"),
            ("与经审计财报核对", "其他应付款合计 = 应付利息审定 + 应付股利审定 + 其他应付款审定；差异 = 合计 − 报表数", "logic_check",
             "财报核对区（reconRows，应付利息审定数自动取合计）", "useL2Adjudication"),
            ("TB 回写(2231)", "期末审定合计 → 回写 trial_balance 科目 2231", "取数",
             "submitAdjudication + EventBus 'substantive:adjudicated'", "useL2Adjudication"),
            ("审定表 ↔ 明细表勾稽", "审定表期末合计 − 明细表期末审定合计", "logic_check",
             "|差额| ≤ 0.01 视为匹配（adjudicationVsDetail）", "useL2CrossSheet"),
        ],
        # L2-2 明细表（27 列 4 区段）
        "L2-2": [
            ("期末应付利息", "期初 + 本期计提 − 本期支付", "计算",
             "负债类期末余额（recalcRowFormulas.endBalance=calcLiabilityEndBalance）", "useL2Detail / useL2FormulaEngine"),
            ("期末未审", "期末应付 + 被审计单位重分类", "计算",
             "明细行期末未审（endUnadjusted）", "useL2Detail"),
            ("审定数", "期末未审 + AJE + RJE", "计算",
             "明细行审定（audited）", "useL2Detail"),
            ("审定期末", "审定期初 + 审定计提 − 审定支付", "计算",
             "审定验证区段（adjustedEnd=calcLiabilityEndBalance）", "useL2Detail"),
            ("按来源小计", "按 source 分组 Σ 期末应付", "计算",
             "供与审定表 L2-1 交叉验证（subtotalBySource）", "useL2Detail"),
            ("本期计提 → L8 联动", "Σ 各行本期计提 + 按来源分类", "取数",
             "EventBus 'l2:accrual-calculated' 供 L8 财务费用（明细 accrued 变化时广播）", "useL2Detail"),
        ],
        # L2-3 调整分录汇总表
        "L2-3": [
            ("借贷平衡校验", "Σ 借方金额 = Σ 贷方金额", "logic_check",
             "AJE/RJE 借贷平衡（|差额| ≤ 0.01，currentBalanceCheck）", "useL2Adjustment"),
            ("2231 净调整额", "科目 2231 贷方 − 借方", "计算",
             "净调增/调减应付利息（ajeNetAmount/rjeNetAmount）", "useL2Adjustment"),
            ("发布调整 + 推送 A13", "借贷平衡 → EventBus 'adjustment:created' + 'a13:push-misstatement'", "取数",
             "通知 L2-1 审定表 + AJE 视为错报候选推送 A13（submitAdjustment）", "useL2Adjustment"),
        ],
        # L2-4 应付利息检查表（凭证级）
        "L2-4": [
            ("检查合计(借/贷)", "Σ 凭证检查行 借方/贷方金额", "计算",
             "凭证级检查合计（checkedDebitTotal/checkedCreditTotal）", "useL2VoucherCheck"),
            ("本期发生额", "借方=Σ 明细本期支付(paid)；贷方=Σ 明细本期计提(accrued)", "取数",
             "来自 L2-2 明细（periodDebitOccurrence/periodCreditOccurrence）", "useL2VoucherCheck"),
            ("检查比例", "检查合计 ÷ 本期发生额", "计算",
             "借/贷方检查覆盖比例（debitCheckRatio/creditCheckRatio）", "useL2VoucherCheck"),
            ("核对内容①~⑤完整性", "有金额行需 ①原始凭证齐全∧②授权批准∧③会计处理正确∧④金额相符∧⑤期间归属 全勾", "logic_check",
             "未全勾进 incompleteRows（CHECK_LABELS）", "useL2VoucherCheck"),
        ],
        # 附注披露（上市/国企）—— 分类固定行从 L2-2 明细 SUMIF 聚合
        "附注上市": [
            ("分类披露金额", "按类别 SUMIF(L2-2)：期末=Σ审定期末(audited)；上年年末=Σ审定期初(adjustedBegin)", "取数",
             "5 类 + 优先股(工具1+工具2汇总) + 其他 + 合计（disclosureRows，detailSourceToRowKey）", "useL2Disclosure"),
            ("重要逾期未付利息表", "从 L2-2 明细 isOverdue 行提取", "取数",
             "借款单位/逾期金额/逾期原因（overdueRows）", "useL2Disclosure"),
        ],
        "附注国企": [
            ("分类披露金额", "按类别 SUMIF(L2-2)：期末=Σ审定期末；期初=Σ审定期初", "取数",
             "5 类 + 优先股汇总 + 其他 + 合计（disclosureRows）", "useL2Disclosure"),
            ("重要逾期未付利息表", "从 L2-2 明细 isOverdue 行提取", "取数",
             "借款单位/逾期金额/逾期原因（overdueRows）", "useL2Disclosure"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # L3 长期借款（负债贷方 2501；双期审定含减一年内到期 + 利息 + 重分类 + 凭证检查）
    # ═══════════════════════════════════════════════════════════════════════
    "L3": {
        # L3-1 审定表（双期，4 类，含减一年内到期 → 披露审定数）
        "L3-1": [
            ("审定数", "未审数 + 账项调整(AJE) + 重分类调整(RJE)", "计算",
             "期初/期末各行审定（beginAudited/endAudited，源模板 E7=B7+C7+D7）", "useL3Adjudication / useL3FormulaEngine"),
            ("披露审定数", "审定数 − 减：一年内到期的长期借款", "计算",
             "流动/非流动重分类后非流动披露数（beginDisclosed/endDisclosed）", "useL3Adjudication"),
            ("合计", "Σ 各分类（质押/抵押/保证/信用）", "计算",
             "合计行（buildTotalRow，calcSubtotal）", "useL3Adjudication / useL3FormulaEngine"),
            ("变动额/变动率", "期末−期初；变动额÷期初基数", "计算",
             "base=0 特殊处理（unadjChange/auditedChange/calcRate）", "useL3Adjudication"),
            ("从 L3-2 明细带入", "按借款类型 SUMIF：期初未审=Σ beginning；期末未审=Σ endBalance；期末一年内到期=Σ currentPortion", "取数",
             "质押/抵押/保证/信用聚合带入（importFromDetail，loanTypeToRowKey）", "useL3Adjudication"),
            ("TB 回写(2501)", "期末审定合计 → 回写 trial_balance 科目 2501", "取数",
             "submitAdjudication + EventBus 'substantive:adjudicated'", "useL3Adjudication"),
            ("审定表 ↔ 明细表勾稽", "审定表期末合计 − 明细表期末余额合计", "logic_check",
             "|差额| ≤ 0.01 视为匹配（adjudicationVsDetail）", "useL3CrossSheet"),
        ],
        # L3-2 明细表（负债类 roll-forward）
        "L3-2": [
            ("期末余额", "期初 + 贷方发生(借入) − 借方发生(归还)", "计算",
             "负债类期末余额（calcLiabilityEndBalance，源模板 K=H+I−J）", "useL3FormulaEngine"),
        ],
        # L3-3 调整分录 / 一年内到期重分类
        "L3-3": [
            ("借贷平衡校验", "Σ 借方金额 = Σ 贷方金额", "logic_check",
             "AJE/RJE 借贷平衡", "useL3Adjustment"),
            ("一年内到期判定", "到期日 ≤ 报告日+1年 → 全额重分类；否则 0", "logic_check",
             "日历年+1（含边界，calcCurrentPortion）", "useL3ReclassEngine"),
            ("重分类分录(RJE)", "借：长期借款(2501) / 贷：一年内到期的非流动负债(2801)", "计算",
             "一年内到期重分类（buildReclassEntry）", "useL3ReclassEngine"),
            ("一年内到期合计", "Σ L3-2 明细各行 currentPortion", "取数",
             "供 L3-1 披露审定 + 流动/非流动列报（currentPortionTotal）", "useL3CrossSheet"),
        ],
        # L3-4 征信核对
        "L3-4": [
            ("征信差异", "征信余额 − 账面借款余额", "logic_check",
             "差异≠0 红色高亮 + 差异说明（calcCreditDiff，源模板 R=P−Q）", "useL3FormulaEngine"),
            ("征信 ↔ 明细勾稽(完整性)", "Σ 征信余额 − Σ 明细期末余额", "logic_check",
             "正值=征信大于账面(未入账借款)/负值=虚增借款（creditVsDetail）", "useL3CrossSheet"),
        ],
        # L3-5 利息测算表（实际天数 365 制）
        "L3-5": [
            ("计息天数", "起算=max(报告起始,借款起始)；截止=min(借款到期,报告截止)；(截止−起算)=365→365 否则+1", "计算",
             "报告期区间裁剪（calcInterestDays，xlsx L3-5 L11）", "useL3InterestEngine"),
            ("测算利息", "本金 × 年利率 × 计息天数 ÷ 365", "计算",
             "365 天制（calcInterest，xlsx M11=J11*I11/365*L11）", "useL3InterestEngine"),
            ("利息差异", "测算利息 − 账载利息", "logic_check",
             "正=少计/负=多计（calcInterestDiff，xlsx N11=M11−K11）", "useL3InterestEngine"),
            ("利息 → L2/L8 联动", "Σ 测算利息（非资本化部分计入财务费用）", "取数",
             "EventBus 'l3:interest-calculated' 供 L2 计提核对 / L8 利息支出（publishInterestCalculated）",
             "useL3CrossSheet"),
        ],
        # L3-8 抵质押资产检查
        "L3-8": [
            ("担保比例", "担保借款额 ÷ 资产账面价值 × 100", "计算",
             "账面价值=0 时返 0（除零保护，calcPledgeRatio）", "useL3FormulaEngine"),
        ],
        # L3-9 长期借款检查表（凭证级）
        "L3-9": [
            ("检查合计(借/贷)", "Σ 凭证检查行 借方/贷方金额", "计算",
             "凭证级检查合计（checkedDebitTotal/checkedCreditTotal）", "useL3VoucherCheck"),
            ("本期发生额", "借方=Σ 明细本期归还(repaid)；贷方=Σ 明细本期借入(borrowed)", "取数",
             "来自 L3-2 明细（periodDebitOccurrence/periodCreditOccurrence）", "useL3VoucherCheck"),
            ("检查比例", "检查合计 ÷ 本期发生额", "计算",
             "借/贷方检查覆盖比例（debitCheckRatio/creditCheckRatio）", "useL3VoucherCheck"),
            ("核对内容①~⑤完整性", "有金额行需核对①~⑤全勾", "logic_check",
             "未全勾进 incompleteRows（L3_CHECK_LABELS）", "useL3VoucherCheck"),
        ],
        # 附注披露（上市/国企）—— 分类固定行从 L3-2 明细 SUMIF + 减一年内到期
        "附注上市": [
            ("分类披露金额", "按借款类型 SUMIF(L3-2)：期末=Σ审定期末(audited)；上年年末=Σ审定期初(beginning)", "取数",
             "质押/抵押/保证/信用 + 小计 − 减一年内到期 → 合计（classificationRows，loanTypeToRowKey）", "useL3Disclosure"),
            ("减一年内到期", "小计 − 减：一年内到期(Σ currentPortion)", "计算",
             "合计=小计−一年内到期（classificationRows 合计行）", "useL3Disclosure"),
            ("一年内到期子表", "按借款类型 Σ currentPortion", "取数",
             "(1) 一年内到期的长期借款子表（currentPortionRows）", "useL3Disclosure"),
        ],
        "附注国企": [
            ("分类披露金额", "按借款类型 SUMIF(L3-2)：期末=Σ审定期末；期初=Σ审定期初", "取数",
             "质押/抵押/保证/信用 + 小计 − 减一年内到期 → 合计（classificationRows）", "useL3Disclosure"),
            ("一年内到期子表", "按借款类型 Σ currentPortion", "取数",
             "(1) 一年内到期的长期借款子表（currentPortionRows）", "useL3Disclosure"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # L4 应付债券（负债贷方 2502；双期品种×子项 + 实际利率法 + 初始计量 + 权益负债划分）
    # ═══════════════════════════════════════════════════════════════════════
    "L4": {
        # L4-1 审定表（双期，品种[普通/可转换]×子项[成本/利息调整/应计利息]，含减一年内到期）
        "L4-1": [
            ("审定数", "未审数 + 账项调整(AJE) + 重分类调整(RJE)", "计算",
             "叶子行期初/期末审定（beginAudited/endAudited，_derive）", "useL4Adjudication / useL4FormulaEngine"),
            ("披露审定数", "审定数 − 减：一年内到期的应付债券", "计算",
             "流动/非流动重分类（beginDisclosed/endDisclosed）", "useL4Adjudication"),
            ("品种小计", "Σ 该品种(成本+利息调整+应计利息)叶子", "计算",
             "普通/可转换债券品种小计（buildSubtotal）", "useL4Adjudication"),
            ("合计", "Σ 全品种叶子", "计算",
             "合计行（totalRow）", "useL4Adjudication"),
            ("变动额/变动率", "期末−期初；变动额÷期初基数", "计算",
             "base=0 特殊处理（unadjChange/auditedChange/calcRate）", "useL4Adjudication"),
            ("从 L4-2 明细带入", "按品种×子项聚合摊余成本：成本/利息调整期末=期初+贷−借；应计利息取期末", "取数",
             "普通/可转换 × 成本/利息调整/应计利息聚合带入（importFromDetail）", "useL4Adjudication"),
            ("TB 回写(2502)", "期末审定合计 → 回写 trial_balance 科目 2502", "取数",
             "submitAdjudication + EventBus 'substantive:adjudicated'", "useL4Adjudication"),
            ("审定表 ↔ 明细表勾稽", "审定表合计 − 明细表(成本+利息调整+应计利息)期末合计", "logic_check",
             "|差额| < 1 视为匹配（adjudicationVsDetail）", "useL4CrossSheet"),
        ],
        # L4-2 明细表（负债类 roll-forward，摊余成本分解）
        "L4-2": [
            ("期末摊余成本", "期末成本 + 期末利息调整 + 期末应计利息；各分项期末=期初+贷−借", "计算",
             "负债类期末余额（calcLiabilityEndBalance）", "useL4FormulaEngine / useL4Detail"),
        ],
        # L4-5 权益与负债划分检查（CAS37 复合金融工具分拆）
        "L4-5": [
            ("负债成分", "Σ 未来现金流 ÷ (1+市场利率)^期数", "计算",
             "未来现金流按市场利率折现现值（calcLiabilityComponent，市场利率=0 则不折现）", "useL4EquityLiabEngine"),
            ("权益成分", "发行总额 − 负债成分", "计算",
             "剩余法（calcEquityComponent，CAS37）", "useL4EquityLiabEngine"),
            ("分拆异常判定", "权益成分 < 0", "logic_check",
             "红色警告：市场利率过低/不含转换权（isAbnormal，Req10.3）", "useL4EquityLiabCheck"),
        ],
        # L4-6 初始计量
        "L4-6": [
            ("初始入账金额", "发行价格 − 交易费用", "计算",
             "金融负债初始摊余成本（calcInitialAmount，CAS22）", "useL4FormulaEngine"),
            ("溢折价", "初始入账金额 − 面值", "计算",
             "正=溢价/负=折价/0=平价（calcPremiumDiscount）", "useL4FormulaEngine"),
            ("实际利率(IRR)", "使 Σ 现金流现值 = 初始入账金额 的贴现率", "计算",
             "二分法求解 EIR（solveEIR，bullet/installment 现金流构造）", "useL4InitialMeasure / useL4EIREngine"),
        ],
        # L4-7 后续计量（实际利率法，2 分支）
        "L4-7": [
            ("利息费用", "期初摊余成本 × 实际利率(EIR)", "计算",
             "实际利率法利息费用（calcInterestExpense）", "useL4EIREngine"),
            ("期末摊余成本(到期一次还本付息)", "期初 + 利息费用", "计算",
             "bullet 分支利息全资本化滚入（calcEndAmortizedCost_Bullet）", "useL4EIREngine"),
            ("期末摊余成本(分期付息)", "期初 + 利息费用 − 票面利息", "计算",
             "installment 分支（calcEndAmortizedCost_Installment）", "useL4EIREngine"),
            ("末期验证", "|末期期末摊余成本 − 面值| < 1", "logic_check",
             "installment 分支末期≈面值（validateSchedule）", "useL4Subsequent / useL4EIREngine"),
            ("利息费用 → L2/L8 联动", "Σ 各期利息费用", "取数",
             "EventBus 'l4:interest-calculated' 供 L2 计提核对 / L8 利息支出（publishInterestCalculated）",
             "useL4CrossSheet / useL4Subsequent"),
        ],
        # L4-8 账面核对
        "L4-8": [
            ("账面 ↔ 测算摊余成本核对", "L4-8 账面摊余成本 − L4-7 测算摊余成本", "logic_check",
             "|差额| < 1 视为匹配（bookReconVsSubsequent）", "useL4CrossSheet"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # L5 长期应付款（负债贷方 2701 + 未确认融资费用备抵借方；三区段净值 + 摊销）
    # ═══════════════════════════════════════════════════════════════════════
    "L5": {
        # L5-1 审定表（双期·三区段：原值/未确认融资费用/净值，含减一年内到期）
        "L5-1": [
            ("审定数", "未审数 + 账项调整(AJE) + 重分类调整(RJE)", "计算",
             "原值/未确认各行期初/期末审定（deriveRow，源模板 E8=B8+C8+D8）", "useL5Adjudication / useL5FormulaEngine"),
            ("净值", "原值 − 未确认融资费用（逐行按 category 对齐）", "计算",
             "报表列报=面值−未确认=现值（computedNetRows，calcNetPayable）", "useL5Adjudication / useL5FormulaEngine"),
            ("披露审定数", "审定数 − 减：一年内到期", "计算",
             "净值最终审定（endDisclosed）→ 长期应付款非流动披露数", "useL5Adjudication"),
            ("区段合计", "Σ 三类(融资租赁/分期付款/其他)", "计算",
             "原值合计/未确认合计/净值合计（grossTotal/unrecognizedTotal/netTotal）", "useL5Adjudication"),
            ("与经审计财报核对", "长期应付款(=净值最终审定) + 专项应付款(手填) = 合计", "logic_check",
             "财报核对（reconTotal，netFinalAudited=netTotal.endDisclosed）", "useL5Adjudication"),
            ("TB 回写(2701+未确认)", "原值审定 + 未确认融资费用审定 → 双科目回写", "取数",
             "saveAndWriteback + EventBus 'substantive:adjudicated'", "useL5Adjudication"),
            ("审定表 ↔ 明细表勾稽", "审定表合计审定数 − 明细表期末余额合计", "logic_check",
             "|差额| < 1 视为匹配（adjudicationVsDetail）", "useL5CrossSheet"),
        ],
        # L5-2 长期应付款明细表（负债类 roll-forward）
        "L5-2": [
            ("期末余额", "期初 + 贷方发生(新增应付) − 借方发生(偿还)", "计算",
             "负债类期末余额（calcLiabilityEndBalance，源模板 E11=B11−C11+D11）", "useL5FormulaEngine / useL5Detail"),
        ],
        # L5-3 未确认融资费用明细表（备抵借方）
        "L5-3": [
            ("备抵期末余额", "期初 + 借方发生(新增未确认) − 贷方发生(摊销冲减)", "计算",
             "负债备抵类方向（calcContraLiabilityEndBalance）", "useL5FormulaEngine / useL5UnrecognizedDetail"),
            ("未确认 ↔ 摊销表勾稽", "L5-3 未确认余额合计 − L5-5 未摊销余额合计", "logic_check",
             "|差额| < 1 视为一致（unrecognizedVsAmortization）", "useL5CrossSheet"),
        ],
        # L5-5 摊销测算表（实际利率法）
        "L5-5": [
            ("每期摊销(确认的融资费用)", "期初摊余成本 × 实际利率(EIR)", "计算",
             "确认的融资费用（calcAmortization，源模板 F=H×C）", "useL5AmortizationEngine"),
            ("期末摊余成本", "期初 − 付款 + 摊销", "计算",
             "本金减少=付款−摊销；期末=期初−本金减少（calcEndCost）", "useL5AmortizationEngine"),
            ("末期验证", "|末期期末摊余成本| < 1", "logic_check",
             "全部还清时余额≈0（validateSchedule）", "useL5AmortizationEngine"),
            ("本期摊销 → L8 联动", "L5-5 本期(isCurrent)摊销合计", "取数",
             "EventBus 'l5:amortization-calculated' 供 L8 财务费用（publishAmortizationCalculated）",
             "useL5CrossSheet"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # L6 专项应付款（负债贷方 2601；审定 + 明细 + 调整 + 检查）
    # ═══════════════════════════════════════════════════════════════════════
    "L6": {
        # L6-1 审定表（按专项项目 + 合计）
        "L6-1": [
            ("审定数", "未审数 + 账项调整(AJE) + 重分类调整(RJE)", "计算",
             "期初/期末审定（calcAuditedAmount）", "useL6Adjudication / useL6FormulaEngine"),
            ("合计", "Σ 各专项项目", "计算",
             "合计行（calcSubtotal）", "useL6Adjudication"),
            ("变动额", "期末审定 − 期初审定", "计算",
             "本期变动额（calcVariance）", "useL6FormulaEngine"),
            ("变动率", "期初=0∧变动=0→0；期初=0∧变动>0→1；否则 变动额÷期初", "计算",
             "源模板 K7 逻辑（calcVarianceRate）", "useL6FormulaEngine"),
            ("TB 回写(2601)", "期末审定合计 → 回写 trial_balance 科目 2601", "取数",
             "saveAndWriteback + EventBus 'substantive:adjudicated'", "useL6Adjudication"),
            ("审定表 ↔ 明细表勾稽", "审定表合计期末审定 − Σ 明细各专项项目期末余额", "logic_check",
             "差额=0 视为匹配（validateAdjudicationVsDetail / adjudicationVsDetail）", "useL6CrossSheet / useL6FormulaEngine"),
        ],
        # L6-2 明细表（负债类）
        "L6-2": [
            ("明细期末余额", "期初 + 本期拨入 − 本期结转 − 本期返还", "计算",
             "负债类专项项目期末（calcDetailEndBalance；本期结转+返还=借方发生）", "useL6FormulaEngine"),
        ],
        # L6-3 调整分录汇总
        "L6-3": [
            ("借贷平衡校验", "Σ 借方调整金额 = Σ 贷方调整金额", "logic_check",
             "类别(报表调整/账项调整/其他)+借方/贷方（L6-3 F/G 列）", "useL6Adjustment"),
        ],
        # L6-4 检查表
        "L6-4": [
            ("检查比例", "已检查金额 ÷ 本期发生额", "计算",
             "本期发生额=0 时返 0（calcCheckRatio）", "useL6FormulaEngine / useL6SpecialCheck"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # L7 其他非流动负债（负债贷方 2801；审定 + 明细 + 调整）
    # ═══════════════════════════════════════════════════════════════════════
    "L7": {
        # L7-1 审定表（5 项目行 + 合计）
        "L7-1": [
            ("审定数", "未审数 + 账项调整(AJE) + 重分类调整(RJE)", "计算",
             "期初/期末审定（calcAuditedAmount）", "useL7Adjudication / useL7FormulaEngine"),
            ("合计", "Σ 各项目行", "计算",
             "合计行（calcSubtotal，源模板 row12 SUM）", "useL7Adjudication"),
            ("变动额", "本期审定 − 上期审定", "计算",
             "本期变动额（calcVariance）", "useL7FormulaEngine"),
            ("变动率", "上期=0∧本期=0→0；上期=0∧本期>0→1；否则 本期÷上期", "计算",
             "源模板 IF 逻辑（calcVarianceRate）", "useL7FormulaEngine"),
            ("TB 回写(2801)", "期末审定合计 → 回写 trial_balance 科目 2801", "取数",
             "saveAndWriteback + EventBus 'substantive:adjudicated'", "useL7Adjudication"),
            ("审定表 ↔ 明细表勾稽", "审定表合计期末审定 − Σ 明细各项目期末余额", "logic_check",
             "差额=0 视为匹配（validateAdjudicationVsDetail）", "useL7CrossSheet / useL7FormulaEngine"),
        ],
        # L7-2 明细表（负债类）
        "L7-2": [
            ("明细期末余额", "期初 + 本期增加 − 本期减少", "计算",
             "负债类项目期末（calcDetailEndBalance）", "useL7FormulaEngine"),
        ],
        # L7-3 调整分录汇总
        "L7-3": [
            ("借贷平衡校验", "Σ 借方调整金额 = Σ 贷方调整金额", "logic_check",
             "类别(报表调整/账项调整/其他)+借方/贷方（L7-3 G/H 列）", "useL7Adjustment"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # L8 财务费用（损益类借方 6603，取本期发生额；审定签名合计 + 利息汇聚 + 截止）
    # ═══════════════════════════════════════════════════════════════════════
    "L8": {
        # L8-1 审定表（10 费用项目 + 签名合计）
        "L8-1": [
            ("审定数", "未审数(本期发生额) + 账项调整(AJE) + 重分类调整(RJE)", "计算",
             "损益类各行审定（calcAuditedAmount）", "useL8Adjudication / useL8FormulaEngine"),
            ("本期发生额", "借方发生 − 贷方发生", "计算",
             "损益类取发生额，非期末余额（calcOccurrence）", "useL8FormulaEngine"),
            ("合计(签名求和)", "利息费用总额−利息资本化−利息收入+未确认融资费用−未实现融资收益+承兑贴息+汇兑损失−汇兑收益−汇兑资本化+手续费及其他", "计算",
             "各项目 sign(±1) 加减求和（totalRow，源模板 =B7−B8−B9+B10−B11+B12+B13−B14−B15+B16）", "useL8Adjudication"),
            ("变动额", "本期审定 − 上期发生额", "计算",
             "变动额（calcChangeAmount）", "useL8FormulaEngine"),
            ("变动率", "(本期 − 上期) ÷ 上期 × 100", "计算",
             "上期=0 返 'N/A'（calcChangeRate）；|变动率|>20% 异常高亮（isChangeRateExceeding）", "useL8FormulaEngine"),
            ("TB 回写(6603 发生额)", "本期审定合计 → 回写 trial_balance 科目 6603（发生额口径）", "取数",
             "saveAndWriteback + EventBus 'substantive:adjudicated'", "useL8Adjudication"),
            ("审定表 ↔ 明细表勾稽", "审定表本期审定合计 − 明细表净财务费用合计", "logic_check",
             "|差额| < 0.01 视为匹配（validateAdjudicationVsDetail / adjudicationVsDetail）", "useL8CrossSheet / useL8FormulaEngine"),
        ],
        # L8-2 明细表（23 列，1-12 月 + 审定 + 占比）
        "L8-2": [
            ("本期未审合计", "Σ(1月 ~ 12月)", "计算",
             "月度合计（N=SUM(B:M)，calcSubtotal）", "useL8Detail / useL8FormulaEngine"),
            ("本期审定", "本期未审合计 + AJE + RJE", "计算",
             "明细行审定（Q=N+O+P，calcAuditedAmount）", "useL8Detail"),
            ("占比", "本行本期审定 ÷ 合计行本期审定 × 100", "计算",
             "各费用项目占比（R 列）", "useL8Detail"),
            ("净财务费用", "利息支出 − 利息收入 + 汇兑损益 + 手续费 + 其他", "计算",
             "利息收入为减项（calcNetFinanceExpense）", "useL8FormulaEngine"),
        ],
        # L8-3 调整分录汇总
        "L8-3": [
            ("借贷平衡校验", "Σ 借方金额 = Σ 贷方金额", "logic_check",
             "类别(报表调整/账项调整/其他)+借方/贷方（useL8Adjustment）", "useL8Adjustment"),
            ("发布调整事件", "EventBus 'adjustment:created'", "取数",
             "通知 A13 汇总 + L8-1 审定表", "useL8Adjustment"),
        ],
        # L8-4 非金融机构利息支出测算
        "L8-4": [
            ("计息天数", "(还款日−借款日)=365→365；否则 (还款日−借款日)+1", "计算",
             "整年 365 不加 1，非整年算头算尾+1（calcInterestDays）", "useL8NonFinInterest"),
            ("应计利息", "年利率 × 本金 ÷ 365 × 计息天数", "计算",
             "actual/365 制（calcAccruedInterest）", "useL8NonFinInterest"),
            ("可扣除利息", "本金 × 同期金融机构基准利率 × 天数 ÷ 360", "计算",
             "税前扣除限额，360 天制（calcDeductibleInterest，所得税法实施条例第38条）", "useL8InterestEngine"),
            ("超标利息", "账载利息 − 可扣除利息", "logic_check",
             ">0 橙色提示纳税调增（calcExcessInterest / hasExcessInterest）", "useL8InterestEngine / useL8NonFinInterest"),
            ("L 循环利息汇聚", "L1 短期借款 + L3 长期借款 + L4 应付债券 + L5 未确认融资费用摊销", "取数",
             "订阅 l1/l3/l4/l5 利息事件汇总（aggregateInterest / interestFromLCycle）", "useL8CrossSheet / useL8InterestEngine"),
            ("测算 ↔ 账面利息一致性", "L 循环测算利息合计 − 账面利息支出(L8-2)", "logic_check",
             "|差额| < 100 元视为一致（calcInterestDiff / estimatedVsBooked）", "useL8CrossSheet"),
        ],
        # L8-5 截止测试
        "L8-5": [
            ("跨期判定", "应归属期间 ≠ 实际入账期间 → 跨期", "logic_check",
             "费用归属与记账不一致（isCrossPeriod）", "useL8CutoffEngine / useL8CutoffTest"),
            ("截止窗口提取", "报表日 ±N 天(默认±5)内的序时账明细", "取数",
             "序时账窗口提取（extractCutoffWindow）", "useL8CutoffEngine"),
            ("跨期金额合计", "Σ 跨期条目金额", "计算",
             "跨期条目汇总（calcCrossPeriodTotal）", "useL8CutoffEngine"),
            ("跨期率", "跨期笔数 ÷ 窗口内总笔数 × 100", "计算",
             "窗口内跨期率（calcCrossPeriodRate）", "useL8CutoffEngine / useL8CutoffTest"),
        ],
    },
}

