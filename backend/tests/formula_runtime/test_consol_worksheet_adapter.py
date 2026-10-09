"""Tests for ConsolWorksheetMutationAdapter + ConsolWorksheetDomainReader.

真实 ORM/SQLite 测试，覆盖：
- reader: dict/list 行形态、miss/找到、batch 加载
- adapter: prepare→apply→fresh-read round-trip
- CAS 冲突检测（version 不匹配拒绝）
- restore 成功与冲突
- read_versions 准确返回

spec: consol-node-key-isolation-and-shared-context 任务 8.4/8.6
设计: §十二、ADR-CNSC-008、P11
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401  注册全部模型 + SQLite 方言补丁

from app.models.base import Base
from app.models.consol_worksheet_data_models import ConsolWorksheetData
from app.services.formula_runtime.adapters.consol_worksheet import (
    ConsolWorksheetMutationAdapter,
    _get_cell_value,
    _set_cell_value,
)
from app.services.formula_runtime.contracts import CanonicalFormulaTarget, FormulaMutation
from app.services.formula_runtime.value_loader import (
    ConsolWorksheetDomainReader,
    FormulaValueLoader,
)

PROJECT_ID = uuid.UUID("10000000-0000-0000-0000-000000000001")
YEAR = 2025

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


def _make_target(
    sheet_key: str = "info",
    row_identity: str = "0",
    cell_identity: str = "company_code",
) -> CanonicalFormulaTarget:
    return CanonicalFormulaTarget(
        domain="consol_worksheet",
        project_id=PROJECT_ID,
        year=YEAR,
        addr_id=f"cw:{sheet_key}!{row_identity}:{cell_identity}",
        locator={
            "sheet_key": sheet_key,
            "row_identity": row_identity,
            "cell_identity": cell_identity,
        },
    )


async def _seed_worksheet(db, sheet_key: str, data: dict | list, version: int = 0):
    """在 SQLite 测试库中插入一行 consol_worksheet_data。"""
    row = ConsolWorksheetData(
        id=uuid.uuid4(),
        project_id=PROJECT_ID,
        year=YEAR,
        sheet_key=sheet_key,
        data=data,
        version=version,
    )
    db.add(row)
    await db.flush()
    return row


# ═══════════════════════════════════════════════════════════════════════════════
# Helper tests: _get_cell_value / _set_cell_value
# ═══════════════════════════════════════════════════════════════════════════════


class TestHelpers:
    def test_get_dict_row(self):
        data = {"rows": [{"company_code": "A", "name": "甲公司"}]}
        assert _get_cell_value(data, "0", "company_code") == "A"

    def test_get_dict_nested(self):
        data = {"capital": {"adjustment": 100}}
        assert _get_cell_value(data, "capital", "adjustment") == 100

    def test_get_list_by_identity(self):
        data = {"rows": [{"company_code": "A", "ratio": 80}, {"company_code": "B", "ratio": 60}]}
        assert _get_cell_value(data, "B", "ratio") == 60

    def test_get_miss(self):
        data = {"rows": []}
        assert _get_cell_value(data, "0", "missing") is None

    def test_set_dict_row(self):
        data = {"rows": [{"company_code": "A", "ratio": 80}]}
        result = _set_cell_value(data, "0", "ratio", 90)
        assert result["rows"][0]["ratio"] == 90
        # 原数据不变（深拷贝）
        assert data["rows"][0]["ratio"] == 80

    def test_set_creates_structure(self):
        result = _set_cell_value(None, "capital", "adjustment", 100)
        assert result["capital"]["adjustment"] == 100


# ═══════════════════════════════════════════════════════════════════════════════
# Reader tests: ConsolWorksheetDomainReader
# ═══════════════════════════════════════════════════════════════════════════════


class TestConsolWorksheetDomainReader:

    @pytest.mark.asyncio
    async def test_read_found_value(self, db_session):
        await _seed_worksheet(db_session, "info", {"rows": [{"company_code": "A", "ratio": 80}]})
        await db_session.flush()

        reader = ConsolWorksheetDomainReader(db_session)
        target = _make_target("info", "0", "ratio")
        result = await reader.read_batch([target])

        assert target.addr_id in result
        assert float(result[target.addr_id]) == 80.0

    @pytest.mark.asyncio
    async def test_read_miss_returns_empty(self, db_session):
        await _seed_worksheet(db_session, "info", {"rows": []})
        await db_session.flush()

        reader = ConsolWorksheetDomainReader(db_session)
        target = _make_target("info", "99", "missing_field")
        result = await reader.read_batch([target])

        assert target.addr_id not in result

    @pytest.mark.asyncio
    async def test_read_nonexistent_sheet_miss(self, db_session):
        reader = ConsolWorksheetDomainReader(db_session)
        target = _make_target("nonexistent", "0", "field")
        result = await reader.read_batch([target])

        assert target.addr_id not in result

    @pytest.mark.asyncio
    async def test_loader_includes_consol_worksheet(self, db_session):
        """FormulaValueLoader 默认 reader map 包含 consol_worksheet。"""
        loader = FormulaValueLoader(db_session)
        assert "consol_worksheet" in loader._readers


# ═══════════════════════════════════════════════════════════════════════════════
# Adapter tests: ConsolWorksheetMutationAdapter
# ═══════════════════════════════════════════════════════════════════════════════


class TestConsolWorksheetAdapter:

    @pytest.mark.asyncio
    async def test_prepare_reads_existing_value(self, db_session):
        await _seed_worksheet(db_session, "info", {"rows": [{"company_code": "A"}]}, version=3)
        await db_session.flush()

        adapter = ConsolWorksheetMutationAdapter(db_session)
        target = _make_target("info", "0", "company_code")
        mutations = await adapter.prepare_many([target], {target.addr_id: "B"})

        assert len(mutations) == 1
        assert mutations[0].before_value == "A"
        assert mutations[0].after_value == "B"
        assert mutations[0].expected_version == "3"

    @pytest.mark.asyncio
    async def test_prepare_nonexistent_sheet(self, db_session):
        adapter = ConsolWorksheetMutationAdapter(db_session)
        target = _make_target("nonexistent", "0", "field")
        mutations = await adapter.prepare_many([target], {target.addr_id: "val"})

        assert len(mutations) == 1
        assert mutations[0].before_value is None
        assert mutations[0].expected_version is None

    @pytest.mark.asyncio
    async def test_apply_writes_and_increments_version(self, db_session):
        row = await _seed_worksheet(db_session, "info", {"rows": [{"company_code": "A"}]}, version=3)
        await db_session.flush()

        adapter = ConsolWorksheetMutationAdapter(db_session)
        target = _make_target("info", "0", "company_code")
        mutation = (await adapter.prepare_many([target], {target.addr_id: "B"}))[0]

        applied = await adapter.apply_many([mutation])
        assert len(applied) == 1
        assert applied[0].applied_version == "4"

        # fresh read: 确认持久化可见
        await db_session.refresh(row)
        assert row.version == 4
        assert row.data["rows"][0]["company_code"] == "B"

    @pytest.mark.asyncio
    async def test_apply_version_conflict_raises(self, db_session):
        await _seed_worksheet(db_session, "info", {"rows": [{"company_code": "A"}]}, version=5)
        await db_session.flush()

        adapter = ConsolWorksheetMutationAdapter(db_session)
        target = _make_target("info", "0", "company_code")

        # 伪造 expected_version=3（当前是 5）
        bad_mutation = FormulaMutation(
            target=target,
            before_value="A",
            after_value="B",
            expected_version="3",
        )

        with pytest.raises(ValueError, match="版本冲突"):
            await adapter.apply_many([bad_mutation])

    @pytest.mark.asyncio
    async def test_restore_success(self, db_session):
        await _seed_worksheet(db_session, "info", {"rows": [{"company_code": "A"}]}, version=3)
        await db_session.flush()

        adapter = ConsolWorksheetMutationAdapter(db_session)
        target = _make_target("info", "0", "company_code")

        # prepare → apply
        mutation = (await adapter.prepare_many([target], {target.addr_id: "B"}))[0]
        await adapter.apply_many([mutation])

        # restore
        restored = await adapter.restore_many([mutation])
        assert len(restored) == 1
        assert restored[0].conflict is False

    @pytest.mark.asyncio
    async def test_restore_conflict_when_modified(self, db_session):
        row = await _seed_worksheet(db_session, "info", {"rows": [{"company_code": "A"}]}, version=3)
        await db_session.flush()

        adapter = ConsolWorksheetMutationAdapter(db_session)
        target = _make_target("info", "0", "company_code")

        # prepare → apply
        mutation = (await adapter.prepare_many([target], {target.addr_id: "B"}))[0]
        await adapter.apply_many([mutation])

        # 手动修改（模拟另一用户覆盖）
        row.data = _set_cell_value(row.data, "0", "company_code", "C")
        await db_session.flush()

        # restore 应检测到冲突
        restored = await adapter.restore_many([mutation])
        assert len(restored) == 1
        assert restored[0].conflict is True

    @pytest.mark.asyncio
    async def test_read_versions(self, db_session):
        await _seed_worksheet(db_session, "info", {"rows": []}, version=7)
        await db_session.flush()

        adapter = ConsolWorksheetMutationAdapter(db_session)
        target = _make_target("info", "0", "field")

        versions = await adapter.read_versions([target])
        assert versions[target.addr_id] == "7"

    @pytest.mark.asyncio
    async def test_read_versions_nonexistent(self, db_session):
        adapter = ConsolWorksheetMutationAdapter(db_session)
        target = _make_target("nonexistent", "0", "field")

        versions = await adapter.read_versions([target])
        assert versions[target.addr_id] == "0"

    @pytest.mark.asyncio
    async def test_locator_validation_rejects_missing_keys(self, db_session):
        adapter = ConsolWorksheetMutationAdapter(db_session)
        bad_target = CanonicalFormulaTarget(
            domain="consol_worksheet",
            project_id=PROJECT_ID,
            year=YEAR,
            addr_id="cw:bad",
            locator={"sheet_key": "info"},  # 缺少 row_identity, cell_identity
        )

        with pytest.raises(ValueError, match="缺少必需键"):
            await adapter.prepare_many([bad_target], {bad_target.addr_id: "val"})
