"""D~N / S 多 sheet 专属组件类型 — 单一来源。

整册统一路由（WHOLE_WP）与契约测试共用此常量，避免
`wp_render_config._WHOLE_WP_MULTISHEET_DEDICATED` 与 VALID / FE 三处手写漂移。

新增专属组件时：
1. 在此集合追加 componentType
2. 同步 VALID_COMPONENT_TYPES + htmlRendererRegistry + RENDERER_DISPATCH（或 WHITELIST/CONFIRMATION）
3. 跑 test_dedicated_component_registry_contract.py
"""

from __future__ import annotations

# 多 sheet 工作簿整册路由到同一专属 componentType（65 项）
DEDICATED_COMPONENT_TYPES: frozenset[str] = frozenset(
    {
        # A/B 多 sheet Bundle（整册路由到同一专属组件，子 sheet 如 B19-1=skip 由 Bundle 内打开）
        "a10-bundle",
        "a11-bundle",
        "a12-bundle",
        "a15-bundle",
        "a16-bundle",
        "a17-bundle",
        "b2-bundle",
        "b13-bundle",
        "b19-bundle",
        "b51-bundle",
        # C 控制测试 / 向导
        "c1-entity-level-control",
        "c-control-test",
        "c22-itgc-bundle",
        "c23-journal-entry-control",
        "c24-journal-entry-detail",
        # H 固定资产循环
        "h1-fixed-assets",
        "h2-construction-in-progress",
        "h3-investment-property",
        "h4-engineering-materials",
        "h6-asset-disposal-clearing",
        "h8-right-of-use-assets",
        "h9-lease-liabilities",
        "h10-asset-disposal-income",
        "h5-oil-gas-assets",
        "h7-biological-assets",
        # I 无形资产循环
        "i1-intangible-assets",
        "i2-development-expenditure",
        "i3-goodwill",
        "i4-long-term-prepaid",
        "i5-other-noncurrent-assets",
        "i6-research-development-expense",
        # J 职工薪酬
        "j1-employee-compensation",
        "j2-defined-benefit-plan",
        "j3-share-based-payment",
        # K 管理循环
        "k1-other-receivables",
        "k2-other-current-assets",
        "k3-other-payables",
        "k4-other-current-liabilities",
        "k5-provisions",
        "k6-held-for-sale",
        "k7-deferred-income",
        "k8-selling-expenses",
        "k9-admin-expenses",
        "k10-other-income",
        "k11-asset-impairment-loss",
        "k12-non-operating-income",
        "k13-non-operating-expense",
        # L 债务循环
        "l1-short-term-loans",
        "l2-interest-payable",
        "l3-long-term-loans",
        "l4-bonds-payable",
        "l5-long-term-payables",
        "l6-special-payables",
        "l7-other-noncurrent-liabilities",
        "l8-financial-expenses",
        # M 权益循环
        "m1-dividends-payable",
        "m2-paid-in-capital",
        "m3-treasury-stock",
        "m4-capital-reserve",
        "m5-surplus-reserve",
        "m6-retained-earnings",
        "m7-special-reserve",
        "m8-general-risk-reserve",
        "m9-other-comprehensive-income",
        "m10-other-equity-instruments",
        # N 税费循环
        "n1-deferred-tax-assets",
        "n2-taxes-payable",
        "n3-deferred-tax-liabilities",
        "n4-taxes-and-surcharges",
        "n5-income-tax-expense",
        # S 特定项目
        "s3-policy-change",
        "s4-nonmonetary-exchange",
        "s5-debt-restructuring",
        "s6-fund-occupation",
        "s12-cpa-expert",
        "s13-mgmt-expert",
        "s14-accounting-estimate",
        "s15-eps-roe",
        "s20-revenue-deduction",
        "s21-data-asset",
        "s32-fraud-bundle",
        "s33-ann14-bundle",
    }
)
