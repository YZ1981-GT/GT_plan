#!/usr/bin/env python
"""G7 列结构三向对齐诊断（只读）—— 边① 源 xlsx <-> 模板 seed。

背景
----
G7 的列结构有三个真源：源 xlsx / 模板 seed（``note_template_*.json``）/ 运行时载荷
（``buildG7{Listed,Soe}Columns()``）。现有守卫只锁住两条边，源 xlsx <-> 运行时这条边
从未有过判据（见 spec design.md 的三角图）。

本脚本负责两件事：

1. ``read_source_facts()`` —— openpyxl 直读两张披露 sheet，按 ``ws.merged_cells.ranges``
   判两级表头（**横向合并（跨度>=2）= 父表头**），产出
   ``{(variant, noteSectionId, tableName): TableFacts}``。
2. ``build_alignment_report()`` —— 六维比对 seed 与源 xlsx，输出 ``AlignmentDeviation``
   列表，并按成因打 A~E 分类标签。

3. ``run_self_checks()`` —— 对两条已裁决口径做**可执行的反向自检**（动态列段数 /
   同名必误合并 / 豁免表仍单槽 / 豁免登记表完整性），任一不成立 ``--check`` 即 exit 2。

报告分两节：**计入偏差**与**豁免登记**。后者是 ``SOURCE_PLACEHOLDER_SINGLE_SLOT``
登记的 4 张合营表（源模板 merge 结构暗示 3 槽、叶子只填 1 槽 ⇒ 平台按单槽 flat 实现），
其 ``flat`` / ``group`` 偏差**不计入偏差数**但必须如实打印。

``--emit-facts`` 把 (1) 的结果落盘成 ``backend/data/g7_column_source_facts.json``，
供前端三向守卫（Task 3）作「源 xlsx 端」使用。该 JSON 是**派生投影、不是真源**，
由 ``backend/tests/four_table/test_g7_column_source_facts.py`` 钉死「与实时 openpyxl
读取逐字相等」。

只读性
------
本脚本**只读**：不提供 ``--apply``、不连数据库、不改写 ``note_template_*.json``。
唯一允许的写盘是 ``--emit-facts`` 写上述派生投影 JSON。

索引键
------
🔴 索引键必须是 ``(variant, noteSectionId, tableName)`` 三元组。实测模板侧跨章节同名表
listed 63 个表名出现 >1 次、soe 40 个（``长期股权投资`` 出现 3 次），按表名全局索引会
匹配到会计政策章的空壳版并产出假结论（建档核实轮已复现一次）。

Usage::

    python backend/scripts/diagnose/diagnose_g7_column_alignment.py --dry-run
    python backend/scripts/diagnose/diagnose_g7_column_alignment.py --check
    python backend/scripts/diagnose/diagnose_g7_column_alignment.py --emit-facts

spec: .kiro/specs/g7-column-alignment-and-extraction-closure/ (Task 1)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import openpyxl

# backend/scripts/diagnose/x.py -> file.parents[2] == backend/ ; parents[3] == 仓库根
# 🔴 注意 _HERE 已是 .parent（= diagnose/），故从它数要少一级：
#    _HERE.parents[1] == backend/ ; _HERE.parents[2] == 仓库根
_HERE = Path(__file__).resolve().parent
_BACKEND = _HERE.parents[1]
_REPO_ROOT = _HERE.parents[2]

SRC_XLSX = _BACKEND / "wp_templates" / "G" / "G7 长期股权投资.xlsx"
TEMPLATE_PATHS = {
    "listed": _BACKEND / "data" / "note_template_listed.json",
    "soe": _BACKEND / "data" / "note_template_soe.json",
}
FACTS_PATH = _BACKEND / "data" / "g7_column_source_facts.json"

SHEETS = {
    "listed": "附注披露信息（上市公司）",
    "soe": "附注披露信息（国企）",
}

# ─────────────────────────── 表区域注册表 ───────────────────────────
# (variant, noteSectionId, tableName, header_row_start, header_row_end)
#
# 章节号取 note_template_*.json 的 `section_number` 原值 —— soe 的 `七、…` 是 md 截断值
# （10 字符），属既有真源形态，**不得补全**。
# 表头行区间取自四个既有幂等脚本 docstring 里登记的源模板区间，并已用 openpyxl 逐区复核。
# 右边界不写死：由「叶子表头最后一个非空列」自动判定（源模板有大量空白横向合并作排版留白，
# 写死列数会把留白算成数据列）。

_Region = tuple[str, str, str, int, int]

REGIONS: tuple[_Region, ...] = (
    # ── listed 五、18（源 A8:M23）──
    ("listed", "五、18", "长期股权投资", 8, 11),
    # ── listed 七、1（源 A26:M243，14 张表）──
    ("listed", "七、1", "企业集团的构成", 28, 29),
    ("listed", "七、1", "重要的非全资子公司", 49, 49),
    ("listed", "七、1", "重要非全资子公司主要财务信息—期末数", 58, 59),
    ("listed", "七、1", "续（1）", 66, 67),
    ("listed", "七、1", "续（2）", 74, 75),
    ("listed", "七、1", "未丧失控制权的所有者权益份额变动影响", 96, 96),
    ("listed", "七、1", "重要的合营企业或联营企业", 111, 112),
    ("listed", "七、1", "重要合营企业主要财务信息", 132, 133),
    ("listed", "七、1", "续：重要合营企业本期及上期经营成果", 153, 154),
    ("listed", "七、1", "重要联营企业主要财务信息", 169, 170),
    ("listed", "七、1", "续：重要联营企业本期及上期经营成果", 189, 190),
    ("listed", "七、1", "其他不重要合营企业和联营企业的汇总财务信息", 200, 200),
    ("listed", "七、1", "对合营企业或联营企业发生超额亏损的分担额", 221, 221),
    ("listed", "七、1", "重要的共同经营", 235, 236),
    # ── soe 七、…（13 节，其中 2 节纯文本无表格）──
    ("soe", "七、本期纳入合并报表", "本期纳入合并报表范围的子公司基本情况", 9, 9),
    ("soe", "七、母公司拥有被投资",
     "母公司拥有被投资单位表决权不足半数但能对被投资单位形成控制的原因", 25, 25),
    ("soe", "七、母公司直接或通过",
     "母公司直接或通过其他子公司间接拥有被投资单位半数以上的表决权但未能对其形成控制的原因",
     37, 37),
    ("soe", "七、重要非全资子公司", "少数股东", 55, 55),
    ("soe", "七、重要非全资子公司", "主要财务信息", 62, 63),
    ("soe", "七、本期不再纳入合并", "原子公司的基本情况", 78, 78),
    ("soe", "七、本期不再纳入合并", "本期出售的子公司出售日的财务状况", 87, 88),
    ("soe", "七、本期不再纳入合并", "本期出售的子公司出售日的经营成果", 98, 99),
    ("soe", "七、本期新纳入合并范", "本期新纳入合并范围的主体", 109, 109),
    ("soe", "七、本期发生的同一控", "本期发生的同一控制下企业合并情况", 122, 123),
    ("soe", "七、本期发生的非同一", "本期发生的非同一控制下企业合并情况", 129, 131),
    ("soe", "七、本期发生的吸收合", "本期发生的吸收合并", 139, 140),
    ("soe", "七、母公司在子公司的", "母公司在子公司的所有者权益份额发生变化的情况", 187, 187),
    # ── soe 八、18（10 张表）──
    ("soe", "八、18", "长期股权投资分类", 202, 202),
    ("soe", "八、18", "长期股权投资明细", 210, 211),
    ("soe", "八、18", "重要合营企业的主要财务信息（划分为持有待售的除外）", 229, 230),
    ("soe", "八、18", "续：重要合营企业本期及上期经营成果", 243, 244),
    ("soe", "八、18", "重要联营企业的主要财务信息", 257, 258),
    ("soe", "八、18", "续：重要联营企业本期及上期经营成果", 271, 272),
    ("soe", "八、18", "不重要合营企业和联营企业的汇总信息", 280, 280),
    ("soe", "八、18", "②对合营企业或联营企业发生超额亏损的分担额", 301, 301),
    ("soe", "八、18", "结构化主体权益的账面价值和最大损失敞口", 323, 324),
    ("soe", "八、18", "结构化主体获得收益及转移资产情况", 340, 341),
)

_MAX_SCAN_COL = 24  # 两张 sheet 的 max_col 分别是 13 / 17，24 足够且不会误吞

# 平台标签列 key 惯例：266 个标签列定义里 241 个（91%）用 'label'，跨 70 文件。
LABEL_KEY_CONVENTION = "label"

# ── 动态列父表头占位 ──────────────────────────────────────────────
# 源模板把「被投资单位名称」留空由审计师填（如 B169:C169 空合并 + 下行 期末数/期初数），
# 运行时按 {slot}_{seq} 动态生成父表头名。比对 group 时对该占位**只校验跨度不校验名字**
# —— 名字来自项目实际数据，源 xlsx 无从裁决。
#
# 🔴 占位名必须**按锚列区分身份**（`<DYNAMIC:c2>` / `<DYNAMIC:c4>`），不能所有占位共用
# 一个 `<DYNAMIC>`：`_compress_groups` 按「相邻且同名则合并」压运行段，同名会把
# 「3 个实体槽 × 2 子列」的三个独立合并（B169:C169 / D169:E169 / F169:G169）压成
# 1 个跨 6，与 seed 正确声明的 3 段不匹配 —— 那是**探针缺陷产出的假偏差**。
# 反向自检 `_sc_uniform_dynamic_would_merge()` 钉死该结论，防日后被「优化」回同名。
DYNAMIC_GROUP_PREFIX = "<DYNAMIC:"
DYNAMIC_GROUP_UNIFORM = "<DYNAMIC>"  # 朴素同名形态，**仅**用于反向自检


def dynamic_group_name(anchor_col: int) -> str:
    """按锚列生成带身份的动态占位名（anchor_col 为 1-based xlsx 列号）。"""
    return f"{DYNAMIC_GROUP_PREFIX}c{anchor_col}>"


def is_dynamic_group(name: str | None) -> bool:
    return bool(name) and str(name).startswith(DYNAMIC_GROUP_PREFIX)


DeviationKind = Literal[
    "table_missing", "seed_no_cols", "is_label", "flat", "group", "group_label",
    "key_label_col", "key_data_col", "label", "count",
]

# 偏差 -> 成因分类（A~E 见 requirements.md 的「偏差台账」表）
#
# 🔴 `group` 与 `group_label` 必须分家：
#   * `group`       = **结构性**丢 group / 段数或跨度不符 ⇒ A 类（附注列结构错）
#   * `group_label` = 段数与 (start, span) 完全一致、**只有父表头文字不符** ⇒ D 类
#     （如 `重要的共同经营` seed 写「持股比例或享有的份额(%)」而源 E235 是
#     「持股比例/享有的份额(%)」，斜杠不是「或」）
# 这样 A 类只保留真正的结构性缺陷。
KIND_TO_CLASS: dict[str, str] = {
    "group": "A",
    "flat": "A",
    "key_label_col": "B",
    "key_data_col": "C",
    "label": "D",
    "group_label": "D",
    "count": "E",
    "is_label": "-",
    "table_missing": "-",
    "seed_no_cols": "-",
}

CLASS_DESC = {
    "A": "结构性丢 group / 两级表头被压扁",
    "B": "标签列 key 分叉（应统一到平台惯例 'label'）",
    "C": "数据列 key 命名分叉（本脚本不可判，归 Task 3）",
    "D": "文字不符源 xlsx（列 label 或 group 名）",
    "E": "列数不一致",
    "-": "结构性（无 A~E 分类）",
}


@dataclass(frozen=True)
class AlignmentDeviation:
    """一个偏差点。

    ``runtime`` 侧本脚本恒为空串 —— 运行时列由 ``buildG7*Columns()`` 动态生成，
    是 TypeScript 侧的事实，归前端三向守卫（Task 3，边②③）。

    ``exempt`` 非空 = 已登记豁免（源模板占位形态，见
    ``SOURCE_PLACEHOLDER_SINGLE_SLOT``）⇒ **不计入偏差数**，但报告单列一节如实打印。
    """

    variant: str
    section: str
    table: str
    kind: str
    seed: str
    runtime: str
    source: str
    exempt: str = ""

    @property
    def cls(self) -> str:
        return KIND_TO_CLASS.get(self.kind, "-")

    @property
    def counted(self) -> bool:
        return not self.exempt


# ─────────────────── 豁免登记：源模板占位形态（单槽） ───────────────────
#
# 4 张合营表源侧确有 `B132:C132` 这类**空白跨 2 合并**，但**同表的 D/E、F/G（soe 为
# E/F、G/H）合并其叶子行为空** ⇒ 源模板自身只填了 1 个实体槽，与联营表填满 3 槽
# **不同构**。裁决为「源模板占位形态，登记豁免、不重构」。
#
# 🔴 这不是「待修」而是「已裁决豁免」：报告必须单列一节如实打印
#    「源模板 merge 结构暗示 3 槽、叶子只填 1 槽 —— 平台按单槽 flat 实现」。
# 🔴 配 stale 检测：某天源 xlsx 把 D/E、F/G 的叶子填上了，`expected_source_runs`
#    断言即打红，提醒重新裁决（见 `_sc_single_slot_still_single()`）。
# 🔴 条目数上限 4 且**只许缩短**（`_EXEMPTION_CAP`），防它变成逃逸阀。


@dataclass(frozen=True)
class SingleSlotExemption:
    variant: str
    section: str
    table: str
    source_ref: str
    source_text: str
    basis: tuple[str, ...]
    platform_intent: str
    expected_source_runs: int = 1
    exempt_kinds: frozenset[str] = frozenset({"flat", "group"})

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.variant, self.section, self.table)


_BASIS_COMMON: tuple[str, ...] = (
    "源侧 D/E、F/G（soe 为 E/F、G/H）合并的叶子行为空 ⇒ 源模板只填了 1 个实体槽",
    "seed 与运行时**两侧独立**都判 flat + 2 数据列（两个独立实现结论一致）",
    "改成动态多实体属**结构性变更**，超出本 spec R1 明列的 6 张 A 类表",
    "父表头是**实体名**、源 xlsx 留空 ⇒ 无从裁决，改了就是臆造（违「宁缺勿造」）",
)

SOURCE_PLACEHOLDER_SINGLE_SLOT: tuple[SingleSlotExemption, ...] = (
    SingleSlotExemption(
        variant="listed", section="七、1", table="重要合营企业主要财务信息",
        source_ref="A132:C133",
        source_text="A132:A133='项 目'；B132:C132 空白合并；B133='期末数' C133='期初数'；"
                    "D132:E132 与 F132:G132 亦为空白合并但 D133~G133 全空",
        basis=_BASIS_COMMON,
        platform_intent="按单槽 flat 实现：标签列「项目」+ 期末数 / 期初数 两个数据列，不声明 group",
    ),
    SingleSlotExemption(
        variant="listed", section="七、1", table="续：重要合营企业本期及上期经营成果",
        source_ref="A153:C154",
        source_text="A153:A154='项  目'；B153:C153 空白合并；B154='本期发生额' C154='上期发生额'；"
                    "D153:E153 与 F153:G153 亦为空白合并但 D154~G154 全空",
        basis=_BASIS_COMMON,
        platform_intent="按单槽 flat 实现：标签列「项目」+ 本期发生额 / 上期发生额 两个数据列，不声明 group",
    ),
    SingleSlotExemption(
        variant="soe", section="八、18",
        table="重要合营企业的主要财务信息（划分为持有待售的除外）",
        source_ref="A229:D230",
        source_text="A229:B230='项 目'（标签列跨 2 xlsx 列）；C229:D229 空白合并；"
                    "C230='期末数' D230='期初数'；E229:F229 与 G229:H229 亦为空白合并但 E230~H230 全空",
        basis=_BASIS_COMMON,
        platform_intent="按单槽 flat 实现：标签列「项目」+ 期末数 / 期初数 两个数据列，不声明 group",
    ),
    SingleSlotExemption(
        variant="soe", section="八、18", table="续：重要合营企业本期及上期经营成果",
        source_ref="A243:D244",
        source_text="A243:B244='项  目'（标签列跨 2 xlsx 列）；C243:D243 空白合并；"
                    "C244='本期发生额' D244='上期发生额'；E243:F243 与 G243:H243 亦为空白合并但 E244~H244 全空",
        basis=_BASIS_COMMON,
        platform_intent="按单槽 flat 实现：标签列「项目」+ 本期发生额 / 上期发生额 两个数据列，不声明 group",
    ),
)

# 上限只许下调：`len(...) <= _EXEMPTION_CAP` 拦不住把 CAP 改大，故另存天花板常量。
_EXEMPTION_CAP = 4
_EXEMPTION_CAP_CEILING = 4

EXEMPTION_INDEX: dict[tuple[str, str, str], SingleSlotExemption] = {
    e.key: e for e in SOURCE_PLACEHOLDER_SINGLE_SLOT
}

# ───────── 豁免登记 2：平台结构约束导致的必要偏离（源文无法逐字照抄） ─────────
#
# 平台 `ColumnDef.group` **只支持单级**：`/` 是 `note_sub_table_projector`
# `_extract_column_groups` 的**层级分隔符**（L336 `g.split("/")` → 走树形分支返
# `{group, children}`），而前端 `activeTableColumns` 只认扁平 `{group, start, span}`
# ⇒ group 含 `/` 会**渲染崩**。该约束由平台守卫强制（`_note_structure_kit.validate_section`
# 的「group 含 '/'」检查 + `test_note_d1/d2_structure.test_group_is_single_level` +
# `test_note_d_cycle_rest_structure.test_validator_rejects_group_with_slash`）。
#
# ⇒ 源 xlsx 用了 `/` 或**三级**表头时，逐字照抄会触发平台约束 ⇒ 必须做等价改写。
#   这是**已裁决的必要偏离**、不是待修偏差。
#
# 🔴 与登记表 1 的区别：登记表 1 的成因在**源模板自身**（只填 1 槽），本表成因在
#   **平台渲染约束**（源模板没错、平台不支持）。两表**键互斥**（自检钉死）。
# 🔴 stale 检测：源文一旦不再含 `/`（或三级表头被拍平），`expected_source_text`
#   断言即打红 ⇒ 提醒移出登记而不是继续豁免。
# 🔴 条目数上限 2 且只许缩短（另存天花板常量）。


@dataclass(frozen=True)
class PlatformConstraintExemption:
    """平台结构约束导致的必要偏离登记项。

    ``expected_source_text`` 是**源 xlsx 该处的原文**（stale 检测锚点）；
    ``seed_text`` 是平台实现值。两者不等是**预期**，等了反而说明源模板变了。
    """

    variant: str
    section: str
    table: str
    kind: str                    # 被豁免的偏差维度
    source_ref: str
    expected_source_text: str    # 源 xlsx 原文（不等即 stale）
    seed_text: str               # 平台实现值
    constraint: str              # 触发的平台约束
    basis: tuple[str, ...]
    platform_intent: str
    # 🔴 `label` 偏差是**逐列**产出的：不带列下标就等于整表豁免，会把同表其他列的真偏差
    #    一起放过。故 kind == 'label' 时**必须**列出被豁免的数据列下标（0-based，
    #    与 `data_defs` 对齐）；kind 为表级维度（group_label / flat / group）时留空。
    col_indexes: frozenset[int] = frozenset()

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.variant, self.section, self.table)


_SLASH_CONSTRAINT = (
    "group 只支持单级：'/' 是 note_sub_table_projector._extract_column_groups 的层级"
    "分隔符（g.split('/') → 树形 {group,children}），前端 activeTableColumns 只认扁平"
    " {group,start,span} ⇒ 含 '/' 会渲染崩"
)

PLATFORM_CONSTRAINT_EXEMPTIONS: tuple[PlatformConstraintExemption, ...] = (
    PlatformConstraintExemption(
        variant="listed", section="七、1", table="重要的共同经营",
        kind="group_label",
        source_ref="E235（父表头，跨 E:F 两列）",
        expected_source_text="持股比例/享有的份额(%)",
        seed_text="持股比例或享有的份额(%)",
        constraint=_SLASH_CONSTRAINT,
        basis=(
            "源文 E235='持股比例/享有的份额(%)' 含 '/'，逐字照抄会被平台判为多级 group",
            "平台守卫强制单级：_note_structure_kit.validate_section 报「group 含 '/'」；"
            "test_note_d1/d2_structure.test_group_is_single_level 逐表断言；"
            "test_note_d_cycle_rest_structure.test_validator_rejects_group_with_slash 钉死",
            "段数与 (start, span) 与源侧完全一致（1 段 @ start=3 span=2）⇒ 仅名字改写，结构无损",
            "'/' 在此是「或」的意思（持股比例 或 享有的份额），改写为「或」语义等价、不臆造",
        ),
        platform_intent="group 名改写为等价无斜杠表述「持股比例或享有的份额(%)」，段结构逐字保持",
    ),
    PlatformConstraintExemption(
        variant="soe", section="七、本期发生的非同一",
        table="本期发生的非同一控制下企业合并情况",
        kind="label",
        source_ref="F129:H129 / F130:F131+G130:H130 / G131+H131（三级表头）",
        expected_source_text=(
            "可辨认净资产公允价值总额金额 | 可辨认净资产公允价值总额确定方法"
            "（源为三级：F129:H129='购买日被购买方' → G130:H130='可辨认净资产公允价值总额'"
            " → G131='金额' H131='确定方法'）"
        ),
        seed_text=(
            "可辨认净资产公允价值总额（金额） | 可辨认净资产公允价值总额（确定方法）"
        ),
        constraint=_SLASH_CONSTRAINT,
        basis=(
            "源 xlsx 该表是**三级**表头（level_count=3）：一级 '购买日被购买方'、"
            "二级 '可辨认净资产公允价值总额'、三级 '金额'/'确定方法'",
            "平台 group 只支持单级 ⇒ 三级无法表达；一级已用作 group，二级必须并入叶子列名",
            "并入时用全角括号「（金额）」「（确定方法）」区分二三级，保持人可读且不丢信息",
            "本脚本 _leaf_parts 直接拼接三级文字得到无括号形态，故与 seed 不等是**判据侧的"
            "拼接口径差异**，不是 seed 写错 —— 两者所指的源单元格完全相同",
        ),
        platform_intent=(
            "三级表头压成「二级（三级）」的叶子列名，一级保留为 group='购买日被购买方'"
        ),
        # 源 columns 的第 5、6 项（0-based）= 金额 / 确定方法；只豁免这两列
        col_indexes=frozenset({5, 6}),
    ),
)

_PLATFORM_EXEMPTION_CAP = 2
_PLATFORM_EXEMPTION_CAP_CEILING = 2

# ───────── 登记 3：源模板「转角标题」—— 标签列无列名，探针拼接会产出幻影表头 ─────────
#
# 实测（`_leaf_parts` 逐表扫标签列）：38 张表里标签列**非纵向合并**（两个表头行各有
# 独立文字）的只有 3 张。其中两类语义完全不同：
#
#   (a) **纵向拆分列名**（真拼接）—— soe `结构化主体获得收益及转移资产情况`
#       A340='结构化主体' + A341='类型'，数据行是 `信用资产证券化`/`投资基金`
#       ⇒ 拼成 `结构化主体类型` 读作一个名词短语，**拼接正确**，不进本登记。
#
#   (b) **转角标题**（phantom）—— soe 两张「出售日」表：
#       A87='公司名称' 标注的是**行 87 本身**（该行放 `公司1`/`公司2` 等公司名），
#       A88='截止日期' 标注的是**行 88 本身**（该行放 `出售日`/`期初余额`）。
#       两者都在描述**表头行**，而非行标识列。数据行是 `流动资产`/`长期股权投资`/…
#       与 `营业收入`/`营业成本`/… ⇒ 行标识列的真实语义是**「项目」**，源 xlsx
#       **根本没给它列名**。探针把两个转角标题拼成 `公司名称截止日期` 是**幻影**。
#
# 🔴 (a) 与 (b) **无干净结构判据可区分**（两者都是「group 行 + leaf 行」、标签列两行
#   各有文字）—— 区分靠语义。故按登记 + stale 检测处理，不硬编码进比对逻辑。
# 🔴 本登记**同时下发给前端**（facts JSON 的 `label_header_kind`），否则前端三向守卫会
#   对同一个幻影再报一次 `labelHeaderText` 偏差 —— 一处登记、两端消费。
# 🔴 条目数上限 2 且只许缩短（另存天花板常量）。


@dataclass(frozen=True)
class CornerTitleExemption:
    """源模板转角标题登记项（标签列无列名 ⇒ 行标识语义为「项目」）。"""

    variant: str
    section: str
    table: str
    source_ref: str
    expected_parts: tuple[str, ...]      # 源侧标签列两行原文（stale 锚点）
    expected_data_rows: tuple[str, ...]  # 源侧前两个数据行（证明行语义是「项目」）
    row_titled: tuple[str, ...]          # 每个转角标题实际标注的那一行的内容样例
    seed_label: str                      # 平台实现值
    basis: tuple[str, ...]
    platform_intent: str

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.variant, self.section, self.table)


_CORNER_BASIS_COMMON: tuple[str, ...] = (
    "两个转角标题各自标注**表头行**而非行标识列：上行放公司名、下行放日期/期间",
    "源 xlsx 对行标识列**根本没给列名** ⇒ 拼接两个转角标题得到的是幻影，不是真表头",
    "数据行语义实测为报表「项目」（资产/负债/权益科目、收入/成本/利润项）"
    " ⇒ seed 的 '项目' 是正确的行标识列名",
    "38 张表里标签列非纵向合并的仅 3 张，另 1 张（结构化主体获得收益）是**真**纵向"
    "拆分列名并已正确拼接 ⇒ 本形态是可枚举的少数例外，不是判据普遍失效",
)

CORNER_TITLE_EXEMPTIONS: tuple[CornerTitleExemption, ...] = (
    CornerTitleExemption(
        variant="soe", section="七、本期不再纳入合并",
        table="本期出售的子公司出售日的财务状况",
        source_ref="A87:B87='公司名称' / A88:B88='截止日期'（各自横向合并 A:B，无纵向合并）",
        expected_parts=("公司名称", "截止日期"),
        expected_data_rows=("流动资产", "长期股权投资"),
        row_titled=("行87 放 公司1 / 公司2", "行88 放 出售日 / 期初余额"),
        seed_label="项目",
        basis=_CORNER_BASIS_COMMON,
        platform_intent="标签列 label 取「项目」（源 xlsx 未给行标识列名，按数据行语义定）",
    ),
    CornerTitleExemption(
        variant="soe", section="七、本期不再纳入合并",
        table="本期出售的子公司出售日的经营成果",
        source_ref="A98:B98='公司名称' / A99:B99='期间'（各自横向合并 A:B，无纵向合并）",
        expected_parts=("公司名称", "期间"),
        expected_data_rows=("营业收入", "营业成本"),
        row_titled=("行98 放 A公司~E公司", "行99 放 本年年初-出售日 / 上年发生额"),
        seed_label="项目",
        basis=_CORNER_BASIS_COMMON,
        platform_intent="标签列 label 取「项目」（源 xlsx 未给行标识列名，按数据行语义定）",
    ),
)

_CORNER_CAP = 2
_CORNER_CAP_CEILING = 2

CORNER_TITLE_INDEX: dict[tuple[str, str, str], CornerTitleExemption] = {
    e.key: e for e in CORNER_TITLE_EXEMPTIONS
}

# 一张表可能有多条不同 kind 的平台约束豁免 ⇒ 索引为**列表**，不是单值。
PLATFORM_EXEMPTION_INDEX: dict[tuple[str, str, str], list[PlatformConstraintExemption]] = {}
for _pex in PLATFORM_CONSTRAINT_EXEMPTIONS:
    PLATFORM_EXEMPTION_INDEX.setdefault(_pex.key, []).append(_pex)

# ─────────────── 动态列表登记（裁决 1 的反向自检对象） ───────────────
# 源模板填满多个实体槽的动态列矩阵：源侧 group 运行段数必须等于 seed 侧段数。
# value = 期望段数（= 实体槽数）
DYNAMIC_MATRIX_EXPECTED_RUNS: dict[tuple[str, str, str], int] = {
    ("listed", "七、1", "重要联营企业主要财务信息"): 3,
    ("listed", "七、1", "续：重要联营企业本期及上期经营成果"): 3,
    ("soe", "七、重要非全资子公司", "主要财务信息"): 5,
    ("soe", "八、18", "重要联营企业的主要财务信息"): 3,
    ("soe", "八、18", "续：重要联营企业本期及上期经营成果"): 3,
}


# ─────────────────────────── openpyxl 读取 ───────────────────────────


def _norm(text: Any) -> str:
    """归一化表头文字：只去空白（含换行/全角空格），**保留全半角括号差异**。

    Requirement 4 明确要求「全半角括号按源 xlsx 原文，禁统一」，故不可在此折叠括号。
    """
    if text is None:
        return ""
    return re.sub(r"[\s\u3000]+", "", str(text))


def _build_merge_index(ws) -> dict[tuple[int, int], tuple[int, int, int, int, int, int]]:
    """(row, col) -> (anchor_row, anchor_col, min_row, max_row, min_col, max_col)。"""
    index: dict[tuple[int, int], tuple[int, int, int, int, int, int]] = {}
    for rng in ws.merged_cells.ranges:
        info = (
            rng.min_row, rng.min_col,
            rng.min_row, rng.max_row, rng.min_col, rng.max_col,
        )
        for r in range(rng.min_row, rng.max_row + 1):
            for c in range(rng.min_col, rng.max_col + 1):
                index[(r, c)] = info
    return index


def _cell(ws, merges, row: int, col: int) -> str:
    """取单元格文字，落在合并区内时取锚点值。"""
    hit = merges.get((row, col))
    if hit:
        row, col = hit[0], hit[1]
    return _norm(ws.cell(row, col).value)


def _cell_raw(ws, merges, row: int, col: int) -> str:
    """取单元格文字的**原文**（只 strip 首尾，保留内部空格）。

    🔴 为什么必须与 :func:`_cell` 并存：``_cell`` 用 :func:`_norm` 去掉**全部**空白，
    这对「列 label 逐字比对」是必要的（源模板叶子表头常用 ``认缴持股\\n比例（%）`` 这类
    换行排版，平台铁律要求模板 headers 是纯文本、不含换行 ⇒ 归一化后比对才是对的），
    但它同时让**标签列头的内部空格差异结构上不可见**：

    * 源 xlsx 标签列头实测三种写法 —— ``项  目``（双空格 13 张）/ ``项 目``（单空格 3 张）
      / ``项目``（无空格 1 张）；
    * seed 侧 ``headers[0]`` 逐字保留了原文（``项  目``）；
    * 运行时侧一律写 ``项目``。

    三者不一致，但因 ``_norm('项  目') == _norm('项目')``，边① 与边③ 的 label 维度
    **恒判相等** ⇒ 该偏差长期逃逸（由 Task 12 契约扩容时 helper 的 P5 抓到：
    P5 直接比 ``columns[label] 与 seed headers[0]`` 原文，不经 ``_norm``）。

    故本函数只服务于 ``label_header_raw`` 这个 additive 字段，**不改任何既有判据**。
    """
    hit = merges.get((row, col))
    if hit:
        row, col = hit[0], hit[1]
    val = ws.cell(row, col).value
    return "" if val is None else str(val).strip()


def _label_span(merges, r0: int, r1: int) -> int:
    """标签列占几个 xlsx 列 —— 由「起始于第 1 列的横向合并」判定（如 A62:B63）。"""
    span = 1
    for r in range(r0, r1 + 1):
        hit = merges.get((r, 1))
        if hit and hit[4] == 1 and hit[5] > span:
            span = hit[5]
    return span


def _leaf_parts(ws, merges, row_range: range, col: int) -> list[str]:
    """该列在若干表头行上的文字序列（相邻重复去重 —— 纵向合并会让同值重复出现）。"""
    parts: list[str] = []
    for r in row_range:
        val = _cell(ws, merges, r, col)
        if val and (not parts or parts[-1] != val):
            parts.append(val)
    return parts


def _leaf_parts_raw(ws, merges, row_range: range, col: int) -> list[str]:
    """同 :func:`_leaf_parts`，但取**原文**（保留内部空格）。

    去重判据仍按归一化值比（否则 ``项  目`` 与 ``项 目`` 会被当成两段拼成
    ``项  目项 目``）。只用于 ``label_header_raw``，见 :func:`_cell_raw` 的说明。
    """
    parts: list[str] = []
    seen_norm: str | None = None
    for r in row_range:
        raw = _cell_raw(ws, merges, r, col)
        if not _norm(raw):
            continue
        if seen_norm is not None and _norm(raw) == seen_norm:
            continue
        parts.append(raw)
        seen_norm = _norm(raw)
    return parts


def _is_group_row(ws, r0: int, r1: int, label_span: int, row: int) -> bool:
    """该表头行是否为**分组行** —— 行内存在起始于标签列右侧、跨度>=2 的横向合并。"""
    for rng in ws.merged_cells.ranges:
        if rng.min_row != rng.max_row or rng.min_row != row:
            continue
        if rng.min_col <= label_span:
            continue
        if rng.max_col - rng.min_col + 1 >= 2:
            return True
    return False


def _hspan_at(ws, row: int, col: int) -> tuple[int, int]:
    """(row, col) 所在横向合并的列区间；不在合并区则为自身单列。"""
    for rng in ws.merged_cells.ranges:
        if rng.min_row <= row <= rng.max_row and rng.min_col <= col <= rng.max_col:
            return rng.min_col, rng.max_col
    return col, col


def _is_rowspan(ws, row: int, col: int) -> bool:
    """(row, col) 是否纵向合并到下一行 —— 纵向合并 = 叶子列本身，不是父表头。"""
    for rng in ws.merged_cells.ranges:
        if rng.min_row <= row <= rng.max_row and rng.min_col <= col <= rng.max_col:
            return rng.max_row > row
    return False


def _group_rows(
    ws, merges, r0: int, r1: int, label_span: int, last_col: int
) -> dict[tuple[int, int], tuple[str, int, int, int]]:
    """收集父表头，返回 {(row, min_col): (name, min_col, max_col, row)}。

    判据（三条同时成立）：
      1. 所在行是**分组行**（行内有起始于标签列右侧、跨度>=2 的横向合并）；
      2. 该单元格**不是纵向合并**（纵向合并跨到下一表头行 ⇒ 它是叶子列自身，rowspan=2）；
      3. 单元格在标签列右侧。

    两条与「只认跨度>=2 的非空横向合并」不同的关键处：

    * **跨度为 1 的分组单元格同样计入** —— 源模板 `B323='发起'` / `B324='规模'`
      是「父表头 发起 + 叶子 规模」形态（B323 无纵向合并），若不计入会把它读成
      单列 `发起规模` 并与 seed 的 `group='发起'` 产出假偏差。
    * **值为空的横向合并 = 动态列占位**（源模板留给审计师填被投资单位名，
      如 `B169:C169` 空 + 下行 `期末数/期初数`），记 name=`dynamic_group_name(锚列)`，
      比对时只校验**跨度**不校验名字 —— 这是 R10 已登记的源模板形态，
      按「排版留白」丢弃会让 5 张动态列表产出假的 flat/group 偏差。
      🔴 占位名**按锚列区分身份**，否则 `_compress_groups` 会跨合并边界把
      「3 个跨 2」压成「1 个跨 6」（详见 `DYNAMIC_GROUP_PREFIX` 的注释）。
    """
    found: dict[tuple[int, int], tuple[str, int, int, int]] = {}
    for row in range(r0, r1):  # 最后一行表头必为叶子层，不可能是分组行
        if not _is_group_row(ws, r0, r1, label_span, row):
            continue
        col = label_span + 1
        while col <= last_col:
            lo, hi = _hspan_at(ws, row, col)
            lo = max(lo, label_span + 1)
            if _is_rowspan(ws, row, col):
                col = hi + 1
                continue
            name = _cell(ws, merges, row, col) or (
                dynamic_group_name(lo) if hi > lo else ""
            )
            if name:
                found[(row, lo)] = (name, lo, hi, row)
            col = hi + 1
    return found


def _read_table(ws, merges, region: _Region) -> dict[str, Any]:
    _variant, _section, _table, r0, r1 = region
    header_rows = range(r0, r1 + 1)
    label_span = _label_span(merges, r0, r1)

    # 右边界：叶子表头最后一个非空列（跳过排版留白的空白合并）
    last_col = label_span
    for c in range(label_span + 1, _MAX_SCAN_COL + 1):
        if _leaf_parts(ws, merges, header_rows, c):
            last_col = c

    groups_raw = _group_rows(ws, merges, r0, r1, label_span, last_col)
    # 每列的「最外层」父表头（表头行号最小者）；三级表头的内层折进叶子 label
    col_group: dict[int, tuple[str, int]] = {}
    for name, min_col, max_col, row in groups_raw.values():
        for c in range(min_col, max_col + 1):
            prev = col_group.get(c)
            if prev is None or row < prev[1]:
                col_group[c] = (name, row)

    columns: list[dict[str, Any]] = []
    for c in range(label_span + 1, last_col + 1):
        grp = col_group.get(c)
        skip_row = grp[1] if grp else None
        parts = _leaf_parts(
            ws, merges,
            range(r0, r1 + 1) if skip_row is None else
            (r for r in range(r0, r1 + 1) if r != skip_row),  # type: ignore[arg-type]
            c,
        )
        columns.append({
            "label": "".join(parts),
            "group": grp[0] if grp else None,
            "xlsx_col": c,
        })

    label_parts = _leaf_parts(ws, merges, header_rows, 1)
    label_parts_raw = _leaf_parts_raw(ws, merges, header_rows, 1)
    level_count = 1 + len({row for _n, _a, _b, row in groups_raw.values()})

    return {
        "label_header": "".join(label_parts),
        "label_header_parts": label_parts,
        # 🔴 原文版（保留内部空格）—— 归一化版看不见 `项  目` vs `项目` 的差异，
        # 而模板 seed 的 `headers[0]` 保留原文空格 ⇒ 运行时 labelHeader 若写归一化值，
        # 契约守卫 P5（labelHeader ↔ seed headers[0]）会打红，而边①/边③ 全绿。
        "label_header_raw": "".join(label_parts_raw),
        "label_header_parts_raw": label_parts_raw,
        "label_xlsx_span": label_span,
        "columns": [{"label": c["label"], "group": c["group"]} for c in columns],
        "is_two_level": bool(groups_raw),
        "level_count": level_count,
        "source_rows": f"{_col_letter(1)}{r0}:{_col_letter(last_col)}{r1}",
    }


def _col_letter(col: int) -> str:
    letters = ""
    while col > 0:
        col, rem = divmod(col - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def read_source_facts() -> dict[tuple[str, str, str], dict[str, Any]]:
    """openpyxl 直读两张披露 sheet，产出 {(variant, section, table): TableFacts}。"""
    if not SRC_XLSX.exists():
        raise FileNotFoundError(f"源模板缺失：{SRC_XLSX}")
    wb = openpyxl.load_workbook(SRC_XLSX, data_only=True)
    cache: dict[str, tuple[Any, dict]] = {}
    facts: dict[tuple[str, str, str], dict[str, Any]] = {}
    for region in REGIONS:
        variant = region[0]
        if variant not in cache:
            ws = wb[SHEETS[variant]]
            cache[variant] = (ws, _build_merge_index(ws))
        ws, merges = cache[variant]
        facts[(variant, region[1], region[2])] = _read_table(ws, merges, region)
    wb.close()
    return facts


# ─────────────────────────── seed 读取 ───────────────────────────


def load_seed_facts() -> dict[tuple[str, str, str], dict[str, Any]]:
    """读 note_template_{listed,soe}.json，按 (variant, section_number, table_name) 索引。

    只收本 spec 四个作用域的章节（listed 五、18 / 七、1；soe 八、18 与全部 七、…），
    避免把会计政策章 / 母公司章的同名空壳表匹配进来。
    """
    wanted_sections = {
        "listed": {"五、18", "七、1"},
        "soe": {"八、18"},
    }
    out: dict[tuple[str, str, str], dict[str, Any]] = {}
    for variant, path in TEMPLATE_PATHS.items():
        doc = json.loads(path.read_text(encoding="utf-8"))
        for sec in doc.get("sections") or []:
            num = str(sec.get("section_number") or "")
            in_scope = num in wanted_sections[variant] or (
                variant == "soe" and num.startswith("七、")
            )
            if not in_scope:
                continue
            for tbl in sec.get("tables") or []:
                name = tbl.get("name")
                if not name:
                    continue
                cols = tbl.get("columns") or []
                out[(variant, num, name)] = {
                    "headers": tbl.get("headers") or [],
                    "columns": [
                        {
                            "key": c.get("key"),
                            "label": c.get("label"),
                            "group": c.get("group"),
                            "flat": bool(c.get("flat")),
                            "is_label": bool(c.get("is_label")),
                        }
                        for c in cols
                    ],
                }
    return out


def _groups_structure_match(
    seed_groups: list[tuple[str, int, int]],
    src_groups: list[tuple[str, int, int]],
) -> bool:
    """只比**结构**：段数与每段 (start, span)。名字不参与。"""
    if len(seed_groups) != len(src_groups):
        return False
    return all(
        (s[1], s[2]) == (r[1], r[2])
        for s, r in zip(seed_groups, src_groups)
    )


def _groups_match(
    seed_groups: list[tuple[str, int, int]],
    src_groups: list[tuple[str, int, int]],
) -> bool:
    """比对分组运行段（结构 + 名字）。

    源侧 group 名为动态占位（``is_dynamic_group``）时**只校验 (start, span) 不校验名字**
    —— 那是源模板留空给审计师填被投资单位名称的动态列占位（R10 已登记的源模板形态），
    seed 侧写 `公司1`/`联营企业1` 这类占位名是正确的，不是偏差。
    """
    if not _groups_structure_match(seed_groups, src_groups):
        return False
    for (s_name, _ss, _sp), (r_name, _rs, _rp) in zip(seed_groups, src_groups):
        if is_dynamic_group(r_name):
            continue  # 动态列：名字由项目数据决定，不参与裁决
        if s_name != r_name:
            return False
    return True


def _compress_groups(cols: list[dict[str, Any]]) -> list[tuple[str, int, int]]:
    """把逐列 group 压成 (group, start, span) 运行段；start 为数据列 0-based 下标。

    🔴 合并条件是「相邻 **且同名**」—— 故动态列占位必须带锚列身份，否则跨合并边界误并。
    """
    runs: list[tuple[str, int, int]] = []
    for i, c in enumerate(cols):
        grp = c.get("group")
        if not grp:
            continue
        if runs and runs[-1][0] == grp and runs[-1][1] + runs[-1][2] == i:
            name, start, span = runs[-1]
            runs[-1] = (name, start, span + 1)
        else:
            runs.append((grp, i, 1))
    return runs


def _uniformize_dynamic(cols: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把所有动态占位改成**同名**的朴素形态 —— 仅供反向自检使用。"""
    return [
        {**c, "group": DYNAMIC_GROUP_UNIFORM if is_dynamic_group(c.get("group")) else c.get("group")}
        for c in cols
    ]


