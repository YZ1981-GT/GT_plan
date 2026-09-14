"""Task 61 gate 的守卫：真实 OnlyOffice 9.4 **F2 Word** pilot 门禁。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 5 Task 61
被守的产物：

* `backend/scripts/check/check_task61_oo94_word_pilot_gate.py`
* `backend/scripts/gen/generate_workpaper_task61_word_pilot_probe_registry.py`
* `backend/data/workpaper_task61_word_pilot_gate_probes.json`

═══ 这些守卫要防的四类假绿 ═══

1. **分母悄悄缩小** —— 正文枚举项被改写/删除、Task 44 已声明的场景在这里既无 probe 也
   无豁免登记、Word 族漏声明。三个方向都有反向测试（删一条必须打红）。
2. **判定顺序被交换** —— upstream-gap 必须排在黑盒之前。顺序判据用**源码 return 位置** +
   **反事实行为**双侧断言：接上真实黑盒后同一条 probe 仍须 `failed`+`upstream_gap`。
3. **状态被硬编码** —— 准入与载体门都必须是真读。测试把每个信号**逐个**翻一位并断言
   判定随之改变；对照组（全部翻好）必须变成 admitted，否则"什么都不准入"也算通过。
4. **fail-open** —— 库读不到必须抛 `DatabaseUnreadable`（退出码 2），不得降级成
   "全部 unverifiable"（退出码 1）；后者会让人误以为"门跑过了、只是环境不足"。

🔴 本文件**不**断言"F2 pilot 已通过"。它断言的是"这道门量得准"。
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import re
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
_GATE_PY = _BACKEND / "scripts/check/check_task61_oo94_word_pilot_gate.py"
_GEN_PY = _BACKEND / "scripts/gen/generate_workpaper_task61_word_pilot_probe_registry.py"


def _load(name: str, path: Path) -> ModuleType:
    """按路径加载脚本模块（`backend/scripts/**` 不是 package）。"""
    if str(_BACKEND) not in sys.path:
        sys.path.insert(0, str(_BACKEND))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, path
    module = importlib.util.module_from_spec(spec)
    # 🔴 先进 sys.modules 再 exec：gate 用 `from __future__ import annotations`，
    # dataclass 解析字符串注解要去 `sys.modules[cls.__module__]` 取命名空间。
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


G = _load("_task61_gate_under_test", _GATE_PY)


#: 离线库快照替身：**与今天真实库实测一致**（四张表在 F2 侧全 0、V153 未应用）。
#: 用它是为了让守卫脱离库可跑；准入判据本身仍由 gate 的真读路径承担
#: （`TestNoFailOpen::test_unreadable_database_is_structural_not_unverifiable` 断言那一条）。
OFFLINE_DB_ROW: dict[str, Any] = {
    "approved_bundles": 0,
    "published_representations": 0,
    "upgrade_candidates": 0,
    "content_versions": 0,
    "word_definition_artifacts": 0,
    "v153_candidate_event_table": None,
    "max_applied_migration": 152,
}


@pytest.fixture(scope="module")
def offline_snapshot() -> dict[str, dict[str, Any]]:
    return {ref.entry_id: dict(OFFLINE_DB_ROW) for ref in G.lane_refs()}


@pytest.fixture(scope="module")
def facts(offline_snapshot: dict[str, dict[str, Any]]) -> tuple[Any, ...]:
    return G.collect_lane_facts(db_snapshot=offline_snapshot)


@pytest.fixture(scope="module")
def facts_by_entry(facts: tuple[Any, ...]) -> dict[str, Any]:
    return {entry.entry_id: entry for entry in facts}


#: 供给不足时的**生产**原因文案。🔴 不在这里抄一份中文关键词：从
#: `registry._describe_entry_supply` 的源码里现取那段字面量，抄错/生产侧改文案都会立刻
#: 露馅（教训⑫：判「是不是同一条原因」不能靠自己维护第二份文本）。
def _production_supply_reason() -> str:
    if str(_BACKEND) not in sys.path:
        sys.path.insert(0, str(_BACKEND))
    from app.services.workpaper_sync.adapters import registry as registry_module

    source = inspect.getsource(registry_module._describe_entry_supply)
    match = re.search(r'"(该 entry 还没有 current published representation[^"]*)"', source)
    assert match is not None, "生产侧「无 published representation」原因文案已变 —— 守卫的对照基准失效"
    return match.group(1)


#: 三臂离线替身：**与 2026-09-01 真实库实测一致**（arm_a 186 planned / 0 registered，
#: arm_b 原因与对照 entry 逐字相等，arm_c 落到 provider 那一格）。
#: 用它是为了让守卫脱离库可跑；真跑那一臂由
#: `TestBindingConstraintIsMeasured::test_the_three_arms_really_run_against_the_database` 承担。
@pytest.fixture(scope="module")
def offline_binding_arms() -> dict[str, Any]:
    supply_reason = _production_supply_reason()
    return {
        "arm_a_control": {
            "planned": 186,
            "registered_adapter_ids": [],
            "registered_entry_ids": [],
            "unregistered": 186,
            "distinct_reason_count": 2,
            "control_entry_reason": supply_reason,
            "synth_entry_planned": False,
        },
        "arm_b_manifest_flipped": {
            "planned": 187,
            "registered_adapter_ids": [],
            "registered_entry_ids": [],
            "unregistered": 187,
            "synth_entry_planned": True,
            "synth_reason": supply_reason,
        },
        "arm_c_supply_stubbed": {
            "planned": 187,
            "registered_adapter_ids": [],
            "registered_entry_ids": [],
            "unregistered": 187,
            "synth_reason": (
                "provider app.services.workpaper_sync.pilot_simple_checklist."
                "attach_pilot_adapters 返回空元组 —— 供给已到位但 provider 侧仍有前置未过"
                "（见其自身抛出的原因）"
            ),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# 1. 任务正文是分母（三个方向的反向锁）
# ═══════════════════════════════════════════════════════════════════════════
class TestTaskTextIsTheDenominator:
    """**Validates: Requirements 12.3, 12.10**"""

    def test_every_probe_anchor_appears_verbatim_in_the_task_text(self) -> None:
        counts = G.assert_probes_anchored_in_task_text()
        assert counts, "anchor 计数为空 —— 空集恒成立"
        assert all(v >= 1 for v in counts.values()), counts

    def test_the_gate_survives_the_checkbox_being_ticked(self) -> None:
        """勾选是簿记不是事实：Task 61 被勾成 `[x]` 后正文必须逐字不变。"""
        original = G.read_task_body()
        body = _GATE_PY  # 占位避免 flake8 未用告警（下面用的是 tasks.md 文本）
        assert body.exists()
        text = (
            _REPO
            / ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/tasks.md"
        ).read_bytes().decode("utf-8")
        ticked = G.read_task_body(text=text.replace("- [ ] 61. ", "- [x] 61. "))
        normalize = lambda s: re.sub(r"^- \[[ x~\-]\] 61\. ", "- [ ] 61. ", s)  # noqa: E731
        assert normalize(ticked) == normalize(original)

    def test_removing_one_enumerated_item_from_the_task_text_fails_the_gate(self) -> None:
        """🔴 正文枚举项被删 ⇒ 立刻抛，且诊断点名是哪条 probe 脱钩。"""
        body = G.read_task_body()
        target = "download-only 三实体为 0"
        assert target in body
        with pytest.raises(G.GateStructuralError) as excinfo:
            G.assert_probes_anchored_in_task_text(task_body=body.replace(target, "（删了）"))
        assert "scenario.download_only_zero_three_entities" in str(excinfo.value)
        assert target in str(excinfo.value)

    def test_removing_the_close_family_sentence_fails_the_gate(self) -> None:
        """close 族的「均无条件运行」被删也必须打红（正文第 3 条是无条件族的唯一来源）。"""
        body = G.read_task_body()
        with pytest.raises(G.GateStructuralError, match="均无条件运行"):
            G.assert_probes_anchored_in_task_text(
                task_body=body.replace("均无条件运行", "（删了）")
            )

    def test_all_seventeen_declared_requirements_are_claimed_by_a_probe(self) -> None:
        payload = G.probe_registry_payload()
        assert len(payload["task_requirements"]) == 17, payload["task_requirements"]
        assert payload["requirements_without_probe"] == []
        assert payload["requirements_claimed_but_not_declared"] == []
        G.assert_registry_coverage(payload)

    def test_an_unclaimed_requirement_is_a_structural_failure(self) -> None:
        payload = dict(G.probe_registry_payload())
        payload["requirements_without_probe"] = ["14.8"]
        with pytest.raises(G.GateStructuralError, match="14.8"):
            G.assert_registry_coverage(payload)

    def test_an_empty_requirement_denominator_is_a_structural_failure(self) -> None:
        """🔴 教训⑥：等值判据必须断言覆盖计数非空，否则空集恒等价。"""
        payload = dict(G.probe_registry_payload())
        payload["task_requirements"] = []
        with pytest.raises(G.GateStructuralError, match="分母为空"):
            G.assert_registry_coverage(payload)

    def test_twelve_properties_are_declared_and_each_lands_on_a_probe(self) -> None:
        payload = G.probe_registry_payload()
        assert len(G.DECLARED_PROPERTIES) == 12
        assert payload["properties_without_probe"] == []
        assert payload["properties_claimed_but_not_declared"] == []
        titles = payload["property_titles"]
        assert set(titles) == set(G.DECLARED_PROPERTIES)
        assert all(title.strip() for title in titles.values())

    def test_the_declared_property_tuple_matches_the_task_text(self) -> None:
        """双向：本文件的封闭元组 ↔ 正文「独立验证 Property …」。"""
        payload = G.probe_registry_payload()
        assert payload["declared_properties"] == payload["task_text_properties"]

    def test_a_property_drifting_from_the_task_text_is_a_structural_failure(self) -> None:
        payload = dict(G.probe_registry_payload())
        payload["task_text_properties"] = ["P30"]
        with pytest.raises(G.GateStructuralError, match="独立验证"):
            G.assert_registry_coverage(payload)

    def test_a_property_missing_from_design_md_is_a_structural_failure(self) -> None:
        with pytest.raises(G.GateStructuralError, match="P999"):
            G.design_property_titles(("P30", "P999"))

    def test_generated_registry_data_file_is_fresh(self) -> None:
        """`backend/data/` 的投影必须与 gate 现算逐字节相等。"""
        generator = _load("_task61_registry_gen", _GEN_PY)
        assert generator.main(["--check"]) == 0

    def test_probe_row_count_is_the_declared_product(self) -> None:
        payload = G.probe_registry_payload()
        assert payload["scenario_probe_count"] == len(G.SCENARIO_PROBES) == 26
        assert payload["per_entry_probe_count"] == len(G.PER_ENTRY_PROBES) == 34
        assert payload["gate_probe_count"] == len(G.GATE_PROBES) == 7
        assert payload["total_probe_rows"] == 34 * 2 + 7 == 75

    def test_every_production_ref_resolves_today(self) -> None:
        """probe 声明的生产符号必须都还在 —— 改名/删除立刻抛。"""
        for spec in G.ALL_PROBE_SPECS:
            assert G._resolve_production_refs(spec) == spec.production_refs

    def test_a_vanished_production_symbol_fails_the_probe(self) -> None:
        spec = replace(
            G.SCENARIO_PROBES[0],
            production_refs=("app.services.workpaper_sync.rooms:NoSuchSymbol",),
        )
        with pytest.raises(G.GateStructuralError, match="NoSuchSymbol"):
            G._resolve_production_refs(spec)


# ═══════════════════════════════════════════════════════════════════════════
# 2. scenario 分母：三向锁
# ═══════════════════════════════════════════════════════════════════════════
class TestScenarioDenominatorIsThreeWay:
    """**Validates: Requirements 12.10**"""

    def test_every_declared_scenario_has_a_production_oracle(self) -> None:
        from app.services.workpaper_sync import pilot_harness as ph

        declared = {s.scenario_id for s in G.SCENARIO_PROBES if s.scenario_id}
        assert declared, "declared 为空 —— 空集恒成立"
        assert declared <= set(ph.SCENARIO_ORACLES)

    def test_task44_declared_scenarios_are_the_reverse_lock(self) -> None:
        task44 = G.load_task44_declared_scenarios()
        assert len(task44) >= 20, f"对照分母过小，可能加载错了：{sorted(task44)}"
        declared = {s.scenario_id for s in G.SCENARIO_PROBES if s.scenario_id}
        assert task44 <= declared | set(G.OUT_OF_LANE_SCENARIOS)

    def test_dropping_one_task44_scenario_probe_is_detected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """🔴 反向锁：Task 44 已声明的场景在这里既无 probe 也无豁免 ⇒ 结构性失效。"""
        trimmed = tuple(
            s for s in G.SCENARIO_PROBES if s.scenario_id != "single_participant_close"
        )
        monkeypatch.setattr(G, "SCENARIO_PROBES", trimmed)
        with pytest.raises(G.GateStructuralError, match="single_participant_close"):
            G.scenario_denominator_facts()

    def test_dropping_a_word_family_probe_is_detected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Word 族是本任务的核心：漏一条即打红（即便 Task 44 也没声明它）。"""
        trimmed = tuple(
            s for s in G.SCENARIO_PROBES if s.scenario_id != "word_free_body_isolation"
        )
        monkeypatch.setattr(G, "SCENARIO_PROBES", trimmed)
        with pytest.raises(G.GateStructuralError, match="word_free_body_isolation"):
            G.scenario_denominator_facts()

    def test_out_of_lane_and_probe_sets_are_disjoint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """同时出现在两侧 ⇒ 「豁免」会顶住「未通过」（教训③的另一形态）。"""
        monkeypatch.setitem(
            G.OUT_OF_LANE_SCENARIOS,
            "html_to_oo",
            {"reason": "x" * 12, "measured_from": "y", "owner_task": "67"},
        )
        with pytest.raises(G.GateStructuralError, match="必须互斥"):
            G.scenario_denominator_facts()

    def test_every_out_of_lane_row_has_reason_measured_from_and_owner(self) -> None:
        assert G.OUT_OF_LANE_SCENARIOS, "豁免表为空时本测试恒真 —— 需要非空断言"
        for scenario_id, row in G.OUT_OF_LANE_SCENARIOS.items():
            for field_name in ("reason", "measured_from", "owner_task"):
                assert str(row.get(field_name) or "").strip(), (scenario_id, field_name)

    def test_an_out_of_lane_row_without_owner_is_a_structural_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(
            G.OUT_OF_LANE_SCENARIOS,
            "dynamic_column_stable_keys",
            {"reason": "x" * 12, "measured_from": "y", "owner_task": ""},
        )
        with pytest.raises(G.GateStructuralError, match="owner_task"):
            G.scenario_denominator_facts()

    def test_denominator_counts_are_non_empty(self) -> None:
        facts = G.scenario_denominator_facts()
        assert facts["declared_scenario_probes"] == 26
        assert facts["production_oracles"] >= 26
        assert facts["task44_declared"] > 0
        assert facts["out_of_lane_registered"] == len(G.OUT_OF_LANE_SCENARIOS)
        assert facts["word_family_scenarios"] == [
            "word_free_body_isolation",
            "word_sdt_tag_row_uuid_retention",
        ]


