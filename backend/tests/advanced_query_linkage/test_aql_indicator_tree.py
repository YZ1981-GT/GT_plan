"""指标树按项目形态（advanced-query-linkage-closure 任务 20，ADR-AQL-10 / 16；R5.5、R5.7 叶子列）。

改造前（AQ-11）：单体项目的树上也挂「试算平衡表（tb_summary）」与整组「合并工作底稿」，点开恒 0 行；调整分录叶子叫
「重分类调整(RCL)」；没有辅助核算叶子；叶子不说明能否带条件。现在：单体隐藏合并类叶子、「科目明细」更名「试算平衡表（科目）」，
合并项目保留合并类叶子（tb_summary 更名「合并试算平衡表（工作底稿）」）；叶子列与 ``supports_conditions`` 由注册表生成。

直接调用端点函数（同 ``test_advanced_query_indicators_lazy``），附注上下文替换为固定报表范围，不触达数据库。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.routers import custom_query as rm
from app.services.custom_query import source_registry as sr
from app.services.custom_query.fetchers import disclosure as disclosure_module

USER = SimpleNamespace(id="u-aql-b6", role="admin")


async def _tree(monkeypatch: pytest.MonkeyPatch, report_scope: str, **params) -> tuple[dict, dict]:
    async def _ctx(db, project_id, year, user):
        return disclosure_module.NotesContext(2025, report_scope, None, "v-aql-b6")

    monkeypatch.setattr(disclosure_module, "resolve_notes_context", _ctx)
    response = SimpleNamespace(headers={})
    tree = await rm.get_indicators(**{"project_id": None, "depth": 1, "branch": None, "year": None, "response": response,
                                      "db": None, "current_user": USER, **params})
    return ({node["key"]: node for node in tree} if isinstance(tree, list) and params.get("branch") is None else tree,
            response.headers)


def _keys(node: dict) -> list[str]:
    return [leaf["key"] for leaf in node["children"]]


async def test_standalone_tree_hides_consolidated_leaves(monkeypatch) -> None:
    tree, headers = await _tree(monkeypatch, "standalone")
    assert headers["X-Notes-Version"] == "v-aql-b6"
    assert "worksheet" not in tree, "单体项目不显示合并工作底稿组（恒 0 行）"
    assert _keys(tree["trial_balance"]) == ["tb_detail", "account_balance", "ledger_entries", "aux_balance", "aux_ledger"]
    assert tree["trial_balance"]["children"][0]["label"] == "试算平衡表（科目）"
    assert [(leaf["key"], leaf["label"]) for leaf in tree["adjustment"]["children"]] == [
        ("adj_aje", "审计调整分录(AJE)"), ("adj_rje", "重分类调整分录(RJE)")]


async def test_consolidated_tree_keeps_consolidated_leaves(monkeypatch) -> None:
    tree, _ = await _tree(monkeypatch, "consolidated")
    assert _keys(tree["trial_balance"])[:2] == ["tb_detail", "tb_summary"]
    assert tree["trial_balance"]["children"][1]["label"] == "合并试算平衡表（工作底稿）"
    assert _keys(tree["worksheet"]) == ["ws_info", "ws_elimination", "ws_consol_tb"]


@pytest.mark.parametrize("report_scope", ["standalone", "consolidated"])
async def test_leaf_columns_and_conditions_come_from_the_registry(monkeypatch, report_scope: str) -> None:
    """SQL 源叶子：列 = 注册表显示列、可带条件；JSON 内存源叶子：列为空、不可带条件（R5.7）。"""
    tree, _ = await _tree(monkeypatch, report_scope)
    checked = 0
    for group in tree.values():
        for leaf in group.get("children") or []:
            spec = sr.resolve_source(leaf["key"]).spec
            if spec is None:
                assert (leaf["columns"], leaf["supports_conditions"]) == ([], False), leaf["key"]
            else:
                assert (leaf["columns"], leaf["supports_conditions"]) == (spec.display_keys, True), leaf["key"]
            checked += 1
    assert checked >= 14, "判据空转：叶子数太少"


async def test_seed_tree_leaves_are_json_sources(monkeypatch) -> None:
    """合并项目 / 无项目的附注种子树：叶子列为空、不可带条件；分支加载也带 X-Notes-Version。"""
    branch, headers = await _tree(monkeypatch, "consolidated", branch="disclosure", depth=None)
    leaves = [leaf for group in branch for leaf in group.get("children") or []]
    assert leaves and all((leaf["columns"], leaf["supports_conditions"]) == ([], False) for leaf in leaves)
    assert headers["X-Notes-Version"] == "v-aql-b6"
    assert rm._INDICATORS_SCHEMA_VERSION >= 13