# ─────────────────────────── 六维比对 ───────────────────────────


def build_alignment_report() -> list[AlignmentDeviation]:
    """六维比对 seed 与源 xlsx。

    六维 = is_label / flat / group（同名同跨度）/ 标签列 key / 数据列 key / label 文字 / 列数。
    其中 **数据列 key 源 xlsx 无从裁决**（xlsx 只有列头文字、没有数据键），故本脚本不产出
    ``key_data_col`` 偏差 —— 该维归前端三向守卫（Task 3）比对 seed 与运行时。
    """
    source = read_source_facts()
    seed = load_seed_facts()
    devs: list[AlignmentDeviation] = []

    def _exempt_for(
        k: tuple[str, str, str], kind: str, *, col_index: int | None = None
    ) -> str:
        """查两张登记表；``col_index`` 非 None 时 label 豁免须**逐列精确匹配**。

        🔴 label 偏差是**逐列**产出的，若按 (key, kind) 整表豁免会把同表其他列的真偏差
        一起放过 —— 故 `PlatformConstraintExemption.col_indexes` 必须参与匹配。
        """
        ex = EXEMPTION_INDEX.get(k)
        if ex is not None and kind in ex.exempt_kinds:
            return f"源模板占位形态（单槽），登记豁免 @ {ex.source_ref}"
        for pex in PLATFORM_EXEMPTION_INDEX.get(k, ()):
            if kind != pex.kind:
                continue
            if pex.col_indexes and (col_index is None or col_index not in pex.col_indexes):
                continue
            return f"平台结构约束必要偏离（{pex.constraint}），登记豁免 @ {pex.source_ref}"
        # 登记 3 只豁免**标签列**的 label 偏差（`col_index is None` 即标签列那一支）
        cex = CORNER_TITLE_INDEX.get(k)
        if cex is not None and kind == "label" and col_index is None:
            return f"源模板转角标题（标签列无列名），登记豁免 @ {cex.source_ref}"
        return ""

    for key in sorted(source, key=lambda k: (k[0], k[1], k[2])):
        variant, section, table = key
        src = source[key]
        sd = seed.get(key)
        if sd is None:
            devs.append(AlignmentDeviation(
                variant, section, table, "table_missing",
                seed="<缺失>", runtime="", source=src["source_rows"],
            ))
            continue
        seed_cols = sd["columns"]
        if not seed_cols:
            devs.append(AlignmentDeviation(
                variant, section, table, "seed_no_cols",
                seed="columns=[]", runtime="", source=f"{len(src['columns'])} 数据列",
            ))
            continue

        label_defs = [c for c in seed_cols if c["is_label"]]
        data_defs = [c for c in seed_cols if not c["is_label"]]

        # 维 1：is_label —— 必须恰好一个标签列（投影器靠它跳过标签列算 group 索引）
        if len(label_defs) != 1:
            devs.append(AlignmentDeviation(
                variant, section, table, "is_label",
                seed=f"is_label 列数={len(label_defs)}", runtime="",
                source="恰好 1 个（源 xlsx 首列为行标识列）",
            ))
            # 无唯一标签列时，后续按「首列为标签列」继续比对
            if not label_defs:
                label_defs = seed_cols[:1]
                data_defs = seed_cols[1:]

        # 维 4：标签列 key（平台惯例）
        lab = label_defs[0]
        if lab["key"] != LABEL_KEY_CONVENTION:
            devs.append(AlignmentDeviation(
                variant, section, table, "key_label_col",
                seed=repr(lab["key"]), runtime="",
                source=f"平台惯例 {LABEL_KEY_CONVENTION!r}（241/266，91%）",
            ))

        # 维 7：列数
        if len(data_defs) != len(src["columns"]):
            devs.append(AlignmentDeviation(
                variant, section, table, "count",
                seed=f"{len(data_defs)} 数据列", runtime="",
                source=f"{len(src['columns'])} 数据列 @ {src['source_rows']}",
            ))

        # 维 2：flat 表态
        seed_flat = any(c["flat"] for c in seed_cols)
        if src["is_two_level"] and seed_flat:
            devs.append(AlignmentDeviation(
                variant, section, table, "flat",
                seed="声明 flat", runtime="",
                source=f"两级表头（{src['level_count']} 级）@ {src['source_rows']}",
                exempt=_exempt_for(key, "flat"),
            ))
        if not src["is_two_level"] and not seed_flat:
            devs.append(AlignmentDeviation(
                variant, section, table, "flat",
                seed="未声明 flat", runtime="",
                source=f"单级表头 @ {src['source_rows']}",
                exempt=_exempt_for(key, "flat"),
            ))

        # 维 3：group 同名同跨度（动态列父表头只比跨度 —— 名字来自项目数据）
        # 结构一致而只有父表头文字不符 ⇒ 归 `group_label`（D 类），使 A 类只剩结构性缺陷。
        seed_groups = _compress_groups(data_defs)
        src_groups = _compress_groups(src["columns"])
        if not _groups_match(seed_groups, src_groups):
            kind = "group_label" if _groups_structure_match(seed_groups, src_groups) else "group"
            devs.append(AlignmentDeviation(
                variant, section, table, kind,
                seed=repr(seed_groups), runtime="", source=repr(src_groups),
                exempt=_exempt_for(key, kind),
            ))

        # 维 6：label 文字逐字（去空白归一后比对；标签列容忍「多行表头拼接/取其一」）
        lab_ok = _norm(lab["label"]) in {
            _norm(src["label_header"]), *[_norm(p) for p in src["label_header_parts"]]
        }
        if not lab_ok:
            # `col_index=None` = 标签列那一支 ⇒ 由登记 3（转角标题）判豁免
            devs.append(AlignmentDeviation(
                variant, section, table, "label",
                seed=f"[标签列] {lab['label']!r}", runtime="",
                source=f"{src['label_header']!r} parts={src['label_header_parts']}",
                exempt=_exempt_for(key, "label", col_index=None),
            ))
        for i, (sd_c, sr_c) in enumerate(zip(data_defs, src["columns"])):
            if _norm(sd_c["label"]) != _norm(sr_c["label"]):
                devs.append(AlignmentDeviation(
                    variant, section, table, "label",
                    seed=f"[col{i}] {sd_c['label']!r}", runtime="",
                    source=repr(sr_c["label"]),
                    exempt=_exempt_for(key, "label", col_index=i),
                ))

    return devs


