"""幂等修订 note_template_soe.json 章节「八、5 应收账款」结构。

基准 = 致同 2025 修订版源模板
``D2-1至D2-4  应收账款- 审定表明细表（Leap-常规程序）.xlsx`` 的
``附注披露信息(国企)`` sheet（A1:K138 实测）。

修订内容（spec d2-ar-disclosure-soe-alignment R5）：
1. 账龄表 4 档 → 6 档，并补 `小 计` / `减：坏账准备` / `合 计` 三行结构
2. 分类披露 3 列 → 双期各一张 6 列宽表（带 `_column_groups` 两级表头）
3. 组合计提示例分表 3 列 → 7 列（双期 × {应收账款, 比例（%）, 坏账准备}），账龄 6 档
4. 「采用余额百分比或其他组合方法」3 列 → 7 列
5. 变动表 4 列 → 6 列，`本期变动金额` 跨三子列分组
6. 新增「（7）应收账款转移继续涉入形成的资产、负债的金额」表与对应 text_section

幂等：以 `_aligned_by` 标记 + 结构全等判定，重复执行结果逐字节相等。

用法：
    python -m scripts.fix.fix_note_ar_soe_structure           # 就地修订
    python -m scripts.fix.fix_note_ar_soe_structure --check   # 只校验，不写盘
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

# `row_type` 判据单一真源（见 `_data()` 处注释）。
from app.services.note_expandable_markers import (  # noqa: E402
    row_type_for_label as _row_type_for_label,
)

TPL_PATH = _BACKEND_ROOT / "data" / "note_template_soe.json"
SECTION_NUMBER = "八、5"
ALIGNED_BY = "d2-ar-disclosure-soe-alignment"

# ─── 账龄档位（源模板 r7~r12）────────────────────────────────────────────────
AGING_BUCKETS = [
    "1年以内（含1年）",
    "1至2年",
    "2至3年",
    "3至4年",
    "4至5年",
    "5年以上",
]

# ─── 组合计提示例项目（沿用模板既有示例名，源模板为 #REF! 占位）──────────────
PORTFOLIO_EXAMPLES = ["应收中央企业客户", "应收海外企业客户"]


def _data(label: str) -> dict:
    # 🔴 禁硬编码 "data"：源模板可扩位标签（`……` / `可无限量添加行` 等）须标
    # `expandable`（零可见内容），否则与 fix_note_expandable_rows.py 互相翻转。
    # 判据单一真源 = app/services/note_expandable_markers.row_type_for_label。
    return {"label": label, "row_type": _row_type_for_label(label)}


def _header(label: str) -> dict:
    return {"label": label, "row_type": "header_label"}


def _subtotal(label: str) -> dict:
    return {"label": label, "is_total": True, "row_type": "subtotal"}


def _total(label: str) -> dict:
    return {"label": label, "is_total": True, "row_type": "total"}


def _class_table(name: str) -> dict:
    """按坏账准备计提方法分类披露（源模板 r17~r28，双期各一张 6 列宽表）。

    合计 = 单项 + 组合（源模板 B28=B20+B21）；`其中：` 各组合为信息性子行。
    """
    return {
        "name": name,
        "headers": ["类 别", "金额", "比例(%)", "金额", "预期信用损失率(%)", "账面价值"],
        "_column_groups": [
            {"group": "账面金额", "start": 1, "span": 2},
            {"group": "坏账准备", "start": 3, "span": 2},
        ],
        "rows": [
            _data("按单项计提坏账准备"),
            _data("按组合计提坏账准备"),
            _header("其中："),
            *[_data(n) for n in PORTFOLIO_EXAMPLES],
            _total("合 计"),
        ],
    }


def _portfolio_table(portfolio_name: str) -> dict:
    """组合计提分表（源模板 r36~r79：账龄 × 双期{应收账款, 比例（%）, 坏账准备}）。"""
    return {
        "name": f"组合计提项目：{portfolio_name}",
        "headers": [
            "账 龄",
            "应收账款", "比例（%）", "坏账准备",
            "应收账款", "比例（%）", "坏账准备",
        ],
        "_column_groups": [
            {"group": "期末数", "start": 1, "span": 3},
            {"group": "期初数", "start": 4, "span": 3},
        ],
        "rows": [*[_data(b) for b in AGING_BUCKETS], _total("合 计")],
    }


def build_tables() -> list[dict]:
    """按源模板顺序产出 八、5 全部表（TAB）。"""
    return [
        # （1）按账龄披露（源模板 r6~r15）
        {
            "name": "（1）按账龄披露应收账款",
            "headers": ["账 龄", "期末数", "期初数"],
            "rows": [
                *[_data(b) for b in AGING_BUCKETS],
                _subtotal("小 计"),
                _data("减：坏账准备"),
                _total("合 计"),
            ],
        },
        # （2）分类披露：双期各一张 6 列宽表（源模板 r17~r28）
        _class_table("（2）按坏账准备计提方法分类披露应收账款"),
        _class_table("（2）按坏账准备计提方法分类披露应收账款（续：期初数）"),
        # 期末单项计提明细（源模板 r29~r33，+「计提理由」为平台既有增强列）
        {
            "name": "期末单项计提坏账准备的应收账款",
            "headers": [
                "债务人名称", "账面余额", "坏账准备", "账龄",
                "预期信用损失率（%）", "计提理由",
            ],
            "rows": [_total("合 计")],
        },
        # 按信用风险特征组合计提（源模板 r34~r79）
        *[_portfolio_table(n) for n in PORTFOLIO_EXAMPLES],
        # 采用余额百分比或其他组合方法（源模板 r80~r90）
        {
            "name": "采用余额百分比或其他组合方法计提坏账准备的应收账款",
            "headers": [
                "组合名称",
                "账面余额", "计提比例（%）", "坏账准备",
                "账面余额", "计提比例（%）", "坏账准备",
            ],
            "_column_groups": [
                {"group": "期末数", "start": 1, "span": 3},
                {"group": "期初数", "start": 4, "span": 3},
            ],
            "rows": [_total("合 计")],
        },
        # （3）本期计提、收回或转回（源模板 r93~r99）
        {
            "name": "（3）本期计提、收回或转回的坏账准备情况",
            "headers": ["类 别", "期初数", "计提", "收回或转回", "转销或核销", "期末数"],
            "_column_groups": [
                {"group": "本期变动金额", "start": 2, "span": 3},
            ],
            "rows": [_data("单项"), _data("组合："), _data("……"), _total("合 计")],
        },
        # 收回或转回的坏账准备（源模板 r100~r104）
        {
            "name": "收回或转回的坏账准备",
            "headers": [
                "债务人名称", "转回或收回金额",
                "转回或收回前累计已计提坏账准备金额", "转回或收回原因、方式",
            ],
            "rows": [_total("合 计")],
        },
        # （4）本期实际核销（源模板 r106~r110）
        {
            "name": "（4）本期实际核销的应收账款",
            "headers": [
                "债务人名称", "应收账款性质", "核销金额", "核销原因",
                "履行的核销程序", "是否因关联交易产生",
            ],
            "rows": [_total("合 计")],
        },
        # （5）前五名（源模板 r111~r118）
        {
            "name": "（5）按欠款方归集的期末余额前五名的应收账款",
            "headers": ["债务人名称", "账面余额", "占应收账款合计的比例（%）", "坏账准备"],
            "rows": [_total("合 计")],
        },
        # （6）由金融资产转移而终止确认（源模板 r119~r124）
        {
            "name": "（6）由金融资产转移而终止确认的应收账款",
            "headers": [
                "债务人名称", "终止确认金额",
                "与终止确认相关的利得或损失（损失以“-”填列）",
            ],
            "rows": [_total("合 计")],
        },
        # （7）转移继续涉入形成的资产、负债（源模板 r129~r136）
        {
            "name": "（7）应收账款转移继续涉入形成的资产、负债的金额",
            "headers": ["项  目", "期末金额"],
            "rows": [
                _header("资产："),
                _subtotal("资产小计"),
                _header("负债："),
                _subtotal("负债小计"),
            ],
        },
    ]


TEXT_SECTIONS = [
    "（1）按账龄披露应收账款",
    "（2）按坏账准备计提方法分类披露应收账款",
    "#### 期末单项计提坏账准备的应收账款",
    "（3）本期计提、收回或转回的坏账准备情况",
    "（4）本期实际核销的应收账款",
    "（5）按欠款方归集的期末余额前五名的应收账款",
    "（6）由金融资产转移而终止确认的应收账款",
    "（7）应收账款转移继续涉入形成的资产、负债的金额",
]


def apply(path: Path = TPL_PATH, *, check_only: bool = False) -> bool:
    """返回 True 表示需要修改（check_only 下不写盘）。"""
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    matches = [s for s in data["sections"] if s.get("section_number") == SECTION_NUMBER]
    if len(matches) != 1:
        raise SystemExit(
            f"期望 {SECTION_NUMBER} 恰好 1 个 section，实际 {len(matches)} 个"
        )
    section = matches[0]

    tables = build_tables()
    changed = (
        section.get("tables") != tables
        or section.get("text_sections") != TEXT_SECTIONS
        or section.get("_aligned_by") != ALIGNED_BY
    )
    if not changed:
        print(f"{SECTION_NUMBER} 已对齐（{ALIGNED_BY}），无需修改")
        return False
    if check_only:
        print(f"{SECTION_NUMBER} 与源模板不一致，需执行修订")
        return True

    section["tables"] = tables
    section["text_sections"] = list(TEXT_SECTIONS)
    section["_aligned_by"] = ALIGNED_BY
    # 保持既有落盘格式（indent=2 / LF / 无尾随换行），避免整文件换行符 diff
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    path.write_bytes(payload.encode("utf-8"))
    print(f"{SECTION_NUMBER} 已修订：{len(tables)} 张表 / {len(TEXT_SECTIONS)} 个文本节")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只校验不写盘")
    args = parser.parse_args()
    apply(check_only=args.check)
    return 0


if __name__ == "__main__":
    sys.exit(main())
