"""export-word / check-incomplete 端点级测试（spec ``api-prefix-fix-recovery`` 任务 4）

═══ 为什么必须真发请求 ═══

本 spec 的主题就是「端点坏了三个月没人发现」：`completion_phase` 里两份同路径实现比
`wp_export_word` 先注册、把后者遮蔽住，而它们自己又坏的（`WorkingPaper` 没有 `wp_code` 列 ⇒
导出恒 500；check 返回 `{incomplete, count}` 与前端 / `CheckIncompleteResponse` 的
`{complete, missing_fields, wp_code, reason}` 不符 ⇒ 确认框永不弹）。这三个月里
`test_wp_export_word.py` 只测 service 层、`test_regulatory_letter_service.py` 只测 service 实现
—— 所以**只测 service 会漏掉整类问题**。这里走 `app.main.app` 真发 HTTP 请求。

═══ 覆盖 ═══

- check-incomplete 的响应信封是 `{complete, missing_fields, wp_code, reason}`（两态：未完成非空 / 全部完成）
- export-word 不再 500，返回 docx 文件流（`Content-Disposition` + OOXML MIME + zip 魔数）
- 鉴权：未登录 401；非成员 403；跨项目 wp_id 404（挂了项目只读门 ≠ wp 属于该项目）
- 未注册编码 501
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, ProjectStatus, UserRole
from app.models.core import Project, ProjectUser, User
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType, WpStatus

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

OWNER, READER, OUTSIDER = (uuid.uuid4() for _ in range(3))
_ROLE = {
    OWNER: UserRole.auditor,
    READER: UserRole.auditor,
    OUTSIDER: UserRole.auditor,
}
PROJECT = uuid.uuid4()
OTHER_PROJECT = uuid.uuid4()
WP_ID = uuid.uuid4()
OTHER_WP_ID = uuid.uuid4()
UNREGISTERED_WP_ID = uuid.uuid4()

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

#: ``checklist_responses`` 没有 ORM 模型（走裸 SQL），``Base.metadata.create_all`` 建不出来 ——
#: 必须按现表结构手工建（与 ``tests/test_review_rbac_guard.py`` / ``test_procedure_trim_recycle.py`` 同法）。
_CHECKLIST_DDL = (
    "CREATE TABLE checklist_responses ("
    "id TEXT PRIMARY KEY, project_id TEXT NOT NULL, wp_id TEXT NOT NULL, "
    "item_id TEXT NOT NULL, conclusion TEXT, remark TEXT, wp_ref TEXT, updated_by TEXT, "
    "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "
    "updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"
)

#: 检查表行按真实写入方形状造：item_id 前缀 ``a182-``，值在 remark，``conclusion`` 恒 null
#: （``useA182RegulatoryCommunication.ts`` 的 ``a182-matter${id}-${field}``）
_ALL_DONE_ROWS = [
    ("a182-matter1-applicability", "N"),
    ("a182-matter2-applicability", "NA"),
    ("a182-matter3-applicability", "N"),
    ("a182-matter4-applicability", "N"),
]
_INCOMPLETE_ROWS = [
    ("a182-matter1-applicability", "Y"),  # 适用但没填内容 ⇒ 未完成
    ("a182-matter2-applicability", "N"),
    ("a182-matter3-applicability", "NA"),
    ("a182-matter4-applicability", "Y"),  # 适用但没填内容 ⇒ 未完成
]
#: 未完成行之外再补一次 Excel 导出的内容（保证导出路径也走「有内容」分支）
_EXPORT_ROWS = [
    ("a182-recipient-authority", "中国证券监督管理委员会"),
    ("a182-matter1-applicability", "Y"),
    ("a182-matter1-content", "已识别出管理层凌驾于控制之上的风险迹象，并已向治理层书面沟通。"),
    ("a182-matter2-applicability", "N"),
    ("a182-matter3-applicability", "N"),
    ("a182-matter4-applicability", "Y"),
    ("a182-matter4-content", "无其他需沟通的重大事项。"),
]


class _PlainUser:
    """测试替身：与生产 ``User`` 一样区分 ``role.value``（``deps.assert_project_permission`` 读它）。"""

    def __init__(self, user_id: uuid.UUID) -> None:
        self.id = user_id
        self.username = f"u{user_id.hex[:8]}"
        self.email = f"{user_id.hex[:8]}@test.local"
        self.role = _ROLE[user_id]
        self.is_active = True
        self.is_deleted = False


@pytest_asyncio.fixture
async def db():
    from sqlalchemy import text

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(_CHECKLIST_DDL))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        for uid in _ROLE:
            session.add(
                User(
                    id=uid,
                    username=f"u{uid.hex[:8]}",
                    email=f"{uid.hex[:8]}@test.local",
                    hashed_password="x",
                    role=_ROLE[uid].value,
                )
            )
        session.add_all(
            [
                Project(
                    id=PROJECT, name="【测试】A18-2 导出",
                    client_name="测试股份有限公司", status=ProjectStatus.execution,
                    audit_year=2025, created_by=OWNER,
                ),
                Project(
                    id=OTHER_PROJECT, name="【测试】别的项目",
                    client_name="别的公司", status=ProjectStatus.execution,
                    audit_year=2025, created_by=OWNER,
                ),
            ]
        )
        a182_index = WpIndex(
            id=uuid.uuid4(), project_id=PROJECT, wp_code="A18-2",
            wp_name="与监管层沟通函", audit_cycle="A", status=WpStatus.not_started,
        )
        other_index = WpIndex(
            id=uuid.uuid4(), project_id=OTHER_PROJECT, wp_code="D2",
            wp_name="应收账款", audit_cycle="D", status=WpStatus.not_started,
        )
        unregistered_index = WpIndex(
            id=uuid.uuid4(), project_id=PROJECT, wp_code="Z9",
            wp_name="未注册导出服务的编码", audit_cycle="Z", status=WpStatus.not_started,
        )
        session.add_all([a182_index, other_index, unregistered_index])
        session.add_all(
            [
                WorkingPaper(
                    id=WP_ID, project_id=PROJECT, wp_index_id=a182_index.id,
                    file_path="A18-2.xlsx", source_type=WpSourceType.template, file_version=1,
                ),
                WorkingPaper(
                    id=OTHER_WP_ID, project_id=OTHER_PROJECT, wp_index_id=other_index.id,
                    file_path="D2.xlsx", source_type=WpSourceType.template, file_version=1,
                ),
                WorkingPaper(
                    id=UNREGISTERED_WP_ID, project_id=PROJECT, wp_index_id=unregistered_index.id,
                    file_path="Z9.xlsx", source_type=WpSourceType.template, file_version=1,
                ),
            ]
        )
        for uid, level in ((OWNER, "edit"), (READER, "readonly")):
            session.add(
                ProjectUser(
                    project_id=PROJECT, user_id=uid, role="auditor",
                    permission_level=level, is_deleted=False,
                )
            )
        await session.commit()
        yield session
    await engine.dispose()


async def _seed_rows(db: AsyncSession, rows: list[tuple[str, str]]) -> None:
    from sqlalchemy import text

    for item_id, remark in rows:
        await db.execute(
            text(
                "INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, remark) "
                "VALUES (:id, :pid, :wid, :iid, NULL, :remark)"
            ),
            {
                "id": uuid.uuid4().hex,
                "pid": str(PROJECT),
                "wid": str(WP_ID),
                "iid": item_id,
                "remark": remark,
            },
        )
    await db.commit()


@pytest_asyncio.fixture
async def client(db, monkeypatch):
    """真 ``app.main.app`` + 真项目级鉴权判定；只替换取当前用户、数据库连接与 Wp_Bound_Gate。

    🔴 不 override ``require_project_access`` —— 它是依赖工厂，每次 ``require_project_access("readonly")``
    返回**新函数对象**，按 key 覆盖会静默失效（全部 401），覆盖 ``get_current_user`` 才能让真实判定跑起来。

    🔴 把 ``enforce_wp_gate`` 换成 no-op：那是 router 级可见性门（``dedicated_wp_gate``），要读
    ``wp_visibility_policy_epoch`` / 委派历史 / 生效范围等 PG 专有结构，SQLite 上恒 404
    「资源不存在或不可访问」—— 本文件测的是**项目级鉴权 + 业务契约**，可见性门本身有专属套件
    （``tests/procedure_delegation_visibility/``）。同一处置见 ``test_wp_content_write_edit_lock.py``。
    注意：门换成 no-op 后 ``get_current_user`` 仍由 ``dedicated_wp_gate`` 自己依赖 ⇒ 未登录照样 401。
    """
    from app.main import app
    from app.routers import _wp_gate

    async def _no_gate(*_args, **_kwargs):
        return None

    monkeypatch.setattr(_wp_gate, "enforce_wp_gate", _no_gate)

    state: dict = {}

    async def _override_db():
        yield db

    async def _override_user():
        uid = state.get("user")
        if uid is None:
            raise AssertionError("测试未设置当前用户")
        return _PlainUser(uid)

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            c.as_user = lambda uid: state.update(user=uid)  # type: ignore[attr-defined]
            yield c
    finally:
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def anon():
    """未登录：取当前用户走真实实现（无 Authorization 头 ⇒ 401）。"""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _check_url(pid: uuid.UUID = PROJECT, wp_id: uuid.UUID = WP_ID) -> str:
    return f"/api/projects/{pid}/working-papers/{wp_id}/export-word/check-incomplete"


def _export_url(pid: uuid.UUID = PROJECT, wp_id: uuid.UUID = WP_ID) -> str:
    return f"/api/projects/{pid}/working-papers/{wp_id}/export-word"


def _payload(resp) -> dict:
    """解 ``ResponseWrapperMiddleware`` 的 ``{code, message, data}`` 信封。"""
    body = resp.json()
    if isinstance(body, dict) and "data" in body and "code" in body:
        return body["data"]
    return body


def _message(resp) -> object:
    """拒绝文案：错误信封把 ``HTTPException.detail`` 放在 ``message``。"""
    body = resp.json()
    if not isinstance(body, dict):
        return None
    return body.get("message", body.get("detail"))


# ─── check-incomplete ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_incomplete_returns_frontend_contract_when_incomplete(client, db):
    """有未完成项：``complete=False`` 且 ``missing_fields`` 是可读中文标签（前端据此列明缺哪几项）。

    🔴 这个断言在原实现下不可能过：原实现返回 ``{incomplete, count}``，`missing_fields` 取不到，
    前端 `Array.isArray(incomplete?.missing_fields)` 恒 false ⇒ 确认框永不弹。
    """
    await _seed_rows(db, _INCOMPLETE_ROWS)
    client.as_user(READER)

    resp = await client.get(_check_url())
    assert resp.status_code == 200, resp.text
    data = _payload(resp)
    assert set(data) == {"complete", "missing_fields", "wp_code", "reason"}
    assert data["complete"] is False
    assert data["wp_code"] == "A18-2"
    assert len(data["missing_fields"]) == 2
    assert "舞弊" in data["missing_fields"][0]
    assert "其他事项" in data["missing_fields"][1]
    assert data["reason"] == "2 项议题未完成"


@pytest.mark.asyncio
async def test_check_incomplete_reports_complete_when_all_matters_decided(client, db):
    """全部处理完（不适用也算处理完）：``complete=True``、无缺失项、无原因。"""
    await _seed_rows(db, _ALL_DONE_ROWS)
    client.as_user(READER)

    resp = await client.get(_check_url())
    assert resp.status_code == 200, resp.text
    data = _payload(resp)
    assert data == {
        "complete": True,
        "missing_fields": [],
        "wp_code": "A18-2",
        "reason": None,
    }


# ─── export-word ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_word_returns_docx_instead_of_500(client, db):
    """导出 Word 不再 500，返回 docx 文件流（OOXML MIME + attachment 头 + zip 魔数）。

    🔴 原实现 100% 500：``find_template_file_any(wp.wp_code)`` 里 ``WorkingPaper`` 没有 ``wp_code`` 列
    ⇒ ``AttributeError``（该实现已删，现由 ``wp_export_word`` 分发到 ``regulatory_letter_service``）。
    """
    await _seed_rows(db, _EXPORT_ROWS)
    client.as_user(OWNER)

    resp = await client.get(_export_url())
    assert resp.status_code == 200, resp.text[:600]
    assert resp.headers["content-type"].startswith(DOCX_MIME), resp.headers
    disposition = resp.headers.get("content-disposition", "")
    assert "attachment" in disposition
    assert "A18-2" in disposition
    # docx 是 zip：首两字节 PK
    assert resp.content[:2] == b"PK", resp.content[:16]


# ─── 鉴权 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_endpoints_reject_unauthenticated(anon):
    """未登录 401（两条端点）。"""
    assert (await anon.get(_check_url())).status_code == 401
    assert (await anon.get(_export_url())).status_code == 401


@pytest.mark.asyncio
async def test_endpoints_reject_non_member(client, db):
    """不是项目成员 403（读被审计单位底稿要有该项目只读权）。"""
    await _seed_rows(db, _ALL_DONE_ROWS)
    client.as_user(OUTSIDER)
    assert (await client.get(_check_url())).status_code == 403
    assert (await client.get(_export_url())).status_code == 403


@pytest.mark.asyncio
async def test_endpoints_reject_workpaper_of_another_project(client, db):
    """``wp_id`` 属于别的项目 ⇒ 404。

    项目只读门只能证明「调用者能读路径上的 project_id」，不证明「wp_id 属于它」——
    不校验就能拿 A 项目权限导出 B 项目底稿（``_resolve_wp_code`` 已带 project_id 过滤）。
    """
    client.as_user(OWNER)
    resp = await client.get(_check_url(PROJECT, OTHER_WP_ID))
    assert (resp.status_code, _message(resp)) == (404, "底稿不存在")
    resp = await client.get(_export_url(PROJECT, OTHER_WP_ID))
    assert (resp.status_code, _message(resp)) == (404, "底稿不存在")


# ─── 未注册编码 ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_incomplete_for_unregistered_code_returns_501_schema(client):
    """未注册导出服务的编码返回 501，但 body 仍带完整 schema（前端能显示原因）。"""
    client.as_user(OWNER)
    resp = await client.get(_check_url(PROJECT, UNREGISTERED_WP_ID))
    assert resp.status_code == 501, resp.text
    message = _message(resp)
    assert isinstance(message, dict), message
    assert message["complete"] is False
    assert message["wp_code"] == "Z9"
    assert message["reason"] == "检查服务未就绪"


@pytest.mark.asyncio
async def test_export_word_for_unregistered_code_returns_501(client):
    """未注册编码的导出返回 501（不是 500）。"""
    client.as_user(OWNER)
    resp = await client.get(_export_url(PROJECT, UNREGISTERED_WP_ID))
    assert resp.status_code == 501, resp.text
    assert "Z9" in str(_message(resp))
