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

# ─── H3-5 增减检查（成本模式 · 账→证） ─────────────────────────────────────

_H3_5_COST_HEADERS = [
    "序号", "投资性房地产类别", "资产名称", "增减日期", "增减方式", "凭证号", "对方科目",
    "原值", "累计折旧", "减值准备", "净值", "支持性文件",
    "核对1", "核对2", "核对3", "核对4", "核对5",
    "索引号", "是否异常", "备注说明",
]
_H3_5_COST_KEYS = [
    "seq", "category", "assetName", "date", "changeType", "voucherNo", "creditAccount",
    "originalCost", "accDep", "impairment", "netValue", "supportingDocs",
    "check1", "check2", "check3", "check4", "check5",
    "indexRef", "isAbnormal", "remark",
]

# ─── H3-5 增减检查（公允模式 · 账→证） ─────────────────────────────────────

_H3_5_FAIR_HEADERS = [
    "序号", "投资性房地产类别", "资产名称", "增减日期", "增减方式", "凭证号", "对方科目",
    "公允价值", "公允价值变动", "期末余额", "评估依据", "支持性文件",
    "核对1", "核对2", "核对3", "核对4", "核对5",
    "索引号", "是否异常", "备注说明",
]
_H3_5_FAIR_KEYS = [
    "seq", "category", "assetName", "date", "changeType", "voucherNo", "creditAccount",
    "fairValue", "fairValueChange", "endBalance", "appraisalBasis", "supportingDocs",
    "check1", "check2", "check3", "check4", "check5",
    "indexRef", "isAbnormal", "remark",
]

# ─── H3-5 证→账追查（完整性） ────────────────────────────────────────────────

_H3_5_TRACE_HEADERS = [
    "序号", "源文件类型", "源文件编号", "源文件日期", "对方名称", "源文件金额",
    "已入账", "账面凭证号", "账面资产", "账面金额", "差额", "结果", "索引号", "备注",
]
_H3_5_TRACE_KEYS = [
    "seq", "sourceType", "sourceRef", "sourceDate", "sourceParty", "sourceAmount",
    "recordedInBooks", "bookVoucherNo", "bookAssetName", "bookAmount", "amountDiff", "checkResult", "indexRef", "linkedTitleRowId", "remark",
]

_H3_5_GUIDANCE_COMMON = [
    "H3-5 投资性房地产增减检查 编制说明",
    "",
    "编制逻辑：审计目标 → 样本选取 → 账→证抽查 + 证→账追查 → 检查比例 → 说明/结论。",
    "账→证支撑存在与计价；证→账追查支撑完整性认定。",
    "检查比例=样本检查金额/本期新增合计；偏低时扩大样本或在审计说明中解释。",
    "增减方式：外购/在建转入/自用转入/存货转入/后续支出/处置/转出/其他。",
]

# ─── H3-9 盘点检查 ──────────────────────────────────────────────────────────

_H3_9_HEADERS = [
    "序号", "抽盘方向", "资产名称", "资产编号", "坐落位置", "面积(㎡)",
    "账面数量", "账面金额", "企业盘点数量", "抽盘数量",
    "用途", "租赁状态", "租户", "产权证号", "品质状况",
    "盘点结果", "差异原因", "备注",
]
_H3_9_KEYS = [
    "seq", "direction", "assetName", "assetNo", "location", "area",
    "bookQty", "bookAmount", "clientCountQty", "sampleQty",
    "purpose", "leaseStatus", "tenant", "titleCertNo", "qualityStatus",
    "result", "diffReason", "remark",
]

# ─── H3-12 产权核对 ─────────────────────────────────────────────────────────

_H3_12_HEADERS = [
    "序号", "账面所有者", "资产编号", "资产名称", "坐落地点", "账面面积", "账面原值",
    "办证状态", "证书名称", "产权证号", "证载面积", "面积差异", "证载所有人", "是否被审计单位",
    "核对一致", "不一致原因", "预计办证日", "办证进度", "权属纠纷", "证载用途", "实际用途",
    "是否权利受限", "抵押面积", "抵押价值", "抵押性质", "查封", "索引号", "来源", "备注",
]
_H3_12_KEYS = [
    "seq", "bookOwner", "assetCode", "assetName", "location", "bookArea", "bookValue",
    "certStatus", "certName", "titleCertNo", "certArea", "areaDiff", "certOwner", "isAuditEntity",
    "matchConsistent", "inconsistentReason", "expectedCertDate", "certProgressNote", "hasDispute",
    "certPurpose", "actualPurpose",
    "isRestricted", "mortgageArea", "mortgageValue", "mortgageNature", "seizure", "refIndex", "sourceTags", "remark",
]

# ─── H3-13 关联交易 ─────────────────────────────────────────────────────────

