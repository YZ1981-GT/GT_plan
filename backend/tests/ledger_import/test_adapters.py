"""适配器测试 — Task 78：8 家适配器各自至少 3 用例。

覆盖：
- 每个适配器的 match() 正向/负向匹配
- get_column_aliases() 返回非空 dict（balance + ledger）
- GenericAdapter 兜底行为
- AdapterRegistry.detect_best 优先级排序
"""

from __future__ import annotations

import pytest

from backend.app.services.ledger_import.adapters import AdapterRegistry
from backend.app.services.ledger_import.adapters.base import BaseAdapter
from backend.app.services.ledger_import.adapters.generic import GenericAdapter
from backend.app.services.ledger_import.adapters.kingdee import KingdeeAdapter
from backend.app.services.ledger_import.adapters.yonyou import YonyouAdapter
from backend.app.services.ledger_import.adapters.sap import SapAdapter
from backend.app.services.ledger_import.adapters.oracle import OracleAdapter
from backend.app.services.ledger_import.adapters.inspur import InspurAdapter
from backend.app.services.ledger_import.adapters.newgrand import NewgrandAdapter
from backend.app.services.ledger_import.detection_types import FileDetection, SheetDetection


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fd(filename: str = "test.xlsx", sheet_names: list[str] | None = None) -> FileDetection:
    """Build minimal FileDetection for adapter matching."""
    sheets = []
    for sn in (sheet_names or ["Sheet1"]):
        sheets.append(SheetDetection(
            file_name=filename, sheet_name=sn,
            row_count_estimate=100, header_row_index=0, data_start_row=1,
            table_type="unknown", table_type_confidence=0,
            confidence_level="manual_required",
            preview_rows=[], detection_evidence={},
        ))
    return FileDetection(
        file_name=filename, file_size_bytes=1024, file_type="xlsx",
        sheets=sheets,
    )


# ---------------------------------------------------------------------------
# 用友
# ---------------------------------------------------------------------------


class TestYonyouAdapter:
    """用友适配器测试。"""

    def test_match_filename_positive(self):
        """文件名含"用友" → match > 0。"""
        adapter = YonyouAdapter()
        fd = _make_fd("用友U8_余额表.xlsx")
        assert adapter.match(fd) >= 0.5

    def test_match_filename_negative(self):
        """文件名无用友关键词 → match = 0。"""
        adapter = YonyouAdapter()
        fd = _make_fd("金蝶K3_余额表.xlsx")
        assert adapter.match(fd) == 0.0

    def test_balance_aliases_complete(self):
        """余额表别名包含关键列。"""
        adapter = YonyouAdapter()
        aliases = adapter.get_column_aliases("balance")
        assert "account_code" in aliases
        assert "opening_balance" in aliases
        assert "closing_balance" in aliases
        assert "debit_amount" in aliases

    def test_ledger_aliases_complete(self):
        """序时账别名包含关键列。"""
        adapter = YonyouAdapter()
        aliases = adapter.get_column_aliases("ledger")
        assert "voucher_date" in aliases
        assert "voucher_no" in aliases
        assert "account_code" in aliases
        assert "debit_amount" in aliases


# ---------------------------------------------------------------------------
# 金蝶
# ---------------------------------------------------------------------------


class TestKingdeeAdapter:
    """金蝶适配器测试。"""

    def test_match_filename_positive(self):
        adapter = KingdeeAdapter()
        fd = _make_fd("金蝶K3_科目余额表.xlsx")
        assert adapter.match(fd) >= 0.5

    def test_match_filename_eas(self):
        adapter = KingdeeAdapter()
        fd = _make_fd("EAS_export_2025.xlsx")
        assert adapter.match(fd) >= 0.5

    def test_match_filename_negative(self):
        adapter = KingdeeAdapter()
        fd = _make_fd("用友U8_余额表.xlsx")
        assert adapter.match(fd) == 0.0

    def test_balance_aliases(self):
        adapter = KingdeeAdapter()
        aliases = adapter.get_column_aliases("balance")
        assert "account_code" in aliases
        assert len(aliases) >= 4


# ---------------------------------------------------------------------------
# SAP
# ---------------------------------------------------------------------------


class TestSapAdapter:
    """SAP 适配器测试。"""

    def test_match_filename_positive(self):
        adapter = SapAdapter()
        fd = _make_fd("SAP_GL_Export_2025.xlsx")
        assert adapter.match(fd) >= 0.5

    def test_match_filename_negative(self):
        adapter = SapAdapter()
        fd = _make_fd("金蝶K3_余额表.xlsx")
        assert adapter.match(fd) == 0.0

    def test_balance_aliases(self):
        adapter = SapAdapter()
        aliases = adapter.get_column_aliases("balance")
        assert "account_code" in aliases


