"""H4 工程物资 — 导入导出3端点（列结构对齐 requirements）.

POST /h4/export-template → 空白结构xlsx（根据sheet_name导出对应表模板）
POST /h4/export-data → 当前数据xlsx（含已填数据）
POST /h4/import-data → 解析xlsx→验证→写入checklist_responses

支持sheets: H4-2/H4-3/H4-4/H4-5/H4-6/H4-9
科目编码: 1605工程物资（借方/资产类）

Requirements: 3.8, 4.6
"""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ─── H4-2 明细表（对齐 C4：未审原值 + 调整 + 减值净值；字段与前端 useH4Detail 一致） ──

_H4_2_HEADERS = [
    "物资分类", "名称", "规格", "单位", "供应商",
    "期初数量", "增加数量", "减少数量",
    "期初金额", "本期采购", "其他增加",
    "领用出库", "退货", "报废", "其他减少",
    "AJE期初", "AJE增加", "AJE减少",
    "跌价期初", "本期计提", "本期转销", "AJE减值",
    "库龄", "品质",
]
_H4_2_KEYS = [
    "category", "name", "spec", "unit", "supplier",
    "beginQty", "increaseQty", "decreaseQty",
    "beginAmount", "purchaseAmount", "otherIncrease",
    "usageAmount", "returnAmount", "scrapAmount", "otherDecrease",
    "ajeBegin", "ajeIncrease", "ajeDecrease",
    "impairBegin", "impairIncrease", "impairDecrease", "ajeImpair",
    "aging", "quality",
]

# ─── H4-3 调整分录汇总 ─────────────────────────────────────────────────────

_H4_3_HEADERS = [
    "调整事项说明", "类别", "报表项目", "科目代码", "科目名称",
    "附注项目", "借方调整金额", "贷方调整金额", "索引", "备注",
]
_H4_3_KEYS = [
    "description", "category", "reportItem", "accountCode", "accountName",
    "noteItem", "debitAmount", "creditAmount", "indexRef", "remark",
]

# ─── H4-4 增加检查表 ───────────────────────────────────────────────────────

_H4_4_HEADERS = [
    "工程物资类别", "工程物资名称", "凭证日期", "凭证编号", "业务内容",
    "对方科目", "对方明细科目", "借方金额", "支持性文件",
    "供应商", "发票金额",
    "核对1", "核对2", "核对3", "核对4", "核对5",
    "索引号", "是否异常", "是否关联方", "关联方名称", "关联关系", "备注说明",
]
_H4_4_KEYS = [
    "category", "name", "voucherDate", "voucherNo", "businessContent",
    "oppositeAccount", "oppositeDetail", "amount", "supportingDocs",
    "supplier", "invoiceAmount",
    "check1", "check2", "check3", "check4", "check5",
    "indexRef", "isAbnormal", "isRelatedParty", "relatedPartyName", "relationship", "remark",
]

# ─── H4-5 减少检查表 ───────────────────────────────────────────────────────

_H4_5_HEADERS = [
    "工程物资类别", "工程物资名称", "入账凭证号", "减少方式", "对方科目", "数量",
    "原值", "减值准备", "净值", "清理费用", "清理收入", "清理净损益",
    "支持性文件", "对应H2编号",
    "核对1", "核对2", "核对3", "核对4", "核对5",
    "索引号", "是否异常", "是否关联方", "关联方名称", "关联关系", "备注说明",
]
_H4_5_KEYS = [
    "category", "name", "voucherNo", "disposalMethod", "oppositeAccount", "quantity",
    "originalCost", "impairment", "netValue", "disposalCost", "disposalIncome", "disposalNetPl",
    "supportingDocs", "h2Ref",
    "check1", "check2", "check3", "check4", "check5",
    "indexRef", "isAbnormal", "isRelatedParty", "relatedPartyName", "relationship", "remark",
]

# ─── H4-6 盘点检查表 ───────────────────────────────────────────────────────

_H4_6_HEADERS = [
    "抽盘方向", "物资名称", "资产编号", "规格型号", "单位",
    "账面数量", "账面金额", "企业盘点数量", "抽盘数量",
    "品质状况", "存放位置", "差异原因", "盘点结果", "备注",
]
_H4_6_KEYS = [
    "direction", "name", "assetNo", "spec", "unit",
    "bookQty", "bookAmount", "clientCountQty", "sampleQty",
    "qualityStatus", "location", "diffReason", "result", "remark",
]

# ─── H4-9 关联交易检查表 ───────────────────────────────────────────────────

_H4_9_HEADERS = [
    "交易类型", "关联单位名称", "关联方关系", "资产类别", "工程物资名称",
    "交易金额", "入账价值", "出售原值", "减值准备", "公允评估价值",
    "交易时间", "定价政策", "是否异常", "审批文件", "核查结论", "备注", "索引号",
]
_H4_9_KEYS = [
    "transType", "counterparty", "relationship", "assetCategory", "name",
    "transAmount", "bookValue", "originalCost", "impairment", "appraisedValue",
    "transDate", "pricingPolicy", "hasAnomaly", "approvalDoc", "conclusion", "remark", "indexRef",
]

