"""G9 其他非流动金融资产 — 导入导出（G9-2~6 + 附注上市/国企 × 3 端点）."""

from __future__ import annotations

from ._cycle_import_export_common import create_cycle_import_export_router

_G9_2_HEADERS = [
    "序号", "资产名称", "分类", "工具种类", "指定FVTPL", "初始投资日", "到期日", "持有数量", "面值成本", "计量属性", "关联方",
    "期初余额", "期初调整", "本期增加", "本期减少", "公允价值变动", "利息收入", "减值损失", "OCI变动",
    "期末余额", "期末调整", "审定数", "公允价值层次", "估值方法", "发函情况", "OCI累计", "减值准备", "备注",
]
_G9_2_KEYS = [
    "seq", "assetName", "classification", "instrumentType", "isDesignated", "initialInvestDate", "maturityDate",
    "holdingQuantity", "faceValueOrCost", "measurementAttribute", "isRelatedParty",
    "openingBalance", "openingAdjustment", "increaseAmount", "decreaseAmount",
    "fvChangeAmount", "interestIncome", "impairmentLoss", "ociChange",
    "closingBalance", "closingAdjustment", "closingAdjusted", "fairValueLevel",
    "valuationMethod", "confirmationStatus", "ociCumulative", "impairmentProvision", "remark",
]

_G9_3_HEADERS = [
    "序号", "分录类型", "日期", "摘要", "科目代码", "科目名称", "借方", "贷方", "编制人", "备注",
]
_G9_3_KEYS = [
    "seq", "entryType", "date", "summary", "accountCode", "accountName",
    "debitAmount", "creditAmount", "preparedBy", "remark",
]

_G9_4_HEADERS = [
    "序号", "资产名称", "投资日",
    "未审数量", "未审单价", "未审公允价值",
    "审定数量", "审定单价", "审定公允价值", "差异", "差异原因",
    "公允价值层次", "估值方法", "与上期一致",
    "估值技术", "不可观察输入值", "输入值", "估值来源", "输入值来源",
    "非流动性折扣", "估值文件索引",
]
_G9_4_KEYS = [
    "seq", "assetName", "initialInvestDate",
    "closingUnadjustedQty", "closingUnadjustedPrice", "closingUnadjustedFV",
    "closingAuditedQty", "closingAuditedPrice", "closingAuditedFV", "fairValueDiff", "diffReason",
    "fairValueLevel", "valuationMethod", "methodConsistentWithPrior",
    "valuationTechnique", "unobservableInputDesc", "unobservableInputValue",
    "valuationSource", "inputSourceAndAdjustment",
    "nonLiquidityDiscount", "valuationDocIndex",
]

_G9_5_HEADERS = [
    "序号", "资产名称", "期初公允价值", "本期购入", "本期处置", "转入第三层次", "转出第三层次",
    "公允价值变动损益", "公允价值变动OCI", "利息收入", "减值损失", "其他变动",
    "期末公允价值", "仍持有未实现", "企业报告期末", "差异", "备注",
]
_G9_5_KEYS = [
    "seq", "assetName", "openingFairValue", "purchaseAmount", "disposalAmount",
    "transferIn", "transferOut", "fvChangePL", "fvChangeOCI", "interestIncome",
    "impairmentLoss", "otherChanges", "closingFairValue", "unrealizedHeld",
    "reportedClosing", "variance", "remark",
]

_G9_6_HEADERS = [
    "序号", "日期", "凭证编号", "业务内容", "对方科目", "资产名称", "借方", "贷方", "来源",
    "支持性文件", "原始凭证", "授权批准", "账务处理", "分类正确", "公允价值", "减值计提",
    "是否异常", "强制异常", "异常类型", "异常说明", "风险等级", "处理建议", "索引", "备注",
]
_G9_6_KEYS = [
    "seq", "voucherDate", "voucherNo", "businessContent", "counterAccount", "assetName",
    "debitAmount", "creditAmount", "source",
    "supportDoc", "checkOriginal", "checkAuthorized", "checkAccounting", "checkClassification",
    "checkFairValue", "checkImpairment",
    "isAbnormal", "forceAbnormal", "abnormalType", "abnormalDesc", "riskLevel", "suggestion",
    "indexRef", "remark",
]

