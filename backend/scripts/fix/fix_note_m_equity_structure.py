#!/usr/bin/env python
"""幂等修复 M 循环（权益类）附注模板结构。

覆盖章节：
  listed: 五、53 股本 / 五、54 其他权益工具 / 五、56 库存股 /
          五、57 其他综合收益 / 五、60 一般风险准备 / 五、61 未分配利润
  soe:    八、58 实收资本 / 八、59 其他权益工具 / 八、60 资本公积(已对齐-验证) /
          八、61 专项储备(已对齐-验证) / 八、62 盈余公积(已对齐-验证) /
          八、63 未分配利润 / 八、79 归属于母公司OCI
          **八、94 一般风险准备（新建）**

权威来源：`backend/wp_templates/M/*.xlsx` 源模板披露 sheet。

用法：
  python backend/scripts/fix/fix_note_m_equity_structure.py --dry-run
  python backend/scripts/fix/fix_note_m_equity_structure.py --check
  python backend/scripts/fix/fix_note_m_equity_structure.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.fix._note_structure_kit import (  # noqa: E402
    build_cli,
    flat_columns,
    grouped_columns,
    rule,
    run_section,
)

LISTED = Path("backend/data/note_template_listed.json")
SOE = Path("backend/data/note_template_soe.json")
ALIGNED_BY = "fix_note_m_equity_structure"

# ═══════════════════════════════════════════════════════════════════════════════
# 列定义
# ═══════════════════════════════════════════════════════════════════════════════

# ── 五、56 库存股（5 列 flat 标准变动表）──────────────────────────────────────
COLS_M3_LISTED = flat_columns([
    ("label", "项目", None),
    ("begin_amount", "期初余额", "amount"),
    ("increase", "本期增加", "amount"),
    ("decrease", "本期减少", "amount"),
    ("end_amount", "期末余额", "amount"),
])

# ── 五、60 一般风险准备（5 列 flat 变动表）────────────────────────────────────
COLS_M8_LISTED = flat_columns([
    ("label", "项目", None),
    ("begin_amount", "期初余额", "amount"),
    ("increase", "本期增加", "amount"),
    ("decrease", "本期减少", "amount"),
    ("end_amount", "期末余额", "amount"),
])

# ── 五、57 其他综合收益（上市，两级 8 列）──────────────────────────────────
# 源 xlsx R6:R7 merged: A6:A7 项目 rowspan2 / B6:B7 期初余额 rowspan2 /
# C6:G6 本期发生金额 / H6:H7 期末余额 rowspan2
# C7 本期所得税前发生额 / D7 减：前期计入OCI当期转入损益 / E7 减：所得税费用 /
# F7 税后归属于母公司(2) / G7 税后归属于少数股东
COLS_M9_LISTED = grouped_columns(
    ("label", "项目"),
    [
        ("begin_amount", "期初余额", "amount", None),  # rowspan=2 独立列
        ("pre_tax", "本期所得税前发生额", "amount", "本期发生金额"),
        ("transfer_to_pl", "减：前期计入其他综合收益当期转入损益", "amount", "本期发生金额"),
        ("tax_effect", "减：所得税费用", "amount", "本期发生金额"),
        ("after_tax_parent", "税后归属于母公司", "amount", "本期发生金额"),
        ("after_tax_minority", "税后归属于少数股东", "amount", "本期发生金额"),
        ("end_amount", "期末余额", "amount", None),  # rowspan=2 独立列
    ],
)

# ── 八、79 归属于母公司OCI（国企，两级 7 列，双期）──────────────────────────
# 源 xlsx R8:R9: A8:A9 项目 rowspan2 / B8:G8 本期发生额 / H8:M8 上期发生额
# B9 税前金额 / D9 所得税 / F9 税后净额 (各占 2 col 合并)
# 实质 key 用 end/prior 前缀区分双期
COLS_M9_SOE_OCI = grouped_columns(
    ("label", "项目"),
    [
        ("end_pre_tax", "税前金额", "amount", "本期发生额"),
        ("end_tax", "所得税", "amount", "本期发生额"),
        ("end_net", "税后净额", "amount", "本期发生额"),
        ("prior_pre_tax", "税前金额", "amount", "上期发生额"),
        ("prior_tax", "所得税", "amount", "上期发生额"),
        ("prior_net", "税后净额", "amount", "上期发生额"),
    ],
)

# ── 五、53 股本（上市，两级 8 列）──────────────────────────────────────────
# 源 xlsx R6:R7: A6:A7 项目 rowspan2 / B6:B7 期初余额 rowspan2 /
# C6:G6 本期增减（+、-） / H6:H7 期末余额 rowspan2
# C7 发行新股 / D7 送股 / E7 公积金转股 / F7 其他 / G7 小计
COLS_M2_LISTED_STOCK = grouped_columns(
    ("label", "项目"),
    [
        ("begin_amount", "期初余额", "amount", None),
        ("issue_new", "发行新股", "amount", "本期增减（+、-）"),
        ("bonus_shares", "送股", "amount", "本期增减（+、-）"),
        ("reserve_to_shares", "公积金转股", "amount", "本期增减（+、-）"),
        ("other_change", "其他", "amount", "本期增减（+、-）"),
        ("subtotal_change", "小计", "amount", "本期增减（+、-）"),
        ("end_amount", "期末余额", "amount", None),
    ],
)

# ── 八、58 实收资本（国企，两级 7 列）──────────────────────────────────────
# 源 xlsx R6:R7: A6:A7 投资者名称 rowspan2 / B6:C6 年初余额 / D6:D7 本期增加 rowspan2 /
# E6:E7 本期减少 rowspan2 / F6:G6 期末余额
# B7 投资金额 / C7 所占比例(%) / F7 投资金额 / G7 所占比例(%)
COLS_M2_SOE = grouped_columns(
    ("label", "投资者名称"),
    [
        ("begin_amount", "投资金额", "amount", "年初余额"),
        ("begin_ratio", "所占比例（%）", "text", "年初余额"),
        ("increase", "本期增加", "amount", None),
        ("decrease", "本期减少", "amount", None),
        ("end_amount", "投资金额", "amount", "期末余额"),
        ("end_ratio", "所占比例（%）", "text", "期末余额"),
    ],
)

# ── 五、54 其他权益工具（上市，表2 两级 9 列）──────────────────────────────
# 源 xlsx R26:R27: A26:A27 发行在外的金融工具 rowspan2 /
# B26:C26 期初余额 / D26:E26 本期增加 / F26:G26 本期减少 / H26:I26 期末余额
# B27 数量 / C27 账面价值 × 4 组
COLS_M10_LISTED_MOVEMENT = grouped_columns(
    ("label", "发行在外的金融工具"),
    [
        ("begin_qty", "数量", "amount", "期初余额"),
        ("begin_value", "账面价值", "amount", "期初余额"),
        ("increase_qty", "数量", "amount", "本期增加"),
        ("increase_value", "账面价值", "amount", "本期增加"),
        ("decrease_qty", "数量", "amount", "本期减少"),
        ("decrease_value", "账面价值", "amount", "本期减少"),
        ("end_qty", "数量", "amount", "期末余额"),
        ("end_value", "账面价值", "amount", "期末余额"),
    ],
)

# ── 八、59 其他权益工具（国企，两级 9 列，同上市表2 结构）────────────────────
# 源 xlsx R6:R7 完全同形（期初→期末 各 数量·账面价值）
COLS_M10_SOE = COLS_M10_LISTED_MOVEMENT  # 结构完全相同

# ── 五、54 表1 基本情况（10 列 flat）──────────────────────────────────────
COLS_M10_LISTED_BASIC = flat_columns([
    ("label", "发行在外的金融工具", None),
    ("issue_time", "发行时间", "text"),
    ("classification", "会计分类", "text"),
    ("dividend_rate", "股利率或利息率", "text"),
    ("issue_price", "发行价格", "amount"),
    ("quantity", "数量", "amount"),
    ("amount", "金额", "amount"),
    ("maturity", "到期日或续期情况", "text"),
    ("conversion_terms", "转股条件", "text"),
    ("conversion_status", "转换情况", "text"),
])

# ── 五、54 表3 权益工具持有者的相关信息（3 列 flat）──────────────────────────
COLS_M10_LISTED_HOLDERS = flat_columns([
    ("label", "项目", None),
    ("current", "期末余额/本期发生额", "amount"),
    ("prior", "上年年末余额/上期发生额", "amount"),
])
COLS_M6_LISTED = flat_columns([
    ("label", "项目", None),
    ("current", "本期发生额", "amount"),
    ("prior", "上期发生额", "amount"),
    ("ratio", "提取或分配比例", "text"),
])

# ── 八、63 未分配利润（3 列 flat）────────────────────────────────────────────
COLS_M6_SOE = flat_columns([
    ("label", "项目", None),
    ("current", "本期金额", "amount"),
    ("prior", "上期金额", "amount"),
])

# ── 八、94 一般风险准备（5 列 flat，同 M8 上市版）──────────────────────────────
COLS_M8_SOE = flat_columns([
    ("label", "项目", None),
    ("begin_amount", "期初余额", "amount"),
    ("increase", "本期增加", "amount"),
    ("decrease", "本期减少", "amount"),
    ("end_amount", "期末余额", "amount"),
])

# ═══════════════════════════════════════════════════════════════════════════════
# 行集
# ═══════════════════════════════════════════════════════════════════════════════

# M3 库存股行骨架（动态可扩区，只 seed 合计行）
ROWS_M3_LISTED = [{"label": "合计", "row_type": "total"}]

# M8 一般风险准备行骨架（动态区 + 合计）
ROWS_M8 = [{"label": "合计", "row_type": "total"}]

# M6 上市固定行（源 xlsx R7:R20）
ROWS_M6_LISTED = [
    {"label": "调整前上期末未分配利润", "row_type": "data"},
    {"label": "调整期初未分配利润合计数（调增+，调减-）", "row_type": "total"},
    {"label": "调整后期初未分配利润", "row_type": "data"},
    {"label": "加：本期归属于母公司所有者的净利润", "row_type": "data"},
    {"label": "使用盈余公积弥补亏损", "row_type": "data"},
    {"label": "使用资本公积弥补亏损", "row_type": "data"},
    {"label": "其他调整", "row_type": "data"},
    {"label": "减：提取法定盈余公积", "row_type": "data"},
    {"label": "提取任意盈余公积", "row_type": "data"},
    {"label": "提取一般风险准备", "row_type": "data"},
    {"label": "应付普通股股利", "row_type": "data"},
    {"label": "应付其他权益持有者的股利", "row_type": "data"},
    {"label": "转作股本的普通股股利", "row_type": "data"},
    {"label": "期末未分配利润", "row_type": "data"},
]

# M6 国企固定行（源 xlsx R7:R19）
ROWS_M6_SOE = [
    {"label": "上年年末余额", "row_type": "data"},
    {"label": "期初调整金额", "row_type": "data"},
    {"label": "本期期初余额", "row_type": "data"},
    {"label": "本期增加额", "row_type": "data"},
    {"label": "其中：本期净利润转入", "row_type": "data"},
    {"label": "盈余公积弥补亏损转入", "row_type": "data"},
    {"label": "资本公积弥补亏损转入", "row_type": "data"},
    {"label": "其他调整因素", "row_type": "data"},
    {"label": "本期减少额", "row_type": "data"},
    {"label": "其中：本期提取盈余公积数", "row_type": "data"},
    {"label": "本期提取一般风险准备", "row_type": "data"},
    {"label": "本期分配现金股利数", "row_type": "data"},
    {"label": "转增资本", "row_type": "data"},
    {"label": "其他减少", "row_type": "data"},
    {"label": "本期期末余额", "row_type": "data"},
]

# ═══════════════════════════════════════════════════════════════════════════════
# guidance
# ═══════════════════════════════════════════════════════════════════════════════

GUIDANCE_M3 = (
    "源模板 M3 库存股：库存股变动情况及原因、回购本公司股份的原因及对应库存股成本确定方法；"
    "因库存股注销而减少的股本；注销高于/低于对应股本成本的冲减/增加资本公积金额；"
    "库存股转让时转让收入与成本差额的处理；"
    "因实行股权激励回购本公司股份的比例。"
)

GUIDANCE_M8 = (
    "源模板 M8 一般风险准备：一般风险准备变动情况说明。"
    "（适用于金融企业，依照相关金融监管制度计提的一般风险准备。）"
)

GUIDANCE_M6_LISTED = (
    "源模板 M6 未分配利润（上市）：对期初未分配利润进行调整的各项调整原因及金额。"
    "利润分配依据与可供股东分配利润确认方法。"
)

GUIDANCE_M6_SOE = (
    "源模板 M6 未分配利润（国企）：企业应详细披露各项调整原因。"
)

# ═══════════════════════════════════════════════════════════════════════════════
# text_sections
# ═══════════════════════════════════════════════════════════════════════════════

TEXT_M6_SOE = ["注：企业应详细披露各项调整原因。"]

TEXT_M8_LISTED = ["（一般风险准备情况说明）"]

TEXT_M8_SOE = ["说明：一般风险准备的变动情况及原因。"]

# ═══════════════════════════════════════════════════════════════════════════════
# 执行分派
# ═══════════════════════════════════════════════════════════════════════════════

SECTIONS = {
    # ─── listed ───
    "listed-m2-53": ("五、53", LISTED, [
        rule("股本（单位：万股）", COLS_M2_LISTED_STOCK, [{"label": "股份总数", "row_type": "data"}],
             "源模板 M2 股本（上市）：股本变动情况。如果报告期内有增资或减资行为的，应披露验资报告信息。"),
    ]),
    "listed-m10-54": ("五、54", LISTED, [
        rule("参考披露格式：", COLS_M10_LISTED_BASIC, None,
             "源模板 M10 其他权益工具（上市）：期末发行在外的优先股、永续债等其他金融工具的基本情况。",
             aliases=["参考披露格式："]),
        rule("期末发行在外的优先股、永续债等其他金融工具变动情况", COLS_M10_LISTED_MOVEMENT, None,
             "源模板 M10 其他权益工具变动情况（上市）：期初/本期增加/本期减少/期末 各数量·账面价值。"),
        rule("权益工具持有者的相关信息", COLS_M10_LISTED_HOLDERS, None,
             "源模板 M10 权益工具持有者的相关信息（上市）：归属于母公司所有者/少数股东的权益相关信息。",
             aliases=["项  目"]),
    ]),
    "listed-m3-56": ("五、56", LISTED, [
        rule("库存股", COLS_M3_LISTED, ROWS_M3_LISTED, GUIDANCE_M3),
    ]),
    "listed-m9-57": ("五、57", LISTED, [
        rule("资产负债表中归属于母公司的其他综合收益：", COLS_M9_LISTED, None,
             "源模板 M9 其他综合收益（上市）：资产负债表中归属于母公司的其他综合收益。"
             "一、以后不能重分类进损益的 / 二、以后将重分类进损益的 / 合计。",
             aliases=["资产负债表中归属于母公司的其他综合收益："]),
        rule("利润表中归属于母公司的其他综合收益：", COLS_M9_LISTED, None,
             "源模板 M9 其他综合收益（上市）：利润表中归属于母公司的其他综合收益本期发生额。",
             aliases=["利润表中归属于母公司的其他综合收益："]),
    ]),
    "listed-m8-60": ("五、60", LISTED, [
        rule("一般风险准备", COLS_M8_LISTED, ROWS_M8, GUIDANCE_M8, insert=True),
    ]),
    "listed-m6-61": ("五、61", LISTED, [
        rule("未分配利润", COLS_M6_LISTED, ROWS_M6_LISTED, GUIDANCE_M6_LISTED),
    ]),
    # ─── soe ───
    "soe-m2-58": ("八、58", SOE, [
        rule("实收资本", COLS_M2_SOE, [{"label": "合计", "row_type": "total"}],
             "源模板 M2 实收资本（国企）：投资者名称、年初余额（投资金额+占比）、本期增减、期末余额（投资金额+占比）。"
             "动态插行区：按投资者展开。"),
    ]),
    "soe-m10-59": ("八、59", SOE, [
        rule("其他权益工具", COLS_M10_SOE, [{"label": "合计", "row_type": "total"}],
             "源模板 M10 其他权益工具（国企）：期初/本期增加/本期减少/期末 各数量·账面价值。"),
    ]),
    "soe-m6-63": ("八、63", SOE, [
        rule("未分配利润", COLS_M6_SOE, ROWS_M6_SOE, GUIDANCE_M6_SOE),
    ]),
    "soe-m9-79": ("八、79", SOE, [
        rule("其他综合收益各项目及其所得税影响和转入损益情况", COLS_M9_SOE_OCI, None,
             "源模板 M9 其他综合收益（国企）表(1)：其他综合收益各项目及其所得税影响和转入损益情况。"
             "一、以后不能重分类进损益的 / 二、以后将重分类进损益的 / 合计。",
             aliases=["其他综合收益各项目及其所得税影响和转入损益情况"]),
    ]),
    "soe-m8-94": ("八、94", SOE, [
        rule("一般风险准备", COLS_M8_SOE, ROWS_M8, GUIDANCE_M8, insert=True),
    ]),
}

# 每个键对应的预期表名集合
EXPECTED: dict[str, list[str]] = {
    "listed-m2-53": ["股本（单位：万股）"],
    "listed-m10-54": ["参考披露格式：", "期末发行在外的优先股、永续债等其他金融工具变动情况", "权益工具持有者的相关信息"],
    "listed-m3-56": ["库存股"],
    "listed-m9-57": ["资产负债表中归属于母公司的其他综合收益：", "利润表中归属于母公司的其他综合收益："],
    "listed-m8-60": ["一般风险准备"],
    "listed-m6-61": ["未分配利润"],
    "soe-m2-58": ["实收资本"],
    "soe-m10-59": ["其他权益工具"],
    "soe-m6-63": ["未分配利润"],
    "soe-m9-79": ["其他综合收益各项目及其所得税影响和转入损益情况"],
    "soe-m8-94": ["一般风险准备"],
}

# text_sections 覆盖（完整替换）
TEXT_OVERRIDES: dict[str, list[str] | None] = {
    "soe-m6-63": TEXT_M6_SOE,
    "listed-m8-60": TEXT_M8_LISTED,
    "soe-m8-94": TEXT_M8_SOE,
}

LABELS = {
    "listed-m2-53": "[listed] 五、53 股本",
    "listed-m10-54": "[listed] 五、54 其他权益工具",
    "listed-m3-56": "[listed] 五、56 库存股",
    "listed-m9-57": "[listed] 五、57 其他综合收益",
    "listed-m8-60": "[listed] 五、60 一般风险准备",
    "listed-m6-61": "[listed] 五、61 未分配利润",
    "soe-m2-58": "[soe] 八、58 实收资本",
    "soe-m10-59": "[soe] 八、59 其他权益工具",
    "soe-m6-63": "[soe] 八、63 未分配利润",
    "soe-m9-79": "[soe] 八、79 归属于母公司OCI",
    "soe-m8-94": "[soe] 八、94 一般风险准备（新建）",
}


def _ensure_soe_m8_section() -> None:
    """若 note_template_soe.json 里尚无 `八、94` 章节，在正确位置插入空骨架。"""
    import json as _json

    doc = _json.loads(SOE.read_text(encoding="utf-8"))
    secs = doc["sections"]
    for s in secs:
        if (s.get("section_number") or "").replace(" ", "") == "八、94":
            return  # 已存在

    # 找 八、93 的位置，在其后插入
    insert_idx = len(secs)
    for i, s in enumerate(secs):
        if (s.get("section_number") or "").replace(" ", "") == "八、93":
            insert_idx = i + 1
            break

    # 参照邻近章节的字段结构
    new_section = {
        "section_number": "八、94",
        "section_title": "一般风险准备",
        "account_name": "一般风险准备",
        "content_type": "table",
        "tables": [],
        "text_sections": [],
        "check_presets": [],
        "wide_table_presets": [],
        "scope": "both",
        "sort_order": 594,
        "section_id": "chapter-08-cai-wu-bao-biao-xiang-mu-zhu-shi-yi-ban-feng-xian-zhun-bei",
        "level": 2,
        "parent_section_id": "chapter-08-cai-wu-bao-biao-xiang-mu-zhu-shi",
        "sort_index": 93,
        "auto_numbering": True,
        "lock_number": False,
    }
    secs.insert(insert_idx, new_section)
    SOE.write_text(_json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  + 新建章节 八、94 一般风险准备（插入位置 idx={insert_idx}）")


def _run(key: str, dry_run: bool, check: bool):
    import json as _json
    from scripts.fix._note_structure_kit import find_section

    # 新建章节前置（仅对 soe-m8-94 生效，且非 check 模式）
    if key == "soe-m8-94" and not check:
        _ensure_soe_m8_section()

    section_number, path, plan = SECTIONS[key]

    # 前处理：删除 header_label 假行（两级表头重建后旧残留会让 validate 报错阻止写入）
    if not check:
        doc = _json.loads(path.read_text(encoding="utf-8"))
        section = find_section(doc, section_number)
        if section:
            modified = False
            for tbl in section.get("tables") or []:
                rows = tbl.get("rows") or []
                new_rows = [r for r in rows if str(r.get("row_type", "")) != "header_label"]
                if len(new_rows) < len(rows):
                    tbl["rows"] = new_rows
                    modified = True
            if modified:
                path.write_text(_json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    expected = EXPECTED[key]
    text = TEXT_OVERRIDES.get(key)
    return run_section(
        path,
        section_number,
        plan,
        expected,
        aligned_by=ALIGNED_BY,
        dry_run=dry_run,
        check=check,
        text_sections=text,
    )


main = build_cli(
    "M 循环（权益类）附注模板结构幂等修复",
    _run,
    LABELS,
)

if __name__ == "__main__":
    sys.exit(main())
