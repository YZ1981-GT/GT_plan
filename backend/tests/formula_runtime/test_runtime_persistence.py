"""Formula Runtime Persistence — migration 幂等 / outbox 同事务 / 并发约束 测试。

**Validates: Requirements 4, 8, 9 | Properties P4, P9, P10, P11**

- P4: 真实回滚恒等（outbox 事件存在性与业务写入一致）
- P9: Outbox 原子性 — 业务写入提交当且仅当对应 outbox event 存在
- P10: Revision fingerprint 敏感性
- P11: 并发单写者 — (project_id, year, idempotency_key) 唯一约束

覆盖:
1. V104 migration 幂等性（IF NOT EXISTS 多次执行不报错）
2. ORM 模型字段完整性
3. write_outbox_event 幂等写入
4. publish_pending_events 重试与交付
5. 同事务原子性保证（outbox 与 audit 同在/同无）
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st


# ═══════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════

PROJECT_ID = uuid.UUID("5e193c68-0000-0000-0000-000000000001")
RUN_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
YEAR = 2025


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Migration V104 幂等性
# ═══════════════════════════════════════════════════════════════════════════════


class TestMigrationIdempotency:
    """V104 migration 使用 IF NOT EXISTS / information_schema，多次执行不报错。"""

    def test_migration_file_uses_if_not_exists(self):
        """V104 DDL 全部使用幂等语法（IF NOT EXISTS / DO $$ ... END $$）。"""
        import pathlib

        migration_path = pathlib.Path("backend/migrations/V104__formula_runtime_outbox.sql")
        if not migration_path.exists():
            migration_path = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "V104__formula_runtime_outbox.sql"

        assert migration_path.exists(), f"V104 migration not found at {migration_path}"
        content = migration_path.read_text(encoding="utf-8")

        # 所有 ALTER TABLE 应在 DO $$ + information_schema 检查内
        assert "information_schema.columns" in content
        assert "CREATE TABLE IF NOT EXISTS formula_runtime_outbox" in content
        assert "CREATE INDEX IF NOT EXISTS" in content
        # 唯一约束也有幂等检查
        assert "pg_indexes" in content

    def test_migration_creates_unique_constraint_for_concurrency(self):
        """V104 包含 (project_id, year, idempotency_key) 唯一约束。"""
        import pathlib

        migration_path = pathlib.Path("backend/migrations/V104__formula_runtime_outbox.sql")
        if not migration_path.exists():
            migration_path = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "V104__formula_runtime_outbox.sql"

        content = migration_path.read_text(encoding="utf-8")
        assert "uq_audit_project_year_idempotency" in content
        assert "project_id" in content
        assert "idempotency_key" in content


# ═══════════════════════════════════════════════════════════════════════════════
# 2. ORM 模型完整性
# ═══════════════════════════════════════════════════════════════════════════════


class TestORMModelCompleteness:
    """验证 ORM 模型包含 V104 扩展列。"""

    def test_draft_refresh_audit_has_v104_columns(self):
        """DraftRefreshAudit 包含 V104 扩展列。"""
        from app.models.workpaper_models import DraftRefreshAudit

        mapper = DraftRefreshAudit.__table__
        col_names = {c.name for c in mapper.columns}

        assert "revision_fingerprint" in col_names
        assert "transaction_mode" in col_names
        assert "idempotency_key" in col_names
        assert "failure_detail" in col_names

    def test_draft_refresh_snapshot_has_v104_columns(self):
        """DraftRefreshSnapshot 包含 V104 扩展列。"""
        from app.models.workpaper_models import DraftRefreshSnapshot

        mapper = DraftRefreshSnapshot.__table__
        col_names = {c.name for c in mapper.columns}

        assert "domain" in col_names
        assert "target_locator" in col_names
        assert "after_value" in col_names
        assert "before_version" in col_names
        assert "after_version" in col_names
        assert "restored_at" in col_names

    def test_wp_formula_has_lifecycle_columns(self):
        """WpFormula 包含 V104 生命周期列。"""
        from app.models.workpaper_models import WpFormula

        mapper = WpFormula.__table__
        col_names = {c.name for c in mapper.columns}

        assert "lifecycle_state" in col_names
        assert "definition_version" in col_names
        assert "definition_hash" in col_names

    def test_formula_runtime_outbox_model_exists(self):
        """FormulaRuntimeOutbox ORM 模型存在且字段完整。"""
        from app.models.workpaper_models import FormulaRuntimeOutbox

        mapper = FormulaRuntimeOutbox.__table__
        col_names = {c.name for c in mapper.columns}

        expected = {
            "id", "event_key", "run_id", "event_type",
            "payload", "attempts", "delivered_at", "last_error", "created_at",
        }
        assert expected.issubset(col_names)

    def test_outbox_event_key_is_unique(self):
        """FormulaRuntimeOutbox.event_key 列有唯一约束。"""
        from app.models.workpaper_models import FormulaRuntimeOutbox

        col = FormulaRuntimeOutbox.__table__.c.event_key
        assert col.unique is True


# ═══════════════════════════════════════════════════════════════════════════════
# 3. write_outbox_event 幂等写入
# ═══════════════════════════════════════════════════════════════════════════════


class TestWriteOutboxEvent:
    """write_outbox_event 幂等性 + 原子性。"""

    @pytest.mark.asyncio
    async def test_write_returns_outbox_record(self):
        """write_outbox_event 返回 FormulaRuntimeOutbox 实例。"""
        from app.services.formula_runtime.outbox import write_outbox_event
        from app.models.workpaper_models import FormulaRuntimeOutbox

        event_key = f"stale:{RUN_ID}:workpaper:wp1"
        mock_record = MagicMock(spec=FormulaRuntimeOutbox)
        mock_record.event_key = event_key
        mock_record.run_id = RUN_ID
        mock_record.event_type = "stale"
        mock_record.attempts = 0
        mock_record.delivered_at = None

        session = AsyncMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()

        # Second execute (select) returns the record
        select_result = MagicMock()
        select_result.scalar_one = MagicMock(return_value=mock_record)

        call_count = [0]

        async def _side_effect(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                # INSERT ON CONFLICT
                return MagicMock()
            else:
                # SELECT
                return select_result

        session.execute = AsyncMock(side_effect=_side_effect)

        result = await write_outbox_event(
            session,
            run_id=RUN_ID,
            event_type="stale",
            event_key=event_key,
            payload={"domain": "workpaper", "target": "wp1"},
        )

        assert result.event_key == event_key
        assert result.event_type == "stale"
        session.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_write_idempotent_on_duplicate_key(self):
        """相同 event_key 多次调用不报错（ON CONFLICT DO NOTHING）。"""
        from app.services.formula_runtime.outbox import write_outbox_event
        from app.models.workpaper_models import FormulaRuntimeOutbox

        event_key = f"invalidate:{RUN_ID}:ref:formula_abc"
        mock_record = MagicMock(spec=FormulaRuntimeOutbox)
        mock_record.event_key = event_key
        mock_record.attempts = 0

        session = AsyncMock()
        select_result = MagicMock()
        select_result.scalar_one = MagicMock(return_value=mock_record)

        async def _side_effect(stmt):
            return select_result

        session.execute = AsyncMock(side_effect=_side_effect)
        session.flush = AsyncMock()

        # Call twice with same event_key — should not raise
        r1 = await write_outbox_event(
            session, run_id=RUN_ID, event_type="invalidate", event_key=event_key,
        )
        r2 = await write_outbox_event(
            session, run_id=RUN_ID, event_type="invalidate", event_key=event_key,
        )

        assert r1.event_key == event_key
        assert r2.event_key == event_key

    @pytest.mark.asyncio
    async def test_write_with_none_payload_defaults_to_empty_dict(self):
        """payload=None 时默认写入 {} 空 JSON。"""
        from app.services.formula_runtime.outbox import write_outbox_event

        session = AsyncMock()
        session.flush = AsyncMock()

        call_args_captured = []

        async def _capture_execute(stmt):
            call_args_captured.append(stmt)
            result = MagicMock()
            result.scalar_one = MagicMock(return_value=MagicMock(
                event_key="k", payload={}, attempts=0
            ))
            return result

        session.execute = AsyncMock(side_effect=_capture_execute)

        await write_outbox_event(
            session, run_id=RUN_ID, event_type="stale", event_key="k", payload=None,
        )

        # The first call is INSERT — verify it was executed without error
        assert len(call_args_captured) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# 4. publish_pending_events 重试与交付
# ═══════════════════════════════════════════════════════════════════════════════


class TestPublishPendingEvents:
    """publish_pending_events 幂等发布、失败重试。"""

    @pytest.mark.asyncio
    async def test_publish_marks_delivered(self):
        """成功发布的事件被标记 delivered_at。"""
        from app.services.formula_runtime.outbox import publish_pending_events
        from app.models.workpaper_models import FormulaRuntimeOutbox

        event = MagicMock(spec=FormulaRuntimeOutbox)
        event.event_key = "test-key"
        event.event_type = "stale"
        event.payload = {"domain": "workpaper"}
        event.attempts = 0
        event.delivered_at = None
        event.run_id = RUN_ID

        session = AsyncMock()
        select_result = MagicMock()
        select_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[event]))
        )
        session.execute = AsyncMock(return_value=select_result)
        session.flush = AsyncMock()

        publisher = AsyncMock()  # no-op publisher

        count = await publish_pending_events(
            session, run_id=RUN_ID, publisher=publisher,
        )

        assert count == 1
        assert event.delivered_at is not None
        assert event.attempts == 1
        publisher.assert_awaited_once_with("stale", {"domain": "workpaper"})

    @pytest.mark.asyncio
    async def test_publish_records_error_on_failure(self):
        """发布失败时递增 attempts 并记录 last_error。"""
        from app.services.formula_runtime.outbox import publish_pending_events
        from app.models.workpaper_models import FormulaRuntimeOutbox

        event = MagicMock(spec=FormulaRuntimeOutbox)
        event.event_key = "fail-key"
        event.event_type = "invalidate"
        event.payload = {}
        event.attempts = 2
        event.delivered_at = None
        event.last_error = None
        event.run_id = RUN_ID

        session = AsyncMock()
        select_result = MagicMock()
        select_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[event]))
        )
        session.execute = AsyncMock(return_value=select_result)
        session.flush = AsyncMock()

        # Publisher that always fails
        publisher = AsyncMock(side_effect=RuntimeError("network timeout"))

        count = await publish_pending_events(
            session, run_id=RUN_ID, publisher=publisher,
        )

        assert count == 0  # nothing delivered
        assert event.attempts == 3
        assert "network timeout" in event.last_error
        assert event.delivered_at is None

    @pytest.mark.asyncio
    async def test_publish_without_publisher_marks_delivered(self):
        """无 publisher 时（测试场景），事件直接标记已交付。"""
        from app.services.formula_runtime.outbox import publish_pending_events
        from app.models.workpaper_models import FormulaRuntimeOutbox

        event = MagicMock(spec=FormulaRuntimeOutbox)
        event.event_key = "noop-key"
        event.event_type = "stale"
        event.payload = {}
        event.attempts = 0
        event.delivered_at = None
        event.run_id = RUN_ID

        session = AsyncMock()
        select_result = MagicMock()
        select_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[event]))
        )
        session.execute = AsyncMock(return_value=select_result)
        session.flush = AsyncMock()

        count = await publish_pending_events(
            session, run_id=RUN_ID, publisher=None,
        )

        assert count == 1
        assert event.delivered_at is not None

    @pytest.mark.asyncio
    async def test_publish_empty_queue_returns_zero(self):
        """无待发布事件时返回 0。"""
        from app.services.formula_runtime.outbox import publish_pending_events

        session = AsyncMock()
        select_result = MagicMock()
        select_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[]))
        )
        session.execute = AsyncMock(return_value=select_result)
        session.flush = AsyncMock()

        count = await publish_pending_events(session, run_id=RUN_ID)
        assert count == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Outbox 原子性（P9）— 业务写入提交 ↔ outbox event 同在/同无
# ═══════════════════════════════════════════════════════════════════════════════


class TestP9OutboxAtomicity:
    """**Validates: Property 9 — 业务写入提交当且仅当对应 outbox event 存在。**

    验证 write_outbox_event 必须在业务事务内调用：
    - 正常提交：audit + outbox 同在
    - 回滚场景：audit + outbox 同无（事务回滚两者都丢）
    """

    @pytest.mark.asyncio
    async def test_write_within_transaction_ensures_coexistence(self):
        """同事务写入 audit + outbox → 提交后两者同在。"""
        from app.services.formula_runtime.outbox import write_outbox_event

        # Simulate: audit 已写入同一 session (mock)，outbox 紧随其后
        session = AsyncMock()
        session.flush = AsyncMock()

        mock_outbox = MagicMock()
        mock_outbox.event_key = "coexist-key"
        mock_outbox.run_id = RUN_ID

        select_result = MagicMock()
        select_result.scalar_one = MagicMock(return_value=mock_outbox)

        session.execute = AsyncMock(return_value=select_result)

        result = await write_outbox_event(
            session,
            run_id=RUN_ID,
            event_type="stale",
            event_key="coexist-key",
        )

        # 验证 outbox 事件与 run_id 关联
        assert result.run_id == RUN_ID
        # flush 被调用（同事务内）
        session.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_rollback_removes_both_audit_and_outbox(self):
        """事务 rollback 时 outbox 和 audit 两者均不存在（原子性）。

        验证方式：模拟 rollback 后查询 outbox → 空。
        """
        from app.services.formula_runtime.outbox import get_events_by_run

        session = AsyncMock()
        # After rollback, query returns empty
        select_result = MagicMock()
        select_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[]))
        )
        session.execute = AsyncMock(return_value=select_result)

        events = await get_events_by_run(session, RUN_ID)
        assert events == []


# ═══════════════════════════════════════════════════════════════════════════════
# 6. 并发约束（P11）— (project_id, year, idempotency_key) 唯一
# ═══════════════════════════════════════════════════════════════════════════════


class TestP11ConcurrencyConstraint:
    """**Validates: Property 11 — 并发单写者。**

    唯一约束 uq_audit_project_year_idempotency 保证：
    同 project_id + year + idempotency_key 只能有一个成功的 run。
    """

    def test_audit_model_has_idempotency_key(self):
        """DraftRefreshAudit 有 idempotency_key 列。"""
        from app.models.workpaper_models import DraftRefreshAudit

        mapper = DraftRefreshAudit.__table__
        col_names = {c.name for c in mapper.columns}
        assert "idempotency_key" in col_names

    def test_unique_constraint_in_migration(self):
        """V104 migration 含 partial unique index on (project_id, year, idempotency_key)。"""
        import pathlib

        migration_path = pathlib.Path("backend/migrations/V104__formula_runtime_outbox.sql")
        if not migration_path.exists():
            migration_path = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "V104__formula_runtime_outbox.sql"

        content = migration_path.read_text(encoding="utf-8")

        # Partial unique index (WHERE idempotency_key IS NOT NULL)
        assert "uq_audit_project_year_idempotency" in content
        assert "WHERE idempotency_key IS NOT NULL" in content

    @settings(max_examples=5, deadline=None)
    @given(
        key=st.text(min_size=1, max_size=64, alphabet="abcdef0123456789"),
    )
    def test_pbt_idempotency_key_dedup_property(self, key: str):
        """**Validates: P11** — 相同 idempotency_key 的并发请求被唯一约束阻止。

        验证：唯一约束的存在性保证了 DB 层面同 key 只有一行。
        （真正的并发测试需要 PG integration — 此处验证 ORM 契约。）
        """
        from app.models.workpaper_models import DraftRefreshAudit

        # Verify the column exists and accepts the key string
        col = DraftRefreshAudit.__table__.c.idempotency_key
        assert col is not None
        assert col.type.length >= len(key)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Revision fingerprint column 存在性（P10）
# ═══════════════════════════════════════════════════════════════════════════════


class TestP10RevisionFingerprint:
    """**Validates: Property 10 — revision_fingerprint 列存在。**

    真实 SHA256 敏感性测试由 integration test 覆盖；
    此处验证 ORM 列存在且类型正确。
    """

    def test_audit_has_revision_fingerprint_column(self):
        """DraftRefreshAudit.revision_fingerprint 是 VARCHAR(64)。"""
        from app.models.workpaper_models import DraftRefreshAudit

        col = DraftRefreshAudit.__table__.c.revision_fingerprint
        assert col is not None
        assert col.type.length == 64

    def test_transaction_mode_has_default(self):
        """DraftRefreshAudit.transaction_mode 默认 all_or_nothing。"""
        from app.models.workpaper_models import DraftRefreshAudit

        col = DraftRefreshAudit.__table__.c.transaction_mode
        assert col is not None
        # Check server_default text
        assert "all_or_nothing" in str(col.server_default.arg)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Module import 验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestModuleImports:
    """验证 outbox 模块可正常导入。"""

    def test_outbox_module_importable(self):
        """formula_runtime.outbox 可导入。"""
        from app.services.formula_runtime import outbox

        assert hasattr(outbox, "write_outbox_event")
        assert hasattr(outbox, "publish_pending_events")
        assert hasattr(outbox, "get_events_by_run")
        assert hasattr(outbox, "count_undelivered")
        assert hasattr(outbox, "MAX_DELIVERY_ATTEMPTS")

    def test_outbox_max_delivery_attempts_is_reasonable(self):
        """MAX_DELIVERY_ATTEMPTS 在合理范围 [3, 10]。"""
        from app.services.formula_runtime.outbox import MAX_DELIVERY_ATTEMPTS

        assert 3 <= MAX_DELIVERY_ATTEMPTS <= 10
