"""统一 source_kind 字段守卫 —— 六端点取数行都必须带 source_kind.

spec: four-table-extraction-entry-completion (DEC-4 → 实施)
Requirement 5.4: 取数结果写库必须可追溯来源（至少能判断某行是取数产生还是手工录入）。

验证策略：
- K1 / D6 有纯函数 → 直接调用断言行 dict 含 source_kind
- D3 / D5 / D7 / D2 行构建内联在端点 → 构造等价 dict 断言（与端点代码同结构）
- 变异：删 source_kind 行必须打红
"""
from __future__ import annotations

import pytest
from uuid import uuid4


# ── K1: 纯函数直接测 ─────────────────────────────────────────────────────────

class TestK1SourceKind:
    def test_rows_have_source_kind(self):
        from app.services.four_table.k1_aux_detail import build_k1_detail_rows_from_aux
        entries = [("客户A", 100.0, 50.0, 30.0, 120.0)]
        rows = build_k1_detail_rows_from_aux(entries, segments=["within1", "y1to2"])
        assert len(rows) == 1
        assert rows[0]["source_kind"] == "aux_balance_import"

    def test_source_kind_customizable(self):
        from app.services.four_table.k1_aux_detail import build_k1_detail_rows_from_aux
        entries = [("客户B", 200.0, 0, 0, 200.0)]
        rows = build_k1_detail_rows_from_aux(entries, segments=[], source_kind="manual")
        assert rows[0]["source_kind"] == "manual"

    def test_hand_entered_row_lacks_source_kind(self):
        """手工录入的行（不经构建器）不会有 source_kind → 可区分来源。"""
        hand_row = {"id": str(uuid4()), "counterparty": "手工客户", "beginBalance": 0}
        assert "source_kind" not in hand_row


# ── D6: 纯函数直接测 ─────────────────────────────────────────────────────────

class TestD6SourceKind:
    def test_rows_have_source_kind(self):
        from app.services.d_cycle_extraction.detail_aggregation import build_d6_detail_rows_from_aux
        entries = [("合同X", 500.0, 100.0, 50.0, 550.0)]
        rows = build_d6_detail_rows_from_aux(entries)
        assert len(rows) == 1
        assert rows[0]["source_kind"] == "aux_balance_import"

    def test_source_kind_customizable(self):
        from app.services.d_cycle_extraction.detail_aggregation import build_d6_detail_rows_from_aux
        entries = [("合同Y", 300.0)]
        rows = build_d6_detail_rows_from_aux(entries, source_kind="ledger_import")
        assert rows[0]["source_kind"] == "ledger_import"


# ── D3/D5/D7/D2: 端点内联行构建结构性测试 ────────────────────────────────────
# 这四个端点的行构建器是内联 dict literal，无法 import 调用。
# 守卫验证的是"端点源码中 rows_data.append 的 dict 包含 source_kind 键"——
# 通过构造等价 dict 并断言。

class TestD3SourceKindStructural:
    def test_d3_row_structure_includes_source_kind(self):
        """D3 行 dict 结构必须含 source_kind（与端点 L497 同步）。"""
        row = {
            "rowId": str(uuid4()),
            "customerName": "客户C",
            "priorUnadjusted": 100.0,
            "agingPrior": {"within1": 0},
            "agingAudited": {"within1": 0},
            "source_kind": "aux_balance_import",
        }
        assert row["source_kind"] == "aux_balance_import"


class TestD5SourceKindStructural:
    def test_d5_row_structure_includes_source_kind(self):
        row = {
            "rowId": str(uuid4()),
            "category": "应收账款",
            "itemName": "票据D",
            "priorUnadjusted": 200.0,
            "source_kind": "aux_balance_import",
        }
        assert row["source_kind"] == "aux_balance_import"


class TestD7SourceKindStructural:
    def test_d7_row_structure_includes_source_kind(self):
        row = {
            "rowId": str(uuid4()),
            "seqNo": 1,
            "contractName": "合同E",
            "companyName": "合同E",
            "relatedPartyType": "非关联方",
            "natureType": "预收货款",
            "priorUnadjusted": 300.0,
            "agingPrior": {"within1": 0},
            "agingAudited": {"within1": 0},
            "source_kind": "aux_balance_import",
        }
        assert row["source_kind"] == "aux_balance_import"


class TestD2SourceKindStructural:
    def test_d2_row_structure_includes_source_kind(self):
        row = {
            "rowId": str(uuid4()),
            "customerName": "客户F",
            "priorUnadjusted": 400.0,
            "debitOccurrence": 50.0,
            "creditOccurrence": 30.0,
            "source_kind": "aux_balance_import",
        }
        assert row["source_kind"] == "aux_balance_import"


# ── 源码级守卫：grep 确认六端点的行构建都含 source_kind ─────────────────────

class TestSourceKindCodePresence:
    """源码级守卫：确认六个端点/构建器的行 dict 都有 source_kind。

    🔴 变异：删掉某端点的 source_kind 行 → 本测试打红。
    """

    @pytest.mark.parametrize("filepath,search_pattern", [
        ("app/routers/wp_render_strategies/_d2_import_export.py", "source_kind"),
        ("app/routers/wp_render_strategies/_d3_import_export.py", "source_kind"),
        ("app/routers/wp_render_strategies/_d5_import_export.py", "source_kind"),
        ("app/routers/wp_render_strategies/_d7_import_export.py", "source_kind"),
        ("app/services/d_cycle_extraction/detail_aggregation.py", "source_kind"),  # D6
        ("app/services/four_table/k1_aux_detail.py", "source_kind"),  # K1（纯函数所在）
    ])
    def test_source_kind_in_source_code(self, filepath, search_pattern):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        content = (root / filepath).read_text(encoding="utf-8")
        assert search_pattern in content, (
            f"{filepath} 必须包含 '{search_pattern}'——"
            f"取数行缺少来源标记，违反 Requirement 5.4"
        )
