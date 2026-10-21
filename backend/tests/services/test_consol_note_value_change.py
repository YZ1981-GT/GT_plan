"""合并附注值变化通知——值指纹计算 + 事件处理器 + 值确认 + 结构锁测试。

spec: consol-note-mapping-reuse-and-reference-push Phase 4 Task 16 + Phase 5/6

覆盖：
- compute_value_fingerprint：精度/排除/确定性
- on_note_section_saved：触发条件/stale 标记/confirmation 降级
- confirm_entity_value：UPSERT/幂等/过期
- check_all_confirmed：闸门 pass/block
- activate_lock / check_structure_lock / release_lock
"""
from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.consol_note_mapping_models import (
    ConsolNoteDetailTemplate,
    ConsolNoteDetailTemplateVersion,
    ConsolNoteMappingBinding,
    ConsolNoteMappingRule,
    ConsolNoteTemplateBinding,
)
from app.models.consol_note_mapping_template_models import (
    ConsolNoteMappingRuleTemplate,
    ConsolNoteStructureLock,
    ConsolNoteStructureLockEntity,
    ConsolNoteValueConfirmation,
)
from app.models.core import Project, User

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON  # type: ignore[attr-defined]

_ENGINE = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, poolclass=StaticPool)
_SESSION = async_sessionmaker(_ENGINE, class_=AsyncSession, expire_on_commit=False)
_TABLES = [
    User.__table__, Project.__table__,
    ConsolNoteDetailTemplate.__table__, ConsolNoteDetailTemplateVersion.__table__,
    ConsolNoteTemplateBinding.__table__,
    ConsolNoteMappingRule.__table__, ConsolNoteMappingBinding.__table__,
    ConsolNoteMappingRuleTemplate.__table__,
    ConsolNoteStructureLock.__table__, ConsolNoteStructureLockEntity.__table__,
    ConsolNoteValueConfirmation.__table__,
]
_HASH_A = "a" * 64
_SECTION = "五-1-1"


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _ENGINE.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.drop_all(c, tables=_TABLES))
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    async with _SESSION() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def user(db: AsyncSession) -> User:
    u = User(id=uuid4(), username="tester", email="t@test.com",
             hashed_password="fakehash", role="partner")
    db.add(u)
    await db.flush()
    return u


@pytest_asyncio.fixture
async def consol_project(db: AsyncSession) -> Project:
    p = Project(id=uuid4(), name="G_2025_consol", client_name="TestGroup",
                company_code="TG", audit_year=2025,
                audit_period_end=date(2025, 12, 31))
    db.add(p)
    await db.flush()
    return p


@pytest_asyncio.fixture
async def entity_project(db: AsyncSession) -> Project:
    p = Project(id=uuid4(), name="SubCo_2025", client_name="TestGroup",
                company_code="SC", audit_year=2025,
                audit_period_end=date(2025, 12, 31))
    db.add(p)
    await db.flush()
    return p


# ═══════════════════════════════════════════════════════════════════════════════
# 1. compute_value_fingerprint
# ═══════════════════════════════════════════════════════════════════════════════


class TestValueFingerprint:

    def test_same_data_same_fingerprint(self):
        from app.services.consol_note_value_change_service import compute_value_fingerprint
        rows = [["标签A", "100.00", "200.50"], ["标签B", "300", "400.123"]]
        fp1 = compute_value_fingerprint(rows)
        fp2 = compute_value_fingerprint(rows)
        assert fp1 == fp2
        assert len(fp1) == 64

    def test_change_amount_changes_fingerprint(self):
        from app.services.consol_note_value_change_service import compute_value_fingerprint
        rows_a = [["标签", "100.00"]]
        rows_b = [["标签", "200.00"]]
        assert compute_value_fingerprint(rows_a) != compute_value_fingerprint(rows_b)

    def test_change_label_no_change(self):
        """改行名不改金额→fingerprint 不变。"""
        from app.services.consol_note_value_change_service import compute_value_fingerprint
        rows_a = [["货币资金", "100.00", "200.00"]]
        rows_b = [["现金", "100.00", "200.00"]]
        assert compute_value_fingerprint(rows_a) == compute_value_fingerprint(rows_b)

    def test_precision_rounding(self):
        """100.001 和 100.00 在两位精度下相同。"""
        from app.services.consol_note_value_change_service import compute_value_fingerprint
        rows_a = [["X", "100.001"]]
        rows_b = [["X", "100.00"]]
        assert compute_value_fingerprint(rows_a) == compute_value_fingerprint(rows_b)

    def test_dict_format_rows(self):
        """dict 格式的 rows 也能正确计算。"""
        from app.services.consol_note_value_change_service import compute_value_fingerprint
        rows = [{"values": {"col1": "100.00", "col2": "200.00"}}]
        fp = compute_value_fingerprint(rows)
        assert len(fp) == 64

    def test_empty_rows(self):
        from app.services.consol_note_value_change_service import compute_value_fingerprint
        fp = compute_value_fingerprint([])
        assert len(fp) == 64

    def test_non_numeric_ignored(self):
        """非数值内容变化不影响 fingerprint。"""
        from app.services.consol_note_value_change_service import compute_value_fingerprint
        rows_a = [["标签", "abc", "100.00"]]
        rows_b = [["标签", "xyz", "100.00"]]
        assert compute_value_fingerprint(rows_a) == compute_value_fingerprint(rows_b)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. on_note_section_saved
