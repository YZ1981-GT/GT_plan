"""附注导出端点的一致性闸门 — deliverable-writeback-and-online-edit-integrity Phase D / US-4。

直接以函数方式调用 `render_disclosure_notes` 端点处理器，用 mock 隔离 DB / 鉴权 / 渲染管线，
只验**闸门决策**本身：

- 不一致 + 未确认 ⇒ requires_confirmation=True，且**不触发任何 task 变更 / 版本构建**
  （export_or_new_deliverable / render_and_store 一次都不调）；
- 不一致 + 已确认（confirm_inconsistent=True）⇒ 正常构建版本，响应 consistency.confirmed=True；
- 本就一致 ⇒ 正常构建版本，响应 consistency.confirmed=False、两桶空。

端点内部对渲染管线用 `from ... import ...` 局部导入，故在**源模块**上打桩。
"""
from __future__ import annotations

import uuid
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.phase13_schemas import DeliverableExportRequest

PROJECT_ID = uuid.uuid4()
TASK_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
YEAR = 2025


def _consistency(consistent: bool):
    if consistent:
        return {"consistent": True, "never_synced": [], "stale": []}
    return {
        "consistent": False,
        "never_synced": [
            {
                "note_section": "八、1",
                "section_title": "货币资金",
                "wp_codes": ["E1"],
                "wp_ids": {"E1": "wp-e1"},
                "wp_sheet": "E1-审定表",
            }
        ],
        "stale": [{"note_section": "九", "section_title": "应收账款"}],
    }


class _GateHarness:
    """装配一次端点所需的全部 mock，返回 (调用 render_disclosure_notes 的 awaitable, 探针)。"""

    def __init__(self, *, consistent: bool):
        self.consistency = _consistency(consistent)
        self.dsvc = MagicMock()
        # export_or_new_deliverable → (task, created)
        self.task = SimpleNamespace(
            id=TASK_ID, selected_sections=None, template_type=None
        )
        self.dsvc.export_or_new_deliverable = AsyncMock(
            return_value=(self.task, True)
        )
        self.dsvc.capture_snapshot_refs = AsyncMock(return_value={})
        self.store = SimpleNamespace(
            version=SimpleNamespace(version_no=7),
            download_url="http://x/dl",
            platform_persist_failed=False,
            file_path="/storage/disclosure_notes_2025_v7.docx",
        )
        self.dsvc.render_and_store = AsyncMock(return_value=self.store)

    def run(self, body: DeliverableExportRequest):
        import asyncio

        from app.routers import deliverable as mod

        db = AsyncMock()
        # 适配 refresh_rebuild 基线后，导出端点以 NoteWordExporter 路径导出：先查 Project.template_type/report_scope
        # （一致用例会走到）。`await db.execute(...)` 是 async 返回 result，result.one_or_none() 是同步方法
        # ⇒ result 必须是普通 MagicMock（否则 AsyncMock 把 one_or_none 也做成 coroutine，proj_row 不可下标）。
        _proj_result = MagicMock()
        _proj_result.one_or_none.return_value = ("soe", "standalone")
        db.execute = AsyncMock(return_value=_proj_result)
        user = SimpleNamespace(id=USER_ID)

        note_meta = SimpleNamespace(delivery_warnings=[])
        exporter = SimpleNamespace(
            export_with_meta=AsyncMock(return_value=(BytesIO(b"docx"), note_meta))
        )

        with (
            patch.object(mod, "_guard_action", new=AsyncMock()),
            patch.object(mod, "DeliverableService", return_value=self.dsvc),
            patch.object(mod, "_advance_to_editing", new=AsyncMock()),
            patch.object(
                mod, "_note_delivery_warnings", new=AsyncMock(return_value=[])
            ),
            patch(
                "app.services.deliverable_note_consistency.check_note_consistency",
                new=AsyncMock(return_value=self.consistency),
            ),
            patch(
                "app.services.note_word_exporter.NoteWordExporter",
                return_value=exporter,
            ),
            patch(
                "app.services.deliverable_section_state_service."
                "persist_note_export_section_states",
                new=AsyncMock(),
            ),
        ):
            return asyncio.run(
                mod.render_disclosure_notes(
                    PROJECT_ID, body, db=db, current_user=user
                )
            )


def test_inconsistent_unconfirmed_returns_requires_confirmation_no_version():
    """不一致 + 未确认 ⇒ requires_confirmation=True，且绝不构建版本。"""
    h = _GateHarness(consistent=False)
    body = DeliverableExportRequest(year=YEAR, confirm_inconsistent=False)
    resp = h.run(body)

    assert resp.requires_confirmation is True
    assert resp.task_id is None
    assert resp.version_no is None
    assert resp.download_url is None
    # 清单透传给前端弹框
    assert resp.consistency is not None
    assert resp.consistency.confirmed is False
    assert [i.note_section for i in resp.consistency.never_synced] == ["八、1"]
    assert [i.note_section for i in resp.consistency.stale] == ["九"]
    assert resp.consistency.never_synced[0].wp_codes == ["E1"]

    # 🔴 核心：闸门短路发生在任何 task 变更之前 —— 一个版本都不能建
    h.dsvc.export_or_new_deliverable.assert_not_called()
    h.dsvc.render_and_store.assert_not_called()


def test_inconsistent_confirmed_builds_version_with_confirmed_flag():
    """不一致 + 已确认 ⇒ 正常构建版本，consistency.confirmed=True（留痕用户知情导出）。"""
    h = _GateHarness(consistent=False)
    body = DeliverableExportRequest(year=YEAR, confirm_inconsistent=True)
    resp = h.run(body)

    assert resp.requires_confirmation is False
    assert resp.task_id == TASK_ID
    assert resp.version_no == 7
    assert resp.download_url == "http://x/dl"
    assert resp.consistency is not None
    assert resp.consistency.confirmed is True
    # 确认导出仍带上不一致清单（留痕）
    assert [i.note_section for i in resp.consistency.never_synced] == ["八、1"]

    h.dsvc.export_or_new_deliverable.assert_awaited_once()
    h.dsvc.render_and_store.assert_awaited_once()


def test_consistent_builds_version_without_confirmed_flag():
    """本就一致 ⇒ 正常构建版本，consistency.confirmed=False、两桶空。"""
    h = _GateHarness(consistent=True)
    body = DeliverableExportRequest(year=YEAR, confirm_inconsistent=False)
    resp = h.run(body)

    assert resp.requires_confirmation is False
    assert resp.task_id == TASK_ID
    assert resp.version_no == 7
    assert resp.consistency is not None
    assert resp.consistency.confirmed is False
    assert resp.consistency.never_synced == []
    assert resp.consistency.stale == []

    h.dsvc.export_or_new_deliverable.assert_awaited_once()
    h.dsvc.render_and_store.assert_awaited_once()


def test_consistent_even_with_confirm_flag_confirmed_is_false():
    """一致时即便带 confirm_inconsistent=True，confirmed 仍为 False（没有不一致可确认）。"""
    h = _GateHarness(consistent=True)
    body = DeliverableExportRequest(year=YEAR, confirm_inconsistent=True)
    resp = h.run(body)
    assert resp.requires_confirmation is False
    assert resp.consistency.confirmed is False
