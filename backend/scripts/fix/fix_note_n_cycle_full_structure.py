#!/usr/bin/env python3
"""N 类（N1~N5）附注模板表格结构补齐幂等脚本.

覆盖章节：
- 五、30 / 八、31  递延所得税资产与递延所得税负债（N1+N3 共节）
- 五、41 / 八、41  应交税费（N2）
- 五、63            税金及附加（N4，仅上市；国企 null 不建）
- 三、所得税费用    所得税费用（N5 上市）
- 八、78            所得税费用（N5 国企）

用法：
  python backend/scripts/fix/fix_note_n_cycle_full_structure.py --dry-run   # 预览变更
  python backend/scripts/fix/fix_note_n_cycle_full_structure.py --check     # CI 守卫 exit 0=无欠账
  python backend/scripts/fix/fix_note_n_cycle_full_structure.py --apply     # 写入

Requirements: n-cycle-note-template-and-disclosure-completion 1.*
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# ─── 共享工具（沿用平台范式）────────────────────────────────────────────────────

BACKEND_DATA = Path(__file__).resolve().parent.parent.parent / "data"
LISTED_PATH = BACKEND_DATA / "note_template_listed.json"
SOE_PATH = BACKEND_DATA / "note_template_soe.json"

ALIGNED_BY = "n-cycle-note-template-and-disclosure-completion"


def _load_json(path: Path) -> tuple[dict, list]:
    """加载模板 JSON，返回 (root_obj, sections_list)."""
    root = json.loads(path.read_text("utf-8"))
    if isinstance(root, dict) and "sections" in root:
        return root, root["sections"]
    # 兼容纯数组格式
    return {"sections": root}, root


def _save_json(path: Path, root: dict) -> None:
    path.write_text(json.dumps(root, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _find_section(sections: list, section_number: str) -> dict | None:
    for s in sections:
        if s.get("section_number") == section_number:
            return s
    return None


def _col(key: str, label: str, **kw) -> dict:
    """构造一个 column 定义 dict."""
    d: dict = {"key": key, "label": label}
    if kw.get("is_label"):
        d["is_label"] = True
    if kw.get("flat"):
        d["flat"] = True
    if kw.get("group"):
        d["group"] = kw["group"]
    if kw.get("format"):
        d["format"] = kw["format"]
    return d


# ─── N1 递延所得税（五、30 / 八、31）─────────────────────────────────────────

def _n1_unoffset_columns_listed() -> list[dict]:
    """表(1) 未经抵销 — 上市 5 列两级表头."""
    return [
        _col("label", "项目", is_label=True),
        _col("end_diff", "可抵扣/应纳税暂时性差异", group="期末余额", format="amount"),
        _col("end_tax", "递延所得税资产/负债", group="期末余额", format="amount"),
        _col("prior_diff", "可抵扣/应纳税暂时性差异", group="上年年末余额", format="amount"),
        _col("prior_tax", "递延所得税资产/负债", group="上年年末余额", format="amount"),
    ]


def _n1_unoffset_columns_soe() -> list[dict]:
    """表(1) 已确认 — 国企 5 列两级表头（列序反转：tax 在前）."""
    return [
        _col("label", "项目", is_label=True),
        _col("end_tax", "递延所得税资产/负债", group="期末余额", format="amount"),
        _col("end_diff", "可抵扣/应纳税暂时性差异", group="期末余额", format="amount"),
        _col("prior_tax", "递延所得税资产/负债", group="年初余额", format="amount"),
        _col("prior_diff", "可抵扣/应纳税暂时性差异", group="年初余额", format="amount"),
    ]


def _n1_net_offset_columns_listed() -> list[dict]:
    """表(2) 抵销后净额 — 上市 5 列 flat."""
    return [
        _col("label", "项目", is_label=True, flat=True),
        _col("offset_end", "递延所得税资产和负债期末互抵金额", format="amount"),
        _col("net_end", "抵销后递延所得税资产或负债期末余额", format="amount"),
        _col("offset_prior", "递延所得税资产和负债期初互抵金额", format="amount"),
        _col("net_prior", "抵销后递延所得税资产或负债期初余额", format="amount"),
    ]


def _n1_net_offset_columns_soe() -> list[dict]:
    """表(2)A 互抵后 — 国企 5 列 flat."""
    return [
        _col("label", "项目", is_label=True, flat=True),
        _col("net_end", "报告期末互抵后的递延所得税资产或负债", format="amount"),
        _col("diff_end", "报告期末互抵后的可抵扣或应纳税暂时性差异", format="amount"),
        _col("net_prior", "报告年初互抵后的递延所得税资产或负债", format="amount"),
        _col("diff_prior", "报告年初互抵后的可抵扣或应纳税暂时性差异", format="amount"),
    ]


def _n1_offset_detail_columns() -> list[dict]:
    """表(2)B 互抵明细 — 国企独有，2 列 flat."""
    return [
        _col("label", "项目", is_label=True, flat=True),
        _col("amount", "本期互抵金额", format="amount"),
    ]


def _n1_unrecognized_columns(variant: str) -> list[dict]:
    """表(3) 未确认 DTA — 3 列 flat."""
    prior_label = "上年年末余额" if variant == "listed" else "年初余额"
    return [
        _col("label", "项目", is_label=True, flat=True),
        _col("end", "期末余额", format="amount"),
        _col("prior", prior_label, format="amount"),
    ]


def _n1_loss_expiry_columns(variant: str) -> list[dict]:
    """表(4) 亏损到期 — 4 列 flat."""
    prior_label = "上年年末余额" if variant == "listed" else "年初余额"
    return [
        _col("label", "年份", is_label=True, flat=True),
        _col("end", "期末余额", format="amount"),
        _col("prior", prior_label, format="amount"),
        _col("remark", "备注", format="text"),
    ]


# 行集 seed
_N1_ASSET_ROWS = [
    {"label": "资产减值准备"},
    {"label": "可抵扣亏损"},
    {"label": "内部交易未实现利润"},
    {"label": "公允价值变动"},
    {"label": "租赁负债"},
    {"label": "购入摊销年限小于税法规定的资产"},
    {"label": "其他"},
]

_N1_LIABILITY_ROWS = [
    {"label": "购入摊销年限大于税法规定的资产"},
    {"label": "可供出售金融资产公允价值变动"},
    {"label": "投资性房地产公允价值变动"},
    {"label": "使用权资产"},  # 上市
    {"label": "其他"},
]

_N1_LIABILITY_ROWS_SOE = [
    {"label": "购入摊销年限大于税法规定的资产"},
    {"label": "可供出售金融资产公允价值变动"},
    {"label": "投资性房地产公允价值变动"},
    {"label": "租赁形成"},  # 国企
    {"label": "其他"},
]

_N1_GUIDANCE_UNOFFSET = (
    "递延所得税资产和递延所得税负债不以抵销后的净额列示时使用本表。"
    "资产段按可抵扣暂时性差异类别列示，负债段按应纳税暂时性差异类别列示。"
    "连续亏损情况下仍确认较大金额 DTA 须披露判断依据。"
    "资产减值准备含持有待售资产减值准备。"
)

_N1_GUIDANCE_NET = (
    "递延所得税资产和递延所得税负债以抵销后的净额列示时使用本表（不适用的删除）。"
)

_N1_GUIDANCE_UNRECOGNIZED = (
    "列示由于未来能否获得足够的应纳税所得额具有不确定性，"
    "因此没有确认为递延所得税资产的可抵扣暂时性差异和可抵扣亏损。"
)

_N1_GUIDANCE_LOSS = (
    "列示未确认递延所得税资产的可抵扣亏损将于以下年度到期的情况。"
    "年份为动态生成（审计年度+1 至+5 + 无使用期限）。"
)


def _build_n1_listed_tables() -> list[dict]:
    """五、30 — 4 张表."""
    unoffset_rows = (
        [{"label": "递延所得税资产：", "row_type": "section_header"}]
        + _N1_ASSET_ROWS
        + [{"label": "小计", "is_total": True}]
        + [{"label": "递延所得税负债：", "row_type": "section_header"}]
        + _N1_LIABILITY_ROWS
        + [{"label": "小计", "is_total": True}]
    )
    return [
        {
            "name": "未经抵销的递延所得税资产和递延所得税负债",
            "columns": _n1_unoffset_columns_listed(),
            "rows": unoffset_rows,
            "guidance": _N1_GUIDANCE_UNOFFSET,
        },
        {
            "name": "以抵销后净额列示的递延所得税资产或负债",
            "columns": _n1_net_offset_columns_listed(),
            "rows": [{"label": "递延所得税资产"}, {"label": "递延所得税负债"}],
            "guidance": _N1_GUIDANCE_NET,
        },
        {
            "name": "未确认递延所得税资产的可抵扣暂时性差异及可抵扣亏损明细",
            "columns": _n1_unrecognized_columns("listed"),
            "rows": [
                {"label": "可抵扣暂时性差异"},
                {"label": "可抵扣亏损"},
                {"label": "合计", "is_total": True},
            ],
            "guidance": _N1_GUIDANCE_UNRECOGNIZED,
        },
        {
            "name": "未确认递延所得税资产的可抵扣亏损将于以下年度到期",
            "columns": _n1_loss_expiry_columns("listed"),
            "rows": [],  # 动态年份由推送覆盖
            "guidance": _N1_GUIDANCE_LOSS,
        },
    ]


def _build_n1_soe_tables() -> list[dict]:
    """八、31 — 5 张表."""
    unoffset_rows = (
        [{"label": "一、递延所得税资产", "row_type": "section_header"}]
        + _N1_ASSET_ROWS
        + [{"label": "小计", "is_total": True}]
        + [{"label": "二、递延所得税负债", "row_type": "section_header"}]
        + _N1_LIABILITY_ROWS_SOE
        + [{"label": "小计", "is_total": True}]
    )
    return [
        {
            "name": "未经抵销的递延所得税资产和递延所得税负债",
            "columns": _n1_unoffset_columns_soe(),
            "rows": unoffset_rows,
            "guidance": _N1_GUIDANCE_UNOFFSET,
        },
        {
            "name": "以抵销后净额列示的递延所得税资产或负债",
            "columns": _n1_net_offset_columns_soe(),
            "rows": [{"label": "递延所得税资产"}, {"label": "递延所得税负债"}],
            "guidance": _N1_GUIDANCE_NET,
        },
        {
            "name": "递延所得税资产和递延所得税负债互抵明细",
            "columns": _n1_offset_detail_columns(),
            "rows": [{"label": "递延所得税资产"}, {"label": "递延所得税负债"}],
            "guidance": "互抵明细表：列示本期递延所得税资产与负债互抵金额。",
        },
        {
            "name": "未确认递延所得税资产明细",
            "columns": _n1_unrecognized_columns("soe"),
            "rows": [
                {"label": "可抵扣暂时性差异"},
                {"label": "可抵扣亏损"},
                {"label": "合计", "is_total": True},
            ],
            "guidance": _N1_GUIDANCE_UNRECOGNIZED,
        },
        {
            "name": "未确认递延所得税资产的可抵扣亏损将于以下年度到期",
            "columns": _n1_loss_expiry_columns("soe"),
            "rows": [],
            "guidance": _N1_GUIDANCE_LOSS,
        },
    ]


# ─── N2 应交税费（五、41 / 八、41）─────────────────────────────────────────────

_N2_GUIDANCE_LISTED = (
    "小税（费）种可合并反映。"
    "增值税根据「应交税费-未交增值税、简易计税、转让金融商品应交增值税、"
    "代扣代缴增值税」科目贷方余额计算填列。"
    "对于满足条件将当期所得税资产及当期所得税负债以抵销后的净额列示的情况，"
    "超过部分列示为「其他流动资产」。"
)

_N2_GUIDANCE_SOE = (
    "增值税根据「应交税费-未交增值税、简易计税、转让金融商品应交增值税、"
    "代扣代缴增值税」科目贷方余额计算填列。"
    "期末余额 = 期初余额 + 本期应交 - 本期已交。"
)

# seed 行（源模板 R8~R20 固定税种 13 行 + R21~R22 空行可扩 + R23 合计）
_N2_SEED_ROWS = [
    {"label": "企业所得税"},
    {"label": "增值税"},
    {"label": "消费税"},
    {"label": "资源税"},
    {"label": "土地增值税"},
    {"label": "城市维护建设税"},
    {"label": "车船牌照税"},
    {"label": "房产税"},
    {"label": "土地使用税"},
    {"label": "教育费附加"},
    {"label": "矿产资源补偿费"},
    {"label": "代扣代缴外国企业所得税"},
    {"label": "代扣代缴个人所得税"},
]


def _build_n2_listed_tables() -> list[dict]:
    return [{
        "name": "应交税费",
        "columns": [
            _col("label", "税项", is_label=True, flat=True),
            _col("end", "期末余额", format="amount"),
            _col("prior", "上年年末余额", format="amount"),
        ],
        "rows": _N2_SEED_ROWS + [{"label": "合计", "is_total": True}],
        "guidance": _N2_GUIDANCE_LISTED,
    }]


def _build_n2_soe_tables() -> list[dict]:
    return [{
        "name": "应交税费",
        "columns": [
            _col("label", "项目", is_label=True, flat=True),
            _col("opening", "期初余额", format="amount"),
            _col("payable", "本期应交", format="amount"),
            _col("paid", "本期已交", format="amount"),
            _col("end", "期末余额", format="amount"),
        ],
        "rows": _N2_SEED_ROWS + [{"label": "合计", "is_total": True}],
        "guidance": _N2_GUIDANCE_SOE,
    }]


# ─── N4 税金及附加（五、63，仅上市）──────────────────────────────────────────

_N4_SEED_ROWS = [
    {"label": "消费税"},
    {"label": "城市维护建设税"},
    {"label": "教育费附加"},
    {"label": "地方教育附加"},
    {"label": "房产税"},
    {"label": "城镇土地使用税"},
    {"label": "车船税"},
    {"label": "印花税"},
]

_N4_GUIDANCE = "各项税金及附加的计缴标准详见附注四、税项。"


def _build_n4_listed_tables() -> list[dict]:
    return [{
        "name": "税金及附加",
        "columns": [
            _col("label", "项目", is_label=True, flat=True),
            _col("current", "本期发生额", format="amount"),
            _col("prior", "上期发生额", format="amount"),
        ],
        "rows": _N4_SEED_ROWS + [{"label": "合计", "is_total": True}],
        "guidance": _N4_GUIDANCE,
    }]


# ─── N5 所得税费用（三、所得税费用 / 八、78）─────────────────────────────────

_N5_GUIDANCE = (
    "所得税费用等于第二行至倒数第二行之和。"
    "「对以前期间当期所得税的调整」是指对以前年度所得税进行汇算清缴的结果"
    "与以前年度确认的金额不同而调整本年所得税费用的金额。"
    "「不可抵扣的成本、费用和损失」「未确认可抵扣亏损和可抵扣暂时性差异的纳税影响」"
    "不应为负数。不适用项目可删除，「其他」金额不应过大。"
)

_N5_DETAIL_ROWS_LISTED = [
    {"label": "按税法及相关规定计算的当期所得税"},
    {"label": "递延所得税费用"},
    {"label": "合计", "is_total": True},
]

_N5_DETAIL_ROWS_SOE = [
    {"label": "当期所得税费用"},
    {"label": "递延所得税调整"},
    {"label": "其他"},
    {"label": "合计", "is_total": True},
]

# 表(2) 调整过程行（源模板从 N5-2 取动态行标签，此处 seed 空行集由推送覆盖）
_N5_RECONCILE_GUIDANCE = (
    "所得税费用与利润总额的关系列示。"
    "调整项行标签从所得税费用明细表 N5-2 动态取值。"
    "不适用项目可删除。"
)


def _n5_three_columns() -> list[dict]:
    return [
        _col("label", "项目", is_label=True, flat=True),
        _col("current", "本期发生额", format="amount"),
        _col("prior", "上期发生额", format="amount"),
    ]


def _build_n5_listed_tables() -> list[dict]:
    return [
        {
            "name": "所得税费用明细",
            "columns": _n5_three_columns(),
            "rows": _N5_DETAIL_ROWS_LISTED,
            "guidance": _N5_GUIDANCE,
        },
        {
            "name": "所得税费用与利润总额的关系",
            "columns": _n5_three_columns(),
            "rows": [],  # 动态行由推送覆盖
            "guidance": _N5_RECONCILE_GUIDANCE,
        },
    ]


def _build_n5_soe_tables() -> list[dict]:
    return [
        {
            "name": "所得税费用",
            "columns": _n5_three_columns(),
            "rows": _N5_DETAIL_ROWS_SOE,
            "guidance": _N5_GUIDANCE,
        },
        {
            "name": "会计利润与所得税费用调整过程",
            "columns": _n5_three_columns(),
            "rows": [],  # 动态行由推送覆盖
            "guidance": _N5_RECONCILE_GUIDANCE,
        },
    ]


# ─── 计划声明 ─────────────────────────────────────────────────────────────────

PLAN: list[dict] = [
    {"path": "listed", "section_number": "五、30", "tables": _build_n1_listed_tables},
    {"path": "soe", "section_number": "八、31", "tables": _build_n1_soe_tables},
    {"path": "listed", "section_number": "五、41", "tables": _build_n2_listed_tables},
    {"path": "soe", "section_number": "八、41", "tables": _build_n2_soe_tables},
    {"path": "listed", "section_number": "五、63", "tables": _build_n4_listed_tables},
    {"path": "listed", "section_number": "三、所得税费用", "tables": _build_n5_listed_tables},
    {"path": "soe", "section_number": "八、78", "tables": _build_n5_soe_tables},
]


# ─── 执行逻辑 ─────────────────────────────────────────────────────────────────

def _apply_plan(dry_run: bool = True) -> list[str]:
    """执行计划，返回变更描述列表."""
    changes: list[str] = []

    for item in PLAN:
        path = LISTED_PATH if item["path"] == "listed" else SOE_PATH
        root, sections = _load_json(path)
        sec = _find_section(sections, item["section_number"])
        if sec is None:
            changes.append(f"[ERROR] {item['section_number']} 在 {path.name} 中未找到")
            continue

        target_tables = item["tables"]()

        # 检查是否已对齐
        existing = sec.get("_tables", [])

        # 逐表比对
        needs_update = False
        if len(existing) != len(target_tables):
            needs_update = True
        else:
            for et, tt in zip(existing, target_tables):
                if et.get("name") != tt["name"]:
                    needs_update = True
                    break
                if et.get("columns") != tt.get("columns"):
                    needs_update = True
                    break
                if not et.get("guidance") and tt.get("guidance"):
                    needs_update = True
                    break

        if not needs_update and sec.get("_aligned_by") == ALIGNED_BY:
            continue

        # 应用变更
        desc = f"{item['section_number']} ({path.name}): "
        if not existing:
            desc += f"新建 {len(target_tables)} 张表"
        else:
            desc += f"更新 {len(existing)}->{len(target_tables)} 张表"
            # 保留已有 rows（推送已填充的数据不丢）
            for tt in target_tables:
                for et in existing:
                    if et.get("name") == tt["name"] and et.get("rows"):
                        # 只更新 columns/guidance，保留 rows
                        tt["rows"] = et["rows"]
                        break

        changes.append(desc)

        if not dry_run:
            sec["_tables"] = target_tables
            sec["_aligned_by"] = ALIGNED_BY
            _save_json(path, root)

    return changes


def main():
    args = sys.argv[1:]
    if "--check" in args:
        changes = _apply_plan(dry_run=True)
        if changes:
            print(f"[FAIL] {len(changes)} 处欠账:")
            for c in changes:
                print(f"  {c}")
            sys.exit(1)
        else:
            print("[OK] N 类附注模板结构无欠账")
            sys.exit(0)
    elif "--apply" in args:
        changes = _apply_plan(dry_run=False)
        print(f"[APPLIED] {len(changes)} 处变更:")
        for c in changes:
            print(f"  {c}")
    else:
        # --dry-run（默认）
        changes = _apply_plan(dry_run=True)
        if changes:
            print(f"[DRY-RUN] {len(changes)} 处将变更:")
            for c in changes:
                print(f"  {c}")
        else:
            print("[DRY-RUN] 无需变更（已对齐）")


if __name__ == "__main__":
    main()
