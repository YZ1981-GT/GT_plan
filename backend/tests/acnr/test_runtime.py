"""Unit tests for ACNR L3 runtime.py — register_custom + ownership validation.

Requirements: 23.3, 24.1, 24.2
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.acnr.runtime import (
    RuntimeCellEntry,
    WpOwnershipError,
    _build_addr_id,
    _build_formula_ref,
    _build_uri,
    _validate_wp_ownership,
    clear_all_runtime_entries,
    clear_runtime_entries,
    get_runtime_entries,
    get_runtime_entry,
    register_custom,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_l3():
    """每个测试前后清空 L3 store。"""
    clear_all_runtime_entries()
    yield
    clear_all_runtime_entries()


def _mock_db_session(*, ownership_exists: bool = True) -> AsyncMock:
    """构造 mock db session，控制 ownership 校验结果。"""
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = 1 if ownership_exists else None
    db.execute.return_value = result
    return db


# ─── Tests: _build helpers ───────────────────────────────────────────────────


class TestBuildHelpers:
    def test_build_addr_id(self):
        pid = "proj-001"
        wid = "wp-001"
        code = "CUST-01"
        cell = "B7"
        assert _build_addr_id(pid, wid, code, cell) == "runtime/proj-001/wp-001/CUST-01/B7"

    def test_build_uri(self):
        assert _build_uri("CUST-01", "B7") == "wp://CUST-01/B7"

    def test_build_formula_ref(self):
        assert _build_formula_ref("CUST-01", "B7") == "WP('CUST-01','B7')"


# ─── Tests: _validate_wp_ownership ───────────────────────────────────────────


class TestValidateWpOwnership:
    @pytest.mark.asyncio
    async def test_valid_ownership_passes(self):
        """wp 属于该 project 时校验通过（无异常）。"""
        db = _mock_db_session(ownership_exists=True)
        # 不应抛异常
        await _validate_wp_ownership(db, "proj-001", "wp-001")
        db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_ownership_raises(self):
        """wp 不属于该 project 时抛出 WpOwnershipError（R24.1）。"""
        db = _mock_db_session(ownership_exists=False)
        with pytest.raises(WpOwnershipError) as exc_info:
            await _validate_wp_ownership(db, "proj-001", "wp-999")
        assert "proj-001" in str(exc_info.value)
        assert "wp-999" in str(exc_info.value)


# ─── Tests: register_custom ─────────────────────────────────────────────────


class TestRegisterCustom:
    @pytest.mark.asyncio
    async def test_register_basic(self):
        """基本登记：cells 写入 L3，返回 RuntimeCellEntry 列表。"""
        db = _mock_db_session(ownership_exists=True)
        project_id = str(uuid.uuid4())
        wp_id = str(uuid.uuid4())

        cells = [
            {"cell_address": "B7", "wp_code": "CUST-01"},
            {"cell_address": "C10", "wp_code": "CUST-01", "semantic_label": "合计"},
        ]

        entries = await register_custom(db, project_id, wp_id, cells)

        assert len(entries) == 2
        assert all(isinstance(e, RuntimeCellEntry) for e in entries)
        # 验证字段
        e0 = entries[0]
        assert e0.domain == "wp"
        assert e0.origin == "custom"
        assert e0.uri_profile == "custom_flat"
        assert e0.runtime_only is True
        assert e0.cell_address == "B7"
        assert e0.wp_code == "CUST-01"
        assert e0.uri == "wp://CUST-01/B7"
        assert e0.formula_ref == "WP('CUST-01','B7')"
        assert e0.addr_id == f"runtime/{project_id}/{wp_id}/CUST-01/B7"
        # semantic_label
        e1 = entries[1]
        assert e1.semantic_label == "合计"

    @pytest.mark.asyncio
    async def test_register_stored_in_l3(self):
        """登记后可通过 get_runtime_entries 检索（R24.2: 仅 L3）。"""
        db = _mock_db_session(ownership_exists=True)
        project_id = str(uuid.uuid4())
        wp_id = str(uuid.uuid4())

        cells = [{"cell_address": "A1", "wp_code": "CUST-02"}]
        await register_custom(db, project_id, wp_id, cells)

        store = get_runtime_entries(project_id)
        assert len(store) == 1
        entry = list(store.values())[0]
        assert entry.cell_address == "A1"
        assert entry.wp_code == "CUST-02"

    @pytest.mark.asyncio
    async def test_register_rejects_invalid_ownership(self):
        """wp 不属于 project 时登记失败（R24.1 防 IDOR）。"""
        db = _mock_db_session(ownership_exists=False)
        project_id = str(uuid.uuid4())
        wp_id = str(uuid.uuid4())

        cells = [{"cell_address": "B7", "wp_code": "CUST-01"}]
        with pytest.raises(WpOwnershipError):
            await register_custom(db, project_id, wp_id, cells)

        # L3 不应有任何数据
        assert get_runtime_entries(project_id) == {}

    @pytest.mark.asyncio
    async def test_register_empty_cells(self):
        """空 cells 列表不报错，返回空列表。"""
        db = _mock_db_session(ownership_exists=True)
        entries = await register_custom(db, "p1", "w1", [])
        assert entries == []

    @pytest.mark.asyncio
    async def test_register_skips_invalid_cells(self):
        """缺少 cell_address 或 wp_code 的 cell 被跳过。"""
        db = _mock_db_session(ownership_exists=True)
        project_id = str(uuid.uuid4())
        wp_id = str(uuid.uuid4())

        cells = [
            {"cell_address": "", "wp_code": "CUST-01"},       # 空 cell_address
            {"cell_address": "B7", "wp_code": ""},            # 空 wp_code
            {"cell_address": "C3", "wp_code": "CUST-01"},    # 有效
        ]

        entries = await register_custom(db, project_id, wp_id, cells)
        assert len(entries) == 1
        assert entries[0].cell_address == "C3"

    @pytest.mark.asyncio
    async def test_register_multiple_calls_accumulate(self):
        """同一 project 多次调用累积（不覆盖之前的）。"""
        db = _mock_db_session(ownership_exists=True)
        project_id = str(uuid.uuid4())
        wp_id_1 = str(uuid.uuid4())
        wp_id_2 = str(uuid.uuid4())

        await register_custom(db, project_id, wp_id_1, [{"cell_address": "A1", "wp_code": "X1"}])
        await register_custom(db, project_id, wp_id_2, [{"cell_address": "B2", "wp_code": "X2"}])

        store = get_runtime_entries(project_id)
        assert len(store) == 2

    @pytest.mark.asyncio
    async def test_register_isolation_between_projects(self):
        """不同 project 的 L3 数据互相隔离（多租户）。"""
        db = _mock_db_session(ownership_exists=True)
        pid_a = str(uuid.uuid4())
        pid_b = str(uuid.uuid4())
        wp_id = str(uuid.uuid4())

        await register_custom(db, pid_a, wp_id, [{"cell_address": "A1", "wp_code": "X"}])
        await register_custom(db, pid_b, wp_id, [{"cell_address": "B1", "wp_code": "Y"}])

        assert len(get_runtime_entries(pid_a)) == 1
        assert len(get_runtime_entries(pid_b)) == 1
        assert list(get_runtime_entries(pid_a).values())[0].wp_code == "X"
        assert list(get_runtime_entries(pid_b).values())[0].wp_code == "Y"

    @pytest.mark.asyncio
    async def test_runtime_only_flag(self):
        """所有 RuntimeCellEntry 的 runtime_only=True（R24.2: 不落 L1）。"""
        db = _mock_db_session(ownership_exists=True)
        project_id = str(uuid.uuid4())
        wp_id = str(uuid.uuid4())

        entries = await register_custom(
            db, project_id, wp_id,
            [{"cell_address": "E5", "wp_code": "CUST-03"}],
        )
        assert all(e.runtime_only is True for e in entries)


# ─── Tests: get_runtime_entry ────────────────────────────────────────────────


class TestGetRuntimeEntry:
    @pytest.mark.asyncio
    async def test_get_by_addr_id(self):
        """按 addr_id 精确查找。"""
        db = _mock_db_session(ownership_exists=True)
        project_id = str(uuid.uuid4())
        wp_id = str(uuid.uuid4())

        await register_custom(db, project_id, wp_id, [{"cell_address": "D4", "wp_code": "CUST-05"}])
        addr_id = f"runtime/{project_id}/{wp_id}/CUST-05/D4"
        entry = get_runtime_entry(project_id, addr_id)
        assert entry is not None
        assert entry.cell_address == "D4"

    def test_get_nonexistent_returns_none(self):
        """不存在的 addr_id 返回 None。"""
        assert get_runtime_entry("no-proj", "no-addr") is None


# ─── Tests: clear_runtime_entries ────────────────────────────────────────────


class TestClearRuntimeEntries:
    @pytest.mark.asyncio
    async def test_clear_single_project(self):
        """清除单个 project 的 L3 不影响其他。"""
        db = _mock_db_session(ownership_exists=True)
        pid_a = "proj-a"
        pid_b = "proj-b"
        wp = str(uuid.uuid4())

        await register_custom(db, pid_a, wp, [{"cell_address": "A1", "wp_code": "X"}])
        await register_custom(db, pid_b, wp, [{"cell_address": "B1", "wp_code": "Y"}])

        clear_runtime_entries(pid_a)
        assert get_runtime_entries(pid_a) == {}
        assert len(get_runtime_entries(pid_b)) == 1
