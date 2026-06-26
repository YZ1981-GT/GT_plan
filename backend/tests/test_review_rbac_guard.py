"""Unit tests for review_rbac_guard.check_rbac.

Tests RBAC check logic:
- wp_code 不在 REVIEW_ROLE_MAP → 放行 (False)
- user_id 无 staff 记录 → 安全降级 (True)
- 有 staff 但无匹配 project_assignment → denied (True)
- 有 staff 且有匹配 role → allowed (False)
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.staff_models import ProjectAssignment, StaffMember
from app.services.review_rbac_guard import check_rbac, check_sequential_gate, check_sign_lock, extract_base_level, extract_variant_suffix

# ---------------------------------------------------------------------------
# SQLite async fixture (in-memory)
# ---------------------------------------------------------------------------

# Patch JSONB for SQLite
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON  # type: ignore[attr-defined]


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # checklist_responses is not ORM-mapped; create manually for tests
        await conn.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS checklist_responses (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                wp_id TEXT NOT NULL,
                item_id VARCHAR(20) NOT NULL,
                conclusion VARCHAR(5),
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
# extract_base_level tests
# ---------------------------------------------------------------------------


class TestExtractBaseLevel:
    def test_plain_code(self):
        assert extract_base_level("A21") == "A21"
        assert extract_base_level("A22") == "A22"
        assert extract_base_level("A25") == "A25"

    def test_variant_suffix(self):
        assert extract_base_level("A21-1") == "A21"
        assert extract_base_level("A22-2") == "A22"
        assert extract_base_level("A25-1") == "A25"

    def test_non_review_code(self):
        assert extract_base_level("B50") is None
        assert extract_base_level("A1") is None
        assert extract_base_level("D2-1") is None
        assert extract_base_level("A20") is None
        assert extract_base_level("A26") is None


# ---------------------------------------------------------------------------
# check_rbac tests
# ---------------------------------------------------------------------------


class TestCheckRbac:
    @pytest.mark.asyncio
    async def test_non_review_wp_code_returns_false(self, db: AsyncSession):
        """wp_code 不在 REVIEW_ROLE_MAP 时直接返回 False（不受管辖）."""
        result = await check_rbac(db, uuid.uuid4(), uuid.uuid4(), "B50")
        assert result is False

    @pytest.mark.asyncio
    async def test_no_staff_record_returns_true(self, db: AsyncSession):
        """user_id 无对应 staff 记录时返回 True（安全降级）."""
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()
        result = await check_rbac(db, user_id, project_id, "A21")
        assert result is True

    @pytest.mark.asyncio
    async def test_staff_no_assignment_returns_true(self, db: AsyncSession):
        """有 staff 但无匹配 project_assignment → denied."""
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()
        staff = StaffMember(id=uuid.uuid4(), user_id=user_id, name="张三")
        db.add(staff)
        await db.flush()

        result = await check_rbac(db, user_id, project_id, "A21")
        assert result is True

    @pytest.mark.asyncio
    async def test_staff_wrong_role_returns_true(self, db: AsyncSession):
        """有 staff + assignment 但 role 不匹配 → denied."""
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()
        staff_id = uuid.uuid4()

        staff = StaffMember(id=staff_id, user_id=user_id, name="李四")
        db.add(staff)
        await db.flush()

        # A21 需要 senior 或 auditor，给 manager
        assignment = ProjectAssignment(
            id=uuid.uuid4(),
            project_id=project_id,
            staff_id=staff_id,
            role="manager",
        )
        db.add(assignment)
        await db.flush()

        result = await check_rbac(db, user_id, project_id, "A21")
        assert result is True

    @pytest.mark.asyncio
    async def test_staff_correct_role_returns_false(self, db: AsyncSession):
        """有 staff + assignment 且 role 匹配 → allowed."""
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()
        staff_id = uuid.uuid4()

        staff = StaffMember(id=staff_id, user_id=user_id, name="王五")
        db.add(staff)
        await db.flush()

        assignment = ProjectAssignment(
            id=uuid.uuid4(),
            project_id=project_id,
            staff_id=staff_id,
            role="auditor",  # A21 允许 auditor
        )
        db.add(assignment)
        await db.flush()

        result = await check_rbac(db, user_id, project_id, "A21")
        assert result is False

    @pytest.mark.asyncio
    async def test_a22_manager_allowed(self, db: AsyncSession):
        """A22 需要 manager 角色."""
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()
        staff_id = uuid.uuid4()

        staff = StaffMember(id=staff_id, user_id=user_id, name="赵六")
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

        result = await check_rbac(db, user_id, project_id, "A22")
        assert result is False

    @pytest.mark.asyncio
    async def test_variant_suffix_respected(self, db: AsyncSession):
        """wp_code 含变体后缀 (A21-1) 仍正确提取基础级别."""
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()
        staff_id = uuid.uuid4()

        staff = StaffMember(id=staff_id, user_id=user_id, name="孙七")
        db.add(staff)
        await db.flush()

        assignment = ProjectAssignment(
            id=uuid.uuid4(),
            project_id=project_id,
            staff_id=staff_id,
            role="senior",  # A21 允许 senior
        )
        db.add(assignment)
        await db.flush()

        result = await check_rbac(db, user_id, project_id, "A21-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_deleted_staff_ignored(self, db: AsyncSession):
        """软删除的 staff 记录应被忽略."""
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()
        staff_id = uuid.uuid4()

        staff = StaffMember(
            id=staff_id, user_id=user_id, name="周八", is_deleted=True
        )
        db.add(staff)
        await db.flush()

        result = await check_rbac(db, user_id, project_id, "A21")
        assert result is True  # 软删除 → 视为无 staff

    @pytest.mark.asyncio
    async def test_deleted_assignment_ignored(self, db: AsyncSession):
        """软删除的 assignment 应被忽略."""
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()
        staff_id = uuid.uuid4()

        staff = StaffMember(id=staff_id, user_id=user_id, name="吴九")
        db.add(staff)
        await db.flush()

        assignment = ProjectAssignment(
            id=uuid.uuid4(),
            project_id=project_id,
            staff_id=staff_id,
            role="auditor",
            is_deleted=True,
        )
        db.add(assignment)
        await db.flush()

        result = await check_rbac(db, user_id, project_id, "A21")
        assert result is True  # 软删除 assignment → 无匹配


# ---------------------------------------------------------------------------
# extract_variant_suffix tests
# ---------------------------------------------------------------------------


class TestExtractVariantSuffix:
    def test_no_suffix(self):
        assert extract_variant_suffix("A21") == ""
        assert extract_variant_suffix("A22") == ""

    def test_with_suffix(self):
        assert extract_variant_suffix("A21-1") == "-1"
        assert extract_variant_suffix("A22-2") == "-2"
        assert extract_variant_suffix("A25-1") == "-1"

    def test_non_review_code(self):
        # Non-review codes return empty (extract_base_level would return None)
        assert extract_variant_suffix("B50") == ""
        assert extract_variant_suffix("D2-1") == ""


# ---------------------------------------------------------------------------
# check_sequential_gate tests
# ---------------------------------------------------------------------------


class TestCheckSequentialGate:
    @pytest.mark.asyncio
    async def test_a21_always_passes(self, db: AsyncSession):
        """A21 无前置依赖，始终放行."""
        project_id = uuid.uuid4()
        blocked, reason = await check_sequential_gate(db, project_id, "A21")
        assert blocked is False
        assert reason is None

    @pytest.mark.asyncio
    async def test_a21_variant_always_passes(self, db: AsyncSession):
        """A21-1 / A21-2 也无前置依赖."""
        project_id = uuid.uuid4()
        blocked, reason = await check_sequential_gate(db, project_id, "A21-1")
        assert blocked is False
        assert reason is None

    @pytest.mark.asyncio
    async def test_a22_blocked_when_a21_not_signed(self, db: AsyncSession):
        """A22 被阻止，因为 A21-sign 不存在."""
        project_id = uuid.uuid4()
        blocked, reason = await check_sequential_gate(db, project_id, "A22")
        assert blocked is True
        assert reason == "需先完成 A21 复核并签字"

    @pytest.mark.asyncio
    async def test_a22_allowed_when_a21_signed(self, db: AsyncSession):
        """A22 放行，因为 A21-sign conclusion='pass' 存在."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()

        # 插入 A21-sign pass 记录
        await db.execute(
            sa.text(
                """
                INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, created_at, updated_at)
                VALUES (:id, :pid, :wp_id, 'A21-sign', 'pass', '2026-01-01', '2026-01-01')
                """
            ),
            {"id": str(uuid.uuid4()), "pid": str(project_id), "wp_id": str(wp_id)},
        )
        await db.flush()

        blocked, reason = await check_sequential_gate(db, project_id, "A22")
        assert blocked is False
        assert reason is None

    @pytest.mark.asyncio
    async def test_a22_blocked_when_a21_rejected(self, db: AsyncSession):
        """A22 被阻止，A21-sign conclusion='reject' 不算 pass."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()

        await db.execute(
            sa.text(
                """
                INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, created_at, updated_at)
                VALUES (:id, :pid, :wp_id, 'A21-sign', 'reject', '2026-01-01', '2026-01-01')
                """
            ),
            {"id": str(uuid.uuid4()), "pid": str(project_id), "wp_id": str(wp_id)},
        )
        await db.flush()

        blocked, reason = await check_sequential_gate(db, project_id, "A22")
        assert blocked is True
        assert reason == "需先完成 A21 复核并签字"

    @pytest.mark.asyncio
    async def test_variant_matching_a22_1_requires_a21_1(self, db: AsyncSession):
        """A22-1 要求 A21-1-sign 已签字（变体匹配）."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()

        # 只有 A21-sign (无变体) pass — 对 A22-1 不应放行
        await db.execute(
            sa.text(
                """
                INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, created_at, updated_at)
                VALUES (:id, :pid, :wp_id, 'A21-sign', 'pass', '2026-01-01', '2026-01-01')
                """
            ),
            {"id": str(uuid.uuid4()), "pid": str(project_id), "wp_id": str(wp_id)},
        )
        await db.flush()

        blocked, reason = await check_sequential_gate(db, project_id, "A22-1")
        assert blocked is True
        assert reason == "需先完成 A21-1 复核并签字"

    @pytest.mark.asyncio
    async def test_variant_matching_a22_1_allowed(self, db: AsyncSession):
        """A22-1 放行，因为 A21-1-sign pass 存在."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()

        await db.execute(
            sa.text(
                """
                INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, created_at, updated_at)
                VALUES (:id, :pid, :wp_id, 'A21-1-sign', 'pass', '2026-01-01', '2026-01-01')
                """
            ),
            {"id": str(uuid.uuid4()), "pid": str(project_id), "wp_id": str(wp_id)},
        )
        await db.flush()

        blocked, reason = await check_sequential_gate(db, project_id, "A22-1")
        assert blocked is False
        assert reason is None

    @pytest.mark.asyncio
    async def test_non_review_wp_code_not_blocked(self, db: AsyncSession):
        """非复核表 wp_code 不受管辖."""
        project_id = uuid.uuid4()
        blocked, reason = await check_sequential_gate(db, project_id, "B50")
        assert blocked is False
        assert reason is None

    @pytest.mark.asyncio
    async def test_a23_blocked_when_a22_not_signed(self, db: AsyncSession):
        """A23 需要 A22 已签字."""
        project_id = uuid.uuid4()
        blocked, reason = await check_sequential_gate(db, project_id, "A23")
        assert blocked is True
        assert reason == "需先完成 A22 复核并签字"

    @pytest.mark.asyncio
    async def test_a25_2_requires_a24_2_signed(self, db: AsyncSession):
        """A25-2 需要 A24-2-sign pass."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()

        # A24-1-sign pass (wrong variant)
        await db.execute(
            sa.text(
                """
                INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, created_at, updated_at)
                VALUES (:id, :pid, :wp_id, 'A24-1-sign', 'pass', '2026-01-01', '2026-01-01')
                """
            ),
            {"id": str(uuid.uuid4()), "pid": str(project_id), "wp_id": str(wp_id)},
        )
        await db.flush()

        blocked, reason = await check_sequential_gate(db, project_id, "A25-2")
        assert blocked is True
        assert reason == "需先完成 A24-2 复核并签字"


