"""附件溯源项目隔离：查询只取本项目、附件未软删、``object_id`` 字面匹配；附件三端点按附件所属项目分级。

spec formula-hub-integrity-closure 任务 4；需求 7.2、7.3；ADR-FHIC-13；变异 #28。

A. 端点（TestClient 真发请求、真实鉴权链）：应用按生产注册只挂 ``attachment_lineage`` 与 ``lineage`` 两个 router，只替换
   ``get_current_user`` / ``get_db``，``require_project_access`` / ``assert_project_permission`` 照常按成员行判定。TestClient
   在自己的事件循环线程里跑应用，会话用 ``pg_tx`` 的同一实现 ``pg_tx_session`` 建在该线程（``client.portal``）：夹具、请求、
   对账共用同一外层事务，用例结束回滚。
   1. 两个项目各一个附件、关联的 ``target_ref`` 相同：每个项目的成员经溯源端点与附件关联端点只拿到本项目的行，另一项目的
      项目 / 附件 / 关联 id 与文件名不出现在响应文本里；A 的附件上 ``project_id`` 为空的行（迁移后旧代码写入）两个端点都
      不返回；查另一项目附件的关联 ⇒ 403。
   2. 分级（需求 7.3）：readonly 成员查询 200、关联 / 删除关联 403；非成员查询 / 关联 403；拒绝后关联行不变。edit 成员关联
      写入附件所属项目（库内 ``project_id`` = A）、能删本项目的行；删 ``project_id`` 为空的行 ⇒ 404 且该行仍在。

B. 查询语义（``pg_tx``，直调 ``UnifiedLineageService._query_attachments``）。溯源端点对 ``note_cell`` / ``report_row`` 会先跑
   附注溯源子源，快照库没有 ``note_wp_mapping`` 表，该子源报错使事务中止、附件子源随之取空（子源隔离归任务 27），故不经端点。
   1. 字面匹配（表驱动）：``%``、``_``、``\\`` 与实现所用的转义符 ``/`` 在等值与「``object_id + '!'`` 前缀」两条分支都按字面；
      前缀须紧跟 ``!``；``object_id`` 含 ``!`` 只做等值。期望集合由纯 Python（``==`` / ``str.startswith``）对全部引用逐个判定，
      不经 SQL。每个引用另有 ``project_id`` 为空、属于另一项目的两条同引用行，加一条附件已不存在（``project_id`` 已回填）的
      孤儿，都不得返回。
   2. 附件软删前可见、软删后不可见。
   3. 类型：``note_cell`` 查 ``target_type='note_section'`` 的行（``note_cell`` 原值的行不算）；``wp_cell`` / ``report_row`` 同名；
      表外类型 ``tb_row``、``adjustment`` 按原值精确匹配。
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.routers.attachment_lineage as attachment_lineage_router
import app.routers.lineage as lineage_router
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import PermissionLevel, ProjectUserRole, UserRole
from app.models.core import ProjectUser, User
from app.services.attachment_lineage_schema import clear_lineage_schema_cache
from app.services.unified_lineage_service import UnifiedLineageService
from tests.authz_world import assert_world_overrides, build_app
from tests.formula_hub._lineage_fixtures import insert_lineage, lineage_state, make_attachment, make_project
from tests.formula_hub._pg_harness import pg_tx_session

pytestmark = pytest.mark.pg_only

REF = "FH-T4-ISO"
CELL = f"{REF}!B5"


@pytest.fixture(autouse=True)
def _fresh_schema_cache():
    clear_lineage_schema_cache()
    yield
    clear_lineage_schema_cache()


# ─── A. 端点 ─────────────────────────────────────────────────────────────────


@dataclass
class Side:
    project_id: uuid.UUID
    attachment_id: uuid.UUID
    file_name: str
    links: set[uuid.UUID]
    reader: User  # 本项目 readonly 成员

    def secrets(self) -> list[str]:
        return [str(self.project_id), str(self.attachment_id), self.file_name, *map(str, self.links)]


@dataclass
class World:
    a: Side
    b: Side
    editor_a: User  # A 的 edit 成员
    null_a: uuid.UUID  # A 的附件上 project_id 为空的行


async def _member(session, project_id: uuid.UUID, level: PermissionLevel) -> User:
    tag = uuid.uuid4().hex[:10]
    user = User(username=f"fh_iso_{tag}", email=f"fh_iso_{tag}@example.test", hashed_password="x",
                role=UserRole.auditor)
    session.add(user)
    await session.flush()
    session.add(ProjectUser(project_id=project_id, user_id=user.id, role=ProjectUserRole.auditor,
                            permission_level=level))
    await session.flush()
    return user


async def _side(session, label: str) -> Side:
    project_id = await make_project(session, f"iso_{label}")
    attachment_id = await make_attachment(session, project_id)
    file_name = (await session.execute(text("SELECT file_name FROM attachments WHERE id = :id"),
                                       {"id": attachment_id})).scalar_one()
    links = set()
    for ref in (REF, CELL):  # 等值命中、「REF!」前缀命中各一行
        links.add(await insert_lineage(session, attachment_id=attachment_id, target_ref=ref, project_id=project_id))
    reader = await _member(session, project_id, PermissionLevel.readonly)
    return Side(project_id, attachment_id, file_name, links, reader)


async def _seed(session) -> World:
    a = await _side(session, "a")
    b = await _side(session, "b")
    editor_a = await _member(session, a.project_id, PermissionLevel.edit)
    null_a = await insert_lineage(session, attachment_id=a.attachment_id, target_ref=CELL)  # project_id 为空
    await session.commit()  # pg_tx_session：只释放保存点
    return World(a, b, editor_a, null_a)


async def _rows_of(session, attachment_id: uuid.UUID) -> dict[uuid.UUID, dict]:
    ids = (await session.execute(text("SELECT id FROM attachment_lineage WHERE attachment_id = :aid"),
                                 {"aid": attachment_id})).scalars().all()
    return await lineage_state(session, list(ids))


@contextmanager
def _endpoint() -> Iterator[tuple[TestClient, object, object]]:
    api = build_app(attachment_lineage_router.router, lineage_router.router)
    with TestClient(api) as client:
        with client.portal.wrap_async_context_manager(pg_tx_session()) as session:
            async def _db():
                yield session

            api.dependency_overrides[get_db] = _db
            yield client, session, api


def _as(api, user: User) -> None:
    async def _user():
        return user

    api.dependency_overrides[get_current_user] = _user
    assert_world_overrides(api)


def _lineage(client: TestClient, project_id: uuid.UUID):
    return client.get(f"/api/projects/{project_id}/lineage",
                      params={"object_type": "wp_cell", "object_id": REF, "direction": "both"})


def _ids(items) -> set[str]:
    return {item["id"] for item in items}


def test_two_projects_same_ref_each_member_sees_only_own_project():
    with _endpoint() as (client, session, api):
        world = client.portal.call(_seed, session)
        seen = {}
        for own, other in ((world.a, world.b), (world.b, world.a)):
            _as(api, own.reader)
            seen[own.project_id] = {
                "lineage": _lineage(client, own.project_id),
                "links": client.get(f"/api/attachments/{own.attachment_id}/links"),
                "foreign_links": client.get(f"/api/attachments/{other.attachment_id}/links"),
            }

    for own, other in ((world.a, world.b), (world.b, world.a)):
        responses = seen[own.project_id]
        lineage, links, foreign = responses["lineage"], responses["links"], responses["foreign_links"]
        assert lineage.status_code == 200, lineage.text
        assert lineage.json()["errors"] == []
        assert _ids(lineage.json()["attachments"]) == {str(i) for i in own.links}, lineage.text
        assert links.status_code == 200, links.text
        assert _ids(links.json()) == {str(i) for i in own.links}, links.text
        assert foreign.status_code == 403, foreign.text
        for name, response in responses.items():
            leaked = [secret for secret in other.secrets() if secret in response.text]
            assert leaked == [], (own.project_id, name, leaked)
    for name in ("lineage", "links"):
        assert str(world.null_a) not in seen[world.a.project_id][name].text, name


def test_levels_follow_attachment_project_and_post_writes_project_id():
    body = {"target_type": "wp_cell", "target_ref": CELL}
    with _endpoint() as (client, session, api):
        world = client.portal.call(_seed, session)
        a = world.a
        base = f"/api/attachments/{a.attachment_id}"
        before = client.portal.call(_rows_of, session, a.attachment_id)
        denied = {}
        _as(api, a.reader)
        reader_get = client.get(f"{base}/links")
        denied["readonly POST"] = client.post(f"{base}/link", json=body)
        denied["readonly DELETE"] = client.delete(f"{base}/link/{sorted(a.links)[0]}")
        _as(api, world.b.reader)  # A 的非成员
        denied["non_member GET"] = client.get(f"{base}/links")
        denied["non_member POST"] = client.post(f"{base}/link", json=body)
        after_denied = client.portal.call(_rows_of, session, a.attachment_id)

        _as(api, world.editor_a)
        created = client.post(f"{base}/link", json=body)
        assert created.status_code == 200, created.text
        created_id = uuid.UUID(created.json()["id"])
        stored = client.portal.call(lineage_state, session, [created_id])
        null_delete = client.delete(f"{base}/link/{world.null_a}")
        own_delete = client.delete(f"{base}/link/{created_id}")
        after = client.portal.call(_rows_of, session, a.attachment_id)

    assert reader_get.status_code == 200, reader_get.text
    assert _ids(reader_get.json()) == {str(i) for i in a.links}, reader_get.text
    for name, response in denied.items():
        assert response.status_code == 403, (name, response.text)
    assert after_denied == before  # 拒绝时 attachment_lineage 行不变
    assert stored[created_id]["project_id"] == str(a.project_id)  # POST 写入附件所属项目
    assert null_delete.status_code == 404, null_delete.text
    assert own_delete.status_code == 200, own_delete.text
    assert world.null_a in after and after == before  # 空值行仍在；新建的行已删，其余不变


# ─── B. 查询语义 ─────────────────────────────────────────────────────────────

#: (object_id, 应命中的引用, 只差通配 / 转义 / 边界、不应命中的引用)；``"\\"`` 是一个反斜杠
_LITERAL_CASES: list[tuple[str, set[str], set[str]]] = [
    ("FH%T4", {"FH%T4", "FH%T4!B5"}, {"FHxyzT4", "FHxyzT4!B5", "FH%T40!B5"}),
    ("FH_T4", {"FH_T4", "FH_T4!B5"}, {"FHxT4", "FHxT4!B5"}),
    ("FH\\T4", {"FH\\T4", "FH\\T4!B5"}, {"FHT4", "FHT4!B5", "FH\\\\T4!B5"}),
    ("FH/T4", {"FH/T4", "FH/T4!B5"}, {"FH//T4!B5"}),
    ("FH-T4-PFX", {"FH-T4-PFX", "FH-T4-PFX!B5", "FH-T4-PFX!B50"}, {"FH-T4-PFX0!B5", "X-FH-T4-PFX!B5"}),
    ("FH-T4-PFX!B5", {"FH-T4-PFX!B5"}, {"FH-T4-PFX!B50", "FH-T4-PFX!B5!C1"}),
]


def _literal_hit(object_id: str, ref: str) -> bool:
    """需求 7.2 的字面口径：等值，或（``object_id`` 不含 ``!`` 时）以 ``object_id + "!"`` 开头。"""
    return ref == object_id or ("!" not in object_id and ref.startswith(f"{object_id}!"))


async def _found(service: UnifiedLineageService, project_id: uuid.UUID, object_type: str, object_id: str):
    return await service._query_attachments(project_id, object_type, object_id)


async def test_literal_match_project_scope_and_orphans(pg_tx):
    session = pg_tx
    refs = set()
    for object_id, hits, misses in _LITERAL_CASES:  # 先自检表：判定函数与表里的「应 / 不应命中」一致
        assert all(_literal_hit(object_id, ref) for ref in hits), (object_id, hits)
        assert not any(_literal_hit(object_id, ref) for ref in misses), (object_id, misses)
        refs |= hits | misses
    project_id = await make_project(session, "iso_lit")
    other_project = await make_project(session, "iso_lit_other")
    attachment_id = await make_attachment(session, project_id)
    other_attachment = await make_attachment(session, other_project)
    own: dict[str, uuid.UUID] = {}
    invisible: set[str] = set()
    for ref in sorted(refs):
        own[ref] = await insert_lineage(session, attachment_id=attachment_id, target_ref=ref, project_id=project_id)
        invisible.add(str(await insert_lineage(session, attachment_id=attachment_id, target_ref=ref)))
        invisible.add(str(await insert_lineage(session, attachment_id=other_attachment, target_ref=ref,
                                               project_id=other_project)))
    invisible.add(str(await insert_lineage(session, attachment_id=uuid.uuid4(), target_ref="FH-T4-PFX!B7",
                                           project_id=project_id)))  # 孤儿：附件已不存在，project_id 已回填
    service = UnifiedLineageService(session)
    for object_id, _hits, _misses in _LITERAL_CASES:
        rows = await _found(service, project_id, "wp_cell", object_id)
        want = {str(own[ref]) for ref in refs if _literal_hit(object_id, ref)}
        assert {row["id"] for row in rows} == want, (object_id, sorted(row["target_ref"] for row in rows))
        assert not invisible & {row["id"] for row in rows}, object_id


async def test_soft_deleted_attachment_rows_are_invisible(pg_tx):
    session = pg_tx
    project_id = await make_project(session, "iso_del")
    attachment_id = await make_attachment(session, project_id)
    link = await insert_lineage(session, attachment_id=attachment_id, target_ref="FH-T4-DEL!B5", project_id=project_id)
    service = UnifiedLineageService(session)
    before = {row["id"] for row in await _found(service, project_id, "wp_cell", "FH-T4-DEL")}
    await session.execute(text("UPDATE attachments SET is_deleted = true WHERE id = :id"), {"id": attachment_id})
    after = {row["id"] for row in await _found(service, project_id, "wp_cell", "FH-T4-DEL")}
    assert before == {str(link)} and after == set(), (before, after)


#: 溯源对象类型 → 应命中的 ``target_type``（``note_cell`` 映射；表外类型按原值）
_TYPE_CASES = {"wp_cell": "wp_cell", "report_row": "report_row", "note_cell": "note_section",
               "tb_row": "tb_row", "adjustment": "adjustment"}


async def test_object_type_maps_to_attachment_target_type(pg_tx):
    session = pg_tx
    project_id = await make_project(session, "iso_type")
    attachment_id = await make_attachment(session, project_id)
    ref = "五、1"  # 同一引用在每种 target_type 下各一行，含 note_cell 原值的一行
    rows: dict[str, uuid.UUID] = {}
    for target_type in ("wp_cell", "report_row", "note_section", "note_cell", "tb_row", "adjustment"):
        rows[target_type] = await insert_lineage(session, attachment_id=attachment_id, target_ref=ref,
                                                 target_type=target_type, project_id=project_id)
    service = UnifiedLineageService(session)
    got = {}
    for object_type in _TYPE_CASES:
        found = await _found(service, project_id, object_type, ref)
        got[object_type] = {(row["target_type"], row["id"]) for row in found}
    assert got == {object_type: {(t, str(rows[t]))} for object_type, t in _TYPE_CASES.items()}, got
