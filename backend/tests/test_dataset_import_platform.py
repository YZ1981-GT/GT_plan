import uuid
from inspect import signature

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

from app.models.base import Base
import app.models.core  # noqa: F401
import app.models.audit_platform_models  # noqa: F401
import app.models.dataset_models  # noqa: F401
from app.models.audit_platform_models import AccountChart, AccountCategory, AccountDirection, AccountSource, TbAuxBalance, TbBalance
from app.models.dataset_models import DatasetStatus, JobStatus
from app.services.dataset_query import get_active_filter
from app.services.dataset_service import DatasetService
from app.services.import_job_service import ImportJobService
from app.services.import_job_runner import ImportJobRunner
from app.services.import_queue_service import ImportQueueService
from app.services.import_artifact_service import ImportArtifactService
from app.services.import_validation_service import ImportValidationService
from app.services.import_intelligence import enhance_column_mapping
from app.services.ledger_import_application_service import LedgerImportApplicationService
from app.routers import ledger_datasets, ledger_penetration
from app.routers import mapping as mapping_router
from app.services import account_chart_service
from app.services import mapping_service
from app.services.drilldown_service import DrilldownService


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def _project_permission_for_route(handler) -> str | None:
    default = signature(handler).parameters["current_user"].default
    dependency = getattr(default, "dependency", None)
    closure = getattr(dependency, "__closure__", None) or []
    for cell in closure:
        value = cell.cell_contents
        if value in {"readonly", "edit", "review"}:
            return value
    return None


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_import_job_state_machine(db_session: AsyncSession):
    project_id = uuid.uuid4()
    job = await ImportJobService.create_job(db_session, project_id=project_id, year=2024)

    await ImportJobService.transition(db_session, job.id, JobStatus.queued)
    await ImportJobService.transition(db_session, job.id, JobStatus.running, progress_pct=10)
    await ImportJobService.set_progress(db_session, job.id, progress_pct=55, progress_message="写入中")
    loaded = await ImportJobService.get_job(db_session, job.id)

    assert loaded is not None
    assert loaded.status == JobStatus.running
    assert loaded.progress_pct == 55


@pytest.mark.asyncio
async def test_import_job_claim_is_single_consumer(db_session: AsyncSession):
    project_id = uuid.uuid4()
    job = await ImportJobService.create_job(db_session, project_id=project_id, year=2024)
    await ImportJobService.transition(db_session, job.id, JobStatus.queued)
    await db_session.commit()

    claimed = await ImportJobService.claim_queued_job(db_session, job.id)
    await db_session.commit()
    claimed_again = await ImportJobService.claim_queued_job(db_session, job.id)

    assert claimed is not None
    assert claimed.status == JobStatus.running
    assert claimed_again is None


def test_sharedfs_artifact_materialize_requires_accessible_manifest(tmp_path):
    missing_bundle = tmp_path / "missing"
    with pytest.raises(HTTPException) as missing_exc:
        ImportArtifactService.materialize_bundle(
            f"sharedfs://{missing_bundle.as_posix()}",
            upload_token="token",
        )
    assert missing_exc.value.status_code == 503
    assert "sharedfs" in str(missing_exc.value.detail)

    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    with pytest.raises(HTTPException) as manifest_exc:
        ImportArtifactService.materialize_bundle(
            f"sharedfs://{bundle_dir.as_posix()}",
            upload_token="token",
        )
    assert manifest_exc.value.status_code == 503
    assert "manifest.json" in str(manifest_exc.value.detail)


