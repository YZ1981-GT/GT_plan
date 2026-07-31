"""幂等修订 N 循环税务类附注章节结构（N2 应交税费 / N4 税金及附加 / N5 所得税费用）。

章节
----
- ``note_template_listed.json`` §五、41 应交税费
- ``note_template_soe.json``    §八、41 应交税费
- ``note_template_listed.json`` §五、63 税金及附加（国企版源模板不披露 → **不建章节**）
- ``note_template_listed.json`` §三、所得税费用（章节位置由 md 重建错挂，本脚本不动，见下）
- ``note_template_soe.json``    §八、78 所得税费用

权威源
------
``backend/wp_templates/N/{N2 应交税费,N4 税金及附加,N5 所得税费用}.xlsx`` 的
``附注披露信息（上市公司）`` / ``附注披露信息（国企）`` 两 sheet，逐行 + 合并单元格实测；
结论固化在 ``.kiro/specs/n-cycle-tax-disclosure-alignment/design.md`` §Data Models。

修订内容（spec R5）
-------------------
1. **八、41 应交税费：3 列 → 5 列**。源模板国企侧是**变动表**
   （``项  目 / 期初余额 / 本期应交 / 本期已交 / 期末余额``，末列行内公式 ``=B8+C8-D8``），
   被 md 重建压成了双期表（``项目 / 期末余额 / 期初余额``）。
   上市侧是**双期表**（``税  项 / 期末余额 / 上年年末余额``）—— 两版列结构本质不同，各守其源。
2. **五、41 / 五、63 / 八、78 表 1 / 三、所得税费用两表：补 ``columns(flat)`` + ``guidance``**。
3. **N5 两版表名去重**（🔴 表名是同步键，同名会让 ``sub_table_data`` 互相覆盖丢表）：
   - 上市 ``三、所得税费用``：两表都叫 ``项  目``（md 重建把表头首格当表名泄漏）
     → ``所得税费用明细`` / ``所得税费用与利润总额的关系``
   - 国企 ``八、78``：两表都叫 ``所得税费用``
     → ``所得税费用`` / ``会计利润与所得税费用调整过程``
4. **八、78 表 2：2 列 → 3 列**（补回被压扁丢掉的 ``上期发生额``；源模板 R14 表头实测 3 列）。
5. ``text_sections`` 表标题统一 ``#### `` 前缀（裸表名会被当正文输出），补齐源模板实质披露文本。

**行集合不动原则**：明细行标签保持附注模板既有集合 —— 附注是交付物，且 ``_source=workpaper``
时 seed 行会被底稿整表覆盖，行骨架只服务"从未同步过的项目"。

**不做的事**
------------
- **不修 ``三、所得税费用`` 的章节归属**。它被 md 重建挂到 ``chapter-03 重要会计政策及会计估计``，
  而内容是利润表项目注释（应在 ``chapter-05``）。同批错挂共 8 个章节（公允价值变动收益 /
  信用减值损失 / 资产减值损失 / 资产处置收益 / 营业外收入 / 营业外支出 / 所得税费用 /
  现金流量表项目注释）。迁移会改动章节号并影响既有项目的 ``note_section`` 定位键 → 须单独立 spec。
- **不为国企税金及附加建章节**：源模板 ``附注披露信息：无``，``variant_matrix`` 的
  ``shui_jin_ji_fu_jia.soe_* = None`` 是正确的，不得"补齐"。

用法::

    python -m scripts.fix.fix_note_n_cycle_tax_structure --dry-run   # 只打印差异
    python -m scripts.fix.fix_note_n_cycle_tax_structure             # 就地修订
    python -m scripts.fix.fix_note_n_cycle_tax_structure --check     # 不一致则 exit 1（CI）
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

ALIGNED_BY = "n-cycle-tax-disclosure-alignment"

SECTION_N2_LISTED = "五、41"
SECTION_N2_SOE = "八、41"
SECTION_N4_LISTED = "五、63"
SECTION_N5_LISTED = "三、所得税费用"
SECTION_N5_SOE = "八、78"

AMT = "amount"

# ─────────────────────────── 表名（同步键，必须唯一）───────────────────────────
T_N2 = "应交税费"
T_N4 = "税金及附加"
T_N5_DETAIL = "所得税费用明细"
T_N5_RECONCILE_LISTED = "所得税费用与利润总额的关系"
T_N5_SOE_MAIN = "所得税费用"
T_N5_RECONCILE_SOE = "会计利润与所得税费用调整过程"

# 旧表名（md 重建产物）—— 供前端 `legacyObsolete` 与守卫引用，重命名后须清理孤儿键
LEGACY_TABLE_NAMES = {
    SECTION_N5_LISTED: ["项  目"],
    SECTION_N5_SOE: ["所得税费用"],
}


# ─────────────────────────── 行 / 列构造 ───────────────────────────


def _data(label: str, **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"label": label}
    row.update(extra)
    row.setdefault("row_type", "data")
    return row


def _total(label: str = "合计") -> dict[str, Any]:
    return {"label": label, "is_total": True, "row_type": "total"}


def _flat_columns(specs: list[tuple[str, str, str | None]]) -> list[dict[str, Any]]:
    """单级表头列定义；首列为标签列并带 ``flat`` 显式表态。

    ``flat`` 只需任一列携带（后端 ``_extract_column_groups`` 三态：任一列 flat 即显式单级），
    标在标签列即对整表生效 —— 否则 seed 路径会被 ``_infer_groups_from_headers``
    对共享前缀的 headers 反猜出凭空父表头。
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


