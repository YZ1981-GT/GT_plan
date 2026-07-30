#!/usr/bin/env python
"""K1 其他应收款附注章节结构对齐（spec: k1-other-receivable-disclosure-alignment Sprint 2）.

对齐目标
--------
- `note_template_listed.json` §五、8「其他应收款」
- `note_template_soe.json`    §八、9「其他应收款」

权威源
------
1. `基础数据/附注模版/上市报表附注.md` / `国企报表附注.md`（§其他应收款）
2. `基础数据/致同通用审计程序及底稿模板（2025年修订）/…/K1 其他应收款.xlsx`
   sheet `附注披露信息(上市公司）` / `附注披露信息（国企）`

做三件事
--------
1. 二级表头：`headers` 展开为**无空串的全限定列名** + `_column_groups`（DisclosureEditor
   `activeTableColumns` 消费）。不能用空串占位——`test_note_template_row_type.py` 卡点。
2. 补缺表：国企 §八、9 缺 4 张（账面余额变动 / 转移终止确认 / 继续涉入 / 政府补助），
   表名·列头·行标签逐字取自 K1 国企披露 sheet。
3. 补 `guidance`（TAB 页签提示）与国企 `text_sections`——只引用源模板红字 / 附注模版
   括注 / 15号文条款，或明确以「勾稽：」前缀标注的工具提示。

幂等：可重复运行。
"""

from __future__ import annotations

import json
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
LISTED = BACKEND / "data" / "note_template_listed.json"
SOE = BACKEND / "data" / "note_template_soe.json"

LISTED_SECTION = "五、8"
SOE_SECTION = "八、9"


# ─── 工具 ────────────────────────────────────────────────────────────────────

def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save(path: Path, data: dict) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(text)
        f.write("\n")


def find_section(data: dict, section_number: str) -> dict:
    for s in data.get("sections", []):
        if str(s.get("section_number", "")).strip() == section_number:
            return s
    raise SystemExit(f"section {section_number} not found")


def table(section: dict, name: str) -> dict:
    for t in section.get("tables") or []:
        if t.get("name") == name:
            return t
    raise SystemExit(f"table {name!r} not found in {section.get('section_number')}")


def has_table(section: dict, name: str) -> bool:
    return any(t.get("name") == name for t in section.get("tables") or [])


def row(label: str, row_type: str = "data", **extra) -> dict:
    d = {"label": label, "row_type": row_type}
    if row_type in ("total", "subtotal"):
        d["is_total"] = True
    d.update(extra)
    return d


def drop_header_label_rows(t: dict) -> None:
    """启用 `_column_groups` 后，硬塞的 header_label 行成为冗余，删除。"""
    t["rows"] = [r for r in (t.get("rows") or []) if r.get("row_type") != "header_label"]


def set_guidance(section: dict, mapping: dict[str, str]) -> None:
    for name, text in mapping.items():
        table(section, name)["guidance"] = text


# ─── 上市 §五、8 ─────────────────────────────────────────────────────────────

