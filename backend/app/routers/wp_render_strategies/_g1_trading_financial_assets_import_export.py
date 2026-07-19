"""G1 交易性金融资产 — 导入导出（列结构对齐 requirements + composable field keys）.

支持 12 张表格：
  G1-1 审定表（keyed store）/
  G1-2 明细表(35列/5区段) / G1-3 调整分录 / G1-4 结存表 / G1-5 收益测算 /
  G1-6 公允价值测试 / G1-7 第三层次调节 /
  G1-10 合同现金流量特征分析（多 sheet，对齐 G4-6）/
  G1-11 监盘 / G1-12 倒轧 / G1-13 检查表 / G1-14 衍生工具核查

字段键与前端 composable（useG1Detail/useG1Inventory/... 的行接口）严格对齐，保证 round-trip。
宽表（G1-2 明细 / G1-12 倒轧 / G1-4 结存 / G1-5 收益）导出为单 sheet 宽表，
表头区段前缀（[基础]/[持有]/[公允]/[损益]/[审定]）标注 5 区段归属。
"""

from __future__ import annotations

import io
from typing import Any
from uuid import uuid4

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from ._cycle_import_export_common import (
    ROW_LIMIT,
    create_cycle_import_export_router,
    export_row_by_keys,
    safe_float,
    safe_str,
)


# ── G1-1 审定表（keyed remark store：{rowKey: cell}）──
_G1_1_HEADERS = [
    "行键", "项目", "区段", "分类", "品种",
    "期初未审数", "期初账项调整", "期末未审数", "期末账项调整", "原因分析",
]
_G1_1_KEYS = [
    "rowKey", "label", "section", "classKey", "assetKey",
    "openingUnadjusted", "openingAdjustment", "closingUnadjusted", "closingAdjustment", "reasonAnalysis",
]
_G1_1_KEEP_KEYS = [
    "openingUnadjusted", "openingAdjustment", "closingUnadjusted", "closingAdjustment", "reasonAnalysis",
]

_G1_1_CLASSES = [
    ("trading", "交易性金融资产"),
    ("classified", "划分为以公允价值计量且其变动计入当期损益的金融资产"),
    ("designated", "指定为以公允价值计量且其变动计入当期损益的金融资产"),
]
_G1_1_ASSETS = [
    ("debt", "债务工具投资"),
    ("equity", "权益工具投资"),
    ("derivative", "衍生金融资产"),
    ("wealth", "理财产品"),
    ("structured", "结构性存款"),
    ("fund", "基金"),
    ("other", "其他"),
]
_G1_1_SECTIONS = [
    ("cost", "投资成本"),
    ("fv", "累计公允价值变动"),
]


def _build_g1_1_prefill():
    rows = []
    for section, section_label in _G1_1_SECTIONS:
        for class_key, _class_label in _G1_1_CLASSES:
            for asset_key, asset_label in _G1_1_ASSETS:
                row_key = f"{section}-{class_key}-{asset_key}"
                rows.append([
                    row_key,
                    asset_label,
                    section_label,
                    class_key,
                    asset_key,
                    0, 0, 0, 0, "",
                ])
    rows.append([
        "footer-over-one-year",
        "减：超过一年到期的部分",
        "footer",
        "",
        "",
        0, 0, 0, 0, "",
    ])
    return rows


# ── 调整分录（G1-3，借贷平衡）──
_ADJ_HEADERS = ["序号", "分录类型", "日期", "摘要", "科目代码", "科目名称", "借方金额", "贷方金额", "编制人", "备注"]
_ADJ_KEYS = ["seq", "entryType", "date", "summary", "accountCode", "accountName", "debit", "credit", "preparer", "remark"]

