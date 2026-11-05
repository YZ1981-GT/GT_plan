# -*- coding: utf-8 -*-
"""任务 70 门 —— census 普查量与逐字节锁分离的判据。

拆分自 `backend/tests/workpaper_sync_oo/test_task70_oo_scenario_gate.py`（原 1704 行 > pre-commit 行数门禁 whitelist 基线 1567 + 5% = 1645）。
判据本体**原样搬移**，一条断言未改、未删；宿主的接线（GATE / fixtures）按路径加载复用，
不抄第二份 —— 抄第二份会让「宿主与本文件对同一个门的认知」可能分叉。

census 机制本身见 `backend/scripts/_census_lock.py`。
"""
from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path
from typing import Any, Mapping  # noqa: F401  搬移来的签名用得到

import pytest  # noqa: F401  搬移来的用例可能用到

_HOST_PATH = Path(__file__).with_name("test_task70_oo_scenario_gate.py")
_spec = importlib.util.spec_from_file_location("_task70_census_host", _HOST_PATH)
assert _spec is not None and _spec.loader is not None
_host = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _host
_spec.loader.exec_module(_host)

GUARD_REL = _host.GUARD_REL

gate = _host.gate  # noqa: F811  fixture 需在本模块命名空间
report = _host.report  # noqa: F811  同上
live_db = _host.live_db  # noqa: F811  活库语义判据要真跑一次供给链

