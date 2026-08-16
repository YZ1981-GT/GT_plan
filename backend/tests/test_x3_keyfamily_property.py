"""test_x3_keyfamily_property —— 用例层。

判据（常量 / 登记表 / fixture / 纯函数 / helper）见 `_test_x3_keyfamily_property_criteria.py`，
原文件 docstring 也在那里。拆分原因：原单文件 1586 行 > pre-commit 800 行门禁。
"""

from __future__ import annotations

import asyncio
import io
import json
import uuid
from collections.abc import Iterable, Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any, NamedTuple, get_args

import pytest
import sqlalchemy as sa
from fastapi import APIRouter, FastAPI
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st
from httpx import ASGITransport, AsyncClient
from openpyxl import Workbook
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.routers.wp_render_strategies import _x3_adjustment_import_export as impl

from tests._test_x3_keyfamily_property_criteria import (  # noqa: F401  fixtures 需在本模块命名空间
    _AbstractRow,
    _BASE_INDICES,
    _CONTRACT,
    _ITEM_COL,
    _MARK,
    _MAX_ROWS,
    _MAX_SEED,
    _SETTINGS,
    _SNAPSHOT_COLUMNS,
    _SeedPlan,
    _WP_BYSTANDER,
    _WP_COL,
    _WP_TARGET,
    _arb_row,
    _arb_rows,
    _arb_seed,
    _belongs,
    _canonical_entry_types,
    _codes,
    _delta,
    _expected_seed_readback,
    _exploded_keys,
    _face,
    _family_prefixes,
    _hz,
    _is_single,
    _keys_for_indices,
    _leading_run,
    _materialize,
    _materialize_all,
    _spec,
    _static_region,
    _strategies,
    _upload_bytes,
)

__all__ = [
    "_AbstractRow",
    "_BASE_INDICES",
    "_CONTRACT",
    "_ITEM_COL",
    "_MARK",
    "_MAX_ROWS",
    "_MAX_SEED",
    "_SETTINGS",
    "_SNAPSHOT_COLUMNS",
    "_SeedPlan",
    "_WP_BYSTANDER",
    "_WP_COL",
    "_WP_TARGET",
    "_arb_row",
    "_arb_rows",
    "_arb_seed",
    "_belongs",
    "_canonical_entry_types",
    "_codes",
    "_delta",
    "_expected_seed_readback",
    "_exploded_keys",
    "_face",
    "_family_prefixes",
    "_hz",
    "_is_single",
    "_keys_for_indices",
    "_leading_run",
    "_materialize",
    "_materialize_all",
    "_spec",
    "_static_region",
    "_strategies",
    "_upload_bytes",
]


def test_anchor_workscope_and_family_distribution() -> None:
    """作业面规模 / 与实现键集双向锁死 / 三族分布 —— 塌陷时 ∀ 属性恒真。"""
    codes = _codes()
    assert len(codes) == 16, (
        f"作业面实测 {len(codes)} 张（design 用户裁决 1：16 张，零 pending_manual）："
        f"{list(codes)}"
    )
    assert set(codes) == set(impl.X3_SHEET_SPECS), (
        "清单派生作业面与实现 `X3_SHEET_SPECS` 分叉：\n"
        f"  清单={sorted(codes)}\n  实现={sorted(impl.X3_SHEET_SPECS)}"
    )
    dist: dict[str, list[str]] = {}
    for code in codes:
        dist.setdefault(_spec(code).key_family.value, []).append(code)
    counts = {family: len(members) for family, members in sorted(dist.items())}
    assert len(counts) == 3, (
        f"写入族只覆盖到 {counts} ⇒ 三族分派里有一支没有任何 sheet 走到，"
        f"本文件对那一支的判据全是空转"
    )
    assert counts == {"single_json": 5, "per_field": 3, "per_field_plus_data": 8}, (
        f"三族分布实测 {counts}（本轮基线 single_json 5 / per_field 3 / "
        f"per_field_plus_data 8）—— 分布变了说明清单 `key_family` 被改，"
        f"本文件按族分推的判据（尤其整表单键族的数组长度那条）须同步复核"
    )
    families = {_spec(code).read_family for code in codes}
    assert impl.KeyFamily.NONE not in families, (
        "有 sheet 的 `read_family` 还是 NONE（design E21，收口在任务 4.2）⇒ "
        "「界面读路径」此时是回落到写入族的近似值，Property 2 的读回判据须改口径"
    )