# ── G1-2 明细表（对齐双桶滚动 + 会计分类）──
_G1_2_HEADERS = [
    "序号", "投资项目", "证券代码", "会计分类", "投资品种", "交易市场", "取得日期", "初始成本", "原币", "汇率",
    "期初数量", "本期买入", "本期卖出", "期末数量",
    "期初成本", "期初累计公允变动", "期初成本调整", "期初公允调整", "一年以上扣减(期初)",
    "本期增加成本", "本期减少成本", "本期公允变动", "利息股利",
    "期末单位公允", "公允层级", "报价日期",
    "期末成本调整", "期末公允调整", "AJE", "RJE", "一年以上扣减(期末)",
    "变现受限", "是否质押", "处置收入", "处置成本", "公允变动损益", "备注", "索引",
]
_G1_2_KEYS = [
    "seq", "securityName", "securityCode", "acctClass", "investType", "market", "acquisitionDate", "initialCost", "originalCurrency", "exchangeRate",
    "openingQuantity", "boughtQuantity", "soldQuantity", "closingQuantity",
    "openingCost", "openingCumulativeFv", "openingCostAdj", "openingFvAdj", "openingLtDeduction",
    "addedCost", "reducedCost", "periodFvChange", "dividendIncome",
    "unitFairValue", "fairValueSource", "quoteDate",
    "closingCostAdj", "closingFvAdj", "aje", "rje", "closingLtDeduction",
    "realizationRestricted", "pledged", "disposalProceeds", "disposalCost", "fvChangeInPL", "remark", "indexRef",
]

# ── G1-4 结存表（账面/库存/对账/函证/差异）──
_G1_4_HEADERS = [
    "序号", "证券名称", "资金账号", "账户名称",
    "账面数量", "账面面值", "票面利率", "到期日", "账面总计",
    "库存数量", "库存面值", "库存总计",
    "对账数量", "对账面值", "对账总计",
    "函证数量", "函证面值", "函证总计",
    "证据源", "差异数量", "差异面值", "差异总计", "备注",
]
_G1_4_KEYS = [
    "seq", "securityName", "cashAccountNo", "accountName",
    "bookQuantity", "bookFaceValue", "couponRate", "maturityDate", "bookTotal",
    "stockQuantity", "stockFaceValue", "stockTotal",
    "stmtQuantity", "stmtFaceValue", "stmtTotal",
    "confQuantity", "confFaceValue", "confTotal",
    "evidenceSource", "diffQuantity", "diffFaceValue", "diffTotal", "remark",
]

# ── G1-5 债息测算（主路径；股利/处置见 guidance）──
_G1_5_HEADERS = [
    "序号", "金融投资名称", "合同金额", "年化利率(%)",
    "起始日", "结息日", "到期日", "计息基数",
    "结息前天数(手工)", "结息后天数(手工)",
    "结息前天数", "结息后天数", "结息前利息", "结息后利息", "应计利息小计", "备注",
]
_G1_5_KEYS = [
    "seq", "securityName", "contractAmount", "annualRatePct",
    "startDate", "settlementDate", "maturityDate", "dayCountBasis",
    "daysBeforeManual", "daysAfterManual",
    "daysBefore", "daysAfter", "interestBefore", "interestAfter", "interestSubtotal", "remark",
]

# ── G1-6 公允价值测试（账面 vs 测试 + Level1-3 估值详情）──
_G1_6_HEADERS = [
    "序号", "证券名称", "代码",
    "持仓数量", "账面单位公允", "期末账面值", "Level层级",
    "估值方法", "与上期是否一致",
    "报价日期", "报价来源", "报价值", "计算市值", "Level1差异",
    "可观察输入描述", "Level2估值结果", "Level2差异",
    "估值技术", "不可观察输入", "输入值数值", "估值假设", "敏感性分析",
    "Level3估值结果", "Level3差异",
    "测试公允价值", "差异", "估值文件索引", "结论", "备注",
]
_G1_6_KEYS = [
    "seq", "securityName", "securityCode",
    "quantity", "bookUnitFv", "bookValue", "fvLevel",
    "valuationMethod", "methodConsistentWithPrior",
    "quoteDate", "quoteSource", "quoteValue", "marketValue", "level1Diff",
    "observableDesc", "level2Result", "level2Diff",
    "valuationTechnique", "unobservableInput", "unobservableInputValue", "assumption", "sensitivityAnalysis",
    "level3Result", "level3Diff",
    "testedValue", "activeDiff", "valuationDocIndex", "conclusion", "remark",
]

