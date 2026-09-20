# -*- coding: utf-8 -*-
"""D4-9「重要客户结构分析」双区 + totals 守卫的**变异检验**（四态）。

spec: d4-9-customer-structure-bidirectional-writeback · Task 11
Requirements 2.4 / 3.1 / 3.4 / 4.1 / 4.2 / 5.3 / 8.3 · Property 2/3/4/6/10

对生产 sibling provider ``phase5_d4_customer_structure`` 做**内存内（monkeypatch）**变异
（跑完立即恢复，绝不改磁盘源码），每个锚点重跑本脚本内联的守卫断言集合，观察守卫是否打红。
守卫断言与 ``tests/workpaper_sync/test_d4_9_customer_structure_contract.py`` /
``test_d4_9_user_formula_protection.py`` 同源同构，此处内联是为让变异脚本可独立四态自证
（baseline GREEN + 每锚点 RED），不依赖 pytest 收集。

契约经**父模块** phase5_d4_revenue_detail.build_contract_payload() 现算 + parse_contract。

≥5 锚点（design §Testing 要求 ≥4）：
  M1  删 D/F formula_mask —— 令 FORMULA_MASK_CURRENT 去掉 D 列区间：占比列不再受保护
        → 「占比列在 formula_mask 内」守卫红（parse_contract CS-13 直接抛）。
  M2  静态标量改 row 域 —— 令 totals 字段 pointer 带 {row_uuid}（伪装行域）：
        → 「totals row_scoped=False / 无 row_identity」守卫红。
  M3  合并两 table —— 令本期/上期共用同一 table_key：两区投影键前缀塌成一个
        → 「两区 row_keys 不相交」守卫红。
  M4  去 rowId 身份 —— 令 _iter_region_rows 用下标兜底作行身份（丢稳定 rowId）：
        → 「缺 rowId fail-closed」守卫红。
  M5  用户公式 cell 不进保护集合 —— 令 runtime_user_formula_cells 恒返回空：
        → 「用户公式 cell 并入运行时保护区」守卫红。

四态：RED（期望）/ GREEN（守卫缺陷）/ ANCHOR-MISS（provider 漂移）/ BASELINE-FAIL。

用法（从 backend 目录）：
  python scripts/diagnose/mutate_d4_9_customer_structure_guards.py
"""
from __future__ import annotations

import copy
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterator

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import phase5_d4_customer_structure as C  # noqa: E402
from app.services.workpaper_sync import phase5_d4_revenue_detail as D4  # noqa: E402
from app.services.workpaper_sync.contracts import FieldMode, parse_contract  # noqa: E402

SHEET = C.MANAGED_SHEET_D49


def _store(cur_rows, prior_rows, cur_ta=1000, cur_tq=50, pri_ta=500, pri_tq=25):
    return json.dumps({
        "current": {"rows": cur_rows, "totalAmount": cur_ta, "totalQuantity": cur_tq},
        "prior": {"rows": prior_rows, "totalAmount": pri_ta, "totalQuantity": pri_tq},
    })


# ═══════════════════════════════════════════════════════════════════════════
# 守卫断言集合（抛 AssertionError / 异常即「守卫打红」）
# ═══════════════════════════════════════════════════════════════════════════


def guard_contract_parses_with_three_tables() -> None:
    """父契约含 D4-9 sheet 三 table；占比 formula + formula_mask（防 M1/M2）。

    parse_contract 对「formula 字段列不在 formula_mask」直接抛（CS-13），对 totals
    「row_scoped 与 row_identity 不一致」也抛 —— 故本守卫覆盖 M1/M2。
    """
    contract = parse_contract(D4.build_contract_payload(), adapter_id=D4.ADAPTER_ID)
    sheet = {s.sheet_key: s for s in contract.sheets}[C.SHEET_KEY_D49]
    tables = {t.table_key: t for t in sheet.tables}
    assert set(tables) == {
        C.ROWS_TABLE_KEY_CURRENT, C.ROWS_TABLE_KEY_PRIOR, C.TOTALS_TABLE_KEY
    }, f"D4-9 sheet 三 table 异常: {sorted(tables)}"
    # 占比列 formula + 在 mask 内
    for tk in (C.ROWS_TABLE_KEY_CURRENT, C.ROWS_TABLE_KEY_PRIOR):
        ratio = [f for f in tables[tk].fields if f.column_key in ("amount_ratio", "quantity_ratio")]
        assert len(ratio) == 2 and all(f.mode is FieldMode.formula for f in ratio)
    # totals 静态标量：无 row_identity，字段 row_scoped=False
    totals = tables[C.TOTALS_TABLE_KEY]
    assert totals.row_identity is None, "totals 不得有 row_identity"
    assert all(f.row_scoped is False for f in totals.fields), "totals 字段必须 row_scoped=False"


