# -*- coding: utf-8 -*-
"""D4-21 / D4-24 导入导出 round-trip（Wave 3 T3.2，Req 4.1/4.2）。

验证：
- 专用 parser 按中文列头映射到契约 camelCase 键（与 phase5_d4_ipo_related_sheets 对齐）；
- 派生列（D4-21 差异率/差异率(公允)）导出可展示、导入**不采信**（不入 store）；
- 录入列 export → import round-trip 逐字段保真。
"""
from __future__ import annotations

import re

import app.routers.wp_render_strategies._d4_import_export as ie


# ── 复刻 export 分支的 row_values 构造（与生产同序）──────────────────────────
def _export_d4_21(store_row: dict, headers: list[str]) -> list:
    _g = ie._safe_float(store_row.get("avgPrice"))
    _h = ie._safe_float(store_row.get("nonrelatedAvgPrice"))
    _j = ie._safe_float(store_row.get("fairPrice"))
    return [
        "",
        store_row.get("partyName", ""),
        store_row.get("relationship", ""),
        store_row.get("product", ""),
        ie._safe_float(store_row.get("qty")),
        ie._safe_float(store_row.get("salesAmount")),
        ie._safe_float(store_row.get("salesRatio")),
        _g, _h,
        round((_g - _h) / _h * 100, 2) if _h else "",
        _j,
        round((_g - _j) / _j * 100, 2) if _j else "",
        ie._safe_float(store_row.get("priorSalesRatio")),
        ie._safe_float(store_row.get("priorAvgPrice")),
        store_row.get("remark", ""),
    ]


def test_d4_21_roundtrip_and_derived_excluded():
    headers = ie._SHEET_HEADERS["D4-21"]
    store_row = {
        "rowId": "r1", "partyName": "关联方甲", "relationship": "母子公司",
        "product": "产品A", "qty": 100.0, "salesAmount": 50000.0, "salesRatio": 12.5,
        "avgPrice": 500.0, "nonrelatedAvgPrice": 480.0, "fairPrice": 490.0,
        "priorSalesRatio": 10.0, "priorAvgPrice": 470.0, "remark": "备注x",
    }
    exported = _export_d4_21(store_row, headers)
    # 差异率列在导出侧被计算展示
    assert exported[9] != "" and exported[11] != ""

    parsed = ie._parse_d4_21_row(tuple(exported), headers)
    # 录入列逐字段保真
    for k in ("partyName", "relationship", "product", "qty", "salesAmount",
              "salesRatio", "avgPrice", "nonrelatedAvgPrice", "fairPrice",
              "priorSalesRatio", "priorAvgPrice", "remark"):
        assert parsed[k] == store_row[k], f"{k} 不保真: {parsed[k]} != {store_row[k]}"
    # 🔴 派生列不采信：解析结果无任何差异率键
    assert not any("差异" in str(k) or "DiffRate" in str(k) for k in parsed)
    assert "rowId" in parsed


def _export_d4_24(store_row: dict) -> list:
    return [
        "",
        store_row.get("customerName", ""),
        ie._safe_float(store_row.get("annualSales")),
        ie._safe_float(store_row.get("endingAr")),
        ie._safe_float(store_row.get("thirdPartyAmount")),
        store_row.get("payerName", ""),
        store_row.get("reason", ""),
        store_row.get("payerCustomerRelation", ""),
        store_row.get("payerEntityRelation", ""),
        store_row.get("hasPaymentAgreement", ""),
        store_row.get("isConfirmed", ""),
        store_row.get("rationality", ""),
        store_row.get("indexNo", ""),
    ]


def test_d4_24_roundtrip():
    headers = ie._SHEET_HEADERS["D4-24"]
    store_row = {
        "rowId": "r2", "customerName": "客户乙", "annualSales": 800000.0,
        "endingAr": 120000.0, "thirdPartyAmount": 50000.0, "payerName": "第三方丙",
        "reason": "代付", "payerCustomerRelation": "关联", "payerEntityRelation": "无",
        "hasPaymentAgreement": "是", "isConfirmed": "否", "rationality": "合理", "indexNo": "E1-31",
    }
    exported = _export_d4_24(store_row)
    assert len(exported) == len(headers)
    parsed = ie._parse_d4_24_row(tuple(exported), headers)
    for k in ("customerName", "annualSales", "endingAr", "thirdPartyAmount",
              "payerName", "reason", "payerCustomerRelation", "payerEntityRelation",
              "hasPaymentAgreement", "isConfirmed", "rationality", "indexNo"):
        assert parsed[k] == store_row[k], f"{k} 不保真: {parsed[k]} != {store_row[k]}"
    assert "rowId" in parsed