# ═══════════════════════════ N2 应交税费 ═══════════════════════════

# 行集合 = 附注模板既有（md 派生），不改
_N2_LISTED_ROWS = ["增值税", "消费税", "企业所得税", "个人所得税", "城市维护建设税"]
_N2_SOE_ROWS = [
    "增值税",
    "消费税",
    "资源税",
    "企业所得税",
    "城市维护建设税",
    "房产税",
    "土地使用税",
    "个人所得税",
    "教育费附加（含地方教育费附加）",
    "其他税费",
]

_G_N2_LISTED = (
    "上市版按**双期余额**列示（期末余额 / 上年年末余额）。"
    "源模板说明：小税（费）种可合并反映；"
    "满足条件将当期所得税资产及当期所得税负债以抵销后净额列示时，"
    "实交税款大于应交税的超过部分列示为「其他流动资产」，小于时差额列示为「应交税费」。"
    "【提示：增值税，根据“应交税费-未交增值税、简易计税、转让金融商品应交增值税、"
    "代扣代缴增值税”科目贷方余额计算填列。】"
    "勾稽：合计 = 各税项之和（源模板 =SUM(B8:B22)）。"
)

_G_N2_SOE = (
    "🔴 国企版按**变动口径**列示（期初余额 / 本期应交 / 本期已交 / 期末余额），"
    "与上市版的双期余额表结构本质不同，不可互相套用。"
    "【提示：增值税，根据“应交税费-未交增值税、简易计税、转让金融商品应交增值税、"
    "代扣代缴增值税”科目贷方余额计算填列。】"
    "勾稽：每行 期末余额 = 期初余额 + 本期应交 − 本期已交（源模板 =B8+C8-D8）；"
    "合计 = 各列之和（源模板 =SUM(B8:B22) 等）。"
)


def build_n2_listed_tables() -> list[dict[str, Any]]:
    return [
        _flat_table(
            T_N2,
            [
                ("label", "税项", None),
                ("end", "期末余额", AMT),
                ("prior", "上年年末余额", AMT),
            ],
            [*[_data(n) for n in _N2_LISTED_ROWS], _total()],
            _G_N2_LISTED,
        )
    ]


N2_LISTED_TEXT_SECTIONS = [
    f"#### {T_N2}",
    "（小税（费）种可合并反映。）",
    "（对于满足条件将当期所得税资产及当期所得税负债以抵销后的净额列示的情况，"
    "当企业实际交纳的所得税税款大于按照税法规定计算的应交税时，超过部分在资产负债表中"
    "应当列示为“其他流动资产”；当企业实际交纳的所得税税款小于按照税法规定计算的应交税时，"
    "差额部分应当作为资产负债表中的“应交税费”项目列示。）",
    "【提示：增值税，根据“应交税费-未交增值税、简易计税、转让金融商品应交增值税、"
    "代扣代缴增值税”科目贷方余额计算填列；】",
]


def build_n2_soe_tables() -> list[dict[str, Any]]:
    return [
        _flat_table(
            T_N2,
            [
                ("label", "项目", None),
                ("opening", "期初余额", AMT),
                ("payable", "本期应交", AMT),
                ("paid", "本期已交", AMT),
                ("end", "期末余额", AMT),
            ],
            [*[_data(n) for n in _N2_SOE_ROWS], _total()],
            _G_N2_SOE,
        )
    ]


N2_SOE_TEXT_SECTIONS = [
    f"#### {T_N2}",
    "【提示：增值税，根据“应交税费-未交增值税、简易计税、转让金融商品应交增值税、"
    "代扣代缴增值税”科目贷方余额计算填列。】",
]

# ═══════════════════════════ N4 税金及附加（仅上市）═══════════════════════════

_N4_LISTED_ROWS = [
    "消费税",
    "城市维护建设税",
    "教育费附加",
    "资源税",
    "房产税",
    "土地使用税",
    "车船使用税",
    "印花税",
]

