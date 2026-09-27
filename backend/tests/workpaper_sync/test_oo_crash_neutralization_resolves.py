# -*- coding: utf-8 -*-
"""平台级守卫：`oo_crash_neutralization_fn` **声明 ⇔ 运行时解析得到**。

spec: `h2-h6-h10-pilot-cross-reference-lanes`（H 收口时实测发现解析恒空）

═══ 这条判据为什么必须存在 ═══════════════════════════════════════════════════════

`store_item_registry` 里每条需要 OO 加载期崩溃缓解的 adapter 都声明
`oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas"`。但该函数**只定义在**
`g7_oo_crash_if_neutralize`，原解析实现只查 provider 模块并 `getattr(..., None)`
软跳过 ⇒ 实测 **21 条声明里 20 条解析结果是 None**（G 循环 11 条 + H 循环 9 条），
中性化从未执行，而注册表、契约、类型门、既有判据**全绿**。

带裸 `IF(` 的册子在 OnlyOffice 9.4 加载期崩（`editor_error_-82`，用户看到打开就白屏）。
最重的一册 `H1 固定资产.xlsx` 有 496 个含 IF 公式格。

⇒ 「声明了」和「真能调到」之间必须有一条判据。本文件就是那条。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync.oo_crash_neutralization import (  # noqa: E402
    OO_CRASH_FN_DEFINING_MODULE,
    OoCrashNeutralizationFnUnresolvedError,
    resolve_oo_crash_neutralization_fn,
)
from app.services.workpaper_sync.store_item_registry import (  # noqa: E402
    STORE_MERGE_REGISTRY,
)

#: 现算：声明了中性化的 adapter_id（**不写死名单** —— 每条新 entry 交付都会变）。
_DECLARED = tuple(
    sorted(a for a, p in STORE_MERGE_REGISTRY.items() if p.oo_crash_neutralization_fn)
)
_UNDECLARED = tuple(
    sorted(a for a, p in STORE_MERGE_REGISTRY.items() if not p.oo_crash_neutralization_fn)
)


def test_the_declared_set_is_not_empty() -> None:
    """自检前提：分母非空。为空说明注册表读取出错，下面的参数化会静默全过。"""
    assert _DECLARED, "声明集为空 —— 注册表解析失败，本文件所有判据会变成空转"


@pytest.mark.parametrize("adapter_id", _DECLARED)
def test_declared_neutralization_fn_actually_resolves(adapter_id: str) -> None:
    """🔴 核心：**声明了就必须解析得到可调用对象**。

    原缺陷正是这里 —— 声明齐全而解析恒 `None`。
    """
    fn = resolve_oo_crash_neutralization_fn(adapter_id)
    assert fn is not None, (
        f"{adapter_id}: 声明了 oo_crash_neutralization_fn 但解析不到 —— "
        "中性化会被静默跳过，带裸 IF( 的册子在 OO 9.4 加载期崩"
    )
    assert callable(fn), f"{adapter_id}: 解析结果不可调用 {fn!r}"


@pytest.mark.parametrize("adapter_id", _UNDECLARED)
def test_undeclared_adapters_resolve_to_none(adapter_id: str) -> None:
    """未声明 ⇒ 必须返回 `None`（语义「这家不需要中性化」），**不得**抛错。

    这半边同样要守：若把 fail-closed 写成「一律要求能解析」，D/E/F 那批不需要中性化的
    adapter 会全部打红，修的人就会把 fail-closed 整个拿掉 —— 缺陷复发。
    """
    assert resolve_oo_crash_neutralization_fn(adapter_id) is None


def test_unknown_adapter_id_resolves_to_none() -> None:
    """未注册的 adapter_id ⇒ `None`（回方向对非 adapter 输入的既有软跳过语义不变）。"""
    assert resolve_oo_crash_neutralization_fn("nope.not-registered") is None


def test_defining_module_really_exports_the_function() -> None:
    """回落终点必须真的有这个符号 —— 否则回落分支是死路。"""
    import importlib

    mod = importlib.import_module(OO_CRASH_FN_DEFINING_MODULE)
    assert callable(getattr(mod, "neutralize_oo_crash_if_formulas", None)), (
        f"{OO_CRASH_FN_DEFINING_MODULE} 未导出 neutralize_oo_crash_if_formulas"
    )


def test_fail_closed_when_the_declared_name_does_not_exist(monkeypatch) -> None:
    """🔴 fail-closed 判据：声明一个不存在的函数名 ⇒ **抛**，不得静默返回 None。

    原实现在这种情形下返回 `None`（软跳过），于是「函数名写错」与「这家不需要中性化」
    在观测面上一模一样 —— 这正是本缺陷能活下来的形态。
    """
    from dataclasses import replace

    from app.services.workpaper_sync import oo_crash_neutralization as M

    victim = _DECLARED[0]
    broken = dict(STORE_MERGE_REGISTRY)
    broken[victim] = replace(
        STORE_MERGE_REGISTRY[victim],
        oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas_TYPO",
    )
    monkeypatch.setattr(
        "app.services.workpaper_sync.store_item_registry.STORE_MERGE_REGISTRY", broken
    )
    with pytest.raises(OoCrashNeutralizationFnUnresolvedError) as ei:
        M.resolve_oo_crash_neutralization_fn(victim)
    # 错误消息必须可归因：带 adapter_id、函数名、两个候选模块
    msg = str(ei.value)
    assert victim in msg and "TYPO" in msg
    assert STORE_MERGE_REGISTRY[victim].provider_module in msg


def test_dropping_the_defining_module_fallback_would_false_green(monkeypatch) -> None:
    """🔴 变异判据：把回落终点指向一个**没有**该符号的模块 ⇒ 必须打红。

    证明「回落到唯一定义模块」这一步真的在承重 —— 若哪天有人把它删了想着
    「各 provider 自己 re-export 就好」，这条会立刻报出来。
    """
    from app.services.workpaper_sync import oo_crash_neutralization as M

    monkeypatch.setattr(
        M, "OO_CRASH_FN_DEFINING_MODULE", "app.services.workpaper_sync.limits"
    )
    # provider 侧自带 re-export 的那家（G7）不受影响；靠回落的那些必须抛
    relying_on_fallback = [
        a
        for a in _DECLARED
        if not _provider_exports(a, STORE_MERGE_REGISTRY[a].oo_crash_neutralization_fn)
    ]
    assert relying_on_fallback, (
        "没有任何 adapter 依赖回落分支 —— 说明 21 家都自己 re-export 了，"
        "那本变异判据的前提已变，需要重新表达（不是放宽）"
    )
    for adapter_id in relying_on_fallback:
        with pytest.raises(OoCrashNeutralizationFnUnresolvedError):
            M.resolve_oo_crash_neutralization_fn(adapter_id)


def _provider_exports(adapter_id: str, fn_name: str) -> bool:
    import importlib

    plan = STORE_MERGE_REGISTRY[adapter_id]
    try:
        mod = importlib.import_module(
            f"app.services.workpaper_sync.{plan.provider_module}"
        )
    except ImportError:
        return False
    return getattr(mod, fn_name, None) is not None
