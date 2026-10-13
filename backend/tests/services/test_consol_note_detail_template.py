"""合并附注明细模板与绑定 service 测试。

spec: consol-note-detail-template-and-mapping Phase 1 Task 7
覆盖：模板 CRUD + 版本递增 + 绑定切换 + 删除引用检查 + 参数校验。
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
from app.models.core import Project, User
from app.services.consol_note_detail_template_service import (
    TemplateServiceError,
    add_version,
    bind_template_version,
    change_visibility,
    check_row_deletion_impact,
    create_template,
    get_binding,
    get_bindings,
    get_template,
    get_versions,
    list_templates,
    soft_delete_template,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON  # type: ignore[attr-defined]

_ENGINE = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    echo=False,
    poolclass=StaticPool,
)
_SESSION = async_sessionmaker(_ENGINE, class_=AsyncSession, expire_on_commit=False)

_TABLES = [
    User.__table__,
    Project.__table__,
    ConsolNoteDetailTemplate.__table__,
    ConsolNoteDetailTemplateVersion.__table__,
    ConsolNoteTemplateBinding.__table__,
    ConsolNoteMappingRule.__table__,
    ConsolNoteMappingBinding.__table__,
]


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
    u = User(id=uuid4(), username="tester", email="t@test.com", hashed_password="fakehash", role="partner")
    db.add(u)
    await db.flush()
    return u


@pytest_asyncio.fixture
async def project(db: AsyncSession) -> Project:
    p = Project(
        id=uuid4(),
        name="Test_2025",
        client_name="Test",
        company_code="T",
        ultimate_company_code="T",
        audit_year=2025,
        audit_period_end=date(2025, 12, 31),
    )
    db.add(p)
    await db.flush()
    return p


# ═══════════════════════════════════════════════════════════════════════════════
# 模板 CRUD
# ═══════════════════════════════════════════════════════════════════════════════


class TestCreateTemplate:
    @pytest.mark.asyncio
    async def test_create_with_rows(self, db, user):
        result = await create_template(
            db,
            template_type="soe",
            section_id="五-67-1",
            name="管理费用明细",
            rows=[
                {"canonical_name": "职工薪酬"},
                {"canonical_name": "办公费", "aliases": ["办公费用"]},
                {"canonical_name": "合计", "row_type": "total"},
            ],
            created_by=user.id,
        )
        assert result["template_type"] == "soe"
        assert result["section_id"] == "五-67-1"
        assert result["name"] == "管理费用明细"
        lv = result["latest_version"]
        assert lv["version_number"] == 1
        assert len(lv["rows"]) == 3
        # 自动生成 target_row_id
        for row in lv["rows"]:
            assert row["target_row_id"]
            assert len(row["target_row_id"]) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_create_auto_generates_target_row_id(self, db, user):
        result = await create_template(
            db,
            template_type="listed",
            section_id="五-65-1",
            rows=[{"canonical_name": "残疾人就业保障金"}],
            created_by=user.id,
        )
        row = result["latest_version"]["rows"][0]
        assert row["target_row_id"]
        assert row["canonical_name"] == "残疾人就业保障金"
        assert row["row_type"] == "data"
        assert row["aliases"] == []

    @pytest.mark.asyncio
    async def test_create_invalid_template_type(self, db, user):
        with pytest.raises(TemplateServiceError) as exc_info:
            await create_template(db, template_type="bad", section_id="x", created_by=user.id)
        assert exc_info.value.status == 400

    @pytest.mark.asyncio
    async def test_create_missing_section_id(self, db, user):
        with pytest.raises(TemplateServiceError) as exc_info:
            await create_template(db, template_type="soe", section_id="", created_by=user.id)
        assert exc_info.value.status == 400

    @pytest.mark.asyncio
    async def test_create_row_missing_name(self, db, user):
        with pytest.raises(TemplateServiceError) as exc_info:
            await create_template(
                db, template_type="soe", section_id="五-1-1",
                rows=[{"canonical_name": ""}],
                created_by=user.id,
            )
        assert exc_info.value.status == 400


class TestListAndGet:
    @pytest.mark.asyncio
    async def test_list_empty(self, db):
        result = await list_templates(db)
        assert result == []

    @pytest.mark.asyncio
    async def test_list_filters(self, db, user):
        await create_template(db, template_type="soe", section_id="五-67-1", rows=[{"canonical_name": "A"}], created_by=user.id)
        await create_template(db, template_type="listed", section_id="五-65-1", rows=[{"canonical_name": "B"}], created_by=user.id)

        soe_only = await list_templates(db, template_type="soe")
        assert len(soe_only) == 1
        assert soe_only[0]["template_type"] == "soe"

        all_items = await list_templates(db)
        assert len(all_items) == 2

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, db):
        result = await get_template(db, uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_get_existing(self, db, user):
        created = await create_template(db, template_type="soe", section_id="五-1-1", rows=[{"canonical_name": "现金"}], created_by=user.id)
        from uuid import UUID
        result = await get_template(db, UUID(created["id"]))
        assert result is not None
        assert result["section_id"] == "五-1-1"


class TestVersions:
    @pytest.mark.asyncio
    async def test_add_version_increments(self, db, user):
        created = await create_template(db, template_type="soe", section_id="五-1-1", rows=[{"canonical_name": "A"}], created_by=user.id)
        from uuid import UUID
        tid = UUID(created["id"])

        v2 = await add_version(db, tid, rows=[{"canonical_name": "A"}, {"canonical_name": "B"}], change_note="加了B", created_by=user.id)
        assert v2["version_number"] == 2
        assert len(v2["rows"]) == 2

        v3 = await add_version(db, tid, rows=[{"canonical_name": "A"}, {"canonical_name": "B"}, {"canonical_name": "合计", "row_type": "total"}], created_by=user.id)
        assert v3["version_number"] == 3

    @pytest.mark.asyncio
    async def test_get_versions_ordered(self, db, user):
        created = await create_template(db, template_type="soe", section_id="五-1-1", rows=[{"canonical_name": "A"}], created_by=user.id)
        from uuid import UUID
        tid = UUID(created["id"])
        await add_version(db, tid, rows=[{"canonical_name": "A"}, {"canonical_name": "B"}], created_by=user.id)
        versions = await get_versions(db, tid)
        assert len(versions) == 2
        assert versions[0]["version_number"] == 2  # 降序
        assert versions[1]["version_number"] == 1

    @pytest.mark.asyncio
    async def test_add_version_nonexistent_template(self, db, user):
        with pytest.raises(TemplateServiceError) as exc_info:
            await add_version(db, uuid4(), rows=[{"canonical_name": "X"}], created_by=user.id)
        assert exc_info.value.status == 404


class TestSoftDelete:
    @pytest.mark.asyncio
    async def test_soft_delete(self, db, user):
        created = await create_template(db, template_type="soe", section_id="五-1-1", rows=[{"canonical_name": "A"}], created_by=user.id)
        from uuid import UUID
        tid = UUID(created["id"])
        result = await soft_delete_template(db, tid)
        assert result["deleted"] is True

        # list 不再返回
        items = await list_templates(db)
        assert len(items) == 0

        # get 也不返回
        assert await get_template(db, tid) is None

    @pytest.mark.asyncio
    async def test_soft_delete_nonexistent(self, db):
        with pytest.raises(TemplateServiceError) as exc_info:
            await soft_delete_template(db, uuid4())
        assert exc_info.value.status == 404


class TestChangeVisibility:
    @pytest.mark.asyncio
    async def test_change_visibility(self, db, user):
        created = await create_template(db, template_type="soe", section_id="五-1-1", rows=[{"canonical_name": "A"}], created_by=user.id)
        from uuid import UUID
        tid = UUID(created["id"])
        result = await change_visibility(db, tid, visibility="firm")
        assert result["visibility"] == "firm"

    @pytest.mark.asyncio
    async def test_change_visibility_invalid(self, db, user):
        created = await create_template(db, template_type="soe", section_id="五-1-1", rows=[{"canonical_name": "A"}], created_by=user.id)
        from uuid import UUID
        with pytest.raises(TemplateServiceError) as exc_info:
            await change_visibility(db, UUID(created["id"]), visibility="bad")
        assert exc_info.value.status == 400


# ═══════════════════════════════════════════════════════════════════════════════
# 模板绑定
# ═══════════════════════════════════════════════════════════════════════════════


class TestBinding:
    @pytest.mark.asyncio
    async def test_bind_and_get(self, db, user, project):
        created = await create_template(db, template_type="soe", section_id="五-67-1", rows=[{"canonical_name": "A"}], created_by=user.id)
        vid = created["latest_version"]["id"]

        result = await bind_template_version(
            db, project_id=project.id, section_id="五-67-1",
            template_version_id=__import__("uuid").UUID(vid),
            bound_by=user.id,
        )
        assert result["action"] == "bound"

        binding = await get_binding(db, project.id, "五-67-1")
        assert binding is not None
        assert binding["template_version_id"] == vid
        assert binding["version_number"] == 1

    @pytest.mark.asyncio
    async def test_get_bindings_list(self, db, user, project):
        t1 = await create_template(db, template_type="soe", section_id="五-67-1", rows=[{"canonical_name": "A"}], created_by=user.id)
        t2 = await create_template(db, template_type="soe", section_id="五-68-1", rows=[{"canonical_name": "B"}], created_by=user.id)
        from uuid import UUID
        await bind_template_version(db, project_id=project.id, section_id="五-67-1", template_version_id=UUID(t1["latest_version"]["id"]), bound_by=user.id)
        await bind_template_version(db, project_id=project.id, section_id="五-68-1", template_version_id=UUID(t2["latest_version"]["id"]), bound_by=user.id)

        bindings = await get_bindings(db, project.id)
        assert len(bindings) == 2

    @pytest.mark.asyncio
    async def test_switch_version_requires_confirm(self, db, user, project):
        """切换版本时，如果有活跃映射规则，需要 confirm=True。"""
        created = await create_template(db, template_type="soe", section_id="五-67-1", rows=[{"canonical_name": "A"}], created_by=user.id)
        from uuid import UUID
        tid = UUID(created["id"])
        v1_id = UUID(created["latest_version"]["id"])

        # 先绑定 v1
        await bind_template_version(db, project_id=project.id, section_id="五-67-1", template_version_id=v1_id, bound_by=user.id)

        # 创建一条引用 v1 的映射规则
        rule = ConsolNoteMappingRule(
            project_id=project.id,
            section_id="五-67-1",
            template_version_id=v1_id,
            source_structure_hash="a" * 64,
            version_number=1,
            mappings=[],
            is_active=True,
        )
        db.add(rule)
        await db.flush()

        # 追加 v2
        v2 = await add_version(db, tid, rows=[{"canonical_name": "A"}, {"canonical_name": "B"}], created_by=user.id)
        v2_id = UUID(v2["id"])

        # 不带 confirm 应该返回 confirm_required
        result = await bind_template_version(db, project_id=project.id, section_id="五-67-1", template_version_id=v2_id, bound_by=user.id, confirm=False)
        assert result["action"] == "confirm_required"
        assert result["affected_rule_count"] == 1

        # 带 confirm=True 才生效
        result2 = await bind_template_version(db, project_id=project.id, section_id="五-67-1", template_version_id=v2_id, bound_by=user.id, confirm=True)
        assert result2["action"] == "bound"

    @pytest.mark.asyncio
    async def test_get_binding_nonexistent(self, db, project):
        result = await get_binding(db, project.id, "不存在的章节")
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# 删除行影响检测
# ═══════════════════════════════════════════════════════════════════════════════


class TestRowDeletionImpact:
    @pytest.mark.asyncio
    async def test_no_impact_when_no_rules(self, db, user):
        created = await create_template(db, template_type="soe", section_id="五-1-1", rows=[{"canonical_name": "A"}], created_by=user.id)
        from uuid import UUID
        tid = UUID(created["id"])
        target_row_id = created["latest_version"]["rows"][0]["target_row_id"]

        result = await check_row_deletion_impact(db, tid, [target_row_id])
        assert result["affected_rule_count"] == 0
        assert result["affected_entity_count"] == 0

    @pytest.mark.asyncio
    async def test_detects_affected_rules_and_entities(self, db, user, project):
        created = await create_template(db, template_type="soe", section_id="五-67-1", rows=[{"canonical_name": "职工薪酬"}, {"canonical_name": "办公费"}], created_by=user.id)
        from uuid import UUID
        tid = UUID(created["id"])
        v1_id = UUID(created["latest_version"]["id"])
        target_row_id = created["latest_version"]["rows"][0]["target_row_id"]

        # 创建映射规则引用该 target_row_id
        rule = ConsolNoteMappingRule(
            project_id=project.id,
            section_id="五-67-1",
            template_version_id=v1_id,
            source_structure_hash="b" * 64,
            version_number=1,
            mappings=[{"source_label": "工资", "target_row_id": target_row_id, "mapping_action": "map"}],
            is_active=True,
        )
        db.add(rule)
        await db.flush()

        # 创建企业绑定
        binding = ConsolNoteMappingBinding(
            project_id=project.id,
            section_id="五-67-1",
            entity_node_key="A:subsidiary",
            entity_project_id=uuid4(),
            rule_id=rule.id,
            bound_source_hash="b" * 64,
            status="confirmed",
        )
        db.add(binding)
        await db.flush()

        result = await check_row_deletion_impact(db, tid, [target_row_id])
        assert result["affected_rule_count"] == 1
        assert result["affected_entity_count"] == 1

    @pytest.mark.asyncio
    async def test_empty_target_row_ids(self, db, user):
        created = await create_template(db, template_type="soe", section_id="五-1-1", rows=[{"canonical_name": "A"}], created_by=user.id)
        from uuid import UUID
        result = await check_row_deletion_impact(db, UUID(created["id"]), [])
        assert result["affected_rule_count"] == 0
