#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""L 循环附注章节结构对齐（幂等）。

覆盖 L5 长期应付款 / L6 专项应付款 / L7 其他非流动负债 / L8 财务费用：

| 章节        | 科目             | 源模板 sheet                              |
|-------------|------------------|-------------------------------------------|
| 五、48      | 长期应付款(+专项) | L5 `附注披露信息（上市公司）` + L6 同名     |
| 八、53      | 长期应付款(+专项) | L5 `附注披露信息（国企）` + L6 `附注披露（国企）信息` |
| 八、47      | 一年内到期长期应付款 | L5 国企（源 xlsx 主表的减项）           |
| 五、52      | 其他非流动负债   | `附注披露信息（上市公司）`                |
| 八、57      | 其他非流动负债   | `附注披露信息(国企)`（**半角**）          |
| 五、67      | 财务费用         | `附注披露信息（上市公司）`                |
| 八、68      | 财务费用         | `附注披露信息（国企）`                    |

🔴 **L6 专项应付款没有独立附注章节**：其披露表是 五、48 的第 3 张「专项应付款」/
八、53 的第 3 张「①专项应付款期末余额最大的前5 项」，与 L5 共章节 —— 由两个底稿
分别推**不同子表**，靠后端 `sub_table_data` 按 key 浅合并（同 H4→H2 已验证范式）。
源 xlsx L6 两版都写着「【长期应付款与专项应付款的合计数披露详见P5-1】」印证此点。

修订内容（全部以 `backend/wp_templates/L/*.xlsx` 为裁决者 —— `附注模版/*.md`
在本仓库不存在，只能以源 xlsx 复核，同 F2 Sprint 7 的裁决口径）：

0. **L5/L6 三章节**：
   - 五、48「（按款项性质列示）」**只有小计/减项/合计三行、缺全部数据行骨架** →
     按源 xlsx r12~r18 补「毛额段 2 行 +『减：未确认融资费用：』标签行 + 未确认段 2 行」；
     `…` 占位省略号删除。
   - 五、48「专项应付款」只有合计行 → 补 5 个空白录入行（源 xlsx L6 上市 r9~r18 为空行）。
   - 八、53 两张「前5 项」表的 `1．`~`5．` 是**序号占位行名**，会被推成占位披露行
     → 改空白骨架（同 K3「账龄超1年」的处理）。
   - 八、47 只有合计行 → 补 3 个空白录入行。
1. **五、52 表名 `项  目` 是表头首格泄漏** → 正名「其他非流动负债」（与国企侧同名），
   否则附注 TAB 页签显示列名、同步侧无法按表名定位。
2. **五、52 无数据行骨架**（只有合计行）→ 源 xlsx r7~r11 是 5 个空行，补空白骨架。
3. **八、57 残留 `……` 占位行** → 删（md 重建把源模板省略号当数据行）。
4. **财务费用两版行集与源模板不符** —— 源 xlsx r7~r18 共 12 行（含 3 个派生小计
   行「利息费用 / 利息净支出 / 汇兑净损失」），而模板上市只有 7 行、国企 9 行：
   上市缺「利息费用 / 利息净支出 / 承兑汇票贴息 / 汇兑损失 / 减：汇兑收益 /
   汇兑净损失」，且「利息支出」应为「利息费用总额」、「利息收入」应为「减：利息收入」、
   「汇兑损益」应为「汇兑损失」；国企缺「利息净支出 / 汇兑损失 / 减：汇兑收益 /
   汇兑净损失」，且「利息费用净额」应为「利息费用」。→ 两版统一按源 xlsx 重建。
5. 四张表全部补 `columns`（**单级表头 → 显式 `flat`**，防 `_infer_groups_from_headers`
   凭空推断父表头）+ `guidance`。

🔴 两处**有意不改**（决策留痕，防后续会话反复"纠正"）：

- **八、57 列序保持「期末余额 / 期初余额」**：源 xlsx 国企侧 r6 是「项目 | 年初余额 |
  期末余额」（期初在前），但①附注交付物惯例期末在前，②模板既有 `合同负债` 行已带
  `account_codes` 说明被认真 seed 过，③上市侧亦为期末在前。源 xlsx 的列序属底稿录入
  习惯，不传导到附注。
