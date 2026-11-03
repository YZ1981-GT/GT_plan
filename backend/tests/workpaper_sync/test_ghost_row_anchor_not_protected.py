# -*- coding: utf-8 -*-
"""幽灵行锚点不得是受保护列（spec oo-writeback-template-parity-closure R3 批 B1）。

═══ 为什么要这道门 ═══

`phase5_row_table_sheet.merge_projection_into_store_rows` 合并 OO 侧读回的值时跳过受保护字段
（`fv.is_protected` ⇔ mode ∈ `contracts.PROTECTED_MODES`：formula 一族 + auto_source），受保护列的
值不进 store。随后的幽灵行防护只对**本次新增**的身份判「锚点空 ⇒ 剔除」，锚点 =
`managed_field_specs(spec)[spec.ghost_row_anchor_index]`。

⇒ 锚点若是受保护列，OO 侧新增的行在合并结果里锚点恒空 ⇒ **每一行都被当幽灵行剔除**，零报错、
  零冲突、回执里也看不出来（被剔除的行不算 touched）。

这不是假想：批 B1 把 G11-2 的 A 序号改成 auto_source（前端按位置编号）时锚点仍是默认 `[0]`，
磁盘变异实测 OO 侧新增的行全部丢失；E1-4（A 序号）早先同因改指 B。只靠逐家记得改锚点不可靠
⇒ 全仓现扫冻结。

═══ 判据 ═══

全仓 `RowTableSheetSpec`（`phase5_*` / `pilot_*` 模块的属性、tuple / list / dict 成员、以及
`managed_row_table_specs()` / `section_specs()` / `instrumentation_row_table_specs()` 工厂返回值）
逐个取锚点：下标在范围内，且 mode 不在 `PROTECTED_MODES`。例外逐条登记且**可伪证**（锚点列 / mode /
固定行判据 / 扩展区），失效即红、只许删。模块导入失败也判红（扫不到的模块就是脱管）。
"""
from __future__ import annotations

import dataclasses
import importlib
import os
import pkgutil
import sys
from pathlib import Path
from typing import Any

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

import app.services.workpaper_sync as _ws_pkg  # noqa: E402
from app.services.workpaper_sync.contracts import PROTECTED_MODES, FieldMode  # noqa: E402
from app.services.workpaper_sync.phase5_e1_04_digital import SPEC_E104  # noqa: E402
from app.services.workpaper_sync.phase5_g11_02_detail import SPEC_G1102  # noqa: E402
from app.services.workpaper_sync.phase5_row_table_sheet import (  # noqa: E402
    RowTableSheetSpec,
    managed_field_specs,
)

#: 正对照：A 序号受保护（前端按位置编号 ⇒ auto_source）、锚点改指 B 的两家。
_KNOWN_B_ANCHORED: tuple[RowTableSheetSpec, ...] = (SPEC_E104, SPEC_G1102)

_FACTORY_NAMES: tuple[str, ...] = (
    "managed_row_table_specs",
    "section_specs",
    "instrumentation_row_table_specs",
)

#: 例外：锚点是受保护列、但不会因此丢行的区。键 = (store_item_id, table_key)。
#:
#: 🔴 每条都必须可伪证（不是只写理由）：
#:   - `anchor_column` / `anchor_mode`：锚点现状，变了 ⇒ 本条失效；
#:   - `label_column`：固定行判据 —— 本区**不受管**的行标签列（模板预置类别名，取数公式按它匹配）。
#:     该列一旦受管（可在 OO 侧录名称），新增行就有意义，本条即不成立；
#:   - `expansion_store_item_id`：同 sheet 上承接新增行的区，其锚点必须可编辑、且标签列在该区受管。
_ALLOWED: dict[tuple[str, str], dict[str, str]] = {
    ("F3-1-adj-seed-rows", "adjudication_seed_rows"): {
        "anchor_column": "B",
        "anchor_mode": "formula",
        "label_column": "A",
        "expansion_store_item_id": "F3-1-adj-slot-rows",
        "reason": (
            "F3-1 审定表种子区 R7-R8 是模板预置的两行（银行承兑汇票 / 商业承兑汇票），A 列类别名是"
            " SUMPRODUCT 匹配键、不受管；本区 B/E/F/G/H/I 全是公式，可编辑的只有调整与索引列。"
            "OO 侧在本区插入的行既录不了类别、也取不到数，丢弃是正确结果；扩展行走空槽区 R9-R10。"
        ),
    },
}


def _collect(val: Any, label: str, modname: str, out: dict[int, tuple[str, str, RowTableSheetSpec]]) -> None:
    if isinstance(val, RowTableSheetSpec):
        out.setdefault(id(val), (modname, label, val))
        return
    if isinstance(val, dict):
        for k, v in val.items():
            if isinstance(v, RowTableSheetSpec):
                out.setdefault(id(v), (modname, f"{label}[{k!r}]", v))
        return
    if isinstance(val, (tuple, list)):
        for i, v in enumerate(val):
            if isinstance(v, RowTableSheetSpec):
                out.setdefault(id(v), (modname, f"{label}[{i}]", v))


