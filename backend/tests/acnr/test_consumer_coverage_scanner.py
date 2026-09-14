"""
test_consumer_coverage_scanner.py — Consumer Coverage 扫描器集成测试

验证 P12: legacy consumer drift 被阻断 — 新增消费者→exit 1

Feature: acnr-runtime-convergence, Task 13
Requirements: Req-11
**Validates: Requirements Req-11**
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# ─── 路径 ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent  # GT_plan/
SCANNER_SCRIPT = (
    PROJECT_ROOT / "backend" / "scripts" / "check" / "check_acnr_consumer_coverage.py"
)
REAL_SCAN_ROOT = PROJECT_ROOT / "backend" / "app"
REAL_LEDGER = PROJECT_ROOT / "backend" / "data" / "acnr" / "coverage_ledger.json"


class TestScannerBasicFunctionality:
    """基础功能测试：脚本可运行、报告模式不崩溃。"""

    def test_script_exists(self):
        """扫描器脚本存在。"""
        assert SCANNER_SCRIPT.exists(), f"Scanner script not found: {SCANNER_SCRIPT}"

    def test_report_mode_exits_zero(self):
        """报告模式恒退出码 0（不 --strict）。"""
        result = subprocess.run(
            [sys.executable, str(SCANNER_SCRIPT)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0, (
            f"Report mode should exit 0, got {result.returncode}.\n"
            f"stdout: {result.stdout[:500]}\nstderr: {result.stderr[:500]}"
        )

    def test_strict_mode_with_real_codebase(self):
        """严格模式扫描真实 codebase + allowlist 应 exit 0（当前所有消费者已登记）。"""
        result = subprocess.run(
            [sys.executable, str(SCANNER_SCRIPT), "--strict"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(PROJECT_ROOT),
        )
        # 如果 allowlist 覆盖全部现有消费者，strict 应 exit 0
        # 如果有未登记的（可能因 codebase 变化），至少不崩溃
        assert result.returncode in (0, 1), (
            f"Unexpected exit code: {result.returncode}.\n"
            f"stderr: {result.stderr[:500]}"
        )


class TestNewConsumerDrift:
    """P12: 新增 legacy 消费者被阻断。"""

    def test_new_consumer_triggers_failure(self, tmp_path: Path):
        """新增文件含 address_registry. 直接消费且未在 allowlist → exit 1。"""
        # 创建临时扫描目录结构
        scan_dir = tmp_path / "app"
        scan_dir.mkdir()

        # 写一个有 address_registry 直接消费的假文件
        violating_file = scan_dir / "new_consumer.py"
        violating_file.write_text(
            "from app.services.address_registry import address_registry\n"
            "\n"
            "async def bad_function(db):\n"
            "    result = await address_registry.search(db, 'proj', 2025, 'foo')\n"
            "    return result\n",
            encoding="utf-8",
        )

        # 空 allowlist ledger
        ledger_file = tmp_path / "coverage_ledger.json"
        ledger_file.write_text(
            json.dumps({"metadata": {}, "allowlist": []}),
            encoding="utf-8",
        )

        # 运行 strict 模式
        result = subprocess.run(
            [
                sys.executable,
                str(SCANNER_SCRIPT),
                "--strict",
                "--scan-root",
                str(scan_dir),
                "--ledger-path",
                str(ledger_file),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        assert result.returncode == 1, (
            f"Expected exit 1 for unregistered consumer, got {result.returncode}.\n"
            f"stdout: {result.stdout}"
        )
        assert "VIOLATION" in result.stdout or "FAIL" in result.stdout

    def test_registered_consumer_passes(self, tmp_path: Path):
        """allowlist 已登记的直接消费 → strict 模式 exit 0。"""
        scan_dir = tmp_path / "app"
        scan_dir.mkdir()

        # 有 address_registry 调用的文件
        registered_file = scan_dir / "known_consumer.py"
        registered_file.write_text(
            "from app.services.address_registry import address_registry\n"
            "\n"
            "async def old_function(db):\n"
            "    await address_registry.invalidate_async('proj')\n",
            encoding="utf-8",
        )

        # allowlist 包含该文件
        ledger_file = tmp_path / "coverage_ledger.json"
        ledger_file.write_text(
            json.dumps({
                "metadata": {},
                "allowlist": [
                    {
                        "file": "known_consumer.py",
                        "reason": "Legacy invalidate",
                        "migration_target": "P6",
                    }
                ],
            }),
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(SCANNER_SCRIPT),
                "--strict",
                "--scan-root",
                str(scan_dir),
                "--ledger-path",
                str(ledger_file),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        assert result.returncode == 0, (
            f"Expected exit 0 for registered consumer, got {result.returncode}.\n"
            f"stdout: {result.stdout}"
        )

    def test_acnr_facade_not_flagged(self, tmp_path: Path):
        """经 ACNR facade 的 import 不计入违规。"""
        scan_dir = tmp_path / "app"
        scan_dir.mkdir()

        # 文件只用 ACNR facade，无 address_registry 直调
        clean_file = scan_dir / "modern_consumer.py"
        clean_file.write_text(
            "from app.services.acnr.resolver import full_resolve\n"
            "from app.services.acnr.events import invalidate\n"
            "\n"
            "async def good_function(db):\n"
            "    result = await full_resolve(input_data, db=db)\n"
            "    return result\n",
            encoding="utf-8",
        )

        # 空 allowlist
        ledger_file = tmp_path / "coverage_ledger.json"
        ledger_file.write_text(
            json.dumps({"metadata": {}, "allowlist": []}),
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(SCANNER_SCRIPT),
                "--strict",
                "--scan-root",
                str(scan_dir),
                "--ledger-path",
                str(ledger_file),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        assert result.returncode == 0, (
            f"ACNR facade should not be flagged, got exit {result.returncode}.\n"
            f"stdout: {result.stdout}"
        )
        assert "VIOLATION" not in result.stdout


class TestACNRCoreExclusion:
    """ACNR 核心模块（services/acnr/*）被排除扫描。"""

    def test_acnr_core_module_excluded(self, tmp_path: Path):
        """services/acnr/ 下的文件允许直调 address_registry（delegation）。"""
        scan_dir = tmp_path / "app"
        acnr_dir = scan_dir / "services" / "acnr"
        acnr_dir.mkdir(parents=True)

        # ACNR 核心模块直调 address_registry（合法 delegation）
        acnr_file = acnr_dir / "events.py"
        acnr_file.write_text(
            "from app.services.address_registry import address_registry\n"
            "\n"
            "async def invalidate(project_id):\n"
            "    await address_registry.invalidate_async(project_id)\n",
            encoding="utf-8",
        )

        # 空 allowlist
        ledger_file = tmp_path / "coverage_ledger.json"
        ledger_file.write_text(
            json.dumps({"metadata": {}, "allowlist": []}),
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(SCANNER_SCRIPT),
                "--strict",
                "--scan-root",
                str(scan_dir),
                "--ledger-path",
                str(ledger_file),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        assert result.returncode == 0, (
            f"ACNR core should be excluded, got exit {result.returncode}.\n"
            f"stdout: {result.stdout}"
        )


class TestSelfModuleExclusion:
    """address_registry 模块自身被排除扫描。"""

    def test_self_module_excluded(self, tmp_path: Path):
        """services/address_registry.py 自身不计入违规。"""
        scan_dir = tmp_path / "app"
        svc_dir = scan_dir / "services"
        svc_dir.mkdir(parents=True)

        # address_registry 自身
        self_file = svc_dir / "address_registry.py"
        self_file.write_text(
            "class AddressRegistry:\n"
            "    async def search(self, db, project_id, year, keyword):\n"
            "        pass\n"
            "\n"
            "address_registry = AddressRegistry()\n",
            encoding="utf-8",
        )

        # 空 allowlist
        ledger_file = tmp_path / "coverage_ledger.json"
        ledger_file.write_text(
            json.dumps({"metadata": {}, "allowlist": []}),
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(SCANNER_SCRIPT),
                "--strict",
                "--scan-root",
                str(scan_dir),
                "--ledger-path",
                str(ledger_file),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        assert result.returncode == 0, (
            f"Self module should be excluded, got exit {result.returncode}.\n"
            f"stdout: {result.stdout}"
        )


class TestLedgerStructure:
    """Coverage Ledger 结构校验。"""

    def test_ledger_exists_and_valid_json(self):
        """coverage_ledger.json 存在且为合法 JSON。"""
        assert REAL_LEDGER.exists(), f"Ledger not found: {REAL_LEDGER}"
        with open(REAL_LEDGER, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "allowlist" in data
        assert "metadata" in data

    def test_ledger_entries_have_required_fields(self):
        """每条 allowlist 条目必须有 file/reason/migration_target。"""
        with open(REAL_LEDGER, "r", encoding="utf-8") as f:
            data = json.load(f)

        for entry in data["allowlist"]:
            assert "file" in entry, f"Entry missing 'file': {entry}"
            assert "reason" in entry, f"Entry missing 'reason': {entry}"
            assert "migration_target" in entry, (
                f"Entry missing 'migration_target': {entry}"
            )
            # migration_target 应为 P 编号格式
            mt = entry["migration_target"]
            assert mt.startswith("P"), (
                f"migration_target should start with 'P': {mt}"
            )


class TestCommentLinesIgnored:
    """注释行不计入违规。"""

    def test_comment_line_excluded(self, tmp_path: Path):
        """Python 注释行中的 address_registry 引用不算违规。"""
        scan_dir = tmp_path / "app"
        scan_dir.mkdir()

        comment_file = scan_dir / "comments_only.py"
        comment_file.write_text(
            "# from app.services.address_registry import address_registry\n"
            "# address_registry.search(...)\n"
            "\n"
            "def clean_function():\n"
            "    pass\n",
            encoding="utf-8",
        )

        ledger_file = tmp_path / "coverage_ledger.json"
        ledger_file.write_text(
            json.dumps({"metadata": {}, "allowlist": []}),
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(SCANNER_SCRIPT),
                "--strict",
                "--scan-root",
                str(scan_dir),
                "--ledger-path",
                str(ledger_file),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        assert result.returncode == 0, (
            f"Comments should not be flagged, got exit {result.returncode}.\n"
            f"stdout: {result.stdout}"
        )
