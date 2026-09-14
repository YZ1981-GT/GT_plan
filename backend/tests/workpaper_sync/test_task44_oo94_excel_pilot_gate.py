# -*- coding: utf-8 -*-
"""Task 44 守卫：真实 OnlyOffice 9.4 Excel pilot gate。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 4 Task 44
Requirements: 4.10, 4.11, 5.5, 6.8, 6.11, 6.16, 8.10, 10.2, 10.3, 10.4, 10.9, 10.10,
12.2, 12.10, 14.2, 14.3, 14.5, 14.6, 14.7, 14.8, 14.9, 14.16
Properties: **P18 / P25 / P26 / P29 / P43 / P44 / P49 / P55 / P56 / P58 / P62 / P63 /
P64 / P65 / P66 / P69**

判据取向（本 spec 反复实测出来的三条）
------------------------------------

1. **不用字符串存在判据**。「gate 里写了 finalize」不能证明 gate 真读了 finalize ——
   每条 finalize/准入判据都用**替身翻转**：把生产信号改成"已就绪"，gate 的结论必须跟着变。
   这同时排掉了 `return False` 硬编码（它在替身下不会变）。
2. **validator 必须双向可达**。只测"缺记录 ⇒ unverifiable"会让 validator 成为死代码
   （假绿第①源）：给齐记录后必须真能 `passed`，改坏一个字段必须 `failed`。
3. **顺序判据落在行为上**。upstream-gap 排在 black-box 之前这件事，除了源码位置还要有
   **交叉形态**（既有欠账又需黑盒）的真实判定 —— Task 43 的 required set 里没有这种
   形态，只能用反事实；本文件补上合成的交叉形态。
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
_GATE_PY = _BACKEND / "scripts/check/check_task44_oo94_excel_pilot_gate.py"
_GEN_PY = _BACKEND / "scripts/gen/generate_workpaper_task44_pilot_probe_registry.py"

if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def _load(name: str, path: Path) -> ModuleType:
    """按路径加载脚本模块。

    🔴 必须先注册进 `sys.modules` 再 exec：目标模块用了
    `from __future__ import annotations`，`@dataclass` 解析字符串注解时会去
    `sys.modules[cls.__module__]` 取命名空间，不注册即 `AttributeError: 'NoneType'
    object has no attribute '__dict__'`（实测踩过）。
    """
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, path
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


G = _load("_task44_gate_under_test", _GATE_PY)

_PILOT_CLASSES = {"simple_checklist", "d2_large_json", "h1_grouped_dynamic", "g7_two_level_dynamic"}


@pytest.fixture(scope="module")
def facts_by_class() -> dict[str, Any]:
    """四个 pilot 的实测事实（一次采集，全模块复用）。"""
    return {ref.pilot_class: G.collect_pilot_facts(ref) for ref in G.PILOTS}


@pytest.fixture(scope="module")
def report() -> dict[str, Any]:
    return G.build_report()


# ═══════════════════════════════════════════════════════════════════════════
# 1. probe 分母与 tasks.md / design.md 双向锁
# ═══════════════════════════════════════════════════════════════════════════


class TestProbeRegistryIsLockedToTaskText:
    """**Validates: Requirements 12.2, 14.9**"""

    def test_every_probe_anchor_occurs_verbatim_in_task_44_body(self) -> None:
        counts = G.assert_probes_anchored_in_task_text()
        assert set(counts) == {spec.anchor for spec in G.ALL_PROBE_SPECS}
        assert all(hits >= 1 for hits in counts.values()), counts

    def test_task_body_is_located_by_number_not_line_and_survives_a_ticked_checkbox(self) -> None:
        """勾选 Task 44 不得让本门失效：checkbox 是簿记，不是事实。"""
        import re

        original = G.read_task_body()
        raw_text = G._TASKS_MD.read_bytes().decode("utf-8")
        # 不管当前 checkbox 是 [ ] / [x] / [-] / [~]，都替换成 [x] 验证 gate 不被影响
        ticked = re.sub(r"- \[[ x~\-]\] 44\. ", "- [x] 44. ", raw_text, count=1)
        assert ticked != raw_text or "[x] 44." in raw_text
        ticked_body = G.read_task_body(text=ticked)
        # 把两边 checkbox 都抹成统一形态后正文应该相等
        normalized_original = re.sub(r"^\- \[[ x~\-]\] 44\. ", "- [ ] 44. ", original)
        normalized_ticked = re.sub(r"^\- \[[ x~\-]\] 44\. ", "- [ ] 44. ", ticked_body)
        assert normalized_ticked == normalized_original

    def test_removing_one_enumerated_item_from_the_task_text_fails_the_gate(self) -> None:
        """🔴 正文枚举项被删 ⇒ 立刻抛，且诊断点名是哪条 probe 脱钩。"""
        body = G.read_task_body()
        target = "download-only 三实体为 0"
        assert target in body
        with pytest.raises(G.GateStructuralError) as excinfo:
            G.assert_probes_anchored_in_task_text(task_body=body.replace(target, "（删了）"))
        assert "scenario.download_only_zero_three_entities" in str(excinfo.value)
        assert target in str(excinfo.value)

    def test_all_twenty_two_declared_requirements_are_claimed_by_a_probe(self) -> None:
        payload = G.probe_registry_payload()
        assert len(payload["task_requirements"]) == 22, payload["task_requirements"]
        assert payload["requirements_without_probe"] == []
        G.assert_registry_coverage(payload)

    def test_an_unclaimed_requirement_is_a_structural_failure(self) -> None:
        payload = dict(G.probe_registry_payload())
        payload["requirements_without_probe"] = ["14.8"]
        with pytest.raises(G.GateStructuralError, match="14.8"):
            G.assert_registry_coverage(payload)

    def test_sixteen_properties_are_declared_and_each_lands_on_a_probe(self) -> None:
        payload = G.probe_registry_payload()
        assert len(G.DECLARED_PROPERTIES) == 16
        assert payload["properties_without_probe"] == []
        assert payload["properties_claimed_but_not_declared"] == []
        titles = payload["property_titles"]
        assert set(titles) == set(G.DECLARED_PROPERTIES)
        assert all(title.strip() for title in titles.values())

    def test_a_property_missing_from_design_md_is_a_structural_failure(self) -> None:
        """design.md 里没有定义的 Property 无从"独立验证" ⇒ 必须抛。"""
        with pytest.raises(G.GateStructuralError, match="P999"):
            G.design_property_titles(("P49", "P999"))

    def test_generated_registry_data_file_is_fresh(self) -> None:
        """`backend/data/` 的投影必须与 gate 现算逐字节相等。"""
        generator = _load("_task44_registry_gen", _GEN_PY)
        assert generator.main(["--check"]) == 0

    def test_probe_row_count_is_the_declared_product(self) -> None:
        payload = G.probe_registry_payload()
        assert payload["per_pilot_probe_count"] == len(G.PER_PILOT_PROBES) == 42
        assert payload["gate_probe_count"] == len(G.GATE_PROBES) == 5
        assert payload["total_probe_rows"] == 42 * 4 + 5 == 173

    def test_every_production_ref_resolves_today(self) -> None:
        """probe 声明的生产符号必须都还在 —— 改名/删除立刻抛。"""
        for spec in G.ALL_PROBE_SPECS:
            assert G._resolve_production_refs(spec) == spec.production_refs

    def test_a_vanished_production_symbol_fails_the_probe(self) -> None:
        spec = replace(
            G.PER_PILOT_PROBES[0],
            production_refs=("app.services.workpaper_sync.rooms:NoSuchSymbol",),
        )
        with pytest.raises(G.GateStructuralError, match="NoSuchSymbol"):
            G._resolve_production_refs(spec)


class TestScenarioDenominatorIsBidirectional:
    """**Validates: Requirements 12.2, 12.10**"""

    def test_every_required_scenario_of_every_pilot_has_a_declared_probe(
        self, facts_by_class: dict[str, Any]
    ) -> None:
        declared = {spec.scenario_id for spec in G._SCENARIO_PROBES}
        for pilot_class, facts in facts_by_class.items():
            assert set(facts.required_scenario_ids) <= declared, pilot_class

    def test_dropping_one_scenario_probe_makes_the_denominator_shrink_detectable(
        self, facts_by_class: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """🔴 反向锁：required set 里有场景却没人声明 probe ⇒ 结构性失效。"""
        trimmed = tuple(
            spec for spec in G._SCENARIO_PROBES if spec.scenario_id != "single_participant_close"
        )
        monkeypatch.setattr(G, "_SCENARIO_PROBES", trimmed)
        with pytest.raises(G.GateStructuralError, match="single_participant_close"):
            G._scenario_denominator_facts(facts_by_class["g7_two_level_dynamic"])

    def test_declared_but_not_required_is_exactly_the_dynamic_family(
        self, facts_by_class: dict[str, Any]
    ) -> None:
        """动态族进不了 required set 是**已登记的上游欠账**，不是漏声明。"""
        for pilot_class, facts in facts_by_class.items():
            denominator = G._scenario_denominator_facts(facts)
            assert denominator["declared_not_required"] == [
                "dynamic_row_add_delete_reorder_copy"
            ], pilot_class

    def test_missing_dynamic_scenario_maps_to_a_registered_upstream_debt(
        self, facts_by_class: dict[str, Any]
    ) -> None:
        """四个 pilot 都必须指向**已注册**的那条同源欠账（不得重复发明一个新名字）。"""
        for pilot_class, facts in facts_by_class.items():
            debt = G._debt_for_missing_scenario(facts, "dynamic_row_add_delete_reorder_copy")
            assert debt is not None, pilot_class
            assert "DYNAMIC_FAMILY_GATED_ON_MOUNT_CARDINALITY" in debt, pilot_class

    def test_task40_pilot_never_registered_the_dynamic_family_debt(
        self, facts_by_class: dict[str, Any]
    ) -> None:
        """🔴 实测缺陷（本门量出来的）：Tasks 41/42/43 都登记了动态族欠账，Task 40 没有。

        gate 因此跨 pilot 沿用已注册的名字，并在 notes 里点名"本 pilot 未登记" ——
        既不重复发明名字，也不把缺登记掩盖成"没有欠账"。
        """
        registered = {
            pilot_class: [n for n in facts.registered_debts if "DYNAMIC_FAMILY" in n]
            for pilot_class, facts in facts_by_class.items()
        }
        assert registered["simple_checklist"] == []
        for pilot_class in ("d2_large_json", "h1_grouped_dynamic", "g7_two_level_dynamic"):
            assert registered[pilot_class] == [
                "UPSTREAM_DEBT_DYNAMIC_FAMILY_GATED_ON_MOUNT_CARDINALITY"
            ], pilot_class
        debt = G._debt_for_missing_scenario(
            facts_by_class["simple_checklist"], "dynamic_row_add_delete_reorder_copy"
        )
        assert "Task 40 的 pilot 模块**未**登记这条同源欠账" in debt

    def test_a_scenario_probe_without_a_production_oracle_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            G,
            "PER_PILOT_PROBES",
            G.PER_PILOT_PROBES + (replace(G._SCENARIO_PROBES[0], probe_id="x", scenario_id="nope"),),
        )
        with pytest.raises(G.GateStructuralError, match="nope"):
            G._assert_scenarios_known()

    def test_close_predicate_is_cross_checked_against_the_raw_manifest(
        self, facts_by_class: dict[str, Any]
    ) -> None:
        """close 谓词双源：生产推导 vs 直接读 manifest 三字段，不得只用一侧。"""
        for pilot_class, facts in facts_by_class.items():
            assert facts.close_required is True, pilot_class
            assert facts.close_predicate_raw is True, pilot_class
            assert facts.editability == "editable"
            assert facts.room_model == "shared"
            assert facts.capability != "bidirectional"


# ═══════════════════════════════════════════════════════════════════════════
# 2. finalize 状态：真实反读 + 替身翻转（本文件最重要的一节）
# ═══════════════════════════════════════════════════════════════════════════


class TestFinalizeStateIsReadFromProduction:
    """**Validates: Requirements 12.2, 8.10** · Property 49"""

    def test_all_four_pilots_are_blocked_before_task_36_finalize(
        self, facts_by_class: dict[str, Any]
    ) -> None:
        assert set(facts_by_class) == _PILOT_CLASSES
        for pilot_class, facts in facts_by_class.items():
            signals = facts.signals
            assert signals.admitted is False, pilot_class
            assert signals.capability_enabled is False
            assert signals.adapter_registered is False
            # Task 75 起观测器**已交付** ⇒ 探针按异常类型分型判它 available；
            # 「今天仍不准入」由 capability_enabled / adapter_registered 两项承担。
            assert signals.published_identity_observer == "available"
            assert signals.attach_without_representation == ()
            assert signals.attach_with_representation_without_bundle == ()

    def test_observer_debt_is_cleared_and_the_detail_says_why(
        self, facts_by_class: dict[str, Any]
    ) -> None:
        """诊断必须指名道姓 —— 「finalize 没做」和「观测器缺失」是两件事。

        Task 75 结清了后者：四个 pilot 的 `UPSTREAM_DEBT_PUBLISHED_IDENTITY_OBSERVER` 已删，
        探针 detail 改为指名观测器自己的 shape 错误（拿 `None` 去问的必然结果）。
        「今天仍 finalize 不成」的原因换成**供给**，由 `upstream_gap` 行的 debt 文本承载。
        """
        for pilot_class, facts in facts_by_class.items():
            assert "RepresentationShapeError" in facts.signals.observer_detail, pilot_class
            assert not any(
                "PUBLISHED_IDENTITY_OBSERVER" in name for name in facts.registered_debts
            ), f"{pilot_class} 仍登记着已结清的观测器欠账"

    @pytest.mark.parametrize("pilot_class", sorted(_PILOT_CLASSES))
    def test_each_signal_flips_independently_under_substitution(self, pilot_class: str) -> None:
        """🔴 逐个信号替身翻转 —— 比"四个一起翻"强：后者在三个硬编码时也会通过。"""
        ref = next(r for r in G.PILOTS if r.pilot_class == pilot_class)
        module = G.load_pilot_module(ref)
        from app.services.workpaper_sync.adapters import registry as registry_module

        baseline = G.probe_finalize_signals(module)
        assert baseline.admitted is False

        saved_capability = module.assert_manifest_capability_enabled
        try:
            module.assert_manifest_capability_enabled = lambda **_k: None
            flipped = G.probe_finalize_signals(module)
        finally:
            module.assert_manifest_capability_enabled = saved_capability
        assert flipped.capability_enabled is True
        assert flipped.capability_reject == ""
        assert G.probe_finalize_signals(module).capability_enabled is False

        async def _observer(**_kwargs: Any) -> object:
            return object()

        saved_observer = module.resolve_published_frozen_definitions
        try:
            module.resolve_published_frozen_definitions = _observer
            flipped = G.probe_finalize_signals(module)
        finally:
            module.resolve_published_frozen_definitions = saved_observer
        assert flipped.published_identity_observer == "available"
        # 🔴 Task 75 起真实基线也是 `available`（观测器已交付；拿 `None` 去问它抛
        #    `RepresentationShapeError` 正是**已实现**的行为）。信号的可翻转性改由
        #    `_unimplemented_observer` 证明：换成抛别的异常 ⇒ 立刻退回 `unavailable`。
        assert G.probe_finalize_signals(module).published_identity_observer == "available"

        async def _unimplemented_observer(**_kwargs: Any) -> object:
            raise RuntimeError("观测器未实现（合成）")

        try:
            module.resolve_published_frozen_definitions = _unimplemented_observer
            regressed = G.probe_finalize_signals(module)
        finally:
            module.resolve_published_frozen_definitions = saved_observer
        assert regressed.published_identity_observer == "unavailable", (
            "换成「抛非 shape 异常」后信号没退回 unavailable ⇒ 探针的三态分型是装饰"
        )

        class _Stand:
            def registrations(self) -> tuple[Any, ...]:
                return (type("R", (), {"adapter_id": str(module.PILOT_ADAPTER_ID)})(),)

        saved_registry = registry_module.build_production_registry
        try:
            registry_module.build_production_registry = lambda: _Stand()
            flipped = G.probe_finalize_signals(module)
        finally:
            registry_module.build_production_registry = saved_registry
        assert flipped.adapter_registered is True
        assert str(module.PILOT_ADAPTER_ID) in flipped.registered_adapter_ids
        assert G.probe_finalize_signals(module).adapter_registered is False

        async def _attach(_registry: Any, *, session: Any) -> tuple[str, ...]:
            return (str(module.PILOT_ADAPTER_ID),)

        saved_attach = module.attach_pilot_adapters
        try:
            module.attach_pilot_adapters = _attach
            flipped = G.probe_finalize_signals(module)
        finally:
            module.attach_pilot_adapters = saved_attach
        assert flipped.attach_without_representation == (str(module.PILOT_ADAPTER_ID),)
        assert G.probe_finalize_signals(module).attach_without_representation == ()

    def test_admitted_requires_all_four_signals(self) -> None:
        """准入是**合取**：任一缺失即不准入。逐项掰掉一个，`admitted` 必须变 False。"""
        ready = G.FinalizeSignals(
            capability_enabled=True,
            capability_reject="",
            adapter_registered=True,
            registered_adapter_ids=("x",),
            published_identity_observer="available",
            observer_detail="",
            attach_without_representation=("x",),
            attach_with_representation_without_bundle=("x",),
        )
        assert ready.admitted is True
        for field_name, broken in (
            ("capability_enabled", False),
            ("adapter_registered", False),
            ("published_identity_observer", "unavailable"),
            ("attach_without_representation", ()),
        ):
            assert replace(ready, **{field_name: broken}).admitted is False, field_name

    def test_the_four_pilots_short_circuit_at_different_gates(
        self, facts_by_class: dict[str, Any]
    ) -> None:
        """🔴 本门量出来的真实差异：Tasks 41/42/43 在 capability 门就 `return ()` 且
        **一次库都不读**（Task 41 因 raise 让整条 sync 路由 500 之后改的形态），
        而 Task 40 的版本先查 `entry_state`。

        判据落在"读了几次库"这个实测量上 —— 谁把两道门的顺序重排，这条就打红。
        """
        reads = {
            pilot_class: facts.signals.attach_session_reads
            for pilot_class, facts in facts_by_class.items()
        }
        assert reads["simple_checklist"] >= 1, reads
        for pilot_class in ("d2_large_json", "h1_grouped_dynamic", "g7_two_level_dynamic"):
            assert reads[pilot_class] == 0, reads
        for pilot_class, facts in facts_by_class.items():
            assert facts.signals.attach_without_representation == (), pilot_class

    def test_the_stub_session_is_the_only_substituted_part(self) -> None:
        """替身只替换 DB：被调用的 `attach_pilot_adapters` 是生产函数本体。"""
        ref = next(r for r in G.PILOTS if r.pilot_class == "simple_checklist")
        module = G.load_pilot_module(ref)
        assert module.attach_pilot_adapters.__module__ == ref.module_path
        session = G._StubSession([None])
        import asyncio

        from app.services.workpaper_sync.adapters.registry import (
            WorkpaperSyncAdapterRegistry,
        )
        from app.services.workpaper_sync.entry_profile import load_entry_manifest

        assert (
            asyncio.run(
                module.attach_pilot_adapters(
                    WorkpaperSyncAdapterRegistry(manifest=load_entry_manifest()),
                    session=session,
                )
            )
            == ()
        )
        assert session.calls >= 1

    def test_gate_probe_admission_is_state_sensitive_passes_for_all_four(self) -> None:
        ok, detail, observed = G.gate_probe_admission_is_state_sensitive()
        assert ok is True, detail
        assert set(observed) == _PILOT_CLASSES
        for pilot_class, data in observed.items():
            assert data["real_admitted"] is False, pilot_class
            assert data["substituted_admitted"] is True, pilot_class
            # Task 75 起观测器已交付 ⇒ 真实态是 available；`real_admitted is False` 由
            # capability_enabled / adapter_registered 两项承担（上面已逐条断言）。
            assert data["real_observer"] == "available"
            assert data["substituted_observer"] == "available"

    def test_a_hardcoded_admission_would_fail_the_state_sensitivity_probe(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """🔴 反向自检：把 `probe_finalize_signals` 换成恒 False 的硬编码实现后，
        `gate.admission_is_state_sensitive` 必须变 False —— 证明这条 probe 真能拦住硬编码。
        """
        blocked = G.FinalizeSignals(
            capability_enabled=False,
            capability_reject="hardcoded",
            adapter_registered=False,
            registered_adapter_ids=(),
            published_identity_observer="unavailable",
            observer_detail="hardcoded",
            attach_without_representation=(),
            attach_with_representation_without_bundle=(),
        )
        monkeypatch.setattr(G, "probe_finalize_signals", lambda _module: blocked)
        ok, detail, _observed = G.gate_probe_admission_is_state_sensitive()
        assert ok is False
        assert "未随信号改变" in detail


# ═══════════════════════════════════════════════════════════════════════════
# 3. 判定顺序不可交换
# ═══════════════════════════════════════════════════════════════════════════


class TestOrderingIsNotCommutable:
    """**Validates: Requirements 14.9** · Property 49"""

    def test_upstream_gap_branch_precedes_black_box_branch_in_both_layers(self) -> None:
        facts = G.ordering_facts()
        assert facts["production_upstream_gap_decided_before_black_box"] is True
        assert facts["gate_upstream_gap_decided_before_black_box"] is True
        assert 0 <= facts["production_upstream_debt_branch_line"] < facts[
            "production_black_box_branch_line"
        ]
        assert 0 <= facts["gate_upstream_debt_branch_line"] < facts["gate_black_box_branch_line"]

    def test_upstream_gap_is_failed_not_unverifiable(self, report: dict[str, Any]) -> None:
        rows = [
            row
            for row in report["probe_rows"]
            if row["error_code"] == "upstream_gap"
        ]
        assert rows, "今天必须有 upstream_gap 行（四个 pilot 各七条）"
        assert {row["result"] for row in rows} == {"failed"}
        assert len(rows) == 28, len(rows)

    def test_counterfactual_without_debt_changes_the_verdict(
        self, facts_by_class: dict[str, Any]
    ) -> None:
        """行为侧证据：清空 `upstream_debt` 后同一条 probe 的判定必须不同。"""
        env = G.default_environment()
        for pilot_class, facts in facts_by_class.items():
            counterfactual = G.upstream_gap_counterfactual(facts, env)
            assert set(counterfactual) == {
                "scenario.same_application_higher_sequence_fold",
                "scenario.wrong_prior_confirmation_bundle_fence_contributor_rejected",
            }, pilot_class
            for probe_id, data in counterfactual.items():
                assert data["with_debt"] == {"result": "failed", "error_code": "upstream_gap"}
                assert data["without_debt"]["result"] != "failed", probe_id
                assert data["differs"] is True

    def test_crossing_shape_debt_and_black_box_together_still_lands_on_upstream_gap(
        self, facts_by_class: dict[str, Any]
    ) -> None:
        """🔴 交叉形态（既有欠账、又需真实黑盒）—— Task 43 的 required set 里没有这种
        形态，只能用反事实；这里合成出来，让"顺序生效"有直接判据。
        """
        from app.services.workpaper_sync import pilot_harness as ph

        facts = facts_by_class["h1_grouped_dynamic"]
        spec = next(s for s in G._SCENARIO_PROBES if s.scenario_id == "identity_retention")
        oracle = ph.SCENARIO_ORACLES["identity_retention"]
        assert oracle.needs_black_box is True
        assert oracle.upstream_debt is None
        patched = dict(ph.SCENARIO_ORACLES)
        patched["identity_retention"] = replace(oracle, upstream_debt="合成欠账：实现缺失")
        original = ph.SCENARIO_ORACLES
        try:
            ph.SCENARIO_ORACLES = patched
            row = G.evaluate_probe(
                spec,
                facts,
                environment=G.default_environment(),
                record=None,
                supplied_inputs=frozenset(),
            )
        finally:
            ph.SCENARIO_ORACLES = original
        assert row.result == "failed"
        assert row.error_code == "upstream_gap"
        assert "real_black_box_not_executed" in row.blocking_conditions
        assert "合成欠账" in " ".join(row.notes)

    def test_black_box_probes_stay_unverifiable_even_when_the_pilot_is_admitted(
        self, facts_by_class: dict[str, Any]
    ) -> None:
        """接上 finalize 但没有真实 OO ⇒ 黑盒场景必须仍是 unverifiable，不得自动刷绿。"""
        facts = replace(facts_by_class["g7_two_level_dynamic"], signals=_ready_signals())
        spec = next(s for s in G._SCENARIO_PROBES if s.scenario_id == "identity_retention")
        row = G.evaluate_probe(
            spec,
            facts,
            environment=G.default_environment(),
            record={"artifact_sha256": "a" * 64},
            supplied_inputs=frozenset({"artifact_digests", "onlyoffice_forcesave"}),
        )
        assert row.result == "unverifiable"
        assert row.error_code == "real_onlyoffice_not_executed"

    def test_schema_unrepresentable_is_decided_first(self, report: dict[str, Any]) -> None:
        rows = [
            row
            for row in report["probe_rows"]
            if row["scenario_id"] == "quarantined_rejects_application_and_engine"
        ]
        assert len(rows) == 4
        assert {row["result"] for row in rows} == {"unverifiable"}
        assert {row["error_code"] for row in rows} == {"scenario_kind_unrepresentable"}


def _ready_signals() -> Any:
    """「已 finalize」的替身信号（只在守卫里用，生产路径不存在这条路）。"""
    return G.FinalizeSignals(
        capability_enabled=True,
        capability_reject="",
        adapter_registered=True,
        registered_adapter_ids=("stand-in",),
        published_identity_observer="available",
        observer_detail="substituted",
        attach_without_representation=("stand-in",),
        attach_with_representation_without_bundle=("stand-in",),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 4. 不得以文档声明通过
# ═══════════════════════════════════════════════════════════════════════════


class TestNoDocumentaryPass:
    """**Validates: Requirements 14.9, 12.2** · Property 49, Property 69"""

    @pytest.mark.parametrize(
        "payload",
        [
            {"result": "passed"},
            {"probes": {"xlsx/x": {"scenario.rollback": {"verdict": "passed"}}}},
            {"probes": [{"aggregate_result": "verified"}]},
            {"a": {"b": [{"c": {"passed": True}}]}},
            {"environment": {"status": "verified"}},
            {"outcome": "ok"},
        ],
    )
    def test_every_burial_form_of_a_result_claim_is_rejected(self, payload: Any) -> None:
        with pytest.raises(G.DocumentaryClaimRejected):
            G.assert_records_carry_no_claim(payload)

    def test_a_record_without_claims_is_accepted(self) -> None:
        G.assert_records_carry_no_claim(
            {"environment": {"onlyoffice_build": "9.4.0"}, "probes": {"x": {"y": {"z": 1}}}}
        )

    def test_load_execution_records_rejects_a_claiming_file(self, tmp_path: Path) -> None:
        path = tmp_path / "records.json"
        path.write_bytes(
            json.dumps({"probes": {"e": {"p": {"result": "passed"}}}}).encode("utf-8")
        )
        with pytest.raises(G.DocumentaryClaimRejected):
            G.load_execution_records(path)

    def test_gate_probe_runs_the_refusal_path_for_real(self) -> None:
        ok, detail, payload = G.gate_probe_no_documentary_pass()
        assert ok is True, detail
        assert set(payload["samples"]) == {"top_level", "nested", "in_list"}
        assert all(v.startswith("rejected") for v in payload["samples"].values())

    def test_the_probe_would_fail_if_the_refusal_stopped_working(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """🔴 反向自检：把拒绝路径改成放行后这条 probe 必须变 False。"""
        monkeypatch.setattr(G, "assert_records_carry_no_claim", lambda *_a, **_k: None)
        ok, _detail, payload = G.gate_probe_no_documentary_pass()
        assert ok is False
        assert set(payload["samples"].values()) == {"NOT-REJECTED"}

    def test_forbidden_keys_cover_the_result_vocabulary(self) -> None:
        assert G.FORBIDDEN_RECORD_KEYS == frozenset(
            {"result", "verdict", "passed", "aggregate_result", "status", "outcome"}
        )


# ═══════════════════════════════════════════════════════════════════════════
# 5. validator 双向可达（防"新增即死代码"）
# ═══════════════════════════════════════════════════════════════════════════

_REAL_ENV_BUILDS = ("9.4.0.1234", "Chromium 131.0.6778.86")


def _real_environment() -> Any:
    return G.Environment(
        onlyoffice_build=_REAL_ENV_BUILDS[0],
        browser_build=_REAL_ENV_BUILDS[1],
        source_commit="deadbeef",
    )


def _uuids(count: int) -> list[str]:
    import uuid as _uuid

    return [str(_uuid.uuid4()) for _ in range(count)]


def _oo_timeline() -> dict[str, str]:
    from app.services.workpaper_sync import pilot_harness as ph

    base = "2026-08-16T0{}:00:00+00:00"
    return {key: base.format(index) for index, key in enumerate(ph.OO_TO_HTML_TIMELINE_ORDER)}


def _recovery_timeline() -> dict[str, str]:
    from app.services.workpaper_sync import pilot_harness as ph

    base = "2026-08-16T0{}:00:00+00:00"
    return {key: base.format(index) for index, key in enumerate(ph.RECOVERY_TIMELINE_ORDER)}


def _full_records(facts: Any) -> dict[str, dict[str, Any]]:
    """一份**形态完整**的执行记录（字段齐、数值自洽），用于证明判据双向可达。

    🔴 它不是"假装 pilot 通过了"：这些记录只喂给 validator 单测，且喂它们的前提是
    把 `signals` 换成替身。生产路径上四个 pilot 未准入，一条也进不到这一层
    （`test_no_probe_can_pass_on_the_real_unadmitted_pilots` 把这件事直接测了）。
    """
    from app.services.workpaper_sync import excel_instrumentation as ei

    contributors = _uuids(2)
    return {
        "channel.playwright_network_console": {
            "network_requests": [{"url": "/api/wp-sync/commands", "status": 202}],
            "console_messages": [{"level": "info", "text": "mounted"}],
            "har_sha256": "b" * 64,
        },
        "channel.recovery_application_operation_timeline": {
            "operation_timeline": _oo_timeline(),
            "recovery_timeline": _recovery_timeline(),
        },
        "channel.db_timestamps": {
            "clock_source": "server",
            "db_timestamps": _oo_timeline(),
        },
        "channel.published_result_representation": {
            "representation_id": _uuids(1)[0],
            "representation_state": "published",
            "representation_kind": "result",
            "projection_sha256": "c" * 64,
            "extracted_projection_sha256": "c" * 64,
            "candidate_participated": False,
        },
        "channel.authority_model": {
            "authority_model": facts.authority_model,
            "authority_model_definition_sha256": facts.authority_model_definition_sha256,
        },
        "channel.bundle_digest_typed_slots": {
            "bundle_sha256": facts.bundle_sha256,
            "typed_slots": {
                "template": {"type": "definition", "digest": facts.template_definition_sha256},
                "instrumentation": {
                    "type": "definition",
                    "digest": facts.instrumentation_definition_sha256,
                },
                "contract": {"type": "definition", "digest": facts.contract_canonical_sha256},
            },
        },
        "channel.artifact_identity_inventory": {
            "artifact_sha256": "d" * 64,
            "identity_inventory": {
                "metadata_sheet": ei.GT_SYNC_SHEET_NAME,
                "defined_names": ["GT_SYNC_ENTRY"],
                "row_uuids": ["row-1", "row-2"],
            },
        },
        "channel.per_scenario_distinct_application_ids": {
            "per_scenario_application_ids": {
                scenario_id: _uuids(1) for scenario_id in facts.required_scenario_ids
            }
        },
        "channel.full_data_restoration": {
            "counts_before": {"working_paper_content_application": 0, "workpaper_artifact": 3},
            "counts_after": {"working_paper_content_application": 0, "workpaper_artifact": 3},
            "restored_at": "2026-08-16T09:00:00+00:00",
        },
        "close_aspect.exactly_one_capture_on_applicable_paths": {
            "close_captures_by_scenario": {
                "single_participant_close": 1,
                "two_user_close_order_a_then_b": 1,
                "two_user_close_order_b_then_a": 1,
                "b_close_before_a_forcesave_terminal": 1,
                "b_close_after_a_forcesave_terminal": 1,
                "close_leader_revoked_successor_exactly_one": 1,
                "close_leader_revoked_no_successor_recovery_required": 0,
                "close_reconciler_reentrant_exactly_one_capture": 1,
            }
        },
        "close_aspect.aggregate_artifact": {
            "artifact_sha256": "e" * 64,
            "contributor_user_ids": contributors,
            "forcesave_initiator": contributors[0],
        },
        "close_aspect.initiator_route_contributors_separated": {
            "initiator_participant_id": "participant-a",
            "route_credential_id": "route-1",
            "contributor_row_ids": ["contributor-row-1", "contributor-row-2"],
        },
        "close_aspect.revoke_drop_generation_rotation": {
            "revoked_participant_id": "participant-b",
            "oo_drop_observed": False,
            "write_fence_epoch_before": 3,
            "write_fence_epoch_after": 4,
            "generation_before": "gen-1",
            "generation_after": "gen-2",
            "cancelled_request_ids": _uuids(1),
        },
    }


def _supplied_for(spec: Any) -> frozenset[str]:
    """该 probe 声明需要的证据种类（scenario probe 从生产 oracle 现取）。"""
    from app.services.workpaper_sync import pilot_harness as ph

    if spec.scenario_id:
        return frozenset(i.value for i in ph.SCENARIO_ORACLES[spec.scenario_id].requires)
    return frozenset(spec.evidence_inputs)


class TestValidatorsAreBidirectionallyReachable:
    """**Validates: Requirements 6.11, 6.16, 8.10, 10.2, 10.3, 10.4, 10.9, 12.10, 14.5,
    14.6, 14.8, 14.9, 14.16** · Property 29, 44, 58, 63, 64, 65, 66, 69"""

    @pytest.mark.parametrize(
        "probe_id",
        sorted(
            spec.probe_id
            for spec in G.PER_PILOT_PROBES
            if spec.validator is not None
        ),
    )
    def test_a_complete_record_reaches_passed(
        self, probe_id: str, facts_by_class: dict[str, Any]
    ) -> None:
        """🔴 给齐记录必须真能 `passed` —— 否则 validator 是死代码。"""
        facts = replace(facts_by_class["g7_two_level_dynamic"], signals=_ready_signals())
        spec = next(s for s in G.PER_PILOT_PROBES if s.probe_id == probe_id)
        row = G.evaluate_probe(
            spec,
            facts,
            environment=_real_environment(),
            record=_full_records(facts)[probe_id],
            supplied_inputs=_supplied_for(spec),
        )
        assert row.result == "passed", (row.error_code, row.notes)
        assert row.error_code is None

    @pytest.mark.parametrize(
        ("probe_id", "mutate", "expect"),
        [
            (
                "channel.playwright_network_console",
                lambda r: {**r, "console_messages": [{"level": "error", "text": "boom"}]},
                "error 级消息",
            ),
            (
                "channel.playwright_network_console",
                lambda r: {**r, "network_requests": []},
                "network_requests 为空",
            ),
            (
                "channel.recovery_application_operation_timeline",
                lambda r: {
                    **r,
                    "operation_timeline": dict(
                        reversed(list(r["operation_timeline"].items()))
                    )
                    | {"reload": "2026-08-16T00:00:00+00:00"},
                },
                "timeline 不成立",
            ),
            (
                "channel.db_timestamps",
                lambda r: {**r, "clock_source": "client"},
                "只接受服务端时钟",
            ),
            (
                "channel.db_timestamps",
                lambda r: {**r, "order_keys": ["client_saved_at"]},
                "TimelineUsageError",
            ),
            (
                "channel.db_timestamps",
                lambda r: {
                    **r,
                    "db_timestamps": {
                        "b": "2026-08-16T10:00:00+00:00",
                        "a": "2026-08-16T09:00:00+00:00",
                    },
                },
                "非单调",
            ),
            (
                "channel.published_result_representation",
                lambda r: {**r, "representation_state": "candidate"},
                "candidate 不得作为结果",
            ),
            (
                "channel.published_result_representation",
                lambda r: {**r, "extracted_projection_sha256": "f" * 64},
                "Property 29 不成立",
            ),
            (
                "channel.authority_model",
                lambda r: {**r, "authority_model_definition_sha256": "0" * 64},
                "已 stale",
            ),
            (
                "channel.bundle_digest_typed_slots",
                lambda r: {**r, "bundle_sha256": "0" * 64},
                "≠ 现算",
            ),
            (
                "channel.bundle_digest_typed_slots",
                lambda r: {
                    **r,
                    "typed_slots": {
                        **r["typed_slots"],
                        "contract": {"type": "marker", "digest": r["typed_slots"]["contract"]["digest"]},
                    },
                },
                "marker 不得冒充",
            ),
            (
                "channel.artifact_identity_inventory",
                lambda r: {
                    **r,
                    "identity_inventory": {**r["identity_inventory"], "row_uuids": []},
                },
                "identity 载体缺失",
            ),
            (
                "channel.artifact_identity_inventory",
                lambda r: {
                    **r,
                    "identity_inventory": {**r["identity_inventory"], "metadata_sheet": "别的"},
                },
                "与生产常量",
            ),
            (
                "channel.full_data_restoration",
                lambda r: {**r, "counts_after": {**r["counts_after"], "workpaper_artifact": 4}},
                "未复原",
            ),
            (
                "channel.full_data_restoration",
                lambda r: {**r, "counts_before": {}, "counts_after": {}},
                "空计数比对恒成立",
            ),
            (
                "close_aspect.exactly_one_capture_on_applicable_paths",
                lambda r: {
                    **r,
                    "close_captures_by_scenario": {
                        **r["close_captures_by_scenario"],
                        "single_participant_close": 2,
                    },
                },
                "capture 数与生产期望不符",
            ),
            (
                "close_aspect.exactly_one_capture_on_applicable_paths",
                lambda r: {
                    **r,
                    "close_captures_by_scenario": {
                        k: v
                        for k, v in r["close_captures_by_scenario"].items()
                        if k != "close_reconciler_reentrant_exactly_one_capture"
                    },
                },
                "观测覆盖不全",
            ),
            (
                "close_aspect.aggregate_artifact",
                lambda r: {**r, "contributor_user_ids": r["contributor_user_ids"][:1]},
                "≥2 个 contributor",
            ),
            (
                "close_aspect.initiator_route_contributors_separated",
                lambda r: {**r, "route_credential_id": r["initiator_participant_id"]},
                "route 被当成授权主体",
            ),
            (
                "close_aspect.revoke_drop_generation_rotation",
                lambda r: {**r, "write_fence_epoch_after": r["write_fence_epoch_before"]},
                "AC 10.4 原文",
            ),
            (
                "close_aspect.revoke_drop_generation_rotation",
                lambda r: {**r, "cancelled_request_ids": []},
                "未取消 outstanding requests",
            ),
            (
                "channel.per_scenario_distinct_application_ids",
                lambda r: {
                    "per_scenario_application_ids": {
                        k: [] for k in r["per_scenario_application_ids"]
                    }
                },
                "为空",
            ),
        ],
    )
    def test_a_broken_record_reaches_failed(
        self,
        probe_id: str,
        mutate: Any,
        expect: str,
        facts_by_class: dict[str, Any],
    ) -> None:
        """🔴 每条 validator 至少一个否定样例 —— 只测肯定侧等于没判据。"""
        facts = replace(facts_by_class["g7_two_level_dynamic"], signals=_ready_signals())
        spec = next(s for s in G.PER_PILOT_PROBES if s.probe_id == probe_id)
        row = G.evaluate_probe(
            spec,
            facts,
            environment=_real_environment(),
            record=mutate(_full_records(facts)[probe_id]),
            supplied_inputs=_supplied_for(spec),
        )
        assert row.result == "failed", (row.error_code, row.notes)
        assert row.error_code in {"validator_rejected", "validator_error"}
        assert expect in " ".join(row.notes), row.notes

    def test_reused_application_ids_across_scenarios_are_rejected_by_production(
        self, facts_by_class: dict[str, Any]
    ) -> None:
        """复用规则委派生产 `assert_no_reuse_within_run` —— 判据不在这里抄第二份。"""
        facts = replace(facts_by_class["d2_large_json"], signals=_ready_signals())
        spec = next(
            s
            for s in G.PER_PILOT_PROBES
            if s.probe_id == "channel.per_scenario_distinct_application_ids"
        )
        shared = _uuids(1)
        row = G.evaluate_probe(
            spec,
            facts,
            environment=_real_environment(),
            record={
                "per_scenario_application_ids": {
                    scenario_id: shared for scenario_id in facts.required_scenario_ids
                }
            },
            supplied_inputs=_supplied_for(spec),
        )
        assert row.result == "failed"
        assert row.error_code == "validator_error"
        assert "entity_reused_within_run" in " ".join(row.notes)

    def test_naive_timestamps_are_rejected(self, facts_by_class: dict[str, Any]) -> None:
        """naive 时间戳无法区分服务端/客户端时钟 ⇒ 必须失败而不是通过。"""
        facts = replace(facts_by_class["h1_grouped_dynamic"], signals=_ready_signals())
        spec = next(s for s in G.PER_PILOT_PROBES if s.probe_id == "channel.db_timestamps")
        row = G.evaluate_probe(
            spec,
            facts,
            environment=_real_environment(),
            record={
                "clock_source": "server",
                "db_timestamps": {"a": "2026-08-16T09:00:00", "b": "2026-08-16T10:00:00"},
            },
            supplied_inputs=_supplied_for(spec),
        )
        assert row.result == "failed"
        assert "naive" in " ".join(row.notes)

    def test_a_fully_supplied_close_scenario_can_reach_passed_through_production_oracle(
        self, facts_by_class: dict[str, Any]
    ) -> None:
        """scenario probe 的接线也必须双向可达：委派的是生产 oracle，不是本门自己判。"""
        facts = replace(facts_by_class["simple_checklist"], signals=_ready_signals())
        spec = next(
            s for s in G._SCENARIO_PROBES if s.scenario_id == "single_participant_close"
        )
        record = {
            "operation_ids": _uuids(1),
            "application_ids": _uuids(1),
            "observed_close_captures": 1,
            "server_timeline": _oo_timeline(),
        }
        row = G.evaluate_probe(
            spec,
            facts,
            environment=_real_environment(),
            record=record,
            supplied_inputs=_supplied_for(spec),
        )
        assert row.result == "passed", (row.error_code, row.notes)

    def test_wrong_close_capture_count_is_failed_by_production_oracle(
        self, facts_by_class: dict[str, Any]
    ) -> None:
        facts = replace(facts_by_class["simple_checklist"], signals=_ready_signals())
        spec = next(
            s for s in G._SCENARIO_PROBES if s.scenario_id == "single_participant_close"
        )
        row = G.evaluate_probe(
            spec,
            facts,
            environment=_real_environment(),
            record={
                "operation_ids": _uuids(1),
                "application_ids": _uuids(1),
                "observed_close_captures": 2,
                "server_timeline": _oo_timeline(),
            },
            supplied_inputs=_supplied_for(spec),
        )
        assert row.result == "failed"
        assert row.error_code == "close_capture_count_mismatch"

    def test_no_probe_can_pass_on_the_real_unadmitted_pilots(
        self, facts_by_class: dict[str, Any]
    ) -> None:
        """🔴 真实事实侧：即使给齐记录 + 真实 build，未 finalize 的 pilot 一条也不许通过。"""
        for pilot_class, facts in facts_by_class.items():
            records = _full_records(facts)
            for spec in G.PER_PILOT_PROBES:
                row = G.evaluate_probe(
                    spec,
                    facts,
                    environment=_real_environment(),
                    record=records.get(spec.probe_id, {"anything": 1}),
                    supplied_inputs=_supplied_for(spec),
                )
                assert row.result != "passed", (pilot_class, spec.probe_id, row.notes)


# ═══════════════════════════════════════════════════════════════════════════
# 6. 阻断 Wave 5 / 报告闭合 / Property 落点
# ═══════════════════════════════════════════════════════════════════════════


class TestGateBlocksWave5:
    """**Validates: Requirements 12.2, 14.9** · Property 49"""

    def test_main_exits_non_zero_today(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = G.main([])
        out = capsys.readouterr().out
        assert code == 1, out
        assert "[BLOCKED]" in out
        assert "Wave 5 阻断" in out

    def test_blocking_output_names_the_owner_task_of_every_pilot(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """阻断原因必须具体到"哪个 pilot 的哪一环"，不是笼统一句 failed。"""
        G.main([])
        out = capsys.readouterr().out
        for ref in G.PILOTS:
            assert f"Task {ref.owner_task}" in out, ref.pilot_class
            assert ref.pilot_class in out
        # Task 75 起阻断原因指向**供给**（Task 76 的 provisioner）而不是观测器缺失。
        assert "supply_gap" in out or "Task 76" in out, out[-800:]

    def test_structural_failure_exits_two_not_one(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """🔴 门自身失效比"有 probe 没通过"更严重 —— 退出码必须区分。"""
        def _boom(**_kwargs: Any) -> str:
            raise G.GateStructuralError("锚点脱钩（合成）")

        monkeypatch.setattr(G, "read_task_body", _boom)
        code = G.main([])
        assert code == 2
        assert "[FATAL]" in capsys.readouterr().out

    def test_exit_code_helper_is_derived_from_rows_not_from_a_flag(self) -> None:
        passed = G.ProbeRow(
            "x", "gate", None, None, None, "a", G.RESULT_PASSED, None, (), (), (), ()
        )
        failed = replace(passed, result=G.RESULT_FAILED)
        assert G._exit_code_for([passed], structural_error=None) == 0
        assert G._exit_code_for([passed, failed], structural_error=None) == 1
        assert G._exit_code_for([passed], structural_error="boom") == 2

    def test_gate_blocks_wave5_probe_is_true_because_the_exit_code_is_non_zero(
        self, report: dict[str, Any]
    ) -> None:
        row = next(
            r for r in report["probe_rows"] if r["probe_id"] == "gate.blocks_wave5"
        )
        assert row["result"] == "passed"
        assert "退出码 1" in row["notes"][0]
        assert report["unpassed_probe_count"] > 0

    def test_json_report_is_written_with_utf8_bytes(self, tmp_path: Path) -> None:
        target = tmp_path / "report.json"
        assert G.main(["--json", str(target)]) == 1
        payload = json.loads(target.read_bytes().decode("utf-8"))
        assert payload["all_pilots_verified"] is False
        assert len(payload["probe_rows"]) == 173


class TestReportIsClosedAndMeasured:
    """**Validates: Requirements 12.2, 12.10, 14.16**"""

    def test_every_declared_probe_produces_exactly_one_row_per_pilot(
        self, report: dict[str, Any]
    ) -> None:
        rows = report["probe_rows"]
        assert len(rows) == 173
        per_pilot = [r for r in rows if r["entry_id"]]
        assert len(per_pilot) == 168
        for ref in G.PILOTS:
            mine = [r for r in per_pilot if r["pilot_class"] == ref.pilot_class]
            assert len(mine) == 42, ref.pilot_class
            assert len({r["probe_id"] for r in mine}) == 42

    def test_no_pilot_is_verified_and_all_four_are_unverifiable(
        self, report: dict[str, Any]
    ) -> None:
        assert report["all_pilots_verified"] is False
        assert report["verified_pilot_classes"] == []
        assert len(report["pilots"]) == 4
        assert {d["status"] for d in report["pilots"].values()} == {"unverifiable"}

    def test_required_digests_are_pairwise_distinct(self, report: dict[str, Any]) -> None:
        digests = {
            entry_id: data["required_scenario_set"]["digest"]
            for entry_id, data in report["pilots"].items()
        }
        assert len(set(digests.values())) == 4, digests

    def test_bundle_digests_are_pairwise_distinct(self, report: dict[str, Any]) -> None:
        bundles = {
            entry_id: data["digests"]["bundle"] for entry_id, data in report["pilots"].items()
        }
        assert len(set(bundles.values())) == 4, bundles

    def test_production_oracle_echo_reproduces_the_task43_baseline(
        self, report: dict[str, Any]
    ) -> None:
        """交叉校验：本门对 24 条 required scenario 的生产 oracle 回声必须等于
        Task 43 evidence 里实测的分布（2 upstream_gap / 10 real_oo / 11 input / 1 schema）。
        """
        expected = {
            "failed/upstream_gap": 2,
            "unverifiable/real_onlyoffice_not_executed": 10,
            "unverifiable/evidence_input_missing": 11,
            "unverifiable/scenario_kind_unrepresentable": 1,
        }
        for entry_id, data in report["pilots"].items():
            assert data["production_oracle_echo_distribution"] == expected, entry_id

    def test_environment_is_the_not_executed_sentinel_by_default(
        self, report: dict[str, Any]
    ) -> None:
        from app.services.workpaper_sync import pilot_harness as ph

        env = report["environment"]
        assert env["onlyoffice_build"] == ph.NOT_EXECUTED
        assert env["browser_build"] == ph.NOT_EXECUTED
        assert env["real_onlyoffice"] is False
        assert env["real_browser"] is False

    def test_supplying_real_builds_alone_does_not_verify_anything(self) -> None:
        """🔴 只把 build 号填上（不 finalize、不给记录）不得改变结论。"""
        records = {
            "environment": {
                "onlyoffice_build": _REAL_ENV_BUILDS[0],
                "browser_build": _REAL_ENV_BUILDS[1],
            },
            "supplied_inputs": {},
            "probes": {},
        }
        report = G.build_report(records=records)
        assert report["all_pilots_verified"] is False
        assert report["environment"]["real_onlyoffice"] is True
        passed = [r for r in report["probe_rows"] if r["result"] == "passed"]
        assert {r["probe_class"] for r in passed} == {"gate"}

    def test_blocking_conditions_keep_the_black_box_fact_visible(
        self, report: dict[str, Any]
    ) -> None:
        """判定只给一个 error_code，但事实一条不能丢 —— 黑盒未执行必须仍可计数。"""
        conditions = report["blocking_condition_distribution"]
        assert conditions["real_black_box_not_executed"] == 56
        assert conditions["finalize_blocked"] == 16
        assert conditions["pilot_not_admitted"] == 152
        assert conditions["enumerated_scenario_not_in_required_set"] == 4


class TestPropertyLandings:
    """**Validates: Requirements 12.2** · 16 条 Property 的落点与结论"""

    def test_all_sixteen_properties_have_landing_rows(self, report: dict[str, Any]) -> None:
        assert set(report["properties"]) == set(G.DECLARED_PROPERTIES)
        for prop, data in report["properties"].items():
            assert data["probe_rows"] >= 1, prop
            assert data["distinct_probe_ids"], prop
            assert data["title"].strip()

    def test_no_property_is_reported_as_passed_today(self, report: dict[str, Any]) -> None:
        """🔴 四个 pilot 未 finalize ⇒ 没有任何 Property 可判 passed。"""
        verdicts = {prop: data["verdict"] for prop, data in report["properties"].items()}
        assert "passed" not in set(verdicts.values()), verdicts

    def test_property_verdict_is_the_worst_of_its_rows(self, report: dict[str, Any]) -> None:
        for prop, data in report["properties"].items():
            distribution = data["result_distribution"]
            if "failed" in distribution:
                assert data["verdict"] == "failed", prop
            elif set(distribution) == {"passed"}:
                assert data["verdict"] == "passed", prop
            else:
                assert data["verdict"] == "unverifiable", prop

    def test_p49_and_p69_have_behaviourally_verified_gate_rows(
        self, report: dict[str, Any]
    ) -> None:
        """P49/P69 的"本门自己不作假"这一半是**真跑**出来的（gate probe 全绿）。"""
        gate_rows = [r for r in report["probe_rows"] if r["probe_class"] == "gate"]
        assert len(gate_rows) == 5
        by_id = {r["probe_id"]: r for r in gate_rows}
        for probe_id in (
            "gate.no_documentary_pass",
            "gate.ordering_upstream_gap_before_black_box",
            "gate.admission_is_state_sensitive",
            "gate.blocks_wave5",
        ):
            assert by_id[probe_id]["result"] == "passed", probe_id
        assert "P49" in by_id["gate.no_documentary_pass"]["properties"]
        assert "P69" in by_id["gate.no_documentary_pass"]["properties"]

    def test_mutation_probe_is_the_only_failing_gate_row_until_mutations_land(
        self, report: dict[str, Any]
    ) -> None:
        failing = [
            r["probe_id"]
            for r in report["probe_rows"]
            if r["probe_class"] == "gate" and r["result"] != "passed"
        ]
        ok, detail, payload = G.mutation_coverage_facts()
        if payload.get("present"):
            assert failing == [] if ok else failing == ["gate.mutation_four_state"], detail
        else:
            assert failing == ["gate.mutation_four_state"], detail

    def test_mutation_probe_requires_declared_equals_executed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """🔴 「已跑的全 RED」不得冒充全量：declared != executed 必须判不通过。"""
        monkeypatch.setattr(G, "_EVIDENCE_DIR", tmp_path)
        (tmp_path / "mutation_report.json").write_bytes(
            json.dumps([{"id": "M01", "verdict": "RED"}]).encode("utf-8")
        )
        (tmp_path / "mutation_coverage.json").write_bytes(
            json.dumps({"declared_count": 9, "executed_count": 1}).encode("utf-8")
        )
        ok, detail, _payload = G.mutation_coverage_facts()
        assert ok is False
        assert "declared=9 executed=1" in detail

        (tmp_path / "mutation_coverage.json").write_bytes(
            json.dumps({"declared_count": 1, "executed_count": 1}).encode("utf-8")
        )
        ok, _detail, _payload = G.mutation_coverage_facts()
        assert ok is True

    def test_mutation_probe_rejects_a_non_red_verdict(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(G, "_EVIDENCE_DIR", tmp_path)
        (tmp_path / "mutation_report.json").write_bytes(
            json.dumps(
                [{"id": "M01", "verdict": "RED"}, {"id": "M02", "verdict": "GREEN"}]
            ).encode("utf-8")
        )
        (tmp_path / "mutation_coverage.json").write_bytes(
            json.dumps({"declared_count": 2, "executed_count": 2}).encode("utf-8")
        )
        ok, detail, _payload = G.mutation_coverage_facts()
        assert ok is False
        assert "GREEN" in detail


class TestGateAddsNoProductionModule:
    """**Validates: Requirements 9.1**（本任务不得给 Task 20 收口门增债）"""

    def test_the_gate_lives_in_scripts_check_not_in_backend_app(self) -> None:
        assert _GATE_PY.exists()
        assert _GATE_PY.parts[-3:] == ("scripts", "check", "check_task44_oo94_excel_pilot_gate.py")
        assert not (_BACKEND / "app/services/workpaper_sync/task44_gate.py").exists()

    def test_no_workpaper_sync_production_module_references_task_44(self) -> None:
        """反向锁：生产模块里不得出现 task44 接线（否则清册 source_digest 会过期）。"""
        offenders = [
            path.name
            for path in sorted((_BACKEND / "app/services/workpaper_sync").rglob("*.py"))
            if "task44" in path.read_bytes().decode("utf-8").lower()
        ]
        assert offenders == [], offenders

    def test_writer_inventory_is_still_fresh(self) -> None:
        """产物侧判据：清册的 `source_digest` 未过期 ⇒ Task 20 收口门仍按设计报 916。"""
        generator = _load(
            "_task44_inventory_gen", _BACKEND / "scripts/gen/generate_workpaper_writer_inventory.py"
        )
        assert generator.main(["--check"]) == 0

    def test_gate_calls_no_non_canonical_resolver_symbol(self) -> None:
        """用清册**本体**的符号表判定，不抄一份名字。"""
        generator = _load(
            "_task44_inventory_symbols",
            _BACKEND / "scripts/gen/generate_workpaper_writer_inventory.py",
        )
        symbols = set(generator._RESOLVER_SYMBOLS)
        assert "find_template_file" in symbols
        called: set[str] = set()
        for node in ast.walk(ast.parse(_GATE_PY.read_bytes().decode("utf-8"))):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if name in symbols:
                    called.add(str(name))
        assert called == set(), called