def test_anchor_family_key_spaces_are_pairwise_disjoint() -> None:
    """16 张的族键空间两两不交 ⇒ 「同一底稿放 16 张」的作用域结论才可解读。

    判的是**前缀级**不交（``_fetch_by_prefix`` 用的是 ``LIKE '前缀%'``）：只要有一张的键
    落进另一张的前缀里，一次导入就会把别人的行捞进 ``stored`` 并可能删掉 —— 而那时
    P2-4 的失败原因会被误读成「夹具把 16 张塞进同一底稿」。
    """
    probe_indices = tuple(range(1, _MAX_SEED + 1)) + (99,)
    keys: dict[str, frozenset[str]] = {}
    for code in _codes():
        spec = _spec(code)
        keys[code] = _keys_for_indices(code, probe_indices) | frozenset(
            spec.standalone_item_ids
        )

    collisions: list[str] = []
    for code in _codes():
        spec = _spec(code)
        prefixes = _family_prefixes(spec)
        for other, other_keys in keys.items():
            if other == code:
                continue
            shared = sorted(k for k in other_keys if _belongs(spec, k))
            if shared:
                collisions.append(f"{other} 的键 {shared[:3]} 落在 {code} 的前缀 {prefixes} 内")
    assert not collisions, "族键空间交叠：\n  " + "\n  ".join(collisions)

    duplicated: list[str] = []
    for code, own in keys.items():
        for other, other_keys in keys.items():
            if other <= code:
                continue
            shared = sorted(own & other_keys)
            if shared:
                duplicated.append(f"{code} 与 {other} 共用键 {shared[:3]}")
    assert not duplicated, "族键重名：\n  " + "\n  ".join(duplicated)

    standalone_leak = [
        f"{code}: {iid}"
        for code in _codes()
        for iid in _spec(code).standalone_item_ids
        if _belongs(_spec(code), iid)
    ]
    assert not standalone_leak, (
        "表级独立键落在自己的族键空间内 ⇒ 一次归约会把用户写的调整说明/审计结论删掉，"
        f"且本文件的静态区判据会把它误算成「该动的行」：{standalone_leak}"
    )
    with_standalone = [c for c in _codes() if _spec(c).standalone_item_ids]
    assert len(with_standalone) == 3, (
        f"有表级独立键的 sheet 实测 {len(with_standalone)} 张（本轮基线 3 张）："
        f"{with_standalone} —— 数量变了说明清单 `standalone_item_ids` 被改，"
        f"P2-4 的「独立键零改动」witness 组须同步复核"
    )


def test_anchor_entry_type_field_never_shadows_a_column_field() -> None:
    """entryType 字段名不与任何列字段撞名 ⇒ materialize 时不会把列取值覆盖掉。"""
    clashes = [
        f"{code}: {_spec(code).entry_type_field}"
        for code in _codes()
        if _spec(code).entry_type_field in {k for k in _spec(code).field_keys if k}
    ]
    assert not clashes, (
        "entryType 字段名与列字段撞名 ⇒ 本文件 `_materialize` 的最后一行会静默覆盖那一列的"
        f"生成取值，「∀ 取值」这一维塌掉一列：{clashes}"
    )


def test_anchor_strategy_vocabulary_comes_from_truth_source() -> None:
    """策略取值面取自 ``ConflictStrategy`` 的 ``Literal``，且含实现门控用的那个值。"""
    values = _strategies()
    assert len(values) == 3, (
        f"平台冲突策略实测 {len(values)} 种 {values}（本轮基线 3 种）—— 新增策略必须"
        f"在 P2-3 里得到判据，否则新策略会带着未经判定的破坏性清理上线"
    )
    assert len(set(values)) == len(values), f"策略词表有重复：{values}"


def test_anchor_db_fixture_is_writable_and_monotonic() -> None:
    """夹具自检：``NOW()`` 替身生效、两个底稿的 16 张都预置到库、快照读到全部 10 列。"""
    hz = _hz()
    hz.reset()
    snap = hz.snapshot()
    assert snap, "预置后 `checklist_responses` 仍是空表 ⇒ 全部库态判据在空表上恒真"
    assert all(len(row) == len(_SNAPSHOT_COLUMNS) for row in snap), (
        f"快照列数与 `_SNAPSHOT_COLUMNS` 不符（{len(_SNAPSHOT_COLUMNS)} 列）"
    )
    wps = {row[_WP_COL] for row in snap}
    assert wps == set(hz.wp_ids), f"预置只落到 {sorted(wps)}，期望两个底稿 {list(hz.wp_ids)}"
    for code in _codes():
        for wp_id in hz.wp_ids:
            got = hz.family_keys(code, wp_id=wp_id)
            want = _keys_for_indices(code, _BASE_INDICES)
            assert got == want, (
                f"{code} @ {wp_id} 预置族键与生产函数派生集不符：缺 "
                f"{sorted(want - got)[:3]} / 多 {sorted(got - want)[:3]}"
            )

    # `NOW()` 替身单调：连写两次同一份内容，`updated_at` 必须前移
    code = _codes()[0]
    rows = _materialize_all(code, [_AbstractRow(tuple([None] * len(_face())), _canonical_entry_types()[0])])
    hz.write(code, rows, impl._STRATEGY_OVERWRITE)
    first = hz.snapshot()
    hz.write(code, rows, impl._STRATEGY_OVERWRITE)
    second = hz.snapshot()
    assert first != second, (
        "对同一份内容连写两次，整表快照逐字节相同 ⇒ `NOW()` 替身没生效或没被写进 "
        "`updated_at`，「零写入」判据会漏掉幂等 upsert 这一类"
    )
    hz.reset()


def test_anchor_seeded_item_ids_are_storable() -> None:
    """预置族键落在 ``item_id`` 列宽内（防夹具造出生产不可能存在的键）。"""
    limit = 64  # `checklist_responses.item_id` 列宽（迁移 V089 定为 VARCHAR(64)）
    too_long: list[str] = []
    for code in _codes():
        for item_id in _keys_for_indices(code, tuple(range(1, _MAX_SEED + 1))) | frozenset(
            _spec(code).standalone_item_ids
        ):
            if len(item_id) > limit:
                too_long.append(f"{code}: {item_id} ({len(item_id)} 字符)")
    assert not too_long, f"族键超出 item_id 列宽 {limit}：{too_long}"


