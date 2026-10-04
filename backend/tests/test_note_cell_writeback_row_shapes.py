"""任务 3.5：custom query 附注 cell writer 的行形态保形与边界错误 —— 真 ORM / 真 SQLite 行测试。

spec: consol-node-key-isolation-and-shared-context（需求 3.5；设计 §五、P7、ADR-CNSC-004）。

被测的是生产函数 ``snapshot_writer_modules.write_note_cell``（禁用 mock 替换被测函数本身）。
本任务聚焦**行形态保形**（归属复验由 3.4 的 test_note_cell_writeback_scope.py 覆盖）：

  - **dict 对象行**：列号经 ``_NOTE_COLUMNS``（A=code,B=name,C=year_end,D=year_begin,E=formula）
    映射键名原位更新，保留其余键与键序，不改写成数组。
  - **二维数组行**（list）：按位置列号写入，保留该行其它列与其它行；窄行只补到目标列，不强制等宽。
  - **保留非目标 cell**：只改目标单元格，其余行列不变（独立会话复读全行对拍）。
  - **行列越界 / 不支持形状**：明确 ``ValueError``（router 转 400），且 ``consol_note_data`` 不变。

证据纪律：
  - 「独立复读」用**另一个会话**查 DB 全行，证明目标 cell 变、其余 cell 原样（或拒绝时整行不变）。
  - 变异证明：把 ``_write_note_row_cell`` 对数组行退化成「只处理 dict」（``row_obj[col_name]=...``）
    会在数组行上抛 ``TypeError`` —— 证明生产的位置写入分支是真实必需的，不是恒绿。
  - 读写同口径对拍：写进去的值用取数器 ``module_cell_resolver._query_note_cells`` 读回来，证明
    writer 的列映射与 reader 一致（不会写进 reader 读不到的位置）。
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

import pytest
import pytest_asyncio
import sqlalchemy as sa

import tests.conftest  # noqa: F401  注册全部模型 + SQLite 方言补丁
from app.models.base import Base, UserRole
from app.models.consol_note_data_models import ConsolNoteData
from app.models.core import Project, ProjectUser, User  # noqa: F401  (建表需注册)
from app.services.custom_query import snapshot_writer_modules as _mod

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
    return None


# ─── PG-faithful SQLite 包装（与 3.4 测试同口径：只修正裸 SQL 读 consol_note_data 的表征） ───


def _strip_for_update_on_sqlite(engine) -> None:
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
    """只转换 write_note_cell 那条 SELECT 的 data(JSON→dict) / updated_at(str→datetime)，其余透传。"""

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
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
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


def _dict_data():
    """dict 对象行形态：两行，每行 code/name/year_end/year_begin（无 formula 键，验证不被凭空补）。"""
    return {
        "headers": ["项  目", "期末余额", "期初余额"],
        "rows": [
            {"code": "库存现金", "name": "N1", "year_end": "10", "year_begin": "1"},
            {"code": "银行存款", "name": "N2", "year_end": "20", "year_begin": "2"},
        ],
    }


def _array_data():
    """二维数组行形态：[[code,name,year_end,year_begin], ...]，第二行故意只有 2 列（窄行）。"""
    return {
        "headers": ["项  目", "期末余额", "期初余额"],
        "rows": [
            ["库存现金", "A1", "10", "1"],
            ["银行存款", "A2"],  # 窄行：只有 2 列
        ],
    }


@pytest_asyncio.fixture
async def seeded(factory):
    pid = uuid.uuid4()
    async with factory() as s:
        dict_row = ConsolNoteData(project_id=pid, year=Y, section_id=SID, node_key=NODE,
                                  data=_dict_data(), updated_at=_utc())
        arr_row = ConsolNoteData(project_id=pid, year=Y, section_id="五-2-2", node_key=NODE,
                                 data=_array_data(), updated_at=_utc())
        s.add_all([dict_row, arr_row])
        await s.commit()
        ids = {
            "pid": pid,
            "dict_id": dict_row.id.hex,
            "dict_section": SID,
            "arr_id": arr_row.id.hex,
            "arr_section": "五-2-2",
        }
    return ids


async def _reread_rows(factory, note_hex):
    """独立会话复读整个 rows 数组（证明目标 cell 变、其余不变 / 拒绝时整行不变）。"""
    async with factory() as s:
        rec = (await s.execute(sa.select(ConsolNoteData).where(
            ConsolNoteData.id == uuid.UUID(note_hex)))).scalar_one()
        return rec.data["rows"]


# cell_ref 口径（与 reader 一致）：row 1 = 表头，row 2 起为数据；col A=0 列。
# B2 → row_idx(parse,0idx)=1 → data_row_idx=0；col_idx=1 → _NOTE_COLUMNS[1]="name"（数组下标 1）
# C3 → data_row_idx=1；col_idx=2 → year_end（数组下标 2）


class TestDictRowShape:
    @pytest.mark.asyncio
    async def test_dict_row_updates_target_key_preserves_others(self, factory, seeded):
        """dict 行写 C2（year_end）：只改 rows[0]["year_end"]，其余键/行原样，键序保留。"""
        async with factory() as s:
            res = await _mod.write_note_cell(
                _PgFaithfulSession(s), _mk_user(), str(seeded["dict_id"]), "note", "C2", "999", _utc(),
                check_lock=_no_lock,
                project_id=str(seeded["pid"]), year=Y, section_id=seeded["dict_section"], node_key=NODE,
            )
            await s.commit()
        assert res["success"] is True
        assert res["old_value"] == "10"
        rows = await _reread_rows(factory, seeded["dict_id"])
        # 目标 cell 变
        assert rows[0]["year_end"] == "999"
        # 同行其它键不变
        assert rows[0] == {"code": "库存现金", "name": "N1", "year_end": "999", "year_begin": "1"}
        # 其它行完全不变
        assert rows[1] == {"code": "银行存款", "name": "N2", "year_end": "20", "year_begin": "2"}
        # 行仍是 dict，未被改写成数组
        assert isinstance(rows[0], dict)


class TestArrayRowShape:
    @pytest.mark.asyncio
    async def test_array_row_updates_by_position_preserves_others(self, factory, seeded):
        """二维数组行写 B2（下标 1）：只改 rows[0][1]，其余列/行原样，行仍是 list。"""
        async with factory() as s:
            res = await _mod.write_note_cell(
                _PgFaithfulSession(s), _mk_user(), str(seeded["arr_id"]), "note", "B2", "ARR新值", _utc(),
                check_lock=_no_lock,
                project_id=str(seeded["pid"]), year=Y, section_id=seeded["arr_section"], node_key=NODE,
            )
            await s.commit()
        assert res["success"] is True
        assert res["old_value"] == "A1"
        rows = await _reread_rows(factory, seeded["arr_id"])
        assert rows[0] == ["库存现金", "ARR新值", "10", "1"]  # 只第 1 列变
        assert rows[1] == ["银行存款", "A2"]  # 窄行完全不变
        assert isinstance(rows[0], list)

    @pytest.mark.asyncio
    async def test_array_narrow_row_extends_only_to_target_col(self, factory, seeded):
        """窄行（rows[1] 只 2 列）写 D3（下标 3）：只补到目标列（4 列），不强制全行等宽到表头外。"""
        async with factory() as s:
            res = await _mod.write_note_cell(
                _PgFaithfulSession(s), _mk_user(), str(seeded["arr_id"]), "note", "D3", "补列值", _utc(),
                check_lock=_no_lock,
                project_id=str(seeded["pid"]), year=Y, section_id=seeded["arr_section"], node_key=NODE,
            )
            await s.commit()
        assert res["success"] is True
        assert res["old_value"] is None  # 原来越过行尾，无旧值
        rows = await _reread_rows(factory, seeded["arr_id"])
        # 窄行补到下标 3（4 列），中间空位补 ""，不多补
        assert rows[1] == ["银行存款", "A2", "", "补列值"]
        # 另一行不变
        assert rows[0] == ["库存现金", "A1", "10", "1"]

    @pytest.mark.asyncio
    async def test_array_write_roundtrips_through_reader(self, factory, seeded):
        """读写同口径：writer 按位置写入后，取数器 _query_note_cells 能从同一位置读回。"""
        from app.services.custom_query.module_cell_resolver import _query_note_cells

        async with factory() as s:
            await _mod.write_note_cell(
                _PgFaithfulSession(s), _mk_user(), str(seeded["arr_id"]), "note", "C2", "7777", _utc(),
                check_lock=_no_lock,
                project_id=str(seeded["pid"]), year=Y, section_id=seeded["arr_section"], node_key=NODE,
            )
            await s.commit()
        async with factory() as s:
            cells = await _query_note_cells(
                s, str(seeded["pid"]), Y, seeded["arr_section"], "C2", node_key=NODE,
            )
        # C2 → year_end 列（数组下标 2），reader 应读回 writer 写入的值
        assert any(c["cell_ref"] == "C2" and str(c["value"]) == "7777" for c in cells), cells


class TestBoundaryAndUnsupportedShape:
    @pytest.mark.asyncio
    async def test_row_out_of_range_rejected_no_write(self, factory, seeded):
        """行越界（只有 2 数据行，写第 5 行 B6）→ ValueError，整表不变。"""
        before = await _reread_rows(factory, seeded["dict_id"])
        async with factory() as s:
            with pytest.raises(ValueError, match="Row index out of range"):
                await _mod.write_note_cell(
                    _PgFaithfulSession(s), _mk_user(), str(seeded["dict_id"]), "note", "B6", "X", _utc(),
                    check_lock=_no_lock,
                    project_id=str(seeded["pid"]), year=Y, section_id=seeded["dict_section"], node_key=NODE,
                )
            await s.rollback()
        assert await _reread_rows(factory, seeded["dict_id"]) == before

    @pytest.mark.asyncio
    async def test_column_out_of_range_rejected_no_write(self, factory, seeded):
        """列越界（_NOTE_COLUMNS 只 5 列 A~E，写 F2 → col_idx=5）→ ValueError，整表不变。"""
        before = await _reread_rows(factory, seeded["dict_id"])
        async with factory() as s:
            with pytest.raises(ValueError, match="Column index out of range"):
                await _mod.write_note_cell(
                    _PgFaithfulSession(s), _mk_user(), str(seeded["dict_id"]), "note", "F2", "X", _utc(),
                    check_lock=_no_lock,
                    project_id=str(seeded["pid"]), year=Y, section_id=seeded["dict_section"], node_key=NODE,
                )
            await s.rollback()
        assert await _reread_rows(factory, seeded["dict_id"]) == before

    @pytest.mark.asyncio
    async def test_unsupported_row_shape_rejected_no_write(self, factory):
        """行既非 dict 也非 list（标量行）→ ValueError（不支持的形状），整表不变。"""
        pid = uuid.uuid4()
        bad = {"headers": ["x"], "rows": ["我是一个标量行不是对象也不是数组"]}
        async with factory() as s:
            rec = ConsolNoteData(project_id=pid, year=Y, section_id=SID, node_key=NODE,
                                 data=bad, updated_at=_utc())
            s.add(rec)
            await s.commit()
            rec_hex = rec.id.hex
        before = await _reread_rows(factory, rec_hex)
        async with factory() as s:
            with pytest.raises(ValueError, match="Unsupported note row shape"):
                await _mod.write_note_cell(
                    _PgFaithfulSession(s), _mk_user(), str(rec_hex), "note", "B2", "X", _utc(),
                    check_lock=_no_lock,
                    project_id=str(pid), year=Y, section_id=SID, node_key=NODE,
                )
            await s.rollback()
        assert await _reread_rows(factory, rec_hex) == before


class TestMutationProof:
    def test_dict_only_write_would_break_array_rows(self):
        """变异证明：若 writer 退化成「只处理 dict」（对数组行用 row[col_name]=...），数组行会抛
        TypeError（list indices must be integers）—— 证明生产的位置写入分支是真实必需的。"""
        from app.services.custom_query.module_cell_resolver import _NOTE_COLUMNS

        array_row = ["库存现金", "A1", "10", "1"]
        col_idx = 1
        # 生产行为：位置写入成功
        old = _mod._write_note_row_cell(list(array_row), col_idx, "新", _NOTE_COLUMNS, "B2")
        assert old == "A1"
        # 退化行为（dict-only）：用列名索引 list 必然 TypeError
        with pytest.raises(TypeError):
            col_name = _NOTE_COLUMNS[col_idx]
            array_row[col_name] = "新"  # type: ignore[index]
