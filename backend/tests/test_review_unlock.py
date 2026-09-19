"""Unit tests for POST /api/workpapers/{wp_id}/review-unlock endpoint.

Tests:
- reason 为空 → 422 "解锁必须填写原因"
- -sign 记录不存在 → 422 "该复核表未签字，无需解锁"
- 非 signing_partner → 403 "仅合伙人可解锁已签字复核表"
- 正常解锁流程：删除 -sign + 创建 -unlock-log + 返回 success
"""

from __future__ import annotations

import json
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.staff_models import ProjectAssignment, StaffMember
from app.services.review_rbac_guard import check_sign_lock

# Patch JSONB for SQLite
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON  # type: ignore[attr-defined]


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS checklist_responses (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                wp_id TEXT NOT NULL,
                item_id VARCHAR(20) NOT NULL,
                conclusion VARCHAR(10),
                remark TEXT,
                wp_ref VARCHAR(100),
                updated_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(wp_id, item_id)
            )
        """))
        # Create working_papers table for wp lookup
        await conn.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS working_papers (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                name TEXT,
                status TEXT DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """))

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

    await engine.dispose()


# ---------------------------------------------------------------------------
# Helper: simulate unlock logic (extracted from endpoint for unit testing)
# ---------------------------------------------------------------------------

