# -*- coding: utf-8 -*-
"""WorkpaperSaveOrchestrator 单元测试 —— **零版本写**的可重放副作用 handler。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 16 + 18
Requirements: 2.1, 2.12, 13.1, 13.3, 13.4
Properties: P4（业务版本与 representation generation 正交）/ P52 / P54 / P61

═══ 判据在 Task 18 翻了面 ═══

改造前本文件有三组用例把 ``file_version`` 当成 ``after_save`` 的产出来断言：

* ``TestAfterSaveIncrementsFileVersion``（"1 → 2"、"5 → 6"）；
* ``TestAfterSaveWritesAuditLog`` 断言审计日志里的 ``old_version/new_version``；
* ``TestOptimisticLockMismatchRaises409`` + 一条 PBT，验 ``expected_version`` 比对。

三组都随生产实现一起改：

1. **零版本写**。Requirement 2.12 要求这个 handler「由提交后可重放 handler 执行；
   handler 重试不得再次递增 content revision」。一个被四条写路径共用、且要能重放的
   handler 不可能是任何版本的所有者 —— 重放一次就多一个伪版本。所以现在断言的是
   ``after_save`` 只写 :data:`SIDE_EFFECT_WRITABLE_FIELDS` 里那两个字段，
   ``file_version`` / ``content_revision`` 一个都不碰。
2. **审计日志记业务内容版本**。旧实现记的是 ``file_version``，于是「审计日志里的
   版本」与「下游按哪个版本刷新」是两个不同的计数器。
3. **``expected_version`` 不是乐观锁**。它比较的是**内存里**的 ``wp.file_version``：
   同一个 Python 对象自己跟自己比，两次调用之间没有任何数据库谓词。旧的那条 PBT
   之所以"恰好一个成功一个冲突"，纯粹因为第一次调用把内存里的值 +1 了 —— 换成两个
   独立 session 就两个都成功。真乐观锁是
   ``WorkpaperSyncRepository.bump_content_revision()`` 的
   ``UPDATE ... WHERE content_revision = :expected``（单条 SQL CAS），由
   ``ContentMutationService`` 在业务事务内执行，行为验证在
   ``tests/workpaper_sync/test_task18_html_save_unified_revision_pg.py``（真库、真并发）。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.workpaper_save_orchestrator import (
    SIDE_EFFECT_HANDLER_NAME,
    SIDE_EFFECT_HANDLER_VERSION,
    SIDE_EFFECT_WRITABLE_FIELDS,
    WorkpaperSaveOrchestrator,
    orchestrator,
)

#: 本 handler 绝不允许写入的版本字段。取值与
#: `check_workpaper_writer_revision_gate` 的 `after_save_still_increments_revision`
#: 判据同域（`writes_legacy_version_field` ∪ `writes_unified_content_revision`）。
_FORBIDDEN_VERSION_FIELDS = ("file_version", "content_revision")


# ─── Fixtures ────────────────────────────────────────────────────────────────


class _RecordingWorkingPaper:
    """记录**每一次**属性写入的 WorkingPaper 替身。

    刻意不是 ``MagicMock``：``MagicMock`` 对任何属性赋值都静默接受，于是
    「handler 有没有写 ``file_version``」这条判据在 mock 上恒为不可判定 —— 只能靠
    "写完之后值是多少"间接推断，而 handler 若把它写成同一个值就查不出来。
    这个替身记录 ``(field, value)`` 序列，因此「写过但值没变」也算写过。
    """

    def __init__(self, *, file_version: int = 1, content_revision: int = 7) -> None:
        object.__setattr__(self, "_writes", [])
        object.__setattr__(self, "id", uuid.uuid4())
        object.__setattr__(self, "project_id", uuid.uuid4())
        object.__setattr__(self, "file_version", file_version)
        object.__setattr__(self, "content_revision", content_revision)
        object.__setattr__(self, "prefill_stale", False)
        object.__setattr__(
            self, "updated_at", datetime(2025, 1, 1, tzinfo=timezone.utc)
        )

    def __setattr__(self, name: str, value: object) -> None:
        self._writes.append((name, value))
        object.__setattr__(self, name, value)

    @property
    def written_fields(self) -> list[str]:
        return [field for field, _ in self._writes]


def _make_wp(file_version: int = 1, content_revision: int = 7) -> _RecordingWorkingPaper:
    return _RecordingWorkingPaper(
        file_version=file_version, content_revision=content_revision
    )


def _make_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.username = "test_user"
    return user


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture(autouse=True)
def _patch_event_bus():
    """统一 patch event_bus.publish 避免真实调用。

    Task 16 起 after_save 不再在事务内发布（Requirement 13.1），所以这个 mock 的
    `publish` **必须一次都不被调到** —— 见
    `TestAfterSaveEnqueuesDurableEventInsteadOfPublishing`。
    """
    mock_bus = MagicMock()
    mock_bus.publish = AsyncMock()
    mock_bus.publish_immediate = AsyncMock()
    with patch("app.services.event_bus.event_bus", mock_bus):
        yield mock_bus


def _added_of_type(db: AsyncMock, type_name: str) -> list:
    """从 `db.add` 的调用记录里挑出指定 ORM 类型的实例。"""
    return [
        call.args[0]
        for call in db.add.call_args_list
        if type(call.args[0]).__name__ == type_name
    ]


# ─── Requirement 2.12：零版本写 ───────────────────────────────────────────────


class TestAfterSaveWritesNoVersionField:
    """**Validates: Requirements 2.12**

    Property 4 的 handler 侧：副作用 handler 不得移动任何版本字段。
    """

    @pytest.mark.asyncio
    async def test_after_save_writes_no_version_field(self):
        wp = _make_wp(file_version=1, content_revision=7)
        db = _make_db()

        await orchestrator.after_save(
            db, wp, _make_user(), trigger="html_save", extra={}, content_revision=8
        )

        # ① 逐字段判据：写入集合必须是允许集合的子集。
        assert set(wp.written_fields) <= SIDE_EFFECT_WRITABLE_FIELDS, (
            f"after_save 写了不该写的字段: "
            f"{sorted(set(wp.written_fields) - SIDE_EFFECT_WRITABLE_FIELDS)}"
        )
        # ② 版本字段一次都没被赋值 —— 「写成同一个值」也算写过（替身记录的是写入动作，
        #    不是最终值），所以这条无法用「值没变」蒙过去。
        for field in _FORBIDDEN_VERSION_FIELDS:
            assert field not in wp.written_fields, (
                f"after_save 写了 {field} —— 它必须由各自的所有者推进"
                "（content_revision → ContentMutationService；file_version → 真正写文件那处）"
            )
        # ③ 值也确实没动。
        assert wp.file_version == 1
        assert wp.content_revision == 7

    @pytest.mark.asyncio
    async def test_the_allowed_write_set_is_exactly_the_two_side_effect_fields(self):
        """允许集合本身是判据的一半，所以它必须被钉住。

        把 ``file_version`` 悄悄加进 :data:`SIDE_EFFECT_WRITABLE_FIELDS` 就能让上一条
        用例变绿 —— 这条防的正是那种"改判据而不是改行为"。
        """
        assert SIDE_EFFECT_WRITABLE_FIELDS == frozenset({"prefill_stale", "updated_at"})

    @pytest.mark.asyncio
    async def test_replaying_the_handler_never_moves_a_version(self):
        """Requirement 2.12 后半句：handler 重试不得再次递增 content revision。"""
        wp = _make_wp(file_version=4, content_revision=11)
        db = _make_db()
        user = _make_user()

        for _ in range(3):
            await orchestrator.after_save(
                db, wp, user, trigger="html_save", extra={}, content_revision=12
            )

        assert wp.file_version == 4
        assert wp.content_revision == 11
        assert set(wp.written_fields) <= SIDE_EFFECT_WRITABLE_FIELDS

    @pytest.mark.asyncio
    async def test_handler_version_moved_with_the_semantics(self):
        """语义变了，handler version 必须跟着 +1（Requirement 13.3 的幂等键半边）。

        v1 时代的语义含「递增 file_version」；沿用 v1 会让 v1 已消费过的 event id 复用
        v2 语义的幂等键，重放时该做的副作用被当成"已做过"。
        """
        assert SIDE_EFFECT_HANDLER_NAME == "workpaper_save_orchestrator.after_save"
        assert SIDE_EFFECT_HANDLER_VERSION >= 2


class TestAfterSaveMarksPrefillStale:
    """test_after_save_marks_prefill_stale"""

    @pytest.mark.asyncio
    async def test_sets_prefill_stale_true(self):
        wp = _make_wp()
        db = _make_db()

        await orchestrator.after_save(
            db, wp, _make_user(), trigger="html_save", extra={}
        )

        assert wp.prefill_stale is True
        assert wp.updated_at.tzinfo is not None, "updated_at 必须是 aware datetime"


class TestAfterSaveReturnsTheContentRevisionUnchanged:
    """**Validates: Requirements 2.12**

    `content_revision` 参数是**只读**的：原样回传，便于调用方断言两边一致。
    """

    @pytest.mark.asyncio
    async def test_returns_what_it_was_given(self):
        wp = _make_wp(content_revision=3)
        db = _make_db()

        returned = await orchestrator.after_save(
            db, wp, _make_user(), trigger="html_save", extra={}, content_revision=4
        )

        assert returned == 4, "handler 必须原样回传调用方声明的 business revision"

    @pytest.mark.asyncio
    async def test_unmigrated_callers_may_pass_none(self):
        """尚未迁入 `ContentMutationService` 的路径（Task 19）传 None，不得因此报错。"""
        wp = _make_wp()
        db = _make_db()

        returned = await orchestrator.after_save(
            db, wp, _make_user(), trigger="univer_save", extra={}
        )

        assert returned is None


class TestAfterSaveEnqueuesDurableEventInsteadOfPublishing:
    """spec workpaper-html-onlyoffice-bidirectional-writeback-closure Task 16。

    **Validates: Requirements 13.1**

    原用例断言"after_save 在事务内 publish 了一次"。Task 16 把这条判据翻面：事务内
    发布在回滚后会留下下游按不存在的版本刷新的幽灵事件（Property 52），所以现在只许
    写一条 pending 耐久行，发布由调用方在 commit 之后完成。
    """

    @pytest.mark.asyncio
    async def test_enqueues_pending_outbox_row_with_full_payload(self, _patch_event_bus):
        wp = _make_wp(file_version=3, content_revision=9)
        db = _make_db()

        await orchestrator.after_save(
            db, wp, _make_user(), trigger="custom_query_writeback",
            extra={"year": 2025, "wp_code": "D2"},
            content_revision=10,
        )

        rows = _added_of_type(db, "ImportEventOutbox")
        assert len(rows) == 1, "一次保存恰一条耐久事件行"
        row = rows[0]
        assert row.event_type == "workpaper.saved"
        assert row.project_id == wp.project_id
        assert row.year == 2025
        assert row.status.value == "pending", "入队时是 pending，发布后才 published"
        assert row.payload["trigger"] == "custom_query_writeback"
        # 🔴 payload 里的版本是**业务内容版本**。旧实现放的是 file_version，于是下游
        #    "按返回的新版本刷新"刷的是另一个计数器。
        assert row.payload["content_revision"] == 10
        assert "file_version" not in row.payload, (
            "耐久 payload 不得再携带 file_version 作为同步版本（Requirement 2.1）"
        )
        assert row.payload["wp_id"] == str(wp.id)
        assert row.payload["wp_code"] == "D2"
        # year 是路由列，不重复进 payload。
        assert "year" not in row.payload

    @pytest.mark.asyncio
    async def test_does_not_publish_inside_the_transaction(self, _patch_event_bus):
        wp = _make_wp(file_version=3)
        db = _make_db()

        await orchestrator.after_save(
            db, wp, _make_user(), trigger="html_save", extra={"year": 2025}
        )

        _patch_event_bus.publish.assert_not_called()
        _patch_event_bus.publish_immediate.assert_not_called()


class TestAfterSaveWritesAuditLog:
    """test_after_save_writes_audit_log"""

    @pytest.mark.asyncio
    async def test_writes_log(self):
        wp = _make_wp(file_version=2, content_revision=5)
        db = _make_db()

        await orchestrator.after_save(
            db, wp, _make_user(), trigger="onlyoffice_callback", extra={},
            content_revision=6,
        )

        # Task 16 起同一事务里加两行：审计 Log + 耐久 outbox 事件。按类型挑，不再用
        # assert_called_once —— 那会把"多加了一行耐久事件"误判成回归。
        logs = _added_of_type(db, "Log")
        assert len(logs) == 1
        log_obj = logs[0]
        assert log_obj.action_type == "workpaper_onlyoffice_callback"
        assert log_obj.object_type == "working_paper"
        assert log_obj.object_id == wp.id
        # 记的是业务内容版本，不是文件版本（旧实现记 old_version/new_version）。
        assert log_obj.new_value["content_revision"] == 6
        assert "old_version" not in log_obj.new_value
        assert "new_version" not in log_obj.new_value


class TestOptimisticLockIsNoLongerThisHandlersJob:
    """**Validates: Requirements 2.2**

    ``expected_version`` / ``OptimisticLockError`` 已从本模块删除。这里用**导入面**
    判据钉住"它不会悄悄回来"：留一个同名壳（哪怕永不抛）就会让调用方以为自己有锁。
    """

    def test_module_no_longer_exports_an_in_memory_lock(self):
        import app.services.workpaper_save_orchestrator as mod

        assert not hasattr(mod, "OptimisticLockError"), (
            "OptimisticLockError 不该回来：它比较的是内存里的 wp.file_version，"
            "跨进程并发一个也拦不住。真锁在 WorkpaperSyncRepository.bump_content_revision"
        )

    def test_after_save_signature_has_no_expected_version(self):
        import inspect

        params = inspect.signature(
            WorkpaperSaveOrchestrator.after_save
        ).parameters
        assert "expected_version" not in params, sorted(params)
        assert "content_revision" in params, sorted(params)


# ─── PBT: 任意 trigger / 任意 revision 下都零版本写 ──────────────────────────

from hypothesis import HealthCheck, given, settings, strategies as st


class TestZeroVersionWriteHoldsForEveryTrigger:
    """**Validates: Requirements 2.12**

    Property 4 / Property 61 的 handler 侧全称命题：**任意** trigger、任意
    ``content_revision``、任意重放次数下，``after_save`` 写入的字段集合恒为
    :data:`SIDE_EFFECT_WRITABLE_FIELDS` 的子集，且两个版本字段的值恒不变。

    这条取代了旧的"两个并发写入恰好一个成功"—— 那条 PBT 验的是内存断言，换成两个
    独立 session 就两个都成功，属于把假锁当真锁锁死（假绿第③源）。
    """

    @settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        initial_file_version=st.integers(min_value=0, max_value=1000),
        initial_revision=st.integers(min_value=0, max_value=1000),
        target_revision=st.one_of(st.none(), st.integers(min_value=0, max_value=2000)),
        trigger=st.sampled_from(
            [
                "html_save",
                "univer_save",
                "onlyoffice_callback",
                "custom_query_writeback",
            ]
        ),
        replays=st.integers(min_value=1, max_value=3),
    )
    @pytest.mark.asyncio
    async def test_no_version_moves_for_any_input(
        self,
        initial_file_version,
        initial_revision,
        target_revision,
        trigger,
        replays,
        _patch_event_bus,
    ):
        wp = _make_wp(
            file_version=initial_file_version, content_revision=initial_revision
        )
        db = _make_db()
        user = _make_user()
        orch = WorkpaperSaveOrchestrator()

        for _ in range(replays):
            returned = await orch.after_save(
                db, wp, user, trigger=trigger, extra={},
                content_revision=target_revision,
            )
            assert returned == target_revision

        assert set(wp.written_fields) <= SIDE_EFFECT_WRITABLE_FIELDS
        assert wp.file_version == initial_file_version
        assert wp.content_revision == initial_revision
        # 每次投递恰一条耐久行 —— fan-out 去重是 outbox 侧的闸门（Requirement 13.3），
        # 不是靠 handler 少写一行来实现的。
        assert len(_added_of_type(db, "ImportEventOutbox")) == replays
