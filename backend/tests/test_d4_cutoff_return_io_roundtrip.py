"""D4-17/18/19/20 截止/折扣/退货 导入导出 Round-Trip 与结构守卫

Feature: d4-cutoff-return-writeback-formula-io · IO 收口
Property（Requirements 1.2-1.5）：四表 export/import 往返后稳定 row id 与全部录入字段逐字段
一致，派生值由公式重算（isCutoff 留 None、discountRate/shouldProvide/diff 重算，不信文件值）。

行为级 PBT：驱动真实 _parse_d4_17/18/19/20_row + export 行构造。hypothesis max_examples=5。
参照 test_d4_inspection_io_roundtrip.py 同源写法。
"""

from __future__ import annotations

import datetime
import io

import openpyxl
from hypothesis import given, settings
from hypothesis import strategies as st

from app.routers.wp_render_strategies import _d4_import_export as mod


def _headers(sheet: str) -> list[str]:
    return mod._get_headers(sheet)


def _roundtrip(headers: list[str], row_values_list: list[list], parser) -> list[dict]:
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


_txt = st.text(max_size=14, alphabet=st.characters(min_codepoint=0x4E00, max_codepoint=0x9FFF))
_amt = st.floats(min_value=0, max_value=1e9, allow_nan=False, allow_infinity=False).map(lambda x: round(x, 2))
_date = st.dates(min_value=datetime.date(2020, 1, 1), max_value=datetime.date(2027, 12, 31)).map(lambda d: d.isoformat())


# ─── D4-17 截止（账到单据）：isCutoff 留 None ────────────────────────────────

@settings(max_examples=5)
@given(
    rows=st.lists(
        st.fixed_dictionaries({
            "voucherDate": _date, "voucherNo": _txt, "voucherProduct": _txt,
            "voucherQty": _txt, "voucherAmount": _amt,
            "deliveryDate": _date, "deliveryNo": _txt, "deliveryProduct": _txt,
            "deliveryQty": _txt, "deliveryAmount": _amt, "remark": _txt,
        }),
        min_size=1, max_size=5,
    ),
    poison_cutoff=st.sampled_from(["是", "否", "√", "×"]),
)
def test_d4_17_round_trip_cutoff_left_none(rows: list[dict], poison_cutoff: str) -> None:
    """**Validates: Requirements 1.2, 1.5, 4.2**

    D4-17：录入字段逐字段往返；isCutoff 留 None（前端 checkCutoff 重算），不采信文件跨期列。
    """
    headers = _headers("D4-17")
    row_values_list = []
    for r in rows:
        row_values_list.append([
            "",  # 序号
            r["voucherDate"], r["voucherNo"], r["voucherProduct"], r["voucherQty"], r["voucherAmount"],
            r["deliveryDate"], r["deliveryNo"], r["deliveryProduct"], r["deliveryQty"], r["deliveryAmount"],
            poison_cutoff,  # 是否跨期（污染 → parser 留 None）
            r["remark"],
        ])
    parsed = _roundtrip(headers, row_values_list, mod._parse_d4_17_row)
    assert len(parsed) == len(rows)
    for orig, got in zip(rows, parsed):
        assert got["id"].startswith("r-")
        assert got["voucherNo"] == mod._safe_str(orig["voucherNo"])
        assert got["voucherAmount"] == orig["voucherAmount"]
        assert got["deliveryDate"] == mod._safe_str(orig["deliveryDate"])
        assert got["deliveryAmount"] == orig["deliveryAmount"]
        assert got["remark"] == mod._safe_str(orig["remark"])
        assert got["isCutoff"] is None  # 派生列单源


# ─── D4-18 截止（单据到账） ─────────────────────────────────────────────────

@settings(max_examples=5)
@given(
    rows=st.lists(
        st.fixed_dictionaries({
            "deliveryDate": _date, "deliveryNo": _txt, "deliveryProduct": _txt,
            "deliveryQty": _txt, "deliveryAmount": _amt,
            "voucherDate": _date, "voucherNo": _txt, "voucherProduct": _txt,
            "voucherQty": _txt, "voucherAmount": _amt, "remark": _txt,
        }),
        min_size=1, max_size=5,
    ),
)
def test_d4_18_round_trip(rows: list[dict]) -> None:
    """**Validates: Requirements 1.2, 1.5**

    D4-18：发货单→凭证方向，字段逐字段往返，isCutoff 留 None。
    """
    headers = _headers("D4-18")
    row_values_list = []
    for r in rows:
        row_values_list.append([
            "",
            r["deliveryDate"], r["deliveryNo"], r["deliveryProduct"], r["deliveryQty"], r["deliveryAmount"],
            r["voucherDate"], r["voucherNo"], r["voucherProduct"], r["voucherQty"], r["voucherAmount"],
            "", r["remark"],
        ])
    parsed = _roundtrip(headers, row_values_list, mod._parse_d4_18_row)
    assert len(parsed) == len(rows)
    for orig, got in zip(rows, parsed):
        assert got["deliveryNo"] == mod._safe_str(orig["deliveryNo"])
        assert got["voucherAmount"] == orig["voucherAmount"]
        assert got["isCutoff"] is None


