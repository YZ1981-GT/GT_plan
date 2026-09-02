# -*- coding: utf-8 -*-
"""任务 67 生成器 —— census 普查量的**语义退化**判据。

新建（不是拆分）：宿主 `test_task67_structural_pre_reconcile.py` 里**没有**任何 census /
语义退化判据 —— 实测 `mutate_task67` 的 M35（`all_hold` 恒真）与 M36
（`scan_reaches_beyond_the_required_targets` 恒真）双双 **GREEN**，因为宿主只在**今天合规的
真实数据**上断言，把合规答案写死是等价变异。

判据形状因此是「纯函数 + 合成的**不合规**输入」：喂退化的入向普查结果，每条语义性质必须
逐条打红，且打红的**正是**预期那条（否则 RED 与 WRONG-TEST 分不开）。

census 机制见 `backend/scripts/_census_lock.py`。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

_THIS = Path(__file__).resolve()
REPO = _THIS.parents[3]
_GEN_PATH = REPO / "backend" / "scripts" / "gen" / "generate_task67_structural_pre_reconcile.py"

_spec = importlib.util.spec_from_file_location("_task67_gen_for_census", _GEN_PATH)
assert _spec is not None and _spec.loader is not None
GEN: Any = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = GEN
_spec.loader.exec_module(GEN)


class TestCensusSemanticsAreAssertedNotMerelySkipped:
    """剔除 ≠ 不管：被 census 剔掉的入向普查量仍须现算并逐条断言语义性质。"""

    def test_real_scan_holds_every_semantic_property(self) -> None:
        """正例（防判据恒假）：真实入向普查必须逐条成立。"""
        result = GEN.census_semantics(GEN.collect_inbound_obligations())
        assert result["all_hold"] is True, f"真实普查的语义断言就不成立: {result['failing_checks']}"

    def test_each_degradation_reds_exactly_its_own_check(self) -> None:
        """逐个植入退化形态，必须打红且**正是**预期那条。"""
        real = GEN.collect_inbound_obligations()
        required = list(GEN.REQUIRED_INBOUND_TARGETS)
        assert real and required, "判据前提漂移：真实普查或必需目标清单为空"

        cases = (
            ("空集", [], "scan_is_not_empty"),
            (
                "普查器被改成只返回写死的必需目标",
                [row for row in real if str(row.get("path")) in required],
                "scan_reaches_beyond_the_required_targets",
            ),
            (
                "漏掉一个必需目标",
                [row for row in real if str(row.get("path")) != required[0]],
                "all_required_targets_present",
            ),
            (
                "结构化归属与散文提及被压平成一态",
                [{**row, "structured_ownership": True} for row in real],
                "both_ownership_kinds_present",
            ),
        )
        for label, rows, expect in cases:
            result = GEN.census_semantics(rows)
            assert result["all_hold"] is False, (
                f"{label}：语义断言没打红 ⇒ 「剔除 ≠ 不管」退化成了「不看了」"
            )
            assert expect in result["failing_checks"], (
                f"{label}：打红的不是预期那条（实得 {result['failing_checks']}）"
            )

    def test_projection_keeps_the_stable_core_and_drops_the_tail(self) -> None:
        """投影必须保住必需目标那几行、剔掉随仓库增长的尾巴（整块剔会放过普查器退化）。"""
        real = GEN.collect_inbound_obligations()
        required = set(GEN.REQUIRED_INBOUND_TARGETS)
        projected = GEN.strip_census({"inbound_obligations": real})["inbound_obligations"]
        kept = {str(row.get("path")) for row in projected}
        assert kept == required & {str(r.get("path")) for r in real}, (
            "投影没有恰好保住必需目标那几行 ⇒ 稳定核与尾巴的边界漂了"
        )
        assert len(projected) < len(real), (
            "投影没剔掉任何行 ⇒ 随仓库增长的尾巴仍在锁里（BP-72-8 复发）"
        )
