"""G7 长期股权投资(子公司组) — 导入导出（6张表×3端点=18端点）.

支持 6 张动态行表格：
  G7-8  同控初始计量（三区段多sheet）
  G7-9  非同控初始计量（三区段多sheet）
  G7-10 后续计量（三区段：股利/购买少数股权/不丧失控制权处置）
  G7-11 处置非一揽子(14列) / G7-12 处置一揽子(六区段)
  G7-18 凭证检查(19列→3区段Tab)

G7-8 / G7-9 / G7-10 / G7-12 / G7-18 导出为多 worksheet；其余单sheet。
字段键与前端 composable 严格对齐，保证 round-trip。
"""

from __future__ import annotations

import io
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

from ._cycle_import_export_common import (
    ROW_LIMIT,
    build_workbook_template,
    export_row_by_keys,
    is_numeric_field_key,
    load_json_payload,
    load_json_rows,
    parse_row_by_headers,
    parse_upload_xlsx,
    safe_float,
    safe_str,
    upsert_json_payload,
    upsert_json_rows,
    workbook_to_response,
)
from ._g7_long_term_equity_subsidiary_service import G7SubsidiaryService

router = APIRouter(tags=["g7-sub-import-export"])


# ═══════════════════════════════════════════════════════════════════════════════
# G7-8 同控初始计量（原底稿三类业务）
# ═══════════════════════════════════════════════════════════════════════════════

_G7_8_MERGER_HEADERS = [
    "公司名称", "合并日", "最终控制方", "会计政策一致", "政策调整说明",
    "被合并方所有者权益账面价值①", "合并后出资比例②",
    "初始投资成本③=①×②", "现金", "非现金资产账面价值", "债务账面价值",
    "权益性证券面值", "或有对价", "支付对价合计④",
    "调整资本公积/留存收益⑤=③-④", "可用资本公积", "差额处理说明", "索引", "审计结论",
]
_G7_8_MERGER_KEYS = [
    "investeeName", "acquisitionDate", "finalController", "accountingPolicyConsistent", "accountingPolicyNote",
    "ownerEquityBookValue", "ownershipRatio",
    "initialInvestmentCost", "cashConsideration", "nonCashAssetBookValue", "debtBookValue",
    "equitySecuritiesFaceValue", "contingentConsideration", "totalConsideration",
    "capitalReserveRetainedEarningsAdjustment", "availableCapitalReserve",
    "adjustmentTreatment", "indexRef", "auditConclusion",
]

_G7_8_STEP_HEADERS = [
    "公司名称", "公司标识", "次别", "交易日期", "合并日", "购买比例①", "支付对价②",
    "交易时被投资方可辨认净资产账面价值", "原持股账面价值",
    "原投资累计其他综合收益/损益调整等③",
    "是否一揽子交易", "不构成一揽子交易依据", "可用资本公积", "索引/备注",
]
_G7_8_STEP_KEYS = [
    "companyName", "companyId", "transactionNo", "transactionDate", "acquisitionDate", "purchaseRatio",
    "consideration", "netAssetsBookValue", "priorHoldingBookValue",
    "priorInvestmentAdjustments",
    "isPackageDeal", "notPackageBasis", "availableCapitalReserve", "indexRef",
]

_G7_8_REVERSE_HEADERS = [
    "交易内容", "会计上的购买方", "会计上的购买方的股东",
    "会计上的被购买方（上市公司）", "会计上的被购买方的原股东",
    "判断构成反向购买的依据", "是否构成业务及其判断依据", "索引号",
]
_G7_8_REVERSE_KEYS = [
    "transactionContent", "accountingAcquirer", "acquirerShareholders",
    "accountingAcquiree", "acquireeOriginalShareholders", "reversePurchaseBasis",
    "businessDeterminationBasis", "indexRef",
]

# ═══════════════════════════════════════════════════════════════════════════════
# G7-9 非同控初始计量（原底稿三类业务）
# ═══════════════════════════════════════════════════════════════════════════════

_G7_9_MERGER_HEADERS = [
    "公司名称", "购买日", "购买日认定证据索引",
    "可辨认净资产FV①", "持股比例②",
    "现金对价FV", "非现金资产FV", "承担债务FV", "权益证券FV", "或有对价FV",
    "合并对价FV合计③", "原持股购买日FV④", "对价账面价值合计⑤",
    "直接费用（费用化）", "初始投资成本⑥=③+④", "对价损益⑦=③-⑤",
    "享有份额①×②", "少数股东权益份额", "商誉/廉价购买利得⑧=⑥-①×②",
    "廉价购买已复核", "廉价购买复核说明",
    "对价证据索引", "评估报告索引", "综合索引", "审计结论",
]
_G7_9_MERGER_KEYS = [
    "investeeName", "acquisitionDate", "acquisitionDateEvidenceRef",
    "acquireeIdentifiableNetAssetsFV", "ownershipRatio",
    "cashConsideration", "nonCashAssetFV", "debtFV", "equitySecuritiesFV",
    "contingentConsiderationFV", "totalConsiderationFV", "priorHoldingFV",
    "considerationBookValue", "acquisitionCostsExpensed",
    "initialInvestmentCost", "considerationGainLoss",
    "shareOfFV", "nonControllingInterestShare", "goodwill",
    "bargainPurchaseReviewed", "bargainPurchaseReviewNote",
    "considerationEvidenceRef", "valuationReportRef", "indexRef", "auditConclusion",
]

_G7_9_STEP_HEADERS = [
    "公司名称", "公司标识", "次别", "交易日期", "购买比例①",
    "支付对价FV②", "交易时可辨认净资产FV③", "享有份额④=①×③", "商誉/损益⑤=②-④",
    "权益法OCI等⑥", "原持股账面价值", "原持股购买日FV",
    "是否一揽子交易", "不构成一揽子交易依据", "购买日证据索引",
    "对价证据索引", "评估报告索引", "综合索引/备注",
]
_G7_9_STEP_KEYS = [
    "companyName", "companyId", "transactionNo", "transactionDate", "purchaseRatio",
    "considerationFV", "netAssetsFVAtTxn", "shareOfFVAtTxn", "goodwillAtTxn",
    "priorEquityMethodAdjustments", "priorHoldingBookValue", "priorHoldingFV",
    "isPackageDeal", "notPackageBasis", "acquisitionDateEvidenceRef",
    "considerationEvidenceRef", "valuationReportRef", "indexRef",
]

_G7_9_REVERSE_HEADERS = [
    "交易内容", "会计上的购买方", "会计上的购买方的股东",
    "会计上的被购买方（上市公司）", "会计上的被购买方的原股东",
    "判断构成反向购买的依据", "是否构成业务", "是否构成业务及其判断依据", "索引号",
]
_G7_9_REVERSE_KEYS = [
    "transactionContent", "accountingAcquirer", "acquirerShareholders",
    "accountingAcquiree", "acquireeOriginalShareholders", "reversePurchaseBasis",
    "constitutesBusiness", "businessDeterminationBasis", "indexRef",
]

# 单sheet端点暂以合并区段为主；保留名称供通用导入导出分派使用。
_G7_9_HEADERS = _G7_9_MERGER_HEADERS
_G7_9_KEYS = _G7_9_MERGER_KEYS

# ═══════════════════════════════════════════════════════════════════════════════
# G7-10 后续计量（对齐源模板三区段：股利 / 购买少数股权 / 不丧失控制权处置）
# ═══════════════════════════════════════════════════════════════════════════════

_G7_10_DIVIDEND_HEADERS = [
    "公司名称", "分配方案股东决议", "持股比例", "宣告分派股利日", "主要股利分配政策",
    "宣告分派的股利金额", "被审计单位应分配股利", "实际入账股利", "差异", "审计结论",
]
_G7_10_DIVIDEND_KEYS = [
    "companyName", "distributionPlan", "shareholdingRatio", "declarationDate", "dividendPolicy",
    "declaredAmount", "entitledDividend", "recordedDividend", "variance", "auditConclusion",
]

_G7_10_NCI_HEADERS = [
    "公司名称", "购买前长投账面", "原持股比例", "新增持股比例①",
    "现金", "非现金资产公允价值", "债务账面价值", "权益证券面值", "或有对价",
    "购买成本②", "购买后长投账面",
    "持续计算净资产FV③", "按新增比例享有份额④", "权益调整⑤",
    "调整资本公积", "调整盈余公积", "调整未分配利润", "索引号", "审计结论",
]
_G7_10_NCI_KEYS = [
    "companyName", "priorCarryingAmount", "originalRatio", "addedRatio",
    "costCash", "costNonCashFV", "costDebtBV", "costEquityFace", "costContingent",
    "purchaseCost", "carryingAfterPurchase",
    "netAssetsFV", "shareOfNetAssets", "equityAdjustment",
    "adjCapitalReserve", "adjSurplusReserve", "adjRetainedEarnings", "indexRef", "auditConclusion",
]

_G7_10_PARTIAL_HEADERS = [
    "公司名称", "处置日长投账面①", "原持股比例②", "减少持股比例③",
    "现金", "非现金资产公允价值", "解除债务账面价值", "权益证券面值", "或有对价",
    "处置对价④", "个别报表投资收益⑤",
    "持续计算净资产FV⑥", "按减少比例享有份额⑦", "合并权益调整⑧",
    "调整资本公积", "调整盈余公积", "调整未分配利润", "索引号", "审计结论",
]
_G7_10_PARTIAL_KEYS = [
    "companyName", "bookValueAtDisposal", "originalRatio", "reducedRatio",
    "considerationCash", "considerationNonCashFV", "considerationDebtBV",
    "considerationEquityFace", "considerationContingent",
    "consideration", "individualGain",
    "netAssetsFV", "consolShare", "consolEquityAdj",
    "adjCapitalReserve", "adjSurplusReserve", "adjRetainedEarnings", "indexRef", "auditConclusion",
]