LISTED_GUIDANCE = {
    "其他应收款": "汇总表：应收利息 + 应收股利 + 其他应收款 = 合计。勾稽：合计 = 资产负债表「其他应收款」项目（BS-009）。",
    "应收利息分类": "【提示：仅反映相关金融工具已到期可收取但于资产负债表日尚未收到的利息。基于实际利率法计提的金融工具的利息应包含在金融工具的账面余额中。】",
    "重要逾期利息": "（15号文第十九条10.对于重要的逾期应收利息，应按借款单位披露应收利息的期末余额、逾期时间和逾期原因、是否发生减值的判断。）",
    "应收股利": "勾稽：小计 − 减：坏账准备 = 合计。",
    "重要的账龄超过1年的应收股利": "（对于重要的账龄超过1 年的应收股利，应披露未收回的原因和对相关款项是否发生减值的判断。）",
    "按账龄披露": (
        "1年以内可按月度区间细分（其中：0-X个月 / X-Y个月）后给出「1年以内小计：」。"
        "勾稽：细分行合计 = 1年以内；小计 = K1-1 其他应收款审定期末数；小计 − 减：坏账准备 = 合计。"
    ),
    "按款项性质披露": (
        "两级表头：期末金额 / 上年年末金额 各含账面余额、坏账准备、账面价值。"
        "账面余额 − 坏账准备 = 账面价值。勾稽：合计账面余额 = 按账龄披露表小计。"
    ),
    "期末处于第一阶段的坏账准备": (
        "（15号文第十九条（四）5.采用一般预期信用损失模型计提坏账准备的应收款项，应分三阶段披露坏账准备计提情况，"
        "以及各阶段划分依据和坏账准备计提比例。）第一阶段按未来12个月内的预期信用损失率计提；"
        "组合口径须与会计政策中披露的组合保持一致。"
    ),
    "期末处于第二阶段的坏账准备": (
        "发生下列情形中的一种或多种时，则属于“自初始确认后信用风险显著增加”，划分为第二阶段："
        "款项逾期超过30 天但未超过90 天；欠款方发生影响其偿付能力的负面事件；"
        "担保物价值或第三方提供的担保或信用增级质量的显著不利变化。"
        "若不存在第二阶段，可改用文字表述：【或】期末，本公司不存在处于第二阶段的应收利息、应收股利和其他应收款。"
    ),
    "期末处于第三阶段的坏账准备": (
        "发生下列情形中的一种或多种时，则属于“已发生信用减值”，划分为第三阶段：款项逾期超过90 天；"
        "欠款方发生重大财务困难，或很可能破产或进行其他财务重组；"
        "其他违反合同约定且表明金融资产已存在客观减值证据的情形。"
    ),
    "上年年末处于第一阶段的坏账准备": "上年年末三阶段快照，结构与期末同。勾稽：三张表坏账准备合计 = 按账龄披露表「减：坏账准备」上年年末余额。",
    "上年年末处于第二阶段的坏账准备": "若不存在第二阶段，可改用文字表述：【或】上年年末，本公司不存在处于第二阶段的应收利息、应收股利和其他应收款。",
    "上年年末处于第三阶段的坏账准备": "上年年末已发生信用减值的部分，划分依据与期末第三阶段一致。",
    "本期计提、收回或转回的坏账准备情况": (
        "三阶段滚动表：期初余额 → 阶段迁移（转入/转回）→ 本期计提/转回/转销/核销/其他变动 → 期末余额。"
        "勾稽：期末余额 = 期末三阶段坏账准备合计；期初余额 = 上年年末三阶段坏账准备合计。"
    ),
    "本期转回或收回金额重要的坏账准备": (
        "（注：本表列报本报告期前已全额计提坏账准备，或计提减值准备的比例较大，但在本期又全额收回或转回，"
        "或在本期收回或转回比例较大的其他应收款。对本期通过重组等方式收回的金额重大的其他应收款，"
        "则应逐笔列报，金额不重大的，可汇总列报。）"
    ),
    "本期实际核销的其他应收款情况": "勾稽：核销金额 = 本期计提、收回或转回表「本期核销」行合计（绝对值）。",
    "重要的其他应收款核销情况（逐项披露）": (
        "【15号文第十九条（四）6，对于其中重要的应收款项，应逐项披露款项性质、核销原因、履行的核销程序及核销金额。"
        "实际核销的款项由关联交易产生的，应单独披露；】"
    ),
    "按欠款方归集的其他应收款期末余额前五名单位情况": (
        "【按欠款方归集的期末余额前五名的其他应收款，应分别披露欠款方名称、期末余额及占其他应收款期末余额合计数的比例、"
        "款项的性质、对应的账龄、坏账准备期末余额；】勾稽：占比分母 = 按账龄披露表小计；占比合计不应超过 100%。"
    ),
}

# 源模板 listed R34/R35：三阶段表内单项计提下挂两行示例单位
STAGE_UNIT_ROWS = ["其他应收款单位1", "其他应收款单位2"]


def fix_listed(data: dict) -> list[str]:
    log: list[str] = []
    sec = find_section(data, LISTED_SECTION)

    # 1) 按款项性质披露 → 7 列 + _column_groups（附注模版 md 二级表头）
    t = table(sec, "按款项性质披露")
    t["headers"] = [
        "项  目",
        "期末账面余额", "期末坏账准备", "期末账面价值",
        "上年年末账面余额", "上年年末坏账准备", "上年年末账面价值",
    ]
    t["_column_groups"] = [
        {"group": "期末金额", "start": 1, "span": 3},
        {"group": "上年年末金额", "start": 4, "span": 3},
    ]
    drop_header_label_rows(t)
    log.append("listed 按款项性质披露 → 7 列 + _column_groups")

    # 2) 期末/上年年末 第一、二阶段补「其他应收款单位1/2」（第三阶段已有）
    for name in (
        "期末处于第一阶段的坏账准备",
        "期末处于第二阶段的坏账准备",
        "上年年末处于第一阶段的坏账准备",
        "上年年末处于第二阶段的坏账准备",
    ):
        t = table(sec, name)
        labels = [r.get("label") for r in t.get("rows") or []]
        if STAGE_UNIT_ROWS[0] in labels:
            continue
        idx = labels.index("按单项计提坏账准备") + 1
        for offset, unit in enumerate(STAGE_UNIT_ROWS):
            t["rows"].insert(idx + offset, row(unit))
        log.append(f"listed {name} → 补单项计提示例行")

    # 3) guidance
    set_guidance(sec, LISTED_GUIDANCE)
    log.append(f"listed guidance × {len(LISTED_GUIDANCE)}")
    return log