def test_anchor_seed_readback_matches_leading_run() -> None:
    """预置态**真的**能被界面读路径读出预期行数 ⇒ 「n < 库中现有行数」不是虚构的边界。

    这是本文件最要紧的一条反空转锚点：若预置根本读不出行，「写 n 行后读回 n 行」会退化成
    「反正都读不出多余的行」。三族的预期行数按 ``_expected_seed_readback`` 分推
    （逐字段族 / 整行 JSON 族看**连续前缀**，整表单键族看数组长度 —— 模块 docstring 实测 1）。
    """
    hz = _hz()
    hz.reset()
    seen: dict[str, set[Any]] = {"kinds": set(), "runs": set(), "holes": set()}

    @given(plan=_arb_seed())
    @_SETTINGS
    def prop(plan: _SeedPlan) -> None:
        seen["kinds"].add(plan.kind)
        seen["holes"].add(bool(plan.indices) and _leading_run(plan.indices) < len(plan.indices))
        for code in _codes():
            hz.seed(code, plan.indices)
            want = _expected_seed_readback(code, plan.indices)
            seen["runs"].add(want)
            got = len(hz.readback(code))
            assert got == want, (
                f"{code}（{_spec(code).key_family.value} / 读回族 "
                f"{_spec(code).read_family.value}）预置行号 {list(plan.indices)} 后界面读回 "
                f"{got} 行，期望 {want} 行 ⇒ 预置形态与实现的读回口径分叉，"
                f"本文件「n < 库中现有行数」这一边界失去意义"
            )

    prop()
    assert seen["kinds"] == {"prefix", "sparse"}, f"种子形态未全覆盖：{seen['kinds']}"
    assert True in seen["holes"], "从未生成过带空洞的预置 ⇒ 断档读回那一维是空转"
    assert 0 in seen["runs"] and max(seen["runs"]) >= 3, (
        f"预置读回行数覆盖面不足：{sorted(seen['runs'])}（需含 0 与 ≥3）"
    )
    hz.reset()


# ═══════════════════════════════════════════════════════════════════════════
# 6. Property 2 —— 保行数
# ═══════════════════════════════════════════════════════════════════════════


def test_p2_1_readback_row_count_equals_n() -> None:
    """∀ 16 张 × ∀ 目标行数 n × ∀ 预置态 × ∀ 取值：``overwrite`` 落库后界面读回恰 n 行。

    量化的是 Property 2 的前半句「界面读路径读回的行数恰为 n」。判据同时钉住两侧：

    * ``load_rows`` 返回的行数 == n（界面读路径 —— R6.5 / R6.6）
    * ``write_rows`` 自报的 ``written_count`` == n（自报值与库态不符时能分辨是哪一侧错）

    n 与「库中现有行数」的相对位置（``<`` / ``==`` / ``>``）由生成器铺开并在跑完后自证。

    **Validates: Requirements 2.5, 6.5, 6.6**
    """
    hz = _hz()
    hz.reset()
    width = len(_face())
    seen: dict[str, set[Any]] = {
        "n": set(),
        "kinds": set(),
        "families": set(),
        "relation": set(),
        "cells": set(),
    }

    @given(rows=_arb_rows(width), plan=_arb_seed())
    @_SETTINGS
    def prop(rows: list[_AbstractRow], plan: _SeedPlan) -> None:
        n = len(rows)
        seen["n"].add(n)
        seen["kinds"].add(plan.kind)
        for row in rows:
            for cell in row.cells:
                seen["cells"].add(_cell_class(cell))
        for code in _codes():
            spec = _spec(code)
            seen["families"].add(spec.key_family.value)
            hz.seed(code, plan.indices)
            existing = len(hz.readback(code))
            seen["relation"].add("<" if n < existing else ("==" if n == existing else ">"))

            outcome = hz.write(code, _materialize_all(code, rows), impl._STRATEGY_OVERWRITE)
            assert outcome.written_count == n, (
                f"{code}: `write_rows` 自报写入 {outcome.written_count} 行，实为 {n} 行"
            )
            got = len(hz.readback(code))
            assert got == n, (
                f"{code}（{spec.key_family.value} / 读回族 {spec.read_family.value}）"
                f"预置行号 {list(plan.indices)}（界面原可读 {existing} 行）后写入 {n} 行，"
                f"界面读回 {got} 行 —— 多出的是幽灵行、少掉的是被误删的行。"
                f"库中族键 {sorted(hz.family_keys(code))[:4]}…"
            )

    prop()
    assert 0 in seen["n"], "从未生成过 n = 0（任务明确要求覆盖该边界）"
    assert max(seen["n"]) >= 3, f"目标行数上界只到 {max(seen['n'])}"
    assert seen["kinds"] == {"prefix", "sparse"}, f"种子形态未全覆盖：{seen['kinds']}"
    assert len(seen["families"]) == 3, f"三族未全覆盖：{sorted(seen['families'])}"
    assert seen["relation"] == {"<", "==", ">"}, (
        f"n 与库中现有行数的相对位置未全覆盖：{sorted(seen['relation'])}"
        f"（缺 '<' 就等于没覆盖任务要求的「n < 库中现有行数」边界）"
    )
    assert len(seen["cells"]) >= 6, f"取值类别只命中 {sorted(seen['cells'])}"
    hz.reset()


