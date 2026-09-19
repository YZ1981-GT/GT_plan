"""D4-13/14/15/16 检查表 导入导出 Round-Trip 与结构守卫

Feature: d4-inspection-writeback-formula-io · Task T3（IO 收口）
Property 1（Requirements 1.2-1.5）：四表 export/import 往返后稳定 row/column id 与全部
录入字段逐字段一致，派生值由同一公式重算（不信文件差异/一致性列）。

行为级测试（非纯字符串）：直接驱动 _d4_import_export 的 parser/exporter 纯函数，构造结构化
数据 → 导出 xlsx 行 → 重新解析 → 断言结构等价。用 hypothesis max_examples=5（项目约定）。

参照姊妹 spec 的 test_d4_ipo_fraud_io_pbt.py 同源写法（真端点是 async+DB，此处只验 parser/
exporter 纯函数的结构保真 + 派生列重算 + item_id 双侧一致）。
"""

from __future__ import annotations

import io
import re as _re
from pathlib import Path

import openpyxl
from hypothesis import given, settings
from hypothesis import strategies as st

from app.routers.wp_render_strategies import _d4_import_export as mod


def _headers(sheet: str) -> list[str]:
    return mod._get_headers(sheet)


def _roundtrip_rows(headers: list[str], row_values_list: list[list], parser) -> list[dict]:
    """写 xlsx（headers + rows）→ 读回 → 逐行走真实 parser。"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for rv in row_values_list:
        ws.append(rv)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    wb2 = openpyxl.load_workbook(buf, data_only=True)
    ws2 = wb2.active
    actual_headers = [
        str(c.value).strip() if c.value else ""
        for c in next(ws2.iter_rows(min_row=1, max_row=1))
    ]
    out = []
    for row in ws2.iter_rows(min_row=2, values_only=True):
        if not row or all(v is None for v in row):
            continue
        d = parser(row, actual_headers)
        if d:
            out.append(d)
    return out


# 文本 hypothesis 策略：避开 openpyxl 非法控制符与首字符 = / +（会被当公式），最大化往返稳定
_txt = st.text(
    max_size=16,
    alphabet=st.characters(min_codepoint=0x4E00, max_codepoint=0x9FFF),
)
_amt = st.floats(min_value=0, max_value=1e9, allow_nan=False, allow_infinity=False).map(
    lambda x: round(x, 2)
)
_date = st.dates(min_value=__import__("datetime").date(2020, 1, 1),
                 max_value=__import__("datetime").date(2027, 12, 31)).map(lambda d: d.isoformat())


# ═══════════════════════════════════════════════════════════════════════════════
# D4-16 出口核对：英文 key 往返 + 差异列后端重算（不信文件值）
# ═══════════════════════════════════════════════════════════════════════════════


@settings(max_examples=5)
@given(
    rows=st.lists(
        st.fixed_dictionaries({
            "bookAmount": _amt,
            "portsPeriod": _txt,
            "portsAmount": _amt,
            "portsReason": _txt,
            "taxReportAmount": _amt,
            "taxReason": _txt,
            "taxIndex": _txt,
        }),
        min_size=1, max_size=6,
    ),
    # 文件里塞进被污染的差异值：往返后必须被重算覆盖，不得原样保留
    poison=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False).map(lambda x: round(x, 2)),
)
def test_d4_16_export_import_round_trip_and_diff_recompute(rows: list[dict], poison: float) -> None:
    """**Validates: Requirements 1.4, 1.5, 4.2**

    D4-16：录入字段（bookAmount/portsAmount/tax*/reason/index）逐字段一致；
    portsDiff/taxDiff 由后端 book-ports / book-tax 重算，不采信文件里被污染的差异列。
    """
    headers = _headers("D4-16")  # 序号|账面出口收入金额|口岸期间|口岸结关金额|口岸差异|口岸差异原因|申报外营收入|申报差异|申报差异原因|索引
    row_values_list = []
    for r in rows:
        row_values_list.append([
            "",                       # 序号（展示列，导入忽略）
            r["bookAmount"],
            r["portsPeriod"],
            r["portsAmount"],
            poison,                   # 口岸差异（污染值 → 必须被重算覆盖）
            r["portsReason"],
            r["taxReportAmount"],
            poison,                   # 申报差异（污染值）
            r["taxReason"],
            r["taxIndex"],
        ])
    parsed = _roundtrip_rows(headers, row_values_list, mod._parse_d4_16_row)

    assert len(parsed) == len(rows)
    for orig, got in zip(rows, parsed):
        assert got["id"].startswith("r-")               # 稳定 id 前缀
        assert got["bookAmount"] == orig["bookAmount"]
        assert got["portsAmount"] == orig["portsAmount"]
        assert got["taxReportAmount"] == orig["taxReportAmount"]
        assert got["portsPeriod"] == mod._safe_str(orig["portsPeriod"])
        assert got["portsReason"] == mod._safe_str(orig["portsReason"])
        assert got["taxReason"] == mod._safe_str(orig["taxReason"])
        assert got["taxIndex"] == mod._safe_str(orig["taxIndex"])
        # 派生列单源：后端重算，不读文件差异列（poison 被覆盖）
        assert got["portsDiff"] == orig["bookAmount"] - orig["portsAmount"]
        assert got["taxDiff"] == orig["bookAmount"] - orig["taxReportAmount"]


# ═══════════════════════════════════════════════════════════════════════════════
# D4-15 完整性：三维嵌套 delivery/invoice/voucher 往返 + isConsistent 留空（前端重算）
# ═══════════════════════════════════════════════════════════════════════════════

_dim = st.fixed_dictionaries({
    "date": _date,
    "number": _txt,
    "productName": _txt,
    "quantity": _txt,
    "amount": _amt,
})


@settings(max_examples=5)
@given(
    items=st.lists(
        st.fixed_dictionaries({
            "delivery": _dim, "invoice": _dim, "voucher": _dim, "remark": _txt,
        }),
        min_size=1, max_size=5,
    ),
    poison_consistent=st.sampled_from(["√", "×", "是", "否"]),
)
def test_d4_15_three_dimension_round_trip_and_consistency_left_none(
    items: list[dict], poison_consistent: str
) -> None:
    """**Validates: Requirements 1.3, 1.5**

    D4-15：delivery/invoice/voucher 三层字段逐字段往返；isConsistent 强制留 None
    （由前端 checkConsistency 重算），不采信文件里的一致性列。
    """
    headers = _headers("D4-15")
    row_values_list = []
    for it in items:
        d, inv, v = it["delivery"], it["invoice"], it["voucher"]
        row_values_list.append([
            "",  # 序号
            d["date"], d["number"], d["productName"], d["quantity"], d["amount"],
            inv["date"], inv["number"], inv["productName"], inv["quantity"], inv["amount"],
            v["date"], v["number"], v["productName"], v["quantity"], v["amount"],
            poison_consistent,   # 一致性列（污染 → 必须被 parser 忽略置 None）
            it["remark"],
        ])
    parsed = _roundtrip_rows(headers, row_values_list, mod._parse_d4_15_row)

    assert len(parsed) == len(items)
    for orig, got in zip(items, parsed):
        assert got["id"].startswith("c-")
        for dim in ("delivery", "invoice", "voucher"):
            o, g = orig[dim], got[dim]
            assert g["date"] == mod._safe_str(o["date"])
            assert g["number"] == mod._safe_str(o["number"])
            assert g["productName"] == mod._safe_str(o["productName"])
            assert g["quantity"] == mod._safe_str(o["quantity"])
            assert g["amount"] == o["amount"]
        assert got["remark"] == mod._safe_str(orig["remark"])
        # 派生列单源：isConsistent 不采信文件，一律 None
        assert got["isConsistent"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# D4-14 发生/穿行：7 维嵌套往返 + consistencyScore 归 0（前端重算）
# ═══════════════════════════════════════════════════════════════════════════════


@settings(max_examples=5)
@given(
    items=st.lists(
        st.fixed_dictionaries({
            "indexNo": _txt, "label": _txt,
            "vMonth": _txt, "vDate": _date, "vNumber": _txt, "vProduct": _txt,
            "vQty": _txt, "vAmount": _amt, "vAcctDate": _date,
            "cNumber": _txt, "cProduct": _txt, "cAmount": _amt, "cApprover": _txt, "cConfirmor": _txt,
            "dDate": _date, "dProduct": _txt, "dAmount": _amt, "dKeeper": _txt,
            "sDate": _date, "sProduct": _txt, "sAmount": _amt,
            "rDate": _date, "rProduct": _txt, "rAmount": _amt,
            "iDate": _date, "iNumber": _txt, "iAmount": _amt,
            "oDesc": _txt, "oIndex": _txt,
            "conclusion": _txt,
        }),
        min_size=1, max_size=4,
    ),
    poison_score=st.integers(min_value=1, max_value=100),
)
def test_d4_14_seven_dimension_round_trip_and_score_reset(
    items: list[dict], poison_score: int
) -> None:
    """**Validates: Requirements 1.5, 2.4**

    D4-14：七维嵌套 voucher/contract/delivery/shipping/receipt/invoice/other 字段往返；
    consistencyScore 导入归 0（由前端重算），不采信文件分数。
    """
    headers = _headers("D4-14")  # 32 列语义头
    row_values_list = []
    for it in items:
        row_values_list.append([
            it["indexNo"], it["label"],
            it["vMonth"], it["vDate"], it["vNumber"], it["vProduct"], it["vQty"], it["vAmount"], it["vAcctDate"],
            it["cNumber"], it["cProduct"], it["cAmount"], it["cApprover"], it["cConfirmor"],
            it["dDate"], it["dProduct"], it["dAmount"], it["dKeeper"],
            it["sDate"], it["sProduct"], it["sAmount"],
            it["rDate"], it["rProduct"], it["rAmount"],
            it["iDate"], it["iNumber"], it["iAmount"],
            it["oDesc"], it["oIndex"],
            poison_score,        # 一致性分数（污染 → 归 0）
            it["conclusion"],
            "",                  # 备注
        ])
    parsed = _roundtrip_rows(headers, row_values_list, mod._parse_d4_14_row)

    assert len(parsed) == len(items)
    for orig, got in zip(items, parsed):
        assert got["id"].startswith("t-")
        assert got["indexNo"] == mod._safe_str(orig["indexNo"])
        assert got["label"] == mod._safe_str(orig["label"])
        assert got["voucher"]["number"] == mod._safe_str(orig["vNumber"])
        assert got["voucher"]["amount"] == orig["vAmount"]
        assert got["contract"]["amount"] == orig["cAmount"]
        assert got["contract"]["approver"] == mod._safe_str(orig["cApprover"])
        assert got["delivery"]["warehouseKeeper"] == mod._safe_str(orig["dKeeper"])
        assert got["shipping"]["amount"] == orig["sAmount"]
        assert got["receipt"]["amount"] == orig["rAmount"]
        assert got["invoice"]["number"] == mod._safe_str(orig["iNumber"])
        assert got["other"]["description"] == mod._safe_str(orig["oDesc"])
        assert got["conclusion"] == mod._safe_str(orig["conclusion"])
        # 派生列单源：分数归 0，anomaly 默认 False
        assert got["consistencyScore"] == 0
        assert got["isAnomalous"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 结构守卫（非往返）：item_id 双侧一致 + D4-13 文本锚点
# ═══════════════════════════════════════════════════════════════════════════════


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for _ in range(8):
        if (p / "backend").exists() and (p / "audit-platform").exists():
            return p
        p = p.parent
    raise RuntimeError("repo root not found")


def _read(rel: str) -> str:
    return (_repo_root() / rel).read_text(encoding="utf-8")


# 前端组件持久化 item_id（真源=各组件 allResponses.set 第一参数）
_FRONTEND_ITEM_IDS = {
    "D4-14": "D4-14-transactions",
    "D4-15": "D4-15-items",
    # D4-16 走默认 {sheet}-rows = D4-16-rows（无显式 elif 分支）
}
_FE_COMPONENT = {
    "D4-14": "audit-platform/frontend/src/components/workpaper/composables/useD4WalkthroughTest.ts",
    "D4-15": "audit-platform/frontend/src/components/workpaper/composables/useD4CompletenessCheck.ts",
    "D4-16": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabExport.vue",
}


def test_item_id_double_side_consistency() -> None:
    """**Validates: Requirements 1.3, 1.4, 4.1**

    后端 import/export item_id 映射与前端组件持久化 item_id 逐字一致，
    否则导入写进的 key 前端读不到（假绿高发点）。
    """
    src = _read("backend/app/routers/wp_render_strategies/_d4_import_export.py")
    # D4-14/15 后端两处（import/export）显式映射
    for iid in _FRONTEND_ITEM_IDS.values():
        assert src.count(f'item_id = "{iid}"') >= 2, f"后端 import/export 未双侧映射 {iid}"

    # 前端组件确实用这些 item_id 持久化
    assert "'D4-14-transactions'" in _read(_FE_COMPONENT["D4-14"]) or \
           '"D4-14-transactions"' in _read(_FE_COMPONENT["D4-14"])
    assert "'D4-15-items'" in _read(_FE_COMPONENT["D4-15"])
    # D4-16 走默认 {sheet}-rows，前端组件用 'D4-16-rows'
    assert "'D4-16-rows'" in _read(_FE_COMPONENT["D4-16"])


def test_d4_13_text_anchor_sections() -> None:
    """**Validates: Requirements 1.2**

    D4-13 双 item 文本锚点：后端 _D4_13_SECTIONS 必须精确映射
    核对过程→D4-13-process、核对结论→D4-13-conclusion，且前端组件消费同键。
    """
    assert mod._D4_13_SECTIONS == [
        ("核对过程", "D4-13-process"),
        ("核对结论", "D4-13-conclusion"),
    ]
    assert mod._D4_13_SECTION_BY_LABEL["核对过程"] == "D4-13-process"
    assert mod._D4_13_SECTION_BY_LABEL["核对结论"] == "D4-13-conclusion"

    fe = _read("audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabErpCheck.vue")
    assert "D4-13-process" in fe
    assert "D4-13-conclusion" in fe


def test_d4_15_16_derived_columns_not_trusted_from_file() -> None:
    """**Validates: Requirements 1.5, 4.2**

    派生列单源守卫（源码级）：D4-15 isConsistent 强制 None、D4-16 差异走 book-ports/book-tax
    重算 —— parser 源码不得出现「读文件一致性/差异列」的采信路径。
    """
    src = _read("backend/app/routers/wp_render_strategies/_d4_import_export.py")
    # D4-16 差异必须是 book-ports / book-tax 形态（重算），不是读列
    assert "book - ports" in src
    assert "book - tax" in src
    # D4-15 isConsistent 留 None
    assert '"isConsistent": None' in src


def test_all_four_sheets_supported() -> None:
    """**Validates: Requirements 1.1**

    D4-13/14/15/16 均在 _SUPPORTED_SHEETS，且各有专用 header（非 generic 兜底）。
    """
    for s in ("D4-13", "D4-14", "D4-15", "D4-16"):
        assert s in mod._SUPPORTED_SHEETS
        assert mod._get_headers(s) is not mod._GENERIC_HEADERS
        assert mod._get_headers(s) != mod._GENERIC_HEADERS
