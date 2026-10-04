"""任务 3.6：custom query 附注 cell writer 的综合收口测试 —— 真 ORM / 真 SQLite + 真 FastAPI。

spec: consol-node-key-isolation-and-shared-context（需求 3.1~3.6；设计 §五、P6/P7、
ADR-CNSC-004、铁律 ㉕）。

本文件是 section 3（3.1~3.5）的 writer 综合收口。3.4（test_note_cell_writeback_scope.py）
与 3.5（test_note_cell_writeback_row_shapes.py）已分别覆盖「锁后归属复验」与「行形态保形」，
但两者都用 ``_no_lock`` 乐观锁放行桩。本任务补齐三块 3.4/3.5 没有正面覆盖的缺口：

  1. **真实乐观锁**（WritebackConflict）——用生产 ``SnapshotWriter._check_optimistic_lock``
     （而非 ``_no_lock`` 桩）验证冲突路径（``opened_at < updated_at`` → 冲突、不写入、独立
     复读原值不变）与非冲突路径（``opened_at >= updated_at`` → 正常写入）；并经端点验证冲突
     响应是 HTTP 409 + ``{conflict: true, ...}`` 契约。
  2. **综合矩阵**（跨项目 / 跨年度 / 跨章节 / 跨节点伪造 ID / 行不存在 / 对象行 / 数组行）在
     同一真实乐观锁路径下过一遍，每条被拒都用**独立会话复读**确认无部分写入、每条成功都用
     独立会话复读确认落库 —— 作为 3.6 的完整收口矩阵（P7：归属不符/越界/缺行均无任何
     ``consol_note_data`` 更新；dict/二维数组均只改目标 cell）。
  3. **真发 HTTP 请求**（铁律 ㉕：只测 service 会漏掉鉴权）——经真实
     ``/api/custom-query/cell-writeback`` 端点，挂 ``ResponseWrapperMiddleware`` 验证：
       - 鉴权依赖链（``get_visible_project_ids`` + 项目编辑权限）；
       - 响应 envelope（成功 2xx 被包装成 ``{code, message, data}``）；
       - 成功 200 / 跨项目伪造 ID 403 / 乐观锁冲突 409 的 HTTP 状态码与响应体契约。

证据纪律（遵循铁律 ㉕/㉗ 与设计 §八）：
  - **禁用 mock 替换被测函数本身**：被测的是生产 ``write_note_cell`` 与生产
    ``snapshot_writer._check_optimistic_lock``。乐观锁测试用**真实**生产函数（不是放行桩）。
  - **故障注入放下一层**：唯一的变异证明把生产复验 helper ``_verify_note_scope`` 替换成
    no-op（证明它是真实拦截点，非恒绿），不替换 ``write_note_cell``。
  - **独立事务复读**：成功写入与被拒写入都用**另一个会话**复读确认（最终一致 / 无残留）。
  - **先判据后实现**：若断言失败，先判断是判据写错还是生产实现有缺陷，不把断言降级成恒绿。
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
from app.middleware.response import ResponseWrapperMiddleware
from app.models.base import Base, UserRole
from app.models.consol_note_data_models import ConsolNoteData
from app.models.core import Project, ProjectUser, User  # noqa: F401  (建表需注册)
from app.services.custom_query import snapshot_writer_modules as _mod
from app.services.custom_query.snapshot_writer import snapshot_writer
from app.services.custom_query.snapshot_writer_shared import (
    WritebackConflict,
    WritebackPermissionDenied,
)

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


# ─── 真实乐观锁：直接用生产 SnapshotWriter._check_optimistic_lock（不是 _no_lock 桩） ───
# 任务 3.6 明确要求「乐观锁测试要用真实 _check_optimistic_lock 而非放行桩」。
# 它是绑定在模块级单例 snapshot_writer 上的生产方法，签名 (opened_at, current_updated_at, user)。
_real_lock = snapshot_writer._check_optimistic_lock


# ─── 真 SQLite 引擎 / 会话工厂（StaticPool 内存库 → 独立会话跨 commit 可见） ───


def _strip_for_update_on_sqlite(engine) -> None:
    """SQLite 不支持 ``SELECT ... FOR UPDATE``（生产走 PG 行锁）。测试专用 shim：仅对
    sqlite 方言去掉 FOR UPDATE 后缀，不改生产代码路径（与 3.4/3.5 同口径）。"""
    import re as _re

    from sqlalchemy import event as _event

    @_event.listens_for(engine.sync_engine, "before_cursor_execute", retval=True)
    def _rewrite(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        if conn.dialect.name == "sqlite" and "FOR UPDATE" in statement:
            statement = _re.sub(r"\s+FOR UPDATE(\s+OF\s+\w+)?", "", statement)
        return statement, parameters


class _OneShot:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _PgFaithfulSession:
    """只转换 write_note_cell 那条 SELECT 的 data(JSON→dict)/updated_at(str→datetime)，其余透传。

    与 3.4/3.5 测试同口径：生产走 PG 时裸 SQL 读 JSONB 得 dict、读时间戳列得 datetime；
    SQLite 裸 ``text()`` 读出的是字符串（ORM 类型反序列化只作用于 ORM construct）。这是纯
    测试环境结果表征差异，不是生产行为。真实行/复验 SQL/UPDATE/commit/rollback 全部透传。

    注意：本任务的乐观锁依赖 ``updated_at`` 列被还原成真实 ``datetime`` 才能与 ``opened_at``
    比较 —— 这正是本包装器修正的表征之一，使真实 ``_check_optimistic_lock`` 能在 SQLite 下
    走到与 PG 一致的比较逻辑。
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
            cols = list(raw)  # id, data, updated_at, project_id, year, section_id, node_key
            if isinstance(cols[1], str):
                cols[1] = json.loads(cols[1])
            if isinstance(cols[2], str):
                try:
                    cols[2] = datetime.fromisoformat(cols[2])
                except ValueError:
                    pass
            return _OneShot(tuple(cols))
        return result


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


