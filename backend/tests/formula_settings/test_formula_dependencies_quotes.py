"""需求 14.3：formula_settings/dependencies.py 9 个正则同时认单、双引号。

每个函数 × 单引号 + 双引号 → 结果必须相等。
混合引号（前后不配对）不应匹配。
upstream_refs / references 两个入口均覆盖。
"""
from __future__ import annotations

import pytest

from app.services.formula_settings.dependencies import references, upstream_refs


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

_REPORT_TYPES = {"BS-002": "BS", "BS-001": "BS", "BS-015": "BS", "IS-010": "IS"}


def _addr_ids(refs: list[dict]) -> list[str]:
    return [r["addr_id"] for r in refs]


# ===== 1. TB =====

class TestTBQuotes:
    _single = "TB('1001','期末余额')"
    _double = 'TB("1001","期末余额")'

    def test_single(self):
        refs = upstream_refs(self._single, {})
        assert _addr_ids(refs) == ["tb:1001"]

    def test_double(self):
        refs = upstream_refs(self._double, {})
        assert _addr_ids(refs) == ["tb:1001"]

    def test_equal(self):
        assert upstream_refs(self._single, {}) == upstream_refs(self._double, {})


# ===== 2. SUM_TB =====

class TestSumTBQuotes:
    _single = "SUM_TB('1001~1009','期末余额')"
    _double = 'SUM_TB("1001~1009","期末余额")'

    def test_single(self):
        refs = upstream_refs(self._single, {})
        assert _addr_ids(refs) == ["tb:1001~1009"]

    def test_double(self):
        refs = upstream_refs(self._double, {})
        assert _addr_ids(refs) == ["tb:1001~1009"]

    def test_equal(self):
        assert upstream_refs(self._single, {}) == upstream_refs(self._double, {})


# ===== 3. ROW =====

class TestROWQuotes:
    _single = "ROW('BS-002')"
    _double = 'ROW("BS-002")'

    def test_single(self):
        refs = upstream_refs(self._single, _REPORT_TYPES)
        assert _addr_ids(refs) == ["report:BS:BS-002"]

    def test_double(self):
        refs = upstream_refs(self._double, _REPORT_TYPES)
        assert _addr_ids(refs) == ["report:BS:BS-002"]

    def test_equal(self):
        assert upstream_refs(self._single, _REPORT_TYPES) == upstream_refs(self._double, _REPORT_TYPES)


# ===== 4. SUM_ROW =====

class TestSumROWQuotes:
    _single = "SUM_ROW('BS-001','BS-015')"
    _double = 'SUM_ROW("BS-001","BS-015")'

    def test_single(self):
        refs = upstream_refs(self._single, {})
        assert _addr_ids(refs) == ["report:BS-001~BS-015"]

    def test_double(self):
        refs = upstream_refs(self._double, {})
        assert _addr_ids(refs) == ["report:BS-001~BS-015"]

    def test_equal(self):
        assert upstream_refs(self._single, {}) == upstream_refs(self._double, {})


# ===== 5. REPORT =====

class TestREPORTQuotes:
    _single = "REPORT('BS-002')"
    _double = 'REPORT("BS-002")'

    def test_single(self):
        refs = upstream_refs(self._single, _REPORT_TYPES)
        assert _addr_ids(refs) == ["report:BS:BS-002"]

    def test_double(self):
        refs = upstream_refs(self._double, _REPORT_TYPES)
        assert _addr_ids(refs) == ["report:BS:BS-002"]

    def test_equal(self):
        assert upstream_refs(self._single, _REPORT_TYPES) == upstream_refs(self._double, _REPORT_TYPES)


# ===== 6. WP =====

