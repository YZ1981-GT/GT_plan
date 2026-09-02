# -*- coding: utf-8 -*-
"""任务 71 门的守卫。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 7
被守对象: backend/scripts/check/check_task71_mutation_capacity_recovery_gate.py
          backend/data/workpaper_sync_task71_mutation_capacity_recovery.json

═══ 为什么这个文件不在上游那个普查目录里 ═══

任务 68 的逐字节锁把 `backend/tests/<被验包>` 做成了**目录普查**：往里新增任何一个「不引用
被验生产单元」的测试文件都会打红它 1~3 条守卫，表象是「上游报告过期」（BP-69-6 实测，
任务 69 的规避法是自己开目录）。本门用 `backend/tests/workpaper_sync_chaos/`，并把
「不在普查目录」做成 :class:`TestGuardPlacement` 里的**现算**判据而不是注释。

═══ 为什么本文件里一条生产模块路径字面量都没有 ═══

BP-70-8：换目录只躲开目录普查；上游的**辐射面 digest** 扫 `backend/tests` 全树，凡出现被验
生产包模块路径的文件都会进它的锁 ⇒ 新增守卫必红 3 条。因此本文件里的生产模块**全部**经
`gate._production()` 取，需要 dotted name 的地方用 `__name__` 现算；并且有一条判据从上游门
源码**现读** pattern 做零命中自检（带反向自检防 pattern 解析失效）。

═══ 每条判据都配一条逻辑级现算 ═══

教训 17：只读磁盘产物的判据对实现侧改动天生不敏感。因此本文件里凡是断言报告里某个数字的
地方，都同时用**独立路径**把那个数字重算一遍（现跑门的函数、现算 tasks.md、现算 AST），
再与报告比对 —— 两侧来源不同，才不是自我比对。
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

import pytest

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

GATE_REL = "backend/scripts/check/check_task71_mutation_capacity_recovery_gate.py"
REPORT_REL = "backend/data/workpaper_sync_task71_mutation_capacity_recovery.json"
MUTATE_REL = "backend/scripts/diagnose/mutate_task71_chaos_guards.py"
GUARD_REL = "backend/tests/workpaper_sync_chaos/test_task71_chaos_gate.py"

GATE_PATH = REPO / GATE_REL
REPORT_PATH = REPO / REPORT_REL
UPSTREAM_GATE = REPO / "backend/scripts/check/check_task68_backend_chain_independent_regression.py"
TASKS_MD = REPO / ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/tasks.md"


def _load_gate() -> Any:
    """import 门模块（`sys.modules` 必须先注册，否则 `@dataclass` 会 AttributeError）。"""
    if "task71_gate" in sys.modules:
        return sys.modules["task71_gate"]
    spec = importlib.util.spec_from_file_location("task71_gate", GATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["task71_gate"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate() -> Any:
    return _load_gate()


@pytest.fixture(scope="module")
def prod(gate: Any) -> Mapping[str, Any]:
    """生产模块**经门自己的访问器**取得（`gate._production()`）。

    走门的访问器不是绕过判据：import 仍然真的发生，逐条判据一个没少；而且它顺带让
    「生产入口只有一处」这件事在守卫侧也成立 —— 守卫与门消费的是同一个访问器。
    """
    return gate._production()


@pytest.fixture(scope="module")
def report() -> Mapping[str, Any]:
    assert REPORT_PATH.is_file(), f"{REPORT_REL} 不存在 —— 先跑门的 --write"
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


# ════════════════════════════════════════════════════════════════════════════
# §1 报告新鲜且逐字节锁死
# ════════════════════════════════════════════════════════════════════════════


class TestReportIsFreshAndByteLocked:
    def test_gate_check_passes(self, gate: Any) -> None:
        """`--check` 必须逐字节一致。随机值（scratch hex / 临时目录名）与墙钟耗时已排除。"""
        assert gate.main(["--check"]) == 0, (
            f"现算结果与 {REPORT_REL} 不一致 —— 报告已过期或被手改"
        )

    def test_report_digest_is_self_consistent(self, gate: Any, report: Mapping[str, Any]) -> None:
        recomputed = gate.digest_of(
            gate.strip_volatile(
                {key: value for key, value in report.items() if key != "report_digest"}
            )
        )
        assert recomputed == report["report_digest"]

    def test_volatile_keys_are_only_random_and_wallclock(self, gate: Any) -> None:
        """排除名单里只能有随机值与墙钟耗时。

        🔴 `source_commit` 刻意**不**在名单里：它是「源码变了但证据没刷新」这条 stale 轴的
        唯一锁。把它排除掉会让门在源码漂移后仍然逐字节相等。
        """
        assert "source_commit" not in gate.VOLATILE_KEYS
        assert "report_digest" not in gate.VOLATILE_KEYS
        assert gate.VOLATILE_KEYS == frozenset(
            {
                "generated_at",
                "elapsed_seconds",
                "wallclock_seconds",
                "scratch_schema",
                "temp_artifact_root",
                "probe_elapsed_seconds",
            }
        )

    def test_cli_modes_are_mutually_exclusive_and_required(self, gate: Any) -> None:
        with pytest.raises(SystemExit):
            gate.main([])
        with pytest.raises(SystemExit):
            gate.main(["--check", "--write"])


# ════════════════════════════════════════════════════════════════════════════
# §2 body digest 归一化复选框（BP-70-6 的正向修复）
# ════════════════════════════════════════════════════════════════════════════


class TestTaskBodyDigestIgnoresCheckboxState:
    def test_checkbox_flip_does_not_change_body_digest(self, gate: Any) -> None:
        """把复选框在四个状态间翻牌，body digest 必须一字不变。

        这是 BP-70-6 的**正向**判据：任务 69 的门在这里失守（`- [-] 69.` → `- [x] 69.` 让它
        的逐字节锁必红，而正文零变化）。本条对四个合法状态各算一次。
        """
        original = TASKS_MD.read_text(encoding="utf-8")
        digests = {gate.task_body(): "as-is"}
        try:
            for marker in (" ", "x", "~", "-"):
                mutated = re.sub(
                    r"^(\s*-\s\[)[ x~\-](\]\s+71\.)",
                    rf"\g<1>{marker}\g<2>",
                    original,
                    count=1,
                    flags=re.M,
                )
                TASKS_MD.write_text(mutated, encoding="utf-8")
                digests[gate.task_body()] = marker
        finally:
            TASKS_MD.write_text(original, encoding="utf-8")
        assert len(digests) == 1, (
            f"复选框翻牌改变了 body digest（得到 {len(digests)} 个不同 digest）—— "
            "编排器一翻牌本门的锁就会假红，正是 BP-70-6 的形态"
        )

    def test_body_digest_still_reacts_to_real_text_change(self, gate: Any) -> None:
        """反向自检：正文**内容**变了 digest 必须变（否则归一化把锁归一化没了）。"""
        original = TASKS_MD.read_text(encoding="utf-8")
        baseline = gate.task_body()
        try:
            mutated = original.replace(
                "所有结果持久化并按 RED/GREEN/ANCHOR-MISS/WRONG-TEST判定",
                "所有结果持久化并按 RED/GREEN/ANCHOR-MISS/WRONG-TEST判定（守卫反向自检插入）",
                1,
            )
            assert mutated != original, "反向自检的锚点没命中 —— 判据本身失效"
            TASKS_MD.write_text(mutated, encoding="utf-8")
            assert gate.task_body() != baseline, (
                "正文内容变了但 body digest 没变 —— 归一化把整条锁抹掉了"
            )
        finally:
            TASKS_MD.write_text(original, encoding="utf-8")

    def test_report_records_normalization_and_declarations(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        decl = report["task_declarations"]
        assert decl["body_digest_checkbox_normalized"] is True
        assert decl["properties_match"] is True
        assert decl["sub_bullet_count_match"] is True
        live = gate.task_declarations()
        assert live["body_digest"] == decl["body_digest"]
        assert live["sub_bullet_count_in_task_text"] == decl["sub_bullet_count_declared"]

    def test_declared_properties_match_tasks_md(self, gate: Any) -> None:
        """独立现算 tasks.md 正文里的 Property 号并与门的常量比对。"""
        body = gate.task_body()
        in_text = sorted({int(m) for m in re.findall(r"Property (\d+)", body)})
        assert in_text == sorted(gate.DECLARED_PROPERTIES)
        assert len(in_text) == 24


# ════════════════════════════════════════════════════════════════════════════
# §3 变异分母：逐条点名 → 真实证据源（跨文件双向锁）
# ════════════════════════════════════════════════════════════════════════════


class TestMutationCoverageDenominator:
    def test_every_target_has_at_least_one_evidence_ref(self, gate: Any) -> None:
        """空 evidence 在构造时就必须抛（空集恒真是假绿第⑥源）。"""
        for target in gate.MUTATION_TARGETS:
            assert target.evidence, f"{target.target_id} 的 evidence 为空"
        with pytest.raises(gate.Task71GateError, match="没有任何证据源"):
            gate.MutationTarget("probe", 1, "probe", ())

    def test_evidence_kind_vocabulary_is_closed(self, gate: Any) -> None:
        """证据源前缀词表封闭；非法前缀必须在构造时抛。"""
        assert set(gate.EVIDENCE_KINDS) == {
            "t68_arm",
            "t68_endpoint",
            "t71_arm",
            "t71_facet",
            "guard_mutation",
            "unverifiable",
        }
        with pytest.raises(gate.Task71GateError, match="前缀非法"):
            gate.MutationTarget("probe", 1, "probe", ("documented:yes",))

    def test_all_six_mutation_sub_bullets_have_targets(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """正文六个变异子条目**每条**都要有目标（少一条即分母缩小）。"""
        by_bullet = report["mutation_coverage"]["targets_by_sub_bullet"]
        for bullet in ("1", "2", "3", "4", "5", "6"):
            assert int(by_bullet.get(bullet, 0)) > 0, f"子条目 {bullet} 没有任何变异目标"
        live = {str(t.sub_bullet) for t in gate.MUTATION_TARGETS}
        assert {"1", "2", "3", "4", "5", "6"} <= live

    def test_no_unresolved_or_disagreeing_evidence(self, report: Mapping[str, Any]) -> None:
        coverage = report["mutation_coverage"]
        assert coverage["unresolved_refs"] == [], (
            f"变异目标引用了不存在的证据源: {coverage['unresolved_refs'][:6]}"
        )
        assert coverage["disagreeing_refs"] == [], (
            f"引用的上游 arm 不成立: {coverage['disagreeing_refs'][:6]}"
        )
        assert coverage["target_count"] > 0, "变异目标为 0 —— 覆盖计数必须断言非空"

    def test_upstream_arm_refs_really_exist_in_task68_report(self, gate: Any) -> None:
        """跨文件双向锁：`t68_arm:` 必须在任务 68 报告里真的找到且 agrees。

        🔴 这是本门最强的一条判据来源：它不是「我写了一行说已覆盖」，而是「上游报告里那条
        arm 一旦消失或变 disagrees，本门立刻变红」。这里**现读**上游报告，不读本门产物。
        """
        upstream = json.loads(
            (REPO / "backend/data/workpaper_sync_task68_backend_chain_regression.json").read_text(
                encoding="utf-8"
            )
        )
        arms = {
            str(arm["arm_id"]): bool(arm.get("agrees"))
            for row in upstream.get("invariants") or []
            for arm in (row.get("behaviour_side") or {}).get("arms") or []
        }
        endpoints = {
            str(row.get("check_id")): bool(row.get("passed"))
            for row in upstream.get("endpoint_checks") or []
        }
        assert len(arms) >= 100, f"上游 arm 池只有 {len(arms)} 条 —— 前提已漂移"
        referenced_arms = {
            ref.split(":", 1)[1]
            for target in gate.MUTATION_TARGETS
            for ref in target.evidence
            if ref.startswith("t68_arm:")
        }
        referenced_endpoints = {
            ref.split(":", 1)[1]
            for target in gate.MUTATION_TARGETS
            for ref in target.evidence
            if ref.startswith("t68_endpoint:")
        }
        assert referenced_arms, "一条上游 arm 都没引用 —— 分母是空的"
        missing = sorted(referenced_arms - set(arms))
        assert not missing, f"引用了不存在的上游 arm: {missing}"
        not_agreeing = sorted(name for name in referenced_arms if not arms[name])
        assert not not_agreeing, f"引用的上游 arm 不成立: {not_agreeing}"
        missing_ep = sorted(referenced_endpoints - set(endpoints))
        assert not missing_ep, f"引用了不存在的上游端点检查: {missing_ep}"

    def test_resolver_really_reports_a_missing_or_disagreeing_upstream_arm(
        self, gate: Any, tmp_path: Any
    ) -> None:
        """反向自检：给解析器喂「缺失的 arm」与「disagrees 的 arm」，两条都必须被报出来。

        🔴 上一条判据自己重算了一遍上游报告，因此**对门的解析器改动天生不敏感**（教训 17）：
        把 `resolve_mutation_coverage` 里的 `unresolved` / `disagreeing` 分支短路掉，上一条
        仍然全绿（首轮变异实测 M01/M02 双 GREEN 的根因）。这里把上游报告换成合成的，并让
        目标表指向其中的 arm，逼门自己给结论。
        """
        synthetic = tmp_path / "synthetic_upstream.json"
        synthetic.write_text(
            json.dumps(
                {
                    "invariants": [
                        {
                            "check_id": "probe",
                            "behaviour_side": {
                                "arms": [
                                    {"arm_id": "t71_probe_ok", "expectation": "accepted",
                                     "agrees": True},
                                    {"arm_id": "t71_probe_bad", "expectation": "rejected",
                                     "agrees": False},
                                ]
                            },
                        }
                    ],
                    "endpoint_checks": [{"check_id": "probe_ep", "passed": True}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        planted_targets = (
            gate.MutationTarget("p_ok", 1, "对照组：存在且成立的 arm", ("t68_arm:t71_probe_ok",)),
            gate.MutationTarget("p_missing", 1, "缺失的 arm", ("t68_arm:t71_probe_absent",)),
            gate.MutationTarget("p_bad", 1, "存在但 disagrees 的 arm", ("t68_arm:t71_probe_bad",)),
        )
        original_targets = gate.MUTATION_TARGETS
        original_report = gate.T68_REPORT
        try:
            gate.MUTATION_TARGETS = planted_targets
            gate.T68_REPORT = synthetic
            live = gate.resolve_mutation_coverage(
                behaviour={"observations": {}}, facets={}
            )
        finally:
            gate.MUTATION_TARGETS = original_targets
            gate.T68_REPORT = original_report
        assert live["unresolved_refs"] == ["p_missing -> t68_arm:t71_probe_absent"], (
            "缺失的上游 arm 没有被报进 unresolved_refs —— 跨文件双向锁失效"
        )
        assert live["disagreeing_refs"] == ["p_bad -> t68_arm:t71_probe_bad"], (
            "disagrees 的上游 arm 没有被报进 disagreeing_refs —— 「引用的证据不成立」测不出来"
        )
        # 对照组必须先过：合法 arm 不得被误报（否则上面两条可能只是「什么都报」）
        assert "p_ok" not in " ".join(live["unresolved_refs"] + live["disagreeing_refs"])

    def test_own_arm_refs_resolve_to_declared_arms(self, gate: Any) -> None:
        """`t71_arm:` 必须指向本门 `OWN_ARMS` 里声明过的臂（防写错名字静静不解析）。"""
        declared = {arm.arm_id for arm in gate.OWN_ARMS}
        referenced = {
            ref.split(":", 1)[1]
            for target in gate.MUTATION_TARGETS
            for ref in target.evidence
            if ref.startswith("t71_arm:")
        }
        assert referenced, "一条本门 arm 都没引用"
        assert referenced <= declared, f"引用了未声明的本门 arm: {sorted(referenced - declared)}"

    def test_guard_mutation_refs_resolve_to_real_mutation_ids(self, gate: Any) -> None:
        """`guard_mutation:` 必须指向变异脚本里真实存在的变异号（现读脚本源码）。"""
        ids = set(gate.guard_mutation_ids())
        assert ids, "变异脚本里读不到任何变异号 —— 四件套不完整或形态漂移"
        referenced = {
            ref.split(":", 1)[1]
            for target in gate.MUTATION_TARGETS
            for ref in target.evidence
            if ref.startswith("guard_mutation:")
        }
        assert referenced <= ids, f"引用了不存在的变异号: {sorted(referenced - ids)}"

    def test_every_unverifiable_ref_names_an_owner_and_a_reason(self, gate: Any) -> None:
        for target in gate.MUTATION_TARGETS:
            for ref in target.evidence:
                if not ref.startswith("unverifiable:"):
                    continue
                _, _, rest = ref.partition(":")
                owner, _, why = rest.partition(":")
                assert owner.strip().isdigit(), f"{target.target_id} 的欠账 owner 不是任务号"
                assert len(why.strip()) >= 10, f"{target.target_id} 的欠账理由过短"

    def test_facet_refs_resolve_against_the_live_facet_pool(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """`t71_facet:` 的点号路径必须在报告里真的取到值（不是 `_MISSING`）。"""
        pool = {
            "bp_68_1_recheck": report["bp_68_1_recheck"],
            "capacity": report["capacity"],
            "redaction": report["redaction"],
            "alerting": report["alerting"],
            "fault_injection": report["fault_injection"],
            "data_restoration": report["data_restoration"],
            "deletion_gate": report["deletion_gate"],
            "dag_dependency": report["dag_dependency"],
            "protocol_source_scan": report["protocol_source_scan"],
            "multi_resolver_adjudication": report["multi_resolver_adjudication"],
            "retention": report["retention"],
        }
        bad: list[str] = []
        for target in gate.MUTATION_TARGETS:
            for ref in target.evidence:
                if not ref.startswith("t71_facet:"):
                    continue
                dotted = ref.split(":", 1)[1]
                if gate._dig(pool, dotted) is gate._MISSING:
                    bad.append(f"{target.target_id} -> {ref}")
        assert not bad, f"facet 引用取不到值: {bad}"
        # 反向自检：明显不存在的路径必须被判为缺失（否则 `_dig` 恒返值 = 重言式）
        assert gate._dig(pool, "capacity.no_such_key_t71") is gate._MISSING


# ════════════════════════════════════════════════════════════════════════════
# §4 覆盖档位分类器：判定顺序不可交换 + 反事实 + 正向重算
# ════════════════════════════════════════════════════════════════════════════


class TestCoverageClassifier:
    def test_broken_beats_row_evidence(self, gate: Any) -> None:
        """`evidence_broken` 排第一：有真行证据也不得盖住「引用不成立」。"""
        for override in ({"any_unresolved": True}, {"any_disagreeing": True}):
            tier = gate.classify_coverage(
                has_row_evidence=True,
                has_structural_evidence=True,
                has_unverifiable_evidence=True,
                any_unresolved=override.get("any_unresolved", False),
                any_disagreeing=override.get("any_disagreeing", False),
            )
            assert tier == gate.TIER_BROKEN

    def test_row_beats_structural_beats_unverifiable(self, gate: Any) -> None:
        assert (
            gate.classify_coverage(
                has_row_evidence=True,
                has_structural_evidence=True,
                has_unverifiable_evidence=True,
                any_unresolved=False,
                any_disagreeing=False,
            )
            == gate.TIER_ROWS
        )
        assert (
            gate.classify_coverage(
                has_row_evidence=False,
                has_structural_evidence=True,
                has_unverifiable_evidence=True,
                any_unresolved=False,
                any_disagreeing=False,
            )
            == gate.TIER_STRUCTURAL
        )
        assert (
            gate.classify_coverage(
                has_row_evidence=False,
                has_structural_evidence=False,
                has_unverifiable_evidence=True,
                any_unresolved=False,
                any_disagreeing=False,
            )
            == gate.TIER_UNVERIFIABLE
        )

    def test_nothing_at_all_is_broken_not_verified(self, gate: Any) -> None:
        """一条证据都没有时必须判 broken —— 不许滑到 `verified_on_rows`。"""
        assert (
            gate.classify_coverage(
                has_row_evidence=False,
                has_structural_evidence=False,
                has_unverifiable_evidence=False,
                any_unresolved=False,
                any_disagreeing=False,
            )
            == gate.TIER_BROKEN
        )

    def test_tier_vocabulary_is_closed_and_four(self, gate: Any) -> None:
        assert len(set(gate.COVERAGE_TIERS)) == 4
        assert set(gate.COVERAGE_TIERS) == {
            gate.TIER_ROWS,
            gate.TIER_STRUCTURAL,
            gate.TIER_UNVERIFIABLE,
            gate.TIER_BROKEN,
        }

    def test_no_target_is_broken(self, gate: Any, report: Mapping[str, Any]) -> None:
        tiers = report["coverage_tiers"]
        assert tiers["broken_targets"] == [], f"覆盖档位 broken: {tiers['broken_targets']}"
        assert tiers["verified_on_rows_count"] > 0, "0 条目标有真行证据 —— 覆盖计数必须非空"
        histogram = tiers["tier_histogram"]
        assert sum(histogram.values()) == report["mutation_coverage"]["target_count"]

    def test_counterfactual_arms_are_all_sensitive(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """五条反事实臂必须**逐条**翻转结论；现跑一次而不是只读报告（教训 17）。"""
        live = gate.build_counterfactual_arms(report["mutation_coverage"])
        assert live["all_arms_sensitive"] is True, (
            f"退化成重言式的臂: {live['arms_not_changing_conclusion']}"
        )
        assert len(live["arms"]) == 5
        assert report["counterfactual_arms"]["baseline_counts"] == live["baseline_counts"]

    def test_forward_recompute_agrees_and_has_a_positive_case(self, gate: Any) -> None:
        """多臂只能证明「非重言」，抓不到「恒真」⇒ 必须有正向重算且含正例（教训 15）。"""
        live = gate.build_forward_recompute()
        assert live["all_agree"] is True, f"不符的算例: {live['disagreeing_cases']}"
        assert live["has_positive_case"] is True
        assert len(live["distinct_expected_tiers"]) == 4, (
            "正向重算没有覆盖全部四个档位 —— 抓不到「分类器恒返某一档」"
        )


# ════════════════════════════════════════════════════════════════════════════
# §5 行为侧：对照组 + 实验组 + 拒绝理由互不命中
# ════════════════════════════════════════════════════════════════════════════


class TestBehaviourArms:
    def test_every_facet_has_a_control_and_an_experiment(self, gate: Any) -> None:
        """每个 facet 都必须既有对照组（accepted）又有实验组（rejected/measure）。

        🔴 对照组不过时「非法被拒」可能只是因为世界搭错了（教训 5）。
        """
        facets = {arm.facet for arm in gate.OWN_ARMS}
        assert facets, "一条行为臂都没有"
        for facet in sorted(facets):
            arms = [arm for arm in gate.OWN_ARMS if arm.facet == facet]
            assert any(arm.expectation == "accepted" for arm in arms), f"{facet} 缺对照组"
            assert any(
                arm.expectation in ("rejected", "measure") for arm in arms
            ), f"{facet} 只有对照组"

    def test_rejected_arms_must_declare_a_signature(self, gate: Any) -> None:
        """只比「抛了异常」会把 NOT NULL/FK/别的 CHECK 都算成通过（教训 1）。"""
        for arm in gate.OWN_ARMS:
            if arm.expectation == "rejected":
                assert arm.signature, f"{arm.arm_id} 声明 rejected 却没有 signature"
        with pytest.raises(gate.Task71GateError, match="signature"):
            gate.OwnArm("probe", "probe", "probe", "rejected")
        with pytest.raises(gate.Task71GateError, match="expect"):
            gate.OwnArm("probe", "probe", "probe", "measure")

    def test_all_arms_agree_with_their_declaration(self, report: Mapping[str, Any]) -> None:
        behaviour = report["behaviour"]
        assert behaviour["harness_error"] is None, behaviour["harness_error"]
        assert behaviour["apply_errors"] == []
        assert behaviour["probe_errors"] == {}
        assert behaviour["disagreeing_arms"] == [], behaviour["disagreeing_arms"]
        assert behaviour["missing_observations"] == [], behaviour["missing_observations"]
        assert behaviour["arms_agreeing"] == behaviour["arm_count"]
        assert behaviour["arm_count"] > 0, "行为臂为 0 —— 覆盖计数必须断言非空"

    def test_no_arm_observation_is_written_twice(self, report: Mapping[str, Any]) -> None:
        """同一臂被写两次观测时后写的会静静覆盖前一条 ⇒ 必须显式报出来。"""
        assert report["behaviour"]["duplicate_arm_writes"] == []

    def test_rejection_reasons_are_mutually_exclusive(self, report: Mapping[str, Any]) -> None:
        """任一 rejected 臂的 signature 不得命中另一条 rejected 臂的实测拒绝文案。"""
        assert report["behaviour"]["cross_signature_hits"] == [], (
            f"拒绝理由互相命中: {report['behaviour']['cross_signature_hits']}"
        )

    def test_cross_signature_detector_catches_a_planted_collision(self, gate: Any) -> None:
        """反向自检：人为造一对同签名的 rejected 臂，检测器必须报出来。

        🔴 只断「今天是空的」会让「把 cross 列表短路成 []」变成等价变异（教训 11）。
        """
        planted = {
            "observations": {
                "t71_probe_a": {"accepted": False, "rejection": "SameError|shared-fragment"},
                "t71_probe_b": {"accepted": False, "rejection": "SameError|shared-fragment"},
            }
        }
        original = gate.OWN_ARMS
        try:
            gate.OWN_ARMS = (
                gate.OwnArm("t71_probe_a", "probe", "a", "rejected",
                            signature=("shared-fragment",)),
                gate.OwnArm("t71_probe_b", "probe", "b", "rejected",
                            signature=("shared-fragment",)),
                gate.OwnArm("t71_probe_c", "probe", "c", "accepted"),
            )
            live = gate.build_behaviour_report(planted)
        finally:
            gate.OWN_ARMS = original
        assert live["cross_signature_hits"], (
            "人为造出同签名的两条 rejected 臂，检测器却没报出来 —— 该判据被短路了"
        )

    def test_missing_observation_is_not_a_pass(self, gate: Any) -> None:
        """观测缺失必须判 disagrees（additive 注入即死代码）。"""
        row = gate.evaluate_own_arm(gate.OWN_ARMS[0], None)
        assert row["state"] == "missing_observation"
        assert row["agrees"] is False

    def test_rejected_arm_with_the_wrong_reason_disagrees(self, gate: Any) -> None:
        """喂一条「被拒了但理由完全不同」的观测，必须 disagrees。

        🔴 只断「今天所有臂都 agrees」会让「把 `agrees` 从比 signature 改成只看 `not accepted`」
        变成等价变异（今天每条 signature 本来就命中，首轮实测 M13 GREEN）。这里造非平凡输入。
        """
        arm = next(a for a in gate.OWN_ARMS if a.expectation == "rejected")
        wrong = gate.evaluate_own_arm(
            arm, {"accepted": False, "rejection": "SomeOtherError|完全不同的理由"}
        )
        assert wrong["agrees"] is False, (
            "拒绝理由完全不同却算通过 —— 只比「抛了异常」会把别的约束都算成命中（教训 1）"
        )
        # 对照组：理由正确必须 agrees（否则上一条可能只是「什么都不通过」）
        right = gate.evaluate_own_arm(
            arm, {"accepted": False, "rejection": "|".join(arm.signature)}
        )
        assert right["agrees"] is True

    def test_obs_records_a_duplicate_write(self, gate: Any) -> None:
        """同一臂被写两次观测时必须记进 `duplicates`。

        🔴 只断「今天没有重复」会让「把重复检测短路成 `if False`」变成等价变异（M15 首轮 GREEN）。
        """
        obs = gate._Obs()
        obs.accepted("t71_probe_dup")
        obs.accepted("t71_probe_dup")
        assert obs.duplicates == ["t71_probe_dup"], (
            "重复写观测没有被记录 —— 后写的会静静覆盖前一条而无人知道"
        )
        fresh = gate._Obs()
        fresh.accepted("t71_probe_a")
        fresh.accepted("t71_probe_b")
        assert fresh.duplicates == []

    def test_missing_control_detector_catches_a_planted_facet(self, gate: Any) -> None:
        """植入一个只有实验组的 facet，`facets_missing_control` 必须报出来。

        🔴 只断「今天是空的」会让「把该判据短路成 `if False`」变成等价变异（M16 首轮）。
        """
        original = gate.OWN_ARMS
        try:
            gate.OWN_ARMS = (
                gate.OwnArm(
                    "t71_probe_only_reject", "probe_facet", "只有实验组", "rejected",
                    signature=("z",),
                ),
            )
            live = gate.build_behaviour_report(
                {
                    "observations": {
                        "t71_probe_only_reject": {"accepted": False, "rejection": "z"}
                    }
                }
            )
        finally:
            gate.OWN_ARMS = original
        assert live["facets_missing_control"] == ["probe_facet"], (
            "植入的「只有实验组」facet 没被报出来 —— 对照组缺失无人管（教训 5）"
        )

    def test_measure_arms_compare_every_declared_key(self, gate: Any) -> None:
        """`measure` 臂逐键比对，缺键即 disagrees（禁止只断言「非空」）。"""
        arm = next(a for a in gate.OWN_ARMS if a.expectation == "measure")
        row = gate.evaluate_own_arm(arm, {"measured": {}})
        assert row["agrees"] is False
        assert row["mismatched"]


# ════════════════════════════════════════════════════════════════════════════
# §6 BP-68-1 独立复核
# ════════════════════════════════════════════════════════════════════════════


class TestBp681Recheck:
    def test_upstream_bp_is_still_present_and_owned(self, report: Mapping[str, Any]) -> None:
        row = report["bp_68_1_recheck"]
        assert row["upstream_bp_present"] is True, "上游 BP-68-1 不见了 —— 复核前提已漂移"
        assert row["upstream_arm_id"] == "dlv_pre_durable_owner"

    def test_this_gate_measured_the_ddl_side_independently(
        self, report: Mapping[str, Any]
    ) -> None:
        row = report["bp_68_1_recheck"]
        assert row["this_gate_measures_ddl_accepts"] is True, (
            "本门实测 DDL **拒绝** pre-durable rejected + owner —— 与上游结论相反，须复核"
        )
        assert row["agrees_with_task68"] is True
        assert set(row["per_state_ddl"]) == {"rejected", "error"}, (
            "两个 pre-durable 终态都必须各造一次（只造一个会让另一个永久不可达）"
        )

    def test_service_layer_pure_invariant_half_is_measured(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """BP-68-1 留空的那一半必须有结论，而不是只留一句「靠服务层把住」。

        现跑一次纯不变量探针（不需要数据库），因此对探针实现侧的改动敏感（教训 17）。
        """
        obs = gate._Obs()
        gate.probe_delivery_ownership_invariant(obs)
        live_measured = (obs.data["t71_pre_durable_owner_invariant"] or {})["measured"]
        assert live_measured["negative_control_double_owner_rejected"] is True, (
            "负对照（双 owner）竟然被接受 —— except 分支把拒绝记成了接受"
        )
        assert live_measured["per_state"]["double_owner_negative_control"] is False
        assert live_measured["invariant_accepts_pre_durable_owner"] is True

        half = report["bp_68_1_recheck"]["service_layer_pure_invariant"]
        assert half["callable"] == "assert_delivery_ownership"
        assert set(half["per_state"]) == {
            "rejected",
            "error",
            "double_owner_negative_control",
        }
        assert half["control_arms"] and half["experiment_arms"]
        # 🔴 负对照：必须有一条**真的被拒**的形态。没有它，「抛了也记成接受」这种改动落在
        #    永不执行的 except 分支上 ⇒ 任何判据都抓不到（M50 首轮 GREEN 的根因）。
        assert half["negative_control_double_owner_rejected"] is True
        assert half["per_state"]["double_owner_negative_control"] is False

    def test_recheck_flips_when_the_two_sides_disagree(self, gate: Any) -> None:
        """喂一个「本门实测 DDL 拒绝、上游说接受」的合成 harness，`agrees_with_task68` 必须 False。

        🔴 只断「今天一致」会让「把该字段写死成 True」变成等价变异（M49 首轮 GREEN）——
        独立复核就退化成复述上游结论。
        """
        planted = {
            "observations": {
                "t71_pre_durable_owner_ddl": {
                    "accepted": True,
                    "rejection": None,
                    "measured": {
                        "ddl_accepts_pre_durable_owner": False,
                        "per_state": {"rejected": False, "error": False},
                    },
                },
                "t71_pre_durable_owner_invariant": {
                    "accepted": True,
                    "rejection": None,
                    "measured": {
                        "invariant_accepts_pre_durable_owner": False,
                        "negative_control_double_owner_rejected": True,
                        "per_state": {},
                    },
                },
            }
        }
        live = gate.build_bp_68_1_recheck(planted)
        assert live["this_gate_measures_ddl_accepts"] is False
        assert live["agrees_with_task68"] is False, (
            "两侧结论相反时仍报「与上游一致」—— 独立复核退化成复述"
        )
        assert "不一致" in live["finding"]

    def test_invariant_control_and_experiment_arms_both_landed(
        self, report: Mapping[str, Any]
    ) -> None:
        by_id = {row["arm_id"]: row for row in report["behaviour"]["arms"]}
        for arm_id in (
            "t71_pre_durable_zero_owner_invariant",
            "t71_request_and_application_invariant",
        ):
            assert by_id[arm_id]["expectation"] == "accepted"
            assert by_id[arm_id]["agrees"] is True
        for arm_id in (
            "t71_double_owner_invariant",
            "t71_durable_state_without_fact_invariant",
            "t71_durable_zero_owner_invariant",
        ):
            assert by_id[arm_id]["expectation"] == "rejected"
            assert by_id[arm_id]["agrees"] is True

    def test_invariant_really_runs_the_production_callable(
        self, prod: Mapping[str, Any]
    ) -> None:
        """逻辑级现算：直接调生产纯不变量复现同一结论（不读报告，教训 17）。"""
        import uuid as _uuid

        models = prod["models"]
        state = models.DeliveryState
        # pre-durable rejected + application owner：生产纯不变量今天**不拒**
        models.assert_delivery_ownership(
            state=state.rejected,
            durable_at_is_set=False,
            application_id=_uuid.uuid4(),
            callback_recovery_case_id=None,
        )
        # 双 owner 必拒（对照：说明这个 callable 真的会拒东西，上一条不是因为它什么都不做）
        with pytest.raises(Exception):
            models.assert_delivery_ownership(
                state=state.received,
                durable_at_is_set=False,
                application_id=_uuid.uuid4(),
                callback_recovery_case_id=_uuid.uuid4(),
            )

    def test_bp_71_3_records_the_finding_with_owner(self, report: Mapping[str, Any]) -> None:
        point = next(p for p in report["blocking_points"] if p["id"] == "BP-71-3")
        assert point["owner_task"] == "22"
        assert "assert_delivery_ownership" in str(point["statement"]) or "纯不变量" in str(
            point["statement"]
        )
        assert point["measured"]["pure_invariant_accepts"] is True


# ════════════════════════════════════════════════════════════════════════════
# §7 六个面各自独立
# ════════════════════════════════════════════════════════════════════════════


class TestCapacityFacet:
    def test_profile_matches_requirements_text(
        self, prod: Mapping[str, Any], report: Mapping[str, Any]
    ) -> None:
        """逻辑级现算：期望值来自需求原文，不从被测常量抄一遍。"""
        capacity = prod["capacity"]
        facts = capacity.requirement_facts()
        assert facts == report["capacity"]["requirement_facts"]
        for name, want in facts.items():
            assert getattr(capacity.CAPACITY_PROFILE, name) == want
        assert report["capacity"]["profile_matches_requirements"] is True

    def test_fail_closed_without_execution_record(
        self, prod: Mapping[str, Any], report: Mapping[str, Any]
    ) -> None:
        """没有执行记录时必须**抛**而不是返回 False（返回值会被 `if not ok: pass` 吞掉）。"""
        capacity = prod["capacity"]
        with pytest.raises(capacity.CapacityNotExecutedError):
            capacity.assert_capacity_verified(None)
        # 🔴 现跑门的函数而不是只读磁盘报告：把 `assert_capacity_verified(None)` 的调用删掉时
        #    磁盘报告不会变（M18 首轮 WRONG-TEST 的根因，教训 17）。
        for row in (
            gate_capacity(_load_gate())["fail_closed_without_execution_record"],
            report["capacity"]["fail_closed_without_execution_record"],
        ):
            assert row["raised"] is True
            assert row["is_not_executed_error"] is True
            assert row["error_code"] == "sync_capacity_not_executed"

    def test_production_names_this_task_as_execution_owner(
        self, prod: Mapping[str, Any], report: Mapping[str, Any]
    ) -> None:
        capacity = prod["capacity"]
        assert capacity.CAPACITY_PROFILE.execution_owner.endswith("71")
        assert report["capacity"]["execution_owner_declared_by_production"].endswith("71")
        assert report["capacity"]["status_is_registered_pending_execution"] is True

    def test_evaluator_arms_cover_all_seven_budgets(self, report: Mapping[str, Any]) -> None:
        """四条负载 + 一条时长 + 两条延迟，逐条独立成一条 shortfall（合并会丢「哪项没达标」）。"""
        capacity = report["capacity"]
        assert capacity["evaluator_arms_disagreeing"] == []
        assert capacity["evaluator_control_arms"] >= 1
        assert capacity["evaluator_experiment_arms"] >= 7
        ids = {row["arm_id"] for row in capacity["evaluator_arms"]}
        for field in (
            "concurrent_login_sessions",
            "active_onlyoffice_participants",
            "same_second_forcesave_burst",
            "sustained_applications_per_second",
            "sustained_duration_seconds",
        ):
            assert f"cap_shortfall_{field}" in ids, f"缺 {field} 的 shortfall 臂"
        for field in ("incoming_durable_p95_seconds", "applied_terminal_p95_seconds"):
            assert f"cap_over_budget_{field}" in ids
        assert "cap_shortfall_without_adr_raises" in ids
        assert "cap_missing_environment_raises" in ids

    def test_real_load_is_unverifiable_with_an_owner_and_premises(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """真实负载必须如实标 UNVERIFIABLE 并点名 owner —— 不许用合成值冒充通过。

        🔴 现跑 + 报告双侧：只读报告时把 tier 谎报成 EXECUTED 磁盘不会变（M17 首轮 WRONG-TEST）。
        """
        for row in (
            gate_capacity(gate)["real_load_execution"],
            report["capacity"]["real_load_execution"],
        ):
            assert row["tier"] == "UNVERIFIABLE"
            assert str(row["owner_task"]).strip()
            assert row["measured_premises"]["port_3030_listening"] is False
            assert row["measured_premises"]["task70_executed_end_to_end"] == 0
            assert "不" in row["not_claimed"]

    def test_gate_really_calls_the_production_requirement_lock(self, gate: Any) -> None:
        """`assert_profile_matches_requirements` 与 `assert_capacity_verified` 必须**被真调**。

        判据走 AST（不走子串），且先剥注释 —— 门的文档里正当地引用了这两个名字（教训 12）。
        🔴 只断「登记值与需求原文相等」会让「把调用删掉」变成等价变异：那条相等关系由生产
        常量与需求原文各自成立，与门有没有调它无关（M19 首轮 GREEN 的根因）。
        """
        tree = ast.parse(gate.strip_comments(GATE_PATH.read_text(encoding="utf-8")))
        called = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        for name in ("assert_profile_matches_requirements", "assert_capacity_verified"):
            assert name in called, f"门没有真调生产的 {name}()"

    def test_synthetic_measurements_are_labelled(self, report: Mapping[str, Any]) -> None:
        capacity = report["capacity"]
        assert capacity["synthetic_measurements_are_labelled"] is True
        assert "synthetic" in capacity["synthetic_label"]


_FACET_CACHE: dict[str, Any] = {}


def gate_facet(gate: Any, name: str) -> Mapping[str, Any]:
    """**现跑**一个纯内存面（redaction / alerting）并在进程内缓存。

    🔴 只读磁盘报告的判据对这两个面的实现改动天生不敏感（教训 17）：把「植入密钥是否存活」
    的现算短路、或把 synthetic 事件流的一半删掉时磁盘报告都不会变
    （M51~M54 首轮全部 GREEN 的根因）。
    """
    if name not in _FACET_CACHE:
        _FACET_CACHE[name] = getattr(gate, f"build_{name}")()
    return _FACET_CACHE[name]


class TestRedactionFacet:
    def test_no_planted_secret_survives(self, gate: Any, report: Mapping[str, Any]) -> None:
        for row in (gate_facet(gate, "redaction"), report["redaction"]):
            assert row["planted_secret_count"] >= 4
            assert row["leaked_planted_secrets"] == [], row["leaked_planted_secrets"]
            assert row["no_planted_secret_survives"] is True
            assert row["exception_with_url_contains_secret"] is False
            assert row["exception_with_bearer_contains_secret"] is False
            assert row["url_redacted_contains_secret"] is False

    def test_bare_token_in_free_text_gap_is_registered_not_hidden(
        self, prod: Mapping[str, Any], report: Mapping[str, Any]
    ) -> None:
        """自由文本里的裸 `token=<短串>` 不被抹 —— 如实登记 + 点名 owner，不假装已覆盖。

        逻辑级现算：直接调生产 `redact_exception` 复现同一结论（不读报告，教训 17）。
        """
        row = report["redaction"]
        assert row["bare_token_in_free_text_is_scrubbed"] is False
        assert str(row["bare_token_owner_task"]).strip()
        assert "既有设计边界" in row["bare_token_finding"]

        live = gate_facet(_load_gate(), "redaction")
        assert live["bare_token_in_free_text_is_scrubbed"] is False
        assert str(live["bare_token_owner_task"]).strip()

        redaction = prod["redaction"]
        policy = redaction.load_redaction_policy()
        secret = "t71-guard-bare-token-4b1f"
        # 裸短串：不命中任何 value pattern ⇒ 留在文本里
        assert secret in policy.redact_exception(RuntimeError(f"失败 token={secret}"))
        # 对照：命中 bearer_header pattern 的同一串必须被抹（说明 scrubber 真的在工作）
        assert secret not in policy.redact_exception(RuntimeError(f"失败 Bearer {secret}"))

    def test_control_passes_and_four_experiments_raise(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        for row in (gate_facet(gate, "redaction"), report["redaction"]):
            assert row["arms_disagreeing"] == [], row["arms_disagreeing"]
            assert row["control_arm_count"] >= 1
            assert row["experiment_arm_count"] >= 4
            # 四条实验组的拒绝理由不得全撞成一条（否则其中三条是死判据，教训 1）
            assert row["distinct_rejection_signatures"] >= 2

    def test_leak_detector_really_raises_on_raw_payload(
        self, prod: Mapping[str, Any]
    ) -> None:
        """逻辑级现算：直接调生产 `assert_no_leak` 复现（对照组 + 实验组各一条）。"""
        redaction = prod["redaction"]
        policy = redaction.load_redaction_policy()
        projected, _ = policy.redact({"authorization": "Bearer t71-guard-secret"})
        policy.assert_no_leak(projected)  # 对照组：脱敏后必须过
        with pytest.raises(Exception):
            policy.assert_no_leak({"authorization": "Bearer t71-guard-secret"})


class TestAlertingFacet:
    def test_three_way_validation_is_clean(
        self, prod: Mapping[str, Any], report: Mapping[str, Any]
    ) -> None:
        alerting = prod["alerting"]
        registry = alerting.load_alert_registry()
        assert list(alerting.validate_registry(registry)) == []
        assert report["alerting"]["three_way_clean"] is True
        assert report["alerting"]["conditions_without_rule"] == []

    def test_every_requirement_13_9_condition_has_a_rule(
        self, prod: Mapping[str, Any], report: Mapping[str, Any]
    ) -> None:
        """独立现算 Requirement 13.9 的分母并与报告比对。"""
        alerting = prod["alerting"]
        registry = alerting.load_alert_registry()
        for label, condition in alerting.REQUIREMENT_13_9_CONDITIONS.items():
            assert condition in registry.rules_by_condition, f"13.9 的「{label}」没有规则"
        assert report["alerting"]["requirement_13_9_condition_count"] == len(
            alerting.REQUIREMENT_13_9_CONDITIONS
        )

    def test_every_rule_fires_at_threshold_and_is_silent_below(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """逐规则两组样本：少任何一半都会让「阈值改 0」或「恒触发」测不出来。

        现跑 + 报告双侧：只读报告时把 `agrees` 写死、或把阈值以下那一半删掉都不会改磁盘。
        """
        for row in (gate_facet(gate, "alerting"), report["alerting"]):
            assert row["rules_disagreeing"] == [], row["rules_disagreeing"]
            assert row["rules_firing_at_threshold"] == row["rule_count"]
            assert row["rules_silent_below_threshold"] == row["rule_count"]
            assert row["rule_count"] > 0
            for rule in row["rules"]:
                assert rule["fires_at_threshold"] is True, rule["rule_id"]
                assert rule["silent_below_threshold"] is True, rule["rule_id"]

    def test_dedupe_collapses_same_key_and_keeps_distinct_keys(
        self, report: Mapping[str, Any]
    ) -> None:
        row = report["alerting"]
        assert row["dedupe_same_key_instance_count"] == 1
        assert row["dedupe_distinct_key_instance_count"] == 2

    def test_both_recovery_kinds_have_rules(self, report: Mapping[str, Any]) -> None:
        """自动恢复与显式处理两态都必须有落点 —— 全落一态说明分型是装饰。"""
        row = report["alerting"]
        assert row["auto_recovering_rule_count"] > 0
        assert row["explicit_resolution_rule_count"] > 0

    def test_runbooks_meet_the_minimum(self, report: Mapping[str, Any]) -> None:
        row = report["alerting"]
        assert row["shortest_runbook_chars"] >= row["min_runbook_chars_required"]

    def test_naive_datetime_and_unknown_rule_are_rejected(
        self, report: Mapping[str, Any]
    ) -> None:
        assert report["alerting"]["naive_datetime_rejected"]["raised"] is True
        assert report["alerting"]["unknown_rule_id_rejected"]["raised"] is True


_FAULT_CACHE: dict[str, Any] = {}


def gate_fault(gate: Any, report: Mapping[str, Any]) -> Mapping[str, Any]:
    """**现跑**一次故障注入面并在进程内缓存。

    🔴 只读磁盘报告的判据对注入函数的改动天生不敏感（教训 17）：把 Windows lock 的句柄换成
    别的文件、或把 OO 注入的判定短路掉时磁盘报告不会变（M40/M41/M42 首轮全部 WRONG-TEST /
    GREEN 的根因）。进程中断那条依赖 scratch schema，因此从报告里取它的既有观测复用。
    """
    if "value" not in _FAULT_CACHE:
        atomicity = next(
            row
            for row in report["behaviour"]["arms"]
            if row["arm_id"] == "t71_atomicity_partial_rollback"
        )
        _FAULT_CACHE["value"] = gate.build_fault_injection(
            {
                "observations": {
                    "t71_atomicity_partial_rollback": {
                        "accepted": True,
                        "rejection": None,
                        "measured": atomicity["measured"],
                    }
                }
            }
        )
    return _FAULT_CACHE["value"]


class TestFaultInjectionFacet:
    def test_all_six_injections_are_present_and_agree(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        live = gate_fault(gate, report)
        assert set(live["injections"]) == set(report["fault_injection"]["injections"])
        assert live["injections_disagreeing"] == [], live["injections_disagreeing"]
        assert len(live["injections_agreeing"]) == 6
        row = report["fault_injection"]
        assert set(row["injections"]) == {
            "onlyoffice",
            "postgres",
            "redis",
            "disk",
            "windows_lock",
            "process_interrupt",
        }
        assert row["injections_disagreeing"] == [], row["injections_disagreeing"]
        assert len(row["injections_agreeing"]) == 6

    def test_each_injection_carries_a_measurement_and_an_expectation(
        self, report: Mapping[str, Any]
    ) -> None:
        for name, row in report["fault_injection"]["injections"].items():
            assert row["measured"], f"{name} 缺实测"
            assert str(row["expectation"]).strip(), f"{name} 缺期望"
            assert str(row["kind"]).strip(), f"{name} 缺分类"

    def test_windows_lock_keeps_the_file_and_classifies_the_error(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """现跑 + 报告双侧：真占用句柄 ⇒ 删不掉、被分类成 FILE_IN_USE、文件仍在。"""
        for source in (gate_fault(gate, report), report["fault_injection"]):
            row = source["injections"]["windows_lock"]["measured"]
            assert row["control_delete_without_handle"] is True, "对照组没删掉 —— 世界搭错了"
            assert row["control_file_gone"] is True
            assert row["experiment"]["raised"] is True, (
                "持有句柄时删除竟然成功 —— 注入没有真的占用目标文件，对照组失效"
            )
            assert row["experiment"]["classified_file_in_use"] is True
            assert row["file_survived_the_locked_attempt"] is True
            assert row["root_removed"] is True

    def test_process_interrupt_leaves_no_partial_rows(self, report: Mapping[str, Any]) -> None:
        row = report["fault_injection"]["injections"]["process_interrupt"]["measured"]
        assert row["raised"] is True
        assert row["rows_after_failed_transaction"] == 0

    def test_disk_injection_distinguishes_escape_from_absent(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """两条分支必须**各自**有结论：合并会让「不存在的对象」被当成「已删」。"""
        for source in (gate_fault(gate, report), report["fault_injection"]):
            row = source["injections"]["disk"]["measured"]
            assert row["path_escape"]["raised"] is True
            assert str(row["path_escape"].get("signature") or ""), (
                "路径越界被报成已拒但没有拒绝理由 —— 只比「抛了异常」不够（教训 1）"
            )
            assert "ArtifactPathError" in str(row["path_escape"]["signature"])
            assert row["absent_object"]["raised"] is False
            assert row["absent_object"]["returned"] is False
            assert row["root_removed"] is True

    def test_orphan_outbox_pointer_gaps_name_their_owners(
        self, report: Mapping[str, Any]
    ) -> None:
        row = report["fault_injection"]["orphan_outbox_pointers"]
        assert row["dual_baseline_tier"] == "UNVERIFIABLE"
        assert str(row["dual_baseline_owner"]).strip()
        assert row["real_concurrent_retry_tier"] == "UNVERIFIABLE"
        assert str(row["real_concurrent_retry_owner"]).strip()
        assert row["retention_reference_sources"] > 0


@pytest.fixture(scope="module")
def live_behaviour(gate: Any) -> Mapping[str, Any]:
    """**现跑**一次 scratch schema 行为侧采集（模块级缓存，只跑一次）。

    🔴 retention 的十二条臂全在这里产生；只读磁盘报告的判据对 `_probe_retention` 的改动天生
    不敏感（M55/M56 首轮 WRONG-TEST 的根因，教训 17）。这一次采集同时验证复原实证可复现。
    """
    return gate.build_behaviour_report(gate.collect_all_observations())


class TestRetentionFacet:
    def test_live_harness_reproduces_all_arms(self, live_behaviour: Mapping[str, Any]) -> None:
        """现跑一轮：采集无错、逐臂符合声明、无缺失观测。"""
        assert live_behaviour["harness_error"] is None, live_behaviour["harness_error"]
        assert live_behaviour["probe_errors"] == {}, live_behaviour["probe_errors"]
        assert live_behaviour["disagreeing_arms"] == [], live_behaviour["disagreeing_arms"]
        assert live_behaviour["missing_observations"] == []

    def test_plan_covers_seven_decision_branches_live(
        self, live_behaviour: Mapping[str, Any]
    ) -> None:
        by_id = {row["arm_id"]: row for row in live_behaviour["arms"]}
        for arm_id in (
            "t71_retention_plan_deletes_unreferenced",
            "t71_retention_legal_hold",
            "t71_retention_ttl_not_elapsed",
            "t71_retention_grace_not_elapsed",
            "t71_retention_reference_found",
            "t71_retention_class_scope_mismatch",
            "t71_retention_no_policy_retains_and_alerts",
        ):
            assert by_id[arm_id]["agrees"] is True, arm_id

    def test_apply_protocol_and_recheck_branches_live(
        self, live_behaviour: Mapping[str, Any]
    ) -> None:
        by_id = {row["arm_id"]: row for row in live_behaviour["arms"]}
        for arm_id in (
            "t71_retention_apply_requires_dry_run",
            "t71_retention_apply_policy_version_drift",
            "t71_retention_apply_deletes_and_audits",
            "t71_retention_windows_lock_retains",
            "t71_retention_reference_reappears_on_recheck",
        ):
            assert by_id[arm_id]["agrees"] is True, arm_id
        recheck = by_id["t71_retention_reference_reappears_on_recheck"]["measured"]
        assert recheck["reason"] == "reference_found_on_recheck"

    def test_plan_covers_seven_decision_branches(self, report: Mapping[str, Any]) -> None:
        by_id = {row["arm_id"]: row for row in report["behaviour"]["arms"]}
        for arm_id in (
            "t71_retention_plan_deletes_unreferenced",
            "t71_retention_legal_hold",
            "t71_retention_ttl_not_elapsed",
            "t71_retention_grace_not_elapsed",
            "t71_retention_reference_found",
            "t71_retention_class_scope_mismatch",
            "t71_retention_no_policy_retains_and_alerts",
        ):
            assert arm_id in by_id, f"缺 {arm_id}"
            assert by_id[arm_id]["agrees"] is True, arm_id

    def test_apply_protocol_and_recheck_branches(self, report: Mapping[str, Any]) -> None:
        by_id = {row["arm_id"]: row for row in report["behaviour"]["arms"]}
        for arm_id in (
            "t71_retention_apply_requires_dry_run",
            "t71_retention_apply_policy_version_drift",
            "t71_retention_apply_deletes_and_audits",
            "t71_retention_windows_lock_retains",
            "t71_retention_reference_reappears_on_recheck",
        ):
            assert by_id[arm_id]["agrees"] is True, arm_id
        recheck = by_id["t71_retention_reference_reappears_on_recheck"]["measured"]
        assert recheck["reason"] == "reference_found_on_recheck"
        assert recheck["deleted"] == 0

    def test_retention_facts_are_recorded(self, report: Mapping[str, Any]) -> None:
        facts = report["retention"]
        assert facts, "retention 面没有任何实测"
        assert facts["decision_count"] > 0
        assert facts["apply_deleted"] == 1
        assert facts["deleted_file_gone"] is True
        assert facts["apply_audit_sha256_present"] is True
        assert "delete_failed" in facts["windows_lock_alerts"]

    def test_reference_sources_match_production_declaration(
        self, prod: Mapping[str, Any], report: Mapping[str, Any]
    ) -> None:
        retention = prod["retention"]
        assert report["retention"]["reference_sources_declared"] == len(
            retention.REFERENCE_SOURCES
        )
        assert len(retention.REFERENCE_SOURCES) >= 10


class TestDataRestoration:
    def test_public_schema_is_unchanged(self, report: Mapping[str, Any]) -> None:
        row = report["data_restoration"]
        assert row["measured"] is True
        assert row["drifted_tables"] == {}, row["drifted_tables"]
        assert row["table_count"] > 0
        assert set(row["public_before"]) == set(row["public_after"])

    def test_own_scratch_schema_is_dropped(self, report: Mapping[str, Any]) -> None:
        row = report["data_restoration"]
        assert row["own_schema_left"] == 0
        assert row["restored"] is True

    def test_foreign_and_upstream_leftovers_are_reported_separately(
        self, report: Mapping[str, Any]
    ) -> None:
        """本轮残留与外来残留必须**分开**报：合并会让其中一类被静默容忍或造出假红。"""
        row = report["data_restoration"]
        assert "own_schema_left" in row
        assert "foreign_scratch_schemas" in row
        assert "upstream_scratch_schemas" in row
        assert row["own_schema_left"] not in row["foreign_scratch_schemas"]

    def test_temp_artifact_root_is_removed(self, report: Mapping[str, Any]) -> None:
        assert report["data_restoration"]["temp_artifact_root_removed"] is True

    def test_restoration_record_catches_drift_leftovers_and_temp_dir(
        self, gate: Any
    ) -> None:
        """喂三种「没复原」的合成 harness，逐条必须被抓到。

        🔴 只断「今天前后行数相等」会让「把比较改成 `if False`」变成等价变异（M37/M38/M39
        首轮 GREEN）。三条各自独立造一次：行数漂移 / 本轮 scratch 残留 / 临时目录未删。
        """
        clean = {
            "public_before": {"t": 1},
            "public_after": {"t": 1},
            "own_schema_left": 0,
            "foreign_scratch_schemas": [],
            "upstream_scratch_schemas": [],
            "temp_artifact_root_removed": True,
            "scratch_row_counts": {},
        }
        assert gate.restoration_record(clean)["restored"] is True  # 对照组先过

        drifted = gate.restoration_record({**clean, "public_after": {"t": 2}})
        assert drifted["drifted_tables"] == {"t": {"before": 1, "after": 2}}, (
            "生产 public 行数漂移没被抓到 —— 「悄悄写了库」会被报成 0 行新增"
        )
        assert drifted["restored"] is False

        left = gate.restoration_record({**clean, "own_schema_left": 1})
        assert left["own_schema_left"] == 1, "本轮 scratch 残留被写死成 0"
        assert left["restored"] is False

        temp = gate.restoration_record({**clean, "temp_artifact_root_removed": False})
        assert temp["restored"] is False, "临时 artifact 根未删仍判已复原"

    def test_foreign_and_own_leftovers_do_not_contaminate_each_other(
        self, gate: Any
    ) -> None:
        """外来残留不得让本轮结论变红；本轮残留不得被外来残留掩盖。"""
        base = {
            "public_before": {"t": 1},
            "public_after": {"t": 1},
            "own_schema_left": 0,
            "foreign_scratch_schemas": ["tmp_task71_chaos_deadbeef"],
            "upstream_scratch_schemas": ["tmp_task24_ci_x"],
            "temp_artifact_root_removed": True,
            "scratch_row_counts": {},
        }
        row = gate.restoration_record(base)
        assert row["restored"] is True, "外来残留把本轮的复原结论打成假红"
        assert row["foreign_scratch_schemas"] == ["tmp_task71_chaos_deadbeef"]
        assert row["upstream_scratch_schemas"] == ["tmp_task24_ci_x"]
        assert gate.restoration_record({**base, "own_schema_left": 1})["restored"] is False

    def test_no_task71_temp_dir_is_left_on_disk(self) -> None:
        """会话产物清理：磁盘上不得留下本门的临时目录。"""
        leftovers = sorted(
            path.name
            for path in REPO.glob("tmp_task71_*")
            if path.is_dir()
        )
        assert leftovers == [], f"本门的临时目录残留: {leftovers}"


# ════════════════════════════════════════════════════════════════════════════
# §8 `multi_resolver` 裁决
# ════════════════════════════════════════════════════════════════════════════


class TestMultiResolverAdjudication:
    def test_four_named_rows_are_written_down(self, gate: Any) -> None:
        """名单类判据必须写死真实目标（教训 16）。"""
        assert set(gate.MULTI_RESOLVER_ROWS) == {
            "get_sheet_onlyoffice_config",
            "get_sheet_wopi_contents",
            "get_whole_excel_grid",
            "post_sheet_onlyoffice_callback",
        }

    def test_named_rows_come_from_the_task_text(self, gate: Any) -> None:
        """四条行名必须在正文里逐字出现（防「悄悄换一条更容易归零的行」）。"""
        body = gate.task_body()
        for name in gate.MULTI_RESOLVER_ROWS:
            assert name in body, f"{name} 不在正文里 —— 名单与正文脱钩"

    def test_measured_count_matches_named_rows(self, report: Mapping[str, Any]) -> None:
        row = report["multi_resolver_adjudication"]
        assert row["multi_resolver_count"] == len(row["named_rows"])
        assert row["measured_rows_match_named"] is True

    def test_criterion_does_not_pass_today_and_says_why(
        self, report: Mapping[str, Any]
    ) -> None:
        """实测非零 ⇒ 本门这条准则不过，且必须说清后果（不放行任务 72 的 legacy 删除）。"""
        row = report["multi_resolver_adjudication"]
        assert row["multi_resolver_is_zero"] is False
        assert row["criterion_passes"] is False
        assert len(row["rows_still_deferred"]) == 4
        assert "legacy_delete" in row["consequence_if_not_zero"]
        assert report["verdict"]["legacy_delete_released"] is False
        assert "保持红" in report["verdict"]["task72_stage_a"]

    def test_matrix_keeps_two_independent_fields(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """`blocking_task` 指真实阻塞、`adjudication_owner_task` 指本门 —— 合并即失去意义。

        现算 + 报告双侧：只读报告的判据对实现侧改动天生不敏感（教训 17）。
        """
        for row in (gate.resolver_matrix_facts(), report["multi_resolver_adjudication"]):
            assert row["two_independent_fields_present"] is True
            assert row["fields_are_not_merged"] is True
            assert row["rows_with_adjudication_owner_71"] == sorted(
                gate.MULTI_RESOLVER_ROWS
            )
            assert row["rows_with_blocking_task_pointing_at_36"] == sorted(
                gate.MULTI_RESOLVER_ROWS
            )

    def test_matrix_facts_catch_merged_fields(self, gate: Any, tmp_path: Any) -> None:
        """喂一份「两个字段被合并」且「仍 deferred」的合成矩阵，两条判据必须都翻转。

        🔴 只断「今天两个字段不同」会让「把 `fields_are_not_merged` 写死成 True」变成等价
        变异（M29 首轮 WRONG-TEST）。合成矩阵让判据可以在秒级复核，不必连带重算 writer matrix。
        """
        merged = tmp_path / "merged_matrix.json"
        merged.write_text(
            json.dumps(
                {
                    "rows": [
                        {
                            "qualname": name,
                            "module": "app.routers.wp_onlyoffice_router",
                            "status": "deferred",
                            "intended_status": "deferred",
                            "blocking_task": "71",
                            "adjudication_owner_task": "71",
                        }
                        for name in gate.MULTI_RESOLVER_ROWS
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        live = gate.resolver_matrix_facts(merged)
        assert live["fields_are_not_merged"] is False, (
            "两个字段被合并后判据仍为 True —— 「登记的阻塞必须真的把守发布门」失去意义"
        )
        assert live["rows_still_deferred"] == sorted(gate.MULTI_RESOLVER_ROWS), (
            "仍 deferred 的四条行没被报出来 —— 正文逐字要求的「任一行仍 deferred 即不过」失守"
        )
        # 对照组：真实矩阵下两个字段不同且能正确列出 deferred 行
        real = gate.resolver_matrix_facts()
        assert real["fields_are_not_merged"] is True

    def test_criterion_helper_requires_both_conditions(self, gate: Any) -> None:
        """准则必须**两个**条件都满足：计数为 0 **且**四条行都不再 deferred。"""
        assert gate.multi_resolver_criterion_passes(
            multi_resolver_rows=[], rows_still_deferred=[]
        ) is True
        assert gate.multi_resolver_criterion_passes(
            multi_resolver_rows=["x"], rows_still_deferred=[]
        ) is False, "计数非零却放行 —— 正文逐字「计数非零则本门不过」"
        assert gate.multi_resolver_criterion_passes(
            multi_resolver_rows=[], rows_still_deferred=["y"]
        ) is False, "仍有 deferred 行却放行 —— 正文逐字「任一行仍 deferred 则本门不过」"

    def test_inventory_staleness_helper_compares_digests(self, gate: Any) -> None:
        assert gate.inventory_staleness(live_digest="a", on_disk_digest="b") is True
        assert gate.inventory_staleness(live_digest="a", on_disk_digest="a") is False

    def test_bulk_adapters_gate_is_not_attached(self, report: Mapping[str, Any]) -> None:
        row = report["multi_resolver_adjudication"]
        assert row["bulk_adapters_gate_not_attached"] is True
        assert "Wave 5" in row["why_bulk_adapters_not_attached"]

    def test_all_fourteen_writer_criteria_are_measured(self, report: Mapping[str, Any]) -> None:
        """14 条准则逐条登记计数（只报自己那一条会让「其余被顶回非零」看不见）。"""
        row = report["multi_resolver_adjudication"]
        assert row["writer_gate_criteria_count"] == 14
        assert "multi_resolver" in row["writer_gate_criteria"]

    def test_inventory_staleness_is_reported_not_silently_regenerated(
        self, report: Mapping[str, Any]
    ) -> None:
        row = report["multi_resolver_adjudication"]
        assert row["inventory_on_disk_is_stale"] is True
        assert str(row["inventory_stale_owner_task"]).strip()
        assert row["inventory_source_digest_on_disk"] != row["inventory_source_digest_live"]
        assert "不" in row["inventory_stale_note"]


# ════════════════════════════════════════════════════════════════════════════
# §9 删除门 / DAG / 协议源码现算
# ════════════════════════════════════════════════════════════════════════════


class TestDeletionGateMutations:
    def test_three_landings_each_agree_independently(self, report: Mapping[str, Any]) -> None:
        """三条落点**各自**独立成字段（合并会让靠后的那条永久不可达）。"""
        row = report["deletion_gate"]
        for key in (
            "task67_must_not_require_zero_stale",
            "task67_must_not_claim_eligibility",
            "task72_stage_a_must_not_require_unreachable_zero",
            "smoke_cannot_restore_verified",
        ):
            assert key in row, f"缺 {key}"
            assert row[key]["agrees"] is True, key
            assert str(row[key].get("why") or "").strip() or key.startswith("task67_must_not_claim")

    def test_task67_stale_is_really_nonzero(self, report: Mapping[str, Any]) -> None:
        """「不要求清零」这条判据的前提：上游 stale 计数**真的**非零。"""
        row = report["deletion_gate"]["task67_must_not_require_zero_stale"]
        assert row["stale_is_nonzero"] is True
        assert row["entries_with_any_stale_axis"] > 0
        assert row["stale_axis_kinds"] >= 3

    def test_task67_claims_no_eligibility(self, report: Mapping[str, Any]) -> None:
        assert report["deletion_gate"]["task67_must_not_claim_eligibility"][
            "eligibility_tokens_found"
        ] == []

    def test_stale_and_eligibility_fields_are_computed_not_hardcoded(
        self, gate: Any, tmp_path: Any, monkeypatch: Any
    ) -> None:
        """喂一份「stale 为 0 且宣称 eligibility」的合成上游报告，两个字段必须都翻转。

        🔴 只断「今天成立」会让「把 `stale_is_nonzero` 写死成 True」变成等价变异
        （M21 首轮 GREEN）。这里把上游报告换掉，逼门自己算。
        """
        synthetic = tmp_path / "synthetic_t67.json"
        synthetic.write_text(
            json.dumps(
                {
                    "entries": [{"entry_id": "x", "evidence_rerun_axes": []}],
                    "verdict": {"state": "eligibility_declared",
                                "state_vocabulary": ["eligibility_declared"]},
                    "eligibility": {"claimed": True},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(gate, "T67_REPORT", synthetic)
        live = gate.build_deletion_gate()
        assert live["task67_must_not_require_zero_stale"]["stale_is_nonzero"] is False, (
            "stale 计数为 0 的合成报告仍被判成非零 —— 该字段被写死了"
        )
        assert live["task67_must_not_require_zero_stale"]["agrees"] is False
        assert live["task67_must_not_claim_eligibility"]["eligibility_tokens_found"], (
            "宣称 eligibility 的合成报告没有被抓到 —— 该判据被短路了"
        )
        assert live["task67_must_not_claim_eligibility"]["agrees"] is False

    def test_stage_a_clause_is_read_from_the_task_text(
        self, gate: Any, monkeypatch: Any
    ) -> None:
        """把 Task 72 正文里那条 clause 抹掉，字段必须翻转（现算，不写死）。"""
        real_task_body = gate.task_body

        def _stripped(task_number: str = "71") -> str:
            body = real_task_body(task_number)
            if task_number == "72":
                body = body.replace("不得要求待删 unreachable在删除前已为0", "")
                body = body.replace("不得要求待删 unreachable 在删除前已为 0", "")
            return body

        monkeypatch.setattr(gate, "task_body", _stripped)
        live = gate.build_deletion_gate()
        row = live["task72_stage_a_must_not_require_unreachable_zero"]
        assert row["clause_present_in_task72_text"] is False, (
            "正文里那条 clause 被抹掉后字段仍为 True —— 该判据被写死了"
        )
        assert row["agrees"] is False

    def test_smoke_field_is_read_from_task70_vocabulary(
        self, gate: Any, tmp_path: Any, monkeypatch: Any
    ) -> None:
        """给任务 70 的词表塞一个 `passed`，`smoke_cannot_restore_verified` 必须翻转。

        🔴 只断「今天词表里没有 passed」会让「把该字段写死成 True」变成等价变异（M23 首轮）。
        """
        real = json.loads(
            (REPO / "backend/data/workpaper_sync_task70_oo_scenario_refresh.json").read_text(
                encoding="utf-8"
            )
        )
        real["verdict"]["state_vocabulary"] = list(real["verdict"]["state_vocabulary"]) + [
            "passed"
        ]
        synthetic = tmp_path / "synthetic_t70.json"
        synthetic.write_text(json.dumps(real, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(gate, "T70_REPORT", synthetic)
        live = gate.build_deletion_gate()
        row = live["smoke_cannot_restore_verified"]
        assert row["task70_vocabulary_has_no_passed"] is False, (
            "词表里塞进 `passed` 后字段仍为 True —— 该判据被写死了"
        )
        assert row["agrees"] is False

    def test_smoke_cannot_flip_evidence_back_to_verified(
        self, report: Mapping[str, Any]
    ) -> None:
        row = report["deletion_gate"]["smoke_cannot_restore_verified"]
        assert row["task70_vocabulary_has_no_passed"] is True
        assert "passed" not in row["task70_verdict_vocabulary"]
        assert row["task72_text_says_smoke_only_appends"] is True

    def test_evidence_rows_are_measured_as_zero_and_owned(
        self, report: Mapping[str, Any]
    ) -> None:
        row = report["deletion_gate"]
        assert row["evidence_scenario_rows"] == 0
        assert row["test_run_rows"] == 0
        assert row["required_scenario_rows"] > 0
        point = next(p for p in report["blocking_points"] if p["id"] == "BP-71-4")
        assert point["owner_task"] == "70"


class TestDagDependency:
    def test_task24_depends_on_task23(self, gate: Any, report: Mapping[str, Any]) -> None:
        """逻辑级现算依赖图（不读报告自述）。"""
        graph = gate.dependency_graph()
        deps = {str(k): [str(v) for v in vals] for k, vals in graph["dependencies"].items()}
        assert "23" in deps["24"], "任务 24 对任务 23 的依赖不在依赖图里"
        assert report["dag_dependency"]["task24_depends_on_task23"] is True

    def test_the_field_is_computed_not_hardcoded(
        self, gate: Any, monkeypatch: Any
    ) -> None:
        """喂一张**没有**那条依赖的图，字段必须变 False。

        🔴 只断「今天是 True」会让「把字段写死成 True」变成等价变异（M20 首轮 GREEN）——
        而正文点名的变异正是「把任务 24 对任务 23 的依赖删掉」，写死之后它删了也不红。
        """
        monkeypatch.setattr(
            gate,
            "dependency_graph",
            lambda: {
                "waves": [{"wave": 7, "tasks": ["71", "72", "74"]}],
                "dependencies": {"24": ["21"], "71": [], "72": ["71"], "74": ["71"]},
            },
        )
        live = gate.build_dag_dependency()
        assert live["task24_depends_on_task23"] is False, (
            "依赖被删掉后字段仍为 True —— 该判据被写死了"
        )
        assert live["task72_depends_on_task71"] is True  # 对照：其余字段仍正确计算

    def test_task72_and_task74_depend_on_this_gate(self, report: Mapping[str, Any]) -> None:
        row = report["dag_dependency"]
        assert row["task72_depends_on_task71"] is True
        assert row["task74_depends_on_task71"] is True

    def test_this_gate_is_in_wave_seven(self, report: Mapping[str, Any]) -> None:
        assert report["dag_dependency"]["wave_of_task71"] == "7"


class TestProtocolSourceScan:
    def test_application_key_excludes_status_and_request_identity(
        self, prod: Mapping[str, Any], report: Mapping[str, Any]
    ) -> None:
        """独立现算 AST：`compute_application_key` 的入参不得含 status/request 身份/mtime。

        🔴 判据走 AST 取函数签名，**不** grep 符号名（教训 2）：grep `status` 会命中文档
        字符串、注释与任何叫 status 的局部变量。
        """
        models = prod["models"]
        tree = ast.parse(Path(models.__file__).read_text(encoding="utf-8"))
        node = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "compute_application_key"
        )
        params = sorted(
            [a.arg for a in node.args.kwonlyargs] + [a.arg for a in node.args.args]
        )
        assert params == report["protocol_source_scan"]["application_key_inputs"]
        assert params, "入参为空 —— 判据前提失效"
        for token in ("status", "request_id", "request_sequence", "last_applied", "mtime"):
            assert not any(token in name for name in params), f"入参里出现 {token}"
        assert report["protocol_source_scan"][
            "application_key_excludes_status_and_request_identity"
        ] is True

    def test_forbidden_input_detector_catches_planted_names(self, gate: Any) -> None:
        """喂植入的入参名，检测器必须逐个抓出来（对照组是干净入参）。

        🔴 只断「今天没有禁用入参」会让「把检测短路成 `if False`」变成等价变异（M25 首轮 GREEN）。
        名单本身也要写死真实目标（教训 16）—— 换掉 `status` 会让本条打红。
        """
        assert set(gate.FORBIDDEN_KEY_INPUT_TOKENS) == {
            "status",
            "request_id",
            "request_sequence",
            "last_applied",
            "mtime",
        }
        planted = [
            "wp_id",
            "callback_status",
            "origin_request_id",
            "effective_request_sequence",
            "room_last_applied_version_id",
            "file_mtime_ns",
        ]
        hits = gate.forbidden_key_inputs(planted)
        assert hits == sorted(
            [
                "callback_status",
                "effective_request_sequence",
                "file_mtime_ns",
                "origin_request_id",
                "room_last_applied_version_id",
            ]
        ), f"植入的禁用入参没被全部抓到: {hits}"
        # 对照组：干净入参不得被误报
        assert gate.forbidden_key_inputs(["wp_id", "room_id", "generation"]) == []

    def test_doc_key_is_mtime_free_measured_by_the_production_probe(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """doc_key 与 mtime 无关，判据是**真执行**探针而不是文本扫描。

        🔴 首轮实测：按「同一行既有 doc_key 又有 mtime」扫源码，在生产 room 模块上命中 15 行，
        全部是文档/注释里解释「doc_key 不含 mtime」的句子 ⇒ 文本扫描会把「已修好并写了说明」
        判成「仍有问题」（把错值当基线，假绿第③源的镜像）。现跑 + 报告双侧比对。
        """
        for source in (gate.build_protocol_source_scan(), report["protocol_source_scan"]):
            probe = source["doc_key_probe"]
            assert probe["doc_key_includes_mtime"] is False
            assert probe["doc_key_stable_across_mtime_change"] is True
            assert probe["doc_key_source_is_mtime_free"] is True
            assert probe["doc_key_rotates_with_generation"] is True
            assert probe["mtime_really_changed"] is True, (
                "探针没有真的改掉 mtime —— 「改了 mtime 后 key 不变」就没有信息量（对照组失效）"
            )
            assert probe["probe_dir_removed"] is True, (
                "doc_key 探针的临时目录没被清理 —— 正文要求测试数据完整复原/清理"
            )

    def test_doc_key_probe_is_the_production_single_source(
        self, prod: Mapping[str, Any], report: Mapping[str, Any]
    ) -> None:
        """逻辑级现算：直接调生产探针复现同一结论（不读报告，教训 17）。"""
        import shutil
        import tempfile

        models = prod["models"]
        rooms = __import__(
            models.__name__.rsplit(".", 1)[0] + ".rooms", fromlist=["probe_room_facts"]
        )
        assert report["protocol_source_scan"]["doc_key_probe"]["measured_by"] == (
            f"{rooms.__name__}:probe_room_facts"
        )
        tmp = Path(tempfile.mkdtemp(prefix="tmp_task71_guard_dockey_"))
        try:
            live = rooms.probe_room_facts(tmp_path=tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        assert live.doc_key_includes_mtime is False
        assert live.mtime_after != live.mtime_before

    def test_doc_key_field_is_computed_not_hardcoded(
        self, prod: Mapping[str, Any], gate: Any, monkeypatch: Any
    ) -> None:
        """让探针返回「doc_key 仍含 mtime」，门的字段必须翻转。

        🔴 只断「今天不含 mtime」会让「把该字段写死成 False」变成等价变异（M24 首轮 GREEN）。
        """
        models = prod["models"]
        rooms = __import__(
            models.__name__.rsplit(".", 1)[0] + ".rooms", fromlist=["probe_room_facts"]
        )
        real = rooms.probe_room_facts

        def _fake(**kwargs: Any) -> Any:
            import dataclasses
            import shutil
            import tempfile

            tmp = Path(tempfile.mkdtemp(prefix="tmp_task71_guard_fake_"))
            try:
                base = real(tmp_path=tmp)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            return dataclasses.replace(base, doc_key_source_is_mtime_free=False)

        monkeypatch.setattr(rooms, "probe_room_facts", _fake)
        live = gate.build_protocol_source_scan()
        assert live["doc_key_probe"]["doc_key_includes_mtime"] is True, (
            "探针报「仍含 mtime」时门的字段仍为 False —— 该字段被写死了"
        )
        assert live["doc_key_probe"]["doc_key_source_is_mtime_free"] is False


# ════════════════════════════════════════════════════════════════════════════
# §10 Property 落点 / 变异四态 / verdict
# ════════════════════════════════════════════════════════════════════════════


class TestPropertyLandings:
    def test_all_24_declared_properties_have_a_landing(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        assert report["properties"]["all_declared_have_landing"] is True
        assert report["properties"]["missing_landings"] == []
        assert report["properties"]["landings_not_declared"] == []
        assert report["properties"]["landing_count"] == 24

        # 🔴 反向自检：人为拿掉一条落点，门必须报缺失（否则「写死成 []」是等价变异）。
        victim = gate.DECLARED_PROPERTIES[0]
        planted = {k: v for k, v in gate._PROPERTY_LANDINGS.items() if k != victim}
        original = gate._PROPERTY_LANDINGS
        try:
            gate._PROPERTY_LANDINGS = planted
            live = gate.build_property_landings()
        finally:
            gate._PROPERTY_LANDINGS = original
        assert live["missing_landings"] == [victim]
        assert live["all_declared_have_landing"] is False

    def test_every_landing_has_tier_target_and_reason(self, report: Mapping[str, Any]) -> None:
        for row in report["properties"]["rows"]:
            assert row["tier"] in ("verified_here", "structural_side_only", "unverifiable")
            assert str(row["landed_on"]).strip(), f"Property {row['property']} 缺落点"
            assert str(row["why"]).strip(), f"Property {row['property']} 缺理由"
            assert str(row["design_title"]).strip(), (
                f"Property {row['property']} 在 design.md 里没有标题"
            )

    def test_every_unverified_property_names_an_owner(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        assert report["properties"]["unverified_without_owner"] == []
        assert report["properties"]["every_unverified_has_owner"] is True

        # 反向自检：清空一条非 verified_here 的 owner，门必须报出来。
        victim = next(
            number
            for number, landing in gate._PROPERTY_LANDINGS.items()
            if landing["tier"] != "verified_here"
        )
        planted = {
            number: ({**landing, "owner_if_unverified": ""} if number == victim else landing)
            for number, landing in gate._PROPERTY_LANDINGS.items()
        }
        original = gate._PROPERTY_LANDINGS
        try:
            gate._PROPERTY_LANDINGS = planted
            live = gate.build_property_landings()
        finally:
            gate._PROPERTY_LANDINGS = original
        assert live["unverified_without_owner"] == [victim]
        assert live["every_unverified_has_owner"] is False

    def test_tier_histogram_is_not_all_one_bucket(self, report: Mapping[str, Any]) -> None:
        """三档都要有落点 —— 全落一档说明档位是装饰。"""
        histogram = report["properties"]["tier_histogram"]
        assert len(histogram) >= 2
        assert histogram.get("verified_here", 0) > 0, "0 条真跑验过 ⇒ 档位没有区分力"
        assert histogram.get("unverifiable", 0) > 0, "0 条不可验 ⇒ 与实测环境不符"


class TestMutationStateMachine:
    def test_four_states_and_no_fifth(self, gate: Any) -> None:
        assert set(gate.MUTATION_STATES) == {"RED", "GREEN", "ANCHOR-MISS", "WRONG-TEST"}
        assert len(gate.MUTATION_STATES) == 4

    def test_report_explains_why_exit_code_is_not_evidence(
        self, report: Mapping[str, Any]
    ) -> None:
        row = report["mutation_state_machine"]
        assert set(row["state_semantics"]) == set(row["state_vocabulary"])
        assert "ERROR" in row["error_counts_as_hit"]
        assert "GREEN" in row["error_counts_as_hit"]

    def test_mutation_script_exists_and_declares_mutations(
        self, report: Mapping[str, Any]
    ) -> None:
        row = report["mutation_state_machine"]
        assert row["mutation_script_present"] is True
        assert row["mutation_count"] > 0
        assert row["script_has_check_anchors"] is True

    def test_mutation_script_reads_and_writes_bytes(self, report: Mapping[str, Any]) -> None:
        """`read_text`/`write_text` 的换行翻译会让逐文件 md5 复原校验必失败。"""
        assert report["mutation_state_machine"]["script_reads_and_writes_bytes"] is True


class TestVerdict:
    def test_vocabulary_is_exactly_three(self, gate: Any) -> None:
        assert set(gate.VERDICT_VOCABULARY) == {"passed", "failed", "unverifiable"}

    def test_state_is_unverifiable_and_says_why(self, report: Mapping[str, Any]) -> None:
        verdict = report["verdict"]
        assert verdict["state"] in verdict["state_vocabulary"]
        assert verdict["state"] == "unverifiable"
        assert verdict["structural_errors"] == [], verdict["structural_errors"]
        assert verdict["capacity_real_load_unverifiable"] is True
        assert "UNVERIFIABLE" in verdict["means"]

    def test_zero_behaviour_arms_would_be_unverifiable_not_passed(self, gate: Any) -> None:
        """合成算例：0 条行为臂时必须 unverifiable。「零证据全过」不是通过（Property 71）。

        🔴 今天恰好有真实的 UNVERIFIABLE 欠账会遮住这条分支，所以必须造一个「一切干净、
        只是一条臂都没跑」的合成世界把它单独逼出来（教训 19）。
        """
        skeleton = _clean_skeleton(gate)
        skeleton["behaviour"]["arms_agreeing"] = 0
        skeleton["behaviour"]["arm_count"] = 0
        verdict = gate.build_verdict(skeleton)
        assert verdict["state"] == "unverifiable"
        assert "零证据" in verdict["means"]

    def test_a_clean_world_with_no_debts_would_pass(self, gate: Any) -> None:
        """反向自检：一切干净且无欠账时必须 passed —— 否则 verdict 恒 unverifiable（恒真）。"""
        verdict = gate.build_verdict(_clean_skeleton(gate))
        assert verdict["state"] == "passed", verdict["structural_errors"]

    def test_a_planted_structural_error_flips_to_failed(self, gate: Any) -> None:
        skeleton = _clean_skeleton(gate)
        skeleton["task_declarations"]["properties_match"] = False
        assert gate.build_verdict(skeleton)["state"] == "failed"

    def test_a_disagreeing_arm_flips_to_failed(self, gate: Any) -> None:
        skeleton = _clean_skeleton(gate)
        skeleton["behaviour"]["disagreeing_arms"] = ["t71_probe"]
        assert gate.build_verdict(skeleton)["state"] == "failed"

    def test_a_leaked_secret_flips_to_failed(self, gate: Any) -> None:
        skeleton = _clean_skeleton(gate)
        skeleton["redaction"]["no_planted_secret_survives"] = False
        skeleton["redaction"]["leaked_planted_secrets"] = ["bearer_token"]
        assert gate.build_verdict(skeleton)["state"] == "failed"

    def test_unrestored_data_flips_to_failed(self, gate: Any) -> None:
        skeleton = _clean_skeleton(gate)
        skeleton["data_restoration"]["restored"] = False
        assert gate.build_verdict(skeleton)["state"] == "failed"

    def test_cross_signature_hit_flips_to_failed(self, gate: Any) -> None:
        """拒绝理由互相命中时 verdict 必须变 failed（否则死判据可以长期存在）。"""
        skeleton = _clean_skeleton(gate)
        skeleton["behaviour"]["cross_signature_hits"] = [
            {"signature_of": "a", "also_hits": "b", "hits": ["x"]}
        ]
        assert gate.build_verdict(skeleton)["state"] == "failed"

    def test_missing_observation_flips_to_failed(self, gate: Any) -> None:
        skeleton = _clean_skeleton(gate)
        skeleton["behaviour"]["missing_observations"] = ["t71_probe"]
        assert gate.build_verdict(skeleton)["state"] == "failed"

    def test_duplicate_arm_write_flips_to_failed(self, gate: Any) -> None:
        skeleton = _clean_skeleton(gate)
        skeleton["behaviour"]["duplicate_arm_writes"] = ["t71_probe"]
        assert gate.build_verdict(skeleton)["state"] == "failed"

    def test_forbidden_claims_are_listed(self, report: Mapping[str, Any]) -> None:
        claims = report["verdict"]["forbidden_claims"]
        assert any("OO probe" in claim for claim in claims)
        assert any("CapacityMeasurement" in claim for claim in claims)
        assert any("退出码" in claim for claim in claims)

    def test_every_facet_has_a_conclusion(self, report: Mapping[str, Any]) -> None:
        conclusions = report["verdict"]["facet_conclusions"]
        assert set(conclusions) == {
            "capacity",
            "fault_injection",
            "retention",
            "redaction",
            "alerting",
            "data_restoration",
        }
        for name, text in conclusions.items():
            assert str(text).strip(), f"{name} 缺结论"


_CAPACITY_CACHE: dict[str, Any] = {}


def gate_capacity(gate: Any) -> Mapping[str, Any]:
    """现跑一次容量面并在进程内缓存（昂贵对象只算一次）。"""
    if "value" not in _CAPACITY_CACHE:
        _CAPACITY_CACHE["value"] = gate.build_capacity()
    return _CAPACITY_CACHE["value"]


def _clean_skeleton(gate: Any) -> dict[str, Any]:
    """「一切干净」的合成世界。

    🔴 逐项反事实必须先造这个（教训 19）：真实报告本就带真实欠账，单项变异会被别的失败
    掩盖，于是「植入 X 会让 verdict 变 failed」这条判据在真实报告上永远测不出来。
    """
    return {
        "task_declarations": {"properties_match": True, "sub_bullet_count_match": True},
        "mutation_coverage": {
            "unresolved_refs": [],
            "disagreeing_refs": [],
            "unverifiable_without_owner": [],
            "targets_with_any_unverifiable_evidence": [],
            "targets_with_only_unverifiable_evidence": [],
            "target_count": 3,
        },
        "coverage_tiers": {"broken_targets": []},
        "behaviour": {
            "harness_error": None,
            "apply_errors": [],
            "probe_errors": {},
            "disagreeing_arms": [],
            "missing_observations": [],
            "duplicate_arm_writes": [],
            "cross_signature_hits": [],
            "facets_missing_control": [],
            "arms_agreeing": 3,
            "arm_count": 3,
        },
        "behaviour_facets": {"retention": {"decision_count": 1}},
        "capacity": {
            "profile_matches_requirements": True,
            "fail_closed_without_execution_record": {"raised": True},
            "evaluator_arms_disagreeing": [],
            "real_load_execution": {"tier": "EXECUTED", "owner_task": "71"},
        },
        "redaction": {
            "no_planted_secret_survives": True,
            "leaked_planted_secrets": [],
            "arms_disagreeing": [],
        },
        "alerting": {
            "three_way_clean": True,
            "validate_registry_problems": [],
            "rules_disagreeing": [],
            "conditions_without_rule": [],
            "rule_count": 17,
        },
        "fault_injection": {"injections_disagreeing": [], "injections_agreeing": ["disk"]},
        "data_restoration": {
            "restored": True,
            "drifted_tables": {},
            "own_schema_left": 0,
            "temp_artifact_root_removed": True,
        },
        "properties": {
            "all_declared_have_landing": True,
            "every_unverified_has_owner": True,
            "tiers_out_of_vocabulary": [],
            "unverified_without_owner": [],
            "missing_landings": [],
            "landing_count": 3,
            "verified_here_count": 3,
        },
        "counterfactual_arms": {"all_arms_sensitive": True, "arms_not_changing_conclusion": []},
        "forward_recompute": {
            "all_agree": True,
            "has_positive_case": True,
            "disagreeing_cases": [],
        },
        "dag_dependency": {"task24_depends_on_task23": True, "task72_depends_on_task71": True},
        "deletion_gate": {
            "task67_must_not_require_zero_stale": {"agrees": True},
            "task67_must_not_claim_eligibility": {"agrees": True},
            "task72_stage_a_must_not_require_unreachable_zero": {"agrees": True},
            "smoke_cannot_restore_verified": {"agrees": True},
        },
        "mutation_state_machine": {
            "mutation_script_present": True,
            "mutation_ids": ["M01"],
            "script_reads_and_writes_bytes": True,
        },
        "blocking_points": [{"id": "BP-71-1"}],
        "multi_resolver_adjudication": {"criterion_passes": True, "multi_resolver_count": 0},
    }


# ════════════════════════════════════════════════════════════════════════════
# §11 BP 编号 / 守卫落位 / 产物跟踪
# ════════════════════════════════════════════════════════════════════════════


def gate_blocking_points(gate: Any, report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """用报告自身的各面**现跑**一次阻塞登记构造。

    🔴 只读报告时改错某个 BP 编号磁盘不会变（M46 首轮 WRONG-TEST）。
    """
    return gate.build_blocking_points(
        coverage=report["mutation_coverage"],
        capacity=report["capacity"],
        fault=report["fault_injection"],
        multi_resolver=report["multi_resolver_adjudication"],
        bp681=report["bp_68_1_recheck"],
        deletion=report["deletion_gate"],
        restoration=report["data_restoration"],
        redaction_facts=report["redaction"],
        lock_impact=report["upstream_lock_impact"],
    )


class TestBlockingPoints:
    def test_every_id_matches_bp_71_n(self, gate: Any, report: Mapping[str, Any]) -> None:
        assert report["blocking_points"], "阻塞登记为空 —— 覆盖计数必须断言非空"
        live = gate_blocking_points(gate, report)
        assert live, "现跑的阻塞登记为空"
        for point in list(report["blocking_points"]) + list(live):
            assert gate.BP_ID_PATTERN.fullmatch(str(point["id"])), (
                f"BP 编号 {point['id']!r} 不匹配 BP-71-\\d+"
            )
        # 反向自检：编号锁必须真的拒掉非法编号（全部合法 ⇒ 放宽成 `.*` 是等价变异）。
        for illegal in ("BP71-2", "BP-70-1", "BP-71-", "bp-71-1", "BP-71-1x"):
            assert not gate.BP_ID_PATTERN.fullmatch(illegal), (
                f"编号锁放行了非法编号 {illegal!r}"
            )

    def test_ids_are_unique_and_dense(self, gate: Any, report: Mapping[str, Any]) -> None:
        for points in (report["blocking_points"], gate_blocking_points(gate, report)):
            ids = [str(point["id"]) for point in points]
            assert len(set(ids)) == len(ids)
            numbers = sorted(int(i.rsplit("-", 1)[1]) for i in ids)
            assert numbers == list(range(1, len(numbers) + 1)), f"BP 编号不连续: {numbers}"

    def test_every_point_carries_measurement_owner_and_disposition(
        self, report: Mapping[str, Any]
    ) -> None:
        for point in report["blocking_points"]:
            assert point.get("measured") not in (None, {}, []), f"{point['id']} 缺实测"
            assert str(point.get("measured_how") or "").strip(), f"{point['id']} 缺测量方式"
            assert str(point.get("owner_task") or "").strip(), f"{point['id']} 缺 owner"
            assert str(point.get("why_not_fixed_here") or "").strip()
            assert str(point.get("disposition") or "").strip()
            assert str(point.get("relation_to_upstream") or "").strip()

    def test_bp_71_1_is_the_multi_resolver_blocker(self, report: Mapping[str, Any]) -> None:
        point = next(p for p in report["blocking_points"] if p["id"] == "BP-71-1")
        assert point["measured"]["multi_resolver_count"] == 4
        assert point["owner_task"] == "36"
        assert point["disposition"] == "仍阻塞"


class TestGuardPlacement:
    def test_guard_lives_outside_the_upstream_census_dir(self, gate: Any) -> None:
        """本文件必须**不在**上游的目录普查范围内（BP-69-6）。判据现算，不写在注释里。"""
        here = str(Path(__file__).resolve().relative_to(REPO)).replace("\\", "/")
        assert here == GUARD_REL
        assert not here.startswith(f"{gate.UPSTREAM_CENSUS_DIR}/"), (
            f"守卫落在上游的目录普查范围 {gate.UPSTREAM_CENSUS_DIR} 内 —— 会打红它 1~3 条守卫"
        )

    def test_census_dir_literal_is_read_from_the_upstream_gate(self, gate: Any) -> None:
        """普查目录字面量必须与上游门里的**真实**值一致（不能自说自话）。"""
        assert UPSTREAM_GATE.is_file()
        text = UPSTREAM_GATE.read_text(encoding="utf-8", errors="replace")
        assert gate.UPSTREAM_CENSUS_DIR in text, (
            "上游门里找不到普查目录字面量 —— 本判据的前提已漂移，需重新确认规避法"
        )

    def test_guard_file_avoids_upstream_surface_patterns(self) -> None:
        """本文件必须对上游的辐射面 pattern **零命中**（BP-70-8）。

        pattern **从上游门源码现读**，不在本文件抄第二份（抄的那份在上游改 pattern 后静静
        过期）。本文件刻意连举例都不写出那些字面量 —— 写出来本条就会自己打红自己。
        """
        text = UPSTREAM_GATE.read_text(encoding="utf-8", errors="replace")
        block = re.search(r"_SURFACE_PATTERNS[^=]*=\s*\((.*?)\n\)", text, re.S)
        assert block is not None, "上游门里找不到 _SURFACE_PATTERNS —— 本判据的前提已漂移"
        patterns = re.findall(
            r'\(\s*"[^"]+"\s*,\s*r?"((?:[^"\\]|\\.)*)"\s*\)', block.group(1)
        )
        assert len(patterns) >= 4, f"只解析出 {len(patterns)} 条 pattern —— 解析失效"

        mine = Path(__file__).read_text(encoding="utf-8")
        hits = {
            pattern: len(re.findall(pattern, mine))
            for pattern in patterns
            if re.search(pattern, mine)
        }
        assert not hits, (
            f"本守卫文件命中了上游的辐射面 pattern {hits} —— 会顶掉它的 digest 并打红 3 条"
            "（BP-70-8）。生产模块请经 `gate._production()` 取，路径用 `__name__` 现算。"
        )

        # 反向自检：pattern 必须真的能命中**上游自己的**辐射面成员，否则「零命中」只是因为
        # pattern 解析错了（重言式）。
        sample = UPSTREAM_GATE
        sample_text = sample.read_text(encoding="utf-8", errors="replace")
        assert any(re.search(pattern, sample_text) for pattern in patterns), (
            "解析出的 pattern 对上游门自己也不命中 —— pattern 解析失效，「零命中」不构成证据"
        )

    def test_production_modules_come_from_the_gate_accessor(self, gate: Any) -> None:
        """生产模块的 dotted name 由 `__name__` 现算，不在本文件抄字面量。"""
        prod = gate._production()
        for key in ("capacity", "retention", "redaction", "alerting", "models"):
            assert key in prod, f"访问器里缺 {key}"
            assert prod[key].__name__.endswith(key) or key in prod[key].__name__

    def test_report_records_the_placement_rationale(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """现跑 + 报告双侧：只读报告时把该字段谎报磁盘不会变（教训 17）。"""
        for surface in (gate.radiation_surface(), report["radiation_surface"]):
            assert surface["own_guard_path"] == GUARD_REL
            assert surface["own_guard_outside_census_dir"] is True
            assert surface["scanned_test_files"] > 0
            assert surface["referencing_test_file_count"] > 0

    def test_upstream_lock_impact_is_measured_and_owned(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """本门守卫对上游锁的影响必须**现算**出来并点名 owner，不许含糊过去。

        实测：任务 70 的 `--check` **只**因为本文件的存在而变红（把它移出 `backend/tests`
        后 rc=0、放回 rc=1）。根因是它把 `backend/tests` 全树 test 文件计数锁进了逐字节比对，
        换目录（BP-69-6 的规避法）与不写模块路径字面量（BP-70-8 的规避法）都躲不开。
        """
        for row in (gate.upstream_lock_impact(), report["upstream_lock_impact"]):
            assert row["task70_lock_goes_stale_because_of_this_gate"] is True
            assert row["own_guard_is_in_task70_surface"] is True
            assert row["own_guard_matched_subjects"], "本文件命中的 subject 清单为空 —— 判据前提漂移"
            assert row["owner_task"] == "70"
            assert (
                row["task70_scanned_test_files_live"]
                == row["task70_scanned_test_files_on_disk"] + 1
            ), (
                "全树 test 文件计数的增量不是 1 —— 说明还有别的新增测试文件，需重新归因"
            )
            assert str(row["isolation_method"]).strip()
            assert str(row["why_unavoidable"]).strip()

    def test_all_four_upstream_locks_are_declared_with_baselines(self, gate: Any) -> None:
        """四把上游锁逐条登记基线（少一条即无法判「是否新增红」）。"""
        assert len(gate.UPSTREAM_LOCKS) == 4
        tasks = {task for _, task, _, _ in gate.UPSTREAM_LOCKS}
        assert tasks == {"67", "68", "69", "70"}
        for guard, task, passed, failed in gate.UPSTREAM_LOCKS:
            assert (REPO / guard).is_file(), f"上游锁 {guard} 不在磁盘上"
            assert passed > 0, f"任务 {task} 的基线通过数为 0"
            assert failed >= 0

    def test_known_preexisting_red_is_task69_not_ours(self, report: Mapping[str, Any]) -> None:
        """任务 69 的那一条红是 BP-70-6 的复选框根因，本门起手基线即为红。"""
        known = report["upstream_lock_impact"]["known_preexisting_red"]
        assert len(known) == 1
        path, why = next(iter(known.items()))
        assert "task69" in path
        assert "BP-70-6" in why

    def test_artifact_git_status_is_reported_for_every_product(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """四件套逐个登记跟踪状态（`??` 会让 CI job 在干净 checkout 下必挂）。"""
        status = report["artifact_git_status"]
        for path in (GATE_REL, REPORT_REL, GUARD_REL, MUTATE_REL):
            assert path in status, f"{path} 未登记 git 状态"
            assert status[path] != "missing-on-disk", f"{path} 不在磁盘上"

        # 反向自检：四个产物今天都在磁盘上 ⇒ 把「先判存在」短路掉是等价变异。
        absent = "backend/data/_task71_guard_probe_definitely_absent.json"
        assert not (REPO / absent).exists()
        probed = gate.git_porcelain([absent])
        assert probed[absent] == "missing-on-disk", (
            f"不存在的路径被报成 {probed[absent]!r} —— 「产物还没写出来」会被伪装成"
            "「已跟踪且干净」"
        )