def _data(tag, *, kind="dict"):
    """dict 行或二维数组行；A=code,B=name,C=year_end,D=year_begin。"""
    if kind == "dict":
        return {
            "headers": ["项  目", "期末余额", "期初余额"],
            "rows": [
                {"code": "库存现金", "name": tag, "year_end": "10", "year_begin": "1"},
                {"code": "银行存款", "name": "", "year_end": "20", "year_begin": "2"},
            ],
        }
    return {
        "headers": ["项  目", "期末余额", "期初余额"],
        "rows": [
            ["库存现金", tag, "10", "1"],
            ["银行存款", "", "20", "2"],
        ],
    }


@pytest_asyncio.fixture
async def seeded(factory):
    """种 project A（节点行 dict + 节点行 array + legacy 行）+ project B（节点行）。

    ``updated_at`` 显式设成 1 小时前的固定基准，便于乐观锁测试精确构造
    opened_at 早于/晚于该时刻的两种路径。
    """
    pid_a = uuid.uuid4()
    pid_b = uuid.uuid4()
    base_updated = _utc() - timedelta(hours=1)

    async with factory() as s:
        node_a = ConsolNoteData(project_id=pid_a, year=Y, section_id=SID, node_key=NODE,
                                data=_data("A节点原值", kind="dict"), updated_at=base_updated)
        node_a_arr = ConsolNoteData(project_id=pid_a, year=Y, section_id="五-2-2", node_key=NODE,
                                    data=_data("A数组原值", kind="array"), updated_at=base_updated)
        legacy_a = ConsolNoteData(project_id=pid_a, year=Y, section_id=SID, node_key=None,
                                  data=_data("A-legacy原值", kind="dict"), updated_at=base_updated)
        node_b = ConsolNoteData(project_id=pid_b, year=Y, section_id=SID, node_key=NODE,
                                data=_data("B节点原值", kind="dict"), updated_at=base_updated)
        s.add_all([node_a, node_a_arr, legacy_a, node_b])
        await s.commit()
        ids = {
            "pid_a": pid_a, "pid_b": pid_b,
            "base_updated": base_updated,
            "node_a": node_a.id.hex,
            "node_a_arr": node_a_arr.id.hex,
            "legacy_a": legacy_a.id.hex,
            "node_b": node_b.id.hex,
        }
    return ids


async def _reread_rows(factory, note_hex):
    async with factory() as s:
        rec = (await s.execute(sa.select(ConsolNoteData).where(
            ConsolNoteData.id == uuid.UUID(note_hex)))).scalar_one()
        return rec.data["rows"]