_G7_10_NUMERIC_KEYS = {
    "shareholdingRatio", "declaredAmount", "entitledDividend", "recordedDividend", "variance",
    "priorCarryingAmount", "originalRatio", "addedRatio",
    "costCash", "costNonCashFV", "costDebtBV", "costEquityFace", "costContingent",
    "purchaseCost", "carryingAfterPurchase", "netAssetsFV", "shareOfNetAssets", "equityAdjustment",
    "adjCapitalReserve", "adjSurplusReserve", "adjRetainedEarnings",
    "bookValueAtDisposal", "reducedRatio",
    "considerationCash", "considerationNonCashFV", "considerationDebtBV",
    "considerationEquityFace", "considerationContingent",
    "consideration", "individualGain", "consolShare", "consolEquityAdj",
    # 旧版成本法滚存兼容字段
    "openingBalance", "additionInvestment", "impairmentLoss",
    "declaredDividend", "investmentIncome", "closingBalance", "companyEndingBalance",
}

# 旧版单sheet（兼容导入）
_G7_10_HEADERS = [
    "被投资单位", "期初账面", "本期增加", "本期减值",
    "被投资方宣告股利", "持股比例", "应确认投资收益", "期末账面", "企业期末数",
]
_G7_10_KEYS = [
    "investeeName", "openingBalance", "additionInvestment", "impairmentLoss",
    "declaredDividend", "shareholdingRatio", "investmentIncome", "closingBalance", "companyEndingBalance",
]

# ═══════════════════════════════════════════════════════════════════════════════
# G7-11 处置非一揽子（14列，单sheet）
# ═══════════════════════════════════════════════════════════════════════════════

_G7_11_HEADERS = [
    "被投资单位", "被投资单位ID", "处置日", "处置比例", "处置对价",
    "处置日长投账面", "处置日应收股利", "处置前OCI累计", "可转损益OCI",
    "个别报表处置损益", "合并报表调整", "合并层面净资产份额", "合并处置损益",
    "合并损益手工覆盖", "审计结论", "索引",
]
_G7_11_KEYS = [
    "investeeName", "investeeId", "disposalDate", "disposalRatio", "disposalPrice",
    "disposalDateBookValue", "disposalDateDividend", "priorOCICumulative", "transferableOCI",
    "individualGain", "consolidationAdjustment", "consolidatedNetAssetShare", "consolidatedGain",
    "consolidatedGainManual", "auditConclusion", "indexRef",
]
_G7_11_CORE_HEADERS = [
    "被投资单位", "处置日", "处置比例", "处置对价",
    "处置日长投账面", "处置日应收股利", "处置前OCI累计", "可转损益OCI",
    "个别报表处置损益", "合并报表调整", "合并层面净资产份额", "合并处置损益",
    "审计结论", "索引",
]
_G7_11_OPTIONAL_HEADERS = ("被投资单位ID", "合并损益手工覆盖")
_G7_11_HEADER_ALIASES = {
    "被投资单位ID": ["investeeId", "被投资单位Id"],
    "合并损益手工覆盖": ["consolidatedGainManual", "手工覆盖"],
    "处置比例": ["处置比例(%)"],
}

# ═══════════════════════════════════════════════════════════════════════════════
# G7-12 处置一揽子（14列，单sheet）
# ═══════════════════════════════════════════════════════════════════════════════

_G7_12_HEADERS = [
    "被投资单位", "各次交易日期", "各次交易对价", "各次交易持股变动",
    "累计对价", "累计持股变动", "丧失控制权日", "丧失日长投账面",
    "丧失日剩余投资FV", "追溯调整金额", "合并处置损益", "一揽子判断依据",
    "审计结论", "索引",
]
_G7_12_KEYS = [
    "investeeName", "transactionDate", "transactionPrice", "transactionShareChange",
    "cumulativePrice", "cumulativeShareChange", "lossOfControlDate", "lossDateBookValue",
    "lossDateResidualFV", "retrospectiveAdjustment", "consolidatedGain", "packageJudgmentBasis",
    "auditConclusion", "indexRef",
]

_G7_12_SEGMENTS = [
    (
        "1-基本情况",
        ["企业名称", "注册地", "业务性质", "原持股比例", "表决权比例", "不再成为子公司的原因"],
        ["investeeName", "registeredPlace", "businessNature", "originalShareholdingRatio", "votingRatio", "disposalReason"],
    ),
    (
        "2-一揽子判断",
        [
            "企业名称", "同时或考虑彼此影响订立", "整体才能达成完整商业结果",
            "一项交易取决于其他交易", "单项不经济但整体经济", "总体结论",
            "判断依据及反向证据",
        ],
        [
            "investeeName", "judgmentSimultaneous", "judgmentCompleteResult",
            "judgmentInterdependent", "judgmentEconomicTogether", "packageJudgmentConclusion",
            "packageJudgmentBasis",
        ],
    ),
    (
        "各次交易明细",
        ["企业名称", "次别", "交易日期", "对价", "持股变动", "备注"],
        ["investeeName", "stepSeq", "stepDate", "consideration", "shareChange", "note"],
    ),
    (
        "3-交易与时点",
        [
            "企业名称", "交易日期", "股权处置价款", "处置比例", "剩余股权比例",
            "剩余股权构成", "处置方式", "丧失控制权日", "时点确定依据",
            "取得的查验资料", "索引",
        ],
        [
            "investeeName", "transactionDate", "transactionPrice", "disposalRatio",
            "remainingShareholdingRatio", "remainingInterestType", "disposalMethod",
            "lossOfControlDate", "lossOfControlBasis", "evidenceObtained", "indexRef",
        ],
    ),
    (
        "4-个别报表",
        [
            "企业名称", "处置日长投账面", "应转出长投", "剩余股权账面",
            "剩余股权公允价值", "重新计量利得损失", "联营合营可转损益OCI",
            "金融资产可转损益OCI", "不可转损益OCI", "应确认投资收益", "应转入权益",
        ],
        [
            "investeeName", "individualBookValue", "disposedBookValue", "residualBookValue",
            "residualFairValue", "remeasurementGain", "associateJointVentureRecyclableOci",
            "financialAssetRecyclableOci", "nonRecyclableOci", "individualGain", "transferToEquity",
        ],
    ),
    (
        "5-合并报表",
        [
            "企业名称", "处置日子公司净资产", "处置对应净资产份额",
            "价款与净资产份额差额", "商誉", "剩余股权公允价值确定方法及假设",
            "可转损益OCI", "前序交易差额", "合并处置损益",
        ],
        [
            "investeeName", "consolidatedNetAssets", "consolidatedNetAssetShare",
            "priceShareDifference", "goodwill", "residualFairValueMethod",
            "consolidatedRecyclableOci", "priorStepDifference", "consolidatedGain",
        ],
    ),
    (
        "6-权益法追溯",
        [
            "企业名称", "权益法比例", "原取得日至处置日净利润", "本期净利润",
            "其他综合收益", "其他所有者权益变动", "盈余公积比例", "期初未分配利润", "盈余公积",
            "投资收益", "长投-其他综合收益", "长投-其他变动",
        ],
        [
            "investeeName", "equityMethodRatio", "preDisposalProfit", "currentProfit",
            "otherComprehensiveIncome", "otherEquityChanges", "surplusReserveRate",
            "openingRetainedEarnings", "surplusReserve", "investmentIncome",
            "longTermInvestmentOci", "longTermInvestmentOtherChanges",
        ],
    ),
]

_G7_12_NUMERIC_KEYS = {
    "originalShareholdingRatio", "votingRatio", "transactionPrice", "disposalRatio",
    "remainingShareholdingRatio", "individualBookValue", "disposedBookValue",
    "residualBookValue", "residualFairValue", "remeasurementGain",
    "associateJointVentureRecyclableOci", "financialAssetRecyclableOci",
    "nonRecyclableOci", "individualGain", "transferToEquity",
    "consolidatedNetAssets", "consolidatedNetAssetShare", "priceShareDifference",
    "goodwill", "consolidatedRecyclableOci", "priorStepDifference", "consolidatedGain",
    "equityMethodRatio", "preDisposalProfit", "currentProfit",
    "otherComprehensiveIncome", "otherEquityChanges", "surplusReserveRate",
    "openingRetainedEarnings", "surplusReserve", "investmentIncome",
    "longTermInvestmentOci", "longTermInvestmentOtherChanges",
    "consideration", "shareChange", "stepSeq", "cumulativePrice", "cumulativeShareChange",
}


# ═══════════════════════════════════════════════════════════════════════════════
# G7-18 凭证检查（19列→3区段Tab）— 多sheet导出
# ═══════════════════════════════════════════════════════════════════════════════

# 区段1: 凭证基础(7列)
_G7_18_SEG1_HEADERS = [
    "日期", "凭证号", "业务内容", "对方科目", "借方", "贷方", "附件",
]
_G7_18_SEG1_KEYS = [
    "voucherDate", "voucherNo", "businessContent", "counterAccount", "debitAmount", "creditAmount", "attachment",
]

# 区段2: 核对检查(7列)
_G7_18_SEG2_HEADERS = [
    "支持性文件", "核对1-原始凭证", "核对2-授权", "核对3-账务",
    "核对4-金额", "核对5-分类", "核对6-投资收益",
]
_G7_18_SEG2_KEYS = [
    "supportingDoc", "check1Original", "check2Authorization", "check3Accounting",
    "check4Amount", "check5Classification", "check6InvestmentIncome",
]

# 区段3: 结论(5列)
_G7_18_SEG3_HEADERS = [
    "索引", "是否异常", "异常说明", "风险等级", "备注",
]
_G7_18_SEG3_KEYS = [
    "indexRef", "isAbnormal", "abnormalNote", "riskLevel", "remark",
]

# 全19列合并（用于导入解析 - 宽表模式）
_G7_18_ALL_HEADERS = _G7_18_SEG1_HEADERS + _G7_18_SEG2_HEADERS + _G7_18_SEG3_HEADERS
_G7_18_ALL_KEYS = _G7_18_SEG1_KEYS + _G7_18_SEG2_KEYS + _G7_18_SEG3_KEYS

# 3 区段名与对应列
_G7_18_SEGMENTS = [
    ("凭证基础", _G7_18_SEG1_HEADERS, _G7_18_SEG1_KEYS),
    ("核对检查", _G7_18_SEG2_HEADERS, _G7_18_SEG2_KEYS),
    ("结论", _G7_18_SEG3_HEADERS, _G7_18_SEG3_KEYS),
]