# ─── D4-19 销售折扣：discountRate 重算 ───────────────────────────────────────

@settings(max_examples=5)
@given(
    rows=st.lists(
        st.fixed_dictionaries({
            "customerName": _txt, "discountType": _txt,
            "revenueAmount": st.floats(min_value=1, max_value=1e8, allow_nan=False).map(lambda x: round(x, 2)),
            "discountAmount": st.floats(min_value=1, max_value=1e6, allow_nan=False).map(lambda x: round(x, 2)),
            "reason": _txt, "voucherDate": _date, "voucherNo": _txt,
            "accountSubject": _txt, "detailSubject": _txt,
            "debitAmount": _amt, "creditAmount": _amt,
            "approvalDate": _date, "approver": _txt, "remark": _txt,
        }),
        min_size=1, max_size=5,
    ),
    poison_rate=st.floats(min_value=-99, max_value=99, allow_nan=False).map(lambda x: round(x, 4)),
)
def test_d4_19_round_trip_rate_recompute(rows: list[dict], poison_rate: float) -> None:
    """**Validates: Requirements 1.2, 1.5, 4.2**

    D4-19：录入字段往返；discountRate = 折扣额/收入额 后端重算，不采信文件污染的比例列。
    """
    headers = _headers("D4-19")
    row_values_list = []
    for r in rows:
        row_values_list.append([
            "",  # 序号
            r["customerName"], r["discountType"],
            r["revenueAmount"], r["discountAmount"],
            poison_rate,  # 折扣比例（污染 → 重算覆盖）
            r["reason"], r["voucherDate"], r["voucherNo"],
            r["accountSubject"], r["detailSubject"],
            r["debitAmount"], r["creditAmount"],
            r["approvalDate"], r["approver"], r["remark"],
        ])
    parsed = _roundtrip(headers, row_values_list, mod._parse_d4_19_row)
    assert len(parsed) == len(rows)
    for orig, got in zip(rows, parsed):
        assert got["customerName"] == mod._safe_str(orig["customerName"])
        assert got["revenueAmount"] == orig["revenueAmount"]
        assert got["discountAmount"] == orig["discountAmount"]
        assert got["debitAmount"] == orig["debitAmount"]
        assert got["approver"] == mod._safe_str(orig["approver"])
        # 派生列单源：比例 = 折扣/收入 重算
        assert got["discountRate"] == orig["discountAmount"] / orig["revenueAmount"]


# ─── D4-20 退货明细（current/post）+ 计提（provision 派生重算）─────────────────

@settings(max_examples=5)
@given(
    rows=st.lists(
        st.fixed_dictionaries({
            "voucherDate": _date, "voucherNo": _txt, "bizContent": _txt,
            "subjectName": _txt, "detailSubject": _txt,
            "debitAmount": _amt, "creditAmount": _amt,
            "customerName": _txt, "productName": _txt,
            "returnQty": _txt, "returnAmount": _amt, "returnReason": _txt,
            "hasLitigation": st.sampled_from(["是", "否", ""]),
            "isAbnormal": st.sampled_from(["是", "否", ""]),
            "indexRef": _txt,
        }),
        min_size=1, max_size=4,
    ),
)
def test_d4_20_return_round_trip(rows: list[dict]) -> None:
    """**Validates: Requirements 1.2, 1.3**

    D4-20 退货明细（current/post 同构）：字段逐字段往返，稳定 id。
    """
    headers = _headers("D4-20-current")
    row_values_list = []
    for r in rows:
        row_values_list.append([
            "",
            r["voucherDate"], r["voucherNo"], r["bizContent"], r["subjectName"], r["detailSubject"],
            r["debitAmount"], r["creditAmount"], r["customerName"], r["productName"],
            r["returnQty"], r["returnAmount"], r["returnReason"],
            r["hasLitigation"], r["isAbnormal"], r["indexRef"],
        ])
    parsed = _roundtrip(headers, row_values_list, mod._parse_d4_20_return_row)
    assert len(parsed) == len(rows)
    for orig, got in zip(rows, parsed):
        assert got["id"].startswith("r-")
        assert got["voucherNo"] == mod._safe_str(orig["voucherNo"])
        assert got["returnAmount"] == orig["returnAmount"]
        assert got["hasLitigation"] == mod._safe_str(orig["hasLitigation"])
        assert got["isAbnormal"] == mod._safe_str(orig["isAbnormal"])


