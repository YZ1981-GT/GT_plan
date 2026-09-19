"""test_x3_bulk_strategy_parity —— 用例层。

判据（常量 / 登记表 / fixture / 纯函数 / helper）见 `_test_x3_bulk_strategy_parity_criteria.py`，
原文件 docstring 也在那里。拆分原因：原单文件 1168 行 > pre-commit 800 行门禁。
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import io
import json
import re
import uuid
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any, NamedTuple, get_args

import pytest
import sqlalchemy as sa
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from openpyxl import Workbook
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.routers.wp_render_strategies import _x3_adjustment_import_export as impl
from app.services.bulk_tab import _kfgh_cycle_adapters as ad
from app.services.bulk_tab.single_tab_adapter import (
    IE_ADAPTER_REGISTRY,
    ConflictStrategy,
    import_tab,
)

from tests._test_x3_bulk_strategy_parity_criteria import (  # noqa: F401  fixtures 需在本模块命名空间
    _CONTRACT,
    _ID_COL,
    _ITEM_COL,
    _MARK,
    _SEED_ID,
    _SNAPSHOT_COLUMNS,
    _WP_COL,
    _WP_TARGET,
    _codes,
    _delta,
    _hz,
    _import_endpoint,
    _is_single,
    _normalize,
    _normalize_rows,
    _ok,
    _run_via,
    _spec,
    _strategies,
)

__all__ = [
    "_CONTRACT",
    "_ID_COL",
    "_ITEM_COL",
    "_MARK",
    "_SEED_ID",
    "_SNAPSHOT_COLUMNS",
    "_WP_COL",
    "_WP_TARGET",
    "_codes",
    "_delta",
    "_hz",
    "_import_endpoint",
    "_is_single",
    "_normalize",
    "_normalize_rows",
    "_ok",
    "_run_via",
    "_spec",
    "_strategies",
]


def test_anchor_workscope_and_strategy_face() -> None:
    """作业面规模 / 与实现键集双向锁死 / 策略取值面 —— 塌陷时等价判据恒真。"""
    codes = _codes()
    assert len(codes) == 16, (
        f"作业面实测 {len(codes)} 张（design 用户裁决 1：16 张）：{list(codes)}"
    )
    assert set(codes) == set(impl.X3_SHEET_SPECS), (
        "契约清单口径与实现 `X3_SHEET_SPECS` 键集分叉："
        f"仅清单 {sorted(set(codes) - set(impl.X3_SHEET_SPECS))} / "
        f"仅实现 {sorted(set(impl.X3_SHEET_SPECS) - set(codes))}"
    )
    assert len(_strategies()) == 3, f"策略取值面实测 {_strategies()}（期望 3 个）"
    families = {_spec(c).key_family for c in codes}
    singles = [c for c in codes if _is_single(_spec(c))]
    assert len(families) == 3 and len(singles) == 5, (
        f"三族分布漂移：族 {sorted(f.value for f in families)} / 整表单键族 {singles}"
    )


def test_anchor_two_paths_share_one_callable() -> None:
    """恒等锚点：bulk 解析到的 endpoint 与界面通路命中的**是同一个对象**。

    GS6 判的是「同一模块」；模块相同不等于对象相同 —— 模块里若挂了两份同名闭包
    （比如 `attach_shape_a_routes` 被调用两次），bulk 按后缀 `endswith` 命中第一份、
    UI 命中另一份，两条通路照样分叉。故此处判对象恒等。
    """
    served: dict[str, Any] = {}
    for route in _hz().app.routes:
        path = str(getattr(route, "path", ""))
        if path.endswith(f"/{ad._SUFFIX_IMPORT}"):
            served.setdefault(path, getattr(route, "endpoint", None))
    checked = 0
    for code in _codes():
        prefix = _spec(code).api_prefix
        path = f"/api/workpapers/{{wp_id}}/{prefix}/{ad._SUFFIX_IMPORT}"
        assert path in served, f"{code}: ASGI app 未挂载 {path}"
        bulk_endpoint = _import_endpoint(code)
        assert bulk_endpoint is not None, f"{code}: bulk 侧解析不到 import-data 端点"
        assert served[path] is bulk_endpoint, (
            f"{code}: 界面通路命中的 endpoint 与 bulk 解析到的不是同一对象 "
            f"(ui={served[path]!r} / bulk={bulk_endpoint!r}) ⇒ split-brain"
        )
        checked += 1
    assert checked == 16, f"恒等锚点只覆盖了 {checked} 张"


def test_anchor_strategy_param_surface_is_exactly_the_x3_sixteen() -> None:
    """签名探测面锚点：`_PREFIX_TO_MODULE` 里带 ``strategy`` 形参的恰为 16 个 X-3 短前缀。

    这是「其余 73 键行为逐字不变」的**结构证明**：探测条件 ``"strategy" in params``
    对它们恒为假 ⇒ ``kwargs`` 一字不变。数字一旦变动（别的循环也加了 ``strategy`` 形参），
    这条打红 ⇒ 逼下一轮重新量化影响面，而不是默认「只影响 16 张」。
    """
    x3_prefixes = {_spec(c).api_prefix for c in _codes()}
    with_strategy: list[str] = []
    unresolved: list[str] = []
    for prefix, module_name in ad._PREFIX_TO_MODULE.items():
        try:
            module = importlib.import_module(ad._resolve_module_path(module_name))
        except Exception as exc:  # noqa: BLE001 - 解析不了要打红，不许静默跳过
            unresolved.append(f"{prefix}: {type(exc).__name__}: {exc}")
            continue
        endpoint = ad._endpoint_for(module, prefix, ad._SUFFIX_IMPORT)
        if endpoint is None:
            continue
        if "strategy" in inspect.signature(endpoint).parameters:
            with_strategy.append(prefix)
    assert not unresolved, f"`_PREFIX_TO_MODULE` 有键解析不到模块：{unresolved}"
    assert set(with_strategy) == x3_prefixes, (
        "带 `strategy` 形参的短前缀集合与 16 个 X-3 短前缀分叉："
        f"多出 {sorted(set(with_strategy) - x3_prefixes)} / "
        f"缺 {sorted(x3_prefixes - set(with_strategy))}"
    )
    assert len(ad._PREFIX_TO_MODULE) - len(with_strategy) == 73, (
        f"非 X-3 键规模实测 {len(ad._PREFIX_TO_MODULE) - len(with_strategy)}（基线 73）"
    )


def test_anchor_registry_and_fixture_are_live() -> None:
    """夹具自检：16 个前缀都在注册表里；预置真的落库；快照读到全部 10 列。"""
    hz = _hz()
    hz.reset()
    missing = [c for c in _codes() if _spec(c).api_prefix not in IE_ADAPTER_REGISTRY]
    assert not missing, f"这些 X-3 的短前缀未注册进 IE_ADAPTER_REGISTRY：{missing}"
    snapshot = hz.snapshot()
    assert snapshot, "预置后整表为空 ⇒ 夹具没写进库"
    assert all(len(row) == len(_SNAPSHOT_COLUMNS) for row in snapshot)
    wps = {row[_WP_COL] for row in snapshot}
    assert wps == set(hz.wp_ids), f"预置底稿集合 {wps} 与夹具声明不符"
    for code in _codes():
        rows = hz.readback(code)
        assert rows, f"{code}: 预置后界面读路径读回 0 行 ⇒ 预置形态与读回口径分叉"


# ═══════════════════════════════════════════════════════════════════════════
# 5. 反空转 witness（施加前的真实丢参调用 ⇒ 库态必分叉）
# ═══════════════════════════════════════════════════════════════════════════


def test_witness_dropping_strategy_diverges_from_ui() -> None:
    """把 ``strategy`` 丢掉（= 施加前形态）⇒ 与界面通路库态**必须**分叉。

    这条同时是本文件的反空转锚点与缺陷量化：
      * vs 界面 ``fill-empty`` / ``reject``：**16/16** 分叉（用户选的策略被丢 ⇒ 按覆盖写）
      * vs 界面 ``overwrite``：**11 张非整表单键族**分叉（残留族键从不清 ⇒ 幽灵行留存）；
        **5 张整表单键族**相同（该族无残留概念 ⇒ 只剩「合并语义恰好等同 overwrite」）
    """
    hz = _hz()
    diverge: dict[str, list[str]] = {"overwrite": [], "fill-empty": [], "reject": []}
    same: dict[str, list[str]] = {"overwrite": [], "fill-empty": [], "reject": []}
    for code in _codes():
        _dropped_result, dropped_state = _run_via(hz, code, "", "dropped")
        for strategy in _strategies():
            _ui_result, ui_state = _run_via(hz, code, strategy, "ui")
            bucket = same if dropped_state == ui_state else diverge
            bucket.setdefault(strategy, []).append(code)
    singles = sorted(c for c in _codes() if _is_single(_spec(c)))
    non_singles = sorted(c for c in _codes() if not _is_single(_spec(c)))

    assert sorted(diverge["fill-empty"]) == sorted(_codes()), (
        "丢参态与界面 fill-empty 库态相同的 sheet："
        f"{sorted(same['fill-empty'])} ⇒ 「用户选 fill-empty 被丢掉」这条缺陷不可量化"
    )
    assert sorted(diverge["reject"]) == sorted(_codes()), (
        f"丢参态与界面 reject 库态相同的 sheet：{sorted(same['reject'])}"
    )
    assert sorted(diverge["overwrite"]) == non_singles, (
        "丢参 vs 界面 overwrite 的分叉面漂移（期望 = 11 张非整表单键族）："
        f"实测分叉 {sorted(diverge['overwrite'])} / 相同 {sorted(same['overwrite'])}"
    )
    assert sorted(same["overwrite"]) == singles, (
        f"整表单键族在 overwrite 上应与丢参态相同，实测相同集 {sorted(same['overwrite'])}"
    )
    hz.reset()


# ═══════════════════════════════════════════════════════════════════════════
# 6. 主判据（库态与行为）
# ═══════════════════════════════════════════════════════════════════════════


def test_bulk_path_reaches_same_db_state_as_ui_path() -> None:
    """∀ 16 张 × ∀ 3 策略：bulk 通路与界面通路导入后 ``checklist_responses`` 逐行逐列相同。

    两侧从**同一基线**（确定性 id + 固定时间戳）各跑一次，比对归一后的**整表** 10 列
    （含「本轮是否被写过」这一维）；再比对界面读路径 ``load_rows`` 的返回行。
    """
    hz = _hz()
    compared = 0
    for code in _codes():
        for strategy in _strategies():
            bulk_result, bulk_state = _run_via(hz, code, strategy, "bulk")
            bulk_readback = _normalize_rows(hz.readback(code))
            ui_result, ui_state = _run_via(hz, code, strategy, "ui")
            ui_readback = _normalize_rows(hz.readback(code))

            assert _ok(bulk_result) == _ok(ui_result), (
                f"{code} / {strategy}: 两条通路的成败不一致 —— "
                f"bulk={bulk_result!r} / ui={ui_result!r}"
            )
            assert bulk_state == ui_state, (
                f"{code} / {strategy}: bulk 通路与界面通路库态分叉 ⇒ "
                f"{_delta(bulk_state, ui_state)}"
            )
            assert bulk_readback == ui_readback, (
                f"{code} / {strategy}: 库态相同但界面读回不同（读回口径依赖写入顺序？）"
                f" bulk={len(bulk_readback)} 行 / ui={len(ui_readback)} 行"
            )
            compared += 1
    assert compared == 48, f"通路对照实测 {compared} 组（期望 16 × 3 = 48）"
    hz.reset()


def test_reject_via_bulk_really_rejects_instead_of_overwriting() -> None:
    """∀ 16 张：``reject`` 经 bulk 必须**整表拒绝**，库态与导入前逐行逐列相同。

    「拒绝」的量化不是返回值好看，而是：① 通路自报失败 ② 整表快照与导入前**逐行逐列**
    相同（连 ``updated_at`` 都不许前移 —— 值相同的幂等 upsert 也是写）。
    施加前这条必红：策略被丢 ⇒ 走防御性 ``else`` ⇒ 按覆盖写入 = 静默覆盖已编制内容。
    """
    hz = _hz()
    for code in _codes():
        hz.reset()
        before = _normalize(hz.snapshot())
        result = hz.via_bulk(code, "reject")
        after = _normalize(hz.snapshot())
        assert not _ok(result), (
            f"{code}: bulk 侧 reject 自报成功（{result!r}）⇒ 没拒绝"
        )
        assert result.status == "failed" and result.errors, (
            f"{code}: reject 应返回 failed + 错误说明，实得 {result!r}"
        )
        assert after == before, (
            f"{code}: reject 却改了库态 ⇒ {_delta(before, after)}"
        )
    hz.reset()


def test_fill_empty_via_bulk_preserves_existing_content() -> None:
    """∀ 16 张：``fill-empty`` 经 bulk 不覆盖已编制内容、也不清残留族键。

    这是「静默覆盖」那条缺陷的正面判据：预置行 1 的取值全非空 ⇒ ``fill-empty`` 后
    **落库值必须仍是预置值**（不是上传值）；行 2/3 的族键必须仍在（不清残留）。
    """
    hz = _hz()
    for code in _codes():
        hz.reset()
        before = {
            (row[_WP_COL], row[_ITEM_COL]): row for row in hz.snapshot()
        }
        result = hz.via_bulk(code, "fill-empty")
        assert _ok(result), f"{code}: fill-empty 经 bulk 未成功：{result!r}"
        after = {(row[_WP_COL], row[_ITEM_COL]): row for row in hz.snapshot()}

        vanished = sorted(k[1] for k in set(before) - set(after))
        assert not vanished, (
            f"{code}: fill-empty 却删了族键 {vanished[:6]} ⇒ 策略没透传到残留门控"
        )
        value_col = _SNAPSHOT_COLUMNS.index(_spec(code).storage_field)
        overwritten = sorted(
            k[1]
            for k in set(before) & set(after)
            if before[k][value_col] != after[k][value_col]
        )
        assert not overwritten, (
            f"{code}: fill-empty 覆盖了已编制内容 {overwritten[:6]} ⇒ 静默数据丢失"
        )
    hz.reset()


# ═══════════════════════════════════════════════════════════════════════════
# 7. 反向自检（证明判据不是在跟自己绕圈）
# ═══════════════════════════════════════════════════════════════════════════


def test_reverse_selfcheck_normalization_is_not_lossy() -> None:
    """归一必须仍能区分两个刻意不同的库态（否则「两态相同」是归一造出来的假绿）。"""
    hz = _hz()
    hz.reset()
    baseline = _normalize(hz.snapshot())
    code = _codes()[0]
    hz.loop.run_until_complete(hz._seed(code, _WP_TARGET, (1,)))
    fewer = _normalize(hz.snapshot())
    assert fewer != baseline, (
        "把预置从 3 行改成 1 行后归一快照不变 ⇒ 归一把关键信息丢了，等价判据不可解读"
    )
    _result, written = _run_via(hz, code, "overwrite", "ui")
    assert written != baseline, "导入后归一快照与预置态相同 ⇒ 归一或写入通路塌陷"
    hz.reset()


def test_reverse_selfcheck_both_paths_are_actually_exercised() -> None:
    """正面钉住两条通路都**真的**改了库（防「两边都空转 ⇒ 恒等价」这种假绿）。"""
    hz = _hz()
    for path in ("bulk", "ui"):
        for code in _codes():
            hz.reset()
            before = _normalize(hz.snapshot())
            result, after = _run_via(hz, code, "overwrite", path)
            assert _ok(result), f"{code} / {path}: overwrite 未成功：{result!r}"
            assert after != before, (
                f"{code} / {path}: overwrite 后库态与预置态相同 ⇒ 该通路没真写库"
            )
    hz.reset()


def test_reverse_selfcheck_probe_marker_absent_from_truth_sources() -> None:
    """探针记号不出现在任何真源取值里（证明预置值与真源取值不互相污染）。"""
    assert _MARK not in _CONTRACT.read_text(encoding="utf-8"), (
        f"探针记号 {_MARK!r} 出现在契约清单里"
    )
    for code in _codes():
        spec = _spec(code)
        surface = (
            (code, spec.sheet_name, spec.item_id, spec.entry_type_field)
            + tuple(spec.per_field_suffixes)
            + tuple(spec.standalone_item_ids)
            + tuple(k for k in spec.field_keys if k)
        )
        polluted = [s for s in surface if s and _MARK in s]
        assert not polluted, f"{code}: 真源取值里含探针记号 {polluted}"


def test_reverse_selfcheck_uuid_import_is_used() -> None:
    """夹具不再用 ``uuid4`` 造预置 id（确定性基线是「逐行逐列相同」的前提）。"""
    assert uuid.uuid4() != uuid.uuid4(), "uuid4 不随机 ⇒ 环境异常"
    hz = _hz()
    hz.reset()
    ids = {row[_ID_COL] for row in hz.snapshot()}
    assert ids and all(str(i).startswith(f"{_SEED_ID}:") for i in ids), (
        "预置行的 id 不是确定性取值 ⇒ 两条通路的基线不逐字节相同"
    )

# ═══════════════════════════════════════════════════════════════════════════
# 8. 全键 kwargs 双向锁死（「其余 73 键行为逐字不变」的执行层证明）
# ═══════════════════════════════════════════════════════════════════════════
#
# 第 4 节的 `test_anchor_strategy_param_surface_is_exactly_the_x3_sixteen` 是**结构**证明
# （带 `strategy` 形参的短前缀恰为 16 个 ⇒ 探测条件对其余 73 键恒假）。本节补**执行层**：
# 真走一遍生产 `_call_endpoint`，把它为全部 89 键 × 三态实际构造的 kwargs 收下来比对。
# 两层并存的理由：结构证明依赖「探测条件写对了」这个前提，一旦有人把探测条件改成无条件
# 塞键（`kwargs["strategy"] = strategy` 不带 `in params` 守卫），结构证明照样绿。

#: 探测取值 —— 必须是**真字符串**（判据之一就是它别再退化成 `Query` 那个 `FieldInfo`）。
_SPY_STRATEGY = "fill-empty"


def _spy_for(real: Any) -> tuple[Any, dict[str, Any]]:
    """签名与真端点逐字相同的间谍（``_call_endpoint`` 只读 ``inspect.signature``）。

    用间谍而非真端点：本节判的是**传参面**（库态那面由第 6 节判），不必真跑业务代码；
    但签名必须逐字取自真端点，否则量到的是探针自己的形状，不是生产的。
    """
    captured: dict[str, Any] = {}

    async def spy(**kwargs: Any) -> Any:
        captured.clear()
        captured.update(kwargs)
        return {"ok": True, "imported_count": 0, "errors": []}

    spy.__signature__ = inspect.signature(real)  # type: ignore[attr-defined]
    return spy, captured


def _kw_shape(kwargs: Mapping[str, Any]) -> dict[str, str]:
    """kwargs → 可跨调用比对的形态。

    ``UploadFile`` / ``_DummyUser`` 这些**没有值相等语义**的对象每次调用都是新实例，直接
    比 dict 会恒不等（那是探针缺陷不是代码缺陷）；故标量按 ``repr`` 比、对象按**类型**比。
    仍能抓到关键分叉：``strategy`` 由 ``str`` 退化成 ``FieldInfo`` 会体现为类型名变化、
    取值变化会体现为 ``repr`` 变化。
    """
    out: dict[str, str] = {}
    for key, value in kwargs.items():
        if value is None or isinstance(value, (str, bool, int, float)):
            out[key] = f"{type(value).__name__}:{value!r}"
        else:
            out[key] = f"{type(value).__module__}.{type(value).__name__}"
    return out


def _kwargs_all_keys(strategy: str | None) -> dict[str, dict[str, dict[str, Any]]]:
    """∀ ``_PREFIX_TO_MODULE`` 键 × 三态 → 生产 ``_call_endpoint`` 实构造的 kwargs。

    调用形态照抄生产 ``_make_export_fn`` / ``_make_import_fn``（导出通路本来就不带
    ``strategy``、导入通路带）⇒ 量到的就是 bulk 的真实传参面，不是重抄一份探测规则。
    """
    upload = ad._make_upload_file(b"probe", "SHEET")
    out: dict[str, dict[str, dict[str, Any]]] = {}

    async def _drive() -> None:
        for prefix, module_name in ad._PREFIX_TO_MODULE.items():
            module = importlib.import_module(ad._resolve_module_path(module_name))
            per: dict[str, dict[str, Any]] = {}
            for suffix in (ad._SUFFIX_TEMPLATE, ad._SUFFIX_DATA, ad._SUFFIX_IMPORT):
                real = ad._endpoint_for(module, prefix, suffix)
                if real is None:
                    continue
                spy, captured = _spy_for(real)
                if suffix == ad._SUFFIX_IMPORT:
                    await ad._call_endpoint(
                        spy,
                        db=None,  # type: ignore[arg-type]
                        wp_id=_WP_TARGET,
                        sheet_code="SHEET",
                        upload_file=upload,
                        strategy=strategy,
                    )
                else:
                    await ad._call_endpoint(
                        spy,
                        db=None,  # type: ignore[arg-type]
                        wp_id=_WP_TARGET,
                        sheet_code="SHEET",
                    )
                per[suffix] = dict(captured)
            out[prefix] = per

    asyncio.run(_drive())
    return out


def test_all_keys_kwargs_unchanged_except_the_x3_sixteen() -> None:
    """非 X-3 的 **73 键**三态 kwargs 一个都不带 ``strategy``；16 个 X-3 的 ``import-data``
    恰好带上，且取值是**传进去那个 ``str``** 本身（不是 ``FieldInfo``、不是硬编码常量）。

    这条是任务 17.1「修法对其余 73 键行为必须逐字不变」的执行层落点：施加面被夹在
    「非 X-3 一个都不许多」与「16 张一个都不许少」之间，任一侧漂移都打红。
    """
    x3 = {_spec(c).api_prefix for c in _codes()}
    got = _kwargs_all_keys(_SPY_STRATEGY)
    assert set(got) == set(ad._PREFIX_TO_MODULE), "全键遍历面与 `_PREFIX_TO_MODULE` 不符"

    non_x3 = sorted(set(got) - x3)
    assert len(non_x3) == 73, f"非 X-3 键规模实测 {len(non_x3)}（基线 73）"

    offenders = {
        f"{prefix}/{suffix}": sorted(kw)
        for prefix in non_x3
        for suffix, kw in got[prefix].items()
        if "strategy" in kw
    }
    assert not offenders, (
        f"非 X-3 键的 kwargs 多出了 `strategy` ⇒ 施加面外溢：{offenders}"
    )

    resolved = sum(len(got[prefix]) for prefix in non_x3)
    assert resolved == 219, (
        f"73 键实际解析到的端点数 {resolved}（基线 219）⇒ 遍历面塌陷，上一条判据会空转"
    )

    for code in sorted(_codes()):
        prefix = _spec(code).api_prefix
        imp = got[prefix].get(ad._SUFFIX_IMPORT)
        assert imp is not None, f"{code}: bulk 侧解析不到 import-data 端点"
        assert imp.get("strategy") == _SPY_STRATEGY, (
            f"{code}: import-data 的 kwargs 里 `strategy` = {imp.get('strategy')!r}，"
            f"期望逐字等于传入值 {_SPY_STRATEGY!r}"
        )
        assert isinstance(imp["strategy"], str), (
            f"{code}: `strategy` 落到 {type(imp['strategy'])} ⇒ 又变回 FieldInfo 形态"
        )
        for suffix in (ad._SUFFIX_TEMPLATE, ad._SUFFIX_DATA):
            assert "strategy" not in got[prefix].get(suffix, {}), (
                f"{code}/{suffix}: 导出通路不该带 `strategy`"
            )


def test_reverse_selfcheck_kwargs_probe_is_live_and_delta_is_exactly_one_key() -> None:
    """反向自检三条 —— 证明上一条不是在跟空 dict 绕圈。

    ① 间谍真收到了 kwargs（``wp_id``/``sheet``/``db``/``current_user``/``file`` 都在）；
    ② ``strategy=None``（导出通路形态、也是**施加前**的形态）⇒ 该键缺席；
    ③ 传值 vs 不传值两份 kwargs 的差**恰好只有** ``strategy`` 这一个键 —— 即施加没有
      顺手动到别的传参（否则「73 键逐字不变」只是没查到而已）。
    """
    x3 = sorted(_spec(c).api_prefix for c in _codes())
    got_none = _kwargs_all_keys(None)
    got_str = _kwargs_all_keys(_SPY_STRATEGY)
    baseline = {"wp_id", "sheet", "db", "current_user", "file"}
    for prefix in x3:
        omitted = got_none[prefix][ad._SUFFIX_IMPORT]
        passed = got_str[prefix][ad._SUFFIX_IMPORT]
        assert baseline <= set(omitted), (
            f"{prefix}: 间谍收到的 kwargs 形态异常 {sorted(omitted)} ⇒ 探针塌陷"
        )
        assert "strategy" not in omitted, (
            f"{prefix}: `strategy=None` 时仍塞了该键 ⇒ 导出通路与施加前不再逐字相同"
        )
        assert set(passed) - set(omitted) == {"strategy"}, (
            f"{prefix}: 传 `strategy` 后多出的键不只它一个：{sorted(set(passed) - set(omitted))}"
        )
        assert set(omitted) - set(passed) == set(), (
            f"{prefix}: 传 `strategy` 后少了键：{sorted(set(omitted) - set(passed))}"
        )
    for prefix, per in got_none.items():
        if prefix in x3:
            continue
        for suffix, kw in per.items():
            omitted_shape = _kw_shape(kw)
            passed_shape = _kw_shape(got_str[prefix][suffix])
            assert omitted_shape == passed_shape, (
                f"{prefix}/{suffix}: 传不传 `strategy` 改变了非 X-3 键的 kwargs ⇒ "
                f"{omitted_shape} vs {passed_shape}"
            )
