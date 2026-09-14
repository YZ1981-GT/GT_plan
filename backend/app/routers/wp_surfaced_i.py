"""I 循环底稿公式 surfacing 目录（与各 useI{n}* composable 同源，不臆造）。

对齐 D 循环（wp_surfaced_d._CATALOG）与 E1 标准：把「专属组件底稿」（数据存
checklist_responses、无 wp_formula 网格记录）的取数/计算/逻辑审核公式以只读条目
surface 到公式管理中心，让每张 sheet 都能体现其取数逻辑。

每条公式均可在对应前端 composable 中找到依据（calc 函数 / 跨 sheet 键 / TB 核对 /
合计聚合）；找不到依据的 sheet 不写（宁缺勿造）。

分类只用三种：
  - 取数     跨 sheet / 四表库 / 从明细带入
  - 计算     表间计算（审定=未审+AJE+RJE、期末余额、净值、摊销、变动额/率、合计等）
  - logic_check  逻辑审核（TB 核对、审定↔明细勾稽、三角勾稽、借贷平衡、跨期判定、
                 CAS6/CAS8 判定、VR-I6-01 校验等）

科目方向（从各 composable 的 ACCOUNT_CODE_* 常量核实）：
  I1 无形资产：1701 无形资产（借方/资产类）+ 1702 累计摊销（贷方/备抵类）
              + 1703 无形资产减值准备（贷方/备抵类）
  I2 开发支出：1717 开发支出（借方/资产类）
  I3 商誉：    1711 商誉（借方/资产类，**不摊销**，仅年度减值测试）
  I4 长期待摊费用：1801（借方/资产类）
  I5 其他非流动资产：1911（借方/资产类）
  I6 研发费用：6602（**损益类/借方科目**，取发生额非余额；净发生额=借方−贷方）
"""
from __future__ import annotations

SheetFormula = tuple[str, str, str, str, str]  # (项目名, 公式, 分类, 说明, 来源)

