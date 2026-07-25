"""M 循环（股东权益类）底稿公式 surfacing 目录（与各 useM{n}* composable 同源，不臆造）。

对齐 D 循环（wp_surfaced_d.py）与 E1 标准：把「专属组件底稿」（数据存
checklist_responses、无 wp_formula 网格记录）的取数/计算/逻辑审核公式以只读条目
surface 到公式管理中心，让每张 sheet 都能体现其取数逻辑。

每条公式均可在对应前端 composable 中找到依据（calc 函数 / 跨 sheet 键 / TB 回写 /
审定↔明细勾稽 / EventBus 权益循环联动）；找不到依据的 sheet 不写（宁缺勿造）。

分类只用三种：
  - 取数     跨 sheet / EventBus 联动带入 / 从明细带入
  - 计算     表间计算（审定=未审+AJE+RJE、期末余额、小计、变动额/率、计提测算、外币折算等）
  - logic_check  逻辑审核（TB 回写核对、审定↔明细勾稽、金额守恒、注销冲减平衡、行业适用性等）

─── 科目方向（以各 composable 的 ACCOUNT_CODE 常量核实，非臆造） ───
  M1  应付股利           2232  负债贷方       期末=期初+贷(宣告)−借(支付)
  M2  实收资本/股本       4001  权益贷方       期末=期初+贷(增资)−借(减资)
  M3  库存股             4002  权益备抵借方   期末=期初+借(回购)−贷(注销/再售)  ← 方向特殊，与其余 M 相反！
  M4  资本公积           4002  权益贷方       期末=期初+贷(增加)−借(减少)
  M5  盈余公积           4101  权益贷方       期末=期初+贷(计提)−借(转增/弥补)
  M6  利润分配-未分配利润 4104  权益贷方(枢纽) 期末=期初+贷(净利润转入)−借(分配)
  M7  专项储备           4201  权益贷方       期末=期初+贷(计提)−借(使用)
  M8  一般风险准备        4104  权益贷方(金融专属) 期末=期初+贷(计提)−借(转回/使用)
  M9  其他综合收益        4103  权益贷方       期末=期初+贷(OCI增加)−借(减少/重分类)
  M10 其他权益工具        4003  权益贷方       期末=期初+贷(发行)−借(赎回/转换)

注：M 循环各底稿的 composable 内容与其 ACCOUNT_CODE 注释完全一致，据此确定循环名称
（部分与旧映射不同，一律以 composable 为准）。审定数公式全 M 统一
（calcAuditedAmount：审定=未审+AJE+RJE）；审定表审定数变化 → writebackTB(科目)
+ EventBus 'substantive:adjudicated'（通知附注/检查表刷新）。
"""
from __future__ import annotations

SheetFormula = tuple[str, str, str, str, str]  # (项目名, 公式, 分类, 说明, 来源)

