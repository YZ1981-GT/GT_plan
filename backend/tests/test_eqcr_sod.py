"""R5 Task 2: EQCR 独立性 SoD 规则测试

Validates: Requirements 1.3 (R5 需求 1 验收标准 3) — EQCR 不得同时是同项目的
signing_partner / manager / auditor / qc。

覆盖 :func:`validate_eqcr_sod_in_batch`（纯函数，批内互斥）与
:meth:`SoDGuardService.check_assignment_independence`（DB 级校验）。
"""

from __future__ import annotations

import uuid

import pytest

from app.services.sod_guard_service import (
    SodViolation,
    sod_guard_service,
    validate_eqcr_sod_in_batch,
)


# ---------------------------------------------------------------------------
# 纯函数批内校验
# ---------------------------------------------------------------------------


class TestValidateEqcrSodInBatch:
    """批内 EQCR 独立性校验（提交前预检）"""

    def test_eqcr_then_conflict_in_batch_raises(self) -> None:
        """同一 staff_id 先 eqcr 后 signing_partner 应抛 SodViolation"""
        staff_id = str(uuid.uuid4())
        batch = [
            {"staff_id": staff_id, "role": "eqcr"},
            {"staff_id": staff_id, "role": "signing_partner"},
        ]
        with pytest.raises(SodViolation) as exc_info:
            validate_eqcr_sod_in_batch(batch)
        assert exc_info.value.policy_code == "SOD_EQCR_INDEPENDENCE_CONFLICT"
        assert staff_id in str(exc_info.value)

    def test_conflict_then_eqcr_in_batch_raises(self) -> None:
        """顺序反过来同样应抛 SodViolation（集合语义不依赖顺序）"""
        staff_id = str(uuid.uuid4())
        batch = [
            {"staff_id": staff_id, "role": "manager"},
            {"staff_id": staff_id, "role": "eqcr"},
        ]
        with pytest.raises(SodViolation) as exc_info:
            validate_eqcr_sod_in_batch(batch)
        assert exc_info.value.policy_code == "SOD_EQCR_INDEPENDENCE_CONFLICT"

    def test_eqcr_alone_passes(self) -> None:
        """只担任 eqcr 无冲突角色，不应抛异常"""
        staff_id = str(uuid.uuid4())
        batch = [{"staff_id": staff_id, "role": "eqcr"}]
        # 不应抛异常
        validate_eqcr_sod_in_batch(batch)

    def test_eqcr_and_partner_different_staff_passes(self) -> None:
        """不同 staff_id 分别担任 eqcr 与 signing_partner → 合规"""
        staff_a = str(uuid.uuid4())
        staff_b = str(uuid.uuid4())
        batch = [
            {"staff_id": staff_a, "role": "eqcr"},
            {"staff_id": staff_b, "role": "signing_partner"},
            {"staff_id": staff_b, "role": "manager"},  # partner+manager 不违反 EQCR 规则
        ]
        # 不应抛异常（本规则只关注 eqcr 与其它角色互斥）
        validate_eqcr_sod_in_batch(batch)

    def test_eqcr_with_all_four_conflict_roles_raises(self) -> None:
        """eqcr 与四个冲突角色全部同批 → 抛异常，错误信息含所有冲突角色"""
        staff_id = str(uuid.uuid4())
        batch = [
            {"staff_id": staff_id, "role": "eqcr"},
            {"staff_id": staff_id, "role": "signing_partner"},
            {"staff_id": staff_id, "role": "manager"},
            {"staff_id": staff_id, "role": "auditor"},
            {"staff_id": staff_id, "role": "qc"},
        ]
        with pytest.raises(SodViolation) as exc_info:
            validate_eqcr_sod_in_batch(batch)
        msg = str(exc_info.value)
        # 错误信息至少应展示冲突角色列表中的一个代表值
        assert "signing_partner" in msg or "manager" in msg or "auditor" in msg or "qc" in msg

    def test_empty_batch_passes(self) -> None:
        """空批次应视为合规"""
        validate_eqcr_sod_in_batch([])

    def test_duplicate_eqcr_same_staff_passes(self) -> None:
        """同一人重复 eqcr 角色本身不违反独立性规则（由上层唯一约束处理）"""
        staff_id = str(uuid.uuid4())
        batch = [
            {"staff_id": staff_id, "role": "eqcr"},
            {"staff_id": staff_id, "role": "eqcr"},
        ]
        validate_eqcr_sod_in_batch(batch)


# ---------------------------------------------------------------------------
# 服务方法（DB 校验）
# ---------------------------------------------------------------------------


class TestCheckAssignmentIndependence:
    """服务级 SoD 校验（读数据库已存在分配）

    使用轻量级 mock session 避免完整集成环境。
    """

    class _FakeResult:
        def __init__(self, rows: list[tuple[str]]):
            self._rows = rows

        def all(self) -> list[tuple[str]]:
            return self._rows

    class _FakeSession:
        def __init__(self, existing_roles: list[str]):
            self._existing_roles = existing_roles

        async def execute(self, stmt):  # noqa: ARG002
            return TestCheckAssignmentIndependence._FakeResult(
                [(r,) for r in self._existing_roles]
            )

    @pytest.mark.asyncio
    async def test_new_eqcr_with_existing_partner_raises(self) -> None:
        """已是 signing_partner → 再赋 eqcr 抛异常"""
        session = self._FakeSession(["signing_partner"])
        with pytest.raises(SodViolation) as exc_info:
            await sod_guard_service.check_assignment_independence(
                db=session,  # type: ignore[arg-type]
                project_id=uuid.uuid4(),
                staff_id=uuid.uuid4(),
                new_role="eqcr",
            )
        assert exc_info.value.policy_code == "SOD_EQCR_INDEPENDENCE_CONFLICT"

    @pytest.mark.asyncio
    async def test_new_partner_with_existing_eqcr_raises(self) -> None:
        """已是 eqcr → 再赋 signing_partner 抛异常"""
        session = self._FakeSession(["eqcr"])
        with pytest.raises(SodViolation):
            await sod_guard_service.check_assignment_independence(
                db=session,  # type: ignore[arg-type]
                project_id=uuid.uuid4(),
                staff_id=uuid.uuid4(),
                new_role="signing_partner",
            )

    @pytest.mark.asyncio
    async def test_new_eqcr_with_no_existing_passes(self) -> None:
        """无既有角色 → 首次赋 eqcr 合规"""
        session = self._FakeSession([])
        await sod_guard_service.check_assignment_independence(
            db=session,  # type: ignore[arg-type]
            project_id=uuid.uuid4(),
            staff_id=uuid.uuid4(),
            new_role="eqcr",
        )

    @pytest.mark.asyncio
    async def test_partner_and_manager_no_eqcr_passes(self) -> None:
        """签字合伙人 + 经理无 eqcr → 新增另一冲突角色不触发 EQCR 规则

        （这些冲突可能由其他 SoD 规则处理，不属于本规则范围）
        """
        session = self._FakeSession(["signing_partner"])
        await sod_guard_service.check_assignment_independence(
            db=session,  # type: ignore[arg-type]
            project_id=uuid.uuid4(),
            staff_id=uuid.uuid4(),
            new_role="manager",
        )
