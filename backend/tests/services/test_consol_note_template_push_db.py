"""合并附注「📤 下推模板」写入子企业附注（spec note-pull-header-formula-closure R6.1 任务 21）。SQLite 内存库 + 真 ORM。

原实现导入不存在的 ``app.models.disclosure_note_models`` ⇒ 每家子企业都失败；结构锁模型导错模块被 ImportError 吞掉；
推送日志 SQL 的 ``:f::jsonb`` 不是绑定参数 ⇒ PG 语法错、端点必 500 —— 从未写成过。只修导入会让它直接写子企业附注，
而原写法写 ``_tables[0]``（选错表）、首次下推把已有行全当用户行追加（重复行）、新建一列「项目」的残缺章节，故写入规则一并改。

判据：①首次下推按行名 / 别名认领已有行：行名、数值、位置不动、不重复，缺的模板行补空值（按列宽）②重推幂等、子企业取消的
可选行保持取消、模板删掉的行只去标记 ③按映射子表名选表（不是第 1 张）④没附注 / 本期无此情形 / 底稿同步 / 对不上的表跳过不写
⑤附注编辑门禁拒绝（无权限 / 合并锁定）记跳过 ⑥一家写失败只回滚这一家 ⑦结构锁只关联成功的企业、推送日志落库
⑧模板版本前置校验 ⑨端点：合并锁 423、未绑定 / 版本不符 400。
"""
from __future__ import annotations

import copy
import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401  注册全部模型 + SQLite JSONB 兼容
from app.models.base import Base, ProjectStatus, UserRole
from app.models.consol_note_mapping_models import (
    ConsolNoteDetailTemplate,
    ConsolNoteDetailTemplateVersion,
    ConsolNoteTemplateBinding,
)
from app.models.consolidation_models import ConsolNoteTemplatePushLog
from app.models.core import Project, User
from app.models.report_models import ContentType, DisclosureNote
from app.services import consol_note_template_push_service as push_mod
from app.services.consol_note_template_push_service import PushTemplateError, push_template_to_subsidiaries

YEAR = 2025
CASH = "五-1-1"      # 国企合并 五-1-1 → 单体 八、1「货币资金」
AGING = "五-5-1"     # 国企合并 五-5-1 → 单体 八、5「（1）按账龄披露应收账款」
R_CASH, R_BANK, R_OTHER, R_TOTAL = (str(uuid.uuid4()) for _ in range(4))
CASH_ROWS = [
    {"target_row_id": R_CASH, "canonical_name": "库存现金", "aliases": ["现金"], "row_type": "data", "category": "required"},
    {"target_row_id": R_BANK, "canonical_name": "银行存款", "aliases": [], "row_type": "data", "category": "required"},
    {"target_row_id": R_OTHER, "canonical_name": "其他货币资金", "aliases": [], "row_type": "data", "category": "optional"},
    {"target_row_id": str(uuid.uuid4()), "canonical_name": "[动态行区]", "aliases": [], "row_type": "data",
     "category": "dynamic_zone"},
    {"target_row_id": R_TOTAL, "canonical_name": "合计", "aliases": [], "row_type": "total", "category": "required"},
]


def _row(label, values, **kw):
    return {"label": label, "values": values, **kw}


def _cash_table(*rows):
    return {"name": "货币资金", "headers": ["项目", "期末余额", "期初余额"], "rows": list(rows)}


CASH_TABLE = _cash_table(
    _row("现金", [100.0, 90.0]),
    _row("银行存款", [200.0, 180.0]),
    _row("合  计", [300.0, 270.0], row_type="total"),
    _row("其中：存放在境外的款项总额", [None, None]),
)
AGING_TABLE = {"name": "（1）按账龄披露应收账款", "headers": ["账龄", "期末数", "期初数"],
               "rows": [_row("1年以内", [800.0, 600.0]), _row("1至2年", [200.0, None]), _row("合计", [1000.0, 600.0], row_type="total")]}
BAD_DEBT_TABLE = {"name": "（2）按坏账准备计提方法分类披露应收账款", "headers": ["类别", "金额", "比例(%)"],
                  "rows": [_row("按单项计提坏账准备", [100.0, 10.0]), _row("合计", [100.0, 10.0], row_type="total")]}
