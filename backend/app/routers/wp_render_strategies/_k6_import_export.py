"""K6 持有待售资产和负债 — 导入导出（3张动态行表: K6-2明细/K6-3调整/K6-6处置组）.

科目 1481 持有待售资产（借方/资产类） + 2605 持有待售负债（贷方/负债类）。
K6-2 明细表 15 列：序号/处置组或资产名称/类别/账面原值/累计折旧摊销/减值准备/账面价值/公允价值/预计出售费用/公允价值净额/持有待售确认日/预计出售日/凭证/结论/备注。
K6-3 调整分录汇总。
K6-6 处置组减值测试表 11 列。
"""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ────────────────────────────────────────────────────────────
# K6-2 明细表（15列）
# 序号/处置组或资产名称/类别/账面原值/累计折旧摊销/减值准备/账面价值(公式)
# /公允价值/预计出售费用/公允价值净额(公式)/持有待售确认日/预计出售日/凭证号/结论/备注
# ────────────────────────────────────────────────────────────
_K6_2_HEADERS = [
    "序号", "处置组或资产名称", "类别", "账面原值",
    "累计折旧摊销", "减值准备", "账面价值",
    "公允价值", "预计出售费用", "公允价值净额",
    "持有待售确认日", "预计出售日", "凭证号", "结论", "备注",
]
_K6_2_KEYS = [
    "seq", "assetName", "category", "originalCost",
    "accDepreciation", "impairment", "bookValue",
    "fairValue", "sellingCost", "fairValueNet",
    "classificationDate", "expectedSaleDate", "voucherNo", "conclusion", "remark",
]

# ────────────────────────────────────────────────────────────
# K6-3 调整分录汇总（10列）
# ────────────────────────────────────────────────────────────
_K6_3_HEADERS = [
    "序号", "分录类型", "摘要", "科目代码", "科目名称",
    "借方金额", "贷方金额", "编制人", "备注",
]
_K6_3_KEYS = [
    "seq", "entryType", "summary", "accountCode", "accountName",
    "debitAmount", "creditAmount", "preparedBy", "remark",
]

# ────────────────────────────────────────────────────────────
# K6-6 处置组减值测试表（11列）
# 处置组/组内资产名称/资产类别/账面价值/组整体减值/商誉抵减/
# 非流动资产分摊比例/分摊减值/分摊后账面/减值下限/结论
# ────────────────────────────────────────────────────────────
_K6_6_HEADERS = [
    "处置组", "组内资产名称", "资产类别", "账面价值",
    "组整体减值", "商誉抵减", "分摊比例",
    "分摊减值", "分摊后账面", "减值下限", "结论",
]
_K6_6_KEYS = [
    "groupName", "assetName", "assetCategory", "bookValue",
    "groupImpairment", "goodwillDeduction", "allocationRatio",
    "allocatedImpairment", "postAllocationBook", "impairmentFloor", "conclusion",
]

# ────────────────────────────────────────────────────────────
# K6-4 初始确认估值表（19列，对齐前端 K6ValuationRow）
# 公允价值三方法确定 + 孰低净额 + CAS42判断列
# ────────────────────────────────────────────────────────────
_K6_4_HEADERS = [
    "分类", "处置组/主体", "项目", "账面价值",
    "销售协议价格", "销售协议依据", "活跃市场价格", "活跃市场依据",
    "估计价格", "估计依据", "公允价值", "出售费用", "公允净额",
    "预计出售时间", "即可立即出售", "决议索引", "协议索引",
]
_K6_4_KEYS = [
    "category", "groupName", "itemName", "bookValue",
    "salesPrice", "salesBasis", "marketPrice", "marketBasis",
    "estimatePrice", "estimateBasis", "fairValue", "sellingCost", "fairValueNet",
    "expectedSaleTime", "immediatelySellable", "decisionRef", "agreementRef",
]

# ────────────────────────────────────────────────────────────
# K6-5 减值准备测试表（对齐前端 K6ImpairmentRow）
# 项目/账面/公允/公允依据/出售费用/公允净额/减值/已计提/应补提/结论/备注
# ────────────────────────────────────────────────────────────
_K6_5_HEADERS = [
    "序号", "项目", "账面价值", "公允价值", "公允价值确定依据",
    "出售费用", "公允净额", "减值金额", "已计提", "应补提", "结论", "备注",
]
_K6_5_KEYS = [
    "seqNo", "assetName", "bookValue", "fairValue", "fairValueBasis",
    "sellingCost", "fairValueNet", "impairmentAmount", "existingProvision",
    "additionalProvision", "conclusion", "remark",
]

# ────────────────────────────────────────────────────────────
# K6-7 检查表（不再满足持有待售）（对齐前端 K6NoLongerCheckItem）
# ①②③④净额分解 + 可收回金额/方法 + 调整后账面/现账面/调整差额 + 合规判定
# ────────────────────────────────────────────────────────────
_K6_7_HEADERS = [
    "序号", "分类", "处置组/主体", "项目/资产名称",
    "①被划归前账面", "②假设折旧摊销", "③假设减值", "④净额",
    "可收回金额", "可收回确定方法", "调整后账面", "现账面", "调整差额",
    "不再满足原因", "重分类日", "决议索引", "协议索引", "状态", "结论", "凭证", "备注",
]
_K6_7_KEYS = [
    "seqNo", "category", "groupName", "assetName",
    "preClassBookValue", "assumedDepreciation", "assumedImpairment", "netValue",
    "recoverableAmount", "recoverableMethod", "adjustedBookValue", "currentBookValue", "adjustmentDiff",
    "noLongerReason", "reclassificationDate", "decisionRef", "agreementRef", "status", "conclusion", "voucherRef", "remark",
]

