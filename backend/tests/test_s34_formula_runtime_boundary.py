"""P1.4 S34 runtime 与 formula-push 治理边界守卫。"""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = ROOT / "backend" / "data" / "formula_push_rules.json"
RUNTIME_PATH = (
    ROOT
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "s34-ipo-bundle"
    / "useS34FormulaEngine.ts"
)


def test_s34_is_absent_from_formula_push_rules() -> None:
    """S34 本地 runtime 公式不得变成推送到目标底稿/TB 的规则。"""
    document = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    s_rules = [
        rule
        for rule in document.get("rules", [])
        if str(rule.get("target", {}).get("wp_code", "")).upper().startswith("S")
    ]
    assert s_rules == []


def test_s34_runtime_has_no_formula_push_or_governance_import() -> None:
    """runtime 文件只能计算传入网格，不通过 import 接入后端治理/推送链。"""
    source = RUNTIME_PATH.read_text(encoding="utf-8")
    import_lines = [
        line.strip()
        for line in source.splitlines()
        if line.lstrip().startswith(("import ", "export ")) and " from " in line
    ]
    assert not any("formula_push" in line or "formula_settings" in line for line in import_lines)
    assert "fetch(" not in source
    assert "axios" not in source