R_AGE1, R_AGE2, R_AGE3, R_AGE_T = (str(uuid.uuid4()) for _ in range(4))
AGING_ROWS = [
    {"target_row_id": R_AGE1, "canonical_name": "1年以内", "aliases": [], "row_type": "data", "category": "required"},
    {"target_row_id": R_AGE2, "canonical_name": "1至2年", "aliases": [], "row_type": "data", "category": "required"},
    {"target_row_id": R_AGE3, "canonical_name": "2至3年", "aliases": [], "row_type": "data", "category": "required"},
    {"target_row_id": R_AGE_T, "canonical_name": "合计", "aliases": [], "row_type": "total", "category": "required"},
]


def _td(*tables):
    tables = [copy.deepcopy(t) for t in tables]
    return {"headers": list(tables[0]["headers"]), "rows": copy.deepcopy(tables[0]["rows"]), "_tables": tables}


def _labels(rows):
    return [r["label"] for r in rows]


def _rids(rows):
    return [r.get("_pushed_row_id") for r in rows]


_TABLES = [User, Project, DisclosureNote, ConsolNoteDetailTemplate, ConsolNoteDetailTemplateVersion,
           ConsolNoteTemplateBinding, ConsolNoteTemplatePushLog]
SUBS = ("甲", "乙", "丙", "丁", "戊")


@pytest_asyncio.fixture
async def env(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[m.__table__ for m in _TABLES]))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    actor = SimpleNamespace(id=uuid.uuid4(), role=UserRole.admin)
    cid = uuid.uuid4()
    subs = {name: uuid.uuid4() for name in SUBS}
    async with factory() as s:
        s.add(User(id=actor.id, username="pusher", email="pusher@example.com", hashed_password="x", role=UserRole.admin))
        s.add(Project(id=cid, name="集团_2025", client_name="集团", template_type="soe", report_scope="consolidated",
                      status=ProjectStatus.execution))
        for name, pid in subs.items():
            s.add(Project(id=pid, name=f"{name}_2025", client_name=f"{name}公司", template_type="soe",
                          report_scope="standalone", status=ProjectStatus.execution))
        await s.commit()

    leaves = [SimpleNamespace(node_key=f"n-{name}", project_id=pid, company_name=f"{name}公司") for name, pid in subs.items()]
    state = {"leaves": leaves, "denied": {}}

    async def fake_tree(_db, _pid):
        return object()

    async def fake_type(_db, _pid):
        return "soe"

    async def fake_gate(_db, _user, project_id, *, consol_lock):
        assert consol_lock is True, "写子企业附注须判合并锁"
        if project_id in state["denied"]:
            raise state["denied"][project_id]
        return _user

    monkeypatch.setattr("app.services.consol_tree_service.build_tree", fake_tree)
    monkeypatch.setattr("app.services.consol_calc_basis.data_leaves", lambda _tree: list(state["leaves"]))
    monkeypatch.setattr("app.services.consol_note_detail_source_service.resolve_section_template_type", fake_type)
    monkeypatch.setattr("app.services.note_edit_gate.assert_note_edit_access", fake_gate)
    yield SimpleNamespace(engine=engine, factory=factory, actor=actor, cid=cid, subs=subs, state=state)
    await engine.dispose()


async def _add_note(env, sub, table_data, *, section="八、1", title="货币资金", is_empty=False, sort_order=None):
    async with env.factory() as s:
        s.add(DisclosureNote(project_id=env.subs[sub], year=YEAR, note_section=section, section_title=title,
                             content_type=ContentType.table, table_data=table_data, is_empty=is_empty,
                             sort_order=sort_order))
        await s.commit()


async def _add_version(env, rows, *, section=CASH, template_type="soe", deleted=False, number=1, template_id=None):
    async with env.factory() as s:
        if template_id is None:
            tmpl = ConsolNoteDetailTemplate(template_type=template_type, section_id=section, name="t",
                                            created_by=env.actor.id, is_deleted=deleted)
            s.add(tmpl)
            await s.flush()
            template_id = tmpl.id
        version = ConsolNoteDetailTemplateVersion(template_id=template_id, version_number=number,
                                                  rows=copy.deepcopy(rows), created_by=env.actor.id)
        s.add(version)
        await s.commit()
        return version.id, template_id


