"""附注模板 五、5「应收账款」结构对齐源模板（幂等修订脚本）

spec: d2-ar-disclosure-template-alignment — Task 7.1

**为什么需要本脚本**：`note_template_listed.json` 由 `scripts/fix/rebuild_note_from_md.py`
从 `基础数据/附注模版/上市报表附注.md` 抽取生成，抽取器会把 md 里的**多行表头压扁成单行**
（三级表头 `类 别 | 账面余额{金额,比例} | 坏账准备{金额,损失率} | 账面价值` 被压成
`类别 | 期末余额 | 上年年末余额`），并把双期两张表合并成一张。故直接手改 JSON 会在下次
重建时丢失——本脚本以致同源模板
`D2-1至D2-4 应收账款-审定表明细表（Leap-常规程序）.xlsx` 的 `附注披露信息(上市公司)`
sheet（A1:I181）为权威结构真源，重写 五、5 的 `tables` 与补齐 `text_sections`。

**重建后须重跑本脚本**（契约测试 `tests/services/test_note_ar_listed_structure.py` 兜底）。

用法::

    python scripts/fix/fix_note_ar_listed_structure.py            # 写入
    python scripts/fix/fix_note_ar_listed_structure.py --dry-run  # 只看差异

幂等：以表名集合与 `_aligned_by` 标记判断，重复执行结果完全相等（Property 8）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = _BACKEND / "data" / "note_template_listed.json"

SECTION_NUMBER = "五、5"
ALIGNED_BY = "d2-ar-disclosure-template-alignment"

# ─── 行/表构造助手 ────────────────────────────────────────────────────────────


def _row(label: str, row_type: str = "data", **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"label": label, "row_type": row_type}
    if row_type in ("total", "subtotal"):
        row["is_total"] = True
    row.update(extra)
    return row


def _blank_rows(n: int) -> list[dict[str, Any]]:
    """空白录入行（源模板留空行，供审计师逐行填写）。"""
    return [_row("", "data") for _ in range(n)]


def _table(
    name: str,
    headers: list[str],
    rows: list[dict[str, Any]],
    *,
    column_groups: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    tbl: dict[str, Any] = {"name": name, "headers": headers, "rows": rows}
    if column_groups:
        tbl["_column_groups"] = column_groups
    tbl["_aligned_by"] = ALIGNED_BY
    return tbl


# ─── 源模板结构定义 ──────────────────────────────────────────────────────────

# （1）按账龄披露：源模板 r7~r20
AGING_HEADERS = ["账 龄", "期末余额", "上年年末余额"]
AGING_ROWS = [
    _row("1年以内"),
    _row("其中：0-X个月"),
    _row("X-Y个月"),
    _row("1年以内小计：", "subtotal"),
    _row("1至2年"),
    _row("2至3年"),
    _row("3至4年"),
    _row("4至5年"),
    _row("5年以上"),
    _row("小  计", "subtotal"),
    _row("减：坏账准备"),
    _row("合  计", "total"),
]

# （2）按坏账计提方法分类披露：源模板 r22~r36（期末）/ r38~r49（续：上年年末）
CLASS_HEADERS = ["类 别", "金额", "比例(%)", "金额", "预期信用损失率(%)", "账面价值"]
CLASS_COLUMN_GROUPS = [
    {"group": "账面余额", "start": 1, "span": 2},
    {"group": "坏账准备", "start": 3, "span": 2},
]


def _class_rows() -> list[dict[str, Any]]:
    return [
        _row("按单项计提坏账准备"),
        _row("其中："),
        *_blank_rows(2),
        _row("按组合计提坏账准备【注意：与会计政策中披露的组合保持一致】"),
        _row("其中："),
        _row("应收中央企业客户"),
        _row("应收海外企业客户"),
        _row("合  计", "total"),
    ]


# （2-a）按单项计提坏账准备的应收账款：源模板 r51~r56（期末）/ r58~r63（续）
INDIVIDUAL_HEADERS = ["名 称", "账面余额", "坏账准备", "预期信用损失率（%）", "计提依据"]


def _individual_rows() -> list[dict[str, Any]]:
    return [*_blank_rows(3), _row("合  计", "total", values=[None, None, None, "/"])]


# （2-b）组合计提分表：源模板 r66~r74（每组合一张，双期各 3 列）
PORTFOLIO_HEADERS = [
    "账龄",
    "应收账款", "坏账准备", "预期信用损失率(%)",
    "应收账款", "坏账准备", "预期信用损失率(%)",
]
PORTFOLIO_COLUMN_GROUPS = [
    {"group": "期末余额", "start": 1, "span": 3},
    {"group": "上年年末余额", "start": 4, "span": 3},
]
PORTFOLIO_AGING_LABELS = ["1年以内", "1-2年", "2-3年", "3-4年", "4-5年", "5年以上"]


def _portfolio_rows() -> list[dict[str, Any]]:
    return [*(_row(lbl) for lbl in PORTFOLIO_AGING_LABELS), _row("合  计", "total")]


# （3）坏账准备变动：源模板 r116~r123（首行为「上年年末余额」）
MOVEMENT_HEADERS = ["项 目", "坏账准备金额"]
MOVEMENT_ROWS = [
    _row("上年年末余额"),
    _row("本期计提"),
    _row("本期收回或转回"),
    _row("本期核销"),
    _row("[本期转销]"),
    _row("[其他]"),
    _row("期末余额", "total"),
]

REVERSAL_HEADERS = ["单位名称", "转回原因", "收回方式", "原确定坏账准备的依据", "转回或收回金额"]
WRITEOFF_AMOUNT_HEADERS = ["项  目", "核销金额"]
WRITEOFF_DETAIL_HEADERS = [
    "单位名称", "应收账款性质", "核销金额", "核销原因", "履行的核销程序", "款项是否由关联交易产生",
]
TOP5_HEADERS = [
    "单位名称",
    "应收账款期末余额",
    "合同资产期末余额",
    "应收账款和合同资产期末余额",
    "占应收账款和合同资产期末余额合计数的比例%",
    "应收账款坏账准备和合同资产减值准备期末余额",
]
DERECOGNIZED_HEADERS = ["项  目", "转移方式", "终止确认金额", "与终止确认相关的利得或损失"]
CONTINUED_INVOLVEMENT_HEADERS = [
    "项  目", "资产转移方式", "继续涉入形成的资产金额", "继续涉入形成的负债金额",
]

# 表名（与 d2NoteSectionMap.D2_TABLE_NAMES.listed 逐字一致，续表键补「（续：上年年末余额）」）
T_AGING = "按账龄披露"
T_CLASS_END = "按坏账计提方法分类披露"
T_CLASS_PRIOR = "按坏账计提方法分类披露（续：上年年末余额）"
T_IND_END = "按单项计提坏账准备的应收账款"
T_IND_PRIOR = "按单项计提坏账准备的应收账款（续：上年年末余额）"
T_MOVEMENT = "本期计提、收回或转回的坏账准备情况"
T_REVERSAL = "转回或收回金额重要的坏账准备"
T_WRITEOFF_AMOUNT = "本期实际核销的应收账款情况"
T_WRITEOFF_DETAIL = "重要的应收账款核销情况（逐项披露）"
T_TOP5 = "按欠款方归集的应收账款和合同资产期末余额前五名单位情况"
T_DERECOGNIZED = "因金融资产转移而终止确认的应收账款情况"
T_CONTINUED_INVOLVEMENT = "转移应收账款且继续涉入形成的资产、负债"

# 组合分表示例名：沿用模板既有 5 个（来自 md 抽取，不臆造新名）
PORTFOLIO_FALLBACK_NAMES = [
    "组合计提项目：应收中央企业客户",
    "组合计提项目：应收地方国有企业客户",
    "组合计提项目：应收海外企业客户",
    "组合计提项目：组合4",
    "组合计提项目：组合5",
]

# 补齐的 text_sections（源模板 r161/r167~r171/r173/r181），仅在缺失时追加
TEXT_SECTIONS_APPEND = [
    "### 因金融资产转移而终止确认的应收账款情况",
    (
        "【15号文第五十一条 公司发生金融资产转移的，应按照金融资产转移方式分类列示已转移金融资产性质及金额、"
        "终止确认情况及其判断依据。因转移而终止确认的金融资产，应分项列示金融资产转移的方式、"
        "终止确认的金融资产金额，及与终止确认相关的利得或损失。】"
    ),
    (
        "A、期末，本公司因办理了不附追索权的应收账款保理，保理金额为XXX元，同时终止确认应收账款账面价值为XXX元，"
        "账面余额为XXX元，账龄为一年以内，已计提坏账准备XXX元。"
    ),
    (
        "B、【不符合终止确认条件的应收账款的转移，应在附注中单独列示其金额。参考披露格式："
        "期末，本公司共有账面价值为XXX元的应收账款，办理了附追索权的应收账款保理，账面余额为XXX元，"
        "已计提坏账准备XXX元，应收账款质押给银行取得短期借款XXX元。】"
    ),
    (
        "C、本公司已背书给供应商用于结算应付账款及已向银行贴现的银行承兑汇票账面价值合计为XX元，"
        "本公司认为，其中账面价值为XXX元的应收票据于贴现时已经转移了几乎所有的风险与报酬，"
        "符合金融资产终止确认条件，因此，终止确认相关应收票据。这些已终止确认的应收票据继续涉入的"
        "风险最大敞口与回购该票据的未折现现金流量，与应收票据的账面价值相等。"
        "本公司认为继续涉入已终止确认的应收票据的公允价值并不重大。"
    ),
    "### 转移应收账款且继续涉入形成的资产、负债的金额",
    "【转移金融资产且继续涉入的，应披露资产转移方式、分项列示继续涉入形成的资产、负债的金额。】",
    (
        "说明：（资产转移方式；未全部终止确认的被转移金融资产与相关负债之间的关系，"
        "已终止确认的金融资产继续涉入的性质及相关风险的信息。）"
    ),
]


def _build_tables(existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按源模板重建 五、5 的 tables（保留既有组合分表示例名）。"""
    existing_portfolios = [
        str(t.get("name"))
        for t in existing
        if isinstance(t, dict) and str(t.get("name", "")).startswith("组合计提项目：")
    ]
    portfolio_names = existing_portfolios or PORTFOLIO_FALLBACK_NAMES

    tables: list[dict[str, Any]] = [
        _table(T_AGING, AGING_HEADERS, AGING_ROWS),
        _table(T_CLASS_END, CLASS_HEADERS, _class_rows(), column_groups=CLASS_COLUMN_GROUPS),
        _table(T_CLASS_PRIOR, CLASS_HEADERS, _class_rows(), column_groups=CLASS_COLUMN_GROUPS),
        _table(T_IND_END, INDIVIDUAL_HEADERS, _individual_rows()),
        _table(T_IND_PRIOR, INDIVIDUAL_HEADERS, _individual_rows()),
    ]
    for name in portfolio_names:
        tables.append(
            _table(name, PORTFOLIO_HEADERS, _portfolio_rows(), column_groups=PORTFOLIO_COLUMN_GROUPS)
        )
    tables += [
        _table(T_MOVEMENT, MOVEMENT_HEADERS, MOVEMENT_ROWS),
        _table(T_REVERSAL, REVERSAL_HEADERS, [*_blank_rows(3), _row("合  计", "total")]),
        _table(T_WRITEOFF_AMOUNT, WRITEOFF_AMOUNT_HEADERS, [_row("实际核销的应收账款")]),
        _table(T_WRITEOFF_DETAIL, WRITEOFF_DETAIL_HEADERS, [*_blank_rows(3), _row("合  计", "total")]),
        _table(T_TOP5, TOP5_HEADERS, [*_blank_rows(5), _row("合  计", "total")]),
        _table(T_DERECOGNIZED, DERECOGNIZED_HEADERS, [*_blank_rows(3), _row("合  计", "total")]),
        _table(
            T_CONTINUED_INVOLVEMENT,
            CONTINUED_INVOLVEMENT_HEADERS,
            [*_blank_rows(3), _row("合 计", "total")],
        ),
    ]
    return tables


