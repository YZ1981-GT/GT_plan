# -*- coding: utf-8 -*-
"""任务 70 门 —— 第五批四条判据的守卫（证据档位 / 能力分桶 / 文档择路 / 环境分型）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Task 6.3

═══ 为什么单开一个文件 ═══

这四条修复是 2026-11-05 第五批加的，交付时**守卫侧零覆盖** —— 四个判据在
`backend/tests/workpaper_sync_oo/**` 里一条断言都没有（grep
`evidence_not_recorded` / `PENDING_CAPABILITY_BUCKET` / `measurement_is_environment_limited`
/ `spec_doc(` 全树零命中）。按方法论铁律⑳「每条判据至少被某份守卫引用」补齐。
不并进宿主是因为宿主 1565 行已贴着行数门 whitelist 基线（1694 行的 +5% 是 1778），
照 `test_task70_supply_chain.py` 的既有范式新开文件。

═══ 每条都配反向控制 ═══

四条修复里**三条今天恰好「不触发」**（证据 0 行 / 没有区分类 entry / storage 已补齐），
只断言「现在的值」等于把环境快照冻进判据 —— 铁律②⑮：结构性零必须配变异证明。
所以每个类都给出「触发态」与「不触发态」两组输入，并断言两者结论相反：

* 证据档位：无证据 ⇒ 降档；有证据 ⇒ **放行**（可伪证，真跑出 evidence 后自然变绿）。
* 能力分桶：pending ⇒ ``pending`` 桶，且 `capability_of` 对同一条 entry 真的抛
  （反事实前提不成立时这条修复本身是空的）。
* 文档择路：活跃目录那份**真的不含**要找的正文（否则按内容择路是空转）。
* 环境分型：根在 + 零失败 ⇒ 不受限；根在 + 有失败 ⇒ **受限**（只看根存在会漏这一支）。
"""
from __future__ import annotations

import importlib.util
import re
import sys
import types
from pathlib import Path
from typing import Any, Mapping

import pytest

_HOST_PATH = Path(__file__).with_name("test_task70_oo_scenario_gate.py")
_spec = importlib.util.spec_from_file_location("_task70_evidence_host", _HOST_PATH)
assert _spec is not None and _spec.loader is not None
_host = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _host
_spec.loader.exec_module(_host)

gate = _host.gate  # noqa: F811  fixture 需在本模块命名空间
report = _host.report  # noqa: F811  同上
live_db = _host.live_db  # noqa: F811  同上
prod = _host.prod  # noqa: F811  同上

REPO = _host.REPO


def _derivation(gate_mod: Any, entry_id: str, scenario_ids: list[str]) -> Any:
    """最小 `EntryDerivation`：只填 `build_scenario_execution` 真会读的字段。

    字段全集按 `dataclasses.fields` 现读（铁律㉑：接口先现读再动笔），非本判据关心的
    用占位值；`per_model["projection_contract"]` 是唯一真载荷。
    """
    return gate_mod.EntryDerivation(
        entry_id=entry_id,
        capability="bidirectional",
        editable=True,
        editability="editable",
        room_model="shared",
        document_type="xlsx",
        independent=True,
        mount_cardinality="single",
        scenario_profile_digest="0" * 64,
        source_digest="1" * 64,
        close_required=True,
        per_model={
            "projection_contract": {
                "scenario_ids": list(scenario_ids),
                "required_scenario_set_digest": "2" * 64,
            }
        },
        derivation_error=None,
    )


