# -*- coding: utf-8 -*-
"""D4-12「合同检查表」转置双向回写守卫的**变异检验**（四态）。

spec: d4-12-transposed-writeback · Task 12 · Requirement 6.3 · Property 1/2/3/7

对生产 provider / 注册表 / 泛化引擎做**内存内（monkeypatch）**变异（跑完立即恢复，绝不改
磁盘源码），每锚点重跑本脚本内联的守卫断言集合，观察守卫是否打红。守卫与
tests/workpaper_sync/test_d4_12_contract.py / test_d4_12_transposed_roundtrip.py 同源同构，
此处内联使变异脚本可独立四态自证（baseline GREEN + 每锚点 RED），不依赖 pytest 收集。

**每条变异后 D4-29 回归须保持绿**（证明泛化不牵连蓝本，design 变异 1-4 要求）。

≥4 锚点（design §Testing 要求 ≥4）：
  M1  泛化改回 D4-29 单例 —— REGISTRY 只认 SPEC_D429 → resolve 对 d4-12 契约不命中
        → 「resolve_transposed_specs 命中 d4-12」守卫红；D4-29 回归仍绿。
  M2  first_entity_column 改回 C —— SPEC_D412.first_entity_column='C'
        → 「materialize 写 B 列起 / 往返闭合」守卫红；D4-29 回归仍绿。
  M3  去 identity carrier hidden 强校验 —— extract 不校验载体行 hidden
        → 「载体行未 hidden 应 fail-closed」守卫红；D4-29 回归仍绿。
  M4  契约去 d4-12-managed —— provider flag 关
        → 「live 契约含 d4-12-managed」守卫红；D4-29 回归仍绿。

四态：RED（期望）/ GREEN（守卫缺陷）/ ANCHOR-MISS（provider 漂移）/ BASELINE-FAIL。

用法（从 backend 目录）：
  python scripts/diagnose/mutate_d4_12_transposed_guards.py
"""
from __future__ import annotations

import dataclasses
import io
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from openpyxl import load_workbook  # noqa: E402
from openpyxl.utils import column_index_from_string  # noqa: E402

from app.services.workpaper_sync import phase5_d4_12_contract as D12  # noqa: E402
from app.services.workpaper_sync import phase5_d4_29_customer_detail as D29  # noqa: E402
from app.services.workpaper_sync import phase5_d4_revenue_detail as D4  # noqa: E402
from app.services.workpaper_sync import phase5_transposed_sheet as ENG  # noqa: E402
from app.services.workpaper_sync import transposed_registry as REG  # noqa: E402
from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402
from app.services.workpaper_sync.excel_instrumentation import instrument_workbook_bytes_multi  # noqa: E402


def _instrumented_template() -> bytes:
    """注入了 D4-12 转置锚点 + 隐藏载体行的合并模板（flag on 后 provider 已含）。"""
    return instrument_workbook_bytes_multi(
        D4.read_authoritative_template(), D4.instrumentation_specs(), gate=D4.excel_carrier_gate()
    ).instrumented_bytes


def _contracts(count=2):
    out = []
    for i in range(count):
        item = {"id": f"c-{i}", "indexNo": f"D4-12-{i + 1}", "label": f"合同{i}"}
        for k in D12.FIELD_KEYS:
            item[k] = 100 + i if k == "contractAmount" else f"{k}-{i}"
        out.append(item)
    return out


def _d29_customers(count=2):
    return [{"id": f"id{i}", "name": f"客户{i}", "fields": {k: f"{k}-{i}" for k in D29.FIELD_KEYS}}
            for i in range(count)]


# ═══════════════════════════════════════════════════════════════════════════
# 守卫断言集合（抛即「守卫打红」）
# ═══════════════════════════════════════════════════════════════════════════


def guard_registry_resolves_d412() -> None:
    """resolve_transposed_specs 对含 d4-12-managed 的契约命中 SPEC_D412（防 M1）。"""
    contract = parse_contract(D4.build_contract_payload())
    specs = REG.resolve_transposed_specs(contract)
    keys = {s.sheet_key for s in specs}
    assert "d4-12-managed" in keys, f"resolve 未命中 d4-12-managed: {sorted(keys)}"


