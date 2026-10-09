# -*- coding: utf-8 -*-
"""Task 11 欠账：Property 5 在三张 D6 新 sheet 上「无分母」的可执行复核 + 由此暴露的静默面守卫。

spec: d567-sync-coverage-via-row-table-engine · Task 11 · Requirements 2.8, 2.9, 6.1

═══ 原登记与本文件的关系 ═══

Task 11 如实登记：三张 D6 新 sheet（D6-3 / D6-5 / D6-8）实测 `aging_layout=None`
⇒ **Property 5（flat 键派生 ≡ 原写法）在本轮无分母**；flat 路径仍只由已接的 D6-2 承载
（上游 `test_phase5_row_table_sheet.TestProperty3ManagedFieldSpecsD6Flat` 已覆盖 —— 本文件
已复核该类真实存在）。

本文件做两件事：
  ① 把「无分母」从注释声明变成**现算复核**（三张的 `expand_aging_fields()` 恒为空、
    `managed_field_specs()` 就等于声明字段本身、无账龄尾）；
  ② 🔴 复核过程中发现一个**静默面**，就地立守卫（见下）。

═══ 🔴 发现的静默面：`aging_groups` 为空时 `aging_layout` 完全惰性 ═══

实测（2026-09-30）：把 `SPEC_D603`（`layout=None, groups=()`）的 layout 翻成 `flat` 或 `nested`，
`expand_aging_fields()` **都不报错**、都返回 0 条，`managed_field_specs()` 输出**逐项相同**。
机理：引擎 flat/nested 两分支都是 `for group in spec.aging_groups`，空序列零次迭代。

⇒ 后果：若某张有账龄列的 sheet 声了 `aging_layout=flat` 却**忘了给 `aging_groups`**，
  它会**静默丢掉全部账龄列**且无任何报错 —— 这是「声明层静默失效」的典型形态
  （对照 Task 13 已钉住的另一侧：layout 与 groups **形态**错配会响亮抛 ValueError；
  但 groups **为空**这一侧是静默的，两侧不是一回事）。

⇒ 🔴 这个风险不是假想：Task 9 的原始 bullet 写的是「`D6-3-rows` / `D6-5-rows`；`aging_layout=flat`」，
  而交付事实是 `aging_layout=None`（narrative 行已如实记为 None）。**当时若照 bullet 把代码改成
  `flat` 而没补 `aging_groups`，产出会与现在一模一样、零报错**（上面的惰性实验就是这个场景）。
  也就是说这条声明矛盾之所以至今无害，靠的是运气而非设计。故本文件把不变量冻结下来。

全仓现算基线（2026-09-30）：**124** 个 `RowTableSheetSpec` 实例，layout 分布
`None=120 / nested=3 / flat=1`，两类违规**均为 0**。
"""
from __future__ import annotations

import dataclasses
import importlib
import os
import pkgutil
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

import app.services.workpaper_sync as _ws_pkg  # noqa: E402
from app.services.workpaper_sync.phase5_row_table_sheet import (  # noqa: E402
    AgingLayout,
    RowTableSheetSpec,
    expand_aging_fields,
    managed_field_specs,
)
from app.services.workpaper_sync.phase5_d6_03_impairment import SPEC_D603  # noqa: E402
from app.services.workpaper_sync.phase5_d6_05_related_party import SPEC_D605  # noqa: E402
from app.services.workpaper_sync.phase5_d6_08_ecl import SPEC_D608  # noqa: E402
from app.services.workpaper_sync.phase5_d6_contract_assets import SPEC_D62  # noqa: E402

#: 三张 D6 新 sheet（Task 9/10 交付物）+ 其 store 键。
#: 🔴 `D6-8` 是 `-single-rows` **不是** `-rows`（后者全仓零写入点，Task 10 已钉住此陷阱）。
_NEW_D6_SHEETS = [
    ("D6-3", SPEC_D603, "D6-3-rows", 14),
    ("D6-5", SPEC_D605, "D6-5-rows", 14),
    ("D6-8", SPEC_D608, "D6-8-single-rows", 8),
]