# ─────────────────────────── 反向自检 ───────────────────────────
#
# 判据本身可能有缺陷（建档核实轮已实测到一次：动态占位同名让 3 段被压成 1 段，产出
# 假偏差）。故对两条裁决各配可执行自检，任一不成立即 `--check` exit 2。


@dataclass(frozen=True)
class SelfCheck:
    name: str
    ok: bool
    detail: str


def _sc_dynamic_matrix_runs(
    facts: dict[tuple[str, str, str], dict[str, Any]],
    seed: dict[tuple[str, str, str], dict[str, Any]],
) -> list[SelfCheck]:
    """裁决 1 正向自检：5 张动态列表的**源侧段数 == seed 侧段数 == 期望实体槽数**。"""
    out: list[SelfCheck] = []
    for key, expected in DYNAMIC_MATRIX_EXPECTED_RUNS.items():
        src = facts.get(key)
        sd = seed.get(key)
        if src is None or sd is None:
            out.append(SelfCheck(
                f"动态列段数 {key[0]}/{key[1]}/{key[2]}", False,
                f"登记表 stale：源事实={src is not None} seed={sd is not None}",
            ))
            continue
        src_runs = _compress_groups(src["columns"])
        seed_runs = _compress_groups([c for c in sd["columns"] if not c["is_label"]])
        ok = len(src_runs) == len(seed_runs) == expected
        out.append(SelfCheck(
            f"动态列段数 {key[0]}/{key[1]}/{key[2]}", ok,
            f"期望={expected} 源侧={len(src_runs)} seed侧={len(seed_runs)}"
            + ("" if ok else f"  src={src_runs!r}  seed={seed_runs!r}"),
        ))
    return out


