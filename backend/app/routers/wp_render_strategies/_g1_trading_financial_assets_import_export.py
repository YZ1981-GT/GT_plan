"""G1 交易性金融资产 — 导入导出（列结构对齐 requirements + composable field keys）.

支持 10 张动态行表格：
  G1-2 明细表(35列/5区段) / G1-3 调整分录 / G1-4 结存表 / G1-5 收益测算 /
  G1-6 公允价值测试 / G1-7 第三层次调节 / G1-11 监盘 / G1-12 倒轧 /
  G1-13 检查表 / G1-14 衍生工具核查

字段键与前端 composable（useG1Detail/useG1Inventory/... 的行接口）严格对齐，保证 round-trip。
宽表（G1-2 35列 / G1-12 18列 / G1-4 21列 / G1-5 18列）导出为单 sheet 宽表，
表头区段前缀（[基础]/[持有]/[公允]/[损益]/[审定]）标注 5 区段归属。
"""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ── 调整分录（G1-3，借贷平衡）──
_ADJ_HEADERS = ["序号", "分录类型", "日期", "摘要", "科目代码", "科目名称", "借方金额", "贷方金额", "编制人", "备注"]
_ADJ_KEYS = ["seq", "entryType", "date", "summary", "accountCode", "accountName", "debit", "credit", "preparer", "remark"]

# ── G1-2 明细表（35列，5区段，宽表）──
_G1_2_HEADERS = [
    # 基础信息(7)
    "序号", "投资品种名称", "证券代码", "投资类型", "交易市场", "初始取得日期", "初始取得成本",
    # 持有明细(7)
    "期初持有数量", "本期买入数量", "本期卖出数量", "期末持有数量", "期初成本", "本期增加成本", "本期减少成本",
    # 公允价值(7)
    "期末单位公允值", "期末公允价值", "公允价值来源", "期初公允价值", "公允价值变动", "累计公允变动", "报价日期",
    # 损益(7)
    "本期处置收入", "处置成本", "已实现损益", "利息股利收入", "投资收益合计", "公允变动损益", "备注",
    # 审定调整(7)
    "期末成本", "未审余额", "AJE", "RJE", "审定余额", "差异", "索引",
]
_G1_2_KEYS = [
    "seq", "securityName", "securityCode", "investType", "market", "acquisitionDate", "initialCost",
    "openingQuantity", "boughtQuantity", "soldQuantity", "closingQuantity", "openingCost", "addedCost", "reducedCost",
    "unitFairValue", "closingFairValue", "fairValueSource", "openingFairValue", "fairValueChange", "cumulativeFVChange", "quoteDate",
    "disposalProceeds", "disposalCost", "realizedGain", "dividendIncome", "totalIncome", "fvChangeInPL", "remark",
    "closingCost", "unadjusted", "aje", "rje", "adjusted", "variance", "indexRef",
]

# ── G1-4 结存表（21列，宽表）──
_G1_4_HEADERS = [
    "序号", "证券名称", "代码", "类型",
    "期初数量", "期初成本", "期初公允",
    "增加数量", "增加成本",
    "减少数量", "减少成本", "处置收入",
    "期末数量", "期末成本", "期末公允", "未实现损益",
]
_G1_4_KEYS = [
    "seq", "securityName", "securityCode", "securityType",
    "openingQuantity", "openingCost", "openingFairValue",
    "addQuantity", "addCost",
    "reduceQuantity", "reduceCost", "disposalProceeds",
    "closingQuantity", "closingCost", "closingFairValue", "unrealizedGain",
]

# ── G1-5 收益测算（18列 = 投资收益9 + 处置损益9，宽表）──
_G1_5_HEADERS = [
    "序号", "证券名称",
    "持有数量", "每股股利/利率", "应收金额", "实收金额", "差异", "确认日期", "来源", "收益备注",
    "卖出数量", "成交价", "成交金额", "原始成本", "处置损益", "手续费", "净损益", "处置备注",
]
_G1_5_KEYS = [
    "seq", "securityName",
    "holdingQuantity", "dividendPerShare", "receivableAmount", "receivedAmount", "incomeDiff", "confirmDate", "incomeSource", "incomeRemark",
    "soldQuantity", "dealPrice", "dealAmount", "originalCost", "realizedGain", "fee", "netGain", "disposalRemark",
]

