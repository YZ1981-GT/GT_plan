"""FM-P0-05 跨项目越权（IDOR）TestClient 坐实 —— Phase 5 Task 5.1（前置·先坐实）

spec: formula-manager-closure / Task 5.1 / 需求 5.1·5.2·5.8 / design §6.1 · ADR-FMC-06
      · §1 锚点 #4 / #7 / #9 / #10 / #11

## 这个文件在干什么

ADR-FMC-06 把 FM-P0-05「项目隔离缺失」定级为**静态高危·待 TestClient 坐实**：
`wp_formula` / `report_config` / `/api/formula/execute` / `formula-scope` / `tb_detail`
诸端点在 §1 现状 grep 全部实测仅 `Depends(get_current_user)`（或仅 `require_role`
角色门控，非项目门控），路径只有对象 id、无项目级反查、无 `require_project_access`。
但**整改前未执行过任何跨项目越权探测**，不能把推断当事故。

本用例以**项目 A 凭据**（user_a 是 A 的成员、不是 B 的成员）对**项目 B 的资源**
分别发读 / 写 / 执行请求，分两层断言：

  · `TestCrossProjectBaseline` —— **恒通过**，只**记录并打印**每个端点的**加固前**
    实际响应码（坐实 / 推翻 IDOR 的证据，需求 5.8）。本任务只坐实、记录基线。

  · `TestCrossProjectHardened` —— 用例写成「**加固后**应断言的形态」：全部 403 +
    0 副作用（目标项目 B 数据无变更）。当前 Phase 5 加固（Task 5.2 / 5.3）尚未合入，
    故整类标 `xfail(strict=False)`：现在 red（证明 IDOR 存在），5.2 / 5.3 加固后
    自动转 xpass → 届时去掉 xfail 标记转正（本文件即门禁断言⑦的硬前置）。

## 关键纪律（memory 教训㉕①）

🔴 **禁直接覆盖 `require_project_access` / `require_role` 工厂** —— 它们是依赖工厂，
每次调用返回**新的函数对象**，作为 `dependency_overrides` 的 key 与路由里已绑定的
那个不是同一对象 ⇒ override 静默失效（全部请求意外 401）。正确做法 = override 其
**内层**依赖 `get_current_user` / `get_db`，让 `assert_project_permission` /
`require_role` 的**真实判定**跑起来。加固后：user_a（manager 角色、但不是 B 的
`ProjectUser`）→ `assert_project_permission` 查无成员记录 → 真实 403。

## 鉴权口径穷举（避免漏判别名，需求 5.1）

坐实的是「**项目级**隔离」，不是「登录了没有」。平台真实的项目级鉴权形态（取自
`backend/tests/test_project_endpoint_authorization_baseline.py` 的 `_PROJECT_LEVEL_TOKENS`
现算清单）为：`require_project_access` / `assert_project_permission` /
`require_project_permission` / `require_project_delegator`(_pid) /
`require_wp_edit_permission` / `require_query_builder_access` / `dedicated_wp_gate` /
`authorize_wp_read` / `authorize_wp_edit` / `authorize_object` / `ownership_guard` /
`require_operation` 等。仅 `get_current_user` / `require_role` 属**身份/角色**门控，
**不含项目维度** ⇒ 挂了它们仍可被任意登录用户用于访问任意项目（本用例即坐实这一点）。
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
from app.models.workpaper_models import (
    WorkingPaper,
    WpFileStatus,
    WpFormula,
    WpIndex,
    WpReviewStatus,
    WpSourceType,
    WpStatus,
)

# SQLite 没有 JSONB —— 用 JSON 渲染（与既有鉴权端点测试同款）。
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
_YEAR = 2025


# ── fixtures ───────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


class _Seed:
    """一套最小跨项目越权场景的 id 集合。"""

    def __init__(self) -> None:
        self.user_a_id: uuid.UUID
        self.project_a_id: uuid.UUID
        self.project_b_id: uuid.UUID
        self.b_wp_id: uuid.UUID
        self.b_config_id: uuid.UUID
        self.b_wp_formula_id: uuid.UUID


@pytest_asyncio.fixture
async def seed(db: AsyncSession) -> _Seed:
    """建 user_a（manager 角色）、项目 A/B，user_a 只是 A 的成员；B 侧各资源各一条。

    - user_a 角色取 **manager**：落在 `save_tb_detail_formulas` 的
      `require_role(["admin","partner","signing_partner","manager"])` 允许集内，
      使该写端点的**角色门控放行** → 正好坐实「角色门控 ≠ 项目门控」：加固前 manager
      可写**任意项目** tb_detail，加固后须被项目归属校验挡下。
    - user_a 对 **A** 有 `edit` 成员记录、对 **B** 无任何 `ProjectUser` 记录
      ⇒ 加固后 `assert_project_permission(B)` 查无成员 → 真实 403。
    """
    s = _Seed()

    user_a = User(
        id=uuid.uuid4(),
        username="user_a_manager",
        email="user_a@example.com",
        hashed_password="x",  # NOT NULL；值无关（鉴权走 override 的 get_current_user）
        role=UserRole.manager,
    )
    db.add(user_a)

    proj_a = Project(
        id=uuid.uuid4(),
        name="项目A_2025",
        client_name="客户A",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
    )
    proj_b = Project(
        id=uuid.uuid4(),
        name="项目B_2025",
        client_name="客户B",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
    )
    db.add_all([proj_a, proj_b])
    await db.flush()

    # user_a 仅是 A 的成员（edit），对 B 无成员记录。
    db.add(
        ProjectUser(
            id=uuid.uuid4(),
            project_id=proj_a.id,
            user_id=user_a.id,
            role=ProjectUserRole.manager,
            permission_level=PermissionLevel.edit,
        )
    )

    # ── 项目 B 侧资源 ──
    # 用一个既非 E1、也非 D-cycle 的中性 wp_code（"Z1"）：list_formulas 的 surfaced /
    # extraction 旁支对它一律短路（返回 [] / None），GET 可干净返 200，便于观察鉴权。
    b_wp_index = WpIndex(
        id=uuid.uuid4(),
        project_id=proj_b.id,
        wp_code="Z1",
        wp_name="Z1 中性底稿",
        status=WpStatus.not_started,
        is_deleted=False,
    )
    db.add(b_wp_index)
    await db.flush()

    b_wp = WorkingPaper(
        id=uuid.uuid4(),
        project_id=proj_b.id,
        wp_index_id=b_wp_index.id,
        file_path="/tmp/b_z1.xlsx",
        source_type=WpSourceType.template,
        status=WpFileStatus.draft,
        review_status=WpReviewStatus.not_submitted,
        is_deleted=False,
    )
    db.add(b_wp)
    await db.flush()

    # B 的既有 wp_formula 一条（供越权读 / 作越权写的 0-副作用基线对照）。
    b_formula = WpFormula(
        id=uuid.uuid4(),
        project_id=proj_b.id,
        wp_id=b_wp.id,
        sheet_name="Z1-1",
        target_cell="B2",
        expression="1 + 1",
        category="auto_calc",
        description="B 项目既有公式（越权写不得改动它）",
        created_by=None,
    )
    db.add(b_formula)

    # B 的报表配置行一条（project-scoped clone，applicable_standard=project:{B}）。
    b_config = ReportConfig(
        id=uuid.uuid4(),
        report_type=FinancialReportType.balance_sheet,
        row_number=1,
        row_code="BS-TEST-IDOR",
        row_name="越权测试行",
        applicable_standard=f"project:{proj_b.id}",
        formula="TB('1001','期末余额')",
        is_deleted=False,
    )
    db.add(b_config)
    await db.flush()
    await db.commit()

    s.user_a_id = user_a.id
    s.project_a_id = proj_a.id
    s.project_b_id = proj_b.id
    s.b_wp_id = b_wp.id
    s.b_config_id = b_config.id
    s.b_wp_formula_id = b_formula.id
    return s


def _make_app(db: AsyncSession, user_a: User) -> FastAPI:
    """挂载被测五个 router，override **内层** get_db / get_current_user（教训㉕①）。

    绝不 override `require_project_access(...)` / `require_role([...])` 工厂本身
    （每次返回新函数对象、key 对不上 → 静默失效）。这里只注入 user_a 与测试 session，
    让各端点的真实鉴权判定（加固后才有）自己跑。
    """
    from app.routers import (
        formula as formula_router,
        formula_scope_query as formula_scope_router,
        report_config as report_config_router,
        wp_formula as wp_formula_router,
    )

    app = FastAPI()
    app.include_router(wp_formula_router.router)
    app.include_router(report_config_router.router)
    app.include_router(formula_router.router)
    app.include_router(formula_scope_router.router)

    async def _override_db():
        yield db

    async def _override_user():
        return user_a

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    return app


async def _load_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    return (await db.execute(select(User).where(User.id == user_id))).scalar_one()


# ── 五个越权向量（统一描述，供两层复用）──────────────────────────────────────
#
# 每个向量 = (标签, 调用闭包 client -> Response)。标签对齐 §1 锚点编号。


def _vectors(seed: _Seed):
    pid_b = str(seed.project_b_id)
    wp_b = str(seed.b_wp_id)
    cfg_b = str(seed.b_config_id)

    return [
        # #4 wp_formula 读（GET /api/workpapers/{B_wp_id}/formulas）
        ("wp_formula.read[#4]",
         lambda c: c.get(f"/api/workpapers/{wp_b}/formulas")),
        # #4 wp_formula 写（PUT /api/workpapers/{B_wp_id}/formulas）
        ("wp_formula.write_put[#4]",
         lambda c: c.put(
             f"/api/workpapers/{wp_b}/formulas",
             json={
                 "sheet_name": "Z1-1", "target_cell": "C3",
                 "expression": "2 + 2", "year": _YEAR,
                 "template_type": "soe", "kind": "wp",
                 "category": "auto_calc", "description": "越权写入尝试",
             },
         )),
        # #7 report_config 更新（PUT /api/report-config/{config_id}）
        ("report_config.update[#7]",
         lambda c: c.put(
             f"/api/report-config/{cfg_b}",
             json={"project_id": pid_b, "year": _YEAR, "row_name": "越权改名"},
         )),
        # #10 /api/formula/execute（body.project_id = B）
        ("formula.execute[#10]",
         lambda c: c.post(
             "/api/formula/execute",
             json={"project_id": pid_b, "year": _YEAR,
                   "formula_type": "TB", "params": {}},
         )),
        # #11 formula-scope（GET /api/formula-scope/{B_project_id}/formulas）
        ("formula_scope.read[#11]",
         lambda c: c.get(f"/api/formula-scope/{pid_b}/formulas")),
        # #9 tb_detail 读（GET /api/report-config/tb-detail-formulas/{B_project_id}）
        ("tb_detail.read[#9]",
         lambda c: c.get(f"/api/report-config/tb-detail-formulas/{pid_b}")),
        # #9 tb_detail 写（PUT /api/report-config/tb-detail-formulas/{B_project_id}）
        ("tb_detail.write[#9]",
         lambda c: c.put(
             f"/api/report-config/tb-detail-formulas/{pid_b}",
             json={"overrides": {}, "added": [
                 {"row_code": "9999", "row_name": "越权写入",
                  "formula": "TB('9999','期末余额')"}
             ]},
         )),
    ]


# ══════════════════════════════════════════════════════════════════════════
# 第一层：加固前基线记录（恒通过，坐实 / 推翻 IDOR 的证据）
# ══════════════════════════════════════════════════════════════════════════


class TestCrossProjectBaseline:
    """以项目 A 凭据对项目 B 各资源发请求，**记录加固前实际响应码**。

    本类恒通过（除非端点整个崩成 500）：它的职责是产出 IDOR 坐实基线，供 5.2 / 5.3
    加固与定级（需求 5.8）参考，不是卡门禁。
    """

    @pytest.mark.asyncio
    async def test_record_cross_project_responses(
        self, db: AsyncSession, seed: _Seed, capsys
    ):
        user_a = await _load_user(db, seed.user_a_id)
        app = _make_app(db, user_a)

        rows: list[tuple[str, int]] = []
        # raise_server_exceptions=False：若某端点加固前因 SQLite / 下游旁支抛异常，
        # 以 500 记录而非让测试崩溃 —— 500 同样坐实「鉴权未拦截」（不是 403）。
        with TestClient(app, raise_server_exceptions=False) as client:
            for label, call in _vectors(seed):
                resp = call(client)
                rows.append((label, resp.status_code))

        # 产出一张人读基线表（pytest -s 可见）。
        print("\n=== FM-P0-05 跨项目越权·加固前响应基线 (user_a=manager, 非 B 成员) ===")
        for label, code in rows:
            if code == 403:
                verdict = "[ISOLATED] 已隔离(403)"
            elif 200 <= code < 300:
                verdict = "[IDOR] 坐实越权(2xx)"
            elif code == 422:
                verdict = "[IDOR] 鉴权未拦截(422·入参/校验后置)"
            else:
                verdict = f"[IDOR] 鉴权未拦截({code})"
            print(f"  {label:<28} -> {code}  {verdict}")

        # 断言：该类只记录、不评判，始终通过（恒有 7 条记录）。
        assert len(rows) == len(_vectors(seed))
        # 把基线塞进 node 供其它工具/人读取（不影响判定）。
        self._baseline = dict(rows)  # type: ignore[attr-defined]


# ══════════════════════════════════════════════════════════════════════════
# 第二层：加固后应有形态（Task 5.2 对象型端点 + Task 5.3 report_config CRUD /
# 自定义函数写限 admin 全部合入后，本类 7 条全部转**硬断言**转正 —— 不再 xfail）
#
# 转正依据（门禁断言⑦的硬前置）：Phase 5 全部对象型端点均已加固并通过本坐实：
#   · wp_formula 读/写（Task 5.2）· formula-scope（Task 5.2）· tb_detail 读/写（Task 5.2）
#   · /api/formula/execute（Task 5.2）· report_config.update（Task 5.3，项目克隆行
#     走 require_project_access("edit")，user_a 非 B 成员 → 真实 403）
# 7 条曾全 XPASS，故移除类级 xfail 转为常规硬断言（strict 转正）。任一加固被摘除
# → 对应用例直接 red（变异反证，memory 铁律㉖）。
# ══════════════════════════════════════════════════════════════════════════


class TestCrossProjectHardened:
    """加固后：以项目 A 凭据跨项目访问 B，**全部 403 且 0 副作用**。

    每个端点一条独立用例（逐处可定位，memory 铁律㉖：加固时逐处变异验证）。
    """

    @pytest.mark.asyncio
    async def test_wp_formula_read_forbidden(self, db: AsyncSession, seed: _Seed):
        user_a = await _load_user(db, seed.user_a_id)
        app = _make_app(db, user_a)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(f"/api/workpapers/{seed.b_wp_id}/formulas")
        assert resp.status_code == 403, f"wp_formula 读应 403，实得 {resp.status_code}"

    @pytest.mark.asyncio
    async def test_wp_formula_write_forbidden_zero_side_effect(
        self, db: AsyncSession, seed: _Seed
    ):
        user_a = await _load_user(db, seed.user_a_id)
        before = await _count_b_formulas(db, seed)
        app = _make_app(db, user_a)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.put(
                f"/api/workpapers/{seed.b_wp_id}/formulas",
                json={
                    "sheet_name": "Z1-1", "target_cell": "C3",
                    "expression": "2 + 2", "year": _YEAR,
                    "template_type": "soe", "kind": "wp",
                },
            )
        assert resp.status_code == 403, f"wp_formula 写应 403，实得 {resp.status_code}"
        after = await _count_b_formulas(db, seed)
        assert after == before, f"越权写产生副作用：B 公式数 {before}->{after}"

    @pytest.mark.asyncio
    async def test_report_config_update_forbidden_zero_side_effect(
        self, db: AsyncSession, seed: _Seed
    ):
        user_a = await _load_user(db, seed.user_a_id)
        before = await _b_config_row_name(db, seed)
        app = _make_app(db, user_a)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.put(
                f"/api/report-config/{seed.b_config_id}",
                json={"project_id": str(seed.project_b_id), "row_name": "越权改名"},
            )
        assert resp.status_code == 403, f"report_config 更新应 403，实得 {resp.status_code}"
        after = await _b_config_row_name(db, seed)
        assert after == before, f"越权更新产生副作用：row_name {before!r}->{after!r}"

    @pytest.mark.asyncio
    async def test_formula_execute_forbidden(self, db: AsyncSession, seed: _Seed):
        user_a = await _load_user(db, seed.user_a_id)
        app = _make_app(db, user_a)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/api/formula/execute",
                json={"project_id": str(seed.project_b_id), "year": _YEAR,
                      "formula_type": "TB", "params": {}},
            )
        assert resp.status_code == 403, f"formula/execute 应 403，实得 {resp.status_code}"

    @pytest.mark.asyncio
    async def test_formula_scope_read_forbidden(self, db: AsyncSession, seed: _Seed):
        user_a = await _load_user(db, seed.user_a_id)
        app = _make_app(db, user_a)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(f"/api/formula-scope/{seed.project_b_id}/formulas")
        assert resp.status_code == 403, f"formula-scope 读应 403，实得 {resp.status_code}"

    @pytest.mark.asyncio
    async def test_tb_detail_read_forbidden(self, db: AsyncSession, seed: _Seed):
        user_a = await _load_user(db, seed.user_a_id)
        app = _make_app(db, user_a)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(
                f"/api/report-config/tb-detail-formulas/{seed.project_b_id}"
            )
        assert resp.status_code == 403, f"tb_detail 读应 403，实得 {resp.status_code}"

    @pytest.mark.asyncio
    async def test_tb_detail_write_forbidden_zero_side_effect(
        self, db: AsyncSession, seed: _Seed
    ):
        user_a = await _load_user(db, seed.user_a_id)
        before = await _b_wizard_state(db, seed)
        app = _make_app(db, user_a)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.put(
                f"/api/report-config/tb-detail-formulas/{seed.project_b_id}",
                json={"overrides": {}, "added": [
                    {"row_code": "9999", "row_name": "越权写入",
                     "formula": "TB('9999','期末余额')"}
                ]},
            )
        assert resp.status_code == 403, f"tb_detail 写应 403，实得 {resp.status_code}"
        after = await _b_wizard_state(db, seed)
        assert after == before, f"越权写 tb_detail 产生副作用：wizard_state {before!r}->{after!r}"


# ── 副作用观测辅助 ───────────────────────────────────────────────────────────
#
# 🔴 必须用**独立 session** 观测副作用（不复用请求共享的 `db`）：
#   加固后的写端点在 `edit` 权限下走 `assert_project_permission` →
#   `_check_project_not_archived` → `await db.get(Project, ...)`。本测试把**同一个**
#   AsyncSession 通过 `dependency_overrides` 注入给请求处理器，而 TestClient 在**另一个
#   greenlet/worker** 里跑 handler。若在发请求**前**对共享 `db` 调 `expire_all()`，
#   identity map 里的 Project 被标记过期；handler 侧 `db.get(Project)` 触发**跨 greenlet
#   的惰性刷新 IO** → `sqlalchemy.exc.MissingGreenlet` → 500（而非预期 403）。
#   这纯属「单 session 跨 greenlet 共享」的测试工装假象——生产每请求独立 session、鉴权
#   判定全程在同一请求 greenlet 内，`db.get` 正常，跨项目写真实返回 403（已探针坐实）。
#   故副作用前/后计数一律开**新 session**（_fresh_session），既忠实复现生产（请求 session
#   不被测试侧 expire 污染），又不弱化「0 副作用」断言。
from contextlib import asynccontextmanager


@asynccontextmanager
async def _fresh_session():
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


async def _count_b_formulas(db: AsyncSession, seed: _Seed) -> int:
    async with _fresh_session() as s:
        rows = (
            await s.execute(
                select(WpFormula).where(WpFormula.project_id == seed.project_b_id)
            )
        ).scalars().all()
        return len(rows)


async def _b_config_row_name(db: AsyncSession, seed: _Seed) -> str:
    async with _fresh_session() as s:
        cfg = (
            await s.execute(
                select(ReportConfig).where(ReportConfig.id == seed.b_config_id)
            )
        ).scalar_one()
        return cfg.row_name


async def _b_wizard_state(db: AsyncSession, seed: _Seed):
    async with _fresh_session() as s:
        proj = (
            await s.execute(select(Project).where(Project.id == seed.project_b_id))
        ).scalar_one()
        return proj.wizard_state