async def _push(env, version_id, *, section=CASH):
    async with env.factory() as s:
        result = await push_template_to_subsidiaries(
            s, consol_project_id=env.cid, section_id=section, year=YEAR, template_version_id=version_id,
            actor=env.actor)
        await s.commit()
        return result


async def _note(env, sub, section="八、1"):
    async with env.factory() as s:
        return (await s.execute(sa.select(DisclosureNote).where(
            DisclosureNote.project_id == env.subs[sub], DisclosureNote.note_section == section))).scalar_one()


def _entity(result, sub):
    return next(e for e in result.entities if e.company_name == f"{sub}公司")


async def test_first_push_claims_existing_rows_without_touching_labels_or_values(env):
    await _add_note(env, "甲", _td(CASH_TABLE))
    vid, _ = await _add_version(env, CASH_ROWS)
    result = await _push(env, vid)

    er = _entity(result, "甲")
    assert (er.status, er.claimed, er.added, er.released) == ("success", 3, 1, 0)
    note = await _note(env, "甲")
    rows = note.table_data["_tables"][0]["rows"]
    # 「现金」按别名认领、行名不改；缺的「其他货币资金」补在合计之前；「其中：」行留在原位；动态行区占位不写
    assert _labels(rows) == ["现金", "银行存款", "其他货币资金", "合  计", "其中：存放在境外的款项总额"]
    assert _rids(rows) == [R_CASH, R_BANK, R_OTHER, R_TOTAL, None]
    assert [r["values"] for r in rows] == [[100.0, 90.0], [200.0, 180.0], [None, None], [300.0, 270.0], [None, None]]
    assert rows[2]["_pushed_category"] == "optional" and rows[2]["_pushed_optional_active"] is True
    assert "_pushed_optional_active" not in rows[0]
    assert note.table_data["rows"] == rows, "顶层 rows 原是首表镜像 ⇒ 跟着改"
    assert note.updated_by == env.actor.id, "以操作人身份盖「最近一次编辑」"
    # 其余企业没有该章节附注：跳过、写明原因，不替子企业新建章节
    assert {e.status for e in result.entities if e is not er} == {"skipped"}
    assert "未生成章节 八、1" in _entity(result, "乙").reason
    async with env.factory() as s:
        assert (await s.execute(sa.select(sa.func.count()).select_from(DisclosureNote))).scalar_one() == 1


async def test_repush_is_idempotent_and_keeps_subsidiary_choices(env):
    await _add_note(env, "甲", _td(CASH_TABLE))
    vid, tid = await _add_version(env, CASH_ROWS)
    await _push(env, vid)
    async with env.factory() as s:  # 子企业：填了其他货币资金、取消勾选、在合计前自己加了一行
        note = (await s.execute(sa.select(DisclosureNote).where(DisclosureNote.project_id == env.subs["甲"]))).scalar_one()
        td = copy.deepcopy(note.table_data)
        rows = td["_tables"][0]["rows"]
        rows[2]["values"] = [5.0, 4.0]
        rows[2]["_pushed_optional_active"] = False
        rows.insert(3, _row("支付宝余额", [7.0, None]))
        note.table_data = td
        await s.commit()
    before = (await _note(env, "甲")).table_data

    again = await _push(env, vid)
    assert (_entity(again, "甲").status, _entity(again, "甲").reason) == ("success", "已是最新，未改动")
    assert (await _note(env, "甲")).table_data == before

    # 新版本删掉「银行存款」：只去下推标记，不删行、不删数
    v2, _ = await _add_version(env, [r for r in CASH_ROWS if r["target_row_id"] != R_BANK], number=2, template_id=tid)
    third = await _push(env, v2)
    assert (_entity(third, "甲").claimed, _entity(third, "甲").released) == (3, 1)
    rows = (await _note(env, "甲")).table_data["_tables"][0]["rows"]
    bank = next(r for r in rows if r["label"] == "银行存款")
    assert bank["values"] == [200.0, 180.0] and "_pushed_row_id" not in bank and "_pushed_category" not in bank
    other = next(r for r in rows if r["label"] == "其他货币资金")
    assert other["values"] == [5.0, 4.0] and other["_pushed_optional_active"] is False
    assert _labels(rows).count("其他货币资金") == 1 and "支付宝余额" in _labels(rows)


