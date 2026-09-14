#!/usr/bin/env python
"""附注 H7 生产性生物资产章节结构重建（幂等）。

源模板 `backend/wp_templates/H/H7 生产性生物资产.xlsx`。

**上市 §五、24**（`附注披露信息（上市公司）`）—— 两张**列转置 + 两级表头**表，
openpyxl 合并区实证（表1 `A9:A10` / `B9:C9` / `D9:E9` / `F9:G9` / `H9:I9` / `J9:J10`；
表2 R51:R52 同构）：

- 列 = 项目（rowspan 2）+ 4 产业（各下辖 `类别` + `……` 两子列）+ 合计（rowspan 2）
- 表1「（1）以成本计量」R11–R44 = **34 行四层**
- 表2「（2）以公允价值计量」R53–R64 = **11 行**（R61 源模板留白）

欠账：①第 2 张表名是表头首格泄漏 `项  目`（应为「（2）以公允价值计量」）
②两表各残留 1 个 `row_type=header_label` 假行 ③两表 `columns=0` 无 guidance。

**国企 §八、24**（`附注披露信息（国有企业）` —— 注意是「国有企业」，与 H9/H10 的「国企」
不同）—— 两张 5 列单级表，行 = 4 产业 + 每产业「其中：N．」可扩类别行 + 合计。

欠账：①两表 `columns=0` 无 guidance ②两表各 4 个 `……` 纯占位行
③`text_sections` 漏源模板 R39「注：应披露公允价值确认依据。」、R40 丢了「（3）」前缀。

🔴 **`……` 两种语义相反**：
- 作**列头**（R10/R52）永远收不到数据 → 丢弃，改为可增删的类别列
- 作**行**（上市表1 R20/R30/R40、表2 R58/R63）是真实可扩明细行且参与所属小计 → **保留**
- 国企的 `……`（R11/R14/R17/R20）是**行形态的「可继续加行」标记**，在动态类别行模型下
  每个类别行都有真实名称 → seed 删除（与上市那五处**有模型键**的可扩明细行不同）

🔴 上市第 2 表改名走 `rule(aliases=['项  目'])`，**绝不进 `drop_tables`**
（drop 在 `apply_plan` 之前执行，会把该表连行一起删掉，H2 已踩）。

Usage::

    python backend/scripts/fix/fix_note_h7_biological_assets_structure.py --dry-run
    python backend/scripts/fix/fix_note_h7_biological_assets_structure.py
    python backend/scripts/fix/fix_note_h7_biological_assets_structure.py --check

spec: .kiro/specs/h7-biological-assets-disclosure-rebuild/ (Task 5)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _note_structure_kit import (  # noqa: E402
    AMOUNT,
    build_cli,
    data_row,
    flat_columns,
    grouped_columns,
    rule,
    run_section,
    total_row,
)

_BACKEND = Path(__file__).resolve().parent.parent.parent
DATA_DIR = _BACKEND / "data"
LISTED_PATH = DATA_DIR / "note_template_listed.json"
SOE_PATH = DATA_DIR / "note_template_soe.json"

LISTED_SECTION = "五、24"
SOE_SECTION = "八、24"
ALIGNED_BY = "h7-biological-assets-disclosure-rebuild"

# ── 表名 ────────────────────────────────────────────────────────────────
T_LISTED_COST = "（1）以成本计量"
T_LISTED_FAIR = "（2）以公允价值计量"
T_SOE_COST = "以成本计量"
T_SOE_FAIR = "以公允价值计量"
LEAKED = "项  目"  # 上市第 2 表的表头首格泄漏名

# ── 上市列（两级：项目 rowspan2 + 4 产业各 1 个默认类别列 + 合计 rowspan2）──────
# 叶子列名取源模板 R10 字面 `类别`（占位，审计师改成实际类别名）；
# key 用稳定 `{industryKey}_{seq}`（四个产业默认叶子名相同，用 label 作 key 会撞键）
_INDUSTRIES = (
    ("crop", "种植业"),
    ("livestock", "畜牧养殖业"),
    ("forestry", "林业"),
    ("aquatic", "水产业"),
)
_CATEGORY_LEAF = "类别"

LISTED_COLUMNS = grouped_columns(
    ("label", "项目"),
    [(f"{k}_1", _CATEGORY_LEAF, AMOUNT, label) for k, label in _INDUSTRIES]
    + [("total", "合计", AMOUNT, None)],
)

# ── 国企列（5 列单级 → 必须 flat）─────────────────────────────────────────
SOE_COLUMNS = flat_columns([
    ("label", "项目", None),
    ("begin", "期初账面价值", AMOUNT),
    ("increase", "本期增加额", AMOUNT),
    ("decrease", "本期减少额", AMOUNT),
    ("end", "期末账面价值", AMOUNT),
])

# ── 行集 ────────────────────────────────────────────────────────────────
# 上市表1：源 xlsx R11–R44 共 34 行四层（`……` 行是可扩明细行，保留）
LISTED_COST_ROW_LABELS = [
    "一、账面原值",
    "1.期初余额",
    "2.本期增加金额", "（1）外购", "（2）自行培育", "（3）其他增加",
    "3.本期减少金额", "（1）处置", "（2）其他", "……",
    "4.期末余额",
    "二、累计折旧",
    "1.期初余额",
    "2.本期增加金额", "（1）计提", "（2）其他增加",
    "3.本期减少金额", "（1）处置", "（2）其他", "……",
    "4.期末余额",
    "三、减值准备",
    "1.期初余额",
    "2.本期增加金额", "（1）计提", "（2）其他增加",
    "3.本期减少金额", "（1）处置", "（2）其他", "……",
    "4.期末余额",
    "四、账面价值",
    "1.期末账面价值",
    "2.期初账面价值",
]

# 上市表2：源 xlsx R53–R64 共 11 行（R61 源模板留白）
LISTED_FAIR_ROW_LABELS = [
    "一、期初余额",
    "二、本期变动",
    "加：外购", "自行培育", "企业合并增加", "……",
    "减：处置", "其他转出",
    "公允价值变动", "……",
    "三、期末余额",
]

# 国企：4 产业 + 每产业 1 个类别槽位 + 合计（源 13 行里 4 个 `……` 占位行删除 → 9 行）
_SOE_INDUSTRY_LABELS = ("一、种植业", "二、畜牧养殖业", "三、林业", "四、水产业")
_SOE_CATEGORY_SEED = "其中：1．"


def _listed_rows(labels: list[str]) -> list[dict[str, Any]]:
    return [data_row(x) for x in labels]


def _soe_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ind in _SOE_INDUSTRY_LABELS:
        rows.append(data_row(ind))
        rows.append(data_row(_SOE_CATEGORY_SEED))
    rows.append(total_row("合计"))
    return rows


# ── guidance ────────────────────────────────────────────────────────────
_G_LISTED_COST = (
    "以成本计量的生产性生物资产变动表（源模板 R9–R44）：两级表头 —— 列为 项目 + "
    "种植业 / 畜牧养殖业 / 林业 / 水产业（每个产业下按实际类别分列，可增删列并改列名，"
    "源模板首列表头占位为「类别」）+ 合计；行为四层结构 —— "
    "一、账面原值 / 二、累计折旧 / 三、减值准备 / 四、账面价值，"
    "各层含 期初余额 + 本期增加金额{分项} + 本期减少金额{分项 + 「……」可扩明细行} + 期末余额。"
    "勾稽：本期增加（减少）金额 = 其分项之和；期末余额 = 期初余额 + 本期增加金额 − 本期减少金额；"
    "四、账面价值 1.期末账面价值 = 账面原值期末 − 累计折旧期末 − 减值准备期末，2.期初账面价值 同口径；"
    "合计列 = 各类别列之和；本表账面价值合计应与审定表 H7-1（成本模式）审定数一致。"
    "【长期资产本期进行减值测试的，应披露可收回金额的具体确定方法。可收回金额按公允价值减去处置费用后的"
    "净额确定的，应披露公允价值和处置费用的确定方式、关键参数及其确定依据。可收回金额按预计未来现金流量的"
    "现值确定的，应披露预测期的年限、预测期及稳定期的关键参数及其确定依据。（15号文第十九条（十九））"
    "注意：本年执行减值测试的，即使未计提减值，也要参照上述要求披露。】"
    "数据来源：审定表 H7-1（成本模式）/ 明细表 H7-2（成本模式）/ 折旧测算表 H7-11 / 减值测算表 H7-15。"
)

_G_LISTED_FAIR = (
    "以公允价值计量的生产性生物资产变动表（源模板 R51–R64）：两级表头与成本模式表同构。"
    "行为 一、期初余额 / 二、本期变动{加：外购、自行培育、企业合并增加、「……」；"
    "减：处置、其他转出；公允价值变动、「……」} / 三、期末余额。"
    "勾稽：二、本期变动 = 加项之和 − 减项之和 + 公允价值变动 + 其他变动；"
    "三、期末余额 = 一、期初余额 + 二、本期变动；合计列 = 各类别列之和；"
    "期末余额合计应与审定表 H7-1（公允价值模式）审定数一致。"
    "公允价值模式须披露公允价值层级（L1/L2/L3）、估值技术与关键参数（在本节说明文字中披露）。"
    "数据来源：审定表 H7-1（公允价值模式）/ 明细表 H7-2（公允价值模式）/ 公允价值复核表 H7-13。"
)

_G_SOE_BASE = (
    "行为 4 个产业（一、种植业 / 二、畜牧养殖业 / 三、林业 / 四、水产业）+ 每个产业下"
    "以「其中：N．」列示的具体类别（按被审计单位实际情况增删行）+ 合计。"
    "勾稽：期末账面价值 = 期初账面价值 + 本期增加额 − 本期减少额；"
    "产业行 = 其下各类别行之和（无类别明细时直接填列产业行）；合计行 = 4 个产业行之和。"
)

_G_SOE_COST = (
    "以成本计量的生产性生物资产（源模板 R8–R21）：" + _G_SOE_BASE
    + "另需披露：①各类生物资产的期末实物数量，如有天然起源的生物资产，还应披露该资产的类别、"
    "取得方式和数量等；②各类生产性生物资产的预计使用寿命、预计净残值、折旧方法、累计折旧和"
    "减值准备累计金额（在本节说明文字中披露）。"
    "本表合计应与审定表 H7-1（成本模式）审定数一致。"
    "数据来源：审定表 H7-1 / 明细表 H7-2 / 折旧测算表 H7-11 / 减值测算表 H7-15。"
)

_G_SOE_FAIR = (
    "以公允价值计量的生产性生物资产（源模板 R25–R38）：" + _G_SOE_BASE
    + "另需披露公允价值确认依据，以及生产性生物资产相关的风险情况与管理措施"
    "（在本节说明文字中披露）。本表合计应与审定表 H7-1（公允价值模式）审定数一致。"
    "数据来源：审定表 H7-1 / 明细表 H7-2 / 公允价值复核表 H7-13。"
)

# ── text_sections（整表替换；正文段禁带 `#`，表标题用 `#### `）─────────────
LISTED_TEXT_SECTIONS = [
    "（有公益性生物资产的企业，应增设“公益性生物资产”项目，列在“生产性生物资产”项目之后）",
    f"#### {T_LISTED_COST}",
    "【长期资产本期进行减值测试的，应披露可收回金额的具体确定方法。可收回金额按公允价值减去处置费用后的"
    "净额确定的，应披露公允价值和处置费用的确定方式、关键参数及其确定依据。可收回金额按预计未来现金流量的"
    "现值确定的，应披露预测期的年限、预测期及稳定期的关键参数及其确定依据。前述信息与以前年度减值测试采用的"
    "信息或外部信息明显不一致的，或公司以前年度减值测试采用信息与当年实际情况明显不一致的，应披露差异原因。"
    "（15号文第十九条（十九）】",
    "注意：本年执行减值测试的，即使未计提减值，也要参照上述要求披露。",
    "（提示：如有天然起源的生物资产，还应披露该资产的类别、取得方式和数量等。各类生产性生物资产的预计"
    "使用寿命、预计净残值、折旧方法、累计折旧和减值准备累计金额。与生物资产相关的风险情况与管理措施。）",
    f"#### {T_LISTED_FAIR}",
]

SOE_TEXT_SECTIONS = [
    f"#### {T_SOE_COST}",
    "①各类生物资产的期末实物数量，如有天然起源的生物资产，还应披露该资产的类别、取得方式和数量等。",
    "②各类生产性生物资产的预计使用寿命、预计净残值、折旧方法、累计折旧和减值准备累计金额。）",
    f"#### {T_SOE_FAIR}",
    # 源模板 R39，模板 JSON 原本整段缺失
    "注：应披露公允价值确认依据。",
    # 源模板 R40，模板 JSON 原本丢了「（3）」前缀（全长 24 字 > 20，不会被当标题丢弃）
    "（3）说明生产性生物资产相关的风险情况与管理措施。",
]


def _listed_plan() -> list[dict[str, Any]]:
    return [
        rule(T_LISTED_COST, LISTED_COLUMNS, _listed_rows(LISTED_COST_ROW_LABELS), _G_LISTED_COST),
        rule(
            T_LISTED_FAIR,
            [dict(c) for c in LISTED_COLUMNS],
            _listed_rows(LISTED_FAIR_ROW_LABELS),
            _G_LISTED_FAIR,
            aliases=[LEAKED],
        ),
    ]


def _soe_plan() -> list[dict[str, Any]]:
    return [
        rule(T_SOE_COST, SOE_COLUMNS, _soe_rows(), _G_SOE_COST),
        rule(T_SOE_FAIR, [dict(c) for c in SOE_COLUMNS], _soe_rows(), _G_SOE_FAIR),
    ]


EXPECTED = {
    "listed": [T_LISTED_COST, T_LISTED_FAIR],
    "soe": [T_SOE_COST, T_SOE_FAIR],
}

_TARGETS: dict[str, tuple[Path, str, Any, list[str]]] = {
    "listed": (LISTED_PATH, LISTED_SECTION, _listed_plan, LISTED_TEXT_SECTIONS),
    "soe": (SOE_PATH, SOE_SECTION, _soe_plan, SOE_TEXT_SECTIONS),
}

_LABELS = {
    "listed": "note_template_listed.json §五、24 生产性生物资产（上市）",
    "soe": "note_template_soe.json §八、24 生产性生物资产（国企）",
}


def _runner(key: str, dry_run: bool, check: bool):
    path, section_number, plan_fn, text_sections = _TARGETS[key]
    return run_section(
        path,
        section_number,
        plan_fn(),
        EXPECTED[key],
        aligned_by=ALIGNED_BY,
        dry_run=dry_run,
        check=check,
        # 🔴 不传 drops —— `项  目` 只能靠 rule(aliases=[...]) 改名。
        # drop_tables 在 apply_plan **之前**执行，进 drops 会把该表连行一起删掉。
        text_sections=text_sections,
    )


main = build_cli("附注 H7 生产性生物资产章节结构重建（幂等）", _runner, _LABELS)

if __name__ == "__main__":
    raise SystemExit(main())