# ── G1-7 第三层次调节（对齐致同纸质底稿 / CAS 39）──
_G1_7_HEADERS = [
    "序号", "投资项目", "品种", "期初余额", "转入第三层次", "转出第三层次",
    "公允价值变动损益", "投资收益", "购买", "发行", "出售", "结算",
    "期末余额", "仍持有未实现损益变动", "企业报告期末", "差异", "备注",
]
_G1_7_KEYS = [
    "seq", "itemName", "assetClass", "openingBalance", "transferIn", "transferOut",
    "gainPl", "investmentIncome", "purchase", "issue", "sale", "settlement",
    "closingBalance", "unrealizedHeld", "reportedClosing", "variance", "remark",
]

# ── G1-11 有价证券监盘（对齐致同纸质 + 账实核对扩展）──
_G1_11_HEADERS = [
    "序号", "盘点地点", "证券名称", "面值", "数量", "总计", "票面利率(%)", "到期日",
    "代码", "类型", "账面数量", "差异", "差异原因", "保管机构", "监盘日期",
]
_G1_11_KEYS = [
    "seq", "location", "securityName", "faceValue", "countedQuantity", "total", "couponRate", "maturityDate",
    "securityCode", "securityType", "bookedQuantity", "countDiff", "diffReason", "custodian", "countDate",
]

# ── G1-12 盘点倒轧（对齐 Excel：盘点日/增减/报表日+账面+差异）──
_G1_12_HEADERS = [
    "序号", "分类", "证券名称",
    "盘点日·数量", "盘点日·面值", "盘点日·总计", "盘点日·票面利率", "盘点日·到期日",
    "增加·数量", "增加·面值总额", "减少·数量", "减少·面值总额",
    "报表日·数量", "报表日·面值", "报表日·总计", "报表日·票面利率", "报表日·到期日",
    "账面·数量", "账面·面值", "账面·总计",
    "差异·数量", "差异·金额", "备注",
]
_G1_12_KEYS = [
    "seq", "category", "securityName",
    "countQuantity", "countFaceValue", "countTotal", "countCouponRate", "countMaturityDate",
    "increaseQuantity", "increaseFaceTotal", "decreaseQuantity", "decreaseFaceTotal",
    "reportQuantity", "reportFaceValue", "reportTotal", "reportCouponRate", "reportMaturityDate",
    "bookQuantity", "bookFaceValue", "bookTotal",
    "diffQuantity", "diffAmount", "remark",
]

# ── G1-13 检查表（本期/期后 + 六项核对）──
_G1_13_HEADERS = [
    "序号", "区段", "凭证日期", "凭证号", "业务内容",
    "借方科目", "贷方科目", "借方金额", "贷方金额", "金额",
    "支持性文件",
    "原始单据齐全", "凭证与单据相符", "账务处理正确", "期间正确", "公允价值正确", "授权审批恰当",
    "索引", "是否异常", "异常说明", "备注", "抽凭来源", "附件",
]
_G1_13_KEYS = [
    "seq", "period", "voucherDate", "voucherNo", "businessContent",
    "debitAccount", "creditAccount", "debitAmount", "creditAmount", "amount",
    "supportingDocs",
    "check1DocsComplete", "check2VoucherMatch", "check3Accounting", "check4Period", "check5FairValue", "check6Approval",
    "indexRef", "isAbnormal", "abnormalDesc", "remark", "sampleSource", "attachment",
]

