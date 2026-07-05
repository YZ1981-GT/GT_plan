"""G9 其他非流动金融资产 — 导入导出（G9-2 / G9-3 / G9-4 / G9-5 / G9-6 × 3 端点 = 15）."""

from __future__ import annotations

from ._cycle_import_export_common import create_cycle_import_export_router

_G9_2_HEADERS = [
    "序号", "资产名称", "分类", "初始投资日", "到期日", "持有数量", "面值成本",
    "期初余额", "本期增加", "本期减少", "公允价值变动", "利息收入", "减值损失",
    "期末余额", "审定数", "公允价值层次", "估值方法", "备注",
]
_G9_2_KEYS = [
    "seq", "assetName", "classification", "initialInvestDate", "maturityDate",
    "holdingQuantity", "faceValueOrCost", "openingBalance", "increaseAmount",
    "decreaseAmount", "fvChangeAmount", "interestIncome", "impairmentLoss",
    "closingBalance", "closingAdjusted", "fairValueLevel", "valuationMethod", "remark",
]

_G9_3_HEADERS = [
    "序号", "分录类型", "日期", "摘要", "科目代码", "科目名称", "借方", "贷方", "编制人", "备注",
]
_G9_3_KEYS = [
    "seq", "entryType", "date", "summary", "accountCode", "accountName",
    "debitAmount", "creditAmount", "preparedBy", "remark",
]

_G9_4_HEADERS = [
    "序号", "资产名称", "未审公允价值", "审定公允价值", "差异", "公允价值层次",
    "估值方法", "估值技术", "不可观察输入值", "估值文件索引",
]
_G9_4_KEYS = [
    "seq", "assetName", "closingUnadjustedFV", "closingAuditedFV", "fairValueDiff",
    "fairValueLevel", "valuationMethod", "valuationTechnique", "unobservableInputDesc",
    "valuationDocIndex",
]

_G9_5_HEADERS = [
    "序号", "资产名称", "期初公允价值", "本期购入", "本期处置", "转入第三层次", "转出第三层次",
    "公允价值变动损益", "公允价值变动OCI", "利息收入", "减值损失", "其他变动",
    "期末公允价值", "企业报告期末", "差异",
]
_G9_5_KEYS = [
    "seq", "assetName", "openingFairValue", "purchaseAmount", "disposalAmount",
    "transferIn", "transferOut", "fvChangePL", "fvChangeOCI", "interestIncome",
    "impairmentLoss", "otherChanges", "closingFairValue", "reportedClosing", "variance",
]

_G9_6_HEADERS = [
    "序号", "日期", "凭证编号", "业务内容", "借方", "贷方",
    "原始凭证", "授权批准", "账务处理", "分类正确", "公允价值", "减值计提",
    "是否异常", "异常说明", "风险等级", "备注",
]
_G9_6_KEYS = [
    "seq", "voucherDate", "voucherNo", "businessContent", "debitAmount", "creditAmount",
    "checkOriginal", "checkAuthorized", "checkAccounting", "checkClassification",
    "checkFairValue", "checkImpairment", "isAbnormal", "abnormalDesc", "riskLevel", "remark",
]

_G9_SPECS = {
    "G9-2": {
        "item_id": "G9-detail-rows",
        "title": "G9-2 明细表",
        "headers": _G9_2_HEADERS,
        "field_keys": _G9_2_KEYS,
        "guidance": ["G9-2 明细表编制说明", "", "期末余额=期初审定+增加-减少+FV变动+利息-减值"],
    },
    "G9-3": {
        "item_id": "G9-adjustment-rows",
        "title": "G9-3 调整分录",
        "headers": _G9_3_HEADERS,
        "field_keys": _G9_3_KEYS,
        "guidance": ["G9-3 调整分录编制说明", "", "借贷须平衡；AJE/RJE 汇总回写 G9-1"],
    },
    "G9-4": {
        "item_id": "G9-fv-test-rows",
        "title": "G9-4 公允价值测试",
        "headers": _G9_4_HEADERS,
        "field_keys": _G9_4_KEYS,
        "guidance": ["G9-4 公允价值测试编制说明", "", "Level3 时估值技术与不可观察输入值必填"],
    },
    "G9-5": {
        "item_id": "G9-l3-rows",
        "title": "G9-5 第三层次调节表",
        "headers": _G9_5_HEADERS,
        "field_keys": _G9_5_KEYS,
        "guidance": ["G9-5 L3调节表编制说明", "", "期末=期初+购入-处置+转入-转出+FV(损益)+FV(OCI)+利息-减值+其他"],
    },
    "G9-6": {
        "item_id": "G9-voucher-rows",
        "title": "G9-6 凭证检查",
        "headers": _G9_6_HEADERS,
        "field_keys": _G9_6_KEYS,
        "guidance": ["G9-6 凭证检查编制说明", "", "核对项任一✗则是否异常=是"],
    },
}

router = create_cycle_import_export_router(
    tag="g9-import-export",
    api_prefix="g9",
    specs=_G9_SPECS,
    storage_field="remark",
)
