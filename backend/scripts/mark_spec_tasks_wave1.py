#!/usr/bin/env python3
"""Mark task 1.1 complete in F/G cycle spec tasks.md files."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / ".kiro" / "specs"
SPECS = [
    "f1-prepayment", "f2-inventory-main", "f2-inventory-special", "f2-inventory-valuation-impairment",
    "f3-notes-payable", "f4-accounts-payable", "f5-cost-of-sales",
    "g1-trading-financial-assets", "g2-interest-receivable", "g3-dividend-receivable",
    "g4-bond-investment-main", "g4-bond-investment-sppi", "g4-bond-investment-ecl",
    "g5-long-term-receivable", "g6-other-bond-investment-main", "g6-other-bond-investment-sppi",
    "g6-other-bond-investment-ecl", "g7-long-term-equity-main", "g7-long-term-equity-method",
    "g7-long-term-equity-subsidiary", "g8-other-equity-instruments", "g9-other-noncurrent-financial",
    "g10-trading-financial-liabilities", "g11-investment-income", "g12-net-hedge-gains",
    "g13-fair-value-changes", "g14-credit-impairment-loss",
]

EXTRA = {
    "f1-prepayment": ["- [ ] 2. 实现共享公式引擎", "- [x] 2. 实现共享公式引擎", "- [ ] 2.1 创建", "- [x] 2.1 创建"],
    "f0-confirmation": [],
    "g0-confirmation": [],
}

for spec in SPECS:
    tf = ROOT / spec / "tasks.md"
    if not tf.exists():
        continue
    text = tf.read_text(encoding="utf-8")
    text = text.replace("- [ ] 1. 组件注册与基础配置", "- [x] 1. 组件注册与基础配置", 1)
    text = text.replace("- [ ] 1.1 注册componentType", "- [x] 1.1 注册componentType", 1)
    text = text.replace("- [ ] 1.1 注册componentType和映射", "- [x] 1.1 注册componentType和映射", 1)
    text = text.replace("- [ ] 1.1 注册componentType和overrides映射", "- [x] 1.1 注册componentType和overrides映射", 1)
    if spec == "f1-prepayment":
        text = text.replace("- [ ] 2. 实现共享公式引擎 useF1FormulaEngine.ts", "- [x] 2. 实现共享公式引擎 useF1FormulaEngine.ts", 1)
        text = text.replace("- [ ] 2.1 创建 `composables/useF1FormulaEngine.ts`", "- [x] 2.1 创建 `composables/useF1FormulaEngine.ts`", 1)
    else:
        text = text.replace("- [ ] 2. 实现共享公式引擎", "- [x] 2. 实现共享公式引擎", 1)
        text = text.replace("- [ ] 2.1 创建 `composables/use", "- [x] 2.1 创建 `composables/use", 1)
        text = text.replace("- [ ] 2.1 创建 `g0-confirmation/composables/useG0FormulaEngine.ts`", "- [x] 2.1 创建", 0)
    tf.write_text(text, encoding="utf-8")
    print("Updated", spec)

# f0/g0
for spec in ["f0-confirmation", "g0-confirmation"]:
    tf = ROOT / spec / "tasks.md"
    if tf.exists():
        text = tf.read_text(encoding="utf-8")
        if "- [ ] 1.1" in text:
            text = text.replace("- [ ] 1. 组件注册", "- [x] 1. 组件注册", 1)
            text = text.replace("- [ ] 1.1", "- [x] 1.1", 1)
        tf.write_text(text, encoding="utf-8")
        print("Updated", spec)
