"""I3 商誉 — 导入导出3端点（列结构对齐 Excel 双表滚动 + A/B1/B2 粗化）.

POST /i3/export-template → 空白结构xlsx
POST /i3/export-data → 当前数据xlsx
POST /i3/import-data → 解析xlsx→验证→写入checklist_responses

动态行: I3-2(原值/减值滚动), I3-3, I3-4, I3-6(粗化分摊), I3-7(DCF)
兼容旧表头别名（30列三区段 / 旧减值列）。
"""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ─── I3-1 审定表 ──────────────────────────────────────────────────────────────

_I3_1_HEADERS = [
    "被投资单位", "初始确认", "期初余额", "本期增加(新并购)", "本期减少(减值)",
    "期末余额", "未审数", "AJE", "RJE", "审定数", "减值准备", "净额",
]
_I3_1_KEYS = [
    "investee", "initialRecognition", "openingBalance", "newAcquisition", "impairment",
    "closingBalance", "unadjusted", "aje", "rje", "audited", "impairmentReserve", "netValue",
]

# ─── I3-2 明细表（原值滚动 + 减值滚动 + 入账/基础，单表多列） ─────────────────

_I3_2_HEADERS = [
    "被投资单位", "所属CGU",
    # 原值滚动
    "原值期初", "原值本期增加", "增加方式", "原值本期减少", "减少原因",
    "原值期末", "原值未审", "原值账项调整", "原值审定",
    # 减值滚动
    "减值期初", "本期计提", "计提方式", "减值本期减少", "减值减少原因",
    "减值期末", "减值未审", "减值账项调整", "减值审定", "商誉净值",
    # 入账测算
    "合并成本", "可辨认净资产公允份额", "测算商誉原值",
    # 基础
    "并购日期", "合并方式", "持股比例", "备注",
]
_I3_2_KEYS = [
    "investee", "cguName",
    "costOpening", "costIncrease", "costIncreaseMethod", "costDecrease", "costDecreaseReason",
    "costEnding", "costUnadj", "costAje", "costAudited",
    "impOpening", "impIncrease", "impIncreaseMethod", "impDecrease", "impDecreaseReason",
    "impEnding", "impUnadj", "impAje", "impAudited", "goodwillNetValue",
    "mergerCost", "netAssetFairValue", "entryGoodwillCalc",
    "acquisitionDate", "mergerType", "shareholding", "basicRemark",
]

# 旧表头 → 规范表头（导入兼容）
_I3_2_ALIASES: dict[str, list[str]] = {
    "被投资单位": ["被投资单位名称", "形成商誉的事项", "项目名称", "子公司名称"],
    "所属CGU": ["CGU", "资产组", "所属资产组", "资产组名称"],
    "原值期初": ["商誉原值", "期初数", "原值期初数", "期初原值", "goodwillOriginal"],
    "原值本期增加": ["本期增加", "本期增加金额", "本期新增商誉"],
    "增加方式": ["增加原因", "增加方式/原因"],
    "原值本期减少": ["本期减少", "本期减少金额", "原值减少"],
    "减少原因": ["原值减少原因"],
    "原值期末": ["期末数", "原值期末数", "期末原值"],
    "原值未审": ["未审数", "未审期末", "原值未审数"],
    "原值账项调整": ["账项调整", "AJE", "原值AJE", "costAje"],
    "原值审定": ["审定数", "审定期末", "原值审定数", "costAudited"],
    "减值期初": ["累计减值期初", "累计减值", "减值准备期初", "accImpairmentBegin"],
    "本期计提": ["本期减值", "本期增加(计提)", "currentImpairment", "本期计提减值"],
    "计提方式": ["减值增加方式", "计提原因"],
    "减值本期减少": ["减值减少", "本期转出减值", "处置转出"],
    "减值减少原因": ["转出原因"],
    "减值期末": ["累计减值期末", "减值准备期末", "accImpairmentEnd"],
    "减值未审": ["减值未审数", "未审减值"],
    "减值账项调整": ["减值AJE", "impAje", "减值准备账项调整"],
    "减值审定": ["累计减值期末审定", "减值准备审定", "impAudited"],
    "商誉净值": ["期末净额", "净值", "goodwillNetValue", "netValueEnd"],
    "合并成本": ["合并成本合计", "mergerCost"],
    "可辨认净资产公允份额": ["可辨认净资产公允", "被购方净资产公允价值", "netAssetFairValue"],
    "测算商誉原值": ["商誉", "入账商誉", "entryGoodwillCalc"],
    "并购日期": ["购买日", "合并日", "acquisitionDate"],
    "合并方式": ["企业合并方式", "mergerType"],
    "持股比例": ["股权比例", "shareholding"],
    "备注": ["说明", "basicRemark", "remark"],
}

# ─── I3-3 调整分录（含被投资单位，便于回写 I3-2） ───────────────────────────

