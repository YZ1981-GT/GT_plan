"""附件↔底稿关联收敛 — Wave 0 characterization + 幂等基础测试

spec: attachment-workpaper-linkage-convergence

Task 1.1（characterization 基线）锁定 Wave 0 内**保持不变**的既有行为，作为零回归基线：
  - ``AttachmentLinkService.link_attachment_to_workpaper``：``UPDATE attachments SET
    reference_type='working_paper', reference_id=`` （1:1 覆盖；Wave 1 起额外双写权威链表，
    见 ``test_attachment_wp_linkage_wave1.py``）。
  - ``get_wp_attachments``：Wave 0 只 join 链表；Wave 1 起返回 ``{items}`` envelope 且
    ∪ reference（见 Wave 1 测试）。本文件仍断言「有链行可读」；reference-only 可见性
    改由 Wave 1 覆盖。
  - ``associate_with_wp`` 的返回结构（id/attachment_id/wp_id/association_type/notes）。

Task 1.2（幂等基础）：
  - ``associate_with_wp`` 历史**无去重**（连续两次同 (att,wp) → 两行）。Wave 0 Task 1.2
    有意将其改为委托幂等 ``ensure_wp_link`` → 连续两次同 (att,wp) 只一行。故本文件
    **不再**把「两行」当作永久不变量断言（那是被本 spec 有意取代的旧行为，仅在此
    docstring 记录），改为断言新的去重行为，见 ``TestEnsureWpLinkIdempotent``。
  - V133 迁移：存量去重（保留最早）+ ``uq_awp_attachment_wp`` 唯一索引生效 + 幂等重跑。

DB fixture 沿用现有 attachment 测试（test_attachment_versioning.py）的 SQLite 内存 +
PG 类型兼容 shim 用法：只建所需表 + ``SQLiteTypeCompiler.visit_JSONB = visit_JSON``。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.migration_runner import MigrationRunner
from app.models.attachment_models import Attachment, AttachmentWorkingPaper
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User
from app.services.attachment_service import AttachmentService
from app.services.process_record_service import AttachmentLinkService

# PG JSONB → SQLite JSON 兼容 shim（Attachment 有 JSONB 列 metadata_missing）
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
_V133 = _MIGRATIONS_DIR / "V133__attachment_wp_link_unique.sql"

_CORE_TABLES = [
    User.__table__,
    Project.__table__,
    Attachment.__table__,
    AttachmentWorkingPaper.__table__,
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
    project = Project(
        id=project_id,
        name="附件关联收敛测试",
        client_name="测试客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.execution,
        created_by=user_id,
    )
    db_session.add(project)
    await db_session.commit()
    return {"project_id": project_id, "user_id": user_id}


async def _new_attachment(svc: AttachmentService, project_id: uuid.UUID, name: str = "证据.pdf") -> uuid.UUID:
    att = await svc.create_attachment(
        project_id,
        {"file_name": name, "file_path": f"/storage/{name}", "file_type": "pdf", "file_size": 100},
    )
    await svc.db.flush()
    return uuid.UUID(att["id"])


async def _raw_insert_attachment(db: AsyncSession, att_id: uuid.UUID, project_id: uuid.UUID) -> None:
    """以字符串形式直接插入一条 attachment。

    ``link_attachment_to_workpaper`` 走 raw SQL ``WHERE id = :att_id``（绑 ``str(uuid)`` 的
    dashed 表征）。真实 PG16 下 id 为原生 uuid，该 WHERE 直接命中；但 SQLite 把 PG
    ``UUID(as_uuid=True)`` 以 32 位 hex 存储，与 dashed 字符串比较不一致（纯测试环境
    artifact，非主代码 bug）。故本 helper 以 dashed 字符串直接插入，使 raw 关联路径的
    表征在 SQLite 下自洽，忠实复现该 SQL 语义。
    """
    await db.execute(
        sa.text(
            "INSERT INTO attachments (id, project_id, file_name, file_path, file_type, file_size) "
            "VALUES (:id, :pid, 'e.pdf', '/e.pdf', 'pdf', 100)"
        ),
        {"id": str(att_id), "pid": str(project_id)},
    )


class TestCharacterizationBaseline:
    """Wave 0 内保持不变的既有行为基线（零回归）。"""

    @pytest.mark.asyncio
    async def test_link_attachment_updates_reference(self, db_session, seeded_db):
        """link_attachment_to_workpaper 把 attachment 的 reference 指向底稿（ORM UPDATE）。"""
        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"])
        wp_id = uuid.uuid4()

        ok = await AttachmentLinkService().link_attachment_to_workpaper(db_session, att_id, wp_id)
        assert ok is True
        await db_session.commit()

        att = (
            await db_session.execute(sa.select(Attachment).where(Attachment.id == att_id))
        ).scalar_one()
        assert att.reference_type == "working_paper"
        assert att.reference_id == wp_id

    @pytest.mark.asyncio
    async def test_reference_only_without_link_row_baseline_via_orm(self, db_session, seeded_db):
        """仅 ORM 写 reference、无链行：Wave 0 时代反查不可见；Wave 1 起可见。

        本用例改为断言 **Wave 1 修复后** 的目标行为（reference-only 可见），避免与
        ``test_attachment_wp_linkage_wave1`` 重复锁死旧 gap。若需回看旧 gap，见该文件
        提交历史 / Wave 0 docstring。
        """
        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"])
        wp_id = uuid.uuid4()

        await db_session.execute(
            sa.update(Attachment)
            .where(Attachment.id == att_id)
            .values(reference_type="working_paper", reference_id=wp_id)
        )
        await db_session.commit()

        result = await svc.get_wp_attachments(wp_id)
        items = result["items"] if isinstance(result, dict) else result
        assert len(items) == 1
        assert items[0]["id"] == str(att_id)
        assert items[0].get("source") == "referenced"

    @pytest.mark.asyncio
    async def test_get_wp_attachments_reads_link_table(self, db_session, seeded_db):
        """有链行时 get_wp_attachments 返回该附件（join attachment_working_paper）。"""
        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"])
        wp_id = uuid.uuid4()

        await svc.associate_with_wp(att_id, wp_id)
        await db_session.commit()

        result = await svc.get_wp_attachments(wp_id)
        visible = result["items"] if isinstance(result, dict) else result
        assert len(visible) == 1
        assert visible[0]["id"] == str(att_id)

    @pytest.mark.asyncio
    async def test_associate_return_structure_preserved(self, db_session, seeded_db):
        """associate_with_wp 返回结构（改委托 ensure_wp_link 后签名/结构不变）。"""
        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"])
        wp_id = uuid.uuid4()

        link = await svc.associate_with_wp(att_id, wp_id, "evidence", "审计证据")
        assert set(link.keys()) == {"id", "attachment_id", "wp_id", "association_type", "notes"}
        assert link["attachment_id"] == str(att_id)
        assert link["wp_id"] == str(wp_id)
        assert link["association_type"] == "evidence"
        assert link["notes"] == "审计证据"


class TestEnsureWpLinkIdempotent:
    """Task 1.2：ensure_wp_link 幂等 + associate 委托后去重。"""

    @pytest.mark.asyncio
    async def test_ensure_wp_link_idempotent_single_row(self, db_session, seeded_db):
        """连续两次 ensure_wp_link 同 (att,wp) → 链表只一行，且两次返回同一 id。"""
        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"])
        wp_id = uuid.uuid4()

        first = await svc.ensure_wp_link(att_id, wp_id, association_type="evidence")
        second = await svc.ensure_wp_link(att_id, wp_id, association_type="evidence")
        assert first["id"] == second["id"]

        cnt = (
            await db_session.execute(
                sa.select(sa.func.count())
                .select_from(AttachmentWorkingPaper)
                .where(
                    AttachmentWorkingPaper.attachment_id == att_id,
                    AttachmentWorkingPaper.wp_id == wp_id,
                )
            )
        ).scalar()
        assert cnt == 1

    @pytest.mark.asyncio
    async def test_associate_with_wp_now_idempotent(self, db_session, seeded_db):
        """associate_with_wp 改委托 ensure_wp_link 后：连续两次同 (att,wp) 只一行。

        （历史行为为两行；Wave 0 Task 1.2 有意去重。）
        """
        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"])
        wp_id = uuid.uuid4()

        a = await svc.associate_with_wp(att_id, wp_id)
        b = await svc.associate_with_wp(att_id, wp_id)
        assert a["id"] == b["id"]

        cnt = (
            await db_session.execute(
                sa.select(sa.func.count())
                .select_from(AttachmentWorkingPaper)
                .where(
                    AttachmentWorkingPaper.attachment_id == att_id,
                    AttachmentWorkingPaper.wp_id == wp_id,
                )
            )
        ).scalar()
        assert cnt == 1

    @pytest.mark.asyncio
    async def test_ensure_wp_link_updates_type_and_notes_on_existing(self, db_session, seeded_db):
        """已存在链行时，非空 association_type / 非 None notes 更新既有行（不新增）。"""
        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"])
        wp_id = uuid.uuid4()

        first = await svc.ensure_wp_link(att_id, wp_id, association_type="evidence", notes="初版")
        updated = await svc.ensure_wp_link(att_id, wp_id, association_type="support", notes="改后")
        assert updated["id"] == first["id"]
        assert updated["association_type"] == "support"
        assert updated["notes"] == "改后"

        cnt = (
            await db_session.execute(
                sa.select(sa.func.count()).select_from(AttachmentWorkingPaper)
            )
        ).scalar()
        assert cnt == 1

    @pytest.mark.asyncio
    async def test_ensure_wp_link_none_notes_preserves_existing(self, db_session, seeded_db):
        """notes 传 None 时不覆盖既有 notes（不把既有值抹为空）。"""
        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"])
        wp_id = uuid.uuid4()

        await svc.ensure_wp_link(att_id, wp_id, notes="保留我")
        again = await svc.ensure_wp_link(att_id, wp_id, notes=None)
        assert again["notes"] == "保留我"

    @pytest.mark.asyncio
    async def test_distinct_pairs_are_separate_rows(self, db_session, seeded_db):
        """不同 (att,wp) 对各自独立成行。"""
        svc = AttachmentService(db_session)
        att1 = await _new_attachment(svc, seeded_db["project_id"], "a.pdf")
        att2 = await _new_attachment(svc, seeded_db["project_id"], "b.pdf")
        wp1 = uuid.uuid4()
        wp2 = uuid.uuid4()

        await svc.ensure_wp_link(att1, wp1)
        await svc.ensure_wp_link(att2, wp1)  # 同 wp 不同 att
        await svc.ensure_wp_link(att1, wp2)  # 同 att 不同 wp

        cnt = (
            await db_session.execute(
                sa.select(sa.func.count()).select_from(AttachmentWorkingPaper)
            )
        ).scalar()
        assert cnt == 3

    @pytest.mark.asyncio
    async def test_ensure_wp_link_return_structure(self, db_session, seeded_db):
        """返回结构与 associate_with_wp 一致。"""
        svc = AttachmentService(db_session)
        att_id = await _new_attachment(svc, seeded_db["project_id"])
        wp_id = uuid.uuid4()
        link = await svc.ensure_wp_link(att_id, wp_id, association_type="evidence", notes="n")
        assert set(link.keys()) == {"id", "attachment_id", "wp_id", "association_type", "notes"}
        assert link["attachment_id"] == str(att_id)
        assert link["wp_id"] == str(wp_id)


class TestV133Migration:
    """V133：存量去重 + uq_awp_attachment_wp 唯一索引生效 + 幂等重跑。"""

    @staticmethod
    def _insert_link(link_id, att_id, wp_id, created_at: str) -> str:
        return (
            "INSERT INTO attachment_working_paper "
            "(id, attachment_id, wp_id, association_type, created_at) "
            f"VALUES ('{link_id}', '{att_id}', '{wp_id}', 'evidence', '{created_at}')"
        )

    @pytest.mark.asyncio
    async def test_dedup_index_and_idempotent_rerun(self):
        engine = create_async_engine(TEST_DATABASE_URL, echo=False)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(
                    lambda c: Base.metadata.create_all(c, tables=_CORE_TABLES)
                )

            att1, att2, wp1 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
            keep_id, dropped_id, distinct_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

            # 存量：同 (att1,wp1) 两行（Jan 保留 / Jun 删除）+ 独立 (att2,wp1) 一行。
            async with engine.begin() as conn:
                await conn.exec_driver_sql(
                    self._insert_link(keep_id, att1, wp1, "2024-01-01 00:00:00")
                )
                await conn.exec_driver_sql(
                    self._insert_link(dropped_id, att1, wp1, "2024-06-01 00:00:00")
                )
                await conn.exec_driver_sql(
                    self._insert_link(distinct_id, att2, wp1, "2024-03-01 00:00:00")
                )

            v133_stmts = MigrationRunner._split_sql_statements(_V133.read_text(encoding="utf-8"))
            assert v133_stmts, "V133 迁移应至少含去重 DELETE + 建索引两条语句"

            # 应用 V133。
            async with engine.begin() as conn:
                for stmt in v133_stmts:
                    await conn.exec_driver_sql(stmt)

            # 去重：(att1,wp1) 仅剩最早那条；(att2,wp1) 未动；总计 2 行。
            async with engine.connect() as conn:
                dup_rows = (
                    await conn.exec_driver_sql(
                        f"SELECT id FROM attachment_working_paper "
                        f"WHERE attachment_id = '{att1}' AND wp_id = '{wp1}'"
                    )
                ).fetchall()
                assert len(dup_rows) == 1
                assert str(dup_rows[0][0]) == str(keep_id)

                total = (
                    await conn.exec_driver_sql("SELECT COUNT(*) FROM attachment_working_paper")
                ).scalar()
                assert total == 2

            # 索引生效：再插同 (att1,wp1) → 唯一约束冲突。
            with pytest.raises(IntegrityError):
                async with engine.begin() as conn:
                    await conn.exec_driver_sql(
                        self._insert_link(uuid.uuid4(), att1, wp1, "2024-09-01 00:00:00")
                    )

            # 幂等重跑：再次应用 V133 → 不报错，行数不变。
            async with engine.begin() as conn:
                for stmt in v133_stmts:
                    await conn.exec_driver_sql(stmt)
            async with engine.connect() as conn:
                total2 = (
                    await conn.exec_driver_sql("SELECT COUNT(*) FROM attachment_working_paper")
                ).scalar()
                assert total2 == 2
        finally:
            await engine.dispose()