# ── G1-6 公允价值测试（19列，Level1-3）──
_G1_6_HEADERS = [
    "序号", "证券名称", "代码", "持仓数量", "期末账面值", "Level层级",
    "报价日期", "报价来源", "报价值", "计算市值", "Level1差异",
    "可观察输入描述", "估值方法", "Level2估值结果", "Level2差异",
    "不可观察输入", "估值假设", "Level3估值结果", "Level3差异",
    "结论", "备注",
]
_G1_6_KEYS = [
    "seq", "securityName", "securityCode", "quantity", "bookValue", "fvLevel",
    "quoteDate", "quoteSource", "quoteValue", "marketValue", "level1Diff",
    "observableDesc", "valuationMethod", "level2Result", "level2Diff",
    "unobservableInput", "assumption", "level3Result", "level3Diff",
    "conclusion", "remark",
]

# ── G1-7 第三层次调节（13列）──
_G1_7_HEADERS = [
    "序号", "项目名称", "期初余额", "本期增加·新确认", "本期增加·转入",
    "本期减少·终止确认", "本期减少·转出", "本期公允变动", "期末余额", "累计变动",
    "估值方法", "关键假设", "敏感性分析", "审计评价", "备注",
]
_G1_7_KEYS = [
    "seq", "itemName", "openingBalance", "addNewRecognition", "addTransferIn",
    "reduceDerecognition", "reduceTransferOut", "fairValueChange", "closingBalance", "cumulativeChange",
    "valuationMethod", "keyAssumption", "sensitivity", "auditEval", "remark",
]

# ── G1-11 有价证券监盘（10列）──
_G1_11_HEADERS = [
    "序号", "证券名称", "代码", "类型", "账面数量", "盘点数量", "差异", "差异原因", "保管机构", "监盘日期",
]
_G1_11_KEYS = [
    "seq", "securityName", "securityCode", "securityType", "bookedQuantity", "countedQuantity", "countDiff", "diffReason", "custodian", "countDate",
]

# ── G1-12 盘点倒轧（18列，宽表）──
_G1_12_HEADERS = [
    "序号", "证券名称",
    "监盘日余额·数量", "监盘日余额·金额", "增加·数量", "增加·金额", "减少·数量", "减少·金额",
    "推算余额·数量", "推算余额·金额", "账面余额·数量", "账面余额·金额", "差异·数量", "差异·金额", "结论",
]
_G1_12_KEYS = [
    "seq", "securityName",
    "countDayQuantity", "countDayAmount", "increaseQuantity", "increaseAmount", "decreaseQuantity", "decreaseAmount",
    "derivedQuantity", "derivedAmount", "bookQuantity", "bookAmount", "diffQuantity", "diffAmount", "conclusion",
]

# ── G1-13 检查表（17列，凭证核对）──
_G1_13_HEADERS = [
    "序号", "凭证日期", "凭证号", "摘要", "证券名称", "投资类型", "金额", "对方科目",
    "合同核对", "结算单核对", "报价/估值核对", "授权审批核对", "账务处理核对", "审计结论", "附件", "备注", "抽凭来源",
]
_G1_13_KEYS = [
    "seq", "voucherDate", "voucherNo", "summary", "securityName", "investType", "amount", "counterAccount",
    "contractCheck", "settlementCheck", "quoteCheck", "approvalCheck", "bookkeepingCheck", "auditConclusion", "attachment", "remark", "sampleSource",
]

# ── G1-14 衍生金融工具核查（10列）──
_G1_14_HEADERS = [
    "序号", "工具名称", "类型", "名义金额", "期限", "对手方", "保证金", "是否套期", "会计处理适当性", "合规结论",
]
_G1_14_KEYS = [
    "seq", "instrumentName", "instrumentType", "notionalAmount", "term", "counterparty", "margin", "isHedging", "accountingAppropriateness", "complianceConclusion",
]


