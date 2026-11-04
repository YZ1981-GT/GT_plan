"""R4.2：row_status 的 definition_hash 分支测试（formula-hub-release-blockers）。

修复前 row_status 算出 stale=True 却返回重新计算的 is_effectively_stale，丢掉了 hash 漂移。
"""
from types import SimpleNamespace

import pytest

from app.services.report_freshness import CALC_VERSION, row_status


def _row(*, formula: str = "TB('1001','期末余额')", definition_hash: str = "old") -> SimpleNamespace:
    """构造一条「公式/版本/标记全正常，但来源信封 hash 与当前不符」的报表行。"""
    return SimpleNamespace(
        is_stale=False,
        calc_version=CALC_VERSION,
        formula_used=formula,
        provenance={"applied_attempt": {"definition_hash": definition_hash}},
        calc_error=None,
        blank_reason=None,
    )


class TestDefinitionHashStale:
    """仅覆盖 definition_hash 分支，不走 is_effectively_stale 的两条旧判据。"""

    def test_hash_mismatch_is_stale(self):
        """来源信封的 definition_hash 与当前不同 → is_stale=True。"""
        row = _row(definition_hash="old")
        result = row_status(row, row.formula_used, "new")
        assert result["is_stale"] is True

    def test_hash_match_is_fresh(self):
        """来源信封的 definition_hash 与当前相同 → is_stale=False（其他判据也不成立）。"""
        row = _row(definition_hash="same")
        result = row_status(row, row.formula_used, "same")
        assert result["is_stale"] is False

    def test_no_hash_param_skips_branch(self):
        """不传 definition_hash 参数 → 不进入 hash 分支，旧判据说了算。"""
        row = _row(definition_hash="old")
        result = row_status(row, row.formula_used)  # definition_hash 默认 None
        assert result["is_stale"] is False  # 旧判据全正常

    def test_no_provenance_skips_branch(self):
        """行没有 provenance → 不进入 hash 分支。"""
        row = _row()
        row.provenance = None
        result = row_status(row, row.formula_used, "new")
        assert result["is_stale"] is False

    def test_no_applied_attempt_skips_branch(self):
        """provenance 里没有 applied_attempt → 不进入 hash 分支。"""
        row = _row()
        row.provenance = {"other": 1}
        result = row_status(row, row.formula_used, "new")
        assert result["is_stale"] is False
