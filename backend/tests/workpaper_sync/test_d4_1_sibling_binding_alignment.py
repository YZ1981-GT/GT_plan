# -*- coding: utf-8 -*-
"""D4-1 同 sheet 双区 sibling binding 对齐 —— 行为级验证（judge-first）。

spec: d4-1-adjudication-bidirectional-writeback-and-formula-io（D4-1 第二前置）
      · 亦服务 d4-9-customer-structure-bidirectional-writeback
Requirements（主控 §5.3 shared-lock）：ADD/GENERALIZE 对齐逻辑，不回归多 sheet / 单 sheet。

背景（已核实的 ROOT CAUSE）：
`projection_first_publication._sibling_identity_bindings`（publish）与
`phase5_d4_revenue_detail._attach_sibling_bindings`（attach）原来都用
`zip(specs[1:], sheets[1:])` 位置配对，并以 `len(sheets) != len(specs)` 计数守卫，
隐含「1 spec ↔ 1 sheet」。D4-1 是**同一张受管 sheet**（`d41-managed`）里两个
row table（主营 UUID 列 W / 其他 UUID 列 X），`instrumentation_spec_d41()` 返回
**2 个 spec 共享同一 managed_sheet**。位置 zip + 计数守卫双双失效
（spec 数 > sheet 数、且一张 sheet 要映到两个 spec）。

修复（共享内核 `_align_specs_to_sibling_tables`）：把 spec 对齐到**行 table**（按
managed sheet 归组、同 sheet 双区靠 UUID 列一一配对），计数守卫改为
「行 table 总数 == spec 数」。

本文件锁死三条判据：
1. 同 sheet 双区对齐：D4-1 两 spec → 两条不同 sibling binding（UUID 列 W/X、
   table_key main/other），primary（D4-2 revenue_detail_rows）不在其列；
   publish 与 attach 两路径行为一致。
2. 变异守卫：把对齐逻辑改回位置 `zip`/`len(sheets)!=len(specs)` → 双区测试必红
   （抛 ProviderCapabilityError 或把两 spec 映到同一张 table）。
3. 无回归：既有多 sheet entry（每 sheet 1 张行 table）经泛化后产出的 sibling
   binding 与「1 sheet 1 spec」语义一致（table 归组 == sheet 归组）。
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

from app.services.workpaper_sync import phase5_d4_revenue_detail as D4  # noqa: E402
from app.services.workpaper_sync import projection_first_publication as PFP  # noqa: E402
from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402

# ── 从 provider 冻结常量派生的期望（D4-1 双区 + D4-2 primary） ──────────────────
D41_SHEET_KEY = "d41-managed"
D41_TABLE_MAIN = "adjudication_main_rows"
D41_TABLE_OTHER = "adjudication_other_rows"
D41_UUID_MAIN = "W"
D41_UUID_OTHER = "X"
D42_PRIMARY_TABLE_KEY = D4.ROWS_TABLE_KEY  # "revenue_detail_rows"


class _PrimaryStub:
    """`_sibling_identity_bindings` / helper 只读 primary.table_key。"""

    def __init__(self, table_key: str) -> None:
        self.table_key = table_key


class _StagedStub:
    """`_sibling_identity_bindings` 只读 staged.observed_dynamic_bindings。"""

    observed_dynamic_bindings: dict[str, Any] = {}


def _contract() -> Any:
    return parse_contract(D4.build_contract_payload(), adapter_id=D4.ADAPTER_ID)


def _primary() -> _PrimaryStub:
    return _PrimaryStub(D42_PRIMARY_TABLE_KEY)


# ═══════════════════════════════════════════════════════════════════════════
# 前置：D4-1 两 spec 已 live（flag 已 flip），且计数与行 table 总数 reconcile
# ═══════════════════════════════════════════════════════════════════════════


def test_d41_two_specs_are_live_in_instrumentation_specs() -> None:
    """`_INCLUDE_D41_ADJUDICATION_INSTRUMENTATION=True` 后 D4-1 两 spec 进入 specs()。"""
    specs = tuple(D4.instrumentation_specs())
    d41_specs = [
        s for s in specs if getattr(s, "managed_sheet", None) == D4.MANAGED_SHEET_D41
    ]
    assert len(d41_specs) == 2, (
        f"D4-1 两 spec 未 live（实得 {len(d41_specs)}）—— flag 未 flip 或 specs 拼装漏接"
    )
    uuid_cols = {str(s.uuid_col) for s in d41_specs}
    assert uuid_cols == {D41_UUID_MAIN, D41_UUID_OTHER}, (
        f"D4-1 两 spec 的 UUID 列应为 {{W, X}}，实得 {uuid_cols}"
    )


def test_specs_count_reconciles_with_total_row_tables() -> None:
    """新计数守卫：row_oriented_sheets 的行 table 总数 == len(specs)（数 table 不数 sheet）。"""
    from app.services.workpaper_sync.phase5_d4_29_customer_detail import (
        row_oriented_sheets,
    )

    contract = _contract()
    specs = tuple(D4.instrumentation_specs())
    total_row_tables = sum(
        len([t for t in sheet.tables if t.row_identity is not None])
        for sheet in row_oriented_sheets(contract)
    )
    assert total_row_tables == len(specs), (
        f"行 table 总数 ({total_row_tables}) 与 spec 数 ({len(specs)}) 不 reconcile —— "
        "计数守卫应会 fail-closed"
    )
    # 且真的不会抛（对齐成功）。
    pairs = PFP._align_specs_to_sibling_tables(
        provider=D4, contract=contract, primary=_primary()
    )
    assert pairs, "对齐结果为空 —— sibling 应至少覆盖 D4-1 两区 + 其它多 sheet"


# ═══════════════════════════════════════════════════════════════════════════
# 判据 1：同 sheet 双区对齐 —— D4-1 两 spec → 两条不同 sibling binding
# ═══════════════════════════════════════════════════════════════════════════


def _d41_siblings(bindings: tuple[Any, ...]) -> list[Any]:
    return [
        b
        for b in bindings
        if str(b.table_key) in (D41_TABLE_MAIN, D41_TABLE_OTHER)
    ]


def test_publish_path_yields_two_distinct_d41_sibling_bindings() -> None:
    """publish 路径 `_sibling_identity_bindings`：D4-1 两区各一条，UUID/table_key 各异。"""
    bindings = PFP._sibling_identity_bindings(
        provider=D4,
        staged=_StagedStub(),
        contract=_contract(),
        primary=_primary(),
    )
    d41 = _d41_siblings(bindings)
    assert len(d41) == 2, (
        f"D4-1 同 sheet 双区应产出 2 条 sibling binding，实得 {len(d41)}: "
        f"{[b.table_key for b in d41]}"
    )
    by_table = {str(b.table_key): b for b in d41}
    assert set(by_table) == {D41_TABLE_MAIN, D41_TABLE_OTHER}, (
        f"两条 binding 的 table_key 必须是 main/other，实得 {set(by_table)}"
    )
    # UUID 列必须与 spec 侧一一对应（不串区）。
    assert str(by_table[D41_TABLE_MAIN].uuid_column) == D41_UUID_MAIN
    assert str(by_table[D41_TABLE_OTHER].uuid_column) == D41_UUID_OTHER
    # UUID 列互不相同（否则同 sheet 双区身份串区）。
    assert (
        by_table[D41_TABLE_MAIN].uuid_column != by_table[D41_TABLE_OTHER].uuid_column
    )
    # primary（D4-2 revenue_detail_rows）绝不出现在 sibling 里。
    assert all(str(b.table_key) != D42_PRIMARY_TABLE_KEY for b in bindings)


def test_attach_path_matches_publish_path_for_d41() -> None:
    """attach 路径 `_attach_sibling_bindings` 与 publish 同规则：D4-1 两区也各一条。"""
    contract = _contract()
    bindings = D4._attach_sibling_bindings(
        primary=_primary(), contract=contract, dynamic_bindings={}
    )
    d41 = _d41_siblings(bindings)
    assert len(d41) == 2, (
        f"attach 路径 D4-1 双区应产出 2 条 sibling binding，实得 {len(d41)}: "
        f"{[b.table_key for b in d41]}"
    )
    by_table = {str(b.table_key): b for b in d41}
    assert set(by_table) == {D41_TABLE_MAIN, D41_TABLE_OTHER}
    assert str(by_table[D41_TABLE_MAIN].uuid_column) == D41_UUID_MAIN
    assert str(by_table[D41_TABLE_OTHER].uuid_column) == D41_UUID_OTHER


# ═══════════════════════════════════════════════════════════════════════════
# 判据 3：无回归 —— 多 sheet entry（每 sheet 1 张行 table）仍正确对齐
# ═══════════════════════════════════════════════════════════════════════════


def test_multi_sheet_single_table_bindings_still_produced() -> None:
    """既有多 sheet entry（D4-3 等，每 sheet 1 张行 table）仍产出各自 sibling binding。

    泛化后 tables-per-sheet==1 时 table 归组 == sheet 归组：这些 binding 的
    table_key 集合必须包含 D4-3 的行表 key（未被丢、未串区）。
    """
    bindings = PFP._sibling_identity_bindings(
        provider=D4,
        staged=_StagedStub(),
        contract=_contract(),
        primary=_primary(),
    )
    table_keys = {str(b.table_key) for b in bindings}
    # D4-3「其他业务收入」是最经典的多 sheet sibling（每 sheet 1 表）。
    assert D4.ROWS_TABLE_KEY_D43 in table_keys, (
        f"D4-3 sibling binding 丢失 —— 泛化回归了多 sheet 路径；实得 {sorted(table_keys)}"
    )
    # 每个 sibling binding 的 table_key 唯一（无 table 被双映）。
    all_keys = [str(b.table_key) for b in bindings]
    assert len(all_keys) == len(set(all_keys)), (
        f"sibling binding 出现重复 table_key（双映）: {all_keys}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 判据 2：变异守卫 —— 改回位置 zip / len(sheets)!=len(specs) 必红
# ═══════════════════════════════════════════════════════════════════════════


def test_reverting_to_positional_zip_breaks_dual_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """把对齐逻辑换回缺陷版（位置 zip + 计数守卫数 sheet），D4-1 双区必红。

    缺陷版对 D4-1：specs 数 > sheets 数（同 sheet 双区），旧 `len(sheets)!=len(specs)`
    直接抛 ProviderCapabilityError；即便绕过，位置 zip 也无法把两 spec 映到同一
    sheet 的两张 table。这条证明判据 1 不是空转。
    """
    from app.services.workpaper_sync.phase5_d4_29_customer_detail import (
        row_oriented_sheets,
    )

    def _broken_align(*, provider: Any, contract: Any, primary: Any) -> list:
        specs = tuple(provider.instrumentation_specs())
        if len(specs) <= 1:
            return []
        sheets = row_oriented_sheets(contract)
        # 缺陷版计数守卫：数 sheet 不数 table。
        if len(sheets) != len(specs):
            raise PFP.ProviderCapabilityError(
                "位置 zip 缺陷版：spec 数与 sheet 数不一致"
            )
        pairs = []
        for spec, sheet in zip(specs[1:], sheets[1:]):
            dynamic = next(
                (t for t in sheet.tables if t.row_identity is not None), None
            )
            if dynamic is None:
                continue
            if str(dynamic.table_key) == str(primary.table_key):
                continue
            pairs.append((spec, dynamic))
        return pairs

    monkeypatch.setattr(PFP, "_align_specs_to_sibling_tables", _broken_align)

    contract = _contract()
    with pytest.raises(PFP.ProviderCapabilityError):
        PFP._sibling_identity_bindings(
            provider=D4,
            staged=_StagedStub(),
            contract=contract,
            primary=_primary(),
        )