@pytest.mark.asyncio
async def test_dataset_activation_and_rollback_toggle_visibility(db_session: AsyncSession):
    project_id = uuid.uuid4()
    previous = await DatasetService.create_staged(db_session, project_id=project_id, year=2024)
    await DatasetService.activate(db_session, previous.id)
    current = await DatasetService.create_staged(db_session, project_id=project_id, year=2024)

    db_session.add_all([
        TbBalance(
            project_id=project_id,
            year=2024,
            company_code="001",
            account_code="1001",
            account_name="现金",
            dataset_id=previous.id,
            is_deleted=True,
        ),
        TbBalance(
            project_id=project_id,
            year=2024,
            company_code="001",
            account_code="1002",
            account_name="银行",
            dataset_id=current.id,
            is_deleted=True,
        ),
        AccountChart(
            project_id=project_id,
            account_code="1001",
            account_name="现金",
            direction=AccountDirection.debit,
            level=1,
            category=AccountCategory.asset,
            source=AccountSource.client,
            dataset_id=previous.id,
            is_deleted=True,
        ),
    ])

    await DatasetService.activate(db_session, current.id)
    assert previous.status == DatasetStatus.superseded
    assert current.status == DatasetStatus.active

    restored = await DatasetService.rollback(db_session, project_id, 2024)
    await db_session.flush()

    assert restored is not None
    assert restored.id == previous.id
    assert current.status == DatasetStatus.rolled_back
    assert previous.status == DatasetStatus.active
    assert getattr(restored, "_rolled_back_dataset_id") == current.id


@pytest.mark.asyncio
async def test_mark_failed_cleans_staged_dataset_rows(db_session: AsyncSession):
    project_id = uuid.uuid4()
    dataset = await DatasetService.create_staged(db_session, project_id=project_id, year=2024)
    db_session.add_all([
        TbBalance(
            project_id=project_id,
            year=2024,
            company_code="001",
            account_code="1001",
            account_name="现金",
            dataset_id=dataset.id,
            is_deleted=True,
        ),
        AccountChart(
            project_id=project_id,
            account_code="1001",
            account_name="现金",
            direction=AccountDirection.debit,
            level=1,
            category=AccountCategory.asset,
            source=AccountSource.client,
            dataset_id=dataset.id,
            is_deleted=True,
        ),
    ])
    await db_session.flush()

    await DatasetService.mark_failed(db_session, dataset.id)
    await db_session.flush()

    assert dataset.status == DatasetStatus.failed
    assert (await db_session.execute(
        sa.select(sa.func.count()).select_from(TbBalance).where(TbBalance.dataset_id == dataset.id)
    )).scalar_one() == 0
    assert (await db_session.execute(
        sa.select(sa.func.count()).select_from(AccountChart).where(AccountChart.dataset_id == dataset.id)
    )).scalar_one() == 0


@pytest.mark.asyncio
async def test_mark_failed_for_job_cleans_only_staged_dataset(db_session: AsyncSession):
    project_id = uuid.uuid4()
    job = await ImportJobService.create_job(db_session, project_id=project_id, year=2024)
    staged = await DatasetService.create_staged(db_session, project_id=project_id, year=2024, job_id=job.id)
    active = await DatasetService.create_staged(db_session, project_id=project_id, year=2025, job_id=job.id)
    await DatasetService.activate(db_session, active.id)
    db_session.add_all([
        TbBalance(
            project_id=project_id,
            year=2024,
            company_code="001",
            account_code="1001",
            account_name="待清理",
            dataset_id=staged.id,
            is_deleted=True,
        ),
        TbBalance(
            project_id=project_id,
            year=2025,
            company_code="001",
            account_code="1002",
            account_name="已激活",
            dataset_id=active.id,
            is_deleted=False,
        ),
    ])
    await db_session.flush()

    cleaned = await DatasetService.mark_failed_for_job(db_session, job.id)
    await db_session.flush()

    assert cleaned == 1
    assert staged.status == DatasetStatus.failed
    assert active.status == DatasetStatus.active
    assert (await db_session.execute(
        sa.select(sa.func.count()).select_from(TbBalance).where(TbBalance.dataset_id == staged.id)
    )).scalar_one() == 0
    assert (await db_session.execute(
        sa.select(sa.func.count()).select_from(TbBalance).where(TbBalance.dataset_id == active.id)
    )).scalar_one() == 1


@pytest.mark.asyncio
async def test_active_filter_prefers_dataset_id(db_session: AsyncSession):
    project_id = uuid.uuid4()
    dataset = await DatasetService.create_staged(db_session, project_id=project_id, year=2024)
    await DatasetService.activate(db_session, dataset.id)

    table = TbBalance.__table__
    condition = await get_active_filter(db_session, table, project_id, 2024)

    assert "dataset_id" in str(condition)