# ---------------------------------------------------------------------------
# check_sign_lock tests
# ---------------------------------------------------------------------------


class TestCheckSignLock:
    @pytest.mark.asyncio
    async def test_not_locked_when_no_sign_record(self, db: AsyncSession):
        """无 -sign 记录时返回 not locked."""
        project_id = uuid.uuid4()
        locked, signed_by, signed_at = await check_sign_lock(db, project_id, "A21")
        assert locked is False
        assert signed_by is None
        assert signed_at is None

    @pytest.mark.asyncio
    async def test_not_locked_when_sign_rejected(self, db: AsyncSession):
        """有 -sign 记录但 conclusion='reject' → 不算锁定."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()

        await db.execute(
            sa.text(
                """
                INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, created_at, updated_at)
                VALUES (:id, :pid, :wp_id, 'A21-sign', 'reject', '2026-01-01', '2026-01-01')
                """
            ),
            {"id": str(uuid.uuid4()), "pid": str(project_id), "wp_id": str(wp_id)},
        )
        await db.flush()

        locked, signed_by, signed_at = await check_sign_lock(db, project_id, "A21")
        assert locked is False
        assert signed_by is None
        assert signed_at is None

    @pytest.mark.asyncio
    async def test_locked_when_sign_pass_exists(self, db: AsyncSession):
        """有 -sign conclusion='pass' → 锁定."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()
        staff_id = uuid.uuid4()

        # 创建 staff 记录
        staff = StaffMember(id=staff_id, user_id=uuid.uuid4(), name="张三")
        db.add(staff)
        await db.flush()

        import json
        remark = json.dumps({"signer_id": str(staff_id)})

        await db.execute(
            sa.text(
                """
                INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, remark, created_at, updated_at)
                VALUES (:id, :pid, :wp_id, 'A21-sign', 'pass', :remark, '2026-01-01', '2026-01-15T10:30:00')
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "pid": str(project_id),
                "wp_id": str(wp_id),
                "remark": remark,
            },
        )
        await db.flush()

        locked, signed_by, signed_at = await check_sign_lock(db, project_id, "A21")
        assert locked is True
        assert signed_by == "张三"
        assert signed_at == "2026-01-15T10:30:00"

    @pytest.mark.asyncio
    async def test_signed_by_resolved_from_remark(self, db: AsyncSession):
        """signed_by 正确解析 remark JSON 中的 signer_id → staff name."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()
        staff_id = uuid.uuid4()

        staff = StaffMember(id=staff_id, user_id=uuid.uuid4(), name="李四经理")
        db.add(staff)
        await db.flush()

        import json
        remark = json.dumps({"signer_id": str(staff_id), "comment": "审核通过"})

        await db.execute(
            sa.text(
                """
                INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, remark, created_at, updated_at)
                VALUES (:id, :pid, :wp_id, 'A22-sign', 'pass', :remark, '2026-01-01', '2026-02-20T14:00:00')
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "pid": str(project_id),
                "wp_id": str(wp_id),
                "remark": remark,
            },
        )
        await db.flush()

        locked, signed_by, signed_at = await check_sign_lock(db, project_id, "A22")
        assert locked is True
        assert signed_by == "李四经理"
        assert signed_at == "2026-02-20T14:00:00"

    @pytest.mark.asyncio
    async def test_malformed_remark_still_locked(self, db: AsyncSession):
        """remark 非有效 JSON 时仍然返回 locked=True，signed_by=None."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()

        await db.execute(
            sa.text(
                """
                INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, remark, created_at, updated_at)
                VALUES (:id, :pid, :wp_id, 'A23-sign', 'pass', 'not-valid-json', '2026-01-01', '2026-03-01T09:00:00')
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "pid": str(project_id),
                "wp_id": str(wp_id),
            },
        )
        await db.flush()

        locked, signed_by, signed_at = await check_sign_lock(db, project_id, "A23")
        assert locked is True
        assert signed_by is None
        assert signed_at == "2026-03-01T09:00:00"

    @pytest.mark.asyncio
    async def test_null_remark_still_locked(self, db: AsyncSession):
        """remark 为 NULL 时仍然返回 locked=True，signed_by=None."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()

        await db.execute(
            sa.text(
                """
                INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, remark, created_at, updated_at)
                VALUES (:id, :pid, :wp_id, 'A24-sign', 'pass', NULL, '2026-01-01', '2026-04-01T16:00:00')
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "pid": str(project_id),
                "wp_id": str(wp_id),
            },
        )
        await db.flush()

        locked, signed_by, signed_at = await check_sign_lock(db, project_id, "A24")
        assert locked is True
        assert signed_by is None
        assert signed_at == "2026-04-01T16:00:00"

    @pytest.mark.asyncio
    async def test_variant_wp_code_sign_lock(self, db: AsyncSession):
        """A21-1-sign 变体 wp_code 也能正确检查."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()
        staff_id = uuid.uuid4()

        staff = StaffMember(id=staff_id, user_id=uuid.uuid4(), name="王五")
        db.add(staff)
        await db.flush()

        import json
        remark = json.dumps({"signer_id": str(staff_id)})

        await db.execute(
            sa.text(
                """
                INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, remark, created_at, updated_at)
                VALUES (:id, :pid, :wp_id, 'A21-1-sign', 'pass', :remark, '2026-01-01', '2026-05-10T08:30:00')
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "pid": str(project_id),
                "wp_id": str(wp_id),
                "remark": remark,
            },
        )
        await db.flush()

        locked, signed_by, signed_at = await check_sign_lock(db, project_id, "A21-1")
        assert locked is True
        assert signed_by == "王五"
        assert signed_at == "2026-05-10T08:30:00"

    @pytest.mark.asyncio
    async def test_signer_id_not_in_staff_returns_none_name(self, db: AsyncSession):
        """remark 中 signer_id 在 staff_members 找不到 → signed_by=None."""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()

        import json
        remark = json.dumps({"signer_id": str(uuid.uuid4())})  # non-existent staff

        await db.execute(
            sa.text(
                """
                INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, remark, created_at, updated_at)
                VALUES (:id, :pid, :wp_id, 'A25-sign', 'pass', :remark, '2026-01-01', '2026-06-01T12:00:00')
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "pid": str(project_id),
                "wp_id": str(wp_id),
                "remark": remark,
            },
        )
        await db.flush()

        locked, signed_by, signed_at = await check_sign_lock(db, project_id, "A25")
        assert locked is True
        assert signed_by is None
        assert signed_at == "2026-06-01T12:00:00"


# ---------------------------------------------------------------------------
# calc_unresolved_count tests
# ---------------------------------------------------------------------------

from app.services.review_rbac_guard import calc_unresolved_count


class TestCalcUnresolvedCount:
    @pytest.mark.asyncio
    async def test_returns_zero_when_no_responses(self, db: AsyncSession):
        """无 checklist_responses 记录时返回 0."""
        wp_id = uuid.uuid4()
        count = await calc_unresolved_count(db, wp_id)
        assert count == 0

    @pytest.mark.asyncio
    async def test_counts_conclusion_n_items(self, db: AsyncSession):
        """正确统计 conclusion='N' 的记录数."""
        wp_id = uuid.uuid4()
        project_id = uuid.uuid4()

        # 插入 3 条 conclusion='N' 的记录
        for i in range(3):
            await db.execute(
                sa.text(
                    """
                    INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, created_at, updated_at)
                    VALUES (:id, :pid, :wp_id, :item_id, 'N', '2026-01-01', '2026-01-01')
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "pid": str(project_id),
                    "wp_id": str(wp_id),
                    "item_id": f"A21-chk-{i+1}",
                },
            )
        await db.flush()

        count = await calc_unresolved_count(db, wp_id)
        assert count == 3

    @pytest.mark.asyncio
    async def test_excludes_sign_items(self, db: AsyncSession):
        """排除 item_id 以 -sign 结尾的系统项."""
        wp_id = uuid.uuid4()
        project_id = uuid.uuid4()

        # 一条普通 N 记录
        await db.execute(
            sa.text(
                """
                INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, created_at, updated_at)
                VALUES (:id, :pid, :wp_id, 'A21-chk-1', 'N', '2026-01-01', '2026-01-01')
                """
            ),
            {"id": str(uuid.uuid4()), "pid": str(project_id), "wp_id": str(wp_id)},
        )
        # -sign 系统项（应排除）
        await db.execute(
            sa.text(
                """
                INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, created_at, updated_at)
                VALUES (:id, :pid, :wp_id, 'A21-sign', 'N', '2026-01-01', '2026-01-01')
                """
            ),
            {"id": str(uuid.uuid4()), "pid": str(project_id), "wp_id": str(wp_id)},
        )
        await db.flush()

        count = await calc_unresolved_count(db, wp_id)
        assert count == 1

    @pytest.mark.asyncio
    async def test_excludes_record_items(self, db: AsyncSession):
        """排除 item_id 以 -record 结尾的系统项."""
        wp_id = uuid.uuid4()
        project_id = uuid.uuid4()

        # 一条普通 N 记录
        await db.execute(
            sa.text(
                """
                INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, created_at, updated_at)
                VALUES (:id, :pid, :wp_id, 'A21-chk-2', 'N', '2026-01-01', '2026-01-01')
                """
            ),
            {"id": str(uuid.uuid4()), "pid": str(project_id), "wp_id": str(wp_id)},
        )
        # -record 系统项（应排除）
        await db.execute(
            sa.text(
                """
                INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, created_at, updated_at)
                VALUES (:id, :pid, :wp_id, 'A21-record', 'N', '2026-01-01', '2026-01-01')
                """
            ),
            {"id": str(uuid.uuid4()), "pid": str(project_id), "wp_id": str(wp_id)},
        )
        await db.flush()

        count = await calc_unresolved_count(db, wp_id)
        assert count == 1

    @pytest.mark.asyncio
    async def test_excludes_unlock_log_items(self, db: AsyncSession):
        """排除 item_id 以 -unlock-log 结尾的系统项."""
        wp_id = uuid.uuid4()
        project_id = uuid.uuid4()

        # 一条普通 N 记录
        await db.execute(
            sa.text(
                """
                INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, created_at, updated_at)
                VALUES (:id, :pid, :wp_id, 'A21-chk-3', 'N', '2026-01-01', '2026-01-01')
                """
            ),
            {"id": str(uuid.uuid4()), "pid": str(project_id), "wp_id": str(wp_id)},
        )
        # -unlock-log 系统项（应排除）
        await db.execute(
            sa.text(
                """
                INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, created_at, updated_at)
                VALUES (:id, :pid, :wp_id, 'A21-unlock-log', 'N', '2026-01-01', '2026-01-01')
                """
            ),
            {"id": str(uuid.uuid4()), "pid": str(project_id), "wp_id": str(wp_id)},
        )
        await db.flush()

        count = await calc_unresolved_count(db, wp_id)
        assert count == 1

    @pytest.mark.asyncio
    async def test_does_not_count_y_and_na(self, db: AsyncSession):
        """conclusion='Y' 和 'NA' 的记录不计入."""
        wp_id = uuid.uuid4()
        project_id = uuid.uuid4()

        # conclusion='Y'
        await db.execute(
            sa.text(
                """
                INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, created_at, updated_at)
                VALUES (:id, :pid, :wp_id, 'A21-chk-1', 'Y', '2026-01-01', '2026-01-01')
                """
            ),
            {"id": str(uuid.uuid4()), "pid": str(project_id), "wp_id": str(wp_id)},
        )
        # conclusion='NA'
        await db.execute(
            sa.text(
                """
                INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, created_at, updated_at)
                VALUES (:id, :pid, :wp_id, 'A21-chk-2', 'NA', '2026-01-01', '2026-01-01')
                """
            ),
            {"id": str(uuid.uuid4()), "pid": str(project_id), "wp_id": str(wp_id)},
        )
        await db.flush()

        count = await calc_unresolved_count(db, wp_id)
        assert count == 0

    @pytest.mark.asyncio
    async def test_mixed_data_correct_count(self, db: AsyncSession):
        """混合数据：正确统计多种 conclusion + 系统项排除."""
        wp_id = uuid.uuid4()
        project_id = uuid.uuid4()

        items = [
            ("A21-chk-1", "N"),   # 计入
            ("A21-chk-2", "N"),   # 计入
            ("A21-chk-3", "Y"),   # 不计入
            ("A21-chk-4", "NA"),  # 不计入
            ("A21-chk-5", "N"),   # 计入
            ("A21-sign", "N"),    # 系统项，排除
            ("A21-record", "N"),  # 系统项，排除
            ("A21-unlock-log", "N"),  # 系统项，排除
        ]

        for item_id, conclusion in items:
            await db.execute(
                sa.text(
                    """
                    INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, created_at, updated_at)
                    VALUES (:id, :pid, :wp_id, :item_id, :conclusion, '2026-01-01', '2026-01-01')
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "pid": str(project_id),
                    "wp_id": str(wp_id),
                    "item_id": item_id,
                    "conclusion": conclusion,
                },
            )
        await db.flush()

        count = await calc_unresolved_count(db, wp_id)
        assert count == 3  # 只有 chk-1, chk-2, chk-5


