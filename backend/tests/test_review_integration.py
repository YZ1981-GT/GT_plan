"""集成测试: 权限链路端到端验证.

验证 RBAC → Sequential Gate → Sign-Lock → Unlock → Dashboard 全链路联动。
使用 in-memory SQLite 模拟完整数据流。

Covers Task 10 sub-tasks:
- 10.1 RBAC 完整链路
- 10.2 签字→锁定→解锁完整流程
- 10.3 Sequential Gate + Dashboard 联动
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.staff_models import ProjectAssignment, StaffMember
from app.services.review_rbac_guard import (
    REVIEW_DEPENDENCY,
    REVIEW_ROLE_MAP,
    ReviewGuardResult,
    calc_unresolved_count,
    check_rbac,
    check_sequential_gate,
    check_sign_lock,
    evaluate_guard,
)

# Patch JSONB for SQLite
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db():
    """In-memory SQLite async session with all required tables."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS checklist_responses (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                wp_id TEXT NOT NULL,
                item_id VARCHAR(100) NOT NULL,
                conclusion VARCHAR(10),
                remark TEXT,
                wp_ref VARCHAR(100),
                updated_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(wp_id, item_id)
            )
        """))

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

    await engine.dispose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_user_with_role(
    db: AsyncSession,
    project_id: uuid.UUID,
    role: str,
    name: str = "测试用户",
) -> tuple[uuid.UUID, uuid.UUID]:
    """Create a staff + assignment, return (user_id, staff_id)."""
    user_id = uuid.uuid4()
    staff_id = uuid.uuid4()

    staff = StaffMember(id=staff_id, user_id=user_id, name=name)
    db.add(staff)
    await db.flush()

    assignment = ProjectAssignment(
        id=uuid.uuid4(),
        project_id=project_id,
        staff_id=staff_id,
        role=role,
    )
    db.add(assignment)
    await db.flush()

    return user_id, staff_id


async def _sign_checklist(
    db: AsyncSession,
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    wp_code: str,
    signer_staff_id: uuid.UUID,
    conclusion: str = "pass",
) -> str:
    """Insert a sign record. Returns record id."""
    record_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    remark = json.dumps({"signer_id": str(signer_staff_id), "signed_at": now})

    await db.execute(
        sa.text("""
            INSERT INTO checklist_responses
                (id, project_id, wp_id, item_id, conclusion, remark, created_at, updated_at)
            VALUES (:id, :pid, :wp_id, :item_id, :conclusion, :remark, :now, :now)
        """),
        {
            "id": record_id,
            "pid": str(project_id),
            "wp_id": str(wp_id),
            "item_id": f"{wp_code}-sign",
            "conclusion": conclusion,
            "remark": remark,
            "now": now,
        },
    )
    await db.flush()
    return record_id


async def _do_unlock(
    db: AsyncSession,
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    wp_code: str,
    user_id: uuid.UUID,
    reason: str = "需要修改",
) -> dict:
    """Simulate unlock logic (same as endpoint logic)."""
    # 1. Validate sign exists
    sign_item_id = f"{wp_code}-sign"
    sign_result = await db.execute(
        sa.text("""
            SELECT id, remark FROM checklist_responses
            WHERE project_id = :project_id
              AND item_id = :item_id
              AND conclusion = 'pass'
            LIMIT 1
        """),
        {"project_id": str(project_id), "item_id": sign_item_id},
    )
    sign_row = sign_result.first()
    assert sign_row is not None, "Cannot unlock: no sign record"

    # 2. Extract original signer
    original_signer_id = None
    if sign_row[1]:
        try:
            remark_data = json.loads(sign_row[1])
            original_signer_id = remark_data.get("signer_id")
        except (json.JSONDecodeError, TypeError):
            pass

    # 3. Delete sign record
    await db.execute(
        sa.text("DELETE FROM checklist_responses WHERE id = :id"),
        {"id": str(sign_row[0])},
    )

    # 4. Create unlock-log
    unlocked_at = datetime.now(timezone.utc).isoformat()
    unlock_remark = json.dumps({
        "unlocked_by": str(user_id),
        "unlocked_at": unlocked_at,
        "reason": reason,
        "original_signer_id": original_signer_id,
    }, ensure_ascii=False)

    await db.execute(
        sa.text("""
            INSERT INTO checklist_responses
                (id, project_id, wp_id, item_id, conclusion, remark, created_at, updated_at)
            VALUES (:id, :pid, :wp_id, :item_id, 'unlocked', :remark, :now, :now)
        """),
        {
            "id": str(uuid.uuid4()),
            "pid": str(project_id),
            "wp_id": str(wp_id),
            "item_id": f"{wp_code}-unlock-log",
            "remark": unlock_remark,
            "now": unlocked_at,
        },
    )
    await db.flush()
    return {"success": True, "unlocked_at": unlocked_at}


async def _insert_checklist_item(
    db: AsyncSession,
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    item_id: str,
    conclusion: str = "Y",
) -> None:
    """Insert a checklist response item."""
    await db.execute(
        sa.text("""
            INSERT INTO checklist_responses
                (id, project_id, wp_id, item_id, conclusion, created_at, updated_at)
            VALUES (:id, :pid, :wp_id, :item_id, :conclusion, :now, :now)
        """),
        {
            "id": str(uuid.uuid4()),
            "pid": str(project_id),
            "wp_id": str(wp_id),
            "item_id": item_id,
            "conclusion": conclusion,
            "now": datetime.now(timezone.utc).isoformat(),
        },
    )
    await db.flush()


# ===========================================================================
# 10.1 验证 RBAC 完整链路
# ===========================================================================


class TestRBACFullChain:
    """10.1: render-config → guard → readonly 注入 → 前端禁用全链路.

    确认 evaluate_guard 整合 RBAC、gate、lock 三重判定。
    确认无权用户操作返回 rbac_denied=True。
    """

    @pytest.mark.asyncio
    async def test_authorized_user_gets_readonly_false(self, db: AsyncSession):
        """有权用户: evaluate_guard → readonly=False, rbac_denied=False."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()

        user_id, _ = await _create_user_with_role(db, project_id, "senior", "现场负责人")

        result = await evaluate_guard(db, user_id, project_id, "A21", wp_id)

        assert result.readonly is False
        assert result.rbac_denied is False
        assert result.locked is False
        assert result.gate_reason is None

    @pytest.mark.asyncio
    async def test_unauthorized_user_gets_readonly_true(self, db: AsyncSession):
        """无权用户: evaluate_guard → readonly=True, rbac_denied=True."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()

        # manager 尝试访问 A21 (需要 senior/auditor)
        user_id, _ = await _create_user_with_role(db, project_id, "manager", "经理")

        result = await evaluate_guard(db, user_id, project_id, "A21", wp_id)

        assert result.readonly is True
        assert result.rbac_denied is True

    @pytest.mark.asyncio
    async def test_no_staff_record_gets_denied(self, db: AsyncSession):
        """无 staff 记录: evaluate_guard → rbac_denied=True (安全降级)."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()
        user_id = uuid.uuid4()  # No staff record

        result = await evaluate_guard(db, user_id, project_id, "A22", wp_id)

        assert result.readonly is True
        assert result.rbac_denied is True

    @pytest.mark.asyncio
    async def test_unauthorized_review_sign_returns_denied(self, db: AsyncSession):
        """无权用户 POST review-sign → check_rbac 返回 True (403)."""
        project_id = uuid.uuid4()

        # auditor 尝试签 A23 (需要 signing_partner)
        user_id, _ = await _create_user_with_role(db, project_id, "auditor", "审计助理")

        denied = await check_rbac(db, user_id, project_id, "A23")
        assert denied is True  # 后端应返回 403

    @pytest.mark.asyncio
    async def test_unauthorized_checklist_put_returns_denied(self, db: AsyncSession):
        """无权用户 PUT checklist-responses → check_rbac 返回 True (403)."""
        project_id = uuid.uuid4()

        # qc 尝试编辑 A21 (需要 senior/auditor)
        user_id, _ = await _create_user_with_role(db, project_id, "qc", "质控")

        denied = await check_rbac(db, user_id, project_id, "A21")
        assert denied is True  # 后端应返回 403

    @pytest.mark.asyncio
    async def test_each_level_requires_correct_role(self, db: AsyncSession):
        """验证每个级别对应正确的角色映射."""
        project_id = uuid.uuid4()

        for wp_code, allowed_roles in REVIEW_ROLE_MAP.items():
            # 创建有权用户
            user_id, _ = await _create_user_with_role(
                db, project_id, allowed_roles[0], f"{wp_code}用户"
            )
            denied = await check_rbac(db, user_id, project_id, wp_code)
            assert denied is False, f"{wp_code} with role {allowed_roles[0]} should be allowed"

    @pytest.mark.asyncio
    async def test_variant_suffix_rbac_works(self, db: AsyncSession):
        """变体后缀 (A21-1) 正确使用基础级别角色映射."""
        project_id = uuid.uuid4()

        user_id, _ = await _create_user_with_role(db, project_id, "senior", "现场负责人")

        denied = await check_rbac(db, user_id, project_id, "A21-1")
        assert denied is False

        denied = await check_rbac(db, user_id, project_id, "A21-2")
        assert denied is False