def _scan() -> tuple[list[tuple[str, str, RowTableSheetSpec]], list[str]]:
    """全仓现扫（禁写死清单）。返回 (specs, 导入 / 工厂调用失败)。"""
    found: dict[int, tuple[str, str, RowTableSheetSpec]] = {}
    failures: list[str] = []
    for m in pkgutil.iter_modules(_ws_pkg.__path__):
        if not (m.name.startswith("phase5_") or m.name.startswith("pilot_")):
            continue
        try:
            mod = importlib.import_module(f"app.services.workpaper_sync.{m.name}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{m.name}: {type(exc).__name__}: {exc}"[:300])
            continue
        for name, val in vars(mod).items():
            _collect(val, name, m.name, found)
        for fn_name in _FACTORY_NAMES:
            fn = getattr(mod, fn_name, None)
            if not callable(fn):
                continue
            try:
                _collect(fn(), f"{fn_name}()", m.name, found)
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{m.name}.{fn_name}(): {type(exc).__name__}: {exc}"[:300])
    specs = sorted(found.values(), key=lambda t: (t[0], t[1]))
    return specs, failures


def _anchor(spec: RowTableSheetSpec) -> tuple[str, str, str, str] | None:
    """锚点 (column_key, column, mode, json_path)；下标越界返回 None。"""
    specs = managed_field_specs(spec)
    idx = spec.ghost_row_anchor_index
    if not 0 <= idx < len(specs):
        return None
    ck, col, mode, _vt, jp, _label, _g = specs[idx]
    return str(ck), str(col), str(mode), str(jp)


def _violations(
    specs: list[tuple[str, str, RowTableSheetSpec]],
    allowed: dict[tuple[str, str], dict[str, str]],
) -> list[str]:
    """判据本体：越界 / 受保护锚点（不在例外表里）。"""
    out: list[str] = []
    for modname, label, spec in specs:
        if not managed_field_specs(spec):
            continue
        a = _anchor(spec)
        where = f"{modname}.{label}（{spec.store_item_id} / {spec.table_key}）"
        if a is None:
            out.append(f"{where} 锚点下标 {spec.ghost_row_anchor_index} 越界")
            continue
        if FieldMode(a[2]) in PROTECTED_MODES and (spec.store_item_id, spec.table_key) not in allowed:
            out.append(f"{where} 锚点 {a[1]} 列 {a[3]} 是 {a[2]}（受保护）⇒ OO 侧新增行全被当幽灵行剔除")
    return out


def _stale_allowances(
    specs: list[tuple[str, str, RowTableSheetSpec]],
    allowed: dict[tuple[str, str], dict[str, str]],
) -> list[str]:
    """例外表逐条伪证：失效 / 判据不成立即报。"""
    by_key = {(s.store_item_id, s.table_key): s for _m, _l, s in specs}
    by_item: dict[str, list[RowTableSheetSpec]] = {}
    for _m, _l, s in specs:
        by_item.setdefault(s.store_item_id, []).append(s)
    out: list[str] = []
    for key, entry in allowed.items():
        spec = by_key.get(key)
        if spec is None:
            out.append(f"{key} 已扫不到 ⇒ 删本条")
            continue
        a = _anchor(spec)
        if a is None or FieldMode(a[2]) not in PROTECTED_MODES:
            out.append(f"{key} 锚点已不受保护 ⇒ 删本条")
            continue
        if (a[1], a[2]) != (entry["anchor_column"], entry["anchor_mode"]):
            out.append(f"{key} 锚点实为 {a[1]}/{a[2]}，登记 {entry['anchor_column']}/{entry['anchor_mode']}")
        label_col = entry["label_column"]
        if label_col in {f[1] for f in managed_field_specs(spec)}:
            out.append(f"{key} 标签列 {label_col} 已受管 ⇒ 不再是固定行区，例外不成立")
        exp = [s for s in by_item.get(entry["expansion_store_item_id"], ()) if s.sheet_key == spec.sheet_key]
        if not exp:
            out.append(f"{key} 扩展区 {entry['expansion_store_item_id']} 在同 sheet 上扫不到")
            continue
        for s in exp:
            ea = _anchor(s)
            if ea is None or FieldMode(ea[2]) in PROTECTED_MODES:
                out.append(f"{key} 扩展区 {s.store_item_id} 的锚点不可编辑")
            label_specs = [f for f in managed_field_specs(s) if f[1] == label_col]
            if not label_specs or FieldMode(label_specs[0][2]) in PROTECTED_MODES:
                out.append(f"{key} 扩展区 {s.store_item_id} 的标签列 {label_col} 不可编辑")
    return out


@pytest.fixture(scope="module")
def scanned() -> tuple[list[tuple[str, str, RowTableSheetSpec]], list[str]]:
    return _scan()


