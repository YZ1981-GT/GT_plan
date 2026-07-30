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

**行集合不动原则**：表 1 的明细行标签保持附注模板既有（md 派生）集合，不改成源 xlsx 的行名——
附注是交付物，且 ``_source=workpaper`` 时 seed 行会被底稿整表覆盖，行骨架只服务"从未同步过的项目"。
唯一例外是国企表 2（原为 2 行简写，按源 xlsx 补齐为与表 1 同构的明细）。

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

# 表 1 行集合 = 附注模板既有（md 派生），仅删首行 header_label 假数据行。
# 分组标题行保留 row_type=data + account_codes/report_row_code（承载 BS 报表行映射）。
_LISTED_UNOFFSET_ROWS: list[dict[str, Any]] = [
    _row("递延所得税资产：", account_codes=["1811"], report_row_code="BS-018"),
    _row("资产减值准备"),
    _row("内部交易未实现利润"),
    _row("开办费"),
    _row("可抵扣亏损"),
    _row("租赁负债", account_codes=["2601"], report_row_code="BS-042"),
    _subtotal(),
    _row("递延所得税负债："),
    _row("非同一控制企业合并资产评估增值"),
    _row("交易性金融工具、衍生金融工具的估值"),
    _row("计入其他综合收益的应收款项融资公允价值变动"),
    _row("计入其他综合收益的其他债权投资公允价值变动"),
    _row("使用权资产", account_codes=["1641", "1642", "1643"], report_row_code="BS-019"),
    _subtotal(),
]

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
    "勾稽：本表「合计」= 上表「可抵扣亏损」行（源模板 B40=B52 / C40=C52，期末与上年年末各校验一次）。"
)


def build_listed_tables() -> list[dict[str, Any]]:
    return [
        _unoffset_table("listed", _LISTED_UNOFFSET_ROWS, _G_LISTED_UNOFFSET),
        _flat_table(
            T_NET_OFFSET,
            [
                ("label", "项目", None),
                ("offset_end", "递延所得税资产和负债期末互抵金额", AMT),
                ("net_end", "抵销后递延所得税资产或负债期末余额", AMT),
                ("offset_prior", "递延所得税资产和负债上年年末互抵金额", AMT),
                ("net_prior", "抵销后递延所得税资产或负债上年年末余额", AMT),
            ],
            [
                _row("递延所得税资产", account_codes=["1811"], report_row_code="BS-018"),
                _row("递延所得税负债"),
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
            [*[_row(f"{y}年") for y in range(2025, 2031)], _total()],
            _G_LOSS_EXPIRY_LISTED,
        ),
    ]


LISTED_TEXT_SECTIONS = [
    f"#### {T_UNOFFSET}",
    "说明：其中一年后预期转回的递延所得税资产和递延所得税负债分别为X.XX元、X.XX元。",
    "【提示：连续亏损的情况下，仍将较大金额的未抵扣亏损确认递延所得税资产，"
    "对当期净利润影响较大，甚至扭亏为盈，应当披露相关判断依据】",
    "【提示：产生递延所得税资产的资产减值准备中包括持有待售资产的资产减值准备。】",
    # 模板既有原文（md 抽取时已被截断，保留原样不自造补全）
    "按照证监会《监管规则适用指引——会计类第5号》，公司在发行并初始确认可转换债券时，"
    "**若该可转换债券作为复合金融工具、其金融负债成分的计税基础等于债券票面金额并",
    f"#### {T_NET_OFFSET}（不适用的删除）",
    f"#### {T_UNRECOGNIZED_LISTED}",
    "注：列示由于未来能否获得足够的应纳税所得额具有不确定性，"
    "因此没有确认为递延所得税资产的可抵扣暂时性差异和可抵扣亏损。",
    f"#### {T_LOSS_EXPIRY}",
    "注：无法在资产负债表日确定全部可抵扣亏损情况的，"
    "可只填写能确定部分的金额及其到期年度，并在备注栏予以说明。",
]

# ═══════════════════════════ 国企 八、31 ═══════════════════════════

# 资产段 / 负债段明细行（附注模板既有集合，供表 1 与表 2 共用）
_SOE_ASSET_DETAIL = [
    _row("信用减值准备"),
    _row("资产减值准备"),
    _row("交易性金融工具、衍生金融工具的估值"),
    _row("计入其他综合收益的其他金融资产公允价值变动"),
    _row("租赁负债", account_codes=["2601"], report_row_code="BS-042"),
    _row("开办费"),
    _row("可抵扣亏损"),
    _row("……"),
]

_SOE_LIABILITY_DETAIL = [
    _row("交易性金融工具、衍生金融工具的估值"),
    _row("计入其他综合收益的其他金融资产公允价值变动"),
    _row("使用权资产", account_codes=["1641", "1642", "1643"], report_row_code="BS-019"),
    _row("……"),
]


def _soe_two_segment_rows() -> list[dict[str, Any]]:
    """资产段 + 小计 + 负债段 + 小计（表 1 与表 2 同构）。"""
    return [
        _row("一、递延所得税资产"),
        *[dict(r) for r in _SOE_ASSET_DETAIL],
        _subtotal(),
        _row("二、递延所得税负债"),
        *[dict(r) for r in _SOE_LIABILITY_DETAIL],
        _subtotal(),
    ]


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
)

_G_SOE_UNRECOGNIZED = (
    "列示由于未来能否获得足够的应纳税所得额具有不确定性，"
    "因此没有确认为递延所得税资产的可抵扣暂时性差异和可抵扣亏损。"
    "勾稽：合计 = 可抵扣暂时性差异 + 可抵扣亏损。"
)

_G_SOE_LOSS_EXPIRY = (
    "【注：无法在资产负债表日确定全部可抵扣亏损情况的，"
    "可只填写能确定部分的金额及其到期年度，并在备注栏予以说明。】"
    "第 3 列附注口径为「期初余额」（源模板底稿侧称「年初余额」，同一口径）。"
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
            [_row("……")],
            _G_SOE_OFFSET_DETAIL,
        ),
        _flat_table(
            T_UNRECOGNIZED_SOE,
            [("label", "项目", None), ("end", "期末余额", AMT), ("prior", "期初余额", AMT)],
            [_row("可抵扣暂时性差异"), _row("可抵扣亏损"), _total()],
            _G_SOE_UNRECOGNIZED,
        ),
        _flat_table(
            T_LOSS_EXPIRY,
            [
                ("label", "年份", None),
                ("end", "期末余额", AMT),
                ("prior", "期初余额", AMT),
                ("remark", "备注", None),
            ],
            [
                *[_row(f"{y}年") for y in range(2025, 2036)],
                _row("……"),
                _row("无使用期限"),
                _total(),
            ],
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
    return " / ".join(f"{t['name']}({len(t['headers'])}列)" for t in tables)


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