# ─── 国企 §八、9 ─────────────────────────────────────────────────────────────

SOE_GUIDANCE = {
    "其他应收款": "汇总表：应收利息 + 应收股利 + 其他应收款项 = 合计。勾稽：合计 = 资产负债表「其他应收款」项目。",
    "应收利息分类": "勾稽：小计 − 减：坏账准备 = 合计。",
    "重要逾期利息": "按借款单位披露期末余额、逾期时间、逾期原因，以及是否发生减值及其判断依据。",
    "坏账准备计提情况": "本表为**应收利息**的坏账准备三阶段变动；其他应收款项的三阶段变动见「其他应收款项坏账准备计提情况」。",
    "应收股利": "按账龄一年以内 / 一年以上分组，其中项逐项列示；勾稽：小计： − 减：坏账准备 = 合计。",
    "按账龄披露其他应收款项": (
        "两级表头：期末数 / 期初数 各含账面余额、坏账准备。"
        "勾稽：合计账面余额 = K1-1 其他应收款审定期末数；合计坏账准备 = 三阶段变动表期末余额。"
    ),
    "按坏账准备计提方法分类披露其他应收款项": (
        "两级表头：账面余额（金额、比例%）、坏账准备（金额、预期信用损失率%）、账面价值。"
        "比例% = 该类账面余额 ÷ 合计账面余额；预期信用损失率% = 坏账准备 ÷ 账面余额。"
        "勾稽：合计账面余额 = 按账龄披露表合计。"
    ),
    "续：": "本表为「按坏账准备计提方法分类披露其他应收款项」的期初余额续表，列结构与期末表一致。",
    "单项计提坏账准备的其他应收款项": (
        "逐户列示单项评估的债务人及计提理由。勾稽：合计账面余额 / 坏账准备 = 按计提方法分类表「单项计提坏账准备的其他应收款项」行。"
    ),
    "账龄组合": (
        "按信用风险特征组合计提中的**账龄组合**。两级表头：期末数 / 期初数 各含账面余额（金额、比例%）与坏账准备。"
        "勾稽：账龄组合坏账准备 + 其他组合坏账准备 = 按计提方法分类表「按信用风险特征组合计提坏账准备的其他应收款项」行。"
    ),
    "采用余额百分比法或其他组合方法计提坏账准备的其他应收款项": (
        "按组合名称列示；此处「计提比例(%)」为人工设定的计提比例（非结构占比），坏账准备 = 账面余额 × 计提比例。"
    ),
    "其他应收款项坏账准备计提情况": (
        "三阶段滚动表：期初余额 → 阶段迁移 → 本期计提/转回/转销/核销/其他变动 → 期末余额。"
        "勾稽：期末余额 = 按账龄披露表合计坏账准备。"
    ),
    "其他应收款项账面余额变动": (
        "账面余额（非坏账准备）的三阶段变动。方向约定（源模板）：转入第二阶段＝第一阶段【负数】、第二阶段【正数】；"
        "转入第三阶段＝第一、二阶段【负数】、第三阶段【正数】；转回第一阶段＝第一阶段【正数】、第二、三阶段【负数】。"
        "勾稽：期末余额合计 = K1-1 其他应收款审定期末数。"
    ),
    "收回或转回的坏账准备": (
        "（注：本表列报本报告期前已全额计提坏账准备，或计提减值准备的比例较大，但在本期又全额收回或转回，"
        "或在本期收回或转回比例较大的其他应收款项。对本期通过重组等方式收回的金额重大的其他应收款项，"
        "则应逐笔列报，金额不重大的，可汇总列报。）"
    ),
    "本期实际核销的其他应收款项": "对重要的核销逐项披露款项性质、核销原因、履行的核销程序及核销金额；因关联交易产生的应单独披露。",
    "按欠款方归集的期末余额前五名的其他应收款项": "勾稽：占比分母 = 其他应收款项账面余额合计；占比合计不应超过 100%。",
    "由金融资产转移而终止确认的其他应收款项": "列示因金融资产转移而终止确认的金额及相关利得或损失，损失以「-」填列。",
    "其他应收款项转移继续涉入形成的资产、负债的金额": (
        "【如证券化、保理等】分资产、负债两区分项列示并给出小计；"
        "说明中披露资产转移方式、未全部终止确认的被转移金融资产与相关负债之间的关系、"
        "已终止确认的金融资产继续涉入的性质及相关风险的信息。"
    ),
    "涉及政府补助的应收款项": "（注：涉及重要的政府补助的应收款项应披露相关信息。）按补助单位与补助项目逐项披露期末余额、期末账龄及预计收取的时间、金额及依据。",
}