_H3_13_HEADERS = [
    "序号", "关联方", "关联关系", "交易类型", "金额",
    "定价政策", "市场价参考", "差异率(%)", "审批文件",
    "是否存在异常", "备注/索引号",
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
    "H3-5-cost": {
        "item_id": "H3-5-cost-rows",
        "item_id_candidates": ["H3-5-cost-rows", "H3-5-rows"],
        "title": "H3-5 增减检查表（成本模式）",
        "headers": _H3_5_COST_HEADERS,
        "field_keys": _H3_5_COST_KEYS,
        "storage_field": "remark",
        "dual_write": True,
        "allow_missing_headers": True,
        "header_aliases": {
            "资产名称": ["投资性房地产名称", "名称"],
            "增减日期": ["变动日期", "日期"],
            "增减方式": ["变动类型", "增加方式"],
            "凭证号": ["入账凭证号"],
            "是否异常": ["异常"],
            "备注说明": ["备注"],
        },
        "guidance": _H3_5_GUIDANCE_COMMON + [
            "成本模式：净值=原值-累计折旧-减值准备。",
            "外购追查合同/发票/验收/产权证；转入关注转换依据与审批。",
        ],
    },
    "H3-5-fair": {
        "item_id": "H3-5-fair-rows",
        "item_id_candidates": ["H3-5-fair-rows", "H3-5-rows"],
        "title": "H3-5 增减检查表（公允价值模式）",
        "headers": _H3_5_FAIR_HEADERS,
        "field_keys": _H3_5_FAIR_KEYS,
        "storage_field": "remark",
        "dual_write": True,
        "allow_missing_headers": True,
        "header_aliases": {
            "资产名称": ["投资性房地产名称", "名称"],
            "增减日期": ["变动日期", "日期"],
            "增减方式": ["变动类型"],
            "凭证号": ["入账凭证号"],
            "是否异常": ["异常"],
            "备注说明": ["备注"],
        },
        "guidance": _H3_5_GUIDANCE_COMMON + [
            "公允价值模式：关注评估依据与公允价值变动列示。",
            "可与 H3-8 公允价值复核交叉验证。",
        ],
    },
    "H3-5-trace-cost": {
        "item_id": "H3-5-cost-trace-rows",
        "title": "H3-5 证→账追查（成本模式）",
        "headers": _H3_5_TRACE_HEADERS,
        "field_keys": _H3_5_TRACE_KEYS,
        "storage_field": "remark",
        "dual_write": True,
        "allow_missing_headers": True,
        "header_aliases": {
            "源文件类型": ["文件类型"],
            "源文件编号": ["文件编号", "编号"],
            "已入账": ["是否入账"],
            "结果": ["检查结果", "审计结论"],
        },
        "guidance": _H3_5_GUIDANCE_COMMON + [
            "证→账追查：从合同/发票/验收报告等源文件追查至账面是否入账。",
            "差额=源文件金额-账面金额；未入账或差额较大须跟进。",
        ],
    },
    "H3-5-trace-fair": {
        "item_id": "H3-5-fair-trace-rows",
        "title": "H3-5 证→账追查（公允价值模式）",
        "headers": _H3_5_TRACE_HEADERS,
        "field_keys": _H3_5_TRACE_KEYS,
        "storage_field": "remark",
        "dual_write": True,
        "allow_missing_headers": True,
        "header_aliases": {
            "源文件类型": ["文件类型"],
            "源文件编号": ["文件编号", "编号"],
            "已入账": ["是否入账"],
            "结果": ["检查结果", "审计结论"],
        },
        "guidance": _H3_5_GUIDANCE_COMMON + [
            "证→账追查：从评估报告/合同等源文件追查至公允价值入账。",
            "差额=源文件金额-账面公允价值；未入账须关注完整性。",
        ],
    },
    "H3-9": {
        "item_id": "H3-9-stocktake-rows",
        "title": "H3-9 盘点检查表",
        "headers": _H3_9_HEADERS,
        "field_keys": _H3_9_KEYS,
        "guidance": [
            "H3-9 投资性房地产盘点 编制说明",
            "",
            "抽盘方向：bookToFloor=账面→实物（存在性）；floorToBook=实物→账面（完整性）。",
            "三数量勾稽：账面数量、企业盘点数量、审计抽盘数量应比对一致。",
            "租赁状态：已出租/空置/到期/部分出租；空置率>20%需关注减值。",
            "期末原值合计用于计算样本覆盖率，避免除零错误。",
        ],
    },
    "H3-12": {
        "item_id": "H3-12-title-rows",
        "title": "H3-12 产权核对表",
        "headers": _H3_12_HEADERS,
        "field_keys": _H3_12_KEYS,
        "guidance": [
            "H3-12 投资性房地产产权核对 编制说明",
            "",
            "三段式核对：账面(登记簿) → 产权证明 → 抵押/权利限制。",
            "面积差异=证载面积-账面面积；容差±1㎡或0.5%内为可接受差异。",
            "办证中资产须填预计办证日与进度；抵押与 L1-8 交叉验证。",
            "可从 H3-2/H3-9 联动带入，并同步附注「限制及担保」。",
        ],
    },
    "H3-13": {
        "item_id": "H3-13-rp-rows",
        "title": "H3-13 关联交易检查表",
        "headers": _H3_13_HEADERS,
        "field_keys": _H3_13_KEYS,
        "guidance": [
            "H3-13 投资性房地产关联交易 编制说明",
            "",
            "一、审计目标：识别并核查关联方交易的完整性、定价公允性与披露恰当性。",
            "二、审计过程：对于合并范围外关联交易，核对合同、发票等文件，了解交易目的、价格和条件。",
            "三、差异率=(金额-市场价)/市场价×100%；差异率>10%时需重点关注定价合理性。",
            "四、出租类交易应与 H3-14 租金收入测算表勾稽；结果与附注关联方披露一致。",
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