- **五、52 列名取源 xlsx 的「期末数 / 上年年末数」**（模板原 headers 写「期末余额 /
  上年年末余额」）：模板 headers 是 `rebuild_note_from_md.py` 产物易失真，而源 xlsx
  r6 明确是「期末数 / 上年年末数」，且既有 `l7NoteSectionMap.ts` 也是这两个字面。
- **八、53 两张「前5 项」表名保留 `①` 前缀与「前5 项」的空格**：源 xlsx 无这两个
  表名（源写「长期应付款（说明：分项披露…前五项）」），该字面来自附注模版 md =
  交付物权威；改名要同步 `l5/l6NoteSectionMap`，收益低风险高。
- **八、53 专项应付款表列头保留模板的「期初余额 / 期末余额」**：源 xlsx L6 国企 r9
  写的是 `201X.01.01` / `201X.12.31`（**年份占位符**），不能当附注列头字面。

Usage::

    python backend/scripts/fix/fix_note_l_cycle_structure.py --dry-run
    python backend/scripts/fix/fix_note_l_cycle_structure.py
    python backend/scripts/fix/fix_note_l_cycle_structure.py --check
    python backend/scripts/fix/fix_note_l_cycle_structure.py --only l8-listed

spec: .kiro/specs/disclosure-sync-path-buildout/ Task 4
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

_KIT_PATH = Path(__file__).resolve().parent / "_note_structure_kit.py"
_spec = importlib.util.spec_from_file_location("_note_structure_kit", _KIT_PATH)
assert _spec and _spec.loader
kit = importlib.util.module_from_spec(_spec)
sys.modules["_note_structure_kit"] = kit
_spec.loader.exec_module(kit)

AMOUNT = kit.AMOUNT
TEXT = kit.TEXT

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LISTED = DATA_DIR / "note_template_listed.json"
SOE = DATA_DIR / "note_template_soe.json"

ALIGNED_BY = "fix_note_l_cycle_structure"

# ── L8 财务费用：源 xlsx r7~r18 逐字行清单（两版完全相同） ────────────────────
#
# 派生关系（源模板计算行，写进 guidance）：
#   利息费用   = 利息费用总额 − 减：利息资本化
#   利息净支出 = 利息费用 − 减：利息收入
#   汇兑净损失 = 汇兑损失 − 减：汇兑收益 − 减：汇兑损益资本化
#   合计       = 利息净支出 + 承兑汇票贴息 + 汇兑净损失 + 手续费及其他
FINANCE_COST_ROWS: list[str] = [
    "利息费用总额",
    "减：利息资本化",
    "利息费用",
    "减：利息收入",
    "利息净支出",
    "承兑汇票贴息",
    "汇兑损失",
    "减：汇兑收益",
    "减：汇兑损益资本化",
    "汇兑净损失",
    "手续费及其他",
]

FINANCE_COST_GUIDANCE = (
    "勾稽：利息费用 = 利息费用总额 − 利息资本化；利息净支出 = 利息费用 − 利息收入；"
    "汇兑净损失 = 汇兑损失 − 汇兑收益 − 汇兑损益资本化；"
    "合计 = 利息净支出 + 承兑汇票贴息 + 汇兑净损失 + 手续费及其他。"
    "（注：以下不存在的项目可以删除）数据来源 L8-1 审定表 / L8-2 明细表。"
)


def _finance_cost_columns() -> list[dict[str, Any]]:
    return kit.flat_columns([
        ("label", "项目", None),
        ("current_amount", "本期发生额", AMOUNT),
        ("prior_amount", "上期发生额", AMOUNT),
    ])


def _finance_cost_rows() -> list[dict[str, Any]]:
    return kit.labels_then_total(FINANCE_COST_ROWS)


# ── L5 长期应付款 / L6 专项应付款 ────────────────────────────────────────────

#: 五、48（1）按款项性质列示 —— 源 xlsx r12~r21 逐字（`…` 占位行已剔除）
LISTED_BY_NATURE_ROWS: list[dict[str, Any]] = [
    kit.data_row("售后租回业务形成的融资"),
    kit.data_row("分期付款方式购入固定资产"),
    kit.data_row("减：未确认融资费用："),
    kit.data_row("售后租回业务形成的融资"),
    kit.data_row("分期付款方式购入固定资产"),
    kit.subtotal_row("小计"),
    kit.data_row("减：一年内到期长期应付款"),
    kit.total_row(),
]

