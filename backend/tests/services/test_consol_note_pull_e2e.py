"""合并附注从子企业单体附注拉数 —— 端到端（真实形态，全程调用生产函数，不在测试里重写循环）。

链路：子企业单体附注（单体章节号「八、1」+ ``_tables`` / workpaper 投影，真库形态）→
suggest_template_for_section → create_template → bind_template_version → preview_detail_refresh →
confirm_mapping（逐组）→ apply_detail_refresh → consol_note_data。
另测：中间合并节点只汇总自己子树；预览后来源结构变化 409；子企业保存附注 → 用到它的合并章节 stale。

企业树（三码推导，夹具实测）：
  G:consol ─ G:consol_elim / G:parent（无单体项目）/ A:consol / B:subsidiary
  A:consol ─ A:consol_elim / A:parent（A本部）/ A1:subsidiary
数据叶子：A:parent、A1:subsidiary、B:subsidiary
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
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
from app.services import consol_note_stale_handler as stale_handler
from app.services.consol_note_detail_apply_service import ApplyError, apply_detail_refresh
from app.services.consol_note_detail_source_service import (
    preview_detail_refresh,
    suggest_template_for_section,
)
from app.services.consol_note_detail_template_service import bind_template_version, create_template
from app.services.consol_note_formula_service import find_table
from app.services.consol_note_mapping_rule_service import confirm_mapping

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON  # type: ignore[attr-defined]

_ENGINE = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, poolclass=StaticPool)
_SESSION = async_sessionmaker(_ENGINE, class_=AsyncSession, expire_on_commit=False)
_TABLES = [
    User.__table__, Project.__table__, DisclosureNote.__table__, ConsolNoteData.__table__,
    ConsolNoteDetailTemplate.__table__, ConsolNoteDetailTemplateVersion.__table__,
    ConsolNoteTemplateBinding.__table__, ConsolNoteMappingRule.__table__,
    ConsolNoteMappingBinding.__table__,
]
_YEAR = 2025
_SECTION = "五-1-1"  # 合并「货币资金」 ↔ 单体「八、1」子表「货币资金」


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
    u = User(id=uuid4(), username="tester", email="t@test.com", hashed_password="x", role="partner")
    db.add(u)
    await db.flush()
    return u


@pytest_asyncio.fixture
async def group(db: AsyncSession) -> dict[str, Project]:
    def _p(name: str, code: str, parent: str | None, scope: str) -> Project:
        return Project(
            id=uuid4(), name=f"{name}_{_YEAR}", client_name=name, company_code=code,
            parent_company_code=parent, ultimate_company_code="G",
            relation_to_parent="subsidiary" if parent else None, report_scope=scope,
            audit_year=_YEAR, audit_period_end=date(_YEAR, 12, 31),
        )
    projects = {
        "G": _p("G集团合并", "G", None, "consolidated"),
        "A_consol": _p("A合并", "A", "G", "consolidated"),
        "A": _p("A本部", "A", "G", "standalone"),
        "A1": _p("A1子公司", "A1", "A", "standalone"),
        "B": _p("B子公司", "B", "G", "standalone"),
    }
    db.add_all(projects.values())
    await db.flush()
    return projects


def _tables_row(label: str, end, prior, *, total: bool = False) -> dict:
    """真库「八、1」_tables 行：values 不含行名，带 _cell_meta / _cell_modes。"""
    return {
        "label": label, "values": [end, prior], "is_total": total,
        "row_type": "total" if total else "data",
        "_cell_meta": {"0": {"semantic": "closing_balance", "binding_id": f"八、1.{label}.closing_balance"},
                       "1": {"semantic": "opening_balance", "binding_id": f"八、1.{label}.opening_balance"}},
        "_cell_modes": {"0": "auto", "1": "auto"},
    }


async def _seed_cash_note(db: AsyncSession, project: Project, rows: list[dict]) -> DisclosureNote:
    """模板生成的单体附注：「八、1」两张表（货币资金 / 受限制的货币资金明细）。"""
    note = DisclosureNote(
        project_id=project.id, year=_YEAR, note_section="八、1", section_title="货币资金",
        table_data={"_tables": [
            {"name": "货币资金", "headers": ["项目", "期末余额", "期初余额"], "rows": rows},
            {"name": "受限制的货币资金明细", "headers": ["项目", "期末余额", "期初余额"],
             "rows": [_tables_row("银行承兑汇票保证金", 88.0, None)]},
        ]},
        status="draft",
    )
    db.add(note)
    await db.flush()
    return note


async def _seed_workpaper_cash_note(db: AsyncSession, project: Project) -> DisclosureNote:
    """底稿同步来的单体附注（宜宾形态）：编辑器显示 sub_table_data 投影，行名写「现金」。"""
    note = DisclosureNote(
        project_id=project.id, year=_YEAR, note_section="八、1", section_title="货币资金",
        table_data={
            "_source": "workpaper",
            "_tables": [{"name": "货币资金", "headers": ["项目", "期末余额", "期初余额"],
                         "rows": [_tables_row("库存现金", 999999.0, 999999.0)]}],  # 被投影遮住，不得读到
            "_sub_table_columns": {"货币资金": [
                {"key": "label", "flat": True, "label": "项目", "is_label": True},
                {"key": "end_amount", "label": "期末余额", "format": "amount"},
                {"key": "prior_amount", "label": "期初余额", "format": "amount"},
            ]},
            "sub_table_data": {"货币资金": [
                {"label": "现金", "end_amount": 100, "prior_amount": 50},
                {"label": "银行存款", "end_amount": 2000, "prior_amount": 1000},
                {"label": "其他货币资金", "end_amount": 500, "prior_amount": 0},
                {"label": "数字货币", "end_amount": 0, "prior_amount": 0},
                {"label": "合计", "is_total": True, "end_amount": 9999, "prior_amount": 9999},  # 来源合计故意错
            ]},
        },
        status="draft",
    )
    db.add(note)
    await db.flush()
    return note


A_ROWS = [
    _tables_row("库存现金", 376.73, 286.73),
    _tables_row("银行存款", 1000000.0, 800000.0),
    _tables_row("其他货币资金", None, None),
    _tables_row("数字货币", None, None),
    _tables_row("合计", 1000376.73, 800286.73, total=True),
    _tables_row("其中：存放在境外的款项总额", None, None),
]


async def _bind_template_from_suggestion(db: AsyncSession, user: User, consol: Project) -> dict:
    """用户在模板编辑器点「💡 从来源建议」→ 保存并绑定（来源独有的行删掉；「现金」建议里已并进「库存现金」别名）。"""
    suggestion = await suggest_template_for_section(db, project_id=consol.id, section_id=_SECTION, year=_YEAR)
    rows = []
    for r in suggestion["suggested_rows"]:
        if r["origin"] == "source":
            continue
        aliases = list(r["aliases"]) + (["现金"] if r["canonical_name"] == "库存现金" and "现金" not in r["aliases"] else [])
        rows.append({"canonical_name": r["canonical_name"], "aliases": aliases, "row_type": r["row_type"]})
    tmpl = await create_template(db, template_type="soe", section_id=_SECTION, rows=rows, created_by=user.id)
    await bind_template_version(
        db, project_id=consol.id, section_id=_SECTION,
        template_version_id=UUID(tmpl["latest_version"]["id"]), bound_by=user.id,
    )
    return suggestion


async def _confirm_all_groups(db: AsyncSession, user: User, consol: Project, preview: dict) -> None:
    """映射弹窗「确认映射」：每组按建议目标确认（与 ConsolNoteMappingDialog 同口径）。"""
    for grp in preview["groups"]:
        labels = {sr["label"] for sr in grp["source_rows"]}
        mappings = []
        for s in preview["suggestions"]:
            if s["source_label"] not in labels:
                continue
            target = s["suggested_target"]
            assert target is not None, f"「{s['source_label']}」没有建议目标"
            mappings.append({"source_label": s["source_label"], "target_row_id": target["target_row_id"],
                             "mapping_action": "map"})
        await confirm_mapping(
            db, project_id=consol.id, section_id=_SECTION, year=_YEAR,
            template_version_id=UUID(preview["template_version_id"]),
            source_structure_hash=grp["hash"], mappings=mappings,
            entity_node_keys=[{**e, "hash": grp["hash"]} for e in grp["entities"]],
            confirmed_by=user.id,
        )


async def _note_record(db: AsyncSession, consol: Project, node_key: str | None) -> ConsolNoteData:
    q = sa.select(ConsolNoteData).where(
        ConsolNoteData.project_id == consol.id, ConsolNoteData.section_id == _SECTION,
        ConsolNoteData.node_key == node_key if node_key else ConsolNoteData.node_key.is_(None),
    ).execution_options(populate_existing=True)
    return (await db.execute(q)).scalar_one()


def _amounts(row: list[str]) -> tuple[Decimal | None, Decimal | None]:
    return tuple(Decimal(v) if v not in ("", None) else None for v in row[1:3])  # type: ignore[return-value]


class TestFullChainFromStandaloneNotes:

    @pytest.mark.asyncio
    async def test_cash_section_pulled_from_children(self, db, user, group):
        """A本部（模板 _tables）+ A1（workpaper 投影、行名「现金」）→ 根节点合并「货币资金」。B 未生成附注。"""
        G = group["G"]
        await _seed_cash_note(db, group["A"], A_ROWS)
        await _seed_workpaper_cash_note(db, group["A1"])

        suggestion = await _bind_template_from_suggestion(db, user, G)
        # 建议以合并附注模板该表为骨架（顺序 / 合计行类型），来源独有的「现金」单列为 source 行
        template_labels = [r[0] for r in find_table("soe", _SECTION)["rows"]]
        skeleton = [r["canonical_name"] for r in suggestion["suggested_rows"] if r["origin"] == "template"]
        assert skeleton == [lbl.replace(" ", "") if lbl.replace(" ", "") == "合计" else lbl for lbl in template_labels]
        # 全局别名库认得「现金」= 库存现金：并进模板行别名，不单列一行（note-pull-header-formula-closure R6.3；
        # 原先单列 ⇒ 不删就建模板时合并附注出现「库存现金」「现金」两行，金额各算一半）
        assert [r["canonical_name"] for r in suggestion["suggested_rows"] if r["origin"] == "source"] == []
        assert "现金" in next(r for r in suggestion["suggested_rows"] if r["canonical_name"] == "库存现金")["aliases"]
        missing = {s["node_key"]: s for s in suggestion["entity_sources"] if s["status"] != "found"}
        assert missing["B:subsidiary"]["status"] == "missing" and "八、1" in missing["B:subsidiary"]["reason"]

        preview = await preview_detail_refresh(db, project_id=G.id, section_id=_SECTION, year=_YEAR)
        assert preview["entity_count"] == 2 and preview["missing_count"] == 1
        by_label = {s["source_label"]: s for s in preview["suggestions"]}
        assert by_label["现金"]["match_type"] == "alias"
        assert by_label["现金"]["suggested_target"]["canonical_name"] == "库存现金"
        assert by_label["合计"]["match_type"] == "exact"
        await _confirm_all_groups(db, user, G, preview)

        result = await apply_detail_refresh(
            db, project_id=G.id, section_id=_SECTION, year=_YEAR, node_key="G:consol",
            preview_entity_hashes=preview["_token_data"]["entity_hashes"],
        )
        assert result["status"] == "applied"
        assert result["applied_entity_count"] == 2
        assert result["unbound_entities"] == [] and result["skipped_entities"] == []

        record = await _note_record(db, G, "G:consol")
        rows = {r[0]: r for r in record.data["rows"]}
        assert _amounts(rows["库存现金"]) == (Decimal("476.73"), Decimal("336.73"))
        assert _amounts(rows["银行存款"]) == (Decimal("1002000.00"), Decimal("801000.00"))
        assert _amounts(rows["其他货币资金"]) == (Decimal("500.00"), Decimal("0.00"))
        assert _amounts(rows["数字货币"]) == (Decimal("0.00"), Decimal("0.00"))
        # 合计 = 本表合计行以上数据行之和，不取来源合计（A1 来源合计故意写成 9999）
        assert _amounts(rows["合计"]) == (Decimal("1002976.73"), Decimal("801336.73"))
        # 合计行之后的「其中」不进合计；两家都没填 → 保持空白，不写 0.00
        assert _amounts(rows["其中：存放在境外的款项总额"]) == (None, None)
        # 被 workpaper 投影遮住的模板 _tables（999999）不得读到
        assert "999999" not in str(record.data["rows"])
        assert record.data["headers"] == find_table("soe", _SECTION)["headers"]
        assert record.data["_last_write_source"] == "detail_mapping"
        assert record.data["_detail_entity_count"] == 2
        assert record.is_stale is False

    @pytest.mark.asyncio
    async def test_restricted_cash_is_second_table_of_same_section(self, db, user, group):
        """五-1-2「受限制的货币资金明细」与 五-1-1 同属单体「八、1」：按子表名读第二张表。"""
        from app.services.consol_note_detail_source_service import load_source_tables, resolve_section_template_type

        await _seed_cash_note(db, group["A"], A_ROWS)
        tt = await resolve_section_template_type(db, group["G"].id)
        sources = await load_source_tables(db, [group["A"].id, group["B"].id], "五-1-2", _YEAR, template_type=tt)
        assert sources[group["A"].id].table_name == "受限制的货币资金明细"
        assert sources[group["A"].id].rows == [
            {"label": "银行承兑汇票保证金", "row_type": "data", "values": [88.0, None], "_occurrence": 0, "_group": "", "_group_occurrence": 0}]
        assert sources[group["B"].id].status == "missing"


class TestMixedTemplateGroup:

    @pytest.mark.asyncio
    async def test_listed_group_reads_soe_child_by_section_title(self, db, user, group):
        """上市版合并（货币资金 = 单体「五、1」）+ 国企版子企业（货币资金在「八、1」）：按章节标题认到。

        国企集团含上市子公司 / 反之都存在（2026-08-16 裁决：底稿不做准则门控）。
        """
        from app.services.consol_note_detail_source_service import load_source_tables

        group["G"].template_type = "listed"
        await db.flush()
        await _seed_cash_note(db, group["A"], A_ROWS)
        sources = await load_source_tables(db, [group["A"].id], _SECTION, _YEAR, template_type="listed")
        st = sources[group["A"].id]
        assert st.table_name == "货币资金"
        # 上市版合并表头「期末余额 / 上年年末余额」与国企版「期末余额 / 期初余额」同位置
        assert st.rows[0] == {"label": "库存现金", "row_type": "data", "values": [376.73, 286.73], "_occurrence": 0, "_group": "", "_group_occurrence": 0}

        # 子企业保存「八、1」→ 上市版合并章节（映射到单体「五、1」）照样按标题判为受影响
        affected = await stale_handler._affected_consol_sections(db, group["A"].id, "八、1", "货币资金")
        assert affected == {}  # 还没有绑定
        await _bind_template_from_suggestion_listed(db, user, group["G"])
        await _confirm_all_groups(db, user, group["G"], await preview_detail_refresh(
            db, project_id=group["G"].id, section_id=_SECTION, year=_YEAR))
        affected = await stale_handler._affected_consol_sections(db, group["A"].id, "八、1", "货币资金")
        assert affected == {_SECTION: [group["G"].id]}


async def _bind_template_from_suggestion_listed(db: AsyncSession, user: User, consol: Project) -> None:
    suggestion = await suggest_template_for_section(db, project_id=consol.id, section_id=_SECTION, year=_YEAR)
    rows = [{"canonical_name": r["canonical_name"], "aliases": r["aliases"], "row_type": r["row_type"]}
            for r in suggestion["suggested_rows"]]
    tmpl = await create_template(db, template_type="listed", section_id=_SECTION, rows=rows, created_by=user.id)
    await bind_template_version(
        db, project_id=consol.id, section_id=_SECTION,
        template_version_id=UUID(tmpl["latest_version"]["id"]), bound_by=user.id,
    )


class TestNodeScope:

    @pytest.mark.asyncio
    async def test_mid_level_node_only_sums_its_subtree(self, db, user, group):
        """A:consol（中间合并节点）只汇总 A本部 + A1；根节点再加上 B。"""
        G = group["G"]
        await _seed_cash_note(db, group["A"], A_ROWS)
        await _seed_workpaper_cash_note(db, group["A1"])
        await _seed_cash_note(db, group["B"], [
            _tables_row("库存现金", 1000.0, 1000.0),
            _tables_row("银行存款", None, None),
            _tables_row("其他货币资金", None, None),
            _tables_row("数字货币", None, None),
            _tables_row("合计", 1000.0, 1000.0, total=True),
            _tables_row("其中：存放在境外的款项总额", None, None),
        ])
        await _bind_template_from_suggestion(db, user, G)
        preview = await preview_detail_refresh(db, project_id=G.id, section_id=_SECTION, year=_YEAR)
        assert preview["entity_count"] == 3
        await _confirm_all_groups(db, user, G, preview)

        mid = await apply_detail_refresh(db, project_id=G.id, section_id=_SECTION, year=_YEAR, node_key="A:consol")
        assert mid["applied_entity_count"] == 2 and mid["out_of_scope_count"] == 1
        root = await apply_detail_refresh(db, project_id=G.id, section_id=_SECTION, year=_YEAR, node_key="G:consol")
        assert root["applied_entity_count"] == 3

        mid_rows = {r[0]: r for r in (await _note_record(db, G, "A:consol")).data["rows"]}
        root_rows = {r[0]: r for r in (await _note_record(db, G, "G:consol")).data["rows"]}
        assert _amounts(mid_rows["库存现金"]) == (Decimal("476.73"), Decimal("336.73"))
        assert _amounts(root_rows["库存现金"]) == (Decimal("1476.73"), Decimal("1336.73"))

    @pytest.mark.asyncio
    async def test_unknown_node_is_rejected(self, db, user, group):
        G = group["G"]
        await _seed_cash_note(db, group["A"], A_ROWS)
        await _bind_template_from_suggestion(db, user, G)
        await _confirm_all_groups(db, user, G, await preview_detail_refresh(
            db, project_id=G.id, section_id=_SECTION, year=_YEAR))
        with pytest.raises(ApplyError) as exc:
            await apply_detail_refresh(db, project_id=G.id, section_id=_SECTION, year=_YEAR, node_key="X:consol")
        assert exc.value.code == "NODE_NOT_FOUND"


class TestPreviewGuard:

    @pytest.mark.asyncio
    async def test_source_structure_changed_after_preview_is_409(self, db, user, group):
        G = group["G"]
        note = await _seed_cash_note(db, group["A"], A_ROWS)
        await _bind_template_from_suggestion(db, user, G)
        preview = await preview_detail_refresh(db, project_id=G.id, section_id=_SECTION, year=_YEAR)
        await _confirm_all_groups(db, user, G, preview)

        # 预览之后子企业在单体附注里加了一行
        td = dict(note.table_data)
        tables = [dict(t) for t in td["_tables"]]
        tables[0]["rows"] = list(tables[0]["rows"]) + [_tables_row("新增明细", 1.0, 1.0)]
        note.table_data = {**td, "_tables": tables}
        await db.flush()

        with pytest.raises(ApplyError) as exc:
            await apply_detail_refresh(
                db, project_id=G.id, section_id=_SECTION, year=_YEAR, node_key="G:consol",
                preview_entity_hashes=preview["_token_data"]["entity_hashes"],
            )
        assert exc.value.status == 409 and exc.value.code == "SOURCE_CHANGED"


class TestStaleOnChildNoteSaved:

    async def _applied(self, db, user, group) -> DisclosureNote:
        G = group["G"]
        note = await _seed_cash_note(db, group["A"], A_ROWS)
        await _bind_template_from_suggestion(db, user, G)
        await _confirm_all_groups(db, user, G, await preview_detail_refresh(
            db, project_id=G.id, section_id=_SECTION, year=_YEAR))
        await apply_detail_refresh(db, project_id=G.id, section_id=_SECTION, year=_YEAR, node_key="G:consol")
        # 一个没有明细映射绑定的合并章节（公式填的），子企业改附注不该把它标 stale
        db.add(ConsolNoteData(project_id=G.id, year=_YEAR, section_id="五-67-1", node_key="G:consol",
                              data={"rows": []}, is_stale=False))
        await db.commit()
        return note

    async def _fire(self, project: Project, section_code: str | None) -> list:
        from app.services.event_bus import EventPayload
        from app.models.audit_platform_schemas import EventType

        event = EventPayload(
            event_type=EventType.NOTE_SECTION_SAVED, project_id=project.id, year=_YEAR,
            extra={"section_code": section_code, "action": "update"},
        )
        with patch("app.core.database.async_session", _SESSION), \
                patch.object(stale_handler, "_emit_consol_note_stale") as emit:
            await stale_handler._on_note_section_saved_mark_consol_stale(event)
        return emit.call_args_list

    async def _stale(self, db, project_id: UUID, section_id: str) -> bool:
        return (await db.execute(
            sa.select(ConsolNoteData.is_stale).where(
                ConsolNoteData.project_id == project_id, ConsolNoteData.section_id == section_id,
            ).execution_options(populate_existing=True)
        )).scalar_one()

    @pytest.mark.asyncio
    async def test_saving_mapped_child_section_marks_consol_stale(self, db, user, group):
        await self._applied(db, user, group)
        calls = await self._fire(group["A"], "八、1")
        assert await self._stale(db, group["G"].id, _SECTION) is True
        assert await self._stale(db, group["G"].id, "五-67-1") is False
        assert len(calls) == 1 and calls[0].args[0] == group["G"].id

    @pytest.mark.asyncio
    async def test_event_carrying_note_id_resolves_section(self, db, user, group):
        """个别发布方只带附注记录 id：按 id 查回「八、1」。"""
        note = await self._applied(db, user, group)
        await self._fire(group["A"], str(note.id))
        assert await self._stale(db, group["G"].id, _SECTION) is True

    @pytest.mark.asyncio
    async def test_unrelated_child_section_or_unbound_child_does_not_mark(self, db, user, group):
        await self._applied(db, user, group)
        assert await self._fire(group["A"], "八、66") == []   # 管理费用：没有绑定
        assert await self._fire(group["B"], "八、1") == []    # B 没参与映射
        assert await self._stale(db, group["G"].id, _SECTION) is False
