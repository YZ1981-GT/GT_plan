"""附注主表交接（需求 5）：build_main_skeleton + 引擎缺表建骨架 + 遮挡数据检查 + 共享夹具对拍。

spec: chain-closure-phase3-push-rollout · Task 12 · design §五
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.services.formula_push import note_writer as nw
from app.services.formula_push.note_writer import has_obscured_data as _has_obscured_data

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ── 共享夹具对拍（需求 5.5）──────────────────────────────────────────────


@pytest.fixture(scope="module")
def fixture():
    with open(FIXTURES_DIR / "e1_note_skeleton.json", encoding="utf-8") as f:
        return json.load(f)


class TestBuildMainSkeletonFixtureAlignment:
    """后端 build_main_skeleton 产出与共享夹具逐字一致（需求 5.5）。"""

    @pytest.mark.parametrize("template_type", ["listed", "soe"])
    def test_rows_match_fixture(self, fixture, template_type):
        skel = nw.build_main_skeleton(template_type, "五、1" if template_type == "listed" else "八、1", "货币资金")
        assert skel is not None, f"build_main_skeleton('{template_type}', '货币资金') 返回 None"
        expected_rows = fixture[template_type]["rows"]
        assert skel.rows == expected_rows, (
            f"{template_type} 行标签或结构与共享夹具不一致\n"
            f"  got:      {skel.rows}\n"
            f"  expected: {expected_rows}"
        )

    @pytest.mark.parametrize("template_type", ["listed", "soe"])
    def test_columns_match_fixture(self, fixture, template_type):
        skel = nw.build_main_skeleton(template_type, "五、1" if template_type == "listed" else "八、1", "货币资金")
        assert skel is not None
        expected_cols = fixture[template_type]["columns"]
        assert skel.columns == expected_cols, (
            f"{template_type} 列定义与共享夹具不一致\n"
            f"  got:      {skel.columns}\n"
            f"  expected: {expected_cols}"
        )


class TestBuildMainSkeletonStructure:
    """build_main_skeleton 结构正确性。"""

    @pytest.mark.parametrize("template_type", ["listed", "soe"])
    def test_rows_have_none_values(self, template_type):
        """所有行的 end_amount / prior_amount 初始为 None。"""
        skel = nw.build_main_skeleton(template_type, "五、1" if template_type == "listed" else "八、1", "货币资金")
        assert skel is not None
        for row in skel.rows:
            assert row["end_amount"] is None
            assert row["prior_amount"] is None

    @pytest.mark.parametrize("template_type", ["listed", "soe"])
    def test_exactly_one_total_row(self, template_type):
        skel = nw.build_main_skeleton(template_type, "五、1" if template_type == "listed" else "八、1", "货币资金")
        assert skel is not None
        total_rows = [r for r in skel.rows if r.get("is_total")]
        assert len(total_rows) == 1
        assert total_rows[0]["label"] == "合计"

    def test_listed_has_more_rows_than_soe(self):
        """listed 比 soe 多「存放财务公司款项」「存款应计利息」两行（准则口径差异）。"""
        listed = nw.build_main_skeleton("listed", "五、1", "货币资金")
        soe = nw.build_main_skeleton("soe", "八、1", "货币资金")
        assert listed is not None and soe is not None
        assert len(listed.rows) == len(soe.rows) + 2
        listed_labels = {r["label"] for r in listed.rows}
        soe_labels = {r["label"] for r in soe.rows}
        assert "存放财务公司款项" in listed_labels - soe_labels
        assert "存款应计利息" in listed_labels - soe_labels

    def test_columns_differ_in_prior_label(self):
        """listed 期初列叫「上年年末余额」，soe 叫「期初余额」。"""
        listed = nw.build_main_skeleton("listed", "五、1", "货币资金")
        soe = nw.build_main_skeleton("soe", "八、1", "货币资金")
        assert listed is not None and soe is not None
        listed_prior = [c for c in listed.columns if c["key"] == "prior_amount"][0]
        soe_prior = [c for c in soe.columns if c["key"] == "prior_amount"][0]
        assert listed_prior["label"] == "上年年末余额"
        assert soe_prior["label"] == "期初余额"

    def test_unknown_template_returns_none(self):
        assert nw.build_main_skeleton("unknown", "五、1", "货币资金") is None

    def test_unknown_table_returns_none(self):
        assert nw.build_main_skeleton("listed", "五、1", "不存在的表") is None

    def test_explicit_section_is_authoritative(self):
        """传入的章节决定查找位置，不能回退到模板类型的隐式章节。"""
        assert nw.build_main_skeleton("listed", "八、1", "货币资金") is None

    def test_custom_template_and_section_are_supported(self, tmp_path, monkeypatch):
        """任意规则登记的模板类型 / 章节均可构建骨架。"""
        (tmp_path / "note_template_custom.json").write_text(
            json.dumps({
                "template_type": "custom",
                "sections": [{
                    "section_number": "自定义-1",
                    "tables": [{
                        "name": "自定义表",
                        "rows": [{"label": "项目一", "is_total": True}],
                        "columns": [{"key": "label", "label": "项目", "is_label": True}],
                    }],
                }],
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        old_cache = dict(nw._TEMPLATE_CACHE)
        nw._TEMPLATE_CACHE.clear()
        monkeypatch.setattr(nw, "_DATA_DIR", tmp_path)
        try:
            skel = nw.build_main_skeleton("custom", "自定义-1", "自定义表")
        finally:
            nw._TEMPLATE_CACHE.clear()
            nw._TEMPLATE_CACHE.update(old_cache)
        assert skel is not None
        assert skel.rows == [{"label": "项目一", "end_amount": None, "prior_amount": None, "is_total": True}]


# ── 遮挡数据检查（需求 5.2）──────────────────────────────────────────────


class TestObscuredDataCheck:
    """_has_obscured_data 检测原表格有非空非零数值。"""

    def test_empty_table_data_no_obstruction(self):
        """空 table_data 不阻塞。"""
        td = {"_source": "workpaper", "sub_table_data": {}}
        assert _has_obscured_data(td, "货币资金") is None

    def test_rows_with_business_values_blocks(self):
        """顶层 rows 有非空非零数值 → 阻塞。"""
        td = {
            "_source": "workpaper",
            "rows": [{"label": "库存现金", "end_amount": 1000}],
        }
        result = _has_obscured_data(td, "货币资金")
        assert result is not None
        assert "rows" in result

    def test_rows_with_only_zero_and_none_passes(self):
        td = {
            "_source": "workpaper",
            "rows": [{"label": "库存现金", "end_amount": 0, "prior_amount": None}],
        }
        assert _has_obscured_data(td, "货币资金") is None

    def test_tables_with_values_blocks(self):
        td = {
            "_source": "workpaper",
            "_tables": [{"rows": [{"label": "test", "values": [100]}]}],
        }
        result = _has_obscured_data(td, "货币资金")
        assert result is not None
        assert "_tables" in result

    def test_tables_with_only_none_passes(self):
        td = {
            "_source": "workpaper",
            "_tables": [{"rows": [{"label": "test", "values": [None, 0]}]}],
        }
        assert _has_obscured_data(td, "货币资金") is None


# ── 骨架合并逻辑（需求 5.3）──────────────────────────────────────────────


class TestSkeletonMerge:
    """验证引擎的骨架合并保留其余子表和叙述。"""

    @pytest.mark.parametrize("template_type", ["listed", "soe"])
    def test_skeleton_rows_locatable_after_build(self, template_type):
        """build_main_skeleton 产出的行可被 locate_table 定位。"""
        skel = nw.build_main_skeleton(template_type, "五、1" if template_type == "listed" else "八、1", "货币资金")
        assert skel is not None
        # 模拟将骨架写入 table_data
        td = {
            "_source": "workpaper",
            "sub_table_data": {"货币资金": copy.deepcopy(skel.rows)},
            "_sub_table_columns": {"货币资金": copy.deepcopy(skel.columns)},
        }
        table, reason = nw.locate_table(td, "货币资金")
        assert reason is None
        assert table is not None
        assert len(table.rows) == len(skel.rows)

    def test_shallow_merge_preserves_other_subtables(self):
        """骨架合并保留其余子表。"""
        skel = nw.build_main_skeleton("soe", "八、1", "货币资金")
        assert skel is not None
        existing_td = {
            "_source": "workpaper",
            "sub_table_data": {
                "受限制的货币资金明细": [{"label": "保证金", "end_amount": 500}],
            },
            "_sub_table_columns": {},
            "text_content": "测试叙述",
            "_note_texts": [{"section": "soe-note-restricted", "text": "说明文字"}],
        }
        # 模拟浅合并
        sub = existing_td.setdefault("sub_table_data", {})
        sub["货币资金"] = copy.deepcopy(skel.rows)
        cols = existing_td.setdefault("_sub_table_columns", {})
        cols["货币资金"] = copy.deepcopy(skel.columns)
        # 验证其余子表和叙述保留
        assert "受限制的货币资金明细" in existing_td["sub_table_data"]
        assert existing_td["sub_table_data"]["受限制的货币资金明细"][0]["end_amount"] == 500
        assert existing_td["text_content"] == "测试叙述"
        assert existing_td["_note_texts"][0]["text"] == "说明文字"
        # 且主表已写入
        assert "货币资金" in existing_td["sub_table_data"]
        assert len(existing_td["sub_table_data"]["货币资金"]) == len(skel.rows)


# ── 前端 mainTable:false 语义（需求 5.4）──────────────────────────────────
# 此处只验证 fixture 对齐关系；前端 vitest 单独覆盖 buildE1SyncPayload({mainTable:false})


class TestFixtureRowLabelsMatchFrontend:
    """共享夹具行标签必须与前端 e1MainRows noteLabel 一致（需求 5.5）。

    前端真源是 e1DisclosureScope 的 E1_MAIN_ROWS_LISTED / SOE，
    骨架行标签是 noteLabel（推送到附注的字面）或 label。
    此处按前端 source of truth 写死检查。
    """

    def test_listed_labels_match_frontend(self, fixture):
        """listed 骨架行标签 = 前端 E1_MAIN_ROWS_LISTED 的 noteLabel ?? label。"""
        expected = [
            "库存现金", "银行存款", "存放财务公司款项",
            "其他货币资金", "存款应计利息", "数字货币",
            "合计", "其中：存放在境外的款项总额",
        ]
        actual = [r["label"] for r in fixture["listed"]["rows"]]
        assert actual == expected

    def test_soe_labels_match_frontend(self, fixture):
        """soe 骨架行标签 = 前端 E1_MAIN_ROWS_SOE 的 noteLabel ?? label。"""
        expected = [
            "库存现金", "银行存款", "其他货币资金",
            "数字货币", "合计", "其中：存放在境外的款项总额",
        ]
        actual = [r["label"] for r in fixture["soe"]["rows"]]
        assert actual == expected
