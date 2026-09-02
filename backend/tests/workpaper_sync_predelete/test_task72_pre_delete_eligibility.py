# -*- coding: utf-8 -*-
"""任务 72 Stage A 门的守卫。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 7
被守对象: backend/scripts/check/check_task72_pre_delete_eligibility_gate.py
          backend/data/workpaper_sync_task72_pre_delete_eligibility.json

═══ 这个文件为什么不在 `backend/tests/workpaper_sync/` ═══

BP-69-6：Task 68 的逐字节锁把 `backend/tests/workpaper_sync/` 做成**目录普查**，往里新增任何
一个「不引用被验生产单元」的测试文件都会额外打红它 1~3 条守卫，表象是「上游报告过期」。
Tasks 69/70/71 各自开了目录，本门沿用同一规避法并把「不在普查目录」做成**现算**判据。

═══ 本文件的判据风格：行为 / 结构 / 纯谓词，不用「字符存在」═══

假绿第②源就是「grep 式守卫只查字符串存在」。因此：

* 凡断言某个数字，都用**独立路径**把它重算一遍再比对（现跑门的纯函数、现算 AST、现算 git），
  两侧来源不同才不是自我比对；
* 凡断言某条判据「有效」，都喂**合成输入**让它翻转 —— 一个恒红的门与一个恒绿的门一样没有
  信息量；
* 凡断言「没做某件事」，都要有反证（磁盘 digest、AST 边界），不接受自述。
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

import pytest

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

GATE_REL = "backend/scripts/check/check_task72_pre_delete_eligibility_gate.py"
REPORT_REL = "backend/data/workpaper_sync_task72_pre_delete_eligibility.json"
MUTATE_REL = "backend/scripts/diagnose/mutate_task72_pre_delete_eligibility_guards.py"
GUARD_REL = "backend/tests/workpaper_sync_predelete/test_task72_pre_delete_eligibility.py"

GATE_PATH = REPO / GATE_REL
REPORT_PATH = REPO / REPORT_REL
SPEC_DIR = REPO / ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure"
TASKS_MD = SPEC_DIR / "tasks.md"


def _load_gate() -> Any:
    if "task72_gate" in sys.modules:
        return sys.modules["task72_gate"]
    spec = importlib.util.spec_from_file_location("task72_gate", GATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["task72_gate"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate() -> Any:
    return _load_gate()


@pytest.fixture(scope="module")
def report() -> Mapping[str, Any]:
    assert REPORT_PATH.is_file(), f"{REPORT_REL} 不存在 —— 先跑门的 --write"
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


# ════════════════════════════════════════════════════════════════════════════
# §1 报告新鲜且逐字节锁死
# ════════════════════════════════════════════════════════════════════════════


class TestReportIsFreshAndByteLocked:
    def test_gate_check_passes(self, gate: Any) -> None:
        assert gate.main(["--check"]) == 0, f"现算结果与 {REPORT_REL} 不一致 —— 报告已过期或被手改"

    def test_report_digest_is_self_consistent(self, gate: Any, report: Mapping[str, Any]) -> None:
        recomputed = gate.digest_of(
            gate.strip_volatile({k: v for k, v in report.items() if k != "report_digest"})
        )
        assert recomputed == report["report_digest"]

    def test_source_commit_is_not_excluded_from_the_lock(self, gate: Any) -> None:
        """`source_commit` 必须**留在**锁里 —— 它是「源码变了但结论没刷新」的唯一 stale 轴。"""
        assert "source_commit" not in gate.VOLATILE_KEYS
        assert "report_digest" not in gate.VOLATILE_KEYS
        assert gate.VOLATILE_KEYS == frozenset({"generated_at", "elapsed_seconds"})

    def test_cli_modes_are_mutually_exclusive_and_required(self, gate: Any) -> None:
        with pytest.raises(SystemExit):
            gate.main([])
        with pytest.raises(SystemExit):
            gate.main(["--check", "--write"])

    def test_checkbox_flip_does_not_change_body_digest(self, gate: Any) -> None:
        """把复选框在四态间翻牌，body digest 一字不变（BP-70-6 的正向修复）。"""
        original = TASKS_MD.read_text(encoding="utf-8")
        digests = {gate.sha256_text(gate.task_body())}
        try:
            for mark in (" ", "x", "~", "-"):
                flipped = re.sub(
                    r"^(\s*-\s\[)[ x~\-](\]\s+72\.)",
                    rf"\g<1>{mark}\g<2>",
                    original,
                    count=1,
                    flags=re.M,
                )
                TASKS_MD.write_text(flipped, encoding="utf-8", newline="")
                digests.add(gate.sha256_text(gate.task_body()))
        finally:
            TASKS_MD.write_text(original, encoding="utf-8", newline="")
        assert len(digests) == 1, "复选框状态影响了 body digest —— 编排器勾选即打红（BP-70-6）"


# ════════════════════════════════════════════════════════════════════════════
# §2 vacuous zero 必须不可采纳（本门最容易被做成假绿的一条）
# ════════════════════════════════════════════════════════════════════════════


class TestVacuousZeroIsNotAdmissible:
    def test_zero_with_empty_denominator_is_rejected(self, gate: Any) -> None:
        row = gate.count_admissibility(value=0, denominator=0)
        assert row["zero"] is True
        assert row["admissible"] is False, "空分母下的 0 被当成已清零 —— 空集恒真（假绿第⑥源）"
        assert row["reason"] == "vacuous_zero_empty_denominator"

    def test_zero_with_real_denominator_is_accepted(self, gate: Any) -> None:
        """正例：分母非空时的 0 必须可采纳，否则判据恒假（门永远说红，同样无信息量）。"""
        row = gate.count_admissibility(value=0, denominator=142)
        assert row["admissible"] is True
        assert row["reason"] == "admissible_zero"

    def test_nonzero_is_rejected_regardless_of_denominator(self, gate: Any) -> None:
        for denominator in (0, 1, 142):
            row = gate.count_admissibility(value=3, denominator=denominator)
            assert row["admissible"] is False
            assert row["reason"] == "nonzero"

    def test_evidence_stale_today_is_the_vacuous_kind(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """今天这条红的形态必须被如实记成 vacuous，而不是「已达标的 0」。

        🔴 分母的**出处**由守卫独立重算：直接读 Task 67 报告数 `evidence_stale_is_measurable`，
        不经门的任何函数。首版只读门写出的报告，被「把分母偷换成 entry 总数」那条变异绕过
        （只打红了逐字节锁 = WRONG-TEST，语义判据毫无反应）。
        """
        live = gate.build_five_counts()
        t67 = json.loads(
            (REPO / "backend/data/workpaper_sync_task67_structural_pre_reconcile.json").read_text(
                encoding="utf-8"
            )
        )
        independent = [row for row in (t67.get("entries") or []) if row.get("independent_entry")]
        measurable = sum(
            1
            for row in independent
            if (row.get("verdicts") or {}).get("evidence_stale_is_measurable") is True
        )
        assert live["denominators"]["evidence_stale_denominator"] == measurable, (
            "evidence stale 的分母不是「可度量的 entry 数」—— 分母被偷换会让 vacuous zero 变成"
            "「可采纳的 0」，Stage A 凭空少一条红"
        )
        assert live["denominators"]["evidence_stale_denominator"] != len(independent), (
            "分母等于独立 entry 总数 ⇒ 用的是 entry 数而不是可度量数"
        )
        # 🔴 断言**现算**的 admissibility 行，不是盘上那一行：`denominators` 与
        #    `admissibility[...]["denominator"]` 是两个独立赋值点，只查前者会漏掉「传给
        #    count_admissibility 的那个分母被偷换」这条路径（实测：只打红逐字节锁 = WRONG-TEST）。
        live_row = live["admissibility"]["evidence_stale"]
        assert live_row["denominator"] == measurable == 0, (
            "传给 count_admissibility 的分母不是可度量数 —— vacuous zero 会被算成「可采纳的 0」"
        )
        assert live_row["admissible"] is False
        assert live_row["reason"] == "vacuous_zero_empty_denominator"
        row = report["five_counts"]["admissibility"]["evidence_stale"]
        assert row["value"] == 0
        assert row["denominator"] == measurable == 0
        assert row["admissible"] is False
        assert row["reason"] == "vacuous_zero_empty_denominator"
        assert (
            report["five_counts"]["denominators"]["sync_test_run_rows_measured_by_task70"] == 0
        ), "test_run 行数非 0 时 evidence stale 的分母就不该为空 —— 两侧来源必须一致"


# ════════════════════════════════════════════════════════════════════════════
# §3 Stage A 谓词词表封闭 + AC 12.13 的两条禁令
# ════════════════════════════════════════════════════════════════════════════


class TestStageAPredicateVocabulary:
    def test_extra_predicate_raises_instead_of_silently_concluding(self, gate: Any) -> None:
        """偷偷加一条谓词必须**抛**，而不是静静算出一个结论。"""
        predicates = {pid: True for pid in gate.STAGE_A_PREDICATE_IDS}
        predicates["pending_delete_unreachable_is_zero"] = True
        with pytest.raises(gate.Task72GateError):
            gate.stage_a_state(predicates)

    def test_missing_predicate_raises(self, gate: Any) -> None:
        """摘掉一条（比如把 evidence stale 摘掉让门变绿）必须抛。"""
        predicates = {pid: True for pid in gate.STAGE_A_PREDICATE_IDS}
        predicates.pop("evidence_stale_is_admissibly_zero")
        with pytest.raises(gate.Task72GateError):
            gate.stage_a_state(predicates)

    def test_stage_a_never_requires_unreachable_to_be_zero(self, gate: Any) -> None:
        """AC 12.13 逐字：不得把「待删 unreachable 已为 0」当 Stage A 前置条件。

        两侧都要：真词表干净 **+ 检出器对合成违规词表真的命中**。只查前者时「把检出条件改成
        `if False`」是等价变异（实测 GREEN）—— 检出器坏掉与词表合规长得一模一样。
        """
        facts = gate.stage_a_vocabulary_excludes_unreachable_zero()
        assert facts["offending_predicate_ids"] == []
        assert facts["excludes_unreachable_zero"] is True

        planted = gate.stage_a_vocabulary_excludes_unreachable_zero(
            (
                "unadjudicated_is_admissibly_zero",
                "pending_delete_unreachable_is_zero",
                "unreachable_stubs_cleared",
            )
        )
        assert planted["excludes_unreachable_zero"] is False, "检出器对违规词表不命中 ⇒ 判据恒真"
        assert sorted(planted["offending_predicate_ids"]) == [
            "pending_delete_unreachable_is_zero",
            "unreachable_stubs_cleared",
        ]

    def test_ac_12_13_really_contains_both_clauses(self, gate: Any) -> None:
        """法源现读：AC 12.13 必须真的点名四个零 + 唯一命中 + 那条禁令。"""
        clauses = gate.requirement_clauses()
        assert clauses["ac_12_13_names_four_zeros"] is True
        assert clauses["ac_12_13_requires_unique_plan_landing"] is True
        assert clauses["ac_12_13_forbids_requiring_unreachable_zero_upfront"] is True


class TestStageAIsNotPermanentlyRed:
    def test_all_green_input_returns_green(self, gate: Any) -> None:
        """🔴 最重要的一条：全绿输入下门必须返回 green。恒红门与恒绿门一样没有信息量。"""
        assert gate.stage_a_state({pid: True for pid in gate.STAGE_A_PREDICATE_IDS}) == "green"

    def test_every_predicate_alone_can_turn_it_red(self, gate: Any) -> None:
        """每条谓词都必须**参与**结论 —— 存在不参与的谓词就是 additive 死判据（假绿第①源）。"""
        for pid in gate.STAGE_A_PREDICATE_IDS:
            probe = {other: True for other in gate.STAGE_A_PREDICATE_IDS}
            probe[pid] = False
            assert gate.stage_a_state(probe) == "red", f"{pid} 单独为假时门仍为 green"

    def test_report_records_the_sensitivity(self, gate: Any, report: Mapping[str, Any]) -> None:
        arms = report["counterfactual_arms"]
        assert arms["gate_can_go_green"] is True
        assert arms["every_predicate_alone_can_turn_it_red"] is True
        assert arms["arm_count"] == len(report["stage_a"]["predicate_ids"])

        # 🔴 注入一个「全绿也返回 red」的假实现：全绿探针若不是真跑的，这里察觉不到。
        #    首版只读报告字段，被「把探针结果内联写死成 green」那条变异绕过（实测 GREEN）。
        injected = gate.build_counterfactual_arms(
            report["stage_a"], state_fn=lambda predicates: "red"
        )
        assert injected["gate_can_go_green"] is False, (
            "喂了恒红的 state_fn 后仍报「本门会变绿」⇒ 全绿探针没有真跑，那个结论是写死的"
        )
        assert injected["every_predicate_alone_can_turn_it_red"] is True

        honest = gate.build_counterfactual_arms(
            report["stage_a"], state_fn=lambda predicates: "green"
        )
        assert honest["every_predicate_alone_can_turn_it_red"] is False, (
            "喂了恒绿的 state_fn 后仍报「每条谓词都能翻红」⇒ 单谓词探针也没真跑"
        )


# ════════════════════════════════════════════════════════════════════════════
# §4 Stage A 今天为红，且每条红都有实测数字 + owner
# ════════════════════════════════════════════════════════════════════════════


class TestStageAIsRedTodayWithAttribution:
    def test_stage_a_is_red(self, report: Mapping[str, Any]) -> None:
        assert report["stage_a"]["state"] == "red"
        assert report["verdict"]["state"] == "stage_a_red"
        assert report["verdict"]["task_72_completable"] is False

    def test_every_failing_predicate_has_measured_numbers_and_owner(
        self, report: Mapping[str, Any]
    ) -> None:
        detail = report["stage_a"]["predicate_detail"]
        for pid in report["stage_a"]["failing_predicates"]:
            row = detail[pid]
            assert row.get("measured"), f"{pid} 没有实测数字 —— 只有结论不构成证据"
            assert str(row.get("owner_task")).strip(), f"{pid} 没点名 owner"
            assert str(row.get("statement")).strip()

    def test_five_counts_recompute_agrees_with_task67(self, gate: Any) -> None:
        """独立路径重算：逐 entry 现算 vs Task 67 自述必须一致（跨文件双向锁）。"""
        counts = gate.build_five_counts()
        assert counts["all_recomputes_agree"] is True
        for key, agrees in counts["recompute_agrees_with_task67_primary"].items():
            assert agrees, f"{key} 的逐 entry 现算与 Task 67 自述不符"

    #: 正文点名的六个 scenario id，**在守卫这一侧独立声明**。
    #: 🔴 首版拿 `gate.NAMED_REQUIRED_SCENARIOS` 与它自己比，是自我比对：删掉其中一条时两侧
    #:    同步变小，判据毫无反应（实测只打红了逐字节锁 = WRONG-TEST）。
    EXPECTED_NAMED = (
        "close_leader_revoked_no_successor_recovery_required",
        "close_leader_revoked_successor_exactly_one",
        "cross_participant_idempotency_409",
        "opaque_version_rollback_no_numeric_collision",
        "quarantined_rejects_application_and_engine",
        "same_application_higher_sequence_fold",
    )

    def test_named_required_scenarios_are_recomputed_not_read_from_verdict(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """现算执行档并与 Task 70 自述比对；两侧一致才算复核过。"""
        live = gate.build_required_scenario_execution()
        assert live["agrees_with_task70_self_report"] is True
        assert live["required_scenario_rows_recomputed"] == report[
            "required_scenario_execution"
        ]["required_scenario_rows_recomputed"]
        assert live["named_scenarios_missing_from_task70"] == []
        assert live["all_named_really_executed"] is False
        assert sorted(gate.NAMED_REQUIRED_SCENARIOS) == list(self.EXPECTED_NAMED), (
            "点名 scenario 集合与守卫侧独立声明不符 —— 分母被缩小或掉换（正文点名的五类）"
        )
        assert sorted(live["named_scenarios_not_executed"]) == list(self.EXPECTED_NAMED)

    def test_scenario_agreement_really_reports_a_mismatch(self, gate: Any) -> None:
        """跨文件双向锁的反向自检：喂不一致的两侧，必须报 False。

        首版只断言「今天一致」，被「把该字段写死成 True」那条变异绕过（实测 GREEN）——
        今天两侧本来就一致，写死与真算长得一样。
        """
        assert (
            gate.scenario_counts_agree(
                recomputed_rows=3290,
                recomputed_executed=0,
                self_reported_rows=3290,
                self_reported_executed=0,
            )
            is True
        )
        assert (
            gate.scenario_counts_agree(
                recomputed_rows=3290,
                recomputed_executed=0,
                self_reported_rows=3290,
                self_reported_executed=3290,
            )
            is False
        ), "上游自述说全跑过、现算说一条没跑，判据却说一致 ⇒ 双向锁失效"
        assert (
            gate.scenario_counts_agree(
                recomputed_rows=1,
                recomputed_executed=0,
                self_reported_rows=3290,
                self_reported_executed=0,
            )
            is False
        )

    def test_empty_scenario_family_is_not_a_pass(self, gate: Any) -> None:
        """「零场景全部通过」不是通过。"""
        assert gate.family_execution_state({})["really_executed"] is False
        assert gate.family_execution_state({"unrunnable_today": 5})["really_executed"] is False
        assert gate.family_execution_state({"executed_end_to_end": 5})["really_executed"] is True

    def test_multi_resolver_criterion_needs_both_conditions(self, gate: Any) -> None:
        """计数为 0 但仍 deferred ⇒ 准则不过（正文逐字「任一行仍 deferred 或计数非零」）。"""
        assert (
            gate.multi_resolver_criterion_passes(multi_resolver_rows=[], rows_still_deferred=[])
            is True
        )
        assert (
            gate.multi_resolver_criterion_passes(
                multi_resolver_rows=[], rows_still_deferred=["get_whole_excel_grid"]
            )
            is False
        )
        assert (
            gate.multi_resolver_criterion_passes(
                multi_resolver_rows=["x"], rows_still_deferred=[]
            )
            is False
        )

    def test_multi_resolver_matrix_rows_are_read_live(self, gate: Any) -> None:
        """Task 12 矩阵四行现读：全部在册且今天全部 deferred。"""
        facts = gate.resolver_matrix_facts()
        assert facts["rows_absent_from_matrix"] == [], "有 resolver 行不在 Task 12 矩阵里"
        assert sorted(facts["rows_still_deferred"]) == sorted(gate.MULTI_RESOLVER_ROWS)

    def test_matrix_reader_narrows_by_module_not_just_by_name(
        self, gate: Any, tmp_path: Path
    ) -> None:
        """喂**植入矩阵**：同名函数出现在别的 module 时不得被误取。

        首版只读真矩阵，被「删掉 module 收窄条件」那条变异绕过（实测 GREEN）—— 今天没有别的
        module 有这些同名函数，去掉收窄与保留收窄长得一样。植入才测得出身份唯一性。
        """
        planted = tmp_path / "planted_matrix.json"
        planted.write_text(
            json.dumps(
                {
                    "rows": [
                        # 🔴 顺序刻意让**真身在前、冒充者在后**：dict 推导保留最后一次赋值，
                        #    真身在后时去掉 module 收窄也仍然"碰巧"取对（首轮实测 GREEN）。
                        {
                            "qualname": "get_whole_excel_grid",
                            "module": "app.routers.wp_onlyoffice_router",
                            "status": "deferred",
                            "intended_status": "deferred",
                            "blocking_task": "21,25,26,36",
                            "adjudication_owner_task": "71",
                        },
                        {
                            "qualname": "get_whole_excel_grid",
                            "module": "app.routers.some_other_router",
                            "status": "migrated",
                            "intended_status": "migrated",
                            "blocking_task": "0",
                            "adjudication_owner_task": "0",
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        facts = gate.resolver_matrix_facts(planted)
        row = facts["per_row"]["get_whole_excel_grid"]
        assert row["status"] == "deferred", (
            "读到了别的 module 的同名行 —— resolver 身份不唯一，`status` 会被张冠李戴"
        )
        assert "get_whole_excel_grid" in facts["rows_still_deferred"]


# ════════════════════════════════════════════════════════════════════════════
# §5 待删项唯一命中判据的四个维度
# ════════════════════════════════════════════════════════════════════════════


class TestPendingDeleteLanding:
    def test_all_four_dimensions_are_load_bearing(self, gate: Any) -> None:
        """四个维度逐一单独打掉都必须让「唯一命中」为假；四个都满足时为真。"""
        bindings = {name: True for name in gate.REQUIRED_BINDINGS}
        clean = gate.pending_delete_landing_verdict(
            plan_item_count_for_subject=1,
            bindings_present=bindings,
            digest_matches_disk=True,
            rollback_recoverable=True,
        )
        assert clean["uniquely_landed"] is True, "全满足时不成立 ⇒ 判据恒假"

        for kwargs, marker in (
            ({"plan_item_count_for_subject": 2}, "plan_item_count"),
            ({"plan_item_count_for_subject": 0}, "plan_item_count"),
            ({"digest_matches_disk": False}, "digest_drift"),
            ({"rollback_recoverable": False}, "rollback_not_recoverable"),
        ):
            args: dict[str, Any] = {
                "plan_item_count_for_subject": 1,
                "bindings_present": bindings,
                "digest_matches_disk": True,
                "rollback_recoverable": True,
            }
            args.update(kwargs)
            row = gate.pending_delete_landing_verdict(**args)
            assert row["uniquely_landed"] is False
            assert any(marker in reason for reason in row["failure_reasons"])

        for missing in gate.REQUIRED_BINDINGS:
            partial = dict(bindings)
            partial[missing] = False
            row = gate.pending_delete_landing_verdict(
                plan_item_count_for_subject=1,
                bindings_present=partial,
                digest_matches_disk=True,
                rollback_recoverable=True,
            )
            assert row["uniquely_landed"] is False
            assert missing in row["missing_bindings"]

    def test_subject_granularity_is_item_id_not_path(self, report: Mapping[str, Any]) -> None:
        """按 path 判唯一性会把 80 条多 item 路径全打成重复命中 —— 那是判据错。"""
        landing = report["pending_delete_landing"]
        assert landing["subject_granularity"] == "item_id"
        assert (
            landing["pending_delete_subject_total"] > landing["pending_delete_distinct_path_total"]
        ), "subject 数不大于路径数 ⇒ 多 item 路径的事实没被覆盖到，判据粒度无从验证"

    def test_rollback_dimension_is_what_fails_today(self, report: Mapping[str, Any]) -> None:
        landing = report["pending_delete_landing"]
        assert landing["all_subjects_uniquely_landed"] is False
        assert "rollback_not_recoverable" in landing["failure_reason_histogram"]
        assert landing["task66_rollback_isolation_verdict"] == "blocked"

    def test_replacement_surface_untracked_is_measured_live(self, gate: Any) -> None:
        """替代面「未入库」现测（git ls-files），不读 Task 66 的登记值。"""
        landing = gate.build_pending_delete_landing()
        assert landing["replacement_surface_untracked_live_count"] > 0
        assert landing["replacement_surface_untracked_live_count"] <= landing[
            "replacement_surface_total"
        ]
        assert landing["recompute_agrees_with_task66_isolation"] is True

    def test_untracked_measurement_provenance_is_git_not_the_upstream_field(
        self, gate: Any
    ) -> None:
        """AST 判据：该度量必须真调 `_git(["ls-files", ...])`，不得读 `tracked_in_git` 登记值。

        今天两个来源给出同一个数（22 == 22）⇒ 换成读登记值是**等价变异**，数值判据测不出差别
        （实测 GREEN）。判据因此落在**取值出处**上，而出处只能用 AST 判 —— 子串会被说明文字骗到。
        """
        source = (REPO / GATE_REL).read_text(encoding="utf-8")
        tree = ast.parse(source)
        func = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "build_pending_delete_landing"
        )
        git_ls_files_calls = [
            node
            for node in ast.walk(func)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_git"
            and any(
                isinstance(element, ast.Constant) and element.value == "ls-files"
                for arg in node.args
                if isinstance(arg, (ast.List, ast.Tuple))
                for element in arg.elts
            )
        ]
        assert git_ls_files_calls, (
            "替代面入库状态不是用 `_git([\"ls-files\", ...])` 现测的 —— 读上游登记值时上游一旦"
            "过期本门跟着错，「独立复核」四个字被架空"
        )
        read_upstream_field = [
            node
            for node in ast.walk(func)
            if isinstance(node, ast.Constant) and node.value == "tracked_in_git"
        ]
        assert not read_upstream_field, "函数里出现了对上游 `tracked_in_git` 登记值的读取"

    def test_untracked_at_plan_commit_is_measured_by_git(self, gate: Any) -> None:
        """`git ls-tree <plan_commit>` 现算 —— 不信计划里的 `tracked_at_plan_time` 自述。"""
        landing = gate.build_pending_delete_landing()
        tracked = gate.git_tracked_at(landing["plan_commit"], landing["paths_untracked_at_plan_commit"])
        assert tracked and not any(tracked.values()), "现算说它们在 plan commit 上是 tracked"


# ════════════════════════════════════════════════════════════════════════════
# §6 Stage B 没有执行，且有反证
# ════════════════════════════════════════════════════════════════════════════


class TestStageBWasNotExecuted:
    def test_stage_b_is_blocked_and_reports_zero_deletions(
        self, report: Mapping[str, Any]
    ) -> None:
        stage_b = report["stage_b"]
        assert stage_b["state"] == "blocked"
        assert stage_b["executed"] is False
        assert stage_b["bytes_deleted"] == 0
        assert stage_b["files_deleted"] == 0
        assert stage_b["blocked_by"] == ["stage_a_red"]

    def test_disk_still_matches_the_plan_digests(self, gate: Any, report: Mapping[str, Any]) -> None:
        """反证而不是自述：待删对象的磁盘 sha256 与 plan 登记值逐条全等。

        并且**喂一个带漂移的合成 landing**：反证必须翻成 False。首版只断言「今天全等」，被
        「把反证写死成 True」那条变异绕过（实测 GREEN）—— 今天本来就全等。

        🔴 **2026-09-02 起有一条具名的 out-of-band 移除**（`useG7LonTerDualMode.ts`，用户点名清理
        指向已删模块的 `@deprecated` 墓碑）。所以「未动」的判据从「缺失/漂移一条都没有」改成「除
        经现场核验通过的登记外一条都没有」——**分母没有变小**：全量 `paths_missing_from_disk` /
        `digest_drift_paths` 照旧全量报出，只是多了 `unexplained_*` 两个字段作结论口径，未登记的
        缺失仍一条不放（下面三条测试逐条守登记本身不能当万能豁免）。
        """
        proof = report["stage_b"]["non_execution_proof"]
        excused = set(report["stage_b"]["out_of_band_removals"]["valid_paths"])
        assert proof["unexplained_digest_drift_paths"] == []
        assert proof["unexplained_paths_missing_from_disk"] == []
        assert set(proof["paths_missing_from_disk"]) <= excused, (
            "有待删对象已不在盘上却没有 out-of-band 登记 —— 可能有人偷偷执行了 Stage B"
        )
        assert set(proof["digest_drift_paths"]) <= excused
        assert proof["disk_matches_plan_digest_everywhere"] is True
        assert proof["pending_delete_paths_checked"] > 0

        drifted = dict(report["pending_delete_landing"])
        drifted["digest_drift_paths"] = ["audit-platform/frontend/src/some/legacy.ts"]
        flipped = gate.build_stage_b(stage_a_state_value="red", landing=drifted)
        assert flipped["non_execution_proof"]["disk_matches_plan_digest_everywhere"] is False, (
            "喂了 digest 漂移后反证仍说「磁盘未动」⇒ 那个结论是写死的，Stage B 失去唯一客观证据"
        )

        missing = dict(report["pending_delete_landing"])
        missing["paths_missing_from_disk"] = ["audit-platform/frontend/src/some/deleted.ts"]
        flipped2 = gate.build_stage_b(stage_a_state_value="red", landing=missing)
        assert flipped2["non_execution_proof"]["disk_matches_plan_digest_everywhere"] is False

    def test_the_out_of_band_registry_is_verified_not_believed(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """登记的每一条都必须**现场核验**通过：在计划待删集合里、盘上确实已不在、计划登记一致。"""
        oob = report["stage_b"]["out_of_band_removals"]
        assert oob["records"], "登记为空却仍保留这套机制 —— 要么删机制，要么它没生效"
        assert oob["all_valid"] is True, oob["invalid_records"]
        for row in oob["records"]:
            assert row["problems"] == []
            assert row["plan_item_ids"], f"{row['path']} 在 Task 66 计划里找不到 item"
            assert row["plan_disposition"] == ["pending_delete"], row
            assert not (REPO / row["path"]).exists(), (
                f"{row['path']} 登记成已 out-of-band 移除，却仍在盘上"
            )
            assert row["counts_as_stage_b_execution"] == "false"
            assert len(row["why"]) > 80, "登记必须写清为什么这一条可以在 Stage B 之外移除"
        assert report["stage_b"]["executed"] is False
        assert report["stage_b"]["files_deleted"] == 0

    def test_planting_an_unrelated_path_in_the_registry_still_turns_the_proof_red(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """🔴 变异锚点：登记不是万能豁免。

        三种伪登记各自必须打红：

        * **还在盘上的路径**（它根本没被移除）⇒ `registered_but_still_on_disk`；
        * **计划外路径** ⇒ `registered_but_not_in_plan`；
        * **disposition 与计划不符** ⇒ `plan_disposition_mismatch`。

        没有这条，`OUT_OF_BAND_REMOVALS` 就是一个「往里加一行即变绿」的后门 —— 与「加豁免列」
        逐字同型。
        """
        plan_items = [
            item
            for item in (gate.read_json(gate.T66_REPORT).get("items") or [])
            if str(item.get("disposition")) == "pending_delete"
        ]
        pending_paths = [str(item.get("path")) for item in plan_items]
        on_disk_pending = next(
            path for path in pending_paths if (REPO / path).is_file()
        )

        still_present = gate.validate_out_of_band_removals(
            pending_paths=pending_paths,
            plan_items=plan_items,
            registry=(
                {
                    "path": on_disk_pending,
                    "directive": "planted",
                    "expected_disposition": "pending_delete",
                    "expected_category": "legacy_composable",
                    "why": "x" * 100,
                    "counts_as_stage_b_execution": "false",
                },
            ),
        )
        assert still_present["all_valid"] is False
        assert "registered_but_still_on_disk" in still_present["records"][0]["problems"]

        outside_plan = gate.validate_out_of_band_removals(
            pending_paths=pending_paths,
            plan_items=plan_items,
            registry=(
                {
                    "path": "audit-platform/frontend/src/not/in/the/plan.ts",
                    "directive": "planted",
                    "expected_disposition": "pending_delete",
                    "expected_category": "legacy_composable",
                    "why": "x" * 100,
                    "counts_as_stage_b_execution": "false",
                },
            ),
        )
        assert outside_plan["all_valid"] is False
        assert "registered_but_not_in_plan" in outside_plan["records"][0]["problems"]

        wrong_disposition = gate.validate_out_of_band_removals(
            pending_paths=pending_paths,
            plan_items=plan_items,
            registry=(
                {
                    **gate.OUT_OF_BAND_REMOVALS[0],
                    "expected_disposition": "keep",
                },
            ),
        )
        assert wrong_disposition["all_valid"] is False
        assert any(
            problem.startswith("plan_disposition_mismatch")
            for problem in wrong_disposition["records"][0]["problems"]
        )

        # 行为级收口：伪登记进 stage_b 之后，「磁盘未动」的反证必须翻红，且结构错误必须点名它。
        planted_stage_b = gate.build_stage_b(
            stage_a_state_value="red",
            landing={
                **report["pending_delete_landing"],
                "paths_missing_from_disk": ["audit-platform/frontend/src/some/deleted.ts"],
            },
            out_of_band=still_present,
        )
        assert (
            planted_stage_b["non_execution_proof"]["disk_matches_plan_digest_everywhere"] is False
        )
        planted_report = dict(report)
        planted_report["stage_b"] = planted_stage_b
        verdict = gate.build_verdict(planted_report)
        assert any(
            "out-of-band" in error for error in verdict["structural_errors"]
        ), verdict["structural_errors"]

    def test_the_registered_removal_did_not_change_any_stage_a_predicate(
        self, report: Mapping[str, Any]
    ) -> None:
        """out-of-band 移除**不许**改变 Stage A 的任何谓词判定（实测：删前删后 7 条同名同集合）。

        `every_pending_delete_uniquely_lands_in_plan` 早已因 2 条 `rollback_not_recoverable` 为红；
        被移除那条只是给 landing 的失败清单多加一行 `digest_drift`，不改变任何谓词的真假。
        """
        failing = {
            str(item["name"]) if isinstance(item, Mapping) else str(item)
            for item in report["verdict"]["stage_a_failing_predicates"]
        }
        assert "every_pending_delete_uniquely_lands_in_plan" in failing
        histogram = report["pending_delete_landing"]["failure_reason_histogram"]
        assert histogram.get("rollback_not_recoverable", 0) >= 2, (
            "那两条与本次 out-of-band 移除无关的失败项消失了 —— 谓词的红不再独立于本次移除"
        )

    def test_gate_source_has_no_delete_primitive(self, gate: Any) -> None:
        """AST 边界：门源码里没有删除原语，写盘只打 OUTPUT_PATH。"""
        facts = gate._self_ast_write_targets()
        assert facts["delete_primitives_found"] == []
        assert facts["no_delete_primitive"] is True
        assert facts["write_calls_only_output_path"] is True

    def test_delete_primitive_detector_actually_fires(self, gate: Any) -> None:
        """反向自检：把删除原语真喂给**同一个**判据函数，必须命中。

        没有这条，上一条测试可能只是**检测器坏了**（永远返回空集）—— 那是假绿第②源的 AST 版本。
        判据函数吃 source 字符串，因此这里喂的是合成源码而不是复制一份检测逻辑（复制即自我比对）。
        """
        sample = (
            "import os\n"
            "import shutil\n"
            "from pathlib import Path\n"
            "shutil.rmtree(Path('x'))\n"
            "os.remove('y')\n"
            "Path('z').unlink()\n"
            "TARGET.write_text('a')\n"
        )
        facts = gate.scan_source_boundary(sample)
        assert facts["no_delete_primitive"] is False
        assert "shutil.rmtree" in facts["delete_primitives_found"]
        assert "os.remove" in facts["delete_primitives_found"]
        assert any(name.endswith(".unlink") for name in facts["delete_primitives_found"])
        assert facts["write_calls_only_output_path"] is False, (
            "写盘目标是 TARGET 而不是 OUTPUT_PATH，判据却说合规 ⇒ 该判据恒真"
        )

    def test_write_target_detector_accepts_the_legitimate_shape(self, gate: Any) -> None:
        """正例：只写 `OUTPUT_PATH` 的源码必须判合规，否则该判据恒假。"""
        facts = gate.scan_source_boundary("OUTPUT_PATH.write_text('x')\n'a'.replace('a','b')\n")
        assert facts["write_calls_only_output_path"] is True
        assert facts["no_delete_primitive"] is True, "`str.replace` 又被当成删除原语了"

    def test_str_replace_is_not_mistaken_for_a_delete_primitive(self, gate: Any) -> None:
        """首版实测过的假红：只按方法名判会把 `str.replace` 当成删除原语。"""
        assert "replace" not in gate._DELETE_CALLS
        assert "remove" not in gate._DELETE_CALLS
        assert ("os", "replace") in gate._QUALIFIED_DELETE_CALLS
        assert ("os", "remove") in gate._QUALIFIED_DELETE_CALLS


# ════════════════════════════════════════════════════════════════════════════
# §7 Stage C / Stage D：UNVERIFIABLE 与「未运行 ≠ 静默 skip」
# ════════════════════════════════════════════════════════════════════════════


class TestStageCIsHonestlyUnverifiable:
    def test_stage_c_is_unverifiable_with_named_missing_preconditions(
        self, report: Mapping[str, Any]
    ) -> None:
        stage_c = report["stage_c"]
        assert stage_c["state"] == "unverifiable"
        assert stage_c["executed"] is False
        assert stage_c["not_a_silent_skip"] is True
        assert stage_c["new_test_runs_created"] == 0
        assert stage_c["what_stage_c_needs"], "没写清缺什么前置条件 ⇒ 无法被解除"

    def test_source_commit_really_is_unchanged(self, gate: Any, report: Mapping[str, Any]) -> None:
        """现算 HEAD 与上游五份报告的 source commit 全等 ⇒ Stage C 的触发条件不成立。"""
        head = gate.git_head()
        assert report["stage_c"]["source_commit_head"] == head
        assert report["stage_c"]["source_commit_unchanged_since_upstream_runs"] is True
        assert set(report["stage_c"]["upstream_report_source_commits"].values()) == {head}

    def test_forbidden_substitutes_are_named(self, report: Mapping[str, Any]) -> None:
        assert set(report["stage_c"]["forbidden_substitutes"]) >= {
            "离线测试",
            "smoke",
            "文档声明",
            "合成 measurement",
        }


class TestStageDDistinguishesNotRunFromSkip:
    def test_run_decision_has_no_skip_state(self, gate: Any) -> None:
        """返回值域里根本没有 `skipped` —— 正文「禁止静默 skip」。"""
        assert gate.stage_d_run_decision("red") == gate.STAGE_D_NOT_RUN
        assert gate.stage_d_run_decision("green") == gate.STAGE_D_RUN
        assert "skip" not in gate.STAGE_D_NOT_RUN.replace("not_run_because_stage_a_red", "")
        assert {gate.stage_d_run_decision(state) for state in ("red", "green", "anything")} == {
            gate.STAGE_D_RUN,
            gate.STAGE_D_NOT_RUN,
        }

    def test_all_six_final_gates_are_recorded_as_not_run_with_a_reason(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """🔴 **现跑** `build_stage_d` 而不是读盘上报告：只读产物的判据对实现侧改动天生不敏感
        （首版被「把 `run` 写死成 True」那条变异绕过，只打红了逐字节锁 = WRONG-TEST）。
        """
        live = gate.build_stage_d(
            stage_a=report["stage_a"],
            counts=gate.build_five_counts(),
            landing=report["pending_delete_landing"],
        )
        for source, gates in (("live", live["final_gates"]), ("report", report["stage_d"]["final_gates"])):
            assert sorted(gates) == sorted(gate.STAGE_D_FINAL_GATES), source
            for name, row in gates.items():
                assert row["run"] is False, f"[{source}] {name} 声称已运行，但 Stage A 为红"
                assert row["reason"] == gate.STAGE_D_NOT_RUN
                assert row["not_a_silent_skip"] is True
                assert str(row["why_not_run"]).strip()
        assert live["final_gates_run_count"] == 0
        assert live["final_gates_silently_skipped_count"] == 0
        assert report["stage_d"]["final_gates_run_count"] == 0
        assert report["stage_d"]["final_gates_silently_skipped_count"] == 0

    def test_stage_d_precondition_flips_once_stage_a_goes_green(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """正例：Stage A 变绿后前置条件必须翻 True，否则「未运行」也只是写死的一句话。

        `run` 仍为 False 是**诚实**的 —— 本门从不执行 Stage D 的最终门。会变的是前置条件。
        """
        live = gate.build_stage_d(
            stage_a={"state": "green"},
            counts=gate.build_five_counts(),
            landing=report["pending_delete_landing"],
        )
        assert live["state"] == gate.STAGE_D_RUN
        assert all(row["stage_a_precondition_met"] is True for row in live["final_gates"].values())
        assert all(row["run"] is False for row in live["final_gates"].values())
        red = gate.build_stage_d(
            stage_a={"state": "red"},
            counts=gate.build_five_counts(),
            landing=report["pending_delete_landing"],
        )
        assert all(
            row["stage_a_precondition_met"] is False for row in red["final_gates"].values()
        )

    def test_unreachable_is_a_stage_d_condition_not_a_stage_a_one(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        five = report["stage_d"]["post_delete_five_zeros"]
        assert set(five) == {
            "unadjudicated",
            "fake_bidirectional",
            "bidirectional_unaccepted",
            "unreachable",
            "evidence_stale",
        }
        assert "unreachable" not in " ".join(gate.STAGE_A_PREDICATE_IDS)

    def test_archive_is_not_claimed(self, report: Mapping[str, Any]) -> None:
        archive = report["stage_d"]["archive"]
        assert archive["archived"] is False
        assert archive["index_updated"] is False
        assert archive["what_archive_needs"]


# ════════════════════════════════════════════════════════════════════════════
# §8 上游产物零改动 + 禁止宣称
# ════════════════════════════════════════════════════════════════════════════


class TestUpstreamArtifactsAreUntouched:
    def test_recorded_digests_match_the_files_on_disk(self, gate: Any, report: Mapping[str, Any]) -> None:
        for rel_path, digest in report["upstream_artifacts_untouched"]["digests"].items():
            assert gate.sha256_file(REPO / rel_path) == digest, f"{rel_path} 已被改动"

    def test_gate_never_writes_to_an_upstream_report(self, gate: Any) -> None:
        """AST：写盘目标只有 OUTPUT_PATH，上游六份报告不在其中。"""
        facts = gate._self_ast_write_targets()
        assert facts["write_call_targets"] in ([], ["OUTPUT_PATH"])
        assert gate.OUTPUT_PATH not in gate.UPSTREAM_REPORTS

    def test_no_forbidden_claim_keys_in_the_report(self, report: Mapping[str, Any]) -> None:
        assert report["verdict"]["forbidden_record_keys_found"] == []
        assert report["verdict"]["structural_errors"] == []
        assert report["verdict"]["legacy_delete_gate_released"] is False

    def test_verdict_really_catches_an_ever_red_gate(self, gate: Any, report: Mapping[str, Any]) -> None:
        """喂一份「恒红门」的合成报告：verdict 必须把它记成结构错误。

        首版只断言「今天结构错误为 0」，被「删掉恒红门那条检查」的变异绕过（实测 GREEN）——
        今天门本来就能变绿，那条分支从不触发。判据必须能在**违规输入**上触发。
        """
        fake = copy.deepcopy(dict(report))
        fake.pop("verdict", None)
        fake["counterfactual_arms"]["gate_can_go_green"] = False
        verdict = gate.build_verdict(fake)
        assert any("恒红" in line for line in verdict["structural_errors"]), (
            f"恒红门没有被 verdict 抓出来：{verdict['structural_errors']}"
        )

        fake2 = copy.deepcopy(dict(report))
        fake2.pop("verdict", None)
        fake2["counterfactual_arms"]["every_predicate_alone_can_turn_it_red"] = False
        verdict2 = gate.build_verdict(fake2)
        assert any("死判据" in line for line in verdict2["structural_errors"])

        clean = copy.deepcopy(dict(report))
        clean.pop("verdict", None)
        assert gate.build_verdict(clean)["structural_errors"] == [], (
            "干净输入上也报结构错误 ⇒ 判据恒假"
        )

    def test_report_does_not_claim_any_real_oo_probe_passed(self, report: Mapping[str, Any]) -> None:
        text = json.dumps(report, ensure_ascii=False)
        for claim in ("probe 已通过", "全部通过", "scenarios passed"):
            assert claim not in text or "不得宣称" in text, f"报告里出现可疑宣称: {claim}"
        assert report["required_scenario_execution"]["executed_rows_recomputed"] == 0


# ════════════════════════════════════════════════════════════════════════════
# §9 落位、声明与守卫自身的位置
# ════════════════════════════════════════════════════════════════════════════


class TestDeclarationsAndPlacement:
    def test_declared_properties_match_tasks_md_and_design_md(self, gate: Any) -> None:
        declarations = gate.task_declarations()
        assert declarations["properties_match"] is True
        titles = gate.design_property_titles()
        assert sorted(int(k) for k in titles) == sorted(gate.DECLARED_PROPERTIES)
        for number, title in titles.items():
            assert title.strip(), f"Property {number} 在 design.md 里没有标题"

    def test_every_declared_property_has_a_landing_and_owner(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        properties = report["properties"]
        assert properties["all_declared_have_landing"] is True
        assert properties["every_unverified_has_owner"] is True
        assert properties["missing_landings"] == []
        assert properties["extra_landings"] == []
        for number, row in properties["rows"].items():
            assert row["tier"] in properties["tier_vocabulary"], number

    def test_property_tier_vocabulary_rejects_free_text(self, gate: Any) -> None:
        """喂一个自由文本档位：必须抛。

        首版只断言「今天的档位都合规」，被「把词表校验改成 `if False`」那条变异绕过（实测
        GREEN）—— 全部合规时校验有没有都一样。自由文本充当验证结论是本 spec 反复实测的形态。
        """
        for tier in gate.PROPERTY_TIERS:
            assert gate.assert_property_tier(tier) == tier
        for bogus in ("已覆盖", "passed", "verified", ""):
            with pytest.raises(gate.Task72GateError):
                gate.assert_property_tier(bogus)

    def test_sub_bullets_match_the_four_stages(self, gate: Any) -> None:
        declarations = gate.task_declarations()
        assert declarations["sub_bullet_count_declared"] == 4
        assert set(gate.SUB_BULLETS) == {"1", "2", "3", "4"}

    def test_guard_is_outside_the_upstream_census_directory(self, report: Mapping[str, Any]) -> None:
        placement = report["upstream_lock_impact"]["guard_dir_is_outside_upstream_census_dirs"]
        assert placement["outside"] is True
        assert Path(GUARD_REL).parent.name != Path(placement["upstream_census_dir"]).name
        assert (REPO / GUARD_REL).is_file()

    def test_upstream_lock_impact_is_recorded_not_worked_around(
        self, report: Mapping[str, Any]
    ) -> None:
        impact = report["upstream_lock_impact"]
        assert impact["known_defect_id"] == "BP-71-8"
        assert impact["known_defect_owner_task"] == "70"
        assert impact["task70_scanned_test_files_live"] > (
            impact["task70_scanned_test_files_on_disk"] or 0
        ), "全树 test 计数没有增加 ⇒ 本门守卫没被算进去，那条影响的登记就是空话"

    def test_mutation_script_exists_with_four_state_vocabulary(self, report: Mapping[str, Any]) -> None:
        machine = report["mutation_state_machine"]
        assert machine["mutation_script_present"] is True
        assert machine["state_vocabulary"] == ["RED", "GREEN", "ANCHOR-MISS", "WRONG-TEST"]
        assert machine["script_has_check_anchors"] is True
        assert machine["script_reads_and_writes_bytes"] is True
        assert machine["script_collects_errors_too"] is True

    def test_blocking_points_use_task_scoped_ids_with_owners(self, report: Mapping[str, Any]) -> None:
        points = report["blocking_points"]
        assert points, "阻塞清册为空 —— Stage A 红却没有可交办的条目"
        for row in points:
            assert re.fullmatch(r"BP-72-\d+", str(row["id"])), f"{row['id']} 不是 task-scoped id"
            assert str(row["owner_task"]).strip()
            assert str(row["why_not_fixed_here"]).strip()
            assert row["measured"], f"{row['id']} 没有实测值"

    def test_artifact_git_status_distinguishes_missing_from_clean(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """四个产物都在盘上；并且**喂一条不存在的路径**证明 `missing-on-disk` 真的能出现。

        首版只查现有四条，被「删掉存在性预检」那条变异绕过（实测 GREEN）—— 四条都存在时预检
        有没有都一样。而这条预检正是「产物还没写出来 vs 已跟踪且干净」两个状态的唯一分界。
        """
        status = report["artifact_git_status"]
        assert set(status) == {GATE_REL, REPORT_REL, GUARD_REL, MUTATE_REL}
        for path, state in status.items():
            assert state != "missing-on-disk", f"{path} 还没写出来"

        probed = gate.git_porcelain(["backend/data/__task72_definitely_missing__.json"])
        assert probed["backend/data/__task72_definitely_missing__.json"] == "missing-on-disk", (
            "不存在的路径被报成已跟踪且干净 —— 挂进 CI 的 job 在干净 checkout 下必挂而报告里"
            "看不出来"
        )

    def test_radiation_surface_includes_this_guard(self, report: Mapping[str, Any]) -> None:
        surface = report["radiation_surface"]
        assert surface["own_guard_included"] is True
        assert surface["referencing_test_file_count"] >= 1


class TestForwardRecompute:
    def test_all_pure_predicate_cases_agree(self, gate: Any) -> None:
        forward = gate.build_forward_recompute()
        assert forward["all_agree"] is True, forward["disagreeing_cases"]
        assert forward["has_positive_case"] is True
        assert forward["row_count"] >= 14

    def test_gate_write_and_check_are_idempotent(self) -> None:
        """真跑一次 `--check` 子进程：门必须在不写盘的情况下自证新鲜。"""
        proc = subprocess.run(
            [sys.executable, GATE_REL, "--check"],
            cwd=REPO,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=900,
            check=False,
        )
        assert proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")