from pathlib import Path


# ───────────────────────────────────────────────────────────────────
# 双向回写真搬数据判据（T3 遗留1）：前端 store 行对象的键集
# 必须 == 后端 descriptor 的 json_path 集合。
#
# 背景：D4-24 曾存在第三套字段名（salesAmount/arBalance/thirdPartyName/
# relationTo*/hasAgreement/hasConfirmation/analysis/indexRef + id），与
# descriptor canonical 名不一致 ⇒ item_id 虽同为 D4-24-rows，但 projection
# 按 json_path 取不到值 = 双向回写「空搬」（只搬结构不搬数据）。
# 本守卫抽前端 ThirdPartyRow interface 字段名 vs descriptor json_path，
# 真行为判据（读两边源码做集合比对），非 grep 存在性。
# ───────────────────────────────────────────────────────────────────

_FRONTEND_D424_VUE = (
    Path(__file__).resolve().parents[2]
    / "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabThirdParty.vue"
)


def _extract_ts_interface_fields(source: str, iface_name: str) -> set[str]:
    """抽取 TS interface <name> 的字段名集合（到首个 '}' 为止，去注释/字符串）。

    边界用 'interface <name>' 起始锚点 + 首个 '\\n}' 结束锚点（非固定窗口、
    非 index() 一刀切，符合 memory「截函数体」铁律）。
    """
    start_anchor = f"interface {iface_name} "
    start = source.find(start_anchor)
    if start < 0:
        return set()
    end = source.find("\n}", start)
    if end < 0:
        return set()
    body = source[start + len(start_anchor) : end]
    fields: set[str] = set()
    for line in body.splitlines():
        # 去单行注释（'//' 后）
        if "//" in line:
            line = line.split("//", 1)[0]
        line = line.strip()
        if not line:
            continue
        # 字段形如 'field: type' 或 'field?: type'
        if ":" not in line:
            continue
        name = line.split(":", 1)[0].strip()
        if name.endswith("?"):
            name = name[:-1].strip()
        # 只认合法标识符（防把类型里的泛型角括号误判）
        if name and all(c.isalnum() or c == "_" for c in name):
            fields.add(name)
    return fields


def test_d424_frontend_store_keys_match_descriptor_json_paths():
    """前端 ThirdPartyRow 字段键集 == 后端 D4-24 descriptor json_path ∪ {rowId}。"""
    from app.services.workpaper_sync.phase5_d4_ipo_related_sheets import (
        MANAGED_FIELD_SPECS_D424,
        ROW_IDENTITY_STORE_KEY_D424,
        STORE_ITEM_ID_D424,
    )

    # 后端 canonical 键 = json_path 集合 + 行身份键。
    # 豁免：seq（序号）是前端 $index+1 派生展示列，与 D4-21 范式一致
    # （D4-21 RelatedPriceRow 同样无序号字段，序号列在 tab 内计算生成）。
    # 若 descriptor 增删受管列，此豁免须同步评估——禁静默扩张。
    DERIVED_DISPLAY_KEYS = {"seq"}

    backend_keys = {row[4] for row in MANAGED_FIELD_SPECS_D424}
    backend_keys.add(ROW_IDENTITY_STORE_KEY_D424)
    backend_keys -= DERIVED_DISPLAY_KEYS

    source = _FRONTEND_D424_VUE.read_text(encoding="utf-8")
    frontend_keys = _extract_ts_interface_fields(source, "ThirdPartyRow")

    assert STORE_ITEM_ID_D424 == "D4-24-rows"

    missing = backend_keys - frontend_keys  # 后端有、前端无 → projection 取空
    extra = frontend_keys - backend_keys    # 前端有、后端无 → 写不进去
    assert not missing, f"D4-24 前端缺 descriptor 字段（双向回写会空搬这些列）：{sorted(missing)}"
    assert not extra, f"D4-24 前端有多余字段（不会被 descriptor 持久化）：{sorted(extra)}"


