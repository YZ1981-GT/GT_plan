"""Phase4 交付中心 — trio 端点与项目级鉴权（spec chain-closure-phase4 Task 9）。

覆盖 design §4.4 / 需求 1.6, 3.5, 5.1, 5.6, 7.4：

- readiness(readonly) / 状态(readonly) / 下载(readonly) / 创建(edit) / 重试(edit)
  经 ``require_project_access`` **真依赖链**校验项目级权限；
- TestClient **真请求**（httpx ASGITransport），真 SQLite + 真 ``ProjectUser`` 行，
  override 的是**内层** ``get_db`` / ``get_current_user``，让真实 ``assert_project_permission``
  跑起来（铁律㉕：依赖工厂直接 override 会静默失效）；
- ready / blocked readiness；
- job 属主项目校验：错项目 → 403；
- 403 零写入：只读成员 POST 创建 → 403 且无 ExportJob 落库；
- 重试快照冲突 → 409；
- 下载前物理哈希校验：文件缺失 → 404 / 被篡改（size/sha 不符）→ 409，均不返回文件；
- **变异证明**：
    * 用 AST 确认每个端点**真的**声明了 ``require_project_access`` 依赖（铁律㉖，非文本匹配）；
    * 非成员访问任一端点必 403（去掉鉴权依赖这条就会变绿 → 红）；
    * 错项目 job/item 必 403（把归属校验改成恒真就会变绿 → 红）。
"""

from __future__ import annotations

import ast
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, PermissionLevel, ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.models.phase13_models import ExportJob, ExportJobItem, ExportJobStatus
from app.routers.deliverable_trio import router as trio_router

YEAR = 2025


# ===================================================================
# fixtures
# ===================================================================


@pytest_asyncio.fixture
async def test_db():
    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

    SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


