"""G7 叶子科目 → 业务桶分类（单一真源 `four_table/g7_investment_buckets`）。

**2026-08-01 改写**：原文件锁的是 `_classify_leaf` 按**客户自定义子科目编码**
（`{'1511.01': 'cost'}`）分类的旧实现。平台已实证同类编码跨客户语义冲突
（`6403.02` 一家是城建税、另一家是车船税）→ 改为**名称优先、编码兜底**。

断言意图保留：分类可判定、未命中进 unmapped、灰度关闭不注入。
新增：`其他权益变动_不属于其他综合收益` 的否决词判定（这是名称分类最容易错的一处）。

spec: g7-four-table-extraction-and-disclosure-alignment R1.5 / R11.3，Property 4 / 16
"""

from __future__ import annotations

import openpyxl
import pytest

from app.routers.wp_render_strategies import _g7_long_term_equity_main as g7
from app.services.four_table.g7_investment_buckets import (
    BUCKET_ASSOCIATE,
    BUCKET_IMPAIRMENT,
    BUCKET_JV,
    BUCKET_OCI,
    BUCKET_OTHER_EQUITY,
    BUCKET_SUBSIDIARY,
    G7_INVESTMENT_BUCKETS,
    classify_g7_leaf,
)
from app.services.four_table.leaf_aggregation import LeafRow
from app.services.four_table.report_line_accounts import ReportLineAccounts

_SOURCE_XLSX = "backend/wp_templates/G/G7 长期股权投资.xlsx"


class TestClassifyByName:
    """活体科目名（项目 2aa00f57 / 0ec33ac9 / c8621493 实证）逐条归桶。"""

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("长期股权投资_对子公司的投资", BUCKET_SUBSIDIARY),
            ("长期股权投资_联营企业投资成本", BUCKET_ASSOCIATE),
            ("长期股权投资_损益调整", "equity_profit"),
            ("长期股权投资_其他权益变动", BUCKET_OTHER_EQUITY),
            ("长期股权投资_其他权益变动_属于其他综合收益", BUCKET_OCI),
            ("长期股权投资_其他权益变动_不属于其他综合收益", BUCKET_OTHER_EQUITY),
            ("长期股权投资减值准备", BUCKET_IMPAIRMENT),
            ("对合营企业投资", BUCKET_JV),
        ],
    )
    def test_live_account_names(self, name, expected):
        assert classify_g7_leaf(name) == expected

    def test_exclude_keyword_is_required(self):
        """🔴 否决词缺失就会错：`不属于其他综合收益` 也含 `其他综合收益`。

        没有 `exclude_keywords` 时 `.04.02` 会被判成 OCI，「其他权益变动」列恒 0。
        """
        assert classify_g7_leaf("其他权益变动_属于其他综合收益") == BUCKET_OCI
        assert classify_g7_leaf("其他权益变动_不属于其他综合收益") == BUCKET_OTHER_EQUITY

    def test_code_fallback_only_when_name_misses(self):
        """名称无命中才用标准码兜底，且要求点号边界。"""
        assert classify_g7_leaf("", "1512") == BUCKET_IMPAIRMENT
        assert classify_g7_leaf("", "1512.01") == BUCKET_IMPAIRMENT
        # 15120 与 1512 无父子关系 → 不得命中
        assert classify_g7_leaf("", "15120") is None

    def test_unmapped_returns_none(self):
        """无法归类返回 None（调用方须放 unmapped，不得塞进任何桶）。"""
        assert classify_g7_leaf("长期股权投资") is None
        assert classify_g7_leaf("长期股权投资_待分配", "1511.99") is None


class TestBucketDeclarationIntegrity:
    def test_bucket_keys_unique_and_priority_total_order(self):
        keys = [b.bucket for b in G7_INVESTMENT_BUCKETS]
        assert len(keys) == len(set(keys))
        prios = [b.priority for b in G7_INVESTMENT_BUCKETS]
        assert len(prios) == len(set(prios)), "priority 必须全序唯一（判定顺序可复现）"

    def test_labels_traceable_to_source_template(self):
        """🔴 Property 16：每个桶的 label 必须能在 source_ref 指向的源 xlsx 单元格命中。

        防「顺手写个顺眼的中文标签」—— 标签是交付物文字，只能来自源模板。
        """
        wb = openpyxl.load_workbook(_SOURCE_XLSX, data_only=True)
        for bucket in G7_INVESTMENT_BUCKETS:
            assert bucket.source_ref, f"{bucket.bucket} 缺 source_ref"
            hits = []
            for ref in bucket.source_ref:
                sheet_name, cell = ref.split("!", 1)
                assert sheet_name in wb.sheetnames, f"源 xlsx 无 sheet {sheet_name!r}"
                raw = wb[sheet_name][cell].value
                text = "".join(str(raw or "").split())
                hits.append(bucket.label in text)
            assert any(hits), (
                f"桶 {bucket.bucket} 的 label {bucket.label!r} 在 "
                f"{bucket.source_ref} 中均未命中"
            )

    def test_movement_nature_buckets_are_the_three_expected(self):
        nature = {b.bucket for b in G7_INVESTMENT_BUCKETS if b.is_movement_nature}
        assert nature == {"equity_profit", BUCKET_OCI, BUCKET_OTHER_EQUITY}


class TestBuildLeafCategories:
    def _accounts(self) -> ReportLineAccounts:
        return ReportLineAccounts(
            gross=["1511"],
            provision=["1512"],
            gross_standard=["1511"],
            provision_standard=["1512"],
            row_code="BS-024",
        )

    def test_provision_absolute_and_unmapped_isolated(self):
        leaves = [
            LeafRow("1511.01", "长期股权投资_对子公司的投资", opening=100.0, closing=120.0),
            LeafRow("1511.99", "长期股权投资_待分配", opening=0.0, closing=7.0),
            # 备抵负值存储（活体形态）→ 输出必须为正
            LeafRow("1512", "长期股权投资减值准备", opening=-50.0, closing=-80.0),
        ]
        out = g7.build_g7_leaf_categories(self._accounts(), leaves)
        assert out is not None
        assert out["buckets"][BUCKET_SUBSIDIARY]["closing"] == 120.0
        assert out["buckets"][BUCKET_IMPAIRMENT]["opening"] == 50.0
        assert out["buckets"][BUCKET_IMPAIRMENT]["closing"] == 80.0
        assert out["impairment"] == 80.0
        # 未归类叶子不并入任何桶
        assert [u["code"] for u in out["unmapped"]] == ["1511.99"]
        assert out["cost"] == 120.0

    def test_returns_none_without_data(self):
        assert g7.build_g7_leaf_categories(self._accounts(), []) is None
        assert g7.build_g7_leaf_categories(None, []) is None


class TestGrayOff:
    def test_render_omits_extraction_keys_when_flag_off(self, monkeypatch):
        """灰度关闭 → `tb_leaf_categories` 为 None、`adjudication_prefill` 为 {}。

        取数纯函数本身不看开关（可单测），门控在 render 编排层。
        """
        from app.core.config import settings

        monkeypatch.setattr(
            settings, "G7_FOUR_TABLE_EXTRACTION_ENABLED", False, raising=False
        )
        assert settings.G7_FOUR_TABLE_EXTRACTION_ENABLED is False