def _cell_class(cell: Any) -> str:
    """取值类别（只给覆盖面自证用）。"""
    if cell is None:
        return "none"
    if cell == "":
        return "empty"
    if isinstance(cell, bool):
        return "bool"
    if isinstance(cell, int):
        return "int"
    if isinstance(cell, float):
        return "float-small" if abs(cell) <= 1e-6 else "float"
    if any("\u4e00" <= ch <= "\u9fff" for ch in str(cell)):
        return "chinese"
    if any(ch in "，。（）%&#@!?+-*/_|^$<>[]{}~`'\"\\" for ch in str(cell)):
        return "special"
    return "plain"


# ═══════════════════════════════════════════════════════════════════════════
# 7. Property 2 —— 无幽灵残留（落库键集恰等于爆炸集）
# ═══════════════════════════════════════════════════════════════════════════


def test_p2_2_stored_key_set_is_exactly_the_exploded_family() -> None:
    """∀ 16 张 × ∀ n × ∀ 预置态：库中族键集合**恰**等于「行 1..n × 全部登记后缀」。

    量化 Property 2 的后半句「不存在索引大于 n 的残留键」，并把同一判据的另外三个方向
    一并钉住 —— 它们都是「集合相等」的直接推论，却各自对应一类真实缺陷：

    * 多出行号 > n 的键 ⇒ **幽灵残留**（归约没做或做漏）
    * 少掉行号 ≤ n 的键 ⇒ **误删刚导入的行**（off-by-one）
    * 某行少掉某个后缀 ⇒ **爆炸不完备**（如 ``ociBlock`` 那一张多出来的后缀被写死的
      全局后缀表吞掉；``per_field_plus_data`` 的整行 JSON 族没写 ⇒ R6.6 的界面读不到）
    * 出现行号空洞 ⇒ 界面读回会在断档处截断（读回族「从 1 连续取到断档为止」）

    整表单键 JSON 族按族形态分推：键集恒为那一个键，行数落在**数组长度**上（实测 2）。

    另判 ``removed_item_ids`` **精确等于**「预置键集 − 爆炸集」—— 不只判「非空」：
    多删一个就是删用户数据，少删一个就是幽灵行。

    **Validates: Requirements 2.5, 6.5, 6.6, 11.7**
    """
    hz = _hz()
    hz.reset()
    width = len(_face())
    seen: dict[str, set[Any]] = {"n": set(), "removed": set(), "families": set()}

    @given(rows=_arb_rows(width), plan=_arb_seed())
    @_SETTINGS
    def prop(rows: list[_AbstractRow], plan: _SeedPlan) -> None:
        n = len(rows)
        seen["n"].add(n)
        for code in _codes():
            spec = _spec(code)
            seen["families"].add(spec.key_family.value)
            hz.seed(code, plan.indices)
            seeded = _keys_for_indices(code, plan.indices)

            outcome = hz.write(code, _materialize_all(code, rows), impl._STRATEGY_OVERWRITE)
            want_keys = _exploded_keys(code, n)
            got_keys = hz.family_keys(code)
            assert got_keys == want_keys, (
                f"{code}（{spec.key_family.value}）预置行号 {list(plan.indices)} 后写入 {n} 行，"
                f"库中族键与爆炸集不符：\n"
                f"  多出（幽灵残留 / 越界键）={sorted(got_keys - want_keys)[:6]}\n"
                f"  缺失（爆炸不完备 / 误删）={sorted(want_keys - got_keys)[:6]}"
            )

            expected_removed = frozenset(seeded) - want_keys
            if _is_single(spec):
                expected_removed = frozenset()
            got_removed = frozenset(outcome.removed_item_ids)
            seen["removed"].add(len(got_removed))
            assert got_removed == expected_removed, (
                f"{code}: `removed_item_ids` 与「预置键集 − 爆炸集」不符：\n"
                f"  多删={sorted(got_removed - expected_removed)[:6]}"
                f"（删的是行号 ≤ {n} 的键或别处的键 = 删用户数据）\n"
                f"  少删={sorted(expected_removed - got_removed)[:6]}（= 幽灵残留）"
            )

            if _is_single(spec):
                array = hz.single_json_array(code)
                assert isinstance(array, list), (
                    f"{code} 整表单键族的库值解析不出数组：{array!r}"
                )
                assert len(array) == n, (
                    f"{code}（整表单键 JSON 族）写入 {n} 行后库中数组长 {len(array)} —— "
                    f"这一族的幽灵行形态就是数组里多出的元素（无行号可判）"
                )
            else:
                indices = {
                    idx
                    for key in got_keys
                    for idx in (_index_of(spec, key),)
                    if idx is not None
                }
                assert indices == set(range(1, n + 1)), (
                    f"{code} 库中族键行号集 {sorted(indices)} != {{1..{n}}} ⇒ "
                    f"有空洞或有越界行号（界面读回会在断档处截断）"
                )

    prop()
    assert 0 in seen["n"], "从未生成过 n = 0"
    assert len(seen["families"]) == 3, f"三族未全覆盖：{sorted(seen['families'])}"
    assert max(seen["removed"]) > 0, (
        "`removed_item_ids` 全程为空 ⇒ 归约通路一次也没触发，"
        "「无幽灵残留」的结论只是因为库里从来没有过越界键"
    )
    hz.reset()