# CAS 39 / 纸质 Excel G9-5 列名 → 十因子电子稿规范列名
_G9_5_HEADER_ALIASES = {
    "资产名称": [
        "投资项目",
        "投资项目【按明细项目列示（如：证券名称或投资单位名称）】",
    ],
    "期初公允价值": ["期初余额"],
    "本期购入": ["购买", "购入"],
    "本期处置": ["出售"],
    "转入第三层次": ["转入"],
    "转出第三层次": ["转出"],
    "公允价值变动损益": ["公允价值变动"],
    "利息收入": ["投资收益"],
    "其他变动": ["发行", "结算", "其他"],
    "期末公允价值": ["期末余额"],
    "仍持有未实现": [
        "仍持有未实现损益变动",
        "对于在报告期末持有的资产，计入损益的当期未实现利得或损失的变动",
    ],
    "企业报告期末": ["企业期末", "报告期末"],
}

_G9_DISC_HEADERS = ["行键", "项目", "期末金额", "期初金额", "附注文本"]
_G9_DISC_KEYS = ["rowKey", "label", "currentAmount", "priorAmount", "noteText"]
_G9_DISC_KEEP = ["currentAmount", "priorAmount", "noteText"]
_G9_DISC_ALIASES = {
    "项目": ["种类", "种  类", "项  目", "项目名称"],
    "期末金额": ["期末余额", "期末公允价值", "本期"],
    "期初金额": ["上年年末余额", "期初公允价值", "上期", "期初余额"],
    "行键": ["rowKey", "row_key", "键"],
    "附注文本": ["附注", "说明", "备注"],
}
_G9_DISC_LISTED_PREFILL = [
    ["listed_1", "债务工具投资", 0, 0, ""],
    ["listed_2", "权益工具投资", 0, 0, ""],
    ["listed_3", "指定为以公允价值计量且其变动计入当期损益的金融资产", 0, 0, ""],
    ["listed_4", "其他", 0, 0, ""],
]
_G9_DISC_SOE_PREFILL = [
    ["soe_1", "债务工具投资", 0, 0, ""],
    ["soe_2", "权益工具投资", 0, 0, ""],
    ["soe_3", "指定为以公允价值计量且其变动计入当期损益的金融资产", 0, 0, ""],
    ["soe_4", "其他", 0, 0, ""],
]
_G9_DISC_GUIDANCE_COMMON = [
    "附注披露编制说明",
    "",
    "结构对齐 Excel：四类（债务/权益/指定FVTPL/其他）+ 合计（合计由页面公式汇总，勿导入合计行）。",
    "行键须保留（listed_* / soe_*）；金额列可与底稿「期末余额/上年年末余额」或「期末公允价值/期初公允价值」别名对应。",
    "建议先在 G9-2 填工具种类与指定，再在附注页「分项带入」；也可本表手工/导入金额。",
    "期末合计应与 G9-1 审定（1504）勾稽；有 Level3 时应在附注汇总说明层次与调节过程。",
]

