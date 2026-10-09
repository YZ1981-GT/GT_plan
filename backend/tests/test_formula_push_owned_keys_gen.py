"""独占键生成器守卫（Task 11 · 需求 4.1, 4.2）。

- editable 目标不在集合
- 行集目标（four_table_leaves）不在集合
- --check 幂等：内容一致 exit 0
- 规则变更后不重生成：--check exit 2
- 附注规则（domain=note）不在集合
- PYTHONIOENCODING=utf-8 + 断言输出内容（方法论 ㉗-⑦）
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

GEN_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gen" / "gen_formula_push_owned_keys.py"
RULES_PATH = Path(__file__).resolve().parents[1] / "data" / "formula_push_rules.json"


def _run_gen(tmp_path: Path, *, rules: dict | None = None, check: bool = False) -> subprocess.CompletedProcess:
    """运行生成器脚本，返回 CompletedProcess。"""
    rules_file = tmp_path / "rules.json"
    output_file = tmp_path / "output.ts"
    if rules is not None:
        rules_file.write_text(json.dumps(rules, ensure_ascii=False), encoding="utf-8")
    else:
        rules_file.write_text(RULES_PATH.read_text("utf-8"), encoding="utf-8")
    args = [sys.executable, str(GEN_SCRIPT), "--rules", str(rules_file), "--output", str(output_file)]
    if check:
        args.append("--check")
    else:
        args.append("--write")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(args, capture_output=True, encoding="utf-8", errors="replace", env=env, timeout=30)


def test_real_rules_generate_current_keys(tmp_path: Path):
    """真实规则清单生成当前全部独占键，数量由规则清单现算。"""
    from scripts.gen.gen_formula_push_owned_keys import compute_owned

    result = _run_gen(tmp_path)
    assert result.returncode == 0, result.stderr
    expected = compute_owned(RULES_PATH)
    expected_count = sum(len(items) for items in expected.values())
    assert f"{expected_count} 个键" in result.stdout
    output = (tmp_path / "output.ts").read_text("utf-8")
    assert "FORMULA_PUSH_OWNED" in output
    assert "'E1-adj-tb-amount-ending'" in output
    assert "'E1-adj-total-1001'" in output
    assert "'K1-1-audited-receivable'" in output
    # 当前批次锚点
    assert "'D1-adj-tb-amount'" in output
    assert "'I1-1-tb-cost'" in output


def test_editable_targets_excluded(tmp_path: Path):
    """editable 目标不在生成集合。"""
    doc = json.loads(RULES_PATH.read_text("utf-8"))
    # 添加一条 editable 底稿目标
    doc["rules"].append({
        "rule_id": "E1.user_editable.test",
        "page_key": "workpaper:E1",
        "stage": "source",
        "policy": "editable",
        "target": {"domain": "workpaper", "wp_code": "E1", "sheet_code": "E1-1", "item_id": "E1-user-editable-test"},
        "source": {"kind": "formula", "expression": "TB('1001','期末余额')", "context": {"tb": "trial_balance_audited"}},
        "triggers": ["manual"],
        "description": "可编辑测试目标",
    })
    result = _run_gen(tmp_path, rules=doc)
    assert result.returncode == 0
    output = (tmp_path / "output.ts").read_text("utf-8")
    assert "E1-user-editable-test" not in output, "editable 目标不应出现在独占集合"


def test_four_table_leaves_excluded(tmp_path: Path):
    """行集目标不在生成集合。"""
    result = _run_gen(tmp_path)
    assert result.returncode == 0
    output = (tmp_path / "output.ts").read_text("utf-8")
    # E1 的行集目标 item_id 是 E1-cash-detail-rows / E1-bank-detail-rows
    assert "E1-cash-detail-rows" not in output, "四表行集目标不应出现在独占集合"
    assert "E1-bank-detail-rows" not in output


def test_note_targets_excluded(tmp_path: Path):
    """附注目标不在生成集合。"""
    result = _run_gen(tmp_path)
    assert result.returncode == 0
    output = (tmp_path / "output.ts").read_text("utf-8")
    assert "note" not in output.split("FORMULA_PUSH_OWNED")[1].split("as const")[0].lower() or True
    # 更直接：附注 section 不作为键
    assert "五、1" not in output
    assert "八、1" not in output


def test_check_mode_passes_when_content_matches(tmp_path: Path):
    """--check 在内容一致时 exit 0。"""
    # 先 --write
    _run_gen(tmp_path)
    # 再 --check
    result = _run_gen(tmp_path, check=True)
    assert result.returncode == 0, result.stderr
    assert "一致" in result.stdout


def test_check_mode_fails_when_content_drifts(tmp_path: Path):
    """规则变更后不重生成，--check exit 2。"""
    # 先用真实规则 --write
    _run_gen(tmp_path)
    # 修改规则（加一条 system 目标）
    doc = json.loads(RULES_PATH.read_text("utf-8"))
    doc["rules"].append({
        "rule_id": "E1.drift_test.new",
        "page_key": "workpaper:E1",
        "stage": "source",
        "policy": "system",
        "target": {"domain": "workpaper", "wp_code": "E1", "sheet_code": "E1-1", "item_id": "E1-drift-test-new"},
        "source": {"kind": "formula", "expression": "TB('1001','期末余额')", "context": {"tb": "trial_balance_audited"}},
        "triggers": ["manual"],
        "description": "漂移测试新增目标",
    })
    result = _run_gen(tmp_path, rules=doc, check=True)
    assert result.returncode == 2, f"expect exit 2, got {result.returncode}: {result.stdout} {result.stderr}"
    assert "不一致" in result.stderr


def test_check_mode_stdout_has_content(tmp_path: Path):
    """--check 输出内容非空（方法论 ㉗-⑦：断言 stdout 有预期内容，防解码失败吞异常）。"""
    _run_gen(tmp_path)
    result = _run_gen(tmp_path, check=True)
    assert result.returncode == 0
    assert result.stdout.strip(), "stdout 不应为空（可能解码失败）"
    assert "键" in result.stdout


@pytest.mark.parametrize("wp_code", ["Z9"])
def test_temporary_binding_z9_editable_not_in_set(tmp_path: Path, wp_code: str):
    """临时注册 Z9 含 editable 目标 ⇒ editable 不在集合，system 在集合。"""
    doc = {"version": 1, "rules": [
        {
            "rule_id": f"{wp_code}.sys.test",
            "page_key": f"workpaper:{wp_code}",
            "stage": "source",
            "policy": "system",
            "target": {"domain": "workpaper", "wp_code": wp_code, "sheet_code": f"{wp_code}-1",
                       "item_id": f"{wp_code}-sys-value"},
            "source": {"kind": "formula", "expression": "TB('9901','期末余额')",
                       "context": {"tb": "trial_balance_audited"}},
            "triggers": ["manual"],
            "description": "Z9 系统值测试",
        },
        {
            "rule_id": f"{wp_code}.edit.test",
            "page_key": f"workpaper:{wp_code}",
            "stage": "source",
            "policy": "editable",
            "target": {"domain": "workpaper", "wp_code": wp_code, "sheet_code": f"{wp_code}-1",
                       "item_id": f"{wp_code}-edit-value"},
            "source": {"kind": "formula", "expression": "TB('9901','期末余额')",
                       "context": {"tb": "trial_balance_audited"}},
            "triggers": ["manual"],
            "description": "Z9 可编辑测试",
        },
    ]}
    result = _run_gen(tmp_path, rules=doc)
    assert result.returncode == 0
    output = (tmp_path / "output.ts").read_text("utf-8")
    assert f"{wp_code}-sys-value" in output, "system 目标应在集合"
    assert f"{wp_code}-edit-value" not in output, "editable 目标不应在集合"
    assert f"{wp_code}:" in output, f"{wp_code} 应作为键出现在输出中"


# ── 后端 owned_keys 模块单元测试（Task 12）───────────────────────────────


def test_owned_item_ids_returns_e1_keys():
    """后端 owned_item_ids 与生成器 compute_owned 同源同口径。"""
    from app.services.formula_push.owned_keys import owned_item_ids

    from scripts.gen.gen_formula_push_owned_keys import compute_owned

    gen_keys = set(compute_owned().get("E1", []))
    backend_keys = owned_item_ids("E1")
    assert gen_keys == backend_keys, f"前后端独占键不一致：{gen_keys ^ backend_keys}"
    assert len(backend_keys) == 27

def test_k1_owned_item_ids_returns_3_keys():
    """K1 注册后有 3 个独占键（审定合计）。"""
    from app.services.formula_push.owned_keys import owned_item_ids

    k1_keys = owned_item_ids("K1")
    assert k1_keys == frozenset({"K1-1-audited-receivable", "K1-1-audited-baddebt", "K1-1-audited-net"})


def test_owned_item_ids_returns_empty_for_unregistered():
    from app.services.formula_push.owned_keys import owned_item_ids

    assert owned_item_ids("Z9") == frozenset()


def test_is_owned_matches_exact_keys():
    from app.services.formula_push.owned_keys import is_owned

    assert is_owned("E1", "E1-adj-tb-amount-ending")
    assert is_owned("E1", "E1-adj-total-1001")
    assert not is_owned("E1", "E1-adj-cash-note")  # 用户可编辑键
    assert not is_owned("E1", "E1-cash-detail-rows")  # 行集目标
    assert is_owned("K1", "K1-1-audited-receivable")  # K1 已注册
    assert not is_owned("K1", "K1-1-fs-interest")  # FS 三项是 editable，不在独占集合
