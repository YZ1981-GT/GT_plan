"""check_no_float_amount.py 单元测试。

验证：
- 含 float() 金额调用的文件被检出
- 安全模式（json.dumps / 日志 / 注释）不被检出
- baseline 超限时 exit 1
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# 确保 scripts/check 可 import
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "check"))

from check_no_float_amount import is_safe_usage, scan_file, main  # noqa: E402


class TestIsSafeUsage:
    """测试安全模式判断。"""

    def test_json_dumps_is_safe(self):
        line = '    result = json.dumps({"amount": float(value)})'
        assert is_safe_usage(line) is True

    def test_logger_is_safe(self):
        line = '    logger.info(f"Amount: {float(amount)}")'
        assert is_safe_usage(line) is True

    def test_comment_is_safe(self):
        line = '    # float(amount) is used here'
        assert is_safe_usage(line) is True

    def test_isinstance_is_safe(self):
        line = '    if isinstance(value, float):'
        assert is_safe_usage(line) is True

    def test_format_string_is_safe(self):
        line = '    msg = f"value={float(x):.2f}"'
        assert is_safe_usage(line) is True

    def test_bare_float_is_unsafe(self):
        line = '    amount = float(debit) - float(credit)'
        assert is_safe_usage(line) is False

    def test_abs_float_is_unsafe(self):
        line = '    val = abs(float(item.get("amount", 0)))'
        assert is_safe_usage(line) is False


class TestScanFile:
    """测试文件扫描。"""

    def test_detects_float_call(self, tmp_path):
        f = tmp_path / "wp_test_service.py"
        f.write_text(
            "def calc():\n"
            "    amount = float(debit) - float(credit)\n"
            "    return amount\n",
            encoding="utf-8",
        )
        violations = scan_file(f)
        assert len(violations) == 1
        assert violations[0][0] == 2  # line number
        assert "float(debit)" in violations[0][1]

    def test_skips_safe_json(self, tmp_path):
        f = tmp_path / "wp_test_service.py"
        f.write_text(
            "import json\n"
            "def serialize():\n"
            "    return json.dumps({'v': float(amount)})\n",
            encoding="utf-8",
        )
        violations = scan_file(f)
        assert len(violations) == 0

    def test_skips_comment_lines(self, tmp_path):
        f = tmp_path / "wp_test_service.py"
        f.write_text(
            "# float(amount) old code\n"
            "def clean():\n"
            "    pass\n",
            encoding="utf-8",
        )
        violations = scan_file(f)
        assert len(violations) == 0

    def test_multiple_violations(self, tmp_path):
        f = tmp_path / "wp_test_service.py"
        f.write_text(
            "def calc():\n"
            "    a = float(x)\n"
            "    b = float(y)\n"
            "    return a + b\n",
            encoding="utf-8",
        )
        violations = scan_file(f)
        assert len(violations) == 2


class TestMain:
    """测试 main 函数退出码。"""

    def test_init_creates_baseline(self, tmp_path, monkeypatch):
        baseline_file = tmp_path / "baseline.txt"
        services_dir = tmp_path / "services"
        services_dir.mkdir()
        (services_dir / "wp_test.py").write_text(
            "amount = float(x)\n", encoding="utf-8"
        )

        monkeypatch.setattr(
            "check_no_float_amount.SERVICES_DIR", services_dir
        )
        monkeypatch.setattr(
            "check_no_float_amount.BASELINE_FILE", baseline_file
        )
        monkeypatch.setattr(
            "check_no_float_amount.ROOT", tmp_path
        )

        result = main(["--init"])
        assert result == 0
        assert baseline_file.exists()
        assert baseline_file.read_text().strip() == "1"

    def test_exceeds_baseline_returns_1(self, tmp_path, monkeypatch):
        baseline_file = tmp_path / "baseline.txt"
        baseline_file.write_text("0\n", encoding="utf-8")

        services_dir = tmp_path / "services"
        services_dir.mkdir()
        (services_dir / "wp_test.py").write_text(
            "amount = float(x)\n", encoding="utf-8"
        )

        monkeypatch.setattr(
            "check_no_float_amount.SERVICES_DIR", services_dir
        )
        monkeypatch.setattr(
            "check_no_float_amount.BASELINE_FILE", baseline_file
        )
        monkeypatch.setattr(
            "check_no_float_amount.ROOT", tmp_path
        )

        result = main([])
        assert result == 1

    def test_within_baseline_returns_0(self, tmp_path, monkeypatch):
        baseline_file = tmp_path / "baseline.txt"
        baseline_file.write_text("5\n", encoding="utf-8")

        services_dir = tmp_path / "services"
        services_dir.mkdir()
        (services_dir / "wp_test.py").write_text(
            "amount = float(x)\n", encoding="utf-8"
        )

        monkeypatch.setattr(
            "check_no_float_amount.SERVICES_DIR", services_dir
        )
        monkeypatch.setattr(
            "check_no_float_amount.BASELINE_FILE", baseline_file
        )
        monkeypatch.setattr(
            "check_no_float_amount.ROOT", tmp_path
        )

        result = main([])
        assert result == 0
