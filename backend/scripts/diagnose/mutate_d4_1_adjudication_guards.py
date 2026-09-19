# -*- coding: utf-8 -*-
"""D4-1「营业收入审定表」双区 store 守卫的**变异检验**（四态）。

spec: d4-1-adjudication-bidirectional-writeback-and-formula-io · Task 9
Requirements 5.1 / 5.3 / 5.4 · Property 3（双区动态行往返一致 + 两区不串 + formula_mask 不回写）

对生产 provider ``phase5_d4_adjudication_sheet`` 做**内存内（monkeypatch）**变异（跑完立即
恢复，绝不改磁盘源码），每个锚点重跑本脚本内联的守卫断言集合，观察守卫是否打红。守卫断言
与 ``tests/workpaper_sync/test_d4_1_adjudication_store_roundtrip.py`` 同源同构（两区往返逐格
一致 / 两区 rowId 各自唯一不串 / formula_mask 不回写 / 缺码 fail-closed），此处内联是为了让
变异脚本可独立四态自证（baseline GREEN + 每个锚点 RED），不依赖 pytest 收集。

≥4 锚点（各是一处 distinct 变异，必把守卫打红）：
  M1  改区 anchor/UUID —— 令两区共用同一 table_key（``ROWS_TABLE_KEY_OTHER`` = MAIN）：
        两区投影键前缀塌成一个 → 「两区 row_keys 不相交」守卫红。
  M2  formula_mask 可回写 —— 往 ``_COLUMN_KEY_TO_STORE_KEY`` 注入审定数派生列映射
        （``current_audited`` → ``currentAudited``）：注入的 formula_mask 键会被 merge 回写
        → 「formula_mask 不回写」守卫红。
  M3  合并两区 —— 令 ``_table_key_for_section`` 无视 sectionKey 恒归主营：其他区行全被吸进
        主营区 → 「按 table_key 分区不串」守卫红。
  M4  去 rowId 身份 —— 令 ``_iter_store_rows`` 用数组下标兜底作行身份（丢稳定 rowId）：
        缺 rowId 的行不再 fail-closed → 「缺行身份 fail-closed」守卫红。

四态：
  RED         —— 变异后守卫抛断言（**期望态**）。
  GREEN       —— 变异后守卫仍全过 = **守卫缺陷**（vacuous guard），脚本判 fail。
  ANCHOR-MISS —— 变异锚点在真实 provider 里对不上（provider 漂移，脚本需更新）。
  BASELINE-FAIL —— 未变异时守卫就红（守卫本身坏了）。

用法（从 backend 目录）：
  python scripts/diagnose/mutate_d4_1_adjudication_guards.py
"""
from __future__ import annotations

import copy
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2]  # backend/
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import phase5_d4_adjudication_sheet as A  # noqa: E402
from app.services.workpaper_sync import phase5_d4_revenue_detail as D4  # noqa: E402
from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402

_AMOUNT_KEYS = (
    "currentUnadjusted", "currentAje", "currentRje",
    "priorUnadjusted", "priorAje", "priorRje",
)


def _row(rid: str, section: str, label: str, base: float) -> dict[str, Any]:
    return {
        A.ROW_IDENTITY_STORE_KEY_D41: rid,
        "label": label,
        A.SECTION_KEY_FIELD: section,
        "currentUnadjusted": base + 0.5, "currentAje": base + 1.0, "currentRje": -(base + 2.0),
        "priorUnadjusted": base + 3.0, "priorAje": base + 4.0, "priorRje": -(base + 5.0),
    }


def _empty_base(rid: str, section: str) -> dict[str, Any]:
    row: dict[str, Any] = {A.ROW_IDENTITY_STORE_KEY_D41: rid, "label": "", A.SECTION_KEY_FIELD: section}
    for key in _AMOUNT_KEYS:
        row[key] = 0
    return row


# ═══════════════════════════════════════════════════════════════════════════
# 守卫断言集合（与 roundtrip 测试同源）—— 抛 AssertionError 即「守卫打红」
# ═══════════════════════════════════════════════════════════════════════════


def _contract() -> Any:
    return parse_contract(D4.build_contract_payload(), adapter_id=D4.ADAPTER_ID)