class TestCensusLock:
    """census 判据（拆分自宿主的 `TestGuardPlacement`，逐字未改）。"""

    def test_census_derived_quantities_are_excluded_from_the_byte_lock(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """普查派生量必须被 `strip_census` 剔掉，选取契约必须留下。

        🔴 BP-71-8：本门的 `radiation_surface()` 把 **`backend/tests` 全树 test 文件计数**
        （登记 2340）写进了逐字节比对 ⇒ 仓库任意位置新增一个测试文件都让 `--check` 打红。
        换目录、不写模块路径字面量都躲不开 —— 唯一出路是改判据的形状。

        正反两面各一条：
        * 正面 —— 往普查量里塞一个合成的新测试文件，投影必须**不变**；
        * 反面 —— 动选取契约（`subject_coverage` / `production_subjects`），投影必须**变**
          （否则 `strip_census` 剔多了，「辐射面选取逻辑被改坏」会被一起放过）。
        """
        assert gate.CENSUS_KEYS, "CENSUS_KEYS 为空 ⇒ 普查免疫没有落点"
        assert "radiation_surface.scanned_test_files" in gate.CENSUS_KEYS, (
            "全树计数没进 census ⇒ BP-71-8 的根因字段仍在锁里"
        )
        # volatile 与 census 必须是**两个**常量：合并会让「剔除 ≠ 不管」这条区分消失
        assert not (set(gate.VOLATILE_KEYS) & set(gate.CENSUS_KEYS))

        base = gate.strip_census(dict(report))
        grown = copy.deepcopy(dict(report))
        grown["radiation_surface"]["scanned_test_files"] = (
            int(grown["radiation_surface"]["scanned_test_files"]) + 37
        )
        grown["radiation_surface"]["referencing_test_file_count"] = (
            int(grown["radiation_surface"]["referencing_test_file_count"]) + 2
        )
        grown["radiation_surface"]["referencing_test_files"][
            "backend/tests/synthetic/test_a_brand_new_unrelated_file.py"
        ] = ["evidence"]
        grown["radiation_surface"]["digest"] = "0" * 64
        assert gate.strip_census(grown) == base, (
            "新增测试文件让投影变了 ⇒ 普查量又被冻进锁了（BP-71-8 复发）"
        )

        # 逐单元覆盖布尔必须**真的由成员清单派生**：写成恒真时它照样与记录相等
        # （记录里今天也全是 True），只有从同一份清单重算才能抓到。
        live = gate.radiation_surface()
        assert live["subject_coverage"] == {
            subject: any(subject in why for why in live["referencing_test_files"].values())
            for subject in live["production_subjects"]
        }, "逐被验单元覆盖布尔与成员清单脱钩 ⇒ 恒真的选取契约"

        for field in ("subject_coverage", "production_subjects", "own_guard_outside_census_dir"):
            tampered = copy.deepcopy(dict(report))
            node = tampered["radiation_surface"]
            node[field] = {} if isinstance(node[field], dict) else (
                [] if isinstance(node[field], list) else False
            )
            assert gate.strip_census(tampered) != base, (
                f"把辐射面选取契约字段 {field} 清空后投影没变 ⇒ strip_census 剔多了，"
                "「选取逻辑被改坏」会被放过"
            )

    def test_census_semantics_are_asserted_not_merely_skipped(self, gate: Any) -> None:
        """剔除 ≠ 不管：喂植入的退化辐射面，语义断言必须逐条打红且**正是**预期那条。"""
        live = gate.radiation_surface()
        assert gate.census_semantics(live)["all_hold"] is True, (
            f"真实辐射面的语义断言就不成立: {gate.census_semantics(live)['failing_checks']}"
        )
        for label, mutated, expect in (
            (
                "空集",
                dict(live, referencing_test_file_count=0, referencing_test_files={}),
                "surface_is_not_empty",
            ),
            ("不遍历", dict(live, scanned_test_files=0), "walk_really_traversed_the_tree"),
            (
                "退化成全量",
                dict(live, referencing_test_file_count=int(live["scanned_test_files"])),
                "surface_is_not_the_whole_tree",
            ),
            (
                "某被验单元零引用",
                dict(
                    live,
                    subject_coverage={**live["subject_coverage"], "pilot_harness": False},
                ),
                "every_production_subject_is_covered",
            ),
            (
                "本门守卫不在辐射面",
                dict(
                    live,
                    referencing_test_files={
                        k: v
                        for k, v in live["referencing_test_files"].items()
                        if k != GUARD_REL
                    },
                ),
                "own_guard_is_in_the_surface",
            ),
        ):
            result = gate.census_semantics(mutated)
            assert result["all_hold"] is False, f"{label}：语义断言没打红 ⇒ 剔除退化成了不看"
            assert expect in result["failing_checks"], (
                f"{label}：打红的不是预期那条（实得 {result['failing_checks']}）"
            )

    def test_census_contract_declares_what_is_still_locked(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """普查契约必须写明「剔了什么」「为什么」「什么仍然锁死」，三者缺一即无从复核。"""
        contract = report["census_contract"]
        assert sorted(contract["census_keys"]) == sorted(gate.CENSUS_KEYS), (
            "报告登记的 census 键与门的常量不符 ⇒ 剔了什么无从核对"
        )
        assert str(contract["why"]).strip()
        assert str(contract["excluded_is_not_unchecked"]).strip()
        locked = "\n".join(contract["still_locked"])
        # 🔴 源码轴已从 HEAD sha 换成**内容** digest：提交这份报告本身就会改 HEAD
        #    ⇒ 报告在它自己的提交里必然 stale（恒红门禁）。说理见 `source_digests`。
        assert "source_digests" in locked, "没写明 source_digests 仍然锁死 ⇒ 真 stale 轴丢了"
        assert "source_commit" in str(sorted(gate.CENSUS_KEYS)), (
            "source_commit 没进 census ⇒ 它会在提交动作后把锁顶红"
        )
        assert "subject_coverage" in locked
        assert contract["semantics"]["all_hold"] is True


def _s6_detail(node: Mapping[str, Any]) -> dict[str, Any]:
    for step in node["supply_chain_walk"]["steps"]:
        if step["step"] == "S6":
            return step["detail"]
    raise AssertionError("S6 不在 supply_chain_walk 里 —— 判据前提已漂移")


class TestLiveDbLock:
    """第三类剔除：共享真库的现状量（2026-11-05 新增）。

    🔴 实测形态：报告在具备观测条件的环境里刷新、`--check` 当场 rc=0，约 **40 分钟后**
    再跑就有 **47 条叶子路径**漂移 —— 另一个会话给 `xlsx/gt-d4-operating-revenue` 发布了
    一条新的 content representation（representation 455→456 / content_version 435→436 /
    entry_state 83→84 / S6 failure 27→28 / reason 138→137）。
    把这些冻进逐字节锁，等于**要求共享库停止写入** ⇒ 这条锁恒红 = 没有锁，与 BP-71-8
    （要求仓库停止演进）是同一笔账。

    下面三条臂分别钉住：剔了该剔的 / 没有剔多 / 源码轴换成内容 digest 之后仍然锁着。
    """

    def test_live_db_quantities_are_excluded_from_the_byte_lock(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """臂 A：活库现状量漂移 ⇒ `comparable()` 投影必须不变。"""
        assert gate.LIVE_DB_KEYS, "LIVE_DB_KEYS 为空 ⇒ 第三类免疫没有落点"
        # 三个剔除集合必须互不相交：合并会让「剔除 ≠ 不管」的分类说理消失
        assert not (set(gate.LIVE_DB_KEYS) & set(gate.CENSUS_KEYS))
        assert not (set(gate.LIVE_DB_KEYS) & set(gate.VOLATILE_KEYS))

        payload = {key: value for key, value in report.items() if key != "report_digest"}
        base = gate.comparable(payload)
        assert gate.digest_of(base) == report["report_digest"], (
            "report_digest 不是算在三类剔除之后的内容上 ⇒ digest 自己又成了会过期的锁"
        )

        def drifted(mutate: Any) -> Any:
            node = copy.deepcopy(payload)
            mutate(node)
            return gate.comparable(node)

        for label, mutate in (
            ("某表行数 +N", lambda n: n["db_snapshot"]["row_counts_after"].update(
                {"working_paper_content_representation": 99999})),
            ("S6 failure_count+1", lambda n: _s6_detail(n).update(
                {"failure_count": int(_s6_detail(n)["failure_count"]) + 1})),
            ("S6 registered_entry_ids 少一条", lambda n: _s6_detail(n).__setitem__(
                "registered_entry_ids", list(_s6_detail(n)["registered_entry_ids"])[:-1])),
            ("环境分型取反", lambda n: _s6_detail(n).update(
                {"measurement_is_environment_limited":
                 not _s6_detail(n)["measurement_is_environment_limited"]})),
            ("failure_code_histogram 换内容", lambda n: _s6_detail(n).update(
                {"failure_code_histogram": {"whatever": 1}})),
        ):
            assert drifted(mutate) == base, (
                f"{label} 让投影变了 ⇒ 共享库一被别人写就 stale（这条锁会恒红）"
            )

    def test_judgements_are_still_locked(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """臂 B：判据/结论字段 ⇒ 投影必须变（证明没有剔多）。

        少了这一条，第三类剔除就可能把「本门的结论」一起放过 —— 那比不剔更糟。
        """
        payload = {key: value for key, value in report.items() if key != "report_digest"}
        base = gate.comparable(payload)

        def changed(mutate: Any) -> bool:
            node = copy.deepcopy(payload)
            mutate(node)
            return gate.comparable(node) != base

        for label, mutate in (
            ("verdict.state", lambda n: n["verdict"].update({"state": "refreshed"})),
            ("verdict.executed_end_to_end",
             lambda n: n["verdict"].update({"executed_end_to_end": 1206})),
            ("scenario_execution.tier_histogram", lambda n: n["scenario_execution"].update(
                {"tier_histogram": {"executed_end_to_end": 1206}})),
            ("S6 accounting_identity_holds", lambda n: _s6_detail(n).update(
                {"accounting_identity_holds": False})),
            ("S6 accounting_identity_formula", lambda n: _s6_detail(n).update(
                {"accounting_identity_formula": "registered == planned"})),
            ("S6 planned", lambda n: _s6_detail(n).update({"planned": 1})),
            ("first_hard_stop_step", lambda n: n["supply_chain_walk"].update(
                {"first_hard_stop_step": "S6"})),
            # 🔴 剔除集合**自己**必须进锁：否则往里加一条路径就能让任意漂移合法绕过锁，
            #    那是个静默逃生口。加路径会改报告内容 ⇒ 必须显式 --write ⇒ review 看得见。
            ("live_db_contract.census_keys",
             lambda n: n["live_db_contract"]["census_keys"].append("verdict.state")),
            ("live_db_contract.semantics.all_hold",
             lambda n: n["live_db_contract"]["semantics"].update({"all_hold": False})),
        ):
            assert changed(mutate), f"改 {label} 后投影没变 ⇒ 第三类剔除剔多了"

    def test_source_axis_uses_content_digest_not_head_sha(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """臂 C：`source_commit` 变（= 提交动作）不该打红；源码内容变必须打红。

        🔴 原来这条轴靠顶层 `source_commit`（`git rev-parse HEAD`）锁，而**提交这份报告本身
        就会改 HEAD** ⇒ 报告在它自己的提交里必然 stale、`test_gate_check_passes` 落地即红。
        内容 digest 没有这个毛病。
        """
        payload = {key: value for key, value in report.items() if key != "report_digest"}
        base = gate.comparable(payload)

        committed = copy.deepcopy(payload)
        committed["source_commit"] = "0" * 40
        assert gate.comparable(committed) == base, (
            "换 HEAD sha 让投影变了 ⇒ 报告在它自己的提交里必然 stale（恒红门禁）"
        )

        assert report["source_digests"], "source_digests 为空 ⇒ 真 stale 轴没有落点"
        # 🔴 产物清单必须**现调**，不能只看报告里已有的值：只读报告的判据对实现侧改动天生
        #    不敏感（教训 17）。实测把门里的清单改成 `[]` 或改成「含报告自己」，两个变异
        #    都 GREEN —— 因为磁盘报告没变。现调之后两者都打红。
        targets = gate.source_digest_targets()
        assert targets, "源码轴的产物清单现算为空 ⇒ 轴整体消失"
        assert gate.rel(gate.OUTPUT_PATH) not in targets, (
            "报告自己进了源码轴的产物清单 ⇒ 自指，算不出不动点"
        )
        assert sorted(report["source_digests"]) == sorted(targets), (
            f"报告登记的源码轴产物与门现算的清单不符：{sorted(report['source_digests'])}"
            f" vs {sorted(targets)}"
        )
        assert set(gate.source_digests(gate.REPO, targets)) == set(report["source_digests"])
        for path, digest in report["source_digests"].items():
            assert len(str(digest)) == 64, f"{path} 的 digest 不是 sha256：{digest!r}"
        touched = copy.deepcopy(payload)
        first = sorted(touched["source_digests"])[0]
        touched["source_digests"][first] = "f" * 64
        assert gate.comparable(touched) != base, (
            "源码内容 digest 变了投影却没变 ⇒ 「源码改了但报告没刷新」这条轴丢了"
        )

    def test_live_db_semantics_are_asserted_not_merely_skipped(
        self, gate: Any, live_db: Mapping[str, Any]
    ) -> None:
        """剔除 ≠ 不管：喂植入的退化活库事实，语义断言必须打红且**正是**预期那条。"""
        assert gate.live_db_semantics(live_db)["all_hold"] is True, (
            f"真实活库事实的语义断言就不成立: "
            f"{gate.live_db_semantics(live_db)['failing_checks']}"
        )

        def mutated(mutate: Any) -> dict[str, Any]:
            node = copy.deepcopy(dict(live_db))
            mutate(node)
            return gate.live_db_semantics(node)

        for label, mutate, expect in (
            ("快照为空", lambda n: n["db_snapshot"].update({"row_counts_before": {}}),
             "snapshot_is_not_empty"),
            ("前后覆盖的表不一致",
             lambda n: n["db_snapshot"]["row_counts_after"].update({"ghost_table": 1}),
             "snapshot_covers_the_same_tables_before_and_after"),
            ("行数出现负值",
             lambda n: n["db_snapshot"]["row_counts_after"].update(
                 {sorted(n["db_snapshot"]["row_counts_after"])[0]: -1}),
             "every_row_count_is_a_non_negative_int"),
            ("注册分母为 0", lambda n: _s6_detail(n).update({"planned": 0}),
             "registry_denominator_is_non_empty"),
            ("三集合之和对不上", lambda n: _s6_detail(n).update({"failure_count": 0}),
             "three_sets_sum_to_planned"),
            ("reason 直方图加总不符",
             lambda n: _s6_detail(n).update({"reason_kind_histogram": {"x": 1}}),
             "reason_histogram_sums_to_its_count"),
            ("环境分型与重算不符", lambda n: _s6_detail(n).update(
                {"measurement_is_environment_limited":
                 not _s6_detail(n)["measurement_is_environment_limited"]}),
             "artifact_environment_verdict_is_recomputable"),
        ):
            result = mutated(mutate)
            assert result["all_hold"] is False, f"{label}：语义断言没打红 ⇒ 剔除退化成了不看"
            assert expect in result["failing_checks"], (
                f"{label}：打红的不是预期那条（实得 {result['failing_checks']}）"
            )

    def test_live_db_contract_declares_what_is_still_locked(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """活库契约必须写明「剔了什么」「为什么」「什么仍然锁死」。"""
        contract = report["live_db_contract"]
        assert sorted(contract["census_keys"]) == sorted(gate.LIVE_DB_KEYS), (
            "报告登记的活库剔除键与门的常量不符 ⇒ 剔了什么无从核对"
        )
        assert str(contract["why"]).strip()
        assert str(contract["excluded_is_not_unchecked"]).strip()
        locked = "\n".join(contract["still_locked"])
        for token in ("planned", "accounting_identity", "verdict", "tier_histogram"):
            assert token in locked, f"没写明 {token} 仍然锁死 ⇒ 结论轴可能被削弱"
        assert contract["semantics"]["all_hold"] is True