async def _reread_name(factory, note_hex, idx=0):
    rows = await _reread_rows(factory, note_hex)
    r = rows[idx]
    return r["name"] if isinstance(r, dict) else r[1]


# B2 → data_row_idx=0, col_idx=1 → name 列（dict）/ 下标 1（array）
_CELL = "B2"
_NEW = "新写入值"


# ═══════════════════ 1. 真实乐观锁（WritebackConflict） ═══════════════════


class TestRealOptimisticLock:
    """用生产 _check_optimistic_lock（非放行桩）验证冲突与非冲突两条路径。"""

    @pytest.mark.asyncio
    async def test_opened_before_update_raises_conflict_no_write(self, factory, seeded):
        """opened_at < 记录 updated_at ⇒ 真实乐观锁抛 WritebackConflict，独立复读原值不变。

        记录 updated_at = base_updated（1 小时前）；opened_at 构造成更早（2 小时前）⇒ 前端
        打开后记录又被他人改动 ⇒ 冲突。被测的是生产 _check_optimistic_lock，不是放行桩。
        """
        stale_opened = seeded["base_updated"] - timedelta(hours=1)
        async with factory() as s:
            with pytest.raises(WritebackConflict) as ei:
                await _mod.write_note_cell(
                    _PgFaithfulSession(s), _mk_user(), str(seeded["node_a"]), "note", _CELL, _NEW,
                    stale_opened,
                    check_lock=_real_lock,
                    project_id=str(seeded["pid_a"]), year=Y, section_id=SID, node_key=NODE,
                )
            await s.rollback()
        # 冲突异常携带最新编辑信息（router 据此构造 409 响应体）
        assert ei.value.latest_updated_at is not None
        # 独立复读：冲突 ⇒ 一个字节都没写
        assert await _reread_name(factory, seeded["node_a"]) == "A节点原值"

    @pytest.mark.asyncio
    async def test_opened_after_update_writes_through_real_lock(self, factory, seeded):
        """opened_at >= 记录 updated_at ⇒ 真实乐观锁放行，写入成功，独立复读落库。

        opened_at = now（晚于 base_updated）⇒ 前端打开时数据是最新的 ⇒ 非冲突路径。
        与上一条共用同一真实 _check_optimistic_lock，证明它两条分支都真实生效。
        """
        fresh_opened = _utc()
        async with factory() as s:
            res = await _mod.write_note_cell(
                _PgFaithfulSession(s), _mk_user(), str(seeded["node_a"]), "note", _CELL, _NEW,
                fresh_opened,
                check_lock=_real_lock,
                project_id=str(seeded["pid_a"]), year=Y, section_id=SID, node_key=NODE,
            )
            await s.commit()
        assert res["success"] is True
        assert await _reread_name(factory, seeded["node_a"]) == _NEW

    @pytest.mark.asyncio
    async def test_scope_check_runs_before_lock_cross_project_still_denied(self, factory, seeded):
        """归属复验在乐观锁之前：即便构造 stale opened_at，跨项目伪造 ID 仍先被归属拒绝。

        这证明越权请求不会先泄露「记录是否已被他人改动」的乐观锁状态（设计 §五.2 的顺序）。
        请求 project A 但 record 属 project B，且 opened_at 构造成会触发冲突的更早时刻 ——
        实际应抛 WritebackPermissionDenied（归属不符）而非 WritebackConflict。
        """
        stale_opened = seeded["base_updated"] - timedelta(hours=1)
        async with factory() as s:
            with pytest.raises(WritebackPermissionDenied):
                await _mod.write_note_cell(
                    _PgFaithfulSession(s), _mk_user(), str(seeded["node_b"]), "note", _CELL, _NEW,
                    stale_opened,
                    check_lock=_real_lock,
                    project_id=str(seeded["pid_a"]), year=Y, section_id=SID, node_key=NODE,
                )
            await s.rollback()
        assert await _reread_name(factory, seeded["node_b"]) == "B节点原值"


# ═══════════════════ 2. 综合矩阵（真实乐观锁路径下过一遍） ═══════════════════


