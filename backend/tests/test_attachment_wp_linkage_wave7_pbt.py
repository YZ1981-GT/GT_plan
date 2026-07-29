"""附件↔底稿关联收敛 — Wave 7：Property 1–8 PBT 汇总

spec: attachment-workpaper-linkage-convergence Task 8.1

汇总各波次正确性属性为 hypothesis 驱动的回归门；与
``test_attachment_wp_linkage_wave{0..6}.py`` 互补（本文件偏组合/幂等/门控）。
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.attachment_models import Attachment, AttachmentWorkingPaper
from app.models.base import Base
from app.models.confirmation_models import Confirmation, ConfirmationAttachmentLink
from app.models.core import Project, ProjectStatus, ProjectType, User
from app.services.attachment_ocr_writeback import writeback_ocr_to_linked_attachment
from app.services.attachment_service import AttachmentService
from app.services.process_record_service import AttachmentLinkService
from app.services.workpaper_attachment_stale import build_stale_info
from app.services.workpaper_evidence_requirements import (
    build_evidence_requirements,
    matches_wp_code_prefix,
    resolve_requirements_for_wp_code,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

_CORE_TABLES = [
    User.__table__,
    Project.__table__,
    Attachment.__table__,
    AttachmentWorkingPaper.__table__,
    Confirmation.__table__,
    ConfirmationAttachmentLink.__table__,
]


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.drop_all(c, tables=_CORE_TABLES))
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_CORE_TABLES))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    project_id = uuid.uuid4()
    user_id = uuid.uuid4()
    db_session.add(
        Project(
            id=project_id,
            name="Wave7 PBT",
            client_name="测试客户",
            project_type=ProjectType.annual,
            status=ProjectStatus.execution,
            created_by=user_id,
        )
    )
    await db_session.commit()
    return {"project_id": project_id, "user_id": user_id}


async def _new_attachment(
    svc: AttachmentService,
    project_id: uuid.UUID,
    *,
    name: str = "证据.pdf",
    attachment_type: str = "general",
) -> uuid.UUID:
    att = await svc.create_attachment(
        project_id,
        {
            "file_name": name,
            "file_path": f"/storage/{name}",
            "file_type": "pdf",
            "file_size": 100,
            "attachment_type": attachment_type,
        },
    )
    await svc.db.flush()
    return uuid.UUID(att["id"])


def _items(result) -> list[dict]:
    assert isinstance(result, dict) and "items" in result
    return result["items"]


async def _link_row_count(db: AsyncSession, att_id: uuid.UUID, wp_id: uuid.UUID) -> int:
    n = (
        await db.execute(
            sa.select(sa.func.count())
            .select_from(AttachmentWorkingPaper)
            .where(
                AttachmentWorkingPaper.attachment_id == att_id,
                AttachmentWorkingPaper.wp_id == wp_id,
            )
        )
    ).scalar()
    return int(n or 0)


# ─── Property 1: 双写幂等 ───────────────────────────────────────────────────


class TestProperty1DualWriteIdempotent:
    """对同一 (att, wp) 任意次序/次数 associate + linkAttachment → 权威链表仅一行。"""

    @given(
        n_associate=st.integers(min_value=1, max_value=5),
        n_link=st.integers(min_value=0, max_value=5),
        associate_first=st.booleans(),
    )
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_dual_write_single_link_row(
        self,
        db_session,
        seeded_db,
        n_associate,
        n_link,
        associate_first,
    ):
        svc = AttachmentService(db_session)
        link_svc = AttachmentLinkService()
        att_id = await _new_attachment(svc, seeded_db["project_id"])
        wp_id = uuid.uuid4()

        ops: list[str] = []
        if associate_first:
            ops.extend(["associate"] * n_associate)
            ops.extend(["link"] * n_link)
        else:
            ops.extend(["link"] * n_link)
            ops.extend(["associate"] * n_associate)

        for op in ops:
            if op == "associate":
                await svc.associate_with_wp(att_id, wp_id, association_type="evidence")
            else:
                await link_svc.link_attachment_to_workpaper(db_session, att_id, wp_id)

        await db_session.commit()
        assert await _link_row_count(db_session, att_id, wp_id) == 1

        # associate 对称双写 reference
        att = (
            await db_session.execute(sa.select(Attachment).where(Attachment.id == att_id))
        ).scalar_one()
        assert att.reference_type == "working_paper"
        assert att.reference_id == wp_id


# ─── Property 2–4: 反查去重 / reference 可见 / 来源标注 ─────────────────────


class TestProperty2to4ReverseLookup:
    @given(
        via_link=st.booleans(),
        via_ref=st.booleans(),
        via_conf=st.booleans(),
    )
    @settings(max_examples=15, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_dedupe_and_source_labels(
        self,
        db_session,
        seeded_db,
        via_link,
        via_ref,
        via_conf,
    ):
        """同一附件多来源 → 一行；source/sources 与真实来源一致。"""
        if not (via_link or via_ref or via_conf):
            via_ref = True  # 至少一种来源，保证可见

        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"])
        wp_id = uuid.uuid4()

        if via_link:
            await svc.ensure_wp_link(att_id, wp_id, association_type="evidence")
        if via_ref:
            await db_session.execute(
                sa.update(Attachment)
                .where(Attachment.id == att_id)
                .values(reference_type="working_paper", reference_id=wp_id)
            )
        if via_conf:
            conf_id = uuid.uuid4()
            db_session.add(
                Confirmation(
                    id=conf_id,
                    project_id=seeded_db["project_id"],
                    confirm_type="bank",
                    counterparty="PBT银行",
                    status="returned",
                    wp_id=wp_id,
                )
            )
            db_session.add(
                ConfirmationAttachmentLink(
                    id=uuid.uuid4(),
                    confirmation_id=conf_id,
                    attachment_id=att_id,
                    role="inbound",
                    match_status="manual",
                )
            )
        await db_session.commit()

        items = _items(await svc.get_wp_attachments(wp_id))
        matched = [i for i in items if i["id"] == str(att_id)]
        assert len(matched) == 1
        row = matched[0]
        sources = set(row["sources"])

        if via_link:
            assert "associated" in sources
            assert row["source"] == "associated"
            assert row["association_type"] == "evidence"
        elif via_ref:
            assert "referenced" in sources
            assert row["source"] == "referenced"
            assert row["association_type"] is None
        else:
            assert "confirmation" in sources
            assert row["source"] == "confirmation"
            assert row["association_type"] is None

        if via_ref:
            assert "referenced" in sources
        if via_conf:
            assert "confirmation" in sources

    @pytest.mark.asyncio
    async def test_property3_reference_only_visible(self, db_session, seeded_db):
        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"], name="仅reference.pdf")
        wp_id = uuid.uuid4()
        await db_session.execute(
            sa.update(Attachment)
            .where(Attachment.id == att_id)
            .values(reference_type="working_paper", reference_id=wp_id)
        )
        await db_session.commit()

        items = _items(await svc.get_wp_attachments(wp_id))
        assert len(items) == 1
        assert items[0]["source"] == "referenced"
        assert items[0]["sources"] == ["referenced"]


# ─── Property 5: 解除关联幂等 ───────────────────────────────────────────────


class TestProperty5UnlinkIdempotent:
    @given(extra_unlinks=st.integers(min_value=1, max_value=4))
    @settings(max_examples=12, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_unlink_idempotent(self, db_session, seeded_db, extra_unlinks):
        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"])
        wp_id = uuid.uuid4()

        await svc.ensure_wp_link(att_id, wp_id, association_type="evidence")
        await db_session.execute(
            sa.update(Attachment)
            .where(Attachment.id == att_id)
            .values(reference_type="working_paper", reference_id=wp_id)
        )
        await db_session.commit()

        first = await svc.unlink_wp_attachment(wp_id, att_id)
        await db_session.commit()
        assert first["ok"] is True
        assert first["link_removed"] == 1
        assert first["reference_cleared"] is True
        assert _items(await svc.get_wp_attachments(wp_id)) == []

        for _ in range(extra_unlinks):
            again = await svc.unlink_wp_attachment(wp_id, att_id)
            assert again["ok"] is True
            assert again["link_removed"] == 0

        assert await _link_row_count(db_session, att_id, wp_id) == 0
        att = (
            await db_session.execute(sa.select(Attachment).where(Attachment.id == att_id))
        ).scalar_one()
        assert att.reference_id is None
        assert att.reference_type is None


# ─── Property 6: 缺证据提示仅对有声明的底稿 ─────────────────────────────────


class TestProperty6EvidenceRequirementsGate:
    @given(suffix=st.sampled_from(["", "-1", "-10", "A", "B"]))
    @settings(max_examples=25, deadline=None)
    def test_declared_e1_variants(self, suffix):
        """有声明底稿：缺失全 false；配齐类型后对应项 true。"""
        wp_code = f"E1{suffix}"
        assert matches_wp_code_prefix(wp_code, "E1")
        assert resolve_requirements_for_wp_code(wp_code)

        missing = build_evidence_requirements(wp_code, [])
        assert missing is not None
        assert all(r["satisfied"] is False for r in missing)

        satisfied = build_evidence_requirements(
            wp_code,
            [
                {"attachment_type": "bank_statement", "sources": ["associated"]},
                {"attachment_type": "confirmation", "sources": ["confirmation"]},
            ],
        )
        assert satisfied is not None
        by_type = {r["type"]: r["satisfied"] for r in satisfied}
        assert by_type.get("bank_statement") is True
        assert by_type.get("confirmation") is True

    def test_undeclared_and_e10_no_false_positive(self):
        assert build_evidence_requirements("Z99", []) is None
        assert not matches_wp_code_prefix("E10", "E1")
        assert resolve_requirements_for_wp_code("E10") == []
        assert build_evidence_requirements("E10", []) is None


# ─── Property 7: OCR 回流同源 ───────────────────────────────────────────────


class TestProperty7OcrWritebackHomologous:
    @given(
        text=st.text(min_size=1, max_size=40).filter(lambda s: s.strip() != ""),
        field_key=st.sampled_from(["party_a", "amount", "contract_no"]),
        field_val=st.text(min_size=0, max_size=20),
    )
    @settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_writeback_same_fields_no_business(
        self, db_session, seeded_db, text, field_key, field_val
    ):
        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"])
        wp_id = uuid.uuid4()
        await svc.ensure_wp_link(att_id, wp_id)
        await db_session.commit()

        ok = await writeback_ocr_to_linked_attachment(
            db_session,
            attachment_id=att_id,
            wp_id=wp_id,
            ocr_text=text,
            extracted_fields={field_key: field_val},
            confidence=0.88,
        )
        await db_session.commit()
        assert ok is True

        att = (
            await db_session.execute(sa.select(Attachment).where(Attachment.id == att_id))
        ).scalar_one()
        assert att.ocr_text == text
        assert isinstance(att.ocr_fields_cache, dict)
        assert att.ocr_fields_cache.get("governed") is False
        assert att.ocr_fields_cache.get("requires_human_confirmation") is True
        assert att.ocr_fields_cache.get(field_key) == field_val
        # 不落业务字段：Attachment 无合同金额等业务列被写入
        assert not hasattr(att, "contract_amount") or getattr(att, "contract_amount", None) is None


# ─── Property 8: 兼容 + fail-open ───────────────────────────────────────────


class TestProperty8CompatFailOpen:
    @pytest.mark.asyncio
    async def test_envelope_shape_and_associate_keys(self, db_session, seeded_db):
        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"])
        wp_id = uuid.uuid4()

        link = await svc.associate_with_wp(att_id, wp_id)
        for key in ("id", "attachment_id", "wp_id", "association_type", "notes"):
            assert key in link

        result = await svc.get_wp_attachments(wp_id)
        assert set(result.keys()) >= {"items"}
        assert isinstance(result["items"], list)
        row = result["items"][0]
        for key in ("id", "file_name", "source", "sources"):
            assert key in row

    @pytest.mark.asyncio
    async def test_authority_write_fail_open(self, db_session, seeded_db):
        """ensure_wp_link 失败不阻断 linkAttachment reference 写入。"""
        svc = AttachmentService(db_session)
        link_svc = AttachmentLinkService()
        att_id = await _new_attachment(svc, seeded_db["project_id"])
        wp_id = uuid.uuid4()

        with patch.object(
            AttachmentService,
            "ensure_wp_link",
            AsyncMock(side_effect=RuntimeError("boom")),
        ):
            ok = await link_svc.link_attachment_to_workpaper(db_session, att_id, wp_id)
        await db_session.commit()
        assert ok is True

        att = (
            await db_session.execute(sa.select(Attachment).where(Attachment.id == att_id))
        ).scalar_one()
        assert att.reference_type == "working_paper"
        assert att.reference_id == wp_id

    @pytest.mark.asyncio
    async def test_stale_fail_open_returns_none(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=RuntimeError("db down"))
        info = await build_stale_info(db, wp_id=uuid.uuid4(), attachment_ids=[])
        assert info is None

    @pytest.mark.asyncio
    async def test_confirmation_lookup_fail_open(self):
        """函证 join 抛错 → 仍返回 envelope（空 items），不阻断。"""
        boom_db = AsyncMock()
        boom_svc = AttachmentService(boom_db)
        wp_id = uuid.uuid4()
        call_n = {"n": 0}

        async def fake_execute(stmt, *a, **kw):
            call_n["n"] += 1
            result = MagicMock()
            if call_n["n"] == 1:
                result.all.return_value = []
                return result
            if call_n["n"] == 2:
                result.scalars.return_value.all.return_value = []
                return result
            raise RuntimeError("conf fail")

        boom_db.execute = AsyncMock(side_effect=fake_execute)
        with patch.object(boom_svc, "_resolve_wp_code", AsyncMock(return_value=None)):
            with patch(
                "app.services.workpaper_attachment_stale.build_stale_info",
                AsyncMock(return_value=None),
            ):
                result = await boom_svc.get_wp_attachments(wp_id)

        assert "items" in result
        assert result["items"] == []
