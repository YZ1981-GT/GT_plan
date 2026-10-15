"""Phase 7（第二轮复盘 R-17 重写）：快照 / 不可变版本 / 授权，全部真调生产代码。

首版 10 例无一调用生产代码（断言 ``3+1==4``、刚赋值的变量等），``generate_snapshot`` /
``save_snapshot`` 从未被执行过。本文件用真 SQLite + 真 ORM 跑 service 主函数。
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401  注册全部模型 + SQLite JSONB 兼容
from app.models.base import Base, ProjectStatus, UserRole
from app.models.core import Project, User
from app.models.note_content_template_models import (
    NoteContentTemplate,
    NoteContentTemplateVersion,
    NoteTextBatchApplication,
)
from app.models.report_models import DisclosureNote, NoteStatus
from app.models.staff_models import ProjectAssignment, StaffMember
from app.services.note_content_template_service import can_manage_group_template, can_view_template
from app.services.note_content_template_snapshot import (
    TemplateError,
    generate_snapshot,
    get_template_detail,
    list_templates,
    list_versions,
    save_snapshot,
    snapshot_preview,
    soft_delete_template,
)

YEAR = 2025
_TABLES = [User.__table__, Project.__table__, DisclosureNote.__table__, NoteContentTemplate.__table__,
           NoteContentTemplateVersion.__table__, NoteTextBatchApplication.__table__, StaffMember.__table__,
           ProjectAssignment.__table__]


def _consolidated_only_code() -> str:
    from app.services.note_section_catalog import load_section_scope_map, section_applies_to_scope

    return sorted(c for c, s in load_section_scope_map("soe").items()
                  if not section_applies_to_scope({"scope": s}, "standalone"))[0]


@pytest_asyncio.fixture
async def env():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids = {k: uuid.uuid4() for k in ("me", "boss", "other", "P", "A", "B", "C", "basic", "cash", "period")}
    async with factory() as s:
        def project(key: str, name: str, parent: str | None = None) -> Project:
            return Project(id=ids[key], name=name, client_name=f"{name}公司", template_type="soe",
                           report_scope="standalone", status=ProjectStatus.execution,
                           parent_project_id=ids[parent] if parent else None)

        s.add_all([project("P", "集团"), project("C", "异组")])
        await s.flush()
        s.add_all([project("A", "子甲", "P"), project("B", "子乙", "P")])
        await s.flush()
        boss_auditor, boss_manager = StaffMember(name="经理甲"), StaffMember(name="经理甲（重复档案）")
        boss_auditor.user_id = boss_manager.user_id = ids["boss"]
        s.add_all([boss_auditor, boss_manager])
        await s.flush()
        s.add_all([
            # 同一用户两份人员档案：首版取「第一条委派」比对，可能拿到 auditor 而误拒
            ProjectAssignment(project_id=ids["P"], staff_id=boss_auditor.id, role="auditor"),
            ProjectAssignment(project_id=ids["P"], staff_id=boss_manager.id, role="manager"),
            DisclosureNote(id=ids["basic"], project_id=ids["A"], year=YEAR, note_section="一、1",
                           section_title="公司基本情况", text_content="<p>子甲公司成立于2001年。</p>",
                           status=NoteStatus.confirmed, sort_index=1),
            DisclosureNote(id=ids["cash"], project_id=ids["A"], year=YEAR, note_section="八、1",
                           section_title="货币资金", text_content="<p>货币资金说明</p>",
                           table_data={"rows": [{"label": "库存现金", "values": [1]}]}, sort_index=3),
            DisclosureNote(id=ids["period"], project_id=ids["A"], year=YEAR, note_section="四、会计期间",
                           section_title="会计期间", sort_index=2),
            DisclosureNote(project_id=ids["A"], year=YEAR, note_section=_consolidated_only_code(),
                           section_title="合并专属", text_content="<p>旁路长出的章节</p>", sort_index=4),
        ])
        await s.commit()
    yield {"factory": factory, "ids": ids,
           "user": lambda key: SimpleNamespace(id=ids[key], role="auditor")}
    await engine.dispose()


async def _set_text(env, key: str, html: str | None) -> None:
    async with env["factory"]() as db:
        (await db.get(DisclosureNote, env["ids"][key])).text_content = html
        await db.commit()


async def _save(env, *, who: str = "me", scope: str = "personal", name: str = "全套模板", project: str = "A",
                digest: str | None = None) -> dict:
    async with env["factory"]() as db:
        if digest is None:
            digest = (await snapshot_preview(db, env["ids"][project], YEAR, user=env["user"](who),
                                             owner_scope=scope))["snapshot_digest"]
        result = await save_snapshot(db, project_id=env["ids"][project], year=YEAR, name=name, description="说明",
                                     owner_scope=scope, snapshot_digest=digest, user=env["user"](who))
        await db.commit()
        return result


async def _rows(env, model) -> list:
    async with env["factory"]() as db:
        return list((await db.execute(sa.select(model))).scalars().all())


class TestSnapshot:
    @pytest.mark.asyncio
    async def test_full_set_built_on_server_without_tables(self, env):
        async with env["factory"]() as db:
            snap = await generate_snapshot(db, env["ids"]["A"], YEAR)
        by_code = {s["note_section"]: s for s in snap["sections_data"]}
        # 叙述 + 科目解释 + 空章全在；口径不适用的合并专属章不进模板
        assert set(by_code) == {"一、1", "四、会计期间", "八、1"}
        assert by_code["八、1"]["section_kind"] == "account_explanation"
        assert all("table_data" not in s for s in snap["sections_data"])
        assert (snap["source_project_name"], snap["template_type"], snap["report_scope"]) == (
            "子甲", "soe", "standalone")
        q = snap["quality_summary"]
        assert (q["total"], q["empty"], q["account_explanation"]) == (3, 1, 1)

    @pytest.mark.asyncio
    async def test_digest_is_deterministic_and_tracks_content(self, env):
        async with env["factory"]() as db:
            first = (await generate_snapshot(db, env["ids"]["A"], YEAR))["snapshot_digest"]
            again = (await generate_snapshot(db, env["ids"]["A"], YEAR))["snapshot_digest"]
        await _set_text(env, "basic", "<p>改过的正文</p>")
        async with env["factory"]() as db:
            changed = (await generate_snapshot(db, env["ids"]["A"], YEAR))["snapshot_digest"]
        assert first == again != changed


class TestSaveAndVersions:
    @pytest.mark.asyncio
    async def test_same_content_reused_new_content_new_immutable_version(self, env):
        v1 = await _save(env)
        assert (v1["version_no"], v1["reused"]) == (1, False)
        again = await _save(env)
        assert (again["version_id"], again["reused"]) == (v1["version_id"], True)
        await _set_text(env, "basic", "<p>第二版正文</p>")
        v2 = await _save(env)
        assert (v2["version_no"], v2["reused"], v2["template_id"]) == (2, False, v1["template_id"])
        [template] = await _rows(env, NoteContentTemplate)
        assert str(template.current_version_id) == v2["version_id"]
        old = next(v for v in await _rows(env, NoteContentTemplateVersion) if str(v.id) == v1["version_id"])
        assert old.content_hash == v1["content_hash"]
        assert {s["note_section"]: s["text_content"] for s in old.sections_data}["一、1"] == "<p>子甲公司成立于2001年。</p>"

    @pytest.mark.asyncio
    async def test_reverting_content_points_current_back_without_new_version(self, env):
        v1 = await _save(env)
        await _set_text(env, "basic", "<p>第二版正文</p>")
        await _save(env)
        await _set_text(env, "basic", "<p>子甲公司成立于2001年。</p>")
        back = await _save(env)
        assert (back["version_id"], back["reused"]) == (v1["version_id"], True)
        [template] = await _rows(env, NoteContentTemplate)
        assert str(template.current_version_id) == v1["version_id"]
        assert len(await _rows(env, NoteContentTemplateVersion)) == 2

    @pytest.mark.asyncio
    async def test_stale_digest_rejected_and_nothing_written(self, env):
        async with env["factory"]() as db:
            digest = (await snapshot_preview(db, env["ids"]["A"], YEAR, user=env["user"]("me")))["snapshot_digest"]
        await _set_text(env, "basic", "<p>预检后被改</p>")
        with pytest.raises(TemplateError) as err:
            await _save(env, digest=digest)
        assert (err.value.code, err.value.status) == ("STALE_SNAPSHOT", 409)
        assert await _rows(env, NoteContentTemplate) == []

    @pytest.mark.asyncio
    async def test_blank_name_rejected(self, env):
        with pytest.raises(TemplateError) as err:
            await _save(env, name="   ")
        assert err.value.code == "TEMPLATE_NAME_INVALID"

    @pytest.mark.asyncio
    async def test_deleted_name_can_be_reused(self, env):
        first = await _save(env)
        async with env["factory"]() as db:
            assert await soft_delete_template(db, uuid.UUID(first["template_id"]), project_id=env["ids"]["A"],
                                              user=env["user"]("me"))
            await db.commit()
        second = await _save(env)
        assert second["template_id"] != first["template_id"] and second["version_no"] == 1


class TestGroupPublish:
    @pytest.mark.asyncio
    async def test_non_manager_cannot_publish_and_nothing_written(self, env):
        with pytest.raises(TemplateError) as err:
            await _save(env, scope="group")
        assert (err.value.code, err.value.status) == ("GROUP_PUBLISH_FORBIDDEN", 403)
        assert await _rows(env, NoteContentTemplate) == []

    @pytest.mark.asyncio
    async def test_manager_on_root_publishes_to_root_visible_to_whole_group_only(self, env):
        saved = await _save(env, who="boss", scope="group")
        [template] = await _rows(env, NoteContentTemplate)
        assert (template.owner_scope, template.owner_group_project_id) == ("group", env["ids"]["P"])
        tid = uuid.UUID(saved["template_id"])
        async with env["factory"]() as db:
            for viewer, expected in (("P", True), ("A", True), ("B", True), ("C", False)):
                detail = await get_template_detail(db, tid, project_id=env["ids"][viewer], user=env["user"]("me"))
                assert (detail is not None) is expected, viewer

    @pytest.mark.asyncio
    async def test_manager_found_among_multiple_assignments(self, env):
        async with env["factory"]() as db:
            assert await can_manage_group_template(db, env["user"]("boss"), env["ids"]["P"])
            assert not await can_manage_group_template(db, env["user"]("boss"), env["ids"]["C"])


async def _template(db, *, scope: str, owner, name: str, deleted: bool = False) -> NoteContentTemplate:
    t = NoteContentTemplate(name=name, owner_scope=scope, is_deleted=deleted,
                            owner_user_id=owner if scope == "personal" else None,
                            owner_group_project_id=owner if scope == "group" else None)
    db.add(t)
    await db.flush()
    return t


class TestList:
    @pytest.mark.asyncio
    async def test_sql_filter_equals_per_row_authority(self, env):
        """R-15：列表改在 SQL 层过滤后，结果必须与逐条 ``can_view_template`` 完全一致。"""
        ids = env["ids"]
        async with env["factory"]() as db:
            matrix = [await _template(db, scope="personal", owner=ids["me"], name="我的"),
                      await _template(db, scope="personal", owner=ids["other"], name="他人的"),
                      await _template(db, scope="group", owner=ids["P"], name="本集团"),
                      await _template(db, scope="group", owner=ids["C"], name="异组"),
                      await _template(db, scope="personal", owner=ids["me"], name="我删掉的", deleted=True)]
            await db.commit()
            for who in ("me", "other"):
                for viewer in ("A", "B", "C", "P"):
                    user, pid = env["user"](who), ids[viewer]
                    listed = {i["id"] for i in (await list_templates(db, project_id=pid, user=user))["items"]}
                    expected = {str(t.id) for t in matrix if await can_view_template(db, user, t, viewer_project_id=pid)}
                    assert listed == expected, (who, viewer)
            mine_in_a = {i["name"] for i in (await list_templates(db, project_id=ids["A"], user=env["user"]("me")))["items"]}
            assert mine_in_a == {"我的", "本集团"}

    @pytest.mark.asyncio
    async def test_paginated_with_version_metadata_but_no_content(self, env):
        for n in ("模板一", "模板二", "模板三"):
            await _save(env, name=n)
        async with env["factory"]() as db:
            page = await list_templates(db, project_id=env["ids"]["A"], user=env["user"]("me"), limit=2)
            versions = await list_versions(db, uuid.UUID(page["items"][0]["id"]), project_id=env["ids"]["A"],
                                           user=env["user"]("me"))
        assert (page["total"], len(page["items"])) == (3, 2)
        meta = page["items"][0]["current_version"]
        assert (meta["version_no"], meta["source_project_name"], meta["quality_summary"]["total"]) == (1, "子甲", 3)
        assert "sections_data" not in meta and [v["version_no"] for v in versions] == [1]


class TestDelete:
    @pytest.mark.asyncio
    async def test_owner_rules_and_history_preserved(self, env):
        ids = env["ids"]
        mine = await _save(env, name="个人模板")
        group = await _save(env, who="boss", scope="group", name="集团模板")
        async with env["factory"]() as db:
            db.add(NoteTextBatchApplication(
                source_kind="content_template", template_version_id=uuid.UUID(group["version_id"]),
                target_project_id=ids["B"], target_year=YEAR, mutation_id="m-hist", request_fingerprint="a" * 64,
                preview_digest="b" * 64, applied_count=1))
            await db.commit()
            # 他人看不到我的个人模板 ⇒ 当作不存在；能看到集团模板但不是经理 ⇒ 403
            assert not await soft_delete_template(db, uuid.UUID(mine["template_id"]), project_id=ids["A"],
                                                  user=env["user"]("other"))
            with pytest.raises(TemplateError) as err:
                await soft_delete_template(db, uuid.UUID(group["template_id"]), project_id=ids["B"],
                                           user=env["user"]("me"))
            assert (err.value.code, err.value.status) == ("TEMPLATE_DELETE_FORBIDDEN", 403)
            assert await soft_delete_template(db, uuid.UUID(group["template_id"]), project_id=ids["A"],
                                              user=env["user"]("boss"))
            await db.commit()
            listed = {i["id"] for i in (await list_templates(db, project_id=ids["A"], user=env["user"]("boss")))["items"]}
        assert group["template_id"] not in listed
        assert {str(v.id) for v in await _rows(env, NoteContentTemplateVersion)} >= {group["version_id"]}
        [application] = await _rows(env, NoteTextBatchApplication)
        assert str(application.template_version_id) == group["version_id"]


class TestSaverNameAndAppliedVersion:
    """AC-8.2 版本元数据带保存人姓名；AC-8.4 列表告诉本项目（本年度）最近引用的是哪一版——新版本只提示、不自动覆盖。"""

    @pytest.mark.asyncio
    async def test_saver_name_resolved_at_read_time_staff_first_then_username(self, env):
        ids, me = env["ids"], env["user"]("me")
        mine = await _save(env, name="我的")
        group = await _save(env, who="boss", scope="group", name="集团")

        async def read() -> tuple[dict, list, dict]:
            async with env["factory"]() as db:
                listed = {i["name"]: i for i in (await list_templates(db, project_id=ids["A"], user=me))["items"]}
                versions = await list_versions(db, uuid.UUID(group["template_id"]), project_id=ids["A"], user=me)
                detail = await get_template_detail(db, uuid.UUID(mine["template_id"]), project_id=ids["A"], user=me)
            return listed, versions, detail

        listed, versions, detail = await read()
        # 经理甲有两份人员档案：确定性取一份（MIN(name)），且不能因联表而把版本行翻倍
        assert listed["集团"]["current_version"]["created_by_name"] == "经理甲"
        assert [v["created_by_name"] for v in versions] == ["经理甲"]
        # 既无人员档案也无用户行（用户被删后 created_by 置空同此）⇒ 不编造姓名
        assert listed["我的"]["current_version"]["created_by_name"] is None

        async with env["factory"]() as db:
            db.add(User(id=ids["me"], username="me_login", email="me@example.com", hashed_password="x",
                        role=UserRole.auditor))
            await db.commit()
        listed, _, detail = await read()
        assert listed["我的"]["current_version"]["created_by_name"] == "me_login"  # 无人员档案 ⇒ 回退登录名
        assert detail["current_version"]["created_by_name"] == "me_login"

    @pytest.mark.asyncio
    async def test_last_applied_version_scoped_to_project_year_and_never_auto_overwritten(self, env):
        from datetime import datetime

        ids = env["ids"]
        v1 = await _save(env, who="boss", scope="group", name="集团")
        b_copy = "<p>子乙引用 v1 后的本地副本</p>"
        async with env["factory"]() as db:
            db.add(DisclosureNote(project_id=ids["B"], year=YEAR, note_section="一、1", section_title="公司基本情况",
                                  text_content=b_copy, sort_index=1))
            db.add(NoteTextBatchApplication(
                source_kind="content_template", template_version_id=uuid.UUID(v1["version_id"]),
                target_project_id=ids["B"], target_year=YEAR, mutation_id="m-v1", request_fingerprint="a" * 64,
                preview_digest="b" * 64, applied_count=1, applied_at=datetime(2026, 10, 1, 9, 0, 0)))
            await db.commit()
        await _set_text(env, "basic", "<p>子甲公司 2025 年完成改制。</p>")
        v2 = await _save(env, who="boss", scope="group", name="集团")
        assert (v2["template_id"], v2["version_no"]) == (v1["template_id"], 2)

        async def item(project: str, year: int | None = YEAR) -> dict:
            async with env["factory"]() as db:
                page = await list_templates(db, project_id=ids[project], user=env["user"]("boss"), year=year)
            return {i["id"]: i for i in page["items"]}[v1["template_id"]]

        b = await item("B")
        assert b["current_version"]["version_no"] == 2
        assert (b["last_applied"]["version_id"], b["last_applied"]["version_no"]) == (v1["version_id"], 1)
        assert (await item("A"))["last_applied"] is None              # 从未引用的项目不提示
        assert (await item("B", YEAR + 1))["last_applied"] is None    # 别的年度不串
        assert (await item("B", None))["last_applied"]["version_no"] == 1  # 不传年度 ⇒ 本项目任一年度
        # 发布新版本不改已引用项目的本地副本（只提示，用户重新预览确认后才变）
        [b_note] = [n for n in await _rows(env, DisclosureNote) if n.project_id == ids["B"]]
        assert b_note.text_content == b_copy

        # 「最近一次」按引用时间：先引 v2、后又刻意引回 v1 ⇒ 仍提示与当前版本不同
        async with env["factory"]() as db:
            db.add(NoteTextBatchApplication(
                source_kind="content_template", template_version_id=uuid.UUID(v2["version_id"]),
                target_project_id=ids["B"], target_year=YEAR, mutation_id="m-v2", request_fingerprint="c" * 64,
                preview_digest="d" * 64, applied_count=1, applied_at=datetime(2026, 9, 1, 9, 0, 0)))
            await db.commit()
        assert (await item("B"))["last_applied"]["version_no"] == 1