@pytest.mark.asyncio
async def test_dataset_business_validation_blocks_unbalanced_voucher(db_session: AsyncSession):
    project_id = uuid.uuid4()
    dataset_id = uuid.uuid4()
    db_session.add(TbBalance(
        project_id=project_id,
        year=2024,
        company_code="001",
        account_code="1001",
        account_name="现金",
        dataset_id=dataset_id,
        opening_balance=0,
        debit_amount=100,
        credit_amount=0,
        closing_balance=1,
        is_deleted=True,
    ))
    await db_session.flush()

    findings = await ImportValidationService.run_dataset_business_validation(
        db_session,
        project_id=project_id,
        year=2024,
        dataset_id=dataset_id,
    )

    assert any(f.rule_code == "BV-04" for f in findings)


@pytest.mark.asyncio
async def test_import_queue_status_prefers_import_job(db_session: AsyncSession):
    project_id = uuid.uuid4()
    job = await ImportJobService.create_job(db_session, project_id=project_id, year=2024)
    await ImportJobService.transition(db_session, job.id, JobStatus.queued, progress_pct=5, progress_message="已排队")
    await db_session.commit()

    status = await ImportQueueService.get_status(project_id, db_session)
    assert status is not None
    assert status.get("job_id") == str(job.id)
    assert status.get("progress") == 5


@pytest.mark.asyncio
async def test_import_queue_memory_lock_does_not_block_db_lock(db_session: AsyncSession):
    from app.services.import_queue_service import _import_locks

    project_id = uuid.uuid4()
    _import_locks[str(project_id)] = {
        "batch_id": str(uuid.uuid4()),
        "user": "stale-web-process",
        "started": "2099-01-01T00:00:00",
        "progress": 10,
        "status": "processing",
        "message": "stale in-process cache",
    }

    try:
        ok, msg, batch_id = await ImportQueueService.acquire_lock(
            project_id,
            "tester",
            db_session,
            source_type="smart_import",
            file_name="ledger.csv",
            year=2024,
        )
    finally:
        _import_locks.pop(str(project_id), None)

    assert ok is True
    assert msg == "OK"
    assert batch_id is not None


def test_ledger_import_history_routes_require_project_permissions():
    readonly_routes = [
        ledger_datasets.list_datasets,
        ledger_datasets.get_active_dataset,
        ledger_datasets.list_activation_records,
        ledger_datasets.list_import_jobs,
        ledger_datasets.list_import_artifacts,
        ledger_datasets.get_import_job,
    ]
    edit_routes = [
        ledger_datasets.rollback_dataset,
        ledger_datasets.retry_import_job,
        ledger_datasets.cancel_import_job,
    ]

    for route in readonly_routes:
        assert _project_permission_for_route(route) == "readonly"
    for route in edit_routes:
        assert _project_permission_for_route(route) == "edit"


def test_mapping_routes_require_project_permissions():
    readonly_routes = [
        mapping_router.auto_suggest,
        mapping_router.get_mappings,
        mapping_router.get_completion_rate,
    ]
    edit_routes = [
        mapping_router.auto_match,
        mapping_router.save_mapping,
        mapping_router.update_mapping,
        mapping_router.batch_confirm,
    ]

    for route in readonly_routes:
        assert _project_permission_for_route(route) == "readonly"
    for route in edit_routes:
        assert _project_permission_for_route(route) == "edit"


@pytest.mark.asyncio
async def test_aux_balance_paged_uses_active_dataset_filter(db_session: AsyncSession):
    project_id = uuid.uuid4()
    year = 2024
    previous = await DatasetService.create_staged(db_session, project_id=project_id, year=year)
    await DatasetService.activate(db_session, previous.id)
    current = await DatasetService.create_staged(db_session, project_id=project_id, year=year)
    await DatasetService.activate(db_session, current.id)

    db_session.add_all([
        TbAuxBalance(
            project_id=project_id,
            year=year,
            company_code="001",
            account_code="1001",
            account_name="现金",
            aux_type="客户",
            aux_code="OLD",
            aux_name="旧版本客户",
            closing_balance=10,
            dataset_id=previous.id,
            is_deleted=False,
        ),
        TbAuxBalance(
            project_id=project_id,
            year=year,
            company_code="001",
            account_code="1001",
            account_name="现金",
            aux_type="客户",
            aux_code="NEW",
            aux_name="当前版本客户",
            closing_balance=20,
            dataset_id=current.id,
            is_deleted=False,
        ),
    ])
    await db_session.commit()

    result = await ledger_penetration.get_aux_balance_paged(
        project_id=project_id,
        year=year,
        dim_type=None,
        search=None,
        filter=None,
        page=1,
        page_size=100,
        db=db_session,
        current_user=None,
    )

    assert result["total"] == 1
    assert result["rows"][0]["aux_code"] == "NEW"


