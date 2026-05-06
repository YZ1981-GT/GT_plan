"""BatchAssignStrategy 纯函数单元测试

测试三种策略：manual / round_robin / by_level
每种策略 3 个用例，共 9 个核心用例 + override 微调测试。
"""

from __future__ import annotations

import uuid

import pytest

from app.services.batch_assign_strategy import (
    AssignmentResult,
    CandidateInfo,
    WorkpaperInfo,
    assign_by_level,
    assign_manual,
    assign_round_robin,
    compute_assignments,
)


def _uid() -> uuid.UUID:
    return uuid.uuid4()


# ── manual 策略 ──────────────────────────────────────────────────


class TestManualStrategy:
    """手动策略：所有底稿分给 candidates[0]"""

    def test_all_assigned_to_first_candidate(self):
        """所有底稿分给第一个候选人"""
        c1, c2 = _uid(), _uid()
        wps = [WorkpaperInfo(wp_id=_uid()) for _ in range(5)]

        results = assign_manual(wps, [c1, c2])

        assert len(results) == 5
        for r in results:
            assert r.user_id == c1

    def test_single_workpaper(self):
        """单张底稿分配"""
        c1 = _uid()
        wp = WorkpaperInfo(wp_id=_uid())

        results = assign_manual([wp], [c1])

        assert len(results) == 1
        assert results[0].wp_id == wp.wp_id
        assert results[0].user_id == c1

    def test_empty_candidates_raises(self):
        """候选人为空时抛异常"""
        wps = [WorkpaperInfo(wp_id=_uid())]

        with pytest.raises(ValueError, match="至少需要一个候选人"):
            assign_manual(wps, [])


# ── round_robin 策略 ─────────────────────────────────────────────


class TestRoundRobinStrategy:
    """轮询策略：按候选人列表均匀分配"""

    def test_even_distribution(self):
        """6 张底稿 3 个候选人，每人 2 张"""
        c1, c2, c3 = _uid(), _uid(), _uid()
        wps = [WorkpaperInfo(wp_id=_uid()) for _ in range(6)]

        results = assign_round_robin(wps, [c1, c2, c3])

        assert len(results) == 6
        # 按顺序轮询
        assert results[0].user_id == c1
        assert results[1].user_id == c2
        assert results[2].user_id == c3
        assert results[3].user_id == c1
        assert results[4].user_id == c2
        assert results[5].user_id == c3

    def test_uneven_distribution(self):
        """5 张底稿 2 个候选人，一人 3 张一人 2 张"""
        c1, c2 = _uid(), _uid()
        wps = [WorkpaperInfo(wp_id=_uid()) for _ in range(5)]

        results = assign_round_robin(wps, [c1, c2])

        assert len(results) == 5
        c1_count = sum(1 for r in results if r.user_id == c1)
        c2_count = sum(1 for r in results if r.user_id == c2)
        assert c1_count == 3
        assert c2_count == 2

    def test_empty_candidates_raises(self):
        """候选人为空时抛异常"""
        wps = [WorkpaperInfo(wp_id=_uid())]

        with pytest.raises(ValueError, match="至少需要一个候选人"):
            assign_round_robin(wps, [])


# ── by_level 策略 ────────────────────────────────────────────────


