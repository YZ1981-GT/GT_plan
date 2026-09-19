"""G10 交易性金融负债 — 导入导出（G10-1~8 + 附注 × 3 端点）."""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router
from ._g10_disclosure_io import (
    build_listed_disclosure_workbook,
    build_soe_disclosure_workbook,
    parse_listed_disclosure_workbook,
    parse_soe_disclosure_workbook,
)

# ── G10-1 审定表（keyed remark store：{rowKey: cell}，对齐 G2-1 / G1-1）──
_G10_1_HEADERS = [
    "行键", "项目", "区段",
    "期初未审", "期初AJE", "期初RJE",
    "期末未审", "期末AJE", "期末RJE",
    "原因分析", "索引",
]
_G10_1_KEYS = [
    "rowKey", "label", "section",
    "openingUnadjusted", "openingAJE", "openingRJE",
    "closingUnadjusted", "closingAJE", "closingRJE",
    "reasonAnalysis", "indexRef",
]
_G10_1_KEEP_KEYS = [
    "openingUnadjusted", "openingAJE", "openingRJE",
    "closingUnadjusted", "closingAJE", "closingRJE",
    "reasonAnalysis", "indexRef",
]

_G10_1_LINES = [
    ("trading_liability", "交易性金融负债"),
    ("trading_bond", "其中：发行的交易性债券"),
    ("derivative_liability", "衍生金融负债"),
    ("other", "其他"),
    ("designated_fvtpl", "指定为以公允价值计量且其变动计入当期损益的金融负债"),
    ("designated_bond", "其中：债券"),
    ("hybrid_tool", "混合工具"),
    ("other_designated", "其他"),
]
_G10_1_SECTIONS = [
    ("(一)初始金额", "init"),
    ("(二)累计公允价值变动", "fv"),
    ("(三)账面余额（公允价值）", "book"),
]


def _build_g10_1_prefill() -> list[list[Any]]:
    rows: list[list[Any]] = []
    for section_label, prefix in _G10_1_SECTIONS:
        for suffix, label in _G10_1_LINES:
            rows.append([
                f"{prefix}_{suffix}",
                label,
                section_label,
                0, 0, 0, 0, 0, 0, "", "",
            ])
    return rows


_G10_2_HEADERS = [
    "序号", "类别", "负债名称", "负债类型", "对手方", "合同日", "到期日", "票面利率", "期末应付利息", "发行文件索引",
    "期初(一)初始确认", "期初(二)累计FV", "期初调整", "期初审定",
    "本期初始确认", "本期FV变动", "计入财务费用利息", "本期减少",
    "期末(一)初始", "期末(二)累计FV", "期末(三)公允价值", "期末余额", "调整数", "审定数",
    "公允价值层次", "估值方法", "是否衍生工具", "主合同描述", "嵌入衍生判断", "发函情况", "备注",
]
_G10_2_KEYS = [
    "seq", "liabilityCategory", "liabilityName", "liabilityType", "counterparty", "contractDate", "maturityDate",
    "couponRate", "accruedInterest", "issuanceDocIndex",
    "openingInitialAmount", "openingFvAccum", "openingAdjustment", "openingAdjusted",
    "movementInitialAmount", "movementFvChange", "interestExpense", "currentDecrease",
    "closingInitialAmount", "closingFvAccum", "closingFairValue", "closingBalance", "closingAdjustment", "closingAdjusted",
    "fairValueLevel", "valuationMethod", "isDerivative", "hostContractDesc", "embeddedDerivativeJudgment",
    "confirmationStatus", "remark",
]

_G10_3_HEADERS = [
    "序号", "分录类型", "日期", "摘要", "负债类型", "回写行", "科目代码", "科目名称",
    "借方", "贷方", "索引", "编制人", "备注",
]
_G10_3_KEYS = [
    "seq", "entryType", "date", "summary", "liabilityType", "adjudicationRowKey",
    "accountCode", "accountName", "debitAmount", "creditAmount", "indexRef",
    "preparedBy", "remark",
]

