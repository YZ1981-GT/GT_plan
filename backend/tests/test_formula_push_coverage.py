"""接入等级清册守卫（Task 21 · 需求 6.1~6.3）。

- L3 集合 == 注册表
- 每个推送目标只属于一个 wp_code（不跨批次）
- --check 幂等
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

GEN_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gen" / "gen_formula_push_coverage.py"
COVERAGE_PATH = Path(__file__).resolve().parents[1] / "data" / "formula_push_coverage.json"


def _run_gen(*, check: bool = False) -> subprocess.CompletedProcess:
    args = [sys.executable, str(GEN_SCRIPT)]
    args.append("--check" if check else "--write")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(args, capture_output=True, encoding="utf-8", errors="replace", env=env, timeout=30)


def test_coverage_json_exists_and_matches_registry():
    """生成的清册与注册表一致。"""
    result = _run_gen(check=True)
    assert result.returncode == 0, result.stderr
    assert "一致" in result.stdout


def test_l3_codes_equal_registered_codes():
    """清册中 L3 集合 == 注册表 supported_wp_codes。"""
    from app.services.formula_push.bindings import supported_wp_codes

    coverage = json.loads(COVERAGE_PATH.read_text("utf-8"))
    registered = set(supported_wp_codes())
    l3_codes = {e["wp_code"] for e in coverage["entries"] if e["level"] == "L3"}
    assert l3_codes == registered, f"L3 {l3_codes} != 注册表 {registered}"


def test_coverage_rule_counts_and_note_flags_match_registry_rules():
    """清册的规则统计必须与规则清单逐编码一致。"""
    from app.services.formula_push.bindings import supported_wp_codes
    from app.services.formula_push.rules import load_rules

    coverage = json.loads(COVERAGE_PATH.read_text("utf-8"))
    entries = {entry["wp_code"]: entry for entry in coverage["entries"]}
    rules = load_rules()
    by_code: dict[str, list] = {code: [] for code in supported_wp_codes()}
    for rule in rules:
        by_code.setdefault(rule.wp_code, []).append(rule)

    assert set(by_code) == set(supported_wp_codes())
    assert set(entries) == set(supported_wp_codes())
    assert all(by_code[code] for code in supported_wp_codes())
    for code in supported_wp_codes():
        entry = entries[code]
        code_rules = by_code[code]
        assert entry["rule_count"] == len(code_rules), code
        assert entry["has_note_rules"] == any(rule.target.domain == "note" for rule in code_rules), code


def test_no_item_id_belongs_to_two_wp_codes():
    """每个推送目标 item_id 只属于一个 wp_code（不跨批次）。"""
    from app.services.formula_push.rules import load_rules

    rules = load_rules()
    seen: dict[str, str] = {}
    for rule in rules:
        if rule.target.domain != "workpaper":
            continue
        item = rule.target.item_id
        if item in seen:
            assert seen[item] == rule.wp_code, (
                f"item_id {item} 被 {seen[item]} 和 {rule.wp_code} 两个批次的规则写"
            )
        seen[item] = rule.wp_code


def test_check_mode_idempotent():
    """--check 重复运行结果一致。"""
    r1 = _run_gen(check=True)
    r2 = _run_gen(check=True)
    assert r1.returncode == r2.returncode == 0