_G9_SPECS = {
    "G9-2": {
        "item_id": "G9-detail-rows",
        "title": "G9-2 明细表",
        "headers": _G9_2_HEADERS,
        "field_keys": _G9_2_KEYS,
        "allow_missing_headers": True,
        "guidance": [
            "G9-2 明细表编制说明",
            "",
            "审计目标：核对明细存在、计价与分类；期末审定合计与 G9-1 勾稽。",
            "公式：期末余额=期初审定+增加−减少+FV+利息−减值+OCI；审定数=期末+调整。",
            "可辅助核算取数（1504）；按分类回写 G9-1 各组首行未审数；Level3 须填估值方法。",
            "工具种类（债务/权益/衍生/其他）与「指定FVTPL」供附注分项带入；旧模板缺列可忽略（allow_missing）。",
            "FVOCI 可将本期 FV 变动填入 OCI 变动；可带入 G9-4/G9-5。",
        ],
    },
    "G9-3": {
        "item_id": "G9-adjustment-rows",
        "title": "G9-3 调整分录",
        "headers": _G9_3_HEADERS,
        "field_keys": _G9_3_KEYS,
        "guidance": [
            "G9-3 调整分录编制说明",
            "",
            "审计目标：核实 1504 相关 AJE/RJE 依据充分、借贷平衡，并正确回写 G9-1。",
            "AJE=账项调整；RJE=重分类。仅汇总 1504 借−贷净额，分 AJE/RJE 回写审定表 fvtpl_1。",
            "FVTPL 成对：1504 ↔ 6101；FVOCI 成对：1504 ↔ 4002。整表借贷须平衡。",
            "可自 G9-4 推送公允差异；可与中央调整分录模块双向同步。",
        ],
    },
    "G9-4": {
        "item_id": "G9-fv-test-rows",
        "title": "G9-4 公允价值测试",
        "headers": _G9_4_HEADERS,
        "field_keys": _G9_4_KEYS,
        "allow_missing_headers": True,
        "guidance": [
            "G9-4 公允价值测试编制说明",
            "",
            "审计目标：验证公允价值计量恰当性；层次划分与估值技术/不可观察输入值合理。",
            "有数量单价时 FV=数量×单价；差异=审定−未审；|差异|>0.01 须填差异原因。",
            "Level3：估值技术、不可观察输入值描述/数值、估值文件索引必填；Level2 须填估值来源。",
            "建议工作流：G9-2 带入 → 本表测试 → 回写 G9-2 / 推送差异至 G9-3 → Level3 带入 G9-5 → 回填 G9A seq8。",
        ],
    },
    "G9-5": {
        "item_id": "G9-l3-rows",
        "title": "G9-5 第三层次调节表",
        "headers": _G9_5_HEADERS,
        "field_keys": _G9_5_KEYS,
        "allow_missing_headers": True,
        "header_aliases": _G9_5_HEADER_ALIASES,
        "guidance": [
            "G9-5 第三层次公允价值调节表编制说明",
            "",
            "审计目标：验证 L3 期初至期末十因子变动完整准确，公式期末与企业报告勾稽，调节过程披露恰当。",
            "公式：期末=期初+购入-处置+转入-转出+FV(损益)+FV(OCI)+利息-减值+其他",
            "仍持有未实现：报告期末仍持有资产计入损益的当期未实现利得或损失变动（CAS 39 披露项，不进期末公式）。",
            "兼容纸质 CAS 39 列名导入：投资项目/期初余额/购买出售/投资收益/仍持有未实现等将自动映射到十因子列。",
            "建议工作流：G9-2 Level3 明细 → 本表十因子 → 与 G9-4 审定FV / 附注勾稽；转入转出须注明原因。",
            "FV(损益)与FV(OCI)分列，不得混淆；差异=公式期末-企业报告期末，>0.01须说明。",
        ],
    },
    "G9-6": {
        "item_id": "G9-voucher-rows",
        "title": "G9-6 凭证检查",
        "headers": _G9_6_HEADERS,
        "field_keys": _G9_6_KEYS,
        "guidance": [
            "G9-6 凭证检查编制说明",
            "",
            "核对项三态(未测/通过/不通过)；仅「不通过」标异常；抽样参数须文档化",
            "资产名称可挂接 G9-2；公允价值/减值不通过属金额类异常，可推送 A13",
            "forceAbnormal=是 表示截止跨期或人工强制异常",
        ],
    },
    "附注上市": {
        "item_id": "G9-disclosure-listed",
        "title": "附注披露信息（上市公司）",
        "headers": _G9_DISC_HEADERS,
        "field_keys": _G9_DISC_KEYS,
        "keyed_by": "rowKey",
        "keep_keys": _G9_DISC_KEEP,
        "allow_missing_headers": True,
        "header_aliases": _G9_DISC_ALIASES,
        "template_prefill": _G9_DISC_LISTED_PREFILL,
        "guidance": _G9_DISC_GUIDANCE_COMMON + [
            "上市公司表头口径：种类 / 期末余额 / 上年年末余额。",
        ],
    },
    "附注国企": {
        "item_id": "G9-disclosure-soe",
        "title": "附注披露信息（国企）",
        "headers": _G9_DISC_HEADERS,
        "field_keys": _G9_DISC_KEYS,
        "keyed_by": "rowKey",
        "keep_keys": _G9_DISC_KEEP,
        "allow_missing_headers": True,
        "header_aliases": _G9_DISC_ALIASES,
        "template_prefill": _G9_DISC_SOE_PREFILL,
        "guidance": _G9_DISC_GUIDANCE_COMMON + [
            "国企表头口径：项目 / 期末公允价值 / 期初公允价值。",
        ],
    },
}

router = create_cycle_import_export_router(
    tag="g9-import-export",
    api_prefix="g9",
    specs=_G9_SPECS,
    storage_field="remark",
)