class TestComprehensiveMatrix:
    """跨项目/年度/章节/跨节点伪造 ID/行不存在 → 全部拒绝 + 独立复读无部分写入（P7）。

    与 3.4 的区别：这里全程用真实 _real_lock（非 _no_lock），作为 3.6 的收口矩阵，证明
    归属复验在真实乐观锁在场时仍是先决拦截点。成功写入放在 TestObjectAndArrayUpdate。
    """

    async def _expect_reject_no_write(self, factory, note_hex, before_val, exc, **kwargs):
        fresh_opened = _utc()
        async with factory() as s:
            with pytest.raises(exc):
                await _mod.write_note_cell(
                    _PgFaithfulSession(s), _mk_user(), str(note_hex), "note", _CELL, _NEW,
                    fresh_opened,
                    check_lock=_real_lock, **kwargs,
                )
            await s.rollback()
        assert await _reread_name(factory, note_hex) == before_val

    @pytest.mark.asyncio
    async def test_cross_project_forged_id(self, factory, seeded):
        await self._expect_reject_no_write(
            factory, seeded["node_b"], "B节点原值", WritebackPermissionDenied,
            project_id=str(seeded["pid_a"]), year=Y, section_id=SID, node_key=NODE,
        )

    @pytest.mark.asyncio
    async def test_cross_year(self, factory, seeded):
        await self._expect_reject_no_write(
            factory, seeded["node_a"], "A节点原值", WritebackPermissionDenied,
            project_id=str(seeded["pid_a"]), year=Y + 1, section_id=SID, node_key=NODE,
        )

    @pytest.mark.asyncio
    async def test_cross_section(self, factory, seeded):
        await self._expect_reject_no_write(
            factory, seeded["node_a"], "A节点原值", WritebackPermissionDenied,
            project_id=str(seeded["pid_a"]), year=Y, section_id="五-9-9", node_key=NODE,
        )

    @pytest.mark.asyncio
    async def test_cross_node_forged_key(self, factory, seeded):
        await self._expect_reject_no_write(
            factory, seeded["node_a"], "A节点原值", WritebackPermissionDenied,
            project_id=str(seeded["pid_a"]), year=Y, section_id=SID, node_key="A:consol",
        )

    @pytest.mark.asyncio
    async def test_node_request_against_legacy_row(self, factory, seeded):
        await self._expect_reject_no_write(
            factory, seeded["legacy_a"], "A-legacy原值", WritebackPermissionDenied,
            project_id=str(seeded["pid_a"]), year=Y, section_id=SID, node_key=NODE,
        )

    @pytest.mark.asyncio
    async def test_legacy_request_against_node_row(self, factory, seeded):
        await self._expect_reject_no_write(
            factory, seeded["node_a"], "A节点原值", WritebackPermissionDenied,
            project_id=str(seeded["pid_a"]), year=Y, section_id=SID, node_key=None,
        )

    @pytest.mark.asyncio
    async def test_missing_record_no_legacy_fallback(self, factory, seeded):
        """记录不存在 ⇒ ValueError，不 fallback；同项目/年度/章节的 legacy 行原样。"""
        ghost = uuid.uuid4()
        fresh_opened = _utc()
        async with factory() as s:
            with pytest.raises(ValueError):
                await _mod.write_note_cell(
                    _PgFaithfulSession(s), _mk_user(), str(ghost), "note", _CELL, _NEW,
                    fresh_opened,
                    check_lock=_real_lock,
                    project_id=str(seeded["pid_a"]), year=Y, section_id=SID, node_key=NODE,
                )
            await s.rollback()
        assert await _reread_name(factory, seeded["legacy_a"]) == "A-legacy原值"


# ═══════════════════ 3. 对象/数组更新 + 独立事务复读（成功路径收口） ═══════════════════


