"""AI 待确认列表的目标标签（spec ai-content-pending-target-label）。

2026-10-21 R6 把「target_label 全 None」标为已修，但没有一个用例断言标签值。实际：底稿查
``working_paper.wp_name``（列在 ``wp_index``）、附注把 ``target_cell`` 末段当章节号（第二段才是附注 id）、
两条查询放同一保存点 ⇒ 列表含底稿项时全部为空。这里用真 ORM + 真路由逐条钉死标签值。

``target_cell`` 编码以写入方为准：``ai_content_log_service.create`` 存 ``{instance_type}:{instance_id}[:{位置}]``。
"""

from __future__ import annotations

import ast
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# SQLite 兼容 JSONB + ARRAY（先于模型导入）
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

import app.models.core  # noqa: E402, F401
import app.models.audit_log_models  # noqa: E402, F401
import app.models.report_models  # noqa: E402, F401
import app.models.v3_refinement_models  # noqa: E402, F401
import app.models.workpaper_models  # noqa: E402, F401

from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.models.base import Base, ProjectStatus, ProjectType, UserRole  # noqa: E402
from app.models.core import Project, User  # noqa: E402
from app.models.report_models import DisclosureNote  # noqa: E402
from app.models.v3_refinement_models import AiContentLog  # noqa: E402
from app.models.workpaper_models import (  # noqa: E402
    WorkingPaper,
    WpFileStatus,
    WpIndex,
    WpReviewStatus,
    WpSourceType,
)
from app.routers import ai_content  # noqa: E402

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
_ROUTER_FILE = Path(ai_content.__file__)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        tables = [
            Base.metadata.tables[name]
            for name in ("users", "projects", "wp_index", "working_paper", "disclosure_notes", "ai_content_log")
        ]
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


def _wp(project_id, index_id, path):
    return WorkingPaper(
        id=uuid.uuid4(), project_id=project_id, wp_index_id=index_id, file_path=path,
        source_type=WpSourceType.manual, status=WpFileStatus.draft, review_status=WpReviewStatus.not_submitted,
    )


def _note(project_id, section, title):
    return DisclosureNote(
        id=uuid.uuid4(), project_id=project_id, year=2025, note_section=section, section_title=title,
        section_id=f"sec_{uuid.uuid4().hex[:8]}", text_content="", table_data={"rows": []},
    )


@pytest_asyncio.fixture
async def world(db_session: AsyncSession) -> dict:
    """本项目 P：底稿 D2（有底稿行）、E1（只有索引）、附注 八、1 / 八、5；别的项目 Q：底稿 F1、附注 八、9。"""
    admin = User(
        id=uuid.uuid4(), username=f"lbl_{uuid.uuid4().hex[:8]}", email=f"{uuid.uuid4().hex[:8]}@lbl.example",
        hashed_password="x", role=UserRole.admin, is_active=True,
    )
    db_session.add(admin)
    await db_session.flush()
    p = Project(id=uuid.uuid4(), name="【测试】标签项目", client_name="客户", project_type=ProjectType.annual,
                status=ProjectStatus.execution, created_by=admin.id)
    q = Project(id=uuid.uuid4(), name="【测试】别的项目", client_name="客户", project_type=ProjectType.annual,
                status=ProjectStatus.execution, created_by=admin.id)
    db_session.add_all([p, q])
    await db_session.flush()

    wi_d2 = WpIndex(id=uuid.uuid4(), project_id=p.id, wp_code="D2", wp_name="应收账款审定表")
    wi_e1 = WpIndex(id=uuid.uuid4(), project_id=p.id, wp_code="E1", wp_name="货币资金审定表")
    wi_q = WpIndex(id=uuid.uuid4(), project_id=q.id, wp_code="F1", wp_name="存货审定表")
    db_session.add_all([wi_d2, wi_e1, wi_q])
    await db_session.flush()
    wp_d2 = _wp(p.id, wi_d2.id, "/t/d2.xlsx")
    wp_q = _wp(q.id, wi_q.id, "/t/f1.xlsx")
    n_cash = _note(p.id, "八、1", "货币资金")
    n_stock = _note(p.id, "八、5", "存货")
    n_q = _note(q.id, "八、9", "别的项目附注")
    db_session.add_all([wp_d2, wp_q, n_cash, n_stock, n_q])
    await db_session.flush()

    cells = {
        "wp_by_paper": f"workpaper:{wp_d2.id}:E5",
        "wp_by_index": f"workpaper:{wi_e1.id}",
        "note_two_parts": f"note:{n_cash.id}",
        "note_three_parts": f"note:{n_stock.id}:正文第一段",
        "note_colon_position": f"note:{n_cash.id}:位置:含冒号",
        "wp_other_project": f"workpaper:{wp_q.id}",
        "wp_other_project_index": f"workpaper:{wi_q.id}",
        "note_other_project": f"note:{n_q.id}",
        "not_uuid": "workpaper:x'; DROP TABLE wp_index;--:E1",
        "no_target": None,
    }
    logs = {}
    for n, (key, cell) in enumerate(cells.items()):
        log = AiContentLog(
            id=uuid.uuid4(), project_id=p.id, user_id=admin.id, content_hash="c" * 64, target_cell=cell,
            model="qwen3.5", generated_content=f"AI 内容 {n}", confirm_action="pending",
            generated_at=datetime.now(timezone.utc),
        )
        db_session.add(log)
        logs[key] = log
    await db_session.commit()
    return {"admin": admin, "project": p, "logs": logs}