def test_scan_has_no_import_failures(scanned) -> None:
    """扫不到的模块 = 锚点脱管 ⇒ 导入 / 工厂调用失败一律判红（不静默跳过）。"""
    specs, failures = scanned
    assert specs, "全仓扫不到任何 RowTableSheetSpec ⇒ 扫描器坏了（空分母假绿）"
    assert failures == [], f"{len(failures)} 处导入 / 工厂调用失败，其锚点未被检查：{failures}"


def test_scan_reaches_known_carriers(scanned) -> None:
    """正对照：已知「A 序号受保护 ⇒ 锚点改 B」的两家必须被扫到且锚点是 B 可编辑列；
    工厂 / 容器路径也必须有产出（只扫模块属性会漏掉按区构造的 spec）。"""
    specs, _ = scanned
    ids = {id(s) for _m, _l, s in specs}
    for known in _KNOWN_B_ANCHORED:
        assert id(known) in ids, f"扫描器没扫到 {known.store_item_id}"
        first = managed_field_specs(known)[0]
        assert first[1] == "A" and FieldMode(first[2]) in PROTECTED_MODES, (
            f"{known.store_item_id} 的 A 列已不是受保护序号 ⇒ 换一家正对照"
        )
        a = _anchor(known)
        assert a is not None and a[1] == "B", f"{known.store_item_id} 锚点实为 {a}"
        assert FieldMode(a[2]) not in PROTECTED_MODES
    via_container = [lbl for _m, lbl, _s in specs if "[" in lbl or lbl.endswith("()")]
    assert via_container, "容器 / 工厂路径零产出 ⇒ 只扫到了模块属性"


def test_no_protected_ghost_anchor(scanned) -> None:
    specs, _ = scanned
    bad = _violations(specs, _ALLOWED)
    assert bad == [], "\n".join([f"{len(bad)} 个行表的幽灵行锚点不可用：", *bad])


def test_allowances_are_falsifiable_and_current(scanned) -> None:
    specs, _ = scanned
    stale = _stale_allowances(specs, _ALLOWED)
    assert stale == [], "\n".join(["例外表失效或判据不成立：", *stale])
    for key, entry in _ALLOWED.items():
        assert len(entry.get("reason", "")) >= 20, f"{key} 缺少理由"


# ═══ 变异自检（判据本体是本文件的函数，变异喂的是改过的声明副本）═══


def test_mutation_anchor_back_to_protected_seq_is_caught(scanned) -> None:
    """G11-2 锚点改回默认 0（A 序号 auto_source）⇒ 判据必须报出它。"""
    specs, _ = scanned
    item = SPEC_G1102.store_item_id
    mutated = [
        (m, lbl, dataclasses.replace(s, ghost_row_anchor_index=0) if s is SPEC_G1102 else s)
        for m, lbl, s in specs
    ]
    assert all(item not in b for b in _violations(specs, _ALLOWED)), "变异前 G11-2 就已违规"
    bad = _violations(mutated, _ALLOWED)
    assert any(item in b and "auto_source" in b for b in bad), bad


def test_mutation_out_of_range_anchor_is_caught(scanned) -> None:
    specs, _ = scanned
    m0, l0, s0 = next(t for t in specs if managed_field_specs(t[2]))
    n = len(managed_field_specs(s0))
    bad = _violations([(m0, l0, dataclasses.replace(s0, ghost_row_anchor_index=n))], _ALLOWED)
    assert len(bad) == 1 and "越界" in bad[0], bad


def test_mutation_allowance_without_spec_or_with_editable_anchor_is_stale(scanned) -> None:
    """例外表的两种失效形态都必须报：spec 不在了 / 锚点已可编辑。"""
    specs, _ = scanned
    without_seed = [t for t in specs if t[2].store_item_id != "F3-1-adj-seed-rows"]
    assert any("扫不到" in s for s in _stale_allowances(without_seed, _ALLOWED))
    seed_entry = dict(_ALLOWED[("F3-1-adj-seed-rows", "adjudication_seed_rows")])
    editable = {(SPEC_E104.store_item_id, SPEC_E104.table_key): seed_entry}
    assert any("已不受保护" in s for s in _stale_allowances(specs, editable))


def test_mutation_label_column_managed_breaks_allowance(scanned) -> None:
    """种子区把 A 类别列改成受管（可在 OO 侧录名称）⇒ 固定行判据不成立，例外必须失效。"""
    specs, _ = scanned
    mutated = []
    for m, lbl, s in specs:
        if s.store_item_id == "F3-1-adj-seed-rows":
            extra = ("category", "A", "editable", "text", "label", "项目", "")
            s = dataclasses.replace(s, field_specs=(extra, *s.field_specs), ghost_row_anchor_index=1)
        mutated.append((m, lbl, s))
    stale = _stale_allowances(mutated, _ALLOWED)
    assert any("标签列 A 已受管" in x for x in stale), stale