def test_d424_no_legacy_field_names_remain():
    """旧第三套字段名必须零残留（防回退）。"""
    source = _FRONTEND_D424_VUE.read_text(encoding="utf-8")
    legacy = [
        "salesAmount", "arBalance", "thirdPartyName",
        "relationToCustomer", "relationToAuditee",
        "hasAgreement", "hasConfirmation", "indexRef",
    ]
    present = [name for name in legacy if name in source]
    # 'analysis' 用 r.analysis 精确定位（避免与 descriptor 的 rationality 无关子串混淆）
    for token in ("r.analysis", "row.id", "r.id"):
        if token in source:
            present.append(token)
    assert not present, f"D4-24 残留旧字段名（第三套模型未清干净）：{present}"


# ───────────────────────────────────────────────────────────────────
# D4-23 收入与开票比较：前端 composable 行对象键集
# 必须 == 后端 descriptor json_path 集合（含派生列豁免）。
#
# 背景：D4-23 曾有两个竞争 composable（useD4Ipo 存 D4-23-rows 用第四套
# 字段 month/revenue/invoiceAmount/diff；useD4InvoiceCompare 存 D4-23-data
# 用第三套 vatAmount/vatCount/normalAmount/normalCount/indexRef）。已收敛到
# 唯一活实现 useD4InvoiceCompare + item_id D4-23-rows。
# FORMULA_MASK = D,I,J（revenueTotal/invoiceTotal/diff 是前端本地派生，
# 对应模板内部公式，descriptor 已排除，不入契约）。
# ───────────────────────────────────────────────────────────────────

_FRONTEND_D423_TS = (
    Path(__file__).resolve().parents[2]
    / "audit-platform/frontend/src/components/workpaper/composables/useD4InvoiceCompare.ts"
)
_FRONTEND_D423_VUE = (
    Path(__file__).resolve().parents[2]
    / "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabInvoiceCompare.vue"
)

# 前端本地派生列（不持久化、不进 projection，对应 FORMULA_MASK D/I/J）
D423_DERIVED_KEYS = {"revenueTotal", "invoiceTotal", "diff"}


def test_d423_frontend_store_keys_match_descriptor_json_paths():
    """前端 InvoiceCompareRow 字段键集 == 后端 D4-23 descriptor json_path ∪ 派生列。"""
    from app.services.workpaper_sync.phase5_d4_ipo_related_sheets import (
        MANAGED_FIELD_SPECS_D423,
        ROW_IDENTITY_STORE_KEY_D423,
        STORE_ITEM_ID_D423,
    )

    backend_keys = {row[4] for row in MANAGED_FIELD_SPECS_D423}
    backend_keys.add(ROW_IDENTITY_STORE_KEY_D423)
    backend_keys |= D423_DERIVED_KEYS  # 前端派生列，descriptor 按 mask 排除

    source = _FRONTEND_D423_TS.read_text(encoding="utf-8")
    frontend_keys = _extract_ts_interface_fields(source, "InvoiceCompareRow")

    assert STORE_ITEM_ID_D423 == "D4-23-rows"

    missing = backend_keys - frontend_keys
    extra = frontend_keys - backend_keys
    assert not missing, f"D4-23 前端缺 descriptor 字段（双向回写会空搬这些列）：{sorted(missing)}"
    assert not extra, f"D4-23 前端有多余字段（不会被 descriptor 持久化）：{sorted(extra)}"


def test_d423_storage_key_and_no_legacy_fields():
    """存储键必须是 D4-23-rows；旧第三套/第四套字段名零残留。"""
    ts_source = _FRONTEND_D423_TS.read_text(encoding="utf-8")
    vue_source = _FRONTEND_D423_VUE.read_text(encoding="utf-8")

    # 活存储键 = D4-23-rows（与后端 STORE_ITEM_ID_D423 一致）
    assert "D4-23-rows" in ts_source
    assert "D4-23-data" not in ts_source, "D4-23 仍用旧键 D4-23-data（与后端 descriptor 不一致）"

    legacy = [
        "vatAmount", "vatCount", "normalAmount", "normalCount", "indexRef",
    ]
    # 词边界匹配（\b...\b）：避免把合法新名 vatInvoiceCount/vatCountTotal
    # 等含旧子串的标识符误判为残留。旧字段名在代码里总是独立标识符。
    present = []
    for name in legacy:
        pattern = rf"\b{re.escape(name)}\b"
        if re.search(pattern, ts_source) or re.search(pattern, vue_source):
            present.append(name)
    assert not present, f"D4-23 残留旧字段名：{present}"