def _sc_uniform_dynamic_would_merge(
    facts: dict[tuple[str, str, str], dict[str, Any]],
) -> list[SelfCheck]:
    """裁决 1 反向自检：把动态占位改成**同名**后必被 `_compress_groups` 误合并成 1 段。

    这条证明「按锚列区分动态占位身份」是**必要**的，防日后被「优化」回同名。
    """
    out: list[SelfCheck] = []
    for key, expected in DYNAMIC_MATRIX_EXPECTED_RUNS.items():
        src = facts.get(key)
        if src is None:
            out.append(SelfCheck(f"同名必误合并 {key[2]}", False, "登记表 stale：源事实缺失"))
            continue
        real = _compress_groups(src["columns"])
        naive = _compress_groups(_uniformize_dynamic(src["columns"]))
        total_span = sum(r[2] for r in real)
        ok = len(real) == expected and len(naive) == 1 and naive[0][2] == total_span
        out.append(SelfCheck(
            f"同名必误合并 {key[2]}", ok,
            f"按锚列={len(real)} 段 / 朴素同名={len(naive)} 段"
            + (f"（跨 {naive[0][2]}）" if naive else "")
            + ("" if ok else f"  real={real!r} naive={naive!r}"),
        ))
    return out


def _sc_single_slot_still_single(
    facts: dict[tuple[str, str, str], dict[str, Any]],
) -> list[SelfCheck]:
    """裁决 2 stale 检测：4 张豁免表的源侧 group 段数必须仍为 1。

    某天源 xlsx 把 D/E、F/G（soe 为 E/F、G/H）的叶子填上了 ⇒ 段数变 3 ⇒ 打红，
    提醒重新裁决（该表就不再是「单槽占位」了）。
    """
    out: list[SelfCheck] = []
    for ex in SOURCE_PLACEHOLDER_SINGLE_SLOT:
        src = facts.get(ex.key)
        if src is None:
            out.append(SelfCheck(f"豁免仍单槽 {ex.table}", False, "登记表 stale：源事实缺失"))
            continue
        runs = _compress_groups(src["columns"])
        ok = len(runs) == ex.expected_source_runs
        out.append(SelfCheck(
            f"豁免仍单槽 {ex.table}", ok,
            f"源侧段数={len(runs)} 期望={ex.expected_source_runs} @ {ex.source_ref}"
            + ("" if ok else "  ⇒ 源 xlsx 已填多槽，必须重新裁决而非继续豁免"),
        ))
    return out


