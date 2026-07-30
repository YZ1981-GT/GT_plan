#!/usr/bin/env python
"""H1 固定资产附注章节结构对齐（幂等脚本）.

对齐目标
--------
- ``note_template_listed.json`` §五、22「固定资产」（6 张表）
- ``note_template_soe.json``    §八、22「固定资产」（5 张表）

权威源
------
``基础数据/致同通用审计程序及底稿模板（2025年修订）/1.致同审计程序及底稿模板（2025年）/
4.风险应对-实质性程序（D-N）/H 固定资产循环/H1 固定资产.xlsx``
的 sheet ``附注披露信息（上市公司）``（A1:F93）与 ``附注披露信息（国有企业）``（A1:F78）。

做四件事
--------
1. **列结构修复**：上市「固定资产情况」表头的 ``……`` 占位列展开为平台五类
   （办公设备 / 其他设备），与前端 ``buildH1ListedColumns`` 推送的列名逐字一致；
   否则同步后附注 TAB 出现孤儿列 + 底稿数据丢失（披露子表名契约铁律）。
   展开依据：源模板 R52 红字「此处分类应与固定资产项目注释的分类保持一致」+
   平台共用口径 ``H1_FA_CATEGORIES``（电子设备归一到办公设备）。
2. **删假数据行**：源模板 A65 / A74 的「可无限量添加行」是模板占位说明，
   被 md 重建脚本当成数据行落进 ``rows``，会渲染成一行假披露数据 → 删除，
   语义移入对应表 ``guidance``。
3. **显式 guidance**（TAB 页签编制提示）：11 张表全部声明。
   内容只取源模板红字 / 15号文条款 / 以「勾稽：」前缀标注的工具提示。
   显式声明经 ``disclosure_engine._carry_seed_table_guidance`` **优先于**
   ``text_sections`` 段落游标推断——H1 的游标推断有两处错位：
   上市「本期冲减…政府补助金额为XXX元」被 ``_match_title_to_table_idx``
   包含匹配吞成表 0 的标题（实质文本被丢弃 + 后续提示错落到汇总表）；
   国企缺汇总表标题导致「注：…清理进展」落进正文而非清理表提示。
4. **text_sections 修正**：
   - 上市：政府补助那句去掉 ``#### `` 前缀，使其作为实质正文进 ``text_content``
     （源模板 R84 是⑤小节正文，不是表标题）；
   - 国企：补 ``### 固定资产``（源模板 R6「15、固定资产」汇总表标题），
     使 5 张表都有对应小节标题。

幂等：可重复运行，结果稳定。
"""

from __future__ import annotations

import json
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
LISTED = BACKEND / "data" / "note_template_listed.json"
SOE = BACKEND / "data" / "note_template_soe.json"

LISTED_SECTION = "五、22"
SOE_SECTION = "八、22"

#: 源模板 A65 / A74 的模板占位说明，误落为数据行
PLACEHOLDER_ROW_LABEL = "可无限量添加行"

#: 上市「固定资产情况」列头 = 标签列 + 平台五类 + 合计
#: 逐字对齐前端 ``buildH1ListedColumns``（H1_LISTED_DEFAULT_CATEGORIES 顺序）
LISTED_MOVEMENT_HEADERS = [
    "项目",
    "房屋及建筑物",
    "机器设备",
    "运输设备",
    "办公设备",
    "其他设备",
    "合计",
]


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


def drop_placeholder_rows(t: dict) -> int:
    before = len(t.get("rows") or [])
    t["rows"] = [
        r for r in (t.get("rows") or [])
        if str(r.get("label") or "").strip() != PLACEHOLDER_ROW_LABEL
    ]
    return before - len(t["rows"])


def set_guidance(section: dict, mapping: dict[str, str]) -> None:
    for name, text in mapping.items():
        table(section, name)["guidance"] = text


# ─── 上市 §五、22 ────────────────────────────────────────────────────────────

