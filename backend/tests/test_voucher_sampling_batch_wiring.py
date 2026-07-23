"""抽样批次治理接线测试（voucher-sampling-hardening P0-1 激活）

Task 7 建了 V123 约束 + 状态机，但 `record_extraction_log` 从不写
idempotency_key/batch_id/status → 幂等唯一索引恒 NULL 永不触发（零去重）。
本文件验证 P0-1 接线后：
- `derive_idempotency_key` 稳定、顺序无关、凭证集合不同→键不同（纯函数）。
- `record_extraction_log` 落库时写 batch_id(uuid)/status='filled'/派生 idempotency_key。
- 同一底稿+相同凭证集合重复回填 → 返回既有记录（idempotent:True），不重复插入。

Validates: Requirements 5.1, 5.2, 5.3, 5.5
Properties: Property 9, Property 11
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from app.models.audit_platform_models import WorkpaperExtractionLog
from app.services.ledger_sampling_service import (
    ExtractionLogCreate,
    LedgerSamplingService,
    derive_idempotency_key,
)


# ─── 纯函数：derive_idempotency_key ───────────────────────────────────────────


class TestDeriveIdempotencyKey:
    def test_deterministic(self):
        wp = uuid4()
        k1 = derive_idempotency_key(wp, "voucher", "append", ["V1", "V2"])
        k2 = derive_idempotency_key(wp, "voucher", "append", ["V1", "V2"])
        assert k1 == k2
        assert len(k1) == 64  # sha256 hex

    def test_order_independent(self):
        wp = uuid4()
        k1 = derive_idempotency_key(wp, "voucher", "append", ["V1", "V2", "V3"])
        k2 = derive_idempotency_key(wp, "voucher", "append", ["V3", "V1", "V2"])
        assert k1 == k2

    def test_different_vouchers_different_key(self):
        wp = uuid4()
        k1 = derive_idempotency_key(wp, "voucher", "append", ["V1", "V2"])
        k2 = derive_idempotency_key(wp, "voucher", "append", ["V1", "V2", "V3"])
        assert k1 != k2

    def test_different_wp_different_key(self):
        k1 = derive_idempotency_key(uuid4(), "voucher", "append", ["V1"])
        k2 = derive_idempotency_key(uuid4(), "voucher", "append", ["V1"])
        assert k1 != k2

    def test_different_mode_different_key(self):
        wp = uuid4()
        k1 = derive_idempotency_key(wp, "voucher", "append", ["V1"])
        k2 = derive_idempotency_key(wp, "voucher", "replace", ["V1"])
        assert k1 != k2


# ─── record_extraction_log 接线（stateful 假会话，无需 live PG）──────────────


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    """最小可用假会话：追踪 add 的记录；execute(SELECT) 按 (wp, idem, 未撤销) 查已存记录。"""

    def __init__(self):
        self.store: list[WorkpaperExtractionLog] = []
        self._pending: WorkpaperExtractionLog | None = None
        # 预期查询的 (workpaper_id, idempotency_key)；由 record_extraction_log 的 where 决定
        self.last_lookup: tuple | None = None

    async def execute(self, stmt):
        # 简化：返回 store 中第一个未撤销且 idempotency_key 已落库的记录
        # （测试仅两次调用同键，够用）
        for rec in self.store:
            if not rec.is_undone and rec.idempotency_key is not None:
                return _FakeResult(rec)
        return _FakeResult(None)

    def add(self, record):
        self._pending = record

    async def flush(self):
        rec = self._pending
        if rec is not None:
            if getattr(rec, "id", None) is None:
                rec.id = uuid4()
            if getattr(rec, "created_at", None) is None:
                rec.created_at = datetime.now(timezone.utc)
            if getattr(rec, "is_undone", None) is None:
                rec.is_undone = False
            self.store.append(rec)
            self._pending = None

    async def rollback(self):
        self._pending = None


def _make_log(wp, vouchers):
    return ExtractionLogCreate(
        project_id=uuid4(),
        workpaper_id=wp,
        user_id=uuid4(),
        extraction_type="voucher",
        extraction_criteria={"filled_voucher_nos": vouchers},
        total_matched=len(vouchers),
        filled_count=len(vouchers),
        fill_mode="append",
    )


class TestRecordExtractionLogWiring:
    def test_insert_sets_batch_governance_fields(self):
        wp = uuid4()
        db = _FakeSession()
        res = asyncio.get_event_loop().run_until_complete(
            LedgerSamplingService.record_extraction_log(db, _make_log(wp, ["V1", "V2"]))
        )
        assert res.get("batch_id")  # 生成了 batch_id
        assert len(db.store) == 1
        rec = db.store[0]
        assert rec.status == "filled"
        assert rec.batch_id is not None
        assert rec.idempotency_key is not None
        # 幂等键与派生一致
        assert rec.idempotency_key == derive_idempotency_key(
            wp, "voucher", "append", ["V1", "V2"]
        )

    def test_duplicate_fill_is_idempotent(self):
        wp = uuid4()
        db = _FakeSession()
        loop = asyncio.get_event_loop()
        r1 = loop.run_until_complete(
            LedgerSamplingService.record_extraction_log(db, _make_log(wp, ["V1", "V2"]))
        )
        # 相同凭证集合重复回填 → 命中既有，不重复插入
        r2 = loop.run_until_complete(
            LedgerSamplingService.record_extraction_log(db, _make_log(wp, ["V2", "V1"]))
        )
        assert len(db.store) == 1  # 未重复插入
        assert r2.get("idempotent") is True
        assert r2["id"] == r1["id"]

    def test_no_voucher_nos_no_idempotency_key(self):
        # 无 filled_voucher_nos → 不派生幂等键（向后兼容，key 为 NULL 不参与去重）
        wp = uuid4()
        db = _FakeSession()
        log = ExtractionLogCreate(
            project_id=uuid4(),
            workpaper_id=wp,
            user_id=uuid4(),
            extraction_type="voucher",
            extraction_criteria={},
            total_matched=0,
            filled_count=0,
            fill_mode="append",
        )
        asyncio.get_event_loop().run_until_complete(
            LedgerSamplingService.record_extraction_log(db, log)
        )
        assert len(db.store) == 1
        assert db.store[0].idempotency_key is None
        assert db.store[0].batch_id is not None  # batch_id 仍生成

    def test_invalid_status_rejected(self):
        wp = uuid4()
        db = _FakeSession()
        log = _make_log(wp, ["V1"])
        log.status = "bogus"
        import pytest

        with pytest.raises(ValueError):
            asyncio.get_event_loop().run_until_complete(
                LedgerSamplingService.record_extraction_log(db, log)
            )