async def test_pushes_into_the_mapped_table_not_the_first_one(env):
    await _add_note(env, "甲", _td(BAD_DEBT_TABLE, AGING_TABLE), section="八、5", title="应收账款")
    vid, _ = await _add_version(env, AGING_ROWS, section=AGING)
    result = await _push(env, vid, section=AGING)

    er = _entity(result, "甲")
    assert (er.status, er.table_name, er.claimed, er.added) == ("success", "（1）按账龄披露应收账款", 3, 1)
    td = (await _note(env, "甲", "八、5")).table_data
    assert td["_tables"][0] == BAD_DEBT_TABLE, "第 1 张表（坏账准备）不动"
    assert td["rows"] == BAD_DEBT_TABLE["rows"], "顶层镜像是第 1 张表，不动"
    aging = td["_tables"][1]["rows"]
    assert _labels(aging) == ["1年以内", "1至2年", "2至3年", "合计"]
    assert aging[2]["values"] == [None, None] and aging[2]["_pushed_row_id"] == R_AGE3
    assert [r["values"] for r in aging if r["label"] != "2至3年"] == [r["values"] for r in AGING_TABLE["rows"]]


async def test_sections_the_push_must_not_write_are_skipped_with_reasons(env):
    other_table = _cash_table(_row("应收利息", [1.0, None]), _row("合计", [1.0, None], row_type="total"))
    await _add_note(env, "甲", _td(CASH_TABLE))
    await _add_note(env, "丙", _td(CASH_TABLE), is_empty=True)
    await _add_note(env, "丁", {**_td(CASH_TABLE), "_source": "workpaper"})
    await _add_note(env, "戊", _td({**other_table, "name": "货币资金"}))
    before = {sub: copy.deepcopy((await _note(env, sub)).table_data) for sub in ("丙", "丁", "戊")}
    vid, _ = await _add_version(env, CASH_ROWS)
    result = await _push(env, vid)

    assert _entity(result, "甲").status == "success"
    reasons = {sub: _entity(result, sub).reason for sub in ("乙", "丙", "丁", "戊")}
    assert {sub: _entity(result, sub).status for sub in reasons} == dict.fromkeys(reasons, "skipped")
    assert "未生成章节 八、1" in reasons["乙"]
    assert "本期无此情形" in reasons["丙"]
    assert "底稿披露表同步" in reasons["丁"]
    assert "没有一行明细与集团模板对得上" in reasons["戊"], "只有「合计」对得上不算（多半选错了表）"
    for sub, td in before.items():
        assert (await _note(env, sub)).table_data == td, f"{sub} 不该被写"
    assert (result.success_count, result.skip_count, result.failure_count) == (1, 4, 0)


async def test_note_edit_gate_rejections_are_skips_and_others_still_written(env):
    for sub in ("甲", "乙", "丙"):
        await _add_note(env, sub, _td(CASH_TABLE))
    env.state["denied"] = {
        env.subs["乙"]: HTTPException(status_code=403, detail={"error_code": "X", "message": "权限不足"}),
        env.subs["丙"]: HTTPException(status_code=423, detail="项目已被合并锁定，无法修改"),
    }
    vid, _ = await _add_version(env, CASH_ROWS)
    result = await _push(env, vid)

    assert _entity(result, "甲").status == "success"
    assert (_entity(result, "乙").status, _entity(result, "乙").reason) == ("skipped", "权限不足")
    assert (_entity(result, "丙").status, _entity(result, "丙").reason) == ("skipped", "项目已被合并锁定，无法修改")
    for sub in ("乙", "丙"):
        assert _rids((await _note(env, sub)).table_data["_tables"][0]["rows"]) == [None] * 4