# ── G1-14 衍生金融工具核查（10列）──
_G1_14_HEADERS = [
    "序号", "工具名称", "类型", "名义金额", "期限", "对手方", "保证金", "是否套期", "会计处理适当性", "合规结论",
]
_G1_14_KEYS = [
    "seq", "instrumentName", "instrumentType", "notionalAmount", "term", "counterparty", "margin", "isHedging", "accountingAppropriateness", "complianceConclusion",
]

# ── G1-10 合同现金流量特征分析（7 分区 × 多 sheet，对齐 useG1ContractCashflow）──
_G1_10_BOND_HEADERS = [
    "序号", "投资项目", "账面/面值", "票面利率",
    "提前赎回", "展期", "权益转换", "杠杆", "结论", "分析说明",
]
_G1_10_BOND_KEYS = [
    "seq", "investItem", "bookOrFaceValue", "couponRate",
    "hasEarlyRedemption", "hasExtension", "hasEquityConversion", "hasLeverage",
    "conclusion", "analysisNote",
]
_G1_10_WEALTH1_HEADERS = [
    "序号", "投资项目", "投资总额", "保证本金", "固定收益", "固定收益率",
    "约定浮动收益", "浮动收益率", "结论", "备注",
]
_G1_10_WEALTH1_KEYS = [
    "seq", "investItem", "totalAmount", "guaranteesPrincipal", "fixedGuaranteed", "fixedRate",
    "floatingGuaranteed", "floatingRate", "conclusion", "remark",
]
_G1_10_WEALTH2_HEADERS = [
    "序号", "投资项目", "固定收益率", "浮动收益确定方式", "基础变量历史变动", "是否不现实", "结论", "备注",
]
_G1_10_WEALTH2_KEYS = [
    "seq", "investItem", "fixedRate", "floatingMethod", "baseVariableHistory",
    "isUnrealistic", "conclusion", "remark",
]
_G1_10_PERP_HEADERS = [
    "序号", "投资项目", "账面价值", "期限", "初始利率",
    "可递延股利", "递延是否计息", "可转固定数量权益", "结论", "分析说明",
]
_G1_10_PERP_KEYS = [
    "seq", "investItem", "bookValue", "term", "initialRate",
    "hasDeferredDividend", "deferredCompounds", "convertibleToFixedEquity",
    "conclusion", "analysisNote",
]
_G1_10_CONV_HEADERS = [
    "序号", "投资项目", "投资总额", "期限", "票面利率", "初始转股价",
    "含转股条款", "条款描述", "结论", "分析说明",
]
_G1_10_CONV_KEYS = [
    "seq", "investItem", "totalAmount", "term", "couponRate", "initialConversionPrice",
    "hasConversionFeature", "featureDesc", "conclusion", "analysisNote",
]
_G1_10_PROJ_HEADERS = [
    "序号", "投资项目", "投资总额", "期限", "票面利率",
    "底层现金流", "差额补足", "担保", "现金流依赖项目运营", "结论", "分析说明",
]
_G1_10_PROJ_KEYS = [
    "seq", "investItem", "totalAmount", "term", "couponRate",
    "underlyingCashFlow", "deficiencyCompensation", "guarantee",
    "cfDependsOnProjectOps", "conclusion", "analysisNote",
]
_G1_10_ABS_HEADERS = [
    "序号", "投资项目", "投资总额", "期限", "票面利率", "级次",
    "基础资产现金流", "信用风险比较", "穿透条件满足", "结论", "分析说明",
]
_G1_10_ABS_KEYS = [
    "seq", "investItem", "totalAmount", "term", "couponRate", "tranche",
    "underlyingCashFlow", "creditRiskCompare", "lookThroughOk",
    "conclusion", "analysisNote",
]