def guard_regions_disjoint() -> None:
    """本期/上期 row_keys 互不相交，键前缀与归属一致（防 M3 合并两 table）。"""
    contract = parse_contract(D4.build_contract_payload(), adapter_id=D4.ADAPTER_ID)
    payload = _store(
        [{"rowId": "c1", "name": "A", "amount": 1}, {"rowId": "c2", "name": "B", "amount": 2}],
        [{"rowId": "p1", "name": "C", "amount": 3}],
    )
    proj = C.build_d49_store_projection(payload, contract=contract)
    cur = set(proj.row_keys.get(C.ROWS_TABLE_KEY_CURRENT, ()))
    pri = set(proj.row_keys.get(C.ROWS_TABLE_KEY_PRIOR, ()))
    assert cur == {"c1", "c2"}, f"本期 row_keys 异常: {sorted(cur)}"
    assert pri == {"p1"}, f"上期 row_keys 异常: {sorted(pri)}"
    assert cur.isdisjoint(pri), f"两区串区: {cur & pri}"


def guard_missing_row_id_fail_closed() -> None:
    """缺行身份必须 fail-closed（StorePayloadError），不得下标兜底（防 M4）。"""
    contract = parse_contract(D4.build_contract_payload(), adapter_id=D4.ADAPTER_ID)
    raised = False
    try:
        C.build_d49_store_projection(_store([{"name": "无身份", "amount": 1}], []), contract=contract)
    except C.StorePayloadError:
        raised = True
    assert raised, "缺 rowId 未 fail-closed —— 行身份退回数组下标兜底"


def guard_user_formula_cell_in_protected_set() -> None:
    """用户公式 cell 必须并入运行时保护集合（防 M5）。"""
    formulas = [SimpleNamespace(
        sheet_name=SHEET, target_cell="C24", expression="=D4-7!D26", formula_source="reference"
    )]
    protected = set(C.runtime_protected_cells(formulas))
    assert "C24" in protected, "用户公式 cell C24 未并入运行时保护集合"
    # 且它不在纯静态 mask 里（证明必须靠用户公式并入才受保护）
    assert "C24" not in set(C.runtime_protected_cells([])), (
        "C24 竟在静态 mask —— 该判据失去意义"
    )


ALL_GUARDS: tuple[Callable[[], None], ...] = (
    guard_contract_parses_with_three_tables,
    guard_regions_disjoint,
    guard_missing_row_id_fail_closed,
    guard_user_formula_cell_in_protected_set,
)


def _run_guards() -> tuple[bool, str]:
    for guard in ALL_GUARDS:
        try:
            guard()
        except AssertionError as exc:
            return False, f"{guard.__name__}: {exc}"
        except Exception as exc:  # noqa: BLE001 —— 变异可能让 provider 抛非断言异常，也算红
            return False, f"{guard.__name__}: {type(exc).__name__}: {exc}"
    return True, ""


# ═══════════════════════════════════════════════════════════════════════════
# 变异（内存内 monkeypatch，跑完 finally 恢复）
# ═══════════════════════════════════════════════════════════════════════════


@contextmanager
def _patch_attr(module: Any, name: str, value: Any) -> Iterator[None]:
    sentinel = object()
    original = getattr(module, name, sentinel)
    setattr(module, name, value)
    try:
        yield
    finally:
        if original is sentinel:
            delattr(module, name)
        else:
            setattr(module, name, original)


def mut_m1_drop_ratio_formula_mask() -> Iterator[None]:
    """M1：删本期 D 列 formula_mask 区间 → 占比 formula 字段列不在 mask（CS-13 抛）。"""
    # 只留 F 与合计，去掉 D13:D22 → D 列占比字段 formula 无 mask 覆盖。
    mutated = tuple(r for r in C.FORMULA_MASK_CURRENT if not r.startswith("D"))
    return _patch_attr(C, "FORMULA_MASK_CURRENT", mutated)


def mut_m2_totals_becomes_row_scoped() -> Iterator[None]:
    """M2：把 totals 字段 pointer 混入 {row_uuid}（非行域字段带行占位 → CS-9 抛）。

    🔴 捕获**原始** totals_table_payload 再包装，避免递归调到 patched 版本。
    """
    original = C.totals_table_payload

    def _bad_totals_payload(*, excel_name: str = SHEET) -> dict:
        base = original(excel_name=excel_name)
        for f in base["fields"]:
            # 非行域字段（row_scoped=False）pointer 含 {row_uuid} → assert_row_scope
            # 抛 ContractSchemaError（CS-9）。cell.row_from 仍是静态行号 → parse 必失败。
            f["json_pointer"] = f"/current/{{row_uuid}}/{f['column_key']}"
        return base
    return _patch_attr(C, "totals_table_payload", _bad_totals_payload)