CATALOG: dict[str, dict[str, list[SheetFormula]]] = {
    # ═══════════════════════════════════════════════════════════════════════
    # I1 无形资产（1701 原值借方 + 1702 累计摊销贷方备抵 + 1703 减值准备贷方备抵）
    #   三区块净值结构 + 摊销测算/分配 + 减值DCF + 使用寿命/权属/政策检查
    # ═══════════════════════════════════════════════════════════════════════
    "I1": {
        # I1-1 审定表（三区块：原值/累计摊销/减值准备 + 净值合计）
        "I1-1": [
            ("审定数", "未审数 + 账项调整(AJE) + 重分类调整(RJE)", "计算",
             "各行审定金额（calcAuditedAmount）", "useI1FormulaEngine.calcAuditedAmount"),
            ("原值期末余额(1701)", "期初余额 + 本期增加 − 本期减少", "计算",
             "资产类借方科目期末余额（calcAssetEndBalance）", "useI1FormulaEngine.calcAssetEndBalance"),
            ("摊销/减值期末余额(1702/1703)", "期初余额 + 增加(贷方) − 减少(借方)", "计算",
             "备抵类贷方科目期末余额（calcContraEndBalance）", "useI1FormulaEngine.calcContraEndBalance"),
            ("区块小计", "Σ 区块内明细行各列", "计算",
             "原值/累计摊销/减值准备三区块各自小计（calcSubtotal）", "useI1Adjudication.costSubtotal/amortSubtotal/impairmentSubtotal"),
            ("无形资产净值合计", "原值小计审定 − 累计摊销小计审定 − 减值准备小计审定", "计算",
             "末行净值联动（calcNetValue）", "useI1FormulaEngine.calcNetValue"),
            ("净值变动额", "期末净值审定 − 期初净值", "计算",
             "四、净值按分类变动额（netRows.changeAmount）", "useI1Adjudication.netRows"),
            ("净值变动率", "(期末净值 − 期初净值) ÷ 期初净值 × 100", "计算",
             "期初=0 返回 null；|变动率|≥30% 高亮标记重大变动（calcChangeRate）", "useI1FormulaEngine.calcChangeRate"),
            ("从 I1-2 按分类带入", "按分类聚合原值/摊销/减值各区块期初/增加/减少/期末/未审", "取数",
             "book 模式带未审保留 AJE/RJE，full 模式带审定并清零（fillFromDetail）", "useI1Adjudication.fillFromDetail"),
            ("三角勾稽校验", "期末 − (期初 + 增加 − 减少) = 0", "logic_check",
             "各行及三区块小计勾稽平衡（calcTriangleReconciliation，容差 0.01）", "useI1FormulaEngine.calcTriangleReconciliation"),
            ("试算平衡表数核对", "各区块审定小计 − 试算平衡表数(1701/1702/1703)", "logic_check",
             "审定数与 TB 各科目未审数核对（differenceRows）", "useI1Adjudication.differenceRows"),
            ("审定表 ↔ I1-2 明细交叉验证", "原值/摊销/减值小计审定 − I1-2 明细各科目期末合计", "logic_check",
             "差异>0.01 黄色警告（crossValidation）", "useI1Adjudication.crossValidation / useI1CrossSheet.adjudicationFromDetail"),
            ("试算表1701原值期末(TB核对)", "TB('1701','期末余额')", "取数", "审定表TB↔审定核对标量，原值", "Tier A"),
            ("试算表1702摊销期末(TB核对)", "TB('1702','期末余额')", "取数", "审定表TB↔审定核对标量，备抵", "Tier A"),
            ("试算表1703减值期末(TB核对)", "TB('1703','期末余额')", "取数", "审定表TB↔审定核对标量，备抵", "Tier A"),
        ],
        # I1-2 明细表
        "I1-2": [
            ("原值期末合计", "Σ 各行 costEnd", "计算",
             "科目 1701 原值期末聚合（detailTotals.cost）", "useI1CrossSheet.detailTotals"),
            ("累计摊销期末合计", "Σ 各行 accAmortEnd", "计算",
             "科目 1702 摊销期末聚合（detailTotals.accAmort）", "useI1CrossSheet.detailTotals"),
            ("减值准备期末合计", "Σ 各行 impairmentEnd", "计算",
             "科目 1703 减值期末聚合（detailTotals.impairment）", "useI1CrossSheet.detailTotals"),
            ("净值", "原值 − 累计摊销 − 减值准备", "计算",
             "明细行净值（calcNetValue）", "useI1FormulaEngine.calcNetValue"),
        ],
        # I1-3 调整分录
        "I1-3": [
            ("借贷平衡校验", "Σ 借方金额 = Σ 贷方金额（容差 0.01）", "logic_check",
             "调整分录借贷平衡（isBalanced）", "useI1FormulaEngine.isBalanced"),
            ("AJE/RJE 按科目回写审定表", "按 1701/1702/1703 汇总 AJE/RJE 净额(借−贷)", "取数",
             "报表/重分类调整→RJE，其余→AJE，回写 I1-1 三区块（adjustmentNets）", "useI1CrossSheet.adjustmentNets"),
        ],
        # I1-4 摊销/减值政策检查
        "I1-4": [
            ("政策合规五维判断", "五维判断均为「是」→政策适当；任一「否」→需关注", "logic_check",
             "被审计单位摊销/减值政策五维检查（CAS_CHECK_DEFS）", "useI1PolicyCheck"),
            ("同行业政策对标", "本单位政策 vs 同行业 ≤4 家对标公司政策", "logic_check",
             "关注是否过于激进（peer companies 对标）", "useI1PolicyCheck"),
            ("按类别从 I1-2 聚合寿命众数", "按分类聚合明细寿命/摊销方法众数", "取数",
             "供政策合理性判断（aggregateCategoriesFromDetail）", "useI1PolicyCheck.aggregateCategoriesFromDetail"),
        ],
        # I1-5 增加检查
        "I1-5": [
            ("检查比例", "检查合计(样本) ÷ 本期发生额(总体) × 100", "计算",
             "增加检查覆盖率（summary.coverageRate）", "useI1AdditionCheck.summary"),
            ("检查比例告警", "检查比例 < 告警阈值(默认 20%) ∧ 本期发生额>0", "logic_check",
             "覆盖率过低提示扩大样本（coverageLow）", "useI1AdditionCheck.coverageLow"),
            ("本期发生额取数", "取自 I1-1 审定表原值本期增加合计", "取数",
             "总体发生额自 I1-adjudication-cost-addition-total 带入（linkedPeriodTotal）", "useI1AdditionCheck.syncPeriodFromLinked"),
            ("追查金额差异", "来源金额 − 账面金额", "计算",
             "追查证据与账面核对（calcI1TraceAmountDiff）", "useI1AdditionCheck.calcI1TraceAmountDiff"),
            ("从 I2 转入带入", "订阅 development:capitalized-to-intangible 事件带入转入明细", "取数",
             "I2 开发支出转入无形资产（seedI1AdditionFromI2Transfer）", "useI1AdditionCheck"),
        ],
        # I1-6 处置检查
        "I1-6": [
            ("处置净值", "原值 − 累计摊销 − 减值准备", "计算",
             "处置资产账面净值（calcI1DisposalNet）", "useI1DisposalCheck.calcI1DisposalNet"),
            ("处置损益", "清理收入 − 清理费用 − 账面净值", "计算",
             "处置损益（calcI1DisposalGainLoss）", "useI1DisposalCheck.calcI1DisposalGainLoss"),
            ("从 I1-2 带入减少行", "筛选 I1-2 有本期减少的行带入", "取数",
             "处置检查明细带入（seedI1DisposalFromDetail）", "useI1DisposalCheck.seedI1DisposalFromDetail"),
        ],
        # I1-7 使用寿命检查
        "I1-7": [
            ("剩余年限", "原始寿命月数 ÷ 12 − 已用年限；不确定返回 null", "计算",
             "剩余摊销年限（calcRemainingYears）", "useI1UsefulLifeCheck.calcRemainingYears"),
            ("使用寿命不确定判定", "isIndefinite='Y' ∨ 使用寿命月数=0 → 不确定", "logic_check",
             "不确定寿命无形资产识别（isIndefiniteRow）", "useI1UsefulLifeCheck.isIndefiniteRow"),
            ("不确定清单联动 I1-12", "发布不确定寿命清单供减值测试取数", "取数",
             "不确定寿命→年度减值测试（publishIndefiniteList）", "useI1UsefulLifeCheck.publishIndefiniteList"),
            ("从 I1-2 带入", "带入名称/使用寿命月/账面净值", "取数",
             "使用寿命检查明细带入（seedFromDetail）", "useI1UsefulLifeCheck.seedFromDetail"),
        ],
        # I1-8 权属检查
        "I1-8": [
            ("账面净值", "原值 − 累计摊销 − 减值准备", "计算",
             "权证记载 vs 财务账面净值（calcI1TitleNetBook）", "useI1TitleCheck.calcI1TitleNetBook"),
            ("到期预警", "无日期→none；已过期→expired；≤365 天→near；否则 ok", "logic_check",
             "权利到期预警（classifyI1TitleExpiry）", "useI1TitleCheck.classifyI1TitleExpiry"),
            ("从 I1-2 带入账面", "带入原值/累计摊销/减值准备/净值", "取数",
             "权属检查账面带入（seedI1TitleFromDetail）", "useI1TitleCheck.seedI1TitleFromDetail"),
        ],
        # I1-9 摊销分配
        "I1-9": [
            ("分配合计", "生产成本 + 管理费用 + 销售费用 + 制造费用 + 研发费用 + 其他", "计算",
             "各资产摊销费用分配合计（calcI1RowAllocSum）", "useI1AmortizationAlloc.calcI1RowAllocSum"),
            ("分配平衡校验", "|分配合计 − 摊销总额| < 容差", "logic_check",
             "分配额与摊销总额勾稽（isI1RowBalanced）", "useI1AmortizationAlloc.isI1RowBalanced"),
            ("分配余额", "摊销总额 − 分配合计", "计算",
             "未分配余额（calcI1RowRemainder）", "useI1AmortizationAlloc.calcI1RowRemainder"),
            ("按资产从 I1-10/11 带入摊销额", "从摊销测算按资产名聚合本期摊销合计", "取数",
             "供分配表摊销总额（amortizationForAlloc.byAsset）", "useI1CrossSheet.amortizationForAlloc"),
        ],
        # I1-10 摊销测算（直线法，不含减值）
        "I1-10": [
            ("月摊销额（直线法）", "(原值 − 残值) ÷ 使用寿命月数", "计算",
             "直线法月摊销，寿命≤0 返回 0（calcStraightLineAmort）", "useI1AmortizationEngine.calcStraightLineAmort"),
            ("剩余年限法月摊销", "(原值 − 残值 − 累计摊销) ÷ 剩余月数", "计算",
             "变更后剩余年限法（calcRemainingLifeAmort）", "useI1AmortizationEngine.calcRemainingLifeAmort"),
            ("摊销到期日", "开始日 + 使用寿命月数", "计算",
             "对齐源表摊销到期日（calcFullAmortDate）", "useI1AmortizationEngine.calcFullAmortDate"),
        ],
        # I1-11 摊销测算（含减值）
        "I1-11": [
            ("减值后月摊销额", "(原值 − 残值 − 累计摊销 − 减值准备) ÷ 剩余月数", "计算",
             "减值后剩余年限法摊销（calcAmortWithImpairment）", "useI1AmortizationEngine.calcAmortWithImpairment"),
        ],
        # I1-12 减值准备测试
        "I1-12": [
            ("账面价值②", "原值 − 累计摊销", "计算",
             "减值测试账面价值（recomputeI1ImpairmentRow）", "useI1Impairment"),
            ("可收回金额⑤", "MAX(公允价值净额③, DCF现值④)", "计算",
             "可收回金额取大（calcRecoverableAmount）", "useI1AmortizationEngine.calcRecoverableAmount"),
            ("应计提减值⑥", "MAX(账面价值② − 可收回金额⑤, 0)", "计算",
             "减值金额夹紧 [0, 账面]（calcImpairmentAmount）", "useI1AmortizationEngine.calcImpairmentAmount"),
            ("本期补提⑧", "MAX(应计提⑥ − 已入账⑦, 0)", "计算",
             "本期补提减值（CAS8 不得转回，⑨仅待查）", "useI1Impairment"),
            ("从 I1-2 带入账面②", "带入原值/累计摊销", "取数",
             "减值测试账面带入（seedFromDetail）", "useI1Impairment.seedFromDetail"),
        ],
        # I1-13 可收回金额（DCF）
        "I1-13": [
            ("DCF 现值", "Σ 预测期现金流 ÷ (1+折现率)^t", "计算",
             "折现率≤0 返回 0（calcDcfPresentValue）", "useI1AmortizationEngine.calcDcfPresentValue"),
            ("终值（Gordon 模型）", "永续现金流 ÷ (折现率 − 增长率)", "计算",
             "折现率≤增长率 返回 0（calcTerminalValue）", "useI1AmortizationEngine.calcTerminalValue"),
            ("可收回金额", "MAX(公允价值净额, 使用价值DCF)", "计算",
             "回写 I1-12 ③④⑤（calcRecoverableAmount）", "useI1AmortizationEngine.calcRecoverableAmount"),
        ],
        # 附注披露
        "附注上市": [
            ("附注变动表金额", "取自 I1-2 明细按分类聚合的原值/摊销/减值变动", "取数",
             "上市附注按分类取数（pullFromSources）", "useI1ListedDisclosure.pullFromSources"),
            ("摊销分配披露", "取自 I1-9 按费用科目分配汇总", "取数",
             "附注摊销分配取数（aggregateI19AmortAlloc）", "useI1ListedDisclosure"),
            ("附注 ↔ I1-1 审定交叉校验", "附注变动表期末 − I1-1 审定数", "logic_check",
             "附注与审定表勾稽（buildI1ListedCrossCheck）", "useI1ListedDisclosure.crossCheck"),
        ],
        "附注国企": [
            ("附注五层变动表金额", "取自 I1-2 明细/I1-1 审定聚合（原值/摊销/减值/净值）", "取数",
             "国企附注取数（recomputeI1SoeDerivedLayers）", "useI1SoeDisclosure"),
            ("附注 ↔ I1-1 审定交叉校验", "附注期末 − I1-1 审定数", "logic_check",
             "附注与审定表勾稽（buildI1SoeCrossCheck）", "useI1SoeDisclosure.crossCheck"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # I2 开发支出（资产借方 1717）
    #   CAS6 五条件资本化 + I6↔I2 双向联动 + I2→I1 转入 + 减值DCF + 截止
    # ═══════════════════════════════════════════════════════════════════════
    "I2": {
        # I2-1 审定表
        "I2-1": [
            ("审定数", "未审数 + 账项调整(AJE) + 重分类调整(RJE)", "计算",
             "期初/期末各行审定金额（recalcI2AdjudicationRow）", "useI2Adjudication"),
            ("期末余额", "期初审定 + 本期增加(资本化) − 本期减少(转无形+转费用)", "计算",
             "资产类借方科目期末余额（calcAssetEndBalance）", "useI2FormulaEngine.calcAssetEndBalance"),
            ("合计", "Σ 各项目行", "计算",
             "审定表合计（summarizeI2Adjudication）", "useI2Adjudication.summary"),
            ("从 I2-2 明细带入", "按项目名聚合期初未审/期末未审/增加/减少", "取数",
             "审定表明细带入（seedAdjudicationFromI22）", "useI2Adjudication.seedFromDetail"),
            ("从 I2-3 同步 AJE/RJE", "按项目名精确匹配，剩余按期末未审占比分摊", "取数",
             "调整分录同步至审定表（applyAjeFromI23）", "useI2Adjudication.syncAjeFromI23"),
            ("试算平衡表数核对", "期末审定合计 − 试算平衡表数(1717)", "logic_check",
             "审定合计与 TB 开发支出(1717)核对（tbDiff）", "useI2Adjudication.tbDiff"),
            ("期末余额 ↔ I2-2 明细交叉验证", "审定表期末余额合计 − I2-2 资本化期末合计", "logic_check",
             "审定表↔明细勾稽（detailTotals.capitalized）", "useI2CrossSheet.detailTotals"),
            ("试算表1717期末余额(TB核对)", "TB('1717','期末余额')", "取数", "审定表TB↔审定核对标量", "Tier A"),
        ],
        # I2-2 明细表
        "I2-2": [
            ("投入合计", "材料投入 + 人工投入 + 折旧投入 + 其他投入", "计算",
             "本期研发投入合计", "useI2Detail"),
            ("资本化期末", "资本化期初 + 本期资本化增加 − 本期资本化减少", "计算",
             "资本化金额期末（calcAssetEndBalance）", "useI2FormulaEngine.calcAssetEndBalance"),
            ("资本化金额期末合计", "Σ 各行 capitalizedEnd", "计算",
             "供 I2-1 审定表交叉验证（detailTotals.capitalized）", "useI2CrossSheet.detailTotals"),
            ("转入无形资产合计", "Σ 各行 transferToIntangible", "计算",
             "供 I2→I1 转入联动（detailTotals.transferred）", "useI2CrossSheet.detailTotals"),
        ],
        # I2-3 调整分录
        "I2-3": [
            ("借贷平衡校验", "Σ 借方合计 = Σ 贷方合计（容差 1e-6）", "logic_check",
             "调整分录借贷平衡（calcDebitCreditBalance）", "useI2FormulaEngine.calcDebitCreditBalance"),
        ],
        # I2-4 会计政策检查
        "I2-4": [
            ("政策合规检查", "CAS 段落 + 询问 + 流程 + 同行对标 + 合理性判断", "logic_check",
             "会计政策五维检查（casItems/reasonableness）", "useI2PolicyCheck"),
            ("从 I2-7 带入项目名", "带入 I2-7 研发项目名称", "取数",
             "检查项目清单带入（syncProjectsFromI27）", "useI2PolicyCheck.syncProjectsFromI27"),
            ("政策不符生成 I2-3 调整草稿", "政策不符项 → 生成账项调整草稿", "取数",
             "一键生成政策调整至 I2-3", "useI2PolicyCheck"),
        ],
        # I2-5 实质性分析
        "I2-5": [
            ("构成分析/波动分析", "本期 vs 上期构成占比与波动", "计算",
             "实质性分析（构成/同行/人均）", "useI2Analysis"),
            ("变动率", "(本期 − 上期) ÷ 上期", "计算",
             "开发支出项目波动（calcChangeRate）", "useI2FormulaEngine.calcChangeRate"),
        ],
        # I2-6 资本化时点判断（CAS6 五条件）
        "I2-6": [
            ("CAS6 五条件资本化判定", "五条件(技术可行性/完成意图/使用出售方式/经济利益/支出可计量)同时为「是」→可资本化", "logic_check",
             "CAS6 第9条同时满足判定（evaluateCapitalization）", "useI2CapitalizationEngine.evaluateCapitalization"),
            ("研究/开发阶段划分闸门", "资本化时点须五条件满足且已填时点", "logic_check",
             "资本化闸门/勾稽/时点校验（validateI26CapTiming）", "useI2Capitalization"),
            ("回写 I2-2 资本化起点", "五条件满足→按同名项目回写 I2-2 资本化起点日期", "取数",
             "资本化时点联动明细（linkCapDateToDetail）", "useI2Capitalization.linkCapDateToDetail"),
        ],
        # I2-7 研发项目构成明细
        "I2-7": [
            ("项目滚动勾稽", "期初 + 本期增加 − 本期减少 = 期末（资本化/费用化各项）", "计算",
             "项目滚动勾稽（serializeI2ProjectDetailRow）", "useI2ProjectDetail"),
            ("与 I2-2 交叉验证", "I2-7 本期资本化增加合计 − I2-2 totalInvestment", "logic_check",
             "项目明细↔资本化明细勾稽（crossValidateI22Diff）", "useI2ProjectDetail.crossValidateI22Diff"),
        ],
        # I2-8 研发材料投入检查
        "I2-8": [
            ("检查比例", "检查合计(样本) ÷ 本期发生额(总体)", "计算",
             "材料投入检查覆盖率（sampleMeta）", "useI2MaterialCheck"),
            ("从 I2-7 带入材料费总体", "取 I2-7 材料费合计作检查总体", "取数",
             "材料检查总体带入", "useI2MaterialCheck"),
        ],
        # I2-11 委外研发检查
        "I2-11": [
            ("检查比例", "检查合计(样本) ÷ 委外总体", "计算",
             "委外研发检查覆盖率（sampleMeta）", "useI2OutsourceCheck"),
            ("从 I2-7 带入委外总体", "取 I2-7 委外金额合计作检查总体", "取数",
             "委外检查总体带入（extractI27OutsourceTotal）", "useI2OutsourceCheck.linkedOutsourceTotal"),
        ],
        # I2-12 针对性检查
        "I2-12": [
            ("检查比例", "检查合计(样本) ÷ 本期资本化增加(总体) × 100", "计算",
             "针对性检查覆盖率（linkedCapTotal）", "useI2TargetedCheck.linkedCapTotal"),
            ("从 I2-2 带入总体", "取 I2-2 本期资本化增加合计作检查总体", "取数",
             "总体金额带入（syncPopulationFromI22）", "useI2TargetedCheck.syncPopulationFromI22"),
        ],
        # I2-13 截止测试（账→单据）
        "I2-13": [
            ("会计跨期判定", "单据日与记账日分居资产负债表日两侧 → 跨期", "logic_check",
             "开发支出截止跨期判定（isCutoffPeriodCrossing）", "useI2FormulaEngine.isCutoffPeriodCrossing"),
            ("跨期金额", "跨期时取单据金额或记账金额，否则 0", "计算",
             "跨期错报金额（calcCrossPeriodAmount）", "useI2FormulaEngine.calcCrossPeriodAmount"),
            ("跨期天数", "|记账日 − 单据日|", "计算",
             "截止测试日期差（calcDateDiffDays）", "useI2FormulaEngine.calcDateDiffDays"),
        ],
        # I2-14 截止测试（单据→账）
        "I2-14": [
            ("会计跨期判定", "单据日与记账日分居资产负债表日两侧 → 跨期", "logic_check",
             "开发支出截止跨期判定（isCutoffPeriodCrossing）", "useI2FormulaEngine.isCutoffPeriodCrossing"),
            ("跨期金额", "跨期时取单据金额或记账金额，否则 0", "计算",
             "跨期错报金额（calcCrossPeriodAmount）", "useI2FormulaEngine.calcCrossPeriodAmount"),
        ],
        # I2-15 减值准备测试
        "I2-15": [
            ("账面价值②", "从 I2-2 带入原值", "取数",
             "减值测试账面（seedFromDetail）", "useI2Impairment.seedFromDetail"),
            ("可收回金额⑤", "MAX(公允价值净额③, DCF现值④)", "计算",
             "可收回金额取大（recomputeI2ImpairmentRow）", "useI2Impairment"),
            ("应计提减值⑥", "MAX(账面② − 可收回⑤, 0)", "计算",
             "减值金额有效性 ∈ [0, 账面]（calcImpairmentValid）", "useI2FormulaEngine.calcImpairmentValid"),
            ("本期补提⑧", "应计提⑥ − 已入账⑦", "计算",
             "推送本期补提至 K11 资产减值损失汇总（publishImpairmentToParent）", "useI2Impairment.publishImpairmentToParent"),
        ],
        # I2-16 可收回金额（DCF）
        "I2-16": [
            ("DCF 现值", "Σ 预测期现金流 ÷ (1+折现率)^t", "计算",
             "折现率≤0 返回 0（复用 I1-13/CAS8）", "useI2Impairment"),
            ("可收回金额", "MAX(公允价值净额, 使用价值DCF)", "计算",
             "回填 I2-15 ③④⑤（linkRecoverableToImpairment）", "useI2Impairment.linkRecoverableToImpairment"),
        ],
        # 附注披露
        "附注上市": [
            ("附注按性质披露", "取自审定/项目明细按性质聚合（内部开发/外购等）", "取数",
             "上市附注性质表取数（seedNatureCapitalizedFromI27）", "useI2Disclosure.autoFillFromSources"),
            ("附注项目滚动披露", "取自 I2-2 明细期初/增加/减少/期末", "取数",
             "上市附注滚动表取数（seedMovementFromI22 + enrichFromI26）", "useI2Disclosure.autoFillFromSources"),
            ("性质表资本化 ↔ 滚动内部开发校验", "性质表资本化合计 − 滚动表内部开发增加", "logic_check",
             "两表勾稽（natureVsMovementDiff）", "useI2Disclosure.natureVsMovementDiff"),
        ],
        "附注国企": [
            ("附注项目滚动披露", "取自 I2-2 明细/I2-7 项目滚动", "取数",
             "国企附注滚动表取数（seedMovementFromI22）", "useI2Disclosure.autoFillFromSources"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # I3 商誉（资产借方 1711；**不摊销**，仅年度减值测试；CAS8 两步法分摊）
    # ═══════════════════════════════════════════════════════════════════════
    "I3": {
        # I3-1 审定表
        "I3-1": [
            ("审定数", "未审数 + 账项调整(AJE) + 重分类调整(RJE)", "计算",
             "各被投资单位审定金额（recalcI3AdjudicationRow）", "useI3Adjudication.subtotals"),
            ("商誉期末余额", "期初 + 本期增加(新并购) − 本期减少(减值)", "计算",
             "**商誉不摊销**，只减不增（calcGoodwillEndBalance）", "useI3FormulaEngine.calcGoodwillEndBalance"),
            ("商誉净值", "原值(初始确认) − 累计减值准备", "计算",
             "商誉无累计摊销（calcGoodwillNetValue）", "useI3FormulaEngine.calcGoodwillNetValue"),
            ("从 I3-2 带入", "按被投资单位带入原值/减值/净值滚动", "取数",
             "审定表明细带入（seedI3AdjudicationFromDetail）", "useI3Adjudication.seedFromI32"),
            ("从 I3-3 同步 AJE/RJE", "按被投资单位精确匹配，剩余比例分摊", "取数",
             "调整分录同步（applyAjeFromI33）", "useI3Adjudication.syncFromI33"),
            ("从 I3-6 同步本期减值", "取合并确认商誉减值(母公司份额)", "取数",
             "减值测试同步（applyI3ImpairmentFromTest）", "useI3Adjudication.syncImpairmentFromI36"),
            ("减值不可转回校验", "本期减少(减值) ≥ 0", "logic_check",
             "商誉减值不可转回，负数即报错（warnings.impairmentReversal）", "useI3Adjudication.warnings"),
            ("期末余额 ↔ 净额校验", "|期末余额 − 净额| ≤ 0.01", "logic_check",
             "期末与净额一致性（warnings.endVsNet）", "useI3Adjudication.warnings"),
            ("试算平衡表数核对", "审定合计 − 试算平衡表数(1711)", "logic_check",
             "审定合计与 TB 商誉(1711)核对（tbDiff）", "useI3Adjudication.tbDiff"),
            ("审定表 ↔ I3-2 明细交叉验证", "审定原值/减值/净值 − I3-2 明细合计", "logic_check",
             "审定表↔明细勾稽（buildI3AdjudicationCrossCheck）", "useI3Adjudication.crossCheck"),
            ("试算表1711期末余额(TB核对)", "TB('1711','期末余额')", "取数", "审定表TB↔审定核对标量，不摊销仅减值", "Tier A"),
        ],
        # I3-2 明细表
        "I3-2": [
            ("商誉原值期末合计", "Σ 各行 costAudited/goodwillOriginal", "计算",
             "科目 1711 原值聚合（detailTotals.goodwillOriginalTotal）", "useI3CrossSheet.detailTotals"),
            ("累计减值合计", "Σ 各行 impAudited/accImpairmentEnd", "计算",
             "累计减值准备聚合（detailTotals.accImpairmentTotal）", "useI3CrossSheet.detailTotals"),
            ("净值合计", "原值合计 − 累计减值合计", "计算",
             "商誉净值聚合（detailTotals.netValueTotal）", "useI3CrossSheet.detailTotals"),
            ("入账测算差异", "I3-4 入账测算商誉 − I3-2 原值/增加", "logic_check",
             "初始商誉入账勾稽（entryVariances）", "useI3CrossSheet.entryVariances"),
            ("账项调整 ↔ I3-3 差异", "I3-2 明细账项调整列 − I3-3 商誉科目汇总", "logic_check",
             "明细调整列与调整分录勾稽（ajeVariances）", "useI3CrossSheet.ajeVariances"),
        ],
        # I3-3 调整分录
        "I3-3": [
            ("借贷平衡校验", "Σ 借方金额 = Σ 贷方金额", "logic_check",
             "调整分录借贷平衡", "useI3Adjustment"),
            ("按被投资单位汇总商誉 AJE/RJE", "按 1711 科目汇总净额(借−贷)，按被投资单位拆分", "取数",
             "回写 I3-1/I3-2（aggregateGoodwillAjeByInvestee）", "useI3CrossSheet.adjustmentSync"),
        ],
        # I3-4 入账测算
        "I3-4": [
            ("初始商誉", "合并成本 − 被购方可辨认净资产公允价值份额", "计算",
             "CAS20 非同一控制下合并商誉（calcInitialGoodwill）", "useI3FormulaEngine.calcInitialGoodwill"),
        ],
        # I3-5 针对性检查
        "I3-5": [
            ("检查比例", "检查合计(样本) ÷ 本期发生额(总体)", "计算",
             "针对性检查覆盖率（sampleMeta，可联动 I3-2）", "useI3TargetedCheck"),
        ],
        # I3-6 减值测试
        "I3-6": [
            ("减值分摊（CAS8 两步法）", "Step1 先冲商誉至0；Step2 剩余按资产组其他资产账面比例分摊", "计算",
             "减值分摊，其他资产分摊≤账面且不低于可收回金额（calcImpairmentAllocation）", "useI3FormulaEngine.calcImpairmentAllocation"),
            ("其他资产分摊上限", "MAX(0, 账面价值 − 可收回金额)", "计算",
             "CAS8 §23 抵减后不低于可收回金额（calcAssetAllocCap）", "useI3FormulaEngine.calcAssetAllocCap"),
            ("合并确认商誉减值", "按 CGU 取母公司份额商誉减值", "计算",
             "供 I3-1/I3-2 本期减值（impairmentResult.consolidatedGwImpairment）", "useI3CrossSheet.impairmentResult"),
            ("从 I3-7 取可收回金额", "按 CGU 取公允净额/使用价值/可收回金额", "取数",
             "减值测试取可收回金额（recoverableByCgu）", "useI3CrossSheet.recoverableByCgu"),
        ],
        # I3-7 可收回金额（DCF）
        "I3-7": [
            ("DCF 现值", "Σ 现金流 ÷ (1+折现率)^t", "计算",
             "折现率≤0 或空数组返回 0（calcDcfPresentValue）", "useI3DcfEngine.calcDcfPresentValue"),
            ("终值（Gordon 模型）", "FCF × (1+增长率) ÷ (折现率 − 增长率)", "计算",
             "折现率≤增长率 返回 0（calcTerminalValue）", "useI3DcfEngine.calcTerminalValue"),
            ("WACC", "权益成本×权益比例 + 债务成本×债务比例×(1−税率)", "计算",
             "加权平均资本成本（calcWacc）", "useI3DcfEngine.calcWacc"),
            ("可收回金额", "MAX(公允价值净额, 使用价值)", "计算",
             "可收回金额取大（calcRecoverableAmount）", "useI3DcfEngine.calcRecoverableAmount"),
            ("敏感性分析", "折现率±1% / 增长率±0.5% 调整后现值", "计算",
             "敏感性测算（calcSensitivity）", "useI3DcfEngine.calcSensitivity"),
        ],
        # 附注披露
        "附注上市": [
            ("附注商誉账面价值/减值", "取自 I3-2 明细/I3-1 审定按被投资单位滚动", "取数",
             "上市附注取数（pullFromDetailRows / disclosureAutoFill）", "useI3Disclosure / useI3CrossSheet.disclosureAutoFill"),
            ("CGU 分摊披露", "按资产组聚合期末净额/原值", "取数",
             "附注 CGU 分摊取数（pullFromDetailRows）", "useI3Disclosure.pullFromDetailRows"),
            ("附注 ↔ I3-1 审定交叉校验", "附注原值/减值/净额期末 − I3-1 审定数", "logic_check",
             "附注与审定表勾稽（bookValueTotal/impairmentTotal/netValueTotal）", "useI3Disclosure"),
        ],
        "附注国企": [
            ("附注商誉账面价值/减值", "取自 I3-2 明细/I3-1 审定滚动", "取数",
             "国企附注取数（pullFromDetailRows / disclosureAutoFill）", "useI3Disclosure / useI3CrossSheet.disclosureAutoFill"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # I4 长期待摊费用（资产借方 1801；期末=期初+增加-摊销-减少；直线/工作量法）
    # ═══════════════════════════════════════════════════════════════════════
    "I4": {
        # I4-1 审定表
        "I4-1": [
            ("审定数", "未审数 + 账项调整(AJE) + 重分类调整(RJE)", "计算",
             "各项目审定金额（recalcI4AdjudicationRow）", "useI4Adjudication.subtotals"),
            ("期末余额", "期初 + 本期增加 − 本期摊销 − 本期减少", "计算",
             "长期待摊费用期末余额（calcAssetEndBalance）", "useI4FormulaEngine.calcAssetEndBalance"),
            ("变动率", "(本期审定 − 上期审定) ÷ 上期审定", "计算",
             "本期较上期变动率（calcChangeRate）", "useI4FormulaEngine.calcChangeRate"),
            ("从 I4-2 带入", "按项目名带入期初/增加/摊销/减少/期末（保留 AJE/RJE）", "取数",
             "审定表明细带入（seedI4AdjudicationFromDetail）", "useI4Adjudication.seedFromI42"),
            ("从 I4-3 同步 AJE/RJE", "按项目名精确匹配，剩余按占比分摊", "取数",
             "调整分录同步（applyAjeFromI43）", "useI4Adjudication.syncFromI43"),
            ("从 I4-6/I4-7 同步本期摊销", "取直线法/工作量法 12 月摊销矩阵合计", "取数",
             "摊销测算同步至审定表本期摊销（applyAmortFromI46）", "useI4Adjudication.syncAmortFromI46"),
            ("三角勾稽校验", "期末 − (期初 + 增加 − 摊销 − 减少) = 0", "logic_check",
             "长期待摊费用勾稽平衡（calcTriangleReconciliation）", "useI4FormulaEngine.calcTriangleReconciliation"),
            ("试算平衡表数核对", "审定合计 − 试算平衡表数(1801)", "logic_check",
             "审定合计与 TB 长期待摊费用(1801)核对（tbDifference）", "useI4Adjudication.tbDifference"),
            ("审定表 ↔ I4-2 明细交叉验证", "审定期末合计 − I4-2 明细期末余额合计", "logic_check",
             "审定表↔明细勾稽（buildI4AdjudicationCrossCheck）", "useI4Adjudication.crossCheck"),
            ("试算表1801期末余额(TB核对)", "TB('1801','期末余额')", "取数", "审定表TB↔审定核对标量", "Tier A"),
        ],
        # I4-2 明细表
        "I4-2": [
            ("期末余额合计", "Σ 各行期末余额", "计算",
             "供 I4-1 审定表交叉验证（detailTotals.endBalance）", "useI4CrossSheet.detailTotals"),
            ("本期摊销合计", "Σ 各行本期摊销", "计算",
             "明细本期摊销聚合（detailTotals.amortization）", "useI4CrossSheet.detailTotals"),
        ],
        # I4-3 调整分录
        "I4-3": [
            ("借贷平衡校验", "Σ 借方金额 = Σ 贷方金额", "logic_check",
             "调整分录借贷平衡", "useI4Adjustment"),
            ("按项目汇总 AJE/RJE 回写审定表", "账项调整→AJE / 报表调整→RJE，按项目名匹配", "取数",
             "回写 I4-1 审定表（applyAjeFromI43）", "useI4Adjudication.syncFromI43"),
        ],
        # I4-4 摊销政策检查
        "I4-4": [
            ("摊销政策五维判断", "五维判断均「是」→政策适当；任一「否」→需关注", "logic_check",
             "长期待摊费用摊销政策检查（casItems）", "useI4PolicyCheck"),
            ("同行业政策对标", "本单位政策 vs 同行业对标公司", "logic_check",
             "对标公司政策比较（peer companies）", "useI4PolicyCheck"),
        ],
        # I4-5 针对性检查
        "I4-5": [
            ("检查比例", "检查合计(样本) ÷ 本期发生额(总体)", "计算",
             "针对性检查覆盖率（可联动 I4-2）", "useI4TargetedCheck"),
        ],
        # I4-6 摊销测算（直线法）
        "I4-6": [
            ("12 月摊销矩阵", "各项目按直线法生成 12 月摊销额", "计算",
             "直线法月摊销矩阵（amortizationMatrix）", "useI4CrossSheet.amortizationMatrix"),
        ],
        # I4-7 摊销测算（工作量法）
        "I4-7": [
            ("12 月摊销矩阵", "各项目按工作量法生成 12 月摊销额（年度合计均分或按工作量）", "计算",
             "工作量法月摊销矩阵（amortizationMatrix）", "useI4CrossSheet.amortizationMatrix"),
        ],
        # 附注披露
        "附注上市": [
            ("附注变动表金额", "取自 I4-2 明细期初/增加/摊销/减少/期末", "取数",
             "上市附注取数（aggregateI4DetailForDisclosure）", "useI4Disclosure"),
            ("附注期末余额", "期初 + 增加 − 摊销 − 其他减少", "计算",
             "附注变动表期末（calcI4DisclosureEnd）", "useI4Disclosure"),
            ("一年内摊销额", "取本期摊销一年内部分", "取数",
             "流动性拆分（calcI4CurrentPortion）", "useI4Disclosure"),
        ],
        "附注国企": [
            ("附注变动表金额", "取自 I4-2 明细期初/增加/摊销/减少/期末", "取数",
             "国企附注取数（aggregateI4DetailForDisclosure）", "useI4Disclosure"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # I5 其他非流动资产（资产借方 1911；标准资产类 期末=期初+增加-减少）
    #   明细对齐 Excel 原值/减值/净值三层
    # ═══════════════════════════════════════════════════════════════════════
    "I5": {
        # I5-1 审定表
        "I5-1": [
            ("审定数", "未审数 + 账项调整(AJE) + 重分类调整(RJE)", "计算",
             "各项目审定金额（recalcI5AdjudicationRow）", "useI5Adjudication.subtotals"),
            ("期末余额", "期初 + 本期增加 − 本期减少", "计算",
             "其他非流动资产期末余额（calcAssetEndBalance）", "useI5FormulaEngine.calcAssetEndBalance"),
            ("变动率", "(本期审定 − 上期审定) ÷ 上期审定", "计算",
             "本期较上期变动率（calcChangeRate）", "useI5FormulaEngine.calcChangeRate"),
            ("从 I5-2 带入", "按项目名带入期初/增加/减少/期末（保留 AJE/RJE）", "取数",
             "审定表明细带入（seedI5AdjudicationFromDetail）", "useI5Adjudication.seedFromI52"),
            ("从 I5-3 同步 AJE/RJE", "按项目名精确匹配，剩余按占比分摊", "取数",
             "调整分录同步（applyAjeFromI53）", "useI5Adjudication.syncFromI53"),
            ("三层矩阵净值（原值/减值/净值）", "净值 = 原值审定 − 减值审定", "计算",
             "有 I5-2 嵌套原值/减值时展示三层矩阵（buildI5ThreeLayerLeadFromDetail）", "useI5Adjudication.threeLayerLeadRows"),
            ("三角勾稽校验", "(期初 + 增加 − 减少) − 期末 = 0", "logic_check",
             "其他非流动资产勾稽平衡（calcTriangleReconciliation）", "useI5FormulaEngine.calcTriangleReconciliation"),
            ("试算平衡表数核对", "审定合计 − 试算平衡表数(1911)", "logic_check",
             "审定合计与 TB 其他非流动资产(1911)核对（tbDifference）", "useI5Adjudication.tbDifference"),
            ("审定表 ↔ I5-2 明细交叉验证", "审定期末合计 − I5-2 明细净值期末合计", "logic_check",
             "审定表↔明细勾稽（buildI5AdjudicationCrossCheck）", "useI5Adjudication.crossCheck"),
            ("试算表1911期末余额(TB核对)", "TB('1911','期末余额')", "取数", "审定表TB↔审定核对标量", "Tier A"),
        ],
        # I5-2 明细表
        "I5-2": [
            ("净值期末合计", "Σ 各行(原值期末审定 − 减值期末审定)", "计算",
             "供 I5-1 审定表交叉验证（detailTotals.endBalance）", "useI5CrossSheet.detailTotals"),
            ("期初/增加/减少合计", "Σ 各行原值−减值 各列", "计算",
             "明细滚动聚合（detailTotals）", "useI5CrossSheet.detailTotals"),
        ],
        # I5-3 调整分录
        "I5-3": [
            ("借贷平衡校验", "Σ 借方金额 = Σ 贷方金额", "logic_check",
             "调整分录借贷平衡", "useI5Adjustment"),
            ("按项目汇总 AJE/RJE 回写审定表", "账项调整→AJE / 报表调整→RJE，按项目名匹配", "取数",
             "回写 I5-1 审定表（applyAjeFromI53）", "useI5Adjudication.syncFromI53"),
        ],
        # I5-4 针对性检查
        "I5-4": [
            ("检查比例", "检查合计(样本) ÷ 本期发生额(总体)", "计算",
             "针对性检查覆盖率（可联动 I5-2）", "useI5TargetedCheck"),
        ],
        # 附注披露
        "附注上市": [
            ("附注披露金额", "取自 I5-2 明细/I5-1 审定聚合（主要构成/重大项目/受限）", "取数",
             "上市附注取数（aggregateI5DetailForDisclosure）", "useI5Disclosure"),
        ],
        "附注国企": [
            ("附注披露金额", "取自 I5-2 明细/I5-1 审定聚合", "取数",
             "国企附注取数（aggregateI5DetailForDisclosure）", "useI5Disclosure"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # I6 研发费用（**损益类借方 6602**；取发生额非余额；净发生额=借方−贷方）
    #   月度12列明细 + VR-I6-01(费用化+资本化=研发总额) + 截止
    # ═══════════════════════════════════════════════════════════════════════
    "I6": {
        # I6-1 审定表（27行×11列，上期/本期各 未审/AJE/RJE/审定）
        "I6-1": [
            ("上期审定(E)", "上期未审(B) + 上期AJE(C) + 上期RJE(D)", "计算",
             "上期审定发生额（calcAuditedAmount）", "useI6FormulaEngine.calcAuditedAmount"),
            ("本期审定(I)", "本期未审(F) + 本期AJE(G) + 本期RJE(H)", "计算",
             "本期审定发生额（calcAuditedAmount）", "useI6FormulaEngine.calcAuditedAmount"),
            ("变动额(J)", "本期审定(I) − 上期审定(E)", "计算",
             "本期较上期变动额", "useI6Adjudication.computedRows"),
            ("变动率(K)", "IF(E=0∧J=0→0; E=0∧J>0→1; 否则→J/E)", "计算",
             "特殊变动率规则；|变动率|>30% 高亮（calcI6ChangeRate）", "useI6Adjudication"),
            ("合计行", "各列 Σ 明细行", "计算",
             "27 行合计（calcSubtotal）", "useI6FormulaEngine.calcSubtotal / useI6Adjudication.totalRow"),
            ("从 I6-2 明细按类别聚合", "按费用类别聚合月度合计→本期未审", "取数",
             "审定表从明细带入（syncFromDetail）", "useI6Adjudication.syncFromDetail"),
            ("从 I6-3 同步 AJE/RJE", "按 6602 汇总净额，按类别匹配写入本期 AJE/RJE", "取数",
             "调整分录同步（applyAjeFromI63）", "useI6Adjudication.syncFromI63"),
            ("VR-I6-01 校验", "费用化(I6本期审定) + 资本化(I2) = 研发总额（容差 0.01）", "logic_check",
             "研发投入拆分校验（validateVRI601）", "useI6FormulaEngine.validateVRI601"),
            ("试算平衡表数核对", "本期审定合计 − 试算平衡表数(6602 发生额)", "logic_check",
             "审定发生额与 TB 研发费用(6602)核对（tbDifference）", "useI6Adjudication.tbDifference"),
            ("审定表 ↔ I6-2 明细交叉验证", "本期审定合计 − I6-2 月度合计之和", "logic_check",
             "审定表↔明细月度勾稽（detailCrossValidation）", "useI6Adjudication.detailCrossValidation"),
            ("试算表6602审定发生额(TB核对)", "TB('6602','审定数')", "取数", "审定表TB↔审定核对标量，损益类借方", "Tier A"),
        ],
        # I6-2 明细表（月度12列横向）
        "I6-2": [
            ("年度合计", "Σ(1月 ~ 12月)", "计算",
             "各行月度横向汇总（calcMonthlyTotal）", "useI6FormulaEngine.calcMonthlyTotal"),
            ("月度合计（12列）", "各月列 Σ 所有行", "计算",
             "底部合计行，供审定表净发生额验证（detailMonthlyTotals）", "useI6CrossSheet.detailMonthlyTotals"),
            ("费用化金额合计", "Σ(12月合计)", "计算",
             "I6 费用化发生额，供 VR-I6-01（i6ExpenseAmount）", "useI6CrossSheet"),
        ],
        # I6-3 调整分录
        "I6-3": [
            ("借贷平衡校验", "Σ 借方合计 = Σ 贷方合计（容差 0.01）", "logic_check",
             "调整分录借贷平衡（calcDebitCreditBalance）", "useI6FormulaEngine.calcDebitCreditBalance"),
            ("按类别汇总 6602 净额回写审定表", "按 6602 汇总净额，按类别写入本期 AJE/RJE", "取数",
             "回写 I6-1 审定表（applyAjeFromI63）", "useI6Adjudication.syncFromI63"),
        ],
        # I6-4 针对性检查
        "I6-4": [
            ("检查比例", "检查合计(样本) ÷ 本期审定合计(总体)", "计算",
             "针对性检查覆盖率（可联动 I6-2 本期审定合计）", "useI6TargetedCheck"),
        ],
        # I6-5 截止测试（账→单据）
        "I6-5": [
            ("会计跨期判定", "单据日与记账日分居资产负债表日两侧 → 跨期", "logic_check",
             "研发费用截止跨期判定（isCutoffPeriodCrossing / isCutoffCrossover）", "useI6CrossSheet / useI6FormulaEngine.isCutoffCrossover"),
            ("截止样本聚合", "聚合 I6-5/I6-6 截止样本并标记跨期状态", "取数",
             "截止测试样本（cutoffSamples）", "useI6CrossSheet.cutoffSamples"),
        ],
        # I6-6 截止测试（单据→账）
        "I6-6": [
            ("会计跨期判定", "单据日与记账日分居资产负债表日两侧 → 跨期", "logic_check",
             "研发费用截止跨期判定（isCutoffPeriodCrossing）", "useI6CrossSheet"),
        ],
        # 附注披露
        "附注上市": [
            ("附注研发费用披露", "取自 I6-2 明细/I6-1 审定按类别聚合发生额", "取数",
             "上市附注取数（aggregateI6DetailForDisclosure / aggregateI6AdjForDisclosure）", "useI6Disclosure"),
            ("费用化 ↔ 资本化勾稽", "I6 费用化 + I2 资本化 = 研发总额", "logic_check",
             "研发投入构成披露勾稽（buildI6DisclosureReconcileView）", "useI6Disclosure"),
        ],
        "附注国企": [
            ("附注研发费用披露", "取自 I6-2 明细/I6-1 审定按类别聚合发生额", "取数",
             "国企附注取数（aggregateI6DetailForDisclosure）", "useI6Disclosure"),
        ],
    },
}
