# -*- coding: utf-8 -*-
"""注册按 entry 隔离 + 通用对齐守卫 —— 行为级判据。

spec: workpaper-sync-registration-isolation-and-d2-republish · Wave A · Requirements 1 / 2

起因：D2 灰度开关打开后只改契约不重发布 ⇒ attach 期 ContractDriftError ⇒ 注册是「全有或
全无」，一个 entry 抛错整批中断、缓存不写 ⇒ **所有** entry 的 sync 端点都 422。本文件钉住：
① 一个 entry 的注册失败只影响它自己（其余照常注册）；② 失败（真故障）与供给不足（reason）
两个集合分开、记账等式成立；③ 通用对齐守卫覆盖全部 provider。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync.adapters import registry as R  # noqa: E402
from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402
from app.services.workpaper_sync.models import SyncDomainError  # noqa: E402
from app.services.workpaper_sync import phase5_row_table_sheet as F  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# 1. 记账等式：registered + reasons + failures == planned，三集合不相交
# ═══════════════════════════════════════════════════════════════════════════


def test_outcome_accounting_is_closed_across_three_buckets() -> None:
    """三桶记账：一个 entry 只能落进 registered / reasons / failures 之一，之和 == planned。"""
    outcome = R.ManifestRegistrationOutcome(
        registered_adapter_ids=("a.b",),
        reasons={"e2": "供给不足"},
        planned_entry_ids=("e1", "e2", "e3"),
        registered_entry_ids=("e1",),
        failures={
            "e3": R.RegistrationFailure(
                entry_id="e3",
                error_code="sync_contract_structure_drift",
                message="结构漂移",
                exc_type="ContractDriftError",
            )
        },
    )
    reg = set(outcome.registered_entry_ids)
    reasons = set(outcome.reasons)
    fails = set(outcome.failures)
    assert len(reg) + len(reasons) + len(fails) == len(outcome.planned_entry_ids)
    # 两两不相交（同一 entry 不得既 registered 又 failure）
    assert not (reg & reasons) and not (reg & fails) and not (reasons & fails)


def test_failure_and_reason_are_separate_buckets() -> None:
    """AC 5.12：注册失败（真故障）不得被降级成供给不足（reason）。as_dict 分列。"""
    outcome = R.ManifestRegistrationOutcome(
        registered_adapter_ids=(),
        reasons={"e1": "尚无 published representation"},
        planned_entry_ids=("e1", "e2"),
        registered_entry_ids=(),
        failures={
            "e2": R.RegistrationFailure(
                entry_id="e2",
                error_code="sync_contract_structure_drift",
                message="结构漂移，首个不一致位置 ...",
                exc_type="ContractDriftError",
            )
        },
    )
    d = outcome.as_dict()
    assert "e1" in d["reasons"] and "e1" not in d["failures"]
    assert "e2" in d["failures"] and "e2" not in d["reasons"]
    assert d["failures"]["e2"]["error_code"] == "sync_contract_structure_drift"
    # 未注册计数含两类（reason + failure），不遗漏 failure
    assert d["unregistered_entry_count"] == 2


def test_default_failures_is_empty_mapping() -> None:
    """向后兼容：不传 failures 的历史构造 outcome 仍合法（失败集合默认空）。"""
    outcome = R.ManifestRegistrationOutcome(
        registered_adapter_ids=("a.b",),
        reasons={},
        planned_entry_ids=("e1",),
        registered_entry_ids=("e1",),
    )
    assert dict(outcome.failures) == {}
    assert outcome.as_dict()["failures"] == {}


# ═══════════════════════════════════════════════════════════════════════════
# 2. register_from_manifest 按 entry 隔离（源码级 + 行为级）
# ═══════════════════════════════════════════════════════════════════════════


def test_register_from_manifest_isolates_domain_errors_not_bare_exceptions() -> None:
    """源码级：捕获**只**是 SyncDomainError（记 failure），非域异常必上抛。

    只捕 SyncDomainError 而不是宽 `except Exception`：DB 故障 / AttributeError 是真 bug，
    吞成 fail-visible 的注册失败会把它藏进 outcome 里，运维查不到。
    """
    import ast
    import inspect

    src = inspect.getsource(R.WorkpaperSyncAdapterRegistry.register_from_manifest)
    import textwrap

    tree = ast.parse(textwrap.dedent(src))
    caught: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            t = node.type
            if isinstance(t, ast.Name):
                caught.append(t.id)
            elif isinstance(t, ast.Tuple):
                caught.extend(e.id for e in t.elts if isinstance(e, ast.Name))
            elif t is None:
                caught.append("<bare>")
    assert caught, "register_from_manifest 一个 except 都没有 ⇒ 隔离判据无分母"
    assert set(caught) == {"SyncDomainError"}, (
        f"隔离只能捕 SyncDomainError，实得 {caught} —— 宽泛捕获会把真 bug 吞成注册失败"
    )


def test_register_from_manifest_still_records_failure_as_typed() -> None:
    """行为级（合成 registry）：一个 entry 的 provider 抛 SyncDomainError ⇒ 记 failure、
    继续其余 entry、不中断。"""
    import asyncio

    class _DriftError(SyncDomainError):
        error_code = "sync_contract_structure_drift"

    class _Item:
        def __init__(self, entry_id, provider_module):
            self.entry_id = entry_id
            self.provider_module = provider_module
            self.blocked_reason = None
            self.capability = None
            self.contract_id = None

    good_item = _Item("xlsx/good", "mod.good")
    bad_item = _Item("xlsx/bad", "mod.bad")

    class _Reg(R.WorkpaperSyncAdapterRegistry):
        def __init__(self):
            self._by_entry_id = {}
            self._by_adapter_id = {}
            self._plan = (good_item, bad_item)

        @property
        def registration_plan(self):
            return self._plan

    reg = _Reg()

    async def _fake_supply(*, session, entry_id):
        return None  # 供给都满足，走到 provider

    def _fake_loader(item):
        async def _provider(registry, *, session):
            if item.entry_id == "xlsx/bad":
                raise _DriftError("结构漂移，首个不一致位置 sheet='d21-managed'")
            return ("good.adapter",)

        return _provider

    import app.services.workpaper_sync.adapters.registry as regmod

    orig_supply = regmod._describe_entry_supply
    orig_loader = regmod._load_entry_provider
    regmod._describe_entry_supply = _fake_supply
    regmod._load_entry_provider = _fake_loader
    try:
        outcome = asyncio.run(reg.register_from_manifest(session=object()))
    finally:
        regmod._describe_entry_supply = orig_supply
        regmod._load_entry_provider = orig_loader

    # good 注册成功、bad 记 failure、不中断
    assert "good.adapter" in outcome.registered_adapter_ids
    assert "xlsx/good" in outcome.registered_entry_ids
    assert "xlsx/bad" in outcome.failures
    f = outcome.failures["xlsx/bad"]
    assert f.error_code == "sync_contract_structure_drift"
    assert f.exc_type == "_DriftError"
    # 记账三桶闭合
    assert (
        len(outcome.registered_entry_ids)
        + len(outcome.reasons)
        + len(outcome.failures)
        == len(outcome.planned_entry_ids)
    )


def test_register_from_manifest_reraises_non_domain_error() -> None:
    """非 SyncDomainError（真 bug）必上抛，不吞成注册失败。"""
    import asyncio

    class _Item:
        def __init__(self, entry_id):
            self.entry_id = entry_id
            self.provider_module = "mod.x"
            self.blocked_reason = None

    class _Reg(R.WorkpaperSyncAdapterRegistry):
        def __init__(self):
            self._by_entry_id = {}
            self._by_adapter_id = {}
            self._plan = (_Item("xlsx/boom"),)

        @property
        def registration_plan(self):
            return self._plan

    import app.services.workpaper_sync.adapters.registry as regmod

    async def _fake_supply(*, session, entry_id):
        return None

    def _fake_loader(item):
        async def _provider(registry, *, session):
            raise RuntimeError("DB 连接断了")  # 非域异常

        return _provider

    orig_supply = regmod._describe_entry_supply
    orig_loader = regmod._load_entry_provider
    regmod._describe_entry_supply = _fake_supply
    regmod._load_entry_provider = _fake_loader
    try:
        with pytest.raises(RuntimeError, match="DB 连接断了"):
            asyncio.run(_Reg().register_from_manifest(session=object()))
    finally:
        regmod._describe_entry_supply = orig_supply
        regmod._load_entry_provider = orig_loader


# ═══════════════════════════════════════════════════════════════════════════
# 3. 通用对齐守卫覆盖全部 provider（含 D4 —— 此前无守卫）
# ═══════════════════════════════════════════════════════════════════════════

#: 从 golden digest 门的权威登记取 provider（唯一来源，不重复维护）。
def _golden_providers():
    sys.path.insert(0, str(_BACKEND / "scripts" / "check"))
    try:
        from check_sync_provider_golden_digest import PROVIDERS  # noqa: PLC0415
    finally:
        sys.path.remove(str(_BACKEND / "scripts" / "check"))
    return PROVIDERS


# 已知 misaligned 的 provider 豁免名单。
#
# 🔴 **现在是空的，且禁止回填**。曾经有两条，都已被兑现并移除（2026-09-28）：
#
#   * `d1.notes_receivable_detail` —— 原登记（2026-09-26 观测）：契约已扩 11 张 sheet
#     但父 provider `phase5_d1_notes_receivable` 的 instrumentation 受管 sheet 集合只出
#     d13，原文写明「待 D1 那条会话补齐 `instrumentation_specs` 后从本集合移除」。
#     该补齐已完成：entry 模块补出复数 `instrumentation_specs()` 薄转发（18 组），
#     并把 `instrumentation_definition_payload` 改走
#     `build_instrumentation_payload_for_sheets`。这条豁免随之失效。
#     🔴 顺带证实：那个「只出 d13」的漂移不只是登记问题 —— 它同时是 D1 整册
#     representation 发布长期抛 `ContractDriftError` 的**根因**
#     （staged substrate 里 18 张声明表只注出 1 张）。详见
#     `test_d1_instrumentation_specs_forwarder.py` 与 `test_d1_full_book_gate_open_pg.py`。
#
#   * `d3.prepaid_receipts_detail` —— 原登记：契约已扩 d34/d35/d36 但父 provider 只暴露
#     单数 `instrumentation_spec`（d32）。现算已对齐（通用守卫不再抛），豁免同样失效。
#
# 名单为空时 `test_known_misaligned_has_no_stale_entries` 仍然有意义：它禁止
# 「把新漂移塞进名单当已知问题」这条退路 —— 加进来就必须证明它真的 misaligned。
_KNOWN_MISALIGNED: set[str] = set()


@pytest.mark.parametrize("row", _golden_providers(), ids=lambda r: r[0])
def test_generic_alignment_guard_covers_every_provider(row) -> None:
    """每个已交付 provider：通用守卫要么对齐通过，要么（已知并发态）精确报差集。"""
    import importlib

    label, module_name, adapter_const, _hp, _pl = row
    mod = importlib.import_module(f"app.services.workpaper_sync.{module_name}")
    adapter_id = getattr(mod, adapter_const)
    contract = parse_contract(mod.build_contract_payload(), adapter_id=adapter_id)
    if adapter_id in _KNOWN_MISALIGNED:
        with pytest.raises(SyncDomainError):
            F.assert_provider_specs_align_with_contract(mod, contract)
    else:
        # 对齐即返回 None；不对齐会抛并报差集（本轮修复要求这些全对齐）。
        F.assert_provider_specs_align_with_contract(mod, contract)


def test_known_misaligned_has_no_stale_entries() -> None:
    """豁免名单的**反向断言**：名单里每一条都必须真的 misaligned。

    🔴 这是「豁免名单必配反向断言」这条纪律的落地：没有它，名单会变成
    「把红转绿」的万能出口 —— 缺陷修好之后豁免仍在，下一个人无从知道它已过期。
    本仓库刚被这条抓了两次（d1 与 d3 都已对齐却仍在名单里）。

    名单为空时本条自然通过（空循环），但它守的是**往里加**的动作。
    """
    import importlib

    rows = {row[0]: row for row in _golden_providers()}
    stale: list[str] = []
    for adapter_id in sorted(_KNOWN_MISALIGNED):
        row = rows.get(adapter_id)
        assert row is not None, (
            f"豁免名单里的 {adapter_id!r} 不在 golden digest 登记中 —— 名单已与真源脱钩"
        )
        _label, module_name, adapter_const, _hp, _pl = row
        mod = importlib.import_module(f"app.services.workpaper_sync.{module_name}")
        contract = parse_contract(
            mod.build_contract_payload(), adapter_id=getattr(mod, adapter_const)
        )
        try:
            F.assert_provider_specs_align_with_contract(mod, contract)
        except SyncDomainError:
            continue  # 确实 misaligned，豁免成立
        stale.append(adapter_id)

    assert not stale, (
        f"豁免名单有 {len(stale)} 条**失效条目**（现已对齐却仍被豁免）：{stale} —— "
        f"请把它们从 `_KNOWN_MISALIGNED` 移除，并在注释里写明是什么改动让它对齐的"
    )


def test_alignment_guard_reports_exact_diff_on_missing_spec() -> None:
    """合成：契约多一张 spec 没有的 sheet ⇒ fail-closed 且报出那张的差集。"""
    from app.services.workpaper_sync.projection_first_publication import (
        ProviderCapabilityError,
    )
    from app.services.workpaper_sync import pilot_d2_large_json as D2

    contract = parse_contract(D2.build_contract_payload(), adapter_id=D2.PILOT_ADAPTER_ID)

    class _FakeContract:
        # 比真契约多一张 spec 没有的 sheet
        sheets = tuple(contract.sheets) + (
            type("S", (), {"sheet_key": "ghost-managed"})(),
        )

    with pytest.raises(ProviderCapabilityError) as exc:
        F.assert_provider_specs_align_with_contract(D2, _FakeContract())
    assert "ghost-managed" in str(exc.value)
    assert "打挂整个 entry" in str(exc.value)
