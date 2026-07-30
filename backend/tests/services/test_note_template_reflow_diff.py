"""模板回流差异计算（只读）单测。

Spec: .kiro/specs/disclosure-note-follow-actual-content/ R2 / Task 2.4
"""
from __future__ import annotations

from typing import Any

import pytest

from app.services.note_template_reflow_service import (
    ColumnDrift,
    RenameCandidate,
    SectionDiff,
    diff_tables,
)


def _col(key: str, label: str, **kw: Any) -> dict[str, Any]:
    return {"key": key, "label": label, **kw}


# 模板：3 张表（两级表头 1 张 + 单级 2 张）
TPL: list[dict[str, Any]] = [
    {
        "name": "存货分类",
        "columns": [
            _col("label", "项目", is_label=True),
            _col("end_gross", "账面余额", group="期末余额", format="amount"),
            _col("end_imp", "跌价准备", group="期末余额", format="amount"),
        ],
        "guidance": "按企业具体情况分类（源模版注）。",
    },
    {
        "name": "开发成本",
        "columns": [
            _col("project_name", "项目名称", is_label=True, flat=True),
            _col("end_balance", "期末数", format="amount"),
        ],
        "guidance": "房地产开发企业按此格式披露（源模版注）。",
    },
    {
        "name": "确认为存货的数据资源",
        "columns": [
            _col("label", "项目", is_label=True, flat=True),
            _col("purchased", "外购的数据资源存货", format="amount"),
        ],
        "guidance": "《企业数据资源相关会计处理暂行规定》…",
    },
]


def _cols_of(name: str) -> list[dict[str, Any]]:
    return next(t["columns"] for t in TPL if t["name"] == name)


# ════════════════════════════════════════════════════════════════════
# missing / extra
# ════════════════════════════════════════════════════════════════════


def test_all_tables_missing_when_note_empty():
    d = diff_tables(TPL, {}, {})
    assert d["missing"] == ["存货分类", "开发成本", "确认为存货的数据资源"]
    assert d["extra"] == []
    assert d["column_drift"] == []


def test_missing_preserves_template_order():
    d = diff_tables(TPL, {"开发成本": []}, {"开发成本": _cols_of("开发成本")})
    assert d["missing"] == ["存货分类", "确认为存货的数据资源"]


def test_extra_table_reported_not_deleted():
    sub = {n: [] for n in ("存货分类", "开发成本", "确认为存货的数据资源")}
    sub["项目自定义表"] = []
    cols = {n: _cols_of(n) for n in ("存货分类", "开发成本", "确认为存货的数据资源")}
    d = diff_tables(TPL, sub, cols)
    assert d["extra"] == ["项目自定义表"]
    assert d["missing"] == []


def test_meta_keys_are_ignored():
    sub = {"_note_texts": [], "_removed_table_keys": [], "开发成本": []}
    d = diff_tables(TPL, sub, {"开发成本": _cols_of("开发成本")})
    assert "_note_texts" not in d["extra"]
    assert "_removed_table_keys" not in d["extra"]


def test_no_diff_when_fully_aligned():
    sub = {t["name"]: [] for t in TPL}
    cols = {t["name"]: t["columns"] for t in TPL}
    guidance = {t["name"]: t["guidance"] for t in TPL}
    d = diff_tables(TPL, {**sub, "_guidance": guidance}, cols)
    assert d["missing"] == [] and d["extra"] == []
    assert d["column_drift"] == [] and d["guidance_missing"] == []


# ════════════════════════════════════════════════════════════════════
# column_drift
# ════════════════════════════════════════════════════════════════════


def test_drift_when_note_has_no_columns():
    """附注侧无列头 → count 漂移（投影会退化为只显示行名）。"""
    d = diff_tables(TPL, {"开发成本": []}, {})
    drift = [c for c in d["column_drift"] if c.table == "开发成本"]
    assert len(drift) == 1
    assert drift[0].reason == "count"


def test_drift_on_column_count():
    d = diff_tables(
        TPL,
        {"存货分类": []},
        {"存货分类": [_col("label", "项目", is_label=True)]},
    )
    drift = [c for c in d["column_drift"] if c.table == "存货分类"]
    assert drift and drift[0].reason == "count"


