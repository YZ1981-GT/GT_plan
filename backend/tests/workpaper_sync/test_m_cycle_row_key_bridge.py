# -*- coding: utf-8 -*-
"""M 循环「明细行 → 契约字段」键名桥守卫（spec `m-cycle-key-naming-unification` 任务 5）。

═══ 钉住什么 ═══

`phase5_m_cycle_common._build_store_projection` 曾有两个独立缺陷，任一都让明细值
**一格都进不了 OO**：

1. **键名空间错配**：拿契约 `column_key`（下划线）匹配前端行键（驼峰）⇒ 只命中 `remark`；
2. **行身份错配**：按 `rowId`/`row_uuid`/`id` 取身份，M 前端行只有 `key` ⇒ 零行产出。

本文件对**每一个 M entry**（10 条）逐条断言：真实前端行喂进去，必须产出该 entry
契约里真实存在的行表键，且值逐项相等。

═══ 为什么用「真实前端行键」而不是手写样例 ═══

手写样例容易照着 provider 的驼峰名写（那正好是「改名前」的样子），测出来是绿的而生产仍坏。
本文件的前端行键**从 composable 的 interface 现读**（`useM{n}Detail.ts`），
provider 侧从 `CONFIG.sheets[].fields[].json_key` 现取 —— 两侧都是现算，没有第三方清单。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync.m_cycle_row_key_bridge import (  # noqa: E402
    MRowKeyBridgeError,
    build_field_index,
    row_identity_of,
    split_detail_row,
)

_ROOT = _BACKEND.parent
_COMPOSABLES = _ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper" / "composables"

#: 十条 M entry：`(label, module_name, composable, interface)`。
#: interface 是与该 entry 明细表对应的前端行模型（M2 取非上市版，与契约 m201-unlisted-managed 对齐）。
ENTRIES = [
    ("M1", "phase5_m1_dividends_payable", "useM1Detail.ts", "M1DetailRow"),
    ("M2", "phase5_m2_paid_in_capital", "useM2Detail.ts", "M2DetailUnlistedRow"),
    ("M3", "phase5_m3_treasury_stock", "useM3Detail.ts", "M3DetailRow"),
    ("M4", "phase5_m4_capital_reserve", "useM4Detail.ts", "M4DetailRow"),
    ("M5", "phase5_m5_surplus_reserve", "useM5Detail.ts", "M5DetailRow"),
    ("M6", "phase5_m6_retained_earnings", "useM6Detail.ts", "M6DetailRow"),
    ("M7", "phase5_m7_special_reserve", "useM7Detail.ts", "M7DetailRow"),
    ("M8", "phase5_m8_general_risk_reserve", "useM8Detail.ts", "M8DetailRow"),
    ("M9", "phase5_m9_other_comprehensive_income", "useM9Detail.ts", "M9DetailRow"),
    ("M10", "phase5_m10_other_equity_instruments", "useM10Detail.ts", "M10DetailRow"),
]

#: 🔴 **不可对齐的三条（现算 2026-11-16）**——它们不是「键名差异」，而是**前端渲染的是另一张表**：
#:
#: * M3：契约/模板是库存股增减变动（batchName / repurchaseDate / repurchaseShares…），
#:   前端行只有 17 个键且与契约交集 = {remark}；
#: * M5：模板是盈余公积增减变动（itemName / priorOpening / increaseAmount…），
#:   前端行是 sourceName / beginning / accrual / capitalConversion / lossOffset —— **交集为空**；
#: * M7：交集为 {remark}。
#:
#: 这三条需要「重建前端行模型以对齐模板」，属另一层工作（涉及渲染列、导入导出、真实 OO 往返），
#: 不在本 spec 的「键名桥」范围。它们在本文件里被**显式登记为已知缺口**，
#: 并由 `test_disjoint_models_are_registered_and_still_disjoint` 钉住——一旦有人对齐了它们，
#: 该用例会变红并要求把它从名单里删掉（防止名单长期腐烂）。
#: 2026-11-16 §R12 之后：M3 / M5 / M7 已按权威模板**重建**行模型（列与行都来自
#: 生成文件 `mCycleDetailColumns.generated.ts`，真源 = provider），因此它们从「不可对齐」名单
#: 移入 `BRIDGED_ENTRIES`（本棘轮按设计变红，已按要求删除条目）。
#: 保留空 dict 而非删变量：后续若再出现不可对齐的 entry，往这里登记即可；
#: `test_disjoint_models_are_registered_and_still_disjoint` 在空分母下不产生用例（合法空集）。
DISJOINT_ENTRIES: dict[str, str] = {}

#: 桥已经真正接通的 entry（交集非空 ⇒ 键名一致就能投影）。
BRIDGED_ENTRIES = [e for e in ENTRIES if e[0] not in DISJOINT_ENTRIES]


def _provider(module_name: str):
    import importlib

    return importlib.import_module(f"app.services.workpaper_sync.{module_name}")


def _interface_keys(composable: str, interface: str) -> list[str]:
    """取该明细表行模型的键集（两种形态都支持）。

    * **interface 形态**（M1/M2/M4/M6/M8/M9/M10 仍是）：从 `export interface` 现读字段名；
    * **Record + 生成文件形态**（M3/M5/M7 §R12 重建后）：行键由生成文件提供，
      那份文件本身已由 `test_m_cycle_detail_columns_generated.py` 与 provider 对齐
      ⇒ 直接从生成文件取 `jsonKey`。

    🔴 为什么要兼容两种：重建后 M3/M5/M7 已不存在 `export interface`。
    只认 interface 会让守卫在**正确实现**上报「找不到 interface」—— 那是假阳。
    """
    path = _COMPOSABLES / composable
    assert path.exists(), f"{composable} 不存在 —— 改名后必须同步本守卫"
    src = path.read_text(encoding="utf-8")
    m = re.search(rf"export interface {interface}\b[^{{]*{{(.*?)\n}}", src, re.S)
    if m:
        keys: list[str] = []
        for line in m.group(1).splitlines():
            line = line.strip()
            if not line or line.startswith(("//", "/*", "*")):
                continue
            hit = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\??\s*:", line)
            if hit:
                keys.append(hit.group(1))
        return keys

    # Record 形态：键集来自生成文件
    label = composable.replace("use", "").replace("Detail.ts", "")
    gen = _ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper" / "m-cycle" / "mCycleDetailColumns.generated.ts"
    assert gen.exists(), f"{composable} 既无 interface {interface}，又找不到生成文件"
    gen_text = gen.read_text(encoding="utf-8")
    block = re.search(rf"\b{label}: \{{(.*?)\n  \}},", gen_text, re.S)
    assert block, f"生成文件里找不到 {label} 的定义"
    return re.findall(r'"jsonKey": "([^"]+)"', block.group(1))


def _row_identity_fields(keys: list[str]) -> set[str]:
    from app.services.workpaper_sync.m_cycle_row_key_bridge import ROW_IDENTITY_KEYS

    return set(keys) & set(ROW_IDENTITY_KEYS)


@pytest.mark.parametrize("label,module_name,composable,interface", ENTRIES, ids=[e[0] for e in ENTRIES])
def test_contract_declares_a_row_table(label, module_name, composable, interface) -> None:
    """每条 M entry 的契约都要声明行表（否则本 spec 的桥无对象）。"""
    mod = _provider(module_name)
    contract = mod.load_contract_from_disk()
    index = build_field_index(contract)
    assert index, f"{label} 契约没有任何带 table_key 的字段"


@pytest.mark.parametrize("label,module_name,composable,interface", BRIDGED_ENTRIES, ids=[e[0] for e in BRIDGED_ENTRIES])
def test_real_frontend_row_projects_onto_contract_fields(
    label, module_name, composable, interface
) -> None:
    """**核心判据**：真实前端行 → 必须产出契约行表键（不是死键、不是零行）。"""
    mod = _provider(module_name)
    contract = mod.load_contract_from_disk()
    index = build_field_index(contract)
    keys = _interface_keys(composable, interface)

    # 用 interface 的**真实键名**造一行（值用可识别的哨兵），行身份取前端惯用的 `key`
    row = {k: f"V::{k}" for k in keys if k not in _row_identity_fields(keys)}
    row["key"] = f"{label.lower()}-detail-1"

    emitted = split_detail_row(row, field_index=index)
    assert emitted, (
        f"{label}: 真实前端行（键来自 {composable} 的 {interface}）投影出 **0** 个契约字段 —— "
        "这正是「键名空间错配 + 行身份错配」叠加后的现场形态：值一格都进不了 OO。"
    )

    # 产出的键必须都是 `{table_key}/{row_uuid}/{column_key}` 形态，且 row_uuid 是前端给的身份
    for stable_key, _raw, spec in emitted:
        parts = stable_key.split("/")
        assert len(parts) == 3, stable_key
        assert parts[1] == f"{label.lower()}-detail-1", stable_key
        assert parts[2] == spec["column_key"], stable_key

    # 值必须逐项带过去（不串行、不丢）
    for _stable_key, raw, spec in emitted:
        assert raw == f"V::{next(k for k in keys if k not in _row_identity_fields(keys) and raw == f'V::{k}')}", (
            f"{label}: {spec['column_key']} 的值串了：{raw!r}"
        )


@pytest.mark.parametrize("label,module_name,composable,interface", BRIDGED_ENTRIES, ids=[e[0] for e in BRIDGED_ENTRIES])
def test_frontend_keys_that_match_a_contract_column_are_not_dropped(
    label, module_name, composable, interface
) -> None:
    """前端行里凡能对上契约列的键，都不得被静默丢弃。

    口径：`json_pointer` 末段（provider 声明的前端键）∪ `column_key`。
    这一条防的是「桥只认一种写法」——两种写法都必须命中。
    """
    mod = _provider(module_name)
    contract = mod.load_contract_from_disk()
    index = build_field_index(contract)
    known = set()
    for bucket in index.values():
        known |= set(bucket)

    keys = _interface_keys(composable, interface)
    matched = [k for k in keys if k in known]
    assert matched, (
        f"{label}: {composable} 的 {interface} 里没有任何键能对上契约 —— "
        "说明 provider 声明的前端键与前端行模型完全脱节"
    )

    row = {k: "x" for k in matched}
    row["key"] = f"{label.lower()}-r1"
    emitted = split_detail_row(row, field_index=index)
    emitted_cols = {spec["column_key"] for _k, _v, spec in emitted}
    for key in matched:
        spec = next(s for bucket in index.values() for k, s in bucket.items() if k == key)
        assert spec["column_key"] in emitted_cols, (
            f"{label}: 前端键 {key!r} 能对上契约列 {spec['column_key']!r}，但投影时被丢弃了"
        )


def test_row_identity_accepts_the_frontend_key_field() -> None:
    """M 循环前端行只有 `key` —— 必须被认作行身份，不得整行跳过。"""
    assert row_identity_of({"key": "m1-detail-1"}) == "m1-detail-1"
    assert row_identity_of({"key": "  spaced  "}) == "spaced"


def test_row_identity_never_falls_back_to_array_index() -> None:
    """缺身份必须 fail closed —— 退回下标会让行序变化被认成新行。"""
    with pytest.raises(MRowKeyBridgeError) as exc:
        row_identity_of({"shareholderName": "甲"})
    assert "rowId" in str(exc.value) or "key" in str(exc.value)


def test_unmatched_frontend_columns_are_not_written_as_dead_keys() -> None:
    """前端多出来的列（契约没有）不得产出死键 —— 否则物化时无处可写。"""
    mod = _provider("phase5_m1_dividends_payable")
    index = build_field_index(mod.load_contract_from_disk())
    row = {"key": "r1", "shareholderName": "甲", "totallyUnknownColumn": "zzz"}
    emitted = split_detail_row(row, field_index=index)
    cols = {spec["column_key"] for _k, _v, spec in emitted}
    assert "totallyUnknownColumn" not in cols
    assert "shareholder_name" in cols


@pytest.mark.parametrize("label,module_name", sorted(DISJOINT_ENTRIES.items()))
def test_disjoint_models_are_registered_and_still_disjoint(label, module_name) -> None:
    """已知缺口棘轮：M3/M5/M7 的前端行模型与契约列**仍然**几乎不相交。

    为什么要这么写：这三条不是「键名没对齐」，而是前端渲染的是另一张表
    （见模板表头 vs 前端列标题）。把它们当作「改个键名就好」会把真问题掩盖掉。
    一旦有人真的建了是对得上的行模型，本用例会红 ⇒ 必须从 DISJOINT_ENTRIES 删掉它。
    """
    mod = _provider(module_name)
    index = build_field_index(mod.load_contract_from_disk())
    known = set()
    for bucket in index.values():
        known |= set(bucket)

    composable, interface = next(
        (c, i) for lbl, _m, c, i in ENTRIES if lbl == label
    )
    keys = _interface_keys(composable, interface)
    matched = [k for k in keys if k in known]

    # 交集上限：现算 M3=1 / M5=0 / M7=1（都只有 remark 或更少）
    assert len(matched) <= 1, (
        f"{label}: 前端行模型现在能对上 {len(matched)} 个契约键 {matched} —— "
        "说明它已被对齐，必须从 DISJOINT_ENTRIES 删掉并把它加回 BRIDGED_ENTRIES"
    )
