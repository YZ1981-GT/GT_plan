#!/usr/bin/env python
"""附注「所有权或使用权受到限制的资产」结构修订（listed 五、32 / soe 八、93）。

spec: .kiro/specs/restricted-assets-note-row-scope-rollout/ Task 3
Requirements 1.1~1.7

**这是 29 张多段共享表里受益面最大的一张**（owner 横跨 E1 / D1 / D2 / D5 / F2 /
H1 / H2 / I1），段边界读 `rows[].report_row_code`，故本脚本修的东西直接决定
行级合并把各循环的数据落到哪一行。

## 修什么（逐条都有真源依据）

1. **soe「应收款项融资」缺 `report_row_code`** → 补 `BS-007`
   （`report_config` 实证 `BS-007 应收款项融资 = TB('1124')`，与该行 `account_codes`
   一致）。现为 `null` → 被 `split_segments` 卷进上一段 `BS-006 应收账款`（D2），
   D2 一推数据就把 D5 的行覆盖掉。
2. **soe「存货」错码 `BS-008`** → `BS-010`
   （`report_config` 实证 `BS-008 = TB('1123')` **预付款项**、
   `BS-010 = SUM_TB('1401~1499')` 存货；listed 侧标的 `BS-010` 才对）。
3. **soe 末行「其他」标 `row_type = "unowned"`**（表级兜底行，不属任何 owner）。
   不标则 `BS-029 在建工程` 段的可写区含它 → H2 推送会删掉它。
   🔴「其他」这个标签**不能全局判定** —— `五、30`/`八、31` 递延所得税表里的
   「其他」是段内合法明细行，故只认模板的显式声明。
4. **listed 两表删 `row_type = "header_label"` 假行**（md 重建把压扁的第二行表头
   留成了数据行，会渲染成一行空披露数据）。
5. **三张子表补 `columns`（单级必标 `flat`）+ `guidance`**
   —— 现 `columns=0` → seed 路径会被 `_infer_groups_from_headers` 塞凭空父表头。
6. **「续：」正名**为「所有权或使用权受到限制的资产（续：上年年末）」
   —— 裸续表名会跨章节撞键（`sub_table_data` 以表名为键）。走 `rule(aliases=)`
   改名，**不能进 drops**（`drop_tables` 在 `apply_plan` 之前执行会连行一起删）。
7. **text_sections**：listed 的裸段落「续：」随表改名同步正名；soe 补源模板
   `A3-5/A3-6` R13 的「说明：各项资产受限的原因」提示。

## 源模板说明（诚实记录）

该披露表在 `backend/wp_templates/` 里**没有对应的披露 sheet** —— 全量扫描 349 个
xlsx 的结果是：只有 `A3-5 合并附注汇总-2019.xlsx` / `A3-6 母公司附注汇总-2019.xlsx`
的 sheet「所有权受限资产」（A1「所有权或使用权受到限制的资产附注汇总」），
那是**合并/母公司按主体横向展开的汇总工作表**（审定数/抵消数/汇总/母公司审定/
子公司1..N），行只有 货币资金/应收票据/存货/固定资产/无形资产 + 2 空行 + 合计，
**不是附注披露表本身**。

故本表的行集真源 = **附注模板**，段归属真源 = **`report_config`**；
A3-5/A3-6 的科目清单作**旁证**（守卫断言那 5 个科目都在附注模板里）。

用法（在仓库根）：
    python backend/scripts/fix/fix_note_restricted_assets_structure.py --dry-run
    python backend/scripts/fix/fix_note_restricted_assets_structure.py --check
    python backend/scripts/fix/fix_note_restricted_assets_structure.py          # 写入
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent))

from _note_structure_kit import (  # noqa: E402
    build_cli,
    flat_columns,
    rule,
    run_section,
)

_BACKEND = _HERE.parent.parent.parent
DATA_DIR = _BACKEND / "data"
LISTED_PATH = DATA_DIR / "note_template_listed.json"
SOE_PATH = DATA_DIR / "note_template_soe.json"

ALIGNED_BY = "fix_note_restricted_assets_structure.py"

# ── 表名（`sub_table_data` 以表名为键 → 错一个字就产生孤儿表）────────────────
LISTED_MAIN = "所有权或使用权受到限制的资产"
LISTED_PRIOR = "所有权或使用权受到限制的资产（续：上年年末）"
LISTED_PRIOR_LEGACY = "续："
SOE_MAIN = "所有权和使用权受到限制的资产"

#: 无主行标记（与 `app/services/note_shared_table_segments.UNOWNED_ROW_TYPE` 同值）
UNOWNED = "unowned"

# ── 段归属（`report_config` 实证；守卫会交叉校验同名报表行）──────────────────
#: `(label, report_row_code, account_codes)` —— **顺序即模板行序**
LISTED_SEGMENTS: list[tuple[str, str, list[str]]] = [
    ("货币资金", "BS-002", ["1001", "1002", "1012"]),
    ("应收票据", "BS-005", ["1121"]),
    ("应收账款", "BS-006", ["1122"]),
    ("存货", "BS-010", ["1401", "1402", "1403", "1405", "1408", "1461"]),
    ("固定资产", "BS-028", ["1601", "1602"]),
    ("无形资产", "BS-032", ["1701", "1702"]),
]
SOE_SEGMENTS: list[tuple[str, str, list[str]]] = [
    ("货币资金", "BS-002", ["1001", "1002", "1012"]),
    ("应收票据", "BS-005", ["1121"]),
    ("应收账款", "BS-006", ["1122"]),
    # 🔴 本次补码：现为 null → 被卷进上一段 BS-006（D2）
    ("应收款项融资", "BS-007", ["1124"]),
    # 🔴 本次纠错：现为 BS-008（预付款项）
    ("存货", "BS-010", ["1401", "1402", "1403", "1405", "1408", "1461"]),
    ("固定资产", "BS-028", ["1601", "1602"]),
    ("无形资产", "BS-032", ["1701", "1702"]),
    ("在建工程", "BS-029", ["1604"]),
]


def _seg_rows(segments: list[tuple[str, str, list[str]]]) -> list[dict[str, Any]]:
    return [
        {
            "label": label,
            "account_codes": list(codes),
            "report_row_code": code,
            "row_type": "data",
        }
        for label, code, codes in segments
    ]


def _listed_rows() -> list[dict[str, Any]]:
    """listed 两表同构：6 个科目段 + 可扩行 + 合计（**删掉 header_label 假行**）。"""
    return [
        *_seg_rows(LISTED_SEGMENTS),
        {"label": "……", "row_type": "data"},
        {"label": "合计", "is_total": True, "row_type": "total"},
    ]


def _soe_rows() -> list[dict[str, Any]]:
    """soe 单表：8 个科目段 + 表级兜底「其他」（**标 unowned**）。soe 侧无合计行。"""
    return [
        *_seg_rows(SOE_SEGMENTS),
        {"label": "其他", "row_type": UNOWNED},
    ]


# ── 列定义（单级 → 首列自动带 `is_label` + `flat`）────────────────────────────
COLS_LISTED_MAIN = flat_columns([
    ("label", "项目", None),
    ("end_amount", "期末", "amount"),
])
COLS_LISTED_PRIOR = flat_columns([
    ("label", "项目", None),
    ("prior_amount", "上年年末", "amount"),
])
COLS_SOE = flat_columns([
    ("label", "项目", None),
    ("end_carrying", "期末账面价值", "amount"),
    ("reason", "受限原因", "text"),
])

_OWNER_HINT = (
    "本表跨循环共享：每一行归属一个循环，段归属由 report_row_code 声明 —— "
    "货币资金 BS-002（E1）/ 应收票据 BS-005（D1）/ 应收账款 BS-006（D2）/ "
    "存货 BS-010（F2）/ 固定资产 BS-028（H1）/ 无形资产 BS-032（I1）。"
    "各循环推送时声明 sub_table_data._row_scope 只替换自己那一段，段外行原样保留；"
    "段边界解析不出时整表跳过写入而不退化为整表覆盖。"
)

GUIDANCE_LISTED_MAIN = (
    "按资产类别分项披露用于抵押、质押、查封、冻结、扣押等所有权或使用权受限资产的"
    "账面价值及受限情况（企业会计准则解释第15号第十九条（二十三））。"
    "本表只列期末数，上年年末数在「（续：上年年末）」表。"
    + _OWNER_HINT
    + "合计行是表级汇总，不属于任何循环，行级合并不会覆盖它；"
    "尚未接入推送的段可在附注模块直接填列，不会被他循环的推送清掉。"
)
GUIDANCE_LISTED_PRIOR = (
    "上年年末数（与主表同构，双期拆两张表）。"
    + _OWNER_HINT
    + "合计行是表级汇总，不属于任何循环。"
)
GUIDANCE_SOE = (
    "按资产类别列示期末账面价值与受限原因。受限原因须写明抵押/质押/查封/冻结/"
    "扣押的具体情形与对应借款或担保合同，货币资金段可对照 E1 底稿「受限制的货币资金"
    "明细」填列。"
    + _OWNER_HINT
    + "另有 应收款项融资 BS-007（D5）与 在建工程 BS-029（H2）两段为国企版专有。"
    "末行「其他」是表级兜底行，不属于任何循环（模板标 row_type=unowned），"
    "由审计师在附注模块直接填列，行级合并不会覆盖它。"
)

# listed 章节的 text_sections —— 首段原为裸表名「续：」，随表改名同步正名。
TEXT_SECTIONS_LISTED = [
    f"#### {LISTED_PRIOR}",
    "【提示：按资产类别分项披露用于抵押、质押、查封、冻结、扣押等所有权或使用权受限资产的"
    "账面余额、账面价值及受限情况。（15号文第十九条（二十三））】",
]
# soe 章节缺提示段 —— 补源模板 A3-5/A3-6 R13 的「说明：各项资产受限的原因」。
REQUIRE_TEXTS_SOE = [
    "【提示：说明各项资产受限的原因（抵押、质押、查封、冻结、扣押等），"
    "并与借款、担保等相关披露交叉核对。】",
]


def _plan_listed() -> list[dict[str, Any]]:
    return [
        rule(LISTED_MAIN, COLS_LISTED_MAIN, _listed_rows(), GUIDANCE_LISTED_MAIN),
        # 改名走 aliases（末项即目标名）；**不能进 drops**
        rule(
            LISTED_PRIOR,
            COLS_LISTED_PRIOR,
            _listed_rows(),
            GUIDANCE_LISTED_PRIOR,
            aliases=[LISTED_PRIOR_LEGACY, LISTED_PRIOR],
        ),
    ]


def _plan_soe() -> list[dict[str, Any]]:
    return [rule(SOE_MAIN, COLS_SOE, _soe_rows(), GUIDANCE_SOE)]


def run(scope: str, dry_run: bool, check: bool) -> tuple[list[str], list[str], list[str]]:
    if scope == "listed":
        return run_section(
            LISTED_PATH,
            "五、32",
            _plan_listed(),
            [LISTED_MAIN, LISTED_PRIOR],
            aligned_by=ALIGNED_BY,
            dry_run=dry_run,
            check=check,
            text_sections=TEXT_SECTIONS_LISTED,
        )
    return run_section(
        SOE_PATH,
        "八、93",
        _plan_soe(),
        [SOE_MAIN],
        aligned_by=ALIGNED_BY,
        dry_run=dry_run,
        check=check,
        require_text_sections=REQUIRE_TEXTS_SOE,
    )


LABELS = {
    "listed": "上市 五、32 所有权或使用权受到限制的资产（主表 + 续表）",
    "soe": "国企 八、93 所有权和使用权受到限制的资产",
}

main = build_cli(__doc__ or "", run, LABELS)

if __name__ == "__main__":
    raise SystemExit(main())