@settings(max_examples=5)
@given(
    rows=st.lists(
        st.fixed_dictionaries({
            "productName": _txt,
            "base": _amt,
            "rate": st.floats(min_value=0, max_value=1, allow_nan=False).map(lambda x: round(x, 4)),
            "alreadyProvided": _amt,
            "diffReason": _txt,
        }),
        min_size=1, max_size=4,
    ),
    poison_should=_amt,
    poison_diff=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False).map(lambda x: round(x, 2)),
)
def test_d4_20_provision_round_trip_recompute(rows: list[dict], poison_should: float, poison_diff: float) -> None:
    """**Validates: Requirements 1.2, 1.5, 4.2**

    D4-20 计提：应计提=基数×比例、差异=应计提−已计提 后端重算，不采信文件派生列。
    """
    headers = _headers("D4-20-provision")
    row_values_list = []
    for r in rows:
        row_values_list.append([
            "",  # 序号
            r["productName"], r["base"], r["rate"],
            poison_should,   # 应计提金额（污染 → 重算）
            r["alreadyProvided"],
            poison_diff,     # 差异金额（污染 → 重算）
            r["diffReason"],
        ])
    parsed = _roundtrip(headers, row_values_list, mod._parse_d4_20_provision_row)
    assert len(parsed) == len(rows)
    for orig, got in zip(rows, parsed):
        assert got["base"] == orig["base"]
        assert got["rate"] == orig["rate"]
        assert got["alreadyProvided"] == orig["alreadyProvided"]
        # 派生列单源
        assert got["shouldProvide"] == orig["base"] * orig["rate"]
        assert got["diff"] == orig["base"] * orig["rate"] - orig["alreadyProvided"]


# ─── 结构守卫：item_id 双侧一致（含 D4-20 子表键错位修复）+ 死配置删除 ─────────

from pathlib import Path


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for _ in range(8):
        if (p / "backend").exists() and (p / "audit-platform").exists():
            return p
        p = p.parent
    raise RuntimeError("repo root not found")


def _read(rel: str) -> str:
    return (_repo_root() / rel).read_text(encoding="utf-8")


def test_d4_20_subtable_key_alignment() -> None:
    """**Validates: Requirements 1.1, 1.3**

    🔴 D4-20 子表键错位修复：后端 sheet 码 D4-20-current/post → item_id
    D4-20-current-returns/post-returns（对齐前端 store 键，DEC-2），provision → D4-20-provision。
    前端组件确实用这些键。
    """
    src = _read("backend/app/routers/wp_render_strategies/_d4_import_export.py")
    # 后端 import+export 两侧都映射到前端键
    assert src.count('item_id = "D4-20-current-returns"') >= 2
    assert src.count('item_id = "D4-20-post-returns"') >= 2
    # 前端组件确实用这些键
    fe = _read("audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabReturn.vue")
    assert "'D4-20-current-returns'" in fe
    assert "'D4-20-post-returns'" in fe
    assert "'D4-20-provision'" in fe


def test_d4_20_bare_sheet_dead_config_removed() -> None:
    """**Validates: Requirements 1.1（DEC-1）**

    D4-20 主 sheet 是死配置（前端只用三子表）→ 已从 _SUPPORTED_SHEETS / _SHEET_HEADERS 删除。
    """
    assert "D4-20" not in mod._SUPPORTED_SHEETS
    assert mod._get_headers("D4-20") == mod._GENERIC_HEADERS  # 不再有专用 header
    # 三子表仍在
    for s in ("D4-20-current", "D4-20-post", "D4-20-provision"):
        assert s in mod._SUPPORTED_SHEETS
        assert mod._get_headers(s) != mod._GENERIC_HEADERS


def test_d4_17_18_19_dispatch_dedicated_parsers() -> None:
    """**Validates: Requirements 1.2**

    import 分发 D4-17/18/19 走专用 parser（不再 generic 兜底）。
    """
    import re
    src = _read("backend/app/routers/wp_render_strategies/_d4_import_export.py")
    assert re.search(r'elif sheet == "D4-17":\s*\n\s*row_dict = _parse_d4_17_row', src)
    assert re.search(r'elif sheet == "D4-18":\s*\n\s*row_dict = _parse_d4_18_row', src)
    assert re.search(r'elif sheet == "D4-19":\s*\n\s*row_dict = _parse_d4_19_row', src)
    assert re.search(r'elif sheet in \("D4-20-current", "D4-20-post"\):\s*\n\s*row_dict = _parse_d4_20_return_row', src)