def _index_of(spec: Any, item_id: str) -> int | None:
    """从族键抠行号 —— 走生产函数 ``_row_index_from_key``（不复制第二份解析式子）。"""
    if spec.data_key_prefix is not None and spec.data_key_suffix is not None:
        idx = impl._row_index_from_key(item_id, spec.data_key_prefix, spec.data_key_suffix)
        if idx is not None:
            return idx
    if spec.per_field_prefix is not None:
        return impl._row_index_from_key(item_id, spec.per_field_prefix, None)
    return None


# ═══════════════════════════════════════════════════════════════════════════
# 8. Property 2 —— 清理只在 overwrite 下生效（R11.7 的破坏性门控）
# ═══════════════════════════════════════════════════════════════════════════


def test_p2_3_purge_happens_only_under_overwrite() -> None:
    """∀ 策略 × ∀ 16 张 × ∀ n < 库中现有行数：只有 ``overwrite`` 允许删越界族键。

    这是 R11.7 在**库态**上的量化。GS1 已判「``_should_purge_residual`` 的返值真值表」与
    「``write_rows`` 体内调了它」；本条判的是**结果有没有被用上** —— 一次
    ``if _should_purge_residual(...) or True:`` 能让 GS1 那两条全绿，而库里用户已编制的行
    会被 ``fill-empty`` 静默删掉。

    * ``overwrite`` ⇒ 越界族键必须**全部消失**（正面对照，防「反正都没删」）
    * **任何非 ``overwrite`` 的策略** ⇒ 分两支，都不许删越界键：
      · 整表拒收（抛异常）⇒ 库态**逐行逐列不变**
      · 放行（不抛）⇒ ``removed_item_ids`` 为空 **且**越界族键逐个存活

    🔴 判据刻意**不按策略名分支**（只认实现自己的门控常量 ``_STRATEGY_OVERWRITE``）：
    「哪一种策略会抛」是平台 ``conflict_resolver`` 的内部约定，写进判据等于把它复制第二份；
    而「非 overwrite 一律不许删」才是 R11.7 的原话。这样平台若新增第四种策略，本条自动
    覆盖它 —— 策略取值面取自 ``ConflictStrategy`` 的 ``Literal``。

    实测 3 的分叉（逐字段族在 ``n = 0`` + 拒收策略下**不抛**、整表单键族抛）因此不再是判据
    前提，只作为「两支都要跑到」的覆盖面自证；``n = 0`` × 每一种策略由 ``@example`` 钉住，
    不靠随机命中（首版靠随机 ⇒ 「不抛」那支 100 例一次没中，覆盖面自证直接假红）。

    **Validates: Requirements 11.7, 2.5**
    """
    from app.services.bulk_tab.conflict_resolver import ConflictRejected

    hz = _hz()
    hz.reset()
    width = len(_face())
    seen: dict[str, set[Any]] = {
        "strategies": set(),
        "branches": set(),
        "families": set(),
        "n": set(),
    }

    def _pin_zero_row_examples(fn: Any) -> Any:
        """把「n = 0 × 每一种策略」钉成 ``@example`` —— 策略名从真源取，不写字面量。"""
        for strategy in _strategies():
            fn = example(rows=[], strategy=strategy, seed_len=1)(fn)
        return fn

    @given(
        rows=_arb_rows(width),
        strategy=st.sampled_from(_strategies()),
        seed_len=st.integers(min_value=1, max_value=_MAX_SEED),
    )
    @_SETTINGS
    @_pin_zero_row_examples
    def prop(rows: list[_AbstractRow], strategy: str, seed_len: int) -> None:
        n = min(len(rows), seed_len)
        rows = rows[:n]
        seen["strategies"].add(strategy)
        seen["n"].add(n)
        indices = tuple(range(1, seed_len + 1))
        for code in _codes():
            spec = _spec(code)
            seen["families"].add(spec.key_family.value)
            hz.seed(code, indices)
            seeded = _keys_for_indices(code, indices)
            residual = frozenset(seeded) - _exploded_keys(code, n)
            before = hz.snapshot()

            raised: Exception | None = None
            outcome = None
            try:
                outcome = hz.write(code, _materialize_all(code, rows), strategy)
            except ConflictRejected as exc:
                raised = exc

            if strategy == impl._STRATEGY_OVERWRITE:
                seen["branches"].add((strategy, "purged"))
                assert raised is None, f"{code}: overwrite 不该抛 {raised!r}"
                survivors = sorted(residual & hz.family_keys(code))
                assert not survivors, (
                    f"{code}: overwrite 下行号 > {n} 的族键仍在库里 {survivors[:6]} ⇒ "
                    f"幽灵行（正面对照失败：本条其余分支的「没删」因此不可归因）"
                )
            elif raised is not None:
                seen["branches"].add((strategy, "rejected"))
                assert hz.snapshot() == before, (
                    f"{code}: strategy={strategy!r} 整表拒收（{type(raised).__name__}）"
                    f"却改动了库态 —— 拒收的语义是不部分写入："
                    f"{_delta(before, hz.snapshot())}"
                )
            else:
                seen["branches"].add((strategy, "kept"))
                assert outcome is not None and not outcome.removed_item_ids, (
                    f"{code}: strategy={strategy!r} 自报清理了 "
                    f"{list(outcome.removed_item_ids)[:6]} ⇒ 破坏性清理越出 "
                    f"{impl._STRATEGY_OVERWRITE!r}（R11.7）"
                )
                dead = sorted(residual - hz.family_keys(code))
                assert not dead, (
                    f"{code}: strategy={strategy!r} 下行号 > {n} 的族键被删了 {dead[:6]} ⇒ "
                    f"非 overwrite 策略执行了破坏性清理，用户已编制的第 {n + 1} 行起被静默删除。"
                    f"快照差：{_delta(before, hz.snapshot())}"
                )

    prop()
    assert seen["strategies"] == set(_strategies()), (
        f"策略未全覆盖：实测 {sorted(seen['strategies'])} / 词表 {sorted(_strategies())}"
    )
    non_overwrite = {s for s in _strategies() if s != impl._STRATEGY_OVERWRITE}
    outcomes = {branch for strategy, branch in seen["branches"] if strategy != impl._STRATEGY_OVERWRITE}
    assert outcomes == {"rejected", "kept"}, (
        f"非 overwrite 的两支未全覆盖：{sorted(outcomes)} —— 少「rejected」= 拒收通路空转，"
        f"少「kept」= 「放行但不清理」这一支空转（实测 3 的分叉正落在这里）"
    )
    touched = {strategy for strategy, _branch in seen["branches"]}
    assert touched == set(_strategies()), (
        f"策略分支未全命中：{sorted(touched)} / 词表 {sorted(_strategies())}"
        f"（非 overwrite 策略 {sorted(non_overwrite)}）"
    )
    assert len(seen["families"]) == 3, f"三族未全覆盖：{sorted(seen['families'])}"
    assert 0 in seen["n"], "从未生成过 n = 0"
    hz.reset()


