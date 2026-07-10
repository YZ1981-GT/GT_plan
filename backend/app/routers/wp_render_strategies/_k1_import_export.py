"""K1 其他应收款 — 导入导出（4张动态行表: K1-2/K1-5/K1-7/K1-8）."""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ────────────────────────────────────────────────────────────
# K1-2 明细表（17列）
# ────────────────────────────────────────────────────────────
_K1_2_HEADERS = [
    "往来对象", "性质", "关联关系", "期初余额", "期末余额",
    "1年内", "1-2年", "2-3年", "3-4年", "4-5年", "5年以上",
    "阶段", "坏账准备", "净值", "凭证号", "结论", "备注",
]
_K1_2_KEYS = [
    "counterparty", "nature", "relatedParty", "openingBalance", "closingBalance",
    "agingLt1", "aging1to2", "aging2to3", "aging3to4", "aging4to5", "agingGt5",
    "stage", "badDebtProvision", "netValue", "voucherNo", "conclusion", "remark",
]

# ────────────────────────────────────────────────────────────
# K1-5 大额分析（7列）
# ────────────────────────────────────────────────────────────
_K1_5_HEADERS = [
    "往来对象", "期末余额", "性质", "形成原因", "预计收回时间", "收回可能性", "后续核查",
]
_K1_5_KEYS = [
    "counterparty", "closingBalance", "nature", "formationReason", "expectedRecoveryTime", "recoveryPossibility", "followUpCheck",
]

# ────────────────────────────────────────────────────────────
# K1-7 三阶段划分（7列）
# ────────────────────────────────────────────────────────────
_K1_7_HEADERS = [
    "往来对象", "期末余额", "信用风险是否显著增加", "是否已发生信用减值", "划分阶段", "上期阶段", "变动说明",
]
_K1_7_KEYS = [
    "counterparty", "closingBalance", "significantIncrease", "isImpaired", "currentStage", "priorStage", "changeNote",
]

# ────────────────────────────────────────────────────────────
# K1-8 坏账测算 — 两个区段（账龄Tab + ECL Tab）合并为宽表导出
# 账龄Tab: 账龄区间/期末余额/迁徙率/预期损失率
# ECL Tab: 往来对象/EAD/PD/LGD/企业计提/测算结论
# ────────────────────────────────────────────────────────────
_K1_8_HEADERS = [
    "账龄区间", "期末余额", "迁徙率", "预期损失率",
    "往来对象", "EAD", "PD", "LGD", "企业计提", "测算结论",
]
_K1_8_KEYS = [
    "agingBucket", "closingBalance", "migrationRate", "expectedLossRate",
    "counterparty", "ead", "pd", "lgd", "bookedProvision", "calcConclusion",
]

# ────────────────────────────────────────────────────────────
# Sheet Specs 汇总
# ────────────────────────────────────────────────────────────
_K1_SPECS: dict[str, dict[str, Any]] = {
    "K1-2": {
        "item_id": "K1-2-rows",
        "title": "K1-2 其他应收款明细表",
        "headers": _K1_2_HEADERS,
        "field_keys": _K1_2_KEYS,
        # 动态账龄列头（Task 12.1）：导出时基础列 + 项目账龄配置派生的 3N 账龄列（期初/期末未审/期末审定）
        "aging": {
            "subject": "K1",
            "base_headers": [
                "往来对象", "性质", "关联关系", "期初余额", "期末余额",
                "阶段", "坏账准备", "净值", "凭证号", "结论", "备注",
            ],
            "base_field_keys": [
                "counterparty", "nature", "relatedParty", "openingBalance", "closingBalance",
                "stage", "badDebtProvision", "netValue", "voucherNo", "conclusion", "remark",
            ],
        },
        "guidance": [
            "K1-2 明细表 编制说明",
            "",
            "17列对应：往来对象/性质/关联关系/期初余额/期末余额/1年内~5年以上(6档账龄)/阶段/坏账准备/净值/凭证号/结论/备注。",
            "期末余额应等于各账龄区间之和。净值=期末余额-坏账准备。",
            "账龄区间金额为数值型，单位：元。",
        ],
    },
    "K1-5": {
        "item_id": "K1-5-rows",
        "title": "K1-5 大额其他应收款情况分析表",
        "headers": _K1_5_HEADERS,
        "field_keys": _K1_5_KEYS,
        "guidance": [
            "K1-5 大额分析 编制说明",
            "",
            "填列金额较大（超过重要性水平）的其他应收款，逐笔分析形成原因及收回可能性。",
            "收回可能性填：很可能/可能/极小可能。",
        ],
    },
    "K1-7": {
        "item_id": "K1-7-rows",
        "title": "K1-7 三阶段划分检查表",
        "headers": _K1_7_HEADERS,
        "field_keys": _K1_7_KEYS,
        "guidance": [
            "K1-7 三阶段划分 编制说明",
            "",
            "阶段判定规则：已减值→Stage3；信用风险显著增加→Stage2；否则→Stage1。",
            "信用风险是否显著增加 / 是否已发生信用减值 填 是/否。",
            "划分阶段填 1/2/3 或 Stage1/Stage2/Stage3。",
        ],
    },
    "K1-8": {
        "item_id": "K1-8-rows",
        "title": "K1-8 坏账准备测算（账龄+ECL合并宽表）",
        "headers": _K1_8_HEADERS,
        "field_keys": _K1_8_KEYS,
        "guidance": [
            "K1-8 坏账测算 编制说明",
            "",
            "前4列为账龄迁徙区段：账龄区间/期末余额/迁徙率/预期损失率。",
            "后6列为ECL测算区段：往来对象/EAD/PD/LGD/企业计提/测算结论。",
            "ECL=EAD×PD×LGD；预期损失=期末余额×预期损失率。",
            "两区段行数可能不同，空行跳过。",
        ],
    },
}

router = create_cycle_import_export_router(tag="k1-import-export", api_prefix="k1", specs=_K1_SPECS)