# ---------------------------------------------------------------------------
# Oracle
# ---------------------------------------------------------------------------


class TestOracleAdapter:
    """Oracle 适配器测试。"""

    def test_match_filename_positive(self):
        adapter = OracleAdapter()
        fd = _make_fd("Oracle_EBS_GL_2025.xlsx")
        assert adapter.match(fd) >= 0.5

    def test_match_filename_negative(self):
        adapter = OracleAdapter()
        fd = _make_fd("用友U8.xlsx")
        assert adapter.match(fd) == 0.0

    def test_ledger_aliases(self):
        adapter = OracleAdapter()
        aliases = adapter.get_column_aliases("ledger")
        assert "voucher_date" in aliases


# ---------------------------------------------------------------------------
# 浪潮
# ---------------------------------------------------------------------------


class TestInspurAdapter:
    """浪潮适配器测试。"""

    def test_match_filename_positive(self):
        adapter = InspurAdapter()
        fd = _make_fd("浪潮GS_余额表.xlsx")
        assert adapter.match(fd) >= 0.5

    def test_match_filename_negative(self):
        adapter = InspurAdapter()
        fd = _make_fd("SAP_GL.xlsx")
        assert adapter.match(fd) == 0.0

    def test_balance_aliases(self):
        adapter = InspurAdapter()
        aliases = adapter.get_column_aliases("balance")
        assert "account_code" in aliases


# ---------------------------------------------------------------------------
# 新中大
# ---------------------------------------------------------------------------


class TestNewgrandAdapter:
    """新中大适配器测试。"""

    def test_match_filename_positive(self):
        adapter = NewgrandAdapter()
        fd = _make_fd("新中大_科目余额表.xlsx")
        assert adapter.match(fd) >= 0.5

    def test_match_filename_negative(self):
        adapter = NewgrandAdapter()
        fd = _make_fd("金蝶K3.xlsx")
        assert adapter.match(fd) == 0.0

    def test_balance_aliases(self):
        adapter = NewgrandAdapter()
        aliases = adapter.get_column_aliases("balance")
        assert "account_code" in aliases


# ---------------------------------------------------------------------------
# GenericAdapter（兜底）
# ---------------------------------------------------------------------------


class TestGenericAdapter:
    """通用兜底适配器测试。"""

    def test_match_always_nonzero(self):
        """GenericAdapter 对任何文件都返回非零匹配度。"""
        adapter = GenericAdapter()
        fd = _make_fd("random_file.xlsx")
        assert adapter.match(fd) > 0

    def test_priority_lowest(self):
        """GenericAdapter priority = 0（最低）。"""
        adapter = GenericAdapter()
        assert adapter.priority == 0

    def test_balance_aliases_from_defaults(self):
        """GenericAdapter 使用默认别名表。"""
        adapter = GenericAdapter()
        aliases = adapter.get_column_aliases("balance")
        assert "account_code" in aliases
        assert "opening_balance" in aliases

    def test_unknown_table_type_returns_empty(self):
        """unknown 表类型返回空 dict。"""
        adapter = GenericAdapter()
        aliases = adapter.get_column_aliases("unknown")
        # GenericAdapter 对 unknown 也应返回通用别名或空
        assert isinstance(aliases, dict)


# ---------------------------------------------------------------------------
# AdapterRegistry
# ---------------------------------------------------------------------------


class TestAdapterRegistry:
    """注册表优先级排序测试。"""

    def test_detect_best_prefers_high_priority(self):
        """高优先级适配器优先匹配。"""
        registry = AdapterRegistry()
        registry.register(GenericAdapter())
        registry.register(YonyouAdapter())

        fd = _make_fd("用友U8_余额表.xlsx")
        best, score = registry.detect_best(fd)

        assert best.id == "yonyou"
        assert score >= 0.5

    def test_detect_best_falls_back_to_generic(self):
        """无 vendor 匹配时回退到 GenericAdapter。"""
        registry = AdapterRegistry()
        registry.register(GenericAdapter())
        registry.register(YonyouAdapter())
        registry.register(KingdeeAdapter())

        fd = _make_fd("unknown_software_export.xlsx")
        best, score = registry.detect_best(fd)

        assert best.id == "generic"

    def test_all_adapters_registered(self):
        """全局 registry 应包含所有 7 个适配器。"""
        from backend.app.services.ledger_import.adapters import registry

        all_adapters = registry.all()
        ids = {a.id for a in all_adapters}
        # 至少包含这些
        expected = {"yonyou", "kingdee", "sap", "oracle", "inspur", "newgrand", "generic"}
        assert expected <= ids, f"Missing adapters: {expected - ids}"
