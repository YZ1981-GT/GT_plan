"""附注模板 五、5「应收账款」结构契约（对齐致同源模板）

spec: d2-ar-disclosure-template-alignment — Task 7.3
Source: `D2-1至D2-4 应收账款-审定表明细表（Leap-常规程序）.xlsx` / `附注披露信息(上市公司)`

卡点目的：`scripts/fix/rebuild_note_from_md.py` 从 md 重建模板时会把多级表头压扁、
把双期两张表并成一张。本文件在 CI 阶段拦住这种回退，提示重跑
`scripts/fix/fix_note_ar_listed_structure.py`。

Validates: Requirements 7.1~7.7；Property 8（脚本幂等）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = _BACKEND / "data" / "note_template_listed.json"
SECTION_NUMBER = "五、5"
_FIX_HINT = "请重跑 python scripts/fix/fix_note_ar_listed_structure.py"

if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


@pytest.fixture(scope="module")
def section() -> dict:
    data = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    sec = next(
        (s for s in data.get("sections") or [] if s.get("section_number") == SECTION_NUMBER),
        None,
    )
    assert sec is not None, f"模板缺少 {SECTION_NUMBER} 章节"
    return sec


@pytest.fixture(scope="module")
def tables_by_name(section: dict) -> dict[str, dict]:
    return {str(t.get("name")): t for t in section.get("tables") or []}


def _labels(headers: list) -> list[str]:
    return [str(h) for h in headers]


# ─── Requirement 7.1：分类披露双期两张 6 列表（含两级表头）────────────────────

@pytest.mark.parametrize(
    "name",
    ["按坏账计提方法分类披露", "按坏账计提方法分类披露（续：上年年末余额）"],
)
def test_class_disclosure_is_two_period_six_columns(tables_by_name: dict, name: str) -> None:
    tbl = tables_by_name.get(name)
    assert tbl is not None, f"缺表 {name}；{_FIX_HINT}"
    assert _labels(tbl["headers"]) == [
        "类 别", "金额", "比例(%)", "金额", "预期信用损失率(%)", "账面价值",
    ], f"{name} 列头未对齐源模板 r23~r24；{_FIX_HINT}"
    assert tbl.get("_column_groups") == [
        {"group": "账面余额", "start": 1, "span": 2},
        {"group": "坏账准备", "start": 3, "span": 2},
    ], f"{name} 缺两级表头分组；{_FIX_HINT}"
    labels = [str(r.get("label")) for r in tbl["rows"]]
    assert labels[0] == "按单项计提坏账准备"
    assert any("按组合计提坏账准备" in x for x in labels)
    assert labels[-1] == "合  计"


# ─── Requirement 7.2：单项计提双期 5 列 + 组合分表含标签列与双期各 3 列 ────────

@pytest.mark.parametrize(
    "name",
    ["按单项计提坏账准备的应收账款", "按单项计提坏账准备的应收账款（续：上年年末余额）"],
)
def test_individual_is_two_period_five_columns(tables_by_name: dict, name: str) -> None:
    tbl = tables_by_name.get(name)
    assert tbl is not None, f"缺表 {name}；{_FIX_HINT}"
    assert _labels(tbl["headers"]) == [
        "名 称", "账面余额", "坏账准备", "预期信用损失率（%）", "计提依据",
    ], f"{name} 列头未对齐源模板 r52/r59；{_FIX_HINT}"
    total = tbl["rows"][-1]
    assert total["label"] == "合  计" and total.get("is_total") is True
    # 源模板 E56/E63：合计行「计提依据」为 /
    assert total.get("values", [None])[-1] == "/"


def test_portfolio_tables_have_label_column_and_two_periods(section: dict) -> None:
    portfolios = [
        t for t in section.get("tables") or []
        if str(t.get("name", "")).startswith("组合计提项目：")
    ]
    assert portfolios, f"缺组合计提分表；{_FIX_HINT}"
    for tbl in portfolios:
        name = tbl.get("name")
        assert _labels(tbl["headers"]) == [
            "账龄",
            "应收账款", "坏账准备", "预期信用损失率(%)",
            "应收账款", "坏账准备", "预期信用损失率(%)",
        ], f"{name} 列头未对齐源模板 r67；{_FIX_HINT}"
        assert tbl.get("_column_groups") == [
            {"group": "期末余额", "start": 1, "span": 3},
            {"group": "上年年末余额", "start": 4, "span": 3},
        ], f"{name} 缺双期分组；{_FIX_HINT}"


# ─── Requirement 7.3 / 7.4：终止确认表存在 + 前五名表名正确 ───────────────────

def test_derecognition_and_continuing_involvement_tables_exist(tables_by_name: dict) -> None:
    der = tables_by_name.get("因金融资产转移而终止确认的应收账款情况")
    assert der is not None, f"缺终止确认表（源模板 r160）；{_FIX_HINT}"
    assert _labels(der["headers"]) == [
        "项  目", "转移方式", "终止确认金额", "与终止确认相关的利得或损失",
    ]
    ci = tables_by_name.get("转移应收账款且继续涉入形成的资产、负债")
    assert ci is not None, f"缺继续涉入表（源模板 r172）；{_FIX_HINT}"
    assert _labels(ci["headers"]) == [
        "项  目", "资产转移方式", "继续涉入形成的资产金额", "继续涉入形成的负债金额",
    ]


def test_top5_table_name_is_section_title_not_first_column(tables_by_name: dict) -> None:
    assert "按欠款方归集的应收账款和合同资产期末余额前五名单位情况" in tables_by_name, _FIX_HINT
    # 旧抽取把首列名当表名
    assert "单位名称" not in tables_by_name, f"前五名表名仍为首列名；{_FIX_HINT}"


# ─── Requirement 7.5 / 7.6：账龄 10 行口径 + 变动首行 ─────────────────────────

def test_aging_rows_match_source_segments(tables_by_name: dict) -> None:
    tbl = tables_by_name["按账龄披露"]
    assert _labels(tbl["headers"]) == ["账 龄", "期末余额", "上年年末余额"]
    labels = [str(r.get("label")) for r in tbl["rows"]]
    for seg in ["1至2年", "2至3年", "3至4年", "4至5年", "5年以上"]:
        assert seg in labels, f"账龄缺 {seg}；{_FIX_HINT}"
    assert "3年以上" not in labels, f"账龄出现模板未定义的合并段 3年以上；{_FIX_HINT}"
    assert labels[-3:] == ["小  计", "减：坏账准备", "合  计"]


def test_movement_first_row_is_prior_year_end(tables_by_name: dict) -> None:
    tbl = tables_by_name["本期计提、收回或转回的坏账准备情况"]
    labels = [str(r.get("label")) for r in tbl["rows"]]
    assert labels[0] == "上年年末余额", f"变动表首行应为「上年年末余额」（源模板 r117）；{_FIX_HINT}"
    assert labels[-1] == "期末余额"


# ─── Requirement 7.7：终止确认 / 继续涉入说明文本节 ──────────────────────────

def test_text_sections_cover_derecognition_and_continuing_involvement(section: dict) -> None:
    texts = [str(t) for t in section.get("text_sections") or []]
    joined = "\n".join(texts)
    assert "### 因金融资产转移而终止确认的应收账款情况" in texts, _FIX_HINT
    assert "15号文第五十一条" in joined, _FIX_HINT
    assert "不附追索权的应收账款保理" in joined, f"缺说明 A 范式；{_FIX_HINT}"
    assert "附追索权的应收账款保理" in joined, f"缺说明 B 范式；{_FIX_HINT}"
    assert "继续涉入" in joined, f"缺继续涉入说明；{_FIX_HINT}"


# ─── Property 8：修订脚本幂等 ────────────────────────────────────────────────

def test_align_script_is_idempotent(section: dict) -> None:
    from scripts.fix.fix_note_ar_listed_structure import align_section

    once = align_section(section)
    twice = align_section(once)
    assert once == twice, "align_section 非幂等"
    # 当前模板已是对齐态 → 再跑一次不产生任何变化
    assert once == section, f"模板与脚本产物不一致；{_FIX_HINT}"
