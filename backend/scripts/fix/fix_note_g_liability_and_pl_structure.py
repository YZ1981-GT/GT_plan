#!/usr/bin/env python
"""补齐 G10/G11/G13/G14 附注披露表 columns 与 guidance（幂等）。

**目标**：附注模板 G10 交易性金融负债 / G11 投资收益 / G13 公允价值变动收益 /
G14 信用减值损失共 8 个章节 12 张表此前**全部缺 `columns`**（`columns: []`）→
seed 路径走 `note_sub_table_projector._infer_groups_from_headers` 前缀推断，
可能凭空造父表头；金额列无 `format=amount`。

所有 12 张表在源模板中均为**单行表头**（无两级分组）→ 一律显式标 `flat`。

权威源（三者互证）：

- `backend/wp_templates/G/` 下对应源 xlsx 的两张披露 sheet（openpyxl 实测列头）；
- `note_template_{listed,soe}.json` 既有 headers（交付物权威）；
- `g{10,11,13,14}NoteSectionMap.ts` / `g11NoteSectionMap.ts` 等的列定义（推送路径已验证）。

章节与表结构：

- **G10 交易性金融负债**（逐表按底稿 G10 两张披露 sheet，R8.4 批 9b-2）
  - Listed §五、34：3 tables —— 主表 5 列（项目/期初余额/本期增加/本期减少/期末余额）、
    指定类明细 4 列（项目/期初余额/期末余额/指定的理由和依据）、公允价值变动 4 列
    （项目/2025年公允价值变动额/因自身信用风险变动引起的公允价值本年变动额/…累计变动额）
  - Listed §五、35：1 table，3 列（项目/期末余额/上年年末余额）
  - Soe §八、34：2 tables —— 主表 3 列（项目/期末公允价值/期初公允价值）、公允价值变动 4 列

- **G11 投资收益**
  - Listed §五、69：2 tables，主表 3 列（项目/本期发生额/上期发生额）
  - Soe §八、70：1 table，3 列（项目/本期发生额/上期发生额）

- **G13 公允价值变动收益**
  - Listed §五、75：2 tables，主表 3 列（产生公允价值变动收益的来源/本期发生额/上期发生额）
  - Soe §八、72：1 table，3 列（产生公允价值变动收益的来源/本期发生额/上期发生额）

- **G14 信用减值损失**
  - Listed §五、76：1 table，3 列（项目/本期发生额/上期发生额）
  - Soe §八、73：1 table，3 列（项目/本期发生额/上期发生额）

Usage::

    python backend/scripts/fix/fix_note_g_liability_and_pl_structure.py --dry-run
    python backend/scripts/fix/fix_note_g_liability_and_pl_structure.py
    python backend/scripts/fix/fix_note_g_liability_and_pl_structure.py --check
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _note_structure_kit import (  # noqa: E402
    AMOUNT,
    TEXT,
    build_cli,
    data_row,
    flat_columns,
    rule,
    run_section,
    total_row,
)

_BACKEND = Path(__file__).resolve().parent.parent.parent
DATA_DIR = _BACKEND / "data"
LISTED_PATH = DATA_DIR / "note_template_listed.json"
SOE_PATH = DATA_DIR / "note_template_soe.json"

ALIGNED_BY = "g-cycle-extraction-mapping-and-disclosure-alignment"

# ═══════════════════════════ Guidance 文本 ═══════════════════════════

GUIDANCE_G10 = (
    "对于指定为以公允价值计量且其变动计入当期损益的金融负债，"
    "需区分企业自身信用风险变动引起的公允价值变动金额计入其他综合收益"
    "和全部利得或损失计入当期损益两种情况（CAS 37 第41-43条）。"
)
GUIDANCE_G11 = (
    "以下不存在的项目可以删除。对于业务处置的收益（含子公司和分公司），"
    "无论直接出售还是先持有待售再出售，均整体计入投资收益。"
)
GUIDANCE_G13 = (
    "以下不存在的项目可以删除。"
    "公允价值变动收益按产生来源分类列示本期发生额与上期发生额。"
)
GUIDANCE_G14 = (
    "损失以「—」号填列，以下不存在的项目可以删除。"
    "信用减值损失按 CAS 22 预期信用损失模型分来源列示。"
)

# ═══════════════════════════ G10 交易性金融负债 ═══════════════════════════

G10_LISTED_SECTION = "五、34"
G10_LISTED_DERIVATIVE_SECTION = "五、35"
G10_SOE_SECTION = "八、34"

# 🔴 逐表定列（R8.4 批 9b-2，2026-10-24）：原先运行时读出本节全部表名、把主表列套给每一张 ⇒ 上市「指定为…理由和
#    依据」表成了变动表（底稿第 18 行是 期初余额 | 期末余额 | 指定的理由和依据）、两版「公允价值的变动情况」表成了
#    变动表 / 余额表（底稿上市第 26 行、国企第 18 行是 公允价值变动额 | 因自身信用风险变动引起的公允价值本年变动额 |
#    …累计变动额），对齐白名单只能整表豁免。列与两版 Word 原表头一致；列键 = 前端载荷 g10DisclosureSyncPayload.ts。
#    表名逐字取模板（= 两版 Word 原文）：上市写 2025 年、国企写 202X 年。表名是模板表的标识、不随审计年度变，审计
#    年度只体现在前端推送的列名里（原先前端按审计年度拼表名，国企恒对不上模板、上市跨年对不上）。
G10_LISTED_MAIN_TABLE = "交易性金融负债"
G10_LISTED_DESIGNATED_TABLE = (
    "1、对于指定为以公允价值计量且其变动计入当期损益的金融负债，应单独列示期初余额、期末余额，并披露指定的理由和依据。"
)
G10_LISTED_FV_TABLE = "对于指定为以公允价值计量且其变动计入当期损益的金融负债，2025年公允价值的变动情况如下表所示："
#: 单表章节，表名 = 章节名（与国企 八、35 同）。5914e315b（Word 同步）把它换成了表前的 15 号文提示段（提示段本就在
#: guidance 里），前端一直推「衍生金融负债」⇒ 别名改回（R8.4 批 9b-2）
G10_LISTED_DERIVATIVE_TABLE = "衍生金融负债"
_G10_LISTED_DERIVATIVE_DAMAGED = (
    "（15号文第二十条（三），分类列示衍生金融负债期初余额、期末余额，披露其形成的原因以及相关会计处理。）"
)
G10_SOE_MAIN_TABLE = "交易性金融负债"
G10_SOE_FV_TABLE = "对于指定为以公允价值计量且其变动计入当期损益的金融负债，202X年公允价值的变动情况如下表所示："

_G10_LISTED_MAIN_COLS = flat_columns([
    ("label", "项目", None),
    ("begin_balance", "期初余额", AMOUNT),
    ("current_increase", "本期增加", AMOUNT),
    ("current_decrease", "本期减少", AMOUNT),
    ("end_balance", "期末余额", AMOUNT),
])
_G10_LISTED_DESIGNATED_COLS = flat_columns([
    ("label", "项目", None),
    ("begin_balance", "期初余额", AMOUNT),
    ("end_balance", "期末余额", AMOUNT),
    ("designation_reason", "指定的理由和依据", TEXT),
])
_G10_LISTED_DERIVATIVE_COLS = flat_columns([
    ("label", "项目", None),
    ("end_balance", "期末余额", AMOUNT),
    ("prior_balance", "上年年末余额", AMOUNT),
])
_G10_SOE_MAIN_COLS = flat_columns([
    ("label", "项目", None),
    ("end_fv", "期末公允价值", AMOUNT),
    ("begin_fv", "期初公允价值", AMOUNT),
])


def _g10_fv_cols(year_text: str) -> list[dict]:
    """公允价值变动表（两版同构，首个金额列名带 Word 原文年份）。"""
    return flat_columns([
        ("label", "项目", None),
        ("fv_change_amount", f"{year_text}年公允价值变动额", AMOUNT),
        ("credit_risk_current", "因自身信用风险变动引起的公允价值本年变动额", AMOUNT),
        ("credit_risk_cumulative", "因自身信用风险变动引起的公允价值累计变动额", AMOUNT),
    ])


#: 主表行按底稿（上市第 8~15 行 / 国企第 8~14 行）：两组「其中」各带父行（底稿 B8 = B9+B10+B11 求和）。
#: 原先上市是 Word 的空「其中：」占位行，国企缺「衍生金融负债」与指定类下的「其他」
_G10_LISTED_MAIN_ROWS = [
    data_row("交易性金融负债"),
    data_row("其中：发行的交易性债券"),
    data_row("衍生金融负债"),
    data_row("其他"),
    data_row("指定为以公允价值计量且其变动计入当期损益的金融负债"),
    data_row("其中：债券"),
    data_row("其他"),
    total_row("合计"),
]
_G10_SOE_MAIN_ROWS = [
    data_row("交易性金融负债"),
    data_row("其中：发行的交易性债券"),
    data_row("衍生金融负债"),
    data_row("其他"),
    data_row("指定为以公允价值计量且其变动计入当期损益的金融负债"),
    data_row("其他"),
    total_row("合计"),
]
GUIDANCE_G10_DERIVATIVE = (
    "（提示：企业衍生金融工具业务具有重要性的，单独披露衍生金融负债。）\n"
    "（15号文第二十条（三），分类列示衍生金融负债期初余额、期末余额，披露其形成的原因以及相关会计处理。）"
)

# ═══════════════════════════ G11 投资收益 ═══════════════════════════

G11_LISTED_SECTION = "五、69"
G11_SOE_SECTION = "八、70"

_G11_COLS = flat_columns([
    ("label", "项目", None),
    ("current_amount", "本期发生额", AMOUNT),
    ("prior_amount", "上期发生额", AMOUNT),
])

# ═══════════════════════════ G13 公允价值变动收益 ═══════════════════════════

G13_LISTED_SECTION = "五、75"
G13_SOE_SECTION = "八、72"

_G13_COLS = flat_columns([
    ("label", "产生公允价值变动收益的来源", None),
    ("current_amount", "本期发生额", AMOUNT),
    ("prior_amount", "上期发生额", AMOUNT),
])

# ═══════════════════════════ G14 信用减值损失 ═══════════════════════════

G14_LISTED_SECTION = "五、76"
G14_SOE_SECTION = "八、73"

_G14_COLS = flat_columns([
    ("label", "项目", None),
    ("current_amount", "本期发生额", AMOUNT),
    ("prior_amount", "上期发生额", AMOUNT),
])


# ═══════════════════════════ 章节计划 ═══════════════════════════

def _g10_listed_plan(_tables: list[str]) -> list[dict]:
    """G10 Listed 五、34：主表 + 指定类明细 + 公允价值变动（逐表定列，见 G10 常量注释）。"""
    return [
        rule(G10_LISTED_MAIN_TABLE, _G10_LISTED_MAIN_COLS, _G10_LISTED_MAIN_ROWS, GUIDANCE_G10),
        rule(G10_LISTED_DESIGNATED_TABLE, _G10_LISTED_DESIGNATED_COLS, None, GUIDANCE_G10),
        rule(G10_LISTED_FV_TABLE, _g10_fv_cols("2025"), None, GUIDANCE_G10),
    ]


def _g10_listed_derivative_plan(_tables: list[str]) -> list[dict]:
    """G10 Listed 五、35 衍生金融负债：列键随前端载荷（原为列名当键）。"""
    return [rule(G10_LISTED_DERIVATIVE_TABLE, _G10_LISTED_DERIVATIVE_COLS, None, GUIDANCE_G10_DERIVATIVE,
                 aliases=[_G10_LISTED_DERIVATIVE_DAMAGED])]


def _g10_soe_plan(_tables: list[str]) -> list[dict]:
    """G10 Soe 八、34：主表 + 公允价值变动（逐表定列）。"""
    return [
        rule(G10_SOE_MAIN_TABLE, _G10_SOE_MAIN_COLS, _G10_SOE_MAIN_ROWS, GUIDANCE_G10),
        rule(G10_SOE_FV_TABLE, _g10_fv_cols("202X"), None, GUIDANCE_G10),
    ]


def _g11_listed_plan(tables: list[str]) -> list[dict]:
    """G11 Listed 五、69：2 tables，全部使用相同 3 列结构。"""
    return [rule(name, _G11_COLS, None, GUIDANCE_G11) for name in tables]


def _g11_soe_plan(tables: list[str]) -> list[dict]:
    """G11 Soe 八、70：1 table。"""
    return [rule(name, _G11_COLS, None, GUIDANCE_G11) for name in tables]


def _g13_listed_plan(tables: list[str]) -> list[dict]:
    """G13 Listed 五、75：2 tables（主表+套保明细），同结构。"""
    return [rule(name, _G13_COLS, None, GUIDANCE_G13) for name in tables]


def _g13_soe_plan(tables: list[str]) -> list[dict]:
    """G13 Soe 八、72：1 table。"""
    return [rule(name, _G13_COLS, None, GUIDANCE_G13) for name in tables]


def _g14_listed_plan(tables: list[str]) -> list[dict]:
    """G14 Listed 五、76：1 table。"""
    return [rule(name, _G14_COLS, None, GUIDANCE_G14) for name in tables]


def _g14_soe_plan(tables: list[str]) -> list[dict]:
    """G14 Soe 八、73：1 table。"""
    return [rule(name, _G14_COLS, None, GUIDANCE_G14) for name in tables]


# ═══════════════════════════ 表名发现（运行时从模板读取） ═══════════════════════════

import json  # noqa: E402


def _get_table_names(path: Path, section_number: str) -> list[str]:
    """从模板 JSON 中读取指定章节的所有表名。"""
    doc = json.loads(path.read_text(encoding="utf-8"))
    for sec in doc.get("sections", []):
        if str(sec.get("section_number", "")) == section_number:
            tables = sec.get("tables") or []
            return [str(t.get("name", "")) for t in tables]
    return []


# ═══════════════════════════ 统一调度 ═══════════════════════════

_TARGETS: dict[str, tuple[Path, str, type]] = {}
_LABELS: dict[str, str] = {}

# 按章节键注册：{cycle}_{variant}
_CHAPTER_DEFS: list[tuple[str, str, Path, str, object]] = [
    ("g10_listed", "G10 交易性金融负债（上市 §五、34）", LISTED_PATH, G10_LISTED_SECTION, _g10_listed_plan),
    ("g10_listed_derivative", "G10 衍生金融负债（上市 §五、35）", LISTED_PATH, G10_LISTED_DERIVATIVE_SECTION,
     _g10_listed_derivative_plan),
    ("g10_soe", "G10 交易性金融负债（国企 §八、34）", SOE_PATH, G10_SOE_SECTION, _g10_soe_plan),
    ("g11_listed", "G11 投资收益（上市 §五、69）", LISTED_PATH, G11_LISTED_SECTION, _g11_listed_plan),
    ("g11_soe", "G11 投资收益（国企 §八、70）", SOE_PATH, G11_SOE_SECTION, _g11_soe_plan),
    ("g13_listed", "G13 公允价值变动收益（上市 §五、75）", LISTED_PATH, G13_LISTED_SECTION, _g13_listed_plan),
    ("g13_soe", "G13 公允价值变动收益（国企 §八、72）", SOE_PATH, G13_SOE_SECTION, _g13_soe_plan),
    ("g14_listed", "G14 信用减值损失（上市 §五、76）", LISTED_PATH, G14_LISTED_SECTION, _g14_listed_plan),
    ("g14_soe", "G14 信用减值损失（国企 §八、73）", SOE_PATH, G14_SOE_SECTION, _g14_soe_plan),
]


#: 表名复位后要摘掉 `#### ` 前缀的段落（与 `aliases=[..._DAMAGED]` 成对，见
#: `_note_structure_kit.untitleize_text_sections`）。5914e315b 把提示段当成了表名，之后有人给那条
#: 提示段加了 `#### ` 当标题让「每张表都有小节标题」过关；表名复位后标题就多了一个，`disclosure_engine`
#: 段落游标会多走一格、把后续提示段错配到别的表。受损前（5914e315b~1）它是普通正文段 ⇒ 摘回去
#: （R8.4 批 9b-2，2026-10-25；逐条取证见 design §17.6）。
_UNTITLE_AFTER_RESTORE: dict[str, list[str]] = {
    "g10_listed_derivative": [_G10_LISTED_DERIVATIVE_DAMAGED],
}


def _runner(key: str, dry_run: bool, check: bool):
    for chap_key, label, path, section_number, plan_fn in _CHAPTER_DEFS:
        if chap_key == key:
            table_names = _get_table_names(path, section_number)
            if not table_names:
                return [], [f"章节 {section_number} 无表或不存在（{path.name}）"], []
            plan = plan_fn(table_names)
            return run_section(
                path,
                section_number,
                plan,
                # 期望表名取计划本身：G10 逐表写死（缺表 / 改名 --check 报欠账），G11/G13/G14 仍按现有表名
                [r["new_name"] for r in plan],
                aligned_by=ALIGNED_BY,
                dry_run=dry_run,
                check=check,
                untitle_text_sections=_UNTITLE_AFTER_RESTORE.get(key),
            )
    return [], [f"未知键：{key}"], []


_LABELS = {chap_key: label for chap_key, label, *_ in _CHAPTER_DEFS}

main = build_cli(
    "补齐 G10/G11/G13/G14 附注披露表 columns 与 guidance（幂等）",
    _runner,
    _LABELS,
)

if __name__ == "__main__":
    raise SystemExit(main())