# ═══════════════════════════════════════════════════════════════════════════
# 9. Property 2 —— 清理作用域由 (wp_id, 族前缀) 双重限定
# ═══════════════════════════════════════════════════════════════════════════


def test_p2_4_purge_scope_is_double_limited_by_wp_and_prefix() -> None:
    """∀ 16 张 × ∀ n：一次导入只许动「本底稿 × 本 sheet 族键空间」，别的一行都不许碰。

    静态区 = 整表快照减去「``wp_id == 目标底稿`` 且 ``item_id`` 落在本 sheet 族键空间」的行，
    它同时含三组 witness（每组都在断言里单独核过非空）：

    * **另一个底稿**的同 sheet 族键（同名 ``item_id``、不同 ``wp_id``）—— 抓
      ``DELETE`` 丢掉 ``wp_id`` 过滤这一类：那会跨底稿删数据，而 ``removed_item_ids``
      看起来完全正常
    * **同底稿的别的 15 张** sheet 的族键 —— 抓前缀限定失效（LIKE 模式变宽）
    * 本 sheet 的**表级独立键** —— 抓「调整说明 / 审计说明 / 审计结论被当行数据删掉」

    判据是逐行逐列（含 ``created_at`` / ``updated_at``）比对：``NOW()`` 替身单调 ⇒ 连
    「只把静态区的行 upsert 了一遍」也会被抓到。

    **Validates: Requirements 11.7, 6.6**
    """
    hz = _hz()
    hz.reset()
    width = len(_face())
    seen: dict[str, set[Any]] = {"n": set(), "witness": set()}

    @given(rows=_arb_rows(width), plan=_arb_seed())
    @_SETTINGS
    def prop(rows: list[_AbstractRow], plan: _SeedPlan) -> None:
        n = len(rows)
        seen["n"].add(n)
        for code in _codes():
            spec = _spec(code)
            hz.seed(code, plan.indices)
            before = hz.snapshot()
            static_before = _static_region(before, code, _WP_TARGET)

            bystander = [
                row for row in static_before if row[_WP_COL] == _WP_BYSTANDER and _belongs(spec, row[_ITEM_COL])
            ]
            others = [
                row
                for row in static_before
                if row[_WP_COL] == _WP_TARGET and not _belongs(spec, row[_ITEM_COL])
            ]
            assert bystander, (
                f"{code}: 静态区里没有另一个底稿的同 sheet 族键 ⇒ 「跨底稿越界」这一维空转"
            )
            assert others, f"{code}: 静态区里没有本底稿其它键 ⇒ 「跨 sheet 越界」这一维空转"
            seen["witness"].add("bystander")
            seen["witness"].add("other-sheets")
            standalone_rows = [
                row for row in others if row[_ITEM_COL] in set(spec.standalone_item_ids)
            ]
            if spec.standalone_item_ids:
                assert standalone_rows, f"{code}: 表级独立键未落进静态区"
                seen["witness"].add("standalone")

            hz.write(code, _materialize_all(code, rows), impl._STRATEGY_OVERWRITE)

            static_after = _static_region(hz.snapshot(), code, _WP_TARGET)
            assert static_after == static_before, (
                f"{code}: 写 {n} 行（预置行号 {list(plan.indices)}）时动了作用域以外的行 —— "
                f"R11.7 要求作用域由 (wp_id, item_id 前缀) 双重限定。"
                f"静态区差异：{_delta(static_before, static_after)}"
            )

    prop()
    assert 0 in seen["n"], "从未生成过 n = 0"
    assert seen["witness"] == {"bystander", "other-sheets", "standalone"}, (
        f"三组 witness 未全命中：{sorted(seen['witness'])}"
    )
    hz.reset()


# ═══════════════════════════════════════════════════════════════════════════
# 10. Property 2 —— 两个边界的显式量化（n = 0 与 n < 库中现有行数）
# ═══════════════════════════════════════════════════════════════════════════