# ═══════════════════════════════════════════════════════════════════════════════
# 通用辅助
# ═══════════════════════════════════════════════════════════════════════════════

_ITEM_IDS = {
    "G7-8": "G7-8-rows",
    "G7-9": "G7-9-rows",
    "G7-10": "G7-10-rows",
    "G7-11": "G7-11-rows",
    "G7-12": "G7-12-rows",
    "G7-18": "G7-18-rows",
}

_SUPPORTED_SHEETS = set(_ITEM_IDS.keys())

# 单sheet兼容规格（G7-10/G7-11/G7-12）
_SINGLE_SHEET_SPECS: dict[str, dict[str, Any]] = {
    "G7-10": {
        "headers": _G7_10_DIVIDEND_HEADERS,
        "field_keys": _G7_10_DIVIDEND_KEYS,
        "title": "G7-10 后续计量（三区段）",
        "guidance": [
            "G7-10 请使用三区段模板（股利/购买少数股权/不丧失控制权处置）。",
            "本单sheet规格仅作兼容保留；导出请走专用多sheet工作簿。",
        ],
    },
    "G7-11": {
        "headers": _G7_11_HEADERS,
        "field_keys": _G7_11_KEYS,
        "title": "G7-11 处置测试（非一揽子）",
        "guidance": [
            "G7-11 非一揽子处置测试 编制说明",
            "",
            "处置比例以小数填写（如 0.30 表示处置30%股权），范围 0~1。",
            "个别报表处置损益 = 处置对价 - 处置日长投账面 - 处置日应收股利 + 可转损益OCI。",
            "合并处置损益默认 = 个别损益 + 合并调整 − 净资产份额；手工覆盖填「是」可保留 Excel 值。",
            "处置前OCI累计为备查列，不进入个别损益公式；入账用「可转损益OCI」。",
            "被投资单位ID 与 G7-4 行 id 对齐（可空）。",
            "审计结论填写处置定价公允性、关联方交易判断。",
        ],
    },
    "G7-12": {
        "headers": _G7_12_HEADERS,
        "field_keys": _G7_12_KEYS,
        "title": "G7-12 处置测试（一揽子交易）",
        "guidance": [
            "G7-12 一揽子交易处置测试 编制说明",
            "",
            "一揽子交易：多次交易实质上构成一项整体安排。",
            "累计对价/累计持股变动为前序交易累加值。",
            "丧失控制权日统一确认全部处置损益。",
            "追溯调整金额 = 丧失日剩余投资FV - 丧失日长投账面。",
            "一揽子判断依据为必填项，需说明判断理由。",
        ],
    },
}


def _validate_sheet(sheet: str) -> None:
    if sheet not in _SUPPORTED_SHEETS:
        raise HTTPException(400, f"不支持的sheet: {sheet}。支持: {sorted(_SUPPORTED_SHEETS)}")


def _yes_no_to_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return raw != 0
    s = str(raw or "").strip().lower()
    return s in {"是", "true", "1", "y", "yes"}


def _normalize_ratio_to_fraction(raw: Any) -> float:
    """处置比例：Excel 可能填 30 表示 30%，已是小数则保持。"""
    v = safe_float(raw)
    if abs(v) > 1.0000001:
        return round(v / 100.0, 8)
    return v


def _recalculate_g7_11_row(row: dict) -> dict:
    """与前端 recalcDisposalSingleRow 口径一致。"""
    svc = G7SubsidiaryService
    price = safe_float(row.get("disposalPrice"))
    book = safe_float(row.get("disposalDateBookValue"))
    dividend = safe_float(row.get("disposalDateDividend"))
    oci = safe_float(row.get("transferableOCI"))
    individual = round(svc.calc_disposal_gain(price, book, dividend, oci), 2)
    row["individualGain"] = individual

    manual = _yes_no_to_bool(row.get("consolidatedGainManual"))
    row["consolidatedGainManual"] = manual
    if not manual:
        adj = safe_float(row.get("consolidationAdjustment"))
        na_share = safe_float(row.get("consolidatedNetAssetShare"))
        row["consolidatedGain"] = round(individual + adj - na_share, 2)
    else:
        row["consolidatedGain"] = round(safe_float(row.get("consolidatedGain")), 2)

    # 比例归一（若仍为百分数）
    if "disposalRatio" in row:
        row["disposalRatio"] = _normalize_ratio_to_fraction(row.get("disposalRatio"))
    return row


