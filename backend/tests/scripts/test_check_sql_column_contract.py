"""Tests for check_sql_column_contract.py — SQL 列契约检查脚本。

验收标准：脚本可在无 DB 连接时部分运行（allowlist + regex 提取测试）。
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def test_allowlist_is_valid_json():
    """白名单文件是合法 JSON 且包含 allowed_references 列表。"""
    allowlist_path = Path(__file__).resolve().parents[2] / "scripts" / "check" / "sql_column_contract_allowlist.json"
    assert allowlist_path.exists(), f"allowlist not found: {allowlist_path}"

    data = json.loads(allowlist_path.read_text(encoding="utf-8"))
    assert "allowed_references" in data
    assert isinstance(data["allowed_references"], list)
    assert len(data["allowed_references"]) > 0


def test_extract_column_refs_qualified():
    """_extract_column_refs 提取 table.column 格式引用。"""
    from scripts.check.check_sql_column_contract import _extract_column_refs

    sql = "SELECT t.name, t.amount FROM trial_balance t WHERE t.project_id = :pid"
    refs = _extract_column_refs(sql)

    # Should extract t.name, t.amount, t.project_id
    assert ("t", "name") in refs
    assert ("t", "amount") in refs
    assert ("t", "project_id") in refs


def test_extract_column_refs_skips_python_patterns():
    """_extract_column_refs 跳过 Python 对象引用（self.xxx, os.path 等）。"""
    from scripts.check.check_sql_column_contract import _extract_column_refs

    sql = "self.value os.path json.dumps datetime.now"
    refs = _extract_column_refs(sql)

    assert len(refs) == 0, f"Should skip Python patterns, got: {refs}"


def test_extract_column_refs_skips_sql_functions():
    """_extract_column_refs 跳过 SQL 函数调用。"""
    from scripts.check.check_sql_column_contract import _extract_column_refs

    sql = "func.count func.sum func.now"
    refs = _extract_column_refs(sql)

    assert len(refs) == 0, f"Should skip SQL functions, got: {refs}"