def _sc_exemption_registry(
    facts: dict[tuple[str, str, str], dict[str, Any]],
    seed: dict[tuple[str, str, str], dict[str, Any]],
) -> list[SelfCheck]:
    """豁免登记表自身的完整性：上限只许下调、键真实存在、只豁免 flat/group、理由齐备。"""
    out: list[SelfCheck] = []
    out.append(SelfCheck(
        "豁免上限只许下调", _EXEMPTION_CAP <= _EXEMPTION_CAP_CEILING,
        f"_EXEMPTION_CAP={_EXEMPTION_CAP} 天花板={_EXEMPTION_CAP_CEILING}",
    ))
    out.append(SelfCheck(
        "豁免条目数 <= 上限", len(SOURCE_PLACEHOLDER_SINGLE_SLOT) <= _EXEMPTION_CAP,
        f"条目数={len(SOURCE_PLACEHOLDER_SINGLE_SLOT)} 上限={_EXEMPTION_CAP}",
    ))
    missing = [e.key for e in SOURCE_PLACEHOLDER_SINGLE_SLOT
               if e.key not in facts or e.key not in seed]
    out.append(SelfCheck("豁免键均真实存在", not missing, f"stale 条目={missing!r}"))
    bad_kinds = [e.key for e in SOURCE_PLACEHOLDER_SINGLE_SLOT
                 if not e.exempt_kinds <= {"flat", "group"}]
    out.append(SelfCheck("只豁免 flat/group", not bad_kinds, f"越权条目={bad_kinds!r}"))
    thin = [e.key for e in SOURCE_PLACEHOLDER_SINGLE_SLOT
            if len(e.basis) < 4 or len(e.source_text) < 20 or len(e.platform_intent) < 20]
    out.append(SelfCheck("每条豁免理由齐备（源原文/依据>=4条/平台意图）", not thin,
                         f"理由不全={thin!r}"))
    overlap = set(EXEMPTION_INDEX) & set(DYNAMIC_MATRIX_EXPECTED_RUNS)
    out.append(SelfCheck("豁免表与动态列表互斥", not overlap, f"交集={overlap!r}"))
    return out


