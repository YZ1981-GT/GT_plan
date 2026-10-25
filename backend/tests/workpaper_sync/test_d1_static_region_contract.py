# -*- coding: utf-8 -*-
"""D1-4 第三区（票据种类小计 R23-24）的**静态受管区**通路 —— 契约 + 投影 + 回写真跑。

spec: d1-sync-row-table-engine-and-d1-coverage · 契约层 `static_tables`（Task 25~29 的前置）

═══ 这条通路为什么必须自带一对投影/回写函数 ═══

`phase5_row_table_sheet.store_row_identity()` 对 `row_identity_key == ""` **直接抛**
`RowTableStorePayloadError("… 声明为无行身份（static_region）—— 不应走行表投影路径")`
⇒ 行表引擎明确拒绝静态 spec，`build_store_projection` / `merge_projection_into_store_rows`
   这条通路对本区走不通。

形态先例取 **D4-33**（固定 12 月行 × 3 业务槽）而非 D4-5 ——
D4-5 的 fixed 表是「每字段一个格」，只证明「同 sheet 动静两 table 可并列」，
**没证明多行静态区怎么表达**。

═══ 为什么不需要独立 binding ═══

`managed_tables_of(contract, binding=…)` 按 `binding.table_key` 找到 sheet 后，把该 sheet 上
**所有**不带 `row_identity` 的 table 作为 `static_tables` 一并返回；而 `plan_managed_writes`
（动态路径）本身就遍历 `static_tables` ⇒ 走已有 `bad_debt_individual_rows` binding 即可。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync import phase5_d1_04_bad_debt as D104  # noqa: E402
from app.services.workpaper_sync import phase5_d1_expansion as EXP  # noqa: E402
from app.services.workpaper_sync import phase5_d1_notes_receivable as P  # noqa: E402
from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402

# 🔴 T7 裁决 A：静态 table 已撤回（`_INCLUDE_D104_NOTETYPE_STATIC=False`）。
#    本文件是「静态 table **在**契约里」时的判据 ⇒ 通路不存在时整体跳过，**不删** ——
#    marker-relative content 字段落地、开关翻回 True 时自动复活。
#    排除态的正向守卫在 `test_d104_static_region_excluded.py`（含失效条目反向检查）。
pytestmark = pytest.mark.skipif(
    not EXP._INCLUDE_D104_NOTETYPE_STATIC,
    reason="T7 裁决 A：D1-4 静态 table 已撤回；排除态守卫见 test_d104_static_region_excluded.py",
)
from app.services.workpaper_sync.excel_extract import (  # noqa: E402
    ExcelIdentityBinding,
    managed_tables_of,
)

TABLE_KEY = "bad_debt_notetype_rows"
ITEM_ID = "D1-bd-notetype-rows"


@pytest.fixture(scope="module")
def contract():
    return parse_contract(P.build_contract_payload(), adapter_id=P.ADAPTER_ID)


def _payload(**overrides) -> str:
    """两条固定行的合成载荷（形态照前端 `serializeNoteTypeRows()` 的 9 个键）。"""
    base = [
        {
            "rowId": "fixed-bank", "noteType": "银行承兑汇票小计", "isFixed": True,
            "priorUnadjusted": 100.0, "priorAje": 1.0, "priorRje": 2.0,
            "currentUnadjusted": 200.0, "currentAje": 3.0, "currentRje": 4.0,
        },
        {
            "rowId": "fixed-commercial", "noteType": "商业承兑汇票小计", "isFixed": True,
            "priorUnadjusted": 50.0, "priorAje": 5.0, "priorRje": 6.0,
            "currentUnadjusted": 80.0, "currentAje": 7.0, "currentRje": 8.0,
        },
    ]
    for row in base:
        row.update(overrides.get(row["rowId"], {}))
    return json.dumps(base, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════════
# 1. 契约层：static_tables 不再为空
# ═══════════════════════════════════════════════════════════════════════════


def test_static_table_is_in_contract_and_classified_static(contract) -> None:
    """🔴 原始断口：契约 `static_tables` 全空 ⇒ 该 item 没有任何 stable field key 可投影。"""
    statics = [t for s in contract.sheets for t in s.tables if not t.has_dynamic_rows]
    assert [t.table_key for t in statics] == [TABLE_KEY], (
        f"静态 table 集合不符：{[t.table_key for t in statics]}"
    )
    t = statics[0]
    assert t.row_identity is None, "静态 table 不得有 row_identity（否则会被判成动态）"
    assert t.has_dynamic_rows is False


def test_static_table_geometry_is_two_fixed_rows_by_nine_columns(contract) -> None:
    t = next(t for s in contract.sheets for t in s.tables if t.table_key == TABLE_KEY)
    rows = sorted({f.cell.static_row for f in t.fields if f.cell})
    cols = sorted({f.cell.column for f in t.fields if f.cell})
    assert rows == [23, 24], f"固定行号不符：{rows}（源模板 R23 银行/R24 商业）"
    assert cols == ["A", "B", "C", "D", "E", "K", "L", "M", "N"], (
        f"列集不符：{cols} —— F~J 应已按「分权拥有」排除"
    )
    assert len(t.fields) == 18, f"field 数应为 2 行 × 9 列 = 18，实得 {len(t.fields)}"
    # 每个字段都必须是绝对行号（不能是动态表的 "row_identity"）
    for f in t.fields:
        assert f.cell is not None and f.cell.static_row in (23, 24), (
            f"{f.stable_field_key} 的 cell 不是绝对行号：{f.cell}"
        )


def test_formula_columns_are_masked(contract) -> None:
    """E/K/N 三列模板有真公式 ⇒ 必须进 mask 受保护。"""
    t = next(t for s in contract.sheets for t in s.tables if t.table_key == TABLE_KEY)
    assert set(t.formula_mask) == {"E23:E24", "K23:K24", "N23:N24"}


def test_stable_keys_use_frontend_row_ids(contract) -> None:
    """🔴 stable key 中段必须是**前端 rowId**，不是序号 —— 否则插删行会错位。"""
    t = next(t for s in contract.sheets for t in s.tables if t.table_key == TABLE_KEY)
    mids = {f.stable_field_key.split("/")[1] for f in t.fields}
    assert mids == {"fixed-bank", "fixed-commercial"}, f"stable key 中段不符：{mids}"
    for f in t.fields:
        assert f.json_pointer.startswith("/rows/fixed-"), (
            f"json_pointer 未按 rowId 定位：{f.json_pointer}"
        )


def test_reachable_via_same_sheet_dynamic_binding(contract) -> None:
    """🔴「不需要独立 binding」的关键断言：同 sheet 的动态 binding 就能取到静态表。"""
    for dyn_key in ("bad_debt_individual_rows", "bad_debt_portfolio_rows"):
        binding = ExcelIdentityBinding(
            table_key=dyn_key, table_name="X", uuid_column="O", metadata_sheet="_GT_SYNC"
        )
        dyn, statics = managed_tables_of(contract, binding=binding)
        assert dyn is not None and dyn.table_key == dyn_key
        assert [t.table_key for t in statics] == [TABLE_KEY], (
            f"binding={dyn_key} 取不到静态表"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 2. 投影 / 回写真跑
# ═══════════════════════════════════════════════════════════════════════════


def test_projection_covers_only_html_owned_editable_columns(contract) -> None:
    """投影只供 HTML 拥有的 6 个可编辑列；E/K/N 不供 ⇒ `_emit` 跳过 ⇒ 模板公式保留。"""
    proj = D104.build_notetype_store_projection(_payload(), contract=contract)
    cols = {k.split("/")[-1] for k in proj.values}
    assert cols == {"item", "prior_unadjusted", "prior_aje", "prior_rje",
                    "current_aje", "current_rje"}, f"投影列集不符：{sorted(cols)}"
    assert len(proj.values) == 12, f"应 2 行 × 6 列 = 12，实得 {len(proj.values)}"
    for c in ("prior_audited", "current_unadjusted", "current_audited"):
        assert not any(k.endswith(f"/{c}") for k in proj.values), (
            f"{c} 是模板公式列，不该出现在投影里（会试图覆盖公式）"
        )


def test_projection_values_come_from_the_right_row(contract) -> None:
    proj = D104.build_notetype_store_projection(_payload(), contract=contract)
    bank = proj.values[D104.notetype_stable_key("fixed-bank", "prior_unadjusted")]
    comm = proj.values[D104.notetype_stable_key("fixed-commercial", "prior_unadjusted")]
    assert bank.value == 100.0 and comm.value == 50.0, "两行的值串了"
    label = proj.values[D104.notetype_stable_key("fixed-bank", "item")]
    assert label.value == "银行承兑汇票小计"


def test_missing_fixed_row_is_skipped_not_zeroed(contract) -> None:
    """🔴 载荷里缺某固定行 ⇒ 该行不投影（Excel 那行保持原值），**不得**投成 0。

    `_emit` 对投影缺键的字段 `return`；若这里改成「补 0 再投」，
    materialize 会把审计师在 OO 侧填的那行清零。
    """
    only_bank = json.dumps(
        [json.loads(_payload())[0]], ensure_ascii=False
    )
    proj = D104.build_notetype_store_projection(only_bank, contract=contract)
    assert all("fixed-commercial" not in k for k in proj.values)
    assert len(proj.values) == 6


def test_extra_custom_row_is_ignored_without_raising(contract) -> None:
    """历史遗留的第三方自定义行：忽略且不报错（Excel 侧零余量、无处安放）。"""
    rows = json.loads(_payload())
    rows.append({"rowId": "nt-legacy", "noteType": "供应链票据小计", "isFixed": False,
                 "priorUnadjusted": 9.0})
    proj = D104.build_notetype_store_projection(
        json.dumps(rows, ensure_ascii=False), contract=contract
    )
    assert all("nt-legacy" not in k for k in proj.values)
    assert len(proj.values) == 12


def test_malformed_payload_fails_closed(contract) -> None:
    with pytest.raises(ValueError, match="必须是行对象数组"):
        D104.build_notetype_store_projection('{"rows": []}', contract=contract)


def test_roundtrip_projection_then_merge_is_value_equal(contract) -> None:
    """🔴 真往返：store → projection → merge → store，6 个可编辑列逐值相等。"""
    raw = _payload()
    proj = D104.build_notetype_store_projection(raw, contract=contract)
    rows, touched, _skipped, protected = D104.merge_projection_into_notetype_rows(
        projection=proj, base_rows=[]
    )
    assert len(rows) == 2
    by_id = {r["rowId"]: r for r in rows}
    src = {r["rowId"]: r for r in json.loads(raw)}
    for row_id in ("fixed-bank", "fixed-commercial"):
        for k in ("noteType", "priorUnadjusted", "priorAje", "priorRje",
                  "currentAje", "currentRje"):
            assert by_id[row_id][k] == src[row_id][k], f"{row_id}.{k} 往返不等值"
    assert touched > 0, "一处都没写 ⇒ merge 是空转"
    assert protected == set(), "投影里没有公式列 ⇒ 不该有受保护键"


def test_merge_creates_missing_fixed_row_with_template_label(contract) -> None:
    """base 为空时必须补出两条固定行（否则 OO 侧首次录入无处落）。"""
    proj = D104.build_notetype_store_projection(_payload(), contract=contract)
    rows, _t, _s, _p = D104.merge_projection_into_notetype_rows(projection=proj, base_rows=[])
    assert [r["rowId"] for r in rows] == ["fixed-bank", "fixed-commercial"]
    assert [r["noteType"] for r in rows] == ["银行承兑汇票小计", "商业承兑汇票小计"]
    assert all(r["isFixed"] is True for r in rows)


def test_merge_preserves_legacy_custom_rows(contract) -> None:
    """不在 `NOTETYPE_FIXED_ROWS` 里的行原样保留 —— 删除归前端，同步层不代为清理。"""
    proj = D104.build_notetype_store_projection(_payload(), contract=contract)
    base = [{"rowId": "nt-legacy", "noteType": "供应链票据小计", "priorUnadjusted": 9.0}]
    rows, _t, _s, _p = D104.merge_projection_into_notetype_rows(
        projection=proj, base_rows=base
    )
    legacy = next(r for r in rows if r["rowId"] == "nt-legacy")
    assert legacy["priorUnadjusted"] == 9.0
    assert legacy["noteType"] == "供应链票据小计"


def test_merge_does_not_let_oo_rename_fixed_rows(contract) -> None:
    """固定行名逐字取自源模板 A23/A24，OO 侧改不掉（前端也标 isFixed 不允许改）。"""
    proj = D104.build_notetype_store_projection(_payload(), contract=contract)
    base = [{"rowId": "fixed-bank", "noteType": "被改过的名字", "isFixed": False}]
    rows, _t, _s, _p = D104.merge_projection_into_notetype_rows(
        projection=proj, base_rows=base
    )
    bank = next(r for r in rows if r["rowId"] == "fixed-bank")
    assert bank["noteType"] == "银行承兑汇票小计"
    assert bank["isFixed"] is True


def test_merge_skips_protected_fields(contract) -> None:
    """受保护字段（公式列）即使出现在投影里也不回写 —— OO 的计算结果不是权威值。"""
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection

    sk = D104.notetype_stable_key("fixed-bank", "current_unadjusted")
    spec = contract.field_by_stable_key(sk)
    proj = Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values={sk: FieldValue(stable_key=sk, value=999.0,
                               value_type=spec.value_type, mode=spec.mode, row_key=None)},
        row_keys={},
    )
    rows, touched, _s, protected = D104.merge_projection_into_notetype_rows(
        projection=proj, base_rows=[{"rowId": "fixed-bank", "currentUnadjusted": 1.0}]
    )
    bank = next(r for r in rows if r["rowId"] == "fixed-bank")
    assert bank["currentUnadjusted"] == 1.0, "受保护字段被回写了"
    assert sk in protected
    assert touched == 0


# ═══════════════════════════════════════════════════════════════════════════
# 3. 编排接线：契约表与投影/回写函数必须成对
# ═══════════════════════════════════════════════════════════════════════════


def test_static_region_contract_and_projection_are_paired() -> None:
    """🔴 契约里有 static table ⇔ 有对应的投影/回写函数（双射）。

    缺前者 ⇒ 投影时 `field_by_stable_key` 抛；缺后者 ⇒ 该区恒空（D4-35 同型断口）。
    """
    tables = EXP.static_region_table_payloads()
    builders = P._static_region_projection_builders()
    handlers = P._static_region_merge_handlers()
    assert len(tables) == len(builders) == len(handlers), (
        f"三者数量不等：table={len(tables)} build={len(builders)} merge={len(handlers)}"
    )
    assert {i for i, _ in builders} == {i for i, _ in handlers} == {ITEM_ID}


def test_combined_projection_includes_static_region(contract) -> None:
    """🔴 整册 combined 投影必须包含静态区 —— 这是 D4-35「恒空」同型断口的守卫。"""
    payloads = {ITEM_ID: _payload()}
    proj = P.build_combined_store_projection(payloads, contract=contract)
    static_keys = [k for k in proj.values if k.startswith(f"{TABLE_KEY}/")]
    assert len(static_keys) == 12, f"combined 投影里静态区只有 {len(static_keys)} 个键"


def test_merge_all_includes_static_region(contract) -> None:
    proj = P.build_combined_store_projection({ITEM_ID: _payload()}, contract=contract)
    out = P.merge_projection_into_all_d1_stores(projection=proj, base_by_item={})
    assert ITEM_ID in out, "回方向整体镜像漏了静态区"
    rows, touched, _s, _p = out[ITEM_ID]
    assert [r["rowId"] for r in rows] == ["fixed-bank", "fixed-commercial"]
    assert touched > 0


def test_no_store_item_without_contract_table_remains() -> None:
    """✅ 原白名单已清空；将来再出现必须显式登记，不得藏在 `continue` 里。"""
    assert P.STORE_ITEM_IDS_WITHOUT_CONTRACT_TABLE == ()


def test_static_item_is_in_all_store_item_ids() -> None:
    assert ITEM_ID in P.all_store_item_ids()
