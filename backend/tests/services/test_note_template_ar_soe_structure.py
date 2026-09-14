"""附注模板「八、5 应收账款」（国企）结构契约 + 修订脚本幂等 + 列元数据透传。

spec: d2-ar-disclosure-soe-alignment
- R5.1~R5.7 / Property 6（模板幂等）
- R6.1~R6.3 / Property 7（透传零回归）

基准 = 致同 2025 修订版源模板 `附注披露信息(国企)` sheet（A1:K138 实测）。
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from app.services.disclosure_engine import _carry_seed_column_meta
from scripts.fix.fix_note_ar_soe_structure import (
    ALIGNED_BY,
    SECTION_NUMBER,
    TEXT_SECTIONS,
    TPL_PATH,
    apply,
    build_tables,
)


@pytest.fixture(scope="module")
def soe_section() -> dict:
    data = json.loads(TPL_PATH.read_text(encoding="utf-8"))
    matches = [
        s for s in data["sections"] if s.get("section_number") == SECTION_NUMBER
    ]
    assert len(matches) == 1, f"{SECTION_NUMBER} 应恰好 1 个 section"
    return matches[0]


# ─── R5：结构契约 ────────────────────────────────────────────────────────────


def test_section_marked_aligned(soe_section: dict) -> None:
    assert soe_section["_aligned_by"] == ALIGNED_BY


def test_table_names_and_order(soe_section: dict) -> None:
    """13 张表（TAB），表名与顺序对齐源模板。"""
    assert [t["name"] for t in soe_section["tables"]] == [
        "（1）按账龄披露应收账款",
        "（2）按坏账准备计提方法分类披露应收账款",
        "（2）按坏账准备计提方法分类披露应收账款（续：期初数）",
        "期末单项计提坏账准备的应收账款",
        "组合计提项目：应收中央企业客户",
        "组合计提项目：应收海外企业客户",
        "采用余额百分比或其他组合方法计提坏账准备的应收账款",
        "（3）本期计提、收回或转回的坏账准备情况",
        "收回或转回的坏账准备",
        "（4）本期实际核销的应收账款",
        "（5）按欠款方归集的期末余额前五名的应收账款",
        "（6）由金融资产转移而终止确认的应收账款",
        "（7）应收账款转移继续涉入形成的资产、负债的金额",
    ]


def _table(section: dict, name: str) -> dict:
    return next(t for t in section["tables"] if t["name"] == name)


def test_aging_table_six_buckets_with_deduction(soe_section: dict) -> None:
    """R5.1 账龄 6 档 + 小 计(subtotal) + 减：坏账准备(data) + 合 计(total)。"""
    t = _table(soe_section, "（1）按账龄披露应收账款")
    assert t["headers"] == ["账 龄", "期末数", "期初数"]
    assert [(r["label"], r["row_type"]) for r in t["rows"]] == [
        ("1年以内（含1年）", "data"),
        ("1至2年", "data"),
        ("2至3年", "data"),
        ("3至4年", "data"),
        ("4至5年", "data"),
        ("5年以上", "data"),
        ("小 计", "subtotal"),
        ("减：坏账准备", "data"),
        ("合 计", "total"),
    ]


@pytest.mark.parametrize(
    "name",
    [
        "（2）按坏账准备计提方法分类披露应收账款",
        "（2）按坏账准备计提方法分类披露应收账款（续：期初数）",
    ],
)
def test_class_tables_six_columns_grouped(soe_section: dict, name: str) -> None:
    """R5.2 分类披露双期各一张 6 列宽表 + 两级表头分组。"""
    t = _table(soe_section, name)
    assert t["headers"] == [
        "类 别", "金额", "比例(%)", "金额", "预期信用损失率(%)", "账面价值",
    ]
    assert t["_column_groups"] == [
        {"group": "账面金额", "start": 1, "span": 2},
        {"group": "坏账准备", "start": 3, "span": 2},
    ]
    # 合计 = 单项 + 组合（源模板 B28=B20+B21）；「其中：」为信息性子行
    assert [(r["label"], r["row_type"]) for r in t["rows"]] == [
        ("按单项计提坏账准备", "data"),
        ("按组合计提坏账准备", "data"),
        ("其中：", "header_label"),
        ("应收中央企业客户", "data"),
        ("应收海外企业客户", "data"),
        ("合 计", "total"),
    ]


@pytest.mark.parametrize(
    "name", ["组合计提项目：应收中央企业客户", "组合计提项目：应收海外企业客户"]
)
def test_portfolio_tables_seven_columns(soe_section: dict, name: str) -> None:
    """R5.3 组合分表 7 列（双期 × 3 值列），账龄 6 档。"""
    t = _table(soe_section, name)
    assert t["headers"] == [
        "账 龄",
        "应收账款", "比例（%）", "坏账准备",
        "应收账款", "比例（%）", "坏账准备",
    ]
    assert t["_column_groups"] == [
        {"group": "期末数", "start": 1, "span": 3},
        {"group": "期初数", "start": 4, "span": 3},
    ]
    # Property 2 双期同构
    assert t["headers"][1:4] == t["headers"][4:7]
    assert len([r for r in t["rows"] if r["row_type"] == "data"]) == 6


def test_other_portfolio_seven_columns(soe_section: dict) -> None:
    """R5.4 采用余额百分比或其他组合方法 7 列。"""
    t = _table(soe_section, "采用余额百分比或其他组合方法计提坏账准备的应收账款")
    assert t["headers"] == [
        "组合名称",
        "账面余额", "计提比例（%）", "坏账准备",
        "账面余额", "计提比例（%）", "坏账准备",
    ]
    assert t["_column_groups"] == [
        {"group": "期末数", "start": 1, "span": 3},
        {"group": "期初数", "start": 4, "span": 3},
    ]


def test_movement_table_grouped(soe_section: dict) -> None:
    """R5.5 变动表 6 列，「本期变动金额」跨三子列。"""
    t = _table(soe_section, "（3）本期计提、收回或转回的坏账准备情况")
    assert t["headers"] == [
        "类 别", "期初数", "计提", "收回或转回", "转销或核销", "期末数",
    ]
    assert t["_column_groups"] == [
        {"group": "本期变动金额", "start": 2, "span": 3},
    ]


def test_continued_involvement_table(soe_section: dict) -> None:
    """R5.6 新增（7）继续涉入表：2 列 + 资产/负债分块与各自小计。"""
    t = _table(soe_section, "（7）应收账款转移继续涉入形成的资产、负债的金额")
    assert t["headers"] == ["项  目", "期末金额"]
    assert [(r["label"], r["row_type"]) for r in t["rows"]] == [
        ("资产：", "header_label"),
        ("资产小计", "subtotal"),
        ("负债：", "header_label"),
        ("负债小计", "subtotal"),
    ]


def test_text_sections_include_continued_involvement(soe_section: dict) -> None:
    """R5.6 text_sections 追加（7）标题。"""
    assert soe_section["text_sections"] == TEXT_SECTIONS
    assert soe_section["text_sections"][-1] == "（7）应收账款转移继续涉入形成的资产、负债的金额"


def test_column_groups_span_matches_headers(soe_section: dict) -> None:
    """分组区间不得越界，且不与标签列（index 0）重叠。"""
    for t in soe_section["tables"]:
        groups = t.get("_column_groups") or []
        for g in groups:
            assert g["start"] >= 1, t["name"]
            assert g["start"] + g["span"] <= len(t["headers"]), t["name"]


# ─── Property 6：修订脚本幂等 ────────────────────────────────────────────────


def test_script_is_idempotent(tmp_path: Path) -> None:
    work = tmp_path / "note_template_soe.json"
    shutil.copyfile(TPL_PATH, work)
    # 已对齐 → 第一次即返回 False
    assert apply(work, check_only=True) is False
    first = work.read_bytes()

    # 人为退化：删掉标记与新增表，再跑两次应收敛到同一字节
    data = json.loads(work.read_text(encoding="utf-8"))
    section = next(
        s for s in data["sections"] if s.get("section_number") == SECTION_NUMBER
    )
    section.pop("_aligned_by", None)
    section["tables"] = section["tables"][:3]
    section["text_sections"] = section["text_sections"][:2]
    work.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    assert apply(work) is True
    once = work.read_bytes()
    # Property 6：连跑两次逐字节相等
    assert apply(work) is False
    assert work.read_bytes() == once
    # 修订结果与生产文件语义相等（不比字节，避免编辑器尾随换行/换行符差异干扰）
    assert json.loads(once.decode("utf-8")) == json.loads(first.decode("utf-8"))


def test_build_tables_is_pure() -> None:
    """build_tables 每次调用产出等值且互不共享引用（避免 mutate 污染）。"""
    a, b = build_tables(), build_tables()
    assert a == b
    a[0]["rows"][0]["label"] = "mutated"
    assert build_tables()[0]["rows"][0]["label"] == "1年以内（含1年）"


# ─── Property 7：列元数据透传零回归 ──────────────────────────────────────────


@pytest.mark.parametrize("tpl", [None, {}, {"headers": [], "rows": []}, "not-a-dict"])
def test_carry_seed_column_meta_no_regression(tpl: object) -> None:
    """模板无列元数据 → built 键集合不变（不新增键）。"""
    built = {"headers": ["a"], "rows": []}
    _carry_seed_column_meta(tpl, built)  # type: ignore[arg-type]
    assert set(built) == {"headers", "rows"}


@pytest.mark.parametrize(
    "name,groups",
    [
        (
            "（2）按坏账准备计提方法分类披露应收账款",
            [
                {"group": "账面金额", "start": 1, "span": 2},
                {"group": "坏账准备", "start": 3, "span": 2},
            ],
        ),
        (
            "组合计提项目：应收中央企业客户",
            [
                {"group": "期末数", "start": 1, "span": 3},
                {"group": "期初数", "start": 4, "span": 3},
            ],
        ),
        (
            "（3）本期计提、收回或转回的坏账准备情况",
            [{"group": "本期变动金额", "start": 2, "span": 3}],
        ),
    ],
)
def test_soe_seed_meta_reaches_built_table(name: str, groups: list[dict]) -> None:
    """八、5 各宽表 seed 的 `_column_groups` 经既有透传机制到达 built table_data。

    透传实现由 spec f2-inventory-disclosure-template-alignment R5 提供
    （`_carry_seed_column_meta`，已在 `generate_notes` / `get_note_detail`
    的多表分支调用），本 spec 只复用并锁定国企 八、5 的分组契约。
    """
    seed = next(t for t in build_tables() if t["name"] == name)
    built = {"name": name, "headers": seed["headers"], "rows": []}
    _carry_seed_column_meta(seed, built)
    assert built["_column_groups"] == groups