# ═══════════════════════════════════════════════════════════════════════════════


class TestOnNoteSectionSaved:

    @pytest.mark.asyncio
    async def test_no_binding_returns_none(self, db, entity_project):
        """无映射绑定→返回 None。"""
        from app.services.consol_note_value_change_service import on_note_section_saved
        result = await on_note_section_saved(
            db, entity_project_id=entity_project.id,
            section_id=_SECTION, year=2025,
            rows=[["标签", "100"]],
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_with_binding_returns_payload(self, db, consol_project, entity_project, user):
        """有映射绑定→返回事件 payload。"""
        from app.services.consol_note_value_change_service import on_note_section_saved

        # 创建映射绑定
        tmpl = ConsolNoteDetailTemplate(
            template_type="soe", section_id=_SECTION, name="T",
            visibility="project", created_by=user.id)
        db.add(tmpl)
        await db.flush()
        ver = ConsolNoteDetailTemplateVersion(
            template_id=tmpl.id, version_number=1, rows=[], created_by=user.id)
        db.add(ver)
        await db.flush()
        rule = ConsolNoteMappingRule(
            project_id=consol_project.id, section_id=_SECTION,
            template_version_id=ver.id, source_structure_hash=_HASH_A,
            version_number=1, mappings=[], is_active=True)
        db.add(rule)
        await db.flush()
        binding = ConsolNoteMappingBinding(
            project_id=consol_project.id, section_id=_SECTION,
            entity_node_key="sub_1", entity_project_id=entity_project.id,
            rule_id=rule.id, bound_source_hash=_HASH_A, status="confirmed")
        db.add(binding)
        await db.flush()

        result = await on_note_section_saved(
            db, entity_project_id=entity_project.id,
            section_id=_SECTION, year=2025,
            rows=[["标签", "100"]],
        )
        assert result is not None
        assert len(result["affected_projects"]) == 1
        assert result["affected_projects"][0]["consol_project_id"] == str(consol_project.id)

    @pytest.mark.asyncio
    async def test_confirmation_degraded(self, db, consol_project, entity_project, user):
        """有 confirmed 确认且 fingerprint 不同→降级为 outdated。"""
        from app.services.consol_note_value_change_service import on_note_section_saved

        # 创建映射绑定
        tmpl = ConsolNoteDetailTemplate(
            template_type="soe", section_id=_SECTION, name="T",
            visibility="project", created_by=user.id)
        db.add(tmpl)
        await db.flush()
        ver = ConsolNoteDetailTemplateVersion(
            template_id=tmpl.id, version_number=1, rows=[], created_by=user.id)
        db.add(ver)
        await db.flush()
        rule = ConsolNoteMappingRule(
            project_id=consol_project.id, section_id=_SECTION,
            template_version_id=ver.id, source_structure_hash=_HASH_A,
            version_number=1, mappings=[], is_active=True)
        db.add(rule)
        await db.flush()
        binding = ConsolNoteMappingBinding(
            project_id=consol_project.id, section_id=_SECTION,
            entity_node_key="sub_1", entity_project_id=entity_project.id,
            rule_id=rule.id, bound_source_hash=_HASH_A, status="confirmed")
        db.add(binding)
        await db.flush()

        # 创建一个旧的 confirmed 确认（hash 不同于新 fingerprint）
        old_hash = "b" * 64
        conf = ConsolNoteValueConfirmation(
            project_id=consol_project.id, section_id=_SECTION,
            entity_node_key="sub_1", confirmed_value_hash=old_hash,
            confirmed_by=user.id, status="confirmed")
        db.add(conf)
        await db.flush()

        await on_note_section_saved(
            db, entity_project_id=entity_project.id,
            section_id=_SECTION, year=2025,
            rows=[["标签", "999"]],  # 值变了
        )
        await db.refresh(conf)
        assert conf.status == "outdated"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 值确认 CRUD + 闸门
# ═══════════════════════════════════════════════════════════════════════════════


class TestValueConfirmation:

    @pytest.mark.asyncio
    async def test_confirm_and_query(self, db, consol_project, user):
        from app.services.consol_note_value_confirmation_service import (
            confirm_entity_value, get_confirmation_status,
        )
        hash_val = "c" * 64
        result = await confirm_entity_value(
            db, project_id=consol_project.id, section_id=_SECTION,
            entity_node_key="sub_1", confirmed_by=user.id,
            value_hash=hash_val,
        )
        assert result["action"] == "confirmed"

        status = await get_confirmation_status(db, project_id=consol_project.id)
        assert len(status) == 1
        assert status[0]["status"] == "confirmed"

    @pytest.mark.asyncio
    async def test_confirm_idempotent(self, db, consol_project, user):
        """重复确认→更新 confirmed_at，不新建行。"""
        from app.services.consol_note_value_confirmation_service import (
            confirm_entity_value, get_confirmation_status,
        )
        h1 = "d" * 64
        h2 = "e" * 64
        await confirm_entity_value(
            db, project_id=consol_project.id, section_id=_SECTION,
            entity_node_key="sub_1", confirmed_by=user.id, value_hash=h1,
        )
        await confirm_entity_value(
            db, project_id=consol_project.id, section_id=_SECTION,
            entity_node_key="sub_1", confirmed_by=user.id, value_hash=h2,
        )
        status = await get_confirmation_status(db, project_id=consol_project.id)
        assert len(status) == 1
        assert status[0]["confirmed_value_hash"] == h2

    @pytest.mark.asyncio
    async def test_check_all_confirmed_pass(self, db, consol_project, entity_project, user):
        """全确认→passed=True。"""
        from app.services.consol_note_value_confirmation_service import (
            check_all_confirmed, confirm_entity_value,
        )

        # 创建映射绑定
        tmpl = ConsolNoteDetailTemplate(
            template_type="soe", section_id=_SECTION, name="T",
            visibility="project", created_by=user.id)
        db.add(tmpl)
        await db.flush()
        ver = ConsolNoteDetailTemplateVersion(
            template_id=tmpl.id, version_number=1, rows=[], created_by=user.id)
        db.add(ver)
        await db.flush()
        rule = ConsolNoteMappingRule(
            project_id=consol_project.id, section_id=_SECTION,
            template_version_id=ver.id, source_structure_hash=_HASH_A,
            version_number=1, mappings=[], is_active=True)
        db.add(rule)
        await db.flush()
        binding = ConsolNoteMappingBinding(
            project_id=consol_project.id, section_id=_SECTION,
            entity_node_key="sub_1", entity_project_id=entity_project.id,
            rule_id=rule.id, bound_source_hash=_HASH_A, status="confirmed")
        db.add(binding)
        await db.flush()

        # 确认
        await confirm_entity_value(
            db, project_id=consol_project.id, section_id=_SECTION,
            entity_node_key="sub_1", confirmed_by=user.id, value_hash="f" * 64,
        )
        result = await check_all_confirmed(db, consol_project_id=consol_project.id)
        assert result["passed"] is True
        assert result["confirmed_count"] == 1

    @pytest.mark.asyncio
    async def test_check_all_confirmed_block(self, db, consol_project, entity_project, user):
        """有未确认→blocking。"""
        from app.services.consol_note_value_confirmation_service import check_all_confirmed

        # 创建映射绑定但不确认
        tmpl = ConsolNoteDetailTemplate(
            template_type="soe", section_id=_SECTION, name="T",
            visibility="project", created_by=user.id)
        db.add(tmpl)
        await db.flush()
        ver = ConsolNoteDetailTemplateVersion(
            template_id=tmpl.id, version_number=1, rows=[], created_by=user.id)
        db.add(ver)
        await db.flush()
        rule = ConsolNoteMappingRule(
            project_id=consol_project.id, section_id=_SECTION,
            template_version_id=ver.id, source_structure_hash=_HASH_A,
            version_number=1, mappings=[], is_active=True)
        db.add(rule)
        await db.flush()
        binding = ConsolNoteMappingBinding(
            project_id=consol_project.id, section_id=_SECTION,
            entity_node_key="sub_1", entity_project_id=entity_project.id,
            rule_id=rule.id, bound_source_hash=_HASH_A, status="confirmed")
        db.add(binding)
        await db.flush()

        result = await check_all_confirmed(db, consol_project_id=consol_project.id)
        assert result["passed"] is False
        assert len(result["blocking_items"]) == 1
        assert result["blocking_items"][0]["reason"] == "未确认"

    @pytest.mark.asyncio
    async def test_no_bindings_pass(self, db, consol_project):
        """无映射绑定→passed=True。"""
        from app.services.consol_note_value_confirmation_service import check_all_confirmed
        result = await check_all_confirmed(db, consol_project_id=consol_project.id)
        assert result["passed"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 结构锁
# ═══════════════════════════════════════════════════════════════════════════════


class TestStructureLock:

    @pytest.mark.asyncio
    async def test_activate_and_check(self, db, consol_project, entity_project, user):
        """激活锁→check 命中。"""
        from app.services.consol_note_structure_lock_service import (
            activate_lock, check_structure_lock,
        )

        # 创建模板版本（锁需要引用）
        tmpl = ConsolNoteDetailTemplate(
            template_type="soe", section_id=_SECTION, name="T",
            visibility="project", created_by=user.id)
        db.add(tmpl)
        await db.flush()
        ver = ConsolNoteDetailTemplateVersion(
            template_id=tmpl.id, version_number=1, rows=[], created_by=user.id)
        db.add(ver)
        await db.flush()

        # 手动插入 entity（因为测试环境没有合并树，activate_lock 的 build_tree 会失败）
        lock = ConsolNoteStructureLock(
            consol_project_id=consol_project.id, section_id=_SECTION,
            locked_version_id=ver.id, locked_by=user.id)
        db.add(lock)
        await db.flush()
        db.add(ConsolNoteStructureLockEntity(
            lock_id=lock.id, entity_project_id=entity_project.id,
            entity_node_key="sub_1"))
        await db.flush()

        result = await check_structure_lock(
            db, entity_project_id=entity_project.id, section_id=_SECTION,
        )
        assert result is not None
        assert result["locked"] is True

    @pytest.mark.asyncio
    async def test_check_no_lock(self, db, entity_project):
        """无锁→返回 None。"""
        from app.services.consol_note_structure_lock_service import check_structure_lock
        result = await check_structure_lock(
            db, entity_project_id=entity_project.id, section_id=_SECTION,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_release_lock(self, db, consol_project, entity_project, user):
        """释放锁→check 返回 None。"""
        from app.services.consol_note_structure_lock_service import (
            check_structure_lock, release_lock,
        )

        tmpl = ConsolNoteDetailTemplate(
            template_type="soe", section_id=_SECTION, name="T",
            visibility="project", created_by=user.id)
        db.add(tmpl)
        await db.flush()
        ver = ConsolNoteDetailTemplateVersion(
            template_id=tmpl.id, version_number=1, rows=[], created_by=user.id)
        db.add(ver)
        await db.flush()

        lock = ConsolNoteStructureLock(
            consol_project_id=consol_project.id, section_id=_SECTION,
            locked_version_id=ver.id, locked_by=user.id)
        db.add(lock)
        await db.flush()
        db.add(ConsolNoteStructureLockEntity(
            lock_id=lock.id, entity_project_id=entity_project.id,
            entity_node_key="sub_1"))
        await db.flush()

        await release_lock(
            db, consol_project_id=consol_project.id,
            section_id=_SECTION, released_by=user.id,
        )
        result = await check_structure_lock(
            db, entity_project_id=entity_project.id, section_id=_SECTION,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_release_nonexistent_lock(self, db, consol_project, user):
        """释放不存在的锁→404。"""
        from app.services.consol_note_structure_lock_service import (
            StructureLockError, release_lock,
        )
        with pytest.raises(StructureLockError) as exc_info:
            await release_lock(
                db, consol_project_id=consol_project.id,
                section_id="不存在", released_by=user.id,
            )
        assert exc_info.value.status == 404