# ───────────────────────────────────────────────────────────────────
# D4-22 重要指标分析：持久化形态字段键集
# 必须覆盖后端 descriptor 固定列 json_path + 行身份 metricName，
# 且动态同业列用 peer_N 稳定键（禁 label 作 key、禁写死列数）。
#
# 背景：D4-22 前端行模型是 {key,label,currentPeriod,priorPeriod,
# peers:[...],analysis,isAutoCalc}，与 descriptor 期望的扁平行
# {metricName,currentPeriod,priorPeriod,rationality,peer_1,peer_2,...}
# 形态不同（peers 数组 vs peer_N 展平）。descriptor 按 metricName 取行
# 身份（merge_projection_into_d422_store_rows 里 row.get("metricName")），
# 前端旧持久化直接写 label/analysis/peers 数组 ⇒ 后端 rid 恒空 ⇒ 双向
# 回写空搬。现已加 toPersistedRows 序列化层展平 + loadData 逆投影。
# ───────────────────────────────────────────────────────────────────

_FRONTEND_D422_TS = (
    Path(__file__).resolve().parents[2]
    / "audit-platform/frontend/src/components/workpaper/composables/useD4KeyIndicator.ts"
)


def test_d422_persist_shape_matches_descriptor():
    """D4-22 持久化键集覆盖 descriptor 固定列 + 行身份；动态列用 peer_N 稳定键。"""
    from app.services.workpaper_sync.phase5_d4_ipo_related_sheets import (
        METRIC_ROW_KEYS_D422,
        MANAGED_FIELD_SPECS_D422,
        ROW_IDENTITY_STORE_KEY_D422,
        STORE_ITEM_ID_D422,
        DYNAMIC_PEER_SLOT_D422,
    )

    source = _FRONTEND_D422_TS.read_text(encoding="utf-8")

    assert STORE_ITEM_ID_D422 == "D4-22-rows"
    assert ROW_IDENTITY_STORE_KEY_D422 == "metricName"

    # 固定列 json_path 必须在持久化层出现（toPersistedRows 输出键）
    fixed_json_paths = {row[4] for row in MANAGED_FIELD_SPECS_D422}
    fixed_json_paths.add(ROW_IDENTITY_STORE_KEY_D422)  # metricName
    missing = [k for k in fixed_json_paths if k not in source]
    assert not missing, f"D4-22 持久化层缺 descriptor 字段：{missing}"

    # 动态同业列：用 {slot}_{seq} 稳定键，禁 label 作 key、禁写死列数
    assert DYNAMIC_PEER_SLOT_D422 == "peer"
    # 展平表达式必须用 peer_${i+1} 形式的稳定键，而非 peers[label]
    assert "peer_${i + 1}" in source, "D4-22 动态同业列未用 peer_N 稳定键展平"
    # 持久化形态不得把 peers 数组直接写进 remark（会破坏扁平投影）
    assert "rows: toPersistedRows()" in source

    # 存储键对齐（活键 D4-22-rows，旧键 D4-22-data 零残留）
    assert "D4-22-rows" in source
    assert "D4-22-data" not in source, "D4-22 仍用旧键 D4-22-data"

    # 指标名真源一致：前端 INDICATOR_DEFINITIONS 的 label 必须覆盖后端 METRIC_ROW_KEYS_D422
    for metric in METRIC_ROW_KEYS_D422:
        assert metric in source, f"D4-22 前端缺指标行（行身份对不齐）：{metric}"


def test_d422_no_legacy_field_names():
    """D4-22 旧字段名 analysis 不得作为持久化键（已改 rationality）。"""
    source = _FRONTEND_D422_TS.read_text(encoding="utf-8")
    # 持久化层必须用 rationality（descriptor json_path），不是 analysis
    # analysis 只允许作为 UI 内部态字段名存在，且持久化时映射到 rationality
    assert "rationality: r.analysis" in source, "D4-22 持久化未把 analysis 映射到 rationality"
    # loadData 逆投影必须把 rationality 读回 analysis
    assert "analysis: src.rationality" in source, "D4-22 加载未把 rationality 逆投影回 analysis"

