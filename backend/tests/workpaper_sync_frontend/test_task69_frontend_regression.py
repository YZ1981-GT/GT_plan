"""Task 69 前端独立回归门的**守卫**。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 7 Task 69

═══ 守卫与门的分工 ═══

* **门**（`backend/scripts/check/check_task69_frontend_independent_regression.py`）现算全部
  结论、真跑前端判据面、并把报告逐字节锁死。
* **本守卫**把「门有没有偷工」变成可断言的事实：正文声明双向锁死、11 条 Property 逐条有
  落点与档位、五条立即失败各有独立判据、行为侧结论必须来自**真实执行**（而不是「文件里
  有这个字符串」）、反事实臂与正向重算两者都在、两个验证档位没有被压成一句话。

═══ 为什么本文件不在 `backend/tests/workpaper_sync/` 里 ═══

上游后端独立回归（Wave 7 前一条）的逐字节锁冻结了**两样**东西，本文件都会撞：

1. **辐射面**（按「测试文件里有没有出现被验单元的模块路径字面量」现算）。故本文件刻意
   **不 import 任何生产模块**、也**不写那个包路径字面量** —— 写一个就会被拉进它的清册并
   改掉它的摘要。本守卫只读 JSON 报告与两个脚本的源码（走 AST）。
2. **目录普查**（`in_dir_but_out_of_surface` = 那个目录里**不**引用被验单元的测试文件清单）。
   这一条无法靠改写引用形式规避 —— 只要文件在那个目录里，清单就变长。故本文件放在
   `backend/tests/workpaper_sync_frontend/`。

本轮实测的完整因果链（每段都真跑上游守卫取证）：①放在普查目录 + 带包路径字面量 ⇒ 上游
3 红；②去掉字面量 ⇒ 2 条转绿、剩 1 条纯目录成员红；③移出普查目录 ⇒ 上游全绿。
该脆弱性登记为 **BP-69-6**（owner 68/72 —— Tasks 70/71/72 还要往那个目录加测试文件）。
位置本身是判据：见 `TestGuardPlacementIsRecomputedNotAsserted`（门侧现算，不是注释）。
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import json
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import pytest

REPO = Path(__file__).resolve().parents[3]
REPORT_PATH = REPO / "backend" / "data" / "workpaper_sync_task69_frontend_regression.json"
GATE_PATH = (
    REPO / "backend" / "scripts" / "check" / "check_task69_frontend_independent_regression.py"
)
MUTATION_PATH = (
    REPO / "backend" / "scripts" / "diagnose" / "mutate_task69_frontend_regression_guards.py"
)
GUARD_SPEC_PATH = (
    REPO
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "sync"
    / "__tests__"
    / "task69IndependentRegression.spec.ts"
)

DECLARED_PROPERTIES = (8, 11, 12, 13, 14, 15, 35, 46, 47, 48, 58)
IMMEDIATE_FAILURE_IDS = (
    "nonexistent_prop_or_expose",
    "editor_fetches_its_own_config",
    "normal_shell_fakes_application_early",
    "three_entities_faked_before_claim",
    "fail_open_success_text",
)
#: 教训 16：禁令/名单类判据必须断言「包含那个真实目标」。这五个 subject 是本门真实登记的
#: 阻塞点，只断言「BP 非空且 id 合规」会被改名/换主题绕过。
REQUIRED_BP_SUBJECTS = (
    "replacement_surface_unreachable_from_production_hosts",
    "legacy_mode_key_forms_outside_migration_regex",
    "refresh_required_reopen_has_no_runtime_producer",
    "incoming_durable_event_cannot_carry_incoming_artifact_digest",
    "no_real_browser_in_this_gate",
)
#: 本门实测不被统一迁移正则覆盖的真实键形态（同上：必须断言包含真实目标）。
REQUIRED_UNCOVERED_LITERALS = (
    "f4-ap-mode:",
    "g7-equity-method-mode-",
    "g7-sub-mode-",
    "l1-dual-mode-",
    "l2-dual-mode-",
    "l3-dual-mode-",
    "n3-dual-mode",
)


@lru_cache(maxsize=1)
def report() -> dict[str, Any]:
    if not REPORT_PATH.exists():
        pytest.fail(f"缺少 {REPORT_PATH.name} —— 先跑门的 --write --run-vitest")
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def gate_check() -> subprocess.CompletedProcess[str]:
    """真跑一次门的 `--check`（现算 + 逐字节比对）。进程内缓存：它要扫七千多个前端文件。"""
    return subprocess.run(
        [sys.executable, str(GATE_PATH), "--check"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=1800,
    )


@lru_cache(maxsize=1)
def gate_ast() -> ast.Module:
    return ast.parse(GATE_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def gate_module() -> Any:
    """按文件路径加载门模块（它是脚本、不是包成员），只为**调用它的纯函数**做合成输入重算。

    🔴 为什么必须这样做：门里有几条判据落在**当前世界走不到的分支**上（产物齐全 ⇒ 永不
    进入「缺失」分支；BP id 全合规 ⇒ 校验永不触发）。这类分支被短路掉时，只读磁盘记录的
    判据一律全绿 —— 本轮变异实测就抓到 3 条 GREEN。修法不是删变异，而是用**合成输入**把
    那些分支真的走一遍（教训 5：对照组必须先过；教训 15：反事实抓不到恒真，要正向重算）。
    """
    spec = importlib.util.spec_from_file_location("task69_gate_under_test", GATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["task69_gate_under_test"] = module
    spec.loader.exec_module(module)
    return module


def verdict_of(mutate: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    """深拷贝真实报告 → 按 `mutate` 改一处 → 让门的判定函数**现算**一遍。"""
    payload = copy.deepcopy(report())
    mutate(payload)
    return gate_module().build_verdict(payload)


def invariants() -> list[dict[str, Any]]:
    return report()["invariants"]


# ════════════════════════════════════════════════════════════════════════════


class TestGateIsInSyncWithTheTaskText:
    """正文声明与门锁定的常量双向锁死（少一条 / 多一条 / 改名都必须红）。"""

    def test_the_eleven_properties_match_the_task_text(self) -> None:
        declarations = report()["task_declarations"]
        assert declarations["properties_in_task_text"] == sorted(DECLARED_PROPERTIES)
        assert declarations["declared_properties"] == sorted(DECLARED_PROPERTIES)
        assert declarations["properties_match"] is True

    def test_the_requirement_list_is_read_from_the_task_text(self) -> None:
        declarations = report()["task_declarations"]
        requirements = declarations["requirements_in_task_text"]
        assert declarations["requirement_count"] == len(requirements)
        assert declarations["requirement_count"] >= 18
        # 正文点名的几条必须在内（只断言「非空」会被改成任意一条蒙过去）
        for needed in ("3.2", "3.7", "4.1", "5.8", "8.1", "11.2", "11.5", "11.12", "14.8"):
            assert needed in requirements, needed

    def test_the_sub_bullet_count_matches(self) -> None:
        declarations = report()["task_declarations"]
        assert declarations["sub_bullet_count_declared"] == 4
        assert declarations["sub_bullet_count_match"] is True

    def test_every_declared_property_has_a_design_title(self) -> None:
        titles = report()["design_property_titles"]
        for number in DECLARED_PROPERTIES:
            assert str(number) in titles, number
            assert titles[str(number)].strip() != ""


class TestReportIsFreshAndByteLocked:
    """报告必须是现算的：`--check` 现算并与磁盘逐字节比对。"""

    def test_gate_check_passes(self) -> None:
        proc = gate_check()
        assert proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")

    def test_gate_check_and_write_are_mutually_exclusive_and_required(self) -> None:
        # 两个都不给 ⇒ argparse 必须拒绝（互斥必选）
        none_given = subprocess.run(
            [sys.executable, str(GATE_PATH)],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        assert none_given.returncode != 0
        both_given = subprocess.run(
            [sys.executable, str(GATE_PATH), "--check", "--write"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        assert both_given.returncode != 0

    def test_verdict_is_passed_with_no_blockers(self) -> None:
        verdict = report()["verdict"]
        assert verdict["blockers"] == []
        assert verdict["result"] == "passed"

    def test_report_excludes_wallclock_so_the_byte_lock_can_hold(self) -> None:
        run = report()["vitest_run"]
        assert run.get("wallclock_excluded") is True
        # 报告里不得出现任何看起来像墙钟耗时的键（它每轮都变 ⇒ 锁等于不存在）
        blob = json.dumps(report(), ensure_ascii=False)
        for forbidden in ('"elapsed_seconds"', '"startTime"', '"duration_ms"'):
            assert forbidden not in blob, forbidden


class TestBehaviourSideIsRealExecution:
    """行为侧结论必须来自真实执行的前端判据面，且每条不变量的目标测试唯一命中并通过。"""

    def test_vitest_really_ran_and_matched_suites(self) -> None:
        run = report()["vitest_run"]
        assert run["executed"] is True
        assert run["matched_zero_suites"] is False
        assert run["suite_total"] > 0
        assert run["test_failed"] == 0
        assert run["test_passed"] == run["test_total"]
        assert run["test_total"] >= len(invariants())

    def test_every_invariant_has_a_uniquely_located_passing_test(self) -> None:
        broken: list[str] = []
        for row in invariants():
            behaviour = row["behaviour_side"]
            if not (behaviour["found"] and behaviour["unique"] and behaviour["passed"]):
                broken.append(f"{row['id']}: {behaviour}")
        assert broken == [], broken

    def test_the_guard_spec_is_the_only_behaviour_source_and_is_in_the_radiation_surface(
        self,
    ) -> None:
        surface = report()["radiation_surface"]
        assert surface["own_guard_included"] is True
        assert surface["own_guard_path"] in surface["spec_files"]
        assert surface["spec_file_count"] >= 18
        # 辐射面是现算的：摘要必须与清单一致
        assert surface["digest"]

    def test_all_thirty_three_invariants_pass(self) -> None:
        counts = report()["invariant_counts"]
        assert counts["total"] == len(invariants())
        assert counts["passed"] == counts["total"]
        assert counts["total"] >= 33
        # 三个内容子条目各自有落点（某一条为 0 = 正文那条没人验）
        assert set(counts["by_sub_bullet"]) == {"1", "2", "3"}
        for bullet, count in counts["by_sub_bullet"].items():
            assert count > 0, bullet

    def test_logic_recompute_exists_where_it_can_and_is_honest_where_it_cannot(self) -> None:
        counts = report()["invariant_counts"]
        # 至少七条配了逻辑级现算（教训 17）；其余显式标 behaviour_only 并写清理由
        assert counts["with_logic_recompute"] >= 7
        for row in invariants():
            logic = row["logic_side"]
            assert logic["state"] in {"recomputed", "behaviour_only"}
            if logic["state"] == "behaviour_only":
                assert logic["why"].strip() != ""
            else:
                assert logic["passed"] is True
                assert logic["recomputed_from"].strip() != ""


class TestDomNetworkOrderIsJudgedNotAsserted:
    """DOM/network 顺序必须是**判据**（能抓顺序交换），不是「三件事都发生过」。"""

    def test_four_chains_are_judged_on_real_traces(self) -> None:
        orders = report()["dom_network_order"]
        assert orders["chain_count"] == 4
        scenarios = {row["scenario"] for row in orders["chains"]}
        assert scenarios == {
            "descriptor_open",
            "recovery_claim",
            "recovery_download_only",
            "crash_recovery",
        }
        for row in orders["chains"]:
            assert row["trace_present"] is True, row["scenario"]
            assert row["ok"] is True, row
            assert row["verdict"]["missing_markers"] == []
            assert row["verdict"]["order_violations"] == []

    def test_descriptor_chain_really_is_mount_then_ready_then_confirm(self) -> None:
        row = next(
            r for r in report()["dom_network_order"]["chains"] if r["scenario"] == "descriptor_open"
        )
        positions = row["verdict"]["positions"]
        assert positions["editor:doc-editor-constructed"] < positions["emit:ready"]
        assert positions["emit:ready"] < positions["net:confirm_descriptor"]
        assert positions["net:materialize"] < positions["editor:doc-editor-constructed"]

    def test_every_adjacent_swap_flips_the_judgement_to_red(self) -> None:
        orders = report()["dom_network_order"]
        assert orders["all_arms_flip"] is True
        for row in orders["chains"]:
            assert row["counterfactual_arms"], row["scenario"]
            for arm in row["counterfactual_arms"]:
                assert arm["flips_to_red"] is True, (row["scenario"], arm)

    def test_forward_recompute_accepts_correct_and_rejects_missing(self) -> None:
        orders = report()["dom_network_order"]
        assert orders["forward_recompute_ok"] is True
        for row in orders["chains"]:
            assert row["forward_recompute_accepts_correct_order"] is True
            assert row["forward_recompute_rejects_missing_marker"] is True


class TestThreeEntityFactsComeFromTheObservedNetwork:
    """三实体结论必须落在前端观测到的 network 序列上（不是读后端库）。"""

    def test_claim_has_zero_entity_creating_calls_before_it(self) -> None:
        facts = report()["three_entity_facts"]["claim"]
        assert facts["trace_present"] is True
        assert facts["claim_call_index"] >= 0
        assert facts["entity_creating_calls_before_claim"] == []
        assert facts["three_entities_zero_before_claim"] is True
        assert facts["operation_probe_after_claim"] is True

    def test_download_only_creates_nothing(self) -> None:
        facts = report()["three_entity_facts"]["download_only"]
        assert facts["trace_present"] is True
        assert facts["entity_creating_calls_anywhere"] == []
        assert facts["calls_after_terminate"] == []
        assert facts["three_entities_zero"] is True

    def test_crash_recovery_creates_nothing_and_emits_the_case(self) -> None:
        facts = report()["three_entity_facts"]["crash"]
        assert facts["trace_present"] is True
        assert facts["recovery_case_emitted"] is True
        assert facts["entity_creating_calls"] == []
        assert facts["three_entities_zero"] is True

    def test_injecting_one_forcesave_call_flips_all_three_conclusions(self) -> None:
        facts = report()["three_entity_facts"]
        assert facts["all_arms_flip_to_red"] is True
        arms = {arm["scenario"]: arm for arm in facts["counterfactual_arms"]}
        assert set(arms) == {"claim", "download_only", "crash"}
        for scenario, arm in arms.items():
            assert arm["injected"] is True, scenario
            assert arm["flips_to_red"] is True, scenario


class TestImmediateFailuresEachHaveTheirOwnJudgement:
    """正文第 3 子条目逐字五条，每条各有独立打红判据，且判据是真实执行。"""

    def test_five_items_are_declared_and_each_has_at_least_one_invariant(self) -> None:
        immediate = report()["immediate_failures"]
        assert immediate["declared_count"] == 5
        assert immediate["without_judgement"] == []
        ids = {row["id"] for row in immediate["rows"]}
        assert ids == set(IMMEDIATE_FAILURE_IDS)
        for row in immediate["rows"]:
            assert row["invariant_count"] >= 1, row["id"]
            assert row["passed"] is True, row["id"]

    def test_each_item_is_judged_by_real_execution_not_by_string_existence(self) -> None:
        by_failure = {
            row["immediate_failure"]: row
            for row in invariants()
            if row.get("immediate_failure")
        }
        assert set(by_failure) == set(IMMEDIATE_FAILURE_IDS)
        statuses = report()["vitest_run"]["test_statuses"]
        for failure_id, row in by_failure.items():
            behaviour = row["behaviour_side"]
            assert behaviour["unique"] is True, failure_id
            assert behaviour["passed"] is True, failure_id
            # 目标测试必须真的在执行结果里（改名 / 删掉即红）
            assert behaviour["test"] in statuses, failure_id
            assert statuses[behaviour["test"]] == "passed", failure_id


class TestTwoVerificationTiersAreKeptApart:
    """「组件级独立挂载已验」与「生产宿主链路已验」必须是两个不同档位。"""

    def test_component_level_mount_is_verified(self) -> None:
        tiers = report()["verification_tiers"]
        assert tiers["component_level_mount"]["state"] == "verified"

    def test_production_host_chain_is_explicitly_not_verified(self) -> None:
        tiers = report()["verification_tiers"]["production_host_chain"]
        assert tiers["state"] == "not_verified_here"
        assert tiers["editor_host_reachable"] is False
        assert tiers["bridge_reachable"] is False
        assert tiers["blocking_point"] == "BP-69-1"
        assert tiers["owner_of_remainder"] != "69"

    def test_verdict_honest_scope_does_not_overclaim(self) -> None:
        scope = report()["verdict"]["honest_scope"]
        assert scope["component_level_mount_verified"] is True
        assert scope["production_host_chain_verified"] is False
        assert scope["real_browser"] is False
        assert scope["real_onlyoffice"] is False

    def test_reachability_semantics_are_stated_and_both_kinds_reported(self) -> None:
        reach = report()["replacement_reachability"]
        assert reach["surface_module_count"] >= 22
        assert reach["unreachable_count"] >= 19
        assert reach["reachability_semantics"].startswith("transitive")
        # 两个口径的差集必须显式列出（压成一个口径会让 19/22 说不清是哪个）
        assert reach["direct_unreachable_count"] >= reach["unreachable_count"]
        assert isinstance(reach["direct_only_gap"], list)

    def test_reachability_agrees_with_the_upstream_deletion_plan(self) -> None:
        cross = report()["reachability_cross_check"]
        assert cross["available"] is True
        assert cross["compared_module_count"] >= 20
        assert cross["disagreeing_modules"] == []
        assert cross["agrees"] is True
        assert cross["upstream_unreachable_count"] == cross["recomputed_unreachable_count"]


class TestPropertyLandingsAndTiers:
    """11 条 Property 逐条有落点 + 明确档位；partially 档必须点名 owner。"""

    def test_all_eleven_properties_have_landings(self) -> None:
        properties = report()["properties"]
        assert properties["structural_errors"] == []
        assert properties["declared_count"] == 11
        numbers = {row["number"] for row in properties["rows"]}
        assert numbers == set(DECLARED_PROPERTIES)
        for row in properties["rows"]:
            assert row["invariant_count"] >= 1, row["property"]
            assert row["all_landings_passed"] is True, row["property"]

    def test_every_property_has_an_explicit_tier(self) -> None:
        for row in report()["properties"]["rows"]:
            assert row["tier"] in {"independently_expressed", "partially_expressed"}, row

    def test_partially_expressed_properties_name_their_owner_and_what_is_missing(self) -> None:
        partial = [
            row for row in report()["properties"]["rows"] if row["tier"] == "partially_expressed"
        ]
        assert partial, "至少有一条 Property 只能部分表达（真浏览器/服务端 timeline 不在前端侧）"
        for row in partial:
            assert row["verified_here"].strip() != "", row["property"]
            assert row["not_verified_here"].strip() != "", row["property"]
            assert row["owner_of_remainder"] not in {"", "69"}, row["property"]

    def test_no_property_is_claimed_as_second_tier_self_certification(self) -> None:
        # 第二档（「跑了实现任务的测试所以算验过」）不许出现 —— 那正是正文禁止的自证形态
        tiers = {row["tier"] for row in report()["properties"]["rows"]}
        assert "independently_executed" not in tiers


class TestCounterfactualAndForwardRecomputeBothExist:
    """教训 13 + 15：两者都要，缺一即判据可能是重言或恒真。"""

    def test_counterfactual_arms_all_change_the_conclusion(self) -> None:
        arms = report()["counterfactual_arms"]
        assert arms["arm_count"] >= 5
        assert arms["all_arms_change_conclusion"] is True
        for arm in arms["arms"]:
            assert arm["conclusion_changed"] is True, arm["id"]

    def test_forward_recompute_covers_every_pure_judge(self) -> None:
        forward = report()["forward_recompute"]
        assert forward["row_count"] >= 5
        assert forward["all_passed"] is True
        ids = {row["id"] for row in forward["rows"]}
        for needed in (
            "judge_order_on_synthetic_inputs",
            "three_entity_verdict_on_synthetic_inputs",
            "migration_regex_on_synthetic_keys",
            "ts_literal_extractors_on_synthetic_source",
            "key_form_reconstruction_on_synthetic_source",
        ):
            assert needed in ids, needed

    def test_order_judge_rejects_reversed_and_missing_on_synthetic_inputs(self) -> None:
        row = next(
            r
            for r in report()["forward_recompute"]["rows"]
            if r["id"] == "judge_order_on_synthetic_inputs"
        )
        assert row["accepts_correct"] is True
        assert row["rejects_reversed"] is True
        assert row["rejects_missing"] is True


class TestLegacyKeyDenominatorIsRealAndDiscriminating:
    """AC 11.8 的迁移面分母必须现算、非空、且真的能区分覆盖与不覆盖。"""

    def test_denominator_is_not_empty(self) -> None:
        keys = report()["legacy_mode_key_coverage"]
        assert keys["mode_key_constant_total"] >= 80
        assert keys["dual_mode_constant_total"] >= 78
        assert keys["covered_count"] > 0
        # 分母为空会让覆盖率恒 100%（假绿第⑥源）
        assert keys["covered_count"] + keys["uncovered_count"] == keys["dual_mode_constant_total"]

    def test_the_regex_is_read_from_the_single_source(self) -> None:
        keys = report()["legacy_mode_key_coverage"]
        assert keys["migration_regex_source"] == "^([a-z0-9][a-z0-9-]*)-dual-mode:(.+)$"
        assert keys["migration_regex_read_from"].endswith("workpaperSyncModeStorage.ts")

    def test_the_uncovered_list_contains_the_real_targets(self) -> None:
        keys = report()["legacy_mode_key_coverage"]
        literals = {row["literal"] for row in keys["uncovered"]}
        for needed in REQUIRED_UNCOVERED_LITERALS:
            assert needed in literals, needed
        assert keys["uncovered_count"] >= len(REQUIRED_UNCOVERED_LITERALS)

    def test_bare_global_keys_are_reported_as_a_separate_worse_kind(self) -> None:
        bp = next(
            row
            for row in report()["blocking_points"]
            if row["subject"] == "legacy_mode_key_forms_outside_migration_regex"
        )
        kinds = bp["two_distinct_gap_kinds"]
        assert kinds["separator_or_naming_drift"], kinds
        assert kinds["bare_global_key_without_wp_segment"], kinds
        # 两类不许重叠（重叠说明分类判据没起作用）
        assert not set(kinds["separator_or_naming_drift"]) & set(
            kinds["bare_global_key_without_wp_segment"]
        )


class TestBridgeStateSurfaceIsRecomputed:
    """AC 11.2 / 11.3 的逻辑级复算：状态域与文案改一个字就变。"""

    def test_ac_11_2_nineteen_states_are_all_in_the_domain(self) -> None:
        bridge = report()["bridge_state_surface"]
        assert bridge["ac_11_2_required_count"] == 19
        assert bridge["ac_11_2_missing_from_domain"] == []
        assert bridge["state_count"] >= 19

    def test_every_state_has_a_distinct_chinese_text_and_none_says_sync_succeeded(self) -> None:
        bridge = report()["bridge_state_surface"]
        assert bridge["states_without_text"] == []
        assert bridge["duplicate_state_texts"] == []
        assert bridge["states_with_forbidden_success_text"] == []
        assert bridge["four_ac_11_3_texts_distinct"] is True

    def test_terminal_states_are_declared(self) -> None:
        bridge = report()["bridge_state_surface"]
        assert set(bridge["terminal_states"]) == {
            "duplicate",
            "recovery_download_only",
            "close_recovery_required",
        }


class TestBlockingPointsAreTaskScopedAndNameRealTargets:
    def test_every_bp_id_is_task_scoped(self) -> None:
        for row in report()["blocking_points"]:
            assert re.fullmatch(r"BP-69-\d+", str(row["id"])), row["id"]

    def test_the_five_real_subjects_are_registered(self) -> None:
        subjects = {row["subject"] for row in report()["blocking_points"]}
        for needed in REQUIRED_BP_SUBJECTS:
            assert needed in subjects, needed

    def test_every_bp_is_measured_and_has_an_owner(self) -> None:
        for row in report()["blocking_points"]:
            assert row.get("measured") is True, row["id"]
            assert str(row.get("owner_task", "")).strip() != "", row["id"]
            assert str(row.get("disposition", "")).strip() != "", row["id"]

    def test_the_unreachability_bp_is_forwarded_not_claimed_resolved(self) -> None:
        row = next(
            r
            for r in report()["blocking_points"]
            if r["subject"] == "replacement_surface_unreachable_from_production_hosts"
        )
        assert row["disposition"] == "reported_forward_unchanged"
        assert row["owner_task"] != "69"
        assert row["cross_check_with_upstream_deletion_plan"]["agrees"] is True


class TestNothingProductionWasTouched:
    """本门只新增判据面；发现的缺陷登记为 BP，不顺手修。"""

    def test_report_declares_zero_production_changes(self) -> None:
        touched = report()["production_code_touched"]
        assert touched["frontend_production_files"] == []
        assert touched["backend_production_files"] == []
        assert touched["migrations"] == []

    def test_gate_only_writes_its_own_output_file(self) -> None:
        """AST 判据：门里所有写盘调用的接收者只能是那个临时文件。"""
        writers: list[str] = []
        for node in ast.walk(gate_ast()):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in {"write_text", "write_bytes"}:
                writers.append(ast.unparse(func.value))
        assert writers, "门里一个写盘调用都没有 ⇒ --write 是空操作"
        assert set(writers) == {"tmp"}, writers

    def test_gate_replaces_only_the_declared_output_path(self) -> None:
        replaces: list[str] = []
        for node in ast.walk(gate_ast()):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "replace"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os"
            ):
                replaces.append(ast.unparse(node.args[1]))
        assert replaces == ["OUTPUT_PATH"], replaces

    def test_gate_has_no_database_import(self) -> None:
        imported: set[str] = set()
        for node in ast.walk(gate_ast()):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        for forbidden in ("asyncpg", "sqlalchemy", "psycopg2"):
            assert not any(name.startswith(forbidden) for name in imported), forbidden


class TestGuardSpecIsIndependentOfImplementationFixtures:
    """正文「不得由实现任务自证」：判据面不许 import 实现任务的夹具。"""

    def test_the_spec_exists(self) -> None:
        assert GUARD_SPEC_PATH.exists()

    def test_the_spec_does_not_import_the_implementation_harness(self) -> None:
        text = GUARD_SPEC_PATH.read_text(encoding="utf-8")
        specifiers = re.findall(r"""(?:from|import)\s+['"]([^'"]+)['"]""", text)
        assert specifiers, "取不到 import 说明符"
        for specifier in specifiers:
            assert "UiHarness" not in specifier, specifier
            assert "workpaperSyncUiHarness" not in specifier, specifier

    def test_the_spec_only_mocks_the_platform_http_surface(self) -> None:
        text = GUARD_SPEC_PATH.read_text(encoding="utf-8")
        mocked = re.findall(r"""vi\.mock\(\s*['"]([^'"]+)['"]""", text)
        assert mocked == ["@/utils/http"], mocked


class TestUpstreamByteLocksSurviveThisGate:
    """本门往 backend/data 写产物 ⇒ 必须证明上游两份报告的逐字节锁仍然过。"""

    def test_locks_were_rerun(self) -> None:
        locks = report()["upstream_lock_reruns"]
        assert locks["executed"] is True, "收尾必须用 --write --run-vitest 真跑一次上游锁"
        assert locks["all_passed"] is True, locks["results"]

    def test_both_upstream_locks_are_covered(self) -> None:
        locks = report()["upstream_lock_reruns"]
        names = set(locks["results"])
        assert len(names) == 2
        # 教训 16：名单类判据必须写死那个真实目标 —— 只断言「两条且名字里有某个词」会被
        # 换成任意两条测试蒙过去。这两个 basename 就是上游两份报告各自的逐字节锁守卫。
        #
        # 🔴 刻意用 basename 而**不是**被验包的路径字面量：上游后端独立回归按
        # 「测试文件里有没有出现该包的路径字面量」现算自己的辐射面，本文件里写一个就会被
        # 拉进它的清册、改掉它的摘要并让它的逐字节锁打红。本轮已实测该因果（写着那个
        # 字面量时上游 3 红：辐射面不可复算 / surface_size 不可复算 / 现算判定与磁盘不一致；
        # 改成 basename 形态后同一套上游守卫转绿），故此处的引用形式本身就是判据的一部分。
        basenames = {name.rsplit("/", 1)[-1] for name in names}
        assert basenames == {
            "test_task67_structural_pre_reconcile.py",
            "test_task68_backend_chain_regression.py",
        }, basenames
        for name, row in locks["results"].items():
            assert row["failed_count"] == 0, (name, row)
            assert row["passed_count"] > 0, (name, row)


class TestVerdictLogicFiresOnSyntheticCounterExamples:
    """门里那些**当前世界走不到**的判定分支，用合成输入逐条走一遍。

    只断言磁盘记录时，把这些分支整段短路掉也全绿（本轮变异实测 M10/M13/M14 三条 GREEN）。
    """

    def test_control_group_passes_first(self) -> None:
        """教训 5：对照组必须先过 —— 不动任何字段时判定仍是 passed。"""
        verdict = verdict_of(lambda payload: None)
        assert verdict["result"] == "passed", verdict["blockers"]

    def test_zero_matched_suites_becomes_a_blocker(self) -> None:
        """过滤器写错 ⇒ 0 个 suite ⇒ 行为侧结论无来源，必须是 blocker 而不是「全过了」。"""
        verdict = verdict_of(
            lambda payload: payload["vitest_run"].__setitem__("matched_zero_suites", True)
        )
        assert verdict["result"] == "failed"
        assert any("0 个 suite" in str(row) for row in verdict["blockers"]), verdict["blockers"]

    def test_a_globally_numbered_blocking_point_becomes_a_blocker(self) -> None:
        """全局 `BP-NN` 已被多个任务重复占用 ⇒ 混进来必须打红（不是只在注释里说一声）。"""

        def swap(payload: dict[str, Any]) -> None:
            payload["blocking_points"][0]["id"] = "BP-42"

        verdict = verdict_of(swap)
        assert verdict["result"] == "failed"
        assert any("BP-42" in str(row) for row in verdict["blockers"]), verdict["blockers"]

    def test_guard_moved_back_into_the_census_dir_becomes_a_blocker(self) -> None:
        verdict = verdict_of(
            lambda payload: payload["guard_placement"].__setitem__("outside_census_dir", False)
        )
        assert verdict["result"] == "failed"
        assert any("普查目录" in str(row) for row in verdict["blockers"]), verdict["blockers"]

    def test_a_trigger_literal_in_the_guard_becomes_a_blocker(self) -> None:
        verdict = verdict_of(
            lambda payload: payload["guard_placement"].__setitem__(
                "trigger_literal_hit_lines", [625]
            )
        )
        assert verdict["result"] == "failed"

    def test_an_upstream_lock_failure_becomes_a_blocker(self) -> None:
        verdict = verdict_of(
            lambda payload: payload["upstream_lock_reruns"].__setitem__("all_passed", False)
        )
        assert verdict["result"] == "failed"

    def test_absent_artifact_is_reported_as_missing_not_as_tracked_clean(self) -> None:
        """`git status --porcelain -- <不存在的路径>` 输出为空，与「已跟踪且干净」逐字节相同。

        产物齐全时这条分支永远走不到 ⇒ 把它改成 `tracked_clean` 时磁盘记录一字不变。
        故必须用一个**确定不存在**的路径正向重算一次。
        """
        probe = "backend/data/__task69_absent_probe_never_created__.json"
        assert not (REPO / probe).exists(), "探针路径居然存在 ⇒ 这条判据失去意义"
        assert gate_module().git_porcelain([probe]) == {probe: "missing"}

    def test_an_existing_untracked_artifact_is_not_reported_as_clean(self) -> None:
        """对照组的另一半：真实存在且未入库的产物必须报 `??`，不能也报 missing/clean。"""
        states = gate_module().git_porcelain([GATE_PATH.relative_to(REPO).as_posix()])
        assert set(states.values()) <= {"??", "A", "AM", "M", "MM", "tracked_clean"}
        assert "missing" not in states.values()


class TestGuardPlacementIsRecomputedNotAsserted:
    """本门守卫的**放置位置**本身是判据 —— 挪回上游普查目录 / 写回触发字面量都必须红。"""

    def test_placement_is_recomputed_and_passes(self) -> None:
        placement = report()["guard_placement"]
        assert placement["guard_test_exists"] is True
        assert placement["outside_census_dir"] is True
        assert placement["trigger_literal_hit_lines"] == []
        assert placement["passed"] is True

    def test_this_file_is_the_declared_guard(self) -> None:
        """现算：报告里声明的守卫路径必须就是本文件（挪了文件却忘改声明 ⇒ 红）。"""
        placement = report()["guard_placement"]
        assert placement["guard_test"] == Path(__file__).resolve().relative_to(REPO).as_posix()

    def test_the_census_membership_rule_is_a_real_function_not_a_constant(self) -> None:
        """两臂都断言：写死 `return True` 时第二臂立刻打红（教训 15 的正向重算）。"""
        outside = gate_module().outside_census_dir
        assert outside("backend/tests/workpaper_sync_frontend/test_probe.py") is True
        assert outside("backend/tests/workpaper_sync/test_probe.py") is False

    def test_the_upstream_pattern_is_read_from_the_upstream_gate_not_copied(self) -> None:
        placement = report()["guard_placement"]
        assert placement["upstream_pattern_found"] is True
        assert placement["upstream_pattern_read_from"].endswith(".py")
        # 模式字面量必须非空且真的是个可编译正则（抄成空串会让「零命中」恒成立）
        assert placement["upstream_pattern_literal"].strip() != ""
        re.compile(placement["upstream_pattern_literal"])

    def test_the_census_fragility_is_registered_as_a_blocking_point(self) -> None:
        row = next(
            r
            for r in report()["blocking_points"]
            if r["subject"] == "upstream_byte_lock_freezes_a_test_directory_census"
        )
        assert row["id"] == "BP-69-6"
        assert row["disposition"] == "reported_not_fixed"
        assert row["owner_task"] != "69"
        assert report()["guard_placement"]["registered_as"] == "BP-69-6"


class TestFrontendBaselineWasMeasuredHere:
    """旧的「887 passed」不可直接引用 —— 全套基线必须由本门实测并落进产物。"""

    def test_baseline_really_ran_the_whole_suite(self) -> None:
        baseline = report()["frontend_baseline"]
        assert baseline["executed"] is True, "全套前端基线必须真跑一次（--write --run-vitest）"
        assert baseline["measured_by_this_gate"] is True
        # 全套必须严格大于辐射面（等于说明过滤器没去掉 ⇒ 跑的不是全套）
        assert int(baseline["test_total"]) > int(report()["vitest_run"]["test_total"])
        assert int(baseline["suite_total"]) > int(report()["vitest_run"]["suite_total"])

    def test_baseline_is_internally_consistent(self) -> None:
        baseline = report()["frontend_baseline"]
        assert int(baseline["test_failed"]) == len(baseline["failures"])
        assert int(baseline["test_passed"]) + int(baseline["test_failed"]) <= int(
            baseline["test_total"]
        )

    def test_our_own_judgement_surface_is_green_inside_the_full_run(self) -> None:
        """全套里**本门自己的判据面**必须 0 红；其余既存红不属本任务，只如实登记。"""
        baseline = report()["frontend_baseline"]
        own = GUARD_SPEC_PATH.name
        mine = [row for row in baseline["failures"] if row["suite"].endswith(own)]
        assert mine == [], mine

    def test_baseline_excludes_wallclock_so_the_byte_lock_can_hold(self) -> None:
        assert report()["frontend_baseline"]["wallclock_excluded"] is True

    def test_preexisting_reds_are_attributed_on_both_sides(self) -> None:
        """既存红必须有归因 + owner + 「为何不在本任务修」，且不许声称是本门弄红的。"""
        reds = report()["preexisting_reds"]
        for side in ("frontend", "backend"):
            row = reds[side]
            assert row["attribution"].strip() != "", side
            assert str(row["owner_task"]).strip() != "", side
            assert row["why_not_fixed_here"].strip() != "", side
        # 前端侧的逐条清单是现算记录，不是手抄 ⇒ 计数必须与 failures 列表一致
        baseline = report()["frontend_baseline"]
        assert reds["frontend_failed_count_in_record"] == len(baseline["failures"])
        assert reds["frontend_failed_suite_count_in_record"] == len(baseline["failed_suites"])

    def test_the_flaky_baseline_finding_is_registered(self) -> None:
        row = next(
            r
            for r in report()["blocking_points"]
            if r["subject"] == "frontend_full_suite_baseline_is_not_reproducible"
        )
        assert row["id"] == "BP-69-7"
        assert row["measured"] is True
        assert row["owner_task"] != "69"
        assert row["why_it_does_not_affect_this_gate"].strip() != ""


class TestArtifactsAreRecordedForCheckIn:
    """「spec 全绿」≠「产物已入库」：逐产物记 git 状态，缺文件必须显式为 missing。"""

    def test_all_five_artifacts_exist(self) -> None:
        status = report()["artifact_git_status"]
        assert len(status) == 5
        missing = [path for path, state in status.items() if state == "missing"]
        assert missing == [], missing

    def test_the_mutation_script_is_registered(self) -> None:
        status = report()["artifact_git_status"]
        assert any("mutate_task69" in path for path in status)
        assert MUTATION_PATH.exists()

    def test_untracked_artifacts_are_visible_in_the_report(self) -> None:
        status = report()["artifact_git_status"]
        # 只要求「如实记录」，不要求已入库（并发多会话下工作树长期不干净）
        for path, state in status.items():
            assert state in {"??", "A", "M", "AM", "MM", "tracked_clean"}, (path, state)


class TestOoScopeBoundaryIsExplicit:
    def test_no_real_onlyoffice_or_browser_is_claimed(self) -> None:
        boundary = report()["oo_scope_boundary"]
        assert boundary["runs_real_onlyoffice"] is False
        assert boundary["runs_real_browser"] is False
        assert boundary["port_3030_listening"] is False
        assert "jsdom" in boundary["test_environment"]

    def test_upstream_dom_denominator_is_consumed_by_key_not_wholesale(self) -> None:
        denominator = report()["upstream_dom_descriptor_denominators"]
        assert denominator["available"] is True
        assert denominator["consumed_keys"] == [
            "entries[].host_dom_landing",
            "entries[].descriptor_room_config",
        ]
        assert denominator["entry_total"] >= 186
        assert denominator["mount_total"] > denominator["entry_total"]
        assert denominator["how_this_gate_uses_it"].strip() != ""