def guard_regions_disjoint(contract: Any) -> None:
    """两区 row_keys 互不相交，且键前缀与 rowId 归属一致（防 M1 串区）。"""
    rows = [
        _row("m-1", A.SECTION_KEY_MAIN, "批发", 1.0),
        _row("m-2", A.SECTION_KEY_MAIN, "零售", 2.0),
        _row("o-1", A.SECTION_KEY_OTHER, "物流", 3.0),
    ]
    proj = A.build_store_projection_d41(rows, contract=contract)
    main_ids = set(proj.row_keys.get(A.ROWS_TABLE_KEY_MAIN, ()))
    other_ids = set(proj.row_keys.get(A.ROWS_TABLE_KEY_OTHER, ()))
    assert main_ids == {"m-1", "m-2"}, f"主营区 row_keys 异常: {sorted(main_ids)}"
    assert other_ids == {"o-1"}, f"其他区 row_keys 异常: {sorted(other_ids)}"
    assert main_ids.isdisjoint(other_ids), f"两区 rowId 串区: {main_ids & other_ids}"
    # 两区键前缀必须分别落各自 rowId 集合。
    for key in proj.stable_keys():
        sk = str(key)
        rid = sk.rsplit("/", 1)[0].split("/", 1)[1]
        if sk.startswith(A.ROWS_TABLE_KEY_MAIN + "/"):
            assert rid in main_ids, f"主营区键带非主营 rowId: {sk}"
        elif sk.startswith(A.ROWS_TABLE_KEY_OTHER + "/"):
            assert rid in other_ids, f"其他区键带非其他 rowId: {sk}"
        else:
            raise AssertionError(f"投影键前缀非两区之一: {sk}")


def guard_formula_mask_not_written_back(contract: Any) -> None:
    """注入 formula_mask 审定数派生列键，merge 必须不回写进 store 行（防 M2）。"""
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection
    from app.services.workpaper_sync.contracts import FieldMode, ValueType

    rows = [_row("m-1", A.SECTION_KEY_MAIN, "批发", 1.0)]
    proj = A.build_store_projection_d41(rows, contract=contract)
    values = dict(proj.values)
    bad_key = f"{A.ROWS_TABLE_KEY_MAIN}/m-1/current_audited"
    values[bad_key] = FieldValue(
        stable_key=bad_key, value=999999.0, value_type=ValueType.amount,
        mode=FieldMode.editable, row_key="m-1",
    )
    tampered = Projection(
        contract_id=proj.contract_id, semantic_version=proj.semantic_version,
        document_type=proj.document_type, values=values, row_keys=proj.row_keys,
    )
    merged, _a, _v, _t = A.merge_projection_into_d41_rows(
        projection=tampered, base_rows=[_empty_base("m-1", A.SECTION_KEY_MAIN)]
    )
    out = merged[0]
    assert "current_audited" not in out and "currentAudited" not in out, (
        f"formula_mask 派生列被回写进 store 行: {out}"
    )


def guard_merge_routes_by_table_key(contract: Any) -> None:
    """merge 按 table_key 权威回填 sectionKey，两区不串（防 M3 合并两区）。"""
    rows = [
        _row("m-1", A.SECTION_KEY_MAIN, "批发", 10.0),
        _row("o-1", A.SECTION_KEY_OTHER, "物流", 20.0),
    ]
    proj = A.build_store_projection_d41(rows, contract=contract)
    base = [_empty_base("m-1", A.SECTION_KEY_MAIN), _empty_base("o-1", A.SECTION_KEY_OTHER)]
    merged, _a, _v, _t = A.merge_projection_into_d41_rows(projection=proj, base_rows=base)
    by_id = {r[A.ROW_IDENTITY_STORE_KEY_D41]: r for r in merged}
    assert set(by_id) == {"m-1", "o-1"}, f"merge 行集合异常: {sorted(by_id)}"
    assert by_id["m-1"][A.SECTION_KEY_FIELD] == A.SECTION_KEY_MAIN, "主营行串到其他区"
    assert by_id["o-1"][A.SECTION_KEY_FIELD] == A.SECTION_KEY_OTHER, "其他行串到主营区"
    # 其他区必须真有键被投影（合并两区后其他区键消失 → row_keys 空）。
    assert proj.row_keys.get(A.ROWS_TABLE_KEY_OTHER), "其他区 row_keys 为空 —— 两区被合并"


def guard_missing_row_id_fail_closed(contract: Any) -> None:
    """缺行身份必须 fail-closed（ValueError），不得下标兜底（防 M4 去 rowId）。"""
    raised = False
    try:
        A.build_store_projection_d41(
            [{"label": "无身份", A.SECTION_KEY_FIELD: A.SECTION_KEY_MAIN}],
            contract=contract,
        )
    except ValueError:
        raised = True
    assert raised, "缺行身份未 fail-closed —— 行身份退回数组下标兜底"


ALL_GUARDS: tuple[Callable[[Any], None], ...] = (
    guard_regions_disjoint,
    guard_formula_mask_not_written_back,
    guard_merge_routes_by_table_key,
    guard_missing_row_id_fail_closed,
)


def _run_guards() -> tuple[bool, str]:
    """跑全部守卫；全过 → (True, '')，任一红 → (False, 首个失败摘要)。"""
    contract = _contract()
    for guard in ALL_GUARDS:
        try:
            guard(contract)
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


