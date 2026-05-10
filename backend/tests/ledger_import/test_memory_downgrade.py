"""F51 / Sprint 8.33: 内存降级单元测试

覆盖点：
1. psutil.virtual_memory().percent > 80 → 返回 True 触发降级（流式 + 小 chunk）
2. psutil.virtual_memory().percent = 50 → 返回 False 保持默认
3. psutil 未安装（ImportError）→ 返回 False 静默跳过
4. psutil.virtual_memory() 抛异常 → 返回 False 静默跳过
5. 降级日志 tag 'memory_pressure_downgrade' 可以被捕获

Validates: Requirements F51（pipeline 启动时读 psutil，>80% 降级 openpyxl + 10k chunk）
"""

from __future__ import annotations

import builtins
import logging
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.services.ledger_import.pipeline import _detect_memory_pressure


# ---------------------------------------------------------------------------
# Case 1：内存 > 80% 触发降级
# ---------------------------------------------------------------------------


class TestMemoryPressureDetection:
    def test_high_memory_returns_true(self):
        """模拟 psutil 返回 85%，应触发降级。"""
        fake_mem = MagicMock()
        fake_mem.percent = 85.0

        with patch("psutil.virtual_memory", return_value=fake_mem):
            assert _detect_memory_pressure(uuid4()) is True

    def test_very_high_memory_returns_true(self):
        """95% 极限场景也要触发。"""
        fake_mem = MagicMock()
        fake_mem.percent = 95.0

        with patch("psutil.virtual_memory", return_value=fake_mem):
            assert _detect_memory_pressure(uuid4()) is True

    def test_exactly_at_threshold_returns_false(self):
        """80.0% 边界不触发（严格 >）。"""
        fake_mem = MagicMock()
        fake_mem.percent = 80.0

        with patch("psutil.virtual_memory", return_value=fake_mem):
            assert _detect_memory_pressure(uuid4()) is False

    def test_just_above_threshold_returns_true(self):
        """80.1% 恰好触发。"""
        fake_mem = MagicMock()
        fake_mem.percent = 80.1

        with patch("psutil.virtual_memory", return_value=fake_mem):
            assert _detect_memory_pressure(uuid4()) is True


# ---------------------------------------------------------------------------
# Case 2：内存 ≤ 80% 保持默认
# ---------------------------------------------------------------------------


class TestNormalMemoryLevel:
    def test_low_memory_returns_false(self):
        fake_mem = MagicMock()
        fake_mem.percent = 50.0

        with patch("psutil.virtual_memory", return_value=fake_mem):
            assert _detect_memory_pressure(uuid4()) is False

    def test_zero_memory_returns_false(self):
        fake_mem = MagicMock()
        fake_mem.percent = 0.0

        with patch("psutil.virtual_memory", return_value=fake_mem):
            assert _detect_memory_pressure(uuid4()) is False


# ---------------------------------------------------------------------------
# Case 3：psutil 未安装 → 静默跳过
# ---------------------------------------------------------------------------


class TestPsutilOptional:
    def test_import_error_returns_false(self):
        """psutil 未装（ImportError）时不应抛异常，返回 False 保持默认。"""
        original_import = builtins.__import__

        def _fake_import(name, *args, **kwargs):
            if name == "psutil":
                raise ImportError("No module named 'psutil'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_fake_import):
            result = _detect_memory_pressure(uuid4())

        assert result is False


# ---------------------------------------------------------------------------
# Case 4：psutil 抛异常 → 静默跳过
# ---------------------------------------------------------------------------


class TestPsutilRuntimeError:
    def test_virtual_memory_raises_returns_false(self):
        """psutil.virtual_memory() 抛异常不应阻断主流程。"""
        with patch(
            "psutil.virtual_memory",
            side_effect=OSError("cannot read meminfo"),
        ):
            result = _detect_memory_pressure(uuid4())

        assert result is False

    def test_percent_attribute_missing_returns_false(self):
        """psutil 返回对象但 .percent 缺失，应降级为 False。"""
        broken = MagicMock()
        type(broken).percent = property(
            lambda self: (_ for _ in ()).throw(AttributeError("no percent"))
        )

        with patch("psutil.virtual_memory", return_value=broken):
            result = _detect_memory_pressure(uuid4())

        assert result is False


# ---------------------------------------------------------------------------
# Case 5：降级日志 tag
# ---------------------------------------------------------------------------


class TestMemoryDowngradeLog:
    def test_downgrade_log_emitted(self, caplog):
        """触发降级时 WARNING 日志应包含 'memory_pressure_downgrade' 可grep。"""
        fake_mem = MagicMock()
        fake_mem.percent = 90.0

        with patch("psutil.virtual_memory", return_value=fake_mem):
            with caplog.at_level(
                logging.WARNING,
                logger="app.services.ledger_import.pipeline",
            ):
                _detect_memory_pressure(uuid4())

        messages = [r.message for r in caplog.records]
        assert any("memory_pressure_downgrade" in m for m in messages), (
            f"expected 'memory_pressure_downgrade' in log records, got: {messages}"
        )

    def test_no_log_below_threshold(self, caplog):
        """内存正常时不应记 WARNING。"""
        fake_mem = MagicMock()
        fake_mem.percent = 50.0

        with patch("psutil.virtual_memory", return_value=fake_mem):
            with caplog.at_level(
                logging.WARNING,
                logger="app.services.ledger_import.pipeline",
            ):
                _detect_memory_pressure(uuid4())

        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert not any("memory_pressure" in r.message for r in warnings)