_G10_5_HEADERS = [
    "序号", "负债名称", "初始确认日期",
    "期末未审数量", "期末未审单价", "期末未审公允价值",
    "期末审定数量", "期末审定单价", "期末审定公允价值", "公允价值层次",
    "估值方法", "与上期一致", "来源机构", "输入值来源", "估值技术",
    "不可观察输入值描述", "数值", "敏感性分析", "索引",
]
_G10_5_KEYS = [
    "seq", "liabilityName", "initialDate",
    "closingUnadjustedQty", "closingUnadjustedPrice", "closingUnadjustedFV",
    "closingAuditedQty", "closingAuditedPrice", "closingAuditedFV", "fairValueLevel",
    "valuationMethod", "methodConsistentWithPrior", "valuationSource", "inputSourceAndAdjustment",
    "valuationTechnique", "unobservableInputDesc", "unobservableInputValue",
    "sensitivityAnalysis", "valuationDocIndex",
]

_G10_6_HEADERS = [
    "序号", "负债名称", "期初余额", "本期新增", "本期终止", "转入L3", "转出L3",
    "公允价值变动", "利息费用", "其他", "期末余额(公式)", "企业报告期末", "差异", "备注",
]
_G10_6_KEYS = [
    "seq", "liabilityName", "openingBalance", "currentNew", "currentTerminated",
    "transferIntoL3", "transferOutOfL3", "fairValueChange", "interestExpense", "otherChanges",
    "closingBalance", "reportedClosing", "variance", "remark",
]
_G10_6_HEADER_ALIASES = {
    "负债名称": ["项目名称"],
    "企业报告期末": ["企业期末", "报告期末"],
    "期末余额(公式)": ["期末余额", "公式期末"],
}

_G10_7_HEADERS = [
    "序号", "期间", "日期", "凭证编号", "业务内容", "对方科目", "借方", "贷方",
    "附件", "文件描述", "核对1齐全", "核对2授权", "核对3账务", "核对4成本", "核对5利息", "核对6公允",
    "索引号", "是否异常", "异常说明", "风险等级", "备注",
]
_G10_7_KEYS = [
    "seq", "periodScope", "voucherDate", "voucherNo", "businessContent", "counterAccount",
    "debitAmount", "creditAmount", "attachment", "supportingDocDesc",
    "check1OriginalComplete", "check2Authorization", "check3Accounting",
    "check4InitialCost", "check5Interest", "check6FairValueCorrect",
    "indexNo", "isAbnormal", "abnormalDesc", "riskLevel", "remark",
]

_G10_4_HEADERS = [
    "行ID", "序号", "负债名称", "期末账面价值", "负债类别",
    "交易性-近期出售回购", "交易性-组合短期获利", "交易性-衍生金融负债",
    "指定-消除会计错配", "指定-公允价值管理", "索引", "明细行ID",
]
_G10_4_KEYS = [
    "id", "seq", "liabilityName", "closingBookValue", "liabilityCategory",
    "tradingNearTermSale", "tradingPortfolioShortTerm", "tradingDerivative",
    "designatedMismatch", "designatedFvManagement", "indexRef", "detailRowId",
]

_G10_8_HEADERS = [
    "行ID", "序号", "区段号", "区段标题", "检查领域", "检查项目", "审计要求",
    "检查结果", "合规性", "风险等级", "审计结论", "索引", "备注",
]
_G10_8_KEYS = [
    "rowId", "seq", "sectionNo", "sectionTitle", "checkArea", "checkItem", "auditRequirement",
    "checkResult", "compliance", "riskLevel", "auditConclusion", "indexRef", "remark",
]