# ────────────────────────────────────────────────────────────
# Sheet Specs 汇总
# ────────────────────────────────────────────────────────────
_K6_SPECS: dict[str, dict[str, Any]] = {
    "K6-2": {
        "item_id": "K6-2-rows",
        "title": "K6-2 持有待售明细表",
        "headers": _K6_2_HEADERS,
        "field_keys": _K6_2_KEYS,
        "guidance": [
            "K6-2 明细表 编制说明",
            "",
            "15列：序号/处置组或资产名称/类别/账面原值/累计折旧摊销/减值准备/账面价值(公式)",
            "/公允价值/预计出售费用/公允价值净额(公式)/持有待售确认日/预计出售日/凭证号/结论/备注。",
            "",
            "账面价值 = 原值 - 累计折旧摊销 - 减值准备（公式列，导入时可空）。",
            "公允价值净额 = 公允价值 - 预计出售费用（公式列，导入时可空）。",
            "持有待售资产（借方/资产类）：正数表示借方余额。",
            "类别：固定资产/无形资产/投资性房地产/长期股权投资/其他。",
            "金额为数值型，单位：元。",
        ],
    },
    "K6-3": {
        # 前端 K6TabAdjustment 持久化键为 K6-3-adj-entries（AdjustmentEntry[]）
        "item_id": "K6-3-adj-entries",
        # 前端 K6TabAdjustment 读写 remark 列，工厂默认 conclusion 会写错列（Task 2.7）
        "storage_field": "remark",
        "title": "K6-3 持有待售调整分录汇总",
        "headers": _K6_3_HEADERS,
        "field_keys": _K6_3_KEYS,
        "guidance": [
            "K6-3 调整分录 编制说明",
            "",
            "10列：序号/分录类型(AJE/RJE)/摘要/科目代码/科目名称/借方金额/贷方金额/编制人/凭证号/备注。",
            "借贷必须平衡：∑借方 = ∑贷方。",
            "分录类型填 AJE（审计调整）或 RJE（重分类调整）。",
            "金额单位：元。",
        ],
    },
    "K6-6": {
        "item_id": "K6-6-rows",
        "title": "K6-6 处置组减值测试表",
        "headers": _K6_6_HEADERS,
        "field_keys": _K6_6_KEYS,
        "guidance": [
            "K6-6 处置组减值测试表 编制说明",
            "",
            "11列：处置组/组内资产名称/资产类别/账面价值/组整体减值/商誉抵减",
            "/分摊比例(公式)/分摊减值(公式)/分摊后账面(公式)/减值下限/结论。",
            "",
            "处置组减值分摊逻辑（CAS42）：",
            "1. 先抵减商誉（商誉全额冲减）",
            "2. 余额按账面价值比例分摊至组内非流动资产",
            "3. 分摊比例 = 组内资产账面 / 组账面合计",
            "4. 分摊后账面不得低于公允价值净额（减值下限）",
            "金额为数值型，单位：元。",
        ],
    },
    "K6-4": {
        "item_id": "K6-4-valuation-rows",
        "title": "K6-4 初始确认估值表",
        "headers": _K6_4_HEADERS,
        "field_keys": _K6_4_KEYS,
        "guidance": [
            "K6-4 初始确认估值表 编制说明",
            "",
            "分类填：非流动资产(asset_noncurrent)/处置组资产(asset_group)/处置组负债(liability_group)。",
            "公允价值三方法优先级：销售协议价 > 活跃市场价 > 估计价（公允价值列为公式，导入可空）。",
            "公允净额 = 公允价值 - 出售费用（公式列，导入可空）。",
            "即可立即出售填：是/否/待定。",
            "决议索引/协议索引指向董事会决议、不可撤销转让协议等支持性证据。",
            "金额为数值型，单位：元。",
        ],
    },
    "K6-5": {
        "item_id": "K6-5-rows",
        "title": "K6-5 减值准备测试表",
        "headers": _K6_5_HEADERS,
        "field_keys": _K6_5_KEYS,
        "guidance": [
            "K6-5 减值准备测试表 编制说明",
            "",
            "孰低法：公允净额 = 公允价值 - 出售费用；减值金额 = MAX(0, 账面 - 公允净额)。",
            "应补提 = 减值金额 - 已计提减值准备（公式列，导入可空）。",
            "公允净额/减值金额/应补提为公式列，导入时可空，前端自动重算。",
            "金额为数值型，单位：元。",
        ],
    },
    "K6-7": {
        "item_id": "K6-7-rows",
        "title": "K6-7 检查表（不再满足持有待售条件）",
        "headers": _K6_7_HEADERS,
        "field_keys": _K6_7_KEYS,
        "guidance": [
            "K6-7 检查表 编制说明",
            "",
            "分类填：非流动资产(asset_noncurrent)/处置组资产(asset_group)/处置组负债(liability_group)。",
            "④净额 = ①被划归前账面 - ②假设折旧摊销 - ③假设减值（公式列，导入可空）。",
            "调整后账面 = min(④净额, 可收回金额)（CAS42第22条孰低，公式列，导入可空）。",
            "调整差额 = 调整后账面 - 现账面（计入当期损益，公式列，导入可空）。",
            "可收回确定方法填：fair_value_net(公允净额)/value_in_use(使用价值)/appraisal(评估报告)。",
            "状态填：compliant(合规)/non_compliant(不合规)/na(不适用)。",
            "金额为数值型，单位：元。",
        ],
    },
}

router = create_cycle_import_export_router(tag="k6-import-export", api_prefix="k6", specs=_K6_SPECS)