# (store_key, sheet_title, headers, keys, numeric_keys)
_G1_10_SECTIONS: list[tuple[str, str, list[str], list[str], set[str]]] = [
    ("bondRows", "债券投资", _G1_10_BOND_HEADERS, _G1_10_BOND_KEYS, {"seq", "bookOrFaceValue"}),
    ("wealthStep1", "理财-保本保收益", _G1_10_WEALTH1_HEADERS, _G1_10_WEALTH1_KEYS, {"seq", "totalAmount"}),
    ("wealthStep2", "理财-浮动不现实", _G1_10_WEALTH2_HEADERS, _G1_10_WEALTH2_KEYS, {"seq"}),
    ("perpetualRows", "优先股永续债", _G1_10_PERP_HEADERS, _G1_10_PERP_KEYS, {"seq", "bookValue"}),
    ("convertibleRows", "可转换债券", _G1_10_CONV_HEADERS, _G1_10_CONV_KEYS, {"seq", "totalAmount"}),
    ("projectRows", "项目收益信托", _G1_10_PROJ_HEADERS, _G1_10_PROJ_KEYS, {"seq", "totalAmount"}),
    ("absRows", "资产支持证券", _G1_10_ABS_HEADERS, _G1_10_ABS_KEYS, {"seq", "totalAmount"}),
]

_G1_10_YN_KEYS = {
    "hasEarlyRedemption", "hasExtension", "hasEquityConversion", "hasLeverage",
    "guaranteesPrincipal", "fixedGuaranteed", "floatingGuaranteed", "isUnrealistic",
    "hasDeferredDividend", "deferredCompounds", "convertibleToFixedEquity",
    "hasConversionFeature", "cfDependsOnProjectOps", "lookThroughOk",
}


def _g1_10_norm_yn(val: Any) -> str:
    if val is None:
        return ""
    s = str(val).strip().lower()
    if s in ("是", "yes", "y", "true", "1"):
        return "yes"
    if s in ("否", "no", "n", "false", "0"):
        return "no"
    return ""


def _g1_10_norm_conclusion(val: Any) -> str:
    s = safe_str(val).upper().replace(" ", "_")
    if s in ("PASS", "通过", "通过SPPI", "通过_SPPI"):
        return "PASS"
    if s in ("FAIL", "不通过", "不通过（FVTPL）", "FVTPL"):
        return "FAIL"
    if s in ("FURTHER_ANALYSIS", "FURTHERANALYSIS", "待分析", "需进一步分析"):
        return "FURTHER_ANALYSIS"
    return safe_str(val)


