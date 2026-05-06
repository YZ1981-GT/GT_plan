"""预填充 provenance 回写测试

Validates: Requirements 7 — 预填充带来源元数据
Tests:
- _build_source_ref 各公式类型的 source_ref 构建
- _write_cell_provenance supersede 策略
- _FORMULA_TYPE_TO_SOURCE 映射正确性
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.services.prefill_engine import (
    PREFILL_SERVICE_VERSION,
    _FORMULA_TYPE_TO_SOURCE,
    _build_source_ref,
    _write_cell_provenance,
)


# ---------------------------------------------------------------------------
# _FORMULA_TYPE_TO_SOURCE 映射测试
# ---------------------------------------------------------------------------


class TestFormulaTypeToSource:
    """验证公式类型到 provenance source 的映射"""

    def test_tb_maps_to_trial_balance(self):
        assert _FORMULA_TYPE_TO_SOURCE["TB"] == "trial_balance"

    def test_sum_tb_maps_to_trial_balance(self):
        assert _FORMULA_TYPE_TO_SOURCE["SUM_TB"] == "trial_balance"

    def test_aux_maps_to_ledger(self):
        assert _FORMULA_TYPE_TO_SOURCE["AUX"] == "ledger"

    def test_prev_maps_to_prior_year(self):
        assert _FORMULA_TYPE_TO_SOURCE["PREV"] == "prior_year"

    def test_wp_maps_to_formula(self):
        assert _FORMULA_TYPE_TO_SOURCE["WP"] == "formula"

    def test_all_five_sources_covered(self):
        """确保覆盖需求 7 定义的所有来源类型"""
        expected_sources = {"trial_balance", "prior_year", "formula", "ledger"}
        actual_sources = set(_FORMULA_TYPE_TO_SOURCE.values())
        assert expected_sources == actual_sources


# ---------------------------------------------------------------------------
# _build_source_ref 测试
# ---------------------------------------------------------------------------


class TestBuildSourceRef:
    """验证 source_ref 构建逻辑"""

    def test_tb_source_ref(self):
        params = {"account_code": "1001", "column_name": "audited_amount"}
        result = _build_source_ref("TB", "1001, audited_amount", params)
        assert result == "1001:audited_amount"

    def test_sum_tb_source_ref(self):
        params = {"account_range": "1001-1099", "column_name": "audited_amount"}
        result = _build_source_ref("SUM_TB", "1001-1099, audited_amount", params)
        assert result == "1001-1099:audited_amount"

    def test_aux_source_ref(self):
        params = {
            "account_code": "1122",
            "aux_dimension": "客户",
            "dimension_value": "ABC公司",
            "column_name": "closing_balance",
        }
        result = _build_source_ref("AUX", "1122, 客户, ABC公司, closing_balance", params)
        assert result == "1122:客户:ABC公司:closing_balance"

    def test_prev_source_ref(self):
        params = {"formula_type": "TB", "account_code": "1001", "column_name": "audited_amount"}
        result = _build_source_ref("PREV", "TB, 1001, audited_amount", params)
        assert result == "TB:1001"

    def test_wp_source_ref(self):
        params = {"wp_code": "D-01", "cell_ref": "B5"}
        result = _build_source_ref("WP", "D-01, B5", params)
        assert result == "D-01!B5"

    def test_tb_empty_account_code_returns_none(self):
        params = {"account_code": "", "column_name": "audited_amount"}
        result = _build_source_ref("TB", "", params)
        assert result is None

    def test_unknown_formula_type_returns_none(self):
        params = {"something": "value"}
        result = _build_source_ref("UNKNOWN", "args", params)
        assert result is None

    def test_case_insensitive_formula_type(self):
        """_build_source_ref 内部做 .upper()"""
        params = {"account_code": "1001", "column_name": "audited_amount"}
        result = _build_source_ref("tb", "1001, audited_amount", params)
        assert result == "1001:audited_amount"


# ---------------------------------------------------------------------------
# _write_cell_provenance 测试（supersede 策略）
# ---------------------------------------------------------------------------


def _make_wp_mock(parsed_data=None):
    """创建一个模拟 WorkingPaper 对象"""
    wp = MagicMock()
    wp.parsed_data = parsed_data
    return wp


class TestWriteCellProvenance:
    """验证 provenance 写入和 supersede 策略"""

    def test_write_to_empty_parsed_data(self):
        """parsed_data 为 None 时应正确初始化"""
        wp = _make_wp_mock(parsed_data=None)
        provenance = {
            "D5": {
                "source": "trial_balance",
                "source_ref": "1001:audited_amount",
                "filled_at": "2026-05-08T10:00:00",
                "filled_by_service_version": PREFILL_SERVICE_VERSION,
            }
        }
        _write_cell_provenance(wp, provenance)

        assert wp.parsed_data is not None
        assert "cell_provenance" in wp.parsed_data
        assert "D5" in wp.parsed_data["cell_provenance"]
        entry = wp.parsed_data["cell_provenance"]["D5"]
        assert entry["source"] == "trial_balance"
        assert entry["source_ref"] == "1001:audited_amount"
        assert entry["filled_at"] == "2026-05-08T10:00:00"
        assert entry["filled_by_service_version"] == PREFILL_SERVICE_VERSION

    def test_write_preserves_existing_parsed_data(self):
        """写入 provenance 不应覆盖 parsed_data 中的其他字段"""
        wp = _make_wp_mock(parsed_data={
            "audited_amount": 100000,
            "conclusion": "无保留意见",
        })
        provenance = {
            "B3": {
                "source": "prior_year",
                "source_ref": "TB:1001",
                "filled_at": "2026-05-08T10:00:00",
                "filled_by_service_version": PREFILL_SERVICE_VERSION,
            }
        }
        _write_cell_provenance(wp, provenance)

        assert wp.parsed_data["audited_amount"] == 100000
        assert wp.parsed_data["conclusion"] == "无保留意见"
        assert "cell_provenance" in wp.parsed_data
        assert "B3" in wp.parsed_data["cell_provenance"]

    def test_supersede_overwrites_old_value(self):
        """重填时应覆盖旧值"""
        wp = _make_wp_mock(parsed_data={
            "cell_provenance": {
                "D5": {
                    "source": "trial_balance",
                    "source_ref": "1001:audited_amount",
                    "filled_at": "2026-05-01T08:00:00",
                    "filled_by_service_version": "prefill_v1.1",
                }
            }
        })
        new_provenance = {
            "D5": {
                "source": "trial_balance",
                "source_ref": "1001:audited_amount",
                "filled_at": "2026-05-08T10:00:00",
                "filled_by_service_version": PREFILL_SERVICE_VERSION,
            }
        }
        _write_cell_provenance(wp, new_provenance)

        entry = wp.parsed_data["cell_provenance"]["D5"]
        assert entry["filled_at"] == "2026-05-08T10:00:00"
        assert entry["filled_by_service_version"] == PREFILL_SERVICE_VERSION

    def test_supersede_keeps_max_one_history(self):
        """supersede 时保留最多 1 次历史（_prev 字段）"""
        wp = _make_wp_mock(parsed_data={
            "cell_provenance": {
                "D5": {
                    "source": "trial_balance",
                    "source_ref": "1001:audited_amount",
                    "filled_at": "2026-05-01T08:00:00",
                    "filled_by_service_version": "prefill_v1.1",
                }
            }
        })
        new_provenance = {
            "D5": {
                "source": "trial_balance",
                "source_ref": "1001:audited_amount",
                "filled_at": "2026-05-08T10:00:00",
                "filled_by_service_version": PREFILL_SERVICE_VERSION,
            }
        }
        _write_cell_provenance(wp, new_provenance)

        entry = wp.parsed_data["cell_provenance"]["D5"]
        assert "_prev" in entry
        assert entry["_prev"]["filled_at"] == "2026-05-01T08:00:00"
        assert entry["_prev"]["filled_by_service_version"] == "prefill_v1.1"

    def test_supersede_discards_older_history(self):
        """第三次填充时，_prev 只保留上一次，不保留更早的"""
        wp = _make_wp_mock(parsed_data={
            "cell_provenance": {
                "D5": {
                    "source": "trial_balance",
                    "source_ref": "1001:audited_amount",
                    "filled_at": "2026-05-05T09:00:00",
                    "filled_by_service_version": "prefill_v1.1",
                    "_prev": {
                        "source": "trial_balance",
                        "source_ref": "1001:audited_amount",
                        "filled_at": "2026-05-01T08:00:00",
                        "filled_by_service_version": "prefill_v1.0",
                    },
                }
            }
        })
        new_provenance = {
            "D5": {
                "source": "trial_balance",
                "source_ref": "1001:audited_amount",
                "filled_at": "2026-05-08T10:00:00",
                "filled_by_service_version": PREFILL_SERVICE_VERSION,
            }
        }
        _write_cell_provenance(wp, new_provenance)

        entry = wp.parsed_data["cell_provenance"]["D5"]
        # 当前值是最新的
        assert entry["filled_at"] == "2026-05-08T10:00:00"
        # _prev 只保留上一次（2026-05-05），不保留更早的（2026-05-01）
        assert entry["_prev"]["filled_at"] == "2026-05-05T09:00:00"
        assert "_prev" not in entry["_prev"]

    def test_multiple_cells_provenance(self):
        """多个单元格同时写入 provenance"""
        wp = _make_wp_mock(parsed_data=None)
        provenance = {
            "D5": {
                "source": "trial_balance",
                "source_ref": "1001:audited_amount",
                "filled_at": "2026-05-08T10:00:00",
                "filled_by_service_version": PREFILL_SERVICE_VERSION,
            },
            "E5": {
                "source": "prior_year",
                "source_ref": "TB:1001",
                "filled_at": "2026-05-08T10:00:00",
                "filled_by_service_version": PREFILL_SERVICE_VERSION,
            },
            "F5": {
                "source": "formula",
                "source_ref": "D-01!B5",
                "filled_at": "2026-05-08T10:00:00",
                "filled_by_service_version": PREFILL_SERVICE_VERSION,
            },
        }
        _write_cell_provenance(wp, provenance)

        cp = wp.parsed_data["cell_provenance"]
        assert len(cp) == 3
        assert cp["D5"]["source"] == "trial_balance"
        assert cp["E5"]["source"] == "prior_year"
        assert cp["F5"]["source"] == "formula"

    def test_same_filled_at_no_history(self):
        """相同 filled_at 时不创建 _prev（幂等重入）"""
        wp = _make_wp_mock(parsed_data={
            "cell_provenance": {
                "D5": {
                    "source": "trial_balance",
                    "source_ref": "1001:audited_amount",
                    "filled_at": "2026-05-08T10:00:00",
                    "filled_by_service_version": PREFILL_SERVICE_VERSION,
                }
            }
        })
        # 同一时间戳重入
        new_provenance = {
            "D5": {
                "source": "trial_balance",
                "source_ref": "1001:audited_amount",
                "filled_at": "2026-05-08T10:00:00",
                "filled_by_service_version": PREFILL_SERVICE_VERSION,
            }
        }
        _write_cell_provenance(wp, new_provenance)

        entry = wp.parsed_data["cell_provenance"]["D5"]
        assert "_prev" not in entry


# ---------------------------------------------------------------------------
# PREFILL_SERVICE_VERSION 常量测试
# ---------------------------------------------------------------------------


class TestServiceVersion:
    def test_version_format(self):
        """版本号应为 prefill_vX.Y 格式"""
        assert PREFILL_SERVICE_VERSION.startswith("prefill_v")
        # 确保有版本号部分
        version_part = PREFILL_SERVICE_VERSION.replace("prefill_v", "")
        parts = version_part.split(".")
        assert len(parts) == 2
        assert all(p.isdigit() for p in parts)