@pytest.mark.asyncio
async def test_client_chart_tree_can_use_active_dataset_filter(db_session: AsyncSession):
    project_id = uuid.uuid4()
    year = 2024
    previous = await DatasetService.create_staged(db_session, project_id=project_id, year=year)
    await DatasetService.activate(db_session, previous.id)
    current = await DatasetService.create_staged(db_session, project_id=project_id, year=year)
    await DatasetService.activate(db_session, current.id)

    db_session.add_all([
        AccountChart(
            project_id=project_id,
            account_code="1001",
            account_name="旧版本现金",
            direction=AccountDirection.debit,
            level=1,
            category=AccountCategory.asset,
            source=AccountSource.client,
            dataset_id=previous.id,
            is_deleted=False,
        ),
        AccountChart(
            project_id=project_id,
            account_code="1002",
            account_name="当前版本银行",
            direction=AccountDirection.debit,
            level=1,
            category=AccountCategory.asset,
            source=AccountSource.client,
            dataset_id=current.id,
            is_deleted=False,
        ),
    ])
    await db_session.commit()

    tree = await account_chart_service.get_client_chart_tree(project_id, db_session, year=year)

    assert [node.account_code for node in tree["asset"]] == ["1002"]
    assert tree["asset"][0].account_name == "当前版本银行"


@pytest.mark.asyncio
async def test_mapping_auto_suggest_uses_active_dataset_client_accounts(db_session: AsyncSession):
    project_id = uuid.uuid4()
    year = 2024
    previous = await DatasetService.create_staged(db_session, project_id=project_id, year=year)
    await DatasetService.activate(db_session, previous.id)
    current = await DatasetService.create_staged(db_session, project_id=project_id, year=year)
    await DatasetService.activate(db_session, current.id)

    db_session.add_all([
        AccountChart(
            project_id=project_id,
            account_code="1001",
            account_name="旧版本现金",
            direction=AccountDirection.debit,
            level=1,
            category=AccountCategory.asset,
            source=AccountSource.client,
            dataset_id=previous.id,
            is_deleted=False,
        ),
        AccountChart(
            project_id=project_id,
            account_code="1002",
            account_name="银行存款",
            direction=AccountDirection.debit,
            level=1,
            category=AccountCategory.asset,
            source=AccountSource.client,
            dataset_id=current.id,
            is_deleted=False,
        ),
        AccountChart(
            project_id=project_id,
            account_code="1002",
            account_name="银行存款",
            direction=AccountDirection.debit,
            level=1,
            category=AccountCategory.asset,
            source=AccountSource.standard,
            is_deleted=False,
        ),
    ])
    await db_session.commit()

    suggestions = await mapping_service.auto_suggest(project_id, db_session, year=year)

    assert [item.original_account_code for item in suggestions] == ["1002"]


@pytest.mark.asyncio
async def test_drilldown_aux_balance_uses_active_dataset_filter(db_session: AsyncSession):
    project_id = uuid.uuid4()
    year = 2024
    previous = await DatasetService.create_staged(db_session, project_id=project_id, year=year)
    await DatasetService.activate(db_session, previous.id)
    current = await DatasetService.create_staged(db_session, project_id=project_id, year=year)
    await DatasetService.activate(db_session, current.id)

    db_session.add_all([
        TbAuxBalance(
            project_id=project_id,
            year=year,
            company_code="001",
            account_code="1001",
            account_name="现金",
            aux_type="客户",
            aux_code="OLD",
            aux_name="旧版本客户",
            closing_balance=10,
            dataset_id=previous.id,
            is_deleted=False,
        ),
        TbAuxBalance(
            project_id=project_id,
            year=year,
            company_code="001",
            account_code="1001",
            account_name="现金",
            aux_type="客户",
            aux_code="NEW",
            aux_name="当前版本客户",
            closing_balance=20,
            dataset_id=current.id,
            is_deleted=False,
        ),
    ])
    await db_session.commit()

    rows = await DrilldownService(db_session).drill_to_aux_balance(project_id, year, "1001")

    assert [row.aux_code for row in rows] == ["NEW"]