def _build_g1_10_workbook(payload: Any, *, template_only: bool = False) -> Workbook:
    """G1-10 按 7 分区分 sheet 导出（对齐 Excel / useG1ContractCashflow）。"""
    wb = Workbook()
    wb.remove(wb.active)
    store: dict[str, Any] = payload if isinstance(payload, dict) else {}
    # 兼容旧版扁平数组 → 仅债券
    if isinstance(payload, list):
        store = {"bondRows": payload}

    for store_key, title, headers, keys, _nums in _G1_10_SECTIONS:
        ws = wb.create_sheet(title=title)
        ws.append([f"G1-10 合同现金流量特征分析 — {title}"])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(headers), 1))
        ws["A1"].font = Font(bold=True, size=12)
        ws.append(headers)
        ws.freeze_panes = "A3"
        for col_idx in range(1, len(headers) + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 14
        if template_only:
            continue
        rows = store.get(store_key) or []
        if not isinstance(rows, list):
            continue
        for row_data in rows:
            if not isinstance(row_data, dict):
                continue
            ws.append(export_row_by_keys(row_data, keys))

    ws_guide = wb.create_sheet("编制说明")
    ws_guide.append(["G1-10 合同现金流量特征分析 编制说明"])
    ws_guide.append([])
    for line in [
        "七个工作表对应前端分区：（一）债券（二）理财保本/浮动（三）优先股永续债（四）可转债（五）项目收益/信托（六）ABS。",
        "是/否列填 yes/no 或 是/否；结论填 PASS / FAIL / FURTHER_ANALYSIS（或 通过/不通过/待分析）。",
        "ABS 级次填 senior/mezzanine/subordinated/other（或 优先/中间/次级/其他）。",
        "导入后前端自动重算「建议」结论；与结论不一致时界面会提示复核。",
        "存储键 G1-10-rows（version=2 分区对象）；审计说明/结论另存 G1-10-audit-note / G1-10-conclusion。",
    ]:
        ws_guide.append([line])
    ws_guide.column_dimensions["A"].width = 90
    return wb


def _parse_g1_10_sheet_rows(
    ws: Any,
    headers: list[str],
    keys: list[str],
    numeric_keys: set[str],
) -> list[dict]:
    header_row_idx = 2
    actual = [
        str(c.value).strip() if c.value else ""
        for c in next(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
    ]
    key_by_header = {h: k for h, k in zip(headers, keys)}
    out: list[dict] = []
    for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
        if all(v is None for v in row):
            continue
        if len(out) >= ROW_LIMIT:
            break
        values = list(row) + [None] * max(0, len(actual) - len(row))
        parsed: dict[str, Any] = {"id": str(uuid4()), "seq": row_idx + 1}
        empty = True
        for col_i, h in enumerate(actual):
            if not h or h not in key_by_header:
                continue
            key = key_by_header[h]
            raw = values[col_i] if col_i < len(values) else None
            if key in numeric_keys:
                parsed[key] = safe_float(raw)
                if parsed[key]:
                    empty = False
            elif key in _G1_10_YN_KEYS:
                parsed[key] = _g1_10_norm_yn(raw)
                if parsed[key]:
                    empty = False
            elif key == "conclusion":
                parsed[key] = _g1_10_norm_conclusion(raw)
                if parsed[key]:
                    empty = False
            elif key == "tranche":
                t = safe_str(raw).lower()
                mapping = {
                    "优先": "senior", "senior": "senior",
                    "中间": "mezzanine", "mezzanine": "mezzanine",
                    "次级": "subordinated", "subordinated": "subordinated",
                    "其他": "other", "other": "other",
                }
                parsed[key] = mapping.get(t, t if t in ("senior", "mezzanine", "subordinated", "other") else "")
                if parsed[key]:
                    empty = False
            else:
                parsed[key] = safe_str(raw)
                if parsed[key]:
                    empty = False
        if empty and not safe_str(parsed.get("investItem")):
            continue
        parsed["conclusionOverridden"] = True
        out.append(parsed)
    return out


def _parse_g1_10_import(content: bytes) -> tuple[dict[str, Any], list[str], int]:
    """解析 G1-10 多 sheet 导入 → version=2 store。"""
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    errors: list[str] = []
    store: dict[str, Any] = {
        "version": 2,
        "bondRows": [],
        "wealthStep1": [],
        "wealthStep2": [],
        "perpetualRows": [],
        "convertibleRows": [],
        "projectRows": [],
        "absRows": [],
    }
    total = 0
    for store_key, title, headers, keys, nums in _G1_10_SECTIONS:
        ws = None
        for name in wb.sheetnames:
            if title in name or name == title:
                ws = wb[name]
                break
        if ws is None:
            if store_key == "bondRows":
                for name in wb.sheetnames:
                    if "编制" in name:
                        continue
                    ws = wb[name]
                    break
            if ws is None:
                continue
        try:
            rows = _parse_g1_10_sheet_rows(ws, headers, keys, nums)
        except Exception as e:
            errors.append(f"工作表[{title}]解析失败: {e}")
            continue
        store[store_key] = rows
        total += len(rows)
    wb.close()
    if total == 0 and not errors:
        errors.append("未解析到有效数据行，请确认工作表名称与表头是否匹配模板")
    return store, errors, total


_G1_SPECS: dict[str, dict[str, Any]] = {
    "G1-1": {
        "item_id": "G1-1-rows",
        "title": "G1-1 交易性金融资产审定表",
        "headers": _G1_1_HEADERS,
        "field_keys": _G1_1_KEYS,
        "storage_field": "remark",
        "keyed_by": "rowKey",
        "keep_keys": _G1_1_KEEP_KEYS,
        "template_prefill": _build_g1_1_prefill(),
        "guidance": [
            "G1-1 审定表 编制说明",
            "",
            "行键(rowKey)须与模板一致，勿改动；仅填写未审数/账项调整/原因分析。",
            "区段：投资成本(cost) / 累计公允价值变动(fv)；账面余额由前端自动=成本+累计FV。",
            "分类：trading / classified / designated；品种：debt/equity/derivative/wealth/structured/fund/other。",
            "审定=未审+账项调整；|变动率|>30% 时原因分析必填。",
            "footer-over-one-year 为「减：超过一年到期的部分」。",
        ],
    },
    "G1-2": {
        "item_id": "G1-2-rows",
        "title": "G1-2 交易性金融资产明细表（双桶滚动）",
        "headers": _G1_2_HEADERS,
        "field_keys": _G1_2_KEYS,
        "guidance": [
            "G1-2 明细表 编制说明",
            "",
            "会计分类填 trading / classified_fvpl / designated_fvpl；投资品种填 stock/fund/bond/derivative/other。",
            "成本与累计公允变动双桶：期初→调整→审定→本期变动→期末→审定；一年以上扣减得报表数。",
            "公式列（期末数量/成本/公允/审定等）导入后前端自动重算；闸门存 G1-2-gates（不在本表导出）。",
        ],
    },
    "G1-3": {
        "item_id": "G1-3-rows",
        "title": "G1-3 交易性金融资产调整分录",
        "headers": _ADJ_HEADERS,
        "field_keys": _ADJ_KEYS,
        "guidance": ["G1-3 调整分录 编制说明", "", "分录类型填 AJE 或 RJE；每张凭证借贷方金额必须相等。"],
    },
    "G1-4": {
        "item_id": "G1-4-rows",
        "title": "G1-4 结存表（账面/库存/对账/函证）",
        "headers": _G1_4_HEADERS,
        "field_keys": _G1_4_KEYS,
        "guidance": [
            "G1-4 结存表 编制说明",
            "",
            "差异=账面−库存−(函证优先否则对账单)；证据源填 auto/statement/confirmation/stocktake。",
            "可从 G1-2 带入账面、从 G1-11 回填监盘；差异可推送 G1-3。",
        ],
    },
    "G1-5": {
        "item_id": "G1-5-interest-rows",
        "title": "G1-5 收益测算表（债息主路径）",
        "headers": _G1_5_HEADERS,
        "field_keys": _G1_5_KEYS,
        "guidance": [
            "G1-5 收益测算 编制说明",
            "",
            "主路径：合同金额×年化利率×天数/基数（结息前/后）；手工天数列可覆盖自动天数。",
            "股利/处置/账面勾稽/闸门另存：G1-5-dividend-rows、G1-5-disposal-rows、G1-5-book-recon、G1-5-gates。",
            "应计利息=本金×利率%×天数/基数；导入后前端重算公式列。",
        ],
    },
    "G1-6": {
        "item_id": "G1-6-rows",
        "title": "G1-6 公允价值测试表（账面vs审定 + Level1-3）",
        "headers": _G1_6_HEADERS,
        "field_keys": _G1_6_KEYS,
        "guidance": [
            "G1-6 公允价值测试 编制说明",
            "",
            "编制路径：账面公允价值 → 按层次测试 → 差异分析 → 回写 G1-2。",
            "Level层级填 1/2/3；测试公允价值：L1=数量×报价，L2/L3=估值结果；差异=测试−账面。",
            "Level3 须填估值技术与不可观察输入；变动调节见 G1-7。",
        ],
    },
    "G1-7": {
        "item_id": "G1-7-rows",
        "title": "G1-7 第三层次公允价值计量的调节表",
        "headers": _G1_7_HEADERS,
        "field_keys": _G1_7_KEYS,
        "guidance": [
            "G1-7 第三层次调节 编制说明",
            "",
            "列结构对齐致同纸质底稿 / CAS 39：层次转移、当期利得或损失(公允变动/投资收益)、购买发行出售结算、仍持有未实现。",
            "品种填 debt/equity/derivative/other（债务工具/权益工具/衍生/其他），附注⑤按品种拆分同步。",
            "期末余额=期初+转入-转出+公允变动损益+投资收益+购买+发行-出售-结算（公式列，导入后前端重算）。",
            "差异=公式期末-企业报告期末；|差异|>0.01 须核查。可从 G1-2(Level3) / G1-6 带入。估值方法/假设见 G1-6。",
        ],
    },
    "G1-10": {
        "item_id": "G1-10-rows",
        "title": "G1-10 合同现金流量特征分析（SPPI）",
        "headers": _G1_10_BOND_HEADERS,
        "field_keys": _G1_10_BOND_KEYS,
        "build_workbook": _build_g1_10_workbook,
        "parse_import": _parse_g1_10_import,
        "guidance": [
            "G1-10 多 sheet：债券 / 理财两步 / 优先股永续债 / 可转债 / 项目收益信托 / ABS。",
        ],
    },
    "G1-11": {
        "item_id": "G1-11-rows",
        "title": "G1-11 有价证券监盘表",
        "headers": _G1_11_HEADERS,
        "field_keys": _G1_11_KEYS,
        "guidance": [
            "G1-11 监盘表 编制说明",
            "",
            "盘点信息头（单位/日期/地点/人员）在前端「盘点信息」弹窗填写，存储键 G1-11-header。",
            "总计=面值×数量；差异=盘点数量-账面数量；|差异|>0 须填差异原因（闸门）。",
            "盘点地点可按行填写并分组；可推送至 G1-12；行级 OCR 识别对账单/盘点表。",
            "可上传监盘扫描件；盘点日≠报表日时衔接 G1-12 倒轧。",
        ],
    },
    "G1-12": {
        "item_id": "G1-12-rows",
        "title": "G1-12 有价证券盘点倒轧表",
        "headers": _G1_12_HEADERS,
        "field_keys": _G1_12_KEYS,
        "guidance": [
            "G1-12 盘点倒轧 编制说明",
            "",
            "报表日实存 = 盘点日实存 −（资产负债表日→盘点日）增加 + 减少；差异 = 报表日 − 账面。",
            "分类填 debt/equity/derivative/other；可从 G1-11 带入盘点日实存。",
            "公式列（盘点日总计/报表日数量与总计/差异）导入后前端自动重算。",
        ],
    },
    "G1-13": {
        "item_id": "G1-13-rows",
        "title": "G1-13 交易性金融资产检查表（本期/期后）",
        "headers": _G1_13_HEADERS,
        "field_keys": _G1_13_KEYS,
        "guidance": [
            "G1-13 检查表 编制说明",
            "",
            "区段 period 填 current（本期发生额）或 subsequent（期后处置/新售）。",
            "六项核对填 true/false；任一项否自动标异常。抽样计划另存 G1-13-sampling-plan。",
            "可通过抽凭引擎按科目1501填入；检查比例=样本金额/总体金额（总体为0时不计算）。",
        ],
    },
    "G1-14": {
        "item_id": "G1-14-rows",
        "title": "G1-14 衍生金融工具核查表",
        "headers": _G1_14_HEADERS,
        "field_keys": _G1_14_KEYS,
        "guidance": [
            "G1-14 衍生工具核查 编制说明",
            "",
            "类型填 option/futures/swap/forward（期权/期货/互换/远期）；会计处理适当性填 appropriate/inappropriate/needs-review。",
        ],
    },
}

router = create_cycle_import_export_router(tag="g1-import-export", api_prefix="g1", specs=_G1_SPECS)
