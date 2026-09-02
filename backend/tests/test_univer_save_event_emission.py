"""univer-save WORKPAPER_SAVED 事件发布契约回归测试。

2026-06-12 首修，2026-06-22 迁移到 orchestrator，Task 16 迁移到耐久 outbox。

原始根因：`save_univer_data` 早期把裸 dict 传给 `event_bus.publish()`，
且包在 `asyncio.create_task(...)` + `try/except: pass` 中→事件从未分发。

修复 v1：改用真实 EventPayload。
修复 v2：统一由 WorkpaperSaveOrchestrator.after_save 负责事件发布，
save_univer_data 只调 orchestrator，不再内联 event_bus。
修复 v3（spec workpaper-html-onlyoffice-bidirectional-writeback-closure Task 16，
Requirement 13.1/13.4）：after_save **不再在事务内发布**，而是同事务写一条耐久
outbox 行；发布由调用方在 commit 之后调 `publish_pending` 完成，失败自动落 failed
由 `outbox_replay_worker` 重放。原来的"发布失败记 warning"判据因此翻面 —— warning
本身就是要被消灭的 best-effort 降级。

本测试验证：
1. save_univer_data 仍然经 orchestrator 走统一后处理（不内联 event_bus）
2. orchestrator 把事件写进耐久 outbox，且事务内不发布
3. orchestrator 不再有把副作用降级成 warning 的 except 分支
4. save_univer_data 在 commit 之后发布
"""
from __future__ import annotations

import ast
import inspect

from app.routers import wp_editor_router
from app.services import workpaper_save_orchestrator


def _save_univer_source() -> str:
    return inspect.getsource(wp_editor_router.save_univer_data)


def _orchestrator_source() -> str:
    return inspect.getsource(workpaper_save_orchestrator.WorkpaperSaveOrchestrator.after_save)


def _call_leaves(source: str) -> set[str]:
    """从源码 AST 取出所有被调用符号的叶子名（去掉接收者）。"""
    tree = ast.parse(inspect.cleandoc(source.replace("\n    ", "\n")))
    leaves: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                leaves.add(func.attr)
            elif isinstance(func, ast.Name):
                leaves.add(func.id)
    return leaves


def test_orchestrator_enqueues_a_durable_event_instead_of_publishing_inline():
    """事件必须进耐久 outbox，且事务内一次 publish 都没有。

    **Validates: Requirements 13.1**
    """
    src = _orchestrator_source()
    leaves = _call_leaves(src)
    assert "enqueue" in leaves, "after_save 必须调 DurableEventOutboxService.enqueue"
    assert "EventType.WORKPAPER_SAVED" in src, "事件类型仍是 WORKPAPER_SAVED"
    assert "publish" not in leaves and "publish_immediate" not in leaves, (
        "after_save 事务内不许发布：回滚后会留下幽灵事件（Property 52）"
    )


def test_publish_derives_year():
    """orchestrator 的 extra 中可携带 year；save_univer_data 负责推导 year 传入 extra。"""
    src = _save_univer_source()
    # save_univer_data 仍需推导 year（传给 orchestrator.after_save extra）
    assert "saved_year" in src, "save_univer_data 应推导 year 传入 orchestrator"
    assert "audit_period_end" in src, "year 应从 Project.audit_period_end 推导"


def test_side_effects_are_no_longer_degraded_to_a_warning():
    """after_save 内不得再有把副作用降级成 warning 的 except 分支。

    **Validates: Requirements 13.4**

    耐久性现在由 outbox 行提供（失败 → pending/failed/DLQ），不再由 warning "兜底"。
    """
    src = _orchestrator_source()
    assert "event publish failed" not in src, (
        "这条 warning 是被 Task 16 消灭的 best-effort 降级，不该再出现"
    )
    assert "audit log failed" not in src

    tree = ast.parse(inspect.cleandoc(src.replace("\n    ", "\n")))
    handlers = [node for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler)]
    assert handlers == [], f"after_save 体内不该有 except，行号 {[h.lineno for h in handlers]}"


def test_save_univer_uses_orchestrator_and_publishes_after_commit():
    """save_univer_data 必须调 orchestrator.after_save，并在 commit 之后发布。

    **Validates: Requirements 13.1**
    """
    src = _save_univer_source()
    assert "save_orchestrator.after_save" in src, (
        "save_univer_data 必须调用 orchestrator.after_save"
    )
    assert 'trigger="univer_save"' in src, (
        "trigger 参数必须为 'univer_save'"
    )
    # 提交顺序判据（行号次序，不是"出现过"）：publish_pending 必须晚于 db.commit()。
    lines = src.splitlines()
    commit_line = next(i for i, line in enumerate(lines) if "await db.commit()" in line)
    publish_line = next(i for i, line in enumerate(lines) if "publish_pending(" in line)
    assert publish_line > commit_line, (
        f"publish_pending(行 {publish_line}) 必须在 db.commit()(行 {commit_line}) 之后"
    )