def _two_scenarios_that_clear_all_five_layers(gate_mod: Any) -> list[str]:
    """五层阻塞全清后会落 `TIER_EXECUTED` 的 scenario —— 本类判据的素材。

    现算而不是写死 id：词表改名后写死的那两条会静静变成「分类函数不认识的 id」，
    于是降档断言在**错误的理由**下仍然绿（教训：变异 RED 要核对红在哪一条）。
    """
    evidence = gate_mod._production()["evidence"]
    ids: set[str] = set()
    for const in ("CLOSE_SCENARIOS", "FIELD_LEVEL_SCENARIOS", "PROJECTION_BASE_SCENARIOS"):
        for item in getattr(evidence, const, ()) or ():
            ids.add(str(getattr(item, "scenario_id", item)))
    clear = sorted(
        sid
        for sid in ids
        if gate_mod.classify_scenario_execution(
            scenario_id=sid,
            oo_available=True,
            browser_available=True,
            application_chain_available=True,
        )["execution_tier"]
        == gate_mod.TIER_EXECUTED
    )
    assert len(clear) >= 2, (
        "没有任何 scenario 在五层全清后落 executed ⇒ 本类判据的素材塌了，"
        "降档断言会在「本来就不是 executed」的理由下假绿"
    )
    return clear[:2]


# ════════════════════════════════════════════════════════════════════════════
# §1 `executed_end_to_end` 必须有证据（第五批抓到的假绿）
# ════════════════════════════════════════════════════════════════════════════


