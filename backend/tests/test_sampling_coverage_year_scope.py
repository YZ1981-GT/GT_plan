"""抽样增强页「抽凭概览」按年度统计（spec voucher-workflow-linkage-lineage-closure 浏览器实测发现）

原先 ``project_sampling_coverage`` 的 by_workpaper 不看年度：页面把年度改成 2024 仍列 2025 的抽凭批次，
而同一结果里的重复抽凭（已抽凭证登记的年度）与存续核对（该年度的账套）都按年度。抽样记录表没有年度列，
按 ``_record_in_year`` 三级认法：本批次已抽凭证的年度 → 抽样框账套的年度 → 项目审计年度。

SQLite 真 ORM 行走生产函数；端点用例只替换鉴权与项目年度两个取数点，验证路由把项目年度传给统计。
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_phase_models import InterimSurvivalCheck
from app.models.dataset_models import DatasetStatus, LedgerDataset
from app.models.workpaper_models import SampledVoucher, SamplingRecord, WorkingPaper, WpIndex
from app.services.sampled_voucher_queries import project_sampling_coverage

_PID, _OTHER_PID = uuid.uuid4(), uuid.uuid4()
#: A：两批，凭证登记一批 2025、一批 2024；B：没有凭证登记、抽样框账套 2024；C：凭证登记与账套都没有；
#: D：凭证登记已全部软删、抽样框账套 2025（软删的登记行不决定年度）；E：别的项目的 2024 批次
WP_A, WP_B, WP_C, WP_D, WP_E = (uuid.uuid4() for _ in range(5))
DS_2025, DS_2024 = uuid.uuid4(), uuid.uuid4()


def _record(wp: uuid.UUID, size: int, *, batch: uuid.UUID | None = None, dataset: uuid.UUID | None = None,
            project: uuid.UUID = _PID) -> SamplingRecord:
    return SamplingRecord(id=uuid.uuid4(), project_id=project, working_paper_id=wp, batch_id=batch,
                          dataset_id=dataset, sampling_purpose="凭证检查", population_description="本科目借方发生额",
                          sample_size=size)


def _voucher(batch: uuid.UUID, year: int, wp: uuid.UUID, no: str, *, deleted: bool = False,
             project: uuid.UUID = _PID) -> SampledVoucher:
    return SampledVoucher(id=uuid.uuid4(), project_id=project, year=year, voucher_no=no, working_paper_id=wp,
                          batch_id=batch, is_deleted=deleted)


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [SamplingRecord.__table__, SampledVoucher.__table__, LedgerDataset.__table__, WorkingPaper.__table__,
              WpIndex.__table__, InterimSurvivalCheck.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: SamplingRecord.metadata.create_all(c, tables=tables))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        a_2025, a_2024, d_batch, e_batch = (uuid.uuid4() for _ in range(4))
        session.add_all([
            LedgerDataset(id=DS_2025, project_id=_PID, year=2025, status=DatasetStatus.active, source_type="import"),
            LedgerDataset(id=DS_2024, project_id=_PID, year=2024, status=DatasetStatus.active, source_type="import"),
            _record(WP_A, 3, batch=a_2025, dataset=DS_2024),  # 凭证登记优先于账套：这批算 2025
            _voucher(a_2025, 2025, WP_A, "0001"), _voucher(a_2025, 2025, WP_A, "0002"),
            _record(WP_A, 4, batch=a_2024),
            _voucher(a_2024, 2024, WP_A, "0009"),
            _record(WP_B, 7, dataset=DS_2024),
            _record(WP_C, 2),
            _record(WP_D, 6, batch=d_batch, dataset=DS_2025),
            _voucher(d_batch, 2024, WP_D, "0005", deleted=True),
            _record(WP_E, 9, batch=e_batch, project=_OTHER_PID),
            _voucher(e_batch, 2024, WP_E, "0007", project=_OTHER_PID),
        ])
        await session.commit()
        yield session
    await engine.dispose()


def _counts(coverage: dict) -> dict[str, tuple[int, int]]:
    names = {str(WP_A): "A", str(WP_B): "B", str(WP_C): "C", str(WP_D): "D", str(WP_E): "E"}
    return {names[r["working_paper_id"]]: (r["batch_count"], r["sample_count"]) for r in coverage["by_workpaper"]}


async def test_audit_year_counts_only_its_own_batches(db):
    got = _counts(await project_sampling_coverage(db, _PID, 2025, project_year=2025))
    # A 只算 2025 那批；C 认不出年度、算项目审计年度；D 的登记行已软删，按账套 2025；B 的账套是 2024
    assert got == {"A": (1, 3), "C": (0, 2), "D": (1, 6)}


async def test_other_year_does_not_list_audit_year_batches(db):
    got = _counts(await project_sampling_coverage(db, _PID, 2024, project_year=2025))
    # 原先这里会把 A 的两批（7 笔）、C、D 全列出来
    assert got == {"A": (1, 4), "B": (0, 7)}


async def test_unknown_year_record_counts_nowhere_without_project_year(db):
    assert "C" not in _counts(await project_sampling_coverage(db, _PID, 2025))
    assert "C" not in _counts(await project_sampling_coverage(db, _PID, 2024))


async def test_endpoint_passes_project_year_and_requested_year(db, monkeypatch):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.deps import get_current_user
    from app.routers import voucher_sampling

    seen: dict[str, object] = {}

    async def _allow(_db, user, project_id, level):
        seen["permission"] = (project_id, level)

    async def _project_year(_db, project_id):
        return 2025

    monkeypatch.setattr(voucher_sampling, "assert_project_permission", _allow)
    monkeypatch.setattr(voucher_sampling, "registry_resolve_project_year", _project_year)
    app = FastAPI()
    app.include_router(voucher_sampling.router)

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid.uuid4())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        default = await client.get(f"/api/projects/{_PID}/sampling/voucher-coverage")
        other = await client.get(f"/api/projects/{_PID}/sampling/voucher-coverage", params={"year": 2024})
    assert default.status_code == 200 and other.status_code == 200, (default.text, other.text)
    assert seen["permission"] == (_PID, "readonly")
    assert default.json()["year"] == 2025 and _counts(default.json()) == {"A": (1, 3), "C": (0, 2), "D": (1, 6)}
    # 改看 2024：认不出年度的 C 仍算项目审计年度 2025，不出现在 2024
    assert other.json()["year"] == 2024 and _counts(other.json()) == {"A": (1, 4), "B": (0, 7)}