async def test_a_failing_subsidiary_rolls_back_alone(env, monkeypatch):
    for sub in ("甲", "乙", "丙"):
        await _add_note(env, sub, _td(CASH_TABLE))
    from app.services import note_edit_stamp

    real = note_edit_stamp.stamp_note_edit
    bad = env.subs["乙"]

    def stamp(note, user_id):  # 乙：表格已改写、盖章时出错 ⇒ 这一家整体回滚
        if note.project_id == bad:
            raise RuntimeError("盖章失败")
        real(note, user_id)

    monkeypatch.setattr(note_edit_stamp, "stamp_note_edit", stamp)
    vid, _ = await _add_version(env, CASH_ROWS)
    result = await _push(env, vid)

    assert _entity(result, "乙").status == "failed" and "盖章失败" in _entity(result, "乙").reason
    assert _rids((await _note(env, "乙")).table_data["_tables"][0]["rows"]) == [None] * 4
    for sub in ("甲", "丙"):
        assert _entity(result, sub).status == "success"
        assert R_CASH in _rids((await _note(env, sub)).table_data["_tables"][0]["rows"])
    assert result.failure_count == 1


async def test_push_log_is_written_per_push(env):
    """每次下推写一条下推记录（结构锁随 V202 退役，R16：本测试库不建锁表，下推再写锁即 no such table）。"""
    await _add_note(env, "甲", _td(CASH_TABLE))
    await _add_note(env, "丙", _td(CASH_TABLE))
    vid, tid = await _add_version(env, CASH_ROWS)
    await _push(env, vid)
    v2, _ = await _add_version(env, CASH_ROWS, number=2, template_id=tid)
    await _push(env, v2)

    async with env.factory() as s:
        logs = (await s.execute(sa.select(ConsolNoteTemplatePushLog).order_by(ConsolNoteTemplatePushLog.pushed_at))).scalars().all()
    assert [(lg.template_version_id, lg.entity_count, lg.success_count, lg.failure_count) for lg in logs] == [
        (vid, 5, 2, 0), (v2, 5, 2, 0)]
    assert logs[0].pushed_by == env.actor.id
    assert sorted(f["node_key"] for f in logs[0].failures) == ["n-丁", "n-乙", "n-戊"]
    assert {f["status"] for f in logs[0].failures} == {"skipped"}


@pytest.mark.parametrize(("kw", "expect"), [
    ({"section": AGING}, "不是 五-1-1"),
    ({"template_type": "listed"}, "与合并项目附注口径（国企）不符"),
    ({"deleted": True}, "已删除"),
])
async def test_template_version_is_validated_before_any_write(env, kw, expect):
    await _add_note(env, "甲", _td(CASH_TABLE))
    vid, _ = await _add_version(env, CASH_ROWS, **kw)
    with pytest.raises(PushTemplateError, match=expect):
        await _push(env, vid)
    assert _rids((await _note(env, "甲")).table_data["_tables"][0]["rows"]) == [None] * 4


async def test_template_without_pushable_rows_is_rejected(env):
    vid, _ = await _add_version(env, [r for r in CASH_ROWS if r["category"] == "dynamic_zone"])
    with pytest.raises(PushTemplateError, match="没有可下推的行"):
        await _push(env, vid)
    with pytest.raises(PushTemplateError, match="不存在"):
        await _push(env, uuid.uuid4())


# ── 端点（真实 require_project_access / check_consol_lock；只替换取库与当前用户）──


@pytest_asyncio.fixture
async def client(env):
    """请求共用一个会话（``env.request_session``）：SQLite 里最外层保存点 RELEASE 即提交，查不出漏提交，
    只能看 ORM 会话请求后是否还在事务里。"""
    from app.core.database import get_db
    from app.deps import get_current_user
    from app.middleware.error_handler import http_exception_handler
    from app.routers import consol_notes

    app = FastAPI()
    app.include_router(consol_notes.router)
    app.add_exception_handler(HTTPException, http_exception_handler)

    async with env.factory() as session:
        env.request_session = session

        async def db_override():
            yield session

        app.dependency_overrides[get_db] = db_override
        app.dependency_overrides[get_current_user] = lambda: env.actor
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            yield c