#: 八、53① 前 5 项 —— 序号占位 `1．`~`5．` 改空白骨架 + 其他 + 小计 + 减项 + 合计
SOE_TOP5_LTP_ROWS: list[dict[str, Any]] = [
    *[kit.data_row() for _ in range(5)],
    kit.data_row("其他"),
    kit.subtotal_row("小计"),
    kit.data_row("减：一年内到期长期应付款项"),
    kit.total_row(),
]

SOE_TOP5_SPECIAL_ROWS: list[dict[str, Any]] = [
    *[kit.data_row() for _ in range(5)],
    kit.data_row("其他"),
    kit.total_row(),
]


def _two_period_cols(end_label: str, prior_label: str) -> list[dict[str, Any]]:
    return kit.flat_columns([
        ("label", "项目", None),
        ("end_amount", end_label, AMOUNT),
        ("prior_amount", prior_label, AMOUNT),
    ])


def _special_payable_cols(begin_label: str, end_label: str, with_reason: bool) -> list[dict[str, Any]]:
    pairs: list[tuple[str, str, str | None]] = [
        ("label", "项目", None),
        ("begin_amount", begin_label, AMOUNT),
        ("increase", "本期增加", AMOUNT),
        ("decrease", "本期减少", AMOUNT),
        ("end_amount", end_label, AMOUNT),
    ]
    if with_reason:
        pairs.append(("reason", "形成原因", TEXT))
    return kit.flat_columns(pairs)


LTP_MAIN_GUIDANCE = (
    "勾稽：合计 = 长期应付款 + 专项应付款。两行分别等于下方「按款项性质列示」"
    "与「专项应付款」两表的合计（专项应付款由 L6 底稿推送）。数据来源 L5-1 审定表。"
)

LTP_BY_NATURE_GUIDANCE = (
    "勾稽：小计 = 毛额各项 − 未确认融资费用各项；合计 = 小计 − 一年内到期长期应付款。"
    "「减：未确认融资费用：」为分组标签行（源 xlsx r15），其下明细与毛额段一一对应。"
    "数据来源 L5-2 明细表 / L5-3 未确认融资费用明细表。"
)

SPECIAL_PAYABLE_GUIDANCE = (
    "勾稽：期末余额 = 期初余额 + 本期增加 − 本期减少；合计 = 各项之和。"
    "本表由 **L6 专项应付款**底稿推送（与长期应付款共章节，按子表名浅合并）。"
    "须说明专项应付款的来源、指定的专门用途与使用限制。"
)


def plan_l5_listed() -> tuple[list[dict[str, Any]], list[str], list[str], list[str]]:
    """五、48 长期应付款（上市）—— 3 表（第 3 张由 L6 推送）。"""
    main = "长期应付款"
    by_nature = "长期应付款（按款项性质列示）"
    special = "专项应付款"
    plan = [
        kit.rule(
            main,
            _two_period_cols("期末数", "上年年末余额"),
            kit.labels_then_total(["长期应付款", "专项应付款"]),
            LTP_MAIN_GUIDANCE,
        ),
        kit.rule(
            by_nature,
            _two_period_cols("期末数", "上年年末余额"),
            LISTED_BY_NATURE_ROWS,
            LTP_BY_NATURE_GUIDANCE,
        ),
        kit.rule(
            special,
            _special_payable_cols("期初数", "期末数", with_reason=True),
            kit.blanks_then_total(5),
            SPECIAL_PAYABLE_GUIDANCE,
        ),
    ]
    text_sections = [
        "### 长期应付款（按款项性质列示）",
        "### 专项应付款",
        "（说明专项应付款的来源、指定的专门用途、使用限制等相关内容。"
        "如：该专项应付款为财政部按照XX文规定拨付的X项目专用设备购置款。）",
        "【提示：",
        "1、企业因城镇整体规划、库区建设、棚户区改造、沉陷区治理等公共利益进行搬迁，"
        "收到政府从财政预算直接拨付的搬迁补偿款，在专项应付款中核算。",
        "2、根据《财政部关于印发〈工业企业结构调整专项奖补资金管理办法〉的通知》，"
        "中央财政将安排工业企业结构调整专项奖补资金，用于支持地方政府和中央企业推动钢铁、"
        "煤炭等行业化解过剩产能。中央企业在收到预拨的专项奖补资金时，应当暂通过"
        "“专项应付款”科目核算，借记“银行存款”等科目，贷记“专项应付款”科目。】",
    ]
    return plan, [main, by_nature, special], [], text_sections


