"""母公司附注章结构修订（Task 3~7，幂等）。

覆盖范围（**只动母公司章，合并章逐字节不动**）:

- Task 3: soe 第 12 章 ``section_title`` / ``section_id`` 改写 + 6 子节前缀同步 + 旧 slug 进
  ``legacy_aliases``；``sort_index`` 保持 12。
- Task 4: 表名唯一化（表头首格泄漏 / 同子节重名 → ``{科目名}（表N）`` 范式，主表 = 科目名本身，
  其余 N 从既有最大编号 +1 续排；沿用 soe「其他应收款（表2）」既有自动编号形态，
  **不臆造业务表名**）。旧名 → 新名映射进表级 ``legacy_aliases``。

  🔴 **范围只含「自有表子节」**（用户 2026-08-06 裁决 = 方案 A）：现为
  ``listed/长期股权投资``（``被投资单位``×2）**一个子节**。

  🔴🔴 **范围修正（2026-08-06）：``soe/其他应收款`` 已从本任务移除，归 Task 6。**
  该子节此前被当作「自有表子节」列入 ``RENAME_SECTIONS``，事实前提错误 ——
  源 docx 实测 ``DOCX_SECTIONS["soe"]["其他应收款"] == 0``（**own_table_count=0**）
  ⇒ 按需求 1.4 / 4.1 的定义**它是同构子节** ⇒ 结构由 Task 6 按合并章整体替换。
  需求 4.1（有源 docx 证据）优先于需求 6.5（笼统措辞连带提到它）。
  **下个会话不得把它加回 ``RENAME_SECTIONS``**（详见该常量处注释）。

  **listed 侧 4 个同构子节（应收票据 / 应收账款 / 其他应收款 / 营业收入与营业成本，
  共 53 张表）有意不在本任务范围** —— 它们归 Task 6 按合并章**整体替换** ``tables``，
  在此正名会被那次替换整表覆盖 = 白做。下个会话若按 requirements 6.5 字面「listed 侧
  重名全部正名」再做一遍，属重复劳动，请先看 Task 6 是否已完成。

  🔴 表级 ``legacy_aliases`` **当前全仓零消费方**（2026-08-06 实证：21 处 ``legacy_aliases``
  引用中 ``procedure_*`` 系列是另一张表的列，``note_word_exporter`` / loader 读的都是
  **section 级**章节码别名）。此处写入是为 Task 12 取数接线预留迁移映射，
  **不得声称「已解决表名漂移导致的数据失联」** —— 那要等消费方接上才成立。
  另注意 soe 4 张重名表的旧名相同 ⇒ 旧名 → 新名是**一对多**，只能按位置区分，
  该字段不可用于反向唯一解析。
- Task 5: 长期股权投资两级表头还原（listed 7/9/13 列，soe 仅表 3 → 12 列；
  soe 表 1/表 2 **只补 columns 不改 headers/rows**）。
- Task 6: 同构子节按合并章**整体替换** ``tables``（用户 2026-08-06 裁决），
  被替换掉的旧表名 **与这些表自己的 ``legacy_aliases`` 里的更旧名**一并进子节级
  ``_removed_table_keys``（仍与本次写入的新表名求差集）。
  ⇒ Task 4 正名产生的中间名（如 ``其他应收款（表8/9/10/11）``）与更早的
  ``其他应收款（续）债务人名称`` 都留有迁移记录，供 Task 12 使用。
- Task 7: 自有表子节里**除长期股权投资以外**的表补 ``columns``（每张表显式 ``group`` 或
  ``flat``，禁留 ``None`` 触发前缀推断）+ ``guidance``（纯文本无 markdown 粗体），
  并把 ``listed/投资收益`` 的表头首格泄漏名「项  目」正名（登记在 ``RENAME_SECTIONS``，
  复用 Task 4 的正名机制，**须早于补列**）；soe 章首补源 docx 连续 5 段说明。

  🔴 **同构子节（7 个）不在 Task 7 范围** —— 它们的 ``columns``/``guidance`` 由 Task 6
  按合并章整体替换时**继承齐备**（合并章那 7 个子节的列结构早由前序 spec 补齐）。
  在此重写会与 ``check_isomorphic`` 的「与合并章深相等」判据打架。故 Task 7 的实际
  工作面只有 **3 张表**：``listed/投资收益`` 1 张 + ``soe/{投资收益,现金流量表补充资料}``
  各 1 张（守卫 ``CURRENT_MISSING_COLUMNS_COUNT`` 曾登记的 1/2 即此）。

判据真源 = ``docs/模版/`` 两份源 docx（由 Task 1 提取器 / Task 2 守卫锁死），
本脚本只负责把已裁决的目标态幂等地写进 ``note_template_{listed,soe}.json``。

CLI: ``--dry-run``（**默认**）/ ``--apply`` / ``--check`` / ``--only {listed,soe}``。

> 与 ``_note_structure_kit.build_cli`` 的偏差：后者「无标记即写盘」，本 spec 要求
> 「``--dry-run`` 默认」，故自带 ``main()``，但输出格式与 kit 一致（``~`` 变更 / ``!`` 告警
> / ``x`` 欠账），行/列构造与校验一律复用 kit，不另写一份。

铁律:

- 控制台输出禁 emoji（Windows GBK 会 ``UnicodeEncodeError`` 且崩点在写盘之后）。
- 写盘前做 round-trip 自检：``json.dumps`` 不能逐字复现原文即 exit 2（防全文件重排 /
  并发会话互相回退）。
- 母公司章禁删；合并章禁改（本脚本对合并章只读）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _note_structure_kit import (  # noqa: E402
    AMOUNT,
    PERCENT,
    TEXT,
    derive_column_groups,
    ensure_text_sections,
    flat_columns,
    grouped_columns,
    headers_of,
    is_title_paragraph,
    missing_text_sections,
    stamp,
    two_period_columns,
    validate_section,
)
# 🔴 **有意不用 kit 的 ``titleize_text_sections``**：它给 ``text_sections`` 里的
# **裸表名**加 ``#### `` 前缀，而 Task 7 要补的 soe 章首三段是**实质披露正文**
# （非表名、非标题）。加 ``#### `` 会让 ``disclosure_engine._is_table_title_paragraph``
# 判成标题 → 标题本身不进任何输出 ⇒ 三段说明被静默丢弃。
# 追加走 ``ensure_text_sections``（只补缺段、不动已有段、无前缀），
# ``--check`` 走 ``missing_text_sections``；``is_title_paragraph`` 用于反向自检
# 「这三段确实不会被判成标题」。
# 🔴 markdown 粗体剥离**必须复用平台级口径**（成对非贪婪，孤立 `**` 原样保留）。
# 自己写 `replace("**", "")` 会把脱敏占位「诉讼金额为**元」改成「诉讼金额为元」。
from fix_note_bold_markers import strip_pairs  # noqa: E402

# ─────────────────────────── 定位与目标常量 ───────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "backend" / "data"
TEMPLATE_PATH = {
    "listed": DATA_DIR / "note_template_listed.json",
    "soe": DATA_DIR / "note_template_soe.json",
}
LABELS = {
    "listed": "listed 第十六章 母公司财务报表主要项目注释",
    "soe": "soe 第十二章 母公司财务报表的主要项目附注",
}
ALIGNED_BY = "fix_note_parent_company_chapter.py"

# 母公司章定位：listed 现值已是母公司语义 slug，soe 现值是错误 slug（Task 3 改）
PARENT_CHAPTER_SID_OLD = {
    "listed": "chapter-16-mu-gong-si-cai-wu-bao-biao-zhu-yao-xiang-mu-zhu-shi",
    "soe": "chapter-12-gu-fen-zhi-fu",
}
PARENT_CHAPTER_SID_NEW = {
    "listed": PARENT_CHAPTER_SID_OLD["listed"],  # 需求 3.2：listed 侧保留现值
    "soe": "chapter-12-mu-gong-si-cai-wu-bao-biao-de-zhu-yao-xiang-mu-fu-zhu",
}
# soe 第 12 章标题逐字取自源 docx Heading 1（需求 2.1）
SOE_CHAPTER_TITLE_NEW = "母公司财务报表的主要项目附注"

# soe 章首说明，**逐字**取自源 docx 母公司章 Heading 1 之后、首个子节 Heading 之前的
# 连续 5 个 Normal 段落（需求 5.2，禁改写、禁增删字符）。
#
# 🔴 **由 3 段扩到 5 段（Task 7，2026-08-06）** —— 原 3 段版本有两处与源 docx 不符：
#
# 1. **第 3 条末尾的 `）` 被截掉** —— 源 docx 第 3 条原文以 `）` 收尾，它与第 1 段
#    开头的 `（` 是**一对**（源模板把整段说明括在一对全角括号里）。只留 3 条又去掉
#    `）`，看似自洽，实则是改写源文（需求 5.2 明令「仅取自源 docx」）。
# 2. **少了前后两段** —— 前置段 `（对已编制合并财务报表的企业…按照以下要求披露：`
#    正是「母公司章为何存在、何时适用」的章首说明本体（是实质编制指引，不是排版噪声）；
#    后置段 `〔披露内容参考如下：〕` 引出下面 6 个子节。
#
# ⇒ 与其在「哪一段算实质说明」上做源模板不支持的取舍判断，不如**整段连续区间照抄**：
# 零发明、零删减、括号成对、可由守卫直接与源 docx 逐字比对（守卫按 Heading 1 →
# 首个子 Heading 之间的 Normal 段落序列复算，源模板一改即打红）。
#
# 🔴 五段**都不得**被判成标题段（否则 `disclosure_engine._is_table_title_paragraph`
# 会让它们静默不进任何输出）。实测均为 False，但**第 1/2/3 条离触发只差长度** ——
# `_NUMBERED_TITLE_RE` 的 `^(\d+)[.、]` 命中 `1、`，只因三条都 >20 字才逃过 20 字长度门。
# 故 `check_chapter_intro` 用 kit 的 `is_title_paragraph` 逐段反向断言，禁靠「看起来很长」。
SOE_CHAPTER_INTRO = [
    "（对已编制合并财务报表的企业，在财务报表附注中，除对合并报表项目注释外，"
    "还应当对母公司报表的主要项目注释。按照以下要求披露：",
    "1、母公司报表主要项目包括应收账款、其他应收款、长期股权投资、营业收入和营业成本、"
    "投资收益、现金流量表补充资料等项目，应参照上述相应项目的要求加以注释；",
    "2、本期发生反向购买的，母公司报表附注应披露以公允价值入账的资产、负债及其公允价值、"
    "确定公允价值方法、公允价值计算过程、原账面价值。因反向购买形成长期股权投资的，"
    "应披露长期股权投资成本及其确定方法、计算过程。",
    "3、本期发生使用资本公积弥补亏损的，母公司报表附注应披露亏损的情况、弥补亏损的原因"
    "以及用于弥补亏损的公积金来源、金额和方式等。）",
    "〔披露内容参考如下：〕",
]

# listed 侧母公司章**无章首说明段落** —— 源 docx 实测 Heading 1（idx 2168）之后紧跟
# 首个子节 Heading 2「应收票据（披露格式参考附注五、4）」，中间零个 Normal 段落。
# 其「参照合并章」的口径写在**子节标题里**（`（披露格式参考附注五、X）`），已由
# Task 2 守卫的 `check_section_kinds` / 同构清单锁死 ⇒ 本 spec 不给 listed 造章首文字
# （宁缺勿造）。该事实由 `check_chapter_intro` 的 listed 分支正向断言（写入即打红）。
CHAPTER_INTRO: dict[str, list[str]] = {"listed": [], "soe": SOE_CHAPTER_INTRO}

# 同构子节 → 合并章 section_number（需求 4.1，2026-08-06 实测章节号）
ISOMORPHIC_SOURCE: dict[str, dict[str, str]] = {
    "listed": {
        "应收票据": "五、4",
        "应收账款": "五、5",
        "其他应收款": "五、8",
        "营业收入与营业成本": "五、62",
    },
    "soe": {
        "应收账款": "八、5",
        "其他应收款": "八、9",
        "营业收入与营业成本": "八、64",
    },
}
# 自有表子节（需求 4.2：严格按母公司章源 docx，**不参与对齐**）
OWN_TABLE_SECTIONS: dict[str, tuple[str, ...]] = {
    "listed": ("长期股权投资", "投资收益"),
    "soe": ("长期股权投资", "投资收益", "现金流量表补充资料"),
}


# ─────────────────────────── 长期股权投资列定义（Task 5） ───────────────────────────

def _listed_lte_t1() -> list[dict[str, Any]]:
    """listed 表 1（7 列）：项目 × {期末余额, 上年年末余额} × {账面余额, 减值准备, 账面价值}。"""
    return two_period_columns(
        ("label", "项目"),
        ("期末余额", "上年年末余额"),
        [
            ("balance", "账面余额", AMOUNT),
            ("provision", "减值准备", AMOUNT),
            ("book_value", "账面价值", AMOUNT),
        ],
    )


# listed 表 2 / 表 3 与 soe 表 3 共用的「本期增减变动」子列
_MOVE_4 = [
    ("add_investment", "追加投资"),
    ("reduce_investment", "减少投资"),
    ("provision_accrued", "计提减值准备"),
    ("other_movement", "其他"),
]
_MOVE_8 = [
    ("add_investment", "追加/新增投资"),
    ("reduce_investment", "减少投资"),
    ("equity_pnl", "权益法下确认的投资损益"),
    ("oci_adjust", "其他综合收益调整"),
    ("other_equity", "其他权益变动"),
    ("declared_dividend", "宣告发放现金股利或利润"),
    ("provision_accrued", "计提减值准备"),
    ("other_movement", "其他"),
]
_MOVE_GROUP = "本期增减变动"


def _lte_movement_table(
    label: tuple[str, str],
    head_specs: list[tuple[str, str, str | None]],
    moves: list[tuple[str, str]],
    tail_specs: list[tuple[str, str, str | None]],
) -> list[dict[str, Any]]:
    """混合分组：前若干列与后若干列 rowspan=2（无 group），中间「本期增减变动」分组。"""
    specs: list[tuple[str, str, str | None, str | None]] = [
        (k, lbl, fmt, None) for k, lbl, fmt in head_specs
    ]
    specs += [(k, lbl, AMOUNT, _MOVE_GROUP) for k, lbl in moves]
    specs += [(k, lbl, fmt, None) for k, lbl, fmt in tail_specs]
    return grouped_columns(label, specs)


def _listed_lte_t2() -> list[dict[str, Any]]:
    """listed 表 2（9 列）。"""
    return _lte_movement_table(
        ("label", "被投资单位"),
        [
            ("opening_book_value", "期初余额（账面价值）", AMOUNT),
            ("opening_provision", "减值准备期初余额", AMOUNT),
        ],
        _MOVE_4,
        [
            ("closing_book_value", "期末余额（账面价值）", AMOUNT),
            ("closing_provision", "减值准备期末余额", AMOUNT),
        ],
    )


def _listed_lte_t3() -> list[dict[str, Any]]:
    """listed 表 3（13 列）：表 2 结构，本期增减变动扩为 8 子列。"""
    return _lte_movement_table(
        ("label", "被投资单位"),
        [
            ("opening_book_value", "期初余额（账面价值）", AMOUNT),
            ("opening_provision", "减值准备期初余额", AMOUNT),
        ],
        _MOVE_8,
        [
            ("closing_book_value", "期末余额（账面价值）", AMOUNT),
            ("closing_provision", "减值准备期末余额", AMOUNT),
        ],
    )


def _soe_lte_t1() -> list[dict[str, Any]]:
    """soe 表 1（5 列）—— headers 已与源 docx 逐字一致，只补 columns（需求 4.4 反向断言）。"""
    return flat_columns(
        [
            ("label", "项目", None),
            ("opening", "期初余额", AMOUNT),
            ("increase", "本期增加", AMOUNT),
            ("decrease", "本期减少", AMOUNT),
            ("closing", "期末余额", AMOUNT),
        ]
    )


def _soe_lte_t2() -> list[dict[str, Any]]:
    """soe 表 2（7 列）—— 同上，结构已正确，不得改动 headers/rows。"""
    return flat_columns(
        [
            ("label", "被投资单位", None),
            ("opening", "期初余额", AMOUNT),
            ("increase", "本期增加", AMOUNT),
            ("decrease", "本期减少", AMOUNT),
            ("closing", "期末余额", AMOUNT),
            ("provision_accrued", "本期计提减值准备", AMOUNT),
            ("closing_provision", "减值准备期末余额", AMOUNT),
        ]
    )


def _soe_lte_t3() -> list[dict[str, Any]]:
    """soe 表 3（12 列）：被投资单位/期初余额 + 本期增减变动{8} + 期末余额/减值准备期末余额。"""
    return _lte_movement_table(
        ("label", "被投资单位"),
        [("opening", "期初余额", AMOUNT)],
        _MOVE_8,
        [
            ("closing", "期末余额", AMOUNT),
            ("closing_provision", "减值准备期末余额", AMOUNT),
        ],
    )


# ─────────────────────────── 自有表子节规则（Task 5 + Task 7） ───────────────────────────

_G_LTE_LISTED_T1 = (
    "勾稽：合计行 = 对子公司投资 + 对合营企业投资 + 对联营企业投资；"
    "各期账面价值 = 账面余额 - 减值准备。"
)
_G_LTE_LISTED_T2 = (
    "勾稽：期末余额（账面价值）= 期初余额（账面价值）+ 本期增减变动各列合计；"
    "减值准备期末余额 = 减值准备期初余额 + 计提减值准备。"
)
_G_LTE_LISTED_T3 = (
    "勾稽：小计行 = 其上各明细行之和，合计行 = 联营企业小计 + 合营企业小计；"
    "期末余额（账面价值）= 期初余额（账面价值）+ 本期增减变动各列合计。"
    "标有「…」的行为可扩行，可按被投资单位逐项添加。"
)
_G_LTE_SOE_T1 = (
    "勾稽：小计行 = 对子公司投资 + 对合营企业投资 + 对联营企业投资；"
    "合计行 = 小计 - 长期股权投资减值准备。"
)
_G_LTE_SOE_T2 = (
    "勾稽：期末余额 = 期初余额 + 本期增加 - 本期减少；"
    "减值准备期末余额已包含本期计提减值准备。"
)
_G_LTE_SOE_T3 = (
    "勾稽：合计行 = 合营企业与联营企业各明细行之和；"
    "期末余额 = 期初余额 + 本期增减变动各列合计。"
    "标有「…」的行为可扩行，可按被投资单位逐项添加。"
)
# 源 docx 括注逐字（listed 侧含源模板笔误「也有那个」，原样保留，禁「顺手修正」）
_G_INV_LISTED = (
    "（若投资收益汇回有重大限制的，应予以说明。若不存在此类重大限制，也有那个作出说明。）\n"
    "勾稽：合计行 = 其上各项目之和。"
)
_G_INV_SOE = (
    "注：若投资收益汇回有重大限制的，应予以说明。若不存在此类重大限制，也应做出说明。\n"
    "勾稽：合计行 = 其上各来源之和。"
)
_G_CF_SOE = (
    "母公司报表主要项目包括应收账款、其他应收款、长期股权投资、营业收入和营业成本、"
    "投资收益、现金流量表补充资料等项目，应参照上述相应项目的要求加以注释。\n"
    "勾稽：经营活动产生的现金流量净额 = 净利润 + 上列各调节项目之和；"
    "现金及现金等价物净增加额 = 现金的期末余额 - 现金的期初余额 "
    "+ 现金等价物的期末余额 - 现金等价物的期初余额。"
)


def _inv_columns(label_text: str) -> list[dict[str, Any]]:
    return flat_columns(
        [
            ("label", label_text, None),
            ("current", "本期发生额", AMOUNT),
            ("prior", "上期发生额", AMOUNT),
        ]
    )


def _cf_columns() -> list[dict[str, Any]]:
    return flat_columns(
        [
            ("label", "项目", None),
            ("current", "本期发生额", AMOUNT),
            ("prior", "上期发生额", AMOUNT),
        ]
    )


# (子节标题) -> [每张表的目标态]；``rebuild_headers=False`` 表示只补 columns 不动 headers
OWN_RULES: dict[str, dict[str, list[dict[str, Any]]]] = {
    "listed": {
        "长期股权投资": [
            {"columns": _listed_lte_t1(), "guidance": _G_LTE_LISTED_T1, "rebuild_headers": True},
            {"columns": _listed_lte_t2(), "guidance": _G_LTE_LISTED_T2, "rebuild_headers": True},
            {"columns": _listed_lte_t3(), "guidance": _G_LTE_LISTED_T3, "rebuild_headers": True},
        ],
        "投资收益": [
            {"columns": _inv_columns("项目"), "guidance": _G_INV_LISTED, "rebuild_headers": True},
        ],
    },
    "soe": {
        "长期股权投资": [
            {"columns": _soe_lte_t1(), "guidance": _G_LTE_SOE_T1, "rebuild_headers": False},
            {"columns": _soe_lte_t2(), "guidance": _G_LTE_SOE_T2, "rebuild_headers": False},
            {"columns": _soe_lte_t3(), "guidance": _G_LTE_SOE_T3, "rebuild_headers": True},
        ],
        "投资收益": [
            {
                "columns": _inv_columns("产生投资收益的来源"),
                "guidance": _G_INV_SOE,
                "rebuild_headers": False,
            },
        ],
        "现金流量表补充资料": [
            {"columns": _cf_columns(), "guidance": _G_CF_SOE, "rebuild_headers": False},
        ],
    },
}

_UNUSED = (PERCENT, TEXT)  # kit 常量占位（本脚本目标表无百分比/文本列）

# ─────────────────────────── Task 3: 章标题与标识改写 ───────────────────────────

# 平台既有 slug 生成器的长度上限：listed 侧 `chapter-16-…-ying-ye-shou-ru-yu-ying-ye-cheng`
# 恰好 95 字符且末尾被截断（源标题是「营业收入与营业成本」，`-ben` 被切掉），
# soe 侧最长 97（`…-cha-cuo-de-g-kua-2`，含去重后缀）⇒ 取 95 与主流形态一致。
SLUG_MAX_LEN = 95

# soe 第 12 章的 account_name 现值同为「股份支付」；其余 13 个 level-1 章
# 实测 `section_title == account_name` 恒成立 ⇒ 改标题必须同步它，否则该章
# 成为全库唯一一个两者不一致的章（下游按 account_name 索引的路径会落空）。
SOE_CHAPTER_ACCOUNT_NAME_OLD = "股份支付"


def _truncate_slug(sid: str) -> str:
    """按平台既有上限截断，并去掉截断产生的尾部连字符。"""
    if len(sid) <= SLUG_MAX_LEN:
        return sid
    return sid[:SLUG_MAX_LEN].rstrip("-")


def _rewrite_sid(old_sid: str, old_prefix: str, new_prefix: str) -> str:
    """把 `old_prefix` 前缀换成 `new_prefix`（章本身 = 前缀全等）。"""
    if old_sid == old_prefix:
        return _truncate_slug(new_prefix)
    return _truncate_slug(new_prefix + old_sid[len(old_prefix):])


def _append_alias(node: dict[str, Any], old_value: str) -> bool:
    """把旧 slug 追加进 ``legacy_aliases``（幂等；已在则空操作）。返回是否新增。"""
    aliases = node.get("legacy_aliases")
    if not isinstance(aliases, list):
        aliases = []
    if old_value in aliases:
        node["legacy_aliases"] = aliases
        return False
    aliases.append(old_value)
    node["legacy_aliases"] = aliases
    return True


def _find_parent_chapter(sections: list[dict[str, Any]], variant: str) -> dict[str, Any] | None:
    """按新旧 sid 双向定位母公司章（幂等：已改写过时按新 sid 命中）。"""
    for sid in (PARENT_CHAPTER_SID_OLD[variant], PARENT_CHAPTER_SID_NEW[variant]):
        ch = next(
            (s for s in sections if s.get("section_id") == sid and s.get("level") == 1), None
        )
        if ch is not None:
            return ch
    return None


def _parent_children(sections: list[dict[str, Any]], variant: str) -> list[dict[str, Any]]:
    wanted = {PARENT_CHAPTER_SID_OLD[variant], PARENT_CHAPTER_SID_NEW[variant]}
    return [s for s in sections if s.get("parent_section_id") in wanted]


def apply_chapter_identity(doc: dict[str, Any], variant: str) -> tuple[list[str], list[str]]:
    """Task 3：soe 第 12 章 ``section_title`` / ``section_id`` / ``account_name`` 改写，
    6 子节 ``section_id`` 前缀与 ``parent_section_id`` 同步，旧 slug 进 ``legacy_aliases``。

    ``sort_index`` / ``sort_order`` / ``section_number`` / ``scope`` **一律不动**（需求 2.5）。
    listed 侧 sid 与标题已是母公司语义（需求 3.2 裁决保留现值）⇒ 本函数对 listed 是空操作。
    """
    changes: list[str] = []
    warnings: list[str] = []
    sections = doc.get("sections") or []

    chapter = _find_parent_chapter(sections, variant)
    if chapter is None:
        warnings.append(
            f"未找到 {variant} 母公司章（sid={PARENT_CHAPTER_SID_OLD[variant]} / "
            f"{PARENT_CHAPTER_SID_NEW[variant]}）→ 跳过 Task 3"
        )
        return changes, warnings

    if variant != "soe":
        # 需求 3.2：listed 标题保留 JSON 现值，section_id 亦不动
        return changes, warnings

    old_prefix = PARENT_CHAPTER_SID_OLD["soe"]
    new_prefix = PARENT_CHAPTER_SID_NEW["soe"]

    # 章序不得变（需求 2.5）——改写前先钉住，防后续误动
    if chapter.get("sort_index") != 12 or chapter.get("section_number") != "十二":
        warnings.append(
            f"soe 母公司章位置异常：sort_index={chapter.get('sort_index')!r} "
            f"section_number={chapter.get('section_number')!r}（应为 12 / 十二）→ 跳过 Task 3"
        )
        return changes, warnings

    # 1) 章标题（需求 2.1，逐字取自源 docx Heading 1）
    if chapter.get("section_title") != SOE_CHAPTER_TITLE_NEW:
        old_title = chapter.get("section_title")
        chapter["section_title"] = SOE_CHAPTER_TITLE_NEW
        changes.append(f"章 section_title：「{old_title}」→「{SOE_CHAPTER_TITLE_NEW}」")

    # 2) account_name 同步（其余 13 章实测 title == account_name）
    if chapter.get("account_name") == SOE_CHAPTER_ACCOUNT_NAME_OLD:
        chapter["account_name"] = SOE_CHAPTER_TITLE_NEW
        changes.append(
            f"章 account_name：「{SOE_CHAPTER_ACCOUNT_NAME_OLD}」→「{SOE_CHAPTER_TITLE_NEW}」"
            "（与 section_title 保持一致，同其余 13 章）"
        )
    elif chapter.get("account_name") != SOE_CHAPTER_TITLE_NEW:
        warnings.append(
            f"章 account_name 非预期值 {chapter.get('account_name')!r} → 不改写（宁缺勿造）"
        )

    # 3) 章 section_id + legacy_aliases
    if chapter.get("section_id") == old_prefix:
        chapter["section_id"] = new_prefix
        if _append_alias(chapter, old_prefix):
            changes.append(f"章 legacy_aliases 追加旧 slug「{old_prefix}」")
        changes.append(f"章 section_id：「{old_prefix}」→「{new_prefix}」")

    # 4) 6 子节 section_id 前缀 + parent_section_id 同步
    kids = _parent_children(sections, "soe")
    if len(kids) != 6:
        warnings.append(f"soe 母公司章子节数应为 6，实为 {len(kids)} → 仍按实际子节改写")

    taken = {str(s.get("section_id")) for s in sections}
    for kid in kids:
        old_kid_sid = str(kid.get("section_id") or "")
        if kid.get("parent_section_id") == old_prefix:
            kid["parent_section_id"] = new_prefix
            changes.append(
                f"子节「{kid.get('section_title')}」parent_section_id → 「{new_prefix}」"
            )
        if not old_kid_sid.startswith(old_prefix):
            continue
        new_kid_sid = _rewrite_sid(old_kid_sid, old_prefix, new_prefix)
        if new_kid_sid == old_kid_sid:
            continue
        taken.discard(old_kid_sid)
        if new_kid_sid in taken:
            warnings.append(
                f"子节「{kid.get('section_title')}」sid 改写跳过：「{new_kid_sid}」已被占用"
            )
            taken.add(old_kid_sid)
            continue
        kid["section_id"] = new_kid_sid
        taken.add(new_kid_sid)
        if _append_alias(kid, old_kid_sid):
            changes.append(
                f"子节「{kid.get('section_title')}」legacy_aliases 追加「{old_kid_sid}」"
            )
        note = "（超 95 字符已按平台上限截断）" if len(new_prefix + old_kid_sid[len(old_prefix):]) > SLUG_MAX_LEN else ""
        changes.append(
            f"子节「{kid.get('section_title')}」section_id → 「{new_kid_sid}」{note}"
        )

    return changes, warnings


def check_chapter_identity(doc: dict[str, Any], variant: str) -> list[str]:
    """Task 3 的 ``--check`` 欠账清单。"""
    errs: list[str] = []
    sections = doc.get("sections") or []
    chapter = _find_parent_chapter(sections, variant)
    if chapter is None:
        return [f"{variant} 母公司章不存在（母公司章禁删）"]

    if variant != "soe":
        # listed 侧只核「现值未被误改」（需求 3.2 双向锁死的模板侧）
        if chapter.get("section_id") != PARENT_CHAPTER_SID_NEW["listed"]:
            errs.append(
                f"listed 母公司章 section_id 应保持「{PARENT_CHAPTER_SID_NEW['listed']}」，"
                f"实为「{chapter.get('section_id')}」"
            )
        return errs

    if chapter.get("section_title") != SOE_CHAPTER_TITLE_NEW:
        errs.append(
            f"章 section_title 应为「{SOE_CHAPTER_TITLE_NEW}」，实为「{chapter.get('section_title')}」"
        )
    if chapter.get("account_name") != SOE_CHAPTER_TITLE_NEW:
        errs.append(
            f"章 account_name 应为「{SOE_CHAPTER_TITLE_NEW}」，实为「{chapter.get('account_name')}」"
        )
    if chapter.get("section_id") != PARENT_CHAPTER_SID_NEW["soe"]:
        errs.append(
            f"章 section_id 应为「{PARENT_CHAPTER_SID_NEW['soe']}」，实为「{chapter.get('section_id')}」"
        )
    if chapter.get("sort_index") != 12 or chapter.get("section_number") != "十二":
        errs.append(
            f"章序被改动：sort_index={chapter.get('sort_index')!r} "
            f"section_number={chapter.get('section_number')!r}（需求 2.5 要求保持 12 / 十二）"
        )

    old_prefix = PARENT_CHAPTER_SID_OLD["soe"]
    if old_prefix not in (chapter.get("legacy_aliases") or []):
        errs.append(f"章 legacy_aliases 缺旧 slug「{old_prefix}」（需求 2.3 迁移映射）")

    kids = _parent_children(sections, "soe")
    if len(kids) != 6:
        errs.append(f"母公司章子节数应为 6，实为 {len(kids)}")
    for kid in kids:
        sid = str(kid.get("section_id") or "")
        title = kid.get("section_title")
        if kid.get("parent_section_id") != PARENT_CHAPTER_SID_NEW["soe"]:
            errs.append(f"子节「{title}」parent_section_id 未同步：{kid.get('parent_section_id')!r}")
        if old_prefix in sid:
            errs.append(f"子节「{title}」section_id 仍含旧 slug：「{sid}」")
        if not sid.startswith(PARENT_CHAPTER_SID_NEW["soe"]):
            errs.append(f"子节「{title}」section_id 未落在新前缀下：「{sid}」")
        aliases = kid.get("legacy_aliases") or []
        if not any(str(a).startswith(old_prefix) for a in aliases):
            errs.append(f"子节「{title}」legacy_aliases 缺旧 slug（需求 2.3）")

    sids = [str(s.get("section_id")) for s in sections]
    dup = sorted({s for s in sids if sids.count(s) > 1})
    if dup:
        errs.append(f"改写后 section_id 出现重复：{dup}")
    return errs


# ─────────────────────────── Task 4: 表名唯一化 ───────────────────────────

# 🔴 范围只含「自有表子节」（用户 2026-08-06 裁决 = 方案 A）。
# 同构子节归 Task 6 整体替换 tables，在此正名会被覆盖 ⇒ 有意不列入。
# 值 = 该子节的主表名（正名基名），取自子节标题；`（表N）` 从既有最大 N 续排。
#
# 🔴🔴 **范围修正登记（2026-08-06，修正 2026-08-06 早前「方案 A」那次裁决的事实前提）**：
#
# `soe/其他应收款` 曾被列入本表，其事实前提是「它是自有表子节」——**该前提是错的**。
# 源 docx 实测 `DOCX_SECTIONS["soe"]["其他应收款"] == 0`（**own_table_count=0**）
# ⇒ 按需求 1.4 / 4.1 的定义**它是同构子节**（源 docx 无自有表、明文参照合并章）
# ⇒ 归 **Task 6**（按合并章整体替换 tables），**不归 Task 4**。
#
# 判据优先级：需求 4.1（有源 docx 证据支撑）**优先于** 需求 6.5（按「listed 侧重名全部
# 正名」的笼统措辞连带提到它）。且本 dict 的适用范围在模块 docstring 里自述为
# 「只含两个自有表子节」—— 把一个同构子节放进来与该声明自相矛盾。
#
# ⇒ 下个会话**不得**把 `其他应收款` 加回 `RENAME_SECTIONS["soe"]`。它的旧名迁移记录
# 由 `apply_isomorphic` 在整体替换前一并并入子节级 `_removed_table_keys`（见该函数）。
# `soe` 键保留为空 dict（不删键）—— `apply_table_renames` / `check_table_renames`
# 对空 targets 已是空操作，保留键使「两个变体都被显式表态过」这一点在代码里可见。
# 🔴 **Task 7 追加一条 `listed/投资收益`**（2026-08-06）：该表名是表头首格泄漏
# 「项  目」（headers[0] == `项目`），它是**自有表子节**故不参与 Task 6 对齐 ⇒ 名字
# 不会被替换掉。守卫里 `_XFAIL_LISTED_INV_INCOME_LEAK` 的 reason 已把它的正名明确
# 归入「Task 7 补列元数据那一轮一并处置」。**正名必须早于补列**（列规则按表名索引），
# 故登记在此处而不是另写一套改名逻辑。soe 侧两张自有表名本就唯一非泄漏，不需正名。
RENAME_SECTIONS: dict[str, dict[str, str]] = {
    "listed": {"长期股权投资": "长期股权投资", "投资收益": "投资收益"},
    "soe": {},  # 见上：`其他应收款` 是同构子节（源 docx own_table_count=0），归 Task 6
}

# 沿用 soe 侧既有自动编号形态：主表 = 基名，其余 = 「{基名}（表N）」，N 从 2 起。
_SEQ_NAME_RE = re.compile(r"^(?P<base>.+?)（表(?P<n>\d+)）$")


def _seq_name(base: str, n: int) -> str:
    """N==1 → 主表名（基名本身）；N>=2 → 「{基名}（表N）」。"""
    return base if n <= 1 else f"{base}（表{n}）"


def _parse_seq(name: str, base: str) -> int | None:
    """把已是编号形态的表名解析回序号（主表 → 1），否则 None。"""
    if name == base:
        return 1
    m = _SEQ_NAME_RE.match(name)
    if m and m.group("base") == base:
        return int(m.group("n"))
    return None


def _norm_ws(s: str) -> str:
    """去掉全部空白（含全角空格）用于表名 ↔ 表头首格比对。"""
    return re.sub(r"[\s\u3000]+", "", s)


def _is_header_leak(name: str, tbl: dict[str, Any]) -> bool:
    """表名是否是「表头首格泄漏」（md 重建把 headers[0] 当表名）。

    必须叠「去空白后相等」判定：源模板表头带全角空格（``项  目``），而 headers[0]
    实测已被归一成 ``项目``，裸 ``==`` 会漏判。

    ``apply`` 与 ``check`` 共用本函数（单一判据，避免两侧漂移）。
    """
    headers = list(tbl.get("headers") or [])
    if not headers:
        return False
    h0 = str(headers[0] or "")
    if not h0.strip() or not name.strip():
        return False
    return _norm_ws(name) == _norm_ws(h0)


def _needs_rename(name: str, tbl: dict[str, Any], counts: Counter[str]) -> bool:
    """该表名是否需要正名。

    只动三类（**最小改动面** —— 唯一且语义清晰的名字一律保留，改它等于白白让既有
    ``sub_table_data`` 键失联）：

    1. **空名** —— 表名是 ``sub_table_data`` 的键，空名互相覆盖丢整表；
    2. **同子节内重名** —— 同上；
    3. **表头首格泄漏** —— 见 ``_is_header_leak``。
    """
    if not name.strip():
        return True
    if counts[name] > 1:
        return True
    return _is_header_leak(name, tbl)


def _plan_renames(
    tables: list[dict[str, Any]], base: str
) -> list[tuple[int, str, str]]:
    """规划一个子节内的正名动作。返回 ``[(索引, 旧名, 新名), ...]``（幂等：已合规不产出）。

    需求 6.4 的验收判据是「同子节内表名集合大小 == 表数量」；本函数在满足该判据的
    前提下**只改必须改的那几张**（见 ``_needs_rename``），并沿用既有 ``（表N）``
    编号不整体重排 —— 重排会让全部既有 ``sub_table_data`` 键失联。

    新编号 = 既有最大编号 + 1 起续排（不填补中间空缺，避免编号与表位置错位）。
    listed 侧三张表全需正名 ⇒ 无既有编号 ⇒ 从 1 起（主表名 = 基名本身）。
    """
    names = [str(t.get("name") or "") for t in tables]
    counts = Counter(names)
    to_fix = {
        i for i, nm in enumerate(names) if _needs_rename(nm, tables[i], counts)
    }

    # 保留下来的名字先占位：已是 `{base}（表N）` 形态的占其序号，其余占「名字」本身
    taken_seq: set[int] = set()
    taken_names: set[str] = set()
    for i, nm in enumerate(names):
        if i in to_fix:
            continue
        taken_names.add(nm)
        seq = _parse_seq(nm, base)
        if seq is not None:
            taken_seq.add(seq)

    # 新编号从**既有最大编号 + 1** 续排，不填补中间空缺 —— 填空缺会让编号与表在
    # 子节内的位置错位（soe 实测：既有 2/3/4/6/7，第 9 张表若拿到 5 会误导阅读）。
    plan: list[tuple[int, str, str]] = []
    nxt = (max(taken_seq) + 1) if taken_seq else 1
    for i in sorted(to_fix):
        while nxt in taken_seq or _seq_name(base, nxt) in taken_names:
            nxt += 1
        new = _seq_name(base, nxt)
        taken_seq.add(nxt)
        taken_names.add(new)
        plan.append((i, names[i], new))
    return plan


def _rename_table(tbl: dict[str, Any], new_name: str) -> None:
    """改名并把旧名登记进表级 ``legacy_aliases``（幂等）。

    ⚠️ 该字段当前零消费方（见模块 docstring），仅为 Task 12 预留。
    """
    old = str(tbl.get("name") or "")
    if old and old != new_name:
        _append_alias(tbl, old)
    tbl["name"] = new_name


def apply_table_renames(doc: dict[str, Any], variant: str) -> tuple[list[str], list[str]]:
    """Task 4：自有表子节内表名唯一化。**必须在补 columns（Task 7）之前执行**
    —— 列规则按表名索引，先补列会落到旧名上。"""
    changes: list[str] = []
    warnings: list[str] = []
    targets = RENAME_SECTIONS.get(variant) or {}
    if not targets:
        return changes, warnings

    kids = {str(k.get("section_title")): k for k in _parent_children(doc.get("sections") or [], variant)}
    for title, base in targets.items():
        kid = kids.get(title)
        if kid is None:
            warnings.append(f"{variant} 母公司章缺子节「{title}」→ 跳过 Task 4 该子节")
            continue
        tables = kid.get("tables") or []
        if not tables:
            warnings.append(f"{variant}/{title} 无 tables → 跳过")
            continue
        for idx, old, new in _plan_renames(tables, base):
            _rename_table(tables[idx], new)
            shown = old if old else "<空名>"
            changes.append(f"{variant}/{title} 表[{idx}]：「{shown}」→「{new}」")
    return changes, warnings


def check_table_renames(doc: dict[str, Any], variant: str) -> list[str]:
    """Task 4 的 ``--check`` 欠账清单（需求 6.4 / 6.6）。

    判据 = 同子节内**表名集合大小 == 表数量**（不是只查空串）+ 无空名 + 无表头首格泄漏；
    正名后的旧名必须能在表级 ``legacy_aliases`` 找到（需求 6.3）。

    ⚠️ **不断言「全部表名符合 `{base}（表N）` 范式」** —— soe 侧 11 张唯一且语义清晰的
    表名（``其他应收款账龄分析`` / ``其他应收款（续）类  别`` 等）是合法现值，
    压成 ``（表N）`` 只会让既有 ``sub_table_data`` 键失联。
    """
    errs: list[str] = []
    targets = RENAME_SECTIONS.get(variant) or {}
    if not targets:
        return errs
    kids = {
        str(k.get("section_title")): k
        for k in _parent_children(doc.get("sections") or [], variant)
    }
    for title, base in targets.items():
        kid = kids.get(title)
        if kid is None:
            errs.append(f"{variant} 母公司章缺子节「{title}」")
            continue
        tables = kid.get("tables") or []
        names = [str(t.get("name") or "") for t in tables]
        if len(set(names)) != len(names):
            dups = sorted({n for n in names if names.count(n) > 1})
            errs.append(
                f"{variant}/{title} 表名不唯一：表数={len(names)} 去重后={len(set(names))} 重名={dups}"
            )
        empties = [i for i, n in enumerate(names) if not n.strip()]
        if empties:
            errs.append(f"{variant}/{title} 存在空表名，索引={empties}")
        leaks = [
            (i, n)
            for i, (n, tbl) in enumerate(zip(names, tables))
            if _is_header_leak(n, tbl)
        ]
        if leaks:
            errs.append(f"{variant}/{title} 表名是表头首格泄漏：{leaks}")
        # 需求 6.3：正名后的旧名必须可在 legacy_aliases 找到
        for i, tbl in enumerate(tables):
            aliases = tbl.get("legacy_aliases")
            if aliases is not None and not isinstance(aliases, list):
                errs.append(f"{variant}/{title} 表[{i}] legacy_aliases 非列表：{aliases!r}")
    return errs


# ─────────────────────────── Task 5: 长期股权投资两级表头还原 ───────────────────────────

LTE_SECTION_TITLE = "长期股权投资"

# 源 docx 目标列数（Task 1 提取器实测，与守卫 ``LTE_COLS_DOCX`` 同源）。
# 🔴 soe 表 1(5)/表 2(7) **本来就与源一致**（需求 4.4 已裁决事项 6）⇒ ``rebuild_headers=False``，
# 只补 ``columns``，``headers``/``rows`` 一律不动。按「两版三张表全压扁」的错误前提去重写
# 会造成无谓 diff 并破坏零回归判据。
LTE_TARGET_COLS = {"listed": [7, 9, 13], "soe": [5, 7, 12]}

# Property 10：源 docx 的可扩行（``…``）与分组结构行必须保留，不得当占位删除。
# 键 = 该子节内表索引；值 = 必须仍存在的行 label。
LTE_PRESERVED_ROW_LABELS: dict[str, dict[int, tuple[str, ...]]] = {
    "listed": {2: ("①联营企业", "②合营企业", "…")},
    "soe": {2: ("一、合营企业", "二、联营企业", "…")},
}


def _lte_section(doc: dict[str, Any], variant: str) -> dict[str, Any] | None:
    kids = {
        str(k.get("section_title")): k
        for k in _parent_children(doc.get("sections") or [], variant)
    }
    return kids.get(LTE_SECTION_TITLE)


def _drop_header_label_rows(tbl: dict[str, Any]) -> int:
    """删除压扁的第二行表头残留（``row_type == "header_label"``）。返回删除条数。

    两级表头还原后，原先被压进 ``rows`` 的第二行表头由 ``ColumnDef.group`` 承载，
    留着会在附注正文渲染出一行空披露数据（平台既有铁律，`validate_section` 亦判它为错）。
    **只删 header_label**，``…`` 可扩行与 ``一、合营企业`` 类结构行一律保留（Property 10）。
    """
    rows = tbl.get("rows")
    if not isinstance(rows, list):
        return 0
    keep = [r for r in rows if str((r or {}).get("row_type") or "") != "header_label"]
    dropped = len(rows) - len(keep)
    if dropped:
        tbl["rows"] = keep
    return dropped


def _sync_column_groups(tbl: dict[str, Any], cols: list[dict[str, Any]]) -> str | None:
    """按 columns 派生 ``_column_groups``；单级表则移除该键。返回变更说明。"""
    want = derive_column_groups(cols)
    if want:
        if tbl.get("_column_groups") != want:
            tbl["_column_groups"] = json.loads(json.dumps(want, ensure_ascii=False))
            return f"_column_groups → {len(want)} 组（两级表头）"
        return None
    if tbl.pop("_column_groups", None) is not None:
        return "_column_groups → 删除（单级表头）"
    return None


# ── 自有表子节的「一张表」共用件（Task 5 与 Task 7 共用，禁抄第二份） ─────────
#
# Task 5（长期股权投资）与 Task 7（投资收益 / 现金流量表补充资料）对**单张表**的
# 目标态处置完全同构：`rebuild_headers` 决定是重建 headers 还是先校验再补 columns，
# 随后 columns / `_column_groups` / guidance 三件套。抽成一对函数供两处调用，
# 避免「改一处另一处不跟」的双真源。


def _apply_own_table(
    tbl: dict[str, Any], spec: dict[str, Any], where: str
) -> tuple[list[str], list[str]]:
    """把单张自有表写成 ``spec`` 的目标态。返回 ``(changes, warnings)``。

    - ``rebuild_headers=True``：``headers`` 重建为 columns 的**叶子**列名，父表头由
      ``ColumnDef.group`` 承载；压扁残留的 ``header_label`` 行删除。
    - ``rebuild_headers=False``：结构已与源 docx 一致 ⇒ **先校验** ``headers_of(columns)``
      与现有 headers 逐字相等，不等则告警跳过（宁缺勿造，绝不静默写入与 headers 不符的
      columns —— 那会让前端列头与数据键错位）。

    ``key`` 由本脚本首次声明（母公司章现状 ``columns`` 全为 null ⇒ 无既有 key 可丢）；
    ``rows`` 除 ``header_label`` 外一律不动（Property 10：``…`` 可扩行与结构行保留）。
    """
    changes: list[str] = []
    warnings: list[str] = []
    cols: list[dict[str, Any]] = spec["columns"]
    want_headers = headers_of(cols)

    if spec["rebuild_headers"]:
        if list(tbl.get("headers") or []) != want_headers:
            old = len(tbl.get("headers") or [])
            tbl["headers"] = list(want_headers)
            changes.append(f"{where} headers：{old} → {len(want_headers)} 列（两级表头叶子名）")
        dropped = _drop_header_label_rows(tbl)
        if dropped:
            changes.append(f"{where} 删除 {dropped} 行 header_label（压扁的第二行表头残留）")
    else:
        if list(tbl.get("headers") or []) != want_headers:
            warnings.append(
                f"{where} headers 与目标 columns 不符 → 跳过（不写入与 headers 不一致的 columns）\n"
                f"      现有: {tbl.get('headers')}\n      目标: {want_headers}"
            )
            return changes, warnings

    if tbl.get("columns") != cols:
        tbl["columns"] = json.loads(json.dumps(cols, ensure_ascii=False))
        changes.append(f"{where} columns → {len(cols)} 列")

    note = _sync_column_groups(tbl, cols)
    if note:
        changes.append(f"{where} {note}")

    guidance = str(spec.get("guidance") or "")
    if guidance and tbl.get("guidance") != guidance:
        tbl["guidance"] = guidance
        changes.append(f"{where} guidance → {len(guidance)} 字")
    return changes, warnings


def _check_own_table(tbl: dict[str, Any], spec: dict[str, Any], where: str) -> list[str]:
    """单张自有表的 ``--check`` 判据（Property 12 在自有表子节的部分）。

    判据九条（与后端 ``note_sub_table_projector._extract_column_groups`` 三态同口径）：
    columns 非空 / 长度 == headers / ``columns[0].label == headers[0]`` / 首列标
    ``is_label`` / 显式表态（``group`` 或 ``flat``，不得并存也不得都无）/ 标签列不带
    ``group`` / ``group`` 不含 ``/`` / ``columns`` 与目标态逐字相等 /
    ``_column_groups`` 与 ``columns.group`` 一致；外加 guidance 非空且无 markdown 粗体
    （需求 5.2 / 5.3）与 ``header_label`` 残留检查。
    """
    errs: list[str] = []
    cols_want: list[dict[str, Any]] = spec["columns"]
    cols = tbl.get("columns") or []
    headers = list(tbl.get("headers") or [])

    if not cols:
        errs.append(f"{where} 缺 columns")
    else:
        if len(cols) != len(headers):
            errs.append(f"{where} columns={len(cols)} ≠ headers={len(headers)}")
        if headers and str(cols[0].get("label") or "") != str(headers[0]):
            errs.append(
                f"{where} columns[0].label={cols[0].get('label')!r} ≠ headers[0]={headers[0]!r}"
            )
        if cols[0].get("is_label") is not True:
            errs.append(f"{where} 首列未标 is_label")
        has_group = any(c.get("group") for c in cols)
        has_flat = any(c.get("flat") for c in cols)
        if has_group and has_flat:
            errs.append(f"{where} columns 表态冲突（flat 与 group 并存）")
        if not has_group and not has_flat:
            errs.append(f"{where} columns 未表态（会触发 _infer_groups_from_headers 前缀推断）")
        if has_group and cols[0].get("group"):
            errs.append(f"{where} 标签列不得带 group")
        if any("/" in str(c.get("group") or "") for c in cols):
            errs.append(f"{where} group 含 '/'（前端只认扁平 {{group,start,span}}）")
        if cols != cols_want:
            errs.append(f"{where} columns 与目标态不一致（源 docx 裁决）")

    want_groups = derive_column_groups(cols_want)
    groups = tbl.get("_column_groups")
    if want_groups:
        if groups != want_groups:
            errs.append(f"{where} _column_groups 与 columns.group 不一致")
    elif groups is not None:
        errs.append(f"{where} 单级表头仍残留 _column_groups")

    guidance = str(tbl.get("guidance") or "").strip()
    if not guidance:
        errs.append(f"{where} 缺 guidance")
    elif "**" in guidance:
        errs.append(f"{where} guidance 含 markdown 粗体（需求 5.3 要求纯文本）")

    if spec["rebuild_headers"] and any(
        str((r or {}).get("row_type") or "") == "header_label" for r in (tbl.get("rows") or [])
    ):
        errs.append(f"{where} 仍残留 header_label 行（压扁的第二行表头）")
    return errs


def apply_lte_tables(doc: dict[str, Any], variant: str) -> tuple[list[str], list[str]]:
    """Task 5：还原长期股权投资 3 张表的两级表头 + 补 columns/guidance。

    - listed 3 表：``headers`` 重建为源 docx 的**叶子**列名，父表头走 ``ColumnDef.group``；
      压扁残留的 ``header_label`` 行删除。
    - soe 表 1/表 2：``rebuild_headers=False`` ⇒ 只补 ``columns``，且**先校验**
      ``headers_of(columns)`` 与现有 headers 逐字相等，不等则告警跳过（宁缺勿造，
      绝不静默写入与 headers 不符的 columns）。
    - soe 表 3：与 listed 同款重建。

    ``key`` 由本脚本首次声明（现状 ``columns`` 全为 null ⇒ 无既有 key 可丢）；
    ``rows`` 除 header_label 外一律不动。
    """
    changes: list[str] = []
    warnings: list[str] = []
    kid = _lte_section(doc, variant)
    if kid is None:
        return changes, [f"{variant} 母公司章缺子节「{LTE_SECTION_TITLE}」→ 跳过 Task 5"]

    tables = kid.get("tables") or []
    specs = OWN_RULES[variant][LTE_SECTION_TITLE]
    if len(tables) != len(specs):
        return changes, [
            f"{variant}/{LTE_SECTION_TITLE} 表数应为 {len(specs)}，实为 {len(tables)}"
            " → 跳过 Task 5（表数变更需重新裁决）"
        ]

    for i, (tbl, spec) in enumerate(zip(tables, specs)):
        # 单张表的处置与 Task 7 同构 ⇒ 走共用件 `_apply_own_table`（禁抄第二份）
        c, w = _apply_own_table(
            tbl, spec, f"{variant}/{LTE_SECTION_TITLE} 表[{i}]「{tbl.get('name')}」"
        )
        changes += c
        warnings += w

    return changes, warnings


def check_lte_tables(doc: dict[str, Any], variant: str) -> list[str]:
    """Task 5 的 ``--check`` 欠账清单（Property 9 / 10 / 12 在长期股权投资子节的部分）。"""
    errs: list[str] = []
    kid = _lte_section(doc, variant)
    if kid is None:
        return [f"{variant} 母公司章缺子节「{LTE_SECTION_TITLE}」"]

    tables = kid.get("tables") or []
    specs = OWN_RULES[variant][LTE_SECTION_TITLE]
    target = LTE_TARGET_COLS[variant]
    actual_cols = [len(t.get("headers") or []) for t in tables]
    if actual_cols != target:
        errs.append(
            f"{variant}/{LTE_SECTION_TITLE} headers 列数应为 {target}（源 docx），实为 {actual_cols}"
        )
    if len(tables) != len(specs):
        return errs + [
            f"{variant}/{LTE_SECTION_TITLE} 表数应为 {len(specs)}，实为 {len(tables)}"
        ]

    for i, (tbl, spec) in enumerate(zip(tables, specs)):
        where = f"{variant}/{LTE_SECTION_TITLE} 表[{i}]「{tbl.get('name')}」"
        # 列元数据 / guidance / header_label 判据走共用件（与 Task 7 同一实现）
        errs += _check_own_table(tbl, spec, where)

        rows = tbl.get("rows") or []
        labels = [str((r or {}).get("label") or "") for r in rows]
        for keep in LTE_PRESERVED_ROW_LABELS.get(variant, {}).get(i, ()):  # Property 10
            if keep not in labels:
                errs.append(
                    f"{where} 丢失源 docx 结构行/可扩行「{keep}」（需求 4.6 禁当占位删除）"
                )
    return errs


# ─────────────────────────── Task 6: 同构子节对齐合并章 ───────────────────────────
#
# 用户 2026-08-06 裁决 = **整体替换** ``tables``（不做逐表 diff/合并）。
# 源 = 本变体**合并章**对应科目子节（``ISOMORPHIC_SOURCE`` 的 section_number）。
#
# 🔴 三条硬约束：
#
# 1. **深拷贝**（``json.loads(json.dumps(...))``）—— 否则母公司章与合并章共享同一批
#    dict 对象，任一侧后续改动会互相污染，且合并章零回归判据会以诡异方式打红。
# 2. **剥 markdown 粗体** —— 合并章源侧本身带 `**`（实测 2 处：`listed 五、8` 的
#    「应收政府补助情况」= `**逐项**`；`soe 八、9` 的「按账龄披露其他应收款项」=
#    `**单级 3 列**`），需求 5.3 / Property 12 禁粗体 ⇒ 复制管道里必须剥。
#    这两处在合并章里是**预存在缺陷、属另一半径**，本脚本对合并章只读，绝不顺手改
#    （Property 28 零回归）。剥离一律走平台级 ``strip_pairs``（成对非贪婪）。
# 3. **被替换掉的旧表名进子节级 ``_removed_table_keys``**，语义沿用服务端
#    ``wp_disclosure_sync_service._extract_removed_table_keys``：即「本次推送键」要
#    从 removed 集合里剔除（与新表名求差集），否则会把刚写入的表当孤儿删。
#
# ⚠️ ``_removed_table_keys`` 在**模板 JSON 侧此前无先例**（既有脚本都是把旧名登记在
#    脚本常量里、由前端载荷上报）。当前**零消费方** —— 服务端那个函数读的是
#    ``sub_table_data._removed_table_keys``（前端推送载荷），不读模板。此处写入是给
#    Task 12 取数接线预留迁移映射，**不得声称「附注残留空表问题已解决」**（同表级
#    ``legacy_aliases`` 那个已登记的坑）。

#: 子节级 removed 键的字段名（与服务端载荷侧同名，便于 Task 12 直接搬运）
REMOVED_TABLE_KEYS_FIELD = "_removed_table_keys"


def _strip_bold_deep(node: Any) -> tuple[Any, int]:
    """递归剥离 ``**成对粗体**``。返回 ``(新节点, 剥离对数)``。

    只处理 str / list / dict，其余类型原样返回。**不就地修改入参** —— 调用方传进来的
    已经是深拷贝，但保持纯函数语义便于单测。
    """
    if isinstance(node, str):
        return strip_pairs(node)
    if isinstance(node, list):
        total = 0
        out_l: list[Any] = []
        for item in node:
            new, n = _strip_bold_deep(item)
            out_l.append(new)
            total += n
        return out_l, total
    if isinstance(node, dict):
        total = 0
        out_d: dict[str, Any] = {}
        for k, v in node.items():
            new, n = _strip_bold_deep(v)
            out_d[k] = new
            total += n
        return out_d, total
    return node, 0


def _find_section_by_number(
    sections: list[dict[str, Any]], section_number: str
) -> dict[str, Any] | None:
    """按 ``section_number`` 定位合并章子节。

    实测 7 个源 section_number 在各自变体内**唯一命中**（无歧义）；多命中即返回 None
    并由调用方告警（宁缺勿造，绝不静默取第一条）。
    """
    hits = [s for s in sections if s.get("section_number") == section_number]
    return hits[0] if len(hits) == 1 else None


def build_isomorphic_tables(
    source_tables: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """从合并章 ``tables`` 造出母公司侧的目标态。返回 ``(新 tables, 剥离粗体对数)``。

    - **深拷贝**（一次 dumps/loads），母公司侧与合并章不共享任何对象；
    - 剥 markdown 粗体（需求 5.3）；
    - 清掉合并章的 ``_aligned_by`` / ``_aligned_at`` 表级戳记（那是别的 spec 的署名，
      带过来会让「谁对齐了这张表」失真；母公司章的戳记由 ``stamp()`` 打在 section 上）。

    ``key`` 沿用合并章原值（母公司侧现状 ``columns`` 全 null ⇒ 无既有 key 可丢，
    同 Task 5 理由）。``name``/``headers``/``rows``/``columns``/``_column_groups``/
    ``guidance`` 一律逐字继承，从而「表集合与列结构一致」（需求 4.1）天然成立。
    """
    cloned = json.loads(json.dumps(source_tables, ensure_ascii=False))
    stripped, pairs = _strip_bold_deep(cloned)
    out: list[dict[str, Any]] = []
    for tbl in stripped:
        if isinstance(tbl, dict):
            tbl.pop("_aligned_by", None)
            tbl.pop("_aligned_at", None)
        out.append(tbl)
    return out, pairs


def merge_removed_table_keys(
    existing: Any, old_names: list[str], new_names: list[str]
) -> list[str]:
    """合并 ``_removed_table_keys``：并入旧名，再**与本次写入的新表名求差集**。

    差集语义沿用服务端 ``_extract_removed_table_keys`` 的「跳过本次推送键」——
    旧名与新名相同的表（同构对齐后大量表名不变）不得进 removed，否则消费方接上时
    会把刚写入的表当孤儿删掉。空名（现状 listed 侧有 7 张空名表）不登记。

    ``old_names`` 由调用方汇总，**须同时包含被替换表的 ``name`` 与其表级
    ``legacy_aliases`` 里的更旧名**（见 ``collect_replaced_table_names``）——
    否则 Task 4 正名产生的中间名会成为唯一记录、更早的原始名彻底丢失。
    """
    acc: list[str] = []
    seen: set[str] = set()
    for name in list(existing or []) + old_names:
        s = str(name or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        acc.append(s)
    kept = set(new_names)
    return [n for n in acc if n not in kept]


def collect_replaced_table_names(tables: Any) -> list[str]:
    """收集被替换表的**全部历史名**：``name`` + 表级 ``legacy_aliases``。

    整体替换会丢弃整个表对象，其表级 ``legacy_aliases`` 随之消失 ⇒ 只并入 ``name``
    的话，Task 4 正名过的表只留下**中间名**（``其他应收款（表8..11）``）而更早的
    原始名（``其他应收款（续）债务人名称``）彻底无迹可寻。故两者一并并入子节级
    ``_removed_table_keys``，让 Task 12 的迁移映射能覆盖完整链条。

    保序 + 去重；空名跳过（``merge_removed_table_keys`` 也会兜一层，此处提前过滤
    只为让返回值本身干净可断言）。
    """
    out: list[str] = []
    seen: set[str] = set()

    def _push(value: Any) -> None:
        s = str(value or "").strip()
        if not s or s in seen:
            return
        seen.add(s)
        out.append(s)

    for tbl in list(tables or []):
        if not isinstance(tbl, dict):
            continue
        _push(tbl.get("name"))
        aliases = tbl.get("legacy_aliases")
        if isinstance(aliases, list):
            for alias in aliases:
                _push(alias)
    return out


#: 母公司侧允许**多**于合并章的表级 additive 字段（Task 11 的 `report_row_code`）。
#:
#: 需求 4.1 的对齐口径是「表集合与列结构一致」，不涉及取数元数据；而需求 8.3 要求母公司章
#: 的表具备 `report_row_code`，合并章又是**只读源**（Property 28 零回归，绝不反向给它加码）
#: ⇒ 两条需求只能靠「比对时剔除该字段 + 替换时按表名搬运」共存。
#:
#: 🔴 **白名单只许收窄不许扩张** —— 每多一个字段就等于给 Task 6 的深相等判据开一个盲区。
ISOMORPHIC_PARENT_ONLY_FIELDS: tuple[str, ...] = ("report_row_code",)


def strip_parent_only_fields(tbl: Any) -> Any:
    """剔除母公司侧 additive 字段后的表副本（非 dict 原样返回）。"""
    if not isinstance(tbl, dict):
        return tbl
    return {k: v for k, v in tbl.items() if k not in ISOMORPHIC_PARENT_ONLY_FIELDS}


def carry_parent_only_fields(
    old_tables: Any, new_tables: list[dict[str, Any]]
) -> list[str]:
    """整体替换前把母公司侧 additive 字段按**表名**搬到新表上。返回搬运说明。

    不搬运会让 Task 6 的替换每次擦掉 Task 11 写入的 `report_row_code`（`apply` 顺序上
    Task 11 在后、结果虽仍收敛，但 apply 每轮都报变更 = 幂等空操作永不成立）。

    表名在两侧都必须**恰好出现一次**才搬（`PARENT_TABLE_CENSUS` 实测 12/12 子节表名唯一）；
    多命中一律跳过并说明（宁缺勿造，绝不猜哪一张）。
    """
    notes: list[str] = []
    olds = [t for t in list(old_tables or []) if isinstance(t, dict)]
    old_names = [str(t.get("name") or "") for t in olds]
    new_names = [str(t.get("name") or "") for t in new_tables]
    for tbl, name in zip(olds, old_names):
        carry = {k: tbl[k] for k in ISOMORPHIC_PARENT_ONLY_FIELDS if k in tbl}
        if not carry:
            continue
        if not name or old_names.count(name) != 1 or new_names.count(name) != 1:
            notes.append(
                f"表名「{name}」在替换两侧非唯一命中 → 不搬运 {sorted(carry)}（宁缺勿造）"
            )
            continue
        new_tables[new_names.index(name)].update(carry)
        notes.append(f"表「{name}」搬运 {sorted(carry)}")
    return notes


def _isomorphic_children(
    doc: dict[str, Any], variant: str
) -> dict[str, dict[str, Any]]:
    return {
        str(k.get("section_title")): k
        for k in _parent_children(doc.get("sections") or [], variant)
    }


def apply_isomorphic(doc: dict[str, Any], variant: str) -> tuple[list[str], list[str]]:
    """Task 6：同构子节按合并章整体替换 ``tables``（需求 4.1 / 4.7 / 4.8）。

    自有表子节（``OWN_TABLE_SECTIONS``）**不参与**，子节数量不增删（需求 4.8）。
    合并章为只读源（Property 28）。
    """
    changes: list[str] = []
    warnings: list[str] = []
    mapping = ISOMORPHIC_SOURCE.get(variant) or {}
    if not mapping:
        return changes, warnings

    sections = doc.get("sections") or []
    kids = _isomorphic_children(doc, variant)
    own = set(OWN_TABLE_SECTIONS.get(variant) or ())

    for title, src_number in mapping.items():
        if title in own:  # 防常量被误改成交集
            warnings.append(
                f"{variant}/{title} 同时出现在 ISOMORPHIC_SOURCE 与 OWN_TABLE_SECTIONS"
                " → 跳过（自有表子节不参与对齐，需求 4.2）"
            )
            continue
        kid = kids.get(title)
        if kid is None:
            warnings.append(f"{variant} 母公司章缺子节「{title}」→ 跳过 Task 6 该子节")
            continue
        src = _find_section_by_number(sections, src_number)
        if src is None:
            warnings.append(
                f"{variant}/{title} 合并章源「{src_number}」未唯一命中 → 跳过（宁缺勿造）"
            )
            continue
        src_tables = src.get("tables") or []
        if not src_tables:
            warnings.append(f"{variant}/{title} 合并章源「{src_number}」无 tables → 跳过")
            continue

        target, pairs = build_isomorphic_tables(src_tables)
        # 🔴 母公司侧 additive 字段（Task 11 的 report_row_code）按表名搬到新表上 ——
        # 不搬则本轮替换擦掉它、Task 11 再写回，apply 每轮都报变更（幂等空操作永不成立）
        carried = carry_parent_only_fields(kid.get("tables"), target)
        # 🔴 整体替换前先收集被替换表的 name **与表级 legacy_aliases 里的旧名**
        # （替换会丢弃整个表对象，只并入 name 会让 Task 4 的原始名彻底丢失）
        old_names = collect_replaced_table_names(kid.get("tables"))
        new_names = [str(t.get("name") or "") for t in target]

        if kid.get("tables") == target:
            continue  # 幂等空操作
        for note in carried:
            changes.append(f"{variant}/{title} 同构替换保留母公司侧字段：{note}")

        old_count = len(kid.get("tables") or [])
        kid["tables"] = target
        changes.append(
            f"{variant}/{title} tables 整体替换为合并章「{src_number}」"
            f"：{old_count} → {len(new_names)} 张"
            + (f"（剥离 {pairs} 对 markdown 粗体）" if pairs else "")
        )
        removed = merge_removed_table_keys(
            kid.get(REMOVED_TABLE_KEYS_FIELD), old_names, new_names
        )
        if removed != (kid.get(REMOVED_TABLE_KEYS_FIELD) or []):
            kid[REMOVED_TABLE_KEYS_FIELD] = removed
            changes.append(
                f"{variant}/{title} {REMOVED_TABLE_KEYS_FIELD} → {len(removed)} 个旧表名"
                "（已与本次写入表名求差集；当前零消费方，为 Task 12 预留）"
            )
    return changes, warnings


def check_isomorphic(doc: dict[str, Any], variant: str) -> list[str]:
    """Task 6 的 ``--check`` 欠账清单。

    判据 = 母公司子节 ``tables`` 与合并章对应子节 ``tables`` **深相等**，
    除两项已登记差异：表级 ``_aligned_by``/``_aligned_at`` 戳记 与 已剥离的粗体。
    守卫侧 **import 本函数**交叉锁死，不在测试里重抄判据。
    """
    errs: list[str] = []
    mapping = ISOMORPHIC_SOURCE.get(variant) or {}
    if not mapping:
        return errs
    sections = doc.get("sections") or []
    kids = _isomorphic_children(doc, variant)
    own = set(OWN_TABLE_SECTIONS.get(variant) or ())

    for title, src_number in mapping.items():
        if title in own:
            errs.append(
                f"{variant}/{title} 被同时登记为同构与自有表子节（常量冲突，需求 4.2）"
            )
            continue
        kid = kids.get(title)
        if kid is None:
            errs.append(f"{variant} 母公司章缺子节「{title}」")
            continue
        src = _find_section_by_number(sections, src_number)
        if src is None:
            errs.append(f"{variant}/{title} 合并章源「{src_number}」未唯一命中")
            continue
        want, _ = build_isomorphic_tables(src.get("tables") or [])
        got = kid.get("tables") or []
        if len(got) != len(want):
            errs.append(
                f"{variant}/{title} 表数应与合并章「{src_number}」一致（{len(want)}），实为 {len(got)}"
            )
            continue
        for i, (g_raw, w) in enumerate(zip(got, want)):
            # 剔除母公司侧 additive 字段后再比 —— 见 ISOMORPHIC_PARENT_ONLY_FIELDS 的依据
            g = strip_parent_only_fields(g_raw)
            if g != w:
                gname, wname = str(g.get("name")), str(w.get("name"))
                if gname != wname:
                    errs.append(
                        f"{variant}/{title} 表[{i}] 名「{gname}」≠ 合并章「{wname}」"
                    )
                else:
                    diff = sorted(
                        k for k in set(g) | set(w) if g.get(k) != w.get(k)
                    )
                    errs.append(
                        f"{variant}/{title} 表[{i}]「{gname}」与合并章不一致，字段={diff}"
                    )
    return errs


# ─────────────────────── Task 7: 列元数据与编制指引补齐 ───────────────────────
#
# 处理范围 = **自有表子节里除长期股权投资以外的那些**（LTE 归 Task 5，同一对
# `_apply_own_table` / `_check_own_table` 共用件）：
#   listed = 投资收益（1 表）
#   soe    = 投资收益（1 表）、现金流量表补充资料（1 表）
# 同构子节（7 个）的 columns/guidance 由 Task 6 按合并章整体替换时**继承齐备**，
# 不在本任务范围 —— 在此重写会与 `check_isomorphic` 的「与合并章深相等」判据打架。
#
# 目标态取自 `OWN_RULES`（columns + guidance + rebuild_headers），与 Task 5 同一真源。

#: 本任务覆盖的子节（= 自有表子节 − 长期股权投资）
COLUMNS_SECTIONS: dict[str, tuple[str, ...]] = {
    variant: tuple(t for t in titles if t != LTE_SECTION_TITLE)
    for variant, titles in OWN_TABLE_SECTIONS.items()
}

#: 各子节的目标表名（供 kit `validate_section` 的 `expected` 参数）。
#: 三张表的目标名都等于子节标题：soe 两张现值即如此；listed/投资收益 由
#: `apply_table_renames` 从泄漏名「项  目」正名而来（主表 N==1 ⇒ 名 = 基名）。
#: 显式声明而非从 JSON 现值反推 —— 反推会让 `validate_section` 的表名判据空转。
COLUMNS_TARGET_NAMES: dict[str, dict[str, tuple[str, ...]]] = {
    "listed": {"投资收益": ("投资收益",)},
    "soe": {"投资收益": ("投资收益",), "现金流量表补充资料": ("现金流量表补充资料",)},
}


def _own_section(doc: dict[str, Any], variant: str, title: str) -> dict[str, Any] | None:
    kids = {
        str(k.get("section_title")): k
        for k in _parent_children(doc.get("sections") or [], variant)
    }
    return kids.get(title)


def apply_columns(doc: dict[str, Any], variant: str) -> tuple[list[str], list[str]]:
    """Task 7：自有表子节（除长期股权投资）补 ``columns`` + ``guidance``。

    **必须在 `apply_table_renames` 之后执行** —— `OWN_RULES` 按子节标题索引、
    `COLUMNS_TARGET_NAMES` 按目标表名断言，先补列会落到尚未正名的旧表名上。
    """
    changes: list[str] = []
    warnings: list[str] = []
    for title in COLUMNS_SECTIONS.get(variant) or ():
        kid = _own_section(doc, variant, title)
        if kid is None:
            warnings.append(f"{variant} 母公司章缺子节「{title}」→ 跳过 Task 7 该子节")
            continue
        tables = kid.get("tables") or []
        specs = OWN_RULES.get(variant, {}).get(title) or []
        if not specs:
            warnings.append(f"{variant}/{title} 无 OWN_RULES 目标态 → 跳过（宁缺勿造）")
            continue
        if len(tables) != len(specs):
            warnings.append(
                f"{variant}/{title} 表数应为 {len(specs)}，实为 {len(tables)}"
                " → 跳过（表数变更需重新裁决）"
            )
            continue
        for i, (tbl, spec) in enumerate(zip(tables, specs)):
            c, w = _apply_own_table(
                tbl, spec, f"{variant}/{title} 表[{i}]「{tbl.get('name')}」"
            )
            changes += c
            warnings += w
    return changes, warnings


def check_columns(doc: dict[str, Any], variant: str) -> list[str]:
    """Task 7 的 ``--check`` 欠账清单（Property 12 在自有表子节的部分）。

    两层判据，缺一不可：

    1. **逐表**走共用件 `_check_own_table`（与 Task 5 同一实现）；
    2. **子节级**走平台共享 kit 的 `validate_section` —— 它额外覆盖表名齐备唯一 /
       headers 无空串无 HTML / 同组内列名不重复 / `_column_groups` 越界 /
       `text_sections` 含裸表名（会被当披露正文渲染）等本函数不重抄的判据。
    """
    errs: list[str] = []
    for title in COLUMNS_SECTIONS.get(variant) or ():
        kid = _own_section(doc, variant, title)
        if kid is None:
            errs.append(f"{variant} 母公司章缺子节「{title}」")
            continue
        tables = kid.get("tables") or []
        specs = OWN_RULES.get(variant, {}).get(title) or []
        if not specs:
            errs.append(f"{variant}/{title} 缺 OWN_RULES 目标态（常量被误删？）")
            continue
        if len(tables) != len(specs):
            errs.append(f"{variant}/{title} 表数应为 {len(specs)}，实为 {len(tables)}")
            continue
        for i, (tbl, spec) in enumerate(zip(tables, specs)):
            errs += _check_own_table(
                tbl, spec, f"{variant}/{title} 表[{i}]「{tbl.get('name')}」"
            )
        expected = list(COLUMNS_TARGET_NAMES.get(variant, {}).get(title) or ())
        for e in validate_section(kid, expected):
            errs.append(f"{variant}/{title} {e}")
    return errs


def apply_chapter_intro(doc: dict[str, Any], variant: str) -> tuple[list[str], list[str]]:
    """Task 7：把源 docx 的章首说明补进母公司章 ``text_sections``（需求 5.2）。

    - soe：追加 `SOE_CHAPTER_INTRO` 五段（`ensure_text_sections` 只补缺段、已有不动、
      **无 `#### ` 前缀** —— 加前缀会被判成标题而静默丢弃）。
    - listed：源 docx 无章首说明段落 ⇒ **空操作**（宁缺勿造）。
    """
    changes: list[str] = []
    warnings: list[str] = []
    required = CHAPTER_INTRO.get(variant) or []
    if not required:
        return changes, warnings

    chapter = _find_parent_chapter(doc.get("sections") or [], variant)
    if chapter is None:
        return changes, [f"{variant} 母公司章不存在 → 跳过 Task 7 章首说明"]

    # 写入前自检：任一段被判成标题就整体跳过（写进去等于静默丢弃，比不写更坏）
    titled = [p for p in required if is_title_paragraph(p)]
    if titled:
        return changes, [
            f"{variant} 章首说明有 {len(titled)} 段会被判成标题段（`#` 开头或 ≤20 字编号标题）"
            " → 跳过（写入会被 disclosure_engine 静默丢弃）："
            + "；".join(f"「{p[:20]}…」" for p in titled)
        ]

    for note in ensure_text_sections(chapter, required):
        changes.append(f"{variant} 章首 {note}")
    return changes, warnings


def check_chapter_intro(doc: dict[str, Any], variant: str) -> list[str]:
    """Task 7 章首说明的 ``--check`` 欠账清单。

    三条判据：缺段（`missing_text_sections`）/ 任一段被判成标题（会静默丢弃）/
    含 markdown 粗体（需求 5.3）。listed 侧反向断言「不得凭空造章首文字」。
    """
    errs: list[str] = []
    chapter = _find_parent_chapter(doc.get("sections") or [], variant)
    if chapter is None:
        return [f"{variant} 母公司章不存在"]
    required = CHAPTER_INTRO.get(variant) or []
    paras = chapter.get("text_sections")
    paras = list(paras) if isinstance(paras, list) else []

    if not required:
        # listed：源 docx 无章首说明 ⇒ 模板侧也不得有（宁缺勿造，写入即打红）
        if paras:
            errs.append(
                f"{variant} 母公司章 text_sections 应为空（源 docx 该章无章首说明段落），"
                f"实有 {len(paras)} 段：{[str(p)[:20] for p in paras]}"
            )
        return errs

    for miss in missing_text_sections(chapter, required):
        errs.append(f"{variant} 章首缺源 docx 说明段：「{str(miss).strip()[:24]}…」")
    for p in required:
        if is_title_paragraph(p):
            errs.append(
                f"{variant} 章首说明段「{str(p)[:20]}…」会被判成标题段而静默丢弃"
                "（需求 5.2 要求它作为披露正文可见）"
            )
    for p in paras:
        if "**" in str(p):
            errs.append(
                f"{variant} 章首说明段含 markdown 粗体（需求 5.3 要求纯文本）：「{str(p)[:24]}…」"
            )
    return errs


# ─────────────────── Task 11: report_row_code 实证对账 ───────────────────
#
# 需求 8.3：母公司章的表须具备 `report_row_code`，取值按 `report_config` **实证对账**，
# 不得按名称推断。查不到 → 留 None 并在本节的登记表里写明理由（宁缺勿造）。
#
# 🔴🔴 **三条落地口径（与 spec 字面有分歧，逐条写明依据）**
#
# 1. **落在表级（`tables[]` 上），不落行级。**
#    全库实测（2026-08-06）：`report_row_code` **表级 0 处**、行级 listed 94 处 / soe 27 处，
#    唯一生产消费方是 `note_shared_table_segments`（读 `row.get("report_row_code")` 切段）
#    与 `note_formula_generator`（行级 `REPORT()` 兜底）⇒ **表级取值当前无消费方（inert）**。
#    仍落表级的两条依据：① 需求 8.3 与 tasks.md Task 11 都写「母公司章各**表**的
#    `report_row_code`」；② 本 spec 的零回归红线要求母公司章 `rows` 一律不动
#    （Task 4~7 成果）⇒ 行级写入在本任务里结构上不可行。
#    → 下游若要消费，应在另立 spec 里决定「表级读取」还是「段首行落码」，**不要**
#    在本任务里顺手改 `rows`。
#
# 2. **「留 None」落地为「不写该键」**，不写 `"report_row_code": null`。
#    `t.get("report_row_code")` 恒 `None`，与全库其余 700+ 张表形态一致；给 97 张表
#    塞显式 null 只会让 1.35 MB / 851 KB 的模板 JSON 更大，且无任何消费方能区分两者。
#
# 3. **对账必须分象限**：`report_config` 无 `project_id` 列（纯模板表，实测 18 列），
#    按 `applicable_standard` 分四象限存 1222 行；**同一 row_code 在不同象限可能是完全
#    不同的科目**（实测 `BS-018` listed=流动资产合计 / soe=存货；`BS-075` listed=股本 /
#    soe=其他应付款，全库「一码两义」78 条）⇒ listed 侧只查 `listed_*`、soe 侧只查 `soe_*`。
#
# **对账结果（2026-08-06 连库实测，四象限逐条比对）**
#
# | row_code | report_type      | 四象限 row_name | 说明 |
# |---|---|---|---|
# | BS-005 | balance_sheet    | 应收票据       | 四象限逐字一致 |
# | BS-006 | balance_sheet    | 应收账款       | 四象限逐字一致（子节无汇总主表 ⇒ 不填） |
# | BS-009 | balance_sheet    | 其他应收款     | 四象限逐字一致 |
# | BS-024 | balance_sheet    | 长期股权投资   | 四象限逐字一致 |
# | IS-011 | income_statement | 投资收益       | 四象限逐字一致 |
#
# 五个 row_name 在**每个**象限内都恰好只有 1 个 row_code（`GROUP BY` 实测 n=1 × 20 组）
# ⇒ 「同 (report_type, row_name) 唯一码」结构性成立，不存在选码歧义。

#: 各变体对账所用象限（entity 的两个 scope 都查 —— 五个目标码在两 scope 下 row_name 相同）
ROW_CODE_QUADRANTS: dict[str, tuple[str, ...]] = {
    "listed": ("listed_standalone", "listed_consolidated"),
    "soe": ("soe_standalone", "soe_consolidated"),
}

#: 理由必须命中的实证标记（防「无法确定」这类空话冒充理由）
ROW_CODE_EVIDENCE_MARKERS: tuple[str, ...] = ("实证", "report_config", "源 docx", "合并章")

#: 理由最短长度（含实证依据的理由不可能短于此）
ROW_CODE_REASON_MIN_LEN = 24

# 行名归一化：**只许**去空白（含全角空格）+ 去行业适用性标记 `△▲※*`。
# 再激进（去括注 / 去「其中：」/ 模糊匹配）会放过真错位 —— 见 `check_row_name_selfcheck`
# 的反向自检「把『其他应收款』落在『货币资金』行上仍判不符」。
_ROW_NAME_NOISE_RE = re.compile(r"[\s\u3000\u00a0△▲※*]+")


def normalize_row_name(text: Any) -> str:
    """行名/子节名归一化（去空白 + 去行业适用性标记），其余字符一律保留。"""
    return _ROW_NAME_NOISE_RE.sub("", str(text or ""))


def is_row_name_comparable(section_title: Any, row_name: Any) -> bool:
    """归一后**严格相等**才算可比对（空串一律不可比对）。"""
    left = normalize_row_name(section_title)
    return bool(left) and left == normalize_row_name(row_name)


@dataclass(frozen=True)
class ReportRowRef:
    """一条已与 `report_config` 对账过的报表行引用。"""

    row_code: str
    row_name: str
    report_type: str
    quadrants: tuple[str, ...]
    evidence: str


@dataclass(frozen=True)
class RowCodePlan:
    """一个母公司章子节的 `report_row_code` 目标态。

    Attributes:
        ref: 该子节科目对应的报表行（已对账）。``None`` = 该子节整体无唯一报表行。
        main_table: 填码的那张表名。``None`` = 本子节**一张都不填**（宁缺勿造）。
            非 ``None`` 时必须在该子节表名里**恰好出现一次**（禁两张表填同一码，
            下游取数会双算）。
        section_reason: 本子节**未填表**的统一理由（须含实证标记）。
        table_reasons: 个别表的专属理由（覆盖 ``section_reason``）。
    """

    ref: ReportRowRef | None
    main_table: str | None
    section_reason: str
    table_reasons: dict[str, str] = field(default_factory=dict)


def _ref(variant: str, row_code: str, row_name: str, report_type: str, evidence: str) -> ReportRowRef:
    return ReportRowRef(
        row_code=row_code,
        row_name=row_name,
        report_type=report_type,
        quadrants=ROW_CODE_QUADRANTS[variant],
        evidence=evidence,
    )


def _detail_reason(section: str, ref: ReportRowRef, main_table: str) -> str:
    return (
        f"本表是「{section}」子节的分类/明细/续表维度，非该科目的汇总主表；"
        f"report_config 实证 {ref.row_code}「{ref.row_name}」（{ref.report_type}，"
        f"象限 {'/'.join(ref.quadrants)}）已由主表「{main_table}」唯一承载 —— "
        "同一子节两张表填同一 row_code 会让下游取数双算，故留 None。"
    )


#: 母公司章 `report_row_code` 目标态。键 = 子节标题（与 JSON `section_title` 逐字一致）。
PARENT_ROW_CODE_PLAN: dict[str, dict[str, RowCodePlan]] = {
    "listed": {
        "应收票据": RowCodePlan(
            ref=(
                _r := _ref(
                    "listed",
                    "BS-005",
                    "应收票据",
                    "balance_sheet",
                    "report_config 实证：BS-005 在 listed_standalone / listed_consolidated "
                    "的 row_name 均为「应收票据」，与子节名逐字相等；且「应收票据」这个 "
                    "row_name 在每个象限内只有 BS-005 一个码（GROUP BY 实测 n=1）。",
                )
            ),
            main_table="应收票据",
            section_reason=_detail_reason("应收票据", _r, "应收票据"),
        ),
        "应收账款": RowCodePlan(
            ref=_ref(
                "listed",
                "BS-006",
                "应收账款",
                "balance_sheet",
                "report_config 实证：BS-006 在两个 listed 象限的 row_name 均为「应收账款」。"
                "但本子节无汇总主表 ⇒ 已对账仍不填（见 section_reason）。",
            ),
            main_table=None,
            section_reason=(
                "report_config 实证 BS-006 在两个 listed 象限 row_name 均为「应收账款」，"
                "但本子节（Task 6 已与合并章 五、5 同构）**无「应收账款」汇总主表** —— "
                "全部 17 张表都是账龄 / 坏账计提方法 / 组合计提 / 核销 / 前五名 / 金融资产转移 "
                "等分类维度，无一张唯一对应该报表行；任填一张都会让下游把某一维度当整行取数，"
                "故按宁缺勿造全部留 None。"
            ),
        ),
        "其他应收款": RowCodePlan(
            ref=(
                _r := _ref(
                    "listed",
                    "BS-009",
                    "其他应收款",
                    "balance_sheet",
                    "report_config 实证：BS-009 在两个 listed 象限 row_name 均为「其他应收款」，"
                    "与子节名逐字相等；主表「其他应收款」的行集（应收利息 / 应收股利 / "
                    "其他应收款 / 合计）正是该报表行的合并列示口径。",
                )
            ),
            main_table="其他应收款",
            section_reason=_detail_reason("其他应收款", _r, "其他应收款"),
        ),
        "长期股权投资": RowCodePlan(
            ref=(
                _r := _ref(
                    "listed",
                    "BS-024",
                    "长期股权投资",
                    "balance_sheet",
                    "report_config 实证：BS-024 在两个 listed 象限 row_name 均为「长期股权投资」，"
                    "与子节名逐字相等；主表（源 docx 7 列两级、行 = 对子公司 / 对合营 / 对联营 / "
                    "合计）唯一对应该报表行。",
                )
            ),
            main_table="长期股权投资",
            section_reason=_detail_reason("长期股权投资", _r, "长期股权投资"),
        ),
        "营业收入与营业成本": RowCodePlan(
            ref=None,
            main_table=None,
            section_reason=(
                "report_config 实证：该子节的科目对应**两个**报表行 —— IS-001「一、营业收入」"
                "与 IS-002「减：营业成本」（income_statement，两个 listed 象限逐条一致），"
                "且全库不存在 row_name 为「营业收入」或「营业成本」（不带序号/「减：」）的行 ⇒ "
                "任一张表都无法唯一对应单一 row_code，按宁缺勿造全部留 None。"
            ),
            table_reasons={
                "营业收入和营业成本": (
                    "report_config 实证：本表同时承载 IS-001「一、营业收入」与 IS-002"
                    "「减：营业成本」两个报表行（表头「收入 / 成本」双列组即两行口径），"
                    "表级只能挂一个 row_code ⇒ 填任一个都会让另一个口径失落，故留 None。"
                ),
            },
        ),
        "投资收益": RowCodePlan(
            ref=_ref(
                "listed",
                "IS-011",
                "投资收益",
                "income_statement",
                "report_config 实证：IS-011 在两个 listed 象限 row_name 均为「投资收益」，"
                "与子节名逐字相等；该子节仅 1 张同名表，唯一对应。",
            ),
            main_table="投资收益",
            section_reason=(
                "占位：listed/投资收益 子节只有 1 张表且已填 IS-011，本理由不应被解析到；"
                "若被解析到说明该子节新增了表且未登记理由（report_config 实证口径需重新裁决）。"
            ),
        ),
    },
    "soe": {
        "应收账款": RowCodePlan(
            ref=_ref(
                "soe",
                "BS-006",
                "应收账款",
                "balance_sheet",
                "report_config 实证：BS-006 在 soe_standalone / soe_consolidated 的 row_name "
                "均为「应收账款」。但本子节无汇总主表 ⇒ 已对账仍不填（见 section_reason）。",
            ),
            main_table=None,
            section_reason=(
                "report_config 实证 BS-006 在两个 soe 象限 row_name 均为「应收账款」，"
                "但本子节（Task 6 已与合并章 八、5 同构）**无「应收账款」汇总主表** —— "
                "全部 13 张表都是账龄 / 坏账计提方法 / 组合计提 / 核销 / 前五名 / 金融资产转移 "
                "等分类维度，无一张唯一对应该报表行，故按宁缺勿造全部留 None。"
            ),
        ),
        "其他应收款": RowCodePlan(
            ref=(
                _r := _ref(
                    "soe",
                    "BS-009",
                    "其他应收款",
                    "balance_sheet",
                    "report_config 实证：BS-009 在两个 soe 象限 row_name 均为「其他应收款」，"
                    "与子节名逐字相等；主表行集（应收利息 / 应收股利 / 其他应收款项 / 合计）"
                    "即该报表行的合并列示口径。soe 侧另有 BS-016「其中：应收股利」——"
                    "它是「其中：」明细行不是独立报表行，故表级仍取 BS-009。",
                )
            ),
            main_table="其他应收款",
            section_reason=_detail_reason("其他应收款", _r, "其他应收款"),
        ),
        "长期股权投资": RowCodePlan(
            ref=(
                _r := _ref(
                    "soe",
                    "BS-024",
                    "长期股权投资",
                    "balance_sheet",
                    "report_config 实证：BS-024 在两个 soe 象限 row_name 均为「长期股权投资」，"
                    "与子节名逐字相等；主表（源 docx 5 列、行 = 对子公司 / 对合营 / 对联营 / "
                    "小计 / 减：减值准备 / 合计）唯一对应该报表行。",
                )
            ),
            main_table="长期股权投资",
            section_reason=_detail_reason("长期股权投资", _r, "长期股权投资"),
        ),
        "营业收入与营业成本": RowCodePlan(
            ref=None,
            main_table=None,
            section_reason=(
                "report_config 实证：该子节的科目对应**两个**报表行 —— IS-001「一、营业收入」"
                "与 IS-002「减：营业成本」（income_statement，两个 soe 象限逐条一致），"
                "任一张表都无法唯一对应单一 row_code，按宁缺勿造全部留 None。"
            ),
            table_reasons={
                "营业收入、营业成本": (
                    "report_config 实证：本表同时承载 IS-001「一、营业收入」与 IS-002"
                    "「减：营业成本」两个报表行，表级只能挂一个 row_code ⇒ 留 None。"
                ),
            },
        ),
        "投资收益": RowCodePlan(
            ref=_ref(
                "soe",
                "IS-011",
                "投资收益",
                "income_statement",
                "report_config 实证：IS-011 在两个 soe 象限 row_name 均为「投资收益」，"
                "与子节名逐字相等；该子节仅 1 张同名表，唯一对应。",
            ),
            main_table="投资收益",
            section_reason=(
                "占位：soe/投资收益 子节只有 1 张表且已填 IS-011，本理由不应被解析到；"
                "若被解析到说明该子节新增了表且未登记理由（report_config 实证口径需重新裁决）。"
            ),
        ),
        "现金流量表补充资料": RowCodePlan(
            ref=None,
            main_table=None,
            section_reason=(
                "report_config 实证：本表是**整张报表**而非单一报表行 —— 它对应 "
                "report_type=cash_flow_supplement（soe 两象限各 30 行），表的 30 行与 "
                "CFSS-001「1.将净利润调节为经营活动现金流量：」/ CFSS-002「净利润」/ "
                "CFSS-003「加：资产减值损失」/ CFSS-004「信用减值损失」逐行对应；"
                "不存在能代表整表的单一 row_code，故留 None。"
            ),
        ),
    },
}

del _r  # 上面用海象表达式复用 ref 构造 detail 理由，避免把中间名留在模块命名空间


def iter_parent_tables(doc: dict[str, Any], variant: str) -> list[tuple[str, str, dict[str, Any]]]:
    """母公司章全部表：``(子节标题, 表名, 表对象)``。供守卫做覆盖面自检。"""
    out: list[tuple[str, str, dict[str, Any]]] = []
    for kid in _parent_children(doc.get("sections") or [], variant):
        title = str(kid.get("section_title") or "")
        for tbl in kid.get("tables") or []:
            out.append((title, str(tbl.get("name") or ""), tbl))
    return out


def report_row_code_target(variant: str, section_title: str, table_name: str) -> str | None:
    """该表应填的 `report_row_code`（``None`` = 留空）。"""
    plan = PARENT_ROW_CODE_PLAN.get(variant, {}).get(section_title)
    if plan is None or plan.ref is None or plan.main_table is None:
        return None
    return plan.ref.row_code if table_name == plan.main_table else None


def report_row_code_reason(variant: str, section_title: str, table_name: str) -> str:
    """该表留 None 的理由（已填表返回空串）。"""
    plan = PARENT_ROW_CODE_PLAN.get(variant, {}).get(section_title)
    if plan is None:
        return ""
    if plan.main_table is not None and table_name == plan.main_table:
        return ""
    return plan.table_reasons.get(table_name) or plan.section_reason


def check_reason_quality(reason: str) -> list[str]:
    """理由质量闸：非空白 + 长度下限 + 至少一个实证标记。"""
    text = (reason or "").strip()
    if not text:
        return ["理由为空白（= 未登记）"]
    errs: list[str] = []
    if len(text) < ROW_CODE_REASON_MIN_LEN:
        errs.append(f"理由过短（{len(text)} < {ROW_CODE_REASON_MIN_LEN} 字），须写明实证依据")
    if not any(m in text for m in ROW_CODE_EVIDENCE_MARKERS):
        errs.append(f"理由缺实证标记（须含 {ROW_CODE_EVIDENCE_MARKERS} 之一）")
    return errs


def check_row_name_selfcheck() -> list[str]:
    """归一化的反向自检：错位必须仍判不符，行业标记/空白差异必须判相符。

    需求「名称比对的归一化只许去空白 + 去行业适用性标记」的可执行形式。
    """
    errs: list[str] = []
    if is_row_name_comparable("其他应收款", "货币资金"):
        errs.append("反向自检失败：把「其他应收款」落在「货币资金」行上被判成相符")
    if is_row_name_comparable("长期股权投资", "长期应收款"):
        errs.append("反向自检失败：「长期股权投资」与「长期应收款」被判成相符")
    if is_row_name_comparable("投资收益", "一、营业收入"):
        errs.append("反向自检失败：「投资收益」与「一、营业收入」被判成相符")
    if not is_row_name_comparable("应收 票据", "△应收票据"):
        errs.append("正向自检失败：空白与行业适用性标记 △ 的差异应判相符")
    if is_row_name_comparable("", ""):
        errs.append("反向自检失败：空串被判成可比对")
    return errs


def apply_report_row_codes(doc: dict[str, Any], variant: str) -> tuple[list[str], list[str]]:
    """Task 11：按 `PARENT_ROW_CODE_PLAN` 写入表级 `report_row_code`（留空 = 不写该键）。

    **必须排在 `apply_columns` 之后** —— 目标态按**表名**索引，先写会落到尚未正名的旧名上。
    """
    changes: list[str] = []
    warnings: list[str] = []
    kids = {
        str(k.get("section_title") or ""): k
        for k in _parent_children(doc.get("sections") or [], variant)
    }
    plan_map = PARENT_ROW_CODE_PLAN.get(variant) or {}

    for title, plan in plan_map.items():
        kid = kids.get(title)
        if kid is None:
            warnings.append(f"{variant} 母公司章缺子节「{title}」→ 跳过 Task 11 该子节")
            continue
        tables = kid.get("tables") or []
        names = [str(t.get("name") or "") for t in tables]
        if plan.main_table is not None and names.count(plan.main_table) != 1:
            warnings.append(
                f"{variant}/{title} 主表「{plan.main_table}」在该子节命中 "
                f"{names.count(plan.main_table)} 次（应为 1）→ 跳过（宁缺勿造）"
            )
            continue
        for tbl in tables:
            name = str(tbl.get("name") or "")
            want = report_row_code_target(variant, title, name)
            cur = tbl.get("report_row_code")
            if want is None:
                if "report_row_code" in tbl:
                    tbl.pop("report_row_code", None)
                    changes.append(
                        f"{variant}/{title} 表「{name}」.report_row_code：{cur!r} → 移除"
                        "（本表按登记理由留 None）"
                    )
                continue
            if cur != want:
                ref = plan.ref
                assert ref is not None  # want 非 None ⇒ ref 必非 None（check 侧亦断言）
                tbl["report_row_code"] = want
                changes.append(
                    f"{variant}/{title} 表「{name}」.report_row_code：{cur!r} → {want!r}"
                    f"（report_config {ref.report_type} row_name=「{ref.row_name}」，"
                    f"象限 {'/'.join(ref.quadrants)}）"
                )
    return changes, warnings


def check_report_row_codes(doc: dict[str, Any], variant: str) -> list[str]:
    """Task 11 的 ``--check`` 欠账清单（Property 21 的结构侧；DB 侧由守卫连库断言）。

    覆盖 8 类判据：登记表自洽 / 覆盖面 / 主表存在唯一 / 已填值正确 / 未填表无残留 /
    子节内 row_code 唯一 / 变体内 row_code 唯一 / 每张未填表有合格理由。
    """
    errs: list[str] = []
    errs += [f"{variant} 行名归一化 {e}" for e in check_row_name_selfcheck()]

    plan_map = PARENT_ROW_CODE_PLAN.get(variant) or {}
    if not plan_map:
        return errs + [f"{variant} PARENT_ROW_CODE_PLAN 为空（常量被误删？）"]

    kids = {
        str(k.get("section_title") or ""): k
        for k in _parent_children(doc.get("sections") or [], variant)
    }

    # 覆盖面：JSON 子节集合 == 登记表键集合（新增子节漏登记必红）
    missing = sorted(set(plan_map) - set(kids))
    extra = sorted(set(kids) - set(plan_map))
    if missing:
        errs.append(f"{variant} 登记表声明的子节在 JSON 中不存在：{missing}")
    if extra:
        errs.append(
            f"{variant} 母公司章子节未登记 report_row_code 目标态：{extra}"
            "（新增子节必须显式表态填码或留 None + 理由）"
        )

    filled: list[tuple[str, str, str]] = []  # (子节, 表名, row_code)
    for title, plan in plan_map.items():
        # 登记表自洽：ref 与 main_table 的表态必须一致
        if plan.main_table is not None and plan.ref is None:
            errs.append(f"{variant}/{title} 声明了主表却无 report_config 对账依据（ref=None）")
        if plan.ref is not None:
            for e in check_reason_quality(plan.ref.evidence):
                errs.append(f"{variant}/{title} ref.evidence {e}")
            if not plan.ref.quadrants:
                errs.append(f"{variant}/{title} ref.quadrants 为空（未声明对账象限）")
            for q in plan.ref.quadrants:
                if not q.startswith(f"{variant}_"):
                    errs.append(
                        f"{variant}/{title} ref.quadrants 含跨主体象限 {q!r}"
                        "（一码两义：listed 侧只许查 listed_*，soe 侧只许查 soe_*）"
                    )
            if plan.main_table is not None and not is_row_name_comparable(
                title, plan.ref.row_name
            ):
                errs.append(
                    f"{variant}/{title} 子节名与 {plan.ref.row_code} 的 row_name"
                    f"「{plan.ref.row_name}」归一后不相等 ⇒ 不得填码"
                )

        kid = kids.get(title)
        if kid is None:
            continue
        tables = kid.get("tables") or []
        names = [str(t.get("name") or "") for t in tables]
        if plan.main_table is not None and names.count(plan.main_table) != 1:
            errs.append(
                f"{variant}/{title} 主表「{plan.main_table}」在该子节命中 "
                f"{names.count(plan.main_table)} 次（应为 1）"
            )

        for tbl in tables:
            name = str(tbl.get("name") or "")
            want = report_row_code_target(variant, title, name)
            cur = tbl.get("report_row_code")
            if want is not None:
                if cur != want:
                    errs.append(
                        f"{variant}/{title} 主表「{name}」.report_row_code={cur!r}，"
                        f"应为 {want!r}（report_config 实证对账值）"
                    )
                else:
                    filled.append((title, name, want))
                continue
            if cur is not None:
                errs.append(
                    f"{variant}/{title} 表「{name}」按登记理由应留 None，实为 {cur!r}"
                )
            for e in check_reason_quality(report_row_code_reason(variant, title, name)):
                errs.append(f"{variant}/{title} 表「{name}」留 None 的{e}")

    # 同一子节内 row_code 唯一（下游取数双算红线）
    by_section: dict[tuple[str, str], list[str]] = {}
    for title, name, code in filled:
        by_section.setdefault((title, code), []).append(name)
    for (title, code), tbls in by_section.items():
        if len(tbls) > 1:
            errs.append(
                f"{variant}/{title} 内 {len(tbls)} 张表填了同一 row_code {code}：{tbls}"
                "（下游取数会双算）"
            )
    # 同一变体内 row_code 唯一（一个报表行不得被两个子节认领）
    by_variant: dict[str, list[str]] = {}
    for title, name, code in filled:
        by_variant.setdefault(code, []).append(f"{title}/{name}")
    for code, where in by_variant.items():
        if len(where) > 1:
            errs.append(f"{variant} row_code {code} 被 {len(where)} 张表认领：{where}")
    return errs


# ─────────────────────────── 写盘与 CLI ───────────────────────────

def _dump(doc: dict[str, Any]) -> str:
    """与两份模板 JSON 现有序列化形态逐字一致（实测 indent=2 + 尾换行 round-trip 相等）。"""
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def _detect_newline(raw: bytes) -> bytes:
    """探测原文主导行尾。空文件 / 无行尾的退化情形取默认 ``LF``。

    判据 = ``b"\\r\\n"`` 计数 vs **纯** ``b"\\n"`` 计数（后者 = 总 LF 数 − CRLF 数），
    两者相等时取 CRLF（Windows 工作树的常态）。
    """
    crlf = raw.count(b"\r\n")
    lone_lf = raw.count(b"\n") - crlf
    if crlf == 0 and lone_lf == 0:
        return b"\n"
    return b"\r\n" if crlf >= lone_lf else b"\n"


def _write(path: Path, payload: str) -> None:
    """``write_bytes`` 落盘，并**显式沿用原文行尾**（探测 → 转换 → 写字节）。

    ``_dump()`` 恒产出 LF 字符串；本函数按原文主导行尾把它转成目标字节，
    于是三个目标同时成立：

    1. **落盘字节完全由代码决定** ⇒ 「连续两次 ``--apply`` 逐字节一致」可判、
       ``md5`` 基线不失效（``write_text`` 下读回的字节比写出去的多 N 个 ``\\r``，
       哈希基线天然对不上）；
    2. **工作树行尾与其余文件一致**（不改 ``.gitattributes``，避免影响他人 checkout）；
    3. 规避 ``write_text`` 的隐式转换 —— 问题不是结果错，而是**结果取决于平台**：
       同一份脚本在 CI/Linux 上落 LF、本机落 CRLF ⇒ 字节级判据不可移植。

    🔴 **CRLF 是 checkout 状态，与本 spec 的改动无关**（2026-08-06 实证三条）：

    - 本仓库 ``core.autocrlf=true``，``.gitattributes`` 只给 ``*.sh`` 钉了 ``eol=lf``、
      **不覆盖 ``*.json``** ⇒ ``git ls-files --eol`` 对两份模板 JSON 报 ``i/lf w/crlf``，
      即 index 侧 LF、工作树侧 CRLF 本来如此；
    - 故 Task 3 那次 ``--apply``（当时走 ``write_text``）**没有污染行尾**，
      ``note_template_listed.json`` 至今 git-clean 且仍是 34392 个 CRLF 即旁证；
    - ``Path.read_text()`` 走 universal-newlines 会把 CRLF 读成 ``\\n``，这正是
      round-trip 自检 ``_dump(json.loads(raw)) == raw`` 能在 CRLF 工作树上成立的原因
      —— 该自检比对的是**归一后**的文本，不涉及行尾。
    """
    original = path.read_bytes() if path.exists() else b""
    newline = _detect_newline(original)
    data = payload.encode("utf-8")
    # 自检：_dump() 必须只产出 LF，否则下面的 replace 会造出 \r\r\n
    if b"\r" in data:
        print("[ERR] _dump() 产出了 CR，行尾转换会造成 \\r\\r\\n，拒绝写盘")
        raise SystemExit(2)
    if newline != b"\n":
        data = data.replace(b"\n", newline)
    path.write_bytes(data)


def process(variant: str, dry_run: bool, check: bool) -> tuple[list[str], list[str], list[str]]:
    """处理单个变体。返回 ``(changes, warnings, errs)``。

    🔴 **执行顺序即依赖顺序**：Task 3（章标识）→ Task 4（表名唯一化）→ Task 5（长期股权
    投资两级表头）→ Task 6/7。正名必须早于补 ``columns``/``guidance``，因为列规则按表名
    索引，先补列会落到旧名上。

    Task 7 的 ``apply_columns`` 依赖 Task 4 的正名（列规则按子节标题取目标态、
    ``COLUMNS_TARGET_NAMES`` 按目标表名断言）；``apply_chapter_intro`` 与其余步骤无依赖，
    放在最后只为让「结构 → 文字」的顺序与 docstring 一致。
    """
    path = TEMPLATE_PATH[variant]
    raw = path.read_text(encoding="utf-8")
    doc = json.loads(raw)

    def _checks(d: dict[str, Any]) -> list[str]:
        return (
            check_chapter_identity(d, variant)
            + check_table_renames(d, variant)
            + check_lte_tables(d, variant)
            + check_isomorphic(d, variant)
            + check_columns(d, variant)
            + check_chapter_intro(d, variant)
            + check_report_row_codes(d, variant)
        )

    if check:
        return [], [], _checks(doc)

    changes, warnings = apply_chapter_identity(doc, variant)
    # Task 4：正名（须在补列之前 —— 列规则按表名索引）
    rn_changes, rn_warnings = apply_table_renames(doc, variant)
    changes += rn_changes
    warnings += rn_warnings
    # Task 5：长期股权投资两级表头还原
    lte_changes, lte_warnings = apply_lte_tables(doc, variant)
    changes += lte_changes
    warnings += lte_warnings
    # Task 6：同构子节按合并章整体替换 tables（须在 Task 4/5 之后 —— 它只碰同构子节，
    # 与自有表子节无交集；放这里是为了让「正名 → 还原 → 替换」的顺序与 docstring 一致）
    iso_changes, iso_warnings = apply_isomorphic(doc, variant)
    changes += iso_changes
    warnings += iso_warnings
    # Task 7：自有表子节补 columns/guidance（须在 Task 4 正名之后 —— 列规则按表名索引）
    col_changes, col_warnings = apply_columns(doc, variant)
    changes += col_changes
    warnings += col_warnings
    # Task 7：soe 章首说明补进 text_sections（listed 侧源 docx 无章首说明 ⇒ 空操作）
    intro_changes, intro_warnings = apply_chapter_intro(doc, variant)
    changes += intro_changes
    warnings += intro_warnings
    # Task 11：表级 report_row_code 实证对账（须在 Task 4 正名与 Task 7 补列**之后** ——
    # 目标态按表名索引；补列不改表名，故与它无先后硬约束，但顺序按 tasks.md 明确要求）
    rc_changes, rc_warnings = apply_report_row_codes(doc, variant)
    changes += rc_changes
    warnings += rc_warnings
    errs = _checks(doc)

    if changes and not dry_run and not errs:
        # round-trip 自检：仅当「未改动时能逐字复现原文」才敢写盘（防全文件重排 / 覆盖并发改动）
        if _dump(json.loads(raw)) != raw:
            print(
                "[ERR] round-trip 自检失败：json.dumps 无法逐字复现原文，"
                f"拒绝写入 {path.name}（防全文件重排）"
            )
            raise SystemExit(2)
        chapter = _find_parent_chapter(doc.get("sections") or [], variant)
        if chapter is not None:
            stamp(chapter, ALIGNED_BY)  # kit 的 stamp 作用于 section，不是整个 doc
        _write(path, _dump(doc))
    return changes, warnings, errs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__ and __doc__.splitlines()[0])
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--apply", action="store_true", help="写入文件")
    grp.add_argument("--check", action="store_true", help="只校验欠账，非零表示有欠账")
    ap.add_argument("--dry-run", action="store_true", help="只打印变更（默认行为）")
    ap.add_argument("--only", choices=sorted(TEMPLATE_PATH), help="只处理单个变体")
    args = ap.parse_args()

    dry_run = not args.apply  # --dry-run 默认
    keys = [args.only] if args.only else list(TEMPLATE_PATH)
    total_changes = 0
    total_errs = 0
    total_warns = 0
    for key in keys:
        changes, warnings, errs = process(key, dry_run, args.check)
        print(f"\n=== {LABELS[key]} ===")
        for c in changes:
            print(f"  ~ {c}")
        for w in warnings:
            print(f"  ! {w}")
        for e in errs:
            print(f"  x {e}")
        if not changes and not errs and not warnings:
            print("  = 已对齐（幂等空操作）")
        total_changes += len(changes)
        total_errs += len(errs)
        total_warns += len(warnings)

    if args.check:
        print(f"\n--check：{total_errs} 项欠账")
        return 1 if total_errs else 0
    print(
        f"\n{'[dry-run] ' if dry_run else '[apply] '}共 {total_changes} 处变更，"
        f"{total_errs} 项欠账，{total_warns} 项告警"
    )
    return 1 if total_errs else 0


if __name__ == "__main__":
    raise SystemExit(main())