async def _bind(env, version_id, section=CASH):
    async with env.factory() as s:
        s.add(ConsolNoteTemplateBinding(project_id=env.cid, section_id=section, template_version_id=version_id))
        await s.commit()


def _url(env):
    return f"/api/consolidation/notes/{env.cid}/{YEAR}/push-template"


async def test_endpoint_pushes_bound_version_and_commits(env, client):
    await _add_note(env, "甲", _td(CASH_TABLE))
    vid, _ = await _add_version(env, CASH_ROWS)
    await _bind(env, vid)
    # 旧前端仍带 activate_lock（结构锁随 V202 退役，R16）：忽略、照常下推
    resp = await client.post(_url(env), json={"template_version_id": str(vid), "section_ids": [CASH], "activate_lock": True})
    assert resp.status_code == 200, resp.text
    assert not env.request_session.in_transaction(), "端点提交了事务"
    body = resp.json()
    assert (body["total_entities"], body["total_success"], body["total_skipped"], body["total_failure"]) == (5, 1, 4, 0)
    assert body["errors"] == [] and body["success"] is True
    assert R_CASH in _rids((await _note(env, "甲")).table_data["_tables"][0]["rows"]), "端点提交了写入"
    async with env.factory() as s:
        assert (await s.execute(sa.select(sa.func.count()).select_from(ConsolNoteTemplatePushLog))).scalar_one() == 1


async def test_endpoint_rejects_consol_locked_project_with_423(env, client):
    vid, _ = await _add_version(env, CASH_ROWS)
    await _bind(env, vid)
    async with env.factory() as s:
        (await s.get(Project, env.cid)).consol_lock = True
        await s.commit()
    resp = await client.post(_url(env), json={"section_ids": [CASH]})
    assert resp.status_code == 423 and "合并锁定" in resp.json()["message"]
    async with env.factory() as s:
        assert (await s.execute(sa.select(sa.func.count()).select_from(ConsolNoteTemplatePushLog))).scalar_one() == 0


@pytest.mark.parametrize(("payload", "bind", "expect"), [
    ({}, False, "没有绑定明细模板的章节"),
    ({"section_ids": [CASH]}, False, "章节未绑定明细模板"),
    ({"section_ids": [CASH], "template_version_id": "other"}, True, "与本章节绑定的版本不一致"),
    ({"section_ids": [CASH, AGING], "template_version_id": "any"}, True, "一次只能下推一个章节"),
])
async def test_endpoint_section_level_errors_are_400(env, client, payload, bind, expect):
    vid, _ = await _add_version(env, CASH_ROWS)
    if bind:
        await _bind(env, vid)
    payload = {**payload, **({"template_version_id": str(uuid.uuid4())} if payload.get("template_version_id") else {})}
    resp = await client.post(_url(env), json=payload)
    assert resp.status_code == 400 and expect in resp.json()["message"], resp.text


async def test_push_and_pull_pick_the_same_section_number_first_then_title(env):
    """同一企业按章节号与按标题都命中：取按号命中的那一节（下推写的与拉数读的是同一节）。"""
    from app.services.consol_note_detail_source_service import load_source_tables, load_standalone_note

    await _add_note(env, "甲", _td(CASH_TABLE), section="八、1")
    # 同标题的另一节排在后面（sort_order 非空排在 NULL 之后）：只认「最后一行」的取舍会选错它
    await _add_note(env, "甲", _td(_cash_table(_row("库存现金", [9.0, 9.0]))), section="五、1", sort_order=5)
    async with env.factory() as s:
        note = await load_standalone_note(s, env.subs["甲"], YEAR, "八、1", "货币资金")
        assert note.note_section == "八、1"
        only_title = await load_standalone_note(s, env.subs["甲"], YEAR, "七、9", "货币资金")
        assert only_title is not None and only_title.note_section in ("八、1", "五、1"), "按号取不到时按标题取"
        sources = await load_source_tables(s, [env.subs["甲"]], CASH, YEAR, template_type="soe")
    assert [r["label"] for r in sources[env.subs["甲"]].rows][:2] == ["现金", "银行存款"], "拉数读的也是按号命中的那一节"
