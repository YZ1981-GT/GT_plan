#!/usr/bin/env python
"""修订附注「货币资金」章节结构（上市 五、1 / 国企 八、1），幂等。

**源模板真源**：`backend/wp_templates/E/E1-1至E1-11 货币资金- 审定表明细表（Leap-常规程序）.xlsx`
的 `附注披露信息(上市公司)` / `附注披露信息(国企)`（**半角括号**，openpyxl 实证）。

**改造前的欠账（openpyxl 逐格比对）**

1. **两版全部表 `columns=0` + `guidance` 空** → seed 路径无列元数据（`_infer_groups_from_headers`
   可能凭空推父表头）、附注 TAB 页签无编制提示。
2. **国企主表首行是「库存现金」**，源 xlsx R8 字面是「**现金**」。
3. **国企主表末行「其中：存放在境外的款项总额」是假行** —— 源 xlsx R13 实为括注
   「（如有因抵押、质押或冻结等对使用有限制、存放在境外、有潜在回收风险的款项应单独说明。）」，
   被 md 重建当成数据行落进了模板。上市侧 R15 才是真数据行（保留）。
4. **国企②表多一行「金融企业法定存款准备金或备付金」**（源 xlsx R17~R21 **没有**该行），
   且**缺「合计」行**（源 R23 有「合  计」，校验预设 F1-4 亦要求合计 = 明细之和）。
5. **上市侧整张缺②表** —— 用户裁决（2026-08-01）**补建**：源 xlsx 上市 sheet 虽只有 R18/R19
   文字，但 `note_check_preset_formulas.json` 的 **listed 侧 F1-4/F1-5/F1-6 三条明确引用
   「② 受限制的货币资金明细表」**，其中 F1-5/F1-6 是与现金流量表补充资料③表的跨科目勾稽
   （只有表格化才能自动校验）→ 按平台铁律「校验预设是列结构裁决者」补建。

**不动的地方（与铁律一致）**

- **列头字面不改**（上市 `期末余额/上年年末余额`、国企 `期末余额/期初余额`）：附注是交付物，
  列结构随附注模版 + 校验预设；底稿侧才按源 xlsx 的 `期末数/期初数`、`期末余额/年初余额`，
  由 `e1NoteSectionMap` 投影。本仓库无 `附注模版/*.md` 可复核，故保守不动。
- **②表只 3 列**：底稿的「受限原因」列不推附注 —— 源模板②表 3 列，受限事由按 R13 括注
  「应单独说明」写在**文字说明段**里（`_note_texts` 的「受限及境外款项说明」）。
- `text_sections` 只**补齐缺段**不整表替换（`require_text_sections`）：现有 10 段（上市）/
  3 段（国企）多为源模板提示原文，整表替换要手抄全部、抄错会被写回模板。

Usage::

    python backend/scripts/fix/fix_note_e1_monetary_fund_structure.py --dry-run
    python backend/scripts/fix/fix_note_e1_monetary_fund_structure.py
    python backend/scripts/fix/fix_note_e1_monetary_fund_structure.py --check

spec: .kiro/specs/e1-four-table-extraction-and-disclosure-alignment/ R5 / R6 (Task 11)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _note_structure_kit import (  # noqa: E402
    build_cli,
    data_row,
    flat_columns,
    rule,
    run_section,
    total_row,
)

_BACKEND = Path(__file__).resolve().parent.parent.parent
DATA = _BACKEND / "data"
LISTED = DATA / "note_template_listed.json"
SOE = DATA / "note_template_soe.json"

ALIGNED_BY = "e1-four-table-extraction-and-disclosure-alignment"

MAIN_TABLE = "货币资金"
RESTRICTED_TABLE = "受限制的货币资金明细"
FX_TABLE = "外币货币性项目"

# ── 列定义（key 逐字镜像 e1NoteSectionMap 的载荷列键）──────────────────────────
MAIN_COLS_LISTED = flat_columns(
    [
        ("label", "项目", None),
        ("end_amount", "期末余额", "amount"),
        ("prior_amount", "上年年末余额", "amount"),
    ]
)
MAIN_COLS_SOE = flat_columns(
    [
        ("label", "项目", None),
        ("end_amount", "期末余额", "amount"),
        ("prior_amount", "期初余额", "amount"),
    ]
)
RESTRICTED_COLS_LISTED = flat_columns(
    [
        ("label", "项目", None),
        ("end_amount", "期末余额", "amount"),
        ("prior_amount", "上年年末余额", "amount"),
    ]
)
RESTRICTED_COLS_SOE = flat_columns(
    [
        ("label", "项目", None),
        ("end_amount", "期末余额", "amount"),
        ("prior_amount", "期初余额", "amount"),
    ]
)

# ── 行集（逐字取自源 xlsx）─────────────────────────────────────────────────────
#
# 上市 R8~R15：库存现金/银行存款/存放财务公司款项/其他货币资金/存款应计利息/数字货币/
#              合计/其中：存放在境外的款项总额
# （R16 是**勾稽校验行** `B16=B14-D62`，不是披露行 → 不进模板）
MAIN_ROWS_LISTED = [
    {"label": "库存现金", "row_type": "data", "account_codes": ["1001"]},
    {"label": "银行存款", "row_type": "data", "account_codes": ["1002"]},
    {"label": "存放财务公司款项", "row_type": "data", "account_codes": []},
    {"label": "其他货币资金", "row_type": "data", "account_codes": ["1012"]},
    {"label": "存款应计利息", "row_type": "data", "account_codes": []},
    {"label": "数字货币", "row_type": "data", "account_codes": []},
    total_row("合计"),
    # 源 xlsx R15 —— 上市侧是**真数据行**（国企侧没有，见下）
    {"label": "其中：存放在境外的款项总额", "row_type": "data", "account_codes": []},
]

# 国企 R8~R12：现金/银行存款/其他货币资金/数字货币/合  计
# 🔴 首行是「现金」不是「库存现金」；🔴 **无**「其中：存放在境外的款项总额」行（R13 是括注）
MAIN_ROWS_SOE = [
    {"label": "现金", "row_type": "data", "account_codes": ["1001"]},
    {"label": "银行存款", "row_type": "data", "account_codes": ["1002"]},
    {"label": "其他货币资金", "row_type": "data", "account_codes": ["1012"]},
    {"label": "数字货币", "row_type": "data", "account_codes": []},
    total_row("合计"),
]

# ②表 R17~R23：五个命名类别 + R22 `…`（动态插行标记，**不 seed**）+ 合  计
RESTRICTED_ROWS = [
    data_row("银行承兑汇票保证金"),
    data_row("信用证保证金"),
    data_row("履约保证金"),
    data_row("用于担保的定期存款或通知存款"),
    data_row("放在境外且资金汇回受到限制的款项"),
    total_row("合计"),
]

# ── guidance（只取源模板红字/括注 + 准则条款，**纯文本禁 markdown 粗体**）────────
GUIDANCE_MAIN_LISTED = (
    "取数：库存现金/银行存款/其他货币资金取自 E1-1 货币资金审定表各科目审定数"
    "（跨 sheet 键 E1-adj-total-1001/1002/1012）；存款应计利息 = 审定表应计利息三行之和。"
    "列报口径（《企业会计准则解释第15号》财会〔2021〕35号）："
    "成员单位未归集至集团母公司账户而直接存入财务公司的资金，应在资产负债表「货币资金」项目中列示，"
    "可根据重要性原则在「货币资金」项目之下增设「其中：存放财务公司款项」单独列示；"
    "企业持有中国人民银行发行的数字人民币的，可增设「数字货币」二级科目核算，"
    "在资产负债表中列报于「货币资金」项目。"
    "存款利息：银行存款包括按实际利率法计提、尚未到付息期的应计利息，"
    "不包括已到期可收取但于资产负债表日尚未收到的逾期未收利息（列示于「应收利息」）；"
    "该部分利息不属于「现金及现金等价物」。"
    "勾稽（校验预设 F1-1/F1-2/F1-3）：报表货币资金期末/期初 = 本表合计行期末/期初余额；"
    "合计行 = 各明细行之和（合计行与「其中：存放在境外的款项总额」行不参与加总）。"
)
GUIDANCE_MAIN_SOE = (
    "取数：现金/银行存款/其他货币资金取自 E1-1 货币资金审定表各科目审定数"
    "（跨 sheet 键 E1-adj-total-1001/1002/1012）。"
    "源模板括注：如有因抵押、质押或冻结等对使用有限制、存放在境外、有潜在回收风险的款项应单独说明；"
    "企业持有由中国人民银行发行的数字人民币，可单独增加「数字货币」二级明细项目"
    "（《企业会计准则解释第15号》财会〔2021〕35号）。"
    "勾稽（校验预设 F1-1/F1-2/F1-3）：报表货币资金期末/期初 = 本表合计行期末/期初余额；"
    "合计行 = 各明细行之和。"
)
FX_COLS = flat_columns(
    [
        ("label", "项目", None),
        ("end_fc", "期末外币余额", "amount"),
        ("rate", "折算汇率", "rate"),
        ("end_rmb", "期末折算人民币余额", "amount"),
    ]
)

GUIDANCE_FX = (
    "本表跨循环共享：按科目分段列示外币货币性项目（货币资金 / 应收账款 / 短期借款 / "
    "长期借款 / 应付债券 等），各段下按币种列「其中：」明细，段末留可扩行。"
    "货币资金段可对照 E1 底稿披露表的「外币性货币项目」与「货币资金（原币）」两表填列"
    "（底稿侧为 7 列含期初，本表为 4 列仅期末，故只取期末口径）。"
    "折算汇率取资产负债表日中国人民银行公布的人民币汇率中间价。"
    "同步机制：本表已启用平台级「行级合并」—— 各循环推送时声明 `_row_scope` "
    "只负责自己那一段（货币资金段 = BS-002，由 E1 底稿推送），"
    "段外行原样保留，段边界解析不出时整表跳过写入而不退化为整表覆盖。"
    "尚未接入的段仍可在附注模块直接填列，不会被他循环的推送清掉。"
)

GUIDANCE_RESTRICTED = (
    "列示保证金、担保存款、冻结款项及存放境外且资金汇回受限等不符合现金及现金等价物条件"
    "或使用受限的款项。类别行由底稿②表按科目名动态归集"
    "（受限资金无独立标准科目，各项目子科目命名不同，判不出来的科目在底稿「待归类科目」"
    "面板由审计师点选归类）；源模板类别之外可动态增行。"
    "受限事由不设列，按源模板括注要求写在本节文字说明「受限及境外款项说明」中。"
    "勾稽（校验预设 F1-4/F1-5/F1-6）：合计行 = 各明细行之和（每个数值列独立校验）；"
    "合计行期末 = 报表货币资金期末 − 现金流量表补充资料「期末现金及现金等价物余额」；"
    "合计行期初同理。"
)

# ── 源模板要求存在的说明段（只补齐缺的，不整表替换）─────────────────────────────
REQUIRE_TEXTS_LISTED = [
    "期末，本公司不存在抵押、质押或冻结、或存放在境外且资金汇回受到限制的款项。",
]

#: `五、1` text_sections 里的**陈旧章节号**：外币货币性项目实为 `五、73`（非 `五、81`）。
#: `note_template_variant_matrix.json` 实证 `wai_bi_huo_bi_xing_xiang_mu.listed = 五、73`；
#: 代码里另有两处历史注释记录过同一处误映射的修正。
STALE_XREF_FIXES: list[tuple[str, str]] = [
    (
        "（外币信息，在“附注五、81、外币货币性项目”中披露）",
        "（外币信息，在“附注五、73、外币货币性项目”中披露）",
    ),
]


def _fix_stale_xrefs(section: dict, fixes: list[tuple[str, str]]) -> list[str]:
    """就地纠正 text_sections 里的陈旧章节号交叉引用。"""
    texts = section.get("text_sections")
    if not isinstance(texts, list):
        return []
    changes: list[str] = []
    for i, para in enumerate(texts):
        for old, new in fixes:
            if isinstance(para, str) and para == old:
                texts[i] = new
                changes.append(f"text_sections[{i}] 陈旧章节号纠正：{old!r} → {new!r}")
    return changes
REQUIRE_TEXTS_SOE = [
    "（注：如有因抵押、质押或冻结等对使用有限制、存放在境外、有潜在回收风险的款项应单独说明。）",
    "### 受限制的货币资金明细",
]

PLANS = {
    "listed": {
        "path": LISTED,
        "section": "五、1",
        "plan": [
            rule(MAIN_TABLE, MAIN_COLS_LISTED, MAIN_ROWS_LISTED, GUIDANCE_MAIN_LISTED),
            # 用户裁决：上市侧补建②表（校验预设 listed 侧 F1-4~F1-6 明确引用）
            rule(
                RESTRICTED_TABLE,
                RESTRICTED_COLS_LISTED,
                RESTRICTED_ROWS,
                GUIDANCE_RESTRICTED,
                insert=True,
            ),
        ],
        "expected": [MAIN_TABLE, RESTRICTED_TABLE],
        "require_texts": REQUIRE_TEXTS_LISTED,
    },
    # 外币货币性项目 —— **只补 columns/guidance，`rows=None` 不动行集**。
    # 该章节跨循环共享（同时承载应收账款/借款/应付债券各段），动行集会打断他循环；
    # 「可无限量添加行」/「……」是源模板的**可扩行**（作行保留，作列头才丢弃）。
    "fx_listed": {
        "path": LISTED,
        "section": "五、73",
        "plan": [rule(FX_TABLE, FX_COLS, None, GUIDANCE_FX)],
        "expected": [FX_TABLE],
        "require_texts": [],
    },
    "soe": {
        "path": SOE,
        "section": "八、1",
        "plan": [
            rule(MAIN_TABLE, MAIN_COLS_SOE, MAIN_ROWS_SOE, GUIDANCE_MAIN_SOE),
            rule(RESTRICTED_TABLE, RESTRICTED_COLS_SOE, RESTRICTED_ROWS, GUIDANCE_RESTRICTED),
        ],
        "expected": [MAIN_TABLE, RESTRICTED_TABLE],
        "require_texts": REQUIRE_TEXTS_SOE,
    },
    "fx_soe": {
        "path": SOE,
        "section": "八、92",
        "plan": [rule(FX_TABLE, FX_COLS, None, GUIDANCE_FX)],
        "expected": [FX_TABLE],
        "require_texts": [],
    },
}

LABELS = {
    "listed": "上市 五、1 货币资金",
    "soe": "国企 八、1 货币资金",
    "fx_listed": "上市 五、73 外币货币性项目（只补列元数据）",
    "fx_soe": "国企 八、92 外币货币性项目（只补列元数据）",
}


def _run_xref_pass(path: Path, section_number: str, dry_run: bool, check: bool):
    """独立一趟处理 text_sections 的陈旧章节号（`run_section` 只管表结构）。"""
    doc = __import__("json").loads(path.read_text(encoding="utf-8"))
    section = next(
        (s for s in doc.get("sections", []) if str(s.get("section_number")) == section_number),
        None,
    )
    if section is None:
        return [], []
    if check:
        texts = section.get("text_sections") or []
        return [], [
            f"text_sections 残留陈旧章节号：{old!r}（应为 {new!r}）"
            for old, new in STALE_XREF_FIXES
            if old in texts
        ]
    changes = _fix_stale_xrefs(section, STALE_XREF_FIXES)
    if changes and not dry_run:
        path.write_text(
            __import__("json").dumps(doc, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return changes, []


def _run(key: str, dry_run: bool, check: bool):
    cfg = PLANS[key]
    xref_changes: list[str] = []
    xref_errs: list[str] = []
    if key == "listed":
        xref_changes, xref_errs = _run_xref_pass(
            cfg["path"], cfg["section"], dry_run, check
        )
    changes, warnings, errs = run_section(
        cfg["path"],
        cfg["section"],
        cfg["plan"],
        cfg["expected"],
        aligned_by=ALIGNED_BY,
        dry_run=dry_run,
        check=check,
        require_text_sections=cfg["require_texts"],
    )
    return xref_changes + changes, warnings, xref_errs + errs


main = build_cli(__doc__ or "", _run, LABELS)

if __name__ == "__main__":
    sys.exit(main())
