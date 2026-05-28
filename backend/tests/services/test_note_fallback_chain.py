"""Sprint A.2.5/2.6 — 多源 fallback 链 + provenance 单测.

覆盖：
- resolve_with_fallback (8 cases)
  - v1 单源 binding（向后兼容自动归一化）
  - v2 主源命中 / fallback[0] 命中 / fallback[1] 命中 / 全部失败
  - CI-9: fallback > 3 抛 ValueError
  - CI-10: provenance 字典必含 source 字段
- attach_cell_provenance / get_cell_provenance (3 cases)

Validates: Requirements D3 / D4 / CI-9 / CI-10
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.services.note_fallback_chain import (
    MAX_FALLBACK_DEPTH,
    attach_cell_provenance,
    get_cell_provenance,
    resolve_with_fallback,
)


def _ctx(**overrides):
    base = {
        "project_id": uuid4(),
        "year": 2025,
        "db": None,
        "_tb_cache": {},
        "_wp_cache": {},
        "_prior_notes_cache": {},
    }
    base.update(overrides)
    return base


# ===========================================================================
# resolve_with_fallback (8+ cases)
# ===========================================================================


@pytest.mark.asyncio
async def test_v1_single_source_primary_success():
    """v1 单源 binding（无 primary key）— 自动归一化为 primary."""
    ctx = _ctx()
    ctx["_tb_cache"]["1001"] = {"audited": 999.0, "opening": 0, "unadjusted": 0}
    binding = {
        "source": "trial_balance",
        "field": "audited_amount",
        "account_codes": ["1001"],
    }
    value, prov = await resolve_with_fallback(binding, ctx)
    assert value == 999.0
    assert prov["source"] == "trial_balance"
    assert prov["fallback_used"] is False
    assert prov["fallback_index"] is None


@pytest.mark.asyncio
async def test_v2_primary_success_no_fallback_used():
    """v2 主源命中 → fallback_used=False."""
    ctx = _ctx()
    ctx["_wp_cache"]["h08"] = {
        "wp_code": "h08",
        "cells": {"分类构成!F5": 12345},
    }
    binding = {
        "primary": {
            "source": "wp_data",
            "wp_code": "h08",
            "sheet": "分类构成",
            "extract": "cell",
            "cell_ref": "F5",
        },
        "fallback": [
            {"source": "trial_balance", "account_codes": ["1601"]},
        ],
    }
    value, prov = await resolve_with_fallback(binding, ctx)
    assert value == Decimal("12345")
    assert prov["source"] == "wp_data"
    assert prov["fallback_used"] is False
    assert prov["fallback_index"] is None
    # source_detail 含 wp_code / sheet / cell_ref
    assert prov["source_detail"]["wp_code"] == "h08"
    assert prov["source_detail"]["sheet"] == "分类构成"
    assert prov["source_detail"]["cell_ref"] == "F5"


@pytest.mark.asyncio
async def test_primary_fail_fallback0_success():
    """主源失败 → fallback[0] 命中 → fallback_used=True, index=0."""
    ctx = _ctx()
    # 主源 wp_data 缺数据；fallback trial_balance 有数据
    ctx["_tb_cache"]["1601"] = {"audited": 500.0, "opening": 0, "unadjusted": 0}
    binding = {
        "primary": {
            "source": "wp_data",
            "wp_code": "missing_wp",
            "sheet": "s",
            "extract": "cell",
            "cell_ref": "A1",
        },
        "fallback": [
            {
                "source": "trial_balance",
                "field": "audited_amount",
                "account_codes": ["1601"],
            },
        ],
    }
    value, prov = await resolve_with_fallback(binding, ctx)
    assert value == 500.0
    assert prov["source"] == "trial_balance"
    assert prov["fallback_used"] is True
    assert prov["fallback_index"] == 0
    assert prov["source_detail"]["account_codes"] == ["1601"]


@pytest.mark.asyncio
async def test_primary_fail_fallback0_fail_fallback1_success():
    """主源 + fallback[0] 都失败 → fallback[1] 命中 → index=1."""
    ctx = _ctx()
    binding = {
        "primary": {"source": "wp_data", "wp_code": "missing", "sheet": "s",
                    "extract": "cell", "cell_ref": "A1"},
        "fallback": [
            {
                "source": "trial_balance",
                "field": "audited_amount",
                "account_codes": ["9999"],  # 缓存无此 code → None
            },
            {"source": "manual", "manual_value": 7.5},
        ],
    }
    value, prov = await resolve_with_fallback(binding, ctx)
    assert value == 7.5
    assert prov["source"] == "manual"
    assert prov["fallback_used"] is True
    assert prov["fallback_index"] == 1


@pytest.mark.asyncio
async def test_all_sources_fail_returns_none_with_source_none():
    """全部失败 → (None, source='none')."""
    ctx = _ctx()
    binding = {
        "primary": {"source": "wp_data", "wp_code": "missing", "sheet": "s",
                    "extract": "cell", "cell_ref": "A1"},
        "fallback": [
            {"source": "trial_balance", "account_codes": ["X"],
             "field": "audited_amount"},
            {"source": "manual"},  # 无 manual_value
        ],
    }
    value, prov = await resolve_with_fallback(binding, ctx)
    assert value is None
    assert prov["source"] == "none"
    assert prov["fallback_used"] is True
    assert prov["fallback_index"] is None


@pytest.mark.asyncio
async def test_v1_binding_auto_normalized():
    """v1 单源 binding（无 primary key）→ 自动当 primary 处理."""
    ctx = _ctx()
    binding = {
        "source": "manual",
        "manual_value": "审计师手填",
    }
    value, prov = await resolve_with_fallback(binding, ctx)
    assert value == "审计师手填"
    assert prov["source"] == "manual"
    assert prov["fallback_used"] is False


@pytest.mark.asyncio
async def test_ci9_max_fallback_depth_exceeded():
    """CI-9: fallback 列表 > 3 → ValueError."""
    binding = {
        "primary": {"source": "manual", "manual_value": None},
        "fallback": [
            {"source": "manual"},
            {"source": "manual"},
            {"source": "manual"},
            {"source": "manual"},  # 第 4 项 → 超限
        ],
    }
    with pytest.raises(ValueError, match="CI-9|fallback chain"):
        await resolve_with_fallback(binding, _ctx())


@pytest.mark.asyncio
async def test_ci9_exactly_3_fallback_ok():
    """CI-9 边界：恰好 3 项 fallback → OK 不抛."""
    assert MAX_FALLBACK_DEPTH == 3
    binding = {
        "primary": {"source": "manual", "manual_value": None},
        "fallback": [
            {"source": "manual"},
            {"source": "manual"},
            {"source": "manual", "manual_value": "last"},
        ],
    }
    value, prov = await resolve_with_fallback(binding, _ctx())
    assert value == "last"
    assert prov["fallback_index"] == 2


@pytest.mark.asyncio
async def test_ci10_provenance_always_has_source_field():
    """CI-10: provenance 字典必含 source 字段（无论命中/全失败）."""
    ctx = _ctx()
    ctx["_tb_cache"]["1001"] = {"audited": 1.0, "opening": 0, "unadjusted": 0}

    # 命中场景
    _, prov_hit = await resolve_with_fallback(
        {"source": "trial_balance", "field": "audited_amount",
         "account_codes": ["1001"]},
        ctx,
    )
    assert "source" in prov_hit
    assert prov_hit["source"]

    # 全失败场景
    _, prov_miss = await resolve_with_fallback(
        {"source": "trial_balance", "field": "audited_amount",
         "account_codes": ["NOT_EXIST"]},
        ctx,
    )
    assert "source" in prov_miss
    assert prov_miss["source"] == "none"


@pytest.mark.asyncio
async def test_invalid_binding_type_raises():
    """非 dict binding → ValueError."""
    with pytest.raises(ValueError):
        await resolve_with_fallback(None, _ctx())  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        await resolve_with_fallback({"primary": "not-dict"}, _ctx())


@pytest.mark.asyncio
async def test_empty_value_falls_through():
    """primary 返回空 list → 视为缺失，进入 fallback."""
    ctx = _ctx()
    ctx["_wp_cache"]["empty_wp"] = {
        "wp_code": "empty_wp",
        "cells": {},  # extract=table 会返回 []
    }
    binding = {
        "primary": {
            "source": "wp_data",
            "wp_code": "empty_wp",
            "sheet": "s",
            "extract": "table",
            "label_col": "A",
            "value_cols": {"v": "B"},
        },
        "fallback": [
            {"source": "manual", "manual_value": "fallback hit"},
        ],
    }
    value, prov = await resolve_with_fallback(binding, ctx)
    assert value == "fallback hit"
    assert prov["source"] == "manual"
    assert prov["fallback_used"] is True


# ===========================================================================
# attach_cell_provenance / get_cell_provenance (3+ cases)
# ===========================================================================


def test_attach_to_empty_table_creates_bucket():
    """空 table_data → _cell_provenance 自动创建."""
    td = {"rows": []}
    prov = {"source": "wp_data", "value": 100}
    new_td = attach_cell_provenance(td, "row_3:col_amount_end", prov)

    # 不 mutate 原对象
    assert "_cell_provenance" not in td
    # 新对象含 provenance
    assert "_cell_provenance" in new_td
    assert new_td["_cell_provenance"]["row_3:col_amount_end"]["source"] == "wp_data"


def test_attach_multiple_cells_all_stored():
    """多 cell 写入 → 全部存储."""
    td = {"rows": []}
    td = attach_cell_provenance(td, "row_1:col_a", {"source": "wp_data"})
    td = attach_cell_provenance(td, "row_2:col_b", {"source": "trial_balance"})
    td = attach_cell_provenance(td, "row_3:col_c", {"source": "manual"})

    bucket = td["_cell_provenance"]
    assert len(bucket) == 3
    assert bucket["row_1:col_a"]["source"] == "wp_data"
    assert bucket["row_2:col_b"]["source"] == "trial_balance"
    assert bucket["row_3:col_c"]["source"] == "manual"


def test_get_returns_none_for_missing():
    """get 不存在的 cell → None."""
    assert get_cell_provenance({}, "x") is None
    assert get_cell_provenance({"_cell_provenance": {}}, "x") is None
    td = attach_cell_provenance({}, "row_1:col_a", {"source": "wp_data"})
    assert get_cell_provenance(td, "row_1:col_a") is not None
    assert get_cell_provenance(td, "row_99:col_z") is None


def test_attach_ci10_missing_source_raises():
    """CI-10: provenance 缺 source → ValueError."""
    with pytest.raises(ValueError, match="CI-10|source"):
        attach_cell_provenance({}, "k", {"value": 1})


def test_attach_overwrites_existing_cell_key():
    """同一 cell_key 写两次 → 覆盖."""
    td = attach_cell_provenance({}, "k", {"source": "a", "value": 1})
    td = attach_cell_provenance(td, "k", {"source": "b", "value": 2})
    assert td["_cell_provenance"]["k"]["source"] == "b"
    assert td["_cell_provenance"]["k"]["value"] == 2


def test_attach_validates_inputs():
    """invalid input → 抛 TypeError/ValueError."""
    with pytest.raises(TypeError):
        attach_cell_provenance("not-dict", "k", {"source": "a"})  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        attach_cell_provenance({}, "k", "not-dict")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        attach_cell_provenance({}, "", {"source": "a"})


def test_resolve_with_fallback_provenance_contains_required_audit_fields():
    """provenance 应含完整审计字段：source / value / fetched_at / source_detail / fallback_used."""
    pass  # 由 below sync test 覆盖


@pytest.mark.asyncio
async def test_provenance_has_audit_fields():
    """provenance 含 audit 字段（fetched_at / source_detail / fallback_used / fallback_index）."""
    ctx = _ctx()
    ctx["_tb_cache"]["1001"] = {"audited": 100.0, "opening": 0, "unadjusted": 0}
    _, prov = await resolve_with_fallback(
        {"source": "trial_balance", "field": "audited_amount",
         "account_codes": ["1001"]},
        ctx,
    )
    assert "source" in prov
    assert "value" in prov
    assert "fetched_at" in prov
    assert "source_detail" in prov
    assert "fallback_used" in prov
    assert "fallback_index" in prov
