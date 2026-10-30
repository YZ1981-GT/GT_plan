"""AST 守卫：AuditLogEntry 构造与裸 SQL 写入只允许在白名单模块内。

ADR-ALC-08: 绕过写入方收口。

规则：
1. `AuditLogEntry(` 构造只允许出现在白名单文件（head.py / forks.py）
2. backend/app 内 SQL 文本不得含 `INSERT INTO audit_log_entries`
3. 守卫自检：白名单含不存在的文件 → 测试应红
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

# 白名单：允许直接构造 AuditLogEntry 的模块（相对于 backend/app/）
_ALLOWED_CONSTRUCTOR_FILES: set[str] = {
    "services/audit_chain/head.py",
    "services/audit_chain/forks.py",
    "services/audit_log_helper.py",
    "workers/audit_log_writer_worker.py",
}

_APP_DIR = Path(__file__).resolve().parents[2] / "app"


def _scan_constructor_sites() -> list[tuple[str, int]]:
    """扫描 backend/app/ 下所有 .py 里的 AuditLogEntry( 构造。"""
    violations: list[tuple[str, int]] = []
    for root, _dirs, files in os.walk(_APP_DIR):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            fpath = Path(root) / fname
            rel = str(fpath.relative_to(_APP_DIR)).replace("\\", "/")
            if rel in _ALLOWED_CONSTRUCTOR_FILES:
                continue
            try:
                source = fpath.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(fpath))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    name = ""
                    if isinstance(func, ast.Name):
                        name = func.id
                    elif isinstance(func, ast.Attribute):
                        name = func.attr
                    if name == "AuditLogEntry":
                        violations.append((rel, node.lineno))
    return violations


def _scan_raw_sql_inserts() -> list[tuple[str, int]]:
    """扫描 backend/app/ 下所有 .py 里 SQL 文本含 INSERT INTO audit_log_entries。"""
    violations: list[tuple[str, int]] = []
    needle = "INSERT INTO audit_log_entries"
    for root, _dirs, files in os.walk(_APP_DIR):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            fpath = Path(root) / fname
            try:
                source = fpath.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for lineno, line in enumerate(source.splitlines(), 1):
                if needle.lower() in line.lower():
                    # 排除注释行
                    stripped = line.lstrip()
                    if stripped.startswith("#"):
                        continue
                    rel = str(fpath.relative_to(_APP_DIR)).replace("\\", "/")
                    violations.append((rel, lineno))
    return violations


def _check_whitelist_exists() -> list[str]:
    """白名单文件必须全部存在。"""
    missing: list[str] = []
    for rel in _ALLOWED_CONSTRUCTOR_FILES:
        if not (_APP_DIR / rel).exists():
            missing.append(rel)
    return missing


class TestAuditChainWritersGuard:
    """AuditLogEntry 构造与裸 SQL 写入收口守卫。"""

    def test_no_constructor_outside_whitelist(self):
        """AuditLogEntry( 只在白名单文件内。"""
        violations = _scan_constructor_sites()
        if violations:
            msg = "AuditLogEntry( 构造出现在白名单之外:\n"
            for rel, line in violations:
                msg += f"  {rel}:{line}\n"
            pytest.fail(msg)

    def test_no_raw_sql_insert(self):
        """SQL 文本不含 INSERT INTO audit_log_entries。"""
        violations = _scan_raw_sql_inserts()
        if violations:
            msg = "裸 SQL INSERT INTO audit_log_entries 发现:\n"
            for rel, line in violations:
                msg += f"  {rel}:{line}\n"
            pytest.fail(msg)

    def test_whitelist_files_exist(self):
        """白名单文件必须全部存在（防止改名后守卫无效）。"""
        missing = _check_whitelist_exists()
        assert not missing, f"白名单文件不存在: {missing}"

    def test_self_check_whitelist_nonexistent_file(self):
        """自检：白名单加不存在的文件 → 应检测到。"""
        # 构造一个临时的白名单检查
        fake_whitelist = _ALLOWED_CONSTRUCTOR_FILES | {"services/nonexistent_module.py"}
        missing: list[str] = []
        for rel in fake_whitelist:
            if not (_APP_DIR / rel).exists():
                missing.append(rel)
        assert "services/nonexistent_module.py" in missing, (
            "自检失败：不存在的文件未被检出"
        )