@contextmanager
def _patch_dict(target: dict, mutate: Callable[[dict], None]) -> Iterator[None]:
    original = copy.deepcopy(target)
    mutate(target)
    try:
        yield
    finally:
        target.clear()
        target.update(original)


def mut_m1_same_uuid_region() -> Iterator[None]:
    """M1：两区共用同一 table_key（区身份/UUID 塌缩）。"""
    # _SECTION_TO_TABLE 与 _table_key_for_section 都引用 ROWS_TABLE_KEY_OTHER；
    # 直接把 section→table 映射的其他区指向主营 table_key。
    def _mutate(d: dict) -> None:
        d[A.SECTION_KEY_OTHER] = A.ROWS_TABLE_KEY_MAIN
    return _patch_dict(A._SECTION_TO_TABLE, _mutate)


def mut_m2_formula_mask_writable() -> Iterator[None]:
    """M2：把审定数派生列加入受管列映射 → formula_mask 键可被回写。"""
    def _mutate(d: dict) -> None:
        d["current_audited"] = "currentAudited"
    return _patch_dict(A._COLUMN_KEY_TO_STORE_KEY, _mutate)


def mut_m3_merge_two_regions() -> Iterator[None]:
    """M3：sectionKey 分流失效，两区合并（恒归主营）。"""
    return _patch_attr(A, "_table_key_for_section", lambda _section: A.ROWS_TABLE_KEY_MAIN)


def mut_m4_drop_row_identity() -> Iterator[None]:
    """M4：行身份用数组下标兜底（丢稳定 rowId，不再 fail-closed）。"""
    def _positional_iter(payload: Any):
        rows = payload
        if isinstance(rows, (str, bytes, bytearray)):
            text = rows.decode("utf-8") if isinstance(rows, (bytes, bytearray)) else rows
            rows = json.loads(text or "[]")
        if isinstance(rows, dict):
            rows = rows.get("rows", [])
        for ordinal, row in enumerate(rows or []):
            rid = str(row.get(A.ROW_IDENTITY_STORE_KEY_D41) or ordinal)  # 下标兜底
            yield rid, row
    return _patch_attr(A, "_iter_store_rows", _positional_iter)


MUTATIONS: tuple[tuple[str, str, Callable[[], Iterator[None]]], ...] = (
    ("M1_same_uuid_region", "两区共用同一 table_key（区身份塌缩）", mut_m1_same_uuid_region),
    ("M2_formula_mask_writable", "审定数派生列进受管映射（formula_mask 可回写）", mut_m2_formula_mask_writable),
    ("M3_merge_two_regions", "sectionKey 分流失效（两区合并归主营）", mut_m3_merge_two_regions),
    ("M4_drop_row_identity", "行身份下标兜底（丢稳定 rowId）", mut_m4_drop_row_identity),
)


def main() -> int:
    # 基线：未变异守卫必须全绿。
    ok, detail = _run_guards()
    if not ok:
        print(json.dumps({"baseline": "BASELINE-FAIL", "detail": detail}, ensure_ascii=False, indent=2))
        return 1

    verdicts: list[dict[str, Any]] = []
    non_red = 0
    for mid, desc, factory in MUTATIONS:
        cm = factory()
        try:
            with cm:
                passed, detail = _run_guards()
        except Exception as exc:  # noqa: BLE001 —— 建变异本身炸也算 anchor-miss
            verdicts.append({"id": mid, "actual": "ANCHOR-MISS", "desc": desc, "detail": f"{type(exc).__name__}: {exc}"})
            non_red += 1
            continue
        if passed:
            verdicts.append({"id": mid, "actual": "GREEN", "desc": desc, "detail": "变异后守卫仍全过 = 守卫缺陷"})
            non_red += 1
        else:
            verdicts.append({"id": mid, "actual": "RED", "desc": desc, "caught_by": detail})

    # 恢复自检：确认关键映射已还原。
    restored_ok = (
        A._SECTION_TO_TABLE.get(A.SECTION_KEY_OTHER) == A.ROWS_TABLE_KEY_OTHER
        and "current_audited" not in A._COLUMN_KEY_TO_STORE_KEY
        and A._table_key_for_section(A.SECTION_KEY_OTHER) == A.ROWS_TABLE_KEY_OTHER
    )
    baseline_after, _ = _run_guards()

    report = {
        "baseline": "GREEN",
        "guards": [g.__name__ for g in ALL_GUARDS],
        "verdicts": verdicts,
        "non_red_count": non_red,
        "restored_ok": restored_ok,
        "baseline_after_restore": "GREEN" if baseline_after else "FAIL",
        "four_state_matrix": {
            "baseline": "GREEN",
            **{v["id"]: v["actual"] for v in verdicts},
        },
        "pass": (
            non_red == 0
            and all(v["actual"] == "RED" for v in verdicts)
            and restored_ok
            and baseline_after
        ),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
