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


def test_no_item_id_belongs_to_two_wp_codes():
    """每个推送目标 item_id 只属于一个 wp_code（不跨批次）。"""
    from app.services.formula_push.rules import RULES_PATH, load_rules

    rules = load_rules()
    seen: dict[str, str] = {}
    for r in rules:
        if r.target.domain != "workpaper":
            continue
        item = r.target.item_id
        if item in seen:
            assert seen[item] == r.wp_code, (
                f"item_id {item} 被 {seen[item]} 和 {r.wp_code} 两个批次的规则写"
            )
        seen[item] = r.wp_code


def test_check_mode_idempotent():
    """--check 重复运行结果一致。"""
    r1 = _run_gen(check=True)
    r2 = _run_gen(check=True)
    assert r1.returncode == r2.returncode == 0