class TestExecutedTierRequiresEvidence:
    """档位语义是「本轮端到端真跑并有可重算证据」，不是「今天能跑」。

    🔴 实测形态（2026-11-05）：给工作树补上 storage 副本、注入 OO 密钥、3030 又在监听
    之后，黑盒与 application 链两层同时解除，`classify_scenario_execution` 的五层逐层
    排除再也排不掉任何东西 ⇒ **1206/1608 行瞬间变「已执行」**，而
    `working_paper_sync_test_run` 与 `working_paper_entry_evidence_scenario` 都是 0 行。
    这正是门禁文件头点名要防的「接了 OO 就自动变绿」。
    """

    def test_no_evidence_downgrades_every_runnable_scenario(self, gate: Any) -> None:
        """五层全清 + 零证据 ⇒ 一条都不许记成已执行。"""
        first, second = _two_scenarios_that_clear_all_five_layers(gate)
        result = gate.build_scenario_execution(
            [_derivation(gate, "synthetic/entry-a", [first, second])],
            oo_available=True,
            browser_available=True,
            application_chain_available=True,
            recorded_evidence={"test_run_rows": 0, "evidence_scenario_rows": 0,
                               "passed_pairs": []},
        )
        assert result["scenario_row_total"] == 2
        assert gate.TIER_EXECUTED not in result["tier_histogram"], (
            "零证据却有行落在 executed 档 ⇒ 假绿复发"
        )
        assert result["tier_histogram"].get(gate.TIER_UNRUNNABLE) == 2
        scenarios = [
            scenario
            for entry in result["entries"]
            for scenario in entry["scenarios"]
        ]
        assert len(scenarios) == 2, "逐场景明细丢了 ⇒ 降档理由无从核对"
        for scenario in scenarios:
            assert scenario["execution_tier"] == gate.TIER_UNRUNNABLE
            assert scenario["blocked_by"] == "evidence_not_recorded"
            assert str(scenario["blocked_owner_task"]) == str(gate.OWNER_TASK)
            assert "passed" in scenario["blocked_detail"]

    def test_recorded_evidence_really_unlocks_the_executed_tier(self, gate: Any) -> None:
        """🔴 可伪证方向：有 `result='passed'` 的证据对 ⇒ 该场景**放行**。

        少了这一条，「证据档」就退化成「永远降档」—— 那是另一种假门禁（恒红等于没有门禁），
        真把 6.3 跑通之后报告也不会变绿，没人会相信这个数字。
        """
        first, second = _two_scenarios_that_clear_all_five_layers(gate)
        result = gate.build_scenario_execution(
            [_derivation(gate, "synthetic/entry-a", [first, second])],
            oo_available=True,
            browser_available=True,
            application_chain_available=True,
            recorded_evidence={
                "test_run_rows": 1,
                "evidence_scenario_rows": 1,
                "passed_pairs": [("synthetic/entry-a", first)],
            },
        )
        histogram = result["tier_histogram"]
        assert histogram.get(gate.TIER_EXECUTED) == 1, (
            f"有证据的那一条没放行（直方图 {histogram}）⇒ 档位恒降，门禁恒红"
        )
        assert histogram.get(gate.TIER_UNRUNNABLE) == 1, (
            f"没证据的那一条被一起放行了（直方图 {histogram}）⇒ 证据不是逐对匹配的"
        )

    def test_evidence_is_matched_per_entry_not_per_scenario(self, gate: Any) -> None:
        """证据对是 (entry_id, scenario_id) 二元组 —— 换一条 entry 不得蹭到放行。"""
        first, _second = _two_scenarios_that_clear_all_five_layers(gate)
        result = gate.build_scenario_execution(
            [_derivation(gate, "synthetic/entry-b", [first])],
            oo_available=True,
            browser_available=True,
            application_chain_available=True,
            recorded_evidence={
                "test_run_rows": 1,
                "evidence_scenario_rows": 1,
                "passed_pairs": [("synthetic/entry-a", first)],
            },
        )
        assert gate.TIER_EXECUTED not in result["tier_histogram"], (
            "别的 entry 的证据让本 entry 放行了 ⇒ 证据只按 scenario 匹配"
        )

    def test_recorded_evidence_only_counts_passed_rows(self, gate: Any) -> None:
        """取数侧：SQL 必须只认 ``result = 'passed'``，并真的经 run_id 回到 entry。"""
        source = Path(gate.__file__).with_name("_task70_gate_env.py").read_text(
            encoding="utf-8"
        )
        body = source[source.index("async def recorded_evidence(") :]
        body = body[: body.index("\ndef ") if "\ndef " in body else len(body)]
        assert "result = 'passed'" in body, "证据查询不再按 result='passed' 过滤"
        assert "working_paper_sync_test_run" in body and "r.id = s.run_id" in body, (
            "证据查询不再经 run_id 回到 entry ⇒ entry 维度的匹配无从谈起"
        )

    def test_live_evidence_counts_are_internally_consistent(
        self, live_db: Mapping[str, Any]
    ) -> None:
        """真库侧不变式（不冻结今天的 0）：没有 run 就不可能有通过对。"""
        facts = live_db["recorded_evidence"]
        pairs = list(facts["passed_pairs"])
        assert len(pairs) <= int(facts["evidence_scenario_rows"]), (
            "通过对比证据行还多 ⇒ 取数口径错了"
        )
        if int(facts["test_run_rows"]) == 0:
            assert not pairs, "一条 run 都没有却有通过对 ⇒ join 失效"

    def test_report_executed_count_never_exceeds_evidence(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """报告侧不变式：已执行行数 ≤ 通过对数。"""
        execution = report["scenario_execution"]
        executed = int(execution["tier_histogram"].get(gate.TIER_EXECUTED, 0))
        assert executed <= int(execution["recorded_evidence"]["passed_pair_count"]), (
            "报告里的已执行行数超过证据对数 ⇒ 档位又不看证据了"
        )


# ════════════════════════════════════════════════════════════════════════════
# §2 能力分桶容纳未裁决态
# ════════════════════════════════════════════════════════════════════════════


class TestCapabilityBucketHandlesPending:
    """门禁原来用 `capability_of` 统计含 pending entry 的能力分布 ⇒ 整门崩在第一条上。"""

    def test_pending_entry_goes_to_the_pending_bucket(self, gate: Any, prod: Mapping[str, Any]) -> None:
        env = _env_module(gate)
        entry_profile = prod["entry_profile"]
        pending, adjudicated = _pending_and_adjudicated(entry_profile)
        assert env.capability_bucket(entry_profile, pending) == env.PENDING_CAPABILITY_BUCKET
        expected = entry_profile.effective_capability(adjudicated).value
        assert env.capability_bucket(entry_profile, adjudicated) == expected

    def test_capability_of_really_raises_on_the_same_entry(
        self, prod: Mapping[str, Any]
    ) -> None:
        """🔴 反事实前提：若 `capability_of` 不再抛，这条修复本身就是空的。"""
        entry_profile = prod["entry_profile"]
        pending, _ = _pending_and_adjudicated(entry_profile)
        with pytest.raises(Exception) as excinfo:  # noqa: PT011  生产异常类型由生产定义
            entry_profile.capability_of(pending)
        assert "EntryProfileError" in type(excinfo.value).__name__, (
            f"抛的是 {type(excinfo.value).__name__} —— 不是 pending 裁决那一类错误"
        )
        assert entry_profile.effective_capability(pending) is None

    def test_pending_bucket_is_not_a_capability_member(self, prod: Mapping[str, Any]) -> None:
        """``pending`` 不得混进封闭四态（混进去就等于悄悄开了第五种能力）。"""
        entry_profile = prod["entry_profile"]
        env = _env_module(_host._load_gate())
        members = {member.value for member in entry_profile.Capability}
        assert env.PENDING_CAPABILITY_BUCKET not in members

    def test_report_histogram_covers_every_entry_and_is_recomputed(
        self, report: Mapping[str, Any], prod: Mapping[str, Any]
    ) -> None:
        """报告直方图：桶集合封闭、加总等于 entry 总数、pending 数现算对得上。

        不冻结「86 条 pending」—— 那是裁决进度，会随上游推进变化；冻结它等于
        要求裁决停下来（第五批对 S8 三项计数做过同样的改正）。
        """
        distributions = _capability_distributions(report)
        entry_profile = prod["entry_profile"]
        entries = entry_profile.manifest_entries_by_id(entry_profile.load_entry_manifest())
        env = _env_module(_host._load_gate())
        allowed = {member.value for member in entry_profile.Capability}
        allowed.add(env.PENDING_CAPABILITY_BUCKET)
        recomputed: dict[str, int] = {}
        for entry in entries.values():
            bucket = env.capability_bucket(entry_profile, entry)
            recomputed[bucket] = recomputed.get(bucket, 0) + 1
        for path, histogram in distributions.items():
            assert set(histogram) <= allowed, (
                f"{path} 出现了词表外的桶：{set(histogram) - allowed}"
            )
            assert sum(histogram.values()) == len(entries), (
                f"{path} 加总 {sum(histogram.values())} != entry 总数 {len(entries)}"
                " ⇒ 有 entry 被静默跳过（原来 pending entry 让整门抛在第一条上）"
            )
            assert histogram == recomputed, (
                f"{path} 与按 `capability_bucket` 重算的分布不一致：{histogram} vs {recomputed}"
            )


def _env_module(gate_mod: Any) -> Any:
    """拆出去的环境模块 —— 经门模块所在目录定位，不写生产 dotted path。"""
    path = Path(gate_mod.__file__).with_name("_task70_gate_env.py")
    spec = importlib.util.spec_from_file_location("_task70_gate_env_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pending_and_adjudicated(entry_profile: Any) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """manifest 里现取一条未裁决与一条已裁决 entry。"""
    entries = entry_profile.manifest_entries_by_id(entry_profile.load_entry_manifest())
    pending = adjudicated = None
    for entry in entries.values():
        try:
            effective = entry_profile.effective_capability(entry)
        except Exception:  # noqa: BLE001  本判据只要样本，解析不了的跳过
            continue
        if effective is None and pending is None:
            pending = entry
        elif effective is not None and adjudicated is None:
            adjudicated = entry
        if pending is not None and adjudicated is not None:
            return pending, adjudicated
    pytest.skip(f"manifest 里缺样本（pending={pending is not None} / 已裁决={adjudicated is not None}）")
    raise AssertionError("unreachable")


def _capability_distributions(report: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    """报告里**全部**能力分布 —— 按路径收集，缺失即失败（不 skip）。

    🔴 首版写成「键里同时含 capability 与 histogram」的模糊查找，而真实键是
    `capability_distribution`（不含 histogram）⇒ 一条都找不到、`pytest.skip` 把整条
    判据变成空转。集合类判据必须断言分母非空（铁律：守卫自己也要可伪证）。
    """
    found: dict[str, dict[str, int]] = {}

    def visit(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                here = f"{path}.{key}"
                if (
                    isinstance(key, str)
                    and key == "capability_distribution"
                    and isinstance(value, dict)
                ):
                    found[here] = {str(name): int(count) for name, count in value.items()}
                visit(value, here)
        elif isinstance(node, list):
            for index, item in enumerate(node):
                visit(item, f"{path}[{index}]")

    visit(report, "")
    assert found, "报告里一处 `capability_distribution` 都没有 ⇒ 能力分布没进报告"
    return found


# ════════════════════════════════════════════════════════════════════════════
# §3 spec 文档按内容择路（两代目录都存在）
# ════════════════════════════════════════════════════════════════════════════


class TestSpecDocRoutesByContent:
    def test_task_body_is_resolved_to_the_file_that_really_contains_it(
        self, gate: Any
    ) -> None:
        path = gate.tasks_md()
        pattern = rf"^\s*-\s\[[ x~\-]\]\s+{gate.TASK_NUMBER}\."
        assert re.search(pattern, path.read_text(encoding="utf-8"), re.M), (
            f"{path} 里找不到任务 {gate.TASK_NUMBER} 正文 ⇒ 择路选错了一代"
        )

    def test_existence_only_routing_would_pick_the_wrong_generation(
        self, gate: Any
    ) -> None:
        """🔴 反事实：活跃目录那份 tasks.md **真的不含**任务 70 正文。

        若两代内容一样，「按内容择路」就是空转 —— 这条断言是那条修复的存在理由。
        """
        env = _env_module(gate)
        by_existence = env.spec_doc(REPO, gate.SPEC, "tasks.md")
        by_content = gate.tasks_md()
        pattern = rf"^\s*-\s\[[ x~\-]\]\s+{gate.TASK_NUMBER}\."
        if by_existence == by_content:
            pytest.skip("两代 tasks.md 已合并，按内容择路暂不可区分")
        assert not re.search(pattern, by_existence.read_text(encoding="utf-8"), re.M), (
            f"{by_existence} 其实含任务 {gate.TASK_NUMBER} 正文 ⇒ 不需要按内容择路"
        )

    def test_design_property_is_resolved_to_the_file_that_declares_it(
        self, gate: Any
    ) -> None:
        path = gate.design_md()
        first = min(gate.DECLARED_PROPERTIES)
        assert re.search(rf"^###\s+Property\s+{first}\b", path.read_text(encoding="utf-8"), re.M)

    def test_unfindable_content_raises_a_named_error_with_candidates(
        self, gate: Any
    ) -> None:
        """找不到时必须点名候选路径（否则「哪一代」要靠猜）。"""
        env = _env_module(gate)
        with pytest.raises(env.SpecDocNotFoundError) as excinfo:
            env.spec_doc(REPO, gate.SPEC, "tasks.md",
                         must_contain=r"^- \[x\] 任务编号绝不存在-9f3c\b")
        message = str(excinfo.value)
        assert "候选" in message and ".kiro/specs" in message.replace("\\", "/")

    def test_missing_spec_dir_also_raises_instead_of_returning_a_ghost_path(
        self, gate: Any, tmp_path: Path
    ) -> None:
        env = _env_module(gate)
        with pytest.raises(env.SpecDocNotFoundError):
            env.spec_doc(tmp_path, gate.SPEC, "tasks.md")


# ════════════════════════════════════════════════════════════════════════════
# §4 storage 缺失记成环境事实，不记成供给事实
# ════════════════════════════════════════════════════════════════════════════


def _failure(error_code: str) -> Any:
    return types.SimpleNamespace(error_code=error_code)


class TestArtifactEnvironmentIsRecorded:
    """`storage/` 不入库 ⇒ 干净检出里 registered 恒被压到 0。那是环境，不是供给。

    A/B 实测（2026-11-05，同一份代码同一个库）：无 storage 副本的 worktree
    registered **0** / artifact_publish_failed **59**；补上 59 份产物后
    registered **32** / 真实漂移 **27**（16 published_identity_observed_drift
    + 11 sync_contract_structure_drift）。
    """

    def test_missing_storage_root_is_environment_limited(
        self, gate: Any, tmp_path: Path
    ) -> None:
        env = _env_module(gate)
        info = env.artifact_environment(tmp_path, {})
        assert info["storage_root_exists"] is False
        assert info["project_dirs"] == 0
        assert env.measurement_is_environment_limited(info) is True

    def test_present_storage_with_no_failures_is_not_environment_limited(
        self, gate: Any, tmp_path: Path
    ) -> None:
        """🔴 反向控制：不触发态必须判 False，否则这条分型恒真、等于没分型。"""
        env = _env_module(gate)
        (tmp_path / "storage").mkdir()
        info = env.artifact_environment(tmp_path, {})
        assert info["storage_root_exists"] is True
        assert info["artifact_publish_failed_count"] == 0
        assert env.measurement_is_environment_limited(info) is False

    def test_present_but_empty_storage_with_failures_is_environment_limited(
        self, gate: Any, tmp_path: Path
    ) -> None:
        """🔴 只看「根是否存在」会漏掉这一支 —— 临时 worktree 实测就是它。"""
        env = _env_module(gate)
        (tmp_path / "storage").mkdir()
        info = env.artifact_environment(
            tmp_path, {"xlsx/x": _failure("artifact_publish_failed")}
        )
        assert info["storage_root_exists"] is True
        assert info["project_dirs"] == 0
        assert info["artifact_publish_failed_count"] == 1
        assert env.measurement_is_environment_limited(info) is True, (
            "目录在、里面是空的、59 条全失败 —— 只看根存在就会把它读成「供给不足」"
        )

    def test_other_failure_codes_are_not_counted_as_environment(
        self, gate: Any, tmp_path: Path
    ) -> None:
        """契约漂移等 typed failure 是**真实**供给结论，不许混进环境分型。"""
        env = _env_module(gate)
        (tmp_path / "storage").mkdir()
        info = env.artifact_environment(
            tmp_path,
            {
                "xlsx/a": _failure("sync_contract_structure_drift"),
                "xlsx/b": _failure("published_identity_observed_drift"),
            },
        )
        assert info["artifact_publish_failed_count"] == 0
        assert info["artifact_publish_failed_entries"] == []
        assert env.measurement_is_environment_limited(info) is False, (
            "契约漂移被当成环境受限 ⇒ 真实供给缺口会被环境理由盖掉"
        )

    def test_failed_entries_are_named_sorted_and_capped(
        self, gate: Any, tmp_path: Path
    ) -> None:
        env = _env_module(gate)
        (tmp_path / "storage").mkdir()
        failures = {
            f"xlsx/e{index:02d}": _failure("artifact_publish_failed")
            for index in range(20)
        }
        info = env.artifact_environment(tmp_path, failures)
        named = info["artifact_publish_failed_entries"]
        assert info["artifact_publish_failed_count"] == 20
        assert named == sorted(named)
        assert len(named) == 12, "点名数不再受限 ⇒ 报告会被几百条 entry id 冲掉"

    def test_project_dirs_counts_only_directories(self, gate: Any, tmp_path: Path) -> None:
        env = _env_module(gate)
        storage = tmp_path / "storage"
        storage.mkdir()
        (storage / "proj-a").mkdir()
        (storage / "proj-b").mkdir()
        (storage / "stray.txt").write_text("x", encoding="utf-8")
        assert env.artifact_environment(tmp_path, {})["project_dirs"] == 2

    def test_report_records_the_environment_next_to_the_registered_number(
        self, report: Mapping[str, Any], gate: Any
    ) -> None:
        """报告侧：注册数字旁边必须带环境分型，且该分型是**现算**的。"""
        env = _env_module(gate)
        step = next(
            item
            for item in report["supply_chain_walk"]["steps"]
            if item["step"] == "S6"
        )
        detail = step["detail"]
        artifact_env = detail["artifact_environment"]
        assert isinstance(detail["measurement_is_environment_limited"], bool)
        assert detail["measurement_is_environment_limited"] == (
            env.measurement_is_environment_limited(artifact_env)
        ), "报告里的环境分型与按同一函数重算的结论不一致 ⇒ 它被写死了"
        assert artifact_env["storage_is_gitignored"] is True
        assert "storage" in artifact_env["why"]
