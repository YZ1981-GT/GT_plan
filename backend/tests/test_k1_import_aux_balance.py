"""K1-2 明细表 ← 辅助余额归集：端点单测（fake session，不触库）.

spec: .kiro/specs/k1-extraction-chain-and-note-alignment/
Requirements 1.1, 1.2, 1.5, 1.8 / Properties 1, 2
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.routers.wp_render_strategies._k1_import_export import (
    _K1_2_DETAIL_ITEM_ID,
    k1_import_aux_balance,
)


def _run(coro):
    return asyncio.run(coro)


class _Rows:
    def __init__(self, rows):
        self._rows = list(rows)

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    """按 SQL 关键字路由（working_paper / active_dataset / tb_aux_balance 归集两跳 /
    related_party_registry / checklist_responses 读写 / report_config 系）。"""

    def __init__(
        self,
        *,
        wp_row=None,
        aux_type_rows=None,
        aux_name_rows=None,
        related_party=None,
        existing_detail_rows=None,
        active_dataset_row=None,
        raise_on_aux=False,
    ):
        self.wp_row = wp_row
        self.aux_type_rows = aux_type_rows or []
        self.aux_name_rows = aux_name_rows or []
        self.related_party = related_party or []
        self.existing_detail_rows = existing_detail_rows
        self.active_dataset_row = active_dataset_row or SimpleNamespace(
            id=uuid4(), status="active"
        )
        self.raise_on_aux = raise_on_aux
        self.upserts: list[tuple[str, str]] = []
        self.committed = False

    async def execute(self, stmt, params=None):
        s = str(stmt)
        p = params or {}
        if "FROM working_paper wp JOIN projects p" in s:
            return _Rows([self.wp_row] if self.wp_row else [])
        if "FROM projects" in s:
            return _Rows([SimpleNamespace(applicable_standard_v2=None)])
        if "report_config" in s:
            return _Rows([])
        if "account_chart" in s:
            return _Rows([])
        if "account_mapping" in s:
            return _Rows([])
        if "ledger_datasets" in s or "dataset" in s.lower() and "aux_type" not in s:
            return _Rows([self.active_dataset_row])
        if self.raise_on_aux and ("aux_type" in s):
            raise RuntimeError("aux boom")
        if "group_by" in s.lower() or ("aux_type" in s.lower() and "count" in s.lower()):
            pass
        if "func.count" in s or "n" in s and "aux_type" in s:
            pass
        # 两跳查询按是否含 aux_name 区分（第二跳按 aux_name 归集）
        if "aux_name" in s and "aux_type ==" not in s:
            return _Rows(self.aux_name_rows)
        if "TbAuxBalance.aux_type" in s or "aux_type" in s:
            return _Rows(self.aux_type_rows)
        if "related_party_registry" in s:
            return _Rows([SimpleNamespace(name=n) for n in self.related_party])
        if "checklist_responses" in s and ("SELECT" in s or "select" in s):
            if self.existing_detail_rows is None:
                return _Rows([])
            return _Rows(
                [SimpleNamespace(
                    conclusion="",
                    remark=json.dumps(self.existing_detail_rows, ensure_ascii=False),
                )]
            )
        return _Rows([])

    async def rollback(self):
        pass

    async def commit(self):
        self.committed = True


@pytest.fixture(autouse=True)
def _stub_active_filter_and_json_helpers(monkeypatch):
    """跳过 `get_active_filter`（涉及真实 ORM 表达式）与
    `load_json_rows`/`upsert_json_rows`（涉及 checklist_responses 具体列拼接），
    直接用内存字典驱动，聚焦端点自身的编排逻辑。"""
    import app.services.four_table.aux_aggregation as agg_mod
    import app.routers.wp_render_strategies._k1_import_export as mod

    async def _fake_active_filter(db, table, project_id, year):
        return True  # sentinel, 未被真实使用（_FakeSession 不解析 WHERE）

    monkeypatch.setattr(agg_mod, "get_active_filter", _fake_active_filter, raising=False)

    async def _fake_resolve_gross(db, project_id):
        return ["1221"]

    monkeypatch.setattr(mod, "_resolve_k1_gross_prefixes", _fake_resolve_gross)

    class _Seg:
        def __init__(self, key):
            self.key = key
            self.label = key

    async def _fake_resolve_segments(db, wp_id):
        return [_Seg("within1"), _Seg("y1to2")]

    monkeypatch.setattr(mod, "_resolve_k1_segments", _fake_resolve_segments)

    store: dict[str, list[dict]] = {}

    async def _fake_load_json_rows(db, wp_id, item_id, field="remark"):
        return list(store.get(item_id, []))

    async def _fake_upsert_json_rows(db, wp_id, item_id, rows_data, field="remark", **kw):
        store[item_id] = list(rows_data)

    monkeypatch.setattr(mod, "load_json_rows", _fake_load_json_rows)
    monkeypatch.setattr(mod, "upsert_json_rows", _fake_upsert_json_rows)
    yield store


def test_wp_not_found_raises_404():
    session = _FakeSession(wp_row=None)
    with pytest.raises(HTTPException) as exc:
        _run(k1_import_aux_balance(wp_id=str(uuid4()), db=session, current_user=None))
    assert exc.value.status_code == 404


def test_no_aux_data_returns_zero_without_writing(_stub_active_filter_and_json_helpers, monkeypatch):
    import app.services.four_table.aux_aggregation as agg_mod

    async def _empty(db, project_id, year, prefixes):
        return [], None, 0

    monkeypatch.setattr(agg_mod, "aggregate_aux_by_name", _empty)
    import app.routers.wp_render_strategies._k1_import_export as mod
    monkeypatch.setattr(mod, "aggregate_aux_by_name", _empty)

    session = _FakeSession(wp_row=SimpleNamespace(project_id=uuid4(), audit_year=2025))
    out = _run(k1_import_aux_balance(wp_id=str(uuid4()), db=session, current_user=None))
    assert out["ok"] is True
    assert out["imported_count"] == 0
    assert out["rows"] == []
    assert "1221" in out["message"]
    assert _stub_active_filter_and_json_helpers == {}  # 未写库


def test_import_writes_rows_with_correct_field_names(monkeypatch, _stub_active_filter_and_json_helpers):
    import app.services.four_table.aux_aggregation as agg_mod
    from app.services.four_table.aux_aggregation import AuxEntry
    import app.routers.wp_render_strategies._k1_import_export as mod

    async def _fake_aggregate(db, project_id, year, prefixes):
        assert prefixes == ["1221"]
        return (
            [AuxEntry("甲公司", 100.0, 20.0, 0.0, 120.0), AuxEntry("乙公司", 0.0, 0.0, 0.0, 50.0)],
            "客户",
            2,
        )

    monkeypatch.setattr(mod, "aggregate_aux_by_name", _fake_aggregate)

    session = _FakeSession(
        wp_row=SimpleNamespace(project_id=uuid4(), audit_year=2025),
        related_party=["甲公司"],
    )
    out = _run(k1_import_aux_balance(wp_id=str(uuid4()), db=session, current_user=None))
    assert out["ok"] is True
    assert out["imported_count"] == 2
    assert out["aux_type"] == "客户"
    rows = out["rows"]
    assert {r["counterparty"] for r in rows} == {"甲公司", "乙公司"}
    for r in rows:
        assert "beginBalance" in r and "endBalance" in r
        assert "openingBalance" not in r and "closingBalance" not in r
    got = next(r for r in rows if r["counterparty"] == "甲公司")
    assert got["relatedParty"] == "是"
    assert got["endBalance"] == 120.0
    stored = _stub_active_filter_and_json_helpers[_K1_2_DETAIL_ITEM_ID]
    assert len(stored) == 2


def test_manual_rows_not_duplicated_on_reimport(monkeypatch, _stub_active_filter_and_json_helpers):
    import app.services.four_table.aux_aggregation as agg_mod
    from app.services.four_table.aux_aggregation import AuxEntry
    import app.routers.wp_render_strategies._k1_import_export as mod

    async def _fake_aggregate(db, project_id, year, prefixes):
        return [AuxEntry("甲公司", 0.0, 0.0, 0.0, 1.0)], "客户", 1

    monkeypatch.setattr(mod, "aggregate_aux_by_name", _fake_aggregate)

    wp_id = str(uuid4())
    _stub_active_filter_and_json_helpers[_K1_2_DETAIL_ITEM_ID] = [
        {"id": "manual-1", "seq": 5, "counterparty": "甲公司", "endBalance": 999.0,
         "nature": "手工分类", "remark": "手工录入"},
    ]
    session = _FakeSession(wp_row=SimpleNamespace(project_id=uuid4(), audit_year=2025))
    out = _run(k1_import_aux_balance(wp_id=wp_id, db=session, current_user=None))
    assert out["imported_count"] == 0
    assert out["total_rows"] == 1
    stored = _stub_active_filter_and_json_helpers[_K1_2_DETAIL_ITEM_ID]
    assert stored[0]["endBalance"] == 999.0  # 手工数据未被覆盖


def test_truncation_flagged_in_message(monkeypatch, _stub_active_filter_and_json_helpers):
    import app.services.four_table.aux_aggregation as agg_mod
    from app.services.four_table.aux_aggregation import AuxEntry
    from app.services.four_table.k1_aux_detail import K1_DETAIL_ROW_LIMIT
    import app.routers.wp_render_strategies._k1_import_export as mod

    entries = [AuxEntry(f"单位{i}", 0.0, 0.0, 0.0, float(i)) for i in range(K1_DETAIL_ROW_LIMIT + 5)]

    async def _fake_aggregate(db, project_id, year, prefixes):
        return entries, "客户", len(entries)

    monkeypatch.setattr(mod, "aggregate_aux_by_name", _fake_aggregate)

    session = _FakeSession(wp_row=SimpleNamespace(project_id=uuid4(), audit_year=2025))
    out = _run(k1_import_aux_balance(wp_id=str(uuid4()), db=session, current_user=None))
    assert out.get("truncated") is True
    assert "截断" in out["message"]
    assert out["total_units"] == K1_DETAIL_ROW_LIMIT + 5