def test_drift_on_column_label():
    bad = [
        _col("label", "项目", is_label=True),
        _col("end_gross", "账面金额", group="期末余额", format="amount"),  # 名不同
        _col("end_imp", "跌价准备", group="期末余额", format="amount"),
    ]
    d = diff_tables(TPL, {"存货分类": []}, {"存货分类": bad})
    drift = [c for c in d["column_drift"] if c.table == "存货分类"]
    assert drift and drift[0].reason == "label"
    assert drift[0].template_labels[1] == "账面余额"
    assert drift[0].note_labels[1] == "账面金额"


def test_drift_on_flat_declaration_missing():
    """🔴 实测场景：既有项目列名一致但缺 `flat` → `_column_groups=None` 会回退前缀推断。"""
    stale = [
        _col("project_name", "项目名称", is_label=True),  # 少了 flat=True
        _col("end_balance", "期末数", format="amount"),
    ]
    d = diff_tables(TPL, {"开发成本": []}, {"开发成本": stale})
    drift = [c for c in d["column_drift"] if c.table == "开发成本"]
    assert drift and drift[0].reason == "group_or_flat"


def test_drift_on_group_declaration_change():
    stale = [
        _col("label", "项目", is_label=True),
        _col("end_gross", "账面余额", format="amount"),  # 少了 group
        _col("end_imp", "跌价准备", format="amount"),
    ]
    d = diff_tables(TPL, {"存货分类": []}, {"存货分类": stale})
    drift = [c for c in d["column_drift"] if c.table == "存货分类"]
    assert drift and drift[0].reason == "group_or_flat"


def test_no_drift_reported_for_missing_tables():
    """缺失表只进 missing，不重复报 column_drift。"""
    d = diff_tables(TPL, {}, {})
    assert d["column_drift"] == []


# ════════════════════════════════════════════════════════════════════
# guidance_missing（实测：同步路径不落 guidance → 既有项目恒缺）
# ════════════════════════════════════════════════════════════════════


def test_guidance_missing_for_all_existing_tables():
    sub = {t["name"]: [] for t in TPL}
    cols = {t["name"]: t["columns"] for t in TPL}
    d = diff_tables(TPL, sub, cols)
    assert d["guidance_missing"] == ["存货分类", "开发成本", "确认为存货的数据资源"]


def test_guidance_present_via_sub_guidance_map():
    sub = {t["name"]: [] for t in TPL}
    sub["_guidance"] = {"开发成本": "已有提示"}
    cols = {t["name"]: t["columns"] for t in TPL}
    d = diff_tables(TPL, sub, cols)
    assert "开发成本" not in d["guidance_missing"]
    assert "存货分类" in d["guidance_missing"]


def test_guidance_present_via_columns_guidance_map():
    sub = {t["name"]: [] for t in TPL}
    cols = {t["name"]: t["columns"] for t in TPL}
    cols["_guidance"] = {"存货分类": "已有提示"}
    d = diff_tables(TPL, sub, cols)
    assert "存货分类" not in d["guidance_missing"]


def test_blank_guidance_counts_as_missing():
    sub = {t["name"]: [] for t in TPL}
    sub["_guidance"] = {"开发成本": "   "}
    d = diff_tables(TPL, sub, {t["name"]: t["columns"] for t in TPL})
    assert "开发成本" in d["guidance_missing"]


def test_template_without_guidance_not_reported():
    tpl = [{"name": "T", "columns": [_col("label", "项目", is_label=True, flat=True)]}]
    d = diff_tables(tpl, {"T": []}, {"T": tpl[0]["columns"]})
    assert d["guidance_missing"] == []


# ════════════════════════════════════════════════════════════════════
# renamed
# ════════════════════════════════════════════════════════════════════


def test_declared_rename_takes_precedence():
    tpl = [
        {
            "name": "按组合计提存货跌价准备（续）",
            "_renamed_from": "续：",
            "columns": [_col("g", "组合", is_label=True, flat=True)],
        }
    ]
    d = diff_tables(tpl, {"续：": []}, {"续：": tpl[0]["columns"]})
    assert len(d["renamed"]) == 1
    r = d["renamed"][0]
    assert r.basis == "declared"
    assert r.note_name == "续："
    assert r.template_candidates == ("按组合计提存货跌价准备（续）",)
    assert not r.is_ambiguous
    # 已消费 → 不再报 missing / extra
    assert d["missing"] == [] and d["extra"] == []