@pytest.mark.asyncio
async def test_import_job_recover_transitions_pending(monkeypatch, db_session: AsyncSession):
    project_id = uuid.uuid4()
    job = await ImportJobService.create_job(db_session, project_id=project_id, year=2024)
    await db_session.commit()
    captured: list[uuid.UUID] = []

    def _fake_enqueue(job_id: uuid.UUID):
        captured.append(job_id)

    monkeypatch.setattr(ImportJobRunner, "enqueue", _fake_enqueue)
    local_session = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("app.services.import_job_runner.async_session", local_session)
    await ImportJobRunner.recover_jobs()

    async with local_session() as check_db:
        refreshed = await ImportJobService.get_job(check_db, job.id)
    assert refreshed is not None
    assert refreshed.status == JobStatus.queued
    assert job.id in captured


def test_smart_suggestion_contract_marks_low_confidence_content_inference():
    diagnostics = [{
        "status": "preview",
        "data_type": "ledger",
        "column_mapping": {
            "凭证号": "voucher_no",
            "摘要": "summary",
            "疑似日期列": "voucher_date",
        },
        "header_mapped": ["凭证号", "摘要"],
        "content_inferred": {"疑似日期列": "voucher_date"},
    }]

    contract = LedgerImportApplicationService._build_suggestion_contract(diagnostics)

    assert contract["suggested_mapping"] == {
        "ledger.voucher_no": "凭证号",
        "ledger.summary": "摘要",
        "ledger.voucher_date": "疑似日期列",
    }
    assert contract["confidence_by_field"]["ledger.voucher_no"] == 0.92
    assert contract["confidence_by_field"]["ledger.voucher_date"] == 0.76
    assert contract["reasons"]["ledger.voucher_date"] == "value_pattern"
    assert contract["rule_version"] == "import-rules-2026.04"
    assert contract["needs_confirmation"] == ["ledger.voucher_date"]


def test_smart_suggestion_contract_is_consistent_for_ledger_and_account_payloads():
    diagnostics = [{
        "status": "ok",
        "file": "chart.xlsx",
        "sheet": "科目表",
        "data_type": "account_chart",
        "row_count": 3,
        "column_mapping": {
            "科目编码": "account_code",
            "科目名称": "account_name",
        },
    }]
    result = {
        "total_accounts": 3,
        "data_sheets_imported": {"account_chart": 3},
        "sheet_diagnostics": diagnostics,
        "year": 2024,
    }

    account_payload = LedgerImportApplicationService.build_account_chart_result_payload(result)
    ledger_payload = LedgerImportApplicationService.build_ledger_job_result_payload(
        result,
        job_batch_id=None,
    )

    contract_fields = (
        "suggested_mapping",
        "confidence_by_field",
        "reasons",
        "rule_version",
        "needs_confirmation",
    )
    for field in contract_fields:
        assert account_payload[field] == ledger_payload[field]
    assert account_payload["suggested_mapping"] == {
        "account_chart.account_code": "科目编码",
        "account_chart.account_name": "科目名称",
    }


def test_smart_suggestion_auto_apply_threshold_comes_from_settings(monkeypatch):
    diagnostics = [{
        "status": "preview",
        "data_type": "ledger",
        "column_mapping": {"疑似日期列": "voucher_date"},
        "content_inferred": {"疑似日期列": "voucher_date"},
    }]

    monkeypatch.setattr(
        "app.services.ledger_import_application_service.settings.LEDGER_IMPORT_AUTO_APPLY_CONFIDENCE_THRESHOLD",
        0.7,
    )
    low_threshold_contract = LedgerImportApplicationService._build_suggestion_contract(diagnostics)
    assert low_threshold_contract["auto_apply_threshold"] == 0.7
    assert low_threshold_contract["needs_confirmation"] == []

    monkeypatch.setattr(
        "app.services.ledger_import_application_service.settings.LEDGER_IMPORT_AUTO_APPLY_CONFIDENCE_THRESHOLD",
        0.9,
    )
    high_threshold_contract = LedgerImportApplicationService._build_suggestion_contract(diagnostics)
    assert high_threshold_contract["auto_apply_threshold"] == 0.9
    assert high_threshold_contract["needs_confirmation"] == ["ledger.voucher_date"]