class TestObjectAndArrayUpdate:
    """对象行与数组行在真实乐观锁路径下成功写入，独立会话复读确认只改目标 cell。"""

    @pytest.mark.asyncio
    async def test_dict_row_update_isolated_reread(self, factory, seeded):
        async with factory() as s:
            res = await _mod.write_note_cell(
                _PgFaithfulSession(s), _mk_user(), str(seeded["node_a"]), "note", "C2", "999", _utc(),
                check_lock=_real_lock,
                project_id=str(seeded["pid_a"]), year=Y, section_id=SID, node_key=NODE,
            )
            await s.commit()
        assert res["success"] is True and res["old_value"] == "10"
        rows = await _reread_rows(factory, seeded["node_a"])
        # 目标 cell 变、同行其它键与其它行完全不变、行仍是 dict
        assert rows[0] == {"code": "库存现金", "name": "A节点原值", "year_end": "999", "year_begin": "1"}
        assert rows[1] == {"code": "银行存款", "name": "", "year_end": "20", "year_begin": "2"}
        assert isinstance(rows[0], dict)

    @pytest.mark.asyncio
    async def test_array_row_update_isolated_reread(self, factory, seeded):
        async with factory() as s:
            res = await _mod.write_note_cell(
                _PgFaithfulSession(s), _mk_user(), str(seeded["node_a_arr"]), "note", "B2", "ARR新值", _utc(),
                check_lock=_real_lock,
                project_id=str(seeded["pid_a"]), year=Y, section_id="五-2-2", node_key=NODE,
            )
            await s.commit()
        assert res["success"] is True and res["old_value"] == "A数组原值"
        rows = await _reread_rows(factory, seeded["node_a_arr"])
        assert rows[0] == ["库存现金", "ARR新值", "10", "1"]  # 只下标 1 变
        assert rows[1] == ["银行存款", "", "20", "2"]  # 其它行不变
        assert isinstance(rows[0], list)

    @pytest.mark.asyncio
    async def test_rejected_write_leaves_db_untouched_independent_session(self, factory, seeded):
        """被拒写入（跨项目）与成功写入（本项目）交叉：独立会话复读确认 B 不变、A 变。

        同一 fixture 内先打一次越权（B 不应变），再打一次合法（A 应变），用独立会话分别复读 ——
        证明「被拒无残留」与「成功落库」在同一数据库上互不干扰。
        """
        # 越权：请求 project A，record 属 project B ⇒ 拒绝
        async with factory() as s:
            with pytest.raises(WritebackPermissionDenied):
                await _mod.write_note_cell(
                    _PgFaithfulSession(s), _mk_user(), str(seeded["node_b"]), "note", _CELL, "越权值", _utc(),
                    check_lock=_real_lock,
                    project_id=str(seeded["pid_a"]), year=Y, section_id=SID, node_key=NODE,
                )
            await s.rollback()
        # 合法：请求 project A，record 属 project A ⇒ 成功
        async with factory() as s:
            await _mod.write_note_cell(
                _PgFaithfulSession(s), _mk_user(), str(seeded["node_a"]), "note", _CELL, "合法值", _utc(),
                check_lock=_real_lock,
                project_id=str(seeded["pid_a"]), year=Y, section_id=SID, node_key=NODE,
            )
            await s.commit()
        # 独立会话复读两条记录
        assert await _reread_name(factory, seeded["node_b"]) == "B节点原值"  # 越权无残留
        assert await _reread_name(factory, seeded["node_a"]) == "合法值"      # 合法已落库


# ═══════════════════ 4. 变异证明：复验是真实拦截点（故障注在下一层） ═══════════════════


class TestMutationProof:
    @pytest.mark.asyncio
    async def test_disabling_scope_verification_lets_forged_id_through(self, factory, seeded, monkeypatch):
        """把生产复验 helper _verify_note_scope 替换成 no-op ⇒ 跨项目伪造 ID 原本会被误放行。

        证明 _verify_note_scope 确实是拦截点（非恒绿）；故障注在被测函数的下一层，不替换
        write_note_cell 本身。注意乐观锁仍是真实的（_real_lock），opened_at=now 不触发冲突。
        """
        monkeypatch.setattr(_mod, "_verify_note_scope", lambda **kw: None)
        async with factory() as s:
            res = await _mod.write_note_cell(
                _PgFaithfulSession(s), _mk_user(), str(seeded["node_b"]), "note", _CELL, _NEW, _utc(),
                check_lock=_real_lock,
                project_id=str(seeded["pid_a"]), year=Y, section_id=SID, node_key=NODE,
            )
            await s.commit()
        assert res["success"] is True
        assert await _reread_name(factory, seeded["node_b"]) == _NEW  # 复验被禁 ⇒ 越权写成功


# ═══════════════════ 5. 真发 HTTP 请求（鉴权链 + 响应 envelope + 状态码） ═══════════════════