# ===========================================================================
# 10.2 验证签字→锁定→解锁完整流程
# ===========================================================================


class TestSignLockUnlockFlow:
    """10.2: Sign → locked=true → Unlock → locked=false + unlock-log exists.

    验证完整签字→锁定→解锁生命周期。
    """

    @pytest.mark.asyncio
    async def test_sign_then_guard_returns_locked(self, db: AsyncSession):
        """签字后 evaluate_guard 返回 locked=true + signed_by + signed_at."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()

        user_id, staff_id = await _create_user_with_role(
            db, project_id, "senior", "现场负责人张三"
        )

        # 签字
        await _sign_checklist(db, project_id, wp_id, "A21", staff_id)

        # 验证 guard
        result = await evaluate_guard(db, user_id, project_id, "A21", wp_id)

        assert result.readonly is True
        assert result.locked is True
        assert result.signed_by == "现场负责人张三"
        assert result.signed_at is not None

    @pytest.mark.asyncio
    async def test_locked_checklist_blocks_all_users(self, db: AsyncSession):
        """签字锁定后，即使有权用户也无法编辑 (readonly=True)."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()

        user_id, staff_id = await _create_user_with_role(
            db, project_id, "senior", "负责人"
        )

        await _sign_checklist(db, project_id, wp_id, "A21", staff_id)

        # 同一有权用户再看 → locked readonly
        result = await evaluate_guard(db, user_id, project_id, "A21", wp_id)
        assert result.readonly is True
        assert result.locked is True

    @pytest.mark.asyncio
    async def test_unlock_restores_editable(self, db: AsyncSession):
        """解锁后 evaluate_guard 返回 locked=False, readonly=False."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()

        user_id, staff_id = await _create_user_with_role(
            db, project_id, "senior", "负责人"
        )
        partner_user_id, _ = await _create_user_with_role(
            db, project_id, "signing_partner", "合伙人"
        )

        # 签字
        await _sign_checklist(db, project_id, wp_id, "A21", staff_id)

        # 验证锁定
        result = await evaluate_guard(db, user_id, project_id, "A21", wp_id)
        assert result.locked is True

        # 解锁
        unlock_result = await _do_unlock(
            db, project_id, wp_id, "A21", partner_user_id, "发现错误"
        )
        assert unlock_result["success"] is True

        # 验证解锁后恢复
        result = await evaluate_guard(db, user_id, project_id, "A21", wp_id)
        assert result.locked is False
        assert result.readonly is False

    @pytest.mark.asyncio
    async def test_unlock_creates_log_record(self, db: AsyncSession):
        """解锁后 -unlock-log 记录存在且包含必要信息."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()

        _, staff_id = await _create_user_with_role(db, project_id, "senior", "负责人")
        partner_user_id, _ = await _create_user_with_role(
            db, project_id, "signing_partner", "合伙人"
        )

        await _sign_checklist(db, project_id, wp_id, "A21", staff_id)
        await _do_unlock(db, project_id, wp_id, "A21", partner_user_id, "重新审核")

        # 查询 unlock-log
        log_result = await db.execute(
            sa.text("""
                SELECT conclusion, remark FROM checklist_responses
                WHERE project_id = :pid AND item_id = 'A21-unlock-log'
            """),
            {"pid": str(project_id)},
        )
        log_row = log_result.first()

        assert log_row is not None
        assert log_row[0] == "unlocked"

        remark_data = json.loads(log_row[1])
        assert remark_data["unlocked_by"] == str(partner_user_id)
        assert remark_data["reason"] == "重新审核"
        assert remark_data["original_signer_id"] == str(staff_id)
        assert "unlocked_at" in remark_data

    @pytest.mark.asyncio
    async def test_unlock_cascades_blocks_downstream(self, db: AsyncSession):
        """解锁后依赖链上游重新 gate-blocked.

        A21 签字 → A22 可编辑 → A21 解锁 → A22 重新被阻止.
        """
        project_id = uuid.uuid4()
        wp_id_a21 = uuid.uuid4()
        wp_id_a22 = uuid.uuid4()

        user_senior, staff_senior = await _create_user_with_role(
            db, project_id, "senior", "负责人"
        )
        user_manager, _ = await _create_user_with_role(
            db, project_id, "manager", "经理"
        )
        user_partner, _ = await _create_user_with_role(
            db, project_id, "signing_partner", "合伙人"
        )

        # A21 签字 → A22 应该可编辑
        await _sign_checklist(db, project_id, wp_id_a21, "A21", staff_senior)

        gate_blocked, reason = await check_sequential_gate(db, project_id, "A22")
        assert gate_blocked is False  # A22 不再被阻止

        # 解锁 A21
        await _do_unlock(db, project_id, wp_id_a21, "A21", user_partner, "需重审")

        # A22 应重新被 gate-blocked
        gate_blocked, reason = await check_sequential_gate(db, project_id, "A22")
        assert gate_blocked is True
        assert "A21" in reason


    @pytest.mark.asyncio
    async def test_sign_reject_does_not_lock(self, db: AsyncSession):
        """签字 reject 不锁定表."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()

        user_id, staff_id = await _create_user_with_role(
            db, project_id, "senior", "负责人"
        )

        await _sign_checklist(db, project_id, wp_id, "A21", staff_id, conclusion="reject")

        result = await evaluate_guard(db, user_id, project_id, "A21", wp_id)
        assert result.locked is False
        assert result.readonly is False

    @pytest.mark.asyncio
    async def test_unresolved_count_included_when_locked(self, db: AsyncSession):
        """锁定状态也应返回 unresolved_count (供前端展示)."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()

        user_id, staff_id = await _create_user_with_role(
            db, project_id, "senior", "负责人"
        )

        # 添加 unresolved items
        await _insert_checklist_item(db, project_id, wp_id, "A21-chk-1", "N")
        await _insert_checklist_item(db, project_id, wp_id, "A21-chk-2", "N")

        # 签字
        await _sign_checklist(db, project_id, wp_id, "A21", staff_id)

        result = await evaluate_guard(db, user_id, project_id, "A21", wp_id)
        assert result.locked is True
        assert result.unresolved_count == 2