_G10_SPECS: dict[str, dict[str, Any]] = {
    "G10-1": {
        "item_id": "G10-adj-rows",
        "title": "G10-1 交易性金融负债审定表",
        "headers": _G10_1_HEADERS,
        "field_keys": _G10_1_KEYS,
        "storage_field": "remark",
        "keyed_by": "rowKey",
        "keep_keys": _G10_1_KEEP_KEYS,
        "template_prefill": _build_g10_1_prefill(),
        "guidance": [
            "G10-1 审定表 编制说明",
            "",
            "行键(rowKey)须与模板一致，勿改动；仅填写未审/AJE/RJE/原因分析/索引。",
            "区段：(一)初始金额 / (二)累计公允价值变动 / (三)账面余额（公允价值）。",
            "审定=未审+AJE+RJE；(三)各分项应等于(一)+(二)；|变动率|>20% 时原因分析必填。",
            "可从 G10-2「回写 G10-1」或 G10-3 分项账项调整自动带入；导入后请校验与试算 2101 勾稽。",
        ],
    },
    "G10-2": {
        "item_id": "G10-detail-rows",
        "title": "G10-2 交易性金融负债明细表",
        "headers": _G10_2_HEADERS,
        "field_keys": _G10_2_KEYS,
        "guidance": [
            "G10-2 明细表 编制说明",
            "",
            "对齐 Excel roll-forward：期初/期末均分解 (一)初始确认+(二)累计FV=(三)公允价值；",
            "本期变动分列初始确认、FV变动、计入财务费用利息、减少；审定=期末余额+调整。",
        ],
    },
    "G10-3": {
        "item_id": "G10-aje-rows",
        "title": "G10-3 调整分录汇总表",
        "headers": _G10_3_HEADERS,
        "field_keys": _G10_3_KEYS,
        "guidance": [
            "G10-3 调整分录汇总表 编制说明",
            "",
            "一、本表目的",
            "汇总本科目（2101 交易性金融负债）相关的审计调整分录（AJE）和重分类调整分录（RJE），",
            "确保调整依据充分、借贷平衡，并正确回写至 G10-1 审定表 (三) 账面余额分项。",
            "",
            "二、填写要求",
            "1. 「分录类型」：AJE（账项调整）/ RJE（重分类调整）。",
            "2. 「负债类型/回写行」：指定 G10-1 (三) 回写目标；未填时按摘要关键词自动推断。",
            "3. 「科目代码/名称」：2101/6101/6603 等；FVTPL 公允变动通常 Dr 6101 / Cr 2101。",
            "4. 「借方/贷方」：整表借贷须平衡。",
            "5. 「索引」：支持性底稿索引（如 G10-5 公允价值测试、G10-2 明细）。",
            "",
            "三、审计关注",
            "1. 2101 净额（贷−借）须与 G10-1 对应分项期末账项调整一致。",
            "2. RJE 仅影响列报；AJE 涉及损益须与 G10-2「计入损益」勾稽。",
            "3. 差异来源于 G10-5 公允测试时，索引应指向 G10-5。",
            "4. 可从 G10-5「推送差异→G10-3」、G10-7「推送异常→G10-3」、G10-8「推送不合规→G10-3」带入；",
            "   亦可推送/同步至中央调整分录模块。",
            "5. 「负债类型/回写行」用于分项回写 G10-1 (三)；零金额备忘行须后续补录借贷金额。",
        ],
    },
    "G10-4": {
        "item_id": "G10-classification-rows",
        "title": "G10-4 分类的适当性检查表",
        "headers": _G10_4_HEADERS,
        "field_keys": _G10_4_KEYS,
        "guidance": [
            "G10-4 分类适当性检查 编制说明",
            "",
            "核实 FVTPL 金融负债分类依据是否符合 CAS 22/37。",
            "勾选列填 yes / no / na（或 是/否/不适用）；至少一项交易性或指定依据为 yes。",
            "建议先从 G10-2 带入项目与账面价值，再勾选依据。",
            "缺依据或类别不符可推送重分类草稿至 G10-3。",
        ],
    },
    "G10-5": {
        "item_id": "G10-fv-test-rows",
        "title": "G10-5 公允价值测试表",
        "headers": _G10_5_HEADERS,
        "field_keys": _G10_5_KEYS,
        "guidance": [
            "G10-5 公允价值测试 编制说明",
            "",
            "Level3 时估值技术与不可观察输入值描述必填。",
        ],
    },
    "G10-6": {
        "item_id": "G10-l3-rows",
        "title": "G10-6 第三层次公允价值调节表",
        "headers": _G10_6_HEADERS,
        "field_keys": _G10_6_KEYS,
        "allow_missing_headers": True,
        "header_aliases": _G10_6_HEADER_ALIASES,
        "guidance": [
            "G10-6 L3调节表 编制说明",
            "",
            "一、本表目的",
            "按 CAS 37 / IFRS 13 要求，对第三层次（L3）交易性金融负债编制期初至期末调节表，",
            "验证各因子变动完整准确，公式期末与企业报告勾稽，为附注披露提供数据基础。",
            "",
            "二、填写要求",
            "1. 「负债名称」列：逐笔列示 L3 负债（与 G10-2 / G10-5 一致）。",
            "2. 十因子列（期初~其他）：逐笔填写期间内各类变动金额（负债方向：新增/终止）。",
            "3. 「企业报告期末」列：填写企业财务报表中列示的 L3 期末金额（用于勾稽）。",
            "",
            "三、自动计算列说明（灰底，导入时忽略）",
            "公式期末 = 期初 + 新增 − 终止 + 转入L3 − 转出L3 + FV变动 + 利息费用 + 其他",
            "差异 = 企业报告期末 − 公式期末（差异 > 0.01 须说明）",
            "",
            "四、审计关注",
            "1. 企业期末合计应与 G10-5 Level3 审定 FV 勾稽。",
            "2. 差异超标可「推送差异→G10-3」生成 AJE 并回写 G10-1。",
            "3. 优先「从 G10-2 带入」明细变动；「从 G10-5 带入」补填企业期末。",
        ],
    },
    "G10-7": {
        "item_id": "G10-voucher-rows",
        "title": "G10-7 凭证检查表",
        "headers": _G10_7_HEADERS,
        "field_keys": _G10_7_KEYS,
        "guidance": [
            "G10-7 凭证检查 编制说明",
            "",
            "六项核对：①齐全②授权③账务④成本⑤利息⑥公允；任一项「否」→ 异常。",
            "本期与期后分表编制；检查比例 = 已查金额 ÷ 总体金额。",
            "金额类异常可「推送异常→G10-3」生成 AJE 草稿并回写 G10-1。",
        ],
    },
    "G10-8": {
        "item_id": "G10-derivative-rows",
        "title": "G10-8 衍生金融工具核查表",
        "headers": _G10_8_HEADERS,
        "field_keys": _G10_8_KEYS,
        "guidance": [
            "G10-8 衍生金融工具核查 编制说明",
            "",
            "五要素（CAS22）逐项核查；合规性填 compliant / non_compliant / not_applicable。",
            "风险等级 high / medium / low；不合规项可推送至 G10-3。",
            "可从 G10-2 带入衍生明细后回写判断。",
        ],
    },
    "附注上市": {
        "item_id": "G10-disclosure-listed",
        "title": "附注披露信息（上市公司）",
        "storage_field": "remark",
        "dual_write": False,
        "build_workbook": lambda payload, template_only=False: build_listed_disclosure_workbook(
            payload, template_only=template_only,
        ),
        "parse_import": parse_listed_disclosure_workbook,
        "guidance": [
            "附注披露（上市公司）编制说明",
            "",
            "多工作表结构对齐 Excel 底稿：",
            "1. 「变动表」：项目/期初/增加/减少/期末（父行合计由页面公式汇总，勿导入合计行）",
            "2. 「指定明细」：期初/期末/指定的理由和依据",
            "3. 「信用风险」：公允价值变动与自身信用风险拆分（CAS 37 §41-43）",
            "4. 「衍生负债」：期末/上年年末 + 「说明」表填写衍生成因",
            "5. 「说明」：derivativeNote / maturityDiffNote",
            "",
            "建议先在 G10-2 维护种类与增减，再在附注页「分项带入」；也可本模板手工/导入。",
            "期末合计应与 G10-1 审定（2101）勾稽。",
        ],
    },
    "附注国企": {
        "item_id": "G10-disclosure-soe",
        "title": "附注披露信息（国企）",
        "storage_field": "remark",
        "dual_write": False,
        "build_workbook": lambda payload, template_only=False: build_soe_disclosure_workbook(
            payload, template_only=template_only,
        ),
        "parse_import": parse_soe_disclosure_workbook,
        "guidance": [
            "附注披露（国企）编制说明",
            "",
            "多工作表结构：",
            "1. 「余额表」：项目/期末公允价值/期初公允价值",
            "2. 「信用风险」：公允价值变动与自身信用风险拆分",
            "3. 「说明」：maturityDiffNote（到期支付差额披露）",
            "",
            "期初列可引用 G10-1 审定分项；建议「分项带入」后按种类手工分拆。",
        ],
    },
}

router = create_cycle_import_export_router(
    tag="g10-import-export",
    api_prefix="g10",
    specs=_G10_SPECS,
    storage_field="remark",
)
