"""Tests for audit_logger_enhanced + audit_log_writer_worker + verify-chain endpoint.

Refinement Round 1 — Task 21: 审计日志真实落库 + 哈希链
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import fakeredis.aioredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base

# Patch JSONB for SQLite
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

# Import models to register them with Base.metadata
import app.models.core  # noqa: F401
import app.models.audit_log_models  # noqa: F401

from app.services.audit_logger_enhanced import (
    AuditLoggerEnhanced,
    _compute_entry_hash,
    AUDIT_LOG_QUEUE_KEY,
)
from app.workers.audit_log_writer_worker import (
    _compute_entry_hash as worker_compute_hash,
    _mask_payload,
    _write_batch,
    GENESIS_HASH,
)

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    """Create test HTTP client with overridden dependencies."""
    from app.main import app
    from app.core.database import get_db
    from app.core.redis import get_redis

    async def override_get_db():
        yield db_session

    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def override_get_redis():
        yield fake_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


# --- Unit Tests: audit_logger_enhanced ---


class TestAuditLoggerEnhanced:
    """Test the enhanced audit logger service."""

    @pytest.fixture
    def logger_instance(self):
        return AuditLoggerEnhanced()

    @pytest.mark.asyncio
    async def test_log_action_adds_to_memory_cache(self, logger_instance):
        """log_action 调用后内存缓存有记录。"""
        with patch.object(logger_instance, "_get_redis", return_value=None):
            result = await logger_instance.log_action(
                user_id=uuid.uuid4(),
                action="test_action",
                object_type="project",
                object_id=uuid.uuid4(),
                project_id=uuid.uuid4(),
                details={"key": "value"},
                ip_address="127.0.0.1",
            )

        assert len(logger_instance._recent_actions) == 1
        assert logger_instance._recent_actions[0]["action_type"] == "test_action"
        assert logger_instance._recent_actions[0]["object_type"] == "project"
        assert result["action_type"] == "test_action"

    @pytest.mark.asyncio
    async def test_log_action_memory_cache_limit(self, logger_instance):
        """内存缓存限制为 1000 条。"""
        with patch.object(logger_instance, "_get_redis", return_value=None):
            for i in range(1100):
                await logger_instance.log_action(
                    user_id=uuid.uuid4(),
                    action=f"action_{i}",
                    object_type="test",
                )

        assert len(logger_instance._recent_actions) == 1000

    @pytest.mark.asyncio
    async def test_log_action_pushes_to_fallback_queue_when_redis_unavailable(self, logger_instance):
        """Redis 不可用时推入降级队列。"""
        with patch.object(logger_instance, "_get_redis", return_value=None):
            await logger_instance.log_action(
                user_id=uuid.uuid4(),
                action="test_action",
                object_type="project",
            )

        assert logger_instance._fallback_queue is not None
        assert not logger_instance._fallback_queue.empty()

    @pytest.mark.asyncio
    async def test_log_action_returns_entry_dict(self, logger_instance):
        """log_action 返回完整的 entry dict。"""
        uid = uuid.uuid4()
        oid = uuid.uuid4()
        pid = uuid.uuid4()

        with patch.object(logger_instance, "_get_redis", return_value=None):
            result = await logger_instance.log_action(
                user_id=uid,
                action="signature_signed",
                object_type="signature",
                object_id=oid,
                project_id=pid,
                details={"gate_eval_id": "abc123"},
                ip_address="192.168.1.1",
                session_id="sess_001",
                ua="Mozilla/5.0",
            )

        assert result["user_id"] == str(uid)
        assert result["action_type"] == "signature_signed"
        assert result["object_type"] == "signature"
        assert result["object_id"] == str(oid)
        assert result["project_id"] == str(pid)
        assert result["payload"] == {"gate_eval_id": "abc123"}
        assert result["ip"] == "192.168.1.1"
        assert result["session_id"] == "sess_001"
        assert result["ua"] == "Mozilla/5.0"
        assert "ts" in result

    def test_query_logs_filters(self, logger_instance):
        """query_logs 按条件过滤。"""
        logger_instance._recent_actions = [
            {"user_id": "u1", "action_type": "read", "object_type": "wp", "project_id": "p1", "timestamp": 1},
            {"user_id": "u2", "action_type": "write", "object_type": "wp", "project_id": "p1", "timestamp": 2},
            {"user_id": "u1", "action_type": "write", "object_type": "report", "project_id": "p2", "timestamp": 3},
        ]

        assert len(logger_instance.query_logs(user_id="u1")) == 2
        assert len(logger_instance.query_logs(action="write")) == 2
        assert len(logger_instance.query_logs(object_type="report")) == 1
        assert len(logger_instance.query_logs(project_id="p2")) == 1

    @pytest.mark.asyncio
    async def test_log_action_pushes_to_redis_when_available(self, logger_instance):
        """Redis 可用时推入 Redis List。"""
        fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

        async def mock_get_redis():
            return fake_redis

        with patch.object(logger_instance, "_get_redis", side_effect=mock_get_redis):
            await logger_instance.log_action(
                user_id=uuid.uuid4(),
                action="test_redis",
                object_type="project",
            )

        length = await fake_redis.llen(AUDIT_LOG_QUEUE_KEY)
        assert length == 1


# --- Unit Tests: hash computation ---


class TestHashComputation:
    """Test hash chain computation."""

    def test_compute_entry_hash_deterministic(self):
        """相同输入产生相同哈希。"""
        h1 = _compute_entry_hash("2024-01-01T00:00:00", "user1", "action", "obj1", "{}", "0" * 64)
        h2 = _compute_entry_hash("2024-01-01T00:00:00", "user1", "action", "obj1", "{}", "0" * 64)
        assert h1 == h2

    def test_compute_entry_hash_changes_with_input(self):
        """不同输入产生不同哈希。"""
        h1 = _compute_entry_hash("2024-01-01T00:00:00", "user1", "action", "obj1", "{}", "0" * 64)
        h2 = _compute_entry_hash("2024-01-01T00:00:01", "user1", "action", "obj1", "{}", "0" * 64)
        assert h1 != h2

    def test_compute_entry_hash_is_sha256(self):
        """哈希是 64 字符的 SHA-256。"""
        h = _compute_entry_hash("ts", "uid", "act", "oid", "{}", "0" * 64)
        assert len(h) == 64
        int(h, 16)

    def test_hash_chain_continuity(self):
        """哈希链连续性：每条的 prev_hash 是上一条的 entry_hash。"""
        prev = GENESIS_HASH
        hashes = []
        for i in range(5):
            h = _compute_entry_hash(
                f"2024-01-0{i+1}T00:00:00", "user1", "action", f"obj{i}", "{}", prev
            )
            hashes.append(h)
            prev = h

        assert len(set(hashes)) == 5
        prev = GENESIS_HASH
        for i, expected in enumerate(hashes):
            computed = _compute_entry_hash(
                f"2024-01-0{i+1}T00:00:00", "user1", "action", f"obj{i}", "{}", prev
            )
            assert computed == expected
            prev = computed

    def test_worker_and_service_hash_consistent(self):
        """Worker 和 Service 的哈希计算函数一致。"""
        args = ("2024-01-01T00:00:00", "user1", "action", "obj1", '{"key": "val"}', "0" * 64)
        assert _compute_entry_hash(*args) == worker_compute_hash(*args)


# --- Unit Tests: mask_payload ---


class TestMaskPayload:
    """Test payload masking."""

    def test_mask_payload_masks_sensitive_fields(self):
        """脱敏函数替换敏感字段。"""
        payload = {
            "client_contact_phone": "13800138000",
            "client_contact_email": "test@example.com",
            "bank_account_number": "6222021234567890",
            "normal_field": "keep this",
        }
        masked = _mask_payload(payload)
        assert masked["client_contact_phone"] == "***"
        assert masked["client_contact_email"] == "***"
        assert masked["bank_account_number"] == "***"
        assert masked["normal_field"] == "keep this"

    def test_mask_payload_preserves_non_sensitive(self):
        """非敏感字段保持不变。"""
        payload = {"action": "sign", "project_id": "p1", "amount": 1000}
        masked = _mask_payload(payload)
        assert masked == payload


# --- Integration Tests: write_batch + verify-chain ---


class TestWriteBatchAndVerifyChain:
    """Integration tests for batch write and chain verification."""

    @pytest.mark.asyncio
    async def test_write_batch_creates_hash_chain(self, db_session):
        """worker batch write 正确落库 + hash chain 连续。"""
        from app.models.audit_log_models import AuditLogEntry
        from sqlalchemy import select, asc

        project_id = str(uuid.uuid4())
        entries = []
        for i in range(5):
            entries.append({
                "user_id": str(uuid.uuid4()),
                "action_type": f"action_{i}",
                "object_type": "test",
                "object_id": str(uuid.uuid4()),
                "project_id": project_id,
                "payload": {"project_id": project_id, "index": i},
                "ip": "127.0.0.1",
                "ua": None,
                "trace_id": None,
                "session_id": None,
                "ts": datetime(2024, 1, i + 1, tzinfo=timezone.utc).isoformat(),
            })

        # Patch _get_session_factory to use our test session factory
        test_session_factory = async_sessionmaker(
            test_engine, class_=AsyncSession, expire_on_commit=False
        )

        async def mock_session_factory():
            return test_session_factory

        with patch("app.workers.audit_log_writer_worker._get_session_factory", mock_session_factory):
            with patch("app.core.config.settings") as mock_settings:
                mock_settings.DATABASE_URL = TEST_DATABASE_URL
                written = await _write_batch(entries)

        assert written == 5

        # Verify hash chain continuity (prev_hash linkage)
        stmt = select(AuditLogEntry).order_by(asc(AuditLogEntry.ts))
        result = await db_session.execute(stmt)
        rows = result.scalars().all()

        test_rows = [r for r in rows if r.payload and r.payload.get("project_id") == project_id]
        assert len(test_rows) == 5

        # Verify chain linkage: each entry's prev_hash == previous entry's entry_hash
        prev_hash = GENESIS_HASH
        for row in test_rows:
            assert row.prev_hash == prev_hash
            # entry_hash should be non-empty 64-char hex
            assert len(row.entry_hash) == 64
            int(row.entry_hash, 16)  # valid hex
            prev_hash = row.entry_hash

        # Verify all hashes are unique
        all_hashes = [r.entry_hash for r in test_rows]
        assert len(set(all_hashes)) == 5

    @pytest.mark.asyncio
    async def test_verify_chain_passes_for_valid_chain(self, db_session, client):
        """verify-chain 对正确链返回 valid=true。"""
        from app.models.audit_log_models import AuditLogEntry

        project_id = str(uuid.uuid4())

        prev_hash = GENESIS_HASH
        for i in range(3):
            # Use naive datetime to match SQLite round-trip behavior
            ts = datetime(2024, 2, i + 1)
            user_id = str(uuid.uuid4())
            action_type = f"verify_test_{i}"
            object_id = str(uuid.uuid4())
            payload = {"project_id": project_id}
            payload_json = json.dumps(payload, sort_keys=True, ensure_ascii=False)

            # Compute hash using the same ts.isoformat() that verify-chain will use
            entry_hash = worker_compute_hash(
                ts.isoformat(), user_id, action_type, object_id, payload_json, prev_hash
            )

            entry = AuditLogEntry(
                id=uuid.uuid4(),
                ts=ts,
                user_id=uuid.UUID(user_id),
                action_type=action_type,
                object_type="test",
                object_id=uuid.UUID(object_id),
                payload=payload,
                prev_hash=prev_hash,
                entry_hash=entry_hash,
            )
            db_session.add(entry)
            prev_hash = entry_hash

        await db_session.commit()

        resp = await client.get(
            "/api/audit-logs/verify-chain",
            params={"project_id": project_id},
        )

        assert resp.status_code == 200
        data = resp.json()
        if "data" in data:
            data = data["data"]
        assert data["valid"] is True
        assert data["entries_checked"] == 3

    @pytest.mark.asyncio
    async def test_verify_chain_detects_tampered_entry(self, db_session, client):
        """篡改一条后 verify-chain 检出断链。"""
        from app.models.audit_log_models import AuditLogEntry
        from sqlalchemy import update

        project_id = str(uuid.uuid4())

        prev_hash = GENESIS_HASH
        entry_ids = []
        for i in range(3):
            # Use naive datetime to match SQLite round-trip
            ts = datetime(2024, 3, i + 1)
            user_id = str(uuid.uuid4())
            action_type = f"tamper_test_{i}"
            object_id = str(uuid.uuid4())
            payload = {"project_id": project_id, "seq": i}
            payload_json = json.dumps(payload, sort_keys=True, ensure_ascii=False)

            entry_hash = worker_compute_hash(
                ts.isoformat(), user_id, action_type, object_id, payload_json, prev_hash
            )

            eid = uuid.uuid4()
            entry_ids.append(eid)
            entry = AuditLogEntry(
                id=eid,
                ts=ts,
                user_id=uuid.UUID(user_id),
                action_type=action_type,
                object_type="test",
                object_id=uuid.UUID(object_id),
                payload=payload,
                prev_hash=prev_hash,
                entry_hash=entry_hash,
            )
            db_session.add(entry)
            prev_hash = entry_hash

        await db_session.commit()

        # Tamper with the second entry's payload
        await db_session.execute(
            update(AuditLogEntry)
            .where(AuditLogEntry.id == entry_ids[1])
            .values(payload={"project_id": project_id, "seq": 999, "tampered": True})
        )
        await db_session.commit()

        resp = await client.get(
            "/api/audit-logs/verify-chain",
            params={"project_id": project_id},
        )

        assert resp.status_code == 200
        data = resp.json()
        if "data" in data:
            data = data["data"]
        assert data["valid"] is False
        assert "broken_at_entry_id" in data

    @pytest.mark.asyncio
    async def test_verify_chain_empty_returns_valid(self, client):
        """空链返回 valid=true, entries_checked=0。"""
        resp = await client.get(
            "/api/audit-logs/verify-chain",
            params={"project_id": str(uuid.uuid4())},
        )

        assert resp.status_code == 200
        data = resp.json()
        if "data" in data:
            data = data["data"]
        assert data["valid"] is True
        assert data["entries_checked"] == 0
