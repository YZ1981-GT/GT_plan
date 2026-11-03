"""预审样本存续核对（spec voucher-identity-writeback-and-audit-phase 任务 17，需求 8，ADR-VK-11）。

SQLite 真 ORM 行覆盖四步顺序、汇总 upsert / 既有确认保留、逐行确认汇总、旧数据集拒绝、项目抽样概览投影、
端点鉴权 / 项目归属 / 阶段 / 年度。真实 PG 四状态与请求链见 ``test_interim_survival_pg.py``。
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_phase_models import InterimSurvivalCheck
from app.models.audit_platform_models import TbLedger
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, ProjectUser, User
from app.models.dataset_models import DatasetStatus, LedgerDataset
from app.models.workpaper_models import SamplingRecord, WorkingPaper, WpIndex, WpSourceType, WpStatus
from app.services.interim_survival import check_interim_survival, set_unacked, survival_status
from app.services.sampled_voucher_queries import project_sampling_coverage
from app.services.voucher_identity import VoucherKey, line_fingerprint

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

USER, STRANGER, PROJECT, OTHER = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
WP, WP_OTHER, DATASET = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
YEAR = 2025


def _vk(no: str, day: int) -> VoucherKey:
    return VoucherKey.of(year=YEAR, company_code="T17", voucher_date=date(YEAR, 12, day), voucher_type="ZZ", voucher_no=no)


def _fp(no: str, day: int, account: str, side: str, amount: str) -> str:
    return line_fingerprint(_vk(no, day), account, side, amount, 0)


def _input(no: str, day: int, account: str, side: str, amount: str, **extra) -> dict:
    lfp = _fp(no, day, account, side, amount)
    return {"row_key": lfp, "lfp": lfp, "vk": _vk(no, day).to_str(), "account_code": account,
            "side": side, "amount": amount, **extra}


def _ledger(no: str, day: int, account: str, side: str, amount: str) -> TbLedger:
    return TbLedger(
        id=uuid.uuid4(), project_id=PROJECT, year=YEAR, company_code="T17", voucher_date=date(YEAR, 12, day),
        voucher_type="ZZ", voucher_no=no, account_code=account, account_name=f"科目{account}",
        debit_amount=amount if side == "D" else None, credit_amount=amount if side == "C" else None,
        summary=f"{no} 摘要", dataset_id=DATASET,
    )


def _wp(session: AsyncSession, wp_id: uuid.UUID, project_id: uuid.UUID, code: str) -> None:
    idx = WpIndex(id=uuid.uuid4(), project_id=project_id, wp_code=code, wp_name=f"{code} 凭证检查",
                  status=WpStatus.not_started)
    session.add(idx)
    session.add(WorkingPaper(id=wp_id, project_id=project_id, wp_index_id=idx.id, file_path=f"{code}.xlsx",
                             source_type=WpSourceType.template, file_version=1))


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add(User(id=USER, username="survival_editor", email="survival@test.com", hashed_password="x", role="auditor"))
        session.add(User(id=STRANGER, username="survival_stranger", email="stranger@test.com", hashed_password="x", role="auditor"))
        for pid, name in ((PROJECT, "【测试】存续核对"), (OTHER, "【测试】其他项目")):
            session.add(Project(id=pid, name=name, client_name="测试", project_type=ProjectType.annual,
                                status=ProjectStatus.execution, created_by=USER, audit_year=YEAR,
                                current_audit_phase="final", interim_cutoff_date=date(YEAR, 9, 30)))
        session.add(ProjectUser(project_id=PROJECT, user_id=USER, role="auditor", permission_level="edit", is_deleted=False))
        _wp(session, WP, PROJECT, "J1")
        _wp(session, WP_OTHER, OTHER, "E1")
        session.add(LedgerDataset(id=DATASET, project_id=PROJECT, year=YEAR, status=DatasetStatus.active,
                                  source_type="import"))
        # unchanged；modified（同凭证键、金额已改）；renumbered（原号不在、同日同科目栏位金额的新号）
        session.add_all([
            _ledger("U-1", 20, "1001", "D", "100.00"),
            _ledger("M-1", 21, "1002", "C", "201.00"),
            _ledger("M-CAND", 21, "1002", "C", "200.00"),  # 即使有同额候选，原凭证仍在必须先判 modified
            _ledger("R-NEW", 22, "1003", "D", "300.00"),
            _ledger("R-WRONG-SIDE", 22, "1003", "C", "300.00"),
            _ledger("R-WRONG-AMOUNT", 22, "1003", "D", "301.00"),
        ])
        await session.commit()
        yield session
    await engine.dispose()


async def _run(db: AsyncSession, rows=None):
    rows = rows or [
        _input("U-1", 20, "1001", "D", "100.00"),
        _input("M-1", 21, "1002", "C", "200.00"),
        _input("R-OLD", 22, "1003", "D", "300.00"),
        _input("D-OLD", 23, "1004", "C", "400.00"),
    ]
    return await check_interim_survival(db, project_id=PROJECT, workpaper_id=WP, year=YEAR, rows=rows, checked_by=USER)


class TestSurvivalService:
    async def test_four_statuses_in_required_order_and_summary(self, db):
        out = await _run(db)
        assert [r["status"] for r in out["results"]] == ["unchanged", "modified", "renumbered", "deleted"]
        assert (out["total"], out["unchanged"], out["modified"], out["renumbered"], out["deleted"], out["unacked"]) == (4, 1, 1, 1, 1, 3)
        modified = out["results"][1]["current_voucher"]
        assert modified["voucher_key"] == _vk("M-1", 21).to_str() and modified["lines"][0]["amount"] == "201.00"
        renumbered = out["results"][2]
        assert [c["voucher_no"] for c in renumbered["candidates"]] == ["R-NEW"]
        assert "candidates" not in out["results"][3]
        row = (await db.execute(sa.select(InterimSurvivalCheck))).scalar_one()
        assert str(row.id) == out["check_id"] and (row.changed, row.renumbered, row.deleted, row.unacked) == (1, 1, 1, 3)

    async def test_duplicate_expanded_rows_count_once_and_ack_preserved_only_for_same_result_dataset(self, db):
        row = _input("M-1", 21, "1002", "C", "200.00", previous_dataset_id=str(DATASET),
                     previous_status="modified", acknowledged=True)
        out = await _run(db, [row, {**row, "row_key": row["row_key"] + "#counterpart"}])
        assert out["total"] == 1 and len(out["results"]) == 1 and out["results"][0]["acknowledged"] is True
        assert out["unacked"] == 0
        # 数据集或状态任一变化都不能沿用旧确认
        out = await _run(db, [{**row, "previous_dataset_id": str(uuid.uuid4())}])
        assert out["unacked"] == 1 and out["results"][0]["acknowledged"] is False

    async def test_rerun_upserts_same_summary(self, db):
        first = await _run(db)
        second = await _run(db, [_input("U-1", 20, "1001", "D", "100.00")])
        assert first["check_id"] == second["check_id"]
        assert (await db.execute(sa.select(sa.func.count()).select_from(InterimSurvivalCheck))).scalar_one() == 1
        assert (await db.execute(sa.select(InterimSurvivalCheck))).scalar_one().total == 1

    async def test_status_and_idempotent_unacked_update(self, db):
        out = await _run(db)
        check_id = uuid.UUID(out["check_id"])
        ack = await set_unacked(db, project_id=PROJECT, workpaper_id=WP, dataset_id=DATASET,
                                check_id=check_id, unacked=2, actor_id=USER)
        assert ack["unacked"] == 2 and ack["ack_by"] == str(USER) and ack["ack_at"]
        again = await set_unacked(db, project_id=PROJECT, workpaper_id=WP, dataset_id=DATASET,
                                  check_id=check_id, unacked=2, actor_id=USER)
        assert again["unacked"] == 2
        status = await survival_status(db, project_id=PROJECT, workpaper_id=WP, year=YEAR)
        assert status["active_dataset_id"] == str(DATASET) and status["check"]["unacked"] == 2

    async def test_stale_dataset_and_invalid_unacked_rejected(self, db):
        out = await _run(db)
        with pytest.raises(HTTPException) as bad:
            await set_unacked(db, project_id=PROJECT, workpaper_id=WP, dataset_id=DATASET,
                              check_id=uuid.UUID(out["check_id"]), unacked=4, actor_id=USER)
        assert bad.value.status_code == 422 and bad.value.detail["error_code"] == "INVALID_UNACKED_COUNT"
        await db.execute(sa.update(LedgerDataset).where(LedgerDataset.id == DATASET).values(status=DatasetStatus.superseded))
        with pytest.raises(HTTPException) as stale:
            await set_unacked(db, project_id=PROJECT, workpaper_id=WP, dataset_id=DATASET,
                              check_id=uuid.UUID(out["check_id"]), unacked=1, actor_id=USER)
        assert stale.value.status_code == 409 and stale.value.detail["error_code"] == "SURVIVAL_DATASET_STALE"

    @pytest.mark.parametrize("patch,code", [
        ({"lfp": "bad"}, "INVALID_SURVIVAL_ROW"),
        ({"vk": _vk("OTHER", 20).to_str()}, "SURVIVAL_IDENTITY_MISMATCH"),
        ({"account_code": "9999"}, "SURVIVAL_LINE_MISMATCH"),
        ({"amount": "not-money"}, "INVALID_SURVIVAL_ROW"),
    ])
    async def test_corrupt_row_metadata_rejected(self, db, patch, code):
        row = {**_input("U-1", 20, "1001", "D", "100.00"), **patch}
        with pytest.raises(HTTPException) as exc:
            await _run(db, [row])
        assert exc.value.status_code == 422 and exc.value.detail["error_code"] == code


async def test_project_coverage_includes_survival_only_workpaper_and_names(db):
    out = await _run(db)
    coverage = await project_sampling_coverage(db, PROJECT, YEAR)
    row = next(r for r in coverage["by_workpaper"] if r["working_paper_id"] == str(WP))
    assert coverage["active_dataset_id"] == str(DATASET)
    assert (row["wp_code"], row["wp_name"], row["batch_count"], row["sample_count"]) == ("J1", "J1 凭证检查", 0, 0)
    assert row["interim_survival_check_id"] == out["check_id"] and row["interim_survival_unacked"] == 3
    assert row["interim_survival_counts"] == {"total": 4, "unchanged": 1, "modified": 1, "renumbered": 1, "deleted": 1}


@pytest_asyncio.fixture
async def client(db):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.deps import get_current_user
    from app.routers import sampling_phase, voucher_sampling

    app = FastAPI()
    app.include_router(sampling_phase.router)
    app.include_router(voucher_sampling.router)
    state = {"user": USER}

    class _User:
        def __init__(self, user_id):
            self.id = user_id

        class _Role:
            value = "auditor"

        role = _Role()

    async def _db():
        yield db

    async def _user():
        return _User(state["user"])

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.as_user = lambda user_id: state.update(user=user_id)  # type: ignore[attr-defined]
        yield c


def _body(wp=WP, rows=None, year=YEAR):
    return {"wp_id": str(wp), "year": year, "rows": rows or [
        _input("U-1", 20, "1001", "D", "100.00"),
        _input("M-1", 21, "1002", "C", "200.00"),
    ]}


class TestEndpoints:
    async def test_post_get_patch_and_coverage(self, client, db):
        posted = await client.post(f"/api/projects/{PROJECT}/sampling/interim-survival", json=_body())
        assert posted.status_code == 200, posted.text
        result = posted.json()
        assert [r["status"] for r in result["results"]] == ["unchanged", "modified"] and result["unacked"] == 1
        status = await client.get(f"/api/projects/{PROJECT}/sampling/interim-survival/status",
                                  params={"wp_id": str(WP), "year": YEAR})
        assert status.status_code == 200 and status.json()["check"]["unacked"] == 1
        ack = await client.patch(f"/api/projects/{PROJECT}/sampling/interim-survival/{result['check_id']}", json={
            "wp_id": str(WP), "dataset_id": str(DATASET), "unacked": 0})
        assert ack.status_code == 200 and ack.json()["unacked"] == 0 and ack.json()["ack_by"] == str(USER)
        cov = await client.get(f"/api/projects/{PROJECT}/sampling/voucher-coverage", params={"year": YEAR})
        assert cov.status_code == 200 and cov.json()["by_workpaper"][0]["interim_survival_unacked"] == 0

    async def test_voucher_coverage_requires_project_membership(self, client):
        client.as_user(STRANGER)  # type: ignore[attr-defined]
        resp = await client.get(f"/api/projects/{PROJECT}/sampling/voucher-coverage", params={"year": YEAR})
        assert resp.status_code == 403

    async def test_wrong_project_workpaper_and_year_rejected(self, client):
        wrong = await client.post(f"/api/projects/{PROJECT}/sampling/interim-survival", json=_body(WP_OTHER))
        assert wrong.status_code == 403  # 不是该底稿所属项目的成员，authorize_wp_edit 拒绝
        year = await client.post(f"/api/projects/{PROJECT}/sampling/interim-survival", json=_body(year=2024))
        assert year.status_code == 422 and year.json()["detail"]["error_code"] == "SURVIVAL_YEAR_MISMATCH"

    async def test_preliminary_phase_rejected(self, client, db):
        await db.execute(sa.update(Project).where(Project.id == PROJECT).values(current_audit_phase="preliminary"))
        await db.commit()
        resp = await client.post(f"/api/projects/{PROJECT}/sampling/interim-survival", json=_body())
        assert resp.status_code == 409 and resp.json()["detail"]["error_code"] == "FINAL_PHASE_REQUIRED"

    async def test_pydantic_rejects_empty_and_bad_side(self, client):
        empty = await client.post(f"/api/projects/{PROJECT}/sampling/interim-survival", json={"wp_id": str(WP), "year": YEAR, "rows": []})
        assert empty.status_code == 422
        bad = _body(rows=[{**_input("U-1", 20, "1001", "D", "100.00"), "side": "debit"}])
        assert (await client.post(f"/api/projects/{PROJECT}/sampling/interim-survival", json=bad)).status_code == 422