def test_declared_rename_accepts_list():
    tpl = [
        {
            "name": "新名",
            "_renamed_from": ["旧名A", "旧名B"],
            "columns": [_col("x", "X", is_label=True, flat=True)],
        }
    ]
    d = diff_tables(tpl, {"旧名B": []}, {"旧名B": tpl[0]["columns"]})
    assert d["renamed"][0].note_name == "旧名B"


def test_structural_rename_single_candidate():
    """列结构同构 → 推断改名（basis=structural），不产生孤儿空表。"""
    d = diff_tables(
        TPL,
        {"老的开发成本表": []},
        {"老的开发成本表": _cols_of("开发成本")},
    )
    structural = [r for r in d["renamed"] if r.basis == "structural"]
    assert len(structural) == 1
    assert structural[0].note_name == "老的开发成本表"
    assert structural[0].template_candidates == ("开发成本",)
    assert "开发成本" not in d["missing"]
    assert "老的开发成本表" not in d["extra"]


def test_structural_rename_ambiguous_lists_all_candidates():
    """两张模板表列结构相同 → 候选多个，标记 ambiguous 供人工选，不自动迁移。"""
    tpl = [
        {"name": "A表", "columns": [_col("k", "组合", is_label=True, flat=True)]},
        {"name": "B表", "columns": [_col("k", "组合", is_label=True, flat=True)]},
    ]
    d = diff_tables(tpl, {"旧表": []}, {"旧表": tpl[0]["columns"]})
    assert len(d["renamed"]) == 1
    r = d["renamed"][0]
    assert r.is_ambiguous
    assert set(r.template_candidates) == {"A表", "B表"}
    # 歧义时不消费 missing（等人工确认）
    assert set(d["missing"]) == {"A表", "B表"}


def test_no_rename_when_structure_differs():
    d = diff_tables(
        TPL,
        {"无关表": []},
        {"无关表": [_col("z", "完全不同的列", is_label=True, flat=True)]},
    )
    assert d["renamed"] == []
    assert d["extra"] == ["无关表"]


def test_no_rename_when_note_table_has_no_columns():
    """附注侧无列头 → 无法结构推断，只报 extra。"""
    d = diff_tables(TPL, {"神秘表": []}, {})
    assert d["renamed"] == []
    assert "神秘表" in d["extra"]


# ════════════════════════════════════════════════════════════════════
# 健壮性
# ════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("bad", [None, {}, {"x": None}])
def test_tolerates_missing_inputs(bad: Any):
    d = diff_tables(TPL, bad, bad)
    assert isinstance(d["missing"], list)


def test_ignores_non_dict_template_entries():
    d = diff_tables([*TPL, "oops", None, 42], {}, {})  # type: ignore[list-item]
    assert d["missing"] == ["存货分类", "开发成本", "确认为存货的数据资源"]


def test_ignores_template_entry_without_name():
    d = diff_tables([{"columns": []}, *TPL], {}, {})
    assert d["missing"] == ["存货分类", "开发成本", "确认为存货的数据资源"]


# ════════════════════════════════════════════════════════════════════
# 数据结构
# ════════════════════════════════════════════════════════════════════


def test_section_diff_has_changes_ignores_extra():
    """extra（附注多出的表）只报告不删 → 不算「需要回流的变更」。"""
    d = SectionDiff(note_id="1", note_section="五、9", section_title="存货", extra=("X",))
    assert d.has_changes is False
    assert SectionDiff("1", "五、9", "存货", missing=("A",)).has_changes is True
    assert SectionDiff("1", "五、9", "存货", guidance_missing=("A",)).has_changes is True


def test_to_dict_is_json_serializable():
    import json

    d = SectionDiff(
        note_id="1",
        note_section="五、9",
        section_title="存货",
        missing=("A",),
        renamed=(RenameCandidate("旧", ("新",), "declared"),),
        column_drift=(ColumnDrift("T", "label", ("a",), ("b",)),),
        guidance_missing=("A",),
        extra=("X",),
        has_legacy_snapshot=True,
        notes=("提示",),
    )
    s = json.dumps(d.to_dict(), ensure_ascii=False)
    assert "五、9" in s and "declared" in s and "has_legacy_snapshot" in s