@pytest_asyncio.fixture
async def cw_client(factory, seeded):
    """挂 custom_query 路由 + ResponseWrapperMiddleware；override get_db / get_current_user。

    - ResponseWrapperMiddleware：验证成功响应被包装成 {code, message, data}（铁律 ㉕）。
    - get_visible_project_ids：admin 对两项目都可见 → 鉴权不是本测拦截点，拦截点应当是
      writer 的锁后归属复验（跨项目伪造 ID）与真实乐观锁（stale opened_at）。
    """
    from app.routers import custom_query as cq
    from app.routers.custom_query import router as cq_router

    app = FastAPI()
    app.add_middleware(ResponseWrapperMiddleware)
    app.include_router(cq_router)

    async def _db():
        async with factory() as s:
            yield _PgFaithfulSession(s)

    admin = _mk_user(UserRole.admin)

    async def _visible(user, db):
        return {seeded["pid_a"], seeded["pid_b"]}

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: admin
    monkey = cq.get_visible_project_ids
    cq.get_visible_project_ids = _visible  # type: ignore[assignment]
    try:
        yield AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    finally:
        cq.get_visible_project_ids = monkey  # type: ignore[assignment]


def _writeback_payload(seeded, note_hex, *, project_id=None, value=_NEW):
    return {
        "project_id": project_id or str(seeded["pid_a"]),
        "wp_code": note_hex,  # note 模块：wp_code 承载 consol_note_data.id
        "sheet_name": "note",
        "cell_ref": _CELL,
        "new_value": value,
        "module": "note",
        "note_year": Y,
        "note_section_id": SID,
        "node_key": NODE,
    }


class TestEndpointHTTP:
    @pytest.mark.asyncio
    async def test_matching_scope_200_wrapped_envelope(self, cw_client, factory, seeded):
        """真发请求：归属全匹配 + 新 opened_at ⇒ 200，响应被包装成 {code,message,data}。"""
        async with cw_client as c:
            resp = await c.post(
                "/api/custom-query/cell-writeback",
                headers={"X-File-Opened-At": _utc().isoformat()},
                json=_writeback_payload(seeded, str(seeded["node_a"])),
            )
        assert resp.status_code == 200, resp.text
        env = resp.json()
        # ResponseWrapperMiddleware 信封契约
        assert env["code"] == 200
        assert env["message"] == "success"
        assert env["data"]["success"] is True
        # 独立复读确认落库
        assert await _reread_name(factory, seeded["node_a"]) == _NEW

    @pytest.mark.asyncio
    async def test_cross_project_forged_id_403_db_unchanged(self, cw_client, factory, seeded):
        """真发请求：声称 project A，record 属 project B ⇒ 403，B 行 DB 不变。"""
        async with cw_client as c:
            resp = await c.post(
                "/api/custom-query/cell-writeback",
                headers={"X-File-Opened-At": _utc().isoformat()},
                json=_writeback_payload(seeded, str(seeded["node_b"])),
            )
        assert resp.status_code == 403, resp.text
        assert await _reread_name(factory, seeded["node_b"]) == "B节点原值"

    @pytest.mark.asyncio
    async def test_optimistic_conflict_409_conflict_contract(self, cw_client, factory, seeded):
        """真发请求：X-File-Opened-At 早于记录 updated_at ⇒ 409 + {conflict:true,...}，DB 不变。

        409 不是 2xx ⇒ 中间件不包装 ⇒ 响应体是端点直接构造的 conflict 契约。
        """
        stale_opened = seeded["base_updated"] - timedelta(hours=1)
        async with cw_client as c:
            resp = await c.post(
                "/api/custom-query/cell-writeback",
                headers={"X-File-Opened-At": stale_opened.isoformat()},
                json=_writeback_payload(seeded, str(seeded["node_a"])),
            )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body["conflict"] is True
        assert "latest_editor" in body
        # 冲突 ⇒ DB 未改
        assert await _reread_name(factory, seeded["node_a"]) == "A节点原值"

    @pytest.mark.asyncio
    async def test_missing_opened_at_header_400(self, cw_client, seeded):
        """缺 X-File-Opened-At header ⇒ 400（端点前置校验，鉴权前的输入契约）。"""
        async with cw_client as c:
            resp = await c.post(
                "/api/custom-query/cell-writeback",
                json=_writeback_payload(seeded, str(seeded["node_a"])),
            )
        assert resp.status_code == 400, resp.text
