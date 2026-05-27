"""Sprint 4 Task 4.2 — linkage_graph_builder._from_note_referenced_accounts 单测.

Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 4 Task 4.2
Reqs:   R2.2（NOTE→TB 双向边自动生成）

策略：
- 用纯函数测 _collect_account_codes_from_binding（静态 helper，无需 DB）
- 用 mock async session + monkeypatch loader 测 _from_note_referenced_accounts
- 用相对断言（"较 baseline 增加 ≥ N"）替代硬编码 ≥ 200 节点
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.linkage_graph_builder import LinkageGraphBuilder


# ---------------------------------------------------------------------------
# 1. 静态 helper：_collect_account_codes_from_binding
# ---------------------------------------------------------------------------


def test_collect_account_codes_handles_none():
    assert LinkageGraphBuilder._collect_account_codes_from_binding(None) == set()


def test_collect_account_codes_handles_empty():
    assert LinkageGraphBuilder._collect_account_codes_from_binding({}) == set()


def test_collect_account_codes_handles_no_tables():
    assert LinkageGraphBuilder._collect_account_codes_from_binding(
        {"section_number": "X", "wp_code": "F1"}
    ) == set()


def test_collect_account_codes_handles_non_list_tables():
    assert LinkageGraphBuilder._collect_account_codes_from_binding(
        {"tables": "not a list"}
    ) == set()


def test_collect_account_codes_extracts_from_single_cell():
    binding = _make_binding(
        [
            {
                "row1": {
                    "binding": {
                        "col1": {"account_codes": ["1001", "1002"]},
                    }
                }
            }
        ]
    )
    codes = LinkageGraphBuilder._collect_account_codes_from_binding(binding)
    assert codes == {"1001", "1002"}


def test_collect_account_codes_unions_multi_tables():
    binding = _make_binding(
        [
            {
                "row1": {"binding": {"col1": {"account_codes": ["1001"]}}},
                "row2": {"binding": {"col1": {"account_codes": ["1002"]}}},
            },
            {
                "row3": {"binding": {"col1": {"account_codes": ["1001", "1003"]}}},
            },
        ]
    )
    codes = LinkageGraphBuilder._collect_account_codes_from_binding(binding)
    assert codes == {"1001", "1002", "1003"}


def test_collect_account_codes_skips_malformed_cells():
    """非 dict / 非 list / 非 str 元素不抛错."""
    binding = _make_binding(
        [
            {
                "row1": "not a dict",
                "row2": {"binding": "not a dict"},
                "row3": {"binding": {"col1": "not a dict"}},
                "row4": {"binding": {"col1": {"account_codes": "not a list"}}},
                "row5": {"binding": {"col1": {"account_codes": [None, 123, "1001"]}}},
            }
        ]
    )
    codes = LinkageGraphBuilder._collect_account_codes_from_binding(binding)
    assert codes == {"1001"}


def _make_binding(tables_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """生成符合 binding json schema 的 dict."""
    return {
        "section_number": "test",
        "wp_code": "X1",
        "tables": [{"rows": rows} for rows in tables_rows],
    }


# ---------------------------------------------------------------------------
# 2. _from_note_referenced_accounts 集成（async mock DB + monkeypatch loader）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_from_note_referenced_accounts_no_db_returns_silently():
    """无 DB 时不抛错，节点 / 边都不增加."""
    builder = LinkageGraphBuilder(db=None)
    await builder._from_note_referenced_accounts()
    assert builder._nodes == {}
    assert builder._edges == []


@pytest.mark.asyncio
async def test_from_note_referenced_accounts_empty_bindings_index(monkeypatch):
    """binding 索引为空时安全跳过（不抛错，不增节点）."""
    builder = LinkageGraphBuilder(db=AsyncMock())

    monkeypatch.setattr(
        "app.services.note_template_bindings_loader._ensure_loaded",
        lambda: {},
    )
    await builder._from_note_referenced_accounts()
    assert builder._nodes == {}


@pytest.mark.asyncio
async def test_from_note_referenced_accounts_creates_bidirectional_edges(monkeypatch):
    """单 note 多 account_codes 生成双向边 NOTE↔TB."""
    fake_db = _fake_db_with_notes([("五、1 货币资金", "货币资金")])
    builder = LinkageGraphBuilder(db=fake_db)

    fake_bindings = {
        "五、1 货币资金": _make_binding(
            [{"row1": {"binding": {"col1": {"account_codes": ["1001", "1002"]}}}}]
        )
    }
    monkeypatch.setattr(
        "app.services.note_template_bindings_loader._ensure_loaded",
        lambda: fake_bindings,
    )

    await builder._from_note_referenced_accounts()

    # NOTE 节点 + 2 TB 节点
    note_uri = "NOTE:五、1 货币资金::"
    assert note_uri in builder._nodes
    assert "TB:1001::" in builder._nodes
    assert "TB:1002::" in builder._nodes
    assert builder._nodes[note_uri]["module"] == "NOTE"
    assert builder._nodes["TB:1001::"]["module"] == "TB"

    # 双向边：每 account_code 2 条（NOTE→TB + TB→NOTE）
    assert len(builder._edges) == 4
    edge_pairs = {(e["source"], e["target"]) for e in builder._edges}
    assert (note_uri, "TB:1001::") in edge_pairs
    assert ("TB:1001::", note_uri) in edge_pairs
    assert (note_uri, "TB:1002::") in edge_pairs
    assert ("TB:1002::", note_uri) in edge_pairs


@pytest.mark.asyncio
async def test_from_note_referenced_accounts_silently_skips_missing_binding(monkeypatch):
    """note 在 binding 索引中找不到对应 key 时不抛错（仍创建 NOTE 节点但无 TB 边）."""
    fake_db = _fake_db_with_notes([("八、X 自定义章节", "X")])
    builder = LinkageGraphBuilder(db=fake_db)

    monkeypatch.setattr(
        "app.services.note_template_bindings_loader._ensure_loaded",
        lambda: {"五、1 货币资金": _make_binding([])},  # 不含目标章节
    )
    await builder._from_note_referenced_accounts()

    # NOTE 节点仍创建（保持 BFS 入口存在），但无 TB 边
    assert "NOTE:八、X 自定义章节::" in builder._nodes
    assert builder._edges == []


@pytest.mark.asyncio
async def test_from_note_referenced_accounts_adds_node_increment(monkeypatch):
    """相对断言：调用前 baseline → 调用后节点至少多增加 N（避免硬编码 200）."""
    notes = [(f"五、{i} 章节{i}", f"章节{i}") for i in range(20)]
    fake_db = _fake_db_with_notes(notes)
    builder = LinkageGraphBuilder(db=fake_db)

    fake_bindings = {
        sec: _make_binding(
            [{"row1": {"binding": {"col1": {"account_codes": [f"100{i}"]}}}}]
        )
        for i, (sec, _) in enumerate(notes)
    }
    monkeypatch.setattr(
        "app.services.note_template_bindings_loader._ensure_loaded",
        lambda: fake_bindings,
    )

    baseline_nodes = len(builder._nodes)
    baseline_edges = len(builder._edges)
    await builder._from_note_referenced_accounts()

    # 至少增加：20 NOTE + 20 TB 节点 + 40 边（双向）
    assert len(builder._nodes) - baseline_nodes >= 40, (
        f"NOTE+TB 节点增量不足：从 {baseline_nodes} 到 {len(builder._nodes)}"
    )
    assert len(builder._edges) - baseline_edges >= 40, (
        f"双向边增量不足：从 {baseline_edges} 到 {len(builder._edges)}"
    )


@pytest.mark.asyncio
async def test_from_note_referenced_accounts_handles_db_error(monkeypatch, caplog):
    """DB 查询抛错时安全 rollback，不影响调用方."""
    fake_db = AsyncMock()
    fake_db.execute = AsyncMock(side_effect=Exception("connection lost"))
    fake_db.rollback = AsyncMock()

    monkeypatch.setattr(
        "app.services.note_template_bindings_loader._ensure_loaded",
        lambda: {"X": _make_binding([])},
    )

    builder = LinkageGraphBuilder(db=fake_db)
    await builder._from_note_referenced_accounts()

    # 不抛错；rollback 被调用
    fake_db.rollback.assert_awaited()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _fake_db_with_notes(notes: list[tuple[str, str]]):
    """构造 mock async session：execute(SELECT note_section ...) 返回指定行."""
    fake_db = AsyncMock()
    fake_result = MagicMock()
    fake_result.fetchall = MagicMock(return_value=notes)
    fake_db.execute = AsyncMock(return_value=fake_result)
    fake_db.rollback = AsyncMock()
    return fake_db
