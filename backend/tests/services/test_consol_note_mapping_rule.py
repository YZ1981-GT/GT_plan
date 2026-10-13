"""合并附注映射规则 CRUD、confirm_mapping 与 stale 检测测试。

spec: consol-note-detail-template-and-mapping Phase 3 Task 21
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
    add_version,
    bind_template_version,
    create_template,
)
from app.services.consol_note_mapping_rule_service import (
    MappingRuleError,
    confirm_mapping,
    create_rule,
    deactivate_rule,
    detect_stale_bindings,
    get_active_rules,
    get_rule_versions,
    upgrade_version,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON  # type: ignore[attr-defined]

_ENGINE = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, poolclass=StaticPool)
_SESSION = async_sessionmaker(_ENGINE, class_=AsyncSession, expire_on_commit=False)
_TABLES = [
    User.__table__, Project.__table__,
    ConsolNoteDetailTemplate.__table__, ConsolNoteDetailTemplateVersion.__table__,
    ConsolNoteTemplateBinding.__table__,
    ConsolNoteMappingRule.__table__, ConsolNoteMappingBinding.__table__,
]
_HASH_A = "a" * 64
_HASH_B = "b" * 64
_SECTION = "五-67-1"


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
    p = Project(id=uuid4(), name="G_2025", client_name="G", company_code="G",
                ultimate_company_code="G", audit_year=2025, audit_period_end=date(2025, 12, 31))
    db.add(p)
    await db.flush()
    return p


@pytest_asyncio.fixture
async def template_v1(db: AsyncSession, user: User) -> dict:
    """创建一个模板并返回 {template_id, version_id, rows}。"""
    result = await create_template(
        db, template_type="soe", section_id=_SECTION,
        rows=[{"canonical_name": "职工薪酬"}, {"canonical_name": "办公费"}, {"canonical_name": "合计", "row_type": "total"}],
        created_by=user.id,
    )
    return {
        "template_id": result["id"],
        "version_id": result["latest_version"]["id"],
        "rows": result["latest_version"]["rows"],
    }


def _map(source: str, target_row_id: str, action: str = "map") -> dict:
    m = {"source_label": source, "target_row_id": target_row_id, "mapping_action": action}
    if action == "ignore":
        m["ignore_reason"] = "不适用"
    return m


# ═══════════════════════════════════════════════════════════════════════════════
# 规则 CRUD
# ═══════════════════════════════════════════════════════════════════════════════


class TestCreateRule:
    @pytest.mark.asyncio
    async def test_create_v1(self, db, user, project, template_v1):
        from uuid import UUID
        vid = UUID(template_v1["version_id"])
        trid = template_v1["rows"][0]["target_row_id"]
        result = await create_rule(
            db, project_id=project.id, section_id=_SECTION,
            template_version_id=vid, source_structure_hash=_HASH_A,
            mappings=[_map("工资", trid)], confirmed_by=user.id,
        )
        assert result["version_number"] == 1
        assert result["is_active"] is True
        assert len(result["mappings"]) == 1

    @pytest.mark.asyncio
    async def test_invalid_hash_rejected(self, db, user, project, template_v1):
        from uuid import UUID
        with pytest.raises(MappingRuleError) as exc:
            await create_rule(
                db, project_id=project.id, section_id=_SECTION,
                template_version_id=UUID(template_v1["version_id"]),
                source_structure_hash="short",
                mappings=[_map("X", "tid", "ignore")],
            )
        assert exc.value.status == 400

    @pytest.mark.asyncio
    async def test_ignore_without_reason_rejected(self, db, user, project, template_v1):
        from uuid import UUID
        with pytest.raises(MappingRuleError) as exc:
            await create_rule(
                db, project_id=project.id, section_id=_SECTION,
                template_version_id=UUID(template_v1["version_id"]),
                source_structure_hash=_HASH_A,
                mappings=[{"source_label": "X", "target_row_id": "", "mapping_action": "ignore"}],
            )
        assert exc.value.code == "MISSING_IGNORE_REASON"

    @pytest.mark.asyncio
    async def test_map_without_target_rejected(self, db, user, project, template_v1):
        from uuid import UUID
        with pytest.raises(MappingRuleError) as exc:
            await create_rule(
                db, project_id=project.id, section_id=_SECTION,
                template_version_id=UUID(template_v1["version_id"]),
                source_structure_hash=_HASH_A,
                mappings=[{"source_label": "X", "mapping_action": "map"}],
            )
        assert exc.value.code == "MISSING_TARGET"


class TestUpgradeVersion:
    @pytest.mark.asyncio
    async def test_upgrade_deactivates_old(self, db, user, project, template_v1):
        from uuid import UUID
        vid = UUID(template_v1["version_id"])
        trid = template_v1["rows"][0]["target_row_id"]
        r1 = await create_rule(
            db, project_id=project.id, section_id=_SECTION,
            template_version_id=vid, source_structure_hash=_HASH_A,
            mappings=[_map("工资", trid)], confirmed_by=user.id,
        )
        r2 = await upgrade_version(
            db, UUID(r1["id"]),
            mappings=[_map("工资", trid), _map("办公", template_v1["rows"][1]["target_row_id"])],
            confirmed_by=user.id,
        )
        assert r2["version_number"] == 2
        # 旧版已停用
        versions = await get_rule_versions(db, project_id=project.id, section_id=_SECTION)
        active = [v for v in versions if v["is_active"]]
        assert len(active) == 1
        assert active[0]["version_number"] == 2


class TestDeactivateRule:
    @pytest.mark.asyncio
    async def test_deactivate(self, db, user, project, template_v1):
        from uuid import UUID
        vid = UUID(template_v1["version_id"])
        r = await create_rule(
            db, project_id=project.id, section_id=_SECTION,
            template_version_id=vid, source_structure_hash=_HASH_A,
            mappings=[_map("X", template_v1["rows"][0]["target_row_id"])],
        )
        result = await deactivate_rule(db, UUID(r["id"]))
        assert result["deactivated"] is True
        rules = await get_active_rules(db, project_id=project.id)
        assert len(rules) == 0

    @pytest.mark.asyncio
    async def test_deactivate_nonexistent(self, db):
        with pytest.raises(MappingRuleError) as exc:
            await deactivate_rule(db, uuid4())
        assert exc.value.status == 404


# ═══════════════════════════════════════════════════════════════════════════════
# confirm_mapping
# ═══════════════════════════════════════════════════════════════════════════════


class TestConfirmMapping:
    @pytest.mark.asyncio
    async def test_confirm_creates_rule_and_bindings(self, db, user, project, template_v1):
        from uuid import UUID
        vid = UUID(template_v1["version_id"])
        trid = template_v1["rows"][0]["target_row_id"]
        entities = [
            {"node_key": "A:sub", "project_id": str(uuid4()), "hash": _HASH_A},
            {"node_key": "B:sub", "project_id": str(uuid4()), "hash": _HASH_A},
        ]
        result = await confirm_mapping(
            db, project_id=project.id, section_id=_SECTION, year=2025,
            template_version_id=vid, source_structure_hash=_HASH_A,
            mappings=[_map("工资", trid)],
            entity_node_keys=entities, confirmed_by=user.id,
        )
        assert result["action"] == "confirmed"
        assert result["bound_count"] == 2
        assert result["excluded_count"] == 0

    @pytest.mark.asyncio
    async def test_confirm_with_exclusion(self, db, user, project, template_v1):
        from uuid import UUID
        vid = UUID(template_v1["version_id"])
        trid = template_v1["rows"][0]["target_row_id"]
        entities = [
            {"node_key": "A:sub", "project_id": str(uuid4()), "hash": _HASH_A},
            {"node_key": "B:sub", "project_id": str(uuid4()), "hash": _HASH_A},
        ]
        result = await confirm_mapping(
            db, project_id=project.id, section_id=_SECTION, year=2025,
            template_version_id=vid, source_structure_hash=_HASH_A,
            mappings=[_map("工资", trid)],
            entity_node_keys=entities,
            excluded_node_keys=["B:sub"],
            confirmed_by=user.id,
        )
        assert result["bound_count"] == 1
        assert result["excluded_count"] == 1

    @pytest.mark.asyncio
    async def test_confirm_upgrades_existing_rule(self, db, user, project, template_v1):
        from uuid import UUID
        vid = UUID(template_v1["version_id"])
        trid = template_v1["rows"][0]["target_row_id"]
        entities = [{"node_key": "A:sub", "project_id": str(uuid4()), "hash": _HASH_A}]
        # 首次确认
        r1 = await confirm_mapping(
            db, project_id=project.id, section_id=_SECTION, year=2025,
            template_version_id=vid, source_structure_hash=_HASH_A,
            mappings=[_map("工资", trid)],
            entity_node_keys=entities, confirmed_by=user.id,
        )
        assert r1["version_number"] == 1
        # 二次确认——升版
        r2 = await confirm_mapping(
            db, project_id=project.id, section_id=_SECTION, year=2025,
            template_version_id=vid, source_structure_hash=_HASH_A,
            mappings=[_map("工资", trid), _map("办公", template_v1["rows"][1]["target_row_id"])],
            entity_node_keys=entities, confirmed_by=user.id,
        )
        assert r2["version_number"] == 2

    @pytest.mark.asyncio
    async def test_409_on_source_hash_conflict(self, db, user, project, template_v1):
        from uuid import UUID
        vid = UUID(template_v1["version_id"])
        trid = template_v1["rows"][0]["target_row_id"]
        entities = [{"node_key": "A:sub", "project_id": str(uuid4()), "hash": _HASH_A}]
        with pytest.raises(MappingRuleError) as exc:
            await confirm_mapping(
                db, project_id=project.id, section_id=_SECTION, year=2025,
                template_version_id=vid, source_structure_hash=_HASH_A,
                mappings=[_map("工资", trid)],
                entity_node_keys=entities, confirmed_by=user.id,
                current_entity_hashes={"A:sub": _HASH_B},  # 模拟来源已变
            )
        assert exc.value.status == 409
        assert exc.value.code == "SOURCE_STRUCTURE_CONFLICT"


# ═══════════════════════════════════════════════════════════════════════════════
# stale 检测
# ═══════════════════════════════════════════════════════════════════════════════


class TestStaleDetection:
    @pytest.mark.asyncio
    async def test_detects_stale(self, db, user, project, template_v1):
        from uuid import UUID
        vid = UUID(template_v1["version_id"])
        trid = template_v1["rows"][0]["target_row_id"]
        ep = str(uuid4())
        # 先创建确认绑定
        await confirm_mapping(
            db, project_id=project.id, section_id=_SECTION, year=2025,
            template_version_id=vid, source_structure_hash=_HASH_A,
            mappings=[_map("工资", trid)],
            entity_node_keys=[{"node_key": "A:sub", "project_id": ep, "hash": _HASH_A}],
            confirmed_by=user.id,
        )
        # 来源行名变化 → hash 变了
        stale = await detect_stale_bindings(
            db, project_id=project.id, section_id=_SECTION,
            current_hashes={"A:sub": _HASH_B},
        )
        assert len(stale) == 1
        assert stale[0]["entity_node_key"] == "A:sub"
        assert stale[0]["old_hash"] == _HASH_A
        assert stale[0]["new_hash"] == _HASH_B

    @pytest.mark.asyncio
    async def test_no_stale_when_unchanged(self, db, user, project, template_v1):
        from uuid import UUID
        vid = UUID(template_v1["version_id"])
        trid = template_v1["rows"][0]["target_row_id"]
        ep = str(uuid4())
        await confirm_mapping(
            db, project_id=project.id, section_id=_SECTION, year=2025,
            template_version_id=vid, source_structure_hash=_HASH_A,
            mappings=[_map("工资", trid)],
            entity_node_keys=[{"node_key": "A:sub", "project_id": ep, "hash": _HASH_A}],
            confirmed_by=user.id,
        )
        stale = await detect_stale_bindings(
            db, project_id=project.id, section_id=_SECTION,
            current_hashes={"A:sub": _HASH_A},
        )
        assert len(stale) == 0
