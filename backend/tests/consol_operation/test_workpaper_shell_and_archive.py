"""批 6：薄底稿壳幂等创建 + 归档 provider fail-closed。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401
from app.models.attachment_models import Attachment, AttachmentWorkingPaper
from app.models.audit_log_models import AuditChainHead, AuditLogEntry
from app.models.base import Base, ProjectStatus
from app.models.consol_operation_models import ConsolOperation
from app.models.consol_workpaper_instance_models import ConsolWorkpaperInstance
from app.models.core import Project, User
from app.models.phase10_models import ConsolSnapshot
from app.models.report_generation_models import ConsolArtifact, ReportGenerationRun
from app.models.wp_optimization_models import EvidenceLink
from app.models.workpaper_models import WpIndex, WorkingPaper
from app.services.consol_archive_provider import (
    archive_items_complete,
    archive_missing_items,
    collect_consol_archive_items,
)
from app.services.consol_snapshot_service import create_consol_snapshot
from app.services.consol_workpaper_shell import (
    WP_CODE,
    ensure_consol_workpaper_shell,
    get_consol_workpaper_shell,
)

YEAR = 2025
_TABLES = [
    User.__table__, Project.__table__, ConsolOperation.__table__,
    ReportGenerationRun.__table__, ConsolArtifact.__table__,
    WpIndex.__table__, WorkingPaper.__table__,
    ConsolWorkpaperInstance.__table__,
    ConsolSnapshot.__table__, Attachment.__table__,
    AttachmentWorkingPaper.__table__, EvidenceLink.__table__,
    AuditLogEntry.__table__, AuditChainHead.__table__,
]


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABLES)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _project() -> Project:
    return Project(
        id=uuid.uuid4(), name="【测试】归档壳_2025", client_name="【测试】归档壳",
        company_code="SH", audit_year=YEAR, report_scope="consolidated",
        status=ProjectStatus.execution,
    )


def test_V268_migration_orm_and_schema_are_aligned():
    """迁移 DDL 与 ORM 三层一致：表名/列/约束/索引对齐，rollback 可逆。"""
    from pathlib import Path

    backend = Path(__file__).resolve().parents[2]
    forward = (backend / "migrations/V268__consol_workpaper_instance.sql").read_text(encoding="utf-8")
    rollback = (backend / "migrations/R268__rollback_consol_workpaper_instance.sql").read_text(
        encoding="utf-8"
    )
    assert "CREATE TABLE IF NOT EXISTS consol_workpaper_instance" in forward
    assert "DROP TABLE IF EXISTS consol_workpaper_instance" in rollback
    # ORM 列必须出现在 DDL
    ddl_cols = {
        "project_id", "year", "working_paper_id", "wp_index_id",
        "latest_operation_id", "latest_artifact_id", "version",
    }
    for col in ddl_cols:
        assert col in forward, col
        assert col in ConsolWorkpaperInstance.__table__.columns, col
    # 唯一索引对齐
    index_names = {idx.name for idx in ConsolWorkpaperInstance.__table__.indexes}
    assert index_names >= {
        "ux_consol_workpaper_instance_project_year",
        "ux_consol_workpaper_instance_working_paper",
    }
    assert "ux_consol_workpaper_instance_project_year" in forward
    assert "ux_consol_workpaper_instance_working_paper" in forward
    # version 正数约束
    assert "ck_consol_workpaper_instance_version" in forward
    # FK 指向正确表
    assert "REFERENCES working_paper(id)" in forward
    assert "REFERENCES wp_index(id)" in forward
    assert "REFERENCES consol_operation(id)" in forward
    assert "REFERENCES consol_artifact(id)" in forward


class TestWorkpaperShell:
    @pytest.mark.asyncio
    async def test_idempotent_create_and_update(self, db: AsyncSession):
        p = _project(); db.add(p); await db.commit()
        first = await ensure_consol_workpaper_shell(db, p.id)
        await db.commit()
        assert first["created"] is True
        assert first["wp_code"] == WP_CODE
        assert first["version"] == 1
        assert first["instance_id"]
        # 年度从项目 audit_year 解析
        assert first["year"] == YEAR

        second = await ensure_consol_workpaper_shell(db, p.id, artifact_path="consol://new/path.xlsx")
        await db.commit()
        assert second["created"] is False
        assert second["wp_index_id"] == first["wp_index_id"]
        assert second["working_paper_id"] == first["working_paper_id"]
        assert second["instance_id"] == first["instance_id"]
        # 只更新 file_path、未传 operation/artifact 指针 ⇒ version 不膨胀
        assert second["version"] == 1

        shell = await get_consol_workpaper_shell(db, p.id)
        assert shell is not None
        assert shell["file_path"] == "consol://new/path.xlsx"
        assert shell["instance_id"] == first["instance_id"]
        assert shell["version"] == 1
        assert shell["year"] == YEAR

    @pytest.mark.asyncio
    async def test_idempotent_repeated_call_does_not_bump_version(self, db: AsyncSession):
        """重复幂等调用（无指针变化）不应递增 version。"""
        p = _project(); db.add(p); await db.commit()
        await ensure_consol_workpaper_shell(db, p.id)
        await db.commit()
        for _ in range(3):
            result = await ensure_consol_workpaper_shell(db, p.id)
            await db.commit()
            assert result["created"] is False
            assert result["version"] == 1

    @pytest.mark.asyncio
    async def test_artifact_and_operation_association_bumps_version(self, db: AsyncSession):
        """关联新 operation / artifact 指针时 version 单调递增并落到实例行。"""
        p = _project(); db.add(p); await db.commit()
        now = datetime.now(timezone.utc)
        op = ConsolOperation(
            id=uuid.uuid4(), project_id=p.id, year=YEAR, operation_type="refresh_all",
            idempotency_key="k-assoc", idempotency_keys={}, request_hash="h" * 64,
            request_payload={}, context_json={}, version_vector={}, status="succeeded",
            revision=1, trigger_source="manual", steps=[], errors=[],
            result_refs={}, metrics={}, finished_at=now,
        )
        run = ReportGenerationRun(
            id=uuid.uuid4(), project_id=p.id, year=YEAR, trigger="manual",
            operation_id=op.id, operation_revision=1, node_key="SH:consol",
            status="succeeded", calc_version=1, row_digest="d" * 64,
            row_count=5, rows_json={}, finished_at=now,
        )
        artifact = ConsolArtifact(
            id=uuid.uuid4(), project_id=p.id, year=YEAR,
            operation_id=op.id, report_run_id=run.id, node_key="SH:consol",
            kind="consol_workpaper", status="ready", file_name="wp.xlsx",
            storage_path="consol/wp.xlsx", content_type="application/xlsx",
            size_bytes=2048, sha256="a" * 64, ready_at=now,
        )
        db.add_all([op, run, artifact]); await db.commit()

        first = await ensure_consol_workpaper_shell(db, p.id)
        await db.commit()
        assert first["version"] == 1

        # 关联 operation + artifact ⇒ version += 1，file_path 指向 artifact
        assoc = await ensure_consol_workpaper_shell(
            db, p.id, operation_id=op.id, artifact_id=artifact.id,
            artifact_path=artifact.storage_path,
        )
        await db.commit()
        assert assoc["created"] is False
        assert assoc["version"] == 2

        shell = await get_consol_workpaper_shell(db, p.id)
        assert shell["latest_operation_id"] == str(op.id)
        assert shell["latest_artifact_id"] == str(artifact.id)
        assert shell["file_path"] == "consol/wp.xlsx"
        assert shell["version"] == 2

        # 再次用相同指针调用 ⇒ 幂等不再递增
        again = await ensure_consol_workpaper_shell(
            db, p.id, operation_id=op.id, artifact_id=artifact.id,
        )
        await db.commit()
        assert again["version"] == 2

    @pytest.mark.asyncio
    async def test_explicit_year_overrides_project_audit_year(self, db: AsyncSession):
        """显式 year 入参优先于项目 audit_year。"""
        p = _project(); db.add(p); await db.commit()
        result = await ensure_consol_workpaper_shell(db, p.id, year=2024)
        await db.commit()
        assert result["year"] == 2024

    @pytest.mark.asyncio
    async def test_no_shell_returns_none(self, db: AsyncSession):
        p = _project(); db.add(p); await db.commit()
        assert await get_consol_workpaper_shell(db, p.id) is None


async def _build_core_archive(
    db: AsyncSession,
    project_id: uuid.UUID,
    *,
    with_report_workpaper: tuple[str, ...] = ("report_excel", "consol_workpaper"),
) -> tuple[ConsolOperation, ReportGenerationRun]:
    """成功 operation + 成功报表运行 + 指定 ready artifacts（不含快照/附件/审计）。"""
    now = datetime.now(timezone.utc)
    op = ConsolOperation(
        id=uuid.uuid4(), project_id=project_id, year=YEAR, operation_type="refresh_all",
        idempotency_key=f"k-{uuid.uuid4().hex[:8]}", idempotency_keys={},
        request_hash="h" * 64, request_payload={}, context_json={}, version_vector={},
        status="succeeded", revision=1, trigger_source="manual", steps=[], errors=[],
        result_refs={}, metrics={}, finished_at=now,
    )
    run = ReportGenerationRun(
        id=uuid.uuid4(), project_id=project_id, year=YEAR, trigger="manual",
        operation_id=op.id, operation_revision=1, node_key="SH:consol",
        status="succeeded", calc_version=1, row_digest="d" * 64,
        row_count=5, rows_json={}, finished_at=now,
    )
    op.result_refs = {"report_run_id": str(run.id)}
    db.add_all([op, run])
    for kind in with_report_workpaper:
        db.add(ConsolArtifact(
            id=uuid.uuid4(), project_id=project_id, year=YEAR,
            operation_id=op.id, report_run_id=run.id, node_key="SH:consol",
            kind=kind, status="ready", file_name=f"{kind}.xlsx",
            storage_path=f"consol/{kind}.xlsx", content_type="application/xlsx",
            size_bytes=1024, sha256="a" * 64, ready_at=now,
        ))
    await db.flush()
    return op, run


async def _attach_evidence_to_shell(
    db: AsyncSession, project_id: uuid.UUID, wp_id: uuid.UUID,
    *, is_deleted: bool = False,
) -> Attachment:
    """给底稿壳挂一条行级证据链接（可控制附件是否已删除）。"""
    att = Attachment(
        id=uuid.uuid4(), project_id=project_id, file_name="evidence.pdf",
        file_path=f"local://{project_id}/evidence.pdf", file_type="pdf",
        file_size=321, storage_type="local", state="available",
        is_deleted=is_deleted,
    )
    db.add(att)
    await db.flush()
    db.add(EvidenceLink(
        id=uuid.uuid4(), wp_id=wp_id, sheet_name="consol_trial",
        cell_ref="node:SH:consol/row:1001/col:consol_amount",
        attachment_id=att.id, created_by=uuid.uuid4(),
    ))
    await db.flush()
    return att


class TestArchiveProvider:
    @pytest.mark.asyncio
    async def test_no_operation_is_missing(self, db: AsyncSession):
        p = _project(); db.add(p); await db.commit()
        items = await collect_consol_archive_items(db, p.id, YEAR)
        assert not archive_items_complete(items)
        assert items[0]["status"] == "missing"
        assert items[0]["kind"] == "consol_operation"

    @pytest.mark.asyncio
    async def test_complete_archive_includes_all_required_items(self, db: AsyncSession):
        """operation + report run + 两 artifact + 签字快照 + 壳 + 附件证据 + 审计清单齐全 ⇒ complete。"""
        p = _project(); db.add(p); await db.commit()
        await _build_core_archive(db, p.id)
        shell = await ensure_consol_workpaper_shell(db, p.id)
        await _attach_evidence_to_shell(db, p.id, uuid.UUID(shell["working_paper_id"]))
        await db.commit()
        # 真实签字快照（reason=sign ⇒ 锁定 + 写 consol.snapshot.create 审计留痕）
        actor = uuid.uuid4()
        await create_consol_snapshot(db, p.id, YEAR, reason="sign", user_id=actor, enforce_gate=False)

        items = await collect_consol_archive_items(db, p.id, YEAR)
        assert archive_items_complete(items), archive_missing_items(items)
        kinds = {item["kind"]: item["status"] for item in items}
        assert kinds["consol_operation"] == "ready"
        assert kinds["report_run"] == "ready"
        assert kinds["report_excel"] == "ready"
        assert kinds["consol_workpaper"] == "ready"
        assert kinds["workpaper_shell"] == "ready"
        assert kinds["sign_snapshot"] == "ready"
        assert kinds["attachments"] == "ready"
        assert kinds["audit_manifest"] == "ready"
        # 快照项带可还原 hash；附件项带计数；审计项带链尾 hash
        snap = next(i for i in items if i["kind"] == "sign_snapshot")
        assert snap["locked"] is True and snap["hash"]
        att_item = next(i for i in items if i["kind"] == "attachments")
        assert att_item["attachment_count"] == 1
        audit = next(i for i in items if i["kind"] == "audit_manifest")
        assert audit["entry_count"] >= 1
        assert any(a.startswith("consol.") for a in audit["actions"])

    @pytest.mark.asyncio
    async def test_missing_artifact_blocks_archive(self, db: AsyncSession):
        """缺少任何 artifact 时 fail-closed。"""
        p = _project(); db.add(p); await db.commit()
        # 只建 report_excel，缺 consol_workpaper
        await _build_core_archive(db, p.id, with_report_workpaper=("report_excel",))
        await db.commit()

        items = await collect_consol_archive_items(db, p.id, YEAR)
        assert not archive_items_complete(items)
        missing = archive_missing_items(items)
        assert any("工作底稿包" in item.get("reason", "") for item in missing)

    def test_completeness_logic_fail_closed_on_any_missing(self):
        """``archive_items_complete`` / ``archive_missing_items`` 的纯判定：

        - 全 ready/not_applicable ⇒ complete；任一 missing ⇒ not complete 且进缺件清单。
        - 覆盖 artifact 缺 SHA-256 这类防御分支的信封形状（DB CHECK 保证 ready 必有 hash，
          真库走不到，这里以单元测试守住完整性判定口径）。
        """
        all_ok = [
            {"kind": "consol_operation", "status": "ready"},
            {"kind": "workpaper_shell", "status": "not_applicable"},
            {"kind": "attachments", "status": "ready"},
        ]
        assert archive_items_complete(all_ok)
        assert archive_missing_items(all_ok) == []

        with_missing = all_ok + [
            {"kind": "consol_workpaper", "status": "missing",
             "reason": "合并工作底稿包缺少 SHA-256，无法校验完整性"},
        ]
        assert not archive_items_complete(with_missing)
        missing = archive_missing_items(with_missing)
        assert len(missing) == 1 and "SHA-256" in missing[0]["reason"]

    @pytest.mark.asyncio
    async def test_missing_sign_snapshot_blocks_archive(self, db: AsyncSession):
        """归档口径（require_snapshot=True）下没有签字/锁定快照 ⇒ fail-closed。"""
        p = _project(); db.add(p); await db.commit()
        await _build_core_archive(db, p.id)
        shell = await ensure_consol_workpaper_shell(db, p.id)
        await _attach_evidence_to_shell(db, p.id, uuid.UUID(shell["working_paper_id"]))
        # 写一条审计留痕让审计项 ready，单独把快照隔离成唯一缺件
        from app.services.consol_audit_helper import log_consol_action
        await log_consol_action(
            db, user_id=uuid.uuid4(), project_id=p.id, action="consol.recalc",
            resource_type="consol_trial", resource_id=None, before=None, after={},
        )
        await db.commit()

        items = await collect_consol_archive_items(db, p.id, YEAR)
        assert not archive_items_complete(items)
        missing = archive_missing_items(items)
        assert [m["kind"] for m in missing] == ["sign_snapshot"]
        assert "签字" in missing[0]["reason"]

    @pytest.mark.asyncio
    async def test_manual_only_snapshot_still_blocks_archive(self, db: AsyncSession):
        """只有手工诊断快照（reason=manual，不锁定）时仍视为缺签字快照 ⇒ fail-closed。"""
        p = _project(); db.add(p); await db.commit()
        await _build_core_archive(db, p.id)
        await ensure_consol_workpaper_shell(db, p.id)
        await db.commit()
        await create_consol_snapshot(db, p.id, YEAR, reason="manual", user_id=uuid.uuid4())

        items = await collect_consol_archive_items(db, p.id, YEAR)
        snap = next(i for i in items if i["kind"] == "sign_snapshot")
        assert snap["status"] == "missing"
        assert not archive_items_complete(items)

    @pytest.mark.asyncio
    async def test_require_snapshot_false_marks_snapshot_not_applicable(self, db: AsyncSession):
        """诊断口径 require_snapshot=False：缺快照记 not_applicable，不构成缺件。"""
        p = _project(); db.add(p); await db.commit()
        await _build_core_archive(db, p.id)
        shell = await ensure_consol_workpaper_shell(db, p.id)
        await _attach_evidence_to_shell(db, p.id, uuid.UUID(shell["working_paper_id"]))
        from app.services.consol_audit_helper import log_consol_action
        await log_consol_action(
            db, user_id=uuid.uuid4(), project_id=p.id, action="consol.recalc",
            resource_type="consol_trial", resource_id=None, before=None, after={},
        )
        await db.commit()

        items = await collect_consol_archive_items(db, p.id, YEAR, require_snapshot=False)
        snap = next(i for i in items if i["kind"] == "sign_snapshot")
        assert snap["status"] == "not_applicable"
        assert archive_items_complete(items)

    @pytest.mark.asyncio
    async def test_corrupted_snapshot_hash_blocks_archive(self, db: AsyncSession):
        """签字快照存在但哈希被篡改 ⇒ 完整性受损 ⇒ fail-closed。"""
        p = _project(); db.add(p); await db.commit()
        await _build_core_archive(db, p.id)
        await ensure_consol_workpaper_shell(db, p.id)
        await db.commit()
        result = await create_consol_snapshot(db, p.id, YEAR, reason="sign", user_id=uuid.uuid4(), enforce_gate=False)
        # 篡改存储哈希，模拟分片/根 hash 不符
        snap_row = await db.get(ConsolSnapshot, uuid.UUID(result["id"]))
        tampered = dict(snap_row.snapshot_data)
        tampered["_hash"] = "0" * 64
        snap_row.snapshot_data = tampered
        await db.commit()

        items = await collect_consol_archive_items(db, p.id, YEAR)
        snap = next(i for i in items if i["kind"] == "sign_snapshot")
        assert snap["status"] == "missing"
        assert "哈希" in snap["reason"] or "完整性" in snap["reason"]
        assert not archive_items_complete(items)

    @pytest.mark.asyncio
    async def test_dangling_evidence_attachment_blocks_archive(self, db: AsyncSession):
        """证据链接指向已删除附件 ⇒ 清单与文件无法闭合 ⇒ fail-closed。"""
        p = _project(); db.add(p); await db.commit()
        await _build_core_archive(db, p.id)
        shell = await ensure_consol_workpaper_shell(db, p.id)
        att = await _attach_evidence_to_shell(
            db, p.id, uuid.UUID(shell["working_paper_id"]), is_deleted=True,
        )
        await db.commit()
        await create_consol_snapshot(db, p.id, YEAR, reason="sign", user_id=uuid.uuid4(), enforce_gate=False)

        items = await collect_consol_archive_items(db, p.id, YEAR)
        att_item = next(i for i in items if i["kind"] == "attachments")
        assert att_item["status"] == "missing"
        assert str(att.id) in att_item["dangling_attachment_ids"]
        assert not archive_items_complete(items)

    @pytest.mark.asyncio
    async def test_no_attachments_is_ready_not_missing(self, db: AsyncSession):
        """合并底稿允许没有附件证据：空集合记 ready（count=0），不是缺件。"""
        p = _project(); db.add(p); await db.commit()
        await _build_core_archive(db, p.id)
        await ensure_consol_workpaper_shell(db, p.id)
        await db.commit()
        await create_consol_snapshot(db, p.id, YEAR, reason="sign", user_id=uuid.uuid4(), enforce_gate=False)

        items = await collect_consol_archive_items(db, p.id, YEAR)
        att_item = next(i for i in items if i["kind"] == "attachments")
        assert att_item["status"] == "ready"
        assert att_item["attachment_count"] == 0
        assert archive_items_complete(items)

    @pytest.mark.asyncio
    async def test_missing_audit_manifest_blocks_archive(self, db: AsyncSession):
        """成功运行却零合并生命周期审计留痕 ⇒ 不可追溯 ⇒ fail-closed。"""
        p = _project(); db.add(p); await db.commit()
        await _build_core_archive(db, p.id)
        shell = await ensure_consol_workpaper_shell(db, p.id)
        await _attach_evidence_to_shell(db, p.id, uuid.UUID(shell["working_paper_id"]))
        await db.commit()
        # 有效签字快照（user_id=None ⇒ 不写审计留痕），把审计清单隔离成唯一缺件
        await create_consol_snapshot(db, p.id, YEAR, reason="sign", user_id=None, enforce_gate=False)

        items = await collect_consol_archive_items(db, p.id, YEAR)
        missing = archive_missing_items(items)
        assert [m["kind"] for m in missing] == ["audit_manifest"]
        audit = next(i for i in items if i["kind"] == "audit_manifest")
        assert audit["status"] == "missing"
        assert "留痕" in audit["reason"]

    @pytest.mark.asyncio
    async def test_no_shell_marks_shell_and_attachments_not_applicable(self, db: AsyncSession):
        """未建壳：壳与附件项都记 not_applicable（证据无挂载点），不构成缺件。"""
        p = _project(); db.add(p); await db.commit()
        await _build_core_archive(db, p.id)
        await db.commit()
        await create_consol_snapshot(db, p.id, YEAR, reason="sign", user_id=uuid.uuid4(), enforce_gate=False)

        items = await collect_consol_archive_items(db, p.id, YEAR)
        shell_item = next(i for i in items if i["kind"] == "workpaper_shell")
        att_item = next(i for i in items if i["kind"] == "attachments")
        assert shell_item["status"] == "not_applicable"
        assert att_item["status"] == "not_applicable"


class TestArchiveInventoryWiring:
    """generic 归档清单对合并 provider 的接线（archive_inventory._consol_entries / build_project_inventory）。"""

    @pytest.mark.asyncio
    async def test_standalone_project_has_no_consol_entries(self, db: AsyncSession):
        """非合并项目（standalone）不纳入合并产物清单，口径不变。"""
        from app.services.archive_inventory import _ArcNames, _consol_entries

        p = Project(
            id=uuid.uuid4(), name="【测试】单体_2025", client_name="【测试】单体",
            company_code="SH", audit_year=YEAR, report_scope="standalone",
            status=ProjectStatus.execution,
        )
        db.add(p); await db.commit()
        entries = await _consol_entries(db, p.id, _ArcNames())
        assert entries == []

    @pytest.mark.asyncio
    async def test_consolidated_missing_items_become_inventory_missing(self, db: AsyncSession):
        """合并项目缺件 ⇒ 映射成通用 InventoryEntry 的 MISSING（供 build_archive_package fail-closed）。"""
        from app.services.archive_inventory import MISSING, _ArcNames, _consol_entries

        p = _project(); db.add(p); await db.commit()  # report_scope=consolidated
        entries = await _consol_entries(db, p.id, _ArcNames())
        # 没有任何成功 operation ⇒ 至少一条 MISSING，且分类是通用的底稿数据类目
        missing = [e for e in entries if e.status == MISSING]
        assert missing
        assert all(e.category == "workpaper_data" for e in entries)
        assert any("合并运行" in e.label for e in missing)

    @pytest.mark.asyncio
    async def test_consolidated_ready_artifacts_become_file_entries(self, db: AsyncSession):
        """合并 ready artifact 映射成真文件入包项（文件缺失则 MISSING，不假成功）。"""
        from app.services.archive_inventory import MISSING, OK, SKIPPED, _ArcNames, _consol_entries

        p = _project(); db.add(p); await db.commit()
        await _build_core_archive(db, p.id)
        shell = await ensure_consol_workpaper_shell(db, p.id)
        await _attach_evidence_to_shell(db, p.id, uuid.UUID(shell["working_paper_id"]))
        await db.commit()
        await create_consol_snapshot(db, p.id, YEAR, reason="sign", user_id=uuid.uuid4(), enforce_gate=False)

        entries = await _consol_entries(db, p.id, _ArcNames())
        by_source = {e.source_id: e for e in entries}
        # 两个 artifact 是文件型入包项；真实文件未落盘 ⇒ MISSING（fail-closed，不伪装 ready）
        for src in ("consol:report_excel", "consol:consol_workpaper"):
            assert src in by_source
            assert by_source[src].status == MISSING
            assert "文件不存在" in by_source[src].reason
        # 数据/引用型 required source 记 SKIPPED（operation / snapshot / audit / shell / attachments）
        statuses = {e.source_id: e.status for e in entries}
        assert statuses["consol:consol_operation"] == SKIPPED
        assert statuses["consol:sign_snapshot"] == SKIPPED
        assert statuses["consol:audit_manifest"] == SKIPPED
        assert OK not in statuses.values()  # 本例无真实落盘文件
