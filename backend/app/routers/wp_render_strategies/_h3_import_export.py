"""H3 投资性房地产 — 导入导出3端点（列结构对齐 requirements）.

POST /h3/export-template → 空白结构xlsx（根据measurement_model导出对应版本）
POST /h3/export-data → 当前数据xlsx（含公式结果）
POST /h3/import-data → 解析xlsx→验证→写入checklist_responses
"""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ─── H3-2 明细表（成本模式基本区段） ─────────────────────────────────────────

_H3_2_COST_BASE_HEADERS = [
    "资产分类", "资产名称", "资产编号", "坐落位置", "入账日期",
    "使用年限(年)", "残值率(%)", "折旧方法", "面积(㎡)", "用途",
]
_H3_2_COST_BASE_KEYS = [
    "assetCategory", "assetName", "assetCode", "location", "acquisitionDate",
    "usefulLife", "salvageRate", "depMethod", "area", "purpose",
]

# ─── H3-2 明细表（成本模式原值变动区段） ─────────────────────────────────────

_H3_2_COST_CHANGE_HEADERS = [
    "资产分类", "资产名称", "期初原值", "本期增加", "本期减少",
    "本期转换", "期末原值",
]
_H3_2_COST_CHANGE_KEYS = [
    "assetCategory", "assetName", "costOpening", "costIncrease", "costDecrease",
    "costTransfer", "costClosing",
]

# ─── H3-2 明细表（成本模式折旧区段） ────────────────────────────────────────

_H3_2_COST_DEP_HEADERS = [
    "资产分类", "资产名称", "累计折旧期初", "本期计提", "本期转回",
    "本期转换", "累计折旧期末", "净值",
]
_H3_2_COST_DEP_KEYS = [
    "assetCategory", "assetName", "depOpening", "depProvision", "depReversal",
    "depTransfer", "depClosing", "netValue",
]

# ─── H3-2 明细表（公允模式） ─────────────────────────────────────────────────

_H3_2_FAIR_HEADERS = [
    "资产分类", "资产名称", "资产编号", "坐落位置", "面积(㎡)", "用途",
    "期初公允价值", "本期增加", "本期减少", "本期转换",
    "公允价值变动", "期末公允价值",
]
_H3_2_FAIR_KEYS = [
    "assetCategory", "assetName", "assetCode", "location", "area", "purpose",
    "fairOpening", "fairIncrease", "fairDecrease", "fairTransfer",
    "fairValueChange", "fairClosing",
]

# ─── H3-3 调整分录 ──────────────────────────────────────────────────────────

_H3_3_HEADERS = [
    "序号", "调整事项说明", "类别", "报表项目", "科目代码", "科目名称",
    "附注项目", "摘要", "借方金额", "贷方金额", "对方科目", "索引", "备注",
]
_H3_3_KEYS = [
    "seq", "description", "entryType", "reportItem", "accountCode", "accountName",
    "noteItem", "summary", "debitAmount", "creditAmount", "contraAccount", "indexRef", "remark",
]

# ─── H3-5 增减检查 ──────────────────────────────────────────────────────────

_H3_5_HEADERS = [
    "序号", "资产名称", "资产编号", "变动类型", "变动日期", "金额",
    "合同/协议", "发票", "评估报告", "审批文件", "入账科目",
    "计量模式", "公允价值", "差异", "审计结论", "备注",
]
_H3_5_KEYS = [
    "seq", "assetName", "assetCode", "changeType", "changeDate", "amount",
    "contract", "invoice", "appraisalReport", "approvalDoc", "accountEntry",
    "measurementModel", "fairValue", "difference", "conclusion", "remark",
]

# ─── H3-9 盘点检查 ──────────────────────────────────────────────────────────

_H3_9_HEADERS = [
    "序号", "资产名称", "资产编号", "坐落位置", "面积(㎡)",
    "使用状况", "出租状态", "承租方", "租赁期限", "月租金",
    "盘点结果", "差异原因", "备注",
]
_H3_9_KEYS = [
    "seq", "assetName", "assetCode", "location", "area",
    "usageStatus", "rentalStatus", "tenant", "leaseTerm", "monthlyRent",
    "stocktakeResult", "diffReason", "remark",
]

# ─── H3-12 产权核对 ─────────────────────────────────────────────────────────

_H3_12_HEADERS = [
    "序号", "资产名称", "账面原值", "产权证号", "证载面积",
    "账面面积", "面积差异", "证载所有人", "是否被审计单位",
    "抵押情况", "查封情况", "使用限制", "证载用途", "实际用途",
    "用途是否一致", "备注",
]
_H3_12_KEYS = [
    "seq", "assetName", "bookValue", "titleNo", "certArea",
    "bookArea", "areaDiff", "certOwner", "isAuditee",
    "mortgage", "seizure", "restriction", "certPurpose", "actualPurpose",
    "purposeConsistent", "remark",
]

# ─── H3-13 关联交易 ─────────────────────────────────────────────────────────

_H3_13_HEADERS = [
    "序号", "关联方", "关联关系", "交易类型", "金额",
    "定价方式", "市场价参考", "差异率(%)", "审批文件",
    "审计结论", "备注",
]
_H3_13_KEYS = [
    "seq", "relatedParty", "relationship", "transType", "amount",
    "pricingMethod", "marketRef", "diffRate", "approvalDoc",
    "conclusion", "remark",
]

# ─── H3-14 租金收入测算 ─────────────────────────────────────────────────────