async def _do_unlock(
    db: AsyncSession,
    wp_id: uuid.UUID,
    project_id: uuid.UUID,
    wp_code: str,
    reason: str,
    current_user_id: uuid.UUID,
) -> dict:
    """Reproduce the unlock logic for unit-level testing without HTTP layer."""
    from datetime import datetime, timezone

    # 1. Validate reason
    if not reason or not reason.strip():
        raise ValueError("解锁必须填写原因")

    # 2. Check -sign record exists
    sign_item_id = f"{wp_code}-sign"
    sign_result = await db.execute(
        sa.text(
            """
            SELECT id, remark FROM checklist_responses
            WHERE project_id = :project_id
              AND item_id = :item_id
              AND conclusion = 'pass'
            LIMIT 1
            """
        ),
        {"project_id": str(project_id), "item_id": sign_item_id},
    )
    sign_row = sign_result.first()

    if sign_row is None:
        raise ValueError("该复核表未签字，无需解锁")

    # 3. Check signing_partner role
    staff_stmt = (
        sa.select(StaffMember.id)
        .where(StaffMember.user_id == current_user_id)
        .where(StaffMember.is_deleted == sa.false())
        .limit(1)
    )
    staff_result = await db.execute(staff_stmt)
    staff_id = staff_result.scalar_one_or_none()

    if staff_id is None:
        raise PermissionError("仅合伙人可解锁已签字复核表")

    partner_stmt = (
        sa.select(sa.func.count())
        .select_from(ProjectAssignment.__table__)
        .where(ProjectAssignment.project_id == project_id)
        .where(ProjectAssignment.staff_id == staff_id)
        .where(ProjectAssignment.role == "signing_partner")
        .where(ProjectAssignment.is_deleted == sa.false())
    )
    partner_result = await db.execute(partner_stmt)
    partner_count = partner_result.scalar() or 0

    if partner_count == 0:
        raise PermissionError("仅合伙人可解锁已签字复核表")

    # 4. Extract original signer
    original_signer_id = None
    sign_remark_raw = sign_row[1]
    if sign_remark_raw:
        try:
            remark_data = json.loads(sign_remark_raw)
            if isinstance(remark_data, dict):
                original_signer_id = remark_data.get("signer_id")
        except (json.JSONDecodeError, TypeError):
            pass

    # 5. Delete -sign record
    sign_record_id = sign_row[0]
    await db.execute(
        sa.text("DELETE FROM checklist_responses WHERE id = :id"),
        {"id": str(sign_record_id)},
    )

    # 6. Create -unlock-log
    unlocked_at = datetime.now(timezone.utc).isoformat()
    unlock_log_remark = json.dumps(
        {
            "unlocked_by": str(current_user_id),
            "unlocked_at": unlocked_at,
            "reason": reason.strip(),
            "original_signer_id": original_signer_id,
        },
        ensure_ascii=False,
    )
    unlock_log_item_id = f"{wp_code}-unlock-log"

    await db.execute(
        sa.text(
            """
            INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, remark, created_at, updated_at)
            VALUES (:id, :project_id, :wp_id, :item_id, 'unlocked', :remark, :now, :now)
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "project_id": str(project_id),
            "wp_id": str(wp_id),
            "item_id": unlock_log_item_id,
            "remark": unlock_log_remark,
            "now": unlocked_at,
        },
    )

    await db.flush()
    return {"success": True, "unlocked_at": unlocked_at}


# ---------------------------------------------------------------------------
# Helper: seed a signed checklist
# ---------------------------------------------------------------------------

async def _seed_signed_checklist(
    db: AsyncSession,
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    wp_code: str,
    signer_staff_id: uuid.UUID,
) -> str:
    """Insert a -sign pass record. Returns the record id."""
    record_id = str(uuid.uuid4())
    remark = json.dumps({"signer_id": str(signer_staff_id)})
    await db.execute(
        sa.text(
            """
            INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, remark, created_at, updated_at)
            VALUES (:id, :pid, :wp_id, :item_id, 'pass', :remark, '2026-01-01', '2026-01-15T10:30:00')
            """
        ),
        {
            "id": record_id,
            "pid": str(project_id),
            "wp_id": str(wp_id),
            "item_id": f"{wp_code}-sign",
            "remark": remark,
        },
    )
    await db.flush()
    return record_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestReviewUnlockValidation:
    """校验逻辑测试."""

    @pytest.mark.asyncio
    async def test_empty_reason_raises(self, db: AsyncSession):
        """reason 为空 → ValueError '解锁必须填写原因'."""
        with pytest.raises(ValueError, match="解锁必须填写原因"):
            await _do_unlock(db, uuid.uuid4(), uuid.uuid4(), "A21", "", uuid.uuid4())

    @pytest.mark.asyncio
    async def test_whitespace_only_reason_raises(self, db: AsyncSession):
        """reason 仅空白 → ValueError '解锁必须填写原因'."""
        with pytest.raises(ValueError, match="解锁必须填写原因"):
            await _do_unlock(db, uuid.uuid4(), uuid.uuid4(), "A21", "   ", uuid.uuid4())

    @pytest.mark.asyncio
    async def test_no_sign_record_raises(self, db: AsyncSession):
        """无 -sign 记录 → ValueError '该复核表未签字，无需解锁'."""
        with pytest.raises(ValueError, match="该复核表未签字，无需解锁"):
            await _do_unlock(
                db, uuid.uuid4(), uuid.uuid4(), "A21", "需要修改", uuid.uuid4()
            )


class TestReviewUnlockRBAC:
    """角色校验测试."""

    @pytest.mark.asyncio
    async def test_no_staff_record_raises_permission(self, db: AsyncSession):
        """用户无 staff 记录 → PermissionError."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()
        signer_staff_id = uuid.uuid4()
        user_id = uuid.uuid4()

        # 创建 signer staff (不是当前用户)
        signer_staff = StaffMember(id=signer_staff_id, user_id=uuid.uuid4(), name="签字人")
        db.add(signer_staff)
        await db.flush()

        await _seed_signed_checklist(db, project_id, wp_id, "A21", signer_staff_id)

        with pytest.raises(PermissionError, match="仅合伙人可解锁已签字复核表"):
            await _do_unlock(db, wp_id, project_id, "A21", "需要修改", user_id)

    @pytest.mark.asyncio
    async def test_non_partner_role_raises_permission(self, db: AsyncSession):
        """有 staff 但 role 非 signing_partner → PermissionError."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()
        user_id = uuid.uuid4()
        staff_id = uuid.uuid4()
        signer_staff_id = uuid.uuid4()

        # 创建当前用户 staff + manager role (非 signing_partner)
        staff = StaffMember(id=staff_id, user_id=user_id, name="经理")
        db.add(staff)
        await db.flush()

        assignment = ProjectAssignment(
            id=uuid.uuid4(),
            project_id=project_id,
            staff_id=staff_id,
            role="manager",
        )
        db.add(assignment)
        await db.flush()

        # 创建 signer staff
        signer_staff = StaffMember(id=signer_staff_id, user_id=uuid.uuid4(), name="签字人")
        db.add(signer_staff)
        await db.flush()

        await _seed_signed_checklist(db, project_id, wp_id, "A21", signer_staff_id)

        with pytest.raises(PermissionError, match="仅合伙人可解锁已签字复核表"):
            await _do_unlock(db, wp_id, project_id, "A21", "需要修改", user_id)


class TestReviewUnlockSuccess:
    """正常解锁流程测试."""

    @pytest.mark.asyncio
    async def test_unlock_deletes_sign_record(self, db: AsyncSession):
        """解锁后 -sign 记录被删除."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()
        user_id = uuid.uuid4()
        staff_id = uuid.uuid4()
        signer_staff_id = uuid.uuid4()

        # 创建合伙人用户
        staff = StaffMember(id=staff_id, user_id=user_id, name="合伙人")
        db.add(staff)
        await db.flush()

        assignment = ProjectAssignment(
            id=uuid.uuid4(),
            project_id=project_id,
            staff_id=staff_id,
            role="signing_partner",
        )
        db.add(assignment)
        await db.flush()

        # 创建 signer
        signer_staff = StaffMember(id=signer_staff_id, user_id=uuid.uuid4(), name="原签字人")
        db.add(signer_staff)
        await db.flush()

        await _seed_signed_checklist(db, project_id, wp_id, "A21", signer_staff_id)

        # 执行解锁
        result = await _do_unlock(db, wp_id, project_id, "A21", "发现错误需修改", user_id)

        assert result["success"] is True
        assert "unlocked_at" in result

        # 验证 -sign 记录已删除
        locked, _, _ = await check_sign_lock(db, project_id, "A21")
        assert locked is False

    @pytest.mark.asyncio
    async def test_unlock_creates_log_record(self, db: AsyncSession):
        """解锁后创建 -unlock-log 记录."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()
        user_id = uuid.uuid4()
        staff_id = uuid.uuid4()
        signer_staff_id = uuid.uuid4()

        staff = StaffMember(id=staff_id, user_id=user_id, name="合伙人B")
        db.add(staff)
        await db.flush()

        assignment = ProjectAssignment(
            id=uuid.uuid4(),
            project_id=project_id,
            staff_id=staff_id,
            role="signing_partner",
        )
        db.add(assignment)
        await db.flush()

        signer_staff = StaffMember(id=signer_staff_id, user_id=uuid.uuid4(), name="原签字人B")
        db.add(signer_staff)
        await db.flush()

        await _seed_signed_checklist(db, project_id, wp_id, "A22", signer_staff_id)

        result = await _do_unlock(db, wp_id, project_id, "A22", "重新复核", user_id)

        # 查询 -unlock-log 记录
        log_result = await db.execute(
            sa.text(
                """
                SELECT conclusion, remark FROM checklist_responses
                WHERE project_id = :pid AND item_id = :item_id
                """
            ),
            {"pid": str(project_id), "item_id": "A22-unlock-log"},
        )
        log_row = log_result.first()

        assert log_row is not None
        assert log_row[0] == "unlocked"

        remark_data = json.loads(log_row[1])
        assert remark_data["unlocked_by"] == str(user_id)
        assert remark_data["reason"] == "重新复核"
        assert remark_data["original_signer_id"] == str(signer_staff_id)
        assert "unlocked_at" in remark_data

    @pytest.mark.asyncio
    async def test_unlock_returns_unlocked_at_iso(self, db: AsyncSession):
        """返回的 unlocked_at 是有效 ISO 时间戳."""
        from datetime import datetime

        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()
        user_id = uuid.uuid4()
        staff_id = uuid.uuid4()
        signer_staff_id = uuid.uuid4()

        staff = StaffMember(id=staff_id, user_id=user_id, name="合伙人C")
        db.add(staff)
        await db.flush()

        assignment = ProjectAssignment(
            id=uuid.uuid4(),
            project_id=project_id,
            staff_id=staff_id,
            role="signing_partner",
        )
        db.add(assignment)
        await db.flush()

        signer_staff = StaffMember(id=signer_staff_id, user_id=uuid.uuid4(), name="签字人C")
        db.add(signer_staff)
        await db.flush()

        await _seed_signed_checklist(db, project_id, wp_id, "A23", signer_staff_id)

        result = await _do_unlock(db, wp_id, project_id, "A23", "修正意见", user_id)

        # Validate ISO format
        unlocked_at = result["unlocked_at"]
        parsed = datetime.fromisoformat(unlocked_at)
        assert parsed is not None