def mut_m3_merge_two_tables() -> Iterator[None]:
    """M3：上期投影用本期 table_key（两区键前缀塌成一个）。"""
    orig = C.build_d49_prior_projection

    def _prior_as_current(payload, *, contract, limits=None):
        from app.services.workpaper_sync.adapters.base import FieldValue, Projection
        from app.services.workpaper_sync.excel_extract import StreamingProjectionBudget
        from app.services.workpaper_sync.limits import load_limits
        lim = limits or load_limits()
        budget = StreamingProjectionBudget(lim)
        data = C._parse_store_payload(payload)
        # 用 CURRENT table_key 投上期行 → 键前缀塌缩到本期。
        values, row_keys = C._build_region_projection_values(
            data, region_name="prior", table_key=C.ROWS_TABLE_KEY_CURRENT,
            contract=contract, budget=budget,
        )
        return Projection(
            contract_id=contract.contract_id, semantic_version=contract.semantic_version,
            document_type=contract.document_type, values=values,
            row_keys={C.ROWS_TABLE_KEY_CURRENT: tuple(row_keys)},
        )
    return _patch_attr(C, "build_d49_prior_projection", _prior_as_current)


def mut_m4_drop_row_identity() -> Iterator[None]:
    """M4：_iter_region_rows 用下标兜底作行身份（丢稳定 rowId，不再 fail-closed）。"""
    def _positional(region: Any, *, region_name: str):
        if not isinstance(region, dict):
            return
        for ordinal, row in enumerate(region.get("rows") or []):
            rid = str(row.get(C.ROW_IDENTITY_STORE_KEY_D49) or ordinal)  # 下标兜底
            yield rid, row
    return _patch_attr(C, "_iter_region_rows", _positional)


def mut_m5_user_formula_cells_empty() -> Iterator[None]:
    """M5：runtime_user_formula_cells 恒返回空 → 用户公式 cell 不进保护集合。"""
    return _patch_attr(C, "runtime_user_formula_cells", lambda _f: ())


MUTATIONS: tuple[tuple[str, str, Callable[[], Iterator[None]]], ...] = (
    ("M1_drop_ratio_formula_mask", "删 D 列占比 formula_mask（CS-13）", mut_m1_drop_ratio_formula_mask),
    ("M2_totals_row_scoped", "totals 静态标量改行域 pointer", mut_m2_totals_becomes_row_scoped),
    ("M3_merge_two_tables", "上期用本期 table_key（合并两区）", mut_m3_merge_two_tables),
    ("M4_drop_row_identity", "行身份下标兜底（丢 rowId）", mut_m4_drop_row_identity),
    ("M5_user_formula_unprotected", "用户公式 cell 不进保护集合", mut_m5_user_formula_cells_empty),
)


def main() -> int:
    ok, detail = _run_guards()
    if not ok:
        print(json.dumps({"baseline": "BASELINE-FAIL", "detail": detail}, ensure_ascii=False, indent=2))
        return 1

    verdicts: list[dict[str, Any]] = []
    non_red = 0
    for mid, desc, factory in MUTATIONS:
        try:
            with factory():
                passed, detail = _run_guards()
        except Exception as exc:  # noqa: BLE001 —— 建变异本身炸算 anchor-miss
            verdicts.append({"id": mid, "actual": "ANCHOR-MISS", "desc": desc, "detail": f"{type(exc).__name__}: {exc}"})
            non_red += 1
            continue
        if passed:
            verdicts.append({"id": mid, "actual": "GREEN", "desc": desc, "detail": "变异后守卫仍全过 = 守卫缺陷"})
            non_red += 1
        else:
            verdicts.append({"id": mid, "actual": "RED", "desc": desc, "caught_by": detail})

    baseline_after, _ = _run_guards()
    report = {
        "baseline": "GREEN",
        "guards": [g.__name__ for g in ALL_GUARDS],
        "verdicts": verdicts,
        "non_red_count": non_red,
        "baseline_after_restore": "GREEN" if baseline_after else "FAIL",
        "four_state_matrix": {"baseline": "GREEN", **{v["id"]: v["actual"] for v in verdicts}},
        "pass": (
            non_red == 0
            and all(v["actual"] == "RED" for v in verdicts)
            and baseline_after
        ),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