class TestByLevelStrategy:
    """按职级策略：根据底稿复杂度匹配候选人职级"""

    def test_simple_wps_to_junior(self):
        """D 循环（初级）底稿分给 auditor"""
        auditor = CandidateInfo(user_id=_uid(), role="auditor")
        manager = CandidateInfo(user_id=_uid(), role="manager")
        wps = [
            WorkpaperInfo(wp_id=_uid(), audit_cycle="D"),
            WorkpaperInfo(wp_id=_uid(), audit_cycle="F"),
        ]

        results = assign_by_level(wps, [auditor, manager])

        # D 和 F 都是初级，应分给 auditor（junior 组）
        for r in results:
            assert r.user_id == auditor.user_id

    def test_complex_wps_to_manager(self):
        """K/N 循环（复杂）底稿分给 manager"""
        auditor = CandidateInfo(user_id=_uid(), role="auditor")
        manager = CandidateInfo(user_id=_uid(), role="manager")
        wps = [
            WorkpaperInfo(wp_id=_uid(), audit_cycle="K"),
            WorkpaperInfo(wp_id=_uid(), audit_cycle="N"),
        ]

        results = assign_by_level(wps, [auditor, manager])

        # K 和 N 都是复杂，应分给 manager
        for r in results:
            assert r.user_id == manager.user_id

    def test_mixed_complexity_distribution(self):
        """混合复杂度底稿按职级分配"""
        auditor = CandidateInfo(user_id=_uid(), role="auditor")
        senior = CandidateInfo(user_id=_uid(), role="senior_auditor")
        manager = CandidateInfo(user_id=_uid(), role="manager")

        wps = [
            WorkpaperInfo(wp_id=_uid(), audit_cycle="D"),   # 初级 → auditor/senior
            WorkpaperInfo(wp_id=_uid(), audit_cycle="K"),   # 复杂 → manager
            WorkpaperInfo(wp_id=_uid(), complexity=2),       # 中等 → senior
        ]

        results = assign_by_level(wps, [auditor, senior, manager])

        # 按 wp_id 找到对应结果
        result_map = {r.wp_id: r.user_id for r in results}

        # D 循环（初级）→ junior 组（auditor + senior）
        assert result_map[wps[0].wp_id] in (auditor.user_id, senior.user_id)
        # K 循环（复杂）→ manager
        assert result_map[wps[1].wp_id] == manager.user_id
        # complexity=2（中等）→ senior
        assert result_map[wps[2].wp_id] == senior.user_id

    def test_fallback_when_no_matching_role(self):
        """当没有匹配角色时，回退到所有候选人"""
        auditor = CandidateInfo(user_id=_uid(), role="auditor")
        # 只有 auditor，没有 manager，但有复杂底稿
        wps = [WorkpaperInfo(wp_id=_uid(), audit_cycle="K")]

        results = assign_by_level(wps, [auditor])

        # 没有 manager，回退到全体候选人
        assert len(results) == 1
        assert results[0].user_id == auditor.user_id

    def test_empty_candidates_raises(self):
        """候选人为空时抛异常"""
        wps = [WorkpaperInfo(wp_id=_uid(), audit_cycle="D")]

        with pytest.raises(ValueError, match="至少需要一个候选人"):
            assign_by_level(wps, [])


# ── compute_assignments 统一入口 ─────────────────────────────────


class TestComputeAssignments:
    """统一入口 + override 微调"""

    def test_override_replaces_strategy_result(self):
        """override_assignments 覆盖策略计算结果"""
        c1, c2 = _uid(), _uid()
        wp1_id, wp2_id = _uid(), _uid()
        wps = [
            WorkpaperInfo(wp_id=wp1_id),
            WorkpaperInfo(wp_id=wp2_id),
        ]

        # manual 策略会把所有底稿分给 c1
        # 但 override 把 wp2 改给 c2
        results = compute_assignments(
            strategy="manual",
            workpapers=wps,
            candidates=[c1],
            override_assignments=[AssignmentResult(wp_id=wp2_id, user_id=c2)],
        )

        result_map = {r.wp_id: r.user_id for r in results}
        assert result_map[wp1_id] == c1  # 未被 override
        assert result_map[wp2_id] == c2  # 被 override

    def test_unknown_strategy_raises(self):
        """未知策略抛异常"""
        wps = [WorkpaperInfo(wp_id=_uid())]

        with pytest.raises(ValueError, match="未知策略"):
            compute_assignments(
                strategy="unknown",  # type: ignore
                workpapers=wps,
                candidates=[_uid()],
            )

    def test_by_level_via_compute(self):
        """通过 compute_assignments 调用 by_level 策略"""
        auditor = CandidateInfo(user_id=_uid(), role="auditor")
        manager = CandidateInfo(user_id=_uid(), role="manager")
        wps = [
            WorkpaperInfo(wp_id=_uid(), audit_cycle="D"),
            WorkpaperInfo(wp_id=_uid(), audit_cycle="K"),
        ]

        results = compute_assignments(
            strategy="by_level",
            workpapers=wps,
            candidates=[auditor, manager],
        )

        assert len(results) == 2
        result_map = {r.wp_id: r.user_id for r in results}
        # D → auditor (junior)
        assert result_map[wps[0].wp_id] == auditor.user_id
        # K → manager
        assert result_map[wps[1].wp_id] == manager.user_id