def _sc_corner_title_registry(
    facts: dict[tuple[str, str, str], dict[str, Any]],
    seed: dict[tuple[str, str, str], dict[str, Any]],
) -> list[SelfCheck]:
    """登记 3 的 stale 检测与完整性。

    stale 判据 = 源侧标签列两行原文仍与 ``expected_parts`` 逐字相等。某天源 xlsx 给
    行标识列补上真列名（或把转角标题合并成一行）⇒ 打红，提醒移出登记而非继续豁免。

    🔴 另配「另 1 张真拼接表不得进本登记」的互斥断言 —— 那张
    （``结构化主体获得收益及转移资产情况``）的拼接是**正确**的，若被顺手加进来
    就等于把一个真偏差永久豁免掉。
    """
    out: list[SelfCheck] = []
    out.append(SelfCheck(
        "转角标题上限只许下调", _CORNER_CAP <= _CORNER_CAP_CEILING,
        f"_CORNER_CAP={_CORNER_CAP} 天花板={_CORNER_CAP_CEILING}",
    ))
    out.append(SelfCheck(
        "转角标题条目数 <= 上限", len(CORNER_TITLE_EXEMPTIONS) <= _CORNER_CAP,
        f"条目数={len(CORNER_TITLE_EXEMPTIONS)} 上限={_CORNER_CAP}",
    ))
    for ex in CORNER_TITLE_EXEMPTIONS:
        src = facts.get(ex.key)
        if src is None:
            out.append(SelfCheck(f"转角标题 stale {ex.table}", False, "源事实缺失"))
            continue
        got = tuple(src["label_header_parts"])
        ok = got == ex.expected_parts
        out.append(SelfCheck(
            f"转角标题 stale {ex.table}", ok,
            f"源侧 parts={got!r} 期望={ex.expected_parts!r}"
            + ("" if ok else "  ⇒ 源 xlsx 已变，须重新裁决而非继续豁免"),
        ))
        sd = seed.get(ex.key)
        lab = next((c for c in (sd or {}).get("columns", []) if c["is_label"]), None)
        seed_ok = lab is not None and _norm(lab["label"]) == _norm(ex.seed_label)
        out.append(SelfCheck(
            f"转角标题 seed 实现值 {ex.table}", seed_ok,
            f"seed 标签列 label={(lab or {}).get('label')!r} 期望={ex.seed_label!r}",
        ))
        thin = len(ex.basis) < 4 or len(ex.platform_intent) < 20 or not ex.expected_data_rows
        out.append(SelfCheck(
            f"转角标题理由齐备 {ex.table}", not thin,
            f"依据={len(ex.basis)} 条 / 数据行样例={ex.expected_data_rows!r}",
        ))
    # 互斥：真拼接表（结构化主体获得收益）不得进本登记
    true_concat = ("soe", "八、18", "结构化主体获得收益及转移资产情况")
    out.append(SelfCheck(
        "真纵向拆分列名表不得进转角登记", true_concat not in CORNER_TITLE_INDEX,
        f"{true_concat[2]} 的拼接是正确的（数据行=信用资产证券化/投资基金），"
        "进登记会把真偏差永久豁免",
    ))
    # 三张登记表键两两互斥（同一表不得被两种理由重复豁免）
    for a_name, a, b_name, b in (
        ("单槽", set(EXEMPTION_INDEX), "平台约束", set(PLATFORM_EXEMPTION_INDEX)),
        ("单槽", set(EXEMPTION_INDEX), "转角标题", set(CORNER_TITLE_INDEX)),
        ("平台约束", set(PLATFORM_EXEMPTION_INDEX), "转角标题", set(CORNER_TITLE_INDEX)),
    ):
        out.append(SelfCheck(
            f"登记表互斥 {a_name} x {b_name}", not (a & b), f"交集={(a & b)!r}",
        ))
    return out