SOE_TEXT_SECTIONS = [
    "应收利息",
    "#### 应收利息分类",
    "#### 重要逾期利息",
    "（对于重要的逾期应收利息，应按借款单位披露应收利息的期末余额、逾期时间和逾期原因、是否发生减值的判断。）",
    "#### 坏账准备计提情况",
    "应收股利",
    "（对于重要的账龄超过1 年的应收股利，应披露未收回的原因和对相关款项是否发生减值的判断。）",
    "其他应收款项",
    "#### 按账龄披露其他应收款项",
    "#### 按坏账准备计提方法分类披露其他应收款项",
    "单项计提坏账准备的其他应收款项",
    "按信用风险特征组合计提坏账准备的其他应收款项",
    "#### 账龄组合",
    "#### 采用余额百分比法或其他组合方法计提坏账准备的其他应收款项",
    "#### 其他应收款项坏账准备计提情况",
    "本期坏账准备计提金额以及评估金融工具的信用风险是否显著增加的采用依据。",
    "#### 其他应收款项账面余额变动",
    "说明：对本期发生损失准备变动的账面余额显著变动的情况说明。",
    "收回或转回的坏账准备",
    "（注：本表列报本报告期前已全额计提坏账准备，或计提减值准备的比例较大，但在本期又全额收回或转回，或在本期收回或转回比例较大的其他应收款项。对本期通过重组等方式收回的金额重大的其他应收款项，则应逐笔列报，金额不重大的，可汇总列报。）",
    "本期实际核销的其他应收款项",
    "按欠款方归集的期末余额前五名的其他应收款项",
    "由金融资产转移而终止确认的其他应收款项",
    "其他应收款项转移继续涉入形成的资产、负债的金额【如证券化、保理等】",
    "说明：（资产转移方式；未全部终止确认的被转移金融资产与相关负债之间的关系，已终止确认的金融资产继续涉入的性质及相关风险的信息。）",
    "企业应披露涉及政府补助的应收款项",
    "（注：涉及重要的政府补助的应收款项应披露相关信息。）",
]

STAGE_MOVEMENT_HEADERS = ["第一阶段", "第二阶段", "第三阶段", "合计"]

BALANCE_MOVEMENT_ROWS = [
    "期初余额",
    "期初余额在本期",
    "—转入第二阶段",
    "—转入第三阶段",
    "—转回第二阶段",
    "—转回第一阶段",
    "本期新增",
    "本期终止确认",
    "其他变动",
]


def new_soe_tables() -> list[dict]:
    """K1 国企披露 sheet R76-R130 对应的 4 张表（附注 §八、9 原缺）。"""
    return [
        {
            "name": "其他应收款项账面余额变动",
            "headers": ["账面余额", *STAGE_MOVEMENT_HEADERS],
            "rows": [
                row("账面余额", "header_label"),
                *[row(label) for label in BALANCE_MOVEMENT_ROWS],
                row("期末余额", "total"),
            ],
        },
        {
            "name": "由金融资产转移而终止确认的其他应收款项",
            "headers": ["债务人名称", "终止确认金额", "与终止确认相关的利得或损失"],
            "rows": [row("合  计", "total")],
        },
        {
            "name": "其他应收款项转移继续涉入形成的资产、负债的金额",
            "headers": ["项  目", "期末金额"],
            "rows": [
                row("资产："),
                row("资产小计", "subtotal"),
                row("负债："),
                row("负债小计", "subtotal"),
            ],
        },
        {
            "name": "涉及政府补助的应收款项",
            "headers": ["单位名称", "政府补助项目名称", "期末余额", "期末账龄", "预计收取的时间、金额及依据"],
            "rows": [row("合  计", "total")],
        },
    ]


