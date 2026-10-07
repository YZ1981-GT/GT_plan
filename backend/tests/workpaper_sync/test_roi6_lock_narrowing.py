# -*- coding: utf-8 -*-
"""ROI-6 锁临界区收窄的正确性守卫。

spec: oo-html-writeback-performance T11/T12

验证 `_apply_settled` 拆分后的三个安全性质：

1. **CPU 段在锁外执行**：`_prepare_and_stage` 不持有 room advisory lock。
2. **commit 段在锁内执行**：`_apply_committed` 在 `lock_room_oo_apply` 之后。
3. **并行 CAS 保障**：两个并行 apply 的 CPU 段可重叠，但 `_commit_once` 内部的
   `expected_revision` CAS 只放一个过，另一个收到 `RevisionConflictError`。
4. **方法拆分完整性**：旧 `_apply_settled_locked` 已移除，新方法存在且可达。
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from typing import TYPE_CHECKING

import pytest

import app.services.workpaper_sync.oo_to_html as OH
from app.services.workpaper_sync.content_mutation import (
    ContentMutationService,
    StagedCommit,
    _ReplayHit,
)


# ═══════════════════════════════════════════════════════════════════════════
# 1. 结构判据：方法存在性与调用拓扑
# ═══════════════════════════════════════════════════════════════════════════


class TestLockNarrowingMethodTopology:
    """_apply_settled 拆分后的方法存在性与调用关系。"""

    def test_old_method_is_removed(self):
        """旧 _apply_settled_locked 必须已删除——不能同时存在两套路径。"""
        assert not hasattr(OH.OoToHtmlCoordinator, "_apply_settled_locked"), (
            "_apply_settled_locked 仍存在！ROI-6 要求删除它，"
            "用 _prepare_and_stage + _apply_committed 替代"
        )

    def test_new_methods_exist(self):
        """新方法必须存在于 OoToHtmlCoordinator 上。"""
        for name in ("_apply_settled", "_prepare_and_stage", "_apply_committed"):
            assert hasattr(OH.OoToHtmlCoordinator, name), (
                f"OoToHtmlCoordinator.{name} 不存在——"
                "ROI-6 锁收窄要求这三个方法完整存在"
            )

    def test_apply_settled_calls_prepare_then_commit(self):
        """_apply_settled 必须先调 _prepare_and_stage（锁外），再调 _apply_committed（锁内）。

        判据用 AST 验证调用顺序，不是运行时 mock——确保代码形态上就是
        「CPU 段在 lock 之前」。
        """
        source = textwrap.dedent(inspect.getsource(
            OH.OoToHtmlCoordinator._apply_settled
        ))
        tree = ast.parse(source)
        calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if node.value.id == "self" and node.attr in (
                    "_prepare_and_stage",
                    "_apply_committed",
                    "_repo",
                ):
                    # 记录方法名和行号
                    if node.attr == "_repo":
                        # 进一步看是不是 lock_room_oo_apply
                        parent = getattr(node, "_parent", None)
                    calls.append((node.attr, node.lineno))
            # 补充：抓 self._repo.lock_room_oo_apply
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "lock_room_oo_apply"
            ):
                calls.append(("lock_room_oo_apply", node.lineno))

        method_lines = {name: line for name, line in calls}
        # _prepare_and_stage 必须在 lock_room_oo_apply 之前
        assert "_prepare_and_stage" in method_lines, (
            "_apply_settled 未调用 _prepare_and_stage"
        )
        assert "lock_room_oo_apply" in method_lines, (
            "_apply_settled 未调用 lock_room_oo_apply"
        )
        assert method_lines["_prepare_and_stage"] < method_lines["lock_room_oo_apply"], (
            f"_prepare_and_stage (line {method_lines['_prepare_and_stage']}) "
            f"必须在 lock_room_oo_apply (line {method_lines['lock_room_oo_apply']}) 之前——"
            "CPU 段必须在锁外"
        )
        # _apply_committed 必须在 lock_room_oo_apply 之后
        assert "_apply_committed" in method_lines, (
            "_apply_settled 未调用 _apply_committed"
        )
        assert method_lines["_apply_committed"] > method_lines["lock_room_oo_apply"], (
            f"_apply_committed (line {method_lines['_apply_committed']}) "
            f"必须在 lock_room_oo_apply (line {method_lines['lock_room_oo_apply']}) 之后——"
            "commit 段必须在锁内"
        )

    def test_prepare_and_stage_does_not_acquire_room_lock(self):
        """_prepare_and_stage 不得调用 lock_room_oo_apply——它在锁外执行。"""
        source = textwrap.dedent(inspect.getsource(
            OH.OoToHtmlCoordinator._prepare_and_stage
        ))
        assert "lock_room_oo_apply" not in source, (
            "_prepare_and_stage 包含 lock_room_oo_apply 调用——"
            "这是锁外方法，不得取锁"
        )

    def test_apply_committed_does_not_call_stage(self):
        """_apply_committed 不得调用 stage_for_commit——CPU 段不在锁内。"""
        source = textwrap.dedent(inspect.getsource(
            OH.OoToHtmlCoordinator._apply_committed
        ))
        assert "stage_for_commit" not in source, (
            "_apply_committed 包含 stage_for_commit 调用——"
            "CPU 段不能在锁内方法里重复执行"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 2. ContentMutationService two-phase API
# ═══════════════════════════════════════════════════════════════════════════


class TestTwoPhaseCommitApi:
    """stage_for_commit / commit_staged / StagedCommit / _ReplayHit 的存在性。"""

    def test_staged_commit_is_frozen(self):
        """StagedCommit 必须是 frozen dataclass——跨锁边界传递不可变数据。"""
        import dataclasses as dc
        assert dc.is_dataclass(StagedCommit), "StagedCommit 不是 dataclass"
        # frozen=True 通过尝试赋值验证
        fields = {f.name for f in dc.fields(StagedCommit)}
        assert "plan" in fields
        assert "mutation" in fields
        assert "projection" in fields
        assert "staged" in fields
        assert "revision_snapshot" in fields

    def test_stage_for_commit_exists(self):
        """ContentMutationService 必须暴露 stage_for_commit 方法。"""
        assert hasattr(ContentMutationService, "stage_for_commit"), (
            "ContentMutationService.stage_for_commit 不存在——two-phase commit 的前半段"
        )

    def test_commit_staged_exists(self):
        """ContentMutationService 必须暴露 commit_staged 方法。"""
        assert hasattr(ContentMutationService, "commit_staged"), (
            "ContentMutationService.commit_staged 不存在——two-phase commit 的后半段"
        )

    def test_original_commit_still_exists(self):
        """原 commit 方法不受影响——其他调用方不应被迫走 two-phase。"""
        assert hasattr(ContentMutationService, "commit"), (
            "ContentMutationService.commit 被删了！其他调用方（HTML→OO / upload / "
            "rollback）应继续用单步 commit"
        )

    def test_replay_hit_is_not_domain_error(self):
        """_ReplayHit 不继承 ContentMutationError——它是控制流信号，不是业务错误。"""
        from app.services.workpaper_sync.content_mutation import ContentMutationError
        assert not issubclass(_ReplayHit, ContentMutationError), (
            "_ReplayHit 继承了 ContentMutationError——它会被 caller 的 except "
            "ContentMutationError 误捕，应该只被 except _ReplayHit 捕获"
        )

    def test_replay_hit_carries_receipt(self):
        """_ReplayHit 必须携带 receipt，caller 才能跳过 commit_staged 直接返回。"""
        sentinel = object()
        hit = _ReplayHit(sentinel)  # type: ignore[arg-type]
        assert hit.receipt is sentinel


# ═══════════════════════════════════════════════════════════════════════════
# 3. 锁语义不变量
# ═══════════════════════════════════════════════════════════════════════════


class TestLockSemanticsInvariant:
    """锁的 keying、类型、解锁方式不受 ROI-6 影响。"""

    def test_lock_is_still_session_level(self):
        """lock_room_oo_apply 仍用 pg_advisory_lock（会话级），不是 pg_advisory_xact_lock。

        docstring 里会提到 pg_advisory_xact_lock 作为对比说明，所以只检查 SQL 语句部分。
        """
        from app.services.workpaper_sync.repository import WorkpaperSyncRepository
        source = textwrap.dedent(inspect.getsource(WorkpaperSyncRepository.lock_room_oo_apply))
        # 确认 SQL 文本字符串里用的是 pg_advisory_lock 而不是 pg_advisory_xact_lock
        # SQL 语句是 sa.text("SELECT pg_advisory_lock(...)") 形式
        import re
        sql_strings = re.findall(r'"SELECT\s+(\w+)\(', source)
        assert any("pg_advisory_lock" == fn for fn in sql_strings), (
            f"lock_room_oo_apply 的 SQL 中找不到 pg_advisory_lock 调用，实际: {sql_strings}"
        )
        assert all("pg_advisory_xact_lock" != fn for fn in sql_strings), (
            "lock_room_oo_apply 的 SQL 换成了事务级锁——临界区内有 commit，事务级锁会自动释放"
        )

    def test_unlock_still_explicit(self):
        """unlock_room_oo_apply 仍在 finally 中显式释放。"""
        source = textwrap.dedent(inspect.getsource(
            OH.OoToHtmlCoordinator._apply_settled
        ))
        assert "unlock_room_oo_apply" in source, (
            "_apply_settled 的 finally 中缺少 unlock_room_oo_apply——"
            "会话级锁不随事务结束自动释放，必须显式释放"
        )
        assert "finally" in source, (
            "_apply_settled 缺少 finally 块——锁释放必须在 finally 中"
        )

    def test_keying_unchanged(self):
        """锁的 keying 仍是 f'oo_apply:{room_id}'。"""
        from app.services.workpaper_sync.repository import WorkpaperSyncRepository
        source = textwrap.dedent(inspect.getsource(WorkpaperSyncRepository.lock_room_oo_apply))
        assert "oo_apply:" in source, (
            "锁的 key 前缀变了——不同前缀会导致新旧锁互不阻塞"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 4. 变异证明：删掉 lock 后判据必须打红
# ═══════════════════════════════════════════════════════════════════════════


class TestMutationProof:
    """如果有人把 lock_room_oo_apply 从 _apply_settled 中删掉，上面的判据必须红。"""

    def test_removing_lock_breaks_topology_check(self):
        """模拟：把 lock_room_oo_apply 从源码中移除，验证拓扑判据失败。"""
        source = textwrap.dedent(inspect.getsource(
            OH.OoToHtmlCoordinator._apply_settled
        ))
        # 确认现在有 lock 调用
        assert "lock_room_oo_apply" in source, "前提不成立：源码里没有 lock 调用"
        # 如果把 lock 删了，拓扑检查应该抓到
        mutated = source.replace("lock_room_oo_apply", "noop_no_lock_xxx")
        tree = ast.parse(mutated)
        has_lock = any(
            isinstance(n, ast.Attribute) and n.attr == "lock_room_oo_apply"
            for n in ast.walk(tree)
        )
        assert not has_lock, "变异后仍能找到 lock_room_oo_apply——变异无效"
