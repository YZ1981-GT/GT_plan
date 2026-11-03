"""Task 5.3 · 全局模板 / 全局自定义函数写限 admin —— formula-manager-closure

spec: formula-manager-closure / Task 5.3 / 需求 5.4·15.2 / design §5 步骤 5 · ADR-FMC-06
      · §1 锚点 #7 / #10

## 这个文件在干什么

Task 5.1 坐实 IDOR、Task 5.2 加固对象型端点（wp_formula / formula-scope / tb_detail /
execute）。本文件专测 Task 5.3 的两类**全局写**收紧（5.2 已覆盖的不重复）：

  1. `report_config` CRUD（list/get/clone/update/create/delete/execute-batch）的
     **全局模板行**（applicable_standard ∈ {enterprise, listed, ...}，非 "project:{uuid}"）
     写操作 → **仅 admin**；非 admin 返 403。

  2. `report_config` 的**项目克隆行**（applicable_standard == "project:{uuid}"）写
     → require_project_access("edit")：项目成员（edit）通过、非成员 403。
     （= 全局模板 vs 项目克隆行的**写鉴权分流**，design §5 步骤 5。）

  3. `formula.py` 自定义函数**注册 / 注销**（全局能力）→ 仅 admin；非 admin 返 403。

## 鉴权口径 / 工装纪律（memory 教训㉕①）

🔴 禁覆盖 `require_role([...])` / `require_project_access(...)` 工厂本身（每次返回新
函数对象、作 dependency_overrides 的 key 对不上 → 静默失效）。只 override **内层**
`get_db` / `get_current_user`，让 require_role / assert_project_permission 的真实判定跑。

## 变异反证（memory 铁律㉖）

类 `TestMutationReverseAssertion` 临时把被测端点依赖降级回 `get_current_user`（去掉
admin 门控），断言非 admin 写**此时能通过**（坐实「门控确实在起作用」）；测试结束恢复，
不污染全局路由注册。
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, PermissionLevel, ProjectUserRole
from app.models.core import (
    Project,
    ProjectStatus,
    ProjectType,
    ProjectUser,
    User,
    UserRole,
)
from app.models.report_models import FinancialReportType, ReportConfig

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON


@pytest.fixture(autouse=True)
def _isolate_custom_functions():
    """自定义函数注册表自 ADR-FHIC-17 起是模块级单一注册表 ⇒ 每例结束注销它新注册的函数（admin 注册的 ``ADMFN`` 原先留在
    注册表里，同一进程后跑的 ``test_custom_dsl_coding`` 的 list 用例数到 3）。"""
    from app.services.formula_custom_functions import get_custom_registry, unregister_custom_function

    before = set(get_custom_registry())
    yield
    for name in set(get_custom_registry()) - before:
        unregister_custom_function(name)

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


class _Seed:
    def __init__(self) -> None:
        self.admin_id: uuid.UUID
        self.manager_id: uuid.UUID          # manager，项目 P 的 edit 成员
        self.manager_non_member_id: uuid.UUID  # manager，非项目 P 成员
        self.project_id: uuid.UUID
        self.global_config_id: uuid.UUID    # 全局模板行（applicable_standard=enterprise）
        self.project_config_id: uuid.UUID   # 项目克隆行（applicable_standard=project:{P}）


@pytest_asyncio.fixture
async def seed(db: AsyncSession) -> _Seed:
    s = _Seed()
    admin = User(id=uuid.uuid4(), username="admin_u", email="admin@e.com",
                 hashed_password="x", role=UserRole.admin)
    mgr = User(id=uuid.uuid4(), username="mgr_member", email="m1@e.com",
               hashed_password="x", role=UserRole.manager)
    mgr_out = User(id=uuid.uuid4(), username="mgr_nonmember", email="m2@e.com",
                   hashed_password="x", role=UserRole.manager)
    db.add_all([admin, mgr, mgr_out])

    proj = Project(id=uuid.uuid4(), name="项目P_2025", client_name="客户P",
                   project_type=ProjectType.annual, status=ProjectStatus.planning)
    db.add(proj)
    await db.flush()

    db.add(ProjectUser(id=uuid.uuid4(), project_id=proj.id, user_id=mgr.id,
                       role=ProjectUserRole.manager, permission_level=PermissionLevel.edit))

    global_cfg = ReportConfig(
        id=uuid.uuid4(), report_type=FinancialReportType.balance_sheet,
        row_number=1, row_code="BS-GLOBAL", row_name="全局模板行",
        applicable_standard="enterprise", formula="TB('1001','期末余额')",
        is_deleted=False,
    )
    project_cfg = ReportConfig(
        id=uuid.uuid4(), report_type=FinancialReportType.balance_sheet,
        row_number=2, row_code="BS-PROJ", row_name="项目克隆行",
        applicable_standard=f"project:{proj.id}", formula="TB('1002','期末余额')",
        is_deleted=False,
    )
    db.add_all([global_cfg, project_cfg])
    await db.flush()
    await db.commit()

    s.admin_id, s.manager_id, s.manager_non_member_id = admin.id, mgr.id, mgr_out.id
    s.project_id = proj.id
    s.global_config_id = global_cfg.id
    s.project_config_id = project_cfg.id
    return s


def _make_app(db: AsyncSession, user: User) -> FastAPI:
    from app.routers import (
        formula as formula_router,
        report_config as report_config_router,
    )
    app = FastAPI()
    app.include_router(report_config_router.router)
    app.include_router(formula_router.router)

    async def _override_db():
        yield db

    async def _override_user():
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    return app


async def _load(db: AsyncSession, uid: uuid.UUID) -> User:
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


# ══════════════════════════════════════════════════════════════════════════
# 1. 全局模板行写 → 仅 admin
# ══════════════════════════════════════════════════════════════════════════


class TestGlobalTemplateWriteAdminOnly:

    @pytest.mark.asyncio
    async def test_global_update_non_admin_forbidden(self, db, seed):
        """非 admin 改全局模板行 → 403。"""
        mgr = await _load(db, seed.manager_id)
        app = _make_app(db, mgr)
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.put(f"/api/report-config/{seed.global_config_id}",
                         json={"row_name": "非 admin 越权改全局"})
        assert resp.status_code == 403, f"非 admin 改全局模板应 403，实得 {resp.status_code}"

    @pytest.mark.asyncio
    async def test_global_update_admin_ok(self, db, seed):
        """admin 改全局模板行 → 通过（200）。"""
        admin = await _load(db, seed.admin_id)
        app = _make_app(db, admin)
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.put(f"/api/report-config/{seed.global_config_id}",
                         json={"row_name": "admin 改名 OK"})
        assert resp.status_code == 200, f"admin 改全局模板应 200，实得 {resp.status_code}: {resp.text}"

    @pytest.mark.asyncio
    async def test_global_create_non_admin_forbidden(self, db, seed):
        mgr = await _load(db, seed.manager_id)
        app = _make_app(db, mgr)
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.post("/api/report-config",
                          json={"report_type": "balance_sheet", "row_code": "NEW-G",
                                "row_name": "新全局行", "applicable_standard": "enterprise"})
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_global_create_admin_ok(self, db, seed):
        admin = await _load(db, seed.admin_id)
        app = _make_app(db, admin)
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.post("/api/report-config",
                          json={"report_type": "balance_sheet", "row_code": "NEW-G",
                                "row_name": "新全局行", "applicable_standard": "enterprise"})
        assert resp.status_code == 200, resp.text

    @pytest.mark.asyncio
    async def test_global_delete_non_admin_forbidden_zero_side_effect(self, db, seed):
        mgr = await _load(db, seed.manager_id)
        app = _make_app(db, mgr)
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.delete(f"/api/report-config/{seed.global_config_id}")
        assert resp.status_code == 403
        # 0 副作用：该行未被软删
        async with async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)() as s:
            row = (await s.execute(select(ReportConfig).where(
                ReportConfig.id == seed.global_config_id))).scalar_one()
            assert row.is_deleted is False, "非 admin 删除全局模板不得产生副作用"

    @pytest.mark.asyncio
    async def test_global_delete_admin_ok(self, db, seed):
        """admin 删全局行 = 删除公式位的发布（formula-global-settings-sync R2.2 / R9）：
        不带版本 428 且零写入；带当前版本 200 且行被软删、版本 +1。"""
        admin = await _load(db, seed.admin_id)
        with TestClient(_make_app(db, admin), raise_server_exceptions=False) as c:
            missing = c.delete(f"/api/report-config/{seed.global_config_id}")
        assert missing.status_code == 428, missing.text
        assert missing.json()["detail"]["error_code"] == "FORMULA_VERSION_REQUIRED"
        # 本文件各请求共用一个会话：428 路径回滚后实例已过期，重新载入身份再发下一请求
        admin = await _load(db, seed.admin_id)
        with TestClient(_make_app(db, admin), raise_server_exceptions=False) as c:
            resp = c.delete(f"/api/report-config/{seed.global_config_id}", params={"expected_version": 1})
        assert resp.status_code == 200, resp.text
        async with async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)() as s:
            row = (await s.execute(select(ReportConfig).where(
                ReportConfig.id == seed.global_config_id))).scalar_one()
        assert (row.is_deleted, row.formula_version) == (True, 2)


# ══════════════════════════════════════════════════════════════════════════
# 2. 项目克隆行写 → require_project_access("edit")
# ══════════════════════════════════════════════════════════════════════════


class TestProjectCloneRowWriteProjectAccess:

    @pytest.mark.asyncio
    async def test_project_row_update_member_ok(self, db, seed):
        """项目 edit 成员改项目克隆行 → 通过（全局模板限 admin 不误伤项目成员）。"""
        mgr = await _load(db, seed.manager_id)
        app = _make_app(db, mgr)
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.put(f"/api/report-config/{seed.project_config_id}",
                         json={"row_name": "项目成员改名"})
        assert resp.status_code == 200, f"项目成员改克隆行应 200，实得 {resp.status_code}: {resp.text}"

    @pytest.mark.asyncio
    async def test_project_row_update_non_member_forbidden(self, db, seed):
        """非项目成员（有 manager 角色）改项目克隆行 → 403（项目维度挡下）。"""
        out = await _load(db, seed.manager_non_member_id)
        app = _make_app(db, out)
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.put(f"/api/report-config/{seed.project_config_id}",
                         json={"row_name": "非成员越权"})
        assert resp.status_code == 403, f"非项目成员改克隆行应 403，实得 {resp.status_code}"

    @pytest.mark.asyncio
    async def test_project_row_update_admin_ok(self, db, seed):
        """admin 改项目克隆行 → 通过（admin 在 assert_project_permission 内放行）。"""
        admin = await _load(db, seed.admin_id)
        app = _make_app(db, admin)
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.put(f"/api/report-config/{seed.project_config_id}",
                         json={"row_name": "admin 改克隆行"})
        assert resp.status_code == 200, resp.text

    @pytest.mark.asyncio
    async def test_project_row_update_body_pid_mismatch_forbidden(self, db, seed):
        """body.project_id 与行归属不一致 → 403（不以入参冒充归属）。"""
        mgr = await _load(db, seed.manager_id)
        app = _make_app(db, mgr)
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.put(f"/api/report-config/{seed.project_config_id}",
                         json={"project_id": str(uuid.uuid4()), "row_name": "伪造 pid"})
        assert resp.status_code == 403, f"project_id 不一致应 403，实得 {resp.status_code}"


# ══════════════════════════════════════════════════════════════════════════
# 3. 自定义函数注册/注销 → 仅 admin
# ══════════════════════════════════════════════════════════════════════════


class TestCustomFunctionAdminOnly:

    @pytest.mark.asyncio
    async def test_register_non_admin_forbidden(self, db, seed):
        mgr = await _load(db, seed.manager_id)
        app = _make_app(db, mgr)
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.post("/api/formula/custom-functions",
                          json={"name": "MYFN", "expression": "a + b",
                                "param_names": ["a", "b"]})
        assert resp.status_code == 403, f"非 admin 注册自定义函数应 403，实得 {resp.status_code}"

    @pytest.mark.asyncio
    async def test_unregister_non_admin_forbidden(self, db, seed):
        mgr = await _load(db, seed.manager_id)
        app = _make_app(db, mgr)
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.delete("/api/formula/custom-functions/ANYFN")
        assert resp.status_code == 403, f"非 admin 注销自定义函数应 403，实得 {resp.status_code}"

    @pytest.mark.asyncio
    async def test_register_admin_passes_gate(self, db, seed):
        """admin 过 admin 门控（不因 403 被拦）；注册本身成功或因引擎/入参非 403 失败。"""
        admin = await _load(db, seed.admin_id)
        app = _make_app(db, admin)
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.post("/api/formula/custom-functions",
                          json={"name": "ADMFN", "expression": "a + b",
                                "param_names": ["a", "b"]})
        assert resp.status_code != 403, f"admin 不应被 admin 门控 403，实得 {resp.status_code}: {resp.text}"


# ══════════════════════════════════════════════════════════════════════════
# 4. 变异反证：摘掉 admin 门控 → 非 admin 写此时能通过（坐实门控真起作用）
# ══════════════════════════════════════════════════════════════════════════


class TestMutationReverseAssertion:

    @pytest.mark.asyncio
    async def test_mutation_global_update_without_admin_gate_passes(self, db, seed):
        """临时把 _authorize_report_config_write 换成 no-op（模拟摘掉 admin 门控），
        非 admin 改全局模板应**不再 403**（证明门控是真拦截，而非恒绿）。"""
        from app.routers import report_config as rc_mod

        orig = rc_mod._authorize_report_config_write

        async def _noop(db_, user_, std_):  # noqa: ANN001
            return None

        rc_mod._authorize_report_config_write = _noop  # type: ignore[assignment]
        try:
            mgr = await _load(db, seed.manager_id)
            app = _make_app(db, mgr)
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.put(f"/api/report-config/{seed.global_config_id}",
                             json={"row_name": "摘门控后应放行"})
            assert resp.status_code != 403, (
                f"摘掉 admin 门控后非 admin 写不应再 403（实得 {resp.status_code}）；"
                "若仍 403 说明门控被别处硬编码、变异反证无效"
            )
        finally:
            rc_mod._authorize_report_config_write = orig  # type: ignore[assignment]

    @pytest.mark.asyncio
    async def test_mutation_register_without_admin_gate_passes(self, db, seed):
        """对照：一个与 register_custom_function 同签名但**无 admin 门控**（仅
        get_current_user）的等价端点，非 admin 注册应**不再 403** —— 证明生产端点的 403
        确来自 require_role(["admin"]) 门控而非其他（manager 角色本身无其它拦截）。"""
        from fastapi import Depends, FastAPI as _FastAPI

        mgr = await _load(db, seed.manager_id)

        probe = _FastAPI()

        # 对照端点刻意**只挂 get_current_user**（无 admin 门控）、不取 body：
        # 变异反证的被测点是「admin 门控」本身，与 body 解析无关。若此处声明
        # Pydantic body 参数，FastAPI 在方法内闭包作用域下用 get_type_hints 解析该
        # 模型注解会失败、把 body 误当 query 参数 → 422（与门控无关的工装噪声），
        # 反而掩盖「manager 本身未被其它拦截」这一真正要证的点。故不取 body。
        @probe.post("/api/formula/custom-functions")
        async def _probe_register(  # noqa: ANN202
            current_user: User = Depends(get_current_user),
        ):
            return {"ok": True, "role": current_user.role.value}

        async def _override_user():
            return mgr

        probe.dependency_overrides[get_current_user] = _override_user
        with TestClient(probe, raise_server_exceptions=False) as c:
            resp = c.post("/api/formula/custom-functions",
                          json={"name": "X", "expression": "a", "param_names": ["a"]})
        assert resp.status_code != 403, (
            "无 admin 门控的等价端点非 admin 不应 403 —— 证明 403 来自真实门控而非其他"
        )
        assert resp.json().get("role") == "manager", (
            "manager 角色本身不触发其它拦截 —— 证明生产端点 403 确来自 require_role 门控"
        )


# ══════════════════════════════════════════════════════════════════════════
# 5. runtime-integrity：历史未覆盖旁路 + 后端函数 preflight
# ══════════════════════════════════════════════════════════════════════════


class TestFormulaRuntimeIntegritySecurity:

    @pytest.mark.asyncio
    async def test_project_standard_list_and_types_require_membership(self, db, seed):
        outsider = await _load(db, seed.manager_non_member_id)
        app = _make_app(db, outsider)
        standard = f"project:{seed.project_id}"
        with TestClient(app, raise_server_exceptions=False) as c:
            list_resp = c.get("/api/report-config", params={"applicable_standard": standard})
            types_resp = c.get("/api/report-config/types", params={"applicable_standard": standard})
        assert list_resp.status_code == 403
        assert types_resp.status_code == 403

    @pytest.mark.asyncio
    async def test_project_and_standard_mismatch_is_forbidden(self, db, seed):
        mgr = await _load(db, seed.manager_id)
        app = _make_app(db, mgr)
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get(
                "/api/report-config/types",
                params={
                    "project_id": str(seed.project_id),
                    "applicable_standard": f"project:{uuid.uuid4()}",
                },
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_seed_is_admin_only(self, db, seed):
        mgr = await _load(db, seed.manager_id)
        app = _make_app(db, mgr)
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.post("/api/report-config/seed")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_report_execute_requires_project_membership(self, db, seed):
        outsider = await _load(db, seed.manager_non_member_id)
        app = _make_app(db, outsider)
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.post(
                "/api/report-config/execute-formula",
                json={
                    "project_id": str(seed.project_id),
                    "year": 2025,
                    "formula": "TB('1001','期末余额')",
                },
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_formula_batch_requires_membership(self, db, seed):
        outsider = await _load(db, seed.manager_non_member_id)
        app = _make_app(db, outsider)
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.post(
                "/api/formula/batch-execute",
                json=[{
                    "project_id": str(seed.project_id),
                    "year": 2025,
                    "formula_type": "TB",
                    "params": {},
                }],
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_formula_batch_rejects_mixed_project_or_year(self, db, seed):
        mgr = await _load(db, seed.manager_id)
        app = _make_app(db, mgr)
        base = {
            "project_id": str(seed.project_id),
            "year": 2025,
            "formula_type": "TB",
            "params": {},
        }
        with TestClient(app, raise_server_exceptions=False) as c:
            mixed_project = c.post(
                "/api/formula/batch-execute",
                json=[base, {**base, "project_id": str(uuid.uuid4())}],
            )
            mixed_year = c.post(
                "/api/formula/batch-execute",
                json=[base, {**base, "year": 2024}],
            )
        assert mixed_project.status_code == 422
        assert mixed_year.status_code == 422

    @pytest.mark.asyncio
    async def test_report_execution_rejects_unsupported_function_before_zero_fallback(self, db, seed):
        mgr = await _load(db, seed.manager_id)
        app = _make_app(db, mgr)
        with TestClient(app, raise_server_exceptions=False) as c:
            single = c.post(
                "/api/report-config/execute-formula",
                json={
                    "project_id": str(seed.project_id),
                    "year": 2025,
                    "formula": "PREV('1001')",
                },
            )
            batch = c.post(
                "/api/report-config/execute-formulas-batch",
                json={
                    "project_id": str(seed.project_id),
                    "year": 2025,
                    "formulas": [{"row_code": "BS-X", "formula": "AUX('客户')"}],
                },
            )
        assert single.status_code == 422
        assert batch.status_code == 422
        assert "FORMULA_FUNCTION_UNSUPPORTED" in single.text
        assert "FORMULA_FUNCTION_UNSUPPORTED" in batch.text
