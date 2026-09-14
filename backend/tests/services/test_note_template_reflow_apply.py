"""模板回流写入（apply_reflow_tables）单测。

Spec: .kiro/specs/disclosure-note-follow-actual-content/ R2 / Task 6
验证 Property 4（只增不减）。
"""
from __future__ import annotations

from typing import Any

import pytest

from app.services.note_template_reflow_service import (
    apply_reflow_tables,
)


def _col(key: str, label: str, **kw: Any) -> dict[str, Any]:
    return {"key": key, "label": label, **kw}


# ════════════════════════════════════════════════════════════════════
# 测试用模板
# ════════════════════════════════════════════════════════════════════

TPL: list[dict[str, Any]] = [
    {
        "name": "存货分类",
        "columns": [
            _col("label", "项目", is_label=True),
            _col("end_gross", "账面余额", group="期末余额", format="amount"),
            _col("end_imp", "跌价准备", group="期末余额", format="amount"),
        ],
        "rows": [
            {"label": "原材料", "end_gross": None, "end_imp": None},
            {"label": "在产品", "end_gross": None, "end_imp": None},
        ],
    },
    {
        "name": "开发成本",
        "columns": [
            _col("project_name", "项目名称", is_label=True, flat=True),
            _col("end_balance", "期末数", format="amount"),
        ],
        "rows": [
            {"project_name": "", "end_balance": None},
        ],
    },
    {
        "name": "确认为存货的数据资源",
        "columns": [
            _col("label", "项目", is_label=True, flat=True),
            _col("purchased", "外购的数据资源存货", format="amount"),
        ],
        "rows": [],
    },
]


# ════════════════════════════════════════════════════════════════════
# 基础：空附注 → 补齐全部
# ════════════════════════════════════════════════════════════════════


class TestApplyReflowBasic:
    def test_empty_note_gets_all_tables(self):
        sub: dict[str, Any] = {}
        cols: dict[str, Any] = {}
        result = apply_reflow_tables(TPL, sub, cols)
        assert set(result["added"]) == {"存货分类", "开发成本", "确认为存货的数据资源"}
        assert "存货分类" in sub
        assert "存货分类" in cols

    def test_existing_table_not_overwritten(self):
        """已有表的行数据不被覆盖（Property 4）。"""
        existing_rows = [{"label": "自定义行", "end_gross": 100.0, "end_imp": 50.0}]
        sub: dict[str, Any] = {"存货分类": list(existing_rows)}
        cols: dict[str, Any] = {"存货分类": TPL[0]["columns"]}
        result = apply_reflow_tables(TPL, sub, cols)
        # 不应覆盖已有行
        assert sub["存货分类"] == existing_rows
        assert "存货分类" not in result["added"]

    def test_missing_table_added_with_skeleton(self):
        """缺失表用模板骨架行填充。"""
        sub: dict[str, Any] = {"存货分类": [{"label": "test", "end_gross": 1}]}
        cols: dict[str, Any] = {"存货分类": TPL[0]["columns"]}
        result = apply_reflow_tables(TPL, sub, cols)
        assert "开发成本" in result["added"]
        assert "确认为存货的数据资源" in result["added"]
        assert sub["开发成本"] == TPL[1]["rows"]

    def test_header_label_rows_excluded_from_skeleton(self):
        """模板中 row_type=header_label 的假数据行不进骨架。"""
        tpl_with_header = [
            {
                "name": "测试表",
                "columns": [_col("label", "项目", is_label=True)],
                "rows": [
                    {"label": "合计", "row_type": "header_label"},
                    {"label": "真实行", "end": None},
                ],
            }
        ]
        sub: dict[str, Any] = {}
        cols: dict[str, Any] = {}
        apply_reflow_tables(tpl_with_header, sub, cols)
        assert len(sub["测试表"]) == 1
        assert sub["测试表"][0]["label"] == "真实行"


# ════════════════════════════════════════════════════════════════════
# 列头漂移修正
# ════════════════════════════════════════════════════════════════════


