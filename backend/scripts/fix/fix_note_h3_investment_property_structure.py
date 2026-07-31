#!/usr/bin/env python
"""附注「投资性房地产」章节结构对齐源模板（幂等修订）。

**目标**：附注模板投资性房地产章节（上市 §五、21 / 国企 §八、21）对齐致同源模板
`backend/wp_templates/H/H3 投资性房地产.xlsx`。

历史问题（2026-07-31 逐 sheet 精读源 xlsx + 模板 dump 实测）：

1. **国企两级表头被 md 重建压扁**：
   - 「以成本计量」源为 7 列两级 —— `期初余额` + `本期增加{购置或计提, 自用房地产或存货转入}`
     + `本期减少{处 置, 转为自用房地产}` + `期末余额`（源 xlsx 行 8~10，「购置或/计提」
     跨两行书写）；模板压成 5 列。
   - 「以公允价值计量」源为 8 列两级 —— `期初公允价值` + `本期增加{购置, 自用房地产或存货转入,
     公允价值变动损益}` + `本期减少{处 置, 转为自用房地产}` + `期末公允价值`（行 29~30）；
     模板压成 5 列。
   期初/期末列是 rowspan=2 的独立列 → **不给 group**（混合分组）。
2. **国企第 3 张表与第 2 张同名 `以公允价值计量`**：表名是 `sub_table_data` 的键，
   同名互相覆盖**丢整张表**；源模板实为「（3）未办妥产权证书的投资性房地产」。
3. **`header_label` 假数据行**：国企前两表 `rows[0]` 是压扁的第二行表头残留。
4. **上市 6 处「可无限量添加行」占位说明行**：源模板的「可无限量添加行」被 md 重建当数据行
   落进 `rows`，会渲染成空披露数据行 → 必删，语义移入 `guidance`。
5. **columns / guidance 全缺**：两版共 6 表 `columns=0`（未表态）且无 `guidance`
   → seed 路径走 `_infer_groups_from_headers` 前缀推断。
6. **上市 `text_sections` 裸标题/说明未加 `#### ` 前缀**，且缺源模板 (4)「房地产转换情况
   及改变计量模式的情况」全文（行 71~74）与两条 【】提示（行 48~49，移入 guidance）。

裁决要点：

- **上市是列转置结构**：列 = 资产类别（房屋、建筑物 / 土地使用权 / 在建工程 / 合计），
  行 = 变动层次明细（四层 / 三段）。列 `key` 用类别名（同 H1「固定资产情况」范式）。
  两表均为**单行表头** → 显式 `flat`。
- 上市行集与源模板逐字一致（含源模板自身的 `3、本期减少金额` 顿号书写，不"修正"）。
- 国企行集 = 5 层 / 3 层，每层 1 合计行 + 2 类别行（`1、房屋、建筑物` / `2、土地使用权`；
  公允价值表带 `其中：` 前缀）。
- 「未办妥产权证书」两版列不同：上市 `项目/账面价值/未办妥产权证书原因`（无合计行，
  源模板行 67~68），国企 `项目/账面价值/原因`（带合计行，源模板行 42~46）。

Usage::

    python backend/scripts/fix/fix_note_h3_investment_property_structure.py --dry-run
    python backend/scripts/fix/fix_note_h3_investment_property_structure.py
    python backend/scripts/fix/fix_note_h3_investment_property_structure.py --check

spec: .kiro/specs/h3-investment-property-disclosure-alignment/ (Task 3)
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

LISTED_SECTION = "五、21"
SOE_SECTION = "八、21"
ALIGNED_BY = "h3-investment-property-disclosure-alignment"

# ── 表名（与 h3NoteSectionMap.ts 及模板 tables[].name 逐字一致）────────────────
T_L_COST = "按成本计量的投资性房地产"
T_L_FAIR = "按公允价值计量的投资性房地产"
T_L_TITLE = "未办妥产权证书的情况"

T_S_COST = "以成本计量"
T_S_FAIR = "以公允价值计量"
T_S_TITLE = "未办妥产权证书的投资性房地产"

# 上市资产类别列（源 xlsx 行 8 / 行 53）
_LISTED_CATEGORIES = ("房屋、建筑物", "土地使用权", "在建工程", "合计")


def _listed_transposed_columns() -> list[dict[str, Any]]:
    """列转置：标签列 + 资产类别列（单行表头 → flat）。"""
    return flat_columns([("label", "项目", None)] + [(c, c, AMOUNT) for c in _LISTED_CATEGORIES])


# ── 上市行集（逐字取源 xlsx，删除「可无限量添加行」占位）──────────────────────
_L_COST_ROWS = [data_row(x) for x in (
    "一、账面原值",
    "1.期初余额",
    "2.本期增加金额",
    "（1）外购",
    "（2）存货\\固定资产\\在建工程转入",
    "（3）企业合并增加",
    "3.本期减少金额",
    "（1）处置",
    "（2）其他转出",
    "4.期末余额",
    "二、累计折旧和累计摊销",
    "1.期初余额",
    "2.本期增加金额",
    "（1）计提或摊销",
    "（2）企业合并增加",
    "（3）其他增加",
    "3.本期减少金额",
    "（1）处置",
    "（2）其他转出",
    "4.期末余额",
    "三、减值准备",
    "1.期初余额",
    "2.本期增加金额",
    "（1）计提",
    "（2）其他增加",
    # 源模板此处为顿号书写「3、本期减少金额」（其余层为「3.」）—— 保持源模板字面
    "3、本期减少金额",
    "（1）处置",
    "（2）其他转出",
    "4.期末余额",
    "四、账面价值",
    "1.期末账面价值",
    "2.期初账面价值",
)]

_L_FAIR_ROWS = [data_row(x) for x in (
    "一、期初余额",
    "二、本期变动",
    "加：外购",
    "存货\\固定资产\\在建工程转入",
    "企业合并增加",
    "减：处置",
    "其他转出",
    "公允价值变动",
    "三、期末余额",
)]

# 源模板上市 (3) 只有「可无限量添加行」占位、无合计行 → 空行骨架
_L_TITLE_ROWS = [data_row() for _ in range(3)]


# ── 国企两级列 ────────────────────────────────────────────────────────────────
def _soe_cost_columns() -> list[dict[str, Any]]:
    """7 列两级：期初/期末 rowspan=2 无 group（混合分组）。"""
    return grouped_columns(
        ("label", "项目"),
        [
            ("begin", "期初余额", AMOUNT, None),
            ("buy_or_provision", "购置或计提", AMOUNT, "本期增加"),
            ("transfer_in", "自用房地产或存货转入", AMOUNT, "本期增加"),
            ("disposal", "处 置", AMOUNT, "本期减少"),
            ("transfer_out", "转为自用房地产", AMOUNT, "本期减少"),
            ("end", "期末余额", AMOUNT, None),
        ],
    )


def _soe_fair_columns() -> list[dict[str, Any]]:
    """8 列两级：本期增加含「公允价值变动损益」子列。"""
    return grouped_columns(
        ("label", "项目"),
        [
            ("begin_fair", "期初公允价值", AMOUNT, None),
            ("buy", "购置", AMOUNT, "本期增加"),
            ("transfer_in", "自用房地产或存货转入", AMOUNT, "本期增加"),
            ("fair_change_pl", "公允价值变动损益", AMOUNT, "本期增加"),
            ("disposal", "处 置", AMOUNT, "本期减少"),
            ("transfer_out", "转为自用房地产", AMOUNT, "本期减少"),
            ("end_fair", "期末公允价值", AMOUNT, None),
        ],
    )


def _soe_layer_rows(layers: list[str], *, which_prefix: bool) -> list[dict[str, Any]]:
    """每层 1 个合计行 + 2 个类别行（公允价值表首类别带「其中：」前缀）。"""
    rows: list[dict[str, Any]] = []
    for layer in layers:
        rows.append(total_row(layer))
        rows.append(data_row("其中：1、房屋、建筑物" if which_prefix else "1、房屋、建筑物"))
        rows.append(data_row("2、土地使用权"))
    return rows


_S_COST_ROWS = _soe_layer_rows([
    "一、账面原值合计",
    "二、累计折旧和累计摊销合计",
    "三、投资性房地产账面净值合计",
    "四、投资性房地产减值准备累计金额合计",
    "五、投资性房地产账面价值合计",
], which_prefix=False)

_S_FAIR_ROWS = _soe_layer_rows([
    "一、成本合计",
    "二、公允价值变动合计",
    "三、投资性房地产账面价值合计",
], which_prefix=True)

_S_TITLE_ROWS = [data_row() for _ in range(3)] + [total_row()]


# ── guidance（源模板红字 / 15 号文 / 证监会年报会计监管报告 / 勾稽）─────────────
_G_L_COST = (
    "（1）按成本计量的投资性房地产（如无以公允价值计量的投资性房地产，删除此标题）。"
    "列 = 资产类别（房屋、建筑物 / 土地使用权 / 在建工程 / 合计），行 = 四层变动明细；"
    "各层「本期增加金额 / 本期减少金额」下的明细项按被审计单位实际情况可无限量添加行"
    "（源模板 A15/A19/A27/A31/A38/A42）。"
    "勾稽：各层 期末余额 = 期初余额 + 本期增加金额 − 本期减少金额；"
    "四、账面价值 1.期末账面价值 = 一、账面原值4.期末余额 − 二、累计折旧和累计摊销4.期末余额"
    " − 三、减值准备4.期末余额；2.期初账面价值 同口径；合计列 = 各资产类别之和。"
    "【长期资产本期进行减值测试的，应披露可收回金额的具体确定方法。可收回金额按公允价值减去"
    "处置费用后的净额确定的，应披露公允价值和处置费用的确定方式、关键参数及其确定依据。"
    "可收回金额按预计未来现金流量的现值确定的，应披露预测期的年限、预测期及稳定期的关键参数"
    "及其确定依据。前述信息与以前年度减值测试采用的信息或外部信息明显不一致的，或公司以前年度"
    "减值测试采用信息与当年实际情况明显不一致的，应披露差异原因。（15号文第十九条（十九））】"
    "【提示：证监会《2014 年上市公司年报会计监管报告》，已出租的建筑物是指公司拥有产权的、"
    "以经营租赁方式出租的建筑物。因此，不得将没有产权的物业经营权列报为投资性房地产。】"
)
_G_L_FAIR = (
    "（2）按公允价值计量的投资性房地产（不适用的删除）。"
    "（采用公允价值计量模式的投资性房地产，分类列示期初余额、期末余额和本期增减变动情况。）"
    "勾稽：三、期末余额 = 一、期初余额 + 二、本期变动（加：外购 + 存货\\固定资产\\在建工程转入"
    " + 企业合并增加 − 处置 − 其他转出 + 公允价值变动）；合计列 = 各资产类别之和。"
)
_G_L_TITLE = (
    "（3）未办妥产权证书的情况。（披露未办妥产权证书的投资性房地产账面价值及原因。）"
    "行按实际情况可无限量添加（源模板 A68）。"
    "勾稽：账面价值合计不得超过「按成本计量的投资性房地产」四、账面价值 1.期末账面价值 合计。"
)
_G_S_COST = (
    "（1）以成本计量（如无按公允价值计量的投资性房地产，删除此标题）。"
    "两级表头：期初余额 + 本期增加{购置或计提, 自用房地产或存货转入} + "
    "本期减少{处 置, 转为自用房地产} + 期末余额。"
    "五层结构：一、账面原值合计 → 二、累计折旧和累计摊销合计 → 三、投资性房地产账面净值合计 →"
    " 四、投资性房地产减值准备累计金额合计 → 五、投资性房地产账面价值合计，"
    "各层下列示 1、房屋、建筑物 / 2、土地使用权。"
    "勾稽：各层 期末余额 = 期初余额 + 本期增加 − 本期减少；"
    "账面净值 = 账面原值 − 累计折旧和累计摊销；账面价值 = 账面净值 − 减值准备累计金额；"
    "各层合计行 = 该层类别行之和。另需说明本期折旧和摊销额、本期减值准备计提额（源模板 ①②）。"
)
_G_S_FAIR = (
    "（2）以公允价值计量（不适用的删除）。"
    "两级表头：期初公允价值 + 本期增加{购置, 自用房地产或存货转入, 公允价值变动损益} + "
    "本期减少{处 置, 转为自用房地产} + 期末公允价值。"
    "三层结构：一、成本合计 / 二、公允价值变动合计 / 三、投资性房地产账面价值合计，"
    "各层下列示 其中：1、房屋、建筑物 / 2、土地使用权。"
    "勾稽：三、投资性房地产账面价值合计 = 一、成本合计 + 二、公允价值变动合计（逐列成立）。"
    "（注：①应披露公允价值确认依据。②说明报告期内改变计量模式的投资性房地产转换的原因及其影响。）"
)
_G_S_TITLE = (
    "（3）未办妥产权证书的投资性房地产。按项目列示账面价值及未办妥产权证书的原因。"
    "勾稽：合计行 = 各明细行之和；账面价值合计不得超过「以成本计量」五、投资性房地产账面价值合计"
    "（或「以公允价值计量」三、投资性房地产账面价值合计）的期末数。"
)

# ── text_sections（标题加 `#### ` 前缀避免被当披露正文；(4) 段取源模板全文）──────
_LISTED_TEXT_SECTIONS = [
    "#### 按成本计量的投资性房地产",
    "#### 按公允价值计量的投资性房地产",
    "（采用公允价值计量模式的投资性房地产，分类列示期初余额、期末余额和本期增减变动情况。）",
    "#### 未办妥产权证书的情况",
    "（披露未办妥产权证书的投资性房地产账面价值及原因。）",
    "#### 房地产转换情况及改变计量模式的情况",
    "（说明报告期内房地产转换或改变计量模式的情况、理由，以及对损益或所有者权益的影响。",
    "对于转换为投资性房地产并采用公允价值计量模式的，应披露转换的理由、审批程序，以及对损益、"
    "其他综合收益的影响。（15号文第十九条（十二）",
    "房地产开发企业列示出租开发产品时，应披露出租开发产品的成本、租赁合同主要条款等内容。"
    "对重要的出租房产应单项披露，非重要或零星的出租房产可采用合并披露。）",
]

_SOE_TEXT_SECTIONS = [
    "#### 以成本计量",
    "① 本期折旧和摊销额XX元。",
    "② 投资性房地产本期减值准备计提额XX元。",
    "#### 以公允价值计量",
    "（注：①应披露公允价值确认依据。②说明报告期内改变计量模式的投资性房地产转换的原因及其影响。）",
    "#### 未办妥产权证书的投资性房地产",
]


def _listed_plan() -> list[dict[str, Any]]:
    return [
        rule(T_L_COST, _listed_transposed_columns(), _L_COST_ROWS, _G_L_COST),
        rule(T_L_FAIR, _listed_transposed_columns(), _L_FAIR_ROWS, _G_L_FAIR),
        rule(T_L_TITLE, flat_columns([
            ("label", "项目", None),
            ("book_value", "账面价值", AMOUNT),
            ("reason", "未办妥产权证书原因", None),
        ]), _L_TITLE_ROWS, _G_L_TITLE),
    ]


def _soe_plan() -> list[dict[str, Any]]:
    return [
        rule(T_S_COST, _soe_cost_columns(), _S_COST_ROWS, _G_S_COST),
        rule(T_S_FAIR, _soe_fair_columns(), _S_FAIR_ROWS, _G_S_FAIR),
        # 第 3 表原与第 2 表重名 `以公允价值计量` → 走 aliases 改名（不能进 drops：
        # drop_tables 在 apply_plan 之前执行，会把待改名的表连同行一起删掉）。
        # 游标已前进到 idx 2，故 alias 命中的是第 3 张而非第 2 张。
        rule(T_S_TITLE, flat_columns([
            ("label", "项目", None),
            ("book_value", "账面价值", AMOUNT),
            ("reason", "原因", None),
        ]), _S_TITLE_ROWS, _G_S_TITLE, aliases=[T_S_FAIR]),
    ]


EXPECTED = {
    "listed": [T_L_COST, T_L_FAIR, T_L_TITLE],
    "soe": [T_S_COST, T_S_FAIR, T_S_TITLE],
}

_TARGETS = {
    "listed": (LISTED_PATH, LISTED_SECTION, _listed_plan, _LISTED_TEXT_SECTIONS),
    "soe": (SOE_PATH, SOE_SECTION, _soe_plan, _SOE_TEXT_SECTIONS),
}
_LABELS = {
    "listed": "note_template_listed.json §五、21 投资性房地产（上市）",
    "soe": "note_template_soe.json §八、21 投资性房地产（国企）",
}


def _runner(key: str, dry_run: bool, check: bool):
    path, section_number, plan_fn, texts = _TARGETS[key]
    return run_section(
        path,
        section_number,
        plan_fn(),
        EXPECTED[key],
        aligned_by=ALIGNED_BY,
        dry_run=dry_run,
        check=check,
        text_sections=texts,
    )


main = build_cli("附注投资性房地产章节结构对齐源模板（幂等）", _runner, _LABELS)

if __name__ == "__main__":
    raise SystemExit(main())