# ---------------------------------------------------------------------------
# evaluate_guard tests
# ---------------------------------------------------------------------------

from app.services.review_rbac_guard import evaluate_guard, ReviewGuardResult


class TestEvaluateGuard:
    @pytest.mark.asyncio
    async def test_locked_state_returns_readonly(self, db: AsyncSession):
        """签字锁定时返回 readonly=True, locked=True, 并填充 signed_by/signed_at."""
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()
        staff_id = uuid.uuid4()

        # 创建 staff 用于签字人解析
        staff = StaffMember(id=staff_id, user_id=uuid.uuid4(), name="张三经理")
        db.add(staff)
        await db.flush()

        import json
        remark = json.dumps({"signer_id": str(staff_id)})

        # 插入 sign pass 记录
        await db.execute(
            sa.text(
                """
                INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, remark, created_at, updated_at)
                VALUES (:id, :pid, :wp_id, 'A21-sign', 'pass', :remark, '2026-01-01', '2026-01-15T10:30:00')
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "pid": str(project_id),
                "wp_id": str(wp_id),
                "remark": remark,
            },
        )
        await db.flush()

        result = await evaluate_guard(db, user_id, project_id, "A21", wp_id)

        assert result.readonly is True
        assert result.locked is True
        assert result.signed_by == "张三经理"
        assert result.signed_at == "2026-01-15T10:30:00"
        assert result.rbac_denied is False  # locked 状态不执行 rbac

    @pytest.mark.asyncio
    async def test_rbac_denied_returns_readonly(self, db: AsyncSession):
        """用户无匹配角色时返回 readonly=True, rbac_denied=True."""
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()
        staff_id = uuid.uuid4()

        # 创建 staff + 分配错误角色
        staff = StaffMember(id=staff_id, user_id=user_id, name="李四")
        db.add(staff)
        await db.flush()

        assignment = ProjectAssignment(
            id=uuid.uuid4(),
            project_id=project_id,
            staff_id=staff_id,
            role="manager",  # A21 需要 senior/auditor，给 manager 不匹配
        )
        db.add(assignment)
        await db.flush()

        result = await evaluate_guard(db, user_id, project_id, "A21", wp_id)

        assert result.readonly is True
        assert result.locked is False
        assert result.rbac_denied is True
        assert result.gate_reason is None

    @pytest.mark.asyncio
    async def test_gate_blocked_returns_readonly(self, db: AsyncSession):
        """前置依赖未满足时返回 readonly=True, gate_reason 非空."""
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()
        staff_id = uuid.uuid4()

        # 创建 staff + 分配正确角色（A22 需要 manager）
        staff = StaffMember(id=staff_id, user_id=user_id, name="王五")
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

        # A22 需要 A21 已签字，但此处没有 A21-sign 记录
        result = await evaluate_guard(db, user_id, project_id, "A22", wp_id)

        assert result.readonly is True
        assert result.locked is False
        assert result.rbac_denied is False
        assert result.gate_reason == "需先完成 A21 复核并签字"

    @pytest.mark.asyncio
    async def test_all_pass_returns_editable(self, db: AsyncSession):
        """所有检查通过时返回 readonly=False."""
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()
        staff_id = uuid.uuid4()

        # 创建 staff + 分配正确角色（A21 允许 senior）
        staff = StaffMember(id=staff_id, user_id=user_id, name="赵六")
        db.add(staff)
        await db.flush()

        assignment = ProjectAssignment(
            id=uuid.uuid4(),
            project_id=project_id,
            staff_id=staff_id,
            role="senior",
        )
        db.add(assignment)
        await db.flush()

        result = await evaluate_guard(db, user_id, project_id, "A21", wp_id)

        assert result.readonly is False
        assert result.locked is False
        assert result.rbac_denied is False
        assert result.gate_reason is None
        assert result.unresolved_count == 0

    @pytest.mark.asyncio
    async def test_unresolved_count_filled(self, db: AsyncSession):
        """正确填充 unresolved_count."""
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()
        staff_id = uuid.uuid4()

        # 创建 staff + 分配正确角色
        staff = StaffMember(id=staff_id, user_id=user_id, name="孙七")
        db.add(staff)
        await db.flush()

        assignment = ProjectAssignment(
            id=uuid.uuid4(),
            project_id=project_id,
            staff_id=staff_id,
            role="senior",
        )
        db.add(assignment)
        await db.flush()

        # 插入 2 条 conclusion='N' 的记录
        for i in range(2):
            await db.execute(
                sa.text(
                    """
                    INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, created_at, updated_at)
                    VALUES (:id, :pid, :wp_id, :item_id, 'N', '2026-01-01', '2026-01-01')
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "pid": str(project_id),
                    "wp_id": str(wp_id),
                    "item_id": f"A21-chk-{i+1}",
                },
            )
        await db.flush()

        result = await evaluate_guard(db, user_id, project_id, "A21", wp_id)

        assert result.readonly is False
        assert result.unresolved_count == 2
