"""追加参数从两个提交入口进入 ImportJob.options，并在激活时再次锁定基准。"""
from __future__ import annotations

import uuid
from inspect import signature
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

from app.models.audit_platform_models import TbAuxBalance, TbAuxLedger, TbBalance, TbLedger
from app.models.dataset_models import (
    ActivationRecord,
    ImportArtifact,
    ImportEventOutbox,
    ImportJob,
    LedgerDataset,
    DatasetStatus,
)
from app.services.dataset_service import DatasetService
from app.services.import_artifact_service import ImportArtifactService
from app.services.import_job_runner import ImportJobRunner
from app.services.import_job_service import ImportJobService
from app.services.import_queue_service import ImportQueueService
from app.services.ledger_dataset_merge import BaseDatasetChangedError
from app.services.ledger_import.orchestrator import ImportOrchestrator
from app.services.ledger_import_application_service import LedgerImportApplicationService
from app.routers import ledger_data as ledger_data_router
from tests.advanced_query_linkage.builder_tables import create_tables_with_closure

PROJECT = uuid.UUID("22222222-3333-4444-5555-666666666666")
USER = uuid.UUID("33333333-4444-5555-6666-777777777777")
YEAR = 2025


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    seeds = (
        LedgerDataset.__table__,
        ImportJob.__table__,
        ImportArtifact.__table__,
        ActivationRecord.__table__,
        ImportEventOutbox.__table__,
        TbBalance.__table__,
        TbLedger.__table__,
        TbAuxBalance.__table__,
        TbAuxLedger.__table__,
    )
    async with engine.begin() as conn:
        await conn.run_sync(create_tables_with_closure, seeds)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _active(db: AsyncSession) -> LedgerDataset:
    dataset = LedgerDataset(
        id=uuid.uuid4(),
        project_id=PROJECT,
        year=YEAR,
        status=DatasetStatus.active,
        source_type="test",
    )
    db.add(dataset)
    await db.flush()
    return dataset


@pytest.mark.asyncio
async def test_legacy_submit_freezes_base_and_keeps_user_mapping(monkeypatch, db: AsyncSession):
    base = await _active(db)

    async def fake_sources(**_kwargs):
        return "upload-token", [("总账.xlsx", b"x")]

    async def fake_lock(*_args, **_kwargs):
        return True, "ok", None

    async def no_artifact(*_args, **_kwargs):
        return None

    monkeypatch.setattr(LedgerImportApplicationService, "resolve_file_sources", fake_sources)
    monkeypatch.setattr(ImportQueueService, "acquire_lock", fake_lock)
    monkeypatch.setattr(ImportArtifactService, "get_by_upload_token", no_artifact)
    monkeypatch.setattr(ImportJobRunner, "enqueue", lambda _job_id: None)
    monkeypatch.setattr(
        "app.services.ledger_import_application_service.settings.LEDGER_IMPORT_IN_PROCESS_RUNNER_ENABLED",
        False,
    )
    raw_mapping = {"总账.xlsx/序时账": {"凭证号": "voucher_no"}}
    response = await LedgerImportApplicationService.submit_import_job(
        project_id=PROJECT,
        user_id=str(USER),
        db=db,
        upload_token="upload-token",
        year=YEAR,
        custom_mapping=raw_mapping,
        append_strategy="skip",
        balance_carry_confirmed=True,
    )
    job = await ImportJobService.get_job(db, uuid.UUID(response["job_id"]))
    assert job.options["append"] == {
        "strategy": "skip",
        "base_dataset_id": str(base.id),
        "balance_carry_confirmed": True,
        "no_base": False,
    }
    assert job.custom_mapping["confirmed_mappings"][0]["mappings"] == {"凭证号": "voucher_no"}


