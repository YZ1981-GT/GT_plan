"""Unit tests for custom WP cell → ACNR L3 runtime registration (task 13.3).

覆盖三点（P7 / Req 12.3, 12.4）：
1. 注册进 runtime（custom_flat profile）+ full_resolve 可命中，命中 L3 源层。
2. `_build_custom_wp_cell_entries` 单 wp register_custom 失败仅 warning + continue，
   其余 wp 与全部 legacy AddressEntry 仍产出，异常不上抛。
3. invalidate 清理 project-scoped runtime（clear_runtime_entries / canonical
   acnr.events.invalidate 清空该 project 的 L3 store）。

Requirements: 12.3, 12.4
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.acnr.runtime import (
    clear_all_runtime_entries,
    clear_runtime_entries,
    get_runtime_entries,
    register_custom,
)
from app.services.acnr.resolver import full_resolve, reset_resolve_metrics


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_state():
    """每个测试前后清空 L3 store 与 resolve 指标。"""
    clear_all_runtime_entries()
    reset_resolve_metrics()
    yield
    clear_all_runtime_entries()
    reset_resolve_metrics()


def _mock_db_session(*, ownership_exists: bool = True) -> AsyncMock:
    """构造 mock db session，让 _validate_wp_ownership 通过（SELECT 1）。"""
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = 1 if ownership_exists else None
    db.execute.return_value = result
    return db


# ─── Test 1: register (custom_flat) → full_resolve hits L3 ───────────────────


class TestRuntimeRegistrationFullResolveHit:
    @pytest.mark.asyncio
    async def test_custom_flat_register_then_full_resolve_hits_l3(self):
        """custom_flat 登记后，full_resolve(WP 3 参) 命中同一 addr_id + L3 源层。"""
        db = _mock_db_session(ownership_exists=True)
        project_id = str(uuid.uuid4())
        wp_id = str(uuid.uuid4())
        # 使用不太可能与真实 catalog 冲突的 wp_code
        wp_code = "ZZCUSTOMWP1"
        cell = "B7"

        entries = await register_custom(
            db,
            project_id,
            wp_id,
            [{"cell_address": cell, "wp_code": wp_code, "semantic_label": "自定义合计"}],
            addr_profile="custom_flat",
        )

        # custom_flat addr_id == {wp_code}/{wp_code}/{cell}
        expected_addr_id = f"{wp_code}/{wp_code}/{cell}"
        assert len(entries) == 1
        assert entries[0].addr_id == expected_addr_id
        assert entries[0].formula_ref == f"WP('{wp_code}','{wp_code}','{cell}')"

        # full_resolve 经 3 参 custom_flat WP() 命中 L3
        result = await full_resolve(
            formula_ref=f"WP('{wp_code}','{wp_code}','{cell}')",
            project_id=project_id,
            db=db,
        )

        assert result.found is True
        assert result.addr_id == expected_addr_id
        assert result.source_layer == "L3"
        assert result.cell_address == cell
        assert result.semantic_label == "自定义合计"

    @pytest.mark.asyncio
    async def test_full_resolve_miss_when_project_scope_mismatch(self):
        """L3 是 project-scoped：换一个 project_id 解析不到（found=False）。"""
        db = _mock_db_session(ownership_exists=True)
        registered_pid = str(uuid.uuid4())
        other_pid = str(uuid.uuid4())
        wp_code = "ZZCUSTOMWP2"
        cell = "C9"

        await register_custom(
            db,
            registered_pid,
            str(uuid.uuid4()),
            [{"cell_address": cell, "wp_code": wp_code}],
            addr_profile="custom_flat",
        )

        result = await full_resolve(
            formula_ref=f"WP('{wp_code}','{wp_code}','{cell}')",
            project_id=other_pid,
            db=db,
        )
        assert result.found is False


# ─── Test 2: per-wp failure continue in _build_custom_wp_cell_entries ─────────


class TestBuildCustomWpCellEntriesPerWpFailure:
    @pytest.mark.asyncio
    async def test_single_wp_register_failure_does_not_break_others(self, monkeypatch):
        """某 wp register_custom 抛异常 → 仅 warning+continue；

        其余 wp 的 register 仍被调用，且两个 wp 的 legacy AddressEntry 都产出，
        异常不上抛。
        """
        from app.services import address_registry as ar

        project_id = str(uuid.uuid4())
        wp_id_fail = str(uuid.uuid4())
        wp_id_good = str(uuid.uuid4())
        # flat parsed_data：field 为单元格地址 → extract_custom_cells 提取
        parsed_data = {"Sheet1": {"B7": 123}}

        # 行顺序：FAILWP 在前，验证其失败后 GOODWP 仍被处理
        rows = [
            (wp_id_fail, parsed_data, "FAILWP", "失败底稿"),
            (wp_id_good, parsed_data, "GOODWP", "正常底稿"),
        ]

        db = AsyncMock()
        result = MagicMock()
        result.all.return_value = rows
        db.execute.return_value = result

        register_calls: list[tuple[str, list[str]]] = []

        async def fake_register_custom(
            _db, _pid, _wid, cells, *, addr_profile="runtime"
        ):
            codes = [c.get("wp_code") for c in cells]
            register_calls.append((_wid, codes))
            if codes and codes[0] == "FAILWP":
                raise RuntimeError("simulated register_custom failure")
            return []

        # register_custom 在函数内 `from ... import register_custom` 于调用时解析，
        # monkeypatch 模块属性即可生效
        monkeypatch.setattr(
            "app.services.acnr.runtime.register_custom", fake_register_custom
        )

        # 不应抛异常
        entries = await ar._build_custom_wp_cell_entries(db, project_id, 2025)

        # 两个 wp 的 register 都被尝试（FAILWP 抛异常但被 continue 吞掉）
        attempted_wps = {wid for wid, _ in register_calls}
        assert wp_id_fail in attempted_wps
        assert wp_id_good in attempted_wps

        # 两个 wp 的 legacy AddressEntry 都产出（register 失败不影响已产出条目）
        produced_codes = {e.wp_code for e in entries}
        assert "FAILWP" in produced_codes
        assert "GOODWP" in produced_codes

    @pytest.mark.asyncio
    async def test_all_registers_ok_still_returns_legacy_entries(self, monkeypatch):
        """register_custom 全部成功时，legacy AddressEntry 仍正常产出。"""
        project_id = str(uuid.uuid4())
        parsed_data = {"Sheet1": {"D4": 1}}
        rows = [(str(uuid.uuid4()), parsed_data, "OKWP", "OK 底稿")]

        db = AsyncMock()
        result = MagicMock()
        result.all.return_value = rows
        db.execute.return_value = result

        async def fake_register_custom(_db, _pid, _wid, cells, *, addr_profile="runtime"):
            return []

        monkeypatch.setattr(
            "app.services.acnr.runtime.register_custom", fake_register_custom
        )

        from app.services import address_registry as ar

        entries = await ar._build_custom_wp_cell_entries(db, project_id, 2025)
        assert any(e.wp_code == "OKWP" for e in entries)


# ─── Test 3: invalidate clears project-scoped L3 runtime ─────────────────────


class TestInvalidateClearsRuntime:
    @pytest.mark.asyncio
    async def test_clear_runtime_entries_empties_project(self):
        """clear_runtime_entries(pid) 清空该 project 的 L3，不影响其他 project。"""
        db = _mock_db_session(ownership_exists=True)
        pid_a = str(uuid.uuid4())
        pid_b = str(uuid.uuid4())

        await register_custom(
            db, pid_a, str(uuid.uuid4()),
            [{"cell_address": "A1", "wp_code": "ZZA"}],
            addr_profile="custom_flat",
        )
        await register_custom(
            db, pid_b, str(uuid.uuid4()),
            [{"cell_address": "B1", "wp_code": "ZZB"}],
            addr_profile="custom_flat",
        )
        assert len(get_runtime_entries(pid_a)) == 1
        assert len(get_runtime_entries(pid_b)) == 1

        clear_runtime_entries(pid_a)

        assert get_runtime_entries(pid_a) == {}
        assert len(get_runtime_entries(pid_b)) == 1

    @pytest.mark.asyncio
    async def test_canonical_invalidate_empties_l3_store(self):
        """canonical acnr.events.invalidate(pid) 清空该 project 的 L3 store。"""
        from app.services.acnr import events

        db = _mock_db_session(ownership_exists=True)
        project_id = str(uuid.uuid4())

        await register_custom(
            db, project_id, str(uuid.uuid4()),
            [{"cell_address": "E5", "wp_code": "ZZCLR"}],
            addr_profile="custom_flat",
        )
        assert len(get_runtime_entries(project_id)) == 1

        # canonical invalidate（含 L3→L2→reverse_index→legacy，不抛异常）
        await events.invalidate(project_id, trigger="unit_test")

        assert get_runtime_entries(project_id) == {}