def guard_materialize_writes_first_column_B() -> None:
    """materialize 首实体列写 B（非 A/C）且 21 字段往返闭合（防 M2）。"""
    tpl = _instrumented_template()
    payload = _contracts(2)
    data = D12.materialize_transposed_workbook(tpl, payload)
    ws = load_workbook(io.BytesIO(data))[D12.MANAGED_SHEET]
    b = column_index_from_string("B")
    assert ws.cell(D12.IDENTITY_CARRIER_ROW, b).value == "GT-CONTRACT-c-0", "首合同未写 B 列载体"
    assert ws.cell(11, b).value == "contractNo-0", "首合同字段未写 B 列"
    # A 列标签不被覆盖
    assert ws["A11"].value == "合同编号", "A 标签列被业务值覆盖"
    # 往返闭合
    got = D12.extract_transposed_workbook(data)
    assert len(got) == 2 and got[0]["contractNo"] == "contractNo-0", "21 字段往返漂移"


def guard_carrier_hidden_fail_closed() -> None:
    """载体行未 hidden 时 extract 必须 fail-closed（防 M3）。"""
    tpl = _instrumented_template()
    data = D12.materialize_transposed_workbook(tpl, _contracts(1))
    wb = load_workbook(io.BytesIO(data))
    wb[D12.MANAGED_SHEET].row_dimensions[D12.IDENTITY_CARRIER_ROW].hidden = False
    buf = io.BytesIO()
    wb.save(buf)
    raised = False
    try:
        D12.extract_transposed_workbook(buf.getvalue())
    except ValueError:
        raised = True
    assert raised, "载体行未 hidden 竟未 fail-closed"


def guard_live_contract_has_d412() -> None:
    """flag on → live 契约含 d4-12-managed（防 M4）。"""
    contract = parse_contract(D4.build_contract_payload())
    keys = {s.sheet_key for s in contract.sheets}
    assert "d4-12-managed" in keys, "live 契约缺 d4-12-managed"


ALL_GUARDS: tuple[Callable[[], None], ...] = (
    guard_registry_resolves_d412,
    guard_materialize_writes_first_column_B,
    guard_carrier_hidden_fail_closed,
    guard_live_contract_has_d412,
)


def guard_d429_regression() -> None:
    """D4-29 蓝本零回归：materialize→extract 逐字段 + mapping_digest 冻结（每条变异后须绿）。"""
    tpl = _instrumented_template()
    payload = _d29_customers(3)
    data = D29.materialize_transposed_workbook(tpl, payload)
    assert D29.extract_transposed_workbook(data) == payload, "D4-29 往返漂移"
    assert D29.compute_mapping_digest() == D29.EXPECTED_MAPPING_DIGEST, "D4-29 mapping_digest 漂移"


def _run(guards) -> tuple[bool, str]:
    """早退版：任一守卫红即返回（baseline / D4-29 回归用，要求全绿）。"""
    for guard in guards:
        try:
            guard()
        except AssertionError as exc:
            return False, f"{guard.__name__}: {exc}"
        except Exception as exc:  # noqa: BLE001
            return False, f"{guard.__name__}: {type(exc).__name__}: {exc}"
    return True, ""


def _run_collect(guards) -> dict[str, str]:
    """全跑版：返回 {守卫名: 失败原因}（变异下用，核对「哪些守卫红」以明确职责）。

    不早退——一个变异可能同时触发多个守卫（如 first_col 改 C 既让 materialize 写错列、
    又让 mapping_digest 漂移）。收集全部红守卫，验证「对应职责守卫」确实在其中。
    """
    failed: dict[str, str] = {}
    for guard in guards:
        try:
            guard()
        except AssertionError as exc:
            failed[guard.__name__] = str(exc)
        except Exception as exc:  # noqa: BLE001
            failed[guard.__name__] = f"{type(exc).__name__}: {exc}"
    return failed


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


def mut_m1_registry_only_d429() -> Iterator[None]:
    """M1：REGISTRY 只认 D4-29 → resolve 对 d4-12 契约不命中。"""
    return _patch_attr(REG, "REGISTRY", (D29.SPEC_D429,))


def mut_m2_first_column_C() -> Iterator[None]:
    """M2：SPEC_D412.first_entity_column 改回 C → 写列错位/往返漂移。"""
    mutated = dataclasses.replace(D12.SPEC_D412, first_entity_column="C")
    return _patch_attr(D12, "SPEC_D412", mutated)


def mut_m3_extract_skips_hidden_check() -> Iterator[None]:
    """M3：extract 不校验载体行 hidden（去强校验）。"""
    def _lax_extract(workbook_bytes, *, sheet_name=D12.MANAGED_SHEET):
        # 复刻 provider.extract_transposed_workbook 但用一个跳过 hidden 校验的 spec 语义：
        # 直接调通用引擎但先把 sheet 的 hidden 判定绕过 —— 通过 monkeypatch 引擎的 resolve
        # 太深，改为在此处用「先强制置 hidden=True 再 extract」模拟校验缺失（永不 fail）。
        wb, ws = ENG.resolve_managed_sheet(workbook_bytes, spec=D12.SPEC_D412)
        ws.row_dimensions[D12.IDENTITY_CARRIER_ROW].hidden = True
        buf = io.BytesIO()
        wb.save(buf)
        return ENG.extract_transposed_workbook(buf.getvalue(), spec=D12.SPEC_D412)
    return _patch_attr(D12, "extract_transposed_workbook", _lax_extract)


