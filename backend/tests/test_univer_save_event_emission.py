"""univer-save WORKPAPER_SAVED 事件发布契约回归测试（2026-06-12 修复，2026-06-22 迁移到 orchestrator）。

原始根因：`save_univer_data` 早期把裸 dict 传给 `event_bus.publish()`，
且包在 `asyncio.create_task(...)` + `try/except: pass` 中→事件从未分发。

修复 v1：改用真实 EventPayload。
修复 v2（本次）：统一由 WorkpaperSaveOrchestrator.after_save 负责事件发布，
save_univer_data 只调 orchestrator，不再内联 event_bus。

本测试验证：
1. save_univer_data 通过 orchestrator 发布事件
2. orchestrator 内部正确构建 EventPayload + 推导 year
3. orchestrator 发布失败有 warning 记录（非静默）
"""
from __future__ import annotations

import inspect

from app.routers import wp_editor_router
from app.services import workpaper_save_orchestrator


def _save_univer_source() -> str:
    return inspect.getsource(wp_editor_router.save_univer_data)


def _orchestrator_source() -> str:
    return inspect.getsource(workpaper_save_orchestrator.WorkpaperSaveOrchestrator.after_save)


def test_publish_uses_event_payload_not_dict():
    """事件发布必须构建 EventPayload，禁止裸 dict（由 orchestrator 保证）。"""
    src = _orchestrator_source()
    # orchestrator 必须导入并构建 EventPayload
    assert "EventPayload(" in src, "orchestrator 必须用 EventPayload 构建事件"
    assert "EventType.WORKPAPER_SAVED" in src


def test_publish_derives_year():
    """orchestrator 的 extra 中可携带 year；save_univer_data 负责推导 year 传入 extra。"""
    src = _save_univer_source()
    # save_univer_data 仍需推导 year（传给 orchestrator.after_save extra）
    assert "saved_year" in src, "save_univer_data 应推导 year 传入 orchestrator"
    assert "audit_period_end" in src, "year 应从 Project.audit_period_end 推导"


def test_publish_failure_is_logged_not_silently_passed():
    """发布失败必须记录日志，不再 except: pass 静默吞掉（由 orchestrator 保证）。"""
    src = _orchestrator_source()
    # orchestrator 内 except 分支必须 warning 记录
    assert "event publish failed" in src, (
        "orchestrator 发布失败必须记录 warning"
    )


def test_save_univer_uses_orchestrator():
    """save_univer_data 必须调用 orchestrator.after_save。"""
    src = _save_univer_source()
    assert "save_orchestrator.after_save" in src, (
        "save_univer_data 必须调用 orchestrator.after_save"
    )
    assert 'trigger="univer_save"' in src, (
        "trigger 参数必须为 'univer_save'"
    )
