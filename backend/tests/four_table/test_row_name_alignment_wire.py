"""名称对齐 wire 编排 `build_alignment_wire` 守卫（Task 8）。

覆盖：
- 固定 wire 字段齐全（Requirement 1.1 / 1.3）
- 已确认且未失效映射 → user_confirmed，has_pending 不因它 +1（Property 5 / Requirement 3.3）
- stale 映射 → unmatched + stale_reason，计入 pending
- unmatched/ambiguous 计入 has_pending

用 monkeypatch 替换 build_candidates（不连真库，测编排）。
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

import app.services.row_name_alignment_wire as wire_mod
from app.services.four_table.row_name_alignment import (
    SOURCE_AUX,
    Candidate,
    TargetIdentity,
    _dimension_key,
)
from app.services.row_name_alignment_wire import RowAlignmentInput, build_alignment_wire
from app.services.row_name_mapping_service import MappingScope

_WIRE_FIELDS = {
    "row_key", "match_state", "candidates", "target_identity", "amount",
    "similarity", "source_kind", "confirmed_by", "confirmed_at",
    "mapping_version", "stale_reason",
}
_DS = str(uuid.uuid4())


def _target(name, code="1221", aux_type="客户", ds=_DS):
    return TargetIdentity(
        source_kind=SOURCE_AUX, account_code=code, aux_type=aux_type,
        aux_name=name, dimension_key=_dimension_key(code, aux_type, name), dataset_id=ds,
    )


def _cand(name, row_label, amount=100.0, **kw):
    from app.services.four_table.row_name_alignment import normalize_name, similarity
    t = _target(name, **kw)
    return Candidate(
        target=t, display_name=name, normalized_name=normalize_name(name),
        amount=Decimal(str(amount)), similarity=similarity(row_label, name),
    )


class _FakeMappingService:
    """替身：返回预置的 saved mappings，不连库。"""

    def __init__(self, saved):
        self._saved = saved

    async def load_active_mappings(self, scope):
        return self._saved


def _scope():
    return MappingScope(project_id=uuid.uuid4(), year=2025, wp_code="K1-1", sheet_code="K1-1")


@pytest.mark.asyncio
async def test_wire_fields_complete_for_unmatched(monkeypatch):
    """零候选 → unmatched；wire 字段齐全。"""
    async def fake_build(*a, **k):
        return []
    monkeypatch.setattr(wire_mod, "build_candidates", fake_build)
    monkeypatch.setattr(wire_mod, "RowNameMappingService", lambda db: _FakeMappingService({}))

    out = await build_alignment_wire(
        None, _scope(),
        [RowAlignmentInput(row_key="r1", row_label="预收销售款", account_prefixes=["2203"])],
        dataset_id=_DS,
    )
    assert out["has_pending"] is True
    assert out["unmatched_count"] == 1
    row = out["rows"][0]
    assert set(row.keys()) == _WIRE_FIELDS
    assert row["match_state"] == "unmatched"
    assert row["amount"] is None


@pytest.mark.asyncio
async def test_wire_auto_matched_carries_amount(monkeypatch):
    """唯一精确候选 → auto_matched，携带金额，不计入 pending。"""
    async def fake_build(*a, **k):
        return [_cand("预收账款甲", "预收账款甲", amount=500.0)]
    monkeypatch.setattr(wire_mod, "build_candidates", fake_build)
    monkeypatch.setattr(wire_mod, "RowNameMappingService", lambda db: _FakeMappingService({}))

    out = await build_alignment_wire(
        None, _scope(),
        [RowAlignmentInput(row_key="r1", row_label="预收账款甲", account_prefixes=["2203"])],
        dataset_id=_DS,
    )
    assert out["has_pending"] is False
    row = out["rows"][0]
    assert row["match_state"] == "auto_matched"
    assert row["amount"] == "500.0"
    assert row["source_kind"] == "auto"


@pytest.mark.asyncio
async def test_wire_user_confirmed_not_pending(monkeypatch):
    """已确认且候选中身份仍在 → user_confirmed，不弹窗（has_pending=false，Property 5）。"""
    from app.services.four_table.row_name_alignment import SavedMapping

    t = _target("应收甲单位")
    saved = {"r1": SavedMapping(row_key="r1", targets=(t,), mapping_version=3,
                                confirmed_by="u1", confirmed_at="2026-01-01T00:00:00")}

    async def fake_build(*a, **k):
        return [_cand("应收甲单位", "应收甲单位", amount=888.0)]
    monkeypatch.setattr(wire_mod, "build_candidates", fake_build)
    monkeypatch.setattr(wire_mod, "RowNameMappingService", lambda db: _FakeMappingService(saved))

    out = await build_alignment_wire(
        None, _scope(),
        [RowAlignmentInput(row_key="r1", row_label="应收甲单位", account_prefixes=["1221"])],
        dataset_id=_DS,
    )
    assert out["has_pending"] is False
    row = out["rows"][0]
    assert row["match_state"] == "user_confirmed"
    assert row["mapping_version"] == 3
    assert row["confirmed_by"] == "u1"
    assert row["amount"] == "888.0"
    # target_identity 来自映射
    assert len(row["target_identity"]) == 1
    assert row["target_identity"][0]["aux_name"] == "应收甲单位"


@pytest.mark.asyncio
async def test_wire_stale_mapping_falls_back_unmatched(monkeypatch):
    """已确认但候选身份变了（dataset 变）→ stale ⇒ unmatched + stale_reason，计入 pending。"""
    from app.services.four_table.row_name_alignment import SavedMapping

    saved_t = _target("应收甲单位", ds="ds-OLD")
    saved = {"r1": SavedMapping(row_key="r1", targets=(saved_t,), mapping_version=2,
                                confirmed_by="u1", confirmed_at="2026-01-01T00:00:00")}

    async def fake_build(*a, **k):
        # 当前 active 是新 dataset → 身份不匹配
        return [_cand("应收甲单位", "应收甲单位", amount=1.0, ds="ds-active")]
    monkeypatch.setattr(wire_mod, "build_candidates", fake_build)
    monkeypatch.setattr(wire_mod, "RowNameMappingService", lambda db: _FakeMappingService(saved))

    out = await build_alignment_wire(
        None, _scope(),
        [RowAlignmentInput(row_key="r1", row_label="应收甲单位", account_prefixes=["1221"])],
        dataset_id="ds-active",
    )
    assert out["has_pending"] is True
    row = out["rows"][0]
    assert row["match_state"] == "unmatched"
    assert row["stale_reason"]
    assert row["amount"] is None
