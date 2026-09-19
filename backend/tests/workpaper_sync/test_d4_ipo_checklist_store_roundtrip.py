# -*- coding: utf-8 -*-
"""D4-25/26/27/28 IPO 检查表：**生产路径** store projection roundtrip。

spec: d4-ipo-checklist-dual-mode-writeback-and-formula · Requirement 2（AC 2.3/2.4）
Properties: **P6 / P7 / P8**

═══ 为什么必须有这个文件（复盘实证的守卫空洞）═══

Property 6/7/8（金额往返一致 / 单元格↔行字段相等 / 全空行不产生行记录）此前**只被前端
`ipoSyncBridge.spec.ts` 覆盖，而它测的是 `ipoChecklistSchema.rowsToSheet` / `sheetToRows`
两个在生产代码里零调用方的纯函数** —— 也就是「测了一个不参与运行的实现」。

真正在跑的是后端 provider `phase5_d4_ipo_checklist_sheets`：
`build_store_projection`（HTML store rows → FieldValue projection）与
`merge_projection_into_rows`（projection → rows）。全 `backend/` 唯一 import 该 provider 的
测试（`test_d4_ipo_checklist_cross_lang_contract.py`）**只读 `_SHEETS` 常量、从不调这两个函数**，
而同目录其它 D4 受管表都有 roundtrip 测试（`test_d43_production_roundtrip.py` 等）。
于是这四张表的投影在生产路径上零覆盖。本文件补上。

判据刻意落在**真实解析出来的契约**上（`D4.build_contract_payload()` → `parse_contract`），
不自造 contract stub —— 否则列字母/stable key/value_type 任一漂移都测不出来。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import phase5_d4_ipo_checklist_sheets as CK  # noqa: E402
from app.services.workpaper_sync import phase5_d4_revenue_detail as D4  # noqa: E402
from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402


@pytest.fixture(scope="module")
def contract() -> Any:
    """真实契约（provider 现算 payload → parse_contract），非 stub。"""
    return parse_contract(D4.build_contract_payload(), adapter_id=D4.ADAPTER_ID)


def _row(code: str, rid: str, **over: Any) -> dict[str, Any]:
    """构造一行：按该 sheet 的 json_path（前端 camelCase 列 key）填值。"""
    row: dict[str, Any] = {"rowId": rid}
    row.update(over)
    return row


def _json_paths(code: str) -> list[str]:
    return [spec[4] for spec in CK._SHEETS[code]["fields"]]


def _be_key(code: str, json_path: str) -> str:
    """json_path（前端 camelCase 列 key）→ 后端 column_key（stable key 尾段用它）。"""
    for spec in CK._SHEETS[code]["fields"]:
        if spec[4] == json_path:
            return spec[0]
    raise KeyError(f"{code}: 找不到 json_path={json_path} 的后端 column_key")


# ═══════════════════════════════════════════════════════════════════════════
# P7：rows → projection → rows 逐字段相等（单元格 ↔ 行字段）
# ═══════════════════════════════════════════════════════════════════════════


def _checkbox_paths(code: str) -> set[str]:
    """该 sheet 的勾选列 json_path（value_type=boolean）。"""
    return {spec[4] for spec in CK._SHEETS[code]["fields"] if spec[3] == "boolean"}


def _sample_value(code: str, json_path: str) -> Any:
    """按列类型给一个可区分的往返测试值（boolean 列给 True，其余给唯一字符串）。"""
    return True if json_path in _checkbox_paths(code) else f"v-{json_path}"


@pytest.mark.parametrize("code", CK.CHECKLIST_SHEET_CODES)
def test_roundtrip_preserves_every_managed_field(code: str, contract: Any) -> None:
    """每个受管列的值经 build → merge 往返后逐字段相等（P7）。

    🔴 boolean（勾选）列与 text/amount 列要用各自类型的值：boolean 列塞字符串会被
    normalize 拒绝。勾选列给 `True`，往返回来应仍是 `True`（勾选态保持）。
    """
    paths = _json_paths(code)
    cb = _checkbox_paths(code)
    payload = [_row(code, "row-A", **{p: _sample_value(code, p) for p in paths})]

    proj = CK.build_store_projection(code, payload, contract=contract)
    merged, applied, visited, touched = CK.merge_projection_into_rows(
        code, projection=proj, base_rows=[{"rowId": "row-A"}]
    )

    assert len(merged) == 1, f"{code}: 往返后行数变了"
    got = merged[0]
    for p in paths:
        expected = True if p in cb else f"v-{p}"
        assert got.get(p) == expected, f"{code}: 列 {p} 往返丢值/串列（实得 {got.get(p)!r}）"
    assert applied > 0 and visited >= applied
    assert touched == {"row-A"}


# ═══════════════════════════════════════════════════════════════════════════
# checkbox「勾选=1 / 未勾=空」口径：接通后的端到端判据（BP-22 boolean 链路）
#
# 🔴 复盘接通前这条口径在生产路径**没有实现者**：契约 value_type=text、provider 原值
#    照抄布尔 → OO 里落成字面量 "True" 而非数字 1。现改为 value_type=boolean + 两向桥接，
#    本组判据钉住新口径，防再次退化。
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("code", ("D4-26", "D4-27", "D4-28"))
def test_checkbox_columns_are_boolean_value_type(code: str) -> None:
    """三张带勾选框的表，勾选列 value_type 必须是 boolean（不是 text，也不是 integer）。"""
    cb = _checkbox_paths(code)
    assert cb, f"{code}: 没有 boolean 勾选列 —— 口径又退回 text 了？"
    # 数量核对：D4-26 五个 check_* / D4-27 十个 is_*（不含 is_duplicate_name）/ D4-28 五个 method_*
    expected = {"D4-26": 5, "D4-27": 10, "D4-28": 5}[code]
    assert len(cb) == expected, f"{code}: 勾选列数应为 {expected}，实得 {len(cb)}（{sorted(cb)}）"


@pytest.mark.parametrize("code", ("D4-26", "D4-27", "D4-28"))
def test_checked_maps_to_true_unchecked_maps_to_none(code: str, contract: Any) -> None:
    """勾选（前端 True）→ 投影 True（落 OO `<v>1</v>`）；未勾（False/空）→ 投影 None（落空格）。

    🔴 未勾必须是 None 而不是 False：boolean_literal 对 False 落 `<v>0</v>`，会把「未填」
    变成满屏 0，与源模板「勾选=1 / 未勾=空白」口径不符。
    """
    cb = sorted(_checkbox_paths(code))
    checked_path, unchecked_path = cb[0], cb[1]
    name_path = _json_paths(code)[1]
    payload = [
        _row(code, "r1", **{name_path: "甲", checked_path: True, unchecked_path: False}),
    ]
    proj = CK.build_store_projection(code, payload, contract=contract)

    def _val(path: str) -> Any:
        hits = [proj.get(k) for k in proj.stable_keys() if str(k).endswith(f"/{_be_key(code, path)}")]
        return hits[0].value if hits and hits[0] is not None else "MISSING"

    assert _val(checked_path) is True, f"{code}: 勾选列 {checked_path} 投影值应为 True"
    # 未勾的列：build 侧 False→None ⇒ 该 stable key 的 FieldValue.value 为 None
    unchecked_hits = [
        proj.get(k).value  # type: ignore[union-attr]
        for k in proj.stable_keys()
        if str(k).endswith(f"/{_be_key(code, unchecked_path)}") and proj.get(k) is not None
    ]
    assert unchecked_hits == [None], (
        f"{code}: 未勾列 {unchecked_path} 应投影为 None（未勾=空格），实得 {unchecked_hits}"
    )


@pytest.mark.parametrize("code", ("D4-26", "D4-27", "D4-28"))
def test_checkbox_merge_back_yields_strict_bool(code: str, contract: Any) -> None:
    """回读（projection → rows）：勾选 → True，未勾 → False（前端 el-checkbox 要严格布尔）。"""
    cb = sorted(_checkbox_paths(code))
    checked_path, unchecked_path = cb[0], cb[1]
    name_path = _json_paths(code)[1]
    payload = [_row(code, "r1", **{name_path: "甲", checked_path: True, unchecked_path: False})]
    proj = CK.build_store_projection(code, payload, contract=contract)
    merged, _a, _v, _t = CK.merge_projection_into_rows(
        code, projection=proj, base_rows=[{"rowId": "r1"}]
    )
    assert merged[0][checked_path] is True, f"{code}: 勾选列回读应为 True"
    assert merged[0][unchecked_path] is False, f"{code}: 未勾列回读应为 False（严格布尔）"


@pytest.mark.parametrize("code", CK.CHECKLIST_SHEET_CODES)
def test_amount_roundtrip_within_tolerance(code: str, contract: Any) -> None:
    """金额列数值往返一致（P6，容差 0.005）。"""
    amount_paths = [
        spec[4] for spec in CK._SHEETS[code]["fields"] if spec[3] == "amount"
    ]
    assert amount_paths, f"{code}: 该表没有 amount 列，判据会恒真"
    payload = [_row(code, "row-A", **{p: 1234.56 for p in amount_paths})]

    proj = CK.build_store_projection(code, payload, contract=contract)
    merged, _a, _v, _t = CK.merge_projection_into_rows(
        code, projection=proj, base_rows=[{"rowId": "row-A"}]
    )

    for p in amount_paths:
        assert abs(float(merged[0][p]) - 1234.56) <= 0.005, f"{code}: 金额列 {p} 往返超容差"


# ═══════════════════════════════════════════════════════════════════════════
# P8 同族：行身份是唯一定位依据（不靠下标、不靠排序）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("code", CK.CHECKLIST_SHEET_CODES)
def test_row_identity_is_authoritative_not_ordinal(code: str, contract: Any) -> None:
    """merge 按 rowId 对齐；base_rows 顺序与 projection 顺序不同也不得串行。

    🔴 这条是前端死函数 `sheetToRows`（按网格行序派生 seq）与后端真实行为的**关键差异**：
    后端行定位是 `row_from="row_identity"`（UUID 列），顺序无关。
    """
    name_path = _json_paths(code)[1]  # 第二列通常是名称列（seq 之后）
    payload = [
        _row(code, "row-1", **{name_path: "第一行"}),
        _row(code, "row-2", **{name_path: "第二行"}),
    ]
    proj = CK.build_store_projection(code, payload, contract=contract)

    # base_rows 故意倒序
    merged, _a, _v, _t = CK.merge_projection_into_rows(
        code, projection=proj, base_rows=[{"rowId": "row-2"}, {"rowId": "row-1"}]
    )
    by_id = {r["rowId"]: r for r in merged}
    assert by_id["row-1"][name_path] == "第一行", f"{code}: 行按下标串了"
    assert by_id["row-2"][name_path] == "第二行", f"{code}: 行按下标串了"


@pytest.mark.parametrize("code", CK.CHECKLIST_SHEET_CODES)
def test_row_without_identity_is_rejected(code: str, contract: Any) -> None:
    """缺 rowId 的行必须被拒（禁下标兜底）—— 这是后端「不产生幽灵行」的真实机制（P8）。"""
    with pytest.raises(CK.D4ChecklistDigestError, match="稳定行身份"):
        CK.build_store_projection(code, [{"customerName": "无身份行"}], contract=contract)


@pytest.mark.parametrize("code", CK.CHECKLIST_SHEET_CODES)
def test_duplicate_row_identity_is_rejected(code: str, contract: Any) -> None:
    """重复 rowId 必须被拒（否则两行会互相覆盖且无人知情）。"""
    with pytest.raises(CK.D4ChecklistDigestError, match="重复行身份"):
        CK.build_store_projection(
            code, [{"rowId": "dup"}, {"rowId": "dup"}], contract=contract
        )


@pytest.mark.parametrize("code", CK.CHECKLIST_SHEET_CODES)
def test_empty_store_yields_no_rows(code: str, contract: Any) -> None:
    """空 store → 零行（P8：不凭空造行）。"""
    proj = CK.build_store_projection(code, [], contract=contract)
    table_key = CK._SHEETS[code]["table_key"]
    assert proj.row_keys[table_key] == ()
    merged, applied, _v, touched = CK.merge_projection_into_rows(
        code, projection=proj, base_rows=[]
    )
    assert merged == [] and applied == 0 and touched == set()


# ═══════════════════════════════════════════════════════════════════════════
# D4-27 总计列：源模板内嵌 =SUM(C:L)，必须入 mask 且**不进契约**
# ═══════════════════════════════════════════════════════════════════════════


def test_d427_total_column_is_masked_and_unmanaged(contract: Any) -> None:
    """`total` 不得出现在受管字段里，且 M 列区间在 formula_mask（投影不得覆盖内嵌公式）。"""
    paths = _json_paths("D4-27")
    assert "total" not in paths, "D4-27 total 列进了受管契约 —— 会覆盖源模板 =SUM(C15:L15)"
    assert "M15:M24" in CK._SHEETS["D4-27"]["formula_mask"]

    # 即便 store 里带了 total（前端派生列会写进 rows），投影也不该产出它
    proj = CK.build_store_projection(
        "D4-27", [{"rowId": "r1", "name": "陈某", "total": 3}], contract=contract
    )
    leaked = [k for k in proj.stable_keys() if str(k).endswith("/total")]
    assert not leaked, f"total 泄漏进 projection: {leaked}"


# ═══════════════════════════════════════════════════════════════════════════
# checkbox 「1 ↔ true」口径已接通：勾选列显式枚举 + is_duplicate_name 仍是 text select
# （详细往返判据见上文 test_checked_maps_to_true_* / test_checkbox_merge_back_* 三组）
# ═══════════════════════════════════════════════════════════════════════════


def test_checkbox_columns_enumerated_and_boolean() -> None:
    """勾选列必须与显式枚举逐一对齐且 value_type=boolean；is_duplicate_name 保持 text（Y/N select）。

    🔴 显式枚举而不是按 `is_*` 前缀猜：D4-27 的 `is_duplicate_name`（重名 Y/N）也以 is_
    开头但是 select 列，前缀启发式会把它误算进勾选列。
    """
    checkbox_columns = {
        "D4-26": (
            "check_field_visit", "check_trans_confirm", "check_customs_confirm",
            "check_declaration", "check_eport_data",
        ),
        "D4-27": (
            "is_personal_customer", "is_customer_legal", "is_contract_signer",
            "is_exec_relative", "is_finance_dept", "is_mgmt_dept", "is_tech_dept",
            "is_production_dept", "is_marketing_dept", "is_other",
        ),
        "D4-28": (
            "method_business_info", "method_internet", "method_confirmation",
            "method_interview", "method_field_visit",
        ),
    }
    for code, keys in checkbox_columns.items():
        by_key = {s[0]: s for s in CK._SHEETS[code]["fields"]}
        for key in keys:
            assert key in by_key, f"{code}: 勾选列 {key} 不在受管契约里"
            assert by_key[key][3] == "boolean", (
                f"{code}.{key} value_type={by_key[key][3]!r} —— 应为 boolean（勾选=1 口径已接通）"
            )
    # is_duplicate_name 是 Y/N 文本 select，必须保持 text（别被一起改成 boolean）
    dup = {s[0]: s for s in CK._SHEETS["D4-27"]["fields"]}["is_duplicate_name"]
    assert dup[3] == "text", "is_duplicate_name 是 Y/N select，不该改成 boolean"


# ═══════════════════════════════════════════════════════════════════════════
# mapping_digest：列字母/几何漂移的冻结（provider 自带，这里确保它真被断言）
# ═══════════════════════════════════════════════════════════════════════════


def test_all_mapping_digests_match_frozen_values() -> None:
    """四张表的 mapping_digest 与冻结值一致（改列字母/列序/表头即红）。"""
    CK.assert_all_checklist_mapping_digests()


# ═══════════════════════════════════════════════════════════════════════════
# 超模板占位行数：last_data_row 不是运行时截断点（Task C 语义澄清的运行时证据）
#
# 源模板每张表只有固定占位行（D4-25 = 12..21 共 10 行）。用户担心「插到第 11 行会不会
# 被吞 / 顶掉结论区」。store↔projection 层不涉及 xlsx 行几何（footer 下移是 materialize
# 层的事），但它必须先做到「行数超占位也不截断、行身份不丢」—— 否则第 11 行起的数据在
# 进入 materialize 之前就没了。本组把这条钉死：给远超 last_data_row 占位数的行集，
# 投影行数必须精确等于输入行数，且每行身份可回读。
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("code", CK.CHECKLIST_SHEET_CODES)
def test_rows_beyond_template_placeholder_are_not_truncated(code: str, contract: Any) -> None:
    """行数远超模板占位（last_data_row-first_data_row+1）时，投影/merge 都不得截断。"""
    s = CK._SHEETS[code]
    placeholder_rows = s["last_data_row"] - s["first_data_row"] + 1
    n = placeholder_rows + 5  # 蓄意超占位 5 行（如 D4-25 15 行 > 10 占位）
    name_path = _json_paths(code)[1]
    payload = [_row(code, f"row-{i}", **{name_path: f"客户{i}"}) for i in range(n)]

    proj = CK.build_store_projection(code, payload, contract=contract)
    table_key = s["table_key"]
    assert len(proj.row_keys[table_key]) == n, (
        f"{code}: 投影行数 {len(proj.row_keys[table_key])} != 输入 {n} "
        f"—— last_data_row({s['last_data_row']}) 被误当截断点了"
    )

    merged, _a, _v, _t = CK.merge_projection_into_rows(
        code, projection=proj, base_rows=[{"rowId": f"row-{i}"} for i in range(n)]
    )
    assert len(merged) == n, f"{code}: merge 后行数 {len(merged)} != {n}"
    by_id = {r["rowId"]: r for r in merged}
    # 抽查超占位的那 5 行（下标 >= placeholder_rows）身份与值都在
    for i in range(placeholder_rows, n):
        assert by_id[f"row-{i}"][name_path] == f"客户{i}", (
            f"{code}: 超占位第 {i} 行（模板只有 {placeholder_rows} 占位）丢失/串行"
        )
