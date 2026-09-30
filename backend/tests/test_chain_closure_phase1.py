# -*- coding: utf-8 -*-
"""阶段一四个根因的变异证明测试。

spec: chain-closure-phase1-root-cause-fixes

四组，每组在修复前**必红**、修复后转绿，且各自带反向断言（防恒真）：

- R1 `PARTNER_ROLES` 漏 admin ⇒ 全局刷新入口在真实环境无人可达
- R2 `page_keys.append("report:*")` 写死 ⇒ 预设库恒不命中，锁死 343 条报表公式
- R3 `on_trial_balance_updated` 漏传 `applicable_standard` ⇒ 走默认 "enterprise"，
  而 `report_config` 无该准则 ⇒ 零行重算且静默成功
- R4 stale 级联只标 `AuditReport`，`financial_report` 从未被标 ⇒ 静默陈旧

🔴 为什么现有 `test_report_engine.py` 测不出 R3：它用 `TEST_STANDARD = "enterprise"`
造 report_config，与真库的 `listed_standalone` 两边自洽但永不相交；且现有测试**全部直接调**
`regenerate_affected` 并显式传准则，**没有一个走 handler 路径** —— 本文件是 handler 路径的首个覆盖。
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.report_models import (
    AuditReport,
    FinancialReport,
    FinancialReportType,
    ReportConfig,
)
from app.services.report_engine import ReportEngine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_URL = "sqlite+aiosqlite:///:memory:"
# 🔴 必须 StaticPool：SQLite `:memory:` 对**每个连接**是独立数据库。R4 的 handler 内部
# 自己 `async with async_session_factory()` 开新 session（新连接），默认池下会连到一个
# **空库**，update 影响 0 行 —— 看起来像「修复没生效」，实则测试环境问题。
_engine = create_async_engine(_URL, echo=False, poolclass=StaticPool)

USER_ID = uuid.uuid4()
PROJ_ID = uuid.uuid4()
YEAR = 2025
# 本项目真实准则：template_type='listed' + report_scope='standalone'
REAL_STANDARD = "listed_standalone"
# 现行 regenerate_affected 的默认值 —— 真库 report_config 里零行
DEAD_STANDARD = "enterprise"


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def seeded(db: AsyncSession):
    """项目(listed+standalone) + TB 两行 + report_config(listed_standalone) + 报表两行。"""
    db.add(Project(
        id=PROJ_ID,
        name="链条闭环阶段一测试_2025",
        client_name="链条闭环阶段一测试",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=USER_ID,
        template_type="listed",
        report_scope="standalone",
    ))
    await db.flush()

    # 试算表：1122 资产 / 6001 收入（审定数 = 未审 + aje）
    for code, name, cat, unadj in (
        ("1122", "应收账款", AccountCategory.asset, Decimal("1000000")),
        ("6001", "主营业务收入", AccountCategory.revenue, Decimal("2000000")),
    ):
        db.add(TrialBalance(
            project_id=PROJ_ID, year=YEAR, company_code="001",
            standard_account_code=code, account_name=name, account_category=cat,
            unadjusted_amount=unadj, audited_amount=unadj,
            opening_balance=Decimal("0"),
            aje_adjustment=Decimal("0"), rje_adjustment=Decimal("0"),
        ))

    # 报表配置：只造项目真实准则那一套（刻意不造 enterprise，复现真库分布）
    cfgs = [
        (FinancialReportType.balance_sheet, 1, "BS-006", "应收账款", "TB('1122','期末余额')"),
        (FinancialReportType.income_statement, 1, "IS-001", "一、营业收入", "TB('6001','期末余额')"),
    ]
    for rt, no, rc, rn, formula in cfgs:
        db.add(ReportConfig(
            report_type=rt, row_number=no, row_code=rc, row_name=rn,
            formula=formula, applicable_standard=REAL_STANDARD,
            indent_level=0, is_total_row=False,
        ))

    # 报表既有数据（旧快照，值刻意偏离当前审定数）
    for rt, rc, rn, amt in (
        (FinancialReportType.balance_sheet, "BS-006", "应收账款", Decimal("1")),
        (FinancialReportType.income_statement, "IS-001", "一、营业收入", Decimal("2")),
    ):
        db.add(FinancialReport(
            project_id=PROJ_ID, year=YEAR, report_type=rt, row_code=rc, row_name=rn,
            current_period_amount=amt, prior_period_amount=Decimal("0"),
            is_stale=False, indent_level=0, is_total_row=False,
            # 🔴 必须显式传 is_deleted：SQLite 下无 server_default 时落 NULL，
            # 而 handler 用 `is_deleted == False` 过滤 ⇒ NULL 不匹配 ⇒ update 0 行，
            # 看起来像「修复没生效」。真库该列有 server_default false，无此问题。
            is_deleted=False,
        ))
    await db.flush()
    return db


# ═══════════════════════════════════════════════════════════════════════════════
# R3：报表增量重算必须用项目真实准则
# ═══════════════════════════════════════════════════════════════════════════════
class TestR3RecalcUsesProjectStandard:
    @pytest.mark.asyncio
    async def test_dead_standard_loads_zero_configs(self, seeded: AsyncSession):
        """反向断言（防恒真）：'enterprise' 在本库确实零命中。

        这是 R3 的分母。若此断言失败说明 fixture 造了 enterprise 配置，判据失效。
        """
        eng = ReportEngine(seeded)
        dead = await eng._load_report_configs(DEAD_STANDARD)
        assert sum(len(v) for v in dead.values()) == 0, (
            f"'{DEAD_STANDARD}' 竟加载到配置，R3 判据的分母被污染"
        )
        real = await eng._load_report_configs(REAL_STANDARD)
        assert sum(len(v) for v in real.values()) > 0, (
            f"'{REAL_STANDARD}' 应有配置，fixture 造数据失败"
        )

    @pytest.mark.asyncio
    async def test_resolver_returns_project_real_standard(self, seeded: AsyncSession):
        """项目准则解析器对 listed+standalone 应得 listed_standalone。"""
        from app.services.report_config_service import ReportConfigService

        got = await ReportConfigService.resolve_applicable_standard(seeded, PROJ_ID)
        assert got == REAL_STANDARD, f"准则解析得 {got!r}，期望 {REAL_STANDARD!r}"

    @pytest.mark.asyncio
    async def test_handler_path_actually_regenerates(self, seeded: AsyncSession):
        """🔴 核心变异：走 on_trial_balance_updated handler 路径必须真重算。

        修复前：handler 不传 applicable_standard → 默认 'enterprise' → 零配置 → 报表值不变（红）
        修复后：handler 解析出 listed_standalone → 报表值被重算为当前审定数（绿）
        """
        before = {
            r.row_code: r.current_period_amount
            for r in (await seeded.execute(sa.select(FinancialReport))).scalars()
        }
        assert before == {"BS-006": Decimal("1"), "IS-001": Decimal("2")}, before

        eng = ReportEngine(seeded)
        await eng.on_trial_balance_updated(EventPayload(
            event_type=EventType.TRIAL_BALANCE_UPDATED,
            project_id=PROJ_ID, year=YEAR, account_codes=["1122", "6001"],
        ))
        await seeded.flush()

        after = {
            r.row_code: r.current_period_amount
            for r in (await seeded.execute(sa.select(FinancialReport))).scalars()
        }
        assert after["BS-006"] == Decimal("1000000"), (
            f"BS-006 未被重算（{before['BS-006']} → {after['BS-006']}）"
            "：handler 路径仍在用零命中的默认准则"
        )
        assert after["IS-001"] == Decimal("2000000"), (
            f"IS-001 未被重算（{before['IS-001']} → {after['IS-001']}）"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# R4：stale 级联必须标到 financial_report（而不只是 AuditReport）
# ═══════════════════════════════════════════════════════════════════════════════
def _find_handler(name: str, event_type: EventType):
    """从全局 event_bus 取指定名字的 handler（只跑目标 handler，不跑全套）。"""
    from app.services.event_bus import event_bus
    from app.services.event_handlers import register_event_handlers

    if not event_bus._handlers.get(event_type):
        register_event_handlers()
    for h in event_bus._handlers.get(event_type, []):
        if getattr(h, "__name__", "") == name:
            return h
    return None


class TestR4StaleMarksFinancialReport:
    @pytest.mark.asyncio
    async def test_stale_cascade_marks_financial_report(
        self, seeded: AsyncSession, monkeypatch
    ):
        """🔴 核心变异：调整分录 stale 级联必须置 financial_report.is_stale。

        修复前：只标 AuditReport，financial_report 一行未标（红）
        修复后：该项目该年度全部被标，且 AuditReport 仍被标（零回归）
        """
        from app.models.report_models import OpinionType

        seeded.add(AuditReport(
            project_id=PROJ_ID, year=YEAR, is_stale=False,
            opinion_type=OpinionType.unqualified, is_deleted=False,
        ))
        await seeded.commit()

        factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

        # ── 诊断分母：handler 内三条 update 各自单独执行，确认哪条会抛 ──────────
        # （handler 外层 except 会 rollback 整个 session，任一条抛都会连带丢失前面的更新）
        from app.models.report_models import DisclosureNote

        diag: dict[str, str] = {}
        for nm, model in (("AuditReport", AuditReport),
                          ("FinancialReport", FinancialReport),
                          ("DisclosureNote", DisclosureNote)):
            async with factory() as s:
                try:
                    r = await s.execute(
                        sa.update(model).where(
                            model.project_id == PROJ_ID,
                            model.year == YEAR,
                            model.is_deleted == sa.false(),
                        ).values(is_stale=True)
                    )
                    await s.commit()
                    diag[nm] = f"OK rowcount={r.rowcount}"
                except Exception as e:  # noqa: BLE001
                    await s.rollback()
                    diag[nm] = f"{type(e).__name__}: {str(e)[:160]}"
        # 复原，让 handler 从干净状态跑
        async with factory() as s:
            await s.execute(sa.update(FinancialReport).values(is_stale=False))
            await s.commit()

        assert "OK" in diag["FinancialReport"], (
            f"FinancialReport 单独 update 就失败 ⇒ 不是 handler 的问题: {diag}"
        )

        handler = _find_handler(
            "_mark_reports_stale_on_adjustment", EventType.ADJUSTMENT_APPROVED
        )
        assert handler is not None, "取不到 _mark_reports_stale_on_adjustment handler"

        # 让 handler 内的 async_session_factory 指向测试库。
        # 🔴 必须经 `handler.__module__` 反查 `sys.modules` 取模块对象：
        # `event_handlers/__init__.py` 做了 `sys.modules[__name__] = _impl` 的**模块替换**，
        # 于是 `from app.services.event_handlers import _impl` 会触发 import fallback
        # 而**重复加载**出第二个实例（实测名字变成 `...._impl._impl`、
        # `is` 比较为 False）—— patch 打在副本上，handler 完全不受影响，测试会假红。
        import sys as _sys

        hmod = _sys.modules[handler.__module__]
        monkeypatch.setattr(hmod, "async_session_factory", factory)
        assert hmod.async_session_factory is factory, "patch 未生效，测试会假红"

        await handler(EventPayload(
            event_type=EventType.ADJUSTMENT_APPROVED,
            project_id=PROJ_ID, year=YEAR, account_codes=["1122"],
        ))

        async with factory() as s:
            fr = (await s.execute(sa.select(FinancialReport))).scalars().all()
            assert fr, "fixture 未造 financial_report 行，判据无分母"
            stale_n = sum(1 for r in fr if r.is_stale)
            assert stale_n == len(fr), (
                f"financial_report 仅 {stale_n}/{len(fr)} 被标 stale"
                f"：stale 级联没标到财务报表数据表；三表单独 update 诊断={diag}"
            )
            ar = (await s.execute(sa.select(AuditReport))).scalars().all()
            assert ar and all(r.is_stale for r in ar), (
                "AuditReport 不再被标 ⇒ 零回归被破坏"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# R2：report scope 的 page_keys 必须逐张派生且全部命中预设库
# ═══════════════════════════════════════════════════════════════════════════════
class TestR2ReportScopePageKeys:
    def test_wildcard_is_not_a_real_preset_key(self):
        """反向断言（证明旧实现确实坏）：'report:*' 不在预设库索引里。"""
        from app.services.formula_management.preset_library import build_preset_index

        idx = build_preset_index()
        assert "report:*" not in idx, "'report:*' 竟成了真实预设键，本判据失效"
        report_keys = [k for k in idx if k.startswith("report:")]
        assert len(report_keys) > 0, "预设库无 report: 前缀键，判据无分母"

    @pytest.mark.asyncio
    async def test_report_scope_page_keys_all_hit_presets(self, seeded: AsyncSession):
        """🔴 核心变异：scope='report' 派生的 page_keys 必须全部命中预设库。

        修复前：派生出 ['report:*']，命中 0（红）
        修复后：派生出全部 report: 前缀键，逐个命中（绿）
        """
        from app.services.formula_management.draft_refresh_orchestrator import (
            DraftRefreshOrchestrator,
        )
        from app.services.formula_management.preset_library import build_preset_index

        idx = build_preset_index()
        expected = sorted(k for k in idx if k.startswith("report:"))

        orch = DraftRefreshOrchestrator(seeded)
        _units, page_keys = await orch._dispatch_via_coordinator(
            "report", project_id=PROJ_ID, year=YEAR
        )

        assert page_keys, "report scope 未派生任何 page_key"
        missed = [k for k in page_keys if k not in idx]
        assert not missed, f"派生的 page_keys 有 {len(missed)} 个不命中预设库: {missed}"
        assert sorted(page_keys) == expected, (
            f"派生集合与预设库 report: 键不等\n派生={sorted(page_keys)}\n预设={expected}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# R1：全局刷新门禁必须对真实存在的角色可达
# ═══════════════════════════════════════════════════════════════════════════════
class TestR1DraftRefreshGate:
    def test_whitelist_reachable_by_real_user_role(self):
        """白名单至少有一个条目能匹配 ``users.role`` 的真实枚举值（可达性）。

        🔴 实测事实（本测试据此立判据）：``UserRole`` 只有
        admin/partner/manager/auditor/qc/eqcr/readonly，**没有 signing_partner** ——
        它是**项目级分配角色**（`project_assignments.role` / `staff_members`），
        与 `users.role` 不是同一套。而 `deps.require_role` 比对的是 `users.role.value`
        ⇒ 白名单里的 `signing_partner` 对该端点**永不匹配**。

        为什么不删 `signing_partner`：它永不匹配但无害，删掉会破坏「将来 UserRole
        补该成员」的向前兼容。真正的故障是**没有任何可匹配的角色**（真库零 partner），
        判据因此立在「可达性」而非「无幽灵条目」上。
        """
        from app.models.core import UserRole
        from app.routers.draft_refresh import PARTNER_ROLES

        valid = {m.value for m in UserRole}
        reachable = [r for r in PARTNER_ROLES if r in valid]
        assert reachable, (
            f"PARTNER_ROLES={PARTNER_ROLES} 没有一个条目属于 UserRole"
            f"（枚举实有 {sorted(valid)}）⇒ 端点对任何账号都不可达"
        )
        # 真库现存角色只有 admin / auditor ⇒ 可达集合必须与之有交集
        assert set(reachable) & {"admin", "auditor"}, (
            f"白名单可达角色 {reachable} 与真库现存角色 {{admin, auditor}} 无交集"
            " ⇒ 仍然无人能触发全局刷新"
        )

    def test_admin_is_allowed(self):
        """🔴 核心变异：admin 必须在白名单里（修复前红）。"""
        from app.routers.draft_refresh import PARTNER_ROLES

        assert "admin" in PARTNER_ROLES, (
            "admin 不在全局刷新白名单 ⇒ 全库 61 个活跃用户"
            "（auditor 53 + admin 8、零 partner）无人能触发自动刷新"
        )

    def test_auditor_stays_denied(self):
        """反向断言（防修过头）：auditor / readonly 不得被放开。"""
        from app.routers.draft_refresh import PARTNER_ROLES

        assert "auditor" not in PARTNER_ROLES, (
            "auditor 被放进白名单 ⇒ 审计助理可批量改写全项目底稿/报表/附注初稿"
        )
        assert "readonly" not in PARTNER_ROLES

    @pytest.mark.asyncio
    async def test_endpoint_level_role_gate(self, seeded: AsyncSession):
        """端点级真发请求：admin 不得 403，auditor 必须 403。

        🔴 依赖工厂坑：``require_role(...)`` 每次返回**新函数对象**，直接
        ``dependency_overrides[require_role([...])]`` 的 key 匹配不上会静默失效
        ⇒ 必须 override **内层** ``get_current_user``，让真实角色判定跑。
        """
        from httpx import ASGITransport, AsyncClient

        from app.core.database import get_db
        from app.deps import get_current_user
        from app.main import app
        from app.models.core import User, UserRole

        body = {
            "project_id": str(PROJ_ID),
            "year": YEAR,
            "scopes": ["report"],
            "transaction_mode": "partial_success",
        }

        async def _run_as(role: UserRole) -> int:
            user = User(
                id=uuid.uuid4(),
                username=f"probe_{role.value}",
                role=role,
                is_active=True,
            )
            app.dependency_overrides[get_current_user] = lambda: user
            app.dependency_overrides[get_db] = lambda: seeded
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://t"
                ) as c:
                    r = await c.post("/api/workpapers/draft-refresh", json=body)
                    return r.status_code
            finally:
                app.dependency_overrides.pop(get_current_user, None)
                app.dependency_overrides.pop(get_db, None)

        assert await _run_as(UserRole.auditor) == 403, "auditor 应被拒"
        assert await _run_as(UserRole.admin) != 403, (
            "admin 仍被 403 ⇒ 全局刷新入口对现存账号不可达"
        )
