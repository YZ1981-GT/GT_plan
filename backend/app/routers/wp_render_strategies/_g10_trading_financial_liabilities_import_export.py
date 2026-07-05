"""G10 交易性金融负债 — 导入导出（G10-2 / G10-3 / G10-5 / G10-6 / G10-7 × 3 端点 = 15）."""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

_G10_2_HEADERS = [
    "序号", "负债名称", "负债类型", "对手方", "合同日", "到期日",
    "初始金额", "期初余额", "期初审定", "本期增加", "本期减少", "期末余额", "审定数",
    "公允价值层次", "估值方法", "期初公允价值", "期末公允价值", "公允价值变动",
    "计入损益金额", "是否衍生工具", "主合同描述", "嵌入衍生判断", "发函情况", "备注",
]
_G10_2_KEYS = [
    "seq", "liabilityName", "liabilityType", "counterparty", "contractDate", "maturityDate",
    "initialAmount", "openingBalance", "openingAdjusted", "currentIncrease", "currentDecrease",
    "closingBalance", "closingAdjusted",
    "fairValueLevel", "valuationMethod", "openingFairValue", "closingFairValue", "fairValueChange",
    "profitLossAmount", "isDerivative", "hostContractDesc", "embeddedDerivativeJudgment",
    "confirmationStatus", "remark",
]

_G10_3_HEADERS = [
    "序号", "分录类型", "日期", "摘要", "科目代码", "科目名称", "借方", "贷方", "编制人", "备注",
]
_G10_3_KEYS = [
    "seq", "entryType", "date", "summary", "accountCode", "accountName",
    "debitAmount", "creditAmount", "preparedBy", "remark",
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
    "公允价值变动", "利息费用", "其他", "期末余额", "差异", "备注",
]
_G10_6_KEYS = [
    "seq", "liabilityName", "openingBalance", "currentNew", "currentTerminated",
    "transferIntoL3", "transferOutOfL3", "fairValueChange", "interestExpense", "otherChanges",
    "closingBalance", "variance", "remark",
]

_G10_7_HEADERS = [
    "序号", "日期", "凭证编号", "业务内容", "对方科目", "借方", "贷方",
    "附件", "文件描述", "核对1完整", "核对2授权", "核对3账务正确", "核对4公允价值正确",
    "索引号", "是否异常", "异常说明", "风险等级", "备注",
]
_G10_7_KEYS = [
    "seq", "voucherDate", "voucherNo", "businessContent", "counterAccount",
    "debitAmount", "creditAmount", "attachment", "fileDescription",
    "check1Complete", "check2Authorization", "check3Accounting", "check4FairValue",
    "indexNo", "isAbnormal", "abnormalDesc", "riskLevel", "remark",
]

_G10_SPECS: dict[str, dict[str, Any]] = {
    "G10-2": {
        "item_id": "G10-detail-rows",
        "title": "G10-2 交易性金融负债明细表",
        "headers": _G10_2_HEADERS,
        "field_keys": _G10_2_KEYS,
        "guidance": [
            "G10-2 明细表 编制说明",
            "",
            "24列宽表可拆分为基础信息/公允价值+分类两区段导入；审定数=未审+调整。",
        ],
    },
    "G10-3": {
        "item_id": "G10-aje-rows",
        "title": "G10-3 调整分录汇总表",
        "headers": _G10_3_HEADERS,
        "field_keys": _G10_3_KEYS,
        "guidance": [
            "G10-3 调整分录 编制说明",
            "",
            "类型填 AJE/RJE；借贷须平衡；可同步至审定表调整数。",
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
        "guidance": [
            "G10-6 L3调节表 编制说明",
            "",
            "期末=期初+新增-终止+转入-转出+FV变动+利息+其他；差异=实际期末-计算期末。",
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
            "核对列填 ✓/✗；任一✗则是否异常=是；借贷须平衡。",
        ],
    },
}

router = create_cycle_import_export_router(
    tag="g10-import-export",
    api_prefix="g10",
    specs=_G10_SPECS,
    storage_field="remark",
)
