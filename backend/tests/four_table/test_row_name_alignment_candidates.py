"""build_candidates 守卫（复盘 #2 跨源去重 + #5 fail-open）。

build_candidates 依赖两个 DB 取数源（aggregate_aux_by_name / fetch_tb_subtree），
用 monkeypatch 注入，不连库。

spec: formula-row-name-alignment-confirmation（复盘修复）
"""
from __future__ import annotations

import uuid

import pytest

import app.services.four_table.row_name_alignment as mod
from app.services.four_table.aux_aggregation import AuxEntry
from app.services.four_table.leaf_aggregation import LeafRow
from app.services.four_table.row_name_alignment import (
    CandidateSourceError,
    build_candidates,
)


def _patch_sources(monkeypatch, *, aux=None, aux_type="客户", leaves=None,
                   aux_exc=None, leaf_exc=None):
    async def fake_aux(db, pid, year, prefixes):
        if aux_exc:
            raise aux_exc
        return (aux or [], aux_type, len(aux or []))

    async def fake_subtree(db, pid, year, prefixes):
        if leaf_exc:
            raise leaf_exc
        return leaves or []

    monkeypatch.setattr(mod, "aggregate_aux_by_name", fake_aux)
    # fetch_tb_subtree 在函数内部 from .tb_query import，patch 该模块属性
    import app.services.four_table.tb_query as tbq
    monkeypatch.setattr(tbq, "fetch_tb_subtree", fake_subtree)


# ── #2 跨源去重 ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cross_source_dedup_by_normalized_name(monkeypatch):
    """同一明细的 aux 名与 account 科目名（归一后相同）只出一条候选，防双算。"""
    aux = [AuxEntry(aux_name="重庆医药集团", opening=0, debit=0, credit=0, closing=100.0)]
    # account 侧叶子科目名归一后与 aux 相同（都剥「集团」不剥；此处用完全同名）
    leaves = [LeafRow(account_code="1221.01", account_name="重庆医药集团", closing=100.0)]
    _patch_sources(monkeypatch, aux=aux, leaves=leaves)

    cands = await build_candidates(None, uuid.uuid4(), 2025, ["1221"], "重庆医药集团")
    # 同归一名只保留 aux 侧一条（account 侧被跳过）
    names = [c.display_name for c in cands]
    assert names.count("重庆医药集团") == 1
    assert cands[0].target.source_kind == mod.SOURCE_AUX


@pytest.mark.asyncio
async def test_distinct_names_both_kept(monkeypatch):
    """不同名的 aux / account 候选都保留。"""
    aux = [AuxEntry(aux_name="客户甲", opening=0, debit=0, credit=0, closing=100.0)]
    leaves = [LeafRow(account_code="1221.01", account_name="科目乙", closing=50.0)]
    _patch_sources(monkeypatch, aux=aux, leaves=leaves)

    cands = await build_candidates(None, uuid.uuid4(), 2025, ["1221"], "任意")
    names = {c.display_name for c in cands}
    assert names == {"客户甲", "科目乙"}


# ── #5 fail-open 区分真空 vs 错误 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_sources_return_empty_not_error(monkeypatch):
    """两源都真空 → 返回 []（正常空结果，不抛）。"""
    _patch_sources(monkeypatch, aux=[], leaves=[])
    cands = await build_candidates(None, uuid.uuid4(), 2025, ["1221"], "行名")
    assert cands == []


@pytest.mark.asyncio
async def test_source_error_raises_not_swallowed(monkeypatch):
    """取数源异常 → 抛 CandidateSourceError（不再吞成空列表掩盖接线错误）。"""
    _patch_sources(monkeypatch, aux_exc=RuntimeError("db boom"))
    with pytest.raises(CandidateSourceError):
        await build_candidates(None, uuid.uuid4(), 2025, ["1221"], "行名")


@pytest.mark.asyncio
async def test_no_prefixes_returns_empty(monkeypatch):
    _patch_sources(monkeypatch, aux=[], leaves=[])
    assert await build_candidates(None, uuid.uuid4(), 2025, [], "行名") == []