@pytest.mark.asyncio
async def test_v2_submit_freezes_same_append_contract(db: AsyncSession):
    base = await _active(db)
    result = await ImportOrchestrator.submit(
        db,
        upload_token="v2-token",
        project_id=PROJECT,
        year=YEAR,
        confirmed_mappings=[],
        file_manifest=[],
        storage_uri="local:///test",
        created_by=USER,
        append_strategy="overwrite",
        balance_carry_confirmed=False,
    )
    job = await db.get(ImportJob, result["job_id"])
    assert job.options["append"] == {
        "strategy": "overwrite",
        "base_dataset_id": str(base.id),
        "balance_carry_confirmed": False,
        "no_base": False,
    }


@pytest.mark.asyncio
async def test_first_import_records_append_intent_without_fake_base(db: AsyncSession):
    result = await ImportOrchestrator.submit(
        db,
        upload_token="first-token",
        project_id=PROJECT,
        year=YEAR,
        confirmed_mappings=[],
        file_manifest=[],
        storage_uri="local:///test",
        append_strategy="skip",
        balance_carry_confirmed=True,
    )
    job = await db.get(ImportJob, result["job_id"])
    assert job.options["append"]["no_base"] is True
    assert job.options["append"]["base_dataset_id"] is None


@pytest.mark.asyncio
async def test_activate_rechecks_frozen_base_in_same_transaction(db: AsyncSession):
    base = await _active(db)
    staged = await DatasetService.create_staged(db, PROJECT, YEAR)
    replacement = LedgerDataset(
        id=uuid.uuid4(),
        project_id=PROJECT,
        year=YEAR,
        status=DatasetStatus.active,
        source_type="other-import",
    )
    base.status = DatasetStatus.superseded
    db.add(replacement)
    await db.flush()

    with pytest.raises(BaseDatasetChangedError, match="基准版本已变化"):
        await DatasetService.activate(
            db,
            staged.id,
            expected_active_dataset_id=base.id,
        )
    assert staged.status == DatasetStatus.staged
    assert replacement.status == DatasetStatus.active


def test_runner_passes_append_options_and_commits_queue_batch_completion():
    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "app/services/import_job_runner.py").read_text(encoding="utf-8")
    assert source.count('append_options=options.get("append")') == 2
    assert "await ImportQueueService.fail_job(" in source

    tree = ast.parse(source)
    completion_blocks: list[ast.AsyncWith] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncWith):
            continue
        binds_status_db = any(
            isinstance(item.optional_vars, ast.Name) and item.optional_vars.id == "status_db"
            for item in node.items
        )
        calls_complete = any(
            isinstance(child, ast.Await)
            and isinstance(child.value, ast.Call)
            and isinstance(child.value.func, ast.Attribute)
            and child.value.func.attr == "complete_job"
            for child in ast.walk(node)
        )
        if binds_status_db and calls_complete:
            completion_blocks.append(node)

    # 旧 Smart Import 与 v2 两条路径都必须把 queue batch 的终态提交。
    assert len(completion_blocks) == 2
    for block in completion_blocks:
        complete_lines = [
            child.lineno
            for child in ast.walk(block)
            if isinstance(child, ast.Await)
            and isinstance(child.value, ast.Call)
            and isinstance(child.value.func, ast.Attribute)
            and child.value.func.attr == "complete_job"
        ]
        commit_lines = [
            child.lineno
            for child in ast.walk(block)
            if isinstance(child, ast.Await)
            and isinstance(child.value, ast.Call)
            and isinstance(child.value.func, ast.Attribute)
            and isinstance(child.value.func.value, ast.Name)
            and child.value.func.value.id == "status_db"
            and child.value.func.attr == "commit"
        ]
        assert commit_lines and max(commit_lines) > max(complete_lines)

    # 超时路径先固化 staged 失败态，再允许 fail_job 回滚自己的事务。
    assert (
        "await DatasetService.mark_failed_for_job(status_db, job.id)\n"
        "                await status_db.commit()"
    ) in source