# ===========================================================================
# 10.3 验证 Sequential Gate + Dashboard 联动
# ===========================================================================


class TestSequentialGateDashboard:
    """10.3: A21 签字后 A22 可编辑; 完整依赖链逐级解锁.

    验证逐级前置依赖 + evaluate_guard 联动。
    """

    @pytest.mark.asyncio
    async def test_a22_blocked_until_a21_signs(self, db: AsyncSession):
        """A21 未签字时 A22 被 gate-blocked."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()

        user_id, _ = await _create_user_with_role(db, project_id, "manager", "经理")

        result = await evaluate_guard(db, user_id, project_id, "A22", wp_id)

        assert result.readonly is True
        assert result.gate_reason is not None
        assert "A21" in result.gate_reason

    @pytest.mark.asyncio
    async def test_a22_editable_after_a21_signs(self, db: AsyncSession):
        """A21 签字后 A22 变为可编辑."""
        project_id = uuid.uuid4()
        wp_id_a21 = uuid.uuid4()
        wp_id_a22 = uuid.uuid4()

        _, staff_senior = await _create_user_with_role(
            db, project_id, "senior", "负责人"
        )
        user_manager, _ = await _create_user_with_role(
            db, project_id, "manager", "经理"
        )

        # A21 签字
        await _sign_checklist(db, project_id, wp_id_a21, "A21", staff_senior)

        # A22 evaluate_guard
        result = await evaluate_guard(db, user_manager, project_id, "A22", wp_id_a22)

        assert result.readonly is False
        assert result.gate_reason is None
        assert result.rbac_denied is False

    @pytest.mark.asyncio
    async def test_full_dependency_chain_sequential_unlock(self, db: AsyncSession):
        """完整依赖链: A21→A22→A23→A24→A25 逐级签字后逐级放行."""
        project_id = uuid.uuid4()
        wp_ids = {f"A2{i}": uuid.uuid4() for i in range(1, 6)}

        # 创建每级对应的用户
        users = {}
        staffs = {}
        for wp_code, roles in REVIEW_ROLE_MAP.items():
            uid, sid = await _create_user_with_role(
                db, project_id, roles[0], f"{wp_code}用户"
            )
            users[wp_code] = uid
            staffs[wp_code] = sid

        # A21 无前置，可直接编辑
        result = await evaluate_guard(
            db, users["A21"], project_id, "A21", wp_ids["A21"]
        )
        assert result.readonly is False

        # A22~A25 初始全被阻止
        for wp_code in ["A22", "A23", "A24", "A25"]:
            result = await evaluate_guard(
                db, users[wp_code], project_id, wp_code, wp_ids[wp_code]
            )
            assert result.readonly is True, f"{wp_code} should be blocked initially"
            assert result.gate_reason is not None

        # 逐级签字，验证下一级解锁
        chain = ["A21", "A22", "A23", "A24", "A25"]
        for i, wp_code in enumerate(chain[:-1]):
            # 签字当前级
            await _sign_checklist(
                db, project_id, wp_ids[wp_code], wp_code, staffs[wp_code]
            )

            # 下一级应该不再被 gate-blocked
            next_code = chain[i + 1]
            result = await evaluate_guard(
                db, users[next_code], project_id, next_code, wp_ids[next_code]
            )
            assert result.readonly is False, (
                f"{next_code} should be editable after {wp_code} signs"
            )
            assert result.gate_reason is None

    @pytest.mark.asyncio
    async def test_variant_dependency_chain(self, db: AsyncSession):
        """变体后缀依赖链: A21-1 → A22-1 → A23-1."""
        project_id = uuid.uuid4()
        wp_id_a21 = uuid.uuid4()
        wp_id_a22 = uuid.uuid4()

        _, staff_senior = await _create_user_with_role(
            db, project_id, "senior", "负责人"
        )
        user_manager, _ = await _create_user_with_role(
            db, project_id, "manager", "经理"
        )

        # A22-1 被阻止 (A21-1 未签字)
        result = await evaluate_guard(db, user_manager, project_id, "A22-1", wp_id_a22)
        assert result.readonly is True
        assert "A21-1" in result.gate_reason

        # 签 A21-1
        await _sign_checklist(db, project_id, wp_id_a21, "A21-1", staff_senior)

        # A22-1 放行
        result = await evaluate_guard(db, user_manager, project_id, "A22-1", wp_id_a22)
        assert result.readonly is False
        assert result.gate_reason is None

    @pytest.mark.asyncio
    async def test_variant_isolation(self, db: AsyncSession):
        """不同变体互不影响: A21-1 签字不放行 A22-2."""
        project_id = uuid.uuid4()
        wp_id_a21_1 = uuid.uuid4()
        wp_id_a22_2 = uuid.uuid4()

        _, staff_senior = await _create_user_with_role(
            db, project_id, "senior", "负责人"
        )
        user_manager, _ = await _create_user_with_role(
            db, project_id, "manager", "经理"
        )

        # 签 A21-1
        await _sign_checklist(db, project_id, wp_id_a21_1, "A21-1", staff_senior)

        # A22-2 仍被阻止 (需要 A21-2 签字)
        result = await evaluate_guard(db, user_manager, project_id, "A22-2", wp_id_a22_2)
        assert result.readonly is True
        assert "A21-2" in result.gate_reason

    @pytest.mark.asyncio
    async def test_combined_rbac_and_gate(self, db: AsyncSession):
        """同时违反 RBAC + gate 时 readonly=True (双重保护)."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()

        # auditor 试图访问 A22 (需要 manager 角色 + A21 签字)
        user_id, _ = await _create_user_with_role(db, project_id, "auditor", "助理")

        result = await evaluate_guard(db, user_id, project_id, "A22", wp_id)
        assert result.readonly is True
        assert result.rbac_denied is True
        assert result.gate_reason is not None  # 也有 gate 原因

    @pytest.mark.asyncio
    async def test_dashboard_status_reflects_sign(self, db: AsyncSession):
        """签字后 check_sign_lock 反映状态 (Dashboard 数据来源)."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()

        _, staff_id = await _create_user_with_role(
            db, project_id, "senior", "现场负责人"
        )

        # 未签字
        locked, signed_by, signed_at = await check_sign_lock(db, project_id, "A21")
        assert locked is False

        # 签字
        await _sign_checklist(db, project_id, wp_id, "A21", staff_id)

        # 已签字
        locked, signed_by, signed_at = await check_sign_lock(db, project_id, "A21")
        assert locked is True
        assert signed_by == "现场负责人"
        assert signed_at is not None

    @pytest.mark.asyncio
    async def test_unresolved_blocks_sign_flow(self, db: AsyncSession):
        """未清意见 > 0 时阻止签字 (calc_unresolved_count 集成验证)."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()

        user_id, _ = await _create_user_with_role(db, project_id, "senior", "负责人")

        # 添加 N 结论 items
        await _insert_checklist_item(db, project_id, wp_id, "A21-chk-1", "N")
        await _insert_checklist_item(db, project_id, wp_id, "A21-chk-2", "N")
        await _insert_checklist_item(db, project_id, wp_id, "A21-chk-3", "Y")

        result = await evaluate_guard(db, user_id, project_id, "A21", wp_id)
        assert result.unresolved_count == 2

        # 清零后
        await db.execute(
            sa.text("""
                UPDATE checklist_responses
                SET conclusion = 'Y'
                WHERE wp_id = :wp_id AND conclusion = 'N'
            """),
            {"wp_id": str(wp_id)},
        )
        await db.flush()

        result = await evaluate_guard(db, user_id, project_id, "A21", wp_id)
        assert result.unresolved_count == 0