_I3_3_HEADERS = [
    "序号", "调整事项", "被投资单位", "类别", "科目代码", "科目名称",
    "摘要", "借方金额", "贷方金额", "索引", "备注",
]
_I3_3_KEYS = [
    "seq", "description", "investee", "entryType", "accountCode", "accountName",
    "summary", "debitAmount", "creditAmount", "indexRef", "remark",
]
_I3_3_ALIASES: dict[str, list[str]] = {
    "被投资单位": ["投资单位", "CGU", "资产组", "子公司"],
    "类别": ["entryType", "AJE/RJE"],
    "调整事项": ["调整事项说明", "说明"],
}

# ─── I3-4 入账价值测算 ──────────────────────────────────────────────────────

_I3_4_HEADERS = [
    "被投资单位", "合并成本", "对价形式", "或有对价", "交易费用",
    "被购方可辨认净资产公允", "少数股东权益", "商誉", "确认日期", "备注",
]
_I3_4_KEYS = [
    "investee", "mergerCost", "considerationType", "contingentConsideration", "transactionCosts",
    "identifiableNetAssetFV", "minorityInterest", "goodwillAmount", "recognitionDate", "remark",
]
_I3_4_ALIASES: dict[str, list[str]] = {
    "商誉": ["商誉金额", "goodwill"],
    "被购方可辨认净资产公允": ["可辨认净资产公允", "netAssetFairValue"],
}

# ─── I3-6 减值测试（A/B1/B2 粗化 + 合并确认） ────────────────────────────────

_I3_6_HEADERS = [
    "CGU名称", "A资产组账面", "B1母公司商誉", "B2少数股东商誉", "合计A+B1+B2",
    "公允减处置费", "使用价值", "可收回金额", "减值准备",
    "商誉分摊(全额)", "合并确认商誉减值", "其他资产分摊", "减值原因",
]
_I3_6_KEYS = [
    "cguName", "assetGroupCarrying", "goodwillB1", "minorityB2", "cguBookValue",
    "fairValueLessCost", "valueInUse", "recoverableAmount", "impairmentAmount",
    "goodwillImpairment", "consolidatedGwImpairment", "otherAssetImpairment", "impairmentReason",
]
_I3_6_ALIASES: dict[str, list[str]] = {
    "CGU名称": ["资产组名称", "项目名称", "cguName"],
    "B1母公司商誉": ["包含商誉", "商誉账面", "goodwillAmount", "goodwillBookValue"],
    "A资产组账面": ["资产组其他资产账面", "otherAssetsBookValue"],
    "合计A+B1+B2": ["资产组账面(含商誉)", "totalBookValue", "cguBookValue"],
    "合并确认商誉减值": ["商誉分摊减值", "goodwillImpairment"],
    "其他资产分摊": ["其他资产分摊减值", "otherAssetsImpairment"],
    "使用价值": ["DCF使用价值", "valueInUse"],
    "公允减处置费": ["公允价值减处置费用", "fairValueLessDisposal"],
}

# ─── I3-7 可收回金额测试 ─────────────────────────────────────────────────────

_I3_7_HEADERS = [
    "CGU名称", "预测年份", "营业收入", "营业成本", "营业利润",
    "所得税", "折旧摊销", "资本支出", "营运资金变动", "自由现金流",
    "折现率(WACC)", "折现因子", "现值", "永续增长率", "终值", "终值现值",
    "公允减处置费", "使用价值", "可收回金额",
]
_I3_7_KEYS = [
    "cguName", "forecastYear", "revenue", "costOfGoods", "operatingProfit",
    "incomeTax", "depreciation", "capex", "workingCapitalChange", "freeCashFlow",
    "waccRate", "discountFactor", "presentValue", "growthRate", "terminalValue", "terminalValuePV",
    "fairValueLessCost", "valueInUse", "recoverableAmount",
]

# ═══════════════════════════════════════════════════════════════════════════════

