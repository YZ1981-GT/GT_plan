"""调整分录明细科目码 detail_account_code —— characterization + 属性/契约测试。

spec: adjustment-detail-account-code

覆盖正确性属性：
- P1  列可空默认 NULL（schema 默认 None）
- P2  一级归一逻辑保留（源码契约：import 仍归一 std_code，不因明细码改变）
- P3  明细码保留规则（candidate≠std → 保留）
- P4  明细=一级时不冗余（candidate==std 或空 → None）
- P5  校验只认一级（源码契约：_validate_account_codes 仅校验 standard_account_code）
- P7  recalc 不读明细码（源码契约：调整聚合 group_by adjustments.account_code，不引用 detail_account_code）
- P8  序列化含字段（AdjustmentEntryResponse 含 detail_account_code）
- P11 迁移幂等（V127 IF NOT EXISTS / R127 IF EXISTS DROP）

纯逻辑/源码断言，不依赖 DB，快速可靠。DB 端到端由零回归门（test_adjustments/test_trial_balance 全绿）+ HTTP round-trip 覆盖。
"""
from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.audit_platform_schemas import (
    AdjustmentLineItem,
    AdjustmentEntryResponse,
)

BACKEND = Path(__file__).resolve().parents[1]


# ─────────────────────────────────────────────────────────────────────────────
# P1 / P8 — schema：可选字段、默认 NULL、序列化含字段
# ─────────────────────────────────────────────────────────────────────────────

def test_line_item_detail_code_optional_default_none():
    """P1：不提供 detail_account_code → 默认 None（可空）。"""
    li = AdjustmentLineItem(standard_account_code="1122", debit_amount=Decimal("100"))
    assert li.detail_account_code is None


def test_line_item_detail_code_accepts_value():
    """P3 语义：提供明细码被接受并保留。"""
    li = AdjustmentLineItem(
        standard_account_code="1122",
        detail_account_code="112201",
        credit_amount=Decimal("100"),
    )
    assert li.standard_account_code == "1122"
    assert li.detail_account_code == "112201"


def test_entry_response_serializes_detail_code():
    """P8：分录组响应明细行含 detail_account_code；NULL→null。"""
    r1 = AdjustmentEntryResponse(
        line_no=1, standard_account_code="1122", detail_account_code="112201",
    )
    r2 = AdjustmentEntryResponse(line_no=2, standard_account_code="6602")
    d1 = r1.model_dump()
    d2 = r2.model_dump()
    assert "detail_account_code" in d1 and d1["detail_account_code"] == "112201"
    assert "detail_account_code" in d2 and d2["detail_account_code"] is None


# ─────────────────────────────────────────────────────────────────────────────
# P3 / P4 — 明细码判定规则（与 _import_adjustments 内联逻辑同源，可测化）
# ─────────────────────────────────────────────────────────────────────────────

def _decide_detail_code(detail_candidate: str | None, std_code: str) -> str | None:
    """复刻 _import_adjustments 的判定：明细码非空且 ≠ 一级码时保留，否则 None。"""
    detail_candidate = (detail_candidate or "")
    return detail_candidate if (detail_candidate and detail_candidate != std_code) else None


@pytest.mark.parametrize("candidate,std,expected", [
    ("112201", "1122", "112201"),   # P3 明细≠一级 → 保留
    ("1122", "1122", None),         # P4 明细==一级 → 不冗余
    ("", "1122", None),             # 空 → None
    (None, "1122", None),           # None → None
    ("100101", "1001", "100101"),  # 三级明细 → 保留
])
def test_detail_code_decision(candidate, std, expected):
    assert _decide_detail_code(candidate, std) == expected


# ─────────────────────────────────────────────────────────────────────────────
# 源码契约断言（P2 / P5 / P7 / P11） —— 锁定零影响与关键行为不漂移
# ─────────────────────────────────────────────────────────────────────────────

def _read(rel: str) -> str:
    return (BACKEND / rel).read_text(encoding="utf-8")


def test_p7_recalc_does_not_read_detail_account_code():
    """P7：recalc 调整聚合按 adjustments 头表 account_code，且全文不引用 detail_account_code。"""
    src = _read("app/services/trial_balance_service.py")
    assert "detail_account_code" not in src, "recalc 不应引用 detail_account_code（零影响红线）"
    assert "group_by(adj.c.account_code" in src, "调整聚合应按 adjustments.account_code（一级）"


def test_p5_validate_only_standard_code():
    """P5：科目校验仍只针对 standard_account_code。"""
    src = _read("app/services/adjustment_service.py")
    assert "[li.standard_account_code for li in data.line_items]" in src


def test_p2_import_keeps_level1_normalization_and_persists_detail():
    """P2/P3：导入仍归一 std_code，且把明细码写入 line_item detail_account_code。"""
    src = _read("app/routers/import_templates.py")
    assert "_normalize_to_level1" in src, "一级归一逻辑保留"
    assert "detail_code" in src and "detail_account_code=ln.get(\"detail_code\")" in src


def test_create_update_persist_detail_code():
    """create_entry / update_entry 均持久化 detail_account_code。"""
    src = _read("app/services/adjustment_service.py")
    assert src.count("detail_account_code=li.detail_account_code") == 2


def test_orm_has_detail_account_code_nullable():
    """ORM AdjustmentEntry 声明可空 detail_account_code。"""
    src = _read("app/models/audit_platform_models.py")
    assert re.search(
        r"detail_account_code:\s*Mapped\[str\s*\|\s*None\]\s*=\s*mapped_column\(String,\s*nullable=True\)",
        src,
    )


def test_p11_migration_idempotent():
    """P11：V127 用 IF NOT EXISTS 幂等加列；R127 用 IF EXISTS 幂等删列。"""
    v = _read("migrations/V127__add_adjustment_entry_detail_account_code.sql")
    r = _read("migrations/R127__rollback_add_adjustment_entry_detail_account_code.sql")
    assert "IF NOT EXISTS" in v and "ADD COLUMN detail_account_code" in v
    assert "adjustment_entries" in v
    assert "IF EXISTS" in r and "DROP COLUMN detail_account_code" in r