def fix_soe(data: dict) -> list[str]:
    log: list[str] = []
    sec = find_section(data, SOE_SECTION)

    # 1) 按账龄披露其他应收款项 → 期末数/期初数 各含 账面余额+坏账准备
    t = table(sec, "按账龄披露其他应收款项")
    t["headers"] = ["账  龄", "期末账面余额", "期末坏账准备", "期初账面余额", "期初坏账准备"]
    t["_column_groups"] = [
        {"group": "期末数", "start": 1, "span": 2},
        {"group": "期初数", "start": 3, "span": 2},
    ]
    drop_header_label_rows(t)
    log.append("soe 按账龄披露其他应收款项 → 5 列 + _column_groups")

    # 2) 按坏账准备计提方法分类 + 续：
    for name, period in (("按坏账准备计提方法分类披露其他应收款项", "期末余额"), ("续：", "期初余额")):
        t = table(sec, name)
        t["headers"] = ["类  别", "账面余额", "比例(%)", "坏账准备", "预期信用损失率(%)", "账面价值"]
        t["_column_groups"] = [
            {"group": "账面余额", "start": 1, "span": 2},
            {"group": "坏账准备", "start": 3, "span": 2},
        ]
        t["period_label"] = period
        drop_header_label_rows(t)
        log.append(f"soe {name} → 6 列 + _column_groups（{period}）")

    # 3) 单项计提坏账准备的其他应收款项
    t = table(sec, "单项计提坏账准备的其他应收款项")
    t["headers"] = ["债务人名称", "账面余额", "坏账准备", "预期信用损失率(%)", "计提理由"]
    t["_column_groups"] = [{"group": "期末余额", "start": 1, "span": 4}]
    drop_header_label_rows(t)
    log.append("soe 单项计提坏账准备的其他应收款项 → 5 列 + _column_groups")

    # 4) 账龄组合
    t = table(sec, "账龄组合")
    t["headers"] = [
        "账  龄",
        "期末账面余额", "期末比例(%)", "期末坏账准备",
        "期初账面余额", "期初比例(%)", "期初坏账准备",
    ]
    t["_column_groups"] = [
        {"group": "期末数", "start": 1, "span": 3},
        {"group": "期初数", "start": 4, "span": 3},
    ]
    drop_header_label_rows(t)
    log.append("soe 账龄组合 → 7 列 + _column_groups")

    # 5) 采用余额百分比法或其他组合方法
    t = table(sec, "采用余额百分比法或其他组合方法计提坏账准备的其他应收款项")
    t["headers"] = [
        "组合名称",
        "期末账面余额", "期末计提比例(%)", "期末坏账准备",
        "期初账面余额", "期初计提比例(%)", "期初坏账准备",
    ]
    t["_column_groups"] = [
        {"group": "期末数", "start": 1, "span": 3},
        {"group": "期初数", "start": 4, "span": 3},
    ]
    drop_header_label_rows(t)
    log.append("soe 采用余额百分比法… → 7 列 + _column_groups")

    # 6) 补 4 张缺表（账面余额变动紧随 ECL 变动表；其余 3 张置于章节末）
    fresh = {tb["name"]: tb for tb in new_soe_tables()}
    tables = sec["tables"]
    balance_name = "其他应收款项账面余额变动"
    if not has_table(sec, balance_name):
        anchor = [i for i, tb in enumerate(tables) if tb.get("name") == "其他应收款项坏账准备计提情况"]
        tables.insert(anchor[0] + 1 if anchor else len(tables), fresh[balance_name])
        log.append(f"soe 新增表 {balance_name}")
    for name in (
        "由金融资产转移而终止确认的其他应收款项",
        "其他应收款项转移继续涉入形成的资产、负债的金额",
        "涉及政府补助的应收款项",
    ):
        if not has_table(sec, name):
            tables.append(fresh[name])
            log.append(f"soe 新增表 {name}")

    # 7) text_sections + guidance
    sec["text_sections"] = list(SOE_TEXT_SECTIONS)
    log.append(f"soe text_sections → {len(SOE_TEXT_SECTIONS)} 条")
    set_guidance(sec, SOE_GUIDANCE)
    log.append(f"soe guidance × {len(SOE_GUIDANCE)}")
    return log


def main() -> None:
    listed = load(LISTED)
    soe = load(SOE)
    logs = fix_listed(listed) + fix_soe(soe)
    save(LISTED, listed)
    save(SOE, soe)
    for line in logs:
        print("  ✓", line)
    print(f"\n上市 §五、8 表数：{len(find_section(listed, LISTED_SECTION)['tables'])}")
    print(f"国企 §八、9 表数：{len(find_section(soe, SOE_SECTION)['tables'])}")


if __name__ == "__main__":
    main()
