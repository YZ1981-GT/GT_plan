"""finalize saga 持久化 ACK ledger 判据。

Spec: custom-workpaper-template-ingestion-and-sync-closure, Task 16

## 本文件防的故障形态

`run_finalize_saga` 只接受 `InMemoryAckLedger`：进程一退，ACK 与 visibility 全丢，
publication 永远停在 PENDING_VISIBILITY ⇒ 已就绪的 instantiate 端点在真实链路里
永远拿不到 ACTIVE。

判据分五层：
1. **真落库**：`upsert` 后真表里有行（不是内存 dict）；
2. **幂等**：同幂等键重复 upsert 返回同一 ack_id，不新增行；
3. **verdict 冲突必须抛**：同幂等键换 verdict 是调用方缺陷（内存版同判据，
   而 `record_ack` 本身会静默返回既有行 —— 这里刻意更严）；
4. **resolve 只认全 ACCEPTED**：缺 ACK = PENDING、有 REJECTED = REJECTED；
5. **必需 consumer 是四个**（不是 `resolve_visibility` 默认的单 guidance）。
"""
from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.orm import Session

import app.models  # noqa: F401  —— 触发 ORM 注册
from app.models.base import Base
from app.models.guidance_handoff_ack_models import (
    ACK_ACCEPTED,
    ACK_CONSUMER_ENTRY_NAMESPACE,
    ACK_CONSUMER_GUIDANCE,
    ACK_CONSUMER_PUBLIC_SHELL,
    ACK_CONSUMER_RENDERER,
    ACK_REJECTED,
    VISIBILITY_ACTIVE,
    VISIBILITY_PENDING,
    VISIBILITY_REJECTED,
    GuidanceConsumerAck,
    GuidanceHandoffVisibility,
)
from app.services.custom_template_ingestion.durable_ack_ledger import DurableAckLedger
from app.services.custom_template_ingestion.finalize_saga import (
    FinalizeSagaError,
    REQUIRED_FINALIZE_CONSUMERS,
)

HID = "handoff-1"
HDIGEST = "a" * 64


@pytest.fixture()
def session() -> Session:
    SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
    engine = sa.create_engine("sqlite://")
    for table in (
        GuidanceConsumerAck.__table__,
        GuidanceHandoffVisibility.__table__,
    ):
        table.create(engine, checkfirst=True)
    with Session(engine) as s:
        yield s


def _accept(ledger: DurableAckLedger, consumer: str):
    return ledger.upsert(
        handoff_id=HID,
        handoff_digest=HDIGEST,
        consumer=consumer,
        consumer_version="v1",
        verdict=ACK_ACCEPTED,
    )


def _all_accept(ledger: DurableAckLedger) -> None:
    for c in REQUIRED_FINALIZE_CONSUMERS:
        _accept(ledger, c)


