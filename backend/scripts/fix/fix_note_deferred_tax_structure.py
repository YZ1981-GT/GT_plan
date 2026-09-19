"""幂等修订附注模板「递延所得税资产和递延所得税负债」章节结构。

章节
----
- ``note_template_listed.json`` §五、30 递延所得税资产与递延所得税负债（4 张表）
- ``note_template_soe.json``    §八、31 递延所得税资产和递延所得税负债（5 张表）

权威源
------
``backend/wp_templates/N/N1 递延所得税资产.xlsx``（运行时权威目录）的
``附注披露信息（上市公司）``（A1:K54）与 ``附注披露信息（国企）``（A1:IV74），
逐行 + 合并单元格实测；结论固化在
``.kiro/specs/n1-deferred-tax-disclosure-template-alignment/design.md`` §1。

为什么需要本脚本
----------------
``note_template_*.json`` 由 ``scripts/fix/rebuild_note_from_md.py`` 从附注模版 md 抽取生成，
抽取器会**把多级表头压扁成单行**并把被压扁的第二行表头残留成 ``row_type: header_label``
假数据行。本章节两版的第 1 张表都中招（源模板是 5 列两级表头，模板里只剩 3 列 + 假数据行），
国企第 2 张表还被压成 3 列且整整丢了一张表。故结构修订必须做成幂等脚本 + 契约测试兜底，
禁止直接手改 JSON（下次重建会覆盖）。

修订内容（spec R4）
-------------------
1. 两版表 1：3 列 → 5 列两级表头（``_column_groups``），删 ``header_label`` 假数据行。
   🔴 **子列序两版相反**：上市「可抵扣/应纳税暂时性差异」在前，国企「递延所得税资产/负债」在前。
2. 国企表 2：3 列 → 5 列（报告期末/报告年初 × {互抵后资产或负债, 互抵后可抵扣或应纳税暂时性差异}），
   行骨架由 md 简写的 2 行按源 xlsx 补齐为「资产段明细 + 小计 + 负债段明细 + 小计」。
3. 国企新增表「递延所得税资产和递延所得税负债互抵明细」（源模板（2）B，2 列）。
4. 两版全部表补 ``columns``（单级标 ``flat`` / 两级标 ``group``），
   否则 seed 路径会被 ``_infer_groups_from_headers`` 塞凭空父表头。
5. 两版全部表补 ``guidance``（TAB 页签编制提示）。
6. ``text_sections``：表标题统一 ``#### `` 前缀（否则被当正文），补齐源模板实质披露文本。

修订内容（spec n1-four-table-extraction-and-disclosure-alignment R5）
------------------------------------------------------------------
7. **行集回归源 xlsx**（推翻此前的「行集合不动原则」）。原则原本依据「附注模版 md」，
   但该目录在本仓库**不存在**（``glob('**/*附注模版*')`` 0 命中）→ 据它的结论不可信，
   与 F2 存货 Sprint 7 同款推翻。实测偏差：

   - 上市表 1 资产段只有 5 行且含源模板没有的「开办费」，缺「公允价值变动」
     「购入摊销年限小于税法规定的资产」「其他」；负债段 5 行里 4 行与源模板不符。
   - 国企表 1 / 表 2 同类偏离，且残留 5 处 ``……`` **占位假数据行**
     （平台铁律：模板 rows 里的占位说明是假数据行，会渲染成一行空披露数据 → 必删）。
   - 国企表 2（互抵明细）只有一行 ``……``，而源模板 R56:R58 全空 = **纯动态行区域**。
   - 国企亏损到期表 11 个年度 + ``……`` + 「无使用期限」，源模板只有 6 个年度。

   资产段 7 项与前端 ``N1_ASSET_ITEMS``、后端 ``_N1_ADJUDICATION_CATEGORIES``
   **三处同构**（三者独立演进却都收敛到源模板 R13:R19）—— 这是行集正确性的交叉印证。

8. **报表行编码纠错**：原写 ``BS-018``，DB 只读实证 ``BS-018`` 在上市是「流动资产合计」、
   在国企是「存货」。正确值 ``BS-036``（递延所得税资产）/ ``BS-067``（递延所得税负债），
   四套准则一致。

9. **剥离底层资产负债科目**：原「租赁负债」行挂 ``account_codes=['2601']``、
   「使用权资产」行挂 ``['1641','1642','1643']``。这些是**被计量的底层科目**，
   而本表金额是暂时性差异与递延所得税 —— 一旦取数会把租赁负债余额拉进递延税列。
   附注行只许挂递延所得税科目（``1811`` / ``2901``）。

10. 删除 ``text_sections`` 中**在句中被截断**的证监会指引段（源模板无此内容）。

**为什么行集仍然值得修**：``_source=workpaper`` 时投影器只渲染底稿推来的
``sub_table_data``、不与模板 ``_tables`` 合并，故 seed 行只服务「从未同步过的项目」
与 Word 导出；但那恰恰是现状主导面（全库 346/348 附注章节 ``last_sync_at`` 为 NULL）。

用法::

    python -m scripts.fix.fix_note_deferred_tax_structure --dry-run   # 只打印差异
    python -m scripts.fix.fix_note_deferred_tax_structure             # 就地修订
    python -m scripts.fix.fix_note_deferred_tax_structure --check     # 不一致则 exit 1（CI）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LISTED_PATH = DATA_DIR / "note_template_listed.json"
SOE_PATH = DATA_DIR / "note_template_soe.json"

LISTED_SECTION = "五、30"
SOE_SECTION = "八、31"
ALIGNED_BY = "n1-deferred-tax-disclosure-template-alignment"

AMT = "amount"

# ─────────────────────────── 表名（逐字保持，禁改名）───────────────────────────
# 改名会产生孤儿子表（附注 TAB 永空 + 底稿数据丢失），且 n1NoteSectionMap.ts 的
# N1_SUB_TABLE_KEYS 与本清单是同一契约（n1NoteSubtableContract.spec.ts 双向锁）。
T_UNOFFSET = "未经抵销的递延所得税资产和递延所得税负债"
T_NET_OFFSET = "以抵销后净额列示的递延所得税资产或负债"
T_OFFSET_DETAIL = "递延所得税资产和递延所得税负债互抵明细"  # 国企新增（源模板（2）B）
T_UNRECOGNIZED_LISTED = "未确认递延所得税资产的可抵扣暂时性差异及可抵扣亏损明细"
T_UNRECOGNIZED_SOE = "未确认递延所得税资产明细"
T_LOSS_EXPIRY = "未确认递延所得税资产的可抵扣亏损将于以下年度到期"

# ───────────────── 报表行编码 / 科目白名单（DB 只读实证）─────────────────
# `report_config` 四套准则（listed/soe × standalone/consolidated）全部一致：
#   BS-036 递延所得税资产 = TB('1811','期末余额')
#   BS-067 递延所得税负债 = TB('2901','期末余额')
# 🔴 曾错写 BS-018（实为 上市「流动资产合计」/ 国企「存货」）→ 守卫已钉死。
ASSET_ROW_CODE = "BS-036"
LIABILITY_ROW_CODE = "BS-067"
ASSET_ACCOUNT_CODES = ["1811"]
LIABILITY_ACCOUNT_CODES = ["2901"]
# 附注行只许挂递延所得税科目：本表金额是暂时性差异与递延所得税，
# 挂底层被计量科目（2601 租赁负债 / 1641~1643 使用权资产）会把其余额拉进递延税列。
ALLOWED_ACCOUNT_CODES = {"1811", "2901"}

# ───────────────── 源模板行集（唯一裁决者）─────────────────
# 资产段 = `附注披露信息（上市公司）` R13:R19；国企 R13:R19 用公式引用上市同列，故两版同集。
# 🔴 与前端 `N1_ASSET_ITEMS`、后端 `_N1_ADJUDICATION_CATEGORIES` 三处同构（交叉印证）。
SRC_ASSET_ITEMS = [
    "资产减值准备",
    "可抵扣亏损",
    "内部交易未实现利润",
    "公允价值变动",
    "租赁负债",
    "购入摊销年限小于税法规定的资产",
    "其他",
]

# 负债段 = 两版 R23:R27。🔴 第 4 项两版用语不同：上市 A26「使用权资产」/ 国企 A26「租赁形成」。
SRC_LIABILITY_ITEMS = {
    "listed": [
        "购入摊销年限大于税法规定的资产",
        "可供出售金融资产公允价值变动",
        "投资性房地产公允价值变动",
        "使用权资产",
        "其他",
    ],
    "soe": [
        "购入摊销年限大于税法规定的资产",
        "可供出售金融资产公允价值变动",
        "投资性房地产公允价值变动",
        "租赁形成",
        "其他",
    ],
}

# 亏损到期年度骨架 = 源模板 R46:R51 / R66:R71 共 **6 行**。
# 设计原理：期末（审计年度 Y 末）的亏损到期于 Y+1..Y+5；上年年末（Y-1 末）的到期于 Y..Y+4，
# 两列并集 = Y..Y+5 → 首行只在上年年末列有值（源模板 B46='——'）、
# 末行只在期末列有值（源模板 C51='——'）。
LOSS_EXPIRY_BASE_YEAR = 2025
LOSS_EXPIRY_YEARS = 6

# ─────────────────────────── 行构造 ───────────────────────────


def _row(label: str, **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"label": label}
    row.update(extra)
    row.setdefault("row_type", "data")
    return row


def _subtotal(label: str = "小计") -> dict[str, Any]:
    return {"label": label, "is_total": True, "row_type": "subtotal"}


def _total(label: str = "合计") -> dict[str, Any]:
    return {"label": label, "is_total": True, "row_type": "total"}


# ─────────────────────────── 列构造 ───────────────────────────

_DIFF_LABEL = "可抵扣/应纳税暂时性差异"
_TAX_LABEL = "递延所得税资产/负债"


def _unoffset_sub_order(variant: str) -> list[tuple[str, str]]:
    """表 1 两级表头的子列序。

    🔴 源模板两版相反（实测 B11:E11）：
    - 上市：可抵扣/应纳税暂时性差异 → 递延所得税资产/负债
    - 国企：递延所得税资产/负债 → 可抵扣/应纳税暂时性差异

    同步载荷 ``columns`` 的键序必须与此一致，否则附注列错位。
    """
    if variant == "listed":
        return [("diff", _DIFF_LABEL), ("tax", _TAX_LABEL)]
    return [("tax", _TAX_LABEL), ("diff", _DIFF_LABEL)]


def _unoffset_table(variant: str, rows: list[dict[str, Any]], guidance: str) -> dict[str, Any]:
    """表 1：项目 + 期末余额{2 子列} + {上年年末|期初}余额{2 子列}。"""
    prior_group = "上年年末余额" if variant == "listed" else "年初余额"
    end_group = "期末余额"
    order = _unoffset_sub_order(variant)
    return {
        "name": T_UNOFFSET,
        "headers": ["项目", *[lbl for _, lbl in order], *[lbl for _, lbl in order]],
        "columns": [
            {"key": "label", "label": "项目", "is_label": True},
            *[
                {"key": f"end_{k}", "label": lbl, "group": end_group, "format": AMT}
                for k, lbl in order
            ],
            *[
                {"key": f"prior_{k}", "label": lbl, "group": prior_group, "format": AMT}
                for k, lbl in order
            ],
        ],
        "_column_groups": [
            {"group": end_group, "start": 1, "span": 2},
            {"group": prior_group, "start": 3, "span": 2},
        ],
        "guidance": guidance,
        "rows": rows,
    }


def _flat_columns(specs: list[tuple[str, str, str | None]]) -> list[dict[str, Any]]:
    """单级表头列定义；首列为标签列并带 ``flat`` 显式表态。

    ``flat`` 只需任一列携带（后端 ``_extract_column_groups`` 三态：任一列 flat 即显式单级）。
    """
    out: list[dict[str, Any]] = []
    for i, (key, label, fmt) in enumerate(specs):
        col: dict[str, Any] = {"key": key, "label": label}
        if i == 0:
            col["is_label"] = True
            col["flat"] = True
        if fmt:
            col["format"] = fmt
        out.append(col)
    return out


def _flat_table(
    name: str,
    specs: list[tuple[str, str, str | None]],
    rows: list[dict[str, Any]],
    guidance: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "headers": [label for _, label, _ in specs],
        "columns": _flat_columns(specs),
        "guidance": guidance,
        "rows": rows,
    }


# ═══════════════════════════ 上市 五、30 ═══════════════════════════

def _two_segment_rows(variant: str, asset_label: str, liability_label: str) -> list[dict[str, Any]]:
    """资产段（标题 + 7 项 + 小计）+ 负债段（标题 + 5 项 + 小计），共 16 行。

    表 1（未经抵销）与国企表 2（抵销后净额）同构 —— 源模板国企 A36=``=A13`` …
    A50=``=A27`` 即行标签镜像关系。
    分组标题行承载 BS 报表行映射（``account_codes`` + ``report_row_code``）。
    """
    return [
        _row(
            asset_label,
            account_codes=list(ASSET_ACCOUNT_CODES),
            report_row_code=ASSET_ROW_CODE,
        ),
        *[_row(n) for n in SRC_ASSET_ITEMS],
        _subtotal(),
        _row(
            liability_label,
            account_codes=list(LIABILITY_ACCOUNT_CODES),
            report_row_code=LIABILITY_ROW_CODE,
        ),
        *[_row(n) for n in SRC_LIABILITY_ITEMS[variant]],
        _subtotal(),
    ]


def _loss_expiry_rows() -> list[dict[str, Any]]:
    """6 个年度行 + 合计（源模板 R46:R51 / R66:R71）。"""
    return [
        *[
            _row(f"{y}年")
            for y in range(LOSS_EXPIRY_BASE_YEAR, LOSS_EXPIRY_BASE_YEAR + LOSS_EXPIRY_YEARS)
        ],
        _total(),
    ]


# 上市表 1（源模板 A12「递延所得税资产：」/ A22「递延所得税负债：」，均整行合并）
def _listed_unoffset_rows() -> list[dict[str, Any]]:
    return _two_segment_rows("listed", "递延所得税资产：", "递延所得税负债：")

_G_LISTED_UNOFFSET = (
    "递延所得税资产段与递延所得税负债段分别列示，各段末置「小计」。"
    "负债段数据来源于递延所得税负债底稿（源模板红字：递延所得税负债数据来源于递延所得税负债底稿）。"
    "【提示：连续亏损的情况下，仍将较大金额的未抵扣亏损确认递延所得税资产，"
    "对当期净利润影响较大，甚至扭亏为盈，应当披露相关判断依据】"
    "【提示：产生递延所得税资产的资产减值准备中包括持有待售资产的资产减值准备。】"
    "勾稽：小计 = 段内各明细项之和。"
)

_G_NET_OFFSET_LISTED = (
    "源模板标题括注「不适用的删除」：仅在递延所得税资产与递延所得税负债以抵销后净额列示时填列。"
    "勾稽：抵销后期末余额 = 未经抵销的段小计 − 期末互抵金额。"
)

_G_UNRECOGNIZED_LISTED = (
    "源模板注：列示由于未来能否获得足够的应纳税所得额具有不确定性，"
    "因此没有确认为递延所得税资产的可抵扣暂时性差异和可抵扣亏损。"
    "勾稽：合计 = 可抵扣暂时性差异 + 可抵扣亏损。"
)

_G_LOSS_EXPIRY_LISTED = (
    "源模板注：无法在资产负债表日确定全部可抵扣亏损情况的，"
    "可只填写能确定部分的金额及其到期年度，并在备注栏予以说明。"
    "年度骨架为 6 行（源模板 R46:R51）：期末列的亏损到期于 Y+1~Y+5、"
    "上年年末列到期于 Y~Y+4，两列并集即 Y~Y+5 —— 故首行期末列、末行上年年末列均为「——」。"
    "结转期限长于 5 年（高新技术企业 / 科技型中小企业 10 年）或无使用期限的，按需新增行。"
    "勾稽：本表「合计」= 上表「可抵扣亏损」行（源模板 B40=B52 / C40=C52，期末与上年年末各校验一次）。"
)


def build_listed_tables() -> list[dict[str, Any]]:
    return [
        _unoffset_table("listed", _listed_unoffset_rows(), _G_LISTED_UNOFFSET),
        _flat_table(
            T_NET_OFFSET,
            [
                ("label", "项目", None),
                ("offset_end", "递延所得税资产和负债期末互抵金额", AMT),
                ("net_end", "抵销后递延所得税资产或负债期末余额", AMT),
                ("offset_prior", "递延所得税资产和负债期初互抵金额", AMT),
                ("net_prior", "抵销后递延所得税资产或负债期初余额", AMT),
            ],
            [
                _row(
                    "递延所得税资产",
                    account_codes=list(ASSET_ACCOUNT_CODES),
                    report_row_code=ASSET_ROW_CODE,
                ),
                _row(
                    "递延所得税负债",
                    account_codes=list(LIABILITY_ACCOUNT_CODES),
                    report_row_code=LIABILITY_ROW_CODE,
                ),
            ],
            _G_NET_OFFSET_LISTED,
        ),
        _flat_table(
            T_UNRECOGNIZED_LISTED,
            [
                ("label", "项目", None),
                ("end", "期末余额", AMT),
                ("prior", "上年年末余额", AMT),
            ],
            [_row("可抵扣暂时性差异"), _row("可抵扣亏损"), _total()],
            _G_UNRECOGNIZED_LISTED,
        ),
        _flat_table(
            T_LOSS_EXPIRY,
            [
                ("label", "年份", None),
                ("end", "期末余额", AMT),
                ("prior", "上年年末余额", AMT),
                ("remark", "备注", None),
            ],
            _loss_expiry_rows(),
            _G_LOSS_EXPIRY_LISTED,
        ),
    ]


LISTED_TEXT_SECTIONS = [
    f"#### {T_UNOFFSET}",
    "说明：其中一年后预期转回的递延所得税资产和递延所得税负债分别为X.XX元、X.XX元。",
    "【提示：连续亏损的情况下，仍将较大金额的未抵扣亏损确认递延所得税资产，"
    "对当期净利润影响较大，甚至扭亏为盈，应当披露相关判断依据】",
    "【提示：产生递延所得税资产的资产减值准备中包括持有待售资产的资产减值准备。】",
    # 🔴 已删：md 抽取遗留的证监会《监管规则适用指引——会计类第5号》段落。
    #    ①源模板 `附注披露信息（上市公司）` 无此内容；②该段**在句中被截断**
    #    （止于「其金融负债成分的计税基础等于债券票面金额并」）且带 `**` markdown 残迹
    #    → 落进附注正文与 Word 导出即是一句半截话，交付物层面不可接受。
    #    宁缺勿造：不自造补全，直接移除。
    f"#### {T_NET_OFFSET}（不适用的删除）",
    f"#### {T_UNRECOGNIZED_LISTED}",
    "注：列示由于未来能否获得足够的应纳税所得额具有不确定性，"
    "因此没有确认为递延所得税资产的可抵扣暂时性差异和可抵扣亏损。",
    f"#### {T_LOSS_EXPIRY}",
    "注：无法在资产负债表日确定全部可抵扣亏损情况的，"
    "可只填写能确定部分的金额及其到期年度，并在备注栏予以说明。",
]

# ═══════════════════════════ 国企 八、31 ═══════════════════════════

def _soe_two_segment_rows() -> list[dict[str, Any]]:
    """资产段 + 小计 + 负债段 + 小计（表 1 与表 2 同构）。

    源模板 A12「一、递延所得税资产」/ 表 2 A45「二、递延所得税负债」；
    表 1 的负债段标题源模板写 `递延所得税负债：`，附注模板统一为 `二、递延所得税负债`
    使表 1 与表 2 同构便于对照。
    """
    return _two_segment_rows("soe", "一、递延所得税资产", "二、递延所得税负债")


_G_SOE_UNOFFSET = (
    "递延所得税资产和递延所得税负债**不**以抵销后的净额列示时按本表披露"
    "（以抵销后净额列示的改填下一张表）。"
    "【提示：资产减值准备，含“持有待售资产减值准备”】"
    "【注：计入其他综合收益的其他金融资产为计入其他综合收益的其他债权投资、其他权益工具投资。】"
    "负债段数据来源于递延所得税负债底稿。"
    "勾稽：小计 = 段内各明细项之和。"
)

_G_SOE_NET_OFFSET = (
    "递延所得税资产和递延所得税负债以抵销后的净额列示时按本表披露："
    "列示互抵后的递延所得税资产或负债，及其对应的互抵后可抵扣或应纳税暂时性差异。"
    "勾稽：小计 = 段内各明细项之和。"
)

_G_SOE_OFFSET_DETAIL = (
    "源模板（2）B、递延所得税资产和递延所得税负债互抵明细：按项目列示本期互抵金额。"
    "仅在以抵销后净额列示时填列。"
    "本表为**纯动态行区域**（源模板 R56:R58 全空，无固定行名）：互抵项目由项目实际情况决定，"
    "在底稿披露表按需新增行并自行命名。"
)

_G_SOE_UNRECOGNIZED = (
    "列示由于未来能否获得足够的应纳税所得额具有不确定性，"
    "因此没有确认为递延所得税资产的可抵扣暂时性差异和可抵扣亏损。"
    "勾稽：合计 = 可抵扣暂时性差异 + 可抵扣亏损。"
)

_G_SOE_LOSS_EXPIRY = (
    "【注：无法在资产负债表日确定全部可抵扣亏损情况的，"
    "可只填写能确定部分的金额及其到期年度，并在备注栏予以说明。】"
    "第 3 列口径为「年初余额」（逐字对齐源模板 C65，与表 1 一致）。"
    "年度骨架为 6 行（源模板 R66:R71，首行期末列与末行年初列为「——」）。"
    "结转期限长于 5 年（高新技术企业 / 科技型中小企业 10 年）或无使用期限的，按需新增行。"
    "勾稽：本表「合计」= 上表「可抵扣亏损」行（源模板 B72=B62 / C72=C62）。"
)


def build_soe_tables() -> list[dict[str, Any]]:
    return [
        _unoffset_table("soe", _soe_two_segment_rows(), _G_SOE_UNOFFSET),
        _flat_table(
            T_NET_OFFSET,
            [
                ("label", "项目", None),
                ("net_end", "报告期末互抵后的递延所得税资产或负债", AMT),
                ("diff_end", "报告期末互抵后的可抵扣或应纳税暂时性差异", AMT),
                ("net_prior", "报告年初互抵后的递延所得税资产或负债", AMT),
                ("diff_prior", "报告年初互抵后的可抵扣或应纳税暂时性差异", AMT),
            ],
            _soe_two_segment_rows(),
            _G_SOE_NET_OFFSET,
        ),
        _flat_table(
            T_OFFSET_DETAIL,
            [("label", "项目", None), ("amount", "本期互抵金额", AMT)],
            # 🔴 空行骨架：源模板（2）B 的 R56:R58 **全空** = 纯动态行区域
            #    （互抵项目由项目实际情况决定，无固定行名）。
            #    原实现放一行 `……` 会在附注渲染出一行空披露数据。
            [],
            _G_SOE_OFFSET_DETAIL,
        ),
        _flat_table(
            T_UNRECOGNIZED_SOE,
            [("label", "项目", None), ("end", "期末余额", AMT), ("prior", "年初余额", AMT)],
            [_row("可抵扣暂时性差异"), _row("可抵扣亏损"), _total()],
            _G_SOE_UNRECOGNIZED,
        ),
        _flat_table(
            T_LOSS_EXPIRY,
            [
                ("label", "年份", None),
                ("end", "期末余额", AMT),
                ("prior", "年初余额", AMT),
                ("remark", "备注", None),
            ],
            # 🔴 6 个年度（对齐源模板 R66:R71）。原实现有 11 个年度 + `……` + 「无使用期限」，
            #    源模板均无 —— 10 年结转期（高新技术/科技型中小企业）与「无使用期限」
            #    由底稿动态增行承载（`addLossExpiryRow` 支持可改名行），语义写入 guidance。
            _loss_expiry_rows(),
            _G_SOE_LOSS_EXPIRY,
        ),
    ]


SOE_TEXT_SECTIONS = [
    f"#### {T_UNOFFSET}",
    "递延所得税资产和递延所得税负债不以抵销后的净额列示的，按（1）披露；"
    "若递延所得税资产和递延所得税负债以抵销后的净额列示的，按（2）披露。",
    "【提示：资产减值准备，含“持有待售资产减值准备”】",
    "【注：计入其他综合收益的其他金融资产为计入其他综合收益的其他债权投资、其他权益工具投资。】",
    f"#### {T_NET_OFFSET}",
    f"#### {T_OFFSET_DETAIL}",
    f"#### {T_UNRECOGNIZED_SOE}",
    f"#### {T_LOSS_EXPIRY}",
    "【注：无法在资产负债表日确定全部可抵扣亏损情况的，"
    "可只填写能确定部分的金额及其到期年度，并在备注栏予以说明。】",
]


# ─────────────────────────── apply ───────────────────────────

_PLAN = (
    ("listed", LISTED_PATH, LISTED_SECTION, build_listed_tables, LISTED_TEXT_SECTIONS),
    ("soe", SOE_PATH, SOE_SECTION, build_soe_tables, SOE_TEXT_SECTIONS),
)


def _find_section(data: dict[str, Any], section_number: str) -> dict[str, Any]:
    hits = [s for s in data["sections"] if s.get("section_number") == section_number]
    if len(hits) != 1:
        raise SystemExit(f"期望 {section_number} 恰好 1 个 section，实际 {len(hits)} 个")
    return hits[0]


def _describe(tables: list[dict[str, Any]]) -> str:
    return " / ".join(
        f"{t.get('name')}({len(t.get('headers') or [])}列 {len(t.get('rows') or [])}行)"
        for t in tables
    )


def _row_labels(table: dict[str, Any]) -> list[str]:
    return [str(r.get("label", "")) for r in (table.get("rows") or [])]


def _print_row_diff(old_tables: list[dict[str, Any]], new_tables: list[dict[str, Any]]) -> None:
    """逐表打印行集差异 —— 本脚本的主要改动面在 rows，只报列数看不出来。"""
    by_name_old = {t.get("name"): t for t in old_tables}
    for t in new_tables:
        name = t.get("name")
        old = by_name_old.get(name)
        if old is None:
            print(f"      + 新表 {name}")
            continue
        a, b = _row_labels(old), _row_labels(t)
        if a == b:
            continue
        print(f"      ~ {name}:")
        removed = [x for x in a if x not in b]
        added = [x for x in b if x not in a]
        if removed:
            print(f"          删 {removed}")
        if added:
            print(f"          增 {added}")
        if not removed and not added:
            print(f"          仅行序变化 {a} → {b}")


def apply(*, check_only: bool = False, dry_run: bool = False) -> bool:
    """返回 True 表示存在待修订内容。"""
    any_changed = False
    for variant, path, section_number, build, texts in _PLAN:
        data = json.loads(path.read_text(encoding="utf-8"))
        section = _find_section(data, section_number)
        tables = build()

        changed = (
            section.get("tables") != tables
            or section.get("text_sections") != texts
            or section.get("_aligned_by") != ALIGNED_BY
        )
        if not changed:
            print(f"[{variant}] {section_number} 已对齐（{ALIGNED_BY}），无需修改")
            continue

        any_changed = True
        if check_only or dry_run:
            old = section.get("tables") or []
            print(f"[{variant}] {section_number} 与源模板不一致：")
            print(f"    现状 {len(old)} 表 → {_describe(old) if old else '(无)'}")
            print(f"    目标 {len(tables)} 表 → {_describe(tables)}")
            _print_row_diff(old, tables)
            old_texts = section.get("text_sections") or []
            if old_texts != list(texts):
                dropped = [t for t in old_texts if t not in texts]
                added_t = [t for t in texts if t not in old_texts]
                if dropped:
                    print(f"      文本删 {[t[:40] + '…' for t in dropped]}")
                if added_t:
                    print(f"      文本增 {[t[:40] + '…' for t in added_t]}")
            continue

        section["tables"] = tables
        section["text_sections"] = list(texts)
        section["_aligned_by"] = ALIGNED_BY
        # 保持既有落盘格式（indent=2 / LF / 无尾随换行），避免整文件换行符 diff
        path.write_bytes(
            json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        )
        print(f"[{variant}] {section_number} 已修订：{len(tables)} 张表 / {len(texts)} 个文本节")

    return any_changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只校验不写盘，不一致则 exit 1")
    parser.add_argument("--dry-run", action="store_true", help="只打印差异摘要，不写盘")
    args = parser.parse_args()
    changed = apply(check_only=args.check, dry_run=args.dry_run)
    if args.check and changed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
