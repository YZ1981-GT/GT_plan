"""wp_account_mapping.json 去重守护测试。

确保 wp_code 无重复条目（多轮 subagent 执行可能导致重复追加）。
"""
from __future__ import annotations

import json
from pathlib import Path

_MAPPING_PATH = Path(__file__).resolve().parent.parent / "data" / "wp_account_mapping.json"


def test_no_duplicate_wp_codes():
    """wp_account_mapping.json 中不应有重复的 wp_code。"""
    with open(_MAPPING_PATH, encoding="utf-8") as f:
        data = json.load(f)
    mappings = data.get("mappings", data) if isinstance(data, dict) else data
    codes = [e["wp_code"] for e in mappings]
    duplicates = [c for c in set(codes) if codes.count(c) > 1]
    assert not duplicates, f"发现重复 wp_code ({len(duplicates)} 个): {sorted(duplicates)}"


def test_wp_codes_non_empty():
    """每个条目的 wp_code 不为空。"""
    with open(_MAPPING_PATH, encoding="utf-8") as f:
        data = json.load(f)
    mappings = data.get("mappings", data) if isinstance(data, dict) else data
    for i, entry in enumerate(mappings):
        assert entry.get("wp_code"), f"第 {i} 条缺少 wp_code: {entry}"


def test_wp_codes_no_whitespace():
    """wp_code 不含前后空格。"""
    with open(_MAPPING_PATH, encoding="utf-8") as f:
        data = json.load(f)
    mappings = data.get("mappings", data) if isinstance(data, dict) else data
    for entry in mappings:
        code = entry.get("wp_code", "")
        assert code == code.strip(), f"wp_code 有空格: '{code}'"