class TestApplyReflowColumnDrift:
    def test_missing_columns_added(self):
        """附注表无列定义 → 从模板补入。"""
        sub: dict[str, Any] = {"存货分类": [{"label": "a"}]}
        cols: dict[str, Any] = {}  # 无列定义
        result = apply_reflow_tables(TPL, sub, cols)
        assert "存货分类" in result["columns_updated"]
        assert cols["存货分类"] == TPL[0]["columns"]

    def test_label_drift_updated(self):
        """列名不同 → 更新列定义。"""
        old_cols = [_col("label", "项目"), _col("end_gross", "旧名"), _col("end_imp", "跌价")]
        sub: dict[str, Any] = {"存货分类": [{"label": "a"}]}
        cols: dict[str, Any] = {"存货分类": old_cols}
        result = apply_reflow_tables(TPL, sub, cols)
        assert "存货分类" in result["columns_updated"]
        assert cols["存货分类"] == TPL[0]["columns"]

    def test_group_flat_drift_updated(self):
        """group/flat 声明不同 → 更新列定义。"""
        # 去掉 group 声明
        old_cols = [
            _col("label", "项目", is_label=True),
            _col("end_gross", "账面余额", format="amount"),  # no group
            _col("end_imp", "跌价准备", format="amount"),  # no group
        ]
        sub: dict[str, Any] = {"存货分类": [{"label": "a"}]}
        cols: dict[str, Any] = {"存货分类": old_cols}
        result = apply_reflow_tables(TPL, sub, cols)
        assert "存货分类" in result["columns_updated"]

    def test_identical_columns_not_updated(self):
        """列头与模板一致 → 不更新。"""
        sub: dict[str, Any] = {"存货分类": [{"label": "a"}]}
        cols: dict[str, Any] = {"存货分类": list(TPL[0]["columns"])}
        result = apply_reflow_tables(TPL, sub, cols)
        assert "存货分类" not in result["columns_updated"]

    def test_row_data_unchanged_after_column_update(self):
        """列头更新后行数据不变（Property 4）。"""
        original_rows = [{"label": "自定义", "end_gross": 999.99}]
        sub: dict[str, Any] = {"存货分类": list(original_rows)}
        cols: dict[str, Any] = {"存货分类": [_col("label", "项目"), _col("x", "旧列")]}
        apply_reflow_tables(TPL, sub, cols)
        assert sub["存货分类"] == original_rows


# ════════════════════════════════════════════════════════════════════
# 改名
# ════════════════════════════════════════════════════════════════════


class TestApplyReflowRename:
    def test_declared_rename_auto_executed(self):
        """模板 _renamed_from 声明的非歧义改名自动执行。"""
        tpl_rename = [
            {
                "name": "新表名",
                "columns": [_col("label", "项目")],
                "rows": [],
                "_renamed_from": "旧表名",
            },
        ]
        sub: dict[str, Any] = {"旧表名": [{"label": "数据行", "amount": 100}]}
        cols: dict[str, Any] = {"旧表名": [_col("label", "项目"), _col("amount", "金额")]}
        result = apply_reflow_tables(tpl_rename, sub, cols)
        assert ("旧表名", "新表名") in result["renamed"]
        assert "旧表名" not in sub
        assert sub["新表名"] == [{"label": "数据行", "amount": 100}]

    def test_explicit_rename_pair(self):
        """用户显式确认的改名对被执行。"""
        tpl_rename = [
            {"name": "新名A", "columns": [_col("k", "列")], "rows": []},
        ]
        sub: dict[str, Any] = {"旧名A": [{"k": 1}]}
        cols: dict[str, Any] = {}
        result = apply_reflow_tables(
            tpl_rename, sub, cols, include_renamed=[("旧名A", "新名A")]
        )
        assert ("旧名A", "新名A") in result["renamed"]
        assert sub["新名A"] == [{"k": 1}]

    def test_rename_preserves_row_data(self):
        """改名后行数据保持不变（Property 4）。"""
        rows = [{"label": "重要数据", "amount": 12345.67}]
        tpl_rename = [
            {"name": "新名", "columns": [_col("label", "标签")], "rows": [], "_renamed_from": "旧名"},
        ]
        sub: dict[str, Any] = {"旧名": list(rows)}
        cols: dict[str, Any] = {}
        apply_reflow_tables(tpl_rename, sub, cols)
        assert sub["新名"] == rows

    def test_rename_new_name_already_exists_skipped(self):
        """新名已存在于附注 → 不执行改名（防覆盖）。"""
        tpl_rename = [
            {"name": "已有表", "columns": [_col("k", "列")], "rows": [], "_renamed_from": "旧名"},
        ]
        sub: dict[str, Any] = {"旧名": [{"k": 1}], "已有表": [{"k": 2}]}
        cols: dict[str, Any] = {}
        result = apply_reflow_tables(tpl_rename, sub, cols)
        assert result["renamed"] == []
        assert sub["旧名"] == [{"k": 1}]
        assert sub["已有表"] == [{"k": 2}]