_I3_SPECS: dict[str, dict[str, Any]] = {
    "I3-1": {
        # 与前端 i3AdjudicationModel.I3_ADJ_ROWS_KEY 对齐；旧键镜像写入兼容
        "item_id": "I3-adj-rows",
        "mirror_item_ids": ["I3-1-adj-rows"],
        "item_id_candidates": ["I3-adj-rows", "I3-1-adj-rows", "I3-1-rows"],
        "title": "审定表I3-1（商誉不摊销！期末=期初+新并购-减值）",
        "headers": _I3_1_HEADERS,
        "field_keys": _I3_1_KEYS,
        "allow_missing_headers": True,
        "dual_write": True,
        "storage_field": "remark",
        "guidance": [
            "I3-1 商誉审定表 编制说明",
            "",
            "商誉不摊销！期末余额=期初+本期增加(新并购)-本期减少(减值)。",
            "本期减少仅来自减值（商誉减值不可转回！）。",
            "审定数=未审+AJE+RJE。净额=原值-累计减值。",
            "存储键：I3-adj-rows（兼容旧键 I3-1-adj-rows）。",
        ],
    },
    "I3-2": {
        "item_id": "I3-2-rows",
        "title": "I3-2 商誉明细表（原值/减值双表滚动）",
        "headers": _I3_2_HEADERS,
        "field_keys": _I3_2_KEYS,
        "header_aliases": _I3_2_ALIASES,
        "allow_missing_headers": True,
        "dual_write": True,
        "storage_field": "remark",
        "guidance": [
            "I3-2 商誉明细表 编制说明",
            "",
            "原值滚动：期末=期初+本期增加−本期减少；审定=未审+账项调整。",
            "减值滚动：同期结构；本期计提对接 I3-6 合并确认商誉减值。",
            "净值=原值审定−减值审定（商誉不摊销）。",
            "所属CGU 须与 I3-6/I3-7 名称一致以便跨表联动。",
            "旧模板「商誉原值/累计减值/本期减值」列可通过别名导入为滚动字段。",
        ],
    },
    # 兼容旧前端分段导出编码
    "I3-2-base": {
        "item_id": "I3-2-rows",
        "title": "I3-2 明细表（兼容-基础，建议改用 I3-2）",
        "headers": _I3_2_HEADERS,
        "field_keys": _I3_2_KEYS,
        "header_aliases": _I3_2_ALIASES,
        "allow_missing_headers": True,
        "dual_write": True,
        "storage_field": "remark",
        "guidance": ["已合并至 I3-2 统一滚动模板，本编码仅兼容旧调用。"],
    },
    "I3-2-entry": {
        "item_id": "I3-2-rows",
        "title": "I3-2 明细表（兼容-入账，建议改用 I3-2）",
        "headers": _I3_2_HEADERS,
        "field_keys": _I3_2_KEYS,
        "header_aliases": _I3_2_ALIASES,
        "allow_missing_headers": True,
        "dual_write": True,
        "storage_field": "remark",
        "guidance": ["已合并至 I3-2 统一滚动模板。"],
    },
    "I3-2-impair": {
        "item_id": "I3-2-rows",
        "title": "I3-2 明细表（兼容-减值，建议改用 I3-2）",
        "headers": _I3_2_HEADERS,
        "field_keys": _I3_2_KEYS,
        "header_aliases": _I3_2_ALIASES,
        "allow_missing_headers": True,
        "dual_write": True,
        "storage_field": "remark",
        "guidance": ["已合并至 I3-2 统一滚动模板。"],
    },
    "I3-3": {
        "item_id": "I3-3-rows",
        "title": "I3-3 调整分录汇总表",
        "headers": _I3_3_HEADERS,
        "field_keys": _I3_3_KEYS,
        "header_aliases": _I3_3_ALIASES,
        "allow_missing_headers": True,
        "dual_write": True,
        "storage_field": "remark",
        "guidance": [
            "I3-3 调整分录 编制说明",
            "",
            "类别填 AJE（审计调整）或 RJE（重分类）；借贷须平衡。",
            "请填写「被投资单位」以便回写 I3-2 原值/减值账项调整列。",
            "商誉减值：借记资产减值损失，贷记商誉（或减值准备）。",
        ],
    },
    "I3-4": {
        "item_id": "I3-4-rows",
        "title": "I3-4 入账价值测算表",
        "headers": _I3_4_HEADERS,
        "field_keys": _I3_4_KEYS,
        "header_aliases": _I3_4_ALIASES,
        "allow_missing_headers": True,
        "dual_write": True,
        "storage_field": "remark",
        "guidance": [
            "I3-4 入账价值测算 编制说明",
            "",
            "商誉=合并成本-被购方可辨认净资产公允价值份额。",
            "仅非同一控制下企业合并产生商誉；可回写 I3-2 本期增加。",
        ],
    },
    "I3-6": {
        "item_id": "I3-6-rows",
        "title": "I3-6 商誉减值测试（A/B1/B2粗化+合并确认）",
        "headers": _I3_6_HEADERS,
        "field_keys": _I3_6_KEYS,
        "header_aliases": _I3_6_ALIASES,
        "allow_missing_headers": True,
        "dual_write": True,
        "storage_field": "remark",
        "guidance": [
            "I3-6 商誉减值测试 编制说明",
            "",
            "账面价值(1)=A+B1+B2（含未确认少数股东商誉粗化）。",
            "可收回金额(2)=MAX(公允减处置费, 使用价值)；可从 I3-7 同步。",
            "减值准备=MAX((1)-(2),0)；先冲全额商誉(B1+B2)，再分摊其他资产。",
            "合并报表确认=商誉分摊×B1/(B1+B2)；回写 I3-1/I3-2 用合并确认数。",
            "商誉减值不可转回。",
        ],
    },
    "I3-7": {
        "item_id": "I3-7-rows",
        "title": "I3-7 可收回金额测试（DCF）",
        "headers": _I3_7_HEADERS,
        "field_keys": _I3_7_KEYS,
        "allow_missing_headers": True,
        "dual_write": True,
        "storage_field": "remark",
        "guidance": [
            "I3-7 可收回金额测试 编制说明",
            "",
            "可收回金额=MAX(公允价值-处置费用, 使用价值DCF)。",
            "CGU名称须与 I3-6 一致以便同步。",
        ],
    },
}

router = create_cycle_import_export_router(tag="i3-import-export", api_prefix="i3", specs=_I3_SPECS)
