"""底稿生成 operation service 的 SQLite async 状态机集成测试。

只验证数据库与文件状态；SQLite 不具备 PostgreSQL ``FOR UPDATE`` 行锁语义，
租约互斥用已提交租约的顺序竞争验证，不把它表述为数据库级并发证明。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import app.models  # noqa: E402, F401  注册外键目标表
from app.models.base import Base, ProjectStatus, UserRole  # noqa: E402
from app.models.core import Project, User  # noqa: E402
from app.models.procedure_models import ProcedureInstance  # noqa: E402
from app.models.workpaper_models import WorkingPaper, WpIndex  # noqa: E402
from app.models.wp_generation_models import (  # noqa: E402
    WorkpaperGenerationItem,
    WorkpaperGenerationOperation,
)
from app.services import (  # noqa: E402
    dataset_query,
    wp_generate_file,
    wp_generation_header_stage,
    wp_header_service,
    wp_template_init_service,
)
from app.services import wp_generation_operation_service as service  # noqa: E402
from app.services.procedure_scope_retention import GenerationPlan, TrimmedScope  # noqa: E402
from app.services.wp_generation_descriptors import GenerationDescriptor  # noqa: E402
from app.services.wp_generation_staging import (  # noqa: E402
    MaterializedItem,
    SourceSnapshot,
    file_sha256,
    staging_base,
    staging_root,
)
from tests._sqlite_fk import enable_sqlite_foreign_keys, with_fk_parents  # noqa: E402

pytestmark = pytest.mark.asyncio

_TABLES = with_fk_parents([
    User.__table__,
    Project.__table__,
    ProcedureInstance.__table__,
    WorkpaperGenerationOperation.__table__,
    WorkpaperGenerationItem.__table__,
    WpIndex.__table__,
    WorkingPaper.__table__,
])
_FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


@pytest.fixture
async def world(tmp_path, monkeypatch):
    storage = tmp_path / "wp_storage"
    monkeypatch.setattr(wp_template_init_service, "STORAGE_DIR", storage)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    enable_sqlite_foreign_keys(engine)
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=_TABLES))

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    actor_id = uuid.uuid4()
    project_id = uuid.uuid4()
    other_project_id = uuid.uuid4()
    async with factory() as db:
        db.add(User(
            id=actor_id,
            username="wp_generation_operation_actor",
            email="wp-generation-operation@example.com",
            hashed_password="x",
            role=UserRole.auditor,
            is_active=True,
        ))
        for pid, name in (
            (project_id, "【测试】生成操作甲"),
            (other_project_id, "【测试】生成操作乙"),
        ):
            db.add(Project(
                id=pid,
                name=name,
                client_name=name,
                status=ProjectStatus.execution,
                template_type="soe",
                report_scope="standalone",
                audit_year=2025,
            ))
        await db.commit()

    yield {
        "factory": factory,
        "actor_id": actor_id,
        "project_id": project_id,
        "other_project_id": other_project_id,
        "storage": storage,
    }
    await engine.dispose()


def _plan(*, trimmed: bool = False) -> GenerationPlan:
    scope = TrimmedScope.from_rows([
        ("D2", "not_applicable" if trimmed else "execute"),
    ])
    return GenerationPlan(
        to_create=[] if trimmed else ["D2"],
        skipped_trimmed_codes=["D2"] if trimmed else [],
        in_recycle_codes=[],
        existing_codes=[],
        scope=scope,
    )


def _patch_prepare_dependencies(monkeypatch) -> dict[str, int]:
    calls = {"descriptors": 0, "scenario": 0}

    async def fake_prepare_descriptors(
        _db,
        *,
        kind,
        project_id,
        template_set_id,
        codes,
    ):
        calls["descriptors"] += 1
        assert kind == "from_codes"
        assert project_id is not None
        assert template_set_id is None
        assert codes == ["D2"]
        return (
            _plan(),
            [GenerationDescriptor("D2", "应收账款", "D")],
            [],
            ["D2"],
        )

    async def fake_load_generation_scenario(_db, project_id):
        calls["scenario"] += 1
        assert project_id is not None
        return "normal", False

    monkeypatch.setattr(service, "_prepare_descriptors", fake_prepare_descriptors)
    monkeypatch.setattr(wp_generate_file, "load_generation_scenario", fake_load_generation_scenario)
    return calls


async def _prepare(db, world, operation_id, *, project_id=None, codes=None):
    return await service.prepare_operation(
        db,
        operation_id=operation_id,
        project_id=project_id or world["project_id"],
        actor_user_id=world["actor_id"],
        year=2025,
        kind="from_codes",
        codes=["D2"] if codes is None else codes,
    )


async def _prepare_claim_and_stage(
    db, world, operation_id, *, content=b"staged workbook", header_prepared=True,
):
    created = await _prepare(db, world, operation_id)
    assert created.action == "created"
    await db.commit()

    claimed = await service.claim_operation(db, world["project_id"], operation_id)
    assert claimed.active is False and claimed.lease_token is not None
    await db.commit()

    item = (await db.execute(
        sa.select(WorkpaperGenerationItem).where(
            WorkpaperGenerationItem.operation_id == operation_id
        )
    )).scalar_one()
    staged = staging_base(world["project_id"], operation_id, item.wp_id).with_suffix(".xlsx")
    staged.write_bytes(content)
    materialized = MaterializedItem(
        item_id=item.id,
        staging_path=str(staged),
        file_sha256=file_sha256(staged),
        from_template=True,
    )
    await service.record_materialized(
        db,
        world["project_id"],
        operation_id,
        claimed.lease_token,
        [materialized],
    )
    if header_prepared:
        item.header_prepared = True
    await db.commit()
    return claimed.lease_token, item, staged


async def test_canonical_request_distinguishes_none_from_explicit_empty_codes():
    project_id = uuid.uuid4()
    omitted = service.canonical_request(
        kind="from_codes",
        project_id=project_id,
        year=2025,
        template_set_id=None,
        codes=None,
    )
    empty = service.canonical_request(
        kind="from_codes",
        project_id=project_id,
        year=2025,
        template_set_id=None,
        codes=[],
    )

    assert omitted["codes"] == empty["codes"] == []
    assert omitted["codes_provided"] is False
    assert empty["codes_provided"] is True
    assert service.request_digest(omitted) != service.request_digest(empty)


async def test_prepare_creates_operation_and_reserved_items_without_formal_rows(world, monkeypatch):
    calls = _patch_prepare_dependencies(monkeypatch)
    operation_id = uuid.uuid4()

    async with world["factory"]() as db:
        result = await _prepare(db, world, operation_id)
        await db.commit()

        operation = await db.get(WorkpaperGenerationOperation, operation_id)
        items = (await db.execute(
            sa.select(WorkpaperGenerationItem).where(
                WorkpaperGenerationItem.operation_id == operation_id
            )
        )).scalars().all()
        index_count = await db.scalar(sa.select(sa.func.count()).select_from(WpIndex))
        paper_count = await db.scalar(sa.select(sa.func.count()).select_from(WorkingPaper))

    assert result.action == "created" and result.status == "prepared"
    assert calls == {"descriptors": 1, "scenario": 1}
    assert operation is not None
    assert operation.progress_total == 1 and operation.progress_done == 0
    assert operation.request_payload["effective_codes"] == ["D2"]
    assert operation.request_payload["scenario"] == "normal"
    assert operation.request_payload["has_foreign_currency"] is False
    assert len(items) == 1
    assert items[0].wp_code == "D2" and items[0].status == "prepared"
    assert items[0].wp_index_id and items[0].wp_id
    assert items[0].wp_index_id != items[0].wp_id
    assert index_count == paper_count == 0


async def test_prepare_replays_terminal_active_and_resumable_operations(world, monkeypatch):
    calls = _patch_prepare_dependencies(monkeypatch)
    monkeypatch.setattr(service, "_utcnow", lambda: _FIXED_NOW)
    terminal_id, active_id, resume_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    terminal_receipt = {"operation_id": str(terminal_id), "status": "succeeded", "created": 1}

    async with world["factory"]() as db:
        for operation_id in (terminal_id, active_id, resume_id):
            assert (await _prepare(db, world, operation_id)).action == "created"
        terminal = await db.get(WorkpaperGenerationOperation, terminal_id)
        active = await db.get(WorkpaperGenerationOperation, active_id)
        resume = await db.get(WorkpaperGenerationOperation, resume_id)
        assert terminal and active and resume
        terminal.status = "succeeded"
        terminal.receipt = terminal_receipt
        active.status = "materializing"
        active.lease_token = uuid.uuid4()
        active.lease_expires_at = _FIXED_NOW + timedelta(seconds=30)
        resume.status = "materialized"
        await db.commit()

        terminal_result = await _prepare(db, world, terminal_id)
        active_result = await _prepare(db, world, active_id)
        resume_result = await _prepare(db, world, resume_id)

    assert terminal_result.action == "terminal"
    assert terminal_result.status == "succeeded"
    assert terminal_result.receipt == terminal_receipt
    assert active_result.action == "active" and active_result.status == "materializing"
    assert resume_result.action == "resume" and resume_result.status == "materialized"
    assert calls == {"descriptors": 3, "scenario": 3}, "重入不得重新解析 Phase A"


async def test_prepare_rejects_payload_change_and_cross_project_operation_id_reuse(world, monkeypatch):
    calls = _patch_prepare_dependencies(monkeypatch)
    operation_id = uuid.uuid4()

    async with world["factory"]() as db:
        await _prepare(db, world, operation_id)
        await db.commit()

        with pytest.raises(service.OperationConflict, match="不同的生成请求"):
            await _prepare(db, world, operation_id, codes=["E1"])
        with pytest.raises(service.OperationConflict, match="其他生成请求"):
            await _prepare(
                db,
                world,
                operation_id,
                project_id=world["other_project_id"],
            )

    assert calls == {"descriptors": 1, "scenario": 1}, "冲突必须先于描述符读取被拒绝"


async def test_claim_excludes_live_lease_and_recovers_expired_finalizing_operation(world, monkeypatch):
    _patch_prepare_dependencies(monkeypatch)
    monkeypatch.setattr(service, "_utcnow", lambda: _FIXED_NOW)
    operation_id = uuid.uuid4()

    async with world["factory"]() as db:
        await _prepare(db, world, operation_id)
        await db.commit()

    async with world["factory"]() as first_db:
        first = await service.claim_operation(first_db, world["project_id"], operation_id)
        await first_db.commit()
    assert first.active is False and first.lease_token is not None
    assert first.status == "materializing"

    async with world["factory"]() as competing_db:
        competing = await service.claim_operation(competing_db, world["project_id"], operation_id)
        persisted = await competing_db.get(WorkpaperGenerationOperation, operation_id)
    assert competing.active is True and competing.lease_token is None
    assert persisted is not None and persisted.attempt == 1
    assert persisted.lease_token == first.lease_token

    async with world["factory"]() as expiry_db:
        expired = await expiry_db.get(WorkpaperGenerationOperation, operation_id)
        assert expired is not None
        expired.status = "finalizing"
        expired.lease_expires_at = _FIXED_NOW - timedelta(seconds=1)
        await expiry_db.commit()

    async with world["factory"]() as recovery_db:
        recovered = await service.claim_operation(recovery_db, world["project_id"], operation_id)
        await recovery_db.commit()
        operation = await recovery_db.get(WorkpaperGenerationOperation, operation_id)

    assert recovered.active is False and recovered.lease_token is not None
    assert recovered.lease_token != first.lease_token
    assert recovered.status == "materialized"
    assert operation is not None and operation.attempt == 2
    assert operation.lease_token == recovered.lease_token


async def test_source_snapshot_rejects_drift_and_record_materialized_persists_manifest(world, monkeypatch):
    _patch_prepare_dependencies(monkeypatch)
    monkeypatch.setattr(service, "_utcnow", lambda: _FIXED_NOW)
    operation_id = uuid.uuid4()
    first_fingerprint = "a" * 64

    async with world["factory"]() as db:
        await _prepare(db, world, operation_id)
        await db.commit()
        claim = await service.claim_operation(db, world["project_id"], operation_id)
        assert claim.lease_token is not None
        await db.commit()
        item = (await db.execute(
            sa.select(WorkpaperGenerationItem).where(
                WorkpaperGenerationItem.operation_id == operation_id
            )
        )).scalar_one()
        item_id, wp_id = item.id, item.wp_id

        snapshot = SourceSnapshot(
            item_id=item_id,
            source={"library_file": "templates/D2.xlsx", "revision": 7},
            fingerprint=first_fingerprint,
        )
        await service.record_source_snapshots(
            db, world["project_id"], operation_id, claim.lease_token, [snapshot]
        )
        await db.commit()

        loaded = await service.load_materialization_snapshot(
            db, world["project_id"], operation_id, claim.lease_token
        )
        assert loaded.items[0].expected_source_fingerprint == first_fingerprint
        assert loaded.items[0].library_file == "templates/D2.xlsx"

        with pytest.raises(service.OperationConflict, match="模板来源已变化：D2"):
            await service.record_source_snapshots(
                db,
                world["project_id"],
                operation_id,
                claim.lease_token,
                [SourceSnapshot(item_id, {"revision": 8}, "b" * 64)],
            )
        await db.rollback()

        persisted = await db.get(WorkpaperGenerationItem, item_id)
        assert persisted is not None
        assert persisted.template_fingerprint == first_fingerprint
        assert persisted.template_source == {"library_file": "templates/D2.xlsx", "revision": 7}

        staged = staging_base(world["project_id"], operation_id, wp_id).with_suffix(".xlsx")
        staged.write_bytes(b"materialized-D2")
        digest = file_sha256(staged)
        await service.record_materialized(
            db,
            world["project_id"],
            operation_id,
            claim.lease_token,
            [MaterializedItem(item_id, str(staged), digest, True)],
        )
        await db.commit()

    async with world["factory"]() as verify_db:
        operation = await verify_db.get(WorkpaperGenerationOperation, operation_id)
        item = await verify_db.get(WorkpaperGenerationItem, item_id)
    assert operation is not None and item is not None
    assert operation.status == "materialized"
    assert operation.progress_done == 1
    assert operation.lease_token == claim.lease_token
    assert item.status == "materialized"
    assert item.staging_path == str(staged)
    assert item.file_sha256 == digest
    assert item.from_template is True


def _patch_finalize_dependencies(monkeypatch, plan):
    async def fake_plan_generation(_db, project_id, codes):
        assert project_id is not None
        assert codes == ["D2"]
        return plan

    async def no_dataset_binding(*_args, **_kwargs):
        return None

    async def header_filled(*_args, **kwargs):
        assert Path(kwargs["path"]).is_file()
        return None

    monkeypatch.setattr(service, "plan_generation", fake_plan_generation)
    monkeypatch.setattr(dataset_query, "bind_to_active_dataset", no_dataset_binding)
    monkeypatch.setattr(wp_header_service, "fill_generated_workpaper_header", header_filled)


async def test_finalize_uses_reserved_ids_and_persists_terminal_receipt(world, monkeypatch):
    _patch_prepare_dependencies(monkeypatch)
    monkeypatch.setattr(service, "_utcnow", lambda: _FIXED_NOW)
    _patch_finalize_dependencies(monkeypatch, _plan())
    operation_id = uuid.uuid4()

    async with world["factory"]() as db:
        lease_token, prepared_item, staged = await _prepare_claim_and_stage(
            db, world, operation_id, content=b"final-D2"
        )
        reserved_item_id = prepared_item.id
        reserved_index_id = prepared_item.wp_index_id
        reserved_wp_id = prepared_item.wp_id

        terminal = await service.finalize_operation(
            db,
            project_id=world["project_id"],
            operation_id=operation_id,
            lease_token=lease_token,
        )
        await db.commit()

        operation = await db.get(WorkpaperGenerationOperation, operation_id)
        item = await db.get(WorkpaperGenerationItem, reserved_item_id)
        index = await db.get(WpIndex, reserved_index_id)
        paper = await db.get(WorkingPaper, reserved_wp_id)
        assert operation is not None and item is not None
        assert index is not None and paper is not None
        saved_receipt = dict(operation.receipt or {})

        replay = await service.finalize_operation(
            db,
            project_id=world["project_id"],
            operation_id=operation_id,
            lease_token=lease_token,
        )
        index_count = await db.scalar(sa.select(sa.func.count()).select_from(WpIndex))
        paper_count = await db.scalar(sa.select(sa.func.count()).select_from(WorkingPaper))

    expected_path = world["storage"] / str(world["project_id"]) / f"{reserved_wp_id}.xlsx"
    assert terminal["terminal"] is True and terminal["status"] == "succeeded"
    assert terminal["receipt"] == saved_receipt
    assert saved_receipt["operation_id"] == str(operation_id)
    assert saved_receipt["status"] == "succeeded"
    assert saved_receipt["created_codes"] == ["D2"]
    assert operation.status == "succeeded"
    assert operation.lease_token is None and operation.lease_expires_at is None
    assert item.status == "succeeded" and item.final_path == str(expected_path)
    assert index.id == reserved_index_id
    assert paper.id == reserved_wp_id and paper.wp_index_id == reserved_index_id
    assert Path(paper.file_path) == expected_path
    assert expected_path.read_bytes() == b"final-D2"
    assert not staged.exists()
    assert not staging_root(world["project_id"], operation_id, create=False).exists()
    assert replay["receipt"] == saved_receipt
    assert index_count == paper_count == 1, "terminal 重放不得重复创建正式行"


async def test_finalize_marks_stale_when_trim_decision_changes_after_phase_a(world, monkeypatch):
    _patch_prepare_dependencies(monkeypatch)
    monkeypatch.setattr(service, "_utcnow", lambda: _FIXED_NOW)
    _patch_finalize_dependencies(monkeypatch, _plan(trimmed=True))
    operation_id = uuid.uuid4()

    async with world["factory"]() as db:
        lease_token, prepared_item, staged = await _prepare_claim_and_stage(
            db, world, operation_id, content=b"stale-D2"
        )
        terminal = await service.finalize_operation(
            db,
            project_id=world["project_id"],
            operation_id=operation_id,
            lease_token=lease_token,
        )
        await db.commit()

        operation = await db.get(WorkpaperGenerationOperation, operation_id)
        item = await db.get(WorkpaperGenerationItem, prepared_item.id)
        index_count = await db.scalar(sa.select(sa.func.count()).select_from(WpIndex))
        paper_count = await db.scalar(sa.select(sa.func.count()).select_from(WorkingPaper))

    assert operation is not None and item is not None
    assert terminal["terminal"] is True and terminal["status"] == "stale"
    assert terminal["receipt"]["status"] == "stale"
    assert terminal["receipt"]["skipped_trimmed_codes"] == ["D2"]
    assert operation.status == "stale"
    assert operation.public_error == "程序裁剪结果已变化，请刷新生成计划后重试"
    assert operation.lease_token is None and operation.lease_expires_at is None
    assert operation.receipt == terminal["receipt"]
    assert item.status == "stale" and item.final_path is None
    assert index_count == paper_count == 0
    assert not staged.exists()
    assert not staging_root(world["project_id"], operation_id, create=False).exists()


async def test_two_prepared_operations_for_same_code_finalize_once(world, monkeypatch):
    """两次 Phase A 都看到待生成时，Phase B 项目锁内 replan 让后一操作稳定回报 existing。"""
    _patch_prepare_dependencies(monkeypatch)

    async def no_dataset_binding(*_args, **_kwargs):
        return None

    async def header_filled(*_args, **_kwargs):
        return None

    monkeypatch.setattr(dataset_query, "bind_to_active_dataset", no_dataset_binding)
    monkeypatch.setattr(wp_header_service, "fill_generated_workpaper_header", header_filled)
    first_id, second_id = uuid.uuid4(), uuid.uuid4()
    async with world["factory"]() as db:
        first_token, _, _ = await _prepare_claim_and_stage(db, world, first_id, content=b"first")
        second_token, second_item, second_stage = await _prepare_claim_and_stage(db, world, second_id, content=b"second")

        first = await service.finalize_operation(
            db, project_id=world["project_id"], operation_id=first_id, lease_token=first_token,
        )
        await db.commit()
        second = await service.finalize_operation(
            db, project_id=world["project_id"], operation_id=second_id, lease_token=second_token,
        )
        await db.commit()
        item = await db.get(WorkpaperGenerationItem, second_item.id)
        index_count = await db.scalar(sa.select(sa.func.count()).select_from(WpIndex))
        paper_count = await db.scalar(sa.select(sa.func.count()).select_from(WorkingPaper))

    assert first["receipt"]["created_codes"] == ["D2"]
    assert second["receipt"]["created_codes"] == []
    assert second["receipt"]["existing_codes"] == ["D2"]
    assert item is not None and item.status == "stale"
    assert not second_stage.exists()
    assert index_count == paper_count == 1


async def test_header_stage_uses_sibling_file_and_is_retryable_before_manifest_commit(world, monkeypatch):
    _patch_prepare_dependencies(monkeypatch)
    operation_id = uuid.uuid4()

    async def fill_header(*_args, **kwargs):
        path = Path(kwargs["path"])
        path.write_bytes(path.read_bytes() + b"-header")
        return "模板有外部链接表头"

    monkeypatch.setattr(wp_generation_header_stage, "fill_generated_workpaper_header", fill_header)
    async with world["factory"]() as db:
        token, prepared_item, original = await _prepare_claim_and_stage(
            db, world, operation_id, content=b"original", header_prepared=False,
        )
        prepared_item_id = prepared_item.id
        await wp_generation_header_stage.prepare_staged_headers(
            db, project_id=world["project_id"], operation_id=operation_id, lease_token=token,
        )
        first = await db.get(WorkpaperGenerationItem, prepared_item_id)
        assert first is not None
        header_path = Path(first.staging_path)
        assert header_path != original and original.read_bytes() == b"original"
        assert header_path.read_bytes() == b"original-header"
        await db.rollback()  # 模拟文件已写、manifest commit 前进程终止

        persisted = await db.get(WorkpaperGenerationItem, prepared_item_id)
        assert persisted is not None and persisted.header_prepared is False
        assert persisted.staging_path == str(original)
        await wp_generation_header_stage.prepare_staged_headers(
            db, project_id=world["project_id"], operation_id=operation_id, lease_token=token,
        )
        await db.commit()
        persisted = await db.get(WorkpaperGenerationItem, prepared_item_id)

    assert persisted is not None and persisted.header_prepared is True
    assert persisted.header_issue == "模板有外部链接表头"
    assert Path(persisted.staging_path) == header_path
    assert persisted.file_sha256 == file_sha256(header_path)
    assert header_path.read_bytes() == b"original-header", "重入应从未改写的原 staging 重新准备，不重复叠加"
