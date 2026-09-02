# -*- coding: utf-8 -*-
"""把统一内容提交边界替换成记录式替身的测试工具。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 19
Requirements: 2.2（所有 writer 经统一 `ContentMutationService.commit(...)` 提交业务内容）

═══ 为什么需要它 ═══

Task 19 把 `VersionTrailService.rollback_to_snapshot` 等恢复 writer 接到了
`AuthoritativeContentWriter` → `ContentMutationService` 上。那条 lane 是**真**协议：
它要发布内容寻址 artifact、查 `working_paper_sync_entry_state` 是否已有 representation
pointer、跑 `content_revision` 的 CAS、并用 `pg_current_xact_id()` 自证单事务。

用 `AsyncMock` / `MagicMock` 当 session 的既有测试因此必然失败，而且**失败得毫无信息**：
mock 的 `scalar_one()` 返回一个真值 MagicMock，于是「该 entry 已有 representation」这条
判据恒真，报出来的是 `HtmlOnlyEntryHasRepresentationError`（Task 19 实测）。

那些测试的被测对象是**恢复语义**（先删后插、INSERT 参数与快照逐字段一致、回滚会创建
一条 `snapshot_type='rollback'` 记录、越权返回 403）。它们不是、也不该是统一 lane 的
守卫 —— lane 本身由 `workpaper_sync/test_task15_content_mutation*.py`、
`test_task18_html_save_unified_revision*.py` 与
`test_task19_writer_migration.py` 在真库/真实执行下验证。

═══ 这个替身**不**证明什么（防假绿）═══

它把提交边界整段短路，因此使用它的测试**不得**用来断言：

* 「恰一次 business revision」/「同一个事务」—— 需要真库的 `xmin`/`pg_current_xact_id()`；
* 「artifact 先耐久再写 pointer」—— 需要真实 artifact 仓库；
* 「走的是哪条 lane」—— 那是 `test_task19_writer_migration.py` 的 AST/真实执行判据。

替身会把每次调用的关键字参数记进 :attr:`UnifiedCommitCalls.projection`，所以调用点传了
什么仍然可断言 —— 短路的是「提交」，不是「调用发生过」。
"""

from __future__ import annotations

import contextlib
import uuid
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Iterator
from unittest.mock import patch

__all__ = ["UnifiedCommitCalls", "stub_unified_content_commit"]


@dataclass
class UnifiedCommitCalls:
    """替身记录下来的调用（按发生顺序）。"""

    projection: list[dict[str, Any]] = field(default_factory=list)
    bytes_: list[dict[str, Any]] = field(default_factory=list)
    #: `current_revision()` 的固定返回值。测试可在进入上下文前改它来模拟不同基线。
    current_revision: int = 0


@contextlib.contextmanager
def stub_unified_content_commit(
    current_revision: int = 0,
) -> Iterator[UnifiedCommitCalls]:
    """在 `with` 作用域内把 `AuthoritativeContentWriter` 的三个出口换成替身。

    刻意做成**上下文管理器而不是 fixture**：这些文件里有 `@given`（Hypothesis）用例，
    函数作用域 fixture 会触发 `HealthCheck.function_scoped_fixture`，而为了绕开它去
    `suppress_health_check` 会顺手关掉一条真正有用的检查。
    """
    from app.services.workpaper_sync.writer_migration import AuthoritativeContentWriter

    calls = UnifiedCommitCalls(current_revision=current_revision)

    async def _current_revision(self: Any, wp_id: uuid.UUID) -> int:
        return calls.current_revision

    def _receipt(kwargs: dict[str, Any]) -> SimpleNamespace:
        return SimpleNamespace(
            wp_id=kwargs.get("wp_id"),
            entry_id=kwargs.get("entry_id"),
            revision=int(kwargs.get("expected_revision", calls.current_revision)) + 1,
            content_version_id=uuid.uuid4(),
        )

    async def _commit_projection(self: Any, **kwargs: Any) -> SimpleNamespace:
        calls.projection.append(kwargs)
        return _receipt(kwargs)

    async def _commit_bytes(self: Any, **kwargs: Any) -> SimpleNamespace:
        calls.bytes_.append(kwargs)
        return _receipt(kwargs)

    async def _publish(self: Any, receipt: Any) -> dict[str, Any]:
        return {}

    with patch.object(
        AuthoritativeContentWriter, "current_revision", _current_revision
    ), patch.object(
        AuthoritativeContentWriter, "commit_projection", _commit_projection
    ), patch.object(
        AuthoritativeContentWriter, "commit_bytes", _commit_bytes
    ), patch.object(
        AuthoritativeContentWriter, "publish_committed_events", _publish
    ):
        yield calls