def test_p2_5_boundaries_n_zero_and_n_below_existing() -> None:
    """两个边界**独立成条**，不靠上面几条的随机命中（任务对本任务的硬要求）。

    * **n = 0**：库里原有 k ≥ 1 行 ⇒ 读回 0 行；逐字段族与整行 JSON 族的族键**一个不剩**、
      整表单键族剩那一个键但数组为空；``removed_item_ids`` 恰等于原有全部族键。
      这是最容易被 off-by-one 或「空列表提前 return」放过的一档：
      ``rows == []`` 时 ``incoming`` 也是空的，一个「没有要写的就直接返回」的实现会让
      整批旧行原地不动 —— 接口仍 200、``imported_count`` 仍 0。
    * **n < 库中现有行数**：读回恰 n 行，且行号 > n 的族键全消失。

    **Validates: Requirements 2.5, 6.5, 6.6, 11.7**
    """
    hz = _hz()
    hz.reset()
    width = len(_face())
    seen: dict[str, set[Any]] = {"zero": set(), "below": set(), "gaps": set()}

    # 🔴 `rows` 在本条**必须非空**：边界 2 要写 `n = min(len(rows), existing - 1)` 行，
    # 而 `rows` 为空时 `rows[:n]` 恒为空列表 —— 首版按 `or 1` 兜了个 n=1 却仍写 0 行，
    # 被 hypothesis 一击命中（`rows=[] / seed_len=2` ⇒ 期望读回 1 行、实测 0 行）。
    # 边界 1 的 n = 0 是显式传 `[]`，不从 `rows` 取，故 `min_size=1` 不影响它。
    @given(
        rows=st.lists(_arb_row(width), min_size=1, max_size=_MAX_ROWS),
        seed_len=st.integers(min_value=1, max_value=_MAX_SEED),
        drop=st.booleans(),
    )
    @_SETTINGS
    def prop(rows: list[_AbstractRow], seed_len: int, drop: bool) -> None:
        # 预置一定非空（边界的定义要求「库中现有行数 ≥ 1」）；`drop` 让预置带一个空洞
        indices = tuple(range(1, seed_len + 1))
        if drop and seed_len >= 3:
            indices = tuple(i for i in indices if i != seed_len - 1)
        seen["gaps"].add(_leading_run(indices) < len(indices))

        for code in _codes():
            spec = _spec(code)
            seeded = _keys_for_indices(code, indices)

            # ── 边界 1：n = 0 ────────────────────────────────────────────
            hz.seed(code, indices)
            existing = len(hz.readback(code))
            assert existing >= 1, f"{code}: 预置 {list(indices)} 却读回 0 行，边界前提不成立"
            outcome = hz.write(code, [], impl._STRATEGY_OVERWRITE)
            assert len(hz.readback(code)) == 0, (
                f"{code}: n = 0 落库后界面仍读回 "
                f"{len(hz.readback(code))} 行 ⇒ 整批旧行没被归约掉（幽灵行）"
            )
            if _is_single(spec):
                assert hz.single_json_array(code) == [], (
                    f"{code}: n = 0 后整表单键族数组仍为 {hz.single_json_array(code)!r}"
                )
                assert not outcome.removed_item_ids, (
                    f"{code}: 整表单键族无残留概念，却自报清理了 {list(outcome.removed_item_ids)}"
                )
            else:
                left = hz.family_keys(code)
                assert not left, f"{code}: n = 0 后仍剩族键 {sorted(left)[:6]}"
                assert frozenset(outcome.removed_item_ids) == frozenset(seeded), (
                    f"{code}: n = 0 的清理面与原有族键集不符："
                    f"多删 {sorted(frozenset(outcome.removed_item_ids) - seeded)[:4]} / "
                    f"少删 {sorted(seeded - frozenset(outcome.removed_item_ids))[:4]}"
                )
            seen["zero"].add(code)

            # ── 边界 2：n < 库中现有行数（n ≥ 1）────────────────────────
            hz.seed(code, indices)
            existing = len(hz.readback(code))
            if existing < 2:
                continue
            n = min(len(rows), existing - 1)
            assert 1 <= n < existing, (
                f"{code}: 边界 2 的 n={n} 未落在 [1, {existing}) 内 ⇒ 本轮量化的不是"
                f"「n < 库中现有行数」这个边界（生成器约束失效）"
            )
            outcome = hz.write(
                code, _materialize_all(code, rows[:n]), impl._STRATEGY_OVERWRITE
            )
            got = len(hz.readback(code))
            assert got == n, (
                f"{code}: 库中原可读 {existing} 行、写入 {n} 行（n < 现有行数）后读回 {got} 行"
            )
            over = sorted(k for k in hz.family_keys(code) if (_index_of(spec, k) or 0) > n)
            assert not over, f"{code}: 归约后仍有行号 > {n} 的残留键 {over[:6]}"
            seen["below"].add((code, n, existing))

    prop()
    assert set(seen["zero"]) == set(_codes()), (
        f"n = 0 边界未覆盖全部 16 张：缺 {sorted(set(_codes()) - set(seen['zero']))}"
    )
    covered = {code for code, _n, _e in seen["below"]}
    assert covered == set(_codes()), (
        f"n < 现有行数 边界未覆盖全部 16 张：缺 {sorted(set(_codes()) - covered)}"
    )
    assert seen["gaps"] == {True, False}, f"带空洞 / 不带空洞的预置未全覆盖：{seen['gaps']}"
    hz.reset()