_G1_SPECS: dict[str, dict[str, Any]] = {
    "G1-2": {
        "item_id": "G1-2-rows",
        "title": "G1-2 交易性金融资产明细表（35列/5区段）",
        "headers": _G1_2_HEADERS,
        "field_keys": _G1_2_KEYS,
        "guidance": [
            "G1-2 明细表 编制说明",
            "",
            "35列对应 HTML 底稿 5 区段Tab（基础信息/持有明细/公允价值/损益/审定调整），此处合并为宽表。",
            "公式列（期末持有数量/期末公允价值/公允价值变动/已实现损益/投资收益合计/期末成本/审定余额）导入后前端自动重算。",
            "投资类型填：股票/基金/债券/衍生/其他（stock/fund/bond/derivative/other）；公允价值来源填 1/2/3（Level）。",
        ],
    },
    "G1-3": {
        "item_id": "G1-3-rows",
        "title": "G1-3 交易性金融资产调整分录",
        "headers": _ADJ_HEADERS,
        "field_keys": _ADJ_KEYS,
        "guidance": ["G1-3 调整分录 编制说明", "", "分录类型填 AJE 或 RJE；每张凭证借贷方金额必须相等。"],
    },
    "G1-4": {
        "item_id": "G1-4-rows",
        "title": "G1-4 结存表（21列）",
        "headers": _G1_4_HEADERS,
        "field_keys": _G1_4_KEYS,
        "guidance": [
            "G1-4 结存表 编制说明",
            "",
            "期末数量=期初+增加-减少；期末成本=期初成本+增加成本-减少成本；未实现损益=期末公允-期末成本。",
        ],
    },
    "G1-5": {
        "item_id": "G1-5-rows",
        "title": "G1-5 收益测算表（18列/2区段）",
        "headers": _G1_5_HEADERS,
        "field_keys": _G1_5_KEYS,
        "guidance": [
            "G1-5 收益测算 编制说明",
            "",
            "应收金额=持有数量×每股股利；处置损益=成交金额-原始成本；净损益=处置损益-手续费。",
        ],
    },
    "G1-6": {
        "item_id": "G1-6-rows",
        "title": "G1-6 公允价值测试表（Level1-3）",
        "headers": _G1_6_HEADERS,
        "field_keys": _G1_6_KEYS,
        "guidance": [
            "G1-6 公允价值测试 编制说明",
            "",
            "Level层级填 1/2/3；Level1：计算市值=持仓×报价，差异=市值-账面；Level2/3：差异=估值结果-账面。",
            "|差异|>1%×账面值时前端橙色高亮。",
        ],
    },
    "G1-7": {
        "item_id": "G1-7-rows",
        "title": "G1-7 第三层次调节表（13列）",
        "headers": _G1_7_HEADERS,
        "field_keys": _G1_7_KEYS,
        "guidance": ["G1-7 第三层次调节 编制说明", "", "期末余额=期初+增加(新确认+转入)-减少(终止确认+转出)+本期公允变动。"],
    },
    "G1-11": {
        "item_id": "G1-11-rows",
        "title": "G1-11 有价证券监盘表",
        "headers": _G1_11_HEADERS,
        "field_keys": _G1_11_KEYS,
        "guidance": ["G1-11 监盘表 编制说明", "", "盘点差异=盘点数量-账面数量；|差异|>0 前端橙色高亮。"],
    },
    "G1-12": {
        "item_id": "G1-12-rows",
        "title": "G1-12 盘点倒轧表（18列/2区段）",
        "headers": _G1_12_HEADERS,
        "field_keys": _G1_12_KEYS,
        "guidance": ["G1-12 盘点倒轧 编制说明", "", "推算余额=监盘日余额+增加-减少；倒轧差异=推算余额-账面余额。"],
    },
    "G1-13": {
        "item_id": "G1-13-rows",
        "title": "G1-13 检查表（凭证核对，17列）",
        "headers": _G1_13_HEADERS,
        "field_keys": _G1_13_KEYS,
        "guidance": ["G1-13 检查表 编制说明", "", "凭证核对逐笔检查；可通过抽凭引擎自动填入样本（抽凭来源列标注）。"],
    },
    "G1-14": {
        "item_id": "G1-14-rows",
        "title": "G1-14 衍生金融工具核查表",
        "headers": _G1_14_HEADERS,
        "field_keys": _G1_14_KEYS,
        "guidance": [
            "G1-14 衍生工具核查 编制说明",
            "",
            "类型填 option/futures/swap/forward（期权/期货/互换/远期）；会计处理适当性填 appropriate/inappropriate/needs-review。",
        ],
    },
}

router = create_cycle_import_export_router(tag="g1-import-export", api_prefix="g1", specs=_G1_SPECS)