# ════════════════════════════════════════════════════════════════════
# Property 4: PBT — 只增不减
# ════════════════════════════════════════════════════════════════════


class TestPropertyOnlyAddNeverRemove:
    """Property 4：apply_reflow 后原有每张表的行数与行标签集合不变。"""

    @pytest.mark.parametrize(
        "existing_sub",
        [
            {"存货分类": [{"label": "原材料", "end_gross": 100}]},
            {
                "存货分类": [{"label": "a"}, {"label": "b"}, {"label": "c"}],
                "开发成本": [{"project_name": "项目一", "end_balance": 500}],
            },
            {"自定义表": [{"x": 1}, {"x": 2}]},  # extra table not in template
        ],
    )
    def test_original_tables_row_count_preserved(self, existing_sub: dict[str, Any]):
        import copy

        before = copy.deepcopy(existing_sub)
        cols: dict[str, Any] = {}
        apply_reflow_tables(TPL, existing_sub, cols)
        for name, rows in before.items():
            assert name in existing_sub, f"表 {name!r} 消失了"
            assert len(existing_sub[name]) == len(rows), f"表 {name!r} 行数变了"
            before_labels = {str(r.get("label", "")) for r in rows if isinstance(r, dict)}
            after_labels = {
                str(r.get("label", "")) for r in existing_sub[name] if isinstance(r, dict)
            }
            assert before_labels == after_labels, f"表 {name!r} 标签集变了"

    def test_table_set_only_grows(self):
        """表集合 = 原集合 ∪ 模板缺失表集合。"""
        sub: dict[str, Any] = {"存货分类": [], "自定义": []}
        cols: dict[str, Any] = {}
        apply_reflow_tables(TPL, sub, cols)
        assert "存货分类" in sub
        assert "自定义" in sub
        assert "开发成本" in sub
        assert "确认为存货的数据资源" in sub


# ════════════════════════════════════════════════════════════════════
# 边界情况
# ════════════════════════════════════════════════════════════════════


class TestApplyReflowEdgeCases:
    def test_empty_template(self):
        """模板无表 → 无变化。"""
        sub: dict[str, Any] = {"a": [{"x": 1}]}
        cols: dict[str, Any] = {}
        result = apply_reflow_tables([], sub, cols)
        assert result["added"] == []
        assert result["renamed"] == []
        assert result["columns_updated"] == []

    def test_meta_keys_ignored(self):
        """以 _ 开头的元数据键不参与匹配。"""
        sub: dict[str, Any] = {"_source": "workpaper", "存货分类": []}
        cols: dict[str, Any] = {"存货分类": TPL[0]["columns"]}
        result = apply_reflow_tables(TPL, sub, cols)
        assert "_source" not in result["added"]
        assert "_source" in sub  # 保持不动

    def test_none_inputs(self):
        """None 容忍。"""
        sub: dict[str, Any] = {}
        cols: dict[str, Any] = {}
        result = apply_reflow_tables(None, sub, cols)  # type: ignore[arg-type]
        assert result["added"] == []

    def test_template_without_columns(self):
        """模板表无 columns 字段 → 不报错、不补列头。"""
        tpl_no_cols = [{"name": "简单表", "rows": [{"label": "行一"}]}]
        sub: dict[str, Any] = {}
        cols: dict[str, Any] = {}
        result = apply_reflow_tables(tpl_no_cols, sub, cols)
        assert "简单表" in result["added"]
        assert "简单表" not in cols
