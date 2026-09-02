# -*- coding: utf-8 -*-
"""任务 71 门 —— census 普查量与逐字节锁分离的判据。

拆分自 `backend/tests/workpaper_sync_chaos/test_task71_chaos_gate.py`（原 2351 行 > pre-commit 行数门禁 whitelist 基线 2224 + 5% = 2335）。
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

_HOST_PATH = Path(__file__).with_name("test_task71_chaos_gate.py")
_spec = importlib.util.spec_from_file_location("_task71_census_host", _HOST_PATH)
assert _spec is not None and _spec.loader is not None
_host = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _host
_spec.loader.exec_module(_host)

GUARD_REL = _host.GUARD_REL

gate = _host.gate  # noqa: F811  fixture 需在本模块命名空间
report = _host.report  # noqa: F811  同上

class TestCensusLock:
    """census 判据（拆分自宿主的 `TestGuardPlacement`，逐字未改）。"""

    def test_census_derived_quantities_are_excluded_from_the_byte_lock(
        self, gate: Any, report: Mapping[str, Any]
    ) -> None:
        """普查派生量必须被 `strip_census` 剔掉，且语义性质仍被现算断言。

        🔴 这条是本次判据改形的**正反两面**：
        * 正面 —— 往普查量里塞一个合成的新测试文件，投影必须**不变**（否则仓库演进即打红）；
        * 反面 —— 动一个非普查字段，投影必须**变**（否则 `strip_census` 剔多了，真 stale 轴
          被一起放过）。
        """
        assert gate.CENSUS_KEYS, "CENSUS_KEYS 为空 ⇒ 普查免疫没有落点"
        assert "radiation_surface.scanned_test_files" in gate.CENSUS_KEYS
        assert "upstream_lock_impact.task70_scanned_test_files_live" in gate.CENSUS_KEYS

        base = gate.strip_census(dict(report))
        grown = copy.deepcopy(dict(report))
        grown["radiation_surface"]["scanned_test_files"] = (
            int(grown["radiation_surface"]["scanned_test_files"]) + 41
        )
        grown["radiation_surface"]["files"][
            "backend/tests/synthetic/test_a_brand_new_unrelated_file.py"
        ] = ["own_gate"]
        grown["upstream_lock_impact"]["task70_scanned_test_files_live"] = 999_999
        assert gate.strip_census(grown) == base, (
            "新增测试文件让投影变了 ⇒ 普查量又被冻进锁了（BP-71-8 复发）"
        )

        # 逐 pattern 覆盖布尔必须**真的由成员清单派生**（恒真时它照样与记录相等）
        live = gate.radiation_surface()
        assert live["pattern_coverage"] == {
            name: any(name in why for why in live["files"].values())
            for name in live["patterns"]
        }, "逐 pattern 覆盖布尔与成员清单脱钩 ⇒ 恒真的选取契约"

        tampered = copy.deepcopy(dict(report))
        tampered["radiation_surface"]["pattern_coverage"] = {}
        assert gate.strip_census(tampered) != base, (
            "把辐射面的逐 pattern 覆盖布尔清空后投影没变 ⇒ strip_census 剔多了，"
            "「选取逻辑被改坏」会被放过"
        )
        tampered2 = copy.deepcopy(dict(report))
        tampered2["upstream_lock_impact"]["task70_surface_projection_agrees"] = False
        assert gate.strip_census(tampered2) != base, (
            "把上游投影一致的判定改掉后投影没变 ⇒ 那条真判据没进锁"
        )

    def test_census_semantics_are_asserted_not_merely_skipped(self, gate: Any) -> None:
        """剔除 ≠ 不管：喂植入的退化辐射面，语义断言必须逐条打红。"""
        live = gate.radiation_surface()
        assert gate.census_semantics(live)["all_hold"] is True

        for label, mutated, expect in (
            ("空集", dict(live, referencing_test_file_count=0, files={}), "surface_is_not_empty"),
            (
                "不遍历",
                dict(live, scanned_test_files=0),
                "walk_really_traversed_the_tree",
            ),
            (
                "pattern 无命中",
                dict(live, pattern_coverage={**live["pattern_coverage"], "retention": False}),
                "every_pattern_has_a_match",
            ),
            (
                "守卫不在辐射面",
                dict(live, files={k: v for k, v in live["files"].items() if k != GUARD_REL}),
                "own_guard_is_in_the_surface",
            ),
        ):
            result = gate.census_semantics(mutated)
            assert result["all_hold"] is False, f"{label}：语义断言没打红 ⇒ 剔除退化成了不看"
            assert expect in result["failing_checks"], (
                f"{label}：打红的不是预期那条（实得 {result['failing_checks']}）"
            )

    def test_coverage_boolean_is_derived_not_hardcoded(self, gate: Any) -> None:
        """喂「某 pattern 零命中」的合成清单：覆盖布尔必须给出 False。

        🔴 今天每条 pattern 都真有命中者 ⇒ 把它写成 `{name: True}` 恒真与「从成员清单重算」
        在真实数据上**结果相同**（等价变异，实测 GREEN）。判据因此落在**纯函数 + 合成输入**上，
        而不是在真实数据上做自我比对。
        """
        derive = gate._census_lock.coverage_from_members
        assert derive({"a.py": ["p1"]}, ["p1", "p2"]) == {"p1": True, "p2": False}, (
            "零命中的 pattern 没有被判成 False ⇒ 覆盖布尔是恒真的"
        )
        assert derive({}, ["p1"]) == {"p1": False}, "空成员清单下覆盖必须全 False（空集恒真是假绿源）"
        # 正例（防判据恒假）：真实数据上仍必须与成员清单一致
        live = gate.radiation_surface()
        assert live["pattern_coverage"] == derive(live["files"], live["patterns"])

    def test_upstream_precondition_is_fail_closed(self, gate: Any) -> None:
        """上游回退掉普查免疫（缺 `CENSUS_KEYS` 或 `strip_census`）时本门必须**抛**。

        🔴 今天上游是合规的，那条前提检查从不触发 ⇒ 把它改成 `if False:` 是等价变异
        （实测 GREEN，而它正是 fail-open：`strip=None` 会让 `None == None` 得 True）。
        """
        class _NoCensusKeys:
            CENSUS_KEYS: tuple[str, ...] = ()

            @staticmethod
            def strip_census(node, *a, **k):
                return node

            @staticmethod
            def radiation_surface():
                return {}

            @staticmethod
            def census_semantics(surface=None):
                return {"all_hold": True}

        with pytest.raises(gate.Task71GateError):
            gate.upstream_lock_impact(_NoCensusKeys)

        class _NoStrip(_NoCensusKeys):
            CENSUS_KEYS = ("radiation_surface.scanned_test_files",)
            strip_census = None

        with pytest.raises(gate.Task71GateError):
            gate.upstream_lock_impact(_NoStrip)

    def test_projection_agreement_is_really_computed(self, gate: Any) -> None:
        """喂一个「剔除普查量后仍与盘上不一致」的合成上游：判定必须为 False，不得写死 True。"""
        real = gate.upstream_lock_impact()
        assert real["task70_surface_projection_agrees"] is True, "正例失败：真实上游本应一致"
        assert real["task70_lock_goes_stale_because_of_this_gate"] is False

        upstream = sys.modules["t70_for_71"]
        drifted = copy.deepcopy(upstream.radiation_surface())
        # 动一个**非普查**字段（选取契约）—— 它必须仍在锁里，于是投影必须判不一致
        drifted["production_subjects"] = ["synthetic_subject_only"]

        class _Drifted:
            CENSUS_KEYS = upstream.CENSUS_KEYS
            strip_census = staticmethod(upstream.strip_census)
            census_semantics = staticmethod(upstream.census_semantics)

            @staticmethod
            def radiation_surface():
                return drifted

        row = gate.upstream_lock_impact(_Drifted)
        assert row["task70_surface_projection_agrees"] is False, (
            "动了上游的选取契约字段后投影仍报一致 ⇒ 该判定被写死，普查免疫的复核形同虚设"
        )
        assert row["task70_lock_goes_stale_because_of_this_gate"] is True