def _sc_platform_constraint_registry(
    facts: dict[tuple[str, str, str], dict[str, Any]],
    seed: dict[tuple[str, str, str], dict[str, Any]],
) -> list[SelfCheck]:
    """登记 2 的 stale 检测与完整性。

    stale 判据 = 源侧该处**仍触发平台约束**：
      * ``group_label`` 条目 ⇒ 源侧 group 名仍含 `/`（不含了就该移出登记直接照抄）
      * ``label`` 条目 ⇒ 源侧仍是三级表头（``level_count >= 3``）

    🔴 另断言 ``kind == 'label'`` 的条目**必须**带 ``col_indexes``（否则等于整表豁免，
    会把同表其他列的真偏差一起放过）。
    """
    out: list[SelfCheck] = []
    out.append(SelfCheck(
        "平台约束豁免上限只许下调",
        _PLATFORM_EXEMPTION_CAP <= _PLATFORM_EXEMPTION_CAP_CEILING,
        f"_PLATFORM_EXEMPTION_CAP={_PLATFORM_EXEMPTION_CAP} "
        f"天花板={_PLATFORM_EXEMPTION_CAP_CEILING}",
    ))
    out.append(SelfCheck(
        "平台约束豁免条目数 <= 上限",
        len(PLATFORM_CONSTRAINT_EXEMPTIONS) <= _PLATFORM_EXEMPTION_CAP,
        f"条目数={len(PLATFORM_CONSTRAINT_EXEMPTIONS)} 上限={_PLATFORM_EXEMPTION_CAP}",
    ))
    for ex in PLATFORM_CONSTRAINT_EXEMPTIONS:
        src = facts.get(ex.key)
        if src is None or ex.key not in seed:
            out.append(SelfCheck(f"平台约束键存在 {ex.table}", False, "源事实或 seed 缺失"))
            continue
        if ex.kind == "group_label":
            names = [g for g, _s, _p in _compress_groups(src["columns"])]
            still = any("/" in n for n in names)
            out.append(SelfCheck(
                f"平台约束 stale {ex.table}", still,
                f"源侧 group 名={names!r}"
                + ("" if still else "  ⇒ 源文已不含 '/'，该移出登记并逐字照抄"),
            ))
        elif ex.kind == "label":
            still = src["level_count"] >= 3
            out.append(SelfCheck(
                f"平台约束 stale {ex.table}", still,
                f"源侧 level_count={src['level_count']}"
                + ("" if still else "  ⇒ 源侧已非三级表头，该移出登记"),
            ))
            out.append(SelfCheck(
                f"label 豁免必须带列下标 {ex.table}", bool(ex.col_indexes),
                f"col_indexes={sorted(ex.col_indexes)!r}"
                + ("" if ex.col_indexes else "  ⇒ 空集等于整表豁免，会放过同表其他列真偏差"),
            ))
        thin = (
            len(ex.basis) < 4
            or len(ex.platform_intent) < 20
            or len(ex.expected_source_text) < 10
            or len(ex.constraint) < 20
        )
        out.append(SelfCheck(
            f"平台约束理由齐备 {ex.table}", not thin,
            f"依据={len(ex.basis)} 条 / 约束={len(ex.constraint)} 字",
        ))
    return out


def run_self_checks(
    facts: dict[tuple[str, str, str], dict[str, Any]],
    seed: dict[tuple[str, str, str], dict[str, Any]],
) -> list[SelfCheck]:
    return [
        *_sc_dynamic_matrix_runs(facts, seed),
        *_sc_uniform_dynamic_would_merge(facts),
        *_sc_single_slot_still_single(facts),
        *_sc_exemption_registry(facts, seed),
        *_sc_platform_constraint_registry(facts, seed),
        *_sc_corner_title_registry(facts, seed),
    ]