# ═══════════════════════════════════════════════════════════════════════════
# 3. Task 6 载体门：新鲜度是**现算**的
# ═══════════════════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def carrier_contract() -> dict[str, Any]:
    return json.loads(G.CARRIER_CONTRACT_PATH.read_bytes().decode("utf-8"))


class TestCarrierGateFreshnessIsMeasured:
    """**Validates: Requirements 7.6, 14.4, 14.16**"""

    def test_control_group_is_fresh_today(self, carrier_contract: dict[str, Any]) -> None:
        """🔴 对照组必须先过（教训⑤）：否则「什么都判 stale」也算通过。"""
        verdict = G.probe_carrier_gate(
            contract=carrier_contract,
            source_commit=carrier_contract["environment"]["source_commit"],
            oo_build=carrier_contract["environment"]["oo_build"],
        )
        assert verdict.stale_reasons == (), verdict.stale_reasons
        assert verdict.fresh is True
        assert verdict.really_passed is True

    def test_source_commit_drift_alone_makes_it_stale(
        self, carrier_contract: dict[str, Any]
    ) -> None:
        verdict = G.probe_carrier_gate(
            contract=carrier_contract,
            source_commit="0" * 40,
            oo_build=carrier_contract["environment"]["oo_build"],
        )
        assert verdict.fresh is False
        assert any("source_commit" in r for r in verdict.stale_reasons), verdict.stale_reasons

    def test_oo_build_drift_alone_makes_it_stale(
        self, carrier_contract: dict[str, Any]
    ) -> None:
        verdict = G.probe_carrier_gate(
            contract=carrier_contract,
            source_commit=carrier_contract["environment"]["source_commit"],
            oo_build="0.0.0-0",
        )
        assert verdict.fresh is False
        assert any("OO build" in r for r in verdict.stale_reasons), verdict.stale_reasons

    def test_template_digest_drift_alone_makes_it_stale(
        self, carrier_contract: dict[str, Any]
    ) -> None:
        """三项**分开断言**：写成"任一项变化即 stale"时短路两项也能过（教训③）。"""
        mutated = json.loads(json.dumps(carrier_contract))
        mutated["probe_docs"][1]["template_sha256"] = "f" * 64
        verdict = G.probe_carrier_gate(
            contract=mutated,
            source_commit=carrier_contract["environment"]["source_commit"],
            oo_build=carrier_contract["environment"]["oo_build"],
        )
        assert verdict.fresh is False
        assert any("模板 digest 漂移" in r for r in verdict.stale_reasons), verdict.stale_reasons

    def test_empty_probe_docs_is_a_structural_failure(
        self, carrier_contract: dict[str, Any]
    ) -> None:
        """空 probe_docs 会让"三份模板全匹配"恒真 —— 必须抛（教训⑥）。"""
        mutated = json.loads(json.dumps(carrier_contract))
        mutated["probe_docs"] = []
        with pytest.raises(G.GateStructuralError, match="probe_docs 为空"):
            G.probe_carrier_gate(contract=mutated, source_commit="x", oo_build="y")

    def test_really_passed_requires_w_tag_to_be_the_only_admissible_anchor(
        self, carrier_contract: dict[str, Any]
    ) -> None:
        """载体门"真实通过"不等于"新鲜"：锚点集合被放宽也必须判不通过。"""
        mutated = json.loads(json.dumps(carrier_contract))
        mutated["downstream_gate"]["anchors_allowed"] = ["w_tag", "paragraph_index"]
        verdict = G.probe_carrier_gate(
            contract=mutated,
            source_commit=carrier_contract["environment"]["source_commit"],
            oo_build=carrier_contract["environment"]["oo_build"],
        )
        assert verdict.fresh is True, "本例只改锚点，不该影响新鲜度"
        assert verdict.really_passed is False

    def test_really_passed_requires_the_three_allowed_carriers(
        self, carrier_contract: dict[str, Any]
    ) -> None:
        mutated = json.loads(json.dumps(carrier_contract))
        mutated["downstream_gate"]["carriers_allowed_into_word_engine"] = ["field_sdt_inline"]
        verdict = G.probe_carrier_gate(
            contract=mutated,
            source_commit=carrier_contract["environment"]["source_commit"],
            oo_build=carrier_contract["environment"]["oo_build"],
        )
        assert verdict.really_passed is False

    def test_row_sdt_is_still_blocked_by_task6(self) -> None:
        """Task 6 把 row_sdt 判 failed。这是 `carrier_unrepresentable` 那一格的前提。"""
        verdict = G.probe_carrier_gate()
        assert "row_sdt" in verdict.carriers_blocked
        assert "row_sdt" not in verdict.carriers_allowed

    def test_the_gate_self_check_measures_all_three_inputs(self) -> None:
        ok, why, payload = G.gate_probe_carrier_freshness_is_measured()
        assert ok, why
        assert payload["commit_drift_detected"] is True
        assert payload["build_drift_detected"] is True
        assert payload["template_digest_drift_detected"] is True


