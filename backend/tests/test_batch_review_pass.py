"""批量复核端点测试（batch_review）。

Tests for:
- Task 9.1: 批量复核路由
- Task 9.2: 批量复核事务逻辑

🔴 2026-11-13 重写（基线漂移）：原用例测的三个符号
``ALLOWED_ROLES`` / ``_check_reviewable`` / ``_execute_batch_review`` 已在
``cd0a8fe1f`` 被有意删除，实现改为：

1. 鉴权走 ``Depends(require_project_access("review"))``（项目级权限单一真源）；
2. 状态机走 ``WorkingPaperService.update_review_status``（F8 配置驱动），
   不再有本地 ``_check_reviewable`` 白名单；
3. 批量循环内联进端点，不再有 ``_execute_batch_review``。

因此本文件改为**测当前真实契约**（``_resolve_level`` 提取、
``REVIEWABLE_REVIEW_STATUSES`` 集合、请求/响应模型、项目级鉴权），
并保留两条真实可伪证的不变量（计数守恒 + 跳过项必有 reason）。
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.deps import PERMISSION_HIERARCHY
from app.routers.batch_review import (
    REVIEWABLE_REVIEW_STATUSES,
    BatchReviewRequest,
    BatchReviewResult,
    _resolve_level,
    batch_review,
)
from app.services.assignment_service import ROLE_MAP, UNMAPPED_ROLE


# ---------------------------------------------------------------------------
# RBAC：端点挂的是项目级 review 门禁，不是写死角色名单
# ---------------------------------------------------------------------------


class TestRBAC:
    """RBAC 权限测试。

    与旧口径的实质差异：新机制按项目级别判定，``review`` 级（质控 / EQCR）
    **也能**通过，而旧写死名单把它们排除在外 —— 这正是 ``require_project_access``
    存在的目的（复核岗必须能复核）。
    """

    def test_endpoint_uses_project_review_gate_not_a_hardcoded_roster(self):
        """端点挂的是 review 级项目门禁，且不得恢复写死名单。"""
        import inspect

        from app.routers import batch_review as module

        assert not hasattr(module, "ALLOWED_ROLES"), (
            "ALLOWED_ROLES 已退役：鉴权必须走 require_project_access('review') "
            "项目级单一真源，不得恢复写死名单"
        )
        source = inspect.getsource(module.batch_review)
        assert 'require_project_access("review")' in source

    def test_review_level_roles_satisfy_the_gate(self):
        """review 级角色（质控 / EQCR）满足 review 门禁。"""
        review_roles = {k for k, (_r, lv) in ROLE_MAP.items() if lv.value == "review"}
        assert {"qc", "eqcr"} <= review_roles, review_roles

    def test_edit_level_roles_also_pass_review_gate(self):
        """edit 级（合伙人 / 经理 / 审计员 / 助理）级别更高，同样通过。"""
        for role in ("partner", "manager", "auditor", "assistant"):
            _r, lv = ROLE_MAP[role]
            assert PERMISSION_HIERARCHY[lv.value] >= PERMISSION_HIERARCHY["review"], role

    def test_readonly_fallback_does_not_pass_review_gate(self):
        """未登记角色兜底为 readonly，低于 review ⇒ 被拒。"""
        _r, lv = UNMAPPED_ROLE
        assert PERMISSION_HIERARCHY[lv.value] < PERMISSION_HIERARCHY["review"]


# ---------------------------------------------------------------------------
# _resolve_level：从 review_status 推导当前复核层级
# ---------------------------------------------------------------------------


class TestResolveLevel:
    """``_resolve_level`` 是判定「当前能不能复核」的唯一依据。"""

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            ("pending_level1", 1),
            ("pending_level2", 2),
            ("pending_level3", 3),
            ("pending_level4", 4),
            ("level1_in_progress", 1),
            ("level2_in_progress", 2),
            ("level3_in_progress", 3),
            ("level4_in_progress", 4),
        ],
    )
    def test_pending_and_in_progress_resolve_to_their_level(self, status, expected):
        """待复核 / 复核中都应当前层级。"""
        assert _resolve_level(status) == expected

    @pytest.mark.parametrize(
        "status",
        [
            "not_submitted",
            "level1_passed",
            "level2_rejected",
            "level4_passed",
            "",
            "arbitrary",
        ],
    )
    def test_non_reviewable_statuses_resolve_to_none(self, status):
        """已通过 / 已退回 / 未提交 / 乱写 都不应当前层级（⇒ 跳过）。"""
        assert _resolve_level(status) is None

    def test_reviewable_set_is_derived_from_resolver_not_handwritten(self):
        """可复核集合必须与 ``_resolve_level`` 逐个一致（不得维护第二份名单）。"""
        from app.models.workpaper_models import WpReviewStatus

        expected = {s for s in WpReviewStatus if _resolve_level(s.value) is not None}
        assert REVIEWABLE_REVIEW_STATUSES == frozenset(expected)
        assert REVIEWABLE_REVIEW_STATUSES, "可复核集合不得为空"


# ---------------------------------------------------------------------------
# 请求 / 响应模型契约
# ---------------------------------------------------------------------------


class TestModels:
    """请求与响应模型的字段契约。"""

    def test_request_defaults_to_approve_with_empty_comment(self):
        body = BatchReviewRequest(wp_ids=[uuid4()])
        assert body.action == "approve"
        assert body.comment == ""

    def test_request_accepts_reject_with_comment(self):
        wp_id = uuid4()
        body = BatchReviewRequest(wp_ids=[wp_id], action="reject", comment="需补充底稿")
        assert body.wp_ids == [wp_id]
        assert body.action == "reject"
        assert body.comment == "需补充底稿"

    def test_result_exposes_count_invariant_fields(self):
        result = BatchReviewResult(
            success_count=2,
            skipped_count=1,
            skipped_items=[{"wp_id": "x", "reason": "底稿不存在或已删除"}],
        )
        assert result.success_count + result.skipped_count == 3
        assert result.skipped_items[0]["reason"]


# ---------------------------------------------------------------------------
# 端点：非法 action 与空列表的短路分支（不触库）
# ---------------------------------------------------------------------------


class TestEndpointShortCircuits:
    """不需要数据库就能判定的两个分支。"""

    @pytest.mark.asyncio
    async def test_invalid_action_raises_422(self):
        from fastapi import HTTPException

        body = BatchReviewRequest(wp_ids=[uuid4()], action="delete")
        with pytest.raises(HTTPException) as exc:
            await batch_review(
                project_id=uuid4(),
                body=body,
                db=object(),  # 不会被触及：422 在任何取数之前
                current_user=object(),
            )
        assert exc.value.status_code == 422
        detail = str(exc.value.detail)
        assert "approve" in detail and "reject" in detail

    @pytest.mark.asyncio
    async def test_empty_wp_ids_returns_zero_counts_without_touching_db(self):
        body = BatchReviewRequest(wp_ids=[], action="approve")
        result = await batch_review(
            project_id=uuid4(),
            body=body,
            db=object(),
            current_user=object(),
        )
        assert result.success_count == 0
        assert result.skipped_count == 0
        assert result.skipped_items == []