# ═══════════════════════════════════════════════════════════════════════════════

_H4_SPECS: dict[str, dict[str, Any]] = {
    "H4-2": {
        "item_id": "H4-2-rows",
        "title": "H4-2 工程物资明细表",
        "headers": _H4_2_HEADERS,
        "field_keys": _H4_2_KEYS,
        "guidance": [
            "H4-2 工程物资明细表 编制说明（对齐致同源模板）",
            "",
            "未审原值：期末=期初+采购+其他增加-领用-退货-报废-其他减少；数量同口径 rollforward。",
            "单价=金额÷数量；数量为0时前端显示「—」，避免 #DIV/0!。",
            "AJE 列录入核实调整后得审定原值；跌价准备 rollforward 后净值=原值-跌价。",
            "增加/减少分项供 H4-4/H4-5 带入总体；领用出库联动 H2 在建工程。",
        ],
    },
    "H4-3": {
        "item_id": "H4-3-rows",
        "title": "H4-3 调整分录汇总表",
        "headers": _H4_3_HEADERS,
        "field_keys": _H4_3_KEYS,
        "guidance": [
            "H4-3 调整分录汇总 编制说明（对齐致同 Excel）",
            "",
            "类别填：账项调整 / 报表调整 / 其他（账项→AJE影响审定；报表→RJE仅列报）。",
            "仅列示与工程物资相关的审计调整；一笔完整分录通常多行（1605+对方科目）。",
            "借方调整金额合计应等于贷方调整金额合计（借贷平衡）。",
            "索引交叉引用 H4-4/5/6/7/8/9 等来源底稿。",
        ],
    },
    "H4-4": {
        "item_id": "H4-4-rows",
        "title": "H4-4 增加检查表",
        "headers": _H4_4_HEADERS,
        "field_keys": _H4_4_KEYS,
        "guidance": [
            "H4-4 工程物资增加检查 编制说明（致同五段式）",
            "",
            "一审计目标→二样本选取→三测试（记账凭证六列+核对1-5）→检查比例→说明/结论。",
            "检查比例=样本借方合计/本期新增总体（总体为0时不除零）；总体宜勾稽H4-2本期增加。",
            "核对内容1-5：凭证齐全、账证相符、处理正确、截止、入库单/发票/合同三方一致。",
            "差异=借方金额-发票金额（平台增强），有发票且差异≠0时需说明原因。",
        ],
    },
    "H4-5": {
        "item_id": "H4-5-rows",
        "title": "H4-5 减少检查表",
        "headers": _H4_5_HEADERS,
        "field_keys": _H4_5_KEYS,
        "guidance": [
            "H4-5 工程物资减少检查 编制说明（致同五段式）",
            "",
            "减少方式：领用出库/退货/报废/盘亏/出售/其他。",
            "净值=原值-减值准备；清理净损益=清理收入-清理费用-净值。",
            "领用出库须填写对应H2编号（与在建工程勾稽）。",
            "检查比例=样本原值合计/本期减少贷方总体（总体为0时不除零）。",
            "核对内容1-5：凭证齐全、账证相符、处理正确、截止、H2勾稽/清理损益。",
        ],
    },
    "H4-6": {
        "item_id": "H4-6-rows",
        "title": "H4-6 盘点检查表",
        "headers": _H4_6_HEADERS,
        "field_keys": _H4_6_KEYS,
        "guidance": [
            "H4-6 工程物资盘点检查 编制说明（致同五段式）",
            "",
            "抽盘方向填 bookToFloor（账面→实物/存在）或 floorToBook（实物→账面/完整）。",
            "三数量：账面数量、企业盘点数量、抽盘数量；差异列在系统内自动计算。",
            "品质状况填：正常/闲置/积压/毁损/待报废/其他；闲置毁损盘亏可推送 H4-7。",
            "覆盖率分母为期末工程物资余额合计，须先从 H4-2 同步或手工填入（避免除零）。",
        ],
    },
    "H4-9": {
        "item_id": "H4-9-rows",
        "title": "H4-9 关联交易检查表",
        "headers": _H4_9_HEADERS,
        "field_keys": _H4_9_KEYS,
        "guidance": [
            "H4-9 工程物资关联交易检查 编制说明",
            "",
            "仅登记合并范围外关联方交易；交易类型填「购入」或「出售」。",
            "购入：交易金额=购买价款，入账价值=工程物资入账价值；入账差异=入账价值-购买价款。",
            "出售：出售原值/减值准备用于计算净值；交易金额=销售价格(不含税)；处置损益=售价-净值。",
            "价差率=(交易金额-公允评估价值)/公允评估价值×100%，|价差率|>10%重点关注。",
            "是否异常填「是/否/待定」；无交易时审计说明注明「本期无此类交易」。",
        ],
    },
}

router = create_cycle_import_export_router(tag="h4-import-export", api_prefix="h4", specs=_H4_SPECS)