_G_N4_LISTED = (
    "按税费项目列示本期 / 上期发生额。"
    "源模板说明：各项税金及附加的计缴标准详见附注四、税项。"
    "🔴 国企版源模板此节为「附注披露信息：无」→ **国企不披露税金及附加**，故无国企章节。"
    "勾稽：合计 = 各税费项目之和（源模板 =SUM(B8:B16)）。"
)


def build_n4_listed_tables() -> list[dict[str, Any]]:
    return [
        _flat_table(
            T_N4,
            [
                ("label", "项目", None),
                ("current", "本期发生额", AMT),
                ("prior", "上期发生额", AMT),
            ],
            [*[_data(n) for n in _N4_LISTED_ROWS], _total()],
            _G_N4_LISTED,
        )
    ]


N4_LISTED_TEXT_SECTIONS = [
    f"#### {T_N4}",
    "各项税金及附加的计缴标准详见附注四、税项。",
]

# ═══════════════════════════ N5 所得税费用 ═══════════════════════════

_N5_LISTED_DETAIL_ROWS = ["按税法及相关规定计算的当期所得税", "递延所得税费用"]

# 表（2）行集合 = 附注模板既有 13 行（末行 `所得税费用` 是勾稽落点而非合计行）
_N5_LISTED_RECONCILE_ROWS = [
    "利润总额",
    "按法定（或适用）税率计算的所得税费用（利润总额*XX%）",
    "某些子公司适用不同税率的影响",
    "对以前期间当期所得税的调整",
    "权益法核算的合营企业和联营企业损益",
    "无须纳税的收入（以“-”填列）",
    "不可抵扣的成本、费用和损失",
    "税率变动对期初递延所得税余额的影响",
    "利用以前年度未确认可抵扣亏损和可抵扣暂时性差异的纳税影响（以“-”填列）",
    "未确认可抵扣亏损和可抵扣暂时性差异的纳税影响",
    "研究开发费加成扣除的纳税影响（以“-”填列）",
    "其他",
]

_N5_SOE_MAIN_ROWS = ["当期所得税费用", "递延所得税调整", "其他"]

_N5_SOE_RECONCILE_ROWS = [
    "利润总额",
    "按适定/适用税率计算的所得税费用",
    "子公司适用不同税率的影响",
    "调整以前期间所得税的影响",
    "非应税收入的影响",
    "不可抵扣的成本、费用和损失的影响",
    "使用前期未确认递延所得税资产的可抵扣亏损的影响",
    "本期未确认递延所得税资产的可抵扣暂时性差异或可抵扣亏损的影响",
    "其他",
]

_N5_NOTE_HINT = (
    "源模板注：①所得税费用等于第二行至倒数第二行之和；"
    "②「对以前期间当期所得税的调整」指对以前年度所得税汇算清缴的结果与以前年度确认金额"
    "不同而调整本年所得税费用的金额；"
    "③「不可抵扣的成本、费用和损失」「未确认可抵扣亏损和可抵扣暂时性差异的纳税影响」不应为负数。"
)

_G_N5_DETAIL = (
    "按当期所得税与递延所得税两段列示。"
    "勾稽：合计 = 当期所得税 + 递延所得税费用（源模板 =SUM(C9:C10)）；"
    "本表合计应等于下表「所得税费用」行（同一金额两处列示）。"
)

_G_N5_RECONCILE_LISTED = (
    "源模板标题括注「不适用项目可删除，“其他”金额不应过大」。" + _N5_NOTE_HINT
    + "勾稽：「所得税费用」行 = 第二行至倒数第二行之和。"
)

_G_N5_SOE_MAIN = (
    "国企版按当期所得税费用 / 递延所得税调整 / 其他三段列示。"
    "勾稽：合计 = 三项之和（源模板 =SUM(C8:C10)）；应等于下表「合计」。"
)

_G_N5_RECONCILE_SOE = (
    "源模板标题括注「国资委格式未要求披露，建议披露」。" + _N5_NOTE_HINT
    + "勾稽：合计 = 各调整项之和。"
)


def build_n5_listed_tables() -> list[dict[str, Any]]:
    specs = [
        ("label", "项目", None),
        ("current", "本期发生额", AMT),
        ("prior", "上期发生额", AMT),
    ]
    return [
        _flat_table(
            T_N5_DETAIL,
            specs,
            [*[_data(n) for n in _N5_LISTED_DETAIL_ROWS], _total()],
            _G_N5_DETAIL,
        ),
        _flat_table(
            T_N5_RECONCILE_LISTED,
            specs,
            [
                *[_data(n) for n in _N5_LISTED_RECONCILE_ROWS],
                # 末行是勾稽落点（源模板注 1），不是 is_total
                _data("所得税费用", account_codes=["6801"]),
            ],
            _G_N5_RECONCILE_LISTED,
        ),
    ]