async def _make_user(db: AsyncSession, username: str, role: str = "auditor") -> User:
    u = User(
        id=uuid.uuid4(),
        username=username,
        email=f"{username}@test.com",
        hashed_password="hashed",
        role=UserRole(role),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_project(db: AsyncSession, name: str = "P", *, ready: bool = False) -> Project:
    project = Project(
        id=uuid.uuid4(),
        name=name,
        client_name=f"{name}公司",
        status="created",
        template_type="soe" if ready else None,
        report_scope="standalone",
        audit_year=YEAR if ready else None,
        accounting_standard_id=uuid.uuid4() if ready else None,
    )
    db.add(project)
    await db.flush()
    return project


async def _add_member(
    db: AsyncSession, project: Project, user: User, level: str
) -> ProjectUser:
    pu = ProjectUser(
        project_id=project.id,
        user_id=user.id,
        role=ProjectUserRole.auditor,
        permission_level=PermissionLevel(level),
    )
    db.add(pu)
    await db.flush()
    return pu


def _build_client(db: AsyncSession, current_user: User) -> AsyncClient:
    """最小 app：仅挂 trio 路由，override 内层 get_db / get_current_user。

    关键（铁律㉕）：**不** override ``require_project_access`` 本身（它每次返回新函数对象，
    override 必静默失效）。只 override 它内部依赖的 ``get_db`` / ``get_current_user``，
    使真实 ``assert_project_permission`` 对真 ``ProjectUser`` 行作判定。
    """
    app = FastAPI()
    app.include_router(trio_router)

    async def _override_db():
        yield db

    async def _override_user():
        return current_user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ===================================================================
# 1. readiness：ready / blocked / 403
# ===================================================================


class TestReadiness:
    @pytest.mark.asyncio
    async def test_readiness_blocked_for_incomplete_project(self, test_db):
        """空项目（缺准则/模板/年度 + phase3 能力探测）→ status=blocked + 中文阻断项。"""
        user = await _make_user(test_db, "u_block")
        project = await _make_project(test_db, "空项目", ready=False)
        await _add_member(test_db, project, user, "readonly")

        async with _build_client(test_db, user) as client:
            resp = await client.get(
                f"/api/projects/{project.id}/deliverables/trio/readiness",
                params={"year": YEAR},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "blocked"
        assert len(body["hard_blockers"]) > 0
        # 中文原因存在
        assert any(g["message"] for g in body["hard_blockers"])

    @pytest.mark.asyncio
    async def test_readiness_non_member_403(self, test_db):
        """非项目成员访问 readiness → 403（鉴权真生效的变异证明：去掉依赖即变绿）。"""
        user = await _make_user(test_db, "u_outsider")
        project = await _make_project(test_db, "他人项目", ready=False)
        # 不加 member

        async with _build_client(test_db, user) as client:
            resp = await client.get(
                f"/api/projects/{project.id}/deliverables/trio/readiness",
                params={"year": YEAR},
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_readiness_readonly_member_allowed(self, test_db):
        """只读成员可读 readiness（readonly 门禁放行，返回 200 判定结果）。"""
        user = await _make_user(test_db, "u_ro")
        project = await _make_project(test_db, "就绪项目", ready=False)
        await _add_member(test_db, project, user, "readonly")

        async with _build_client(test_db, user) as client:
            resp = await client.get(
                f"/api/projects/{project.id}/deliverables/trio/readiness",
                params={"year": YEAR},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] in ("ready", "ready_with_warnings", "blocked")


# ===================================================================
# 2. 创建（edit）：403 零写入
# ===================================================================


class TestCreateTrioAuthz:
    @pytest.mark.asyncio
    async def test_readonly_member_cannot_create_and_zero_writes(self, test_db):
        """只读成员 POST 创建三件套 → 403，且**零写入**（无 ExportJob 落库）。"""
        user = await _make_user(test_db, "u_ro2")
        project = await _make_project(test_db, "就绪项目", ready=True)
        await _add_member(test_db, project, user, "readonly")

        async with _build_client(test_db, user) as client:
            resp = await client.post(
                f"/api/projects/{project.id}/deliverables/trio",
                json={"year": YEAR},
            )
        assert resp.status_code == 403

        # 403 零写入：没有任何 ExportJob 被创建
        count = (
            await test_db.execute(sa.select(sa.func.count()).select_from(ExportJob))
        ).scalar_one()
        assert count == 0, "403 不得留下任何 ExportJob（零写入）"

    @pytest.mark.asyncio
    async def test_non_member_cannot_create(self, test_db):
        """非成员 POST 创建 → 403。"""
        user = await _make_user(test_db, "u_out2")
        project = await _make_project(test_db, "他人项目", ready=True)

        async with _build_client(test_db, user) as client:
            resp = await client.post(
                f"/api/projects/{project.id}/deliverables/trio",
                json={"year": YEAR},
            )
        assert resp.status_code == 403


# ===================================================================
# 3. job 属主项目校验：错项目 → 403
# ===================================================================


class TestJobOwnership:
    @pytest.mark.asyncio
    async def test_get_job_wrong_project_403(self, test_db):
        """job 属于项目 A，经项目 B 查询（B 成员）→ 403（铁律㉗：按 job.project_id 真校验）。"""
        user = await _make_user(test_db, "u_cross")
        proj_a = await _make_project(test_db, "项目A")
        proj_b = await _make_project(test_db, "项目B")
        # 用户是 B 的 edit 成员，但 job 属于 A
        await _add_member(test_db, proj_b, user, "edit")

        job = ExportJob(
            project_id=proj_a.id,
            job_type="full_deliverables",
            status=ExportJobStatus.succeeded.value,
            payload={"year": YEAR},
            initiated_by=user.id,
        )
        test_db.add(job)
        await test_db.flush()

        async with _build_client(test_db, user) as client:
            resp = await client.get(
                f"/api/projects/{proj_b.id}/deliverables/trio/jobs/{job.id}"
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_get_job_same_project_ok(self, test_db):
        """job 属于项目 A，经项目 A 查询（A 成员）→ 200。"""
        user = await _make_user(test_db, "u_same")
        proj_a = await _make_project(test_db, "项目A")
        await _add_member(test_db, proj_a, user, "readonly")

        job = ExportJob(
            project_id=proj_a.id,
            job_type="full_deliverables",
            status=ExportJobStatus.succeeded.value,
            payload={"year": YEAR},
            initiated_by=user.id,
        )
        test_db.add(job)
        await test_db.flush()

        async with _build_client(test_db, user) as client:
            resp = await client.get(
                f"/api/projects/{proj_a.id}/deliverables/trio/jobs/{job.id}"
            )
        assert resp.status_code == 200
        assert resp.json()["id"] == str(job.id)


# ===================================================================
# 4. 重试：快照冲突 → 409
# ===================================================================


class TestRetryConflict:
    @pytest.mark.asyncio
    async def test_retry_snapshot_mismatch_409(self, test_db, monkeypatch):
        """重试时 executor 抛 SnapshotMismatchError → 409（绝不混用旧快照）。"""
        from app.services import export_job_service as ejs_mod
        from app.services.full_deliverables_executor import SnapshotMismatchError

        user = await _make_user(test_db, "u_retry")
        proj = await _make_project(test_db, "项目R")
        await _add_member(test_db, proj, user, "edit")

        job = ExportJob(
            project_id=proj.id,
            job_type="full_deliverables",
            status="partial_failed",
            payload={"year": YEAR},
            snapshot_id="oldsnap",
            initiated_by=user.id,
        )
        test_db.add(job)
        await test_db.flush()

        async def _boom(self, job_id, **kwargs):
            raise SnapshotMismatchError(
                "项目数据已变化，原交付快照不再有效",
                job_snapshot="oldsnap",
                current_snapshot="newsnap",
            )

        monkeypatch.setattr(ejs_mod.ExportJobService, "retry_failed", _boom)

        async with _build_client(test_db, user) as client:
            resp = await client.post(
                f"/api/projects/{proj.id}/deliverables/trio/jobs/{job.id}/retry"
            )
        assert resp.status_code == 409
        assert "快照" in str(resp.json()["detail"])

    @pytest.mark.asyncio
    async def test_retry_readonly_member_403(self, test_db):
        """只读成员重试 → 403（edit 门禁）。"""
        user = await _make_user(test_db, "u_retry_ro")
        proj = await _make_project(test_db, "项目R2")
        await _add_member(test_db, proj, user, "readonly")

        job = ExportJob(
            project_id=proj.id,
            job_type="full_deliverables",
            status="partial_failed",
            payload={"year": YEAR},
            initiated_by=user.id,
        )
        test_db.add(job)
        await test_db.flush()

        async with _build_client(test_db, user) as client:
            resp = await client.post(
                f"/api/projects/{proj.id}/deliverables/trio/jobs/{job.id}/retry"
            )
        assert resp.status_code == 403


# ===================================================================
# 5. 下载：物理指纹校验
# ===================================================================


async def _make_job_with_item(
    db: AsyncSession,
    project: Project,
    user: User,
    *,
    file_path: str | None,
    file_sha256: str | None = None,
    file_size: int | None = None,
) -> ExportJobItem:
    job = ExportJob(
        project_id=project.id,
        job_type="full_deliverables",
        status=ExportJobStatus.succeeded.value,
        payload={"year": YEAR},
        initiated_by=user.id,
    )
    db.add(job)
    await db.flush()
    item = ExportJobItem(
        job_id=job.id,
        step_key="financial_report",
        sequence=1,
        status=ExportJobStatus.succeeded.value,
        file_path=file_path,
        file_sha256=file_sha256,
        file_size=file_size,
    )
    db.add(item)
    await db.flush()
    return item


class TestDownloadFingerprint:
    @pytest.mark.asyncio
    async def test_download_missing_file_404(self, test_db, tmp_path):
        """file_path 指向不存在的文件 → 404（不返回文件、不冒充交付）。"""
        user = await _make_user(test_db, "u_dl1")
        proj = await _make_project(test_db, "项目D")
        await _add_member(test_db, proj, user, "readonly")
        missing = str(tmp_path / "ghost.xlsx")
        item = await _make_job_with_item(test_db, proj, user, file_path=missing)

        async with _build_client(test_db, user) as client:
            resp = await client.get(
                f"/api/projects/{proj.id}/deliverables/trio/items/{item.id}/download"
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_download_tampered_hash_409(self, test_db, tmp_path):
        """文件存在但 SHA-256 与版本记录不符（被篡改）→ 409，绝不返回被篡改文件。"""
        user = await _make_user(test_db, "u_dl2")
        proj = await _make_project(test_db, "项目D2")
        await _add_member(test_db, proj, user, "readonly")

        real = tmp_path / "report.xlsx"
        real.write_bytes(b"actual content")
        item = await _make_job_with_item(
            test_db, proj, user,
            file_path=str(real),
            file_sha256="0" * 64,  # 故意写错的哈希
            file_size=len(b"actual content"),
        )

        async with _build_client(test_db, user) as client:
            resp = await client.get(
                f"/api/projects/{proj.id}/deliverables/trio/items/{item.id}/download"
            )
        assert resp.status_code == 409
        assert "指纹" in str(resp.json()["detail"]) or "一致" in str(resp.json()["detail"])

    @pytest.mark.asyncio
    async def test_download_valid_file_streams(self, test_db, tmp_path):
        """文件存在且指纹一致 → 200 返回文件内容。"""
        import hashlib

        user = await _make_user(test_db, "u_dl3")
        proj = await _make_project(test_db, "项目D3")
        await _add_member(test_db, proj, user, "readonly")

        real = tmp_path / "report.xlsx"
        content = b"valid report bytes"
        real.write_bytes(content)
        item = await _make_job_with_item(
            test_db, proj, user,
            file_path=str(real),
            file_sha256=hashlib.sha256(content).hexdigest(),
            file_size=len(content),
        )

        async with _build_client(test_db, user) as client:
            resp = await client.get(
                f"/api/projects/{proj.id}/deliverables/trio/items/{item.id}/download"
            )
        assert resp.status_code == 200
        assert resp.content == content

    @pytest.mark.asyncio
    async def test_download_wrong_project_403(self, test_db, tmp_path):
        """item 的 job 属于项目 A，经项目 B（B 成员）下载 → 403（铁律㉗）。"""
        user = await _make_user(test_db, "u_dl_cross")
        proj_a = await _make_project(test_db, "项目DA")
        proj_b = await _make_project(test_db, "项目DB")
        await _add_member(test_db, proj_b, user, "readonly")

        real = tmp_path / "report.xlsx"
        real.write_bytes(b"x")
        item = await _make_job_with_item(test_db, proj_a, user, file_path=str(real))

        async with _build_client(test_db, user) as client:
            resp = await client.get(
                f"/api/projects/{proj_b.id}/deliverables/trio/items/{item.id}/download"
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_download_non_member_403(self, test_db, tmp_path):
        """非成员下载 → 403。"""
        user = await _make_user(test_db, "u_dl_out")
        proj = await _make_project(test_db, "项目DC")
        real = tmp_path / "report.xlsx"
        real.write_bytes(b"x")
        owner = await _make_user(test_db, "owner")
        item = await _make_job_with_item(test_db, proj, owner, file_path=str(real))

        async with _build_client(test_db, user) as client:
            resp = await client.get(
                f"/api/projects/{proj.id}/deliverables/trio/items/{item.id}/download"
            )
        assert resp.status_code == 403


# ===================================================================
# 6. AST 变异证明：端点真的声明了 require_project_access（铁律㉖，非文本匹配）
# ===================================================================


def _endpoint_authz_levels() -> dict[str, str]:
    """用 AST 解析 deliverable_trio.py，返回 {函数名: require_project_access 的 level}。

    只认**真正的依赖声明**：参数默认值形如 ``Depends(require_project_access("edit"))``。
    docstring 里写「权限：readonly」之类对 AST 不产生 Call 节点 ⇒ 天然排除（铁律㉖）。
    """
    src = Path(__file__).resolve().parents[1] / "app" / "routers" / "deliverable_trio.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    out: dict[str, str] = {}

    def _scan_defaults(fn: ast.AsyncFunctionDef | ast.FunctionDef) -> None:
        for default in fn.args.defaults + fn.args.kw_defaults:
            if default is None:
                continue
            # Depends(require_project_access("level"))
            if (
                isinstance(default, ast.Call)
                and isinstance(default.func, ast.Name)
                and default.func.id == "Depends"
                and default.args
                and isinstance(default.args[0], ast.Call)
                and isinstance(default.args[0].func, ast.Name)
                and default.args[0].func.id == "require_project_access"
                and default.args[0].args
                and isinstance(default.args[0].args[0], ast.Constant)
            ):
                out[fn.name] = default.args[0].args[0].value

    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            _scan_defaults(node)
    return out


def test_all_trio_endpoints_declare_project_authz():
    """每个 trio 端点函数都必须声明 require_project_access，且 level 符合读/写语义。

    这是变异守卫：谁把某端点的 ``require_project_access`` 依赖删掉或改成只验登录，
    本断言立刻变红（铁律㉖ 用 AST，不被 docstring 骗）。
    """
    levels = _endpoint_authz_levels()
    expected = {
        "get_trio_readiness": "readonly",
        "create_trio": "edit",
        "get_trio_job": "readonly",
        "get_trio_job_attempts": "readonly",
        "retry_trio_job": "edit",
        "download_trio_item": "readonly",
    }
    for fn, lvl in expected.items():
        assert fn in levels, f"{fn} 未声明 require_project_access 依赖（鉴权缺失）"
        assert levels[fn] == lvl, (
            f"{fn} 的项目权限级别应为 {lvl}，实际 {levels[fn]}"
        )
    # 没有多余未覆盖的端点（新端点必须进 expected 并补鉴权）
    assert set(levels) == set(expected), (
        f"端点集合与期望不一致：{set(levels) ^ set(expected)}"
    )
