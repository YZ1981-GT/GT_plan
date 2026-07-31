#!/usr/bin/env python
"""附注 K 系复杂类章节结构对齐（批 3：K1 其他应收款 / K6 持有待售资产和负债）—— 幂等。

覆盖 5 个章节（K6 国企拆资产/负债两节）：

| 键          | 文件                      | 章节   | 科目                       |
|-------------|---------------------------|--------|----------------------------|
| k1-listed   | note_template_listed.json | 五、8  | 其他应收款                 |
| k1-soe      | note_template_soe.json    | 八、9  | 其他应收款                 |
| k6-listed   | note_template_listed.json | 五、11 | 持有待售资产和持有待售负债 |
| k6-soe      | note_template_soe.json    | 八、12 | 持有待售资产               |
| k6-soe-liab | note_template_soe.json    | 八、43 | 持有待售负债               |

裁决顺序（平台铁律）：源 xlsx `backend/wp_templates/K/{K1,K6}*.xlsx` 的披露 sheet
> 附注模版列结构 > 校验预设。**附注是交付物** → 列结构随附注模版；底稿可多留审计列，
但同步时必须投影成附注形状。

修掉的实质欠账（全部经 openpyxl 读源 xlsx + 模板 JSON 双向实证）：

K1（§五、8 十八表 / §八、9 十九表）
  1. **37 张表全部 `columns` 缺失** → `_extract_column_groups` 返回 `None`，后端退化到
     `_infer_groups_from_headers` **前缀推断**，对「期末账面余额/期末坏账准备/…」这种
     带期别前缀的表头会凭空造出父表头；同时契约 P3「必须在 group / flat 之间表态」不满足。
  2. **两级表头被压扁成带前缀的单级**（源 xlsx 有跨列合并：上市 `B22:D22`/`E22:G22`；
     国企 `B19:F19`+`B20:C20`+`D20:E20`、`B46:D46`/`E46:G46` 等）→ 现在显式声明
     `group` + **叶子列名**，`key` 保持既有中文键不变（不动同步载荷的数据键）。
  3. **4 处 `header_label` 假数据行**（压扁的第二行表头残留：上市 `本期计提、收回或转回的
     坏账准备情况`；国企 `坏账准备计提情况` / `其他应收款项坏账准备计提情况` /
     `其他应收款项账面余额变动`）→ 会渲染成一行空披露数据。
  4. **占位说明行**（上市 `可无限量添加行` ×2、国企 `……` ×4）→ 改空白录入行骨架。
  5. **国企裸续表名 `续：`** → 正名「按坏账准备计提方法分类披露其他应收款项（续：期初余额）」。
     裸续表名跨章节撞键；同步侧 `K1_SOE_SUBTABLE.methodPrior` 必须同步改（否则立刻孤儿表）。
  6. **三阶段快照 6 表缺第 6 列「理由」**（源 xlsx `F32`/`F41`/`F51`/`F63`/`F72`/`F82`）——
     底稿与同步映射早已有该列，只有附注模板漏了 → 列头对不上、数据无落点。
     ECL 率列**标签按阶段不同**（第一阶段 = 未来 12 个月内；第二/三阶段 = 整个存续期），
     `key` 统一 `预期信用损失率`（既有映射真源）。

K6（§五、11 / §八、12 / §八、43）
  7. **上市 6 张表里 5 张是垃圾名**（`期末，持有待售资产的情况：` 是 A44 段落文本泄漏；
     `子公司A` / `分公司B` 是示例处置组名；`项  目` 是表头首格泄漏），且 `tables[1]`
     **名（持有待售资产减值准备）与内容（持有待售负债行）整体错位一位**。
  8. **主表两级表头 6 列被压扁成 3 列**（源 xlsx 上市 `B6:D6`=期末数 / `E6:G6`=上年年末数；
     国企 `B9:D9`=期末数 / `E9:G9`=期初数，子列均为 账面余额/减值准备/账面价值）——
     模板只剩 `['项目','期末余额','上年年末余额']`，而同步映射 `buildK6ListedColumns()`
     早已是 7 列两级 → 模板与载荷列数不符。
  9. **减值准备表缺「本期减少」二级拆分**（源 xlsx `D32:E32` 合并 = 本期减少，下辖
     `本期转回` / `本期出售`）→ 模板压成单列「本期减少」。
 10. **11 张表 `guidance` 全缺** + 占位行 `……`/`子公司A`/`分公司B` + `header_label` 假行。

用法::

    python backend/scripts/fix/fix_note_k_complex_structure.py --dry-run
    python backend/scripts/fix/fix_note_k_complex_structure.py
    python backend/scripts/fix/fix_note_k_complex_structure.py --check
    python backend/scripts/fix/fix_note_k_complex_structure.py --only k6-listed

spec: .kiro/specs/k-cycle-disclosure-alignment/ 批 3 Task 11
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _note_structure_kit import (  # noqa: E402
    AMOUNT,
    TEXT,
    blanks_then_total,
    build_cli,
    data_row,
    derive_column_groups,  # re-export：守卫测试按同口径复算 `_column_groups`
    flat_columns,
    grouped_columns,
    labels_then_total,
    missing_text_sections,  # re-export：守卫测试查 ⑧⑨⑩ 说明段是否齐备
    rule,
    run_section,
    subtotal_row,
    total_row,
    validate_section,  # re-export：守卫测试做反向自检
)

__all__ = [
    "derive_column_groups",
    "missing_text_sections",
    "validate_section",
    "main",
]

REPO = Path(__file__).resolve().parents[3]
LISTED = REPO / "backend" / "data" / "note_template_listed.json"
SOE = REPO / "backend" / "data" / "note_template_soe.json"

ALIGNED_BY = "fix_note_k_complex_structure"

#: 传给 `rule(guidance=...)` 表示「保留模板现有 guidance」（K1 全表已有，不churn 文案）
KEEP = ""


def _cols(pairs: list[tuple[str, str, str | None]]) -> list[dict[str, Any]]:
    """单级表头：`(key, label, format)`。"""
    return flat_columns(pairs)


# ═══════════════════════════════════════════════════════════════════════
# K1 上市 §五、8
# ═══════════════════════════════════════════════════════════════════════

#: 三阶段快照表列（源 xlsx A32:F39 等；第 6 列「理由」附注模板原缺）
def _stage_cols(rate_label: str) -> list[dict[str, Any]]:
    return _cols([
        ("label", "类别", None),
        ("账面余额", "账面余额", AMOUNT),
        ("预期信用损失率", rate_label, TEXT),
        ("坏账准备", "坏账准备", AMOUNT),
        ("账面价值", "账面价值", AMOUNT),
        ("理由", "理由", TEXT),
    ])


_RATE_12M = "未来12个月内的预期信用损失率(%)"
_RATE_LIFETIME = "整个存续期预期信用损失率（%）"

#: 三阶段快照表行骨架（源 xlsx 单项 2 行 + 组合 2 行；`_source=workpaper` 时由载荷整表覆盖）
_STAGE_ROWS = [
    data_row("按单项计提坏账准备"),
    data_row("其他应收款单位1"),
    data_row("其他应收款单位2"),
    data_row("按组合计提坏账准备【注意：与会计政策中披露的组合保持一致】"),
    data_row("备用金"),
    data_row("保证金、押金"),
    total_row("合计"),
]

#: 三阶段变动表列 —— **国企侧**单级 5 列。
#: 源 xlsx 国企 `A63:E63` / `A77:E77` 是**一行表头**，阶段释义与阶段名写在同一格里
#: （`B63 = 第一阶段未来12个月预期信用损失`），故国企侧确为 `flat`。
def _movement_cols(label_header: str) -> list[dict[str, Any]]:
    return _cols([
        ("label", label_header, None),
        ("第一阶段", "第一阶段", AMOUNT),
        ("第二阶段", "第二阶段", AMOUNT),
        ("第三阶段", "第三阶段", AMOUNT),
        ("合计", "合计", AMOUNT),
    ])


#: 三阶段变动表列 —— **上市侧**两级混合分组。
#:
#: 🔴 源 xlsx 上市 `A91:E92` 是**两行表头**（`A91:A92` 与 `E91:E92` 纵向合并 = rowspan=2；
#: `B91/C91/D91` 是阶段名，`B92/C92/D92` 是各阶段的 ECL 释义）→ 模板原先压成单级 5 列，
#: 第二行的释义整行丢失。现按 `methodColumns()` 同款混合分组落法：
#:   * 标签列 `坏账准备` 与 `合计` **不带 group**（rowspan=2）
#:   * 标签列**不打 `flat`** —— 打了 `_extract_column_groups` 会返回 `[]` 判为显式单级
#:   * `key` 保持既有中文数据键（`第一阶段` 等），只改 `label` + 加 `group`，
#:     同步载荷行对象就是这些键，改 key 会让整表数据丢落点
_STAGE1_ECL_DESC = "未来12个月预期信用损失"
_STAGE2_ECL_DESC = "整个存续期预期信用损失(未发生信用减值)"
_STAGE3_ECL_DESC = "整个存续期预期信用损失(已发生信用减值)"


def _listed_movement_cols(label_header: str) -> list[dict[str, Any]]:
    return grouped_columns(
        ("label", label_header),
        [
            ("第一阶段", _STAGE1_ECL_DESC, AMOUNT, "第一阶段"),
            ("第二阶段", _STAGE2_ECL_DESC, AMOUNT, "第二阶段"),
            ("第三阶段", _STAGE3_ECL_DESC, AMOUNT, "第三阶段"),
            ("合计", "合计", AMOUNT, None),
        ],
    )


_ECL_MOVEMENT_ROWS = [
    data_row("期初余额"),
    data_row("期初余额在本期"),
    data_row("--转入第二阶段"),
    data_row("--转入第三阶段"),
    data_row("--转回第二阶段"),
    data_row("--转回第一阶段"),
    data_row("本期计提"),
    data_row("本期转回"),
    data_row("本期转销"),
    data_row("本期核销"),
    data_row("其他变动"),
    total_row("期末余额"),
]

#: 国企侧变动表用全角破折号（源 xlsx A66「—转入第二阶段」）
_ECL_MOVEMENT_ROWS_SOE = [
    data_row("期初余额"),
    data_row("期初余额在本期"),
    data_row("—转入第二阶段"),
    data_row("—转入第三阶段"),
    data_row("—转回第二阶段"),
    data_row("—转回第一阶段"),
    data_row("本期计提"),
    data_row("本期转回"),
    data_row("本期转销"),
    data_row("本期核销"),
    data_row("其他变动"),
    total_row("期末余额"),
]

_BALANCE_MOVEMENT_ROWS_SOE = [
    data_row("期初余额"),
    data_row("期初余额在本期"),
    data_row("—转入第二阶段"),
    data_row("—转入第三阶段"),
    data_row("—转回第二阶段"),
    data_row("—转回第一阶段"),
    data_row("本期新增"),
    data_row("本期终止确认"),
    data_row("其他变动"),
    total_row("期末余额"),
]

K1_LISTED_PLAN: list[dict[str, Any]] = [
    rule(
        "其他应收款",
        _cols([("label", "项目", None), ("期末余额", "期末余额", AMOUNT),
               ("上年年末余额", "上年年末余额", AMOUNT)]),
        labels_then_total(["应收利息", "应收股利", "其他应收款"]),
        KEEP,
    ),
    rule(
        "应收利息分类",
        _cols([("label", "项目", None), ("期末余额", "期末余额", AMOUNT),
               ("上年年末余额", "上年年末余额", AMOUNT)]),
        [data_row("定期存款"), data_row("委托贷款"), data_row("债券投资"), data_row("其他"),
         subtotal_row("小计"), data_row("减：坏账准备"), total_row("合计")],
        KEEP,
    ),
    rule(
        "重要逾期利息",
        _cols([("label", "借款单位", None), ("期末余额", "期末余额", AMOUNT),
               ("逾期时间（月）", "逾期时间（月）", TEXT), ("逾期原因", "逾期原因", TEXT),
               ("是否发生减值及其判断依据", "是否发生减值及其判断依据", TEXT)]),
        blanks_then_total(3),
        KEEP,
    ),
    rule(
        "应收股利",
        _cols([("label", "项目（或被投资单位）", None), ("期末余额", "期末余额", AMOUNT),
               ("上年年末余额", "上年年末余额", AMOUNT)]),
        [data_row(), data_row(), subtotal_row("小计"), data_row("减：坏账准备"),
         total_row("合计")],
        KEEP,
    ),
    rule(
        "重要的账龄超过1年的应收股利",
        _cols([("label", "项目（或被投资单位）", None), ("期末余额", "期末余额", AMOUNT),
               ("账龄", "账龄", TEXT), ("未收回的原因", "未收回的原因", TEXT),
               ("是否发生减值及其判断依据", "是否发生减值及其判断依据", TEXT)]),
        blanks_then_total(3),
        KEEP,
    ),
    # 🔴 行骨架按源 xlsx `A8:A20` = **5 年段 6 档**（原模板只有 3 年段，缺
    # `3至4年`/`4至5年`/`5年以上`）。`_source=workpaper` 时由载荷整表覆盖（账龄段跟随
    # 项目 `useAgingConfig` 配置），此处 seed 取源模板默认口径（K1 默认 FIVE_YEAR）。
    rule(
        "按账龄披露",
        _cols([("label", "账龄", None), ("期末余额", "期末余额", AMOUNT),
               ("上年年末余额", "上年年末余额", AMOUNT)]),
        [data_row("1年以内"), data_row("其中：0-X个月"), data_row("X-Y个月"),
         subtotal_row("1年以内小计："), data_row("1至2年"), data_row("2至3年"),
         data_row("3至4年"), data_row("4至5年"), data_row("5年以上"),
         subtotal_row("小计"), data_row("减：坏账准备"),
         total_row("合计")],
        KEEP,
    ),
    # 源 xlsx A22:G28 —— B22:D22「期末数」/ E22:G22「上年年末数」跨列合并 = 真两级表头。
    # 附注模版的父表头用「金额」（期末金额 / 上年年末金额）→ 交付物口径优先；
    # `key` 保留既有带前缀的中文数据键（同步载荷行对象就是这些键，改 key 会丢数据）。
    rule(
        "按款项性质披露",
        grouped_columns(
            ("label", "项  目"),
            [
                ("期末账面余额", "账面余额", AMOUNT, "期末金额"),
                ("期末坏账准备", "坏账准备", AMOUNT, "期末金额"),
                ("期末账面价值", "账面价值", AMOUNT, "期末金额"),
                ("上年年末账面余额", "账面余额", AMOUNT, "上年年末金额"),
                ("上年年末坏账准备", "坏账准备", AMOUNT, "上年年末金额"),
                ("上年年末账面价值", "账面价值", AMOUNT, "上年年末金额"),
            ],
        ),
        [data_row("备用金"), data_row("保证金、押金"), data_row(), data_row(),
         total_row("合计")],
        KEEP,
    ),
    rule("期末处于第一阶段的坏账准备", _stage_cols(_RATE_12M), list(_STAGE_ROWS), KEEP),
    rule("期末处于第二阶段的坏账准备", _stage_cols(_RATE_LIFETIME), list(_STAGE_ROWS), KEEP),
    rule("期末处于第三阶段的坏账准备", _stage_cols(_RATE_LIFETIME), list(_STAGE_ROWS), KEEP),
    rule("上年年末处于第一阶段的坏账准备", _stage_cols(_RATE_12M), list(_STAGE_ROWS), KEEP),
    rule("上年年末处于第二阶段的坏账准备", _stage_cols(_RATE_LIFETIME), list(_STAGE_ROWS), KEEP),
    rule("上年年末处于第三阶段的坏账准备", _stage_cols(_RATE_LIFETIME), list(_STAGE_ROWS), KEEP),
    rule(
        "本期计提、收回或转回的坏账准备情况",
        _listed_movement_cols("坏账准备"),
        list(_ECL_MOVEMENT_ROWS),
        KEEP,
    ),
    rule(
        "本期转回或收回金额重要的坏账准备",
        _cols([("label", "单位名称", None), ("转回原因", "转回原因", TEXT),
               ("收回方式", "收回方式", TEXT),
               ("原确定坏账准备的依据", "原确定坏账准备的依据", TEXT),
               ("转回或收回金额", "转回或收回金额", AMOUNT)]),
        blanks_then_total(3),
        KEEP,
    ),
    rule(
        "本期实际核销的其他应收款情况",
        _cols([("label", "项目", None), ("核销金额", "核销金额", AMOUNT)]),
        [data_row("实际核销的其他应收款")],
        KEEP,
    ),
    rule(
        "重要的其他应收款核销情况（逐项披露）",
        _cols([("label", "单位名称", None), ("其他应收款性质", "其他应收款性质", TEXT),
               ("核销金额", "核销金额", AMOUNT), ("核销原因", "核销原因", TEXT),
               ("履行的核销程序", "履行的核销程序", TEXT),
               ("是否由关联交易产生", "是否由关联交易产生", TEXT)]),
        blanks_then_total(3),
        KEEP,
    ),
    rule(
        "按欠款方归集的其他应收款期末余额前五名单位情况",
        _cols([("label", "单位名称", None), ("款项性质", "款项性质", TEXT),
               ("其他应收款期末余额", "其他应收款期末余额", AMOUNT), ("账龄", "账龄", TEXT),
               ("占其他应收款期末余额合计数的比例(%)",
                "占其他应收款期末余额合计数的比例(%)", TEXT),
               ("坏账准备期末余额", "坏账准备期末余额", AMOUNT)]),
        blanks_then_total(5),
        KEEP,
    ),
    # ── 以下 3 张源模板有、模板 JSON 整张缺失（insert=True） ────────────────
    # 国企侧 §八、9 三张都在（`涉及政府补助的应收款项` / `由金融资产转移而终止确认的…` /
    # `…转移继续涉入形成的资产、负债的金额`），上市侧却一张都没有 —— 两版本不对称。
    # 源 xlsx 上市 ⑧`A136:E141` / ⑨`A146:D150` / ⑩`A153:B159` 明确列在其他应收款披露内。
    rule(
        "应收政府补助情况",
        _cols([("label", "单位名称（注：政府补助的发文单位）", None),
               ("政府补助项目名称", "政府补助项目名称", TEXT),
               ("期末余额", "期末余额", AMOUNT), ("账龄", "账龄", TEXT),
               ("预计收取的时间、金额及依据", "预计收取的时间、金额及依据", TEXT)]),
        blanks_then_total(3),
        "（信息披露解释性公告2号：对于报告期末按应收金额确认的政府补助，应按补助单位和"
        "补助项目**逐项**披露应收款项的期末余额、账龄以及预计收取的时间、金额及依据；"
        "未能在预计时点收到预计金额的，应披露原因。）确认应收款项时应履行重大业务咨询程序。",
        insert=True,
    ),
    rule(
        "因金融资产转移而终止确认的其他应收款情况",
        _cols([("label", "项  目", None), ("转移方式", "转移方式", TEXT),
               ("终止确认金额", "终止确认金额", AMOUNT),
               ("与终止确认相关的利得或损失", "与终止确认相关的利得或损失", AMOUNT)]),
        blanks_then_total(3),
        "【因金融资产转移而终止确认的应收款项，应列示金融资产转移的方式、终止确认的"
        "应收款项金额，及与终止确认相关的利得或损失。】",
        insert=True,
    ),
    rule(
        "转移其他应收款且继续涉入形成的资产、负债的金额",
        _cols([("label", "项  目", None), ("期末数", "期末数", AMOUNT)]),
        [data_row("资产："), data_row(), subtotal_row("资产小计"),
         data_row("负债："), data_row(), subtotal_row("负债小计")],
        "【转移应收款项且继续涉入的，应披露资产转移方式、分项列示继续涉入形成的资产、"
        "负债的金额。】说明中披露资产转移方式；未全部终止确认的被转移金融资产与相关负债"
        "之间的关系；已终止确认的金融资产继续涉入的性质及相关风险的信息。",
        insert=True,
    ),
]

#: 源模板上市 ⑧⑨⑩ 的说明段落（模板 JSON 原先只到 ⑦ 资金集中管理）。
#:
#: ⚠️ 正文段一律**不加 `#### ` 前缀** —— `disclosure_engine._is_table_title_paragraph`
#: 见 `#` 即判标题，标题本身不进任何输出 → 实质披露正文会被静默丢弃（H1 上市曾中招）。
#: 只有「小节标题」才用 `#### `。
K1_LISTED_REQUIRE_TEXTS = [
    "#### 应收政府补助情况",
    "（信息披露解释性公告2号要求：对于报告期末按应收金额确认的政府补助，公司应按补助单位和"
    "补助项目逐项披露应收款项的期末余额、账龄以及预计收取的时间、金额及依据。如公司未能在"
    "预计时点收到预计金额的政府补助，公司应披露原因。）",
    "【确认应收款项时，应履行重大业务咨询程序。】",
    "#### 因金融资产转移而终止确认的其他应收款情况",
    "【因金融资产转移而终止确认的应收款项，应列示金融资产转移的方式、终止确认的应收款项"
    "金额，及与终止确认相关的利得或损失；】",
    "#### 转移其他应收款且继续涉入形成的资产、负债的金额",
    "【转移应收款项且继续涉入的，应披露资产转移方式、分项列示继续涉入形成的资产、负债的"
    "金额。】",
    "说明：资产转移方式；未全部终止确认的被转移金融资产与相关负债之间的关系，已终止确认的"
    "金融资产继续涉入的性质及相关风险的信息。",
]

# ═══════════════════════════════════════════════════════════════════════
# K1 国企 §八、9
# ═══════════════════════════════════════════════════════════════════════

#: 国企续表正名（裸 `续：` 跨章节撞键；同步侧 `K1_SOE_SUBTABLE.methodPrior` 已同步）
K1_SOE_METHOD_PRIOR = "按坏账准备计提方法分类披露其他应收款项（续：期初余额）"

#: 按计提方法分类（源 xlsx 国企 A19:F26 是三级表头：期末余额 > 账面余额/坏账准备/账面价值
#: > 金额/比例/预期信用损失率）。顶层期别已由「主表 + 续表」两张表承载（D1/D6 同款范式），
#: 剩下两级用 `group`；`账面价值` 是 rowspan=2 的独立列 → `group=None`（混合分组）。
def _method_cols() -> list[dict[str, Any]]:
    return grouped_columns(
        ("label", "类  别"),
        [
            ("账面余额", "金额", AMOUNT, "账面余额"),
            ("比例(%)", "比例(%)", TEXT, "账面余额"),
            ("坏账准备", "金额", AMOUNT, "坏账准备"),
            ("预期信用损失率(%)", "预期信用损失率(%)", TEXT, "坏账准备"),
            ("账面价值", "账面价值", AMOUNT, None),
        ],
    )


_METHOD_ROWS = [
    data_row("单项计提坏账准备的其他应收款项"),
    data_row("按信用风险特征组合计提坏账准备的其他应收款项"),
    data_row(),
    total_row("合计"),
]

K1_SOE_PLAN: list[dict[str, Any]] = [
    rule(
        "其他应收款",
        _cols([("label", "项目", None), ("期末余额", "期末余额", AMOUNT),
               ("期初余额", "期初余额", AMOUNT)]),
        labels_then_total(["应收利息", "应收股利", "其他应收款项"]),
        KEEP,
    ),
    rule(
        "应收利息分类",
        _cols([("label", "项目", None), ("期末余额", "期末余额", AMOUNT),
               ("期初余额", "期初余额", AMOUNT)]),
        [data_row("定期存款"), data_row("委托贷款"), data_row("债券投资"), data_row("其他"),
         subtotal_row("小计"), data_row("减：坏账准备"), total_row("合计")],
        KEEP,
    ),
    rule(
        "重要逾期利息",
        _cols([("label", "借款单位", None), ("期末余额", "期末余额", AMOUNT),
               ("逾期时间（月）", "逾期时间（月）", TEXT), ("逾期原因", "逾期原因", TEXT),
               ("是否发生减值及其判断依据", "是否发生减值及其判断依据", TEXT)]),
        blanks_then_total(3),
        KEEP,
    ),
    rule("坏账准备计提情况", _movement_cols("坏账准备"), list(_ECL_MOVEMENT_ROWS_SOE), KEEP),
    rule(
        "应收股利",
        _cols([("label", "项目", None), ("期末余额", "期末余额", AMOUNT),
               ("期初余额", "期初余额", AMOUNT),
               ("未收回的原因", "未收回的原因", TEXT),
               ("是否发生减值及其判断依据", "是否发生减值及其判断依据", TEXT)]),
        [data_row("账龄一年以内的应收股利"), data_row("其中：（1）"), data_row("（2）"),
         data_row(), data_row("账龄一年以上的应收股利"), data_row("其中：（1）"),
         data_row("（2）"), data_row(), subtotal_row("小计："),
         data_row("减：坏账准备"), total_row("合计")],
        KEEP,
    ),
    # 🔴 源 xlsx 国企 `A6:C15` 是**单级 3 列**（`账  龄` / `期末数` / `期初数`），
    # 行 = 6 档账龄 + `小  计` + `减：坏账准备` + `合  计`。
    # 模板原先是 5 列（期末数/期初数 各含账面余额+坏账准备）且行为 3 年段无小计/减坏账行
    # —— 那套「双列 + 只有合计行」结构不在源模板里，导致同步侧不得不把「小计 + 减：坏账
    # 准备」两行压进合计行的额外两列（`buildK1SoeSubTableData` 注释自述该 hack）。
    # 现按源模板还原，同步侧即可忠实推 subtotal / provision / total 三种 kind。
    rule(
        "按账龄披露其他应收款项",
        _cols([("label", "账  龄", None), ("期末数", "期末数", AMOUNT),
               ("期初数", "期初数", AMOUNT)]),
        [data_row("1年以内（含1年）"), data_row("1至2年"), data_row("2至3年"),
         data_row("3至4年"), data_row("4至5年"), data_row("5年以上"),
         subtotal_row("小  计"), data_row("减：坏账准备"), total_row("合  计")],
        "源模板国企版账龄表为**单级 3 列**（账龄 / 期末数 / 期初数），行含小  计、"
        "减：坏账准备、合  计。勾稽：小  计 = K1-1 其他应收款审定期末数；"
        "小  计 − 减：坏账准备 = 合  计；减：坏账准备 = 三阶段变动表期末余额。"
        "账龄档随项目账龄配置（3年段 / 5年段 / 自定义），此处 seed 取源模板 5 年段口径。",
    ),
    rule("按坏账准备计提方法分类披露其他应收款项", _method_cols(), list(_METHOD_ROWS), KEEP),
    rule(K1_SOE_METHOD_PRIOR, _method_cols(), list(_METHOD_ROWS), KEEP, aliases=["续："]),
    rule(
        "单项计提坏账准备的其他应收款项",
        grouped_columns(
            ("label", "债务人名称"),
            [
                ("账面余额", "账面余额", AMOUNT, "期末余额"),
                ("坏账准备", "坏账准备", AMOUNT, "期末余额"),
                ("预期信用损失率(%)", "预期信用损失率(%)", TEXT, "期末余额"),
                ("计提理由", "计提理由", TEXT, "期末余额"),
            ],
        ),
        blanks_then_total(3),
        KEEP,
    ),
    rule(
        "账龄组合",
        grouped_columns(
            ("label", "账  龄"),
            [
                ("期末账面余额", "账面余额", AMOUNT, "期末数"),
                ("期末比例(%)", "比例(%)", TEXT, "期末数"),
                ("期末坏账准备", "坏账准备", AMOUNT, "期末数"),
                ("期初账面余额", "账面余额", AMOUNT, "期初数"),
                ("期初比例(%)", "比例(%)", TEXT, "期初数"),
                ("期初坏账准备", "坏账准备", AMOUNT, "期初数"),
            ],
        ),
        # 源 xlsx `A49:A55` = 6 档账龄 + `合  计`（原模板为 3 年段）
        labels_then_total(
            ["1年以内（含1年）", "1至2年", "2至3年", "3至4年", "4至5年", "5年以上"],
            "合  计",
        ),
        KEEP,
    ),
    rule(
        "采用余额百分比法或其他组合方法计提坏账准备的其他应收款项",
        grouped_columns(
            ("label", "组合名称"),
            [
                ("期末账面余额", "账面余额", AMOUNT, "期末数"),
                ("期末计提比例(%)", "计提比例(%)", TEXT, "期末数"),
                ("期末坏账准备", "坏账准备", AMOUNT, "期末数"),
                ("期初账面余额", "账面余额", AMOUNT, "期初数"),
                ("期初计提比例(%)", "计提比例(%)", TEXT, "期初数"),
                ("期初坏账准备", "坏账准备", AMOUNT, "期初数"),
            ],
        ),
        blanks_then_total(3),
        KEEP,
    ),
    rule(
        "其他应收款项坏账准备计提情况",
        _movement_cols("坏账准备"),
        list(_ECL_MOVEMENT_ROWS_SOE),
        KEEP,
    ),
    rule(
        "其他应收款项账面余额变动",
        _movement_cols("账面余额"),
        list(_BALANCE_MOVEMENT_ROWS_SOE),
        KEEP,
    ),
    rule(
        "收回或转回的坏账准备",
        _cols([("label", "债务人名称", None),
               ("转回或收回金额", "转回或收回金额", AMOUNT),
               ("转回或收回前累计已计提坏账准备金额",
                "转回或收回前累计已计提坏账准备金额", AMOUNT),
               ("转回或收回原因、方式", "转回或收回原因、方式", TEXT)]),
        blanks_then_total(3),
        KEEP,
    ),
    rule(
        "本期实际核销的其他应收款项",
        _cols([("label", "债务人名称", None),
               ("其他应收款项性质", "其他应收款项性质", TEXT),
               ("核销金额", "核销金额", AMOUNT), ("核销原因", "核销原因", TEXT),
               ("履行的核销程序", "履行的核销程序", TEXT),
               ("是否因关联交易产生", "是否因关联交易产生", TEXT)]),
        blanks_then_total(3),
        KEEP,
    ),
    rule(
        "按欠款方归集的期末余额前五名的其他应收款项",
        _cols([("label", "债务人名称", None), ("款项性质", "款项性质", TEXT),
               ("账面余额", "账面余额", AMOUNT), ("账龄", "账龄", TEXT),
               ("占其他应收款项合计的比例（%）", "占其他应收款项合计的比例（%）", TEXT),
               ("坏账准备", "坏账准备", AMOUNT)]),
        blanks_then_total(5),
        KEEP,
    ),
    rule(
        "由金融资产转移而终止确认的其他应收款项",
        _cols([("label", "债务人名称", None), ("终止确认金额", "终止确认金额", AMOUNT),
               ("与终止确认相关的利得或损失", "与终止确认相关的利得或损失", AMOUNT)]),
        blanks_then_total(3, "合  计"),
        KEEP,
    ),
    rule(
        "其他应收款项转移继续涉入形成的资产、负债的金额",
        _cols([("label", "项  目", None), ("期末金额", "期末金额", AMOUNT)]),
        [data_row("资产："), subtotal_row("资产小计"), data_row("负债："),
         subtotal_row("负债小计")],
        KEEP,
    ),
    rule(
        "涉及政府补助的应收款项",
        _cols([("label", "单位名称", None),
               ("政府补助项目名称", "政府补助项目名称", TEXT),
               ("期末余额", "期末余额", AMOUNT), ("期末账龄", "期末账龄", TEXT),
               ("预计收取的时间、金额及依据", "预计收取的时间、金额及依据", TEXT)]),
        blanks_then_total(3, "合  计"),
        KEEP,
    ),
]

K1_LISTED_EXPECTED = [r["new_name"] for r in K1_LISTED_PLAN]
K1_SOE_EXPECTED = [r["new_name"] for r in K1_SOE_PLAN]


# ═══════════════════════════════════════════════════════════════════════
# K6 持有待售资产和负债 §五、11 / §八、12 / §八、43
# ═══════════════════════════════════════════════════════════════════════

#: 主表两级表头的父表头串（**per-variant**）。
#: 源 xlsx 是「期末数/上年年末数」「期末数/期初数」，附注模版上市侧作「期末余额/上年年末余额」；
#: **附注是交付物 → 取附注模版口径**，且与既有同步映射 `K6_COLUMN_GROUPS` 逐字一致（不 churn）。
K6_GROUPS = {
    "listed": ("期末余额", "上年年末余额"),
    "soe": ("期末数", "期初数"),
}


def _held_main_cols(variant: str) -> list[dict[str, Any]]:
    """主表 7 列两级表头（源 xlsx 上市 B6:D6/E6:G6、国企 B9:D9/E9:G9 跨列合并）。"""
    end, prior = K6_GROUPS[variant]
    return grouped_columns(
        ("label", "项目"),
        [
            ("end_gross", "账面余额", AMOUNT, end),
            ("end_impairment", "减值准备", AMOUNT, end),
            ("end_book", "账面价值", AMOUNT, end),
            ("prior_gross", "账面余额", AMOUNT, prior),
            ("prior_impairment", "减值准备", AMOUNT, prior),
            ("prior_book", "账面价值", AMOUNT, prior),
        ],
    )


#: 主表 / 减值准备表共用行骨架。
#: 源 xlsx 的 `子公司A` / `分公司B` / `……` 是**占位示例名**（`其中：子公司A` 也只是示例），
#: 按平台铁律改空白录入行；处置组实际名称由底稿动态行提供。
def _held_rows(section_a: str, section_b: str) -> list[dict[str, Any]]:
    return [
        subtotal_row(section_a),
        data_row("其中：固定资产"),
        data_row("无形资产"),
        data_row(),
        subtotal_row(section_b),
        data_row(),
        data_row(),
        data_row(),
        total_row("合计"),
    ]


def _impairment_cols(prior_label: str) -> list[dict[str, Any]]:
    """减值准备变动表 6 列。

    源 xlsx 上市 `A32:F42` / 国企 `A22:F32`：`D32:E32`（`D22:E22`）合并 = 「本期减少」，
    下辖 `本期转回` / `本期出售` 两个子列 → **混合分组**（其余列 rowspan=2、无 group）。
    模板原压成单列「本期减少」，二级拆分整个丢失。
    """
    return grouped_columns(
        ("label", "项目"),
        [
            ("prior_amount", prior_label, AMOUNT, None),
            ("increase", "本期增加", AMOUNT, None),
            ("reverse", "本期转回", AMOUNT, "本期减少"),
            ("disposal", "本期出售", AMOUNT, "本期减少"),
            ("end_amount", "期末数", AMOUNT, None),
        ],
    )


def _fair_value_cols(disposal_fee_label: str) -> list[dict[str, Any]]:
    """持有待售非流动资产 / 处置组 / 负债共用 5 列（上市「预计出售费用」/ 国企「预计处置费用」）。"""
    return _cols([
        ("label", "项目", None),
        ("end_book", "期末账面价值", AMOUNT),
        ("end_fair_value", "期末公允价值", AMOUNT),
        ("disposal_fee", disposal_fee_label, AMOUNT),
        ("timetable", "时间安排", TEXT),
    ])


#: 处置组表行骨架（源 xlsx 上市 A54:A64 / 国企 A43:A47：资产段 + 负债段各自小计）
_DISPOSAL_GROUP_ROWS = [
    subtotal_row("持有待售的处置组中的资产"),
    data_row("货币资金"),
    data_row(),
    data_row("固定资产"),
    data_row(),
    subtotal_row("持有待售的处置组中的负债"),
    data_row("应付票据"),
    data_row("应付账款"),
    data_row("长期应付款"),
    data_row(),
]

_G_MAIN = (
    "【提示：“持有待售资产”反映资产负债表日划分为持有待售类别的非流动资产及划分为持有待售"
    "类别的处置组中的流动资产和非流动资产的期末账面价值，按“持有待售资产”科目期末余额减去"
    "“持有待售资产减值准备”科目期末余额后的净额填列。】"
    "勾稽：账面余额 − 减值准备 = 账面价值（期末/上期各自独立，校验预设 F11-4）；"
    "合计行账面价值 = 资产负债表「持有待售资产」（F11-1/1a）；"
    "合计 =（一）持有待售非流动资产 +（二）持有待售处置组中的资产。数据来源：明细表 K6-2。"
)

_G_LIABILITY = (
    "【提示：“持有待售负债”反映资产负债表日处置组中与划分为持有待售类别的资产直接相关的"
    "负债的期末账面价值，按“持有待售负债”科目期末余额填列。】"
    "注：应披露划分为持有待售的非流动负债或处置组的出售原因、方式和时间安排、分部信息，"
    "以及与其有关的其他综合收益累计金额。数据来源：明细表 K6-2。"
)

_G_IMPAIRMENT = (
    "勾稽：期末数 = 期初（上年年末）数 + 本期增加 − 本期转回 − 本期出售（逐行）；"
    "合计 =（一）持有待售非流动资产 +（二）持有待售处置组中的资产。"
    "「本期减少」在源模板下辖「本期转回」「本期出售」两个子列，不可合并成一列填列。"
    "本表减值准备须与主表「减值准备」列期末数核对一致。"
)

_G_NON_CURRENT = (
    "【提示：期末账面价值应小于等于（期末公允价值 − 预计处置费用）——"
    "划分为持有待售后按二者较低者计量。】数据来源：初始确认检查表 K6-4。"
    "注：应披露持有待售非流动资产的出售原因、方式、时间安排与分部信息。"
)

_G_DISPOSAL_GROUP = (
    "按处置组逐个披露：资产段与负债段分别列示明细并小计。"
    "【提示：如存在专为转售而取得的持有待售的子公司，需披露该子公司出售原因、方式和时间安排；"
    "如子公司、共同经营、合营企业、联营企业不再继续划分为持有待售，需说明原因及会计处理。】"
    "数据来源：初始确认检查表 K6-4 / 处置组减值测试表 K6-6。"
)

K6_LISTED_PLAN: list[dict[str, Any]] = [
    # `tables[0].name` 是章节标题（既有同步映射 `K6_SUBTABLE.listed` 真源），不改名
    rule(
        "持有待售资产和持有待售负债",
        _held_main_cols("listed"),
        _held_rows("（一）持有待售非流动资产", "（二）持有待售处置组中的资产"),
        _G_MAIN,
    ),
    # 🔴 原 `tables[1]` 名叫「持有待售资产减值准备」而 rows 是持有待售负债行 —— name↔rows
    # 整体错位一位（md 重建游标跳位）。源 xlsx A19:C24 就是「持有待售负债」3 列表。
    rule(
        "持有待售负债",
        _cols([("label", "项目", None), ("end_amount", "期末余额", AMOUNT),
               ("prior_amount", "上年年末余额", AMOUNT)]),
        [data_row("持有待售的处置组中的负债"), data_row(), data_row(), total_row("合计")],
        _G_LIABILITY,
        aliases=["持有待售资产减值准备"],
    ),
    # 原名「期末，持有待售资产的情况：」是源 xlsx A44 段落文本泄漏
    rule(
        "持有待售资产减值准备",
        _impairment_cols("上年年末数"),
        _held_rows("（一）持有待售非流动资产", "（二）持有待售处置组中的资产"),
        _G_IMPAIRMENT,
        aliases=["期末，持有待售资产的情况："],
    ),
    # 原名「子公司A」是源 xlsx A52 的示例处置组名泄漏
    rule(
        "持有待售的非流动资产",
        _fair_value_cols("预计出售费用"),
        blanks_then_total(4),
        _G_NON_CURRENT,
        aliases=["子公司A"],
    ),
    # 原名「分公司B」是示例处置组名；源 xlsx 的两张处置组表（① 子公司A / ② 分公司B）
    # 是**同一张表的两个示例实例** → 模板只留一张骨架，实际处置组由底稿动态行推送
    rule(
        "持有待售的处置组",
        _fair_value_cols("预计出售费用"),
        list(_DISPOSAL_GROUP_ROWS),
        _G_DISPOSAL_GROUP,
        aliases=["分公司B"],
    ),
]

K6_SOE_PLAN: list[dict[str, Any]] = [
    rule(
        "持有待售资产",
        _held_main_cols("soe"),
        _held_rows("（一）持有待售非流动资产", "（二）持有待售处置组中的资产"),
        _G_MAIN,
    ),
    rule(
        "持有待售资产减值准备",
        _impairment_cols("期初数"),
        _held_rows("（一）持有待售非流动资产", "（二）持有待售处置组中的资产"),
        _G_IMPAIRMENT,
    ),
    rule(
        "持有待售非流动资产",
        _fair_value_cols("预计处置费用"),
        blanks_then_total(4),
        _G_NON_CURRENT,
    ),
    # 原名「持有待售资产（表4）」是 md 重建的**编号假名**；源 xlsx A41 是「（3）持有待售处置组中的资产」
    rule(
        "持有待售处置组中的资产",
        _fair_value_cols("预计处置费用"),
        list(_DISPOSAL_GROUP_ROWS),
        _G_DISPOSAL_GROUP,
        aliases=["持有待售资产（表4）"],
    ),
]

K6_SOE_LIAB_PLAN: list[dict[str, Any]] = [
    rule(
        "持有待售负债",
        _fair_value_cols("预计处置费用"),
        blanks_then_total(4, "合  计"),
        _G_LIABILITY,
    ),
]

K6_LISTED_EXPECTED = [r["new_name"] for r in K6_LISTED_PLAN]
K6_SOE_EXPECTED = [r["new_name"] for r in K6_SOE_PLAN]
K6_SOE_LIAB_EXPECTED = [r["new_name"] for r in K6_SOE_LIAB_PLAN]


# ═══════════════════════════════════════════════════════════════════════
# runner
# ═══════════════════════════════════════════════════════════════════════

SPECS: dict[str, dict[str, Any]] = {
    "k1-listed": {
        "label": "K1 其他应收款 · 上市 五、8",
        "path": LISTED,
        "section": "五、8",
        "plan": K1_LISTED_PLAN,
        "expected": K1_LISTED_EXPECTED,
        # 源模板 ⑧⑨⑩ 三小节的说明段落（补齐缺段，不整表替换）
        "require_text_sections": K1_LISTED_REQUIRE_TEXTS,
    },
    "k1-soe": {
        "label": "K1 其他应收款 · 国企 八、9",
        "path": SOE,
        "section": "八、9",
        "plan": K1_SOE_PLAN,
        "expected": K1_SOE_EXPECTED,
    },
    "k6-listed": {
        "label": "K6 持有待售 · 上市 五、11",
        "path": LISTED,
        "section": "五、11",
        "plan": K6_LISTED_PLAN,
        "expected": K6_LISTED_EXPECTED,
        # `项  目` 是表头首格泄漏名，且内容与「持有待售的处置组」重复（源模板的第二个示例处置组）
        "drops": ["项  目"],
    },
    "k6-soe": {
        "label": "K6 持有待售资产 · 国企 八、12",
        "path": SOE,
        "section": "八、12",
        "plan": K6_SOE_PLAN,
        "expected": K6_SOE_EXPECTED,
    },
    "k6-soe-liab": {
        "label": "K6 持有待售负债 · 国企 八、43",
        "path": SOE,
        "section": "八、43",
        "plan": K6_SOE_LIAB_PLAN,
        "expected": K6_SOE_LIAB_EXPECTED,
    },
}


def _runner(key: str, dry_run: bool, check: bool) -> tuple[list[str], list[str], list[str]]:
    spec = SPECS[key]
    return run_section(
        spec["path"],
        spec["section"],
        spec["plan"],
        spec["expected"],
        aligned_by=ALIGNED_BY,
        dry_run=dry_run,
        check=check,
        drops=spec.get("drops"),
        require_text_sections=spec.get("require_text_sections"),
    )


main = build_cli(
    "附注 K 系复杂类章节结构对齐（批 3：K1 / K6）",
    _runner,
    {k: v["label"] for k, v in SPECS.items()},
)

if __name__ == "__main__":
    raise SystemExit(main())