def _normalize_g7_11_rows_import(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        if "disposalRatio" in d:
            d["disposalRatio"] = _normalize_ratio_to_fraction(d.get("disposalRatio"))
        if "consolidatedGainManual" in d:
            d["consolidatedGainManual"] = _yes_no_to_bool(d.get("consolidatedGainManual"))
        _recalculate_g7_11_row(d)
        out.append(d)
    return out


def _prepare_g7_11_rows_export(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for r in rows:
        d = _recalculate_g7_11_row(dict(r))
        if "consolidatedGainManual" in d:
            val = d.get("consolidatedGainManual")
            d["consolidatedGainManual"] = "是" if _yes_no_to_bool(val) else "否"
        out.append(d)
    return out


def _parse_g7_11_sheet_rows(content: bytes) -> tuple[list[dict], list[str], list[str]]:
    """按表头名解析；强制旧 14 列，ID/手工覆盖可缺。"""
    try:
        actual, raw = parse_upload_xlsx(
            content,
            _G7_11_CORE_HEADERS,
            header_row=2,
            header_aliases=_G7_11_HEADER_ALIASES,
            require_all_headers=True,
        )
    except ValueError as e:
        return [], [str(e)], []

    warnings: list[str] = []
    missing_opt = [h for h in _G7_11_OPTIONAL_HEADERS if h not in actual]
    if missing_opt:
        warnings.append(f"兼容旧模板：缺列 {', '.join(missing_opt)} 已按空值导入")

    errors: list[str] = []
    rows: list[dict] = []
    header_idx = {h: i for i, h in enumerate(actual)}
    for i, r in enumerate(raw, start=1):
        if i > ROW_LIMIT:
            errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
            break
        values = list(r)
        parsed: dict[str, Any] = {"id": str(uuid4())}
        for h, key in zip(_G7_11_HEADERS, _G7_11_KEYS):
            idx = header_idx.get(h)
            raw_val = values[idx] if idx is not None and idx < len(values) else None
            if key in ("consolidatedGainManual",):
                parsed[key] = safe_str(raw_val)
            elif is_numeric_field_key(key) or key in {
                "disposalRatio", "disposalPrice", "disposalDateBookValue",
                "disposalDateDividend", "priorOCICumulative", "transferableOCI",
                "individualGain", "consolidationAdjustment",
                "consolidatedNetAssetShare", "consolidatedGain",
            }:
                parsed[key] = safe_float(raw_val)
            else:
                parsed[key] = safe_str(raw_val)
        rows.append(parsed)
    return rows, errors, warnings


# ═══════════════════════════════════════════════════════════════════════════════
# G7-12 原底稿六区段导入导出
# ═══════════════════════════════════════════════════════════════════════════════

def _g7_12_recalculate(source: dict[str, Any]) -> dict[str, Any]:
    """复核原底稿公式，导出计算结果；不信任客户端上传的公式列。"""
    row = dict(source)
    steps = row.get("steps") if isinstance(row.get("steps"), list) else []
    if steps:
        cum_price = round(sum(safe_float(s.get("consideration")) for s in steps), 2)
        cum_share = round(sum(abs(safe_float(s.get("shareChange"))) for s in steps), 6)
        if cum_price:
            row["transactionPrice"] = cum_price
            row["cumulativePrice"] = cum_price
        if cum_share:
            row["disposalRatio"] = cum_share
            row["cumulativeShareChange"] = cum_share
    original = safe_float(row.get("originalShareholdingRatio"))
    disposal = abs(safe_float(
        row.get("disposalRatio")
        or row.get("transactionShareChange")
        or row.get("shareholdingChange")
        or row.get("cumulativeShareChange")
    ))
    ratio_of_original = disposal / original if original else 0.0
    remaining = max(0.0, original - disposal)
    book_value = safe_float(
        row.get("individualBookValue")
        or row.get("lossDateBookValue")
        or row.get("bookValueAtLoss")
    )
    residual_fv = safe_float(
        row.get("residualFairValue")
        or row.get("lossDateResidualFV")
        or row.get("remainingInvestmentFV")
        or row.get("remainingFV")
    )
    disposed_book = round(book_value * ratio_of_original, 2)
    residual_book = round(book_value - disposed_book, 2)
    remeasurement = round(residual_fv - residual_book, 2)
    recyclable_oci = round(
        safe_float(row.get("associateJointVentureRecyclableOci")) * ratio_of_original
        + safe_float(row.get("financialAssetRecyclableOci")),
        2,
    )
    consolidated_net_assets = safe_float(row.get("consolidatedNetAssets"))
    consolidated_share = round(consolidated_net_assets * ratio_of_original, 2)
    equity_ratio = safe_float(row.get("equityMethodRatio")) or remaining
    txn_price = safe_float(row.get("transactionPrice") or row.get("cumulativePrice"))
    surplus_rate = safe_float(row.get("surplusReserveRate"))
    if surplus_rate <= 0 or surplus_rate >= 1:
        surplus_rate = 0.1

    row.update({
        "remainingShareholdingRatio": round(remaining, 6),
        "disposedBookValue": disposed_book,
        "residualBookValue": residual_book,
        "remeasurementGain": remeasurement,
        "individualGain": round(remeasurement + recyclable_oci, 2),
        "transferToEquity": round(
            safe_float(row.get("nonRecyclableOci")) * ratio_of_original, 2
        ),
        "consolidatedNetAssetShare": consolidated_share,
        "priceShareDifference": round(txn_price - consolidated_share, 2),
        "consolidatedGain": round(
            txn_price
            + residual_fv
            - consolidated_net_assets
            - safe_float(row.get("goodwill"))
            + safe_float(row.get("consolidatedRecyclableOci"))
            + safe_float(row.get("priorStepDifference")),
            2,
        ),
        "surplusReserveRate": surplus_rate,
        "openingRetainedEarnings": round(
            equity_ratio * safe_float(row.get("preDisposalProfit")) * (1 - surplus_rate), 2
        ),
        "surplusReserve": round(
            equity_ratio * safe_float(row.get("preDisposalProfit")) * surplus_rate, 2
        ),
        "investmentIncome": round(
            equity_ratio * safe_float(row.get("currentProfit")), 2
        ),
        "longTermInvestmentOci": round(
            equity_ratio * safe_float(row.get("otherComprehensiveIncome")), 2
        ),
        "longTermInvestmentOtherChanges": round(
            equity_ratio * safe_float(row.get("otherEquityChanges")), 2
        ),
    })
    return row


def _build_g7_12_workbook(
    rows: list[dict], *, template_only: bool = False
) -> Workbook:
    """按原底稿证据链拆成六个 worksheet，避免一张超宽表掩盖审计逻辑。"""
    wb = Workbook()
    wb.remove(wb.active)  # type: ignore[arg-type]
    calculated_rows = [
        _g7_12_recalculate(row) for row in ([] if template_only else rows)
    ]
    for sheet_name, headers, keys in _G7_12_SEGMENTS:
        ws = wb.create_sheet(sheet_name)
        ws.append([f"G7-12 处置子公司测试表（一揽子交易）— {sheet_name}"])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
        ws["A1"].font = Font(bold=True, size=14)
        ws.append(headers)
        for cell in ws[2]:
            cell.font = Font(bold=True)
        ws.freeze_panes = "B3"
        ws.auto_filter.ref = f"A2:{get_column_letter(len(headers))}2"
        for column_index, header in enumerate(headers, start=1):
            ws.column_dimensions[get_column_letter(column_index)].width = min(
                38, max(14, len(header) * 2 + 4)
            )
        if sheet_name == "2-一揽子判断":
            validation = DataValidation(
                type="list", formula1='"yes,no,na"', allow_blank=True
            )
            ws.add_data_validation(validation)
            validation.add("B3:F502")
        if sheet_name == "各次交易明细":
            if template_only:
                ws.append(["示例子公司", 1, "2025-01-15", 0, 0, "第1次处置"])
            else:
                for row in calculated_rows:
                    steps = row.get("steps") if isinstance(row.get("steps"), list) else []
                    for step in steps:
                        ws.append([
                            row.get("investeeName") or "",
                            step.get("seq") or "",
                            step.get("stepDate") or "",
                            step.get("consideration") or 0,
                            step.get("shareChange") or 0,
                            step.get("note") or "",
                        ])
            continue
        for row in calculated_rows:
            ws.append(export_row_by_keys(row, keys))
        for key_index, key in enumerate(keys, start=1):
            if key in {
                "originalShareholdingRatio", "votingRatio", "disposalRatio",
                "remainingShareholdingRatio", "equityMethodRatio", "surplusReserveRate",
                "shareChange",
            }:
                for cell in ws.iter_cols(
                    min_col=key_index, max_col=key_index, min_row=3,
                    max_row=max(3, ws.max_row)
                ):
                    for item in cell:
                        item.number_format = "0.00%"
    return wb


def _parse_g7_12_import(content: bytes) -> tuple[list[dict], list[str]]:
    """按行号合并六区段；公式结果列导入后由后端统一重算。各次交易明细按企业名称挂到 steps。"""
    errors: list[str] = []
    rows_by_index: dict[int, dict[str, Any]] = {}
    steps_by_name: dict[str, list[dict[str, Any]]] = {}
    try:
        wb = load_workbook(io.BytesIO(content), data_only=True, read_only=False)
    except Exception:
        return [], ["无法解析xlsx文件"]

    formula_keys = {
        "disposedBookValue", "residualBookValue", "remeasurementGain",
        "individualGain", "transferToEquity", "consolidatedNetAssetShare",
        "priceShareDifference", "consolidatedGain", "openingRetainedEarnings",
        "surplusReserve", "investmentIncome", "longTermInvestmentOci",
        "longTermInvestmentOtherChanges",
    }
    matched = False
    for sheet_name, headers, keys in _G7_12_SEGMENTS:
        if sheet_name not in wb.sheetnames:
            if sheet_name == "各次交易明细":
                continue  # 旧模板可无此 sheet
            errors.append(f"缺少工作表[{sheet_name}]")
            continue
        matched = True
        ws = wb[sheet_name]
        actual_headers = [
            safe_str(cell.value)
            for cell in next(ws.iter_rows(min_row=2, max_row=2))
        ]
        missing = [header for header in headers if header not in actual_headers]
        if missing:
            errors.append(f"工作表[{sheet_name}]缺少列: {', '.join(missing)}")
            continue

        if sheet_name == "各次交易明细":
            for values in ws.iter_rows(min_row=3, values_only=True):
                if all(value in (None, "") for value in values):
                    continue
                payload: dict[str, Any] = {}
                for header, key in zip(headers, keys):
                    column_index = actual_headers.index(header)
                    raw = values[column_index] if column_index < len(values) else None
                    payload[key] = (
                        safe_float(raw) if key in _G7_12_NUMERIC_KEYS else safe_str(raw)
                    )
                name = safe_str(payload.get("investeeName"))
                if not name:
                    continue
                steps_by_name.setdefault(name, []).append({
                    "id": str(uuid4()),
                    "seq": int(payload.get("stepSeq") or len(steps_by_name[name]) + 1),
                    "stepDate": safe_str(payload.get("stepDate")),
                    "consideration": safe_float(payload.get("consideration")),
                    "shareChange": safe_float(payload.get("shareChange")),
                    "note": safe_str(payload.get("note")),
                })
            continue

        for row_index, values in enumerate(
            ws.iter_rows(min_row=3, values_only=True)
        ):
            if row_index >= ROW_LIMIT:
                errors.append(f"工作表[{sheet_name}]超过{ROW_LIMIT}行，已截断")
                break
            if all(value in (None, "") for value in values):
                continue
            target = rows_by_index.setdefault(
                row_index, {"id": str(uuid4()), "seq": row_index + 1}
            )
            for header, key in zip(headers, keys):
                if key in formula_keys:
                    continue
                column_index = actual_headers.index(header)
                raw = values[column_index] if column_index < len(values) else None
                target[key] = (
                    safe_float(raw) if key in _G7_12_NUMERIC_KEYS else safe_str(raw)
                )

    wb.close()
    if not matched:
        return [], ["未找到G7-12六区段工作表"]
    for row in rows_by_index.values():
        name = safe_str(row.get("investeeName"))
        if name and name in steps_by_name:
            row["steps"] = steps_by_name[name]
    rows = [_g7_12_recalculate(row) for _, row in sorted(rows_by_index.items())]
    return rows, errors


# ═══════════════════════════════════════════════════════════════════════════════
# G7-8 原底稿三类业务导入导出
# ═══════════════════════════════════════════════════════════════════════════════

_G7_8_NUMERIC_KEYS = {
    "ownerEquityBookValue", "ownershipRatio", "initialInvestmentCost",
    "cashConsideration", "nonCashAssetBookValue", "debtBookValue",
    "equitySecuritiesFaceValue", "contingentConsideration", "totalConsideration",
    "capitalReserveRetainedEarningsAdjustment", "availableCapitalReserve",
    "transactionNo", "purchaseRatio",
    "consideration", "netAssetsBookValue", "priorHoldingBookValue",
    "priorInvestmentAdjustments",
}


def _g7_8_recalculate_merger(row: dict[str, Any]) -> dict[str, Any]:
    ratio = safe_float(row.get("ownershipRatio"))
    equity = safe_float(row.get("ownerEquityBookValue"))
    initial_cost = round(equity * ratio, 2)
    total_consideration = round(sum(safe_float(row.get(key)) for key in (
        "cashConsideration", "nonCashAssetBookValue", "debtBookValue",
        "equitySecuritiesFaceValue", "contingentConsideration",
    )), 2)
    row["initialInvestmentCost"] = initial_cost
    row["totalConsideration"] = total_consideration
    row["capitalReserveRetainedEarningsAdjustment"] = round(
        initial_cost - total_consideration, 2,
    )
    return row


def _build_g7_8_workbook(rows: list[dict], *, template_only: bool = False) -> Workbook:
    """按原底稿三部分生成G7-8工作簿。"""
    wb = Workbook()
    wb.remove(wb.active)  # type: ignore[arg-type]
    specs = [
        ("1-合并方式取得", _G7_8_MERGER_HEADERS, _G7_8_MERGER_KEYS, "merger"),
        ("2-分步实现合并", _G7_8_STEP_HEADERS, _G7_8_STEP_KEYS, "step"),
        ("3-反向购买", _G7_8_REVERSE_HEADERS, _G7_8_REVERSE_KEYS, "reverse"),
    ]
    for title, headers, keys, section in specs:
        ws = wb.create_sheet(title)
        ws.append([f"G7-8 子公司初始计量测试（同控）— {title}"])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
        ws["A1"].font = Font(bold=True, size=12)
        ws.append(headers)
        ws.freeze_panes = "A3"
        for col_idx in range(1, len(headers) + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 16
        if section == "merger":
            conclusion_validation = DataValidation(
                type="list",
                formula1='"无差异,差异可接受,差异需调整"',
                allow_blank=True,
            )
            ws.add_data_validation(conclusion_validation)
            conclusion_validation.add("S3:S502")
            policy_validation = DataValidation(
                type="list",
                formula1='"是,否"',
                allow_blank=True,
            )
            ws.add_data_validation(policy_validation)
            policy_validation.add("D3:D502")
        if section == "step":
            package_validation = DataValidation(
                type="list",
                formula1='"是,否"',
                allow_blank=True,
            )
            ws.add_data_validation(package_validation)
            package_validation.add("K3:K502")
        if not template_only:
            for source in rows:
                source_section = safe_str(source.get("section")) or "merger"
                if source_section != section:
                    continue
                row = dict(source)
                if section == "merger":
                    row = _g7_8_recalculate_merger(row)
                ws.append(export_row_by_keys(row, keys))
        # merger: 出资比例②=列7；step: 购买比例①=列6
        ratio_column = 7 if section == "merger" else 6 if section == "step" else None
        if ratio_column:
            for row_index in range(3, max(ws.max_row, 502) + 1):
                ws.cell(row=row_index, column=ratio_column).number_format = "0.00%"

    # 公式对照汇总（贴近原底稿一页多区段阅读习惯）
    summary = wb.create_sheet("公式对照")
    summary.append(["区段", "公司/交易", "关键公式", "结果金额", "调整方向提示"])
    summary["A1"].font = Font(bold=True)
    for source in ([] if template_only else rows):
        section = safe_str(source.get("section")) or "merger"
        if section == "merger":
            row = _g7_8_recalculate_merger(dict(source))
            adj = safe_float(row.get("capitalReserveRetainedEarningsAdjustment"))
            hint = (
                "无差额" if abs(adj) < 0.005
                else ("贷记资本公积" if adj > 0 else "冲减资本公积/留存收益")
            )
            summary.append([
                "一次合并",
                safe_str(row.get("investeeName")),
                "⑤=③−④",
                adj,
                hint,
            ])
        elif section == "step":
            prior_bv = safe_float(source.get("priorHoldingBookValue"))
            consideration = safe_float(source.get("consideration"))
            prior_adj = safe_float(source.get("priorInvestmentAdjustments"))
            net_assets = safe_float(source.get("netAssetsBookValue"))
            ratio = safe_float(source.get("purchaseRatio"))
            initial = round(net_assets * ratio, 2)
            adj = round(consideration + prior_bv + prior_adj - initial, 2)
            hint = (
                "无差额" if abs(adj) < 0.005
                else ("冲减资本公积/留存收益" if adj > 0 else "贷记资本公积")
            )
            summary.append([
                "分步合并(单次)",
                safe_str(source.get("companyName")),
                "⑥≈②+原账面+③−⑤（按行近似，汇总见系统）",
                adj,
                hint,
            ])
    for col_idx in range(1, 6):
        summary.column_dimensions[get_column_letter(col_idx)].width = 28

    guide = wb.create_sheet("编制说明")
    guidance = [
        "G7-8 子公司初始计量测试表（同一控制）",
        "1. 合并方式取得：填写合并日；初始投资成本③=被合并方所有者权益账面价值①×合并后出资比例②；支付对价④为各类对价账面价值合计；调整金额⑤=③-④。",
        "2. 分步实现同控合并（不构成一揽子交易）：填写取得控制权的合并日；合并日初始成本⑤=合并日净资产账面价值④×累计持股比例①；调整金额⑥=累计对价②+原持股账面价值+原投资累计调整③−初始成本⑤。",
        "3. 若构成一揽子交易，应作为一次取得控制权处理，不适用分步合并区段。",
        "4. 反向购买：识别会计上的购买方，并判断会计上的被购买方是否构成业务。",
        "5. 合并前会计政策不一致时，应先统一会计政策；同控合并不确认商誉。",
        "6. 可用资本公积不足冲减时，差额冲减留存收益并在附注披露。",
        "7. 比例以小数填写，如0.32表示32%。",
        "8. 建议名单与 G7-7（控制+同控）、G7-2/G7-4 子公司勾稽一致。",
    ]
    for line in guidance:
        guide.append([line])
    guide.column_dimensions["A"].width = 120
    return wb


def _parse_g7_8_import(content: bytes) -> tuple[list[dict], list[str]]:
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    rows: list[dict] = []
    errors: list[str] = []
    specs = [
        ("1-合并方式取得", _G7_8_MERGER_HEADERS, _G7_8_MERGER_KEYS, "merger"),
        ("2-分步实现合并", _G7_8_STEP_HEADERS, _G7_8_STEP_KEYS, "step"),
        ("3-反向购买", _G7_8_REVERSE_HEADERS, _G7_8_REVERSE_KEYS, "reverse"),
    ]
    matched = False
    optional_headers = {
        "合并日", "会计政策一致", "政策调整说明", "可用资本公积",
        "原持股账面价值", "是否一揽子交易",
    }
    for sheet_name, expected_headers, keys, section in specs:
        if sheet_name not in wb.sheetnames:
            continue
        matched = True
        ws = wb[sheet_name]
        actual_headers = [
            safe_str(cell.value)
            for cell in next(ws.iter_rows(min_row=2, max_row=2))
        ]
        missing = [
            header for header in expected_headers
            if header not in actual_headers and header not in optional_headers
        ]
        if missing:
            errors.append(f"工作表[{sheet_name}]缺少列: {', '.join(missing)}")
            continue
        for row_index, values in enumerate(ws.iter_rows(min_row=3, values_only=True), start=3):
            if all(value is None for value in values):
                continue
            if len(rows) >= ROW_LIMIT:
                errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
                break
            parsed: dict[str, Any] = {
                "id": str(uuid4()),
                "section": section,
                "seq": row_index - 2,
            }
            for header, key in zip(expected_headers, keys):
                if header not in actual_headers:
                    parsed[key] = 0.0 if key in _G7_8_NUMERIC_KEYS else ""
                    continue
                column_index = actual_headers.index(header)
                raw = values[column_index] if column_index < len(values) else None
                parsed[key] = safe_float(raw) if key in _G7_8_NUMERIC_KEYS else safe_str(raw)
            if section == "merger":
                _g7_8_recalculate_merger(parsed)
            rows.append(parsed)

    if not matched:
        # 兼容旧版9列平表，将其迁移为“一次合并”数据。
        ws = wb.active
        if ws is None:
            wb.close()
            return [], ["xlsx文件中无活动工作表"]
        old_headers = [
            "被投资单位", "合并日", "合并方式", "被合并方账面净资产",
            "持股比例", "享有份额", "初始投资成本", "支付对价", "差额处理",
        ]
        actual_headers = [safe_str(cell.value) for cell in next(ws.iter_rows(min_row=2, max_row=2))]
        if not all(header in actual_headers for header in old_headers):
            wb.close()
            return [], ["无法识别G7-8表头，请使用最新导出模板"]
        for row_index, values in enumerate(ws.iter_rows(min_row=3, values_only=True), start=1):
            if all(value is None for value in values):
                continue
            def value_of(header: str) -> Any:
                idx = actual_headers.index(header)
                return values[idx] if idx < len(values) else None
            parsed = {
                "id": str(uuid4()),
                "section": "merger",
                "seq": row_index,
                "investeeName": safe_str(value_of("被投资单位")),
                "finalController": "",
                "ownerEquityBookValue": safe_float(value_of("被合并方账面净资产")),
                "ownershipRatio": safe_float(value_of("持股比例")),
                "cashConsideration": safe_float(value_of("支付对价")),
                "nonCashAssetBookValue": 0.0,
                "debtBookValue": 0.0,
                "equitySecuritiesFaceValue": 0.0,
                "contingentConsideration": 0.0,
                "adjustmentTreatment": safe_str(value_of("差额处理")),
                "indexRef": "",
                "auditConclusion": "",
            }
            rows.append(_g7_8_recalculate_merger(parsed))
    wb.close()
    return rows, errors


# ═══════════════════════════════════════════════════════════════════════════════
# G7-9 原底稿三类业务导入导出
# ═══════════════════════════════════════════════════════════════════════════════

_G7_9_NUMERIC_KEYS = {
    "cashConsideration", "nonCashAssetFV", "debtFV", "equitySecuritiesFV",
    "contingentConsiderationFV", "totalConsiderationFV", "priorHoldingFV",
    "considerationBookValue", "acquisitionCostsExpensed", "initialInvestmentCost",
    "considerationGainLoss", "acquireeIdentifiableNetAssetsFV", "ownershipRatio",
    "shareOfFV", "nonControllingInterestShare", "goodwill", "transactionNo",
    "purchaseRatio", "considerationFV", "netAssetsFVAtTxn", "shareOfFVAtTxn",
    "goodwillAtTxn", "priorEquityMethodAdjustments", "priorHoldingBookValue",
    # 旧字段兼容
    "netAssetsBookValueAtTxn", "priorOCIReclassify",
}


def _g7_9_recalculate_merger(row: dict[str, Any]) -> dict[str, Any]:
    """对齐源底稿：③合计；⑥=③+④；⑦=③−⑤；⑧=⑥−①×②。"""
    consideration = round(sum(safe_float(row.get(key)) for key in (
        "cashConsideration", "nonCashAssetFV", "debtFV",
        "equitySecuritiesFV", "contingentConsiderationFV",
    )), 2)
    prior_fv = safe_float(row.get("priorHoldingFV"))
    book_value = safe_float(row.get("considerationBookValue"))
    net_assets_fv = safe_float(row.get("acquireeIdentifiableNetAssetsFV"))
    ratio = safe_float(row.get("ownershipRatio"))
    share = round(net_assets_fv * ratio, 2)
    initial_cost = round(consideration + prior_fv, 2)
    row.update({
        "totalConsiderationFV": consideration,
        # 中介费用按CAS20费用化，不进入⑥/⑧
        "initialInvestmentCost": initial_cost,
        "considerationGainLoss": round(consideration - book_value, 2),
        "shareOfFV": share,
        "nonControllingInterestShare": round(
            net_assets_fv * max(0.0, 1.0 - ratio), 2
        ),
        "goodwill": round(initial_cost - share, 2),
    })
    return row


def _g7_9_recalculate_step(row: dict[str, Any]) -> dict[str, Any]:
    """分步：④=①×③；⑤=②−④。兼容旧 netAssetsBookValueAtTxn 字段。"""
    if row.get("netAssetsFVAtTxn") in (None, "") and row.get("netAssetsBookValueAtTxn") not in (None, ""):
        row["netAssetsFVAtTxn"] = row.get("netAssetsBookValueAtTxn")
    if row.get("priorEquityMethodAdjustments") in (None, "") and row.get("priorOCIReclassify") not in (None, ""):
        row["priorEquityMethodAdjustments"] = row.get("priorOCIReclassify")
    ratio = safe_float(row.get("purchaseRatio"))
    net_fv = safe_float(row.get("netAssetsFVAtTxn"))
    consideration = safe_float(row.get("considerationFV"))
    share = round(ratio * net_fv, 2)
    row["shareOfFVAtTxn"] = share
    row["goodwillAtTxn"] = round(consideration - share, 2)
    row["adjustmentScope"] = "transaction"
    return row


def _g7_9_step_company_id(row: dict[str, Any], fallback: str) -> str:
    """Excel中的公司标识可留空；按公司名生成稳定技术标识供前端分组。"""
    supplied = safe_str(row.get("companyId")).strip()
    if supplied:
        return supplied
    company_name = safe_str(row.get("companyName")).strip()
    identity = company_name or fallback
    return f"step-company-{uuid5(NAMESPACE_URL, f'g7-9:{identity}')}"


def _build_g7_9_workbook(rows: list[dict], *, template_only: bool = False) -> Workbook:
    """按一次购买、分步合并、反向购买生成G7-9工作簿。"""
    wb = Workbook()
    wb.remove(wb.active)  # type: ignore[arg-type]
    specs = [
        ("1-一次购买取得", _G7_9_MERGER_HEADERS, _G7_9_MERGER_KEYS, "merger"),
        ("2-分步实现合并", _G7_9_STEP_HEADERS, _G7_9_STEP_KEYS, "step"),
        ("3-反向购买", _G7_9_REVERSE_HEADERS, _G7_9_REVERSE_KEYS, "reverse"),
    ]
    for title, headers, keys, section in specs:
        ws = wb.create_sheet(title)
        ws.append([f"G7-9 子公司初始计量测试（非同控）— {title}"])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
        ws["A1"].font = Font(bold=True, size=12)
        ws.append(headers)
        for cell in ws[2]:
            cell.font = Font(bold=True)
        ws.freeze_panes = "A3"
        ws.auto_filter.ref = f"A2:{get_column_letter(len(headers))}2"
        for col_idx, header in enumerate(headers, start=1):
            ws.column_dimensions[get_column_letter(col_idx)].width = min(
                32, max(14, len(header) * 2 + 2)
            )
        if section == "merger":
            conclusion_validation = DataValidation(
                type="list",
                formula1='"无差异,差异可接受,差异需调整"',
                allow_blank=True,
            )
            ws.add_data_validation(conclusion_validation)
            conclusion_validation.add("Y3:Y502")
            bargain_validation = DataValidation(
                type="list", formula1='"是,否"', allow_blank=True,
            )
            ws.add_data_validation(bargain_validation)
            bargain_validation.add("T3:T502")
        if section == "step":
            package_validation = DataValidation(
                type="list", formula1='"是,否"', allow_blank=True
            )
            ws.add_data_validation(package_validation)
            package_validation.add("M3:M502")
        if section == "reverse":
            business_validation = DataValidation(
                type="list", formula1='"是,否"', allow_blank=True
            )
            ws.add_data_validation(business_validation)
            business_validation.add("G3:G502")
        if not template_only:
            for source in rows:
                source_section = safe_str(source.get("section")) or "merger"
                if source_section != section:
                    continue
                row = dict(source)
                if section == "merger":
                    row = _g7_9_recalculate_merger(row)
                elif section == "step":
                    row["companyId"] = _g7_9_step_company_id(
                        row, safe_str(row.get("id")) or str(row.get("seq") or "")
                    )
                    row = _g7_9_recalculate_step(row)
                ws.append(export_row_by_keys(row, keys))
        ratio_column = 5 if section == "merger" else 5 if section == "step" else None
        if ratio_column:
            for row_index in range(3, max(ws.max_row, 502) + 1):
                ws.cell(row=row_index, column=ratio_column).number_format = "0.00%"

    summary = wb.create_sheet("公式对照")
    summary.append(["区段", "公司/交易", "关键公式", "结果金额", "处理提示"])
    summary["A1"].font = Font(bold=True)
    for source in ([] if template_only else rows):
        section = safe_str(source.get("section")) or "merger"
        if section == "merger":
            row = _g7_9_recalculate_merger(dict(source))
            goodwill = safe_float(row.get("goodwill"))
            summary.append([
                "一次购买",
                safe_str(row.get("investeeName")),
                "⑧=⑥−①×②；⑥=③+④；⑦=③−⑤",
                goodwill,
                (
                    "无商誉/廉价购买利得" if abs(goodwill) < 0.005
                    else ("确认商誉" if goodwill > 0 else "须复核后确认廉价购买利得")
                ),
            ])
        elif section == "step":
            row = _g7_9_recalculate_step(dict(source))
            summary.append([
                "分步合并",
                safe_str(row.get("companyName")),
                "④=①×③；⑤=②−④；个别⑦=累计②+⑥",
                safe_float(row.get("goodwillAtTxn")),
                "一揽子交易不适用本区段",
            ])
    for col_idx in range(1, 6):
        summary.column_dimensions[get_column_letter(col_idx)].width = 34

    guide = wb.create_sheet("编制说明")
    guidance = [
        "G7-9 子公司初始计量测试表（非同一控制）— 对齐源底稿公式编号",
        "1. 一次购买：③=对价FV合计；⑥=③+④（④为购买日前持股于购买日的FV）；⑦=③−⑤（对价FV与账面差额计入损益）；⑧=⑥−①×②。",
        "2. 审计、法律、评估等中介费用于发生时计入当期损益；发行证券交易费用计入证券初始确认金额。",
        "3. 取得投资时点与评估基准日有时间差时，注意公允价值调整。",
        "4. 分步合并（非一揽子）：每笔④=①×③、⑤=②−④；个别报表⑦=累计支付对价②+权益法OCI等⑥。",
        "5. 一揽子交易应作为一次取得控制权，不适用分步区段。",
        "6. 反向购买须判断会计被购买方是否构成业务；不构成业务时按资产购置处理，不得确认商誉。",
        "7. 廉价购买利得须勾选已复核计量并说明复核过程。",
        "8. 中国企业会计准则下少数股东权益按可辨认净资产公允价值份额计量，不提供IFRS 3全商誉选择。",
        "9. 比例以小数填写，如0.60表示60%。",
        "10. 建议名单与G7-7（控制+非同控）、G7-2/G7-4子公司勾稽一致。",
    ]
    for line in guidance:
        guide.append([line])
    guide.column_dimensions["A"].width = 120
    return wb


def _parse_g7_9_import(content: bytes) -> tuple[list[dict], list[str]]:
    """解析三区段工作簿；兼容旧版9列表。"""
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    rows: list[dict] = []
    errors: list[str] = []
    specs = [
        ("1-一次购买取得", _G7_9_MERGER_HEADERS, _G7_9_MERGER_KEYS, "merger"),
        ("2-分步实现合并", _G7_9_STEP_HEADERS, _G7_9_STEP_KEYS, "step"),
        ("3-反向购买", _G7_9_REVERSE_HEADERS, _G7_9_REVERSE_KEYS, "reverse"),
    ]
    matched = False
    formula_keys = {
        "totalConsiderationFV", "initialInvestmentCost", "considerationGainLoss",
        "shareOfFV", "nonControllingInterestShare", "goodwill",
        "shareOfFVAtTxn", "goodwillAtTxn",
    }
    for sheet_name, expected_headers, keys, section in specs:
        if sheet_name not in wb.sheetnames:
            continue
        matched = True
        ws = wb[sheet_name]
        actual_headers = [
            safe_str(cell.value)
            for cell in next(ws.iter_rows(min_row=2, max_row=2))
        ]
        missing = [header for header in expected_headers if header not in actual_headers]
        if missing:
            errors.append(f"工作表[{sheet_name}]缺少列: {', '.join(missing)}")
            continue
        for row_index, values in enumerate(
            ws.iter_rows(min_row=3, values_only=True), start=3
        ):
            if all(value is None for value in values):
                continue
            if len(rows) >= ROW_LIMIT:
                errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
                break
            parsed: dict[str, Any] = {
                "id": str(uuid4()),
                "section": section,
                "seq": row_index - 2,
            }
            for header, key in zip(expected_headers, keys):
                if key in formula_keys:
                    continue
                column_index = actual_headers.index(header)
                raw = values[column_index] if column_index < len(values) else None
                parsed[key] = (
                    safe_float(raw) if key in _G7_9_NUMERIC_KEYS else safe_str(raw)
                )
            if section == "merger":
                _g7_9_recalculate_merger(parsed)
            elif section == "step":
                parsed["companyId"] = _g7_9_step_company_id(
                    parsed, f"import-row-{row_index}"
                )
                _g7_9_recalculate_step(parsed)
            rows.append(parsed)

    if not matched:
        ws = wb.active
        if ws is None:
            wb.close()
            return [], ["xlsx文件中无活动工作表"]
        old_headers = [
            "被投资单位", "购买日", "合并方式", "支付对价",
            "直接费用", "初始投资成本", "被购买方净资产FV", "享有份额", "商誉",
        ]
        actual_headers = [
            safe_str(cell.value)
            for cell in next(ws.iter_rows(min_row=2, max_row=2))
        ]
        if not all(header in actual_headers for header in old_headers):
            wb.close()
            return [], ["无法识别G7-9表头，请使用最新三区段导出模板"]
        for row_index, values in enumerate(
            ws.iter_rows(min_row=3, values_only=True), start=1
        ):
            if all(value is None for value in values):
                continue

            def value_of(header: str) -> Any:
                idx = actual_headers.index(header)
                return values[idx] if idx < len(values) else None

            net_assets = safe_float(value_of("被购买方净资产FV"))
            share = safe_float(value_of("享有份额"))
            ratio = share / net_assets if net_assets else 0.0
            parsed = {
                "id": str(uuid4()),
                "section": "merger",
                "seq": row_index,
                "investeeName": safe_str(value_of("被投资单位")),
                "acquisitionDate": safe_str(value_of("购买日")),
                "cashConsideration": safe_float(value_of("支付对价")),
                "nonCashAssetFV": 0.0,
                "debtFV": 0.0,
                "equitySecuritiesFV": 0.0,
                "contingentConsiderationFV": 0.0,
                # 旧版directFees迁为费用化列，不再计入成本。
                "acquisitionCostsExpensed": safe_float(value_of("直接费用")),
                "acquireeIdentifiableNetAssetsFV": net_assets,
                "ownershipRatio": ratio,
                "acquisitionDateEvidenceRef": "",
                "considerationEvidenceRef": "",
                "valuationReportRef": "",
                "indexRef": "",
                "auditConclusion": "",
            }
            rows.append(_g7_9_recalculate_merger(parsed))
    wb.close()
    return rows, errors



# ═══════════════════════════════════════════════════════════════════════════════
# G7-18 多sheet导出（3区段→3 worksheet）
# ═══════════════════════════════════════════════════════════════════════════════

def _build_g7_18_multi_sheet_workbook(rows: list[dict], *, template_only: bool = False) -> Workbook:
    """G7-18 按3区段分sheet导出，每个区段一个worksheet。"""
    wb = Workbook()
    wb.remove(wb.active)  # type: ignore[arg-type]

    for seg_name, seg_headers, seg_keys in _G7_18_SEGMENTS:
        ws = wb.create_sheet(title=seg_name)
        # 标题行
        ws.append([f"G7-18 凭证检查 — {seg_name}"])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(seg_headers), 1))
        ws["A1"].font = Font(bold=True, size=12)
        # 表头行
        ws.append(seg_headers)
        ws.freeze_panes = "A3"
        for col_idx in range(1, len(seg_headers) + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 14

        if not template_only:
            for row_data in rows:
                ws.append(export_row_by_keys(row_data, seg_keys))

    # 编制说明
    ws_guide = wb.create_sheet("编制说明")
    ws_guide.append(["G7-18 长期股权投资凭证检查 编制说明"])
    ws_guide.append([])
    guidance_lines = [
        "19列拆为3区段Tab：凭证基础(7) / 核对检查(7) / 结论(5)。",
        "凭证基础：日期/凭证号/业务内容/对方科目/借方/贷方/附件。",
        "核对检查：支持性文件+6项核对（true/false或是/否）。",
        "结论：索引/是否异常/异常说明/风险等级/备注。",
        "核对1~6任一为否→自动标记为异常。",
        "借方贷方汇总差额≠0时前端红色告警。",
        "附件列支持上传后OCR自动识别。",
    ]
    for line in guidance_lines:
        ws_guide.append([line])
    ws_guide.column_dimensions["A"].width = 80
    return wb


def _parse_g7_18_import(content: bytes) -> tuple[list[dict], list[str]]:
    """解析G7-18导入文件，支持多sheet或单sheet宽表两种格式。"""
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    errors: list[str] = []
    rows_dict: dict[int, dict] = {}

    # 策略1: 多sheet格式（3区段分sheet）
    multi_sheet = len(wb.sheetnames) >= 3 and any("凭证基础" in s for s in wb.sheetnames)

    if multi_sheet:
        for seg_name, seg_headers, seg_keys in _G7_18_SEGMENTS:
            ws = None
            for name in wb.sheetnames:
                if seg_name in name:
                    ws = wb[name]
                    break
            if ws is None:
                errors.append(f"缺少工作表: {seg_name}")
                continue
            # 表头在第2行（第1行是标题）
            header_row_idx = 2
            actual_headers = [
                str(c.value).strip() if c.value else ""
                for c in next(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
            ]
            missing = [h for h in seg_headers if h not in actual_headers]
            if missing:
                errors.append(f"工作表[{seg_name}]缺少列: {', '.join(missing)}")
                continue
            for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
                if all(v is None for v in row):
                    continue
                if row_idx >= ROW_LIMIT:
                    errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
                    break
                if row_idx not in rows_dict:
                    rows_dict[row_idx] = {"id": str(uuid4())}
                values = list(row) + [None] * max(0, len(seg_headers) - len(row))
                for col_i, key in enumerate(seg_keys):
                    raw = values[col_i] if col_i < len(values) else None
                    if is_numeric_field_key(key):
                        rows_dict[row_idx][key] = safe_float(raw)
                    else:
                        rows_dict[row_idx][key] = safe_str(raw)
    else:
        # 策略2: 单sheet宽表（19列合并）
        ws = wb.active
        if ws is None:
            wb.close()
            return [], ["xlsx文件中无活动工作表"]
        # 自动检测表头行
        header_row_idx = 1
        for r in range(1, 5):
            test_row = [str(c.value).strip() if c.value else "" for c in next(ws.iter_rows(min_row=r, max_row=r))]
            if "日期" in test_row or "凭证号" in test_row:
                header_row_idx = r
                break
        actual_headers = [
            str(c.value).strip() if c.value else ""
            for c in next(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
        ]
        if "凭证号" not in actual_headers and "日期" not in actual_headers:
            errors.append("无法识别表头，缺少'日期'或'凭证号'列")
            wb.close()
            return [], errors
        for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
            if all(v is None for v in row):
                continue
            if row_idx >= ROW_LIMIT:
                errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
                break
            parsed: dict[str, Any] = {"id": str(uuid4())}
            values = list(row) + [None] * max(0, len(actual_headers) - len(row))
            for col_i, h in enumerate(actual_headers):
                if h in _G7_18_ALL_HEADERS:
                    key_idx = _G7_18_ALL_HEADERS.index(h)
                    key = _G7_18_ALL_KEYS[key_idx]
                    raw = values[col_i] if col_i < len(values) else None
                    if is_numeric_field_key(key):
                        parsed[key] = safe_float(raw)
                    else:
                        parsed[key] = safe_str(raw)
            rows_dict[row_idx] = parsed

    wb.close()
    result = list(rows_dict.values())
    if len(result) > ROW_LIMIT:
        result = result[:ROW_LIMIT]
        errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
    return result, errors


# ═══════════════════════════════════════════════════════════════════════════════
# G7-10 原底稿三区段导入导出
# ═══════════════════════════════════════════════════════════════════════════════

def _g7_10_recalc_dividend(row: dict[str, Any]) -> dict[str, Any]:
    ratio = safe_float(row.get("shareholdingRatio"))
    declared = safe_float(row.get("declaredAmount"))
    entitled = round(declared * ratio, 2)
    recorded = safe_float(row.get("recordedDividend"))
    row["entitledDividend"] = entitled
    row["variance"] = round(entitled - recorded, 2)
    return row


def _g7_10_recalc_nci(row: dict[str, Any]) -> dict[str, Any]:
    cost = round(sum(safe_float(row.get(k)) for k in (
        "costCash", "costNonCashFV", "costDebtBV", "costEquityFace", "costContingent",
    )), 2)
    share = round(safe_float(row.get("netAssetsFV")) * safe_float(row.get("addedRatio")), 2)
    row["purchaseCost"] = cost
    row["shareOfNetAssets"] = share
    row["equityAdjustment"] = round(cost - share, 2)
    row["carryingAfterPurchase"] = round(safe_float(row.get("priorCarryingAmount")) + cost, 2)
    return row


def _g7_10_recalc_partial(row: dict[str, Any]) -> dict[str, Any]:
    consideration = round(sum(safe_float(row.get(k)) for k in (
        "considerationCash", "considerationNonCashFV", "considerationDebtBV",
        "considerationEquityFace", "considerationContingent",
    )), 2)
    orig = safe_float(row.get("originalRatio"))
    book = safe_float(row.get("bookValueAtDisposal"))
    reduced = safe_float(row.get("reducedRatio"))
    individual = round(consideration - (book * reduced / orig if orig else 0), 2)
    consol_share = round(safe_float(row.get("netAssetsFV")) * reduced, 2)
    row["consideration"] = consideration
    row["individualGain"] = individual
    row["consolShare"] = consol_share
    row["consolEquityAdj"] = round(consideration - consol_share, 2)
    return row


def _build_g7_10_workbook(rows: list[dict], *, template_only: bool = False) -> Workbook:
    """按源模板三部分生成G7-10工作簿。"""
    wb = Workbook()
    wb.remove(wb.active)  # type: ignore[arg-type]
    specs = [
        ("1-股利分配测算", _G7_10_DIVIDEND_HEADERS, _G7_10_DIVIDEND_KEYS, "dividend"),
        ("2-购买少数股权", _G7_10_NCI_HEADERS, _G7_10_NCI_KEYS, "nci"),
        ("3-不丧失控制权处置", _G7_10_PARTIAL_HEADERS, _G7_10_PARTIAL_KEYS, "partialDisposal"),
    ]
    for title, headers, keys, section in specs:
        ws = wb.create_sheet(title)
        ws.append([f"G7-10 子公司后续计量测试表 — {title}"])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
        ws["A1"].font = Font(bold=True, size=12)
        ws.append(headers)
        ws.freeze_panes = "A3"
        for col_idx in range(1, len(headers) + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 16
        if not template_only:
            for source in rows:
                source_section = safe_str(source.get("section")) or "dividend"
                # 旧版成本法滚存无 section → 归入股利区
                if not source.get("section") and (
                    source.get("openingBalance") is not None
                    or source.get("declaredDividend") is not None
                ):
                    source_section = "dividend"
                if source_section != section:
                    continue
                row = dict(source)
                if section == "dividend":
                    if "companyName" not in row and row.get("investeeName"):
                        row["companyName"] = row.get("investeeName")
                    if row.get("declaredAmount") is None and row.get("declaredDividend") is not None:
                        row["declaredAmount"] = row.get("declaredDividend")
                    row = _g7_10_recalc_dividend(row)
                elif section == "nci":
                    row = _g7_10_recalc_nci(row)
                else:
                    row = _g7_10_recalc_partial(row)
                ws.append(export_row_by_keys(row, keys))

    guide = wb.create_sheet("编制说明")
    guidance = [
        "G7-10 子公司后续计量测试表（对齐致同源模板）",
        "1. 股利分配测算：应享股利=宣告金额×持股比例；差异=应享−实际入账。成本法于宣告日确认投资收益。",
        "2. 购买少数股权：个别按CAS2以对价确定成本；合并④=③×①，⑤=②−④，差额调资本公积（不足冲留存收益），不确认商誉。",
        "3. 不丧失控制权处置：个别⑤=④−①×③/②确认投资收益；合并⑧=④−⑦调权益，不确认损益。丧失控制权请用G7-11/G7-12。",
        "4. 编号①~⑧在各区段内唯一；合并侧净资产须自购买日/合并日持续计算。",
        "5. 比例以小数填写，如0.60表示60%。",
    ]
    for line in guidance:
        guide.append([line])
    guide.column_dimensions["A"].width = 110
    return wb


def _parse_g7_10_import(content: bytes) -> tuple[list[dict], list[str]]:
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    rows: list[dict] = []
    errors: list[str] = []
    specs = [
        ("1-股利分配测算", _G7_10_DIVIDEND_HEADERS, _G7_10_DIVIDEND_KEYS, "dividend"),
        ("2-购买少数股权", _G7_10_NCI_HEADERS, _G7_10_NCI_KEYS, "nci"),
        ("3-不丧失控制权处置", _G7_10_PARTIAL_HEADERS, _G7_10_PARTIAL_KEYS, "partialDisposal"),
    ]
    matched = False
    for sheet_name, expected_headers, keys, section in specs:
        if sheet_name not in wb.sheetnames:
            continue
        matched = True
        ws = wb[sheet_name]
        actual_headers = [
            safe_str(cell.value)
            for cell in next(ws.iter_rows(min_row=2, max_row=2))
        ]
        missing = [header for header in expected_headers if header not in actual_headers]
        if missing:
            errors.append(f"工作表[{sheet_name}]缺少列: {', '.join(missing)}")
            continue
        for row_index, values in enumerate(ws.iter_rows(min_row=3, values_only=True), start=3):
            if all(value is None for value in values):
                continue
            if len(rows) >= ROW_LIMIT:
                errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
                break
            parsed: dict[str, Any] = {
                "id": str(uuid4()),
                "section": section,
                "seq": row_index - 2,
            }
            for header, key in zip(expected_headers, keys):
                column_index = actual_headers.index(header)
                raw = values[column_index] if column_index < len(values) else None
                parsed[key] = safe_float(raw) if key in _G7_10_NUMERIC_KEYS else safe_str(raw)
            if section == "dividend":
                _g7_10_recalc_dividend(parsed)
            elif section == "nci":
                _g7_10_recalc_nci(parsed)
            else:
                _g7_10_recalc_partial(parsed)
            rows.append(parsed)

    if not matched:
        # 兼容旧版9列成本法滚存 → 迁移为股利测算
        ws = wb.active
        if ws is None:
            wb.close()
            return [], ["xlsx文件中无活动工作表"]
        actual_headers = [safe_str(cell.value) for cell in next(ws.iter_rows(min_row=2, max_row=2))]
        if not all(header in actual_headers for header in _G7_10_HEADERS):
            wb.close()
            return [], ["无法识别G7-10表头，请使用最新三区段导出模板"]
        for row_index, values in enumerate(ws.iter_rows(min_row=3, values_only=True), start=1):
            if all(value is None for value in values):
                continue

            def value_of(header: str) -> Any:
                idx = actual_headers.index(header)
                return values[idx] if idx < len(values) else None

            parsed = {
                "id": str(uuid4()),
                "section": "dividend",
                "seq": row_index,
                "companyName": safe_str(value_of("被投资单位")),
                "distributionPlan": "",
                "shareholdingRatio": safe_float(value_of("持股比例")),
                "declarationDate": "",
                "dividendPolicy": "",
                "declaredAmount": safe_float(value_of("被投资方宣告股利")),
                "recordedDividend": safe_float(value_of("应确认投资收益")),
                "auditConclusion": "",
            }
            rows.append(_g7_10_recalc_dividend(parsed))
    wb.close()
    return rows, errors


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/api/workpapers/{wp_id}/g7-sub/export-template")
async def g7_sub_export_template(
    wp_id: str,
    sheet: str = Query(...),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空模板：G7-8/G7-9/G7-10/G7-12/G7-18按业务区段拆分。"""
    _validate_sheet(sheet)

    if sheet == "G7-8":
        wb = _build_g7_8_workbook([], template_only=True)
        return workbook_to_response(wb, "G7-8_子公司初始计量测试_同控_模板.xlsx")
    if sheet == "G7-9":
        wb = _build_g7_9_workbook([], template_only=True)
        return workbook_to_response(wb, "G7-9_子公司初始计量测试_非同控_模板.xlsx")
    if sheet == "G7-10":
        wb = _build_g7_10_workbook([], template_only=True)
        return workbook_to_response(wb, "G7-10_子公司后续计量测试_模板.xlsx")
    if sheet == "G7-12":
        wb = _build_g7_12_workbook([], template_only=True)
        return workbook_to_response(wb, "G7-12_处置子公司测试_一揽子交易_模板.xlsx")
    if sheet == "G7-18":
        wb = _build_g7_18_multi_sheet_workbook([], template_only=True)
        return workbook_to_response(wb, "G7-18_凭证检查_模板.xlsx")
    spec = _SINGLE_SHEET_SPECS[sheet]
    wb = build_workbook_template(
        sheet,
        spec["headers"],
        title=spec.get("title"),
        guidance=spec.get("guidance"),
    )
    return workbook_to_response(wb, f"{sheet}_模板.xlsx")


@router.post("/api/workpapers/{wp_id}/g7-sub/export-data")
async def g7_sub_export_data(
    wp_id: str,
    sheet: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出数据：G7-8/G7-9/G7-10/G7-12/G7-18按业务区段拆分。"""
    _validate_sheet(sheet)
    item_id = _ITEM_IDS[sheet]
    rows = await load_json_rows(db, wp_id, item_id, field="conclusion")

    if sheet == "G7-8":
        wb = _build_g7_8_workbook(rows, template_only=False)
        return workbook_to_response(wb, "G7-8_子公司初始计量测试_同控_数据.xlsx")
    if sheet == "G7-9":
        wb = _build_g7_9_workbook(rows, template_only=False)
        return workbook_to_response(wb, "G7-9_子公司初始计量测试_非同控_数据.xlsx")
    if sheet == "G7-10":
        wb = _build_g7_10_workbook(rows, template_only=False)
        return workbook_to_response(wb, "G7-10_子公司后续计量测试_数据.xlsx")
    if sheet == "G7-12":
        wb = _build_g7_12_workbook(rows, template_only=False)
        return workbook_to_response(wb, "G7-12_处置子公司测试_一揽子交易_数据.xlsx")
    if sheet == "G7-18":
        wb = _build_g7_18_multi_sheet_workbook(rows, template_only=False)
        return workbook_to_response(wb, "G7-18_凭证检查_数据.xlsx")
    spec = _SINGLE_SHEET_SPECS[sheet]
    wb = build_workbook_template(
        sheet,
        spec["headers"],
        title=spec.get("title"),
        guidance=spec.get("guidance"),
    )
    ws = wb[sheet]
    export_rows = _prepare_g7_11_rows_export(rows) if sheet == "G7-11" else rows
    for d in export_rows:
        ws.append(export_row_by_keys(d, spec["field_keys"]))
    return workbook_to_response(wb, f"{sheet}_数据.xlsx")


@router.post("/api/workpapers/{wp_id}/g7-sub/import-data")
async def g7_sub_import_data(
    wp_id: str,
    sheet: str = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """导入数据：G7-8/G7-9/G7-10/G7-12/G7-18支持多区段工作簿。"""
    _validate_sheet(sheet)
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(400, "请上传 .xlsx 格式文件")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "文件大小不能超过10MB")

    item_id = _ITEM_IDS[sheet]
    errors: list[str] = []
    rows: list[dict] = []
    warnings: list[str] = []

    if sheet == "G7-8":
        rows, errors = _parse_g7_8_import(content)
    elif sheet == "G7-9":
        rows, errors = _parse_g7_9_import(content)
    elif sheet == "G7-10":
        rows, errors = _parse_g7_10_import(content)
    elif sheet == "G7-11":
        rows, errors, warnings = _parse_g7_11_sheet_rows(content)
    elif sheet == "G7-12":
        rows, errors = _parse_g7_12_import(content)
    elif sheet == "G7-18":
        rows, errors = _parse_g7_18_import(content)
    else:
        spec = _SINGLE_SHEET_SPECS[sheet]
        try:
            actual, raw = parse_upload_xlsx(content, spec["headers"], header_row=2)
        except ValueError as e:
            return {"ok": False, "errors": [str(e)], "imported_count": 0}
        except Exception:
            raise HTTPException(400, "无法解析xlsx文件")
        keys = spec["field_keys"]
        for i, r in enumerate(raw, start=1):
            if i > ROW_LIMIT:
                errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
                break
            rows.append(parse_row_by_headers(r, actual, keys))

    if errors and not rows:
        return {"ok": False, "errors": errors, "imported_count": 0}

    if sheet == "G7-9":
        rows, hard_errors = G7SubsidiaryService().prepare_g7_9_rows(rows)
        if hard_errors:
            return {
                "ok": False,
                "errors": [error.message for error in hard_errors],
                "details": [
                    {
                        "row_key": error.row_key,
                        "field": error.field,
                        "message": error.message,
                    }
                    for error in hard_errors
                ],
                "imported_count": 0,
            }

    if sheet == "G7-11":
        rows = _normalize_g7_11_rows_import(rows)

    if sheet == "G7-10":
        # 页面存 {rows, materialityLevel} 信封；导入只换行，保留既有重要性
        existing = await load_json_payload(db, wp_id, item_id, field="conclusion")
        materiality = 0
        if isinstance(existing, dict):
            try:
                materiality = float(
                    existing.get("materialityLevel")
                    or existing.get("materiality_level")
                    or 0
                )
            except (TypeError, ValueError):
                materiality = 0
        await upsert_json_payload(
            db,
            wp_id,
            item_id,
            {"rows": rows, "materialityLevel": materiality},
            field="conclusion",
        )
    else:
        await upsert_json_rows(db, wp_id, item_id, rows, field="conclusion")
    out: dict[str, Any] = {"ok": True, "imported_count": len(rows), "errors": errors}
    if warnings:
        out["warning"] = "；".join(warnings)
    if len(rows) >= ROW_LIMIT:
        trunc = f"数据行数超过{ROW_LIMIT}行限制，已截断"
        out["warning"] = f"{out['warning']}；{trunc}" if out.get("warning") else trunc
    return out
