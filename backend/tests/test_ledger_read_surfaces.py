"""
test_ledger_read_surfaces.py

验证 LEDGER_TABLE_READ_SURFACES 结构与 validate_surfaces 的存在性检查。
design §5, R8, AC-16, AC-23.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.ledger_read_surfaces import (
    LEDGER_TABLE_READ_SURFACES,
    ReadSurface,
    SurfaceValidationError,
    validate_surfaces,
)


# ── 1. 注册表结构 ────────────────────────────────────────

class TestReadSurfacesStructure:

    def test_covers_four_tables(self) -> None:
        expected = {"tb_balance", "tb_ledger", "tb_aux_balance", "tb_aux_ledger"}
        assert set(LEDGER_TABLE_READ_SURFACES.keys()) == expected

    def test_each_table_has_at_least_one_surface(self) -> None:
        for table, surfaces in LEDGER_TABLE_READ_SURFACES.items():
            assert len(surfaces) >= 1, f"{table} 缺少读取面"

    def test_all_entries_are_read_surface(self) -> None:
        for table, surfaces in LEDGER_TABLE_READ_SURFACES.items():
            for s in surfaces:
                assert isinstance(s, ReadSurface), f"{table} 中含非 ReadSurface 条目"
                assert s.module_path, f"{table} 条目缺少 module_path"
                assert s.symbol, f"{table} 条目缺少 symbol"

    def test_no_duplicate_fqn(self) -> None:
        seen: set[str] = set()
        for table, surfaces in LEDGER_TABLE_READ_SURFACES.items():
            for s in surfaces:
                fqn = f"{s.module_path}.{s.symbol}"
                assert fqn not in seen, f"重复的 FQN: {fqn}"
                seen.add(fqn)


# ── 2. validate_surfaces 正确性 ──────────────────────────

class TestValidateSurfaces:

    def test_missing_module_raises(self) -> None:
        """注册表中含不存在的模块时 validate_surfaces 抛异常。"""
        fake_surfaces = {
            "tb_balance": [
                ReadSurface(
                    module_path="app.services.nonexistent_module_xyz",
                    symbol="some_func",
                    description="虚假模块",
                ),
            ],
            "tb_ledger": [],
            "tb_aux_balance": [],
            "tb_aux_ledger": [],
        }
        with patch(
            "app.services.ledger_read_surfaces.LEDGER_TABLE_READ_SURFACES",
            fake_surfaces,
        ):
            with pytest.raises(SurfaceValidationError) as exc_info:
                validate_surfaces()
            assert exc_info.value.result.missing_module

    def test_missing_symbol_raises(self) -> None:
        """模块存在但符号不存在时抛异常。"""
        fake_surfaces = {
            "tb_balance": [
                ReadSurface(
                    module_path="app.services.ledger_read_surfaces",  # 自身模块一定存在
                    symbol="nonexistent_function_abc",
                    description="虚假符号",
                ),
            ],
            "tb_ledger": [],
            "tb_aux_balance": [],
            "tb_aux_ledger": [],
        }
        with patch(
            "app.services.ledger_read_surfaces.LEDGER_TABLE_READ_SURFACES",
            fake_surfaces,
        ):
            with pytest.raises(SurfaceValidationError) as exc_info:
                validate_surfaces()
            assert exc_info.value.result.missing_symbol

    def test_self_reference_valid(self) -> None:
        """引用自身模块中存在的符号时不抛异常。"""
        fake_surfaces = {
            "tb_balance": [
                ReadSurface(
                    module_path="app.services.ledger_read_surfaces",
                    symbol="validate_surfaces",  # 自身一定存在
                    description="自引用测试",
                ),
            ],
            "tb_ledger": [],
            "tb_aux_balance": [],
            "tb_aux_ledger": [],
        }
        with patch(
            "app.services.ledger_read_surfaces.LEDGER_TABLE_READ_SURFACES",
            fake_surfaces,
        ):
            result = validate_surfaces()
            assert result.ok
            assert len(result.valid) == 1