class TestWPQuotes:
    _single = "WP('D1','审定表D1-1','审定数')"
    _double = 'WP("D1","审定表D1-1","审定数")'

    def test_single(self):
        refs = upstream_refs(self._single, {})
        assert _addr_ids(refs) == ["wp:D1/审定表D1-1/审定数"]

    def test_double(self):
        refs = upstream_refs(self._double, {})
        assert _addr_ids(refs) == ["wp:D1/审定表D1-1/审定数"]

    def test_equal(self):
        assert upstream_refs(self._single, {}) == upstream_refs(self._double, {})

    def test_two_args_single(self):
        refs = upstream_refs("WP('D1','审定表D1-1')", {})
        assert _addr_ids(refs) == ["wp:D1/审定表D1-1"]

    def test_two_args_double(self):
        refs = upstream_refs('WP("D1","审定表D1-1")', {})
        assert _addr_ids(refs) == ["wp:D1/审定表D1-1"]


# ===== 7. NOTE =====

class TestNOTEQuotes:
    _single = "NOTE('五、1','应收账款')"
    _double = 'NOTE("五、1","应收账款")'

    def test_single(self):
        refs = upstream_refs(self._single, {})
        assert _addr_ids(refs) == ["note:五、1"]

    def test_double(self):
        refs = upstream_refs(self._double, {})
        assert _addr_ids(refs) == ["note:五、1"]

    def test_equal(self):
        assert upstream_refs(self._single, {}) == upstream_refs(self._double, {})


# ===== 8. ADJ =====

class TestADJQuotes:
    _single = "ADJ('1001')"
    _double = 'ADJ("1001")'

    def test_single(self):
        refs = upstream_refs(self._single, {})
        assert _addr_ids(refs) == ["adj:1001"]

    def test_double(self):
        refs = upstream_refs(self._double, {})
        assert _addr_ids(refs) == ["adj:1001"]

    def test_equal(self):
        assert upstream_refs(self._single, {}) == upstream_refs(self._double, {})


# ===== 9. PREV =====

class TestPREVQuotes:
    _single = "PREV('1001','期末余额')"
    _double = 'PREV("1001","期末余额")'

    def test_single(self):
        refs = upstream_refs(self._single, {})
        assert _addr_ids(refs) == ["prev:1001"]

    def test_double(self):
        refs = upstream_refs(self._double, {})
        assert _addr_ids(refs) == ["prev:1001"]

    def test_equal(self):
        assert upstream_refs(self._single, {}) == upstream_refs(self._double, {})


# ===== references() 对两种写法结果相等 =====

class TestReferencesQuoteParity:
    def test_row_single_double(self):
        assert references("ROW('BS-002')", row_code="BS-002") is True
        assert references('ROW("BS-002")', row_code="BS-002") is True

    def test_report_single_double(self):
        assert references("REPORT('BS-002')", row_code="BS-002") is True
        assert references('REPORT("BS-002")', row_code="BS-002") is True

    def test_sum_row_single_double(self):
        assert references("SUM_ROW('BS-001','BS-015')", row_code="BS-002") is True
        assert references('SUM_ROW("BS-001","BS-015")', row_code="BS-002") is True

    def test_tb_single_double(self):
        assert references("TB('1001','期末余额')", account="1001") is True
        assert references('TB("1001","期末余额")', account="1001") is True

    def test_sum_tb_single_double(self):
        assert references("SUM_TB('1001~1009','期末余额')", account="1005") is True
        assert references('SUM_TB("1001~1009","期末余额")', account="1005") is True


# ===== 混合引号拒绝（反向引用 \1 天然不配对） =====

class TestMixedQuotesRejected:
    """前后引号不配对时正则不匹配 → 解析不出任何引用。"""

    def test_tb_mixed(self):
        assert upstream_refs("""TB('1001","期末余额')""", {}) == []

    def test_row_mixed(self):
        assert upstream_refs("""ROW('BS-002")""", {}) == []

    def test_note_mixed(self):
        assert upstream_refs("""NOTE("五、1','应收账款")""", {}) == []

    def test_wp_mixed(self):
        assert upstream_refs("""WP('D1","审定表D1-1','审定数")""", {}) == []

    def test_references_mixed(self):
        assert references("""TB('1001","期末余额')""", account="1001") is False
        assert references("""ROW('BS-002")""", row_code="BS-002") is False
