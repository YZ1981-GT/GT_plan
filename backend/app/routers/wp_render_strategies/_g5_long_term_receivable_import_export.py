"""G5 长期应收款 — 导入导出（8 张表，G5-10 待 G4-10 完成后补齐）."""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

_G5_2_HEADERS = [
    "序号", "债务人", "业务类型", "合同编号", "开始日", "到期日",
    "合同总额", "已收回", "期末余额", "关联方", "未实现收益", "净额",
    "1年内", "1-2年", "2-3年", "3-4年", "4-5年", "5年以上", "账龄合计", "备注",
]
_G5_2_KEYS = [
    "seq", "debtorName", "businessType", "contractNo", "startDate", "maturityDate",
    "contractAmount", "recoveredAmount", "closingBalance", "isRelatedParty", "unrealizedIncome", "netAmount",
    "aging1Year", "aging1to2", "aging2to3", "aging3to4", "aging4to5", "aging5Plus", "agingTotal", "remark",
]

_G5_3_HEADERS = [
    "序号", "债务人/组合", "计提方式", "期末余额", "损失率", "未审坏账", "余额调整", "调整后率",
    "坏账调整", "调整说明", "索引", "审定余额", "审定坏账", "审定净值", "上年坏账", "本年计提", "转回", "备注",
]
_G5_3_KEYS = [
    "seq", "debtorOrGroup", "provisionMethod", "closingBalance", "creditLossRate", "unadjustedProvision",
    "balanceAdjustment", "adjustedLossRate", "provisionAdjustment", "adjustmentDesc", "indexRef",
    "adjustedBalance", "adjustedProvision", "adjustedNetValue", "priorYearProvision", "currentYearProvision",
    "currentYearReversal", "remark",
]

_G5_4_HEADERS = [
    "序号", "分录类型", "日期", "摘要", "科目代码", "科目名称", "借方", "贷方", "编制人", "备注",
]
_G5_4_KEYS = [
    "seq", "entryType", "date", "summary", "accountCode", "accountName", "debitAmount", "creditAmount", "preparedBy", "remark",
]

_G5_5_HEADERS = [
    "项目名称", "期次", "承租人", "内含利率", "期初应收", "期初未实现", "本期收款", "企业账面收益", "备注",
]
_G5_5_KEYS = [
    "projectName", "periodNo", "lessee", "implicitRate", "openingReceivable", "openingUnrealized",
    "periodCollection", "companyBookIncome", "remark",
]

_G5_6_HEADERS = [
    "项目名称", "期次", "应收总额", "公允价值", "实际利率", "期初应收", "本期收款", "备注",
]
_G5_6_KEYS = [
    "projectName", "periodNo", "contractTotal", "fairValue", "effectiveRate", "openingReceivable", "periodCollection", "remark",
]

_G5_7_HEADERS = [
    "序号", "债务人", "保理商", "金额", "方式", "终止确认", "判断依据", "结论", "索引",
]
_G5_7_KEYS = [
    "seq", "debtor", "factor", "amount", "method", "derecognition", "basis", "conclusion", "indexRef",
]

_G5_11_HEADERS = [
    "区段", "序号", "债务人", "累计计提", "转回金额", "核销金额", "审批状态", "关联交易", "原因", "索引",
]
_G5_11_KEYS = [
    "section", "seq", "debtor", "accumulatedProvision", "reversalAmount", "writeoffAmount",
    "approvalStatus", "isRelatedParty", "reason", "indexRef",
]

_G5_12_HEADERS = [
    "序号", "摘要", "对方科目", "金额", "凭证日期", "凭证编号", "债务人", "业务类型",
    "核对1", "核对2", "核对3", "核对4", "核对5", "核对6", "核对7",
    "是否异常", "审计结论", "索引", "来源",
]
_G5_12_KEYS = [
    "seq", "summary", "counterAccount", "amount", "voucherDate", "voucherNo", "debtor", "businessType",
    "check1", "check2", "check3", "check4", "check5", "check6", "check7",
    "isAbnormal", "conclusion", "indexRef", "source",
]

_G5_SPECS: dict[str, dict[str, Any]] = {
    "G5-2": {
        "item_id": "G5-2-rows",
        "title": "G5-2 长期应收款余额明细表",
        "headers": _G5_2_HEADERS,
        "field_keys": _G5_2_KEYS,
        "guidance": ["G5-2 余额明细", "", "期末余额=合同总额-已收回；净额=余额-未实现；账龄合计应等于净额。"],
    },
    "G5-3": {
        "item_id": "G5-3-rows",
        "title": "G5-3 坏账准备明细表",
        "headers": _G5_3_HEADERS,
        "field_keys": _G5_3_KEYS,
        "guidance": ["G5-3 坏账准备", "", "ECL公式链：③=①×②；⑥=⑤×②A+①×(②A-②)；⑦=①+⑤；⑧=③+⑥；⑨=⑦-⑧。"],
    },
    "G5-4": {
        "item_id": "G5-4-rows",
        "title": "G5-4 调整分录汇总",
        "headers": _G5_4_HEADERS,
        "field_keys": _G5_4_KEYS,
        "guidance": ["G5-4 调整分录", "", "分录类型填 AJE 或 RJE；借贷须平衡。"],
    },
    "G5-5": {
        "item_id": "G5-5-rows",
        "title": "G5-5 融资租赁测算",
        "headers": _G5_5_HEADERS,
        "field_keys": _G5_5_KEYS,
        "guidance": ["G5-5 融资租赁", "", "内含利率法：融资收益=净投资额×内含利率。"],
    },
    "G5-6": {
        "item_id": "G5-6-rows",
        "title": "G5-6 分期销售测算",
        "headers": _G5_6_HEADERS,
        "field_keys": _G5_6_KEYS,
        "guidance": ["G5-6 分期销售", "", "实际利率法：融资收益=摊余成本×实际利率。"],
    },
    "G5-7": {
        "item_id": "G5-7-rows",
        "title": "G5-7 保理核查表",
        "headers": _G5_7_HEADERS,
        "field_keys": _G5_7_KEYS,
        "guidance": ["G5-7 保理核查", "", "有追索权保理通常不应终止确认。"],
    },
    "G5-11": {
        "item_id": "G5-11-rows",
        "title": "G5-11 转回核销检查",
        "headers": _G5_11_HEADERS,
        "field_keys": _G5_11_KEYS,
        "guidance": ["G5-11 转回核销", "", "区段填 reversal 或 writeoff；转回金额≤累计计提。"],
    },
    "G5-12": {
        "item_id": "G5-12-rows",
        "title": "G5-12 凭证检查表",
        "headers": _G5_12_HEADERS,
        "field_keys": _G5_12_KEYS,
        "guidance": ["G5-12 凭证检查", "", "核对列填 ✓ 或 ✗；任一✗则是否异常=是。"],
    },
}

router = create_cycle_import_export_router(
    tag="g5-import-export",
    api_prefix="g5",
    specs=_G5_SPECS,
    storage_field="remark",
)