_H3_14_HEADERS = [
    "序号", "资产名称", "承租方", "合同期起", "合同期止",
    "面积(㎡)", "月租金", "年租金", "空置率(%)", "空置月数",
    "空置损失", "实际收入", "测算收入", "差异", "差异率(%)",
    "每平米月租", "租金回报率(%)", "合同到期月数", "续租状态", "备注",
]
_H3_14_KEYS = [
    "seq", "assetName", "tenant", "leaseStart", "leaseEnd",
    "area", "monthlyRent", "annualRent", "vacancyRate", "vacantMonths",
    "vacancyLoss", "actualIncome", "calculatedIncome", "difference", "diffRate",
    "perSqmRent", "rentalYield", "expiryMonths", "renewalStatus", "remark",
]

# ═══════════════════════════════════════════════════════════════════════════════

_H3_SPECS: dict[str, dict[str, Any]] = {
    "H3-2-cost-base": {
        "item_id": "H3-2-rows",
        "title": "H3-2 明细表（成本模式基本信息）",
        "headers": _H3_2_COST_BASE_HEADERS,
        "field_keys": _H3_2_COST_BASE_KEYS,
        "guidance": [
            "H3-2 投资性房地产明细表 — 成本模式基础区段 编制说明",
            "",
            "折旧方法：直线法。残值率通常为0%~5%。",
            "用途：出租/增值/出租+增值。",
        ],
    },
    "H3-2-cost-change": {
        "item_id": "H3-2-rows",
        "title": "H3-2 明细表（成本模式原值变动）",
        "headers": _H3_2_COST_CHANGE_HEADERS,
        "field_keys": _H3_2_COST_CHANGE_KEYS,
        "guidance": [
            "H3-2 原值变动区段 编制说明",
            "",
            "期末原值=期初原值+增加-减少+转换（资产类借方科目1503）。",
            "转换含自用→投资/在建→投资的原值部分。",
        ],
    },
    "H3-2-cost-dep": {
        "item_id": "H3-2-rows",
        "title": "H3-2 明细表（成本模式折旧）",
        "headers": _H3_2_COST_DEP_HEADERS,
        "field_keys": _H3_2_COST_DEP_KEYS,
        "guidance": [
            "H3-2 折旧区段 编制说明",
            "",
            "累计折旧期末=期初+本期计提-本期转回+转换（备抵类贷方科目1504）。",
            "净值=期末原值-累计折旧期末。",
        ],
    },
    "H3-2-fair": {
        "item_id": "H3-2-fair-rows",
        "title": "H3-2 明细表（公允价值模式）",
        "headers": _H3_2_FAIR_HEADERS,
        "field_keys": _H3_2_FAIR_KEYS,
        "guidance": [
            "H3-2 公允价值模式明细表 编制说明",
            "",
            "期末公允=期初+增加-减少+转换+公允价值变动。",
            "公允价值模式不计提折旧和减值。",
        ],
    },
    "H3-3": {
        "item_id": "H3-3-rows",
        "title": "H3-3 调整分录汇总表",
        "headers": _H3_3_HEADERS,
        "field_keys": _H3_3_KEYS,
        "guidance": [
            "H3-3 调整分录 编制说明",
            "",
            "类别填 AJE（审计调整分录）或 RJE（重分类调整分录）。",
            "借方合计应等于贷方合计（借贷平衡）。",
        ],
    },
    "H3-5": {
        "item_id": "H3-5-rows",
        "title": "H3-5 增减检查表",
        "headers": _H3_5_HEADERS,
        "field_keys": _H3_5_KEYS,
        "guidance": [
            "H3-5 投资性房地产增减检查 编制说明",
            "",
            "变动类型：增加(购入/自建/转换转入)/减少(出售/转换转出/报废)。",
            "公允价值模式需记录公允价值及差异。",
        ],
    },
    "H3-9": {
        "item_id": "H3-9-rows",
        "title": "H3-9 盘点检查表",
        "headers": _H3_9_HEADERS,
        "field_keys": _H3_9_KEYS,
        "guidance": [
            "H3-9 投资性房地产盘点 编制说明",
            "",
            "出租状态：已出租/空置/部分出租。",
            "重点关注空置资产的减值迹象。",
        ],
    },
    "H3-12": {
        "item_id": "H3-12-rows",
        "title": "H3-12 产权核对表",
        "headers": _H3_12_HEADERS,
        "field_keys": _H3_12_KEYS,
        "guidance": [
            "H3-12 投资性房地产产权核对 编制说明",
            "",
            "面积差异=证载面积-账面面积。",
            "证载所有人非被审计单位时标记权属异常。",
        ],
    },
    "H3-13": {
        "item_id": "H3-13-rows",
        "title": "H3-13 关联交易检查表",
        "headers": _H3_13_HEADERS,
        "field_keys": _H3_13_KEYS,
        "guidance": [
            "H3-13 投资性房地产关联交易 编制说明",
            "",
            "差异率=(金额-市场价)/市场价×100%。",
            "差异率>10%时需重点关注定价合理性。",
        ],
    },
    "H3-14": {
        "item_id": "H3-14-rows",
        "title": "H3-14 租金收入测算表",
        "headers": _H3_14_HEADERS,
        "field_keys": _H3_14_KEYS,
        "guidance": [
            "H3-14 租金收入测算 编制说明",
            "",
            "年租金=月租×12×(1-空置率)。每平米月租=月租/面积。",
            "租金回报率=年租金/账面原值×100%。",
            "差异率=(实际收入-测算收入)/测算收入×100%。",
            "合同到期月数≤3时标注'即将到期'。",
        ],
    },
}

router = create_cycle_import_export_router(tag="h3-import-export", api_prefix="h3", specs=_H3_SPECS)