# ═══════════════════════════════════════════════════════════════════════════
# 4. 准入是真读，不是硬编码
# ═══════════════════════════════════════════════════════════════════════════
class TestAdmissionIsRealReadback:
    """**Validates: Requirements 12.3**"""

    def test_both_f2_entries_come_from_task60_publication_not_a_hardcoded_list(self) -> None:
        refs = G.lane_refs()
        assert [r.wp_code for r in refs] == ["F2-22", "F2-23"]
        assert [r.entry_id for r in refs] == ["f2.stocktake.plan", "f2.stocktake.summary"]
        source = _GATE_PY.read_text(encoding="utf-8")
        # 🔴 判「不是第二真源」不能只 grep 符号名（教训②）：断言 lane_refs 真的从
        #    发布记录取值 —— 把发布记录的 entries 清空后必须抛。
        with pytest.raises(G.GateStructuralError, match="entries 为空"):
            G.lane_refs({"entries": []})
        assert "PUBLICATION_PATH" in source

    def test_an_empty_publication_is_a_structural_failure(self) -> None:
        with pytest.raises(G.GateStructuralError, match="entries 为空"):
            G.lane_refs({"entries": []})

    def test_a_publication_entry_without_contract_id_is_a_structural_failure(self) -> None:
        with pytest.raises(G.GateStructuralError, match="contract_id 为空"):
            G.lane_refs(
                {
                    "entries": [
                        {
                            "lane_entry_key": "word-lane/x",
                            "wp_code": "F2-22",
                            "template_ref": "t",
                            "contract": {},
                        }
                    ]
                }
            )

    def test_no_f2_entry_is_admitted_today(self, facts: tuple[Any, ...]) -> None:
        """今天的实测事实：两个 entry 都未准入（五个信号全 False）。"""
        assert len(facts) == 2
        for entry in facts:
            signals = entry.signals
            assert signals.admitted is False
            assert signals.contract_installed is False
            assert signals.manifest_entry_present is False
            assert signals.adapter_registered is False
            assert signals.approved_bundle_present is False
            assert signals.published_representation_present is False
            # 载体门本身是通过的 —— 阻断项不是 Task 6
            assert signals.carrier.really_passed is True

    @pytest.mark.parametrize(
        "flipped",
        [
            "contract_installed",
            "manifest_entry_present",
            "adapter_registered",
            "approved_bundles",
            "published_representations",
        ],
    )
    def test_flipping_only_one_signal_still_leaves_it_unadmitted(
        self, facts_by_entry: dict[str, Any], flipped: str
    ) -> None:
        """🔴 五个信号**逐个**断言（教训③）：写成集合成员会被另一个顶住。"""
        signals = facts_by_entry["f2.stocktake.plan"].signals
        if flipped in ("approved_bundles", "published_representations"):
            candidate = replace(signals, db={**dict(signals.db), flipped: 1})
        else:
            candidate = replace(signals, **{flipped: True})
        assert candidate.admitted is False, flipped

    def test_flipping_all_signals_makes_it_admitted(
        self, facts_by_entry: dict[str, Any]
    ) -> None:
        """对照组：全部翻好必须变成 admitted，否则「什么都不准入」也算通过（教训⑤）。"""
        signals = facts_by_entry["f2.stocktake.summary"].signals
        assert G._all_signals_ready(signals).admitted is True

    @pytest.mark.parametrize(
        "turned_off",
        [
            "contract_installed",
            "manifest_entry_present",
            "adapter_registered",
            "approved_bundles",
            "published_representations",
        ],
    )
    def test_each_admission_condition_is_individually_necessary(
        self, facts_by_entry: dict[str, Any], turned_off: str
    ) -> None:
        """🔴 从**全部就绪**出发关掉恰一项，必须立刻不准入。

        这条才是「五个条件各自必要」的判据。只断言"今天两个 entry 都未准入"是不够的：
        今天五项**同时**为 False，去掉其中任何一项的判断，结论都不变 ⇒ 变异检验判 GREEN
        （2026 本轮 M11/M12 实测正是这个形态）。
        """
        ready = G._all_signals_ready(facts_by_entry["f2.stocktake.plan"].signals)
        assert ready.admitted is True, "对照组必须先通过"
        if turned_off in ("approved_bundles", "published_representations"):
            weakened = replace(ready, db={**dict(ready.db), turned_off: 0})
        else:
            weakened = replace(ready, **{turned_off: False})
        assert weakened.admitted is False, turned_off

    def test_contract_installed_is_derived_from_the_production_inventory(
        self, offline_snapshot: dict[str, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """🔴 断言"真做了一次取值"而不是 grep 符号名（教训②）：把生产清册换成含本
        lane 契约的集合后，信号必须翻成 True。硬编码 False 过不了这一条。
        """
        from app.services.workpaper_sync import contracts as contracts_module

        ref = G.lane_refs()[0]
        monkeypatch.setattr(
            contracts_module,
            "available_contract_ids",
            lambda: {ref.contract_id, "b60.hour_budget"},
        )
        signals = G.probe_admission_signals(
            ref, db_snapshot=offline_snapshot[ref.entry_id]
        )
        assert signals.contract_installed is True
        assert ref.contract_id in signals.installed_contract_ids

    def test_manifest_entry_present_is_derived_from_the_source_manifest(
        self, offline_snapshot: dict[str, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services.workpaper_sync import evidence as ev

        ref = G.lane_refs()[0]
        monkeypatch.setattr(
            ev,
            "manifest_entries_by_id",
            lambda _manifest: {ref.entry_id: {"document_type": "docx"}},
        )
        signals = G.probe_admission_signals(
            ref, db_snapshot=offline_snapshot[ref.entry_id]
        )
        assert signals.manifest_entry_present is True
        assert ref.entry_id in signals.manifest_docx_entry_ids

    def test_adapter_registered_is_derived_from_the_production_registry(
        self, offline_snapshot: dict[str, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services.workpaper_sync.adapters import registry as registry_module

        ref = G.lane_refs()[0]

        class _Reg:
            adapter_id = ref.contract_id
            document_type = "docx"

        class _Production:
            def registrations(self) -> tuple[Any, ...]:
                return (_Reg(),)

        monkeypatch.setattr(
            registry_module, "build_production_registry", lambda **_kw: _Production()
        )
        signals = G.probe_admission_signals(
            ref, db_snapshot=offline_snapshot[ref.entry_id]
        )
        assert signals.adapter_registered is True
        assert ref.contract_id in signals.registered_adapter_ids

    def test_a_stale_carrier_gate_alone_blocks_admission(
        self, facts_by_entry: dict[str, Any]
    ) -> None:
        """把其余全部翻好、只让载体门 stale ⇒ 仍不得准入。"""
        ready = G._all_signals_ready(facts_by_entry["f2.stocktake.plan"].signals)
        stale = replace(
            ready, carrier=replace(ready.carrier, stale_reasons=("source_commit 变化",))
        )
        assert stale.admitted is False

    def test_admission_state_sensitivity_probe_passes(self, facts: tuple[Any, ...]) -> None:
        ok, why, payload = G.gate_probe_admission_is_state_sensitive(facts)
        assert ok, why
        assert len(payload["entries"]) == 2
        for row in payload["entries"]:
            assert row["admitted_now"] is False
            assert row["admitted_if_ready"] is True

    def test_the_supply_gap_text_comes_from_task60_publication(
        self, facts_by_entry: dict[str, Any]
    ) -> None:
        """🔴 单一真源：阻断原因取发布记录的 BP 原文，本门不另写一份。"""
        entry = facts_by_entry["f2.stocktake.plan"]
        debt = G.supply_gap_debt(entry)
        assert debt.startswith("upstream_gap[")
        for bp_id in entry.ref.blocked_by:
            assert bp_id in debt
        publication = G.load_publication()
        wanted = {
            str(bp["id"]): str(bp["what"])
            for bp in publication["blocking_preconditions"]
            if str(bp.get("status")) == "open"
        }
        assert entry.ref.blocked_by, "blocked_by 为空时本断言恒真"
        for bp_id in entry.ref.blocked_by:
            assert wanted[bp_id][:24] in debt

    def test_a_blocked_by_that_misses_the_registry_is_a_structural_failure(
        self, facts_by_entry: dict[str, Any]
    ) -> None:
        entry = facts_by_entry["f2.stocktake.plan"]
        detached = replace(entry, ref=replace(entry.ref, blocked_by=("BP-999",)))
        with pytest.raises(G.GateStructuralError, match="脱钩"):
            G.supply_gap_debt(detached)

    def test_a_missing_db_snapshot_is_a_structural_failure(self) -> None:
        with pytest.raises(G.GateStructuralError, match="没有库快照"):
            G.collect_lane_facts(db_snapshot={})

    def test_a_db_snapshot_missing_one_key_is_a_structural_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """少查一张表就会把缺口当成没问题 —— 快照键集是封闭的。"""
        partial = {
            ref.entry_id: {
                k: v for k, v in OFFLINE_DB_ROW.items() if k != "approved_bundles"
            }
            for ref in G.lane_refs()
        }

        async def _fake(_refs: Any) -> dict[str, dict[str, Any]]:
            return partial

        monkeypatch.setattr(G, "_read_db_snapshot", _fake)
        with pytest.raises(G.GateStructuralError, match="缺键"):
            G.read_db_snapshot(G.lane_refs())


# ═══════════════════════════════════════════════════════════════════════════
# 5. 判定顺序不可交换
# ═══════════════════════════════════════════════════════════════════════════
class TestOrderingIsNotCommutative:
    """**Validates: Requirements 14.9**"""

    def test_source_positions_put_upstream_gap_before_the_black_box(self) -> None:
        order = G.ordering_facts()
        assert order["upstream_gap_before_black_box"] is True
        assert order["carrier_before_upstream_gap"] is True
        assert order["black_box_before_record_missing"] is True

    def test_each_return_marker_is_located_exactly_once(self) -> None:
        """命中 0 或 >1 都是脚本缺陷（ANCHOR-MISS 的同型）—— 顺序判据必须定位唯一。"""
        order = G.ordering_facts()
        positions = order["source_positions"]
        assert len(set(positions.values())) == len(positions), positions

    def test_real_black_box_does_not_turn_an_upstream_gap_green(
        self, facts_by_entry: dict[str, Any]
    ) -> None:
        """🔴 本门最关键的自检：接上真实黑盒后同一条 probe 仍须 failed+upstream_gap。"""
        counter = G.upstream_gap_counterfactual(facts_by_entry["f2.stocktake.plan"])
        assert counter["sentinel_env_result"] == G.RESULT_FAILED
        assert counter["sentinel_env_error_code"] == "upstream_gap"
        assert counter["real_env_result"] == G.RESULT_FAILED
        assert counter["real_env_error_code"] == "upstream_gap"
        assert counter["still_failed_with_real_black_box"] is True

    def test_carrier_unrepresentable_outranks_upstream_gap(
        self, facts_by_entry: dict[str, Any]
    ) -> None:
        """row_uuid 半边是**结构性不可表达**，不能被记成 upstream_gap（两者语义不同）。"""
        entry = facts_by_entry["f2.stocktake.plan"]
        spec = next(
            s for s in G.SCENARIO_PROBES
            if s.scenario_id == "word_sdt_tag_row_uuid_retention"
        )
        row = G.evaluate_probe(
            spec,
            entry,
            environment=G.default_environment(),
            record=None,
            supplied_inputs=frozenset(),
        )
        assert row.result == G.RESULT_UNVERIFIABLE
        assert row.error_code == "carrier_unrepresentable_on_this_entry"
        assert any("row_uuid 半边" in n for n in row.notes), row.notes

    def test_the_tag_half_of_the_same_scenario_stays_in_the_denominator(
        self, facts_by_entry: dict[str, Any]
    ) -> None:
        """🔴 只有 row_uuid 半边不可表达：tag 半边（`identity_retention`）仍在分母内，
        且被记成 upstream_gap 而不是豁免。"""
        entry = facts_by_entry["f2.stocktake.plan"]
        spec = next(s for s in G.SCENARIO_PROBES if s.scenario_id == "identity_retention")
        row = G.evaluate_probe(
            spec,
            entry,
            environment=G.default_environment(),
            record=None,
            supplied_inputs=frozenset(),
        )
        assert row.result == G.RESULT_FAILED
        assert row.error_code == "upstream_gap"

    def test_carrier_unrepresentable_needs_both_conditions(
        self, facts_by_entry: dict[str, Any]
    ) -> None:
        """载体豁免的两个条件**各自**必要：row_sdt 被 block **且** 本 entry 无行域字段。

        任一条不成立就不得豁免 —— 否则「某天契约加了 repeaters」会被继续豁免掉。
        """
        entry = facts_by_entry["f2.stocktake.plan"]
        assert G.carrier_unrepresentable_note(entry, "word_sdt_tag_row_uuid_retention")

        with_repeaters = replace(entry, row_scoped_field_count=3)
        assert (
            G.carrier_unrepresentable_note(with_repeaters, "word_sdt_tag_row_uuid_retention")
            is None
        )

        unblocked = replace(
            entry,
            signals=replace(
                entry.signals, carrier=replace(entry.signals.carrier, carriers_blocked=())
            ),
        )
        assert (
            G.carrier_unrepresentable_note(unblocked, "word_sdt_tag_row_uuid_retention")
            is None
        )

    def test_other_scenarios_never_get_the_carrier_excuse(
        self, facts_by_entry: dict[str, Any]
    ) -> None:
        entry = facts_by_entry["f2.stocktake.plan"]
        for scenario_id in ("html_to_oo", "word_free_body_isolation", "rollback"):
            assert G.carrier_unrepresentable_note(entry, scenario_id) is None, scenario_id

    def test_the_ordering_gate_probe_passes(self, facts: tuple[Any, ...]) -> None:
        ok, why, _payload = G.gate_probe_ordering(facts)
        assert ok, why


# ═══════════════════════════════════════════════════════════════════════════
# 6. 不得以文档声明通过
# ═══════════════════════════════════════════════════════════════════════════
class TestDocumentaryClaimIsRejected:
    """**Validates: Requirements 14.9**"""

    def test_control_group_without_claims_is_accepted(self) -> None:
        """🔴 对照组先过：否则「什么都拒」也算通过（教训⑤）。"""
        G.assert_records_carry_no_claim(
            {"entries": {"f2.stocktake.plan": {"browser_trace_path": "x", "notes": ["ok"]}}}
        )

    @pytest.mark.parametrize("key", sorted(G.FORBIDDEN_RECORD_KEYS))
    def test_each_forbidden_key_is_rejected_on_its_own(self, key: str) -> None:
        """六个键**逐个**断言：写成集合成员时短路五个也能过。"""
        with pytest.raises(G.DocumentaryClaimRejected, match=key):
            G.assert_records_carry_no_claim({"entries": {"e": {key: "passed"}}})

    def test_a_claim_nested_inside_a_list_is_rejected(self) -> None:
        with pytest.raises(G.DocumentaryClaimRejected, match=r"\[2\]"):
            G.assert_records_carry_no_claim(
                {"entries": {"e": {"rows": [{}, {}, {"verdict": "ok"}]}}}
            )

    def test_the_rejection_has_its_own_exception_type(self) -> None:
        """🔴 教训①：判「拒绝」不能只比异常类型能不能抓到 —— 这条断言的是"拒的正是
        文档声明"，而不是"抛了个 GateStructuralError"。"""
        assert issubclass(G.DocumentaryClaimRejected, G.GateStructuralError)
        assert G.DocumentaryClaimRejected is not G.DatabaseUnreadable
        with pytest.raises(G.DocumentaryClaimRejected):
            G.assert_records_carry_no_claim({"status": "green"})

    def test_load_execution_records_rejects_a_claiming_file(self, tmp_path: Path) -> None:
        path = tmp_path / "records.json"
        path.write_text(
            json.dumps({"entries": {"e": {"p": {"passed": True}}}}), encoding="utf-8"
        )
        with pytest.raises(G.DocumentaryClaimRejected):
            G.load_execution_records(path)

    def test_load_execution_records_accepts_a_clean_file(self, tmp_path: Path) -> None:
        path = tmp_path / "records.json"
        path.write_text(
            json.dumps(
                {
                    "environment": {"onlyoffice_build": "9.4.0-129"},
                    "supplied_inputs": {"browser_trace": True},
                    "entries": {},
                }
            ),
            encoding="utf-8",
        )
        payload = G.load_execution_records(path)
        assert payload["environment"]["onlyoffice_build"] == "9.4.0-129"

    def test_the_gate_probe_runs_the_rejection_for_real(self) -> None:
        ok, why, payload = G.gate_probe_no_documentary_pass()
        assert ok, why
        assert payload["control_not_rejected"] is True
        assert payload["claim_rejected"] is True


# ═══════════════════════════════════════════════════════════════════════════
# 7. boundary probe：度量「没有提前落地」
# ═══════════════════════════════════════════════════════════════════════════
class TestBoundaryProbesMeasureNonCrossing:
    """**Validates: Requirements 7.8, 12.3**"""

    def test_the_docx_adapter_block_is_still_in_force(self) -> None:
        in_force, detail, row = G.probe_adapter_block()
        assert in_force is True, detail
        assert str(G.TASK_NUMBER) in str(row["blocking_task"])
        assert row["forbidden_paths"], "forbidden_paths 为空时判据恒真"

    def test_a_landed_word_adapter_flips_the_boundary_probe_red(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """🔴 对照实验：造一棵含 `adapters/word.py` 的假树，probe 必须打红。"""
        fake = tmp_path / "backend/app/services/workpaper_sync/adapters"
        fake.mkdir(parents=True)
        (fake / "word.py").write_text("# fake\n", encoding="utf-8")
        monkeypatch.setattr(G, "_REPO", tmp_path)
        in_force, detail, _row = G.probe_adapter_block()
        assert in_force is False
        assert "adapters/word.py" in detail

    def test_a_pending_row_that_stops_naming_task61_flips_it_red(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services.workpaper_sync.adapters import registry as RG

        monkeypatch.setattr(
            RG,
            "PENDING_ENGINE_ADAPTERS",
            (
                {
                    **{k: v for k, v in RG.PENDING_ENGINE_ADAPTERS[0].items()},
                    "blocking_task": "59,60",
                },
            ),
        )
        in_force, detail, _row = G.probe_adapter_block()
        assert in_force is False
        assert "blocking_task" in detail

    def test_two_docx_pending_rows_flip_it_red(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services.workpaper_sync.adapters import registry as RG

        monkeypatch.setattr(
            RG,
            "PENDING_ENGINE_ADAPTERS",
            RG.PENDING_ENGINE_ADAPTERS + (dict(RG.PENDING_ENGINE_ADAPTERS[0]),),
        )
        in_force, detail, _row = G.probe_adapter_block()
        assert in_force is False
        assert "恰 1 行" in detail

    def test_the_word_bulk_gate_is_not_crossed_today(self) -> None:
        ok, why, payload = G.probe_word_bulk_gate_not_crossed()
        assert ok, why
        assert payload["docx_entries_in_delivered_registry"] == []
        assert payload["lane_contracts_installed_into_production_inventory"] == []
        assert payload["docx_adapters_registered"] == []

    def test_the_criterion_is_not_the_checkbox(self) -> None:
        """🔴 假红防护：Task 64 已被并发会话勾成 `[x]`（部分交付簿记语义），
        而它的脚注逐条声明"未越 Task 61 的 `word_bulk` 门" ⇒ checkbox 不得作判据。"""
        states = G.downstream_task_states()
        assert any(state == "x" for state in states.values()), (
            f"本断言登记的是 2026 本轮实测事实：Tasks 62/64 已被并发会话勾成 `[x]`"
            f"（现读 {states}）。若全部回到未勾选，本测试提醒复核 "
            "`probe_word_bulk_gate_not_crossed` 的判据是否仍必要"
        )
        ok, _why, payload = G.probe_word_bulk_gate_not_crossed()
        assert ok is True, "checkbox 已勾选却仍判未跨越 ⇒ 判据确实不是 checkbox"
        assert payload["downstream_task_checkbox_states"] == states

    def test_adding_a_docx_entry_to_the_delivered_registry_flips_it_red(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services.workpaper_sync.adapters import registry as RG

        monkeypatch.setattr(
            RG,
            "DELIVERED_PER_ENTRY_CONTRACTS",
            RG.DELIVERED_PER_ENTRY_CONTRACTS
            + (
                {
                    "contract_id": "f2.stocktake.plan",
                    "entry_id": "docx/word-lane/f2-22",
                    "document_type": "docx",
                },
            ),
        )
        ok, why, payload = G.probe_word_bulk_gate_not_crossed()
        assert ok is False, why
        assert payload["docx_entries_in_delivered_registry"] == ["f2.stocktake.plan"]

    def test_boundary_probes_pass_while_scenarios_do_not(self, facts: tuple[Any, ...]) -> None:
        """boundary probe 在未准入时**应当**通过 —— 它度量的是"守住了"。"""
        entry = facts[0]
        for probe_id in (
            "boundary.word_adapter_has_not_landed",
            "boundary.downstream_tasks_stay_blocked",
        ):
            spec = next(s for s in G.PER_ENTRY_PROBES if s.probe_id == probe_id)
            row = G.evaluate_probe(
                spec,
                entry,
                environment=G.default_environment(),
                record=None,
                supplied_inputs=frozenset(),
            )
            assert row.result == G.RESULT_PASSED, (probe_id, row.notes)

    def test_a_boundary_probe_without_a_criterion_is_a_structural_failure(
        self, facts: tuple[Any, ...]
    ) -> None:
        """🔴 声明存在而判据缺失即假绿（教训⑩：additive 注入即死代码）。"""
        orphan = replace(
            next(s for s in G.PER_ENTRY_PROBES if s.probe_class == "boundary"),
            probe_id="boundary.no_such_criterion",
        )
        with pytest.raises(G.GateStructuralError, match="没有对应判据"):
            G._evaluate_boundary_probe(orphan, facts[0], blocking=(), notes=())


# ═══════════════════════════════════════════════════════════════════════════
# 8. 禁 fail-open
# ═══════════════════════════════════════════════════════════════════════════
class TestNoFailOpen:
    """**Validates: Requirements 12.10, 14.9**"""

    def test_unreadable_database_is_structural_not_unverifiable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """🔴 库读不到 ⇒ `DatabaseUnreadable`（退出码 2），**不**降级成"全部
        unverifiable"（退出码 1）。后者会让人误以为"门跑过了、只是环境不足"。"""

        async def _boom(_refs: Any) -> dict[str, dict[str, Any]]:
            raise RuntimeError("connection refused")

        monkeypatch.setattr(G, "_read_db_snapshot", _boom)
        with pytest.raises(G.DatabaseUnreadable, match="connection refused"):
            G.read_db_snapshot(G.lane_refs())

    def test_the_cli_returns_two_when_the_database_is_unreadable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _boom(_refs: Any) -> dict[str, dict[str, Any]]:
            raise RuntimeError("connection refused")

        monkeypatch.setattr(G, "_read_db_snapshot", _boom)
        assert G.main([]) == 2

    def test_the_module_has_no_silent_except_pass(self) -> None:
        """`except ...: pass` / `except Exception: return` 是 fail-open 的字面形态。"""
        source = _GATE_PY.read_text(encoding="utf-8")
        stripped = "\n".join(
            line for line in source.splitlines() if not line.strip().startswith("#")
        )
        assert "except Exception:\n            pass" not in stripped
        assert not re.search(r"except\s+Exception[^\n]*:\s*\n\s*pass\b", stripped)

    def test_every_broad_except_reraises_or_records_an_error_state(self) -> None:
        """每一处 `except Exception` 都必须 `raise ... from exc`（不吞、不降级）。"""
        source = _GATE_PY.read_text(encoding="utf-8")
        blocks = re.findall(
            r"except Exception as exc:.*?(?=\n    (?:def|class|@)|\Z)", source, flags=re.S
        )
        assert blocks, "找不到任何 broad except —— 本断言的前提消失了，需复核"
        for block in blocks:
            assert "raise" in block, block[:200]

    def test_the_gate_never_treats_a_running_container_as_a_real_roundtrip(self) -> None:
        """🔴 「容器在跑」不等于「本次真跑了 OO 往返」。默认环境必须仍是哨兵。"""
        env = G.default_environment()
        assert env.real_onlyoffice is False
        assert env.real_browser is False
        assert env.onlyoffice_build == "NOT-EXECUTED"

    def test_a_probe_without_validator_or_oracle_cannot_default_to_pass(
        self, facts: tuple[Any, ...]
    ) -> None:
        """既无 validator 又无 oracle 的 probe 必须抛，而不是默认判过。"""
        entry = G._all_signals_ready(facts[0].signals)
        admitted = replace(facts[0], signals=entry)
        orphan = replace(
            next(s for s in G.NON_SCENARIO_PROBES if s.probe_class == "evidence"),
            probe_id="evidence.orphan",
            validator=None,
            scenario_id=None,
            evidence_inputs=(),
        )
        with pytest.raises(G.GateStructuralError, match="无从判定"):
            G.evaluate_probe(
                orphan,
                admitted,
                environment=G.Environment(onlyoffice_build="x", browser_build="y"),
                record={"anything": 1},
                supplied_inputs=frozenset(),
            )


# ═══════════════════════════════════════════════════════════════════════════
# 9. 三条 evidence validator 是真判据
# ═══════════════════════════════════════════════════════════════════════════
def _good_evidence_record(entry: Any) -> dict[str, Any]:
    """一份"六路齐备且 typed slot digest 与本 entry 冻结值逐项相等"的记录。"""
    return {
        "browser_trace_path": "evidence/browser.zip",
        "recovery_application_operation_timeline_path": "evidence/timeline.json",
        "db_timestamps": {"durable_at": "2026-01-01T00:00:00Z"},
        "published_result_representation": {
            "representation_id": "r-1",
            "definition_bundle_slots": {
                name: {"type": "definition", "sha256": digest}
                for name, digest in entry.frozen_slot_digests.items()
            },
        },
        "definition_bundle_sha256": entry.frozen_bundle_identity_sha256,
        "docx_unzip_tag_inventory": {"gt:field:x": 1},
    }


class TestEvidenceValidatorsAreReal:
    """**Validates: Requirements 14.2, 14.3, 14.16**"""

    def test_control_group_passes(self, facts_by_entry: dict[str, Any]) -> None:
        entry = facts_by_entry["f2.stocktake.plan"]
        ok, why = G.validate_evidence_union(entry, _good_evidence_record(entry))
        assert ok, why
        assert "逐项相等" in why

    @pytest.mark.parametrize(
        "dropped",
        [
            "browser_trace_path",
            "recovery_application_operation_timeline_path",
            "db_timestamps",
            "published_result_representation",
            "definition_bundle_sha256",
            "docx_unzip_tag_inventory",
        ],
    )
    def test_dropping_any_one_of_the_six_sources_fails(
        self, facts_by_entry: dict[str, Any], dropped: str
    ) -> None:
        """六路证据**逐个**断言（教训③）。"""
        entry = facts_by_entry["f2.stocktake.plan"]
        record = _good_evidence_record(entry)
        record.pop(dropped)
        ok, why = G.validate_evidence_union(entry, record)
        assert ok is False
        assert dropped in why or "typed slots" in why or "非空" in why

    def test_an_empty_tag_inventory_is_rejected(self, facts_by_entry: dict[str, Any]) -> None:
        """🔴 教训⑥：空集恒等价，必须显式拒（空 dict 由 `_need` 的非空判据拦下）。"""
        entry = facts_by_entry["f2.stocktake.plan"]
        record = _good_evidence_record(entry)
        record["docx_unzip_tag_inventory"] = {}
        ok, why = G.validate_evidence_union(entry, record)
        assert ok is False
        assert "docx_unzip_tag_inventory" in why

    def test_a_non_mapping_tag_inventory_is_rejected(
        self, facts_by_entry: dict[str, Any]
    ) -> None:
        """类型分支必须可达：非空但不是对象（如一个 list）走的是另一条判据。

        🔴 两条分支各有测试 —— 否则 `isinstance` 那一格是不可达代码（假绿）。
        """
        entry = facts_by_entry["f2.stocktake.plan"]
        record = _good_evidence_record(entry)
        record["docx_unzip_tag_inventory"] = ["gt:field:x"]
        ok, why = G.validate_evidence_union(entry, record)
        assert ok is False
        assert "非空对象" in why

    def test_missing_typed_slot_is_rejected(self, facts_by_entry: dict[str, Any]) -> None:
        entry = facts_by_entry["f2.stocktake.plan"]
        record = _good_evidence_record(entry)
        record["published_result_representation"]["definition_bundle_slots"].pop("contract")
        ok, why = G.validate_evidence_union(entry, record)
        assert ok is False
        assert "typed slots" in why

    def test_the_two_entries_have_distinct_frozen_identities(
        self, facts_by_entry: dict[str, Any]
    ) -> None:
        """Task 60 的 cross_entry_isolation：两个 entry 的冻结身份逐项不同。"""
        plan = facts_by_entry["f2.stocktake.plan"]
        summary = facts_by_entry["f2.stocktake.summary"]
        assert plan.frozen_bundle_identity_sha256 != summary.frozen_bundle_identity_sha256
        assert (
            plan.authority_model_definition_sha256
            != summary.authority_model_definition_sha256
        )
        assert plan.contract_canonical_sha256 != summary.contract_canonical_sha256
        for name in ("template", "instrumentation", "contract"):
            assert plan.frozen_slot_digests[name] != summary.frozen_slot_digests[name], name

    @pytest.mark.parametrize("slot", ["template", "instrumentation", "contract"])
    def test_a_slot_digest_from_the_other_entry_is_rejected(
        self, facts_by_entry: dict[str, Any], slot: str
    ) -> None:
        """🔴 三个 slot **逐个**断言（教训③）：每个 F2 entry 保存自身 digest（Property 70）。"""
        plan = facts_by_entry["f2.stocktake.plan"]
        summary = facts_by_entry["f2.stocktake.summary"]
        record = _good_evidence_record(plan)
        record["published_result_representation"]["definition_bundle_slots"][slot][
            "sha256"
        ] = summary.frozen_slot_digests[slot]
        ok, why = G.validate_evidence_union(plan, record)
        assert ok is False
        assert slot in why
        assert "不交叉复用" in why

    def test_an_empty_frozen_plan_is_rejected(self, facts_by_entry: dict[str, Any]) -> None:
        """空计划恒等价 —— 必须显式拒（教训⑥）。"""
        entry = facts_by_entry["f2.stocktake.plan"]
        record = _good_evidence_record(entry)
        ok, why = G.validate_evidence_union(replace(entry, frozen_slot_digests={}), record)
        assert ok is False
        assert "空计划" in why

    def test_a_publication_with_an_empty_slot_digest_is_a_structural_failure(self) -> None:
        publication = json.loads(
            G.PUBLICATION_PATH.read_bytes().decode("utf-8")
        )
        publication["entries"][0]["bundle_slot_plan"]["slots"]["template"][
            "slot_digest"
        ] = ""
        snapshot = {ref.entry_id: dict(OFFLINE_DB_ROW) for ref in G.lane_refs()}
        with pytest.raises(G.GateStructuralError, match="空 slot_digest"):
            G.collect_lane_facts(publication=publication, db_snapshot=snapshot)

    def test_distinct_application_ids_control_group_passes(
        self, facts_by_entry: dict[str, Any]
    ) -> None:
        declared = [s.scenario_id for s in G.SCENARIO_PROBES if s.scenario_id]
        record = {
            "application_ids_by_scenario": {s: f"app-{i}" for i, s in enumerate(declared)}
        }
        ok, why = G.validate_distinct_application_ids(
            facts_by_entry["f2.stocktake.plan"], record
        )
        assert ok, why

    def test_reusing_one_application_id_fails(self, facts_by_entry: dict[str, Any]) -> None:
        declared = [s.scenario_id for s in G.SCENARIO_PROBES if s.scenario_id]
        ids = {s: f"app-{i}" for i, s in enumerate(declared)}
        ids[declared[1]] = ids[declared[0]]
        ok, why = G.validate_distinct_application_ids(
            facts_by_entry["f2.stocktake.plan"], {"application_ids_by_scenario": ids}
        )
        assert ok is False
        assert "复用" in why

    def test_partial_coverage_fails(self, facts_by_entry: dict[str, Any]) -> None:
        declared = [s.scenario_id for s in G.SCENARIO_PROBES if s.scenario_id]
        ids = {s: f"app-{i}" for i, s in enumerate(declared[:3])}
        ok, why = G.validate_distinct_application_ids(
            facts_by_entry["f2.stocktake.plan"], {"application_ids_by_scenario": ids}
        )
        assert ok is False
        assert "覆盖" in why

    def test_an_empty_application_map_is_rejected(
        self, facts_by_entry: dict[str, Any]
    ) -> None:
        ok, why = G.validate_distinct_application_ids(
            facts_by_entry["f2.stocktake.plan"], {"application_ids_by_scenario": {}}
        )
        assert ok is False
        assert "空集" in why

    def test_restoration_control_group_passes(self, facts_by_entry: dict[str, Any]) -> None:
        snapshot = {"working_paper_content_version": 0, "working_paper_sync_operation": 0}
        ok, why = G.validate_full_restoration(
            facts_by_entry["f2.stocktake.plan"],
            {
                "restoration_snapshot_before": snapshot,
                "restoration_snapshot_after": dict(snapshot),
            },
        )
        assert ok, why

    def test_restoration_drift_is_rejected(self, facts_by_entry: dict[str, Any]) -> None:
        ok, why = G.validate_full_restoration(
            facts_by_entry["f2.stocktake.plan"],
            {
                "restoration_snapshot_before": {"a": 0, "b": 1},
                "restoration_snapshot_after": {"a": 0, "b": 2},
            },
        )
        assert ok is False
        assert "未复原" in why

    def test_an_empty_restoration_snapshot_is_rejected(
        self, facts_by_entry: dict[str, Any]
    ) -> None:
        ok, why = G.validate_full_restoration(
            facts_by_entry["f2.stocktake.plan"],
            {"restoration_snapshot_before": {}, "restoration_snapshot_after": {}},
        )
        assert ok is False


# ═══════════════════════════════════════════════════════════════════════════
# 10. 报告：逐 entry / 逐 scenario 结果矩阵
# ═══════════════════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def report(
    offline_snapshot: dict[str, dict[str, Any]], offline_binding_arms: dict[str, Any]
) -> dict[str, Any]:
    return G.build_report(db_snapshot=offline_snapshot, binding_arms=offline_binding_arms)


class TestReportIsPerEntryAndPerScenario:
    """**Validates: Requirements 12.10, 14.9**"""

    def test_seventy_five_probe_rows(self, report: dict[str, Any]) -> None:
        assert report["summary"]["probe_rows"] == 75
        assert len(report["probe_rows"]) == 75

    def test_no_entry_is_verified_today(self, report: dict[str, Any]) -> None:
        assert report["summary"]["entries_verified"] == []
        assert report["summary"]["entries_left_unverifiable"] == [
            "f2.stocktake.plan",
            "f2.stocktake.summary",
        ]
        assert report["summary"]["downstream_tasks_blocked"] is True

    def test_every_scenario_row_exists_once_per_entry(self, report: dict[str, Any]) -> None:
        pairs = [
            (r["entry_id"], r["probe_id"])
            for r in report["probe_rows"]
            if r["entry_id"] is not None
        ]
        assert len(pairs) == len(set(pairs)) == 68

    def test_no_probe_row_is_passed_for_a_scenario(self, report: dict[str, Any]) -> None:
        """🔴 今天不允许任何 scenario 判 passed（未准入 + 无真实执行）。"""
        greens = [
            r["probe_id"]
            for r in report["probe_rows"]
            if r["probe_class"] == "scenario" and r["result"] == G.RESULT_PASSED
        ]
        assert greens == [], greens

    def test_a_row_count_mismatch_is_a_structural_failure(
        self,
        monkeypatch: pytest.MonkeyPatch,
        offline_snapshot: dict[str, dict[str, Any]],
        offline_binding_arms: dict[str, Any],
    ) -> None:
        original = G.probe_registry_payload

        def _inflated() -> dict[str, Any]:
            payload = dict(original())
            payload["total_probe_rows"] = 999
            return payload

        monkeypatch.setattr(G, "probe_registry_payload", _inflated)
        with pytest.raises(G.GateStructuralError, match="分母与执行脱钩"):
            G.build_report(db_snapshot=offline_snapshot, binding_arms=offline_binding_arms)

    def test_observed_environment_is_not_used_for_black_box_verdicts(
        self, report: dict[str, Any]
    ) -> None:
        assert report["environment"]["real_onlyoffice"] is False
        assert report["observed_environment"]["onlyoffice_container_build"] == "9.4.0-129"

    def test_the_exit_code_is_one_while_rows_are_not_all_passed(
        self, report: dict[str, Any]
    ) -> None:
        assert G._exit_code_for(report) == 1


# ═══════════════════════════════════════════════════════════════════════════
# 11. Property 逐条落点
# ═══════════════════════════════════════════════════════════════════════════
class TestProperties:
    """**Validates: Requirements 12.3, 12.10, 14.16**"""

    @pytest.mark.parametrize("prop", list(G.DECLARED_PROPERTIES))
    def test_each_declared_property_lands_on_at_least_one_probe(self, prop: str) -> None:
        owners = [s.probe_id for s in G.ALL_PROBE_SPECS if prop in s.properties]
        assert owners, f"{prop} 无 probe 承载 —— 声明存在而落点缺失即假绿"

    def test_property_titles_come_from_design_md(self) -> None:
        titles = G.design_property_titles()
        assert titles["P33"].startswith("Word pilot")
        assert titles["P34"].startswith("SDT 丢失")
        assert titles["P71"].startswith("evidence 随环境")

    def test_property_71_is_carried_by_the_freshness_probe(self) -> None:
        """P71（evidence 随环境/runner/bundle 变化失效）必须落在载体新鲜度 probe 上。"""
        owners = [s.probe_id for s in G.ALL_PROBE_SPECS if "P71" in s.properties]
        assert "gate.carrier_freshness_is_measured" in owners


# ═══════════════════════════════════════════════════════════════════════════
# 12. 守卫自检（反向）
# ═══════════════════════════════════════════════════════════════════════════
class TestGuardSelfChecks:
    """**Validates: Requirements 14.7**"""

    def test_no_phase_crashed_during_collection(
        self, facts: tuple[Any, ...], report: dict[str, Any]
    ) -> None:
        """🔴 教训⑦：采集穿透会让整 module 变 ERROR，而 `-rf` 只列 FAILED ⇒ 判 GREEN。"""
        assert len(facts) == 2
        assert report["probe_rows"], "报告为空 —— 采集阶段可能已崩"
        assert report["registry"]["registry_digest"]

    def test_the_mutation_probe_is_red_until_the_ledger_exists(self) -> None:
        """变异台账未生成时 `gate.mutation_four_state` 必须 failed（不得默认判过）。"""
        ok, why, payload = G.mutation_coverage_facts()
        assert payload["declared"] > 0, why
        if not G.MUTATION_LEDGER.is_file():
            assert ok is False
            assert payload["executed"] == 0

    def test_every_gate_probe_has_a_runner(
        self, facts: tuple[Any, ...], offline_binding_arms: dict[str, Any]
    ) -> None:
        rows, detail = G.evaluate_gate_probes(facts, binding_arms=offline_binding_arms)
        assert len(rows) == len(G.GATE_PROBES) == 7
        assert sorted(detail) == sorted(s.probe_id for s in G.GATE_PROBES)

    def test_a_gate_probe_without_a_runner_is_a_structural_failure(
        self,
        facts: tuple[Any, ...],
        monkeypatch: pytest.MonkeyPatch,
        offline_binding_arms: dict[str, Any],
    ) -> None:
        monkeypatch.setattr(
            G,
            "GATE_PROBES",
            G.GATE_PROBES + (replace(G.GATE_PROBES[0], probe_id="gate.orphan"),),
        )
        with pytest.raises(G.GateStructuralError, match="一一对应"):
            G.evaluate_gate_probes(facts, binding_arms=offline_binding_arms)

    def test_the_gate_version_is_recorded_for_staleness(self) -> None:
        assert G.GATE_VERSION == "task61-gate/2"
        payload = G.probe_registry_payload()
        assert payload["gate_version"] == G.GATE_VERSION


# ═══════════════════════════════════════════════════════════════════════════
# 13. 绑定约束由三臂实测（gate/2 新增）
# ═══════════════════════════════════════════════════════════════════════════
#
# 首版这道门把「四条结构事实全部成立」当「word_bulk 门未被跨越」的证据，第四条是
# 「生产 registry 里没有注册任何 docx adapter」。2026-09-01 三臂实测证明它是**重言式**：
# 把前三条的前提逐一移除后第四条仍然成立 —— 顶着它的是一条完全不同的平台级约束
# （`working_paper_sync_entry_state` 全表 0 行）。本节把这件事变成可执行判据。
class TestBindingConstraintIsMeasured:
    """**Validates: Requirements 7.3, 12.3**"""

    # ── 登记表形态：三条**分开**断言（教训③）───────────────────────────
    def test_the_constraint_registry_is_not_empty(self) -> None:
        assert G.BINDING_CONSTRAINTS, "空清单会让本 probe 恒成功"

    def test_every_constraint_id_uses_the_task_scoped_prefix(self) -> None:
        """🔴 全局 `BP-NN` 已被 Tasks 60/63/64 各自重复占用（同号不同义）。"""
        for row in G.BINDING_CONSTRAINTS:
            assert re.fullmatch(r"BP-61-\d+", str(row["id"])), row["id"]

    def test_exactly_one_constraint_is_marked_binding(self) -> None:
        binding = [r for r in G.BINDING_CONSTRAINTS if r["kind"] == "binding"]
        assert len(binding) == 1, [r["id"] for r in binding]
        assert binding[0]["id"] == "BP-61-1"

    def test_the_binding_constraint_is_declared_platform_wide(self) -> None:
        """BP-61-1 不是 F2 专属欠账 —— 写成 F2 专属会让它被误派给 Task 61。"""
        binding = next(r for r in G.BINDING_CONSTRAINTS if r["kind"] == "binding")
        assert binding["scope"] == "platform_wide_not_f2_specific"
        assert "Task 61" in binding["owner_task"] and "不属" in binding["owner_task"]

    def test_the_registry_data_file_carries_the_constraints(self) -> None:
        """数据文件是「哪一条是绑定约束」的离线复核处（`git diff` 里可见）。"""
        payload = json.loads(G.REGISTRY_JSON.read_bytes().decode("utf-8"))
        ids = [row["id"] for row in payload["binding_constraints"]]
        assert ids == [row["id"] for row in G.BINDING_CONSTRAINTS]

    # ── 三臂判据：逐条独立打红 ────────────────────────────────────────
    def test_all_three_arms_are_required(self, offline_binding_arms: dict[str, Any]) -> None:
        for dropped in G.BINDING_ARMS:
            arms = {k: v for k, v in offline_binding_arms.items() if k != dropped}
            with pytest.raises(G.GateStructuralError, match="三臂缺"):
                G.binding_constraint_facts(arms)

    def test_arm_b_matching_the_control_reason_verbatim_is_what_demotes_bp_61_2(
        self, offline_binding_arms: dict[str, Any]
    ) -> None:
        facts = G.binding_constraint_facts(offline_binding_arms)
        assert facts["arm_b_reason_equals_control_reason"] is True
        assert facts["binding_constraint_id"] == "BP-61-1"
        assert facts["non_binding_constraint_ids"] == ["BP-61-2"]

    def test_an_arm_b_reason_that_stops_matching_the_control_flips_it_red(
        self, offline_binding_arms: dict[str, Any]
    ) -> None:
        """arm_b 原因不再与对照逐字相等 ⇒ 先后关系变了 ⇒ 拒绝沿用旧裁决。"""
        arms = json.loads(json.dumps(offline_binding_arms))
        arms["arm_b_manifest_flipped"]["synth_reason"] = "别的原因"
        ok, why, facts = G.gate_probe_binding_constraint_is_measured(arms)
        assert ok is False
        assert "逐字相等" in why
        assert facts["binding_constraint_id"] is None

    def test_a_substring_match_is_not_accepted_as_the_same_reason(
        self, offline_binding_arms: dict[str, Any]
    ) -> None:
        """🔴 判「同类」必须逐字相等：子串/前缀相同不算。

        原因文案的真源在 `registry._describe_entry_supply`；允许子串就等于在守卫里
        维护第二份关键词表（抄错看不出，教训②/⑫）。
        """
        arms = json.loads(json.dumps(offline_binding_arms))
        control = arms["arm_a_control"]["control_entry_reason"]
        arms["arm_b_manifest_flipped"]["synth_reason"] = control[:40]
        ok, _why, facts = G.gate_probe_binding_constraint_is_measured(arms)
        assert ok is False
        assert facts["arm_b_reason_equals_control_reason"] is False

    def test_arm_c_not_moving_is_a_hardcoding_signal(
        self, offline_binding_arms: dict[str, Any]
    ) -> None:
        """arm_c 解除供给门后原因不变 ⇒ 本 probe 没在度量顺序（硬编码）⇒ 必须打红。"""
        arms = json.loads(json.dumps(offline_binding_arms))
        arms["arm_c_supply_stubbed"]["synth_reason"] = arms["arm_b_manifest_flipped"][
            "synth_reason"
        ]
        ok, why, facts = G.gate_probe_binding_constraint_is_measured(arms)
        assert ok is False
        assert "硬编码" in why
        assert facts["arm_c_reason_differs_from_arm_b"] is False

    def test_an_empty_planned_denominator_is_rejected(
        self, offline_binding_arms: dict[str, Any]
    ) -> None:
        """教训⑥：分母为空时「零注册」是重言式，必须断言分母非空。"""
        arms = json.loads(json.dumps(offline_binding_arms))
        arms["arm_a_control"]["planned"] = 0
        ok, why, _facts = G.gate_probe_binding_constraint_is_measured(arms)
        assert ok is False
        assert "分母为空" in why

    def test_an_already_registered_adapter_invalidates_the_premise(
        self, offline_binding_arms: dict[str, Any]
    ) -> None:
        """arm_a 出现注册 adapter ⇒ 本门前提已变 ⇒ 必须打红要求重新推导，而不是照旧判过。"""
        arms = json.loads(json.dumps(offline_binding_arms))
        arms["arm_a_control"]["registered_adapter_ids"] = ["f2.stocktake.plan"]
        ok, why, _facts = G.gate_probe_binding_constraint_is_measured(arms)
        assert ok is False
        assert "前提" in why

    def test_a_bad_constraint_id_flips_it_red(
        self, offline_binding_arms: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            G,
            "BINDING_CONSTRAINTS",
            G.BINDING_CONSTRAINTS + ({"id": "BP-30", "kind": "note", "what": "x"},),
        )
        ok, why, _facts = G.gate_probe_binding_constraint_is_measured(offline_binding_arms)
        assert ok is False
        assert "task-scoped" in why

    def test_two_binding_rows_flip_it_red(
        self, offline_binding_arms: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """多条 binding = 没收敛；零条 = 没裁决。两侧都不许过。"""
        monkeypatch.setattr(
            G,
            "BINDING_CONSTRAINTS",
            G.BINDING_CONSTRAINTS + ({"id": "BP-61-9", "kind": "binding", "what": "x"},),
        )
        ok, why, _facts = G.gate_probe_binding_constraint_is_measured(offline_binding_arms)
        assert ok is False
        assert "≠ 1" in why

    def test_the_registry_coverage_check_rejects_an_empty_constraint_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        payload = dict(G.probe_registry_payload())
        payload["binding_constraints"] = []
        with pytest.raises(G.GateStructuralError, match="binding_constraints 为空"):
            G.assert_registry_coverage(payload)

    # ── 真跑那一臂（需要真实库；这是「注入不能换来 passed」的最后一道网）──
    def test_the_three_arms_really_run_against_the_database(self) -> None:
        """不注入替身时三臂必须**真跑**，且真实结果与离线替身的结论一致。

        🔴 这条是本节唯一不接受注入的测试：没有它，`binding_arms=` 就是一个可以喂
        任何形状数据的入口（教训⑤：对照组必须先过；教训⑨：注入而无真实消费方即死代码）。
        库读不到时判 ERROR 态并 skip —— **不**降级成 passed（AC 5.12）。
        """
        try:
            facts = G.binding_constraint_facts()
        except G.DatabaseUnreadable as exc:
            pytest.skip(f"真实库不可达，三臂真跑无法执行：{exc}")
        arm_a = facts["arms"]["arm_a_control"]
        assert arm_a["planned"] > 0
        assert arm_a["registered_adapter_ids"] == []
        assert facts["arms"]["arm_b_manifest_flipped"]["synth_entry_planned"] is True
        assert facts["arm_b_reason_equals_control_reason"] is True
        assert facts["arm_c_reason_differs_from_arm_b"] is True
        assert facts["binding_constraint_id"] == "BP-61-1"

    def test_the_arms_do_not_mutate_the_production_registry(self) -> None:
        """三臂用替身改 `DELIVERED_PER_ENTRY_CONTRACTS` / `_describe_entry_supply`，
        跑完必须逐值复原 —— 否则本进程后续的判据全部不可信。
        """
        if str(_BACKEND) not in sys.path:
            sys.path.insert(0, str(_BACKEND))
        from app.services.workpaper_sync.adapters import registry as registry_module

        before_rows = registry_module.DELIVERED_PER_ENTRY_CONTRACTS
        before_supply = registry_module._describe_entry_supply
        try:
            G.binding_constraint_facts()
        except G.DatabaseUnreadable:
            pytest.skip("真实库不可达")
        assert registry_module.DELIVERED_PER_ENTRY_CONTRACTS is before_rows
        assert registry_module._describe_entry_supply is before_supply

    def test_the_arms_use_an_isolated_engine_not_the_shared_pool(self) -> None:
        """🔴 三臂**必须**用独立 `NullPool` 引擎。

        复用 `app.core.database.async_session` 时，本门 `read_db_snapshot` 那次
        `asyncio.run` 留在共享池里的连接绑定在已关闭的 event loop 上，第二次取到它就报
        `'NoneType' object has no attribute 'send'` ⇒ 被包成 `DatabaseUnreadable` ⇒
        **假 ERROR 态**（gate/2 首跑实测被打成 exit 2，而库其实完全可达）。
        """
        source = inspect.getsource(G._isolated_session_factory)
        # 🔴 断言的是**实参**而不是符号名：只查 `"NullPool" in source` 会被那行
        #    `from sqlalchemy.pool import NullPool` 顶住 —— 删掉 `poolclass=NullPool,`
        #    之后 import 还在，判据照样绿（教训②/⑫的同款形态）。
        assert "poolclass=NullPool" in source
        arms_source = inspect.getsource(G._run_binding_arms)
        assert "async_session" not in arms_source
        assert "arms_engine.dispose()" in arms_source

    def test_the_synthetic_docx_entry_changes_only_the_declared_fields(self) -> None:
        """arm_b 的唯一变量必须真的是 BP-61-2 本身。

        合成 entry 若不把 `document_type` 改成 docx，arm_b 就没有真的解除 BP-61-2 ——
        「原因不变」于是变成一句没有信息量的话（对照组与实验组无差异）。
        """
        raw = G._synthetic_docx_manifest()
        by_id = {e["entry_id"]: e for e in raw["entries"]}
        synth = by_id[G._SYNTH_DOCX_ENTRY_ID]
        source = by_id[G._SYNTH_SOURCE_ENTRY_ID]
        assert synth["document_type"] == "docx"
        assert source["document_type"] == "xlsx"
        assert synth["capability"] == "bidirectional"
        assert synth["editability"] == "editable"
        assert {m["documentType"] for m in synth["mounts"]} == {"docx"}
        differing = sorted(
            k for k in set(synth) | set(source) if synth.get(k) != source.get(k)
        )
        # `editability` / `adapter_id` 不在差集里：源 entry 本来就是 editable / adapter_id=None
        # （实测），合成时的赋值是**幂等**的。把它们写进期望差集会让守卫锁死一个假事实。
        assert differing == [
            "capability",
            "document_type",
            "entry_id",
            "mounts",
        ], differing

    def test_the_probe_declares_its_anchor_in_the_task_text(self) -> None:
        spec = next(
            s for s in G.GATE_PROBES if s.probe_id == "gate.binding_constraint_is_measured"
        )
        body = G.read_task_body()
        assert body.count(spec.anchor) == 1, spec.anchor
