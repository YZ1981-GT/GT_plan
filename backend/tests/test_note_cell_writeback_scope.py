"""任务 3.4：custom query 附注 cell writer 的锁后归属复验 —— 真 ORM / 真 SQLite 行测试。

spec: consol-node-key-isolation-and-shared-context（需求 3.3/3.4/3.6；设计 §五.2、P7、
ADR-CNSC-004）。

被测的是生产函数 ``snapshot_writer_modules.write_note_cell``（禁用 mock 替换被测函数本身）。
附注记录的归属元组为 ``(project_id, year, section_id, node_key)``；``wp_id`` 是可猜测的记录
ID，不是授权边界。writer 在 ``SELECT ... FOR UPDATE`` 锁定记录后必须逐项复验请求携带的归属
字段与锁定行实际值是否一致：

  - 任一字段不符 → ``WritebackPermissionDenied``（router 转 403）→ 回滚，``consol_note_data``
    一行不改（R3.3/R3.4/R3.6）。
  - 记录不存在 → ``ValueError``（router 转 400）→ 不写入、**不** fallback 到 legacy NULL 行。
  - 请求携带节点键、而记录是 legacy NULL（或反之）→ 不匹配拒绝，不把节点写回重定向到 legacy
    （ADR-CNSC-004）。

证据纪律：
  - 「独立复读」用 **另一个会话** 查 DB，证明被拒绝的请求没有留下任何部分写入。
  - 变异证明：把生产复验函数临时替换成 no-op，证明跨项目伪造 ID 原本会被**误放行**（即复验
    确实是拦截点，不是恒绿断言）。故障注入放在被测函数的**下一层**（复验 helper），不替换
    ``write_note_cell`` 本身。
  - 端点级：真发 FastAPI 请求过 ``/api/custom-query/cell-writeback``，验证鉴权依赖链 + 响应
    envelope + 跨项目伪造 note id 被拒 403 且 DB 不变（铁律 ㉕：只测 service 会漏掉鉴权）。
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401  注册全部模型 + SQLite 方言补丁
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, UserRole
from app.models.consol_note_data_models import ConsolNoteData
from app.models.core import Project, ProjectUser, User  # noqa: F401  (建表需注册)
from app.services.custom_query import snapshot_writer_modules as _mod
from app.services.custom_query.snapshot_writer_shared import WritebackPermissionDenied

Y = 2025
SID = "五-1-1"
NODE = "G:consol"


def _utc():
    return datetime.now(timezone.utc)


def _mk_user(role=UserRole.admin):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.username = "tester"
    u.role = role
    return u


def _no_lock(opened_at, current_updated_at, user):
    """乐观锁放行桩：本测聚焦归属复验，乐观锁语义不在范围内。"""
    return None


# ─── 真 SQLite 引擎 / 会话工厂 ──────────────────────────────────────────────
# StaticPool 内存库：同一连接跨会话可见 commit 后数据 → 「独立复读」用新会话验证无部分写入。


def _strip_for_update_on_sqlite(engine) -> None:
    """SQLite 不支持 ``SELECT ... FOR UPDATE`` 语法（生产走 PG 行锁）。

    测试只验锁后归属复验逻辑，不验真实行锁语义（后者需 PG 环境）。注册一个仅对 sqlite
    方言生效的 ``before_cursor_execute``，把裸 SQL 里的 ``FOR UPDATE`` 去掉 —— 这是 **测试
    专用 shim**，不改生产代码路径。
    """
    import re as _re

    from sqlalchemy import event as _event

    sync_engine = engine.sync_engine

    @_event.listens_for(sync_engine, "before_cursor_execute", retval=True)
    def _rewrite(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        if conn.dialect.name == "sqlite" and "FOR UPDATE" in statement:
            statement = _re.sub(r"\s+FOR UPDATE(\s+OF\s+\w+)?", "", statement)
        return statement, parameters


@pytest_asyncio.fixture
async def factory():
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    _strip_for_update_on_sqlite(engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded(factory):
    """种 1 条节点行 + 1 条 legacy 行 + 另一项目的节点行；返回各自 id 与 project_id。"""
    pid_a = uuid.uuid4()
    pid_b = uuid.uuid4()

    # dict 行形态（3.3 writer 当前支持的持久化形态；二维数组行属 Task 3.5 范围）。
    # 列键取 _NOTE_COLUMNS：A=code, B=name, C=year_end, D=year_begin, E=formula。
    def _data(tag):
        return {
            "headers": ["项  目", "期末余额", "期初余额"],
            "rows": [
                {"code": "库存现金", "name": tag, "year_end": "", "year_begin": ""},
                {"code": "银行存款", "name": "", "year_end": "", "year_begin": ""},
            ],
        }

    async with factory() as s:
        node_a = ConsolNoteData(project_id=pid_a, year=Y, section_id=SID, node_key=NODE,
                                data=_data("A节点原值"), updated_at=_utc())
        legacy_a = ConsolNoteData(project_id=pid_a, year=Y, section_id=SID, node_key=None,
                                  data=_data("A-legacy原值"), updated_at=_utc())
        node_b = ConsolNoteData(project_id=pid_b, year=Y, section_id=SID, node_key=NODE,
                                data=_data("B节点原值"), updated_at=_utc())
        s.add_all([node_a, legacy_a, node_b])
        await s.commit()
        # 记录 ID 以 32-hex 字符串形态回传：生产走 PG 原生 UUID，带连字符的 str(uuid) 直接
        # 命中；SQLite 把 Uuid 列存为 32-hex（无连字符），裸 SQL ``WHERE id = :nid`` 只匹配
        # 该形态。统一取 ``.hex`` 让裸 SQL 查询在 SQLite 下也能命中真实行（纯测试环境表征
        # 差异，不是生产问题 —— project_id 复验已用 UUID 归一，与表征无关）。
        ids = {
            "pid_a": pid_a, "pid_b": pid_b,
            "node_a": node_a.id.hex, "legacy_a": legacy_a.id.hex, "node_b": node_b.id.hex,
        }
    return ids


async def _reread_cell(factory, note_hex):
    """独立会话复读 rows[0]["name"]（库存现金·期末余额），证明有无写入。"""
    async with factory() as s:
        rec = (await s.execute(sa.select(ConsolNoteData).where(
            ConsolNoteData.id == uuid.UUID(note_hex)))).scalar_one()
        return rec.data["rows"][0]["name"]


class _PgFaithfulSession:
    """包装真实 SQLite 会话，让裸 ``text()`` 读 ``consol_note_data`` 的结果**在表征上与 PG 一致**。

    生产走 PG：裸 SQL 读 JSONB 列（asyncpg）直接得 ``dict``、时间戳列得 ``datetime``。SQLite 的
    ``JSON``/``DateTime`` 列经裸 ``text()`` 读出的是 **字符串**（ORM 的类型反序列化只在走 ORM
    construct 时生效，不作用于裸 SQL）。这是纯测试环境的结果表征差异，不是生产行为。

    本包装器**只**转换 ``write_note_cell`` 的那条 SELECT 的结果行（``data`` → json.loads、
    ``updated_at`` → datetime），其余一切（真实行、归属复验 SQL、UPDATE、commit/rollback）
    全部透传给真实会话 —— 行是真的、复验是真的、写入是真的，仅修正读出表征。
    """

    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name):
        return getattr(self._inner, name)

    async def execute(self, statement, *args, **kwargs):
        result = await self._inner.execute(statement, *args, **kwargs)
        sql = str(getattr(statement, "text", statement))
        if "FROM consol_note_data" in sql and "SELECT" in sql and "data" in sql:
            raw = result.first()
            if raw is None:
                return _OneShot(None)
            cols = list(raw)
            # 列顺序：id, data, updated_at, project_id, year, section_id, node_key
            if isinstance(cols[1], str):
                cols[1] = json.loads(cols[1])
            if isinstance(cols[2], str):
                try:
                    cols[2] = datetime.fromisoformat(cols[2])
                except ValueError:
                    pass
            return _OneShot(tuple(cols))
        return result


class _OneShot:
    """最小 Result 替身：只需 ``.first()`` 返回预处理过的行。"""

    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


# 虚拟 sheet 第 1 行是表头，第 2 行起为数据（writer: data_row_idx = row_idx - 1）。
# cell_ref B2 → row_idx=1 → data_row_idx=0；col_idx=1 → _NOTE_COLUMNS[1]="name" ⇒ 写 rows[0]["name"]
_CELL = "B2"
_NEW = "新写入值"


# ─────────────────────────── happy path（归属全匹配 → 写入成功） ───────────────────────────


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_matching_scope_writes(self, factory, seeded):
        """归属元组全匹配 ⇒ 写入该节点行；独立复读确认落库。"""
        async with factory() as s:
            res = await _mod.write_note_cell(
                _PgFaithfulSession(s), _mk_user(), str(seeded["node_a"]), "note", _CELL, _NEW, _utc(),
                check_lock=_no_lock,
                project_id=str(seeded["pid_a"]), year=Y, section_id=SID, node_key=NODE,
            )
            await s.commit()
        assert res["success"] is True
        assert res["record_scope"]["node_key"] == NODE
        assert await _reread_cell(factory, seeded["node_a"]) == _NEW

    @pytest.mark.asyncio
    async def test_legacy_request_matches_legacy_row(self, factory, seeded):
        """旧调用（node_key=None）命中 legacy NULL 行 ⇒ 写入成功。"""
        async with factory() as s:
            res = await _mod.write_note_cell(
                _PgFaithfulSession(s), _mk_user(), str(seeded["legacy_a"]), "note", _CELL, _NEW, _utc(),
                check_lock=_no_lock,
                project_id=str(seeded["pid_a"]), year=Y, section_id=SID, node_key=None,
            )
            await s.commit()
        assert res["success"] is True
        assert res["record_scope"]["node_key"] is None
        assert await _reread_cell(factory, seeded["legacy_a"]) == _NEW


# ─────────────────────────── 归属不匹配 → 拒绝 + 回滚无部分写入（P7、R3.6） ───────────────────────────


class TestScopeMismatchRejected:
    async def _expect_reject_no_write(self, factory, note_id, before_val, **kwargs):
        async with factory() as s:
            with pytest.raises(WritebackPermissionDenied):
                await _mod.write_note_cell(
                    s, _mk_user(), str(note_id), "note", _CELL, _NEW, _utc(),
                    check_lock=_no_lock, **kwargs,
                )
            await s.rollback()  # router 对 WritebackPermissionDenied 的处置
        # 独立复读：被拒绝的记录原值不变
        assert await _reread_cell(factory, note_id) == before_val

    @pytest.mark.asyncio
    async def test_cross_project_forged_id_rejected(self, factory, seeded):
        """跨项目伪造 ID：请求 project A，但 record id 实际属于 project B ⇒ 403 拒绝，B 不变。"""
        await self._expect_reject_no_write(
            factory, seeded["node_b"], "B节点原值",
            project_id=str(seeded["pid_a"]), year=Y, section_id=SID, node_key=NODE,
        )

    @pytest.mark.asyncio
    async def test_cross_year_rejected(self, factory, seeded):
        await self._expect_reject_no_write(
            factory, seeded["node_a"], "A节点原值",
            project_id=str(seeded["pid_a"]), year=Y + 1, section_id=SID, node_key=NODE,
        )

    @pytest.mark.asyncio
    async def test_cross_section_rejected(self, factory, seeded):
        await self._expect_reject_no_write(
            factory, seeded["node_a"], "A节点原值",
            project_id=str(seeded["pid_a"]), year=Y, section_id="五-9-9", node_key=NODE,
        )

    @pytest.mark.asyncio
    async def test_cross_node_forged_key_rejected(self, factory, seeded):
        """跨节点伪造 node_key：record 是 G:consol，请求谎称 A:consol ⇒ 拒绝，不串写。"""
        await self._expect_reject_no_write(
            factory, seeded["node_a"], "A节点原值",
            project_id=str(seeded["pid_a"]), year=Y, section_id=SID, node_key="A:consol",
        )

    @pytest.mark.asyncio
    async def test_node_request_against_legacy_row_rejected(self, factory, seeded):
        """请求携带节点键、record 却是 legacy NULL 行 ⇒ 拒绝，不把节点写回重定向到 legacy。"""
        await self._expect_reject_no_write(
            factory, seeded["legacy_a"], "A-legacy原值",
            project_id=str(seeded["pid_a"]), year=Y, section_id=SID, node_key=NODE,
        )

    @pytest.mark.asyncio
    async def test_legacy_request_against_node_row_rejected(self, factory, seeded):
        """旧调用（node_key=None）却指向节点行 ⇒ 拒绝（node_key 不匹配）。"""
        await self._expect_reject_no_write(
            factory, seeded["node_a"], "A节点原值",
            project_id=str(seeded["pid_a"]), year=Y, section_id=SID, node_key=None,
        )

    @pytest.mark.asyncio
    async def test_missing_record_rejected_no_legacy_fallback(self, factory, seeded):
        """记录 ID 不存在 ⇒ ValueError 拒绝，不 fallback 到 legacy，legacy 行原样。"""
        ghost = uuid.uuid4()
        async with factory() as s:
            with pytest.raises(ValueError):
                await _mod.write_note_cell(
                    s, _mk_user(), str(ghost), "note", _CELL, _NEW, _utc(),
                    check_lock=_no_lock,
                    project_id=str(seeded["pid_a"]), year=Y, section_id=SID, node_key=NODE,
                )
            await s.rollback()
        # 不 fallback：同项目/年度/章节的 legacy 行完全未被改写
        assert await _reread_cell(factory, seeded["legacy_a"]) == "A-legacy原值"


# ─────────────────────────── 变异证明：复验是真实拦截点，非恒绿 ───────────────────────────


class TestMutationProof:
    @pytest.mark.asyncio
    async def test_disabling_verification_lets_forged_id_through(self, factory, seeded, monkeypatch):
        """把生产复验 helper 替换成 no-op ⇒ 跨项目伪造 ID 原本会被误放行并写入 B 行。

        这证明 ``_verify_note_scope`` 确实是拦截点：若复验不生效，跨项目越权写就会成功。
        故障注在被测函数的**下一层**（复验 helper），不替换 ``write_note_cell`` 本身。
        """
        monkeypatch.setattr(_mod, "_verify_note_scope", lambda **kw: None)
        async with factory() as s:
            res = await _mod.write_note_cell(
                _PgFaithfulSession(s), _mk_user(), str(seeded["node_b"]), "note", _CELL, _NEW, _utc(),
                check_lock=_no_lock,
                project_id=str(seeded["pid_a"]), year=Y, section_id=SID, node_key=NODE,
            )
            await s.commit()
        # 复验被禁用 ⇒ 越权写成功（证明复验是唯一拦截点；生产路径下 TestScopeMismatch 已证被拦）
        assert res["success"] is True
        assert await _reread_cell(factory, seeded["node_b"]) == _NEW


# ─────────────────────────── 端点级 IDOR（真 FastAPI 请求 + 鉴权依赖链） ───────────────────────────


@pytest_asyncio.fixture
async def cw_client(factory, seeded):
    """挂 custom_query 路由；override get_db / get_current_user / get_visible_project_ids。

    admin 用户对两个项目都可见（鉴权不是本测拦截点）——拦截点应当是 writer 的锁后归属复验。
    """
    from app.routers import custom_query as cq
    from app.routers.custom_query import router as cq_router

    app = FastAPI()
    app.include_router(cq_router)

    # 单一共享会话：端点内 commit/rollback 后，独立复读用同一内存库另开会话。
    sess_holder: dict = {}

    async def _db():
        async with factory() as s:
            sess_holder["s"] = s
            # PG-faithful 包装：仅修正裸 SQL 读 consol_note_data 的 JSON/datetime 表征，
            # 其余（鉴权查询、UPDATE、commit/rollback、outbox）全透传真实会话。
            yield _PgFaithfulSession(s)

    admin = _mk_user(UserRole.admin)

    async def _visible(user, db):
        return {seeded["pid_a"], seeded["pid_b"]}

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: admin
    # 端点在本模块命名空间引用 get_visible_project_ids（铁律：patch 本模块名）
    monkey = cq.get_visible_project_ids
    cq.get_visible_project_ids = _visible  # type: ignore[assignment]
    try:
        yield AsyncClient(transport=ASGITransport(app=app), base_url="http://test"), admin
    finally:
        cq.get_visible_project_ids = monkey  # type: ignore[assignment]


class TestEndpointIDOR:
    @pytest.mark.asyncio
    async def test_cross_project_note_writeback_rejected_403_db_unchanged(self, cw_client, factory, seeded):
        """真发请求：声称 project A，但 note record id 属 project B ⇒ 403，B 行 DB 不变。"""
        client, _admin = cw_client
        async with client as c:
            resp = await c.post(
                "/api/custom-query/cell-writeback",
                headers={"X-File-Opened-At": _utc().isoformat()},
                json={
                    "project_id": str(seeded["pid_a"]),
                    "wp_code": str(seeded["node_b"]),  # note 模块：wp_code 承载 consol_note_data.id
                    "sheet_name": "note",
                    "cell_ref": _CELL,
                    "new_value": _NEW,
                    "module": "note",
                    "note_year": Y,
                    "note_section_id": SID,
                    "node_key": NODE,
                },
            )
        assert resp.status_code == 403, resp.text
        assert await _reread_cell(factory, seeded["node_b"]) == "B节点原值"

    @pytest.mark.asyncio
    async def test_matching_scope_writeback_succeeds_200(self, cw_client, factory, seeded):
        """真发请求：归属全匹配 ⇒ 200，节点 A 行写入。"""
        client, _admin = cw_client
        async with client as c:
            resp = await c.post(
                "/api/custom-query/cell-writeback",
                headers={"X-File-Opened-At": _utc().isoformat()},
                json={
                    "project_id": str(seeded["pid_a"]),
                    "wp_code": str(seeded["node_a"]),
                    "sheet_name": "note",
                    "cell_ref": _CELL,
                    "new_value": _NEW,
                    "module": "note",
                    "note_year": Y,
                    "note_section_id": SID,
                    "node_key": NODE,
                },
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["success"] is True
        assert await _reread_cell(factory, seeded["node_a"]) == _NEW
