"""合并附注明细刷新 apply service 测试。

spec: consol-note-detail-template-and-mapping Phase 4 Task 27
覆盖：全链路 apply / 手工保护 / locked 跳过 / 阻断 / stale 清除 / 穿透写入。
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.consol_note_data_models import ConsolNoteData
from app.models.consol_note_mapping_models import (
    ConsolNoteDetailTemplate,
    ConsolNoteDetailTemplateVersion,
    ConsolNoteMappingBinding,
    ConsolNoteMappingRule,
    ConsolNoteTemplateBinding,
)
from app.models.core import Project, User
from app.models.report_models import DisclosureNote
from app.services.consol_note_detail_apply_service import ApplyError, apply_detail_refresh
from app.services.consol_note_detail_source_service import compute_source_structure_hash
from app.services.consol_note_detail_template_service import bind_template_version, create_template
from app.services.consol_note_mapping_rule_service import confirm_mapping
from app.services.consol_note_section_mapping import (
    resolve_standalone_section,
    resolve_standalone_table_name,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON  # type: ignore[attr-defined]

_ENGINE = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, poolclass=StaticPool)
_SESSION = async_sessionmaker(_ENGINE, class_=AsyncSession, expire_on_commit=False)

_TABLES = [
    User.__table__, Project.__table__,
    ConsolNoteDetailTemplate.__table__, ConsolNoteDetailTemplateVersion.__table__,
    ConsolNoteTemplateBinding.__table__,
    ConsolNoteMappingRule.__table__, ConsolNoteMappingBinding.__table__,
    ConsolNoteData.__table__, DisclosureNote.__table__,
]
_SECTION = "五-66-1"  # 管理费用（R7.6 重对齐前是 五-67-1）
_YEAR = 2025


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
async def consol_project(db: AsyncSession) -> Project:
    p = Project(id=uuid4(), name="G_2025", client_name="G", company_code="G",
                ultimate_company_code="G", report_scope="consolidated",
                audit_year=_YEAR, audit_period_end=date(_YEAR, 12, 31))
    db.add(p)
    await db.flush()
    return p


@pytest_asyncio.fixture
async def child_projects(db: AsyncSession, consol_project: Project) -> list[Project]:
    """两个子公司项目。"""
    children = []
    for code, name in [("A", "甲公司"), ("B", "乙公司")]:
        p = Project(id=uuid4(), name=f"{name}_{_YEAR}", client_name=name, company_code=code,
                    parent_company_code="G", ultimate_company_code="G",
                    relation_to_parent="subsidiary", report_scope="standalone",
                    audit_year=_YEAR, audit_period_end=date(_YEAR, 12, 31))
        db.add(p)
        children.append(p)
    await db.flush()
    return children


def _source_rows_list(labels_amounts: list[tuple[str, str, str]]) -> list[list[str]]:
    """生成来源行 [[label, 本期, 上期], ...]。"""
    return [[la[0], la[1], la[2]] for la in labels_amounts]


def _tables_row(row: list) -> dict:
    """[label, v1, v2] → 单体附注 _tables 行（values 不含行名，数值按真库存 number）。"""
    label, *values = row
    return {
        "label": label,
        "values": [float(v) if str(v).strip() else None for v in values],
        "is_total": False,
        "row_type": "data",
    }


async def _seed_disclosure(db: AsyncSession, project_id: UUID, rows: list) -> None:
    """向子企业 disclosure_notes 写入真实形态的来源数据。

    单体附注里没有合并章节号：合并 ``五-66-1`` 经章节映射是单体「八、66 管理费用」，
    表格放 ``_tables``（附注编辑器显示的那张表）。旧测试两侧共用合并章节号会掩盖
    读取层从不换算章节号的缺陷。
    """
    db.add(DisclosureNote(
        project_id=project_id, year=_YEAR,
        note_section=resolve_standalone_section("soe", _SECTION),
        section_title="管理费用",
        table_data={"_tables": [{
            "name": resolve_standalone_table_name("soe", _SECTION),
            "headers": ["项目", "本期发生额", "上期发生额"],
            "rows": [_tables_row(r) for r in rows],
        }]},
        status="draft",
    ))
    await db.flush()


async def _setup_full_chain(
    db: AsyncSession, user: User, consol_project: Project, child_projects: list[Project],
    source_a: list, source_b: list, template_row_names: list[str],
    mappings_for_confirm: list[dict],
) -> dict:
    """完整搭建模板→绑定→来源→confirm 链路，返回上下文。"""
    # 1. 来源数据
    await _seed_disclosure(db, child_projects[0].id, source_a)
    await _seed_disclosure(db, child_projects[1].id, source_b)

    # 2. 模板
    rows = [{"canonical_name": n} for n in template_row_names[:-1]]
    rows.append({"canonical_name": template_row_names[-1], "row_type": "total"})
    tmpl = await create_template(
        db, template_type="soe", section_id=_SECTION, rows=rows, created_by=user.id,
    )
    vid = UUID(tmpl["latest_version"]["id"])

    # 3. 绑定
    await bind_template_version(db, project_id=consol_project.id, section_id=_SECTION,
                                template_version_id=vid, bound_by=user.id)

    # 4. 结构指纹
    hash_a = compute_source_structure_hash(_SECTION, source_a)
    hash_b = compute_source_structure_hash(_SECTION, source_b)

    # 5. confirm 映射
    entities = [
        {"node_key": "A:sub", "project_id": str(child_projects[0].id), "hash": hash_a},
        {"node_key": "B:sub", "project_id": str(child_projects[1].id), "hash": hash_b},
    ]
    # 如果两家结构相同，一次 confirm；否则分两次
    if hash_a == hash_b:
        await confirm_mapping(
            db, project_id=consol_project.id, section_id=_SECTION, year=_YEAR,
            template_version_id=vid, source_structure_hash=hash_a,
            mappings=mappings_for_confirm, entity_node_keys=entities, confirmed_by=user.id,
        )
    else:
        await confirm_mapping(
            db, project_id=consol_project.id, section_id=_SECTION, year=_YEAR,
            template_version_id=vid, source_structure_hash=hash_a,
            mappings=mappings_for_confirm, entity_node_keys=[entities[0]], confirmed_by=user.id,
        )
        await confirm_mapping(
            db, project_id=consol_project.id, section_id=_SECTION, year=_YEAR,
            template_version_id=vid, source_structure_hash=hash_b,
            mappings=mappings_for_confirm, entity_node_keys=[entities[1]], confirmed_by=user.id,
        )

    return {
        "template": tmpl, "vid": vid,
        "hash_a": hash_a, "hash_b": hash_b,
        "target_rows": tmpl["latest_version"]["rows"],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestApplyBasic:
    """全链路 apply：模板→绑定→来源→confirm→apply。"""

    @pytest.mark.asyncio
    async def test_apply_basic_sum(self, db, user, consol_project, child_projects):
        """简化版：直接手工搭 fixture 测 apply。"""
        source_a = [["工资", "100", "80"], ["办公费", "50", "40"]]
        source_b = [["工资", "200", "160"], ["办公费", "30", "20"]]
        await _seed_disclosure(db, child_projects[0].id, source_a)
        await _seed_disclosure(db, child_projects[1].id, source_b)

        tmpl = await create_template(
            db, template_type="soe", section_id=_SECTION,
            rows=[{"canonical_name": "职工薪酬"}, {"canonical_name": "办公费"}, {"canonical_name": "合计", "row_type": "total"}],
            created_by=user.id,
        )
        tr = tmpl["latest_version"]["rows"]
        vid = UUID(tmpl["latest_version"]["id"])
        await bind_template_version(db, project_id=consol_project.id, section_id=_SECTION,
                                    template_version_id=vid, bound_by=user.id)

        h = compute_source_structure_hash(_SECTION, source_a)
        await confirm_mapping(
            db, project_id=consol_project.id, section_id=_SECTION, year=_YEAR,
            template_version_id=vid, source_structure_hash=h,
            mappings=[
                {"source_label": "工资", "target_row_id": tr[0]["target_row_id"], "mapping_action": "map"},
                {"source_label": "办公费", "target_row_id": tr[1]["target_row_id"], "mapping_action": "map"},
            ],
            entity_node_keys=[
                {"node_key": "A:sub", "project_id": str(child_projects[0].id), "hash": h},
                {"node_key": "B:sub", "project_id": str(child_projects[1].id), "hash": h},
            ],
            confirmed_by=user.id,
        )

        result = await apply_detail_refresh(
            db, project_id=consol_project.id, section_id=_SECTION, year=_YEAR,
        )
        assert result["status"] == "applied"
        assert result["applied_entity_count"] == 2
        assert result["filled_count"] >= 2

        # 验证金额
        import sqlalchemy as sa
        record = (await db.execute(
            sa.select(ConsolNoteData).where(
                ConsolNoteData.project_id == consol_project.id,
                ConsolNoteData.section_id == _SECTION,
            )
        )).scalar_one()
        rows = record.data["rows"]
        assert rows[0][0] == "职工薪酬"
        assert Decimal(rows[0][1]) == Decimal("300")   # 100+200
        assert Decimal(rows[0][2]) == Decimal("240")   # 80+160
        assert rows[1][0] == "办公费"
        assert Decimal(rows[1][1]) == Decimal("80")    # 50+30
        assert Decimal(rows[1][2]) == Decimal("60")    # 40+20
        assert rows[2][0] == "合计"
        assert Decimal(rows[2][1]) == Decimal("380")   # 300+80
        assert Decimal(rows[2][2]) == Decimal("300")   # 240+60
        assert record.is_stale is False

    @pytest.mark.asyncio
    async def test_apply_writes_provenance(self, db, user, consol_project, child_projects):
        """apply 后 _detail_provenance 有内容。"""
        source = [["A费", "10", "5"]]
        await _seed_disclosure(db, child_projects[0].id, source)
        tmpl = await create_template(
            db, template_type="soe", section_id=_SECTION,
            rows=[{"canonical_name": "A费"}, {"canonical_name": "合计", "row_type": "total"}],
            created_by=user.id,
        )
        tr = tmpl["latest_version"]["rows"]
        vid = UUID(tmpl["latest_version"]["id"])
        await bind_template_version(db, project_id=consol_project.id, section_id=_SECTION,
                                    template_version_id=vid, bound_by=user.id)
        h = compute_source_structure_hash(_SECTION, source)
        await confirm_mapping(
            db, project_id=consol_project.id, section_id=_SECTION, year=_YEAR,
            template_version_id=vid, source_structure_hash=h,
            mappings=[{"source_label": "A费", "target_row_id": tr[0]["target_row_id"], "mapping_action": "map"}],
            entity_node_keys=[{"node_key": "A:sub", "project_id": str(child_projects[0].id), "hash": h}],
            confirmed_by=user.id,
        )
        await apply_detail_refresh(db, project_id=consol_project.id, section_id=_SECTION, year=_YEAR)

        import sqlalchemy as sa
        record = (await db.execute(
            sa.select(ConsolNoteData).where(ConsolNoteData.project_id == consol_project.id, ConsolNoteData.section_id == _SECTION)
        )).scalar_one()
        prov = record.data.get("_detail_provenance")
        assert isinstance(prov, list)
        assert len(prov) == 1
        assert prov[0]["entity_node_key"] == "A:sub"
        assert len(prov[0]["contributions"]) >= 1


class TestApplyProtection:
    """手工保护与 locked。"""

    @pytest.mark.asyncio
    async def test_manual_cells_preserved(self, db, user, consol_project, child_projects):
        """有 manual_cells 标记的单元格不被覆盖。"""
        source = [["A费", "100", "50"]]
        await _seed_disclosure(db, child_projects[0].id, source)
        tmpl = await create_template(
            db, template_type="soe", section_id=_SECTION,
            rows=[{"canonical_name": "A费"}, {"canonical_name": "合计", "row_type": "total"}],
            created_by=user.id,
        )
        tr = tmpl["latest_version"]["rows"]
        vid = UUID(tmpl["latest_version"]["id"])
        await bind_template_version(db, project_id=consol_project.id, section_id=_SECTION,
                                    template_version_id=vid, bound_by=user.id)
        h = compute_source_structure_hash(_SECTION, source)
        await confirm_mapping(
            db, project_id=consol_project.id, section_id=_SECTION, year=_YEAR,
            template_version_id=vid, source_structure_hash=h,
            mappings=[{"source_label": "A费", "target_row_id": tr[0]["target_row_id"], "mapping_action": "map"}],
            entity_node_keys=[{"node_key": "A:sub", "project_id": str(child_projects[0].id), "hash": h}],
            confirmed_by=user.id,
        )
        # 预插一条带 manual_cells 的数据
        db.add(ConsolNoteData(
            project_id=consol_project.id, year=_YEAR, section_id=_SECTION,
            data={"rows": [["A费", "999", "888"], ["合计", "", ""]], "manual_cells": [{"row": 0, "col": 1}]},
        ))
        await db.flush()

        result = await apply_detail_refresh(db, project_id=consol_project.id, section_id=_SECTION, year=_YEAR)
        assert result["kept_manual_count"] >= 1

    @pytest.mark.asyncio
    async def test_locked_record_skipped(self, db, user, consol_project, child_projects):
        """cell_state=locked 整节跳过。"""
        source = [["X", "10", "5"]]
        await _seed_disclosure(db, child_projects[0].id, source)
        tmpl = await create_template(
            db, template_type="soe", section_id=_SECTION,
            rows=[{"canonical_name": "X"}, {"canonical_name": "合计", "row_type": "total"}],
            created_by=user.id,
        )
        tr = tmpl["latest_version"]["rows"]
        vid = UUID(tmpl["latest_version"]["id"])
        await bind_template_version(db, project_id=consol_project.id, section_id=_SECTION,
                                    template_version_id=vid, bound_by=user.id)
        h = compute_source_structure_hash(_SECTION, source)
        await confirm_mapping(
            db, project_id=consol_project.id, section_id=_SECTION, year=_YEAR,
            template_version_id=vid, source_structure_hash=h,
            mappings=[{"source_label": "X", "target_row_id": tr[0]["target_row_id"], "mapping_action": "map"}],
            entity_node_keys=[{"node_key": "A:sub", "project_id": str(child_projects[0].id), "hash": h}],
            confirmed_by=user.id,
        )
        db.add(ConsolNoteData(
            project_id=consol_project.id, year=_YEAR, section_id=_SECTION,
            data={}, cell_state="locked",
        ))
        await db.flush()

        result = await apply_detail_refresh(db, project_id=consol_project.id, section_id=_SECTION, year=_YEAR)
        assert result["status"] == "skipped_locked"


class TestApplyBlocking:
    """阻断规则。"""

    @pytest.mark.asyncio
    async def test_no_binding_raises(self, db, consol_project):
        """该章节无模板绑定应报错。"""
        with pytest.raises(ApplyError) as exc:
            await apply_detail_refresh(db, project_id=consol_project.id, section_id=_SECTION, year=_YEAR)
        assert exc.value.code == "NO_TEMPLATE_BINDING"

    @pytest.mark.asyncio
    async def test_no_confirmed_entities_raises(self, db, user, consol_project):
        """有模板绑定但无确认企业应报错。"""
        tmpl = await create_template(
            db, template_type="soe", section_id=_SECTION,
            rows=[{"canonical_name": "X"}], created_by=user.id,
        )
        vid = UUID(tmpl["latest_version"]["id"])
        await bind_template_version(db, project_id=consol_project.id, section_id=_SECTION,
                                    template_version_id=vid, bound_by=user.id)
        with pytest.raises(ApplyError) as exc:
            await apply_detail_refresh(db, project_id=consol_project.id, section_id=_SECTION, year=_YEAR)
        assert exc.value.code == "NO_BINDINGS"


class TestApplyStale:
    """stale 联动。"""

    @pytest.mark.asyncio
    async def test_stale_cleared_after_apply(self, db, user, consol_project, child_projects):
        """apply 后 is_stale = False。"""
        source = [["Y", "77", "33"]]
        await _seed_disclosure(db, child_projects[0].id, source)
        tmpl = await create_template(
            db, template_type="soe", section_id=_SECTION,
            rows=[{"canonical_name": "Y"}, {"canonical_name": "合计", "row_type": "total"}],
            created_by=user.id,
        )
        tr = tmpl["latest_version"]["rows"]
        vid = UUID(tmpl["latest_version"]["id"])
        await bind_template_version(db, project_id=consol_project.id, section_id=_SECTION,
                                    template_version_id=vid, bound_by=user.id)
        h = compute_source_structure_hash(_SECTION, source)
        await confirm_mapping(
            db, project_id=consol_project.id, section_id=_SECTION, year=_YEAR,
            template_version_id=vid, source_structure_hash=h,
            mappings=[{"source_label": "Y", "target_row_id": tr[0]["target_row_id"], "mapping_action": "map"}],
            entity_node_keys=[{"node_key": "A:sub", "project_id": str(child_projects[0].id), "hash": h}],
            confirmed_by=user.id,
        )
        # 预插带 is_stale=True 的数据
        db.add(ConsolNoteData(
            project_id=consol_project.id, year=_YEAR, section_id=_SECTION,
            data={}, is_stale=True,
        ))
        await db.flush()

        await apply_detail_refresh(db, project_id=consol_project.id, section_id=_SECTION, year=_YEAR)

        import sqlalchemy as sa
        record = (await db.execute(
            sa.select(ConsolNoteData).where(
                ConsolNoteData.project_id == consol_project.id, ConsolNoteData.section_id == _SECTION,
            )
        )).scalar_one()
        assert record.is_stale is False


class TestApplyIgnoreAction:
    """ignore 动作的行不参与汇总。"""

    @pytest.mark.asyncio
    async def test_ignored_rows_excluded(self, db, user, consol_project, child_projects):
        source = [["A费", "100", "50"], ["杂费", "10", "5"]]
        await _seed_disclosure(db, child_projects[0].id, source)
        tmpl = await create_template(
            db, template_type="soe", section_id=_SECTION,
            rows=[{"canonical_name": "A费"}, {"canonical_name": "合计", "row_type": "total"}],
            created_by=user.id,
        )
        tr = tmpl["latest_version"]["rows"]
        vid = UUID(tmpl["latest_version"]["id"])
        await bind_template_version(db, project_id=consol_project.id, section_id=_SECTION,
                                    template_version_id=vid, bound_by=user.id)
        h = compute_source_structure_hash(_SECTION, source)
        await confirm_mapping(
            db, project_id=consol_project.id, section_id=_SECTION, year=_YEAR,
            template_version_id=vid, source_structure_hash=h,
            mappings=[
                {"source_label": "A费", "target_row_id": tr[0]["target_row_id"], "mapping_action": "map"},
                {"source_label": "杂费", "mapping_action": "ignore", "ignore_reason": "不适用"},
            ],
            entity_node_keys=[{"node_key": "A:sub", "project_id": str(child_projects[0].id), "hash": h}],
            confirmed_by=user.id,
        )

        result = await apply_detail_refresh(db, project_id=consol_project.id, section_id=_SECTION, year=_YEAR)
        assert result["status"] == "applied"
        # 合计应该只有 A费（100），不含杂费
        import sqlalchemy as sa
        record = (await db.execute(
            sa.select(ConsolNoteData).where(ConsolNoteData.project_id == consol_project.id, ConsolNoteData.section_id == _SECTION)
        )).scalar_one()
        rows = record.data["rows"]
        assert Decimal(rows[0][1]) == Decimal("100")
        assert Decimal(rows[1][1]) == Decimal("100")  # 合计 == A费


class TestApplyMergeAction:
    """map_merge：多来源行汇总到同一目标行。"""

    @pytest.mark.asyncio
    async def test_merge_sums_multiple_source_rows(self, db, user, consol_project, child_projects):
        source = [["工资", "100", "80"], ["奖金", "50", "40"]]
        await _seed_disclosure(db, child_projects[0].id, source)
        tmpl = await create_template(
            db, template_type="soe", section_id=_SECTION,
            rows=[{"canonical_name": "职工薪酬"}, {"canonical_name": "合计", "row_type": "total"}],
            created_by=user.id,
        )
        tr = tmpl["latest_version"]["rows"]
        vid = UUID(tmpl["latest_version"]["id"])
        await bind_template_version(db, project_id=consol_project.id, section_id=_SECTION,
                                    template_version_id=vid, bound_by=user.id)
        h = compute_source_structure_hash(_SECTION, source)
        await confirm_mapping(
            db, project_id=consol_project.id, section_id=_SECTION, year=_YEAR,
            template_version_id=vid, source_structure_hash=h,
            mappings=[
                {"source_label": "工资", "target_row_id": tr[0]["target_row_id"], "mapping_action": "map_merge"},
                {"source_label": "奖金", "target_row_id": tr[0]["target_row_id"], "mapping_action": "map_merge"},
            ],
            entity_node_keys=[{"node_key": "A:sub", "project_id": str(child_projects[0].id), "hash": h}],
            confirmed_by=user.id,
        )

        result = await apply_detail_refresh(db, project_id=consol_project.id, section_id=_SECTION, year=_YEAR)
        assert result["status"] == "applied"

        import sqlalchemy as sa
        record = (await db.execute(
            sa.select(ConsolNoteData).where(ConsolNoteData.project_id == consol_project.id, ConsolNoteData.section_id == _SECTION)
        )).scalar_one()
        rows = record.data["rows"]
        # 工资100 + 奖金50 = 150
        assert Decimal(rows[0][1]) == Decimal("150")
        assert Decimal(rows[0][2]) == Decimal("120")  # 80+40


class TestApplySubtotal:
    """subtotal 行只对本段 data 行求和，不含上一个小计以上的行。"""

    @pytest.mark.asyncio
    async def test_subtotal_sums_only_current_segment(self, db, user, consol_project, child_projects):
        """模板：A / B / 小计 / C / D / 合计。subtotal 只求 A+B，total 求 A+B+C+D。"""
        source = [["A", "10", "5"], ["B", "20", "10"], ["C", "30", "15"], ["D", "40", "20"]]
        await _seed_disclosure(db, child_projects[0].id, source)
        tmpl = await create_template(
            db, template_type="soe", section_id=_SECTION,
            rows=[
                {"canonical_name": "A"},
                {"canonical_name": "B"},
                {"canonical_name": "小计", "row_type": "subtotal"},
                {"canonical_name": "C"},
                {"canonical_name": "D"},
                {"canonical_name": "合计", "row_type": "total"},
            ],
            created_by=user.id,
        )
        tr = tmpl["latest_version"]["rows"]
        vid = UUID(tmpl["latest_version"]["id"])
        await bind_template_version(db, project_id=consol_project.id, section_id=_SECTION,
                                    template_version_id=vid, bound_by=user.id)
        h = compute_source_structure_hash(_SECTION, source)
        await confirm_mapping(
            db, project_id=consol_project.id, section_id=_SECTION, year=_YEAR,
            template_version_id=vid, source_structure_hash=h,
            mappings=[
                {"source_label": "A", "target_row_id": tr[0]["target_row_id"], "mapping_action": "map"},
                {"source_label": "B", "target_row_id": tr[1]["target_row_id"], "mapping_action": "map"},
                {"source_label": "C", "target_row_id": tr[3]["target_row_id"], "mapping_action": "map"},
                {"source_label": "D", "target_row_id": tr[4]["target_row_id"], "mapping_action": "map"},
            ],
            entity_node_keys=[{"node_key": "A:sub", "project_id": str(child_projects[0].id), "hash": h}],
            confirmed_by=user.id,
        )

        result = await apply_detail_refresh(db, project_id=consol_project.id, section_id=_SECTION, year=_YEAR)
        assert result["status"] == "applied"

        import sqlalchemy as sa
        record = (await db.execute(
            sa.select(ConsolNoteData).where(
                ConsolNoteData.project_id == consol_project.id, ConsolNoteData.section_id == _SECTION,
            )
        )).scalar_one()
        rows = record.data["rows"]
        # A=10, B=20, 小计=30(A+B), C=30, D=40, 合计=100(A+B+C+D)
        assert rows[0][0] == "A"
        assert Decimal(rows[0][1]) == Decimal("10")
        assert rows[1][0] == "B"
        assert Decimal(rows[1][1]) == Decimal("20")
        assert rows[2][0] == "小计"
        assert Decimal(rows[2][1]) == Decimal("30")   # subtotal = A+B
        assert rows[3][0] == "C"
        assert Decimal(rows[3][1]) == Decimal("30")
        assert rows[4][0] == "D"
        assert Decimal(rows[4][1]) == Decimal("40")
        assert rows[5][0] == "合计"
        assert Decimal(rows[5][1]) == Decimal("100")   # total = A+B+C+D