N5_LISTED_TEXT_SECTIONS = [
    f"#### {T_N5_DETAIL}",
    f"#### {T_N5_RECONCILE_LISTED}（不适用项目可删除，“其他”金额不应过大）",
    "【提示：",
    "1、上表中，所得税费用等于第二行至倒数第二行之和；",
    "2、“对以前期间当期所得税的调整”是指，对以前年度所得税进行汇算清缴的结果与"
    "以前年度确认的金额不同而调整本年所得税费用的金额。",
    "3、“不可抵扣的成本、费用和损失”、“未确认可抵扣亏损和可抵扣暂时性差异的纳税影响”"
    "不应为负数。】",
]


def build_n5_soe_tables() -> list[dict[str, Any]]:
    specs = [
        ("label", "项目", None),
        ("current", "本期发生额", AMT),
        ("prior", "上期发生额", AMT),
    ]
    return [
        _flat_table(
            T_N5_SOE_MAIN,
            specs,
            [*[_data(n) for n in _N5_SOE_MAIN_ROWS], _total()],
            _G_N5_SOE_MAIN,
        ),
        _flat_table(
            T_N5_RECONCILE_SOE,
            specs,
            [*[_data(n) for n in _N5_SOE_RECONCILE_ROWS], _total()],
            _G_N5_RECONCILE_SOE,
        ),
    ]


N5_SOE_TEXT_SECTIONS = [
    f"#### {T_N5_SOE_MAIN}",
    f"#### {T_N5_RECONCILE_SOE}（国资委格式未要求披露，建议披露）",
    "【提示：",
    "1、上表中，所得税费用等于第二行至倒数第二行之和；",
    "2、“对以前期间当期所得税的调整”是指，对以前年度所得税进行汇算清缴的结果与"
    "以前年度确认的金额不同而调整本年所得税费用的金额。",
    "3、“不可抵扣的成本、费用和损失”、“未确认可抵扣亏损和可抵扣暂时性差异的纳税影响”"
    "不应为负数。】",
]


# ─────────────────────────── apply ───────────────────────────

_PLAN = (
    ("N2/listed", LISTED_PATH, SECTION_N2_LISTED, build_n2_listed_tables, N2_LISTED_TEXT_SECTIONS),
    ("N2/soe", SOE_PATH, SECTION_N2_SOE, build_n2_soe_tables, N2_SOE_TEXT_SECTIONS),
    ("N4/listed", LISTED_PATH, SECTION_N4_LISTED, build_n4_listed_tables, N4_LISTED_TEXT_SECTIONS),
    ("N5/listed", LISTED_PATH, SECTION_N5_LISTED, build_n5_listed_tables, N5_LISTED_TEXT_SECTIONS),
    ("N5/soe", SOE_PATH, SECTION_N5_SOE, build_n5_soe_tables, N5_SOE_TEXT_SECTIONS),
)


def _find_section(data: dict[str, Any], section_number: str) -> dict[str, Any]:
    hits = [s for s in data["sections"] if s.get("section_number") == section_number]
    if len(hits) != 1:
        raise SystemExit(
            f"期望 {section_number} 恰好 1 个 section，实际 {len(hits)} 个"
        )
    return hits[0]


def _describe(tables: list[dict[str, Any]]) -> str:
    return " / ".join(f"{t['name']}({len(t['headers'])}列)" for t in tables)


def apply(*, check_only: bool = False, dry_run: bool = False) -> bool:
    """返回 True 表示存在待修订内容。"""
    any_changed = False
    # 同一模板文件可能被多个章节修订 → 按文件累积后一次写盘
    pending: dict[Path, dict[str, Any]] = {}

    for label, path, section_number, build, texts in _PLAN:
        data = pending.get(path)
        if data is None:
            data = json.loads(path.read_text(encoding="utf-8"))
            pending[path] = data
        section = _find_section(data, section_number)
        tables = build()

        changed = (
            section.get("tables") != tables
            or section.get("text_sections") != texts
            or section.get("_aligned_by") != ALIGNED_BY
        )
        if not changed:
            print(f"[{label}] {section_number} 已对齐（{ALIGNED_BY}），无需修改")
            continue

        any_changed = True
        if check_only or dry_run:
            old = section.get("tables") or []
            print(f"[{label}] {section_number} 与源模板不一致：")
            print(f"    现状 {len(old)} 表 → {_describe(old) if old else '(无)'}")
            print(f"    目标 {len(tables)} 表 → {_describe(tables)}")
            continue

        section["tables"] = tables
        section["text_sections"] = list(texts)
        section["_aligned_by"] = ALIGNED_BY
        print(f"[{label}] {section_number} 已修订：{len(tables)} 张表 / {len(texts)} 个文本节")

    if any_changed and not (check_only or dry_run):
        for path, data in pending.items():
            # 保持既有落盘格式（indent=2 / LF / 无尾随换行），避免整文件换行符 diff
            path.write_bytes(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))

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