# ═══════════════════════════════════════════════════════════════════════════
# 11. 端点侧行为锚点 + 反向自检
# ═══════════════════════════════════════════════════════════════════════════


def test_anchor_import_endpoint_forwards_strategy() -> None:
    """行为锚点：``import-data`` 端点把 ``strategy`` 真的透传到了归约门控。

    上面几条属性直调 ``write_rows``（Property 2 的量化对象就是「爆炸 → 落库 → 归约」这条
    管道）。但若端点把 ``strategy`` 吞掉、恒按默认值走，用户在界面上选的
    「只填空位」就会变成「覆盖并删行」，而所有直调判据仍全绿。故此处走一遍真实
    HTTP 通路：同一份「1 行」的上传文件，在三种传法下库态必须分叉。

    ``fill-empty`` 与「缺省不传」的对照，也顺带证明了端点默认值确实是 ``overwrite``
    （GS6 判的是「剥掉 ``Query`` 包装后是个非空 ``str``」，不判它到底等于哪个词）。
    """
    hz = _hz()
    hz.reset()
    indices = (1, 2, 3)
    checked = 0
    for code in _codes():
        spec = _spec(code)
        if _is_single(spec):
            continue  # 整表单键族无残留概念（门控对它恒为 False，已由 P2-3 覆盖）
        residual = _keys_for_indices(code, indices) - _exploded_keys(code, 1)
        assert residual, f"{code}: 预置 {list(indices)} 保留 1 行却算不出越界键"
        payload = _upload_bytes(code, 1)

        hz.seed(code, indices)
        reply = hz.post(code, "import-data", params={"sheet": code, "strategy": "fill-empty"}, content=payload)
        assert reply.status == 200 and reply.body.get("ok") is True, (
            f"{code}: fill-empty 导入未成功：{reply.status} / {reply.body!r}"
        )
        dead = sorted(residual - hz.family_keys(code))
        assert not dead, (
            f"{code}: 端点带 strategy=fill-empty 却删了越界键 {dead[:6]} ⇒ "
            f"策略没透传到 `_should_purge_residual`（用户选「只填空位」被当成覆盖）"
        )

        hz.seed(code, indices)
        reply = hz.post(code, "import-data", params={"sheet": code, "strategy": impl._STRATEGY_OVERWRITE}, content=payload)
        assert reply.status == 200 and reply.body.get("ok") is True, (
            f"{code}: overwrite 导入未成功：{reply.status} / {reply.body!r}"
        )
        alive = sorted(residual & hz.family_keys(code))
        assert not alive, (
            f"{code}: 端点带 strategy=overwrite 却留下越界键 {alive[:6]} ⇒ "
            f"归约在 HTTP 通路上没接通（直调判据的绿是假绿）"
        )

        hz.seed(code, indices)
        reply = hz.post(code, "import-data", params={"sheet": code}, content=payload)
        assert reply.status == 200 and reply.body.get("ok") is True, (
            f"{code}: 缺省 strategy 导入未成功：{reply.status} / {reply.body!r}"
        )
        alive = sorted(residual & hz.family_keys(code))
        assert not alive, (
            f"{code}: 端点缺省 strategy 时未清理越界键 {alive[:6]} ⇒ "
            f"缺省值不是 {impl._STRATEGY_OVERWRITE!r}（与实现自己的门控常量分叉）"
        )
        checked += 1

    assert checked == 11, (
        f"端点锚点只覆盖了 {checked} 张非整表单键族 sheet（本轮基线 11 张）"
    )
    hz.reset()


def test_reverse_selfcheck_probe_marker_absent_from_truth_sources() -> None:
    """反向自检：探针记号不出现在任何真源取值里（证明判据不是在跟自己的合成值绕圈）。"""
    assert _MARK not in _CONTRACT.read_text(encoding="utf-8"), (
        f"探针记号 {_MARK!r} 出现在契约清单里 ⇒ 预置值与真源取值可能互相污染"
    )
    for code in _codes():
        spec = _spec(code)
        surface: Iterable[str] = (
            (code, spec.sheet_name, spec.item_id, spec.entry_type_field)
            + tuple(spec.per_field_suffixes)
            + tuple(spec.standalone_item_ids)
            + tuple(k for k in spec.field_keys if k)
        )
        polluted = [s for s in surface if _MARK in s]
        assert not polluted, f"{code}: 真源取值里含探针记号 {polluted}"


def test_reverse_selfcheck_readback_count_is_not_constant() -> None:
    """反向自检：``load_rows`` 的返回行数**真的**随库态变化。

    P2-1 / P2-5 全靠「读回行数 == n」。若 ``load_rows`` 在本夹具下恒返同一个数
    （例如取数走不通、永远返空），那些判据只会在 n 恰等于那个常数时绿、其余全红 ——
    但一个「恒返 0 且写入也恒失败」的组合能让它们全绿。这里正面钉住：
    同一张 sheet 在 0 / 1 / 3 行三种库态下，读回行数必须是三个不同的值。
    """
    hz = _hz()
    hz.reset()
    for code in _codes():
        got = []
        for n in (0, 1, 3):
            hz.seed(code, tuple(range(1, n + 1)))
            got.append(len(hz.readback(code)))
        assert got == [0, 1, 3], (
            f"{code}: 预置 0/1/3 行时界面读回 {got}（期望 [0, 1, 3]）⇒ "
            f"读回口径与预置形态分叉，本文件的行数判据不可解读"
        )
    hz.reset()