def _merge_text_sections(existing: list[Any]) -> list[Any]:
    """追加缺失的说明/法规文本节（按前缀判重，幂等）。"""
    out = list(existing)
    present = {str(s).strip() for s in out}
    for text in TEXT_SECTIONS_APPEND:
        if text.strip() in present:
            continue
        out.append(text)
        present.add(text.strip())
    return out


def align_section(section: dict[str, Any]) -> dict[str, Any]:
    """返回对齐后的 section（纯函数，不修改入参）。"""
    out = dict(section)
    out["tables"] = _build_tables(section.get("tables") or [])
    out["text_sections"] = _merge_text_sections(section.get("text_sections") or [])
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="只输出差异，不写文件")
    args = parser.parse_args()

    data = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    sections = data.get("sections") or []
    idx = next(
        (i for i, s in enumerate(sections) if s.get("section_number") == SECTION_NUMBER),
        None,
    )
    if idx is None:
        print(f"[ERROR] 未找到 section_number={SECTION_NUMBER}", file=sys.stderr)
        return 1

    before = sections[idx]
    after = align_section(before)

    print(f"tables: {len(before.get('tables') or [])} → {len(after['tables'])}")
    print(
        f"text_sections: {len(before.get('text_sections') or [])} → {len(after['text_sections'])}"
    )
    for t in after["tables"]:
        print(f"  · {t['name']}  headers={len(t['headers'])}  rows={len(t['rows'])}")

    if before == after:
        print("[OK] 已对齐，无需改动（幂等）")
        return 0
    if args.dry_run:
        print("[DRY-RUN] 未写入")
        return 0

    sections[idx] = after
    TEMPLATE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[OK] 已写入 {TEMPLATE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
