# -*- coding: utf-8 -*-
"""E1 契约发布链五环 —— 逐环断言产物存在，不得只看最终 migrationState。

spec: e1-sync-coverage-and-first-canary · Task 9
Properties: E1-P1（migrationState 转换）/ E1-P4（§9.6 三谓词的前置）/ E1-P12（零回归）

═══ 发布链五环（任一环缺供给都会静默不注册）═══

  ①  build_contract_payload → 生成器 --apply → assert_contract_file_matches_source
  ②  磁盘契约 JSON 存在（approved bundle 的磁盘产物前置）
  ③  published representation（working_paper_sync_entry_state /
      working_paper_content_version / working_paper_content_representation 三表有 E1 行）
  ④  entry_state（manifest capability = bidirectional）
  ⑤  register_from_manifest()（adapter 真注册）

🔴 **2026-09-26 诚实分层**：
  * ① ② 现在就能绿（provider 已存在、磁盘契约已生成）
  * ③ 是 umbrella BP-61-1 的**平台级约束**（三表近空，186 个 planned entry 一个都注册不上）
    ⇒ strict xfail，解除约束后 XPASS 并强制摘掉标记
  * ④ manifest capability 当前为 single_onlyoffice ⇒ strict xfail
  * ⑤ adapter 未注册 ⇒ strict xfail
  * E1-P1 转绿（legacy_fake_bidirectional → adapter_registered）⇒ strict xfail

🔴 **合成测试不得冒充真栈**（Task 9 明令）。xfail 标记的判据将在 umbrella BP-61-1 解除后
   自动 XPASS 并报错，强制更新 spec 状态。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.services.workpaper_sync import phase5_e1_monetary_fund as E
from app.services.workpaper_sync.contracts import parse_contract

_BACKEND = Path(__file__).resolve().parents[2]
_SLICE = _BACKEND / "data" / "workpaper_sync_e_cycle_manifest_slice.json"

# ═══════════════════════════════════════════════════════════════════════════
# 环 ①：build_contract_payload → assert_contract_file_matches_source
#
# provider 已存在、灰度开关已开 2 张 ⇒ 现在就能绿。
# ═══════════════════════════════════════════════════════════════════════════


class TestRing1ContractPayload:
    """环 ①：provider 现算 contract payload 可构建且与磁盘锁死。"""

    def test_build_contract_payload_succeeds(self) -> None:
        """build_contract_payload() 可调用且返回合法结构。"""
        payload = E.build_contract_payload()
        assert payload is not None
        assert payload["contract_id"] == E.ADAPTER_ID
        assert "sheets" in payload
        assert len(payload["sheets"]) >= 1, "至少有 canary sheet"

    def test_contract_has_schema_version(self) -> None:
        """contract payload 带 schema_version（注册表校验的硬前置）。"""
        from app.services.workpaper_sync.contracts import CONTRACT_SCHEMA_VERSION

        payload = E.build_contract_payload()
        assert payload["schema_version"] == CONTRACT_SCHEMA_VERSION

    def test_contract_payload_parseable(self) -> None:
        """现算 payload 可被 parse_contract 正确解析（schema 自洽）。"""
        payload = E.build_contract_payload()
        contract = parse_contract(payload, adapter_id=E.ADAPTER_ID)
        assert contract is not None
        assert contract.contract_id == E.ADAPTER_ID

    def test_assert_contract_file_matches_source(self) -> None:
        """磁盘契约 ↔ provider 现算 payload 双向锁死（环 ① 的核心门）。

        🔴 如果此条红了，说明灰度开关改了而忘记跑
        `generate_phase5_e1_contract.py --apply` —— 或反过来有人手改了磁盘契约。
        """
        contract = E.assert_contract_file_matches_source()
        assert contract.contract_id == E.ADAPTER_ID

    def test_canonical_digest_reproducible(self) -> None:
        """两次现算 payload 的 canonical_digest 一致（确定性）。"""
        from app.services.workpaper_sync.definitions import canonical_digest

        d1 = canonical_digest(E.build_contract_payload())
        d2 = canonical_digest(E.build_contract_payload())
        assert d1 == d2, "canonical_digest 不确定 ⇒ 门会随机打红"


# ═══════════════════════════════════════════════════════════════════════════
# 环 ②：磁盘契约 JSON 存在（approved bundle 的磁盘产物前置）
#
# generate_phase5_e1_contract.py --apply 已跑过 ⇒ 现在就能绿。
# ═══════════════════════════════════════════════════════════════════════════


class TestRing2ContractOnDisk:
    """环 ②：磁盘契约 JSON 已生成且可解析。"""

    def test_contract_file_exists(self) -> None:
        """磁盘契约文件 `{ADAPTER_ID}.json` 存在。"""
        path = E.contract_file_path()
        assert path.exists(), (
            f"磁盘契约不存在：{path} ⇒ 需跑 "
            "`generate_phase5_e1_contract.py --apply` 生成"
        )

    def test_contract_file_is_valid_json(self) -> None:
        """磁盘契约可解析为 JSON。"""
        path = E.contract_file_path()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "contract_id" in data
        assert data["contract_id"] == E.ADAPTER_ID

    def test_contract_file_has_sheets(self) -> None:
        """磁盘契约含 sheet 声明（不是空壳）。"""
        path = E.contract_file_path()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data.get("sheets", [])) >= 1

    def test_load_contract_from_disk_succeeds(self) -> None:
        """load_contract_from_disk() 加载并校验成功（强校验包含 schema 自洽）。"""
        contract = E.load_contract_from_disk()
        assert contract.contract_id == E.ADAPTER_ID

    def test_contract_file_path_matches_adapter_id(self) -> None:
        """磁盘契约路径与 ADAPTER_ID 对齐。"""
        path = E.contract_file_path()
        assert path.stem == E.ADAPTER_ID, (
            f"契约文件名 {path.stem!r} ≠ ADAPTER_ID {E.ADAPTER_ID!r}"
        )

    def test_contract_registered_in_delivered_contracts(self) -> None:
        """E1 已在 DELIVERED_PER_ENTRY_CONTRACTS 注册。"""
        from app.services.workpaper_sync.adapters.registry import (
            DELIVERED_PER_ENTRY_CONTRACTS,
        )

        e1 = [r for r in DELIVERED_PER_ENTRY_CONTRACTS if r["contract_id"] == E.ADAPTER_ID]
        assert len(e1) == 1, f"E1 在交付登记表中应恰好 1 条，实际 {len(e1)}"
        assert e1[0]["entry_id"] == E.ENTRY_ID

    def test_contract_provider_module_matches(self) -> None:
        """注册表里 E1 的 provider_module 正确。"""
        from app.services.workpaper_sync.adapters.registry import (
            DELIVERED_PER_ENTRY_CONTRACTS,
        )

        e1 = next(r for r in DELIVERED_PER_ENTRY_CONTRACTS if r["contract_id"] == E.ADAPTER_ID)
        assert e1["provider_module"] == "app.services.workpaper_sync.phase5_e1_monetary_fund"


# ═══════════════════════════════════════════════════════════════════════════
# 环 ③：published representation（BP-61-1 平台级约束）
#
# 🔴 `working_paper_sync_entry_state` / `working_paper_content_version` /
#    `working_paper_content_representation` 三表近空，186 个 planned entry 一个都注册不上。
# ⇒ strict xfail，解除约束后 XPASS 并强制摘掉标记。
# ═══════════════════════════════════════════════════════════════════════════


class TestRing3PublishedRepresentation:
    """环 ③：E1 在三表中有 published representation（BP-61-1 平台级约束）。

    🔴 umbrella BP-61-1 原文：`working_paper_sync_entry_state` /
    `working_paper_content_version` / `working_paper_content_representation` 三表近空，
    **186 个 planned entry 一个都注册不上**。生产者是
    `ContentMutationService.commit(...)` 与 umbrella Tasks 36/77 的 finalize gate。

    E1 与 D1/D3/D5/D6/D7 六个循环卡在同一缺口 —— 不该在六个 spec 里各自把发布链重做一遍。
    """

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "🔴 BP-61-1 平台级约束：working_paper_sync_entry_state 三表近空，"
            "186 个 planned entry 一个都注册不上。生产者是 "
            "ContentMutationService.commit(...) 与 umbrella Tasks 36/77 的 finalize gate。"
            "E1 与 D1/D3/D5/D6/D7 六个循环卡在同一缺口。"
            "解除后本条 XPASS 并强制摘掉标记。"
        ),
    )
    def test_manifest_capability_is_bidirectional(self) -> None:
        """E1 的 manifest capability 应为 bidirectional（published representation 的前提）。

        当前实测为 `single_onlyoffice` ⇒ 必红。
        """
        assert E.manifest_capability_enabled() is True, (
            "manifest_capability_enabled() 返回 False ⇒ "
            "capability 仍为 single_onlyoffice，published representation 不可能存在"
        )

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "🔴 BP-61-1 平台级约束：assert_manifest_capability_enabled 当前会抛 "
            "EntrySelectionError（capability=single_onlyoffice，期望 bidirectional）。"
            "解除后本条 XPASS 并强制摘掉标记。"
        ),
    )
    def test_assert_manifest_capability_passes(self) -> None:
        """assert_manifest_capability_enabled() 不抛异常。"""
        E.assert_manifest_capability_enabled()

    def test_capability_gate_fails_with_clear_reason(self) -> None:
        """✅ 反向判据：当前 capability 未放行时，错误信息点名 capability 值。

        🔴 这条**现在就能绿** —— 它验证的是「拒绝时的诊断质量」而非「放行」。
        """
        with pytest.raises(E.EntrySelectionError) as excinfo:
            E.assert_manifest_capability_enabled()
        msg = str(excinfo.value)
        assert "capability" in msg or "bidirectional" in msg, (
            f"错误信息未提及 capability/bidirectional：{msg}"
        )
        assert E.ENTRY_ID in msg, f"错误信息未点名 entry_id：{msg}"


# ═══════════════════════════════════════════════════════════════════════════
# 环 ④：entry_state（manifest 里 E1 的迁移状态）
#
# 🔴 manifest capability 未放行 ⇒ adapter 注册被拒 ⇒ entry_state 不变。
# ═══════════════════════════════════════════════════════════════════════════


class TestRing4EntryState:
    """环 ④：manifest 里 E1 的迁移状态。

    当前实测 `migration_state=legacy_fake_bidirectional` + `adapter_id=None`（E1-P1 红形态）。
    """

    @pytest.fixture(scope="class")
    def slice_entry(self) -> dict[str, Any]:
        """从 E 循环 slice 读 E1 的 entry。"""
        payload = json.loads(_SLICE.read_text(encoding="utf-8"))
        entries = payload["independent_entries"]
        entry = next(e for e in entries if e.get("entry_id") == E.ENTRY_ID)
        return entry

    def test_entry_exists_in_slice(self, slice_entry: dict) -> None:
        """E1 entry 在 E 循环 slice 里存在。"""
        assert slice_entry["entry_id"] == E.ENTRY_ID

    def test_current_state_is_legacy(self, slice_entry: dict) -> None:
        """✅ 现状登记：migration_state 为 legacy_fake_bidirectional（红形态）。"""
        assert slice_entry.get("migration_state") == "legacy_fake_bidirectional", (
            "若已变成 adapter_registered，说明发布链已通 ⇒ "
            "本 slice 已过期，需更新 spec 状态"
        )

    def test_adapter_id_is_none(self, slice_entry: dict) -> None:
        """✅ 现状登记：adapter_id 为 None（尚未注册）。"""
        assert slice_entry.get("adapter_id") is None

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "🔴 红基线（发布链五环未通）：E1 的 migration_state 仍为 "
            "legacy_fake_bidirectional，不是 adapter_registered。"
            "发布链五环（尤其第③环 published representation）通过后本条 XPASS。"
        ),
    )
    def test_entry_state_transitions_to_adapter_registered(self, slice_entry: dict) -> None:
        """E1-P1 转绿：migration_state 应从 legacy_fake_bidirectional → adapter_registered。"""
        assert slice_entry.get("migration_state") == "adapter_registered", (
            f"migration_state={slice_entry.get('migration_state')!r}，"
            "期望 adapter_registered"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 环 ⑤：register_from_manifest()（adapter 真注册）
#
# 🔴 capability 未放行 ⇒ attach_pilot_adapters 返回空元组。
#    capability 放行但 adapter 构造未实现 ⇒ raise EntrySelectionError（故意的）。
# ═══════════════════════════════════════════════════════════════════════════


class TestRing5AdapterRegistration:
    """环 ⑤：attach_pilot_adapters 与 adapter 注册。

    两层阻塞：
    1. capability 未放行 ⇒ 返回空元组（不抛，编排需要「暂不可注册」是可继续的结果）
    2. capability 放行后 adapter 构造未实现 ⇒ raise EntrySelectionError（故意的 BP-61-1 登记）
    """

    def test_attach_returns_empty_when_capability_off(self) -> None:
        """✅ capability 未放行时 attach_pilot_adapters 返回空元组（不抛）。

        🔴 这是**有意**设计：`register_from_manifest()` 的编排需要
        「本 entry 暂不可注册」是可继续的结果，而不是让整条注册链崩掉。
        """
        result = E.attach_pilot_adapters(registry=None)
        assert result == (), (
            f"capability 未放行时应返回 ()，实际返回 {result!r}"
        )

    def test_attach_is_callable(self) -> None:
        """attach_pilot_adapters 可调用。"""
        assert callable(E.attach_pilot_adapters)

    def test_publish_definitions_is_callable(self) -> None:
        """publish_definitions 可调用（async 函数签名存在）。"""
        import asyncio
        import inspect

        assert hasattr(E, "publish_definitions")
        assert inspect.iscoroutinefunction(E.publish_definitions)

    def test_resolve_published_frozen_definitions_is_callable(self) -> None:
        """resolve_published_frozen_definitions 可调用（五环的观测器入口）。"""
        import inspect

        assert hasattr(E, "resolve_published_frozen_definitions")
        assert inspect.iscoroutinefunction(E.resolve_published_frozen_definitions)

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "🔴 BP-61-1 平台级约束：capability 未放行 ⇒ attach_pilot_adapters 返回空元组，"
            "adapter 无法注册。即使 capability 放行，attach_pilot_adapters 仍会 raise "
            "EntrySelectionError（adapter 构造未实现，是故意的 BP-61-1 登记）。"
            "adapter 注册成功后本条 XPASS 并强制摘掉标记。"
        ),
    )
    def test_attach_returns_non_empty_adapter(self) -> None:
        """adapter 注册成功后返回非空元组。"""
        result = E.attach_pilot_adapters(registry=None)
        assert len(result) > 0, (
            "attach_pilot_adapters 返回空 ⇒ adapter 未注册"
        )


# ═══════════════════════════════════════════════════════════════════════════
# E1-P1 转绿：综合判据（五环全通后 migrationState + reasonCodes 正确变更）
#
# 🔴 红基线 ⇒ strict xfail。全部转绿时 spec Task 3 的 E1-P1 红判据自动变绿。
# ═══════════════════════════════════════════════════════════════════════════


class TestE1P1TransitionGate:
    """E1-P1 综合转绿门：发布链五环全通后的状态校验。

    🔴 Task 3 先打红的 E1-P1 在本任务转绿。三条 reasonCodes
    （template_only_open / no_durable_forcesave_ack / missing_adapter）全消。

    **现状必红**：slice 实测 E1 仍是 legacy_fake_bidirectional + adapter_id=None。
    """

    @pytest.fixture(scope="class")
    def slice_payload(self) -> dict[str, Any]:
        return json.loads(_SLICE.read_text(encoding="utf-8"))

    @pytest.fixture(scope="class")
    def slice_entry(self, slice_payload: dict) -> dict[str, Any]:
        return next(
            e for e in slice_payload["independent_entries"]
            if e.get("entry_id") == E.ENTRY_ID
        )

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "🔴 红基线（E1-P1 先打红，Task 3）：E1 的 migration_state 仍为 "
            "legacy_fake_bidirectional。发布链五环全通后本条 XPASS。"
        ),
    )
    def test_migration_state_is_adapter_registered(self, slice_entry: dict) -> None:
        """E1-P1：migration_state 应为 adapter_registered。"""
        assert slice_entry.get("migration_state") == "adapter_registered"

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "🔴 红基线（E1-P1 先打红，Task 3）：adapter_id 仍为 None。"
            "发布链五环全通后本条 XPASS。"
        ),
    )
    def test_adapter_id_is_set(self, slice_entry: dict) -> None:
        """E1-P1：adapter_id 应为 ADAPTER_ID。"""
        assert slice_entry.get("adapter_id") == E.ADAPTER_ID

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "🔴 红基线（E1-P1 先打红，Task 3）：manifest capability 仍为 "
            "single_onlyoffice，adapter_id=None，发布链五环未通。"
            "发布链五环全通后本条 XPASS。"
        ),
    )
    def test_capability_transitions_to_bidirectional(self) -> None:
        """E1-P1：manifest capability 应为 bidirectional（三条 reasonCodes 全消的前置）。

        🔴 E 循环 slice 不含 `manifest_legacy_reasons`（那是 D 循环 slice 的字段），
        所以改用 `manifest_capability_enabled()` 作为等价判据 —— capability 从
        `single_onlyoffice` → `bidirectional` **只能**由 `register_from_manifest()` 在
        注册成功后驱动（spec Task 7 的 `assert_manifest_capability_enabled` 明写），
        capability 变 bidirectional ⇔ 三条 reasonCodes 全消。
        """
        assert E.manifest_capability_enabled() is True, (
            "manifest_capability_enabled() 返回 False ⇒ "
            "capability 仍为 single_onlyoffice，发布链五环尚未全通"
        )

    def test_current_red_state_is_documented(self, slice_entry: dict) -> None:
        """✅ 现状登记：E1 确实处于红形态（capability 未放行 + adapter_id=None）。

        🔴 这条**现在就能绿** —— 它登记「红的形态」，不是断言「应该绿」。
        上面三条 xfail 断言的是目标态；本条断言的是现状。两者的数据源是同一个，
        但判据方向相反：一组要它改、一组要它不动 ⇒ 改了会让本条红，
        这就是「E1-P1 转绿」的**双侧信号**。
        """
        # capability 未放行（红形态的正面确认）
        assert E.manifest_capability_enabled() is False, (
            "capability 已放行 ⇒ 红形态已变、本条登记过期，需更新 spec 状态"
        )
        # adapter_id 仍为 None
        assert slice_entry.get("adapter_id") is None, (
            "adapter_id 已设 ⇒ 红形态已变、本条登记过期，需更新 spec 状态"
        )
        # migration_state 仍为 legacy
        assert slice_entry.get("migration_state") == "legacy_fake_bidirectional", (
            "migration_state 已变 ⇒ 红形态已变、本条登记过期，需更新 spec 状态"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 补充：publish_definitions 的签名与编排完整性
#
# 🔴 publish_definitions 与 resolve_published_frozen_definitions 是五环编排的
#    两个入口。本节只验签名/结构（不真调 —— 那需要真 DB session + publisher），
#    确保上游 test_task75 的 AST 判据能找到这两个符号。
# ═══════════════════════════════════════════════════════════════════════════


class TestPublishDefinitionsCompleteness:
    """publish_definitions 的签名与编排完整性（不真调）。"""

    def test_publish_definitions_accepts_publisher_arg(self) -> None:
        """publish_definitions(publisher) 签名正确。"""
        import inspect

        sig = inspect.signature(E.publish_definitions)
        params = list(sig.parameters.keys())
        assert "publisher" in params

    def test_resolve_published_frozen_definitions_accepts_three_args(self) -> None:
        """resolve_published_frozen_definitions(session, representation, contract) 签名正确。"""
        import inspect

        sig = inspect.signature(E.resolve_published_frozen_definitions)
        params = set(sig.parameters.keys())
        assert {"session", "representation", "contract"} <= params

    def test_phase5_definitions_dataclass_exists(self) -> None:
        """Phase5Definitions 数据类存在且有 as_dict 方法。"""
        assert hasattr(E, "Phase5Definitions")
        assert hasattr(E.Phase5Definitions, "as_dict")

    def test_phase5_definitions_fields_cover_five_rings(self) -> None:
        """Phase5Definitions 的字段覆盖五环产物。

        五环产物最终汇聚到 Phase5Definitions，字段名必须包含：
        authority_model / template / instrumentation / contract / bundle。
        """
        import dataclasses

        fields = {f.name for f in dataclasses.fields(E.Phase5Definitions)}
        for keyword in ("authority_model", "template", "instrumentation", "contract", "bundle"):
            matching = [f for f in fields if keyword in f]
            assert matching, (
                f"Phase5Definitions 缺少含 {keyword!r} 的字段 ⇒ 五环产物不完整"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 五环自洽：环之间的依赖关系
#
# 这些判据验证五环**之间**的约束，不重复验证单环。
# ═══════════════════════════════════════════════════════════════════════════


class TestFiveRingCoherence:
    """五环之间的依赖关系与自洽性。"""

    def test_adapter_id_consistent_across_rings(self) -> None:
        """ADAPTER_ID 在 provider / contract payload / 磁盘契约 / 注册表四处一致。"""
        from app.services.workpaper_sync.adapters.registry import (
            DELIVERED_PER_ENTRY_CONTRACTS,
        )

        # provider 常量
        provider_id = E.ADAPTER_ID
        # contract payload
        payload = E.build_contract_payload()
        payload_id = payload["contract_id"]
        # 磁盘契约
        disk_contract = E.load_contract_from_disk()
        disk_id = disk_contract.contract_id
        # 注册表
        reg_entry = next(
            r for r in DELIVERED_PER_ENTRY_CONTRACTS if r["contract_id"] == provider_id
        )
        reg_id = reg_entry["contract_id"]

        assert provider_id == payload_id == disk_id == reg_id, (
            f"ADAPTER_ID 不一致：provider={provider_id}, payload={payload_id}, "
            f"disk={disk_id}, registry={reg_id}"
        )

    def test_entry_id_consistent_across_rings(self) -> None:
        """ENTRY_ID 在 provider / 注册表 / slice 三处一致。"""
        from app.services.workpaper_sync.adapters.registry import (
            DELIVERED_PER_ENTRY_CONTRACTS,
        )

        provider_eid = E.ENTRY_ID
        reg_entry = next(
            r for r in DELIVERED_PER_ENTRY_CONTRACTS if r["contract_id"] == E.ADAPTER_ID
        )
        reg_eid = reg_entry["entry_id"]
        # slice
        slice_data = json.loads(_SLICE.read_text(encoding="utf-8"))
        slice_eids = [e.get("entry_id") for e in slice_data["independent_entries"]]

        assert provider_eid == reg_eid
        assert provider_eid in slice_eids

    def test_ring1_is_prerequisite_for_ring2(self) -> None:
        """环 ① 产物（payload）与环 ② 产物（磁盘文件）的 digest 必须一致。

        这就是 assert_contract_file_matches_source 的核心约束 —— 本条用独立路径验证。
        """
        from app.services.workpaper_sync.definitions import canonical_digest

        payload = E.build_contract_payload()
        disk_data = json.loads(E.contract_file_path().read_text(encoding="utf-8"))
        assert canonical_digest(payload) == canonical_digest(disk_data), (
            "payload digest ≠ disk digest ⇒ 环 ① 与环 ② 脱钩"
        )

    def test_ring3_blocks_ring5(self) -> None:
        """环 ③（capability）未通时环 ⑤（注册）被阻塞。

        ✅ 现在就能绿：验证的是**阻塞关系**而非**放行**。
        """
        # capability 未放行
        assert E.manifest_capability_enabled() is False, (
            "capability 已放行 ⇒ 五环依赖关系需更新"
        )
        # 注册返回空
        result = E.attach_pilot_adapters(registry=None)
        assert result == (), (
            "capability 未放行但 attach 返回非空 ⇒ 环 ③ 未正确阻塞环 ⑤"
        )
