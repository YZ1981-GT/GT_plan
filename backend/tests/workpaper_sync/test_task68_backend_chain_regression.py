"""Task 68 后端全链独立回归门的守卫。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 7 Task 68
被验产物：``backend/scripts/check/check_task68_backend_chain_independent_regression.py``
        ``backend/data/workpaper_sync_task68_backend_chain_regression.json``

═══ 这些判据在防什么 ═══

1. **空集恒真**（假绿第⑥源）—— 生产 `public` schema 里 forcesave request / application /
   operation / delivery / room / scope index / content version 等表实测 **0 行**。只写
   「没有违反行」的判据在 0 行上恒真。故每条不变量都必须**同时**给出 schema 侧（DDL 逐片段）
   与行为侧（scratch schema 真造行）结论，且守卫逐格断言两侧都真的被度量过。
2. **判据是重言式** —— 反事实多臂（逐条在内存里删掉一条 DDL 要求，结论必须翻）+ 正向重算
   （把记录里的输入原样喂回实现比对）。只有多臂会漏掉「恒真」，只有重算会漏掉「不度量」。
3. **additive 注入即死代码** —— 声明的每条行为臂都必须有探针真的在写观测；声明与探针双向锁死。
4. **fail-open** —— 库读不到 / 采集失败必须让判据红，不得降级成「没有违反项所以通过」。
5. **自证** —— 正文逐字「不得由实现任务自证」。守卫断言本门不 import 任何实现任务的守卫，
   且对未能重新表达的 Property 如实标弱并点名 owner。
6. **越界** —— 本任务不冒充真实 OO probe / evidence。守卫断言整份报告不含任何「场景通过」类
   声明，且 evidence 两张表在 scratch schema 里也是 0 行。
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

_THIS = Path(__file__).resolve()
REPO = _THIS.parents[3]
BACKEND = REPO / "backend"
GATE_PATH = (
    BACKEND / "scripts" / "check" / "check_task68_backend_chain_independent_regression.py"
)
REPORT_PATH = BACKEND / "data" / "workpaper_sync_task68_backend_chain_regression.json"

if str(BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(BACKEND))


def _load_gate() -> Any:
    spec = importlib.util.spec_from_file_location("task68_gate", GATE_PATH)
    assert spec and spec.loader, f"无法加载 {GATE_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules["task68_gate"] = module
    spec.loader.exec_module(module)
    return module


GATE = _load_gate()


# ════════════════════════════════════════════════════════════════════════════
# fixtures
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def report() -> dict[str, Any]:
    assert REPORT_PATH.exists(), (
        f"缺少 {REPORT_PATH.relative_to(REPO).as_posix()} —— 先跑 "
        "`--write --run-suites`。报告缺失时**不得** skip：那会把「没验」伪装成「没问题」。"
    )
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def catalog(report: dict[str, Any]) -> Any:
    """从报告记录还原 DDL 目录 —— 正向重算与反事实多臂都基于它。"""
    return GATE.catalog_from_record(report["schema_catalog"])


@pytest.fixture(scope="module")
def observations(report: dict[str, Any]) -> dict[str, Any]:
    obs = dict(report["behaviour_harness"]["observations"])
    obs["__harness__"] = {
        "error": report["behaviour_harness"]["error"],
        "schema": report["behaviour_harness"]["schema_prefix"],
    }
    return obs


@pytest.fixture(scope="module")
def gate_ast() -> ast.Module:
    return ast.parse(GATE_PATH.read_text(encoding="utf-8"))


_ALL_INVARIANTS = GATE.ALL_INVARIANTS


def _clean_suite_record(report: dict[str, Any]) -> dict[str, Any]:
    """合成一份「一切干净」的 suite 记录：只有已登记的既存红，计数逐项对上。

    🔴 存在的理由：真实记录里同时存在多种红，`passed` 早已为假 ⇒ 任何「去掉某一项判据」
    的变异都不会改变结论（假绿：变异被别的失败掩盖）。要证明某一项**单独**参与判定，
    必须先造一个只差那一项的对照世界。
    """
    failed: list[str] = []
    errors: list[str] = []
    for index, entry in enumerate(GATE.PREEXISTING_FAILURES):
        path = str(entry["file"])
        failed += [f"{path}::test_synthetic_{index}_{i}" for i in range(int(entry["failed"]))]
        errors += [f"{path}::test_synthetic_err_{index}_{i}" for i in range(int(entry["errors"]))]
    return {
        **dict(report["suite_run"]),
        "failed_nodeids": failed,
        "error_nodeids": errors,
        "counts": {
            "passed": int(report["suite_run"]["counts"].get("passed", 0)),
            "failed": len(failed),
            "errors": len(errors),
            "xfailed": int(report["suite_run"]["counts"].get("xfailed", 0)),
        },
        "files_digest": report["radiation_surface"]["digest"],
    }


def _clean_report(report: dict[str, Any]) -> dict[str, Any]:
    """把报告压成「一切干净」的形态，供判定的逐项反事实用。"""
    clean = json.loads(json.dumps(report))
    clean["behaviour_harness"]["error"] = None
    clean["behaviour_harness"]["probe_errors"] = {}
    clean["schema_catalog"]["readable"] = True
    for row in clean["invariants"]:
        row["passed"] = True
    for row in clean["endpoint_checks"]:
        row["passed"] = True
    clean["properties"]["structural_errors"] = []
    clean["restoration"]["restored"] = True
    clean["suite_verdict"] = GATE.evaluate_suite_run(
        _clean_suite_record(report), clean["radiation_surface"]
    )
    return clean


# ════════════════════════════════════════════════════════════════════════════
# 一、守卫自证（判据本身不能失效）
# ════════════════════════════════════════════════════════════════════════════


class TestGuardSelfChecks:
    def test_vocabularies_are_closed_non_empty_and_distinct(self) -> None:
        for name, vocabulary in (
            ("BEHAVIOUR_STATES", GATE.BEHAVIOUR_STATES),
            ("SCHEMA_STATES", GATE.SCHEMA_STATES),
            ("REQUIRED_INVARIANT_FACETS", GATE.REQUIRED_INVARIANT_FACETS),
            ("DECLARED_PROPERTIES", GATE.DECLARED_PROPERTIES),
            ("REQUIRED_ENDPOINTS", GATE.REQUIRED_ENDPOINTS),
            ("PREEXISTING_FAILURES", GATE.PREEXISTING_FAILURES),
        ):
            assert vocabulary, f"{name} 为空 —— 空词表让所有成员判据恒真"
            flat = [json.dumps(item, sort_keys=True, default=str) for item in vocabulary]
            assert len(flat) == len(set(flat)), f"{name} 有重复项: {name}"
        assert "verified_on_rows" in GATE.BEHAVIOUR_STATES
        assert "not_enforced_at_schema" in GATE.SCHEMA_STATES

    def test_bp_id_regex_is_task_scoped_and_rejects_the_global_form(self) -> None:
        assert GATE.BP_ID_RE.fullmatch("BP-68-1"), "task-scoped 形态必须被接受"
        assert GATE.BP_ID_RE.fullmatch("BP-68-12"), "两位数编号必须被接受"
        assert not GATE.BP_ID_RE.fullmatch("BP-1"), (
            "全局 `BP-NN` 已被 Tasks 60/61/63/64 重复占用（同号不同义），接回去只会制造第三份冲突"
        )
        assert not GATE.BP_ID_RE.fullmatch("BP-67-1"), "别的任务的编号不得混进本报告"

    def test_invariant_refuses_to_exist_without_a_schema_side(self) -> None:
        arm = GATE.BehaviourArm("x", "对照组", "accepted")
        neg = GATE.BehaviourArm("y", "否定臂", "rejected", ("frag",))
        with pytest.raises(GATE.Task68GateError, match="schema"):
            GATE.Invariant(
                check_id="no_schema",
                sub_bullet=2,
                statement="s",
                measured_by="m",
                properties=(18,),
                requirements=("5.5",),
                arms=(arm, neg),
            )

    def test_invariant_refuses_to_exist_without_behaviour_arms(self) -> None:
        with pytest.raises(GATE.Task68GateError, match="0 行"):
            GATE.Invariant(
                check_id="no_arms",
                sub_bullet=2,
                statement="s",
                measured_by="m",
                properties=(18,),
                requirements=("5.5",),
                schema_requirements=(GATE.DdlRequirement("constraint", "t", "c"),),
            )

    def test_invariant_refuses_to_exist_without_a_control_arm(self) -> None:
        neg = GATE.BehaviourArm("only_negative", "否定臂", "rejected", ("frag",))
        with pytest.raises(GATE.Task68GateError, match="对照组"):
            GATE.Invariant(
                check_id="no_control",
                sub_bullet=2,
                statement="s",
                measured_by="m",
                properties=(18,),
                requirements=("5.5",),
                schema_requirements=(GATE.DdlRequirement("constraint", "t", "c"),),
                arms=(neg,),
            )

    def test_invariant_refuses_to_exist_with_only_a_control_arm(self) -> None:
        pos = GATE.BehaviourArm("only_control", "对照组", "accepted")
        with pytest.raises(GATE.Task68GateError, match="否定"):
            GATE.Invariant(
                check_id="control_only",
                sub_bullet=2,
                statement="s",
                measured_by="m",
                properties=(18,),
                requirements=("5.5",),
                schema_requirements=(GATE.DdlRequirement("constraint", "t", "c"),),
                arms=(pos,),
            )

    def test_rejected_arm_refuses_to_exist_without_a_signature(self) -> None:
        with pytest.raises(GATE.Task68GateError, match="reject_signature"):
            GATE.BehaviourArm("bad", "只比抛没抛", "rejected")

    def test_measure_arm_refuses_to_exist_without_expectations(self) -> None:
        with pytest.raises(GATE.Task68GateError, match="空期望恒真"):
            GATE.BehaviourArm("bad", "空期望", "measure")

    def test_ddl_requirement_detects_a_missing_fragment_not_just_presence(self) -> None:
        snapshot = GATE.SchemaCatalog(readable=True)
        snapshot.constraints[("t", "uq_x")] = {
            "definition": "UNIQUE (room_id, generation, kind, idempotency_key)",
            "contype": "u",
        }
        present_only = GATE.DdlRequirement("constraint", "t", "uq_x")
        assert present_only.evaluate(snapshot)["satisfied"], "对照组：同名对象存在"
        with_columns = GATE.DdlRequirement(
            "constraint", "t", "uq_x", ("initiated_by_participant_id",)
        )
        verdict = with_columns.evaluate(snapshot)
        assert verdict["present"] is True
        assert verdict["satisfied"] is False, (
            "少一列 `initiated_by_participant_id` 时索引仍叫 `uq_x` —— 只查存在的判据会放过"
            "「跨 participant 复用同一 Idempotency-Key 不再 409」这种真实缺陷（教训 16）"
        )
        assert verdict["missing_fragments"] == ["initiated_by_participant_id"]

    def test_absent_column_requirement_is_not_the_same_as_not_null(self) -> None:
        snapshot = GATE.SchemaCatalog(readable=True)
        snapshot.columns[("op", "application_key")] = {"is_nullable": "NO", "data_type": "text"}
        absent = GATE.DdlRequirement("absent_column", "op", "application_key")
        assert absent.evaluate(snapshot)["satisfied"] is False, (
            "Property 64：`application_key` 只能存在于 content application；operation 上出现"
            "同名列即失败 —— 这条不能被 not_null 判据顶替"
        )
        empty = GATE.SchemaCatalog(readable=True)
        assert absent.evaluate(empty)["satisfied"] is True

    def test_db_unreadable_never_reads_as_passed(self) -> None:
        broken = GATE.SchemaCatalog(readable=False, error="boom")
        for invariant in _ALL_INVARIANTS:
            row = invariant.evaluate(broken, {})
            assert row["passed"] is False, f"{invariant.check_id} 在库不可读时判了通过"
            assert row["schema_side"]["state"] == "db_unreadable"
            assert row["behaviour_side"]["state"] == "harness_error"

    def test_missing_observation_is_not_a_pass(self) -> None:
        arm = GATE.BehaviourArm("ghost", "声明了却没探针", "accepted")
        verdict = GATE.evaluate_arm(arm, None)
        assert verdict["agrees"] is False
        assert verdict["state"] == "missing_observation", (
            "additive 注入即死代码：声明的臂没有观测时必须红，不能当「没验到就算过」"
        )

    def test_rejected_arm_needs_every_declared_fragment(self) -> None:
        arm = GATE.BehaviourArm("r", "两片段", "rejected", ("必须 state=durable", "实得 staged"))
        partial = GATE.evaluate_arm(
            arm, {"accepted": False, "rejection": "23514||必须 state=durable，实得 quarantined"}
        )
        assert partial["agrees"] is False, (
            "两臂共用同一条 RAISE 文案时，只命中一半片段就算过会让它们互相冒充"
        )
        full = GATE.evaluate_arm(
            arm, {"accepted": False, "rejection": "23514||必须 state=durable，实得 staged"}
        )
        assert full["agrees"] is True

    def test_rejected_arm_that_was_accepted_is_a_failure(self) -> None:
        arm = GATE.BehaviourArm("r", "应被拒", "rejected", ("frag",))
        verdict = GATE.evaluate_arm(arm, {"accepted": True, "rejection": None})
        assert verdict["agrees"] is False

    def test_measure_arm_compares_every_declared_key_separately(self) -> None:
        arm = GATE.BehaviourArm(
            "m", "收敛", "measure", expect_measure={"primary": 1, "stranded": 0}
        )
        good = GATE.evaluate_arm(arm, {"measured": {"primary": 1, "stranded": 0}})
        assert good["agrees"] is True
        bad = GATE.evaluate_arm(arm, {"measured": {"primary": 1, "stranded": 2}})
        assert bad["agrees"] is False, "集合成员判据要分开断言（教训 3）"
        assert set(bad["mismatched"]) == {"stranded"}
        missing = GATE.evaluate_arm(arm, {"measured": {"primary": 1}})
        assert missing["agrees"] is False, "缺键不能算过（缺键 = 没度量）"

    def test_cross_signature_check_only_flags_differing_reasons(self) -> None:
        same_a = GATE.BehaviourArm("a", "同因不同形态", "rejected", ("uq_x",))
        same_b = GATE.BehaviourArm("b", "同因不同形态", "rejected", ("uq_x",))
        obs = {
            "a": {"accepted": False, "rejection": "uq_x"},
            "b": {"accepted": False, "rejection": "uq_x"},
        }
        assert GATE._cross_signature_hits((same_a, same_b), obs) == [], (
            "两臂**故意**声明同一条约束（同五元组重放 vs 换 payload）是合法的"
        )
        diff_a = GATE.BehaviourArm("a", "理由甲", "rejected", ("ck_alpha",))
        diff_b = GATE.BehaviourArm("b", "理由乙", "rejected", ("ck_beta",))
        obs2 = {
            "a": {"accepted": False, "rejection": "ck_alpha"},
            "b": {"accepted": False, "rejection": "ck_alpha and ck_beta"},
        }
        hits = GATE._cross_signature_hits((diff_a, diff_b), obs2)
        assert hits, (
            "声明了**不同**理由却互相命中 ⇒ 其中一条度量的不是它自称的那条约束（教训 1）"
        )
        assert hits[0]["signature_of"] == "a"

    def test_deferred_property_without_owner_is_a_structural_error(self) -> None:
        """第三档分支必须真的会红 —— 用合成输入证明，而不是预填死条目。"""
        surface = {"digest": "synthetic-empty", "files": {}}
        landings = GATE.build_property_landings([], [], surface, {"state": "executed"})
        assert landings["tiers"]["deferred"] == len(GATE.DECLARED_PROPERTIES)
        kinds = {e["kind"] for e in landings["structural_errors"]}
        assert kinds == {"property_without_landing_or_declared_owner"}
        assert len(landings["structural_errors"]) == len(GATE.DECLARED_PROPERTIES), (
            "48 条全无落点时必须逐条报结构错误，不能只报一条"
        )


# ════════════════════════════════════════════════════════════════════════════
# 二、本门只读生产、只写自己的报告
# ════════════════════════════════════════════════════════════════════════════


def _dotted(node: ast.expr) -> str | None:
    return GATE.dotted_name(node)


class TestGateOnlyReads:
    def test_every_declared_sql_is_read_only(self) -> None:
        assert GATE.READONLY_SQL_STATEMENTS, "只读 SQL 清单为空 ⇒ 无从核查只读承诺"
        for statement in GATE.READONLY_SQL_STATEMENTS:
            head = statement.strip().split()[0].upper()
            assert head == "SELECT", f"清单里出现非 SELECT 语句: {statement[:80]}"
            for forbidden in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE"):
                assert forbidden not in statement.upper(), f"只读 SQL 里出现 {forbidden}"

    def test_the_declared_readonly_list_contains_the_real_targets(self) -> None:
        joined = "\n".join(GATE.READONLY_SQL_STATEMENTS)
        for target in (
            "pg_get_constraintdef",
            "pg_get_indexdef",
            "pg_get_triggerdef",
            "pg_get_functiondef",
            "information_schema.columns",
        ):
            assert target in joined, (
                f"只读清单里缺 {target} —— 清单是「本门只 SELECT」的可核查载体，"
                "漏一条就等于有一条 SQL 没被任何判据看过（教训 16）"
            )

    def test_production_catalog_is_read_without_a_write_transaction(self, gate_ast: ast.Module) -> None:
        fn = GATE.function_def(gate_ast, "_collect_catalog")
        source = ast.unparse(fn)
        assert "engine.connect()" in source, (
            "对生产库的唯一承诺是只读；`connect()` 换成 `begin()` 就打开了写事务"
        )
        assert "engine.begin()" not in source

    def test_only_the_report_is_written_to_disk(self, gate_ast: ast.Module) -> None:
        targets: list[str] = []
        for node in ast.walk(gate_ast):
            if isinstance(node, ast.Call) and _dotted(node.func) in (
                "os.replace",
                "tmp.write_text",
            ):
                targets.append(ast.unparse(node))
        assert targets, "找不到写盘点 —— 判据失效"
        for call in targets:
            assert "MANIFEST" not in call and "OVERLAY" not in call, (
                f"写入目标不是本报告: {call} —— 覆盖 manifest/overlay 等于替复核方签「已复核」"
            )
        assert any("OUTPUT_PATH" in call for call in targets)

    def test_upstream_inputs_are_recorded_as_read_only(self, report: dict[str, Any]) -> None:
        # 磁盘记录 **与** 现算都要查：只查磁盘的判据对门侧改动天生不敏感（教训 17）。
        live = GATE.upstream_inputs()
        for source, inputs in (("report", report["upstream_inputs"]), ("live", live)):
            assert inputs, f"{source}: 上游输入块为空"
            for label, row in inputs.items():
                assert row["present"], f"{source}: 上游输入缺失 {label} ({row['path']})"
                assert row["disposition"] == "read_only_input", (
                    f"{source}: {label} 的处置是 {row['disposition']!r} 而非 read_only_input —— "
                    "处置字段是下游判断「这份上游产物还能不能当真源」的唯一依据"
                )
                assert len(row["sha256"]) == 64, f"{source}: {label} 没记 digest"
        assert {k: v["sha256"] for k, v in live.items()} == {
            k: v["sha256"] for k, v in report["upstream_inputs"].items()
        }, "上游输入的 digest 与记录不一致 ⇒ 它们在本轮被改过"

    def test_the_report_does_not_reference_other_tasks_scan_bigrams(self) -> None:
        """本报告落在 `backend/data/` 内，不得给上游任务的入向扫描凭空加义务。

        🔴 实测因果：报告里出现字面 `Task 67` 时，上游 structural pre-reconcile 的
        `prose_reference` 入向模式会命中，它的逐字节锁与入向判据当场变红（把本报告移出
        `backend/data/` 后立刻转绿）。改本报告的引用形式即可，不必改上游产物。
        """
        raw = REPORT_PATH.read_text(encoding="utf-8")
        for number in (61, 66, 67):
            assert f"Task {number}" not in raw, (
                f"报告里出现字面 `Task {number}` —— 会污染该任务的 `backend/data/**` 入向扫描"
            )
            assert f'"owner_task": "{number}"' not in raw, (
                f"报告里出现 `owner_task: {number}` —— 会被当成指向该任务的归属登记"
            )

    def test_the_gate_imports_no_implementation_task_guard(self, gate_ast: ast.Module) -> None:
        imported: list[str] = []
        for node in ast.walk(gate_ast):
            if isinstance(node, ast.Import):
                imported += [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        offenders = [
            name
            for name in imported
            if "tests" in name or re.search(r"(generate|check|mutate)_task\d+", name)
        ]
        assert not offenders, (
            f"本门 import 了实现任务的产物: {offenders} —— 正文逐字「不得由实现任务自证」"
        )


# ════════════════════════════════════════════════════════════════════════════
# 三、六个子条目各自有独立判据与独立报告字段
# ════════════════════════════════════════════════════════════════════════════


class TestSixSubBulletsAreEachMeasured:
    def test_all_six_sub_bullets_are_declared(self, report: dict[str, Any]) -> None:
        declared = report["sub_bullets"]
        assert sorted(declared) == ["1", "2", "3", "4", "5", "6"], (
            f"正文六个子条目必须逐条声明，实得 {sorted(declared)}"
        )
        for key, text in declared.items():
            assert len(text) > 30, f"子条目 {key} 的声明太短，无法核对"

    def test_sub_bullet_1_and_6_land_on_a_real_execution(self, report: dict[str, Any]) -> None:
        suite = report["suite_verdict"]
        assert suite["state"] == "executed", "子条目 1 没有真实 pytest 执行结果"
        assert suite["provenance"] == "recorded_from_real_execution"
        assert suite["executed_from"] == ".", "正文逐字「从仓库根执行」"
        assert int(suite["file_count"]) > 0
        assert int(suite["counts"]["passed"]) > 1000, (
            "辐射面 passed 计数过低 ⇒ 大概率没真跑（空集恒真）"
        )
        assert suite["surface_digest_matches"] is True, (
            "记录里的文件清单与现算辐射面不一致 ⇒ scanner 改了或记录过期"
        )

    def test_sub_bullet_2_and_3_land_on_invariants(self, report: dict[str, Any]) -> None:
        buckets = report["invariant_counts"]["by_sub_bullet"]
        assert int(buckets.get("2", 0)) >= 10, f"子条目 2 的不变量太少: {buckets}"
        assert int(buckets.get("3", 0)) >= 8, f"子条目 3 的不变量太少: {buckets}"

    def test_sub_bullet_4_lands_on_endpoint_checks(self, report: dict[str, Any]) -> None:
        rows = report["endpoint_checks"]
        assert len(rows) >= 6, f"端点判据太少: {len(rows)}"
        assert all(row["sub_bullet"] == 4 for row in rows)
        ids = {row["check_id"] for row in rows}
        for required in (
            "endpoints_carry_explicit_project_wp_entry",
            "recovery_list_requires_room_and_generation",
            "rollback_route_key_is_opaque_content_version_id",
            "no_route_uses_numeric_revision_as_key",
            "guard_is_the_first_await_in_every_handler",
            "unified_404_403_refusal_surface",
            "duplicate_operation_authorization_keyed_on_requested_id",
        ):
            assert required in ids, f"端点判据里缺 {required}"

    def test_sub_bullet_5_lands_on_chain_checks(self, report: dict[str, Any]) -> None:
        chain = [row for row in report["invariants"] if row["sub_bullet"] == 5]
        assert len(chain) >= 5, f"链路判据太少: {len(chain)}"
        assert all(
            row["behaviour_side"]["state"] == "verified_on_rows" for row in chain
        ), "链路判据必须在真行上验过（不只 schema 侧）"

    def test_sub_bullet_6_declares_the_oo_boundary(self, report: dict[str, Any]) -> None:
        boundary = report["oo_scope_boundary"]
        assert boundary["owner_of_real_oo_scenarios"] == "70"
        # 扫描时剔掉边界声明自身 —— 禁令清单当然含这些词，否则判据必然自撞。
        raw = json.dumps(
            {k: v for k, v in report.items() if k != "oo_scope_boundary"}, ensure_ascii=False
        )
        for claim in boundary["forbidden_claims"]:
            assert f'"{claim}"' not in raw, (
                f"报告里出现禁止的声明 `{claim}` —— 正文明令不冒充真实 OO probe/evidence"
            )
        # 🔴 名单类判据必须断言**包含那两个真实目标**（教训 16）：只逐项断言「清单里的表是 0 行」
        #    时，把清单换成任意两张本来就空的表（如 `working_paper_sync_conflict`）照样绿，
        #    而 evidence 两张表就可以被随意写入了。
        untouched = list(boundary["evidence_tables_left_untouched"])
        live_untouched = list(GATE.OO_SCOPE_BOUNDARY["evidence_tables_left_untouched"])
        assert untouched == live_untouched, (
            "磁盘记录与门里的边界声明不一致 —— 只查磁盘的判据对门侧改动天生不敏感（教训 17）"
        )
        for required in (
            "working_paper_sync_test_run",
            "working_paper_entry_evidence_scenario",
        ):
            assert required in untouched, (
                f"边界声明里缺 {required} —— 这是 evidence 的两张表，Task 70 才有权写"
            )
        scratch = report["restoration"]["scratch_row_counts"]
        for table in untouched:
            assert int(scratch.get(table, 0)) == 0, (
                f"{table} 在 scratch schema 里也被写了行 ⇒ 制造了「有 evidence」的表象"
            )


# ════════════════════════════════════════════════════════════════════════════
# 四、不变量：声明↔报告↔探针三向锁死 + 正向重算 + 反事实多臂
# ════════════════════════════════════════════════════════════════════════════


class TestInvariantsAreMeasured:
    def test_declared_and_reported_invariants_are_the_same_set(
        self, report: dict[str, Any]
    ) -> None:
        declared = {inv.check_id for inv in _ALL_INVARIANTS}
        reported = {row["check_id"] for row in report["invariants"]}
        assert declared == reported, f"声明与报告不一致: {declared ^ reported}"

    def test_every_invariant_carries_every_required_facet(self, report: dict[str, Any]) -> None:
        for row in report["invariants"]:
            missing = [f for f in GATE.REQUIRED_INVARIANT_FACETS if f not in row]
            assert not missing, f"{row['check_id']} 缺字段 {missing}"
            assert row["properties"], f"{row['check_id']} 没有 Property 落点"
            assert row["requirements"], f"{row['check_id']} 没有 Requirement 落点"
            assert row["measured_by"], f"{row['check_id']} 没写用什么度量"
            assert row["owner_task"], f"{row['check_id']} 没有 owner"

    def test_both_sides_are_reported_for_every_invariant(self, report: dict[str, Any]) -> None:
        for row in report["invariants"]:
            schema_state = row["schema_side"]["state"]
            behaviour_state = row["behaviour_side"]["state"]
            assert schema_state in GATE.SCHEMA_STATES, f"{row['check_id']}: {schema_state}"
            assert behaviour_state in GATE.BEHAVIOUR_STATES, f"{row['check_id']}: {behaviour_state}"
            assert row["schema_side"]["requirement_count"] >= 1, (
                f"{row['check_id']} 没有任何 schema 要求 ⇒ schema 侧结论恒真"
            )
            assert row["behaviour_side"]["arm_count"] >= 2, (
                f"{row['check_id']} 行为臂不足 2 条 ⇒ 没有对照组或没有否定臂"
            )

    def test_every_invariant_was_verified_on_real_rows(self, report: dict[str, Any]) -> None:
        """0 行的生产库上「逐行成立」恒真 ⇒ 每条不变量都必须在 scratch schema 真造过行。"""
        not_on_rows = [
            row["check_id"]
            for row in report["invariants"]
            if row["behaviour_side"]["state"] != "verified_on_rows"
        ]
        assert not not_on_rows, (
            f"以下不变量只有 schema 侧结论: {not_on_rows} —— 报告必须显式标出，"
            "本轮期望全部在行上验过"
        )

    def test_declared_arms_and_written_observations_are_two_way_locked(
        self, report: dict[str, Any], observations: dict[str, Any]
    ) -> None:
        declared = {arm.arm_id for inv in _ALL_INVARIANTS for arm in inv.arms}
        written = {key for key in observations if not key.startswith("__")}
        assert declared - written == set(), f"声明了却没探针写观测: {sorted(declared - written)}"
        assert written - declared == set(), f"探针写了却没人声明（死观测）: {sorted(written - declared)}"
        assert len(declared) == int(report["invariant_counts"]["arm_total"])

    def test_every_rejected_arm_really_hit_its_own_declared_reason(
        self, report: dict[str, Any]
    ) -> None:
        for row in report["invariants"]:
            for arm in row["behaviour_side"]["arms"]:
                if arm["expectation"] != "rejected":
                    continue
                assert arm["agrees"], (
                    f"{row['check_id']}/{arm['arm_id']} 的拒绝理由与声明不符: "
                    f"{json.dumps(arm, ensure_ascii=False)[:400]}"
                )
                assert arm["signature_hits"] == arm["signature"], (
                    f"{row['check_id']}/{arm['arm_id']} 只命中部分片段"
                )

    def test_no_two_arms_with_different_reasons_match_each_other(
        self, report: dict[str, Any]
    ) -> None:
        for row in report["invariants"]:
            hits = row["behaviour_side"]["cross_signature_hits"]
            assert not hits, (
                f"{row['check_id']} 的臂互相冒充: {json.dumps(hits, ensure_ascii=False)[:400]}"
            )

    def test_every_invariant_recomputes_from_the_recorded_inputs(
        self, report: dict[str, Any], catalog: Any, observations: dict[str, Any]
    ) -> None:
        """🔴 正向重算：反事实多臂只能证明「非重言」，抓不到「恒真」（教训 15）。"""
        recorded = {row["check_id"]: row for row in report["invariants"]}
        for invariant in _ALL_INVARIANTS:
            fresh = invariant.evaluate(catalog, observations)
            was = recorded[invariant.check_id]
            assert fresh["passed"] == was["passed"], f"{invariant.check_id} 的 passed 不可复算"
            assert fresh["schema_side"]["state"] == was["schema_side"]["state"]
            assert fresh["behaviour_side"]["state"] == was["behaviour_side"]["state"]
            assert [a["agrees"] for a in fresh["behaviour_side"]["arms"]] == [
                a["agrees"] for a in was["behaviour_side"]["arms"]
            ], f"{invariant.check_id} 的逐臂结论不可复算"

    def test_removing_any_single_ddl_requirement_flips_the_invariant(
        self, catalog: Any, observations: dict[str, Any]
    ) -> None:
        """反事实多臂：逐条在内存里抹掉一条 DDL 要求，结论必须翻。

        不翻 ⇒ 那条要求没有度量任何东西（判据是重言式）。
        """
        import dataclasses

        checked = 0
        for invariant in _ALL_INVARIANTS:
            baseline = invariant.evaluate(catalog, observations)
            assert baseline["schema_side"]["satisfied"], (
                f"对照组必须先过: {invariant.check_id}（教训 5）"
            )
            for index, requirement in enumerate(invariant.schema_requirements):
                # 反事实的构造必须按 kind 走：把 `absent_column` 改名会让它**更**满足
                # （不存在的列当然缺席），那条臂就变成无效变异。改指一个确实存在的列才翻。
                if requirement.kind == "absent_column":
                    counterfactual = GATE.DdlRequirement(
                        "absent_column", requirement.table, "id", ()
                    )
                else:
                    counterfactual = GATE.DdlRequirement(
                        requirement.kind,
                        requirement.table,
                        requirement.name + "__task68_counterfactual",
                        requirement.must_contain,
                    )
                stripped = dataclasses.replace(
                    invariant,
                    schema_requirements=tuple(
                        r for i, r in enumerate(invariant.schema_requirements) if i != index
                    )
                    + (counterfactual,),
                )
                arm = stripped.evaluate(catalog, observations)
                assert arm["passed"] is False, (
                    f"{invariant.check_id} 抹掉/改名第 {index} 条 DDL 要求"
                    f"（{requirement.kind} {requirement.table}.{requirement.name}）后仍判通过"
                    " ⇒ 这条要求没度量任何东西"
                )
                checked += 1
        assert checked >= 60, f"反事实臂数过少（{checked}）⇒ 覆盖面可疑"

    def test_flipping_any_single_arm_flips_the_invariant(
        self, catalog: Any, observations: dict[str, Any]
    ) -> None:
        """逐臂反事实：把一条臂的观测改成相反结果，整条不变量必须变红。"""
        checked = 0
        for invariant in _ALL_INVARIANTS:
            for arm in invariant.arms:
                tampered = dict(observations)
                if arm.expectation == "accepted":
                    tampered[arm.arm_id] = {"accepted": False, "rejection": "23514||synthetic"}
                elif arm.expectation == "rejected":
                    tampered[arm.arm_id] = {"accepted": True, "rejection": None}
                else:
                    measured = dict(
                        (observations.get(arm.arm_id) or {}).get("measured") or {}
                    )
                    key = next(iter(arm.expect_measure or {}), None)
                    assert key is not None
                    measured[key] = "task68-synthetic-wrong-value"
                    tampered[arm.arm_id] = {"measured": measured}
                row = invariant.evaluate(catalog, tampered)
                assert row["passed"] is False, (
                    f"{invariant.check_id} 把 {arm.arm_id} 的观测翻掉后仍判通过 ⇒ 这条臂没参与判定"
                )
                checked += 1
        assert checked >= 100, f"逐臂反事实数过少（{checked}）"

    def test_behaviour_state_follows_the_arms_not_a_constant(
        self, catalog: Any, observations: dict[str, Any]
    ) -> None:
        """`behaviour_side.state` 必须由逐臂结论派生。

        🔴 变异检验实测缺陷：把它写成常量 `"verified_on_rows"` 时 `passed` 仍由 `agrees`
        决定，于是所有既有判据照样绿 —— 而报告会对每条不变量都声称「已在真行上验过」。
        `verified_on_rows` 是本报告区分「DDL 把住了」与「真数据上验过」的唯一字段。
        """
        for invariant in _ALL_INVARIANTS:
            baseline = invariant.evaluate(catalog, observations)
            assert baseline["behaviour_side"]["state"] == "verified_on_rows", (
                f"对照组必须先过: {invariant.check_id}"
            )
            first = invariant.arms[0]
            tampered = dict(observations)
            tampered[first.arm_id] = (
                {"accepted": True, "rejection": None}
                if first.expectation == "rejected"
                else {"accepted": False, "rejection": "23514||synthetic"}
            )
            row = invariant.evaluate(catalog, tampered)
            assert row["behaviour_side"]["state"] == "arm_mismatch", (
                f"{invariant.check_id}: 翻掉 {first.arm_id} 的观测后行为侧状态仍是 "
                f"{row['behaviour_side']['state']} ⇒ 该字段是常量，不是派生值"
            )
        broken = dict(observations)
        broken["__harness__"] = {"error": "synthetic harness failure", "schema": None}
        row = _ALL_INVARIANTS[0].evaluate(catalog, broken)
        assert row["behaviour_side"]["state"] == "harness_error", (
            "采集失败时行为侧状态必须是 `harness_error`，不得仍报「在行上验过」（禁 fail-open）"
        )

    def test_the_forcesave_five_tuple_is_checked_column_by_column(
        self, report: dict[str, Any]
    ) -> None:
        row = next(
            r for r in report["invariants"] if r["check_id"] == "forcesave_five_tuple_idempotency"
        )
        requirement = next(
            item
            for item in row["schema_side"]["requirements"]
            if item["target"].endswith("uq_wpfr_idempotency")
        )
        definition = requirement["definition"]
        for column in (
            "room_id",
            "generation",
            "initiated_by_participant_id",
            "kind",
            "idempotency_key",
        ):
            assert column in definition, (
                f"五元键定义里缺列 {column} —— 少 `initiated_by_participant_id` 时索引仍叫"
                " `uq_wpfr_idempotency`，跨 participant 复用同一 Idempotency-Key 就不再 409"
            )

    def test_the_declared_schema_gap_is_measured_not_assumed(
        self, report: dict[str, Any]
    ) -> None:
        gaps = [
            row for row in report["invariants"] if row["schema_side"].get("declared_gap")
        ]
        assert len(gaps) == 1, f"schema gap 数量意外: {[g['check_id'] for g in gaps]}"
        row = gaps[0]
        gap = row["schema_side"]["declared_gap"]
        assert gap["owner_task"] and gap["owner_task"] != GATE.OWNER_TASK, (
            "已登记的 schema gap 必须点名**别的** owner，不能自己收着"
        )
        assert gap["independently_confirmed_by"], "gap 必须点名它在哪里真的被验过"
        probe = next(
            arm for arm in row["behaviour_side"]["arms"] if arm["arm_id"] == "dlv_pre_durable_owner"
        )
        assert probe["measured"]["ddl_accepts_pre_durable_owner"] is True, (
            "gap 是**现测**结论（DDL 真的接受了非法形态），不是假设"
        )


# ════════════════════════════════════════════════════════════════════════════
# 五、端点判据
# ════════════════════════════════════════════════════════════════════════════


class TestEndpointChecks:
    def test_all_endpoint_checks_passed(self, report: dict[str, Any]) -> None:
        failed = [row["check_id"] for row in report["endpoint_checks"] if not row["passed"]]
        assert not failed, f"端点判据未通过: {failed}"

    def test_endpoint_checks_recompute_live(self, report: dict[str, Any]) -> None:
        fresh = {row["check_id"]: row["passed"] for row in GATE.build_endpoint_checks()}
        was = {row["check_id"]: row["passed"] for row in report["endpoint_checks"]}
        assert fresh == was, f"端点判据不可复算: {fresh} vs {was}"

    def test_the_required_endpoint_list_names_the_real_thirteen(self) -> None:
        suffixes = {suffix for _m, suffix, _h in GATE.REQUIRED_ENDPOINTS}
        for required in (
            "/pending-mutations",
            "/materialize",
            "/rooms/{room_id}/confirm-descriptor",
            "/rooms/{room_id}/forcesave",
            "/rooms/{room_id}/close-intents",
            "/recovery-cases",
            "/recovery-cases/{case_id}/claim",
            "/recovery-cases/{case_id}/download-only",
            "/operations/{operation_id}",
            "/operations/{operation_id}/conflicts",
            "/operations/{operation_id}/timeline",
            "/operations/{operation_id}/resolve",
            "/versions/{version_id}/rollback",
        ):
            assert required in suffixes, (
                f"必查端点清单里缺 {required} —— 只迭代路由表的判据在路由被删空时照样绿（教训 16）"
            )
        assert len(GATE.REQUIRED_ENDPOINTS) == 13

    def test_guard_first_await_check_is_not_a_tautology(self) -> None:
        """判据必须真的读到了每个 handler 的 await 序列（不是空列表恒真）。"""
        row = next(
            r
            for r in GATE.build_endpoint_checks()
            if r["check_id"] == "guard_is_the_first_await_in_every_handler"
        )
        orders = row["detail"]["awaited_order"]
        assert len(orders) == len(GATE.REQUIRED_ENDPOINTS)
        for handler, order in orders.items():
            assert order, f"{handler} 的 await 序列为空 ⇒ AST 没读到东西"
            assert order[0] == "_guard", f"{handler} 的第一个 await 不是 _guard"

    def test_the_guard_order_detector_itself_works(self) -> None:
        """喂合成顺序检验**本门的检测器** —— 只重算真路由的判据度量的是路由，不是检测器。"""
        assert GATE.guard_first_violations({"ok": ["_guard", "svc.x"]}) == [], "对照组必须先过"
        late = GATE.guard_first_violations({"late": ["svc.repository.load", "_guard"]})
        assert late and "late" in late[0], (
            "先读业务对象再授权没有被检测到 —— scope-index-before-resource 的核心是**顺序**："
            "先读后授权会通过 404/403 的时序泄露对象存在性"
        )
        absent = GATE.guard_first_violations({"none": ["svc.repository.load"]})
        assert absent and "none" in absent[0], "完全没有 guard 也必须被检测到"

    def test_the_refusal_site_classifier_itself_works(self) -> None:
        """404/403 分桶器的合成输入检验。"""
        assert (
            GATE.classify_refusal_site(404, after_guard=True, error_code="x") == "raw_404"
        ), "404 无论在哪都必须归为裸 404（存在性敏感码只能经 `_not_found()` 工厂）"
        assert (
            GATE.classify_refusal_site(403, after_guard=True, error_code="close_capture_forbidden")
            == "post_guard_403"
        )
        assert (
            GATE.classify_refusal_site(403, after_guard=False, error_code="x") == "bad_403"
        ), "授权**之前**的 403 会泄露存在性，必须判坏"
        assert (
            GATE.classify_refusal_site(403, after_guard=True, error_code=None) == "bad_403"
        ), "没有 error_code 的 403 客户端无法分桶，必须判坏"
        assert GATE.classify_refusal_site(422, after_guard=True, error_code="x") == "other"

    def test_no_route_template_carries_a_numeric_revision(self) -> None:
        row = next(
            r
            for r in GATE.build_endpoint_checks()
            if r["check_id"] == "no_route_uses_numeric_revision_as_key"
        )
        assert int(row["detail"]["route_count"]) > 13, (
            "路由数过少 ⇒ AST 没扫到整张表，这条判据会空集恒真"
        )
        assert row["detail"]["revision_routes"] == []


# ════════════════════════════════════════════════════════════════════════════
# 六、辐射面 / 既存红 / Property 落点
# ════════════════════════════════════════════════════════════════════════════


class TestRadiationSurfaceAndPreexistingReds:
    def test_surface_is_recomputed_from_references_not_hand_written(
        self, report: dict[str, Any]
    ) -> None:
        fresh = GATE.radiation_surface()
        recorded = report["radiation_surface"]
        assert fresh["digest"] == recorded["digest"], "辐射面不可复算（scanner 改了或记录过期）"
        assert int(recorded["scanned_test_files"]) > 1000, (
            "扫描分母过小 ⇒ 没有真的遍历 `backend/tests/**`"
        )
        assert 20 <= int(recorded["surface_size"]) < int(recorded["scanned_test_files"]), (
            "辐射面等于全量或几乎为空 —— 正文逐字「不跑无边界全量」，也不能空集恒真"
        )
        assert recorded["outside_files"], (
            "辐射面里没有 `workpaper_sync/` 目录外的文件 ⇒ 引用关系反查大概率退化成了目录枚举"
        )

    def test_in_dir_but_out_of_surface_files_are_listed_not_hidden(
        self, report: dict[str, Any]
    ) -> None:
        recorded = report["radiation_surface"]
        assert "in_dir_but_out_of_surface" in recorded
        assert recorded["in_dir_but_out_of_surface_note"]
        for path in recorded["in_dir_but_out_of_surface"]:
            assert (REPO / path).exists(), f"清单里的文件不存在: {path}"
            assert path not in recorded["files"], f"{path} 同时出现在两侧"

    def test_this_guard_file_ran_in_the_same_execution(self, report: dict[str, Any]) -> None:
        """本守卫**不在**辐射面（它验的是门，不引用被验生产单元），但必须同批跑掉。

        否则「门自己绿不绿」在报告里就没有实证 —— 只剩一句自称。
        """
        me = _THIS.relative_to(REPO).as_posix()
        suite = report["suite_verdict"]
        assert suite["own_guard_included"] is True, "那次执行没有带上本守卫"
        assert suite["own_guard_path"] == me, (
            f"记录里的守卫路径 {suite['own_guard_path']} 与本文件 {me} 不一致"
        )
        assert int(suite["executed_file_count"]) >= int(suite["file_count"]), (
            "执行文件数小于辐射面文件数 ⇒ 有文件被漏掉"
        )
        # 本守卫可能**恰好**也在辐射面里（它现读 V151/V152 核对 scratch DDL 集合 ⇒ 命中
        # `scratch_migrations` 模式）。那不是自证：命中理由必须是真实的引用模式，且无论
        # 在不在辐射面里，`own_guard_included` 都独立保证它跑掉了。
        surface_files = report["radiation_surface"]["files"]
        if me in surface_files:
            assert surface_files[me], "在辐射面里却没记命中了哪条引用模式"
            for reason in surface_files[me]:
                assert reason in dict(GATE._SURFACE_PATTERNS), f"未知命中理由: {reason}"

    def test_every_preexisting_red_is_registered_with_attribution_and_owner(self) -> None:
        for entry in GATE.PREEXISTING_FAILURES:
            assert entry["attribution"], f"{entry['file']} 没有归因"
            assert entry["owner_task"], f"{entry['file']} 没有 owner"
            assert entry["why_not_fixed_here"], f"{entry['file']} 没说明为何不在本任务修"
            assert (REPO / str(entry["file"])).exists(), f"登记的文件不存在: {entry['file']}"

    def test_the_registered_baseline_matches_the_real_run(self, report: dict[str, Any]) -> None:
        suite = report["suite_verdict"]
        bad = [row["file"] for row in suite["preexisting"] if not row["agrees"]]
        assert not bad, (
            f"既存红逐项核对不上: {bad} —— 声明与实测必须一致（多了要归因，少了说明基线过期）"
        )
        assert suite["unexpected_failed_nodeids"] == [], (
            f"出现未登记的失败: {suite['unexpected_failed_nodeids']}"
        )
        assert suite["unexpected_error_nodeids"] == [], (
            f"出现未登记的 error: {suite['unexpected_error_nodeids']}"
        )
        own = suite["own_guard_result"]
        # 🔴 这里**刻意不**断言 `own["clean"]`：pytest 先跑、报告后写，本守卫读到的永远是
        #    上一份报告 —— 自我断言会变成不动点迭代（4→1→0），每轮 16 分钟。
        #    「本门守卫必须全绿」这条由**门的判定**承担（`verdict.suite_passed` 现算自记录），
        #    它不在循环里，一轮即收敛。这里只断言**分桶完整**：任何失败都必须归入
        #    「已登记既存红」或「本门守卫」二者之一，不得有第三类被静默。
        assert int(suite["observed_errors"]) == int(suite["declared_preexisting_errors"])
        assert (
            int(suite["observed_failed"])
            == int(suite["declared_preexisting_failed"]) + len(own["failed"])
        ), (
            "观测失败数 ≠ 已登记既存红 + 本门守卫失败数 ⇒ 有失败既不属既存红也不属本门守卫，"
            "而 `unexpected_failed_nodeids` 却是空的（分桶漏了一类）"
        )

    def test_error_nodeids_are_actually_captured(self, report: dict[str, Any]) -> None:
        """`-rf` 只列 FAILED；ERROR 必须靠 `-rfE` 才进短摘要，否则 6 个 error 永远对不上。"""
        suite = report["suite_run"]
        assert "-rfE" in str(suite["command"]), "pytest 调用里缺 `-rfE` ⇒ ERROR 不会被记 nodeid"
        assert suite["error_nodeids"], "记录里没有任何 error nodeid，但计数非零"
        assert len(suite["error_nodeids"]) == int(suite["counts"].get("errors", 0))

    def test_surface_extras_are_recomputed_live_not_only_read(
        self, report: dict[str, Any]
    ) -> None:
        """辐射面的**每个**字段都要现算比对 —— 只读磁盘的判据对 scanner 侧改动天生不敏感。"""
        fresh = GATE.radiation_surface()
        recorded = report["radiation_surface"]
        for key in (
            "surface_size",
            "inside_workpaper_sync_dir",
            "outside_workpaper_sync_dir",
            "in_dir_but_out_of_surface",
            "outside_files",
            "digest",
        ):
            assert fresh[key] == recorded[key], f"辐射面字段 {key} 不可复算"
        assert fresh["in_dir_but_out_of_surface"], (
            "现算的「在目录里但不引用被验单元」差集为空 —— 本轮实测该目录确实有这类文件，"
            "空集意味着这条如实报告被短路了"
        )

    def test_the_suite_command_keeps_error_reporting_on(self) -> None:
        """`-rfE` 必须写在**门的源码**里，不能只在磁盘记录里看着对。"""
        source = ast.unparse(GATE.function_def(GATE.module_ast(GATE_PATH), "run_radiation_suites"))
        assert "-rfE" in source, (
            "pytest 调用里缺 `-rfE` ⇒ ERROR 不进短摘要，6 个 collection/setup ERROR 会全部"
            "变成「无 nodeid」，既存红逐项核对永远对不上而总计数看起来还是对的"
        )
        assert "'-rf'" not in source and '"-rf"' not in source

    def test_suite_reconciliation_is_a_pure_function_of_the_record(
        self, report: dict[str, Any]
    ) -> None:
        """用合成 suite 记录直接喂回 `evaluate_suite_run`，逐条结论必须跟着变。

        🔴 只断言磁盘记录的判据对「核对逻辑本身被短路」完全不敏感（教训 17）。
        """
        surface = report["radiation_surface"]
        recomputed = GATE.evaluate_suite_run(report["suite_run"], surface)
        assert recomputed["passed"] == report["suite_verdict"]["passed"], "suite 结论不可复算"
        assert recomputed["preexisting_all_agree"] == report["suite_verdict"][
            "preexisting_all_agree"
        ]

        base = _clean_suite_record(report)
        clean = GATE.evaluate_suite_run(base, surface)
        assert clean["passed"] is True, (
            "合成的「一切干净」记录必须先判通过（对照组）—— 不过则后面每条否定臂都无信息量"
        )
        # ① 声明与实测不符 ⇒ agrees 必须变假
        entry = GATE.PREEXISTING_FAILURES[0]
        stem = Path(str(entry["file"])).name
        shrunk = dict(
            base,
            failed_nodeids=[n for n in base["failed_nodeids"] if stem not in n],
            counts=dict(base["counts"], failed=int(base["counts"]["failed"]) - 1),
        )
        verdict = GATE.evaluate_suite_run(shrunk, surface)
        row = next(r for r in verdict["preexisting"] if Path(str(r["file"])).name == stem)
        assert row["agrees"] is False, (
            "已登记既存红在实测里消失后 `agrees` 仍为真 ⇒ 逐项核对被短路（基线过期不会被发现）"
        )
        assert verdict["passed"] is False

        # ② 本门守卫自身的红必须单列且让 suite 判定失败
        own = f"{GATE.OWN_GUARD_PATH}::TestSynthetic::test_synthetic"
        with_own = dict(
            base,
            failed_nodeids=[*base["failed_nodeids"], own],
            counts=dict(base["counts"], failed=int(base["counts"]["failed"]) + 1),
        )
        verdict2 = GATE.evaluate_suite_run(with_own, surface)
        bucketed = verdict2["own_guard_result"]["failed"]
        # 不比整个集合（记录里本来可能已有若干本门守卫的红，那与本判据无关）——
        # 只要求「合成的那条被正确分桶」且「这一桶里只有本门守卫的 nodeid」。
        assert own in bucketed, (
            "本门守卫的失败没有被单列 ⇒ 会与「未登记的第三类失败」混在一起无法区分"
        )
        assert all(GATE.OWN_GUARD_PATH.split("/")[-1] in n for n in bucketed), (
            f"本门守卫桶里混进了别的文件: {bucketed}"
        )
        assert verdict2["own_guard_result"]["clean"] is False
        assert own not in verdict2["unexpected_failed_nodeids"], (
            "本门守卫的失败被误算成「未登记的既存红」⇒ 自指，永不收敛"
        )
        assert verdict2["passed"] is False, (
            "本门守卫全红时 suite 仍判通过 ⇒ 「跑了自己的守卫」被当成「守卫真的绿」"
        )

        # ③ 真正未登记的第三类失败必须进 unexpected
        stranger = "backend/tests/workpaper_sync/test_task00_not_registered.py::test_x"
        with_stranger = dict(
            base,
            failed_nodeids=[*base["failed_nodeids"], stranger],
            counts=dict(base["counts"], failed=int(base["counts"]["failed"]) + 1),
        )
        verdict3 = GATE.evaluate_suite_run(with_stranger, surface)
        assert verdict3["unexpected_failed_nodeids"] == [stranger]
        assert verdict3["passed"] is False

        # ④ 文件清单与现算辐射面不一致必须失败
        drifted = GATE.evaluate_suite_run(dict(base, files_digest="synthetic"), surface)
        assert drifted["surface_digest_matches"] is False
        assert drifted["passed"] is False

    def test_this_task_did_not_introduce_new_reds(self, report: dict[str, Any]) -> None:
        introduced = [
            row
            for row in report["suite_verdict"]["preexisting"]
            if row.get("discovered_by_this_task") and str(row.get("owner_task")) == "68"
            and (int(row["observed_failed"]) or int(row["observed_errors"]))
        ]
        assert not introduced, (
            f"本任务自己引入的红没有清零: {[r['file'] for r in introduced]}"
        )


class TestPropertyLandings:
    def test_declared_properties_match_the_task_text(self, report: dict[str, Any]) -> None:
        declarations = report["task_declarations"]
        assert declarations["properties_match"] is True, (
            f"声明的 Property 与正文不一致: 正文 {declarations['properties_in_task_text']} vs "
            f"声明 {declarations['declared_properties']}"
        )
        assert len(GATE.DECLARED_PROPERTIES) == 48, (
            f"正文点名 48 条，实得 {len(GATE.DECLARED_PROPERTIES)}"
        )
        assert len(declarations["requirements_in_task_text"]) == 53

    def test_every_declared_property_exists_in_design(self, report: dict[str, Any]) -> None:
        titles = report["design_property_titles"]
        for number in GATE.DECLARED_PROPERTIES:
            assert str(number) in titles, f"design.md 里没有 Property {number}"
            assert titles[str(number)], f"Property {number} 的标题为空"

    def test_every_property_has_a_landing(self, report: dict[str, Any]) -> None:
        landings = report["properties"]
        assert landings["structural_errors"] == [], (
            f"有 Property 无落点: {landings['structural_errors']}"
        )
        assert sum(landings["tiers"].values()) == len(GATE.DECLARED_PROPERTIES)
        assert landings["tiers"]["independently_expressed"] >= 20, (
            "第一档（本门独立重新表达）占比过低 —— 正文逐字「不得由实现任务自证」"
        )

    def test_tier_two_is_honestly_labelled_as_weaker(self, report: dict[str, Any]) -> None:
        rows = [r for r in report["properties"]["rows"] if r["tier"] == "independently_executed"]
        for row in rows:
            assert row["caveat"], f"{row['property']} 第二档没有弱化说明"
            assert int(row["annotated_in_surface_files"]) > 0, (
                f"{row['property']} 声称在辐射面里被点名，但命中文件数为 0"
            )
            assert row["sample_files"], f"{row['property']} 没给出样例文件"

    def test_property_landing_is_derived_not_hand_written(self, report: dict[str, Any]) -> None:
        fresh = GATE.build_property_landings(
            report["invariants"],
            report["endpoint_checks"],
            report["radiation_surface"],
            report["suite_verdict"],
        )
        assert fresh["tiers"] == report["properties"]["tiers"], "Property 档位不可复算"
        assert [r["property"] for r in fresh["rows"]] == [
            r["property"] for r in report["properties"]["rows"]
        ]


# ════════════════════════════════════════════════════════════════════════════
# 七、复原实证 / BP / 判定 / 报告完整性
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def live() -> dict[str, Any]:
    """真跑一次：读真库 DDL + 在 scratch schema 真造行。

    🔴 这是唯一能抓「探针 SQL 被改动」的判据 —— 纯函数级判据全部基于**记录里的观测**，
    对探针本身的改动天生不敏感（本 spec 教训 17 的同型问题）。禁 fail-open：采集失败必须红。
    """
    catalog = GATE.read_schema_catalog()
    harness = GATE.run_behaviour_harness()
    return {"catalog": catalog, "harness": harness}


class TestLiveRunReproducesTheRecord:
    def test_a_failing_catalog_read_records_its_reason(self, monkeypatch: Any) -> None:
        """库读失败必须留下**可诊断的原因**，不能只留 `readable=False`。"""

        async def _boom(_snapshot: Any) -> None:
            raise RuntimeError("synthetic: connection refused")

        monkeypatch.setattr(GATE, "_collect_catalog", _boom)
        broken = GATE.read_schema_catalog()
        assert broken.readable is False
        assert broken.error, (
            "读失败却没记原因 —— 读者无从知道是连不上、权限不足还是表不存在，"
            "「库不可读」这条结论就没有可诊断载体（禁 fail-open）"
        )
        assert "RuntimeError" in broken.error and "connection refused" in broken.error

    def test_probe_and_migration_failures_are_recorded_not_swallowed(
        self, gate_ast: ast.Module
    ) -> None:
        """采集侧的两处失败必须写进报告并中止，不得静默降级成「无数据」。

        🔴 变异检验实测缺陷：把 `probe_errors` 的赋值换成 `pass`、把迁移失败的 `raise` 换成
        `pass` 时，happy path 一切照旧（没有探针真的抛错），所有既有判据全绿 —— 而一旦真出错，
        整族臂会静静消失。所以这两条必须是**结构判据**，不能等 happy path 暴露。
        """
        fn = GATE.function_def(gate_ast, "_run_behaviour")
        probe_loop = None
        for node in ast.walk(fn):
            if isinstance(node, ast.For) and "BEHAVIOUR_PROBES" in ast.unparse(node.iter):
                probe_loop = node
        assert probe_loop is not None, "找不到探针循环 ⇒ 结构判据失效"
        handlers = [
            handler
            for node in ast.walk(probe_loop)
            if isinstance(node, ast.Try)
            for handler in node.handlers
        ]
        assert handlers, "探针循环没有 except 分支"
        recorded = False
        for handler in handlers:
            for stmt in ast.walk(handler):
                if isinstance(stmt, ast.Assign) and any(
                    'probe_errors' in ast.unparse(target) for target in stmt.targets
                ):
                    recorded = True
        assert recorded, (
            "探针异常没有写进 `result[\"probe_errors\"]` ⇒ 被静默吞掉。"
            "本 spec 记录 fail-open 掩盖接线错误是最贵的一类缺陷"
        )
        # 🔴 不要拿 `ast.unparse` 的输出做子串比对：它会把 f-string 的引号规范化
        #    （`f"…{result['apply_errors']}…"` → `f'…{result["apply_errors"]}…'`），
        #    写死原始引号的判据在**未变异**的文件上就会红（首轮实测踩到）。走 AST 结构。
        aborts = [
            node
            for node in ast.walk(fn)
            if isinstance(node, ast.Raise)
            and node.exc is not None
            and "apply_errors" in ast.unparse(node.exc)
        ]
        assert aborts, (
            "迁移在 scratch schema 上应用失败后没有中止 ⇒ 表结构不完整时「非法形态被拒」"
            "会大量来自「表/列不存在」而不是被验的约束（教训 5：世界搭错时后续臂毫无信息量）"
        )
        guarded = [
            node
            for node in ast.walk(fn)
            if isinstance(node, ast.If)
            and "apply_errors" in ast.unparse(node.test)
            and any(isinstance(stmt, ast.Raise) for stmt in ast.walk(node))
        ]
        assert guarded, "中止没有由 `if result[\"apply_errors\"]` 守着 ⇒ 无条件抛或永不抛"

    def test_the_live_catalog_and_harness_really_ran(self, live: dict[str, Any]) -> None:
        assert live["catalog"].readable, (
            f"真库不可读: {live['catalog'].error} —— 库读不到必须记 ERROR 态并让判据红，"
            "不得降级成「没有违反项所以通过」（AC 5.12 禁 fail-open）"
        )
        harness = live["harness"]
        assert harness["error"] is None, f"行为侧采集失败: {harness['error']}"
        assert harness["apply_errors"] == [], f"迁移应用失败: {harness['apply_errors']}"
        assert harness["probe_errors"] == {}, f"探针报错: {harness['probe_errors']}"
        assert str(harness["schema"]).startswith("tmp_task68_reg_"), (
            "行为侧没跑在独立 scratch schema 上"
        )
        assert harness["schema"] != "tmp_task68_reg_", (
            "scratch schema 名没有随机后缀 ⇒ 并发跑会互撞"
        )
        assert len(harness["observations"]) == sum(len(inv.arms) for inv in _ALL_INVARIANTS)

    def test_every_arm_agrees_on_a_freshly_created_world(self, live: dict[str, Any]) -> None:
        observations = dict(live["harness"]["observations"])
        observations["__harness__"] = {
            "error": live["harness"]["error"],
            "schema": live["harness"]["schema"],
        }
        broken: list[str] = []
        for invariant in _ALL_INVARIANTS:
            row = invariant.evaluate(live["catalog"], observations)
            for arm in row["behaviour_side"]["arms"]:
                if not arm["agrees"]:
                    broken.append(
                        f"{invariant.check_id}/{arm['arm_id']}: "
                        f"{json.dumps(arm, ensure_ascii=False)[:260]}"
                    )
        assert not broken, "真跑一次后有臂与声明不符:\n" + "\n".join(broken[:8])

    def test_the_live_run_restores_production(self, live: dict[str, Any]) -> None:
        restoration = GATE.restoration_record(live["harness"])
        assert restoration["measured"] is True
        assert restoration["drifted_tables"] == {}, (
            f"真跑后生产 public schema 行数漂移: {restoration['drifted_tables']}"
        )
        assert int(restoration["own_schema_left"]) == 0
        assert restoration["foreign_scratch_schemas"] == [], (
            f"真跑后库里仍有残留: {restoration['foreign_scratch_schemas']}"
        )
        assert restoration["restored"] is True

    def test_the_live_verdict_matches_the_recorded_one(
        self, live: dict[str, Any], report: dict[str, Any]
    ) -> None:
        fresh = GATE.build_report(
            catalog=live["catalog"],
            harness=live["harness"],
            suite=report["suite_run"],
        )
        assert fresh["verdict"]["result"] == report["verdict"]["result"], (
            "现算判定与磁盘不一致 ⇒ 报告过期或被手改"
        )
        assert [r["passed"] for r in fresh["invariants"]] == [
            r["passed"] for r in report["invariants"]
        ]
        assert fresh["invariant_counts"] == report["invariant_counts"]


class TestProbeWiringIsStructural:
    """声明↔探针的 **AST 级** 双向锁。

    只用「记录里的观测」做锁的话，探针被改名/删调用时记录同样会缺 —— 但那要等真跑才暴露。
    这里直接读源码：每条臂的 id 必须在探针函数体里真的出现，且探针必须挂进注册表。
    """

    def test_every_declared_arm_id_appears_in_some_probe_body(self, gate_ast: ast.Module) -> None:
        probe_names = set(GATE.BEHAVIOUR_PROBES)
        bodies: dict[str, str] = {}
        for node in ast.walk(gate_ast):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
                "_probe_"
            ):
                bodies[node.name] = ast.unparse(node)
        assert bodies, "找不到任何 `_probe_*` 函数 ⇒ AST 判据失效"
        blob = "\n".join(bodies.values())
        missing = [
            arm.arm_id
            for inv in _ALL_INVARIANTS
            for arm in inv.arms
            if arm.arm_id not in blob
        ]
        assert not missing, f"声明了却没有任何探针体提到的臂: {missing}"
        assert len(probe_names) >= 20, f"探针数过少: {len(probe_names)}"

    def test_every_probe_is_registered_and_every_registration_exists(
        self, gate_ast: ast.Module
    ) -> None:
        defined = {
            node.name
            for node in ast.walk(gate_ast)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("_probe_")
        }
        registered_source = ast.unparse(
            next(
                node
                for node in ast.walk(gate_ast)
                if isinstance(node, ast.AnnAssign)
                and GATE.dotted_name(node.target) == "BEHAVIOUR_PROBES"
            )
        )
        unregistered = [name for name in defined if name not in registered_source]
        assert not unregistered, (
            f"定义了却没注册的探针（additive 注入即死代码）: {unregistered}"
        )
        assert len(GATE.BEHAVIOUR_PROBES) == len(defined), (
            f"注册表 {len(GATE.BEHAVIOUR_PROBES)} 项 vs 定义 {len(defined)} 个探针"
        )

    def test_the_scratch_schema_lifecycle_is_complete(self, gate_ast: ast.Module) -> None:
        source = ast.unparse(GATE.function_def(gate_ast, "_run_behaviour"))
        for fragment in ("CREATE SCHEMA", "DROP SCHEMA IF EXISTS", "CASCADE", "public_before",
                        "public_after", "scratch_schema_left"):
            assert fragment in source, (
                f"scratch schema 生命周期缺 `{fragment}` —— 少了它复原实证就不成立"
            )
        assert GATE._SCHEMA_PREFIX.startswith("tmp_task68_"), (
            "scratch schema 前缀必须带任务号，否则清理时无法按归属判断"
        )

    def test_the_scratch_ddl_is_the_production_migration_set(self) -> None:
        names = [path.name for path in GATE.SCRATCH_MIGRATIONS]
        assert any(name.startswith("V151__") for name in names)
        assert any(name.startswith("V152__") for name in names)
        assert not any(name.startswith("V153__") for name in names), (
            "V153 已占号但**未应用**到生产库；scratch 上应用它会让行为侧验的是另一套 schema"
        )
        for path in GATE.SCRATCH_MIGRATIONS:
            assert path.exists(), f"缺少迁移文件: {path}"


class TestRestorationAndVerdict:
    def test_restoration_is_proved_by_data_not_by_exit_code(self, report: dict[str, Any]) -> None:
        restoration = report["restoration"]
        assert restoration["measured"] is True, "没有采到前后快照 ⇒ 复原无从证明"
        assert int(restoration["table_count"]) >= 15, "快照表数过少"
        assert restoration["drifted_tables"] == {}, (
            f"生产 public schema 行数漂移: {restoration['drifted_tables']}"
        )
        assert int(restoration["own_schema_left"]) == 0, "本轮创建的 scratch schema 没被 DROP 干净"
        assert restoration["foreign_scratch_schemas"] == [], (
            f"库里还有 `tmp_task68_reg_*` 残留: {restoration['foreign_scratch_schemas']} —— "
            "通常来自变异实验 M41（故意删掉 DROP）；必须单独清理，不得留在真库里"
        )
        assert restoration["restored"] is True

    def test_the_scratch_schema_really_held_rows(self, report: dict[str, Any]) -> None:
        counts = report["restoration"]["scratch_row_counts"]
        assert counts, "scratch schema 行数快照为空"
        for table in (
            "working_paper_forcesave_request",
            "working_paper_content_application",
            "working_paper_sync_operation",
            "working_paper_callback_delivery",
            "working_paper_sync_scope_index",
            "working_paper_content_representation",
            "working_paper_sync_definition_bundle",
        ):
            assert int(counts.get(table, 0)) > 0, (
                f"{table} 在 scratch schema 里也是 0 行 ⇒ 行为侧其实没造行（空集恒真）"
            )

    def test_production_row_counts_are_reported_as_zero_not_hidden(
        self, report: dict[str, Any]
    ) -> None:
        counts = report["schema_catalog"]["row_counts"]
        assert counts, "生产行数快照缺失"
        empty = [table for table, value in counts.items() if not int(value)]
        assert empty, (
            "生产库相关表居然全都有行 —— 与本轮实测不符，说明快照没真读库"
        )
        honest = report["verdict"]["honest_scope"]
        assert honest["note"], "没有把「scratch 上验过 ≠ 生产数据已验收」讲清楚"
        assert int(honest["really_verified_on_rows"]) == len(_ALL_INVARIANTS)

    def test_every_blocking_point_is_task_scoped_and_owned(self, report: dict[str, Any]) -> None:
        points = report["blocking_points"]
        assert len(points) >= 4, f"BP 太少: {len(points)}"
        seen: set[str] = set()
        for point in points:
            assert GATE.BP_ID_RE.fullmatch(point["id"]), f"BP 编号不合规: {point['id']}"
            assert point["id"] not in seen, f"BP 编号重复: {point['id']}"
            seen.add(point["id"])
            assert point["owner_task"], f"{point['id']} 没有 owner"
            assert point["task68_disposition"] in (
                "reported_not_fixed",
                "reported_not_cleared",
            ), f"{point['id']} 的处置不合规: {point['task68_disposition']}"
            assert point["why_not_fixed_here"], f"{point['id']} 没说明为何不在本任务修"

    def test_blocking_points_are_built_from_inputs_not_constants(
        self, report: dict[str, Any]
    ) -> None:
        """把输入换成合成事实，BP 的度量值必须跟着变（不能是写死的数）。"""
        real = {p["id"]: p for p in report["blocking_points"]}
        synthetic_catalog = dict(report["schema_catalog"])
        synthetic_catalog["row_counts"] = {
            table: 7 for table in report["schema_catalog"]["row_counts"]
        }
        rebuilt = GATE.build_blocking_points(
            invariant_rows=report["invariants"],
            catalog=synthetic_catalog,
            suite=report["suite_verdict"],
            landings=report["properties"],
        )
        synthetic = {p["id"]: p for p in rebuilt}
        assert int(real["BP-68-2"]["measured"]) > 0, "BP-68-2 的实测空表数为 0，与本轮不符"
        assert int(synthetic["BP-68-2"]["measured"]) == 0, (
            "把所有表的行数换成非零后 BP-68-2 的度量值没变 ⇒ 它引用的是常量不是输入"
        )
        empty_landings = GATE.build_property_landings(
            [], [], {"digest": "synthetic", "files": {}}, {"state": "executed"}
        )
        rebuilt2 = {
            p["id"]: p
            for p in GATE.build_blocking_points(
                invariant_rows=report["invariants"],
                catalog=report["schema_catalog"],
                suite=report["suite_verdict"],
                landings=empty_landings,
            )
        }
        assert int(
            rebuilt2["BP-68-4"]["measured"]["deferred"]
        ) == len(GATE.DECLARED_PROPERTIES), "BP-68-4 没跟着 Property 落点变"

    def test_verdict_is_derived_and_names_its_blockers(self, report: dict[str, Any]) -> None:
        verdict = report["verdict"]
        assert verdict["result"] in (
            GATE.RESULT_PASSED,
            GATE.RESULT_FAILED,
            GATE.RESULT_UNVERIFIABLE,
        )
        recomputed = GATE.build_verdict(report)
        assert recomputed["result"] == verdict["result"], "判定不可复算"
        if verdict["result"] != GATE.RESULT_PASSED:
            assert (
                verdict["blockers"]
                or verdict["failed_invariants"]
                or verdict["failed_endpoint_checks"]
                or verdict["property_structural_errors"]
                or not verdict["restored"]
                or not verdict["suite_passed"]
            ), "判了不通过却说不出原因"

    def test_each_failure_source_drives_the_verdict_on_its_own(
        self, report: dict[str, Any]
    ) -> None:
        """判定的逐项反事实：从「一切干净」出发，每次只坏一项，结论必须变。

        🔴 直接用真实报告做反事实是无效的：它本来就多处不干净，`result` 早已不是 passed，
        任何「去掉某一项判据」的变异都会被别的失败掩盖（假绿）。
        """
        clean = _clean_report(report)
        assert GATE.build_verdict(clean)["result"] == GATE.RESULT_PASSED, (
            "合成的「一切干净」报告必须先判 passed（对照组）"
        )
        cases: list[tuple[str, Any, str]] = [
            ("behaviour_harness.error", "synthetic: PostgreSQL unreachable",
             GATE.RESULT_UNVERIFIABLE),
            ("schema_catalog.readable", False, GATE.RESULT_UNVERIFIABLE),
            ("behaviour_harness.probe_errors", {"delivery": "synthetic"},
             GATE.RESULT_UNVERIFIABLE),
            ("restoration.restored", False, GATE.RESULT_FAILED),
            ("invariants.0.passed", False, GATE.RESULT_FAILED),
            ("endpoint_checks.0.passed", False, GATE.RESULT_FAILED),
            ("properties.structural_errors", [{"kind": "synthetic"}], GATE.RESULT_FAILED),
            ("suite_verdict.passed", False, GATE.RESULT_FAILED),
        ]
        for path, value, expected in cases:
            broken = json.loads(json.dumps(clean))
            cursor: Any = broken
            parts = path.split(".")
            for part in parts[:-1]:
                cursor = cursor[int(part)] if part.isdigit() else cursor[part]
            cursor[parts[-1]] = value
            got = GATE.build_verdict(broken)["result"]
            assert got == expected, (
                f"只把 {path} 坏掉后判定是 {got}，期望 {expected} ⇒ 这一项没有单独参与判定"
            )

    def test_the_digest_expression_covers_the_whole_report(self, gate_ast: ast.Module) -> None:
        """`report_digest` 的取值来源必须是「整份报告减去自己」。

        🔴 只比对磁盘上的 digest 与现算值，对**门里**的 digest 表达式被缩窄毫无感知
        （两侧都会一起变小）。这里直接读 AST：必须遍历 `report.items()` 且只排除自身。
        """
        fn = GATE.function_def(gate_ast, "build_report")
        comps = [
            node
            for node in ast.walk(fn)
            if isinstance(node, ast.DictComp) and "report.items()" in ast.unparse(node)
        ]
        assert comps, (
            "digest 的取值来源不是「遍历整份报告」⇒ 报告可被任意手改而 digest 不变"
        )
        rendered = ast.unparse(comps[0])
        assert "report_digest" in rendered, "排除项不是 `report_digest` 自身"
        excluded = re.findall(r"key != '([^']+)'|key != \"([^\"]+)\"", rendered)
        flat = {a or b for a, b in excluded}
        assert flat == {"report_digest"}, f"除自身外还排除了别的键: {flat}"

    def test_the_report_carries_no_per_run_nondeterminism(self, report: dict[str, Any]) -> None:
        """报告里不得出现「每轮都变」的值，否则 `--check` 的逐字节锁永远对不上。

        🔴 首轮实测：`behaviour_harness.schema`（随机 hex）与 `elapsed_seconds`（墙钟）
        让 `--check` **必然**失败 —— 逐字节锁于是等于不存在，报告可被任意手改。
        """
        harness = report["behaviour_harness"]
        assert "schema" not in harness, "随机 schema 名进了报告"
        assert "elapsed_seconds" not in harness, "墙钟耗时进了报告"
        assert harness["schema_prefix"] == GATE._SCHEMA_PREFIX
        assert harness["schema_is_ephemeral"] is True
        for row in report["invariants"]:
            side = row["behaviour_side"]
            assert "scratch_schema" not in side, f"{row['check_id']} 记了随机 schema 名"
            assert side["scratch_schema_prefix"] == GATE._SCHEMA_PREFIX
        raw = json.dumps(report, ensure_ascii=False)
        assert not re.search(r"tmp_task68_reg_[0-9a-f]{6,}", raw), (
            "报告里出现了带随机后缀的 scratch schema 名"
        )
        # 拒绝理由里的 UUID / digest / DETAIL 行必须被规范化，否则逐字节锁永远对不上。
        rejections = [
            str(obs.get("rejection") or "")
            for obs in report["behaviour_harness"]["observations"].values()
        ]
        assert any(rejections), "一条拒绝理由都没有 ⇒ 否定臂全都没跑"
        for text in rejections:
            assert not re.search(
                r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text
            ), f"拒绝理由里残留 UUID: {text[:120]}"
            assert "Failing row contains" not in text, f"拒绝理由里残留 DETAIL 行: {text[:120]}"
        assert GATE.normalize_rejection(
            "23514||x 1413cf17-2b6a-48a8-98d2-5517bbe2b59d\nDETAIL:  Failing row contains (1,2)"
        ) == "23514||x <uuid>\nDETAIL:<row>", "规范化器本身不生效"
        assert "ck_wpcd_no_double_owner" in GATE.normalize_rejection(
            'violates check constraint "ck_wpcd_no_double_owner"\nDETAIL:  Failing row contains (x)'
        ), "规范化把承载判据的约束名也抹掉了"

    def test_report_digest_covers_everything_except_itself(self, report: dict[str, Any]) -> None:
        expected = GATE.digest_of({k: v for k, v in report.items() if k != "report_digest"})
        assert report["report_digest"] == expected, "报告可被手改而 digest 不变"
        tampered = {k: v for k, v in report.items() if k != "report_digest"}
        tampered["verdict"] = dict(tampered["verdict"], result="passed-by-hand")
        assert GATE.digest_of(tampered) != expected

    def test_cli_requires_exactly_one_mode(self) -> None:
        with pytest.raises(SystemExit):
            GATE.main([])
        with pytest.raises(SystemExit):
            GATE.main(["--check", "--write"])

    def test_run_suites_is_refused_without_write(self) -> None:
        assert GATE.main(["--check", "--run-suites"]) == 2, (
            "`--run-suites` 只能与 `--write` 同用（`--check` 必须复用磁盘上那次真实执行）"
        )
