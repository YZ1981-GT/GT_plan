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
        assert "source_commit" in locked, "没写明 source_commit 仍然锁死 ⇒ 真 stale 轴可能被削弱"
        assert "subject_coverage" in locked
        assert contract["semantics"]["all_hold"] is True