def mut_m4_flag_off() -> Iterator[None]:
    """M4：_INCLUDE_D412_TRANSPOSED=False → 契约不含 d4-12-managed。"""
    return _patch_attr(D4, "_INCLUDE_D412_TRANSPOSED", False)


# 每个变异声明**期望被哪个守卫抓**（职责对应）。一个变异可能连带触发多个守卫（如 M2
# first_col 改 C 既让 materialize 写错列、又让 mapping_digest 漂移），但**对应职责守卫**必须在
# 失败集合里——否则说明该守卫在此场景没跑到（被前面守卫短路）或判据错位。
MUTATIONS: tuple[tuple[str, str, str, Callable[[], Iterator[None]]], ...] = (
    ("M1_registry_only_d429", "泛化改回 D4-29 单例（REGISTRY 只认 D4-29）",
     "guard_registry_resolves_d412", mut_m1_registry_only_d429),
    ("M2_first_column_C", "first_entity_column 改回 C",
     "guard_materialize_writes_first_column_B", mut_m2_first_column_C),
    ("M3_carrier_hidden_lax", "去 identity carrier hidden 强校验",
     "guard_carrier_hidden_fail_closed", mut_m3_extract_skips_hidden_check),
    ("M4_contract_no_d412", "契约去 d4-12-managed（flag off）",
     "guard_live_contract_has_d412", mut_m4_flag_off),
)


def main() -> int:
    ok, detail = _run(ALL_GUARDS)
    if not ok:
        print(json.dumps({"baseline": "BASELINE-FAIL", "detail": detail}, ensure_ascii=False, indent=2))
        return 1
    d29_ok, d29_detail = _run((guard_d429_regression,))
    if not d29_ok:
        print(json.dumps({"baseline": "BASELINE-FAIL(D4-29)", "detail": d29_detail}, ensure_ascii=False, indent=2))
        return 1

    verdicts: list[dict[str, Any]] = []
    non_red = 0
    d429_broken = 0
    responsibility_miss = 0
    for mid, desc, expect_guard, factory in MUTATIONS:
        try:
            with factory():
                failed = _run_collect(ALL_GUARDS)
                d29_still, d29_msg = _run((guard_d429_regression,))
        except Exception as exc:  # noqa: BLE001
            verdicts.append({"id": mid, "actual": "ANCHOR-MISS", "desc": desc, "detail": f"{type(exc).__name__}: {exc}"})
            non_red += 1
            continue
        entry = {"id": mid, "desc": desc, "expect_guard": expect_guard,
                 "d429_regression": "GREEN" if d29_still else "RED"}
        if not d29_still:
            d429_broken += 1
            entry["d429_detail"] = d29_msg
        if not failed:
            entry["actual"] = "GREEN"; entry["detail"] = "变异后守卫仍全过 = 守卫缺陷"
            non_red += 1
        else:
            entry["actual"] = "RED"
            entry["red_guards"] = sorted(failed)
            # 职责核对：对应职责守卫必须在失败集合里（明确「谁抓的」，非被前面守卫短路）。
            entry["responsibility_ok"] = expect_guard in failed
            if expect_guard not in failed:
                responsibility_miss += 1
                entry["responsibility_detail"] = f"期望 {expect_guard} 红但未在失败集合: {sorted(failed)}"
            entry["caught_by"] = failed.get(expect_guard, next(iter(failed.values())))
        verdicts.append(entry)

    baseline_after, _ = _run(ALL_GUARDS)
    report = {
        "baseline": "GREEN",
        "guards": [g.__name__ for g in ALL_GUARDS],
        "verdicts": verdicts,
        "non_red_count": non_red,
        "d429_regression_broken_count": d429_broken,
        "responsibility_miss_count": responsibility_miss,
        "baseline_after_restore": "GREEN" if baseline_after else "FAIL",
        "four_state_matrix": {"baseline": "GREEN", **{v["id"]: v["actual"] for v in verdicts}},
        "pass": (
            non_red == 0
            and d429_broken == 0
            and responsibility_miss == 0
            and all(v["actual"] == "RED" for v in verdicts)
            and baseline_after
        ),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
