#!/usr/bin/env python3
"""Patch htmlRendererRegistry + VALID_COMPONENT_TYPES + F1 overrides."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "audit-platform/frontend/src/components/workpaper/htmlRendererRegistry.ts"
REGISTRY_SPEC = ROOT / "audit-platform/frontend/src/components/workpaper/__tests__/htmlRendererRegistry.spec.ts"
CLASSIFY = ROOT / "backend/app/services/wp_classification_service.py"
OVERRIDES = ROOT / "backend/app/data/wp_code_overrides.json"

ENTRIES = [
    ("f1-prepayment", "GtF1Prepayment", "💳", "F1 预付账款"),
    ("f2-inventory-main", "GtF2InventoryMain", "📦", "F2 存货核心"),
    ("f2-inventory-special", "GtF2InventorySpecial", "📦", "F2 存货特殊"),
    ("f2-inventory-valuation-impairment", "GtF2InventoryValuation", "📦", "F2 计价减值"),
    ("f3-notes-payable", "GtF3NotesPayable", "📄", "F3 应付票据"),
    ("f4-accounts-payable", "GtF4AccountsPayable", "📋", "F4 应付账款"),
    ("f5-cost-of-sales", "GtF5CostOfSales", "📊", "F5 营业成本"),
    ("g1-trading-financial-assets", "GtG1TradingFinancialAssets", "📈", "G1 交易性金融资产"),
    ("g2-interest-receivable", "GtG2InterestReceivable", "💰", "G2 应收利息"),
    ("g3-dividend-receivable", "GtG3DividendReceivable", "💰", "G3 应收股利"),
    ("g4-bond-investment-main", "GtG4BondInvestmentMain", "🏦", "G4 债权投资"),
    ("g4-bond-investment-sppi", "GtG4BondInvestmentSppi", "🏦", "G4 SPPI"),
    ("g4-bond-investment-ecl", "GtG4BondInvestmentEcl", "🏦", "G4 ECL"),
    ("g5-long-term-receivable", "GtG5LongTermReceivable", "📑", "G5 长期应收款"),
    ("g6-other-bond-investment-main", "GtG6OtherBondMain", "🏦", "G6 其他债权投资"),
    ("g6-other-bond-investment-sppi", "GtG6OtherBondSppi", "🏦", "G6 SPPI"),
    ("g6-other-bond-investment-ecl", "GtG6OtherBondEcl", "🏦", "G6 ECL"),
    ("g7-long-term-equity-main", "GtG7LongTermEquityMain", "🏢", "G7 长期股权投资"),
    ("g7-long-term-equity-method", "GtG7EquityMethod", "🏢", "G7 权益法"),
    ("g7-long-term-equity-subsidiary", "GtG7EquitySubsidiary", "🏢", "G7 子公司"),
    ("g8-other-equity-instruments", "GtG8OtherEquityInstruments", "📈", "G8 其他权益工具"),
    ("g9-other-noncurrent-financial", "GtG9OtherNoncurrentFinancial", "📈", "G9 其他非流动金融"),
    ("g10-trading-financial-liabilities", "GtG10TradingFinancialLiabilities", "📉", "G10 交易性金融负债"),
    ("g11-investment-income", "GtG11InvestmentIncome", "💹", "G11 投资收益"),
    ("g12-net-hedge-gains", "GtG12NetHedgeGains", "🛡️", "G12 套期收益"),
    ("g13-fair-value-changes", "GtG13FairValueChanges", "📊", "G13 公允价值变动"),
    ("g14-credit-impairment-loss", "GtG14CreditImpairmentLoss", "⚠️", "G14 信用减值损失"),
]


def patch_classify() -> None:
    text = CLASSIFY.read_text(encoding="utf-8")
    for comp, _, _, _ in ENTRIES:
        if f'"{comp}"' not in text:
            text = text.replace(
                '"f2-inventory-main",\n}',
                f'"f2-inventory-main",\n    "{comp}",\n}}',
                1,
            )
    # dedupe: if f2 was only one, add all missing in one block
    missing = [c for c, _, _, _ in ENTRIES if f'"{c}"' not in text]
    if missing:
        block = "\n".join(f'    "{c}",' for c in missing)
        text = text.replace(
            '"f2-inventory-main",\n}',
            '"f2-inventory-main",\n' + block + "\n}",
            1,
        )
    CLASSIFY.write_text(text, encoding="utf-8")


def patch_registry() -> None:
    text = REGISTRY.read_text(encoding="utf-8")
    # type union
    for comp, _, _, _ in ENTRIES:
        if f"| '{comp}'" not in text and f"'{comp}'" not in text.split("export type HtmlComponentType")[1][:3000]:
            text = text.replace(
                "  | 'confirmation-alternative-g06'\n",
                f"  | 'confirmation-alternative-g06'\n  | '{comp}'\n",
                1,
            )
    # lazy imports before registry section
    marker = "// ─── 注册表（单一来源） ─────────────────────────────────────────────────────"
    imports = []
    registry_blocks = []
    for comp, vue, icon, label in ENTRIES:
        const = vue
        if f"const {const} =" not in text:
            imports.append(
                f"const {const} = defineAsyncComponent(() => import('./{vue}.vue'))"
            )
        if f"componentType: '{comp}'" not in text:
            registry_blocks.append(f"""  {{
    componentType: '{comp}',
    component: {const},
    icon: '{icon}',
    label: '{label}',
    emits: ['save', 'completed'],
    contextProps: 'standard',
  }},""")
    if imports:
        text = text.replace(marker, "\n".join(imports) + "\n\n" + marker)
    if registry_blocks:
        text = text.replace(
            "    componentType: 'd3-prepaid-accounts',",
            "\n".join(registry_blocks) + "\n    componentType: 'd3-prepaid-accounts',",
        )
    REGISTRY.write_text(text, encoding="utf-8")


def patch_registry_spec() -> None:
    text = REGISTRY_SPEC.read_text(encoding="utf-8")
    for comp, _, _, _ in ENTRIES:
        if f"'{comp}'" not in text:
            text = text.replace(
                "      'confirmation-alternative-g06',\n",
                f"      'confirmation-alternative-g06',\n      '{comp}',\n",
                1,
            )
    REGISTRY_SPEC.write_text(text, encoding="utf-8")


def patch_f1_overrides() -> None:
    data = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    for key in list(data.keys()):
        if key == "F1" or (key.startswith("F1-") and key[3:4].isdigit()):
            data[key] = "f1-prepayment"
    OVERRIDES.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    patch_classify()
    patch_registry()
    patch_registry_spec()
    patch_f1_overrides()
    print("Registry/classify/F1 overrides patched.")


if __name__ == "__main__":
    main()