def plan_l5_soe() -> tuple[list[dict[str, Any]], list[str], list[str], list[str]]:
    """八、53 长期应付款（国企）—— 3 表（第 3 张由 L6 推送）。"""
    main = "长期应付款"
    top5 = "①长期应付款项期末余额最大的前5 项"
    special = "①专项应付款期末余额最大的前5 项"
    plan = [
        kit.rule(
            main,
            _two_period_cols("期末数", "期初数"),
            kit.labels_then_total(["长期应付款", "专项应付款"]),
            LTP_MAIN_GUIDANCE,
        ),
        kit.rule(
            top5,
            _two_period_cols("期末余额", "年初余额"),
            SOE_TOP5_LTP_ROWS,
            "勾稽：小计 = 前 5 项 + 其他；合计 = 小计 − 一年内到期长期应付款项。"
            "源模板要求分项披露期末余额最大的前五项（行名按实际单位/项目填列）。"
            "数据来源 L5-2 明细表。",
        ),
        kit.rule(
            special,
            _special_payable_cols("期初余额", "期末余额", with_reason=False),
            SOE_TOP5_SPECIAL_ROWS,
            SPECIAL_PAYABLE_GUIDANCE
            + "源模板要求分项披露年末余额最大的前五项。"
            "注：列头取附注模版字面（源 xlsx 写的是 `201X.01.01` / `201X.12.31` 年份占位符）。",
        ),
    ]
    text_sections = [
        "### 长期应付款",
        "#### ①长期应付款项期末余额最大的前5 项",
        "### 专项应付款",
        "#### ①专项应付款期末余额最大的前5 项",
        "（注：",
        "（1）应说明专项应付款的来源、指定的专门用途、使用限制等相关内容。"
        "如：该专项应付款为财政部按照XX文规定拨付的X项目专用设备购置款。",
        "（2）企业因城镇整体规划、库区建设、棚户区改造、沉陷区治理等公共利益进行搬迁，"
        "收到政府从财政预算直接拨付的搬迁补偿款，在专项应付款中核算。）",
    ]
    return plan, [main, top5, special], [], text_sections


def plan_l5_soe_within1y() -> tuple[list[dict[str, Any]], list[str], list[str], list[str]]:
    """八、47（3）一年内到期的长期应付款（国企专有章节）。"""
    name = "（3）一年内到期的长期应付款"
    plan = [
        kit.rule(
            name,
            _two_period_cols("期末余额", "期初余额"),
            kit.blanks_then_total(3),
            "勾稽：合计 = 各项之和，且应与 八、53「长期应付款」表的"
            "「减：一年内到期长期应付款项」行金额一致。数据来源 L5-1 审定表。",
        ),
    ]
    return plan, [name], [], []


# ── 章节计划 ─────────────────────────────────────────────────────────────────

def plan_l7_listed() -> tuple[list[dict[str, Any]], list[str], list[str], list[str]]:
    """五、52 其他非流动负债（上市）。"""
    cols = kit.flat_columns([
        ("label", "项目", None),
        ("end_amount", "期末数", AMOUNT),
        ("prior_amount", "上年年末数", AMOUNT),
    ])
    plan = [
        kit.rule(
            "其他非流动负债",
            cols,
            kit.blanks_then_total(5),
            "勾稽：合计 = 各项目之和。源模板为空行骨架（r7~r11），"
            "项目名称按实际性质填列（递延收益 / 长期保证金 / 政府补助等）；"
            "数据来源 L7-1 审定表 / L7-2 明细表。",
            aliases=["项  目", "项目"],
        ),
    ]
    return plan, ["其他非流动负债"], [], []