def _all_row_table_specs() -> list[tuple[str, str, RowTableSheetSpec]]:
    """全仓收集 `RowTableSheetSpec` 实例（现扫，禁写死清单）。"""
    out: list[tuple[str, str, RowTableSheetSpec]] = []
    for m in pkgutil.iter_modules(_ws_pkg.__path__):
        if not m.name.startswith("phase5_"):
            continue
        try:
            mod = importlib.import_module(f"app.services.workpaper_sync.{m.name}")
        except Exception:  # noqa: BLE001  # import 失败由别的门管，本文件不代管
            continue
        for attr in dir(mod):
            obj = getattr(mod, attr)
            if isinstance(obj, RowTableSheetSpec):
                out.append((m.name, attr, obj))
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 一、把「Property 5 无分母」从注释变成现算复核
# **Validates: Requirements 2.8, 2.9**
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "label,spec,store_key,n_fields",
    _NEW_D6_SHEETS,
    ids=[s[0] for s in _NEW_D6_SHEETS],
)
def test_new_d6_sheets_have_no_aging_denominator(
    label: str, spec: RowTableSheetSpec, store_key: str, n_fields: int
) -> None:
    """🔴 现算复核 Task 11 的如实登记：三张新 sheet 无账龄组 ⇒ Property 5 无分母。

    同时钉住 store 键（D6-8 的 `-single-rows` 陷阱）与字段数。
    """
    assert spec.aging_layout is None, f"{label} 的 aging_layout 不再是 None（登记前提变了）"
    assert spec.aging_groups == (), f"{label} 出现了 aging_groups（登记前提变了）"
    assert expand_aging_fields(spec) == (), f"{label} 竟展开出账龄字段"
    assert spec.store_item_id == store_key, f"{label} store 键漂移：{spec.store_item_id!r}"
    assert len(spec.field_specs) == n_fields


@pytest.mark.parametrize(
    "label,spec",
    [(s[0], s[1]) for s in _NEW_D6_SHEETS],
    ids=[s[0] for s in _NEW_D6_SHEETS],
)
def test_managed_field_specs_equals_declared_fields_when_no_aging(
    label: str, spec: RowTableSheetSpec
) -> None:
    """无账龄组时 `managed_field_specs()` **就等于**声明字段（按列序），无任何账龄尾。

    这是「Property 5 无分母」的另一面：派生管线在这三张上是恒等变换 ⇒ 没有 flat/nested
    键派生行为可供对照，不是漏测。
    """
    mfs = managed_field_specs(spec)
    assert len(mfs) == len(spec.field_specs), f"{label} 派生后字段数变了 ⇒ 混进了账龄尾"
    # 列序必须升序（引擎承诺「按列序排序」）。
    cols = [f[1] for f in mfs]
    assert cols == sorted(cols, key=lambda c: (len(c), c)), f"{label} 列序未升序：{cols}"
    # 字段 key 集合与声明一致（顺序可被排序改变，集合不该变）。
    assert {f[0] for f in mfs} == {f[0] for f in spec.field_specs}


# ═══════════════════════════════════════════════════════════════════════════
# 二、🔴 静默面守卫：layout 与 aging_groups 必须同生共死
# **Validates: Requirements 2.9, 6.1**
# ═══════════════════════════════════════════════════════════════════════════


def test_layout_is_inert_when_groups_are_empty_documented_silent_face() -> None:
    """🔴 把静默面本身钉成判据：`groups=()` 时翻 layout **不报错、输出不变**。

    本条**不是**要求修掉这个惰性（引擎对空序列零次迭代是正常语义），而是把它记录成
    可执行事实 —— 正因为它静默，下一条的不变量才必须存在。若某天引擎改成「layout 非 None
    但 groups 空就抛错」，本条会红，届时下一条不变量可降级为冗余（那是好事，要显式处理）。
    """
    base = managed_field_specs(SPEC_D603)
    for target in (AgingLayout.flat, AgingLayout.nested):
        flipped = dataclasses.replace(SPEC_D603, aging_layout=target)
        assert expand_aging_fields(flipped) == (), f"翻成 {target} 后竟展开出字段"
        assert managed_field_specs(flipped) == base, f"翻成 {target} 后 managed_field_specs 变了"


