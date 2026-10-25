"""P1.2 S 类只读联动 resolver 契约与真实生产函数测试。"""
from __future__ import annotations

import ast
import inspect
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, get_type_hints
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import sqlalchemy as sa

from app.services.auto_data_resolvers import _REGISTRY, resolve_auto_data_source
from app.services.auto_data_resolvers._s_linkage import (
    NEW_S_RESOLVER_SOURCES,
    s14_estimate_related_data,
    s33_5_revenue_cost_check,
    s6_related_party_summary,
)
from app.services.wp_render_schema_service import WpRenderSchemaService


_EXISTING_S_RESOLVER_SOURCES = (
    "s4_nonmonetary_exchange_data",
    "s5_debt_restructuring_data",
    "s6_fund_occupation_data",
    "s8_lease_data",
    "s9_ecommerce_data",
    "s10_environment_data",
    "revenue_audited_for_s20",
    "eps_data_from_tb",
    "s3_policy_change_data",
    "non_recurring_items_from_tb",
    "cycle_audited_amounts",
)
_ALL_S_RESOLVER_SOURCES = _EXISTING_S_RESOLVER_SOURCES + NEW_S_RESOLVER_SOURCES


def _is_select(statement: Any) -> bool:
    """断言 resolver 发出的 ORM/text 语句是 SELECT。"""
    return str(statement).lstrip().upper().startswith("SELECT")


class TestSResolverRegistryContract:
    def test_existing_and_new_s_resolvers_total_fourteen(self):
        registered = set(_REGISTRY)
        assert set(_EXISTING_S_RESOLVER_SOURCES) <= registered
        assert set(NEW_S_RESOLVER_SOURCES) <= registered
        assert len(_EXISTING_S_RESOLVER_SOURCES) == 11
        assert len(set(_ALL_S_RESOLVER_SOURCES)) == 14
        assert len(set(_ALL_S_RESOLVER_SOURCES) & registered) == 14

    def test_all_fourteen_use_async_uniform_signature(self):
        for source in _ALL_S_RESOLVER_SOURCES:
            resolver = _REGISTRY[source]
            assert inspect.iscoroutinefunction(resolver), f"{source} 必须是 async resolver"
            parameters = list(inspect.signature(resolver).parameters.values())
            assert [p.name for p in parameters[:3]] == ["db", "project_id", "year"], source
            kwargs_parameter = parameters[3]
            assert kwargs_parameter.kind is inspect.Parameter.VAR_KEYWORD, source
            assert kwargs_parameter.name == "kwargs", source
            hints = get_type_hints(resolver)
            assert hints.get("return") == dict[str, Any], source

    @pytest.mark.parametrize(
        ("wp_code", "source"),
        [
            ("S6", "s6_related_party_summary"),
            ("S33-5", "s33_5_revenue_cost_check"),
            ("S14", "s14_estimate_related_data"),
        ],
    )
    def test_each_new_resolver_is_referenced_by_loaded_render_schema(self, wp_code, source):
        schema = WpRenderSchemaService().load_schema(wp_code)
        declarations = schema.get("auto_data_source", [])
        assert isinstance(declarations, list)
        assert source in {item.get("source") for item in declarations if isinstance(item, dict)}


@pytest.mark.anyio
async def test_s6_related_party_summary_reads_real_models_without_writes():
    party_result = MagicMock()
    party_result.scalar.return_value = 2
    transaction_result = MagicMock()
    transaction_result.one.return_value = (3, Decimal("100.50"))

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[party_result, transaction_result])

    result = await resolve_auto_data_source(db, uuid4(), 2025, "s6_related_party_summary")

    assert result["party_count"] == 2
    assert result["transaction_count"] == 3
    assert result["transaction_total"] == 100.5
    assert "关联交易" in result["summary"]
    assert all(_is_select(call.args[0]) for call in db.execute.await_args_list)


@pytest.mark.anyio
async def test_s33_5_revenue_cost_check_reuses_d4_and_f5_readers():
    d4_result = {
        "summary": "D4",
        "balances": {"revenue": 1000, "cost": 600, "ar_1122": 10},
        "indicators": {"gross_margin_rate": 0.4},
    }
    f5_result = {
        "summary": "F5",
        "rows": [{"product": "A", "annual": 580}],
    }
    resolver = AsyncMock(side_effect=[d4_result, f5_result])

    import app.services.auto_data_resolvers._s_linkage as linkage

    original = linkage.resolve_auto_data_source
    linkage.resolve_auto_data_source = resolver
    try:
        result = await s33_5_revenue_cost_check(AsyncMock(), uuid4(), 2025)
    finally:
        linkage.resolve_auto_data_source = original

    assert result["revenue"] == 1000.0
    assert result["cost"] == 600.0
    assert result["d4_cost"] == 600.0
    assert result["f5_cost"] == 580.0
    assert result["gross_margin_rate"] == 0.4
    assert result["linked_workpapers"] == ["D4", "F5"]
    assert [call.args[3] for call in resolver.await_args_list] == [
        "d4_analysis_indicators",
        "f5_ledger_monthly_by_product",
    ]