LISTED_GUIDANCE = {
    "固定资产": (
        "汇总表（源模板 R7–R10）：固定资产 + 固定资产清理 = 合计。"
        "勾稽：固定资产行期末余额 = 「固定资产情况」表「四、账面价值 / 1.期末账面价值」合计列；"
        "上年年末余额 = 「2.期初账面价值」合计列；固定资产清理行 = 「固定资产清理」表合计；"
        "本表合计 = 资产负债表「固定资产」项目。"
    ),
    "固定资产情况": (
        "【1、长期资产本期进行减值测试的，应披露可收回金额的具体确定方法。"
        "可收回金额按公允价值减去处置费用后的净额确定的，应披露公允价值和处置费用的确定方式、"
        "关键参数及其确定依据。可收回金额按预计未来现金流量的现值确定的，应披露预测期的年限、"
        "预测期及稳定期的关键参数及其确定依据。前述信息与以前年度减值测试采用的信息或外部信息"
        "明显不一致的，或公司以前年度减值测试采用信息与当年实际情况明显不一致的，应披露差异原因。"
        "（15号文第十九条（十九））】\n"
        "注意：1、本年执行减值测试的，即使未计提减值，也要参照上述要求披露。"
        "2、估计可收回金额时通常不应使用重置成本法。\n"
        "2、说明抵押、担保的固定资产情况。\n"
        "3、本期发生以明显高于账面价值的价格出售固定资产交易的，应详细说明交易作价的基础和依据，"
        "如：估值模型、重要参数的选取依据和估值过程，以及必要的敏感性分析。\n"
        "【提示：在“其他减少”中列示本期收到的政府补助冲减固定资产账面价值的金额。"
        "对于冲减无形资产或其他资产账面价值的政府补助，比照披露。】\n"
        "【提示：非同一控制下企业合并中取得被购买方的资产、负债等应按购买日公允价值计量，"
        "因此新并购固定资产的增加应以净额列示。新并购无形资产或其他资产的增加，"
        "相关科目附注比照上述要求进行列示。】\n"
        "勾稽：期末余额 = 期初余额 + 本期增加金额 − 本期减少金额（原值/累计折旧/减值准备三层各自成立）；"
        "账面价值 = 账面原值 − 累计折旧 − 减值准备；合计列 = 各资产类别之和。"
        "资产类别应与附注三、固定资产会计政策披露的折旧年限分类保持一致，"
        "类别不足时按被审计单位实际情况在底稿「+ 增加资产类别列」扩展。"
    ),
    "暂时闲置的固定资产情况": (
        "（提示：《关于严格执行企业会计准则 切实做好企业2025年年报工作的通知》："
        "企业对于停工项目、闲置资产等的减值情况应予以特别关注，并对是否发生减值作出恰当判断"
        "和相应会计处理。）\n"
        "勾稽：账面价值 = 账面原值 − 累计折旧 − 减值准备。"
        "行按被审计单位实际闲置资产类别可无限量添加（源模板 A65）；底稿可从 H1-4 闲置检查表同步。"
    ),
    "通过经营租赁租出的固定资产": (
        "按资产类别列示期末经营租出固定资产的账面价值。"
        "行可无限量添加（源模板 A74）；底稿可从 H1-19 经营租出固定资产检查表同步。\n"
        "勾稽：本表账面价值合计应与租赁准则下出租人披露（经营租赁租金收入）的资产口径一致，"
        "且不得超过「固定资产情况」表期末账面价值合计。"
    ),
    "未办妥产权证书的固定资产情况": (
        "（披露期末未办妥产权证书的固定资产账面价值及原因。）\n"
        "底稿可从 H1-16 房屋建筑物权属检查表同步（未取得权证、或在建转固且无证号的资产）。"
    ),
    "固定资产清理": (
        "（说明转入固定资产清理起始时间已超过1年的固定资产清理进展情况）\n"
        "勾稽：合计期末余额 = 汇总表「固定资产清理」行期末余额；"
        "上年年末余额同口径核对。底稿可从 H6 固定资产清理底稿同步。"
    ),
}

#: 源模板 R84 是⑤小节正文（不是表标题）——带 `#### ` 前缀会被
#: `_is_table_title_paragraph` 判为标题并**丢弃**，导致实质披露文本消失。
LISTED_GOV_SUBSIDY_HEADING = (
    "#### 本期冲减固定资产账面价值的政府补助金额为XXX元，具体情况见附注八、政府补助。"
)
LISTED_GOV_SUBSIDY_TEXT = (
    "本期冲减固定资产账面价值的政府补助金额为XXX元，具体情况见附注八、政府补助。"
)


def fix_listed(data: dict) -> list[str]:
    log: list[str] = []
    sec = find_section(data, LISTED_SECTION)

    # 1) 「固定资产情况」列头：`……` 占位列 → 平台五类
    t = table(sec, "固定资产情况")
    if t.get("headers") != LISTED_MOVEMENT_HEADERS:
        t["headers"] = list(LISTED_MOVEMENT_HEADERS)
        log.append(f"listed 固定资产情况 → {len(LISTED_MOVEMENT_HEADERS)} 列（展开 `……` 占位列）")

    # 2) 删「可无限量添加行」假数据行
    for name in ("暂时闲置的固定资产情况", "通过经营租赁租出的固定资产"):
        dropped = drop_placeholder_rows(table(sec, name))
        if dropped:
            log.append(f"listed {name} → 删除 {dropped} 行「{PLACEHOLDER_ROW_LABEL}」假数据行")

    # 3) text_sections：政府补助小节正文去 `#### ` 前缀
    ts = list(sec.get("text_sections") or [])
    if LISTED_GOV_SUBSIDY_HEADING in ts:
        ts[ts.index(LISTED_GOV_SUBSIDY_HEADING)] = LISTED_GOV_SUBSIDY_TEXT
        sec["text_sections"] = ts
        log.append("listed text_sections → 政府补助小节由假标题改为实质正文")

    # 4) guidance
    set_guidance(sec, LISTED_GUIDANCE)
    log.append(f"listed guidance × {len(LISTED_GUIDANCE)}")
    return log