# ─────────────────────────── 事实投影 JSON ───────────────────────────


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def build_facts_payload(facts: dict[tuple[str, str, str], dict[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "_meta": {
            "note": (
                "派生投影，非真源。真源 = backend/wp_templates/G/G7 长期股权投资.xlsx；"
                "本文件由 backend/scripts/diagnose/diagnose_g7_column_alignment.py --emit-facts "
                "生成，并由 backend/tests/four_table/test_g7_column_source_facts.py 钉死"
                "「与实时 openpyxl 读取逐字相等」。禁止手改。"
            ),
            "generated_from": "backend/wp_templates/G/G7 长期股权投资.xlsx",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source_sha256": _sha256(SRC_XLSX),
            "sheet_names": [SHEETS["listed"], SHEETS["soe"]],
            "two_level_rule": "横向合并（跨度>=2、值非空、起始列在标签列右侧）= 父表头",
            "dynamic_group_rule": (
                "值为空的横向合并 = 动态列占位（源模板留给审计师填被投资单位名），"
                f"记作 '{DYNAMIC_GROUP_PREFIX}c<锚列>>'。**按锚列区分身份**，"
                "否则相邻同名占位会被运行段压缩误并成一段（3 个跨 2 → 1 个跨 6）。"
                "消费方比对时对该占位只校验 (start, span) 不校验名字。"
            ),
            "index_key": "(variant, noteSectionId, tableName) 三元组",
            "label_header_kind_rule": (
                "标签列表头语义三态，**一处登记两端消费**（后端 CORNER_TITLE_EXEMPTIONS 是"
                "唯一真源，前端读本字段不得另抄一份判定）：\n"
                "  * 'name'   = 源 xlsx 给了行标识列名（含纵向合并的单一名、以及真纵向"
                "拆分列名如 '结构化主体'+'类型'）⇒ `label_header` 可直接逐字比对；\n"
                "  * 'corner' = **转角标题**：标签列两行文字各自标注**表头行本身**"
                "（上行放公司名、下行放日期/期间），源 xlsx **未给行标识列名** ⇒ "
                "`label_header` 是拼接出的**幻影**，禁止用它比对；平台按数据行语义取"
                "`seed_label`（实测为「项目」）。\n"
                "  * 与 'name' 的区分靠**语义**（两者结构完全同形）⇒ 只能登记 + stale 检测，"
                "不可由结构判据自动判。"
            ),
            "single_slot_exemption_rule": (
                "源模板占位形态（单槽）豁免，**一处登记两端消费**（后端 "
                "SOURCE_PLACEHOLDER_SINGLE_SLOT 是唯一真源，前端读表级 "
                "`single_slot_exemption` 字段，不得另抄一份表名清单）：\n"
                "  这 4 张合营表源侧确有「空白跨 2 合并」暗示多个实体槽，但**同表另两组"
                "合并的叶子行全空** ⇒ 源模板自身只填了 1 槽，与联营表填满 3 槽不同构。\n"
                "  平台按**单槽 flat** 实现（标签列 + 2 个数据列，不声明 group）⇒ 运行时"
                "「无分组」与源侧「1 段动态占位跨 2」的差异是**已裁决豁免**，不是待修偏差。\n"
                "  🔴 消费方须豁免的维度 = `exempt_kinds`（仅 flat / group）；其余维度照常比对。\n"
                "  🔴 stale 检测在后端 `_sc_single_slot_still_single()`：源侧段数一旦不再是 1"
                "（源 xlsx 把叶子填满多槽）即打红，提醒**重新裁决**而非继续豁免。"
            ),
        }
    }
    for (variant, section, table), tf in sorted(facts.items(), key=lambda kv: kv[0]):
        cex = CORNER_TITLE_INDEX.get((variant, section, table))
        sex = EXEMPTION_INDEX.get((variant, section, table))
        entry: dict[str, Any] = {
            "label_header": tf["label_header"],
            "label_header_parts": tf["label_header_parts"],
            # 🔴 **未归一化原文**（additive，2026-08-12 Task 12 补）：
            #    `label_header` 经 `_norm()` 去掉了全部空白，故源模板的
            #    `项  目`（双空格）/`项 目`（单空格）在它上面**结构上不可见** ——
            #    G7 运行时长期写 `项目` 而边①/边③ 两个守卫都判绿，正是这个盲区。
            #    R4.4 要求「源 xlsx 自身用了两种写法时以该表原文为准，禁统一成好看的那种」
            #    ⇒ 逐字判据必须落在本字段上；`label_header` 保留给「多行表头拼接容忍」那类比对。
            "label_header_raw": tf["label_header_raw"],
            "label_header_parts_raw": tf["label_header_parts_raw"],
            "label_xlsx_span": tf["label_xlsx_span"],
            # 🔴 三态标记：'corner' 时 `label_header` 是幻影，消费方须改用 `label_header_seed`
            "label_header_kind": "corner" if cex is not None else "name",
            "is_two_level": tf["is_two_level"],
            "level_count": tf["level_count"],
            "source_rows": tf["source_rows"],
            "columns": tf["columns"],
        }
        if cex is not None:
            entry["label_header_seed"] = cex.seed_label
            entry["label_header_corner_basis"] = {
                "source_ref": cex.source_ref,
                "row_titled": list(cex.row_titled),
                "data_row_samples": list(cex.expected_data_rows),
                "platform_intent": cex.platform_intent,
            }
        # 🔴 登记 1（单槽占位）下发：前端 A源 维度靠它豁免那 4 张合营表，
        #    否则同一个已裁决结论要在 TS 里再抄一份表名清单（两份必然漂移）。
        if sex is not None:
            entry["single_slot_exemption"] = {
                "exempt_kinds": sorted(sex.exempt_kinds),
                "source_ref": sex.source_ref,
                "source_text": sex.source_text,
                "basis": list(sex.basis),
                "platform_intent": sex.platform_intent,
                "expected_source_runs": sex.expected_source_runs,
            }
        payload.setdefault(variant, {}).setdefault(section, {})[table] = entry
    return payload


def emit_facts() -> Path:
    payload = build_facts_payload(read_source_facts())
    FACTS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return FACTS_PATH


# ─────────────────────────── 报告 ───────────────────────────


_KINDS = ("table_missing", "seed_no_cols", "is_label", "flat", "group", "group_label",
          "key_label_col", "key_data_col", "label", "count")


def _print_report(
    devs: list[AlignmentDeviation],
    facts: dict,
    seed: dict,
    checks: list[SelfCheck],
) -> None:
    counted = [d for d in devs if d.counted]
    exempted = [d for d in devs if not d.counted]

    print("=" * 96)
    print("G7 列结构对齐诊断 —— 边① 源 xlsx <-> 模板 seed（只读）")
    print("=" * 96)
    print(f"源模板: {SRC_XLSX.relative_to(_REPO_ROOT)}")
    print(f"sha256: {_sha256(SRC_XLSX)}")
    print()

    for variant in ("listed", "soe"):
        tables = [k for k in facts if k[0] == variant]
        secs = sorted({k[1] for k in tables})
        print(f"[{variant}] 源 xlsx 表数={len(tables)}  章节={len(secs)}  {secs}")
    print(f"[seed] 作用域内表数={len(seed)}")
    print()

    # ───────────────────── 一、计入偏差 ─────────────────────
    print("=" * 96)
    print(f"一、计入偏差（{len(counted)} 个偏差点）")
    print("=" * 96)

    print("-" * 96)
    print("按 variant x 成因分类统计")
    print("-" * 96)
    print(f"{'variant':<8}" + "".join(f"{c:>8}" for c in ("A", "B", "C", "D", "E", "-"))
          + f"{'合计':>8}")
    for variant in ("listed", "soe"):
        sub = [d for d in counted if d.variant == variant]
        cells = "".join(f"{sum(1 for d in sub if d.cls == c):>8}"
                        for c in ("A", "B", "C", "D", "E", "-"))
        print(f"{variant:<8}{cells}{len(sub):>8}")
    cells = "".join(f"{sum(1 for d in counted if d.cls == c):>8}"
                    for c in ("A", "B", "C", "D", "E", "-"))
    print(f"{'TOTAL':<8}{cells}{len(counted):>8}")
    print()
    for c in ("A", "B", "C", "D", "E", "-"):
        print(f"  {c} = {CLASS_DESC[c]}")
    print()

    print("-" * 96)
    print("按 kind 统计")
    print("-" * 96)
    for variant in ("listed", "soe"):
        sub = [d for d in counted if d.variant == variant]
        parts = " ".join(f"{k}={sum(1 for d in sub if d.kind == k)}" for k in _KINDS)
        with_dev = len({(d.variant, d.section, d.table) for d in sub})
        total = len([k for k in facts if k[0] == variant])
        print(f"{variant}: total={total} 有计入偏差的表数={with_dev} 无计入偏差={total - with_dev}")
        print(f"    {parts}")
    print()
    print("  注 1：key_data_col 恒为 0 —— 源 xlsx 只有列头文字、无数据键，该维不可由本脚本")
    print("        裁决，归前端三向守卫（Task 3）比对 seed 与运行时（边②③）。")
    print("  注 2：group_label（父表头文字不符、结构一致）计入 D 类，A 类只保留结构性丢 group。")
    print()

    print("-" * 96)
    print("计入偏差明细")
    print("-" * 96)
    cur = None
    for d in counted:
        head = (d.variant, d.section, d.table)
        if head != cur:
            cur = head
            print(f"\n### [{d.variant}] {d.section} | {d.table}")
        print(f"  [{d.cls}] {d.kind}")
        print(f"       seed  : {d.seed}")
        print(f"       source: {d.source}")
    if not counted:
        print("(无偏差)")
    print()

    print("-" * 96)
    print("无计入偏差的表清单")
    print("-" * 96)
    dirty = {(d.variant, d.section, d.table) for d in counted}
    clean = [k for k in sorted(facts) if k not in dirty]
    for variant, section, table in clean:
        k = (variant, section, table)
        tags = []
        if k in EXEMPTION_INDEX:
            tags.append("仅豁免登记项①源模板单槽")
        if k in PLATFORM_EXEMPTION_INDEX:
            tags.append("仅豁免登记项②平台约束")
        tag = f" ({' + '.join(tags)})" if tags else ""
        print(f"  [OK] [{variant}] {section} | {table}{tag}")
    if not clean:
        print("  (无)")
    print()

    # ───────────────────── 二、豁免登记 ─────────────────────
    print("=" * 96)
    print(f"二、豁免登记：源模板占位形态（单槽）—— {len(SOURCE_PLACEHOLDER_SINGLE_SLOT)} 条 / "
          f"{len(exempted)} 个豁免偏差点（不计入偏差数）")
    print("=" * 96)
    print("🔴 如实说明：这 4 张合营表的源模板 merge 结构**暗示 3 个实体槽**")
    print("   （B132:C132 / D132:E132 / F132:G132 三个空白跨 2 合并），")
    print("   但**叶子行只填了 1 槽**（D133~G133 全空）⇒ 平台按**单槽 flat** 实现。")
    print("   这是已裁决的源模板占位形态，不是待修项；源 xlsx 若某天填满多槽，")
    print("   `豁免仍单槽` 自检立即打红，须重新裁决。")
    print()
    for ex in SOURCE_PLACEHOLDER_SINGLE_SLOT:
        eds = [d for d in exempted if (d.variant, d.section, d.table) == ex.key]
        print(f"### [{ex.variant}] {ex.section} | {ex.table}")
        print(f"    源模板位置 : {ex.source_ref}")
        print(f"    源模板原文 : {ex.source_text}")
        print("    判定依据   :")
        for i, b in enumerate(ex.basis, 1):
            print(f"        {i}. {b}")
        print(f"    平台实现   : {ex.platform_intent}")
        print(f"    豁免维度   : {sorted(ex.exempt_kinds)}  (本表命中 {len(eds)} 个)")
        for d in eds:
            print(f"        - {d.kind}: seed={d.seed} | source={d.source}")
        print()

    # ────────── 二之二、豁免登记：平台结构约束导致的必要偏离 ──────────
    plat_exempted = [d for d in exempted if (d.variant, d.section, d.table) in PLATFORM_EXEMPTION_INDEX]
    print("=" * 96)
    print(f"二之二、豁免登记：平台结构约束必要偏离 —— "
          f"{len(PLATFORM_CONSTRAINT_EXEMPTIONS)} 条 / {len(plat_exempted)} 个豁免偏差点")
    print("=" * 96)
    print("🔴 与登记表①的区别：①的成因在**源模板自身**（只填 1 槽）；本表成因在")
    print("   **平台渲染约束**（源模板没错、平台 group 只支持单级）⇒ 源文含 '/' 或三级")
    print("   表头时逐字照抄会渲染崩，必须做等价改写。这是已裁决的必要偏离、不是待修偏差。")
    print()
    for pex in PLATFORM_CONSTRAINT_EXEMPTIONS:
        eds = [d for d in plat_exempted if (d.variant, d.section, d.table) == pex.key]
        print(f"### [{pex.variant}] {pex.section} | {pex.table}")
        print(f"    源模板位置 : {pex.source_ref}")
        print(f"    源模板原文 : {pex.expected_source_text}")
        print(f"    平台实现值 : {pex.seed_text}")
        print(f"    触发约束   : {pex.constraint}")
        print("    判定依据   :")
        for i, b in enumerate(pex.basis, 1):
            print(f"        {i}. {b}")
        print(f"    平台意图   : {pex.platform_intent}")
        print(f"    豁免维度   : {pex.kind}  (本表命中 {len(eds)} 个)")
        for d in eds:
            print(f"        - {d.kind}: seed={d.seed} | source={d.source}")
        print()

    # ───────────────────── 三、反向自检 ─────────────────────
    print("=" * 96)
    print("三、反向自检")
    print("=" * 96)
    for c in checks:
        print(f"  [{'OK ' if c.ok else 'ERR'}] {c.name}")
        print(f"        {c.detail}")
    failed = [c for c in checks if not c.ok]
    print()
    print(f"  自检: {len(checks) - len(failed)}/{len(checks)} 通过")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="G7 列结构对齐诊断（只读）：源 xlsx <-> 模板 seed 六维比对",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", default=True,
                       help="默认：打印偏差报告，不写任何文件")
    group.add_argument("--check", action="store_true",
                       help="有欠账时 exit 2（供 CI 使用）")
    group.add_argument("--emit-facts", action="store_true",
                       help=f"写派生投影 {FACTS_PATH.relative_to(_REPO_ROOT)}（唯一允许的写盘）")
    args = parser.parse_args(argv)

    if args.emit_facts:
        path = emit_facts()
        payload = json.loads(path.read_text(encoding="utf-8"))
        n = sum(len(t) for v in ("listed", "soe") for t in payload[v].values())
        print(f"[OK] 已写 {path.relative_to(_REPO_ROOT)}  表数={n}")
        print(f"     _meta.source_sha256={payload['_meta']['source_sha256']}")
        return 0

    facts = read_source_facts()
    seed = load_seed_facts()
    devs = build_alignment_report()
    checks = run_self_checks(facts, seed)
    _print_report(devs, facts, seed, checks)

    counted = [d for d in devs if d.counted]
    exempted = [d for d in devs if not d.counted]
    failed_checks = [c for c in checks if not c.ok]

    if args.check:
        if failed_checks:
            print(f"[ERR] 反向自检 {len(failed_checks)} 项未通过（判据本身可能已失效）")
            return 2
        if counted:
            print(f"[ERR] 存在 {len(counted)} 个计入偏差点（另 {len(exempted)} 个已豁免），未收口")
            return 2
        print(f"[OK] 0 项欠账（豁免登记 {len(exempted)} 个偏差点不计入）")
        return 0
    print(f"[WARN] dry-run：计入偏差 {len(counted)} 个 / 豁免 {len(exempted)} 个 / "
          f"自检失败 {len(failed_checks)} 项（--check 会以 exit 2 报告）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
