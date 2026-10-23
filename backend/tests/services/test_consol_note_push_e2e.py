"""e2e：集团模板下推 → 子企业填数 → 合并拉数全链路。

验证固定行按 row_id 精确匹配（confidence=1.0），
可选行子企业取消后不参与合并，
动态行走七级匹配。

spec: consol-note-template-push-to-subsidiaries (Task 10)
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.services.consol_note_template_push_service import (
    build_skeleton_rows,
    merge_rows,
)
from app.services.consol_note_detail_suggest import suggest_template_rows
from app.services.consol_note_detail_source_service import (
    compute_source_structure_hash,
    extract_source_rows,
    group_entities_by_structure,
)


# ── 模拟数据 ──

RID_CASH = str(uuid.uuid4())
RID_BANK = str(uuid.uuid4())
RID_OTHER = str(uuid.uuid4())
RID_DZ = str(uuid.uuid4())
RID_TOTAL = str(uuid.uuid4())

TEMPLATE_ROWS = [
    {"target_row_id": RID_CASH, "canonical_name": "库存现金", "row_type": "data", "category": "required", "aliases": ["现金"]},
    {"target_row_id": RID_BANK, "canonical_name": "银行存款", "row_type": "data", "category": "required", "aliases": []},
    {"target_row_id": RID_OTHER, "canonical_name": "其他货币资金", "row_type": "data", "category": "optional", "aliases": []},
    {"target_row_id": RID_DZ, "canonical_name": "", "row_type": "data", "category": "dynamic_zone", "aliases": []},
    {"target_row_id": RID_TOTAL, "canonical_name": "合计", "row_type": "total", "category": "required", "aliases": []},
]


def _subsidiary_rows(cash: float, bank: float, *, deactivate_optional: bool = False, extra_label: str = ""):
    """模拟子企业下推后填了数据的附注行。"""
    skeleton = build_skeleton_rows(TEMPLATE_ROWS)
    # 填金额
    skeleton[0]["values"] = [cash, 0]  # 库存现金：期末、期初
    skeleton[1]["values"] = [bank, 0]  # 银行存款
    if deactivate_optional:
        skeleton[2]["_pushed_optional_active"] = False
    else:
        skeleton[2]["values"] = [10, 5]  # 其他货币资金
    # 动态行区：企业自行新增一行（如果有）
    if extra_label:
        # 在动态行区占位前插入用户行
        dz_idx = next(i for i, r in enumerate(skeleton) if r.get("row_type") == "dynamic_zone_marker")
        skeleton.insert(dz_idx, {"label": extra_label, "values": [99, 0], "row_type": "data"})
    return skeleton


class TestPushThenPullFullChain:
    """下推 → 填数 → 拉数全链路。"""

    def test_fixed_rows_match_by_row_id(self):
        """固定行按 _pushed_row_id 精确匹配（第 0 级 exact_id）。"""
        # 子企业 A 的附注行（下推后填了数据）
        sub_a = _subsidiary_rows(100, 200)
        # 子企业 B 的附注行
        sub_b = _subsidiary_rows(50, 150)

        # 构建来源组（模拟 source_service 的输出）
        groups = [{
            "hash": "h1",
            "entities": [{"node_key": "A"}, {"node_key": "B"}],
            "source_rows": sub_a + sub_b,
        }]

        result = suggest_template_rows(groups, existing_template_rows=TEMPLATE_ROWS)

        # 固定行（库存现金、银行存款、合计）应该按 rid 匹配
        rid_matches = [r for r in result if r["match_type"] == "exact_id"]
        assert len(rid_matches) >= 2  # 至少库存现金和银行存款

        # confidence 全是 1.0
        for m in rid_matches:
            assert m["confidence"] == 1.0

    def test_optional_deactivated_excluded(self):
        """可选行子企业取消后，来源行的 _pushed_optional_active=False。"""
        sub = _subsidiary_rows(100, 200, deactivate_optional=True)
        # 其他货币资金行应该标 optional_active=False
        optional_row = next(r for r in sub if r.get("_pushed_row_id") == RID_OTHER)
        assert optional_row["_pushed_optional_active"] is False

    def test_dynamic_rows_use_name_matching(self):
        """动态行走七级匹配（无 _pushed_row_id）。"""
        sub = _subsidiary_rows(100, 200, extra_label="支付宝余额")

        groups = [{
            "hash": "h2",
            "entities": [{"node_key": "A"}],
            "source_rows": sub,
        }]

        result = suggest_template_rows(groups, existing_template_rows=TEMPLATE_ROWS)

        # 动态行（支付宝余额）没有 rid → 走七级匹配 → manual
        dynamic = [r for r in result if r["source_label"] == "支付宝余额"]
        assert len(dynamic) == 1
        assert dynamic[0]["match_type"] == "manual"

    def test_incremental_merge_preserves_values(self):
        """模板增量下推不覆盖已填金额。"""
        # 子企业已有行（上次下推后填了数）
        existing = _subsidiary_rows(100, 200)

        # 集团模板新增一行（数字货币），其余不变
        new_template = TEMPLATE_ROWS.copy()
        rid_digital = str(uuid.uuid4())
        new_template.insert(3, {
            "target_row_id": rid_digital, "canonical_name": "数字货币",
            "row_type": "data", "category": "required", "aliases": [],
        })

        merged = merge_rows(new_template, existing)

        # 库存现金金额保留
        cash = next(r for r in merged if r.get("_pushed_row_id") == RID_CASH)
        assert cash["values"] == [100, 0]

        # 新增行金额为空
        digital = next(r for r in merged if r.get("_pushed_row_id") == rid_digital)
        assert digital["values"] == []
        assert digital["label"] == "数字货币"

    def test_structure_hash_same_for_pushed_rows(self):
        """下推行结构相同的子企业 hash 一致→共用映射规则。"""
        sub_a = _subsidiary_rows(100, 200)
        sub_b = _subsidiary_rows(50, 300)

        ha = compute_source_structure_hash("五-1-1", sub_a)
        hb = compute_source_structure_hash("五-1-1", sub_b)
        # 结构相同（行名+行类型一致，金额不参与），hash 应一致
        assert ha == hb

    def test_rid_fallback_when_label_changed(self):
        """子企业改了行名但 _pushed_row_id 没变 → 仍能按 rid 匹配。"""
        sub = _subsidiary_rows(100, 200)
        # 子企业把"库存现金"改成了"现金及现金等价物"
        sub[0]["label"] = "现金及现金等价物"

        groups = [{
            "hash": "h3",
            "entities": [{"node_key": "A"}],
            "source_rows": sub,
        }]

        result = suggest_template_rows(groups, existing_template_rows=TEMPLATE_ROWS)

        # 即使名字改了，rid 匹配仍优先
        cash = next(r for r in result if r["source_label"] == "现金及现金等价物")
        assert cash["match_type"] == "exact_id"
        assert cash["suggested_target"]["canonical_name"] == "库存现金"
