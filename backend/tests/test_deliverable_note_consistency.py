"""附注导出前一致性检查 — deliverable-writeback-and-online-edit-integrity Phase D / US-4。

方向裁定（2026-10-17）：附注唯一权威源是底稿披露表的单项推送，交付中心是只读下游、
不回写附注。导出前比对附注模块当前内容与底稿应推送内容，列出不一致章节让用户确认或先同步。

本文件守护纯服务逻辑（judgement 复用 build_readiness 的 needs_sync / is_stale）：
- 从未同步（needs_sync）⇒ never_synced 桶，带回底稿改所需的 wp_codes/wp_ids/wp_sheet
- 上游变更未刷新（is_stale）⇒ stale 桶
- 全部已同步 ⇒ consistent=True，两桶皆空
- selected_sections 非空 ⇒ 只看选中章节（与导出范围一致）
- build_readiness 抛异常 ⇒ fail-open（consistent=True，不因看板故障阻断已完成编制）

build_readiness 的真实构建依赖多张表，这里**按其契约形状打桩**（形状已由
note_readiness_service 的 docstring + test 锁定），只验一致性判定本身。
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest

from app.services import deliverable_note_consistency as mod
from app.services.deliverable_note_consistency import check_note_consistency

PROJECT_ID = uuid.uuid4()
YEAR = 2025


def _section(
    note_section: str,
    *,
    needs_sync: bool = False,
    is_stale: bool = False,
    section_title: str = "",
    wp_codes: list[str] | None = None,
    wp_ids: dict[str, str] | None = None,
    wp_sheet: str | None = None,
) -> dict[str, Any]:
    """按 build_readiness 的 sections[] 契约造一条。"""
    return {
        "note_section": note_section,
        "section_title": section_title or f"{note_section} 标题",
        "needs_sync": needs_sync,
        "is_stale": is_stale,
        "wp_codes": wp_codes or [],
        "wp_ids": wp_ids or {},
        "wp_sheet": wp_sheet,
    }


def _patch_readiness(monkeypatch, sections: list[dict[str, Any]]) -> None:
    async def _fake_build_readiness(db, project_id, year):  # noqa: ANN001
        if hasattr(db, "log"):
            db.log.append("readiness")
        return {"summary": {}, "sections": sections}

    # check_note_consistency 内部 `from app.services.note_readiness_service import build_readiness`
    monkeypatch.setattr(
        "app.services.note_readiness_service.build_readiness",
        _fake_build_readiness,
    )


class _FakeSavepoint:
    def __init__(self, log: list[str]) -> None:
        self._log = log

    async def rollback(self) -> None:
        self._log.append("rollback")


class _FakeSession:
    """只实现 check_note_consistency 用到的 begin_nested，按顺序记录调用。"""

    def __init__(self) -> None:
        self.log: list[str] = []

    async def begin_nested(self) -> _FakeSavepoint:
        self.log.append("begin_nested")
        return _FakeSavepoint(self.log)


def _run(monkeypatch, sections, **kwargs):
    _patch_readiness(monkeypatch, sections)
    return asyncio.run(
        check_note_consistency(_FakeSession(), PROJECT_ID, YEAR, **kwargs)
    )


# ─── never_synced ────────────────────────────────────────────────────────────


def test_never_synced_section_is_inconsistent_with_backfill_info(monkeypatch):
    """从未从底稿同步的章节 ⇒ never_synced 桶，带「回底稿改」所需的定位信息。"""
    result = _run(
        monkeypatch,
        [
            _section(
                "八、1",
                needs_sync=True,
                section_title="货币资金",
                wp_codes=["E1"],
                wp_ids={"E1": "wp-uuid-e1"},
                wp_sheet="E1-审定表",
            )
        ],
    )
    assert result["consistent"] is False
    assert result["stale"] == []
    assert len(result["never_synced"]) == 1
    item = result["never_synced"][0]
    assert item["note_section"] == "八、1"
    assert item["section_title"] == "货币资金"
    # 回底稿改需要的入口信息必须透传
    assert item["wp_codes"] == ["E1"]
    assert item["wp_ids"] == {"E1": "wp-uuid-e1"}
    assert item["wp_sheet"] == "E1-审定表"


# ─── stale ──────────────────────────────────────────────────────────────────


def test_stale_section_is_inconsistent(monkeypatch):
    """底稿已更新、附注陈旧未刷新 ⇒ stale 桶。"""
    result = _run(
        monkeypatch,
        [_section("九", is_stale=True, section_title="应收账款")],
    )
    assert result["consistent"] is False
    assert result["never_synced"] == []
    assert len(result["stale"]) == 1
    assert result["stale"][0]["note_section"] == "九"
    assert result["stale"][0]["section_title"] == "应收账款"


# ─── all consistent ──────────────────────────────────────────────────────────


def test_all_synced_is_consistent(monkeypatch):
    """全部已同步、无 stale ⇒ consistent=True，两桶皆空。"""
    result = _run(
        monkeypatch,
        [
            _section("八、1", needs_sync=False, is_stale=False),
            _section("九", needs_sync=False, is_stale=False),
        ],
    )
    assert result["consistent"] is True
    assert result["never_synced"] == []
    assert result["stale"] == []


def test_empty_sections_is_consistent(monkeypatch):
    """无任何章节（如附注未生成）⇒ consistent=True（无不一致可言）。"""
    result = _run(monkeypatch, [])
    assert result["consistent"] is True
    assert result["never_synced"] == []
    assert result["stale"] == []


# ─── selected_sections 过滤 ──────────────────────────────────────────────────


def test_selected_sections_filters_scope(monkeypatch):
    """selected_sections 非空 ⇒ 只看选中章节；未选中的不一致章节不计入。"""
    sections = [
        _section("八、1", needs_sync=True),  # 选中且不一致
        _section("九", is_stale=True),  # 未选中 → 不计入
    ]
    result = _run(monkeypatch, sections, selected_sections=["八、1"])
    assert result["consistent"] is False
    assert [i["note_section"] for i in result["never_synced"]] == ["八、1"]
    assert result["stale"] == [], "未选中的 stale 章节不应进入结果"


def test_selected_sections_all_consistent_when_bad_ones_excluded(monkeypatch):
    """选中的章节都一致 ⇒ consistent=True，即便全集里有不一致章节。"""
    sections = [
        _section("八、1", needs_sync=False, is_stale=False),  # 选中且一致
        _section("九", needs_sync=True),  # 未选中（不一致）
    ]
    result = _run(monkeypatch, sections, selected_sections=["八、1"])
    assert result["consistent"] is True
    assert result["never_synced"] == []
    assert result["stale"] == []


# ─── fail-open ────────────────────────────────────────────────────────────────


def test_fail_open_on_readiness_error(monkeypatch):
    """build_readiness 抛异常 ⇒ fail-open：consistent=True，不阻断导出。"""

    async def _boom(db, project_id, year):  # noqa: ANN001
        raise RuntimeError("看板查询炸了")

    monkeypatch.setattr(
        "app.services.note_readiness_service.build_readiness", _boom
    )
    db = _FakeSession()
    result = asyncio.run(check_note_consistency(db, PROJECT_ID, YEAR))
    assert result["consistent"] is True
    assert result["never_synced"] == []
    assert result["stale"] == []
    # 抛错时同样回滚到保存点（PG 上不回滚，调用方的事务就停在 aborted）
    assert db.log == ["begin_nested", "rollback"]


# ─── 反向自检：判定确实消费 needs_sync / is_stale ─────────────────────────────


def test_reverse_selfcheck_judgement_consumes_both_signals(monkeypatch):
    """反向自检：needs_sync 与 is_stale 任一为真都会使 consistent=False。

    若有人把判定改成只看其中一个信号，这条会打红。
    """
    only_needs = _run(monkeypatch, [_section("A", needs_sync=True)])
    only_stale = _run(monkeypatch, [_section("B", is_stale=True)])
    both_clean = _run(monkeypatch, [_section("C")])
    assert only_needs["consistent"] is False
    assert only_stale["consistent"] is False
    assert both_clean["consistent"] is True


def test_service_import_surface():
    """check_note_consistency 必须是 deliverable_note_consistency 的公开 API。"""
    assert hasattr(mod, "check_note_consistency")
    assert "check_note_consistency" in getattr(mod, "__all__", [])


def test_readiness_runs_in_savepoint_that_is_always_rolled_back(monkeypatch):
    """只读看板在保存点内执行，成功时也回滚到保存点。

    build_readiness 内部会吞掉查询失败；PG 上那会让整个事务 aborted，只有回滚到保存点才能恢复。
    去掉回滚的变异让本例打红（PG 层的真实恢复见 test_deliverable_note_consistency_pg.py）。
    """
    _patch_readiness(monkeypatch, [_section("八、1", needs_sync=True)])
    db = _FakeSession()
    result = asyncio.run(check_note_consistency(db, PROJECT_ID, YEAR))
    assert result["consistent"] is False
    assert db.log == ["begin_nested", "readiness", "rollback"]