@pytest.mark.anyio
async def test_s14_estimate_related_data_reads_b50_marked_trial_balance_rows(monkeypatch):
    estimate_accounts = [
        {"account": "存货", "is_estimate": "Y", "max_risk": "H"},
        {"account": "应收账款", "is_estimate": "N", "max_risk": "M"},
    ]
    monkeypatch.setattr(
        "app.services.b50_risk_reader.load_b50_accounts",
        AsyncMock(return_value=estimate_accounts),
    )
    monkeypatch.setattr(
        "app.services.dataset_query.get_active_filter",
        AsyncMock(return_value=sa.true()),
    )

    row = SimpleNamespace(
        standard_account_code="1405",
        account_name="存货",
        unadjusted_amount=Decimal("90"),
        aje_adjustment=Decimal("5"),
        rje_adjustment=Decimal("-2"),
        audited_amount=Decimal("93"),
    )
    query_result = MagicMock()
    query_result.fetchall.return_value = [row]
    db = AsyncMock()
    db.execute = AsyncMock(return_value=query_result)

    result = await s14_estimate_related_data(db, uuid4(), 2025)

    assert result["estimate_accounts"] == ["存货"]
    assert result["matched_row_count"] == 1
    assert result["items"] == [
        {
            "standard_account_code": "1405",
            "account_name": "存货",
            "unadjusted_amount": 90.0,
            "aje_adjustment": 5.0,
            "rje_adjustment": -2.0,
            "audited_amount": 93.0,
        }
    ]
    assert result["total_audited"] == 93.0
    assert all(_is_select(call.args[0]) for call in db.execute.await_args_list)


@pytest.mark.anyio
async def test_s6_read_failure_returns_diagnostic_and_rolls_back():
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=RuntimeError("read failed"))

    result = await s6_related_party_summary(db, uuid4(), 2025)

    assert result["_error"] is True
    assert "失败" in result["summary"]
    db.rollback.assert_awaited_once()


def test_new_resolver_module_has_no_write_calls():
    """AST 守卫：新增 resolver 不得调用 ORM/Session 写入 API。"""
    source_path = Path(__file__).resolve().parents[1] / "app" / "services" / "auto_data_resolvers" / "_s_linkage.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    forbidden = {"add", "add_all", "commit", "flush", "delete", "insert", "update"}
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr in forbidden:
            violations.append(f"{node.func.attr}@{node.lineno}")
    assert not violations, f"S linkage resolver 出现写入调用: {violations}"


class TestR71LinkedWorkpapersDeclarations:
    """R7.1: 映射表暴露 S20/S15/S17/S6/S33-5 的 linked_workpapers，并被 resolver 复用。"""

    EXPECTED = {
        "S20": ["D4"],
        "S15": ["D4", "M2"],
        "S17": ["K12", "K13"],
        "S6": ["K1"],
        "S33-5": ["D4", "F5"],
    }

    def _load_mapping(self):
        path = Path(__file__).resolve().parents[1] / "data" / "wp_account_mapping.json"
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return {m["wp_code"]: m for m in data["mappings"] if m.get("wp_code")}

    def test_five_declarations_present_with_exact_targets(self):
        mapping = self._load_mapping()
        for wp_code, links in self.EXPECTED.items():
            entry = mapping.get(wp_code)
            assert entry is not None, f"{wp_code} 缺失于 wp_account_mapping.json"
            assert entry.get("linked_workpapers") == links, (
                f"{wp_code} linked_workpapers 应为 {links}，实际 {entry.get('linked_workpapers')}"
            )

    def test_helper_reads_mapping_as_single_source(self):
        from app.services.auto_data_resolvers._s_linkage import (
            _load_linked_workpapers_index,
            linked_workpapers_for,
        )

        _load_linked_workpapers_index.cache_clear()
        for wp_code, links in self.EXPECTED.items():
            assert linked_workpapers_for(wp_code) == links

    def test_s6_resolver_surfaces_mapping_link_not_self(self):
        """S6 resolver 的 linked_workpapers 复用映射声明（K1），不再自引用 S6。"""
        import ast

        source_path = (
            Path(__file__).resolve().parents[1]
            / "app" / "services" / "auto_data_resolvers" / "_s_linkage.py"
        )
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        # 不得残留硬编码 ["S6"] / ["D4", "F5"] 字面量作为 linked_workpapers 赋值
        literals_from_mapping = source_path.read_text(encoding="utf-8")
        assert 'linked_workpapers_for("S6")' in literals_from_mapping
        assert 'linked_workpapers_for("S33-5")' in literals_from_mapping
        assert '"linked_workpapers": ["S6"]' not in literals_from_mapping