def test_repo_wide_layout_groups_invariant_holds() -> None:
    """🔴 全仓不变量：`aging_layout is not None` ⟺ `aging_groups` 非空。

    违反 A（layout 非 None 但 groups 空）= 该 sheet **静默丢掉全部账龄列**、零报错；
    违反 B（groups 非空但 layout None）= 账龄声明写了却永不展开，同样静默。
    两侧都无报错 ⇒ 只能靠本门拦。
    """
    specs = _all_row_table_specs()
    assert specs, "全仓扫不到任何 RowTableSheetSpec ⇒ 扫描器坏了（空分母假绿）"
    violations_a = [
        f"{m}.{a}" for m, a, s in specs if s.aging_layout is not None and not s.aging_groups
    ]
    violations_b = [
        f"{m}.{a}" for m, a, s in specs if s.aging_layout is None and s.aging_groups
    ]
    assert violations_a == [], (
        f"{len(violations_a)} 个 spec 声了 aging_layout 却没给 aging_groups "
        f"⇒ 账龄列会静默丢失：{violations_a}"
    )
    assert violations_b == [], (
        f"{len(violations_b)} 个 spec 给了 aging_groups 却没声 aging_layout "
        f"⇒ 账龄声明永不展开：{violations_b}"
    )


def test_each_engine_branch_still_has_a_carrier() -> None:
    """引擎三分支（None / flat / nested）都还有承载样本 ⇒ 没有分支脱离回归门视野。

    🔴 现算分布（2026-09-30 基线：None=120 / nested=3 / flat=1），**不写死总数** ——
    只断言每个分支非空 + flat 侧必须仍包含 D6-2（引擎 flat 路径当前唯一样本，
    若它被摘掉，flat 分支就没有任何真实 entry 在跑了）。
    """
    specs = _all_row_table_specs()
    flat = [f"{m}.{a}" for m, a, s in specs if s.aging_layout is AgingLayout.flat]
    nested = [f"{m}.{a}" for m, a, s in specs if s.aging_layout is AgingLayout.nested]
    none_ = [f"{m}.{a}" for m, a, s in specs if s.aging_layout is None]
    assert flat, "flat 分支已无承载样本 ⇒ 引擎该分支脱离回归门"
    assert nested, "nested 分支已无承载样本"
    assert none_, "None 分支已无承载样本"
    assert any("d6_contract_assets" in name for name in flat), (
        f"D6-2 不在 flat 样本里（flat 当前样本：{flat}）—— 引擎 flat 路径的唯一真实承载被改了"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 三、变异自检
# ═══════════════════════════════════════════════════════════════════════════


def test_mutation_layout_without_groups_is_caught_by_invariant() -> None:
    """🔴 变异：造一个 `layout=flat` 但 `groups=()` 的 spec，不变量判据必须检出它。

    证明 `test_repo_wide_layout_groups_invariant_holds` 不是「全仓恰好干净」的恒真装饰。
    """
    bad = dataclasses.replace(SPEC_D603, aging_layout=AgingLayout.flat)
    assert bad.aging_layout is not None and not bad.aging_groups
    # 复用不变量的同一谓词 —— 必须判为违规 A。
    is_violation_a = bad.aging_layout is not None and not bad.aging_groups
    assert is_violation_a, "变异体未被判为违规 ⇒ 不变量谓词无鉴别力"
    # 而且它确实静默（这就是危害）：展开为空、不抛。
    assert expand_aging_fields(bad) == ()


def test_mutation_groups_without_layout_is_caught_by_invariant() -> None:
    """🔴 反向变异：把 D6-2 的 layout 摘成 None（groups 仍非空）⇒ 判为违规 B，且账龄列静默消失。"""
    bad = dataclasses.replace(SPEC_D62, aging_layout=None)
    assert bad.aging_groups, "D6-2 的 aging_groups 应非空（否则本变异没意义）"
    is_violation_b = bad.aging_layout is None and bool(bad.aging_groups)
    assert is_violation_b
    # 危害实证：原本 8 条账龄字段，摘掉 layout 后变 0 条，全程无报错。
    assert len(expand_aging_fields(SPEC_D62)) == 8
    assert expand_aging_fields(bad) == (), "摘掉 layout 后竟还展开出字段"


def test_upstream_flat_coverage_reference_is_not_stale() -> None:
    """🔴 复核 Task 11 引用的上游覆盖真实存在（防「引用了一个不存在的判据」当挡箭牌）。

    Task 11 原文称 flat 路径「上游 D1 spec 的 `TestProperty3ManagedFieldSpecsD6Flat` 已覆盖」。
    """
    mod = importlib.import_module("tests.workpaper_sync.test_phase5_row_table_sheet")
    assert hasattr(mod, "TestProperty3ManagedFieldSpecsD6Flat"), (
        "Task 11 引用的上游 flat 覆盖类已不存在 ⇒ 该引用已过期，需重新安排 flat 侧覆盖"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v", "--tb=short"]))