EXPECTED = {
    # key: (instance_type, target_label, target_position)
    "wp_by_paper": ("workpaper", "D2 应收账款审定表", "E5"),
    "wp_by_index": ("workpaper", "E1 货币资金审定表", None),
    "note_two_parts": ("note", "八、1 货币资金", None),
    "note_three_parts": ("note", "八、5 存货", "正文第一段"),
    "note_colon_position": ("note", "八、1 货币资金", "位置:含冒号"),
    "wp_other_project": ("workpaper", None, None),
    "wp_other_project_index": ("workpaper", None, None),
    "note_other_project": ("note", None, None),
    "not_uuid": ("workpaper", None, "E1"),
    "no_target": (None, None, None),
}


def _client(session: AsyncSession, user) -> AsyncClient:
    app = FastAPI()
    app.include_router(ai_content.router)

    async def _db():
        yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _by_key(world: dict, items: list[dict]) -> dict:
    ids = {str(log.id): key for key, log in world["logs"].items()}
    return {ids[it["id"]]: (it["instance_type"], it["target_label"], it["target_position"]) for it in items}


@pytest.mark.asyncio
async def test_pending_endpoint_returns_real_labels_for_mixed_list(db_session: AsyncSession, world: dict):
    """混合列表经真实路由：两种底稿 id、两种附注形态都取到名称；别的项目的 id、非 UUID、无目标都为空。"""
    with patch("app.deps.set_rls_context", new=AsyncMock(return_value=None)):
        async with _client(db_session, world["admin"]) as client:
            resp = await client.get(f"/api/projects/{world['project'].id}/ai-content/pending", params={"limit": 50})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["count"] == len(EXPECTED)
    assert _by_key(world, data["items"]) == EXPECTED
    # 非 UUID 的那条带着 SQL 片段：不进查询，表还在
    assert (await db_session.execute(sa.select(sa.func.count()).select_from(WpIndex))).scalar_one() == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("broken, survived", [("_note_labels", "workpaper"), ("_workpaper_labels", "note")])
async def test_one_kind_failing_keeps_the_other_kind(db_session, world, monkeypatch, broken, survived):
    """一类查询失败只让该类为空：原实现两条查询同一保存点，底稿那条一失败附注标签也全没了。"""

    async def boom(*_a, **_k):
        raise RuntimeError("模拟查询失败")

    monkeypatch.setattr(ai_content, broken, boom)
    items = list(world["logs"].values())
    got = await ai_content._enrich_target_labels(db_session, world["project"].id, items)
    result = _by_key(world, got)
    for key, (kind, label, position) in EXPECTED.items():
        expect_label = label if kind == survived else None
        assert result[key] == (kind, expect_label, position), key
    # 调用方会话仍可用
    assert (await db_session.execute(sa.select(sa.literal(1)))).scalar_one() == 1


@pytest.mark.parametrize(
    "cell, expected",
    [
        (None, (None, None, None)),
        ("", (None, None, None)),
        ("workpaper", ("workpaper", None, None)),
        ("workpaper:abc", ("workpaper", "abc", None)),
        ("workpaper:abc:E5", ("workpaper", "abc", "E5")),
        ("note:abc:位置:含冒号", ("note", "abc", "位置:含冒号")),
        ("note::E5", ("note", None, "E5")),
    ],
)
def test_parse_target_follows_writer_encoding(cell, expected):
    assert ai_content._parse_target(cell) == expected


def _dynamic_text_calls(tree: ast.AST) -> list[int]:
    """``text(...)`` 的 SQL 不是字符串字面量（f-string / 拼接 / format）的行号。

    认三种写法：``text(...)``、``sa.text(...)``、``from sqlalchemy import text as 别名`` 后的 ``别名(...)``。
    """
    names = {"text"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "sqlalchemy":
            names.update(alias.asname or alias.name for alias in node.names if alias.name == "text")
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        is_text = (isinstance(func, ast.Name) and func.id in names) or (
            isinstance(func, ast.Attribute) and func.attr == "text"
        )
        if not is_text:
            continue
        arg = node.args[0]
        if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
            hits.append(node.lineno)
    return sorted(hits)


def test_router_builds_no_sql_from_strings():
    """本路由不得再用 f-string / 拼接构造 SQL（原标签查询把存储的 target_cell 片段拼进了 SQL）。"""
    tree = ast.parse(_ROUTER_FILE.read_text(encoding="utf-8"))
    assert _dynamic_text_calls(tree) == []


def test_dynamic_text_detector_self_check():
    """反向自检：f-string、拼接、别名导入三种写法都要被判据抓到，字面量不算（防判据写空）。"""
    planted = ast.parse(
        'text(f"SELECT {x}")\n'
        'sa.text("SELECT " + y)\n'
        'text("SELECT 1")\n'
        "from sqlalchemy import text as _t\n"
        '_t(f"SELECT {z}")\n'
    )
    assert _dynamic_text_calls(planted) == [1, 2, 5]