class TestUpsertPersists:
    def test_row_is_written(self, session: Session) -> None:
        ledger = DurableAckLedger(session)
        verdict = _accept(ledger, ACK_CONSUMER_GUIDANCE)
        session.commit()

        assert verdict.verdict == ACK_ACCEPTED
        count = session.execute(
            sa.select(sa.func.count()).select_from(GuidanceConsumerAck)
        ).scalar_one()
        assert count == 1

    def test_idempotent_returns_same_ack_id(self, session: Session) -> None:
        ledger = DurableAckLedger(session)
        first = _accept(ledger, ACK_CONSUMER_GUIDANCE)
        second = _accept(ledger, ACK_CONSUMER_GUIDANCE)
        session.commit()

        assert first.ack_id == second.ack_id
        assert session.execute(
            sa.select(sa.func.count()).select_from(GuidanceConsumerAck)
        ).scalar_one() == 1

    def test_verdict_conflict_raises(self, session: Session) -> None:
        """🔴 同幂等键换 verdict 必须抛 —— `record_ack` 本身会静默返回既有行。"""
        ledger = DurableAckLedger(session)
        _accept(ledger, ACK_CONSUMER_GUIDANCE)
        with pytest.raises(FinalizeSagaError, match="idempotency digest conflict"):
            ledger.upsert(
                handoff_id=HID,
                handoff_digest=HDIGEST,
                consumer=ACK_CONSUMER_GUIDANCE,
                consumer_version="v1",
                verdict=ACK_REJECTED,
            )

    def test_invalid_verdict_rejected(self, session: Session) -> None:
        ledger = DurableAckLedger(session)
        with pytest.raises(FinalizeSagaError, match="非法 verdict"):
            ledger.upsert(
                handoff_id=HID, handoff_digest=HDIGEST,
                consumer=ACK_CONSUMER_GUIDANCE, consumer_version="v1",
                verdict="review_pending",
            )

    def test_reason_codes_persisted(self, session: Session) -> None:
        ledger = DurableAckLedger(session)
        verdict = ledger.upsert(
            handoff_id=HID, handoff_digest=HDIGEST,
            consumer=ACK_CONSUMER_RENDERER, consumer_version="v1",
            verdict=ACK_REJECTED, reason_codes=("digest-mismatch", "schema-gap"),
        )
        session.commit()
        row = session.execute(sa.select(GuidanceConsumerAck)).scalar_one()
        assert list(row.reason_codes_json) == ["digest-mismatch", "schema-gap"]
        # 🔴 返回值也必须带 reason_codes —— 首次 upsert 走 record_ack 分支，
        # `_existing` 那条读取路径覆盖不到它（变异首轮即此存活）。
        assert verdict.reason_codes == ("digest-mismatch", "schema-gap")

    def test_idempotent_replay_keeps_reason_codes(self, session: Session) -> None:
        """幂等重放走 `_existing` 读取路径，reason_codes 不得丢成空元组。"""
        ledger = DurableAckLedger(session)
        ledger.upsert(
            handoff_id=HID, handoff_digest=HDIGEST,
            consumer=ACK_CONSUMER_RENDERER, consumer_version="v1",
            verdict=ACK_REJECTED, reason_codes=("digest-mismatch",),
        )
        replay = ledger.upsert(
            handoff_id=HID, handoff_digest=HDIGEST,
            consumer=ACK_CONSUMER_RENDERER, consumer_version="v1",
            verdict=ACK_REJECTED, reason_codes=("digest-mismatch",),
        )
        session.commit()
        assert replay.reason_codes == ("digest-mismatch",)


class TestResolve:
    def test_all_accepted_is_active(self, session: Session) -> None:
        ledger = DurableAckLedger(session)
        _all_accept(ledger)
        session.commit()
        assert ledger.resolve(handoff_id=HID, handoff_digest=HDIGEST) == VISIBILITY_ACTIVE

    def test_missing_ack_is_pending(self, session: Session) -> None:
        ledger = DurableAckLedger(session)
        _accept(ledger, ACK_CONSUMER_GUIDANCE)
        session.commit()
        assert ledger.resolve(handoff_id=HID, handoff_digest=HDIGEST) == VISIBILITY_PENDING

    def test_rejected_is_rejected(self, session: Session) -> None:
        ledger = DurableAckLedger(session)
        for c in REQUIRED_FINALIZE_CONSUMERS:
            if c == ACK_CONSUMER_PUBLIC_SHELL:
                ledger.upsert(
                    handoff_id=HID, handoff_digest=HDIGEST, consumer=c,
                    consumer_version="v1", verdict=ACK_REJECTED,
                )
            else:
                _accept(ledger, c)
        session.commit()
        assert ledger.resolve(handoff_id=HID, handoff_digest=HDIGEST) == VISIBILITY_REJECTED

    def test_required_set_is_four_consumers(self) -> None:
        """🔴 必需 consumer 是四个，不是 `resolve_visibility` 默认的单 guidance。"""
        assert set(REQUIRED_FINALIZE_CONSUMERS) == {
            ACK_CONSUMER_GUIDANCE,
            ACK_CONSUMER_RENDERER,
            ACK_CONSUMER_PUBLIC_SHELL,
            ACK_CONSUMER_ENTRY_NAMESPACE,
        }

    def test_visibility_row_written(self, session: Session) -> None:
        ledger = DurableAckLedger(session)
        _all_accept(ledger)
        ledger.resolve(handoff_id=HID, handoff_digest=HDIGEST)
        session.commit()
        row = session.execute(sa.select(GuidanceHandoffVisibility)).scalar_one()
        assert row.state == VISIBILITY_ACTIVE
        assert row.handoff_id == HID

    def test_resolve_is_idempotent(self, session: Session) -> None:
        ledger = DurableAckLedger(session)
        _all_accept(ledger)
        first = ledger.resolve(handoff_id=HID, handoff_digest=HDIGEST)
        second = ledger.resolve(handoff_id=HID, handoff_digest=HDIGEST)
        session.commit()
        assert first == second == VISIBILITY_ACTIVE
        assert session.execute(
            sa.select(sa.func.count()).select_from(GuidanceHandoffVisibility)
        ).scalar_one() == 1