# ─── 国企 §八、22 ────────────────────────────────────────────────────────────

SOE_GUIDANCE = {
    "固定资产": (
        "汇总表（源模板 R7–R10）：固定资产 + 固定资产清理 = 合计。"
        "勾稽：固定资产行 = 「固定资产情况」表「五、固定资产账面价值合计」的期末/期初余额；"
        "固定资产清理行 = 「固定资产清理」表合计（可从 H6 同步）；"
        "本表合计 = 资产负债表「固定资产」项目。"
        "注意国企口径列名为「期末账面价值 / 期初账面价值」，不同于上市的「期末余额 / 上年年末余额」。"
    ),
    "固定资产情况": (
        "国企五层结构（源模板 R14–R58）：一、账面原值合计 → 二、累计折旧合计 → "
        "三、固定资产账面净值合计 → 四、固定资产减值准备合计 → 五、固定资产账面价值合计；"
        "每层下以「其中：」列示土地资产 / 房屋、建筑物 / 机器设备 / 运输工具 / 电子设备 / "
        "办公设备 / 酒店业家具 / 其他。\n"
        "勾稽：期末余额 = 期初余额 + 本期增加 − 本期减少（原值 / 累计折旧 / 减值准备三层各自成立）；"
        "账面净值 = 账面原值 − 累计折旧；账面价值 = 账面净值 − 减值准备；"
        "各层合计行 = 该层「其中：」各类别之和。\n"
        "源模板列示约定：账面净值层与账面价值层的「本期增加 / 本期减少」列填「—」（推导列不作变动分析）；"
        "土地资产不计提折旧，累计折旧层该行整行填「—」。"
    ),
    "暂时闲置的固定资产情况": (
        "按资产类别列示暂时闲置固定资产的账面原值、累计折旧、减值准备、账面价值及备注。"
        "勾稽：账面价值 = 账面原值 − 累计折旧 − 减值准备；合计行 = 各明细行之和。"
        "底稿可从 H1-4 闲置检查表同步。停工项目、闲置资产的减值情况应予特别关注并作出恰当判断。"
    ),
    "未办妥产权证书的固定资产情况": (
        "披露期末未办妥产权证书的固定资产账面价值及未办妥原因。"
        "底稿可从 H1-16 房屋建筑物权属检查表同步（未取得权证、或在建转固且无证号的资产）。"
        "勾稽：合计不得超过「固定资产情况」表期末账面价值合计。"
    ),
    "固定资产清理": (
        "注：说明转入固定资产清理起始时间已超过1年的固定资产清理进展情况。\n"
        "勾稽：合计期末账面价值 = 汇总表「固定资产清理」行期末账面价值；期初同口径核对。"
        "底稿可从 H6 固定资产清理底稿同步。"
    ),
}

#: 源模板 R6「15、固定资产」+ R7–R10 汇总表 —— 原 text_sections 缺此标题，
#: 汇总表（tables[0]）在渲染时没有对应小节标题。
SOE_SUMMARY_HEADING = "### 固定资产"


def fix_soe(data: dict) -> list[str]:
    log: list[str] = []
    sec = find_section(data, SOE_SECTION)

    # 1) text_sections：补汇总表小节标题
    ts = list(sec.get("text_sections") or [])
    if SOE_SUMMARY_HEADING not in ts:
        ts.insert(0, SOE_SUMMARY_HEADING)
        sec["text_sections"] = ts
        log.append(f"soe text_sections → 首插「{SOE_SUMMARY_HEADING}」（汇总表小节标题）")

    # 2) guidance
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
        print("  [ok]", line)
    lsec = find_section(listed, LISTED_SECTION)
    ssec = find_section(soe, SOE_SECTION)
    print(f"\n上市 §{LISTED_SECTION} 表数：{len(lsec['tables'])}")
    print(f"国企 §{SOE_SECTION} 表数：{len(ssec['tables'])}")


if __name__ == "__main__":
    main()