def test_enhance_column_mapping_uses_configured_auto_apply_threshold(monkeypatch):
    monkeypatch.setattr(
        "app.services.import_intelligence.settings.LEDGER_IMPORT_AUTO_APPLY_CONFIDENCE_THRESHOLD",
        0.9,
    )

    result = enhance_column_mapping(["凭证编号"], {})

    assert result["auto_apply_threshold"] == 0.9
    assert result["enhanced"] == {}
    assert result["suggestions"] == [{
        "header": "凭证编号",
        "suggested_field": "voucher_no",
        "confidence": 0.85,
        "reason": "模糊匹配",
    }]


@pytest.mark.asyncio
async def test_submit_import_job_can_leave_execution_to_external_worker(monkeypatch, db_session: AsyncSession):
    project_id = uuid.uuid4()
    user_id = str(uuid.uuid4())

    async def _fake_resolve_file_sources(**kwargs):
        return "upload-token", [("ledger.csv", b"account_code,account_name\n1001,cash\n")]

    async def _fake_acquire_lock(*args, **kwargs):
        return True, "ok", None

    async def _fake_get_artifact(*args, **kwargs):
        return None

    def _fail_enqueue(job_id):
        raise AssertionError("web process should not enqueue when in-process runner is disabled")

    monkeypatch.setattr(
        "app.services.ledger_import_application_service.settings.LEDGER_IMPORT_IN_PROCESS_RUNNER_ENABLED",
        False,
    )
    monkeypatch.setattr(
        LedgerImportApplicationService,
        "resolve_file_sources",
        _fake_resolve_file_sources,
    )
    monkeypatch.setattr(ImportQueueService, "acquire_lock", _fake_acquire_lock)
    monkeypatch.setattr(
        "app.services.import_artifact_service.ImportArtifactService.get_by_upload_token",
        _fake_get_artifact,
    )
    monkeypatch.setattr(ImportJobRunner, "enqueue", _fail_enqueue)

    response = await LedgerImportApplicationService.submit_import_job(
        project_id=project_id,
        user_id=user_id,
        db=db_session,
        upload_token="upload-token",
        year=2024,
    )

    queued_job = await ImportJobService.get_job(db_session, uuid.UUID(response["job_id"]))
    assert response["status"] == "accepted"
    assert queued_job is not None
    assert queued_job.status == JobStatus.queued


@pytest.mark.asyncio
async def test_submit_import_job_enqueues_when_in_process_runner_enabled(monkeypatch, db_session: AsyncSession):
    project_id = uuid.uuid4()
    user_id = str(uuid.uuid4())
    captured: list[uuid.UUID] = []

    async def _fake_resolve_file_sources(**kwargs):
        return "upload-token", [("ledger.csv", b"account_code,account_name\n1001,cash\n")]

    async def _fake_acquire_lock(*args, **kwargs):
        return True, "ok", None

    async def _fake_get_artifact(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "app.services.ledger_import_application_service.settings.LEDGER_IMPORT_IN_PROCESS_RUNNER_ENABLED",
        True,
    )
    monkeypatch.setattr(
        LedgerImportApplicationService,
        "resolve_file_sources",
        _fake_resolve_file_sources,
    )
    monkeypatch.setattr(ImportQueueService, "acquire_lock", _fake_acquire_lock)
    monkeypatch.setattr(
        "app.services.import_artifact_service.ImportArtifactService.get_by_upload_token",
        _fake_get_artifact,
    )
    monkeypatch.setattr(ImportJobRunner, "enqueue", lambda job_id: captured.append(job_id))

    response = await LedgerImportApplicationService.submit_import_job(
        project_id=project_id,
        user_id=user_id,
        db=db_session,
        upload_token="upload-token",
        year=2024,
    )

    assert captured == [uuid.UUID(response["job_id"])]
