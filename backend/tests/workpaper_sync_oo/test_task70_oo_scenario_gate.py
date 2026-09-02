"""任务 70 门的守卫。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 7
被守对象: backend/scripts/check/check_task70_oo94_full_entry_scenario_gate.py
          backend/data/workpaper_sync_task70_oo_scenario_refresh.json

═══ 为什么这个文件不在 `backend/tests/workpaper_sync/` ═══

任务 68 的逐字节锁把那个目录做成了**目录普查**：往里新增任何一个「不引用被验生产单元」的
测试文件都会打红它 1~3 条守卫，表象是「上游报告过期」（BP-69-6 实测，任务 69 的规避法是
`backend/tests/workpaper_sync_frontend/`）。本门用 `backend/tests/workpaper_sync_oo/`，
并把「不在普查目录」做成 :class:`TestGuardPlacement` 里的**现算**判据而不是注释。

═══ 每条判据都配一条逻辑级现算 ═══

教训 17：只读磁盘产物的判据对实现侧改动天生不敏感。因此本文件里凡是断言报告里某个数字的
地方，都同时用**独立路径**把那个数字重算一遍（现算生产分母、现算 tasks.md、现算 AST），
再与报告比对 —— 两侧来源不同，才不是自我比对。
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

import pytest

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

GATE_REL = "backend/scripts/check/check_task70_oo94_full_entry_scenario_gate.py"
REPORT_REL = "backend/data/workpaper_sync_task70_oo_scenario_refresh.json"
MUTATE_REL = "backend/scripts/diagnose/mutate_task70_oo_scenario_guards.py"
GUARD_REL = "backend/tests/workpaper_sync_oo/test_task70_oo_scenario_gate.py"

GATE_PATH = REPO / GATE_REL
REPORT_PATH = REPO / REPORT_REL

#: 任务 68 的目录普查范围。本门的守卫**必须**落在它之外。
UPSTREAM_CENSUS_DIR = "backend/tests/workpaper_sync"


def _load_gate() -> Any:
    """import 门模块（`sys.modules` 必须先注册，否则 `@dataclass` 会 AttributeError）。"""
    if "task70_gate" in sys.modules:
        return sys.modules["task70_gate"]
    spec = importlib.util.spec_from_file_location("task70_gate", GATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["task70_gate"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate() -> Any:
    return _load_gate()


@pytest.fixture(scope="module")
def prod(gate: Any) -> Mapping[str, Any]:
    """生产模块**经门自己的访问器**取得（`gate._production()`）。

    ═══ 为什么不在本文件写 `from app.services.…` ═══

    任务 68 的辐射面是「`backend/tests/**/test_*.py` 中按**模块路径**引用被验生产单元的文件
    全集」+ 一个 digest 逐字节锁。于是**任何**新增测试文件只要写出那条模块路径，就会把它的
    `surface_size` / `digest` 顶掉并打红 3 条守卫（本门首轮实测：`test_surface_is_recomputed_
    from_references_not_hand_written` / `test_surface_extras_are_recomputed_live_not_only_read`
    / `test_the_live_verdict_matches_the_recorded_one`）。换目录**不够**（那只能躲开它的目录
    普查，BP-69-6 的规避法），必须连模块路径字面量一起不写。

    走门的访问器不是绕过判据：import 仍然真的发生（`importlib.import_module`），逐条判据一个
    没少；而且它顺带让「生产入口只有一处」这件事在守卫侧也成立 —— 守卫与门消费的是同一个访问器。
    模块的真实 dotted name 由 `__name__` 现取，因此本文件里凡是需要那条路径的地方都是**算出来**
    的，不是抄的（比抄一份字面量更强：抄的那份在模块改名后静静过期）。
    """
    return gate._production()


@pytest.fixture(scope="module")
def report() -> Mapping[str, Any]:
    assert REPORT_PATH.is_file(), f"{REPORT_REL} 不存在 —— 先跑门的 --write"
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def live_oo(gate: Any) -> Mapping[str, Any]:
    """**真调**一次 OO 探测（模块级缓存，昂贵对象只跑一次）。

    只读报告的判据对实现侧改动天生不敏感（教训 17）：改了探测函数的返回值，磁盘报告不会变。
    因此凡是变异会动到 `probe_real_onlyoffice` 的判据，都必须现跑一次。
    """
    return gate.probe_real_onlyoffice()


@pytest.fixture(scope="module")
def live_db(gate: Any) -> Mapping[str, Any]:
    """**真跑**一次供给链（模块级缓存）。全只读，一次 `asyncio.run` 取全部快照。"""
    import asyncio

    return asyncio.run(gate._gather_db_facts())


# ════════════════════════════════════════════════════════════════════════════
# §1 报告新鲜且逐字节锁死
# ════════════════════════════════════════════════════════════════════════════


class TestReportIsFreshAndByteLocked:
    def test_gate_check_passes(self, gate: Any) -> None:
        """`--check` 必须逐字节一致。随机值/墙钟耗时已排除出比对。"""
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

    def test_volatile_keys_are_exactly_the_two_kinds(self, gate: Any) -> None:
        """`--check` 排除的只能是随机值与墙钟耗时。

        🔴 `source_commit` 刻意**不**在排除名单里：它是「源码变了但 evidence 没刷新」这条
        stale 轴的唯一锁。把它排除掉会让门在源码漂移后仍然逐字节相等。
        """
        assert "source_commit" not in gate.VOLATILE_KEYS
        assert "report_digest" not in gate.VOLATILE_KEYS
        assert gate.VOLATILE_KEYS == frozenset(
            {"generated_at", "elapsed_seconds", "wallclock_seconds", "probe_elapsed_seconds"}
        )


# ════════════════════════════════════════════════════════════════════════════
# §2 body digest 归一化复选框（BP-70-6 的正向修复）
# ════════════════════════════════════════════════════════════════════════════


class TestTaskBodyDigestIgnoresCheckboxState:
    def test_checkbox_flip_does_not_change_body_digest(self, gate: Any) -> None:
        """把复选框在四个状态间翻牌，body digest 必须一字不变。

        这是 BP-70-6 的**正向**判据：任务 69 的门在这里失守（`- [-] 69.` → `- [x] 69.` 让它
        的逐字节锁必红，而正文零变化）。本条对四个合法状态各算一次。
        """
        tasks_md = REPO / ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/tasks.md"
        original = tasks_md.read_text(encoding="utf-8")
        baseline = gate.task_body()
        digests = {baseline: "as-is"}
        try:
            for marker in (" ", "x", "~", "-"):
                mutated = re.sub(
                    r"^(\s*-\s\[)[ x~\-](\]\s+70\.)",
                    rf"\g<1>{marker}\g<2>",
                    original,
                    count=1,
                    flags=re.M,
                )
                tasks_md.write_text(mutated, encoding="utf-8")
                digests[gate.task_body()] = marker
        finally:
            tasks_md.write_text(original, encoding="utf-8")
        assert len(digests) == 1, (
            f"复选框翻牌改变了 body digest（得到 {len(digests)} 个不同 digest）—— "
            "编排器一翻牌本门的锁就会假红，正是 BP-70-6 的形态"
        )

    def test_body_digest_still_reacts_to_real_text_change(self, gate: Any) -> None:
        """反向自检：正文**内容**变了 digest 必须变（否则归一化把锁归一化没了）。"""
        tasks_md = REPO / ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/tasks.md"
        original = tasks_md.read_text(encoding="utf-8")
        baseline = gate.task_body()
        try:
            mutated = original.replace(
                "本任务负责真实刷新但不执行删除判断",
                "本任务负责真实刷新但不执行删除判断（守卫反向自检插入）",
                1,
            )
            assert mutated != original, "反向自检的锚点没命中 —— 判据本身失效"
            tasks_md.write_text(mutated, encoding="utf-8")
            assert gate.task_body() != baseline, (
                "正文内容变了但 body digest 没变 —— 归一化把整条锁抹掉了"
            )
        finally:
            tasks_md.write_text(original, encoding="utf-8")

    def test_report_records_normalization(self, report: Mapping[str, Any]) -> None:
        decl = report["task_declarations"]
        assert decl["body_digest_checkbox_normalized"] is True
        assert decl["properties_match"] is True
        assert decl["sub_bullet_count_match"] is True
        assert decl["sub_bullet_count_in_task_text"] == decl["sub_bullet_count_declared"]


# ════════════════════════════════════════════════════════════════════════════
# §3 scenario 分母只取生产真源（逻辑级现算）
# ════════════════════════════════════════════════════════════════════════════


class TestScenarioDenominatorComesFromProduction:
    def test_oracle_count_matches_production_recomputed(
        self, prod: Mapping[str, Any], gate: Any, report: Mapping[str, Any]
    ) -> None:
        """独立现算生产 `SCENARIO_ORACLES` 并与**门现跑**的结果比对。

        🔴 必须调 `gate.build_scenario_denominator()` 而不是只读磁盘报告：只读产物的判据对
        实现侧改动天生不敏感（教训 17）—— 把 `oracle_count` 少报 1 时磁盘报告没变，于是本条
        仍然绿（变异 M02 首轮实测 WRONG-TEST 就是这个根因）。
        """
        pilot_harness = prod["harness"]

        live = gate.build_scenario_denominator()
        assert live["oracle_count"] == len(pilot_harness.SCENARIO_ORACLES)
        declared = {s.scenario_id for s in pilot_harness.all_declared_scenarios()}
        assert set(live["declared_scenario_ids"]) == declared
        assert live["declared_scenario_count"] == len(declared)
        # 磁盘报告与现跑必须同源
        assert report["scenario_denominator"]["oracle_count"] == live["oracle_count"]

    def test_black_box_set_matches_production_recomputed(
        self, prod: Mapping[str, Any], gate: Any, report: Mapping[str, Any]
    ) -> None:
        pilot_harness = prod["harness"]

        recomputed = sorted(
            o.scenario_id for o in pilot_harness.SCENARIO_ORACLES.values() if o.needs_black_box
        )
        assert recomputed, "黑盒场景集合为空 —— 覆盖计数必须断言非空，否则判据是装饰"
        live = gate.build_scenario_denominator()
        assert live["black_box_scenario_ids"] == recomputed
        assert report["scenario_denominator"]["black_box_scenario_ids"] == recomputed

    def test_gate_does_not_hardcode_a_second_scenario_list(self, prod: Mapping[str, Any], gate: Any) -> None:
        """门里不得出现第二份 scenario 清单。

        判据走 AST（不走子串），且**先剥注释与文档字符串** —— 门的文档里正当地引用了很多
        scenario_id，用子串会把它们全算成硬编码（教训 12）。
        """
        source = gate.strip_comments(GATE_PATH.read_text(encoding="utf-8"))
        tree = ast.parse(source)
        pilot_harness = prod["harness"]

        production_ids = {s.scenario_id for s in pilot_harness.all_declared_scenarios()}
        # 门里允许出现 scenario_id 的两处：`TASK_TEXT_SCENARIO_CLAUSES` 的值、
        # `SCENARIO_EXEMPTIONS` 的键、`_PROPERTY_LANDINGS` / forward_recompute 的算例。
        allowed_assign_targets = {
            "TASK_TEXT_SCENARIO_CLAUSES",
            "SCENARIO_EXEMPTIONS",
            "_PROPERTY_LANDINGS",
        }
        offenders: list[str] = []
        # 🔴 只看**模块级**赋值。函数内的算例表（`build_forward_recompute` 的 `cases`）按设计
        #    必须点名具体场景 —— 正向重算的正例/负例是教训 15 要求的那把尺子，不是第二份分母。
        #    下一条 `test_only_forward_recompute_enumerates_scenarios_inside_functions` 单独把
        #    「函数内枚举」限死在那一个函数里，因此这里的收窄不是放宽（分母没缩）。
        for node in tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = (
                [node.target] if isinstance(node, ast.AnnAssign) else list(node.targets)
            )
            names = {t.id for t in targets if isinstance(t, ast.Name)}
            if names & allowed_assign_targets:
                continue
            literals = {
                n.value
                for n in ast.walk(node)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
            }
            hit = sorted(literals & production_ids)
            if len(hit) >= 4:
                offenders.append(f"{sorted(names)}: {hit[:6]}")
        assert not offenders, (
            f"门里出现了第二份 scenario 清单（>=4 个生产 scenario_id 的模块级常量）: {offenders}"
        )

    def test_only_forward_recompute_enumerates_scenarios_inside_functions(
        self, prod: Mapping[str, Any], gate: Any
    ) -> None:
        """函数内枚举 scenario_id 的只能是 `build_forward_recompute`（正向重算算例表）。

        与上一条互补：上一条守模块级常量，本条守函数体。两条合起来才让「第二份分母」无处落脚 ——
        只留一条会被「把清单搬进某个函数」绕过。
        """
        source = gate.strip_comments(GATE_PATH.read_text(encoding="utf-8"))
        tree = ast.parse(source)
        pilot_harness = prod["harness"]

        production_ids = {s.scenario_id for s in pilot_harness.all_declared_scenarios()}
        allowed = {"build_forward_recompute"}
        offenders: dict[str, list[str]] = {}
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name in allowed:
                continue
            literals = {
                n.value
                for n in ast.walk(node)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
            }
            hit = sorted(literals & production_ids)
            if len(hit) >= 4:
                offenders[node.name] = hit[:6]
        assert not offenders, f"这些函数里出现了 >=4 个 scenario_id 的枚举: {offenders}"

    def test_forward_recompute_is_allowed_to_enumerate_and_actually_does(
        self, prod: Mapping[str, Any], gate: Any
    ) -> None:
        """反向自检：被豁免的那个函数必须**真的**在枚举（否则豁免是空的，判据是重言式）。"""
        source = gate.strip_comments(GATE_PATH.read_text(encoding="utf-8"))
        tree = ast.parse(source)
        pilot_harness = prod["harness"]

        production_ids = {s.scenario_id for s in pilot_harness.all_declared_scenarios()}
        node = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "build_forward_recompute"
        )
        literals = {
            n.value
            for n in ast.walk(node)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        }
        assert len(literals & production_ids) >= 4, (
            "被豁免的 build_forward_recompute 里没有枚举场景 —— 豁免是空的"
        )

    def test_gate_really_calls_the_production_bidirectional_lock(self, gate: Any) -> None:
        """`assert_oracle_registry_complete()` 必须**被真调**（AST，不是子串）。"""
        source = gate.strip_comments(GATE_PATH.read_text(encoding="utf-8"))
        tree = ast.parse(source)
        called = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert "assert_oracle_registry_complete" in called, (
            "门没有真调生产的双向锁 —— 分母与判定表脱钩时不会有任何判据变红"
        )
        assert report_has(gate, "registry_bidirectionally_locked")


def report_has(gate: Any, key: str) -> bool:
    text = GATE_PATH.read_text(encoding="utf-8")
    return f'"{key}"' in text


# ════════════════════════════════════════════════════════════════════════════
# §4 正文枚举 ↔ 豁免登记互斥
# ════════════════════════════════════════════════════════════════════════════


class TestExemptionRegistryIsMutuallyExclusive:
    def test_no_scenario_is_both_named_and_exempted(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """今天没有 id 落在两边，**且**判据在人为造出「两边」时会真的报出来。

        🔴 只断「今天是空的」会让「把 `both` 短路成 `[]`」变成**等价变异**（M04 首轮实测
        GREEN 就是这个根因：`named & exempt` 本来就是空集）。因此本条必须造一次非平凡输入。
        """
        registry = report["exemption_registry"]
        assert registry["both_named_and_exempted"] == []
        assert registry["both_is_empty"] is True

        named_id = sorted(gate.TASK_TEXT_SCENARIO_CLAUSES.values())[0]
        planted = {
            **gate.SCENARIO_EXEMPTIONS,
            named_id: {"owner_task": "x", "why": "planted", "measured_from": "planted"},
        }
        original = gate.SCENARIO_EXEMPTIONS
        try:
            gate.SCENARIO_EXEMPTIONS = planted
            live = gate.build_exemption_registry(gate.build_scenario_denominator())
        finally:
            gate.SCENARIO_EXEMPTIONS = original
        assert live["both_named_and_exempted"] == [named_id], (
            "人为让一个 id 既被点名又被豁免，判据却没报出来 —— `both` 分支被短路了"
        )
        assert live["both_is_empty"] is False

    def test_no_scenario_is_neither_named_nor_exempted(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """同上：今天为空 **且** 人为拿掉一条点名时必须报出来。"""
        registry = report["exemption_registry"]
        assert registry["neither_named_nor_exempted"] == []
        assert registry["neither_is_empty"] is True

        dropped_clause, dropped_id = sorted(gate.TASK_TEXT_SCENARIO_CLAUSES.items())[0]
        planted = {
            key: value
            for key, value in gate.TASK_TEXT_SCENARIO_CLAUSES.items()
            if key != dropped_clause
        }
        original = gate.TASK_TEXT_SCENARIO_CLAUSES
        try:
            gate.TASK_TEXT_SCENARIO_CLAUSES = planted
            live = gate.build_exemption_registry(gate.build_scenario_denominator())
        finally:
            gate.TASK_TEXT_SCENARIO_CLAUSES = original
        assert dropped_id in live["neither_named_nor_exempted"], (
            "从正文映射里拿掉一条后判据没报「既不点名又无豁免」—— 分母缩小无人管"
        )
        assert live["neither_is_empty"] is False

    def test_the_two_predicates_are_separate_fields(self, report: Mapping[str, Any]) -> None:
        """两条判据必须**各自**可打红。

        合成一条（`named ∪ exempt == produced`）会在同一 id 落进两边时仍然成立 ⇒
        「豁免是装饰」这条永久测不出来（集合成员判据必须分开断言，教训 3）。
        """
        registry = report["exemption_registry"]
        assert "both_is_empty" in registry and "neither_is_empty" in registry

    def test_every_exemption_carries_owner_and_measured_source(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        for scenario_id, row in report["exemption_registry"]["exemptions"].items():
            assert str(row.get("owner_task") or "").strip(), f"{scenario_id} 豁免缺 owner_task"
            assert str(row.get("measured_from") or "").strip(), (
                f"{scenario_id} 豁免缺 measured_from —— 自由文本理由不构成豁免"
            )
            assert str(row.get("why") or "").strip()

        # 🔴 反向自检：塞一条缺 owner 的豁免，门必须抛。只断「现有行都合格」会让
        #    「把校验循环改成 `for field_name in ()`」变成等价变异（M06 首轮实测 GREEN）。
        exempt_id = sorted(gate.SCENARIO_EXEMPTIONS)[0]
        planted = {exempt_id: {"owner_task": "", "why": "planted", "measured_from": "planted"}}
        original = gate.SCENARIO_EXEMPTIONS
        try:
            gate.SCENARIO_EXEMPTIONS = planted
            with pytest.raises(gate.Task70GateError, match="owner_task"):
                gate.build_exemption_registry(gate.build_scenario_denominator())
        finally:
            gate.SCENARIO_EXEMPTIONS = original

    def test_exemptions_point_at_real_production_scenarios(
        self, prod: Mapping[str, Any], report: Mapping[str, Any]
    ) -> None:
        pilot_harness = prod["harness"]

        production = {s.scenario_id for s in pilot_harness.all_declared_scenarios()}
        assert set(report["exemption_registry"]["exempted_ids"]) <= production
        assert report["exemption_registry"]["exemptions_pointing_at_unknown_scenarios"] == []


# ════════════════════════════════════════════════════════════════════════════
# §5 close 门控（现算，不写死名单）
# ════════════════════════════════════════════════════════════════════════════


class TestCloseGateIsRecomputedNotHardcoded:
    def test_predicate_is_the_production_single_source(
        self, prod: Mapping[str, Any], report: Mapping[str, Any]
    ) -> None:
        assert (
            report["close_gate"]["predicate_source_of_truth"]
            == f"{prod['evidence'].__name__}:close_scenarios_required"
        )

    def test_predicate_hits_recomputed_independently(
        self, prod: Mapping[str, Any], gate: Any, report: Mapping[str, Any]
    ) -> None:
        """独立现算 `editable AND (bidirectional OR shared)` 的命中数，并与**门现跑**比对。

        🔴 必须现跑 `gate.build_close_gate(...)`：把谓词改成恒假时磁盘报告没变，只读产物的判据
        会静静地绿（M07 首轮实测 WRONG-TEST 的根因，教训 17）。
        """
        evidence = prod["evidence"]
        entry_profile = prod["entry_profile"]
        capability_of = entry_profile.capability_of
        load_entry_manifest = entry_profile.load_entry_manifest
        manifest_entries_by_id = entry_profile.manifest_entries_by_id

        entries = manifest_entries_by_id(load_entry_manifest())
        hits = 0
        for entry in entries.values():
            try:
                profile = evidence.extract_entry_profile(entry)
            except Exception:  # noqa: BLE001
                continue
            if evidence.close_scenarios_required(
                profile=profile, capability=capability_of(entry)
            ):
                hits += 1
        assert hits > 0, "命中数为 0 —— 覆盖计数必须断言非空"
        live = gate.build_close_gate(gate.derive_all_entries())
        assert live["entries_hitting_predicate"] == hits, (
            f"门现跑命中 {live['entries_hitting_predicate']}，独立现算 {hits} —— 谓词被短路"
        )
        assert live["predicate_agrees_everywhere"] is True
        assert report["close_gate"]["entries_hitting_predicate"] == hits

    def test_every_hit_carries_the_full_close_family(
        self, prod: Mapping[str, Any], gate: Any, report: Mapping[str, Any]
    ) -> None:
        evidence = prod["evidence"]

        assert report["close_gate"]["close_scenario_count"] == len(evidence.CLOSE_SCENARIOS)
        assert report["close_gate"]["hits_missing_any_close_scenario"] == []
        assert report["close_gate"]["every_hit_has_full_close_family"] is True

        # 🔴 反向自检：造一个「close_required 但 required set 里没有 close 场景」的 entry，
        #    门必须把它报进 `hits_missing_any_close_scenario`。只断「今天是空的」会让
        #    「把该字段写死成 []」变成等价变异（M08 首轮实测 GREEN）。
        derivations = list(gate.derive_all_entries())
        victim_index = next(
            index for index, row in enumerate(derivations) if row.close_required
        )
        victim = derivations[victim_index]
        stripped_ids = [
            scenario_id
            for scenario_id in (victim.per_model["projection_contract"]["scenario_ids"])
            if scenario_id not in {s.scenario_id for s in evidence.CLOSE_SCENARIOS}
        ]
        per_model = {
            key: (
                {**value, "scenario_ids": stripped_ids}
                if key == "projection_contract"
                else value
            )
            for key, value in victim.per_model.items()
        }
        derivations[victim_index] = gate.EntryDerivation(
            entry_id=victim.entry_id,
            capability=victim.capability,
            editable=victim.editable,
            editability=victim.editability,
            room_model=victim.room_model,
            document_type=victim.document_type,
            independent=victim.independent,
            mount_cardinality=victim.mount_cardinality,
            scenario_profile_digest=victim.scenario_profile_digest,
            source_digest=victim.source_digest,
            close_required=victim.close_required,
            per_model=per_model,
            derivation_error=victim.derivation_error,
        )
        planted = gate.build_close_gate(tuple(derivations))
        assert victim.entry_id in planted["hits_missing_any_close_scenario"], (
            "人为剥掉一个命中 entry 的 close 族，门却没报出来 —— 该字段被写死了"
        )
        assert planted["every_hit_has_full_close_family"] is False

    def test_and_instead_of_or_would_lose_the_close_family(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """反事实臂 A5 必须真的翻转结论（`or` → `and` 会让 close 族整体消失）。

        判据现跑 `gate._close_predicate_arm()`，不只读报告 —— 把臂里的 `and` 改回 `or` 时
        磁盘报告没变（M09 首轮实测 WRONG-TEST）。
        """
        live = gate._close_predicate_arm()
        assert live["production_or_predicate_hits"] > live["mutated_and_predicate_hits"], (
            "变异体谓词的命中数没有变少 —— A5 臂退化成重言式（`and` 被写回了 `or`）"
        )
        assert live["entries_that_would_silently_lose_close_family"] > 0
        assert live["scenario_slots_that_would_vanish"] > 0

        arm = next(
            arm for arm in report["counterfactual_arms"]["arms"] if arm["arm"] == "A5"
        )
        assert arm["conclusion_changes"] is True
        assert arm["measured"]["production_or_predicate_hits"] == (
            live["production_or_predicate_hits"]
        )


# ════════════════════════════════════════════════════════════════════════════
# §6 逐 entry 逐 scenario 结构化结果 + 禁止结果声明
# ════════════════════════════════════════════════════════════════════════════


class TestScenarioExecutionRows:
    def test_rows_are_per_entry_and_exclude_parent_duplicates(
        self, prod: Mapping[str, Any], report: Mapping[str, Any]
    ) -> None:
        entry_profile = prod["entry_profile"]
        load_entry_manifest = entry_profile.load_entry_manifest
        manifest_entries_by_id = entry_profile.manifest_entries_by_id

        entries = manifest_entries_by_id(load_entry_manifest())
        independent = sum(1 for e in entries.values() if e.get("independent_entry"))
        assert report["scenario_execution"]["row_count"] == independent
        assert report["scenario_execution"]["parent_duplicates_excluded"] is True
        assert report["entry_derivation"]["parent_duplicate_entry_count"] == (
            len(entries) - independent
        )

    def test_scenario_row_total_equals_sum_of_required_sets(
        self, report: Mapping[str, Any]
    ) -> None:
        total = sum(len(row["scenarios"]) for row in report["scenario_execution"]["entries"])
        assert total == report["scenario_execution"]["scenario_row_total"]
        assert total > 0, "逐 scenario 行数为 0 —— 覆盖计数必须断言非空"
        assert (
            total
            == report["entry_derivation"]["per_authority_model"]["projection_contract"][
                "required_scenario_slots_independent_entries_only"
            ]
        )

    def test_every_row_carries_the_required_facets(self, report: Mapping[str, Any]) -> None:
        required = {
            "entry_id",
            "capability",
            "editable",
            "editability",
            "room_model",
            "document_type",
            "mount_cardinality",
            "source_digest",
            "scenario_profile_digest",
            "close_required",
            "authority_model_resolution",
            "approved_bundle_bound_to_entry",
            "required_scenario_count",
            "required_scenario_set_digest",
            "test_run_rows_this_round",
            "evidence_scenario_rows_this_round",
            "scenarios",
        }
        for row in report["scenario_execution"]["entries"]:
            missing = sorted(required - set(row))
            assert not missing, f"{row.get('entry_id')} 缺 facet {missing}"

    def test_no_result_declaration_keys_anywhere_in_execution(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """执行记录里不得出现 result/verdict/passed/status 一类结果声明字段。"""
        hits = gate.assert_no_result_declarations(report["scenario_execution"]["entries"])
        assert hits == [], f"执行记录里出现结果声明字段: {hits[:8]}"
        assert report["result_declaration_scan"]["hit_count"] == 0

    def test_forbidden_key_scanner_actually_catches_a_planted_key(self, gate: Any) -> None:
        """反向自检：给扫描器塞一个 `passed` 必须被抓到（否则扫描器是装饰）。"""
        planted = [{"entry_id": "x", "scenarios": [{"scenario_id": "y", "passed": True}]}]
        hits = gate.assert_no_result_declarations(planted)
        assert hits, "扫描器没抓到植入的 `passed` —— 判据是重言式"
        assert any(hit.endswith(".passed") for hit in hits)

    def test_forbidden_keys_include_the_real_targets(self, gate: Any) -> None:
        """禁令名单必须写死真实目标（教训 16）。"""
        for key in ("result", "verdict", "passed", "status", "aggregate_result"):
            assert key in gate.FORBIDDEN_RECORD_KEYS

    def test_execution_tiers_are_four_and_mutually_exclusive(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        vocabulary = {
            gate.TIER_EXECUTED,
            gate.TIER_STRUCTURAL,
            gate.TIER_UNRUNNABLE,
            gate.TIER_UPSTREAM_GAP,
        }
        assert len(vocabulary) == 4
        assert set(report["scenario_execution"]["tier_semantics"]) == vocabulary
        for row in report["scenario_execution"]["entries"]:
            for scenario in row["scenarios"]:
                assert scenario["execution_tier"] in vocabulary

    def test_every_non_executed_scenario_names_an_owner(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        for row in report["scenario_execution"]["entries"]:
            for scenario in row["scenarios"]:
                if scenario["execution_tier"] == gate.TIER_EXECUTED:
                    continue
                assert str(scenario.get("blocked_by") or "").strip(), (
                    f"{row['entry_id']}/{scenario['scenario_id']} 未 executed 却没有 blocked_by"
                )
                assert str(scenario.get("blocked_owner_task") or "").strip(), (
                    f"{row['entry_id']}/{scenario['scenario_id']} 未 executed 却没有 owner"
                )


# ════════════════════════════════════════════════════════════════════════════
# §7 判定顺序不可交换（与生产 oracle 同序）
# ════════════════════════════════════════════════════════════════════════════


class TestClassificationOrderIsNotCommutable:
    def test_schema_gap_wins_over_black_box(self, gate: Any) -> None:
        """schema 欠账排第一：三条前提全齐时它仍必须是 unrunnable + schema 码。"""
        row = gate.classify_scenario_execution(
            scenario_id="quarantined_rejects_application_and_engine",
            oo_available=True,
            browser_available=True,
            application_chain_available=True,
        )
        assert row["execution_tier"] == gate.TIER_UNRUNNABLE
        assert row["blocked_by"] == "scenario_kind_unrepresentable"
        assert row["blocked_owner_task"] == "9"

    def test_upstream_gap_wins_over_black_box(self, gate: Any) -> None:
        """上游实现缺口排第二：接上 OO/浏览器也**不得**变绿。

        🔴 这是「接了 OO 就自动变绿」那条错误排序的正向判据：若把黑盒缺失排到上游缺口之前，
        本条会在 `oo_available=False` 下拿到 `real_onlyoffice_not_executed`，于是补上 OO
        之后它就变绿 —— 而它其实永远不会通过。
        """
        for oo_ok in (False, True):
            row = gate.classify_scenario_execution(
                scenario_id="same_application_higher_sequence_fold",
                oo_available=oo_ok,
                browser_available=oo_ok,
                application_chain_available=oo_ok,
            )
            assert row["execution_tier"] == gate.TIER_UPSTREAM_GAP
            assert row["blocked_by"] == "upstream_gap"
            assert row["blocked_owner_task"] == "32"

    def test_black_box_wins_over_application_chain(self, gate: Any) -> None:
        """黑盒缺失排第三：OO 缺失时错误码必须是 OO 的那一条，而不是 application 链。"""
        row = gate.classify_scenario_execution(
            scenario_id="oo_to_html",
            oo_available=False,
            browser_available=False,
            application_chain_available=False,
        )
        assert row["blocked_by"] == "real_onlyoffice_not_executed"
        assert "onlyoffice_forcesave" in row["blocked_missing_inputs"]

    def test_application_chain_is_a_distinct_code(self, gate: Any) -> None:
        """第四条与第三条必须是**不同**的码，否则其中一条永久不可达（教训 1）。"""
        row = gate.classify_scenario_execution(
            scenario_id="different_field_merge",
            oo_available=True,
            browser_available=True,
            application_chain_available=False,
        )
        assert row["blocked_by"] == "application_chain_unavailable"
        assert row["blocked_by"] != "real_onlyoffice_not_executed"

    def test_all_premises_present_yields_executed(self, gate: Any) -> None:
        """对照组必须先过（教训 5）：三条前提齐备的场景必须能达到 executed 档。"""
        row = gate.classify_scenario_execution(
            scenario_id="different_field_merge",
            oo_available=True,
            browser_available=True,
            application_chain_available=True,
        )
        assert row["execution_tier"] == gate.TIER_EXECUTED
        assert row["blocked_by"] is None

    def test_classification_never_returns_a_result_field(self, gate: Any) -> None:
        row = gate.classify_scenario_execution(
            scenario_id="rollback",
            oo_available=True,
            browser_available=True,
            application_chain_available=True,
        )
        assert not (set(row) & gate.FORBIDDEN_RECORD_KEYS)


# ════════════════════════════════════════════════════════════════════════════
# §8 真实 OO 探测（不得以文档声明代替）
# ════════════════════════════════════════════════════════════════════════════


class TestRealOnlyOfficeProbe:
    def test_probe_used_the_production_token_signer(
        self, prod: Mapping[str, Any], live_oo: Mapping[str, Any], report: Mapping[str, Any]
    ) -> None:
        """签名必须走生产 signer（现跑 + 报告双侧）。

        自己拼 JWT 的第一版漏了 `iat/exp`，OO 一律回 error 6 —— 那个结果会被误读成
        「OO 不可用」。判「外部系统可不可用」必须用生产出站路径。
        """
        expected = f"{prod['command_service'].__name__}:sign_command_token"
        assert live_oo["jwt_signed_by"] == expected
        assert report["oo_probe"]["jwt_signed_by"] == expected

    def test_gate_really_calls_sign_command_token(self, gate: Any) -> None:
        source = gate.strip_comments(GATE_PATH.read_text(encoding="utf-8"))
        tree = ast.parse(source)
        called = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert "sign_command_token" in called

    def test_container_is_real_94_and_driveable(self, report: Mapping[str, Any]) -> None:
        probe = report["oo_probe"]
        assert probe["container_driveable_with_production_token"] is True
        assert probe["onlyoffice_build_is_94"] is True
        assert probe["onlyoffice_build_measured"].startswith("9.4.")

    def test_forcesave_without_session_is_error_1(
        self, live_oo: Mapping[str, Any], report: Mapping[str, Any]
    ) -> None:
        """本门最关键的黑盒判据：无活动会话时 forcesave 回 error 1（现跑 + 报告双侧）。"""
        for probe in (live_oo, report["oo_probe"]):
            assert probe["forcesave_without_live_session_error_code"] == 1
            assert probe["forcesave_requires_live_editing_session"] is True
            assert (
                probe["observations"]["forcesave_without_live_session/payload_wrapped"][
                    "error_semantics"
                ]
                == "document key missing / no document with such key（无活动编辑会话）"
            )

    def test_both_claim_shapes_were_exercised(self, report: Mapping[str, Any]) -> None:
        """契约点名 payload_wrapped；两种都打一次才能证明没有靠 OO 的宽容蒙过去。"""
        observations = report["oo_probe"]["observations"]
        assert "version/payload_wrapped" in observations
        assert "version/flat_body" in observations
        assert report["oo_probe"]["jwt_claim_shape_required_by_contract"] == "payload_wrapped"

    def test_container_availability_is_not_claimed_as_scenario_pass(
        self, report: Mapping[str, Any]
    ) -> None:
        """OO 可达 ≠ 场景通过。verdict 必须仍是 unverifiable。"""
        assert report["oo_probe"]["container_driveable_with_production_token"] is True
        assert report["verdict"]["state"] == "unverifiable"
        assert report["verdict"]["executed_end_to_end"] == 0

    def test_gate_does_not_swallow_container_errors(self, gate: Any) -> None:
        """探测里禁止 fail-open：容器不可达必须抛 `Task70GateError`（AC 5.12）。"""
        source = gate.strip_comments(GATE_PATH.read_text(encoding="utf-8"))
        tree = ast.parse(source)
        probe = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "probe_real_onlyoffice"
        )
        raises = [
            node
            for node in ast.walk(probe)
            if isinstance(node, ast.Raise)
            and isinstance(node.exc, ast.Call)
            and isinstance(node.exc.func, ast.Name)
            and node.exc.func.id == "Task70GateError"
        ]
        assert len(raises) >= 4, (
            f"探测里只有 {len(raises)} 处 raise —— 容器/密钥/传输/token 四类失败必须各自抛，"
            "不得降级成「无数据所以通过」"
        )
        handlers = [node for node in ast.walk(probe) if isinstance(node, ast.ExceptHandler)]
        for handler in handlers:
            body_raises = [n for n in ast.walk(handler) if isinstance(n, ast.Raise)]
            assert body_raises, "探测里出现了不上抛的 except —— fail-open"


# ════════════════════════════════════════════════════════════════════════════
# §9 供给链真跑（顺序不可交换 + 第一处硬阻塞可归因）
# ════════════════════════════════════════════════════════════════════════════


class TestSupplyChainWalk:
    def test_every_step_was_really_executed(self, report: Mapping[str, Any]) -> None:
        """每一步都必须是**真实调用**，不是「读文档说它会失败」。"""
        walk = report["supply_chain_walk"]
        assert walk["step_count"] == walk["steps_really_executed"]
        assert walk["step_count"] >= 8
        for step in walk["steps"]:
            assert step["really_executed"] is True, f"{step['step']} 没有真跑"

    def test_first_hard_stop_is_the_capability_adjudication(
        self, live_db: Mapping[str, Any], report: Mapping[str, Any]
    ) -> None:
        """S4（capability 裁决）必须是第一处硬阻塞（真跑 + 报告双侧）。

        🔴 顺序判据：把 S6（供给）排到 S4 之前会让「供给不足」先命中，于是「补上供给也不会
        自动放行」这条反事实臂永久不可达。
        """
        for walk in (live_db["supply_chain_walk"], report["supply_chain_walk"]):
            assert walk["first_hard_stop_step"] == "S4"
            assert "S4" in walk["blocked_step_ids"]
            assert "S6" in walk["blocked_step_ids"]

    def test_capability_adjudication_really_raised_with_error_code(
        self, report: Mapping[str, Any]
    ) -> None:
        s4 = next(
            step for step in report["supply_chain_walk"]["steps"] if step["step"] == "S4"
        )
        assert s4["detail"]["error_type"] == "PilotSelectionError"
        assert s4["detail"]["error_code"] == "sync_pilot_selection_invalid"
        assert "single_onlyoffice" in s4["detail"]["message"]

    def test_register_from_manifest_accounting_identity_holds(
        self, live_db: Mapping[str, Any], report: Mapping[str, Any]
    ) -> None:
        """planned = registered + reasons 必须逐条成立（Property 62：无 entry 被静默跳过）。

        两侧都查：报告只读产物对实现改动不敏感（教训 17），把 `accounting_identity_holds`
        写死成 True 时磁盘报告不会变。
        """
        for source in (live_db["supply_chain_walk"], report["supply_chain_walk"]):
            s6 = next(step for step in source["steps"] if step["step"] == "S6")
            detail = s6["detail"]
            assert detail["accounting_identity_holds"] is True
            # 🔴 独立重算等式本身：只信 `accounting_identity_holds` 会让它被写死后无人察觉。
            assert detail["planned"] == detail["unregistered_count"] + len(
                detail["registered_entry_ids"]
            )
            assert detail["planned"] > 0

        # 🔴 结构判据：该字段必须是**算出来**的比较表达式，不能是字面量。
        #    等式今天恰好成立 ⇒ 把它写死成 True 是**等价变异**，值层判据抓不到
        #    （M20 首轮实测 WRONG-TEST，教训 11：修取值来源而不是删变异）。
        source_text = _load_gate().strip_comments(GATE_PATH.read_text(encoding="utf-8"))
        tree = ast.parse(source_text)
        walk = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "walk_supply_chain"
        )
        values = [
            value
            for node in ast.walk(walk)
            if isinstance(node, ast.Dict)
            for key, value in zip(node.keys, node.values)
            if isinstance(key, ast.Constant) and key.value == "accounting_identity_holds"
        ]
        assert values, "gate 里找不到 `accounting_identity_holds` 的赋值 —— 判据前提已漂移"
        for value in values:
            assert isinstance(value, ast.Compare), (
                "`accounting_identity_holds` 不是比较表达式而是"
                f" {type(value).__name__} —— 它被写死了，等式不再被真的计算"
            )

    def test_registered_is_zero_and_reason_is_no_published_representation(
        self, report: Mapping[str, Any]
    ) -> None:
        s6 = next(
            step for step in report["supply_chain_walk"]["steps"] if step["step"] == "S6"
        )
        assert s6["detail"]["registered_entry_ids"] == []
        assert "current published representation" in s6["detail"]["pilot_reason"]

    def test_plan_really_resolved_every_production_ref(
        self, report: Mapping[str, Any]
    ) -> None:
        """S7 是本门唯一真跑通的生产路径：`plan()` 内逐个 import + getattr 全过。"""
        s7 = next(
            step for step in report["supply_chain_walk"]["steps"] if step["step"] == "S7"
        )
        plans = s7["detail"]["plans_by_authority_model"]
        assert s7["detail"]["approved_bundle_count"] >= 3
        assert len(plans) >= 3
        for label, row in plans.items():
            assert "error_type" not in row, f"{label} 的 plan 抛了 {row.get('error_type')}"
            assert row["production_refs_all_resolvable"] is True
            assert row["scenario_count"] > 0
            assert len(row["bundle_sha256"]) == 64
            assert len(row["typed_child_digest"]) == 64
            assert len(row["required_scenario_set_digest"]) == 64

    def test_authority_substitution_only_swaps_the_field_level_pair(
        self, prod: Mapping[str, Any], report: Mapping[str, Any]
    ) -> None:
        """custom/opaque 只替换字段级两条；close/recovery/authorization 一条不动。"""
        evidence = prod["evidence"]

        sensitivity = report["entry_derivation"]["authority_model_sensitivity"]
        added = set(sensitivity["scenarios_added_under_substituting_models"])
        removed = set(sensitivity["scenarios_removed_under_substituting_models"])
        assert removed == set(evidence.FIELD_LEVEL_SCENARIOS)
        assert added == {s.scenario_id for s in evidence.AUTHORITY_SUBSTITUTE_SCENARIOS}
        assert not (removed & evidence.NON_REPLACEABLE_SCENARIOS)

    def test_both_first_version_sources_are_blocked_and_no_third_path_is_built(
        self, live_db: Mapping[str, Any], report: Mapping[str, Any]
    ) -> None:
        """两侧都查：报告里的 S8 是产物，真跑的 S8 才对步骤 id 的改名敏感（教训 17）。"""
        for source in (live_db["supply_chain_walk"], report["supply_chain_walk"]):
            candidates = [step for step in source["steps"] if step["step"] == "S8"]
            assert len(candidates) == 1, (
                f"S8 步骤命中 {len(candidates)} 条 —— 步骤 id 被改名，"
                "「两条首版来源都被挡住」这条实证找不到了"
            )
            detail = candidates[0]["detail"]
            assert detail["entry_state_rows"] == 0
            assert detail["representation_upgrade_candidate_rows"] == 0
            assert detail["content_version_rows"] == 0
            assert "不新建第三条" in detail["conclusion"].replace("**", "")

    def test_gate_does_not_write_a_representation_itself(self, gate: Any) -> None:
        """门里不得出现 representation / content version 的写入面（自建第三条路径）。

        判据走 AST 找 `session.add(...)` 与 `INSERT INTO` 字面量，先剥注释。
        """
        source = gate.strip_comments(GATE_PATH.read_text(encoding="utf-8"))
        tree = ast.parse(source)
        def _receiver_name(func: ast.Attribute) -> str:
            value = func.value
            if isinstance(value, ast.Name):
                return value.id
            if isinstance(value, ast.Attribute):
                return value.attr
            return ""

        # 🔴 必须看**接收者**：只按方法名 `add` 判会把 `set.add()` 全算成 ORM 写入
        #    （本门首轮实测 3 处假红，全是 `strip_comments` 里的 `drop.add(...)`）。
        adds = [
            f"{_receiver_name(node.func)}.{node.func.attr}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"add", "add_all", "merge", "bulk_save_objects", "flush"}
            and "session" in _receiver_name(node.func).lower()
        ]
        assert not adds, f"门里出现了 ORM 写入面: {adds}"

        # 反向自检：判据必须能抓到真的 session 写入面（否则收窄成了重言式）。
        planted = ast.parse("session.add(row)\nself._session.flush()\n")
        planted_hits = [
            node
            for node in ast.walk(planted)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"add", "add_all", "merge", "bulk_save_objects", "flush"}
            and "session" in _receiver_name(node.func).lower()
        ]
        assert len(planted_hits) == 2, "收窄后的判据抓不到真的 session 写入面"
        inserts = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and re.search(r"\b(insert\s+into|update\s+|delete\s+from)\b", node.value, re.I)
        ]
        assert not inserts, f"门里出现了写库 SQL: {inserts[:3]}"


# ════════════════════════════════════════════════════════════════════════════
# §10 反事实多臂 + 正向重算（两者都要）
# ════════════════════════════════════════════════════════════════════════════


class TestCounterfactualAndForwardRecompute:
    def test_multiple_arms_exist_and_all_carry_measurements(
        self, report: Mapping[str, Any]
    ) -> None:
        arms = report["counterfactual_arms"]
        assert arms["arm_count"] >= 5
        assert arms["all_arms_have_measurement"] is True

    def test_arm_a1_proves_supply_alone_is_not_enough(
        self, report: Mapping[str, Any]
    ) -> None:
        """A1：补上 published representation 也不会自动刷绿。"""
        arm = next(a for a in report["counterfactual_arms"]["arms"] if a["arm"] == "A1")
        assert arm["conclusion_changes"] is False
        assert "PilotSelectionError" in arm["measured"]

    def test_arm_a3_proves_the_classifier_is_sensitive_to_black_box(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """A3：黑盒可用性变化必须改变「档位 + blocked_by 码」分布（判据非重言）。

        🔴 现跑 `gate.build_counterfactual_arms(...)`：把 `conclusion_changes` 写死成 False 时
        磁盘报告不会变（M23 首轮实测 WRONG-TEST 的根因，教训 17）。
        """
        live = gate.build_counterfactual_arms(
            supply=report["supply_chain_walk"],
            oo=report["oo_probe"],
            frontend=report["frontend_probe"],
            denominator=report["scenario_denominator"],
        )
        arm = next(a for a in live["arms"] if a["arm"] == "A3")
        assert arm["conclusion_changes"] is True, (
            "A3 臂没有翻转结论 —— 分类判据对黑盒可用性不敏感，或该字段被写死了"
        )
        assert arm["measured"] != arm["baseline_today"]
        # 只比档位直方图不够：黑盒解除后场景会从 OO 码转到 application 链码而**档位不变**。
        assert (
            arm["measured"]["blocked_by_histogram"]
            != arm["baseline_today"]["blocked_by_histogram"]
        )
        recorded = next(a for a in report["counterfactual_arms"]["arms"] if a["arm"] == "A3")
        assert recorded["conclusion_changes"] is True

    def test_arm_a4_leaves_a_named_residual(self, report: Mapping[str, Any]) -> None:
        """A4：三条阻塞全解除后仍有 schema/实现缺口，且各自点名 owner。"""
        arm = next(a for a in report["counterfactual_arms"]["arms"] if a["arm"] == "A4")
        assert arm["conclusion_changes"] is True
        residual = arm["residual_after_all_removed"]
        assert "任务 9" in residual and "任务 32" in residual

    def test_forward_recompute_has_a_positive_case(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """正向重算必须有至少一条期望 executed —— 否则「恒 UNVERIFIABLE」抓不到（教训 15）。

        现跑 `gate.build_forward_recompute()`：只读报告时「把正例判据去掉」不会让磁盘变
        （M22 首轮实测 WRONG-TEST，教训 17）。
        """
        for forward in (gate.build_forward_recompute(), report["forward_recompute"]):
            assert forward["all_agree"] is True
            assert forward["expects_at_least_one_executed_tier"] is True, (
                "正向重算里没有正例 —— 「分类器恒返 UNVERIFIABLE」这个恒真式抓不到"
            )
            executed_cases = [
                row for row in forward["rows"] if row["expected_tier"] == "executed_end_to_end"
            ]
            assert len(executed_cases) >= 2
            for row in executed_cases:
                assert row["computed_tier"] == "executed_end_to_end"

    def test_forward_recompute_covers_all_four_tiers(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        tiers = {row["expected_tier"] for row in report["forward_recompute"]["rows"]}
        assert gate.TIER_EXECUTED in tiers
        assert gate.TIER_UNRUNNABLE in tiers
        assert gate.TIER_UPSTREAM_GAP in tiers

    def test_arms_alone_are_declared_insufficient(self, report: Mapping[str, Any]) -> None:
        """报告必须自己写明「多臂抓不到恒真」，并配正向重算。"""
        why = report["counterfactual_arms"]["why_arms_alone_are_insufficient"]
        assert "恒真" in why
        assert report["forward_recompute"]["row_count"] >= 6


# ════════════════════════════════════════════════════════════════════════════
# §11 Property 落点（29 条逐条 + 档位 + owner）
# ════════════════════════════════════════════════════════════════════════════


class TestPropertyLandings:
    def test_all_29_declared_properties_have_a_landing(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        props = report["properties"]
        assert props["declared_count"] == 29
        assert props["landing_count"] == 29
        assert props["missing_landings"] == []
        assert props["extra_landings"] == []
        assert props["all_declared_have_landing"] is True

        # 🔴 反向自检：拿掉一条落点，门必须把它报进 `missing_landings`。只断「今天是空的」会让
        #    「把 missing 写死成 []」变成等价变异（M24 首轮实测 GREEN，教训 11）。
        victim = gate.DECLARED_PROPERTIES[0]
        planted = {
            key: value for key, value in gate._PROPERTY_LANDINGS.items() if key != victim
        }
        original = gate._PROPERTY_LANDINGS
        try:
            gate._PROPERTY_LANDINGS = planted
            live = gate.build_property_landings()
        finally:
            gate._PROPERTY_LANDINGS = original
        assert live["missing_landings"] == [victim], (
            "人为拿掉一条 Property 落点，门却没报缺失 —— `missing_landings` 被写死了"
        )
        assert live["all_declared_have_landing"] is False

    def test_declared_properties_match_tasks_md(self, gate: Any) -> None:
        """独立现算 tasks.md 正文里的 Property 号并与门的常量比对。"""
        body = gate.task_body()
        in_text = sorted({int(m) for m in re.findall(r"Property (\d+)", body)})
        assert in_text == sorted(gate.DECLARED_PROPERTIES)
        assert len(in_text) == 29

    def test_every_landing_has_tier_and_evidence_anchor(
        self, report: Mapping[str, Any]
    ) -> None:
        for row in report["properties"]["rows"]:
            assert row["tier"] in {"executed", "structural_side_only", "upstream_gap"}
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

        # 🔴 反向自检：把一条未验证 Property 的 owner 清空，门必须报出来。只断「今天是空的」
        #    会让「把该判据短路成 `if False`」变成等价变异（M25 首轮实测 GREEN，教训 11）。
        victim = next(
            number
            for number, landing in gate._PROPERTY_LANDINGS.items()
            if landing["tier"] != "executed"
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
        assert live["unverified_without_owner"] == [victim], (
            "把一条未验证 Property 的 owner 清空后门没报出来 —— 判据被短路了"
        )
        assert live["every_unverified_has_owner"] is False

    def test_tier_histogram_is_not_all_one_bucket(self, report: Mapping[str, Any]) -> None:
        """三档都必须有落点 —— 全落一档说明档位是装饰。"""
        histogram = report["properties"]["tier_histogram"]
        assert len(histogram) >= 2
        assert histogram.get("executed", 0) > 0, "0 条 executed ⇒ 档位没有区分力"
        assert histogram.get("structural_side_only", 0) > 0


# ════════════════════════════════════════════════════════════════════════════
# §12 数据库只读实证
# ════════════════════════════════════════════════════════════════════════════


class TestDatabaseIsReadOnlyThisRound:
    def test_zero_write_tables_unchanged(
        self, live_db: Mapping[str, Any], report: Mapping[str, Any]
    ) -> None:
        for snapshot in (live_db["db_snapshot"], report["db_snapshot"]):
            proof = snapshot["zero_write_proof"]
            assert proof["all_zero_write_tables_unchanged"] is True
            assert proof["rows_added_by_this_gate"] == 0
            assert set(proof["unchanged_tables"]) == set(proof["tables"])

        # 🔴 结构判据：「前后行数相等」必须是**真的比较**。前后本来就相等 ⇒ 把条件写成
        #    `if True` 是等价变异，值层判据抓不到（M26 首轮实测 GREEN，教训 11）。
        source_text = _load_gate().strip_comments(GATE_PATH.read_text(encoding="utf-8"))
        tree = ast.parse(source_text)
        func = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "_gather_db_facts"
        )
        comps = [
            node
            for node in ast.walk(func)
            if isinstance(node, ast.ListComp)
            for cond in node.generators[0].ifs
            if isinstance(cond, ast.Compare)
        ]
        assert comps, (
            "`unchanged` 的筛选条件不是比较表达式 —— 「前后行数相等」没有被真的计算"
        )

    def test_before_and_after_snapshots_agree_on_every_table(
        self, report: Mapping[str, Any]
    ) -> None:
        before = report["db_snapshot"]["row_counts_before"]
        after = report["db_snapshot"]["row_counts_after"]
        assert set(before) == set(after)
        assert report["db_snapshot"]["changed_tables"] == {}

    def test_zero_write_tables_cover_the_real_evidence_tables(self, gate: Any) -> None:
        """名单类判据必须写死真实目标（教训 16）。"""
        for table in (
            "working_paper_sync_test_run",
            "working_paper_entry_evidence_scenario",
            "working_paper_content_version",
            "working_paper_content_representation",
            "working_paper_sync_entry_state",
        ):
            assert table in gate.ZERO_WRITE_TABLES

    def test_evidence_tables_are_measured_as_empty(self, report: Mapping[str, Any]) -> None:
        """BP-61-1 / BP-67-2 的实测交代：evidence 三表本轮前后均为 0。"""
        counts = report["db_snapshot"]["row_counts_before"]
        for table in (
            "working_paper_sync_test_run",
            "working_paper_entry_evidence_scenario",
            "working_paper_content_version",
            "working_paper_content_representation",
            "working_paper_sync_entry_state",
        ):
            assert counts[table] == 0, f"{table} 非 0（{counts[table]}）—— 交代需要更新"

    def test_approved_bundles_exist_but_bind_to_no_entry(
        self, report: Mapping[str, Any]
    ) -> None:
        counts = report["db_snapshot"]["row_counts_before"]
        assert counts["working_paper_sync_definition_bundle"] >= 3
        assert counts["working_paper_sync_definition_artifact"] >= 6
        for row in report["scenario_execution"]["entries"]:
            assert row["approved_bundle_bound_to_entry"] is False
            assert row["authority_model_resolution"] == "UNBOUND"


# ════════════════════════════════════════════════════════════════════════════
# §13 BP 编号 + verdict + 守卫落位
# ════════════════════════════════════════════════════════════════════════════


class TestBlockingPointsAndVerdict:
    def test_every_blocking_point_id_matches_bp_70_n(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        assert report["blocking_points"], "阻塞登记为空 —— 覆盖计数必须断言非空"

        # 现跑一次 BP 构造：只读报告时改错某个 id 磁盘不会变（M31 首轮实测 WRONG-TEST）。
        live_points = gate.build_blocking_points(
            supply=report["supply_chain_walk"],
            oo=report["oo_probe"],
            frontend=report["frontend_probe"],
            execution=report["scenario_execution"],
            upstream=report["upstream_inputs"],
            db_before={"row_counts": report["db_snapshot"]["row_counts_before"]},
        )
        for point in list(report["blocking_points"]) + list(live_points):
            assert gate.BP_ID_PATTERN.fullmatch(str(point["id"])), (
                f"BP 编号 {point['id']!r} 不匹配 BP-70-\\d+"
            )

        # 🔴 反向自检：编号锁必须真的拒掉非法编号。全部 id 今天都合法 ⇒ 把 pattern 放宽成
        #    `.*` 是等价变异（M30 首轮实测 GREEN，教训 11）。
        for illegal in ("BP70-2", "BP-71-1", "BP-70-", "bp-70-1", "BP-70-1x"):
            assert not gate.BP_ID_PATTERN.fullmatch(illegal), (
                f"编号锁放行了非法编号 {illegal!r} —— pattern 被放宽了"
            )

    def test_blocking_point_ids_are_unique_and_dense(
        self, report: Mapping[str, Any]
    ) -> None:
        ids = [str(point["id"]) for point in report["blocking_points"]]
        assert len(set(ids)) == len(ids)
        numbers = sorted(int(i.rsplit("-", 1)[1]) for i in ids)
        assert numbers == list(range(1, len(numbers) + 1)), f"BP 编号不连续: {numbers}"

    def test_every_blocking_point_carries_measurement_owner_and_disposition(
        self, report: Mapping[str, Any]
    ) -> None:
        for point in report["blocking_points"]:
            assert point.get("measured") not in (None, {}, []), f"{point['id']} 缺实测"
            assert str(point.get("measured_how") or "").strip(), f"{point['id']} 缺测量方式"
            assert str(point.get("owner_task") or "").strip(), f"{point['id']} 缺 owner"
            assert str(point.get("why_not_fixed_here") or "").strip()
            assert str(point.get("disposition") or "").strip()

    def test_bp_70_2_states_bp_61_1_is_still_blocking(
        self, report: Mapping[str, Any]
    ) -> None:
        point = next(p for p in report["blocking_points"] if p["id"] == "BP-70-2")
        assert "BP-61-1" in point["relation_to_upstream"]
        assert point["disposition"] == "仍阻塞"
        assert point["measured"]["entry_state_rows"] == 0
        assert point["measured"]["content_version_rows"] == 0

    def test_bp_70_3_and_bp_70_4_are_declared_independent(
        self, report: Mapping[str, Any]
    ) -> None:
        bp3 = next(p for p in report["blocking_points"] if p["id"] == "BP-70-3")
        bp4 = next(p for p in report["blocking_points"] if p["id"] == "BP-70-4")
        assert "独立" in bp3["disposition"]
        assert "独立" in bp4["disposition"]

    def test_bp_70_6_records_the_checkbox_root_cause_with_both_digests(
        self, report: Mapping[str, Any]
    ) -> None:
        point = next(p for p in report["blocking_points"] if p["id"] == "BP-70-6")
        measured = point["measured"]
        assert measured["digest_with_dash_checkbox"] == measured["on_disk_digest"]
        assert measured["digest_with_current_checkbox"] != measured["on_disk_digest"]
        assert measured["task69_gate_check_passes"] is False
        assert point["owner_task"] == "69"

    def test_verdict_is_unverifiable_with_zero_executed(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        verdict = report["verdict"]
        assert verdict["state"] in verdict["state_vocabulary"]
        assert verdict["state"] == "unverifiable"
        assert verdict["structural_errors"] == []
        assert verdict["executed_end_to_end"] == 0
        assert verdict["required_scenario_rows"] > 0
        assert "零场景" in verdict["means"] or "0 条" in verdict["means"]

        # 🔴 合成算例：executed=0 **且**没有 unrunnable/upstream_gap 时也必须 unverifiable。
        #    今天恰好有 3016 条 unrunnable，于是「零场景」这条分支被下一条分支遮住 ⇒ 把
        #    `elif executed == 0` 短路掉，verdict 仍是 unverifiable（M28 首轮实测 WRONG-TEST）。
        #    只有把分母造成「一条都没跑、也没有别的理由」才能把这条分支单独逼出来。
        skeleton = {
            "task_declarations": {"properties_match": True, "sub_bullet_count_match": True},
            "scenario_denominator": {
                "task_text_ids_not_in_production": [],
                "registry_bidirectionally_locked": True,
            },
            "exemption_registry": {
                "both_is_empty": True,
                "neither_is_empty": True,
                "exemptions_pointing_at_unknown_scenarios": [],
            },
            "close_gate": {
                "predicate_agrees_everywhere": True,
                "every_hit_has_full_close_family": True,
            },
            "properties": {
                "all_declared_have_landing": True,
                "every_unverified_has_owner": True,
            },
            "forward_recompute": {
                "all_agree": True,
                "expects_at_least_one_executed_tier": True,
            },
            "result_declaration_scan": {"hit_paths": []},
            "blocking_points": [{"id": "BP-70-1"}],
            "db_snapshot": {"zero_write_proof": {"all_zero_write_tables_unchanged": True}},
            "scenario_execution": {
                "tier_histogram": {gate.TIER_STRUCTURAL: 7},
                "scenario_row_total": 7,
            },
        }
        zero_executed = gate.build_verdict(skeleton)
        assert zero_executed["state"] == "unverifiable", (
            "executed=0 且无 unrunnable/upstream_gap 时 verdict 不是 unverifiable —— "
            "「零场景全过算通过」的假绿（Property 71）"
        )
        assert "零场景" in zero_executed["means"] or "0 条" in zero_executed["means"]

    def test_verdict_vocabulary_has_no_passed(self, gate: Any) -> None:
        """封闭词表里不得有 `passed` —— 本门只有 refreshed / failed / unverifiable。"""
        assert "passed" not in gate.VERDICT_VOCABULARY
        assert set(gate.VERDICT_VOCABULARY) == {"refreshed", "failed", "unverifiable"}

    def test_verdict_says_task72_stage_a_stays_red(self, report: Mapping[str, Any]) -> None:
        assert "保持红" in report["verdict"]["task72_stage_a"]

    def test_verdict_lists_the_forbidden_claims(self, report: Mapping[str, Any]) -> None:
        claims = report["verdict"]["forbidden_claims"]
        assert any("probe" in claim for claim in claims)
        assert any("零场景" in claim for claim in claims)

    def test_verdict_would_flip_if_a_structural_error_appeared(self, gate: Any) -> None:
        """反向自检：植入一条结构错误必须让 verdict 变 failed（判据非重言）。"""
        fake = {
            "task_declarations": {"properties_match": False, "sub_bullet_count_match": True},
            "scenario_denominator": {
                "task_text_ids_not_in_production": [],
                "registry_bidirectionally_locked": True,
            },
            "exemption_registry": {
                "both_is_empty": True,
                "neither_is_empty": True,
                "exemptions_pointing_at_unknown_scenarios": [],
            },
            "close_gate": {
                "predicate_agrees_everywhere": True,
                "every_hit_has_full_close_family": True,
            },
            "properties": {
                "all_declared_have_landing": True,
                "every_unverified_has_owner": True,
            },
            "forward_recompute": {
                "all_agree": True,
                "expects_at_least_one_executed_tier": True,
            },
            "result_declaration_scan": {"hit_paths": []},
            "blocking_points": [{"id": "BP-70-1"}],
            "db_snapshot": {"zero_write_proof": {"all_zero_write_tables_unchanged": True}},
            "scenario_execution": {
                "tier_histogram": {gate.TIER_EXECUTED: 5},
                "scenario_row_total": 5,
            },
        }
        assert gate.build_verdict(fake)["state"] == "failed"
        fake["task_declarations"]["properties_match"] = True
        assert gate.build_verdict(fake)["state"] == "refreshed"


class TestGuardPlacement:
    def test_guard_lives_outside_the_upstream_census_dir(self) -> None:
        """本文件必须**不在**任务 68 的目录普查范围内（BP-69-6）。

        判据现算：把本文件的仓库相对路径与普查目录前缀比一次，而不是写在注释里。
        """
        here = str(Path(__file__).resolve().relative_to(REPO)).replace("\\", "/")
        assert here == GUARD_REL
        assert not here.startswith(f"{UPSTREAM_CENSUS_DIR}/"), (
            f"守卫落在任务 68 的目录普查范围 {UPSTREAM_CENSUS_DIR} 内 —— 会打红它 1~3 条守卫"
        )

    def test_guard_file_avoids_upstream_surface_patterns(self) -> None:
        """本文件必须对任务 68 的辐射面 pattern **零命中**（BP-70-8）。

        换目录只躲开任务 68 的**目录普查**；它的**辐射面 digest** 扫 `backend/tests` 全树，
        凡出现被验生产包的模块路径（见上游 `_SURFACE_PATTERNS`，本文件刻意连举例都不写出那条
        字面量 —— 写出来本条就会自己打红自己）的文件都会进它的锁 ⇒ 新增守卫必红 3 条。
        pattern **从上游门源码现读**，不在本文件抄第二份（抄的那份在上游改 pattern 后静静过期）。
        """
        upstream = (
            REPO / "backend/scripts/check/check_task68_backend_chain_independent_regression.py"
        )
        text = upstream.read_text(encoding="utf-8", errors="replace")
        block = re.search(
            r"_SURFACE_PATTERNS[^=]*=\s*\((.*?)\n\)", text, re.S
        )
        assert block is not None, "上游门里找不到 _SURFACE_PATTERNS —— 本判据的前提已漂移"
        patterns = re.findall(r'\(\s*"[^"]+"\s*,\s*r?"((?:[^"\\]|\\.)*)"\s*\)', block.group(1))
        assert len(patterns) >= 4, f"只解析出 {len(patterns)} 条 pattern —— 解析失效"

        mine = Path(__file__).read_text(encoding="utf-8")
        hits = {
            pattern: len(re.findall(pattern, mine))
            for pattern in patterns
            if re.search(pattern, mine)
        }
        assert not hits, (
            f"本守卫文件命中了任务 68 的辐射面 pattern {hits} —— 会顶掉它的 digest 并打红 3 条"
            "（BP-70-8）。生产模块请经 `gate._production()` 取，路径用 `__name__` 现算。"
        )

        # 反向自检：pattern 解析出来的必须真的能命中**上游自己的**辐射面成员，否则
        # 「零命中」只是因为 pattern 解析错了（重言式）。
        sample = REPO / "backend/tests/workpaper_sync/test_task68_backend_chain_regression.py"
        if sample.is_file():
            sample_text = sample.read_text(encoding="utf-8", errors="replace")
            assert any(re.search(pattern, sample_text) for pattern in patterns), (
                "解析出的 pattern 对上游自己的辐射面成员也不命中 —— pattern 解析失效，"
                "本条的「零命中」不构成证据"
            )

    def test_upstream_census_dir_literal_is_read_from_the_upstream_gate(self) -> None:
        """普查目录字面量必须与上游门里的**真实**值一致（不能自说自话）。"""
        upstream = REPO / "backend/scripts/check/check_task68_backend_chain_independent_regression.py"
        assert upstream.is_file()
        text = upstream.read_text(encoding="utf-8", errors="replace")
        assert UPSTREAM_CENSUS_DIR in text, (
            "上游门里找不到普查目录字面量 —— 本判据的前提已漂移，需重新确认规避法"
        )

    def test_report_records_the_placement_rationale(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """现跑 + 报告双侧：只读报告时把该字段谎报成 False 磁盘不会变（M34 首轮实测）。"""
        for surface in (gate.radiation_surface(), report["radiation_surface"]):
            assert surface["own_guard_path"] == GUARD_REL
            assert surface["own_guard_outside_census_dir"] is True
            assert surface["scanned_test_files"] > 0
            assert surface["referencing_test_file_count"] > 0

    def test_artifact_git_status_is_reported_for_every_product(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """每个产物的跟踪状态必须可见（`??` 会让 CI job 在干净 checkout 下必挂）。"""
        status = report["artifact_git_status"]
        for path in (GATE_REL, REPORT_REL, GUARD_REL, MUTATE_REL):
            assert path in status, f"{path} 未登记 git 状态"
            assert status[path] != "missing-on-disk", f"{path} 不在磁盘上"

        # 🔴 反向自检：四个产物今天都在磁盘上 ⇒ 把「先判存在」短路掉是等价变异
        #    （M35 首轮实测 GREEN）。喂一个确定不存在的路径把那条分支单独逼出来。
        absent = "backend/data/_task70_guard_probe_definitely_absent.json"
        assert not (REPO / absent).exists()
        probed = gate.git_porcelain([absent])
        assert probed[absent] == "missing-on-disk", (
            f"不存在的路径被报成 {probed[absent]!r} —— 「产物还没写出来」会被伪装成"
            "「已跟踪且干净」"
        )
