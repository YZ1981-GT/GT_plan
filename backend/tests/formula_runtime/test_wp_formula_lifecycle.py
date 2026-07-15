"""WpFormula 生命周期与 service ownership 测试。

**Validates: Requirements 5, 12 | Properties P5, P6, P13**

- P5: save 前后 `last_computed_at` 不因保存动作前推。
- P6: 仅成功 apply 前推计算时间（service 层不写 computed time）。
- P13: 跨项目 wp/formula/reference/target，service 均拒绝且目标项目状态不变。

覆盖 WpFormulaService.save / list_by_wp / delete 的：
- project_id 必填守卫（Req 10.6）
- wp/formula 归属校验（Req 10.1 / 10.4）
- 跨项目访问拒绝不泄露敏感元数据（Req 10.4）
- save 绝不写 last_computed_at（Req 5.1 / P5）
- definition_version 单调递增（design §12）
- definition_hash 由定义字段计算（design §12）
- lifecycle_state 置为 saved（design §5）
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.services.wp_formula_service import (
    WpFormulaService,
    OwnershipError,
    _compute_definition_hash,
    _normalize_refs,
    _ownership_issue,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════

PROJECT_A = uuid.UUID("aaaaaaaa-1111-0000-0000-000000000001")
PROJECT_B = uuid.UUID("bbbbbbbb-2222-0000-0000-000000000002")
WP_ID_A = uuid.UUID("cccccccc-3333-0000-0000-000000000003")
WP_ID_B = uuid.UUID("dddddddd-4444-0000-0000-000000000004")
FORMULA_ID_A = uuid.UUID("eeeeeeee-5555-0000-0000-000000000005")
USER_ID = uuid.UUID("ffffffff-6666-0000-0000-000000000006")


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _make_formula_obj(
    *,
    formula_id: uuid.UUID = FORMULA_ID_A,
    project_id: uuid.UUID = PROJECT_A,
    wp_id: uuid.UUID = WP_ID_A,
    expression: str = "SUM(A1:A5)",
    last_computed_at: datetime | None = None,
    definition_version: int | None = 1,
    definition_hash: str | None = "abc123",
    lifecycle_state: str | None = "saved",
) -> MagicMock:
    """Build a mock WpFormula row for testing."""
    obj = MagicMock()
    obj.id = formula_id
    obj.project_id = project_id
    obj.wp_id = wp_id
    obj.expression = expression
    obj.last_computed_at = last_computed_at
    obj.definition_version = definition_version
    obj.definition_hash = definition_hash
    obj.lifecycle_state = lifecycle_state
    obj.formula_type = "auto_calc"
    obj.refs = []
    obj.category = None
    obj.description = None
    obj.issue_description = None
    obj.hint_text = None
    obj.formula_source = "custom"
    obj.reference_formula_id = None
    obj.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return obj


def _mock_session_for_ownership(
    *,
    wp_project_id: uuid.UUID | None = PROJECT_A,
    existing_formula: MagicMock | None = None,
) -> AsyncMock:
    """Build a mock AsyncSession that returns ownership results.

    - First execute call: wp ownership check → returns wp_project_id
    - Second execute call (if upsert): existing formula lookup → returns existing_formula
    """
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()

    call_count = [0]

    async def _execute_side_effect(stmt):
        call_count[0] += 1
        result = MagicMock()
        if call_count[0] == 1:
            # wp ownership check
            result.scalar_one_or_none = MagicMock(return_value=wp_project_id)
        elif call_count[0] == 2:
            # existing formula lookup (upsert)
            result.scalar_one_or_none = MagicMock(return_value=existing_formula)
        else:
            result.scalar_one_or_none = MagicMock(return_value=None)
            result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        return result

    session.execute = AsyncMock(side_effect=_execute_side_effect)
    return session


# ═══════════════════════════════════════════════════════════════════════════════
# P5: save 前后 last_computed_at 不因保存动作前推
# ═══════════════════════════════════════════════════════════════════════════════


class TestP5SaveDoesNotWriteComputedTime:
    """**Validates: Property 5 — save 绝不写 last_computed_at。**"""

    @pytest.mark.asyncio
    @patch("app.services.wp_formula_service.validate_refs_via_acnr", new_callable=AsyncMock)
    async def test_new_formula_last_computed_at_is_none(self, mock_validate):
        """新建公式 last_computed_at 为 None（P5 / Req 5.1）。"""
        mock_validate.return_value = []
        service = WpFormulaService()
        session = _mock_session_for_ownership(wp_project_id=PROJECT_A, existing_formula=None)

        formula, issues = await service.save(
            session,
            project_id=PROJECT_A,
            wp_id=WP_ID_A,
            sheet_name="Sheet1",
            target_cell="B5",
            expression="SUM(A1:A5)",
            year=2025,
        )

        assert issues == []
        # session.add was called with the formula object
        added_obj = session.add.call_args[0][0]
        assert added_obj.last_computed_at is None

    @pytest.mark.asyncio
    @patch("app.services.wp_formula_service.validate_refs_via_acnr", new_callable=AsyncMock)
    async def test_update_formula_preserves_existing_computed_at(self, mock_validate):
        """更新公式时 last_computed_at 保持原值不动（P5 / Req 5.1）。"""
        mock_validate.return_value = []
        service = WpFormulaService()

        original_time = datetime(2025, 3, 15, 10, 30, tzinfo=timezone.utc)
        existing = _make_formula_obj(
            project_id=PROJECT_A,
            last_computed_at=original_time,
            definition_version=2,
        )

        session = _mock_session_for_ownership(
            wp_project_id=PROJECT_A,
            existing_formula=existing,
        )

        formula, issues = await service.save(
            session,
            project_id=PROJECT_A,
            wp_id=WP_ID_A,
            sheet_name="Sheet1",
            target_cell="B5",
            expression="SUM(A1:A10)",  # updated
            year=2025,
        )

        assert issues == []
        # last_computed_at was NOT modified
        assert existing.last_computed_at == original_time

    @pytest.mark.asyncio
    @patch("app.services.wp_formula_service.validate_refs_via_acnr", new_callable=AsyncMock)
    async def test_update_formula_null_computed_at_stays_null(self, mock_validate):
        """从未执行过的公式更新后 last_computed_at 仍为 None（P5）。"""
        mock_validate.return_value = []
        service = WpFormulaService()

        existing = _make_formula_obj(
            project_id=PROJECT_A,
            last_computed_at=None,
            definition_version=1,
        )

        session = _mock_session_for_ownership(
            wp_project_id=PROJECT_A,
            existing_formula=existing,
        )

        formula, issues = await service.save(
            session,
            project_id=PROJECT_A,
            wp_id=WP_ID_A,
            sheet_name="Sheet1",
            target_cell="B5",
            expression="AVG(C1:C10)",
            year=2025,
        )

        assert issues == []
        assert existing.last_computed_at is None

    @settings(max_examples=5, deadline=None)
    @given(
        expression=st.text(min_size=1, max_size=50, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789()+*/-:!"),
    )
    @pytest.mark.asyncio
    @patch("app.services.wp_formula_service.validate_refs_via_acnr", new_callable=AsyncMock)
    async def test_pbt_save_never_writes_computed_time(self, mock_validate, expression: str):
        """**Validates: Property 5** — 对任意表达式，save 不前推 last_computed_at。"""
        mock_validate.return_value = []
        service = WpFormulaService()

        # Case 1: new formula
        session = _mock_session_for_ownership(wp_project_id=PROJECT_A, existing_formula=None)
        formula, issues = await service.save(
            session,
            project_id=PROJECT_A,
            wp_id=WP_ID_A,
            sheet_name="Sheet1",
            target_cell="B5",
            expression=expression,
            year=2025,
        )
        if not issues:
            added_obj = session.add.call_args[0][0]
            assert added_obj.last_computed_at is None

        # Case 2: existing formula with computed_at
        original_time = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
        existing = _make_formula_obj(
            project_id=PROJECT_A,
            last_computed_at=original_time,
            definition_version=3,
        )
        session2 = _mock_session_for_ownership(
            wp_project_id=PROJECT_A,
            existing_formula=existing,
        )
        formula2, issues2 = await service.save(
            session2,
            project_id=PROJECT_A,
            wp_id=WP_ID_A,
            sheet_name="Sheet1",
            target_cell="B5",
            expression=expression,
            year=2025,
        )
        if not issues2:
            assert existing.last_computed_at == original_time


# ═══════════════════════════════════════════════════════════════════════════════
# P6: 仅成功 apply 前推计算时间（service 层验证不写）
# ═══════════════════════════════════════════════════════════════════════════════


class TestP6OnlySuccessfulApplyWritesComputedTime:
    """**Validates: Property 6 — service.save 绝不写计算时间，留给 coordinator。**

    注：真实 apply+computed_at 写入由 runtime coordinator 负责（Task 13/14），
    本测试仅验证 WpFormulaService 自身的不写入约束。
    """

    @pytest.mark.asyncio
    @patch("app.services.wp_formula_service.validate_refs_via_acnr", new_callable=AsyncMock)
    async def test_save_sets_lifecycle_saved_not_computed(self, mock_validate):
        """Save 置 lifecycle_state='saved'（若 ORM 列可用），不触发 computed 逻辑。"""
        mock_validate.return_value = []
        service = WpFormulaService()
        session = _mock_session_for_ownership(wp_project_id=PROJECT_A, existing_formula=None)

        formula, issues = await service.save(
            session,
            project_id=PROJECT_A,
            wp_id=WP_ID_A,
            sheet_name="Sheet1",
            target_cell="C3",
            expression="A1+A2",
            year=2025,
        )

        assert issues == []
        added = session.add.call_args[0][0]
        assert added.last_computed_at is None
        # lifecycle_state 若 ORM 列存在则为 saved（Task 11 迁移后启用）
        if hasattr(added, "lifecycle_state"):
            assert added.lifecycle_state == "saved"


# ═══════════════════════════════════════════════════════════════════════════════
# Definition version & hash
# ═══════════════════════════════════════════════════════════════════════════════


class TestDefinitionVersionAndHash:
    """验证 definition_version 单调递增、definition_hash 由定义字段计算。"""

    @pytest.mark.asyncio
    @patch("app.services.wp_formula_service.validate_refs_via_acnr", new_callable=AsyncMock)
    async def test_new_formula_gets_version_1(self, mock_validate):
        """新建公式 definition_version = 1（若 ORM 列可用）。"""
        mock_validate.return_value = []
        service = WpFormulaService()
        session = _mock_session_for_ownership(wp_project_id=PROJECT_A, existing_formula=None)

        formula, issues = await service.save(
            session,
            project_id=PROJECT_A,
            wp_id=WP_ID_A,
            sheet_name="Sheet1",
            target_cell="D1",
            expression="SUM(X1:X10)",
            year=2025,
        )

        assert issues == []
        added = session.add.call_args[0][0]
        # definition_version 若 ORM 列存在则为 1（Task 11 迁移后启用）
        if hasattr(added, "definition_version"):
            assert added.definition_version == 1

    @pytest.mark.asyncio
    @patch("app.services.wp_formula_service.validate_refs_via_acnr", new_callable=AsyncMock)
    async def test_update_increments_version(self, mock_validate):
        """更新公式 definition_version 递增。"""
        mock_validate.return_value = []
        service = WpFormulaService()

        existing = _make_formula_obj(
            project_id=PROJECT_A,
            definition_version=5,
        )
        session = _mock_session_for_ownership(
            wp_project_id=PROJECT_A,
            existing_formula=existing,
        )

        formula, issues = await service.save(
            session,
            project_id=PROJECT_A,
            wp_id=WP_ID_A,
            sheet_name="Sheet1",
            target_cell="B5",
            expression="NEW_EXPR()",
            year=2025,
        )

        assert issues == []
        assert existing.definition_version == 6

    @pytest.mark.asyncio
    @patch("app.services.wp_formula_service.validate_refs_via_acnr", new_callable=AsyncMock)
    async def test_update_sets_lifecycle_state_saved(self, mock_validate):
        """更新时 lifecycle_state 重置为 saved。"""
        mock_validate.return_value = []
        service = WpFormulaService()

        existing = _make_formula_obj(
            project_id=PROJECT_A,
            lifecycle_state="succeeded",
        )
        session = _mock_session_for_ownership(
            wp_project_id=PROJECT_A,
            existing_formula=existing,
        )

        formula, issues = await service.save(
            session,
            project_id=PROJECT_A,
            wp_id=WP_ID_A,
            sheet_name="Sheet1",
            target_cell="B5",
            expression="CHANGED()",
            year=2025,
        )

        assert issues == []
        assert existing.lifecycle_state == "saved"

    def test_definition_hash_deterministic(self):
        """相同输入产生相同 hash，不同输入产生不同 hash。"""
        h1 = _compute_definition_hash("SUM(A1:A5)", "auto_calc", [])
        h2 = _compute_definition_hash("SUM(A1:A5)", "auto_calc", [])
        h3 = _compute_definition_hash("SUM(A1:A10)", "auto_calc", [])
        h4 = _compute_definition_hash("SUM(A1:A5)", "logic_check", [])

        assert h1 == h2
        assert h1 != h3
        assert h1 != h4

    def test_definition_hash_includes_refs(self):
        """refs 不同则 hash 不同。"""
        h1 = _compute_definition_hash("X", "auto_calc", [])
        h2 = _compute_definition_hash("X", "auto_calc", [{"addr_id": "D1/Sheet1/B5"}])

        assert h1 != h2


# ═══════════════════════════════════════════════════════════════════════════════
# P13: 跨项目 service 均拒绝且目标项目状态不变
# ═══════════════════════════════════════════════════════════════════════════════


class TestP13CrossProjectOwnership:
    """**Validates: Property 13 — 跨项目 wp/formula/reference/target，service 拒绝。**"""

    # ── save: project_id 必填 (Req 10.6) ──

    @pytest.mark.asyncio
    async def test_save_rejects_missing_project_id(self):
        """save 未提供 project_id 时拒绝（Req 10.6）。"""
        service = WpFormulaService()
        session = AsyncMock()

        formula, issues = await service.save(
            session,
            project_id=None,
            wp_id=WP_ID_A,
            sheet_name="Sheet1",
            target_cell="B5",
            expression="SUM(A1:A5)",
            year=2025,
        )

        assert formula is None
        assert len(issues) == 1
        assert issues[0]["status"] == "project_id_required"
        # DB 不应有任何操作
        session.flush.assert_not_awaited()

    # ── save: wp 不属于 project (Req 10.1 / 10.4) ──

    @pytest.mark.asyncio
    async def test_save_rejects_cross_project_wp(self):
        """save 时 wp 属于 PROJECT_A 但请求 PROJECT_B → 拒绝（Req 10.1）。"""
        service = WpFormulaService()
        # wp belongs to PROJECT_A, but caller claims PROJECT_B
        session = _mock_session_for_ownership(wp_project_id=PROJECT_A)

        formula, issues = await service.save(
            session,
            project_id=PROJECT_B,  # wrong project!
            wp_id=WP_ID_A,
            sheet_name="Sheet1",
            target_cell="B5",
            expression="SUM(A1:A5)",
            year=2025,
        )

        assert formula is None
        assert len(issues) == 1
        assert issues[0]["status"] == "ownership_denied"
        # No sensitive metadata leaked
        assert "expression" not in str(issues[0].get("message", "")).lower()

    @pytest.mark.asyncio
    async def test_save_rejects_nonexistent_wp(self):
        """save 时 wp 不存在 → 拒绝。"""
        service = WpFormulaService()
        session = _mock_session_for_ownership(wp_project_id=None)

        formula, issues = await service.save(
            session,
            project_id=PROJECT_A,
            wp_id=WP_ID_A,
            sheet_name="Sheet1",
            target_cell="B5",
            expression="SUM(A1:A5)",
            year=2025,
        )

        assert formula is None
        assert len(issues) == 1

    # ── list_by_wp: project_id 必填 ──

    @pytest.mark.asyncio
    async def test_list_rejects_missing_project_id(self):
        """list_by_wp 未提供 project_id 时返回空（Req 10.6）。"""
        service = WpFormulaService()
        session = AsyncMock()

        result = await service.list_by_wp(session, WP_ID_A, project_id=None)

        assert result == []
        session.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_list_rejects_cross_project_wp(self):
        """list_by_wp wp 属于 PROJECT_A 但请求 PROJECT_B → 空（Req 10.1）。"""
        service = WpFormulaService()
        session = _mock_session_for_ownership(wp_project_id=PROJECT_A)

        result = await service.list_by_wp(session, WP_ID_A, project_id=PROJECT_B)

        assert result == []

    # ── delete: project_id 必填 ──

    @pytest.mark.asyncio
    async def test_delete_rejects_missing_project_id(self):
        """delete 未提供 project_id 时返回 False（Req 10.6）。"""
        service = WpFormulaService()
        session = AsyncMock()

        result = await service.delete(session, FORMULA_ID_A, project_id=None)

        assert result is False
        session.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_rejects_cross_project_formula(self):
        """delete formula 属于 PROJECT_A 但请求 PROJECT_B → False（Req 10.1）。"""
        service = WpFormulaService()

        # Build session that returns a formula belonging to PROJECT_A
        formula_obj = _make_formula_obj(project_id=PROJECT_A)
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=formula_obj)
        session.execute = AsyncMock(return_value=result_mock)
        session.delete = AsyncMock()
        session.flush = AsyncMock()

        result = await service.delete(session, FORMULA_ID_A, project_id=PROJECT_B)

        assert result is False
        # No deletion should have occurred
        session.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_succeeds_for_same_project(self):
        """delete formula 属于 PROJECT_A、请求 PROJECT_A → True。"""
        service = WpFormulaService()

        formula_obj = _make_formula_obj(project_id=PROJECT_A)
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=formula_obj)
        session.execute = AsyncMock(return_value=result_mock)
        session.delete = AsyncMock()
        session.flush = AsyncMock()

        with patch(
            "app.services.wp_formula_service.WpFormulaService._invalidate_reference_dependents",
            new_callable=AsyncMock,
            return_value=0,
        ):
            result = await service.delete(session, FORMULA_ID_A, project_id=PROJECT_A)

        assert result is True
        session.delete.assert_awaited_once()

    # ── PBT: arbitrary cross-project pairs always rejected ──

    @settings(max_examples=5, deadline=None)
    @given(
        proj_a=st.uuids(),
        proj_b=st.uuids(),
    )
    @pytest.mark.asyncio
    async def test_pbt_cross_project_save_always_rejected(
        self, proj_a: uuid.UUID, proj_b: uuid.UUID
    ):
        """**Validates: Property 13** — 任意两个不同 project 间 save 总拒绝。"""
        assume(proj_a != proj_b)
        service = WpFormulaService()
        # wp belongs to proj_a, caller claims proj_b
        session = _mock_session_for_ownership(wp_project_id=proj_a)

        formula, issues = await service.save(
            session,
            project_id=proj_b,
            wp_id=WP_ID_A,
            sheet_name="S1",
            target_cell="A1",
            expression="1+1",
            year=2025,
        )

        assert formula is None
        assert len(issues) >= 1
        assert issues[0]["status"] == "ownership_denied"

    @settings(max_examples=5, deadline=None)
    @given(
        proj_a=st.uuids(),
        proj_b=st.uuids(),
    )
    @pytest.mark.asyncio
    async def test_pbt_cross_project_delete_always_rejected(
        self, proj_a: uuid.UUID, proj_b: uuid.UUID
    ):
        """**Validates: Property 13** — 任意两个不同 project 间 delete 总拒绝。"""
        assume(proj_a != proj_b)
        service = WpFormulaService()

        formula_obj = _make_formula_obj(project_id=proj_a)
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=formula_obj)
        session.execute = AsyncMock(return_value=result_mock)
        session.delete = AsyncMock()
        session.flush = AsyncMock()

        result = await service.delete(session, FORMULA_ID_A, project_id=proj_b)

        assert result is False
        session.delete.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════════════════════
# Reference 仅存关系（Req 5.1 — 不复制 expression 作为权威定义）
# ═══════════════════════════════════════════════════════════════════════════════


class TestReferenceOnlyStoresRelationship:
    """save reference 公式时只存 reference_formula_id 关系。"""

    @pytest.mark.asyncio
    @patch("app.services.wp_formula_service.validate_refs_via_acnr", new_callable=AsyncMock)
    @patch(
        "app.services.formula_management.reference_resolver.resolve_reference_expression",
        new_callable=AsyncMock,
    )
    async def test_reference_save_stores_formula_id_relationship(
        self, mock_resolve_ref, mock_validate
    ):
        """reference 来源保存 reference_formula_id 作为权威关系。"""
        ref_id = uuid.uuid4()
        mock_resolve_ref.return_value = MagicMock(
            resolved=True,
            expression="SOURCE_EXPR()",
            issue=None,
        )
        mock_validate.return_value = []

        service = WpFormulaService()
        session = _mock_session_for_ownership(wp_project_id=PROJECT_A, existing_formula=None)

        formula, issues = await service.save(
            session,
            project_id=PROJECT_A,
            wp_id=WP_ID_A,
            sheet_name="Sheet1",
            target_cell="E5",
            expression="placeholder",  # will be replaced by source
            year=2025,
            formula_source="reference",
            reference_formula_id=ref_id,
        )

        assert issues == []
        added = session.add.call_args[0][0]
        # reference_formula_id is the authority relationship
        assert added.reference_formula_id == ref_id
        assert added.formula_source == "reference"


# ═══════════════════════════════════════════════════════════════════════════════
# Utility function tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestNormalizeRefs:
    """_normalize_refs 规范化引用。"""

    def test_none_returns_empty(self):
        assert _normalize_refs(None) == []

    def test_empty_list_returns_empty(self):
        assert _normalize_refs([]) == []

    def test_dict_items_preserved(self):
        refs = [{"addr_id": "D1/Sheet1/B5"}, {"formula_ref": "WP('D1','B5')"}]
        assert _normalize_refs(refs) == refs

    def test_string_items_wrapped(self):
        refs = ["WP('D1','B5')", "TB('1001')"]
        result = _normalize_refs(refs)
        assert result == [
            {"formula_ref": "WP('D1','B5')"},
            {"formula_ref": "TB('1001')"},
        ]

    def test_empty_string_skipped(self):
        refs = ["", "  ", "VALID()"]
        result = _normalize_refs(refs)
        assert result == [{"formula_ref": "VALID()"}]
