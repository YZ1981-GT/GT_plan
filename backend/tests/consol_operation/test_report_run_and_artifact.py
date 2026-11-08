"""批 4：正式 report run 与不可变 artifact 的 SQLite / 纯函数闭环。"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import openpyxl
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401 - SQLite 方言兼容与模型注册
from app.models.base import Base, ProjectStatus
from app.models.consol_note_data_models import ConsolNoteData
from app.models.consol_operation_models import ConsolOperation
from app.models.consol_worksheet_data_models import ConsolWorksheetData
from app.models.consolidation_models import ConsolTrial, ConsolWorksheet
from app.models.core import Project, User
from app.models.report_generation_models import ConsolArtifact, ReportGenerationRun
from app.models.report_models import FinancialReport, FinancialReportType
from app.schemas.consol_context import ConsolContext
from app.services.consol_artifact_service import (
    ArtifactError,
    build_consol_workpaper_bytes,
    generate_reserved_artifact,
    reserve_artifact,
    resolve_artifact_path,
    verify_artifact_file,
)
from app.services.consol_report_run_service import (
    canonical_report_rows,
    materialize_consol_report_run,
    operation_input_digest,
    published_report_payload,
    report_row_digest,
    resolve_published_run,
)
from app.services.consol_version_vector import digest_payload

YEAR = 2025
VECTOR = {
    "tree_fingerprint": "a" * 64,
    "tb_digest": "b" * 64,
    "elimination_digest": "c" * 64,
    "formula_digest": "d" * 64,
    "note_mapping_digest": "e" * 64,
    "template_digest": "f" * 64,
}
_TABLES = [
    User.__table__, Project.__table__, ConsolOperation.__table__,
    ReportGenerationRun.__table__, FinancialReport.__table__, ConsolArtifact.__table__,
    ConsolWorksheetData.__table__, ConsolWorksheet.__table__, ConsolTrial.__table__, ConsolNoteData.__table__,
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


def project() -> Project:
    return Project(
        id=uuid.uuid4(), name="【测试】正式报表运行_2025", client_name="【测试】正式报表运行",
        company_code="RUN", audit_year=YEAR, report_scope="consolidated",
        status=ProjectStatus.execution, consol_lock=False,
    )


def operation(pid: uuid.UUID) -> ConsolOperation:
    now = datetime.now(timezone.utc)
    vector = {**VECTOR, "schema_version": 1, "digest": "0" * 64,
              "tree_revision": None, "recorded_tree_fingerprint": None, "worksheet_versions": {}}
    return ConsolOperation(
        id=uuid.uuid4(), project_id=pid, year=YEAR, operation_type="refresh_all",
        idempotency_key=str(uuid.uuid4()), idempotency_keys={}, request_hash="9" * 64,
        request_payload={}, context_json={}, version_vector=vector, status="running", revision=1,
        attempt=1, lease_owner=uuid.uuid4(), lease_expires_at=now + timedelta(minutes=5),
        trigger_source="manual", steps=[], errors=[], result_refs={}, metrics={},
    )


def context(pid: uuid.UUID, op_id: uuid.UUID) -> ConsolContext:
    return ConsolContext(
        project_id=pid, year=YEAR, run_id=op_id, node_key="RUN:consol",
        node_keys=("RUN:consol",), template_type="soe", report_scope="consolidated",
        tree_fingerprint="a" * 64, source_version="0" * 64,
        formula_version="d" * 64, template_version="f" * 64,
    )


def results(amount: str = "123.45") -> dict:
    return {"balance_sheet": [{
        "report_type": "balance_sheet", "row_number": 2, "row_code": "BS-002", "row_name": "货币资金",
        "indent_level": 1, "is_total_row": False, "current_period_amount": amount,
        "prior_period_amount": "100.00", "formula_used": "TB('1001','期末余额')",
        "source_accounts": ["1001"], "blank_reason": None, "prior_blank_reason": None, "has_formula": True,
    }]}


class FakeBasis:
    def __init__(self, pid: uuid.UUID):
        self.year = YEAR
        self.tree = SimpleNamespace(project_id=pid, node_key="RUN:consol")
        self.categories = {"1001": "asset"}


def test_V246_orm_and_ddl_are_aligned():
    backend = Path(__file__).resolve().parents[2]
    sql = (backend / "migrations/V246__report_generation_run_and_consol_artifact.sql").read_text(encoding="utf-8")
    rollback = (backend / "migrations/R246__rollback_report_generation_run_and_consol_artifact.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS report_generation_run" in sql
    assert "CREATE TABLE IF NOT EXISTS consol_artifact" in sql
    assert "ADD COLUMN IF NOT EXISTS run_id" in sql
    assert "ADD COLUMN IF NOT EXISTS provenance" in sql
    assert "DROP TABLE IF EXISTS consol_artifact" in rollback
    assert "DROP TABLE IF EXISTS report_generation_run" in rollback
    assert set(ReportGenerationRun.__table__.columns.keys()) >= {
        "id", "project_id", "year", "operation_id", "operation_revision", "status",
        "rows_json", "input_digest", "row_digest", "provenance",
    }
    assert set(ConsolArtifact.__table__.columns.keys()) >= {
        "id", "project_id", "year", "operation_id", "report_run_id", "kind", "status",
        "storage_path", "size_bytes", "sha256", "manifest_json",
    }
    assert {"run_id", "provenance"} <= set(FinancialReport.__table__.columns.keys())


def test_canonical_rows_and_digest_are_order_stable_and_input_sensitive():
    run_id = uuid.uuid4()
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    left = {
        "income_statement": [{
            "report_type": "income_statement", "row_number": 2, "row_code": "IS-002", "row_name": "成本",
            "current_period_amount": "10", "prior_period_amount": None, "formula_used": "TB('6401','期末余额')",
            "source_accounts": ["6401"], "has_formula": True,
        }],
        **results(),
    }
    right = {"balance_sheet": list(reversed(left["balance_sheet"])), "income_statement": left["income_statement"]}
    kwargs = dict(run_id=run_id, computed_at=now, computed_by=None,
                  operation_input_digest="1" * 64,
                  account_amounts={"1001": Decimal("123.45"), "6401": Decimal("10")})
    a = canonical_report_rows(left, **kwargs)
    b = canonical_report_rows(right, **kwargs)
    assert report_row_digest(a) == report_row_digest(b)
    provenance = a["balance_sheet"][0]["provenance"]
    assert provenance["run_id"] == str(run_id)
    assert provenance["definition_hash"]
    assert provenance["inputs"] == [{"kind": "TB", "key": "1001", "value": "123.45"}]
    changed = canonical_report_rows(left, **{**kwargs, "account_amounts": {"1001": Decimal("123.46"), "6401": Decimal("10")}})
    assert changed["balance_sheet"][0]["provenance"]["input_digest"] != provenance["input_digest"]
    assert report_row_digest(changed) != report_row_digest(a)


def test_operation_input_digest_ignores_recording_revision_but_not_business_inputs():
    left = {**VECTOR, "tree_revision": 1, "recorded_tree_fingerprint": "x"}
    recorded = {**left, "tree_revision": 2, "recorded_tree_fingerprint": "y"}
    changed = {**left, "tb_digest": "z" * 64}
    assert operation_input_digest(left) == operation_input_digest(recorded)
    assert operation_input_digest(left) != operation_input_digest(changed)


@pytest.mark.asyncio
async def test_materialize_is_idempotent_and_only_succeeded_operation_publishes(db: AsyncSession):
    p = project()
    op = operation(p.id)
    db.add_all([p, op])
    await db.commit()
    basis = FakeBasis(p.id)
    ctx = context(p.id, op.id)
    calls = 0

    async def fake_generate(service, project_id, year, standard, **kwargs):
        nonlocal calls
        calls += 1
        db.add(FinancialReport(
            project_id=project_id, year=year, report_type=FinancialReportType.balance_sheet,
            row_code="BS-002", row_name="货币资金", current_period_amount=Decimal("123.45"),
            prior_period_amount=Decimal("100.00"), formula_used="TB('1001','期末余额')",
        ))
        await db.flush()
        return results()

    with patch("app.services.consol_calc_basis.validate_calc_basis", return_value=None), \
         patch("app.services.consol_calc_basis.node_measures", return_value={
             "RUN:consol": {"consolidated": {"1001": Decimal("123.45")}},
         }), \
         patch("app.services.consol_report_service.ConsolReportService.generate_consol_reports", new=fake_generate):
        first = await materialize_consol_report_run(
            db, p.id, YEAR, operation_id=op.id, operation_revision=1, trigger="manual",
            triggered_by=None, context=ctx, tree=basis.tree, basis=basis,
            applicable_standard="soe_consolidated",
        )
        second = await materialize_consol_report_run(
            db, p.id, YEAR, operation_id=op.id, operation_revision=1, trigger="manual",
            triggered_by=None, context=ctx, tree=basis.tree, basis=basis,
            applicable_standard="soe_consolidated",
        )
    assert first.run_id == second.run_id
    assert calls == 1
    assert first.row_count == 1 and first.row_digest
    row = (await db.execute(sa.select(FinancialReport))).scalar_one()
    assert row.run_id == first.run_id
    assert row.provenance["run_id"] == str(first.run_id)
    assert row.calc_version is not None

    # report run succeeded 还不等于 published：operation running/partial/stale 均不可见。
    assert await resolve_published_run(db, p.id, YEAR) is None
    op.status = "partial"
    op.lease_owner = None
    op.lease_expires_at = None
    op.result_refs = {"report_run_id": str(first.run_id)}
    await db.flush()
    assert await resolve_published_run(db, p.id, YEAR) is None

    # 只有 operation succeeded + revision 相同 + result_refs 精确引用，才成为正式结果。
    op.status = "succeeded"
    op.finished_at = datetime.now(timezone.utc)
    await db.flush()
    published = await resolve_published_run(db, p.id, YEAR)
    assert published is not None and published.id == first.run_id
    selected_run, rows = await published_report_payload(db, p.id, YEAR, "balance_sheet")
    assert selected_run.id == first.run_id
    assert rows[0]["current_period_amount"] == "123.45"


@pytest.mark.asyncio
async def test_legacy_financial_report_without_run_is_never_published(db: AsyncSession):
    p = project()
    db.add(p)
    db.add(FinancialReport(
        project_id=p.id, year=YEAR, report_type=FinancialReportType.balance_sheet,
        row_code="BS-001", row_name="旧行", current_period_amount=Decimal("1"), run_id=None,
    ))
    await db.commit()
    assert await resolve_published_run(db, p.id, YEAR) is None


async def _published_fixture(db: AsyncSession) -> tuple[Project, ConsolOperation, ReportGenerationRun]:
    p = project()
    op = operation(p.id)
    op.status = "succeeded"
    op.lease_owner = None
    op.lease_expires_at = None
    op.finished_at = datetime.now(timezone.utc)
    run_id = uuid.uuid4()
    canonical = canonical_report_rows(
        results(), run_id=run_id, computed_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        computed_by=None, operation_input_digest=operation_input_digest(VECTOR),
        account_amounts={"1001": Decimal("123.45")},
    )
    run = ReportGenerationRun(
        id=run_id, project_id=p.id, year=YEAR, operation_id=op.id, operation_revision=1,
        node_key="RUN:consol", applicable_standard="soe_consolidated", trigger="manual",
        status="succeeded", calc_version=1, input_digest=operation_input_digest(VECTOR),
        row_digest=report_row_digest(canonical), rows_json=canonical, row_count=1,
        report_types=["balance_sheet"], provenance={"context": context(p.id, op.id).model_dump(mode="json")},
        finished_at=datetime.now(timezone.utc),
    )
    op.result_refs = {"report_run_id": str(run.id), "report_row_digest": run.row_digest, "input_revision": 1}
    db.add_all([p, op, run])
    await db.commit()
    return p, op, run


@pytest.mark.asyncio
async def test_report_artifact_is_generated_once_and_download_never_rebuilds(db: AsyncSession, tmp_path: Path):
    p, _op, run = await _published_fixture(db)
    artifact, should_generate = await reserve_artifact(
        db, p.id, YEAR, report_run_id=run.id, kind="report_excel", node_key=None, created_by=None,
    )
    assert should_generate and artifact.status == "generating"
    await db.commit()

    from app.services import consol_artifact_service as service
    with patch.object(service, "build_report_excel_bytes", wraps=service.build_report_excel_bytes) as builder:
        ready = await generate_reserved_artifact(db, artifact.id, root=tmp_path)
        await db.commit()
        assert builder.call_count == 1
        path = verify_artifact_file(ready, root=tmp_path)
        first_bytes = path.read_bytes()
        assert ready.status == "ready" and ready.sha256 and ready.size_bytes == len(first_bytes)

        same, should_generate_again = await reserve_artifact(
            db, p.id, YEAR, report_run_id=run.id, kind="report_excel", node_key=None, created_by=None,
        )
        assert same.id == ready.id and not should_generate_again
        # 重复下载只校验现有文件，不调用生成器。
        assert verify_artifact_file(same, root=tmp_path).read_bytes() == first_bytes
        assert builder.call_count == 1

    # 文件被篡改一字节，下载失败关闭。
    path.write_bytes(first_bytes + b"x")
    with pytest.raises(ArtifactError) as tampered:
        verify_artifact_file(ready, root=tmp_path)
    assert tampered.value.code == "ARTIFACT_SIZE_MISMATCH"


def test_artifact_path_rejects_absolute_and_parent_escape(tmp_path: Path):
    for raw in ("../outside.xlsx", "/absolute.xlsx", "a/../../outside.xlsx", ""):
        with pytest.raises(ArtifactError):
            resolve_artifact_path(raw, root=tmp_path)


def test_workpaper_builder_contains_all_required_sections():
    payload = {
        "manifest": {"report_run_id": "r1", "root_digest": "d" * 64},
        "tree": {"node_key": "G:consol", "company_code": "G", "company_name": "集团", "children": []},
        "worksheets": [{"sheet_key": "info", "version": 1, "digest": "a" * 64, "data": {"rows": [{"x": 1}]}}],
        "entries": [{"id": "e1", "entry_no": "E-1", "entry_type": "equity", "node_key": "G:consol_elim",
                     "lines": [{"account_code": "1511", "account_name": "长期股权投资", "debit": "1", "credit": "0"}]}],
        "trial": [{"account_code": "1511", "account_name": "长期股权投资", "individual_sum": "10",
                   "consol_adjustment": "0", "consol_elimination": "1", "consol_amount": "11", "source_entry_ids": ["e1"]}],
        "reconciliation": {"is_reconciled": True, "diff_count": 0, "max_abs_diff": "0", "diffs": []},
        "reports": results("11.00"),
        "notes": [{"section_id": "五、1", "node_key": "G:consol", "cell_state": "auto", "is_stale": False,
                   "locked_cell_count": 0, "data_digest": "n" * 64, "updated_at": None}],
    }
    book = openpyxl.load_workbook(filename=__import__("io").BytesIO(build_consol_workpaper_bytes(payload)), data_only=False)
    assert set(book.sheetnames) >= {
        "Manifest", "企业树与范围", "编制表", "已审批抵销分录", "合并试算", "对账", "资产负债表", "合并附注摘要",
    }
    assert book["资产负债表"]["D2"].value == "11.00"
    assert book["Manifest"]["B2"].value in {"r1", "d" * 64}


@pytest.mark.asyncio
async def test_report_endpoint_defaults_published_and_preview_is_zero_write(db: AsyncSession):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.deps import get_current_user
    from app.routers.consol_report import router
    from app.services.consol_report_values import ReportRow, RowValue

    p = project()
    db.add(p)
    await db.commit()
    app = FastAPI()
    app.include_router(router)

    async def override_db():
        yield db

    async def override_user():
        return SimpleNamespace(id=uuid.uuid4(), role=SimpleNamespace(value="admin"), is_active=True)

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    root = SimpleNamespace(node_key="RUN:consol", role="consol")
    run = SimpleNamespace(
        id=uuid.uuid4(), operation_id=uuid.uuid4(), operation_revision=1,
        input_digest="a" * 64, row_digest="b" * 64, applicable_standard="soe_consolidated",
    )
    published_rows = [{"row_code": "BS-002", "row_name": "货币资金", "current_period_amount": "123.45"}]

    async def fake_published(*_args, **_kwargs):
        return run, published_rows

    basis = SimpleNamespace(categories={}, tree=root)
    view = SimpleNamespace(
        basis=basis, standard="soe_consolidated", year=YEAR,
        rows=[ReportRow("balance_sheet", "BS-002", "货币资金", 2, "TB('1001','期末余额')")],
    )

    async def fake_view(*_args, **_kwargs):
        return view

    async def fake_values(*_args, **_kwargs):
        return {"BS-002": RowValue(Decimal("123.45"))}

    async def fake_prior(*_args, **_kwargs):
        return None, "合并上期留空：没有上年项目"

    with patch("app.services.consol_group_tree.build_group_tree", new=AsyncMock(return_value=SimpleNamespace(root=root))), \
         patch("app.services.consol_report_run_service.published_report_payload", new=fake_published), \
         patch("app.services.consol_report_view_service.load_view_context", new=fake_view), \
         patch("app.services.consol_calc_basis.node_measures", return_value={"RUN:consol": {"consolidated": {}}}), \
         patch("app.services.consol_report_values.report_values", new=fake_values), \
         patch("app.services.consol_report_view_service.prior_node_values", new=fake_prior):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            formal = await client.get(
                f"/api/consolidation/reports/{p.id}/{YEAR}", params={"report_type": "balance_sheet"},
            )
            assert formal.status_code == 200, formal.text
            assert formal.json()["mode"] == "published"
            assert formal.json()["report_run_id"] == str(run.id)
            assert formal.json()["download_allowed"] is True

            before = (await db.execute(sa.select(sa.func.count()).select_from(ReportGenerationRun))).scalar_one()
            preview = await client.get(
                f"/api/consolidation/reports/{p.id}/{YEAR}",
                params={"report_type": "balance_sheet", "mode": "preview"},
            )
            after = (await db.execute(sa.select(sa.func.count()).select_from(ReportGenerationRun))).scalar_one()
            assert preview.status_code == 200, preview.text
            assert preview.json()["mode"] == "preview"
            assert preview.json()["published"] is False
            assert preview.json()["download_allowed"] is False
            assert preview.json()["report_run_id"] is None
            assert preview.json()["rows"][0]["current_period_amount"] == "123.45"
            assert before == after == 0


@pytest.mark.asyncio
async def test_artifact_http_create_is_idempotent_downloads_existing_and_rejects_tamper(
    db: AsyncSession, tmp_path: Path,
):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.deps import get_current_user
    from app.routers.consol_report import router
    from app.services import consol_artifact_service as artifact_service

    p, _op, run = await _published_fixture(db)
    app = FastAPI()
    app.include_router(router)

    async def override_db():
        yield db

    async def override_user():
        return SimpleNamespace(id=uuid.uuid4(), role=SimpleNamespace(value="admin"), is_active=True)

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user

    with patch.object(artifact_service, "artifact_root", return_value=tmp_path), \
         patch.object(
             artifact_service,
             "build_report_excel_bytes",
             wraps=artifact_service.build_report_excel_bytes,
         ) as builder:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first = await client.post(
                f"/api/consolidation/reports/{p.id}/{YEAR}/artifacts",
                json={"report_run_id": str(run.id), "kind": "report_excel"},
            )
            assert first.status_code == 200, first.text
            body = first.json()
            assert body["status"] == "ready" and body["sha256"] and body["size_bytes"] > 0
            assert body["manifest"]["report_run_id"] == str(run.id)
            assert body["manifest"]["report_row_digest"] == run.row_digest

            second = await client.post(
                f"/api/consolidation/reports/{p.id}/{YEAR}/artifacts",
                json={"report_run_id": str(run.id), "kind": "report_excel"},
            )
            assert second.status_code == 200
            assert second.json()["id"] == body["id"]
            assert builder.call_count == 1

            url = f"/api/consolidation/reports/{p.id}/{YEAR}/artifacts/{body['id']}/download"
            download1 = await client.get(url)
            download2 = await client.get(url)
            assert download1.status_code == download2.status_code == 200
            assert download1.content == download2.content
            assert hashlib.sha256(download1.content).hexdigest() == body["sha256"]
            assert builder.call_count == 1, "重复下载不得重新调用生成器"

            artifact = await db.get(ConsolArtifact, uuid.UUID(body["id"]))
            path = resolve_artifact_path(artifact.storage_path, root=tmp_path)
            original = path.read_bytes()
            path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
            tampered = await client.get(url)
            assert tampered.status_code == 409
            assert tampered.json()["detail"]["code"] == "ARTIFACT_HASH_MISMATCH"


@pytest.mark.asyncio
async def test_workpaper_collector_uses_real_orm_fields_and_closes_manifest(db: AsyncSession):
    """真实 ORM 行收集范围/编制表/差额表/试算/附注摘要，所有分片与根 manifest hash 闭合。"""
    from app.services import consol_artifact_service as service
    from app.services.consol_tree_service import TreeNode

    p, op, run = await _published_fixture(db)
    db.add_all([
        ConsolWorksheetData(
            project_id=p.id, year=YEAR, sheet_key="info", data={"rows": [{"company_code": "A"}]}, version=2,
        ),
        ConsolWorksheet(
            project_id=p.id, year=YEAR, node_company_code="RUN:consol", account_code="1001",
            children_amount_sum=Decimal("10"), adjustment_debit=Decimal("1"), adjustment_credit=Decimal("0"),
            elimination_debit=Decimal("2"), elimination_credit=Decimal("0"),
            net_difference=Decimal("3"), consolidated_amount=Decimal("13"),
        ),
        ConsolTrial(
            project_id=p.id, year=YEAR, standard_account_code="1001", account_name="货币资金",
            individual_sum=Decimal("10"), consol_adjustment=Decimal("1"),
            consol_elimination=Decimal("2"), consol_amount=Decimal("13"),
            consolidation_breakdown={"source_entry_ids": ["entry-1"]},
        ),
        ConsolNoteData(
            project_id=p.id, year=YEAR, section_id="五、1", node_key="RUN:consol",
            data={"rows": [["货币资金", "13"]]}, cell_state="locked", locked_cells=[{"row_index": 0, "col_index": 1}],
        ),
    ])
    await db.commit()
    tree = TreeNode(
        project_id=p.id, company_code="RUN", company_name="【测试】集团",
        parent_company_code=None, ultimate_company_code="RUN", consol_level=1,
        node_key="RUN:consol", role="consol", kind="aggregate", children=[],
    )
    reconcile = SimpleNamespace(is_reconciled=True, diffs=[], max_abs_diff=Decimal("0"))
    with patch("app.services.consol_tree_service.build_tree", new=AsyncMock(return_value=tree)), \
         patch("app.services.consol_calc_basis.load_tree_entries", new=AsyncMock(return_value=[])), \
         patch("app.services.consol_reconciliation_service.reconcile_worksheet_vs_trial", new=AsyncMock(return_value=reconcile)), \
         patch.object(service, "_current_input_digest", new=AsyncMock(return_value=run.input_digest)):
        payload = await service.collect_workpaper_payload(db, run, op)
    assert payload["tree"]["node_key"] == "RUN:consol"
    assert {item["sheet_key"] for item in payload["worksheets"]} == {"info", "__derived_node_account__"}
    assert payload["trial"][0]["consol_amount"] == "13.00"
    assert payload["notes"][0]["locked_cell_count"] == 1
    manifest = payload["manifest"]
    for key in ("tree", "worksheets", "entries", "trial", "reconciliation", "reports", "notes"):
        assert manifest["section_digests"][key] == digest_payload(payload[key])
    root_payload = {key: value for key, value in manifest.items() if key != "root_digest"}
    assert manifest["root_digest"] == digest_payload(root_payload)


def test_cross_report_row_reference_records_actual_source_value():
    run_id = uuid.uuid4()
    raw = {
        "income_statement": [{
            "report_type": "income_statement", "row_number": 1, "row_code": "IS-019", "row_name": "净利润",
            "current_period_amount": "88.00", "formula_used": "TB('6001','期末余额')",
            "source_accounts": ["6001"], "has_formula": True,
        }],
        "cash_flow_supplement": [{
            "report_type": "cash_flow_supplement", "row_number": 1, "row_code": "CFSS-002", "row_name": "净利润",
            "current_period_amount": "88.00", "formula_used": "ROW('IS-019')",
            "source_accounts": [], "has_formula": True,
        }],
    }
    normalized = canonical_report_rows(
        raw, run_id=run_id, computed_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        computed_by=None, operation_input_digest="i" * 64,
        account_amounts={"6001": Decimal("88")},
    )
    inputs = normalized["cash_flow_supplement"][0]["provenance"]["inputs"]
    assert inputs == [{"kind": "ROW", "key": "income_statement/IS-019", "value": "88.00"}]


@pytest.mark.asyncio
async def test_formal_refresh_uses_report_run_not_legacy_materialization():
    from app.services.consol_cascade_refresh_service import refresh_all

    pid = uuid.uuid4()
    op_id = uuid.uuid4()
    tree = SimpleNamespace(node_key="RUN:consol", company_code="RUN", project_id=pid, children=[])
    basis = SimpleNamespace(tree=tree, year=YEAR)
    ctx = ConsolContext(project_id=pid, year=YEAR, run_id=op_id, tree_fingerprint="a" * 64)
    report = SimpleNamespace(run_id=uuid.uuid4(), row_digest="r" * 64)
    reconcile = SimpleNamespace(is_reconciled=True, diffs=[], max_abs_diff=Decimal("0"))
    legacy = AsyncMock()
    materialize = AsyncMock(return_value=report)
    db = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    with patch("app.services.consol_cascade_refresh_service.validate_context"), \
         patch("app.services.consol_cascade_refresh_service.load_calc_basis", new=AsyncMock(return_value=basis)), \
         patch("app.services.consol_cascade_refresh_service.get_descendants", return_value=[]), \
         patch("app.services.consol_cascade_refresh_service.recalc_full", new=AsyncMock(return_value={})), \
         patch("app.services.consol_cascade_refresh_service.recalculate_trial", new=AsyncMock(return_value=[])), \
         patch("app.services.consol_cascade_refresh_service.reconcile_worksheet_vs_trial", new=AsyncMock(return_value=reconcile)), \
         patch("app.services.consol_cascade_refresh_service.generate_consol_reports_sync", new=legacy), \
         patch("app.services.consol_report_run_service.materialize_consol_report_run", new=materialize), \
         patch("app.services.consol_cascade_refresh_service.refresh_notes_exclusive", new=AsyncMock(return_value={"note_status": "persisted"})):
        result = await refresh_all(
            db, pid, YEAR, context=ctx, tree=tree, operation_revision=2,
            triggered_by=None, report_trigger="manual",
        )
    assert result.report_run_id == report.run_id
    assert result.report_row_digest == "r" * 64
    assert materialize.await_count == 1
    assert materialize.await_args.kwargs["operation_revision"] == 2
    assert materialize.await_args.kwargs["basis"] is basis
    assert legacy.await_count == 0, "正式 operation 不得再走无 run 的 legacy 报表物化"


@pytest.mark.asyncio
async def test_failed_report_run_rolls_back_and_preserves_previous_published_value(db: AsyncSession):
    p, old_op, old_run = await _published_fixture(db)
    pid = p.id
    old_run_id = old_run.id
    db.add(FinancialReport(
        project_id=pid, year=YEAR, report_type=FinancialReportType.balance_sheet,
        row_code="BS-002", row_name="货币资金", current_period_amount=Decimal("55.00"),
        formula_used="TB('1001','期末余额')", run_id=old_run_id,
        provenance={"run_id": str(old_run_id)},
    ))
    new_op = operation(pid)
    db.add(new_op)
    await db.commit()
    new_op_id = new_op.id
    basis = FakeBasis(pid)
    ctx = context(pid, new_op_id)

    async def mutate_then_fail(service, project_id, year, standard, **kwargs):
        row = (await db.execute(sa.select(FinancialReport).where(
            FinancialReport.project_id == project_id,
            FinancialReport.row_code == "BS-002",
        ))).scalar_one()
        row.current_period_amount = Decimal("999.00")
        await db.flush()
        raise RuntimeError("injected report failure")

    with patch("app.services.consol_calc_basis.validate_calc_basis", return_value=None), \
         patch("app.services.consol_report_service.ConsolReportService.generate_consol_reports", new=mutate_then_fail):
        with pytest.raises(RuntimeError, match="injected report failure"):
            await materialize_consol_report_run(
                db, pid, YEAR, operation_id=new_op_id, operation_revision=1, trigger="manual",
                triggered_by=None, context=ctx, tree=basis.tree, basis=basis,
                applicable_standard="soe_consolidated",
            )
    await db.rollback()  # 报表步骤调用方的真实失败语义
    row = (await db.execute(sa.select(FinancialReport).where(
        FinancialReport.project_id == pid,
        FinancialReport.row_code == "BS-002",
    ))).scalar_one()
    assert row.current_period_amount == Decimal("55.00")
    assert row.run_id == old_run_id
    assert row.provenance == {"run_id": str(old_run_id)}
    runs = (await db.execute(sa.select(ReportGenerationRun).where(
        ReportGenerationRun.project_id == pid,
    ))).scalars().all()
    assert [run.id for run in runs] == [old_run_id]
    assert (await resolve_published_run(db, pid, YEAR)).id == old_run_id