CATALOG: dict[str, dict[str, list[SheetFormula]]] = {
    # ═══════════════════════════════════════════════════════════════════════
    # M1 应付股利（负债贷方 2232；股利测算 + 外币 + M6 利润分配联动）
    # ═══════════════════════════════════════════════════════════════════════
    "M1": {
        # M1-1 审定表（按股东分类 + 小计）
        "M1-1": [
            ("审定数", "未审数 + 账项调整(AJE) + 重分类调整(RJE)", "计算",
             "各行审定金额（calcAuditedAmount，M 循环统一）", "useM1FormulaEngine"),
            ("期末余额", "期初 + 贷方发生(宣告增加) − 借方发生(支付减少)", "计算",
             "负债类贷方方向（calcLiabilityEndBalance）", "useM1FormulaEngine"),
            ("分类小计", "Σ 各股东行金额", "计算",
             "按股东分类合计 B13=SUM(B7:B12)（calcSubtotal）", "useM1FormulaEngine"),
            ("变动额", "期末审定数 − 期初审定数", "计算",
             "审定表 J 列 J7=I7-E7（calcVarianceAmount）", "useM1FormulaEngine"),
            ("变动率", "IF(期初=0∧变动=0,0; 期初=0∧变动>0,1; 变动额÷期初)", "计算",
             "审定表 K 列条件除法（calcVarianceRate）", "useM1FormulaEngine"),
            ("试算平衡表数核对", "审定期末合计 − 试算平衡表数(2232)", "logic_check",
             "审定数变化→writebackTB(2232)回写核对（saveAndWriteback）", "useM1Adjudication"),
            ("M1-1审定表 ↔ M1-2明细表勾稽", "M1-1 期末合计 − M1-2 明细各股东期末合计", "logic_check",
             "审定↔明细交叉验证（adjudicationVsDetail，容差 1 元）", "useM1CrossSheet"),
        ],
        # M1-2 明细表（按股东）
        "M1-2": [
            ("期末余额", "期初 + 贷方(宣告) − 借方(支付)", "计算",
             "按股东明细期末余额（calcLiabilityEndBalance）", "useM1FormulaEngine"),
            ("审定数", "未审数 + AJE + RJE", "计算",
             "各股东审定金额（calcAuditedAmount）", "useM1FormulaEngine"),
            ("明细合计", "Σ 各股东行", "计算",
             "明细表列小计（calcSubtotal）", "useM1FormulaEngine"),
        ],
        # M1-3 调整分录
        "M1-3": [
            ("借贷平衡校验", "Σ 借方金额 = Σ 贷方金额", "logic_check",
             "调整分录借贷平衡", "useM1Adjustment"),
            ("AJE/RJE 回写审定表", "账项调整→AJE / 重分类调整→RJE 汇总回写 M1-1", "取数",
             "监听 adjustment:created 回写审定数", "useM1Adjustment"),
        ],
        # M1-4 外币汇率测算表
        "M1-4": [
            ("折合人民币", "外币金额 × 汇率", "计算",
             "外币股利折算（calcFxConverted，E 列）", "useM1FxEngine"),
            ("汇兑差异", "折合人民币 − 账面金额", "计算",
             "折算与账面差异（calcFxDiff，G 列）", "useM1FxEngine"),
        ],
        # M1-5 应付股利（利润）测算表（接收 M6）
        "M1-5": [
            ("应宣告股利", "可供分配利润 × 分配比例", "计算",
             "股利分配额测算（calcDeclaredDividend，D 列）", "useM1DividendEngine"),
            ("宣告差异", "测算宣告 − 账面宣告", "计算",
             "测算与账面差异（calcDeclareDiff，F 列）", "useM1DividendEngine"),
            ("测算宣告 ↔ M6 分配股利一致性", "M1-5 测算宣告合计 − M6 利润分配-分配股利", "logic_check",
             "订阅 m6:profit-distributed 校验宣告准确性（declareVsM6，容差 100 元）",
             "useM1CrossSheet"),
        ],
        # M1-6 应付股利（利润）检查表
        "M1-6": [
            ("凭证级检查合计", "Σ 检查金额", "计算",
             "股利宣告/支付凭证检查合计（calcSubtotal）", "useM1DividendCheck"),
        ],
        # 附注披露
        "附注上市": [
            ("附注披露金额", "取自 M1-1 审定表各股东审定数", "取数",
             "附注取审定数，订阅 substantive:adjudicated 自动刷新", "useM1Adjudication"),
        ],
        "附注国企": [
            ("附注披露金额", "取自 M1-1 审定表各股东审定数", "取数",
             "附注取审定数，订阅 substantive:adjudicated 自动刷新", "useM1Adjudication"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # M2 实收资本/股本（权益贷方 4001；上市/非上市 + 外币出资 + 验资 + →M4联动）
    # ═══════════════════════════════════════════════════════════════════════
    "M2": {
        # M2-1 审定表（按出资人分类 + 小计）
        "M2-1": [
            ("审定数", "未审数 + 账项调整(AJE) + 重分类调整(RJE)", "计算",
             "各行审定金额（calcAuditedAmount）", "useM2FormulaEngine"),
            ("期末余额", "期初 + 贷方发生(增资) − 借方发生(减资)", "计算",
             "权益类贷方方向（calcEquityEndBalance）", "useM2FormulaEngine"),
            ("分类小计", "Σ 各出资人/股东行", "计算",
             "按出资人分类合计（calcSubtotal）", "useM2FormulaEngine"),
            ("变动额", "期末审定数 − 期初审定数", "计算",
             "审定表 J=I−E（calcVarianceAmount）", "useM2FormulaEngine"),
            ("变动率", "IF(期初=0∧变动=0,0; 期初=0∧变动>0,1; 变动额÷期初)", "计算",
             "审定表条件除法（calcVarianceRate）", "useM2FormulaEngine"),
            ("试算平衡表数核对", "审定期末合计 − 试算平衡表数(4001)", "logic_check",
             "审定数变化→writebackTB(4001)回写核对（saveAndWriteback）", "useM2Adjudication"),
            ("M2-1审定表 ↔ M2-2明细表勾稽", "M2-1 期末合计 − M2-2 明细各出资人期末合计", "logic_check",
             "审定↔明细交叉验证（adjudicationVsDetail，容差 1 元）", "useM2CrossSheet"),
        ],
        # M2-2 明细表（上市/非上市双版本）
        "M2-2": [
            ("期末余额", "期初 + 贷方(增资) − 借方(减资)", "计算",
             "上市 K=D+F−J / 非上市 T=P+R−S（calcEquityEndBalance）", "useM2FormulaEngine"),
            ("审定数", "未审数 + AJE + RJE", "计算",
             "各出资人审定金额（calcAuditedAmount）", "useM2FormulaEngine"),
            ("持股/出资比例", "个体出资(股数) ÷ 合计出资(股数)", "计算",
             "上市持股比例 / 非上市出资比例（calcShareRatio，0除法保护）", "useM2FormulaEngine"),
        ],
        # M2-3 调整分录
        "M2-3": [
            ("借贷平衡校验", "Σ 借方金额 = Σ 贷方金额", "logic_check",
             "调整分录借贷平衡", "useM2Adjustment"),
            ("AJE/RJE 回写审定表", "账项调整→AJE / 重分类调整→RJE 汇总回写 M2-1", "取数",
             "监听 adjustment:created 回写审定数", "useM2Adjustment"),
        ],
        # M2-4 外币投资汇率测算表
        "M2-4": [
            ("折算本位币金额", "外币出资 × 出资日汇率", "计算",
             "外币出资折算（calcFxConverted，E 列）", "useM2FxEngine"),
            ("外币折算差异", "折算本位币 − 账面金额", "计算",
             "折算与账面差异（calcFxDiff，G 列）", "useM2FxEngine"),
            ("外币折算差异 → M4 资本公积", "Σ 各出资人折算差异 > 阈值 → 提示计入 M4 资本溢价", "取数",
             "ADR-4 外币出资折算差异计入资本公积，发布 m2:fx-diff-to-m4（fxDiffToM4）",
             "useM2CrossSheet"),
        ],
        # M2-5 实收资本（股本）检查表（凭证级测试 + 验资）
        "M2-5": [
            ("验资差异", "实缴出资 − 验资报告金额", "计算",
             "实缴与验资核对（calcVerifyDiff）", "useM2VerifyEngine"),
            ("出资到位率", "实缴出资 ÷ 认缴出资", "计算",
             "出资到位率（calcPaidInRate，0除法保护）", "useM2VerifyEngine"),
        ],
        # 附注披露
        "附注上市": [
            ("附注披露金额", "取自 M2-1 审定表各出资人审定数", "取数",
             "附注取审定数，订阅 substantive:adjudicated 自动刷新（onAdjudicatedRefresh）",
             "useM2Adjudication"),
        ],
        "附注国企": [
            ("附注披露金额", "取自 M2-1 审定表各出资人审定数", "取数",
             "附注取审定数，订阅 substantive:adjudicated 自动刷新（onAdjudicatedRefresh）",
             "useM2Adjudication"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # M3 库存股（权益备抵借方 4002；方向特殊！回购/注销 + 注销冲减→M2/M4联动）
    # ═══════════════════════════════════════════════════════════════════════
    "M3": {
        # M3-1 审定表（按回购批次 + 小计）
        "M3-1": [
            ("审定数", "未审数 + 账项调整(AJE) + 重分类调整(RJE)", "计算",
             "各行审定金额（calcAuditedAmount）", "useM3FormulaEngine"),
            ("期末余额", "期初 + 借方发生(回购增加) − 贷方发生(注销/再售减少)", "计算",
             "权益备抵类借方方向，与其余 M 相反（calcContraEquityEndBalance）", "useM3FormulaEngine"),
            ("分类小计", "Σ 各回购批次行", "计算",
             "按回购批次分类合计（calcSubtotal）", "useM3FormulaEngine"),
            ("试算平衡表数核对", "审定期末合计 − 试算平衡表数(4002 库存股)", "logic_check",
             "审定数变化→writebackTB(4002)回写核对（saveAndWriteback）", "useM3Adjudication"),
            ("M3-1审定表 ↔ M3-2明细表勾稽", "M3-1 期末审定合计 − M3-2 各批次期末金额合计", "logic_check",
             "审定↔明细交叉验证（adjudicationVsDetail，容差 1 元）", "useM3CrossSheet"),
        ],
        # M3-2 明细表（按回购批次）
        "M3-2": [
            ("期末余额", "期初 + 借方(回购) − 贷方(注销/再售)", "计算",
             "备抵类明细期末余额（calcContraEquityEndBalance）", "useM3FormulaEngine"),
            ("审定数", "未审数 + AJE + RJE", "计算",
             "各批次审定金额（calcAuditedAmount）", "useM3FormulaEngine"),
            ("明细合计", "Σ 各批次行", "计算",
             "明细表列小计（calcSubtotal）", "useM3FormulaEngine"),
        ],
        # M3-3 调整分录
        "M3-3": [
            ("借贷平衡校验", "Σ 借方金额 = Σ 贷方金额", "logic_check",
             "调整分录借贷平衡", "useM3Adjustment"),
            ("AJE/RJE 回写审定表", "账项调整→AJE / 重分类调整→RJE 汇总回写 M3-1", "取数",
             "监听 adjustment:created 回写审定数", "useM3Adjustment"),
        ],
        # M3-4 外币投资汇率测算表
        "M3-4": [
            ("折算本位币金额", "外币回购金额 × 汇率", "计算",
             "外币回购折算（calcFxConverted）", "useM3FxEngine"),
            ("外币折算差异", "折算本位币 − 账面金额", "计算",
             "折算与账面差异（calcFxDiff）", "useM3FxEngine"),
        ],
        # M3-5 库存股检查表（回购/注销核对）
        "M3-5": [
            ("回购金额", "回购股数 × 回购价格", "计算",
             "回购成本测算（calcRepurchaseAmount）", "useM3TreasuryEngine"),
            ("注销冲减差额", "注销金额 − 冲减实收资本(面值) − 冲减资本公积", "计算",
             "注销冲减剩余差额，>0 需进一步冲减盈余公积/未分配利润（calcCancelDiff）",
             "useM3TreasuryEngine"),
            ("注销冲减 → M2实收资本 + M4资本公积", "注销金额拆分：面值→M2 / 差额→M4", "取数",
             "ADR-2 注销冲减顺序实收资本→资本公积，发布 m3:cancellation-deduction（cancellationToM2M4）",
             "useM3CrossSheet"),
            ("注销冲减平衡校验", "注销金额 = 冲减M2 + 冲减M4 + 未平差额", "logic_check",
             "未平差额 > 0.01 提示冲减盈余公积/未分配利润（hasRemainingDiff）", "useM3CrossSheet"),
        ],
        # 附注披露
        "附注上市": [
            ("附注披露金额", "取自 M3-1 审定表各回购批次审定数", "取数",
             "附注取审定数（M3 手动带入按钮）", "useM3Adjudication"),
        ],
        "附注国企": [
            ("附注披露金额", "取自 M3-1 审定表各回购批次审定数", "取数",
             "附注取审定数（M3 手动带入按钮）", "useM3Adjudication"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # M4 资本公积（权益贷方 4002；资本溢价+其他资本公积 + 接收J3股份支付/M2外币）
    # ═══════════════════════════════════════════════════════════════════════
    "M4": {
        # M4-1 审定表（资本溢价 + 其他资本公积 双区块）
        "M4-1": [
            ("审定数", "未审数 + 账项调整(AJE) + 重分类调整(RJE)", "计算",
             "各行审定金额（calcAuditedAmount）", "useM4FormulaEngine"),
            ("期末余额", "期初 + 贷方发生(增加) − 借方发生(减少)", "计算",
             "权益类贷方方向（calcEquityEndBalance）", "useM4FormulaEngine"),
            ("区块小计", "Σ 资本溢价 / Σ 其他资本公积", "计算",
             "双区块分类合计（calcSubtotal）", "useM4FormulaEngine"),
            ("试算平衡表数核对", "审定期末合计 − 试算平衡表数(4002 资本公积)", "logic_check",
             "审定数变化→writebackTB(4002)回写核对（saveAndWriteback）", "useM4Adjudication"),
            ("M4-1审定表 ↔ M4-2明细表勾稽", "M4-1 期末合计 − M4-2(资本溢价+其他资本公积)合计", "logic_check",
             "审定↔明细交叉验证（adjudicationVsDetail，容差 1 元）", "useM4CrossSheet"),
        ],
        # M4-2 明细表（资本溢价 + 其他资本公积）
        "M4-2": [
            ("期末余额", "期初 + 贷方(增加) − 借方(减少)", "计算",
             "明细期末余额（calcEquityEndBalance）", "useM4FormulaEngine"),
            ("审定数", "未审数 + AJE + RJE", "计算",
             "各项审定金额（calcAuditedAmount）", "useM4FormulaEngine"),
            ("明细合计", "Σ 资本溢价 + Σ 其他资本公积", "计算",
             "明细表列小计（calcSubtotal）", "useM4FormulaEngine"),
        ],
        # M4-3 调整分录
        "M4-3": [
            ("借贷平衡校验", "Σ 借方金额 = Σ 贷方金额", "logic_check",
             "调整分录借贷平衡", "useM4Adjustment"),
            ("AJE/RJE 回写审定表", "账项调整→AJE / 重分类调整→RJE 汇总回写 M4-1", "取数",
             "监听 adjustment:created 回写审定数", "useM4Adjustment"),
        ],
        # M4-4 资本公积检查表（接收 J3/M2）
        "M4-4": [
            ("J3股份支付确认差异", "J3 权益结算确认金额 − 账面其他资本公积增加", "logic_check",
             "订阅 j3:equity-settled 核对股份支付计入其他资本公积（calcShareBasedDiff / shareBasedVsJ3）",
             "useM4ReserveEngine / useM4CrossSheet"),
            ("M2外币折算差异核对", "M2 外币出资折算差异 − M4 资本溢价外币折算变动", "logic_check",
             "订阅 m2:fx-diff-to-m4 核对外币差异计入资本溢价（fxDiffVsM2，容差 0.01 元）",
             "useM4CrossSheet"),
        ],
        # 附注披露
        "附注上市": [
            ("附注披露金额", "取自 M4-1 审定表(资本溢价+其他资本公积)审定数", "取数",
             "附注取审定数，订阅 substantive:adjudicated 自动刷新（onAdjudicatedRefresh）",
             "useM4Adjudication"),
        ],
        "附注国企": [
            ("附注披露金额", "取自 M4-1 审定表(资本溢价+其他资本公积)审定数", "取数",
             "附注取审定数，订阅 substantive:adjudicated 自动刷新（onAdjudicatedRefresh）",
             "useM4Adjudication"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # M5 盈余公积（权益贷方 4101；法定+任意 双区块 + 计提测试 + M6净利润核对）
    # ═══════════════════════════════════════════════════════════════════════
    "M5": {
        # M5-1 审定表（法定盈余公积 + 任意盈余公积 双区块）
        "M5-1": [
            ("审定数", "未审数 + 账项调整(AJE) + 重分类调整(RJE)", "计算",
             "各行审定金额（calcAuditedAmount）", "useM5FormulaEngine"),
            ("期末余额", "期初 + 贷方发生(计提) − 借方发生(转增/弥补)", "计算",
             "权益类贷方方向（calcEquityEndBalance）", "useM5FormulaEngine"),
            ("区块小计", "Σ 法定盈余公积 / Σ 任意盈余公积", "计算",
             "双区块分类合计（calcSubtotal）", "useM5FormulaEngine"),
            ("变动率", "IF(期初=0∧变动=0,0; 期初=0∧变动>0,1; 变动额÷期初)", "计算",
             "审定表条件除法（M 循环统一）", "useM5Adjudication"),
            ("试算平衡表数核对", "审定期末合计 − 试算平衡表数(4101 盈余公积)", "logic_check",
             "审定数变化→writebackTB(4101)回写核对（saveAndWriteback）", "useM5Adjudication"),
            ("M5-1审定表 ↔ M5-2明细表勾稽", "M5-1 期末合计(row11) − M5-2(法定+任意)合计(row16)", "logic_check",
             "审定↔明细交叉验证（adjudicationVsDetail，容差 1 元）", "useM5CrossSheet"),
        ],
        # M5-2 明细表（法定 + 任意盈余公积）
        "M5-2": [
            ("期末余额", "期初 + 贷方(计提) − 借方(转增/弥补)", "计算",
             "明细期末余额（calcEquityEndBalance）", "useM5FormulaEngine"),
            ("审定数", "未审数 + AJE + RJE", "计算",
             "各项审定金额（calcAuditedAmount）", "useM5FormulaEngine"),
            ("明细合计", "Σ 法定 + Σ 任意盈余公积", "计算",
             "明细表列小计（calcSubtotal）", "useM5FormulaEngine"),
        ],
        # M5-3 调整分录
        "M5-3": [
            ("借贷平衡校验", "Σ 借方金额 = Σ 贷方金额", "logic_check",
             "调整分录借贷平衡", "useM5Adjustment"),
            ("AJE/RJE 回写审定表", "账项调整→AJE / 重分类调整→RJE 汇总回写 M5-1", "取数",
             "监听 adjustment:created 回写审定数", "useM5Adjustment"),
        ],
        # M5-4 盈余公积计提检查（法定 10% + 50% 上限）
        "M5-4": [
            ("法定盈余公积应计提", "计提基数(净利润) × 10%", "计算",
             "法定盈余公积计提（calcStatutoryAccrual，默认率 10%）", "useM5AccrualEngine"),
            ("计提差异", "应计提 − 账面计提", "计算",
             "正=少提/负=多提（calcAccrualDiff）", "useM5AccrualEngine"),
            ("累计计提上限判定", "累计盈余公积 ÷ 注册资本 ≥ 50% → 可不再计提", "logic_check",
             "法定盈余公积累计不超注册资本 50%（isAccrualCeilingReached）", "useM5AccrualEngine"),
            ("计提基数 ↔ M6净利润一致性", "M5-4 计提基数(净利润) − M6 实际净利润", "logic_check",
             "订阅 m6:net-profit 校验计提基数（accrualVsM6，容差 0.01 元）", "useM5CrossSheet"),
            ("M5计提 → M6可供分配利润", "Σ(法定计提 + 任意计提) → M6 回流核对", "取数",
             "ADR-3 M5计提盈余公积回流影响 M6，发布 m5:surplus-accrual（publishAccrualToM6）",
             "useM5CrossSheet"),
        ],
        # M5-5 盈余公积检查表
        "M5-5": [
            ("检查合计", "Σ 检查金额", "计算",
             "盈余公积检查合计（calcSubtotal）", "useM5ReserveCheck"),
        ],
        # 附注披露
        "附注上市": [
            ("附注披露金额", "取自 M5-1 审定表(法定+任意)审定数", "取数",
             "附注取审定数，订阅 substantive:adjudicated 自动刷新（onAdjudicatedRefresh）",
             "useM5Adjudication"),
        ],
        "附注国企": [
            ("附注披露金额", "取自 M5-1 审定表(法定+任意)审定数", "取数",
             "附注取审定数，订阅 substantive:adjudicated 自动刷新（onAdjudicatedRefresh）",
             "useM5Adjudication"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # M6 利润分配-未分配利润（权益贷方 4104；权益循环枢纽！结转链 + M5/M1 双向联动）
    # ═══════════════════════════════════════════════════════════════════════
    "M6": {
        # M6-1 审定表
        "M6-1": [
            ("审定数", "未审数 + 账项调整(AJE) + 重分类调整(RJE)", "计算",
             "各行审定金额（calcAuditedAmount）", "useM6FormulaEngine"),
            ("期末余额", "期初 + 贷方发生(净利润转入) − 借方发生(分配)", "计算",
             "权益类贷方方向（calcEquityEndBalance）", "useM6FormulaEngine"),
            ("合计", "Σ 利润分配各项目", "计算",
             "审定表合计（calcSubtotal）", "useM6FormulaEngine"),
            ("试算平衡表数核对", "审定期末数 − 试算平衡表数(4104 未分配利润)", "logic_check",
             "审定数变化→writebackTB(4104)回写核对（saveAndWriteback）", "useM6Adjudication"),
            ("M6-1审定表 ↔ M6-2明细表勾稽", "M6-1 期末审定数 − M6-2 结转后期末未分配利润", "logic_check",
             "审定↔明细交叉验证（adjudicationVsDetail，容差 1 元）", "useM6CrossSheet"),
        ],
        # M6-2 明细表（利润分配结转链）
        "M6-2": [
            ("期末未分配利润", "期初 + 本年净利润 − 提取盈余公积 − 分配股利", "计算",
             "利润分配结转链核心公式（calcRetainedEnd）", "useM6DistributionEngine"),
            ("可供分配利润", "期初未分配利润 + 本年净利润", "计算",
             "可供分配利润（calcDistributable）", "useM6DistributionEngine"),
        ],
        # M6-3 调整分录
        "M6-3": [
            ("借贷平衡校验", "Σ 借方金额 = Σ 贷方金额", "logic_check",
             "调整分录借贷平衡", "useM6Adjustment"),
            ("AJE/RJE 回写审定表", "账项调整→AJE / 重分类调整→RJE 汇总回写 M6-1", "取数",
             "监听 adjustment:created 回写审定数", "useM6Adjustment"),
        ],
        # M6-4 未分配利润检查表（枢纽联动）
        "M6-4": [
            ("提取盈余公积 ↔ M5计提一致性", "M6-2 提取盈余公积 − M5 实际计提合计", "logic_check",
             "订阅 m5:surplus-accrual 核对（surplusVsM5，容差 0.01 元；calcLinkageDiff）",
             "useM6CrossSheet"),
            ("分配股利 ↔ M1宣告一致性", "M6-2 分配股利 − M1 实际宣告股利", "logic_check",
             "订阅 m1:declared-confirmed 核对（dividendVsM1，容差 0.01 元）", "useM6CrossSheet"),
            ("本年净利润 → M5计提基数", "本年净利润 → 驱动 M5 按法定 10% 计提", "取数",
             "ADR-3 枢纽发布 m6:net-profit（publishNetProfitToM5）", "useM6CrossSheet"),
            ("分配股利 → M1应付股利", "分配股利 → 通知 M1 宣告处理", "取数",
             "ADR-3 枢纽发布 m6:profit-distributed（publishDividendToM1）", "useM6CrossSheet"),
        ],
        # 附注披露
        "附注上市": [
            ("附注披露金额", "取自 M6-1 审定表未分配利润审定数", "取数",
             "附注取审定数，订阅 substantive:adjudicated 自动刷新（onAdjudicatedRefresh）",
             "useM6Adjudication"),
        ],
        "附注国企": [
            ("附注披露金额", "取自 M6-1 审定表未分配利润审定数", "取数",
             "附注取审定数，订阅 substantive:adjudicated 自动刷新（onAdjudicatedRefresh）",
             "useM6Adjudication"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # M7 专项储备（权益贷方 4201；安全生产费计提 + 资本化支出→H1联动）
    # ═══════════════════════════════════════════════════════════════════════
    "M7": {
        # M7-1 审定表（按类别 + 小计）
        "M7-1": [
            ("审定数", "未审数 + 账项调整(AJE) + 重分类调整(RJE)", "计算",
             "各行审定金额，xlsx L10=B10+F10+G10（calcAuditedAmount）", "useM7FormulaEngine"),
            ("期末余额", "期初 + 贷方发生(计提) − 借方发生(使用)", "计算",
             "权益类贷方方向，xlsx E10=B10+C10-D10（calcEquityEndBalance）", "useM7FormulaEngine"),
            ("分类小计", "Σ 各类别行", "计算",
             "按类别分类合计 SUM(B7:B12)（calcSubtotal）", "useM7FormulaEngine"),
            ("试算平衡表数核对", "审定期末合计 − 试算平衡表数(4201 专项储备)", "logic_check",
             "审定数变化→writebackTB(4201)回写核对（saveAndWriteback）", "useM7Adjudication"),
            ("M7-1审定表 ↔ M7-2明细表勾稽", "M7-1 期末合计(O17) − M7-2 明细汇总行", "logic_check",
             "审定↔明细交叉验证（adjudicationVsDetail，容差 1 元）", "useM7CrossSheet"),
        ],
        # M7-2 明细表（计提 + 使用）
        "M7-2": [
            ("期末余额", "期初 + 贷方(计提) − 借方(费用化使用 + 资本化使用)", "计算",
             "明细期末余额（calcEquityEndBalance）", "useM7FormulaEngine"),
            ("审定数", "未审数 + AJE + RJE", "计算",
             "各项审定金额（calcAuditedAmount）", "useM7FormulaEngine"),
            ("明细合计", "Σ 计提 / Σ 费用化 / Σ 资本化", "计算",
             "明细表列小计（calcSubtotal）", "useM7FormulaEngine"),
        ],
        # M7-3 调整分录
        "M7-3": [
            ("借贷平衡校验", "Σ 借方金额 = Σ 贷方金额", "logic_check",
             "调整分录借贷平衡", "useM7Adjustment"),
            ("AJE/RJE 回写审定表", "账项调整→AJE / 重分类调整→RJE 汇总回写 M7-1", "取数",
             "监听 adjustment:created 回写审定数", "useM7Adjustment"),
        ],
        # M7-4 专项储备计提测试（安全生产费）
        "M7-4": [
            ("按产量分档计提", "Σ(各档产量 × 分档费率)", "计算",
             "安全生产费按产量分档计提（calcAccrualByOutput）", "useM7AccrualEngine"),
            ("按营业收入计提", "营业收入 × 计提费率", "计算",
             "安全生产费按收入计提（calcAccrualByRevenue）", "useM7AccrualEngine"),
            ("计提差异", "应计提 − 账面计提", "计算",
             "正=应补提/负=多计提（calcAccrualDiff）", "useM7AccrualEngine"),
            ("资本化支出 → H1固定资产", "M7-2 资本化支出合计 − H1 已确认转固金额", "logic_check",
             "ADR-3 资本性支出形成固定资产+全额折旧冲减，订阅 h1:fixed-asset-confirmed"
             "（capitalExpToH1，容差 1 元；发布 m7:capital-exp-to-h1）", "useM7CrossSheet"),
        ],
        # M7-5 专项储备支出检查表
        "M7-5": [
            ("检查合计", "Σ 检查金额", "计算",
             "专项储备支出检查合计（calcSubtotal）", "useM7FormulaEngine"),
        ],
        # 附注披露
        "附注上市": [
            ("附注披露金额", "取自 M7-1 审定表各类别审定数", "取数",
             "附注取审定数（useNoteAutoFill SDK 订阅 substantive:adjudicated 自动刷新）",
             "useM7Adjudication"),
        ],
        "附注国企": [
            ("附注披露金额", "取自 M7-1 审定表各类别审定数", "取数",
             "附注取审定数（useNoteAutoFill SDK 订阅 substantive:adjudicated 自动刷新）",
             "useM7Adjudication"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # M8 一般风险准备（权益贷方 4104；金融企业专属！风险资产计提 + 行业守卫）
    # ═══════════════════════════════════════════════════════════════════════
    "M8": {
        # M8-1 审定表
        "M8-1": [
            ("审定数", "未审数 + 账项调整(AJE) + 重分类调整(RJE)", "计算",
             "各行审定金额（calcAuditedAmount）", "useM8FormulaEngine"),
            ("期末余额", "期初 + 贷方发生(计提) − 借方发生(转回/使用)", "计算",
             "权益类贷方方向 E=B+C-D（calcEquityEndBalance）", "useM8FormulaEngine"),
            ("分类小计", "row13 = SUM(rows 7-12)", "计算",
             "审定表期末合计（calcSubtotal）", "useM8FormulaEngine"),
            ("变动额", "期末审定 − 期初审定（J=I−E）", "计算",
             "本期变动额（M 循环统一）", "useM8Adjudication"),
            ("试算平衡表数核对", "审定期末合计 − 试算平衡表数(4104 一般风险准备)", "logic_check",
             "审定数变化→writebackTB(4104)回写核对（saveAndWriteback）", "useM8Adjudication"),
            ("M8-1审定表 ↔ M8-2明细表勾稽", "M8-1 合计(row13) − M8-2 合计(row17)", "logic_check",
             "审定↔明细交叉验证（adjudicationVsDetail，容差 1 元）", "useM8CrossSheet"),
        ],
        # M8-2 明细表
        "M8-2": [
            ("期末余额", "期初 + 贷方(计提) − 借方(转回/使用)", "计算",
             "明细期末余额（calcEquityEndBalance）", "useM8FormulaEngine"),
            ("审定数", "未审数 + AJE + RJE", "计算",
             "各项审定金额（calcAuditedAmount）", "useM8FormulaEngine"),
            ("明细合计", "row17 = SUM(rows 10-16)", "计算",
             "明细表期末合计（calcSubtotal）", "useM8FormulaEngine"),
        ],
        # M8-3 调整分录
        "M8-3": [
            ("借贷平衡校验", "Σ 借方金额 = Σ 贷方金额", "logic_check",
             "调整分录借贷平衡", "useM8Adjustment"),
            ("AJE/RJE 回写审定表", "账项调整→AJE / 重分类调整→RJE 汇总回写 M8-1", "取数",
             "监听 adjustment:created 回写审定数", "useM8Adjustment"),
        ],
        # M8-4 一般风险准备测试表（风险资产计提测试）
        "M8-4": [
            ("应计提一般风险准备", "风险资产期末余额 × 计提比例(≥1.5%)", "计算",
             "金融企业按风险资产 1.5% 计提（calcRiskProvision，G 列）", "useM8RiskEngine"),
            ("计提差异", "应计提 − 账面计提", "计算",
             "正=计提不足/负=超额计提（calcProvisionDiff）", "useM8RiskEngine"),
            ("金融企业适用性判定", "被审计单位行业 ∈ 金融/银行/证券/保险/信托/基金/期货/金融租赁", "logic_check",
             "一般风险准备仅金融企业适用，非金融企业提示不适用（isFinancialEntity）", "useM8CrossSheet"),
        ],
        # 附注披露
        "附注上市": [
            ("附注披露金额", "取自 M8-1 审定表审定数", "取数",
             "附注取审定数，订阅 substantive:adjudicated 自动刷新（onAdjudicatedRefresh）",
             "useM8Adjudication"),
        ],
        "附注国企": [
            ("附注披露金额", "取自 M8-1 审定表审定数", "取数",
             "附注取审定数，订阅 substantive:adjudicated 自动刷新（onAdjudicatedRefresh）",
             "useM8Adjudication"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # M9 其他综合收益（权益贷方 4103；OCI两大类 + 税后净额 + G8/J2来源核对）
    # ═══════════════════════════════════════════════════════════════════════
    "M9": {
        # M9-1 审定表（不可重分类 + 可重分类 双大类）
        "M9-1": [
            ("审定数", "未审数 + 账项调整(AJE) + 重分类调整(RJE)", "计算",
             "各行审定金额（calcAuditedAmount）", "useM9FormulaEngine"),
            ("期末余额", "期初 + 贷方发生(OCI增加) − 借方发生(减少/重分类进损益)", "计算",
             "权益类贷方方向（calcEquityEndBalance）", "useM9FormulaEngine"),
            ("区块小计", "Σ 不可重分类 / Σ 可重分类", "计算",
             "双大类分组合计（calcSubtotal）", "useM9FormulaEngine"),
            ("变动率", "IF(期初=0∧期末=0,0; 期初=0,1; 变动÷期初)", "计算",
             "审定表条件除法（M 循环统一）", "useM9Adjudication"),
            ("试算平衡表数核对", "审定期末合计 − 试算平衡表数(4103 其他综合收益)", "logic_check",
             "审定数变化→writebackTB(4103)回写核对（saveAndWriteback）", "useM9Adjudication"),
            ("M9-1审定表 ↔ M9-2明细表勾稽", "M9-1 期末合计 − M9-2(不可+可重分类)合计", "logic_check",
             "审定↔明细交叉验证（adjudicationVsDetail，容差 1 元）", "useM9CrossSheet"),
        ],
        # M9-2 明细表（OCI分项 + 税后净额）
        "M9-2": [
            ("期末余额", "期初 + 贷方(OCI增加) − 借方(减少/重分类)", "计算",
             "OCI分项明细期末余额（calcEquityEndBalance）", "useM9FormulaEngine"),
            ("本期税后净额", "本期税前金额 − 所得税影响", "计算",
             "OCI 按税后净额列示（calcAfterTaxNet）", "useM9OciEngine"),
            ("审定数", "未审数 + AJE + RJE", "计算",
             "各分项审定金额（calcAuditedAmount）", "useM9FormulaEngine"),
            ("明细合计", "Σ 各 OCI 分项", "计算",
             "明细表列小计（calcSubtotal）", "useM9FormulaEngine"),
        ],
        # M9-3 调整分录
        "M9-3": [
            ("借贷平衡校验", "Σ 借方金额 = Σ 贷方金额", "logic_check",
             "调整分录借贷平衡", "useM9Adjustment"),
            ("AJE/RJE 回写审定表", "账项调整→AJE / 重分类调整→RJE 汇总回写 M9-1", "取数",
             "监听 adjustment:created 回写审定数", "useM9Adjustment"),
        ],
        # M9-4 OCI核对表（多来源核对）
        "M9-4": [
            ("本期税后净额", "本期税前金额 − 所得税影响", "计算",
             "来源金额税后净额（calcAfterTaxNet）", "useM9OciEngine"),
            ("核对差异", "来源金额(税后) − 账面 OCI 增加", "计算",
             "核对差异（calcReconcileDiff，0=一致）", "useM9OciEngine"),
            ("G8公允价值变动核对", "G8 其他权益工具投资公允变动(税后) − 账面 OCI 增加(不可重分类)", "logic_check",
             "订阅 g8:fair-value-changed 核对（ociVsG8，容差 0.01 元）", "useM9CrossSheet"),
            ("J2重计量核对", "J2 设定受益计划重计量(税后) − 账面 OCI 增加(不可重分类)", "logic_check",
             "订阅 j2:remeasured 核对（ociVsJ2，容差 0.01 元）", "useM9CrossSheet"),
        ],
        # 附注披露
        "附注上市": [
            ("附注披露金额", "取自 M9-1 审定表(不可+可重分类)审定数", "取数",
             "附注取审定数，订阅 substantive:adjudicated 自动刷新（onAdjudicatedRefresh）",
             "useM9Adjudication"),
        ],
        "附注国企": [
            ("附注披露金额", "取自 M9-1 审定表(不可+可重分类)审定数", "取数",
             "附注取审定数，订阅 substantive:adjudicated 自动刷新（onAdjudicatedRefresh）",
             "useM9Adjudication"),
        ],
    },
    # ═══════════════════════════════════════════════════════════════════════
    # M10 其他权益工具（权益贷方 4003；CAS37 权益/负债区分 + 金额守恒 + →L4/L7）
    # ═══════════════════════════════════════════════════════════════════════
    "M10": {
        # M10-1 审定表（按工具类型 永续债/优先股/其他）
        "M10-1": [
            ("审定数", "未审数 + 账项调整(AJE) + 重分类调整(RJE)", "计算",
             "各行审定金额（calcAuditedAmount）", "useM10FormulaEngine"),
            ("期末余额", "期初 + 贷方发生(发行) − 借方发生(赎回/转换)", "计算",
             "权益类贷方方向（calcEquityEndBalance）", "useM10FormulaEngine"),
            ("分类小计", "Σ 永续债 / Σ 优先股 / Σ 其他", "计算",
             "按工具类型分组合计（calcSubtotal）", "useM10FormulaEngine"),
            ("变动额", "期末审定数 − 期初审定数（J=I−E）", "计算",
             "本期变动额（calcVariance）", "useM10FormulaEngine"),
            ("变动率", "IF(期初=0∧期末=0,null; 期初=0∧期末>0,1; (期末−期初)÷期初)", "计算",
             "审定表 K 列条件除法（calcVarianceRate）", "useM10FormulaEngine"),
            ("试算平衡表数核对", "审定期末合计 − 试算平衡表数(4003 其他权益工具)", "logic_check",
             "审定数变化→writebackTB(4003)回写核对（saveAndWriteback）", "useM10Adjudication"),
            ("M10-1审定表 ↔ M10-2明细表勾稽", "M10-1 期末审定合计 − M10-2 各工具期末合计", "logic_check",
             "审定↔明细交叉验证（adjudicationVsDetail，容差 1 元）", "useM10CrossSheet"),
        ],
        # M10-2 明细表（永续债/优先股）
        "M10-2": [
            ("净发行额", "发行总额 − 发行费用", "计算",
             "永续债/优先股扣除承销费等（calcNetIssuance）", "useM10FormulaEngine"),
            ("明细期末余额", "期初 + 本期发行(净额) − 本期赎回/转换", "计算",
             "单项工具明细期末（calcDetailEndBalance）", "useM10FormulaEngine"),
            ("审定数", "未审数 + AJE + RJE", "计算",
             "各工具审定金额（calcAuditedAmount）", "useM10FormulaEngine"),
        ],
        # M10-3 调整分录
        "M10-3": [
            ("借贷平衡校验", "Σ 借方金额 = Σ 贷方金额", "logic_check",
             "调整分录借贷平衡", "useM10Adjustment"),
            ("AJE/RJE 回写审定表", "账项调整→AJE / 重分类调整→RJE 汇总回写 M10-1", "取数",
             "监听 adjustment:created 回写审定数", "useM10Adjustment"),
        ],
        # M10-4 负债与权益区分检查表（CAS37 核心）
        "M10-4": [
            ("工具分类判定", "有合同义务 → 金融负债；无合同义务 → 权益工具", "logic_check",
             "CAS37 权益/负债区分（classifyInstrument）", "useM10ClassificationEngine"),
            ("负债部分金额", "工具总额 − 权益部分金额", "计算",
             "复合金融工具拆分（splitAmount）", "useM10ClassificationEngine"),
            ("分类金额守恒校验", "权益部分 + 负债部分 = 工具总额", "logic_check",
             "复合工具拆分金额守恒（calcClassificationConsistency）", "useM10ClassificationEngine"),
            ("负债部分 → 负债科目", "分类为负债的工具 → L4应付债券(永续债) / L7其他非流动负债(优先股)", "取数",
             "负债部分提示计入负债科目（liabilityItems + crossWpReferences）", "useM10CrossSheet"),
        ],
        # M10-5 其他权益工具检查表
        "M10-5": [
            ("检查合计", "Σ 检查金额", "计算",
             "其他权益工具检查合计（calcSubtotal）", "useM10InstrumentCheck"),
        ],
        # 附注披露
        "附注上市": [
            ("附注披露金额", "取自 M10-1 审定表(按工具类型)审定数", "取数",
             "附注取审定数，订阅 substantive:adjudicated 自动刷新", "useM10Adjudication"),
        ],
        "附注国企": [
            ("附注披露金额", "取自 M10-1 审定表(按工具类型)审定数", "取数",
             "附注取审定数，订阅 substantive:adjudicated 自动刷新", "useM10Adjudication"),
        ],
    },
}