@pytest.mark.asyncio
async def test_complete_job_releases_redis_lock_and_active_member(monkeypatch):
    redis = SimpleNamespace(
        delete=AsyncMock(),
        srem=AsyncMock(),
    )
    monkeypatch.setattr(ImportQueueService, "_get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(ImportQueueService, "_update_job_batch", AsyncMock())
    monkeypatch.setattr(ImportQueueService, "update_progress", lambda *_args, **_kwargs: None)

    await ImportQueueService.complete_job(
        PROJECT,
        uuid.uuid4(),
        SimpleNamespace(),
        message="完成",
    )

    redis.delete.assert_awaited_once()
    redis.srem.assert_awaited_once_with("import_lock:active_set", str(PROJECT))


def test_async_import_paths_never_use_memory_only_lock_release():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app"
    paths = (
        root / "services/import_job_runner.py",
        root / "services/import_queue_service.py",
        root / "services/ledger_import_application_service.py",
        root / "routers/ledger_datasets.py",
    )
    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert "ImportQueueService.release_lock(" not in source, path


def test_both_engines_call_shared_merge_and_recheck_at_activation():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app/services"
    pipeline = (root / "ledger_import/pipeline.py").read_text(encoding="utf-8")
    smart = (root / "smart_import_engine.py").read_text(encoding="utf-8")
    append_stage = (root / "ledger_import/append_stage.py").read_text(encoding="utf-8")
    assert "from .append_stage import expected_base_id, prepare_staged_append" in pipeline
    assert "from app.services.ledger_dataset_merge import merge_into_staged" in append_stage
    assert "from app.services.ledger_dataset_voucher_diff import build_and_store_voucher_diff" in append_stage
    assert "expected_active_dataset_id=expected_base_id(append_options)" in pipeline
    assert "from app.services.ledger_dataset_merge import merge_into_staged" in smart
    assert "from app.services.ledger_dataset_voucher_diff import build_and_store_voucher_diff" in smart
    assert "expected_active_dataset_id=" in smart
    assert "apply_incremental" not in (
        Path(__file__).resolve().parents[1] / "app/routers/ledger_import_v2.py"
    ).read_text(encoding="utf-8")


def _permission(handler) -> str | None:
    default = signature(handler).parameters["current_user"].default
    dependency = getattr(default, "dependency", None)
    for cell in getattr(dependency, "__closure__", None) or ():
        if cell.cell_contents in {"readonly", "edit", "review"}:
            return cell.cell_contents
    return None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("strategy", "inherited", "skipped", "overwritten"),
    [
        ("skip", [1, 2, 3], [3], []),
        ("overwrite", [1, 2], [], [3]),
    ],
)
async def test_incremental_detect_reports_four_month_groups(
    monkeypatch, strategy, inherited, skipped, overwritten
):
    async def existing(*_args, **_kwargs):
        return {1, 2, 3}

    monkeypatch.setattr(ledger_data_router, "detect_existing_periods", existing)
    result = await ledger_data_router.detect_incremental(
        PROJECT,
        ledger_data_router.IncrementalDetectRequest(
            year=YEAR,
            file_periods=[3, 4],
            overlap_strategy=strategy,
        ),
        SimpleNamespace(),
        SimpleNamespace(),
    )
    assert result["new_periods"] == [4]
    assert result["inherited_periods"] == inherited
    assert result["skipped_file_periods"] == skipped
    assert result["overwritten_periods"] == overwritten


@pytest.mark.asyncio
async def test_retired_incremental_apply_always_returns_410_without_db():
    with pytest.raises(HTTPException) as exc:
        await ledger_data_router.apply_incremental_endpoint(
            PROJECT,
            ledger_data_router.IncrementalApplyRequest(year=YEAR, file_periods=[12]),
            SimpleNamespace(),
            None,
        )
    assert exc.value.status_code == 410
    assert exc.value.detail["error_code"] == "INCREMENTAL_APPLY_RETIRED"
    assert _permission(ledger_data_router.get_ledger_summary) == "readonly"
    assert _permission(ledger_data_router.detect_incremental) == "readonly"
    assert _permission(ledger_data_router.apply_incremental_endpoint) == "edit"


def test_destructive_apply_service_is_deleted():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "app/services/ledger_data_service.py").read_text(encoding="utf-8")
    assert "async def apply_incremental(" not in source
    assert '"apply_incremental"' not in source
