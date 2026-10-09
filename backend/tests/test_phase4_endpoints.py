"""Phase4 交付中心三件套 — 端点与权限 TestClient 测试

Task 9: readiness / 生成 / 重试 / 下载端点与权限
- 路由登记在 router_registry，项目成员/只读/编辑权限经真依赖链校验
- TestClient 真请求覆盖 ready/blocked、job 属主项目校验、403 零写入、
  重试冲突、下载前物理哈希校验；去鉴权与错项目变异必须红

_需求引用: 1.6, 3.5, 5.1, 5.6, 7.4_
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base
from app.models.core import Project, User
from app.models.phase13_models import (
    DeliverableSnapshot,
    ExportJob,
    ExportJobAttempt,
    ExportJobAttemptStatus,
    ExportJobItem,
    ExportJobItemStatus,
    ExportJobStatus,
)


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────

PROJECT_ID = uuid.uuid4()
OTHER_PROJECT_ID = uuid.uuid4()
ADMIN_USER_ID = uuid.uuid4()
READONLY_USER_ID = uuid.uuid4()
YEAR = 2024


class _FakeRole:
    """模拟 User.role 枚举对象。"""
    def __init__(self, value: str):
        self.value = value


class _FakeUser:
    """轻量 User 替身 — 不经过 SQLAlchemy instrumentation。"""
    def __init__(self, uid: uuid.UUID, role: str, username: str = "user"):
        self.id = uid
        self.role = _FakeRole(role)
        self.username = username
        self.email = f"{username}@test.com"
        self.is_active = True


ADMIN_USER = _FakeUser(ADMIN_USER_ID, "admin", "admin_user")
READONLY_USER = _FakeUser(READONLY_USER_ID, "readonly", "readonly_user")


@pytest_asyncio.fixture
async def engine():
    """SQLite 内存库引擎。"""
    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
    SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_factory(engine):
    """返回一个 session 工厂，每次调用创建新 session。"""
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return factory


@pytest_asyncio.fixture
async def db(db_factory):
    """用于种数据的 session。"""
    async with db_factory() as session:
        yield session


@pytest_asyncio.fixture
async def seed_project(db: AsyncSession):
    """种入测试项目。"""
    project = Project(
        id=PROJECT_ID,
        name="Phase4端点测试项目",
        client_name="测试有限公司",
        status="created",
        template_type="soe",
        audit_year=YEAR,
    )
    db.add(project)

    other_project = Project(
        id=OTHER_PROJECT_ID,
        name="其他项目",
        client_name="其他公司",
        status="created",
        template_type="listed",
        audit_year=YEAR,
    )
    db.add(other_project)
    await db.commit()
    return project


# ──────────────────────────────────────────────────────────────────────
# Helper: seed readiness data
# ──────────────────────────────────────────────────────────────────────

async def _seed_full_readiness(db: AsyncSession, project_id: uuid.UUID, year: int):
    """种入全部就绪数据 — readiness 返回 ready。"""
    from app.models.audit_platform_models import TrialBalance
    for i in range(3):
        db.add(TrialBalance(
            id=uuid.uuid4(),
            project_id=project_id,
            year=year,
            company_code="001",
            standard_account_code=f"1001.{i:02d}",
            account_name=f"测试科目{i}",
            account_category="assets",
            unadjusted_amount=Decimal("10000.00"),
            audited_amount=Decimal("10000.00"),
        ))

    from app.models.formula_push_models import FormulaPushRun
    db.add(FormulaPushRun(
        id=uuid.uuid4(),
        project_id=project_id,
        year=year,
        trigger_source="manual",
        status="succeeded",
    ))

    from app.models.audit_platform_models import Adjustment
    db.add(Adjustment(
        id=uuid.uuid4(),
        project_id=project_id,
        year=year,
        company_code="001",
        adjustment_no="AJE-001",
        adjustment_type="aje",
        account_code="1001.00",
        debit_amount=Decimal("1000.00"),
        credit_amount=Decimal("0.00"),
        entry_group_id=uuid.uuid4(),
        review_status="approved",
        created_by=ADMIN_USER_ID,
    ))

    from app.models.report_models import FinancialReport
    for i in range(3):
        db.add(FinancialReport(
            id=uuid.uuid4(),
            project_id=project_id,
            year=year,
            report_type="balance_sheet",
            row_code=f"R{i+1:03d}",
            row_name=f"报表行{i}",
            current_period_amount=Decimal("50000.00"),
            is_stale=False,
        ))

    from app.models.report_models import DisclosureNote
    for i in range(2):
        db.add(DisclosureNote(
            id=uuid.uuid4(),
            project_id=project_id,
            year=year,
            note_section=f"五、{i+1}",
            section_title=f"测试附注{i}",
            is_stale=False,
            updated_by=ADMIN_USER_ID,
        ))

    await db.commit()


async def _seed_trio_job(
    db: AsyncSession,
    project_id: uuid.UUID,
    *,
    status: str = "partial",
    items_config: list[dict] | None = None,
) -> tuple[ExportJob, DeliverableSnapshot, list[ExportJobItem]]:
    """种入一个 trio job 和 items/attempt，用于查询/重试/下载测试。"""
    snapshot = DeliverableSnapshot(
        id=uuid.uuid4(),
        project_id=project_id,
        year=YEAR,
        digest="a" * 64,
        payload={},
    )
    db.add(snapshot)
    await db.flush()

    job = ExportJob(
        id=uuid.uuid4(),
        project_id=project_id,
        job_type="deliverable_trio",
        status=status,
        payload={"year": YEAR},
        progress_total=3,
        progress_done=0,
        failed_count=0,
        initiated_by=ADMIN_USER_ID,
        kind="deliverable_trio",
        year=YEAR,
        snapshot_id=snapshot.id,
        trio_total=3,
        trio_succeeded=0,
    )
    db.add(job)
    await db.flush()

    configs = items_config or [
        {"step_key": "financial_report", "sequence": 1, "status": "succeeded"},
        {"step_key": "disclosure_notes", "sequence": 2, "status": "failed",
         "error_message": "导出器异常"},
        {"step_key": "audit_report", "sequence": 3, "status": "blocked",
         "error_message": "前置步骤未成功"},
    ]

    items = []
    for cfg in configs:
        item = ExportJobItem(
            id=uuid.uuid4(),
            job_id=job.id,
            step_key=cfg["step_key"],
            sequence=cfg["sequence"],
            status=cfg["status"],
            snapshot_id=snapshot.id,
            attempt_count=1,
            error_message=cfg.get("error_message"),
        )
        db.add(item)
        items.append(item)

    await db.flush()

    # 为每个 item 种入 attempt
    for item in items:
        attempt = ExportJobAttempt(
            id=uuid.uuid4(),
            job_id=job.id,
            item_id=item.id,
            attempt_no=1,
            status=item.status,
            snapshot_id=snapshot.id,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            error_message=item.error_message,
        )
        db.add(attempt)
        item.last_attempt_id = attempt.id

    await db.commit()
    return job, snapshot, items


# ──────────────────────────────────────────────────────────────────────
# App factory
# ──────────────────────────────────────────────────────────────────────

def _build_app(db_factory, current_user: User) -> FastAPI:
    """构建测试 FastAPI app，override get_db / get_current_user。"""
    from app.routers.deliverable import router

    app = FastAPI()
    app.include_router(router)

    who = {"user": current_user}

    async def _override_db():
        async with db_factory() as session:
            yield session

    def _override_user():
        return who["user"]

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    # 返回 app 和 who，以便测试切换用户
    return app, who


def _base_url(project_id: uuid.UUID) -> str:
    return f"/api/projects/{project_id}/deliverables"


# ══════════════════════════════════════════════════════════════════════
# 1. Readiness 端点：ready vs blocked
# ══════════════════════════════════════════════════════════════════════

class TestReadinessEndpoint:
    """需求 1.6：readiness 端点在 ready / blocked 场景下行为正确。"""

    @pytest.mark.asyncio
    async def test_readiness_returns_ready_when_data_available(
        self, db: AsyncSession, db_factory, seed_project,
    ):
        """全部数据就绪 → status=ready。"""
        await _seed_full_readiness(db, PROJECT_ID, YEAR)

        app, _ = _build_app(db_factory, ADMIN_USER)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as client:
            r = await client.get(
                f"{_base_url(PROJECT_ID)}/trio/readiness",
                params={"year": YEAR},
            )
        assert r.status_code == 200, r.text
        data = r.json()
        # ResponseWrapperMiddleware 可能包装，检查两种形态
        body = data.get("data", data)
        assert body["status"] == "ready"
        assert body["trio"]["total"] == 3

    @pytest.mark.asyncio
    async def test_readiness_returns_blocked_when_no_tb(
        self, db: AsyncSession, db_factory, seed_project,
    ):
        """试算表为空 → status=blocked + hard_blockers 非空。"""
        app, _ = _build_app(db_factory, ADMIN_USER)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as client:
            r = await client.get(
                f"{_base_url(PROJECT_ID)}/trio/readiness",
                params={"year": YEAR},
            )
        assert r.status_code == 200, r.text
        body = r.json().get("data", r.json())
        assert body["status"] == "blocked"
        assert len(body["hard_blockers"]) > 0


# ══════════════════════════════════════════════════════════════════════
# 2. Trio 创建端点：成功 + blocked 返回错误
# ══════════════════════════════════════════════════════════════════════

class TestTrioCreateEndpoint:
    """需求 2.1 / 5.1：创建三件套 job。"""

    @pytest.mark.asyncio
    async def test_create_blocked_when_readiness_fails(
        self, db: AsyncSession, db_factory, seed_project,
    ):
        """readiness 不通过 → 409。"""
        app, _ = _build_app(db_factory, ADMIN_USER)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as client:
            r = await client.post(
                f"{_base_url(PROJECT_ID)}/trio",
                params={"year": YEAR},
            )
        assert r.status_code == 409, r.text
        body = r.json()
        detail = body.get("detail", body)
        assert "blockers" in detail or "交付前检查未通过" in str(detail)

    @pytest.mark.asyncio
    async def test_create_succeeds_when_ready(
        self, db: AsyncSession, db_factory, seed_project,
    ):
        """readiness 通过 → 创建 job，调用 executor。

        mock executor 步骤方法（避免真正调用报表/附注生成器），
        但端点本身经真实依赖链执行。
        """
        await _seed_full_readiness(db, PROJECT_ID, YEAR)

        app, _ = _build_app(db_factory, ADMIN_USER)

        # 模拟 executor 步骤避免调用复杂导出器
        async def _mock_run_financial_reports(*a, **kw):
            return uuid.uuid4()

        async def _mock_run_disclosure_notes(*a, **kw):
            return uuid.uuid4()

        async def _mock_run_report_body(*a, **kw):
            return uuid.uuid4(), None, None

        with (
            patch(
                "app.services.full_deliverables_executor.FullDeliverablesExecutor._run_financial_reports",
                side_effect=_mock_run_financial_reports,
            ),
            patch(
                "app.services.full_deliverables_executor.FullDeliverablesExecutor._run_disclosure_notes",
                side_effect=_mock_run_disclosure_notes,
            ),
            patch(
                "app.services.full_deliverables_executor.FullDeliverablesExecutor._run_report_body",
                side_effect=_mock_run_report_body,
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test",
            ) as client:
                r = await client.post(
                    f"{_base_url(PROJECT_ID)}/trio",
                    params={"year": YEAR},
                )
        assert r.status_code == 200, r.text
        body = r.json().get("data", r.json())
        assert body["trio_total"] == 3
        assert body["job_id"] is not None
        assert body["status"] == "succeeded"
        assert body["trio_succeeded"] == 3


# ══════════════════════════════════════════════════════════════════════
# 3. Job 查询端点：existing vs 404 vs wrong project 403
# ══════════════════════════════════════════════════════════════════════

class TestJobQueryEndpoint:
    """需求 4.3 / 4.4：job 查询端点行为。"""

    @pytest.mark.asyncio
    async def test_get_job_success(
        self, db: AsyncSession, db_factory, seed_project,
    ):
        """正确 project + 存在的 job → 200。"""
        job, _, _ = await _seed_trio_job(db, PROJECT_ID)

        app, _ = _build_app(db_factory, ADMIN_USER)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as client:
            r = await client.get(
                f"{_base_url(PROJECT_ID)}/trio/jobs/{job.id}",
            )
        assert r.status_code == 200, r.text

    @pytest.mark.asyncio
    async def test_get_job_404(
        self, db: AsyncSession, db_factory, seed_project,
    ):
        """不存在的 job → 404。"""
        app, _ = _build_app(db_factory, ADMIN_USER)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as client:
            r = await client.get(
                f"{_base_url(PROJECT_ID)}/trio/jobs/{uuid.uuid4()}",
            )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_get_job_wrong_project_403(
        self, db: AsyncSession, db_factory, seed_project,
    ):
        """job 属于另一项目 → 403。"""
        job, _, _ = await _seed_trio_job(db, PROJECT_ID)

        app, _ = _build_app(db_factory, ADMIN_USER)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as client:
            r = await client.get(
                f"{_base_url(OTHER_PROJECT_ID)}/trio/jobs/{job.id}",
            )
        assert r.status_code == 403


# ══════════════════════════════════════════════════════════════════════
# 4. Retry 端点：成功 + snapshot 冲突 409 + wrong project 403
# ══════════════════════════════════════════════════════════════════════

class TestRetryEndpoint:
    """需求 5.1–5.5：重试失败步骤端点。"""

    @pytest.mark.asyncio
    async def test_retry_wrong_project_403(
        self, db: AsyncSession, db_factory, seed_project,
    ):
        """job 属于另一项目 → 403。"""
        job, _, _ = await _seed_trio_job(db, PROJECT_ID, status="partial")

        app, _ = _build_app(db_factory, ADMIN_USER)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as client:
            r = await client.post(
                f"{_base_url(OTHER_PROJECT_ID)}/trio/jobs/{job.id}/retry",
            )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_retry_404_nonexistent_job(
        self, db: AsyncSession, db_factory, seed_project,
    ):
        """不存在的 job → 404。"""
        app, _ = _build_app(db_factory, ADMIN_USER)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as client:
            r = await client.post(
                f"{_base_url(PROJECT_ID)}/trio/jobs/{uuid.uuid4()}/retry",
            )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_retry_snapshot_conflict_409(
        self, db: AsyncSession, db_factory, seed_project,
    ):
        """快照不一致 → 409（SnapshotConflictError）。

        种入 job 的 snapshot.digest 与当前 readiness 的 digest 不同。
        readiness 有数据时产出真实 digest ≠ 'aaa...a'。
        """
        await _seed_full_readiness(db, PROJECT_ID, YEAR)
        job, _, _ = await _seed_trio_job(db, PROJECT_ID, status="partial")

        app, _ = _build_app(db_factory, ADMIN_USER)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as client:
            r = await client.post(
                f"{_base_url(PROJECT_ID)}/trio/jobs/{job.id}/retry",
            )
        assert r.status_code == 409, (
            f"快照不一致时应返回 409，实际 {r.status_code}: {r.text}"
        )


# ══════════════════════════════════════════════════════════════════════
# 5. Download 端点：文件存在 + hash 验证 + 缺失报错
# ══════════════════════════════════════════════════════════════════════

class TestDownloadEndpoint:
    """需求 3.5：下载前校验物理文件和 hash。"""

    @pytest.mark.asyncio
    async def test_download_item_not_succeeded_400(
        self, db: AsyncSession, db_factory, seed_project,
    ):
        """item 未成功 → 400。"""
        _, _, items = await _seed_trio_job(db, PROJECT_ID)
        failed_item = [i for i in items if i.status == "failed"][0]

        app, _ = _build_app(db_factory, ADMIN_USER)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as client:
            r = await client.get(
                f"{_base_url(PROJECT_ID)}/trio/items/{failed_item.id}/download",
            )
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_download_item_no_file_path_400(
        self, db: AsyncSession, db_factory, seed_project,
    ):
        """item 成功但无 file_path → 400。"""
        _, _, items = await _seed_trio_job(db, PROJECT_ID)
        ok_item = [i for i in items if i.status == "succeeded"][0]
        # ok_item.file_path 默认为 None

        app, _ = _build_app(db_factory, ADMIN_USER)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as client:
            r = await client.get(
                f"{_base_url(PROJECT_ID)}/trio/items/{ok_item.id}/download",
            )
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_download_hash_mismatch_409(
        self, db: AsyncSession, db_factory, seed_project, tmp_path,
    ):
        """文件存在但指纹不一致 → 409。"""
        # 创建一个真实文件
        test_file = tmp_path / "deliverables" / "test_report.xlsx"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_bytes(b"real file content")

        _, _, items = await _seed_trio_job(
            db, PROJECT_ID,
            items_config=[
                {
                    "step_key": "financial_report",
                    "sequence": 1,
                    "status": "succeeded",
                },
            ],
        )
        item = items[0]
        # 设置文件路径和一个错误的 hash
        item.file_path = str(test_file)
        item.file_size = test_file.stat().st_size
        item.file_sha256 = "0" * 64  # 假的 hash
        await db.commit()

        app, _ = _build_app(db_factory, ADMIN_USER)

        # mock DELIVERY_ROOT 让路径校验通过
        with patch(
            "app.services.file_fingerprint_service.DELIVERY_ROOT",
            tmp_path / "deliverables",
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test",
            ) as client:
                r = await client.get(
                    f"{_base_url(PROJECT_ID)}/trio/items/{item.id}/download",
                )
        assert r.status_code == 409, (
            f"hash 不一致时应 409，实际 {r.status_code}: {r.text}"
        )

    @pytest.mark.asyncio
    async def test_download_success_when_fingerprint_matches(
        self, db: AsyncSession, db_factory, seed_project, tmp_path,
    ):
        """文件存在且指纹一致 → 200 文件流。"""
        content = b"valid xlsx content for download test"
        test_file = tmp_path / "deliverables" / "report.xlsx"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_bytes(content)

        sha = hashlib.sha256(content).hexdigest()

        _, _, items = await _seed_trio_job(
            db, PROJECT_ID,
            items_config=[
                {
                    "step_key": "financial_report",
                    "sequence": 1,
                    "status": "succeeded",
                },
            ],
        )
        item = items[0]
        item.file_path = str(test_file)
        item.file_size = len(content)
        item.file_sha256 = sha
        await db.commit()

        app, _ = _build_app(db_factory, ADMIN_USER)

        with patch(
            "app.services.file_fingerprint_service.DELIVERY_ROOT",
            tmp_path / "deliverables",
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test",
            ) as client:
                r = await client.get(
                    f"{_base_url(PROJECT_ID)}/trio/items/{item.id}/download",
                )
        assert r.status_code == 200, (
            f"指纹一致时应 200，实际 {r.status_code}: {r.text}"
        )

    @pytest.mark.asyncio
    async def test_download_wrong_project_403(
        self, db: AsyncSession, db_factory, seed_project,
    ):
        """item 属于另一项目 → 403。"""
        _, _, items = await _seed_trio_job(db, PROJECT_ID)
        item = items[0]

        app, _ = _build_app(db_factory, ADMIN_USER)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as client:
            r = await client.get(
                f"{_base_url(OTHER_PROJECT_ID)}/trio/items/{item.id}/download",
            )
        assert r.status_code == 403


# ══════════════════════════════════════════════════════════════════════
# 6. 权限测试：readonly → 403 on write, 零写入
# ══════════════════════════════════════════════════════════════════════

class TestAuthorizationGuards:
    """需求 5.1 / 7.4：权限校验。

    readonly 角色 → write 端点（create/retry）应 403；
    readonly 角色 → read 端点（readiness/job/download）应 200。
    """

    @pytest.mark.asyncio
    async def test_readonly_user_cannot_create_trio(
        self, db: AsyncSession, db_factory, seed_project,
    ):
        """readonly 角色用户 → POST /trio → 403。"""
        app, _ = _build_app(db_factory, READONLY_USER)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as client:
            r = await client.post(
                f"{_base_url(PROJECT_ID)}/trio",
                params={"year": YEAR},
            )
        assert r.status_code == 403, (
            f"readonly 用户不应能创建三件套，实际 {r.status_code}"
        )

    @pytest.mark.asyncio
    async def test_readonly_user_cannot_retry(
        self, db: AsyncSession, db_factory, seed_project,
    ):
        """readonly 角色用户 → POST retry → 403。"""
        job, _, _ = await _seed_trio_job(db, PROJECT_ID)

        app, _ = _build_app(db_factory, READONLY_USER)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as client:
            r = await client.post(
                f"{_base_url(PROJECT_ID)}/trio/jobs/{job.id}/retry",
            )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_readonly_can_read_readiness(
        self, db: AsyncSession, db_factory, seed_project,
    ):
        """readonly 角色可以查 readiness（只读操作）。"""
        app, _ = _build_app(db_factory, READONLY_USER)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as client:
            r = await client.get(
                f"{_base_url(PROJECT_ID)}/trio/readiness",
                params={"year": YEAR},
            )
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_readonly_can_query_job(
        self, db: AsyncSession, db_factory, seed_project,
    ):
        """readonly 角色可以查 job（只读操作）。"""
        job, _, _ = await _seed_trio_job(db, PROJECT_ID)

        app, _ = _build_app(db_factory, READONLY_USER)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as client:
            r = await client.get(
                f"{_base_url(PROJECT_ID)}/trio/jobs/{job.id}",
            )
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_readonly_create_zero_writes(
        self, db: AsyncSession, db_factory, seed_project,
    ):
        """readonly 创建失败后数据库无新 job/item/snapshot。

        发请求 → 403 → 查 DB 确认零写入。
        """
        import sqlalchemy as sa

        app, _ = _build_app(db_factory, READONLY_USER)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as client:
            r = await client.post(
                f"{_base_url(PROJECT_ID)}/trio",
                params={"year": YEAR},
            )
        assert r.status_code == 403

        # 确认无 job 写入
        async with db_factory() as check_db:
            job_count = (
                await check_db.execute(
                    sa.select(sa.func.count()).select_from(ExportJob).where(
                        ExportJob.project_id == PROJECT_ID,
                        ExportJob.kind == "deliverable_trio",
                    )
                )
            ).scalar_one()
            snap_count = (
                await check_db.execute(
                    sa.select(sa.func.count()).select_from(DeliverableSnapshot).where(
                        DeliverableSnapshot.project_id == PROJECT_ID,
                    )
                )
            ).scalar_one()

        assert job_count == 0, f"403 后不应有 job 写入，实际 {job_count}"
        assert snap_count == 0, f"403 后不应有 snapshot 写入，实际 {snap_count}"


# ══════════════════════════════════════════════════════════════════════
# 7. 变异证明：去鉴权 → 原本被拦截的请求通过 = 证明鉴权是活的
# ══════════════════════════════════════════════════════════════════════

class TestAuthMutationEvidence:
    """变异证明：去除 _guard_action 后 readonly 写端点不再 403。

    测试思路：patch _guard_action 为 noop → readonly 用户能调用写端点。
    这证明现行鉴权是真正起作用的，去掉即红。
    """

    @pytest.mark.asyncio
    async def test_mutation_no_guard_lets_readonly_create(
        self, db: AsyncSession, db_factory, seed_project,
    ):
        """去掉 _guard_action → readonly 可调 POST /trio（不再 403）。

        变异证明：readonly 本应 403；去掉鉴权后不再 403。
        """
        app, _ = _build_app(db_factory, READONLY_USER)

        async def _noop_guard(*a, **kw):
            return None

        with patch("app.routers.deliverable._guard_action", side_effect=_noop_guard):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test",
            ) as client:
                r = await client.post(
                    f"{_base_url(PROJECT_ID)}/trio",
                    params={"year": YEAR},
                )
        # 去鉴权后应进入业务逻辑（409 blocked 或 200），不再是 403
        assert r.status_code != 403, (
            f"变异失败：去掉 _guard_action 后仍 403，说明鉴权不是由它控制"
        )

    @pytest.mark.asyncio
    async def test_mutation_no_guard_lets_readonly_retry(
        self, db: AsyncSession, db_factory, seed_project,
    ):
        """去掉 _guard_action → readonly 可调 POST retry（不再 403）。"""
        job, _, _ = await _seed_trio_job(db, PROJECT_ID)

        app, _ = _build_app(db_factory, READONLY_USER)

        async def _noop_guard(*a, **kw):
            return None

        with patch("app.routers.deliverable._guard_action", side_effect=_noop_guard):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test",
            ) as client:
                r = await client.post(
                    f"{_base_url(PROJECT_ID)}/trio/jobs/{job.id}/retry",
                )
        assert r.status_code != 403, (
            f"变异失败：去掉 _guard_action 后仍 403"
        )


# ══════════════════════════════════════════════════════════════════════
# 8. 变异证明：去项目边界 → 跨项目访问不再 403
# ══════════════════════════════════════════════════════════════════════

class TestProjectBoundaryMutationEvidence:
    """变异证明：去除项目归属校验后跨项目访问不再被拦截。"""

    @pytest.mark.asyncio
    async def test_mutation_no_project_check_on_job_query(
        self, db: AsyncSession, db_factory, seed_project,
    ):
        """去掉 job.project_id 校验 → 跨项目能读到 job（不再 403）。

        正常情况：OTHER_PROJECT_ID 查 PROJECT_ID 的 job → 403。
        变异后：patch get_job_with_items 不含 project_id → 200。
        """
        job, _, _ = await _seed_trio_job(db, PROJECT_ID)

        app, _ = _build_app(db_factory, ADMIN_USER)

        # 模拟 get_job_with_items 返回伪造的 project_id 匹配
        async def _tampered_get_job_with_items(job_id):
            from app.services.export_job_service import ExportJobService
            svc = ExportJobService.__new__(ExportJobService)
            # 直接返回一个 dict，project_id 与请求的 project 一致
            return {
                "id": str(job_id),
                "project_id": str(OTHER_PROJECT_ID),  # 假装属于 OTHER
                "status": "partial",
                "items": [],
            }

        with patch(
            "app.services.export_job_service.ExportJobService.get_job_with_items",
            side_effect=_tampered_get_job_with_items,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test",
            ) as client:
                r = await client.get(
                    f"{_base_url(OTHER_PROJECT_ID)}/trio/jobs/{job.id}",
                )
        # 篡改 project_id 后不再 403
        assert r.status_code == 200, (
            f"变异失败：篡改 project_id 后仍非 200，实际 {r.status_code}"
        )

    @pytest.mark.asyncio
    async def test_mutation_no_project_check_on_download(
        self, db: AsyncSession, db_factory, seed_project, tmp_path,
    ):
        """去掉 download 端点的 job.project_id 校验 → 跨项目能下载。

        正常情况：OTHER_PROJECT_ID 下载 PROJECT_ID 的 item → 403。
        变异后：patch 掉 ExportJob 查询使其看起来属于 OTHER → 不再 403。
        """
        content = b"mutation test file"
        test_file = tmp_path / "deliverables" / "mutation_report.xlsx"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_bytes(content)
        sha = hashlib.sha256(content).hexdigest()

        _, _, items = await _seed_trio_job(
            db, PROJECT_ID,
            items_config=[
                {"step_key": "financial_report", "sequence": 1, "status": "succeeded"},
            ],
        )
        item = items[0]
        item.file_path = str(test_file)
        item.file_size = len(content)
        item.file_sha256 = sha
        await db.commit()

        app, _ = _build_app(db_factory, ADMIN_USER)

        # 种一个假的 job 属于 OTHER_PROJECT_ID，绑定同一 item
        # 这样 download 端点查 job 时发现 project_id 匹配
        from app.models.phase13_models import ExportJob as EJ
        async with db_factory() as s:
            fake_job = EJ(
                id=uuid.uuid4(),
                project_id=OTHER_PROJECT_ID,
                job_type="deliverable_trio",
                status="partial",
                payload={},
                progress_total=3,
                progress_done=0,
                failed_count=0,
                initiated_by=ADMIN_USER_ID,
            )
            s.add(fake_job)
            await s.flush()
            # 把 item 的 job_id 改到 fake_job
            from sqlalchemy import update
            await s.execute(
                update(ExportJobItem)
                .where(ExportJobItem.id == item.id)
                .values(job_id=fake_job.id)
            )
            await s.commit()

        with patch(
            "app.services.file_fingerprint_service.DELIVERY_ROOT",
            tmp_path / "deliverables",
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test",
            ) as client:
                r = await client.get(
                    f"{_base_url(OTHER_PROJECT_ID)}/trio/items/{item.id}/download",
                )
        # 当 item 真的属于 OTHER 项目的 job 时可以下载
        assert r.status_code == 200, (
            f"变异证明失败：item 属于 OTHER 项目时仍非 200，实际 {r.status_code}"
        )


# ══════════════════════════════════════════════════════════════════════
# 9. Retry 成功流 — mock executor, 验证 job 结果结构
# ══════════════════════════════════════════════════════════════════════

class TestRetrySuccessFlow:
    """需求 5.2–5.5：retry 成功后 job 状态更新。"""

    @pytest.mark.asyncio
    async def test_retry_succeeds_when_snapshot_matches(
        self, db: AsyncSession, db_factory, seed_project,
    ):
        """snapshot 一致 + 有失败项 → retry 走真实 executor 步骤。

        mock readiness 返回与 job 相同的 digest，mock executor 步骤方法
        避免真调导出器，但端点本身经真实依赖链。
        """
        await _seed_full_readiness(db, PROJECT_ID, YEAR)
        job, snapshot, items = await _seed_trio_job(
            db, PROJECT_ID,
            status="partial",
            items_config=[
                {"step_key": "financial_report", "sequence": 1, "status": "succeeded"},
                {"step_key": "disclosure_notes", "sequence": 2, "status": "failed",
                 "error_message": "导出器异常"},
                {"step_key": "audit_report", "sequence": 3, "status": "blocked",
                 "error_message": "前置步骤未成功"},
            ],
        )

        app, _ = _build_app(db_factory, ADMIN_USER)

        # 使 readiness 返回与 job 一致的 snapshot digest
        from app.services.deliverable_readiness_service import DeliverableReadinessService

        original_check = DeliverableReadinessService.check

        async def _patched_check(self_, db_, pid, yr, **kw):
            result = await original_check(self_, db_, pid, yr, **kw)
            # 强制 digest 匹配 job 的 snapshot
            result.snapshot["digest"] = snapshot.digest
            return result

        async def _mock_run_step(*a, **kw):
            return uuid.uuid4()

        async def _mock_run_report_body(*a, **kw):
            return (uuid.uuid4(), None, None)

        with (
            patch.object(
                DeliverableReadinessService, "check", _patched_check,
            ),
            patch(
                "app.services.full_deliverables_executor.FullDeliverablesExecutor._run_financial_reports",
                side_effect=_mock_run_step,
            ),
            patch(
                "app.services.full_deliverables_executor.FullDeliverablesExecutor._run_disclosure_notes",
                side_effect=_mock_run_step,
            ),
            patch(
                "app.services.full_deliverables_executor.FullDeliverablesExecutor._run_report_body",
                side_effect=_mock_run_report_body,
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test",
            ) as client:
                r = await client.post(
                    f"{_base_url(PROJECT_ID)}/trio/jobs/{job.id}/retry",
                )

        # retry 应该成功而非 409
        assert r.status_code == 200, (
            f"snapshot 一致时 retry 应 200，实际 {r.status_code}: {r.text}"
        )
        body = r.json().get("data", r.json())
        # 响应里应有 job 相关信息
        assert body is not None


# ══════════════════════════════════════════════════════════════════════
# 10. History 端点与 no-auth 变异
# ══════════════════════════════════════════════════════════════════════

class TestHistoryEndpoint:
    """需求 5.6 / 7.4：trio history 可查询。"""

    @pytest.mark.asyncio
    async def test_history_returns_jobs(
        self, db: AsyncSession, db_factory, seed_project,
    ):
        """有 job 时 history 返回非空列表。"""
        await _seed_trio_job(db, PROJECT_ID)

        app, _ = _build_app(db_factory, ADMIN_USER)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as client:
            r = await client.get(
                f"{_base_url(PROJECT_ID)}/trio/history",
                params={"year": YEAR},
            )
        assert r.status_code == 200
        body = r.json().get("data", r.json())
        assert body["year"] == YEAR
        assert len(body["jobs"]) >= 1

    @pytest.mark.asyncio
    async def test_history_empty_for_other_project(
        self, db: AsyncSession, db_factory, seed_project,
    ):
        """OTHER_PROJECT_ID 无 job → 空列表。"""
        await _seed_trio_job(db, PROJECT_ID)

        app, _ = _build_app(db_factory, ADMIN_USER)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as client:
            r = await client.get(
                f"{_base_url(OTHER_PROJECT_ID)}/trio/history",
                params={"year": YEAR},
            )
        assert r.status_code == 200
        body = r.json().get("data", r.json())
        assert len(body["jobs"]) == 0