def plan_l7_soe() -> tuple[list[dict[str, Any]], list[str], list[str], list[str]]:
    """八、57 其他非流动负债（国企）。"""
    # 🔴 2026-08-15 更新：本 spec 裁决 C 推翻原「有意不改」决策，
    # 列序改为与源模板一致（项目/年初余额/期末余额）。
    # key 保持不变（prior_amount 仍是期初、end_amount 仍是期末），只改 label 与数组顺序。
    cols = kit.flat_columns([
        ("label", "项目", None),
        ("prior_amount", "年初余额", AMOUNT),
        ("end_amount", "期末余额", AMOUNT),
    ])
    plan = [
        kit.rule(
            "其他非流动负债",
            cols,
            kit.labels_then_total(["待转销项税额", "合同负债"]),
            "勾稽：合计 = 各项目之和。数据来源 L7-1 审定表 / L7-2 明细表。"
            "列序按源模板（项目/年初余额/期末余额），与上市侧（期末数/上年年末数）相反是源模板事实。",
        ),
    ]
    return plan, ["其他非流动负债"], [], []


def plan_l8_listed() -> tuple[list[dict[str, Any]], list[str], list[str], list[str]]:
    """五、67 财务费用（上市）。"""
    name = "财务费用（按费用性质列示）"
    plan = [
        kit.rule(name, _finance_cost_columns(), _finance_cost_rows(), FINANCE_COST_GUIDANCE),
    ]
    text_sections = [
        "利息资本化金额已计入存货和在建工程。本期用于计算确定借款费用资本化金额的资本化率为XX%（上期：XX%）",
        "【提示：",
        "（1）利息收入主要为银行存款产生的利息收入，以及根据《企业会计准则第14号——收入》的相关规定确认的利息收入。"
        "其他金融资产利息收入在投资收益列示】",
        "（2）企业在销售商品时给予客户的现金折扣，应当按照收入准则中关于可变对价的相关规定进行会计处理，"
        "不应作为财务费用列示。】",
    ]
    return plan, [name], [], text_sections


def plan_l8_soe() -> tuple[list[dict[str, Any]], list[str], list[str], list[str]]:
    """八、68 财务费用（国企）。"""
    name = "财务费用"
    plan = [
        kit.rule(name, _finance_cost_columns(), _finance_cost_rows(), FINANCE_COST_GUIDANCE),
    ]
    text_sections = [
        "【提示：利息收入主要为银行存款产生的利息收入，"
        "以及根据《企业会计准则第14号——收入》的相关规定确认的利息收入。】",
    ]
    return plan, [name], [], text_sections


SECTIONS: dict[str, tuple[Path, str, Any]] = {
    "l5-listed": (LISTED, "五、48", plan_l5_listed),
    "l5-soe": (SOE, "八、53", plan_l5_soe),
    "l5-soe-within1y": (SOE, "八、47", plan_l5_soe_within1y),
    "l7-listed": (LISTED, "五、52", plan_l7_listed),
    "l7-soe": (SOE, "八、57", plan_l7_soe),
    "l8-listed": (LISTED, "五、67", plan_l8_listed),
    "l8-soe": (SOE, "八、68", plan_l8_soe),
}

LABELS = {
    "l5-listed": "五、48 长期应付款（上市，含 L6 专项应付款表）",
    "l5-soe": "八、53 长期应付款（国企，含 L6 专项应付款表）",
    "l5-soe-within1y": "八、47 一年内到期的长期应付款（国企）",
    "l7-listed": "五、52 其他非流动负债（上市）",
    "l7-soe": "八、57 其他非流动负债（国企）",
    "l8-listed": "五、67 财务费用（上市）",
    "l8-soe": "八、68 财务费用（国企）",
}


def run(key: str, dry_run: bool, check: bool) -> tuple[list[str], list[str], list[str]]:
    path, section_number, planner = SECTIONS[key]
    plan, expected, drops, text_sections = planner()
    return kit.run_section(
        path,
        section_number,
        plan,
        expected,
        aligned_by=ALIGNED_BY,
        dry_run=dry_run,
        check=check,
        drops=drops,
        text_sections=text_sections or None,
    )


main = kit.build_cli(__doc__ or "L 循环附注章节结构对齐", run, LABELS)

if __name__ == "__main__":
    raise SystemExit(main())
